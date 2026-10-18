"""Import every named module in one interpreter and name each one that fails.

The venv install check (``datrix_scripts.venv.unimportable_packages``, ``common/venv.ps1``) asks
whether every workspace package imports. One interpreter per package pays the interpreter
start-up and the shared dependency imports once per package; this module imports every
named module, in order, in one process.

Output: one line per module that fails, then one summary line.

    IMPORT_FAILED <module>: <ExceptionType>: <message>
    IMPORT_CHECK <ok>/<total>

Every line is ASCII: a character outside ASCII is written as its backslash escape, so the
verdict reaches the caller whatever encoding the output stream has (a pipe on Windows is
cp1252 unless PYTHONIOENCODING says otherwise).

Exit codes: 0 when every module imported; 1 when any failed; 2 on a usage error, or when the
self-test, which runs first on every invocation, does not hold.

Usage:
    python -m datrix_scripts.package_imports <module> [<module> ...]
    python -m datrix_scripts.package_imports --self-test
"""

from __future__ import annotations

import argparse
import importlib
import io
import sys
import tempfile
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, TextIO

EXIT_OK: Final = 0
EXIT_IMPORT_FAILED: Final = 1
EXIT_USAGE: Final = 2

FAILURE_PREFIX: Final = "IMPORT_FAILED"
SUMMARY_PREFIX: Final = "IMPORT_CHECK"

_OUTPUT_ENCODING: Final = "ascii"
_OUTPUT_ERRORS: Final = "backslashreplace"

_PROBE_PREFIX: Final = "_datrix_import_probe"
_PROBE_FAILURE_MESSAGE: Final = "planted import failure → ü"
_PROBE_FAILURE_RENDERED: Final = "planted import failure \\u2192 \\xfc"


@dataclass(frozen=True)
class ImportFailure:
    """One module that raised while it was imported."""

    module: str
    exception_type: str
    message: str

    def render(self) -> str:
        """The ``IMPORT_FAILED`` line, ASCII only (non-ASCII characters backslash-escaped)."""
        line = f"{FAILURE_PREFIX} {self.module}: {self.exception_type}: {self.message}"
        return line.encode(_OUTPUT_ENCODING, _OUTPUT_ERRORS).decode(_OUTPUT_ENCODING)


def _one_line(text: str) -> str:
    return " ".join(text.split())


def import_failures(modules: Sequence[str]) -> list[ImportFailure]:
    """Import each of *modules* in order; return one failure per module that raised.

    Catching broadly is reporting, not silencing: every failure is returned by module name,
    and the caller turns any failure into a non-zero exit. ``SystemExit`` is caught as well,
    so a module that exits while it is imported cannot end the check early.
    """
    failures: list[ImportFailure] = []
    for module in modules:
        try:
            importlib.import_module(module)
        except (Exception, SystemExit) as exc:
            failures.append(ImportFailure(module, type(exc).__name__, _one_line(str(exc))))
    return failures


def run_check(modules: Sequence[str], out: TextIO) -> int:
    """Import *modules*, write one line per failure and the summary line to *out*."""
    failures = import_failures(modules)
    for failure in failures:
        print(failure.render(), file=out)
    print(f"{SUMMARY_PREFIX} {len(modules) - len(failures)}/{len(modules)}", file=out)
    return EXIT_IMPORT_FAILED if failures else EXIT_OK


# ---------------------------------------------------------------------------
# Self-Test (runs first on every invocation; --self-test runs only it)
# ---------------------------------------------------------------------------


def _check_planted_modules(root: Path, module_names: Sequence[str]) -> tuple[int, list[str]]:
    """Run the check over *module_names* with *root* first on ``sys.path``, then remove both."""
    out = io.StringIO()
    sys.path.insert(0, str(root))
    importlib.invalidate_caches()
    try:
        exit_code = run_check(module_names, out)
    finally:
        sys.path.remove(str(root))
        for name in module_names:
            if name in sys.modules:
                del sys.modules[name]
    return exit_code, out.getvalue().splitlines()


def run_self_test() -> list[str]:
    """Plant one module that imports and one that raises ImportError with a non-ASCII message;
    prove only the second is reported, by name, its message escaped to ASCII, with exit code 1.
    Returns the problems found (empty when it holds)."""
    suffix = uuid.uuid4().hex
    importable = f"{_PROBE_PREFIX}_ok_{suffix}"
    broken = f"{_PROBE_PREFIX}_broken_{suffix}"
    with tempfile.TemporaryDirectory(prefix="package-imports-") as tmp:
        root = Path(tmp)
        (root / f"{importable}.py").write_text("VALUE = 1\n", encoding="utf-8")
        (root / f"{broken}.py").write_text(
            f"raise ImportError({_PROBE_FAILURE_MESSAGE!r})\n", encoding="utf-8"
        )
        exit_code, lines = _check_planted_modules(root, [importable, broken])
    expected = [
        f"{FAILURE_PREFIX} {broken}: ImportError: {_PROBE_FAILURE_RENDERED}",
        f"{SUMMARY_PREFIX} 1/2",
    ]
    problems: list[str] = []
    if exit_code != EXIT_IMPORT_FAILED:
        problems.append(f"exit code {exit_code}, expected {EXIT_IMPORT_FAILED} for one broken module")
    if lines != expected:
        problems.append(f"output {lines!r}, expected {expected!r}")
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("modules", nargs="*", help="module names to import, in order")
    parser.add_argument("--self-test", action="store_true", help="run only the self-test")
    args = parser.parse_args(argv)

    problems = run_self_test()
    for problem in problems:
        print(f"package_imports self-test FAILED: {problem}", file=sys.stderr)
    if problems:
        return EXIT_USAGE

    if args.self_test:
        if args.modules:
            print("Error: --self-test takes no module names.", file=sys.stderr)
            return EXIT_USAGE
        print("package_imports self-test: the planted broken module was reported by name")
        return EXIT_OK
    if not args.modules:
        print(
            "Error: name at least one module "
            "(usage: python -m datrix_scripts.package_imports <module> [<module> ...]).",
            file=sys.stderr,
        )
        return EXIT_USAGE
    return run_check(args.modules, sys.stdout)


if __name__ == "__main__":
    sys.exit(main())
