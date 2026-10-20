"""The Python lint-correctness gate: pyflakes and top-level blank-line findings are a hard zero.

The lint passes, the tree discovery and the non-vacuity self-test are
``datrix_scripts.python_lint_correctness``'s (shared with ``git/commit-and-push.ps1``, which lints the
pending files of every dirty repo; see that module for the rule selections and why each is held at zero).
This module is what ``gates/repo-hygiene/python-lint-correctness-gate.ps1`` (and its ``.sh`` twin) runs,
in gate mode (``datrix_scripts.gate_log.run_as_gate``): the last line is the
``[GATE] python-lint-correctness PASSED|FAILED exit=<n> log=<path>`` verdict.

Exit codes: 0 = zero findings in every scanned tree (or the self-test passed), 1 = at least one finding,
or the self-test failed, 2 = usage error, or ruff could not run.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import Final

from datrix_scripts.gate_harness import EXIT_USAGE, EXIT_VIOLATION, WRAPPER_DEBUG_FLAG, print_command
from datrix_scripts.gate_log import gate_child, run_as_gate
from datrix_scripts.python_lint_correctness import DATRIX_ROOT, LintGateError, run_scan, self_test
from datrix_scripts.test import wrappers

GATE: Final = "python-lint-correctness"
MODULE: Final = "datrix_scripts.gates.repo_hygiene.python_lint_correctness_gate"
WRAPPER: Final = "python-lint-correctness-gate"


def build_parser() -> argparse.ArgumentParser:
    """The options of ``gates/repo-hygiene/python-lint-correctness-gate.ps1``: one per wrapper parameter,
    spelled exactly."""
    parser = argparse.ArgumentParser(
        prog=WRAPPER,
        description="Fail on any pyflakes (ruff F) or top-level blank-line (ruff E302/E305) finding in the "
        "src/ and tests/ trees of every workspace package and the showcase repo's scripts/.",
        allow_abbrev=False,
    )
    parser.add_argument(
        "--self-test", action="store_true", help="Run only the non-vacuity self-test and the wrapper seam check."
    )
    parser.add_argument(
        WRAPPER_DEBUG_FLAG, dest="debug", action="store_true", help="Log at DEBUG level and print the command first."
    )
    return parser


def _run(args: argparse.Namespace) -> int:
    """Run the gate; returns 0 (clean / self-test passed), 1 (a finding, or the self-test failed),
    2 (usage error, or ruff could not run)."""
    if args.debug:
        print_command()
    try:
        failures = self_test(sys.executable)
        if failures:
            print("PYTHON LINT-CORRECTNESS GATE CANNOT BE TRUSTED: non-vacuity self-test failed.")
            for failure in failures:
                print(f"  {failure}")
            return EXIT_VIOLATION
        print(
            "Self-test passed: planted F401 + F821 and E302 + E305 seen, clean passes, "
            "per-file-ignores honoured."
        )
        if args.self_test:
            return wrappers.run_self_test(
                [], wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=wrappers.REPO_HYGIENE_GATES_DIR
            )
        return run_scan(sys.executable, DATRIX_ROOT.parent)
    except LintGateError as exc:
        print(f"PYTHON LINT-CORRECTNESS GATE CANNOT RUN: {exc}", file=sys.stderr)
        return EXIT_USAGE


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point: the gate in gate mode (a claimed log and the verdict line)."""
    return run_as_gate(GATE, MODULE, gate_child(build_parser, _run), argv)


if __name__ == "__main__":
    sys.exit(main())
