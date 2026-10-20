"""Report function bodies duplicated anywhere across the Datrix package source trees.

The module behind ``scan/find-duplicate-bodies.ps1`` (and its ``.sh`` twin); the editable installs
are checked first. Walks every module-level function and class method in every ``datrix-*``
package's ``src/`` tree (``datrix_scripts.function_sources``), keeps those at or above the body
floor, and groups them two ways (``datrix_scripts.body_digest``):

- **exact**: identical docstring-free bodies, every name and constant kept -- a straight copy;
- **normalized**: identical once parameters and locals become positional tokens and constants
  collapse to their type -- a renamed copy. A normalized group whose members are exactly an
  exact group's is not repeated.

The shared-home body gate pins one slice of this (a copy of a PUBLIC shared-home function);
this report shows every group, including copies where neither side lives in a shared home --
the hoist candidates that gate cannot see. Report only: the exit code is 0 unless the scan
itself fails (2 = a source file did not parse, or a bad argument; 1 = the package install check
failed).

Usage:
    python -m datrix_scripts.scan.find_duplicate_bodies [--cross-package] [--package NAME ...]
                                                        [--limit N] [--json-out PATH] [--dbg]
    python -m datrix_scripts.scan.find_duplicate_bodies --self-test
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import logging
import os
import sys
import tempfile
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from datrix_scripts.behaviour_skeleton import SkeletonError
from datrix_scripts.body_digest import MIN_BODY_LINES, MIN_BODY_NODES, NormalizedFunction, qualifying_functions
from datrix_scripts.function_sources import collect_function_sources
from datrix_scripts.gate_harness import EXIT_VIOLATION, WRAPPER_DEBUG_FLAG, write_files
from datrix_scripts.registered_targets import WORKSPACE_ROOT, discover_all_package_locations
from datrix_scripts.dev.arguments import comma_values
from datrix_scripts.test.wrappers import SCAN_SCRIPTS_DIR, module_main, run_self_test

logger = logging.getLogger(__name__)

MODULE: Final = "datrix_scripts.scan.find_duplicate_bodies"
WRAPPER: Final = "find-duplicate-bodies"
EXIT_OK: Final[int] = 0
EXIT_SCAN_FAILED: Final[int] = 2
EXACT_KIND: Final[str] = "exact"
NORMALIZED_KIND: Final[str] = "normalized"
MIN_GROUP_SIZE: Final[int] = 2
JSON_INDENT: Final[int] = 1
DEFAULT_LIMIT: Final[int] = 25

#: One function above the body floor, planted in two packages by the self-test (renamed in the third).
_PLANTED_BODY: Final = '''
def {name}(items, limit):
    totals = {{}}
    for item in items:
        key = item.strip().lower()
        if not key:
            continue
        totals[key] = totals.get(key, 0) + 1
        if len(totals) > limit:
            raise ValueError("too many keys: " + str(len(totals)))
    ordered = sorted(totals.items(), key=lambda pair: (-pair[1], pair[0]))
    return [name for name, count in ordered if count > 1]
'''
_RENAMED_BODY: Final = '''
def {name}(entries, ceiling):
    counts = {{}}
    for entry in entries:
        word = entry.strip().lower()
        if not word:
            continue
        counts[word] = counts.get(word, 0) + 1
        if len(counts) > ceiling:
            raise ValueError("too many words: " + str(len(counts)))
    ranked = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    return [name for name, count in ranked if count > 1]
'''


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


def report(args: argparse.Namespace, workspace_root: Path) -> int:
    """Scan *workspace_root*, print the groups *args* select (and write them as JSON); the exit code."""
    if args.limit < 0:
        logger.error("--limit must be 0 (all) or a positive count; got %d.", args.limit)
        return EXIT_SCAN_FAILED
    try:
        functions = scan(workspace_root)
    except SkeletonError as exc:
        logger.error("%s", exc)
        return EXIT_SCAN_FAILED
    groups = select_groups(duplicate_groups(functions), args.cross_package, frozenset(comma_values(args.package)))
    print_report(groups, len(functions), args.limit, workspace_root)
    if args.json_out is not None:
        write_json(groups, len(functions), args.json_out, workspace_root)
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    """The options of ``scan/find-duplicate-bodies.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        prog=WRAPPER, description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False
    )
    parser.add_argument("--cross-package", action="store_true", help="Show only groups spanning two or more packages.")
    parser.add_argument(
        "--package",
        action="append",
        default=[],
        help="Show only groups with a member in this package (import name, e.g. datrix_codegen_python). "
             "Repeatable and/or comma-separated.",
    )
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                        help=f"Groups to print (0 = all). Default: {DEFAULT_LIMIT}.")
    parser.add_argument("--json-out", type=Path, help="Also write every selected group to this JSON file.")
    parser.add_argument(WRAPPER_DEBUG_FLAG, dest="debug", action="store_true",
                        help="Debug logging (per-package function counts).")
    parser.add_argument("--self-test", action="store_true",
                        help="Run only the self-test: a planted copy and a planted renamed copy are grouped, "
                             "-Package and -CrossPackage select, a negative -Limit is refused, and the wrapper "
                             "seam holds.")
    return parser


def _planted_workspace(root: Path) -> None:
    """Three packages: one function copied verbatim into two, and renamed in the third."""
    write_files(root, {
        "datrix-alpha/src/datrix_alpha/__init__.py": "",
        "datrix-alpha/src/datrix_alpha/counting.py": _PLANTED_BODY.format(name="repeated_keys"),
        "datrix-beta/src/datrix_beta/__init__.py": "",
        "datrix-beta/src/datrix_beta/counting.py": _PLANTED_BODY.format(name="repeated_keys"),
        "datrix-gamma/src/datrix_gamma/__init__.py": "",
        "datrix-gamma/src/datrix_gamma/words.py": _RENAMED_BODY.format(name="repeated_words"),
    })


def _reported(argv: Sequence[str], root: Path) -> tuple[int, str]:
    """``report`` on *root* with *argv*: the exit code and what it printed."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = report(build_parser().parse_args(argv), root)
    return code, out.getvalue()


def _check_planted_copies_are_grouped() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        _planted_workspace(root)
        code, out = _reported(["--limit=0"], root)
    assert code == EXIT_OK, f"a report must exit {EXIT_OK}; got {code}: {out!r}"
    assert "Scanned 3 function(s)" in out, f"the three planted functions must qualify: {out!r}"
    assert "[exact] 2 copies" in out and "datrix_alpha, datrix_beta" in out, f"the verbatim copy is an exact group: {out!r}"
    assert "[normalized] 3 copies" in out and "repeated_words" in out, f"the renamed copy joins a normalized group: {out!r}"


def _check_package_and_cross_package_select() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        _planted_workspace(root)
        json_path = root / "out" / "groups.json"
        _, gamma = _reported(["--package=datrix_gamma", f"--json-out={json_path}"], root)
        written = json.loads(json_path.read_text(encoding="utf-8"))
        _, either = _reported(["--package=datrix_gamma,datrix_alpha", "--cross-package"], root)
    assert "[exact]" not in gamma and "[normalized] 3 copies" in gamma, f"-Package keeps only groups it is in: {gamma!r}"
    assert [group["kind"] for group in written["groups"]] == [NORMALIZED_KIND], f"the JSON holds the selection: {written}"
    assert "[exact] 2 copies" in either, f"a comma-separated -Package selects each name: {either!r}"


def _check_a_negative_limit_is_refused() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        code, _ = _reported(["--limit=-1"], Path(tmp))
    assert code == EXIT_SCAN_FAILED, f"a negative -Limit must exit {EXIT_SCAN_FAILED}; got {code}"


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        checks = [
            _check_planted_copies_are_grouped,
            _check_package_and_cross_package_select,
            _check_a_negative_limit_is_refused,
        ]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=SCAN_SCRIPTS_DIR)
    from datrix_scripts.test.test import ensure_packages
    from datrix_scripts.venv import require_packages

    if not ensure_packages(os.environ, require_packages):
        return EXIT_VIOLATION
    return report(args, WORKSPACE_ROOT)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
