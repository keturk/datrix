"""Tests for StructuredLogWriter.

Uses real JUnit XML fixtures and real file I/O — no mocks, no fakes.
"""

import json
from datetime import datetime
from pathlib import Path

import pytest

from shared.structured_log_writer import (
    SourceLocation,
    StructuredLogWriter,
    TestCaseResult,
    _MAX_FILENAME_BODY_LENGTH,
)

# ---------------------------------------------------------------------------
# JUnit XML fixtures
# ---------------------------------------------------------------------------

SAMPLE_JUNIT_PARALLEL = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="parallel" tests="4" errors="0" failures="1" skipped="1" time="3.5">
    <testcase classname="tests.test_foo.TestBar" name="test_pass" time="0.5"/>
    <testcase classname="tests.test_foo.TestBar" name="test_fail" time="1.0">
      <failure type="AssertionError" message="assert 1 == 2">
tests/test_foo.py:10: in test_fail
    assert 1 == 2
E   AssertionError: assert 1 == 2
      </failure>
    </testcase>
    <testcase classname="tests.test_baz.TestQux" name="test_error" time="1.0">
      <error type="ImportError" message="No module named 'missing'">
tests/test_baz.py:1: in &lt;module&gt;
    import missing
E   ImportError: No module named 'missing'
      </error>
    </testcase>
    <testcase classname="tests.test_foo.TestBar" name="test_skip" time="0.0">
      <skipped message="skipped reason"/>
    </testcase>
  </testsuite>
</testsuites>
"""

SAMPLE_JUNIT_SERIAL = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="serial" tests="2" errors="0" failures="1" skipped="0" time="2.0">
    <testcase classname="tests.test_serial.TestSerial" name="test_serial_pass" time="0.5"/>
    <testcase classname="tests.test_serial.TestSerial" name="test_serial_fail" time="1.5">
      <failure type="ValueError" message="bad value 42">
tests/test_serial.py:20: in test_serial_fail
    raise ValueError("bad value 42")
src/mylib/core.py:55: in compute
    return x / 0
E   ValueError: bad value 42
      </failure>
    </testcase>
  </testsuite>
</testsuites>
"""

SAMPLE_JUNIT_ALL_PASS = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="all" tests="3" errors="0" failures="0" skipped="0" time="1.5">
    <testcase classname="tests.test_ok.TestOk" name="test_one" time="0.5"/>
    <testcase classname="tests.test_ok.TestOk" name="test_two" time="0.5"/>
    <testcase classname="tests.test_ok.TestOk" name="test_three" time="0.5"/>
  </testsuite>
</testsuites>
"""

TRUNCATED_JUNIT_XML = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="parallel" tests="3"
"""

# Multiple failures that should cluster together (same error + source)
CLUSTERABLE_FAILURES_XML = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="parallel" tests="6" errors="0" failures="4" skipped="0" time="4.0">
    <testcase classname="tests.transpiler.test_ctx.TestA" name="test_alpha" time="0.5">
      <failure type="GenerationError" message="Undefined identifier 'foo'">
tests/transpiler/test_ctx.py:10: in test_alpha
    out = transpile(expr)
src/datrix_common/transpiler/visitor.py:243: in transpile_expression
    raise GenerationError("Undefined identifier 'foo'")
E   GenerationError: Undefined identifier 'foo'
      </failure>
    </testcase>
    <testcase classname="tests.transpiler.test_ctx.TestA" name="test_beta" time="0.5">
      <failure type="GenerationError" message="Undefined identifier 'bar'">
tests/transpiler/test_ctx.py:20: in test_beta
    out = transpile(expr)
src/datrix_common/transpiler/visitor.py:243: in transpile_expression
    raise GenerationError("Undefined identifier 'bar'")
E   GenerationError: Undefined identifier 'bar'
      </failure>
    </testcase>
    <testcase classname="tests.transpiler.test_ctx.TestA" name="test_gamma" time="0.5">
      <failure type="GenerationError" message="Undefined identifier 'baz'">
tests/transpiler/test_ctx.py:30: in test_gamma
    out = transpile(expr)
src/datrix_common/transpiler/visitor.py:243: in transpile_expression
    raise GenerationError("Undefined identifier 'baz'")
E   GenerationError: Undefined identifier 'baz'
      </failure>
    </testcase>
    <testcase classname="tests.transpiler.test_other.TestB" name="test_different" time="0.5">
      <failure type="AttributeError" message="'NoneType' object has no attribute 'name'">
tests/transpiler/test_other.py:5: in test_different
    result = obj.name
src/datrix_common/transpiler/dispatch.py:63: in dispatch
    return target.name
E   AttributeError: 'NoneType' object has no attribute 'name'
      </failure>
    </testcase>
    <testcase classname="tests.transpiler.test_ctx.TestA" name="test_pass1" time="0.5"/>
    <testcase classname="tests.transpiler.test_other.TestB" name="test_pass2" time="0.5"/>
  </testsuite>
</testsuites>
"""

# Error clustering XML (import errors)
ERROR_CLUSTERING_XML = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="parallel" tests="4" errors="3" failures="0" skipped="0" time="1.0">
    <testcase classname="tests.test_import1.TestImport1" name="test_a" time="0.1">
      <error type="ImportError" message="cannot import name 'Widget' from 'mylib'">
tests/test_import1.py:1: in &lt;module&gt;
    from mylib import Widget
src/mylib/__init__.py:12: in &lt;module&gt;
    from mylib.widget import Widget
E   ImportError: cannot import name 'Widget' from 'mylib'
      </error>
    </testcase>
    <testcase classname="tests.test_import2.TestImport2" name="test_b" time="0.1">
      <error type="ImportError" message="cannot import name 'Gadget' from 'mylib'">
tests/test_import2.py:1: in &lt;module&gt;
    from mylib import Gadget
src/mylib/__init__.py:12: in &lt;module&gt;
    from mylib.gadget import Gadget
E   ImportError: cannot import name 'Gadget' from 'mylib'
      </error>
    </testcase>
    <testcase classname="tests.test_import3.TestImport3" name="test_c" time="0.1">
      <error type="ImportError" message="cannot import name 'Thingy' from 'mylib'">
tests/test_import3.py:1: in &lt;module&gt;
    from mylib import Thingy
src/mylib/__init__.py:12: in &lt;module&gt;
    from mylib.thingy import Thingy
E   ImportError: cannot import name 'Thingy' from 'mylib'
      </error>
    </testcase>
    <testcase classname="tests.test_ok.TestOk" name="test_ok" time="0.1"/>
  </testsuite>
</testsuites>
"""

# Source location fallback scenarios
SOURCE_LOCATION_PROJECT_FRAME_XML = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="all" tests="1" errors="0" failures="1" time="0.5">
    <testcase classname="tests.test_loc.TestLoc" name="test_project_frame" time="0.5">
      <failure type="RuntimeError" message="boom">
tests/test_loc.py:10: in test_project_frame
    result = compute()
src/mylib/engine.py:42: in compute
    raise RuntimeError("boom")
E   RuntimeError: boom
      </failure>
    </testcase>
  </testsuite>
</testsuites>
"""

SOURCE_LOCATION_TEST_ONLY_XML = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="all" tests="1" errors="0" failures="1" time="0.5">
    <testcase classname="tests.test_loc.TestLoc" name="test_only_test_frame" time="0.5">
      <failure type="AssertionError" message="assert False">
tests/test_loc.py:15: in test_only_test_frame
    assert False
E   AssertionError: assert False
      </failure>
    </testcase>
  </testsuite>
</testsuites>
"""

SOURCE_LOCATION_STDLIB_ONLY_XML = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="all" tests="1" errors="0" failures="1" time="0.5">
    <testcase classname="tests.test_loc.TestLoc" name="test_stdlib_only" time="0.5">
      <failure type="TypeError" message="bad type">
/usr/lib/python3.14/json/__init__.py:100: in loads
    return _default_decoder.decode(s)
E   TypeError: bad type
      </failure>
    </testcase>
  </testsuite>
</testsuites>
"""

SOURCE_LOCATION_NO_TRACEBACK_XML = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="all" tests="1" errors="0" failures="1" time="0.5">
    <testcase classname="tests.test_loc.TestLoc" name="test_no_traceback" time="0.5">
      <failure type="SomeError" message="no frames"/>
    </testcase>
  </testsuite>
</testsuites>
"""

# Normalization testing XML
NORMALIZATION_XML = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="all" tests="4" errors="0" failures="4" time="2.0">
    <testcase classname="tests.test_norm.TestNorm" name="test_single_quote" time="0.5">
      <failure type="KeyError" message="key 'my_key' not found">
tests/test_norm.py:10: in test_single_quote
    d['my_key']
E   KeyError: key 'my_key' not found
      </failure>
    </testcase>
    <testcase classname="tests.test_norm.TestNorm" name="test_double_quote" time="0.5">
      <failure type="KeyError" message='key "other_key" not found'>
tests/test_norm.py:20: in test_double_quote
    d["other_key"]
E   KeyError: key "other_key" not found
      </failure>
    </testcase>
    <testcase classname="tests.test_norm.TestNorm" name="test_hex_addr" time="0.5">
      <failure type="RuntimeError" message="object at 0x7f1234abcdef is invalid">
tests/test_norm.py:30: in test_hex_addr
    check(obj)
E   RuntimeError: object at 0x7f1234abcdef is invalid
      </failure>
    </testcase>
    <testcase classname="tests.test_norm.TestNorm" name="test_numbers" time="0.5">
      <failure type="IndexError" message="list index 42 out of range 10">
tests/test_norm.py:40: in test_numbers
    lst[42]
E   IndexError: list index 42 out of range 10
      </failure>
    </testcase>
  </testsuite>
</testsuites>
"""

# Long test name for filename truncation
LONG_NAME_XML = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="all" tests="2" errors="0" failures="2" time="1.0">
    <testcase classname="tests.very_long_module_name_that_goes_on_and_on.TestExtremelyDescriptiveClassName" name="test_also_a_very_descriptive_name_that_keeps_going_and_going_until_it_exceeds_the_limit" time="0.5">
      <failure type="AssertionError" message="nope">
tests/very_long_module_name_that_goes_on_and_on.py:10: in test_also_a_very_descriptive_name_that_keeps_going_and_going_until_it_exceeds_the_limit
    assert False
E   AssertionError: nope
      </failure>
    </testcase>
    <testcase classname="tests.test_short.T" name="test_ok" time="0.5">
      <failure type="AssertionError" message="nah">
tests/test_short.py:5: in test_ok
    assert False
E   AssertionError: nah
      </failure>
    </testcase>
  </testsuite>
</testsuites>
"""

# Empty classname edge case
EMPTY_CLASSNAME_XML = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="all" tests="1" errors="0" failures="1" time="0.5">
    <testcase classname="" name="test_no_class" time="0.5">
      <failure type="AssertionError" message="fail">
E   AssertionError: fail
      </failure>
    </testcase>
  </testsuite>
</testsuites>
"""

# Parametrized test variants that should cluster
PARAMETRIZED_XML = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="all" tests="3" errors="0" failures="3" time="1.5">
    <testcase classname="tests.test_param.TestParam" name="test_convert[int]" time="0.5">
      <failure type="GenerationError" message="Undefined identifier 'param1'">
tests/test_param.py:10: in test_convert[int]
    result = convert(expr)
src/converter.py:20: in convert
    raise GenerationError("Undefined identifier 'param1'")
E   GenerationError: Undefined identifier 'param1'
      </failure>
    </testcase>
    <testcase classname="tests.test_param.TestParam" name="test_convert[str]" time="0.5">
      <failure type="GenerationError" message="Undefined identifier 'param2'">
tests/test_param.py:10: in test_convert[str]
    result = convert(expr)
src/converter.py:20: in convert
    raise GenerationError("Undefined identifier 'param2'")
E   GenerationError: Undefined identifier 'param2'
      </failure>
    </testcase>
    <testcase classname="tests.test_param.TestParam" name="test_convert[float]" time="0.5">
      <failure type="GenerationError" message="Undefined identifier 'param3'">
tests/test_param.py:10: in test_convert[float]
    result = convert(expr)
src/converter.py:20: in convert
    raise GenerationError("Undefined identifier 'param3'")
E   GenerationError: Undefined identifier 'param3'
      </failure>
    </testcase>
  </testsuite>
</testsuites>
"""

# Fixture for system-out and system-err
STDOUT_STDERR_XML = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="all" tests="1" errors="0" failures="1" time="0.5">
    <testcase classname="tests.test_io.TestIO" name="test_with_output" time="0.5">
      <failure type="AssertionError" message="output mismatch">
tests/test_io.py:10: in test_with_output
    assert output == expected
E   AssertionError: output mismatch
      </failure>
      <system-out>this is stdout content
line 2 of stdout</system-out>
      <system-err>this is stderr content
line 2 of stderr</system-err>
    </testcase>
  </testsuite>
</testsuites>
"""

# Conftest frame (non-test, non-project)
SOURCE_LOCATION_CONFTEST_XML = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="all" tests="1" errors="1" failures="0" time="0.5">
    <testcase classname="tests.test_fixture.TestFixture" name="test_needs_fixture" time="0.5">
      <error type="RuntimeError" message="fixture setup failed">
tests/conftest.py:25: in my_fixture
    raise RuntimeError("fixture setup failed")
E   RuntimeError: fixture setup failed
      </error>
    </testcase>
  </testsuite>
</testsuites>
"""


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _write_xml(tmp_path: Path, filename: str, content: str) -> Path:
    """Write XML content to a file in tmp_path and return its path."""
    path = tmp_path / filename
    path.write_text(content, encoding="utf-8")
    return path


def _read_index(run_dir: Path) -> dict:
    """Read and parse the index.json from a run directory."""
    index_path = run_dir / "index.json"
    return json.loads(index_path.read_text(encoding="utf-8"))


TIMESTAMP = datetime(2026, 5, 3, 19, 10, 2)


# ===========================================================================
# 1. Happy path — single XML file with failures
# ===========================================================================


class TestHappyPath:
    """Happy path: single XML with mixed pass/fail/error results."""

    def test_index_json_schema(self, tmp_path: Path) -> None:
        """index.json has all required fields with correct types."""
        xml_path = _write_xml(tmp_path, "junit.xml", SAMPLE_JUNIT_PARALLEL)
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        writer = StructuredLogWriter("test-project", run_dir)
        result_path = writer.write([xml_path], TIMESTAMP)

        assert result_path == run_dir / "index.json"
        index = _read_index(run_dir)

        assert index["schema_version"] == 1
        assert index["project"] == "test-project"
        assert index["timestamp"] == "2026-05-03T19:10:02"
        assert isinstance(index["duration_seconds"], (int, float))
        assert index["result"] == "FAILED"
        assert isinstance(index["counts"], dict)
        assert index["counts"]["passed"] == 1
        assert index["counts"]["failed"] == 1
        assert index["counts"]["error"] == 1
        assert index["counts"]["skipped"] == 1
        assert isinstance(index["failures"], list)
        assert isinstance(index["errors"], list)
        assert isinstance(index["failure_clusters"], list)
        assert isinstance(index["error_clusters"], list)

    def test_failure_entry_fields(self, tmp_path: Path) -> None:
        """Each failure entry has required fields."""
        xml_path = _write_xml(tmp_path, "junit.xml", SAMPLE_JUNIT_PARALLEL)
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        writer = StructuredLogWriter("test-project", run_dir)
        writer.write([xml_path], TIMESTAMP)
        index = _read_index(run_dir)

        assert len(index["failures"]) == 1
        failure = index["failures"][0]
        assert "id" in failure
        assert "test_id" in failure
        assert "file" in failure
        assert "class" in failure
        assert "function" in failure
        assert "error_type" in failure
        assert "error_message" in failure
        assert "source_location" in failure
        assert "log_file" in failure

    def test_summary_txt_created(self, tmp_path: Path) -> None:
        """summary.txt is created and contains expected content."""
        xml_path = _write_xml(tmp_path, "junit.xml", SAMPLE_JUNIT_PARALLEL)
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        writer = StructuredLogWriter("test-project", run_dir)
        writer.write([xml_path], TIMESTAMP)

        summary_path = run_dir / "summary.txt"
        assert summary_path.exists()
        content = summary_path.read_text(encoding="utf-8")
        assert "test-project test results" in content
        assert "RESULT: FAILED" in content
        assert len(content.splitlines()) <= 50

    def test_failure_files_created(self, tmp_path: Path) -> None:
        """Individual failure files are created in the failures/ directory."""
        xml_path = _write_xml(tmp_path, "junit.xml", SAMPLE_JUNIT_PARALLEL)
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        writer = StructuredLogWriter("test-project", run_dir)
        writer.write([xml_path], TIMESTAMP)

        failures_dir = run_dir / "failures"
        assert failures_dir.exists()
        failure_files = list(failures_dir.glob("*.txt"))
        assert len(failure_files) == 1

        content = failure_files[0].read_text(encoding="utf-8")
        assert content.startswith("TEST: ")
        assert "CLUSTER:" in content
        assert "ERROR:" in content
        assert "--- Traceback ---" in content

    def test_error_files_created(self, tmp_path: Path) -> None:
        """Individual error files are created in the errors/ directory."""
        xml_path = _write_xml(tmp_path, "junit.xml", SAMPLE_JUNIT_PARALLEL)
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        writer = StructuredLogWriter("test-project", run_dir)
        writer.write([xml_path], TIMESTAMP)

        errors_dir = run_dir / "errors"
        assert errors_dir.exists()
        error_files = list(errors_dir.glob("*.txt"))
        assert len(error_files) == 1

        content = error_files[0].read_text(encoding="utf-8")
        assert "ImportError" in content

    def test_schema_version_is_one(self, tmp_path: Path) -> None:
        """schema_version field is exactly 1."""
        xml_path = _write_xml(tmp_path, "junit.xml", SAMPLE_JUNIT_PARALLEL)
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        writer = StructuredLogWriter("test-project", run_dir)
        writer.write([xml_path], TIMESTAMP)
        index = _read_index(run_dir)

        assert index["schema_version"] == 1


# ===========================================================================
# 2. Two-phase merge
# ===========================================================================


class TestTwoPhaseMerge:
    """Two-phase merge: parallel + serial XML files."""

    def test_both_phases_merged(self, tmp_path: Path) -> None:
        """Both parallel and serial XML are merged into one index."""
        parallel_xml = _write_xml(
            tmp_path, "junit-parallel.xml", SAMPLE_JUNIT_PARALLEL
        )
        serial_xml = _write_xml(
            tmp_path, "junit-serial.xml", SAMPLE_JUNIT_SERIAL
        )
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        writer = StructuredLogWriter("test-project", run_dir)
        writer.write([parallel_xml, serial_xml], TIMESTAMP)
        index = _read_index(run_dir)

        # Parallel: 1 pass + 1 fail + 1 error + 1 skip = 4
        # Serial:   1 pass + 1 fail = 2
        # Total:    2 pass + 2 fail + 1 error + 1 skip = 6
        assert index["counts"]["passed"] == 2
        assert index["counts"]["failed"] == 2
        assert index["counts"]["error"] == 1
        assert index["counts"]["skipped"] == 1

    def test_only_parallel_exists(self, tmp_path: Path) -> None:
        """Only parallel XML exists — serial is missing."""
        parallel_xml = _write_xml(
            tmp_path, "junit-parallel.xml", SAMPLE_JUNIT_PARALLEL
        )
        missing_serial = tmp_path / "junit-serial.xml"  # Does not exist
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        writer = StructuredLogWriter("test-project", run_dir)
        writer.write([parallel_xml, missing_serial], TIMESTAMP)
        index = _read_index(run_dir)

        # Only parallel results
        assert index["counts"]["passed"] == 1
        assert index["counts"]["failed"] == 1
        assert index["result"] == "FAILED"

    def test_only_serial_exists(self, tmp_path: Path) -> None:
        """Only serial XML exists — parallel is missing."""
        missing_parallel = tmp_path / "junit-parallel.xml"  # Does not exist
        serial_xml = _write_xml(
            tmp_path, "junit-serial.xml", SAMPLE_JUNIT_SERIAL
        )
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        writer = StructuredLogWriter("test-project", run_dir)
        writer.write([missing_parallel, serial_xml], TIMESTAMP)
        index = _read_index(run_dir)

        assert index["counts"]["passed"] == 1
        assert index["counts"]["failed"] == 1
        assert index["result"] == "FAILED"


# ===========================================================================
# 3. Missing/corrupt XML
# ===========================================================================


class TestMissingCorruptXml:
    """Missing/corrupt XML handling."""

    def test_no_xml_files_exist(self, tmp_path: Path) -> None:
        """No XML files exist — INCOMPLETE index is written."""
        missing_a = tmp_path / "missing-a.xml"
        missing_b = tmp_path / "missing-b.xml"
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        writer = StructuredLogWriter("test-project", run_dir)
        writer.write([missing_a, missing_b], TIMESTAMP)
        index = _read_index(run_dir)

        assert index["result"] == "INCOMPLETE"
        assert "note" in index
        assert index["counts"] is None
        assert index["failures"] == []
        assert index["errors"] == []
        assert index["failure_clusters"] == []
        assert index["error_clusters"] == []

    def test_truncated_xml(self, tmp_path: Path) -> None:
        """Truncated XML — INCOMPLETE index with note."""
        truncated_path = _write_xml(
            tmp_path, "junit.xml", TRUNCATED_JUNIT_XML
        )
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        writer = StructuredLogWriter("test-project", run_dir)
        writer.write([truncated_path], TIMESTAMP)
        index = _read_index(run_dir)

        assert index["result"] == "INCOMPLETE"
        assert index["schema_version"] == 1

    def test_one_valid_one_corrupt(self, tmp_path: Path) -> None:
        """One valid + one corrupt XML — partial results from valid file."""
        valid_xml = _write_xml(
            tmp_path, "junit-parallel.xml", SAMPLE_JUNIT_PARALLEL
        )
        corrupt_xml = _write_xml(
            tmp_path, "junit-serial.xml", TRUNCATED_JUNIT_XML
        )
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        writer = StructuredLogWriter("test-project", run_dir)
        writer.write([valid_xml, corrupt_xml], TIMESTAMP)
        index = _read_index(run_dir)

        # Should process valid XML and skip corrupt one
        assert index["result"] == "FAILED"
        assert index["counts"]["passed"] == 1
        assert index["counts"]["failed"] == 1

    def test_empty_xml_file(self, tmp_path: Path) -> None:
        """Empty XML file is treated as missing."""
        empty_path = tmp_path / "junit.xml"
        empty_path.write_text("", encoding="utf-8")
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        writer = StructuredLogWriter("test-project", run_dir)
        writer.write([empty_path], TIMESTAMP)
        index = _read_index(run_dir)

        assert index["result"] == "INCOMPLETE"


# ===========================================================================
# 4. Clustering
# ===========================================================================


class TestClustering:
    """Failure and error clustering."""

    def test_same_error_type_and_source_cluster_together(
        self, tmp_path: Path
    ) -> None:
        """Multiple failures with same error type + source location cluster."""
        xml_path = _write_xml(
            tmp_path, "junit.xml", CLUSTERABLE_FAILURES_XML
        )
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        writer = StructuredLogWriter("test-project", run_dir)
        writer.write([xml_path], TIMESTAMP)
        index = _read_index(run_dir)

        # Should have 2 failure clusters:
        # 1. GenerationError cluster (3 failures)
        # 2. AttributeError cluster (1 failure)
        assert len(index["failure_clusters"]) == 2

        # Sort by count descending
        clusters = sorted(
            index["failure_clusters"],
            key=lambda c: c["count"],
            reverse=True,
        )
        assert clusters[0]["count"] == 3
        assert "GenerationError" in clusters[0]["pattern"]
        assert clusters[1]["count"] == 1
        assert "AttributeError" in clusters[1]["pattern"]

    def test_different_source_locations_dont_cluster(
        self, tmp_path: Path
    ) -> None:
        """Failures with different source locations form separate clusters."""
        xml_path = _write_xml(
            tmp_path, "junit.xml", CLUSTERABLE_FAILURES_XML
        )
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        writer = StructuredLogWriter("test-project", run_dir)
        writer.write([xml_path], TIMESTAMP)
        index = _read_index(run_dir)

        # GenerationError and AttributeError have different source locations
        cluster_sources = {
            c["source_location"] for c in index["failure_clusters"]
        }
        assert len(cluster_sources) == 2

    def test_representative_is_alphabetically_first(
        self, tmp_path: Path
    ) -> None:
        """Representative failure is the first by alphabetical test_id."""
        xml_path = _write_xml(
            tmp_path, "junit.xml", CLUSTERABLE_FAILURES_XML
        )
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        writer = StructuredLogWriter("test-project", run_dir)
        writer.write([xml_path], TIMESTAMP)
        index = _read_index(run_dir)

        # Find the GenerationError cluster (3 members)
        gen_cluster = next(
            c
            for c in index["failure_clusters"]
            if "GenerationError" in c["pattern"]
        )
        rep_id = gen_cluster["representative_failure_id"]

        # Find the representative failure
        rep_failure = next(
            f for f in index["failures"] if f["id"] == rep_id
        )

        # The alphabetically first test_id among alpha/beta/gamma
        # is test_alpha
        assert "test_alpha" in rep_failure["test_id"]

    def test_error_clustering_import_errors(
        self, tmp_path: Path
    ) -> None:
        """Import errors cluster together by normalized message + source."""
        xml_path = _write_xml(
            tmp_path, "junit.xml", ERROR_CLUSTERING_XML
        )
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        writer = StructuredLogWriter("test-project", run_dir)
        writer.write([xml_path], TIMESTAMP)
        index = _read_index(run_dir)

        assert len(index["errors"]) == 3
        # All 3 import errors should cluster (same error type + same source)
        assert len(index["error_clusters"]) == 1
        assert index["error_clusters"][0]["count"] == 3
        assert "ImportError" in index["error_clusters"][0]["pattern"]


# ===========================================================================
# 5. Source location extraction
# ===========================================================================


class TestSourceLocationExtraction:
    """Source location extraction with fallback chain."""

    def test_project_source_frame(self, tmp_path: Path) -> None:
        """Traceback with project source frame picks the project frame."""
        xml_path = _write_xml(
            tmp_path, "junit.xml", SOURCE_LOCATION_PROJECT_FRAME_XML
        )
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        writer = StructuredLogWriter("test-project", run_dir)
        writer.write([xml_path], TIMESTAMP)
        index = _read_index(run_dir)

        failure = index["failures"][0]
        assert "src/mylib/engine.py:42" in failure["source_location"]

    def test_test_frame_fallback(self, tmp_path: Path) -> None:
        """Traceback with only test frames falls back to test frame."""
        xml_path = _write_xml(
            tmp_path, "junit.xml", SOURCE_LOCATION_TEST_ONLY_XML
        )
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        writer = StructuredLogWriter("test-project", run_dir)
        writer.write([xml_path], TIMESTAMP)
        index = _read_index(run_dir)

        failure = index["failures"][0]
        assert "tests/test_loc.py:15" in failure["source_location"]

    def test_stdlib_only_fallback(self, tmp_path: Path) -> None:
        """Traceback with only stdlib frames falls back to unknown:0."""
        xml_path = _write_xml(
            tmp_path, "junit.xml", SOURCE_LOCATION_STDLIB_ONLY_XML
        )
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        writer = StructuredLogWriter("test-project", run_dir)
        writer.write([xml_path], TIMESTAMP)
        index = _read_index(run_dir)

        failure = index["failures"][0]
        assert failure["source_location"] == "unknown:0"

    def test_no_traceback_returns_unknown(self, tmp_path: Path) -> None:
        """No parseable traceback returns unknown:0."""
        xml_path = _write_xml(
            tmp_path, "junit.xml", SOURCE_LOCATION_NO_TRACEBACK_XML
        )
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        writer = StructuredLogWriter("test-project", run_dir)
        writer.write([xml_path], TIMESTAMP)
        index = _read_index(run_dir)

        failure = index["failures"][0]
        assert failure["source_location"] == "unknown:0"

    def test_conftest_frame_fallback(self, tmp_path: Path) -> None:
        """Conftest frame is treated as a test path (fallback to test)."""
        xml_path = _write_xml(
            tmp_path, "junit.xml", SOURCE_LOCATION_CONFTEST_XML
        )
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        writer = StructuredLogWriter("test-project", run_dir)
        writer.write([xml_path], TIMESTAMP)
        index = _read_index(run_dir)

        error = index["errors"][0]
        # conftest.py is classified as a test path, so it should be picked up
        assert "conftest.py:25" in error["source_location"]


# ===========================================================================
# 6. Message normalization
# ===========================================================================


class TestMessageNormalization:
    """Normalization replaces quoted strings, hex, and numbers with *."""

    def test_single_quoted_strings_replaced(
        self, tmp_path: Path
    ) -> None:
        """Single-quoted strings are replaced with *."""
        writer = StructuredLogWriter("test", tmp_path)
        result = writer._normalize_error_message(
            "KeyError", "key 'my_key' not found"
        )
        assert result == "KeyError: key * not found"

    def test_double_quoted_strings_replaced(
        self, tmp_path: Path
    ) -> None:
        """Double-quoted strings are replaced with *."""
        writer = StructuredLogWriter("test", tmp_path)
        result = writer._normalize_error_message(
            "KeyError", 'key "other_key" not found'
        )
        assert result == "KeyError: key * not found"

    def test_hex_addresses_replaced(self, tmp_path: Path) -> None:
        """Hex addresses are replaced with *."""
        writer = StructuredLogWriter("test", tmp_path)
        result = writer._normalize_error_message(
            "RuntimeError", "object at 0x7f1234abcdef is invalid"
        )
        assert result == "RuntimeError: object at * is invalid"

    def test_numbers_replaced(self, tmp_path: Path) -> None:
        """Standalone numbers are replaced with *."""
        writer = StructuredLogWriter("test", tmp_path)
        result = writer._normalize_error_message(
            "IndexError", "list index 42 out of range 10"
        )
        assert result == "IndexError: list index * out of range *"

    def test_parametrized_variants_cluster(
        self, tmp_path: Path
    ) -> None:
        """Parametrized test variants cluster together after normalization."""
        xml_path = _write_xml(
            tmp_path, "junit.xml", PARAMETRIZED_XML
        )
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        writer = StructuredLogWriter("test-project", run_dir)
        writer.write([xml_path], TIMESTAMP)
        index = _read_index(run_dir)

        # All 3 parametrized failures should cluster into 1
        assert len(index["failure_clusters"]) == 1
        assert index["failure_clusters"][0]["count"] == 3


# ===========================================================================
# 7. Filename truncation
# ===========================================================================


class TestFilenameTruncation:
    """Filename truncation at _MAX_FILENAME_BODY_LENGTH chars."""

    def test_short_name_no_truncation(self, tmp_path: Path) -> None:
        """Short names (under 120 chars) are not truncated."""
        writer = StructuredLogWriter("test", tmp_path)
        tc = TestCaseResult(
            test_id="tests.test_foo.TestBar::test_ok",
            file="tests/test_foo.py",
            classname="tests.test_foo.TestBar",
            function="test_ok",
            duration=0.5,
            outcome="failed",
        )
        filename = writer._make_filename(1, tc)
        # Should not have a hash suffix
        assert filename == "001-tests-test_foo-TestBar-test_ok.txt"

    def test_long_name_truncated_with_hash(
        self, tmp_path: Path
    ) -> None:
        """Long names are truncated at word boundary + hash suffix."""
        writer = StructuredLogWriter("test", tmp_path)
        tc = TestCaseResult(
            test_id="tests.very_long_module_name_that_goes_on_and_on."
            "TestExtremelyDescriptiveClassName::"
            "test_also_a_very_descriptive_name_that_keeps_going_"
            "and_going_until_it_exceeds_the_limit",
            file="tests/very_long.py",
            classname="tests.very_long_module_name_that_goes_on_and_on."
            "TestExtremelyDescriptiveClassName",
            function="test_also_a_very_descriptive_name_that_keeps_going_"
            "and_going_until_it_exceeds_the_limit",
            duration=0.5,
            outcome="failed",
        )
        filename = writer._make_filename(1, tc)

        # Body (between "001-" and ".txt") should be <= 120 + 1 + 8 = 129
        body = filename[4:-4]  # strip "001-" and ".txt"
        # The body itself before truncation would be > 120 chars
        assert len(body) <= _MAX_FILENAME_BODY_LENGTH + 9  # +9 for "-" + 8 hash

    def test_hash_is_deterministic(self, tmp_path: Path) -> None:
        """Same test_id always produces the same hash."""
        writer = StructuredLogWriter("test", tmp_path)
        tc = TestCaseResult(
            test_id="tests.very_long_module_name_that_goes_on_and_on."
            "TestExtremelyDescriptiveClassName::"
            "test_also_a_very_descriptive_name_that_keeps_going_"
            "and_going_until_it_exceeds_the_limit",
            file="tests/very_long.py",
            classname="tests.very_long_module_name_that_goes_on_and_on."
            "TestExtremelyDescriptiveClassName",
            function="test_also_a_very_descriptive_name_that_keeps_going_"
            "and_going_until_it_exceeds_the_limit",
            duration=0.5,
            outcome="failed",
        )
        filename1 = writer._make_filename(1, tc)
        filename2 = writer._make_filename(1, tc)
        assert filename1 == filename2

    def test_full_test_id_in_file_header(self, tmp_path: Path) -> None:
        """Full test_id in the failure file header matches index.json."""
        xml_path = _write_xml(tmp_path, "junit.xml", LONG_NAME_XML)
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        writer = StructuredLogWriter("test-project", run_dir)
        writer.write([xml_path], TIMESTAMP)
        index = _read_index(run_dir)

        # Check that every failure's log_file contains the full test_id
        for failure in index["failures"]:
            log_file = run_dir / failure["log_file"]
            content = log_file.read_text(encoding="utf-8")
            assert f"TEST: {failure['test_id']}" in content


# ===========================================================================
# 8. Edge cases
# ===========================================================================


class TestEdgeCases:
    """Edge cases: all pass, single failure, empty classname."""

    def test_zero_failures_all_pass(self, tmp_path: Path) -> None:
        """All tests pass — index.json with empty arrays, no failures/ dir."""
        xml_path = _write_xml(
            tmp_path, "junit.xml", SAMPLE_JUNIT_ALL_PASS
        )
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        writer = StructuredLogWriter("test-project", run_dir)
        writer.write([xml_path], TIMESTAMP)
        index = _read_index(run_dir)

        assert index["result"] == "PASSED"
        assert index["counts"]["passed"] == 3
        assert index["counts"]["failed"] == 0
        assert index["failures"] == []
        assert index["failure_clusters"] == []
        assert not (run_dir / "failures").exists()

    def test_single_failure(self, tmp_path: Path) -> None:
        """Single failure — one file, one cluster."""
        xml_path = _write_xml(
            tmp_path, "junit.xml", SOURCE_LOCATION_TEST_ONLY_XML
        )
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        writer = StructuredLogWriter("test-project", run_dir)
        writer.write([xml_path], TIMESTAMP)
        index = _read_index(run_dir)

        assert len(index["failures"]) == 1
        assert len(index["failure_clusters"]) == 1
        assert index["failure_clusters"][0]["count"] == 1

        failure_files = list((run_dir / "failures").glob("*.txt"))
        assert len(failure_files) == 1

    def test_empty_classname(self, tmp_path: Path) -> None:
        """Empty classname in XML is handled gracefully."""
        xml_path = _write_xml(
            tmp_path, "junit.xml", EMPTY_CLASSNAME_XML
        )
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        writer = StructuredLogWriter("test-project", run_dir)
        writer.write([xml_path], TIMESTAMP)
        index = _read_index(run_dir)

        assert len(index["failures"]) == 1
        assert index["failures"][0]["function"] == "test_no_class"

    def test_stdout_stderr_in_failure_file(
        self, tmp_path: Path
    ) -> None:
        """Failure file includes captured stdout and stderr."""
        xml_path = _write_xml(
            tmp_path, "junit.xml", STDOUT_STDERR_XML
        )
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        writer = StructuredLogWriter("test-project", run_dir)
        writer.write([xml_path], TIMESTAMP)

        failure_files = list((run_dir / "failures").glob("*.txt"))
        assert len(failure_files) == 1

        content = failure_files[0].read_text(encoding="utf-8")
        assert "--- Captured stdout ---" in content
        assert "this is stdout content" in content
        assert "--- Captured stderr ---" in content
        assert "this is stderr content" in content

    def test_index_json_forward_slashes(self, tmp_path: Path) -> None:
        """All paths in index.json use forward slashes."""
        xml_path = _write_xml(
            tmp_path, "junit.xml", SAMPLE_JUNIT_PARALLEL
        )
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        writer = StructuredLogWriter("test-project", run_dir)
        writer.write([xml_path], TIMESTAMP)
        index = _read_index(run_dir)

        for failure in index["failures"]:
            assert "\\" not in failure["log_file"]
            assert "/" in failure["log_file"]

    def test_phase_results_included_when_provided(
        self, tmp_path: Path
    ) -> None:
        """Phase results are included in index.json when provided."""
        xml_path = _write_xml(
            tmp_path, "junit.xml", SAMPLE_JUNIT_PARALLEL
        )
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        phase_results = {
            "parallel": {"result": "FAILED", "worker_count": 4, "items": 10},
            "serial": {"result": "PASSED", "items": 2},
        }

        writer = StructuredLogWriter("test-project", run_dir)
        writer.write([xml_path], TIMESTAMP, phase_results=phase_results)
        index = _read_index(run_dir)

        assert "phases" in index
        assert index["phases"]["parallel"]["result"] == "FAILED"
        assert index["phases"]["serial"]["result"] == "PASSED"
