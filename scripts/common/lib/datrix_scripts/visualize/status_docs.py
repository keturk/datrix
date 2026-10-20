"""Report documentation status for Datrix projects.

The module behind ``visualize/status-docs.ps1`` (and its ``.sh`` twin). Scans Datrix project
source directories and reports which documentation artifacts exist under ``<project>/docs/``:
diagrams, OpenAPI specs and AsyncAPI specs. One ``--source`` (a relative path is taken from the
workspace root), or a batch table: ``--all``, ``--domains`` or ``--test-set``.

Exit codes: 0 = reported (a missing single project is reported on stderr); 1 = the batch named no
project; 2 = neither a source nor a batch flag.

Usage:
    python -m datrix_scripts.visualize.status_docs --source=<system.dtrx>
"""

from __future__ import annotations

import argparse
import contextlib
import io
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from datrix_scripts.gate_harness import expect_usage_error, install_sigint_handler
from datrix_scripts.logging_utils import ColorCodes, colorize
from datrix_scripts.test.wrappers import VISUALIZE_SCRIPTS_DIR, module_main, run_self_test
from datrix_scripts.visualize.projects import (
    DOCS_DIR_NAME,
    Project,
    ProjectSelectionError,
    add_selection_arguments,
    batch_projects,
    require_selection,
    selected_test_set,
    workspace_path,
)

MODULE: Final = "datrix_scripts.visualize.status_docs"
WRAPPER: Final = "status-docs"
DOC_TYPES: Final = ("diagrams", "openapi", "asyncapi")
PROJECT_COLUMN_WIDTH: Final = 45
TYPE_COLUMN_WIDTH: Final = 12


def _doc_files(project_dir: Path, doc_type: str) -> list[Path]:
    type_dir = project_dir / DOCS_DIR_NAME / doc_type
    if not type_dir.is_dir():
        return []
    return [f for f in type_dir.iterdir() if not f.name.startswith(".")]


def _check_docs(project_dir: Path) -> dict[str, bool]:
    """Which documentation types have at least one entry under ``<project_dir>/docs/<type>``."""
    return {doc_type: bool(_doc_files(project_dir, doc_type)) for doc_type in DOC_TYPES}


def _scan_single_project(project_dir: Path) -> None:
    """Report docs status for a single Datrix project directory."""
    project_dir = project_dir.resolve()
    if not project_dir.is_dir():
        print(colorize(f"Project directory not found: {project_dir}", ColorCodes.RED), file=sys.stderr)
        return

    print(f"Project: {project_dir.name}")
    print(f"Path:    {project_dir}\n")

    status = _check_docs(project_dir)
    if not any(status.values()):
        print(colorize("  No documentation found.", ColorCodes.YELLOW))
        return
    for doc_type in DOC_TYPES:
        files = _doc_files(project_dir, doc_type)
        if not files:
            print(f"  {doc_type}: {colorize('none', ColorCodes.GRAY)}")
            continue
        print(f"  {doc_type}: {colorize(f'{len(files)} files', ColorCodes.GREEN)}")
        for f in sorted(files):
            print(f"    {f.name}")


def _print_table(projects: list[Project]) -> None:
    """Print a table of docs status for multiple projects."""
    header = f"{'Project':<{PROJECT_COLUMN_WIDTH}}"
    for doc_type in DOC_TYPES:
        header += f"  {doc_type:<{TYPE_COLUMN_WIDTH}}"
    print(header)
    print("-" * len(header))

    with_docs = 0
    for project in projects:
        status = _check_docs(project.directory)
        line = f"{project.name:<{PROJECT_COLUMN_WIDTH}}"
        for doc_type in DOC_TYPES:
            marker = colorize("YES", ColorCodes.GREEN) if status[doc_type] else colorize(" - ", ColorCodes.GRAY)
            line += f"  {marker:<{TYPE_COLUMN_WIDTH}}"
        print(line)
        with_docs += int(any(status.values()))

    print(f"\n{len(projects)} projects scanned, {with_docs} have documentation")


def report_source(source: str) -> int:
    """Docs status of the project *source* names (relative to the workspace root)."""
    _scan_single_project(Project(name="", source=workspace_path(source).resolve()).directory)
    return 0


def report_batch(args: argparse.Namespace) -> int:
    """The docs status table of the selected test set; returns the exit code."""
    test_set = selected_test_set(args)
    try:
        projects = batch_projects(test_set)
    except ProjectSelectionError as exc:
        print(colorize(f"ERROR: {exc}", ColorCodes.RED), file=sys.stderr)
        return 1
    print(f"Documentation status for {len(projects)} projects (test set: {test_set})\n")
    _print_table(projects)
    return 0


def build_parser() -> argparse.ArgumentParser:
    """The options of ``visualize/status-docs.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False
    )
    add_selection_arguments(parser)
    parser.add_argument("--self-test", action="store_true",
                        help="Run only the self-test: a planted project's docs are reported, and the refusals.")
    return parser


def _check_planted_docs_are_reported() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp) / "shop"
        diagrams = project / DOCS_DIR_NAME / "diagrams"
        diagrams.mkdir(parents=True)
        (diagrams / "erd.svg").write_text("<svg/>", encoding="utf-8")
        (diagrams / ".hidden").write_text("", encoding="utf-8")
        (project / "system.dtrx").write_text("", encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()) as printed:
            assert report_source(str(project / "system.dtrx")) == 0
            _print_table([Project(name="shop", source=project / "system.dtrx"), Project(name="bare", source=Path(tmp))])
    text = printed.getvalue()
    assert "diagrams: " in text and "1 files" in text and "    erd.svg" in text and ".hidden" not in text, text
    assert "openapi: " in text and "2 projects scanned, 1 have documentation" in text, text


def _check_no_selection_is_refused() -> None:
    expect_usage_error(lambda: require_selection(build_parser().parse_args([])), "-Source")


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        checks = [_check_planted_docs_are_reported, _check_no_selection_is_refused]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=build_parser(),
                             folder=VISUALIZE_SCRIPTS_DIR)
    require_selection(args)
    return report_source(args.source) if args.source else report_batch(args)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    install_sigint_handler()
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
