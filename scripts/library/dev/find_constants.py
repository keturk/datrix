#!/usr/bin/env python3
"""Collect string literals from Datrix Python projects and write a grouped Markdown report.

Scans ``src/`` and ``tests/`` (when present) for each project by default. Use ``--src`` or
``--tests`` alone to limit to that tree (same idea as ``projects.ps1`` / ``--src`` /
``--tests``). Docstrings are excluded by default.

Usage:
    python scripts/library/dev/find_constants.py datrix-common
    python scripts/library/dev/find_constants.py datrix-common --tests
    python scripts/library/dev/find_constants.py --all --output ./out.md

    Or use the PowerShell wrapper:
        .\\scripts\\dev\\find-constants.ps1 -All
        .\\scripts\\dev\\find-constants.ps1 datrix-common -Tests
        .\\scripts\\dev\\find-constants.ps1 datrix-common -Output .\\my-report.md
"""

from __future__ import annotations

import argparse
import ast
import io
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator

if sys.platform == "win32" and __name__ == "__main__":
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

_library_dir = Path(__file__).resolve().parent.parent
if _library_dir.exists() and str(_library_dir) not in sys.path:
    sys.path.insert(0, str(_library_dir))

from shared.venv import get_datrix_root


@dataclass(frozen=True)
class Occurrence:
    """One string literal site."""

    value: str
    path: Path
    lineno: int


def resolve_scan_paths(
    datrix_root: Path,
    project_names: list[str],
    scan_all: bool,
    *,
    include_src: bool = True,
    include_tests: bool = True,
) -> list[tuple[str, Path]]:
    """Return ``(project_name, directory)`` pairs for ``src`` / ``tests``.

    Raises:
        FileNotFoundError: If a requested project does not exist under the monorepo root.
    """
    if scan_all:
        pairs: list[tuple[str, Path]] = []
        for d in sorted(datrix_root.iterdir()):
            if not d.is_dir() or not d.name.startswith("datrix"):
                continue
            if include_src and (d / "src").is_dir():
                pairs.append((d.name, d / "src"))
            if include_tests:
                tests_dir = d / "tests"
                if tests_dir.is_dir():
                    pairs.append((d.name, tests_dir))
        return pairs

    pairs = []
    for name in project_names:
        clean = name.rstrip("/\\")
        project_dir = datrix_root / clean
        if not project_dir.is_dir():
            available = sorted(
                d.name for d in datrix_root.iterdir() if d.is_dir() and d.name.startswith("datrix")
            )
            raise FileNotFoundError(
                f"Project '{clean}' not found. Available: {available}"
            )
        if include_src:
            src_dir = project_dir / "src"
            if src_dir.is_dir():
                pairs.append((clean, src_dir))
        if include_tests:
            tests_dir = project_dir / "tests"
            if tests_dir.is_dir():
                pairs.append((clean, tests_dir))
    return pairs


def _docstring_value_node(node: ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef) -> ast.AST | None:
    if not node.body:
        return None
    first = node.body[0]
    if not isinstance(first, ast.Expr):
        return None
    v = first.value
    if isinstance(v, ast.Constant) and isinstance(v.value, str):
        return v
    str_type = getattr(ast, "Str", None)
    if str_type is not None and isinstance(v, str_type):
        return v
    return None


class _StringCollector(ast.NodeVisitor):
    def __init__(
        self,
        *,
        include_docstrings: bool,
        min_length: int,
    ) -> None:
        self._include_docstrings = include_docstrings
        self._min_length = min_length
        self._skip_ids: set[int] = set()
        self.occurrences: list[tuple[int, str]] = []

    def _push_skip_docstring(
        self,
        node: ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> None:
        if self._include_docstrings:
            return
        ds = _docstring_value_node(node)
        if ds is not None:
            self._skip_ids.add(id(ds))

    def _pop_skip_docstring(
        self,
        node: ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> None:
        if self._include_docstrings:
            return
        ds = _docstring_value_node(node)
        if ds is not None:
            self._skip_ids.discard(id(ds))

    def visit_Module(self, node: ast.Module) -> None:
        self._push_skip_docstring(node)
        self.generic_visit(node)
        self._pop_skip_docstring(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._push_skip_docstring(node)
        self.generic_visit(node)
        self._pop_skip_docstring(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._push_skip_docstring(node)
        self.generic_visit(node)
        self._pop_skip_docstring(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._push_skip_docstring(node)
        self.generic_visit(node)
        self._pop_skip_docstring(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if not isinstance(node.value, str):
            return
        if id(node) in self._skip_ids:
            return
        if len(node.value) < self._min_length:
            return
        self.occurrences.append((node.lineno, node.value))

    def visit_Str(self, node: ast.AST) -> None:
        str_type = getattr(ast, "Str", None)
        if str_type is None or not isinstance(node, str_type):
            return
        if id(node) in self._skip_ids:
            return
        s = node.s
        if len(s) < self._min_length:
            return
        self.occurrences.append((node.lineno, s))


def iter_python_files(scan_dir: Path) -> Iterator[Path]:
    for p in scan_dir.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        if p.is_file():
            yield p


def collect_from_file(
    py_file: Path,
    datrix_root: Path,
    *,
    include_docstrings: bool,
    min_length: int,
) -> list[Occurrence]:
    try:
        text = py_file.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        print(f"Warning: could not read {py_file}: {exc}", file=sys.stderr)
        return []
    try:
        tree = ast.parse(text, filename=str(py_file))
    except SyntaxError as exc:
        print(f"Warning: syntax error in {py_file}: {exc}", file=sys.stderr)
        return []

    collector = _StringCollector(
        include_docstrings=include_docstrings,
        min_length=min_length,
    )
    collector.visit(tree)

    try:
        rel = py_file.resolve().relative_to(datrix_root.resolve())
    except ValueError:
        rel = py_file.resolve()

    return [Occurrence(value=v, path=rel, lineno=line) for line, v in collector.occurrences]


def group_by_value(occurrences: list[Occurrence]) -> dict[str, list[Occurrence]]:
    groups: dict[str, list[Occurrence]] = defaultdict(list)
    for o in occurrences:
        groups[o.value].append(o)
    for lst in groups.values():
        lst.sort(key=lambda x: (str(x.path), x.lineno))
    return dict(groups)


def _escape_md_fence(s: str, fence: str = "```") -> str:
    if fence not in s:
        return s
    alt = "`````"
    return s.replace(fence, alt)


def _heading_for_value(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return repr(value)
    preview = value[:max_chars] + "…"
    return repr(preview)


def write_markdown(
    out_path: Path,
    *,
    groups: dict[str, list[Occurrence]],
    datrix_root: Path,
    projects_scanned: list[str],
    cwd: Path,
    max_value_chars: int,
    scan_scope_label: str,
) -> None:
    total_literals = sum(len(v) for v in groups.values())
    distinct = len(groups)
    local_ts = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    lines: list[str] = [
        "# String literals report",
        "",
        "## Summary",
        "",
        f"- **Generated (local):** {local_ts}",
        f"- **Working directory:** `{cwd}`",
        f"- **Datrix root:** `{datrix_root}`",
        f"- **Projects:** {', '.join(projects_scanned)}",
        f"- **Scan scope:** {scan_scope_label}",
        f"- **Total literal occurrences:** {total_literals}",
        f"- **Distinct string values:** {distinct}",
        "",
        "---",
        "",
    ]

    sorted_items = sorted(
        groups.items(),
        key=lambda item: (-len(item[1]), item[0]),
    )

    for value, occs in sorted_items:
        count = len(occs)
        heading = _heading_for_value(value, max_value_chars)

        lines.append(f"## {heading} ({count}x)")
        lines.append("")
        if len(value) > max_value_chars:
            lines.append("Full value:")
            lines.append("")
            lines.append("```text")
            lines.append(_escape_md_fence(value))
            lines.append("```")
            lines.append("")
        for o in occs:
            lines.append(f"- `{o.path}`:{o.lineno}")
        lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8", errors="replace")


def resolve_output_path(arg: Path | None) -> Path:
    if arg is None:
        return Path.cwd() / "string-constants-report.md"
    arg = arg.expanduser()
    if arg.exists() and arg.is_dir():
        return arg / "string-constants-report.md"
    return arg


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Find string literals in Datrix Python projects and emit a grouped Markdown report.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "projects",
        nargs="*",
        help="Project names (e.g. datrix-common datrix-language)",
    )
    parser.add_argument(
        "--all",
        "-a",
        action="store_true",
        dest="scan_all",
        help="Include every datrix* project under the monorepo root",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Report file path (default: ./string-constants-report.md under current working directory)",
    )
    parser.add_argument(
        "--include-docstrings",
        action="store_true",
        help="Include module/class/function docstrings as literals",
    )
    parser.add_argument(
        "--min-length",
        type=int,
        default=1,
        metavar="N",
        help="Minimum string length to include (default: 1)",
    )
    parser.add_argument(
        "--max-value-chars",
        type=int,
        default=120,
        metavar="N",
        help="Max characters from the value shown in the section heading (default: 120)",
    )
    parser.add_argument(
        "--src",
        action="store_true",
        help="Scan only each project's src/ tree (combine with --tests to scan both)",
    )
    parser.add_argument(
        "--tests",
        action="store_true",
        help="Scan only each project's tests/ tree (combine with --src to scan both)",
    )
    args = parser.parse_args()

    if not args.projects and not args.scan_all:
        parser.print_help()
        print("\nProvide project names or use --all.", file=sys.stderr)
        return 1

    if args.min_length < 1:
        print("ERROR: --min-length must be >= 1", file=sys.stderr)
        return 1

    if args.src and not args.tests:
        include_src, include_tests = True, False
        scan_scope_label = "src only"
    elif args.tests and not args.src:
        include_src, include_tests = False, True
        scan_scope_label = "tests only"
    else:
        include_src, include_tests = True, True
        scan_scope_label = "src and tests"

    try:
        datrix_root = get_datrix_root()
    except FileNotFoundError:
        print("ERROR: Could not find Datrix root directory", file=sys.stderr)
        return 1

    try:
        scan_pairs = resolve_scan_paths(
            datrix_root,
            args.projects,
            args.scan_all,
            include_src=include_src,
            include_tests=include_tests,
        )
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if not scan_pairs:
        print("No src/ or tests/ directories found to scan.")
        return 0

    all_occurrences: list[Occurrence] = []
    seen_dirs: set[Path] = set()
    for _project_name, directory in scan_pairs:
        resolved = directory.resolve()
        if resolved in seen_dirs:
            continue
        seen_dirs.add(resolved)
        if not resolved.is_dir():
            continue
        for py_file in iter_python_files(resolved):
            all_occurrences.extend(
                collect_from_file(
                    py_file,
                    datrix_root,
                    include_docstrings=args.include_docstrings,
                    min_length=args.min_length,
                )
            )

    groups = group_by_value(all_occurrences)
    out_path = resolve_output_path(args.output)
    unique_projects = sorted({name for name, _ in scan_pairs})

    write_markdown(
        out_path,
        groups=groups,
        datrix_root=datrix_root.resolve(),
        projects_scanned=unique_projects,
        cwd=Path.cwd().resolve(),
        max_value_chars=args.max_value_chars,
        scan_scope_label=scan_scope_label,
    )

    total = sum(len(v) for v in groups.values())
    print(
        f"Wrote report: {out_path} ({total} occurrence(s), {len(groups)} distinct value(s), "
        f"{len(scan_pairs)} scan root(s))",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
