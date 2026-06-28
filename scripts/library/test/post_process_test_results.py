#!/usr/bin/env python3
"""
Post-process generated project test results to generate index.json.

Reads JUnit XML files from a test results directory and generates structured
index.json using GeneratedTestLogWriter. This enables troubleshooting skills
to consume the results.

This script is used by project test wrappers (e.g., test-ecommerce.ps1) to
automatically generate index.json after running tests, making test results
compatible with datrix troubleshooting skills.

Usage:
    python post_process_test_results.py <test_results_dir> [--project-name NAME] [--source-dtrx PATH]
    python post_process_test_results.py D:/.generated/python/docker-compose/local/03-domains/ecommerce/python/.test_results/unit-tests-20260514-224028

Options:
    --project-name NAME    Override project name detection (default: auto-detect from path)
    --source-dtrx PATH     Override source .dtrx path (default: auto-detect)
    --language LANG        Override language (default: auto-detect, python/typescript)
    --platform PLAT        Override platform (default: docker)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add library directory to path
_script_dir = Path(__file__).parent
_library_dir = _script_dir.parent
if str(_library_dir) not in sys.path:
    sys.path.insert(0, str(_library_dir))

from shared.generated_test_log_writer import GeneratedTestLogWriter
from shared.venv import get_datrix_root


def detect_metadata(results_dir: Path) -> dict[str, str]:
    """
    Auto-detect project metadata from directory structure.

    Args:
        results_dir: Path to test results directory

    Returns:
        Dict with project_name, language, platform, source_dtrx
    """
    # Navigate up from .test_results/unit-tests-TIMESTAMP to project root
    # Expected: .projects/{project}/python/.test_results/unit-tests-TIMESTAMP
    project_root = results_dir.parent.parent  # .projects/{project}/python
    project_parent = project_root.parent  # .projects/{project}

    # Detect language from directory name
    language = "python"
    if project_root.name == "typescript":
        language = "typescript"

    # Detect project name from parent directory
    project_name = project_parent.name

    # Default platform
    platform = "docker"

    # Try to find source .dtrx file
    datrix_root = get_datrix_root()

    # Check examples/{project}/system.dtrx
    source_dtrx = datrix_root / "datrix" / "examples" / project_name / "system.dtrx"

    return {
        "project_name": project_name,
        "language": language,
        "platform": platform,
        "source_dtrx": str(source_dtrx) if source_dtrx.exists() else "",
    }


def post_process_results(
    results_dir: Path,
    project_name: str | None = None,
    source_dtrx: str | None = None,
    language: str | None = None,
    platform: str | None = None,
) -> int:
    """
    Post-process test results to generate index.json.

    Args:
        results_dir: Path to test results directory (e.g., .test_results/unit-tests-TIMESTAMP)
        project_name: Override project name (default: auto-detect)
        source_dtrx: Override source .dtrx path (default: auto-detect)
        language: Override language (default: auto-detect)
        platform: Override platform (default: docker)

    Returns:
        Exit code (0 = success, 1 = failure)
    """
    if not results_dir.exists():
        print(f"Error: Results directory not found: {results_dir}", file=sys.stderr)
        return 1

    if not results_dir.is_dir():
        print(f"Error: Not a directory: {results_dir}", file=sys.stderr)
        return 1

    # Check for services directory with JUnit XML files
    services_dir = results_dir / "services"
    if not services_dir.exists() or not services_dir.is_dir():
        print(
            f"Error: Services directory not found: {services_dir}", file=sys.stderr
        )
        print(
            "Expected structure: {results_dir}/services/{service_name}/junit.xml",
            file=sys.stderr,
        )
        return 1

    # Count JUnit XML files
    junit_files = list(services_dir.glob("*/junit.xml"))
    if not junit_files:
        print(
            f"Warning: No JUnit XML files found in {services_dir}", file=sys.stderr
        )
        print("Test results may not have been saved properly.", file=sys.stderr)
        return 1

    print(f"Found {len(junit_files)} service test results in {results_dir}")

    # Auto-detect metadata if not provided
    metadata = detect_metadata(results_dir)
    project_name = project_name or metadata["project_name"]
    language = language or metadata["language"]
    platform = platform or metadata["platform"]
    source_dtrx = source_dtrx or metadata["source_dtrx"]

    print(f"Project: {project_name}")
    print(f"Language: {language}")
    print(f"Platform: {platform}")
    print(f"Source: {source_dtrx}")

    try:
        # Create writer
        writer = GeneratedTestLogWriter(
            project_path=project_name,
            language=language,
            platform=platform,
            example=project_name,
            run_dir=results_dir,
            dtrx_source=source_dtrx,
        )

        # Add all service results
        found_services = 0
        for service_dir in sorted(services_dir.iterdir()):
            if not service_dir.is_dir():
                continue

            junit_xml = service_dir / "junit.xml"
            service_log = service_dir / "service.log"

            # Service log might be in parent directory with pattern {service_name}-tests.log
            if not service_log.exists():
                alt_log = results_dir / f"{service_dir.name}-tests.log"
                if alt_log.exists():
                    service_log = alt_log

            if junit_xml.is_file():
                try:
                    writer.add_service_junit_xml(
                        service_dir.name, junit_xml, service_log
                    )
                    found_services += 1
                except Exception as exc:
                    print(
                        f"Warning: Failed to parse JUnit XML for {service_dir.name}: {exc}",
                        file=sys.stderr,
                    )

        if found_services == 0:
            print(
                "Error: No service results were successfully parsed", file=sys.stderr
            )
            return 1

        print(f"Parsed {found_services} service test results")

        # Write index.json (duration = 0 since we don't have timing data)
        index_path = writer.write(duration_seconds=0.0)
        print(f"Success: Generated {index_path}")

        return 0

    except Exception as exc:
        print(f"Error: Failed to generate index.json: {exc}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Post-process test results to generate index.json"
    )
    parser.add_argument("results_dir", help="Test results directory path")
    parser.add_argument("--project-name", help="Override project name")
    parser.add_argument("--source-dtrx", help="Override source .dtrx path")
    parser.add_argument("--language", help="Override language (python/typescript)")
    parser.add_argument("--platform", help="Override platform (default: docker)")

    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    return post_process_results(
        results_dir,
        project_name=args.project_name,
        source_dtrx=args.source_dtrx,
        language=args.language,
        platform=args.platform,
    )


if __name__ == "__main__":
    sys.exit(main())
