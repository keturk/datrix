"""List the Datrix project directories, or the full paths of their ``src/``, ``tests/`` or ``docs/`` folders.

``scripts/workspace/projects.ps1`` (and its ``.sh`` twin) runs this module. The projects are the workspace's
``datrix`` showcase repository and every ``datrix-*`` directory, discovered from disk
(``framework_repos.workspace_package_dirs``), never listed. With no option it prints each project's name, one
per line; ``--src``, ``--tests`` and ``--docs`` print the full path of that folder for each project that has
one (several options print their lists one after another, in that order).

Exit codes: 0 = listed; 1 = a self-test check failed; 2 = a usage error.

Usage (PYTHONPATH=scripts/common/lib; the wrapper sets it):
    python -m datrix_scripts.workspace.projects
    python -m datrix_scripts.workspace.projects --src
    python -m datrix_scripts.workspace.projects --self-test
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Final

from datrix_scripts.framework_repos import PackageMarker, workspace_package_dirs
from datrix_scripts.gate_harness import EXIT_PASS, write_files
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.test.wrappers import WORKSPACE_SCRIPTS_DIR, module_main, run_self_test

MODULE: Final = "datrix_scripts.workspace.projects"
WRAPPER: Final = "projects"
DOCS_DIR: Final = "docs"


def project_roots(workspace: Path) -> list[Path]:
    """The showcase repository and every ``datrix-*`` directory of *workspace*, sorted by name."""
    return workspace_package_dirs(workspace, include_showcase=True)


def requested_folders(args: argparse.Namespace) -> list[str]:
    """The project subfolders the options ask for, in ``src``, ``tests``, ``docs`` order."""
    wanted = ((args.src, PackageMarker.SRC.value), (args.tests, PackageMarker.TESTS.value), (args.docs, DOCS_DIR))
    return [folder for asked, folder in wanted if asked]


def listing(workspace: Path, folders: Sequence[str]) -> list[str]:
    """The lines to print: project names when *folders* is empty, else each project's existing folder paths."""
    projects = project_roots(workspace)
    if not folders:
        return [project.name for project in projects]
    return [
        str((project / folder).resolve())
        for folder in folders
        for project in projects
        if (project / folder).is_dir()
    ]


def run(args: argparse.Namespace) -> int:
    """Print the listing the options ask for; returns the exit code."""
    for line in listing(WORKSPACE_DIR, requested_folders(args)):
        print(line)
    return EXIT_PASS


def build_parser() -> argparse.ArgumentParser:
    """The options of ``projects.ps1``: its parameters as ``--kebab-name`` flags."""
    parser = argparse.ArgumentParser(
        prog=WRAPPER,
        description="List the Datrix project directories, or the full paths of their src/tests/docs folders.",
        allow_abbrev=False,
    )
    parser.add_argument("--src", action="store_true", help="print each project's src folder (where it exists)")
    parser.add_argument("--tests", action="store_true", help="print each project's tests folder (where it exists)")
    parser.add_argument("--docs", action="store_true", help="print each project's docs folder (where it exists)")
    parser.add_argument("--self-test", action="store_true", help="run the self-test and exit")
    parser.set_defaults(debug=False)
    return parser


# ---------------------------------------------------------------------------
# Self-test: a planted workspace in a temporary directory.
# ---------------------------------------------------------------------------

_PLANTED: Final = {
    "datrix/docs/index.md": "x\n",
    "datrix-b/src/b/__init__.py": "\n",
    "datrix-b/tests/test_b.py": "\n",
    "datrix-a/src/a/__init__.py": "\n",
    "datrix-a/docs/a.md": "x\n",
    "other/src/o.py": "\n",
    "datrixish/src/x.py": "\n",
}


def _check_names_are_the_projects_in_name_order() -> None:
    with TemporaryDirectory() as raw:
        root = Path(raw)
        write_files(root, _PLANTED)
        names = listing(root, [])
    assert names == ["datrix", "datrix-a", "datrix-b"], names


def _check_folders_list_existing_ones_in_option_order() -> None:
    with TemporaryDirectory() as raw:
        root = Path(raw)
        write_files(root, _PLANTED)
        args = build_parser().parse_args(["--docs", "--src"])
        lines = [Path(line).relative_to(root.resolve()).as_posix() for line in listing(root, requested_folders(args))]
    assert lines == ["datrix-a/src", "datrix-b/src", "datrix/docs", "datrix-a/docs"], lines


_SELF_TEST_CHECKS: Final = (
    _check_names_are_the_projects_in_name_order,
    _check_folders_list_existing_ones_in_option_order,
)


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        return run_self_test(
            _SELF_TEST_CHECKS, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=WORKSPACE_SCRIPTS_DIR
        )
    return run(args)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the self-test, or print the listing."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
