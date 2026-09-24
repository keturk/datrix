"""Suite-input stamps: what a package run selected and, for a full run, what it read.

Every package run's ``index.json`` records ``selection``: ``{"kind": "full"}``
when nothing narrowed the run, otherwise ``{"kind": "targeted", ...}`` naming
the narrowing that was applied. No reader ever infers from a log whether a run
was full. A FULL run whose every phase completed additionally records
``inputs``: the suite-input fingerprint (see :mod:`test.suite_inputs`) over the
package's cone, the installed distributions, the interpreter, and the paths and
executables the run was observed to touch. A targeted run never records
``inputs`` -- its inputs are not the package's full suite, so a stamp would let
a narrow run stand in for a full one.

This module is what both package runners (the pytest runner and the Node
runner) share:

- :func:`selection_for` builds the ``selection`` object.
- :class:`FullRunStamp` is prepared BEFORE a full run starts. It derives the
  cone once, supplies the runner plugin's environment, and digests the cone's
  trees and the installed set, so a tree edited while the suite ran refuses
  the stamp instead of vouching for content the suite never saw.
- :func:`merge_run_records` reads the runner plugin's per-session record files
  and refuses a set that is incomplete, inconsistent, or unreadable.
- :func:`write_merged_timings` writes the run's merged ``timings.json``.
- :func:`read_distributed_deselected` reads what every worker of a distributed
  phase deselected -- the evidence that decides whether the serial phase has
  anything to run -- and reports a missing record as absent evidence, never as
  zero. :func:`unstamped_recorder_environment` is the plugin's environment for
  a saved run that records only that evidence.

Every refusal is a :class:`SuiteStampError`. A caller that meets one writes no
``inputs`` at all -- never an empty or partial object (:func:`inputs_or_report`).
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from test import suite_inputs
from test.affected_set import UsageError

logger = logging.getLogger(__name__)

#: The pytest plugin that records what a run touched; loaded with ``-p``.
RUNNER_PLUGIN_MODULE: Final[str] = "datrix_common.testing.runner_plugin"
ENV_RUN_DIR: Final[str] = "DATRIX_RUN_DIR"
ENV_SUITE_CONE: Final[str] = "DATRIX_SUITE_CONE"
ENV_WORKSPACE_ROOT: Final[str] = "DATRIX_WORKSPACE_ROOT"

SELECTION_KIND: Final[str] = "kind"
SELECTION_FULL: Final[str] = "full"
SELECTION_TARGETED: Final[str] = "targeted"
#: The tier switches ``test.ps1`` accepts, by name. A tier always narrows a run.
TIERS: Final[frozenset[str]] = frozenset({"unit", "integration", "e2e", "fast", "slow"})

#: The merged timing record written into the run directory of a full run.
MERGED_TIMINGS_NAME: Final[str] = "timings.json"

_RECORD_SCHEMA = 1
_OBSERVED_KIND = "observed"
_DESELECTED_KIND = "deselected"
_TIMINGS_KIND = "timings"
_WORKERS_KIND = "workers"
_SESSION_RECORD_KINDS = (_OBSERVED_KIND, _DESELECTED_KIND, _TIMINGS_KIND)
_RECORD_FILE = re.compile(
    rf"^({_OBSERVED_KIND}|{_DESELECTED_KIND}|{_TIMINGS_KIND}|{_WORKERS_KIND})-([A-Za-z0-9_-]+)\.json$"
)
_WORKER_ID = re.compile(r"[A-Za-z0-9_-]+")
_STANDALONE_SESSION = "main"
_CONTROLLER_SESSION = "controller"
_OBSERVED_BUCKETS = ("opened", "listed", "dlopened", "executables")
_TIMING_ENTRY_KINDS = ("calls", "fixtures")
_RECORD_SCHEMA_KEY = "schema"
_RECORD_WORKER_KEY = "worker"
_WORKERS_KEY = "workers"
_DESELECTED_KEY = "deselected"

_INPUTS_COMPONENTS = "components"
_COMPONENT_TREES = "trees"
_COMPONENT_INSTALLED = "installed"


class SuiteStampError(suite_inputs.SuiteInputsError):
    """A full run's inputs cannot be established, so it is recorded unstamped."""


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


def selection_for(
    *,
    specific: Sequence[str] | None,
    keyword: str | None,
    tier: str | None,
    marker: str | None,
) -> dict[str, object]:
    """The ``selection`` object of a run's ``index.json``.

    A run is FULL only when nothing narrows it: no specific targets, no
    keyword, no tier, and no marker expression. Anything else is targeted and
    names every narrowing that was applied.

    Args:
        specific: The explicit test targets (files or node ids), or None.
        keyword: The keyword / name-pattern filter, or None.
        tier: The ``test.ps1`` tier switch name, or None.
        marker: The marker expression applied, or None.

    Raises:
        ValueError: if *tier* is not one of :data:`TIERS`, or *specific* is
            given but empty (an empty selection names nothing to run).
    """
    if tier is not None and tier not in TIERS:
        raise ValueError(
            f"Unknown test tier {tier!r}. Expected one of {sorted(TIERS)} (the test.ps1 "
            f"switches -Unit/-Integration/-E2E/-Fast/-Slow), or None for no tier."
        )
    if specific is not None and not specific:
        raise ValueError(
            "A specific selection was given but names no target. Pass None for an "
            "unnarrowed run, or at least one test file or node id."
        )
    if specific is None and keyword is None and tier is None and marker is None:
        return {SELECTION_KIND: SELECTION_FULL}
    return {
        SELECTION_KIND: SELECTION_TARGETED,
        "specific": list(specific) if specific is not None else None,
        "keyword": keyword,
        "tier": tier,
        "marker": marker,
    }


def is_full(selection: Mapping[str, object]) -> bool:
    """True iff *selection* is the full, unnarrowed selection."""
    return selection[SELECTION_KIND] == SELECTION_FULL


# ---------------------------------------------------------------------------
# The runner plugin's record files
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MergedRecords:
    """Every session's records of one run, merged.

    ``observed`` carries the four observation buckets as sorted, de-duplicated
    lists of paths -- the shape :func:`test.suite_inputs.classify_observed`
    takes. ``calls``/``fixtures`` are the timing entries, each tagged with the
    ``worker`` whose session produced it.
    """

    observed: dict[str, list[str]]
    calls: list[dict[str, object]]
    fixtures: list[dict[str, object]]


def _record_name(kind: str, session: str) -> str:
    return f"{kind}-{session}.json"


def _session_record_names(session: str) -> set[str]:
    return {_record_name(kind, session) for kind in _SESSION_RECORD_KINDS}


def _read_record(run_dir: Path, kind: str, session: str) -> dict[str, object]:
    path = run_dir / _record_name(kind, session)
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SuiteStampError(
            f"Runner record {path} cannot be read as JSON: {exc}. The runner plugin writes "
            f"every record atomically, so an unreadable one means the run directory was "
            f"tampered with or the plugin failed; re-run the suite."
        ) from exc
    if not isinstance(record, dict):
        raise SuiteStampError(f"Runner record {path} is a {type(record).__name__}; expected an object.")
    header = {key: record[key] for key in (_RECORD_SCHEMA_KEY, _RECORD_WORKER_KEY) if key in record}
    if header != {_RECORD_SCHEMA_KEY: _RECORD_SCHEMA, _RECORD_WORKER_KEY: session}:
        raise SuiteStampError(
            f"Runner record {path} carries header {header!r}; expected schema {_RECORD_SCHEMA} "
            f"and worker {session!r} (the name of the file). A record that does not describe "
            f"the session its name claims cannot be merged; re-run the suite."
        )
    return {str(key): value for key, value in record.items()}


def _record_field(record: dict[str, object], key: str, kind: str, session: str, run_dir: Path) -> object:
    if key not in record:
        raise SuiteStampError(
            f"{_record_name(kind, session)} in {run_dir} has no '{key}' field; the runner "
            f"plugin always writes it, so the record is malformed. Re-run the suite."
        )
    return record[key]


def _controller_workers(run_dir: Path) -> list[str]:
    """The workers the xdist controller of a distributed phase says it ran."""
    if not (run_dir / _record_name(_WORKERS_KIND, _CONTROLLER_SESSION)).is_file():
        raise SuiteStampError(
            f"The distributed phase left no {_record_name(_WORKERS_KIND, _CONTROLLER_SESSION)} "
            f"in {run_dir}. Without the controller's list of workers, a worker that wrote no "
            f"record is indistinguishable from one that never ran, so the run's observed inputs "
            f"cannot be proven complete. Check that the runner plugin was loaded with -p."
        )
    record = _read_record(run_dir, _WORKERS_KIND, _CONTROLLER_SESSION)
    workers = _record_field(record, _WORKERS_KEY, _WORKERS_KIND, _CONTROLLER_SESSION, run_dir)
    if not isinstance(workers, list) or not workers:
        raise SuiteStampError(
            f"The xdist controller's worker list in {run_dir} is {workers!r}; expected a "
            f"non-empty list of worker ids -- a distributed phase that ran no worker ran no test."
        )
    invalid = [worker for worker in workers if not isinstance(worker, str) or not _WORKER_ID.fullmatch(worker)]
    if invalid:
        raise SuiteStampError(
            f"The xdist controller's worker list in {run_dir} holds {invalid!r}, which cannot "
            f"name record files (expected ids matching {_WORKER_ID.pattern}, e.g. gw0)."
        )
    return [str(worker) for worker in workers]


def _expected_sessions(run_dir: Path, *, distributed: bool, standalone: bool) -> list[str]:
    """Every session that must have written the three per-session records."""
    sessions: list[str] = []
    if standalone:
        sessions.append(_STANDALONE_SESSION)
    if distributed:
        sessions.extend(_controller_workers(run_dir))
    if not sessions:
        raise SuiteStampError(
            "No phase of this run loaded the runner plugin (neither a standalone nor a "
            "distributed phase ran), so there are no observed inputs to stamp."
        )
    return sessions


def _require_exact_record_set(run_dir: Path, sessions: list[str], *, distributed: bool) -> None:
    expected: set[str] = set()
    for session in sessions:
        expected |= _session_record_names(session)
    if distributed:
        expected |= {
            _record_name(_OBSERVED_KIND, _CONTROLLER_SESSION),
            _record_name(_WORKERS_KIND, _CONTROLLER_SESSION),
        }
    present = {path.name for path in run_dir.iterdir() if path.is_file() and _RECORD_FILE.match(path.name)}
    missing = sorted(expected - present)
    unexpected = sorted(present - expected)
    if missing or unexpected:
        raise SuiteStampError(
            f"The runner records in {run_dir} do not match the sessions that ran. Missing: "
            f"{missing}; unexpected: {unexpected}. A session writes no record when it crashes "
            f"or meets an operation it cannot interpret, so a missing record means some of what "
            f"the run read is unknown; an unexpected one names a session nothing accounts for. "
            f"Re-run the suite in a fresh run directory."
        )


def _paths(value: object, where: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise SuiteStampError(f"{where} is {type(value).__name__}; expected a list of path strings.")
    return [str(item) for item in value]


def _entries(value: object, where: str) -> list[dict[str, object]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise SuiteStampError(f"{where} is {type(value).__name__}; expected a list of objects.")
    return [{str(key): item_value for key, item_value in item.items()} for item in value]


def _merge_observed(run_dir: Path, sessions: list[str]) -> dict[str, list[str]]:
    buckets: dict[str, set[str]] = {bucket: set() for bucket in _OBSERVED_BUCKETS}
    for session in sessions:
        record = _read_record(run_dir, _OBSERVED_KIND, session)
        for bucket in _OBSERVED_BUCKETS:
            value = _record_field(record, bucket, _OBSERVED_KIND, session, run_dir)
            buckets[bucket].update(_paths(value, f"{_record_name(_OBSERVED_KIND, session)}.{bucket}"))
    return {bucket: sorted(paths) for bucket, paths in buckets.items()}


def _merge_timings(run_dir: Path, sessions: list[str]) -> dict[str, list[dict[str, object]]]:
    merged: dict[str, list[dict[str, object]]] = {kind: [] for kind in _TIMING_ENTRY_KINDS}
    for session in sessions:
        record = _read_record(run_dir, _TIMINGS_KIND, session)
        for kind in _TIMING_ENTRY_KINDS:
            value = _record_field(record, kind, _TIMINGS_KIND, session, run_dir)
            where = f"{_record_name(_TIMINGS_KIND, session)}.{kind}"
            merged[kind].extend({**entry, _RECORD_WORKER_KEY: session} for entry in _entries(value, where))
    return merged


def merge_run_records(run_dir: Path, *, distributed: bool, standalone: bool) -> MergedRecords:
    """Merge the runner plugin's records of one run, refusing an incomplete set.

    The set the run must have left is derived, never assumed from what is
    present: a standalone phase's ``main`` session, and -- for a distributed
    phase -- the controller's own observation record, its worker list, and all
    three records of every worker it lists. Missing and unexpected records are
    both refusals.

    Args:
        run_dir: The run directory the plugin wrote into; created fresh for
            this run, so nothing in it predates the run.
        distributed: A phase ran under pytest-xdist workers.
        standalone: A phase ran in one pytest process (no workers).

    Returns:
        The merged observations and timings.

    Raises:
        SuiteStampError: if the record set is incomplete, has records nothing
            accounts for, or any record is unreadable or malformed.
    """
    sessions = _expected_sessions(run_dir, distributed=distributed, standalone=standalone)
    _require_exact_record_set(run_dir, sessions, distributed=distributed)
    for session in sessions:
        _deselected_count(run_dir, session)
    observed_sessions = [*sessions, _CONTROLLER_SESSION] if distributed else sessions
    timings = _merge_timings(run_dir, sessions)
    return MergedRecords(
        observed=_merge_observed(run_dir, observed_sessions),
        calls=timings["calls"],
        fixtures=timings["fixtures"],
    )


def write_merged_timings(run_dir: Path, records: MergedRecords) -> Path:
    """Write ``timings.json`` -- every session's timings, tagged by worker.

    Created exclusively: a run directory is fresh per run, so an existing file
    means another writer shares it, and it is never overwritten.

    Raises:
        OSError: if the file exists or cannot be written.
    """
    path = run_dir / MERGED_TIMINGS_NAME
    payload = {_RECORD_SCHEMA_KEY: _RECORD_SCHEMA, "calls": records.calls, "fixtures": records.fixtures}
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return path


# ---------------------------------------------------------------------------
# What a distributed phase deselected
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DeselectedEvidence:
    """What a distributed phase's records say its workers deselected.

    ``counts`` maps every worker the xdist controller listed to the number of
    collected items that worker deselected. ``absent`` says why the records are
    NOT complete evidence -- the controller left no worker list, or a worker it
    listed wrote no deselected record (it crashed, or refused records it could
    not trust) -- and is None only when ``counts`` covers every listed worker.
    """

    counts: Mapping[str, int]
    absent: str | None


def _deselected_count(run_dir: Path, session: str) -> int:
    """*session*'s ``deselected`` count, read from its validated record."""
    record = _read_record(run_dir, _DESELECTED_KIND, session)
    value = _record_field(record, _DESELECTED_KEY, _DESELECTED_KIND, session, run_dir)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise SuiteStampError(
            f"{_record_name(_DESELECTED_KIND, session)} in {run_dir} records deselected={value!r}; "
            f"expected a non-negative integer count of deselected items. The runner plugin always "
            f"writes one, so the record is malformed; re-run the suite."
        )
    return value


def read_distributed_deselected(run_dir: Path) -> DeselectedEvidence:
    """The deselected count of every worker a distributed phase ran.

    The set of workers is the controller's own list, never the set of record
    files present: a worker that wrote nothing is exactly the one a glob would
    miss. Missing evidence is reported through ``absent`` -- the caller must
    treat it as "unknown", never as zero.

    Args:
        run_dir: The run directory the distributed phase's runner plugin wrote
            into, read before any later phase of the run writes to it.

    Raises:
        SuiteStampError: a record is unreadable, names another session, has
            no count or a count that is not a non-negative integer, the
            controller's worker list is empty or malformed, or a deselected
            record names a session the controller did not list.
    """
    workers_record = _record_name(_WORKERS_KIND, _CONTROLLER_SESSION)
    if not (run_dir / workers_record).is_file():
        return DeselectedEvidence(
            counts={},
            absent=(
                f"the parallel phase left no {workers_record} in {run_dir} (the runner plugin was "
                f"not loaded, or the xdist controller did not finish its session)"
            ),
        )
    workers = _controller_workers(run_dir)
    expected = {_record_name(_DESELECTED_KIND, worker) for worker in workers}
    present = {
        path.name
        for path in run_dir.iterdir()
        if path.is_file() and path.name.startswith(f"{_DESELECTED_KIND}-") and _RECORD_FILE.match(path.name)
    }
    unexpected = sorted(present - expected)
    if unexpected:
        raise SuiteStampError(
            f"{run_dir} holds deselected record(s) {unexpected} for sessions the xdist controller did "
            f"not list (it listed {workers}). Nothing accounts for them, so the parallel phase's "
            f"deselected counts cannot be trusted; re-run in a fresh run directory."
        )
    missing = sorted(expected - present)
    if missing:
        return DeselectedEvidence(
            counts={},
            absent=(
                f"worker record(s) {missing} are missing from {run_dir}: a worker the controller "
                f"listed wrote no deselected count (it crashed, or refused records it could not trust)"
            ),
        )
    return DeselectedEvidence(counts={worker: _deselected_count(run_dir, worker) for worker in workers}, absent=None)


def _plugin_environment(run_dir: Path, cone: Sequence[str], workspace: Path) -> dict[str, str]:
    return {
        ENV_RUN_DIR: str(run_dir.resolve()),
        ENV_SUITE_CONE: os.pathsep.join(cone),
        ENV_WORKSPACE_ROOT: str(workspace.resolve()),
    }


def unstamped_recorder_environment(run_dir: Path, workspace: Path, package_root: Path) -> dict[str, str]:
    """The runner plugin's environment for a saved run that is never stamped.

    Such a run (a targeted one, or a full one whose stamp could not be
    prepared) loads the plugin in its parallel phase only for the deselected
    counts that decide whether the serial phase has anything to run. The
    plugin validates ``DATRIX_SUITE_CONE`` but never filters by it, and the
    records of an unstamped run are never classified against a cone, so the
    cone it is given is the package's own tree: deriving the real cone would
    cost a workspace scan for a value nothing reads.
    """
    return _plugin_environment(run_dir, (str(package_root.resolve()),), workspace)


# ---------------------------------------------------------------------------
# The stamp of a full run
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FullRunStamp:
    """What a full run will be stamped against, captured before it starts.

    ``trees_at_start`` and ``installed_at_start`` are the cone's tree digests
    and the installed-dependencies digest (Python distributions plus every Node
    cone package's installed state) when the run began. The stamp is refused when
    either differs at the end: a suite that ran against content someone edited
    mid-run must not vouch for the edited content.
    """

    workspace: Path
    package: str
    cone: tuple[str, ...]
    trees_at_start: Mapping[str, str]
    installed_at_start: str

    @classmethod
    def prepare(cls, workspace: Path, package: str) -> FullRunStamp:
        """Derive *package*'s cone (one workspace scan) and capture its start state.

        Raises:
            UsageError: if the cone cannot be derived or a tree read.
        """
        root = workspace.resolve()
        return cls.for_cone(root, package, suite_inputs.package_cone(root, package))

    @classmethod
    def for_cone(cls, workspace: Path, package: str, cone: Sequence[str]) -> FullRunStamp:
        """Capture the start state of an already-derived cone.

        Raises:
            SuiteStampError: if *cone* does not contain *package*.
            UsageError: if a tree cannot be read.
        """
        roots = tuple(str(Path(root).resolve()) for root in cone)
        if package not in {Path(root).name for root in roots}:
            raise SuiteStampError(
                f"Cone {list(roots)} does not contain '{package}'. A package's cone always "
                f"holds the package itself; pass the cone package_cone() derived for it."
            )
        return cls(
            workspace=workspace.resolve(),
            package=package,
            cone=roots,
            trees_at_start={Path(root).name: suite_inputs.tree_digest(Path(root)) for root in roots},
            installed_at_start=suite_inputs.installed_digest(roots),
        )

    def plugin_environment(self, run_dir: Path) -> dict[str, str]:
        """The three variables the runner plugin requires in every pytest phase."""
        return _plugin_environment(run_dir, self.cone, self.workspace)

    def inputs_for(self, observed: suite_inputs.ObservedInputs) -> dict[str, object]:
        """The run's ``inputs`` object, refusing a state that changed mid-run.

        Raises:
            SuiteStampError: if a cone tree or the installed set changed since
                :meth:`prepare`.
            UsageError: if any component cannot be established.
        """
        inputs = suite_inputs.compute_inputs(self.workspace, self.package, observed, cone=self.cone)
        self._require_unchanged_since_start(inputs)
        return inputs

    def inputs_from_records(self, records: MergedRecords) -> dict[str, object]:
        """Classify a run's merged records and assemble its ``inputs`` object.

        Raises:
            SuiteStampError / UsageError: see :meth:`inputs_for` and
                :func:`test.suite_inputs.classify_observed`.
        """
        observed = suite_inputs.classify_observed(records.observed, self.cone, self.workspace)
        return self.inputs_for(observed)

    def _require_unchanged_since_start(self, inputs: dict[str, object]) -> None:
        components = inputs[_INPUTS_COMPONENTS]
        if not isinstance(components, dict):
            raise SuiteStampError(f"compute_inputs returned components of type {type(components).__name__}.")
        trees_now = components[_COMPONENT_TREES]
        if not isinstance(trees_now, dict):
            raise SuiteStampError(f"compute_inputs returned trees of type {type(trees_now).__name__}.")
        changed = sorted(
            name
            for name in set(self.trees_at_start) | set(trees_now)
            if name not in trees_now or name not in self.trees_at_start or trees_now[name] != self.trees_at_start[name]
        )
        if components[_COMPONENT_INSTALLED] != self.installed_at_start:
            changed.append("installed dependencies")
        if changed:
            raise SuiteStampError(
                f"{', '.join(changed)} changed while the suite ran. The run tested content that "
                f"no longer exists, so it cannot vouch for the current state. A tree also "
                f"changes when a test writes a file git does not ignore into it; re-run the "
                f"suite with no concurrent edits (and fix any test that writes into a package)."
            )


def inputs_or_report(
    compute: Callable[[], dict[str, object]], report: Callable[[str], None]
) -> dict[str, object] | None:
    """Run *compute*; on a refusal, report why and return None (no ``inputs``).

    None is the fail-closed outcome: the run's ``index.json`` then records its
    selection and no ``inputs``, so nothing can carry its verdict.
    """
    try:
        return compute()
    except (UsageError, OSError) as exc:
        report(
            f"This full run is recorded WITHOUT a suite-input stamp: {exc} "
            f"index.json records its selection but no inputs, so its verdict cannot be "
            f"carried by the affected-set gate."
        )
        logger.warning("suite_stamp_omitted reason=%s", exc)
        return None


def prepare_full_run_stamp(
    selection: Mapping[str, object],
    run_dir: Path | None,
    workspace: Path,
    package: str,
    report: Callable[[str], None],
) -> FullRunStamp | None:
    """The stamp to prepare before a run starts, or None when the run writes no ``inputs``.

    None when the run is targeted (never stamped), when it saves no run
    directory (nowhere to record), or when the stamp cannot be prepared -- the
    last is reported through *report*, and the suite still runs.
    """
    if not is_full(selection) or run_dir is None:
        return None
    try:
        return FullRunStamp.prepare(workspace, package)
    except (UsageError, OSError) as exc:
        report(
            f"The suite-input stamp cannot be prepared for {package}: {exc} The suite runs, "
            f"but its index.json will record no inputs."
        )
        logger.warning("suite_stamp_not_prepared package=%s reason=%s", package, exc)
        return None
