"""Fail when a package's newest full-run timings show an un-baselined slow
test or a fixture rebuilt on more than one xdist worker.

Three waste shapes have no enforcement anywhere else in the repo: a single
test that loops a whole matrix (a config-realization sweep looping every
field in one test body), a session/module fixture with no ``xdist_group``
rebuilt once PER WORKER (an e2e fixture paying its setup cost once per
parallel worker instead of once), and a per-parametrized-case corpus re-scan
(a parity test re-walking a whole package tree on every parametrized case).
None of this is caught by a green suite -- a fixed test can silently regrow
the cost it just lost. This module reads the merged ``timings.json`` the
runner plugin writes (datrix-common's ``runner_plugin``) for the newest FULL
run of every testable package (``shared.package_suites.discover_package_suites``
-- never a hardcoded package list, and never a package that carries no test
suite at all) and fails on:

  (i)  any test whose call-phase duration exceeds ``CALL_CEILING_SECONDS``
  (ii) any session/package/module-scoped fixture set up on more than one
       DISTINCT worker (keyed by the recorded ``worker`` id, never by
       occurrence count) with a setup duration exceeding
       ``FIXTURE_CEILING_SECONDS`` on at least one of those workers

...unless the offending id is listed in the decrease-only baseline
(``datrix/scripts/config/slow-test-baseline.json``). A baseline entry that no
longer measures as an offender is itself a gate failure (stale entries rot
into meaningless cover) -- the baseline can only shrink, EXCEPT a
``toolchain-compile`` entry, which is intentionally never driven to zero by
this gate and so is exempt from the staleness check.

A Node package (``datrix-vscode``) carries no runner_plugin and therefore no
``timings.json`` fixture-timing dimension at all -- a JUnit ``<testcase>``'s
own ``time`` attribute is the only call-duration signal available, read from
the merged JUnit XML the Node runner writes. A Node package whose newest run
directory exists but carries no v2 full run with a readable merged JUnit is
reported as ``missing_full_run``, never silently credited with zero offenders.

Decrease-only is enforced against the baseline **as committed at HEAD** in the
``datrix`` package's own git repository -- not merely against ``--seed``'s own
output -- in BOTH check mode and ``--seed``: the working-tree baseline file
(or, for ``--seed``, the newly proposed one) must never add a key or increase
a ``seconds`` value relative to what HEAD carries. A path absent at HEAD reads
as an empty baseline (first seed, allowed). Any other git failure fails
closed with :class:`RatchetError` (exit 2) -- decrease-only cannot be verified
without a trustworthy committed reference, so an unreadable repository is
never treated as "no baseline yet".

Run with ``--self-test`` to prove the detector fires on a planted 31 s call
and a planted 6 s two-worker fixture, clears once both are baselined, flags a
stale entry, respects both ceilings' strict boundaries, tells a same-worker
fixture repeat apart from real replication, rejects a seed placeholder left
in a committed entry, and reads/refuses a real git HEAD correctly.

Run with ``--seed`` to write the baseline from the current offenders, with
placeholder ``class``/``reason`` strings that MUST be replaced by hand before
commit (refused, exit 2, if the result would grow the baseline committed at
HEAD).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path
from typing import Literal

_LIBRARY_DIR = Path(__file__).resolve().parent.parent
if _LIBRARY_DIR.exists() and str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from shared.package_suites import PackageSuite, SuiteKind, discover_package_suites  # noqa: E402
from shared.suite_stamp import MERGED_TIMINGS_NAME  # noqa: E402
from shared.venv import get_datrix_root  # noqa: E402

#: A call's ``call``-phase duration above this is an offender unless baselined.
CALL_CEILING_SECONDS: float = 30.0

#: A session/package/module fixture set up on more than one DISTINCT worker,
#: above this per-worker setup duration, is an offender unless baselined.
FIXTURE_CEILING_SECONDS: float = 5.0

#: Fixture scopes the runner plugin times.
_TIMED_FIXTURE_SCOPES: frozenset[str] = frozenset({"session", "package", "module"})

_DATRIX_REPO_DIRNAME = "datrix"
_BASELINE_RELPATH: tuple[str, ...] = ("scripts", "config", "slow-test-baseline.json")
_ALLOWED_CLASSES: frozenset[str] = frozenset({
    "matrix-in-one-test", "session-fixture-per-worker", "whole-corpus-scan", "toolchain-compile",
})
#: Exempt from the "stale entries fail" rule -- this class is never driven to
#: zero by this gate; leaving its baseline entry in place is not rot.
_STALE_EXEMPT_CLASS = "toolchain-compile"
#: Placeholders ``--seed`` writes. A committed entry still carrying either one
#: was never hand-classified and must be rejected, not silently trusted.
_PLACEHOLDER_CLASS = "REPLACE-WITH-REAL-CLASS"
_PLACEHOLDER_REASON = "REPLACE-WITH-REAL-REASON"
#: The merged JUnit XML a Node full run writes (mirrors
#: ``shared.node_test_runner``'s own private ``_MERGED_XML_NAME``). Node has
#: no runner_plugin/timings.json, so a testcase's own ``time`` attribute is
#: the only call-duration signal available for a Node package.
_NODE_MERGED_JUNIT_NAME = "junit-node.xml"
_INDEX_FILENAME = "index.json"


class RatchetError(Exception):
    """Invalid baseline, unreadable run data, or an untrustworthy git read; the gate exits 2."""


class BaselineEntry:
    """One decrease-only baseline row."""

    def __init__(
        self, *, kind: Literal["call", "fixture"], package: str, id_: str,
        seconds: float, class_: str, reason: str,
    ) -> None:
        if kind not in ("call", "fixture"):
            raise RatchetError(f"Invalid baseline 'kind': {kind!r}. Expected 'call' or 'fixture'.")
        if class_ not in _ALLOWED_CLASSES:
            raise RatchetError(
                f"Invalid baseline 'class' {class_!r} for {package}/{id_}. Expected one of "
                f"{sorted(_ALLOWED_CLASSES)}."
            )
        if not reason.strip():
            raise RatchetError(f"Baseline entry {package}/{id_} has no written 'reason'.")
        if reason.strip() == _PLACEHOLDER_REASON:
            raise RatchetError(
                f"Baseline entry {package}/{id_} still carries the seed placeholder reason "
                f"{_PLACEHOLDER_REASON!r}; replace it with a real, specific justification before commit."
            )
        self.kind = kind
        self.package = package
        self.id = id_
        self.seconds = seconds
        self.class_ = class_
        self.reason = reason

    def key(self) -> tuple[str, str, str]:
        return (self.kind, self.package, self.id)

    def to_json(self) -> dict[str, object]:
        return {
            "kind": self.kind, "package": self.package, "id": self.id,
            "seconds": self.seconds, "class": self.class_, "reason": self.reason,
        }

    @staticmethod
    def from_json(raw: dict[str, object]) -> "BaselineEntry":
        try:
            return BaselineEntry(
                kind=raw["kind"], package=raw["package"], id_=raw["id"],
                seconds=float(raw["seconds"]), class_=raw["class"], reason=raw["reason"],
            )
        except KeyError as exc:
            raise RatchetError(f"Baseline entry missing required key {exc}: {raw!r}") from exc


class Offender:
    """One measured call or fixture that exceeds its ceiling."""

    def __init__(
        self, *, kind: Literal["call", "fixture"], package: str, id_: str,
        seconds: float, workers: int = 1,
    ) -> None:
        self.kind = kind
        self.package = package
        self.id = id_
        self.seconds = seconds
        self.workers = workers

    def key(self) -> tuple[str, str, str]:
        return (self.kind, self.package, self.id)

    def __str__(self) -> str:
        if self.kind == "call":
            return f"{self.package}::{self.id}: {self.seconds:.1f}s call (ceiling {CALL_CEILING_SECONDS}s)"
        return (
            f"{self.package}::{self.id}: fixture setup {self.seconds:.1f}s on "
            f"{self.workers} workers (ceiling {FIXTURE_CEILING_SECONDS}s on >1 worker)"
        )


# ---------------------------------------------------------------------------
# Baseline: on-disk (working tree) and committed (git HEAD)
# ---------------------------------------------------------------------------


def datrix_repo_path(workspace: Path) -> Path:
    """The ``datrix`` showcase package's own git repository root."""
    return workspace / _DATRIX_REPO_DIRNAME


def baseline_path(workspace: Path) -> Path:
    return datrix_repo_path(workspace).joinpath(*_BASELINE_RELPATH)


def load_baseline(path: Path) -> list[BaselineEntry]:
    """Read the decrease-only baseline from the working tree; an absent file
    is an empty baseline."""
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RatchetError(f"Cannot parse {path} as JSON: {exc}.") from exc
    if not isinstance(raw, list):
        raise RatchetError(f"{path} must contain a JSON array of baseline entries; got {type(raw).__name__}.")
    return [BaselineEntry.from_json(entry) for entry in raw]


def _run_git(datrix_repo: Path, arguments: list[str]) -> subprocess.CompletedProcess[str]:
    """Run one git command in *datrix_repo*; any non-zero exit fails closed."""
    result = subprocess.run(  # noqa: S603 -- fixed argv, no shell
        ["git", "-C", str(datrix_repo), *arguments],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise RatchetError(
            f"Cannot read the committed baseline: 'git -C {datrix_repo} {' '.join(arguments)}' "
            f"failed: {result.stderr.strip() or 'no error output'} (exit {result.returncode}). "
            f"Decrease-only cannot be verified without the committed baseline. Fix the git "
            f"failure (run inside a clone of the datrix repo with at least one commit) and re-run."
        )
    return result


def load_committed_baseline(datrix_repo: Path) -> list[BaselineEntry] | None:
    """The baseline as committed at HEAD in *datrix_repo*, or ``None`` when the
    path does not exist there yet (first seed).

    Raises:
        RatchetError: any other git failure -- an unreadable repository, a
            missing/detached HEAD, or unparseable committed content.
            Decrease-only cannot be verified without a trustworthy committed
            reference, so this fails closed rather than treating the failure
            as "no baseline yet".
    """
    relpath = "/".join(_BASELINE_RELPATH)
    # Whether the path exists at HEAD is asked structurally (the tree listing
    # is empty when it does not), never inferred from git's error wording,
    # which differs by whether the file is present on disk.
    listing = _run_git(datrix_repo, ["ls-tree", "--name-only", "HEAD", "--", relpath])
    if not listing.stdout.strip():
        return None
    result = _run_git(datrix_repo, ["show", f"HEAD:{relpath}"])
    try:
        raw = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RatchetError(
            f"The committed baseline at HEAD:{relpath} in {datrix_repo} is not valid JSON: {exc}."
        ) from exc
    if not isinstance(raw, list):
        raise RatchetError(
            f"The committed baseline at HEAD:{relpath} in {datrix_repo} must be a JSON array; "
            f"got {type(raw).__name__}."
        )
    return [BaselineEntry.from_json(entry) for entry in raw]


# ---------------------------------------------------------------------------
# Offender detection
# ---------------------------------------------------------------------------


def _newest_full_run_dir(package_dir: Path) -> Path | None:
    """The newest run directory whose index.json is a v2 full run, or None.

    A "full" run is one whose index.json has selection.kind == "full" and
    schema_version >= 2 -- a targeted run is never consulted, exactly like the
    carry mechanism never carries one. Shared between the pytest path (which
    then reads timings.json beside it) and the Node path (which reads the
    merged JUnit XML beside it instead).
    """
    results_dir = package_dir / ".test_results"
    if not results_dir.is_dir():
        return None
    candidates: list[tuple[str, Path]] = []
    for run_dir in results_dir.iterdir():
        if not run_dir.is_dir():
            continue
        index_path = run_dir / _INDEX_FILENAME
        if not index_path.is_file():
            continue
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if index.get("schema_version", 1) < 2:
            continue
        if index.get("selection", {}).get("kind") != "full":
            continue
        candidates.append((run_dir.name, run_dir))
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]


def _newest_full_run_timings(package_dir: Path) -> dict[str, object] | None:
    run_dir = _newest_full_run_dir(package_dir)
    if run_dir is None:
        return None
    timings_path = run_dir / MERGED_TIMINGS_NAME
    if not timings_path.is_file():
        return None
    payload: dict[str, object] = json.loads(timings_path.read_text(encoding="utf-8"))
    payload["_run_dir"] = str(run_dir)
    return payload


def schedule_independent_nodeid(nodeid: str) -> str:
    """*nodeid* without the ``@<group>`` suffix pytest-xdist appends under ``--dist loadgroup``.

    xdist rewrites a grouped item's node id to ``<nodeid>@<group>``, and the
    group can change without the test changing (a pool index reassigned, a
    group mark added). A baseline keyed on the suffixed id would then read as
    one stale entry plus one new offender for the same test. The suffix always
    follows the whole node id, so a ``@`` inside a parametrize id's brackets
    or before the last ``::`` is part of the id and is kept.
    """
    head, separator, group = nodeid.rpartition("@")
    if not separator or "]" in group or "::" in group or "/" in group:
        return nodeid
    return head


def _call_offenders_from_timings(package: str, timings: dict[str, object]) -> list[Offender]:
    offenders: list[Offender] = []
    for call in timings.get("calls", []):
        seconds = float(call["seconds"])
        if seconds > CALL_CEILING_SECONDS:
            offenders.append(Offender(
                kind="call", package=package,
                id_=schedule_independent_nodeid(call["nodeid"]), seconds=seconds,
            ))
    return offenders


def _fixture_offenders_from_timings(package: str, timings: dict[str, object]) -> list[Offender]:
    """A fixture is an offender when recorded on MORE THAN ONE DISTINCT worker
    with a setup duration above the ceiling on at least one of them -- keyed
    by the recorded ``worker`` id, never by occurrence count. Two records for
    the same worker (e.g. a module-scoped fixture set up for two modules on
    that worker) are not replication.
    """
    per_fixture_worker_seconds: dict[str, dict[str, float]] = {}
    for fx in timings.get("fixtures", []):
        if fx["scope"] not in _TIMED_FIXTURE_SCOPES:
            continue
        by_worker = per_fixture_worker_seconds.setdefault(fx["fixture"], {})
        seconds = float(fx["seconds"])
        by_worker[fx["worker"]] = max(seconds, by_worker.get(fx["worker"], 0.0))

    offenders: list[Offender] = []
    for fixture_id, by_worker in per_fixture_worker_seconds.items():
        distinct_workers = len(by_worker)
        max_seconds = max(by_worker.values())
        if distinct_workers > 1 and max_seconds > FIXTURE_CEILING_SECONDS:
            offenders.append(Offender(
                kind="fixture", package=package, id_=fixture_id,
                seconds=max_seconds, workers=distinct_workers,
            ))
    return offenders


def _node_call_offenders(package: str, package_dir: Path) -> tuple[list[Offender], bool]:
    """Node call-duration offenders from the newest full run's merged JUnit XML.

    Returns:
        ``(offenders, has_full_run)`` -- ``has_full_run`` is False when no v2
        full run with a readable merged JUnit exists, so the caller reports
        the package as missing rather than silently crediting it with zero
        offenders (a package whose ``.test_results`` exists but never
        produced a usable full run must never read as "clean").
    """
    run_dir = _newest_full_run_dir(package_dir)
    if run_dir is None:
        return [], False
    junit_path = run_dir / _NODE_MERGED_JUNIT_NAME
    if not junit_path.is_file():
        return [], False
    offenders: list[Offender] = []
    tree = ET.parse(junit_path)  # noqa: S314 -- runner-produced, local file
    for case in tree.getroot().iter("testcase"):
        seconds = float(case.get("time", "0"))
        if seconds > CALL_CEILING_SECONDS:
            classname = case.get("classname", "")
            name = case.get("name", "")
            offenders.append(Offender(kind="call", package=package, id_=f"{classname}::{name}", seconds=seconds))
    return offenders, True


def find_offenders(packages: dict[str, PackageSuite]) -> tuple[list[Offender], list[str]]:
    """Offenders for every discovered testable package, and packages with no
    usable full run.

    Returns:
        ``(offenders, packages_without_a_full_run)`` -- the second list is a
        fail-closed signal: a package the caller expected to check but that
        has no v2 full run at all is reported, never silently skipped.
    """
    offenders: list[Offender] = []
    missing_full_run: list[str] = []
    for name, suite in sorted(packages.items()):
        if suite.kind is SuiteKind.NODE:
            node_offenders, has_full_run = _node_call_offenders(name, suite.path)
            if not has_full_run:
                missing_full_run.append(name)
            offenders.extend(node_offenders)
            continue
        timings = _newest_full_run_timings(suite.path)
        if timings is None:
            missing_full_run.append(name)
            continue
        offenders.extend(_call_offenders_from_timings(name, timings))
        offenders.extend(_fixture_offenders_from_timings(name, timings))
    return offenders, missing_full_run


def unbaselined(offenders: list[Offender], baseline: list[BaselineEntry]) -> list[Offender]:
    baselined_keys = {entry.key() for entry in baseline}
    return [o for o in offenders if o.key() not in baselined_keys]


def stale_entries(offenders: list[Offender], baseline: list[BaselineEntry]) -> list[BaselineEntry]:
    """Baseline entries that no longer measure as an offender -- decrease-only
    means a fixed test's entry must be REMOVED, never left as harmless cover.
    A ``toolchain-compile`` entry is exempt: this gate never drives that class
    to zero."""
    offender_keys = {o.key() for o in offenders}
    return [
        entry for entry in baseline
        if entry.key() not in offender_keys and entry.class_ != _STALE_EXEMPT_CLASS
    ]


def check_baseline_only_shrank(previous: list[BaselineEntry], candidate: list[BaselineEntry]) -> list[str]:
    """Non-vacuity guard shared by ``--seed`` and CHECK mode's baseline
    integrity check: every candidate entry must already exist in *previous*
    (the baseline committed at HEAD) with an equal-or-smaller ``seconds``, OR
    *previous* must be empty (first seed)."""
    if not previous:
        return []
    previous_by_key = {entry.key(): entry for entry in previous}
    violations: list[str] = []
    for entry in candidate:
        prior = previous_by_key.get(entry.key())
        if prior is None:
            violations.append(f"{entry.package}/{entry.id}: new entry not present in the committed baseline")
        elif entry.seconds > prior.seconds:
            violations.append(
                f"{entry.package}/{entry.id}: {entry.seconds}s > committed {prior.seconds}s (decrease-only)"
            )
    return violations


# ---------------------------------------------------------------------------
# Self-test helpers
# ---------------------------------------------------------------------------


def _write_full_run_index(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / _INDEX_FILENAME).write_text(
        json.dumps({"schema_version": 2, "selection": {"kind": "full"}}), encoding="utf-8",
    )


def _write_timings(run_dir: Path, calls: list[dict[str, object]], fixtures: list[dict[str, object]]) -> None:
    (run_dir / MERGED_TIMINGS_NAME).write_text(
        json.dumps({"schema": 1, "calls": calls, "fixtures": fixtures}), encoding="utf-8",
    )


def _pytest_suite(name: str, path: Path) -> dict[str, PackageSuite]:
    return {name: PackageSuite(name=name, path=path, kind=SuiteKind.PYTEST)}


def _node_suite(name: str, path: Path) -> dict[str, PackageSuite]:
    return {name: PackageSuite(name=name, path=path, kind=SuiteKind.NODE)}


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603, S607 -- fixed argv, self-test-local repo
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=False,
    )


def _init_selftest_git_repo(repo_dir: Path, *, baseline_content: str | None) -> None:
    """A real, one-commit git repo: the baseline file committed at
    ``scripts/config/slow-test-baseline.json`` when *baseline_content* is
    given, or a single unrelated committed file (HEAD exists, the path does
    not) when it is None."""
    repo_dir.mkdir(parents=True, exist_ok=True)
    init = _git(["init", "-q"], repo_dir)
    assert init.returncode == 0, f"git init failed: {init.stderr}"
    _git(["config", "user.email", "selftest@example.invalid"], repo_dir)
    _git(["config", "user.name", "Ratchet Self-Test"], repo_dir)
    if baseline_content is not None:
        target = repo_dir.joinpath(*_BASELINE_RELPATH)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(baseline_content, encoding="utf-8")
    else:
        (repo_dir / "placeholder.txt").write_text("x", encoding="utf-8")
    add = _git(["add", "."], repo_dir)
    assert add.returncode == 0, f"git add failed: {add.stderr}"
    commit = _git(["commit", "-q", "-m", "selftest"], repo_dir)
    assert commit.returncode == 0, f"git commit failed: {commit.stderr}"


# ---------------------------------------------------------------------------
# Self-test checks
# ---------------------------------------------------------------------------


def _check_call_and_fixture_offenders_detected() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        pkg_dir = Path(tmp) / "datrix-selftest-pkg"
        run_dir = pkg_dir / ".test_results" / "test-results-20260101-000000"
        _write_full_run_index(run_dir)
        _write_timings(
            run_dir,
            calls=[{"nodeid": "tests/test_x.py::test_slow", "seconds": 31.0, "worker": "gw0"}],
            fixtures=[
                {"fixture": "tests/e2e::big_fixture", "scope": "module", "seconds": 6.0, "worker": "gw0"},
                {"fixture": "tests/e2e::big_fixture", "scope": "module", "seconds": 6.2, "worker": "gw1"},
            ],
        )
        offenders, missing = find_offenders(_pytest_suite("datrix-selftest-pkg", pkg_dir))
        assert not missing, f"expected a usable full run, got missing_full_run={missing}"
        assert len(offenders) == 2, f"expected 2 offenders (1 call, 1 fixture), got {[str(o) for o in offenders]}"
        fixture_offenders = [o for o in offenders if o.kind == "fixture"]
        assert fixture_offenders and fixture_offenders[0].workers == 2, (
            f"expected the fixture offender to record 2 distinct workers, got {[o.workers for o in fixture_offenders]}"
        )


def _check_offenders_clear_once_baselined() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        pkg_dir = Path(tmp) / "datrix-selftest-pkg"
        run_dir = pkg_dir / ".test_results" / "test-results-20260101-000000"
        _write_full_run_index(run_dir)
        _write_timings(
            run_dir,
            calls=[{"nodeid": "tests/test_x.py::test_slow", "seconds": 31.0, "worker": "gw0"}],
            fixtures=[
                {"fixture": "tests/e2e::big_fixture", "scope": "module", "seconds": 6.0, "worker": "gw0"},
                {"fixture": "tests/e2e::big_fixture", "scope": "module", "seconds": 6.2, "worker": "gw1"},
            ],
        )
        offenders, _ = find_offenders(_pytest_suite("datrix-selftest-pkg", pkg_dir))
        baseline = [
            BaselineEntry(kind="call", package="datrix-selftest-pkg", id_="tests/test_x.py::test_slow",
                          seconds=31.0, class_="matrix-in-one-test", reason="self-test plant"),
            BaselineEntry(kind="fixture", package="datrix-selftest-pkg", id_="tests/e2e::big_fixture",
                          seconds=6.2, class_="session-fixture-per-worker", reason="self-test plant"),
        ]
        cleared = unbaselined(offenders, baseline)
        assert not cleared, f"expected 0 unbaselined offenders once both are baselined, got {[str(o) for o in cleared]}"


def _check_stale_entries_detected() -> None:
    baseline = [
        BaselineEntry(kind="call", package="datrix-selftest-pkg", id_="tests/test_x.py::test_slow",
                      seconds=31.0, class_="matrix-in-one-test", reason="self-test plant"),
        BaselineEntry(kind="fixture", package="datrix-selftest-pkg", id_="tests/e2e::big_fixture",
                      seconds=6.2, class_="session-fixture-per-worker", reason="self-test plant"),
    ]
    stale = stale_entries([], baseline)
    assert len(stale) == 2, f"expected both entries stale once the offenders vanish, got {len(stale)}"


def _check_toolchain_compile_never_stale() -> None:
    baseline = [
        BaselineEntry(kind="call", package="datrix-codegen-azure", id_="tests/unit/test_bicep.py::test_compile",
                      seconds=45.0, class_="toolchain-compile", reason="bicep CLI invocation, argv indirection"),
    ]
    stale = stale_entries([], baseline)
    assert not stale, f"a toolchain-compile entry must never be reported stale, got {[e.id for e in stale]}"


def _check_same_worker_fixture_not_offender() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        pkg_dir = Path(tmp) / "datrix-selftest-pkg"
        run_dir = pkg_dir / ".test_results" / "test-results-20260101-000000"
        _write_full_run_index(run_dir)
        _write_timings(
            run_dir, calls=[],
            fixtures=[
                {"fixture": "tests/e2e::big_fixture", "scope": "module", "seconds": 6.0, "worker": "gw0"},
                {"fixture": "tests/e2e::big_fixture", "scope": "module", "seconds": 6.5, "worker": "gw0"},
            ],
        )
        offenders, _ = find_offenders(_pytest_suite("datrix-selftest-pkg", pkg_dir))
        assert not offenders, (
            f"a fixture set up twice on the SAME worker is not replication; expected 0 offenders, "
            f"got {[str(o) for o in offenders]}"
        )


def _check_call_ceiling_boundary() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        pkg_dir = Path(tmp) / "datrix-selftest-pkg"
        run_dir = pkg_dir / ".test_results" / "test-results-20260101-000000"
        _write_full_run_index(run_dir)
        _write_timings(
            run_dir,
            calls=[
                {"nodeid": "tests/test_x.py::test_at_ceiling", "seconds": 30.0, "worker": "gw0"},
                {"nodeid": "tests/test_x.py::test_over_ceiling", "seconds": 30.1, "worker": "gw0"},
            ],
            fixtures=[],
        )
        offenders, _ = find_offenders(_pytest_suite("datrix-selftest-pkg", pkg_dir))
        ids = {o.id for o in offenders}
        assert "tests/test_x.py::test_at_ceiling" not in ids, "30.0s must NOT be an offender (ceiling is strict >30.0)"
        assert "tests/test_x.py::test_over_ceiling" in ids, "30.1s MUST be an offender"


def _check_xdist_group_suffix_is_not_part_of_the_id() -> None:
    assert schedule_independent_nodeid("tests/t.py::C::test_a@npm_tsc_pool_1") == "tests/t.py::C::test_a"
    assert schedule_independent_nodeid("tests/t.py::test_p[x@y]@grp") == "tests/t.py::test_p[x@y]"
    assert schedule_independent_nodeid("tests/t.py::test_p[x@y]") == "tests/t.py::test_p[x@y]"
    assert schedule_independent_nodeid("tests/t.py::test_plain") == "tests/t.py::test_plain"
    with tempfile.TemporaryDirectory() as tmp:
        pkg_dir = Path(tmp) / "datrix-selftest-pkg"
        run_dir = pkg_dir / ".test_results" / "test-results-20260101-000000"
        _write_full_run_index(run_dir)
        _write_timings(
            run_dir,
            calls=[{"nodeid": "tests/test_x.py::test_slow@npm_tsc_pool_3", "seconds": 31.0, "worker": "gw0"}],
            fixtures=[],
        )
        offenders, _ = find_offenders(_pytest_suite("datrix-selftest-pkg", pkg_dir))
        baseline = [BaselineEntry(
            kind="call", package="datrix-selftest-pkg", id_="tests/test_x.py::test_slow",
            seconds=31.0, class_="toolchain-compile", reason="self-test plant",
        )]
        assert not unbaselined(offenders, baseline), (
            "a call recorded under a different xdist group must still match its baseline entry, "
            f"got {[str(o) for o in unbaselined(offenders, baseline)]}"
        )


def _check_fixture_ceiling_boundary() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        pkg_dir = Path(tmp) / "datrix-selftest-pkg"
        run_dir = pkg_dir / ".test_results" / "test-results-20260101-000000"
        _write_full_run_index(run_dir)
        _write_timings(
            run_dir, calls=[],
            fixtures=[
                {"fixture": "tests/e2e::at_ceiling", "scope": "module", "seconds": 5.0, "worker": "gw0"},
                {"fixture": "tests/e2e::at_ceiling", "scope": "module", "seconds": 5.0, "worker": "gw1"},
                {"fixture": "tests/e2e::over_ceiling", "scope": "module", "seconds": 5.1, "worker": "gw0"},
                {"fixture": "tests/e2e::over_ceiling", "scope": "module", "seconds": 5.1, "worker": "gw1"},
            ],
        )
        offenders, _ = find_offenders(_pytest_suite("datrix-selftest-pkg", pkg_dir))
        ids = {o.id for o in offenders}
        assert "tests/e2e::at_ceiling" not in ids, "5.0s on two workers must NOT be an offender (ceiling is strict >5.0)"
        assert "tests/e2e::over_ceiling" in ids, "5.1s on two workers MUST be an offender"


def _check_shrank_grow_violation() -> None:
    previous = [BaselineEntry(kind="call", package="p", id_="t", seconds=10.0, class_="matrix-in-one-test", reason="x")]
    grown = [BaselineEntry(kind="call", package="p", id_="t", seconds=15.0, class_="matrix-in-one-test", reason="x")]
    assert check_baseline_only_shrank(previous, grown), "a grown seconds value must be flagged"
    added = [*previous, BaselineEntry(kind="call", package="q", id_="u", seconds=1.0, class_="matrix-in-one-test", reason="x")]
    assert check_baseline_only_shrank(previous, added), "an added entry not present in the committed baseline must be flagged"


def _check_shrank_shrink_allowed() -> None:
    previous = [BaselineEntry(kind="call", package="p", id_="t", seconds=10.0, class_="matrix-in-one-test", reason="x")]
    shrunk = [BaselineEntry(kind="call", package="p", id_="t", seconds=8.0, class_="matrix-in-one-test", reason="x")]
    assert check_baseline_only_shrank(previous, shrunk) == [], "a smaller seconds value must be allowed"


def _check_shrank_equal_allowed() -> None:
    previous = [BaselineEntry(kind="call", package="p", id_="t", seconds=10.0, class_="matrix-in-one-test", reason="x")]
    same = [BaselineEntry(kind="call", package="p", id_="t", seconds=10.0, class_="matrix-in-one-test", reason="x")]
    assert check_baseline_only_shrank(previous, same) == [], "an equal seconds value must be allowed"


def _check_shrank_first_seed_allowed() -> None:
    candidate = [BaselineEntry(kind="call", package="p", id_="t", seconds=999.0, class_="matrix-in-one-test", reason="x")]
    assert check_baseline_only_shrank([], candidate) == [], "an empty previous baseline (first seed) must allow anything"


def _check_placeholder_class_rejected() -> None:
    try:
        BaselineEntry.from_json({
            "kind": "call", "package": "p", "id": "t", "seconds": 1.0,
            "class": _PLACEHOLDER_CLASS, "reason": "real reason",
        })
    except RatchetError:
        return
    raise AssertionError("a REPLACE-WITH-REAL-CLASS placeholder must be rejected")


def _check_placeholder_reason_rejected() -> None:
    try:
        BaselineEntry.from_json({
            "kind": "call", "package": "p", "id": "t", "seconds": 1.0,
            "class": "matrix-in-one-test", "reason": _PLACEHOLDER_REASON,
        })
    except RatchetError:
        return
    raise AssertionError("a REPLACE-WITH-REAL-REASON placeholder must be rejected")


def _check_pytest_package_missing_full_run() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        pkg_dir = Path(tmp) / "datrix-selftest-pkg-no-runs"
        pkg_dir.mkdir(parents=True)  # no .test_results at all
        offenders, missing = find_offenders(_pytest_suite("datrix-selftest-pkg-no-runs", pkg_dir))
        assert not offenders
        assert missing == ["datrix-selftest-pkg-no-runs"]


def _check_node_package_missing_full_run_without_junit() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        pkg_dir = Path(tmp) / "datrix-node-selftest-pkg"
        run_dir = pkg_dir / ".test_results" / "test-results-20260101-000000"
        _write_full_run_index(run_dir)  # a v2 full index.json exists...
        # ...but no junit-node.xml is written: the exact shape a partially
        # written or differently-instrumented Node run leaves behind. The
        # original heuristic (".test_results exists" -> treat as clean) would
        # silently pass this; it must be reported missing instead.
        offenders, missing = find_offenders(_node_suite("datrix-node-selftest-pkg", pkg_dir))
        assert not offenders, f"expected 0 offenders, got {[str(o) for o in offenders]}"
        assert missing == ["datrix-node-selftest-pkg"], (
            f"a Node package whose .test_results exists but has no readable "
            f"{_NODE_MERGED_JUNIT_NAME} must be reported missing, not silently passed; got {missing}"
        )


def _check_node_package_call_offender_detected() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        pkg_dir = Path(tmp) / "datrix-node-selftest-pkg"
        run_dir = pkg_dir / ".test_results" / "test-results-20260101-000000"
        _write_full_run_index(run_dir)
        suite_el = ET.Element("testsuite", {"name": "node"})
        ET.SubElement(suite_el, "testcase", {
            "classname": "out/test/slow.test.js", "name": "runs the slow thing", "time": "31.5",
        })
        root = ET.Element("testsuites")
        root.append(suite_el)
        ET.ElementTree(root).write(run_dir / _NODE_MERGED_JUNIT_NAME, encoding="utf-8", xml_declaration=True)
        offenders, missing = find_offenders(_node_suite("datrix-node-selftest-pkg", pkg_dir))
        assert not missing, f"expected a usable Node full run, got missing={missing}"
        assert len(offenders) == 1 and offenders[0].seconds == 31.5, (
            f"expected 1 call offender from the Node JUnit testcase time, got {[str(o) for o in offenders]}"
        )


def _check_committed_baseline_present_at_head_is_parsed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repo_dir = Path(tmp)
        content = json.dumps([{
            "kind": "call", "package": "datrix-codegen-aws", "id": "tests/x.py::y",
            "seconds": 12.5, "class": "matrix-in-one-test", "reason": "measured",
        }])
        _init_selftest_git_repo(repo_dir, baseline_content=content)
        committed = load_committed_baseline(repo_dir)
        assert committed is not None and len(committed) == 1 and committed[0].seconds == 12.5, committed


def _check_committed_baseline_absent_at_head_is_first_seed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repo_dir = Path(tmp)
        _init_selftest_git_repo(repo_dir, baseline_content=None)
        assert load_committed_baseline(repo_dir) is None, (
            "a path absent at HEAD must read as None (first seed), never as a git failure"
        )
        # Git words the failure differently once the file exists on disk
        # but is uncommitted -- the state right after the first seed.
        on_disk = repo_dir.joinpath(*_BASELINE_RELPATH)
        on_disk.parent.mkdir(parents=True, exist_ok=True)
        on_disk.write_text("[]", encoding="utf-8")
        assert load_committed_baseline(repo_dir) is None, (
            "a baseline present on disk but absent at HEAD must read as None (first seed)"
        )


def _check_committed_baseline_non_git_directory_fails_closed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repo_dir = Path(tmp)  # never git-init'd
        try:
            load_committed_baseline(repo_dir)
        except RatchetError:
            return
        raise AssertionError(
            "a directory that is not a git repo must fail closed with RatchetError, "
            "never read as an empty baseline"
        )


_SELF_TEST_CHECKS: tuple[tuple[str, Callable[[], None]], ...] = (
    ("call and fixture offenders detected", _check_call_and_fixture_offenders_detected),
    ("offenders clear once baselined", _check_offenders_clear_once_baselined),
    ("stale entries detected", _check_stale_entries_detected),
    ("toolchain-compile entries never stale", _check_toolchain_compile_never_stale),
    ("same-worker fixture repeat is not an offender", _check_same_worker_fixture_not_offender),
    ("call ceiling boundary (30.0 vs 30.1)", _check_call_ceiling_boundary),
    ("xdist group suffix is not part of a call's id", _check_xdist_group_suffix_is_not_part_of_the_id),
    ("fixture ceiling boundary (5.0 vs 5.1)", _check_fixture_ceiling_boundary),
    ("decrease-only rejects a grown/added entry", _check_shrank_grow_violation),
    ("decrease-only allows a shrink", _check_shrank_shrink_allowed),
    ("decrease-only allows an equal value", _check_shrank_equal_allowed),
    ("decrease-only allows a first seed (empty previous)", _check_shrank_first_seed_allowed),
    ("placeholder class is rejected", _check_placeholder_class_rejected),
    ("placeholder reason is rejected", _check_placeholder_reason_rejected),
    ("pytest package with no full run is reported missing", _check_pytest_package_missing_full_run),
    ("Node package with results dir but no v2 full run is reported missing", _check_node_package_missing_full_run_without_junit),
    ("Node package call offender detected from JUnit time", _check_node_package_call_offender_detected),
    ("committed baseline present at HEAD is parsed", _check_committed_baseline_present_at_head_is_parsed),
    ("committed baseline absent at HEAD reads as first seed", _check_committed_baseline_absent_at_head_is_first_seed),
    ("a non-git directory fails closed", _check_committed_baseline_non_git_directory_fails_closed),
)


def self_test() -> int:
    """Run every check, printing ``[OK]``/``[FAIL]`` per check."""
    all_passed = True
    for name, check in _SELF_TEST_CHECKS:
        try:
            check()
        except AssertionError as exc:
            print(f"[FAIL] {name}: {exc}", file=sys.stderr)
            all_passed = False
        else:
            print(f"[OK] {name}")

    if not all_passed:
        print("SELF-TEST FAILED -- the ratchet is not trustworthy.", file=sys.stderr)
        return 1
    print(
        f"Self-test passed: {len(_SELF_TEST_CHECKS)} checks covering offender detection, "
        "decrease-only enforcement (including against a real git HEAD), placeholder rejection, "
        "and Node/pytest fail-closed missing-run reporting."
    )
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _seed(path: Path, offenders: list[Offender], committed_reference: list[BaselineEntry]) -> int:
    provisional = [
        BaselineEntry(
            kind=o.kind, package=o.package, id_=o.id, seconds=o.seconds,
            class_="matrix-in-one-test", reason="seed placeholder -- classify and justify before committing",
        )
        for o in offenders
    ]
    violations = check_baseline_only_shrank(committed_reference, provisional)
    if violations and committed_reference:
        print("ERROR: --seed would grow the baseline relative to the one committed at HEAD:", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        return 2
    seeded = [
        {
            "kind": o.kind, "package": o.package, "id": o.id, "seconds": o.seconds,
            "class": _PLACEHOLDER_CLASS, "reason": _PLACEHOLDER_REASON,
        }
        for o in offenders
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(seeded, indent=2) + "\n", encoding="utf-8")
    print(
        f"Seeded {len(seeded)} entr{'y' if len(seeded) == 1 else 'ies'} to {path}. "
        "Every entry's class/reason placeholder MUST be replaced by hand before commit."
    )
    return 0


def _report_missing_full_run(missing_full_run: list[str]) -> None:
    print(
        "ERROR: no v2 full run recorded for: " + ", ".join(missing_full_run) + ". "
        "Run its suite at the phase boundary (affected-gate.ps1) before trusting this gate.",
        file=sys.stderr,
    )


def _report_offenders_and_stale(offending: list[Offender], stale: list[BaselineEntry]) -> None:
    if offending:
        print(f"\n{len(offending)} un-baselined slow-test offender(s):", file=sys.stderr)
        for o in offending:
            print(f"  {o}", file=sys.stderr)
    if stale:
        print(
            f"\n{len(stale)} stale baseline entr{'y' if len(stale) == 1 else 'ies'} "
            "(no longer an offender -- remove, decrease-only):",
            file=sys.stderr,
        )
        for entry in stale:
            print(f"  {entry.package}/{entry.id}", file=sys.stderr)


def _run(workspace: Path, *, seed: bool) -> int:
    packages = discover_package_suites(workspace)
    path = baseline_path(workspace)
    working_tree_baseline = load_baseline(path)
    committed = load_committed_baseline(datrix_repo_path(workspace))
    committed_reference = committed if committed is not None else []

    if not seed:
        shrink_violations = check_baseline_only_shrank(committed_reference, working_tree_baseline)
        if shrink_violations:
            print(f"ERROR: {path} grew relative to the baseline committed at HEAD (decrease-only):", file=sys.stderr)
            for v in shrink_violations:
                print(f"  {v}", file=sys.stderr)
            return 1

    offenders, missing_full_run = find_offenders(packages)

    if seed:
        return _seed(path, offenders, committed_reference)

    if missing_full_run:
        _report_missing_full_run(missing_full_run)
        return 1

    offending = unbaselined(offenders, working_tree_baseline)
    stale = stale_entries(offenders, working_tree_baseline)
    if offending or stale:
        _report_offenders_and_stale(offending, stale)
        return 1

    print(f"No un-baselined slow tests across {len(packages)} package(s); baseline has {len(working_tree_baseline)} entries.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true", help="run only the self-test")
    parser.add_argument(
        "--seed", action="store_true",
        help="write the baseline from current offenders (refused if it would grow the baseline committed at HEAD)",
    )
    parser.add_argument("--dbg", action="store_true", help="print the resolved workspace root and package list")
    args = parser.parse_args()

    if args.self_test:
        return self_test()
    if self_test() != 0:
        return 1

    workspace = get_datrix_root()
    if args.dbg:
        packages = discover_package_suites(workspace)
        print(f"workspace={workspace}", file=sys.stderr)
        print(f"packages={sorted(packages)}", file=sys.stderr)

    try:
        return _run(workspace, seed=args.seed)
    except RatchetError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
