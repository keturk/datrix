#!/usr/bin/env python3
"""Shared Test Runner for Datrix Projects

Provides consistent test execution across all Datrix repositories with:
- Automatic xdist detection for parallel execution
- Coverage reporting
- Real-time output streaming
- Log file management
- Virtual environment detection

Usage:
 from shared.test_runner import TestRunner, TestConfig

 config = TestConfig(
 project_root=Path.cwd(),
 project_name="datrix-common",
 coverage_source="src",
 exclude_markers=["benchmark"]
 )
 runner = TestRunner(config)
 exit_code = runner.run(
 coverage=True,
 verbose=True,
 save_log=True
 )
"""

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from shared.logging_utils import LogConfig, TeeLogger
from shared.venv import get_venv_python


@dataclass
class TestConfig:
 """Configuration for test execution."""

 project_root: Path
 project_name: str
 test_dir: str = "tests/"
 coverage_source: str = "src"
 exclude_markers: Optional[list[str]] = None # e.g., ["benchmark"]


class TestRunner:
 """Shared test runner for Datrix projects."""

 def __init__(self, config: TestConfig):
  """
  Initialize test runner.

  Args:
   config: Test configuration
  """
  self.config = config
  self.python_exe: Optional[str] = None
  self.has_xdist: bool = False

 def _get_python_executable(self) -> str:
  """
  Get the Python executable to use.
  Uses common datrix venv at D:\\datrix\\.venv (where all projects are installed in editable mode)
  if available, otherwise falls back to current Python.
  """
  # Use shared.venv to get the venv Python (D:\\datrix\\.venv)
  try:
   venv_python = get_venv_python()
   if venv_python.exists():
    # Verify the Python executable works
    result = subprocess.run(
     [str(venv_python), "--version"],
     capture_output=True,
     check=False,
    )
    if result.returncode == 0:
     print(f"Using Datrix common virtual environment: {venv_python}")
     return str(venv_python)
  except Exception:
   pass

  # Fall back to current Python (should be from activated venv)
  print(f"Using current Python: {sys.executable}")
  if os.environ.get("VIRTUAL_ENV"):
   print(f" (from activated virtual environment: {os.environ.get('VIRTUAL_ENV')})")
  else:
   print("WARNING: No virtual environment detected. Consider setting up the Datrix venv at D:\\datrix\\.venv")
  return sys.executable

 def _check_xdist_available(self, python_exe: str) -> bool:
  """Check if pytest-xdist is available for parallel testing."""
  try:
   # Primary check: try importing pytest_xdist module directly (most reliable)
   # Note: pytest-xdist package provides pytest_xdist module, not xdist
   result = subprocess.run(
    [python_exe, "-c", "import pytest_xdist"],
    cwd=self.config.project_root,
    capture_output=True,
    check=False,
   )
   if result.returncode == 0:
    return True

   # Fallback: check if pytest recognizes -n option in help
   # This is less reliable but works if import fails for some reason
   result = subprocess.run(
    [python_exe, "-m", "pytest", "--help"],
    cwd=self.config.project_root,
    capture_output=True,
    text=True,
    check=False,
   )
   if result.returncode == 0:
    import re
    # Look for "-n" as standalone option (not --nf or --lfnf)
    # Pattern: -n followed by space and description about workers/processes
    # Must be more specific to avoid false positives from pytest-cov's "distributed testing support"
    xdist_patterns = [
     r'\s-n\s+(?:NUM|auto|workers|processes)', # -n NUM or -n auto
     r'number of workers', # Description mentioning workers
     r'parallel.*execution', # Parallel execution description
    ]
    for pattern in xdist_patterns:
     if re.search(pattern, result.stdout, re.IGNORECASE):
      return True

   return False
  except (subprocess.SubprocessError, FileNotFoundError):
   return False

 def _build_pytest_args(
  self,
  python_exe: str,
  coverage: bool,
  verbose: bool,
  marker_expr: str = None,
  test_path: str = None,
  keyword_expr: str = None,
  ignore_paths: Optional[list[str]] = None,
 ) -> list[str]:
  """Build pytest command arguments."""
  # Use test_path if provided, otherwise use default test_dir
  test_target = test_path if test_path else self.config.test_dir
  args = [python_exe, "-m", "pytest", test_target]

  # Add --ignore for paths that should be excluded from this run
  if ignore_paths:
   for ignore_path in ignore_paths:
    args.extend(["--ignore", ignore_path])

  # Enable parallel execution if xdist is available
  # Disable parallel execution when coverage is enabled to avoid race conditions
  # When running in parallel, exclude serial tests (they will run separately)
  exclude_serial_in_parallel = self.has_xdist and not coverage

  # Build marker expression, excluding serial tests if running in parallel
  # When marker_expr is None, the default behavior is to run ALL tests (including comprehensive)
  # This overrides pytest.ini's default marker expression which excludes comprehensive tests
  final_marker_expr = marker_expr
  if exclude_serial_in_parallel:
   if final_marker_expr:
    # Combine existing marker expression with "not serial"
    if "not serial" not in final_marker_expr.lower():
     final_marker_expr = f"({final_marker_expr}) and not serial"
   else:
    # When no marker_expr is provided, run ALL tests (override pytest.ini's exclusion)
    # Only exclude serial tests for parallel execution
    final_marker_expr = "not serial"

  # Marker expression filter (e.g., "unit", "integration", "not slow")
  # When we're excluding serial tests, we need to override pytest.ini's addopts
  # to prevent the default marker from conflicting with our marker
  if final_marker_expr:
   if exclude_serial_in_parallel:
    # Override pytest.ini's addopts marker expression completely
    args.extend(["-o", f'addopts=-v --strict-markers --tb=short -p no:benchmark -m "{final_marker_expr}"'])
   else:
    args.extend(["-m", final_marker_expr])

  # Exclude markers if specified (and no marker_expr override)
  # Skip this if we're using -o addopts override (exclude_serial_in_parallel), as it's already included
  if self.config.exclude_markers and not marker_expr and not exclude_serial_in_parallel:
   for marker in self.config.exclude_markers:
    args.extend(["-m", f"not {marker}"])
    # Disable the plugin if excluding benchmarks
    if marker == "benchmark":
     args.extend(["-p", "no:benchmark"])

  # Keyword expression filter (e.g., "test_parser")
  if keyword_expr:
   args.extend(["-k", keyword_expr])

  # Enable parallel execution if xdist is available
  if exclude_serial_in_parallel:
   args.extend(["-n", "auto"])
   # Use loadgroup distribution to keep slow tests together
   # Tests marked with @pytest.mark.slow will run on the same worker to avoid imbalance
   # This allows fast tests to run in parallel while slow/subprocess-heavy tests
   # are grouped together, preventing resource exhaustion and worker imbalance
   args.extend(["--dist", "loadgroup"])

  # Verbose output
  if verbose:
   args.append("-v")

  # Coverage
  if coverage:
   args.extend([
    f"--cov={self.config.coverage_source}",
    "--cov-report=term-missing",
    "--cov-report=html",
   ])

  return args

 def run(
  self,
  coverage: bool = False,
  verbose: bool = False,
  save_log: bool = True,
  marker_expr: str = None,
  test_path: str = None,
  keyword_expr: str = None,
 ) -> int:
  """
  Run tests with the specified options.

  Args:
   coverage: Generate coverage report
   verbose: Verbose test output
   save_log: Save output to log file
   marker_expr: Pytest marker expression (e.g., "unit", "integration", "not slow")
   test_path: Specific test file or directory to run
   keyword_expr: Pytest keyword expression (-k option)

  Returns:
   Exit code (0 = success, non-zero = failure)
  """
  # Get Python executable
  python_exe = self._get_python_executable()

  # Setup logging
  log_config = LogConfig(
   log_dir=".test_results",
   prefix="test-results",
   project_name=self.config.project_name,
   save_to_file=save_log,
  )

  with TeeLogger(log_config, self.config.project_root) as logger:
   # Check for xdist and install if missing (inside logger context for output)
   # Tests marked with @pytest.mark.serial will run in Phase 2 (serial execution)
   # Disable parallel execution for specific projects if needed
   disable_parallel_for_project = False # Can be set per-project if needed

   if coverage:
    logger.write("Coverage enabled - parallel execution will be disabled")
    # Still check for xdist to inform user, but won't use it
    self.has_xdist = self._check_xdist_available(python_exe)
    logger.write(f"pytest-xdist available: {self.has_xdist} (but disabled for coverage)")
   elif disable_parallel_for_project:
    logger.write(f"Parallel execution disabled for {self.config.project_name} to prevent worker crashes")
    # Still check for xdist to inform user, but won't use it
    self.has_xdist = self._check_xdist_available(python_exe)
    logger.write(f"pytest-xdist available: {self.has_xdist} (but disabled for {self.config.project_name})")
    # Force disable parallelism for this project
    self.has_xdist = False
   else:
    logger.write("Checking for pytest-xdist...")
    self.has_xdist = self._check_xdist_available(python_exe)
    logger.write(f"pytest-xdist available: {self.has_xdist}")
   # Only attempt to install xdist if not running with coverage
   # (since parallel execution is disabled with coverage anyway)
   # Also skip if parallel execution is disabled for this specific project
   if not self.has_xdist and not coverage and not disable_parallel_for_project:
    # Try to install pytest-xdist automatically
    logger.write("pytest-xdist not found. Installing for parallel test execution...")
    install_result = subprocess.run(
     [python_exe, "-m", "pip", "install", "pytest-xdist>=3.0.0"],
     cwd=self.config.project_root,
     capture_output=True,
     text=True,
     check=False,
    )
    if install_result.returncode == 0:
     # Re-check after installation
     self.has_xdist = self._check_xdist_available(python_exe)
     if self.has_xdist:
      logger.write("pytest-xdist installed successfully. Parallel execution enabled.")
     else:
      logger.write_warning("Warning: pytest-xdist installation may have failed. Continuing without parallel execution.")
    else:
     logger.write_warning("Warning: Failed to install pytest-xdist. Continuing without parallel execution.")
     if install_result.stderr:
      logger.write_warning(f" Error: {install_result.stderr}")
   if save_log:
    log_file = logger.get_log_path()
    logger.write(f"Test output will be saved to: {log_file}")

   # Clear __pycache__ directories before running tests to prevent import conflicts
   logger.write("Clearing __pycache__ directories...")
   try:
    import shutil
    pycache_count = 0
    for pycache_dir in self.config.project_root.rglob("__pycache__"):
     if pycache_dir.is_dir():
      shutil.rmtree(pycache_dir, ignore_errors=True)
      pycache_count += 1
    if pycache_count > 0:
     logger.write(f"Cleared {pycache_count} __pycache__ directories")
    else:
     logger.write("No __pycache__ directories found")
   except Exception as e:
    logger.write_warning(f"Warning: Failed to clear __pycache__ directories: {e}")

   logger.write(f"Running {self.config.project_name} tests...")

   # Run tests with real-time output streaming
   returncode = 1 # Default to failure
   env = os.environ.copy()
   env["PYTHONUNBUFFERED"] = "1"

   # Phase execution depends on xdist availability:
   # With xdist: Phase 1 (parallel) → Phase 2 (serial)
   # No xdist: Single phase (all tests)

   phase_results = {} # {phase_name: returncode}

   if self.has_xdist and not coverage:
    # ── Phase 1: Parallel tests (excluding serial) ─────────────────
    phase_num = 1
    logger.write("")
    logger.write("=" * 60)
    logger.write(f"Phase {phase_num}: Parallel tests (excluding serial)")
    logger.write("=" * 60)
    test_args_parallel = self._build_pytest_args(
     python_exe, coverage, verbose, marker_expr, test_path,
     keyword_expr, ignore_paths=None,
    )

    try:
     process = subprocess.Popen(
      test_args_parallel,
      cwd=self.config.project_root,
      stdout=subprocess.PIPE,
      stderr=subprocess.STDOUT,
      text=True,
      bufsize=1,
      env=env,
     )
     returncode_parallel, _ = logger.stream_process(process)
    except Exception as e:
     logger.write_error(f"Error running parallel tests: {e}")
     returncode_parallel = 1

    # Exit code 5 = no tests collected (not an error)
    if returncode_parallel == 5:
     returncode_parallel = 0
    phase_results["Parallel"] = returncode_parallel

    # ── Phase 2: Serial tests ────────────────────────────────────
    phase_num_serial = phase_num + 1
    logger.write(f"\nPhase {phase_num_serial}: Checking for serial tests...")
    # Temporarily disable xdist and exclude_markers to build args
    # without parallel flags and without conflicting -m flags.
    # Pass marker_expr=None so _build_pytest_args does NOT add a CLI
    # -m flag; the serial marker (which already incorporates the
    # original marker_expr) will be set via -o addopts below.
    original_has_xdist = self.has_xdist
    original_exclude_markers = self.config.exclude_markers
    self.has_xdist = False
    self.config.exclude_markers = None
    test_args_serial = self._build_pytest_args(
     python_exe, coverage, verbose, None, test_path,
     keyword_expr, ignore_paths=None,
    )
    self.has_xdist = original_has_xdist
    self.config.exclude_markers = original_exclude_markers

    # Add serial marker filter and override addopts
    serial_marker = "serial"
    if marker_expr:
     if "serial" not in marker_expr.lower():
      serial_marker = f"({marker_expr}) and serial"
     else:
      serial_marker = marker_expr

    test_args_serial.extend(["-o", f'addopts=-v --strict-markers --tb=short -p no:benchmark --no-cov -m "{serial_marker}"'])

    # Check if there are any serial tests to run
    check_args = test_args_serial + ["--collect-only", "-q"]
    try:
     check_process = subprocess.run(
      check_args,
      cwd=self.config.project_root,
      capture_output=True,
      text=True,
      env=env,
      timeout=30,
     )
     output = check_process.stdout + check_process.stderr
     has_serial_tests = (
      check_process.returncode == 0 and
      ("test" in output.lower() or "collected" in output.lower() or any(char.isdigit() for char in output.split() if "/" in char))
     ) or (
      check_process.returncode == 2 and "collected" in output.lower()
     )
    except Exception as e:
     logger.write(f"Warning: Could not check for serial tests: {e}")
     has_serial_tests = True

    if has_serial_tests:
     logger.write(f"Phase {phase_num_serial}: Running serial tests (sequential execution)...")
     try:
      process = subprocess.Popen(
       test_args_serial,
       cwd=self.config.project_root,
       stdout=subprocess.PIPE,
       stderr=subprocess.STDOUT,
       text=True,
       bufsize=1,
       env=env,
      )
      returncode_serial, _ = logger.stream_process(process)
     except Exception as e:
      logger.write_error(f"Error running serial tests: {e}")
      returncode_serial = 1
    else:
     logger.write(f"Phase {phase_num_serial}: No serial tests found, skipping.")
     returncode_serial = 0

    # Exit code 5 = no tests collected (not an error)
    if returncode_serial == 5:
     returncode_serial = 0
    phase_results["Serial"] = returncode_serial
   else:
    # No xdist: run all tests in a single phase
    phase_num = 1
    logger.write("")
    logger.write("=" * 60)
    logger.write("Phase 1: All tests (sequential)")
    logger.write("=" * 60)
    test_args = self._build_pytest_args(
     python_exe, coverage, verbose, marker_expr, test_path,
     keyword_expr, ignore_paths=None,
    )

    try:
     process = subprocess.Popen(
      test_args,
      cwd=self.config.project_root,
      stdout=subprocess.PIPE,
      stderr=subprocess.STDOUT,
      text=True,
      bufsize=1,
      env=env,
     )
     rc_remaining, _ = logger.stream_process(process)
    except Exception as e:
     logger.write_error(f"Error running tests: {e}")
     rc_remaining = 1

    # Exit code 5 = no tests collected (not an error)
    if rc_remaining == 5:
     rc_remaining = 0
    phase_results["Tests"] = rc_remaining

   # ── Combined summary ─────────────────────────────────────────────
   if len(phase_results) > 1:
    logger.write("\n" + "=" * 80)
    logger.write("COMBINED TEST SUMMARY")
    logger.write("=" * 80)
    for phase_name, rc in phase_results.items():
     status = "PASSED" if rc == 0 else "FAILED"
     logger.write(f" {phase_name:12s}: {status}")
    any_failed = any(rc != 0 for rc in phase_results.values())
    logger.write(f" {'Overall':12s}: {'FAILED' if any_failed else 'PASSED'}")
    logger.write("=" * 80)
    logger.write("")
    logger.write("Note: For detailed test counts from each phase, see the pytest summaries above.")
    logger.write("The test status checker will combine counts from all phases automatically.")

   # Determine overall return code: first non-zero, or 0
   returncode = 0
   for rc in phase_results.values():
    if rc != 0:
     returncode = rc
     break

   # Write final message
   # Exit code 5 = no tests collected (not an error for test libraries)
   if returncode == 0:
    logger.write("\nAll tests passed!")
   elif returncode == 5:
    logger.write("\nNo tests collected (test library or framework project)")
    returncode = 0 # Treat as success

  return returncode
