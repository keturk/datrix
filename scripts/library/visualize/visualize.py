#!/usr/bin/env python3
"""Generate Mermaid diagrams from .dtrx source files.

Supports single-file and batch modes. Produces Markdown-wrapped Mermaid
diagrams or raw .mmd files for all 8 diagram types.
"""

from __future__ import annotations

import argparse
import io
import os
import signal
import sys
from pathlib import Path

# ── UTF-8 for Windows ──
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def _sigint_handler(_signum: int, _frame: object) -> None:
    sys.exit(130)


signal.signal(signal.SIGINT, _sigint_handler)

# ── sys.path setup ──
library_dir = Path(__file__).resolve().parent.parent
if library_dir.exists() and str(library_dir) not in sys.path:
    sys.path.insert(0, str(library_dir))

from shared.venv import get_datrix_root  # noqa: E402

datrix_root = get_datrix_root()
for sub in ("datrix-common/src", "datrix-language/src"):
    p = datrix_root / sub
    if p.exists() and str(p) not in sys.path:
        sys.path.insert(0, str(p))

from shared.logging_utils import ColorCodes, colorize  # noqa: E402
from shared.test_projects import get_test_projects  # noqa: E402
from shared.visualization.mermaid import DIAGRAM_TYPES, build_diagram  # noqa: E402
from shared.visualization.svg import build_event_flow_svg  # noqa: E402
from shared.visualization.svg_cqrs import build_cqrs_svg  # noqa: E402
from shared.visualization.svg_erd import build_erd_svgs  # noqa: E402
from shared.visualization.svg_infrastructure import build_infrastructure_svg  # noqa: E402
from shared.visualization.svg_inheritance import build_inheritance_svgs  # noqa: E402
from shared.visualization.svg_service_map import build_service_map_svg  # noqa: E402
from shared.visualization.svg_system_context import build_system_context_svg  # noqa: E402

# Diagram types that use SVG instead of Mermaid
SVG_DIAGRAM_TYPES = {
    "event-flow", "erd", "service-map", "inheritance",
    "infrastructure", "system-context", "cqrs-flow",
}

VALID_DIAGRAM_TYPES = tuple(DIAGRAM_TYPES.keys()) + ("all",)
VALID_FORMATS = ("md", "mmd")


def _parse_application(source_path: Path, profile: str) -> object:
    """Parse a .dtrx file, resolve configs, and run semantic analysis.

    Args:
        source_path: Path to .dtrx file.
        profile: Config profile to resolve (e.g. 'test', 'development').

    Returns the resolved Application object with configs attached.
    """
    from datrix_language.parser import TreeSitterParser
    from datrix_common.semantic import SemanticAnalyzer
    from datrix_common.config_resolution import (
        resolve_service_configs,
        resolve_infrastructure_configs,
    )

    project_root = source_path.parent

    parser = TreeSitterParser()
    ast = parser.parse_file(source_path)

    # Stage 1: resolve service configs (before semantic analysis)
    resolve_service_configs(ast, project_root, profile)

    # Semantic analysis
    analyzer = SemanticAnalyzer()
    result = analyzer.analyze(ast)
    app = result.app

    # Stage 2: resolve infrastructure configs (after semantic analysis)
    resolve_infrastructure_configs(app, project_root, profile)

    return app


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
        title = DIAGRAM_TYPES.get(diagram_type, diagram_type)
        if diagram_type == "api-catalog":
            # API catalog is already Markdown, no code fence needed
            md_content = f"# {title}\n\n{content}\n"
        else:
            md_content = f"# {title}\n\n```mermaid\n{content}\n```\n"
        file_path = output_dir / f"{diagram_type}.md"
        file_path.write_text(md_content, encoding="utf-8")

    return file_path


def _generate_for_project(
    source_path: Path,
    output_path: Path,
    diagram_types: list[str],
    service_name: str | None,
    output_format: str,
    profile: str = "test",
) -> tuple[bool, list[str], list[str]]:
    """Generate diagrams for a single project.

    Returns (success, warnings, errors).
    """
    warnings: list[str] = []
    errors: list[str] = []

    # Resolve system.dtrx if directory given
    if source_path.is_dir():
        system_dtrx = source_path / "system.dtrx"
        if system_dtrx.exists():
            source_path = system_dtrx
        else:
            errors.append(f"No system.dtrx found in {source_path}")
            return False, warnings, errors

    if not source_path.exists():
        errors.append(f"Source file not found: {source_path}")
        return False, warnings, errors

    # Parse with config resolution
    try:
        app = _parse_application(source_path, profile)
    except Exception as e:
        errors.append(f"Parse error: {e}")
        return False, warnings, errors

    # Clean output directories before generating
    docs_dir = output_path / "docs"
    for subdir_name in ("diagrams", "diagrams/ERDs", "diagrams/inheritance", "openapi", "asyncapi"):
        subdir = docs_dir / subdir_name
        if subdir.is_dir():
            for old_file in subdir.iterdir():
                if old_file.is_file():
                    old_file.unlink()

    # Generate diagrams
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
    svg_builders: dict[str, object] = {
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
            svg_content = builder()  # type: ignore[operator]
            if svg_content is None:
                continue
            output_dir.mkdir(parents=True, exist_ok=True)
            svg_path = output_dir / f"{svg_type}.svg"
            svg_path.write_text(svg_content, encoding="utf-8")
            print(f"  {svg_type} (SVG): {svg_path}")
        except Exception as e:
            warnings.append(f"{svg_type} SVG: {e}")
            print(colorize(f"  {svg_type} (SVG): FAILED - {e}", ColorCodes.YELLOW))

    # Per-service ERD SVGs
    if "erd" in diagram_types:
        try:
            erd_svgs = build_erd_svgs(app)
            erd_dir = output_dir / "ERDs"
            erd_dir.mkdir(parents=True, exist_ok=True)
            for svc_name, svg_content in erd_svgs.items():
                svg_path = erd_dir / f"erd-{svc_name}.svg"
                svg_path.write_text(svg_content, encoding="utf-8")
                print(f"  erd (SVG): {svg_path}")
            if not erd_svgs:
                print(colorize("  erd: no services with entities", ColorCodes.YELLOW))
        except Exception as e:
            warnings.append(f"erd SVG: {e}")
            print(colorize(f"  erd (SVG): FAILED - {e}", ColorCodes.YELLOW))

    # Per-service inheritance SVGs
    if "inheritance" in diagram_types:
        try:
            inh_svgs = build_inheritance_svgs(app)
            inh_dir = output_dir / "inheritance"
            inh_dir.mkdir(parents=True, exist_ok=True)
            for svc_name, svg_content in inh_svgs.items():
                svg_path = inh_dir / f"{svc_name}.svg"
                svg_path.write_text(svg_content, encoding="utf-8")
                print(f"  inheritance (SVG): {svg_path}")
            if not inh_svgs:
                print(colorize("  inheritance: no services with entities", ColorCodes.YELLOW))
        except Exception as e:
            warnings.append(f"inheritance SVG: {e}")
            print(colorize(f"  inheritance (SVG): FAILED - {e}", ColorCodes.YELLOW))

    return not errors, warnings, errors


def main() -> int:
    """Entry point for visualization script."""
    parser = argparse.ArgumentParser(
        description="Generate Mermaid diagrams from .dtrx source files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--source", type=str, default=None, help="Path to .dtrx file or directory")
    parser.add_argument("--all", action="store_true", dest="batch_all", help="All projects from test-projects.json")
    parser.add_argument("--tutorial", action="store_true", help="Tutorial examples only")
    parser.add_argument("--domains", action="store_true", help="Domain examples only")
    parser.add_argument("--test-set", type=str, default="all", help="Named test set")
    parser.add_argument("--type", type=str, default="all", choices=VALID_DIAGRAM_TYPES, help="Diagram type")
    parser.add_argument("--service", type=str, default=None, help="Scope to a single service")
    parser.add_argument("--format", type=str, default="md", choices=VALID_FORMATS, help="Output format (md or mmd)")
    parser.add_argument("--profile", type=str, default="test", help="Config profile to resolve (default: test)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    # Determine diagram types
    if args.type == "all":
        diagram_types = list(DIAGRAM_TYPES.keys())
    else:
        diagram_types = [args.type]

    # Determine batch vs single mode
    batch_mode = args.batch_all or args.tutorial or args.domains

    if not batch_mode and not args.source:
        parser.error("Either --source or a batch flag (--all, --tutorial, --domains) is required.")

    success_count = 0
    fail_count = 0

    if args.source:
        # Single project mode — output goes next to the .dtrx source
        source_path = Path(args.source).resolve()
        output_path = source_path.parent if source_path.is_file() else source_path
        print(f"Source: {source_path}")
        print(f"Output: {output_path}")
        print(f"Profile: {args.profile}")
        ok, warnings, errors = _generate_for_project(
            source_path, output_path, diagram_types, args.service, args.format,
            profile=args.profile,
        )
        if ok:
            success_count += 1
        else:
            fail_count += 1
            for err in errors:
                print(colorize(f"  ERROR: {err}", ColorCodes.RED))
    else:
        # Batch mode
        test_set = "all"
        if args.tutorial:
            test_set = "tutorial-all"
        elif args.domains:
            test_set = "domains"
        elif args.test_set != "all":
            test_set = args.test_set

        try:
            projects = get_test_projects(test_set=test_set)
        except Exception as e:
            print(colorize(f"ERROR: Failed to load test projects: {e}", ColorCodes.RED), file=sys.stderr)
            return 1

        if not projects:
            print(colorize(f"No projects found in test set '{test_set}'", ColorCodes.YELLOW))
            return 1

        total = len(projects)
        print(f"Generating diagrams for {total} projects (test set: {test_set}, profile: {args.profile})\n")

        for i, project in enumerate(projects):
            idx = i + 1
            project_name = project.get("name", "unknown")
            source = project.get("path", "")
            output = project.get("output", "")

            source_path = Path(source)
            if not source_path.is_absolute():
                source_path = datrix_root / source

            # Output goes next to the .dtrx source (language-agnostic)
            output_path = source_path.parent if source_path.is_file() else source_path

            print(f"[{idx}/{total}] {project_name}")
            ok, warnings, errors = _generate_for_project(
                source_path, output_path, diagram_types, args.service, args.format,
                profile=args.profile,
            )
            if ok:
                success_count += 1
                print(colorize(f"  -> OK", ColorCodes.GREEN))
            else:
                fail_count += 1
                for err in errors:
                    print(colorize(f"  -> FAILED: {err}", ColorCodes.RED))

    # Summary
    print(f"\nDone: {success_count} succeeded, {fail_count} failed")
    return 1 if fail_count > 0 else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)
