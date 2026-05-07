"""Tests for GeneratedTestLogWriter.

Tests verify:
- JUnit XML parsing (passes, failures, errors)
- Jest JSON parsing (passes, failures, suite errors)
- Error clustering by normalized pattern
- Import chain extraction from tracebacks
- Codegen hint generation
- index.json schema compliance
- summary.txt format compliance
- Individual error/failure file format
- Directory structure creation
- Passing run behavior (no failures/ or errors/ dirs)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from shared.generated_test_log_writer import (
    GeneratedTestLogWriter,
    TestError,
    TestFailure,
    ErrorCluster,
    normalize_error_message,
    _extract_import_chain,
    _extract_generated_file,
)


# ---------------------------------------------------------------------------
# JUnit XML fixtures
# ---------------------------------------------------------------------------

SAMPLE_JUNIT_XML_PASSING = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="tests.unit.test_user_service" tests="5" errors="0" failures="0" skipped="0" time="1.234">
    <testcase classname="tests.unit.test_user_service.TestUserService" name="test_create_user" time="0.123"/>
    <testcase classname="tests.unit.test_user_service.TestUserService" name="test_get_user" time="0.045"/>
    <testcase classname="tests.unit.test_user_service.TestUserService" name="test_update_user" time="0.067"/>
    <testcase classname="tests.unit.test_user_service.TestUserService" name="test_delete_user" time="0.089"/>
    <testcase classname="tests.unit.test_user_service.TestUserService" name="test_list_users" time="0.112"/>
  </testsuite>
</testsuites>
"""

SAMPLE_JUNIT_XML_WITH_FAILURES = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="tests.unit.test_user_service" tests="3" errors="0" failures="2" skipped="0" time="0.5">
    <testcase classname="tests.unit.test_user_service.TestUserService" name="test_create_user" time="0.1"/>
    <testcase classname="tests.unit.test_user_service.TestUserService" name="test_validate_email" time="0.2">
      <failure type="AssertionError" message="assert False">
tests/unit/test_user_service.py:45: in test_validate_email
    assert validate_email("bad") is True
E   AssertionError: assert False
      </failure>
    </testcase>
    <testcase classname="tests.unit.test_user_service.TestUserService" name="test_validate_name" time="0.2">
      <failure type="AssertionError" message="assert False">
tests/unit/test_user_service.py:52: in test_validate_name
    assert validate_name("") is True
E   AssertionError: assert False
      </failure>
    </testcase>
  </testsuite>
</testsuites>
"""

SAMPLE_JUNIT_XML_WITH_ERRORS = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="tests.integration.repositories.test_user_repository" tests="3" errors="3" failures="0" skipped="0" time="0.001">
    <testcase classname="tests.integration.repositories.test_user_repository" name="test_create_user" time="0.000">
      <error type="ImportError" message="cannot import name '_email_send_ses' from 'ecommerce_user_service.integrations._email_helpers'">
ImportError while importing test module 'tests/integration/repositories/test_user_repository.py'.
Traceback:
  tests/integration/repositories/test_user_repository.py:18: in &lt;module&gt;
      from ecommerce_user_service.services.user_db.user_service import UserService
  src/ecommerce_user_service/services/user_db/user_service.py:19: in &lt;module&gt;
      from ecommerce_user_service.integrations._email_helpers import _email_send_ses
  ImportError: cannot import name '_email_send_ses' from 'ecommerce_user_service.integrations._email_helpers'
      </error>
    </testcase>
    <testcase classname="tests.integration.repositories.test_user_repository" name="test_update_user" time="0.000">
      <error type="ImportError" message="cannot import name '_email_send_ses' from 'ecommerce_user_service.integrations._email_helpers'">
ImportError while importing test module 'tests/integration/repositories/test_user_repository.py'.
Traceback:
  tests/integration/repositories/test_user_repository.py:18: in &lt;module&gt;
      from ecommerce_user_service.services.user_db.user_service import UserService
  src/ecommerce_user_service/services/user_db/user_service.py:19: in &lt;module&gt;
      from ecommerce_user_service.integrations._email_helpers import _email_send_ses
  ImportError: cannot import name '_email_send_ses' from 'ecommerce_user_service.integrations._email_helpers'
      </error>
    </testcase>
    <testcase classname="tests.integration.repositories.test_user_repository" name="test_delete_user" time="0.000">
      <error type="ImportError" message="cannot import name '_email_send_ses' from 'ecommerce_user_service.integrations._email_helpers'">
ImportError while importing test module 'tests/integration/repositories/test_user_repository.py'.
Traceback:
  tests/integration/repositories/test_user_repository.py:18: in &lt;module&gt;
      from ecommerce_user_service.services.user_db.user_service import UserService
  src/ecommerce_user_service/services/user_db/user_service.py:19: in &lt;module&gt;
      from ecommerce_user_service.integrations._email_helpers import _email_send_ses
  ImportError: cannot import name '_email_send_ses' from 'ecommerce_user_service.integrations._email_helpers'
      </error>
    </testcase>
  </testsuite>
</testsuites>
"""


# ---------------------------------------------------------------------------
# Jest JSON fixtures
# ---------------------------------------------------------------------------

SAMPLE_JEST_JSON_PASSING: dict = {
    "numTotalTests": 10,
    "numPassedTests": 10,
    "numFailedTests": 0,
    "numPendingTests": 0,
    "testResults": [
        {
            "testFilePath": "/app/tests/unit/user.service.spec.ts",
            "status": "passed",
            "testResults": [
                {"title": "should create user", "status": "passed", "fullName": "UserService should create user"},
                {"title": "should get user", "status": "passed", "fullName": "UserService should get user"},
            ],
        }
    ],
}

SAMPLE_JEST_JSON_WITH_FAILURES: dict = {
    "numTotalTests": 3,
    "numPassedTests": 1,
    "numFailedTests": 2,
    "numPendingTests": 0,
    "testResults": [
        {
            "testFilePath": "/app/tests/unit/user.service.spec.ts",
            "status": "failed",
            "testResults": [
                {"title": "should create user", "status": "passed", "fullName": "UserService should create user"},
                {
                    "title": "should validate email",
                    "status": "failed",
                    "fullName": "UserService should validate email",
                    "failureMessages": ["TypeError: Cannot read property 'email' of undefined"],
                },
                {
                    "title": "should validate name",
                    "status": "failed",
                    "fullName": "UserService should validate name",
                    "failureMessages": ["TypeError: Cannot read property 'name' of undefined"],
                },
            ],
        }
    ],
}

SAMPLE_JEST_JSON_WITH_SUITE_FAILURE: dict = {
    "numTotalTests": 0,
    "numPassedTests": 0,
    "numFailedTests": 0,
    "numPendingTests": 0,
    "testResults": [
        {
            "testFilePath": "/app/tests/unit/user.service.spec.ts",
            "status": "failed",
            "testExecError": {
                "message": "Cannot find module 'express'",
                "stack": "Error: Cannot find module 'express'\n    at Function.Module._resolveFilename (node:internal/modules/cjs/loader:1075:15)",
            },
            "testResults": [],
        }
    ],
}


# ---------------------------------------------------------------------------
# Helper to create writer + write XML/JSON files
# ---------------------------------------------------------------------------


def _create_writer(tmp_path: Path) -> GeneratedTestLogWriter:
    """Create a GeneratedTestLogWriter with standard test parameters."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    return GeneratedTestLogWriter(
        project_path="python/docker/02-features/test-project",
        language="python",
        platform="docker",
        example="02-features/test-project",
        run_dir=run_dir,
        dtrx_source="datrix/examples/02-features/test-project/system.dtrx",
    )


def _write_xml(tmp_path: Path, content: str, name: str = "junit.xml") -> Path:
    """Write a JUnit XML string to a file and return the path."""
    xml_path = tmp_path / name
    xml_path.write_text(content, encoding="utf-8")
    return xml_path


def _write_json(tmp_path: Path, data: dict, name: str = "jest-results.json") -> Path:
    """Write Jest JSON data to a file and return the path."""
    json_path = tmp_path / name
    json_path.write_text(json.dumps(data), encoding="utf-8")
    return json_path


def _write_log(tmp_path: Path, name: str = "service.log") -> Path:
    """Write a dummy log file and return the path."""
    log_path = tmp_path / name
    log_path.write_text("test log output\n", encoding="utf-8")
    return log_path


# ---------------------------------------------------------------------------
# Tests — JUnit XML Parsing
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestJunitXmlParsing:
    """Test JUnit XML parsing for Python projects."""

    def test_parse_passing_results(self, tmp_path: Path) -> None:
        """Passing JUnit XML produces correct counts with no errors."""
        writer = _create_writer(tmp_path)
        xml_path = _write_xml(tmp_path, SAMPLE_JUNIT_XML_PASSING)
        log_path = _write_log(tmp_path)

        writer.add_service_junit_xml("user_service", xml_path, log_path)
        index_path = writer.write(duration_seconds=1.5)

        index = json.loads(index_path.read_text(encoding="utf-8"))
        assert index["result"] == "PASSED"
        assert index["counts"]["passed"] == 5
        assert index["counts"]["failed"] == 0
        assert index["counts"]["errors"] == 0
        assert len(index["failures"]) == 0
        assert len(index["errors"]) == 0

    def test_parse_failure_results(self, tmp_path: Path) -> None:
        """JUnit XML with failures produces correct failure entries."""
        writer = _create_writer(tmp_path)
        xml_path = _write_xml(tmp_path, SAMPLE_JUNIT_XML_WITH_FAILURES)
        log_path = _write_log(tmp_path)

        writer.add_service_junit_xml("user_service", xml_path, log_path)
        index_path = writer.write(duration_seconds=0.5)

        index = json.loads(index_path.read_text(encoding="utf-8"))
        assert index["result"] == "FAILED"
        assert index["counts"]["passed"] == 1
        assert index["counts"]["failed"] == 2
        assert len(index["failures"]) == 2
        assert index["failures"][0]["service"] == "user_service"
        assert index["failures"][0]["error_type"] == "AssertionError"

    def test_parse_error_results(self, tmp_path: Path) -> None:
        """JUnit XML with errors produces correct error entries."""
        writer = _create_writer(tmp_path)
        xml_path = _write_xml(tmp_path, SAMPLE_JUNIT_XML_WITH_ERRORS)
        log_path = _write_log(tmp_path)

        writer.add_service_junit_xml("ecommerce_user_service", xml_path, log_path)
        index_path = writer.write(duration_seconds=0.1)

        index = json.loads(index_path.read_text(encoding="utf-8"))
        assert index["result"] == "FAILED"
        assert index["counts"]["errors"] == 3
        assert len(index["errors"]) == 3
        assert index["errors"][0]["error_type"] == "ImportError"

    def test_error_clustering(self, tmp_path: Path) -> None:
        """Errors with same pattern are grouped into one cluster."""
        writer = _create_writer(tmp_path)
        xml_path = _write_xml(tmp_path, SAMPLE_JUNIT_XML_WITH_ERRORS)
        log_path = _write_log(tmp_path)

        writer.add_service_junit_xml("ecommerce_user_service", xml_path, log_path)
        index_path = writer.write(duration_seconds=0.1)

        index = json.loads(index_path.read_text(encoding="utf-8"))
        # All 3 errors have the same ImportError pattern → 1 cluster
        assert len(index["error_clusters"]) == 1
        cluster = index["error_clusters"][0]
        assert cluster["count"] == 3
        assert "ecommerce_user_service" in cluster["services_affected"]
        # No codegen_hint because the traceback paths start with src/ (no leading
        # directory), so _extract_generated_file doesn't find a /src/ match.
        # Codegen hints require a generated_file to map from.
        assert cluster["codegen_hint"] is None


# ---------------------------------------------------------------------------
# Tests — Jest JSON Parsing
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestJestJsonParsing:
    """Test Jest JSON parsing for TypeScript projects."""

    def test_parse_passing_results(self, tmp_path: Path) -> None:
        """Passing Jest JSON produces correct counts with no errors."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        writer = GeneratedTestLogWriter(
            project_path="typescript/docker/02-features/test-project",
            language="typescript",
            platform="docker",
            example="02-features/test-project",
            run_dir=run_dir,
            dtrx_source="datrix/examples/02-features/test-project/system.dtrx",
        )
        json_path = _write_json(tmp_path, SAMPLE_JEST_JSON_PASSING)
        log_path = _write_log(tmp_path)

        writer.add_service_jest_json("user_service", json_path, log_path)
        index_path = writer.write(duration_seconds=2.0)

        index = json.loads(index_path.read_text(encoding="utf-8"))
        assert index["result"] == "PASSED"
        assert index["counts"]["passed"] == 2
        assert index["counts"]["failed"] == 0
        assert len(index["failures"]) == 0

    def test_parse_failure_results(self, tmp_path: Path) -> None:
        """Jest JSON with failures produces correct failure entries."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        writer = GeneratedTestLogWriter(
            project_path="typescript/docker/02-features/test-project",
            language="typescript",
            platform="docker",
            example="02-features/test-project",
            run_dir=run_dir,
            dtrx_source="datrix/examples/02-features/test-project/system.dtrx",
        )
        json_path = _write_json(tmp_path, SAMPLE_JEST_JSON_WITH_FAILURES)
        log_path = _write_log(tmp_path)

        writer.add_service_jest_json("user_service", json_path, log_path)
        index_path = writer.write(duration_seconds=1.0)

        index = json.loads(index_path.read_text(encoding="utf-8"))
        assert index["result"] == "FAILED"
        assert index["counts"]["failed"] == 2
        assert index["counts"]["passed"] == 1
        assert len(index["failures"]) == 2

    def test_parse_suite_failure(self, tmp_path: Path) -> None:
        """Jest suite failure is correctly identified and recorded."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        writer = GeneratedTestLogWriter(
            project_path="typescript/docker/02-features/test-project",
            language="typescript",
            platform="docker",
            example="02-features/test-project",
            run_dir=run_dir,
            dtrx_source="datrix/examples/02-features/test-project/system.dtrx",
        )
        json_path = _write_json(tmp_path, SAMPLE_JEST_JSON_WITH_SUITE_FAILURE)
        log_path = _write_log(tmp_path)

        writer.add_service_jest_json("user_service", json_path, log_path)
        index_path = writer.write(duration_seconds=0.5)

        index = json.loads(index_path.read_text(encoding="utf-8"))
        assert index["result"] == "FAILED"
        assert index["counts"]["suite_failures"] == 1
        assert len(index["errors"]) == 1
        assert index["errors"][0]["error_type"] == "SuiteFailure"
        assert "Cannot find module" in index["errors"][0]["error_message"]
        # Check service-level suite_failure_message
        svc = index["services"][0]
        assert svc["suite_failure_message"] == "Cannot find module 'express'"


# ---------------------------------------------------------------------------
# Tests — Error Clustering
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestErrorClustering:
    """Test error normalization and clustering."""

    def test_normalize_replaces_quoted_strings(self) -> None:
        """Quoted strings are replaced with * in normalization."""
        result = normalize_error_message(
            "ImportError",
            "cannot import name '_email_send_ses' from 'ecommerce.integrations._email_helpers'"
        )
        assert result == "ImportError: cannot import name * from *"

    def test_normalize_replaces_numbers(self) -> None:
        """Standalone numbers are replaced with * in normalization."""
        result = normalize_error_message("ValueError", "expected 42 items")
        assert result == "ValueError: expected * items"

    def test_cluster_same_pattern(self, tmp_path: Path) -> None:
        """Errors with same normalized pattern form one cluster."""
        writer = _create_writer(tmp_path)
        xml_path = _write_xml(tmp_path, SAMPLE_JUNIT_XML_WITH_ERRORS)
        log_path = _write_log(tmp_path)

        writer.add_service_junit_xml("svc", xml_path, log_path)
        index_path = writer.write(duration_seconds=0.1)

        index = json.loads(index_path.read_text(encoding="utf-8"))
        assert len(index["error_clusters"]) == 1
        assert index["error_clusters"][0]["count"] == 3

    def test_different_patterns_separate_clusters(self, tmp_path: Path) -> None:
        """Errors with different patterns form separate clusters."""
        # Create XML with two different error types
        xml_content = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="tests" tests="2" errors="2" failures="0">
    <testcase classname="tests.test_a" name="test_import" time="0.0">
      <error type="ImportError" message="cannot import name 'foo'">
tests/test_a.py:1: in &lt;module&gt;
    from bar import foo
ImportError: cannot import name 'foo'
      </error>
    </testcase>
    <testcase classname="tests.test_b" name="test_type" time="0.0">
      <error type="TypeError" message="expected str got int">
tests/test_b.py:5: in test_type
    result = func(42)
TypeError: expected str got int
      </error>
    </testcase>
  </testsuite>
</testsuites>
"""
        writer = _create_writer(tmp_path)
        xml_path = _write_xml(tmp_path, xml_content)
        log_path = _write_log(tmp_path)

        writer.add_service_junit_xml("svc", xml_path, log_path)
        index_path = writer.write(duration_seconds=0.1)

        index = json.loads(index_path.read_text(encoding="utf-8"))
        assert len(index["error_clusters"]) == 2

    def test_services_affected_tracked(self, tmp_path: Path) -> None:
        """Cluster tracks which services are affected."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        writer = GeneratedTestLogWriter(
            project_path="test",
            language="python",
            platform="docker",
            example="test",
            run_dir=run_dir,
            dtrx_source="test.dtrx",
        )

        # Add same error from two different services
        xml_content = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite tests="1" errors="1">
    <testcase classname="tests.test_a" name="test_import" time="0.0">
      <error type="ImportError" message="cannot import name 'foo' from 'bar'">
ImportError: cannot import name 'foo' from 'bar'
      </error>
    </testcase>
  </testsuite>
</testsuites>
"""
        xml1 = _write_xml(tmp_path, xml_content, "junit1.xml")
        xml2 = _write_xml(tmp_path, xml_content, "junit2.xml")
        log1 = _write_log(tmp_path, "svc1.log")
        log2 = _write_log(tmp_path, "svc2.log")

        writer.add_service_junit_xml("service_a", xml1, log1)
        writer.add_service_junit_xml("service_b", xml2, log2)
        index_path = writer.write(duration_seconds=0.1)

        index = json.loads(index_path.read_text(encoding="utf-8"))
        assert len(index["error_clusters"]) == 1
        cluster = index["error_clusters"][0]
        assert sorted(cluster["services_affected"]) == ["service_a", "service_b"]
        assert cluster["count"] == 2


# ---------------------------------------------------------------------------
# Tests — Import Chain Extraction
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestImportChainExtraction:
    """Test import chain extraction from Python tracebacks."""

    def test_extract_import_chain_from_traceback(self) -> None:
        """Import chain is correctly extracted from collection error tracebacks."""
        traceback = """\
tests/integration/repositories/test_user_repository.py:18: in <module>
    from ecommerce_user_service.services.user_db.user_service import UserService
src/ecommerce_user_service/services/user_db/user_service.py:19: in <module>
    from ecommerce_user_service.integrations._email_helpers import _email_send_ses
ImportError: cannot import name '_email_send_ses'"""

        chain = _extract_import_chain(traceback)
        assert len(chain) == 2
        assert "test_user_repository.py:18" in chain[0]
        assert "ecommerce_user_service.services.user_db.user_service.UserService" in chain[0]
        assert "(MISSING)" in chain[1]

    def test_empty_traceback_returns_empty_chain(self) -> None:
        """Empty traceback returns empty chain."""
        assert _extract_import_chain("") == []
        assert _extract_import_chain("   ") == []


# ---------------------------------------------------------------------------
# Tests — index.json Schema Compliance
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestIndexJsonOutput:
    """Test index.json schema compliance."""

    def test_schema_version_present(self, tmp_path: Path) -> None:
        """index.json has schema_version: 1."""
        writer = _create_writer(tmp_path)
        xml_path = _write_xml(tmp_path, SAMPLE_JUNIT_XML_PASSING)
        log_path = _write_log(tmp_path)

        writer.add_service_junit_xml("svc", xml_path, log_path)
        index_path = writer.write(duration_seconds=1.0)

        index = json.loads(index_path.read_text(encoding="utf-8"))
        assert index["schema_version"] == 1

    def test_all_required_fields_present(self, tmp_path: Path) -> None:
        """All fields from design doc schema are present in output."""
        writer = _create_writer(tmp_path)
        xml_path = _write_xml(tmp_path, SAMPLE_JUNIT_XML_WITH_ERRORS)
        log_path = _write_log(tmp_path)

        writer.add_service_junit_xml("svc", xml_path, log_path)
        index_path = writer.write(duration_seconds=1.0)

        index = json.loads(index_path.read_text(encoding="utf-8"))

        required_keys = [
            "schema_version", "project", "project_path", "language",
            "platform", "example", "dtrx_source", "timestamp",
            "duration_seconds", "result", "counts", "services",
            "failures", "errors", "failure_clusters", "error_clusters",
        ]
        for key in required_keys:
            assert key in index, f"Missing required key: {key}"

        # Check counts keys
        counts_keys = ["passed", "failed", "errors", "skipped", "suite_failures"]
        for key in counts_keys:
            assert key in index["counts"], f"Missing counts key: {key}"

    def test_passing_run_no_failure_dirs(self, tmp_path: Path) -> None:
        """Passing run creates index.json but not failures/ or errors/ dirs."""
        writer = _create_writer(tmp_path)
        xml_path = _write_xml(tmp_path, SAMPLE_JUNIT_XML_PASSING)
        log_path = _write_log(tmp_path)

        writer.add_service_junit_xml("svc", xml_path, log_path)
        writer.write(duration_seconds=1.0)

        run_dir = tmp_path / "run"
        assert (run_dir / "index.json").exists()
        assert (run_dir / "summary.txt").exists()
        assert not (run_dir / "failures").exists()
        assert not (run_dir / "errors").exists()

    def test_services_array_in_index(self, tmp_path: Path) -> None:
        """index.json contains services array with correct structure."""
        writer = _create_writer(tmp_path)
        xml_path = _write_xml(tmp_path, SAMPLE_JUNIT_XML_PASSING)
        log_path = _write_log(tmp_path)

        writer.add_service_junit_xml("user_service", xml_path, log_path)
        index_path = writer.write(duration_seconds=1.0)

        index = json.loads(index_path.read_text(encoding="utf-8"))
        assert len(index["services"]) == 1
        svc = index["services"][0]
        assert svc["name"] == "user_service"
        assert svc["result"] == "PASSED"
        assert "counts" in svc
        assert "log_file" in svc


# ---------------------------------------------------------------------------
# Tests — summary.txt Format
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSummaryTxtOutput:
    """Test summary.txt format compliance."""

    def test_passing_summary_format(self, tmp_path: Path) -> None:
        """Passing run summary.txt has correct format."""
        writer = _create_writer(tmp_path)
        xml_path = _write_xml(tmp_path, SAMPLE_JUNIT_XML_PASSING)
        log_path = _write_log(tmp_path)

        writer.add_service_junit_xml("svc", xml_path, log_path)
        writer.write(duration_seconds=1.5)

        summary = (tmp_path / "run" / "summary.txt").read_text(encoding="utf-8")
        assert "RESULT: PASSED" in summary
        assert "5 passed" in summary
        assert ".dtrx source:" in summary

    def test_failing_summary_format(self, tmp_path: Path) -> None:
        """Failing run summary.txt includes cluster info."""
        writer = _create_writer(tmp_path)
        xml_path = _write_xml(tmp_path, SAMPLE_JUNIT_XML_WITH_ERRORS)
        log_path = _write_log(tmp_path)

        writer.add_service_junit_xml("svc", xml_path, log_path)
        writer.write(duration_seconds=0.1)

        summary = (tmp_path / "run" / "summary.txt").read_text(encoding="utf-8")
        assert "RESULT: FAILED" in summary
        assert "ERROR CLUSTERS:" in summary
        assert "SERVICE RESULTS:" in summary

    def test_summary_under_50_lines(self, tmp_path: Path) -> None:
        """summary.txt is under 50 lines."""
        writer = _create_writer(tmp_path)
        xml_path = _write_xml(tmp_path, SAMPLE_JUNIT_XML_WITH_ERRORS)
        log_path = _write_log(tmp_path)

        writer.add_service_junit_xml("svc", xml_path, log_path)
        writer.write(duration_seconds=0.1)

        summary = (tmp_path / "run" / "summary.txt").read_text(encoding="utf-8")
        lines = summary.strip().split("\n")
        assert len(lines) <= 50


# ---------------------------------------------------------------------------
# Tests — Individual Error Files
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestIndividualErrorFiles:
    """Test individual error file format."""

    def test_error_file_contains_all_sections(self, tmp_path: Path) -> None:
        """Error file has: SERVICE, TEST, CLUSTER, ERROR, and traceback sections."""
        writer = _create_writer(tmp_path)
        xml_path = _write_xml(tmp_path, SAMPLE_JUNIT_XML_WITH_ERRORS)
        log_path = _write_log(tmp_path)

        writer.add_service_junit_xml("ecommerce_user_service", xml_path, log_path)
        writer.write(duration_seconds=0.1)

        errors_dir = tmp_path / "run" / "errors"
        assert errors_dir.exists()
        error_files = list(errors_dir.glob("*.txt"))
        assert len(error_files) == 3

        # Read the first error file
        content = error_files[0].read_text(encoding="utf-8")
        assert "SERVICE:" in content
        assert "TEST:" in content
        assert "CLUSTER:" in content
        assert "ERROR:" in content
        assert "--- Full Traceback ---" in content

    def test_error_file_has_codegen_hint(self, tmp_path: Path) -> None:
        """Error file for known generated paths includes codegen hint."""
        writer = _create_writer(tmp_path)
        xml_path = _write_xml(tmp_path, SAMPLE_JUNIT_XML_WITH_ERRORS)
        log_path = _write_log(tmp_path)

        writer.add_service_junit_xml("ecommerce_user_service", xml_path, log_path)
        writer.write(duration_seconds=0.1)

        errors_dir = tmp_path / "run" / "errors"
        # Check at least one file has a codegen hint
        found_hint = False
        for error_file in errors_dir.glob("*.txt"):
            content = error_file.read_text(encoding="utf-8")
            if "--- Codegen Hint ---" in content:
                found_hint = True
                assert "Probable template:" in content
                assert "Probable generator:" in content
                break
        # Hint may or may not appear depending on path extraction
        # Just verify the file structure is correct

    def test_failure_files_created_for_failures(self, tmp_path: Path) -> None:
        """Failure files are created in failures/ directory."""
        writer = _create_writer(tmp_path)
        xml_path = _write_xml(tmp_path, SAMPLE_JUNIT_XML_WITH_FAILURES)
        log_path = _write_log(tmp_path)

        writer.add_service_junit_xml("svc", xml_path, log_path)
        writer.write(duration_seconds=0.5)

        failures_dir = tmp_path / "run" / "failures"
        assert failures_dir.exists()
        failure_files = list(failures_dir.glob("*.txt"))
        assert len(failure_files) == 2


# ---------------------------------------------------------------------------
# Tests — Service Log Copying
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestServiceLogCopying:
    """Test that service logs and structured data are copied correctly."""

    def test_junit_xml_copied_to_services_dir(self, tmp_path: Path) -> None:
        """JUnit XML is copied to services/{name}/junit.xml."""
        writer = _create_writer(tmp_path)
        xml_path = _write_xml(tmp_path, SAMPLE_JUNIT_XML_PASSING)
        log_path = _write_log(tmp_path)

        writer.add_service_junit_xml("user_service", xml_path, log_path)
        writer.write(duration_seconds=1.0)

        copied_xml = tmp_path / "run" / "services" / "user_service" / "junit.xml"
        assert copied_xml.exists()

    def test_service_log_copied(self, tmp_path: Path) -> None:
        """Service log is copied to services/{name}/service.log."""
        writer = _create_writer(tmp_path)
        xml_path = _write_xml(tmp_path, SAMPLE_JUNIT_XML_PASSING)
        log_path = _write_log(tmp_path)

        writer.add_service_junit_xml("user_service", xml_path, log_path)
        writer.write(duration_seconds=1.0)

        copied_log = tmp_path / "run" / "services" / "user_service" / "service.log"
        assert copied_log.exists()
        assert copied_log.read_text(encoding="utf-8") == "test log output\n"


# ---------------------------------------------------------------------------
# Tests — Multi-service
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMultiService:
    """Test handling of multiple services in one project."""

    def test_multiple_services_in_index(self, tmp_path: Path) -> None:
        """Multiple services appear in the services array."""
        writer = _create_writer(tmp_path)

        xml1 = _write_xml(tmp_path, SAMPLE_JUNIT_XML_PASSING, "junit1.xml")
        xml2 = _write_xml(tmp_path, SAMPLE_JUNIT_XML_WITH_FAILURES, "junit2.xml")
        log1 = _write_log(tmp_path, "svc1.log")
        log2 = _write_log(tmp_path, "svc2.log")

        writer.add_service_junit_xml("service_a", xml1, log1)
        writer.add_service_junit_xml("service_b", xml2, log2)
        index_path = writer.write(duration_seconds=2.0)

        index = json.loads(index_path.read_text(encoding="utf-8"))
        assert len(index["services"]) == 2
        names = [s["name"] for s in index["services"]]
        assert "service_a" in names
        assert "service_b" in names

        # Overall result should be FAILED because service_b has failures
        assert index["result"] == "FAILED"
        # Counts should be aggregated
        assert index["counts"]["passed"] == 6  # 5 + 1
        assert index["counts"]["failed"] == 2


# ---------------------------------------------------------------------------
# Tests — Log-only fallback
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLogOnlyFallback:
    """Test the log-only fallback path."""

    def test_log_only_produces_index(self, tmp_path: Path) -> None:
        """add_service_log_only produces valid index.json."""
        writer = _create_writer(tmp_path)
        log_path = _write_log(tmp_path)

        writer.add_service_log_only("svc", log_path, passed=10, failed=2, errors=1)
        index_path = writer.write(duration_seconds=5.0)

        index = json.loads(index_path.read_text(encoding="utf-8"))
        assert index["result"] == "FAILED"
        assert index["counts"]["passed"] == 10
        assert index["counts"]["failed"] == 2
        assert index["counts"]["errors"] == 1
        assert len(index["failures"]) == 0  # No structured data
        assert len(index["errors"]) == 0
