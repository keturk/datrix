"""Tests for DeployTestAggregateWriter.

Uses synthetic per-project index.json fixtures to validate cross-project
correlation, aggregate output generation, and edge cases.

No mocks, no fakes — real objects and real file I/O only.
"""

import json
from datetime import datetime
from pathlib import Path

import pytest

from shared.deploy_test_aggregate_writer import DeployTestAggregateWriter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_project_index_infrastructure() -> dict[str, object]:
    """Sample index.json for a project with Docker lifecycle failure."""
    return {
        "schema_version": 1,
        "project": "python/docker/02-features/03-infrastructure-blocks/cache",
        "project_path": "D:/datrix/.generated/python/docker/02-features/"
        "03-infrastructure-blocks/cache",
        "language": "python",
        "platform": "docker",
        "example": "02-features/03-infrastructure-blocks/cache",
        "result": "FAILED",
        "failed_phase": "docker-up",
        "phases": {
            "docker-build": {"result": "PASSED"},
            "docker-up": {
                "result": "FAILED",
                "error_message": "container unhealthy",
            },
            "spec-tests": {"result": "SKIPPED"},
            "integration-tests": {"result": "SKIPPED"},
        },
        "services": [],
        "failures": [],
        "errors": [
            {
                "id": 1,
                "phase": "docker-up",
                "error_type": "ContainerUnhealthy",
            },
        ],
        "failure_clusters": [],
        "error_clusters": [
            {
                "cluster_id": 1,
                "pattern": "ContainerUnhealthy: * is unhealthy",
                "phase": "docker-up",
                "count": 1,
                "codegen_hint": {
                    "probable_template": "docker-compose.yml.j2",
                },
            },
        ],
    }


@pytest.fixture
def sample_project_index_test_failure() -> dict[str, object]:
    """Sample index.json for a project with test failures."""
    return {
        "schema_version": 1,
        "project": "python/docker/01-foundation",
        "project_path": "D:/datrix/.generated/python/docker/01-foundation",
        "language": "python",
        "platform": "docker",
        "example": "01-foundation",
        "result": "FAILED",
        "failed_phase": "integration-tests",
        "phases": {
            "docker-build": {"result": "PASSED"},
            "docker-up": {"result": "PASSED"},
            "spec-tests": {"result": "PASSED"},
            "integration-tests": {
                "result": "FAILED",
                "counts": {"passed": 17, "failed": 2},
            },
        },
        "services": [
            {"name": "library_book_service", "integration_result": "FAILED"},
        ],
        "failures": [
            {
                "id": 1,
                "failure_type": "logic",
                "error_type": "AssertionError",
            },
            {
                "id": 2,
                "failure_type": "transient",
                "error_type": "ConnectionResetError",
            },
        ],
        "errors": [],
        "failure_clusters": [
            {
                "cluster_id": 1,
                "pattern": "AssertionError: assert * == "
                "response.status_code",
                "failure_type": "logic",
                "phase": "integration-tests",
                "count": 1,
            },
            {
                "cluster_id": 2,
                "pattern": "ConnectionResetError: *",
                "failure_type": "transient",
                "phase": "integration-tests",
                "count": 1,
            },
        ],
        "error_clusters": [],
    }


@pytest.fixture
def sample_project_index_passing() -> dict[str, object]:
    """Sample index.json for a passing project."""
    return {
        "schema_version": 1,
        "project": "python/docker/01-tutorial/01-basic-entity",
        "project_path": "D:/datrix/.generated/python/docker/"
        "01-tutorial/01-basic-entity",
        "language": "python",
        "platform": "docker",
        "example": "01-tutorial/01-basic-entity",
        "result": "PASSED",
        "failed_phase": None,
        "phases": {
            "docker-build": {"result": "PASSED"},
            "docker-up": {"result": "PASSED"},
            "spec-tests": {"result": "PASSED"},
            "integration-tests": {
                "result": "PASSED",
                "counts": {"passed": 20, "failed": 0},
            },
        },
        "failures": [],
        "errors": [],
        "failure_clusters": [],
        "error_clusters": [],
    }


def _write_project_index(
    tmp_path: Path,
    project_name: str,
    index_data: dict[str, object],
) -> Path:
    """Write a project index.json to a tmp directory and return its path."""
    proj_dir = (
        tmp_path / project_name / ".test_results" / "deploy-test-20260503"
    )
    proj_dir.mkdir(parents=True)
    index_path = proj_dir / "index.json"
    index_path.write_text(
        json.dumps(index_data, indent=2), encoding="utf-8"
    )
    return index_path


# ---------------------------------------------------------------------------
# Aggregate Output Schema Tests
# ---------------------------------------------------------------------------


class TestAggregateOutputSchema:
    """Test aggregate-index.json schema and field completeness."""

    def test_aggregate_index_has_required_fields(
        self,
        tmp_path: Path,
        sample_project_index_infrastructure: dict[str, object],
        sample_project_index_test_failure: dict[str, object],
        sample_project_index_passing: dict[str, object],
    ) -> None:
        """aggregate-index.json has all required top-level fields."""
        project_paths = [
            _write_project_index(
                tmp_path, "cache", sample_project_index_infrastructure
            ),
            _write_project_index(
                tmp_path, "foundation", sample_project_index_test_failure
            ),
            _write_project_index(
                tmp_path, "basic", sample_project_index_passing
            ),
        ]

        agg_dir = tmp_path / "aggregate"
        agg_dir.mkdir()

        writer = DeployTestAggregateWriter(
            aggregate_dir=agg_dir,
            language="python",
            platform="docker",
        )
        agg_path = writer.write(
            project_index_paths=project_paths,
            timestamp=datetime(2026, 5, 3, 21, 30, 16),
        )

        agg = json.loads(agg_path.read_text(encoding="utf-8"))

        required_fields = [
            "schema_version",
            "timestamp",
            "language",
            "platform",
            "total_projects",
            "projects_passed",
            "projects_failed",
            "total_counts",
            "failed_projects",
            "cross_project_clusters",
        ]
        for field_name in required_fields:
            assert field_name in agg, f"Missing field: {field_name}"

        assert agg["schema_version"] == 1
        assert agg["language"] == "python"
        assert agg["platform"] == "docker"

    def test_project_counts_correct(
        self,
        tmp_path: Path,
        sample_project_index_infrastructure: dict[str, object],
        sample_project_index_test_failure: dict[str, object],
        sample_project_index_passing: dict[str, object],
    ) -> None:
        """total_projects, projects_passed, projects_failed are correct."""
        project_paths = [
            _write_project_index(
                tmp_path, "cache", sample_project_index_infrastructure
            ),
            _write_project_index(
                tmp_path, "foundation", sample_project_index_test_failure
            ),
            _write_project_index(
                tmp_path, "basic", sample_project_index_passing
            ),
        ]

        agg_dir = tmp_path / "aggregate"
        agg_dir.mkdir()

        writer = DeployTestAggregateWriter(
            aggregate_dir=agg_dir,
            language="python",
            platform="docker",
        )
        agg_path = writer.write(
            project_index_paths=project_paths,
            timestamp=datetime(2026, 5, 3, 21, 30, 16),
        )

        agg = json.loads(agg_path.read_text(encoding="utf-8"))
        assert agg["total_projects"] == 3
        assert agg["projects_passed"] == 1
        assert agg["projects_failed"] == 2

    def test_infrastructure_failure_counted(
        self,
        tmp_path: Path,
        sample_project_index_infrastructure: dict[str, object],
        sample_project_index_passing: dict[str, object],
    ) -> None:
        """Infrastructure failures counted in total_counts."""
        project_paths = [
            _write_project_index(
                tmp_path, "cache", sample_project_index_infrastructure
            ),
            _write_project_index(
                tmp_path, "basic", sample_project_index_passing
            ),
        ]

        agg_dir = tmp_path / "aggregate"
        agg_dir.mkdir()

        writer = DeployTestAggregateWriter(
            aggregate_dir=agg_dir,
            language="python",
            platform="docker",
        )
        agg_path = writer.write(
            project_index_paths=project_paths,
            timestamp=datetime(2026, 5, 3, 21, 30, 16),
        )

        agg = json.loads(agg_path.read_text(encoding="utf-8"))
        assert agg["total_counts"]["infrastructure_failures"] == 1

    def test_failed_projects_array_populated(
        self,
        tmp_path: Path,
        sample_project_index_infrastructure: dict[str, object],
        sample_project_index_test_failure: dict[str, object],
    ) -> None:
        """failed_projects array has correct entries for failed projects."""
        project_paths = [
            _write_project_index(
                tmp_path, "cache", sample_project_index_infrastructure
            ),
            _write_project_index(
                tmp_path, "foundation", sample_project_index_test_failure
            ),
        ]

        agg_dir = tmp_path / "aggregate"
        agg_dir.mkdir()

        writer = DeployTestAggregateWriter(
            aggregate_dir=agg_dir,
            language="python",
            platform="docker",
        )
        agg_path = writer.write(
            project_index_paths=project_paths,
            timestamp=datetime(2026, 5, 3, 21, 30, 16),
        )

        agg = json.loads(agg_path.read_text(encoding="utf-8"))
        assert len(agg["failed_projects"]) == 2

        # Each failed project should have required fields
        for fp in agg["failed_projects"]:
            assert "project" in fp
            assert "failed_phase" in fp
            assert "counts" in fp
            assert "top_cluster_pattern" in fp


# ---------------------------------------------------------------------------
# Cross-Project Clustering Tests
# ---------------------------------------------------------------------------


class TestCrossProjectClusters:
    """Test cross-project cluster correlation."""

    def test_distinct_patterns_produce_separate_clusters(
        self,
        tmp_path: Path,
        sample_project_index_infrastructure: dict[str, object],
        sample_project_index_test_failure: dict[str, object],
    ) -> None:
        """Different error patterns produce separate cross-project clusters."""
        project_paths = [
            _write_project_index(
                tmp_path, "cache", sample_project_index_infrastructure
            ),
            _write_project_index(
                tmp_path, "foundation", sample_project_index_test_failure
            ),
        ]

        agg_dir = tmp_path / "aggregate"
        agg_dir.mkdir()

        writer = DeployTestAggregateWriter(
            aggregate_dir=agg_dir,
            language="python",
            platform="docker",
        )
        agg_path = writer.write(
            project_index_paths=project_paths,
            timestamp=datetime(2026, 5, 3, 21, 30, 16),
        )

        agg = json.loads(agg_path.read_text(encoding="utf-8"))
        # Infrastructure cluster + logic cluster + transient cluster = 3
        assert len(agg["cross_project_clusters"]) == 3

        # Each cluster has required fields
        for cluster in agg["cross_project_clusters"]:
            assert "cluster_id" in cluster
            assert "pattern" in cluster
            assert "phase" in cluster
            assert "failure_type" in cluster
            assert "projects_affected" in cluster
            assert "total_errors" in cluster

    def test_same_pattern_across_projects_merged(
        self,
        tmp_path: Path,
    ) -> None:
        """Same error pattern from two projects produces one cluster."""
        # Two projects with the same error pattern
        index_a: dict[str, object] = {
            "schema_version": 1,
            "project": "python/docker/project-a",
            "example": "project-a",
            "result": "FAILED",
            "failed_phase": "docker-up",
            "phases": {},
            "failures": [],
            "errors": [],
            "failure_clusters": [],
            "error_clusters": [
                {
                    "cluster_id": 1,
                    "pattern": "ContainerUnhealthy: * is unhealthy",
                    "phase": "docker-up",
                    "count": 1,
                },
            ],
        }

        index_b: dict[str, object] = {
            "schema_version": 1,
            "project": "python/docker/project-b",
            "example": "project-b",
            "result": "FAILED",
            "failed_phase": "docker-up",
            "phases": {},
            "failures": [],
            "errors": [],
            "failure_clusters": [],
            "error_clusters": [
                {
                    "cluster_id": 1,
                    "pattern": "ContainerUnhealthy: * is unhealthy",
                    "phase": "docker-up",
                    "count": 1,
                },
            ],
        }

        project_paths = [
            _write_project_index(tmp_path, "project-a", index_a),
            _write_project_index(tmp_path, "project-b", index_b),
        ]

        agg_dir = tmp_path / "aggregate"
        agg_dir.mkdir()

        writer = DeployTestAggregateWriter(
            aggregate_dir=agg_dir,
            language="python",
            platform="docker",
        )
        agg_path = writer.write(
            project_index_paths=project_paths,
            timestamp=datetime(2026, 5, 3, 21, 30, 16),
        )

        agg = json.loads(agg_path.read_text(encoding="utf-8"))
        # One pattern → one cluster
        assert len(agg["cross_project_clusters"]) == 1

        cluster = agg["cross_project_clusters"][0]
        assert sorted(cluster["projects_affected"]) == [
            "project-a",
            "project-b",
        ]
        assert cluster["total_errors"] == 2

    def test_passing_projects_not_in_clusters(
        self,
        tmp_path: Path,
        sample_project_index_passing: dict[str, object],
    ) -> None:
        """Passing projects don't contribute to cross-project clusters."""
        project_paths = [
            _write_project_index(
                tmp_path, "basic", sample_project_index_passing
            ),
        ]

        agg_dir = tmp_path / "aggregate"
        agg_dir.mkdir()

        writer = DeployTestAggregateWriter(
            aggregate_dir=agg_dir,
            language="python",
            platform="docker",
        )
        agg_path = writer.write(
            project_index_paths=project_paths,
            timestamp=datetime(2026, 5, 3, 21, 30, 16),
        )

        agg = json.loads(agg_path.read_text(encoding="utf-8"))
        assert len(agg["cross_project_clusters"]) == 0

    def test_cluster_failure_type_preserved(
        self,
        tmp_path: Path,
        sample_project_index_test_failure: dict[str, object],
    ) -> None:
        """Cluster failure_type (logic, transient, infrastructure) preserved."""
        project_paths = [
            _write_project_index(
                tmp_path, "foundation", sample_project_index_test_failure
            ),
        ]

        agg_dir = tmp_path / "aggregate"
        agg_dir.mkdir()

        writer = DeployTestAggregateWriter(
            aggregate_dir=agg_dir,
            language="python",
            platform="docker",
        )
        agg_path = writer.write(
            project_index_paths=project_paths,
            timestamp=datetime(2026, 5, 3, 21, 30, 16),
        )

        agg = json.loads(agg_path.read_text(encoding="utf-8"))
        failure_types = sorted(
            str(c["failure_type"])
            for c in agg["cross_project_clusters"]
        )
        assert "logic" in failure_types
        assert "transient" in failure_types


# ---------------------------------------------------------------------------
# Summary Text Tests
# ---------------------------------------------------------------------------


class TestAggregateSummary:
    """Test aggregate-summary.txt generation."""

    def test_summary_file_generated(
        self,
        tmp_path: Path,
        sample_project_index_infrastructure: dict[str, object],
        sample_project_index_passing: dict[str, object],
    ) -> None:
        """aggregate-summary.txt is generated."""
        project_paths = [
            _write_project_index(
                tmp_path, "cache", sample_project_index_infrastructure
            ),
            _write_project_index(
                tmp_path, "basic", sample_project_index_passing
            ),
        ]

        agg_dir = tmp_path / "aggregate"
        agg_dir.mkdir()

        writer = DeployTestAggregateWriter(
            aggregate_dir=agg_dir,
            language="python",
            platform="docker",
        )
        writer.write(
            project_index_paths=project_paths,
            timestamp=datetime(2026, 5, 3, 21, 30, 16),
        )

        summary = agg_dir / "aggregate-summary.txt"
        assert summary.exists()

    def test_summary_contains_infrastructure_section(
        self,
        tmp_path: Path,
        sample_project_index_infrastructure: dict[str, object],
        sample_project_index_passing: dict[str, object],
    ) -> None:
        """Summary contains INFRASTRUCTURE FAILURES section."""
        project_paths = [
            _write_project_index(
                tmp_path, "cache", sample_project_index_infrastructure
            ),
            _write_project_index(
                tmp_path, "basic", sample_project_index_passing
            ),
        ]

        agg_dir = tmp_path / "aggregate"
        agg_dir.mkdir()

        writer = DeployTestAggregateWriter(
            aggregate_dir=agg_dir,
            language="python",
            platform="docker",
        )
        writer.write(
            project_index_paths=project_paths,
            timestamp=datetime(2026, 5, 3, 21, 30, 16),
        )

        summary = agg_dir / "aggregate-summary.txt"
        content = summary.read_text(encoding="utf-8")
        assert "INFRASTRUCTURE FAILURES" in content
        assert "cache" in content

    def test_summary_contains_result_line(
        self,
        tmp_path: Path,
        sample_project_index_infrastructure: dict[str, object],
        sample_project_index_passing: dict[str, object],
    ) -> None:
        """Summary contains RESULT line with pass/total ratio."""
        project_paths = [
            _write_project_index(
                tmp_path, "cache", sample_project_index_infrastructure
            ),
            _write_project_index(
                tmp_path, "basic", sample_project_index_passing
            ),
        ]

        agg_dir = tmp_path / "aggregate"
        agg_dir.mkdir()

        writer = DeployTestAggregateWriter(
            aggregate_dir=agg_dir,
            language="python",
            platform="docker",
        )
        writer.write(
            project_index_paths=project_paths,
            timestamp=datetime(2026, 5, 3, 21, 30, 16),
        )

        summary = agg_dir / "aggregate-summary.txt"
        content = summary.read_text(encoding="utf-8")
        assert "RESULT:" in content
        assert "1/2" in content

    def test_summary_includes_passed_projects(
        self,
        tmp_path: Path,
        sample_project_index_passing: dict[str, object],
    ) -> None:
        """Summary includes PASSED PROJECTS section."""
        project_paths = [
            _write_project_index(
                tmp_path, "basic", sample_project_index_passing
            ),
        ]

        agg_dir = tmp_path / "aggregate"
        agg_dir.mkdir()

        writer = DeployTestAggregateWriter(
            aggregate_dir=agg_dir,
            language="python",
            platform="docker",
        )
        writer.write(
            project_index_paths=project_paths,
            timestamp=datetime(2026, 5, 3, 21, 30, 16),
        )

        summary = agg_dir / "aggregate-summary.txt"
        content = summary.read_text(encoding="utf-8")
        assert "PASSED PROJECTS" in content


# ---------------------------------------------------------------------------
# Edge Case Tests
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_input_produces_valid_aggregate(
        self,
        tmp_path: Path,
    ) -> None:
        """No project indices produces a valid minimal aggregate."""
        agg_dir = tmp_path / "aggregate"
        agg_dir.mkdir()

        writer = DeployTestAggregateWriter(
            aggregate_dir=agg_dir,
            language="python",
            platform="docker",
        )
        agg_path = writer.write(
            project_index_paths=[],
            timestamp=datetime(2026, 5, 3, 21, 30, 16),
        )

        agg = json.loads(agg_path.read_text(encoding="utf-8"))
        assert agg["total_projects"] == 0
        assert agg["projects_passed"] == 0
        assert agg["projects_failed"] == 0
        assert len(agg["cross_project_clusters"]) == 0

    def test_missing_index_file_skipped(
        self,
        tmp_path: Path,
        sample_project_index_passing: dict[str, object],
    ) -> None:
        """Missing index.json path is skipped without error."""
        valid_path = _write_project_index(
            tmp_path, "basic", sample_project_index_passing
        )
        missing_path = tmp_path / "nonexistent" / "index.json"

        agg_dir = tmp_path / "aggregate"
        agg_dir.mkdir()

        writer = DeployTestAggregateWriter(
            aggregate_dir=agg_dir,
            language="python",
            platform="docker",
        )
        agg_path = writer.write(
            project_index_paths=[valid_path, missing_path],
            timestamp=datetime(2026, 5, 3, 21, 30, 16),
        )

        agg = json.loads(agg_path.read_text(encoding="utf-8"))
        # Only the valid project should be counted
        assert agg["total_projects"] == 1
        assert agg["projects_passed"] == 1

    def test_corrupt_index_file_skipped(
        self,
        tmp_path: Path,
        sample_project_index_passing: dict[str, object],
    ) -> None:
        """Corrupt index.json is skipped without error."""
        valid_path = _write_project_index(
            tmp_path, "basic", sample_project_index_passing
        )

        # Write a corrupt index
        corrupt_dir = tmp_path / "corrupt" / ".test_results" / "deploy-test"
        corrupt_dir.mkdir(parents=True)
        corrupt_path = corrupt_dir / "index.json"
        corrupt_path.write_text("not valid json{{{", encoding="utf-8")

        agg_dir = tmp_path / "aggregate"
        agg_dir.mkdir()

        writer = DeployTestAggregateWriter(
            aggregate_dir=agg_dir,
            language="python",
            platform="docker",
        )
        agg_path = writer.write(
            project_index_paths=[valid_path, corrupt_path],
            timestamp=datetime(2026, 5, 3, 21, 30, 16),
        )

        agg = json.loads(agg_path.read_text(encoding="utf-8"))
        # Only the valid project should be counted
        assert agg["total_projects"] == 1

    def test_full_log_copied_when_provided(
        self,
        tmp_path: Path,
    ) -> None:
        """Full orchestration log is copied to aggregate dir when provided."""
        agg_dir = tmp_path / "aggregate"
        agg_dir.mkdir()

        # Create a fake full log
        log_file = tmp_path / "run-complete-output.log"
        log_file.write_text("full orchestration log content", encoding="utf-8")

        writer = DeployTestAggregateWriter(
            aggregate_dir=agg_dir,
            language="python",
            platform="docker",
        )
        writer.write(
            project_index_paths=[],
            timestamp=datetime(2026, 5, 3, 21, 30, 16),
            full_log_path=log_file,
        )

        copied_log = agg_dir / "full.log"
        assert copied_log.exists()
        assert (
            copied_log.read_text(encoding="utf-8")
            == "full orchestration log content"
        )

    def test_aggregate_dir_created_if_missing(
        self,
        tmp_path: Path,
    ) -> None:
        """Aggregate dir is created if it doesn't exist."""
        agg_dir = tmp_path / "deep" / "nested" / "aggregate"
        # Not created yet

        writer = DeployTestAggregateWriter(
            aggregate_dir=agg_dir,
            language="python",
            platform="docker",
        )
        agg_path = writer.write(
            project_index_paths=[],
            timestamp=datetime(2026, 5, 3, 21, 30, 16),
        )

        assert agg_path.exists()
        agg = json.loads(agg_path.read_text(encoding="utf-8"))
        assert agg["total_projects"] == 0
