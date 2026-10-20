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

#: The debug flag of a gate run by a wrapper that is not rendered from the template.
DEBUG_FLAG: Final = "--debug"
#: The debug flag of a gate behind a rendered wrapper: its ``-Dbg`` passed as ``--dbg``.
WRAPPER_DEBUG_FLAG: Final = "--dbg"

_GREEN: Final = "\033[92m"
_RED: Final = "\033[91m"
_CYAN: Final = "\033[96m"
_RESET: Final = "\033[0m"

_DELIBERATE_FAILURE: Final = "deliberately failing check for the harness self-test"


class UsageError(Exception):
    """A gate was invoked with arguments it cannot act on (exit code 2)."""


def expect_usage_error(call: Callable[[], object], fragment: str) -> None:
    """Assert *call* raises UsageError whose message contains *fragment* (a self-test helper)."""
    try:
        call()
    except UsageError as exc:
        assert fragment in str(exc), f"UsageError must mention {fragment!r}; got: {exc}"
    else:
        raise AssertionError(f"expected UsageError mentioning {fragment!r}")


@dataclass(frozen=True)
class NamedCheck:
    """A check whose reported name is not its function's name (a parametrized case)."""

    name: str
    run: CheckFunc


CHECK_PREFIX: Final = "_check_"


def named_checks(checks: Sequence[CheckFunc | NamedCheck], *, prefix: str = CHECK_PREFIX) -> list[NamedCheck]:
    """Each check named by its function name without ``prefix`` (``_check_x`` reports as ``x``); a
    ``NamedCheck`` keeps its own name."""
    return [
        check if isinstance(check, NamedCheck) else NamedCheck(check.__name__.removeprefix(prefix), check)
        for check in checks
    ]


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
    description: str,
    *,
    update_baseline: bool = False,
    debug_flag: str | None = DEBUG_FLAG,
    allow_abbrev: bool = True,
    harness_self_test_flag: bool = True,
) -> argparse.ArgumentParser:
    """An argument parser carrying the shared gate flags.

    ``--debug``, ``--self-test`` (run only the gate's non-vacuity proof, reading nothing of the
    real workspace), ``--harness-self-test`` (run only ``harness_self_test``) and, when
    ``update_baseline`` is set, ``--update-baseline``.

    A gate behind a wrapper rendered from ``common/templates/entrypoint.ps1`` takes exactly its
    wrapper's parameters as options: *debug_flag* is ``WRAPPER_DEBUG_FLAG`` (its ``-Dbg``), or None
    when the wrapper declares no debug parameter (``args.debug`` is then False);
    *harness_self_test_flag* is False when the wrapper declares no ``-HarnessSelfTest``
    (``args.harness_self_test`` is then False, and the gate's ``--self-test`` runs the harness
    self-test first); and *allow_abbrev* is False, so no abbreviated spelling reaches the module unseen.
    """
    parser = argparse.ArgumentParser(description=description, allow_abbrev=allow_abbrev)
    if debug_flag is None:
        parser.set_defaults(debug=False)
    else:
        parser.add_argument(debug_flag, dest="debug", action="store_true", help="Log at DEBUG level.")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run only the gate's non-vacuity proof over planted inputs.",
    )
    if harness_self_test_flag:
        parser.add_argument(
            "--harness-self-test",
            action="store_true",
            help="Run only the harness self-test (a deliberately failing check must be reported).",
        )
    else:
        parser.set_defaults(harness_self_test=False)
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


def check_list_parser(
    description: str,
    *,
    debug_flag: str | None = DEBUG_FLAG,
    allow_abbrev: bool = True,
    harness_self_test_flag: bool = True,
) -> argparse.ArgumentParser:
    """The parser of a gate that is a list of checks: the shared gate flags (see
    ``gate_argument_parser`` for *debug_flag*, *allow_abbrev* and *harness_self_test_flag*) plus
    ``--only PREFIX``."""
    parser = gate_argument_parser(
        description, debug_flag=debug_flag, allow_abbrev=allow_abbrev, harness_self_test_flag=harness_self_test_flag
    )
    parser.add_argument(
        "--only",
        metavar="PREFIX",
        help="Run only the checks whose name starts with PREFIX.",
    )
    return parser


def print_command() -> None:
    """Print the interpreter and the arguments this process runs with (a wrapper's ``-Dbg``)."""
    print(f"Python executable: {sys.executable}")
    print(f"Arguments: {' '.join(sys.argv)}", flush=True)


def check_list_main(
    description: str,
    subject: str,
    checks: Sequence[CheckFunc | NamedCheck],
    *,
    self_test: Sequence[CheckFunc | NamedCheck] = (),
    temp_file_variable: tuple[str, str] | None = None,
    argv: Sequence[str] | None = None,
    parser: argparse.ArgumentParser | None = None,
) -> int:
    """The ``main`` of a gate that is a list of checks.

    Flags: those of ``check_list_parser`` (*parser*, when the gate builds it itself). The debug flag
    prints the interpreter and arguments first. ``--self-test`` runs ``harness_self_test`` and then
    ``self_test`` -- the gate's checks over planted inputs only. ``temp_file_variable`` is
    ``(environment variable, file name)``: for the run, the variable names a file in a fresh
    temporary directory (so the checks' own side effects, such as a usage log, never land in the
    real one).
    """
    parser = parser if parser is not None else check_list_parser(description)
    args = parser.parse_args(argv)
    if args.debug:
        print_command()
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
