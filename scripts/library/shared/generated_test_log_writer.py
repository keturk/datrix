"""Structured log writer for generated project test results.

Produces per-project structured output directories from JUnit XML (Python)
and Jest JSON (TypeScript) test results. Designed for AI agent consumption —
the agent reads index.json first, then drills into individual error files.
"""

from __future__ import annotations

import json
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from shared.codegen_hint_mapper import CodegenHint, get_codegen_hint

logger = logging.getLogger(__name__)

_SCHEMA_VERSION = 1
_MAX_FILENAME_BODY_LENGTH = 120

# Patterns for normalizing error messages before clustering
_SINGLE_QUOTED = re.compile(r"'[^']*'")
_DOUBLE_QUOTED = re.compile(r'"[^"]*"')
_HEX_ADDRESS = re.compile(r"0x[0-9a-fA-F]+")
_STANDALONE_NUMBER = re.compile(r"\b\d+\b")

# ANSI escape codes
_ANSI_ESCAPE = re.compile(
    r"\x1b\[[0-9;]*[a-zA-Z]"
    r"|\x1b\[\?[0-9;]*[a-zA-Z]"
    r"|#x1B\[[0-9;]*[a-zA-Z]"
    r"|#x1B\[\?[0-9;]*[a-zA-Z]"
)

# Patterns for extracting import chains from tracebacks
_IMPORT_CHAIN_FRAME = re.compile(
    r"^\s*(.+?):(\d+):\s+in\s+(?:<module>|[^\n]+)\s*\n"
    r"\s*(?:from\s+(\S+)\s+import\s+(\S+)|import\s+(\S+))",
    re.MULTILINE,
)
_FRAME_LINE = re.compile(r"^\s*(.+?):(\d+):\s+in\s+(.+)$", re.MULTILINE)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TestFailure:
    """A single test assertion failure."""

    id: int
    service: str
    test_id: str
    test_name: str
    error_type: str
    error_message: str
    traceback: str
    generated_file: str | None = None
    log_file: str = ""


@dataclass(frozen=True)
class TestError:
    """A collection/import error that prevents tests from running."""

    id: int
    service: str
    test_id: str
    error_type: str
    error_message: str
    import_chain: list[str]
    traceback: str
    generated_file: str | None = None
    log_file: str = ""


@dataclass(frozen=True)
class ErrorCluster:
    """A group of errors/failures sharing a common pattern."""

    cluster_id: int
    pattern: str
    generated_file: str | None
    count: int
    services_affected: list[str]
    error_ids: list[int]
    representative_error_id: int
    codegen_hint: dict[str, str] | None


@dataclass
class _ServiceData:
    """Internal mutable holder for service results."""

    name: str
    result: str  # "PASSED" | "FAILED"
    counts: dict[str, int]
    log_path: Path | None
    failures: list[TestFailure]
    errors: list[TestError]
    suite_failure_message: str | None = None


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------


class GeneratedTestLogWriter:
    """Post-processes generated project test results into structured directories.

    Produces:
    - index.json: Machine-readable index (agent reads first)
    - summary.txt: Human-readable summary (< 50 lines)
    - services/{name}/service.log: Per-service raw output
    - services/{name}/junit.xml or jest-results.json: Structured data source
    - failures/NNN-*.txt: One file per unique failure
    - errors/NNN-*.txt: One file per collection/import error
    """

    def __init__(
        self,
        project_path: str,
        language: str,
        platform: str,
        example: str,
        run_dir: Path,
        dtrx_source: str,
    ) -> None:
        """Initialize the writer.

        Args:
            project_path: Relative project path (e.g. ``typescript/docker/03-domains/ecommerce``).
            language: ``python`` or ``typescript``.
            platform: ``docker`` or other platform identifier.
            example: Example name (e.g. ``03-domains/ecommerce``).
            run_dir: Timestamped output directory for this project's test run.
            dtrx_source: Path to the .dtrx source file relative to datrix root.
        """
        self._project_path = project_path
        self._language = language
        self._platform = platform
        self._example = example
        self._run_dir = run_dir
        self._dtrx_source = dtrx_source
        self._services: list[_ServiceData] = []
        self._next_failure_id = 1
        self._next_error_id = 1

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    def add_service_junit_xml(
        self, service_name: str, xml_path: Path, log_path: Path
    ) -> None:
        """Add results from a Python service's JUnit XML output.

        Args:
            service_name: Name of the service.
            xml_path: Path to the JUnit XML file produced by pytest.
            log_path: Path to the raw console log for this service.

        Raises:
            FileNotFoundError: If xml_path does not exist.
        """
        if not xml_path.exists():
            raise FileNotFoundError(
                f"JUnit XML not found at {xml_path}. "
                f"Expected pytest to produce --junit-xml output."
            )

        logger.info(
            "generated_test_log_add_junit service=%s xml=%s",
            service_name,
            xml_path,
        )

        tree = ET.parse(str(xml_path))  # noqa: S314
        root = tree.getroot()

        suites: list[ET.Element] = []
        if root.tag == "testsuites":
            suites = list(root.iter("testsuite"))
        elif root.tag == "testsuite":
            suites = [root]
        else:
            logger.warning(
                "generated_test_log_unexpected_root tag=%s path=%s",
                root.tag,
                xml_path,
            )

        passed = 0
        failed = 0
        errors = 0
        skipped = 0
        suite_failures = 0
        failures_list: list[TestFailure] = []
        errors_list: list[TestError] = []

        for suite in suites:
            for tc in suite.findall("testcase"):
                failure_el = tc.find("failure")
                error_el = tc.find("error")
                skipped_el = tc.find("skipped")

                classname = tc.get("classname", "")
                name = tc.get("name", "")
                test_id = f"{classname}::{name}" if classname else name

                if failure_el is not None:
                    failed += 1
                    err_type = failure_el.get("type", "")
                    err_msg = _ANSI_ESCAPE.sub(
                        "", failure_el.get("message", "")
                    )
                    tb = _ANSI_ESCAPE.sub("", failure_el.text or "")
                    gen_file = _extract_generated_file(tb, service_name)
                    tf = TestFailure(
                        id=self._next_failure_id,
                        service=service_name,
                        test_id=test_id,
                        test_name=name,
                        error_type=err_type,
                        error_message=err_msg,
                        traceback=tb,
                        generated_file=gen_file,
                    )
                    failures_list.append(tf)
                    self._next_failure_id += 1

                elif error_el is not None:
                    errors += 1
                    err_type = error_el.get("type", "")
                    err_msg = _ANSI_ESCAPE.sub(
                        "", error_el.get("message", "")
                    )
                    tb = _ANSI_ESCAPE.sub("", error_el.text or "")
                    chain = _extract_import_chain(tb)
                    gen_file = _extract_generated_file(tb, service_name)
                    te = TestError(
                        id=self._next_error_id,
                        service=service_name,
                        test_id=test_id,
                        error_type=err_type,
                        error_message=err_msg,
                        import_chain=chain,
                        traceback=tb,
                        generated_file=gen_file,
                    )
                    errors_list.append(te)
                    self._next_error_id += 1

                elif skipped_el is not None:
                    skipped += 1
                else:
                    passed += 1

        result = "FAILED" if (failed > 0 or errors > 0 or suite_failures > 0) else "PASSED"
        svc = _ServiceData(
            name=service_name,
            result=result,
            counts={
                "passed": passed,
                "failed": failed,
                "errors": errors,
                "skipped": skipped,
                "suite_failures": suite_failures,
            },
            log_path=log_path,
            failures=failures_list,
            errors=errors_list,
        )
        self._services.append(svc)

        # Copy structured data into services/ subdir
        svc_dir = self._run_dir / "services" / service_name
        svc_dir.mkdir(parents=True, exist_ok=True)
        _copy_file(xml_path, svc_dir / "junit.xml")
        if log_path.exists():
            _copy_file(log_path, svc_dir / "service.log")

    def add_service_jest_json(
        self, service_name: str, json_path: Path, log_path: Path
    ) -> None:
        """Add results from a TypeScript service's Jest JSON output.

        Args:
            service_name: Name of the service.
            json_path: Path to the Jest JSON results file.
            log_path: Path to the raw console log for this service.

        Raises:
            FileNotFoundError: If json_path does not exist.
        """
        if not json_path.exists():
            raise FileNotFoundError(
                f"Jest JSON not found at {json_path}. "
                f"Expected Jest to produce --json --outputFile output."
            )

        logger.info(
            "generated_test_log_add_jest service=%s json=%s",
            service_name,
            json_path,
        )

        data = json.loads(json_path.read_text(encoding="utf-8"))

        passed = 0
        failed = 0
        errors = 0
        skipped = 0
        suite_failures = 0
        failures_list: list[TestFailure] = []
        errors_list: list[TestError] = []
        suite_failure_msg: str | None = None

        for test_suite in data.get("testResults", []):
            test_file = test_suite.get("testFilePath", "")

            # Check for suite execution error (prevents tests from running)
            exec_error = test_suite.get("testExecError")
            if exec_error is not None:
                suite_failures += 1
                msg = exec_error.get("message", "")
                stack = exec_error.get("stack", "")
                if suite_failure_msg is None:
                    suite_failure_msg = msg
                te = TestError(
                    id=self._next_error_id,
                    service=service_name,
                    test_id=test_file,
                    error_type="SuiteFailure",
                    error_message=msg,
                    import_chain=[],
                    traceback=stack,
                    generated_file=_extract_generated_file_from_path(test_file),
                )
                errors_list.append(te)
                self._next_error_id += 1
                continue

            for test_result in test_suite.get("testResults", []):
                status = test_result.get("status", "")
                title = test_result.get("title", "")
                full_name = test_result.get("fullName", title)
                test_id = f"{test_file}::{full_name}"

                if status == "passed":
                    passed += 1
                elif status == "pending":
                    skipped += 1
                elif status == "failed":
                    failed += 1
                    failure_messages = test_result.get("failureMessages", [])
                    msg = "\n".join(failure_messages)
                    err_type = _extract_error_type_from_jest(msg)
                    gen_file = _extract_generated_file_from_path(test_file)
                    tf = TestFailure(
                        id=self._next_failure_id,
                        service=service_name,
                        test_id=test_id,
                        test_name=title,
                        error_type=err_type,
                        error_message=msg.split("\n", 1)[0] if msg else "",
                        traceback=msg,
                        generated_file=gen_file,
                    )
                    failures_list.append(tf)
                    self._next_failure_id += 1

        result = "FAILED" if (failed > 0 or errors > 0 or suite_failures > 0) else "PASSED"
        svc = _ServiceData(
            name=service_name,
            result=result,
            counts={
                "passed": passed,
                "failed": failed,
                "errors": errors,
                "skipped": skipped,
                "suite_failures": suite_failures,
            },
            log_path=log_path,
            failures=failures_list,
            errors=errors_list,
            suite_failure_message=suite_failure_msg,
        )
        self._services.append(svc)

        # Copy structured data into services/ subdir
        svc_dir = self._run_dir / "services" / service_name
        svc_dir.mkdir(parents=True, exist_ok=True)
        _copy_file(json_path, svc_dir / "jest-results.json")
        if log_path.exists():
            _copy_file(log_path, svc_dir / "service.log")

    def add_service_log_only(
        self,
        service_name: str,
        log_path: Path,
        passed: int,
        failed: int,
        errors: int,
    ) -> None:
        """Add results from a service where only log + counts are available.

        Fallback for older generated projects that don't produce JUnit XML
        or Jest JSON.

        Args:
            service_name: Name of the service.
            log_path: Path to the raw console log.
            passed: Number of tests passed.
            failed: Number of tests failed.
            errors: Number of test errors.
        """
        logger.info(
            "generated_test_log_add_log_only service=%s passed=%d "
            "failed=%d errors=%d",
            service_name,
            passed,
            failed,
            errors,
        )

        result = "FAILED" if (failed > 0 or errors > 0) else "PASSED"
        svc = _ServiceData(
            name=service_name,
            result=result,
            counts={
                "passed": passed,
                "failed": failed,
                "errors": errors,
                "skipped": 0,
                "suite_failures": 0,
            },
            log_path=log_path,
            failures=[],
            errors=[],
        )
        self._services.append(svc)

        # Copy log into services/ subdir
        svc_dir = self._run_dir / "services" / service_name
        svc_dir.mkdir(parents=True, exist_ok=True)
        if log_path.exists():
            _copy_file(log_path, svc_dir / "service.log")

    def write(self, duration_seconds: float) -> Path:
        """Write all structured output files.

        Args:
            duration_seconds: Total duration of the test run in seconds.

        Returns:
            Path to the written index.json file.
        """
        timestamp = datetime.now()
        all_failures = _collect_all(self._services, "failures")
        all_errors = _collect_all(self._services, "errors")

        # Cluster failures and errors
        failure_clusters = _cluster_items(all_failures, "failure")
        error_clusters = _cluster_items(all_errors, "error")

        # Aggregate counts
        total_counts = _aggregate_counts(self._services)
        overall_result = "FAILED" if any(
            s.result == "FAILED" for s in self._services
        ) else "PASSED"

        # Write individual error/failure files
        failure_file_map = self._write_detail_files(all_failures, failure_clusters, "failures")
        error_file_map = self._write_detail_files(all_errors, error_clusters, "errors")

        # Update log_file on items
        for item in all_failures:
            object.__setattr__(item, "log_file", failure_file_map.get(item.id, ""))
        for item in all_errors:
            object.__setattr__(item, "log_file", error_file_map.get(item.id, ""))

        # Write index.json
        self._write_index_json(
            timestamp=timestamp,
            duration_seconds=duration_seconds,
            result=overall_result,
            counts=total_counts,
            failures=all_failures,
            errors=all_errors,
            failure_clusters=failure_clusters,
            error_clusters=error_clusters,
            failure_file_map=failure_file_map,
            error_file_map=error_file_map,
        )

        # Write summary.txt
        self._write_summary_txt(
            timestamp=timestamp,
            duration_seconds=duration_seconds,
            result=overall_result,
            counts=total_counts,
            failure_clusters=failure_clusters,
            error_clusters=error_clusters,
        )

        logger.info(
            "generated_test_log_writer_complete project=%s result=%s "
            "failures=%d errors=%d clusters=%d",
            self._project_path,
            overall_result,
            len(all_failures),
            len(all_errors),
            len(failure_clusters) + len(error_clusters),
        )

        return self._run_dir / "index.json"

    # ------------------------------------------------------------------
    # Internal — detail files
    # ------------------------------------------------------------------

    def _write_detail_files(
        self,
        items: list[TestFailure] | list[TestError],
        clusters: list[ErrorCluster],
        subdir_name: str,
    ) -> dict[int, str]:
        """Write individual failure/error detail files.

        Returns:
            Mapping from item ID to relative file path.
        """
        if not items:
            return {}

        # Build cluster lookup: item_id -> cluster
        id_to_cluster: dict[int, ErrorCluster] = {}
        for cluster in clusters:
            for eid in cluster.error_ids:
                id_to_cluster[eid] = cluster

        subdir = self._run_dir / subdir_name
        subdir.mkdir(parents=True, exist_ok=True)

        file_map: dict[int, str] = {}
        for seq, item in enumerate(items, start=1):
            filename = _make_detail_filename(seq, item)
            file_path = subdir / filename
            cluster = id_to_cluster.get(item.id)
            self._write_single_detail_file(item, cluster, file_path)
            file_map[item.id] = f"{subdir_name}/{filename}"

        return file_map

    def _write_single_detail_file(
        self,
        item: TestFailure | TestError,
        cluster: ErrorCluster | None,
        file_path: Path,
    ) -> None:
        """Write a single error/failure detail file."""
        lines: list[str] = []
        lines.append(f"SERVICE: {item.service}")
        lines.append(f"TEST: {item.test_id}")
        if cluster is not None:
            lines.append(f"CLUSTER: {cluster.pattern}")
        lines.append(f"ERROR: {item.error_type}: {item.error_message}")
        lines.append("")

        if isinstance(item, TestError) and item.import_chain:
            lines.append("--- Import Chain ---")
            for step in item.import_chain:
                lines.append(step)
            lines.append("")

        if item.generated_file:
            lines.append("--- Generated File ---")
            lines.append(item.generated_file)
            lines.append("")

        if item.traceback:
            lines.append("--- Full Traceback ---")
            lines.append(item.traceback.rstrip())
            lines.append("")

        hint = get_codegen_hint(item.generated_file) if item.generated_file else None
        if hint is not None:
            lines.append("--- Codegen Hint ---")
            lines.append(f"Probable template: {hint.probable_template}")
            lines.append(f"Probable generator: {hint.probable_generator}")
            lines.append(f".dtrx source: {self._dtrx_source}")
            lines.append("")

        file_path.write_text("\n".join(lines), encoding="utf-8")

    # ------------------------------------------------------------------
    # Internal — index.json
    # ------------------------------------------------------------------

    def _write_index_json(
        self,
        timestamp: datetime,
        duration_seconds: float,
        result: str,
        counts: dict[str, int],
        failures: list[TestFailure],
        errors: list[TestError],
        failure_clusters: list[ErrorCluster],
        error_clusters: list[ErrorCluster],
        failure_file_map: dict[int, str],
        error_file_map: dict[int, str],
    ) -> None:
        """Write the index.json file."""
        services_json: list[dict[str, Any]] = []
        for svc in self._services:
            svc_entry: dict[str, Any] = {
                "name": svc.name,
                "result": svc.result,
                "counts": svc.counts,
                "log_file": f"services/{svc.name}/service.log",
            }
            if svc.suite_failure_message is not None:
                svc_entry["suite_failure_message"] = svc.suite_failure_message
            services_json.append(svc_entry)

        failures_json: list[dict[str, Any]] = []
        for f in failures:
            entry: dict[str, Any] = {
                "id": f.id,
                "service": f.service,
                "test_id": f.test_id,
                "test_name": f.test_name,
                "error_type": f.error_type,
                "error_message": f.error_message,
                "generated_file": f.generated_file,
                "log_file": failure_file_map.get(f.id, ""),
            }
            failures_json.append(entry)

        errors_json: list[dict[str, Any]] = []
        for e in errors:
            entry = {
                "id": e.id,
                "service": e.service,
                "test_id": e.test_id,
                "error_type": e.error_type,
                "error_message": e.error_message,
                "import_chain": e.import_chain,
                "generated_file": e.generated_file,
                "log_file": error_file_map.get(e.id, ""),
            }
            errors_json.append(entry)

        fc_json = [_cluster_to_dict(c) for c in failure_clusters]
        ec_json = [_cluster_to_dict(c) for c in error_clusters]

        index: dict[str, Any] = {
            "schema_version": _SCHEMA_VERSION,
            "project": self._project_path,
            "project_path": str(self._run_dir.parent.parent),
            "language": self._language,
            "platform": self._platform,
            "example": self._example,
            "dtrx_source": self._dtrx_source,
            "timestamp": timestamp.strftime("%Y-%m-%dT%H:%M:%S"),
            "duration_seconds": round(duration_seconds, 2),
            "result": result,
            "counts": counts,
            "services": services_json,
            "failures": failures_json,
            "errors": errors_json,
            "failure_clusters": fc_json,
            "error_clusters": ec_json,
        }

        index_path = self._run_dir / "index.json"
        index_path.write_text(
            json.dumps(index, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # Internal — summary.txt
    # ------------------------------------------------------------------

    def _write_summary_txt(
        self,
        timestamp: datetime,
        duration_seconds: float,
        result: str,
        counts: dict[str, int],
        failure_clusters: list[ErrorCluster],
        error_clusters: list[ErrorCluster],
    ) -> None:
        """Write the human-readable summary.txt (< 50 lines)."""
        lines: list[str] = []
        example_label = self._example.rsplit("/", 1)[-1] if "/" in self._example else self._example
        lines.append(f"{example_label} unit test results ({self._language.capitalize()})")
        lines.append(
            f"{timestamp.strftime('%Y-%m-%d %H:%M:%S')} | "
            f"Duration: {duration_seconds:.1f}s"
        )
        lines.append("")

        total_services = len(self._services)
        failed_services = sum(1 for s in self._services if s.result == "FAILED")

        if result == "FAILED":
            parts: list[str] = []
            if counts["passed"] > 0:
                parts.append(f"{counts['passed']} passed")
            if counts["errors"] > 0:
                parts.append(f"{counts['errors']} errors")
            if counts["failed"] > 0:
                parts.append(f"{counts['failed']} failed")
            detail = ", ".join(parts)
            svc_detail = f" across {failed_services}/{total_services} services" if total_services > 1 else ""
            lines.append(f"RESULT: FAILED ({detail}{svc_detail})")
        else:
            lines.append(f"RESULT: PASSED ({counts['passed']} passed)")

        lines.append("")
        lines.append(f".dtrx source: {self._dtrx_source}")
        lines.append("")

        if error_clusters:
            lines.append("ERROR CLUSTERS:")
            for cluster in error_clusters:
                svc_count = len(cluster.services_affected)
                svc_label = f"across {svc_count} services" if svc_count > 1 else f"in {svc_count} service"
                lines.append(
                    f"  [{cluster.count} errors {svc_label}] {cluster.pattern}"
                )
                if cluster.generated_file:
                    lines.append(f"    Generated file: {cluster.generated_file}")
                if cluster.codegen_hint:
                    lines.append(
                        f"    Probable template: {cluster.codegen_hint['probable_template']}"
                    )
            lines.append("")

        if failure_clusters:
            lines.append("FAILURE CLUSTERS:")
            for cluster in failure_clusters:
                svc_count = len(cluster.services_affected)
                svc_label = f"across {svc_count} services" if svc_count > 1 else f"in {svc_count} service"
                lines.append(
                    f"  [{cluster.count} failures {svc_label}] {cluster.pattern}"
                )
                if cluster.generated_file:
                    lines.append(f"    Generated file: {cluster.generated_file}")
                if cluster.codegen_hint:
                    lines.append(
                        f"    Probable template: {cluster.codegen_hint['probable_template']}"
                    )
            lines.append("")

        lines.append("SERVICE RESULTS:")
        for svc in self._services:
            if svc.result == "PASSED":
                total = svc.counts["passed"]
                lines.append(f"  ✓ {svc.name:<40s} {total} passed")
            else:
                parts_list: list[str] = []
                if svc.counts["errors"] > 0:
                    parts_list.append(f"{svc.counts['errors']} errors")
                if svc.counts["failed"] > 0:
                    parts_list.append(f"{svc.counts['failed']} failed")
                if svc.counts["suite_failures"] > 0:
                    parts_list.append(f"{svc.counts['suite_failures']} suite failures")
                lines.append(f"  ✗ {svc.name:<40s} {', '.join(parts_list)}")

        summary_path = self._run_dir / "summary.txt"
        summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _copy_file(src: Path, dst: Path) -> None:
    """Copy a file, creating parent directories as needed."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(src.read_bytes())


def _collect_all(
    services: list[_ServiceData], attr: str
) -> list[Any]:
    """Collect all failures or errors from all services."""
    result: list[Any] = []
    for svc in services:
        result.extend(getattr(svc, attr))
    return result


def _aggregate_counts(services: list[_ServiceData]) -> dict[str, int]:
    """Sum counts across all services."""
    totals: dict[str, int] = {
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
        "suite_failures": 0,
    }
    for svc in services:
        for key in totals:
            totals[key] += svc.counts.get(key, 0)
    return totals


def normalize_error_message(error_type: str, error_message: str) -> str:
    """Normalize an error message for clustering.

    Replaces quoted strings, hex addresses, and standalone numbers
    with ``*`` to group similar errors together.

    Args:
        error_type: The exception type name.
        error_message: The raw error message text.

    Returns:
        Normalized pattern string like ``ErrorType: normalized message``.
    """
    normalized = _ANSI_ESCAPE.sub("", error_message)
    if error_type and normalized.startswith(f"{error_type}: "):
        normalized = normalized[len(error_type) + 2 :]
    elif error_type and normalized.startswith(f"{error_type}:"):
        normalized = normalized[len(error_type) + 1 :]
    first_line = normalized.split("\n", 1)[0]
    first_line = _SINGLE_QUOTED.sub("*", first_line)
    first_line = _DOUBLE_QUOTED.sub("*", first_line)
    first_line = _HEX_ADDRESS.sub("*", first_line)
    first_line = _STANDALONE_NUMBER.sub("*", first_line)
    return f"{error_type}: {first_line}"


def _cluster_items(
    items: list[TestFailure] | list[TestError],
    kind: str,
) -> list[ErrorCluster]:
    """Cluster items by normalized error pattern.

    Args:
        items: List of TestFailure or TestError objects.
        kind: ``failure`` or ``error`` (for logging).

    Returns:
        List of ErrorCluster objects sorted by count descending.
    """
    if not items:
        return []

    groups: dict[str, list[TestFailure | TestError]] = {}
    for item in items:
        pattern = normalize_error_message(item.error_type, item.error_message)
        if pattern not in groups:
            groups[pattern] = []
        groups[pattern].append(item)

    clusters: list[ErrorCluster] = []
    for cluster_id, (pattern, members) in enumerate(
        sorted(groups.items(), key=lambda kv: len(kv[1]), reverse=True),
        start=1,
    ):
        services_affected = sorted({m.service for m in members})

        # Pick generated_file from the first member that has one
        gen_file: str | None = None
        for m in members:
            if m.generated_file:
                gen_file = m.generated_file
                break

        # Codegen hint from the generated file
        hint_obj = get_codegen_hint(gen_file) if gen_file else None
        hint_dict: dict[str, str] | None = None
        if hint_obj is not None:
            hint_dict = {
                "probable_template": hint_obj.probable_template,
                "probable_generator": hint_obj.probable_generator,
            }

        representative = members[0]  # First = most representative

        cluster = ErrorCluster(
            cluster_id=cluster_id,
            pattern=pattern,
            generated_file=gen_file,
            count=len(members),
            services_affected=services_affected,
            error_ids=[m.id for m in members],
            representative_error_id=representative.id,
            codegen_hint=hint_dict,
        )
        clusters.append(cluster)

    return clusters


def _cluster_to_dict(cluster: ErrorCluster) -> dict[str, Any]:
    """Convert an ErrorCluster to a JSON-serializable dict."""
    return {
        "cluster_id": cluster.cluster_id,
        "pattern": cluster.pattern,
        "generated_file": cluster.generated_file,
        "count": cluster.count,
        "services_affected": cluster.services_affected,
        "error_ids": cluster.error_ids,
        "representative_error_id": cluster.representative_error_id,
        "codegen_hint": cluster.codegen_hint,
    }


def _extract_import_chain(traceback_text: str) -> list[str]:
    """Extract the import chain from a collection error traceback.

    Each step shows ``file.py:N → module.path.name (MISSING)``.

    Args:
        traceback_text: Raw traceback text from JUnit XML.

    Returns:
        List of import chain step strings.
    """
    if not traceback_text:
        return []

    chain: list[str] = []
    lines = traceback_text.split("\n")

    for i, line in enumerate(lines):
        stripped = line.strip()
        # Match "file.py:123: in <module>" style lines
        frame_match = re.match(r"^(.+?):(\d+):\s+in\s+(.+)$", stripped)
        if frame_match:
            file_path = frame_match.group(1)
            line_num = frame_match.group(2)
            # Look at the next line for an import statement
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                from_match = re.match(
                    r"(?:from\s+(\S+)\s+import\s+(\S+)|import\s+(\S+))",
                    next_line,
                )
                if from_match:
                    if from_match.group(1):
                        module = from_match.group(1)
                        name = from_match.group(2)
                        chain.append(
                            f"{file_path}:{line_num} → {module}.{name}"
                        )
                    else:
                        module = from_match.group(3)
                        chain.append(
                            f"{file_path}:{line_num} → {module}"
                        )

    # Mark the last step as MISSING if chain is non-empty
    if chain:
        chain[-1] = chain[-1] + " (MISSING)"

    return chain


def _extract_generated_file(traceback_text: str, service_name: str) -> str | None:
    """Extract the generated file path from a traceback.

    Looks for src/{service_package}/ paths in frame lines.

    Args:
        traceback_text: Raw traceback text.
        service_name: Name of the service for pattern matching.

    Returns:
        The generated file path if found, else None.
    """
    if not traceback_text:
        return None

    for match in _FRAME_LINE.finditer(traceback_text):
        file_path = match.group(1).replace("\\", "/")
        if "/src/" in file_path and "test" not in file_path.lower():
            return file_path

    return None


def _extract_generated_file_from_path(test_file_path: str) -> str | None:
    """Extract generated file info from a Jest test file path.

    Args:
        test_file_path: Path to the test file.

    Returns:
        The test file path normalized, or None.
    """
    if not test_file_path:
        return None
    return test_file_path.replace("\\", "/")


def _extract_error_type_from_jest(message: str) -> str:
    """Extract error type from a Jest failure message.

    Args:
        message: The Jest failure message text.

    Returns:
        The extracted error type, or ``TestFailure`` as fallback.
    """
    if not message:
        return "TestFailure"

    first_line = message.split("\n", 1)[0]
    # Jest often has "Error: message" or "TypeError: message"
    colon_pos = first_line.find(": ")
    if colon_pos > 0:
        candidate = first_line[:colon_pos].strip()
        # Must look like an error class
        if candidate.isidentifier() and candidate[0].isupper():
            return candidate

    return "TestFailure"


def _make_detail_filename(
    seq_num: int, item: TestFailure | TestError
) -> str:
    """Generate a filename for a failure/error detail file.

    Format: ``{NNN}-{service}-{error_type}-{short_id}.txt``

    Args:
        seq_num: Sequential number (1-based).
        item: The failure or error item.

    Returns:
        The filename string.
    """
    prefix = f"{seq_num:03d}"

    # Build body parts
    parts: list[str] = [item.service, item.error_type]

    # Add a short identifier from the test ID
    test_short = item.test_id.rsplit("::", 1)[-1] if "::" in item.test_id else item.test_id
    test_short = test_short.rsplit("/", 1)[-1] if "/" in test_short else test_short
    parts.append(test_short)

    body = "-".join(parts)
    # Sanitize: only keep alphanumeric, dash, underscore
    body = re.sub(r"[^a-zA-Z0-9_\-]", "-", body)
    body = re.sub(r"-{2,}", "-", body)
    body = body.strip("-")

    if len(body) > _MAX_FILENAME_BODY_LENGTH:
        body = body[:_MAX_FILENAME_BODY_LENGTH].rstrip("-")

    return f"{prefix}-{body}.txt"
