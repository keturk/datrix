"""
Script to check test status from latest test result log files.

This script searches for .test_results folders in specific datrix projects,
finds the latest test-results-*.log file, and reports test statistics.
"""

import re
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Optional
from dataclasses import dataclass

# Add library directory to sys.path to import from shared
library_dir = Path(__file__).parent.parent
if library_dir.exists() and str(library_dir) not in sys.path:
  sys.path.insert(0, str(library_dir))

from shared.venv import get_datrix_root


# ANSI color codes
class Colors:
 """ANSI color codes for terminal output."""
 GREEN = '\033[92m'
 RED = '\033[91m'
 YELLOW = '\033[93m'
 CYAN = '\033[96m'
 BOLD = '\033[1m'
 RESET = '\033[0m'
 GRAY = '\033[90m'

 @staticmethod
 def is_color_supported() -> bool:
  """Check if the terminal supports color output."""
  # Windows 10+ supports ANSI colors in PowerShell and cmd
  if sys.platform == 'win32':
   return True
  # Unix-like systems typically support colors
  return hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()


@dataclass
class PhaseResult:
 """Result for a single test phase (Parallel, Serial, or Tests)."""
 status: str # 'PASSED', 'FAILED', 'SKIPPED'
 passed: int = 0
 failed: int = 0
 errors: int = 0
 skipped: int = 0
 warnings: int = 0


@dataclass
class TestResult:
 """Test result information for a project."""
 project_path: str
 project_name: str
 status: str # 'PASSED', 'FAILED', or 'UNKNOWN'
 total_passed: int
 total_failed: int
 total_errors: int
 total_skipped: int
 total_warnings: int
 timestamp: str
 log_file: str
 phases: dict # {'Parallel': PhaseResult, 'Serial': PhaseResult, 'Tests': PhaseResult}


# Retired packages (merged into datrix-common); excluded from status report.
RETIRED_PROJECTS = frozenset({"datrix-core", "datrix-codegen"})


def get_datrix_projects(datrix_root: Path) -> List[str]:
 """
 Get list of active datrix projects that have tests directory.
 Excludes retired projects (datrix-core, datrix-codegen) merged into datrix-common.
 
 Args:
 datrix_root: Root directory containing datrix projects
 
 Returns:
 List of project names (sorted; excludes retired)
 """
 projects = []
 for item in datrix_root.iterdir():
  if item.is_dir() and item.name.startswith("datrix-"):
   if item.name in RETIRED_PROJECTS:
    continue
   if (item / "tests").exists():
    projects.append(item.name)
 return sorted(projects)


def parse_timestamp_from_log_file(log_file_name: str) -> Optional[datetime]:
 """
 Parse timestamp from log file name like 'test-results-20260115-130034.log'.

 Args:
 log_file_name: The log file name to parse

 Returns:
 datetime object or None if parsing fails
 """
 match = re.search(r'test-results-(\d{8})-(\d{6})\.log', log_file_name)
 if match:
  date_str = match.group(1) # YYYYMMDD
  time_str = match.group(2) # HHMMSS
  try:
   return datetime.strptime(f"{date_str}{time_str}", "%Y%m%d%H%M%S")
  except ValueError:
   return None
 return None


def find_latest_log_file(test_results_dir: Path) -> Optional[Path]:
 """
 Find the latest test-results-*.log file based on timestamp.

 Args:
 test_results_dir: Path to .test_results folder

 Returns:
 Path to the latest test-results-*.log file or None if not found
 """
 log_files = []

 for item in test_results_dir.iterdir():
  if item.is_file() and item.name.startswith('test-results-') and item.name.endswith('.log'):
   timestamp = parse_timestamp_from_log_file(item.name)
   if timestamp:
    log_files.append((timestamp, item))

 if not log_files:
  return None

 # Sort by timestamp descending and return the latest
 log_files.sort(key=lambda x: x[0], reverse=True)
 return log_files[0][1]


def _extract_counts_from_summary_line(line: str) -> Optional[dict]:
 """
 Extract test counts from a pytest summary line like:
 '====== 13 passed, 1 skipped in 0.57s ======'

 Returns dict with keys: passed, failed, errors, skipped, warnings, or None.
 """
 if '=' not in line:
  return None
 # Only accept pytest-style summary lines (leading run of '='); reject log lines like "line=1 error=..."
 if not re.match(r'^\s*={4,}', line):
  return None
 if not re.search(r'\d+\s+(passed|failed|error|skipped)', line, re.IGNORECASE):
  return None

 passed_match = re.search(r'\b(\d+)\s+passed\b', line, re.IGNORECASE)
 failed_match = re.search(r'\b(\d+)\s+failed\b', line, re.IGNORECASE)
 error_match = re.search(r'\b(\d+)\s+error', line, re.IGNORECASE)
 skipped_match = re.search(r'\b(\d+)\s+skipped\b', line, re.IGNORECASE)
 warning_match = re.search(r'\b(\d+)\s+warnings?\b', line, re.IGNORECASE)

 # Skip lines that only have "deselected" (from serial collection phase)
 if 'deselected' in line and not any([passed_match, failed_match, error_match]):
  return None

 if not (passed_match or failed_match or error_match):
  return None

 return {
 'passed': int(passed_match.group(1)) if passed_match else 0,
 'failed': int(failed_match.group(1)) if failed_match else 0,
 'errors': int(error_match.group(1)) if error_match else 0,
 'skipped': int(skipped_match.group(1)) if skipped_match else 0,
 'warnings': int(warning_match.group(1)) if warning_match else 0,
 }


def _extract_summary_section(lines: List[str]) -> List[str]:
 """Extract lines between the COMBINED TEST SUMMARY delimiters."""
 section = []
 in_summary = False
 for line in lines:
  if 'COMBINED TEST SUMMARY' in line:
   in_summary = True
   continue
  if not in_summary:
   continue
  if line.strip().startswith('=' * 10) and section:
   break
  if not line.strip().startswith('=' * 10):
   section.append(line)
 return section


def _parse_phase_statuses(lines: List[str]) -> dict:
 """
 Parse the COMBINED TEST SUMMARY section to extract per-phase status.

 Returns dict like {'Parallel': 'FAILED', 'Serial': 'PASSED', 'Tests': 'PASSED'}.
 """
 phase_statuses = {}
 pattern = re.compile(r'\s+(Parallel|Serial|Tests)\s*:\s*(PASSED|FAILED)')
 for line in _extract_summary_section(lines):
  match = pattern.match(line)
  if match:
   phase_statuses[match.group(1)] = match.group(2)
 return phase_statuses


_PHASE_HEADER_MAP = {
 'Parallel tests': 'Parallel',
 'Running serial tests': 'Serial',
 'All tests': 'Tests',
 'Remaining tests': 'Tests',
}


def _detect_phase(line: str) -> Optional[str]:
 """Detect phase name from a phase header line. Returns None if not a header."""
 if 'Phase' not in line:
  return None
 for keyword, phase_name in _PHASE_HEADER_MAP.items():
  if keyword in line:
   return phase_name
 return None


def _parse_phase_counts(lines: List[str]) -> dict:
 """
 Parse per-phase pytest summary counts by tracking phase headers.

 Returns dict like {'Parallel': {counts}, 'Serial': {counts}, 'Tests': {counts}}.
 """
 phase_counts = {}
 current_phase = None

 for line in lines:
  if 'COMBINED TEST SUMMARY' in line:
   break

  detected = _detect_phase(line)
  if detected:
   current_phase = detected
   continue

  if current_phase:
   counts = _extract_counts_from_summary_line(line)
   if counts:
    phase_counts[current_phase] = counts

 return phase_counts


def _count_warning_log_lines(lines: List[str]) -> int:
 """Count lines that are application WARNING log output (e.g. 'WARNING logger.name ...')."""
 return sum(1 for line in lines if line.startswith("WARNING "))


def _extract_timestamp(lines: List[str], log_file_name: str) -> str:
 """Extract timestamp from log header or filename."""
 for line in lines[:10]:
  if 'Timestamp:' in line:
   match = re.search(r'Timestamp:\s+(.+)', line)
   if match:
    return match.group(1).strip()
 file_timestamp = parse_timestamp_from_log_file(log_file_name)
 if file_timestamp:
  return file_timestamp.strftime('%Y-%m-%d %H:%M:%S')
 return ""


def _build_phases(phase_statuses: dict, phase_counts: dict) -> dict:
 """Build PhaseResult objects from parsed statuses and counts."""
 phases = {}
 for phase_name, phase_status in phase_statuses.items():
  counts = phase_counts.get(phase_name, {})
  phases[phase_name] = PhaseResult(
   status=phase_status,
   passed=counts.get('passed', 0),
   failed=counts.get('failed', 0),
   errors=counts.get('errors', 0),
   skipped=counts.get('skipped', 0),
   warnings=counts.get('warnings', 0),
  )
 return phases


def _compute_totals(phase_counts: dict, lines: List[str]) -> dict:
 """Compute aggregate totals from phase counts or fallback to last summary line."""
 totals = {'passed': 0, 'failed': 0, 'errors': 0, 'skipped': 0, 'warnings': 0}
 if phase_counts:
  for counts in phase_counts.values():
   for key in totals:
    totals[key] += counts[key]
 else:
  # No phase structure — find the last summary line (legacy/single-phase)
  for line in reversed(lines):
   counts = _extract_counts_from_summary_line(line)
   if counts:
    totals = counts
    break
 return totals


def parse_pytest_summary(log_file: Path) -> TestResult:
 """
 Parse the test-results-*.log file to extract test results from pytest summary.

 Args:
 log_file: Path to the log file

 Returns:
 TestResult object with parsed information
 """
 project_path = str(log_file.parent.parent.absolute())
 project_name = log_file.parent.parent.name
 status = "UNKNOWN"
 phases = {}
 totals = {'passed': 0, 'failed': 0, 'errors': 0, 'skipped': 0, 'warnings': 0}
 timestamp = ""

 try:
  with open(log_file, 'r', encoding='utf-8') as f:
   lines = f.read().split('\n')

  timestamp = _extract_timestamp(lines, log_file.name)
  phase_statuses = _parse_phase_statuses(lines)
  phase_counts = _parse_phase_counts(lines)
  phases = _build_phases(phase_statuses, phase_counts)
  totals = _compute_totals(phase_counts, lines)
  totals["warnings"] += _count_warning_log_lines(lines)

  if totals['failed'] == 0 and totals['errors'] == 0 and (totals['passed'] > 0 or totals['skipped'] > 0):
   status = 'PASSED'
  elif totals['failed'] > 0 or totals['errors'] > 0:
   status = 'FAILED'

 except Exception as e:
  print(f"Warning: Could not parse {log_file}: {e}", file=sys.stderr)

 return TestResult(
 project_path=project_path,
 project_name=project_name,
 status=status,
 total_passed=totals['passed'],
 total_failed=totals['failed'],
 total_errors=totals['errors'],
 total_skipped=totals['skipped'],
 total_warnings=totals['warnings'],
 timestamp=timestamp,
 log_file=str(log_file),
 phases=phases,
 )


def find_all_test_results(root_dir: Path) -> List[TestResult]:
 """
 Find test results for all specified datrix projects.

 Args:
 root_dir: Root directory to start searching from (workspace root)

 Returns:
 List of TestResult objects
 """
 results = []
 projects = get_datrix_projects(root_dir)

 for project_name in projects:
  project_dir = root_dir / project_name
  test_results_dir = project_dir / '.test_results'

  if test_results_dir.exists() and test_results_dir.is_dir():
   latest_log = find_latest_log_file(test_results_dir)

   if latest_log:
    result = parse_pytest_summary(latest_log)
    results.append(result)

 return results


def _colorize(text: str, color: str, use_colors: bool) -> str:
 """Apply ANSI color to text if colors are supported."""
 if use_colors:
  return f"{color}{text}{Colors.RESET}"
 return text


def _phase_cell(phase: Optional[PhaseResult], width: int, use_colors: bool) -> str:
 """Format a single phase status cell: OK when passed, failure count when failed, - when absent."""
 if phase is None:
  return _colorize("-".center(width), Colors.GRAY, use_colors)
 if phase.status == 'PASSED':
  return _colorize("OK".center(width), Colors.GREEN, use_colors)
 # Show failures and errors separately when both present
 if phase.failed and phase.errors:
  label = f"{phase.failed}F{phase.errors}E"
 elif phase.errors:
  label = f"{phase.errors}E"
 else:
  label = f"{phase.failed}F"
 return _colorize(label.center(width), Colors.BOLD + Colors.RED, use_colors)


def _status_symbol(status: str, use_colors: bool) -> str:
 """Return a colored status symbol."""
 symbols = {'PASSED': ('OK', Colors.GREEN), 'FAILED': ('!!', Colors.RED)}
 sym, color = symbols.get(status, ('??', Colors.YELLOW))
 return _colorize(sym, Colors.BOLD + color, use_colors)


_PHASE_NAMES = ['Parallel', 'Serial', 'Tests']


def _color_num(value: int, width: int, color: str, use_colors: bool) -> str:
 """Format a number right-justified with color if non-zero, plain '0' otherwise."""
 if value:
  return _colorize(str(value).rjust(width), color, use_colors)
 return "0".rjust(width)


_PHASE_COL_WIDTH = 8


def _format_result_row(result: TestResult, name_width: int, use_colors: bool) -> str:
 """Format a single project result as a table row."""
 c = lambda text, color: _colorize(text, color, use_colors)
 sym = _status_symbol(result.status, use_colors)
 pw = _PHASE_COL_WIDTH
 phase_cells = [_phase_cell(result.phases.get(p), pw, use_colors) for p in _PHASE_NAMES]
 ts = result.timestamp.split(' ')[1] if ' ' in result.timestamp else result.timestamp
 return (
 f"{sym} {result.project_name:<{name_width}} "
 f"{phase_cells[0]} {phase_cells[1]} {phase_cells[2]} "
 f"{_color_num(result.total_passed, 6, Colors.GREEN, use_colors)} "
 f"{_color_num(result.total_failed, 6, Colors.RED, use_colors)} "
 f"{_color_num(result.total_errors, 6, Colors.YELLOW, use_colors)} "
 f"{_color_num(result.total_skipped, 5, Colors.GRAY, use_colors)} "
 f"{_color_num(result.total_warnings, 5, Colors.YELLOW, use_colors)} "
 f"{c(ts, Colors.GRAY)}"
 )


def _format_summary_line(project_statuses: dict, use_colors: bool) -> str:
 """Format the project status summary line."""
 c = lambda text, color: _colorize(text, color, use_colors)
 mapping = [('PASSED', 'passed', Colors.GREEN), ('FAILED', 'failed', Colors.RED), ('UNKNOWN', 'unknown', Colors.YELLOW)]
 parts = [c(f"{project_statuses[key]} {label}", color) for key, label, color in mapping if project_statuses.get(key, 0) > 0]
 return ", ".join(parts)


def print_results(results: List[TestResult]):
 """
 Print the test results in a formatted table with phase columns.

 Args:
 results: List of TestResult objects to print
 """
 if not results:
  print("No test results found.")
  return

 use_colors = Colors.is_color_supported()
 c = lambda text, color: _colorize(text, color, use_colors)

 name_width = max(max(len(r.project_name) for r in results), len("Project"))
 line_width = 113

 # Title
 print("=" * line_width)
 print(c("TEST STATUS REPORT", Colors.BOLD + Colors.CYAN))
 print("=" * line_width)
 print()

 # Table header
 pw = _PHASE_COL_WIDTH
 header = (
 f" {'Project':<{name_width}} "
 f"{'Parallel':^{pw}} {'Serial':^{pw}} {'Tests':^{pw}} "
 f"{'Passed':>6} {'Failed':>6} {'Errors':>6} {'Skip':>5} {'Warn':>5} "
 f"{'Timestamp'}"
 )
 print(c(header, Colors.BOLD))
 print("-" * line_width)

 # Data rows
 project_statuses = {'PASSED': 0, 'FAILED': 0, 'UNKNOWN': 0}
 grand = {'passed': 0, 'failed': 0, 'errors': 0, 'skipped': 0, 'warnings': 0}

 for result in results:
  project_statuses[result.status] = project_statuses.get(result.status, 0) + 1
  grand['passed'] += result.total_passed
  grand['failed'] += result.total_failed
  grand['errors'] += result.total_errors
  grand['skipped'] += result.total_skipped
  grand['warnings'] += result.total_warnings
  print(_format_result_row(result, name_width, use_colors))

 # Totals row
 print("-" * line_width)
 totals_row = (
 f" {'TOTAL':<{name_width}} "
 f"{'':^{pw}} {'':^{pw}} {'':^{pw}} "
 f"{_color_num(grand['passed'], 6, Colors.GREEN, use_colors)} "
 f"{_color_num(grand['failed'], 6, Colors.RED, use_colors)} "
 f"{_color_num(grand['errors'], 6, Colors.YELLOW, use_colors)} "
 f"{_color_num(grand['skipped'], 5, Colors.GRAY, use_colors)} "
 f"{_color_num(grand['warnings'], 5, Colors.YELLOW, use_colors)}"
 )
 print(c(totals_row, Colors.BOLD))
 print()

 # Summary
 print(c("SUMMARY", Colors.BOLD + Colors.CYAN))
 print(f" Projects: {len(results)} {_format_summary_line(project_statuses, use_colors)}")

 # Log file paths for failing projects
 failed_results = [r for r in results if r.status == 'FAILED']
 if failed_results:
  print()
  print(c("LOG FILES (failing projects)", Colors.BOLD + Colors.RED))
  for r in failed_results:
   print(f" {r.log_file}")

 print("=" * line_width)


def main():
 """Main entry point."""
 # Find workspace root
 try:
  root_dir = get_datrix_root()
 except FileNotFoundError:
  print("ERROR: Could not find Datrix root directory", file=sys.stderr)
  sys.exit(1)

 print(f"Searching for test results in: {root_dir}")
 print()

 # Find all test results
 results = find_all_test_results(root_dir)

 # Sort results by project name for consistent output
 results.sort(key=lambda x: x.project_name)

 # Print results
 print_results(results)

 # Exit with error code if any tests failed
 if any(r.status == 'FAILED' for r in results):
  sys.exit(1)
 elif any(r.status == 'UNKNOWN' for r in results):
  sys.exit(2)
 else:
  sys.exit(0)


if __name__ == "__main__":
 main()
