#!/usr/bin/env python3
"""
Two-pass Vulture dead-code report: classify as "never referenced" or "only referenced by tests".

Runs Vulture once on src only (Pass 1) and once on src + tests (Pass 2). Items in src that
appear in Pass 1 but not in Pass 2 are "only referenced by tests"; items in both are
"never referenced". Output is per-project, or JSON with --output json.

Includes automatic false-positive filtering for common framework patterns (Pydantic, Typer,
Enum, dynamic dispatch). Use --raw to disable filtering.

Usage:
    python dead_code_report.py --workspace-root D:\\datrix [--all | --projects datrix-common ...]
    python dead_code_report.py --workspace-root D:\\datrix --all --output json
    python dead_code_report.py --workspace-root D:\\datrix --all --raw
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

# Default exclude for Pass 1 (src only): exclude tests and cache
EXCLUDE_SRC_ONLY = "*\\tests\\*,*\\test\\*,*__pycache__*,*.git*"
# Pass 2 (src + tests): exclude only cache
EXCLUDE_SRC_AND_TESTS = "*__pycache__*,*.git*"

# Include functions/classes/methods: Vulture reports them at 60% confidence (variables at 100%).
DEFAULT_MIN_CONFIDENCE = 60
DATRIX_PREFIX = "datrix-"

# Vulture output line: path:line: message (N% confidence)
# Path may contain colons on Windows (e.g. C:\...). Symbol in message: unused type 'name'
_LINE_RE = re.compile(
    r"^(.+):(\d+): (unused .+?) \((\d+)% confidence\)\s*$"
)
_SYMBOL_RE = re.compile(r"unused \w+ '([^']+)'")
_KIND_RE = re.compile(r"unused (variable|function|class|method|attribute|import|property|unreachable_code)\s+")
# Display order: classes/functions/methods first, then variables/attributes/imports
KIND_ORDER = ("class", "function", "method", "attribute", "property", "variable", "import", "unreachable_code", "other")
# Human-readable section headers (plural/capitalized)
KIND_LABELS: dict[str, str] = {
    "class": "Classes",
    "function": "Functions",
    "method": "Methods",
    "attribute": "Attributes",
    "property": "Properties",
    "variable": "Variables",
    "import": "Imports",
    "unreachable_code": "Unreachable code",
    "other": "Other",
}

# --- Known false-positive patterns (quick filters) ---
_SKIP_SYMBOLS = frozenset({"model_config", "__all__"})
# Dunder methods that are called by Python itself, not by user code
_SKIP_DUNDER_NAMES = frozenset({
    "__class_getitem__", "__getattr__", "__signature__", "__qualname__", "__doc__",
    "__init_subclass__", "__set_name__", "__repr__", "__str__", "__hash__",
    "__eq__", "__ne__", "__lt__", "__le__", "__gt__", "__ge__", "__len__",
    "__iter__", "__next__", "__contains__", "__getitem__", "__setitem__",
    "__delitem__", "__call__", "__enter__", "__exit__", "__aenter__", "__aexit__",
    "__aiter__", "__anext__", "__bool__", "__format__", "__del__", "__copy__",
    "__deepcopy__", "__reduce__", "__reduce_ex__", "__sizeof__", "__subclasshook__",
    "__init__", "__new__", "__post_init__", "__get__", "__set__", "__delete__",
})
_SKIP_SYMBOL_PREFIXES = ("_transform_",)
_SKIP_PATH_SEGMENTS = ("builtins/objects/", "builtins\\objects\\")

# --- AST-based filter constants ---
_ENUM_BASES = frozenset({"Enum", "StrEnum", "IntEnum", "Flag", "IntFlag"})
_PYDANTIC_BASES = frozenset({"BaseModel", "BaseSettings"})
_VALIDATOR_DECORATORS = frozenset({
    "field_validator", "model_validator", "computed_field", "field_serializer",
})
_COMMAND_DECORATORS = frozenset({"command", "callback"})


class Finding(NamedTuple):
    """A single Vulture finding: file, line, message, confidence, symbol name, kind (variable/function/class/...)."""

    file: str
    line: int
    message: str
    confidence: int
    symbol: str
    kind: str


class FileContext(NamedTuple):
    """Cached AST-derived context for a single source file."""

    pydantic_field_lines: frozenset[int]
    enum_member_lines: frozenset[int]
    validator_lines: frozenset[int]
    typer_command_lines: frozenset[int]


class FilterResult(NamedTuple):
    """Result of applying false-positive filters to findings."""

    kept: dict[tuple[str, int, str], Finding]
    removed_count: int


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------

def _base_name(node: ast.expr) -> str:
    """Extract the simple name from a base class node (Name, Attribute, or Subscript)."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        return _base_name(node.value)
    return ""


def _has_model_config(cls_node: ast.ClassDef) -> bool:
    """Check if a class body contains a ``model_config = ...`` assignment."""
    for item in cls_node.body:
        if isinstance(item, ast.Assign):
            for target in item.targets:
                if isinstance(target, ast.Name) and target.id == "model_config":
                    return True
    return False


def _decorator_name(dec: ast.expr) -> str:
    """Extract the terminal name from a decorator (handles @name, @obj.name, @obj.name(...))."""
    if isinstance(dec, ast.Name):
        return dec.id
    if isinstance(dec, ast.Attribute):
        return dec.attr
    if isinstance(dec, ast.Call):
        return _decorator_name(dec.func)
    return ""


def _check_decorated_func(
    func_node: ast.FunctionDef | ast.AsyncFunctionDef,
    validator_lines: set[int],
    command_lines: set[int],
) -> None:
    """Check a function's decorators and add relevant line numbers.

    Adds both the def line and all decorator lines, since Vulture may report
    either the decorator line or the def line depending on the Python version.
    """
    for dec in func_node.decorator_list:
        name = _decorator_name(dec)
        if name in _VALIDATOR_DECORATORS:
            validator_lines.add(func_node.lineno)
            for d in func_node.decorator_list:
                validator_lines.add(d.lineno)
            return
        if name in _COMMAND_DECORATORS:
            command_lines.add(func_node.lineno)
            for d in func_node.decorator_list:
                command_lines.add(d.lineno)
            return


def _build_file_context(file_path: str) -> FileContext:
    """Parse a source file and extract line-number sets for AST-based false-positive detection."""
    pydantic_lines: set[int] = set()
    enum_lines: set[int] = set()
    validator_lines: set[int] = set()
    command_lines: set[int] = set()

    try:
        source = Path(file_path).read_text(encoding="utf-8")
        tree = ast.parse(source, filename=file_path)
    except (OSError, SyntaxError):
        return FileContext(frozenset(), frozenset(), frozenset(), frozenset())

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            base_names = {_base_name(b) for b in node.bases}
            is_pydantic = bool(base_names & _PYDANTIC_BASES) or _has_model_config(node)
            is_enum = bool(base_names & _ENUM_BASES)

            for item in node.body:
                if is_pydantic and isinstance(item, ast.AnnAssign):
                    pydantic_lines.add(item.lineno)
                if is_enum and isinstance(item, ast.Assign):
                    enum_lines.add(item.lineno)
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    _check_decorated_func(item, validator_lines, command_lines)

        # Top-level function defs for Typer commands (not inside a class)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _check_decorated_func(node, validator_lines, command_lines)

    return FileContext(
        pydantic_field_lines=frozenset(pydantic_lines),
        enum_member_lines=frozenset(enum_lines),
        validator_lines=frozenset(validator_lines),
        typer_command_lines=frozenset(command_lines),
    )


# ---------------------------------------------------------------------------
# Filter functions
# ---------------------------------------------------------------------------

def _is_false_positive_quick(finding: Finding) -> bool:
    """Check name/path-based false-positive patterns (no file I/O)."""
    if finding.symbol in _SKIP_SYMBOLS:
        return True
    if finding.symbol in _SKIP_DUNDER_NAMES:
        return True
    if finding.kind in ("function", "method"):
        for prefix in _SKIP_SYMBOL_PREFIXES:
            if finding.symbol.startswith(prefix):
                return True
    normalized_path = finding.file.replace("\\", "/")
    for segment in _SKIP_PATH_SEGMENTS:
        if segment.replace("\\", "/") in normalized_path:
            return True
    return False


def _is_false_positive_ast(finding: Finding, ctx: FileContext) -> bool:
    """Check AST-based false-positive patterns using cached file context."""
    if finding.kind == "variable" and finding.line in ctx.enum_member_lines:
        return True
    if finding.kind == "variable" and finding.line in ctx.pydantic_field_lines:
        return True
    if finding.kind in ("function", "method") and finding.line in ctx.validator_lines:
        return True
    if finding.kind == "function" and finding.line in ctx.typer_command_lines:
        return True
    return False


def _apply_filters(
    findings: dict[tuple[str, int, str], Finding],
    file_context_cache: dict[str, FileContext],
) -> FilterResult:
    """Apply false-positive filters to findings. Returns kept findings and removed count."""
    kept: dict[tuple[str, int, str], Finding] = {}
    removed_count = 0

    for key, finding in findings.items():
        if _is_false_positive_quick(finding):
            removed_count += 1
            continue

        resolved_path = str(Path(finding.file).resolve())
        if resolved_path not in file_context_cache:
            file_context_cache[resolved_path] = _build_file_context(resolved_path)
        ctx = file_context_cache[resolved_path]

        if _is_false_positive_ast(finding, ctx):
            removed_count += 1
            continue

        kept[key] = finding

    return FilterResult(kept=kept, removed_count=removed_count)


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def _discover_packages(workspace_root: Path) -> dict[str, Path]:
    """Return dict project_name -> project root for each datrix-* dir with pyproject.toml."""
    result: dict[str, Path] = {}
    if not workspace_root.is_dir():
        return result
    for child in workspace_root.iterdir():
        if not child.is_dir() or not child.name.startswith(DATRIX_PREFIX):
            continue
        if child.name == "datrix":
            continue
        pyproject = child / "pyproject.toml"
        if pyproject.is_file():
            result[child.name] = child.resolve()
    return dict(sorted(result.items()))


def _parse_line(line: str) -> Finding | None:
    """Parse one line of Vulture stdout. Returns None if not a finding line."""
    line = line.rstrip()
    m = _LINE_RE.match(line)
    if not m:
        return None
    path_str, line_str, message, conf_str = m.groups()
    sym_m = _SYMBOL_RE.search(message)
    symbol = sym_m.group(1) if sym_m else message
    kind_m = _KIND_RE.match(message)
    kind = kind_m.group(1) if kind_m else "other"
    return Finding(
        file=path_str,
        line=int(line_str),
        message=message,
        confidence=int(conf_str),
        symbol=symbol,
        kind=kind,
    )


def _normalize_key(f: Finding, workspace_root: Path) -> tuple[str, int, str]:
    """Stable key for matching findings across passes: (normalized_path, line, symbol)."""
    try:
        resolved = Path(f.file).resolve()
        norm = str(resolved)
    except (OSError, RuntimeError):
        norm = str(Path(f.file))
    return (norm, f.line, f.symbol)


def _is_under_src(path_str: str, project_roots: list[Path]) -> bool:
    """True if path is under any project's src/ directory."""
    try:
        p = Path(path_str).resolve()
        for root in project_roots:
            src_dir = root / "src"
            try:
                p.relative_to(src_dir)
                return True
            except ValueError:
                continue
    except (OSError, RuntimeError):
        pass
    return False


def _project_for_path(path_str: str, packages: dict[str, Path]) -> str | None:
    """Return project name if path is under that project's src/, else None."""
    try:
        p = Path(path_str).resolve()
        for name, root in packages.items():
            src_dir = root / "src"
            try:
                p.relative_to(src_dir)
                return name
            except ValueError:
                continue
    except (OSError, RuntimeError):
        pass
    return None


def _run_vulture(
    paths: list[str],
    exclude_pattern: str,
    min_confidence: int,
    cwd: str,
) -> tuple[list[Finding], int]:
    """Run Vulture with given paths and exclude; return (parsed findings, returncode)."""
    cmd = [
        sys.executable,
        "-m",
        "vulture",
        "--min-confidence",
        str(max(60, min(100, min_confidence))),
        "--exclude",
        exclude_pattern,
        *paths,
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    findings: list[Finding] = []
    for line in (result.stdout or "").splitlines():
        f = _parse_line(line)
        if f:
            findings.append(f)
    return findings, result.returncode


def _collect_paths(
    packages: dict[str, Path],
    include_tests: bool,
) -> list[str]:
    """Build list of paths to scan: src (and optionally tests) plus whitelists."""
    paths: list[str] = []
    for _name, root in packages.items():
        src = root / "src"
        if src.is_dir():
            paths.append(str(src))
        if include_tests:
            tests = root / "tests"
            if tests.is_dir():
                paths.append(str(tests))
        whitelist = root / "vulture_whitelist.py"
        if whitelist.is_file():
            paths.append(str(whitelist))
    return paths


def run_report(
    workspace_root: Path,
    project_names: list[str],
    min_confidence: int,
    output_format: str,
    verbose: bool,
    raw: bool = False,
) -> int:
    """Run two-pass Vulture, classify, and print report. Returns 0 on success."""
    packages = _discover_packages(workspace_root)
    if not packages:
        print(
            f"Error: no datrix-* packages found under {workspace_root}",
            file=sys.stderr,
        )
        return 1

    selected = [p for p in project_names if p in packages]
    missing = set(project_names) - set(packages.keys())
    if missing:
        print(
            f"Error: unknown package(s): {sorted(missing)}. Available: {sorted(packages.keys())}",
            file=sys.stderr,
        )
        return 1
    if not selected:
        print("Error: no projects selected.", file=sys.stderr)
        return 1

    packages = {k: v for k, v in packages.items() if k in selected}
    project_roots = list(packages.values())
    cwd = str(workspace_root)

    # Pass 1: src only (exclude tests)
    paths_src_only = _collect_paths(packages, include_tests=False)
    if not paths_src_only:
        print("Error: no src directories to scan.", file=sys.stderr)
        return 1
    if verbose:
        print("Pass 1 (src only)...", file=sys.stderr)
    findings_src_only, _ = _run_vulture(
        paths_src_only,
        EXCLUDE_SRC_ONLY,
        min_confidence,
        cwd,
    )
    set_a = {
        _normalize_key(f, workspace_root): f
        for f in findings_src_only
        if _is_under_src(f.file, project_roots)
    }

    # Pass 2: src + tests (exclude only __pycache__, .git)
    paths_with_tests = _collect_paths(packages, include_tests=True)
    if verbose:
        print("Pass 2 (src + tests)...", file=sys.stderr)
    findings_with_tests, _ = _run_vulture(
        paths_with_tests,
        EXCLUDE_SRC_AND_TESTS,
        min_confidence,
        cwd,
    )
    set_b = {
        _normalize_key(f, workspace_root): f
        for f in findings_with_tests
        if _is_under_src(f.file, project_roots)
    }

    # Filter false positives (unless --raw)
    total_filtered = 0
    if not raw:
        file_ctx_cache: dict[str, FileContext] = {}
        result_a = _apply_filters(set_a, file_ctx_cache)
        set_a = result_a.kept
        total_filtered += result_a.removed_count

        result_b = _apply_filters(set_b, file_ctx_cache)
        set_b = result_b.kept
        total_filtered += result_b.removed_count

        if verbose:
            print(
                f"Filtered {total_filtered} false positives "
                f"({len(file_ctx_cache)} files parsed for AST checks)",
                file=sys.stderr,
            )

    # Classify: never_referenced = in B; only_referenced_by_tests = in A but not B
    never_referenced = {k: set_b[k] for k in set_b}
    only_by_tests = {k: set_a[k] for k in set_a if k not in set_b}

    # Group by project
    by_project: dict[str, dict[str, list[Finding]]] = {
        p: {"never_referenced": [], "only_referenced_by_tests": []}
        for p in sorted(packages.keys())
    }
    for k, f in never_referenced.items():
        proj = _project_for_path(f.file, packages)
        if proj and proj in by_project:
            by_project[proj]["never_referenced"].append(f)
    for k, f in only_by_tests.items():
        proj = _project_for_path(f.file, packages)
        if proj and proj in by_project:
            by_project[proj]["only_referenced_by_tests"].append(f)

    for proj in by_project:
        for kind in ("never_referenced", "only_referenced_by_tests"):
            by_project[proj][kind].sort(key=lambda x: (x.file, x.line))

    if output_format == "json":
        out: dict[str, object] = {
            "filtered_count": total_filtered if not raw else 0,
            "projects": {
                proj: {
                    "never_referenced": [
                        {
                            "file": f.file,
                            "line": f.line,
                            "symbol": f.symbol,
                            "kind": f.kind,
                            "message": f.message,
                            "confidence": f.confidence,
                        }
                        for f in data["never_referenced"]
                    ],
                    "only_referenced_by_tests": [
                        {
                            "file": f.file,
                            "line": f.line,
                            "symbol": f.symbol,
                            "kind": f.kind,
                            "message": f.message,
                            "confidence": f.confidence,
                        }
                        for f in data["only_referenced_by_tests"]
                    ],
                }
                for proj, data in by_project.items()
            },
        }
        print(json.dumps(out, indent=2))
        return 0

    def _by_kind(findings: list[Finding]) -> dict[str, list[Finding]]:
        grouped: dict[str, list[Finding]] = {k: [] for k in KIND_ORDER}
        for f in findings:
            if f.kind in grouped:
                grouped[f.kind].append(f)
            else:
                grouped["other"].append(f)
        return grouped

    # Human-readable report, grouped by type (classes, functions, methods, then variables, etc.)
    for proj in sorted(by_project.keys()):
        data = by_project[proj]
        nr = data["never_referenced"]
        ot = data["only_referenced_by_tests"]
        if not nr and not ot:
            continue
        print(f"\n## {proj}\n")
        if nr:
            print("### Never referenced\n")
            nr_by_kind = _by_kind(nr)
            for kind in KIND_ORDER:
                items = nr_by_kind.get(kind, [])
                if not items:
                    continue
                label = KIND_LABELS.get(kind, kind.capitalize())
                print(f"#### {label}\n")
                for f in sorted(items, key=lambda x: (x.file, x.line)):
                    print(f"  {f.file}:{f.line}: {f.message} ({f.confidence}% confidence)")
                print()
        if ot:
            print("### Only referenced by tests\n")
            ot_by_kind = _by_kind(ot)
            for kind in KIND_ORDER:
                items = ot_by_kind.get(kind, [])
                if not items:
                    continue
                label = KIND_LABELS.get(kind, kind.capitalize())
                print(f"#### {label}\n")
                for f in sorted(items, key=lambda x: (x.file, x.line)):
                    print(f"  {f.file}:{f.line}: {f.message} ({f.confidence}% confidence)")
                print()

    if not raw and total_filtered > 0:
        print(f"\n---\nFiltered {total_filtered} known false positives. Use --raw to see all.")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Dead-code report: never referenced vs only referenced by tests (two-pass Vulture).",
    )
    parser.add_argument(
        "--workspace-root",
        type=Path,
        required=True,
        help="Workspace root (parent of datrix-common, datrix-language, etc.).",
    )
    parser.add_argument(
        "--projects",
        type=str,
        nargs="*",
        metavar="PKG",
        help="Project names to scan (default: all datrix-* except 'datrix').",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Scan all datrix-* projects (exclude 'datrix'). Ignored if --projects is set.",
    )
    parser.add_argument(
        "--min-confidence",
        type=int,
        default=DEFAULT_MIN_CONFIDENCE,
        metavar="N",
        help=f"Vulture min confidence 60-100 (default: {DEFAULT_MIN_CONFIDENCE}).",
    )
    parser.add_argument(
        "--output",
        choices=("text", "json"),
        default="text",
        help="Report format: text or json (default: text).",
    )
    parser.add_argument("--verbose", action="store_true", help="Verbose progress to stderr.")
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Disable false-positive filters (show all Vulture findings).",
    )

    args = parser.parse_args()
    workspace_root = args.workspace_root.resolve()
    if not workspace_root.is_dir():
        print(f"Error: workspace root is not a directory: {workspace_root}", file=sys.stderr)
        return 1

    if args.projects:
        project_names = args.projects
    elif args.all:
        packages = _discover_packages(workspace_root)
        project_names = sorted(packages.keys())
    else:
        # Default: the 11 packages from the plan
        project_names = [
            "datrix-cli",
            "datrix-common",
            "datrix-codegen-aws",
            "datrix-codegen-azure",
            "datrix-codegen-component",
            "datrix-codegen-docker",
            "datrix-codegen-k8s",
            "datrix-codegen-python",
            "datrix-codegen-sql",
            "datrix-codegen-typescript",
            "datrix-language",
        ]

    return run_report(
        workspace_root,
        project_names,
        args.min_confidence,
        args.output,
        args.verbose,
        raw=args.raw,
    )


if __name__ == "__main__":
    sys.exit(main())
