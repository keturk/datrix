"""Collect string literals from Datrix Python projects and write a grouped Markdown report.

``scripts/metrics/find-constants.ps1`` (and its ``.sh`` twin) runs this module. It scans ``src/`` and
``tests/`` (when present) for each project by default. Use ``--src`` or ``--tests`` alone to limit to that
tree. Docstrings are excluded by default.

Exit codes: 0 = report written (or nothing to scan); 1 = no project given, an invalid option value, a
project that does not exist, or a failed self-test check.

Usage:
    python -m datrix_scripts.metrics.find_constants datrix-common   (PYTHONPATH=scripts/common/lib)
    python -m datrix_scripts.metrics.find_constants datrix-common --tests
    python -m datrix_scripts.metrics.find_constants --all --output ./out.md

    Or use the PowerShell wrapper:
        .\\scripts\\metrics\\find-constants.ps1 -All
        .\\scripts\\metrics\\find-constants.ps1 datrix-common -Tests
        .\\scripts\\metrics\\find-constants.ps1 datrix-common -Output .\\my-report.md
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import io
import sys
import tempfile
from collections import defaultdict
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final

from datrix_scripts.gate_harness import write_files
from datrix_scripts.logic_map import resolve_scan_paths
from datrix_scripts.metrics.projects import add_project_arguments
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.test.wrappers import METRICS_SCRIPTS_DIR, module_main, run_self_test

MODULE: Final = "datrix_scripts.metrics.find_constants"
WRAPPER: Final = "find-constants"

DEFAULT_REPORT_NAME: Final = "string-constants-report.md"
DEFAULT_MIN_LENGTH: Final = 1
DEFAULT_MAX_VALUE_CHARS: Final = 120
EXIT_OK: Final = 0
EXIT_FAILED: Final = 1
USAGE_LINES: Final = (
    "Usage:",
    "  .\\find-constants.ps1 <project> [project2 ...] [-Src] [-Tests] [-Output path] [-IncludeDocstrings] "
    "[-MinLength N] [-MaxValueChars N]",
    "  .\\find-constants.ps1 -All [-Src] [-Tests] [-Output path] [-IncludeDocstrings] "
    "[-MinLength N] [-MaxValueChars N]",
    "",
    "Use Get-Help .\\find-constants.ps1 -Full for detailed help.",
)


@dataclass(frozen=True)
class Occurrence:
    """One string literal site."""

    value: str
    path: Path
    lineno: int



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
        return Path.cwd() / DEFAULT_REPORT_NAME
    arg = arg.expanduser()
    if arg.exists() and arg.is_dir():
        return arg / DEFAULT_REPORT_NAME
    return arg


def build_parser() -> argparse.ArgumentParser:
    """The options of ``metrics/find-constants.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        description="Find string literals in Datrix Python projects and emit a grouped Markdown report.",
        allow_abbrev=False,
    )
    add_project_arguments(parser)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=f"Report file path (default: ./{DEFAULT_REPORT_NAME} under current working directory)",
    )
    parser.add_argument(
        "--include-docstrings",
        action="store_true",
        help="Include module/class/function docstrings as literals",
    )
    parser.add_argument(
        "--min-length",
        type=int,
        default=DEFAULT_MIN_LENGTH,
        metavar="N",
        help=f"Minimum string length to include (default: {DEFAULT_MIN_LENGTH})",
    )
    parser.add_argument(
        "--max-value-chars",
        type=int,
        default=DEFAULT_MAX_VALUE_CHARS,
        metavar="N",
        help=f"Max characters from the value shown in the section heading (default: {DEFAULT_MAX_VALUE_CHARS})",
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
    parser.add_argument("--self-test", action="store_true", help="Run only the self-test over planted projects.")
    parser.set_defaults(debug=False)
    return parser


def _scan_scope(src: bool, tests: bool) -> tuple[bool, bool, str]:
    """(include src, include tests, label) for the ``--src`` / ``--tests`` switches."""
    if src and not tests:
        return True, False, "src only"
    if tests and not src:
        return False, True, "tests only"
    return True, True, "src and tests"


def _collect_occurrences(
    scan_pairs: list[tuple[str, Path]], datrix_root: Path, *, include_docstrings: bool, min_length: int
) -> list[Occurrence]:
    """Every literal under the distinct scan roots of *scan_pairs*, in scan order."""
    occurrences: list[Occurrence] = []
    seen_dirs: set[Path] = set()
    for _project_name, directory in scan_pairs:
        resolved = directory.resolve()
        if resolved in seen_dirs:
            continue
        seen_dirs.add(resolved)
        if not resolved.is_dir():
            continue
        for py_file in iter_python_files(resolved):
            occurrences.extend(
                collect_from_file(
                    py_file,
                    datrix_root,
                    include_docstrings=include_docstrings,
                    min_length=min_length,
                )
            )
    return occurrences


def _scan(args: argparse.Namespace, projects: list[str]) -> int:
    """Scan *projects* (or every package under ``--all``) and write the report."""
    include_src, include_tests, scan_scope_label = _scan_scope(args.src, args.tests)
    datrix_root = WORKSPACE_DIR
    try:
        scan_pairs = resolve_scan_paths(
            datrix_root,
            projects,
            args.all,
            include_src=include_src,
            include_tests=include_tests,
        )
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_FAILED

    if not scan_pairs:
        print("No src/ or tests/ directories found to scan.")
        return EXIT_OK

    all_occurrences = _collect_occurrences(
        scan_pairs, datrix_root, include_docstrings=args.include_docstrings, min_length=args.min_length
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
    return EXIT_OK


def _plant_project(root: Path, source: str) -> Path:
    """``<root>/datrix-a/src/m.py`` holding *source*; returns the ``src`` folder."""
    write_files(root, {"datrix-a/src/m.py": source})
    return root / "datrix-a" / "src"


def _planted_occurrences(source: str, *, include_docstrings: bool, min_length: int) -> list[Occurrence]:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        src = _plant_project(root, source)
        return _collect_occurrences(
            [("datrix-a", src)], root, include_docstrings=include_docstrings, min_length=min_length
        )


def _check_planted_literals_are_grouped() -> None:
    occurrences = _planted_occurrences('a = "x"\nb = "x"\nc = "y"\n', include_docstrings=False, min_length=1)
    groups = group_by_value(occurrences)
    sites = {value: [(str(o.path), o.lineno) for o in group] for value, group in groups.items()}
    expected = {
        "x": [(str(Path("datrix-a/src/m.py")), 1), (str(Path("datrix-a/src/m.py")), 2)],
        "y": [(str(Path("datrix-a/src/m.py")), 3)],
    }
    assert sites == expected, sites


def _check_docstrings_excluded_by_default() -> None:
    source = '"""module doc"""\nvalue = "kept"\n'
    without = {o.value for o in _planted_occurrences(source, include_docstrings=False, min_length=1)}
    with_docs = {o.value for o in _planted_occurrences(source, include_docstrings=True, min_length=1)}
    assert without == {"kept"}, without
    assert with_docs == {"kept", "module doc"}, with_docs


def _check_min_length_filters() -> None:
    source = 'a = "x"\nb = "yy"\n'
    kept = {o.value for o in _planted_occurrences(source, include_docstrings=False, min_length=2)}
    assert kept == {"yy"}, kept


def _check_nothing_given_prints_the_wrapper_usage() -> None:
    printed = io.StringIO()
    with contextlib.redirect_stdout(printed):
        code = main([])
    assert code == EXIT_FAILED, code
    assert printed.getvalue().splitlines() == list(USAGE_LINES), printed.getvalue()


SELF_TEST_CHECKS: Final[tuple[Callable[[], None], ...]] = (
    _check_planted_literals_are_grouped,
    _check_docstrings_excluded_by_default,
    _check_min_length_filters,
    _check_nothing_given_prints_the_wrapper_usage,
)


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        return run_self_test(
            SELF_TEST_CHECKS, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=METRICS_SCRIPTS_DIR
        )
    projects = [*args.positional_projects, *args.projects]
    if not projects and not args.all:
        for line in USAGE_LINES:
            print(line)
        return EXIT_FAILED
    if args.min_length < DEFAULT_MIN_LENGTH:
        print(f"ERROR: --min-length must be >= {DEFAULT_MIN_LENGTH}", file=sys.stderr)
        return EXIT_FAILED
    return _scan(args, projects)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
