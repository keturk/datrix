#!/usr/bin/env python3
r"""Audit generated Python code for placeholders and syntax errors.

Scans .generated/python/docker (or a given path) for:
- Python syntax errors (ast.parse)
- Placeholder patterns: pass, raise NotImplementedError, "# Test fixtures placeholder"

Paths matching db/base.py or _microservice_helpers.py are allowlisted (excluded from
--fail-on-placeholders). See datrix/scripts/dev/README.md.

Usage:
    python scripts/library/dev/audit_generated.py [--output-base .generated] [--report path.md]

From repository root. Use --report to write a markdown report file.
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import sys
from pathlib import Path

# Add library directory to sys.path
library_dir = Path(__file__).resolve().parent.parent
if library_dir.exists() and str(library_dir) not in sys.path:
    sys.path.insert(0, str(library_dir))

from shared.venv import get_datrix_root

# Patterns for placeholder scan (path -> list of (line_no, line_text))
PATTERN_PASS = re.compile(r"\bpass\b")
PATTERN_NOT_IMPLEMENTED = re.compile(r"raise\s+NotImplementedError\s*\(")
PATTERN_TEST_PLACEHOLDER = re.compile(r"#\s*Test\s+fixtures\s+placeholder", re.I)

# Path substrings that are allowlisted (intentional placeholders; excluded from --fail-on-placeholders)
ALLOWLIST_PATH_SUBSTRINGS = ("db/base.py", "_microservice_helpers.py")


def _path_is_allowlisted(path_str: str) -> bool:
    """Return True if path matches an allowlist pattern (intentional placeholder)."""
    normalized = path_str.replace("\\", "/")
    return any(sub in normalized for sub in ALLOWLIST_PATH_SUBSTRINGS)


def _split_placeholders(
    placeholder_hits: dict[str, list[tuple[int, str]]],
) -> tuple[dict[str, list[tuple[int, str]]], dict[str, list[tuple[int, str]]]]:
    """Split placeholder hits into actionable vs allowlisted."""
    actionable: dict[str, list[tuple[int, str]]] = {}
    allowlisted: dict[str, list[tuple[int, str]]] = {}
    for path, hits in placeholder_hits.items():
        if _path_is_allowlisted(path):
            allowlisted[path] = hits
        else:
            actionable[path] = hits
    return actionable, allowlisted


def _find_py_files(root: Path) -> list[Path]:
    """Return sorted list of .py files under root."""
    return sorted(root.rglob("*.py"))


def check_syntax(root: Path) -> list[tuple[str, int, str]]:
    """Run ast.parse on each .py under root. Return list of (path, line, msg)."""
    errors: list[tuple[str, int, str]] = []
    for py in _find_py_files(root):
        try:
            ast.parse(py.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError as e:
            errors.append((str(py), e.lineno or 0, e.msg))
    return errors


def scan_placeholders(root: Path) -> dict[str, list[tuple[int, str]]]:
    """Scan for pass, NotImplementedError, Test fixtures placeholder. Return path -> [(line_no, line)]."""
    results: dict[str, list[tuple[int, str]]] = {}
    for py in _find_py_files(root):
        path_str = str(py)
        try:
            lines = py.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        hits: list[tuple[int, str]] = []
        for i, line in enumerate(lines, start=1):
            if PATTERN_PASS.search(line):
                hits.append((i, line.strip()[:80]))
            elif PATTERN_NOT_IMPLEMENTED.search(line):
                hits.append((i, line.strip()[:80]))
            elif PATTERN_TEST_PLACEHOLDER.search(line):
                hits.append((i, line.strip()[:80]))
        if hits:
            results[path_str] = hits
    return results


def write_report(
    output_path: Path,
    syntax_errors: list[tuple[str, int, str]],
    actionable_hits: dict[str, list[tuple[int, str]]],
    allowlisted_hits: dict[str, list[tuple[int, str]]],
    root: Path,
) -> None:
    """Write a markdown report to output_path. Actionable hits fail CI; allowlisted are excluded."""
    total_py = len(_find_py_files(root))
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("# Generated Code Audit Report\n\n")
        f.write(f"**Generated root:** `{root}`\n\n")
        f.write(f"**Python files scanned:** {total_py}\n\n")
        f.write("## Syntax check (ast.parse)\n\n")
        if not syntax_errors:
            f.write("**Result:** 0 errors.\n\n")
        else:
            f.write(f"**Result:** {len(syntax_errors)} file(s) with syntax errors.\n\n")
            for path, line, msg in sorted(syntax_errors):
                f.write(f"- `{path}` line {line}: {msg}\n")
        f.write("\n## Placeholder scan\n\n")
        total_hits = len(actionable_hits) + len(allowlisted_hits)
        f.write(
            f"**Actionable:** {len(actionable_hits)} files "
            f"(allowlisted excluded: {len(allowlisted_hits)}).\n\n"
        )
        for path in sorted(actionable_hits.keys()):
            f.write(f"### {path}\n\n")
            for line_no, line in actionable_hits[path]:
                f.write(f"- L{line_no}: `{line}`\n")
            f.write("\n")
        if allowlisted_hits:
            f.write("## Allowlisted (excluded from failure)\n\n")
            f.write(
                f"**Files:** {len(allowlisted_hits)} "
                f"(paths matching `db/base.py` or `_microservice_helpers.py`).\n\n"
            )
            for path in sorted(allowlisted_hits.keys()):
                f.write(f"### {path}\n\n")
                for line_no, line in allowlisted_hits[path]:
                    f.write(f"- L{line_no}: `{line}`\n")
                f.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit generated Python code for placeholders and syntax errors."
    )
    parser.add_argument(
        "--output-base",
        type=str,
        default=".generated",
        help="Output base directory (default: .generated)",
    )
    parser.add_argument(
        "--subpath",
        type=str,
        default="python/docker",
        help="Subpath under output-base to scan (default: python/docker)",
    )
    parser.add_argument(
        "--report",
        type=str,
        default=None,
        help="Write markdown report to this path",
    )
    parser.add_argument(
        "--fail-on-syntax",
        action="store_true",
        help="Exit with non-zero if any syntax errors found",
    )
    parser.add_argument(
        "--fail-on-placeholders",
        action="store_true",
        help="Exit with non-zero if any placeholder patterns found",
    )
    args = parser.parse_args()

    try:
        datrix_root = get_datrix_root()
    except FileNotFoundError:
        print("ERROR: Could not find Datrix root directory", file=sys.stderr)
        return 1

    root = datrix_root / args.output_base / args.subpath.replace("/", os.sep)
    if not root.is_dir():
        print(f"ERROR: Generated root not found: {root}", file=sys.stderr)
        return 1

    syntax_errors = check_syntax(root)
    placeholder_hits = scan_placeholders(root)
    actionable_hits, allowlisted_hits = _split_placeholders(placeholder_hits)
    total_py = len(_find_py_files(root))

    # Console summary
    print(f"Scanned: {root}")
    print(f"Python files: {total_py}")
    print(f"Syntax errors: {len(syntax_errors)}")
    print(f"Files with placeholder patterns: {len(placeholder_hits)} (actionable: {len(actionable_hits)}, allowlisted: {len(allowlisted_hits)})")
    if syntax_errors:
        for path, line, msg in sorted(syntax_errors)[:20]:
            print(f"  {path}:{line} {msg}")
        if len(syntax_errors) > 20:
            print(f"  ... and {len(syntax_errors) - 20} more")

    if args.report:
        report_path = Path(args.report)
        if not report_path.is_absolute():
            report_path = datrix_root / report_path
        report_path.parent.mkdir(parents=True, exist_ok=True)
        write_report(
            report_path,
            syntax_errors,
            actionable_hits,
            allowlisted_hits,
            root,
        )
        print(f"Report written: {report_path}")

    if args.fail_on_syntax and syntax_errors:
        return 2
    if args.fail_on_placeholders and actionable_hits:
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
