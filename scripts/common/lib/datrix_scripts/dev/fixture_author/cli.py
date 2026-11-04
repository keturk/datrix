"""Author a package's diagnostics fixtures from the diagnostic catalog.

The module behind ``dev/fixture-author.ps1`` (and its ``.sh`` twin). It has one kind.

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
from datrix_scripts.local_llm import add_wrapper_llm_arguments, wrapper_llm_settings
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.test.wrappers import DEV_SCRIPTS_DIR, module_main, run_self_test

MODULE: Final = "datrix_scripts.dev.fixture_author.cli"
WRAPPER: Final = "fixture-author"
#: The fixture kinds the tool authors.
DIAGNOSTICS_KIND: Final = "diagnostics"
KINDS: Final[tuple[str, ...]] = (DIAGNOSTICS_KIND,)
#: How long one draft request may take on a ready model, in seconds.
LLM_TIMEOUT_SECONDS: Final = 300


def build_parser() -> argparse.ArgumentParser:
    """The options of ``dev/fixture-author.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        prog=WRAPPER, description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False
    )
    parser.add_argument("--kind", default="", help=f"The fixtures to author: one of {list(KINDS)}.")
    parser.add_argument(
        "--package", default="", help="The package directory name (e.g. datrix-semantic); required."
    )
    parser.add_argument("--area", default="", help="One planned area; default every planned area.")
    parser.add_argument("--plan", action="store_true", help="Print the needs and the planned areas.")
    parser.add_argument("--scaffold", action="store_true", help="Copy the corpus scaffold into each project root lacking it.")
    parser.add_argument("--verify", action="store_true", help="Compare each area's reported and annotated variants.")
    add_wrapper_llm_arguments(parser, timeout_seconds=LLM_TIMEOUT_SECONDS)
    parser.add_argument(WRAPPER_DEBUG_FLAG, dest="debug", action="store_true", help="Debug logging.")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run only the self-test: needs, area plan, scaffold, verification and drafting, on planted inputs.",
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


def _run(args: argparse.Namespace) -> int:
    # The package sessions import the framework; --help and usage errors stay fast without them.
    if args.self_test:
        from datrix_scripts.dev.fixture_author.self_checks import CHECKS

        return run_self_test(CHECKS, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=DEV_SCRIPTS_DIR)
    if args.kind not in KINDS:
        raise UsageError(f"-Kind {args.kind!r} is not a fixture kind the tool knows; expected one of {list(KINDS)}.")
    settings = replace(wrapper_llm_settings(args), caller=WRAPPER)
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
    "KINDS",
    "MODULE",
    "WRAPPER",
    "build_parser",
    "main",
    "package_root",
]


if __name__ == "__main__":
    sys.exit(main())
