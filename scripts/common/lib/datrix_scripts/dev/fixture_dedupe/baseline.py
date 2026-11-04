"""The semantic baselines across a dedupe write.

Each package holding a committed semantic-baseline manifest protects the semantic output of its fixtures
(``datrix_testing.semantic_baseline``). Moving copies to the shared corpus changes that output in three
ways only, and the write is proven against them:

* before writing, every entry is analyzed once and hashed twice: as it is, and with the path of every copy
  that leaves its tree dumped as the path of the copy replacing it (``moved``) and every reference the
  write rewrites dumped as its new text (``rewritten``: an include's path, a header's config path, held by
  a node located in the rewritten file). An entry whose two hashes differ reaches a leaving copy or a
  rewritten reference: it is *translated*;
* after writing, every entry is analyzed again. A translated entry that stays must hash as its translated
  dump, and the drift from the hashes before to the hashes after must be legal (``baseline_drift``): a
  deleted copy's key leaves, a shared corpus file's key arrives, a translated key's hash changes, and
  nothing else.

The manifest written is the committed one with those changes only: the deleted keys gone, each translated
key and each arriving shared key at its new hash. A key the committed manifest holds at another hash than
the tree gives keeps its committed hash: drift the move did not cause is not banked by it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from datrix_testing.parsing import register_installed_parsers
from datrix_testing.semantic_baseline import (
    SemanticBaselineCorpus,
    analysis_payload,
    analyze_fixture,
    baseline_drift,
    enumerate_fixture_corpus,
    fixture_key,
    semantic_baseline_from_payloads,
)

from datrix_scripts.dev.fixture_dedupe.layout import corpus_root
from datrix_scripts.framework_repos import PackageMarker


class BaselineError(Exception):
    """A semantic-baseline entry cannot be analyzed, so the write cannot be proven to keep its output."""


@dataclass(frozen=True)
class BaselineBefore:
    """One package's semantic baseline before a write.

    Attributes:
        corpus: The package's baseline corpus.
        plain: Each entry's hash as the tree is.
        moved: Each entry's hash with every leaving copy dumped as the copy replacing it.
        deleted: The keys of the copies the write takes out of the package.
    """

    corpus: SemanticBaselineCorpus
    plain: Mapping[str, str]
    moved: Mapping[str, str]
    deleted: frozenset[str]

    @property
    def translated(self) -> frozenset[str]:
        """The keys whose output reaches a leaving copy: their hash changes with the move, and only so."""
        return frozenset(key for key, value in self.plain.items() if self.moved[key] != value)


@dataclass(frozen=True)
class BaselineAfter:
    """One package's semantic baseline once a write is written.

    Attributes:
        hashes: Each entry's hash.
        corpus_keys: The keys of the entries in the shared corpus.
    """

    hashes: Mapping[str, str]
    corpus_keys: frozenset[str]


def baseline_corpora(base_dir: Path, packages: Sequence[Path]) -> list[SemanticBaselineCorpus]:
    """The baseline corpus of each of *packages* holding a committed semantic-baseline manifest, each
    reading the corpus of the workspace at *base_dir*."""
    found: list[SemanticBaselineCorpus] = []
    for package in packages:
        if not (package / PackageMarker.PYPROJECT.value).is_file():
            continue
        corpus = SemanticBaselineCorpus(package_root=package, shared_corpus=corpus_root(base_dir))
        if corpus.manifest_path.is_file():
            found.append(corpus)
    return found


@dataclass(frozen=True)
class Translation:
    """How a dump read before a write records what the write changes.

    Attributes:
        moved: Each leaving copy's resolved old path mapped to the resolved path of the copy replacing it.
        rewritten: Each fixture whose references the write rewrites, by its resolved old path, mapped from
            each reference as written to the text replacing it.
    """

    moved: Mapping[Path, Path]
    rewritten: Mapping[Path, Mapping[str, str]]


#: A dump of the tree as it is.
AS_IS: Translation = Translation(moved={}, rewritten={})


def entry_hashes(path: Path, corpus: SemanticBaselineCorpus, translations: Sequence[Translation]) -> list[str]:
    """The hash of the semantic output of *corpus*'s entry *path*, dumped once per translation of
    *translations*, the entry analyzed once.

    Raises:
        BaselineError: The analysis or its dump raises.
    """
    key = fixture_key(path, corpus)
    try:
        result = analyze_fixture(path, corpus)
        payloads = [analysis_payload(result, corpus, one.moved, one.rewritten) for one in translations]
    except Exception as exc:
        raise BaselineError(
            f"{corpus.package_root.name}: semantic-baseline entry {key} cannot be analyzed and dumped "
            f"({type(exc).__name__}: {exc}), so the write cannot be proven to keep its output. Fix: make the "
            "entry analyze (the package's semantic-baseline test fails on it too), then rerun."
        ) from exc
    hashes = semantic_baseline_from_payloads({str(index): payload for index, payload in enumerate(payloads)})
    return [hashes[str(index)] for index in range(len(payloads))]


def hash_before(
    corpus: SemanticBaselineCorpus, moves: Mapping[Path, Path], rewritten: Mapping[Path, Mapping[str, str]]
) -> BaselineBefore:
    """*corpus*'s baseline before *moves* (each copy leaving a package tree, mapped to the copy replacing
    it) and the reference rewrites *rewritten* (``follow.reference_rewrites``) are written.

    Raises:
        BaselineError: An entry cannot be analyzed.
    """
    register_installed_parsers()
    translation = Translation(
        moved={old.resolve(): new.resolve() for old, new in moves.items()},
        rewritten={source.resolve(): texts for source, texts in rewritten.items()},
    )
    plain: dict[str, str] = {}
    translated: dict[str, str] = {}
    for path in enumerate_fixture_corpus(corpus):
        key = fixture_key(path, corpus)
        plain[key], translated[key] = entry_hashes(path, corpus, (AS_IS, translation))
    package = corpus.package_root.resolve()
    deleted = frozenset(fixture_key(old, corpus) for old in moves if old.resolve().is_relative_to(package))
    return BaselineBefore(corpus, plain, translated, deleted)


def hash_after(corpus: SemanticBaselineCorpus) -> BaselineAfter:
    """*corpus*'s baseline as the tree is now.

    Raises:
        BaselineError: An entry cannot be analyzed.
    """
    register_installed_parsers()
    shared = corpus.shared_corpus.resolve()
    hashes: dict[str, str] = {}
    corpus_keys: set[str] = set()
    for path in enumerate_fixture_corpus(corpus):
        key = fixture_key(path, corpus)
        (hashes[key],) = entry_hashes(path, corpus, (AS_IS,))
        if path.resolve().is_relative_to(shared):
            corpus_keys.add(key)
    return BaselineAfter(hashes, frozenset(corpus_keys))


def baseline_failures(before: BaselineBefore, after: BaselineAfter) -> list[str]:
    """Each change from *before* to *after* the move may not cause, one line naming its key: drift
    ``baseline_drift`` names, and a translated key that stays whose hash is not its translated dump's."""
    failures = list(baseline_drift(before.plain, after.hashes, before.deleted, after.corpus_keys, before.translated))
    for key in sorted(before.translated - before.deleted):
        if key in after.hashes and after.hashes[key] != before.moved[key]:
            failures.append(
                f"{key}: hashes {after.hashes[key][:12]}... once written, not {before.moved[key][:12]}..., its dump "
                "with the leaving copies' paths mapped to their shared copies"
            )
    return failures


def updated_manifest(committed: Mapping[str, str], before: BaselineBefore, after: BaselineAfter) -> dict[str, str]:
    """*committed* with the move's changes only: the deleted keys gone, each translated key it holds at the hash
    the tree gave before the write at its hash *after*, and each arriving shared corpus key at its hash *after*.

    A translated key *committed* holds at another hash than the tree gave before the write keeps its committed
    hash: its drift is not the move's, and taking its new hash would bank it unreviewed.
    """
    manifest = {key: value for key, value in committed.items() if key not in before.deleted}
    manifest.update(
        {
            key: after.hashes[key]
            for key in before.translated
            if key in manifest and key in after.hashes and manifest[key] == before.plain[key]
        }
    )
    manifest.update({key: after.hashes[key] for key in after.corpus_keys if key not in manifest})
    return manifest
