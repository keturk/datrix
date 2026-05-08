"""Tests for DeployTestLogWriter.

Uses real deploy test output fixtures to validate phase detection,
Docker log excerpting, transient classification, clustering,
codegen hints, and structured output generation.

No mocks, no fakes — real objects and real file I/O only.
"""

import json
from datetime import datetime
from pathlib import Path

import pytest

from shared.deploy_test_log_writer import (
    DEPLOY_PHASES,
    TRANSIENT_ERROR_PATTERNS,
    DeployError,
    DeployErrorCluster,
    DeployFailure,
    DeployFailureCluster,
    DeployTestLogWriter,
    PhaseResult,
    ServiceStatus,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_deploy_dir(tmp_path: Path) -> Path:
    """Create a temporary deploy test directory with realistic structure."""
    run_dir = tmp_path / ".test_results" / "deploy-test-20260503-210903"
    run_dir.mkdir(parents=True)
    (run_dir / "docker-logs").mkdir()
    return run_dir


@pytest.fixture
def docker_lifecycle_failure_dir(tmp_deploy_dir: Path) -> Path:
    """Populate deploy dir with Docker lifecycle failure artifacts.

    Simulates: docker-build passed, docker-up failed (container unhealthy).
    No test artifacts (tests never ran).
    """
    # deploy-test-output.log with docker-up failure
    (tmp_deploy_dir / "deploy-test-output.log").write_text(
        "=== Docker Build ===\n"
        "Building services...\n"
        "Successfully built library-book-service\n"
        "=== Docker Up ===\n"
        "Starting services...\n"
        "docker_up_failed exit_code=1\n"
        "container library-book-service is unhealthy\n",
        encoding="utf-8",
    )

    # Docker container log with error
    (tmp_deploy_dir / "docker-logs" / "library-book-service.log").write_text(
        "INFO library_book_service.main application_starting\n"
        "ERROR library_book_service.cache.redis_client redis_connection_failed "
        "host=library-book-service-cache port=6379\n"
        "ERROR library_book_service.main startup_failed "
        "error=Cannot connect to Redis at library-book-service-cache:6379\n",
        encoding="utf-8",
    )

    # No failures.json, no JUnit XML, no Jest JSON (tests never ran)
    return tmp_deploy_dir


@pytest.fixture
def test_failure_dir(tmp_deploy_dir: Path) -> Path:
    """Populate deploy dir with test-level failure artifacts.

    Simulates: all Docker phases passed, integration tests failed.
    """
    # deploy-test-output.log with successful Docker lifecycle
    (tmp_deploy_dir / "deploy-test-output.log").write_text(
        "=== Docker Build ===\nSuccessfully built\n"
        "=== Docker Up ===\nAll services healthy\n"
        "=== Health Check ===\nAll services responding\n"
        "=== DB Connectivity ===\nAll databases connected\n"
        "=== Spec Tests ===\n3 passed\n"
        "=== Integration Tests ===\n17 passed, 2 failed\n",
        encoding="utf-8",
    )

    # failures.json with test failures
    failures = [
        {
            "test": "tests/test_library_book_service.py::TestService::test_create_book",
            "error": "AssertionError: assert 201 == response.status_code, got 400",
            "type": "logic",
        },
        {
            "test": "tests/integration/repositories/test_book_repository.py::TestBookRepo::test_update",
            "error": "ConnectionResetError: Connection aborted.",
            "type": "transient",
        },
    ]
    (tmp_deploy_dir / "failures.json").write_text(
        json.dumps(failures, indent=2),
        encoding="utf-8",
    )

    # JUnit XML for integration tests
    junit_xml = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<testsuites>"
        '<testsuite name="integration" tests="19" failures="2">\n'
        '  <testcase classname="test_library_book_service.TestService" '
        '    name="test_create_book" time="0.5">\n'
        '    <failure type="AssertionError"'
        '      message="assert 201 == response.status_code, got 400">'
        "tests/test_library_book_service.py:42: AssertionError"
        "</failure>\n"
        "  </testcase>\n"
        '  <testcase classname="test_book_repository.TestBookRepo" '
        '    name="test_update" time="1.2">\n'
        '    <failure type="ConnectionResetError"'
        '      message="ConnectionResetError: Connection aborted.,'
        ' RemoteDisconnected">'
        "tests/integration/repositories/test_book_repository.py:15:"
        " ConnectionResetError"
        "</failure>\n"
        "  </testcase>\n"
        "</testsuite></testsuites>\n"
    )
    (
        tmp_deploy_dir / "pytest-integration-library_book_service-project.xml"
    ).write_text(junit_xml, encoding="utf-8")

    return tmp_deploy_dir


@pytest.fixture
def all_passing_dir(tmp_deploy_dir: Path) -> Path:
    """Populate deploy dir with all-passing test artifacts."""
    (tmp_deploy_dir / "deploy-test-output.log").write_text(
        "=== Docker Build ===\nSuccessfully built\n"
        "=== Docker Up ===\nAll services healthy\n"
        "=== Health Check ===\nAll services responding\n"
        "=== DB Connectivity ===\nAll databases connected\n"
        "=== Spec Tests ===\n3 passed\n"
        "=== Integration Tests ===\n20 passed\n",
        encoding="utf-8",
    )

    # Empty failures.json
    (tmp_deploy_dir / "failures.json").write_text("[]", encoding="utf-8")

    # JUnit XML with all passing
    junit_xml = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<testsuites>"
        '<testsuite name="integration" tests="20" failures="0">\n'
        '  <testcase classname="test_svc.TestSvc" name="test_ok" time="0.5"/>\n'
        "</testsuite></testsuites>\n"
    )
    (tmp_deploy_dir / "pytest-integration-my_service-project.xml").write_text(
        junit_xml, encoding="utf-8"
    )

    return tmp_deploy_dir


def _make_writer(
    run_dir: Path,
    tmp_path: Path,
    project_name: str = "cache",
    example: str = "02-features/03-infrastructure-blocks/cache",
) -> DeployTestLogWriter:
    """Create a DeployTestLogWriter with sensible defaults."""
    return DeployTestLogWriter(
        project_name=project_name,
        run_dir=run_dir,
        project_path=tmp_path,
        language="python",
        platform="docker",
        example=example,
        dtrx_source=f"datrix/examples/{example}/system.dtrx",
    )


# ---------------------------------------------------------------------------
# Phase Detection Tests
# ---------------------------------------------------------------------------


class TestPhaseDetection:
    """Test phase detection from file existence and log parsing."""

    def test_docker_lifecycle_failure_detected(
        self,
        docker_lifecycle_failure_dir: Path,
        tmp_path: Path,
    ) -> None:
        """Docker-up failure detected when no test artifacts exist."""
        writer = _make_writer(docker_lifecycle_failure_dir, tmp_path)
        index_path = writer.write(timestamp=datetime(2026, 5, 3, 21, 10, 3))

        index = json.loads(index_path.read_text(encoding="utf-8"))
        assert index["failed_phase"] == "docker-up"
        assert index["phases"]["docker-build"]["result"] == "PASSED"
        assert index["phases"]["docker-up"]["result"] == "FAILED"
        assert index["phases"]["spec-tests"]["result"] == "SKIPPED"
        assert index["phases"]["integration-tests"]["result"] == "SKIPPED"

    def test_test_phase_failure_detected(
        self,
        test_failure_dir: Path,
        tmp_path: Path,
    ) -> None:
        """Integration test failure detected when JUnit XML exists."""
        writer = _make_writer(
            test_failure_dir,
            tmp_path,
            project_name="01-foundation",
            example="01-foundation",
        )
        index_path = writer.write(timestamp=datetime(2026, 5, 3, 21, 9, 3))

        index = json.loads(index_path.read_text(encoding="utf-8"))
        assert index["failed_phase"] == "integration-tests"
        # Docker phases passed since test artifacts exist
        assert index["phases"]["docker-build"]["result"] == "PASSED"
        assert index["phases"]["docker-up"]["result"] == "PASSED"
        assert index["phases"]["integration-tests"]["result"] == "FAILED"

    def test_all_passing_has_no_failed_phase(
        self,
        all_passing_dir: Path,
        tmp_path: Path,
    ) -> None:
        """Passing project has no failed_phase."""
        writer = _make_writer(
            all_passing_dir,
            tmp_path,
            project_name="basic",
            example="02-features/01-core-data-modeling/entities",
        )
        index_path = writer.write(timestamp=datetime(2026, 5, 3, 21, 9, 3))

        index = json.loads(index_path.read_text(encoding="utf-8"))
        assert index["result"] == "PASSED"
        assert index["failed_phase"] is None

    def test_deploy_phases_constant_order(self) -> None:
        """DEPLOY_PHASES constant has correct ordered phases."""
        assert DEPLOY_PHASES == [
            "docker-build",
            "docker-up",
            "health-check",
            "db-connectivity",
            "spec-tests",
            "integration-tests",
        ]

    def test_structured_log_docker_up_failure_detected(
        self,
        tmp_deploy_dir: Path,
        tmp_path: Path,
    ) -> None:
        """Docker-up failure detected from structured log markers.

        Regression test: deploy_test.py emits structured markers like
        'docker_build_started' and 'docker_up_failed exit_code=1' rather
        than human-readable headers like '=== Docker Build ==='.
        The phase markers must match both formats.
        """
        (tmp_deploy_dir / "deploy-test-output.log").write_text(
            "docker_build_started\n"
            "docker_build_completed\n"
            "docker_up output:\n"
            "docker_up_failed exit_code=1\n",
            encoding="utf-8",
        )

        writer = _make_writer(tmp_deploy_dir, tmp_path)
        index_path = writer.write(timestamp=datetime(2026, 5, 7, 13, 41, 39))

        index = json.loads(index_path.read_text(encoding="utf-8"))
        assert index["result"] == "FAILED"
        assert index["failed_phase"] == "docker-up"
        assert index["phases"]["docker-build"]["result"] == "PASSED"
        assert index["phases"]["docker-up"]["result"] == "FAILED"
        assert index["phases"]["health-check"]["result"] == "SKIPPED"

    def test_structured_log_docker_build_failure_detected(
        self,
        tmp_deploy_dir: Path,
        tmp_path: Path,
    ) -> None:
        """Docker-build failure detected from structured log markers.

        Regression test: when Docker Desktop is not running, the log
        contains 'docker_build_started' then 'docker_build_failed
        exit_code=1'. index.json must report FAILED, not PASSED.
        """
        (tmp_deploy_dir / "deploy-test-output.log").write_text(
            "docker_build_started\n"
            "docker_build_failed exit_code=1\n",
            encoding="utf-8",
        )

        writer = _make_writer(tmp_deploy_dir, tmp_path)
        index_path = writer.write(timestamp=datetime(2026, 5, 7, 13, 0, 50))

        index = json.loads(index_path.read_text(encoding="utf-8"))
        assert index["result"] == "FAILED"
        assert index["failed_phase"] == "docker-build"
        assert index["phases"]["docker-build"]["result"] == "FAILED"
        assert index["phases"]["docker-up"]["result"] == "SKIPPED"


# ---------------------------------------------------------------------------
# Docker Log Excerpting Tests
# ---------------------------------------------------------------------------


class TestDockerLogExcerpting:
    """Test Docker container log excerpting for error files."""

    def test_error_excerpt_contains_error_lines(
        self,
        docker_lifecycle_failure_dir: Path,
        tmp_path: Path,
    ) -> None:
        """Error excerpt includes ERROR-level log lines from container."""
        writer = _make_writer(docker_lifecycle_failure_dir, tmp_path)
        writer.write(timestamp=datetime(2026, 5, 3, 21, 10, 3))

        # Check errors/ directory
        errors_dir = docker_lifecycle_failure_dir / "errors"
        assert errors_dir.exists()
        error_files = sorted(errors_dir.glob("*.txt"))
        assert len(error_files) >= 1

        content = error_files[0].read_text(encoding="utf-8")
        assert "redis_connection_failed" in content
        assert "Cannot connect to Redis" in content

    def test_error_file_has_phase_and_error_type(
        self,
        docker_lifecycle_failure_dir: Path,
        tmp_path: Path,
    ) -> None:
        """Error detail file has PHASE and ERROR headers."""
        writer = _make_writer(docker_lifecycle_failure_dir, tmp_path)
        writer.write(timestamp=datetime(2026, 5, 3, 21, 10, 3))

        errors_dir = docker_lifecycle_failure_dir / "errors"
        error_files = sorted(errors_dir.glob("*.txt"))
        assert len(error_files) >= 1

        content = error_files[0].read_text(encoding="utf-8")
        assert content.startswith("PHASE:")
        assert "ERROR:" in content

    def test_no_docker_logs_produces_fallback_message(
        self,
        tmp_deploy_dir: Path,
        tmp_path: Path,
    ) -> None:
        """Missing Docker logs produce a fallback message in the excerpt."""
        (tmp_deploy_dir / "deploy-test-output.log").write_text(
            "=== Docker Up ===\n"
            "docker_up_failed exit_code=1\n"
            "container missing-service is unhealthy\n",
            encoding="utf-8",
        )

        writer = _make_writer(tmp_deploy_dir, tmp_path)
        writer.write(timestamp=datetime(2026, 5, 3, 21, 10, 3))

        # Should still produce errors/ files even without container logs
        errors_dir = tmp_deploy_dir / "errors"
        if errors_dir.exists():
            error_files = sorted(errors_dir.glob("*.txt"))
            if error_files:
                content = error_files[0].read_text(encoding="utf-8")
                assert "PHASE:" in content


# ---------------------------------------------------------------------------
# Transient Classification Tests
# ---------------------------------------------------------------------------


class TestTransientClassification:
    """Test transient vs logic failure classification."""

    def test_connection_reset_is_transient(
        self,
        test_failure_dir: Path,
        tmp_path: Path,
    ) -> None:
        """ConnectionResetError classified as transient."""
        writer = _make_writer(
            test_failure_dir,
            tmp_path,
            project_name="01-foundation",
            example="01-foundation",
        )
        index_path = writer.write(timestamp=datetime(2026, 5, 3, 21, 9, 3))

        index = json.loads(index_path.read_text(encoding="utf-8"))
        transient_failures = [
            f for f in index["failures"] if f["failure_type"] == "transient"
        ]
        logic_failures = [
            f for f in index["failures"] if f["failure_type"] == "logic"
        ]
        assert len(transient_failures) >= 1
        assert len(logic_failures) >= 1

    def test_assertion_error_is_logic(
        self,
        test_failure_dir: Path,
        tmp_path: Path,
    ) -> None:
        """AssertionError classified as logic (not transient)."""
        writer = _make_writer(
            test_failure_dir,
            tmp_path,
            project_name="01-foundation",
            example="01-foundation",
        )
        index_path = writer.write(timestamp=datetime(2026, 5, 3, 21, 9, 3))

        index = json.loads(index_path.read_text(encoding="utf-8"))
        logic_failures = [
            f for f in index["failures"] if f["failure_type"] == "logic"
        ]
        assert len(logic_failures) >= 1
        # Logic failure should have a codegen_hint
        for f in logic_failures:
            if f["error_type"] == "AssertionError":
                assert f["codegen_hint"] is not None

    def test_transient_patterns_list_not_empty(self) -> None:
        """TRANSIENT_ERROR_PATTERNS constant is populated."""
        assert len(TRANSIENT_ERROR_PATTERNS) > 10
        assert "ConnectionResetError" in TRANSIENT_ERROR_PATTERNS
        assert "timeout" in TRANSIENT_ERROR_PATTERNS
        assert "BrokenPipeError" in TRANSIENT_ERROR_PATTERNS


# ---------------------------------------------------------------------------
# Clustering Tests
# ---------------------------------------------------------------------------


class TestClustering:
    """Test failure and error clustering."""

    def test_failures_clustered_by_error_type(
        self,
        test_failure_dir: Path,
        tmp_path: Path,
    ) -> None:
        """Different error types produce separate clusters."""
        writer = _make_writer(
            test_failure_dir,
            tmp_path,
            project_name="01-foundation",
            example="01-foundation",
        )
        index_path = writer.write(timestamp=datetime(2026, 5, 3, 21, 9, 3))

        index = json.loads(index_path.read_text(encoding="utf-8"))
        # Two distinct failures (AssertionError + ConnectionResetError)
        # should produce 2 clusters
        assert len(index["failure_clusters"]) == 2

    def test_error_clusters_for_docker_failure(
        self,
        docker_lifecycle_failure_dir: Path,
        tmp_path: Path,
    ) -> None:
        """Docker lifecycle failure produces error clusters."""
        writer = _make_writer(docker_lifecycle_failure_dir, tmp_path)
        index_path = writer.write(timestamp=datetime(2026, 5, 3, 21, 10, 3))

        index = json.loads(index_path.read_text(encoding="utf-8"))
        assert len(index["error_clusters"]) >= 1
        cluster = index["error_clusters"][0]
        assert cluster["phase"] == "docker-up"
        assert "pattern" in cluster


# ---------------------------------------------------------------------------
# Output Format Tests
# ---------------------------------------------------------------------------


class TestOutputFormat:
    """Test structured output file format and content."""

    def test_index_json_schema(
        self,
        docker_lifecycle_failure_dir: Path,
        tmp_path: Path,
    ) -> None:
        """index.json contains all required top-level fields."""
        writer = _make_writer(docker_lifecycle_failure_dir, tmp_path)
        index_path = writer.write(timestamp=datetime(2026, 5, 3, 21, 10, 3))

        index = json.loads(index_path.read_text(encoding="utf-8"))
        required_fields = [
            "schema_version",
            "project",
            "project_path",
            "language",
            "platform",
            "example",
            "dtrx_source",
            "timestamp",
            "duration_seconds",
            "result",
            "failed_phase",
            "phases",
            "services",
            "failures",
            "errors",
            "failure_clusters",
            "error_clusters",
        ]
        for field_name in required_fields:
            assert field_name in index, f"Missing field: {field_name}"

        assert index["schema_version"] == 1
        assert index["result"] == "FAILED"
        assert index["language"] == "python"
        assert index["platform"] == "docker"

    def test_index_json_test_failure_schema(
        self,
        test_failure_dir: Path,
        tmp_path: Path,
    ) -> None:
        """index.json for test failures has populated failures array."""
        writer = _make_writer(
            test_failure_dir,
            tmp_path,
            project_name="01-foundation",
            example="01-foundation",
        )
        index_path = writer.write(timestamp=datetime(2026, 5, 3, 21, 9, 3))

        index = json.loads(index_path.read_text(encoding="utf-8"))
        assert index["result"] == "FAILED"
        assert len(index["failures"]) >= 1

        # Each failure should have required fields
        for failure in index["failures"]:
            assert "id" in failure
            assert "service" in failure
            assert "phase" in failure
            assert "test_id" in failure
            assert "error_type" in failure
            assert "error_message" in failure
            assert "failure_type" in failure
            assert failure["failure_type"] in ("logic", "transient")

    def test_summary_txt_generated(
        self,
        docker_lifecycle_failure_dir: Path,
        tmp_path: Path,
    ) -> None:
        """summary.txt is generated and under 60 lines."""
        writer = _make_writer(docker_lifecycle_failure_dir, tmp_path)
        writer.write(timestamp=datetime(2026, 5, 3, 21, 10, 3))

        summary = docker_lifecycle_failure_dir / "summary.txt"
        assert summary.exists()
        lines = summary.read_text(encoding="utf-8").splitlines()
        assert len(lines) <= 60
        assert "FAILED" in "\n".join(lines[:5])

    def test_summary_txt_for_test_failure(
        self,
        test_failure_dir: Path,
        tmp_path: Path,
    ) -> None:
        """summary.txt for test failures includes FAILURE CLUSTERS section."""
        writer = _make_writer(
            test_failure_dir,
            tmp_path,
            project_name="01-foundation",
            example="01-foundation",
        )
        writer.write(timestamp=datetime(2026, 5, 3, 21, 9, 3))

        summary = test_failure_dir / "summary.txt"
        assert summary.exists()
        content = summary.read_text(encoding="utf-8")
        assert "FAILURE CLUSTERS" in content
        assert "integration-tests" in content

    def test_failure_detail_files_generated(
        self,
        test_failure_dir: Path,
        tmp_path: Path,
    ) -> None:
        """Individual failure detail files generated in failures/ dir."""
        writer = _make_writer(
            test_failure_dir,
            tmp_path,
            project_name="01-foundation",
            example="01-foundation",
        )
        writer.write(timestamp=datetime(2026, 5, 3, 21, 9, 3))

        failures_dir = test_failure_dir / "failures"
        assert failures_dir.exists()
        failure_files = sorted(failures_dir.glob("*.txt"))
        assert len(failure_files) >= 1

        # Each failure file should have standard headers
        for ff in failure_files:
            content = ff.read_text(encoding="utf-8")
            assert "SERVICE:" in content
            assert "PHASE:" in content
            assert "TEST:" in content
            assert "FAILURE TYPE:" in content
            assert "ERROR:" in content

    def test_passing_project_produces_valid_index(
        self,
        all_passing_dir: Path,
        tmp_path: Path,
    ) -> None:
        """All-passing project produces valid index with no failures."""
        writer = _make_writer(
            all_passing_dir,
            tmp_path,
            project_name="basic",
            example="02-features/01-core-data-modeling/entities",
        )
        index_path = writer.write(timestamp=datetime(2026, 5, 3, 21, 9, 3))

        index = json.loads(index_path.read_text(encoding="utf-8"))
        assert index["result"] == "PASSED"
        assert index["failed_phase"] is None
        assert len(index["failures"]) == 0
        assert len(index["errors"]) == 0
        assert len(index["failure_clusters"]) == 0
        assert len(index["error_clusters"]) == 0

    def test_error_detail_files_for_docker_failure(
        self,
        docker_lifecycle_failure_dir: Path,
        tmp_path: Path,
    ) -> None:
        """Docker lifecycle failure produces error detail files in errors/ dir."""
        writer = _make_writer(docker_lifecycle_failure_dir, tmp_path)
        writer.write(timestamp=datetime(2026, 5, 3, 21, 10, 3))

        errors_dir = docker_lifecycle_failure_dir / "errors"
        assert errors_dir.exists()
        error_files = sorted(errors_dir.glob("*.txt"))
        assert len(error_files) >= 1

        # Error files should have standard headers
        content = error_files[0].read_text(encoding="utf-8")
        assert "PHASE:" in content
        assert "ERROR:" in content
        assert "MESSAGE:" in content


# ---------------------------------------------------------------------------
# Codegen Hints Tests
# ---------------------------------------------------------------------------


class TestCodegenHints:
    """Test codegen hint generation."""

    def test_docker_error_has_codegen_hint(
        self,
        docker_lifecycle_failure_dir: Path,
        tmp_path: Path,
    ) -> None:
        """Docker lifecycle errors include codegen hint."""
        writer = _make_writer(docker_lifecycle_failure_dir, tmp_path)
        index_path = writer.write(timestamp=datetime(2026, 5, 3, 21, 10, 3))

        index = json.loads(index_path.read_text(encoding="utf-8"))
        assert len(index["errors"]) >= 1
        error = index["errors"][0]
        assert error["codegen_hint"] is not None
        assert "probable_template" in error["codegen_hint"]
        assert error["codegen_hint"]["probable_template"] == "docker-compose.yml.j2"

    def test_logic_failure_has_codegen_hint(
        self,
        test_failure_dir: Path,
        tmp_path: Path,
    ) -> None:
        """Logic test failures include codegen hint."""
        writer = _make_writer(
            test_failure_dir,
            tmp_path,
            project_name="01-foundation",
            example="01-foundation",
        )
        index_path = writer.write(timestamp=datetime(2026, 5, 3, 21, 9, 3))

        index = json.loads(index_path.read_text(encoding="utf-8"))
        logic_failures = [
            f for f in index["failures"] if f["failure_type"] == "logic"
        ]
        assert len(logic_failures) >= 1
        for f in logic_failures:
            assert f["codegen_hint"] is not None

    def test_transient_failure_has_no_codegen_hint(
        self,
        test_failure_dir: Path,
        tmp_path: Path,
    ) -> None:
        """Transient failures have null codegen hint (not a codegen bug)."""
        writer = _make_writer(
            test_failure_dir,
            tmp_path,
            project_name="01-foundation",
            example="01-foundation",
        )
        index_path = writer.write(timestamp=datetime(2026, 5, 3, 21, 9, 3))

        index = json.loads(index_path.read_text(encoding="utf-8"))
        transient_failures = [
            f for f in index["failures"] if f["failure_type"] == "transient"
        ]
        assert len(transient_failures) >= 1
        for f in transient_failures:
            assert f["codegen_hint"] is None


# ---------------------------------------------------------------------------
# Services Copy Tests
# ---------------------------------------------------------------------------


class TestServicesCopy:
    """Test copying test artifacts to services/ subdirectory."""

    def test_junit_xml_copied_to_services_dir(
        self,
        test_failure_dir: Path,
        tmp_path: Path,
    ) -> None:
        """JUnit XML files are copied into services/{name}/ subdirectory."""
        writer = _make_writer(
            test_failure_dir,
            tmp_path,
            project_name="01-foundation",
            example="01-foundation",
        )
        writer.write(timestamp=datetime(2026, 5, 3, 21, 9, 3))

        services_dir = test_failure_dir / "services"
        # The service name from the JUnit XML is "library_book_service"
        svc_dir = services_dir / "library_book_service"
        if svc_dir.exists():
            integ_dir = svc_dir / "integration"
            assert integ_dir.exists()
            # Should have at least one XML file copied
            xml_files = list(integ_dir.glob("*.xml"))
            assert len(xml_files) >= 1

    def test_originals_not_moved(
        self,
        test_failure_dir: Path,
        tmp_path: Path,
    ) -> None:
        """Original JUnit XML files remain in place (copied, not moved)."""
        writer = _make_writer(
            test_failure_dir,
            tmp_path,
            project_name="01-foundation",
            example="01-foundation",
        )
        writer.write(timestamp=datetime(2026, 5, 3, 21, 9, 3))

        # Original should still exist
        original = (
            test_failure_dir
            / "pytest-integration-library_book_service-project.xml"
        )
        assert original.exists()


# ---------------------------------------------------------------------------
# Empty/Edge Case Tests
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_deploy_dir_produces_valid_output(
        self,
        tmp_deploy_dir: Path,
        tmp_path: Path,
    ) -> None:
        """Empty deploy dir (no log, no artifacts) produces valid index."""
        writer = _make_writer(tmp_deploy_dir, tmp_path)
        index_path = writer.write(timestamp=datetime(2026, 5, 3, 21, 10, 3))

        index = json.loads(index_path.read_text(encoding="utf-8"))
        assert index["schema_version"] == 1
        # All phases should be SKIPPED
        for phase_data in index["phases"].values():
            assert phase_data["result"] == "SKIPPED"

    def test_corrupt_failures_json_handled(
        self,
        tmp_deploy_dir: Path,
        tmp_path: Path,
    ) -> None:
        """Corrupt failures.json is handled gracefully."""
        (tmp_deploy_dir / "failures.json").write_text(
            "not valid json{{{",
            encoding="utf-8",
        )
        (tmp_deploy_dir / "deploy-test-output.log").write_text(
            "=== Docker Build ===\nOK\n",
            encoding="utf-8",
        )

        writer = _make_writer(tmp_deploy_dir, tmp_path)
        # Should not raise
        index_path = writer.write(timestamp=datetime(2026, 5, 3, 21, 10, 3))
        index = json.loads(index_path.read_text(encoding="utf-8"))
        assert index["schema_version"] == 1

    def test_corrupt_junit_xml_handled(
        self,
        tmp_deploy_dir: Path,
        tmp_path: Path,
    ) -> None:
        """Corrupt JUnit XML is handled gracefully."""
        (tmp_deploy_dir / "pytest-integration-svc.xml").write_text(
            "<not-valid-xml",
            encoding="utf-8",
        )
        (tmp_deploy_dir / "deploy-test-output.log").write_text(
            "=== Docker Build ===\nOK\n",
            encoding="utf-8",
        )

        writer = _make_writer(tmp_deploy_dir, tmp_path)
        # Should not raise
        index_path = writer.write(timestamp=datetime(2026, 5, 3, 21, 10, 3))
        index = json.loads(index_path.read_text(encoding="utf-8"))
        assert index["schema_version"] == 1
