"""Tests for directory-based TeeLogger changes.

Verifies that TeeLogger creates timestamped directories with full.log inside,
and that cleanup_old_logs handles both directories and legacy flat files.
"""

import os
import time
from pathlib import Path

import pytest

from shared.logging_utils import LogConfig, TeeLogger, cleanup_old_logs


class TestTeeLoggerDirectoryCreation:
	"""TeeLogger creates {prefix}-{timestamp}/full.log (not a flat file)."""

	def test_creates_directory_with_full_log(self, tmp_path: Path) -> None:
		"""TeeLogger creates a timestamped directory containing full.log."""
		config = LogConfig(
			log_dir=".test_results",
			prefix="test-results",
			project_name="test-project",
		)
		logger = TeeLogger(config, project_root=tmp_path)

		with logger:
			pass  # Just enter and exit

		log_dir = tmp_path / ".test_results"
		assert log_dir.exists()

		# Should have exactly one subdirectory matching the prefix pattern
		subdirs = [d for d in log_dir.iterdir() if d.is_dir()]
		assert len(subdirs) == 1

		run_dir = subdirs[0]
		assert run_dir.name.startswith("test-results-")

		# full.log should exist inside the run directory
		full_log = run_dir / "full.log"
		assert full_log.exists()
		assert full_log.is_file()

		# No flat .log files should exist in log_dir
		flat_logs = list(log_dir.glob("*.log"))
		assert len(flat_logs) == 0


class TestRunDirProperty:
	"""get_run_dir() returns the directory, get_log_path() returns full.log inside it."""

	def test_run_dir_and_log_path(self, tmp_path: Path) -> None:
		"""run_dir points to directory, log_file points to full.log inside it."""
		config = LogConfig(
			log_dir=".logs",
			prefix="run",
			project_name="test",
		)
		logger = TeeLogger(config, project_root=tmp_path)

		with logger:
			run_dir = logger.get_run_dir()
			log_path = logger.get_log_path()

			assert run_dir is not None
			assert log_path is not None
			assert run_dir.is_dir()
			assert log_path.name == "full.log"
			assert log_path.parent == run_dir

	def test_run_dir_is_none_before_enter(self, tmp_path: Path) -> None:
		"""run_dir is None before the context manager is entered."""
		config = LogConfig(log_dir=".logs", prefix="run")
		logger = TeeLogger(config, project_root=tmp_path)

		assert logger.get_run_dir() is None
		assert logger.get_log_path() is None

	def test_run_dir_when_save_to_file_disabled(self, tmp_path: Path) -> None:
		"""run_dir remains None when save_to_file is False."""
		config = LogConfig(log_dir=".logs", prefix="run", save_to_file=False)
		logger = TeeLogger(config, project_root=tmp_path)

		with logger:
			assert logger.get_run_dir() is None
			assert logger.get_log_path() is None


class TestLogContent:
	"""Content written via write() appears in full.log."""

	def test_write_content_appears_in_full_log(self, tmp_path: Path) -> None:
		"""Text written via write() is captured in full.log."""
		config = LogConfig(
			log_dir=".logs",
			prefix="content",
			project_name="test",
		)
		logger = TeeLogger(config, project_root=tmp_path)

		with logger:
			logger.write("Hello from test")
			logger.write_line("Second line")

		log_path = logger.get_log_path()
		assert log_path is not None
		content = log_path.read_text(encoding="utf-8")

		# Header should be present
		assert "test - content" in content
		assert "=" * 80 in content

		# Written content should be present
		assert "Hello from test" in content
		assert "Second line" in content


class TestCleanupDirectoriesOnly:
	"""Creates 15 directories, cleanup with keep_count=10 deletes 5 oldest."""

	def test_cleanup_keeps_most_recent(self, tmp_path: Path) -> None:
		"""cleanup_old_logs deletes oldest directories beyond keep_count."""
		log_dir = tmp_path / ".test_results"
		log_dir.mkdir()

		# Create 15 directories with staggered mtimes
		dirs: list[Path] = []
		for i in range(15):
			d = log_dir / f"test-results-202605{i:02d}-120000"
			d.mkdir()
			(d / "full.log").write_text(f"log {i}", encoding="utf-8")
			# Set mtime so they're ordered (oldest first)
			mtime = time.time() - (15 - i) * 3600
			os.utime(d, (mtime, mtime))
			dirs.append(d)

		deleted = cleanup_old_logs(log_dir, "test-results", keep_count=10)
		assert deleted == 5

		# The 10 most recent should survive
		remaining = sorted(
			[d for d in log_dir.iterdir() if d.is_dir()],
			key=lambda d: d.stat().st_mtime,
		)
		assert len(remaining) == 10

		# Oldest 5 should be gone
		for d in dirs[:5]:
			assert not d.exists()

		# Newest 10 should still exist
		for d in dirs[5:]:
			assert d.exists()


class TestCleanupMixedLegacy:
	"""Cleanup handles mix of old flat files and new directories."""

	def test_cleanup_mixed_entries(self, tmp_path: Path) -> None:
		"""cleanup_old_logs handles both directories and flat .log files, sorted by mtime."""
		log_dir = tmp_path / ".test_results"
		log_dir.mkdir()

		base_time = time.time()

		# Create 5 legacy flat files (oldest)
		for i in range(5):
			f = log_dir / f"test-results-202604{i:02d}-120000.log"
			f.write_text(f"legacy log {i}", encoding="utf-8")
			mtime = base_time - (10 - i) * 3600  # oldest
			os.utime(f, (mtime, mtime))

		# Create 5 new directories (newest)
		for i in range(5):
			d = log_dir / f"test-results-202605{i:02d}-120000"
			d.mkdir()
			(d / "full.log").write_text(f"log {i}", encoding="utf-8")
			mtime = base_time - (4 - i) * 3600  # newest
			os.utime(d, (mtime, mtime))

		# keep_count=6 should keep the 6 most recent (5 dirs + 1 newest file)
		deleted = cleanup_old_logs(log_dir, "test-results", keep_count=6)
		assert deleted == 4

		# All 5 directories should survive (they're newest)
		remaining_dirs = [d for d in log_dir.iterdir() if d.is_dir()]
		assert len(remaining_dirs) == 5

		# Only 1 legacy file should survive (the newest one)
		remaining_files = list(log_dir.glob("test-results-*.log"))
		assert len(remaining_files) == 1


class TestCleanupAgeBased:
	"""Cleanup with max_age_days deletes old directories."""

	def test_age_based_deletion(self, tmp_path: Path) -> None:
		"""cleanup_old_logs deletes entries older than max_age_days."""
		log_dir = tmp_path / ".test_results"
		log_dir.mkdir()

		base_time = time.time()

		# Create 3 recent directories (1 hour old)
		for i in range(3):
			d = log_dir / f"test-results-recent-{i}"
			d.mkdir()
			(d / "full.log").write_text(f"recent {i}", encoding="utf-8")
			mtime = base_time - 3600  # 1 hour ago
			os.utime(d, (mtime, mtime))

		# Create 3 old directories (40 days old)
		for i in range(3):
			d = log_dir / f"test-results-old-{i}"
			d.mkdir()
			(d / "full.log").write_text(f"old {i}", encoding="utf-8")
			mtime = base_time - (40 * 24 * 3600)  # 40 days ago
			os.utime(d, (mtime, mtime))

		deleted = cleanup_old_logs(
			log_dir, "test-results", keep_count=100, max_age_days=30
		)
		assert deleted == 3

		# Recent directories should survive
		remaining = [d for d in log_dir.iterdir() if d.is_dir()]
		assert len(remaining) == 3
		for d in remaining:
			assert "recent" in d.name

	def test_nonexistent_log_dir(self, tmp_path: Path) -> None:
		"""cleanup_old_logs returns 0 for nonexistent directory."""
		deleted = cleanup_old_logs(tmp_path / "nonexistent", "test", keep_count=5)
		assert deleted == 0


class TestContextManager:
	"""with TeeLogger(...) creates directory on enter, closes file on exit."""

	def test_context_manager_lifecycle(self, tmp_path: Path) -> None:
		"""Context manager creates directory on enter and closes file on exit."""
		config = LogConfig(
			log_dir=".logs",
			prefix="ctx",
			project_name="test",
		)
		logger = TeeLogger(config, project_root=tmp_path)

		# Before enter: no directory
		assert logger.run_dir is None

		with logger:
			# During: directory and file exist, handle is open
			assert logger.run_dir is not None
			assert logger.run_dir.is_dir()
			assert logger.log_file is not None
			assert logger.log_file.exists()
			assert logger.log_handle is not None
			assert not logger.log_handle.closed

			# Write something to confirm it works
			logger.write("inside context")

		# After exit: file handle is closed but paths are still set
		assert logger.log_handle is not None
		assert logger.log_handle.closed

		# Content should be readable
		content = logger.log_file.read_text(encoding="utf-8")
		assert "inside context" in content
