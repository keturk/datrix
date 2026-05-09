#!/usr/bin/env python3
"""Cross-package import boundary scanner for Datrix monorepo.

Enforces architectural dependency rules by scanning all Python source files
in each package's src/ directory and checking imports against forbidden
prefix rules. Uses AST parsing - no package installation required.

Exit codes:
    0: Clean (no violations) or --warn mode
    1: Violations found in fail mode
    2: Usage error or configuration error
"""

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Boundary rules: source package -> list of forbidden import prefixes
# Keys are package names (e.g., datrix_common), values are forbidden import prefixes
BOUNDARY_RULES: dict[str, list[str]] = {
    "datrix_common": [
        "datrix_language",
        "datrix_cli",
        "datrix_codegen_",  # Wildcard: any package starting with datrix_codegen_
        "datrix_extensions",
    ],
    "datrix_language": [
        "datrix_cli",
        "datrix_codegen_",  # Wildcard
    ],
    "datrix_codegen_common": [
        "datrix_codegen_python",
        "datrix_codegen_typescript",
        "datrix_codegen_docker",
        "datrix_codegen_k8s",
        "datrix_codegen_aws",
        "datrix_codegen_azure",
        "datrix_cli",
    ],
    "datrix_codegen_python": [
        "datrix_codegen_typescript",
    ],
    "datrix_codegen_typescript": [
        "datrix_codegen_python",
    ],
    "datrix_codegen_docker": [
        "datrix_codegen_common",
        "datrix_codegen_python",
        "datrix_codegen_typescript",
        "datrix_cli",
    ],
    "datrix_codegen_k8s": [
        "datrix_codegen_common",
        "datrix_codegen_python",
        "datrix_codegen_typescript",
        "datrix_cli",
    ],
    "datrix_codegen_aws": [
        "datrix_codegen_common",
        "datrix_codegen_python",
        "datrix_codegen_typescript",
        "datrix_cli",
    ],
    "datrix_codegen_azure": [
        "datrix_codegen_common",
        "datrix_codegen_python",
        "datrix_codegen_typescript",
        "datrix_cli",
    ],
    "datrix_extensions": [
        "datrix_cli",
        "datrix_codegen_python",
        "datrix_codegen_typescript",
        "datrix_codegen_common",
        "datrix_codegen_docker",
        "datrix_codegen_k8s",
        "datrix_codegen_aws",
        "datrix_codegen_azure",
        "datrix_language",
    ],
}


@dataclass(frozen=True)
class Violation:
    """Represents a single import boundary violation."""

    file_path: Path
    line_number: int
    imported_module: str
    source_package: str
    forbidden_prefix: str


@dataclass(frozen=True)
class AllowlistEntry:
    """Represents a single allowlist entry."""

    file_pattern: str
    import_prefix: str
    issue_url: str


def is_forbidden_import(
    source_package: str, imported_module: str, forbidden_prefix: str
) -> bool:
    """Check if an import violates a forbidden prefix rule.

    Args:
        source_package: The package doing the importing (e.g., datrix_common)
        imported_module: The full dotted import name (e.g., datrix_language.parser)
        forbidden_prefix: The forbidden prefix (may end with _ for wildcard)

    Returns:
        True if the import is forbidden, False otherwise
    """
    # Self-imports are always allowed
    if imported_module.startswith(source_package + ".") or imported_module == source_package:
        return False

    # Handle wildcard prefixes (e.g., datrix_codegen_)
    if forbidden_prefix.endswith("_"):
        # Wildcard match: imported module starts with prefix
        return imported_module.startswith(forbidden_prefix)

    # Exact prefix match (or module.submodule)
    return imported_module.startswith(forbidden_prefix + ".") or imported_module == forbidden_prefix


def extract_imports_from_file(file_path: Path) -> list[tuple[int, str]]:
    """Extract all imports from a Python file using AST.

    Args:
        file_path: Path to Python source file

    Returns:
        List of (line_number, imported_module_name) tuples

    Raises:
        SyntaxError: If the file cannot be parsed
        OSError: If the file cannot be read
    """
    source_code = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source_code, filename=str(file_path))

    imports: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            # import foo, bar.baz
            for alias in node.names:
                imports.append((node.lineno, alias.name))

        elif isinstance(node, ast.ImportFrom):
            # from foo import bar
            # Skip relative imports (node.level > 0)
            if node.level == 0 and node.module is not None:
                imports.append((node.lineno, node.module))

    return imports


def discover_packages(base_dir: Path) -> dict[str, Path]:
    """Discover all datrix-* packages in the monorepo.

    Args:
        base_dir: Monorepo root directory

    Returns:
        Dictionary mapping package names (datrix_common) to src directories
    """
    packages: dict[str, Path] = {}

    for candidate in base_dir.iterdir():
        if not candidate.is_dir():
            continue

        # Only process datrix-* directories
        if not candidate.name.startswith("datrix-"):
            continue

        src_dir = candidate / "src"
        if not src_dir.exists():
            continue

        # Find the package name by looking for the actual package directory under src/
        # e.g., datrix-common/src/datrix_common/ -> package name is datrix_common
        package_dirs = [d for d in src_dir.iterdir() if d.is_dir() and d.name.startswith("datrix")]

        if not package_dirs:
            continue

        # Use the first datrix* directory name as the package name
        package_name = package_dirs[0].name
        packages[package_name] = src_dir / package_name

    return packages


def scan_package_for_violations(
    package_name: str,
    package_src_dir: Path,
    monorepo_root: Path,
    verbose: bool,
) -> list[Violation]:
    """Scan a single package for import boundary violations.

    Args:
        package_name: Package name (e.g., datrix_common)
        package_src_dir: Path to package source directory
        monorepo_root: Monorepo root for relative path calculation
        verbose: Print each file being scanned

    Returns:
        List of violations found
    """
    violations: list[Violation] = []

    # Get forbidden prefixes for this package
    forbidden_prefixes = BOUNDARY_RULES.get(package_name, [])
    if not forbidden_prefixes:
        return violations

    # Walk all .py files under the package src directory
    for py_file in package_src_dir.rglob("*.py"):
        if verbose:
            rel_path = py_file.relative_to(monorepo_root)
            print(f"Scanning: {rel_path}", file=sys.stderr)

        try:
            imports = extract_imports_from_file(py_file)
        except SyntaxError as e:
            rel_path = py_file.relative_to(monorepo_root)
            print(
                f"Warning: Failed to parse {rel_path}:{e.lineno} - {e.msg}",
                file=sys.stderr,
            )
            continue
        except OSError as e:
            rel_path = py_file.relative_to(monorepo_root)
            print(f"Warning: Failed to read {rel_path} - {e}", file=sys.stderr)
            continue

        # Check each import against forbidden prefixes
        for line_num, imported_module in imports:
            for forbidden_prefix in forbidden_prefixes:
                if is_forbidden_import(package_name, imported_module, forbidden_prefix):
                    violations.append(
                        Violation(
                            file_path=py_file,
                            line_number=line_num,
                            imported_module=imported_module,
                            source_package=package_name,
                            forbidden_prefix=forbidden_prefix,
                        )
                    )
                    break  # Only report first matching forbidden prefix

    return violations


def load_allowlist(allowlist_path: Path) -> list[AllowlistEntry]:
    """Load allowlist entries from TOML file.

    Args:
        allowlist_path: Path to allowlist TOML file

    Returns:
        List of allowlist entries (empty if file doesn't exist)
    """
    if not allowlist_path.exists():
        return []

    try:
        import tomllib  # Python 3.11+
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            print(
                "Warning: TOML library not available. Install tomli for allowlist support.",
                file=sys.stderr,
            )
            return []

    with allowlist_path.open("rb") as f:
        data = tomllib.load(f)

    entries: list[AllowlistEntry] = []
    for entry in data.get("allow", []):
        if not isinstance(entry, dict):
            continue

        file_pattern = entry.get("file", "")
        import_prefix = entry.get("import", "")
        issue_url = entry.get("issue", "")

        if file_pattern and import_prefix and issue_url:
            entries.append(
                AllowlistEntry(
                    file_pattern=file_pattern,
                    import_prefix=import_prefix,
                    issue_url=issue_url,
                )
            )

    return entries


def is_allowlisted(violation: Violation, allowlist: list[AllowlistEntry], monorepo_root: Path) -> bool:
    """Check if a violation is allowlisted.

    Args:
        violation: The violation to check
        allowlist: List of allowlist entries
        monorepo_root: Monorepo root for relative path matching

    Returns:
        True if the violation is allowlisted, False otherwise
    """
    rel_path = str(violation.file_path.relative_to(monorepo_root))

    for entry in allowlist:
        # Simple substring matching for file patterns
        if entry.file_pattern in rel_path and violation.imported_module.startswith(entry.import_prefix):
            return True

    return False


def format_violation(violation: Violation, monorepo_root: Path) -> str:
    """Format a violation for output.

    Args:
        violation: The violation to format
        monorepo_root: Monorepo root for relative path calculation

    Returns:
        Formatted violation string
    """
    rel_path = violation.file_path.relative_to(monorepo_root)
    # Use forward slashes for consistency
    rel_path_str = str(rel_path).replace("\\", "/")

    return (
        f"{rel_path_str}:{violation.line_number}\n"
        f"  forbidden import: {violation.imported_module}\n"
        f"  rule: {violation.source_package} must not import {violation.forbidden_prefix}"
    )


def auto_detect_base_dir(script_path: Path) -> Path:
    """Auto-detect monorepo root by walking up from script location.

    Args:
        script_path: Path to this script

    Returns:
        Monorepo root directory

    Raises:
        FileNotFoundError: If monorepo root cannot be found
    """
    # Script is at datrix/scripts/dev/check-import-boundaries.py
    # Monorepo root is 3 levels up
    current = script_path.resolve().parent
    for _ in range(3):
        current = current.parent

    # Verify this looks like the monorepo root
    if (current / "datrix-common").exists():
        return current

    raise FileNotFoundError(
        f"Could not auto-detect monorepo root from {script_path}. "
        f"Use --base-dir to specify manually."
    )


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 = clean/warn mode, 1 = violations found, 2 = error)
    """
    parser = argparse.ArgumentParser(
        description="Cross-package import boundary scanner for Datrix monorepo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-w",
        "--warn",
        action="store_true",
        help="Warning mode: report violations but exit 0",
    )
    parser.add_argument(
        "-b",
        "--base-dir",
        type=Path,
        help="Monorepo root directory (default: auto-detect)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print each file being scanned",
    )

    args = parser.parse_args()

    # Determine monorepo root
    if args.base_dir:
        monorepo_root = args.base_dir.resolve()
    else:
        try:
            monorepo_root = auto_detect_base_dir(Path(__file__))
        except FileNotFoundError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 2

    if not monorepo_root.exists():
        print(f"Error: Monorepo root not found: {monorepo_root}", file=sys.stderr)
        return 2

    # Load allowlist
    allowlist_path = monorepo_root / "datrix" / "scripts" / "config" / "import-boundary-allowlist.toml"
    allowlist = load_allowlist(allowlist_path)

    # Discover packages
    packages = discover_packages(monorepo_root)
    if not packages:
        print(f"Error: No datrix packages found in {monorepo_root}", file=sys.stderr)
        return 2

    if args.verbose:
        print(f"Found {len(packages)} packages:", file=sys.stderr)
        for pkg_name in sorted(packages.keys()):
            print(f"  - {pkg_name}", file=sys.stderr)
        print("", file=sys.stderr)

    # Scan all packages
    all_violations: list[Violation] = []
    for package_name, package_src_dir in sorted(packages.items()):
        violations = scan_package_for_violations(
            package_name,
            package_src_dir,
            monorepo_root,
            args.verbose,
        )
        all_violations.extend(violations)

    # Filter out allowlisted violations
    non_allowlisted_violations = [
        v for v in all_violations if not is_allowlisted(v, allowlist, monorepo_root)
    ]

    # Report violations
    if non_allowlisted_violations:
        mode = "Warning" if args.warn else "Error"
        print(f"{mode}: Found {len(non_allowlisted_violations)} import boundary violations:\n")

        for violation in non_allowlisted_violations:
            print(format_violation(violation, monorepo_root))
            print()  # Blank line between violations

        if args.warn:
            return 0
        return 1

    # Clean
    if args.verbose:
        print("No import boundary violations found.", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
