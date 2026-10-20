"""Compile Python (syntax and import check) in Datrix projects, or under any path.

The module behind ``scan/compile.ps1`` (and its ``.sh`` twin). Two modes:

- Projects (``--all`` or ``--project-dir``): discovers every ``.py`` file under the named project
  directories (every Datrix repository with ``--all``), runs ``py_compile`` on each for the syntax
  check, and for each installable package among them imports the package and every submodule so
  cross-package imports are exercised.
- Path (``--path``): for each file or directory, anywhere, finds the containing installable package
  (the nearest ancestor with ``src/`` and ``pyproject.toml`` or ``setup.py``) and runs that package's
  full check, so a subfolder such as a generated service's ``routes`` still reports a missing import.

Relative names and paths resolve against the workspace root; one that does not exist is refused
(exit 2). Exit codes: 0 every file passed, 1 a syntax or import error, 2 a usage error.

Usage:
    python -m datrix_scripts.scan.compile --all [--dbg]
    python -m datrix_scripts.scan.compile --project-dir=datrix-common [--project-dir=...] [--dbg]
    python -m datrix_scripts.scan.compile --path=<file or directory> [--path=...] [--dbg]
"""

from __future__ import annotations

import argparse
import contextlib
import io
import os
import py_compile
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Final, NamedTuple

from datrix_scripts.dev.arguments import comma_values
from datrix_scripts.gate_harness import (
    EXIT_PASS,
    EXIT_USAGE,
    EXIT_VIOLATION,
    WRAPPER_DEBUG_FLAG,
    UsageError,
    expect_usage_error,
    print_command,
    write_files,
)
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.scan.selection import every_repository
from datrix_scripts.test.wrappers import SCAN_SCRIPTS_DIR, module_main, run_self_test
from datrix_scripts.venv import module_name

MODULE: Final = "datrix_scripts.scan.compile"
WRAPPER: Final = "compile"

# Directories to skip during file discovery (same as syntax_checker)
_SKIP_DIRS = frozenset({
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "build", "dist", ".tox", ".mypy_cache", ".pytest_cache",
    ".eggs", ".ruff_cache",
})

_IMPORT_TIMEOUT_SECONDS: Final = 60

_USAGE: Final = """Usage:
  .\\compile.ps1 -All
  .\\compile.ps1 datrix-common [datrix-language ...]
  .\\compile.ps1 -Path <file or directory> [...]

Use Get-Help .\\compile.ps1 -Full for detailed help."""


class SyntaxErrorResult(NamedTuple):
    """A single syntax error."""

    file_path: Path
    message: str
    line: int


class ImportErrorResult(NamedTuple):
    """A single import error."""

    project_root: Path
    package_name: str
    message: str


def find_py_files(root: Path, skip_dirs: frozenset[str]) -> list[Path]:
    """
    Recursively find all .py files under root, excluding skip_dirs.

    Args:
        root: Directory to search.
        skip_dirs: Directory names to skip (e.g. __pycache__, .venv).

    Returns:
        Sorted list of paths to .py files.
    """
    if not root.is_dir():
        return []
    out: list[Path] = []
    for dir_path, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs and not d.endswith(".egg-info")]
        for name in filenames:
            if name.endswith(".py"):
                out.append(Path(dir_path) / name)
    return sorted(out)


def is_installable_package(project_root: Path) -> bool:
    """Return True if project_root looks like an installable Python package (has src/ and pyproject.toml or setup.py)."""
    if not project_root.is_dir():
        return False
    has_src = (project_root / "src").is_dir()
    has_pyproject = (project_root / "pyproject.toml").is_file()
    has_setup = (project_root / "setup.py").is_file()
    return has_src and (has_pyproject or has_setup)


def get_all_installable_roots(roots: list[Path]) -> list[Path]:
    """
    Return all directory paths under roots that are installable packages (have src/ and pyproject.toml or setup.py).
    Used to build PYTHONPATH so cross-package imports (e.g. from datrix_language.parser) are resolvable.
    """
    out: list[Path] = []
    for root in roots:
        path = Path(root)
        if not path.is_dir():
            continue
        if is_installable_package(path):
            out.append(path)
    return out


def find_installable_ancestor(path: Path) -> Path | None:
    """The nearest directory at or above *path* that is an installable package root, or None.

    A file starts the walk at its parent, so a subfolder (``.../src/<pkg>/routes``) finds the package
    root whose full check covers it.
    """
    current = path.resolve()
    if current.is_file():
        current = current.parent
    while current != current.parent:
        if is_installable_package(current):
            return current
        current = current.parent
    return None


def installable_ancestors(paths: Sequence[Path]) -> list[Path]:
    """The installable package root containing each of *paths*, each root once, in first-seen order."""
    roots: list[Path] = []
    for path in paths:
        root = find_installable_ancestor(path)
        if root is not None and root not in roots:
            roots.append(root)
    return roots


def check_syntax(
    py_files: list[Path],
    debug: bool,
) -> list[SyntaxErrorResult]:
    """
    Run py_compile on each file. Uses a temporary directory for .pyc output.

    Returns:
        List of syntax errors (file, message, line).
    """
    errors: list[SyntaxErrorResult] = []
    with tempfile.TemporaryDirectory(prefix="compile_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        for file_path in py_files:
            if debug:
                print(f"[DEBUG] Checking syntax: {file_path}", file=sys.stderr)
            # Unique cfile per source path so we don't overwrite
            safe_name = str(file_path).replace(os.sep, "_").replace(":", "_").strip("_") + ".pyc"
            cfile = tmp_path / safe_name
            try:
                py_compile.compile(str(file_path), cfile=str(cfile), doraise=True)
            except py_compile.PyCompileError as e:
                msg = e.msg if hasattr(e, "msg") else str(e)
                line = e.lineno if hasattr(e, "lineno") and e.lineno is not None else 0
                errors.append(SyntaxErrorResult(file_path, msg, line))
    return errors


def _make_import_check_script(package_name: str) -> str:
    """Build script that imports package and all submodules to exercise cross-package imports."""
    return f"""
import importlib
import pkgutil
import sys
package_name = {repr(package_name)}
mod = importlib.import_module(package_name)
if hasattr(mod, '__path__'):
    for importer, modname, ispkg in pkgutil.walk_packages(mod.__path__, prefix=package_name + '.'):
        importlib.import_module(modname)
"""


def check_import(project_root: Path, package_name: str) -> ImportErrorResult | None:
    """
    Import the package and all its submodules so cross-package imports (e.g. from datrix_language.parser)
    are exercised.

    Sibling packages resolve through the shared venv, where every ``datrix-*`` package is
    installed in editable mode -- so no ``src`` directory is injected into ``PYTHONPATH``.
    Putting the raw ``src`` directories on ``sys.path`` shadows those editable installs with
    plain directories that carry no ``.dist-info``, which silently strips the packages' entry
    points. A generator package whose DAL generator definitions validate their own target
    against the discovered-plugin registry at import time then fails with a bogus
    "Unknown generator target" -- reporting a package that imports correctly in every
    real code path as an import error.
    """
    script = _make_import_check_script(package_name)
    try:
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=project_root,
            timeout=_IMPORT_TIMEOUT_SECONDS,
            env=os.environ.copy(),
        )
    except subprocess.TimeoutExpired:
        return ImportErrorResult(project_root, package_name, "import timed out")
    except OSError as e:
        return ImportErrorResult(project_root, package_name, f"{type(e).__name__}: {e}")
    if result.returncode == 0:
        return None
    err = (result.stderr or result.stdout or "import failed").strip()
    return ImportErrorResult(project_root, package_name, err or "import failed (no output)")


def run_import_checks(project_roots: list[Path], debug: bool) -> list[ImportErrorResult]:
    """
    For each installable package under project_roots, run an import check that also loads all
    submodules so cross-package imports (e.g. from datrix_language.parser) are exercised.
    """
    roots = [Path(r) for r in project_roots if Path(r).is_dir()]
    errors: list[ImportErrorResult] = []
    for path in get_all_installable_roots(roots):
        pkg = module_name(path.name)
        if debug:
            print(f"[DEBUG] Import check: {pkg} at {path}", file=sys.stderr)
        err = check_import(path, pkg)
        if err is not None:
            errors.append(err)
    return errors


def report(
    py_files: list[Path],
    syntax_errors: list[SyntaxErrorResult],
    import_errors: list[ImportErrorResult],
) -> None:
    """Print summary and per-file/per-package error details."""
    total = len(py_files)
    syntax_count = len(syntax_errors)
    import_count = len(import_errors)

    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Python files checked: {total}")
    print(f"  Syntax errors:         {syntax_count}")
    print(f"  Import errors:         {import_count}")
    print()

    if syntax_errors:
        print("-" * 40)
        print("SYNTAX ERRORS")
        print("-" * 40)
        for r in syntax_errors:
            line_info = f" line {r.line}" if r.line else ""
            print(f"  {r.file_path}{line_info}: {r.message}")
        print()

    if import_errors:
        print("-" * 40)
        print("IMPORT ERRORS")
        print("-" * 40)
        for r in import_errors:
            print(f"  {r.project_root} ({r.package_name}):")
            for line in (r.message or "").splitlines():
                print(f"    {line}")
        print()

    if not syntax_errors and not import_errors:
        print("[OK] All checked files passed syntax and import checks.")
    else:
        print(f"[ERROR] {syntax_count} syntax error(s), {import_count} import error(s).")


def compile_paths(paths_to_check: list[Path], debug: bool) -> int:
    """Syntax-check every ``.py`` file under *paths_to_check* and import-check each installable
    package among them; print the report. 0 when everything passed, else 1."""
    print("Discovering Python files...", flush=True)
    all_py_files: list[Path] = []
    for path in paths_to_check:
        if not path.exists():
            print(f"Warning: Path does not exist: {path}", file=sys.stderr)
            continue
        found = find_py_files(path, _SKIP_DIRS)
        if found:
            print(f"  {path.name}: {len(found)} files", flush=True)
        all_py_files.extend(found)

    if not all_py_files:
        print("No Python files found to check.")
        return EXIT_PASS

    print(f"Found {len(all_py_files)} Python file(s) total.", flush=True)
    print("Checking syntax...", flush=True)

    syntax_errors = check_syntax(all_py_files, debug)
    print("Checking imports (packages + submodules, cross-project)...", flush=True)
    import_errors = run_import_checks(paths_to_check, debug)

    report(all_py_files, syntax_errors, import_errors)
    return EXIT_VIOLATION if syntax_errors or import_errors else EXIT_PASS


def compile_any_path(paths: Sequence[Path], debug: bool) -> int:
    """The Path mode: the full check of the installable package containing each of *paths*."""
    import_roots = installable_ancestors(paths)
    if not import_roots:
        print("No installable package root found for the given path(s).")
        print("Paths must be inside a directory that has src/ and pyproject.toml (or setup.py).")
        return EXIT_PASS
    return compile_paths(import_roots, debug)


def resolve_target(target: str, workspace: Path) -> Path:
    """*target* as given when rooted, else against *workspace*; a missing one is a usage error."""
    full_path = workspace / target
    if not full_path.exists():
        raise UsageError(
            f"Path not found: {full_path}. Pass a project name (datrix-common), or a file or directory path."
        )
    return full_path


def build_parser() -> argparse.ArgumentParser:
    """The options of ``scan/compile.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        prog=WRAPPER, description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False
    )
    parser.add_argument("--all", action="store_true", help="Compile Python in every Datrix repository.")
    parser.add_argument("--project-dir", action="append", default=[],
                        help="A project directory to check: a name (datrix-common) or a path (repeatable).")
    parser.add_argument("--path", action="append", default=[],
                        help="A file or directory, anywhere; its containing package is checked (repeatable or "
                             "comma-separated).")
    parser.add_argument(WRAPPER_DEBUG_FLAG, dest="debug", action="store_true",
                        help="Print the interpreter and arguments, and log at DEBUG level.")
    parser.add_argument("--self-test", action="store_true",
                        help="Run only the self-test: planted projects are checked, the Path mode finds the "
                             "containing package, and the usage errors are refused.")
    return parser


def compile_selected(args: argparse.Namespace, workspace: Path) -> int:
    """Run the mode *args* selects (the wrapper's two parameter sets) over targets under *workspace*."""
    if args.path:
        if args.all or args.project_dir:
            raise UsageError("Specify either -Path, or -All / project directories, not both.")
        paths = [resolve_target(target, workspace) for target in comma_values(args.path)]
        print("Running compile (syntax and import check) for any path...")
        print()
        return compile_any_path(paths, args.debug)
    if not args.all and not args.project_dir:
        print(_USAGE)
        return EXIT_USAGE
    if args.all:
        paths = every_repository(workspace)
    else:
        paths = [resolve_target(target, workspace) for target in args.project_dir]
    print("Running compile (syntax and import check)...")
    print()
    return compile_paths(paths, args.debug)


def _quiet(call: Callable[[], int]) -> int:
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return call()


def _check_a_planted_syntax_error_fails() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp) / "planted-project"
        write_files(project, {"good.py": "VALUE = 1\n", "bad.py": "def broken(:\n"})
        args = build_parser().parse_args(["--project-dir=planted-project"])
        assert _quiet(lambda: compile_selected(args, Path(tmp))) == EXIT_VIOLATION, (
            "a project holding a syntax error must exit 1"
        )


def _check_a_clean_project_passes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        write_files(Path(tmp) / "planted-project", {"good.py": "VALUE = 1\n"})
        args = build_parser().parse_args(["--project-dir=planted-project"])
        assert _quiet(lambda: compile_selected(args, Path(tmp))) == EXIT_PASS, "a clean project must exit 0"


def _check_the_path_mode_finds_the_containing_package() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        package = Path(tmp) / "planted-package"
        write_files(package, {"pyproject.toml": "", "src/planted_package/routes/api.py": "VALUE = 1\n"})
        routes = package / "src" / "planted_package" / "routes"
        found = installable_ancestors([routes, routes / "api.py"])
        assert found == [package.resolve()], f"expected the one package root {package}, found {found}"
        assert installable_ancestors([Path(tmp)]) == [], "a directory outside any package must find no root"


def _check_nothing_selected_prints_usage_and_exits_2() -> None:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = compile_selected(build_parser().parse_args([]), WORKSPACE_DIR)
    assert code == EXIT_USAGE, f"no target must exit {EXIT_USAGE}, got {code}"
    assert out.getvalue().startswith("Usage:"), f"no target must print the usage, printed {out.getvalue()!r}"


def _check_a_missing_target_is_refused() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        for flag in ("--project-dir", "--path"):
            args = build_parser().parse_args([f"{flag}=no-such-project"])
            expect_usage_error(lambda: compile_selected(args, Path(tmp)), "Path not found")


def _check_both_modes_together_are_refused() -> None:
    args = build_parser().parse_args(["--all", "--path=datrix-common"])
    expect_usage_error(lambda: compile_selected(args, WORKSPACE_DIR), "not both")


def _run(args: argparse.Namespace) -> int:
    if args.debug:
        print_command()
    if args.self_test:
        checks = [
            _check_a_planted_syntax_error_fails,
            _check_a_clean_project_passes,
            _check_the_path_mode_finds_the_containing_package,
            _check_nothing_selected_prints_usage_and_exits_2,
            _check_a_missing_target_is_refused,
            _check_both_modes_together_are_refused,
        ]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=SCAN_SCRIPTS_DIR)
    return compile_selected(args, WORKSPACE_DIR)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
