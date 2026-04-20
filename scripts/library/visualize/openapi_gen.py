#!/usr/bin/env python3
"""Generate OpenAPI and AsyncAPI specifications from .dtrx source files.

Produces OpenAPI 3.1 YAML per REST API and AsyncAPI 3.0 YAML per PubSub block.
Supports single-file and batch modes.
"""

from __future__ import annotations

import argparse
import io
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
from shared.visualization.json_schema import (  # noqa: E402
    build_asyncapi_spec,
    build_openapi_spec,
)

VALID_TYPES = ("openapi", "asyncapi", "all")


def _write_yaml(data: dict[str, object], output_path: Path) -> None:
    """Write a dict as YAML to file.

    Uses ruamel.yaml if available, falls back to json-as-yaml.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from ruamel.yaml import YAML

        yaml = YAML()
        yaml.default_flow_style = False
        with open(output_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)
    except ImportError:
        # Fallback: write as JSON (valid YAML superset)
        import json

        output_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def _generate_specs(
    source_path: Path,
    output_path: Path,
    spec_types: list[str],
) -> tuple[bool, list[str], list[str]]:
    """Generate OpenAPI/AsyncAPI specs for a single project.

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

    # Parse
    try:
        from datrix_language.parser import TreeSitterParser
        from datrix_common.semantic import SemanticAnalyzer
        from datrix_common.paths import ServicePaths

        parser = TreeSitterParser()
        ast = parser.parse_file(source_path)
        analyzer = SemanticAnalyzer()
        result = analyzer.analyze(ast)
        app = result.app
    except Exception as e:
        errors.append(f"Parse error: {e}")
        return False, warnings, errors

    file_count = 0

    # OpenAPI specs
    if "openapi" in spec_types or "all" in spec_types:
        for service in app.services.values():
            for api_name, rest_api in service.rest_apis.items():
                try:
                    spec = build_openapi_spec(service, rest_api)
                    sname = ServicePaths(service.name).simple_name
                    spec_path = output_path / "docs" / "openapi" / f"{sname}.yaml"
                    _write_yaml(spec, spec_path)
                    print(f"  OpenAPI: {spec_path}")
                    file_count += 1
                except Exception as e:
                    warnings.append(f"OpenAPI for {service.name}: {e}")

    # AsyncAPI specs
    if "asyncapi" in spec_types or "all" in spec_types:
        for service in app.services.values():
            for block_name, pubsub_block in service.pubsub_blocks.items():
                try:
                    spec = build_asyncapi_spec(service, pubsub_block)
                    sname = ServicePaths(service.name).simple_name
                    spec_path = output_path / "docs" / "asyncapi" / f"{sname}.yaml"
                    _write_yaml(spec, spec_path)
                    print(f"  AsyncAPI: {spec_path}")
                    file_count += 1
                except Exception as e:
                    warnings.append(f"AsyncAPI for {service.name}: {e}")

    if file_count == 0 and not errors:
        warnings.append("No REST APIs or PubSub blocks found — no specs generated.")

    return not errors, warnings, errors


def main() -> int:
    """Entry point for openapi-gen script."""
    parser = argparse.ArgumentParser(
        description="Generate OpenAPI/AsyncAPI specs from .dtrx source files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--source", type=str, default=None, help="Path to .dtrx file or directory")
    parser.add_argument("--all", action="store_true", dest="batch_all", help="All projects from test-projects.json")
    parser.add_argument("--tutorial", action="store_true", help="Tutorial examples only")
    parser.add_argument("--domains", action="store_true", help="Domain examples only")
    parser.add_argument("--test-set", type=str, default="all", help="Named test set")
    parser.add_argument("--type", type=str, default="all", choices=VALID_TYPES, help="Spec type to generate")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    spec_types = [args.type] if args.type != "all" else ["openapi", "asyncapi"]
    batch_mode = args.batch_all or args.tutorial or args.domains

    if not batch_mode and not args.source:
        parser.error("Either --source or a batch flag (--all, --tutorial, --domains) is required.")

    success_count = 0
    fail_count = 0

    if args.source:
        # Single project mode — output goes next to the .dtrx source
        source_path = Path(args.source)
        if not source_path.is_absolute():
            source_path = datrix_root / source_path

        output_path = source_path.parent if source_path.is_file() else source_path

        print(f"Source: {source_path}")
        print(f"Output: {output_path}")
        ok, warnings, errors = _generate_specs(source_path, output_path, spec_types)
        if ok:
            success_count += 1
        else:
            fail_count += 1
            for err in errors:
                print(colorize(f"  ERROR: {err}", ColorCodes.RED))
        for warn in warnings:
            print(colorize(f"  WARNING: {warn}", ColorCodes.YELLOW))
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
        print(f"Generating API specs for {total} projects (test set: {test_set})\n")

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
            ok, warnings, errors = _generate_specs(source_path, output_path, spec_types)
            if ok:
                success_count += 1
                print(colorize(f"  -> OK", ColorCodes.GREEN))
            else:
                fail_count += 1
                for err in errors:
                    print(colorize(f"  -> FAILED: {err}", ColorCodes.RED))
            for warn in warnings:
                print(colorize(f"  -> WARNING: {warn}", ColorCodes.YELLOW))

    print(f"\nDone: {success_count} succeeded, {fail_count} failed")
    return 1 if fail_count > 0 else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)
