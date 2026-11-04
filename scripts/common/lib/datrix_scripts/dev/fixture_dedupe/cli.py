"""Keep one copy of each duplicated test fixture: list the plan, prove it and write it.

The module behind ``dev/fixture-dedupe.ps1`` (and its ``.sh`` twin). It builds the plan over the
workspace (``datrix_scripts.dev.fixture_dedupe.plan``) and lists
(``datrix_scripts.dev.fixture_dedupe.listing``):

* each file group -- fixture files of equal normalized content whose references resolve to files that
  are one, recursively -- with the copy that moves to ``<corpus>/shared/<package>/<path>``, the copies
  deleted and the copies kept with their reason;
* each inline literal group -- literals assigned to one name with equal normalized text -- with its
  ``<corpus>/shared/inline/...`` file, the literals rewritten and the literals left for a hand edit;
* the normalized-equal groups their references split, the directories read whole and the walk sites
  that cannot be evaluated, and the packages whose model-contract capture screened the moved ``.dcfg``
  texts;
* each fixture reference rewritten to reach its file's new place once the copies move
  (``datrix_scripts.dev.fixture_dedupe.follow``), and each one that cannot be read back;
* each test-module site reading a copy that leaves, rewritten to ``shared_fixture(...)``, and each one
  refused for a hand edit (``datrix_scripts.dev.fixture_dedupe.sites``).

With ``--dry-run`` that is all: it writes nothing. Without it the plan's write is proven over the planned
tree, written, proven again over the disk with every semantic baseline's drift, and recorded under
``<workspace>/.tmp/fixture-dedupe/`` (``datrix_scripts.dev.fixture_dedupe.write``); a failure once written
puts every file back. It runs no git command.

Usage:
    python -m datrix_scripts.dev.fixture_dedupe.cli [--dry-run] [--base-dir <workspace>]
    python -m datrix_scripts.dev.fixture_dedupe.cli --self-test

Exit codes: 0 the plan is listed (and, without --dry-run, written and proven); 1 a walk site cannot be
evaluated, so the plan cannot prove which copies a directory read needs, a reference whose reader and file
both stay is shadowed by a placed copy, or the write's proof fails (nothing is written, or everything written
is put back); 2 usage error, or a fixture or module that cannot be read or parsed, a missing corpus, a
screened package whose capture cannot run, or a semantic-baseline entry that cannot be analyzed.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import Final

from datrix_testing.corpus import CORPUS_ROOT

from datrix_scripts.dev.fixture_dedupe.listing import dry_run
from datrix_scripts.dev.fixture_dedupe.self_checks import CHECKS
from datrix_scripts.dev.fixture_dedupe.write import write_run
from datrix_scripts.gate_harness import WRAPPER_DEBUG_FLAG
from datrix_scripts.gates.ratchet.fixture_budget_gate import base_dir_option
from datrix_scripts.test.wrappers import DEV_SCRIPTS_DIR, module_main, run_self_test

MODULE: Final = "datrix_scripts.dev.fixture_dedupe.cli"
WRAPPER: Final = "fixture-dedupe"


def build_parser() -> argparse.ArgumentParser:
    """The options of ``dev/fixture-dedupe.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        prog=WRAPPER, description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="List the plan and write nothing (without it: list, prove, write, record)."
    )
    parser.add_argument("--base-dir", default="", help="Workspace root (default: the workspace).")
    parser.add_argument(WRAPPER_DEBUG_FLAG, dest="debug", action="store_true", help="Debug logging.")
    parser.add_argument(
        "--self-test", action="store_true",
        help="Run only the self-test: the dedupe rules over a planted workspace, and the wrapper seam.",
    )
    parser.set_defaults(debug=False)
    return parser


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        return run_self_test(CHECKS, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=DEV_SCRIPTS_DIR)
    if args.dry_run:
        return dry_run(base_dir_option(args.base_dir))
    return write_run(base_dir_option(args.base_dir), CORPUS_ROOT)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
