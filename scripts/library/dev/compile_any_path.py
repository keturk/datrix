#!/usr/bin/env python3
"""
Compile (syntax + import check) for any Python path: files or directories.

Unlike compile.py, which only runs import checks when given an installable package root,
this script accepts any path(s). For each path it finds the containing installable package
(by walking up to a directory with src/ and pyproject.toml or setup.py) and runs compile.py
on that package. So passing a subfolder (e.g. .../routes) still triggers the full package
syntax and import check and catches missing imports like db or Book.

Usage:
  python scripts/library/dev/compile_any_path.py <path> [path ...] [--debug]
  .\\scripts\\dev\\compile-any-path.ps1 .\\.generated\\...\\routes
"""

import argparse
import subprocess
import sys
from pathlib import Path


def is_installable_package(project_root: Path) -> bool:
    """True if project_root has src/ and pyproject.toml or setup.py."""
    if not project_root.is_dir():
        return False
    return (project_root / "src").is_dir() and (
        (project_root / "pyproject.toml").is_file() or (project_root / "setup.py").is_file()
    )


def find_installable_ancestor(path: Path) -> Path | None:
    """
    Walk up from path until an installable package root is found.

    When the user passes a subfolder (e.g. .../library_book_service/src/.../routes),
    this finds the package root so we can run compile.py on it.
    """
    current = Path(path).resolve()
    if current.is_file():
        current = current.parent
    while current != current.parent:
        if is_installable_package(current):
            return current
        current = current.parent
    return None


def main() -> int:
    """Resolve paths to installable package roots and invoke compile.py."""
    parser = argparse.ArgumentParser(
        description="Compile (syntax + import check) for any Python path(s)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "paths",
        nargs="+",
        type=str,
        help="File or directory paths; resolved to containing package root for compile.py",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug output")

    args = parser.parse_args()

    paths_to_check = [Path(p) for p in args.paths]
    import_roots: list[Path] = []
    seen: set[Path] = set()
    for path in paths_to_check:
        path_obj = Path(path)
        if not path_obj.exists():
            print(f"Warning: Path does not exist: {path_obj}", file=sys.stderr)
            continue
        path_obj = path_obj.resolve()
        if path_obj.is_file():
            path_obj = path_obj.parent
        root = find_installable_ancestor(path_obj)
        if root is not None and root not in seen:
            seen.add(root)
            import_roots.append(root)

    if not import_roots:
        print("No installable package root found for the given path(s).")
        print("Paths must be inside a directory that has src/ and pyproject.toml (or setup.py).")
        return 0

    compile_py = Path(__file__).resolve().parent / "compile.py"
    if not compile_py.is_file():
        print(f"Error: compile.py not found at {compile_py}", file=sys.stderr)
        return 1

    cmd = [sys.executable, str(compile_py)] + [str(r) for r in import_roots]
    if args.debug:
        cmd.append("--debug")

    result = subprocess.run(cmd)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
