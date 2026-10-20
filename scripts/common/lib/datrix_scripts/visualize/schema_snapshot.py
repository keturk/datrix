"""Save a .dtrx Application as a JSON snapshot for future diffs.

The module behind ``visualize/schema-snapshot.ps1`` (and its ``.sh`` twin). Loads the application
the way generation does (``visualization.application_loader``, profile ``test``) and writes the
full structural model (services, entities, endpoints, events) as JSON: to ``--output``, or to
``<project>/docs/snapshots/<name>.json``. One ``--source`` (a relative path is taken from the
workspace root), or a batch: ``--all``, ``--domains`` or ``--test-set``.

Exit codes: 0 = every snapshot was written; 1 = a project failed, or the batch named no project;
2 = neither a source nor a batch flag.

Usage:
    python -m datrix_scripts.visualize.schema_snapshot --source=<system.dtrx> [--output=<file.json>]
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from datrix_scripts.gate_harness import expect_usage_error, install_sigint_handler
from datrix_scripts.logging_utils import ColorCodes, colorize
from datrix_scripts.test.wrappers import VISUALIZE_SCRIPTS_DIR, module_main, run_self_test
from datrix_scripts.visualization.application_loader import load_application
from datrix_scripts.visualization.serializer import serialize_application
from datrix_scripts.visualize.projects import (
    DOCS_DIR_NAME,
    Project,
    ProjectSelectionError,
    add_selection_arguments,
    batch_projects,
    plant_example,
    require_selection,
    selected_test_set,
    workspace_path,
)

MODULE: Final = "datrix_scripts.visualize.schema_snapshot"
WRAPPER: Final = "schema-snapshot"
SNAPSHOT_PROFILE: Final = "test"
SNAPSHOTS_DIR_NAME: Final = "snapshots"


def _parse_and_snapshot(source_path: Path, output_path: Path) -> tuple[bool, str]:
    """Load *source_path* and write its JSON snapshot to *output_path*.

    Returns (success, error_message).
    """
    try:
        app = load_application(source_path, SNAPSHOT_PROFILE)
    except Exception as e:
        return False, f"Load error: {e}"

    try:
        data = serialize_application(app)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        return False, f"Serialization error: {e}"

    return True, ""


def _default_output(project: Project, name: str) -> Path:
    return project.directory / DOCS_DIR_NAME / SNAPSHOTS_DIR_NAME / f"{name}.json"


def snapshot_source(source: str, output: str | None) -> int:
    """Snapshot ``--source`` (relative to the workspace root); returns the exit code."""
    project = Project(name="", source=workspace_path(source))
    output_path = workspace_path(output) if output else _default_output(project, project.source.stem)
    print(f"Source: {project.source}")
    print(f"Output: {output_path}")
    ok, err = _parse_and_snapshot(project.source, output_path)
    if ok:
        print(colorize("Snapshot saved.", ColorCodes.GREEN))
    else:
        print(colorize(f"ERROR: {err}", ColorCodes.RED), file=sys.stderr)
    print(f"\nDone: {int(ok)} succeeded, {int(not ok)} failed")
    return 0 if ok else 1


def snapshot_batch(args: argparse.Namespace) -> int:
    """Snapshot every project of the selected test set; returns the exit code."""
    try:
        projects = batch_projects(selected_test_set(args))
    except ProjectSelectionError as exc:
        print(colorize(f"ERROR: {exc}", ColorCodes.RED), file=sys.stderr)
        return 1
    total = len(projects)
    print(f"Creating snapshots for {total} projects\n")
    success_count = 0
    for idx, project in enumerate(projects, start=1):
        print(f"[{idx}/{total}] {project.name} ... ", end="", flush=True)
        ok, err = _parse_and_snapshot(project.source, _default_output(project, project.name))
        success_count += int(ok)
        print(colorize("OK", ColorCodes.GREEN) if ok else colorize(f"FAILED: {err}", ColorCodes.RED))
    fail_count = total - success_count
    print(f"\nDone: {success_count} succeeded, {fail_count} failed")
    return 1 if fail_count > 0 else 0


def build_parser() -> argparse.ArgumentParser:
    """The options of ``visualize/schema-snapshot.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False
    )
    add_selection_arguments(parser)
    parser.add_argument("--output", help="Explicit output file path (single mode; overrides the default location).")
    parser.add_argument("--self-test", action="store_true",
                        help="Run only the self-test: a planted example is snapshotted, and the refusals.")
    return parser


def _check_a_planted_example_is_snapshotted() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project = plant_example("01-foundation", Path(tmp))
        assert snapshot_source(str(project / "system.dtrx"), None) == 0
        snapshot = project / DOCS_DIR_NAME / SNAPSHOTS_DIR_NAME / "system.json"
        data = json.loads(snapshot.read_text(encoding="utf-8"))
        assert "BookService" in json.dumps(data), sorted(data)


def _check_a_missing_source_fails_and_no_selection_is_refused() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        assert snapshot_source(str(Path(tmp) / "no-such.dtrx"), str(Path(tmp) / "out.json")) == 1
        assert not (Path(tmp) / "out.json").exists()
    expect_usage_error(lambda: require_selection(build_parser().parse_args([])), "-Source")


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        checks = [_check_a_planted_example_is_snapshotted, _check_a_missing_source_fails_and_no_selection_is_refused]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=build_parser(),
                             folder=VISUALIZE_SCRIPTS_DIR)
    require_selection(args)
    return snapshot_source(args.source, args.output) if args.source else snapshot_batch(args)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    install_sigint_handler()
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
