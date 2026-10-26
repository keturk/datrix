"""Run one /implement-finding session per findings file of the inbox, in turn. A session checks its finding
against the code and fixes the defect when the code has it; this module deletes the finding on a passing proof.

``scripts/skill/implement-finding.ps1`` (and its ``.sh`` twin) runs this module, whose sessions are steps of
``datrix_scripts.skill.chain``. For each selected finding, in name order, one headless /implement-finding
session on ``--model`` ends with one line:

  Finding fix: ALREADY RESOLVED   the code no longer has the defect; nothing was changed
  Finding fix: DONE               fixed, with a tagged test and targeted test runs
  Finding fix: BLOCKED B<n>       stopped with a B1-B4 proof; the finding stays for Jon

The session never deletes the finding; this module does, through ``finding_inbox.close_finding`` in this
process, not on a model's word: never while another findings file names it, and after DONE only when the
session's last foreground test.ps1 or ``*-gate.ps1`` run passed (read from the step's stream log). Each
finding is closed before the next one starts. ``finding_inbox.select_findings`` selects the findings (the inbox's subfolders in turn, or the one given with ``--dir``), unless
``--finding`` names them.

Exit codes: 0 every selected finding is deleted (or a passing self-test); 1 a step ended in error, replied
with no outcome line, a finding was left in place, or the findings could not be selected; 2 no failure, but
at least one session stopped for a decision only Jon can make, or a command line this module cannot read.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Final, NoReturn

from datrix_scripts.claude_cli import CLAUDE
from datrix_scripts.gate_harness import write_files
from datrix_scripts.logging_utils import ColorCodes, say
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.skill.chain import (
    CHAIN_CHECKS,
    EFFORTS,
    EXIT_DONE,
    EXIT_FAILED,
    EXIT_NEEDS_JON,
    Chain,
    ChainOptions,
    ChainStopped,
    add_chain_arguments,
    chain_exit_code,
    chain_options,
    table_lines,
)
from datrix_scripts.skill.common import AssistError
from datrix_scripts.skill.finding_inbox import (
    DEFAULT_COUNT,
    EXIT_DELETED,
    EXIT_KEPT,
    EXIT_UNUSABLE,
    close_finding,
    inbox_dir,
)
from datrix_scripts.skill.finding_inbox import (
    select_findings as select_inbox,
)
from datrix_scripts.test.wrappers import SKILL_SCRIPTS_DIR, module_main, run_self_test

MODULE: Final = "datrix_scripts.skill.implement_finding"
WRAPPER: Final = "implement-finding"
DEFAULT_MODEL: Final = "claude-opus-5-5"
DEFAULT_EFFORT: Final = "high"
OUTCOME_PATTERN: Final = re.compile(r"Finding fix:[ \t*_`]*(DONE|ALREADY RESOLVED|BLOCKED\W*(B[1-4]))")
ALREADY_RESOLVED: Final = "ALREADY RESOLVED"
FAILED_PREFIX: Final = "FAILED"
NEEDS_JON_PREFIX: Final = "NEEDS JON"
DRY_RUN_OUTCOME: Final = "dry run"
ALREADY_GONE: Final = "already gone"
FINDINGS_COLUMNS: Final = ("Finding", "Outcome")


def select_findings(workspace: Path, findings: Sequence[str], count: int, directory: str) -> list[Path]:
    """The findings to work: *findings* when given (each must exist), else the first *count* of the inbox;
    stops with 1 when a named finding is missing or the inbox cannot be read."""
    if findings:
        for path in findings:
            if not Path(path).is_file():
                say(f"Finding file not found: {path}. Pass existing files to -Finding.", ColorCodes.RED)
                raise ChainStopped(EXIT_FAILED)
        return [Path(path).resolve() for path in findings]
    try:
        return select_inbox(workspace, directory, count)
    except AssistError as exc:
        say(f"  ERROR: {exc}")
        say(f"Selecting the findings failed (exit {EXIT_UNUSABLE}).", ColorCodes.RED)
        raise ChainStopped(EXIT_FAILED) from exc


def finding_outcome(text: str) -> tuple[str, str]:
    """The last ``Finding fix:`` line of *text*: its outcome and, for BLOCKED, its blocker code; two empty
    strings when it carries none."""
    outcomes = OUTCOME_PATTERN.findall(text)
    return outcomes[-1] if outcomes else ("", "")


def close(finding: Path, session_log: Path | None = None, inbox: Path | None = None) -> int:
    """Delete *finding* when nothing names it (in its folder, or anywhere in *inbox* when it lies there) and,
    given *session_log*, its last test run passed; prints why it was kept; the close exit code."""
    try:
        text, code = close_finding(finding.resolve(), session_log.resolve() if session_log else None, inbox)
    except AssistError as exc:
        text, code = f"ERROR: {exc}", EXIT_UNUSABLE
    for line in text.splitlines():
        say(f"  {line}")
    return code


def resolve_finding(chain: Chain, finding: Path, model: str, effort: str) -> str:
    """One session checks and fixes *finding*; this module closes it. Its outcome."""
    row = chain.step("fix", f"/implement-finding\nFINDING: {finding}\nCLOSE: script", model=model, effort=effort)
    if row.dry_run:
        return DRY_RUN_OUTCOME
    resume = f"claude --resume {row.session_id}"
    if row.is_error:
        return f"{FAILED_PREFIX}: the session ended in error ({row.subtype}); {resume}"
    if not finding.exists():
        return f"{FAILED_PREFIX}: the session deleted the finding itself, so its tests were not checked; {resume}"
    outcome, blocker = finding_outcome("\n".join(chain.replies(row)))
    if not outcome:
        return f"{FAILED_PREFIX}: the session replied with no 'Finding fix:' line; {resume}"
    if blocker:
        return f"{NEEDS_JON_PREFIX}: stopped {blocker}; {resume}"
    if outcome == ALREADY_RESOLVED:
        if close(finding, inbox=inbox_dir(WORKSPACE_DIR)) == EXIT_DELETED:
            return "deleted (no longer an issue)"
        return f"{FAILED_PREFIX}: already resolved, but not deletable (see above); {resume}"
    if close(finding, row.stream_path, inbox_dir(WORKSPACE_DIR)) == EXIT_DELETED:
        return "fixed and deleted"
    return f"{FAILED_PREFIX}: fixed, but left in place (see above); {resume}"


def run_findings(chain: Chain, selected: Sequence[Path], *, model: str, effort: str) -> NoReturn:
    """Resolve each selected finding in turn, print the outcomes, and stop with 1 on any failure, else 2 when a
    session needs Jon, else 0."""
    outcomes: list[tuple[str, str]] = []
    for number, finding in enumerate(selected, start=1):
        say("")
        say(f"##### finding {number} of {len(selected)}: {finding.name}", ColorCodes.MAGENTA)
        if not chain.options.dry_run and not finding.exists():
            outcomes.append((finding.name, ALREADY_GONE))
            continue
        outcomes.append((finding.name, resolve_finding(chain, finding, model, effort)))
    chain.summary()
    say("=== findings ===", ColorCodes.CYAN)
    for line in ["", *table_lines(FINDINGS_COLUMNS, outcomes), "", ""]:
        say(line)
    if any(outcome.startswith(FAILED_PREFIX) for _, outcome in outcomes):
        raise ChainStopped(EXIT_FAILED)
    if any(outcome.startswith(NEEDS_JON_PREFIX) for _, outcome in outcomes):
        raise ChainStopped(EXIT_NEEDS_JON)
    raise ChainStopped(EXIT_DONE)


def build_parser() -> argparse.ArgumentParser:
    """The options of ``skill/implement-finding.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        description="Work through the first findings files one at a time, one fresh session per finding.",
        allow_abbrev=False,
    )
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT,
                        help="How many findings files to take, first by name. Default: 10.")
    parser.add_argument("--finding", action="append", default=[],
                        help="A findings file to work, in place of the first --count of the inbox (repeat for each).")
    parser.add_argument("--dir", default="",
                        help="Work only this folder: absolute, or relative to <workspace>/findings. "
                             "Default: the subfolders of <workspace>/findings in turn, then its own files.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="The model of each session. Default: claude-opus-5-5.")
    parser.add_argument("--effort", choices=EFFORTS, default=DEFAULT_EFFORT,
                        help="The effort of each session. Default: high.")
    add_chain_arguments(parser, resume=False)
    parser.add_argument("--self-test", action="store_true",
                        help="Run only the chain checks, the selection, outcome and dry-run checks and the wrapper seam checks.")
    parser.set_defaults(debug=False)
    return parser


def _check_the_outcome_is_the_last_finding_fix_line() -> None:
    cases = (
        ("Finding fix: **DONE**", ("DONE", "")),
        ("Finding fix: DONE\nlater\nFinding fix: `ALREADY RESOLVED`", (ALREADY_RESOLVED, "")),
        ("Finding fix: BLOCKED -- B3 (USER_FORBADE)", ("BLOCKED -- B3", "B3")),
        ("Finding fix: BLOCKED B7", ("", "")),
        ("finding fix: DONE", ("", "")),
    )
    for text, expected in cases:
        assert finding_outcome(text) == expected, (text, finding_outcome(text))


def _check_findings_are_selected_and_closed_in_process() -> None:
    with TemporaryDirectory() as raw:
        workspace = Path(raw)
        inbox = workspace / "findings"
        write_files(inbox, {"b.md": "b\n", "a.md": "a\n", "c.md": "names a\n", "notes.txt": "x\n"})
        assert select_findings(workspace, [], 2, "") == [inbox / "a.md", inbox / "b.md"]
        assert select_findings(workspace, [str(inbox / "c.md")], 2, "") == [(inbox / "c.md").resolve()]
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            assert chain_exit_code(lambda: select_findings(workspace, [str(inbox / "absent.md")], 1, "")) == EXIT_FAILED
            assert chain_exit_code(lambda: select_findings(workspace, [], 0, "")) == EXIT_FAILED
            assert close(inbox / "a.md") == EXIT_KEPT, "c.md names a.md, so a.md is kept"
            assert close(inbox / "b.md") == EXIT_DELETED and not (inbox / "b.md").exists()
            assert close(inbox / "c.md", inbox / "absent.jsonl") == EXIT_UNUSABLE
        lines = printed.getvalue().splitlines()
    assert lines == [
        f"Finding file not found: {inbox / 'absent.md'}. Pass existing files to -Finding.",
        "  ERROR: --count must be at least 1 (got 0).",
        "Selecting the findings failed (exit 1).",
        f"  Not deleted: {(inbox / 'a.md').resolve()}",
        "    - c.md still names it: remove that pointer first",
        f"  Deleted: {(inbox / 'b.md').resolve()}",
        f"  ERROR: Session log '{(inbox / 'absent.jsonl').resolve()}' does not exist. Pass the step's .stream.jsonl.",
    ], lines


def _check_the_subfolders_are_worked_in_turn_or_only_the_one_given() -> None:
    with TemporaryDirectory() as raw:
        workspace = Path(raw)
        inbox = workspace / "findings"
        write_files(inbox, {"z-loose.md": "z\n", "docs/d1.md": "d1\n", "azure/a2.md": "a2 names d1\n",
                            "azure/a1.md": "a1\n", "python/p1.md": "p1\n", "extra/e1.md": "e1\n"})
        names = [path.relative_to(inbox).as_posix() for path in select_findings(workspace, [], 10, "")]
        assert names == ["python/p1.md", "azure/a1.md", "azure/a2.md", "docs/d1.md", "extra/e1.md", "z-loose.md"], names
        two = [path.relative_to(inbox).as_posix() for path in select_findings(workspace, [], 2, "")]
        assert two == ["python/p1.md", "azure/a1.md"], two
        assert select_findings(workspace, [], 10, "azure") == [inbox / "azure" / "a1.md", inbox / "azure" / "a2.md"]
        given = select_findings(workspace, [], 10, str(inbox / "docs"))
        assert [path.name for path in given] == ["d1.md"], given
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            assert chain_exit_code(lambda: select_findings(workspace, [], 1, "absent")) == EXIT_FAILED
            assert close(inbox / "docs" / "d1.md", inbox=inbox) == EXIT_KEPT, "azure/a2.md names d1.md"
            assert close(inbox / "azure" / "a2.md", inbox=inbox) == EXIT_DELETED


def _check_a_dry_run_prints_every_session() -> None:
    with TemporaryDirectory() as raw:
        workspace = Path(raw)
        selected = [workspace / "a.md", workspace / "b.md"]
        chain = Chain(ChainOptions(workspace=workspace, dry_run=True, auto_compact_window=0), CLAUDE)
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            code = chain_exit_code(lambda: run_findings(chain, selected, model=DEFAULT_MODEL, effort=DEFAULT_EFFORT))
    assert code == EXIT_DONE, code
    assert printed.getvalue().splitlines() == [
        "", "##### finding 1 of 2: a.md",
        "", "=== step 01-fix (claude-opus-5-5, high) ===", "/implement-finding", f"FINDING: {selected[0]}", "CLOSE: script",
        "", "##### finding 2 of 2: b.md",
        "", "=== step 02-fix (claude-opus-5-5, high) ===", "/implement-finding", f"FINDING: {selected[1]}", "CLOSE: script",
        "=== findings ===", "", "Finding Outcome", "------- -------", "a.md    dry run", "b.md    dry run", "", "",
    ], printed.getvalue()


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        checks = [*CHAIN_CHECKS, _check_the_outcome_is_the_last_finding_fix_line,
                  _check_findings_are_selected_and_closed_in_process,
                  _check_the_subfolders_are_worked_in_turn_or_only_the_one_given,
                  _check_a_dry_run_prints_every_session]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=SKILL_SCRIPTS_DIR)

    def body() -> NoReturn:
        selected = select_findings(WORKSPACE_DIR, args.finding, args.count, args.dir)
        if not selected:
            say("No findings files to work on.")
            raise ChainStopped(EXIT_DONE)
        say(f"Findings ({len(selected)}):")
        for finding in selected:
            say(f"  {finding}")
        chain = Chain.start(chain_options(args, WORKSPACE_DIR, resume=False))
        run_findings(chain, selected, model=args.model, effort=args.effort)

    return chain_exit_code(body)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
