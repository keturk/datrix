"""Which of a job's failing tests are still failing, by test id, across every run since.

The module behind ``test/failure-ledger.ps1`` (and its ``.sh`` twin). A multi-suite fix job starts
from several ``index.json`` files. Whether the job is finished is a fact about those tests' ids, not
about a pin count or a green file: this script keeps the starting runs, then replays every later run
of each package in time order and reports, per test id, the last verdict a run gave it.

* ``--runs <index.json,...>`` stores the starting runs (the ledger) and prints each package's failing ids.
* ``--status`` reads the ledger, loads every ``.test_results/test-results-*/index.json`` of each package
  at or after its earliest starting run, and prints one row per package plus every id still open.

An id is **open** when the last run that covered its test file failed it (``FAILING``), or when no run
since has covered its file at all (``NOT-RERUN``). A run covers a file when its selection is ``full``,
or a ``-Specific`` selection names the file (or a directory holding it); a ``-Tag`` / ``-Keyword``
selection names no file and covers nothing here. An id that fails in a later run and was not in a
starting run is ``NEW`` (a regression, or a failure a starting run never reached) and is open until a
later covering run passes it. The job is finished at **zero open ids**; the exit code is 0 then, else 1.

Warnings are not in ``index.json``; ``extract-warnings.ps1`` owns them.

Usage:
    python -m datrix_scripts.test.failure_ledger --runs <index.json[,index.json...]>
    python -m datrix_scripts.test.failure_ledger --status

Exit codes: 0 no open id (or the ledger stored), 1 open ids, 2 usage error.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from datrix_scripts.dev.arguments import comma_values
from datrix_scripts.gate_harness import WRAPPER_DEBUG_FLAG, UsageError, expect_usage_error, write_files
from datrix_scripts.paths import TMP_DIR
from datrix_scripts.test.wrappers import TEST_SCRIPTS_DIR, module_main, run_self_test

MODULE: Final = "datrix_scripts.test.failure_ledger"
WRAPPER: Final = "failure-ledger"
EXIT_OK: Final[int] = 0
EXIT_OPEN: Final[int] = 1
LEDGER_FILE: Final[Path] = TMP_DIR / "failure-ledger" / "ledger.json"
RUN_GLOB: Final = "test-results-*/index.json"
FULL_KIND: Final = "full"
MAX_IDS_PRINTED: Final = 40

FAILING: Final = "FAILING"
NOT_RERUN: Final = "NOT-RERUN"
NEW: Final = "NEW"
PASSED: Final = "PASSED"


@dataclass(frozen=True)
class Run:
    """One ``index.json``: its package, when it ran, what it selected and the ids it failed."""

    project: str
    timestamp: str
    path: Path
    kind: str
    specific: tuple[str, ...]
    failing: dict[str, str]


def _normal(path: str) -> str:
    text = path.replace("\\", "/").lower().strip()
    text = text.split("::", 1)[0]
    return text[2:] if text.startswith("./") else text


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def load_run(path: Path) -> Run:
    """Parse one ``index.json``; a file that is not a run raises ``UsageError`` naming it."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise UsageError(f"{path} is not a readable index.json: {exc}") from exc
    if not isinstance(data, dict) or not _text(data.get("project")) or not _text(data.get("timestamp")):
        raise UsageError(f"{path} holds no 'project' and 'timestamp': it is not a test run's index.json.")
    selection = data.get("selection")
    selection = selection if isinstance(selection, dict) else {}
    specific = selection.get("specific")
    failing: dict[str, str] = {}
    for key in ("failures", "errors"):
        for entry in data.get(key) or []:
            if isinstance(entry, dict) and _text(entry.get("test_id")):
                failing[_text(entry["test_id"])] = _normal(_text(entry.get("file")))
    return Run(
        project=_text(data["project"]),
        timestamp=_text(data["timestamp"]),
        path=path.resolve(),
        kind=_text(selection.get("kind")),
        specific=tuple(_normal(item) for item in specific if isinstance(item, str))
        if isinstance(specific, list)
        else (),
        failing=failing,
    )


def covers(run: Run, test_file: str) -> bool:
    """Whether *run* ran every test of *test_file*: a full run, or a ``-Specific`` naming it or its directory."""
    if run.kind == FULL_KIND:
        return True
    return any(test_file == entry or test_file.startswith(entry.rstrip("/") + "/") for entry in run.specific)


def package_runs(start: Run) -> list[Run]:
    """Every run of *start*'s package at or after it, oldest first (the start itself included)."""
    results_dir = start.path.parent.parent
    runs: list[Run] = []
    for index in results_dir.glob(RUN_GLOB):
        try:
            run = load_run(index)
        except UsageError:
            continue  # a run directory without a finished index.json is still being written
        if run.project == start.project and run.timestamp >= start.timestamp:
            runs.append(run)
    return sorted(runs, key=lambda run: (run.timestamp, str(run.path)))


def verdict(test_id: str, test_file: str, runs: Sequence[Run]) -> str:
    """The last verdict the runs gave *test_id*: FAILING (it failed last) or PASSED (a covering run passed it after)."""
    state = ""
    for run in runs:
        if test_id in run.failing:
            state = FAILING
        elif state and covers(run, test_file):
            state = PASSED
    return state


def _replay(starts: Sequence[Run]) -> tuple[dict[str, dict[str, list[tuple[str, str]]]], dict[str, int]]:
    """Per package, its open ids with their verdicts, and its tallies."""
    open_ids: dict[str, dict[str, list[tuple[str, str]]]] = {}
    tallies: dict[str, int] = {}
    by_project: dict[str, list[Run]] = {}
    for start in starts:
        by_project.setdefault(start.project, []).append(start)
    for project, project_starts in sorted(by_project.items()):
        earliest = min(project_starts, key=lambda run: run.timestamp)
        runs = package_runs(earliest)
        start_paths = {run.path for run in project_starts}
        baseline = {test_id for run in runs if run.path in start_paths for test_id in run.failing}
        files = {test_id: test_file for run in runs for test_id, test_file in run.failing.items()}
        rows: dict[str, list[tuple[str, str]]] = {}
        passed = 0
        for test_id, test_file in sorted(files.items()):
            if verdict(test_id, test_file, runs) == PASSED:
                passed += 1
                continue
            rerun = any(covers(run, test_file) and run.path not in start_paths for run in runs)
            label = FAILING if rerun else NOT_RERUN
            if test_id not in baseline:
                label = NEW
            rows.setdefault(label, []).append((test_id, test_file))
        open_ids[project] = rows
        tallies[project] = len(baseline)
        tallies[f"{project}:passed"] = passed
        tallies[f"{project}:runs"] = len(runs)
    return open_ids, tallies


def store(paths: Sequence[Path], ledger_file: Path = LEDGER_FILE) -> list[Run]:
    """Save the starting runs and return them parsed."""
    if not paths:
        raise UsageError("-Runs needs at least one index.json path.")
    starts = []
    for path in paths:
        if path.name != "index.json" or not path.is_file():
            raise UsageError(f"-Runs {path} is not an existing index.json.")
        starts.append(load_run(path))
    ledger_file.parent.mkdir(parents=True, exist_ok=True)
    ledger_file.write_text(json.dumps({"runs": [str(run.path) for run in starts]}, indent=2), encoding="utf-8")
    return starts


def load_ledger(ledger_file: Path = LEDGER_FILE) -> list[Run]:
    """The stored starting runs; a missing ledger is a usage error that names the fix."""
    if not ledger_file.is_file():
        raise UsageError(f"No ledger at {ledger_file}. Store the job's starting runs first: -Runs <index.json,...>.")
    stored = json.loads(ledger_file.read_text(encoding="utf-8"))
    return [load_run(Path(item)) for item in stored["runs"]]


def _print_status(starts: Sequence[Run]) -> int:
    open_ids, tallies = _replay(starts)
    total_open = 0
    print(f"{'package':<30} {'start':>5} {'passed':>6} {'FAILING':>7} {'NOT-RERUN':>9} {'NEW':>4}  runs")
    for project, rows in open_ids.items():
        counts = {label: len(rows.get(label, [])) for label in (FAILING, NOT_RERUN, NEW)}
        total_open += sum(counts.values())
        print(
            f"{project:<30} {tallies[project]:>5} {tallies[project + ':passed']:>6} {counts[FAILING]:>7} "
            f"{counts[NOT_RERUN]:>9} {counts[NEW]:>4}  {tallies[project + ':runs']}"
        )
    for project, rows in open_ids.items():
        for label, ids in rows.items():
            for test_id, _ in ids[:MAX_IDS_PRINTED]:
                print(f"  [{label}] {project}: {test_id}")
            if len(ids) > MAX_IDS_PRINTED:
                print(f"  [{label}] {project}: ... {len(ids) - MAX_IDS_PRINTED} more")
    print(f"LEDGER: {total_open} open id(s). Warnings are not tracked here (extract-warnings.ps1).")
    return EXIT_OPEN if total_open else EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    """The options of ``test/failure-ledger.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        prog=WRAPPER, description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False
    )
    parser.add_argument(
        "--runs",
        action="append",
        default=[],
        help="Store the job's starting index.json files (repeatable or comma-separated).",
    )
    parser.add_argument(
        "--status", action="store_true", help="Replay every run since the stored ones and list the open ids."
    )
    parser.add_argument(WRAPPER_DEBUG_FLAG, dest="debug", action="store_true", help="Debug logging.")
    parser.add_argument("--self-test", action="store_true", help="Run only the self-test over planted runs.")
    parser.set_defaults(debug=False)
    return parser


def _plant_run(
    root: Path, project: str, name: str, stamp: str, selection: str, failing: Sequence[tuple[str, str]]
) -> Path:
    entries = ",".join(f'{{"test_id": "{test_id}", "file": "{test_file}"}}' for test_id, test_file in failing)
    relative = f"{project}/.test_results/{name}/index.json"
    body = f'{{"project": "{project}", "timestamp": "{stamp}", "selection": {selection}, "failures": [{entries}], "errors": []}}'
    write_files(root, {relative: body})
    return root / relative


_A = ("tests.a::t1", "tests/unit/a.py")
_B = ("tests.b::t2", "tests/unit/b.py")
_FULL = '{"kind": "full"}'


def _open_labels(starts: Sequence[Run]) -> dict[str, str]:
    open_ids, _ = _replay(starts)
    return {test_id: label for rows in open_ids.values() for label, ids in rows.items() for test_id, _ in ids}


def _check_ids_stay_open_until_rerun() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        start = _plant_run(Path(tmp), "pkg", "test-results-1", "2026-01-01T10:00:00", _FULL, [_A, _B])
        labels = _open_labels([load_run(start)])
        assert labels == {_A[0]: NOT_RERUN, _B[0]: NOT_RERUN}, f"no later run leaves both unproven, got {labels}"


def _check_a_covering_run_closes_only_what_it_covers() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        start = _plant_run(root, "pkg", "test-results-1", "2026-01-01T10:00:00", _FULL, [_A, _B])
        _plant_run(
            root,
            "pkg",
            "test-results-2",
            "2026-01-01T11:00:00",
            '{"kind": "targeted", "specific": ["tests\\\\unit\\\\a.py"]}',
            [],
        )
        _plant_run(root, "pkg", "test-results-3", "2026-01-01T12:00:00", '{"kind": "targeted", "tags": ["x"]}', [])
        labels = _open_labels([load_run(start)])
        assert labels == {_B[0]: NOT_RERUN}, f"only the file a -Specific run named is closed, got {labels}"


def _check_a_failing_rerun_and_a_new_failure_stay_open() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        start = _plant_run(root, "pkg", "test-results-1", "2026-01-01T10:00:00", _FULL, [_A])
        later = ("tests.c::t3", "tests/unit/c.py")
        _plant_run(
            root,
            "pkg",
            "test-results-2",
            "2026-01-01T11:00:00",
            '{"kind": "targeted", "specific": ["tests/unit/a.py"]}',
            [_A],
        )
        _plant_run(root, "pkg", "test-results-3", "2026-01-01T12:00:00", _FULL, [_A, later])
        labels = _open_labels([load_run(start)])
        assert labels == {_A[0]: FAILING, later[0]: NEW}, (
            f"a rerun that failed is FAILING and an unseen id NEW, got {labels}"
        )


def _check_a_full_green_run_closes_everything() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        start = _plant_run(root, "pkg", "test-results-1", "2026-01-01T10:00:00", _FULL, [_A, _B])
        _plant_run(root, "pkg", "test-results-2", "2026-01-01T11:00:00", _FULL, [])
        assert not _open_labels([load_run(start)]), "a later full run that fails nothing closes every id"


def _check_the_ledger_round_trips_and_refuses_bad_input() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        start = _plant_run(root, "pkg", "test-results-1", "2026-01-01T10:00:00", _FULL, [_A])
        ledger = root / "ledger.json"
        assert [run.path for run in store([start], ledger)] == [start.resolve()]
        assert [run.path for run in load_ledger(ledger)] == [start.resolve()]
        expect_usage_error(lambda: store([root / "missing" / "index.json"], ledger), "not an existing index.json")
        expect_usage_error(lambda: store([], ledger), "at least one")
        expect_usage_error(lambda: load_ledger(root / "none.json"), "No ledger")


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        checks = [
            _check_ids_stay_open_until_rerun,
            _check_a_covering_run_closes_only_what_it_covers,
            _check_a_failing_rerun_and_a_new_failure_stay_open,
            _check_a_full_green_run_closes_everything,
            _check_the_ledger_round_trips_and_refuses_bad_input,
        ]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=TEST_SCRIPTS_DIR)
    runs = comma_values(args.runs)
    if bool(runs) == args.status:
        raise UsageError(
            "Pass exactly one of -Runs <index.json,...> (store the starting runs) or -Status (check them)."
        )
    if args.status:
        return _print_status(load_ledger())
    starts = store([Path(item) for item in runs])
    return _print_status(starts)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
