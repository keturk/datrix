#!/usr/bin/env python3
"""Parity checker for Datrix codegen language implementations.

Compares builtins and type mappings between Python and TypeScript codegen
to identify missing implementations and inconsistencies.

Usage:
    python scripts/library/dev/parity_checker.py [--report path.md]

From repository root. Default report: parity-check-report.md under datrix root.
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Add library directory to sys.path
library_dir = Path(__file__).resolve().parent.parent
if library_dir.exists() and str(library_dir) not in sys.path:
    sys.path.insert(0, str(library_dir))

from shared.venv import get_datrix_root


@dataclass(frozen=True)
class BuiltinMethod:
    """Represents a builtin method mapping."""

    category: str
    method: str


@dataclass(frozen=True)
class TypeMapping:
    """Represents a type mapping."""

    canonical_name: str


@dataclass(frozen=True)
class ParityReport:
    """Parity check results."""

    python_builtins: set[BuiltinMethod]
    typescript_builtins: set[BuiltinMethod]
    python_types: set[TypeMapping]
    typescript_types: set[TypeMapping]

    @property
    def missing_ts_builtins(self) -> set[BuiltinMethod]:
        """Builtins in Python but not in TypeScript."""
        return self.python_builtins - self.typescript_builtins

    @property
    def missing_py_builtins(self) -> set[BuiltinMethod]:
        """Builtins in TypeScript but not in Python."""
        return self.typescript_builtins - self.python_builtins

    @property
    def missing_ts_types(self) -> set[TypeMapping]:
        """Types in Python but not in TypeScript."""
        return self.python_types - self.typescript_types

    @property
    def missing_py_types(self) -> set[TypeMapping]:
        """Types in TypeScript but not in Python."""
        return self.typescript_types - self.python_types

    @property
    def common_builtins(self) -> set[BuiltinMethod]:
        """Builtins in both implementations."""
        return self.python_builtins & self.typescript_builtins

    @property
    def common_types(self) -> set[TypeMapping]:
        """Types in both implementations."""
        return self.python_types & self.typescript_types

    @property
    def case_variants(self) -> dict[str, list[tuple[str, str]]]:
        """Find methods that exist in different case variants.

        Returns dict mapping normalized (category, method) to list of actual case variants.
        Example: ("json", "parse") -> [("JSON", "parse"), ("Json", "parse")]
        """
        all_builtins = self.python_builtins | self.typescript_builtins
        normalized_map: dict[tuple[str, str], list[tuple[str, str]]] = {}

        for builtin in all_builtins:
            key = (builtin.category.lower(), builtin.method.lower())
            actual = (builtin.category, builtin.method)
            normalized_map.setdefault(key, []).append(actual)

        # Filter to only those with multiple case variants
        return {
            f"{cat}.{method}": variants
            for (cat, method), variants in normalized_map.items()
            if len(set(variants)) > 1
        }


def _load_module_from_path(module_path: Path) -> Any:
    """Load a Python module from a file path."""
    spec = importlib.util.spec_from_file_location("temp_module", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["temp_module"] = module
    spec.loader.exec_module(module)
    return module


def _extract_builtin_mappings_from_dict_ast(file_path: Path) -> set[BuiltinMethod]:
    """Extract builtin mappings by parsing the Python AST.

    Looks for dictionary assignments with (category, method) tuple keys.
    """
    methods = set()

    try:
        with open(file_path, encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(file_path))
    except (OSError, SyntaxError) as e:
        print(f"WARNING: Failed to parse {file_path}: {e}", file=sys.stderr)
        return methods

    for node in ast.walk(tree):
        # Look for dict literals or dict() calls
        if isinstance(node, ast.Dict):
            for key in node.keys:
                if key is None:
                    continue
                # Look for tuple keys: ("Category", "method")
                if isinstance(key, ast.Tuple) and len(key.elts) == 2:
                    elts = key.elts
                    if isinstance(elts[0], ast.Constant) and isinstance(
                        elts[1], ast.Constant
                    ):
                        category = str(elts[0].value)
                        method = str(elts[1].value)
                        methods.add(BuiltinMethod(category=category, method=method))

    return methods


def _extract_type_mappings_from_dict_ast(file_path: Path) -> set[TypeMapping]:
    """Extract type mappings by parsing the Python AST.

    Looks for dictionary assignments with string keys representing type names.
    Handles both regular assignments (var = ...) and annotated assignments (var: type = ...).
    """
    types = set()

    try:
        with open(file_path, encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(file_path))
    except (OSError, SyntaxError) as e:
        print(f"WARNING: Failed to parse {file_path}: {e}", file=sys.stderr)
        return types

    # Look for assignments to *_TYPE_MAP variables
    for node in ast.walk(tree):
        dict_value = None
        var_name = None

        # Handle regular assignments: var = {...}
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.endswith("_TYPE_MAP"):
                    var_name = target.id
                    if isinstance(node.value, ast.Dict):
                        dict_value = node.value

        # Handle annotated assignments: var: type = {...}
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id.endswith(
                "_TYPE_MAP"
            ):
                var_name = node.target.id
                if isinstance(node.value, ast.Dict):
                    dict_value = node.value

        # Extract keys from the dict
        if dict_value is not None:
            for key in dict_value.keys:
                if key is None:
                    continue
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    types.add(TypeMapping(canonical_name=key.value))

    return types


def scan_python_builtins(datrix_root: Path) -> set[BuiltinMethod]:
    """Scan Python codegen for builtin method mappings."""
    builtins_file = (
        datrix_root
        / "datrix-codegen-python"
        / "src"
        / "datrix_codegen_python"
        / "transpiler"
        / "builtins.py"
    )

    if not builtins_file.exists():
        print(
            f"WARNING: Python builtins file not found: {builtins_file}", file=sys.stderr
        )
        return set()

    return _extract_builtin_mappings_from_dict_ast(builtins_file)


def scan_typescript_builtins(datrix_root: Path) -> set[BuiltinMethod]:
    """Scan TypeScript codegen for builtin method mappings.

    TypeScript builtins are split across multiple fragment files.
    """
    transpiler_dir = (
        datrix_root
        / "datrix-codegen-typescript"
        / "src"
        / "datrix_codegen_typescript"
        / "transpiler"
    )

    methods = set()

    # Scan main builtins.py
    main_file = transpiler_dir / "builtins.py"
    if main_file.exists():
        methods.update(_extract_builtin_mappings_from_dict_ast(main_file))

    # Scan fragment files
    for fragment_file in transpiler_dir.glob("_builtins_*.py"):
        methods.update(_extract_builtin_mappings_from_dict_ast(fragment_file))

    if not methods:
        print(
            f"WARNING: No TypeScript builtins found in {transpiler_dir}",
            file=sys.stderr,
        )

    return methods


def scan_python_types(datrix_root: Path) -> set[TypeMapping]:
    """Scan Python codegen for type mappings."""
    types_file = (
        datrix_root
        / "datrix-codegen-python"
        / "src"
        / "datrix_codegen_python"
        / "type_mappings.py"
    )

    if not types_file.exists():
        print(f"WARNING: Python types file not found: {types_file}", file=sys.stderr)
        return set()

    return _extract_type_mappings_from_dict_ast(types_file)


def scan_typescript_types(datrix_root: Path) -> set[TypeMapping]:
    """Scan TypeScript codegen for type mappings."""
    types_file = (
        datrix_root
        / "datrix-codegen-typescript"
        / "src"
        / "datrix_codegen_typescript"
        / "type_mappings.py"
    )

    if not types_file.exists():
        print(
            f"WARNING: TypeScript types file not found: {types_file}", file=sys.stderr
        )
        return set()

    return _extract_type_mappings_from_dict_ast(types_file)


def write_report(report_path: Path, parity: ParityReport) -> None:
    """Write parity check report to Markdown file."""
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# Datrix Codegen Parity Check Report\n\n")
        f.write(
            "Comparison of builtins and type mappings between Python and TypeScript codegen.\n\n"
        )

        # Executive summary
        f.write("## Executive Summary\n\n")
        f.write(f"- **Python builtins:** {len(parity.python_builtins)}\n")
        f.write(f"- **TypeScript builtins:** {len(parity.typescript_builtins)}\n")
        f.write(f"- **Common builtins:** {len(parity.common_builtins)}\n")
        f.write(f"- **Missing in TypeScript:** {len(parity.missing_ts_builtins)}\n")
        f.write(f"- **Missing in Python:** {len(parity.missing_py_builtins)}\n")
        case_variants = parity.case_variants
        if case_variants:
            f.write(f"- **⚠️ Case variants detected:** {len(case_variants)}\n")
        f.write("\n")

        f.write(f"- **Python types:** {len(parity.python_types)}\n")
        f.write(f"- **TypeScript types:** {len(parity.typescript_types)}\n")
        f.write(f"- **Common types:** {len(parity.common_types)}\n")
        f.write(f"- **Missing in TypeScript:** {len(parity.missing_ts_types)}\n")
        f.write(f"- **Missing in Python:** {len(parity.missing_py_types)}\n\n")

        # Case variant warnings
        if case_variants:
            f.write("## ⚠️ Case Sensitivity Issues\n\n")
            f.write(
                "The following methods exist in multiple case variants. This can cause "
                "failures when DSL code uses a different case than what's implemented:\n\n"
            )
            for method_name in sorted(case_variants.keys()):
                variants = case_variants[method_name]
                f.write(f"**{method_name}** has case variants:\n")
                for cat, meth in sorted(set(variants)):
                    # Determine which language(s) have this variant
                    in_python = BuiltinMethod(cat, meth) in parity.python_builtins
                    in_typescript = BuiltinMethod(cat, meth) in parity.typescript_builtins
                    langs = []
                    if in_python:
                        langs.append("Python")
                    if in_typescript:
                        langs.append("TypeScript")
                    f.write(f"- `{cat}.{meth}` — {', '.join(langs)}\n")
                f.write("\n")

        # Builtins section
        f.write("## Builtin Method Parity\n\n")

        if parity.missing_ts_builtins:
            f.write("### Missing in TypeScript\n\n")
            f.write(
                "The following builtin methods are implemented in Python but not in TypeScript:\n\n"
            )
            by_category: dict[str, list[str]] = {}
            for builtin in sorted(
                parity.missing_ts_builtins, key=lambda b: (b.category, b.method)
            ):
                by_category.setdefault(builtin.category, []).append(builtin.method)

            for category in sorted(by_category.keys()):
                methods = by_category[category]
                f.write(f"**{category}** ({len(methods)} methods):\n")
                for method in methods:
                    f.write(f"- `{category}.{method}`\n")
                f.write("\n")

        if parity.missing_py_builtins:
            f.write("### Missing in Python\n\n")
            f.write(
                "The following builtin methods are implemented in TypeScript but not in Python:\n\n"
            )
            by_category = {}
            for builtin in sorted(
                parity.missing_py_builtins, key=lambda b: (b.category, b.method)
            ):
                by_category.setdefault(builtin.category, []).append(builtin.method)

            for category in sorted(by_category.keys()):
                methods = by_category[category]
                f.write(f"**{category}** ({len(methods)} methods):\n")
                for method in methods:
                    f.write(f"- `{category}.{method}`\n")
                f.write("\n")

        if parity.common_builtins:
            f.write("### Common Builtins\n\n")
            f.write(
                f"The following {len(parity.common_builtins)} builtin methods are implemented in both:\n\n"
            )
            by_category = {}
            for builtin in sorted(
                parity.common_builtins, key=lambda b: (b.category, b.method)
            ):
                by_category.setdefault(builtin.category, []).append(builtin.method)

            for category in sorted(by_category.keys()):
                methods = by_category[category]
                f.write(f"**{category}** ({len(methods)} methods): ")
                f.write(", ".join(f"`{m}`" for m in methods))
                f.write("\n\n")

        # Type mappings section
        f.write("## Type Mapping Parity\n\n")

        if parity.missing_ts_types:
            f.write("### Missing in TypeScript\n\n")
            f.write(
                "The following type mappings are defined in Python but not in TypeScript:\n\n"
            )
            for type_mapping in sorted(
                parity.missing_ts_types, key=lambda t: t.canonical_name
            ):
                f.write(f"- `{type_mapping.canonical_name}`\n")
            f.write("\n")

        if parity.missing_py_types:
            f.write("### Missing in Python\n\n")
            f.write(
                "The following type mappings are defined in TypeScript but not in Python:\n\n"
            )
            for type_mapping in sorted(
                parity.missing_py_types, key=lambda t: t.canonical_name
            ):
                f.write(f"- `{type_mapping.canonical_name}`\n")
            f.write("\n")

        if parity.common_types:
            f.write("### Common Type Mappings\n\n")
            f.write(
                f"The following {len(parity.common_types)} type mappings are defined in both:\n\n"
            )
            for type_mapping in sorted(
                parity.common_types, key=lambda t: t.canonical_name
            ):
                f.write(f"- `{type_mapping.canonical_name}`\n")
            f.write("\n")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Check parity between Python and TypeScript codegen implementations.",
    )
    parser.add_argument(
        "--report",
        type=str,
        default=None,
        help="Output Markdown report path (default: <datrix_root>/parity-check-report.md)",
    )
    args = parser.parse_args()

    try:
        datrix_root = get_datrix_root()
    except FileNotFoundError:
        print("ERROR: Could not find Datrix root directory", file=sys.stderr)
        return 1

    print("Scanning Python builtins...")
    py_builtins = scan_python_builtins(datrix_root)
    print(f"  Found {len(py_builtins)} Python builtin methods")

    print("Scanning TypeScript builtins...")
    ts_builtins = scan_typescript_builtins(datrix_root)
    print(f"  Found {len(ts_builtins)} TypeScript builtin methods")

    print("Scanning Python type mappings...")
    py_types = scan_python_types(datrix_root)
    print(f"  Found {len(py_types)} Python type mappings")

    print("Scanning TypeScript type mappings...")
    ts_types = scan_typescript_types(datrix_root)
    print(f"  Found {len(ts_types)} TypeScript type mappings")

    parity = ParityReport(
        python_builtins=py_builtins,
        typescript_builtins=ts_builtins,
        python_types=py_types,
        typescript_types=ts_types,
    )

    report_path = (
        Path(args.report) if args.report else datrix_root / "parity-check-report.md"
    )
    if not report_path.is_absolute():
        report_path = datrix_root / report_path
    report_path.parent.mkdir(parents=True, exist_ok=True)

    write_report(report_path, parity)
    print(f"\nReport written: {report_path}")

    # Summary
    print("\n" + "=" * 70)
    print("PARITY CHECK SUMMARY")
    print("=" * 70)
    print(f"Python builtins:     {len(py_builtins)}")
    print(f"TypeScript builtins: {len(ts_builtins)}")
    print(f"Missing in TS:       {len(parity.missing_ts_builtins)}")
    print(f"Missing in Python:   {len(parity.missing_py_builtins)}")
    print()
    print(f"Python types:        {len(py_types)}")
    print(f"TypeScript types:    {len(ts_types)}")
    print(f"Missing in TS:       {len(parity.missing_ts_types)}")
    print(f"Missing in Python:   {len(parity.missing_py_types)}")
    print("=" * 70)

    if parity.missing_ts_builtins or parity.missing_ts_types:
        print("\n⚠️  TypeScript implementation is missing some features from Python")
        print(f"   See report for details: {report_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
