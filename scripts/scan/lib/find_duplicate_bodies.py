#!/usr/bin/env python3
"""Report function bodies duplicated anywhere across the Datrix package source trees.

Walks every module-level function and class method in every ``datrix-*`` package's ``src/``
tree (``datrix_scripts.function_sources``), keeps those at or above the body floor, and groups
them two ways (``datrix_scripts.body_digest``):

- **exact**: identical docstring-free bodies, every name and constant kept -- a straight copy;
- **normalized**: identical once parameters and locals become positional tokens and constants
  collapse to their type -- a renamed copy. A normalized group whose members are exactly an
  exact group's is not repeated.

The shared-home body gate pins one slice of this (a copy of a PUBLIC shared-home function);
this report shows every group, including copies where neither side lives in a shared home --
the hoist candidates that gate cannot see. Report only: the exit code is 0 unless the scan
itself fails.

Usage:
    python find_duplicate_bodies.py [--cross-package] [--package NAME ...] [--limit N]
                                    [--json-out PATH] [--debug]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from datrix_scripts.behaviour_skeleton import SkeletonError
from datrix_scripts.body_digest import MIN_BODY_LINES, MIN_BODY_NODES, NormalizedFunction, qualifying_functions
from datrix_scripts.function_sources import collect_function_sources
from datrix_scripts.registered_targets import WORKSPACE_ROOT, discover_all_package_locations

logger = logging.getLogger(__name__)

EXIT_OK: Final[int] = 0
EXIT_SCAN_FAILED: Final[int] = 2
EXACT_KIND: Final[str] = "exact"
NORMALIZED_KIND: Final[str] = "normalized"
MIN_GROUP_SIZE: Final[int] = 2
JSON_INDENT: Final[int] = 1


@dataclass(frozen=True)
class DuplicateGroup:
    """Functions sharing one digest."""

    kind: str
    digest: str
    members: tuple[NormalizedFunction, ...]

    @property
    def packages(self) -> list[str]:
        return sorted({member.package for member in self.members})

    @property
    def is_cross_package(self) -> bool:
        return len(self.packages) > 1

    @property
    def duplicated_lines(self) -> int:
        """Lines that would disappear if every member but the first became a call to it."""
        return sum(member.line_count for member in self.members[1:])

    @property
    def identity(self) -> frozenset[tuple[Path, int]]:
        return frozenset(member.identity for member in self.members)


def scan(workspace_root: Path) -> list[NormalizedFunction]:
    """Every qualifying function of every discovered package.

    Raises:
        SkeletonError: A source file cannot be parsed -- named, never skipped.
    """
    functions: list[NormalizedFunction] = []
    for package, src_dir in sorted(discover_all_package_locations(workspace_root).items()):
        found = qualifying_functions(collect_function_sources(src_dir, package))
        logger.debug("%s: %d qualifying function(s)", package, len(found))
        functions.extend(found)
    return functions


def _groups(
    functions: Iterable[NormalizedFunction], kind: str, key: Callable[[NormalizedFunction], str]
) -> list[DuplicateGroup]:
    by_digest: dict[str, list[NormalizedFunction]] = defaultdict(list)
    for function in functions:
        by_digest[key(function)].append(function)
    return [
        DuplicateGroup(kind=kind, digest=digest, members=tuple(members))
        for digest, members in by_digest.items()
        if len(members) >= MIN_GROUP_SIZE
    ]


def duplicate_groups(functions: Sequence[NormalizedFunction]) -> list[DuplicateGroup]:
    """Exact groups, then normalized groups that are not already an exact group, largest first."""
    exact = _groups(functions, EXACT_KIND, lambda function: function.exact_digest)
    exact_identities = {group.identity for group in exact}
    normalized = [
        group
        for group in _groups(functions, NORMALIZED_KIND, lambda function: function.digest)
        if group.identity not in exact_identities
    ]
    return sorted(
        [*exact, *normalized],
        key=lambda group: (not group.is_cross_package, -group.duplicated_lines, group.kind, group.digest),
    )


def select_groups(
    groups: Sequence[DuplicateGroup], cross_package_only: bool, packages: frozenset[str]
) -> list[DuplicateGroup]:
    """The groups the caller asked to see."""
    selected = [group for group in groups if group.is_cross_package or not cross_package_only]
    if packages:
        selected = [group for group in selected if packages & set(group.packages)]
    return selected


def _member_line(member: NormalizedFunction, workspace_root: Path) -> str:
    path = member.file_path.relative_to(workspace_root).as_posix()
    return f"    {path}:{member.line_number} {member.qualified_name} ({member.line_count} lines)"


def print_report(
    groups: Sequence[DuplicateGroup], total_functions: int, limit: int, workspace_root: Path
) -> None:
    """Print a summary per kind and the first *limit* groups (0 = all)."""
    print(
        f"Scanned {total_functions} function(s) at or above the floor "
        f"({MIN_BODY_LINES} lines, {MIN_BODY_NODES} AST nodes)."
    )
    for kind in (EXACT_KIND, NORMALIZED_KIND):
        of_kind = [group for group in groups if group.kind == kind]
        cross = [group for group in of_kind if group.is_cross_package]
        print(
            f"{kind}: {len(of_kind)} group(s), {len(cross)} cross-package, "
            f"{sum(group.duplicated_lines for group in of_kind)} duplicated line(s)"
        )
    shown = groups if limit == 0 else groups[:limit]
    for group in shown:
        scope = "cross-package" if group.is_cross_package else "same-package"
        print(
            f"\n[{group.kind}] {len(group.members)} copies, {group.duplicated_lines} duplicated line(s), "
            f"{scope}: {', '.join(group.packages)}"
        )
        for member in group.members:
            print(_member_line(member, workspace_root))
    if len(shown) < len(groups):
        print(f"\n... {len(groups) - len(shown)} more group(s); pass --limit 0 to print every group.")


def write_json(groups: Sequence[DuplicateGroup], total_functions: int, path: Path, workspace_root: Path) -> None:
    """Write every selected group as JSON to *path*."""
    payload = {
        "functions_scanned": total_functions,
        "min_body_lines": MIN_BODY_LINES,
        "min_body_nodes": MIN_BODY_NODES,
        "groups": [
            {
                "kind": group.kind,
                "digest": group.digest,
                "packages": group.packages,
                "cross_package": group.is_cross_package,
                "duplicated_lines": group.duplicated_lines,
                "members": [
                    {
                        "package": member.package,
                        "path": member.file_path.relative_to(workspace_root).as_posix(),
                        "line": member.line_number,
                        "end_line": member.end_line_number,
                        "qualified_name": member.qualified_name,
                    }
                    for member in group.members
                ],
            }
            for group in groups
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=JSON_INDENT), encoding="utf-8")
    print(f"\nWrote {len(groups)} group(s) to {path}")


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cross-package", action="store_true", help="Show only groups spanning two or more packages.")
    parser.add_argument(
        "--package",
        action="append",
        default=[],
        help="Show only groups with a member in this package (import name, e.g. datrix_codegen_python). Repeatable.",
    )
    parser.add_argument("--limit", type=int, default=25, help="Groups to print (0 = all). Default: 25.")
    parser.add_argument("--json-out", type=Path, help="Also write every selected group to this JSON file.")
    parser.add_argument("--debug", action="store_true", help="Debug logging.")
    return parser.parse_args(argv)


def main(argv: Sequence[str]) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO, format="%(levelname)s: %(message)s")
    if args.limit < 0:
        logger.error("--limit must be 0 (all) or a positive count; got %d.", args.limit)
        return EXIT_SCAN_FAILED
    try:
        functions = scan(WORKSPACE_ROOT)
    except SkeletonError as exc:
        logger.error("%s", exc)
        return EXIT_SCAN_FAILED
    groups = select_groups(duplicate_groups(functions), args.cross_package, frozenset(args.package))
    print_report(groups, len(functions), args.limit, WORKSPACE_ROOT)
    if args.json_out is not None:
        write_json(groups, len(functions), args.json_out, WORKSPACE_ROOT)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
