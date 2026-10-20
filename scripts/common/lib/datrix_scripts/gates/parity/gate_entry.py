"""The entry point every parity gate module shares.

A parity gate module is the ``argparse`` entry point of a wrapper rendered from
``common/templates/entrypoint.ps1``: its options are exactly the wrapper's parameters, and its
``main`` calls ``datrix_scripts.gate_log.run_as_gate`` itself with ``ParityGate.run`` as the child, so
the run keeps its whole output in a claimed log and ends on the
``[GATE] <gate> PASSED|FAILED exit=<n> log=<path>`` line (the scripts-tree census reads that call in
the module the wrapper names):

    return run_as_gate(GATE, MODULE, gate_child(build_parser, GATE_SPEC.run), argv)

``run_gate`` is that module's run, in the same order for every gate:

1. the package install check (``datrix_scripts.venv.require_packages``) when the gate imports the
   editable installs, exit 1 when it fails;
2. under ``--self-test``, the gate's own non-vacuity self-test and the wrapper seam checks
   (``datrix_scripts.test.wrappers.run_self_test``: the wrapper and its ``.sh`` twin are the
   templates rendered, and the wrapper's parameters are the parser's options);
3. otherwise the non-vacuity self-test before the real comparison is trusted, then the comparison.
"""

from __future__ import annotations

import argparse
import logging
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Final

from datrix_scripts.gate_harness import EXIT_PASS, EXIT_VIOLATION, WRAPPER_DEBUG_FLAG
from datrix_scripts.test import wrappers

logger = logging.getLogger(__name__)

EXIT_OK: Final = 0

#: A gate's own self-test: prints or logs its own lines, returns whether every check held.
SelfTest = Callable[[], bool]
#: The real comparison, given the parsed options; returns the gate's exit code.
GateRun = Callable[[argparse.Namespace], int]


@dataclass(frozen=True)
class ParityGate:
    """One parity gate module's identity and behaviour.

    Attributes:
        gate: The gate name in the verdict line and the log directory (``behaviour-parity``).
        wrapper: The wrapper's file name without ``.ps1`` (``behaviour-parity-gate``).
        module: The dotted module the wrapper runs.
        build_parser: The gate's options, exactly the wrapper's parameters.
        self_test: The gate's non-vacuity self-test.
        compare: The real comparison.
        self_test_failed: The exit code of a failed self-test (the gate's "cannot be trusted" code).
        require_packages: Whether the gate needs the editable installs checked first.
    """

    gate: str
    wrapper: str
    module: str
    build_parser: Callable[[], argparse.ArgumentParser]
    self_test: SelfTest
    compare: GateRun
    self_test_failed: int
    require_packages: bool = True

    def run(self, args: argparse.Namespace) -> int:
        """This gate's run on *args*: the child ``main`` hands to ``run_as_gate``."""
        return run_gate(self, args)


def gate_parser(wrapper: str, description: str) -> argparse.ArgumentParser:
    """A parser carrying the two options every parity wrapper declares, ``-Dbg`` and ``-SelfTest``.

    The gate adds its own options; abbreviations are refused, so no spelling reaches the module
    that a hook reading the command line cannot see.
    """
    parser = argparse.ArgumentParser(prog=wrapper, description=description, allow_abbrev=False)
    parser.add_argument(WRAPPER_DEBUG_FLAG, dest="debug", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run only the non-vacuity self-test and the wrapper seam check; read nothing real",
    )
    return parser


def problems_self_test(run_self_test: Callable[[], Sequence[str]]) -> SelfTest:
    """*run_self_test* (which returns failure descriptions) as a ``SelfTest``, logging each failure."""

    def self_test() -> bool:
        problems = list(run_self_test())
        for problem in problems:
            logger.error("SELF-TEST FAILED: %s", problem)
        return not problems

    return self_test


def run_gate(gate: ParityGate, args: argparse.Namespace) -> int:
    """Run *gate* on *args* (see the module docstring for the order)."""
    from datrix_scripts.test.test import ensure_packages
    from datrix_scripts.venv import require_packages

    if gate.require_packages and not ensure_packages(os.environ, require_packages):
        return EXIT_VIOLATION
    if args.self_test:
        code = wrappers.run_self_test(
            [wrappers.self_test_check(gate.wrapper, gate.self_test)],
            wrapper=gate.wrapper,
            module=gate.module,
            parser=gate.build_parser(),
            folder=wrappers.PARITY_GATES_DIR,
        )
        return EXIT_OK if code == EXIT_PASS else gate.self_test_failed
    if not gate.self_test():
        logger.error("Non-vacuity self-test FAILED; the real comparison cannot be trusted.")
        return gate.self_test_failed
    logger.info("Non-vacuity self-test passed.")
    return gate.compare(args)
