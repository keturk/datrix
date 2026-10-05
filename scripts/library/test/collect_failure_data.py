#!/usr/bin/env python3
"""Collect per-cluster failure data from a structured test-results run.

Reads a run directory's index.json, resolves the representative entry of
every error cluster and failure cluster, embeds the tail of its detail log,
and writes ``failure-data.json`` into the run directory.

The bundle is what an agent reads first, so it is kept small without losing
anything: clusters sharing one normalized pattern form a *family* and only the
family's first cluster carries a traceback tail; an error message longer than
the cap is cut with a pointer to its ``log_file``, which holds it whole. Each of
the first ``--llm-hint-limit`` families then gets an advisory hint from a local
model (``shared.local_llm``) that is given the traceback, the message and the
source around the traceback's in-workspace frames -- the code an agent would
otherwise open first. Every prompt line carrying a registered customer term is
withheld before it is sent, and without the term corpus no hint is requested at all.
A hint is a hypothesis to verify, never a verdict.

Supports all three
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
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
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

from dev.customer_domain_isolation import TermCorpus  # noqa: E402
from shared.local_llm import (  # noqa: E402
    ADVISORY_UNAVAILABLE_SOURCE,
    ChatRequest,
    LocalLlmPool,
    LocalLlmSettings,
    LocalLlmUnavailable,
    add_local_llm_arguments,
    local_llm_settings,
)
from shared.local_reading import (  # noqa: E402
    ReadScopeError,
    load_workspace_term_corpus,
    withhold_customer_lines,
)
from shared.package_suites import (  # noqa: E402
    NODE_MANIFEST_NAME,
    NODE_TEST_SCRIPT_KEY,
    SuiteKind,
    detect_suite_kind,
)
from shared.venv import get_datrix_root  # noqa: E402

from test.status_tests import parse_timestamp_from_log_file  # noqa: E402

logger = logging.getLogger(__name__)

# 2: families, hints, capped error messages.
_SCHEMA_VERSION = 2
_OUTPUT_FILENAME = "failure-data.json"
_INDEX_JSON_NAME = "index.json"
_FULL_LOG_NAME = "full.log"
_RUN_DIR_PREFIX = "test-results-"
_DEFAULT_MAX_LOG_LINES = 60
_EXIT_OK = 0
_EXIT_USAGE = 2

# An error message is also written whole to the entry's log_file, so the bundle
# carries only its head. One semantic-baseline assertion once put 36 KB -- a
# quarter of a 16-cluster bundle -- into this one field.
_MAX_MESSAGE_LINES = 20
_MAX_MESSAGE_CHARS = 2000

# Advisory hints: how many families get one (the fix playbooks split a session
# past five clusters, so a sixth hint would not be read in this session), how
# many requests run at once, and the size of each answer.
_DEFAULT_LLM_HINT_LIMIT = 5
_LLM_HINT_WORKERS = 4
_LLM_HINT_MAX_TOKENS = 300
_LLM_HINT_TEMPERATURE = 0.1
_LLM_HINT_TIMEOUT_MS = 120000
# The hint source of a family past the hint limit: no model was asked.
HINT_SKIPPED_SOURCE = "skipped"

# Source given to the hint model per family: this many in-workspace traceback
# frames (deepest first), each with this many lines either side of the frame.
_HINT_MAX_FRAMES = 3
_HINT_CONTEXT_LINES = 12
_HINT_TAIL_LINES = 40

# Traceback frame shapes: CPython's long form and pytest's short "path:line:" form.
_PY_FRAME = re.compile(r'File "(?P<path>[^"]+)", line (?P<line>\d+)')
_PYTEST_FRAME = re.compile(r"^(?P<path>[\w./\\:-]+\.py):(?P<line>\d+):", re.MULTILINE)
# Path segments that mark third-party code, never a defect site to show.
_THIRD_PARTY_SEGMENTS = frozenset({"site-packages", ".venv", "lib"})

_HINT_SYSTEM_PROMPT = (
    "You triage one family of test failures in the Datrix code generator. Use ONLY the "
    "error message, traceback and source excerpts given. Answer in at most 80 words, "
    "plain text, no code: (1) the most likely defect site as file:line taken from the "
    "excerpts, or 'undetermined' if the evidence does not point to one; (2) the probable "
    "cause in one sentence; (3) the first thing to check. Never invent a file or line."
)

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
            f"index.json schema (schema_version 1 or 2) produced by the test runner; "
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


def resolve_run_dir_from_path(raw_path: str) -> Path:
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


def _cap_message(message: str) -> tuple[str, bool]:
    """Keep a message's head; say how much was cut and where the whole of it is.

    Returns (message, truncated). The entry's log_file carries the full message, so
    the cut loses nothing an agent cannot read on demand.
    """
    lines = message.splitlines()
    if len(lines) <= _MAX_MESSAGE_LINES and len(message) <= _MAX_MESSAGE_CHARS:
        return message, False
    head = "\n".join(lines[:_MAX_MESSAGE_LINES])[:_MAX_MESSAGE_CHARS]
    kept_lines = head.count("\n") + 1
    omitted = max(len(lines) - kept_lines, 0)
    return (
        f"{head}\n... [message cut: {omitted} more line(s), {len(message) - len(head)} more "
        f"character(s) -- the whole message is in this entry's log_file]",
        True,
    )


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
    message, truncated = _cap_message(_require_str(entry, "error_message", where))
    payload["error_message"] = message
    if truncated:
        payload["error_message_truncated"] = True
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
        f"(schema_version 1 or 2) produced by the test runner; re-run the test suite "
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
# Families: clusters one normalized pattern produced
# ---------------------------------------------------------------------------


@dataclass
class _Family:
    """Clusters sharing one (kind, normalized pattern), and the hint written for them."""

    family_id: int
    kind: str
    pattern: str
    head: dict[str, object]
    head_representative: dict[str, object]
    cluster_ids: list[int]
    test_count: int
    hint: dict[str, str]

    def to_json(self) -> dict[str, object]:
        return {
            "family_id": self.family_id,
            "kind": self.kind,
            "pattern": self.pattern,
            "cluster_ids": self.cluster_ids,
            "test_count": self.test_count,
            "hint": self.hint,
        }


def _representative_of(cluster: dict[str, object]) -> dict[str, object]:
    representative = cluster["representative"]
    if not isinstance(representative, dict):
        raise TypeError(f"cluster {cluster['cluster_id']} representative is not an object")
    return representative


def _group_families(clusters: list[dict[str, object]]) -> list[_Family]:
    """Group clusters by (kind, pattern); give every cluster its family_id.

    The index writers cluster by pattern AND source location, so one assertion
    raised from five tests is five clusters with five near-identical tails. Only
    the family's first cluster keeps its tail; the others name that cluster in
    ``traceback_tail_in_cluster`` and keep their own ``log_file``.

    Returns the families in first-seen order (errors first, as the clusters are).
    """
    families: dict[tuple[str, str], _Family] = {}
    for cluster in clusters:
        key = (str(cluster["kind"]), str(cluster["pattern"]))
        cluster_id = int(str(cluster["cluster_id"]))
        count = int(str(cluster["count"]))
        if key not in families:
            families[key] = _Family(
                family_id=len(families) + 1,
                kind=key[0],
                pattern=key[1],
                head=cluster,
                head_representative=_representative_of(cluster),
                cluster_ids=[],
                test_count=0,
                hint={"source": HINT_SKIPPED_SOURCE, "text": "not requested"},
            )
        family = families[key]
        cluster["family_id"] = family.family_id
        family.cluster_ids.append(cluster_id)
        family.test_count += count
        representative = _representative_of(cluster)
        if family.head is not cluster and representative["traceback_tail"] is not None:
            representative["traceback_tail"] = None
            representative["traceback_tail_in_cluster"] = family.head["cluster_id"]
    return list(families.values())


def _frame_paths(tail: str, ctx: _RunContext) -> list[tuple[Path, int]]:
    """In-workspace (file, line) frames named in a traceback, deepest first, deduplicated.

    A relative path resolves against the project root. A frame outside the
    workspace, in third-party code, or naming a file that is not there is skipped:
    the hint model is shown only source that exists in this tree.
    """
    workspace = ctx.workspace.resolve()
    frames: list[tuple[Path, int]] = []
    matches = [*_PY_FRAME.finditer(tail), *_PYTEST_FRAME.finditer(tail)]
    for match in sorted(matches, key=lambda m: m.start(), reverse=True):
        raw = Path(match.group("path"))
        path = (raw if raw.is_absolute() else ctx.workspace / ctx.project / raw).resolve()
        if not path.is_relative_to(workspace) or not path.is_file():
            continue
        if _THIRD_PARTY_SEGMENTS & {part.lower() for part in path.relative_to(workspace).parts}:
            continue
        frame = (path, int(match.group("line")))
        if frame not in frames:
            frames.append(frame)
        if len(frames) == _HINT_MAX_FRAMES:
            break
    return frames


def _source_excerpt(path: Path, line: int, workspace: Path) -> str:
    """Numbered lines around ``line``, headed by the workspace-relative path."""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    start = max(line - 1 - _HINT_CONTEXT_LINES, 0)
    end = min(line + _HINT_CONTEXT_LINES, len(lines))
    rel = path.relative_to(workspace.resolve()).as_posix()
    body = "\n".join(
        f"{number:>5}{'>' if number == line else ' '} {text}"
        for number, text in enumerate(lines[start:end], start=start + 1)
    )
    return f"--- {rel}:{line}\n{body}"


def _hint_prompt(family: _Family, ctx: _RunContext) -> str:
    """The user prompt for one family: what failed, where, and the code around it."""
    representative = family.head_representative
    tail = str(representative["traceback_tail"] or "")
    tail_lines = tail.splitlines()[-_HINT_TAIL_LINES:]
    excerpts = [_source_excerpt(path, line, ctx.workspace) for path, line in _frame_paths(tail, ctx)]
    return "\n".join([
        f"Project: {ctx.project}",
        f"Family pattern ({family.test_count} test(s) in {len(family.cluster_ids)} cluster(s)): "
        f"{family.pattern}",
        f"Representative test: {representative.get('test_id')}",
        f"Test location: {family.head['source_location']}",
        "",
        "Error message:",
        str(representative["error_message"]),
        "",
        f"Traceback (last {len(tail_lines)} lines):",
        *tail_lines,
        "",
        "Source excerpts (deepest frame first; '>' marks the frame line):",
        *(excerpts or ["(no in-workspace frame found in the traceback)"]),
    ])


def _hint_for(family: _Family, ctx: _RunContext, pool: LocalLlmPool, corpus: TermCorpus) -> dict[str, str]:
    """One family's hint, or a hint saying no local server could answer.

    Every prompt line carrying a registered customer term is withheld before it is sent.
    """
    lines, _withheld = withhold_customer_lines(_hint_prompt(family, ctx), corpus)
    try:
        reply = pool.chat(ChatRequest(
            system=_HINT_SYSTEM_PROMPT,
            user="\n".join(lines),
            temperature=_LLM_HINT_TEMPERATURE,
            max_tokens=_LLM_HINT_MAX_TOKENS,
        ))
    except LocalLlmUnavailable as exc:
        return {"source": ADVISORY_UNAVAILABLE_SOURCE, "text": str(exc)}
    return {"source": reply.host.label(), "text": reply.text}


def _attach_hints(
    families: list[_Family],
    ctx: _RunContext,
    settings: LocalLlmSettings | None,
    limit: int,
    report: Callable[[str], None] | None = None,
) -> str:
    """Give the first ``limit`` families an advisory hint; return a one-line status.

    ``settings`` None means hints were switched off. Families past the limit, and
    any family no local server could answer for, carry a hint whose ``source`` says
    why it has no model text -- a missing hint is never silent. ``report`` receives
    the pool's server-discovery lines; None prints them to stderr.
    """
    if settings is None or limit == 0 or not families:
        return "hints: off"
    wanted = families[:limit]
    try:
        corpus = load_workspace_term_corpus(ctx.workspace)
    except ReadScopeError as exc:
        for family in wanted:
            family.hint = {"source": ADVISORY_UNAVAILABLE_SOURCE, "text": str(exc)}
        return "hints: withheld (no customer-term corpus to filter the prompts)"
    pool = LocalLlmPool(settings) if report is None else LocalLlmPool(settings, report=report)
    with ThreadPoolExecutor(max_workers=_LLM_HINT_WORKERS) as executor:
        hints = list(executor.map(lambda family: _hint_for(family, ctx, pool, corpus), wanted))
    for family, hint in zip(wanted, hints):
        family.hint = hint
    answered = sorted({hint["source"] for hint in hints if hint["source"] != ADVISORY_UNAVAILABLE_SOURCE})
    if not answered:
        return "hints: unavailable (no local model server answered)"
    unanswered = sum(1 for hint in hints if hint["source"] == ADVISORY_UNAVAILABLE_SOURCE)
    suffix = f", {unanswered} unavailable" if unanswered else ""
    return f"hints: {len(wanted) - unanswered} of {len(families)} famil(ies) from {'; '.join(answered)}{suffix}"


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
        "failure_clusters + a non-python test id",
        {
            "project": "typescript\\local\\example",
            "result": "FAILED",
            "counts": {"passed": 1, "failed": 1, "errors": 0, "skipped": 0},
            "failures": [
                {
                    "id": 1,
                    "service": "svc",
                    "test_id": "ThingService::does thing",
                    "error_type": "Failed",
                    "error_message": "Error: boom",
                    "generated_file": "src/svc/thing.service.ts",
                    "log_file": "failures/001.txt",
                }
            ],
            "errors": [],
            "failure_clusters": [
                {
                    "cluster_id": 1,
                    "pattern": "Failed: Error: *",
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


def _self_test_cluster(cluster_id: int, kind: str, pattern: str, tail: str) -> dict[str, object]:
    return {
        "cluster_id": cluster_id,
        "kind": kind,
        "pattern": pattern,
        "count": 1,
        "source_location": "tests/test_x.py:1",
        "representative": {"test_id": f"t{cluster_id}", "error_message": "m", "traceback_tail": tail},
    }


def _check_message_cap() -> list[str]:
    problems: list[str] = []
    short = "line one\nline two\n"
    if _cap_message(short) != (short, False):
        problems.append("a message within the caps was altered")
    long_message = "\n".join(f"diff line {n}" for n in range(300))
    capped, truncated = _cap_message(long_message)
    if not truncated or len(capped.splitlines()) != _MAX_MESSAGE_LINES + 1 or "log_file" not in capped:
        problems.append("a 300-line message was not cut to the line cap with a log_file pointer")
    wide, wide_truncated = _cap_message("x" * (_MAX_MESSAGE_CHARS * 3))
    if not wide_truncated or len(wide.splitlines()[0]) != _MAX_MESSAGE_CHARS:
        problems.append("a one-line message over the character cap was not cut")
    return problems


def _check_families() -> list[str]:
    problems: list[str] = []
    clusters = [
        _self_test_cluster(1, "failure", "drifted *", "tail one"),
        _self_test_cluster(2, "failure", "other *", "tail two"),
        _self_test_cluster(3, "failure", "drifted *", "tail three"),
        _self_test_cluster(4, "error", "drifted *", "tail four"),
    ]
    families = _group_families(clusters)
    if [(f.kind, f.cluster_ids) for f in families] != [("failure", [1, 3]), ("failure", [2]), ("error", [4])]:
        problems.append(f"families grouped wrongly: {[(f.kind, f.cluster_ids) for f in families]}")
    third = _representative_of(clusters[2])
    if third["traceback_tail"] is not None or third.get("traceback_tail_in_cluster") != 1:
        problems.append("a family's second cluster kept its tail or does not point at the head cluster")
    if _representative_of(clusters[0])["traceback_tail"] != "tail one":
        problems.append("a family's head cluster lost its tail")
    if [c["family_id"] for c in clusters] != [1, 2, 1, 3]:
        problems.append(f"family_id not stamped on clusters: {[c['family_id'] for c in clusters]}")
    return problems


def _check_frame_paths() -> list[str]:
    import tempfile

    problems: list[str] = []
    with tempfile.TemporaryDirectory() as raw_dir:
        workspace = Path(raw_dir)
        module = workspace / "datrix-fixture" / "src" / "mod.py"
        module.parent.mkdir(parents=True)
        module.write_text("\n".join(f"value_{n} = {n}" for n in range(1, 41)) + "\n", encoding="utf-8")
        vendored = workspace / ".venv" / "Lib" / "site-packages" / "pkg.py"
        vendored.parent.mkdir(parents=True)
        vendored.write_text("x = 1\n", encoding="utf-8")
        ctx = _RunContext(run_dir=workspace, workspace=workspace, project="datrix-fixture",
                          max_log_lines=_DEFAULT_MAX_LOG_LINES)
        tail = "\n".join([
            f'  File "{vendored}", line 1, in call',
            '  File "C:\\\\elsewhere\\\\outside.py", line 9, in far',
            "src/mod.py:20: AssertionError",
        ])
        frames = _frame_paths(tail, ctx)
        if frames != [(module.resolve(), 20)]:
            problems.append(f"frames should be only the in-workspace, non-vendored one; got {frames}")
        excerpt = _source_excerpt(module.resolve(), 20, workspace)
        if "datrix-fixture/src/mod.py:20" not in excerpt or "   20> value_20 = 20" not in excerpt:
            problems.append(f"excerpt lacks the relative header or the marked frame line:\n{excerpt}")
    return problems


def _check_hints_without_a_server() -> list[str]:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        closed = int(sock.getsockname()[1])
    settings = LocalLlmSettings(machines=("127.0.0.1",), reachable_timeout_ms=1000,
                                ollama_port=closed, openai_ports=(closed,))
    families = _group_families([_self_test_cluster(n, "failure", f"p{n}", "tail") for n in (1, 2)])
    # The real workspace: its customer-term corpus lets the hint reach the (absent) server.
    ctx = _RunContext(run_dir=Path("."), workspace=get_datrix_root(), project="p", max_log_lines=1)
    status = _attach_hints(families, ctx, settings, limit=1)
    problems: list[str] = []
    if "unavailable" not in status:
        problems.append(f"status must say hints were unavailable, got {status!r}")
    if families[0].hint["source"] != ADVISORY_UNAVAILABLE_SOURCE or "--local-machine" not in families[0].hint["text"]:
        problems.append(f"the requested family's hint must say why it is missing: {families[0].hint}")
    if families[1].hint["source"] != HINT_SKIPPED_SOURCE:
        problems.append(f"a family past the limit must be marked skipped: {families[1].hint}")
    if _attach_hints(families, ctx, None, limit=5) != "hints: off":
        problems.append("hints switched off must report 'hints: off'")
    return problems


def _check_no_corpus_means_no_hint_request() -> list[str]:
    import tempfile

    families = _group_families([_self_test_cluster(1, "failure", "p1", "tail")])
    with tempfile.TemporaryDirectory(prefix="failure-data-") as temp:
        ctx = _RunContext(run_dir=Path(temp), workspace=Path(temp), project="p", max_log_lines=1)
        # Every machine is unreachable on purpose: a request would show as a server error, not a corpus one.
        status = _attach_hints(families, ctx, LocalLlmSettings(machines=("127.0.0.1",), openai_ports=()), limit=1)
    problems: list[str] = []
    if not status.startswith("hints: withheld"):
        problems.append(f"status must say the hints were withheld, got {status!r}")
    if "customer-term corpus" not in families[0].hint["text"]:
        problems.append(f"the hint must say the corpus is missing: {families[0].hint}")
    return problems


#: (name, check) -- each returns the problems it found; empty means OK.
_SELF_TEST_BUNDLE_CHECKS: tuple[tuple[str, Callable[[], list[str]]], ...] = (
    ("error messages are capped with a pointer to log_file", _check_message_cap),
    ("clusters sharing a pattern form one family with one tail", _check_families),
    ("hint frames are in-workspace, non-vendored, with marked excerpts", _check_frame_paths),
    ("hints say why they are missing when no server answers", _check_hints_without_a_server),
    ("no customer-term corpus: no hint prompt is sent", _check_no_corpus_means_no_hint_request),
)


def _run_bundle_self_test() -> int:
    """Run the bundle-shape checks; return the number that failed."""
    failures = 0
    for name, check in _SELF_TEST_BUNDLE_CHECKS:
        problems = check()
        if problems:
            print(f"[FAIL] {name}: {'; '.join(problems)}")
            failures += 1
        else:
            print(f"[OK] {name}")
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
    failures += _run_bundle_self_test()

    if failures:
        print(f"SELF-TEST FAILED: {failures} case(s)")
        return _EXIT_USAGE
    total_cases = (
        len(_SELF_TEST_INDEXES) + len(_SELF_TEST_COMMAND_CASES) + len(_SELF_TEST_BUNDLE_CHECKS) + 2
    )
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
    parser.add_argument(
        "--no-llm-hints",
        action="store_true",
        help="Write no advisory local-model hints (families and message caps still apply)",
    )
    parser.add_argument(
        "--llm-hint-limit",
        type=int,
        default=_DEFAULT_LLM_HINT_LIMIT,
        help=f"Families (in order, errors first) that get a hint (default {_DEFAULT_LLM_HINT_LIMIT})",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    add_local_llm_arguments(parser, generate_timeout_ms=_LLM_HINT_TIMEOUT_MS)
    args = parser.parse_args()
    if args.llm_hint_limit < 0:
        parser.error(f"--llm-hint-limit must be 0 or more, got {args.llm_hint_limit}; 0 writes no hints.")
    return args


def _configure_logging(debug: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )


@dataclass(frozen=True)
class FailureData:
    """A written failure-data.json: where it is, what it holds, and its one-line summary."""

    path: Path
    payload: dict[str, object]
    summary: str


def write_failure_data(
    run_dir: Path,
    workspace: Path,
    *,
    settings: LocalLlmSettings | None,
    max_log_lines: int = _DEFAULT_MAX_LOG_LINES,
    hint_limit: int = _DEFAULT_LLM_HINT_LIMIT,
    report: Callable[[str], None] | None = None,
) -> FailureData:
    """Build the failure bundle for ``run_dir``, write it as failure-data.json, and return it.

    ``settings`` None writes no model hints; otherwise the first ``hint_limit``
    families get one (see ``_attach_hints``, which also says what ``report`` receives).
    """
    if max_log_lines < 1:
        raise UsageError(
            f"--max-log-lines must be a positive integer, got {max_log_lines}."
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
        max_log_lines=max_log_lines,
    )
    clusters = _build_clusters(ctx, index)
    families = _group_families(clusters)
    hint_status = _attach_hints(families, ctx, settings, hint_limit, report)

    payload: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "run_dir": str(run_dir),
        "project": project,
        "result": result,
        "counts": counts,
        "total_clusters": len(clusters),
        "warnings_section_present": _warnings_section_present(run_dir),
        "max_log_lines": max_log_lines,
        "total_families": len(families),
        "families": [family.to_json() for family in families],
        "clusters": clusters,
    }
    if "failed_phase" in index:
        payload["failed_phase"] = index["failed_phase"]
    output_path = run_dir / _OUTPUT_FILENAME
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    summary = (
        f"{error_count} errors, {failed_count} failures in {len(clusters)} clusters "
        f"({len(families)} families; {hint_status})"
    )
    return FailureData(path=output_path, payload=payload, summary=summary)


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
        run_dir = resolve_run_dir_from_path(args.path)
    data =write_failure_data(
        run_dir,
        workspace,
        max_log_lines=args.max_log_lines,
        settings=None if args.no_llm_hints else local_llm_settings(args),
        hint_limit=args.llm_hint_limit,
    )
    print(data.summary)
    print(f"Details: {data.path}")
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
