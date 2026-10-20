"""Implement a design directly, with no tasks: implement -> verify -> absorb, each step a fresh headless
session on its own skill's model.

The module behind ``scripts/skill/implement-design.ps1`` (and its ``.sh`` twin), over the steps of
``datrix_scripts.skill.chain``:

  implement  /implement-design-direct with STOP AFTER: implement, on its model
  verify     /verify-implementation, TASKS: none, FILES from the ledger, on its model
  absorb     /absorb-design, on its model

The implement step keeps its work plan in a ledger this module names,
``<workspace>/.tmp/implement-direct-<design file name>.md``, and the checks between steps are done here,
not by a model: implement is done only when the ledger exists, has no unchecked unit and has a
``## Files changed`` section. No ledger means it stopped at its gate for a decision (exit 2); unchecked
units mean it ran out of turn, so implement runs again from the ledger (up to ``--max-rounds``). Absorb
runs only after verify replies ``Design conformance: PROVEN`` (``Chain.verify_design``); on INCOMPLETE,
implement runs again with ``GAPS:`` naming verify's saved reply.

Exit codes: 0 the design is absorbed (or a passing self-test); 1 a step ended in error, a check failed, or
the arguments name no usable design or ledger; 2 a step stopped for a decision only Jon can make (its reply
and session id are printed), or a command line this module cannot read.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import os
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
    DEFAULT_MAX_ROUNDS,
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
)
from datrix_scripts.test.wrappers import SKILL_SCRIPTS_DIR, module_main, run_self_test

MODULE: Final = "datrix_scripts.skill.implement_design"
WRAPPER: Final = "implement-design"
STEPS: Final = ("implement", "verify", "absorb")
UNCHECKED_UNIT: Final = re.compile(r"^\s*\|.*\[ \]", re.MULTILINE | re.IGNORECASE)
FILES_CHANGED: Final = re.compile(r"^##\s+Files changed\s*$", re.MULTILINE | re.IGNORECASE)
NO_LEDGER: Final = "no ledger"


def ledger_path(workspace: Path, design: Path) -> Path:
    """The ledger the implement step keeps for *design*."""
    return workspace / ".tmp" / f"implement-direct-{design.stem}.md"


def ledger_gap(ledger: Path) -> str:
    """What the ledger still lacks for implement to be done: no ledger, unchecked units, no
    ``## Files changed`` section; empty when nothing."""
    if not ledger.is_file():
        return NO_LEDGER
    text = ledger.read_text(encoding="utf-8-sig")
    if UNCHECKED_UNIT.search(text):
        return "unchecked units"
    if not FILES_CHANGED.search(text):
        return "no '## Files changed' section"
    return ""


def preflight(design: str, start_at: str, *, dry_run: bool, workspace: Path) -> tuple[Path, Path]:
    """The design's absolute path and its ledger; stops with 1 when the design is missing, or a later
    start has no ledger to start from."""
    if not design or not Path(design).exists():
        say(f"Pass the design document: -Design <path> (got '{design}'). Get-Help .\\implement-design.ps1 "
            "-Full.", ColorCodes.RED)
        raise ChainStopped(EXIT_FAILED)
    design_path = Path(os.path.abspath(design))
    ledger = ledger_path(workspace, design_path)
    if STEPS.index(start_at) > 0 and not dry_run and not ledger.is_file():
        say(f"-StartAt {start_at} needs the implement step's ledger, and there is none: {ledger}", ColorCodes.RED)
        raise ChainStopped(EXIT_FAILED)
    return design_path, ledger


def implement(chain: Chain, design: Path, ledger: Path, max_rounds: int, gaps: str = "") -> None:
    """Run /implement-design-direct until its ledger is complete (up to *max_rounds* runs)."""
    prompt = f"/implement-design-direct\nDOCUMENT: {design}\nLEDGER: {ledger}\nSTOP AFTER: implement"
    if gaps:
        prompt += f"\nGAPS: {gaps}"
    row: StepRow | None = None
    for round_number in range(1, max_rounds + 1):
        row = chain.step("implement", prompt)
        if row.dry_run:
            return
        if row.is_error:
            chain.stop(EXIT_FAILED, f"/implement-design-direct ended in error ({row.subtype}).", row)
        gap = ledger_gap(ledger)
        if not gap:
            return
        if gap == NO_LEDGER:
            chain.stop(EXIT_NEEDS_JON, "/implement-design-direct wrote no ledger, so it stopped at its gate for a "
                                       "decision. Answer it in its session, then rerun this script.", row)
        say(f"Implement round {round_number} of {max_rounds} left the ledger with {gap}; running it again.",
            ColorCodes.YELLOW)
    chain.stop(EXIT_FAILED, f"The ledger still has {ledger_gap(ledger)} after {max_rounds} implement run(s): {ledger}",
               row)


def run_direct(chain: Chain, design: Path, ledger: Path, *, start_at: str, keep_source: bool,
               max_rounds: int) -> NoReturn:
    """The chain from *start_at*: implement, verify (implementing again on INCOMPLETE), absorb."""
    first = STEPS.index(start_at)
    if first <= 0:
        implement(chain, design, ledger, max_rounds)
    if first <= 1:
        prompt = (f"/verify-implementation\nDESIGN: {design}\nTASKS: none\n"
                  f"FILES: the files listed under '## Files changed' in {ledger}")
        chain.verify_design(prompt, design, lambda report: implement(chain, design, ledger, max_rounds, str(report)),
                            max_rounds)
    chain.absorb_design(design, keep_source=keep_source)
    chain.complete()


def build_parser() -> argparse.ArgumentParser:
    """The options of ``skill/implement-design.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        description="Implement a design directly: implement -> verify -> absorb, each step a fresh headless session.",
        allow_abbrev=False,
    )
    parser.add_argument("--design", default="", help="The design document to implement.")
    parser.add_argument("--start-at", choices=STEPS, default=STEPS[0],
                        help="The step to start at, to resume after answering a question.")
    parser.add_argument("--keep-source", action="store_true", help="Pass KEEP SOURCE: true to /absorb-design.")
    add_chain_arguments(parser, resume=True)
    parser.add_argument("--max-rounds", type=int, default=DEFAULT_MAX_ROUNDS,
                        help="How many times implement (and verify) may run before the chain gives up. Default: 3.")
    parser.add_argument("--self-test", action="store_true",
                        help="Run only the chain checks, the ledger and dry-run checks and the wrapper seam checks.")
    parser.set_defaults(debug=False)
    return parser


def _check_the_ledger_gap_is_read_from_the_ledger() -> None:
    with TemporaryDirectory() as raw:
        ledger = Path(raw) / "ledger.md"
        cases = (
            ("| U01 | change | [ ] |\n## Files changed\n", "unchecked units"),
            ("| U01 | change | [x] |\n", "no '## Files changed' section"),
            ("| U01 | change | [x] proof |\n\n## files changed\n- a.py\n", ""),
        )
        assert ledger_gap(ledger) == NO_LEDGER
        for text, gap in cases:
            write_files(ledger.parent, {ledger.name: text})
            assert ledger_gap(ledger) == gap, (text, ledger_gap(ledger))


def _check_a_missing_design_or_ledger_stops_before_any_step() -> None:
    with TemporaryDirectory() as raw:
        workspace = Path(raw)
        design = workspace / "design" / "099-x.md"
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            for args in (("", "implement"), (str(design), "implement"), (str(design.parent / "absent.md"), "verify")):
                code = chain_exit_code(lambda: preflight(args[0], args[1], dry_run=False, workspace=workspace))
                assert code == EXIT_FAILED, (args, code)
            write_files(design.parent, {design.name: "# x\n"})
            code = chain_exit_code(lambda: preflight(str(design), "absorb", dry_run=False, workspace=workspace))
            assert code == EXIT_FAILED, code
            assert preflight(str(design), "absorb", dry_run=True, workspace=workspace) == (
                design, workspace / ".tmp" / "implement-direct-099-x.md")
    lines = printed.getvalue().splitlines()
    assert lines[0] == "Pass the design document: -Design <path> (got ''). Get-Help .\\implement-design.ps1 -Full.", lines
    assert lines[-1] == (f"-StartAt absorb needs the implement step's ledger, and there is none: "
                         f"{workspace / '.tmp' / 'implement-direct-099-x.md'}"), lines


def _check_a_dry_run_prints_implement_verify_and_absorb() -> None:
    with TemporaryDirectory() as raw:
        workspace = Path(raw)
        design = workspace / "d.md"
        ledger = ledger_path(workspace, design)
        chain = Chain(ChainOptions(workspace=workspace, dry_run=True, auto_compact_window=0), CLAUDE)
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            code = chain_exit_code(lambda: run_direct(chain, design, ledger, start_at="implement", keep_source=False,
                                                      max_rounds=DEFAULT_MAX_ROUNDS))
    assert code == EXIT_DONE, code
    proof = workspace / ".tmp" / "verify-proven-d.md"
    assert printed.getvalue().splitlines() == [
        "", "=== step 01-implement ===", "/implement-design-direct", f"DOCUMENT: {design}", f"LEDGER: {ledger}",
        "STOP AFTER: implement",
        "", "=== step 02-verify ===", "/verify-implementation", f"DESIGN: {design}", "TASKS: none",
        f"FILES: the files listed under '## Files changed' in {ledger}",
        "", "=== step 03-absorb ===", "/absorb-design", f"DOCUMENT: {design}", f"VERIFIED: {proof}",
    ], printed.getvalue()


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        checks = [*CHAIN_CHECKS, _check_the_ledger_gap_is_read_from_the_ledger,
                  _check_a_missing_design_or_ledger_stops_before_any_step, _check_a_dry_run_prints_implement_verify_and_absorb]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=SKILL_SCRIPTS_DIR)

    def body() -> NoReturn:
        design, ledger = preflight(args.design, args.start_at, dry_run=args.dry_run, workspace=WORKSPACE_DIR)
        chain = Chain.start(chain_options(args, WORKSPACE_DIR, resume=args.resume))
        run_direct(chain, design, ledger, start_at=args.start_at, keep_source=args.keep_source,
                   max_rounds=args.max_rounds)

    return chain_exit_code(body)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
