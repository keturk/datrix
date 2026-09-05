#!/usr/bin/env python3
"""Shared logging utilities for Datrix scripts.

Provides tee-style output streaming, log file management, and consistent
formatting across all Datrix projects.

Usage:
	from shared.logging_utils import TeeLogger, LogConfig

	config = LogConfig(
	log_dir=".test_results",
	prefix="test-results",
	project_name="datrix-common"
	)

	with TeeLogger(config) as logger:
	logger.write("Starting tests...")
	# Output goes to both console and log file
"""

import queue
import re
import shutil
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TextIO

# Regex pattern to match ANSI escape codes
_ANSI_ESCAPE_PATTERN = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]|\x1b\[\?[0-9;]*[a-zA-Z]')

# How many candidate names TeeLogger will try when claiming a private run
# directory (base name, then base-2 ... base-N). Runs colliding on one
# timestamped name are the concurrency case this bounds; N is far above any
# plausible number of same-second runs of one package.
_MAX_RUN_DIR_CLAIM_ATTEMPTS = 1000


def strip_ansi(text: str) -> str:
	"""Remove ANSI escape codes from text.

	Args:
	text: Text potentially containing ANSI codes

	Returns:
	Text with ANSI codes removed
	"""
	return _ANSI_ESCAPE_PATTERN.sub('', text)


@dataclass
class LogConfig:
	"""Configuration for logging."""

	log_dir: str = ".logs"
	prefix: str = "log"
	project_name: str | None = None
	timestamp_format: str = "%Y%m%d-%H%M%S"
	header: str | None = None
	save_to_file: bool = True
	quiet_mode: bool = False


class ColorCodes:
	"""ANSI color codes for terminal output."""

	RESET = "\033[0m"
	RED = "\033[91m"
	GREEN = "\033[92m"
	YELLOW = "\033[93m"
	BLUE = "\033[94m"
	CYAN = "\033[96m"
	GRAY = "\033[90m"


def colorize(text: str, color: str) -> str:
	"""Add color to text (only for TTY)."""
	if sys.stdout.isatty():
		return f"{color}{text}{ColorCodes.RESET}"
	return text


class TeeLogger:
	"""
	Tee-style logger that writes to both console and file.

	Automatically handles file creation, timestamps, headers, and cleanup.
	"""

	def __init__(self, config: LogConfig, project_root: Path | None = None):
		"""
		Initialize tee logger.

		Args:
			config: Logging configuration
			project_root: Project root directory (defaults to current directory)
		"""
		self.config = config
		self.project_root = project_root or Path.cwd()
		self.log_file: Path | None = None
		self.log_handle: TextIO | None = None
		self.run_dir: Path | None = None
		self.quiet_mode = config.quiet_mode

	def __enter__(self):
		"""Context manager entry - create log file."""
		if self.config.save_to_file:
			self._create_log_file()
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		"""Context manager exit - close log file."""
		self._close_log_file()
		return False

	@staticmethod
	def _claim_run_dir(log_dir: Path, base_name: str) -> Path:
		"""Atomically claim a run directory that no other process owns.

		Tries ``base_name`` first, then ``base_name-2``, ``base_name-3``, ...
		Each attempt uses ``Path.mkdir()`` WITHOUT ``exist_ok``, which is an
		atomic create-or-fail: of two processes racing on the same candidate
		name, exactly one succeeds and the other raises FileExistsError and
		tries the next candidate. The returned directory is therefore owned by
		this process alone.

		Args:
			log_dir: Existing directory the run directory is created inside.
			base_name: Preferred directory name (e.g. ``test-results-20260713-120910``).

		Returns:
			Path to the newly created, exclusively-owned run directory.

		Raises:
			RuntimeError: If no free candidate name was found. This means an
				implausible number of runs collided on one timestamp; failing
				loudly is correct, because silently sharing a run directory
				makes every artifact in it untrustworthy.
		"""
		for attempt in range(1, _MAX_RUN_DIR_CLAIM_ATTEMPTS + 1):
			candidate_name = base_name if attempt == 1 else f"{base_name}-{attempt}"
			candidate = log_dir / candidate_name
			try:
				candidate.mkdir()
			except FileExistsError:
				continue
			return candidate

		raise RuntimeError(
			f"Could not claim a private run directory under {log_dir}: the "
			f"names {base_name} through {base_name}-{_MAX_RUN_DIR_CLAIM_ATTEMPTS} "
			f"are all taken. Expected at least one free name. This run cannot "
			f"proceed, because sharing a run directory with another run would "
			f"overwrite its junit XML / index.json and report another run's "
			f"tests as this one's. Fix: remove stale directories from "
			f"{log_dir} (e.g. via scripts/test/cleanup.ps1) and re-run."
		)

	def _create_log_file(self) -> None:
		"""Create log directory and full.log file with header."""
		log_dir = self.project_root / self.config.log_dir
		log_dir.mkdir(exist_ok=True)

		# Create a run directory that this invocation owns EXCLUSIVELY.
		#
		# The directory name is timestamped to the second. Two invocations that
		# reach this point within the same second therefore compute the same
		# name. Creating it with exist_ok=True would let both of them "own" one
		# directory: they would then overwrite each other's junit-*.xml,
		# full.log and index.json, and each process would still report its own
		# (correct) exit code -- so a run could print PASSED while the artifacts
		# it points the caller at describe a DIFFERENT run's tests entirely
		# (e.g. a `-Specific` run whose index.json names another file's tests).
		#
		# mkdir() without exist_ok is an atomic claim: exactly one racer creates
		# the directory, every other racer gets FileExistsError and moves on to
		# the next candidate name. Never relax this to exist_ok=True.
		timestamp = datetime.now().strftime(self.config.timestamp_format)
		self.run_dir = self._claim_run_dir(log_dir, f"{self.config.prefix}-{timestamp}")

		# Write full.log inside the run directory
		self.log_file = self.run_dir / "full.log"
		self.log_handle = open(self.log_file, "w", encoding="utf-8")

		# Write header
		if self.config.header:
			header_text = self.config.header
		elif self.config.project_name:
			header_text = f"{self.config.project_name} - {self.config.prefix}"
		else:
			header_text = self.config.prefix

		self.log_handle.write(f"{header_text}\n")
		self.log_handle.write(
			f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
		)
		self.log_handle.write("=" * 80 + "\n\n")
		self.log_handle.flush()

		if not self.quiet_mode:
			print(f"Log file: {self.log_file}")

	def _close_log_file(self) -> None:
		"""Close log file."""
		if self.log_handle:
			self.log_handle.close()
		if self.log_file and not self.quiet_mode:
			print(f"\nLog saved to: {self.log_file}")

	def write(self, text: str, end: str = "\n") -> None:
		"""
		Write text to console and log file.

		Args:
			text: Text to write
			end: Line ending (default: newline)
		"""
		# Write to console with explicit flush to prevent buffering (unless quiet mode)
		if not self.quiet_mode:
			print(text, end=end, flush=True)

		# Write to log file (strip ANSI codes for clean logs)
		if self.log_handle:
			clean_text = strip_ansi(text)
			self.log_handle.write(clean_text + end)
			self.log_handle.flush()

	def write_line(self, text: str) -> None:
		"""Write a line of text (convenience method)."""
		self.write(text, end="\n")

	def write_console(self, text: str, end: str = "\n") -> None:
		"""
		Write text to console only (always shown, even in quiet mode).
		Still writes to log file if logging is enabled.

		Args:
			text: Text to write
			end: Line ending (default: newline)
		"""
		# Always write to console
		print(text, end=end, flush=True)

		# Write to log file (strip ANSI codes for clean logs)
		if self.log_handle:
			clean_text = strip_ansi(text)
			self.log_handle.write(clean_text + end)
			self.log_handle.flush()

	def write_separator(self, char: str = "=", width: int = 80) -> None:
		"""Write a separator line."""
		self.write(char * width)

	def write_success(self, text: str) -> None:
		"""Write success message in green."""
		colored = colorize(text, ColorCodes.GREEN)
		self.write(colored)

	def write_error(self, text: str) -> None:
		"""Write error message in red."""
		colored = colorize(text, ColorCodes.RED)
		self.write(colored)

	def write_warning(self, text: str) -> None:
		"""Write warning message in yellow."""
		colored = colorize(text, ColorCodes.YELLOW)
		self.write(colored)

	def stream_process(self, process) -> tuple[int, str]:
		"""
		Stream output from a subprocess to console and log file.

		Uses a background thread to avoid blocking on I/O, which can hang
		on Windows when pytest buffers output.

		Args:
			process: subprocess.Popen instance with stdout=PIPE

		Returns:
			Tuple of (returncode, output_text)
		"""
		output_lines = []
		output_queue = queue.Queue()

		def read_output(stream, q):
			"""Read lines from stream and put them in queue."""
			try:
				for line in iter(stream.readline, ''):
					if not line:
						break
					q.put(line)
			except Exception as e:
				q.put(f"ERROR: {e}\n")
			finally:
				q.put(None) # Signal EOF

		# Start background thread to read output
		reader_thread = threading.Thread(
			target=read_output,
			args=(process.stdout, output_queue),
			daemon=True
		)
		reader_thread.start()

		# Process output from queue
		while True:
			try:
				# Wait for output with timeout to detect hangs
				line = output_queue.get(timeout=0.1)

				if line is None:
					# EOF signal
					break

				line = line.rstrip()
				self.write_line(line)
				output_lines.append(line)

			except queue.Empty:
				# No output available, check if process is still running
				if process.poll() is not None:
					# Process finished, drain remaining output
					while True:
						try:
							line = output_queue.get_nowait()
							if line is None:
								break
							line = line.rstrip()
							self.write_line(line)
							output_lines.append(line)
						except queue.Empty:
							break
					break

		# Wait for reader thread to finish (with timeout)
		reader_thread.join(timeout=5.0)

		# Close stdout and wait for process
		try:
			process.stdout.close()
		except Exception:
			pass

		returncode = process.wait()
		output = "\n".join(output_lines)

		return returncode, output

	def get_log_path(self) -> Path | None:
		"""Get the path to the log file."""
		return self.log_file

	def get_run_dir(self) -> Path | None:
		"""Get the path to the run directory (parent of full.log)."""
		return self.run_dir


@contextmanager
def tee_output(
	log_dir: str = ".logs",
	prefix: str = "log",
	project_name: str | None = None,
	project_root: Path | None = None,
):
	"""
	Context manager for tee-style output.

	Example:
	with tee_output(log_dir=".test_results", prefix="test") as logger:
	logger.write("Starting tests...")
	"""
	config = LogConfig(
		log_dir=log_dir,
		prefix=prefix,
		project_name=project_name,
	)
	logger = TeeLogger(config, project_root)
	try:
		yield logger.__enter__()
	finally:
		logger.__exit__(None, None, None)


def cleanup_old_logs(
	log_dir: Path,
	prefix: str,
	keep_count: int = 10,
	max_age_days: int | None = None,
) -> int:
	"""Clean up old log directories.

	Args:
		log_dir: Directory containing log directories
		prefix: Log directory prefix to match
		keep_count: Number of most recent directories to keep
		max_age_days: Maximum age of directories to keep (optional)

	Returns:
		Number of directories deleted
	"""
	if not log_dir.exists():
		return 0

	log_dirs = sorted(
		[d for d in log_dir.iterdir() if d.is_dir() and d.name.startswith(f"{prefix}-")],
		key=lambda d: d.stat().st_mtime,
		reverse=True,
	)

	deleted_count = 0

	# Delete based on count
	if len(log_dirs) > keep_count:
		for entry in log_dirs[keep_count:]:
			try:
				shutil.rmtree(entry)
				deleted_count += 1
			except OSError:
				pass

	# Delete based on age
	if max_age_days:
		max_age_seconds = max_age_days * 24 * 60 * 60
		current_time = time.time()

		for entry in log_dirs:
			if not entry.exists():
				continue
			try:
				age = current_time - entry.stat().st_mtime
				if age > max_age_seconds:
					shutil.rmtree(entry)
					deleted_count += 1
			except OSError:
				pass

	return deleted_count
