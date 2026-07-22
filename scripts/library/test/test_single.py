#!/usr/bin/env python3
"""Lightweight single-test runner for checkpoint-based debugging.

Runs exactly one test file, class, or method with minimal overhead.
Designed for the fix-one-verify-one workflow.

Usage:
  python scripts/library/test/test_single.py <test-path> [--project <name>] [--keyword <expr>]
  .\\scripts\\test\\test-single.ps1 tests/test_foo.py -Project datrix-common
"""

import argparse
import io
import re
import subprocess
import sys
from pathlib import Path

# Configure UTF-8 encoding for stdout/stderr on Windows
if sys.platform == "win32":
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Add library directory to sys.path
library_dir = Path(__file__).resolve().parent.parent
if library_dir.exists() and str(library_dir) not in sys.path:
    sys.path.insert(0, str(library_dir))

from shared.venv import get_datrix_root  # noqa: E402


def resolve_project(test_path: str, project_name: str, workspace_root: Path) -> Path:
    """Resolve the project root directory.

    Args:
        test_path: Test path provided by user (may encode project).
        project_name: Explicit project name from --project flag.
        workspace_root: Datrix workspace root.

    Returns:
        Resolved project root path.

    Raises:
        SystemExit: If project cannot be resolved.
    """
    if project_name:
        project_root = workspace_root / project_name
        if not project_root.is_dir():
            print(f"ERROR: Project not found: {project_root}", file=sys.stderr)
            sys.exit(2)
        return project_root

    if test_path:
        # Try to resolve from full path
        test_path_obj = Path(test_path)
        if test_path_obj.is_absolute() and test_path_obj.exists():
            # Walk up to find datrix-* directory
            current = test_path_obj if test_path_obj.is_dir() else test_path_obj.parent
            while current != current.parent:
                if current.name.startswith("datrix-"):
                    return current
                current = current.parent

        # Try regex extraction from path string
        match = re.search(r"(datrix-[^/\\]+)", test_path)
        if match:
            project_root = workspace_root / match.group(1)
            if project_root.is_dir():
                return project_root

    print("ERROR: Cannot determine project. Use --project to specify explicitly.", file=sys.stderr)
    sys.exit(2)


def resolve_test_path(test_path: str, project_root: Path) -> str:
    """Resolve the test path relative to the project root.

    Args:
        test_path: Raw test path (absolute, relative, or node ID).
        project_root: Project root directory.

    Returns:
        Test path suitable for passing to pytest.
    """
    if not test_path:
        return ""

    # Node ID format (contains ::) — pass through
    if "::" in test_path:
        # If the file part is absolute, make relative
        parts = test_path.split("::", 1)
        file_part = Path(parts[0])
        if file_part.is_absolute():
            try:
                rel = file_part.relative_to(project_root)
                return f"{rel}::{parts[1]}"
            except ValueError:
                return test_path
        return test_path

    # Absolute path
    path_obj = Path(test_path)
    if path_obj.is_absolute():
        if path_obj.exists():
            try:
                return str(path_obj.relative_to(project_root))
            except ValueError:
                return test_path
        return test_path

    # Relative path — check if it exists relative to project
    candidate = project_root / test_path
    if candidate.exists():
        return test_path

    # Normalize slashes and try again
    normalized = test_path.replace("\\", "/")
    candidate = project_root / normalized
    if candidate.exists():
        return normalized

    # Pass through as-is, let pytest report the error
    return test_path


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run a single test file or pattern quickly",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "test_path",
        nargs="?",
        default="",
        help="Path to test file or pytest node ID (file::class::method)",
    )
    parser.add_argument("--project", default="", help="Project name (e.g., datrix-common)")
    parser.add_argument("--keyword", "-k", default="", help="Pytest -k filter expression")
    parser.add_argument("--marker", "-m", default="", help="Pytest -m marker filter")
    parser.add_argument("--verbose", action="store_true", help="Verbose pytest output")
    parser.add_argument("--fail-fast", action="store_true", help="Stop on first failure")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")

    args = parser.parse_args()

    if not args.test_path and not args.keyword:
        parser.print_help()
        return 2

    try:
        workspace_root = get_datrix_root()
    except FileNotFoundError:
        print("ERROR: Could not find Datrix root directory", file=sys.stderr)
        return 1

    # Resolve project
    project_root = resolve_project(args.test_path, args.project, workspace_root)
    project_name = project_root.name

    if args.debug:
        print(f"[DEBUG] Project: {project_name} at {project_root}", file=sys.stderr)

    # Build pytest arguments
    pytest_args: list[str] = [sys.executable, "-m", "pytest"]

    # Resolve and add test path
    if args.test_path:
        resolved = resolve_test_path(args.test_path, project_root)
        if resolved:
            pytest_args.append(resolved)
        if args.debug:
            print(f"[DEBUG] Resolved test path: {resolved}", file=sys.stderr)

    # Filters
    if args.keyword:
        pytest_args.extend(["-k", args.keyword])
    if args.marker:
        pytest_args.extend(["-m", args.marker])

    # Output mode
    if args.verbose:
        pytest_args.append("-v")
    else:
        pytest_args.extend(["-q", "--tb=short"])

    # Fail fast
    if args.fail_fast:
        pytest_args.append("-x")

    # Disable xdist for single-test runs (speed)
    pytest_args.append("-p")
    pytest_args.append("no:xdist")

    # Run pytest
    print()
    print(f"Running: {' '.join(pytest_args[2:])}")  # Skip python -m
    print(f"Project: {project_name}")
    print("─" * 60)
    print()

    result = subprocess.run(
        pytest_args,
        cwd=project_root,
    )

    print()
    if result.returncode == 0:
        print("PASSED")
    else:
        print(f"FAILED (exit code: {result.returncode})")

    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
