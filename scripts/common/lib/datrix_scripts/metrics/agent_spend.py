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

Run by ``metrics/agent-spend.ps1`` (POSIX twin ``agent-spend.sh``):
``--session`` / ``--transcript`` repeatable (a value may also be a comma-separated list),
``--days N``, ``--top N``, ``--self-test``.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import sys
import tempfile
import time
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.test.wrappers import METRICS_SCRIPTS_DIR, module_main, run_self_test

MODULE: Final = "datrix_scripts.metrics.agent_spend"
WRAPPER: Final = "agent-spend"
EXIT_OK: Final[int] = 0
EXIT_NOTHING: Final[int] = 1
EXIT_USAGE: Final[int] = 2
DEFAULT_DAYS: Final = 7
DEFAULT_TOP: Final = 20
#: The wrapper's ``ValidateRange`` bounds, enforced here too for a caller of the ``.sh`` twin.
DAYS_RANGE: Final = (1, 3650)
TOP_RANGE: Final = (1, 1000)
_LIST_SEPARATOR: Final = ","
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


def split_values(values: Sequence[str]) -> list[str]:
    """Every value of a repeatable option, each also split on commas (``powershell -File`` passes ``a,b``
    as one string), trimmed, empty pieces dropped."""
    return [piece.strip() for value in values for piece in value.split(_LIST_SEPARATOR) if piece.strip()]


def select_transcripts(args: argparse.Namespace) -> list[Path]:
    transcripts = split_values(args.transcript)
    if transcripts:
        return [Path(path) for path in transcripts]
    folder = project_dir(PROJECTS_DIR, WORKSPACE_DIR)
    found = sorted(folder.glob(SUBAGENT_GLOB))
    sessions = set(split_values(args.session))
    if sessions:
        return [path for path in found if path.parent.parent.name in sessions]
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


def build_parser() -> argparse.ArgumentParser:
    """The options of ``metrics/agent-spend.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False
    )
    parser.add_argument("--session", action="append", default=[], help="Only this session's subagents. Repeatable.")
    parser.add_argument(
        "--days", type=int, default=DEFAULT_DAYS,
        help=f"Without --session: subagents active in the last N days. Default {DEFAULT_DAYS}.",
    )
    parser.add_argument("--transcript", action="append", default=[], help="Explicit transcript path. Repeatable.")
    parser.add_argument(
        "--top", type=int, default=DEFAULT_TOP, help=f"Rows in the per-tool and per-file tables. Default {DEFAULT_TOP}."
    )
    parser.add_argument("--self-test", action="store_true", help="Run only the self-test over a planted transcript.")
    parser.set_defaults(debug=False)
    return parser


def _out_of_range(value: int, bounds: tuple[int, int]) -> bool:
    low, high = bounds
    return not low <= value <= high


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        return run_self_test(
            SELF_TEST_CHECKS, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=METRICS_SCRIPTS_DIR
        )
    if _out_of_range(args.days, DAYS_RANGE) or _out_of_range(args.top, TOP_RANGE):
        print(
            f"--days must be {DAYS_RANGE[0]}-{DAYS_RANGE[1]} and --top {TOP_RANGE[0]}-{TOP_RANGE[1]}; "
            f"got {args.days} and {args.top}. Fix: pass values inside those ranges."
        )
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


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

_PLANTED_FILE: Final = "D:/w/datrix-a/src/m.py"


def _planted_transcript(root: Path) -> Path:
    """One subagent transcript under *root*: a whole-file Read of a source file (40 result characters),
    a ranged Read, a Bash call, its meta.json label, and one line that is not JSON."""
    transcript = root / "agent-a1.jsonl"
    rows = [
        {"message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "Read", "input": {"file_path": _PLANTED_FILE}},
            {"type": "tool_use", "id": "t2", "name": "Read", "input": {"file_path": _PLANTED_FILE, "offset": 1}},
            {"type": "tool_use", "id": "t3", "name": "Bash", "input": {"command": "ls"}},
        ]}},
        {"message": {"content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "x" * 40},
            {"type": "tool_result", "tool_use_id": "t2", "content": [{"type": "text", "text": "y" * 8}]},
            {"type": "tool_result", "tool_use_id": "t3", "content": "z" * 4},
        ]}},
    ]
    lines = [json.dumps(row) for row in rows] + ["not json"]
    transcript.write_text("\n".join(lines) + "\n", encoding="utf-8")
    transcript.with_name(transcript.stem + META_SUFFIX).write_text(
        json.dumps({"description": "planted agent"}), encoding="utf-8"
    )
    return transcript


def _printed(argv: Sequence[str]) -> tuple[int, str]:
    printed = io.StringIO()
    with contextlib.redirect_stdout(printed):
        code = main(argv)
    return code, printed.getvalue()


def _check_planted_transcript_is_measured() -> None:
    with tempfile.TemporaryDirectory() as raw:
        spend = analyse(_planted_transcript(Path(raw)))
    assert spend.label == "planted agent", spend.label
    assert spend.calls == Counter({"Read": 2, "Bash": 1}), spend.calls
    assert spend.result_chars == Counter({"Read": 48, "Bash": 4}), spend.result_chars
    assert spend.whole_read_by_kind == Counter({"source .py": 40}), spend.whole_read_by_kind
    assert spend.bad_lines == 1, spend.bad_lines


def _check_report_names_the_agent_and_the_bad_line() -> None:
    with tempfile.TemporaryDirectory() as raw:
        transcript = _planted_transcript(Path(raw))
        code, text = _printed([f"--transcript={transcript}", "--top=5"])
    assert code == EXIT_OK, (code, text)
    assert "1 subagent(s); tool results took ~13 tokens" in text, text
    assert "planted agent" in text, text
    assert "1 transcript line(s) were not JSON and were not counted." in text, text


def _check_comma_lists_are_split() -> None:
    assert split_values(["a,b", " c ", ",,"]) == ["a", "b", "c"], split_values(["a,b", " c ", ",,"])


def _check_out_of_range_is_refused_with_exit_two() -> None:
    for argv in (["--days=0"], [f"--days={DAYS_RANGE[1] + 1}"], ["--top=0"], [f"--top={TOP_RANGE[1] + 1}"]):
        code, text = _printed(argv)
        assert code == EXIT_USAGE, (argv, code, text)
        assert "Fix: pass values inside those ranges." in text, text


def _check_missing_project_folder_names_the_fix() -> None:
    with tempfile.TemporaryDirectory() as raw:
        try:
            project_dir(Path(raw), Path("D:/no-such-workspace"))
        except FileNotFoundError as exc:
            message = str(exc)
        else:
            raise AssertionError("project_dir found a folder in an empty projects directory")
    assert "'D--no-such-workspace'" in message and "Fix: pass --transcript paths explicitly." in message, message


SELF_TEST_CHECKS: Final[tuple[Callable[[], None], ...]] = (
    _check_planted_transcript_is_measured,
    _check_report_names_the_agent_and_the_bad_line,
    _check_comma_lists_are_split,
    _check_out_of_range_is_refused_with_exit_two,
    _check_missing_project_folder_names_the_fix,
)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
