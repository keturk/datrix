#!/usr/bin/env python3
"""
Compile all Python scripts in Datrix project folders.

Discovers all .py files under given directories (or all datrix* repos when no paths
are passed), runs py_compile for syntax checking, and optionally runs a top-level
import check for each installable package to surface import issues.

Usage:
  python scripts/library/dev/compile.py [path ...] [--debug]
  .\\scripts\\dev\\compile.ps1
  .\\scripts\\dev\\compile.ps1 D:\\datrix\\datrix-common -Dbg
"""

import argparse
import io
import os
import py_compile
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import NamedTuple

# Configure UTF-8 encoding for stdout/stderr on Windows
if sys.platform == "win32":
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Add library directory to sys.path to import from shared
library_dir = Path(__file__).resolve().parent.parent
if library_dir.exists() and str(library_dir) not in sys.path:
    sys.path.insert(0, str(library_dir))

from shared.venv import get_datrix_root

# Directories to skip during file discovery (same as syntax_checker)
_SKIP_DIRS = frozenset({
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "build", "dist", ".tox", ".mypy_cache", ".pytest_cache",
    ".eggs", ".ruff_cache",
})


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


def directory_to_package_name(dir_name: str) -> str:
    """Convert project directory name to importable package name (e.g. datrix-common -> datrix_common)."""
    return dir_name.replace("-", "_")


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
        for i, file_path in enumerate(py_files):
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


def check_import(
    project_root: Path,
    package_name: str,
    pythonpath_entries: list[Path] | None = None,
    timeout: int = 60,
) -> ImportErrorResult | None:
    """
    Import the package and all its submodules so cross-package imports (e.g. from datrix_language.parser)
    are exercised. Uses pythonpath_entries to set PYTHONPATH so sibling packages are resolvable.
    """
    env = os.environ.copy()
    if pythonpath_entries:
        src_dirs = [str(p / "src") for p in pythonpath_entries if (p / "src").is_dir()]
        if src_dirs:
            env["PYTHONPATH"] = os.pathsep.join(src_dirs)
    script = _make_import_check_script(package_name)
    try:
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=project_root,
            timeout=timeout,
            env=env,
        )
        if result.returncode == 0:
            return None
        err = (result.stderr or result.stdout or "import failed").strip()
        if not err:
            err = "import failed (no output)"
        return ImportErrorResult(project_root, package_name, err)
    except subprocess.TimeoutExpired:
        return ImportErrorResult(project_root, package_name, "import timed out")
    except Exception as e:
        return ImportErrorResult(project_root, package_name, f"{type(e).__name__}: {e}")


def run_import_checks(project_roots: list[Path], debug: bool) -> list[ImportErrorResult]:
    """
    For each installable package under project_roots, run an import check that also loads all
    submodules so cross-package imports (e.g. from datrix_language.parser) are exercised.
    PYTHONPATH is set to all installable projects' src dirs so sibling packages resolve.
    """
    roots = [Path(r) for r in project_roots if Path(r).is_dir()]
    installable = get_all_installable_roots(roots)
    if not installable:
        return []

    # PYTHONPATH: requested packages first (so e.g. .generated/.../library_book_service is importable), then monorepo
    try:
        datrix_root = get_datrix_root()
        all_installable = sorted(
            d for d in datrix_root.iterdir()
            if d.is_dir() and d.name.startswith("datrix") and is_installable_package(d)
        )
    except FileNotFoundError:
        all_installable = []
    combined = list(installable) + (all_installable or [])
    pythonpath_roots = list(dict.fromkeys(combined))

    errors: list[ImportErrorResult] = []
    for path in installable:
        pkg = directory_to_package_name(path.name)
        if debug:
            print(f"[DEBUG] Import check: {pkg} at {path} (PYTHONPATH={len(pythonpath_roots)} src dirs)", file=sys.stderr)
        err = check_import(path, pkg, pythonpath_entries=pythonpath_roots)
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


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Compile all Python in Datrix project folders (syntax and import check)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=str,
        help="Directory paths to check (default: all datrix repositories)",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug output")

    args = parser.parse_args()

    if args.paths:
        paths_to_check = [Path(p) for p in args.paths]
    else:
        try:
            datrix_root = get_datrix_root()
            paths_to_check = sorted(
                d for d in datrix_root.iterdir()
                if d.is_dir() and d.name.startswith("datrix")
            )
        except FileNotFoundError:
            print("ERROR: Could not find Datrix root directory", file=sys.stderr)
            return 1

    print("Discovering Python files...", flush=True)
    all_py_files: list[Path] = []
    for path in paths_to_check:
        path_obj = Path(path)
        if not path_obj.exists():
            print(f"Warning: Path does not exist: {path_obj}", file=sys.stderr)
            continue
        found = find_py_files(path_obj, _SKIP_DIRS)
        if found:
            print(f"  {path_obj.name}: {len(found)} files", flush=True)
        all_py_files.extend(found)

    if not all_py_files:
        print("No Python files found to check.")
        return 0

    print(f"Found {len(all_py_files)} Python file(s) total.", flush=True)
    print("Checking syntax...", flush=True)

    syntax_errors = check_syntax(all_py_files, args.debug)
    print("Checking imports (packages + submodules, cross-project)...", flush=True)
    import_errors = run_import_checks(paths_to_check, args.debug)

    report(all_py_files, syntax_errors, import_errors)

    if syntax_errors or import_errors:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
