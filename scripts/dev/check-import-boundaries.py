#!/usr/bin/env python3
"""Cross-package import boundary scanner for Datrix monorepo.

Enforces architectural dependency rules by scanning all Python source files
in each package's src/, tests/, fixtures/, and helpers/ directories (when they
exist) and checking imports against forbidden prefix rules. Uses AST parsing -
no package installation required.

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


@dataclass(frozen=True)
class BoundaryRule:
    """Per-package boundary rule: forbidden prefixes plus subtree carve-outs.

    An import that matches a forbidden prefix is still permitted when it
    starts with one of ``allowed_subtrees`` — used to admit the narrow,
    language-agnostic platform -> codegen-common edges while keeping the
    language-shaped subtrees walled off.
    """

    forbidden_prefixes: tuple[str, ...]
    allowed_subtrees: frozenset[str] = frozenset()


# The closed set of language-agnostic datrix_codegen_common subtrees that
# platform generators (docker, k8s, aws, azure) are permitted to import.
# Adding a seventh subtree requires a doc + rule edit and review.
#
# Covers all 13 distinct datrix_codegen_common modules that platforms import today:
#   gendsl.*       — GenDSL compiler/executor/registry/scope
#   dashboards.*   — shared Grafana dashboard builder (builder, models)
#   algorithms.serverless            — serverless block plan algorithm
#   context_models.serverless        — serverless plan/render context models
#   context_models.replayable_ingestion — frozen, language-agnostic ingestion plan
#   enums           — shared enums (e.g. DatabaseEngine)
#
# Platforms remain FORBIDDEN from: transpiler.*, language-shaped context_models.*
# (entity/schema/service/endpoint/cache/pubsub/cqrs/jobs/project), and
# language-shaped algorithms.* (same suffixes).
PLATFORM_CODEGEN_COMMON_ALLOWED_SUBTREES: frozenset[str] = frozenset(
    [
        "datrix_codegen_common.gendsl",
        "datrix_codegen_common.dashboards",
        "datrix_codegen_common.algorithms.serverless",
        "datrix_codegen_common.context_models.serverless",
        "datrix_codegen_common.context_models.replayable_ingestion",
        "datrix_codegen_common.enums",
        "datrix_codegen_common.platform",
    ]
)

# The closed set of language-agnostic datrix_codegen_common subtrees that the
# SQL generator is permitted to import.  SQL is a schema/DDL generator — it is
# not a language generator, but it is not a platform generator either, so it
# carries its own narrower carve-out rather than the platform set.
#
# Covers the datrix_codegen_common modules that SQL imports today:
#   gendsl.*                          — GenDSL compiler/executor (shared entry point)
#   context_models.migration          — SQL migration state model (language-agnostic)
#   orchestration.migration_adapter   — migration adapter shared by SQL + TS (language-agnostic)
#
# SQL remains FORBIDDEN from: transpiler.*, language-shaped context_models.*
# (entity/schema/service/endpoint/cache/pubsub/cqrs/jobs/project), algorithms.*,
# dashboards.*, and the platform-specific subtrees.
SQL_CODEGEN_COMMON_ALLOWED_SUBTREES: frozenset[str] = frozenset(
    [
        "datrix_codegen_common.gendsl",
        "datrix_codegen_common.context_models.migration",
        "datrix_codegen_common.orchestration.migration_adapter",
    ]
)

# Boundary rules: source package -> BoundaryRule
# forbidden_prefixes: imports whose prefix matches are forbidden
# allowed_subtrees: specific sub-prefixes that override the broader forbidden prefix
BOUNDARY_RULES: dict[str, BoundaryRule] = {
    "datrix_common": BoundaryRule(
        forbidden_prefixes=(
            "datrix_language",
            "datrix_cli",
            "datrix_codegen_",  # Wildcard: any package starting with datrix_codegen_
            "datrix_extensions",
        ),
    ),
    "datrix_language": BoundaryRule(
        forbidden_prefixes=(
            "datrix_cli",
            "datrix_codegen_",  # Wildcard
        ),
    ),
    "datrix_codegen_common": BoundaryRule(
        forbidden_prefixes=(
            "datrix_codegen_python",
            "datrix_codegen_typescript",
            "datrix_codegen_docker",
            "datrix_codegen_k8s",
            "datrix_codegen_aws",
            "datrix_codegen_azure",
            "datrix_cli",
        ),
    ),
    "datrix_codegen_python": BoundaryRule(
        forbidden_prefixes=("datrix_codegen_typescript",),
    ),
    "datrix_codegen_typescript": BoundaryRule(
        forbidden_prefixes=("datrix_codegen_python",),
    ),
    # SQL generator: forbidden from sibling language packages and from the bulk of
    # datrix_codegen_common (it is not a language generator, so the transpiler and
    # language-shaped subtrees are off-limits).  SQL_CODEGEN_COMMON_ALLOWED_SUBTREES
    # carves out the narrow language-agnostic subtrees SQL legitimately uses.
    "datrix_codegen_sql": BoundaryRule(
        forbidden_prefixes=(
            "datrix_codegen_python",
            "datrix_codegen_typescript",
            "datrix_codegen_common",
            "datrix_cli",
        ),
        allowed_subtrees=SQL_CODEGEN_COMMON_ALLOWED_SUBTREES,
    ),
    # Component generator: forbidden from sibling language packages and datrix_cli.
    # Component is a language-agnostic scaffolding generator — it is not a language
    # generator, but unlike SQL it legitimately imports datrix_codegen_common freely
    # (gendsl, algorithms.serverless, context_models.serverless, etc.), so
    # datrix_codegen_common is NOT on its forbidden list.
    "datrix_codegen_component": BoundaryRule(
        forbidden_prefixes=(
            "datrix_codegen_python",
            "datrix_codegen_typescript",
            "datrix_cli",
        ),
    ),
    # Platform generators keep datrix_codegen_common on forbidden_prefixes but carry
    # PLATFORM_CODEGEN_COMMON_ALLOWED_SUBTREES to admit the language-agnostic
    # subtrees they legitimately consume. The transpiler and language-shaped
    # context_models/algorithms subtrees remain forbidden.
    "datrix_codegen_docker": BoundaryRule(
        forbidden_prefixes=(
            "datrix_codegen_common",
            "datrix_codegen_python",
            "datrix_codegen_typescript",
            "datrix_cli",
        ),
        allowed_subtrees=PLATFORM_CODEGEN_COMMON_ALLOWED_SUBTREES,
    ),
    "datrix_codegen_k8s": BoundaryRule(
        forbidden_prefixes=(
            "datrix_codegen_common",
            "datrix_codegen_python",
            "datrix_codegen_typescript",
            "datrix_cli",
        ),
        allowed_subtrees=PLATFORM_CODEGEN_COMMON_ALLOWED_SUBTREES,
    ),
    "datrix_codegen_aws": BoundaryRule(
        forbidden_prefixes=(
            "datrix_codegen_common",
            "datrix_codegen_python",
            "datrix_codegen_typescript",
            "datrix_cli",
        ),
        allowed_subtrees=PLATFORM_CODEGEN_COMMON_ALLOWED_SUBTREES,
    ),
    "datrix_codegen_azure": BoundaryRule(
        forbidden_prefixes=(
            "datrix_codegen_common",
            "datrix_codegen_python",
            "datrix_codegen_typescript",
            "datrix_cli",
        ),
        allowed_subtrees=PLATFORM_CODEGEN_COMMON_ALLOWED_SUBTREES,
    ),
    "datrix_extensions": BoundaryRule(
        forbidden_prefixes=(
            "datrix_cli",
            "datrix_codegen_python",
            "datrix_codegen_typescript",
            "datrix_codegen_common",
            "datrix_codegen_docker",
            "datrix_codegen_k8s",
            "datrix_codegen_aws",
            "datrix_codegen_azure",
            "datrix_language",
        ),
    ),
}


@dataclass(frozen=True)
class PackageInfo:
    """Package metadata for scanning."""

    name: str  # e.g., datrix_common
    root: Path  # e.g., d:/datrix/datrix-common
    src_dir: Path  # e.g., d:/datrix/datrix-common/src/datrix_common


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
    source_package: str,
    imported_module: str,
    forbidden_prefix: str,
    allowed_subtrees: frozenset[str] = frozenset(),
) -> bool:
    """Check if an import violates a forbidden prefix rule.

    An import that matches a forbidden prefix is still permitted when it
    starts with one of the ``allowed_subtrees`` entries — used to admit
    the narrow, language-agnostic platform -> codegen-common edges.

    Subtree matching uses an exact-or-child rule:
        subtree ``s`` matches ``m`` when ``m == s`` or ``m.startswith(s + ".")``.
    This ensures ``enums`` matches ``enums`` and ``enums.foo`` but never
    ``enums_other``.

    Args:
        source_package: The package doing the importing (e.g., datrix_common)
        imported_module: The full dotted import name (e.g., datrix_language.parser)
        forbidden_prefix: The forbidden prefix (may end with _ for wildcard)
        allowed_subtrees: Fully-qualified subtree roots that override the
            forbidden prefix for this source package.

    Returns:
        True if the import is forbidden, False otherwise
    """
    # Self-imports are always allowed
    if imported_module.startswith(source_package + ".") or imported_module == source_package:
        return False

    # Handle wildcard prefixes (e.g., datrix_codegen_)
    if forbidden_prefix.endswith("_"):
        # Wildcard match: imported module starts with prefix
        matched = imported_module.startswith(forbidden_prefix)
    else:
        # Exact prefix match (or module.submodule)
        matched = imported_module.startswith(forbidden_prefix + ".") or imported_module == forbidden_prefix

    if not matched:
        return False

    # The import matches a forbidden prefix; check whether an allowed subtree
    # carves it out.  A subtree ``s`` covers ``m`` when ``m == s`` or
    # ``m.startswith(s + ".")``.
    for subtree in allowed_subtrees:
        if imported_module == subtree or imported_module.startswith(subtree + "."):
            return False

    return True


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


def discover_packages(base_dir: Path) -> dict[str, PackageInfo]:
    """Discover all datrix-* packages in the monorepo.

    Args:
        base_dir: Monorepo root directory

    Returns:
        Dictionary mapping package names to PackageInfo objects
    """
    packages: dict[str, PackageInfo] = {}

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
        packages[package_name] = PackageInfo(
            name=package_name,
            root=candidate,
            src_dir=src_dir / package_name,
        )

    return packages


def scan_package_for_violations(
    package_info: PackageInfo,
    monorepo_root: Path,
    verbose: bool,
) -> list[Violation]:
    """Scan a single package for import boundary violations.

    Args:
        package_info: Package metadata
        monorepo_root: Monorepo root for relative path calculation
        verbose: Print each file being scanned

    Returns:
        List of violations found
    """
    violations: list[Violation] = []

    # Get the boundary rule for this package; no rule means no restrictions
    rule = BOUNDARY_RULES.get(package_info.name)
    if rule is None:
        return violations

    # Directories to scan: src/, tests/, fixtures/, helpers/
    scan_dirs = [package_info.src_dir]

    # Add optional directories if they exist
    for dir_name in ["tests", "fixtures", "helpers"]:
        optional_dir = package_info.root / dir_name
        if optional_dir.exists() and optional_dir.is_dir():
            scan_dirs.append(optional_dir)

    # Walk all .py files under all scan directories
    for scan_dir in scan_dirs:
        for py_file in scan_dir.rglob("*.py"):
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

            # Check each import against forbidden prefixes, respecting allowed subtrees
            for line_num, imported_module in imports:
                for forbidden_prefix in rule.forbidden_prefixes:
                    if is_forbidden_import(
                        package_info.name,
                        imported_module,
                        forbidden_prefix,
                        rule.allowed_subtrees,
                    ):
                        violations.append(
                            Violation(
                                file_path=py_file,
                                line_number=line_num,
                                imported_module=imported_module,
                                source_package=package_info.name,
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
    # Normalize to forward slashes for cross-platform matching
    rel_path = str(violation.file_path.relative_to(monorepo_root)).replace("\\", "/")

    for entry in allowlist:
        # Normalize allowlist pattern to forward slashes too
        pattern = entry.file_pattern.replace("\\", "/")
        # Simple substring matching for file patterns
        if pattern in rel_path and violation.imported_module.startswith(entry.import_prefix):
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
    for package_name, package_info in sorted(packages.items()):
        violations = scan_package_for_violations(
            package_info,
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
