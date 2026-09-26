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
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from shared.logging_utils import ColorCodes, LogConfig, TeeLogger, colorize
from shared.suite_stamp import (
 RUNNER_PLUGIN_MODULE,
 DeselectedEvidence,
 FullRunStamp,
 SuiteStampError,
 inputs_or_report,
 merge_run_records,
 prepare_full_run_stamp,
 read_distributed_deselected,
 selection_for,
 unstamped_recorder_environment,
 write_merged_timings,
)
from shared.venv import get_datrix_root, get_venv_python

#: The marker expression each ``test.ps1`` tier switch selects. One table, read
#: both where the expression is built and where a run's selection is recorded,
#: so a recorded tier is looked up, never inferred from an expression's text.
TIER_MARKER_EXPRESSIONS: dict[str, str] = {
 "unit": "unit",
 "integration": "integration",
 "e2e": "e2e",
 "fast": "not slow and not comprehensive",
 "slow": "slow or comprehensive",
}

#: Options of ``datrix_common.testing.feature_tags``, the ``pytest11`` plugin every
#: session in the shared venv loads. Every runner session requires a tag on every
#: collected test; ``-Tag`` narrows a run to the tests carrying the named tags.
REQUIRE_TAGS_OPTION = "--datrix-require-tags"
TAGS_OPTION = "--datrix-tags"
LIST_TAGS_OPTION = "--datrix-list-tags"

#: pytest exit codes of a phase that ran to its end: all passed, some failed,
#: or nothing was collected. Interrupted (2), internal error (3) and usage
#: error (4) mean the phase did not complete, so the run is never stamped.
_COMPLETED_PYTEST_EXIT_CODES = frozenset({0, 1, 5})
#: pytest's USAGE_ERROR exit code: what the feature-tag plugin's refusal (a
#: requested tag no collected test carries, or a tag set selecting the whole
#: test tree) exits with.
_PYTEST_USAGE_ERROR = 4

#: Commas inside a parametrized node id ("test_x.py::test_y[1,2]") are literal.
_TARGET_SEPARATOR = re.compile(r",(?![^\[]*\])")

#: index.json ``phases.Serial`` when the serial phase was skipped because every
#: parallel worker deselected nothing. A string, never a status dict: the phase
#: did not run, so it has no pass/fail status to report.
SERIAL_SKIPPED_NO_SERIAL_ITEMS = "skipped (0 serial items)"
#: The exit code of a run whose runner met evidence it cannot trust (pytest's
#: own INTERNAL_ERROR value), used only when no phase already failed.
_RUNNER_ERROR_EXIT_CODE = 3
#: Why the serial phase runs when the parallel phase recorded no evidence.
_NO_RECORDER_REASON = (
 "the parallel phase did not load the runner plugin (an unsaved run has no run "
 "directory to record into), so nothing shows whether serial items exist"
)


def _split_test_targets(test_path: str | None) -> list[str]:
 """The comma-separated targets of a ``-Specific`` selection, in given order."""
 if not test_path:
  return []
 return [target.strip() for target in _TARGET_SEPARATOR.split(test_path) if target.strip()]


def _classify_selection(
 marker_expr: str | None,
 test_path: str | None,
 keyword_expr: str | None,
 tags: Sequence[str] | None = None,
) -> dict[str, object]:
 """The ``selection`` recorded in a run's index.json.

 Full only when no marker expression, no test path, no keyword and no feature
 tag narrows the run -- a bare ``test.ps1 <package>``. Any marker expression is
 targeted, including one that is not a tier's: an unrecognized expression is
 recorded as ``marker`` with ``tier`` None, never mistaken for a full run.
 """
 tiers = [tier for tier, expression in TIER_MARKER_EXPRESSIONS.items() if expression == marker_expr]
 targets = _split_test_targets(test_path)
 return selection_for(
  specific=targets or None,
  keyword=keyword_expr or None,
  tier=tiers[0] if tiers else None,
  marker=marker_expr or None,
  tags=list(tags) if tags else None,
 )


def split_tags(raw: str | None) -> list[str]:
 """The feature tags of a comma-separated ``-Tag`` value, in given order."""
 if not raw:
  return []
 return [tag.strip() for tag in raw.split(",") if tag.strip()]


def _note_incomplete_phase(incomplete_phases: list[str], phase: str, returncode: int) -> None:
 """Record *phase* as not completed when pytest exited without finishing it."""
 if returncode not in _COMPLETED_PYTEST_EXIT_CODES and phase not in incomplete_phases:
  incomplete_phases.append(phase)


def _full_run_inputs(
 stamp: FullRunStamp,
 run_dir: Path,
 *,
 incomplete_phases: list[str],
 distributed: bool,
 standalone: bool,
 report: Callable[[str], None],
) -> dict[str, object] | None:
 """The ``inputs`` of a full run, or None when the run cannot be stamped.

 Stamped only when every executed phase completed AND every session the
 phases ran left its runner records: the merged records are classified into
 the fingerprint's observed components, and the merged ``timings.json`` is
 written beside them. Every refusal is reported through *report*; None means
 index.json records the selection and no ``inputs`` at all.
 """
 if incomplete_phases:
  report(
   f"This full run is recorded WITHOUT a suite-input stamp: phase(s) "
   f"{', '.join(incomplete_phases)} did not complete (the pytest process could not "
   f"start, or exited interrupted, with an internal error, or with a usage error). "
   f"index.json records its selection but no inputs."
  )
  return None

 def compute() -> dict[str, object]:
  records = merge_run_records(run_dir, distributed=distributed, standalone=standalone)
  write_merged_timings(run_dir, records)
  return stamp.inputs_from_records(records)

 return inputs_or_report(compute, report)


class RunnerDeselectedRecordError(RuntimeError):
 """The parallel phase's deselected records disagree or cannot be read.

 Every worker collects the identical tree, so disagreeing counts are a runner
 defect. Such evidence is never treated as zero: the serial phase runs and
 the run is failed with this error's message.
 """


@dataclass(frozen=True)
class SerialPhaseDecision:
 """Whether the serial phase runs, and why.

 ``skip_reason`` is the ``phases.Serial`` value index.json records when the
 phase is skipped, and None when it runs. ``why`` is the sentence the run's
 log carries either way.
 """

 skip_reason: str | None
 why: str


def _run_serial(why: str) -> SerialPhaseDecision:
 return SerialPhaseDecision(skip_reason=None, why=why)


def decide_serial_phase(
 evidence: DeselectedEvidence, *, parallel_completed: bool, user_filter_active: bool
) -> SerialPhaseDecision:
 """Skip the serial phase only on complete, agreeing evidence that it has nothing to run.

 The parallel phase selects ``not serial``, so a worker deselects every
 serial-marked item it collected. When every worker deselected ZERO items,
 the collected tree holds no serial item and the serial phase -- which
 collects the same tree -- would select nothing: it is skipped. Every other
 case runs it:

 - the parallel phase did not complete (interrupted, internal or usage
   error), so its records are not evidence;
 - a record is missing (no worker list, or a listed worker wrote none);
 - a marker (``-Unit``, ``-Fast``, ...) or keyword filter is active, so a
   non-zero count may be items the filter removed rather than serial ones.
   A ``-Specific`` selection is not such a filter: it narrows what is
   collected and deselects nothing, so the count stays exactly the number of
   serial items among the files it names;
 - some worker deselected items: those are the serial tests.

 Args:
  evidence: What the parallel phase's workers recorded.
  parallel_completed: The parallel phase's pytest ran to its end.
  user_filter_active: A marker expression or keyword narrowed the run.

 Raises:
  RunnerDeselectedRecordError: complete evidence in which workers disagree
   on the count -- a runner defect, never a reason to skip.
 """
 if not parallel_completed:
  return _run_serial("the parallel phase did not complete, so its deselected counts are not evidence")
 if evidence.absent is not None:
  return _run_serial(f"no complete deselected evidence: {evidence.absent}")
 if not evidence.counts:
  return _run_serial("no parallel worker recorded a deselected count")
 distinct = set(evidence.counts.values())
 if len(distinct) > 1:
  raise RunnerDeselectedRecordError(
   f"The parallel phase's workers disagree on how many items they deselected: "
   f"{dict(sorted(evidence.counts.items()))}. Every worker collects the identical tree, so "
   f"the counts must be equal; this is a runner defect and is never read as zero. The "
   f"serial phase runs anyway and this run is failed. Re-run the package; if it recurs, "
   f"inspect the deselected-<worker>.json records in the run directory."
  )
 if user_filter_active:
  return _run_serial(
   "a marker or keyword filter is active, so the deselected count cannot show whether serial items exist"
  )
 count = distinct.pop()
 if count == 0:
  return SerialPhaseDecision(
   skip_reason=SERIAL_SKIPPED_NO_SERIAL_ITEMS,
   why=f"every parallel worker ({len(evidence.counts)}) deselected 0 items, so no collected test is serial",
  )
 return _run_serial(f"every parallel worker deselected {count} serial-marked item(s)")


def _serial_phase_decision_for_run(
 run_dir: Path | None,
 *,
 recorded: bool,
 parallel_completed: bool,
 user_filter_active: bool,
) -> tuple[SerialPhaseDecision, list[str]]:
 """The serial-phase decision for a run, and the runner errors it met.

 Unreadable or disagreeing records are a runner error: the serial phase
 runs, and the error is returned so the caller fails the run with it.
 """
 try:
  evidence = (
   read_distributed_deselected(run_dir)
   if recorded and run_dir is not None
   else DeselectedEvidence(counts={}, absent=_NO_RECORDER_REASON)
  )
  decision = decide_serial_phase(
   evidence, parallel_completed=parallel_completed, user_filter_active=user_filter_active
  )
 except (RunnerDeselectedRecordError, SuiteStampError) as exc:
  return _run_serial(f"the deselected records cannot be trusted: {exc}"), [str(exc)]
 return decision, []


def _target_depth_sort_key(target: str) -> tuple[int, str]:
 """Sort key that orders pytest collection targets by DESCENDING path depth.

 Works around a real pytest collection-tree defect that fires whenever a
 single pytest invocation is given several explicit file-level targets
 (exactly what a comma-separated ``-Specific`` batch produces) that share a
 package ancestor: pytest's own ``Session.collect()`` intentionally does
 NOT cache a file's *immediate parent* collector ("files given directly
 multiple times on the command line should not be deduplicated" --
 ``_pytest/main.py``'s ``handle_dupes`` for a final, file-level path
 match), so that parent's ``.collect()`` runs again for every sibling
 explicit-file target under it. ``Package.collect()``/``Dir.collect()``
 build brand-new child collector objects on every call (no memoization),
 and conftest fixture visibility is bound to collector OBJECT IDENTITY
 (``FixtureManager._matchfactories``: ``fixturedef.node in parent_nodes``)
 rather than to the directory's path string. So re-collecting a shared
 ancestor package orphans any fixture already registered against the
 previous collector instance for that same path -- any test collected
 through a DIFFERENT (later-created) instance of that ancestor silently
 loses the fixture ("fixture 'x' not found"), even though the conftest.py
 that defines it imported successfully.

 A target with FEWER path segments is more likely to be a *direct* child
 of a package that also owns OTHER, deeper subdirectories carrying their
 own conftest fixtures (e.g. ``tests/unit/test_registry.py`` is a direct
 child of ``tests/unit``, which also owns ``tests/unit/generators/`` and
 its nested conftest chain). Processing targets in descending depth order
 -- deepest/most-nested files first, shallow direct-package-children last
 -- guarantees every deeper file's ancestor chain is already resolved
 (its fixtures matched against the collector instance current at THAT
 time) before any shallower target can trigger a re-collection that would
 otherwise orphan it. This is a genuine ordering invariant, not a lucky
 workaround: a shallow target's re-collection can only ever endanger
 targets nested BELOW it, and depth-descending order ensures none remain
 unprocessed when that happens.

 Ties (equal depth) fall back to a stable alphabetical key so the ordering
 is fully deterministic, not merely "depth descending, ties arbitrary".
 """
 file_part = target.split("::", 1)[0]
 depth = file_part.count("/") + file_part.count("\\")
 return (-depth, file_part)


@dataclass
class TestConfig:
 """Configuration for test execution."""

 project_root: Path
 project_name: str
 test_dir: str = "tests/"
 coverage_source: str = "src"
 exclude_markers: list[str] | None = None # e.g., ["benchmark"]


class TestRunner:
 """Shared test runner for Datrix projects."""

 def __init__(self, config: TestConfig):
  """
  Initialize test runner.

  Args:
   config: Test configuration
  """
  self.config = config
  self.python_exe: str | None = None
  self.has_xdist: bool = False

 def _get_python_executable(self, verbose: bool = False) -> str:
  """
  Get the Python executable to use.
  Uses common datrix venv at D:\\datrix\\.venv (where all projects are installed in editable mode)
  if available, otherwise falls back to current Python.

  Args:
   verbose: If True, print diagnostic messages about which Python is being used
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
     if verbose:
      print(f"Using Datrix common virtual environment: {venv_python}")
     return str(venv_python)
  except Exception:
   pass

  # Fall back to current Python (should be from activated venv)
  if verbose:
   print(f"Using current Python: {sys.executable}")
   if os.environ.get("VIRTUAL_ENV"):
    print(f" (from activated virtual environment: {os.environ.get('VIRTUAL_ENV')})")
   else:
    print("WARNING: No virtual environment detected. Consider setting up the Datrix venv at D:\\datrix\\.venv")
  return sys.executable

 def _get_test_summary(self, index_json_path: Path | None) -> dict | None:
  """
  Extract test summary from index.json.

  Args:
   index_json_path: Path to index.json file

  Returns:
   Dictionary with test counts or None if unavailable
  """
  if not index_json_path or not index_json_path.exists():
   return None

  try:
   import json
   with open(index_json_path, encoding="utf-8") as f:
    data = json.load(f)

   # Extract counts from index.json structure
   counts = data.get("counts", {})
   return {
    "passed": counts.get("passed", 0),
    "failed": counts.get("failed", 0),
    "error": counts.get("error", 0),
    "skipped": counts.get("skipped", 0),
   }
  except Exception:
   return None

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
  ignore_paths: list[str] | None = None,
  junit_xml_path: Path | None = None,
  enable_runner_plugin: bool = False,
  tags: Sequence[str] | None = None,
 ) -> list[str]:
  """Build pytest command arguments.

  ``enable_runner_plugin`` loads the runner plugin with its own ``-p`` argv
  element -- never inside a ``-o addopts=...`` override, where it would be
  one token of a single string and register nothing. The feature-tag options
  are standalone argv elements for the same reason: every session requires a
  tag on every test, and ``tags`` narrows it to the tests carrying one of them.
  """
  # Use test_path if provided, otherwise use default test_dir.
  # test_path may carry SEVERAL comma-separated files/node-IDs so one pytest
  # session (one collection, one run directory) covers a whole targeted set
  # instead of one runner startup per file. Commas inside parametrized
  # node IDs (e.g. "test_foo.py::test_bar[1,2]") are literal, not separators.
  test_targets = _split_test_targets(test_path)
  if test_targets:
   # Depth-descending order avoids a real pytest collection-tree defect when
   # several explicit file targets are batched into one session -- see
   # _target_depth_sort_key's docstring for the full mechanism.
   test_targets.sort(key=_target_depth_sort_key)
  else:
   test_targets = [self.config.test_dir]
  args = [python_exe, "-m", "pytest", *test_targets]
  if enable_runner_plugin:
   args.extend(["-p", RUNNER_PLUGIN_MODULE])
  args.append(REQUIRE_TAGS_OPTION)
  if tags:
   args.append(f"{TAGS_OPTION}={','.join(tags)}")

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

  # JUnit XML output for structured log writer
  if junit_xml_path:
   args.extend(["--junit-xml", str(junit_xml_path)])

  return args

 def _run_serial_phase(
  self,
  python_exe: str,
  coverage: bool,
  verbose: bool,
  marker_expr: str | None,
  test_path: str | None,
  keyword_expr: str | None,
  *,
  junit_xml_path: Path | None,
  enable_runner_plugin: bool,
  tags: Sequence[str] | None,
  env: dict[str, str],
  logger: TeeLogger,
  phase_num: int,
  incomplete_phases: list[str],
 ) -> int:
  """Run the ``serial``-marked tests in one process; return pytest's exit code.

  A phase whose pytest could not start, or did not run to its end, is noted
  in *incomplete_phases*.
  """
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
   junit_xml_path=junit_xml_path,
   enable_runner_plugin=enable_runner_plugin,
   tags=tags,
  )
  self.has_xdist = original_has_xdist
  self.config.exclude_markers = original_exclude_markers

  # Add serial marker filter and override addopts
  serial_marker = "serial"
  if marker_expr:
   serial_marker = marker_expr if "serial" in marker_expr.lower() else f"({marker_expr}) and serial"

  test_args_serial.extend(["-o", f'addopts=-v --strict-markers --tb=short -p no:benchmark --no-cov -m "{serial_marker}"'])

  logger.write(f"\nPhase {phase_num}: Running serial tests (sequential execution)...")
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
   incomplete_phases.append("Serial")
   return 1
  _note_incomplete_phase(incomplete_phases, "Serial", returncode_serial)
  return returncode_serial

 def run(
  self,
  coverage: bool = False,
  verbose: bool = False,
  save_log: bool = True,
  marker_expr: str = None,
  test_path: str = None,
  keyword_expr: str = None,
  tags: Sequence[str] | None = None,
 ) -> int:
  """
  Run tests with the specified options.

  Args:
   coverage: Generate coverage report
   verbose: Verbose test output (default is minimal/quiet output)
   save_log: Save output to log file
   marker_expr: Pytest marker expression (e.g., "unit", "integration", "not slow")
   test_path: Specific test file(s) or directory to run; several files/node-IDs
    may be given comma-separated and run in ONE pytest session
   keyword_expr: Pytest keyword expression (-k option)
   tags: Feature tags; the run keeps only tests carrying at least one of them

  Returns:
   Exit code (0 = success, non-zero = failure)
  """
  # Get Python executable
  python_exe = self._get_python_executable(verbose=verbose)

  if tags:
   refusal = self._preflight_tag_selection(python_exe, test_path, tags)
   if refusal is not None:
    return refusal

  # Setup logging with quiet mode (inverted from verbose)
  log_config = LogConfig(
   log_dir=".test_results",
   prefix="test-results",
   project_name=self.config.project_name,
   save_to_file=save_log,
   quiet_mode=not verbose,
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
   # With xdist: Phase 1 (parallel) → Phase 2 (serial), the latter skipped when
   #   the parallel phase's records prove no collected item is serial
   # No xdist: Single phase (all tests)

   phase_results = {} # {phase_name: returncode}
   # Phases that actually ran, and those that pytest exited 5 on (= collected
   # zero tests). A single phase collecting nothing is legitimate (e.g. the
   # parallel phase when the selection holds only `serial` tests), but a run
   # where EVERY executed phase collected nothing selected no tests at all --
   # reporting that as PASSED is a false green (see the zero-collection check
   # after the phase loop).
   executed_phases: list[str] = []
   zero_collection_phases: list[str] = []

   # Get run directory for JUnit XML output (available when save_log=True)
   run_dir = logger.get_run_dir()
   junit_parallel_path = run_dir / "junit-parallel.xml" if run_dir else None
   junit_serial_path = run_dir / "junit-serial.xml" if run_dir else None
   junit_path = run_dir / "junit.xml" if run_dir else None

   # A full run that saves its results loads the runner plugin in every phase
   # and is stamped with its suite inputs. Any other saved run loads it in the
   # parallel phase only, for the deselected counts that decide whether the
   # serial phase has anything to run; it is never stamped, so it pays no cone
   # derivation. An unsaved run has no run directory to record into.
   selection = _classify_selection(marker_expr, test_path, keyword_expr, tags)
   workspace_root = get_datrix_root()
   stamp = prepare_full_run_stamp(
    selection, run_dir, workspace_root, self.config.project_name, logger.write_warning,
   )
   enable_runner_plugin = stamp is not None and run_dir is not None
   record_parallel_phase = run_dir is not None
   if stamp is not None and run_dir is not None:
    env.update(stamp.plugin_environment(run_dir))
   elif run_dir is not None:
    env.update(unstamped_recorder_environment(run_dir, workspace_root, self.config.project_root))
   # Phases whose pytest process did not run to its end; any one refuses the stamp.
   incomplete_phases: list[str] = []
   # Phases deliberately not run, with the reason index.json records for each.
   skipped_phases: dict[str, str] = {}
   # Evidence the runner could not trust; any one fails the run.
   runner_errors: list[str] = []

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
     junit_xml_path=junit_parallel_path,
     enable_runner_plugin=record_parallel_phase,
     tags=tags,
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
     incomplete_phases.append("Parallel")
    _note_incomplete_phase(incomplete_phases, "Parallel", returncode_parallel)

    # Exit code 5 = no tests collected (not an error for this phase alone)
    executed_phases.append("Parallel")
    if returncode_parallel == 5:
     zero_collection_phases.append("Parallel")
     returncode_parallel = 0
    phase_results["Parallel"] = returncode_parallel

    # ── Phase 2: Serial tests ────────────────────────────────────
    # The parallel phase's own records say whether any collected item is
    # serial -- no second collection is spent to find out. The decision
    # skips the phase only on complete evidence that every worker
    # deselected nothing; anything else runs it.
    phase_num_serial = phase_num + 1
    serial_decision, decision_errors = _serial_phase_decision_for_run(
     run_dir,
     recorded=record_parallel_phase,
     parallel_completed="Parallel" not in incomplete_phases,
     user_filter_active=bool(marker_expr or keyword_expr or tags),
    )
    for error in decision_errors:
     logger.write_error(f"Runner error: {error}")
    runner_errors.extend(decision_errors)
    if serial_decision.skip_reason is not None:
     skipped_phases["Serial"] = serial_decision.skip_reason
     logger.write(f"\nPhase {phase_num_serial}: serial tests SKIPPED -- {serial_decision.why}")
    else:
     logger.write(f"\nPhase {phase_num_serial}: serial phase needed -- {serial_decision.why}")
     returncode_serial = self._run_serial_phase(
      python_exe, coverage, verbose, marker_expr, test_path, keyword_expr,
      junit_xml_path=junit_serial_path,
      enable_runner_plugin=enable_runner_plugin,
      tags=tags,
      env=env,
      logger=logger,
      phase_num=phase_num_serial,
      incomplete_phases=incomplete_phases,
     )
     executed_phases.append("Serial")
     # Exit code 5 = no tests collected (not an error for this phase alone)
     if returncode_serial == 5:
      zero_collection_phases.append("Serial")
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
     junit_xml_path=junit_path,
     enable_runner_plugin=enable_runner_plugin,
     tags=tags,
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
     incomplete_phases.append("Tests")
    _note_incomplete_phase(incomplete_phases, "Tests", rc_remaining)

    # Exit code 5 = no tests collected (not an error for this phase alone)
    executed_phases.append("Tests")
    if rc_remaining == 5:
     zero_collection_phases.append("Tests")
     rc_remaining = 0
    phase_results["Tests"] = rc_remaining

   # ── Post-process JUnit XML into structured output ────────────────
   index_json_path: Path | None = None
   if run_dir and save_log:
    try:
     from shared.structured_log_writer import (
      PHASE_STATUS_FAILED,
      PHASE_STATUS_PASSED,
      StructuredLogWriter,
     )

     # Expect a phase's JUnit XML only if that phase actually executed.
     # A phase that never launched pytest wrote no --junitxml file, so
     # unconditionally expecting one here produced a
     # structured_log_writer_xml_missing warning when nothing was wrong.
     # Every executed phase writes its file even when it selects nothing:
     # pytest emits the XML (with zero testcases) before exiting 5.
     xml_paths: list[Path] = []
     if self.has_xdist and not coverage:
      if junit_parallel_path and "Parallel" in executed_phases:
       xml_paths.append(junit_parallel_path)
      if junit_serial_path and "Serial" in executed_phases:
       xml_paths.append(junit_serial_path)
     else:
      if junit_path and "Tests" in executed_phases:
       xml_paths.append(junit_path)

     inputs = None
     if stamp is not None:
      inputs = _full_run_inputs(
       stamp,
       run_dir,
       incomplete_phases=incomplete_phases,
       distributed="Parallel" in executed_phases,
       standalone="Serial" in executed_phases or "Tests" in executed_phases,
       report=logger.write_warning,
      )

     writer = StructuredLogWriter(
      project_name=self.config.project_name,
      run_dir=run_dir,
     )
     from datetime import datetime
     # index.json's "phases" is a map of dicts, and status_tests.py reads
     # each phase's "status" (1 = passed, 2 = failed) to colour the report's
     # Parallel/Serial/Tests columns. Handing it the bare return codes made
     # every non-dict read as status 0, so a failed phase still rendered OK
     # -- the failure showed only in the row's overall symbol and counts.
     # A skipped phase records its reason string instead: it did not run,
     # so it has no status, and status_tests.py renders it as "-".
     phases_index: dict[str, dict[str, object] | str] = {
      name: {
       "status": PHASE_STATUS_PASSED if rc == 0 else PHASE_STATUS_FAILED,
      }
      for name, rc in phase_results.items()
     }
     phases_index.update(skipped_phases)
     writer.write(
      xml_paths=xml_paths,
      timestamp=datetime.now(),
      phase_results=phases_index,
      selection=selection,
      inputs=inputs,
      runner_errors=runner_errors,
     )
     index_json_path = run_dir / 'index.json'
     logger.write(f"Structured test results: {index_json_path}")
    except Exception as e:
     logger.write_warning(f"Warning: Failed to generate structured test results: {e}")

   # ── Combined summary ─────────────────────────────────────────────
   if len(phase_results) + len(skipped_phases) > 1:
    logger.write("\n" + "=" * 80)
    logger.write("COMBINED TEST SUMMARY")
    logger.write("=" * 80)
    for phase_name, rc in phase_results.items():
     status = "PASSED" if rc == 0 else "FAILED"
     logger.write(f" {phase_name:12s}: {status}")
    for phase_name, reason in skipped_phases.items():
     logger.write(f" {phase_name:12s}: SKIPPED ({reason})")
    any_failed = any(rc != 0 for rc in phase_results.values()) or bool(runner_errors)
    logger.write(f" {'Overall':12s}: {'FAILED' if any_failed else 'PASSED'}")
    logger.write("=" * 80)
    logger.write("")
    logger.write("Note: For detailed test counts from each phase, see the pytest summaries above.")
    logger.write("The test status checker will combine counts from all phases automatically.")

   # Determine overall return code: first non-zero, or 0. A runner error
   # fails a run whose phases all passed: its evidence could not be trusted.
   returncode = 0
   for rc in phase_results.values():
    if rc != 0:
     returncode = rc
     break
   if runner_errors and returncode == 0:
    returncode = _RUNNER_ERROR_EXIT_CODE

   # A run in which EVERY executed phase collected zero tests selected nothing
   # at all. Reporting that as PASSED is a false green: the caller believes a
   # suite ran and was clean when pytest never executed a single test (e.g. a
   # `-Specific` path that matches no file, or several paths passed as one
   # space-separated string, which pytest reads as a single nonexistent path).
   selected_nothing = (
    returncode == 0
    and bool(executed_phases)
    and all(phase in zero_collection_phases for phase in executed_phases)
   )
   if selected_nothing:
    selection_text = test_path or "(whole project)"
    if tags:
     selection_text = f"{selection_text}, tags {','.join(tags)}"
    logger.write_error(
     f"No tests were collected for {self.config.project_name} (selection: "
     f"{selection_text}). Expected at least one test to run; pytest collected zero, "
     f"so this run proves nothing and is NOT a pass. Valid selections: a test "
     f"file, a directory, or a pytest node id under the project's tests/ tree "
     f"-- exactly ONE path (a space-separated list of paths is read by pytest "
     f"as a single, nonexistent path). Fix: check the path exists, or run the "
     f"paths one at a time."
    )
    returncode = 5

   # Write final message
   if returncode == 0:
    logger.write("\nAll tests passed!")

   # ── Minimal summary (shown even in quiet mode) ────────────────────
   if logger.quiet_mode:
    # Parse test results from index.json if available
    test_summary = self._get_test_summary(index_json_path)

    # Build status line
    status = "PASSED" if returncode == 0 else "FAILED"
    color = ColorCodes.GREEN if returncode == 0 else ColorCodes.RED

    logger.write_console("")
    logger.write_console(colorize(f"[{status}] {self.config.project_name}", color))

    if test_summary:
     summary_parts = []
     if test_summary.get('passed', 0) > 0:
      summary_parts.append(f"pass: {test_summary['passed']}")
     if test_summary.get('failed', 0) > 0:
      summary_parts.append(f"fail: {test_summary['failed']}")
     if test_summary.get('error', 0) > 0:
      summary_parts.append(f"error: {test_summary['error']}")
     if test_summary.get('skipped', 0) > 0:
      summary_parts.append(f"skip: {test_summary['skipped']}")

     if summary_parts:
      logger.write_console(f"  {', '.join(summary_parts)}")

    # Show link to index.json
    if index_json_path:
     logger.write_console(f"  Details: {index_json_path}")
    elif logger.get_log_path():
     logger.write_console(f"  Log: {logger.get_log_path()}")

  return returncode

 def _preflight_tag_selection(
  self, python_exe: str, test_path: str | None, tags: Sequence[str],
 ) -> int | None:
  """Refuse a ``-Tag`` selection the feature-tag plugin would reject, before any phase runs.

  The plugin's check (a requested tag no collected test carries; a tag set
  that selects the package's whole test tree) fires after collection. In the
  parallel phase that is inside every xdist worker, each of which first
  collects the whole tree -- so a misspelled tag cost a full collection per
  worker and surfaced as a worker crash instead of the plugin's message. One
  collection-only session in a single process, over the run's own targets
  and tags, asks the same question once and runs nothing. It writes no run
  directory: nothing ran.

  Returns:
   pytest's usage-error code when the plugin refuses the selection (its
   message is printed); ``None`` when the run may proceed. Any other outcome
   of this collection -- a module that fails to import, say -- is left to
   the run itself, which reports it with full results.
  """
  targets = _split_test_targets(test_path) or [self.config.test_dir]
  argv = [
   python_exe, "-m", "pytest", *targets,
   "--collect-only", "-q", "-p", "no:cacheprovider",
   f"{TAGS_OPTION}={','.join(tags)}",
  ]
  completed = subprocess.run(  # noqa: S603 -- venv interpreter, fixed argv
   argv,
   cwd=self.config.project_root,
   capture_output=True,
   text=True,
   encoding="utf-8",
   errors="replace",
   check=False,
  )
  if completed.returncode != _PYTEST_USAGE_ERROR:
   return None
  print(
   f"Refusing the -Tag selection for {self.config.project_name} before running any "
   f"test ({','.join(tags)}):"
  )
  for stream in (completed.stdout, completed.stderr):
   if stream.strip():
    print(stream.rstrip("\n"))
  return _PYTEST_USAGE_ERROR

 def list_tags(self, test_path: str | None = None) -> int:
  """Print every feature tag in the package with its test count; run no test.

  A collection-only session with the feature-tag plugin's listing option. It
  writes no run directory: nothing ran, so there is no result to record.

  Args:
   test_path: Comma-separated files/directories to list instead of the whole
    test tree (``-ListTags -Specific "tests/unit/api"``).

  Returns:
   0 when every collected test carries a tag; 1 when any does not or a module
   failed to collect; pytest's own code for a usage error.
  """
  python_exe = self._get_python_executable(verbose=False)
  targets = _split_test_targets(test_path) or [self.config.test_dir]
  argv = [
   python_exe, "-m", "pytest", *targets,
   "--collect-only", "-q", "-p", "no:cacheprovider", LIST_TAGS_OPTION,
  ]
  completed = subprocess.run(  # noqa: S603 -- venv interpreter, fixed argv
   argv,
   cwd=self.config.project_root,
   capture_output=True,
   text=True,
   encoding="utf-8",
   errors="replace",
   check=False,
  )
  print(completed.stdout.rstrip("\n"))
  if completed.stderr.strip():
   print(completed.stderr.rstrip("\n"))
  return completed.returncode
