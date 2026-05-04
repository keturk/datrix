"""Tests for AggregateTestWriter.

Tests verify:
- Reading multiple project index.json files
- Cross-project cluster correlation
- Suite failure clustering (separate from error clusters)
- aggregate-index.json schema compliance
- aggregate-summary.txt format compliance
- Representative project selection
- All-passing scenario
- Mixed scenario handling
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from shared.aggregate_test_writer import (
    AggregateTestWriter,
    CrossProjectCluster,
    ProjectSummary,
    SuiteFailureCluster,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_index_json(
    tmp_path: Path,
    project: str,
    example: str,
    result: str,
    counts: dict[str, int],
    error_clusters: list[dict] | None = None,
    failure_clusters: list[dict] | None = None,
    services: list[dict] | None = None,
    errors: list[dict] | None = None,
    failures: list[dict] | None = None,
) -> Path:
    """Create a per-project index.json file and return its path."""
    project_dir = tmp_path / project.replace("/", "_")
    project_dir.mkdir(parents=True, exist_ok=True)

    data = {
        "schema_version": 1,
        "project": project,
        "project_path": str(project_dir),
        "language": "python",
        "platform": "docker",
        "example": example,
        "dtrx_source": f"datrix/examples/{example}/system.dtrx",
        "timestamp": "2026-05-03T21:04:22",
        "duration_seconds": 5.0,
        "result": result,
        "counts": counts,
        "services": services or [],
        "failures": failures or [],
        "errors": errors or [],
        "failure_clusters": failure_clusters or [],
        "error_clusters": error_clusters or [],
    }

    index_path = project_dir / "index.json"
    index_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return index_path


def _passing_counts() -> dict[str, int]:
    """Return counts for a passing project."""
    return {
        "passed": 20,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
        "suite_failures": 0,
    }


def _failing_counts(passed: int = 5, errors: int = 3) -> dict[str, int]:
    """Return counts for a failing project with errors."""
    return {
        "passed": passed,
        "failed": 0,
        "errors": errors,
        "skipped": 0,
        "suite_failures": 0,
    }


def _suite_failure_counts(passed: int = 0) -> dict[str, int]:
    """Return counts for a project with suite failures."""
    return {
        "passed": passed,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
        "suite_failures": 1,
    }


def _create_aggregate_writer(tmp_path: Path) -> AggregateTestWriter:
    """Create an AggregateTestWriter with standard test parameters."""
    output_dir = tmp_path / "aggregate"
    return AggregateTestWriter(
        language="python",
        platform="docker",
        output_dir=output_dir,
    )


# ---------------------------------------------------------------------------
# Tests — Cross-Project Correlation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCrossProjectCorrelation:
    """Test cross-project error cluster correlation."""

    def test_same_pattern_correlated(self, tmp_path: Path) -> None:
        """Identical normalized patterns across projects form one cross-project cluster."""
        # Two projects with the same error cluster pattern
        pattern = "ImportError: cannot import name * from *"
        idx1 = _make_index_json(
            tmp_path,
            project="python/docker/01-tutorial/proj-a",
            example="01-tutorial/proj-a",
            result="FAILED",
            counts=_failing_counts(errors=3),
            error_clusters=[{
                "cluster_id": 1,
                "pattern": pattern,
                "generated_file": "src/svc/integrations/_email_helpers.py",
                "count": 3,
                "services_affected": ["svc_a"],
                "error_ids": [1, 2, 3],
                "representative_error_id": 1,
                "codegen_hint": {
                    "probable_template": "integration_helpers.py.j2",
                    "probable_generator": "IntegrationGenerator",
                },
            }],
        )
        idx2 = _make_index_json(
            tmp_path,
            project="python/docker/01-tutorial/proj-b",
            example="01-tutorial/proj-b",
            result="FAILED",
            counts=_failing_counts(errors=2),
            error_clusters=[{
                "cluster_id": 1,
                "pattern": pattern,
                "generated_file": "src/svc/integrations/_email_helpers.py",
                "count": 2,
                "services_affected": ["svc_b"],
                "error_ids": [1, 2],
                "representative_error_id": 1,
                "codegen_hint": {
                    "probable_template": "integration_helpers.py.j2",
                    "probable_generator": "IntegrationGenerator",
                },
            }],
        )

        writer = _create_aggregate_writer(tmp_path)
        writer.add_project_results(idx1)
        writer.add_project_results(idx2)
        agg_path = writer.write()

        agg = json.loads(agg_path.read_text(encoding="utf-8"))
        assert len(agg["cross_project_clusters"]) == 1
        cluster = agg["cross_project_clusters"][0]
        assert cluster["pattern"] == pattern
        assert sorted(cluster["projects_affected"]) == [
            "01-tutorial/proj-a",
            "01-tutorial/proj-b",
        ]
        assert cluster["total_errors"] == 5

    def test_different_patterns_not_correlated(self, tmp_path: Path) -> None:
        """Different patterns remain separate cross-project clusters."""
        idx1 = _make_index_json(
            tmp_path,
            project="python/docker/proj-a",
            example="proj-a",
            result="FAILED",
            counts=_failing_counts(errors=2),
            error_clusters=[{
                "cluster_id": 1,
                "pattern": "ImportError: cannot import name * from *",
                "generated_file": None,
                "count": 2,
                "services_affected": ["svc"],
                "error_ids": [1, 2],
                "representative_error_id": 1,
                "codegen_hint": None,
            }],
        )
        idx2 = _make_index_json(
            tmp_path,
            project="python/docker/proj-b",
            example="proj-b",
            result="FAILED",
            counts=_failing_counts(errors=1),
            error_clusters=[{
                "cluster_id": 1,
                "pattern": "TypeError: expected * got *",
                "generated_file": None,
                "count": 1,
                "services_affected": ["svc"],
                "error_ids": [1],
                "representative_error_id": 1,
                "codegen_hint": None,
            }],
        )

        writer = _create_aggregate_writer(tmp_path)
        writer.add_project_results(idx1)
        writer.add_project_results(idx2)
        agg_path = writer.write()

        agg = json.loads(agg_path.read_text(encoding="utf-8"))
        assert len(agg["cross_project_clusters"]) == 2
        patterns = {c["pattern"] for c in agg["cross_project_clusters"]}
        assert "ImportError: cannot import name * from *" in patterns
        assert "TypeError: expected * got *" in patterns

    def test_representative_project_highest_count(self, tmp_path: Path) -> None:
        """Representative project is the one with the most errors for that cluster."""
        pattern = "ImportError: cannot import name * from *"
        idx1 = _make_index_json(
            tmp_path,
            project="python/docker/proj-a",
            example="proj-a",
            result="FAILED",
            counts=_failing_counts(errors=10),
            error_clusters=[{
                "cluster_id": 1,
                "pattern": pattern,
                "generated_file": None,
                "count": 10,
                "services_affected": ["svc"],
                "error_ids": list(range(1, 11)),
                "representative_error_id": 1,
                "codegen_hint": None,
            }],
        )
        idx2 = _make_index_json(
            tmp_path,
            project="python/docker/proj-b",
            example="proj-b",
            result="FAILED",
            counts=_failing_counts(errors=3),
            error_clusters=[{
                "cluster_id": 1,
                "pattern": pattern,
                "generated_file": None,
                "count": 3,
                "services_affected": ["svc"],
                "error_ids": [1, 2, 3],
                "representative_error_id": 1,
                "codegen_hint": None,
            }],
        )

        writer = _create_aggregate_writer(tmp_path)
        writer.add_project_results(idx1)
        writer.add_project_results(idx2)
        agg_path = writer.write()

        agg = json.loads(agg_path.read_text(encoding="utf-8"))
        cluster = agg["cross_project_clusters"][0]
        assert cluster["representative_project"] == "proj-a"

    def test_representative_project_alphabetical_tiebreak(self, tmp_path: Path) -> None:
        """When counts are tied, representative is alphabetically first."""
        pattern = "ImportError: cannot import name * from *"
        idx1 = _make_index_json(
            tmp_path,
            project="python/docker/proj-b",
            example="proj-b",
            result="FAILED",
            counts=_failing_counts(errors=5),
            error_clusters=[{
                "cluster_id": 1,
                "pattern": pattern,
                "generated_file": None,
                "count": 5,
                "services_affected": ["svc"],
                "error_ids": list(range(1, 6)),
                "representative_error_id": 1,
                "codegen_hint": None,
            }],
        )
        idx2 = _make_index_json(
            tmp_path,
            project="python/docker/proj-a",
            example="proj-a",
            result="FAILED",
            counts=_failing_counts(errors=5),
            error_clusters=[{
                "cluster_id": 1,
                "pattern": pattern,
                "generated_file": None,
                "count": 5,
                "services_affected": ["svc"],
                "error_ids": list(range(1, 6)),
                "representative_error_id": 1,
                "codegen_hint": None,
            }],
        )

        writer = _create_aggregate_writer(tmp_path)
        writer.add_project_results(idx1)
        writer.add_project_results(idx2)
        agg_path = writer.write()

        agg = json.loads(agg_path.read_text(encoding="utf-8"))
        cluster = agg["cross_project_clusters"][0]
        assert cluster["representative_project"] == "proj-a"

    def test_codegen_hint_propagated(self, tmp_path: Path) -> None:
        """Codegen hint from per-project cluster is propagated to cross-project cluster."""
        pattern = "ImportError: cannot import name * from *"
        hint = {
            "probable_template": "integration_helpers.py.j2",
            "probable_generator": "IntegrationGenerator",
        }
        idx1 = _make_index_json(
            tmp_path,
            project="python/docker/proj-a",
            example="proj-a",
            result="FAILED",
            counts=_failing_counts(errors=2),
            error_clusters=[{
                "cluster_id": 1,
                "pattern": pattern,
                "generated_file": None,
                "count": 2,
                "services_affected": ["svc"],
                "error_ids": [1, 2],
                "representative_error_id": 1,
                "codegen_hint": hint,
            }],
        )

        writer = _create_aggregate_writer(tmp_path)
        writer.add_project_results(idx1)
        agg_path = writer.write()

        agg = json.loads(agg_path.read_text(encoding="utf-8"))
        cluster = agg["cross_project_clusters"][0]
        assert cluster["codegen_hint"] is not None
        assert cluster["codegen_hint"]["probable_template"] == "integration_helpers.py.j2"
        assert cluster["codegen_hint"]["probable_generator"] == "IntegrationGenerator"

    def test_failure_clusters_also_correlated(self, tmp_path: Path) -> None:
        """Failure clusters (not just error clusters) are correlated across projects."""
        pattern = "AssertionError: assert * == *"
        idx1 = _make_index_json(
            tmp_path,
            project="python/docker/proj-a",
            example="proj-a",
            result="FAILED",
            counts={"passed": 3, "failed": 2, "errors": 0, "skipped": 0, "suite_failures": 0},
            failure_clusters=[{
                "cluster_id": 1,
                "pattern": pattern,
                "generated_file": None,
                "count": 2,
                "services_affected": ["svc"],
                "error_ids": [1, 2],
                "representative_error_id": 1,
                "codegen_hint": None,
            }],
        )
        idx2 = _make_index_json(
            tmp_path,
            project="python/docker/proj-b",
            example="proj-b",
            result="FAILED",
            counts={"passed": 5, "failed": 1, "errors": 0, "skipped": 0, "suite_failures": 0},
            failure_clusters=[{
                "cluster_id": 1,
                "pattern": pattern,
                "generated_file": None,
                "count": 1,
                "services_affected": ["svc"],
                "error_ids": [1],
                "representative_error_id": 1,
                "codegen_hint": None,
            }],
        )

        writer = _create_aggregate_writer(tmp_path)
        writer.add_project_results(idx1)
        writer.add_project_results(idx2)
        agg_path = writer.write()

        agg = json.loads(agg_path.read_text(encoding="utf-8"))
        # Failure clusters appear in cross_project_clusters
        assert len(agg["cross_project_clusters"]) == 1
        cluster = agg["cross_project_clusters"][0]
        assert cluster["pattern"] == pattern
        assert cluster["total_errors"] == 3


# ---------------------------------------------------------------------------
# Tests — Suite Failure Clusters
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSuiteFailureClusters:
    """Test suite failure clustering (separate from error/failure clusters)."""

    def test_suite_failures_clustered_separately(self, tmp_path: Path) -> None:
        """Suite failures form their own cluster type in aggregate."""
        idx1 = _make_index_json(
            tmp_path,
            project="python/docker/proj-a",
            example="proj-a",
            result="FAILED",
            counts=_suite_failure_counts(),
            services=[{
                "name": "svc",
                "result": "FAILED",
                "counts": _suite_failure_counts(),
                "log_file": "services/svc/service.log",
                "suite_failure_message": "Cannot find module 'express'",
            }],
        )
        idx2 = _make_index_json(
            tmp_path,
            project="python/docker/proj-b",
            example="proj-b",
            result="FAILED",
            counts=_suite_failure_counts(),
            services=[{
                "name": "svc",
                "result": "FAILED",
                "counts": _suite_failure_counts(),
                "log_file": "services/svc/service.log",
                "suite_failure_message": "Cannot find module 'express'",
            }],
        )

        writer = _create_aggregate_writer(tmp_path)
        writer.add_project_results(idx1)
        writer.add_project_results(idx2)
        agg_path = writer.write()

        agg = json.loads(agg_path.read_text(encoding="utf-8"))
        assert len(agg["suite_failure_clusters"]) == 1
        sfc = agg["suite_failure_clusters"][0]
        assert "Cannot find module" in sfc["pattern"]
        assert sorted(sfc["projects_affected"]) == ["proj-a", "proj-b"]
        assert sfc["total_suite_failures"] == 2

    def test_top_cluster_pattern_null_for_suite_only(self, tmp_path: Path) -> None:
        """Projects with only suite failures have top_cluster_pattern=null."""
        idx = _make_index_json(
            tmp_path,
            project="python/docker/proj-a",
            example="proj-a",
            result="FAILED",
            counts=_suite_failure_counts(),
            services=[{
                "name": "svc",
                "result": "FAILED",
                "counts": _suite_failure_counts(),
                "log_file": "services/svc/service.log",
                "suite_failure_message": "Cannot find module 'express'",
            }],
        )

        writer = _create_aggregate_writer(tmp_path)
        writer.add_project_results(idx)
        agg_path = writer.write()

        agg = json.loads(agg_path.read_text(encoding="utf-8"))
        # The failed project should have top_cluster_pattern=null since no error clusters
        failed_proj = agg["failed_projects"][0]
        assert failed_proj["top_cluster_pattern"] is None
        assert "suite_failure_message" in failed_proj

    def test_different_suite_failure_messages_separate_clusters(
        self, tmp_path: Path
    ) -> None:
        """Different suite failure messages form separate clusters."""
        idx1 = _make_index_json(
            tmp_path,
            project="python/docker/proj-a",
            example="proj-a",
            result="FAILED",
            counts=_suite_failure_counts(),
            services=[{
                "name": "svc",
                "result": "FAILED",
                "counts": _suite_failure_counts(),
                "log_file": "services/svc/service.log",
                "suite_failure_message": "Cannot find module 'express'",
            }],
        )
        idx2 = _make_index_json(
            tmp_path,
            project="python/docker/proj-b",
            example="proj-b",
            result="FAILED",
            counts=_suite_failure_counts(),
            services=[{
                "name": "svc",
                "result": "FAILED",
                "counts": _suite_failure_counts(),
                "log_file": "services/svc/service.log",
                "suite_failure_message": "SyntaxError: Unexpected token",
            }],
        )

        writer = _create_aggregate_writer(tmp_path)
        writer.add_project_results(idx1)
        writer.add_project_results(idx2)
        agg_path = writer.write()

        agg = json.loads(agg_path.read_text(encoding="utf-8"))
        assert len(agg["suite_failure_clusters"]) == 2


# ---------------------------------------------------------------------------
# Tests — aggregate-index.json Schema Compliance
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAggregateIndexJson:
    """Test aggregate-index.json schema compliance."""

    def test_schema_version_present(self, tmp_path: Path) -> None:
        """aggregate-index.json has schema_version: 1."""
        idx = _make_index_json(
            tmp_path,
            project="python/docker/proj-a",
            example="proj-a",
            result="PASSED",
            counts=_passing_counts(),
        )

        writer = _create_aggregate_writer(tmp_path)
        writer.add_project_results(idx)
        agg_path = writer.write()

        agg = json.loads(agg_path.read_text(encoding="utf-8"))
        assert agg["schema_version"] == 1

    def test_all_required_fields_present(self, tmp_path: Path) -> None:
        """All fields from design doc schema are present."""
        pattern = "ImportError: cannot import name * from *"
        idx1 = _make_index_json(
            tmp_path,
            project="python/docker/proj-a",
            example="proj-a",
            result="FAILED",
            counts=_failing_counts(),
            error_clusters=[{
                "cluster_id": 1,
                "pattern": pattern,
                "generated_file": None,
                "count": 3,
                "services_affected": ["svc"],
                "error_ids": [1, 2, 3],
                "representative_error_id": 1,
                "codegen_hint": None,
            }],
        )
        idx2 = _make_index_json(
            tmp_path,
            project="python/docker/proj-b",
            example="proj-b",
            result="PASSED",
            counts=_passing_counts(),
        )

        writer = _create_aggregate_writer(tmp_path)
        writer.add_project_results(idx1)
        writer.add_project_results(idx2)
        agg_path = writer.write()

        agg = json.loads(agg_path.read_text(encoding="utf-8"))

        # Top-level required keys from design doc
        required_keys = [
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
            "suite_failure_clusters",
        ]
        for key in required_keys:
            assert key in agg, f"Missing required key: {key}"

        # total_counts keys
        counts_keys = ["passed", "failed", "errors", "skipped", "suite_failures"]
        for key in counts_keys:
            assert key in agg["total_counts"], f"Missing total_counts key: {key}"

        # cross_project_clusters entry keys
        if agg["cross_project_clusters"]:
            cpc_keys = [
                "cluster_id",
                "pattern",
                "projects_affected",
                "total_errors",
                "codegen_hint",
                "representative_project",
            ]
            for key in cpc_keys:
                assert key in agg["cross_project_clusters"][0], (
                    f"Missing cross_project_clusters key: {key}"
                )

        # failed_projects entry keys
        if agg["failed_projects"]:
            fp_keys = [
                "project",
                "example",
                "result_dir",
                "counts",
                "top_cluster_pattern",
            ]
            for key in fp_keys:
                assert key in agg["failed_projects"][0], (
                    f"Missing failed_projects key: {key}"
                )

    def test_passing_projects_counted_not_listed(self, tmp_path: Path) -> None:
        """Passing projects contribute to total_projects/projects_passed but not failed_projects."""
        idx1 = _make_index_json(
            tmp_path,
            project="python/docker/proj-pass",
            example="proj-pass",
            result="PASSED",
            counts=_passing_counts(),
        )
        idx2 = _make_index_json(
            tmp_path,
            project="python/docker/proj-fail",
            example="proj-fail",
            result="FAILED",
            counts=_failing_counts(),
        )

        writer = _create_aggregate_writer(tmp_path)
        writer.add_project_results(idx1)
        writer.add_project_results(idx2)
        agg_path = writer.write()

        agg = json.loads(agg_path.read_text(encoding="utf-8"))
        assert agg["total_projects"] == 2
        assert agg["projects_passed"] == 1
        assert agg["projects_failed"] == 1
        assert len(agg["failed_projects"]) == 1
        assert agg["failed_projects"][0]["example"] == "proj-fail"

    def test_total_counts_aggregated(self, tmp_path: Path) -> None:
        """Total counts are the sum across all projects."""
        idx1 = _make_index_json(
            tmp_path,
            project="python/docker/proj-a",
            example="proj-a",
            result="PASSED",
            counts={"passed": 10, "failed": 0, "errors": 0, "skipped": 2, "suite_failures": 0},
        )
        idx2 = _make_index_json(
            tmp_path,
            project="python/docker/proj-b",
            example="proj-b",
            result="FAILED",
            counts={"passed": 5, "failed": 1, "errors": 3, "skipped": 0, "suite_failures": 0},
        )

        writer = _create_aggregate_writer(tmp_path)
        writer.add_project_results(idx1)
        writer.add_project_results(idx2)
        agg_path = writer.write()

        agg = json.loads(agg_path.read_text(encoding="utf-8"))
        assert agg["total_counts"]["passed"] == 15
        assert agg["total_counts"]["failed"] == 1
        assert agg["total_counts"]["errors"] == 3
        assert agg["total_counts"]["skipped"] == 2
        assert agg["total_counts"]["suite_failures"] == 0

    def test_all_passing_scenario(self, tmp_path: Path) -> None:
        """When all projects pass, no failed_projects or clusters."""
        idx1 = _make_index_json(
            tmp_path,
            project="python/docker/proj-a",
            example="proj-a",
            result="PASSED",
            counts=_passing_counts(),
        )
        idx2 = _make_index_json(
            tmp_path,
            project="python/docker/proj-b",
            example="proj-b",
            result="PASSED",
            counts=_passing_counts(),
        )

        writer = _create_aggregate_writer(tmp_path)
        writer.add_project_results(idx1)
        writer.add_project_results(idx2)
        agg_path = writer.write()

        agg = json.loads(agg_path.read_text(encoding="utf-8"))
        assert agg["total_projects"] == 2
        assert agg["projects_passed"] == 2
        assert agg["projects_failed"] == 0
        assert len(agg["failed_projects"]) == 0
        assert len(agg["cross_project_clusters"]) == 0
        assert len(agg["suite_failure_clusters"]) == 0


# ---------------------------------------------------------------------------
# Tests — aggregate-summary.txt Format
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAggregateSummaryTxt:
    """Test aggregate-summary.txt format."""

    def test_format_matches_design_doc(self, tmp_path: Path) -> None:
        """aggregate-summary.txt has correct header and structure."""
        pattern = "ImportError: cannot import name * from *"
        idx1 = _make_index_json(
            tmp_path,
            project="python/docker/proj-a",
            example="proj-a",
            result="FAILED",
            counts=_failing_counts(passed=5, errors=3),
            error_clusters=[{
                "cluster_id": 1,
                "pattern": pattern,
                "generated_file": None,
                "count": 3,
                "services_affected": ["svc"],
                "error_ids": [1, 2, 3],
                "representative_error_id": 1,
                "codegen_hint": {
                    "probable_template": "integration_helpers.py.j2",
                    "probable_generator": "IntegrationGenerator",
                },
            }],
        )
        idx2 = _make_index_json(
            tmp_path,
            project="python/docker/proj-pass",
            example="proj-pass",
            result="PASSED",
            counts=_passing_counts(),
        )

        writer = _create_aggregate_writer(tmp_path)
        writer.add_project_results(idx1)
        writer.add_project_results(idx2)
        writer.write()

        summary_path = tmp_path / "aggregate" / "aggregate-summary.txt"
        assert summary_path.exists()
        content = summary_path.read_text(encoding="utf-8")

        # Check header
        assert "Generated Project Unit Tests" in content
        assert "Cross-Project Summary" in content

        # Check result line
        assert "RESULT: 1/2 projects passed" in content

        # Check cluster section
        assert "CROSS-PROJECT CLUSTERS:" in content
        assert pattern in content
        assert "Probable template:" in content

        # Check failed projects section
        assert "FAILED PROJECTS:" in content
        assert "proj-a" in content

    def test_all_passing_summary_no_clusters(self, tmp_path: Path) -> None:
        """All-passing summary has no CROSS-PROJECT CLUSTERS section."""
        idx1 = _make_index_json(
            tmp_path,
            project="python/docker/proj-a",
            example="proj-a",
            result="PASSED",
            counts=_passing_counts(),
        )

        writer = _create_aggregate_writer(tmp_path)
        writer.add_project_results(idx1)
        writer.write()

        summary_path = tmp_path / "aggregate" / "aggregate-summary.txt"
        content = summary_path.read_text(encoding="utf-8")

        assert "RESULT: 1/1 projects passed" in content
        assert "CROSS-PROJECT CLUSTERS:" not in content
        assert "FAILED PROJECTS:" not in content

    def test_suite_failure_clusters_in_summary(self, tmp_path: Path) -> None:
        """Suite failure clusters appear in summary."""
        idx = _make_index_json(
            tmp_path,
            project="python/docker/proj-a",
            example="proj-a",
            result="FAILED",
            counts=_suite_failure_counts(),
            services=[{
                "name": "svc",
                "result": "FAILED",
                "counts": _suite_failure_counts(),
                "log_file": "services/svc/service.log",
                "suite_failure_message": "Cannot find module 'express'",
            }],
        )

        writer = _create_aggregate_writer(tmp_path)
        writer.add_project_results(idx)
        writer.write()

        summary_path = tmp_path / "aggregate" / "aggregate-summary.txt"
        content = summary_path.read_text(encoding="utf-8")

        assert "SUITE FAILURE CLUSTERS:" in content
        assert "Cannot find module" in content


# ---------------------------------------------------------------------------
# Tests — add_project_results Validation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAddProjectResults:
    """Test add_project_results input validation."""

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        """FileNotFoundError raised for non-existent index.json."""
        writer = _create_aggregate_writer(tmp_path)
        with pytest.raises(FileNotFoundError, match="index.json not found"):
            writer.add_project_results(tmp_path / "nonexistent" / "index.json")

    def test_invalid_json_raises(self, tmp_path: Path) -> None:
        """JSONDecodeError raised for invalid JSON."""
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not valid json {{{", encoding="utf-8")
        writer = _create_aggregate_writer(tmp_path)
        with pytest.raises(json.JSONDecodeError):
            writer.add_project_results(bad_file)


# ---------------------------------------------------------------------------
# Tests — Mixed Scenarios
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMixedScenarios:
    """Test combined error + suite failure scenarios."""

    def test_mixed_errors_and_suite_failures(self, tmp_path: Path) -> None:
        """Project with both errors and suite failures is correctly aggregated."""
        idx1 = _make_index_json(
            tmp_path,
            project="python/docker/proj-errors",
            example="proj-errors",
            result="FAILED",
            counts=_failing_counts(passed=5, errors=3),
            error_clusters=[{
                "cluster_id": 1,
                "pattern": "ImportError: cannot import name * from *",
                "generated_file": None,
                "count": 3,
                "services_affected": ["svc"],
                "error_ids": [1, 2, 3],
                "representative_error_id": 1,
                "codegen_hint": None,
            }],
        )
        idx2 = _make_index_json(
            tmp_path,
            project="python/docker/proj-suite",
            example="proj-suite",
            result="FAILED",
            counts=_suite_failure_counts(),
            services=[{
                "name": "svc",
                "result": "FAILED",
                "counts": _suite_failure_counts(),
                "log_file": "services/svc/service.log",
                "suite_failure_message": "Cannot find module 'express'",
            }],
        )
        idx3 = _make_index_json(
            tmp_path,
            project="python/docker/proj-pass",
            example="proj-pass",
            result="PASSED",
            counts=_passing_counts(),
        )

        writer = _create_aggregate_writer(tmp_path)
        writer.add_project_results(idx1)
        writer.add_project_results(idx2)
        writer.add_project_results(idx3)
        agg_path = writer.write()

        agg = json.loads(agg_path.read_text(encoding="utf-8"))
        assert agg["total_projects"] == 3
        assert agg["projects_passed"] == 1
        assert agg["projects_failed"] == 2
        assert len(agg["cross_project_clusters"]) == 1
        assert len(agg["suite_failure_clusters"]) == 1
        # Total counts should sum all three
        assert agg["total_counts"]["passed"] == 25  # 5 + 0 + 20
        assert agg["total_counts"]["errors"] == 3
        assert agg["total_counts"]["suite_failures"] == 1

    def test_single_project_aggregate(self, tmp_path: Path) -> None:
        """Aggregate with just one project works correctly."""
        idx = _make_index_json(
            tmp_path,
            project="python/docker/proj-only",
            example="proj-only",
            result="FAILED",
            counts=_failing_counts(passed=3, errors=2),
            error_clusters=[{
                "cluster_id": 1,
                "pattern": "ImportError: cannot import name * from *",
                "generated_file": None,
                "count": 2,
                "services_affected": ["svc"],
                "error_ids": [1, 2],
                "representative_error_id": 1,
                "codegen_hint": None,
            }],
        )

        writer = _create_aggregate_writer(tmp_path)
        writer.add_project_results(idx)
        agg_path = writer.write()

        agg = json.loads(agg_path.read_text(encoding="utf-8"))
        assert agg["total_projects"] == 1
        assert agg["projects_passed"] == 0
        assert agg["projects_failed"] == 1
        assert len(agg["cross_project_clusters"]) == 1
        cluster = agg["cross_project_clusters"][0]
        assert len(cluster["projects_affected"]) == 1

    def test_many_projects_aggregated(self, tmp_path: Path) -> None:
        """Aggregate handles many projects correctly."""
        writer = _create_aggregate_writer(tmp_path)
        pattern = "ImportError: cannot import name * from *"

        for i in range(10):
            idx = _make_index_json(
                tmp_path,
                project=f"python/docker/proj-{i:02d}",
                example=f"proj-{i:02d}",
                result="FAILED" if i % 3 == 0 else "PASSED",
                counts=_failing_counts(errors=2) if i % 3 == 0 else _passing_counts(),
                error_clusters=[{
                    "cluster_id": 1,
                    "pattern": pattern,
                    "generated_file": None,
                    "count": 2,
                    "services_affected": ["svc"],
                    "error_ids": [1, 2],
                    "representative_error_id": 1,
                    "codegen_hint": None,
                }] if i % 3 == 0 else [],
            )
            writer.add_project_results(idx)

        agg_path = writer.write()
        agg = json.loads(agg_path.read_text(encoding="utf-8"))
        assert agg["total_projects"] == 10
        # Projects 0, 3, 6, 9 are failed
        assert agg["projects_failed"] == 4
        assert agg["projects_passed"] == 6


# ---------------------------------------------------------------------------
# Tests — Data Classes
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDataClasses:
    """Test aggregate data class constraints."""

    def test_project_summary_is_frozen(self) -> None:
        """ProjectSummary is a frozen dataclass."""
        summary = ProjectSummary(
            project="test",
            example="test",
            result_dir="/tmp/test",
            result="PASSED",
            counts={"passed": 1, "failed": 0, "errors": 0, "skipped": 0, "suite_failures": 0},
            top_cluster_pattern=None,
            suite_failure_message=None,
            error_clusters=[],
            failure_clusters=[],
        )
        with pytest.raises(AttributeError):
            summary.project = "other"  # type: ignore[misc]

    def test_cross_project_cluster_is_frozen(self) -> None:
        """CrossProjectCluster is a frozen dataclass."""
        cluster = CrossProjectCluster(
            cluster_id=1,
            pattern="test",
            projects_affected=["proj-a"],
            total_errors=1,
            codegen_hint=None,
            representative_project="proj-a",
        )
        with pytest.raises(AttributeError):
            cluster.pattern = "other"  # type: ignore[misc]

    def test_suite_failure_cluster_is_frozen(self) -> None:
        """SuiteFailureCluster is a frozen dataclass."""
        cluster = SuiteFailureCluster(
            cluster_id=1,
            pattern="test",
            projects_affected=["proj-a"],
            total_suite_failures=1,
            representative_project="proj-a",
        )
        with pytest.raises(AttributeError):
            cluster.pattern = "other"  # type: ignore[misc]
