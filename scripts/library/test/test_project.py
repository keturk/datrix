#!/usr/bin/env python3
"""
Run tests for a specific Datrix project.
Consolidated test runner that works for any Datrix repository.

Usage:
 python scripts/library/test/test_project.py <project-name> [options]
 python scripts/library/test/test_project.py datrix-common --coverage --verbose
 python scripts/library/test/test_project.py datrix-language --no-auto-install # Prompt before installing

The script will automatically:
- Find the project root directory
- Automatically install missing dependencies (default behavior)
- Run tests excluding benchmark tests
- Execute tests in parallel if pytest-xdist is available
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

try:
 import tomllib
except ImportError:
 tomllib = None # type: ignore[assignment]

# Add library directory to sys.path to import from shared
# library/test -> library (where shared/ is located)
library_dir = Path(__file__).parent.parent
if library_dir.exists() and str(library_dir) not in sys.path:
 sys.path.insert(0, str(library_dir))

# Import shared modules
from shared.venv import get_datrix_root, get_venv_python, is_venv_active, ensure_datrix_venv
from shared.test_runner import TestConfig, TestRunner

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


def check_dependencies(python_exe: str, current_python_exe: str = None) -> tuple[bool, list[tuple[str, str]]]:
 """
 Check for required test dependencies in the appropriate Python environments.
 
 Args:
 python_exe: Python executable for project dependencies (project's venv)
 current_python_exe: Python executable for current environment (for shared modules)
 
 Returns:
 (all_present, missing_modules)
 """
 if current_python_exe is None:
  current_python_exe = sys.executable

 missing = []

 # Project dependencies (checked in project's venv)
 # Note: Projects should declare their own test dependencies in pyproject.toml [project.optional-dependencies] dev section
 project_modules = {}

 # Check project dependencies in project's venv
 for module_name, package_name in project_modules.items():
  try:
   result = subprocess.run(
    [python_exe, "-c", f"import {module_name}"],
    capture_output=True,
    check=False,
   )
   if result.returncode != 0:
    missing.append((module_name, package_name))
  except (subprocess.SubprocessError, FileNotFoundError):
   # If we can't run the Python, assume missing
   missing.append((module_name, package_name))

 # shared modules should be available via sys.path (from top of file)
 # Check if shared module can be imported
 try:
  # Try importing directly (sys.path is already set up)
  import shared
  # If we get here, the import succeeded
 except ImportError:
  # Not found via sys.path, shared modules are required
  missing.append(("shared", "datrix/scripts/library/shared"))
 except Exception:
  # If import check fails for other reasons, assume missing
  missing.append(("shared", "datrix/scripts/library/shared"))

 return len(missing) == 0, missing


def install_dependencies(
 missing_deps: list[tuple[str, str]], project_root: Path, python_exe: str, current_python_exe: str = None, auto_install: bool = True
) -> bool:
 """
 Install missing dependencies. Returns True if installation was successful.

 Args:
 missing_deps: List of (module_name, package_name) tuples
 project_root: Root directory of the project
 python_exe: Python executable for project dependencies (project's venv)
 current_python_exe: Python executable for current environment (for shared modules)
 auto_install: Whether to install automatically without prompting
 """
 if current_python_exe is None:
  current_python_exe = sys.executable

 if not auto_install:
  print("\nWould you like to install missing dependencies automatically? (y/N): ", end="", flush=True)
  try:
   response = input().strip().lower()
   if response not in ("y", "yes"):
    return False
  except (EOFError, KeyboardInterrupt):
   print("\nCancelled.", file=sys.stderr)
   return False

 # Separate project dependencies from shared modules
 project_deps = [dep for dep in missing_deps if dep[0] != "shared"]
 shared_dep = [dep for dep in missing_deps if dep[0] == "shared"]

 all_success = True

 # Install project dependencies in project's venv
 if project_deps:
  if python_exe != sys.executable:
   print(f"\nUsing project virtual environment: {python_exe}")
  else:
   print(f"\nUsing Python: {python_exe}")

  print("Installing missing dependencies...")

  # Check if we're in a monorepo environment
  monorepo_root = project_root.parent
  is_monorepo = monorepo_root.exists() and any(
   (monorepo_root / pkg).exists()
   for pkg in ["datrix-common", "datrix-language", "datrix-common"]
  )

  if is_monorepo:
   # In monorepo: All projects should already be installed in editable mode in the common venv
   # Check if project is already installed, and only install if missing
   print(f"Detected monorepo - checking if {project_root.name} is installed in editable mode...")
   check_cmd = [python_exe, "-m", "pip", "show", project_root.name]
   check_result = subprocess.run(check_cmd, capture_output=True, text=True, check=False)

   if check_result.returncode == 0:
    # Check if it's installed in editable mode
    if "Editable project location" in check_result.stdout or "-e" in check_result.stdout:
     print(f"{project_root.name} is already installed in editable mode.")
    else:
     print(f"Installing {project_root.name} in editable mode...")
     install_cmd = [python_exe, "-m", "pip", "install", "--force-reinstall", "-e", str(project_root), "--no-deps"]
     result = subprocess.run(install_cmd, cwd=project_root, capture_output=True, text=True)
     if result.returncode == 0:
      print(f"Successfully installed {project_root.name} in editable mode!")
     else:
      print(f"ERROR: Failed to install {project_root.name} in editable mode", file=sys.stderr)
      if result.stderr:
       print(f"Installation error: {result.stderr}", file=sys.stderr)
      all_success = False
   else:
    # Project not installed, install it
    print(f"Installing {project_root.name} in editable mode...")
    install_cmd = [python_exe, "-m", "pip", "install", "--force-reinstall", "-e", str(project_root), "--no-deps"]
    result = subprocess.run(install_cmd, cwd=project_root, capture_output=True, text=True)
    if result.returncode == 0:
     print(f"Successfully installed {project_root.name} in editable mode!")
    else:
     print(f"ERROR: Failed to install {project_root.name} in editable mode", file=sys.stderr)
     if result.stderr:
      print(f"Installation error: {result.stderr}", file=sys.stderr)
     all_success = False
  else:
   # Not in monorepo: install normally
   print("Attempting to install all dev dependencies...")
   install_cmd = [python_exe, "-m", "pip", "install", "-e", f"{project_root}[dev]"]
   result = subprocess.run(install_cmd, cwd=project_root, capture_output=True, text=True)

   if result.returncode == 0:
    print("Successfully installed dev dependencies!")
   else:
    # If that fails, try installing individually
    print("Bulk install failed, installing dependencies individually...")
    if result.stderr:
     print(f"Installation error: {result.stderr}", file=sys.stderr)
    for module_name, package_name in project_deps:
     print(f"Installing {package_name}...")
     install_cmd = [python_exe, "-m", "pip", "install", package_name]
     result = subprocess.run(install_cmd, capture_output=True, text=True)
     if result.returncode != 0:
      print(f"ERROR: Failed to install {package_name}", file=sys.stderr)
      if result.stderr:
       print(result.stderr, file=sys.stderr)
      all_success = False
     else:
      print(f"Successfully installed {package_name}")
 
 # Check shared modules availability (they should be in sys.path)
 if shared_dep:
  print(f"\nWARNING: shared modules not found. Ensuring library directory is in sys.path.", file=sys.stderr)
  # Re-ensure library directory (parent of shared) is in sys.path
  script_dir = Path(__file__).parent
  library_dir_path = script_dir.parent # library/test -> library
  shared_dir_path = library_dir_path / "shared"

  if library_dir_path.exists() and shared_dir_path.exists():
   library_dir_str = str(library_dir_path)
   if library_dir_str not in sys.path:
    sys.path.insert(0, library_dir_str)
    print(f"Added library directory to sys.path: {library_dir_str}")
   else:
    print(f"Library directory already in sys.path: {library_dir_str}")

   # Verify import works now
   try:
    import shared
    print("Successfully verified shared modules are available.")
   except ImportError as e:
    print(f"ERROR: Still cannot import shared modules after adding to sys.path: {e}", file=sys.stderr)
    print(f"Library directory: {library_dir_path}", file=sys.stderr)
    print(f"Shared directory: {shared_dir_path}", file=sys.stderr)
    print(f"Current sys.path (first 5):", file=sys.stderr)
    for p in sys.path[:5]:
     print(f" {p}", file=sys.stderr)
    all_success = False
  else:
   print(f"ERROR: Library directory not found at: {library_dir_path}", file=sys.stderr)
   all_success = False

 return all_success


def main() -> int:
 parser = argparse.ArgumentParser(
 description="Run tests for a Datrix project (excluding benchmark tests)",
 formatter_class=argparse.RawDescriptionHelpFormatter,
 epilog="""
Examples:
 python scripts/library/test/test_project.py datrix-common
 python scripts/library/test/test_project.py datrix-language --coverage --verbose
 python scripts/library/test/test_project.py datrix-common --no-auto-install # Prompt before installing

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
 parser.add_argument(
 "--skip-install",
 action="store_true",
 help="Skip dependency installation and show error message only",
 )

 # Test type filters (mutually exclusive)
 test_filter_group = parser.add_mutually_exclusive_group()
 test_filter_group.add_argument("--unit", action="store_true", help="Run unit tests only")
 test_filter_group.add_argument("--integration", action="store_true", help="Run integration tests only")
 test_filter_group.add_argument("--e2e", action="store_true", help="Run end-to-end tests only")
 test_filter_group.add_argument("--fast", action="store_true", help="Run fast tests only (exclude slow tests)")
 test_filter_group.add_argument("--slow", action="store_true", help="Run slow tests only")

 # Test selection options
 parser.add_argument("--specific", type=str, help="Run specific test file or pattern")
 parser.add_argument("-k", "--keyword", type=str, help="Run tests matching keyword expression")
 parser.add_argument("--debug", action="store_true", help="Enable debug logging (DEBUG level instead of INFO)")

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

 print(f"Found project '{args.project_name}' at: {project_root}")

 # Get Python executable (use common venv at D:\\datrix\\.venv where all projects are installed in editable mode)
 python_exe = get_venv_python()
 if python_exe.exists():
  print(f"Using Datrix common virtual environment: {python_exe}")
  print(" (All projects are installed in editable mode in this venv)")
  python_exe = str(python_exe)
 else:
  # Fall back to current Python (should be from activated venv)
  python_exe = sys.executable
  print(f"Using current Python: {python_exe}")
  if not os.environ.get("VIRTUAL_ENV"):
   print("WARNING: No virtual environment detected. Consider setting up the Datrix venv at D:\\datrix\\.venv", file=sys.stderr)

 # When test.ps1 has already run Ensure-DatrixPackagesInstalled, skip per-project pip install -e to avoid concurrent installs.
 packages_ensured_by_caller = os.environ.get("DATRIX_PACKAGES_ENSURED") == "1"

 # Check for dev dependencies first (before other dependency checks)
 needs_dev_deps, has_pyproject_dev = check_dev_dependencies(python_exe, project_root)
 if needs_dev_deps:
  if packages_ensured_by_caller:
   print("Packages ensured by caller (test.ps1); skipping per-project dev install. Proceeding with tests.")
  else:
   print("Detected missing dev dependencies. Installing automatically...")
   if not args.skip_install:
    auto_install = not args.no_auto_install
    if install_dev_dependencies(python_exe, project_root, auto_install=auto_install):
     print("Dev dependencies installed successfully.")
    else:
     if not auto_install:
      print("\nTo install dev dependencies manually, run:", file=sys.stderr)
      print(f" cd {project_root}", file=sys.stderr)
      print(" pip install -e .[dev]", file=sys.stderr)
      return 1
     else:
      print("ERROR: Failed to install dev dependencies", file=sys.stderr)
      return 1
   else:
    print("\nTo install dev dependencies, run:", file=sys.stderr)
    print(f" cd {project_root}", file=sys.stderr)
    print(" pip install -e .[dev]", file=sys.stderr)
    return 1

 # Check for required dependencies
 # Project dependencies (like hypothesis) are checked in project's venv
 # shared modules are checked via sys.path (library/shared is added at top of file)
 deps_ok, missing_deps = check_dependencies(python_exe, current_python_exe=sys.executable)
 if not deps_ok:
  if packages_ensured_by_caller:
   print("Packages ensured by caller (test.ps1); skipping per-project install. Proceeding with tests.")
  else:
   print("ERROR: Missing required test dependencies:", file=sys.stderr)
   for module_name, package_name in missing_deps:
    print(f" - {module_name} (install: {package_name})", file=sys.stderr)

  # Try to install dependencies if not skipped
  if not args.skip_install:
   auto_install = not args.no_auto_install # Default to True unless --no-auto-install is specified
   install_success = install_dependencies(missing_deps, project_root, python_exe, current_python_exe=sys.executable, auto_install=auto_install)

   if install_success:
    # After successful installation, don't re-check immediately
    # The packages should be available, and re-checking can give false negatives
    # due to subprocess import timing issues
    print("Dependencies installation completed. Proceeding with tests...")
   else:
    # Installation was cancelled or failed
    if not auto_install:
     print("\nTo install all test dependencies manually, run from the project root:", file=sys.stderr)
     print(f" cd {project_root}", file=sys.stderr)
     print(" pip install -e .[dev]", file=sys.stderr)
     return 1
    else:
     # Skip install was requested, just show instructions
     print("\nTo install all test dependencies, run from the project root:", file=sys.stderr)
     print(f" cd {project_root}", file=sys.stderr)
     print(" pip install -e .[dev]", file=sys.stderr)
     print("\nOr install individually:", file=sys.stderr)
     for _, package_name in missing_deps:
      print(f" pip install \"{package_name}\"", file=sys.stderr)
     return 1

 # Ensure shared modules are available (should be via sys.path from top of file)
 try:
  import shared
 except ImportError as e:
  print("ERROR: shared modules not available.", file=sys.stderr)
  print(f"Ensure library directory (parent of shared) is in sys.path. Current sys.path includes:", file=sys.stderr)
  for p in sys.path[:5]: # Show first 5 entries
   print(f" {p}", file=sys.stderr)
  script_dir = Path(__file__).parent
  expected_library_dir = script_dir.parent # library/test -> library
  print(f"Expected library directory: {expected_library_dir}", file=sys.stderr)
  print(f"Shared directory should be at: {expected_library_dir / 'shared'}", file=sys.stderr)
  return 1

 # Import test runner (after dependencies are confirmed)
 from shared.test_runner import TestConfig, TestRunner

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

 # Build marker expression based on test type filters
 marker_expr = None
 if args.unit:
  marker_expr = "unit"
 elif args.integration:
  marker_expr = "integration"
 elif args.e2e:
  marker_expr = "e2e"
 elif args.fast:
  marker_expr = "not slow and not comprehensive"
 elif args.slow:
  marker_expr = "slow or comprehensive"

 config = TestConfig(
 project_root=project_root,
 project_name=args.project_name,
 coverage_source=coverage_source,
 exclude_markers=exclude_markers,
 )

 # Determine test path: --specific sets it to a custom path
 test_path = args.specific

 runner = TestRunner(config)
 return runner.run(
 coverage=args.coverage,
 verbose=args.verbose,
 save_log=not args.no_save,
 marker_expr=marker_expr,
 test_path=test_path,
 keyword_expr=args.keyword,
 )


if __name__ == "__main__":
 sys.exit(main())
