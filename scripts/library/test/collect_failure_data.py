#!/usr/bin/env python3
"""Collect per-cluster failure data from a structured test-results run.

Reads a run directory's index.json, resolves the representative entry of
every error cluster and failure cluster, embeds the tail of its detail log,
and writes ``failure-data.json`` into the run directory. Supports all three
structured index schemas: the package schema (structured_log_writer), the
generated-project unit schema (generated_test_log_writer, which adds
codegen_hint/generated_file), and the deploy-test schema
(deploy_test_log_writer, which adds failed_phase/phases and whose
infrastructure error entries carry phase/container instead of test_id).

Usage:
  python scripts/library/test/collect_failure_data.py <run-dir | index.json>
  python scripts/library/test/collect_failure_data.py --project datrix-codegen-azure
  .\\scripts\\test\\collect-failure-data.ps1 -Project datrix-codegen-azure

Exit codes: 0 = analysis completed (even with zero failures),
2 = usage / input-not-found error.
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# Configure UTF-8 encoding for stdout/stderr on Windows
if sys.platform == "win32" and __name__ == "__main__":
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Add library directory to sys.path to import from shared and sibling modules
_LIBRARY_DIR = Path(__file__).resolve().parent.parent
if _LIBRARY_DIR.exists() and str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from shared.package_suites import (  # noqa: E402
    NODE_MANIFEST_NAME,
    NODE_TEST_SCRIPT_KEY,
    SuiteKind,
    detect_suite_kind,
)
from shared.venv import get_datrix_root  # noqa: E402

from test.status_tests import parse_timestamp_from_log_file  # noqa: E402

logger = logging.getLogger(__name__)

_SCHEMA_VERSION = 1
_OUTPUT_FILENAME = "failure-data.json"
_INDEX_JSON_NAME = "index.json"
_FULL_LOG_NAME = "full.log"
_RUN_DIR_PREFIX = "test-results-"
_DEFAULT_MAX_LOG_LINES = 60
_EXIT_OK = 0
_EXIT_USAGE = 2

# pytest warnings-summary section header (same shape extract_warnings.py parses)
_WARNINGS_HEADER = re.compile(r"^=+\s+warnings summary(?:\s+\(final\))?\s+=+\s*$")

# (kind, clusters key, accepted (member-ids key, representative-id key) pairs) -
# errors first per contract. A failure cluster's member-id keys are spelled
# differently across the schemas: structured_log_writer and deploy_test_log_writer
# use failure_ids/representative_failure_id, while generated_test_log_writer builds
# BOTH its cluster lists from one ErrorCluster shape and therefore spells them
# error_ids/representative_error_id in failure_clusters too. Both spellings are
# accepted explicitly, the same way _extract_counts accepts counts['error'] and
# counts['errors'] - an index carrying neither still fails loud.
_CLUSTER_KINDS: tuple[tuple[str, str, tuple[tuple[str, str], ...]], ...] = (
    ("error", "error_clusters", (("error_ids", "representative_error_id"),)),
    (
        "failure",
        "failure_clusters",
        (
            ("failure_ids", "representative_failure_id"),
            ("error_ids", "representative_error_id"),
        ),
    ),
)


class UsageError(Exception):
    """Invalid usage or missing input; the script exits with code 2."""


@dataclass(frozen=True)
class _RunContext:
    """Resolved inputs shared by all cluster payload builders."""

    run_dir: Path
    workspace: Path
    project: str
    max_log_lines: int


# ---------------------------------------------------------------------------
# Schema accessors (fail loud on unexpected shapes)
# ---------------------------------------------------------------------------


def _require_field(data: dict[str, object], key: str, where: str) -> object:
    if key not in data:
        raise UsageError(
            f"Missing required key '{key}' in {where}. Expected the structured "
            f"index.json schema (schema_version 1) produced by the test runner; "
            f"re-run the test suite to regenerate the run directory."
        )
    return data[key]


def _require_str(data: dict[str, object], key: str, where: str) -> str:
    value = _require_field(data, key, where)
    if not isinstance(value, str):
        raise UsageError(
            f"Key '{key}' in {where} must be a string, got {type(value).__name__}. "
            f"The index.json does not match the expected schema; re-run the test suite."
        )
    return value


def _require_int(data: dict[str, object], key: str, where: str) -> int:
    value = _require_field(data, key, where)
    if isinstance(value, bool) or not isinstance(value, int):
        raise UsageError(
            f"Key '{key}' in {where} must be an integer, got {type(value).__name__}. "
            f"The index.json does not match the expected schema; re-run the test suite."
        )
    return value


def _require_list(data: dict[str, object], key: str, where: str) -> list[object]:
    value = _require_field(data, key, where)
    if not isinstance(value, list):
        raise UsageError(
            f"Key '{key}' in {where} must be a list, got {type(value).__name__}. "
            f"The index.json does not match the expected schema; re-run the test suite."
        )
    return list(value)


def _as_dict(value: object, what: str, where: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise UsageError(
            f"{what} in {where} must be an object, got {type(value).__name__}. "
            f"The index.json does not match the expected schema; re-run the test suite."
        )
    return {str(key): item for key, item in value.items()}


def _load_index(index_path: Path) -> dict[str, object]:
    """Load and shape-check an index.json file."""
    try:
        raw = json.loads(index_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise UsageError(
            f"index.json at {index_path} is not valid JSON ({exc}). Expected a "
            f"structured test-results index; re-run the test suite to regenerate it."
        ) from exc
    return _as_dict(raw, "index.json root", str(index_path))


# ---------------------------------------------------------------------------
# Input resolution
# ---------------------------------------------------------------------------


def _resolve_run_dir_from_path(raw_path: str) -> Path:
    """Resolve a positional PATH (run dir or index.json) to the run directory."""
    path = Path(raw_path).resolve()
    if path.is_dir():
        if not (path / _INDEX_JSON_NAME).is_file():
            raise UsageError(
                f"No {_INDEX_JSON_NAME} found in directory {path}. Expected a "
                f"test-results run directory containing {_INDEX_JSON_NAME} "
                f"(e.g. <project>/.test_results/test-results-YYYYMMDD-HHMMSS)."
            )
        return path
    if path.is_file() and path.name == _INDEX_JSON_NAME:
        return path.parent
    raise UsageError(
        f"Input path is not a run directory or an {_INDEX_JSON_NAME} path: {path}. "
        f"Pass a test-results run directory or its {_INDEX_JSON_NAME}."
    )


def _resolve_run_dir_from_project(workspace: Path, project: str) -> Path:
    """Locate the newest test-results-* run dir with an index.json for a project."""
    project_dir = workspace / project
    if not project_dir.is_dir():
        available = sorted(
            item.name
            for item in workspace.iterdir()
            if item.is_dir() and item.name.startswith("datrix-")
        )
        raise UsageError(
            f"Project '{project}' not found at {project_dir}. "
            f"Available projects: {', '.join(available)}."
        )
    test_results_dir = project_dir / ".test_results"
    if not test_results_dir.is_dir():
        raise UsageError(
            f"No .test_results directory for project '{project}' at {test_results_dir}. "
            f"Run the package test suite first (scripts/test/test.ps1 {project})."
        )
    candidates: list[tuple[datetime, Path]] = []
    for item in test_results_dir.iterdir():
        if not item.is_dir() or not item.name.startswith(_RUN_DIR_PREFIX):
            continue
        timestamp = parse_timestamp_from_log_file(item.name)
        if timestamp is not None:
            candidates.append((timestamp, item))
    for _, run_dir in sorted(candidates, key=lambda pair: pair[0], reverse=True):
        if (run_dir / _INDEX_JSON_NAME).is_file():
            return run_dir
    raise UsageError(
        f"No test-results-* run directory with an {_INDEX_JSON_NAME} found under "
        f"{test_results_dir}. Run the package test suite first "
        f"(scripts/test/test.ps1 {project})."
    )


# ---------------------------------------------------------------------------
# Cluster payload construction
# ---------------------------------------------------------------------------


def _entries_by_id(entries: list[object], key: str, where: str) -> dict[int, dict[str, object]]:
    """Index failures/errors entries by their integer id."""
    result: dict[int, dict[str, object]] = {}
    for item in entries:
        entry = _as_dict(item, f"'{key}' entry", where)
        result[_require_int(entry, "id", where)] = entry
    return result


def _test_id_to_node_path(test_id: str) -> str | None:
    """Convert an index test_id to a pytest node path (dots -> '/', keep '::').

    ``tests.unit.test_foo.TestBar::test_baz`` becomes
    ``tests/unit/test_foo.py::TestBar::test_baz``. Path-style first components
    (generated-project/Jest test ids) are kept as-is.

    Returns None when the id carries no lowercase dotted module prefix to map -
    a test id from a target language whose test framework does not name tests by
    source path (xUnit's ``Namespace.Class::Method``, where every segment is
    capitalized). Datrix generates for many languages, so a non-Python id shape
    is an expected input here, not a malformed one; the caller falls back to the
    entry's own ``file``/``generated_file`` and emits no ``test_command`` (which
    is a pytest invocation, meaningful only for package runs anyway).
    """
    parts = test_id.split("::")
    first = parts[0]
    rest = parts[1:]
    if "/" in first or "\\" in first or first.endswith(".py"):
        return "::".join([first.replace("\\", "/"), *rest])
    dot_parts = first.split(".")
    module_parts: list[str] = []
    class_parts: list[str] = []
    for position, part in enumerate(dot_parts):
        if part and part[0].isupper():
            class_parts = dot_parts[position:]
            break
        module_parts.append(part)
    if not module_parts:
        return None
    module_path = "/".join(module_parts) + ".py"
    return "::".join([module_path, *class_parts, *rest])


def _build_test_command(ctx: _RunContext, node_path: str) -> str | None:
    """Build the ready-to-run re-run invocation for a representative test.

    Datrix packages do not share one test runner, so neither can this command.
    A pytest package is re-run by node ID through ``test-single.ps1``. A Node
    package (``datrix-vscode``) has no single-test runner at all — its suite is
    re-run by FILE through ``test.ps1 -Specific``, which accepts the source-side
    ``.ts`` name for the compiled file. Emitting the pytest form for a Node
    package would hand the reader a command that cannot run, so the suite the
    package actually carries decides the shape.

    Args:
        ctx: Resolved run context; ``workspace / project`` is the package root.
        node_path: The representative's test path (``file`` or
            ``file::selector...``).

    Returns:
        The invocation, or ``None`` when the package carries no recognizable
        test suite - there is no truthful command to emit for one.
    """
    scripts_dir = ctx.workspace / "datrix" / "scripts" / "test"
    suite_kind = detect_suite_kind(ctx.workspace / ctx.project)
    if suite_kind is SuiteKind.PYTEST:
        script = (scripts_dir / "test-single.ps1").as_posix()
        return f'powershell -File "{script}" "{node_path}" -Project {ctx.project}'
    if suite_kind is SuiteKind.NODE:
        script = (scripts_dir / "test.ps1").as_posix()
        test_file = node_path.split("::", 1)[0]
        return f'powershell -File "{script}" {ctx.project} -Specific "{test_file}"'
    logger.debug("no_suite_kind_for_project project=%s; test_command omitted", ctx.project)
    return None


def _read_log_tail(log_path: Path, max_lines: int) -> str:
    """Read the last max_lines lines of a per-failure detail log."""
    if not log_path.is_file():
        raise UsageError(
            f"Log file referenced by index.json not found: {log_path}. Expected the "
            f"per-failure detail file written by the structured log writer; the run "
            f"directory is incomplete - re-run the test suite to regenerate it."
        )
    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-max_lines:])


# Optional per-entry context fields copied verbatim onto the representative
# when present (deploy-test schema: infra errors have phase/container; test
# failures have phase/failure_type).
_OPTIONAL_ENTRY_FIELDS: tuple[str, ...] = ("phase", "failure_type", "container", "docker_log_file")


def _representative_payload(
    ctx: _RunContext,
    cluster: dict[str, object],
    entry: dict[str, object],
    where: str,
) -> tuple[dict[str, object], str | None]:
    """Build the representative sub-object; returns (payload, node_path).

    node_path is None for entries without a test_id (deploy-test
    infrastructure errors, which are keyed by phase/container instead) and for
    test ids whose shape carries no source-path prefix (see
    `_test_id_to_node_path`).
    """
    payload: dict[str, object] = {}
    node_path: str | None = None
    if "test_id" in entry:
        test_id = _require_str(entry, "test_id", where)
        node_path = _test_id_to_node_path(test_id)
        payload["test_id"] = test_id
        # Package schema carries an explicit 'file'; the generated-project
        # schemas do not, so derive it from the node path there - and leave it
        # null when the id shape yields no path (the entry's own
        # generated_file, copied below, is the locator in that case).
        if "file" in entry:
            payload["file"] = str(entry["file"])
        elif node_path is not None:
            payload["file"] = node_path.split("::", 1)[0]
        else:
            payload["file"] = None
    payload["error_type"] = _require_str(entry, "error_type", where)
    payload["error_message"] = _require_str(entry, "error_message", where)
    for optional_key in _OPTIONAL_ENTRY_FIELDS:
        if optional_key in entry and entry[optional_key] is not None:
            payload[optional_key] = entry[optional_key]
    # All three schemas carry the log_file key; deploy-test entries may carry
    # log_file: null (no per-item detail file was written) - emit
    # traceback_tail: null then, never guess a path.
    log_file_value = _require_field(entry, "log_file", where)
    if log_file_value is None:
        payload["log_file"] = None
        payload["traceback_tail"] = None
    else:
        log_file_str = _require_str(entry, "log_file", where)
        payload["log_file"] = log_file_str
        payload["traceback_tail"] = _read_log_tail(
            ctx.run_dir / log_file_str, ctx.max_log_lines
        )
    if "generated_file" in entry and entry["generated_file"] is not None:
        payload["generated_file"] = str(entry["generated_file"])
    if "codegen_hint" in cluster and cluster["codegen_hint"] is not None:
        payload["codegen_hint"] = cluster["codegen_hint"]
    return payload, node_path


def _cluster_payload(
    ctx: _RunContext,
    cluster: dict[str, object],
    kind: str,
    ids_key: str,
    rep_key: str,
    entries_by_id: dict[int, dict[str, object]],
) -> dict[str, object]:
    """Build the output object for one error/failure cluster."""
    cluster_id = _require_int(cluster, "cluster_id", f"{kind} cluster")
    where = f"{kind} cluster {cluster_id}"

    member_test_ids: list[str] = []
    for raw_id in _require_list(cluster, ids_key, where):
        if isinstance(raw_id, bool) or not isinstance(raw_id, int):
            raise UsageError(
                f"Member id in {where} must be an integer, got {type(raw_id).__name__}."
            )
        if raw_id not in entries_by_id:
            raise UsageError(
                f"Member id {raw_id} of {where} has no matching entry in the index's "
                f"{kind}s list. The index.json is inconsistent; re-run the test suite."
            )
        member = entries_by_id[raw_id]
        if "test_id" in member:
            member_test_ids.append(_require_str(member, "test_id", where))
        else:
            # Deploy-test infrastructure errors have no test_id; identify the
            # member by its phase and id instead.
            member_test_ids.append(f"{_require_str(member, 'phase', where)}#{raw_id}")

    rep_id = _require_int(cluster, rep_key, where)
    if rep_id not in entries_by_id:
        raise UsageError(
            f"Representative id {rep_id} of {where} has no matching entry in the "
            f"index's {kind}s list. The index.json is inconsistent; re-run the test suite."
        )
    representative, node_path = _representative_payload(
        ctx, cluster, entries_by_id[rep_id], where
    )

    # Package schema carries source_location on the cluster; the
    # generated-project schemas carry generated_file instead (surfaced on
    # the representative above), so source_location is null there.
    source_location = (
        str(cluster["source_location"]) if "source_location" in cluster else None
    )

    payload: dict[str, object] = {
        "cluster_id": cluster_id,
        "kind": kind,
        "pattern": _require_str(cluster, "pattern", where),
        "count": _require_int(cluster, "count", where),
        "source_location": source_location,
        "member_test_ids": member_test_ids,
        "representative": representative,
    }
    # Deploy-test clusters carry phase / failure_type / services_affected.
    for optional_key in ("phase", "failure_type", "services_affected"):
        if optional_key in cluster and cluster[optional_key] is not None:
            payload[optional_key] = cluster[optional_key]
    # The re-run command targets PACKAGE tests only: emit a test_command solely
    # for runs whose project is a real package directory in the workspace.
    # Generated-project runs (unit or deploy) are re-run via run-complete.ps1.
    if node_path is not None and (ctx.workspace / ctx.project).is_dir():
        test_command = _build_test_command(ctx, node_path)
        if test_command is not None:
            payload["test_command"] = test_command
    return payload


def _resolve_member_keys(
    cluster: dict[str, object],
    kind: str,
    accepted_keys: tuple[tuple[str, str], ...],
    where: str,
) -> tuple[str, str]:
    """Pick the (member-ids, representative-id) key pair this cluster actually uses.

    Args:
        cluster: One cluster object read from the index.
        kind: "error" or "failure" - used only in the error message.
        accepted_keys: Candidate (ids_key, rep_key) pairs, most-specific first.
        where: Index path, for the error message.

    Returns:
        The first candidate pair whose ids_key is present on *cluster*.

    Raises:
        UsageError: The cluster carries none of the accepted spellings.
    """
    for ids_key, rep_key in accepted_keys:
        if ids_key in cluster:
            return ids_key, rep_key
    spellings = ", ".join(f"'{ids_key}'" for ids_key, _ in accepted_keys)
    raise UsageError(
        f"A {kind} cluster in {where} carries none of the accepted member-id keys "
        f"({spellings}). Expected one of the structured index.json schemas "
        f"(schema_version 1) produced by the test runner; re-run the test suite "
        f"to regenerate the run directory."
    )


def _build_clusters(ctx: _RunContext, index: dict[str, object]) -> list[dict[str, object]]:
    """Build output objects for every error cluster, then every failure cluster."""
    where = str(ctx.run_dir / _INDEX_JSON_NAME)
    by_kind = {
        "failure": _entries_by_id(_require_list(index, "failures", where), "failures", where),
        "error": _entries_by_id(_require_list(index, "errors", where), "errors", where),
    }
    clusters: list[dict[str, object]] = []
    for kind, clusters_key, accepted_keys in _CLUSTER_KINDS:
        for item in _require_list(index, clusters_key, where):
            cluster = _as_dict(item, f"'{clusters_key}' entry", where)
            ids_key, rep_key = _resolve_member_keys(cluster, kind, accepted_keys, where)
            clusters.append(
                _cluster_payload(ctx, cluster, kind, ids_key, rep_key, by_kind[kind])
            )
    return clusters


# ---------------------------------------------------------------------------
# Top-level assembly
# ---------------------------------------------------------------------------


def _extract_counts(index: dict[str, object], where: str) -> tuple[dict[str, int], int, int]:
    """Validate counts and return (counts, error_count, failed_count)."""
    counts_obj = _require_field(index, "counts", where)
    if counts_obj is None:
        raise UsageError(
            f"The run at {where} is INCOMPLETE (counts is null) - no JUnit XML was "
            f"produced. Re-run the test suite to produce a complete run directory."
        )
    counts_dict = _as_dict(counts_obj, "counts", where)
    counts: dict[str, int] = {}
    for key, value in counts_dict.items():
        if isinstance(value, bool) or not isinstance(value, int):
            raise UsageError(
                f"counts['{key}'] in {where} must be an integer, "
                f"got {type(value).__name__}."
            )
        counts[key] = value
    # structured_log_writer uses "error" (singular); generated_test_log_writer
    # uses "errors" (plural) - accept both schemas explicitly.
    if "error" in counts:
        error_count = counts["error"]
    elif "errors" in counts:
        error_count = counts["errors"]
    else:
        raise UsageError(
            f"counts in {where} has neither 'error' nor 'errors'. Expected one of the "
            f"two structured index schemas; re-run the test suite."
        )
    if "failed" not in counts:
        raise UsageError(
            f"counts in {where} has no 'failed' key. Expected the structured index "
            f"schema; re-run the test suite."
        )
    return counts, error_count, counts["failed"]


def _sum_service_counts(index: dict[str, object], where: str) -> dict[str, int]:
    """Sum per-service counts (deploy-test schema, which has no top-level counts)."""
    totals: dict[str, int] = {}
    for item in _require_list(index, "services", where):
        service = _as_dict(item, "'services' entry", where)
        service_counts = _as_dict(
            _require_field(service, "counts", where), "service counts", where
        )
        for key, value in service_counts.items():
            if isinstance(value, bool) or not isinstance(value, int):
                raise UsageError(
                    f"Service counts['{key}'] in {where} must be an integer, "
                    f"got {type(value).__name__}."
                )
            totals[key] = totals.get(key, 0) + value
    return totals


def _warnings_section_present(run_dir: Path) -> bool:
    """True if the run's full.log contains a pytest warnings-summary marker."""
    full_log = run_dir / _FULL_LOG_NAME
    if not full_log.is_file():
        logger.debug("no full.log in run dir %s; warnings_section_present=False", run_dir)
        return False
    for line in full_log.read_text(encoding="utf-8", errors="replace").splitlines():
        if _WARNINGS_HEADER.match(line):
            return True
    return False


# ---------------------------------------------------------------------------
# Self-test: schema-shape coverage
#
# The collector's whole job is reading indexes written by THREE different
# writers, and each writer's key spellings are a fact this module restates. A
# spelling this module does not accept makes it reject a run directory it
# documents support for - which is how a generated-project unit run once failed
# here with "Missing required key 'failure_ids'". These fixtures pin one
# minimal index per writer shape so that class of drift fails here, in a
# one-second check, instead of at an agent's first read of a real run.
# ---------------------------------------------------------------------------

#: (name, index dict, expected cluster count, expected representative "file")
#: One entry per writer shape the module claims to support.
_SELF_TEST_INDEXES: tuple[tuple[str, dict[str, object], int, str | None], ...] = (
    (
        "package (structured_log_writer): failure_ids + dotted python test id",
        {
            "project": "datrix-common",
            "result": "FAILED",
            "counts": {"passed": 1, "failed": 1, "error": 0, "skipped": 0},
            "failures": [
                {
                    "id": 1,
                    "test_id": "tests.unit.test_foo.TestBar::test_baz",
                    "error_type": "AssertionError",
                    "error_message": "assert 1 == 2",
                    "log_file": "failures/001.txt",
                }
            ],
            "errors": [],
            "failure_clusters": [
                {
                    "cluster_id": 1,
                    "pattern": "assert * == *",
                    "count": 1,
                    "failure_ids": [1],
                    "representative_failure_id": 1,
                }
            ],
            "error_clusters": [],
        },
        1,
        "tests/unit/test_foo.py",
    ),
    (
        "generated-project unit (generated_test_log_writer): error_ids in "
        "failure_clusters + all-capitalized xUnit test id",
        {
            "project": "dotnet\\local\\example",
            "result": "FAILED",
            "counts": {"passed": 1, "failed": 1, "errors": 0, "skipped": 0},
            "failures": [
                {
                    "id": 1,
                    "service": "svc",
                    "test_id": "Svc.Tests.ThingTests::Does_Thing",
                    "error_type": "Failed",
                    "error_message": "System.InvalidOperationException : boom",
                    "generated_file": "src/Svc/Thing.cs",
                    "log_file": "failures/001.txt",
                }
            ],
            "errors": [],
            "failure_clusters": [
                {
                    "cluster_id": 1,
                    "pattern": "Failed: System.InvalidOperationException : *",
                    "count": 1,
                    "services_affected": ["svc"],
                    "error_ids": [1],
                    "representative_error_id": 1,
                    "codegen_hint": None,
                }
            ],
            "error_clusters": [],
        },
        1,
        None,
    ),
    (
        "deploy-test (deploy_test_log_writer): failed_phase + phase-keyed infra "
        "error with no test_id and log_file: null",
        {
            "project": "python\\local\\example",
            "result": "FAILED",
            "failed_phase": "docker-up",
            "services": [{"name": "svc", "counts": {"passed": 0, "failed": 0}}],
            "failures": [],
            "errors": [
                {
                    "id": 1,
                    "phase": "docker-up",
                    "error_type": "ContainerStartError",
                    "error_message": "container exited",
                    "log_file": None,
                }
            ],
            "failure_clusters": [],
            "error_clusters": [
                {
                    "cluster_id": 1,
                    "pattern": "container exited",
                    "count": 1,
                    "phase": "docker-up",
                    "error_ids": [1],
                    "representative_error_id": 1,
                }
            ],
        },
        1,
        None,
    ),
)


#: (case name, package-marker files to create, representative node path,
#: substrings the command must contain, substrings it must NOT contain).
#: An empty marker tuple means a package directory carrying no suite at all,
#: for which no command may be emitted.
_SELF_TEST_COMMAND_CASES: tuple[
    tuple[str, tuple[str, ...], str, tuple[str, ...], tuple[str, ...]], ...
] = (
    (
        "pytest package: node ID re-run via test-single.ps1",
        ("tests/",),
        "tests/unit/test_foo.py::TestBar::test_baz",
        (
            "test-single.ps1",
            '"tests/unit/test_foo.py::TestBar::test_baz"',
            "-Project ",
        ),
        ("-Specific",),
    ),
    (
        "node package: file re-run via test.ps1 -Specific",
        (NODE_MANIFEST_NAME,),
        "src/test/serverResolution.test.ts::D:/pkg/out/test/serverResolution.test.js",
        ('-Specific "src/test/serverResolution.test.ts"',),
        ("test-single.ps1", ".js"),
    ),
)


def _write_suite_markers(package_dir: Path, markers: tuple[str, ...]) -> None:
    """Create the on-disk markers that make a fixture package's suite detectable.

    Args:
        package_dir: Fixture package root to create.
        markers: Marker names - a trailing ``/`` means a directory, and the Node
            manifest name means a manifest declaring a test script. The manifest
            is spelled from ``package_suites``' own constants so the fixture
            cannot drift from what detection actually looks for.

    Raises:
        ValueError: If a marker is neither of those - a fixture nobody can
            interpret would silently prove nothing.
    """
    package_dir.mkdir(parents=True, exist_ok=True)
    for marker in markers:
        if marker.endswith("/"):
            (package_dir / marker.rstrip("/")).mkdir(parents=True, exist_ok=True)
        elif marker == NODE_MANIFEST_NAME:
            (package_dir / marker).write_text(
                json.dumps({"scripts": {NODE_TEST_SCRIPT_KEY: "node --test"}}),
                encoding="utf-8",
            )
        else:
            raise ValueError(
                f"Unrecognized suite marker {marker!r}. Expected a directory "
                f"name ending in '/' or {NODE_MANIFEST_NAME!r}."
            )


def _run_command_shape_self_test() -> int:
    """Check the emitted re-run command matches the suite the package carries.

    A package's runner is a fact about its tree, and this module restates it.
    Handing a Node package a pytest ``test-single.ps1`` invocation produces a
    command that cannot run, which is worse than emitting none - so both shapes
    are pinned here, each asserted to EXCLUDE the other's marker.

    Returns:
        Number of failing cases; 0 when every shape is correct.
    """
    import tempfile

    failures = 0
    for name, markers, node_path, expected, forbidden in _SELF_TEST_COMMAND_CASES:
        with tempfile.TemporaryDirectory() as raw_dir:
            workspace = Path(raw_dir)
            project = "datrix-fixture"
            _write_suite_markers(workspace / project, markers)
            ctx = _RunContext(
                run_dir=workspace,
                workspace=workspace,
                project=project,
                max_log_lines=_DEFAULT_MAX_LOG_LINES,
            )
            command = _build_test_command(ctx, node_path)
        if command is None:
            print(f"[FAIL] {name}: no command emitted")
            failures += 1
            continue
        missing = [part for part in expected if part not in command]
        present = [part for part in forbidden if part in command]
        if missing or present:
            print(
                f"[FAIL] {name}: command {command!r} missing {missing} / "
                f"carries forbidden {present}"
            )
            failures += 1
            continue
        print(f"[OK] {name}")

    # Non-vacuity: a package directory carrying NO suite must yield no command,
    # or the two acceptances above would prove nothing about the detection.
    with tempfile.TemporaryDirectory() as raw_dir:
        workspace = Path(raw_dir)
        _write_suite_markers(workspace / "datrix-fixture", ())
        ctx = _RunContext(
            run_dir=workspace,
            workspace=workspace,
            project="datrix-fixture",
            max_log_lines=_DEFAULT_MAX_LOG_LINES,
        )
        if _build_test_command(ctx, "tests/test_foo.py") is None:
            print("[OK] a package with no test suite yields no command (non-vacuity)")
        else:
            print("[FAIL] a package with no test suite still produced a command")
            failures += 1
    return failures


def _run_self_test() -> int:
    """Parse one minimal index per supported writer shape; report OK/FAIL per case.

    Also runs the re-run-command shape cases, which pin the invocation emitted
    for each kind of test suite a package can carry.

    Returns:
        `_EXIT_OK` when every shape parses and yields the expected clusters,
        `_EXIT_USAGE` when any shape fails (including the deliberate
        unknown-spelling case, which MUST be rejected).
    """
    import tempfile

    failures = 0
    for name, index, expected_clusters, expected_file in _SELF_TEST_INDEXES:
        with tempfile.TemporaryDirectory() as raw_dir:
            run_dir = Path(raw_dir)
            (run_dir / "failures").mkdir()
            (run_dir / "failures" / "001.txt").write_text("detail\n", encoding="utf-8")
            ctx = _RunContext(
                run_dir=run_dir,
                workspace=run_dir,
                project=str(index["project"]),
                max_log_lines=_DEFAULT_MAX_LOG_LINES,
            )
            try:
                clusters = _build_clusters(ctx, index)
            except UsageError as exc:
                print(f"[FAIL] {name}: raised UsageError: {exc}")
                failures += 1
                continue
        if len(clusters) != expected_clusters:
            print(f"[FAIL] {name}: got {len(clusters)} clusters, want {expected_clusters}")
            failures += 1
            continue
        actual_file = clusters[0]["representative"].get("file")  # type: ignore[union-attr]
        if actual_file != expected_file:
            print(f"[FAIL] {name}: representative file {actual_file!r}, want {expected_file!r}")
            failures += 1
            continue
        print(f"[OK] {name}")

    # Non-vacuity: a cluster spelling NO writer produces must still be rejected,
    # or the acceptance above would prove nothing about the guard's existence.
    unknown = {
        "project": "p",
        "failures": [],
        "errors": [],
        "error_clusters": [],
        "failure_clusters": [
            {"cluster_id": 1, "pattern": "x", "count": 1, "member_ids": [1]}
        ],
    }
    with tempfile.TemporaryDirectory() as raw_dir:
        ctx = _RunContext(
            run_dir=Path(raw_dir), workspace=Path(raw_dir), project="p",
            max_log_lines=_DEFAULT_MAX_LOG_LINES,
        )
        try:
            _build_clusters(ctx, unknown)
        except UsageError:
            print("[OK] unknown member-id spelling is rejected (non-vacuity)")
        else:
            print("[FAIL] unknown member-id spelling was ACCEPTED - the guard is vacuous")
            failures += 1

    failures += _run_command_shape_self_test()

    if failures:
        print(f"SELF-TEST FAILED: {failures} case(s)")
        return _EXIT_USAGE
    total_cases = len(_SELF_TEST_INDEXES) + len(_SELF_TEST_COMMAND_CASES) + 2
    print(f"SELF-TEST PASSED: {total_cases} case(s)")
    return _EXIT_OK


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect per-cluster failure data from a structured test-results run."
    )
    parser.add_argument(
        "path",
        nargs="?",
        help="Run directory or index.json path (alternative to --project)",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Parse one fixture index per supported writer schema and exit",
    )
    parser.add_argument(
        "--project",
        help="Project name; auto-locates the newest test-results-* run directory",
    )
    parser.add_argument(
        "--max-log-lines",
        type=int,
        default=_DEFAULT_MAX_LOG_LINES,
        help=f"Tail lines of each representative log to embed (default {_DEFAULT_MAX_LOG_LINES})",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    return parser.parse_args()


def _configure_logging(debug: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        return _run_self_test()
    if bool(args.path) == bool(args.project):
        raise UsageError(
            "Provide exactly one input: either a positional PATH (run directory or "
            "index.json) or --project <name>."
        )
    workspace = get_datrix_root()
    if args.project:
        run_dir = _resolve_run_dir_from_project(workspace, args.project)
    else:
        run_dir = _resolve_run_dir_from_path(args.path)
    if args.max_log_lines < 1:
        raise UsageError(
            f"--max-log-lines must be a positive integer, got {args.max_log_lines}."
        )

    index_path = run_dir / _INDEX_JSON_NAME
    index = _load_index(index_path)
    where = str(index_path)
    project = _require_str(index, "project", where)
    result = _require_str(index, "result", where)
    if "counts" in index:
        counts, error_count, failed_count = _extract_counts(index, where)
    elif "failed_phase" in index:
        # Deploy-test schema: no top-level counts. Totals for the console come
        # from the failure/error arrays; per-service counts are summed for reference.
        counts = _sum_service_counts(index, where)
        error_count = len(_require_list(index, "errors", where))
        failed_count = len(_require_list(index, "failures", where))
    else:
        raise UsageError(
            f"index.json at {where} has neither 'counts' (package / generated-unit "
            f"schema) nor 'failed_phase' (deploy-test schema). Unrecognized index "
            f"schema; re-run the test suite to regenerate the run directory."
        )

    ctx = _RunContext(
        run_dir=run_dir,
        workspace=workspace,
        project=project,
        max_log_lines=args.max_log_lines,
    )
    clusters = _build_clusters(ctx, index)

    payload: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "run_dir": str(run_dir),
        "project": project,
        "result": result,
        "counts": counts,
        "total_clusters": len(clusters),
        "warnings_section_present": _warnings_section_present(run_dir),
        "max_log_lines": args.max_log_lines,
        "clusters": clusters,
    }
    if "failed_phase" in index:
        payload["failed_phase"] = index["failed_phase"]
    output_path = run_dir / _OUTPUT_FILENAME
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print(f"{error_count} errors, {failed_count} failures in {len(clusters)} clusters")
    print(f"Details: {output_path}")
    return _EXIT_OK


def main() -> int:
    """Entry point."""
    args = _parse_args()
    _configure_logging(args.debug)
    try:
        return _run(args)
    except UsageError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return _EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
