"""Deploy test structured log writer for Datrix test infrastructure.

Post-processes deploy test output (failures.json, JUnit XML, Jest JSON,
Docker container logs, deploy-test-output.log) into agent-friendly
structured directories with index.json, summary.txt, and per-failure/error
detail files.
"""

import json
import logging
import re
import shutil
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from .structured_log_writer import (
    _ANSI_ESCAPE,
    _DOUBLE_QUOTED,
    _HEX_ADDRESS,
    _MAX_FILENAME_BODY_LENGTH,
    _SCHEMA_VERSION,
    _SINGLE_QUOTED,
    _STANDALONE_NUMBER,
)

logger = logging.getLogger(__name__)


# --- Deploy test phases (ordered) ---

DEPLOY_PHASES: list[str] = [
    "docker-build",
    "docker-up",
    "health-check",
    "db-connectivity",
    "spec-tests",
    "integration-tests",
]

# Docker lifecycle phases that must run before any test phase. When every one
# of these is SKIPPED, the Docker lifecycle never executed (e.g. the engine was
# unavailable or the build failed before any artifact was written) — a failure,
# not a pass.
_INFRA_PHASES: list[str] = [
    "docker-build",
    "docker-up",
    "health-check",
    "db-connectivity",
]


# --- Transient error patterns ---
# Canonical source. The deploy_test.py template duplicates these
# (see deploy_test.py.j2 lines ~206-223). Keep in sync.

TRANSIENT_ERROR_PATTERNS: list[str] = [
    "connection was closed in the middle of operation",
    "ConnectionDoesNotExistError",
    "WinError 64",
    "ConnectionResetError",
    "ConnectionRefusedError",
    "BrokenPipeError",
    "timeout",
    "timed out",
    "no such container",
    "container is not running",
    "network error",
    "OSError",
    "PermissionError",
    "RemoteDisconnected",
    "ConnectionError",
    "cannot schedule new futures after shutdown",
]

# Docker log error patterns for excerpting
_DOCKER_ERROR_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)\b(ERROR|FATAL|CRITICAL|panic|FAIL)\b"),
    re.compile(r"(?i)traceback|exception|error:"),
    re.compile(r"exit\s+code\s+[1-9]"),
]

_DOCKER_EXCERPT_CONTEXT_LINES = 3
_DOCKER_EXCERPT_TAIL_LINES = 50

# Phase detection patterns from deploy-test-output.log
# Must match BOTH the structured markers emitted by deploy_test.py
# (e.g. docker_build_started) AND any legacy human-readable headers
# (e.g. === Docker Build ===).
_PHASE_MARKERS: dict[str, re.Pattern[str]] = {
    "docker-build": re.compile(
        r"(?i)=== Docker Build ===|Building services|docker\.compose\.build"
        r"|docker_build_started|docker_build output:|docker_build_failed"
    ),
    "docker-up": re.compile(
        r"(?i)=== Docker Up ===|Starting services|docker\.compose\.up"
        r"|docker_up_started|docker_up output:|docker_up_retry"
    ),
    "health-check": re.compile(
        r"(?i)=== Health Check ===|health\.check|waiting for services"
        r"|docker_container_health_check_started|service_waiting"
    ),
    "db-connectivity": re.compile(
        r"(?i)=== DB Connectivity ===|database\.connectivity|db\.connect"
        r"|database_connectivity_validation_started"
    ),
    "spec-tests": re.compile(
        r"(?i)=== Spec Tests ===|spec\.tests|running spec"
        r"|spec_tests_phase_started"
    ),
    "integration-tests": re.compile(
        r"(?i)=== Integration Tests ===|integration\.tests|running integration"
        r"|integration_tests_phase_started|jest_tests_started"
    ),
}

_PHASE_FAILURE_PATTERNS: dict[str, re.Pattern[str]] = {
    "docker-build": re.compile(
        r"(?i)build.failed|ERROR.*build|failed to build"
        r"|docker_build_failed"
    ),
    "docker-up": re.compile(
        r"(?i)docker_up_failed|unhealthy|failed to start|"
        r"dependency failed|container.*is unhealthy"
    ),
    "health-check": re.compile(
        r"(?i)health.check.*fail|health.check.*timeout|"
        r"not responding|connection refused|"
        r"docker_container_health_check_failed|service_health_timeout"
    ),
    "db-connectivity": re.compile(
        r"(?i)db.connectivity.*fail|database.*unreachable|"
        r"cannot connect to.*database|"
        r"database_connectivity_validation_failed|"
        r"database_connectivity_check_failed"
    ),
    "spec-tests": re.compile(
        r"(?i)spec.*failed|spec.*error|spec_tests_phase_failed"
    ),
    "integration-tests": re.compile(
        r"(?i)integration.*failed|integration.*error|"
        r"jest_tests_failed"
    ),
}

# Duration extraction from deploy log
_DURATION_PATTERN = re.compile(
    r"(?:duration|took|elapsed)[=:\s]+(\d+\.?\d*)\s*s", re.IGNORECASE
)


@dataclass(frozen=True)
class PhaseResult:
    """Result for a single deploy test phase."""

    result: str  # "PASSED", "FAILED", "SKIPPED"
    duration_seconds: float = 0.0
    error_message: Optional[str] = None
    relevant_containers: list[str] = field(default_factory=list)
    counts: Optional[dict[str, int]] = None  # For test phases


@dataclass(frozen=True)
class ServiceStatus:
    """Status of a single service in the deploy test."""

    name: str
    port: int
    docker_healthy: bool
    health_check_passed: bool
    db_connectivity_passed: bool
    spec_result: str  # "PASSED", "FAILED", "SKIPPED"
    integration_result: str  # "PASSED", "FAILED", "SKIPPED"
    counts: dict[str, int] = field(
        default_factory=lambda: {
            "passed": 0,
            "failed": 0,
            "errors": 0,
            "skipped": 0,
        }
    )


@dataclass(frozen=True)
class DeployFailure:
    """A test-level failure from spec or integration tests."""

    id: int
    service: str
    phase: str  # "spec-tests" or "integration-tests"
    test_id: str
    test_file: str
    line: int
    error_type: str
    error_message: str
    failure_type: str  # "logic" or "transient"
    traceback_text: str
    generated_file: Optional[str]
    codegen_hint: Optional[dict[str, str]]


@dataclass(frozen=True)
class DeployError:
    """An infrastructure/lifecycle error from Docker phases."""

    id: int
    phase: str
    error_type: str
    error_message: str
    container: Optional[str]
    docker_log_file: Optional[str]
    generated_file: Optional[str]
    codegen_hint: Optional[dict[str, str]]


@dataclass
class DeployFailureCluster:
    """A group of test failures sharing the same root cause."""

    cluster_id: int
    pattern: str
    phase: str
    failure_type: str
    member_ids: list[int] = field(default_factory=list)
    services_affected: list[str] = field(default_factory=list)
    representative_id: int = 0
    codegen_hint: Optional[dict[str, str]] = None


@dataclass
class DeployErrorCluster:
    """A group of infrastructure errors sharing the same root cause."""

    cluster_id: int
    pattern: str
    phase: str
    member_ids: list[int] = field(default_factory=list)
    services_affected: list[str] = field(default_factory=list)
    representative_id: int = 0
    codegen_hint: Optional[dict[str, str]] = None


class DeployTestLogWriter:
    """Post-processes deploy test output into structured directories.

    Reads existing deploy test artifacts (failures.json, JUnit XML,
    Jest JSON, Docker container logs, deploy-test-output.log) and
    produces structured output: index.json, summary.txt, failures/,
    errors/, and services/ directories.
    """

    def __init__(
        self,
        project_name: str,
        run_dir: Path,
        project_path: Path,
        language: str,
        platform: str,
        example: str,
        dtrx_source: str,
    ) -> None:
        """Initialize the deploy test log writer.

        Args:
            project_name: Display name for the project (e.g. "cache").
            run_dir: Path to the timestamped deploy test results directory
                (e.g. {project}/.test_results/deploy-test-{ts}/).
            project_path: Path to the generated project root.
            language: Language being tested ("python" or "typescript").
            platform: Platform being tested ("docker").
            example: Relative example path (e.g. "02-features/03-infrastructure-blocks/cache").
            dtrx_source: Path to the .dtrx source file.
        """
        self._project_name = project_name
        self._run_dir = run_dir
        self._project_path = project_path
        self._language = language
        self._platform = platform
        self._example = example
        self._dtrx_source = dtrx_source

    def write(self, timestamp: datetime) -> Path:
        """Write all structured output files.

        Returns:
            Path to the written index.json file.
        """
        logger.info(
            "deploy_test_log_writer_start project=%s run_dir=%s",
            self._project_name,
            self._run_dir,
        )

        # Detect phases
        phases = self._detect_phases()

        # Merge test results
        failures, services = self._merge_test_results(phases)

        # Extract infrastructure errors from deploy log
        errors = self._extract_errors_from_deploy_log(phases)

        # Cluster failures and errors
        failure_clusters = self._cluster_failures(failures)
        error_clusters = self._cluster_errors(errors)

        # Determine overall result and failed phase
        result, failed_phase = self._determine_result(phases)

        # Compute total duration
        total_duration = sum(
            p.duration_seconds for p in phases.values()
        )

        # Write output files
        failure_file_map = self._write_failure_files(failures)
        error_file_map = self._write_error_files(errors)
        self._copy_test_artifacts_to_services(services)

        # Write index.json
        self._write_index_json(
            timestamp=timestamp,
            result=result,
            failed_phase=failed_phase,
            total_duration=total_duration,
            phases=phases,
            services=services,
            failures=failures,
            errors=errors,
            failure_clusters=failure_clusters,
            error_clusters=error_clusters,
            failure_file_map=failure_file_map,
            error_file_map=error_file_map,
        )

        # Write summary.txt
        self._write_summary_txt(
            timestamp=timestamp,
            result=result,
            failed_phase=failed_phase,
            total_duration=total_duration,
            phases=phases,
            services=services,
            failures=failures,
            failure_clusters=failure_clusters,
            error_clusters=error_clusters,
        )

        logger.info(
            "deploy_test_log_writer_complete project=%s result=%s "
            "failed_phase=%s failures=%d errors=%d",
            self._project_name,
            result,
            failed_phase,
            len(failures),
            len(errors),
        )

        return self._run_dir / "index.json"

    # --- Phase detection (Q4: hybrid) ---

    def _detect_phases(self) -> dict[str, PhaseResult]:
        """Detect deploy test phase results using hybrid approach.

        Primary signal: file existence (JUnit XML, Jest JSON, failures.json).
        Refinement: pattern parsing from deploy-test-output.log.

        Returns:
            Ordered dict of phase name -> PhaseResult.
        """
        phases = self._detect_phases_from_file_existence()
        phases = self._refine_phases_from_log(phases)
        return phases

    def _detect_phases_from_file_existence(self) -> dict[str, PhaseResult]:
        """Detect phase results based on file existence.

        Returns:
            Dict of phase results based on which test artifacts exist.
        """
        has_junit_xml = bool(list(self._run_dir.glob("pytest-*.xml")))
        has_jest_json = bool(
            list(self._run_dir.glob("jest-*.json"))
            or list(self._run_dir.glob("*/jest-*.json"))
        )
        has_failures_json = (self._run_dir / "failures.json").exists()
        has_test_artifacts = has_junit_xml or has_jest_json

        # If test artifacts exist, Docker lifecycle phases passed
        if has_test_artifacts:
            phases: dict[str, PhaseResult] = {
                "docker-build": PhaseResult(result="PASSED"),
                "docker-up": PhaseResult(result="PASSED"),
                "health-check": PhaseResult(result="PASSED"),
                "db-connectivity": PhaseResult(result="PASSED"),
            }

            # Determine spec/integration status from test artifacts
            has_spec = bool(list(self._run_dir.glob("pytest-spec-*.xml"))) or bool(
                list(self._run_dir.glob("*/jest-spec-*.json"))
            )
            has_integration = bool(
                list(self._run_dir.glob("pytest-integration-*.xml"))
            ) or bool(list(self._run_dir.glob("jest-deploy-*.json")))

            if has_spec:
                phases["spec-tests"] = PhaseResult(result="PASSED")
            else:
                phases["spec-tests"] = PhaseResult(result="SKIPPED")

            if has_integration:
                # Default to PASSED; will refine from failures.json / XML
                phases["integration-tests"] = PhaseResult(result="PASSED")
            else:
                phases["integration-tests"] = PhaseResult(result="SKIPPED")

            # If failures.json has entries, mark the relevant test phase as FAILED
            if has_failures_json:
                try:
                    failures_data = json.loads(
                        (self._run_dir / "failures.json").read_text(
                            encoding="utf-8"
                        )
                    )
                    if failures_data:
                        # Tests failed — mark integration as FAILED (most common)
                        phases["integration-tests"] = PhaseResult(
                            result="FAILED"
                        )
                except (json.JSONDecodeError, OSError) as exc:
                    logger.warning(
                        "deploy_test_log_writer_failures_json_error "
                        "project=%s error=%s",
                        self._project_name,
                        exc,
                    )

            return phases

        # No test artifacts — Docker lifecycle failed somewhere
        # Start with all phases as SKIPPED, refine from log
        return {phase: PhaseResult(result="SKIPPED") for phase in DEPLOY_PHASES}

    def _refine_phases_from_log(
        self,
        phases: dict[str, PhaseResult],
    ) -> dict[str, PhaseResult]:
        """Refine phase results from deploy-test-output.log parsing.

        Args:
            phases: Initial phase results from file existence detection.

        Returns:
            Refined phase results with error messages and durations.
        """
        log_path = self._run_dir / "deploy-test-output.log"
        if not log_path.exists():
            return phases

        try:
            log_content = log_path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning(
                "deploy_test_log_writer_log_read_error project=%s error=%s",
                self._project_name,
                exc,
            )
            return phases

        lines = log_content.splitlines()
        current_phase: Optional[str] = None
        phase_lines: dict[str, list[str]] = {p: [] for p in DEPLOY_PHASES}

        # Track which phases were reached in log
        for line in lines:
            # Detect phase transitions
            for phase_name, marker_pattern in _PHASE_MARKERS.items():
                if marker_pattern.search(line):
                    current_phase = phase_name
                    break
            if current_phase is not None:
                phase_lines[current_phase].append(line)

        # Refine phases from log content
        refined = dict(phases)
        found_failure = False

        for phase_name in DEPLOY_PHASES:
            if found_failure:
                # All phases after a failure are SKIPPED
                refined[phase_name] = PhaseResult(result="SKIPPED")
                continue

            section_lines = phase_lines[phase_name]
            if not section_lines:
                # Phase not mentioned in log — keep existing result
                continue

            # If this phase was initially SKIPPED but appears in log,
            # it was at least attempted
            if refined[phase_name].result == "SKIPPED":
                refined[phase_name] = PhaseResult(result="PASSED")

            # Check for failure patterns in this phase's section
            section_text = "\n".join(section_lines)
            failure_pattern = _PHASE_FAILURE_PATTERNS[phase_name]
            failure_match = failure_pattern.search(section_text)

            if failure_match:
                found_failure = True
                error_message = failure_match.group(0).strip()
                # Extract full error context (the line containing the match)
                for sline in section_lines:
                    if failure_match.group(0) in sline:
                        error_message = sline.strip()
                        break

                # Extract relevant containers for Docker phases
                relevant_containers: list[str] = []
                if phase_name in ("docker-up", "health-check"):
                    container_pattern = re.compile(
                        r"container\s+(\S+)\s+is\s+unhealthy|"
                        r"(\S+)\s+(?:failed|unhealthy|timeout)"
                    )
                    for sline in section_lines:
                        match = container_pattern.search(sline)
                        if match:
                            container = match.group(1) or match.group(2)
                            if container and container not in relevant_containers:
                                relevant_containers.append(container)

                refined[phase_name] = PhaseResult(
                    result="FAILED",
                    error_message=error_message,
                    relevant_containers=relevant_containers,
                )

            # Extract duration if available
            duration_match = _DURATION_PATTERN.search(section_text)
            if duration_match and refined[phase_name].result != "FAILED":
                try:
                    duration = float(duration_match.group(1))
                    refined[phase_name] = PhaseResult(
                        result=refined[phase_name].result,
                        duration_seconds=duration,
                        counts=refined[phase_name].counts,
                    )
                except ValueError:
                    pass

        return refined

    # --- Test result merging ---

    def _parse_failures_json(self) -> list[dict[str, object]]:
        """Parse failures.json if it exists.

        Returns:
            List of failure dicts from failures.json.
        """
        path = self._run_dir / "failures.json"
        if not path.exists():
            return []

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
            return []
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "deploy_test_log_writer_parse_failures_json_error "
                "project=%s error=%s",
                self._project_name,
                exc,
            )
            return []

    def _parse_junit_xml(self) -> list[dict[str, object]]:
        """Parse JUnit XML files for test results.

        Returns:
            List of test result dicts from JUnit XML.
        """
        results: list[dict[str, object]] = []
        xml_files = sorted(self._run_dir.glob("pytest-*.xml"))

        for xml_path in xml_files:
            if xml_path.stat().st_size == 0:
                continue

            try:
                tree = ET.parse(xml_path)  # noqa: S314
                root = tree.getroot()
            except ET.ParseError as exc:
                logger.warning(
                    "deploy_test_log_writer_junit_xml_error "
                    "path=%s error=%s",
                    xml_path,
                    exc,
                )
                continue

            # Determine phase from filename
            stem = xml_path.stem.lower()
            if "spec" in stem:
                phase = "spec-tests"
            elif "integration" in stem:
                phase = "integration-tests"
            else:
                phase = "integration-tests"

            # Extract service name from filename pattern:
            # pytest-spec-{service}.xml or pytest-integration-{service}-project.xml
            service_match = re.search(
                r"pytest-(?:spec|integration)-(.+?)(?:-project|-service)?$",
                xml_path.stem,
            )
            service_name = (
                service_match.group(1) if service_match else "unknown"
            )

            suites = list(root.iter("testsuite"))
            if root.tag == "testsuite":
                suites = [root]

            for suite in suites:
                for testcase in suite.findall("testcase"):
                    failure_el = testcase.find("failure")
                    error_el = testcase.find("error")

                    if failure_el is None and error_el is None:
                        continue

                    el = failure_el if failure_el is not None else error_el
                    assert el is not None  # guaranteed by above check

                    classname = testcase.get("classname", "")
                    name = testcase.get("name", "")
                    test_id = f"{classname}::{name}" if classname else name
                    error_type = el.get("type", "")
                    error_message = _ANSI_ESCAPE.sub(
                        "", el.get("message", "")
                    )
                    traceback_text = _ANSI_ESCAPE.sub("", el.text or "")

                    # Derive file from classname
                    file_path = self._classname_to_filepath(classname)

                    results.append(
                        {
                            "test_id": test_id,
                            "test_file": file_path,
                            "service": service_name,
                            "phase": phase,
                            "error_type": error_type,
                            "error_message": error_message,
                            "traceback_text": traceback_text,
                            "line": self._extract_line_number(
                                traceback_text
                            ),
                        }
                    )

        return results

    def _parse_jest_json(self) -> list[dict[str, object]]:
        """Parse Jest JSON result files for test results.

        Returns:
            List of test result dicts from Jest JSON.
        """
        results: list[dict[str, object]] = []
        jest_files = sorted(self._run_dir.glob("jest-*.json"))
        # Also check subdirectories
        jest_files.extend(sorted(self._run_dir.glob("*/jest-*.json")))

        for jest_path in jest_files:
            if jest_path.stat().st_size == 0:
                continue

            try:
                data = json.loads(jest_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning(
                    "deploy_test_log_writer_jest_json_error "
                    "path=%s error=%s",
                    jest_path,
                    exc,
                )
                continue

            # Determine phase from filename
            stem = jest_path.stem.lower()
            if "spec" in stem:
                phase = "spec-tests"
            else:
                phase = "integration-tests"

            # Extract service from parent dir or filename
            service_name = "unknown"
            if jest_path.parent != self._run_dir:
                service_name = jest_path.parent.name

            test_results = data.get("testResults", [])
            for test_suite in test_results:
                for test_result in test_suite.get("assertionResults", []):
                    if test_result.get("status") != "failed":
                        continue

                    test_file = test_suite.get("name", "")
                    full_name = " > ".join(
                        test_result.get("ancestorTitles", [])
                        + [test_result.get("title", "")]
                    )
                    failure_messages = test_result.get("failureMessages", [])
                    error_message = (
                        failure_messages[0] if failure_messages else ""
                    )

                    # Extract error type from first line
                    error_type = self._extract_error_type_from_message(
                        error_message
                    )

                    results.append(
                        {
                            "test_id": f"{test_file}::{full_name}",
                            "test_file": test_file,
                            "service": service_name,
                            "phase": phase,
                            "error_type": error_type,
                            "error_message": error_message,
                            "traceback_text": error_message,
                            "line": self._extract_line_number(error_message),
                        }
                    )

        return results

    def _merge_test_results(
        self, phases: dict[str, PhaseResult]
    ) -> tuple[list[DeployFailure], list[ServiceStatus]]:
        """Merge test results from all sources into unified failures and services.

        Args:
            phases: Detected phase results.

        Returns:
            Tuple of (failures list, services list).
        """
        # Parse all data sources
        failures_json_data = self._parse_failures_json()
        junit_results = self._parse_junit_xml()
        jest_results = self._parse_jest_json()

        # Combine results, preferring JUnit/Jest detail over failures.json
        all_test_results = junit_results + jest_results

        # Build failures list
        failures: list[DeployFailure] = []
        services_map: dict[str, dict[str, object]] = {}

        for idx, result in enumerate(all_test_results, start=1):
            service = str(result["service"])
            error_message = str(result.get("error_message", ""))
            error_type = str(result.get("error_type", ""))
            phase = str(result.get("phase", "integration-tests"))

            # Classify transient vs logic
            failure_type = self._classify_failure(error_message)

            # Also check failures.json classification
            for fj in failures_json_data:
                fj_test = str(fj.get("test", ""))
                if str(result["test_id"]) in fj_test or fj_test in str(
                    result["test_id"]
                ):
                    fj_type = str(fj.get("type", ""))
                    if fj_type in ("transient", "logic"):
                        failure_type = fj_type
                    break

            # Generate codegen hint
            codegen_hint = self._generate_codegen_hint(
                phase=phase,
                error_type=error_type,
                container=None,
            )

            # Determine generated file
            test_file = str(result.get("test_file", ""))
            generated_file: Optional[str] = (
                test_file if failure_type == "logic" else None
            )

            failure = DeployFailure(
                id=idx,
                service=service,
                phase=phase,
                test_id=str(result["test_id"]),
                test_file=test_file,
                line=int(result.get("line", 0)),
                error_type=error_type,
                error_message=error_message,
                failure_type=failure_type,
                traceback_text=str(result.get("traceback_text", "")),
                generated_file=generated_file,
                codegen_hint=codegen_hint if failure_type == "logic" else None,
            )
            failures.append(failure)

            # Track service counts
            if service not in services_map:
                services_map[service] = {
                    "passed": 0,
                    "failed": 0,
                    "errors": 0,
                    "skipped": 0,
                }
            services_map[service]["failed"] = (
                int(services_map[service]["failed"]) + 1
            )

        # If no JUnit/Jest results but failures.json has data, use that
        if not all_test_results and failures_json_data:
            for idx, fj_entry in enumerate(failures_json_data, start=1):
                test_id = str(fj_entry.get("test", ""))
                error_msg = str(fj_entry.get("error", ""))
                fj_type = str(fj_entry.get("type", ""))
                failure_type = fj_type if fj_type in (
                    "transient", "logic"
                ) else self._classify_failure(error_msg)

                # Extract service from test path
                service = self._extract_service_from_test_id(test_id)
                error_type = self._extract_error_type_from_message(error_msg)

                codegen_hint = self._generate_codegen_hint(
                    phase="integration-tests",
                    error_type=error_type,
                    container=None,
                )

                failure = DeployFailure(
                    id=idx,
                    service=service,
                    phase="integration-tests",
                    test_id=test_id,
                    test_file=test_id.split("::")[0] if "::" in test_id else test_id,
                    line=0,
                    error_type=error_type,
                    error_message=error_msg,
                    failure_type=failure_type,
                    traceback_text=error_msg,
                    generated_file=(
                        test_id.split("::")[0]
                        if failure_type == "logic" and "::" in test_id
                        else None
                    ),
                    codegen_hint=(
                        codegen_hint if failure_type == "logic" else None
                    ),
                )
                failures.append(failure)

                if service not in services_map:
                    services_map[service] = {
                        "passed": 0,
                        "failed": 0,
                        "errors": 0,
                        "skipped": 0,
                    }
                services_map[service]["failed"] = (
                    int(services_map[service]["failed"]) + 1
                )

        # Build ServiceStatus objects
        services: list[ServiceStatus] = []
        for svc_name, counts in sorted(services_map.items()):
            # Determine per-service phase results
            svc_failures = [f for f in failures if f.service == svc_name]
            spec_failures = [
                f for f in svc_failures if f.phase == "spec-tests"
            ]
            integration_failures = [
                f for f in svc_failures if f.phase == "integration-tests"
            ]

            spec_result = "PASSED"
            if phases.get("spec-tests", PhaseResult(result="SKIPPED")).result == "SKIPPED":
                spec_result = "SKIPPED"
            elif spec_failures:
                spec_result = "FAILED"

            integration_result = "PASSED"
            if phases.get("integration-tests", PhaseResult(result="SKIPPED")).result == "SKIPPED":
                integration_result = "SKIPPED"
            elif integration_failures:
                integration_result = "FAILED"

            # Docker health is PASSED if we got past docker-up
            docker_healthy = phases.get(
                "docker-up", PhaseResult(result="SKIPPED")
            ).result == "PASSED"
            health_check_passed = phases.get(
                "health-check", PhaseResult(result="SKIPPED")
            ).result == "PASSED"
            db_passed = phases.get(
                "db-connectivity", PhaseResult(result="SKIPPED")
            ).result == "PASSED"

            services.append(
                ServiceStatus(
                    name=svc_name,
                    port=8000,  # Default; exact port not available from logs
                    docker_healthy=docker_healthy,
                    health_check_passed=health_check_passed,
                    db_connectivity_passed=db_passed,
                    spec_result=spec_result,
                    integration_result=integration_result,
                    counts={
                        "passed": int(counts["passed"]),
                        "failed": int(counts["failed"]),
                        "errors": int(counts["errors"]),
                        "skipped": int(counts["skipped"]),
                    },
                )
            )

        return failures, services

    # --- Docker log excerpting (Q2/Q6: error-grep + tail) ---

    def _excerpt_docker_log(self, log_path: Path) -> str:
        """Extract error-relevant lines from a Docker container log.

        Extracts lines matching error patterns with context, plus the
        last N lines as fallback context.

        Args:
            log_path: Path to the container log file.

        Returns:
            Excerpted log content as a string.
        """
        if not log_path.exists():
            return f"(log file not found: {log_path.name})"

        try:
            lines = log_path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            return f"(error reading log: {exc})"

        if not lines:
            return "(empty log file)"

        # Find error lines with context
        error_line_indices: set[int] = set()
        for i, line in enumerate(lines):
            for pattern in _DOCKER_ERROR_PATTERNS:
                if pattern.search(line):
                    # Add context lines
                    start = max(0, i - _DOCKER_EXCERPT_CONTEXT_LINES)
                    end = min(len(lines), i + _DOCKER_EXCERPT_CONTEXT_LINES + 1)
                    for j in range(start, end):
                        error_line_indices.add(j)
                    break

        # Build excerpt: error-grepped lines first
        excerpt_parts: list[str] = []
        if error_line_indices:
            excerpt_parts.append("--- Error-relevant lines ---")
            sorted_indices = sorted(error_line_indices)
            prev_idx = -2
            for idx in sorted_indices:
                if idx > prev_idx + 1:
                    excerpt_parts.append("...")
                excerpt_parts.append(lines[idx])
                prev_idx = idx

        # Append last N lines as fallback context
        tail_start = max(0, len(lines) - _DOCKER_EXCERPT_TAIL_LINES)
        tail_lines = lines[tail_start:]
        if tail_lines:
            excerpt_parts.append("")
            excerpt_parts.append(
                f"--- Last {len(tail_lines)} lines ---"
            )
            excerpt_parts.extend(tail_lines)

        return "\n".join(excerpt_parts)

    def _extract_errors_from_deploy_log(
        self, phases: dict[str, PhaseResult]
    ) -> list[DeployError]:
        """Extract infrastructure errors from Docker lifecycle phases.

        Args:
            phases: Detected phase results.

        Returns:
            List of DeployError objects for Docker lifecycle failures.
        """
        errors: list[DeployError] = []
        error_id = 1

        for phase_name in (
            "docker-build",
            "docker-up",
            "health-check",
            "db-connectivity",
        ):
            phase = phases.get(phase_name)
            if phase is None or phase.result != "FAILED":
                continue

            error_message = phase.error_message or f"{phase_name} failed"

            # Determine error type from message
            error_type = self._classify_error_type(phase_name, error_message)

            # For each relevant container, create an error entry
            if phase.relevant_containers:
                for container in sorted(phase.relevant_containers):
                    docker_log_file = f"docker-logs/{container}.log"
                    log_path = self._run_dir / "docker-logs" / f"{container}.log"
                    actual_log_file: Optional[str] = (
                        docker_log_file if log_path.exists() else None
                    )

                    codegen_hint = self._generate_codegen_hint(
                        phase=phase_name,
                        error_type=error_type,
                        container=container,
                    )

                    errors.append(
                        DeployError(
                            id=error_id,
                            phase=phase_name,
                            error_type=error_type,
                            error_message=error_message,
                            container=container,
                            docker_log_file=actual_log_file,
                            generated_file=self._get_generated_file_for_phase(
                                phase_name, container
                            ),
                            codegen_hint=codegen_hint,
                        )
                    )
                    error_id += 1
            else:
                # No specific container identified
                codegen_hint = self._generate_codegen_hint(
                    phase=phase_name,
                    error_type=error_type,
                    container=None,
                )

                errors.append(
                    DeployError(
                        id=error_id,
                        phase=phase_name,
                        error_type=error_type,
                        error_message=error_message,
                        container=None,
                        docker_log_file=None,
                        generated_file=self._get_generated_file_for_phase(
                            phase_name, None
                        ),
                        codegen_hint=codegen_hint,
                    )
                )
                error_id += 1

        return errors

    # --- Transient classification (Q1: shared patterns) ---

    def _classify_failure(self, error_message: str) -> str:
        """Classify a test failure as transient or logic.

        Args:
            error_message: The error message text.

        Returns:
            "transient" or "logic".
        """
        error_lower = error_message.lower()
        for pattern in TRANSIENT_ERROR_PATTERNS:
            if pattern.lower() in error_lower:
                return "transient"
        return "logic"

    # --- Clustering ---

    def _cluster_failures(
        self,
        failures: list[DeployFailure],
    ) -> list[DeployFailureCluster]:
        """Cluster test failures by normalized error pattern.

        Args:
            failures: List of deploy failures to cluster.

        Returns:
            List of failure clusters sorted by count descending.
        """
        if not failures:
            return []

        groups: dict[str, list[DeployFailure]] = {}
        for failure in failures:
            key = self._normalize_error_message(
                failure.error_type, failure.error_message
            )
            if key not in groups:
                groups[key] = []
            groups[key].append(failure)

        clusters: list[DeployFailureCluster] = []
        for cluster_id, (pattern, members) in enumerate(
            sorted(
                groups.items(),
                key=lambda item: len(item[1]),
                reverse=True,
            ),
            start=1,
        ):
            services_affected = sorted(
                set(m.service for m in members)
            )
            representative = members[0]

            cluster = DeployFailureCluster(
                cluster_id=cluster_id,
                pattern=pattern,
                phase=representative.phase,
                failure_type=representative.failure_type,
                member_ids=[m.id for m in members],
                services_affected=services_affected,
                representative_id=representative.id,
                codegen_hint=representative.codegen_hint,
            )
            clusters.append(cluster)

        return clusters

    def _cluster_errors(
        self,
        errors: list[DeployError],
    ) -> list[DeployErrorCluster]:
        """Cluster infrastructure errors by normalized error pattern.

        Args:
            errors: List of deploy errors to cluster.

        Returns:
            List of error clusters sorted by count descending.
        """
        if not errors:
            return []

        groups: dict[str, list[DeployError]] = {}
        for error in errors:
            key = self._normalize_error_message(
                error.error_type, error.error_message
            )
            if key not in groups:
                groups[key] = []
            groups[key].append(error)

        clusters: list[DeployErrorCluster] = []
        for cluster_id, (pattern, members) in enumerate(
            sorted(
                groups.items(),
                key=lambda item: len(item[1]),
                reverse=True,
            ),
            start=1,
        ):
            services_affected = sorted(
                set(m.container for m in members if m.container)
            )
            representative = members[0]

            cluster = DeployErrorCluster(
                cluster_id=cluster_id,
                pattern=pattern,
                phase=representative.phase,
                member_ids=[m.id for m in members],
                services_affected=services_affected,
                representative_id=representative.id,
                codegen_hint=representative.codegen_hint,
            )
            clusters.append(cluster)

        return clusters

    def _normalize_error_message(self, error_type: str, message: str) -> str:
        """Normalize an error message for clustering.

        Replaces quoted strings, hex addresses, and standalone numbers
        with * to group similar errors together.

        Args:
            error_type: The exception/error type name.
            message: The raw error message text.

        Returns:
            Normalized pattern string.
        """
        normalized = _ANSI_ESCAPE.sub("", message)
        # Strip the error_type prefix if already present
        if error_type and normalized.startswith(f"{error_type}: "):
            normalized = normalized[len(error_type) + 2:]
        elif error_type and normalized.startswith(f"{error_type}:"):
            normalized = normalized[len(error_type) + 1:]
        # Use only the first line
        first_line = normalized.split("\n", 1)[0]
        first_line = _SINGLE_QUOTED.sub("*", first_line)
        first_line = _DOUBLE_QUOTED.sub("*", first_line)
        first_line = _HEX_ADDRESS.sub("*", first_line)
        first_line = _STANDALONE_NUMBER.sub("*", first_line)
        return f"{error_type}: {first_line}"

    # --- Codegen hints ---

    def _generate_codegen_hint(
        self,
        phase: str,
        error_type: str,
        container: Optional[str],
    ) -> Optional[dict[str, str]]:
        """Generate a best-effort codegen hint for a failure/error.

        Maps phase + error type + container to probable template/generator.

        Args:
            phase: The deploy test phase.
            error_type: The error type classification.
            container: The container name (if applicable).

        Returns:
            Dict with probable_template and probable_generator, or None.
        """
        # Docker lifecycle phases -> Docker generators
        if phase in ("docker-build", "docker-up"):
            return {
                "probable_template": "docker-compose.yml.j2",
                "probable_generator": "DockerComposeGenerator",
            }

        if phase == "health-check":
            if self._language == "python":
                return {
                    "probable_template": "main.py.j2",
                    "probable_generator": "ServiceGenerator",
                }
            return {
                "probable_template": "app.module.ts.j2",
                "probable_generator": "AppModuleGenerator",
            }

        if phase == "db-connectivity":
            if self._language == "python":
                return {
                    "probable_template": "database.py.j2",
                    "probable_generator": "DatabaseConfigGenerator",
                }
            return {
                "probable_template": "database.config.ts.j2",
                "probable_generator": "DatabaseConfigGenerator",
            }

        # Test phases -> test templates
        if phase == "spec-tests":
            if self._language == "python":
                return {
                    "probable_template": "test_service.py.j2",
                    "probable_generator": "SpecTestGenerator",
                }
            return {
                "probable_template": "service.spec.ts.j2",
                "probable_generator": "SpecTestGenerator",
            }

        if phase == "integration-tests":
            if self._language == "python":
                return {
                    "probable_template": "test_service.py.j2",
                    "probable_generator": "IntegrationTestGenerator",
                }
            return {
                "probable_template": "service.e2e-spec.ts.j2",
                "probable_generator": "IntegrationTestGenerator",
            }

        return None

    # --- Output writers ---

    def _write_index_json(
        self,
        timestamp: datetime,
        result: str,
        failed_phase: Optional[str],
        total_duration: float,
        phases: dict[str, PhaseResult],
        services: list[ServiceStatus],
        failures: list[DeployFailure],
        errors: list[DeployError],
        failure_clusters: list[DeployFailureCluster],
        error_clusters: list[DeployErrorCluster],
        failure_file_map: dict[int, str],
        error_file_map: dict[int, str],
    ) -> None:
        """Write the index.json file with full structured data."""
        # Build phases dict
        phases_json: dict[str, dict[str, object]] = {}
        for phase_name, phase_result in phases.items():
            entry: dict[str, object] = {"result": phase_result.result}
            if phase_result.duration_seconds > 0:
                entry["duration_seconds"] = round(
                    phase_result.duration_seconds, 1
                )
            if phase_result.error_message:
                entry["error_message"] = phase_result.error_message
            if phase_result.relevant_containers:
                entry["relevant_containers"] = phase_result.relevant_containers
            if phase_result.counts:
                entry["counts"] = phase_result.counts
            phases_json[phase_name] = entry

        # Build services array
        services_json: list[dict[str, object]] = []
        for svc in services:
            services_json.append(
                {
                    "name": svc.name,
                    "port": svc.port,
                    "docker_healthy": svc.docker_healthy,
                    "health_check_passed": svc.health_check_passed,
                    "db_connectivity_passed": svc.db_connectivity_passed,
                    "spec_result": svc.spec_result,
                    "integration_result": svc.integration_result,
                    "counts": svc.counts,
                }
            )

        # Build failures array
        failures_json: list[dict[str, object]] = []
        for f in failures:
            entry_f: dict[str, object] = {
                "id": f.id,
                "service": f.service,
                "phase": f.phase,
                "test_id": f.test_id,
                "test_file": f.test_file,
                "line": f.line,
                "error_type": f.error_type,
                "error_message": f.error_message,
                "failure_type": f.failure_type,
                "generated_file": f.generated_file,
                "log_file": failure_file_map.get(f.id),
                "codegen_hint": f.codegen_hint,
            }
            failures_json.append(entry_f)

        # Build errors array
        errors_json: list[dict[str, object]] = []
        for e in errors:
            entry_e: dict[str, object] = {
                "id": e.id,
                "phase": e.phase,
                "error_type": e.error_type,
                "error_message": e.error_message,
                "container": e.container,
                "docker_log_file": e.docker_log_file,
                "log_file": error_file_map.get(e.id),
                "generated_file": e.generated_file,
                "codegen_hint": e.codegen_hint,
            }
            errors_json.append(entry_e)

        # Build failure_clusters array
        failure_clusters_json: list[dict[str, object]] = []
        for fc in failure_clusters:
            failure_clusters_json.append(
                {
                    "cluster_id": fc.cluster_id,
                    "pattern": fc.pattern,
                    "phase": fc.phase,
                    "failure_type": fc.failure_type,
                    "count": len(fc.member_ids),
                    "services_affected": fc.services_affected,
                    "failure_ids": fc.member_ids,
                    "representative_failure_id": fc.representative_id,
                    "codegen_hint": fc.codegen_hint,
                }
            )

        # Build error_clusters array
        error_clusters_json: list[dict[str, object]] = []
        for ec in error_clusters:
            error_clusters_json.append(
                {
                    "cluster_id": ec.cluster_id,
                    "pattern": ec.pattern,
                    "phase": ec.phase,
                    "count": len(ec.member_ids),
                    "services_affected": ec.services_affected,
                    "error_ids": ec.member_ids,
                    "representative_error_id": ec.representative_id,
                    "codegen_hint": ec.codegen_hint,
                }
            )

        index: dict[str, object] = {
            "schema_version": _SCHEMA_VERSION,
            "project": self._project_name,
            "project_path": str(self._project_path.resolve()),
            "language": self._language,
            "platform": self._platform,
            "example": self._example,
            "dtrx_source": self._dtrx_source,
            "timestamp": timestamp.strftime("%Y-%m-%dT%H:%M:%S"),
            "duration_seconds": round(total_duration, 1),
            "result": result,
            "failed_phase": failed_phase,
            "phases": phases_json,
            "services": services_json,
            "failures": failures_json,
            "errors": errors_json,
            "failure_clusters": failure_clusters_json,
            "error_clusters": error_clusters_json,
        }

        index_path = self._run_dir / "index.json"
        index_path.write_text(
            json.dumps(index, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def _write_summary_txt(
        self,
        timestamp: datetime,
        result: str,
        failed_phase: Optional[str],
        total_duration: float,
        phases: dict[str, PhaseResult],
        services: list[ServiceStatus],
        failures: list[DeployFailure],
        failure_clusters: list[DeployFailureCluster],
        error_clusters: list[DeployErrorCluster],
    ) -> None:
        """Write summary.txt (human-readable, under 60 lines)."""
        lines: list[str] = []
        lines.append(
            f"{self._project_name} deploy test results ({self._language.title()})"
        )
        lines.append(
            f"{timestamp.strftime('%Y-%m-%d %H:%M:%S')} | "
            f"Duration: {total_duration:.1f}s"
        )
        lines.append("")

        # Result line
        if failed_phase and failed_phase in (
            "spec-tests",
            "integration-tests",
        ):
            test_phase = phases.get(failed_phase)
            counts_str = ""
            if test_phase and test_phase.counts:
                passed = test_phase.counts.get("passed", 0)
                failed_count = test_phase.counts.get("failed", 0)
                counts_str = f" ({passed} passed, {failed_count} failed)"
            lines.append(
                f"RESULT: FAILED at {failed_phase} phase{counts_str}"
            )
        elif failed_phase:
            lines.append(f"RESULT: FAILED at {failed_phase} phase")
        else:
            lines.append(f"RESULT: {result}")

        lines.append("")
        lines.append(
            f".dtrx source: {self._dtrx_source}"
        )
        lines.append("")

        # Phases
        lines.append("PHASES:")
        for phase_name in DEPLOY_PHASES:
            phase = phases.get(phase_name, PhaseResult(result="SKIPPED"))
            if phase.result == "PASSED":
                marker = "\u2713"
                duration_str = (
                    f"  {phase.duration_seconds:.1f}s"
                    if phase.duration_seconds > 0
                    else ""
                )
                extra = ""
                if phase.counts:
                    extra = f"  (all passed)"
                lines.append(
                    f"  {marker} {phase_name:<17}{duration_str}{extra}"
                )
            elif phase.result == "FAILED":
                marker = "\u2717"
                duration_str = (
                    f"  {phase.duration_seconds:.1f}s"
                    if phase.duration_seconds > 0
                    else ""
                )
                error_str = ""
                if phase.error_message:
                    # Truncate long error messages
                    msg = phase.error_message[:80]
                    error_str = f"  \u2192 {msg}"
                elif phase.counts:
                    passed = phase.counts.get("passed", 0)
                    failed_count = phase.counts.get("failed", 0)
                    error_str = (
                        f"  ({passed} passed, {failed_count} failed)"
                    )
                lines.append(
                    f"  {marker} {phase_name:<17}{duration_str}{error_str}"
                )
            else:
                lines.append(f"  - {phase_name:<17}(skipped)")
        lines.append("")

        # Errors (infrastructure)
        if error_clusters:
            lines.append("ERRORS:")
            for ec in error_clusters:
                container_str = ""
                if ec.services_affected:
                    container_str = (
                        f" ({', '.join(ec.services_affected)})"
                    )
                lines.append(
                    f"  [{ec.phase}] {ec.pattern}{container_str}"
                )
                if ec.codegen_hint:
                    lines.append(
                        f"    Probable template: "
                        f"{ec.codegen_hint['probable_template']}"
                    )
            lines.append("")

        # Failure clusters
        if failure_clusters:
            lines.append("FAILURE CLUSTERS:")
            for fc in failure_clusters:
                count = len(fc.member_ids)
                lines.append(
                    f"  [{count} {fc.failure_type} failure"
                    f"{'s' if count > 1 else ''}] {fc.pattern}"
                )
                if fc.failure_type == "transient":
                    lines.append(
                        "    (transient \u2014 likely infrastructure "
                        "flakiness, not a codegen bug)"
                    )
                elif fc.codegen_hint:
                    lines.append(
                        f"    Probable template: "
                        f"{fc.codegen_hint['probable_template']}"
                    )
            lines.append("")

        # Service status
        if services:
            lines.append("SERVICE STATUS:")
            for svc in services:
                docker_str = (
                    "healthy" if svc.docker_healthy else "unhealthy"
                )
                spec_str = svc.spec_result.lower()
                integ_str = svc.integration_result.lower()
                marker = (
                    "\u2713"
                    if svc.integration_result == "PASSED"
                    and svc.spec_result in ("PASSED", "SKIPPED")
                    else "\u2717"
                )
                parts = [
                    f"port:{svc.port}",
                    f"docker:{docker_str}",
                ]
                if svc.spec_result != "SKIPPED":
                    parts.append(f"spec:{spec_str}")
                if svc.integration_result != "SKIPPED":
                    failed_count = svc.counts.get("failed", 0)
                    if failed_count > 0:
                        parts.append(
                            f"integration:{integ_str} ({failed_count})"
                        )
                    else:
                        parts.append(f"integration:{integ_str}")
                lines.append(
                    f"  {marker} {svc.name}  {'  '.join(parts)}"
                )

        summary_path = self._run_dir / "summary.txt"
        summary_path.write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )

    def _write_failure_files(
        self,
        failures: list[DeployFailure],
    ) -> dict[int, str]:
        """Write individual failure detail files to failures/ directory.

        Args:
            failures: List of deploy failures to write.

        Returns:
            Mapping from failure ID to relative file path.
        """
        if not failures:
            return {}

        failures_dir = self._run_dir / "failures"
        failures_dir.mkdir(parents=True, exist_ok=True)

        file_map: dict[int, str] = {}

        # Sort: by service, then phase, then test name
        sorted_failures = sorted(
            failures,
            key=lambda f: (f.service, f.phase, f.test_id),
        )

        for seq, failure in enumerate(sorted_failures, start=1):
            # Build filename: {NNN}-{service}-{phase}-{error_type}-{test_name}.txt
            test_name = failure.test_id.rsplit("::", 1)[-1] if "::" in failure.test_id else failure.test_id
            body_parts = [
                failure.service,
                failure.phase.split("-")[0],  # "spec" or "integration"
                failure.error_type,
                test_name,
            ]
            body = "-".join(
                re.sub(r"[^a-zA-Z0-9_\-]", "-", p) for p in body_parts
            )
            body = re.sub(r"-{2,}", "-", body).strip("-")
            if len(body) > _MAX_FILENAME_BODY_LENGTH:
                body = body[:_MAX_FILENAME_BODY_LENGTH].rstrip("-")

            filename = f"{seq:03d}-{body}.txt"
            file_path = failures_dir / filename

            # Write failure detail file
            content_lines: list[str] = [
                f"SERVICE: {failure.service}",
                f"PHASE: {failure.phase}",
                f"TEST: {failure.test_id}",
                f"FAILURE TYPE: {failure.failure_type}",
                f"ERROR: {failure.error_type}: {failure.error_message}",
                "",
            ]

            if failure.traceback_text:
                content_lines.append("--- Traceback ---")
                content_lines.append(failure.traceback_text.rstrip())
                content_lines.append("")

            if failure.generated_file:
                content_lines.append("--- Generated File ---")
                content_lines.append(failure.generated_file)
                content_lines.append("")

            if failure.codegen_hint:
                content_lines.append("--- Codegen Hint ---")
                content_lines.append(
                    f"Probable template: "
                    f"{failure.codegen_hint['probable_template']}"
                )
                content_lines.append(
                    f"Probable generator: "
                    f"{failure.codegen_hint['probable_generator']}"
                )
                content_lines.append(
                    f".dtrx source: {self._dtrx_source}"
                )
                content_lines.append("")

            file_path.write_text(
                "\n".join(content_lines), encoding="utf-8"
            )
            file_map[failure.id] = f"failures/{filename}"

        return file_map

    def _write_error_files(
        self,
        errors: list[DeployError],
    ) -> dict[int, str]:
        """Write individual error detail files to errors/ directory.

        Args:
            errors: List of deploy errors to write.

        Returns:
            Mapping from error ID to relative file path.
        """
        if not errors:
            return {}

        errors_dir = self._run_dir / "errors"
        errors_dir.mkdir(parents=True, exist_ok=True)

        file_map: dict[int, str] = {}

        # Sort: by phase order, then container name alphabetically
        phase_order = {p: i for i, p in enumerate(DEPLOY_PHASES)}
        sorted_errors = sorted(
            errors,
            key=lambda e: (
                phase_order.get(e.phase, 99),
                e.container or "",
            ),
        )

        for seq, error in enumerate(sorted_errors, start=1):
            # Build filename: {NNN}-{phase}-{error_type}[-{container}].txt
            body_parts = [error.phase, error.error_type]
            if error.container:
                body_parts.append(error.container)
            body = "-".join(
                re.sub(r"[^a-zA-Z0-9_\-]", "-", p) for p in body_parts
            )
            body = re.sub(r"-{2,}", "-", body).strip("-")
            if len(body) > _MAX_FILENAME_BODY_LENGTH:
                body = body[:_MAX_FILENAME_BODY_LENGTH].rstrip("-")

            filename = f"{seq:03d}-{body}.txt"
            file_path = errors_dir / filename

            # Write error detail file
            content_lines: list[str] = [
                f"PHASE: {error.phase}",
                f"ERROR: {error.error_type}",
                f"MESSAGE: {error.error_message}",
                "",
            ]

            if error.container:
                content_lines.append("--- Relevant Container ---")
                content_lines.append(error.container)
                content_lines.append("")

                # Add Docker log excerpt
                log_path = self._run_dir / "docker-logs" / f"{error.container}.log"
                if log_path.exists():
                    content_lines.append("--- Container Log Excerpt ---")
                    excerpt = self._excerpt_docker_log(log_path)
                    content_lines.append(excerpt)
                    content_lines.append("")

            if error.generated_file:
                content_lines.append("--- Generated Files ---")
                content_lines.append(error.generated_file)
                content_lines.append("")

            if error.codegen_hint:
                content_lines.append("--- Codegen Hint ---")
                content_lines.append(
                    f"Probable template: "
                    f"{error.codegen_hint['probable_template']}"
                )
                content_lines.append(
                    f"Probable generator: "
                    f"{error.codegen_hint['probable_generator']}"
                )
                content_lines.append(
                    f".dtrx source: {self._dtrx_source}"
                )
                content_lines.append("")

            file_path.write_text(
                "\n".join(content_lines), encoding="utf-8"
            )
            file_map[error.id] = f"errors/{filename}"

        return file_map

    def _copy_test_artifacts_to_services(
        self, services: list[ServiceStatus]
    ) -> None:
        """Copy JUnit XML and Jest JSON into services/ subdirectory.

        Copies (not moves) test artifacts into organized services/{name}/
        subdirectories. Originals stay in place.

        Args:
            services: List of service status objects (for service names).
        """
        services_dir = self._run_dir / "services"

        # Map of service names that we know about
        service_names = {svc.name for svc in services}

        # Copy JUnit XML files
        for xml_path in self._run_dir.glob("pytest-*.xml"):
            # Extract service name from filename
            service_match = re.search(
                r"pytest-(?:spec|integration)-(.+?)(?:-project|-service)?$",
                xml_path.stem,
            )
            if not service_match:
                continue

            service_name = service_match.group(1)
            stem_lower = xml_path.stem.lower()

            if "spec" in stem_lower:
                dest_dir = services_dir / service_name / "spec"
            else:
                dest_dir = services_dir / service_name / "integration"

            dest_dir.mkdir(parents=True, exist_ok=True)

            # Determine destination filename
            if "project" in stem_lower:
                dest_name = "junit-project.xml"
            elif "service" in stem_lower:
                dest_name = "junit-service.xml"
            else:
                dest_name = "junit.xml"

            shutil.copy2(xml_path, dest_dir / dest_name)

        # Copy Jest JSON files
        for jest_path in self._run_dir.glob("jest-*.json"):
            stem_lower = jest_path.stem.lower()
            # Determine phase
            if "spec" in stem_lower:
                phase_dir = "spec"
            else:
                phase_dir = "integration"

            # Jest files are often at root level — use first service
            if service_names:
                for svc_name in sorted(service_names):
                    dest_dir = services_dir / svc_name / phase_dir
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(jest_path, dest_dir / "jest-results.json")
                    break

        # Also copy from subdirectories (TypeScript pattern)
        for subdir in self._run_dir.iterdir():
            if not subdir.is_dir() or subdir.name in (
                "docker-logs",
                "services",
                "failures",
                "errors",
            ):
                continue
            for jest_path in subdir.glob("jest-*.json"):
                service_name = subdir.name
                stem_lower = jest_path.stem.lower()
                if "spec" in stem_lower:
                    phase_dir = "spec"
                else:
                    phase_dir = "integration"

                dest_dir = services_dir / service_name / phase_dir
                dest_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(jest_path, dest_dir / "jest-results.json")

    # --- Helper methods ---

    def _determine_result(
        self, phases: dict[str, PhaseResult]
    ) -> tuple[str, Optional[str]]:
        """Determine overall result and the first failed phase.

        Args:
            phases: Dict of phase results.

        Returns:
            Tuple of (result string, failed_phase or None).
        """
        for phase_name in DEPLOY_PHASES:
            phase = phases.get(phase_name)
            if phase and phase.result == "FAILED":
                return "FAILED", phase_name
        # No phase is explicitly FAILED. If every Docker lifecycle phase is
        # SKIPPED, the deploy never ran (engine unavailable, or build failed
        # before writing any artifact). SKIPPED != PASSED — surface the failure
        # at docker-build, the first phase that should have executed.
        all_infra_skipped = all(
            (phases.get(p) or PhaseResult(result="SKIPPED")).result == "SKIPPED"
            for p in _INFRA_PHASES
        )
        if all_infra_skipped:
            return "FAILED", "docker-build"
        return "PASSED", None

    def _classify_error_type(self, phase: str, message: str) -> str:
        """Classify the error type for an infrastructure error.

        Args:
            phase: The deploy phase where the error occurred.
            message: The error message.

        Returns:
            A classified error type string.
        """
        message_lower = message.lower()

        if "unhealthy" in message_lower:
            return "ContainerUnhealthy"
        if "build" in message_lower and "fail" in message_lower:
            return "BuildFailed"
        if "timeout" in message_lower or "timed out" in message_lower:
            return "Timeout"
        if "connection refused" in message_lower:
            return "ConnectionRefused"
        if "port" in message_lower and (
            "conflict" in message_lower or "in use" in message_lower
        ):
            return "PortConflict"
        if "not found" in message_lower or "no such" in message_lower:
            return "NotFound"

        # Default: use the phase name as error type
        return f"{phase.replace('-', '_')}_error".title().replace("_", "")

    def _get_generated_file_for_phase(
        self, phase: str, container: Optional[str]
    ) -> Optional[str]:
        """Get the most likely generated file for a phase failure.

        Args:
            phase: The deploy phase.
            container: The container name (if any).

        Returns:
            Generated file path or None.
        """
        if phase in ("docker-build", "docker-up"):
            return "docker-compose.yml"
        if phase == "health-check":
            return None
        if phase == "db-connectivity":
            return None
        return None

    def _extract_service_from_test_id(self, test_id: str) -> str:
        """Extract service name from a test ID.

        Args:
            test_id: The test identifier string.

        Returns:
            Extracted service name.
        """
        # Pattern: tests/test_{service_name}.py::...
        match = re.search(r"test_(\w+)\.py", test_id)
        if match:
            return match.group(1)
        # Pattern: tests/{service_name}/...
        match = re.search(r"tests/(\w+)/", test_id)
        if match:
            return match.group(1)
        return "unknown"

    def _classname_to_filepath(self, classname: str) -> str:
        """Convert a JUnit classname to a file path.

        Args:
            classname: The JUnit classname attribute.

        Returns:
            A forward-slash file path string.
        """
        if not classname:
            return "unknown"

        parts = classname.split(".")
        module_parts: list[str] = []
        for part in parts:
            if part and part[0].isupper():
                break
            module_parts.append(part)

        if not module_parts:
            return "unknown"

        return "/".join(module_parts) + ".py"

    def _extract_error_type_from_message(self, message: str) -> str:
        """Extract error type from the first line of an error message.

        Args:
            message: The error message text.

        Returns:
            Extracted error type or empty string.
        """
        first_line = message.split("\n", 1)[0]
        colon_pos = first_line.find(": ")
        if colon_pos > 0:
            candidate = first_line[:colon_pos].strip()
            if candidate and candidate[0].isupper() and candidate.isidentifier():
                return candidate
        if first_line.strip().isidentifier() and first_line[0].isupper():
            return first_line.strip()
        return ""

    def _extract_line_number(self, traceback_text: str) -> int:
        """Extract a line number from traceback text.

        Args:
            traceback_text: The traceback text.

        Returns:
            Extracted line number or 0.
        """
        # Match patterns like "file.py:42:" or "line 42"
        match = re.search(r":(\d+):", traceback_text)
        if match:
            return int(match.group(1))
        match = re.search(r"line\s+(\d+)", traceback_text, re.IGNORECASE)
        if match:
            return int(match.group(1))
        return 0
