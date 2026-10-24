"""Implement a design directly, with no tasks: implement -> verify -> absorb, each step a fresh headless
session on its own skill's model.

The module behind ``scripts/skill/implement-design.ps1`` (and its ``.sh`` twin), over the steps of
``datrix_scripts.skill.chain``:

  implement  /implement-design-direct, on its model, as several sessions: STOP AFTER: plan (the gate and
             the ledger), then UNIT: <id> for each unchecked ledger unit, then UNIT: sweep
  verify     /verify-implementation, TASKS: none, FILES from the ledger, on its model
  absorb     /absorb-design, on its model

Every response re-reads the whole context, so what a step costs grows with the square of its length:
one session over every unit of a design re-read about 270k tokens per response and compacted twice,
where a session per unit starts from the design and the ledger and ends before its context is large.

The implement step keeps its work plan in a ledger this module names,
``<workspace>/.tmp/implement-direct-<design file name>.md``, and the checks between sessions are done here,
not by a model: the plan session is run only when there is no ledger (or verify left gaps), and no ledger
after it means it stopped at its gate for a decision (exit 2). A unit whose row is still unchecked after
its session runs again (up to ``--max-rounds`` sessions per unit). Implement is done only when a sweep
session leaves the ledger with no unchecked unit and a ``## Files changed`` section. Absorb runs only
after verify replies ``Design conformance: PROVEN`` (``Chain.verify_design``); on INCOMPLETE, a plan
session with ``GAPS:`` naming verify's saved reply adds the units, and the unit sessions run again.

Without ``--design`` it takes the first ``--count`` (default 10) ``*.md`` files of ``<workspace>/design``, by
name, and runs the chain on each in turn. Later designs build on earlier ones, so the first design that does
not finish stops the run.

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
    IMPLEMENT_TOOLS,
    Chain,
    ChainOptions,
    ChainStopped,
    StepRow,
    add_chain_arguments,
    chain_exit_code,
    chain_options,
)
from datrix_scripts.skill.finding_inbox import DEFAULT_COUNT
from datrix_scripts.test.wrappers import SKILL_SCRIPTS_DIR, module_main, run_self_test

MODULE: Final = "datrix_scripts.skill.implement_design"
WRAPPER: Final = "implement-design"
STEPS: Final = ("implement", "verify", "absorb")
# A ledger row whose last cell (the state) is an unticked box; group 1 is the unit's id (the first cell).
UNCHECKED_UNIT: Final = re.compile(r"^\s*\|\s*([^|\s]+)\s*\|.*\|\s*\[ \]\s*\|?\s*$", re.MULTILINE)
SWEEP: Final = "sweep"
FILES_CHANGED: Final = re.compile(r"^##\s+Files changed\s*$", re.MULTILINE | re.IGNORECASE)
NO_LEDGER: Final = "no ledger"
DESIGN_DIR_PARTS: Final = ("design",)


def ledger_path(workspace: Path, design: Path) -> Path:
    """The ledger the implement step keeps for *design*."""
    return workspace / ".tmp" / f"implement-direct-{design.stem}.md"


def ledger_gap(ledger: Path) -> str:
    """What the ledger still lacks for implement to be done: no ledger, unchecked units, no
    ``## Files changed`` section; empty when nothing."""
    if not ledger.is_file():
        return NO_LEDGER
    if unchecked_units(ledger):
        return "unchecked units"
    if not FILES_CHANGED.search(ledger.read_text(encoding="utf-8-sig")):
        return "no '## Files changed' section"
    return ""


def unchecked_units(ledger: Path) -> list[str]:
    """The ids of the ledger's unchecked units, in ledger order; empty when there is no ledger."""
    if not ledger.is_file():
        return []
    return UNCHECKED_UNIT.findall(ledger.read_text(encoding="utf-8-sig"))


def design_files(workspace: Path, count: int) -> list[Path]:
    """The first *count* ``*.md`` files directly in ``<workspace>/design``, by name; stops with 1 when the
    folder is missing or *count* is below 1."""
    directory = workspace.joinpath(*DESIGN_DIR_PARTS)
    if not directory.is_dir():
        say(f"Design folder '{directory}' does not exist. Pass -Design <path>.", ColorCodes.RED)
        raise ChainStopped(EXIT_FAILED)
    if count < 1:
        say(f"-Count must be at least 1 (got {count}).", ColorCodes.RED)
        raise ChainStopped(EXIT_FAILED)
    return sorted(path for path in directory.glob("*.md") if path.is_file())[:count]


def select_designs(design: str, count: int, start_at: str, workspace: Path) -> list[Path]:
    """The designs to implement: *design* alone when given, else the first *count* of the design folder;
    stops with 1 when -StartAt is given without -Design (a later start needs one named design's ledger)."""
    if design:
        return [Path(design)]
    if start_at != STEPS[0]:
        say(f"-StartAt {start_at} resumes one design's run; pass that design with -Design <path>.", ColorCodes.RED)
        raise ChainStopped(EXIT_FAILED)
    return design_files(workspace, count)


def preflight(design: str, start_at: str, *, dry_run: bool, workspace: Path) -> tuple[Path, Path]:
    """The design's absolute path and its ledger; stops with 1 when the design is missing, or a later
    start has no ledger to start from."""
    if not design or not Path(design).exists():
        say(f"Design document not found: '{design}'. Pass an existing file to -Design. "
            "Get-Help .\\implement-design.ps1 -Full.", ColorCodes.RED)
        raise ChainStopped(EXIT_FAILED)
    design_path = Path(os.path.abspath(design))
    ledger = ledger_path(workspace, design_path)
    if STEPS.index(start_at) > 0 and not dry_run and not ledger.is_file():
        say(f"-StartAt {start_at} needs the implement step's ledger, and there is none: {ledger}", ColorCodes.RED)
        raise ChainStopped(EXIT_FAILED)
    return design_path, ledger


def implement_prompt(design: Path, ledger: Path, *options: str) -> str:
    """The /implement-design-direct prompt of one session: the design, the ledger and *options*."""
    return "\n".join(["/implement-design-direct", f"DOCUMENT: {design}", f"LEDGER: {ledger}", *options])


def implement_step(chain: Chain, name: str, prompt: str) -> StepRow:
    """One implement session, limited to the tools implement uses (``IMPLEMENT_TOOLS``)."""
    return chain.step(name, prompt, tools=IMPLEMENT_TOOLS)


def stop_on_error(chain: Chain, row: StepRow, session: str) -> None:
    """Stop the chain with 1 when the *session*'s step ended in error."""
    if row.is_error:
        chain.stop(EXIT_FAILED, f"/implement-design-direct ({session}) ended in error ({row.subtype}).", row)


def plan(chain: Chain, design: Path, ledger: Path, gaps: str) -> StepRow:
    """Run the plan session: the gate and the ledger, with a unit added for each finding of the *gaps* report;
    stops with 2 when it wrote no ledger (it stopped at its gate for a decision)."""
    options = ["STOP AFTER: plan", *([f"GAPS: {gaps}"] if gaps else [])]
    row = implement_step(chain, "plan", implement_prompt(design, ledger, *options))
    if row.dry_run:
        return row
    stop_on_error(chain, row, "plan")
    if not ledger.is_file():
        chain.stop(EXIT_NEEDS_JON, "/implement-design-direct wrote no ledger, so it stopped at its gate for a "
                                   "decision. Answer it in its session, then rerun this script.", row)
    return row


def run_unit(chain: Chain, design: Path, ledger: Path, unit: str, max_rounds: int) -> None:
    """Run one fresh session on *unit* until its ledger row is ticked (up to *max_rounds* sessions)."""
    row: StepRow | None = None
    for round_number in range(1, max_rounds + 1):
        row = implement_step(chain, f"unit-{unit}", implement_prompt(design, ledger, f"UNIT: {unit}"))
        stop_on_error(chain, row, f"unit {unit}")
        if unit not in unchecked_units(ledger):
            return
        say(f"Unit {unit} round {round_number} of {max_rounds} left its row unchecked; running it again.",
            ColorCodes.YELLOW)
    chain.stop(EXIT_FAILED, f"Unit {unit} is still unchecked after {max_rounds} session(s): {ledger}", row)


def implement(chain: Chain, design: Path, ledger: Path, max_rounds: int, gaps: str = "") -> None:
    """Implement the design as one session per step: plan (when there is no ledger, or *gaps* need units), one
    session per unchecked unit, then the sweep, which must leave a complete ledger (up to *max_rounds* sweeps)."""
    if gaps or not ledger.is_file():
        if plan(chain, design, ledger, gaps).dry_run:
            return
    sweep_prompt = implement_prompt(design, ledger, f"UNIT: {SWEEP}")
    if chain.options.dry_run:
        for unit in unchecked_units(ledger):
            implement_step(chain, f"unit-{unit}", implement_prompt(design, ledger, f"UNIT: {unit}"))
        implement_step(chain, SWEEP, sweep_prompt)
        return
    row: StepRow | None = None
    for round_number in range(1, max_rounds + 1):
        while units := unchecked_units(ledger):
            run_unit(chain, design, ledger, units[0], max_rounds)
        row = implement_step(chain, SWEEP, sweep_prompt)
        stop_on_error(chain, row, SWEEP)
        gap = ledger_gap(ledger)
        if not gap:
            return
        say(f"Sweep round {round_number} of {max_rounds} left the ledger with {gap}; running it again.",
            ColorCodes.YELLOW)
    chain.stop(EXIT_FAILED, f"The ledger still has {ledger_gap(ledger)} after {max_rounds} sweep(s): {ledger}", row)


def run_direct(chain: Chain, design: Path, ledger: Path, *, start_at: str, keep_source: bool,
               max_rounds: int) -> None:
    """One design's chain from *start_at*: implement, verify (implementing again on INCOMPLETE), absorb.
    Returns when the design is absorbed; any failure stops the whole chain."""
    first = STEPS.index(start_at)
    if first <= 0:
        implement(chain, design, ledger, max_rounds)
    if first <= 1:
        prompt = (f"/verify-implementation\nDESIGN: {design}\nTASKS: none\n"
                  f"FILES: the files listed under '## Files changed' in {ledger}")
        chain.verify_design(prompt, design, lambda report: implement(chain, design, ledger, max_rounds, str(report)),
                            max_rounds)
    chain.absorb_design(design, keep_source=keep_source)


def run_designs(chain: Chain, designs: Sequence[Path], *, start_at: str, keep_source: bool, max_rounds: int,
                dry_run: bool, workspace: Path) -> NoReturn:
    """Each design in turn, in name order. Later designs build on earlier ones, so the first design that
    does not finish stops the chain."""
    for number, name in enumerate(designs, start=1):
        design, ledger = preflight(str(name), start_at, dry_run=dry_run, workspace=workspace)
        say("")
        say(f"##### design {number} of {len(designs)}: {design.name}", ColorCodes.MAGENTA)
        run_direct(chain, design, ledger, start_at=start_at, keep_source=keep_source, max_rounds=max_rounds)
    chain.complete()


def build_parser() -> argparse.ArgumentParser:
    """The options of ``skill/implement-design.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        description="Implement a design directly: implement -> verify -> absorb, each step a fresh headless session.",
        allow_abbrev=False,
    )
    parser.add_argument("--design", default="",
                        help="The design document to implement, in place of the first --count of the design folder.")
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT,
                        help="How many designs to take from the design folder, first by name. Default: 10.")
    parser.add_argument("--start-at", choices=STEPS, default=STEPS[0],
                        help="The step to start at, to resume after answering a question.")
    parser.add_argument("--keep-source", action="store_true", help="Pass KEEP SOURCE: true to /absorb-design.")
    add_chain_arguments(parser, resume=True)
    parser.add_argument("--max-rounds", type=int, default=DEFAULT_MAX_ROUNDS,
                        help="How many sessions one unit (or the sweep), and how many verify runs, may take before the "
                             "chain gives up. Default: 3.")
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
        assert unchecked_units(ledger) == []
        for text, gap in cases:
            write_files(ledger.parent, {ledger.name: text})
            assert ledger_gap(ledger) == gap, (text, ledger_gap(ledger))
        write_files(ledger.parent, {ledger.name: (
            "| id | change | acceptance | state |\n|---|---|---|---|\n"
            "| U01 | a | no `[ ]` left | [x] `test.ps1 pkg` → pass: 3 (a | b) |\n"
            "| U02 | b | c | [ ] |\n| U03 | d | e | [ ] |\n")})
        assert unchecked_units(ledger) == ["U02", "U03"], unchecked_units(ledger)


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
    assert lines[0] == ("Design document not found: ''. Pass an existing file to -Design. "
                        "Get-Help .\\implement-design.ps1 -Full."), lines
    assert lines[-1] == (f"-StartAt absorb needs the implement step's ledger, and there is none: "
                         f"{workspace / '.tmp' / 'implement-direct-099-x.md'}"), lines


def _check_designs_are_selected_by_name_and_count() -> None:
    with TemporaryDirectory() as raw:
        workspace = Path(raw)
        folder = workspace / "design"
        write_files(folder, {"020-b.md": "b\n", "010-a.md": "a\n", "030-c.md": "c\n", "notes.txt": "x\n"})
        assert select_designs("", 2, "implement", workspace) == [folder / "010-a.md", folder / "020-b.md"]
        assert select_designs("x.md", 2, "verify", workspace) == [Path("x.md")]
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            assert chain_exit_code(lambda: select_designs("", 0, "implement", workspace)) == EXIT_FAILED
            assert chain_exit_code(lambda: select_designs("", 2, "verify", workspace)) == EXIT_FAILED
            assert chain_exit_code(lambda: select_designs("", 2, "implement", workspace / "none")) == EXIT_FAILED
    assert len(printed.getvalue().splitlines()) == 3, printed.getvalue()


def _dry_run_lines(workspace: Path, design: Path) -> list[str]:
    chain = Chain(ChainOptions(workspace=workspace, dry_run=True, auto_compact_window=0), CLAUDE)
    printed = io.StringIO()
    with contextlib.redirect_stdout(printed):
        code = chain_exit_code(lambda: run_designs(chain, [design], start_at="implement", keep_source=False,
                                                   max_rounds=DEFAULT_MAX_ROUNDS, dry_run=True,
                                                   workspace=workspace))
    assert code == EXIT_DONE, code
    return printed.getvalue().splitlines()


def _check_a_dry_run_prints_the_implement_sessions_verify_and_absorb() -> None:
    with TemporaryDirectory() as raw:
        workspace = Path(raw)
        design = workspace / "d.md"
        write_files(workspace, {design.name: "# d\n"})
        ledger = ledger_path(workspace, design)
        proof = workspace / ".tmp" / "verify-proven-d.md"
        head = ["", "##### design 1 of 1: d.md"]
        tail = ["", "=== step {n}-verify ===", "/verify-implementation", f"DESIGN: {design}", "TASKS: none",
                f"FILES: the files listed under '## Files changed' in {ledger}",
                "", "=== step {m}-absorb ===", "/absorb-design", f"DOCUMENT: {design}", f"VERIFIED: {proof}"]

        def session(number: int, name: str, option: str) -> list[str]:
            return ["", f"=== step {number:02d}-{name} ===", "/implement-design-direct", f"DOCUMENT: {design}",
                    f"LEDGER: {ledger}", option]

        # No ledger: only the plan is known, since the units are the plan's to write.
        no_ledger = _dry_run_lines(workspace, design)
        assert no_ledger == [*head, *session(1, "plan", "STOP AFTER: plan"),
                             *(line.format(n="02", m="03") for line in tail)], no_ledger
        # A ledger with units: one session per unchecked unit, then the sweep.
        write_files(ledger.parent, {ledger.name: "| U01 | a | [x] |\n| U02 | b | [ ] |\n| U03 | c | [ ] |\n"})
        with_ledger = _dry_run_lines(workspace, design)
        assert with_ledger == [*head, *session(1, "unit-U02", "UNIT: U02"), *session(2, "unit-U03", "UNIT: U03"),
                               *session(3, "sweep", "UNIT: sweep"),
                               *(line.format(n="04", m="05") for line in tail)], with_ledger


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        checks = [*CHAIN_CHECKS, _check_designs_are_selected_by_name_and_count,
                  _check_the_ledger_gap_is_read_from_the_ledger,
                  _check_a_missing_design_or_ledger_stops_before_any_step,
                  _check_a_dry_run_prints_the_implement_sessions_verify_and_absorb]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=SKILL_SCRIPTS_DIR)

    def body() -> NoReturn:
        designs = select_designs(args.design, args.count, args.start_at, WORKSPACE_DIR)
        if not designs:
            say("No design documents to work on.")
            raise ChainStopped(EXIT_DONE)
        say(f"Designs ({len(designs)}):")
        for design in designs:
            say(f"  {design}")
        chain = Chain.start(chain_options(args, WORKSPACE_DIR, resume=args.resume))
        run_designs(chain, designs, start_at=args.start_at, keep_source=args.keep_source,
                    max_rounds=args.max_rounds, dry_run=args.dry_run, workspace=WORKSPACE_DIR)

    return chain_exit_code(body)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
