"""Author a package's diagnostics fixtures from the diagnostic catalog, and inventory what the tests need.

The module behind ``dev/fixture-author.ps1`` (and its ``.sh`` twin). It has four kinds.

``needs`` inventories every workspace package holding ``tests/`` (or the one ``--package`` names):
the inputs each test module reads, found statically, and per test function the declarations its
assertions depend on, read by a local model, written to ``.tmp/fixture-author/needs.json`` with a
summary per package and per block family (``datrix_scripts.dev.fixture_author.needs_command``).
Exit 0 written, 1 a module found is not inventoried (nothing is written), a tree reader moved or a
test module cannot be parsed, 2 usage error or a tree the inventory reads is missing, 3 no local
model can read (nothing is written).

``library`` drafts the shared fixture corpus to hold what ``needs.json`` needs
(``datrix_scripts.dev.fixture_author.library``): per block family a local model writes or extends
``services/<family>.dtrx`` and its owner configs, and per new entry its system, round by round, each round
checked by analyzing every entry under every profile it runs (needed − provided = ∅). A draft holding a
secret-looking literal is queued and never written; a unit still failing after the last round is written to
``.tmp/fixture-author/queue/library-<unit>.md``; renames of colliding needs go to
``.tmp/fixture-author/renames.json``. Exit 0 every unit landed or was provided, 1 a unit was queued or the
inventory cannot be read, 2 usage error (``needs.json`` missing), 3 no local model can draft (nothing is
written).

``repoint`` rewrites the test modules ``needs.json`` lists for ``--package`` so their tests read the shared
corpus (``datrix_scripts.dev.fixture_author.repoint``): per module a local model is given the module, its
needs, the corpus entry that provides them and ``renames.json``; a rewrite is kept only when every test and
assertion stays, the module reads no input but a ``// @local`` one, a module holding a shared test reads its
corpus entry, and ``test.ps1 -Specific`` over it passes,
else it is written back byte for byte from ``.tmp/fixture-author/undo/`` and, after the last round, queued
in ``.tmp/fixture-author/queue/repoint-<package>--<module>.md``. Exit 0 inventoried − rewritten − local is
empty, 1 a module is not done or the inventory cannot be read, 2 usage error (no ``--package``, a
diagnostics switch, ``needs.json`` missing), 3 no local model can rewrite.

``repoint --prune`` deletes the fixture files of ``--package`` that nothing reads any more
(``datrix_scripts.dev.fixture_author.prune``), refused while the package's queue holds a module: a file
needs discovery names, a directory a module reads whole, the diagnostics harness tree and what a kept file
reaches are kept; a deletion leaving a model with no contract sample, or changing the package's semantic
baseline other than by the deleted keys leaving and the corpus keys arriving, refuses the run and every
file is written back. An accepted run regenerates the package's semantic manifest and runs
``fixture-budget-gate.ps1 -UpdateBaseline``. Exit 0 pruned and banked, 1 refused or the baseline not
tightened, 2 usage error.

``diagnostics`` authors the area projects under a package's ``tests/fixtures/diagnostics/``. It loads
the package's case session, reads its needs from the catalog, plans its areas, and acts on them
(``datrix_scripts.dev.fixture_author.diagnostics`` holds the rules):

* with no action flag it drafts each planned area not on disk (or the one ``--area`` names) with a
  local model, round by round, each round verified by one analysis; a variant still failing after
  the last round is written to the queue ``.tmp/fixture-author/queue/<area>.md`` for a person to
  finish (``datrix_scripts.dev.fixture_author.drafting``). An area on disk is never drafted over;
* ``--plan`` prints the needs and each planned area with its variants;
* ``--scaffold`` copies the corpus's system configuration and datasource templates into each
  project root that lacks them (the diagnostics directory, and each seeded area's directory);
* ``--verify`` analyzes each planned area on disk (or the one ``--area`` names) as its
  whole-analysis case does and prints what it reports and does not annotate (a cascade) and what it
  annotates and does not report (not provoked).

Usage:
    python -m datrix_scripts.dev.fixture_author.cli --kind diagnostics --package <name> [--area <a>]
    python -m datrix_scripts.dev.fixture_author.cli --kind diagnostics --package <name> --plan [--area <a>]
    python -m datrix_scripts.dev.fixture_author.cli --kind diagnostics --package <name> --scaffold [--area <a>]
    python -m datrix_scripts.dev.fixture_author.cli --kind diagnostics --package <name> --verify [--area <a>]
    python -m datrix_scripts.dev.fixture_author.cli --kind needs [--package <name>]
    python -m datrix_scripts.dev.fixture_author.cli --kind library
    python -m datrix_scripts.dev.fixture_author.cli --kind repoint --package <name>
    python -m datrix_scripts.dev.fixture_author.cli --kind repoint --package <name> --prune
    python -m datrix_scripts.dev.fixture_author.cli --self-test

Exit codes of ``diagnostics``: 0 done (every drafted variant landed; every verified area reports exactly what it
annotates), 1 a variant was queued, an area failed verification or the package's state refuses the
run, 2 usage error, 3 no local model can draft (nothing is written).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Final

from datrix_scripts.framework_repos import workspace_package_dirs
from datrix_scripts.gate_harness import WRAPPER_DEBUG_FLAG, UsageError
from datrix_scripts.local_llm import LocalLlmSettings, add_wrapper_llm_arguments, wrapper_llm_settings
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.test.wrappers import DEV_SCRIPTS_DIR, module_main, run_self_test

MODULE: Final = "datrix_scripts.dev.fixture_author.cli"
WRAPPER: Final = "fixture-author"
#: The fixture kinds the tool authors.
DIAGNOSTICS_KIND: Final = "diagnostics"
#: The inventory of what the packages' tests read and need: it authors nothing.
NEEDS_KIND: Final = "needs"
#: The shared fixture corpus drafted to hold what the inventory needs.
LIBRARY_KIND: Final = "library"
#: A package's test modules rewritten to read the shared fixture corpus.
REPOINT_KIND: Final = "repoint"
KINDS: Final[tuple[str, ...]] = (DIAGNOSTICS_KIND, LIBRARY_KIND, NEEDS_KIND, REPOINT_KIND)
#: The options only ``diagnostics`` reads.
DIAGNOSTICS_OPTIONS: Final[tuple[str, ...]] = ("area", "plan", "scaffold", "verify")
#: How long one draft request may take on a ready model, in seconds.
LLM_TIMEOUT_SECONDS: Final = 300


def build_parser() -> argparse.ArgumentParser:
    """The options of ``dev/fixture-author.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        prog=WRAPPER, description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False
    )
    parser.add_argument("--kind", default="", help=f"The fixtures to author or inventory: one of {list(KINDS)}.")
    parser.add_argument(
        "--package",
        default="",
        help=f"The package directory name (e.g. datrix-semantic); required by {DIAGNOSTICS_KIND} and "
        f"{REPOINT_KIND}, default every package holding tests/ for {NEEDS_KIND}, refused by {LIBRARY_KIND}.",
    )
    parser.add_argument("--area", default="", help="One planned area; default every planned area.")
    parser.add_argument("--plan", action="store_true", help="Print the needs and the planned areas.")
    parser.add_argument("--scaffold", action="store_true", help="Copy the corpus scaffold into each project root lacking it.")
    parser.add_argument("--verify", action="store_true", help="Compare each area's reported and annotated variants.")
    parser.add_argument(
        "--prune",
        action="store_true",
        help=f"With {REPOINT_KIND}: delete the package's fixture files nothing reads, once its queue is empty.",
    )
    add_wrapper_llm_arguments(parser, timeout_seconds=LLM_TIMEOUT_SECONDS)
    parser.add_argument(WRAPPER_DEBUG_FLAG, dest="debug", action="store_true", help="Debug logging.")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run only the self-test: needs, area plan, scaffold, verification, drafting, the corpus "
        "library plan, check and drafting, and repointing and pruning a planted package, on planted inputs.",
    )
    parser.set_defaults(debug=False)
    return parser


def package_root(name: str, workspace: Path = WORKSPACE_DIR) -> Path:
    """The workspace package *name*, which carries a case session.

    Raises:
        UsageError: *name* is empty or names no such package.
    """
    from datrix_scripts.dev.fixture_author.diagnostics import has_case_inputs

    roots = {root.name: root for root in workspace_package_dirs(workspace) if has_case_inputs(root)}
    if name not in roots:
        raise UsageError(
            f"-Package {name!r} is no workspace package carrying a case session (tests/case_inputs.py); "
            f"the packages that do: {sorted(roots)}."
        )
    return roots[name]


def _action(args: argparse.Namespace) -> str:
    chosen = [flag for flag in ("plan", "scaffold", "verify") if getattr(args, flag)]
    if len(chosen) > 1:
        raise UsageError(f"Give at most one of -Plan, -Scaffold, -Verify (given: {chosen}); none drafts.")
    if chosen:
        return chosen[0]
    from datrix_scripts.dev.fixture_author.diagnostics import DRAFT_ACTION

    return DRAFT_ACTION


def _refuse_diagnostics_options(args: argparse.Namespace) -> None:
    given = [f"-{option.title()}" for option in DIAGNOSTICS_OPTIONS if getattr(args, option)]
    if given:
        raise UsageError(f"{args.kind} takes no {', '.join(given)}: only {DIAGNOSTICS_KIND} does.")


def _run_repoint(args: argparse.Namespace, settings: LocalLlmSettings) -> int:
    _refuse_diagnostics_options(args)
    if args.prune:
        from datrix_scripts.dev.fixture_author.prune import run_prune_command

        return run_prune_command(args.package)
    from datrix_scripts.dev.fixture_author.repoint import run_repoint_command

    return run_repoint_command(args.package, settings)


def _run(args: argparse.Namespace) -> int:
    # The package sessions import the framework; --help and usage errors stay fast without them.
    if args.self_test:
        from datrix_scripts.dev.fixture_author.self_checks import CHECKS

        return run_self_test(CHECKS, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=DEV_SCRIPTS_DIR)
    if args.kind not in KINDS:
        raise UsageError(f"-Kind {args.kind!r} is not a fixture kind the tool knows; expected one of {list(KINDS)}.")
    if args.prune and args.kind != REPOINT_KIND:
        raise UsageError(f"-Prune belongs to {REPOINT_KIND} (it deletes what a repointed package no longer reads), "
                         f"not to {args.kind}.")
    settings = replace(wrapper_llm_settings(args), caller=WRAPPER)
    if args.kind == LIBRARY_KIND:
        given = [f"-{option.title()}" for option in ("package", *DIAGNOSTICS_OPTIONS) if getattr(args, option)]
        if given:
            raise UsageError(f"{LIBRARY_KIND} takes no {', '.join(given)}: it drafts the corpus for every package.")
        from datrix_scripts.dev.fixture_author.library import run_library_command

        return run_library_command(settings)
    if args.kind == REPOINT_KIND:
        return _run_repoint(args, settings)
    if args.kind == NEEDS_KIND:
        _refuse_diagnostics_options(args)
        from datrix_scripts.dev.fixture_author.needs_command import run_needs_command

        return run_needs_command(args.package, settings)
    if not args.package:
        raise UsageError("-Package is required: the package whose fixtures are authored (e.g. datrix-semantic).")
    action = _action(args)
    from datrix_scripts.dev.fixture_author.diagnostics import run_diagnostics

    return run_diagnostics(package_root(args.package), action, args.area, settings)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


__all__ = [
    "DIAGNOSTICS_KIND",
    "DIAGNOSTICS_OPTIONS",
    "KINDS",
    "LIBRARY_KIND",
    "MODULE",
    "NEEDS_KIND",
    "REPOINT_KIND",
    "WRAPPER",
    "build_parser",
    "main",
    "package_root",
]


if __name__ == "__main__":
    sys.exit(main())
