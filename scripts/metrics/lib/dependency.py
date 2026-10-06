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
import sys
from pathlib import Path

try:
    import tomllib
except ImportError:
    tomllib = None # type: ignore[assignment]

from datrix_scripts.pyproject_deps import (  # noqa: E402
    build_dependency_graph,
    discover_packages,
)


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
