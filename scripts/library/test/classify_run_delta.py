#!/usr/bin/env python3
"""Classify the delta between two structured test-results runs.

Compares the failing sets (failures + errors, keyed by test_id) and the
cluster patterns of a previous and a current run of the same project, and
writes ``run-delta.json`` into the CURRENT run directory.

Verdicts:
  SUCCESS    - every previously failing test is gone and nothing new fails
  PARTIAL    - some previously failing tests fixed, none new
  NO_CHANGE  - the failing set is identical
  REGRESSION - at least one new failing test

Usage:
  python scripts/library/test/classify_run_delta.py --previous <run> --current <run>
  python scripts/library/test/classify_run_delta.py <previous-run> <current-run>
  .\\scripts\\test\\classify-run-delta.ps1 -Previous <run> -Current <run>

Exit codes: 0 = SUCCESS, 1 = PARTIAL/NO_CHANGE/REGRESSION,
2 = usage / input-not-found error.
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# Configure UTF-8 encoding for stdout/stderr on Windows
if sys.platform == "win32" and __name__ == "__main__":
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Add library directory to sys.path to import from shared
_LIBRARY_DIR = Path(__file__).resolve().parent.parent
if _LIBRARY_DIR.exists() and str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

logger = logging.getLogger(__name__)

_SCHEMA_VERSION = 1
_OUTPUT_FILENAME = "run-delta.json"
_INDEX_JSON_NAME = "index.json"
_EXIT_SUCCESS = 0
_EXIT_NOT_SUCCESS = 1
_EXIT_USAGE = 2

_VERDICT_SUCCESS = "SUCCESS"
_VERDICT_PARTIAL = "PARTIAL"
_VERDICT_NO_CHANGE = "NO_CHANGE"
_VERDICT_REGRESSION = "REGRESSION"


class UsageError(Exception):
    """Invalid usage or missing input; the script exits with code 2."""


# ---------------------------------------------------------------------------
# Schema accessors (fail loud on unexpected shapes)
# ---------------------------------------------------------------------------


def _require_field(data: dict[str, object], key: str, where: str) -> object:
    if key not in data:
        raise UsageError(
            f"Missing required key '{key}' in {where}. Expected the structured "
            f"index.json schema (schema_version 1); re-run the test suite."
        )
    return data[key]


def _require_str(data: dict[str, object], key: str, where: str) -> str:
    value = _require_field(data, key, where)
    if not isinstance(value, str):
        raise UsageError(
            f"Key '{key}' in {where} must be a string, got {type(value).__name__}. "
            f"The index.json does not match the expected schema."
        )
    return value


def _require_int(data: dict[str, object], key: str, where: str) -> int:
    value = _require_field(data, key, where)
    if isinstance(value, bool) or not isinstance(value, int):
        raise UsageError(
            f"Key '{key}' in {where} must be an integer, got {type(value).__name__}. "
            f"The index.json does not match the expected schema."
        )
    return value


def _require_list(data: dict[str, object], key: str, where: str) -> list[object]:
    value = _require_field(data, key, where)
    if not isinstance(value, list):
        raise UsageError(
            f"Key '{key}' in {where} must be a list, got {type(value).__name__}. "
            f"The index.json does not match the expected schema."
        )
    return list(value)


def _as_dict(value: object, what: str, where: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise UsageError(
            f"{what} in {where} must be an object, got {type(value).__name__}. "
            f"The index.json does not match the expected schema."
        )
    return {str(key): item for key, item in value.items()}


# ---------------------------------------------------------------------------
# Input loading
# ---------------------------------------------------------------------------


def _resolve_run_dir(raw_path: str, label: str) -> Path:
    """Resolve a run-dir or index.json path to the run directory."""
    path = Path(raw_path).resolve()
    if path.is_dir():
        if not (path / _INDEX_JSON_NAME).is_file():
            raise UsageError(
                f"The {label} run directory {path} contains no {_INDEX_JSON_NAME}. "
                f"Expected a structured test-results run directory; re-run the test suite."
            )
        return path
    if path.is_file() and path.name == _INDEX_JSON_NAME:
        return path.parent
    raise UsageError(
        f"The {label} input is not a run directory or an {_INDEX_JSON_NAME} path: "
        f"{path}. Pass a test-results run directory or its {_INDEX_JSON_NAME}."
    )


def _load_index(run_dir: Path) -> dict[str, object]:
    """Load and shape-check the run directory's index.json."""
    index_path = run_dir / _INDEX_JSON_NAME
    try:
        raw = json.loads(index_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise UsageError(
            f"index.json at {index_path} is not valid JSON ({exc}). Expected a "
            f"structured test-results index; re-run the test suite to regenerate it."
        ) from exc
    return _as_dict(raw, "index.json root", str(index_path))


# ---------------------------------------------------------------------------
# Failing sets and cluster patterns
# ---------------------------------------------------------------------------


def _failing_map(index: dict[str, object], where: str) -> dict[str, dict[str, str]]:
    """Map test_id -> {kind, error_type, error_message} over failures + errors."""
    failing: dict[str, dict[str, str]] = {}
    for kind, key in (("failure", "failures"), ("error", "errors")):
        for item in _require_list(index, key, where):
            entry = _as_dict(item, f"'{key}' entry", where)
            test_id = _require_str(entry, "test_id", where)
            failing[test_id] = {
                "kind": kind,
                "error_type": _require_str(entry, "error_type", where),
                "error_message": _require_str(entry, "error_message", where),
            }
    return failing


def _cluster_counts(index: dict[str, object], where: str) -> dict[str, int]:
    """Sum member counts per cluster pattern over failure + error clusters."""
    counts: dict[str, int] = {}
    for key in ("failure_clusters", "error_clusters"):
        for item in _require_list(index, key, where):
            cluster = _as_dict(item, f"'{key}' entry", where)
            pattern = _require_str(cluster, "pattern", where)
            count = _require_int(cluster, "count", where)
            if pattern in counts:
                counts[pattern] += count
            else:
                counts[pattern] = count
    return counts


def _compute_verdict(prev_ids: set[str], cur_ids: set[str]) -> str:
    """Classify the delta between the two failing sets."""
    if cur_ids - prev_ids:
        return _VERDICT_REGRESSION
    if not cur_ids:
        return _VERDICT_SUCCESS
    if prev_ids - cur_ids:
        return _VERDICT_PARTIAL
    return _VERDICT_NO_CHANGE


def _still_failing_details(
    prev_failing: dict[str, dict[str, str]],
    cur_failing: dict[str, dict[str, str]],
) -> list[dict[str, object]]:
    """Detail objects for tests failing in both runs, noting message changes."""
    details: list[dict[str, object]] = []
    for test_id in sorted(set(prev_failing) & set(cur_failing)):
        previous = prev_failing[test_id]
        current = cur_failing[test_id]
        details.append(
            {
                "test_id": test_id,
                "kind": current["kind"],
                "error_message_changed": previous["error_message"] != current["error_message"],
                "previous_error_message": previous["error_message"],
                "current_error_message": current["error_message"],
            }
        )
    return details


def _new_failure_details(
    prev_failing: dict[str, dict[str, str]],
    cur_failing: dict[str, dict[str, str]],
) -> list[dict[str, object]]:
    """Detail objects for tests failing now that did not fail before."""
    details: list[dict[str, object]] = []
    for test_id in sorted(set(cur_failing) - set(prev_failing)):
        current = cur_failing[test_id]
        details.append(
            {
                "test_id": test_id,
                "kind": current["kind"],
                "error_type": current["error_type"],
                "error_message": current["error_message"],
            }
        )
    return details


def _cluster_delta(
    prev_clusters: dict[str, int], cur_clusters: dict[str, int]
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    """Split cluster patterns into (resolved, persisting, new) lists."""
    resolved = [
        {"pattern": pattern, "previous_count": prev_clusters[pattern]}
        for pattern in sorted(set(prev_clusters) - set(cur_clusters))
    ]
    persisting = [
        {
            "pattern": pattern,
            "previous_count": prev_clusters[pattern],
            "current_count": cur_clusters[pattern],
        }
        for pattern in sorted(set(prev_clusters) & set(cur_clusters))
    ]
    new = [
        {"pattern": pattern, "current_count": cur_clusters[pattern]}
        for pattern in sorted(set(cur_clusters) - set(prev_clusters))
    ]
    return resolved, persisting, new


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Classify the delta between two structured test-results runs."
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="Previous and current run (run directory or index.json), in that order",
    )
    parser.add_argument("--previous", help="Previous run directory or index.json path")
    parser.add_argument("--current", help="Current run directory or index.json path")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    return parser.parse_args()


def _configure_logging(debug: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )


def _resolve_inputs(args: argparse.Namespace) -> tuple[str, str]:
    """Resolve --previous/--current vs the two-positional form."""
    if args.paths:
        if args.previous is not None or args.current is not None:
            raise UsageError(
                "Give either two positional paths (previous current) or "
                "--previous/--current, not both."
            )
        if len(args.paths) != 2:
            raise UsageError(
                f"Expected exactly 2 positional paths (previous current), "
                f"got {len(args.paths)}."
            )
        return str(args.paths[0]), str(args.paths[1])
    if args.previous is None or args.current is None:
        raise UsageError(
            "Both runs are required: pass --previous <run> --current <run> "
            "(or two positional paths: previous current)."
        )
    return str(args.previous), str(args.current)


def _run(args: argparse.Namespace) -> int:
    previous_raw, current_raw = _resolve_inputs(args)
    prev_dir = _resolve_run_dir(previous_raw, "previous")
    cur_dir = _resolve_run_dir(current_raw, "current")
    prev_index = _load_index(prev_dir)
    cur_index = _load_index(cur_dir)
    prev_where = str(prev_dir / _INDEX_JSON_NAME)
    cur_where = str(cur_dir / _INDEX_JSON_NAME)

    prev_project = _require_str(prev_index, "project", prev_where)
    cur_project = _require_str(cur_index, "project", cur_where)
    if prev_project != cur_project:
        raise UsageError(
            f"The two runs belong to different projects: previous is "
            f"'{prev_project}', current is '{cur_project}'. Expected two runs of "
            f"the same package; pick two run directories of one project."
        )

    prev_failing = _failing_map(prev_index, prev_where)
    cur_failing = _failing_map(cur_index, cur_where)
    prev_ids = set(prev_failing)
    cur_ids = set(cur_failing)

    now_passing = sorted(prev_ids - cur_ids)
    still_failing = _still_failing_details(prev_failing, cur_failing)
    new_failures = _new_failure_details(prev_failing, cur_failing)
    resolved, persisting, new_clusters = _cluster_delta(
        _cluster_counts(prev_index, prev_where), _cluster_counts(cur_index, cur_where)
    )
    verdict = _compute_verdict(prev_ids, cur_ids)

    payload: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "project": cur_project,
        "previous": {
            "run_dir": str(prev_dir),
            "result": _require_str(prev_index, "result", prev_where),
            "failing_total": len(prev_ids),
        },
        "current": {
            "run_dir": str(cur_dir),
            "result": _require_str(cur_index, "result", cur_where),
            "failing_total": len(cur_ids),
        },
        "verdict": verdict,
        "summary": {
            "fixed": len(now_passing),
            "still_failing": len(still_failing),
            "new": len(new_failures),
        },
        "now_passing": now_passing,
        "still_failing": still_failing,
        "new_failures": new_failures,
        "resolved_clusters": resolved,
        "persisting_clusters": persisting,
        "new_clusters": new_clusters,
    }
    output_path = cur_dir / _OUTPUT_FILENAME
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print(
        f"VERDICT: {verdict} - fixed {len(now_passing)}, "
        f"still-failing {len(still_failing)}, new {len(new_failures)}"
    )
    print(f"Details: {output_path}")
    return _EXIT_SUCCESS if verdict == _VERDICT_SUCCESS else _EXIT_NOT_SUCCESS


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
