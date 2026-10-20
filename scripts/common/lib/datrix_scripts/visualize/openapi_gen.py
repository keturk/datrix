"""Generate OpenAPI and AsyncAPI specifications from .dtrx source files.

The module behind ``visualize/openapi-gen.ps1`` (and its ``.sh`` twin). Produces one OpenAPI 3.1
YAML per service (every ``rest_api`` block of the service in one document) and one AsyncAPI 3.0
YAML per service (every pubsub block of the service in one document), into
``<project>/docs/openapi/`` and ``<project>/docs/asyncapi/``; clears only those two directories.
One ``--source`` (a relative path is taken from the workspace root), or a batch: ``--all``,
``--domains`` or ``--test-set``.

Exit codes: 0 = every project's specs were built; 1 = a project failed, or the batch named no
project; 2 = neither a source nor a batch flag.

Usage:
    python -m datrix_scripts.visualize.openapi_gen --source=<system.dtrx> [--type=openapi]
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from datrix_scripts.gate_harness import expect_usage_error, install_sigint_handler
from datrix_scripts.logging_utils import ColorCodes, colorize
from datrix_scripts.test.wrappers import VISUALIZE_SCRIPTS_DIR, module_main, run_self_test
from datrix_scripts.venv import SCRIPTS_DEPENDENCY_GROUP, missing_declared_tool
from datrix_scripts.visualization.application_loader import load_application
from datrix_scripts.visualization.json_schema import build_asyncapi_spec, build_openapi_spec
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

try:
    from ruamel.yaml import YAML
except ImportError as exc:
    raise SystemExit(missing_declared_tool("ruamel.yaml", SCRIPTS_DEPENDENCY_GROUP)) from exc

MODULE: Final = "datrix_scripts.visualize.openapi_gen"
WRAPPER: Final = "openapi-gen"
OPENAPI: Final = "openapi"
ASYNCAPI: Final = "asyncapi"
ALL_TYPES: Final = "all"
VALID_TYPES: Final = (OPENAPI, ASYNCAPI, ALL_TYPES)
DEFAULT_PROFILE: Final = "test"

#: The ``docs/`` subdirectory each spec type writes -- and the only ones this
#: script clears, so a service renamed or removed since the last run leaves no
#: stale document behind.
SPEC_OUTPUT_DIRS: Final[dict[str, str]] = {OPENAPI: "openapi", ASYNCAPI: "asyncapi"}


def _clear_owned_spec_dirs(docs_dir: Path, spec_types: list[str]) -> None:
    """Delete the files in the output directory of every requested spec type."""
    for spec_type, subdir_name in SPEC_OUTPUT_DIRS.items():
        if spec_type not in spec_types:
            continue
        subdir = docs_dir / subdir_name
        if subdir.is_dir():
            for old_file in subdir.iterdir():
                if old_file.is_file():
                    old_file.unlink()


def _write_yaml(data: dict[str, object], output_path: Path) -> None:
    """Write a dict as block-style YAML to file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    yaml = YAML()
    yaml.default_flow_style = False
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f)


def _generate_specs(
    source_path: Path,
    output_path: Path,
    spec_types: list[str],
    profile: str,
) -> tuple[bool, list[str], list[str]]:
    """Generate OpenAPI/AsyncAPI specs for a single project.

    Returns (success, warnings, errors).
    """
    from datrix_common.paths import ServicePaths

    warnings: list[str] = []
    errors: list[str] = []

    try:
        app = load_application(source_path, profile)
    except Exception as e:
        errors.append(f"Load error: {e}")
        return False, warnings, errors

    _clear_owned_spec_dirs(output_path / DOCS_DIR_NAME, spec_types)
    file_count = 0

    # One OpenAPI document per service, covering every rest_api block
    if OPENAPI in spec_types:
        for service in app.services.values():
            if not service.rest_apis:
                continue
            try:
                spec = build_openapi_spec(service, app)
            except Exception as e:
                errors.append(f"OpenAPI for {service.name}: {e}")
                continue
            sname = ServicePaths(service.name).simple_name
            spec_path = output_path / DOCS_DIR_NAME / SPEC_OUTPUT_DIRS[OPENAPI] / f"{sname}.yaml"
            _write_yaml(spec, spec_path)
            print(f"  OpenAPI: {spec_path}")
            file_count += 1

    # One AsyncAPI document per service, covering every pubsub block
    if ASYNCAPI in spec_types:
        for service in app.services.values():
            if not service.pubsub_blocks:
                continue
            try:
                spec = build_asyncapi_spec(service)
            except Exception as e:
                errors.append(f"AsyncAPI for {service.name}: {e}")
                continue
            sname = ServicePaths(service.name).simple_name
            spec_path = output_path / DOCS_DIR_NAME / SPEC_OUTPUT_DIRS[ASYNCAPI] / f"{sname}.yaml"
            _write_yaml(spec, spec_path)
            print(f"  AsyncAPI: {spec_path}")
            file_count += 1

    if file_count == 0 and not errors:
        warnings.append("No REST APIs or PubSub blocks found — no specs generated.")

    return not errors, warnings, errors


def _spec_types(selected: str) -> list[str]:
    return [OPENAPI, ASYNCAPI] if selected == ALL_TYPES else [selected]


def specs_for_source(args: argparse.Namespace) -> int:
    """Specs for ``--source`` (relative to the workspace root); returns the exit code."""
    project = Project(name="", source=workspace_path(args.source))
    print(f"Source: {project.source}")
    print(f"Output: {project.directory}")
    print(f"Profile: {args.profile}")
    ok, warnings, errors = _generate_specs(project.source, project.directory, _spec_types(args.type), args.profile)
    for err in errors:
        print(colorize(f"  ERROR: {err}", ColorCodes.RED))
    for warn in warnings:
        print(colorize(f"  WARNING: {warn}", ColorCodes.YELLOW))
    print(f"\nDone: {int(ok)} succeeded, {int(not ok)} failed")
    return 0 if ok else 1


def specs_for_batch(args: argparse.Namespace) -> int:
    """Specs for every project of the selected test set; returns the exit code."""
    test_set = selected_test_set(args)
    try:
        projects = batch_projects(test_set)
    except ProjectSelectionError as exc:
        print(colorize(f"ERROR: {exc}", ColorCodes.RED), file=sys.stderr)
        return 1
    total = len(projects)
    print(f"Generating API specs for {total} projects (test set: {test_set}, profile: {args.profile})\n")
    success_count = 0
    for idx, project in enumerate(projects, start=1):
        print(f"[{idx}/{total}] {project.name}")
        ok, warnings, errors = _generate_specs(project.source, project.directory, _spec_types(args.type), args.profile)
        success_count += int(ok)
        if ok:
            print(colorize("  -> OK", ColorCodes.GREEN))
        for err in errors:
            print(colorize(f"  -> FAILED: {err}", ColorCodes.RED))
        for warn in warnings:
            print(colorize(f"  -> WARNING: {warn}", ColorCodes.YELLOW))
    fail_count = total - success_count
    print(f"\nDone: {success_count} succeeded, {fail_count} failed")
    return 1 if fail_count > 0 else 0


def build_parser() -> argparse.ArgumentParser:
    """The options of ``visualize/openapi-gen.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False
    )
    add_selection_arguments(parser)
    parser.add_argument("--type", default=ALL_TYPES, choices=VALID_TYPES, help="Spec type (default: all).")
    parser.add_argument("--profile", default=DEFAULT_PROFILE, help="Config profile to resolve (default: test).")
    parser.add_argument("--self-test", action="store_true",
                        help="Run only the self-test: specs of a planted example, and the refusals.")
    return parser


_PLANTED_EXAMPLE: Final = "02-features/02-service-architecture/serverless"


def _check_a_planted_example_gets_its_specs() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project = plant_example(_PLANTED_EXAMPLE, Path(tmp))
        stale = project / DOCS_DIR_NAME / SPEC_OUTPUT_DIRS[OPENAPI] / "stale.yaml"
        stale.parent.mkdir(parents=True)
        stale.write_text("stale", encoding="utf-8")
        args = build_parser().parse_args([f"--source={project}"])
        assert specs_for_source(args) == 0
        docs = project / DOCS_DIR_NAME
        assert not stale.exists(), "a stale spec survived the run"
        assert list((docs / SPEC_OUTPUT_DIRS[OPENAPI]).glob("*.yaml")), sorted(docs.rglob("*"))
        assert list((docs / SPEC_OUTPUT_DIRS[ASYNCAPI]).glob("*.yaml")), sorted(docs.rglob("*"))


def _check_a_missing_source_fails_and_no_selection_is_refused() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        args = build_parser().parse_args([f"--source={Path(tmp) / 'no-such.dtrx'}"])
        assert specs_for_source(args) == 1
    expect_usage_error(lambda: require_selection(build_parser().parse_args([])), "-Source")


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        checks = [_check_a_planted_example_gets_its_specs, _check_a_missing_source_fails_and_no_selection_is_refused]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=build_parser(),
                             folder=VISUALIZE_SCRIPTS_DIR)
    require_selection(args)
    return specs_for_source(args) if args.source else specs_for_batch(args)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    install_sigint_handler()
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
