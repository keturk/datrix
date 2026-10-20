"""Report dependency relationships between Datrix packages from pyproject.toml.

Reads [project].dependencies from each datrix-* package under the workspace root
and reports which packages depend on which (datrix-to-datrix), or which third-party
runtime dependencies each package declares.

Modes:
    tree        - Print a tree: each package with its direct datrix dependencies (indented).
    list        - Print one edge per line: "package -> dependency".
    json        - Machine-readable: packages list and edges array.
    third-party - Every non-datrix runtime dependency with each declaring package and its
                  spec; SPEC DRIFT marks a dependency whose specifiers differ by package.

Run by ``metrics/dependency.ps1`` (POSIX twin ``dependency.sh``): package names positionally or as
``--projects``, or ``--all``; ``--mode``; ``--verbose-output`` / ``--dbg`` (debug logging, which names
the packages discovered); ``--self-test``. Exit 0 = report printed, 1 = nothing to report on (usage, an
unknown package, the showcase repo alone, no package found).
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import logging
import sys
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Final

from datrix_scripts.framework_repos import PackageMarker
from datrix_scripts.gate_harness import WRAPPER_DEBUG_FLAG
from datrix_scripts.metrics.projects import (
    DEFAULT_WORDING,
    EXIT_FAILED,
    EXIT_PASSED,
    SHOWCASE,
    ProjectSelectionError,
    SelectionWording,
    add_project_arguments,
    print_stderr,
    select_projects,
)
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.pyproject_deps import (
    build_dependency_graph,
    discover_packages,
    third_party_dependencies,
)
from datrix_scripts.test.wrappers import METRICS_SCRIPTS_DIR, module_main, run_self_test

logger = logging.getLogger(__name__)

MODULE: Final = "datrix_scripts.metrics.dependency"
WRAPPER: Final = "dependency"
MODE_TREE: Final = "tree"
MODE_LIST: Final = "list"
MODE_JSON: Final = "json"
MODE_THIRD_PARTY: Final = "third-party"
MODES: Final = (MODE_TREE, MODE_LIST, MODE_JSON, MODE_THIRD_PARTY)
#: The packages the report reads: a ``datrix-*`` directory holding a ``pyproject.toml``.
_PYPROJECT_PACKAGES: Final = frozenset({PackageMarker.PYPROJECT})

USAGE_LINES: Final = (
    "Usage:",
    " .\\dependency.ps1 -All [options]",
    " .\\dependency.ps1 <package> [package ...] [options]",
    "",
    "Examples:",
    " .\\dependency.ps1 -All",
    " .\\dependency.ps1 -All -Mode list",
    " .\\dependency.ps1 -All -Mode json",
    " .\\dependency.ps1 datrix-common datrix-language -Mode tree",
    "",
    "Parameters:",
    " -Mode tree | list | json | third-party (default: tree)",
    " -All Include all datrix-* packages",
    " -VerboseOutput Verbose output",
    " -Dbg Debug output",
)
#: ``-All`` is never refused here (the report finds the packages itself), so ``none_found`` is not printed.
WORDING: Final = SelectionWording(
    none_found=DEFAULT_WORDING.none_found,
    none_valid=f"ERROR: No valid projects specified ({SHOWCASE} is excluded).",
    none_given_heading=("",),
    list_available=True,
    available_heading="Available packages:",
)


def run_tree(package_names: list[str], edges: list[tuple[str, str]]) -> None:
    """Print a tree: each package with its direct datrix dependencies indented."""
    deps_by_package: dict[str, list[str]] = {p: [] for p in package_names}
    for pkg, dep in edges:
        deps_by_package[pkg].append(dep)
    for pkg in sorted(package_names):
        print(pkg)
        for dep in sorted(deps_by_package[pkg]):
            print(f"  {dep}")


def run_list_edges(edges: list[tuple[str, str]]) -> None:
    """Print one 'package -> dependency' per line."""
    for pkg, dep in edges:
        print(f"{pkg} -> {dep}")


def run_third_party(packages: dict[str, Path], selected: set[str] | None) -> None:
    """Print every non-datrix runtime dependency with the packages declaring it.

    A dependency whose specifiers differ between packages is marked SPEC DRIFT: the shared
    venv resolves one version, so differing pins mean some package is tested against a
    version its own declaration does not describe.
    """
    owners = third_party_dependencies(packages)
    shown = 0
    for dep_name, declarations in owners.items():
        if selected is not None:
            declarations = [entry for entry in declarations if entry[0] in selected]
        if not declarations:
            continue
        shown += 1
        specs = {spec for _, spec in declarations}
        marker = "  SPEC DRIFT" if len(specs) > 1 else ""
        print(f"{dep_name}{marker}")
        for package, spec in sorted(declarations):
            print(f"  {package}: {spec}")
    print(f"\n{shown} third-party runtime dependenc{'y' if shown == 1 else 'ies'}.")


def run_json(package_names: list[str], edges: list[tuple[str, str]]) -> None:
    """Print JSON with packages and edges."""
    obj = {
        "packages": sorted(package_names),
        "edges": [list(e) for e in edges],
    }
    print(json.dumps(obj, indent=2))


def run_graph(packages: dict[str, Path], selected: set[str] | None, mode: str) -> None:
    """Print the datrix-to-datrix graph in *mode* (tree, list or json), narrowed to *selected*."""
    package_names, edges = build_dependency_graph(packages)
    if selected is not None:
        package_names = [p for p in package_names if p in selected]
        edges = [e for e in edges if e[0] in selected]
    if mode == MODE_TREE:
        run_tree(package_names, edges)
    elif mode == MODE_LIST:
        run_list_edges(edges)
    else:
        run_json(package_names, edges)


def _selection(args: argparse.Namespace, workspace: Path) -> set[str] | None:
    """The packages to report on (None: every one), the line announcing them printed.

    Raises:
        ProjectSelectionError: Names were given but every one was the showcase repo, or nothing was given.
    """
    if args.all:
        print(f"Dependency (mode={args.mode}) for all Datrix packages")
        return None
    names = select_projects(args, workspace, usage=USAGE_LINES, any_of=_PYPROJECT_PACKAGES, wording=WORDING)
    print(f"Dependency (mode={args.mode}) for: {', '.join(names)}")
    return set(names)


def run_dependency(args: argparse.Namespace, workspace: Path) -> int:
    """The wrapper's run over *workspace*: select, then print the report in ``--mode``."""
    try:
        selected = _selection(args, workspace)
    except ProjectSelectionError as exc:
        for line in exc.lines:
            print(line)
        return EXIT_FAILED
    packages = discover_packages(workspace)
    if not packages:
        print_stderr(f"Error: no datrix-* packages with pyproject.toml found under {workspace}")
        return EXIT_FAILED
    logger.debug("Discovered packages: %s", ", ".join(sorted(packages)))
    if selected is not None:
        missing = selected - set(packages)
        if missing:
            print_stderr(f"Error: unknown package(s): {sorted(missing)}. Available: {sorted(packages)}")
            return EXIT_FAILED
    if args.mode == MODE_THIRD_PARTY:
        try:
            run_third_party(packages, selected)
        except (OSError, ValueError) as exc:
            print_stderr(f"Error: a pyproject.toml could not be read: {exc}")
            return EXIT_FAILED
        return EXIT_PASSED
    run_graph(packages, selected, args.mode)
    return EXIT_PASSED


def build_parser() -> argparse.ArgumentParser:
    """The options of ``metrics/dependency.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        description="Datrix package dependency graph from pyproject.toml.", allow_abbrev=False
    )
    add_project_arguments(parser)
    parser.add_argument(
        "--mode", choices=MODES, default=MODE_TREE, help="Output mode: tree, list, json, third-party (default: tree)."
    )
    parser.add_argument(
        "--verbose-output", dest="debug", action="store_true", help="Debug logging: names the packages discovered."
    )
    parser.add_argument(WRAPPER_DEBUG_FLAG, dest="debug", action="store_true", help="Debug logging.")
    parser.add_argument("--self-test", action="store_true", help="Run only the self-test over planted packages.")
    return parser


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        return run_self_test(
            SELF_TEST_CHECKS, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=METRICS_SCRIPTS_DIR
        )
    return run_dependency(args, WORKSPACE_DIR)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

_PLANTED_PYPROJECTS: Final = {
    "datrix-a": '[project]\nname = "datrix-a"\ndependencies = ["datrix-b>=1", "requests>=2"]\n',
    "datrix-b": '[project]\nname = "datrix-b"\ndependencies = ["requests>=2.1"]\n',
}


def _plant(root: Path) -> Path:
    """``datrix-a`` (depends on ``datrix-b`` and ``requests>=2``), ``datrix-b`` (``requests>=2.1``), a
    ``datrix-c`` with no pyproject.toml and the showcase directory."""
    for name, text in _PLANTED_PYPROJECTS.items():
        (root / name).mkdir()
        (root / name / PackageMarker.PYPROJECT.value).write_text(text, encoding="utf-8")
    (root / "datrix-c" / PackageMarker.SRC.value).mkdir(parents=True)
    (root / SHOWCASE).mkdir()
    return root


def _report(argv: Sequence[str]) -> tuple[int, list[str], list[str]]:
    """Exit code, stdout lines and stderr lines of a run over a planted workspace."""
    out, err = io.StringIO(), io.StringIO()
    with tempfile.TemporaryDirectory() as raw:
        workspace = _plant(Path(raw))
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = run_dependency(build_parser().parse_args(list(argv)), workspace)
    return code, out.getvalue().splitlines(), err.getvalue().splitlines()


def _check_tree_lists_each_package_with_its_datrix_dependencies() -> None:
    code, lines, _ = _report(["--all"])
    assert code == EXIT_PASSED, code
    assert lines == ["Dependency (mode=tree) for all Datrix packages", "datrix-a", "  datrix-b", "datrix-b"], lines


def _check_list_and_json_of_named_packages() -> None:
    code, lines, _ = _report(["datrix-a", "--mode=list"])
    assert (code, lines) == (EXIT_PASSED, ["Dependency (mode=list) for: datrix-a", "datrix-a -> datrix-b"]), lines
    code, lines, _ = _report(["--projects=datrix-b", "--mode=json"])
    assert code == EXIT_PASSED, code
    assert json.loads("\n".join(lines[1:])) == {"packages": ["datrix-b"], "edges": []}, lines


def _check_third_party_marks_spec_drift() -> None:
    code, lines, _ = _report(["--all", "--mode=third-party"])
    assert code == EXIT_PASSED, code
    assert lines[1:] == [
        "requests  SPEC DRIFT", "  datrix-a: requests>=2", "  datrix-b: requests>=2.1", "", "1 third-party runtime dependency."
    ], lines


def _check_unknown_package_is_named_on_stderr() -> None:
    code, _, errors = _report(["datrix-c"])
    assert code == EXIT_FAILED, code
    assert errors == ["Error: unknown package(s): ['datrix-c']. Available: ['datrix-a', 'datrix-b']"], errors


def _check_showcase_alone_is_refused() -> None:
    code, lines, _ = _report([SHOWCASE])
    assert (code, lines) == (EXIT_FAILED, [WORDING.none_valid]), (code, lines)


def _check_nothing_given_prints_usage_and_available_packages() -> None:
    code, lines, _ = _report([])
    assert code == EXIT_FAILED, code
    assert lines == ["", *USAGE_LINES, "", "Available packages:", " - datrix-a", " - datrix-b", ""], lines


SELF_TEST_CHECKS: Final[tuple[Callable[[], None], ...]] = (
    _check_tree_lists_each_package_with_its_datrix_dependencies,
    _check_list_and_json_of_named_packages,
    _check_third_party_marks_spec_drift,
    _check_unknown_package_is_named_on_stderr,
    _check_showcase_alone_is_refused,
    _check_nothing_given_prints_usage_and_available_packages,
)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
