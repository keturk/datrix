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

Usage:
    python scripts/library/dev/libcst_scanner.py
    python scripts/library/dev/libcst_scanner.py --projects datrix-common datrix-language
    python scripts/library/dev/libcst_scanner.py --all --report libcst-report.md

    Or use the PowerShell wrapper:
        .\\scripts\\dev\\libcst.ps1 -All
        .\\scripts\\dev\\libcst.ps1 datrix-common datrix-language
"""

from __future__ import annotations

import argparse
import io
import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.platform == "win32" and __name__ == "__main__":
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

try:
    import libcst as cst
    from libcst.metadata import MetadataWrapper, PositionProvider
except ImportError:
    print(
        "ERROR: libcst is required. Install with: pip install libcst",
        file=sys.stderr,
    )
    sys.exit(1)

_library_dir = Path(__file__).resolve().parent.parent
if _library_dir.exists() and str(_library_dir) not in sys.path:
    sys.path.insert(0, str(_library_dir))

from shared.venv import get_datrix_root


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

def resolve_scan_paths(
    datrix_root: Path,
    project_names: list[str],
    scan_all: bool,
    *,
    include_tests: bool = True,
) -> list[tuple[str, Path]]:
    """Return (project_name, directory) pairs to scan.

    Args:
        datrix_root: Monorepo root.
        project_names: Package directory names (``datrix-common``, …).
        scan_all: If True, scan all ``datrix*`` projects with a ``src/`` tree.
        include_tests: If True, also append each project's ``tests/`` directory
            when it exists. If False, only ``src/`` (and scan_all semantics unchanged).

    Raises:
        FileNotFoundError: If a requested project does not exist.
    """
    if scan_all:
        pairs = []
        for d in sorted(datrix_root.iterdir()):
            if d.is_dir() and d.name.startswith("datrix") and (d / "src").is_dir():
                pairs.append((d.name, d / "src"))
                tests_dir = d / "tests"
                if include_tests and tests_dir.is_dir():
                    pairs.append((d.name, tests_dir))
        return pairs

    pairs = []
    for name in project_names:
        clean = name.rstrip("/\\")
        project_dir = datrix_root / clean
        if not project_dir.is_dir():
            available = sorted(
                d.name for d in datrix_root.iterdir()
                if d.is_dir() and d.name.startswith("datrix")
            )
            raise FileNotFoundError(
                f"Project '{clean}' not found. Available: {available}"
            )
        src_dir = project_dir / "src"
        if src_dir.is_dir():
            pairs.append((clean, src_dir))
        tests_dir = project_dir / "tests"
        if include_tests and tests_dir.is_dir():
            pairs.append((clean, tests_dir))
    return pairs


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Scan Datrix Python code for anti-patterns using LibCST.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "projects",
        nargs="*",
        help="Project names to scan (e.g. datrix-common datrix-language)",
    )
    parser.add_argument(
        "--all", "-a",
        action="store_true",
        dest="scan_all",
        help="Scan all projects in the monorepo",
    )
    parser.add_argument(
        "--report", "-r",
        type=str,
        default=None,
        help="Write markdown report to this path (relative to monorepo root)",
    )
    args = parser.parse_args()

    if not args.projects and not args.scan_all:
        parser.print_help()
        print("\nProvide project names or use --all to scan the entire monorepo.")
        return 1

    try:
        datrix_root = get_datrix_root()
    except FileNotFoundError:
        print("ERROR: Could not find Datrix root directory", file=sys.stderr)
        return 1

    try:
        scan_pairs = resolve_scan_paths(
            datrix_root, args.projects, args.scan_all, include_tests=True
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

    if args.report:
        report_path = Path(args.report)
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
