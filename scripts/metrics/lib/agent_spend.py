#!/usr/bin/env python3
"""Where subagents spend their context: tool calls and tool-result size, from Claude Code transcripts.

Reads subagent transcripts (``<projects>/<workspace slug>/<session>/subagents/agent-*.jsonl``,
labelled by the ``agent-*.meta.json`` beside each) and reports, per agent and in total:

- tool calls by tool, and the characters of tool RESULT each tool put into context;
- Read results by kind of file (task file, design doc, rules, tests, source, ...) and how much
  of that was whole-file reads (no ``offset``/``limit``);
- the files most often read whole, and how many agents read each;
- how much source/test reading went to files the same agent never edited (orientation).

Token figures are estimates: characters / 4. Unparseable transcript lines are counted and
reported, never skipped silently.

Usage:
    python agent_spend.py [--session ID ...] [--days N] [--transcript PATH ...] [--top N]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from datrix_scripts.paths import WORKSPACE_DIR

EXIT_OK: Final[int] = 0
EXIT_NOTHING: Final[int] = 1
EXIT_USAGE: Final[int] = 2
CHARS_PER_TOKEN: Final[int] = 4
SECONDS_PER_DAY: Final[int] = 86_400
PROJECTS_DIR: Final[Path] = Path.home() / ".claude" / "projects"
SUBAGENT_GLOB: Final[str] = "*/subagents/agent-*.jsonl"
META_SUFFIX: Final[str] = ".meta.json"
READ_TOOL: Final[str] = "Read"
UNKNOWN_TOOL: Final[str] = "?"
EDIT_TOOLS: Final[frozenset[str]] = frozenset({"Edit", "Write", "NotebookEdit"})
SHELL_TOOLS: Final[tuple[str, ...]] = ("Bash", "PowerShell")
CODE_KINDS: Final[frozenset[str]] = frozenset({"source .py", "tests"})
_SLUG_CHARS: Final[re.Pattern[str]] = re.compile(r"[^A-Za-z0-9]")

#: (substring of the lower-cased, forward-slashed path, kind) -- first match wins.
FILE_KINDS: Final[tuple[tuple[str, str], ...]] = (
    ("/.tasks/", "task file"),
    ("/design/", "design doc"),
    ("architecture-cheat-sheet", "architecture docs"),
    ("/docs/architecture/", "architecture docs"),
    ("ai-agent-rules", "agent rules / guidelines"),
    ("/contributing/", "agent rules / guidelines"),
    ("execution-contract", "agent harness docs"),
    ("/.claude/", "agent harness docs"),
    ("/tests/", "tests"),
)

ToolUses = dict[str, tuple[str, dict[str, object]]]


def kind_of(path: str) -> str:
    """The kind of file a Read touched (see ``FILE_KINDS``)."""
    normalized = path.replace("\\", "/").lower()
    for needle, kind in FILE_KINDS:
        if needle in normalized:
            return kind
    if normalized.endswith(".py"):
        return "source .py"
    if normalized.endswith((".md", ".toml", ".json", ".yaml", ".yml")):
        return "other docs/config"
    return "other"


def text_of(content: object) -> str:
    """The text of a message or tool-result content value (string or list of parts)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            text_of(part.get("text", part.get("content", ""))) if isinstance(part, dict) else str(part) for part in content
        )
    return ""


def _short(path: str) -> str:
    normalized = path.replace("\\", "/")
    prefix = WORKSPACE_DIR.as_posix() + "/"
    return normalized[len(prefix) :] if normalized.lower().startswith(prefix.lower()) else normalized


@dataclass
class AgentSpend:
    """One subagent's tool use."""

    label: str
    turns: int = 0
    bad_lines: int = 0
    calls: Counter[str] = field(default_factory=Counter)
    result_chars: Counter[str] = field(default_factory=Counter)
    read_by_kind: Counter[str] = field(default_factory=Counter)
    whole_read_by_kind: Counter[str] = field(default_factory=Counter)
    whole_read_files: Counter[str] = field(default_factory=Counter)
    code_reads: Counter[str] = field(default_factory=Counter)
    edited: set[str] = field(default_factory=set)

    @property
    def total_chars(self) -> int:
        return sum(self.result_chars.values())

    @property
    def orientation_chars(self) -> int:
        return sum(size for name, size in self.code_reads.items() if name not in self.edited)

    def record_use(self, name: str, tool_input: dict[str, object]) -> None:
        self.calls[name] += 1
        if name in EDIT_TOOLS:
            self.edited.add(str(tool_input.get("file_path", "")).replace("\\", "/").lower())

    def record_result(self, name: str, tool_input: dict[str, object], size: int) -> None:
        self.result_chars[name] += size
        if name != READ_TOOL:
            return
        path = str(tool_input.get("file_path", ""))
        kind = kind_of(path)
        self.read_by_kind[kind] += size
        if kind in CODE_KINDS:
            self.code_reads[path.replace("\\", "/").lower()] += size
        if "offset" not in tool_input and "limit" not in tool_input:
            self.whole_read_by_kind[kind] += size
            self.whole_read_files[_short(path)] += size

    def record_part(self, part: dict[str, object], uses: ToolUses) -> None:
        """Account one content part: a tool call, or the result it produced."""
        kind = part.get("type")
        if kind == "tool_use":
            raw_input = part.get("input")
            tool_input = raw_input if isinstance(raw_input, dict) else {}
            name = str(part.get("name"))
            uses[str(part.get("id"))] = (name, tool_input)
            self.record_use(name, tool_input)
        elif kind == "tool_result":
            name, tool_input = uses.get(str(part.get("tool_use_id")), (UNKNOWN_TOOL, {}))
            self.record_result(name, tool_input, len(text_of(part.get("content"))))


def _label(transcript: Path) -> str:
    meta = transcript.with_name(transcript.stem + META_SUFFIX)
    if meta.is_file():
        data = json.loads(meta.read_text(encoding="utf-8"))
        description = data.get("description") if isinstance(data, dict) else None
        if isinstance(description, str) and description:
            return description
    return transcript.stem


def _rows(transcript: Path, spend: AgentSpend) -> Iterable[dict[str, object]]:
    for line in transcript.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            spend.bad_lines += 1
            continue
        if isinstance(row, dict):
            yield row


def _content_parts(row: dict[str, object]) -> list[object]:
    message = row.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    return content if isinstance(content, list) else []


def analyse(transcript: Path) -> AgentSpend:
    """Tool use of one subagent transcript."""
    spend = AgentSpend(label=_label(transcript))
    uses: ToolUses = {}
    for row in _rows(transcript, spend):
        if row.get("type") == "assistant":
            spend.turns += 1
        for part in _content_parts(row):
            if isinstance(part, dict):
                spend.record_part(part, uses)
    return spend


def project_dir(projects: Path, workspace: Path) -> Path:
    """The Claude Code project folder of *workspace* (its path with every non-alphanumeric as '-').

    Raises:
        FileNotFoundError: No folder matches, naming the slug expected.
    """
    slug = _SLUG_CHARS.sub("-", str(workspace))
    if projects.is_dir():
        for candidate in projects.iterdir():
            if candidate.is_dir() and candidate.name.lower() == slug.lower():
                return candidate
    raise FileNotFoundError(
        f"No Claude Code project folder {slug!r} under {projects}. Fix: pass --transcript paths explicitly."
    )


def select_transcripts(args: argparse.Namespace) -> list[Path]:
    if args.transcript:
        return [Path(path) for path in args.transcript]
    folder = project_dir(PROJECTS_DIR, WORKSPACE_DIR)
    found = sorted(folder.glob(SUBAGENT_GLOB))
    if args.session:
        return [path for path in found if path.parent.parent.name in set(args.session)]
    cutoff = time.time() - args.days * SECONDS_PER_DAY
    return [path for path in found if path.stat().st_mtime >= cutoff]


def _tokens(chars: int) -> str:
    return f"~{chars // CHARS_PER_TOKEN:,}"


def _share(part: int, whole: int) -> str:
    return f"{part / whole:4.0%}" if whole else "   -"


@dataclass
class Totals:
    """Every agent's counters summed."""

    result_chars: Counter[str] = field(default_factory=Counter)
    calls: Counter[str] = field(default_factory=Counter)
    read_by_kind: Counter[str] = field(default_factory=Counter)
    whole_read_by_kind: Counter[str] = field(default_factory=Counter)
    whole_read_files: Counter[str] = field(default_factory=Counter)
    readers: Counter[str] = field(default_factory=Counter)

    @classmethod
    def of(cls, agents: Sequence[AgentSpend]) -> Totals:
        totals = cls()
        for agent in agents:
            totals.result_chars.update(agent.result_chars)
            totals.calls.update(agent.calls)
            totals.read_by_kind.update(agent.read_by_kind)
            totals.whole_read_by_kind.update(agent.whole_read_by_kind)
            totals.whole_read_files.update(agent.whole_read_files)
            totals.readers.update(set(agent.whole_read_files))
        return totals


def _print_tools_and_reads(totals: Totals, agent_count: int, top: int) -> None:
    grand = sum(totals.result_chars.values())
    print(f"{agent_count} subagent(s); tool results took {_tokens(grand)} tokens, {_tokens(grand // max(agent_count, 1))} per agent.")
    print("\nBy tool (calls, tokens, share):")
    for name, chars in totals.result_chars.most_common(top):
        print(f"  {name:14} {totals.calls[name]:6} calls  {_tokens(chars):>12} tokens  {_share(chars, grand)}")
    reads = sum(totals.read_by_kind.values())
    print(f"\nRead results by kind of file ({_tokens(reads)} tokens; whole-file reads in the last column):")
    for kind, chars in totals.read_by_kind.most_common():
        whole = _tokens(totals.whole_read_by_kind[kind])
        print(f"  {kind:26} {_tokens(chars):>12} tokens  {_share(chars, reads)}   whole {whole:>10}")
    print("\nFiles read whole most (tokens, agents that read it whole):")
    for name, chars in totals.whole_read_files.most_common(top):
        print(f"  {_tokens(chars):>10}  x{totals.readers[name]:<3} {name}")


def print_report(agents: Sequence[AgentSpend], top: int) -> None:
    _print_tools_and_reads(Totals.of(agents), len(agents), top)
    code = sum(sum(agent.code_reads.values()) for agent in agents)
    orientation = sum(agent.orientation_chars for agent in agents)
    print(
        f"\nSource/test reading: {_tokens(code)} tokens; on files the reading agent never edited: "
        f"{_tokens(orientation)} ({_share(orientation, code).strip()})."
    )
    print("\nPer agent (turns, tokens in tool results, Read share, shell share):")
    for agent in sorted(agents, key=lambda item: -item.total_chars):
        chars = agent.total_chars
        shell = sum(agent.result_chars[name] for name in SHELL_TOOLS)
        read = _share(agent.result_chars[READ_TOOL], chars)
        print(f"  {agent.turns:5} turns {_tokens(chars):>10}  Read {read}  shell {_share(shell, chars)}  {agent.label}")
    bad = sum(agent.bad_lines for agent in agents)
    if bad:
        print(f"\n{bad} transcript line(s) were not JSON and were not counted.")


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--session", action="append", default=[], help="Only this session's subagents. Repeatable.")
    parser.add_argument("--days", type=int, default=7, help="Without --session: subagents active in the last N days. Default 7.")
    parser.add_argument("--transcript", action="append", default=[], help="Explicit transcript path. Repeatable.")
    parser.add_argument("--top", type=int, default=20, help="Rows in the per-tool and per-file tables. Default 20.")
    return parser.parse_args(argv)


def main(argv: Sequence[str]) -> int:
    args = parse_args(argv)
    if args.days <= 0 or args.top <= 0:
        print(f"--days and --top must be positive; got {args.days} and {args.top}.")
        return EXIT_USAGE
    try:
        transcripts = select_transcripts(args)
    except FileNotFoundError as exc:
        print(str(exc))
        return EXIT_USAGE
    if not transcripts:
        print("No subagent transcripts matched. Widen --days, or pass --session / --transcript.")
        return EXIT_NOTHING
    print_report([analyse(path) for path in transcripts], args.top)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
