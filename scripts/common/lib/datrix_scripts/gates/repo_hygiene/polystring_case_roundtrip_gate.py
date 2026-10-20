"""The PolyString case round-trip gate: a name never goes ``str()`` -> ``to_*_case()``.

The scan and its self-test are ``datrix_scripts.polystring_case_roundtrip``'s (shared with
``git/commit-and-push.ps1``, which runs the commit-path form over pending files; see that module for the
shapes it refuses and why the gate is held at a hard zero). This module is what
``gates/repo-hygiene/polystring-case-roundtrip-gate.ps1`` (and its ``.sh`` twin) runs, in gate mode
(``datrix_scripts.gate_log.run_as_gate``): the last line is the
``[GATE] polystring-case-roundtrip PASSED|FAILED exit=<n> log=<path>`` verdict.

Exit codes: 0 = zero round trips in every scanned file (or the self-test passed), 1 = at least one round
trip, or the self-test failed, 2 = usage error, or a scanned file could not be parsed.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import Final

from datrix_scripts.gate_harness import EXIT_USAGE, EXIT_VIOLATION, WRAPPER_DEBUG_FLAG, print_command
from datrix_scripts.gate_log import gate_child, run_as_gate
from datrix_scripts.polystring_case_roundtrip import (
    DATRIX_ROOT,
    PolyStringGateError,
    resolve_repos,
    run_scan,
    self_test,
)
from datrix_scripts.test import wrappers

GATE: Final = "polystring-case-roundtrip"
MODULE: Final = "datrix_scripts.gates.repo_hygiene.polystring_case_roundtrip_gate"
WRAPPER: Final = "polystring-case-roundtrip-gate"
_REPO_SEPARATOR: Final = ","


def build_parser() -> argparse.ArgumentParser:
    """The options of ``gates/repo-hygiene/polystring-case-roundtrip-gate.ps1``: one per wrapper
    parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        prog=WRAPPER,
        description="Fail on any datrix_common.utils.text case function called on a str()-converted, "
        "str()-bound, nested-cased or simple-name-extracted argument.",
        allow_abbrev=False,
    )
    parser.add_argument(
        "--repo",
        action="append",
        default=None,
        help="Limit the scan to these repo names (repeatable, or comma-separated). Default: every framework repo.",
    )
    parser.add_argument(
        "--self-test", action="store_true", help="Run only the non-vacuity self-test and the wrapper seam check."
    )
    parser.add_argument(
        "--pending-only",
        action="store_true",
        help="Scan only the files a `git add -A` would stage in each repo (the commit-path form).",
    )
    parser.add_argument(
        WRAPPER_DEBUG_FLAG, dest="debug", action="store_true", help="Log at DEBUG level and print the command first."
    )
    return parser


def requested_repos(values: Sequence[str] | None) -> list[str] | None:
    """The repo names *values* request, each split on commas (``powershell -File`` binds ``a,b`` as one
    string, and a repo name never contains a comma); None when no name is requested."""
    names = [name.strip() for value in values or () for name in value.split(_REPO_SEPARATOR) if name.strip()]
    return names or None


def _run(args: argparse.Namespace) -> int:
    """Run the gate; returns 0 (clean / self-test passed), 1 (a round trip, or the self-test failed),
    2 (usage error, or an unparseable file)."""
    if args.debug:
        print_command()
    failures = self_test()
    if failures:
        print("POLYSTRING CASE ROUND-TRIP GATE CANNOT BE TRUSTED: non-vacuity self-test failed.")
        for failure in failures:
            print(f"  {failure}")
        return EXIT_VIOLATION
    print("Self-test passed: the scanner still detects every planted round-trip shape.")

    if args.self_test:
        return wrappers.run_self_test(
            [_check_requested_repos_split_on_commas],
            wrapper=WRAPPER,
            module=MODULE,
            parser=build_parser(),
            folder=wrappers.REPO_HYGIENE_GATES_DIR,
        )
    try:
        repos = resolve_repos(DATRIX_ROOT.parent, requested_repos(args.repo))
        return run_scan(repos, args.pending_only)
    except PolyStringGateError as exc:
        print(f"POLYSTRING CASE ROUND-TRIP GATE CANNOT RUN: {exc}", file=sys.stderr)
        return EXIT_USAGE


def _check_requested_repos_split_on_commas() -> None:
    cases: tuple[tuple[list[str] | None, list[str] | None], ...] = (
        (None, None),
        (["datrix-codegen-aws"], ["datrix-codegen-aws"]),
        (["datrix,datrix-common"], ["datrix", "datrix-common"]),
        (["datrix, ", "datrix-cli"], ["datrix", "datrix-cli"]),
        ([" , "], None),
    )
    for values, expected in cases:
        got = requested_repos(values)
        assert got == expected, f"requested_repos({values!r}) is {got!r}, expected {expected!r}"


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point: the gate in gate mode (a claimed log and the verdict line)."""
    return run_as_gate(GATE, MODULE, gate_child(build_parser, _run), argv)


if __name__ == "__main__":
    sys.exit(main())
