"""Run one /implement-finding session per findings file of the inbox, a batch of sessions side by side. The
session checks its finding against the code and repairs what is wrong there; this module deletes the finding
after a passing proof.

``scripts/skill/implement-finding.ps1`` (and its ``.sh`` twin) runs this module, whose sessions are steps of
``datrix_scripts.skill.chain``. The selected findings are worked in batches of ``BATCH_SIZE`` (``batches``: the
inbox folders taken in turn, so the sessions of a batch work different areas where the selection allows). The
fix sessions of a batch run side by side; each headless /implement-finding session on ``--model`` ends with one
line:

  Finding fix: ALREADY RESOLVED   the code no longer has the defect; nothing was changed
  Finding fix: DONE               fixed, with a tagged test and targeted test runs
  Finding fix: UPDATED            fixed what needed no growth, rewrote the finding with what the rest needs
  Finding fix: BLOCKED B<n>       stopped with a B1-B4 proof; the finding stays for Jon

The session never deletes the finding; this module does, through ``finding_inbox.close_finding`` in this
process, not on a model's word: never while another findings file names it, and after DONE only when the
tests related to what the session wrote pass. After UPDATED the finding stays, the same related tests run,
and the finding file must differ from what the session was given and carry a ``- **Needs Jon:** <text>``
line, which keeps later selections from taking it until Jon deletes the line.

This module runs those related tests itself (``skill.related_tests``: the tests the session wrote, and the
other tests that name the code names it changed), and only once every fix session of the batch has ended
(``prove_batch``): while sessions edit side by side, a run would judge one session's change by another's
half-made edits. On the still tree the sessions are proved in turn; while a session's related tests fail it is
resumed with the failures, as often as it takes: only a pass or a B1-B4 blocker the session proves ends the
repairs. Only the session being repaired edits then, but its repair can break the related tests of a session
proved before it, so the sessions are proved again until a sweep needs no repair.
When the session wrote no package source or test (the scripts tree hosts no test suite), its last foreground
test.ps1 or ``*-gate.ps1`` run must have passed (read from the step's stream log). Every finding of a batch is
closed before the next batch starts. ``finding_inbox.select_findings`` selects the findings (the inbox's
subfolders in turn, or the one given with ``--dir``), unless ``--finding`` names them.

Exit codes: 0 every selected finding is deleted (or a passing self-test); 1 a step ended in error, replied
with no outcome line, a finding was left in place, or the findings could not be selected; 2 no failure, but
at least one session stopped for a decision only Jon can make or rewrote its finding to say what it needs, or
a command line this module cannot read.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import os
import re
import sys
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
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
    StepRow,
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
    UNLIMITED,
    awaits_jon,
    close_finding,
    inbox_dir,
)
from datrix_scripts.skill.finding_inbox import (
    select_findings as select_inbox,
)
from datrix_scripts.skill.related_tests import repair_prompt, verify_related_fresh
from datrix_scripts.skill.related_tests_checks import (
    CHECKS as RELATED_CHECKS,
)
from datrix_scripts.skill.related_tests_checks import tool_use_line, write_stub_harness, write_workspace
from datrix_scripts.test.wrappers import SKILL_SCRIPTS_DIR, module_main, run_self_test

MODULE: Final = "datrix_scripts.skill.implement_finding"
WRAPPER: Final = "implement-finding"
DEFAULT_MODEL: Final = "claude-sonnet-5-5"
DEFAULT_EFFORT: Final = "medium"
# How many fix sessions run side by side. Each one also runs its own targeted test.ps1 runs, and those share the
# machine's cores and the venv's install-check lock with the other sessions' runs.
BATCH_SIZE: Final = 4
OUTCOME_PATTERN: Final = re.compile(r"Finding fix:[ \t*_`]*(DONE|UPDATED|ALREADY RESOLVED|BLOCKED\W*(B[1-4]))")
ALREADY_RESOLVED: Final = "ALREADY RESOLVED"
UPDATED: Final = "UPDATED"
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


def finding_count(everything: bool, count: int | None, findings: Sequence[str]) -> int:
    """How many findings to take: every one with *everything*, else *count* (default ``DEFAULT_COUNT``); stops
    with 1 when *everything* is combined with a count or with named findings, which it would silently override."""
    if everything and (count is not None or findings):
        say("-All works every findings file of the folder; it cannot be combined with -Count or -Finding.",
            ColorCodes.RED)
        raise ChainStopped(EXIT_FAILED)
    if everything:
        return UNLIMITED
    return DEFAULT_COUNT if count is None else count


def batches(selected: Sequence[Path], size: int = BATCH_SIZE) -> list[list[Path]]:
    """*selected* in batches of *size* whose fix sessions run side by side. The folders are taken in turn (the
    first finding of each folder, in the order they first appear, then the second of each, ...), so the sessions
    of a batch work different areas, and so mostly different packages, wherever the selection allows."""
    folders: dict[Path, list[Path]] = {}
    for finding in selected:
        folders.setdefault(finding.parent, []).append(finding)
    queues = list(folders.values())
    turned = [queue[depth] for depth in range(max(map(len, queues), default=0))
              for queue in queues if depth < len(queue)]
    return [turned[start:start + size] for start in range(0, len(turned), size)]


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


def updated_verdict(finding: Path, given: bytes) -> str:
    """The outcome of a session that replied UPDATED: the finding must differ from *given* (what the session was
    handed) and carry the ``Needs Jon`` line that keeps later selections from taking it."""
    if finding.read_bytes() == given:
        return f"{FAILED_PREFIX}: replied UPDATED, but the finding is unchanged"
    if not awaits_jon(finding):
        return f"{FAILED_PREFIX}: replied UPDATED, but the finding has no '- **Needs Jon:**' line"
    return f"{NEEDS_JON_PREFIX}: finding updated with what it needs"


@dataclass(frozen=True)
class RelatedProof:
    """The related-suites proof of one fixed finding: *message* is empty when every related run passed;
    *checked* is whether any related run was planned (when none was, the session's own last run is the proof);
    *repairs* is how many repair steps it resumed the session for."""

    message: str
    checked: bool
    repairs: int = 0


@dataclass(frozen=True)
class FixedFinding:
    """A finding whose fix session replied DONE or UPDATED: it waits for the related runs of its batch.
    *streams* are the stream logs of the session's steps (the fix, then each repair), from which its related
    tests are planned; a repair appends its own."""

    finding: Path
    given: bytes
    outcome: str
    row: StepRow
    streams: list[Path]


def _fix_steps(chain: Chain, batch: Sequence[Path], model: str, effort: str) -> list[StepRow]:
    """The fix step of each finding of *batch*, in batch order, the sessions running side by side (one after
    another in a dry run, which only prints them)."""
    concurrent = len(batch) > 1 and not chain.options.dry_run

    def fix(finding: Path) -> StepRow:
        return chain.step("fix", f"/implement-finding\nFINDING: {finding}\nCLOSE: script", model=model,
                          effort=effort, concurrent=concurrent, subject=str(finding))

    if not concurrent:
        return [fix(finding) for finding in batch]
    with ThreadPoolExecutor(max_workers=len(batch)) as pool:
        return list(pool.map(fix, batch))


def _fix_verdict(chain: Chain, finding: Path, row: StepRow) -> tuple[str, str]:
    """The outcome of *finding* when its fix step settles it without related runs (else empty), and the
    ``Finding fix:`` outcome the session replied."""
    if row.dry_run:
        return DRY_RUN_OUTCOME, ""
    resume = f"claude --resume {row.session_id}"
    if row.is_error:
        return f"{FAILED_PREFIX}: the session ended in error ({row.subtype}); {resume}", ""
    if not finding.exists():
        return f"{FAILED_PREFIX}: the session deleted the finding itself, so its tests were not checked; {resume}", ""
    outcome, blocker = finding_outcome("\n".join(chain.replies(row)))
    if not outcome:
        return f"{FAILED_PREFIX}: the session replied with no 'Finding fix:' line; {resume}", ""
    if blocker:
        return f"{NEEDS_JON_PREFIX}: stopped {blocker}; {resume}", outcome
    if outcome == ALREADY_RESOLVED:
        if close(finding, inbox=inbox_dir(WORKSPACE_DIR)) == EXIT_DELETED:
            return "deleted (no longer an issue)", outcome
        return f"{FAILED_PREFIX}: already resolved, but not deletable (see above); {resume}", outcome
    return "", outcome


def _settle(fixed: FixedFinding, proof: RelatedProof) -> str:
    """Close or keep a fixed finding by its batch's related proof; its outcome."""
    resume = f"claude --resume {fixed.row.session_id}"
    if proof.message:
        return f"{proof.message}; {resume}"
    if fixed.outcome == UPDATED:
        return f"{updated_verdict(fixed.finding, fixed.given)}; {resume}"
    session_log = None if proof.checked else fixed.row.stream_path
    if close(fixed.finding, session_log, inbox_dir(WORKSPACE_DIR)) == EXIT_DELETED:
        return "fixed and deleted"
    return f"{FAILED_PREFIX}: fixed, but left in place (see above); {resume}"


def run_batch(chain: Chain, batch: Sequence[Path], model: str, effort: str) -> dict[Path, str]:
    """Fix every finding of *batch* side by side, then prove the fixed ones on the still tree (``prove_batch``)
    and close them; each finding's outcome."""
    outcomes: dict[Path, str] = {}
    present: list[Path] = []
    for finding in batch:
        if chain.options.dry_run or finding.exists():
            present.append(finding)
        else:
            outcomes[finding] = ALREADY_GONE
    given = {finding: finding.read_bytes() if finding.is_file() else b"" for finding in present}
    fixed: list[FixedFinding] = []
    for finding, row in zip(present, _fix_steps(chain, present, model, effort), strict=True):
        settled, outcome = _fix_verdict(chain, finding, row)
        if settled:
            outcomes[finding] = settled
        else:
            fixed.append(FixedFinding(finding, given[finding], outcome, row, [row.stream_path]))
    proofs = prove_batch(chain, fixed, model, effort)
    for item in fixed:
        outcomes[item.finding] = _settle(item, proofs[item.finding])
    return outcomes


def prove_batch(chain: Chain, fixed: Sequence[FixedFinding], model: str, effort: str) -> dict[Path, RelatedProof]:
    """The related proof of every fixed finding of a batch, taken after every fix session of the batch has ended,
    so no session edits while another's related tests run: the sessions are proved in turn (``prove_related``),
    and only the one being repaired edits between runs. A repair can break the related tests of a session proved
    before it, so a passing proof stands only when no repair ran after it: the sessions are proved again until a
    sweep needs no repair."""
    proofs: dict[Path, RelatedProof] = {}
    proved_after: dict[Path, int] = {}
    repairs = 0

    def stale(item: FixedFinding) -> bool:
        proof = proofs.get(item.finding)
        if proof is None:
            return True
        return not proof.message and proof.checked and proved_after[item.finding] != repairs

    while pending := [item for item in fixed if stale(item)]:
        for item in pending:
            proof = prove_related(chain, item.finding, item.row, item.streams, model, effort)
            repairs += proof.repairs
            proofs[item.finding] = proof
            proved_after[item.finding] = repairs
    return proofs


def prove_related(chain: Chain, finding: Path, row: StepRow, streams: list[Path], model: str,
                  effort: str) -> RelatedProof:
    """Run the tests related to the files the session of *finding* wrote in *streams* (``related_tests``), each
    round in a new process so the code a repair changed is the code that plans and judges; while some fail, resume
    the session with the failures, append the repair's stream to *streams* and run them again. No round count ends
    it: only a pass, a session that ended in error, or a B1-B4 blocker the repair session proves."""
    repairs = 0
    while True:
        attempt = len(list(chain.run_dir.glob(f"{row.name}-related-*")))
        try:
            verdict = verify_related_fresh(chain.options.workspace, streams,
                                           chain.run_dir / f"{row.name}-related-{attempt}")
        except AssistError as exc:
            return RelatedProof(f"{FAILED_PREFIX}: the related tests could not be planned: {exc}", True, repairs)
        if not verdict.selections:
            return RelatedProof("", False, repairs)
        say(f"  related runs of {row.name}: {len(verdict.selections)}, not passing: {len(verdict.failures)}")
        for result in verdict.failures:
            say(f"    NOT PASSING {result.selection.describe()}", ColorCodes.RED)
        if verdict.passed:
            return RelatedProof("", True, repairs)
        repair = chain.step("repair", repair_prompt(verdict), model=model, effort=effort, resume_session=row.session_id,
                            subject=str(finding))
        repairs += 1
        if repair.is_error:
            return RelatedProof(f"{FAILED_PREFIX}: the repair session ended in error ({repair.subtype})", True,
                                repairs)
        _, blocker = finding_outcome("\n".join(chain.replies(repair)))
        if blocker:
            return RelatedProof(f"{NEEDS_JON_PREFIX}: the repair stopped {blocker}", True, repairs)
        streams.append(repair.stream_path)


def run_findings(chain: Chain, selected: Sequence[Path], *, model: str, effort: str) -> NoReturn:
    """Work *selected* batch after batch (``batches``, ``run_batch``), print the outcomes, and stop with 1 on any
    failure, else 2 when a session needs Jon, else 0."""
    outcomes: dict[Path, str] = {}
    groups = batches(selected)
    for number, batch in enumerate(groups, start=1):
        say("")
        say(f"##### batch {number} of {len(groups)}: {', '.join(finding.name for finding in batch)}",
            ColorCodes.MAGENTA)
        outcomes |= run_batch(chain, batch, model, effort)
    rows = [(finding.name, outcomes[finding]) for finding in selected]
    chain.summary()
    say("=== findings ===", ColorCodes.CYAN)
    for line in ["", *table_lines(FINDINGS_COLUMNS, rows), "", ""]:
        say(line)
    if any(outcome.startswith(FAILED_PREFIX) for _, outcome in rows):
        raise ChainStopped(EXIT_FAILED)
    if any(outcome.startswith(NEEDS_JON_PREFIX) for _, outcome in rows):
        raise ChainStopped(EXIT_NEEDS_JON)
    raise ChainStopped(EXIT_DONE)


def build_parser() -> argparse.ArgumentParser:
    """The options of ``skill/implement-finding.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        description="Work through the first findings files, one fresh session per finding, a batch of sessions "
                    "side by side.",
        allow_abbrev=False,
    )
    parser.add_argument("--count", type=int, default=None,
                        help="How many findings files to take, first by name. Default: 10.")
    parser.add_argument("--all", action="store_true",
                        help="Work every findings file of the folder given with --dir (default: every folder of "
                             "<workspace>/findings in turn), with no count cap. Not with --count or --finding.")
    parser.add_argument("--finding", action="append", default=[],
                        help="A findings file to work, in place of the first --count of the inbox (repeat for each).")
    parser.add_argument("--dir", default="",
                        help="Work only this folder: absolute, or relative to <workspace>/findings. "
                             "Default: the subfolders of <workspace>/findings in turn, then its own files.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="The model of each session. Default: claude-sonnet-5-5.")
    parser.add_argument("--effort", choices=EFFORTS, default=DEFAULT_EFFORT,
                        help="The effort of each session. Default: medium.")
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
        ("Finding fix: UPDATED", (UPDATED, "")),
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
                            "azure/a1.md": "a1\n", "python/p1.md": "p1\n", "extra/e1.md": "e1\n",
                            "azure/a3.md": f"a3\n{_NEEDS_JON_TEXT}\n"})
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


def _check_all_takes_every_finding_of_the_folder_and_refuses_a_count() -> None:
    assert finding_count(False, None, []) == DEFAULT_COUNT
    assert finding_count(False, 3, []) == 3
    assert finding_count(True, None, []) == UNLIMITED
    with TemporaryDirectory() as raw:
        workspace = Path(raw)
        inbox = workspace / "findings"
        write_files(inbox, {f"azure/a{n:02d}.md": "a\n" for n in range(DEFAULT_COUNT + 2)} | {"python/p1.md": "p\n"})
        everything = select_findings(workspace, [], UNLIMITED, "")
        assert len(everything) == DEFAULT_COUNT + 3, everything
        assert [path.name for path in select_findings(workspace, [], UNLIMITED, "azure")] == [
            f"a{n:02d}.md" for n in range(DEFAULT_COUNT + 2)]
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            assert chain_exit_code(lambda: finding_count(True, 3, [])) == EXIT_FAILED
            assert chain_exit_code(lambda: finding_count(True, None, ["a.md"])) == EXIT_FAILED
        assert len(printed.getvalue().splitlines()) == 2, printed.getvalue()


def _check_batches_take_the_folders_in_turn() -> None:
    inbox = Path("findings")
    selected = [inbox / "python" / "p1.md", inbox / "python" / "p2.md", inbox / "python" / "p3.md",
                inbox / "azure" / "a1.md", inbox / "docs" / "d1.md", inbox / "docs" / "d2.md"]
    names = [[path.name for path in batch] for batch in batches(selected, 4)]
    assert names == [["p1.md", "a1.md", "d1.md", "p2.md"], ["d2.md", "p3.md"]], names
    assert batches([], 4) == []


_REPAIR_SESSION: Final = "5b0c4a8e-3a7f-4f43-9a0e-2f4f1f0f9c11"
_REPAIR_FINDING: Final = Path("findings") / "a.md"
_STUB_RESULT: Final = ('{{"type":"result","subtype":"success","is_error":false,"num_turns":1,"result":"{reply}",'
                       f'"session_id":"{_REPAIR_SESSION}","total_cost_usd":0,"modelUsage":{{{{}}}},"permission_denials":[]}}}}')


def _stub_claude(directory: Path, fixed_flag: Path | None, reply: str = "Finding fix: DONE",
                 flag_text: str = "") -> str:
    """A real ``claude`` executable for a check: it reads the prompt, writes *flag_text* (a blank line when empty)
    to *fixed_flag* (the stub harness passes once it exists) and prints one result event whose text is *reply*."""
    result = _STUB_RESULT.format(reply=reply)
    if os.name == "nt":
        script = directory / "claude.cmd"
        flag_line = f'echo {flag_text or "."}>"{fixed_flag}"\n' if fixed_flag else ""
        script.write_text(f"@echo off\nmore >nul\n{flag_line}echo {result}\n", encoding="utf-8")
    else:
        script = directory / "claude"
        flag_line = f"echo '{flag_text}' > \"{fixed_flag}\"\n" if fixed_flag else ""
        script.write_text(f"#!/bin/sh\ncat >/dev/null\n{flag_line}echo '{result}'\n", encoding="utf-8")
        script.chmod(0o755)
    return str(script)


def _overlap_stub_claude(directory: Path, sessions: Path, reply: str) -> str:
    """A real ``claude`` executable that claims a folder of its own under *sessions*, writes ``start`` there, waits
    about two seconds, writes ``end`` and prints one result event whose text is *reply*. Each session writes only
    its own files, because ``cmd`` fails an append to a file another process has open; sessions that ran side by
    side leave every ``start`` older than every ``end``. ``mkdir`` is the claim: ``cmd`` has no process id, and
    ``%RANDOM%`` repeats across processes started in the same second."""
    result = _STUB_RESULT.format(reply=reply)
    if os.name == "nt":
        script = directory / "claude.cmd"
        script.write_text(f'@echo off\nmore >nul\nset n=0\n:claim\nset /a n+=1\n'
                          f'mkdir "{sessions}\\%n%" 2>nul || goto claim\n'
                          f'echo start>"{sessions}\\%n%\\start"\nping -n 3 127.0.0.1 >nul\n'
                          f'echo end>"{sessions}\\%n%\\end"\necho {result}\n', encoding="utf-8")
    else:
        script = directory / "claude"
        script.write_text(f"#!/bin/sh\ncat >/dev/null\nmkdir \"{sessions}/$$\"\necho start > \"{sessions}/$$/start\"\n"
                          f"sleep 2\necho end > \"{sessions}/$$/end\"\necho '{result}'\n", encoding="utf-8")
        script.chmod(0o755)
    return str(script)


def _fixed_session(root: Path, package: str = "lib", label: str = "01-fix") -> StepRow:
    """The finished fix step of a session that changed a package's source and its test (each edit swaps one
    plain word, so no other test file names what it changed)."""
    stream = root / f"{label}.stream.jsonl"
    written = [root / f"datrix-{package}" / "src" / f"datrix_{package}" / "__init__.py",
               root / f"datrix-{package}" / "tests" / "unit" / f"test_{package}.py"]
    stream.write_text("\n".join(tool_use_line("Edit", {"file_path": str(path), "old_string": "one",
                                                       "new_string": "two"}) for path in written),
                      encoding="utf-8")
    return StepRow(label, False, "success", "Finding fix: DONE", _REPAIR_SESSION, "", 1, 0.0, 0.0, 0, stream, False)


def _proof_after_repairs(repairs_fix_it: bool) -> tuple[RelatedProof, int, str]:
    """prove_related over a workspace whose related runs fail until the stub session's repair creates the flag
    (when *repairs_fix_it*; otherwise the repair replies with a blocker); the proof, the number of repair
    steps run and what was printed."""
    with TemporaryDirectory() as raw:
        root = Path(raw)
        write_workspace(root)
        flag = root / "datrix" / "scripts" / "test" / "fixed.flag"
        write_stub_harness(root, "if (Test-Path \"$PSScriptRoot/fixed.flag\") { Write-Output 'Total: 1 | Passed: 1 | "
                                 "Failed: 0'; exit 0 }\nWrite-Output 'Total: 1 | Passed: 0 | Failed: 1'\nexit 1\n")
        chain = Chain(ChainOptions(workspace=root, auto_compact_window=0, quiet=True),
                      _stub_claude(root, flag if repairs_fix_it else None,
                                   "Finding fix: DONE" if repairs_fix_it else "Finding fix: BLOCKED B2"))
        row = _fixed_session(root)
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            proof = prove_related(chain, _REPAIR_FINDING, row, [row.stream_path], DEFAULT_MODEL, DEFAULT_EFFORT)
        return proof, len(chain.steps), printed.getvalue()


def _check_failing_related_runs_resume_the_session_until_they_pass() -> None:
    proof, repairs, printed = _proof_after_repairs(repairs_fix_it=True)
    assert (proof, repairs) == (RelatedProof("", True, 1), 1), (proof, repairs)
    assert f"=== step 01-repair {_REPAIR_FINDING} (" in printed, printed
    proof, repairs, _ = _proof_after_repairs(repairs_fix_it=False)
    assert proof.checked and proof.message.startswith(NEEDS_JON_PREFIX) and repairs == 1, (proof, repairs)


def _check_a_repair_proves_the_sessions_before_it_again() -> None:
    """The lib session's related run passes; the other session's fails until its repair; that repair could have
    broken lib, so lib is proved again: lib, other, other, lib."""
    with TemporaryDirectory() as raw:
        root = Path(raw)
        write_workspace(root)
        harness_dir = root / "datrix" / "scripts" / "test"
        write_stub_harness(root, "$given = $args -join ' '\nAdd-Content \"$PSScriptRoot/runs.log\" $given\n"
                                 "if ($given -match 'test_other' -and -not (Test-Path \"$PSScriptRoot/fixed.flag\")) "
                                 "{ Write-Output 'Total: 1 | Passed: 0 | Failed: 1'; exit 1 }\n"
                                 "Write-Output 'Total: 1 | Passed: 1 | Failed: 0'\nexit 0\n")
        chain = Chain(ChainOptions(workspace=root, auto_compact_window=0, quiet=True),
                      _stub_claude(root, harness_dir / "fixed.flag"))
        fixed = []
        for package, label in (("lib", "01-fix"), ("other", "02-fix")):
            row = _fixed_session(root, package, label)
            fixed.append(FixedFinding(root / f"{package}.md", b"", "DONE", row, [row.stream_path]))
        with contextlib.redirect_stdout(io.StringIO()):
            proofs = prove_batch(chain, fixed, DEFAULT_MODEL, DEFAULT_EFFORT)
        runs = ["lib" if "test_lib" in line else "other"
                for line in (harness_dir / "runs.log").read_text(encoding="utf-8").splitlines()]
    assert proofs == {root / "lib.md": RelatedProof("", True, 0), root / "other.md": RelatedProof("", True, 1)}, proofs
    assert runs == ["lib", "other", "other", "lib"], runs
    assert [row.name for row in chain.steps] == ["01-repair"], chain.steps


def _check_the_fix_sessions_of_a_batch_run_side_by_side() -> None:
    with TemporaryDirectory() as raw:
        root = Path(raw)
        write_files(root / "findings", {"a.md": "a\n", "b.md": "b\n"})
        sessions = root / "sessions"
        sessions.mkdir()
        chain = Chain(ChainOptions(workspace=root, auto_compact_window=0, quiet=True),
                      _overlap_stub_claude(root, sessions, "Finding fix: BLOCKED B2"))
        findings = [root / "findings" / "a.md", root / "findings" / "b.md"]
        with contextlib.redirect_stdout(io.StringIO()):
            outcomes = run_batch(chain, findings, DEFAULT_MODEL, DEFAULT_EFFORT)
        starts = [path.stat().st_mtime_ns for path in sessions.glob("*/start")]
        ends = [path.stat().st_mtime_ns for path in sessions.glob("*/end")]
    assert len(starts) == len(ends) == len(findings), (starts, ends)
    assert max(starts) < min(ends), (starts, ends)
    assert all(outcomes[finding].startswith(NEEDS_JON_PREFIX) for finding in findings), outcomes


_NEEDS_JON_TEXT: Final = "- **Needs Jon:** growth"


def _updated_outcome(rewrite: str | None) -> str:
    """run_batch over a stub session that replies UPDATED and, unless *rewrite* is None, overwrites the
    finding with *rewrite* ('' leaves a blank line)."""
    with TemporaryDirectory() as raw:
        root = Path(raw)
        write_workspace(root)
        write_files(root / "findings", {"a.md": "premise\n"})
        finding = root / "findings" / "a.md"
        chain = Chain(ChainOptions(workspace=root, auto_compact_window=0, quiet=True),
                      _stub_claude(root, None if rewrite is None else finding, "Finding fix: UPDATED", rewrite or ""))
        with contextlib.redirect_stdout(io.StringIO()):
            return run_batch(chain, [finding], DEFAULT_MODEL, DEFAULT_EFFORT)[finding]


def _check_an_updated_finding_stays_marked_and_must_have_changed() -> None:
    marked = _updated_outcome(_NEEDS_JON_TEXT)
    assert marked.startswith(NEEDS_JON_PREFIX), marked
    unmarked = _updated_outcome("")
    assert unmarked.startswith(FAILED_PREFIX) and "Needs Jon" in unmarked, unmarked
    unchanged = _updated_outcome(None)
    assert unchanged.startswith(FAILED_PREFIX) and "unchanged" in unchanged, unchanged


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
        "", "##### batch 1 of 1: a.md, b.md",
        "", f"=== step 01-fix {selected[0]} (claude-sonnet-5-5, medium) ===", "/implement-finding",
        f"FINDING: {selected[0]}", "CLOSE: script",
        "", f"=== step 02-fix {selected[1]} (claude-sonnet-5-5, medium) ===", "/implement-finding",
        f"FINDING: {selected[1]}", "CLOSE: script",
        "=== findings ===", "", "Finding Outcome", "------- -------", "a.md    dry run", "b.md    dry run", "", "",
    ], printed.getvalue()


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        checks = [*CHAIN_CHECKS, *RELATED_CHECKS, _check_the_outcome_is_the_last_finding_fix_line,
                  _check_findings_are_selected_and_closed_in_process,
                  _check_the_subfolders_are_worked_in_turn_or_only_the_one_given,
                  _check_all_takes_every_finding_of_the_folder_and_refuses_a_count,
                  _check_batches_take_the_folders_in_turn,
                  _check_failing_related_runs_resume_the_session_until_they_pass,
                  _check_a_repair_proves_the_sessions_before_it_again,
                  _check_the_fix_sessions_of_a_batch_run_side_by_side,
                  _check_an_updated_finding_stays_marked_and_must_have_changed,
                  _check_a_dry_run_prints_every_session]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=SKILL_SCRIPTS_DIR)

    def body() -> NoReturn:
        selected = select_findings(WORKSPACE_DIR, args.finding, finding_count(args.all, args.count, args.finding),
                                   args.dir)
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
