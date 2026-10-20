"""Generate Mermaid and SVG diagrams from .dtrx source files.

The module behind ``visualize/visualize.ps1`` (and its ``.sh`` twin). Produces Markdown-wrapped
Mermaid diagrams or raw ``.mmd`` files, and SVG diagrams, for every diagram type, into
``<project>/docs/diagrams/``. One ``--source`` (a relative path is taken from the current
directory), or a batch: ``--all``, ``--domains`` or ``--test-set``.

Exit codes: 0 = every project loaded; 1 = a project failed to load, or the batch named no project;
2 = neither a source nor a batch flag.

Usage:
    python -m datrix_scripts.visualize.visualize --source=<system.dtrx> [--type=erd] [--format=mmd]
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Final

from datrix_scripts.gate_harness import expect_usage_error, install_sigint_handler
from datrix_scripts.logging_utils import ColorCodes, colorize
from datrix_scripts.test.wrappers import VISUALIZE_SCRIPTS_DIR, module_main, run_self_test
from datrix_scripts.visualization.application_loader import load_application
from datrix_scripts.visualization.mermaid import DIAGRAM_TYPES, build_diagram
from datrix_scripts.visualization.svg import build_event_flow_svg
from datrix_scripts.visualization.svg_cqrs import build_cqrs_svg
from datrix_scripts.visualization.svg_erd import build_erd_svgs
from datrix_scripts.visualization.svg_infrastructure import build_infrastructure_svg
from datrix_scripts.visualization.svg_inheritance import build_inheritance_svgs
from datrix_scripts.visualization.svg_service_map import build_service_map_svg
from datrix_scripts.visualization.svg_system_context import build_system_context_svg
from datrix_scripts.visualize.projects import (
    DOCS_DIR_NAME,
    Project,
    ProjectSelectionError,
    add_selection_arguments,
    batch_projects,
    plant_example,
    require_selection,
    selected_test_set,
)

MODULE: Final = "datrix_scripts.visualize.visualize"
WRAPPER: Final = "visualize"
ALL_TYPES: Final = "all"
DEFAULT_PROFILE: Final = "test"

# Diagram types that use SVG instead of Mermaid
SVG_DIAGRAM_TYPES: Final = {
    "event-flow", "erd", "service-map", "inheritance",
    "infrastructure", "system-context", "cqrs-flow",
}

VALID_DIAGRAM_TYPES: Final = (*DIAGRAM_TYPES.keys(), ALL_TYPES)
VALID_FORMATS: Final = ("md", "mmd")

#: The ``docs/`` subdirectories this script writes, and therefore the only
#: ones it clears before a run. ``docs/openapi`` and ``docs/asyncapi`` belong
#: to ``openapi_gen``; clearing them here left them empty whenever this
#: script ran alone.
DIAGRAM_OUTPUT_DIRS: Final = ("diagrams", "diagrams/ERDs", "diagrams/inheritance")


def _write_diagram(
    content: str,
    diagram_type: str,
    output_dir: Path,
    output_format: str,
) -> Path:
    """Write a diagram to file.

    Args:
        content: Diagram content (Mermaid or Markdown table).
        diagram_type: Diagram type name (for filename).
        output_dir: Directory to write into.
        output_format: 'md' or 'mmd'.

    Returns:
        Path to the written file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    if output_format == "mmd":
        file_path = output_dir / f"{diagram_type}.mmd"
        file_path.write_text(content, encoding="utf-8")
    else:
        # Wrap in Markdown with Mermaid code block
        title = DIAGRAM_TYPES[diagram_type]
        if diagram_type == "api-catalog":
            # API catalog is already Markdown, no code fence needed
            md_content = f"# {title}\n\n{content}\n"
        else:
            md_content = f"# {title}\n\n```mermaid\n{content}\n```\n"
        file_path = output_dir / f"{diagram_type}.md"
        file_path.write_text(md_content, encoding="utf-8")

    return file_path


def _clear_owned_dirs(docs_dir: Path) -> None:
    for subdir_name in DIAGRAM_OUTPUT_DIRS:
        subdir = docs_dir / subdir_name
        if subdir.is_dir():
            for old_file in subdir.iterdir():
                if old_file.is_file():
                    old_file.unlink()


def _write_per_service_svgs(label: str, svgs: dict[str, str], directory: Path, file_prefix: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for svc_name, svg_content in svgs.items():
        svg_path = directory / f"{file_prefix}{svc_name}.svg"
        svg_path.write_text(svg_content, encoding="utf-8")
        print(f"  {label} (SVG): {svg_path}")
    if not svgs:
        print(colorize(f"  {label}: no services with entities", ColorCodes.YELLOW))


def _generate_for_project(
    source_path: Path,
    output_path: Path,
    diagram_types: list[str],
    service_name: str | None,
    output_format: str,
    profile: str,
) -> tuple[bool, list[str], list[str]]:
    """Generate diagrams for a single project.

    Returns (success, warnings, errors).
    """
    warnings: list[str] = []
    errors: list[str] = []

    try:
        app = load_application(source_path, profile)
    except Exception as e:
        errors.append(f"Load error: {e}")
        return False, warnings, errors

    docs_dir = output_path / DOCS_DIR_NAME
    _clear_owned_dirs(docs_dir)
    output_dir = docs_dir / "diagrams"

    # Mermaid diagrams (SVG types are handled separately)
    mermaid_types = [dt for dt in diagram_types if dt not in SVG_DIAGRAM_TYPES]
    for dtype in mermaid_types:
        try:
            content = build_diagram(dtype, app, service_name)
            if content is None:
                continue
            file_path = _write_diagram(content, dtype, output_dir, output_format)
            print(f"  {dtype}: {file_path}")
        except Exception as e:
            warnings.append(f"{dtype}: {e}")
            print(colorize(f"  {dtype}: FAILED - {e}", ColorCodes.YELLOW))

    # SVG diagrams (replace Mermaid versions)
    svg_builders: dict[str, Callable[[], str | None]] = {
        "event-flow": lambda: build_event_flow_svg(app),
        "service-map": lambda: build_service_map_svg(app),
        "infrastructure": lambda: build_infrastructure_svg(app),
        "system-context": lambda: build_system_context_svg(app),
        "cqrs-flow": lambda: build_cqrs_svg(app),
    }
    for svg_type, builder in svg_builders.items():
        if svg_type not in diagram_types:
            continue
        try:
            svg_content = builder()
            if svg_content is None:
                continue
            output_dir.mkdir(parents=True, exist_ok=True)
            svg_path = output_dir / f"{svg_type}.svg"
            svg_path.write_text(svg_content, encoding="utf-8")
            print(f"  {svg_type} (SVG): {svg_path}")
        except Exception as e:
            warnings.append(f"{svg_type} SVG: {e}")
            print(colorize(f"  {svg_type} (SVG): FAILED - {e}", ColorCodes.YELLOW))

    # Per-service ERD and inheritance SVGs
    per_service = (
        ("erd", lambda: build_erd_svgs(app), output_dir / "ERDs", "erd-"),
        ("inheritance", lambda: build_inheritance_svgs(app), output_dir / "inheritance", ""),
    )
    for label, build, directory, file_prefix in per_service:
        if label not in diagram_types:
            continue
        try:
            _write_per_service_svgs(label, build(), directory, file_prefix)
        except Exception as e:
            warnings.append(f"{label} SVG: {e}")
            print(colorize(f"  {label} (SVG): FAILED - {e}", ColorCodes.YELLOW))

    return not errors, warnings, errors


def _diagram_types(selected: str) -> list[str]:
    return list(DIAGRAM_TYPES.keys()) if selected == ALL_TYPES else [selected]


def visualize_source(args: argparse.Namespace) -> int:
    """Diagrams for ``--source`` (relative to the current directory); returns the exit code."""
    project = Project(name="", source=Path(args.source).resolve())
    print(f"Source: {project.source}")
    print(f"Output: {project.directory}")
    print(f"Profile: {args.profile}")
    ok, _warnings, errors = _generate_for_project(
        project.source, project.directory, _diagram_types(args.type), args.service, args.format, args.profile
    )
    for err in errors:
        print(colorize(f"  ERROR: {err}", ColorCodes.RED))
    print(f"\nDone: {int(ok)} succeeded, {int(not ok)} failed")
    return 0 if ok else 1


def visualize_batch(args: argparse.Namespace) -> int:
    """Diagrams for every project of the selected test set; returns the exit code."""
    test_set = selected_test_set(args)
    try:
        projects = batch_projects(test_set)
    except ProjectSelectionError as exc:
        print(colorize(f"ERROR: {exc}", ColorCodes.RED), file=sys.stderr)
        return 1
    total = len(projects)
    print(f"Generating diagrams for {total} projects (test set: {test_set}, profile: {args.profile})\n")
    success_count = 0
    for idx, project in enumerate(projects, start=1):
        print(f"[{idx}/{total}] {project.name}")
        ok, _warnings, errors = _generate_for_project(
            project.source, project.directory, _diagram_types(args.type), args.service, args.format, args.profile
        )
        success_count += int(ok)
        if ok:
            print(colorize("  -> OK", ColorCodes.GREEN))
        for err in errors:
            print(colorize(f"  -> FAILED: {err}", ColorCodes.RED))
    fail_count = total - success_count
    print(f"\nDone: {success_count} succeeded, {fail_count} failed")
    return 1 if fail_count > 0 else 0


def build_parser() -> argparse.ArgumentParser:
    """The options of ``visualize/visualize.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False
    )
    add_selection_arguments(parser)
    parser.add_argument("--type", default=ALL_TYPES, choices=VALID_DIAGRAM_TYPES, help="Diagram type (default: all).")
    parser.add_argument("--service", help="Scope to a single service name.")
    parser.add_argument("--format", default="md", choices=VALID_FORMATS, help="Output format: md or mmd (default: md).")
    parser.add_argument("--profile", default=DEFAULT_PROFILE, help="Config profile to resolve (default: test).")
    parser.add_argument("--self-test", action="store_true",
                        help="Run only the self-test: diagrams of a planted example, and the refusals.")
    return parser


def _check_a_planted_example_gets_its_diagrams() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project = plant_example("01-foundation", Path(tmp))
        args = build_parser().parse_args([f"--source={project / 'system.dtrx'}"])
        assert visualize_source(args) == 0
        diagrams = project / DOCS_DIR_NAME / "diagrams"
        assert (diagrams / "ERDs" / "erd-BookService.svg").is_file(), sorted(diagrams.rglob("*"))
        assert (diagrams / "service-map.svg").is_file(), sorted(diagrams.rglob("*"))


def _check_a_missing_source_fails_and_no_selection_is_refused() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        args = build_parser().parse_args([f"--source={Path(tmp) / 'no-such.dtrx'}"])
        assert visualize_source(args) == 1
    expect_usage_error(lambda: require_selection(build_parser().parse_args([])), "-Source")


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        checks = [_check_a_planted_example_gets_its_diagrams, _check_a_missing_source_fails_and_no_selection_is_refused]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=build_parser(),
                             folder=VISUALIZE_SCRIPTS_DIR)
    require_selection(args)
    return visualize_source(args) if args.source else visualize_batch(args)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    install_sigint_handler()
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
