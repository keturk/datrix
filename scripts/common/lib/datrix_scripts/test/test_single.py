"""Run one test file, class, method or ``-k`` selection quickly, behind ``test/test-single.ps1``.

Runs pytest, in the shared venv, in the project that owns the test, with minimal overhead (quiet
output, no xdist): the fix-one-verify-one loop of checkpoint debugging. The project is
``--project`` or the ``datrix-*`` folder the test path names. Exit codes: pytest's own (0 passed),
2 for a usage error, 1 when the venv check fails.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Final

from datrix_scripts.entrypoint import wrapper_flag
from datrix_scripts.gate_harness import EXIT_USAGE, EXIT_VIOLATION, configure_logging, write_files
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.test.wrappers import ensure_utf8_stdio

logger = logging.getLogger(__name__)

MODULE: Final = "datrix_scripts.test.test_single"
WRAPPER: Final = "test-single"
PROJECT_PREFIX: Final = "datrix-"
NODE_ID_SEPARATOR: Final = "::"
_PROJECT_IN_PATH_RE: Final = re.compile(r"(datrix-[^/\\]+)")
_RULE: Final = "─" * 60
_WINDOWS: Final = os.name == "nt"


class UsageProblem(Exception):
    """The arguments name no project this run can resolve (exit code 2)."""


def resolve_project(test_path: str, project_name: str, workspace_root: Path) -> Path:
    """The project root: ``--project`` when given, else the ``datrix-*`` folder *test_path* lies in or names.

    Raises:
        UsageProblem: The named project does not exist, or no project can be read from *test_path*.
    """
    if project_name:
        project_root = workspace_root / project_name
        if not project_root.is_dir():
            raise UsageProblem(f"ERROR: Project not found: {project_root}")
        return project_root
    if test_path:
        test_path_obj = Path(test_path)
        if test_path_obj.is_absolute() and test_path_obj.exists():
            current = test_path_obj if test_path_obj.is_dir() else test_path_obj.parent
            while current != current.parent:
                if current.name.startswith(PROJECT_PREFIX):
                    return current
                current = current.parent
        match = _PROJECT_IN_PATH_RE.search(test_path)
        if match and (workspace_root / match.group(1)).is_dir():
            return workspace_root / match.group(1)
    raise UsageProblem(f"ERROR: Cannot determine project. Use {wrapper_flag('Project')} to specify explicitly.")


def _relative_to(path: Path, root: Path) -> str | None:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return None


def resolve_test_path(test_path: str, project_root: Path) -> str:
    """*test_path* as pytest takes it from *project_root*: an absolute path made relative, a node ID's
    file part likewise, a relative path with its separators normalised when only that form exists;
    anything else unchanged, for pytest to report."""
    if not test_path:
        return ""
    if NODE_ID_SEPARATOR in test_path:
        file_part, rest = test_path.split(NODE_ID_SEPARATOR, 1)
        if Path(file_part).is_absolute():
            relative = _relative_to(Path(file_part), project_root)
            return f"{relative}{NODE_ID_SEPARATOR}{rest}" if relative is not None else test_path
        return test_path
    path_obj = Path(test_path)
    if path_obj.is_absolute():
        relative = _relative_to(path_obj, project_root) if path_obj.exists() else None
        return relative if relative is not None else test_path
    if (project_root / test_path).exists():
        return test_path
    normalized = test_path.replace("\\", "/")
    if (project_root / normalized).exists():
        return normalized
    return test_path


def pytest_arguments(args: argparse.Namespace, resolved_path: str) -> list[str]:
    """The pytest arguments (after ``python -m pytest``) for *args* and the resolved test path."""
    arguments = [resolved_path] if resolved_path else []
    if args.keyword:
        arguments.extend(["-k", args.keyword])
    if args.marker:
        arguments.extend(["-m", args.marker])
    arguments.extend(["-v"] if args.verbose_output else ["-q", "--tb=short"])
    if args.fail_fast:
        arguments.append("-x")
    # A single-test run gains nothing from xdist workers but their start-up time.
    arguments.extend(["-p", "no:xdist"])
    return arguments


def usage_text(*, windows: bool = _WINDOWS) -> str:
    """The usage printed when neither a test path nor a keyword is given."""
    script = ".\\test-single.ps1" if windows else "./test-single.sh"
    project, keyword = (wrapper_flag(name, windows=windows) for name in ("Project", "Keyword"))
    lines = [
        "Usage:",
        f"  {script} <test-path> [{project} <name>]",
        f"  {script} {project} <name> {keyword} <expr>",
        "",
        "Examples:",
        f"  {script} tests/test_foo.py {project} datrix-common",
        f"  {script} {project} datrix-codegen-python {keyword} test_enum",
        "",
        f"Use Get-Help {script} -Full for detailed help." if windows else f"Use {script} --help for detailed help.",
    ]
    return "\n".join(lines)


def run(args: argparse.Namespace) -> int:
    """Resolve the project and test path, run pytest there, print the verdict; pytest's exit code."""
    from datrix_scripts.venv import require_packages

    test_path = args.test_path or args.positional_test_path
    if not test_path and not args.keyword:
        print(usage_text())
        return EXIT_USAGE
    try:
        project_root = resolve_project(test_path, args.project, WORKSPACE_DIR)
    except UsageProblem as exc:
        print(exc, file=sys.stderr)
        return EXIT_USAGE
    logger.debug("Project: %s at %s", project_root.name, project_root)
    resolved = resolve_test_path(test_path, project_root)
    logger.debug("Resolved test path: %s", resolved)
    if not require_packages():
        return EXIT_VIOLATION
    arguments = pytest_arguments(args, resolved)
    print()
    print(f"Running: pytest {' '.join(arguments)}")
    print(f"Project: {project_root.name}")
    print(_RULE)
    print(flush=True)
    returncode = subprocess.run([sys.executable, "-m", "pytest", *arguments], cwd=project_root, check=False).returncode
    print()
    print("PASSED" if returncode == 0 else f"FAILED (exit code: {returncode})")
    return returncode


def build_parser() -> argparse.ArgumentParser:
    """The options ``test/test-single.ps1`` passes (each wrapper parameter as ``--kebab-name``)."""
    parser = argparse.ArgumentParser(
        prog="test-single",
        description="Run a single test file, class, method or -k selection quickly, in the project that owns it.",
        allow_abbrev=False,
    )
    parser.add_argument("positional_test_path", nargs="?", default="", metavar="TEST_PATH",
                        help="as --test-path, for a caller of the .sh twin")
    parser.add_argument("--test-path", default="",
                        help="test file or pytest node ID (file::class::method): absolute, or relative to the project")
    parser.add_argument("--project", default="", help="project for relative paths, e.g. datrix-common (default: from the path)")
    parser.add_argument("--keyword", "-k", default="", help="pytest -k filter expression")
    parser.add_argument("--marker", "-m", default="", help="pytest -m marker filter")
    parser.add_argument("--verbose-output", action="store_true", help="full pytest output (default: quiet, failures only)")
    parser.add_argument("--fail-fast", action="store_true", help="stop on the first failure (pytest -x)")
    parser.add_argument("--dbg", action="store_true", help="log debug detail to stderr")
    parser.add_argument("--self-test", action="store_true", help="run this module's self-test")
    return parser


def _check_project_resolution() -> None:
    with TemporaryDirectory() as temp:
        workspace = Path(temp)
        write_files(workspace, {"datrix-shop/tests/unit/test_cart.py": "", "notes/readme.txt": ""})
        project = workspace / "datrix-shop"
        test_file = project / "tests" / "unit" / "test_cart.py"
        assert resolve_project(str(test_file), "", workspace) == project, "an absolute path did not walk up"
        assert resolve_project("datrix-shop/tests/unit/test_cart.py", "", workspace) == project
        assert resolve_project("", "datrix-shop", workspace) == project
        for test_path, project_name in (("tests/unit/test_cart.py", ""), ("", "datrix-missing")):
            try:
                resolve_project(test_path, project_name, workspace)
            except UsageProblem:
                continue
            raise AssertionError(f"({test_path!r}, {project_name!r}) resolved to a project")


def _check_test_path_resolution() -> None:
    with TemporaryDirectory() as temp:
        project = Path(temp) / "datrix-shop"
        write_files(project, {"tests/unit/test_cart.py": ""})
        absolute = project / "tests" / "unit" / "test_cart.py"
        relative = str(Path("tests", "unit", "test_cart.py"))
        cases = (
            (str(absolute), relative),
            (f"{absolute}::TestCart::test_add", f"{relative}::TestCart::test_add"),
            ("tests/unit/test_cart.py::TestCart", "tests/unit/test_cart.py::TestCart"),
            ("tests/unit/test_gone.py", "tests/unit/test_gone.py"),
            ("", ""),
        )
        for raw, expected in cases:
            resolved = resolve_test_path(raw, project)
            assert resolved == expected, f"{raw!r} resolved to {resolved!r}, expected {expected!r}"


def _check_pytest_arguments() -> None:
    parser = build_parser()
    quiet = pytest_arguments(parser.parse_args(["--test-path=t.py"]), "t.py")
    assert quiet == ["t.py", "-q", "--tb=short", "-p", "no:xdist"], f"quiet run: {quiet}"
    loud = pytest_arguments(parser.parse_args(["-k", "enum", "--marker=not slow", "--verbose-output", "--fail-fast"]), "")
    assert loud == ["-k", "enum", "-m", "not slow", "-v", "-x", "-p", "no:xdist"], f"verbose run: {loud}"


def _check_usage_text() -> None:
    windows = usage_text(windows=True).splitlines()
    assert windows[1] == "  .\\test-single.ps1 <test-path> [-Project <name>]", f"Windows usage: {windows[1]!r}"
    posix = usage_text(windows=False)
    assert "--project" in posix and "-Project" not in posix, f"POSIX usage names PowerShell flags: {posix!r}"


def run_self_test(parser: argparse.ArgumentParser) -> int:
    """Run this module's checks and its wrapper seam check; the exit code."""
    from datrix_scripts.test.wrappers import run_self_test as run_wrapper_self_test

    checks = [_check_project_resolution, _check_test_path_resolution, _check_pytest_arguments, _check_usage_text]
    return run_wrapper_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=parser)


def main(argv: Sequence[str] | None = None) -> int:
    ensure_utf8_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.dbg)
    if args.self_test:
        return run_self_test(parser)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
