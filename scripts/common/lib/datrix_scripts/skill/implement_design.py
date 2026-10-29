"""Implement a design directly, with no tasks: implement -> verify -> absorb, each step a fresh headless
session on its own skill's model.

The module behind ``scripts/skill/implement-design.ps1`` (and its ``.sh`` twin), over the steps of
``datrix_scripts.skill.chain``:

  implement  /implement-design-direct, on its model, as several sessions: STOP AFTER: plan (the gate and
             the ledger), then UNIT: <id> for each unchecked ledger unit
  verify     /verify-implementation, TASKS: none, FILES from the files supplement, on its model
  absorb     /absorb-design, on its model

Every response re-reads the whole context, so what a step costs grows with the square of its length:
one session over every unit of a design re-read about 270k tokens per response and compacted twice,
where a session per unit starts from the design and the ledger and ends before its context is large.

The implement step keeps its work plan in a ledger this module names,
``<workspace>/.tmp/implement-direct-<design file name>.md``, and the checks between sessions are done here,
not by a model: the plan session is run only when there is no ledger (or verify left gaps), and no ledger
after it means it stopped at its gate for a decision (exit 2). A unit whose row is still unchecked after
its session runs again (up to ``--max-rounds`` sessions per unit). Implement is done only when the ledger
has no unchecked unit and the unit proof files list the files changed. The ledger is bounded
(``ledger_rules``): a session that starts on an over-limit ledger is told to shrink it first, and the chain
stops when that session leaves it over. The files changed are never kept in the ledger: ``ledger_rules``
gathers them from the proof files into the supplement file verify reads. Absorb runs only
after verify replies ``Design conformance: PROVEN`` (``Chain.verify_design``); on INCOMPLETE, a plan
session with ``GAPS:`` naming verify's saved reply adds the units, and the unit sessions run again.

Before each unit session the workspace must load every registered plugin, in a fresh interpreter
(``plugin_load_error``). A session that starts on a workspace another session has left half-edited can
neither run its tests nor generate, and spends itself on workarounds; so a load failure stops the chain
with 1, naming the error, and a rerun resumes at the first unchecked unit.

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
import subprocess
import sys
from collections.abc import Callable, Sequence
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
from datrix_scripts.skill.finding_inbox import DEFAULT_COUNT, UNLIMITED
from datrix_scripts.skill.ledger_rules import (
    LEDGER_CHECKS,
    changed_files,
    files_supplement,
    ledger_violations,
    proof_dir,
    write_files_supplement,
)
from datrix_scripts.test.wrappers import SKILL_SCRIPTS_DIR, module_main, run_self_test

MODULE: Final = "datrix_scripts.skill.implement_design"
WRAPPER: Final = "implement-design"
STEPS: Final = ("implement", "verify", "absorb")
# A ledger row whose last cell (the state) is an unticked box; group 1 is the unit's id (the first cell).
UNCHECKED_UNIT: Final = re.compile(r"^\s*\|\s*([^|\s]+)\s*\|.*\|\s*\[ \]\s*\|?\s*$", re.MULTILINE)
# A ledger row with a state cell, ticked or not; group 1 is the unit's id (the first cell).
UNIT_ROW: Final = re.compile(r"^\s*\|\s*([^|\s]+)\s*\|.*\|\s*\[[ xX]\]", re.MULTILINE)
NO_LEDGER: Final = "no ledger"
NO_UNITS: Final = "no unit row"
NO_CHANGED_FILES: Final = "no '## Files changed' section in any unit proof file"
DESIGN_DIR_PARTS: Final = ("design",)
# Loads every registered language, platform, generator and client-target plugin, as a generation run does.
PLUGIN_LOAD_SCRIPT: Final = (
    "from datrix_codegen_kernel.generation.discovery import (get_all_generator_classes,\n"
    "    get_registered_client_targets, get_registered_languages, get_registered_platforms)\n"
    "for load in (get_registered_languages, get_registered_platforms, get_all_generator_classes,\n"
    "             get_registered_client_targets):\n"
    "    load()\n"
)
PLUGIN_LOAD_TIMEOUT_SECONDS: Final = 300
PLUGIN_LOAD_TAIL_LINES: Final = 8

PluginCheck = Callable[[], str]


def plugin_load_error(script: str = PLUGIN_LOAD_SCRIPT) -> str:
    """Why the workspace cannot load its registered plugins (*script*), as the last lines of the failure; empty
    when every plugin loads. Runs in a fresh interpreter, so it sees the code on disk now, not what this process
    imported."""
    try:
        result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                                encoding="utf-8", errors="replace", cwd=WORKSPACE_DIR,
                                timeout=PLUGIN_LOAD_TIMEOUT_SECONDS, check=False)
    except subprocess.TimeoutExpired:
        return f"loading the plugins took over {PLUGIN_LOAD_TIMEOUT_SECONDS} s"
    except OSError as error:
        return f"{type(error).__name__}: {error}"
    if result.returncode == 0:
        return ""
    output = (result.stderr or result.stdout).strip() or f"exit {result.returncode}, no output"
    return "\n".join(output.splitlines()[-PLUGIN_LOAD_TAIL_LINES:])


def ledger_path(workspace: Path, design: Path) -> Path:
    """The ledger the implement step keeps for *design*."""
    return workspace / ".tmp" / f"implement-direct-{design.stem}.md"


def ledger_gap(ledger: Path) -> str:
    """What the ledger still lacks for implement to be done: no ledger, no unit row, unchecked units, no changed
    file listed in the unit proof files; empty when nothing."""
    if not ledger.is_file():
        return NO_LEDGER
    if not ledger_units(ledger):
        return NO_UNITS
    if unchecked_units(ledger):
        return "unchecked units"
    if not changed_files(ledger):
        return NO_CHANGED_FILES
    return ""


def unchecked_units(ledger: Path) -> list[str]:
    """The ids of the ledger's unchecked units, in ledger order; empty when there is no ledger."""
    if not ledger.is_file():
        return []
    return UNCHECKED_UNIT.findall(ledger.read_text(encoding="utf-8-sig"))


def ledger_units(ledger: Path) -> list[str]:
    """The ids of every unit row of the ledger, ticked or not, in ledger order; empty when there is no ledger."""
    if not ledger.is_file():
        return []
    return UNIT_ROW.findall(ledger.read_text(encoding="utf-8-sig"))


def require_unit_rows(chain: Chain, ledger: Path) -> None:
    """Stop the chain with 1 when the ledger holds no unit row this script can read: no unchecked unit would then
    read as every unit done."""
    if not ledger_units(ledger):
        chain.stop(EXIT_FAILED, f"The ledger holds no unit row this script can read, so no unit would run. Each "
                                f"unit is one markdown table row: its id in the first cell, its state ('[ ]', or "
                                f"'[x]' and its proof) in the last. Rewrite the ledger's units as that table, then "
                                f"rerun this script: {ledger}")


def design_files(directory: Path, count: int) -> list[Path]:
    """The first *count* ``*.md`` files directly in *directory*, by name; stops with 1 when the folder is
    missing or *count* is below 1."""
    if not directory.is_dir():
        say(f"Design folder '{directory}' does not exist. Pass -Design <path>.", ColorCodes.RED)
        raise ChainStopped(EXIT_FAILED)
    if count < 1:
        say(f"-Count must be at least 1 (got {count}).", ColorCodes.RED)
        raise ChainStopped(EXIT_FAILED)
    return sorted(path for path in directory.glob("*.md") if path.is_file())[:count]


def select_designs(design: str, count: int | None, start_at: str, workspace: Path, *,
                   everything: bool = False) -> list[Path]:
    """The designs to implement: *design* alone when given, else the first *count* (default ``DEFAULT_COUNT``)
    of the design folder. With *everything*, every design of the folder *design* names (default
    ``<workspace>/design``), with no count cap; stops with 1 when that is combined with a count or names a file,
    or when -StartAt is given without a single design (a later start needs one named design's ledger)."""
    if everything:
        if count is not None or (design and not Path(design).is_dir()):
            say("-All implements every design of a folder: pass that folder (default <workspace>\\design) as "
                "-Design, and no -Count.", ColorCodes.RED)
            raise ChainStopped(EXIT_FAILED)
    elif design:
        return [Path(design)]
    if start_at != STEPS[0]:
        say(f"-StartAt {start_at} resumes one design's run; pass that design with -Design <path>.", ColorCodes.RED)
        raise ChainStopped(EXIT_FAILED)
    directory = Path(design) if design else workspace.joinpath(*DESIGN_DIR_PARTS)
    if everything:
        return design_files(directory, UNLIMITED)
    return design_files(directory, DEFAULT_COUNT if count is None else count)


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


def limit_options(violations: list[str]) -> list[str]:
    """The prompt option telling a unit session to shrink an over-limit ledger first; none when it is within them."""
    if not violations:
        return []
    return ["LEDGER LIMITS EXCEEDED: " + "; ".join(violations) + ". Before the unit, shrink the ledger to the "
            "limits: move detail into proof files (a '## Files changed' list goes into a proof file under that "
            "same heading), keep only the Units and Decisions sections."]


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


def require_plugins_load(chain: Chain, session: str, check: PluginCheck) -> None:
    """Stop the chain with 1 when *check* finds the workspace cannot load its plugins, before *session* starts."""
    error = check()
    if error:
        chain.stop(EXIT_FAILED, f"The workspace cannot load its registered plugins, so {session} would start on a "
                                f"broken test bed. Fix the failure (or let the session editing it finish), then "
                                f"rerun this script; it resumes at the first unchecked unit. The failure ends:\n"
                                f"{error}")


def run_unit(chain: Chain, design: Path, ledger: Path, unit: str, max_rounds: int,
             check: PluginCheck = plugin_load_error) -> None:
    """Run one fresh session on *unit* until its ledger row is ticked (up to *max_rounds* sessions), each after
    *check* finds every plugin loading."""
    row: StepRow | None = None
    for round_number in range(1, max_rounds + 1):
        require_plugins_load(chain, f"unit {unit}", check)
        over = ledger_violations(ledger)
        row = implement_step(chain, f"unit-{unit}", implement_prompt(design, ledger, f"UNIT: {unit}",
                                                                       *limit_options(over)))
        stop_on_error(chain, row, f"unit {unit}")
        if over and ledger_violations(ledger):
            chain.stop(EXIT_FAILED, f"The ledger was over its limits when unit {unit} started, and the session told "
                                    f"to shrink it left it over: {'; '.join(ledger_violations(ledger))}. Move the "
                                    f"detail into the proof files by hand, then rerun this script: {ledger}", row)
        if unit not in unchecked_units(ledger):
            return
        say(f"Unit {unit} round {round_number} of {max_rounds} left its row unchecked; running it again.",
            ColorCodes.YELLOW)
    chain.stop(EXIT_FAILED, f"Unit {unit} is still unchecked after {max_rounds} session(s): {ledger}", row)


def implement(chain: Chain, design: Path, ledger: Path, max_rounds: int, gaps: str = "",
              check: PluginCheck = plugin_load_error) -> None:
    """Implement the design as one session per step: plan (when there is no ledger, or *gaps* need units), then
    one session per unchecked unit. Every unit lists its changed files in its proof file, so they must be
    listed once the last unit is ticked; stops with 1 when they are not. Each unit session starts only after
    *check* finds every plugin loading."""
    if gaps or not ledger.is_file():
        if plan(chain, design, ledger, gaps).dry_run:
            return
    require_unit_rows(chain, ledger)
    if chain.options.dry_run:
        for unit in unchecked_units(ledger):
            implement_step(chain, f"unit-{unit}", implement_prompt(design, ledger, f"UNIT: {unit}"))
        return
    while units := unchecked_units(ledger):
        run_unit(chain, design, ledger, units[0], max_rounds, check)
    gap = ledger_gap(ledger)
    if gap:
        chain.stop(EXIT_FAILED, f"Every unit is ticked, but the ledger still has {gap}: {ledger}")


def require_files_supplement(chain: Chain, ledger: Path) -> None:
    """Write the files supplement verify reads from the unit proof files; stops the chain with 1 when they list no
    changed file. A dry run writes nothing."""
    if not chain.options.dry_run and not write_files_supplement(ledger):
        chain.stop(EXIT_FAILED, f"No unit proof file lists the files changed, so verify has nothing to review. Each "
                                f"unit lists them under '## Files changed' in its proof file: {ledger}")


def run_direct(chain: Chain, design: Path, ledger: Path, *, start_at: str, keep_source: bool,
               max_rounds: int) -> None:
    """One design's chain from *start_at*: implement, verify (implementing again on INCOMPLETE), absorb.
    Returns when the design is absorbed; any failure stops the whole chain."""
    first = STEPS.index(start_at)
    if first <= 0:
        implement(chain, design, ledger, max_rounds)
    if first <= 1:
        prompt = (f"/verify-implementation\nDESIGN: {design}\nTASKS: none\n"
                  f"FILES: the files listed in {files_supplement(ledger)}")

        def implement_gaps(report: object) -> None:
            implement(chain, design, ledger, max_rounds, str(report))
            require_files_supplement(chain, ledger)

        require_files_supplement(chain, ledger)
        chain.verify_design(prompt, design, implement_gaps, max_rounds)
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
    parser.add_argument("--count", type=int, default=None,
                        help="How many designs to take from the design folder, first by name. Default: 10.")
    parser.add_argument("--all", action="store_true",
                        help="Implement every design of the folder given as --design (default: <workspace>/design), "
                             "with no count cap. Not with --count.")
    parser.add_argument("--start-at", choices=STEPS, default=STEPS[0],
                        help="The step to start at, to resume after answering a question.")
    parser.add_argument("--keep-source", action="store_true", help="Pass KEEP SOURCE: true to /absorb-design.")
    add_chain_arguments(parser, resume=True)
    parser.add_argument("--max-rounds", type=int, default=DEFAULT_MAX_ROUNDS,
                        help="How many sessions one unit, and how many verify runs, may take before the "
                             "chain gives up. Default: 3.")
    parser.add_argument("--self-test", action="store_true",
                        help="Run only the chain checks, the ledger and dry-run checks and the wrapper seam checks.")
    parser.set_defaults(debug=False)
    return parser


def _check_the_ledger_gap_is_read_from_the_ledger() -> None:
    with TemporaryDirectory() as raw:
        ledger = Path(raw) / "ledger.md"
        cases = (
            ("| U01 | change | [ ] |\n", "unchecked units"),
            ("| U01 | change | [x] |\n", NO_CHANGED_FILES),
            ("### U01 — change\n- state: [ ]\n", NO_UNITS),
        )
        assert ledger_gap(ledger) == NO_LEDGER
        assert unchecked_units(ledger) == []
        for text, gap in cases:
            write_files(ledger.parent, {ledger.name: text})
            assert ledger_gap(ledger) == gap, (text, ledger_gap(ledger))
        # The files changed are read from the unit proof files, never from the ledger.
        write_files(ledger.parent, {ledger.name: "| U01 | change | [x] |\n\n## Files changed\n- a.py\n"})
        assert ledger_gap(ledger) == NO_CHANGED_FILES
        write_files(proof_dir(ledger), {"U01.md": "## Files changed\n- a.py\n"})
        assert ledger_gap(ledger) == ""
        write_files(ledger.parent, {ledger.name: (
            "| id | change | acceptance | state |\n|---|---|---|---|\n"
            "| U01 | a | no `[ ]` left | [x] `test.ps1 pkg` → pass: 3 (a | b) |\n"
            "| U02 | b | c | [ ] |\n| U03 | d | e | [ ] |\n")})
        assert unchecked_units(ledger) == ["U02", "U03"], unchecked_units(ledger)
        assert ledger_units(ledger) == ["U01", "U02", "U03"], ledger_units(ledger)


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


def _check_a_session_is_told_to_shrink_an_over_limit_ledger() -> None:
    assert limit_options([]) == []
    option = limit_options(["the ledger is 63450 bytes (max 24000)", "line 9: a table cell holds 2253 chars"])
    assert len(option) == 1 and option[0].startswith("LEDGER LIMITS EXCEEDED: the ledger is 63450 bytes"), option
    prompt = implement_prompt(Path("d.md"), Path("l.md"), "UNIT: U02", *option)
    assert prompt.splitlines()[-2:] == ["UNIT: U02", option[0]], prompt


def _check_designs_are_selected_by_name_and_count() -> None:
    with TemporaryDirectory() as raw:
        workspace = Path(raw)
        folder = workspace / "design"
        write_files(folder, {"020-b.md": "b\n", "010-a.md": "a\n", "030-c.md": "c\n", "notes.txt": "x\n"})
        assert select_designs("", 2, "implement", workspace) == [folder / "010-a.md", folder / "020-b.md"]
        assert select_designs("x.md", 2, "verify", workspace) == [Path("x.md")]
        # -All takes every design of the default folder, or of the folder given, past the default count.
        write_files(folder, {f"{n:03d}-d.md": "d\n" for n in range(100, 100 + DEFAULT_COUNT + 2)})
        everything = select_designs("", None, "implement", workspace, everything=True)
        assert len(everything) == DEFAULT_COUNT + 2 + 3, everything
        assert len(select_designs("", None, "implement", workspace)) == DEFAULT_COUNT
        other = workspace / "other"
        write_files(other, {"b.md": "b\n", "a.md": "a\n"})
        assert select_designs(str(other), None, "implement", workspace, everything=True) == [other / "a.md",
                                                                                              other / "b.md"]
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            assert chain_exit_code(lambda: select_designs("", 0, "implement", workspace)) == EXIT_FAILED
            assert chain_exit_code(lambda: select_designs("", 2, "verify", workspace)) == EXIT_FAILED
            assert chain_exit_code(lambda: select_designs("", 2, "implement", workspace / "none")) == EXIT_FAILED
            assert chain_exit_code(lambda: select_designs("", 2, "implement", workspace, everything=True)) == EXIT_FAILED
            assert chain_exit_code(lambda: select_designs(str(folder / "010-a.md"), None, "implement", workspace,
                                                          everything=True)) == EXIT_FAILED
            assert chain_exit_code(lambda: select_designs("", None, "verify", workspace, everything=True)) == EXIT_FAILED
    assert len(printed.getvalue().splitlines()) == 6, printed.getvalue()


def _dry_run_lines(workspace: Path, design: Path) -> list[str]:
    chain = Chain(ChainOptions(workspace=workspace, dry_run=True, auto_compact_window=0), CLAUDE)
    printed = io.StringIO()
    with contextlib.redirect_stdout(printed):
        code = chain_exit_code(lambda: run_designs(chain, [design], start_at="implement", keep_source=False,
                                                   max_rounds=DEFAULT_MAX_ROUNDS, dry_run=True,
                                                   workspace=workspace))
    assert code == EXIT_DONE, code
    return printed.getvalue().splitlines()


def _check_a_plugin_load_failure_stops_before_the_unit_session() -> None:
    with TemporaryDirectory() as raw:
        workspace = Path(raw)
        ledger = workspace / "ledger.md"
        write_files(workspace, {ledger.name: "| U01 | a | [ ] |\n"})
        chain = Chain(ChainOptions(workspace=workspace, dry_run=False, auto_compact_window=0), CLAUDE)
        failure = "PluginError: Failed to load 'python' from datrix.languages\nKeyError: 'email_local_part'"
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            code = chain_exit_code(lambda: run_unit(chain, workspace / "d.md", ledger, "U01", 1, lambda: failure))
            assert code == EXIT_FAILED, code
            # implement runs the same check before the unit it starts with.
            code = chain_exit_code(lambda: implement(chain, workspace / "d.md", ledger, 1, check=lambda: failure))
            assert code == EXIT_FAILED, code
            # A ledger with every unit ticked but no changed file in any proof file is not done: no session is
            # left to complete it.
            write_files(workspace, {ledger.name: "| U01 | a | [x] |\n"})
            code = chain_exit_code(lambda: implement(chain, workspace / "d.md", ledger, 1, check=lambda: failure))
            assert code == EXIT_FAILED, code
            # A ledger whose units are not table rows is refused, never read as every unit done.
            write_files(workspace, {ledger.name: "### U01 — a\n- state: [ ]\n"})
            code = chain_exit_code(lambda: implement(chain, workspace / "d.md", ledger, 1, check=lambda: failure))
            assert code == EXIT_FAILED, code
    text = printed.getvalue()
    assert "so unit U01 would start on a broken test bed" in text, text
    assert f"Every unit is ticked, but the ledger still has {NO_CHANGED_FILES}" in text, text
    assert "The ledger holds no unit row this script can read" in text, text
    assert text.count("Every unit is ticked") == 1, text
    assert text.count("KeyError: 'email_local_part'") == 2, text
    assert "=== step" not in text, text


def _check_the_plugin_load_error_is_the_tail_of_a_fresh_interpreter_failure() -> None:
    assert plugin_load_error("pass\n") == ""
    error = plugin_load_error("import sys\nprint('noise')\nraise KeyError('email_local_part')\n")
    assert error.splitlines()[-1] == "KeyError: 'email_local_part'", error
    assert len(error.splitlines()) <= PLUGIN_LOAD_TAIL_LINES, error
    assert compile(PLUGIN_LOAD_SCRIPT, "<plugin-load>", "exec") is not None


def _check_a_dry_run_prints_the_implement_sessions_verify_and_absorb() -> None:
    with TemporaryDirectory() as raw:
        workspace = Path(raw)
        design = workspace / "d.md"
        write_files(workspace, {design.name: "# d\n"})
        ledger = ledger_path(workspace, design)
        proof = workspace / ".tmp" / "verify-proven-d.md"
        head = ["", "##### design 1 of 1: d.md"]
        tail = ["", "=== step {n}-verify ===", "/verify-implementation", f"DESIGN: {design}", "TASKS: none",
                f"FILES: the files listed in {files_supplement(ledger)}",
                "", "=== step {m}-absorb ===", "/absorb-design", f"DOCUMENT: {design}", f"VERIFIED: {proof}"]

        def session(number: int, name: str, option: str) -> list[str]:
            return ["", f"=== step {number:02d}-{name} ===", "/implement-design-direct", f"DOCUMENT: {design}",
                    f"LEDGER: {ledger}", option]

        # No ledger: only the plan is known, since the units are the plan's to write.
        no_ledger = _dry_run_lines(workspace, design)
        assert no_ledger == [*head, *session(1, "plan", "STOP AFTER: plan"),
                             *(line.format(n="02", m="03") for line in tail)], no_ledger
        # A ledger with units: one session per unchecked unit.
        write_files(ledger.parent, {ledger.name: "| U01 | a | [x] |\n| U02 | b | [ ] |\n| U03 | c | [ ] |\n"})
        with_ledger = _dry_run_lines(workspace, design)
        assert with_ledger == [*head, *session(1, "unit-U02", "UNIT: U02"), *session(2, "unit-U03", "UNIT: U03"),
                               *(line.format(n="03", m="04") for line in tail)], with_ledger


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        checks = [*CHAIN_CHECKS, *LEDGER_CHECKS, _check_a_session_is_told_to_shrink_an_over_limit_ledger,
                  _check_designs_are_selected_by_name_and_count,
                  _check_the_ledger_gap_is_read_from_the_ledger,
                  _check_a_missing_design_or_ledger_stops_before_any_step,
                  _check_a_plugin_load_failure_stops_before_the_unit_session,
                  _check_the_plugin_load_error_is_the_tail_of_a_fresh_interpreter_failure,
                  _check_a_dry_run_prints_the_implement_sessions_verify_and_absorb]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=SKILL_SCRIPTS_DIR)

    def body() -> NoReturn:
        designs = select_designs(args.design, args.count, args.start_at, WORKSPACE_DIR, everything=args.all)
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
