"""Fail if Python bytecode files are present under package src directories.

Scans Datrix package ``src/`` trees for ``.pyc``/``.pyo`` files and ``__pycache__`` directories. With
no ``--project-dir`` every ``datrix-*`` directory (and the ``datrix`` showcase) under the base directory
that has a ``src/`` is scanned;
a project name is resolved under the base directory, a rooted path is taken as given, and a ``src/``
root outside the base directory is refused. The module behind ``scan/check-python-bytecode.ps1`` (and
its ``.sh`` twin); it needs only the standard library, and the entrypoint runs it with
``PYTHONPYCACHEPREFIX`` set, so the check itself writes no bytecode into any ``src/``.

Exit codes: 0 no bytecode, 1 bytecode found or a refusal (a missing base directory or ``src/``, a root
outside the base directory).

Usage:
    python -m datrix_scripts.scan.check_python_bytecode
    python -m datrix_scripts.scan.check_python_bytecode --project-dir=datrix-common
    python -m datrix_scripts.scan.check_python_bytecode --self-test
"""

from __future__ import annotations

import argparse
import contextlib
import io
import os
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from datrix_scripts.framework_repos import PackageMarker, workspace_package_dirs
from datrix_scripts.gate_harness import EXIT_PASS, EXIT_VIOLATION, write_files
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.test.wrappers import SCAN_SCRIPTS_DIR, module_main, run_self_test

MODULE: Final = "datrix_scripts.scan.check_python_bytecode"
WRAPPER: Final = "check-python-bytecode"

_BYTECODE_SUFFIXES: Final = frozenset({".pyc", ".pyo"})
_PYCACHE: Final = "__pycache__"


class ScanRefused(Exception):
    """The scan cannot start: a missing directory or a root outside the base directory."""


def _full(path: Path) -> Path:
    """*path* made absolute and normalised, without following links (a junctioned package stays where it is named)."""
    return Path(os.path.abspath(path))


def _within(path: Path, base: Path) -> bool:
    """Whether *path* is *base* or below it, compared by path parts (``D:\\datrix2`` is not below ``D:\\datrix``)."""
    parts = [part.casefold() for part in path.parts]
    base_parts = [part.casefold() for part in base.parts]
    return parts[: len(base_parts)] == base_parts


def src_roots(base: Path, project_dirs: Sequence[str]) -> list[Path]:
    """The ``src/`` roots to scan: each named project's, else every framework package's under *base*.

    Raises:
        ScanRefused: *base* or a named project's ``src/`` does not exist, or a root lies outside *base*.
    """
    if not base.exists():
        raise ScanRefused(f"BaseDir not found: {base}")
    if project_dirs:
        roots: list[Path] = []
        for name in project_dirs:
            src = (Path(name) if Path(name).is_absolute() else base / name) / "src"
            if not src.exists():
                raise ScanRefused(f"src directory not found: {src}")
            roots.append(_full(src))
    else:
        roots = [
            _full(child / PackageMarker.SRC.value)
            for child in workspace_package_dirs(base, any_of=frozenset({PackageMarker.SRC}), include_showcase=True)
        ]
    outside = next((root for root in roots if not _within(root, base)), None)
    if outside is not None:
        raise ScanRefused(f"Refusing to scan path outside BaseDir: {outside}")
    return roots


def bytecode_artifacts(roots: Sequence[Path]) -> list[Path]:
    """Every bytecode file and ``__pycache__`` directory under *roots*."""
    found: list[Path] = []
    for root in roots:
        for path in root.rglob("*"):
            if path.is_dir() and path.name == _PYCACHE:
                found.append(path)
            elif path.is_file() and path.suffix in _BYTECODE_SUFFIXES:
                found.append(path)
    return sorted(found, key=lambda path: str(path).casefold())


def check(base: Path, project_dirs: Sequence[str]) -> int:
    """Report the bytecode under the selected ``src/`` roots of *base*; the exit code."""
    try:
        roots = src_roots(base, project_dirs)
    except ScanRefused as refused:
        print(refused, file=sys.stderr)
        return EXIT_VIOLATION
    artifacts = bytecode_artifacts(roots)
    if not artifacts:
        print("No Python bytecode found under package src directories.")
        return EXIT_PASS
    print("Python bytecode artifacts found under package src directories:")
    for path in artifacts:
        print(f"  {path}")
    print()
    print("Remove these artifacts or run Python with PYTHONPYCACHEPREFIX outside src.")
    return EXIT_VIOLATION


def build_parser() -> argparse.ArgumentParser:
    """The options of ``scan/check-python-bytecode.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        prog=WRAPPER, description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False
    )
    parser.add_argument("--base-dir", type=Path, default=WORKSPACE_DIR,
                        help="Monorepo root directory. Default: the workspace holding this scripts tree.")
    parser.add_argument("--project-dir", action="append", default=[],
                        help="A project name under the base directory, or a path, to check (repeatable). "
                             "Default: every datrix-* package (and datrix) with a src directory.")
    parser.add_argument("--self-test", action="store_true",
                        help="Run only the self-test: planted bytecode is listed (exit 1), a clean tree passes, "
                             "a missing src directory and a root outside the base directory are refused, and "
                             "the wrapper seam holds.")
    parser.set_defaults(debug=False)
    return parser


def _checked(base: Path, project_dirs: Sequence[str]) -> tuple[int, str]:
    """``check`` on *base*: the exit code and everything it printed."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = check(base, project_dirs)
    return code, out.getvalue()


def _check_planted_bytecode_is_listed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp).resolve()
        write_files(base, {
            "datrix-planted/src/planted/__pycache__/mod.cpython-314.pyc": "",
            "datrix-planted/src/planted/stale.pyo": "",
            "datrix-clean/src/clean/mod.py": "",
        })
        code, out = _checked(base, [])
    assert code == EXIT_VIOLATION, f"planted bytecode must exit {EXIT_VIOLATION}; got {code}: {out!r}"
    for listed in ("__pycache__", "mod.cpython-314.pyc", "stale.pyo"):
        assert listed in out, f"{listed} must be listed: {out!r}"
    assert "datrix-clean" not in out, f"the clean package must not be listed: {out!r}"


def _check_a_clean_tree_passes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp).resolve()
        write_files(base, {"datrix-clean/src/clean/mod.py": "", "other/src/x.pyc": ""})
        code, out = _checked(base, [])
    assert code == EXIT_PASS, f"a clean tree (bytecode only outside datrix-*) must pass; got {code}: {out!r}"
    assert "No Python bytecode found" in out, out


def _check_a_missing_src_is_refused() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        code, out = _checked(Path(tmp).resolve(), ["no-such-project"])
    assert code == EXIT_VIOLATION and "src directory not found" in out, f"got {code}: {out!r}"


def _check_a_root_outside_the_base_is_refused() -> None:
    with tempfile.TemporaryDirectory() as base_tmp, tempfile.TemporaryDirectory() as other_tmp:
        write_files(Path(other_tmp), {"datrix-elsewhere/src/x.py": ""})
        code, out = _checked(Path(base_tmp).resolve(), [str(Path(other_tmp).resolve() / "datrix-elsewhere")])
    assert code == EXIT_VIOLATION and "outside BaseDir" in out, f"got {code}: {out!r}"


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        checks = [
            _check_planted_bytecode_is_listed,
            _check_a_clean_tree_passes,
            _check_a_missing_src_is_refused,
            _check_a_root_outside_the_base_is_refused,
        ]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=SCAN_SCRIPTS_DIR)
    return check(_full(args.base_dir), args.project_dir)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
