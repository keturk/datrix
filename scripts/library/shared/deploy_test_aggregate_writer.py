"""Deploy test aggregate writer for cross-project correlation.

Reads per-project deploy test index.json files, correlates failure and
error clusters across projects, and writes aggregate-index.json and
aggregate-summary.txt for efficient cross-project triage.
"""

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_SCHEMA_VERSION = 1


class DeployTestAggregateWriter:
    """Aggregates deploy test results across multiple projects.

    Reads index.json from each project's deploy test results directory,
    correlates clusters across projects, and writes aggregate output
    to a central directory.
    """

    def __init__(
        self,
        aggregate_dir: Path,
        language: str,
        platform: str,
    ) -> None:
        """Initialize the aggregate writer.

        Args:
            aggregate_dir: Path to the aggregate output directory
                (e.g., .generated/.test_results/deploy-tests-{ts}/).
            language: Language being tested ("python" or "typescript").
            platform: Platform being tested ("docker").
        """
        self._aggregate_dir = aggregate_dir
        self._language = language
        self._platform = platform

    def write(
        self,
        project_index_paths: list[Path],
        timestamp: datetime,
        full_log_path: Optional[Path] = None,
    ) -> Path:
        """Write aggregate output files.

        Reads each project's index.json, correlates clusters, and
        writes aggregate-index.json and aggregate-summary.txt.

        Args:
            project_index_paths: Paths to per-project index.json files.
            timestamp: Timestamp of the aggregate run.
            full_log_path: Optional path to the full orchestration log
                to copy into the aggregate directory.

        Returns:
            Path to the written aggregate-index.json file.
        """
        logger.info(
            "deploy_test_aggregate_writer_start projects=%d "
            "aggregate_dir=%s",
            len(project_index_paths),
            self._aggregate_dir,
        )

        self._aggregate_dir.mkdir(parents=True, exist_ok=True)

        # Read per-project data
        project_indices = self._read_project_indices(project_index_paths)

        # Correlate clusters across projects
        cross_project_clusters = self._correlate_clusters(project_indices)

        # Write output files
        self._write_aggregate_index_json(
            timestamp, project_indices, cross_project_clusters
        )
        self._write_aggregate_summary_txt(
            timestamp, project_indices, cross_project_clusters
        )

        # Copy full orchestration log if provided
        if full_log_path is not None and full_log_path.exists():
            shutil.copy2(full_log_path, self._aggregate_dir / "full.log")

        logger.info(
            "deploy_test_aggregate_writer_complete projects=%d "
            "failed=%d clusters=%d",
            len(project_indices),
            sum(
                1
                for p in project_indices
                if p.get("result") == "FAILED"
            ),
            len(cross_project_clusters),
        )

        return self._aggregate_dir / "aggregate-index.json"

    # --- Reading per-project data ---

    def _read_project_indices(
        self,
        paths: list[Path],
    ) -> list[dict[str, object]]:
        """Read and validate per-project index.json files.

        Args:
            paths: Paths to per-project index.json files.

        Returns:
            List of parsed index data dicts (only successfully read ones).
        """
        indices: list[dict[str, object]] = []

        for path in paths:
            if not path.exists():
                logger.warning(
                    "deploy_test_aggregate_writer_index_missing path=%s",
                    path,
                )
                continue

            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    logger.warning(
                        "deploy_test_aggregate_writer_index_invalid "
                        "path=%s reason=not_a_dict",
                        path,
                    )
                    continue
                # Store the result_dir (parent of the index.json)
                data["_result_dir"] = str(path.parent.resolve())
                indices.append(data)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning(
                    "deploy_test_aggregate_writer_index_read_error "
                    "path=%s error=%s",
                    path,
                    exc,
                )

        return indices

    # --- Cross-project clustering ---

    def _correlate_clusters(
        self,
        project_indices: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        """Correlate failure and error clusters across projects.

        Groups clusters from different projects that share the same
        normalized error pattern.

        Args:
            project_indices: List of per-project index data.

        Returns:
            List of cross-project cluster dicts.
        """
        # Collect all clusters with their project context
        pattern_groups: dict[str, list[dict[str, object]]] = {}

        for project_data in project_indices:
            if project_data.get("result") != "FAILED":
                continue

            project_name = str(project_data.get("example", ""))

            # Collect error clusters (infrastructure)
            for cluster in project_data.get("error_clusters", []):
                if not isinstance(cluster, dict):
                    continue
                pattern = str(cluster.get("pattern", ""))
                if not pattern:
                    continue

                if pattern not in pattern_groups:
                    pattern_groups[pattern] = []
                pattern_groups[pattern].append(
                    {
                        "project": project_name,
                        "phase": str(cluster.get("phase", "")),
                        "failure_type": "infrastructure",
                        "count": int(cluster.get("count", 1)),
                        "codegen_hint": cluster.get("codegen_hint"),
                    }
                )

            # Collect failure clusters (logic / transient)
            for cluster in project_data.get("failure_clusters", []):
                if not isinstance(cluster, dict):
                    continue
                pattern = str(cluster.get("pattern", ""))
                if not pattern:
                    continue
                failure_type = str(
                    cluster.get("failure_type", "logic")
                )

                if pattern not in pattern_groups:
                    pattern_groups[pattern] = []
                pattern_groups[pattern].append(
                    {
                        "project": project_name,
                        "phase": str(cluster.get("phase", "")),
                        "failure_type": failure_type,
                        "count": int(cluster.get("count", 1)),
                        "codegen_hint": cluster.get("codegen_hint"),
                    }
                )

        # Build cross-project clusters
        cross_clusters: list[dict[str, object]] = []
        for cluster_id, (pattern, members) in enumerate(
            sorted(
                pattern_groups.items(),
                key=lambda item: sum(m["count"] for m in item[1]),
                reverse=True,
            ),
            start=1,
        ):
            projects_affected = sorted(
                set(str(m["project"]) for m in members)
            )
            total_errors = sum(int(m["count"]) for m in members)
            representative_project = projects_affected[0]

            # Use the first member's metadata
            first = members[0]

            cross_clusters.append(
                {
                    "cluster_id": cluster_id,
                    "pattern": pattern,
                    "phase": str(first["phase"]),
                    "failure_type": str(first["failure_type"]),
                    "projects_affected": projects_affected,
                    "total_errors": total_errors,
                    "codegen_hint": first.get("codegen_hint"),
                    "representative_project": representative_project,
                }
            )

        return cross_clusters

    def _match_cluster_patterns(
        self,
        pattern_a: str,
        pattern_b: str,
    ) -> bool:
        """Check if two cluster patterns match after normalization.

        Args:
            pattern_a: First normalized pattern.
            pattern_b: Second normalized pattern.

        Returns:
            True if patterns are identical (post-normalization matching).
        """
        return pattern_a == pattern_b

    # --- Output writers ---

    def _write_aggregate_index_json(
        self,
        timestamp: datetime,
        project_indices: list[dict[str, object]],
        cross_project_clusters: list[dict[str, object]],
    ) -> None:
        """Write aggregate-index.json with cross-project data.

        Args:
            timestamp: Aggregate run timestamp.
            project_indices: Per-project index data.
            cross_project_clusters: Correlated cross-project clusters.
        """
        total_projects = len(project_indices)
        projects_passed = sum(
            1
            for p in project_indices
            if p.get("result") == "PASSED"
        )
        projects_failed = total_projects - projects_passed

        # Compute total counts
        total_passed = 0
        total_failed = 0
        total_errors = 0
        total_skipped = 0
        infrastructure_failures = 0

        for project_data in project_indices:
            if project_data.get("result") != "FAILED":
                # Count tests from passing projects' phases
                phases = project_data.get("phases", {})
                if isinstance(phases, dict):
                    for phase_data in phases.values():
                        if isinstance(phase_data, dict):
                            counts = phase_data.get("counts")
                            if isinstance(counts, dict):
                                total_passed += int(
                                    counts.get("passed", 0)
                                )
                continue

            # Failed project
            failed_phase = project_data.get("failed_phase")

            # Infrastructure failure = failed at Docker lifecycle phase
            if failed_phase in (
                "docker-build",
                "docker-up",
                "health-check",
                "db-connectivity",
            ):
                infrastructure_failures += 1
            else:
                # Count test-level failures
                failures = project_data.get("failures", [])
                if isinstance(failures, list):
                    total_failed += len(failures)

                # Count passed tests from phases
                phases = project_data.get("phases", {})
                if isinstance(phases, dict):
                    for phase_data in phases.values():
                        if isinstance(phase_data, dict):
                            counts = phase_data.get("counts")
                            if isinstance(counts, dict):
                                total_passed += int(
                                    counts.get("passed", 0)
                                )

        total_counts: dict[str, int] = {
            "passed": total_passed,
            "failed": total_failed,
            "errors": total_errors,
            "skipped": total_skipped,
            "infrastructure_failures": infrastructure_failures,
        }

        # Build failed_projects array
        failed_projects: list[dict[str, object]] = []
        for project_data in project_indices:
            if project_data.get("result") != "FAILED":
                continue

            # Get the top cluster pattern
            top_pattern = ""
            failure_clusters = project_data.get("failure_clusters", [])
            error_clusters = project_data.get("error_clusters", [])
            if isinstance(error_clusters, list) and error_clusters:
                first_ec = error_clusters[0]
                if isinstance(first_ec, dict):
                    top_pattern = str(first_ec.get("pattern", ""))
            elif isinstance(failure_clusters, list) and failure_clusters:
                first_fc = failure_clusters[0]
                if isinstance(first_fc, dict):
                    top_pattern = str(first_fc.get("pattern", ""))

            # Count tests for this project
            project_counts: dict[str, int] = {
                "passed": 0,
                "failed": 0,
                "errors": 0,
            }
            phases = project_data.get("phases", {})
            if isinstance(phases, dict):
                for phase_data in phases.values():
                    if isinstance(phase_data, dict):
                        counts = phase_data.get("counts")
                        if isinstance(counts, dict):
                            project_counts["passed"] += int(
                                counts.get("passed", 0)
                            )
                            project_counts["failed"] += int(
                                counts.get("failed", 0)
                            )
                            project_counts["errors"] += int(
                                counts.get("errors", 0)
                            )

            failed_projects.append(
                {
                    "project": str(project_data.get("project", "")),
                    "example": str(project_data.get("example", "")),
                    "result_dir": str(project_data.get("_result_dir", "")),
                    "failed_phase": project_data.get("failed_phase"),
                    "counts": project_counts,
                    "top_cluster_pattern": top_pattern,
                }
            )

        aggregate: dict[str, object] = {
            "schema_version": _SCHEMA_VERSION,
            "timestamp": timestamp.strftime("%Y-%m-%dT%H:%M:%S"),
            "language": self._language,
            "platform": self._platform,
            "total_projects": total_projects,
            "projects_passed": projects_passed,
            "projects_failed": projects_failed,
            "total_counts": total_counts,
            "failed_projects": failed_projects,
            "cross_project_clusters": cross_project_clusters,
        }

        output_path = self._aggregate_dir / "aggregate-index.json"
        output_path.write_text(
            json.dumps(aggregate, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def _write_aggregate_summary_txt(
        self,
        timestamp: datetime,
        project_indices: list[dict[str, object]],
        cross_project_clusters: list[dict[str, object]],
    ) -> None:
        """Write aggregate-summary.txt with human-readable summary.

        Args:
            timestamp: Aggregate run timestamp.
            project_indices: Per-project index data.
            cross_project_clusters: Correlated cross-project clusters.
        """
        total_projects = len(project_indices)
        projects_passed = sum(
            1
            for p in project_indices
            if p.get("result") == "PASSED"
        )

        # Count total tests
        total_test_passed = 0
        total_test_failed = 0
        for project_data in project_indices:
            phases = project_data.get("phases", {})
            if isinstance(phases, dict):
                for phase_data in phases.values():
                    if isinstance(phase_data, dict):
                        counts = phase_data.get("counts")
                        if isinstance(counts, dict):
                            total_test_passed += int(
                                counts.get("passed", 0)
                            )
                            total_test_failed += int(
                                counts.get("failed", 0)
                            )

        lines: list[str] = []
        lines.append(
            "Generated Project Deploy Tests \u2014 Cross-Project Summary"
        )
        lines.append(
            f"{timestamp.strftime('%Y-%m-%d %H:%M:%S')} | "
            f"{self._language.title()}/{self._platform.title()}"
        )
        lines.append("")

        # Result line
        test_summary = f"{total_test_passed} tests passed"
        if total_test_failed > 0:
            test_summary += f", {total_test_failed} failed"
        lines.append(
            f"RESULT: {projects_passed}/{total_projects} projects passed "
            f"({test_summary})"
        )
        lines.append("")

        # Group clusters by type
        infrastructure_clusters = [
            c
            for c in cross_project_clusters
            if c.get("failure_type") == "infrastructure"
        ]
        logic_clusters = [
            c
            for c in cross_project_clusters
            if c.get("failure_type") == "logic"
        ]
        transient_clusters = [
            c
            for c in cross_project_clusters
            if c.get("failure_type") == "transient"
        ]

        # Infrastructure failures
        if infrastructure_clusters:
            infra_projects = set()
            for c in infrastructure_clusters:
                projects_affected = c.get("projects_affected", [])
                if isinstance(projects_affected, list):
                    infra_projects.update(projects_affected)
            lines.append(
                f"INFRASTRUCTURE FAILURES ({len(infra_projects)} "
                f"project{'s' if len(infra_projects) != 1 else ''}):"
            )
            for cluster in infrastructure_clusters:
                projects_affected = cluster.get("projects_affected", [])
                if isinstance(projects_affected, list):
                    for proj in projects_affected:
                        phase = cluster.get("phase", "")
                        pattern = cluster.get("pattern", "")
                        lines.append(
                            f"  \u2717 {proj}  \u2192 {phase}: {pattern}"
                        )
                codegen_hint = cluster.get("codegen_hint")
                if isinstance(codegen_hint, dict):
                    template = codegen_hint.get("probable_template", "")
                    if template:
                        lines.append(
                            f"    Probable template: {template}"
                        )
            lines.append("")

        # Logic failures
        if logic_clusters:
            logic_projects = set()
            for c in logic_clusters:
                projects_affected = c.get("projects_affected", [])
                if isinstance(projects_affected, list):
                    logic_projects.update(projects_affected)
            lines.append(
                f"LOGIC FAILURES ({len(logic_projects)} "
                f"project{'s' if len(logic_projects) != 1 else ''}):"
            )
            for cluster in logic_clusters:
                projects_affected = cluster.get("projects_affected", [])
                if isinstance(projects_affected, list):
                    for proj in projects_affected:
                        phase = cluster.get("phase", "")
                        pattern = cluster.get("pattern", "")
                        lines.append(
                            f"  \u2717 {proj}  \u2192 {phase}: {pattern}"
                        )
                codegen_hint = cluster.get("codegen_hint")
                if isinstance(codegen_hint, dict):
                    template = codegen_hint.get("probable_template", "")
                    if template:
                        lines.append(
                            f"    Probable template: {template}"
                        )
            lines.append("")

        # Transient failures
        if transient_clusters:
            lines.append("TRANSIENT FAILURES:")
            for cluster in transient_clusters:
                projects_affected = cluster.get("projects_affected", [])
                total_errors = cluster.get("total_errors", 0)
                if isinstance(projects_affected, list):
                    for proj in projects_affected:
                        phase = cluster.get("phase", "")
                        pattern = cluster.get("pattern", "")
                        lines.append(
                            f"  \u2717 {proj}  \u2192 {phase}: "
                            f"{pattern} ({total_errors} test"
                            f"{'s' if int(str(total_errors)) != 1 else ''})"
                        )
            lines.append("")

        # Passed projects
        passed_projects = [
            p
            for p in project_indices
            if p.get("result") == "PASSED"
        ]
        if passed_projects:
            lines.append(f"PASSED PROJECTS ({len(passed_projects)}):")
            for project_data in passed_projects:
                project_name = str(
                    project_data.get("example", project_data.get("project", ""))
                )
                # Count tests
                proj_passed = 0
                phases = project_data.get("phases", {})
                if isinstance(phases, dict):
                    for phase_data in phases.values():
                        if isinstance(phase_data, dict):
                            counts = phase_data.get("counts")
                            if isinstance(counts, dict):
                                proj_passed += int(
                                    counts.get("passed", 0)
                                )
                if proj_passed > 0:
                    lines.append(
                        f"  \u2713 {project_name:<25} {proj_passed} passed"
                    )
                else:
                    lines.append(f"  \u2713 {project_name}")

        summary_path = self._aggregate_dir / "aggregate-summary.txt"
        summary_path.write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )
