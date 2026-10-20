"""Gate mode for a gate whose wrapper is rendered from ``common/templates/entrypoint.ps1``.

A gate run keeps its whole output in a log of its own and ends on one verdict line, the seam the
red-run digest hook (``digest-red-test-run.py``) and ``datrix_scripts.skill.implement_finding`` read::

    [GATE] <name> PASSED exit=0 log=<absolute log path>
    [GATE] <name> FAILED exit=<n> log=<absolute log path>

The log is claimed (``datrix_scripts.run_log``) under ``<workspace>/.test-output/gates/<name>/`` as
``<name>-<yyyyMMdd-HHmmss>[-N].log``, so two runs of one gate never share it. A gate module's ``main``
is ``run_as_gate``: the first process claims the log and runs the module again as a child with
``DATRIX_GATE_CHILD`` naming the gate, relays every line the child's process tree writes (stdout and
stderr) to the console and the log, and prints the verdict line last with the child's exit code. A
child that cannot start, or a run interrupted before the child exits, still ends on the verdict line.

This is what ``Invoke-DatrixPythonScript -Gate`` (``common/DatrixPythonScript.psm1``) does for a
wrapper that is not rendered from the template; both write the same log names and the same line.

A gate module whose behaviour is an argparse parser and a run over its parsed arguments hands
``run_as_gate`` ``gate_child(build_parser, run)``: in the child, *run* on the parsed arguments
(``test.wrappers.module_main``), Ctrl-C an exit 130.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Final

from datrix_scripts.gate_harness import EXIT_VIOLATION, install_sigint_handler
from datrix_scripts.logging_utils import ColorCodes, colorize
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.run_log import claim_run_log_file, run_log_base_name, run_log_segment
from datrix_scripts.test.wrappers import ensure_utf8_stdio, module_main

#: Set in the child's environment to the gate's name: that process runs the gate itself.
GATE_CHILD_ENV: Final = "DATRIX_GATE_CHILD"
VERDICT_PREFIX: Final = "[GATE]"
GATE_LOG_FOLDER: Final = "gates"
_OUTPUT_FOLDER: Final = ".test-output"
_PASSED: Final = "PASSED"
_FAILED: Final = "FAILED"
_UTF8: Final = "utf-8"
_REPLACE: Final = "replace"
_LINE_ENDINGS: Final = "\r\n"

GateRun = Callable[[Sequence[str] | None], int]
#: A gate's behaviour over its parsed arguments, returning the exit code.
ArgumentsRun = Callable[[argparse.Namespace], int]


def gate_log_directory(gate: str, *, workspace: Path = WORKSPACE_DIR) -> Path:
    """``<workspace>/.test-output/gates/<gate>``, where every log of *gate* is claimed.

    Raises:
        ValueError: *gate* has no letter or digit, so it names no directory.
    """
    segment = run_log_segment(gate)
    if not segment:
        raise ValueError(
            f"Gate name {gate!r} has no letters or digits. Expected a name like 'shared-library'. "
            "Fix: pass the gate's name to run_as_gate."
        )
    return workspace / _OUTPUT_FOLDER / GATE_LOG_FOLDER / segment


def claim_gate_log(gate: str, *, workspace: Path = WORKSPACE_DIR) -> Path:
    """Claim, and return the absolute path of, a fresh log file for one run of *gate*."""
    directory = gate_log_directory(gate, workspace=workspace)
    return claim_run_log_file(directory, run_log_base_name(run_log_segment(gate))).resolve()


def verdict_line(gate: str, exit_code: int, log: Path) -> str:
    """The one last line of a gate run: PASSED for exit code 0, FAILED for any other."""
    verdict = _PASSED if exit_code == 0 else _FAILED
    return f"{VERDICT_PREFIX} {gate} {verdict} exit={exit_code} log={log.resolve()}"


def _relay(command: Sequence[str], environment: dict[str, str], log: Path) -> int:
    """Run *command*, write each output line to the console and *log*, and return its exit code."""
    with log.open("a", encoding=_UTF8, newline="\n") as sink:
        try:
            process = subprocess.Popen(command, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        except OSError as exc:
            message = f"Error: the gate could not start {command[0]}: {exc}. Expected the shared venv's interpreter."
            print(message, flush=True)
            sink.write(message + "\n")
            return EXIT_VIOLATION
        assert process.stdout is not None  # stdout=PIPE was requested above.
        try:
            for raw in process.stdout:
                line = raw.decode(_UTF8, errors=_REPLACE).rstrip(_LINE_ENDINGS)
                print(line, flush=True)
                sink.write(line + "\n")
                sink.flush()
        except KeyboardInterrupt:
            # The child received the same interrupt; its exit code is the run's.
            process.wait()
            return process.returncode
        return process.wait()


def run_as_gate(gate: str, module: str, run: GateRun, argv: Sequence[str] | None = None) -> int:
    """The ``main`` of a gate module: run *run* in gate mode (see the module docstring).

    In the child (``DATRIX_GATE_CHILD`` names *gate*) this is ``run(argv)``. Otherwise it claims the
    log, runs ``python -m <module> <argv>`` as the child and returns the child's exit code after
    printing the verdict line.
    """
    if os.environ.get(GATE_CHILD_ENV) == gate:
        return run(argv)
    ensure_utf8_stdio()
    arguments = list(sys.argv[1:] if argv is None else argv)
    log = claim_gate_log(gate)
    environment = {**os.environ, GATE_CHILD_ENV: gate, "PYTHONIOENCODING": _UTF8, "PYTHONUNBUFFERED": "1"}
    exit_code = EXIT_VIOLATION
    try:
        exit_code = _relay([sys.executable, "-m", module, *arguments], environment, log)
    finally:
        line = verdict_line(gate, exit_code, log)
        print(colorize(line, ColorCodes.GREEN if exit_code == 0 else ColorCodes.RED), flush=True)
    return exit_code


def gate_child(build_parser: Callable[[], argparse.ArgumentParser], run: ArgumentsRun) -> GateRun:
    """What a gate's ``main`` hands ``run_as_gate`` to run in the child: *run* on the arguments
    *build_parser* reads, Ctrl-C an exit 130."""

    def child(arguments: Sequence[str] | None) -> int:
        install_sigint_handler()
        return module_main(build_parser(), run, arguments)

    return child
