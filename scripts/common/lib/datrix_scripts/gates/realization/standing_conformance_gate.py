"""The standing conformance-spec corpus gate: every committed spec under ``scripts/config/conformance-specs/``.

Only the top-level ``*.json`` files of that directory are specs; fixture subdirectories such as
``_fixtures/`` are never swept. The runner is ``conformance_gate``: its self-test runs first, as on
every invocation of that gate, and a failure aborts with exit 2 before any spec is trusted. Every spec
is then checked for a ``target`` or ``negative_control`` written as an absolute path (a committed spec
addresses its trees relative to itself), and one such field, an absent corpus or an empty one refuses
the whole sweep with exit 2. Each spec writes its own ledger under
``<workspace>/.test-output/conformance/``.

This module is what ``gates/realization/standing-conformance-gate.ps1`` (and its ``.sh`` twin) runs,
in gate mode (``datrix_scripts.gate_log.run_as_gate``): the last line is the
``[GATE] standing-conformance PASSED|FAILED exit=<n> log=<path>`` verdict.

Exit codes: 0 = every spec passes, 1 = any spec fails, 2 = a refused corpus, a malformed spec or a
self-test failure.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from typing import Final

from datrix_scripts.gate_harness import EXIT_USAGE, EXIT_VIOLATION, WRAPPER_DEBUG_FLAG
from datrix_scripts.gate_log import gate_child, run_as_gate
from datrix_scripts.gates.realization.conformance_gate import gate_self_test, run_corpus, runner_proves_its_teeth
from datrix_scripts.paths import CONFIG_DIR

GATE: Final = "standing-conformance"
MODULE: Final = "datrix_scripts.gates.realization.standing_conformance_gate"
WRAPPER: Final = "standing-conformance-gate"
#: The committed corpus: every top-level ``*.json`` here is a spec.
SPEC_DIR: Final = CONFIG_DIR / "conformance-specs"


def build_parser() -> argparse.ArgumentParser:
    """The gate's options: exactly the wrapper's parameters, spelled exactly."""
    parser = argparse.ArgumentParser(
        prog=WRAPPER,
        description="Run every committed conformance spec under scripts/config/conformance-specs/.",
        allow_abbrev=False,
    )
    parser.add_argument(WRAPPER_DEBUG_FLAG, dest="debug", action="store_true", help="Enable DEBUG logging.")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run only the runner's self-test (every assertion type detects and passes; an empty corpus "
        "and a rooted spec field are refused) and run no spec.",
    )
    return parser


def _run(args: argparse.Namespace) -> int:
    from datrix_scripts.test.test import ensure_packages
    from datrix_scripts.venv import require_packages

    if not ensure_packages(os.environ, require_packages):
        return EXIT_VIOLATION
    if args.self_test:
        return gate_self_test(wrapper=WRAPPER, module=MODULE, parser=build_parser())
    if not runner_proves_its_teeth("corpus"):
        return EXIT_USAGE
    return run_corpus(SPEC_DIR)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point: the gate in gate mode (a claimed log and the verdict line)."""
    return run_as_gate(GATE, MODULE, gate_child(build_parser, _run), argv)


if __name__ == "__main__":
    sys.exit(main())
