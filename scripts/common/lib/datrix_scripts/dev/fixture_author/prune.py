"""``fixture-author.ps1 repoint -Package <p> -Prune``: delete the fixture files a repointed package no longer reads.

Run after ``repoint -Package <p>`` and after its queue is finished by hand: it is refused while
``queue/repoint-<package>--*.md`` holds a module, since a queued module still reads the files it was not
repointed off. A run finding an undo record an interrupted run left writes it back first.

The files deleted are the package's fixture files nothing reads (``prune_reads.kept_fixture_files``: needs
discovery rerun over the modules as they are now, the directories they read whole, the diagnostics harness
tree, and what a kept file reaches). Each is saved to ``.tmp/fixture-author/undo/`` and deleted, and then two
tree readers judge the deletions, each by its own rule:

* the model contract capture, when a module of the package hands its ``tests/`` to ``package_contracts``:
  every model sampled before the deletions (the package's ``.dcfg`` fixtures, then the shared corpus's) is
  still sampled after them. A model whose last sample was deleted would fail its contract, so the run is
  refused naming the model and the fixture its sample came from; its value belongs in a corpus config;
* the semantic baseline, when the package holds a manifest (``tests/fixtures/semantic_baseline/manifest.json``):
  the manifest built after the deletions differs from the committed one only by the deleted files' keys
  leaving and the shared corpus entries' keys arriving (``semantic_baseline.baseline_drift``). Any other
  change refuses the run, naming each key.

A refused run writes every deleted file back byte for byte (never a git command) and leaves the manifest as
it was. A run the readers accept writes the regenerated manifest, removes the directories the deletions left
empty and, deleting or not, runs ``fixture-budget-gate.ps1 -UpdateBaseline`` to bank the package's fall.
"""

from __future__ import annotations

import io
import logging
from collections.abc import Callable, Sequence
from contextlib import redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from datrix_testing.model_contracts.capture import CaptureError, collect_samples
from datrix_testing.model_contracts.discovery import ModelDiscoveryError, ModelSet, model_set, qualified_name
from datrix_testing.semantic_baseline import (
    SemanticBaselineCorpus,
    baseline_drift,
    build_semantic_baseline,
    enumerate_shared_corpus,
    fixture_key,
    load_semantic_baseline,
    write_semantic_baseline,
)
from pydantic import BaseModel

from datrix_scripts.dev.fixture_author.drafting import QUEUE_DIR
from datrix_scripts.dev.fixture_author.needs import NeedsScanError
from datrix_scripts.dev.fixture_author.needs_command import EXIT_INCOMPLETE
from datrix_scripts.dev.fixture_author.prune_reads import KeepReason, KeptFiles, kept_fixture_files
from datrix_scripts.dev.fixture_author.repoint import package_dir_named
from datrix_scripts.dev.fixture_author.repoint_jobs import UNDO_DIR, UndoStore, package_queue_files
from datrix_scripts.framework_repos import PackageMarker
from datrix_scripts.gate_harness import EXIT_PASS, UsageError
from datrix_scripts.gates.ratchet.fixture_budget_gate import (
    CORPUS_RELATIVE,
    SHARED_PACKAGE,
    FixtureScanError,
    run_budget,
)
from datrix_scripts.gates.ratchet.fixture_budget_gate import WRAPPER as BUDGET_WRAPPER
from datrix_scripts.paths import WORKSPACE_DIR

logger = logging.getLogger(__name__)

#: The name an undo record of a prune is saved under, before the package's name.
RECORD_PREFIX: Final = "prune "

#: The models of the package at a directory: the set its model contract capture samples.
ModelSource = Callable[[Path], ModelSet]


class PruneRefused(Exception):
    """The prune may not delete: the queue holds a module, or a tree reader refuses the deletions."""


@dataclass(frozen=True)
class Pruner:
    """What pruning one package reads: the package, the workspace whose corpus and budget it reads, where it
    saves and reads the queue, and the models the package's contract capture samples."""

    package_dir: Path
    workspace: Path = WORKSPACE_DIR
    undo: UndoStore = UndoStore(UNDO_DIR)
    queue_dir: Path = QUEUE_DIR
    models: ModelSource = model_set

    @property
    def tests_dir(self) -> Path:
        return (self.package_dir / PackageMarker.TESTS.value).resolve()

    @property
    def shared_corpus(self) -> Path:
        """The workspace's shared fixture corpus: the one the budget gate counts and the tree readers load."""
        return self.workspace / SHARED_PACKAGE / CORPUS_RELATIVE


@dataclass(frozen=True)
class PruneOutcome:
    """What one prune found, deleted and wrote back first, and the semantic manifest it regenerated."""

    kept: KeptFiles
    deleted: tuple[Path, ...]
    recovered: str | None
    manifest: Path | None


@dataclass(frozen=True)
class _Readers:
    """The tree readers judging the deletions, read before any file is deleted: the models the contract capture
    samples with the source of each sample, and the semantic baseline with its committed manifest."""

    models: ModelSet | None
    sampled: dict[type[BaseModel], str]
    baseline: SemanticBaselineCorpus | None
    old_manifest: dict[str, str]


def _label(path: Path, workspace: Path) -> str:
    return path.relative_to(workspace).as_posix() if path.is_relative_to(workspace) else str(path)


def _refuse_queued(pruner: Pruner) -> None:
    queued = package_queue_files(pruner.queue_dir, pruner.package_dir.name)
    if queued:
        raise PruneRefused(
            f"{len(queued)} module(s) of {pruner.package_dir.name} are still queued, and a queued module still "
            f"reads the files it was not repointed off: {[path.name for path in queued]}. Fix: finish each queue "
            "file by hand (test.ps1 -Specific passes, the assertion count holds), delete it, then prune again."
        )


def _sampled(pruner: Pruner, models: ModelSet) -> dict[type[BaseModel], str]:
    """Every model the package's contract capture samples now, with the source of its sample."""
    capture = collect_samples(pruner.tests_dir, models, pruner.shared_corpus)
    return {model: sample.first.source for model, sample in capture.samples.items()}


def _readers(pruner: Pruner, kept: KeptFiles) -> _Readers:
    models = pruner.models(pruner.package_dir) if kept.contract_readers else None
    sampled = _sampled(pruner, models) if models is not None else {}
    corpus = SemanticBaselineCorpus(pruner.package_dir, pruner.shared_corpus)
    if not corpus.manifest_path.is_file():
        return _Readers(models, sampled, None, {})
    return _Readers(models, sampled, corpus, load_semantic_baseline(corpus))


def _lost_samples(pruner: Pruner, readers: _Readers) -> list[str]:
    """sampled before − sampled after: one line per model whose last sample the deletions took."""
    if readers.models is None:
        return []
    after = _sampled(pruner, readers.models)
    return [
        f"model {qualified_name(model)} loses its last sample ({source}): a model no fixture samples fails its "
        "contract. Fix: add the value to a corpus config (datrix-testing fixtures_data/corpus/config/), then "
        "prune again."
        for model, source in sorted(readers.sampled.items(), key=lambda item: qualified_name(item[0]))
        if model not in after
    ]


def _new_manifest(pruner: Pruner, readers: _Readers, deleted: Sequence[Path]) -> tuple[dict[str, str], list[str]]:
    """The manifest built after the deletions, and one line per change ``baseline_drift`` names illegal."""
    corpus = readers.baseline
    if corpus is None:
        return {}, []
    new = build_semantic_baseline(corpus)
    deleted_keys = {fixture_key(path, corpus) for path in deleted}
    corpus_keys = {fixture_key(entry, corpus) for entry in enumerate_shared_corpus(corpus)}
    drift = baseline_drift(readers.old_manifest, new, deleted_keys, corpus_keys)
    return new, [f"semantic baseline of {pruner.package_dir.name}: {line}" for line in drift]


def _delete_and_judge(pruner: Pruner, readers: _Readers, doomed: Sequence[Path]) -> dict[str, str]:
    """Delete *doomed* and have the tree readers judge it; the regenerated manifest. A refusal or an error
    writes every deleted file back first.

    Raises:
        PruneRefused: a tree reader refuses the deletions.
    """
    saved = [*doomed, *([readers.baseline.manifest_path] if readers.baseline is not None else [])]
    pruner.undo.save(f"{RECORD_PREFIX}{pruner.package_dir.name}", saved)
    try:
        for path in doomed:
            path.unlink()
        problems = _lost_samples(pruner, readers)
        manifest, drift = _new_manifest(pruner, readers, doomed) if not problems else ({}, [])
    except BaseException:
        pruner.undo.restore()
        raise
    problems.extend(drift)
    if problems:
        pruner.undo.restore()
        raise PruneRefused(f"{len(doomed)} file(s) written back, nothing deleted:\n  " + "\n  ".join(problems))
    return manifest


def _remove_emptied(deleted: Sequence[Path], tests_dir: Path) -> None:
    """Remove each directory under *tests_dir* the deletions left empty, innermost first."""
    for path in deleted:
        parent = path.parent
        while parent != tests_dir and parent.is_relative_to(tests_dir) and parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent


def prune_package(pruner: Pruner) -> PruneOutcome:
    """Delete the fixture files of the package nothing reads, as its tree readers allow (module docstring).

    Raises:
        PruneRefused: the queue holds a module of the package, its tree readers cannot be read, or one of them
            refuses the deletions.
        NeedsScanError: the shared fixture directory is missing or an input cannot be read.
        FixtureScanError: a module under ``tests/`` cannot be parsed.
    """
    recovered = pruner.undo.restore()
    _refuse_queued(pruner)
    kept = kept_fixture_files(pruner.package_dir, pruner.workspace)
    doomed = kept.unread()
    if not doomed:
        return PruneOutcome(kept, (), recovered, None)
    try:
        readers = _readers(pruner, kept)
    except (ModelDiscoveryError, CaptureError, ValueError, FileNotFoundError) as error:
        raise PruneRefused(f"the tree readers of {pruner.package_dir.name} cannot be read, so no deletion can be "
                           f"judged; nothing deleted: {type(error).__name__}: {error}") from error
    manifest = _delete_and_judge(pruner, readers, doomed)
    if readers.baseline is not None:
        write_semantic_baseline(readers.baseline, manifest)
    pruner.undo.clear()
    _remove_emptied(doomed, pruner.tests_dir)
    logger.debug("prune package=%s deleted=%d", pruner.package_dir.name, len(doomed))
    return PruneOutcome(kept, doomed, recovered,
                        readers.baseline.manifest_path if readers.baseline is not None else None)


def print_prune_outcome(outcome: PruneOutcome, workspace: Path) -> None:
    """One line per file deleted, the files kept by reason, and the manifest regenerated."""
    if outcome.recovered is not None:
        print(f"[UNDO] {outcome.recovered}: written back from the record an interrupted run left")
    for path in outcome.deleted:
        print(f"[DEL ] {_label(path, workspace)}")
    reasons = [f"{reason} {sum(1 for kept in outcome.kept.kept.values() if kept.reason is reason)}"
               for reason in KeepReason]
    print(f"files {len(outcome.kept.files)} - kept {len(outcome.kept.kept)} ({', '.join(reasons)}) "
          f"= {len(outcome.deleted)} deleted")
    if outcome.manifest is not None:
        print(f"[BASE] {_label(outcome.manifest, workspace)}: regenerated, its drift legal")


def run_prune(pruner: Pruner) -> int:
    """Prune the package, then bank the fixture budget; the exit code: 0 pruned and banked, 1 refused, a census
    error, or the budget baseline not tightened (the gate's report printed)."""
    try:
        outcome = prune_package(pruner)
    except PruneRefused as error:
        print(f"REFUSED: {error}")
        return EXIT_INCOMPLETE
    except (NeedsScanError, FixtureScanError) as error:
        print(f"ERROR: {error}")
        return EXIT_INCOMPLETE
    print_prune_outcome(outcome, pruner.workspace)
    report = io.StringIO()
    with redirect_stdout(report):
        code = run_budget(pruner.workspace, update_baseline=True, show_files=False)
    print(report.getvalue().rstrip())
    if code != EXIT_PASS:
        print(f"ERROR: {BUDGET_WRAPPER}.ps1 -UpdateBaseline exited {code}: the baseline is not tightened (its report "
              "above). The deletions stand; prune again once the gate's failure is fixed.")
        return EXIT_INCOMPLETE
    return EXIT_PASS


def run_prune_command(package: str) -> int:
    """``fixture-author.ps1 repoint -Package <package> -Prune``: delete the package's unread fixture files.

    Raises:
        UsageError: *package* is empty or no workspace package holding tests.
    """
    if not package:
        raise UsageError("-Package is required: the package whose unread fixture files are deleted.")
    return run_prune(Pruner(package_dir_named(package, WORKSPACE_DIR)))


__all__ = [
    "RECORD_PREFIX",
    "ModelSource",
    "PruneOutcome",
    "PruneRefused",
    "Pruner",
    "print_prune_outcome",
    "prune_package",
    "run_prune",
    "run_prune_command",
]
