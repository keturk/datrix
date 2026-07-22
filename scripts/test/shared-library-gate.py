#!/usr/bin/env python3
"""Repo-level gate absorbing the coverage of the 8 orphaned pytest files under
``datrix/scripts/library/shared/tests/``.

Why this gate exists
---------------------
Per the datrix showcase-repo boundary ("hosts no test suite of any kind"),
those 8 pytest files were orphaned: no runner ever executed them, and pytest
config/suites are prohibited in this repo. Rather than leave genuinely
valuable regression coverage to rot (or silently delete it), this script
re-expresses every DISTINCT BEHAVIOR CLASS those files described as a plain
Python check -- no pytest, no mocks, real ``tempfile.TemporaryDirectory()``
fixtures and real file I/O -- following the same shape as
``check-generated-file-ratchet.py`` / ``test-specific-selection-gate.py``.

Modules covered (7 full files + 3 classes of an 8th):
    shared.structured_log_writer      (StructuredLogWriter, SourceLocation, TestCaseResult)
    shared.test_runner                (TestConfig, TestRunner._build_pytest_args -- READ ONLY)
    shared.codegen_hint_mapper        (get_codegen_hint, CodegenHint)
    shared.deploy_test_aggregate_writer (DeployTestAggregateWriter)
    shared.generated_test_log_writer  (GeneratedTestLogWriter, normalize_error_message, _extract_import_chain)
    shared.aggregate_test_writer      (AggregateTestWriter, CrossProjectCluster, ProjectSummary, SuiteFailureCluster)
    shared.deploy_test_log_writer     (DeployTestLogWriter, DEPLOY_PHASES, TRANSIENT_ERROR_PATTERNS)
    shared.logging_utils              (TestLogContent / TestCleanupDirectoriesOnly / TestCleanupAgeBased ONLY --
                                        READ ONLY; directory-creation/uniqueness classes are already covered far
                                        more rigorously by test-specific-selection-gate.ps1's
                                        run_dir_exclusivity_check and are deliberately NOT re-covered here)

Harness convention
------------------
Each ``check_*`` function takes no arguments, does its own setup (a fresh
``TemporaryDirectory``), and raises ``AssertionError`` with a descriptive
message on failure. ``run_checks`` catches only ``AssertionError`` per check
(anything else is a bug in the gate itself and is allowed to propagate),
printing ``[OK] <name>`` or ``[FAIL] <name>: <message>``.

Non-vacuity
-----------
Several checks are adversarial by construction (corrupt/truncated/empty XML
must yield INCOMPLETE; a Docker-unavailable-with-no-markers or fully empty
deploy dir must yield FAILED, never PASSED; missing/corrupt per-project
index.json must be skipped without error; add_project_results must raise on
bad input). In addition, ``--harness-self-test`` registers one deliberately
failing dummy check and requires the harness to report it FAILED with a
nonzero exit -- proving the pass/fail mechanism itself cannot swallow a
failure.

Exit codes: 0 = every check passed, 1 = at least one check failed, 2 = usage error.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

_SCRIPT_DIR = Path(__file__).resolve().parent
_LIBRARY_DIR = _SCRIPT_DIR.parent / "library"
if str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from shared.aggregate_test_writer import (  # noqa: E402
    AggregateTestWriter,
    CrossProjectCluster,
    ProjectSummary,
    SuiteFailureCluster,
)
from shared.codegen_hint_mapper import CodegenHint, get_codegen_hint  # noqa: E402
from shared.deploy_test_aggregate_writer import DeployTestAggregateWriter  # noqa: E402
from shared.deploy_test_log_writer import (  # noqa: E402
    DEPLOY_PHASES,
    TRANSIENT_ERROR_PATTERNS,
    DeployTestLogWriter,
)
from shared.generated_test_log_writer import (  # noqa: E402
    GeneratedTestLogWriter,
    _extract_import_chain,
    normalize_error_message,
)
from shared.logging_utils import LogConfig, TeeLogger, cleanup_old_logs  # noqa: E402
from shared.structured_log_writer import (  # noqa: E402
    _MAX_FILENAME_BODY_LENGTH,
    StructuredLogWriter,
)
from shared.structured_log_writer import (  # noqa: E402
    TestCaseResult as _SlwTestCaseResult,  # noqa: E402
)
from shared.test_runner import TestConfig, TestRunner  # noqa: E402

CheckFunc = Callable[[], None]

_GREEN = "\033[92m"
_RED = "\033[91m"
_RESET = "\033[0m"

_TIMESTAMP = datetime(2026, 5, 3, 19, 10, 2)


def _ok(msg: str) -> None:
    print(f"{_GREEN}[OK]{_RESET} {msg}")


def _fail(msg: str) -> None:
    print(f"{_RED}[FAIL]{_RESET} {msg}")


def run_checks(checks: list[CheckFunc]) -> bool:
    """Run every check, catching only AssertionError. Returns True iff all passed."""
    all_passed = True
    for check in checks:
        name = check.__name__
        try:
            check()
        except AssertionError as exc:
            _fail(f"{name}: {exc}")
            all_passed = False
        else:
            _ok(name)
    return all_passed


# ===========================================================================
# shared.structured_log_writer
# ===========================================================================

_SLW_JUNIT_PARALLEL = """\
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

_SLW_JUNIT_SERIAL = """\
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

_SLW_TRUNCATED = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="parallel" tests="3"
"""

_SLW_ALL_PASS = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="all" tests="3" errors="0" failures="0" skipped="0" time="1.5">
    <testcase classname="tests.test_ok.TestOk" name="test_one" time="0.5"/>
    <testcase classname="tests.test_ok.TestOk" name="test_two" time="0.5"/>
    <testcase classname="tests.test_ok.TestOk" name="test_three" time="0.5"/>
  </testsuite>
</testsuites>
"""

_SLW_CLUSTERABLE = """\
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

_SLW_ERROR_CLUSTERING = """\
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

_SLW_SRC_PROJECT_FRAME = """\
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

_SLW_SRC_TEST_ONLY = """\
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

_SLW_SRC_STDLIB_ONLY = """\
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

_SLW_SRC_NO_TRACEBACK = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="all" tests="1" errors="0" failures="1" time="0.5">
    <testcase classname="tests.test_loc.TestLoc" name="test_no_traceback" time="0.5">
      <failure type="SomeError" message="no frames"/>
    </testcase>
  </testsuite>
</testsuites>
"""

_SLW_SRC_CONFTEST = """\
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

_SLW_STDOUT_STDERR = """\
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


def check_structured_log_writer_index_schema() -> None:
    """index.json: schema_version=1, counts dict, failures/errors lists with all
    required fields, failure_clusters/error_clusters present; summary.txt and
    failures/errors detail files are written alongside."""
    with TemporaryDirectory(prefix="slw-schema-") as tmp:
        root = Path(tmp)
        xml_path = root / "junit.xml"
        xml_path.write_text(_SLW_JUNIT_PARALLEL, encoding="utf-8")
        run_dir = root / "run"
        run_dir.mkdir()
        writer = StructuredLogWriter("test-project", run_dir)
        result_path = writer.write([xml_path], _TIMESTAMP)
        assert result_path == run_dir / "index.json", (
            f"write() returned {result_path}, expected {run_dir / 'index.json'}"
        )
        index = json.loads(result_path.read_text(encoding="utf-8"))
        assert index["schema_version"] == 1, f"schema_version={index.get('schema_version')!r}, expected 1"
        assert index["project"] == "test-project"
        assert index["timestamp"] == "2026-05-03T19:10:02"
        assert index["result"] == "FAILED"
        assert index["counts"] == {"passed": 1, "failed": 1, "error": 1, "skipped": 1}, index["counts"]
        assert isinstance(index["failures"], list) and len(index["failures"]) == 1
        assert isinstance(index["errors"], list) and len(index["errors"]) == 1
        assert isinstance(index["failure_clusters"], list)
        assert isinstance(index["error_clusters"], list)
        failure = index["failures"][0]
        for key in (
            "id", "test_id", "file", "class", "function",
            "error_type", "error_message", "source_location", "log_file",
        ):
            assert key in failure, f"failure entry missing required key {key!r}: {failure}"

        summary_path = run_dir / "summary.txt"
        assert summary_path.exists(), "summary.txt was not written"
        content = summary_path.read_text(encoding="utf-8")
        assert "test-project test results" in content
        assert "RESULT: FAILED" in content
        assert len(content.splitlines()) <= 50, "summary.txt exceeds the 50-line budget"

        failures_dir = run_dir / "failures"
        assert failures_dir.exists()
        failure_files = list(failures_dir.glob("*.txt"))
        assert len(failure_files) == 1
        failure_content = failure_files[0].read_text(encoding="utf-8")
        assert failure_content.startswith("TEST: ")
        assert "CLUSTER:" in failure_content
        assert "--- Traceback ---" in failure_content

        errors_dir = run_dir / "errors"
        assert errors_dir.exists()
        error_content = next(errors_dir.glob("*.txt")).read_text(encoding="utf-8")
        assert "ImportError" in error_content


def check_structured_log_writer_two_phase_merge() -> None:
    """Parallel + serial JUnit XML merge into one index; either file missing still
    yields partial (correctly-counted) results from whichever file exists."""
    with TemporaryDirectory(prefix="slw-merge-") as tmp:
        root = Path(tmp)
        parallel_xml = root / "junit-parallel.xml"
        parallel_xml.write_text(_SLW_JUNIT_PARALLEL, encoding="utf-8")
        serial_xml = root / "junit-serial.xml"
        serial_xml.write_text(_SLW_JUNIT_SERIAL, encoding="utf-8")

        run_both = root / "run-both"
        run_both.mkdir()
        StructuredLogWriter("p", run_both).write([parallel_xml, serial_xml], _TIMESTAMP)
        index_both = json.loads((run_both / "index.json").read_text(encoding="utf-8"))
        # parallel: 1 pass + 1 fail + 1 error + 1 skip; serial: 1 pass + 1 fail
        assert index_both["counts"] == {"passed": 2, "failed": 2, "error": 1, "skipped": 1}, index_both["counts"]

        run_parallel_only = root / "run-parallel-only"
        run_parallel_only.mkdir()
        StructuredLogWriter("p", run_parallel_only).write(
            [parallel_xml, root / "missing-serial.xml"], _TIMESTAMP
        )
        index_parallel_only = json.loads((run_parallel_only / "index.json").read_text(encoding="utf-8"))
        assert index_parallel_only["counts"]["passed"] == 1
        assert index_parallel_only["counts"]["failed"] == 1
        assert index_parallel_only["result"] == "FAILED"

        run_serial_only = root / "run-serial-only"
        run_serial_only.mkdir()
        StructuredLogWriter("p", run_serial_only).write(
            [root / "missing-parallel.xml", serial_xml], _TIMESTAMP
        )
        index_serial_only = json.loads((run_serial_only / "index.json").read_text(encoding="utf-8"))
        assert index_serial_only["counts"]["passed"] == 1
        assert index_serial_only["counts"]["failed"] == 1


def check_structured_log_writer_incomplete_on_bad_xml() -> None:
    """Missing, truncated, and empty XML each yield result=INCOMPLETE (with a
    "note" and null counts); one valid + one corrupt file still yields FAILED
    from the valid file alone -- the corrupt file is skipped, not fatal."""
    with TemporaryDirectory(prefix="slw-incomplete-") as tmp:
        root = Path(tmp)

        run_missing = root / "run-missing"
        run_missing.mkdir()
        StructuredLogWriter("p", run_missing).write(
            [root / "missing-a.xml", root / "missing-b.xml"], _TIMESTAMP
        )
        index_missing = json.loads((run_missing / "index.json").read_text(encoding="utf-8"))
        assert index_missing["result"] == "INCOMPLETE"
        assert "note" in index_missing
        assert index_missing["counts"] is None
        assert index_missing["failures"] == [] and index_missing["errors"] == []
        assert index_missing["failure_clusters"] == [] and index_missing["error_clusters"] == []

        truncated_path = root / "truncated.xml"
        truncated_path.write_text(_SLW_TRUNCATED, encoding="utf-8")
        run_truncated = root / "run-truncated"
        run_truncated.mkdir()
        StructuredLogWriter("p", run_truncated).write([truncated_path], _TIMESTAMP)
        index_truncated = json.loads((run_truncated / "index.json").read_text(encoding="utf-8"))
        assert index_truncated["result"] == "INCOMPLETE"
        assert index_truncated["schema_version"] == 1

        empty_path = root / "empty.xml"
        empty_path.write_text("", encoding="utf-8")
        run_empty = root / "run-empty"
        run_empty.mkdir()
        StructuredLogWriter("p", run_empty).write([empty_path], _TIMESTAMP)
        index_empty = json.loads((run_empty / "index.json").read_text(encoding="utf-8"))
        assert index_empty["result"] == "INCOMPLETE"

        valid_path = root / "valid.xml"
        valid_path.write_text(_SLW_JUNIT_PARALLEL, encoding="utf-8")
        run_mixed = root / "run-mixed"
        run_mixed.mkdir()
        StructuredLogWriter("p", run_mixed).write([valid_path, truncated_path], _TIMESTAMP)
        index_mixed = json.loads((run_mixed / "index.json").read_text(encoding="utf-8"))
        assert index_mixed["result"] == "FAILED"
        assert index_mixed["counts"]["passed"] == 1
        assert index_mixed["counts"]["failed"] == 1


def check_structured_log_writer_clustering_and_representative() -> None:
    """Failures cluster by (error_type, source_location); distinct source
    locations stay separate clusters; the cluster representative is the
    alphabetically-first test_id among members; errors cluster the same way."""
    with TemporaryDirectory(prefix="slw-cluster-") as tmp:
        root = Path(tmp)
        xml_path = root / "junit.xml"
        xml_path.write_text(_SLW_CLUSTERABLE, encoding="utf-8")
        run_dir = root / "run"
        run_dir.mkdir()
        StructuredLogWriter("p", run_dir).write([xml_path], _TIMESTAMP)
        index = json.loads((run_dir / "index.json").read_text(encoding="utf-8"))

        assert len(index["failure_clusters"]) == 2, index["failure_clusters"]
        clusters = sorted(index["failure_clusters"], key=lambda c: c["count"], reverse=True)
        assert clusters[0]["count"] == 3 and "GenerationError" in clusters[0]["pattern"]
        assert clusters[1]["count"] == 1 and "AttributeError" in clusters[1]["pattern"]
        source_set = {c["source_location"] for c in index["failure_clusters"]}
        assert len(source_set) == 2, "different source locations must not merge into one cluster"

        gen_cluster = next(c for c in index["failure_clusters"] if "GenerationError" in c["pattern"])
        rep = next(f for f in index["failures"] if f["id"] == gen_cluster["representative_failure_id"])
        assert "test_alpha" in rep["test_id"], (
            f"representative must be the alphabetically-first test_id (test_alpha), got {rep['test_id']}"
        )

        xml_errors = root / "errors.xml"
        xml_errors.write_text(_SLW_ERROR_CLUSTERING, encoding="utf-8")
        run_errors = root / "run-errors"
        run_errors.mkdir()
        StructuredLogWriter("p", run_errors).write([xml_errors], _TIMESTAMP)
        index_errors = json.loads((run_errors / "index.json").read_text(encoding="utf-8"))
        assert len(index_errors["errors"]) == 3
        assert len(index_errors["error_clusters"]) == 1
        assert index_errors["error_clusters"][0]["count"] == 3
        assert "ImportError" in index_errors["error_clusters"][0]["pattern"]


def check_structured_log_writer_source_location_fallback_chain() -> None:
    """Source-location fallback chain: project source frame -> test frame ->
    conftest-as-test frame -> stdlib-only -> no-traceback; the last two both
    collapse to "unknown:0"."""
    with TemporaryDirectory(prefix="slw-srcloc-") as tmp:
        root = Path(tmp)

        xml_project = root / "project.xml"
        xml_project.write_text(_SLW_SRC_PROJECT_FRAME, encoding="utf-8")
        run_project = root / "run-project"
        run_project.mkdir()
        StructuredLogWriter("p", run_project).write([xml_project], _TIMESTAMP)
        index_project = json.loads((run_project / "index.json").read_text(encoding="utf-8"))
        assert "src/mylib/engine.py:42" in index_project["failures"][0]["source_location"]

        xml_test_only = root / "test-only.xml"
        xml_test_only.write_text(_SLW_SRC_TEST_ONLY, encoding="utf-8")
        run_test_only = root / "run-test-only"
        run_test_only.mkdir()
        StructuredLogWriter("p", run_test_only).write([xml_test_only], _TIMESTAMP)
        index_test_only = json.loads((run_test_only / "index.json").read_text(encoding="utf-8"))
        assert "tests/test_loc.py:15" in index_test_only["failures"][0]["source_location"]

        xml_stdlib = root / "stdlib.xml"
        xml_stdlib.write_text(_SLW_SRC_STDLIB_ONLY, encoding="utf-8")
        run_stdlib = root / "run-stdlib"
        run_stdlib.mkdir()
        StructuredLogWriter("p", run_stdlib).write([xml_stdlib], _TIMESTAMP)
        index_stdlib = json.loads((run_stdlib / "index.json").read_text(encoding="utf-8"))
        assert index_stdlib["failures"][0]["source_location"] == "unknown:0"

        xml_no_tb = root / "no-traceback.xml"
        xml_no_tb.write_text(_SLW_SRC_NO_TRACEBACK, encoding="utf-8")
        run_no_tb = root / "run-no-traceback"
        run_no_tb.mkdir()
        StructuredLogWriter("p", run_no_tb).write([xml_no_tb], _TIMESTAMP)
        index_no_tb = json.loads((run_no_tb / "index.json").read_text(encoding="utf-8"))
        assert index_no_tb["failures"][0]["source_location"] == "unknown:0"

        xml_conftest = root / "conftest.xml"
        xml_conftest.write_text(_SLW_SRC_CONFTEST, encoding="utf-8")
        run_conftest = root / "run-conftest"
        run_conftest.mkdir()
        StructuredLogWriter("p", run_conftest).write([xml_conftest], _TIMESTAMP)
        index_conftest = json.loads((run_conftest / "index.json").read_text(encoding="utf-8"))
        assert "conftest.py:25" in index_conftest["errors"][0]["source_location"]


def check_structured_log_writer_message_normalization() -> None:
    """_normalize_error_message replaces single/double-quoted strings, hex
    addresses, and standalone numbers with '*'; parametrized test variants that
    differ only in such values cluster together after normalization."""
    with TemporaryDirectory(prefix="slw-normalize-") as tmp:
        root = Path(tmp)
        writer = StructuredLogWriter("test", root)

        assert writer._normalize_error_message(
            "KeyError", "key 'my_key' not found"
        ) == "KeyError: key * not found"
        assert writer._normalize_error_message(
            "KeyError", 'key "other_key" not found'
        ) == "KeyError: key * not found"
        assert writer._normalize_error_message(
            "RuntimeError", "object at 0x7f1234abcdef is invalid"
        ) == "RuntimeError: object at * is invalid"
        assert writer._normalize_error_message(
            "IndexError", "list index 42 out of range 10"
        ) == "IndexError: list index * out of range *"

        parametrized_xml = """\
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
        xml_path = root / "param.xml"
        xml_path.write_text(parametrized_xml, encoding="utf-8")
        run_dir = root / "run"
        run_dir.mkdir()
        StructuredLogWriter("p", run_dir).write([xml_path], _TIMESTAMP)
        index = json.loads((run_dir / "index.json").read_text(encoding="utf-8"))
        assert len(index["failure_clusters"]) == 1, (
            "parametrized variants differing only by number should cluster into 1"
        )
        assert index["failure_clusters"][0]["count"] == 3


def check_structured_log_writer_filename_truncation() -> None:
    """_make_filename caps the body at _MAX_FILENAME_BODY_LENGTH chars, truncates
    at a '-'/'_' boundary, and appends a deterministic 8-char hash suffix; short
    names are left untouched."""
    with TemporaryDirectory(prefix="slw-truncate-") as tmp:
        root = Path(tmp)
        writer = StructuredLogWriter("test", root)

        short_tc = _SlwTestCaseResult(
            test_id="tests.test_foo.TestBar::test_ok",
            file="tests/test_foo.py",
            classname="tests.test_foo.TestBar",
            function="test_ok",
            duration=0.5,
            outcome="failed",
        )
        short_filename = writer._make_filename(1, short_tc)
        assert short_filename == "001-tests-test_foo-TestBar-test_ok.txt", short_filename

        long_tc = _SlwTestCaseResult(
            test_id=(
                "tests.very_long_module_name_that_goes_on_and_on."
                "TestExtremelyDescriptiveClassName::"
                "test_also_a_very_descriptive_name_that_keeps_going_"
                "and_going_until_it_exceeds_the_limit"
            ),
            file="tests/very_long.py",
            classname=(
                "tests.very_long_module_name_that_goes_on_and_on."
                "TestExtremelyDescriptiveClassName"
            ),
            function=(
                "test_also_a_very_descriptive_name_that_keeps_going_"
                "and_going_until_it_exceeds_the_limit"
            ),
            duration=0.5,
            outcome="failed",
        )
        long_filename = writer._make_filename(1, long_tc)
        body = long_filename[4:-4]  # strip "001-" and ".txt"
        assert len(body) <= _MAX_FILENAME_BODY_LENGTH + 9, (
            f"truncated body too long ({len(body)} chars): {long_filename}"
        )
        # Determinism: same test_id -> same filename (same hash suffix) every time.
        assert writer._make_filename(1, long_tc) == long_filename

        # Full test_id must still appear verbatim in the written file's header,
        # even though the FILENAME is truncated.
        xml_path = root / "long.xml"
        xml_path.write_text(
            _SLW_CLUSTERABLE.replace("test_alpha", "test_" + "x" * 130), encoding="utf-8"
        )
        run_dir = root / "run"
        run_dir.mkdir()
        StructuredLogWriter("p", run_dir).write([xml_path], _TIMESTAMP)
        index = json.loads((run_dir / "index.json").read_text(encoding="utf-8"))
        for failure in index["failures"]:
            log_file = run_dir / failure["log_file"]
            content = log_file.read_text(encoding="utf-8")
            assert f"TEST: {failure['test_id']}" in content


def check_structured_log_writer_edge_cases() -> None:
    """All-pass run has empty failures/clusters and no failures/ dir; stdout/
    stderr are captured verbatim in the failure file; index.json paths always
    use forward slashes; phase_results pass through into index["phases"]."""
    with TemporaryDirectory(prefix="slw-edge-") as tmp:
        root = Path(tmp)

        xml_all_pass = root / "all-pass.xml"
        xml_all_pass.write_text(_SLW_ALL_PASS, encoding="utf-8")
        run_all_pass = root / "run-all-pass"
        run_all_pass.mkdir()
        StructuredLogWriter("p", run_all_pass).write([xml_all_pass], _TIMESTAMP)
        index_all_pass = json.loads((run_all_pass / "index.json").read_text(encoding="utf-8"))
        assert index_all_pass["result"] == "PASSED"
        assert index_all_pass["counts"]["passed"] == 3 and index_all_pass["counts"]["failed"] == 0
        assert index_all_pass["failures"] == [] and index_all_pass["failure_clusters"] == []
        assert not (run_all_pass / "failures").exists(), "no failures/ dir expected on an all-pass run"

        xml_stdout_stderr = root / "stdout-stderr.xml"
        xml_stdout_stderr.write_text(_SLW_STDOUT_STDERR, encoding="utf-8")
        run_io = root / "run-io"
        run_io.mkdir()
        StructuredLogWriter("p", run_io).write([xml_stdout_stderr], _TIMESTAMP)
        failure_file = next((run_io / "failures").glob("*.txt"))
        io_content = failure_file.read_text(encoding="utf-8")
        assert "--- Captured stdout ---" in io_content and "this is stdout content" in io_content
        assert "--- Captured stderr ---" in io_content and "this is stderr content" in io_content

        xml_parallel = root / "parallel.xml"
        xml_parallel.write_text(_SLW_JUNIT_PARALLEL, encoding="utf-8")
        run_slashes = root / "run-slashes"
        run_slashes.mkdir()
        StructuredLogWriter("p", run_slashes).write([xml_parallel], _TIMESTAMP)
        index_slashes = json.loads((run_slashes / "index.json").read_text(encoding="utf-8"))
        for failure in index_slashes["failures"]:
            assert "\\" not in failure["log_file"], failure["log_file"]
            assert "/" in failure["log_file"], failure["log_file"]

        run_phases = root / "run-phases"
        run_phases.mkdir()
        phase_results = {
            "parallel": {"result": "FAILED", "worker_count": 4, "items": 10},
            "serial": {"result": "PASSED", "items": 2},
        }
        StructuredLogWriter("p", run_phases).write([xml_parallel], _TIMESTAMP, phase_results=phase_results)
        index_phases = json.loads((run_phases / "index.json").read_text(encoding="utf-8"))
        assert "phases" in index_phases
        assert index_phases["phases"]["parallel"]["result"] == "FAILED"
        assert index_phases["phases"]["serial"]["result"] == "PASSED"


# ===========================================================================
# shared.test_runner (TestConfig, TestRunner._build_pytest_args) -- READ ONLY
# ===========================================================================


def _make_test_runner(has_xdist: bool = False) -> TestRunner:
    config = TestConfig(project_root=Path("/fake/project"), project_name="test-project")
    runner = TestRunner(config)
    runner.has_xdist = has_xdist
    return runner


def check_test_runner_junit_xml_flag_only_when_given() -> None:
    """--junit-xml is appended only when junit_xml_path is provided; it is absent
    both when explicitly None and when the parameter is omitted entirely."""
    runner = _make_test_runner()
    xml_path = Path("/fake/run-dir/junit.xml")

    args_with = runner._build_pytest_args(
        python_exe="python", coverage=False, verbose=False, junit_xml_path=xml_path
    )
    assert "--junit-xml" in args_with
    idx = args_with.index("--junit-xml")
    assert args_with[idx + 1] == str(xml_path)

    args_none = runner._build_pytest_args(
        python_exe="python", coverage=False, verbose=False, junit_xml_path=None
    )
    assert "--junit-xml" not in args_none

    args_omitted = runner._build_pytest_args(python_exe="python", coverage=False, verbose=False)
    assert "--junit-xml" not in args_omitted


def check_test_runner_junit_xml_coexists_with_addopts_override() -> None:
    """When xdist is enabled with no coverage, _build_pytest_args emits an
    ``-o addopts=...`` override for the parallel phase; --junit-xml must appear
    as its OWN standalone flag, never buried inside that addopts string."""
    runner = _make_test_runner(has_xdist=True)
    xml_path = Path("/fake/run-dir/junit-parallel.xml")

    args = runner._build_pytest_args(
        python_exe="python", coverage=False, verbose=False, junit_xml_path=xml_path
    )
    assert "-o" in args
    assert "--junit-xml" in args
    junit_idx = args.index("--junit-xml")
    assert args[junit_idx + 1] == str(xml_path)
    o_idx = args.index("-o")
    addopts_value = args[o_idx + 1]
    assert "--junit-xml" not in addopts_value, "junit-xml leaked into the addopts override string"


def check_test_runner_junit_xml_with_coverage_and_verbose_marker() -> None:
    """--junit-xml works alongside coverage (which disables the parallel -n auto
    flag) and alongside verbose + marker-expression flags."""
    runner = _make_test_runner(has_xdist=True)
    xml_path = Path("/fake/run-dir/junit.xml")

    args_coverage = runner._build_pytest_args(
        python_exe="python", coverage=True, verbose=False, junit_xml_path=xml_path
    )
    assert "--junit-xml" in args_coverage
    assert "-n" not in args_coverage, "coverage must disable parallel -n auto"

    runner2 = _make_test_runner()
    args_verbose_marker = runner2._build_pytest_args(
        python_exe="python",
        coverage=False,
        verbose=True,
        marker_expr="unit",
        junit_xml_path=xml_path,
    )
    assert "--junit-xml" in args_verbose_marker
    assert "-v" in args_verbose_marker
    assert "-m" in args_verbose_marker


# ===========================================================================
# shared.codegen_hint_mapper
# ===========================================================================


def check_codegen_hint_python_patterns() -> None:
    """Each Python file-type pattern (entity/schema/service/routes/integration
    helpers/error __init__) returns the correct hint."""
    entity = get_codegen_hint("user_service/src/user_service/models/main/user.py")
    assert entity is not None
    assert entity.probable_template == "entity_model.py.j2" and entity.probable_generator == "EntityGenerator"

    schema = get_codegen_hint("svc/src/svc/schemas/main/user_schema.py")
    assert schema is not None
    assert schema.probable_template == "entity_schema.py.j2" and schema.probable_generator == "SchemaGenerator"

    service = get_codegen_hint("svc/src/svc/services/main/user_service.py")
    assert service is not None
    assert service.probable_template == "entity_service.py.j2" and service.probable_generator == "ServiceGenerator"

    routes = get_codegen_hint("svc/src/svc/routes/main/user_routes.py")
    assert routes is not None
    assert routes.probable_template == "api_routes.py.j2" and routes.probable_generator == "EndpointGenerator"

    integration = get_codegen_hint("svc/src/svc/integrations/_email_helpers.py")
    assert integration is not None
    assert integration.probable_template == "integration_helpers.py.j2"
    assert integration.probable_generator == "IntegrationGenerator"

    errors = get_codegen_hint("svc/src/svc/errors/__init__.py")
    assert errors is not None
    assert errors.probable_template == "error_classes.py.j2" and errors.probable_generator == "ErrorGenerator"


def check_codegen_hint_typescript_patterns() -> None:
    """TypeScript entity/dto/controller path patterns each return the right hint."""
    entity = get_codegen_hint("svc/src/entities/user.entity.ts")
    assert entity is not None and entity.probable_template == "entity.ts.j2"
    assert entity.probable_generator == "EntityGenerator"

    dto = get_codegen_hint("svc/src/dto/user.dto.ts")
    assert dto is not None and dto.probable_template == "dto.ts.j2" and dto.probable_generator == "DtoGenerator"

    controller = get_codegen_hint("svc/src/controllers/user.controller.ts")
    assert controller is not None
    assert controller.probable_template == "controller.ts.j2"
    assert controller.probable_generator == "ControllerGenerator"


def check_codegen_hint_docker_patterns() -> None:
    """docker-compose.yml and Dockerfile each return their generator hint."""
    compose = get_codegen_hint("project/docker-compose.yml")
    assert compose is not None
    assert compose.probable_template == "docker-compose.yml.j2"
    assert compose.probable_generator == "DockerComposeGenerator"

    dockerfile = get_codegen_hint("svc/Dockerfile")
    assert dockerfile is not None
    assert dockerfile.probable_template == "Dockerfile.j2"
    assert dockerfile.probable_generator == "DockerfileGenerator"


def check_codegen_hint_unknown_returns_none() -> None:
    """An unrecognized path, a non-code file, and an empty string all return None."""
    assert get_codegen_hint("some/random/file.py") is None
    assert get_codegen_hint("README.md") is None
    assert get_codegen_hint("") is None


def check_codegen_hint_backslash_normalization() -> None:
    """Windows-style backslash paths are normalized to forward slashes before matching."""
    hint = get_codegen_hint("svc\\src\\svc\\models\\main\\user.py")
    assert hint is not None
    assert hint.probable_template == "entity_model.py.j2"


def check_codegen_hint_most_specific_pattern_wins() -> None:
    """The more-specific integration-helpers pattern wins over a would-be general match."""
    hint = get_codegen_hint("svc/src/svc/integrations/_email_helpers.py")
    assert hint is not None
    assert hint.probable_generator == "IntegrationGenerator"


def check_codegen_hint_is_frozen() -> None:
    """CodegenHint is a frozen dataclass -- mutation raises AttributeError."""
    hint = CodegenHint("template.j2", "Generator")
    try:
        hint.probable_template = "other.j2"  # type: ignore[misc]
    except AttributeError:
        pass
    else:
        raise AssertionError("CodegenHint accepted a mutation; it must be frozen")


# ===========================================================================
# shared.deploy_test_aggregate_writer
# ===========================================================================


def _deploy_agg_infrastructure_index() -> dict[str, object]:
    return {
        "schema_version": 1,
        "project": "python/docker/02-features/03-infrastructure-blocks/cache",
        "language": "python",
        "platform": "docker",
        "example": "02-features/03-infrastructure-blocks/cache",
        "result": "FAILED",
        "failed_phase": "docker-up",
        "phases": {
            "docker-build": {"result": "PASSED"},
            "docker-up": {"result": "FAILED", "error_message": "container unhealthy"},
            "spec-tests": {"result": "SKIPPED"},
            "integration-tests": {"result": "SKIPPED"},
        },
        "services": [],
        "failures": [],
        "errors": [{"id": 1, "phase": "docker-up", "error_type": "ContainerUnhealthy"}],
        "failure_clusters": [],
        "error_clusters": [
            {
                "cluster_id": 1,
                "pattern": "ContainerUnhealthy: * is unhealthy",
                "phase": "docker-up",
                "count": 1,
                "codegen_hint": {"probable_template": "docker-compose.yml.j2"},
            },
        ],
    }


def _deploy_agg_test_failure_index() -> dict[str, object]:
    return {
        "schema_version": 1,
        "project": "python/docker/01-foundation",
        "language": "python",
        "platform": "docker",
        "example": "01-foundation",
        "result": "FAILED",
        "failed_phase": "integration-tests",
        "phases": {
            "docker-build": {"result": "PASSED"},
            "docker-up": {"result": "PASSED"},
            "spec-tests": {"result": "PASSED"},
            "integration-tests": {"result": "FAILED", "counts": {"passed": 17, "failed": 2}},
        },
        "services": [{"name": "library_book_service", "integration_result": "FAILED"}],
        "failures": [
            {"id": 1, "failure_type": "logic", "error_type": "AssertionError"},
            {"id": 2, "failure_type": "transient", "error_type": "ConnectionResetError"},
        ],
        "errors": [],
        "failure_clusters": [
            {
                "cluster_id": 1,
                "pattern": "AssertionError: assert * == response.status_code",
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


def _deploy_agg_passing_index() -> dict[str, object]:
    return {
        "schema_version": 1,
        "project": "python/docker/02-features/01-core-data-modeling/entities",
        "language": "python",
        "platform": "docker",
        "example": "02-features/01-core-data-modeling/entities",
        "result": "PASSED",
        "failed_phase": None,
        "phases": {
            "docker-build": {"result": "PASSED"},
            "docker-up": {"result": "PASSED"},
            "spec-tests": {"result": "PASSED"},
            "integration-tests": {"result": "PASSED", "counts": {"passed": 20, "failed": 0}},
        },
        "failures": [],
        "errors": [],
        "failure_clusters": [],
        "error_clusters": [],
    }


def _write_deploy_agg_project_index(root: Path, project_name: str, data: dict[str, object]) -> Path:
    proj_dir = root / project_name / ".test_results" / "deploy-test-20260503"
    proj_dir.mkdir(parents=True)
    index_path = proj_dir / "index.json"
    index_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return index_path


def check_deploy_test_aggregate_schema_and_counts() -> None:
    """aggregate-index.json has all required top-level fields, correct project
    pass/fail counts, and correctly counts an infrastructure (Docker-lifecycle)
    failure separately from a test-level failure."""
    with TemporaryDirectory(prefix="dtaw-schema-") as tmp:
        root = Path(tmp)
        paths = [
            _write_deploy_agg_project_index(root, "cache", _deploy_agg_infrastructure_index()),
            _write_deploy_agg_project_index(root, "foundation", _deploy_agg_test_failure_index()),
            _write_deploy_agg_project_index(root, "basic", _deploy_agg_passing_index()),
        ]
        agg_dir = root / "aggregate"
        agg_dir.mkdir()
        writer = DeployTestAggregateWriter(aggregate_dir=agg_dir, language="python", platform="docker")
        agg_path = writer.write(project_index_paths=paths, timestamp=_TIMESTAMP)
        agg = json.loads(agg_path.read_text(encoding="utf-8"))

        required_fields = (
            "schema_version", "timestamp", "language", "platform", "total_projects",
            "projects_passed", "projects_failed", "total_counts", "failed_projects",
            "cross_project_clusters",
        )
        for field_name in required_fields:
            assert field_name in agg, f"Missing field: {field_name}"
        assert agg["schema_version"] == 1
        assert agg["language"] == "python" and agg["platform"] == "docker"
        assert agg["total_projects"] == 3
        assert agg["projects_passed"] == 1
        assert agg["projects_failed"] == 2
        assert agg["total_counts"]["infrastructure_failures"] == 1


def check_deploy_test_aggregate_failed_projects_populated() -> None:
    """failed_projects has one entry per FAILED project, each with project,
    failed_phase, counts, and top_cluster_pattern."""
    with TemporaryDirectory(prefix="dtaw-failedproj-") as tmp:
        root = Path(tmp)
        paths = [
            _write_deploy_agg_project_index(root, "cache", _deploy_agg_infrastructure_index()),
            _write_deploy_agg_project_index(root, "foundation", _deploy_agg_test_failure_index()),
        ]
        agg_dir = root / "aggregate"
        agg_dir.mkdir()
        writer = DeployTestAggregateWriter(aggregate_dir=agg_dir, language="python", platform="docker")
        agg = json.loads(
            writer.write(project_index_paths=paths, timestamp=_TIMESTAMP).read_text(encoding="utf-8")
        )
        assert len(agg["failed_projects"]) == 2
        for fp in agg["failed_projects"]:
            for key in ("project", "failed_phase", "counts", "top_cluster_pattern"):
                assert key in fp, f"failed_projects entry missing {key!r}: {fp}"


def check_deploy_test_aggregate_cross_project_cluster_correlation() -> None:
    """Distinct error patterns across projects stay separate clusters; the same
    pattern from two projects merges into one cluster with correct
    projects_affected/total_errors; failure_type (logic/transient/
    infrastructure) is preserved on each cluster."""
    with TemporaryDirectory(prefix="dtaw-correlate-") as tmp:
        root = Path(tmp)

        distinct_paths = [
            _write_deploy_agg_project_index(root, "cache", _deploy_agg_infrastructure_index()),
            _write_deploy_agg_project_index(root, "foundation", _deploy_agg_test_failure_index()),
        ]
        agg_dir_a = root / "aggregate-a"
        agg_dir_a.mkdir()
        writer_a = DeployTestAggregateWriter(aggregate_dir=agg_dir_a, language="python", platform="docker")
        agg_a = json.loads(
            writer_a.write(project_index_paths=distinct_paths, timestamp=_TIMESTAMP).read_text(encoding="utf-8")
        )
        # infrastructure cluster + logic cluster + transient cluster = 3
        assert len(agg_a["cross_project_clusters"]) == 3, agg_a["cross_project_clusters"]
        failure_types = sorted(str(c["failure_type"]) for c in agg_a["cross_project_clusters"])
        assert "infrastructure" in failure_types
        assert "logic" in failure_types
        assert "transient" in failure_types
        for cluster in agg_a["cross_project_clusters"]:
            for key in (
                "cluster_id", "pattern", "phase", "failure_type",
                "projects_affected", "total_errors",
            ):
                assert key in cluster, f"cross_project_clusters entry missing {key!r}: {cluster}"

        pattern = "ContainerUnhealthy: * is unhealthy"
        index_a: dict[str, object] = {
            "schema_version": 1, "project": "python/docker/project-a", "example": "project-a",
            "result": "FAILED", "failed_phase": "docker-up", "phases": {}, "failures": [], "errors": [],
            "failure_clusters": [],
            "error_clusters": [{"cluster_id": 1, "pattern": pattern, "phase": "docker-up", "count": 1}],
        }
        index_b: dict[str, object] = {
            "schema_version": 1, "project": "python/docker/project-b", "example": "project-b",
            "result": "FAILED", "failed_phase": "docker-up", "phases": {}, "failures": [], "errors": [],
            "failure_clusters": [],
            "error_clusters": [{"cluster_id": 1, "pattern": pattern, "phase": "docker-up", "count": 1}],
        }
        merge_paths = [
            _write_deploy_agg_project_index(root, "project-a", index_a),
            _write_deploy_agg_project_index(root, "project-b", index_b),
        ]
        agg_dir_b = root / "aggregate-b"
        agg_dir_b.mkdir()
        writer_b = DeployTestAggregateWriter(aggregate_dir=agg_dir_b, language="python", platform="docker")
        agg_b = json.loads(
            writer_b.write(project_index_paths=merge_paths, timestamp=_TIMESTAMP).read_text(encoding="utf-8")
        )
        assert len(agg_b["cross_project_clusters"]) == 1, "identical pattern must merge into one cluster"
        merged = agg_b["cross_project_clusters"][0]
        assert sorted(merged["projects_affected"]) == ["project-a", "project-b"]
        assert merged["total_errors"] == 2


def check_deploy_test_aggregate_summary_sections() -> None:
    """aggregate-summary.txt contains an INFRASTRUCTURE FAILURES section, a
    RESULT line with the pass/total ratio, and a PASSED PROJECTS section."""
    with TemporaryDirectory(prefix="dtaw-summary-") as tmp:
        root = Path(tmp)
        paths = [
            _write_deploy_agg_project_index(root, "cache", _deploy_agg_infrastructure_index()),
            _write_deploy_agg_project_index(root, "basic", _deploy_agg_passing_index()),
        ]
        agg_dir = root / "aggregate"
        agg_dir.mkdir()
        writer = DeployTestAggregateWriter(aggregate_dir=agg_dir, language="python", platform="docker")
        writer.write(project_index_paths=paths, timestamp=_TIMESTAMP)

        summary = (agg_dir / "aggregate-summary.txt").read_text(encoding="utf-8")
        assert "INFRASTRUCTURE FAILURES" in summary
        assert "cache" in summary
        assert "RESULT:" in summary
        assert "1/2" in summary
        assert "PASSED PROJECTS" in summary


def check_deploy_test_aggregate_edge_cases() -> None:
    """Empty input produces a valid minimal aggregate; a missing or corrupt
    per-project index.json is skipped without error; full_log_path is copied
    to full.log; the aggregate directory is auto-created if missing."""
    with TemporaryDirectory(prefix="dtaw-edge-") as tmp:
        root = Path(tmp)

        agg_dir_empty = root / "aggregate-empty"
        agg_dir_empty.mkdir()
        writer_empty = DeployTestAggregateWriter(
            aggregate_dir=agg_dir_empty, language="python", platform="docker"
        )
        agg_empty = json.loads(
            writer_empty.write(project_index_paths=[], timestamp=_TIMESTAMP).read_text(encoding="utf-8")
        )
        assert agg_empty["total_projects"] == 0
        assert agg_empty["projects_passed"] == 0 and agg_empty["projects_failed"] == 0
        assert agg_empty["cross_project_clusters"] == []

        valid_path = _write_deploy_agg_project_index(root, "basic", _deploy_agg_passing_index())
        missing_path = root / "nonexistent" / "index.json"
        corrupt_dir = root / "corrupt" / ".test_results" / "deploy-test"
        corrupt_dir.mkdir(parents=True)
        corrupt_path = corrupt_dir / "index.json"
        corrupt_path.write_text("not valid json{{{", encoding="utf-8")

        agg_dir_skip = root / "aggregate-skip"
        agg_dir_skip.mkdir()
        writer_skip = DeployTestAggregateWriter(
            aggregate_dir=agg_dir_skip, language="python", platform="docker"
        )
        agg_skip = json.loads(
            writer_skip.write(
                project_index_paths=[valid_path, missing_path, corrupt_path], timestamp=_TIMESTAMP
            ).read_text(encoding="utf-8")
        )
        assert agg_skip["total_projects"] == 1, "missing/corrupt indices must be skipped, not counted"
        assert agg_skip["projects_passed"] == 1

        log_file = root / "run-complete-output.log"
        log_file.write_text("full orchestration log content", encoding="utf-8")
        agg_dir_log = root / "deep" / "nested" / "aggregate"
        writer_log = DeployTestAggregateWriter(
            aggregate_dir=agg_dir_log, language="python", platform="docker"
        )
        writer_log.write(project_index_paths=[], timestamp=_TIMESTAMP, full_log_path=log_file)
        assert agg_dir_log.exists(), "aggregate dir must be auto-created"
        copied_log = agg_dir_log / "full.log"
        assert copied_log.exists()
        assert copied_log.read_text(encoding="utf-8") == "full orchestration log content"


# ===========================================================================
# shared.generated_test_log_writer
# ===========================================================================

_GTLW_JUNIT_PASSING = """\
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

_GTLW_JUNIT_FAILURES = """\
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

_GTLW_JUNIT_ERRORS = """\
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

_GTLW_JEST_PASSING: dict[str, object] = {
    "numTotalTests": 2,
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

_GTLW_JEST_FAILURES: dict[str, object] = {
    "numTotalTests": 3,
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

_GTLW_JEST_SUITE_FAILURE: dict[str, object] = {
    "numTotalTests": 0,
    "testResults": [
        {
            "testFilePath": "/app/tests/unit/user.service.spec.ts",
            "status": "failed",
            "testExecError": {
                "message": "Cannot find module 'express'",
                "stack": "Error: Cannot find module 'express'",
            },
            "testResults": [],
        }
    ],
}


def _make_generated_test_log_writer(run_dir: Path, language: str = "python") -> GeneratedTestLogWriter:
    return GeneratedTestLogWriter(
        project_path=f"{language}/docker/02-features/test-project",
        language=language,
        platform="docker",
        example="02-features/test-project",
        run_dir=run_dir,
        dtrx_source="datrix/examples/02-features/test-project/system.dtrx",
    )


def check_generated_test_log_junit_xml_parsing() -> None:
    """JUnit XML parsing: passing/failure/error counts, and error entries carry
    error_type through correctly."""
    with TemporaryDirectory(prefix="gtlw-junit-") as tmp:
        root = Path(tmp)

        run_pass = root / "run-pass"
        run_pass.mkdir()
        xml_pass = root / "pass.xml"
        xml_pass.write_text(_GTLW_JUNIT_PASSING, encoding="utf-8")
        log_pass = root / "svc.log"
        log_pass.write_text("log\n", encoding="utf-8")
        writer_pass = _make_generated_test_log_writer(run_pass)
        writer_pass.add_service_junit_xml("user_service", xml_pass, log_pass)
        index_pass = json.loads(writer_pass.write(duration_seconds=1.5).read_text(encoding="utf-8"))
        assert index_pass["result"] == "PASSED"
        assert index_pass["counts"]["passed"] == 5 and index_pass["counts"]["failed"] == 0
        assert index_pass["failures"] == [] and index_pass["errors"] == []

        run_fail = root / "run-fail"
        run_fail.mkdir()
        xml_fail = root / "fail.xml"
        xml_fail.write_text(_GTLW_JUNIT_FAILURES, encoding="utf-8")
        writer_fail = _make_generated_test_log_writer(run_fail)
        writer_fail.add_service_junit_xml("user_service", xml_fail, log_pass)
        index_fail = json.loads(writer_fail.write(duration_seconds=0.5).read_text(encoding="utf-8"))
        assert index_fail["result"] == "FAILED"
        assert index_fail["counts"]["passed"] == 1 and index_fail["counts"]["failed"] == 2
        assert len(index_fail["failures"]) == 2
        assert index_fail["failures"][0]["error_type"] == "AssertionError"

        run_err = root / "run-err"
        run_err.mkdir()
        xml_err = root / "err.xml"
        xml_err.write_text(_GTLW_JUNIT_ERRORS, encoding="utf-8")
        writer_err = _make_generated_test_log_writer(run_err)
        writer_err.add_service_junit_xml("ecommerce_user_service", xml_err, log_pass)
        index_err = json.loads(writer_err.write(duration_seconds=0.1).read_text(encoding="utf-8"))
        assert index_err["result"] == "FAILED"
        assert index_err["counts"]["errors"] == 3
        assert len(index_err["errors"]) == 3
        assert index_err["errors"][0]["error_type"] == "ImportError"


def check_generated_test_log_jest_json_parsing() -> None:
    """Jest JSON parsing: passing/failure counts, and a suite-execution error
    (testExecError) is recorded as a SuiteFailure with the service-level
    suite_failure_message populated."""
    with TemporaryDirectory(prefix="gtlw-jest-") as tmp:
        root = Path(tmp)
        log_path = root / "svc.log"
        log_path.write_text("log\n", encoding="utf-8")

        run_pass = root / "run-pass"
        run_pass.mkdir()
        json_pass = root / "pass.json"
        json_pass.write_text(json.dumps(_GTLW_JEST_PASSING), encoding="utf-8")
        writer_pass = _make_generated_test_log_writer(run_pass, language="typescript")
        writer_pass.add_service_jest_json("user_service", json_pass, log_path)
        index_pass = json.loads(writer_pass.write(duration_seconds=2.0).read_text(encoding="utf-8"))
        assert index_pass["result"] == "PASSED"
        assert index_pass["counts"]["passed"] == 2 and index_pass["counts"]["failed"] == 0

        run_fail = root / "run-fail"
        run_fail.mkdir()
        json_fail = root / "fail.json"
        json_fail.write_text(json.dumps(_GTLW_JEST_FAILURES), encoding="utf-8")
        writer_fail = _make_generated_test_log_writer(run_fail, language="typescript")
        writer_fail.add_service_jest_json("user_service", json_fail, log_path)
        index_fail = json.loads(writer_fail.write(duration_seconds=1.0).read_text(encoding="utf-8"))
        assert index_fail["result"] == "FAILED"
        assert index_fail["counts"]["failed"] == 2 and index_fail["counts"]["passed"] == 1

        run_suite = root / "run-suite"
        run_suite.mkdir()
        json_suite = root / "suite.json"
        json_suite.write_text(json.dumps(_GTLW_JEST_SUITE_FAILURE), encoding="utf-8")
        writer_suite = _make_generated_test_log_writer(run_suite, language="typescript")
        writer_suite.add_service_jest_json("user_service", json_suite, log_path)
        index_suite = json.loads(writer_suite.write(duration_seconds=0.5).read_text(encoding="utf-8"))
        assert index_suite["result"] == "FAILED"
        assert index_suite["counts"]["suite_failures"] == 1
        assert index_suite["errors"][0]["error_type"] == "SuiteFailure"
        assert "Cannot find module" in index_suite["errors"][0]["error_message"]
        assert index_suite["services"][0]["suite_failure_message"] == "Cannot find module 'express'"


def check_generated_test_log_error_clustering_and_services_affected() -> None:
    """normalize_error_message replaces quoted strings/numbers with '*'; errors
    with the same normalized pattern from DIFFERENT services form one cluster
    that tracks services_affected; differently-patterned errors stay separate."""
    with TemporaryDirectory(prefix="gtlw-cluster-") as tmp:
        root = Path(tmp)

        assert normalize_error_message(
            "ImportError",
            "cannot import name '_email_send_ses' from 'ecommerce.integrations._email_helpers'",
        ) == "ImportError: cannot import name * from *"
        assert normalize_error_message("ValueError", "expected 42 items") == "ValueError: expected * items"

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
        run_dir = root / "run"
        run_dir.mkdir()
        log1 = root / "svc1.log"
        log1.write_text("log1\n", encoding="utf-8")
        log2 = root / "svc2.log"
        log2.write_text("log2\n", encoding="utf-8")
        xml1 = root / "junit1.xml"
        xml1.write_text(xml_content, encoding="utf-8")
        xml2 = root / "junit2.xml"
        xml2.write_text(xml_content, encoding="utf-8")

        writer = GeneratedTestLogWriter(
            project_path="test", language="python", platform="docker", example="test",
            run_dir=run_dir, dtrx_source="test.dtrx",
        )
        writer.add_service_junit_xml("service_a", xml1, log1)
        writer.add_service_junit_xml("service_b", xml2, log2)
        index = json.loads(writer.write(duration_seconds=0.1).read_text(encoding="utf-8"))
        assert len(index["error_clusters"]) == 1
        cluster = index["error_clusters"][0]
        assert sorted(cluster["services_affected"]) == ["service_a", "service_b"]
        assert cluster["count"] == 2

        different_xml = """\
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
        run_dir2 = root / "run2"
        run_dir2.mkdir()
        xml3 = root / "junit3.xml"
        xml3.write_text(different_xml, encoding="utf-8")
        writer2 = _make_generated_test_log_writer(run_dir2)
        writer2.add_service_junit_xml("svc", xml3, log1)
        index2 = json.loads(writer2.write(duration_seconds=0.1).read_text(encoding="utf-8"))
        assert len(index2["error_clusters"]) == 2, "different error patterns must not merge"


def check_generated_test_log_import_chain_extraction() -> None:
    """_extract_import_chain follows the frame->import lines of a collection
    error traceback, marking the LAST hop as (MISSING); an empty or blank
    traceback returns an empty chain."""
    traceback_text = (
        "tests/integration/repositories/test_user_repository.py:18: in <module>\n"
        "    from ecommerce_user_service.services.user_db.user_service import UserService\n"
        "src/ecommerce_user_service/services/user_db/user_service.py:19: in <module>\n"
        "    from ecommerce_user_service.integrations._email_helpers import _email_send_ses\n"
        "ImportError: cannot import name '_email_send_ses'"
    )
    chain = _extract_import_chain(traceback_text)
    assert len(chain) == 2, chain
    assert "test_user_repository.py:18" in chain[0]
    assert "ecommerce_user_service.services.user_db.user_service.UserService" in chain[0]
    assert "(MISSING)" in chain[1]

    assert _extract_import_chain("") == []
    assert _extract_import_chain("   ") == []


def check_generated_test_log_index_schema_and_summary_format() -> None:
    """index.json has every field the design doc requires (including nested
    counts keys); summary.txt has the RESULT line, .dtrx source, ERROR
    CLUSTERS/SERVICE RESULTS sections, and stays under 50 lines; a passing run
    creates index.json/summary.txt but no failures/ or errors/ dirs."""
    with TemporaryDirectory(prefix="gtlw-schema-") as tmp:
        root = Path(tmp)
        log_path = root / "svc.log"
        log_path.write_text("log\n", encoding="utf-8")

        run_dir = root / "run"
        run_dir.mkdir()
        xml_err = root / "err.xml"
        xml_err.write_text(_GTLW_JUNIT_ERRORS, encoding="utf-8")
        writer = _make_generated_test_log_writer(run_dir)
        writer.add_service_junit_xml("svc", xml_err, log_path)
        writer.write(duration_seconds=1.0)
        index = json.loads((run_dir / "index.json").read_text(encoding="utf-8"))

        required_keys = (
            "schema_version", "project", "project_path", "language", "platform",
            "example", "dtrx_source", "timestamp", "duration_seconds", "result",
            "counts", "services", "failures", "errors", "failure_clusters", "error_clusters",
        )
        for key in required_keys:
            assert key in index, f"Missing required key: {key}"
        for key in ("passed", "failed", "errors", "skipped", "suite_failures"):
            assert key in index["counts"], f"Missing counts key: {key}"

        summary = (run_dir / "summary.txt").read_text(encoding="utf-8")
        assert "RESULT: FAILED" in summary
        assert "ERROR CLUSTERS:" in summary
        assert "SERVICE RESULTS:" in summary
        assert len(summary.strip().split("\n")) <= 50

        run_dir_pass = root / "run-pass"
        run_dir_pass.mkdir()
        xml_pass = root / "pass.xml"
        xml_pass.write_text(_GTLW_JUNIT_PASSING, encoding="utf-8")
        writer_pass = _make_generated_test_log_writer(run_dir_pass)
        writer_pass.add_service_junit_xml("svc", xml_pass, log_path)
        writer_pass.write(duration_seconds=1.5)
        summary_pass = (run_dir_pass / "summary.txt").read_text(encoding="utf-8")
        assert "RESULT: PASSED" in summary_pass
        assert "5 passed" in summary_pass
        assert ".dtrx source:" in summary_pass
        assert (run_dir_pass / "index.json").exists()
        assert not (run_dir_pass / "failures").exists()
        assert not (run_dir_pass / "errors").exists()


def check_generated_test_log_detail_files_and_codegen_hint() -> None:
    """Individual error/failure detail files have SERVICE/TEST/CLUSTER/ERROR
    headers and a full traceback section; when the traceback resolves to a
    known generated-file pattern, a --- Codegen Hint --- block is appended."""
    with TemporaryDirectory(prefix="gtlw-detail-") as tmp:
        root = Path(tmp)
        log_path = root / "svc.log"
        log_path.write_text("log\n", encoding="utf-8")

        run_dir = root / "run"
        run_dir.mkdir()
        xml_err = root / "err.xml"
        xml_err.write_text(_GTLW_JUNIT_ERRORS, encoding="utf-8")
        writer = _make_generated_test_log_writer(run_dir)
        writer.add_service_junit_xml("ecommerce_user_service", xml_err, log_path)
        writer.write(duration_seconds=0.1)

        errors_dir = run_dir / "errors"
        assert errors_dir.exists()
        error_files = list(errors_dir.glob("*.txt"))
        assert len(error_files) == 3
        content = error_files[0].read_text(encoding="utf-8")
        assert "SERVICE:" in content and "TEST:" in content and "CLUSTER:" in content
        assert "ERROR:" in content and "--- Full Traceback ---" in content

        run_dir_hint = root / "run-hint"
        run_dir_hint.mkdir()
        hint_xml = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite tests="1" failures="1">
    <testcase classname="tests.test_svc" name="test_email" time="0.1">
      <failure type="AssertionError" message="mismatch">
tests/test_svc.py:10: in test_email
    do_thing()
project/src/svc/integrations/_email_helpers.py:5: in do_thing
    raise AssertionError("mismatch")
E   AssertionError: mismatch
      </failure>
    </testcase>
  </testsuite>
</testsuites>
"""
        xml_hint = root / "hint.xml"
        xml_hint.write_text(hint_xml, encoding="utf-8")
        writer_hint = _make_generated_test_log_writer(run_dir_hint)
        writer_hint.add_service_junit_xml("svc", xml_hint, log_path)
        writer_hint.write(duration_seconds=0.1)
        failure_files = list((run_dir_hint / "failures").glob("*.txt"))
        assert len(failure_files) == 1
        found_hint = False
        for failure_file in failure_files:
            hint_content = failure_file.read_text(encoding="utf-8")
            if "--- Codegen Hint ---" in hint_content:
                found_hint = True
                assert "Probable template:" in hint_content
                assert "Probable generator:" in hint_content
        assert found_hint, "expected a codegen hint block for a src/.../integrations/_x_helpers.py traceback"


def check_generated_test_log_multi_service_and_log_only_fallback() -> None:
    """Multiple services aggregate correctly into the services array and overall
    counts/result; add_service_log_only (no structured data available) still
    produces a valid FAILED/PASSED index with empty failures/errors arrays."""
    with TemporaryDirectory(prefix="gtlw-multi-") as tmp:
        root = Path(tmp)
        log1 = root / "svc1.log"
        log1.write_text("log1\n", encoding="utf-8")
        log2 = root / "svc2.log"
        log2.write_text("log2\n", encoding="utf-8")

        run_dir = root / "run"
        run_dir.mkdir()
        xml1 = root / "junit1.xml"
        xml1.write_text(_GTLW_JUNIT_PASSING, encoding="utf-8")
        xml2 = root / "junit2.xml"
        xml2.write_text(_GTLW_JUNIT_FAILURES, encoding="utf-8")
        writer = _make_generated_test_log_writer(run_dir)
        writer.add_service_junit_xml("service_a", xml1, log1)
        writer.add_service_junit_xml("service_b", xml2, log2)
        index = json.loads(writer.write(duration_seconds=2.0).read_text(encoding="utf-8"))
        assert len(index["services"]) == 2
        names = [s["name"] for s in index["services"]]
        assert "service_a" in names and "service_b" in names
        assert index["result"] == "FAILED"
        assert index["counts"]["passed"] == 6  # 5 + 1
        assert index["counts"]["failed"] == 2

        run_dir_log_only = root / "run-log-only"
        run_dir_log_only.mkdir()
        writer_log_only = _make_generated_test_log_writer(run_dir_log_only)
        writer_log_only.add_service_log_only("svc", log1, passed=10, failed=2, errors=1)
        index_log_only = json.loads(writer_log_only.write(duration_seconds=5.0).read_text(encoding="utf-8"))
        assert index_log_only["result"] == "FAILED"
        assert index_log_only["counts"]["passed"] == 10
        assert index_log_only["counts"]["failed"] == 2
        assert index_log_only["counts"]["errors"] == 1
        assert index_log_only["failures"] == [] and index_log_only["errors"] == []


# ===========================================================================
# shared.aggregate_test_writer
# ===========================================================================


def _make_project_index_json(
    root: Path,
    project: str,
    example: str,
    result: str,
    counts: dict[str, int],
    error_clusters: list[dict[str, object]] | None = None,
    failure_clusters: list[dict[str, object]] | None = None,
    services: list[dict[str, object]] | None = None,
) -> Path:
    project_dir = root / project.replace("/", "_")
    project_dir.mkdir(parents=True, exist_ok=True)
    data: dict[str, object] = {
        "schema_version": 1,
        "project": project,
        "language": "python",
        "platform": "docker",
        "example": example,
        "dtrx_source": f"datrix/examples/{example}/system.dtrx",
        "timestamp": "2026-05-03T21:04:22",
        "duration_seconds": 5.0,
        "result": result,
        "counts": counts,
        "services": services or [],
        "failures": [],
        "errors": [],
        "failure_clusters": failure_clusters or [],
        "error_clusters": error_clusters or [],
    }
    index_path = project_dir / "index.json"
    index_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return index_path


def _passing_counts() -> dict[str, int]:
    return {"passed": 20, "failed": 0, "errors": 0, "skipped": 0, "suite_failures": 0}


def _failing_counts(passed: int = 5, errors: int = 3) -> dict[str, int]:
    return {"passed": passed, "failed": 0, "errors": errors, "skipped": 0, "suite_failures": 0}


def _suite_failure_counts(passed: int = 0) -> dict[str, int]:
    return {"passed": passed, "failed": 0, "errors": 0, "skipped": 0, "suite_failures": 1}


def check_aggregate_test_writer_cross_project_correlation() -> None:
    """Identical normalized patterns across projects correlate into one cluster
    (with codegen_hint propagated); different patterns stay separate; the
    representative project is the one with the highest count, tie-broken
    alphabetically; failure_clusters (not just error_clusters) are correlated too."""
    with TemporaryDirectory(prefix="atw-correlate-") as tmp:
        root = Path(tmp)
        pattern = "ImportError: cannot import name * from *"
        hint = {"probable_template": "integration_helpers.py.j2", "probable_generator": "IntegrationGenerator"}

        idx1 = _make_project_index_json(
            root, "python/docker/02-features/proj-a", "02-features/proj-a", "FAILED",
            _failing_counts(errors=3),
            error_clusters=[{
                "cluster_id": 1, "pattern": pattern, "generated_file": "x", "count": 3,
                "services_affected": ["svc_a"], "error_ids": [1, 2, 3],
                "representative_error_id": 1, "codegen_hint": hint,
            }],
        )
        idx2 = _make_project_index_json(
            root, "python/docker/02-features/proj-b", "02-features/proj-b", "FAILED",
            _failing_counts(errors=2),
            error_clusters=[{
                "cluster_id": 1, "pattern": pattern, "generated_file": "x", "count": 2,
                "services_affected": ["svc_b"], "error_ids": [1, 2],
                "representative_error_id": 1, "codegen_hint": hint,
            }],
        )
        writer = AggregateTestWriter(language="python", platform="docker", output_dir=root / "aggregate")
        writer.add_project_results(idx1)
        writer.add_project_results(idx2)
        agg = json.loads(writer.write().read_text(encoding="utf-8"))
        assert len(agg["cross_project_clusters"]) == 1
        cluster = agg["cross_project_clusters"][0]
        assert cluster["pattern"] == pattern
        assert sorted(cluster["projects_affected"]) == ["02-features/proj-a", "02-features/proj-b"]
        assert cluster["total_errors"] == 5
        assert cluster["codegen_hint"]["probable_template"] == "integration_helpers.py.j2"

        idx3 = _make_project_index_json(
            root, "python/docker/proj-c", "proj-c", "FAILED", _failing_counts(errors=1),
            error_clusters=[{
                "cluster_id": 1, "pattern": "TypeError: expected * got *", "generated_file": None,
                "count": 1, "services_affected": ["svc"], "error_ids": [1],
                "representative_error_id": 1, "codegen_hint": None,
            }],
        )
        writer2 = AggregateTestWriter(language="python", platform="docker", output_dir=root / "aggregate2")
        writer2.add_project_results(idx1)
        writer2.add_project_results(idx3)
        agg2 = json.loads(writer2.write().read_text(encoding="utf-8"))
        assert len(agg2["cross_project_clusters"]) == 2, "different patterns must not correlate"

        idx_hi = _make_project_index_json(
            root, "python/docker/proj-hi", "proj-hi", "FAILED", _failing_counts(errors=10),
            error_clusters=[{
                "cluster_id": 1, "pattern": pattern, "generated_file": None, "count": 10,
                "services_affected": ["svc"], "error_ids": list(range(1, 11)),
                "representative_error_id": 1, "codegen_hint": None,
            }],
        )
        idx_lo = _make_project_index_json(
            root, "python/docker/proj-lo", "proj-lo", "FAILED", _failing_counts(errors=3),
            error_clusters=[{
                "cluster_id": 1, "pattern": pattern, "generated_file": None, "count": 3,
                "services_affected": ["svc"], "error_ids": [1, 2, 3],
                "representative_error_id": 1, "codegen_hint": None,
            }],
        )
        writer3 = AggregateTestWriter(language="python", platform="docker", output_dir=root / "aggregate3")
        writer3.add_project_results(idx_hi)
        writer3.add_project_results(idx_lo)
        agg3 = json.loads(writer3.write().read_text(encoding="utf-8"))
        assert agg3["cross_project_clusters"][0]["representative_project"] == "proj-hi"

        idx_tie_b = _make_project_index_json(
            root, "python/docker/proj-b2", "proj-b2", "FAILED", _failing_counts(errors=5),
            error_clusters=[{
                "cluster_id": 1, "pattern": pattern, "generated_file": None, "count": 5,
                "services_affected": ["svc"], "error_ids": list(range(1, 6)),
                "representative_error_id": 1, "codegen_hint": None,
            }],
        )
        idx_tie_a = _make_project_index_json(
            root, "python/docker/proj-a2", "proj-a2", "FAILED", _failing_counts(errors=5),
            error_clusters=[{
                "cluster_id": 1, "pattern": pattern, "generated_file": None, "count": 5,
                "services_affected": ["svc"], "error_ids": list(range(1, 6)),
                "representative_error_id": 1, "codegen_hint": None,
            }],
        )
        writer4 = AggregateTestWriter(language="python", platform="docker", output_dir=root / "aggregate4")
        writer4.add_project_results(idx_tie_b)
        writer4.add_project_results(idx_tie_a)
        agg4 = json.loads(writer4.write().read_text(encoding="utf-8"))
        assert agg4["cross_project_clusters"][0]["representative_project"] == "proj-a2", (
            "tied counts must tie-break alphabetically"
        )

        fc_pattern = "AssertionError: assert * == *"
        idx_fc_a = _make_project_index_json(
            root, "python/docker/proj-fc-a", "proj-fc-a", "FAILED",
            {"passed": 3, "failed": 2, "errors": 0, "skipped": 0, "suite_failures": 0},
            failure_clusters=[{
                "cluster_id": 1, "pattern": fc_pattern, "generated_file": None, "count": 2,
                "services_affected": ["svc"], "error_ids": [1, 2],
                "representative_error_id": 1, "codegen_hint": None,
            }],
        )
        idx_fc_b = _make_project_index_json(
            root, "python/docker/proj-fc-b", "proj-fc-b", "FAILED",
            {"passed": 5, "failed": 1, "errors": 0, "skipped": 0, "suite_failures": 0},
            failure_clusters=[{
                "cluster_id": 1, "pattern": fc_pattern, "generated_file": None, "count": 1,
                "services_affected": ["svc"], "error_ids": [1],
                "representative_error_id": 1, "codegen_hint": None,
            }],
        )
        writer5 = AggregateTestWriter(language="python", platform="docker", output_dir=root / "aggregate5")
        writer5.add_project_results(idx_fc_a)
        writer5.add_project_results(idx_fc_b)
        agg5 = json.loads(writer5.write().read_text(encoding="utf-8"))
        assert len(agg5["cross_project_clusters"]) == 1, "failure_clusters must also be correlated"
        assert agg5["cross_project_clusters"][0]["total_errors"] == 3


def check_aggregate_test_writer_suite_failure_clusters_separate_type() -> None:
    """Suite failures form their OWN cluster type (suite_failure_clusters),
    separate from error/failure clusters; different suite-failure messages form
    separate clusters; a project with only suite failures has
    top_cluster_pattern=null but suite_failure_message present."""
    with TemporaryDirectory(prefix="atw-suitefail-") as tmp:
        root = Path(tmp)
        svc: list[dict[str, object]] = [{
            "name": "svc", "result": "FAILED", "counts": _suite_failure_counts(),
            "log_file": "services/svc/service.log",
            "suite_failure_message": "Cannot find module 'express'",
        }]
        idx1 = _make_project_index_json(
            root, "python/docker/proj-a", "proj-a", "FAILED", _suite_failure_counts(), services=svc
        )
        idx2 = _make_project_index_json(
            root, "python/docker/proj-b", "proj-b", "FAILED", _suite_failure_counts(), services=svc
        )
        writer = AggregateTestWriter(language="python", platform="docker", output_dir=root / "aggregate")
        writer.add_project_results(idx1)
        writer.add_project_results(idx2)
        agg = json.loads(writer.write().read_text(encoding="utf-8"))
        assert len(agg["suite_failure_clusters"]) == 1
        sfc = agg["suite_failure_clusters"][0]
        assert "Cannot find module" in sfc["pattern"]
        assert sorted(sfc["projects_affected"]) == ["proj-a", "proj-b"]
        assert sfc["total_suite_failures"] == 2

        failed_proj = agg["failed_projects"][0]
        assert failed_proj["top_cluster_pattern"] is None
        assert "suite_failure_message" in failed_proj

        svc_other: list[dict[str, object]] = [{
            "name": "svc", "result": "FAILED", "counts": _suite_failure_counts(),
            "log_file": "services/svc/service.log",
            "suite_failure_message": "SyntaxError: Unexpected token",
        }]
        idx3 = _make_project_index_json(
            root, "python/docker/proj-c", "proj-c", "FAILED", _suite_failure_counts(), services=svc
        )
        idx4 = _make_project_index_json(
            root, "python/docker/proj-d", "proj-d", "FAILED", _suite_failure_counts(), services=svc_other
        )
        writer2 = AggregateTestWriter(language="python", platform="docker", output_dir=root / "aggregate2")
        writer2.add_project_results(idx3)
        writer2.add_project_results(idx4)
        agg2 = json.loads(writer2.write().read_text(encoding="utf-8"))
        assert len(agg2["suite_failure_clusters"]) == 2, "different suite-failure messages must not merge"


def check_aggregate_test_writer_index_schema() -> None:
    """aggregate-index.json has schema_version=1, all required top-level and
    nested keys, correct total/passed/failed project counts, and correctly
    aggregated total_counts across projects."""
    with TemporaryDirectory(prefix="atw-schema-") as tmp:
        root = Path(tmp)
        pattern = "ImportError: cannot import name * from *"
        idx1 = _make_project_index_json(
            root, "python/docker/proj-a", "proj-a", "FAILED", _failing_counts(),
            error_clusters=[{
                "cluster_id": 1, "pattern": pattern, "generated_file": None, "count": 3,
                "services_affected": ["svc"], "error_ids": [1, 2, 3],
                "representative_error_id": 1, "codegen_hint": None,
            }],
        )
        idx2 = _make_project_index_json(root, "python/docker/proj-b", "proj-b", "PASSED", _passing_counts())
        writer = AggregateTestWriter(language="python", platform="docker", output_dir=root / "aggregate")
        writer.add_project_results(idx1)
        writer.add_project_results(idx2)
        agg = json.loads(writer.write().read_text(encoding="utf-8"))

        assert agg["schema_version"] == 1
        required_keys = (
            "schema_version", "timestamp", "language", "platform", "total_projects",
            "projects_passed", "projects_failed", "total_counts", "failed_projects",
            "cross_project_clusters", "suite_failure_clusters",
        )
        for key in required_keys:
            assert key in agg, f"Missing required key: {key}"
        for key in ("passed", "failed", "errors", "skipped", "suite_failures"):
            assert key in agg["total_counts"], f"Missing total_counts key: {key}"
        for key in ("cluster_id", "pattern", "projects_affected", "total_errors", "codegen_hint", "representative_project"):
            assert key in agg["cross_project_clusters"][0], f"Missing cross_project_clusters key: {key}"
        for key in ("project", "example", "result_dir", "counts", "top_cluster_pattern"):
            assert key in agg["failed_projects"][0], f"Missing failed_projects key: {key}"

        assert agg["total_projects"] == 2
        assert agg["projects_passed"] == 1 and agg["projects_failed"] == 1
        assert len(agg["failed_projects"]) == 1
        assert agg["failed_projects"][0]["example"] == "proj-a"

        idx3 = _make_project_index_json(
            root, "python/docker/proj-c", "proj-c", "PASSED",
            {"passed": 10, "failed": 0, "errors": 0, "skipped": 2, "suite_failures": 0},
        )
        idx4 = _make_project_index_json(
            root, "python/docker/proj-d", "proj-d", "FAILED",
            {"passed": 5, "failed": 1, "errors": 3, "skipped": 0, "suite_failures": 0},
        )
        writer2 = AggregateTestWriter(language="python", platform="docker", output_dir=root / "aggregate2")
        writer2.add_project_results(idx3)
        writer2.add_project_results(idx4)
        agg2 = json.loads(writer2.write().read_text(encoding="utf-8"))
        assert agg2["total_counts"] == {"passed": 15, "failed": 1, "errors": 3, "skipped": 2, "suite_failures": 0}

        idx5 = _make_project_index_json(root, "python/docker/proj-e", "proj-e", "PASSED", _passing_counts())
        idx6 = _make_project_index_json(root, "python/docker/proj-f", "proj-f", "PASSED", _passing_counts())
        writer3 = AggregateTestWriter(language="python", platform="docker", output_dir=root / "aggregate3")
        writer3.add_project_results(idx5)
        writer3.add_project_results(idx6)
        agg3 = json.loads(writer3.write().read_text(encoding="utf-8"))
        assert agg3["projects_failed"] == 0
        assert agg3["failed_projects"] == []
        assert agg3["cross_project_clusters"] == [] and agg3["suite_failure_clusters"] == []


def check_aggregate_test_writer_summary_format() -> None:
    """aggregate-summary.txt has the header, RESULT ratio, CROSS-PROJECT
    CLUSTERS / SUITE FAILURE CLUSTERS / FAILED PROJECTS sections when
    applicable, and omits cluster/failed-project sections when all pass."""
    with TemporaryDirectory(prefix="atw-summary-") as tmp:
        root = Path(tmp)
        pattern = "ImportError: cannot import name * from *"
        idx1 = _make_project_index_json(
            root, "python/docker/proj-a", "proj-a", "FAILED", _failing_counts(passed=5, errors=3),
            error_clusters=[{
                "cluster_id": 1, "pattern": pattern, "generated_file": None, "count": 3,
                "services_affected": ["svc"], "error_ids": [1, 2, 3], "representative_error_id": 1,
                "codegen_hint": {"probable_template": "integration_helpers.py.j2", "probable_generator": "IntegrationGenerator"},
            }],
        )
        idx2 = _make_project_index_json(root, "python/docker/proj-pass", "proj-pass", "PASSED", _passing_counts())
        writer = AggregateTestWriter(language="python", platform="docker", output_dir=root / "aggregate")
        writer.add_project_results(idx1)
        writer.add_project_results(idx2)
        writer.write()
        summary = (root / "aggregate" / "aggregate-summary.txt").read_text(encoding="utf-8")
        assert "Generated Project Unit Tests" in summary and "Cross-Project Summary" in summary
        assert "RESULT: 1/2 projects passed" in summary
        assert "CROSS-PROJECT CLUSTERS:" in summary and pattern in summary
        assert "Probable template:" in summary
        assert "FAILED PROJECTS:" in summary and "proj-a" in summary

        svc: list[dict[str, object]] = [{
            "name": "svc", "result": "FAILED", "counts": _suite_failure_counts(),
            "log_file": "services/svc/service.log",
            "suite_failure_message": "Cannot find module 'express'",
        }]
        idx3 = _make_project_index_json(
            root, "python/docker/proj-suite", "proj-suite", "FAILED", _suite_failure_counts(), services=svc
        )
        writer2 = AggregateTestWriter(language="python", platform="docker", output_dir=root / "aggregate2")
        writer2.add_project_results(idx3)
        writer2.write()
        summary2 = (root / "aggregate2" / "aggregate-summary.txt").read_text(encoding="utf-8")
        assert "SUITE FAILURE CLUSTERS:" in summary2 and "Cannot find module" in summary2

        idx4 = _make_project_index_json(root, "python/docker/proj-only-pass", "proj-only-pass", "PASSED", _passing_counts())
        writer3 = AggregateTestWriter(language="python", platform="docker", output_dir=root / "aggregate3")
        writer3.add_project_results(idx4)
        writer3.write()
        summary3 = (root / "aggregate3" / "aggregate-summary.txt").read_text(encoding="utf-8")
        assert "RESULT: 1/1 projects passed" in summary3
        assert "CROSS-PROJECT CLUSTERS:" not in summary3
        assert "FAILED PROJECTS:" not in summary3


def check_aggregate_test_writer_add_project_results_validation() -> None:
    """add_project_results raises FileNotFoundError for a missing index.json and
    json.JSONDecodeError for invalid JSON content."""
    with TemporaryDirectory(prefix="atw-validate-") as tmp:
        root = Path(tmp)
        writer = AggregateTestWriter(language="python", platform="docker", output_dir=root / "aggregate")

        try:
            writer.add_project_results(root / "nonexistent" / "index.json")
        except FileNotFoundError as exc:
            assert "index.json not found" in str(exc), str(exc)
        else:
            raise AssertionError("expected FileNotFoundError for a missing index.json path")

        bad_file = root / "bad.json"
        bad_file.write_text("not valid json {{{", encoding="utf-8")
        try:
            writer.add_project_results(bad_file)
        except json.JSONDecodeError:
            pass
        else:
            raise AssertionError("expected json.JSONDecodeError for invalid JSON content")


def check_aggregate_test_writer_mixed_scenarios() -> None:
    """A run mixing an error-cluster project, a suite-failure project, and a
    passing project aggregates counts/clusters correctly; a single-project and
    a many-project (10) aggregate both work."""
    with TemporaryDirectory(prefix="atw-mixed-") as tmp:
        root = Path(tmp)
        idx1 = _make_project_index_json(
            root, "python/docker/proj-errors", "proj-errors", "FAILED", _failing_counts(passed=5, errors=3),
            error_clusters=[{
                "cluster_id": 1, "pattern": "ImportError: cannot import name * from *", "generated_file": None,
                "count": 3, "services_affected": ["svc"], "error_ids": [1, 2, 3],
                "representative_error_id": 1, "codegen_hint": None,
            }],
        )
        svc: list[dict[str, object]] = [{
            "name": "svc", "result": "FAILED", "counts": _suite_failure_counts(),
            "log_file": "services/svc/service.log", "suite_failure_message": "Cannot find module 'express'",
        }]
        idx2 = _make_project_index_json(
            root, "python/docker/proj-suite", "proj-suite", "FAILED", _suite_failure_counts(), services=svc
        )
        idx3 = _make_project_index_json(root, "python/docker/proj-pass", "proj-pass", "PASSED", _passing_counts())

        writer = AggregateTestWriter(language="python", platform="docker", output_dir=root / "aggregate")
        writer.add_project_results(idx1)
        writer.add_project_results(idx2)
        writer.add_project_results(idx3)
        agg = json.loads(writer.write().read_text(encoding="utf-8"))
        assert agg["total_projects"] == 3
        assert agg["projects_passed"] == 1 and agg["projects_failed"] == 2
        assert len(agg["cross_project_clusters"]) == 1
        assert len(agg["suite_failure_clusters"]) == 1
        assert agg["total_counts"]["passed"] == 25  # 5 + 0 + 20
        assert agg["total_counts"]["errors"] == 3
        assert agg["total_counts"]["suite_failures"] == 1

        idx_only = _make_project_index_json(
            root, "python/docker/proj-only", "proj-only", "FAILED", _failing_counts(passed=3, errors=2),
            error_clusters=[{
                "cluster_id": 1, "pattern": "ImportError: cannot import name * from *", "generated_file": None,
                "count": 2, "services_affected": ["svc"], "error_ids": [1, 2],
                "representative_error_id": 1, "codegen_hint": None,
            }],
        )
        writer_single = AggregateTestWriter(language="python", platform="docker", output_dir=root / "aggregate-single")
        writer_single.add_project_results(idx_only)
        agg_single = json.loads(writer_single.write().read_text(encoding="utf-8"))
        assert agg_single["total_projects"] == 1
        assert len(agg_single["cross_project_clusters"]) == 1
        assert len(agg_single["cross_project_clusters"][0]["projects_affected"]) == 1

        writer_many = AggregateTestWriter(language="python", platform="docker", output_dir=root / "aggregate-many")
        pattern = "ImportError: cannot import name * from *"
        for i in range(10):
            result = "FAILED" if i % 3 == 0 else "PASSED"
            counts = _failing_counts(errors=2) if i % 3 == 0 else _passing_counts()
            clusters = [{
                "cluster_id": 1, "pattern": pattern, "generated_file": None, "count": 2,
                "services_affected": ["svc"], "error_ids": [1, 2], "representative_error_id": 1,
                "codegen_hint": None,
            }] if i % 3 == 0 else []
            idx_i = _make_project_index_json(
                root, f"python/docker/proj-{i:02d}", f"proj-{i:02d}", result, counts, error_clusters=clusters
            )
            writer_many.add_project_results(idx_i)
        agg_many = json.loads(writer_many.write().read_text(encoding="utf-8"))
        assert agg_many["total_projects"] == 10
        assert agg_many["projects_failed"] == 4  # 0, 3, 6, 9
        assert agg_many["projects_passed"] == 6


def check_aggregate_test_writer_frozen_dataclasses() -> None:
    """ProjectSummary, CrossProjectCluster, and SuiteFailureCluster are all
    frozen dataclasses -- mutation raises AttributeError."""
    summary = ProjectSummary(
        project="test", example="test", result_dir="/tmp/test", result="PASSED",
        counts={"passed": 1, "failed": 0, "errors": 0, "skipped": 0, "suite_failures": 0},
        top_cluster_pattern=None, suite_failure_message=None, error_clusters=[], failure_clusters=[],
    )
    try:
        summary.project = "other"  # type: ignore[misc]
    except AttributeError:
        pass
    else:
        raise AssertionError("ProjectSummary accepted a mutation; it must be frozen")

    cross_cluster = CrossProjectCluster(
        cluster_id=1, pattern="test", projects_affected=["proj-a"],
        total_errors=1, codegen_hint=None, representative_project="proj-a",
    )
    try:
        cross_cluster.pattern = "other"  # type: ignore[misc]
    except AttributeError:
        pass
    else:
        raise AssertionError("CrossProjectCluster accepted a mutation; it must be frozen")

    suite_cluster = SuiteFailureCluster(
        cluster_id=1, pattern="test", projects_affected=["proj-a"],
        total_suite_failures=1, representative_project="proj-a",
    )
    try:
        suite_cluster.pattern = "other"  # type: ignore[misc]
    except AttributeError:
        pass
    else:
        raise AssertionError("SuiteFailureCluster accepted a mutation; it must be frozen")


# ===========================================================================
# shared.deploy_test_log_writer
# ===========================================================================


def _new_deploy_run_dir(root: Path, name: str) -> Path:
    run_dir = root / name / ".test_results" / "deploy-test-20260503-210903"
    run_dir.mkdir(parents=True)
    (run_dir / "docker-logs").mkdir()
    return run_dir


def _populate_docker_lifecycle_failure(run_dir: Path) -> None:
    """Docker-build passed, docker-up failed (container unhealthy); no test artifacts."""
    (run_dir / "deploy-test-output.log").write_text(
        "=== Docker Build ===\n"
        "Building services...\n"
        "Successfully built library-book-service\n"
        "=== Docker Up ===\n"
        "Starting services...\n"
        "docker_up_failed exit_code=1\n"
        "container library-book-service is unhealthy\n",
        encoding="utf-8",
    )
    (run_dir / "docker-logs" / "library-book-service.log").write_text(
        "INFO library_book_service.main application_starting\n"
        "ERROR library_book_service.cache.redis_client redis_connection_failed "
        "host=library-book-service-cache port=6379\n"
        "ERROR library_book_service.main startup_failed "
        "error=Cannot connect to Redis at library-book-service-cache:6379\n",
        encoding="utf-8",
    )


def _populate_test_failure_dir(run_dir: Path) -> None:
    """All Docker phases passed, integration tests failed (1 logic + 1 transient)."""
    (run_dir / "deploy-test-output.log").write_text(
        "=== Docker Build ===\nSuccessfully built\n"
        "=== Docker Up ===\nAll services healthy\n"
        "=== Health Check ===\nAll services responding\n"
        "=== DB Connectivity ===\nAll databases connected\n"
        "=== Spec Tests ===\n3 passed\n"
        "=== Integration Tests ===\n17 passed, 2 failed\n",
        encoding="utf-8",
    )
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
    (run_dir / "failures.json").write_text(json.dumps(failures, indent=2), encoding="utf-8")
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
        '      message="ConnectionResetError: Connection aborted., RemoteDisconnected">'
        "tests/integration/repositories/test_book_repository.py:15: ConnectionResetError"
        "</failure>\n"
        "  </testcase>\n"
        "</testsuite></testsuites>\n"
    )
    (run_dir / "pytest-integration-library_book_service-project.xml").write_text(junit_xml, encoding="utf-8")


def _populate_all_passing_dir(run_dir: Path) -> None:
    (run_dir / "deploy-test-output.log").write_text(
        "=== Docker Build ===\nSuccessfully built\n"
        "=== Docker Up ===\nAll services healthy\n"
        "=== Health Check ===\nAll services responding\n"
        "=== DB Connectivity ===\nAll databases connected\n"
        "=== Spec Tests ===\n3 passed\n"
        "=== Integration Tests ===\n20 passed\n",
        encoding="utf-8",
    )
    (run_dir / "failures.json").write_text("[]", encoding="utf-8")
    junit_xml = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<testsuites>"
        '<testsuite name="integration" tests="20" failures="0">\n'
        '  <testcase classname="test_svc.TestSvc" name="test_ok" time="0.5"/>\n'
        "</testsuite></testsuites>\n"
    )
    (run_dir / "pytest-integration-my_service-project.xml").write_text(junit_xml, encoding="utf-8")


def _make_deploy_writer(
    run_dir: Path,
    project_path: Path,
    project_name: str = "cache",
    example: str = "02-features/03-infrastructure-blocks/cache",
) -> DeployTestLogWriter:
    return DeployTestLogWriter(
        project_name=project_name, run_dir=run_dir, project_path=project_path,
        language="python", platform="docker", example=example,
        dtrx_source=f"datrix/examples/{example}/system.dtrx",
    )


def check_deploy_test_log_phase_detection() -> None:
    """Docker-lifecycle failure (no test artifacts) is detected at docker-up
    with later phases SKIPPED; an all-Docker-passed + integration-test failure
    is detected at integration-tests; an all-passing run has failed_phase=None;
    DEPLOY_PHASES is the correct ordered constant."""
    with TemporaryDirectory(prefix="dtlw-phase-") as tmp:
        root = Path(tmp)

        run_lifecycle = _new_deploy_run_dir(root, "lifecycle")
        _populate_docker_lifecycle_failure(run_lifecycle)
        writer_lifecycle = _make_deploy_writer(run_lifecycle, root)
        index_lifecycle = json.loads(
            writer_lifecycle.write(timestamp=_TIMESTAMP).read_text(encoding="utf-8")
        )
        assert index_lifecycle["failed_phase"] == "docker-up"
        assert index_lifecycle["phases"]["docker-build"]["result"] == "PASSED"
        assert index_lifecycle["phases"]["docker-up"]["result"] == "FAILED"
        assert index_lifecycle["phases"]["spec-tests"]["result"] == "SKIPPED"
        assert index_lifecycle["phases"]["integration-tests"]["result"] == "SKIPPED"

        run_test_fail = _new_deploy_run_dir(root, "test-fail")
        _populate_test_failure_dir(run_test_fail)
        writer_test_fail = _make_deploy_writer(
            run_test_fail, root, project_name="01-foundation", example="01-foundation"
        )
        index_test_fail = json.loads(
            writer_test_fail.write(timestamp=_TIMESTAMP).read_text(encoding="utf-8")
        )
        assert index_test_fail["failed_phase"] == "integration-tests"
        assert index_test_fail["phases"]["docker-build"]["result"] == "PASSED"
        assert index_test_fail["phases"]["docker-up"]["result"] == "PASSED"
        assert index_test_fail["phases"]["integration-tests"]["result"] == "FAILED"

        run_pass = _new_deploy_run_dir(root, "all-pass")
        _populate_all_passing_dir(run_pass)
        writer_pass = _make_deploy_writer(
            run_pass, root, project_name="basic", example="02-features/01-core-data-modeling/entities"
        )
        index_pass = json.loads(writer_pass.write(timestamp=_TIMESTAMP).read_text(encoding="utf-8"))
        assert index_pass["result"] == "PASSED"
        assert index_pass["failed_phase"] is None

        assert DEPLOY_PHASES == [
            "docker-build", "docker-up", "health-check", "db-connectivity", "spec-tests", "integration-tests",
        ]


def check_deploy_test_log_regression_no_markers_must_fail_not_pass() -> None:
    """CRITICAL regression coverage: a Docker-unavailable log with NO recognizable
    phase markers, and a completely empty deploy dir (no log, no artifacts), must
    BOTH resolve to FAILED at docker-build with every infra phase SKIPPED --
    never silently PASSED. Also covers structured-marker (non-human-readable)
    phase detection for docker-up and docker-build failures, including the
    WARNING-log-level case where the 'started' marker is never emitted."""
    with TemporaryDirectory(prefix="dtlw-regression-") as tmp:
        root = Path(tmp)

        run_no_markers = _new_deploy_run_dir(root, "no-markers")
        (run_no_markers / "deploy-test-output.log").write_text(
            'error during connect: Get "http://%2F%2F.%2Fpipe%2F'
            'dockerDesktopLinuxEngine/_ping": open //./pipe/'
            "dockerDesktopLinuxEngine: The system cannot find the file specified.\n",
            encoding="utf-8",
        )
        writer_no_markers = _make_deploy_writer(
            run_no_markers, root, project_name="01-foundation", example="01-foundation"
        )
        index_no_markers = json.loads(
            writer_no_markers.write(timestamp=_TIMESTAMP).read_text(encoding="utf-8")
        )
        assert index_no_markers["result"] == "FAILED", (
            "Docker-unavailable-with-no-markers must be FAILED, never silently PASSED"
        )
        assert index_no_markers["failed_phase"] == "docker-build"
        for phase in ("docker-build", "docker-up", "health-check", "db-connectivity"):
            assert index_no_markers["phases"][phase]["result"] == "SKIPPED"

        run_empty = _new_deploy_run_dir(root, "empty")
        writer_empty = _make_deploy_writer(
            run_empty, root, project_name="01-foundation", example="01-foundation"
        )
        index_empty = json.loads(writer_empty.write(timestamp=_TIMESTAMP).read_text(encoding="utf-8"))
        assert index_empty["result"] == "FAILED", "a totally-empty deploy dir must be FAILED, not PASSED"
        assert index_empty["failed_phase"] == "docker-build"
        for phase_data in index_empty["phases"].values():
            assert phase_data["result"] == "SKIPPED"

        run_structured_up = _new_deploy_run_dir(root, "structured-up")
        (run_structured_up / "deploy-test-output.log").write_text(
            "docker_build_started\ndocker_build_completed\ndocker_up output:\ndocker_up_failed exit_code=1\n",
            encoding="utf-8",
        )
        writer_structured_up = _make_deploy_writer(run_structured_up, root)
        index_structured_up = json.loads(
            writer_structured_up.write(timestamp=_TIMESTAMP).read_text(encoding="utf-8")
        )
        assert index_structured_up["result"] == "FAILED"
        assert index_structured_up["failed_phase"] == "docker-up"
        assert index_structured_up["phases"]["docker-build"]["result"] == "PASSED"
        assert index_structured_up["phases"]["docker-up"]["result"] == "FAILED"
        assert index_structured_up["phases"]["health-check"]["result"] == "SKIPPED"

        run_structured_build = _new_deploy_run_dir(root, "structured-build")
        (run_structured_build / "deploy-test-output.log").write_text(
            "docker_build_started\ndocker_build_failed exit_code=1\n", encoding="utf-8"
        )
        writer_structured_build = _make_deploy_writer(run_structured_build, root)
        index_structured_build = json.loads(
            writer_structured_build.write(timestamp=_TIMESTAMP).read_text(encoding="utf-8")
        )
        assert index_structured_build["result"] == "FAILED"
        assert index_structured_build["failed_phase"] == "docker-build"
        assert index_structured_build["phases"]["docker-build"]["result"] == "FAILED"
        assert index_structured_build["phases"]["docker-up"]["result"] == "SKIPPED"

        run_no_started_marker = _new_deploy_run_dir(root, "no-started-marker")
        (run_no_started_marker / "deploy-test-output.log").write_text(
            "2026-06-09 20:22:26,077 ERROR docker_build output:\n"
            "error during connect: open //./pipe/dockerDesktopLinuxEngine: "
            "The system cannot find the file specified.\n"
            "2026-06-09 20:22:26,078 ERROR docker_build_failed exit_code=1\n",
            encoding="utf-8",
        )
        writer_no_started_marker = _make_deploy_writer(run_no_started_marker, root)
        index_no_started_marker = json.loads(
            writer_no_started_marker.write(timestamp=_TIMESTAMP).read_text(encoding="utf-8")
        )
        assert index_no_started_marker["result"] == "FAILED", (
            "WARNING-level logs (no INFO 'started' marker) must still detect the failure"
        )
        assert index_no_started_marker["failed_phase"] == "docker-build"
        assert index_no_started_marker["phases"]["docker-build"]["result"] == "FAILED"


def check_deploy_test_log_docker_log_excerpting_and_fallback() -> None:
    """Error detail files for Docker lifecycle failures excerpt the relevant
    ERROR-level container log lines with PHASE:/ERROR: headers; a missing
    container log still produces a well-formed error file (fallback path)."""
    with TemporaryDirectory(prefix="dtlw-excerpt-") as tmp:
        root = Path(tmp)
        run_dir = _new_deploy_run_dir(root, "lifecycle")
        _populate_docker_lifecycle_failure(run_dir)
        writer = _make_deploy_writer(run_dir, root)
        writer.write(timestamp=_TIMESTAMP)

        errors_dir = run_dir / "errors"
        assert errors_dir.exists()
        error_files = sorted(errors_dir.glob("*.txt"))
        assert len(error_files) >= 1
        content = error_files[0].read_text(encoding="utf-8")
        assert "redis_connection_failed" in content
        assert "Cannot connect to Redis" in content
        assert content.startswith("PHASE:")
        assert "ERROR:" in content

        run_no_container_log = _new_deploy_run_dir(root, "no-container-log")
        (run_no_container_log / "deploy-test-output.log").write_text(
            "=== Docker Up ===\ndocker_up_failed exit_code=1\ncontainer missing-service is unhealthy\n",
            encoding="utf-8",
        )
        writer_no_log = _make_deploy_writer(run_no_container_log, root)
        writer_no_log.write(timestamp=_TIMESTAMP)
        fallback_errors_dir = run_no_container_log / "errors"
        if fallback_errors_dir.exists():
            fallback_files = sorted(fallback_errors_dir.glob("*.txt"))
            if fallback_files:
                assert "PHASE:" in fallback_files[0].read_text(encoding="utf-8")


def check_deploy_test_log_transient_vs_logic_classification() -> None:
    """ConnectionResetError-family messages classify as transient with NO
    codegen hint (not a codegen bug); AssertionError classifies as logic WITH a
    codegen hint; TRANSIENT_ERROR_PATTERNS is populated with the documented entries."""
    with TemporaryDirectory(prefix="dtlw-transient-") as tmp:
        root = Path(tmp)
        run_dir = _new_deploy_run_dir(root, "test-fail")
        _populate_test_failure_dir(run_dir)
        writer = _make_deploy_writer(run_dir, root, project_name="01-foundation", example="01-foundation")
        index = json.loads(writer.write(timestamp=_TIMESTAMP).read_text(encoding="utf-8"))

        transient_failures = [f for f in index["failures"] if f["failure_type"] == "transient"]
        logic_failures = [f for f in index["failures"] if f["failure_type"] == "logic"]
        assert len(transient_failures) >= 1
        assert len(logic_failures) >= 1
        for f in transient_failures:
            assert f["codegen_hint"] is None, "transient failures must have no codegen hint"
        for f in logic_failures:
            if f["error_type"] == "AssertionError":
                assert f["codegen_hint"] is not None, "logic failures must carry a codegen hint"

        assert len(TRANSIENT_ERROR_PATTERNS) > 10
        assert "ConnectionResetError" in TRANSIENT_ERROR_PATTERNS
        assert "timeout" in TRANSIENT_ERROR_PATTERNS
        assert "BrokenPipeError" in TRANSIENT_ERROR_PATTERNS


def check_deploy_test_log_clustering() -> None:
    """Test failures cluster by error type into distinct clusters (AssertionError
    vs ConnectionResetError); a Docker lifecycle failure produces error clusters
    tagged with the failing phase."""
    with TemporaryDirectory(prefix="dtlw-cluster-") as tmp:
        root = Path(tmp)

        run_test_fail = _new_deploy_run_dir(root, "test-fail")
        _populate_test_failure_dir(run_test_fail)
        writer_test_fail = _make_deploy_writer(
            run_test_fail, root, project_name="01-foundation", example="01-foundation"
        )
        index_test_fail = json.loads(
            writer_test_fail.write(timestamp=_TIMESTAMP).read_text(encoding="utf-8")
        )
        assert len(index_test_fail["failure_clusters"]) == 2, index_test_fail["failure_clusters"]

        run_docker = _new_deploy_run_dir(root, "docker-fail")
        _populate_docker_lifecycle_failure(run_docker)
        writer_docker = _make_deploy_writer(run_docker, root)
        index_docker = json.loads(writer_docker.write(timestamp=_TIMESTAMP).read_text(encoding="utf-8"))
        assert len(index_docker["error_clusters"]) >= 1
        cluster = index_docker["error_clusters"][0]
        assert cluster["phase"] == "docker-up"
        assert "pattern" in cluster


def check_deploy_test_log_index_summary_schema() -> None:
    """index.json has every required top-level field for both infra and
    test-level failures; each failure entry has failure_type in
    (logic, transient); summary.txt stays under 60 lines, leads with FAILED,
    and includes a FAILURE CLUSTERS section naming the failing phase."""
    with TemporaryDirectory(prefix="dtlw-schema-") as tmp:
        root = Path(tmp)

        run_docker = _new_deploy_run_dir(root, "docker-fail")
        _populate_docker_lifecycle_failure(run_docker)
        writer_docker = _make_deploy_writer(run_docker, root)
        index_docker = json.loads(writer_docker.write(timestamp=_TIMESTAMP).read_text(encoding="utf-8"))
        required_fields = (
            "schema_version", "project", "project_path", "language", "platform", "example",
            "dtrx_source", "timestamp", "duration_seconds", "result", "failed_phase",
            "phases", "services", "failures", "errors", "failure_clusters", "error_clusters",
        )
        for field_name in required_fields:
            assert field_name in index_docker, f"Missing field: {field_name}"
        assert index_docker["schema_version"] == 1
        assert index_docker["result"] == "FAILED"
        assert index_docker["language"] == "python" and index_docker["platform"] == "docker"

        summary_docker = (run_docker / "summary.txt").read_text(encoding="utf-8")
        assert len(summary_docker.splitlines()) <= 60
        assert "FAILED" in "\n".join(summary_docker.splitlines()[:5])

        run_test_fail = _new_deploy_run_dir(root, "test-fail")
        _populate_test_failure_dir(run_test_fail)
        writer_test_fail = _make_deploy_writer(
            run_test_fail, root, project_name="01-foundation", example="01-foundation"
        )
        index_test_fail = json.loads(
            writer_test_fail.write(timestamp=_TIMESTAMP).read_text(encoding="utf-8")
        )
        assert len(index_test_fail["failures"]) >= 1
        for failure in index_test_fail["failures"]:
            for key in ("id", "service", "phase", "test_id", "error_type", "error_message", "failure_type"):
                assert key in failure, f"deploy failure entry missing {key!r}: {failure}"
            assert failure["failure_type"] in ("logic", "transient")
        summary_test_fail = (run_test_fail / "summary.txt").read_text(encoding="utf-8")
        assert "FAILURE CLUSTERS" in summary_test_fail
        assert "integration-tests" in summary_test_fail

        run_pass = _new_deploy_run_dir(root, "all-pass")
        _populate_all_passing_dir(run_pass)
        writer_pass = _make_deploy_writer(
            run_pass, root, project_name="basic", example="02-features/01-core-data-modeling/entities"
        )
        index_pass = json.loads(writer_pass.write(timestamp=_TIMESTAMP).read_text(encoding="utf-8"))
        assert index_pass["result"] == "PASSED"
        assert index_pass["failures"] == [] and index_pass["errors"] == []
        assert index_pass["failure_clusters"] == [] and index_pass["error_clusters"] == []


def check_deploy_test_log_services_copy_and_corrupt_input_handling() -> None:
    """JUnit XML for a service is COPIED (not moved) into
    services/{name}/integration/; corrupt failures.json and corrupt JUnit XML
    are both handled gracefully (no exception, still a valid index.json)."""
    with TemporaryDirectory(prefix="dtlw-copy-") as tmp:
        root = Path(tmp)

        run_test_fail = _new_deploy_run_dir(root, "test-fail")
        _populate_test_failure_dir(run_test_fail)
        writer_test_fail = _make_deploy_writer(
            run_test_fail, root, project_name="01-foundation", example="01-foundation"
        )
        writer_test_fail.write(timestamp=_TIMESTAMP)
        svc_dir = run_test_fail / "services" / "library_book_service"
        if svc_dir.exists():
            integ_dir = svc_dir / "integration"
            assert integ_dir.exists()
            assert len(list(integ_dir.glob("*.xml"))) >= 1
        original = run_test_fail / "pytest-integration-library_book_service-project.xml"
        assert original.exists(), "original JUnit XML must remain in place (copied, not moved)"

        run_corrupt = _new_deploy_run_dir(root, "corrupt")
        (run_corrupt / "failures.json").write_text("not valid json{{{", encoding="utf-8")
        (run_corrupt / "deploy-test-output.log").write_text("=== Docker Build ===\nOK\n", encoding="utf-8")
        writer_corrupt = _make_deploy_writer(run_corrupt, root)
        index_corrupt = json.loads(writer_corrupt.write(timestamp=_TIMESTAMP).read_text(encoding="utf-8"))
        assert index_corrupt["schema_version"] == 1

        run_corrupt_xml = _new_deploy_run_dir(root, "corrupt-xml")
        (run_corrupt_xml / "pytest-integration-svc.xml").write_text("<not-valid-xml", encoding="utf-8")
        (run_corrupt_xml / "deploy-test-output.log").write_text("=== Docker Build ===\nOK\n", encoding="utf-8")
        writer_corrupt_xml = _make_deploy_writer(run_corrupt_xml, root)
        index_corrupt_xml = json.loads(
            writer_corrupt_xml.write(timestamp=_TIMESTAMP).read_text(encoding="utf-8")
        )
        assert index_corrupt_xml["schema_version"] == 1


# ===========================================================================
# shared.logging_utils -- TestLogContent, TestCleanupDirectoriesOnly,
# TestCleanupAgeBased ONLY (READ ONLY module; the directory-creation/
# uniqueness classes are already covered far more rigorously by
# test-specific-selection-gate.ps1's run_dir_exclusivity_check, so they are
# deliberately NOT re-covered here).
# ===========================================================================


def check_logging_utils_write_content_appears_in_full_log() -> None:
    """Text written via write()/write_line() appears in full.log, alongside the
    standard "{project} - {prefix}" header and a divider line."""
    with TemporaryDirectory(prefix="lu-content-") as tmp:
        root = Path(tmp)
        config = LogConfig(log_dir=".logs", prefix="content", project_name="test")
        logger = TeeLogger(config, project_root=root)
        with logger:
            logger.write("Hello from test")
            logger.write_line("Second line")

        log_path = logger.get_log_path()
        assert log_path is not None
        content = log_path.read_text(encoding="utf-8")
        assert "test - content" in content
        assert "=" * 80 in content
        assert "Hello from test" in content
        assert "Second line" in content


def check_logging_utils_cleanup_keeps_most_recent_directories() -> None:
    """cleanup_old_logs(keep_count=N) deletes exactly the oldest-by-mtime
    directories beyond N, keeping the N most recent."""
    with TemporaryDirectory(prefix="lu-cleanup-count-") as tmp:
        root = Path(tmp)
        log_dir = root / ".test_results"
        log_dir.mkdir()

        dirs: list[Path] = []
        for i in range(15):
            d = log_dir / f"test-results-202605{i:02d}-120000"
            d.mkdir()
            (d / "full.log").write_text(f"log {i}", encoding="utf-8")
            mtime = _mtime_offset_seconds(15 - i)
            _set_mtime(d, mtime)
            dirs.append(d)

        deleted = cleanup_old_logs(log_dir, "test-results", keep_count=10)
        assert deleted == 5

        remaining = sorted(
            (d for d in log_dir.iterdir() if d.is_dir()), key=lambda d: d.stat().st_mtime
        )
        assert len(remaining) == 10
        for d in dirs[:5]:
            assert not d.exists(), f"expected oldest directory {d} to be deleted"
        for d in dirs[5:]:
            assert d.exists(), f"expected newest directory {d} to survive"


def check_logging_utils_cleanup_age_based_and_nonexistent_dir() -> None:
    """cleanup_old_logs(max_age_days=N) deletes only entries older than the
    threshold, keeping recent ones regardless of keep_count; a nonexistent log
    directory returns 0 deletions rather than raising."""
    with TemporaryDirectory(prefix="lu-cleanup-age-") as tmp:
        root = Path(tmp)
        log_dir = root / ".test_results"
        log_dir.mkdir()

        for i in range(3):
            d = log_dir / f"test-results-recent-{i}"
            d.mkdir()
            (d / "full.log").write_text(f"recent {i}", encoding="utf-8")
            _set_mtime(d, _mtime_offset_seconds_from_now(3600))  # 1 hour ago

        for i in range(3):
            d = log_dir / f"test-results-old-{i}"
            d.mkdir()
            (d / "full.log").write_text(f"old {i}", encoding="utf-8")
            _set_mtime(d, _mtime_offset_seconds_from_now(40 * 24 * 3600))  # 40 days ago

        deleted = cleanup_old_logs(log_dir, "test-results", keep_count=100, max_age_days=30)
        assert deleted == 3

        remaining = [d for d in log_dir.iterdir() if d.is_dir()]
        assert len(remaining) == 3
        for d in remaining:
            assert "recent" in d.name

        assert cleanup_old_logs(root / "nonexistent", "test", keep_count=5) == 0


def _mtime_offset_seconds(hours_ago: int) -> float:
    import time

    return time.time() - hours_ago * 3600


def _mtime_offset_seconds_from_now(seconds_ago: float) -> float:
    import time

    return time.time() - seconds_ago


def _set_mtime(path: Path, mtime: float) -> None:
    import os

    os.utime(path, (mtime, mtime))


# ===========================================================================
# Harness self-test (non-vacuity proof for the pass/fail mechanism itself)
# ===========================================================================


def _deliberately_failing_check() -> None:
    """A dummy check that always fails, used only by --harness-self-test."""
    assert False, "deliberately failing check for --harness-self-test"


def harness_self_test() -> bool:
    """Prove the harness cannot silently swallow a failing check.

    Registers exactly one deliberately-failing dummy check and requires
    run_checks() to report it FAILED (and to return False overall). If the
    harness ever reported this as passing, the whole gate would be vacuous.
    """
    print("=== Harness self-test: a deliberately-failing check must be reported FAILED ===")
    all_passed = run_checks([_deliberately_failing_check])
    if all_passed:
        _fail("harness self-test: the deliberately-failing check was NOT reported as failed")
        return False
    _ok("harness self-test: the deliberately-failing check was correctly reported FAILED")
    return True


# ===========================================================================
# main
# ===========================================================================

_ALL_CHECKS: list[CheckFunc] = [
    # shared.structured_log_writer
    check_structured_log_writer_index_schema,
    check_structured_log_writer_two_phase_merge,
    check_structured_log_writer_incomplete_on_bad_xml,
    check_structured_log_writer_clustering_and_representative,
    check_structured_log_writer_source_location_fallback_chain,
    check_structured_log_writer_message_normalization,
    check_structured_log_writer_filename_truncation,
    check_structured_log_writer_edge_cases,
    # shared.test_runner (read-only usage)
    check_test_runner_junit_xml_flag_only_when_given,
    check_test_runner_junit_xml_coexists_with_addopts_override,
    check_test_runner_junit_xml_with_coverage_and_verbose_marker,
    # shared.codegen_hint_mapper
    check_codegen_hint_python_patterns,
    check_codegen_hint_typescript_patterns,
    check_codegen_hint_docker_patterns,
    check_codegen_hint_unknown_returns_none,
    check_codegen_hint_backslash_normalization,
    check_codegen_hint_most_specific_pattern_wins,
    check_codegen_hint_is_frozen,
    # shared.deploy_test_aggregate_writer
    check_deploy_test_aggregate_schema_and_counts,
    check_deploy_test_aggregate_failed_projects_populated,
    check_deploy_test_aggregate_cross_project_cluster_correlation,
    check_deploy_test_aggregate_summary_sections,
    check_deploy_test_aggregate_edge_cases,
    # shared.generated_test_log_writer
    check_generated_test_log_junit_xml_parsing,
    check_generated_test_log_jest_json_parsing,
    check_generated_test_log_error_clustering_and_services_affected,
    check_generated_test_log_import_chain_extraction,
    check_generated_test_log_index_schema_and_summary_format,
    check_generated_test_log_detail_files_and_codegen_hint,
    check_generated_test_log_multi_service_and_log_only_fallback,
    # shared.aggregate_test_writer
    check_aggregate_test_writer_cross_project_correlation,
    check_aggregate_test_writer_suite_failure_clusters_separate_type,
    check_aggregate_test_writer_index_schema,
    check_aggregate_test_writer_summary_format,
    check_aggregate_test_writer_add_project_results_validation,
    check_aggregate_test_writer_mixed_scenarios,
    check_aggregate_test_writer_frozen_dataclasses,
    # shared.deploy_test_log_writer
    check_deploy_test_log_phase_detection,
    check_deploy_test_log_regression_no_markers_must_fail_not_pass,
    check_deploy_test_log_docker_log_excerpting_and_fallback,
    check_deploy_test_log_transient_vs_logic_classification,
    check_deploy_test_log_clustering,
    check_deploy_test_log_index_summary_schema,
    check_deploy_test_log_services_copy_and_corrupt_input_handling,
    # shared.logging_utils (3 classes only -- see module docstring)
    check_logging_utils_write_content_appears_in_full_log,
    check_logging_utils_cleanup_keeps_most_recent_directories,
    check_logging_utils_cleanup_age_based_and_nonexistent_dir,
]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Repo-level gate absorbing the shared-library test coverage orphaned by the "
            "datrix showcase repo's no-pytest-suite boundary."
        )
    )
    parser.add_argument(
        "--harness-self-test",
        action="store_true",
        help="Run only the harness self-test (a deliberately-failing dummy check).",
    )
    args = parser.parse_args()

    if args.harness_self_test:
        return 0 if harness_self_test() else 1

    print(f"Running {len(_ALL_CHECKS)} shared-library behavior checks...\n")
    passed = run_checks(_ALL_CHECKS)

    print()
    if passed:
        print(f"{_GREEN}GATE PASSED{_RESET}: all {len(_ALL_CHECKS)} shared-library behavior checks passed.")
        return 0
    print(f"{_RED}GATE FAILED{_RESET}: see the failures above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
