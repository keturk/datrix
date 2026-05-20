#!/usr/bin/env python3
"""Lint and format ConfigDSL (.dcfg) files.

By default, this script discovers .dcfg files in provided paths and rewrites them
in a normalized style. Use --check for CI-style validation without file writes.
"""

from __future__ import annotations

import argparse
import io
import os
import signal
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if sys.platform == "win32" and __name__ == "__main__":
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

library_dir = Path(__file__).parent.parent
if library_dir.exists() and str(library_dir) not in sys.path:
    sys.path.insert(0, str(library_dir))

if TYPE_CHECKING:
    from datrix_common.config.dcfg import ast_nodes as ast


def _sigint_handler(_signum: int, _frame: object) -> None:
    """Exit with standard SIGINT code on Ctrl-C."""
    sys.exit(130)


def _get_datrix_root() -> Path:
    """Find the monorepo root (directory containing datrix + datrix-common)."""
    candidates = [Path.cwd(), *Path(__file__).resolve().parents]
    for candidate in candidates:
        if (candidate / "datrix").is_dir() and (candidate / "datrix-common").is_dir():
            return candidate
    raise FileNotFoundError("Could not find Datrix root directory")


_SKIP_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        "build",
        "dist",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "htmlcov",
    }
)


@dataclass
class LintIssue:
    line: int
    col: int
    message: str


def _add_datrix_common_to_path(datrix_root: Path) -> None:
    common_src = datrix_root / "datrix-common" / "src"
    if common_src.exists() and str(common_src) not in sys.path:
        sys.path.insert(0, str(common_src))


def _discover_dcfg_files(path: Path) -> list[Path]:
    files: list[Path] = []
    if path.is_file():
        if path.suffix == ".dcfg":
            files.append(path)
        return files
    if not path.is_dir():
        return files

    for dir_path, dirnames, filenames in os.walk(path, followlinks=False):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.endswith(".egg-info")]
        for name in filenames:
            if name.endswith(".dcfg"):
                files.append(Path(dir_path) / name)
    return sorted(files)


def _contains_multiple_statements_on_line(line: str) -> bool:
    in_string = False
    escaped = False
    i = 0
    semicolon_seen = False

    while i < len(line):
        ch = line[i]
        nxt = line[i + 1] if i + 1 < len(line) else ""

        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            i += 1
            continue

        if ch == '"':
            in_string = True
            i += 1
            continue

        if ch == "/" and nxt == "/":
            return False

        if ch == ";":
            semicolon_seen = True
            j = i + 1
            while j < len(line) and line[j].isspace():
                j += 1
            if j < len(line) and not (line[j] == "/" and j + 1 < len(line) and line[j + 1] == "/"):
                return True
            i = j
            continue

        i += 1

    return semicolon_seen and False


def _lint_source_text(source: str) -> list[LintIssue]:
    issues: list[LintIssue] = []
    for index, raw_line in enumerate(source.splitlines(), start=1):
        line = raw_line.rstrip("\r")
        if "\t" in line:
            issues.append(LintIssue(index, line.index("\t") + 1, "Tab character found; use spaces"))
        if line.rstrip(" ") != line:
            issues.append(
                LintIssue(index, len(line.rstrip(" ")) + 1, "Trailing whitespace found")
            )
        if _contains_multiple_statements_on_line(line):
            issues.append(
                LintIssue(index, 1, "Multiple statements on one line; prefer one statement per line")
            )
    return issues


def _escape_string(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


def _render_expr(expr: "ast.Expression") -> str:
    from datrix_common.config.dcfg import ast_nodes as ast

    if isinstance(expr, ast.Identifier):
        return expr.name
    if isinstance(expr, ast.IntLiteral):
        return str(expr.value)
    if isinstance(expr, ast.FloatLiteral):
        return str(expr.value)
    if isinstance(expr, ast.NullLiteral):
        return "null"
    if isinstance(expr, ast.BoolLiteral):
        return "true" if expr.value else "false"
    if isinstance(expr, ast.StringLiteral):
        return _escape_string(expr.value)
    if isinstance(expr, ast.InterpolationExpr):
        return "${" + expr.path + "}"
    if isinstance(expr, ast.InterpolatedString):
        parts: list[str] = []
        for part in expr.parts:
            if isinstance(part, ast.StringLiteral):
                parts.append(part.value)
            else:
                parts.append("${" + part.path + "}")
        return _escape_string("".join(parts))
    if isinstance(expr, ast.DurationLiteral):
        return expr.original_text
    if isinstance(expr, ast.ListLiteral):
        return "[" + ", ".join(_render_expr(v) for v in expr.elements) + "]"
    if isinstance(expr, ast.ObjectLiteral):
        rendered_fields = ", ".join(f"{k}: {_render_expr(v)}" for k, v in expr.fields)
        return "{" + rendered_fields + "}"
    if isinstance(expr, ast.EnvExpr):
        if expr.default is None:
            return f"env({_render_expr(expr.name)})"
        return f"env({_render_expr(expr.name)}, default: {_render_expr(expr.default)})"
    if isinstance(expr, ast.PerProfileExpr):
        parts = [f"{k}: {_render_expr(v)}" for k, v in expr.values.items()]
        if expr.default is not None:
            parts.append(f"default: {_render_expr(expr.default)}")
        return "perProfile(" + ", ".join(parts) + ")"
    if isinstance(expr, ast.TemplateCallExpr):
        args: list[str] = []
        args.extend(_render_expr(v) for v in expr.positional_args)
        args.extend(f"{k}: {_render_expr(v)}" for k, v in expr.named_args.items())
        return f"{expr.template_name}(" + ", ".join(args) + ")"

    raise TypeError(f"Unsupported expression type: {type(expr).__name__}")


def _render_field_assignment(node: "ast.FieldAssignment", indent: int) -> str:
    path = ".".join(node.path)
    return f"{'  ' * indent}{path} = {_render_expr(node.value)};"


def _render_block_assignment(node: "ast.BlockAssignment", indent: int) -> str:
    header = f"{'  ' * indent}{node.name} {{"
    body = _render_body(node.body, indent + 1)
    footer = f"{'  ' * indent}}}"
    return "\n".join([header, *body, footer])


def _render_named_block(node: "ast.NamedBlockDecl", indent: int) -> str:
    prefix = "  " * indent
    if node.template_call is not None:
        return f"{prefix}{node.section} {node.name} from {_render_expr(node.template_call)};"

    header = f"{prefix}{node.section} {node.name} {{"
    body = _render_body(node.body, indent + 1)
    footer = f"{prefix}}}"
    return "\n".join([header, *body, footer])


def _render_replace(node: "ast.ReplaceDecl", indent: int) -> str:
    from datrix_common.config.dcfg import ast_nodes as ast

    if isinstance(node.target, ast.NamedBlockDecl):
        if node.target.template_call is not None:
            return (
                f"{'  ' * indent}replace {node.target.section} {node.target.name} "
                f"from {_render_expr(node.target.template_call)};"
            )
        header = f"{'  ' * indent}replace {node.target.section} {node.target.name} {{"
        body = _render_body(node.target.body, indent + 1)
        footer = f"{'  ' * indent}}}"
        return "\n".join([header, *body, footer])

    if isinstance(node.target, ast.BlockAssignment):
        header = f"{'  ' * indent}replace {node.target.name} {{"
        body = _render_body(node.target.body, indent + 1)
        footer = f"{'  ' * indent}}}"
        return "\n".join([header, *body, footer])

    raise TypeError(f"Unsupported replace target: {type(node.target).__name__}")


def _render_body(
    body: list["ast.FieldAssignment | ast.BlockAssignment | ast.NamedBlockDecl | ast.ReplaceDecl"],
    indent: int,
) -> list[str]:
    from datrix_common.config.dcfg import ast_nodes as ast

    rendered: list[str] = []
    for item in body:
        if isinstance(item, ast.FieldAssignment):
            rendered.append(_render_field_assignment(item, indent))
        elif isinstance(item, ast.BlockAssignment):
            rendered.append(_render_block_assignment(item, indent))
        elif isinstance(item, ast.NamedBlockDecl):
            rendered.append(_render_named_block(item, indent))
        elif isinstance(item, ast.ReplaceDecl):
            rendered.append(_render_replace(item, indent))
        else:
            raise TypeError(f"Unsupported body node type: {type(item).__name__}")
    return rendered


def _render_template_decl(template: "ast.TemplateDecl", indent: int) -> str:
    params: list[str] = []
    for param in template.params:
        if param.default is None:
            params.append(param.name)
        else:
            params.append(f"{param.name} = {_render_expr(param.default)}")
    header = f"{'  ' * indent}template {template.name}(" + ", ".join(params) + ") {"
    body = _render_body(template.body, indent + 1)
    footer = f"{'  ' * indent}}}"
    return "\n".join([header, *body, footer])


def _render_profile(profile: "ast.ProfileBlock", *, is_base: bool, indent: int) -> str:
    prefix = "  " * indent
    if is_base:
        header = f"{prefix}base {{"
    else:
        header = f"{prefix}profile {profile.name}"
        if profile.short_alias is not None:
            header += f" as {_escape_string(profile.short_alias)}"
        if profile.extends is not None:
            header += f" extends {profile.extends}"
        header += " {"

    lines = [header]

    for alias in profile.aliases:
        lines.append(f"{'  ' * (indent + 1)}alias {alias.name} = {_escape_string(alias.value)};")

    if profile.aliases and profile.body:
        lines.append("")

    lines.extend(_render_body(profile.body, indent + 1))
    lines.append(f"{prefix}}}")
    return "\n".join(lines)


def format_dcfg(source: str, source_path: Path) -> tuple[str, list[LintIssue], str | None]:
    """Return formatted content + lint issues + optional parse error."""
    from datrix_common.config.dcfg.parser import ConfigDSLParseError, parse_dcfg

    issues = _lint_source_text(source)

    try:
        ast = parse_dcfg(source, str(source_path))
    except ConfigDSLParseError as exc:
        message = f"Syntax error: {exc}"
        return source, issues, message

    lines: list[str] = [f"config {ast.kind} {ast.owner} {{"]

    for decl in ast.imports:
        lines.append(f"  import {_escape_string(decl.path)};")

    if ast.imports and (ast.templates or ast.base is not None or ast.profiles):
        lines.append("")

    for index, template in enumerate(ast.templates):
        lines.append(_render_template_decl(template, 1))
        if index != len(ast.templates) - 1:
            lines.append("")

    if ast.templates and (ast.base is not None or ast.profiles):
        lines.append("")

    if ast.base is not None:
        lines.append(_render_profile(ast.base, is_base=True, indent=1))
        if ast.profiles:
            lines.append("")

    for index, profile in enumerate(ast.profiles):
        lines.append(_render_profile(profile, is_base=False, indent=1))
        if index != len(ast.profiles) - 1:
            lines.append("")

    lines.append("}")
    formatted = "\n".join(lines).rstrip() + "\n"
    return formatted, issues, None


class ConfigLinter:
    """Find, lint, and format .dcfg files."""

    def __init__(self, check_only: bool, debug: bool) -> None:
        self.check_only = check_only
        self.debug = debug
        self.files_seen = 0
        self.files_formatted = 0
        self.files_with_syntax_errors = 0
        self.total_issues = 0
        self._would_change = 0

    def _debug(self, message: str) -> None:
        if self.debug:
            print(f"[DEBUG] {message}", file=sys.stderr)

    def process_file(self, file_path: Path) -> None:
        self.files_seen += 1
        self._debug(f"Processing {file_path}")

        try:
            original = file_path.read_text(encoding="utf-8")
        except Exception as exc:  # pragma: no cover - IO failures are environment-specific
            self.files_with_syntax_errors += 1
            print(f"ERROR {file_path}: Failed to read file: {exc}")
            return

        formatted, issues, parse_error = format_dcfg(original, file_path)
        self.total_issues += len(issues)

        for issue in issues:
            print(f"WARN  {file_path}:{issue.line}:{issue.col} {issue.message}")

        if parse_error is not None:
            self.files_with_syntax_errors += 1
            print(f"ERROR {file_path}: {parse_error}")
            return

        if formatted != original:
            if self.check_only:
                self._would_change += 1
                print(f"CHECK {file_path}: formatting needed")
            else:
                file_path.write_text(formatted, encoding="utf-8")
                self.files_formatted += 1
                print(f"FIXED {file_path}")

    def report(self) -> int:
        print()
        print("Config linter summary")
        print("---------------------")
        print(f"Files scanned:        {self.files_seen}")
        print(f"Files formatted:      {self.files_formatted}")
        print(f"Format needed:        {self._would_change}")
        print(f"Syntax errors:        {self.files_with_syntax_errors}")
        print(f"Style warnings:       {self.total_issues}")

        if self.files_with_syntax_errors > 0:
            return 1
        if self.check_only and (self._would_change > 0 or self.total_issues > 0):
            return 1
        return 0


def _default_scan_paths() -> list[Path]:
    datrix_root = _get_datrix_root()
    return sorted(d for d in datrix_root.iterdir() if d.is_dir() and d.name.startswith("datrix"))


def main() -> int:
    signal.signal(signal.SIGINT, _sigint_handler)

    parser = argparse.ArgumentParser(
        description="Lint and format .dcfg files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="File or directory paths to scan (default: all datrix* repos)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check mode: report issues/needed formatting, do not write files",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    try:
        datrix_root = _get_datrix_root()
    except FileNotFoundError:
        print("ERROR: Could not find Datrix root directory", file=sys.stderr)
        return 1

    _add_datrix_common_to_path(datrix_root)

    input_paths = [Path(p) for p in args.paths] if args.paths else _default_scan_paths()
    discovered: list[Path] = []

    print("Discovering .dcfg files...", flush=True)
    for p in input_paths:
        if not p.exists():
            print(f"WARN  Path does not exist: {p}")
            continue
        found = _discover_dcfg_files(p)
        if found:
            print(f"  {p}: {len(found)} files", flush=True)
        discovered.extend(found)

    unique_files = sorted(set(discovered))
    if not unique_files:
        print("No .dcfg files found.")
        return 0

    print(f"Found {len(unique_files)} .dcfg file(s).", flush=True)
    print()

    linter = ConfigLinter(check_only=args.check, debug=args.debug)
    for file_path in unique_files:
        linter.process_file(file_path)

    return linter.report()


if __name__ == "__main__":
    sys.exit(main())

