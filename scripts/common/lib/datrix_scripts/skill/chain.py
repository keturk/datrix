"""Run skills as headless Claude Code steps, each in its own ``claude -p`` session.

A skill invoked from inside another skill runs on the caller's model; only a slash command typed as
the prompt switches to the skill's own ``model:`` and ``effort:``. Each step here is such a prompt, so
every step runs on its skill's model, with the hooks, CLAUDE.md and guards of an interactive session.
Used by ``datrix_scripts.skill.skill_chain``, ``implement_design`` and ``implement_finding``.

Each step's prompt reaches the CLI on stdin, never as an argument: on Windows ``claude`` is the
``claude.cmd`` batch shim, where ``cmd.exe`` would end the command at the prompt's first line break.
Every remaining argument is fixed, from a closed set, numeric or validated (the model name, the
session id), and ``claude_cli.require_batch_safe`` refuses the vector before launch otherwise.

A step streams its events: each is kept in ``<label>.stream.jsonl`` under the run's folder
(``<workspace>/.tmp/skill-chain/<timestamp>/``) and, unless quiet, shown as one line; the final result
event is kept in ``<label>.json`` and the CLI's stderr in ``<label>.stderr.txt``.

A chain ends by raising ``ChainStopped`` with its exit code: 0 every step finished
(``Chain.complete``), 1 a step ended in error or a check failed, 2 a step stopped for a decision only
Jon can make (``Chain.stop``).
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import time
import uuid
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import IO, Final, NoReturn

from datrix_scripts.claude_cli import CLAUDE, require_batch_safe
from datrix_scripts.gate_harness import UsageError, expect_usage_error, write_files
from datrix_scripts.logging_utils import ColorCodes, say

EXIT_DONE: Final = 0
EXIT_FAILED: Final = 1
EXIT_NEEDS_JON: Final = 2

PERMISSION_MODES: Final = ("auto", "acceptEdits", "dontAsk", "bypassPermissions")
DEFAULT_PERMISSION_MODE: Final = "auto"
EFFORTS: Final = ("low", "medium", "high", "xhigh", "max")
DEFAULT_MAX_ROUNDS: Final = 3
# Tokens a step's context may reach before Claude Code compacts it, passed to each session as
# CLAUDE_CODE_AUTO_COMPACT_WINDOW. Every response re-reads the whole context, so the context size, not
# the size of an edit or a test log, sets what a long step costs. Left to the model's own window (1M),
# one overnight step grew to about 965k before each compaction and re-read 473k per response on
# average; at 500k a step compacts at about half that window, at the price of compacting more often
# than the model's own window. The interactive sessions' "autoCompactWindow" setting holds the same
# value. 0 leaves the choice to Claude Code.
DEFAULT_AUTO_COMPACT_WINDOW: Final = 500000
AUTO_COMPACT_WINDOW_VARIABLE: Final = "CLAUDE_CODE_AUTO_COMPACT_WINDOW"
RUN_DIR_PARTS: Final = (".tmp", "skill-chain")
RUN_DIR_FORMAT: Final = "%Y%m%d-%H%M%S"
CLOCK_FORMAT: Final = "%H:%M:%S"
PROJECTS_DIR: Final = Path.home() / ".claude" / "projects"
VERDICT_PATTERN: Final = re.compile(r"Design conformance:\W*(PROVEN|INCOMPLETE)")
# The verify proof of a design: .tmp/<prefix><design stem>.md, the file /absorb-design's VERIFIED names.
PROOF_PREFIX: Final = "verify-proven-"
PROVEN: Final = "PROVEN"
INCOMPLETE: Final = "INCOMPLETE"
REPLY_SEPARATOR: Final = "\n\n---\n\n"
# A model name the CLI accepts: an alias (opus) or an id (claude-opus-5-5, claude-opus-5-5[1m]).
MODEL_PATTERN: Final = re.compile(r"[A-Za-z0-9._\[\]-]+")
PROGRESS_TEXT_LIMIT: Final = 300
PROGRESS_DETAIL_LIMIT: Final = 140
TAIL_LINES: Final = 25
# The one field of a tool call that says what it does, in the order it is looked for.
TOOL_DETAIL_FIELDS: Final = ("description", "file_path", "notebook_path", "path", "pattern", "skill", "name",
                             "dotted_path", "topic", "question", "query", "paths", "files", "url", "command",
                             "prompt")
SUMMARY_COLUMNS: Final = ("Name", "Models", "Turns", "Minutes", "CostUsd", "Denials", "Error")
# The numeric columns, which a PowerShell table aligns right.
_RIGHT_ALIGNED: Final = frozenset({"Turns", "Minutes", "CostUsd", "Denials"})
_ASSISTANT: Final = "assistant"
_USER: Final = "user"
_RESULT: Final = "result"
_TEXT: Final = "text"
_TOOL_USE: Final = "tool_use"
_TOOL_RESULT: Final = "tool_result"
_NO_RESULT: Final = "no-result"
_UTF8: Final = "utf-8"
# A transcript line holding an assistant message, found before the line is parsed.
_ASSISTANT_LINE: Final = '"type":"assistant"'
_PROJECT_KEY_CHARACTER: Final = re.compile(r"[^A-Za-z0-9]")
_WHITESPACE: Final = re.compile(r"\s+")
_LINE_BREAK: Final = re.compile(r"\r?\n")
_SECONDS_PER_MINUTE: Final = 60
_COST_DIGITS: Final = 2
_MINUTE_DIGITS: Final = 1
_JSON_INDENT: Final = 4
_BATCH_SAFE_FIX: Final = ("pass -Model as an alias or id of letters, digits, '.', '-', '_' and brackets, and run the "
                          "chain from a workspace path without those characters.")

Event = dict[str, object]
Show = Callable[[str, str], None]


class ChainStopped(Exception):
    """The chain ended; ``code`` is its exit code."""

    def __init__(self, code: int) -> None:
        super().__init__(f"the chain stopped with exit code {code}")
        self.code = code


@dataclass(frozen=True)
class ChainOptions:
    """What every step of one chain run uses."""

    workspace: Path
    resume: bool = False
    permission_mode: str = DEFAULT_PERMISSION_MODE
    max_budget_usd: float = 0.0
    auto_compact_window: int = DEFAULT_AUTO_COMPACT_WINDOW
    dry_run: bool = False
    quiet: bool = False


@dataclass(frozen=True)
class StepRow:
    """One step's outcome, read from its result event (``dry_run``: printed, not run)."""

    name: str
    is_error: bool
    subtype: str
    result: str
    session_id: str
    models: str
    turns: int
    minutes: float
    cost_usd: float
    denials: int
    stream_path: Path
    dry_run: bool


def number_text(value: float) -> str:
    """*value* as PowerShell prints a rounded double: no trailing zeros, no trailing point."""
    return f"{value:f}".rstrip("0").rstrip(".") or "0"


def short_text(text: str, limit: int) -> str:
    """*text* on one line, whitespace runs collapsed, cut to *limit* characters with ``...``."""
    flat = _WHITESPACE.sub(" ", text).strip()
    return flat if len(flat) <= limit else flat[:limit] + "..."


def tail_lines(text: str, count: int = TAIL_LINES) -> list[str]:
    """The last *count* lines of *text*."""
    lines = _LINE_BREAK.split(text)
    return lines[max(0, len(lines) - count):]


def _content(event: Event) -> list[Event]:
    message = event.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        return []
    return [block for block in content if isinstance(block, dict)]


def event_blocks(event: Event, kind: str) -> list[Event]:
    """The content blocks of type *kind* in one stream or transcript event's message."""
    return [block for block in _content(event) if block.get("type") == kind]


def tool_result_text(block: Event) -> str:
    """The text of a ``tool_result`` block: its string content, or its text parts one per line."""
    content = block.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(part.get(_TEXT, "")) for part in content if isinstance(part, dict))
    return ""


def tool_detail(tool_input: object) -> str:
    """The first set field of a tool call's input that says what it does: a path, a description, a pattern."""
    if not isinstance(tool_input, dict):
        return ""
    for field in TOOL_DETAIL_FIELDS:
        value = tool_input.get(field)
        if value:
            parts = value if isinstance(value, list) else [value]
            return short_text(", ".join(str(part) for part in parts), PROGRESS_DETAIL_LIMIT)
    return ""


def _assistant_lines(event: Event, clock: str) -> list[tuple[str, str]]:
    lines: list[tuple[str, str]] = []
    for block in _content(event):
        text = block.get(_TEXT)
        if block.get("type") == _TEXT and isinstance(text, str) and text.strip():
            lines.append((f"  [{clock}] {short_text(text, PROGRESS_TEXT_LIMIT)}", ""))
        elif block.get("type") == _TOOL_USE:
            lines.append((f"  [{clock}] {block.get('name')} {tool_detail(block.get('input'))}", ColorCodes.DARK_GRAY))
    return lines


def event_lines(event: Event, clock: str) -> list[tuple[str, str]]:
    """The console lines of one stream event with their colours: one per agent message, tool call, and
    refused or failed tool call, in message order; none for any other event."""
    if event.get("type") == _ASSISTANT:
        return _assistant_lines(event, clock)
    if event.get("type") != _USER:
        return []
    return [(f"  [{clock}] ! {short_text(tool_result_text(block), PROGRESS_DETAIL_LIMIT)}", ColorCodes.DARK_YELLOW)
            for block in event_blocks(event, _TOOL_RESULT) if block.get("is_error")]


def process_stream(lines: Iterable[str], stream: IO[str], show: Show | None) -> list[Event]:
    """Keep every line of a step's stream in *stream*, show each event's lines through *show* (``None``:
    quiet), and return the result events, in order. A line that is not a JSON object is kept, not shown."""
    results: list[Event] = []
    for line in lines:
        stream.write(line + "\n")
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == _RESULT:
            results.append(event)
        elif show is not None:
            clock = datetime.now().strftime(CLOCK_FORMAT)
            for text, color in event_lines(event, clock):
                show(text, color)
    return results


def _int_field(event: Event, key: str) -> int:
    value = event.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _text_field(event: Event, key: str) -> str:
    value = event.get(key)
    return value if isinstance(value, str) else ""


def step_row(label: str, result: Event, minutes: float, stream_path: Path) -> StepRow:
    """The row of a step that printed *result* as its result event."""
    usage = result.get("modelUsage")
    denials = result.get("permission_denials")
    cost = result.get("total_cost_usd")
    return StepRow(
        name=label,
        is_error=bool(result.get("is_error")),
        subtype=_text_field(result, "subtype"),
        result=_text_field(result, _RESULT),
        session_id=_text_field(result, "session_id"),
        models=", ".join(usage) if isinstance(usage, dict) else "",
        turns=_int_field(result, "num_turns"),
        minutes=minutes,
        cost_usd=round(float(cost), _COST_DIGITS) if isinstance(cost, (int, float)) else 0.0,
        denials=len(denials) if isinstance(denials, list) else 0,
        stream_path=stream_path,
        dry_run=False,
    )


def table_lines(columns: Sequence[str], rows: Sequence[Sequence[str]],
                right_aligned: frozenset[str] = frozenset()) -> list[str]:
    """*rows* as a PowerShell ``Format-Table -AutoSize`` prints them: a header, its rule, one line per row,
    each column as wide as its widest cell, the *right_aligned* columns aligned right."""
    widths = [max(len(column), *(len(row[index]) for row in rows)) for index, column in enumerate(columns)]

    def line(cells: Iterable[str]) -> str:
        return " ".join(cell.rjust(width) if column in right_aligned else cell.ljust(width)
                        for cell, width, column in zip(cells, widths, columns)).rstrip()

    return [line(columns), line("-" * len(column) for column in columns), *(line(row) for row in rows)]


def summary_table(steps: Iterable[StepRow]) -> list[str]:
    """The steps' table: name, models, turns, minutes, list cost, permission denials, error."""
    rows = [(step.name, step.models, str(step.turns), number_text(step.minutes), number_text(step.cost_usd),
             str(step.denials), str(step.is_error)) for step in steps]
    return table_lines(SUMMARY_COLUMNS, rows, _RIGHT_ALIGNED)


def step_command(claude: str, options: ChainOptions, *, session_id: str, model: str, effort: str) -> list[str]:
    """The ``claude`` argument vector of one step (its prompt goes to stdin).

    Raises:
        UsageError: for a model name, effort, permission mode or session id outside what the CLI takes, or
            an argument ``cmd.exe`` would parse when *claude* is a batch shim.
    """
    if options.permission_mode not in PERMISSION_MODES:
        raise UsageError(f"Permission mode '{options.permission_mode}' is not one of {list(PERMISSION_MODES)}. "
                         "Pass one of them.")
    if model and not MODEL_PATTERN.fullmatch(model):
        raise UsageError(f"Model '{model}' is not a model alias or id (letters, digits, '.', '-', '_' and brackets). "
                         "Pass an alias such as opus or an id such as claude-opus-5-5.")
    if effort and effort not in EFFORTS:
        raise UsageError(f"Effort '{effort}' is not one of {list(EFFORTS)}. Pass one of them.")
    command = [claude, "-p", "--output-format", "stream-json", "--verbose", "--permission-mode", options.permission_mode]
    if options.resume and session_id:
        command += ["--resume", _session_argument(session_id)]
    if options.max_budget_usd > 0:
        command += ["--max-budget-usd", number_text(options.max_budget_usd)]
    if model:
        command += ["--model", model]
    if effort:
        command += ["--effort", effort]
    require_batch_safe(command, _BATCH_SAFE_FIX)
    return command


def _session_argument(session_id: str) -> str:
    try:
        return str(uuid.UUID(session_id))
    except ValueError as exc:
        raise UsageError(f"The previous step's session id '{session_id}' is not a UUID, so it cannot be resumed. "
                         "Run the chain without -Resume.") from exc


def _decoded(raw_lines: IO[bytes]) -> Iterator[str]:
    for raw in raw_lines:
        yield raw.decode(_UTF8, errors="replace").rstrip("\r\n")


def session_replies(workspace: Path, row: StepRow, projects_dir: Path = PROJECTS_DIR) -> list[str]:
    """Every assistant text of a step's session, in order, read from its transcript.

    The result event holds only the LAST reply, and a Stop hook that refuses a reply makes the session send
    another one, so a verdict can sit in an earlier reply. Falls back to the row's result when the
    transcript is not found or holds no text.
    """
    transcript = projects_dir / _PROJECT_KEY_CHARACTER.sub("-", str(workspace)) / f"{row.session_id}.jsonl"
    if not row.session_id or not transcript.is_file():
        return [row.result]
    replies: list[str] = []
    for line in transcript.read_text(encoding=_UTF8, errors="replace").splitlines():
        if _ASSISTANT_LINE not in line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict):
            replies += [text for block in event_blocks(entry, _TEXT)
                        if isinstance(text := block.get(_TEXT), str) and text]
    return replies or [row.result]


def text_verdict(text: str) -> str:
    """The last verdict line in *text*: PROVEN, INCOMPLETE, or empty when it carries none."""
    verdicts = VERDICT_PATTERN.findall(text)
    return verdicts[-1] if verdicts else ""


def find_claude() -> str:
    """The Claude Code CLI on ``PATH``; stops the chain with exit 1 when it is not installed."""
    executable = shutil.which(CLAUDE)
    if executable is None:
        say("The claude CLI is not on PATH. Install it: npm install -g @anthropic-ai/claude-code", ColorCodes.RED)
        raise ChainStopped(EXIT_FAILED)
    return executable


class Chain:
    """One run of headless steps: the options they share, the session carried between them, and their rows."""

    def __init__(self, options: ChainOptions, claude: str) -> None:
        self.options = options
        self.claude = claude
        self.run_dir = options.workspace.joinpath(*RUN_DIR_PARTS, datetime.now().strftime(RUN_DIR_FORMAT))
        self.session_id = ""
        self.steps: list[StepRow] = []
        self._number = 0

    @classmethod
    def start(cls, options: ChainOptions) -> Chain:
        """A chain over the ``claude`` on ``PATH`` (exit 1 when there is none)."""
        return cls(options, find_claude())

    def step(self, name: str, prompt: str, *, model: str = "", effort: str = "") -> StepRow:
        """Run *prompt* as one headless step and return its row. *model* and *effort* start the session on
        that model and effort; a skill's own ``model:``/``effort:`` still applies while it runs, so they are
        for skills that declare none and leave the choice to the caller."""
        self._number += 1
        label = f"{self._number:02d}-{name}"
        window = self.options.auto_compact_window
        compact_note = f" [compacts at {window} tokens]" if window > 0 else ""
        model_note = f" ({model}{f', {effort}' if effort else ''})" if model else ""
        say("")
        say(f"=== step {label}{model_note}{compact_note} ===", ColorCodes.CYAN)
        say(prompt)
        stream_path = self.run_dir / f"{label}.stream.jsonl"
        if self.options.dry_run:
            return StepRow(label, False, "", "", "", "", 0, 0.0, 0.0, 0, stream_path, dry_run=True)
        command = step_command(self.claude, self.options, session_id=self.session_id, model=model, effort=effort)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        error_path = self.run_dir / f"{label}.stderr.txt"
        started = time.monotonic()
        results = self._launch(command, prompt, stream_path, error_path)
        if not results:
            say(f"Step {label} printed no result event (see {stream_path} and {error_path}).", ColorCodes.RED)
            return StepRow(label, True, _NO_RESULT, "", "", "", 0, 0.0, 0.0, 0, stream_path, dry_run=False)
        result = results[-1]
        (self.run_dir / f"{label}.json").write_text(json.dumps(result, indent=_JSON_INDENT, ensure_ascii=False),
                                                    encoding=_UTF8)
        minutes = round((time.monotonic() - started) / _SECONDS_PER_MINUTE, _MINUTE_DIGITS)
        row = step_row(label, result, minutes, stream_path)
        if row.session_id:
            self.session_id = row.session_id
        self.steps.append(row)
        outcome = f"ERROR ({row.subtype})" if row.is_error else "done"
        say(f"{label}: {outcome}; models {row.models}; {row.turns} turns; {number_text(minutes)} min; list cost "
            f"{number_text(row.cost_usd)} USD; {row.denials} permission denial(s); session {row.session_id}",
            ColorCodes.RED if row.is_error else ColorCodes.GREEN)
        return row

    def _launch(self, command: list[str], prompt: str, stream_path: Path, error_path: Path) -> list[Event]:
        """Run *command* in the workspace with *prompt* on stdin; keep its stream and stderr; the result events."""
        environment = dict(os.environ)
        if self.options.auto_compact_window > 0:
            environment[AUTO_COMPACT_WINDOW_VARIABLE] = str(self.options.auto_compact_window)
        show = None if self.options.quiet else say
        with stream_path.open("w", encoding=_UTF8, newline="") as stream, error_path.open("wb") as errors, \
                subprocess.Popen(command, cwd=self.options.workspace, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=errors, env=environment) as process:
            if process.stdin is None or process.stdout is None:
                raise OSError(f"{command[0]} was started without the pipes this chain reads; expected stdin and "
                              "stdout pipes.")
            process.stdin.write(prompt.encode(_UTF8))
            process.stdin.close()
            return process_stream(_decoded(process.stdout), stream, show)

    def summary(self) -> None:
        """Print every finished step as a table, with the run's log folder; nothing before the first step."""
        if not self.steps:
            return
        say("")
        say(f"=== chain summary (logs: {self.run_dir}) ===", ColorCodes.CYAN)
        for line in ["", *summary_table(self.steps), "", ""]:
            say(line)

    def stop(self, code: int, message: str, row: StepRow | None = None) -> NoReturn:
        """Print why the chain stops, the step's last reply and how to continue its session, then stop with
        *code*: 1 for an error or a failed check, 2 for a decision only Jon can make."""
        say("")
        say(message, ColorCodes.YELLOW if code == EXIT_NEEDS_JON else ColorCodes.RED)
        if row is not None and row.result:
            say("The step's last reply ends:")
            for line in tail_lines(row.result):
                say(f"  {line}")
        if row is not None and row.session_id:
            say(f"Continue that session interactively: claude --resume {row.session_id}")
        self.summary()
        raise ChainStopped(code)

    def complete(self) -> NoReturn:
        """Print the summary and stop with 0."""
        self.summary()
        raise ChainStopped(EXIT_DONE)

    def replies(self, row: StepRow) -> list[str]:
        """Every assistant text of *row*'s session (``session_replies``)."""
        return session_replies(self.options.workspace, row)

    def verify_proof_path(self, design: Path) -> Path:
        """Where the verify session's replies are kept once they end PROVEN, for /absorb-design's VERIFIED
        input. The path depends only on the design, so a later run that starts at absorb finds the proof an
        earlier run wrote."""
        return self.options.workspace / ".tmp" / f"{PROOF_PREFIX}{design.stem}.md"

    def verify_design(self, prompt: str, design: Path, on_incomplete: Callable[[Path], None],
                      max_rounds: int = DEFAULT_MAX_ROUNDS) -> None:
        """Run /verify-implementation until it replies PROVEN, then save its replies to the design's proof
        file. On INCOMPLETE its replies are saved to a report and *on_incomplete* runs with that path (the
        step that implements again) before the next round; after *max_rounds* the chain stops with 1. A
        reply with neither verdict stops it with 2."""
        proof = self.verify_proof_path(design)
        if proof.exists():
            proof.unlink()
        for round_number in range(1, max_rounds + 1):
            row = self.step("verify", prompt)
            if row.dry_run:
                return
            if row.is_error:
                self.stop(EXIT_FAILED, f"/verify-implementation ended in error ({row.subtype}).", row)
            replies = self.replies(row)
            verdict = text_verdict("\n".join(replies))
            if verdict == PROVEN:
                proof.parent.mkdir(parents=True, exist_ok=True)
                proof.write_text(REPLY_SEPARATOR.join(replies), encoding=_UTF8)
                say(f"Verify: PROVEN (proof for absorb: {proof}).", ColorCodes.GREEN)
                return
            if verdict != INCOMPLETE:
                self.stop(EXIT_NEEDS_JON, "/verify-implementation replied with neither PROVEN nor INCOMPLETE; read "
                                          "its reply.", row)
            if round_number == max_rounds:
                self.stop(EXIT_FAILED, f"The design is still INCOMPLETE after {max_rounds} verify round(s); it is "
                                       "not absorbed.", row)
            report = self.run_dir / f"verify-round-{round_number}.md"
            report.write_text(REPLY_SEPARATOR.join(replies), encoding=_UTF8)
            say(f"Verify round {round_number}: INCOMPLETE (report: {report}). Implementing again.", ColorCodes.YELLOW)
            on_incomplete(report)

    def absorb_design(self, design: Path, *, keep_source: bool) -> None:
        """Run /absorb-design with VERIFIED set to the design's proof file, which a PROVEN verify wrote (in
        this run or an earlier one). Without that file the chain stops with 1 before absorb runs: absorb
        deletes the design only on that proof. Without *keep_source* the design must be gone afterwards; when
        it is not, absorb stopped at one of its questions and the chain stops with 2."""
        proof = self.verify_proof_path(design)
        if not self.options.dry_run:
            verdict = text_verdict(proof.read_text(encoding=_UTF8)) if proof.is_file() else ""
            if verdict != PROVEN:
                self.stop(EXIT_FAILED, f"No PROVEN verify reply for this design at {proof}, so absorb would not "
                                       "delete it. Rerun with -StartAt verify.")
        keep = "\nKEEP SOURCE: true" if keep_source else ""
        row = self.step("absorb", f"/absorb-design\nDOCUMENT: {design}\nVERIFIED: {proof}{keep}")
        if row.dry_run:
            return
        if row.is_error:
            self.stop(EXIT_FAILED, f"/absorb-design ended in error ({row.subtype}).", row)
        if not keep_source and design.exists():
            self.stop(EXIT_NEEDS_JON, "/absorb-design finished but the design still exists, so it stopped at a "
                                      "question; read its reply.", row)


def add_chain_arguments(parser: argparse.ArgumentParser, *, resume: bool) -> None:
    """The options every chain wrapper shares (``--resume`` only where the chain may carry one session)."""
    if resume:
        parser.add_argument("--resume", action="store_true",
                            help="Carry one session through every step instead of a fresh session per step.")
    parser.add_argument("--permission-mode", choices=PERMISSION_MODES, default=DEFAULT_PERMISSION_MODE,
                        help="The permission mode of every step. Default: auto. The guards run in every mode.")
    parser.add_argument("--max-budget-usd", type=float, default=0.0,
                        help="Stop a step that passes this list-price cost. Default: no cap.")
    parser.add_argument("--dry-run", action="store_true", help="Print the steps that would run, and run none.")
    parser.add_argument("--quiet", action="store_true", help="Show only each step's prompt and summary line.")


def chain_options(args: argparse.Namespace, workspace: Path, *, resume: bool) -> ChainOptions:
    """The chain options of a wrapper's parsed ``add_chain_arguments`` (*resume*: its ``--resume``, if any)."""
    return ChainOptions(workspace=workspace, resume=resume,
                        permission_mode=args.permission_mode, max_budget_usd=args.max_budget_usd,
                        dry_run=args.dry_run, quiet=args.quiet)


def chain_exit_code(body: Callable[[], NoReturn]) -> int:
    """Run a chain *body*, which ends with ``Chain.complete`` or ``Chain.stop``; its exit code."""
    try:
        body()
    except ChainStopped as stopped:
        return stopped.code
    raise RuntimeError("The chain body returned without stopping. Expected it to end with Chain.complete() or "
                       "Chain.stop().")


_SESSION: Final = "2620580a-d5bd-4133-876c-e1601a30633b"
_CLOCK: Final = re.compile(r"\[\d\d:\d\d:\d\d\]")
# Events in the shape ``claude -p --output-format stream-json --verbose`` prints them (trimmed).
_STREAM: Final = (
    '{"type":"system","subtype":"init","cwd":"D:\\\\datrix","session_id":"' + _SESSION + '"}',
    '{"type":"assistant","message":{"model":"claude-sonnet-5-5","role":"assistant","content":['
    '{"type":"thinking","thinking":""},{"type":"text","text":"Reading   the\\nledger."},'
    '{"type":"tool_use","id":"toolu_1","name":"Read","input":{"file_path":"D:\\\\datrix\\\\a.md"}}]}}',
    '{"type":"user","message":{"role":"user","content":[{"tool_use_id":"toolu_1","type":"tool_result",'
    '"content":[{"type":"text","text":"refused:"},{"type":"text","text":"read it first"}],"is_error":true}]}}',
    '{"type":"user","message":{"role":"user","content":[{"tool_use_id":"toolu_2","type":"tool_result",'
    '"content":"File created"}]}}',
    "not json",
    '{"type":"rate_limit_event","rate_limit_info":{"status":"allowed"}}',
    '{"type":"result","subtype":"success","is_error":false,"num_turns":13,"result":"Done.\\nDesign conformance: '
    'PROVEN","session_id":"' + _SESSION + '","total_cost_usd":0.37170209999999987,'
    '"modelUsage":{"claude-sonnet-5-5":{},"claude-haiku-5-5":{}},"permission_denials":[{"tool_name":"Bash"}]}',
)


def _check_the_prompt_reaches_stdin_never_an_argument() -> None:
    options = ChainOptions(workspace=Path("w"), resume=True, permission_mode="dontAsk", max_budget_usd=2.5)
    command = step_command("C:/bin/claude.cmd", options, session_id=_SESSION.upper(), model="claude-opus-5-5[1m]",
                           effort="high")
    assert command == ["C:/bin/claude.cmd", "-p", "--output-format", "stream-json", "--verbose", "--permission-mode",
                       "dontAsk", "--resume", _SESSION, "--max-budget-usd", "2.5", "--model", "claude-opus-5-5[1m]",
                       "--effort", "high"], command
    fresh = step_command("claude", ChainOptions(workspace=Path("w")), session_id=_SESSION, model="", effort="")
    assert fresh == ["claude", "-p", "--output-format", "stream-json", "--verbose", "--permission-mode", "auto"], fresh


def _check_unsafe_step_arguments_are_refused() -> None:
    resuming = ChainOptions(workspace=Path("w"), resume=True)
    cases: tuple[tuple[ChainOptions, str, str, str, str], ...] = (
        (resuming, _SESSION, "opus&calc", "", "is not a model alias or id"),
        (resuming, _SESSION, "opus\nrest", "", "is not a model alias or id"),
        (resuming, _SESSION, "", "extreme", "is not one of"),
        (resuming, "abc&calc", "", "", "is not a UUID"),
        (ChainOptions(workspace=Path("w"), permission_mode="plan"), "", "", "", "Permission mode 'plan'"),
    )
    for options, session, model, effort, fragment in cases:
        expect_usage_error(lambda: step_command("claude.cmd", options, session_id=session, model=model,
                                                effort=effort), fragment)


def _check_the_stream_is_kept_and_its_events_shown() -> None:
    shown: list[tuple[str, str]] = []
    kept = io.StringIO()
    results = process_stream(_STREAM, kept, lambda text, color: shown.append((_CLOCK.sub("[t]", text), color)))
    assert kept.getvalue() == "".join(line + "\n" for line in _STREAM), kept.getvalue()
    assert shown == [("  [t] Reading the ledger.", ""), ("  [t] Read D:\\datrix\\a.md", ColorCodes.DARK_GRAY),
                     ("  [t] ! refused: read it first", ColorCodes.DARK_YELLOW)], shown
    assert len(results) == 1, results
    row = step_row("03-verify", results[0], 1.0, Path("s.jsonl"))
    assert (row.is_error, row.subtype, row.session_id, row.models, row.turns, row.cost_usd, row.denials) == (
        False, "success", _SESSION, "claude-sonnet-5-5, claude-haiku-5-5", 13, 0.37, 1), row
    quiet: list[Event] = process_stream(_STREAM, io.StringIO(), None)
    assert quiet == results, quiet
    assert summary_table([row]) == [
        "Name      Models                              Turns Minutes CostUsd Denials Error",
        "----      ------                              ----- ------- ------- ------- -----",
        "03-verify claude-sonnet-5-5, claude-haiku-5-5    13       1    0.37       1 False",
    ], summary_table([row])


def _check_tool_details_and_short_text() -> None:
    assert tool_detail({"command": "git status", "description": "Show status"}) == "Show status"
    assert tool_detail({"paths": ["a.py", "b.py"]}) == "a.py, b.py"
    assert tool_detail({"description": "", "pattern": "x"}) == "x"
    assert tool_detail({"other": "x"}) == "" and tool_detail("text") == ""
    assert short_text("a" * 5, 4) == "aaaa..." and short_text(" a \n\t b ", 9) == "a b"
    assert tail_lines("1\r\n2\n3", 2) == ["2", "3"] and tail_lines("one", 25) == ["one"]
    assert number_text(45.0) == "45" and number_text(0.37) == "0.37" and number_text(0.0) == "0"


def _check_session_replies_read_every_reply_of_the_transcript() -> None:
    with TemporaryDirectory() as raw:
        projects = Path(raw)
        workspace = Path("D:/datrix")
        row = StepRow("02-verify", False, "success", "last reply only", _SESSION, "", 1, 0.0, 0.0, 0, Path("s"), False)
        assert session_replies(workspace, row, projects) == ["last reply only"]
        transcript = projects / "D--datrix" / f"{_SESSION}.jsonl"
        write_files(transcript.parent, {transcript.name: "\n".join((
            '{"type":"user","message":{"content":[{"type":"text","text":"the prompt"}]}}',
            '{"type":"assistant","message":{"content":[{"type":"text","text":"Design conformance: **INCOMPLETE**"}]}}',
            '{"type":"assistant","message":{"content":[{"type":"text","text":"Design conformance: PROVEN"}]}}',
            '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Read","input":{}}]}}',
            '{"type":"assistant","message":{"content":[{"type":"text","text":"Stopping."}]}}',
        ))})
        replies = session_replies(workspace, row, projects)
    assert replies == ["Design conformance: **INCOMPLETE**", "Design conformance: PROVEN", "Stopping."], replies
    assert text_verdict("\n".join(replies)) == PROVEN
    assert text_verdict("no verdict") == "" and text_verdict("Design conformance: INCOMPLETE") == INCOMPLETE


def _check_absorb_needs_a_proven_verify_reply() -> None:
    with TemporaryDirectory() as raw:
        workspace = Path(raw)
        design = workspace / "design" / "099-x.md"
        chain = Chain(ChainOptions(workspace=workspace), CLAUDE)
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            try:
                chain.absorb_design(design, keep_source=False)
            except ChainStopped as stopped:
                code = stopped.code
            else:
                raise AssertionError("absorb ran with no proof file")
        assert code == EXIT_FAILED, code
        assert f"No PROVEN verify reply for this design at {workspace / '.tmp' / 'verify-proven-099-x.md'}" in \
            printed.getvalue(), printed.getvalue()
        assert not chain.run_dir.exists(), "a refused absorb launched a step"


def _check_a_dry_run_prints_the_steps_and_runs_none() -> None:
    with TemporaryDirectory() as raw:
        workspace = Path(raw)
        design = workspace / "d.md"
        chain = Chain(ChainOptions(workspace=workspace, dry_run=True, auto_compact_window=0), CLAUDE)
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            chain.verify_design("/verify-implementation\nDESIGN: d", design, lambda report: None)
            chain.absorb_design(design, keep_source=True)
            row = chain.step("fix", "/implement-finding", model="claude-opus-5-5", effort="high")
        assert row.dry_run and not chain.steps and not chain.run_dir.exists(), (row, chain.steps)
    proof = workspace / ".tmp" / "verify-proven-d.md"
    assert printed.getvalue().splitlines() == [
        "", "=== step 01-verify ===", "/verify-implementation", "DESIGN: d",
        "", "=== step 02-absorb ===", "/absorb-design", f"DOCUMENT: {design}", f"VERIFIED: {proof}", "KEEP SOURCE: true",
        "", "=== step 03-fix (claude-opus-5-5, high) ===", "/implement-finding",
    ], printed.getvalue()


#: The chain's checks, run by the ``--self-test`` of every module that runs a chain.
CHAIN_CHECKS: Final = (
    _check_the_prompt_reaches_stdin_never_an_argument,
    _check_unsafe_step_arguments_are_refused,
    _check_the_stream_is_kept_and_its_events_shown,
    _check_tool_details_and_short_text,
    _check_session_replies_read_every_reply_of_the_transcript,
    _check_absorb_needs_a_proven_verify_reply,
    _check_a_dry_run_prints_the_steps_and_runs_none,
)
