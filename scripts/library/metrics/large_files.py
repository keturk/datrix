#!/usr/bin/env python3
"""
Find and list top N files by line count in a Datrix project's src and tests trees.

Walks both src/ and tests/ (at least one must exist). Default: Python files only.
Supports summary and json output formats.

Usage:
    python large_files.py --project-root D:\\datrix\\datrix-common
    python large_files.py --project-root D:\\datrix\\datrix-common --top 30 --format json
    python large_files.py --project-root D:\\datrix\\datrix-language --suffix ""
    python large_files.py --project-root D:\\datrix\\datrix-common --threshold 500
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_FOLDERS_TO_SKIP = (
    "__pycache__",
    ".git",
    ".venv",
    "node_modules",
    ".pytest_cache",
)
DEFAULT_FORMAT = "summary"
DEFAULT_SUFFIX = "py"
DEFAULT_TOP = 20


def _parse_suffixes(suffix: str) -> frozenset[str] | None:
    """Return normalized set of suffixes, or None if empty (meaning all)."""
    if not suffix or not suffix.strip():
        return None
    return frozenset(s.strip().lower() for s in suffix.split(",") if s.strip())


def _parse_folders_to_skip(value: str) -> frozenset[str]:
    """Return set of folder names to skip."""
    return frozenset(s.strip() for s in value.split(",") if s.strip())


def _count_lines(path: Path) -> int:
    """Count lines in file; read with UTF-8. Raises on error (fail fast)."""
    return len(path.read_text(encoding="utf-8").splitlines())


def _collect_files(
    project_root: Path,
    roots: list[Path],
    suffixes: frozenset[str] | None,
    folders_to_skip: frozenset[str],
) -> list[tuple[str, int]]:
    """Return list of (path_relative_to_project_root, line_count). Raises on read error."""
    results: list[tuple[str, int]] = []
    for root in roots:
        if not root.is_dir():
            continue
        for f in root.rglob("*"):
            if not f.is_file():
                continue
            try:
                rel = f.relative_to(project_root)
            except ValueError:
                continue
            parts = rel.parts
            if any(p in folders_to_skip for p in parts):
                continue
            if suffixes is not None:
                ext = f.suffix
                if ext.startswith("."):
                    ext = ext[1:].lower()
                if ext not in suffixes:
                    continue
            try:
                n = _count_lines(f)
            except (OSError, UnicodeDecodeError) as e:
                raise RuntimeError(f"Error reading {rel}: {e}") from e
            results.append((rel.as_posix(), n))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Top N files by line count (src + tests) for a Datrix project.",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        required=True,
        help="Path to the project root (containing src/ and/or tests/).",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=DEFAULT_TOP,
        help=f"Number of largest files to list (default: {DEFAULT_TOP}).",
    )
    parser.add_argument(
        "--suffix",
        type=str,
        default=DEFAULT_SUFFIX,
        help="Comma-separated file suffixes to include (default: py). Use \"\" for all.",
    )
    parser.add_argument(
        "--folders-to-skip",
        type=str,
        default=",".join(DEFAULT_FOLDERS_TO_SKIP),
        help="Comma-separated folder names to skip.",
    )
    parser.add_argument(
        "--format",
        choices=("summary", "json"),
        default=DEFAULT_FORMAT,
        help=f"Output format (default: {DEFAULT_FORMAT}).",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=0,
        help="Only include files with at least this many lines (0 = no filter).",
    )
    parser.add_argument("--verbose", action="store_true", help="Verbose output.")
    parser.add_argument("--debug", action="store_true", help="Debug output.")

    args = parser.parse_args()
    project_root = args.project_root.resolve()
    if not project_root.is_dir():
        print(
            f"Error: project root is not a directory: {project_root}",
            file=sys.stderr,
        )
        return 1

    src = project_root / "src"
    tests = project_root / "tests"
    if not src.is_dir() and not tests.is_dir():
        print(
            f"Error: project has neither src/ nor tests/: {project_root}",
            file=sys.stderr,
        )
        return 1

    roots = [d for d in (src, tests) if d.is_dir()]
    suffixes = _parse_suffixes(args.suffix)
    folders_to_skip = _parse_folders_to_skip(args.folders_to_skip)

    if args.verbose or args.debug:
        print(
            f"Scanning {[str(r) for r in roots]} (suffixes={suffixes or 'all'})",
            file=sys.stderr,
        )

    try:
        collected = _collect_files(project_root, roots, suffixes, folders_to_skip)
    except (OSError, UnicodeDecodeError, RuntimeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    if args.threshold > 0:
        collected = [x for x in collected if x[1] >= args.threshold]
    collected.sort(key=lambda x: (-x[1], x[0]))
    top_n = collected[: args.top]

    if args.format == "json":
        out = {
            "project_root": str(project_root),
            "top": args.top,
            "files": [{"path": p, "lines": n} for p, n in top_n],
        }
        print(json.dumps(out, indent=2))
    else:
        width = max((len(str(n)) for _, n in top_n), default=1)
        for path, n in top_n:
            print(f"{n:>{width}}  {path}")

    if args.threshold > 0:
        print(f"LARGE_FILES_COUNT: {len(top_n)}", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
