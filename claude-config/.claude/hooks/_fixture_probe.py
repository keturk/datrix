r"""Which fixture projects a session edited, and whether each was probed since.

A fixture project (`tests/fixtures/[projects/]<name>/` holding `.dtrx` and `.dcfg` files) is
written from the config schema and the DSL, and each wrong guess surfaced only as a failed test
run. `dev/probe-fixture.ps1` analyzes the project in seconds and prints the real error; it writes
a stamp (`.tmp/fixture-probes/<hash>.json`) when it has shown the result. A test run that follows
an edit of a fixture project with no probe since that edit is refused
(`guard-test-run-discipline.py`).

`record-fixture-edits.py` keeps, per session, the project directories the session edited and the
test files it edited; both guards read that record.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Final

REPO_ROOT: Final = "d:/datrix"
STATE_DIR: Final = os.path.join(REPO_ROOT, ".claude", "hooks", ".state")
STAMP_DIR: Final = os.path.join(REPO_ROOT, ".tmp", "fixture-probes")
PROBE_COMMAND: Final = (
    'powershell -File "d:/datrix/datrix/scripts/dev/probe-fixture.ps1" -Path <system.dtrx> -ConfigProfile <profile>'
)

#: The directory of a fixture project: the first directory below `tests/fixtures/` (below
#: `tests/fixtures/projects/` when that exists) holding the written `.dtrx` / `.dcfg` file.
_PROJECT_RE: Final = re.compile(
    r"^(.*?/tests/fixtures/(?:projects/)?[^/]+)/.+\.(?:dtrx|dcfg)$", re.IGNORECASE
)
_NOT_PROJECT_NAMES: Final = frozenset({"projects", "config"})
_TEST_FILE_RE: Final = re.compile(r"/tests/.+\.py$", re.IGNORECASE)
_SOURCE_SUFFIXES: Final = (".dtrx", ".dcfg")


def safe_id(session_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", session_id or "unknown")


def edits_path(session_id: str) -> str:
    return os.path.join(STATE_DIR, f"fixture-edits-{safe_id(session_id)}.json")


def normalise(path: str) -> str:
    return path.replace("\\", "/")


def project_dir(path: str) -> str | None:
    """The fixture project directory *path* belongs to, or None when it is none."""
    match = _PROJECT_RE.match(normalise(path))
    if match is None:
        return None
    directory = match.group(1)
    return None if directory.rsplit("/", 1)[-1].lower() in _NOT_PROJECT_NAMES else directory


def is_test_file(path: str) -> bool:
    return _TEST_FILE_RE.search(normalise(path)) is not None


def read_edits(session_id: str) -> dict[str, list[str]]:
    """The recorded `{"projects": [...], "tests": [...]}` of a session (empty when none)."""
    try:
        with open(edits_path(session_id), encoding="utf-8") as handle:
            loaded = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {"projects": [], "tests": []}
    if not isinstance(loaded, dict):
        return {"projects": [], "tests": []}
    return {
        key: [str(item) for item in loaded.get(key, []) if isinstance(item, str)]
        for key in ("projects", "tests")
    }


def write_edits(session_id: str, edits: dict[str, list[str]]) -> None:
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(edits_path(session_id), "w", encoding="utf-8") as handle:
            json.dump(edits, handle, indent=2)
    except OSError:
        return


def stamp_path(directory: str) -> str:
    digest = hashlib.sha1(normalise(directory).lower().encode("utf-8")).hexdigest()  # noqa: S324
    return os.path.join(STAMP_DIR, f"{digest}.json")


def probed_at(directory: str) -> float | None:
    """When the probe last showed this project's analysis, or None when it never did."""
    try:
        with open(stamp_path(directory), encoding="utf-8") as handle:
            stamp = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    value = stamp.get("ts") if isinstance(stamp, dict) else None
    return float(value) if isinstance(value, int | float) else None


def newest_source_mtime(directory: str) -> float | None:
    """The newest modification time among the project's `.dtrx` / `.dcfg` files."""
    root = Path(directory)
    if not root.is_dir() or not any(root.glob("*.dtrx")):
        return None
    times = [
        path.stat().st_mtime
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in _SOURCE_SUFFIXES
    ]
    return max(times) if times else None


def unprobed(directories: list[str]) -> list[str]:
    """The project directories edited after their last probe (or never probed)."""
    stale: list[str] = []
    for directory in directories:
        newest = newest_source_mtime(directory)
        if newest is None:
            continue
        stamp = probed_at(directory)
        if stamp is None or stamp < newest:
            stale.append(directory)
    return stale
