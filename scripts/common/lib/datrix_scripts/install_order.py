#!/usr/bin/env python3
"""
Compute the datrix-* package install order for the shared venv.

Derives install order from each discovered package's declared datrix-* runtime
dependencies ([project.dependencies] in pyproject.toml) via Kahn's algorithm
(graphlib.TopologicalSorter, the standard-library implementation -- never a
hand-rolled in-degree counter), instead of a hand-kept literal order. Ties are
broken alphabetically by package name for determinism. A cycle among declared
dependencies, or a declared datrix-* dependency missing from disk, fails
loudly naming every package involved -- it never silently falls back to
alphabetical order.

Usage (PYTHONPATH=scripts/common/lib; common/venv.ps1 sets it):
    python -m datrix_scripts.install_order --workspace-root D:\\datrix [--packages datrix-common datrix-cli ...]
    python -m datrix_scripts.install_order --self-test
"""

from __future__ import annotations

import argparse
import heapq
import json
import sys
import tempfile
from graphlib import CycleError, TopologicalSorter
from pathlib import Path

from datrix_scripts.pyproject_deps import (
    DATRIX_PREFIX,
    build_dependency_graph,
    discover_packages,
    parse_package_name,
    read_project_dependencies,
)


class InstallOrderError(Exception):
    """A cycle or a missing datrix-* dependency makes install order undecidable."""


def topological_install_order(packages: dict[str, Path]) -> list[str]:
    """Kahn's-algorithm install order over declared datrix-* dependencies.

    Raises InstallOrderError naming every offending package if a declared
    datrix-* dependency is missing from disk, or if the graph has a cycle.

    Ordering is delegated to graphlib.TopologicalSorter, driven one node at a
    time through a heap keyed by package name so ties break alphabetically --
    consuming ts.get_ready() a whole batch at a time would only let a
    newly-freed node compete starting the *next* batch, which is not the same
    ordering. A cycle is reported from TopologicalSorter.prepare()'s own
    CycleError, which names only the true cycle's members, rather than being
    inferred from a length mismatch between the input and the computed order
    (a mismatch would also catch every package merely blocked behind the
    cycle, not just the cycle itself).
    """
    for name, project_root in packages.items():
        pyproject = project_root / "pyproject.toml"
        try:
            specs = read_project_dependencies(pyproject)
        except (OSError, ValueError) as exc:
            raise InstallOrderError(
                f"{name}: cannot read dependencies from {pyproject}: {exc}"
            ) from exc
        for spec in specs:
            dep_name = parse_package_name(spec)
            if dep_name.startswith(DATRIX_PREFIX) and dep_name not in packages:
                raise InstallOrderError(
                    f"{name} declares dependency '{dep_name}' in [project.dependencies], "
                    f"but no '{dep_name}' directory with a pyproject.toml exists under the "
                    "workspace root. Install order cannot be computed."
                )

    package_names, edges = build_dependency_graph(packages)
    predecessors: dict[str, set[str]] = {name: set() for name in package_names}
    for pkg, dep in edges:
        predecessors[pkg].add(dep)

    sorter: TopologicalSorter[str] = TopologicalSorter(predecessors)
    try:
        sorter.prepare()
    except CycleError as exc:
        cycle_members = sorted(set(exc.args[1]))
        raise InstallOrderError(
            "Cycle detected among datrix-* package [project.dependencies]; install order "
            f"cannot be computed. Packages involved: {', '.join(cycle_members)}."
        ) from exc

    ready: list[str] = []
    order: list[str] = []
    while sorter.is_active():
        for name in sorter.get_ready():
            heapq.heappush(ready, name)
        current = heapq.heappop(ready)
        order.append(current)
        sorter.done(current)
    return order


# ---------------------------------------------------------------------------
# Self-Test (--self-test)
# ---------------------------------------------------------------------------


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _ok(message: str) -> None:
    print(f"[OK] {message}")


def _fail(message: str) -> None:
    print(f"[FAIL] {message}")


def _plant_order_fixture(root: Path) -> None:
    # "zulu" sorts AFTER "acme" alphabetically but has no dependencies, while
    # "acme" depends on "zulu" -- zulu must install BEFORE acme despite
    # sorting after it. Mirrors the real datrix-codegen-kernel /
    # datrix-codegen-common case the design doc cites. "beta" is an unrelated
    # zero-dependency package proving ties break alphabetically.
    _write(
        root / "datrix-selftest-acme" / "pyproject.toml",
        '[project]\nname = "datrix-selftest-acme"\nversion = "0.0.0"\n'
        'dependencies = ["datrix-selftest-zulu>=1"]\n',
    )
    _write(
        root / "datrix-selftest-zulu" / "pyproject.toml",
        '[project]\nname = "datrix-selftest-zulu"\nversion = "0.0.0"\ndependencies = []\n',
    )
    _write(
        root / "datrix-selftest-beta" / "pyproject.toml",
        '[project]\nname = "datrix-selftest-beta"\nversion = "0.0.0"\ndependencies = []\n',
    )


def _plant_cycle_fixture(root: Path) -> None:
    _write(
        root / "datrix-selftest-cycle-a" / "pyproject.toml",
        '[project]\nname = "datrix-selftest-cycle-a"\nversion = "0.0.0"\n'
        'dependencies = ["datrix-selftest-cycle-b>=1"]\n',
    )
    _write(
        root / "datrix-selftest-cycle-b" / "pyproject.toml",
        '[project]\nname = "datrix-selftest-cycle-b"\nversion = "0.0.0"\n'
        'dependencies = ["datrix-selftest-cycle-a>=1"]\n',
    )


def _plant_missing_dep_fixture(root: Path) -> None:
    _write(
        root / "datrix-selftest-orphan" / "pyproject.toml",
        '[project]\nname = "datrix-selftest-orphan"\nversion = "0.0.0"\n'
        'dependencies = ["datrix-selftest-nonexistent>=1"]\n',
    )


def _run_order_fixture_checks() -> bool:
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "order"
        root.mkdir()
        _plant_order_fixture(root)
        packages = discover_packages(root)
        order = topological_install_order(packages)
        zulu_idx = order.index("datrix-selftest-zulu")
        acme_idx = order.index("datrix-selftest-acme")
        ok &= _fail_or_ok(
            zulu_idx < acme_idx,
            "dependency installs before its dependent even though it sorts after it "
            f"alphabetically (got order {order})",
        )
        ok &= _fail_or_ok(
            order.index("datrix-selftest-beta") >= 0,
            "unrelated zero-dependency package appears in the order",
        )
        # beta has no dependency relationship to acme/zulu, so among the
        # zero-in-degree starters (beta, zulu) alphabetical order applies.
        ok &= _fail_or_ok(
            order.index("datrix-selftest-beta") < order.index("datrix-selftest-acme"),
            f"ties among ready packages break alphabetically (got order {order})",
        )
    return ok


def _run_cycle_fixture_check() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "cycle"
        root.mkdir()
        _plant_cycle_fixture(root)
        packages = discover_packages(root)
        try:
            topological_install_order(packages)
            _fail("a cycle silently produced an order instead of raising")
            return False
        except InstallOrderError as exc:
            named_both = (
                "datrix-selftest-cycle-a" in str(exc) and "datrix-selftest-cycle-b" in str(exc)
            )
            return _fail_or_ok(named_both, f"cycle error names both members: {exc}")


def _run_missing_dep_fixture_check() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "missing"
        root.mkdir()
        _plant_missing_dep_fixture(root)
        packages = discover_packages(root)
        try:
            topological_install_order(packages)
            _fail("a missing datrix-* dependency silently produced an order instead of raising")
            return False
        except InstallOrderError as exc:
            return _fail_or_ok(
                "datrix-selftest-nonexistent" in str(exc),
                f"missing-dependency error names the missing package: {exc}",
            )


def run_self_test() -> bool:
    ok = _run_order_fixture_checks()
    ok &= _run_cycle_fixture_check()
    ok &= _run_missing_dep_fixture_check()

    print()
    print("SELF-TEST PASSED" if ok else "SELF-TEST FAILED: see failures above.")
    return ok


def _fail_or_ok(condition: bool, label: str) -> bool:
    (_ok if condition else _fail)(label)
    return condition


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--workspace-root", type=Path, default=None)
    parser.add_argument("--packages", type=str, nargs="*", metavar="PKG", help="Restrict to these package names.")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return 0 if run_self_test() else 1

    if args.workspace_root is None:
        print("Error: --workspace-root is required unless --self-test.", file=sys.stderr)
        return 2

    workspace_root = args.workspace_root.resolve()
    packages = discover_packages(workspace_root)
    if args.packages:
        missing = set(args.packages) - set(packages.keys())
        if missing:
            print(f"Error: unknown package(s): {sorted(missing)}.", file=sys.stderr)
            return 2

    # Topological validity is computed against the FULL discovered package set
    # even when --packages restricts the output below -- filtering `packages`
    # here first would silently hide a cycle or missing dependency involving a
    # package outside the restricted set.
    try:
        order = topological_install_order(packages)
    except InstallOrderError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.packages:
        restrict = set(args.packages)
        order = [name for name in order if name in restrict]

    print(json.dumps(order))
    return 0


if __name__ == "__main__":
    sys.exit(main())
