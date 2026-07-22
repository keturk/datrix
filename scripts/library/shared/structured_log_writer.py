"""Structured test log writer for Datrix test infrastructure.

Post-processes JUnit XML from pytest into agent-friendly structured
test result directories with index.json, summary.txt, and per-failure
detail files.
"""

import hashlib
import json
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_SCHEMA_VERSION = 1
_MAX_FILENAME_BODY_LENGTH = 120

# Pattern to match ANSI escape codes (actual ESC byte and pytest's text encoding)
_ANSI_ESCAPE = re.compile(
    r"\x1b\[[0-9;]*[a-zA-Z]"       # Actual ESC byte + CSI sequence
    r"|\x1b\[\?[0-9;]*[a-zA-Z]"    # Actual ESC byte + private mode
    r"|#x1B\[[0-9;]*[a-zA-Z]"      # pytest XML text-encoded ESC (Windows)
    r"|#x1B\[\?[0-9;]*[a-zA-Z]"    # pytest XML text-encoded private mode
)

# Patterns for normalizing error messages before clustering
_SINGLE_QUOTED = re.compile(r"'[^']*'")
_DOUBLE_QUOTED = re.compile(r'"[^"]*"')
_HEX_ADDRESS = re.compile(r"0x[0-9a-fA-F]+")
_STANDALONE_NUMBER = re.compile(r"\b\d+\b")

# Patterns for parsing traceback frames
# Matches lines like: "path/to/file.py:123: in function_name"
_TRACEBACK_FRAME = re.compile(r"^(.+?):(\d+):\s+in\s+(.+)$", re.MULTILINE)

# Paths that indicate stdlib or third-party code
_EXCLUDED_PATH_PATTERNS = (
    "site-packages",
    "lib/python",
    "lib\\python",
    "Lib\\",
    "Lib/",
    "/usr/lib/",
    "\\usr\\lib\\",
)


@dataclass(frozen=True)
class TestCaseResult:
    """Parsed result for a single test case from JUnit XML."""

    test_id: str
    file: str
    classname: str
    function: str
    duration: float
    outcome: str  # "passed", "failed", "error", "skipped"
    error_type: str | None = None
    error_message: str | None = None
    traceback_text: str | None = None
    system_out: str | None = None
    system_err: str | None = None
    phase: str | None = None  # "parallel" or "serial"


@dataclass(frozen=True)
class SourceLocation:
    """Resolved source location from a traceback."""

    file: str
    line: int

    def __str__(self) -> str:
        return f"{self.file}:{self.line}"


@dataclass(frozen=True)
class FailureDetail:
    """Enriched failure/error detail ready for output."""

    id: int
    test_case: TestCaseResult
    source_location: SourceLocation
    cluster_key: str


@dataclass
class Cluster:
    """A group of failures/errors sharing the same root cause."""

    cluster_id: int
    pattern: str
    source_location: SourceLocation
    member_ids: list[int] = field(default_factory=list)
    representative_id: int = 0


class StructuredLogWriter:
    """Post-processes JUnit XML into structured test result directories.

    Parses JUnit XML output from pytest, clusters failures by error
    signature and source location, and writes structured output files
    for efficient agent consumption.
    """

    def __init__(self, project_name: str, run_dir: Path) -> None:
        """Initialize the structured log writer.

        Args:
            project_name: Name of the project being tested.
            run_dir: Path to the timestamped run directory where output
                files will be written.
        """
        self._project_name = project_name
        self._run_dir = run_dir

    def write(
        self,
        xml_paths: list[Path],
        timestamp: datetime,
        phase_results: dict[str, dict[str, object]] | None = None,
    ) -> Path:
        """Write all structured output files.

        Parses JUnit XML files, clusters failures/errors, and writes
        index.json, summary.txt, and individual detail files.

        Args:
            xml_paths: List of JUnit XML file paths to process.
            timestamp: Timestamp of the test run.
            phase_results: Optional per-phase result dicts with keys like
                ``result``, ``worker_count``, ``items``.

        Returns:
            Path to the written index.json file.
        """
        test_cases = self._parse_xml_files(xml_paths)

        if not test_cases:
            logger.warning(
                "structured_log_writer_no_results project=%s xml_paths=%s",
                self._project_name,
                [str(p) for p in xml_paths],
            )
            self._write_incomplete_index(
                timestamp,
                "No JUnit XML produced — test run may have been "
                "interrupted. See full.log for raw output.",
            )
            return self._run_dir / "index.json"

        # Separate results by outcome
        failures: list[TestCaseResult] = []
        errors: list[TestCaseResult] = []
        passed_count = 0
        skipped_count = 0

        for tc in test_cases:
            if tc.outcome == "failed":
                failures.append(tc)
            elif tc.outcome == "error":
                errors.append(tc)
            elif tc.outcome == "passed":
                passed_count += 1
            elif tc.outcome == "skipped":
                skipped_count += 1

        # Build failure details with source locations and cluster keys
        failure_details = self._build_details(failures, start_id=1)
        error_details = self._build_details(
            errors, start_id=len(failure_details) + 1
        )

        # Cluster failures and errors
        failure_clusters = self._cluster_results(failure_details)
        error_clusters = self._cluster_results(error_details)

        # Compute total duration
        total_duration = sum(tc.duration for tc in test_cases)

        # Build counts
        counts = {
            "passed": passed_count,
            "failed": len(failures),
            "error": len(errors),
            "skipped": skipped_count,
        }

        # Determine overall result
        if len(failures) > 0 or len(errors) > 0:
            result = "FAILED"
        else:
            result = "PASSED"

        # Write individual failure/error files
        failure_file_map = self._write_detail_files(
            failure_details, failure_clusters, "failures"
        )
        error_file_map = self._write_detail_files(
            error_details, error_clusters, "errors"
        )

        # Write index.json
        self._write_index_json(
            timestamp=timestamp,
            result=result,
            counts=counts,
            total_duration=total_duration,
            failure_details=failure_details,
            error_details=error_details,
            failure_clusters=failure_clusters,
            error_clusters=error_clusters,
            failure_file_map=failure_file_map,
            error_file_map=error_file_map,
            phase_results=phase_results,
        )

        # Write summary.txt
        self._write_summary_txt(
            timestamp=timestamp,
            result=result,
            counts=counts,
            total_duration=total_duration,
            failure_details=failure_details,
            error_details=error_details,
            failure_clusters=failure_clusters,
            error_clusters=error_clusters,
        )

        logger.info(
            "structured_log_writer_complete project=%s failures=%d "
            "errors=%d clusters=%d",
            self._project_name,
            len(failures),
            len(errors),
            len(failure_clusters) + len(error_clusters),
        )

        return self._run_dir / "index.json"

    # --- Internal methods ---

    def _build_details(
        self, cases: list[TestCaseResult], start_id: int
    ) -> list[FailureDetail]:
        """Build enriched detail objects for a list of failure/error cases.

        Args:
            cases: Test case results to enrich.
            start_id: Starting ID number for sequential assignment.

        Returns:
            List of FailureDetail objects with source locations and cluster keys.
        """
        details: list[FailureDetail] = []
        for i, tc in enumerate(cases):
            detail_id = start_id + i
            source_loc = self._extract_source_location(
                tc.traceback_text or ""
            )
            cluster_key = self._build_cluster_key(
                tc.error_type or "", tc.error_message or "", source_loc
            )
            details.append(
                FailureDetail(
                    id=detail_id,
                    test_case=tc,
                    source_location=source_loc,
                    cluster_key=cluster_key,
                )
            )
        return details

    def _parse_xml_files(
        self, xml_paths: list[Path]
    ) -> list[TestCaseResult]:
        """Parse multiple JUnit XML files and merge results.

        Filters to existing, non-empty files. Catches ParseError on each
        file individually so one corrupt file doesn't prevent processing
        the other.

        Args:
            xml_paths: Paths to JUnit XML files.

        Returns:
            Merged list of test case results, deduplicated by test_id.
        """
        all_results: dict[str, TestCaseResult] = {}

        for xml_path in xml_paths:
            if not xml_path.exists():
                logger.warning(
                    "structured_log_writer_xml_missing path=%s", xml_path
                )
                continue

            if xml_path.stat().st_size == 0:
                logger.warning(
                    "structured_log_writer_xml_empty path=%s", xml_path
                )
                continue

            phase = self._detect_phase(xml_path)
            try:
                cases = self._parse_single_xml(xml_path, phase)
                for tc in cases:
                    # Deduplicate: keep the later-phase result
                    all_results[tc.test_id] = tc
            except ET.ParseError as exc:
                logger.warning(
                    "structured_log_writer_xml_corrupt path=%s error=%s",
                    xml_path,
                    exc,
                )

        return list(all_results.values())

    def _detect_phase(self, xml_path: Path) -> str | None:
        """Detect the test phase from the XML filename.

        Args:
            xml_path: Path to the JUnit XML file.

        Returns:
            Phase name ("parallel" or "serial") or None if not detectable.
        """
        name_lower = xml_path.stem.lower()
        if "parallel" in name_lower:
            return "parallel"
        if "serial" in name_lower:
            return "serial"
        return None

    def _parse_single_xml(
        self, xml_path: Path, phase: str | None
    ) -> list[TestCaseResult]:
        """Parse a single JUnit XML file into test case results.

        Args:
            xml_path: Path to the JUnit XML file.
            phase: Phase name to assign to results, or None.

        Returns:
            List of TestCaseResult objects parsed from the XML.

        Raises:
            xml.etree.ElementTree.ParseError: If the XML is malformed.
        """
        tree = ET.parse(xml_path)  # noqa: S314
        root = tree.getroot()

        results: list[TestCaseResult] = []

        # Handle both <testsuites><testsuite>... and <testsuite>... roots
        if root.tag == "testsuites":
            suites = list(root.iter("testsuite"))
        elif root.tag == "testsuite":
            suites = [root]
        else:
            logger.warning(
                "structured_log_writer_unexpected_root tag=%s path=%s",
                root.tag,
                xml_path,
            )
            return results

        for suite in suites:
            # Detect phase from suite name if not already set
            effective_phase = phase
            suite_name = suite.get("name", "")
            if effective_phase is None and suite_name:
                if "parallel" in suite_name.lower():
                    effective_phase = "parallel"
                elif "serial" in suite_name.lower():
                    effective_phase = "serial"

            for testcase in suite.findall("testcase"):
                tc_result = self._parse_testcase_element(
                    testcase, effective_phase
                )
                results.append(tc_result)

        return results

    def _parse_testcase_element(
        self, testcase: ET.Element, phase: str | None
    ) -> TestCaseResult:
        """Parse a single <testcase> XML element.

        Args:
            testcase: The XML element to parse.
            phase: Phase name to assign.

        Returns:
            A TestCaseResult parsed from the element.
        """
        classname = testcase.get("classname", "")
        name = testcase.get("name", "")
        duration_str = testcase.get("time", "0")

        try:
            duration = float(duration_str)
        except ValueError:
            duration = 0.0

        # Build test ID: classname::name
        test_id = f"{classname}::{name}" if classname else name

        # Convert classname dots to path: tests.test_foo.TestBar -> tests/test_foo.py
        file_path = self._classname_to_filepath(classname)

        # Determine outcome
        failure_el = testcase.find("failure")
        error_el = testcase.find("error")
        skipped_el = testcase.find("skipped")

        if failure_el is not None:
            outcome = "failed"
            error_type = failure_el.get("type", "")
            error_message = _ANSI_ESCAPE.sub("", failure_el.get("message", ""))
            traceback_text = _ANSI_ESCAPE.sub("", failure_el.text or "")
            # Extract error_type from message when XML attribute is empty
            if not error_type and error_message:
                error_type = self._extract_error_type_from_message(
                    error_message
                )
        elif error_el is not None:
            outcome = "error"
            error_type = error_el.get("type", "")
            error_message = _ANSI_ESCAPE.sub("", error_el.get("message", ""))
            traceback_text = _ANSI_ESCAPE.sub("", error_el.text or "")
            # Extract error_type from message when XML attribute is empty
            if not error_type and error_message:
                error_type = self._extract_error_type_from_message(
                    error_message
                )
        elif skipped_el is not None:
            outcome = "skipped"
            error_type = None
            error_message = None
            traceback_text = None
        else:
            outcome = "passed"
            error_type = None
            error_message = None
            traceback_text = None

        # Extract system-out and system-err
        sysout_el = testcase.find("system-out")
        syserr_el = testcase.find("system-err")
        system_out = sysout_el.text if sysout_el is not None else None
        system_err = syserr_el.text if syserr_el is not None else None

        return TestCaseResult(
            test_id=test_id,
            file=file_path,
            classname=classname,
            function=name,
            duration=duration,
            outcome=outcome,
            error_type=error_type,
            error_message=error_message,
            traceback_text=traceback_text,
            system_out=system_out,
            system_err=system_err,
            phase=phase,
        )

    def _classname_to_filepath(self, classname: str) -> str:
        """Convert a JUnit classname to a file path.

        The classname attribute typically contains the module path, e.g.
        ``tests.test_foo.TestBar``. This converts dots to ``/`` for all
        module-level parts and appends ``.py``.

        Args:
            classname: The JUnit classname attribute value.

        Returns:
            A forward-slash file path string.
        """
        if not classname:
            return "unknown"

        parts = classname.split(".")
        # Find where the module path ends and class name begins.
        # Class names start with an uppercase letter.
        module_parts: list[str] = []
        for part in parts:
            if part and part[0].isupper():
                break
            module_parts.append(part)

        if not module_parts:
            return "unknown"

        return "/".join(module_parts) + ".py"

    def _extract_error_type_from_message(
        self, error_message: str
    ) -> str:
        """Extract error type from the error message prefix.

        Many JUnit XML outputs from pytest encode the error type at the
        start of the message (e.g. ``ValueError: some message``). This
        extracts that prefix when the XML ``type`` attribute is empty.

        Args:
            error_message: The error message text.

        Returns:
            The extracted error type, or empty string if not detectable.
        """
        # Match patterns like "ErrorType: message" at the start
        # Only match if the prefix looks like a Python exception class
        first_line = error_message.split("\n", 1)[0]
        colon_pos = first_line.find(": ")
        if colon_pos > 0:
            candidate = first_line[:colon_pos]
            # Must look like a class name (PascalCase or contains "Error"/"Exception")
            if (
                candidate[0].isupper()
                and candidate.isidentifier()
            ):
                return candidate
        # Handle bare "AssertionError" without a colon message
        if first_line.strip().isidentifier() and first_line[0].isupper():
            return first_line.strip()
        return ""

    def _extract_source_location(
        self, traceback_text: str
    ) -> SourceLocation:
        """Extract the most relevant source location from a traceback.

        Follows the fallback chain:
        project source frame -> test frame -> any non-stdlib frame -> unknown:0

        Args:
            traceback_text: Raw traceback text from JUnit XML.

        Returns:
            The resolved SourceLocation.
        """
        if not traceback_text:
            return SourceLocation("unknown", 0)

        frames = _TRACEBACK_FRAME.findall(traceback_text)
        if not frames:
            return SourceLocation("unknown", 0)

        # Walk bottom-up to find the best frame
        project_frame: SourceLocation | None = None
        test_frame: SourceLocation | None = None
        non_stdlib_frame: SourceLocation | None = None

        for file_path, line_str, _func in reversed(frames):
            file_path_normalized = file_path.replace("\\", "/")

            try:
                line_num = int(line_str)
            except ValueError:
                continue

            # Skip stdlib/site-packages
            if self._is_excluded_path(file_path_normalized):
                continue

            loc = SourceLocation(file_path_normalized, line_num)

            # Track the first non-stdlib frame we find (walking bottom-up)
            if non_stdlib_frame is None:
                non_stdlib_frame = loc

            # Check if it's a test frame
            if self._is_test_path(file_path_normalized):
                if test_frame is None:
                    test_frame = loc
                continue

            # It's a project source frame
            if project_frame is None:
                project_frame = loc

        # Apply fallback chain
        if project_frame is not None:
            return project_frame
        if test_frame is not None:
            return test_frame
        if non_stdlib_frame is not None:
            return non_stdlib_frame

        return SourceLocation("unknown", 0)

    def _is_excluded_path(self, path: str) -> bool:
        """Check if a path belongs to stdlib or third-party packages.

        Args:
            path: Normalized (forward-slash) file path.

        Returns:
            True if the path should be excluded from source location selection.
        """
        for pattern in _EXCLUDED_PATH_PATTERNS:
            if pattern in path:
                return True
        return False

    def _is_test_path(self, path: str) -> bool:
        """Check if a path is a test file.

        Args:
            path: Normalized (forward-slash) file path.

        Returns:
            True if the path appears to be a test file or conftest.
        """
        return "tests/" in path or "test_" in path or "conftest" in path

    def _normalize_error_message(
        self, error_type: str, error_message: str
    ) -> str:
        """Normalize an error message for clustering.

        Replaces quoted strings, hex addresses, and standalone numbers
        with ``*`` to group similar errors together. Strips ANSI escape
        codes and avoids duplicating the error_type prefix.

        Args:
            error_type: The exception type name.
            error_message: The raw error message text.

        Returns:
            Normalized pattern string like ``ErrorType: normalized message``.
        """
        # Strip any remaining ANSI codes before normalizing
        normalized = _ANSI_ESCAPE.sub("", error_message)
        # Strip the error_type prefix if the message already starts with it
        if error_type and normalized.startswith(f"{error_type}: "):
            normalized = normalized[len(error_type) + 2:]
        elif error_type and normalized.startswith(f"{error_type}:"):
            normalized = normalized[len(error_type) + 1:]
        # Use only the first line for clustering to avoid multiline noise
        first_line = normalized.split("\n", 1)[0]
        first_line = _SINGLE_QUOTED.sub("*", first_line)
        first_line = _DOUBLE_QUOTED.sub("*", first_line)
        first_line = _HEX_ADDRESS.sub("*", first_line)
        first_line = _STANDALONE_NUMBER.sub("*", first_line)
        return f"{error_type}: {first_line}"

    def _build_cluster_key(
        self,
        error_type: str,
        error_message: str,
        source_location: SourceLocation,
    ) -> str:
        """Build a cluster key from error signature and source location.

        Args:
            error_type: The exception type name.
            error_message: The raw error message text.
            source_location: The resolved source location.

        Returns:
            A cluster key string.
        """
        pattern = self._normalize_error_message(error_type, error_message)
        return f"{pattern} @ {source_location}"

    def _cluster_results(
        self, details: list[FailureDetail]
    ) -> list[Cluster]:
        """Cluster failure/error details by their cluster key.

        Groups details sharing the same cluster key, sorts clusters by
        count descending, and selects the representative as the member
        with the alphabetically first test_id.

        Args:
            details: List of FailureDetail objects to cluster.

        Returns:
            List of Cluster objects sorted by count descending.
        """
        if not details:
            return []

        # Group by cluster key
        groups: dict[str, list[FailureDetail]] = {}
        for detail in details:
            if detail.cluster_key not in groups:
                groups[detail.cluster_key] = []
            groups[detail.cluster_key].append(detail)

        # Build clusters
        clusters: list[Cluster] = []
        for cluster_id, (key, members) in enumerate(
            sorted(
                groups.items(),
                key=lambda item: len(item[1]),
                reverse=True,
            ),
            start=1,
        ):
            # Representative = first by alphabetical test_id
            representative = min(
                members, key=lambda d: d.test_case.test_id
            )

            # Extract pattern and source location from the key
            # The key format is: "ErrorType: message @ file:line"
            cluster = Cluster(
                cluster_id=cluster_id,
                pattern=self._normalize_error_message(
                    representative.test_case.error_type or "",
                    representative.test_case.error_message or "",
                ),
                source_location=representative.source_location,
                member_ids=[d.id for d in members],
                representative_id=representative.id,
            )
            clusters.append(cluster)

        return clusters

    def _make_filename(
        self, seq_num: int, test_case: TestCaseResult
    ) -> str:
        """Generate a filename for a failure/error detail file.

        The filename body is capped at _MAX_FILENAME_BODY_LENGTH chars.
        If truncation is needed, cuts at the nearest ``-`` or ``_``
        boundary and appends an 8-char SHA-256 hash suffix.

        Args:
            seq_num: Sequential number for ordering.
            test_case: The test case to generate a filename for.

        Returns:
            The filename string (e.g. ``001-module-Class-function.txt``).
        """
        prefix = f"{seq_num:03d}-"

        # Build body from classname parts and function name
        parts: list[str] = []
        if test_case.classname:
            classname_parts = test_case.classname.split(".")
            # Take the last 2-3 meaningful parts
            for part in classname_parts:
                parts.append(part.replace("::", "-"))
        if test_case.function:
            parts.append(test_case.function.replace("::", "-"))

        body = "-".join(parts)
        # Sanitize: only keep alphanumeric, dash, underscore
        body = re.sub(r"[^a-zA-Z0-9_\-]", "-", body)
        # Collapse multiple dashes
        body = re.sub(r"-{2,}", "-", body)
        body = body.strip("-")

        if len(body) > _MAX_FILENAME_BODY_LENGTH:
            # Truncate at nearest word boundary
            truncated = body[:_MAX_FILENAME_BODY_LENGTH]
            # Find last separator
            last_sep = max(
                truncated.rfind("-"), truncated.rfind("_")
            )
            if last_sep > _MAX_FILENAME_BODY_LENGTH // 2:
                truncated = truncated[:last_sep]

            # Append hash for uniqueness
            hash_suffix = hashlib.sha256(
                test_case.test_id.encode("utf-8")
            ).hexdigest()[:8]
            body = f"{truncated}-{hash_suffix}"

        return f"{prefix}{body}.txt"

    def _write_detail_files(
        self,
        details: list[FailureDetail],
        clusters: list[Cluster],
        subdir_name: str,
    ) -> dict[int, str]:
        """Write individual failure/error detail files.

        Args:
            details: List of FailureDetail objects to write.
            clusters: Cluster objects for cross-referencing.
            subdir_name: Subdirectory name ("failures" or "errors").

        Returns:
            Mapping from detail ID to relative file path (using forward slashes).
        """
        if not details:
            return {}

        # Build cluster lookup: detail_id -> cluster
        id_to_cluster: dict[int, Cluster] = {}
        for cluster in clusters:
            for member_id in cluster.member_ids:
                id_to_cluster[member_id] = cluster

        subdir = self._run_dir / subdir_name
        subdir.mkdir(parents=True, exist_ok=True)

        file_map: dict[int, str] = {}

        for seq, detail in enumerate(details, start=1):
            filename = self._make_filename(seq, detail.test_case)
            file_path = subdir / filename
            cluster = id_to_cluster[detail.id]

            self._write_failure_file(detail, cluster, file_path)
            # Use forward slashes for cross-platform consistency
            relative = f"{subdir_name}/{filename}"
            file_map[detail.id] = relative

        return file_map

    def _write_failure_file(
        self,
        detail: FailureDetail,
        cluster: Cluster,
        file_path: Path,
    ) -> None:
        """Write a single failure/error detail file.

        Args:
            detail: The failure/error detail to write.
            cluster: The cluster this detail belongs to.
            file_path: Path to write the file to.
        """
        lines: list[str] = []
        lines.append(f"TEST: {detail.test_case.test_id}")
        lines.append(f"CLUSTER: {cluster.pattern} @ {cluster.source_location}")
        error_type = detail.test_case.error_type or "Unknown"
        error_msg = detail.test_case.error_message or ""
        # Strip error_type prefix from message to avoid duplication
        if error_type and error_msg.startswith(f"{error_type}: "):
            error_msg_display = error_msg
        elif error_type and not error_msg.startswith(error_type):
            error_msg_display = f"{error_type}: {error_msg}"
        else:
            error_msg_display = error_msg
        lines.append(f"ERROR: {error_msg_display}")
        lines.append("")

        if detail.test_case.traceback_text:
            lines.append("--- Traceback ---")
            lines.append(detail.test_case.traceback_text.rstrip())
            lines.append("")

        if detail.test_case.system_out:
            lines.append("--- Captured stdout ---")
            lines.append(detail.test_case.system_out.rstrip())
            lines.append("")

        if detail.test_case.system_err:
            lines.append("--- Captured stderr ---")
            lines.append(detail.test_case.system_err.rstrip())
            lines.append("")

        file_path.write_text("\n".join(lines), encoding="utf-8")

    def _write_index_json(
        self,
        timestamp: datetime,
        result: str,
        counts: dict[str, int],
        total_duration: float,
        failure_details: list[FailureDetail],
        error_details: list[FailureDetail],
        failure_clusters: list[Cluster],
        error_clusters: list[Cluster],
        failure_file_map: dict[int, str],
        error_file_map: dict[int, str],
        phase_results: dict[str, dict[str, object]] | None,
    ) -> None:
        """Write the index.json file.

        Args:
            timestamp: Run timestamp.
            result: Overall result string ("PASSED", "FAILED").
            counts: Dict of test outcome counts.
            total_duration: Total test duration in seconds.
            failure_details: Enriched failure details.
            error_details: Enriched error details.
            failure_clusters: Failure clusters.
            error_clusters: Error clusters.
            failure_file_map: Mapping from failure ID to relative file path.
            error_file_map: Mapping from error ID to relative file path.
            phase_results: Optional per-phase result dicts.
        """
        # Build failures array
        failures_json: list[dict[str, object]] = []
        for detail in failure_details:
            entry: dict[str, object] = {
                "id": detail.id,
                "test_id": detail.test_case.test_id,
                "file": detail.test_case.file,
                "class": detail.test_case.classname,
                "function": detail.test_case.function,
                "error_type": detail.test_case.error_type or "",
                "error_message": detail.test_case.error_message or "",
                "source_location": str(detail.source_location),
                "log_file": failure_file_map[detail.id],
            }
            failures_json.append(entry)

        # Build errors array
        errors_json: list[dict[str, object]] = []
        for detail in error_details:
            entry = {
                "id": detail.id,
                "test_id": detail.test_case.test_id,
                "file": detail.test_case.file,
                "class": detail.test_case.classname,
                "function": detail.test_case.function,
                "error_type": detail.test_case.error_type or "",
                "error_message": detail.test_case.error_message or "",
                "source_location": str(detail.source_location),
                "log_file": error_file_map[detail.id],
            }
            errors_json.append(entry)

        # Build failure_clusters array
        failure_clusters_json: list[dict[str, object]] = []
        for cluster in failure_clusters:
            cluster_entry: dict[str, object] = {
                "cluster_id": cluster.cluster_id,
                "pattern": cluster.pattern,
                "source_location": str(cluster.source_location),
                "count": len(cluster.member_ids),
                "failure_ids": cluster.member_ids,
                "representative_failure_id": cluster.representative_id,
            }
            failure_clusters_json.append(cluster_entry)

        # Build error_clusters array
        error_clusters_json: list[dict[str, object]] = []
        for cluster in error_clusters:
            cluster_entry = {
                "cluster_id": cluster.cluster_id,
                "pattern": cluster.pattern,
                "source_location": str(cluster.source_location),
                "count": len(cluster.member_ids),
                "error_ids": cluster.member_ids,
                "representative_error_id": cluster.representative_id,
            }
            error_clusters_json.append(cluster_entry)

        index: dict[str, object] = {
            "schema_version": _SCHEMA_VERSION,
            "project": self._project_name,
            "timestamp": timestamp.strftime("%Y-%m-%dT%H:%M:%S"),
            "duration_seconds": round(total_duration, 2),
            "result": result,
            "counts": counts,
            "failures": failures_json,
            "errors": errors_json,
            "failure_clusters": failure_clusters_json,
            "error_clusters": error_clusters_json,
        }

        if phase_results is not None:
            index["phases"] = phase_results

        index_path = self._run_dir / "index.json"
        index_path.write_text(
            json.dumps(index, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def _write_summary_txt(
        self,
        timestamp: datetime,
        result: str,
        counts: dict[str, int],
        total_duration: float,
        failure_details: list[FailureDetail],
        error_details: list[FailureDetail],
        failure_clusters: list[Cluster],
        error_clusters: list[Cluster],
    ) -> None:
        """Write the summary.txt file (human-readable, under 50 lines).

        Args:
            timestamp: Run timestamp.
            result: Overall result string.
            counts: Dict of test outcome counts.
            total_duration: Total duration in seconds.
            failure_details: Enriched failure details.
            error_details: Enriched error details.
            failure_clusters: Failure clusters.
            error_clusters: Error clusters.
        """
        lines: list[str] = []
        lines.append(f"{self._project_name} test results")
        lines.append(
            f"{timestamp.strftime('%Y-%m-%d %H:%M:%S')} | "
            f"Duration: {total_duration:.2f}s"
        )
        lines.append("")

        # Result line
        total_failed = counts["failed"] + counts["error"]
        if total_failed > 0:
            lines.append(
                f"RESULT: {result} "
                f"({counts['failed']} failed, {counts['error']} errors, "
                f"{counts['passed']} passed)"
            )
        else:
            lines.append(
                f"RESULT: {result} ({counts['passed']} passed)"
            )
        lines.append("")

        # Failure clusters
        if failure_clusters:
            lines.append("FAILURE CLUSTERS:")
            for cluster in failure_clusters:
                rep = self._find_detail_by_id(
                    failure_details, cluster.representative_id
                )
                lines.append(
                    f"  [{len(cluster.member_ids)} failures] "
                    f"{cluster.pattern}"
                )
                lines.append(
                    f"    Source: {cluster.source_location}"
                )
                if rep is not None:
                    lines.append(
                        f"    Example: {rep.test_case.test_id}"
                    )
                lines.append("")

        # Error clusters
        if error_clusters:
            lines.append("ERROR CLUSTERS:")
            for cluster in error_clusters:
                rep = self._find_detail_by_id(
                    error_details, cluster.representative_id
                )
                lines.append(
                    f"  [{len(cluster.member_ids)} errors] "
                    f"{cluster.pattern}"
                )
                lines.append(
                    f"    Source: {cluster.source_location}"
                )
                if rep is not None:
                    lines.append(
                        f"    Example: {rep.test_case.test_id}"
                    )
                lines.append("")

        # List all failed tests
        all_failed = failure_details + error_details
        if all_failed:
            lines.append("ALL FAILED TESTS:")
            for i, detail in enumerate(all_failed, start=1):
                lines.append(
                    f"  {i:03d}  {detail.test_case.test_id}"
                )

        summary_path = self._run_dir / "summary.txt"
        summary_path.write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )

    def _find_detail_by_id(
        self,
        details: list[FailureDetail],
        detail_id: int,
    ) -> FailureDetail | None:
        """Find a FailureDetail by its ID.

        Args:
            details: List of details to search.
            detail_id: The ID to find.

        Returns:
            The matching FailureDetail, or None if not found.
        """
        for detail in details:
            if detail.id == detail_id:
                return detail
        return None

    def _write_incomplete_index(
        self, timestamp: datetime, note: str
    ) -> None:
        """Write a minimal index.json for incomplete/missing results.

        Args:
            timestamp: Run timestamp.
            note: Explanatory note about why data is unavailable.
        """
        index: dict[str, object] = {
            "schema_version": _SCHEMA_VERSION,
            "project": self._project_name,
            "timestamp": timestamp.strftime("%Y-%m-%dT%H:%M:%S"),
            "result": "INCOMPLETE",
            "note": note,
            "counts": None,
            "failures": [],
            "errors": [],
            "failure_clusters": [],
            "error_clusters": [],
        }

        index_path = self._run_dir / "index.json"
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(
            json.dumps(index, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
