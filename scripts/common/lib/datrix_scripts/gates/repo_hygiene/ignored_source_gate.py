"""The ignored-source gate: a ``.gitignore`` rule may never shadow a publishable file.

The scan, the exemptions and the self-test are ``datrix_scripts.ignored_source``'s (shared with
``git/commit-and-push.ps1``, which runs the same comparison over the repos it is about to commit; see that
module for why git is the oracle). This module is what ``gates/repo-hygiene/ignored-source-gate.ps1`` (and
its ``.sh`` twin) runs, in gate mode (``datrix_scripts.gate_log.run_as_gate``): the last line is the
``[GATE] ignored-source PASSED|FAILED exit=<n> log=<path>`` verdict.

Exit codes: 0 = every unstaged working-tree path is a reviewed exemption (or the self-test passed),
1 = a publishable file is shadowed, or the self-test failed, 2 = usage error, or a missing, malformed or
miscounted exemption file.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from typing import Final

from datrix_scripts.gate_harness import EXIT_USAGE, EXIT_VIOLATION, WRAPPER_DEBUG_FLAG, print_command
from datrix_scripts.gate_log import gate_child, run_as_gate
from datrix_scripts.ignored_source import (
    DATRIX_ROOT,
    IgnoredSourceGateError,
    exemption_path,
    load_exemptions,
    load_temp_dir_segment,
    print_exemptions,
    resolve_repos,
    run_scan,
    self_test,
)
from datrix_scripts.test import wrappers

logger = logging.getLogger(__name__)

GATE: Final = "ignored-source"
MODULE: Final = "datrix_scripts.gates.repo_hygiene.ignored_source_gate"
WRAPPER: Final = "ignored-source-gate"
_CANNOT_RUN: Final = "IGNORED-SOURCE GATE CANNOT RUN"


def build_parser() -> argparse.ArgumentParser:
    """The options of ``gates/repo-hygiene/ignored-source-gate.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        prog=WRAPPER,
        description="Fail when a .gitignore rule shadows a publishable file in a framework repo.",
        allow_abbrev=False,
    )
    parser.add_argument(
        "--repo",
        action="append",
        default=None,
        help="Limit the scan to this repo name (repeatable). Default: every framework repo.",
    )
    parser.add_argument(
        "--self-test", action="store_true", help="Run only the non-vacuity self-test and the wrapper seam check."
    )
    parser.add_argument(
        "--show-exempt", action="store_true", help="Also print every reviewed exemption entry and its written reason."
    )
    parser.add_argument(
        WRAPPER_DEBUG_FLAG, dest="debug", action="store_true", help="Log at DEBUG level and print the command first."
    )
    return parser


def _run(args: argparse.Namespace) -> int:
    """Run the gate; returns 0 (clean / self-test passed), 1 (shadowed file, or the self-test failed),
    2 (usage error, or the exemption file or self-test could not be read or run)."""
    if args.debug:
        print_command()
    try:
        exemptions = load_exemptions(exemption_path(DATRIX_ROOT))
        temp_dir_segment = load_temp_dir_segment(DATRIX_ROOT)
    except IgnoredSourceGateError as exc:
        print(f"{_CANNOT_RUN}: {exc}", file=sys.stderr)
        return EXIT_USAGE
    logger.debug("loaded %d exemption entrie(s)", len(exemptions.entries))
    if args.show_exempt:
        print_exemptions(exemptions)

    try:
        failures = self_test(exemptions, temp_dir_segment)
    except IgnoredSourceGateError as exc:
        print(f"{_CANNOT_RUN}: self-test could not execute: {exc}", file=sys.stderr)
        return EXIT_USAGE
    if failures:
        print("IGNORED-SOURCE GATE CANNOT BE TRUSTED: non-vacuity self-test failed.")
        for failure in failures:
            print(f"  {failure}")
        return EXIT_VIOLATION
    print("Self-test passed: the scanner still detects a planted shadowed source file.")

    if args.self_test:
        return wrappers.run_self_test(
            [], wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=wrappers.REPO_HYGIENE_GATES_DIR
        )
    try:
        repos = resolve_repos(DATRIX_ROOT.parent, args.repo)
        return run_scan(repos, exemptions, temp_dir_segment)
    except IgnoredSourceGateError as exc:
        print(f"{_CANNOT_RUN}: {exc}", file=sys.stderr)
        return EXIT_USAGE


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point: the gate in gate mode (a claimed log and the verdict line)."""
    return run_as_gate(GATE, MODULE, gate_child(build_parser, _run), argv)


if __name__ == "__main__":
    sys.exit(main())
