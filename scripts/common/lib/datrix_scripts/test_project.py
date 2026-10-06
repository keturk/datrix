#!/usr/bin/env python3
"""
Run tests for a specific Datrix project.
Consolidated test runner that works for any Datrix repository.

Usage (PYTHONPATH=scripts/common/lib; test.ps1 sets it):
 python -m datrix_scripts.test_project <project-name> [options]
 python -m datrix_scripts.test_project datrix-common --coverage --verbose
 python -m datrix_scripts.test_project datrix-language --no-auto-install # Prompt before installing

The script will automatically:
- Find the project root directory
- Automatically install missing dependencies (default behavior)
- Run tests excluding benchmark tests
- Execute tests in parallel if pytest-xdist is available
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

try:
 import tomllib
except ImportError:
 tomllib = None # type: ignore[assignment]

from datrix_scripts.node_test_runner import run_node_suite  # noqa: E402
from datrix_scripts.package_suites import SuiteKind, detect_suite_kind  # noqa: E402
from datrix_scripts.test_runner import TIER_MARKER_EXPRESSIONS, TestConfig, TestRunner, split_tags  # noqa: E402
from datrix_scripts.venv import get_datrix_root, get_venv_python, is_venv_active  # noqa: E402

# Marker filters that SELECT a marked subset of tests. A suite with no marker
# concept (a Node suite) has no such subset, and pytest's own convention is that
# a marker matching nothing is not a failure -- TestRunner maps pytest's exit
# code 5 to 0 for exactly this case.
_SUBSET_MARKER_FLAGS: tuple[str, ...] = ("unit", "integration", "e2e", "slow")

# Package name (as in pyproject) -> import name for dev deps we can import-check
_DEV_PACKAGE_TO_IMPORT: dict[str, str] = {
 "pytest": "pytest",
 "pytest-cov": "pytest_cov",
 "pytest-xdist": "pytest_xdist",
}


def _parse_package_name(spec: str) -> str:
 """Extract package name from a dependency spec (e.g. 'pytest>=7.0' -> 'pytest')."""
 # Strip version specifiers: >=, ==, <, >, ~=, etc.
 return re.split(r"\s*[\[\]<>!=~]", spec.strip(), maxsplit=1)[0].strip()


def _get_dev_specs(project_root: Path) -> list[str]:
 """Read [project.optional-dependencies].dev from pyproject.toml and return spec strings."""
 pyproject_path = project_root / "pyproject.toml"
 if not pyproject_path.exists():
  return []
 try:
  if tomllib is not None:
   with open(pyproject_path, "rb") as f:
    data = tomllib.load(f)
  else:
   return []
 except (OSError, ValueError):
  return []
 opt_deps = data.get("project", {}).get("optional-dependencies", {})
 dev_specs = opt_deps.get("dev", [])
 if not isinstance(dev_specs, list):
  return []
 return [s for s in dev_specs if isinstance(s, str)]


def _get_dev_imports_to_check(project_root: Path) -> list[str]:
 """
 Read [project.optional-dependencies].dev from pyproject.toml and return
 import names we can check (only known test packages).
 """
 imports: list[str] = []
 seen: set[str] = set()
 for spec in _get_dev_specs(project_root):
  pkg = _parse_package_name(spec)
  if pkg in _DEV_PACKAGE_TO_IMPORT:
   imp = _DEV_PACKAGE_TO_IMPORT[pkg]
   if imp not in seen:
    seen.add(imp)
    imports.append(imp)
 return imports


def find_project_root(project_name: str, datrix_root: Path) -> Path:
 """
 Find the root directory of a specific project.

 Args:
 project_name: Name of the project (e.g., "datrix-common")
 datrix_root: Root directory containing all datrix projects

 Returns:
 Path to the project root directory

 Raises:
 FileNotFoundError: If project directory is not found
 """
 project_path = datrix_root / project_name
 if not project_path.exists():
  # Get available projects
  available = sorted([
   d.name for d in datrix_root.iterdir()
   if d.is_dir() and d.name.startswith("datrix-")
  ])
  raise FileNotFoundError(
   f"Project '{project_name}' not found at {project_path}\n"
   f"Available projects: {', '.join(available)}"
  )
 return project_path


def check_dev_dependencies(python_exe: str, project_root: Path) -> tuple[bool, bool]:
 """
 Check if dev dependencies declared by the project are installed.

 Only checks packages that the project lists in [project.optional-dependencies].dev
 and that we know how to import-check (e.g. pytest, pytest-cov, pytest-xdist).
 Projects that do not declare pytest-xdist (or other optional test deps) are not
 required to have them installed.

 Args:
 python_exe: Python executable to check
 project_root: Root directory of the project

 Returns:
 (needs_install, has_pyproject_dev) tuple
 - needs_install: True if any project-declared checkable dev deps are missing
 - has_pyproject_dev: True if pyproject.toml has [project.optional-dependencies].dev
 """
 pyproject_path = project_root / "pyproject.toml"
 has_pyproject_dev = False
 content = ""
 if pyproject_path.exists():
  try:
   content = pyproject_path.read_text(encoding="utf-8")
   if "[project.optional-dependencies]" in content and "dev" in content:
    has_pyproject_dev = True
  except OSError:
   pass

 # Only check dev deps that this project declares (not a fixed list for all projects)
 modules_to_check = _get_dev_imports_to_check(project_root)

 missing_count = 0
 for module_name in modules_to_check:
  try:
   result = subprocess.run(
    [python_exe, "-c", f"import {module_name}"],
    cwd=project_root,
    capture_output=True,
    check=False,
   )
   if result.returncode != 0:
    missing_count += 1
  except (subprocess.SubprocessError, FileNotFoundError):
   missing_count += 1

 needs_install = missing_count > 0 and has_pyproject_dev
 return needs_install, has_pyproject_dev


def _is_monorepo(project_root: Path) -> bool:
 """True if project_root is inside a datrix monorepo (has datrix-common, datrix-language, etc.)."""
 monorepo_root = project_root.parent
 if not monorepo_root.exists():
  return False
 return any(
  (monorepo_root / pkg).exists()
  for pkg in ["datrix-common", "datrix-language", "datrix-common"]
 )


def install_dev_dependencies(python_exe: str, project_root: Path, auto_install: bool = True) -> bool:
 """
 Install dev dependencies from pyproject.toml.

 In a monorepo, ensures the project is installed editable (--no-deps) then
 installs only the [dev] extra specs to avoid re-resolving main deps (e.g. datrix-common).

 Args:
 python_exe: Python executable to use for installation
 project_root: Root directory of the project
 auto_install: Whether to install automatically without prompting

 Returns:
 True if installation was successful or not needed
 """
 if not auto_install:
  print("\nWould you like to install dev dependencies automatically? (y/N): ", end="", flush=True)
  try:
   response = input().strip().lower()
   if response not in ("y", "yes"):
    return False
  except (EOFError, KeyboardInterrupt):
   print("\nCancelled.", file=sys.stderr)
   return False

 print(f"\nInstalling dev dependencies for {project_root.name}...")
 print(f"Using Python: {python_exe}")

 is_monorepo = _is_monorepo(project_root)

 if is_monorepo:
  # Monorepo: avoid "pip install -e path[dev]" which can fail resolving datrix-common/datrix-language.
  # 1) Ensure project is installed editable with --no-deps
  check_cmd = [python_exe, "-m", "pip", "show", project_root.name]
  check_result = subprocess.run(check_cmd, capture_output=True, text=True, check=False)
  already_editable = (
   check_result.returncode == 0
   and ("Editable project location" in check_result.stdout or "-e" in check_result.stdout)
  )
  if not already_editable:
   install_cmd = [
    python_exe, "-m", "pip", "install", "-e", str(project_root), "--no-deps"
   ]
   result = subprocess.run(
    install_cmd,
    cwd=project_root,
    capture_output=True,
    text=True,
   )
   if result.returncode != 0:
    print("ERROR: Failed to install project in editable mode", file=sys.stderr)
    if result.stderr:
     print(result.stderr, file=sys.stderr)
    return False
  # 2) Install only the [dev] extra specs (no re-resolve of main deps)
  dev_specs = _get_dev_specs(project_root)
  if not dev_specs:
   print("No dev specs in pyproject.toml; skipping dev install.")
   return True
  install_cmd = [python_exe, "-m", "pip", "install", *dev_specs]
  result = subprocess.run(
   install_cmd,
   cwd=project_root,
   capture_output=True,
   text=True,
  )
 else:
  # Standalone: full install with [dev] extra
  install_cmd = [python_exe, "-m", "pip", "install", "-e", f"{project_root}[dev]"]
  result = subprocess.run(
   install_cmd,
   cwd=project_root,
   capture_output=True,
   text=True,
  )

 if result.returncode == 0:
  print("Successfully installed dev dependencies!")
  return True
 print("ERROR: Failed to install dev dependencies", file=sys.stderr)
 if result.stderr:
  print(result.stderr, file=sys.stderr)
 return False


def get_latest_test_result_status(project_root: Path) -> str | None:
    """Return the status of the project's most recent test run.

    Reads the latest timestamped directory (or legacy flat log) under
    ``project_root/.test_results/`` and returns ``"PASSED"``, ``"FAILED"``,
    or ``None`` when no previous results are found.
    """
    test_results_dir = project_root / ".test_results"
    if not test_results_dir.exists():
        return None

    # New directory format: test-results-YYYYMMDD-HHMMSS/
    run_dirs = sorted(
        [d for d in test_results_dir.iterdir() if d.is_dir() and d.name.startswith("test-results-")],
        key=lambda d: d.name,
        reverse=True,
    )
    if run_dirs:
        latest_dir = run_dirs[0]
        index_json = latest_dir / "index.json"
        if index_json.exists():
            try:
                with open(index_json, encoding="utf-8") as f:
                    data = json.load(f)
                result = data.get("result")
                if result in ("PASSED", "FAILED"):
                    return result
                counts = data.get("counts", {})
                if counts.get("failed", 0) > 0 or counts.get("error", 0) > 0:
                    return "FAILED"
                return "PASSED"
            except Exception:
                pass
        # Fallback: scan full.log for pytest summary line
        full_log = latest_dir / "full.log"
        if full_log.exists():
            try:
                content = full_log.read_text(encoding="utf-8", errors="replace")
                if re.search(r"\b\d+\s+failed\b", content):
                    return "FAILED"
                if re.search(r"\b\d+\s+passed\b", content):
                    return "PASSED"
            except Exception:
                pass

    # Legacy flat log files: test-results-*.log
    legacy_logs = sorted(
        [
            f
            for f in test_results_dir.iterdir()
            if f.is_file() and f.name.startswith("test-results-") and f.suffix == ".log"
        ],
        key=lambda f: f.name,
        reverse=True,
    )
    if legacy_logs:
        try:
            content = legacy_logs[0].read_text(encoding="utf-8", errors="replace")
            if re.search(r"\b\d+\s+failed\b", content) or re.search(r"\b\d+\s+error\b", content):
                return "FAILED"
            if re.search(r"\b\d+\s+passed\b", content):
                return "PASSED"
        except Exception:
            pass

    return None


def run_node_project(args: argparse.Namespace, project_root: Path) -> int:
 """Run a Node package's suite, reporting any option the runner cannot honor.

 A Node suite has no pytest markers and no coverage plumbing, so some flags
 that ``test.ps1`` passes to every package have no counterpart here. Each is
 stated on stdout rather than dropped: an option that silently does nothing is
 the same defect as a silent fallback, and it is what makes a caller believe a
 narrowed run happened when the whole suite ran.

 Args:
  args: Parsed command-line arguments.
  project_root: Root directory of the Node package.

 Returns:
  Process exit code from the Node suite, or 0 when a marker filter selects a
  subset this package cannot have (pytest's own no-collection convention).
 """
 if args.list_tags:
  print(
   f"[SKIP] {args.project_name}: a Node suite cannot enumerate its tests without "
   f"running them, so --list-tags lists nothing here. Its feature tags are the "
   f"'#<tag>' tokens in the test() and describe() names under the package's test "
   f"sources; read those names to pick a tag. Nothing was run."
  )
  return 0

 selecting_markers = [flag for flag in _SUBSET_MARKER_FLAGS if getattr(args, flag)]
 if selecting_markers:
  print(
   f"[SKIP] {args.project_name}: --{selecting_markers[0]} selects tests carrying "
   f"that marker, and a Node suite declares no test markers, so this package "
   f"contributes no tests to the selection. Nothing was run."
  )
  return 0

 if args.fast:
  print(
   f"{args.project_name}: --fast excludes slow-marked tests; a Node suite marks "
   f"none, so the whole suite runs."
  )

 if args.coverage:
  print(
   f"{args.project_name}: --coverage collects no data for a Node suite; the "
   f"suite runs without coverage instrumentation."
  )

 # -Fast runs the whole Node suite, but it was still requested as a tier: the
 # run is recorded as that targeted selection, never as a full one.
 return run_node_suite(
  project_root,
  args.project_name,
  verbose=args.verbose,
  save_log=not args.no_save,
  specific=args.specific,
  name_pattern=args.keyword,
  tier="fast" if args.fast else None,
  tags=split_tags(args.tags) or None,
 )


def main() -> int:
 parser = argparse.ArgumentParser(
 description="Run tests for a Datrix project (excluding benchmark tests)",
 formatter_class=argparse.RawDescriptionHelpFormatter,
 epilog="""
Examples:
 python -m datrix_scripts.test_project datrix-common
 python -m datrix_scripts.test_project datrix-language --coverage --verbose
 python -m datrix_scripts.test_project datrix-common --no-auto-install # Prompt before installing

Note: This script should be called from test.ps1, which handles virtual environment activation.
 """,
 )
 parser.add_argument(
 "project_name",
 help="Name of the project to test (e.g., datrix-common, datrix-language)",
 )
 parser.add_argument("--coverage", "-c", action="store_true", help="Generate coverage report")
 parser.add_argument("--verbose", "-v", action="store_true", help="Verbose test output")
 parser.add_argument("--no-save", action="store_true", help="Don't save test output to log files")
 parser.add_argument(
 "--no-auto-install",
 action="store_true",
 help="Disable automatic dependency installation (prompt instead)",
 )

 # Test type filters (mutually exclusive)
 test_filter_group = parser.add_mutually_exclusive_group()
 test_filter_group.add_argument("--unit", action="store_true", help="Run unit tests only")
 test_filter_group.add_argument("--integration", action="store_true", help="Run integration tests only")
 test_filter_group.add_argument("--e2e", action="store_true", help="Run end-to-end tests only")
 test_filter_group.add_argument("--fast", action="store_true", help="Run fast tests only (exclude slow tests)")
 test_filter_group.add_argument("--slow", action="store_true", help="Run slow tests only")

 # Test selection options
 parser.add_argument(
  "--specific",
  type=str,
  help=(
   "Run specific test file(s) or pattern. Several files/node-IDs may be given "
   "comma-separated and run in one pytest session (commas inside parametrized "
   "node IDs like '[1,2]' are literal)."
  ),
 )
 parser.add_argument("-k", "--keyword", type=str, help="Run tests matching keyword expression")
 parser.add_argument(
  "--tags",
  type=str,
  help=(
   "Comma-separated feature tags; run only the tests carrying at least one of them. "
   "Every named tag must be carried by at least one test in the package."
  ),
 )
 parser.add_argument(
  "--list-tags",
  action="store_true",
  help="Print every feature tag in the package with its test count, and run no test.",
 )
 parser.add_argument("--debug", action="store_true", help="Enable debug logging (DEBUG level instead of INFO)")
 parser.add_argument(
  "--rerun",
  action="store_true",
  help=(
   "Only run tests if the project's latest timestamped test log reports a failure. "
   "If the last run passed (or no previous results exist), the project is skipped."
  ),
 )

 args = parser.parse_args()

 # Check if virtual environment is active
 if not is_venv_active():
  print("ERROR: No virtual environment is currently active.", file=sys.stderr)
  print("", file=sys.stderr)
  print("This script should be called from test.ps1, which handles virtual environment activation.", file=sys.stderr)
  print("", file=sys.stderr)
  print("Usage:", file=sys.stderr)
  print(" .\\test.ps1 <project-name> [options]", file=sys.stderr)
  print(" .\\test.ps1 -All [options]", file=sys.stderr)
  print("", file=sys.stderr)
  print("Examples:", file=sys.stderr)
  print(" .\\test.ps1 datrix-common", file=sys.stderr)
  print(" .\\test.ps1 datrix-language --Coverage", file=sys.stderr)
  print(" .\\test.ps1 -All", file=sys.stderr)
  return 1

 # Find Datrix root and project root
 try:
  datrix_root = get_datrix_root()
  project_root = find_project_root(args.project_name, datrix_root)
 except FileNotFoundError as e:
  print(f"ERROR: {e}", file=sys.stderr)
  return 1

 if args.verbose:
  print(f"Found project '{args.project_name}' at: {project_root}")

 # --rerun guard: skip this project if its latest test run already passed.
 if args.rerun:
  status = get_latest_test_result_status(project_root)
  if status == "PASSED":
   print(f"[SKIP] {args.project_name}: latest test run passed — skipping re-run.")
   return 0
  elif status is None:
   print(f"[RERUN] {args.project_name}: no previous test results found — running tests.")
  else:
   print(f"[RERUN] {args.project_name}: latest test run reported failures — running tests.")

 # Dispatch on the kind of suite this package actually carries. Everything
 # below this point -- the venv, the editable installs, the pytest dev-dep
 # checks -- is specific to a Python package, and a Node package needs none
 # of it.
 suite_kind = detect_suite_kind(project_root)
 if suite_kind is SuiteKind.NODE:
  return run_node_project(args, project_root)

 # Get Python executable (use common venv at D:\\datrix\\.venv where all projects are installed in editable mode)
 python_exe = get_venv_python()
 if python_exe.exists():
  if args.verbose:
   print(f"Using Datrix common virtual environment: {python_exe}")
   print(" (All projects are installed in editable mode in this venv)")
  python_exe = str(python_exe)
 else:
  # Fall back to current Python (should be from activated venv)
  python_exe = sys.executable
  if args.verbose:
   print(f"Using current Python: {python_exe}")
  if not os.environ.get("VIRTUAL_ENV"):
   print("WARNING: No virtual environment detected. Consider setting up the Datrix venv at D:\\datrix\\.venv", file=sys.stderr)

 # When test.ps1 has already run Ensure-DatrixPackagesInstalled, skip per-project pip install -e to avoid concurrent installs.
 packages_ensured_by_caller = os.environ.get("DATRIX_PACKAGES_ENSURED") == "1"

 # Check for dev dependencies first (before other dependency checks)
 needs_dev_deps, has_pyproject_dev = check_dev_dependencies(python_exe, project_root)
 if needs_dev_deps:
  if packages_ensured_by_caller:
   if args.verbose:
    print("Packages ensured by caller (test.ps1); skipping per-project dev install. Proceeding with tests.")
  else:
   print("Detected missing dev dependencies. Installing automatically...")
   auto_install = not args.no_auto_install
   if install_dev_dependencies(python_exe, project_root, auto_install=auto_install):
    print("Dev dependencies installed successfully.")
   else:
    if not auto_install:
     print("\nTo install dev dependencies manually, run:", file=sys.stderr)
     print(f" cd {project_root}", file=sys.stderr)
     print(" pip install -e .[dev]", file=sys.stderr)
    else:
     print("ERROR: Failed to install dev dependencies", file=sys.stderr)
    return 1

 # TestConfig/TestRunner are imported at module scope (top of file); this module runs as
 # datrix_scripts.test_project, so the shared package is importable by construction.

 # Determine coverage source - most projects use "src", but check for common patterns
 coverage_source = "src"
 if (project_root / "src" / "datrix").exists():
  coverage_source = "src/datrix"
 elif (project_root / "src").exists():
  coverage_source = "src"

 # Use the shared test runner for actual test execution
 # Exclude benchmark tests by default
 # The TestRunner will create timestamped logs in project_root/.test_results/
 # with incremental (real-time) output streaming
 exclude_markers = ["benchmark"]

 # Build marker expression based on test type filters (the flags are mutually
 # exclusive, so at most one tier is set)
 selected_tiers = [tier for tier in TIER_MARKER_EXPRESSIONS if getattr(args, tier)]
 marker_expr = TIER_MARKER_EXPRESSIONS[selected_tiers[0]] if selected_tiers else None

 config = TestConfig(
 project_root=project_root,
 project_name=args.project_name,
 coverage_source=coverage_source,
 exclude_markers=exclude_markers,
 )

 runner = TestRunner(config)
 if args.list_tags:
  return runner.list_tags(args.specific)

 # Determine test path: --specific sets it to a custom path
 test_path = args.specific

 return runner.run(
 coverage=args.coverage,
 verbose=args.verbose,
 save_log=not args.no_save,
 marker_expr=marker_expr,
 test_path=test_path,
 keyword_expr=args.keyword,
 tags=split_tags(args.tags) or None,
 )


if __name__ == "__main__":
 sys.exit(main())
