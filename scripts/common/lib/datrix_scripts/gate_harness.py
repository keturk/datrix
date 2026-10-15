"""The one harness every scripts gate runs its checks through.

A gate is a list of zero-argument checks, each raising ``AssertionError`` with a descriptive
message when the property it guards does not hold. ``run_checks`` runs them, catching only
``AssertionError`` (anything else is a defect in the gate itself and propagates), prints
``[OK] <name>`` or ``[FAIL] <name>: <message>`` per check, and returns True iff every check
passed. ``harness_self_test`` proves that loop cannot swallow a failure: a deliberately failing
check must be reported FAILED.

Exit codes every gate uses: 0 pass, 1 violation, 2 usage error (``UsageError``), 130 interrupt
(``install_sigint_handler``).

Before this module existed the same loop, the same ``[OK]``/``[FAIL]`` printers and the same
logging setup were copied into every gate module, in two signatures and two log formats. A
census in the shared-library gate keeps them from coming back.
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from types import FrameType
from typing import Final

CheckFunc = Callable[[], None]

EXIT_PASS: Final = 0
EXIT_VIOLATION: Final = 1
EXIT_USAGE: Final = 2
EXIT_INTERRUPTED: Final = 130

LOG_FORMAT: Final = "%(levelname)s %(name)s: %(message)s"

_GREEN: Final = "\033[92m"
_RED: Final = "\033[91m"
_CYAN: Final = "\033[96m"
_RESET: Final = "\033[0m"

_DELIBERATE_FAILURE: Final = "deliberately failing check for the harness self-test"


class UsageError(Exception):
    """A gate was invoked with arguments it cannot act on (exit code 2)."""


@dataclass(frozen=True)
class NamedCheck:
    """A check whose reported name is not its function's name (a parametrized case)."""

    name: str
    run: CheckFunc


CHECK_PREFIX: Final = "_check_"


def named_checks(checks: Sequence[CheckFunc], *, prefix: str = CHECK_PREFIX) -> list[NamedCheck]:
    """Each check named by its function name without ``prefix`` (``_check_x`` reports as ``x``)."""
    return [NamedCheck(check.__name__.removeprefix(prefix), check) for check in checks]


def _check_name(check: CheckFunc | NamedCheck) -> str:
    if isinstance(check, NamedCheck):
        return check.name
    return getattr(check, "__name__", repr(check))


def report_ok(message: str) -> None:
    """Print one passing line: ``[OK] message``."""
    print(f"{_GREEN}[OK]{_RESET} {message}")


def report_fail(message: str) -> None:
    """Print one failing line: ``[FAIL] message``."""
    print(f"{_RED}[FAIL]{_RESET} {message}")


def report_condition(condition: bool, label: str, detail: str = "") -> bool:
    """Report one self-test assertion as ``[OK] label`` or ``[FAIL] label: detail``; return it."""
    if condition:
        report_ok(label)
    else:
        report_fail(f"{label}: {detail}" if detail else label)
    return condition


def report_step(message: str) -> None:
    """Print a section header: a blank line, then ``=== message``."""
    print(f"\n{_CYAN}=== {message}{_RESET}")


def run_checks(
    checks: Sequence[CheckFunc | NamedCheck],
    *,
    also_failing: tuple[type[Exception], ...] = (),
) -> bool:
    """Run every check, catching only ``AssertionError``; True iff all passed.

    ``also_failing`` names further exception types a gate's checks raise to mean "this check
    failed" (a gate's own refusal type), reported as ``[FAIL] name: Type: message``.
    """
    all_passed = True
    for check in checks:
        name = _check_name(check)
        run = check.run if isinstance(check, NamedCheck) else check
        try:
            run()
        except AssertionError as exc:
            report_fail(f"{name}: {exc}")
            all_passed = False
        except also_failing as exc:
            report_fail(f"{name}: {type(exc).__name__}: {exc}")
            all_passed = False
        else:
            report_ok(name)
    return all_passed


def _deliberately_failing_check() -> None:
    raise AssertionError(_DELIBERATE_FAILURE)


def harness_self_test() -> bool:
    """Prove the harness reports a failing check: a deliberate failure must come back FAILED."""
    print("=== Harness self-test: a deliberately-failing check must be reported FAILED ===")
    if run_checks([NamedCheck("deliberately_failing_check", _deliberately_failing_check)]):
        report_fail("harness self-test: the deliberately-failing check was NOT reported as failed")
        return False
    report_ok("harness self-test: the deliberately-failing check was correctly reported FAILED")
    return True


def configure_logging(debug: bool) -> None:
    """Log to stderr in the one gate format, DEBUG when ``debug`` else INFO."""
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format=LOG_FORMAT,
        stream=sys.stderr,
        force=True,
    )


def gate_argument_parser(
    description: str, *, update_baseline: bool = False
) -> argparse.ArgumentParser:
    """An argument parser carrying the shared gate flags.

    ``--debug``, ``--self-test`` (run only the gate's non-vacuity proof, reading nothing of the
    real workspace), ``--harness-self-test`` (run only ``harness_self_test``) and, when
    ``update_baseline`` is set, ``--update-baseline``.
    """
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--debug", action="store_true", help="Log at DEBUG level.")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run only the gate's non-vacuity proof over planted inputs.",
    )
    parser.add_argument(
        "--harness-self-test",
        action="store_true",
        help="Run only the harness self-test (a deliberately failing check must be reported).",
    )
    if update_baseline:
        parser.add_argument(
            "--update-baseline",
            action="store_true",
            help="Rewrite the gate's baseline from the current tree.",
        )
    return parser


@contextmanager
def _temp_file_variable(binding: tuple[str, str] | None) -> Iterator[None]:
    """For the block, point an environment variable at a file in a fresh temporary directory."""
    if binding is None:
        yield
        return
    variable, file_name = binding
    previous = os.environ.get(variable)
    with TemporaryDirectory(prefix="gate-") as temp:
        os.environ[variable] = str(Path(temp) / file_name)
        try:
            yield
        finally:
            if previous is None:
                del os.environ[variable]
            else:
                os.environ[variable] = previous


def _select(checks: Sequence[CheckFunc | NamedCheck], prefix: str) -> list[CheckFunc | NamedCheck]:
    return [check for check in checks if _check_name(check).startswith(prefix)]


def check_list_main(
    description: str,
    subject: str,
    checks: Sequence[CheckFunc | NamedCheck],
    *,
    self_test: Sequence[CheckFunc | NamedCheck] = (),
    temp_file_variable: tuple[str, str] | None = None,
    argv: Sequence[str] | None = None,
) -> int:
    """The ``main`` of a gate that is a list of checks.

    Flags: the shared gate flags plus ``--only PREFIX`` (run the checks whose name starts with
    PREFIX). ``--self-test`` runs ``harness_self_test`` and then ``self_test`` -- the gate's
    checks over planted inputs only. ``temp_file_variable`` is ``(environment variable, file
    name)``: for the run, the variable names a file in a fresh temporary directory (so the
    checks' own side effects, such as a usage log, never land in the real one).
    """
    parser = gate_argument_parser(description)
    parser.add_argument(
        "--only",
        metavar="PREFIX",
        help="Run only the checks whose name starts with PREFIX.",
    )
    args = parser.parse_args(argv)
    if args.harness_self_test:
        return EXIT_PASS if harness_self_test() else EXIT_VIOLATION
    if args.self_test:
        return EXIT_PASS if harness_self_test() and run_checks(self_test) else EXIT_VIOLATION

    selected = _select(checks, args.only) if args.only else list(checks)
    if not selected:
        names = ", ".join(_check_name(check) for check in checks)
        print(
            f"Error: no check name starts with {args.only!r}. Checks: {names}. "
            "Pass a prefix of one of them to --only.",
            file=sys.stderr,
        )
        return EXIT_USAGE

    print(f"Running {len(selected)} {subject} checks...\n")
    with _temp_file_variable(temp_file_variable):
        passed = run_checks(selected)
    print()
    if passed:
        report_ok(f"GATE PASSED: all {len(selected)} {subject} checks passed.")
        return EXIT_PASS
    report_fail("GATE FAILED: see the failures above.")
    return EXIT_VIOLATION


def run_main(
    parse_args: Callable[[], argparse.Namespace],
    run: Callable[[argparse.Namespace], int],
) -> int:
    """Parse arguments, configure logging from ``--debug``, run, and map ``UsageError`` to 2."""
    args = parse_args()
    configure_logging(args.debug)
    try:
        return run(args)
    except UsageError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_USAGE


def _exit_on_interrupt(signum: int, frame: FrameType | None) -> None:
    del signum, frame
    print("\nInterrupted.", file=sys.stderr)
    sys.exit(EXIT_INTERRUPTED)


def install_sigint_handler() -> None:
    """Exit 130 with one message on Ctrl-C instead of a traceback."""
    signal.signal(signal.SIGINT, _exit_on_interrupt)


def write_files(root: Path, files: Mapping[str, str]) -> list[Path]:
    """Write each ``relative path -> text`` under ``root`` (UTF-8), creating parents.

    For a gate's planted fixtures. Returns the written paths in the mapping's order.
    """
    written: list[Path] = []
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        written.append(path)
    return written


def write_file(path: Path, text: str) -> Path:
    """Write one planted fixture file (UTF-8), creating its parents; returns ``path``."""
    return write_files(path.parent, {path.name: text})[0]
