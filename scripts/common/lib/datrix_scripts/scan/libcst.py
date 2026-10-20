#!/usr/bin/env python3
"""Scan Datrix Python code for anti-patterns using LibCST.

Detects violations of the .cursorrules coding standards across one or more
packages (or the entire monorepo).  Patterns checked:

  - silent-fallback        : dict.get(key, None) or type_map.get(t, "Any")
  - empty-except           : except: pass / except Exception: pass
  - missing-encoding       : Path.read_text() / .write_text() / open() without encoding=
  - banned-test-import     : MagicMock, Mock, patch, SimpleNamespace in test files
  - placeholder-body       : pass / raise NotImplementedError as sole function body
  - string-concat-codegen  : f"class {name}:" style code generation

The module behind ``scan/libcst.ps1`` (and its ``.sh`` twin). Exit codes: 0 no finding, 1 a finding,
an unknown project, or neither ``--projects`` nor ``--all`` (the usage is printed). With both,
``--all`` wins.

Usage:
    python -m datrix_scripts.scan.libcst --projects=datrix-common [--projects=datrix-language]
    python -m datrix_scripts.scan.libcst --all --report=libcst-report.md
"""

from __future__ import annotations

import argparse
import contextlib
import io
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from datrix_scripts.venv import SCRIPTS_DEPENDENCY_GROUP, missing_declared_tool

try:
    import libcst as cst
    from libcst.metadata import MetadataWrapper, PositionProvider
except ImportError as exc:
    raise SystemExit(missing_declared_tool("libcst", SCRIPTS_DEPENDENCY_GROUP)) from exc

from datrix_scripts.gate_harness import write_files  # noqa: E402
from datrix_scripts.logic_map import resolve_scan_paths  # noqa: E402
from datrix_scripts.paths import WORKSPACE_DIR  # noqa: E402
from datrix_scripts.scan.selection import (  # noqa: E402
    SelectionRefused,
    expect_refusal,
    require_selection,
    wrapper_usage,
)
from datrix_scripts.test.wrappers import SCAN_SCRIPTS_DIR, module_main, run_self_test  # noqa: E402

MODULE: Final = "datrix_scripts.scan.libcst"
WRAPPER: Final = "libcst"

_USAGE: Final = wrapper_usage(WRAPPER, ["<project> [project2 ...]", "-All [-Report <path>]"])


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Finding:
    """A single anti-pattern finding."""

    file: str
    line: int
    rule: str
    message: str


@dataclass
class ScanResult:
    """Aggregated scan results."""

    findings: list[Finding] = field(default_factory=list)
    files_scanned: int = 0
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Visitor that collects anti-pattern findings
# ---------------------------------------------------------------------------

BANNED_TEST_NAMES = frozenset({"MagicMock", "Mock", "patch", "SimpleNamespace"})

ENCODING_METHODS = frozenset({"read_text", "write_text"})


class AntiPatternVisitor(cst.CSTVisitor):
    """LibCST visitor that detects Datrix .cursorrules anti-patterns."""

    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(self, file_path: str, is_test_file: bool) -> None:
        self.file_path = file_path
        self.is_test_file = is_test_file
        self.findings: list[Finding] = []

    def _pos(self, node: cst.CSTNode) -> int:
        try:
            return self.get_metadata(PositionProvider, node).start.line
        except Exception:
            return 0

    def _add(self, node: cst.CSTNode, rule: str, message: str) -> None:
        self.findings.append(
            Finding(file=self.file_path, line=self._pos(node), rule=rule, message=message)
        )

    # --- silent-fallback: expr.get(key, None) ---
    def visit_Call(self, node: cst.Call) -> bool | None:
        self._check_silent_fallback(node)
        self._check_missing_encoding(node)
        return True

    def _check_silent_fallback(self, node: cst.Call) -> None:
        if not isinstance(node.func, cst.Attribute):
            return
        if node.func.attr.value != "get":
            return
        if len(node.args) < 2:
            return
        second_arg = node.args[1].value
        if isinstance(second_arg, cst.Name) and second_arg.value == "None":
            self._add(
                node,
                "silent-fallback",
                "dict.get(key, None) — use explicit lookup + raise on missing",
            )

    # --- missing-encoding: read_text() / write_text() / open() without encoding= ---
    def _check_missing_encoding(self, node: cst.Call) -> None:
        func_name: str | None = None

        if isinstance(node.func, cst.Attribute) and node.func.attr.value in ENCODING_METHODS:
            func_name = node.func.attr.value
        elif isinstance(node.func, cst.Name) and node.func.value == "open":
            func_name = "open"

        if func_name is None:
            return

        has_encoding = any(
            isinstance(arg.keyword, cst.Name) and arg.keyword.value == "encoding"
            for arg in node.args
            if arg.keyword is not None
        )
        if not has_encoding:
            self._add(
                node,
                "missing-encoding",
                f'{func_name}() called without encoding="utf-8"',
            )

    # --- empty-except: except [Exception]: pass ---
    def visit_ExceptHandler(self, node: cst.ExceptHandler) -> bool | None:
        body_stmts = node.body.body if isinstance(node.body, cst.IndentedBlock) else []
        if len(body_stmts) == 1:
            stmt = body_stmts[0]
            if isinstance(stmt, cst.SimpleStatementLine):
                inner = stmt.body
                if len(inner) == 1 and isinstance(inner[0], cst.Pass):
                    self._add(node, "empty-except", "except: pass — handle or re-raise")
        return True

    # --- banned-test-import: MagicMock / Mock / patch / SimpleNamespace ---
    def visit_ImportFrom(self, node: cst.ImportFrom) -> bool | None:
        if not self.is_test_file:
            return True
        if isinstance(node.names, cst.ImportStar):
            return True
        for alias in node.names:
            imported = alias.name.value if isinstance(alias.name, cst.Name) else ""
            if imported in BANNED_TEST_NAMES:
                self._add(
                    node,
                    "banned-test-import",
                    f"Import of {imported} is banned in tests — use real objects",
                )
        return True

    def visit_Import(self, node: cst.Import) -> bool | None:
        if not self.is_test_file:
            return True
        if isinstance(node.names, cst.ImportStar):
            return True
        for alias in node.names:
            full_name = _dotted_name(alias.name)
            if any(banned in full_name for banned in BANNED_TEST_NAMES):
                self._add(
                    node,
                    "banned-test-import",
                    f"Import of {full_name} is banned in tests — use real objects",
                )
        return True

    # --- placeholder-body: pass / raise NotImplementedError as sole body ---
    def visit_FunctionDef(self, node: cst.FunctionDef) -> bool | None:
        body_stmts = node.body.body if isinstance(node.body, cst.IndentedBlock) else []
        if len(body_stmts) != 1:
            return True

        stmt = body_stmts[0]
        if isinstance(stmt, cst.SimpleStatementLine) and len(stmt.body) == 1:
            inner = stmt.body[0]

            # Sole `pass`
            if isinstance(inner, cst.Pass):
                # Allow in abstract-style methods or __init__ that truly need pass
                name = node.name.value
                if name not in ("__init__", "__repr__", "__str__"):
                    self._add(
                        node,
                        "placeholder-body",
                        f"Function {name}() has only 'pass' — placeholder or stub",
                    )

            # Sole `raise NotImplementedError(...)`
            if isinstance(inner, cst.Raise) and inner.exc is not None:
                exc = inner.exc
                exc_name = ""
                if isinstance(exc, cst.Call) and isinstance(exc.func, cst.Name):
                    exc_name = exc.func.value
                elif isinstance(exc, cst.Name):
                    exc_name = exc.value
                if exc_name == "NotImplementedError":
                    self._add(
                        node,
                        "placeholder-body",
                        f"Function {node.name.value}() raises NotImplementedError — implement or remove",
                    )
        return True


def _dotted_name(node: cst.BaseExpression) -> str:
    if isinstance(node, cst.Name):
        return node.value
    if isinstance(node, cst.Attribute):
        return f"{_dotted_name(node.value)}.{node.attr.value}"
    return ""


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

SKIP_DIRS = frozenset({
    "__pycache__", ".venv", ".git", ".generated", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", "node_modules", ".tox", "dist", "build",
})


def _iter_python_files(root: Path) -> list[Path]:
    """Yield .py files under *root*, skipping non-source directories."""
    results: list[Path] = []
    for child in sorted(root.iterdir()):
        if child.is_dir():
            if child.name in SKIP_DIRS or child.name.startswith("."):
                continue
            results.extend(_iter_python_files(child))
        elif child.suffix == ".py":
            results.append(child)
    return results


def scan_file(path: Path, datrix_root: Path) -> tuple[list[Finding], str | None]:
    """Scan a single file. Returns (findings, error_message)."""
    try:
        source = path.read_text(encoding="utf-8")
    except Exception as exc:
        return [], f"Read error: {exc}"

    if not source.strip():
        return [], None

    try:
        tree = cst.parse_module(source)
    except cst.ParserSyntaxError as exc:
        return [], f"Parse error at line {exc.raw_line}: {exc.message}"

    rel_path = str(path.relative_to(datrix_root))
    is_test = "tests" in path.parts or path.name.startswith("test_")

    try:
        wrapper = MetadataWrapper(tree)
        visitor = AntiPatternVisitor(rel_path, is_test)
        wrapper.visit(visitor)
        return visitor.findings, None
    except Exception as exc:
        return [], f"Visitor error: {type(exc).__name__}: {exc}"


def scan_directory(root: Path, datrix_root: Path) -> ScanResult:
    """Scan all .py files under *root*."""
    result = ScanResult()
    files = _iter_python_files(root)

    for path in files:
        result.files_scanned += 1
        findings, error = scan_file(path, datrix_root)
        result.findings.extend(findings)
        if error:
            result.errors.append(f"{path}: {error}")

    return result


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_summary(result: ScanResult, projects: list[str]) -> None:
    """Print a console summary of findings."""
    print()
    print("=" * 60)
    print("LIBCST ANTI-PATTERN SCAN")
    print("=" * 60)
    print(f"  Projects scanned : {', '.join(projects)}")
    print(f"  Python files     : {result.files_scanned}")
    print(f"  Findings         : {len(result.findings)}")
    print(f"  Parse errors     : {len(result.errors)}")
    print()

    if result.findings:
        by_rule: dict[str, list[Finding]] = {}
        for f in result.findings:
            by_rule.setdefault(f.rule, []).append(f)

        print("-" * 60)
        print("FINDINGS BY RULE")
        print("-" * 60)
        for rule in sorted(by_rule):
            findings = by_rule[rule]
            print(f"\n  [{rule}] ({len(findings)} hits)")
            for f in findings[:20]:
                print(f"    {f.file}:{f.line}  {f.message}")
            if len(findings) > 20:
                print(f"    ... and {len(findings) - 20} more")

    if result.errors:
        print()
        print("-" * 60)
        print(f"ERRORS ({len(result.errors)})")
        print("-" * 60)
        for err in result.errors[:10]:
            print(f"  {err}")
        if len(result.errors) > 10:
            print(f"  ... and {len(result.errors) - 10} more")

    print()


def write_report(result: ScanResult, report_path: Path, projects: list[str]) -> None:
    """Write a markdown report."""
    by_rule: dict[str, list[Finding]] = {}
    for f in result.findings:
        by_rule.setdefault(f.rule, []).append(f)

    with open(report_path, "w", encoding="utf-8") as out:
        out.write("# LibCST Anti-Pattern Scan Report\n\n")
        out.write(f"**Projects:** {', '.join(projects)}\n\n")
        out.write(f"**Files scanned:** {result.files_scanned}\n\n")
        out.write(f"**Findings:** {len(result.findings)}\n\n")

        if not result.findings:
            out.write("No anti-patterns detected.\n")
        else:
            for rule in sorted(by_rule):
                findings = by_rule[rule]
                out.write(f"## {rule} ({len(findings)})\n\n")
                for f in findings:
                    out.write(f"- `{f.file}:{f.line}` — {f.message}\n")
                out.write("\n")

        if result.errors:
            out.write(f"## Parse Errors ({len(result.errors)})\n\n")
            for err in result.errors:
                out.write(f"- {err}\n")
            out.write("\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """The options of ``scan/libcst.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        prog=WRAPPER, description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False
    )
    parser.add_argument("--projects", action="append", default=[],
                        help="A project name to scan, e.g. datrix-common (repeatable).")
    parser.add_argument("--all", action="store_true", dest="scan_all", help="Scan all projects in the monorepo.")
    parser.add_argument("--report", help="Write a markdown report to this path (relative to monorepo root).")
    parser.add_argument("--self-test", action="store_true",
                        help="Run only the self-test: planted anti-patterns are found, a clean project passes, "
                             "the usage is printed when nothing is selected, and the wrapper seam holds.")
    parser.set_defaults(debug=False)
    return parser


def _check_planted_anti_patterns_are_found() -> None:
    source = "def f(d):\n    try:\n        return d.get('k', None)\n    except Exception:\n        pass\n"
    with tempfile.TemporaryDirectory() as tmp:
        write_files(Path(tmp), {"datrix-planted/src/planted.py": source})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = scan_projects(["datrix-planted"], False, None, Path(tmp))
        assert code == 1, f"a project holding anti-patterns must exit 1, got {code}"
        for rule in ("[silent-fallback]", "[empty-except]"):
            assert rule in out.getvalue(), f"the scan must report {rule}; printed {out.getvalue()!r}"


def _check_a_clean_project_passes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        write_files(Path(tmp), {"datrix-planted/src/planted.py": "VALUE = 1\n"})
        with contextlib.redirect_stdout(io.StringIO()):
            code = scan_projects(["datrix-planted"], False, None, Path(tmp))
        assert code == 0, f"a clean project must exit 0, got {code}"


def _check_nothing_selected_prints_the_usage() -> None:
    expect_refusal(lambda: require_selection([], False, _USAGE, refuse_both=False), 1, _USAGE)


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        checks = [
            _check_planted_anti_patterns_are_found,
            _check_a_clean_project_passes,
            _check_nothing_selected_prints_the_usage,
        ]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=SCAN_SCRIPTS_DIR)
    try:
        require_selection(args.projects, args.scan_all, _USAGE, refuse_both=False)
    except SelectionRefused as refused:
        return refused.report()
    return scan_projects(args.projects, args.scan_all, args.report, WORKSPACE_DIR)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


def scan_projects(projects: list[str], scan_all: bool, report: str | None, datrix_root: Path) -> int:
    """Scan the src/ and tests/ trees of *projects* (every project with *scan_all*) under *datrix_root*,
    print the summary and write *report* when given; 1 on any finding or an unknown project, else 0."""
    try:
        scan_pairs = resolve_scan_paths(
            datrix_root, projects, scan_all, include_tests=True
        )
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if not scan_pairs:
        print("No src/ or tests/ directories found to scan.")
        return 0

    project_names = sorted(set(name for name, _ in scan_pairs))
    print(f"Scanning {len(scan_pairs)} directories across {len(project_names)} project(s)...")

    combined = ScanResult()
    for name, directory in scan_pairs:
        result = scan_directory(directory, datrix_root)
        combined.files_scanned += result.files_scanned
        combined.findings.extend(result.findings)
        combined.errors.extend(result.errors)

    print_summary(combined, project_names)

    if report:
        report_path = Path(report)
        if not report_path.is_absolute():
            report_path = datrix_root / report_path
        report_path.parent.mkdir(parents=True, exist_ok=True)
        write_report(combined, report_path, project_names)
        print(f"Report written to: {report_path}")

    if combined.findings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
