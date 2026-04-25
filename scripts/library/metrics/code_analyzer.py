#!/usr/bin/env python3
"""Scan Python sources and emit a grouped Markdown report of symbols plus duplicate top-level names.

Resolves scan packages with the same ``datrix-*`` rule as metrics ``-All`` (not the broader
``datrix*`` glob used by find_constants). Report path defaults to ``./code-structure-report.md``
under the process current working directory.

Usage:
    python code_analyzer.py datrix-common
    python code_analyzer.py --all --tests
    python code_analyzer.py --all --src --tests --output my-report.md
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final

_LIBRARY_DIR = Path(__file__).resolve().parent.parent
if _LIBRARY_DIR.exists() and str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from dev.find_constants import iter_python_files  # noqa: E402
from shared.venv import get_datrix_root  # noqa: E402

CONSTANT_NAME_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Z][A-Z0-9_]*$")
DEFAULT_REPORT_NAME = "code-structure-report.md"


@dataclass(frozen=True)
class MethodEntry:
    """One callable under a class (possibly nested)."""

    name: str
    lineno: int
    role: str


@dataclass(frozen=True)
class ClassEntry:
    """A module-level class and its methods."""

    name: str
    lineno: int
    methods: tuple[MethodEntry, ...]


@dataclass(frozen=True)
class FuncEntry:
    """Module-level function or nested qualified name."""

    name: str
    lineno: int
    is_async: bool


@dataclass(frozen=True)
class ConstEntry:
    name: str
    lineno: int


@dataclass(frozen=True)
class AliasEntry:
    name: str
    lineno: int


@dataclass(frozen=True)
class FileSymbols:
    """Parsed symbols for one ``.py`` file."""

    rel_posix: str
    classes: tuple[ClassEntry, ...]
    module_functions: tuple[FuncEntry, ...]
    constants: tuple[ConstEntry, ...]
    type_aliases: tuple[AliasEntry, ...]


@dataclass
class PublicNameRef:
    """One module-level class or function site for duplicate detection."""

    name: str
    project: str
    rel_posix: str
    lineno: int
    kind: str


def _decorator_role(deco: ast.expr) -> str | None:
    if isinstance(deco, ast.Name):
        if deco.id in ("staticmethod", "classmethod", "property"):
            return deco.id
        return None
    if isinstance(deco, ast.Attribute) and isinstance(deco.value, ast.Name):
        if deco.attr in ("staticmethod", "classmethod", "property"):
            return deco.attr
    return None


def _method_role(decorators: list[ast.expr]) -> str:
    for d in decorators:
        role = _decorator_role(d)
        if role is not None:
            return role
    return "method"


def _collect_nested_functions(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    prefix: str,
) -> list[FuncEntry]:
    nested: list[FuncEntry] = []
    for child in node.body:
        if isinstance(child, ast.FunctionDef):
            qual = f"{prefix}.{child.name}"
            nested.append(FuncEntry(qual, child.lineno, False))
            nested.extend(_collect_nested_functions(child, qual))
        elif isinstance(child, ast.AsyncFunctionDef):
            qual = f"{prefix}.{child.name}"
            nested.append(FuncEntry(qual, child.lineno, True))
            nested.extend(_collect_nested_functions(child, qual))
    return nested


def _collect_nested_methods(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    prefix: str,
    default_role: str,
) -> list[MethodEntry]:
    out: list[MethodEntry] = []
    for child in node.body:
        if isinstance(child, ast.FunctionDef):
            qual = f"{prefix}.{child.name}"
            out.append(MethodEntry(qual, child.lineno, "method"))
            out.extend(_collect_nested_methods(child, qual, "method"))
        elif isinstance(child, ast.AsyncFunctionDef):
            qual = f"{prefix}.{child.name}"
            out.append(MethodEntry(qual, child.lineno, "method"))
            out.extend(_collect_nested_methods(child, qual, "method"))
    return out


def _class_methods(class_node: ast.ClassDef) -> tuple[MethodEntry, ...]:
    methods: list[MethodEntry] = []
    for child in class_node.body:
        if isinstance(child, ast.FunctionDef):
            role = _method_role(child.decorator_list)
            methods.append(MethodEntry(child.name, child.lineno, role))
            methods.extend(_collect_nested_methods(child, child.name, role))
        elif isinstance(child, ast.AsyncFunctionDef):
            role = _method_role(child.decorator_list)
            methods.append(MethodEntry(child.name, child.lineno, role))
            methods.extend(_collect_nested_methods(child, child.name, role))
    methods.sort(key=lambda m: m.name.lower())
    return tuple(methods)


def _is_constant_assign_targets(targets: list[ast.expr]) -> bool:
    if not targets:
        return False
    for t in targets:
        if not isinstance(t, ast.Name):
            return False
        if not CONSTANT_NAME_RE.match(t.id):
            return False
    return True


def _parse_module(
    tree: ast.Module,
    rel_posix: str,
    public_refs: list[PublicNameRef],
    project: str,
) -> FileSymbols:
    classes: list[ClassEntry] = []
    module_functions: list[FuncEntry] = []
    constants: list[ConstEntry] = []
    type_aliases: list[AliasEntry] = []

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            classes.append(
                ClassEntry(
                    name=node.name,
                    lineno=node.lineno,
                    methods=_class_methods(node),
                )
            )
            if not node.name.startswith("_"):
                public_refs.append(
                    PublicNameRef(
                        name=node.name,
                        project=project,
                        rel_posix=rel_posix,
                        lineno=node.lineno,
                        kind="class",
                    )
                )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            is_async = isinstance(node, ast.AsyncFunctionDef)
            module_functions.append(
                FuncEntry(node.name, node.lineno, is_async),
            )
            module_functions.extend(_collect_nested_functions(node, node.name))
            if not node.name.startswith("_"):
                public_refs.append(
                    PublicNameRef(
                        name=node.name,
                        project=project,
                        rel_posix=rel_posix,
                        lineno=node.lineno,
                        kind="function",
                    )
                )
        elif isinstance(node, ast.Assign):
            if _is_constant_assign_targets(node.targets):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        constants.append(ConstEntry(t.id, node.lineno))
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and CONSTANT_NAME_RE.match(node.target.id):
                constants.append(ConstEntry(node.target.id, node.lineno))
        elif hasattr(ast, "TypeAlias") and isinstance(node, ast.TypeAlias):
            if isinstance(node.name, ast.Name):
                type_aliases.append(AliasEntry(node.name.id, node.lineno))

    classes.sort(key=lambda c: c.name.lower())
    module_functions.sort(key=lambda f: f.name.lower())
    constants.sort(key=lambda c: c.name.lower())
    type_aliases.sort(key=lambda a: a.name.lower())

    return FileSymbols(
        rel_posix=rel_posix,
        classes=tuple(classes),
        module_functions=tuple(module_functions),
        constants=tuple(constants),
        type_aliases=tuple(type_aliases),
    )


def parse_python_file(
    scan_root: Path,
    py_path: Path,
    project: str,
    public_refs: list[PublicNameRef],
) -> FileSymbols | None:
    rel = py_path.resolve().relative_to(scan_root.resolve())
    rel_posix = rel.as_posix()
    try:
        text = py_path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        print(f"Warning: could not read {py_path}: {exc}", file=sys.stderr)
        return None
    try:
        tree = ast.parse(text, filename=str(py_path))
    except SyntaxError as exc:
        print(f"Warning: syntax error in {py_path}: {exc}", file=sys.stderr)
        return None
    if not isinstance(tree, ast.Module):
        return None
    return _parse_module(tree, rel_posix, public_refs, project)


def resolve_scan_roots(
    datrix_root: Path,
    project_names: list[str],
    scan_all: bool,
    *,
    include_src: bool,
    include_tests: bool,
) -> list[tuple[str, str, Path]]:
    """Return ``(project_name, root_label, path)`` for each scan root.

    ``root_label`` is ``src`` or ``tests``. ``scan_all`` uses only directories named
    ``datrix-*`` (metrics glob), excluding the bare ``datrix`` package folder.
    """
    pairs: list[tuple[str, str, Path]] = []
    if scan_all:
        for d in sorted(datrix_root.iterdir()):
            if not d.is_dir() or not d.name.startswith("datrix-"):
                continue
            if include_src:
                src_dir = d / "src"
                if src_dir.is_dir():
                    pairs.append((d.name, "src", src_dir))
                else:
                    print(
                        f"Warning: {d.name} has no src/ directory; skipped for src scan.",
                        file=sys.stderr,
                    )
            if include_tests:
                tests_dir = d / "tests"
                if tests_dir.is_dir():
                    pairs.append((d.name, "tests", tests_dir))
                else:
                    print(
                        f"Warning: {d.name} has no tests/ directory; skipped for tests scan.",
                        file=sys.stderr,
                    )
        return pairs

    available = sorted(
        x.name
        for x in datrix_root.iterdir()
        if x.is_dir() and x.name.startswith("datrix-")
    )
    for clean in project_names:
        name = clean.rstrip("/\\")
        project_dir = datrix_root / name
        if not project_dir.is_dir():
            raise FileNotFoundError(
                f"Project '{name}' not found under {datrix_root}. Available: {available}"
            )
        if include_src:
            src_dir = project_dir / "src"
            if src_dir.is_dir():
                pairs.append((name, "src", src_dir))
            else:
                print(
                    f"Warning: {name} has no src/ directory; skipped for src scan.",
                    file=sys.stderr,
                )
        if include_tests:
            tests_dir = project_dir / "tests"
            if tests_dir.is_dir():
                pairs.append((name, "tests", tests_dir))
            else:
                print(
                    f"Warning: {name} has no tests/ directory; skipped for tests scan.",
                    file=sys.stderr,
                )
    return pairs


def resolve_output_path(output: Path | None) -> Path:
    """Resolve report path against ``Path.cwd()`` unless ``output`` is absolute."""
    cwd = Path.cwd()
    if output is None:
        return (cwd / DEFAULT_REPORT_NAME).resolve()
    if output.is_absolute():
        return output.resolve()
    return (cwd / output).resolve()


def build_duplicate_section(refs: list[PublicNameRef]) -> tuple[list[str], int]:
    """Return markdown lines for names that appear under at least two distinct file paths."""
    by_name: dict[str, list[PublicNameRef]] = defaultdict(list)
    for r in refs:
        by_name[r.name].append(r)

    lines: list[str] = []
    dup_keys = 0
    for name in sorted(by_name.keys(), key=str.lower):
        entries = by_name[name]
        distinct_paths = {(e.project, e.rel_posix) for e in entries}
        if len(distinct_paths) < 2:
            continue
        dup_keys += 1
        lines.append(f"### `{name}`")
        lines.append("")
        sorted_entries = sorted(entries, key=lambda e: (e.project, e.rel_posix, e.lineno))
        for e in sorted_entries:
            lines.append(
                f"- **{e.kind}** `{e.project}/{e.rel_posix}` line {e.lineno}",
            )
        lines.append("")

    return lines, dup_keys


def write_report(
    out_path: Path,
    *,
    sections: list[tuple[str, str, list[FileSymbols]]],
    duplicate_lines: list[str],
    datrix_root: Path,
    projects_scanned: list[str],
    scan_scope_label: str,
    files_parsed: int,
    duplicate_name_count: int,
) -> None:
    local_ts = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    cwd = Path.cwd().resolve()
    lines: list[str] = [
        "# Python code structure report",
        "",
        "## Summary",
        "",
        f"- **Generated (local):** {local_ts}",
        f"- **Working directory:** `{cwd}`",
        f"- **Datrix root:** `{datrix_root}`",
        f"- **Projects (distinct):** {', '.join(projects_scanned)}",
        f"- **Scan scope:** {scan_scope_label}",
        f"- **Python files parsed:** {files_parsed}",
        f"- **Duplicate top-level names (cross-file):** {duplicate_name_count}",
        "",
        "---",
        "",
    ]

    for project, root_label, files in sections:
        if not files:
            continue
        lines.append(f"## {project} ({root_label})")
        lines.append("")
        for fs in files:
            lines.append(f"### `{fs.rel_posix}`")
            lines.append("")
            if fs.classes:
                lines.append("**Classes**")
                lines.append("")
                for c in fs.classes:
                    lines.append(f"- **{c.name}** (line {c.lineno})")
                    for m in c.methods:
                        lines.append(f"  - `{m.name}` ({m.role}) L{m.lineno}")
                lines.append("")
            if fs.module_functions:
                lines.append("**Module functions**")
                lines.append("")
                for f in fs.module_functions:
                    async_prefix = "async " if f.is_async else ""
                    lines.append(f"- `{async_prefix}{f.name}` L{f.lineno}")
                lines.append("")
            if fs.constants:
                lines.append("**Constants**")
                lines.append("")
                for c in fs.constants:
                    lines.append(f"- `{c.name}` L{c.lineno}")
                lines.append("")
            if fs.type_aliases:
                lines.append("**Type aliases**")
                lines.append("")
                for a in fs.type_aliases:
                    lines.append(f"- `{a.name}` L{a.lineno}")
                lines.append("")

    lines.append("## Duplicate top-level class/function names")
    lines.append("")
    lines.append(
        "Names that appear as a module-level **class** or **function** in at least "
        "**two different files** (leading `_` excluded). Same name in one file only is omitted.",
    )
    lines.append("")
    if duplicate_lines:
        lines.extend(duplicate_lines)
    else:
        lines.append("*No cross-file duplicates found in the scanned set.*")
        lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build a Markdown report of Python classes, functions, constants, and type "
            "aliases under each package src/ or tests/ tree. Default output path is "
            f"{DEFAULT_REPORT_NAME} under the current working directory; relative --output "
            "is resolved against the cwd."
        ),
    )
    parser.add_argument(
        "projects",
        nargs="*",
        metavar="PROJECT",
        help="One or more package names (e.g. datrix-common). Ignored when --all is set.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Scan every datrix-* package under the monorepo root (metrics -All semantics).",
    )
    parser.add_argument(
        "--src",
        action="store_true",
        help="Include each package's src/ tree (default when --tests is not used alone).",
    )
    parser.add_argument(
        "--tests",
        action="store_true",
        help="Include each package's tests/ tree (use alone for tests-only scan).",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help=(
            f"Report file (default: ./{DEFAULT_REPORT_NAME} under cwd). "
            "Relative paths are resolved against the current working directory."
        ),
    )
    parser.add_argument("--debug", action="store_true", help="Print scan roots to stderr.")
    args = parser.parse_args()

    if not args.projects and not args.all:
        parser.print_help()
        print("\nProvide project names or use --all.", file=sys.stderr)
        return 1

    if args.tests and not args.src:
        include_src, include_tests = False, True
        scan_scope_label = "tests only"
    elif args.src and not args.tests:
        include_src, include_tests = True, False
        scan_scope_label = "src only"
    elif args.src and args.tests:
        include_src, include_tests = True, True
        scan_scope_label = "src and tests"
    else:
        include_src, include_tests = True, False
        scan_scope_label = "src only"

    try:
        datrix_root = get_datrix_root().resolve()
    except FileNotFoundError:
        print("ERROR: Could not find Datrix root directory.", file=sys.stderr)
        return 1

    try:
        scan_triples = resolve_scan_roots(
            datrix_root,
            list(args.projects),
            args.all,
            include_src=include_src,
            include_tests=include_tests,
        )
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if not scan_triples:
        print("No scan directories found (missing src/ and/or tests/ per flags).")
        return 0

    if args.debug:
        for proj, label, root in scan_triples:
            print(f"debug: scan {proj} ({label}) -> {root}", file=sys.stderr)

    public_refs: list[PublicNameRef] = []
    sections: list[tuple[str, str, list[FileSymbols]]] = []
    files_parsed = 0
    current_key: tuple[str, str] | None = None
    current_files: list[FileSymbols] = []

    for project, root_label, root in scan_triples:
        key = (project, root_label)
        if current_key != key:
            if current_key is not None:
                sections.append((current_key[0], current_key[1], current_files))
            current_key = key
            current_files = []
        for py_file in sorted(iter_python_files(root), key=lambda p: str(p).lower()):
            fs = parse_python_file(root, py_file, project, public_refs)
            if fs is not None:
                current_files.append(fs)
                files_parsed += 1
    if current_key is not None:
        sections.append((current_key[0], current_key[1], current_files))

    dup_lines, dup_count = build_duplicate_section(public_refs)
    out_path = resolve_output_path(args.output)
    projects_distinct = sorted({p for p, _, _ in scan_triples})

    write_report(
        out_path,
        sections=sections,
        duplicate_lines=dup_lines,
        datrix_root=datrix_root,
        projects_scanned=projects_distinct,
        scan_scope_label=scan_scope_label,
        files_parsed=files_parsed,
        duplicate_name_count=dup_count,
    )

    print(
        f"Wrote report: {out_path} ({files_parsed} file(s) parsed, "
        f"{dup_count} duplicate top-level name(s) across files).",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
