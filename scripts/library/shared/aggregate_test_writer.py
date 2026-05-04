"""Cross-project test result aggregation.

Reads per-project index.json files, correlates error clusters across
projects, and produces aggregate-index.json and aggregate-summary.txt
at the .generated/.test_results/ level.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from shared.generated_test_log_writer import normalize_error_message

logger = logging.getLogger(__name__)

_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ProjectSummary:
    """Summary of one project's test results for aggregation."""

    project: str
    example: str
    result_dir: str
    result: str
    counts: dict[str, int]
    top_cluster_pattern: str | None
    suite_failure_message: str | None
    error_clusters: list[dict[str, Any]]
    failure_clusters: list[dict[str, Any]]


@dataclass(frozen=True)
class CrossProjectCluster:
    """An error pattern that appears across multiple projects."""

    cluster_id: int
    pattern: str
    projects_affected: list[str]
    total_errors: int
    codegen_hint: dict[str, str] | None
    representative_project: str


@dataclass(frozen=True)
class SuiteFailureCluster:
    """A suite failure pattern that appears across multiple projects."""

    cluster_id: int
    pattern: str
    projects_affected: list[str]
    total_suite_failures: int
    representative_project: str


class AggregateTestWriter:
    """Aggregates per-project test results into cross-project summaries.

    Reads index.json from each project's test results, correlates
    error clusters across projects by normalized pattern, and writes
    aggregate-index.json and aggregate-summary.txt.
    """

    def __init__(
        self,
        language: str,
        platform: str,
        output_dir: Path,
    ) -> None:
        """Initialize the aggregate writer.

        Args:
            language: ``python`` or ``typescript``.
            platform: ``docker`` or other platform identifier.
            output_dir: Directory where aggregate files will be written.
        """
        self._language = language
        self._platform = platform
        self._output_dir = output_dir
        self._projects: list[ProjectSummary] = []
        self._raw_data: list[dict[str, Any]] = []

    def add_project_results(self, index_json_path: Path) -> None:
        """Read a project's index.json and add to aggregation.

        Args:
            index_json_path: Path to the project's index.json file.

        Raises:
            FileNotFoundError: If index_json_path does not exist.
            json.JSONDecodeError: If the file is not valid JSON.
        """
        if not index_json_path.exists():
            raise FileNotFoundError(
                f"index.json not found at {index_json_path}. "
                f"Expected GeneratedTestLogWriter to produce this file."
            )

        data = json.loads(index_json_path.read_text(encoding="utf-8"))
        self._raw_data.append(data)

        result = data.get("result", "UNKNOWN")
        counts = data.get("counts", {})
        error_clusters = data.get("error_clusters", [])
        failure_clusters = data.get("failure_clusters", [])

        # Determine top cluster pattern (highest count error cluster)
        top_pattern: str | None = None
        if error_clusters:
            top_cluster = max(error_clusters, key=lambda c: c.get("count", 0))
            top_pattern = top_cluster.get("pattern")
        elif failure_clusters:
            top_cluster = max(failure_clusters, key=lambda c: c.get("count", 0))
            top_pattern = top_cluster.get("pattern")

        # Check for suite failure message from services
        suite_failure_msg: str | None = None
        for svc in data.get("services", []):
            msg = svc.get("suite_failure_message")
            if msg is not None:
                suite_failure_msg = msg
                break

        summary = ProjectSummary(
            project=data.get("project", ""),
            example=data.get("example", ""),
            result_dir=str(index_json_path.parent),
            result=result,
            counts=counts,
            top_cluster_pattern=top_pattern,
            suite_failure_message=suite_failure_msg,
            error_clusters=error_clusters,
            failure_clusters=failure_clusters,
        )
        self._projects.append(summary)

        logger.info(
            "aggregate_writer_add_project project=%s result=%s",
            summary.project,
            result,
        )

    def write(self) -> Path:
        """Write aggregate-index.json and aggregate-summary.txt.

        Returns:
            Path to the written aggregate-index.json file.
        """
        self._output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now()

        # Separate passed and failed projects
        failed_projects = [p for p in self._projects if p.result != "PASSED"]
        passed_count = sum(1 for p in self._projects if p.result == "PASSED")

        # Aggregate counts
        total_counts = self._aggregate_total_counts()

        # Correlate error clusters across projects
        cross_project_clusters = self._correlate_error_clusters()

        # Correlate suite failure clusters
        suite_failure_clusters = self._correlate_suite_failures()

        # Write aggregate-index.json
        self._write_aggregate_index_json(
            timestamp=timestamp,
            total_projects=len(self._projects),
            passed_count=passed_count,
            failed_projects=failed_projects,
            total_counts=total_counts,
            cross_project_clusters=cross_project_clusters,
            suite_failure_clusters=suite_failure_clusters,
        )

        # Write aggregate-summary.txt
        self._write_aggregate_summary_txt(
            timestamp=timestamp,
            total_projects=len(self._projects),
            passed_count=passed_count,
            failed_projects=failed_projects,
            total_counts=total_counts,
            cross_project_clusters=cross_project_clusters,
            suite_failure_clusters=suite_failure_clusters,
        )

        logger.info(
            "aggregate_writer_complete total=%d passed=%d failed=%d "
            "cross_clusters=%d suite_clusters=%d",
            len(self._projects),
            passed_count,
            len(failed_projects),
            len(cross_project_clusters),
            len(suite_failure_clusters),
        )

        return self._output_dir / "aggregate-index.json"

    # ------------------------------------------------------------------
    # Internal — aggregation
    # ------------------------------------------------------------------

    def _aggregate_total_counts(self) -> dict[str, int]:
        """Sum counts across all projects."""
        totals: dict[str, int] = {
            "passed": 0,
            "failed": 0,
            "errors": 0,
            "skipped": 0,
            "suite_failures": 0,
        }
        for proj in self._projects:
            for key in totals:
                totals[key] += proj.counts.get(key, 0)
        return totals

    def _correlate_error_clusters(self) -> list[CrossProjectCluster]:
        """Correlate error clusters across projects by normalized pattern.

        Returns:
            List of CrossProjectCluster sorted by total_errors descending.
        """
        # Collect all error clusters grouped by pattern
        pattern_groups: dict[str, list[tuple[ProjectSummary, dict[str, Any]]]] = {}

        for proj in self._projects:
            for cluster in proj.error_clusters:
                pattern = cluster.get("pattern", "")
                if pattern not in pattern_groups:
                    pattern_groups[pattern] = []
                pattern_groups[pattern].append((proj, cluster))

            for cluster in proj.failure_clusters:
                pattern = cluster.get("pattern", "")
                if pattern not in pattern_groups:
                    pattern_groups[pattern] = []
                pattern_groups[pattern].append((proj, cluster))

        # Build cross-project clusters
        result: list[CrossProjectCluster] = []
        for cluster_id, (pattern, entries) in enumerate(
            sorted(
                pattern_groups.items(),
                key=lambda kv: sum(e[1].get("count", 0) for e in kv[1]),
                reverse=True,
            ),
            start=1,
        ):
            projects_affected = sorted({e[0].example for e in entries})
            total_errors = sum(e[1].get("count", 0) for e in entries)

            # Pick codegen hint from first entry that has one
            hint: dict[str, str] | None = None
            for _, cluster_data in entries:
                h = cluster_data.get("codegen_hint")
                if h is not None:
                    hint = h
                    break

            # Representative = project with highest count for this pattern
            rep_entry = max(entries, key=lambda e: e[1].get("count", 0))
            rep_project = rep_entry[0].example

            # Tie-break: alphabetically first
            max_count = rep_entry[1].get("count", 0)
            tied = [
                e[0].example
                for e in entries
                if e[1].get("count", 0) == max_count
            ]
            rep_project = sorted(tied)[0]

            cpc = CrossProjectCluster(
                cluster_id=cluster_id,
                pattern=pattern,
                projects_affected=projects_affected,
                total_errors=total_errors,
                codegen_hint=hint,
                representative_project=rep_project,
            )
            result.append(cpc)

        return result

    def _correlate_suite_failures(self) -> list[SuiteFailureCluster]:
        """Correlate suite failures across projects by normalized message.

        Returns:
            List of SuiteFailureCluster sorted by total_suite_failures desc.
        """
        pattern_groups: dict[str, list[ProjectSummary]] = {}

        for proj in self._projects:
            if proj.suite_failure_message is not None:
                # Normalize suite failure message the same way
                normalized = _normalize_suite_failure(proj.suite_failure_message)
                if normalized not in pattern_groups:
                    pattern_groups[normalized] = []
                pattern_groups[normalized].append(proj)

            # Also check for SuiteFailure-typed errors in error_clusters
            for cluster in proj.error_clusters:
                if "SuiteFailure" in cluster.get("pattern", ""):
                    pattern = cluster.get("pattern", "")
                    if pattern not in pattern_groups:
                        pattern_groups[pattern] = []
                    if proj not in pattern_groups[pattern]:
                        pattern_groups[pattern].append(proj)

        result: list[SuiteFailureCluster] = []
        for cluster_id, (pattern, projects) in enumerate(
            sorted(
                pattern_groups.items(),
                key=lambda kv: len(kv[1]),
                reverse=True,
            ),
            start=1,
        ):
            projects_affected = sorted({p.example for p in projects})
            total = sum(p.counts.get("suite_failures", 0) for p in projects)
            if total == 0:
                total = len(projects)

            # Representative: most suite failures, then alphabetically first
            rep = sorted(
                projects,
                key=lambda p: (-p.counts.get("suite_failures", 0), p.example),
            )[0]

            sfc = SuiteFailureCluster(
                cluster_id=cluster_id,
                pattern=pattern,
                projects_affected=projects_affected,
                total_suite_failures=total,
                representative_project=rep.example,
            )
            result.append(sfc)

        return result

    # ------------------------------------------------------------------
    # Internal — output files
    # ------------------------------------------------------------------

    def _write_aggregate_index_json(
        self,
        timestamp: datetime,
        total_projects: int,
        passed_count: int,
        failed_projects: list[ProjectSummary],
        total_counts: dict[str, int],
        cross_project_clusters: list[CrossProjectCluster],
        suite_failure_clusters: list[SuiteFailureCluster],
    ) -> None:
        """Write the aggregate-index.json file."""
        failed_json: list[dict[str, Any]] = []
        for proj in failed_projects:
            entry: dict[str, Any] = {
                "project": proj.project,
                "example": proj.example,
                "result_dir": proj.result_dir,
                "counts": proj.counts,
                "top_cluster_pattern": proj.top_cluster_pattern,
            }
            if proj.suite_failure_message is not None:
                entry["suite_failure_message"] = proj.suite_failure_message
            failed_json.append(entry)

        clusters_json: list[dict[str, Any]] = []
        for cpc in cross_project_clusters:
            clusters_json.append({
                "cluster_id": cpc.cluster_id,
                "pattern": cpc.pattern,
                "projects_affected": cpc.projects_affected,
                "total_errors": cpc.total_errors,
                "codegen_hint": cpc.codegen_hint,
                "representative_project": cpc.representative_project,
            })

        suite_json: list[dict[str, Any]] = []
        for sfc in suite_failure_clusters:
            suite_json.append({
                "cluster_id": sfc.cluster_id,
                "pattern": sfc.pattern,
                "projects_affected": sfc.projects_affected,
                "total_suite_failures": sfc.total_suite_failures,
                "representative_project": sfc.representative_project,
            })

        index: dict[str, Any] = {
            "schema_version": _SCHEMA_VERSION,
            "timestamp": timestamp.strftime("%Y-%m-%dT%H:%M:%S"),
            "language": self._language,
            "platform": self._platform,
            "total_projects": total_projects,
            "projects_passed": passed_count,
            "projects_failed": len(failed_projects),
            "total_counts": total_counts,
            "failed_projects": failed_json,
            "cross_project_clusters": clusters_json,
            "suite_failure_clusters": suite_json,
        }

        path = self._output_dir / "aggregate-index.json"
        path.write_text(
            json.dumps(index, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def _write_aggregate_summary_txt(
        self,
        timestamp: datetime,
        total_projects: int,
        passed_count: int,
        failed_projects: list[ProjectSummary],
        total_counts: dict[str, int],
        cross_project_clusters: list[CrossProjectCluster],
        suite_failure_clusters: list[SuiteFailureCluster],
    ) -> None:
        """Write the human-readable aggregate-summary.txt."""
        lines: list[str] = []
        lang_label = self._language.capitalize()
        platform_label = self._platform.capitalize()

        lines.append("Generated Project Unit Tests — Cross-Project Summary")
        lines.append(
            f"{timestamp.strftime('%Y-%m-%d %H:%M:%S')} | "
            f"{lang_label}/{platform_label}"
        )
        lines.append("")

        total_passed_tests = total_counts["passed"]
        total_errors = total_counts["errors"]
        total_failed = total_counts["failed"]
        error_label_parts: list[str] = []
        if total_errors > 0:
            error_label_parts.append(f"{total_errors:,} errors")
        if total_failed > 0:
            error_label_parts.append(f"{total_failed:,} failed")
        error_label = ", ".join(error_label_parts)

        lines.append(
            f"RESULT: {passed_count}/{total_projects} projects passed "
            f"({total_passed_tests:,} tests passed"
            + (f", {error_label}" if error_label else "")
            + ")"
        )
        lines.append("")

        if cross_project_clusters:
            lines.append("CROSS-PROJECT CLUSTERS:")
            for cpc in cross_project_clusters:
                proj_count = len(cpc.projects_affected)
                proj_label = "projects" if proj_count > 1 else "project"
                lines.append(
                    f"  [{cpc.total_errors} errors across {proj_count} {proj_label}] "
                    f"{cpc.pattern}"
                )
                if cpc.codegen_hint:
                    lines.append(
                        f"    Probable template: {cpc.codegen_hint['probable_template']}"
                    )
                affected_names = [
                    e.rsplit("/", 1)[-1] if "/" in e else e
                    for e in cpc.projects_affected
                ]
                lines.append(f"    Affected: {', '.join(affected_names)}")
            lines.append("")

        if suite_failure_clusters:
            lines.append("SUITE FAILURE CLUSTERS:")
            for sfc in suite_failure_clusters:
                proj_count = len(sfc.projects_affected)
                proj_label = "projects" if proj_count > 1 else "project"
                lines.append(
                    f"  [{sfc.total_suite_failures} suite failures across "
                    f"{proj_count} {proj_label}] {sfc.pattern}"
                )
                affected_names = [
                    e.rsplit("/", 1)[-1] if "/" in e else e
                    for e in sfc.projects_affected
                ]
                lines.append(f"    Affected: {', '.join(affected_names)}")
            lines.append("")

        if failed_projects:
            lines.append("FAILED PROJECTS:")
            for proj in sorted(failed_projects, key=lambda p: p.example):
                example_short = proj.example.rsplit("/", 1)[-1] if "/" in proj.example else proj.example
                parts: list[str] = []
                if proj.counts.get("passed", 0) > 0:
                    parts.append(f"{proj.counts['passed']} passed")
                if proj.counts.get("errors", 0) > 0:
                    parts.append(f"{proj.counts['errors']} errors")
                if proj.counts.get("failed", 0) > 0:
                    parts.append(f"{proj.counts['failed']} failed")
                counts_str = ", ".join(parts) if parts else "no tests"

                # Determine cluster label
                cluster_label = ""
                if proj.top_cluster_pattern:
                    # Extract short pattern
                    short_pattern = proj.top_cluster_pattern.split(": ", 1)[-1] if ": " in proj.top_cluster_pattern else proj.top_cluster_pattern
                    cluster_label = f"  → {short_pattern}"
                elif proj.suite_failure_message:
                    cluster_label = "  → [suiteFailure]"

                lines.append(
                    f"  ✗ {example_short:<30s} {counts_str}{cluster_label}"
                )

        path = self._output_dir / "aggregate-summary.txt"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _normalize_suite_failure(message: str) -> str:
    """Normalize a suite failure message for clustering.

    Replaces specific module/package names with wildcards.

    Args:
        message: The raw suite failure message.

    Returns:
        Normalized pattern string.
    """
    import re

    # Replace quoted strings
    normalized = re.sub(r"'[^']*'", "*", message)
    normalized = re.sub(r'"[^"]*"', "*", normalized)
    return normalized.split("\n", 1)[0]
