#!/usr/bin/env python3
"""Run mypy for one or more Datrix projects (the behaviour of ``test/mypy.ps1``).

A human-only tool: no skill, hook, orchestrator or other script runs a type-check through it (its one caller is
the affected gate's opt-in ``-Mypy`` switch), and ``guard-forbidden-commands.py`` refuses every agent tool call
that would, leaving only ``--self-test``, which launches nothing. The package test suites are the declared gate
for type correctness; this exists so a person can type-check on demand.

Selects the projects (``--all``: every ``datrix-*`` package with a ``pyproject.toml``; or the names or folder
paths given, where the ``datrix`` showcase repo may be named explicitly but is never swept by ``--all``), checks
the shared venv's installs once, type-checks each project whose ``pyproject.toml`` carries ``[tool.mypy]``, and
prints a summary. mypy's incremental cache goes under ``<workspace>/.tmp/mypy-cache``, never into a package
repository. Exit 0 every project passed or was skipped, 1 a project failed (or a selection, install-check or
self-test failure), 2 usage error.

Usage (PYTHONPATH=scripts/common/lib):
  python -m datrix_scripts.test.mypy_check datrix-common [--specific src/datrix_common/builtins]
  python -m datrix_scripts.test.mypy_check --all
  python -m datrix_scripts.test.mypy_check --self-test
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from datrix_scripts.framework_repos import SHOWCASE_REPO_NAME, PackageMarker, workspace_package_dirs
from datrix_scripts.gate_harness import (
    EXIT_PASS,
    EXIT_VIOLATION,
    WRAPPER_DEBUG_FLAG,
    UsageError,
    expect_usage_error,
    run_main,
)
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.test.test import ensure_packages, normalize_project
from datrix_scripts.test.wrappers import ensure_utf8_stdio, run_self_test
from datrix_scripts.venv import get_venv_python, require_packages

MODULE = "datrix_scripts.test.mypy_check"
WRAPPER = "mypy"

_PYPROJECT = PackageMarker.PYPROJECT
_TOOL_TABLE = "tool"
_MYPY_TABLE = "mypy"
_DEFAULT_TARGET = "src"
_CACHE_SUBDIRS = (".tmp", "mypy-cache")
_RESULTS_DIR_NAME = ".test_results"
_SHARED_LIBRARY_SUBDIRS = ("scripts", "common", "lib")
_SHOWCASE_MYPY_ARGS = ("--follow-imports=silent",)
_MYPYPATH_ENV = "MYPYPATH"
_VERBOSE_MYPY_ARG = "--show-error-context"
_RULE = "=" * 40
_SELF_TEST_PREFIX = "mypy-check-selftest-"

#: Wrapper options kept for command-line symmetry with test.ps1; mypy has no use for them. ``e2_e`` is -E2E,
#: passed as --e2-e by the wrapper's kebab rule (as test.ps1's module takes it).
_IGNORED_SWITCHES = ("coverage", "no_auto_install", "unit", "integration", "e2_e", "fast", "slow")
_IGNORED_OPTIONS = (*_IGNORED_SWITCHES, "keyword")
_IGNORED_HELP = "Accepted for parity with test.ps1; mypy does not use it"

_USAGE_LINES = (
    "Usage:",
    " .\\mypy.ps1 <project-name> [options]",
    " .\\mypy.ps1 <folder-path> [options]",
    " .\\mypy.ps1 -All [options]",
    "",
    "Examples:",
    " .\\mypy.ps1 datrix-common",
    " .\\mypy.ps1 .\\datrix-common\\",
    " .\\mypy.ps1 datrix-common datrix-language",
    ' .\\mypy.ps1 datrix-common -Specific "src\\datrix_common\\builtins"',
    " .\\mypy.ps1 -All",
)


class SelectionError(Exception):
    """The projects asked for cannot be type-checked (exit 1); ``lines`` say why and what is available."""

    def __init__(self, lines: Sequence[str]) -> None:
        super().__init__("\n".join(lines))
        self.lines = tuple(lines)


class PyprojectError(Exception):
    """A project's pyproject.toml cannot be read, so whether it configures mypy is unknown."""


@dataclass(frozen=True)
class MypyCommand:
    """One project's mypy launch: the argument vector, where it runs, its cache and environment overrides."""

    argv: tuple[str, ...]
    cwd: Path
    cache_dir: Path
    env_overrides: Mapping[str, str]


# ---------------------------------------------------------------------------
# Project selection
# ---------------------------------------------------------------------------


def sweep_projects(workspace: Path) -> list[str]:
    """What ``--all`` type-checks: every ``datrix-*`` package with a pyproject.toml (never the showcase repo)."""
    return [path.name for path in workspace_package_dirs(workspace, any_of=frozenset({_PYPROJECT}))]


def nameable_projects(workspace: Path) -> list[str]:
    """What may be named: the sweep, plus the showcase repo when it carries a pyproject.toml (its scripts are a
    legitimate targeted check, e.g. ``mypy.ps1 datrix -Specific <file>``)."""
    dirs = workspace_package_dirs(workspace, any_of=frozenset({_PYPROJECT}), include_showcase=True)
    return [path.name for path in dirs]


def _available_lines(workspace: Path) -> list[str]:
    available = nameable_projects(workspace)
    return ["", "Available projects:", *(f" - {name}" for name in available), "", f"Total: {len(available)} projects"]


def requested_projects(args: argparse.Namespace) -> list[str]:
    """The project arguments given positionally and as --projects, as package names, in order."""
    return [normalize_project(raw) for raw in [*args.positional_projects, *args.projects]]


def select_projects(args: argparse.Namespace, workspace: Path) -> list[str]:
    """The projects to type-check; SelectionError when none can be, or when a named one is not a project."""
    requested = requested_projects(args)
    if args.all and requested:
        raise UsageError(
            f"Give -All or project names, not both (got -All and {', '.join(requested)}). "
            "Drop -All to check the named projects, or drop the names to check every package."
        )
    if args.all:
        projects = sweep_projects(workspace)
        if not projects:
            raise SelectionError([f"ERROR: No Datrix projects with pyproject.toml found in: {workspace}"])
        return projects
    if not requested:
        raise SelectionError(["", "ERROR: No projects specified.", "", *_USAGE_LINES, *_available_lines(workspace)])
    unknown = [name for name in requested if name not in nameable_projects(workspace)]
    if unknown:
        raise SelectionError(
            [f"ERROR: Not a Datrix project with a pyproject.toml: {', '.join(unknown)}.", *_available_lines(workspace)]
        )
    return requested


# ---------------------------------------------------------------------------
# One project's check
# ---------------------------------------------------------------------------


def has_mypy_config(project_root: Path) -> bool:
    """Whether *project_root*'s pyproject.toml carries a ``[tool.mypy]`` table (False when it has no pyproject)."""
    pyproject_path = project_root / _PYPROJECT.value
    if not pyproject_path.is_file():
        return False
    try:
        with pyproject_path.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise PyprojectError(
            f"{pyproject_path} cannot be read as TOML ({exc}). Expected a valid pyproject.toml; fix it and re-run."
        ) from exc
    tool = data.get(_TOOL_TABLE)
    mypy = tool.get(_MYPY_TABLE) if isinstance(tool, dict) else None
    return isinstance(mypy, dict)


def resolve_specific_targets(project_root: Path, specific: str | None) -> list[str]:
    """mypy's targets: ``src`` by default, else each comma-separated entry of *specific*, relative to the project."""
    if not specific:
        return [_DEFAULT_TARGET]
    targets: list[str] = []
    for raw_target in specific.split(","):
        target = raw_target.strip()
        if not target:
            continue
        target_path = Path(target)
        if not target_path.is_absolute():
            target_path = project_root / target_path
        targets.append(str(target_path))
    return targets


def resolve_cache_dir(project_root: Path, workspace: Path) -> Path:
    """mypy's incremental cache, kept OUTSIDE every package repository.

    mypy writes ``.mypy_cache/`` into its working directory, and the working directory here is the package root.
    Left at that default, one sweep of the installable packages drops a cache tree inside each of 15 separate git
    repositories -- roughly 51,400 files and a gigabyte, which the repo-level ignored-source gate fails on. The
    cache is pure derived state, so it belongs in the workspace temp tree with everything else that is regenerable.
    """
    return workspace.joinpath(*_CACHE_SUBDIRS, project_root.name)


def mypy_command(
    python_exe: str, project_root: Path, targets: Sequence[str], *, verbose: bool, workspace: Path
) -> MypyCommand:
    """The mypy launch for *project_root* (pure: it creates nothing and runs nothing).

    The showcase repo has no ``src/`` layout: its scripts import the shared scripts package through PYTHONPATH,
    which mypy cannot see unless told, so ``MYPYPATH`` names ``scripts/common/lib`` and ``--follow-imports=silent``
    keeps issues inside that package (which gets no strict run of its own) from blocking the target's own check.
    """
    shared_root = project_root.joinpath(*_SHARED_LIBRARY_SUBDIRS)
    showcase = project_root.name == SHOWCASE_REPO_NAME and shared_root.is_dir()
    extra_args = _SHOWCASE_MYPY_ARGS if showcase else ()
    env_overrides = {_MYPYPATH_ENV: str(shared_root)} if showcase else {}
    cache_dir = resolve_cache_dir(project_root, workspace)
    argv = [python_exe, "-m", "mypy", "--cache-dir", str(cache_dir), *extra_args, *targets]
    if verbose:
        argv.append(_VERBOSE_MYPY_ARG)
    return MypyCommand(argv=tuple(argv), cwd=project_root, cache_dir=cache_dir, env_overrides=env_overrides)


def write_log(project_root: Path, output: str) -> Path:
    """Save *output* to ``<project>/.test_results/mypy-results-<timestamp>.log``; the path."""
    results_dir = project_root / _RESULTS_DIR_NAME
    results_dir.mkdir(exist_ok=True)
    log_path = results_dir / f"mypy-results-{datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
    log_path.write_text(output, encoding="utf-8")
    return log_path


def run_mypy(command: MypyCommand, *, save_log: bool) -> int:
    """Launch *command*, streaming its output; mypy's exit code."""
    command.cache_dir.mkdir(parents=True, exist_ok=True)
    print(f"Running: {' '.join(command.argv)}")
    print(f"Working directory: {command.cwd}")
    print(f"Cache directory: {command.cache_dir}")
    print("")
    process = subprocess.Popen(
        command.argv,
        cwd=command.cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env={**os.environ, **command.env_overrides},
    )
    if process.stdout is None:
        raise RuntimeError("mypy was launched with a piped stdout but no pipe was opened")
    output_lines: list[str] = []
    for line in process.stdout:
        print(line, end="")
        output_lines.append(line)
    exit_code = process.wait()
    if save_log:
        print("")
        print(f"Log file: {write_log(command.cwd, ''.join(output_lines))}")
    return exit_code


def check_project(project: str, args: argparse.Namespace, python_exe: str, workspace: Path) -> int:
    """Type-check one selected project; 0 passed or skipped (no ``[tool.mypy]``), else mypy's exit code or 1."""
    project_root = workspace / project
    print(f"Found project '{project}' at: {project_root}")
    try:
        configured = has_mypy_config(project_root)
    except PyprojectError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_VIOLATION
    if not configured:
        print(f"SKIP: {project} has no [tool.mypy] config in pyproject.toml.")
        return EXIT_PASS
    print(f"Using Python: {python_exe}")
    targets = resolve_specific_targets(project_root, args.specific)
    command = mypy_command(python_exe, project_root, targets, verbose=args.verbose_output or args.debug,
                           workspace=workspace)
    return run_mypy(command, save_log=not args.no_save)


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------


def _print_ignored_options(args: argparse.Namespace) -> None:
    ignored = [name.replace("_", "-") for name in _IGNORED_OPTIONS if getattr(args, name)]
    if ignored:
        print(f"Note: mypy does not use these test runner options: {', '.join(ignored)}")
        print("")


def _venv_python() -> str:
    python = get_venv_python()
    if not python.is_file():
        raise UsageError(
            f"The shared venv's interpreter {python} does not exist. Expected the venv the wrapper ensures; "
            "run test/mypy.ps1 (or mypy.sh), which creates it, instead of the module directly."
        )
    return str(python)


def _print_summary(results: Mapping[str, int]) -> int:
    print("")
    print(_RULE)
    print("Mypy Summary")
    print(_RULE)
    for project in sorted(results):
        print(f" {'[PASS]' if results[project] == EXIT_PASS else '[FAIL]'} : {project}")
    failed = sum(1 for code in results.values() if code != EXIT_PASS)
    print("")
    print(f"Total: {len(results)} | Passed: {len(results) - failed} | Failed: {failed}")
    return EXIT_VIOLATION if failed else EXIT_PASS


def type_check(args: argparse.Namespace, workspace: Path) -> int:
    """Select the projects, check the venv's installs once, type-check each, print the summary; the exit code."""
    try:
        projects = select_projects(args, workspace)
    except SelectionError as exc:
        print("\n".join(exc.lines), file=sys.stderr)
        return EXIT_VIOLATION
    print(f"Running mypy for {'all ' if args.all else ''}projects: {', '.join(projects)}")
    _print_ignored_options(args)
    if not ensure_packages(os.environ, require_packages):
        return EXIT_VIOLATION
    python_exe = _venv_python()
    results: dict[str, int] = {}
    for number, project in enumerate(projects, start=1):
        print("")
        print(_RULE)
        print(f"[{number}/{len(projects)}] Mypy: {project}")
        print(_RULE)
        print("")
        results[project] = check_project(project, args, python_exe, workspace)
        print("")
        if results[project] == EXIT_PASS:
            print(f"[PASS] Mypy passed for {project}")
        else:
            print(f"[FAIL] Mypy failed for {project} (exit code: {results[project]})")
    return _print_summary(results)


# ---------------------------------------------------------------------------
# Self-test: pure functions over a planted workspace; nothing is installed, launched or cached
# ---------------------------------------------------------------------------


def _plant_workspace(root: Path) -> Path:
    """datrix-a and datrix-c (pyproject), datrix-b (none), and a showcase repo with a pyproject and shared lib."""
    for name in ("datrix-a", "datrix-c", SHOWCASE_REPO_NAME):
        (root / name).mkdir()
        (root / name / _PYPROJECT.value).write_text("[project]\nname = \"planted\"\n", encoding="utf-8")
    (root / "datrix-b").mkdir()
    root.joinpath(SHOWCASE_REPO_NAME, *_SHARED_LIBRARY_SUBDIRS).mkdir(parents=True)
    return root


def _check_command_keeps_the_cache_outside_the_package() -> None:
    with tempfile.TemporaryDirectory(prefix=_SELF_TEST_PREFIX) as tmp:
        workspace = _plant_workspace(Path(tmp))
        project_root = workspace / "datrix-a"
        command = mypy_command("py", project_root, ["src"], verbose=False, workspace=workspace)
        cache = workspace / ".tmp" / "mypy-cache" / "datrix-a"
        assert command.argv == ("py", "-m", "mypy", "--cache-dir", str(cache), "src"), command.argv
        assert command.cwd == project_root and not command.env_overrides, command
        assert project_root not in command.cache_dir.parents, f"cache {command.cache_dir} is inside the package"
        assert not command.cache_dir.exists(), "building the command must create nothing"
        verbose = mypy_command("py", project_root, ["src"], verbose=True, workspace=workspace)
        assert verbose.argv[-1] == _VERBOSE_MYPY_ARG, verbose.argv


def _check_showcase_resolves_the_shared_library() -> None:
    with tempfile.TemporaryDirectory(prefix=_SELF_TEST_PREFIX) as tmp:
        workspace = _plant_workspace(Path(tmp))
        showcase = workspace / SHOWCASE_REPO_NAME
        command = mypy_command("py", showcase, ["scripts/x.py"], verbose=False, workspace=workspace)
        shared = str(showcase.joinpath(*_SHARED_LIBRARY_SUBDIRS))
        assert command.env_overrides == {_MYPYPATH_ENV: shared}, command.env_overrides
        assert "--follow-imports=silent" in command.argv, command.argv


def _check_specific_targets_resolve_against_the_project() -> None:
    root = Path("planted-root").resolve()
    absolute = str(Path(root.anchor) / "abs" / "file.py")
    assert resolve_specific_targets(root, None) == [_DEFAULT_TARGET]
    resolved = resolve_specific_targets(root, f"a, ,b,{absolute}")
    assert resolved == [str(root / "a"), str(root / "b"), absolute], resolved


def _check_mypy_config_is_read_from_pyproject() -> None:
    with tempfile.TemporaryDirectory(prefix=_SELF_TEST_PREFIX) as tmp:
        root = Path(tmp)
        assert not has_mypy_config(root), "a project with no pyproject.toml configures no mypy"
        pyproject = root / _PYPROJECT.value
        pyproject.write_text("[tool.ruff]\nline-length = 120\n", encoding="utf-8")
        assert not has_mypy_config(root), "[tool.ruff] alone is not a mypy config"
        pyproject.write_text("[tool.mypy]\nstrict = true\n", encoding="utf-8")
        assert has_mypy_config(root), "[tool.mypy] is a mypy config"
        pyproject.write_text("[tool.mypy\n", encoding="utf-8")
        try:
            has_mypy_config(root)
        except PyprojectError as exc:
            assert "cannot be read as TOML" in str(exc), exc
        else:
            raise AssertionError("a malformed pyproject.toml was read as 'no mypy config'; it must fail loud")


def _expect_selection_error(args: argparse.Namespace, workspace: Path, fragment: str) -> None:
    try:
        select_projects(args, workspace)
    except SelectionError as exc:
        assert fragment in str(exc), f"selection error must mention {fragment!r}; got: {exc}"
    else:
        raise AssertionError(f"expected a selection error mentioning {fragment!r}")


def _check_projects_are_selected_from_the_workspace() -> None:
    parser = build_parser()
    with tempfile.TemporaryDirectory(prefix=_SELF_TEST_PREFIX) as tmp:
        workspace = _plant_workspace(Path(tmp))
        assert select_projects(parser.parse_args(["--all"]), workspace) == ["datrix-a", "datrix-c"]
        named = parser.parse_args(["datrix-c", "--projects=datrix"])
        assert select_projects(named, workspace) == ["datrix-c", SHOWCASE_REPO_NAME]
        _expect_selection_error(parser.parse_args(["datrix-a", "datrix-b"]), workspace, "datrix-b")
        _expect_selection_error(parser.parse_args([]), workspace, "No projects specified")
        expect_usage_error(lambda: select_projects(parser.parse_args(["--all", "datrix-a"]), workspace), "not both")
    with tempfile.TemporaryDirectory(prefix=_SELF_TEST_PREFIX) as tmp:
        _expect_selection_error(parser.parse_args(["--all"]), Path(tmp), "No Datrix projects")


_SELF_TEST_CHECKS = (
    _check_command_keeps_the_cache_outside_the_package,
    _check_showcase_resolves_the_shared_library,
    _check_specific_targets_resolve_against_the_project,
    _check_mypy_config_is_read_from_pyproject,
    _check_projects_are_selected_from_the_workspace,
)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """The options of ``test/mypy.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(description="Run mypy for Datrix projects.", allow_abbrev=False)
    parser.add_argument("positional_projects", nargs="*", metavar="PROJECT",
                        help="as --projects, for a caller of the .sh twin")
    parser.add_argument("--projects", action="append", default=[],
                        help="A project name or folder path to type-check; repeatable")
    parser.add_argument("--all", action="store_true",
                        help="Type-check every datrix-* package with a pyproject.toml")
    for ignored in _IGNORED_SWITCHES:
        parser.add_argument(f"--{ignored.replace('_', '-')}", action="store_true", help=_IGNORED_HELP)
    parser.add_argument("--keyword", help=_IGNORED_HELP)
    parser.add_argument("--verbose-output", action="store_true", help="Show verbose mypy context")
    parser.add_argument("--no-save", action="store_true", help="Don't save mypy output to log files")
    parser.add_argument("--specific", help="Type-check a specific file, directory, or comma-separated targets")
    parser.add_argument(WRAPPER_DEBUG_FLAG, dest="debug", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run only the self-test over a planted workspace: it installs, launches and caches nothing.",
    )
    return parser


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        return run_self_test(_SELF_TEST_CHECKS, wrapper=WRAPPER, module=MODULE, parser=build_parser())
    return type_check(args, WORKSPACE_DIR)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    ensure_utf8_stdio()
    parser = build_parser()
    return run_main(lambda: parser.parse_intermixed_args(argv), _run)


if __name__ == "__main__":
    sys.exit(main())
