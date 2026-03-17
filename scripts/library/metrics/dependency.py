#!/usr/bin/env python3
"""
Report dependency relationships between Datrix packages from pyproject.toml.

Reads [project].dependencies from each datrix-* package under the workspace root
and reports which packages depend on which (datrix-to-datrix only).

Modes:
    tree - Print a tree: each package with its direct datrix dependencies (indented).
    list - Print one edge per line: "package -> dependency".
    json - Machine-readable: packages list and edges array.

Usage:
    python dependency.py --workspace-root D:\\datrix --mode tree
    python dependency.py --workspace-root D:\\datrix --mode list
    python dependency.py --workspace-root D:\\datrix --mode json --packages datrix-common datrix-language
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import tomllib
except ImportError:
    tomllib = None # type: ignore[assignment]

DATRIX_PREFIX = "datrix-"


def _parse_package_name(spec: str) -> str:
    """Extract package name from a dependency spec (e.g. 'datrix-common>=1.0.0' -> 'datrix-common')."""
    return re.split(r"\s*[\[\]<>!=~]", spec.strip(), maxsplit=1)[0].strip()


def _get_project_dependencies(pyproject_path: Path) -> list[str]:
    """Read [project].dependencies from pyproject.toml and return dependency spec strings."""
    if not pyproject_path.is_file():
        return []
    try:
        if tomllib is None:
            return []
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
    except (OSError, ValueError):
        return []
    deps = data.get("project", {}).get("dependencies", [])
    if not isinstance(deps, list):
        return []
    return [s for s in deps if isinstance(s, str)]


def discover_packages(workspace_root: Path) -> dict[str, Path]:
    """Return dict of package name -> project root for each datrix-* dir with pyproject.toml."""
    result: dict[str, Path] = {}
    if not workspace_root.is_dir():
        return result
    for child in workspace_root.iterdir():
        if not child.is_dir() or not child.name.startswith(DATRIX_PREFIX):
            continue
        pyproject = child / "pyproject.toml"
        if pyproject.is_file():
            result[child.name] = child
    return dict(sorted(result.items()))


def build_dependency_graph(
    packages: dict[str, Path],
) -> tuple[list[str], list[tuple[str, str]]]:
    """
    Build datrix-to-datrix dependency graph from pyproject.toml files.

    Returns (list of package names, list of (package, dependency) edges).
    """
    package_names = list(packages.keys())
    edges: list[tuple[str, str]] = []
    for name, project_root in packages.items():
        pyproject = project_root / "pyproject.toml"
        for spec in _get_project_dependencies(pyproject):
            dep_name = _parse_package_name(spec)
            if dep_name.startswith(DATRIX_PREFIX) and dep_name in packages and dep_name != name:
                edges.append((name, dep_name))
    edges.sort(key=lambda e: (e[0], e[1]))
    return package_names, edges


def run_tree(package_names: list[str], edges: list[tuple[str, str]], verbose: bool) -> None:
    """Print a tree: each package with its direct datrix dependencies indented."""
    deps_by_package: dict[str, list[str]] = {p: [] for p in package_names}
    for pkg, dep in edges:
        deps_by_package[pkg].append(dep)
    for pkg in sorted(package_names):
        print(pkg)
        for dep in sorted(deps_by_package[pkg]):
            print(f"  {dep}")
        if verbose and not deps_by_package[pkg]:
            pass  # no extra line for leaf


def run_list_edges(edges: list[tuple[str, str]]) -> None:
    """Print one 'package -> dependency' per line."""
    for pkg, dep in edges:
        print(f"{pkg} -> {dep}")


def run_json(package_names: list[str], edges: list[tuple[str, str]]) -> None:
    """Print JSON with packages and edges."""
    obj = {
        "packages": sorted(package_names),
        "edges": [list(e) for e in edges],
    }
    print(json.dumps(obj, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(
    description="Datrix package dependency graph from pyproject.toml.",
    )
    parser.add_argument(
    "--workspace-root",
    type=Path,
    required=True,
    help="Path to workspace root (parent of datrix-common, datrix-language, etc.).",
    )
    parser.add_argument(
    "--mode",
    choices=("tree", "list", "json"),
    default="tree",
    help="Output mode: tree, list, json (default: tree).",
    )
    parser.add_argument(
    "--packages",
    type=str,
    nargs="*",
    metavar="PKG",
    help="Restrict to these package names (default: all datrix-* packages).",
    )
    parser.add_argument("--verbose", action="store_true", help="Verbose output.")
    parser.add_argument(
    "--debug",
    action="store_true",
    help="Debug output.",
    )

    args = parser.parse_args()
    if tomllib is None:
        print(
            "Error: tomllib is required (Python 3.11+).",
            file=sys.stderr,
        )
        return 2

    workspace_root = args.workspace_root.resolve()
    if not workspace_root.is_dir():
        print(
            f"Error: workspace root is not a directory: {workspace_root}",
            file=sys.stderr,
        )
        return 1

    packages = discover_packages(workspace_root)
    if not packages:
        print(
            f"Error: no datrix-* packages with pyproject.toml found under {workspace_root}",
            file=sys.stderr,
        )
        return 1

    selected: set[str] | None = None
    if args.packages:
        missing = set(args.packages) - set(packages.keys())
        if missing:
            print(
                f"Error: unknown package(s): {sorted(missing)}. Available: {sorted(packages.keys())}",
                file=sys.stderr,
            )
            return 1
        selected = set(args.packages)

    package_names, edges = build_dependency_graph(packages)

    if selected is not None:
        package_names = [p for p in package_names if p in selected]
        edges = [e for e in edges if e[0] in selected]

    if args.mode == "tree":
        run_tree(package_names, edges, args.verbose or args.debug)
    elif args.mode == "list":
        run_list_edges(edges)
    else:
        run_json(package_names, edges)
    return 0


if __name__ == "__main__":
    sys.exit(main())
