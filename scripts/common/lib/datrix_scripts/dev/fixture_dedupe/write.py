"""Write a dedupe plan, proven before and after writing, and record it.

``write_run`` builds the plan and lists it as ``--dry-run`` does, then:

1. refuses, writing nothing, when the listing fails (a walk site or a staying reference the plan cannot
   prove), or when the accessor the rewritten tests import reads another corpus than the workspace's;
2. proves the write set over the planned tree (``proof``): a failure refuses, writing nothing;
3. hashes every semantic-baseline entry before writing (``baseline``);
4. records the bytes of every file it replaces under ``<workspace>/.tmp/fixture-dedupe/<time>/old/``, then
   creates the shared files, rewrites the changed files, and deletes the copies and the directories their
   deletion empties;
5. proves the write again over the disk and checks each package's baseline drift. A failure, or an error
   while writing, puts every replaced file back from the record and removes every file and directory the
   write created, then refuses;
6. writes each package's manifest with the move's changes and the record, ``record.json``: old -> new, the
   files created, changed and deleted, the proof's counts, each package's translated, deleted and arriving
   keys, and the test sites refused for a hand edit.

It runs no git command.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final

from datrix_testing.semantic_baseline import load_semantic_baseline, write_semantic_baseline

from datrix_scripts.dev.fixture_dedupe.baseline import (
    BaselineBefore,
    BaselineError,
    baseline_corpora,
    baseline_failures,
    hash_after,
    hash_before,
    updated_manifest,
)
from datrix_scripts.dev.fixture_dedupe.follow import reference_rewrites
from datrix_scripts.dev.fixture_dedupe.layout import corpus_root
from datrix_scripts.dev.fixture_dedupe.listing import list_plan
from datrix_scripts.dev.fixture_dedupe.plan import Plan, build_plan
from datrix_scripts.dev.fixture_dedupe.proof import DiskTree, PlannedTree, Proof, WriteSet, prove, write_set
from datrix_scripts.dev.fixture_dedupe.secret_screen import ScreenError
from datrix_scripts.framework_repos import PackageMarker
from datrix_scripts.gate_harness import EXIT_PASS, EXIT_USAGE, EXIT_VIOLATION, report_step
from datrix_scripts.gates.ratchet.fixture_budget_gate import FixtureScanError

RECORD_DIR: Final = Path(".tmp") / "fixture-dedupe"
RECORD_FILE: Final = "record.json"
OLD_DIR: Final = "old"
_STAMP: Final = "%Y%m%d-%H%M%S-%f"
_SHOWN_FAILURES: Final = 50


class RestoreError(Exception):
    """A rollback could not put the workspace back as it was: the record holds every replaced file."""


class WriteRefused(Exception):
    """The write is refused before anything is written."""


@dataclass(frozen=True)
class _Baseline:
    """One package's baseline once written: what its record says and the manifest it gets."""

    package: str
    record: dict[str, list[str]]
    manifest: dict[str, str]
    before: BaselineBefore


class WriteTransaction:
    """The files one write creates, replaces and deletes, and how to put them back."""

    def __init__(self, base_dir: Path, old: Mapping[Path, bytes], record: Path) -> None:
        self._base_dir = base_dir
        self._old = old
        self._record = record
        self._created_files: list[Path] = []
        self._created_dirs: list[Path] = []

    def keep_old(self) -> None:
        """Copy the bytes of every replaced file under the record, before anything is written."""
        for path, data in self._old.items():
            kept = self._record / OLD_DIR / path.relative_to(self._base_dir)
            kept.parent.mkdir(parents=True, exist_ok=True)
            kept.write_bytes(data)

    def _make_parents(self, path: Path) -> None:
        missing = [parent for parent in path.parents if not parent.exists()]
        for directory in reversed(missing):
            directory.mkdir()
            self._created_dirs.append(directory)

    def apply(self, write: WriteSet, stops: Sequence[Path]) -> None:
        """Create, rewrite and delete what *write* names; prune each directory a deletion empties, up to the
        nearest of *stops* (each package's ``tests/``)."""
        for path, data in write.created.items():
            self._make_parents(path)
            path.write_bytes(data)
            self._created_files.append(path)
        for path, data in write.changed.items():
            path.write_bytes(data)
        for path in write.deleted:
            path.unlink()
            _prune(path.parent, stops)

    def restore(self) -> None:
        """Remove what the write created and put every replaced file back.

        Raises:
            RestoreError: A file does not read back as it was.
        """
        for path in reversed(self._created_files):
            path.unlink(missing_ok=True)
        for directory in reversed(self._created_dirs):
            if directory.is_dir() and not any(directory.iterdir()):
                directory.rmdir()
        for path, data in self._old.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        wrong = [path for path, data in self._old.items() if path.read_bytes() != data]
        wrong.extend(path for path in self._created_files if path.exists())
        if wrong:
            raise RestoreError(
                f"the rollback left {len(wrong)} file(s) other than they were, first {wrong[0]}. Fix: copy each "
                f"file back from {self._record / OLD_DIR} and delete the shared files the record lists."
            )


def _prune(directory: Path, stops: Sequence[Path]) -> None:
    """Remove *directory* and each parent the removal empties, never one of *stops* or one above them."""
    while directory not in stops and any(directory.is_relative_to(stop) for stop in stops):
        if any(directory.iterdir()):
            return
        directory.rmdir()
        directory = directory.parent


def old_bytes(write: WriteSet) -> dict[Path, bytes]:
    """The bytes of every file *write* replaces, as they are now.

    Raises:
        FixtureScanError: A file it creates already exists, or one it replaces cannot be read.
    """
    existing = [path for path in write.created if path.exists()]
    if existing:
        raise FixtureScanError(
            f"the write would overwrite {existing[0]}, which exists. Fix: rebuild the plan from the files as they are now."
        )
    try:
        return {path: path.read_bytes() for path in write.replaced}
    except OSError as exc:
        raise FixtureScanError(
            f"cannot read a file the write replaces: {exc}. Fix: rebuild the plan from the files as they are now."
        ) from exc


def _print_failures(title: str, failures: Sequence[str]) -> None:
    report_step(f"{title} ({len(failures)})")
    for failure in failures[:_SHOWN_FAILURES]:
        print(f"  {failure}")
    if len(failures) > _SHOWN_FAILURES:
        print(f"  ... and {len(failures) - _SHOWN_FAILURES} more")


def _print_proof(title: str, proof: Proof) -> None:
    report_step(f"{title}: {proof.texts} texts, {proof.references} references, {proof.sites} test sites read back")


def _rel(path: Path, base_dir: Path) -> str:
    return path.relative_to(base_dir).as_posix()


def _record(plan: Plan, write: WriteSet, proofs: Sequence[Proof], baselines: Sequence[_Baseline]) -> dict[str, object]:
    base_dir = plan.base_dir
    return {
        "workspace": str(base_dir),
        "moves": {_rel(old, base_dir): _rel(new, base_dir) for old, new in plan.followed.moves.items()},
        "created": sorted(_rel(path, base_dir) for path in write.created),
        "changed": sorted(_rel(path, base_dir) for path in write.changed),
        "deleted": sorted(_rel(path, base_dir) for path in write.deleted),
        "proof": [{"texts": p.texts, "references": p.references, "sites": p.sites, "failures": len(p.failures)} for p in proofs],
        "baselines": {baseline.package: baseline.record for baseline in baselines},
        "refused_sites": [
            {"module": _rel(site.module, base_dir), "line": site.line, "written": site.written, "reason": site.reason}
            for site in plan.sites.refused
        ],
    }


def _written_baselines(befores: Sequence[BaselineBefore]) -> tuple[list[_Baseline], list[str]]:
    """Each package's baseline once written, and each change the move may not cause."""
    baselines: list[_Baseline] = []
    failures: list[str] = []
    for before in befores:
        after = hash_after(before.corpus)
        package = before.corpus.package_root.name
        failures.extend(f"{package}: {line}" for line in baseline_failures(before, after))
        record = {
            "translated": sorted(before.translated - before.deleted),
            "deleted": sorted(before.deleted & set(before.plain)),
            "arrived": sorted(after.corpus_keys - set(before.plain)),
        }
        manifest = updated_manifest(load_semantic_baseline(before.corpus), before, after)
        baselines.append(_Baseline(package, record, manifest, before))
    return baselines, failures


def _planned_proof(plan: Plan, accessor_corpus: Path, write: WriteSet, old: Mapping[Path, bytes]) -> Proof:
    """The proof of *write* over the planned tree, printed.

    Raises:
        WriteRefused: The rewritten tests' accessor reads another corpus, or the proof fails.
    """
    if accessor_corpus.resolve() != corpus_root(plan.base_dir).resolve():
        raise WriteRefused(
            f"the accessor the rewritten tests import reads the corpus {accessor_corpus}, not this workspace's "
            f"{corpus_root(plan.base_dir)}, so they would read other files; nothing is written. Fix: install "
            "datrix-testing editable from this workspace, or point -BaseDir at the workspace it is installed from."
        )
    proof = prove(plan, PlannedTree(write), old)
    _print_proof("Proof over the planned tree", proof)
    if proof.failures:
        _print_failures("Proof failures over the planned tree", proof.failures)
        raise WriteRefused("the planned write would change what a reader reads; nothing is written.")
    return proof


def write_plan(plan: Plan, accessor_corpus: Path) -> int:
    """Prove, write and record *plan*; *accessor_corpus* is the corpus the rewritten tests' accessor reads.

    Returns ``EXIT_PASS`` written and proven, ``EXIT_VIOLATION`` refused with nothing written or with
    everything written put back.

    Raises:
        FixtureScanError: A file the write reads cannot be read or is not as the plan read it.
        BaselineError: A semantic-baseline entry cannot be analyzed (anything written is put back first).
        RestoreError: A rollback could not put a file back.
    """
    write = write_set(plan)
    old = old_bytes(write)
    try:
        planned = _planned_proof(plan, accessor_corpus, write, old)
    except WriteRefused as exc:
        print(f"\nFAILED: {exc}")
        return EXIT_VIOLATION
    rewritten = reference_rewrites(plan.followed.rewrites)
    befores = [
        hash_before(corpus, plan.followed.moves, rewritten) for corpus in baseline_corpora(plan.base_dir, plan.packages)
    ]
    record = plan.base_dir / RECORD_DIR / datetime.now().strftime(_STAMP)
    held = {**old, **{before.corpus.manifest_path: before.corpus.manifest_path.read_bytes() for before in befores}}
    transaction = WriteTransaction(plan.base_dir, held, record)
    transaction.keep_old()
    try:
        transaction.apply(write, [package / PackageMarker.TESTS.value for package in plan.packages])
        written = prove(plan, DiskTree(), old)
        baselines, failures = _written_baselines(befores)
        failures[:0] = written.failures
        if not failures:
            for baseline in baselines:
                write_semantic_baseline(baseline.before.corpus, baseline.manifest)
    except BaseException:
        transaction.restore()
        raise
    _print_proof("Proof over the written tree", written)
    if failures:
        transaction.restore()
        _print_failures("Failures once written", failures)
        print(f"\nFAILED: the written tree differs from what its readers read; every file is put back (record {record}).")
        return EXIT_VIOLATION
    (record / RECORD_FILE).write_text(json.dumps(_record(plan, write, (planned, written), baselines), indent=2), encoding="utf-8")
    print(
        f"\nWritten: {len(write.created)} created, {len(write.changed)} changed, {len(write.deleted)} deleted; "
        f"semantic baselines proven in {len(baselines)} package(s); record {record / RECORD_FILE}"
    )
    return EXIT_PASS


def write_run(base_dir: Path, accessor_corpus: Path) -> int:
    """Build, list, prove, write and record the plan of *base_dir*; the exit code of the run: 0 written and
    proven, 1 refused (nothing written, or everything written put back), 2 a file, capture or baseline entry
    that cannot be read, run or analyzed."""
    try:
        plan = build_plan(base_dir)
        listed = list_plan(plan)
        if listed != EXIT_PASS:
            return listed
        return write_plan(plan, accessor_corpus)
    except (FixtureScanError, ScreenError, BaselineError, RestoreError) as exc:
        print(f"\nERROR: {exc}")
        return EXIT_USAGE
