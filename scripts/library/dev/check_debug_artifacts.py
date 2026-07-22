#!/usr/bin/env python3
"""Detect leftover debug/logging artifacts in source code.

Scans Python and TypeScript source files for common debug patterns that should
not be committed: print(), console.log(), breakpoint(), debugger statements,
and temporary markers.

Usage:
  python scripts/library/dev/check_debug_artifacts.py [path ...] [--strict] [--debug]
  .\\scripts\\dev\\check-debug-artifacts.ps1 -All
"""

import argparse
import io
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

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

# Directories to skip during file discovery
_SKIP_DIRS = frozenset({
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "build", "dist", ".tox", ".mypy_cache", ".pytest_cache",
    ".eggs", ".ruff_cache", ".generated", ".test_results",
})


class Finding(NamedTuple):
    """A single debug artifact finding."""

    file_path: Path
    line_number: int
    label: str
    severity: str
    content: str


@dataclass
class PatternDef:
    """Definition of a debug pattern to scan for."""

    regex: re.Pattern[str]
    label: str
    severity: str


# ── Pattern definitions ─────────────────────────────────────────────────────

_PYTHON_PATTERNS: list[PatternDef] = [
    PatternDef(re.compile(r"^\s*print\("), "print()", "HIGH"),
    PatternDef(re.compile(r"^\s*breakpoint\(\)"), "breakpoint()", "CRITICAL"),
    PatternDef(re.compile(r"^\s*import\s+pdb"), "import pdb", "CRITICAL"),
    PatternDef(re.compile(r"^\s*pdb\.set_trace\(\)"), "pdb.set_trace()", "CRITICAL"),
    PatternDef(re.compile(r"^\s*import\s+ipdb"), "import ipdb", "CRITICAL"),
    PatternDef(re.compile(r"logger\.(warning|error)\(.*DEBUG", re.IGNORECASE), "debug-labeled logger", "HIGH"),
    PatternDef(re.compile(r"logger\.(warning|error)\(.*TEMP", re.IGNORECASE), "temp-labeled logger", "HIGH"),
    PatternDef(re.compile(r"#\s*DEBUG"), "# DEBUG comment", "MEDIUM"),
    PatternDef(re.compile(r"#\s*TEMP"), "# TEMP comment", "MEDIUM"),
    PatternDef(re.compile(r"#\s*HACK"), "# HACK comment", "MEDIUM"),
    PatternDef(re.compile(r"#\s*XXX"), "# XXX comment", "MEDIUM"),
]

_PYTHON_STRICT_PATTERNS: list[PatternDef] = [
    PatternDef(re.compile(r'logger\.(debug|info)\(f["\']'), "logger with f-string (likely temp)", "LOW"),
]

_TYPESCRIPT_PATTERNS: list[PatternDef] = [
    PatternDef(re.compile(r"^\s*console\.(log|warn|error|debug)\("), "console.log()", "HIGH"),
    PatternDef(re.compile(r"^\s*debugger\b"), "debugger statement", "CRITICAL"),
    PatternDef(re.compile(r"//\s*DEBUG"), "// DEBUG comment", "MEDIUM"),
    PatternDef(re.compile(r"//\s*TEMP"), "// TEMP comment", "MEDIUM"),
    PatternDef(re.compile(r"//\s*HACK"), "// HACK comment", "MEDIUM"),
    PatternDef(re.compile(r"//\s*XXX"), "// XXX comment", "MEDIUM"),
]


def find_source_files(
    root: Path,
    skip_dirs: frozenset[str],
    extensions: tuple[str, ...],
) -> list[Path]:
    """Recursively find source files under root, excluding skip_dirs."""
    if not root.is_dir():
        return []
    out: list[Path] = []
    for dir_path, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs and not d.endswith(".egg-info")]
        for name in filenames:
            if name.endswith(extensions):
                out.append(Path(dir_path) / name)
    return sorted(out)


def scan_file(
    file_path: Path,
    patterns: list[PatternDef],
    debug: bool,
) -> list[Finding]:
    """Scan a single file for debug patterns."""
    findings: list[Finding] = []
    try:
        lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return findings

    if debug:
        print(f"[DEBUG] Scanning: {file_path}", file=sys.stderr)

    for i, line in enumerate(lines):
        for pattern in patterns:
            if pattern.regex.search(line):
                findings.append(Finding(
                    file_path=file_path,
                    line_number=i + 1,
                    label=pattern.label,
                    severity=pattern.severity,
                    content=line.strip(),
                ))
                break  # One finding per line
    return findings


def scan_project(
    project_path: Path,
    strict: bool,
    include_generated: bool,
    debug: bool,
) -> list[Finding]:
    """Scan a project for debug artifacts in all source files."""
    findings: list[Finding] = []
    skip = set(_SKIP_DIRS)
    if not include_generated:
        skip.add(".generated")

    # Scan src/ and tests/ directories
    scan_dirs: list[Path] = []
    src_dir = project_path / "src"
    tests_dir = project_path / "tests"
    if src_dir.is_dir():
        scan_dirs.append(src_dir)
    if tests_dir.is_dir():
        scan_dirs.append(tests_dir)

    if not scan_dirs:
        if debug:
            print(f"[DEBUG] Skipping {project_path.name} (no src/ or tests/)", file=sys.stderr)
        return findings

    for scan_dir in scan_dirs:
        # Python files
        py_patterns = _PYTHON_PATTERNS + (_PYTHON_STRICT_PATTERNS if strict else [])
        py_files = find_source_files(scan_dir, frozenset(skip), (".py",))
        for f in py_files:
            findings.extend(scan_file(f, py_patterns, debug))

        # TypeScript files
        ts_files = find_source_files(scan_dir, frozenset(skip), (".ts",))
        for f in ts_files:
            findings.extend(scan_file(f, _TYPESCRIPT_PATTERNS, debug))

    return findings


def severity_rank(severity: str) -> int:
    """Return sort rank for severity (lower = more severe)."""
    ranks = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    return ranks.get(severity, 4)


def report_findings(
    findings_by_project: dict[str, list[Finding]],
    workspace_root: Path,
    debug: bool,
) -> None:
    """Print findings report to stdout."""
    total = sum(len(f) for f in findings_by_project.values())

    print()
    print(f"DEBUG ARTIFACTS DETECTED: {total} finding(s)")
    print("=" * 60)
    print()

    for project_name in sorted(findings_by_project.keys()):
        findings = findings_by_project[project_name]
        print(f"  {project_name} ({len(findings)} findings)")

        sorted_findings = sorted(findings, key=lambda f: severity_rank(f.severity))
        for finding in sorted_findings:
            rel_path = str(finding.file_path).replace(str(workspace_root), "").lstrip("\\/")
            print(f"    [{finding.severity}] {rel_path}:{finding.line_number} — {finding.label}")
            if debug:
                print(f"           {finding.content}")
        print()

    print(f"Summary: {total} artifact(s) across {len(findings_by_project)} project(s)")
    if not debug:
        print("Run with --debug to see matching line content.")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Detect leftover debug/logging artifacts in source code",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=str,
        help="Project directory paths to scan",
    )
    parser.add_argument("--strict", action="store_true", help="Also flag f-string logger calls")
    parser.add_argument("--include-generated", action="store_true", help="Include .generated/ directory")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")

    args = parser.parse_args()

    if not args.paths:
        print("ERROR: No paths provided", file=sys.stderr)
        return 2

    try:
        workspace_root = get_datrix_root()
    except FileNotFoundError:
        workspace_root = Path(args.paths[0]).parent

    findings_by_project: dict[str, list[Finding]] = {}

    for path_str in args.paths:
        project_path = Path(path_str)
        if not project_path.is_dir():
            print(f"WARNING: Not a directory: {project_path}", file=sys.stderr)
            continue

        project_name = project_path.name
        findings = scan_project(
            project_path,
            strict=args.strict,
            include_generated=args.include_generated,
            debug=args.debug,
        )

        if findings:
            findings_by_project[project_name] = findings

    if not findings_by_project:
        print("No debug artifacts found.")
        return 0

    report_findings(findings_by_project, workspace_root, args.debug)
    return 1


if __name__ == "__main__":
    sys.exit(main())
