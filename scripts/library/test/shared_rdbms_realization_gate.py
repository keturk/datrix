"""Shared-RDBMS realization gate.

A service that ``uses`` a shared container's RDBMS block realizes that block next to its own
(``datrix_common.datrix_model.shared_rdbms_scope.realized_rdbms_blocks``). Every registered
``datrix.languages`` target must emit, for each consumer, the entity modules of the consumed block,
carry the one canonical migration chain the owner renders byte for byte, and emit the block's seed
only in a consumer that holds write access.

THE GATE GENERATES. For each registered language it generates the shared-rdbms fixture -- a shared
container's block, a ``readwrite`` consumer that holds a seed, and a ``readonly`` consumer -- and applies
the same language-neutral file-set assertions to the emitted tree:

* every consumer emits an entity module for the consumed block (a file whose path names the block and
  whose content names the entity);
* every file of the owner's canonical chain appears, byte for byte, in every consumer;
* the block's seed is emitted in the writer and in no reader.

The per-language behavioural assertions (typed access, read-only repositories, the lock key) live in
each package's own tests; this gate pins that no registered language silently lacks the realization.

The language set is enumerated from the installed ``datrix.languages`` entry points at run time -- never
a hardcoded list -- and the gate refuses to pass (exit 2) with fewer than two registered languages.

A non-vacuity self-test runs first on every invocation: a planted language whose consumer emits no entity
module must be reported, a planted language whose carried chain differs from the canonical one must be
reported, a planted language that seeds a reader must be reported, a faithful planted language must
report nothing, and a single-language run must be refused as vacuous.
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

_LIBRARY_DIR = Path(__file__).resolve().parent.parent
if _LIBRARY_DIR.exists() and str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from shared.registered_targets import registered_language_names  # noqa: E402

logger = logging.getLogger(__name__)

#: A comparison over 0 or 1 language cannot tell "realized" from "the only language there is".
_MIN_LANGUAGES: Final[int] = 2

EXIT_OK: Final[int] = 0
EXIT_FAIL: Final[int] = 1
EXIT_VACUOUS: Final[int] = 2

#: The fixture's facts. The gate reads the fixture's own services, so these name its vocabulary only.
_SHARED_NAME: Final[str] = "CatalogData"
_BLOCK_NAME: Final[str] = "catalog_db"
_ENTITY_NAME: Final[str] = "Product"
_WRITER_NAME: Final[str] = "shop.WriterService"
_READER_NAME: Final[str] = "shop.ReaderService"

#: Path vocabulary a language may spell a seed with.
_SEED_TOKEN: Final[str] = "seed"

#: Where every target's manifest records the files it emitted, and the key listing the revision
#: files (retention ``append_only``): the language-neutral definition of "a migration revision".
_MANIFEST_DIR: Final[str] = ".datrix/manifests"
_APPEND_ONLY_KEY: Final[str] = "append_only_files"


@dataclass(frozen=True)
class ConsumerTree:
    """One consumer's emitted files, keyed by path relative to the consumer's own directory."""

    name: str
    writes: bool
    files: Mapping[str, str]


@dataclass(frozen=True)
class GeneratedTree:
    """What one language emitted: the owner's canonical revision files and every consumer's files."""

    owner_chain: Mapping[str, str]
    consumers: tuple[ConsumerTree, ...]


def _names_block(path: str, block_markers: frozenset[str]) -> bool:
    lowered = path.lower()
    return any(marker in lowered for marker in block_markers)


def violations_in(
    tree: GeneratedTree,
    *,
    block_markers: frozenset[str],
    entity_name: str,
) -> list[str]:
    """Every way *tree* fails the realization assertions (empty = realized)."""
    found: list[str] = []
    chain = tree.owner_chain
    if not chain:
        found.append("the owner rendered no revision file for the shared block")
    for consumer in tree.consumers:
        has_entity = any(
            _names_block(path, block_markers) and entity_name in content
            for path, content in consumer.files.items()
        )
        if not has_entity:
            found.append(f"{consumer.name}: no entity module for '{entity_name}' of the consumed block")
        emitted = set(consumer.files.values())
        missing = sorted(path for path, content in chain.items() if content not in emitted)
        for path in missing:
            found.append(f"{consumer.name}: the canonical chain file '{path}' is not carried byte for byte")
        seeds = [
            path
            for path in consumer.files
            if _SEED_TOKEN in path.lower() and _names_block(path, block_markers)
        ]
        if seeds and not consumer.writes:
            found.append(f"{consumer.name}: a read-only consumer emits the shared seed {sorted(seeds)}")
        if not seeds and consumer.writes:
            found.append(f"{consumer.name}: the writing consumer emits no seed for the shared block")
    return found


# ---------------------------------------------------------------------------
# Generation of the shared fixture per language
# ---------------------------------------------------------------------------


#: The profile the fixture's ConfigDSL resolves.
_PROFILE: Final[str] = "test"


def _read_tree(root: Path) -> dict[str, str]:
    """Every file under *root* as ``posix path relative to root -> text``."""
    return {
        path.relative_to(root).as_posix(): path.read_text(encoding="utf-8", errors="replace")
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _append_only_paths(root: Path) -> frozenset[str]:
    """Every revision file any target's manifest under *root* records (retention append-only)."""
    paths: set[str] = set()
    manifest_dir = root / _MANIFEST_DIR
    for manifest in sorted(manifest_dir.glob("*.json")) if manifest_dir.is_dir() else ():
        recorded = json.loads(manifest.read_text(encoding="utf-8")).get(_APPEND_ONLY_KEY, [])
        paths.update(str(path).replace("\\", "/") for path in recorded)
    return frozenset(paths)


def generate_language_tree(language: str, out_dir: Path) -> GeneratedTree:
    """Generate the fixture for *language* through the real pipeline and split the output.

    The fixture project (a shared container's block, the writer and reader services and a
    ``seed/`` directory seeding the shared block) is copied to a scratch directory and run through
    the same ``GenerationPipeline`` ``datrix generate`` uses.
    """
    from datrix_cli.generation.validation_level import ValidationLevel
    from datrix_cli.pipeline.contract import PipelineConfig
    from datrix_cli.pipeline.generation import GenerationPipeline
    from datrix_common.paths import ServicePaths, SharedPaths
    from datrix_common.plugin.identity import LanguageId
    from datrix_language.registration import register_all
    from datrix_testing.shared_fixtures import shared_rdbms_consumption_path

    register_all()

    fixture = shared_rdbms_consumption_path()
    project = out_dir / "project"
    output = out_dir / "output"
    shutil.copytree(fixture.parent, project)
    output.mkdir()
    # ValidationLevel.FAST skips the toolchain build: what is under test is which files each
    # language emits, not whether its toolchain accepts them.
    result = GenerationPipeline().run(
        project / fixture.name,
        output,
        PipelineConfig(
            target_language=LanguageId(language),
            profile=_PROFILE,
            validation_level=ValidationLevel.FAST,
        ),
    )
    if not result.success:
        raise RuntimeError(
            f"pipeline reported failure for language {language!r}: "
            f"{'; '.join(result.errors) or 'success=False, no error text'}"
        )
    files = _read_tree(output)

    def under(directories: tuple[str, ...]) -> dict[str, str]:
        """Files below any of *directories* (a directory segment anywhere in the path)."""
        found: dict[str, str] = {}
        for path, content in files.items():
            segments = path.split("/")
            for directory in directories:
                if directory in segments[:-1]:
                    found["/".join(segments[segments.index(directory) + 1 :])] = content
                    break
        return found

    append_only = _append_only_paths(output)
    shared_dir = SharedPaths(_SHARED_NAME).shared_dir
    owner_chain = {
        path: content
        for path, content in files.items()
        if path in append_only and shared_dir in path.split("/")[:-1]
    }
    consumers: list[ConsumerTree] = []
    for name, writes in ((_WRITER_NAME, True), (_READER_NAME, False)):
        paths = ServicePaths(name)
        consumers.append(
            ConsumerTree(
                name=name,
                writes=writes,
                files=under((paths.service_dir, paths.compose_service)),
            )
        )
    return GeneratedTree(owner_chain=owner_chain, consumers=tuple(consumers))


_BLOCK_MARKERS: Final[frozenset[str]] = frozenset(
    {"catalog_db", "catalog-db", "catalogdb"}
)


def run_gate(
    *,
    languages: frozenset[str] | None = None,
    generate: Callable[[str, Path], GeneratedTree] = generate_language_tree,
) -> int:
    """Full gate run. Returns a process exit code (0/1/2).

    Args:
        languages: Override for the registered language set (the self-test passes a synthetic set to
            prove the vacuity guard through the same code path a live run takes).
        generate: ``(language, out_dir) -> GeneratedTree``.
    """
    names = languages if languages is not None else registered_language_names()
    if len(names) < _MIN_LANGUAGES:
        logger.error(
            "shared_rdbms_gate_vacuous language_count=%d minimum=%d", len(names), _MIN_LANGUAGES
        )
        return EXIT_VACUOUS

    failures: dict[str, list[str]] = {}
    for language in sorted(names):
        with tempfile.TemporaryDirectory(prefix=f"shared-rdbms-{language}-") as tmp:
            tree = generate(language, Path(tmp))
        found = violations_in(tree, block_markers=_BLOCK_MARKERS, entity_name=_ENTITY_NAME)
        logger.info(
            "shared_rdbms_realization language=%s status=%s violations=%d",
            language,
            "GAP" if found else "REALIZED",
            len(found),
        )
        if found:
            failures[language] = found

    if failures:
        for language, found in sorted(failures.items()):
            for line in found:
                logger.error("SHARED-RDBMS REALIZATION GAP (language=%s): %s", language, line)
        return EXIT_FAIL

    logger.info(
        "SHARED-RDBMS REALIZATION HOLDS: %d language(s) realize shared RDBMS consumption.", len(names)
    )
    return EXIT_OK


# ---------------------------------------------------------------------------
# Non-vacuity self-test
# ---------------------------------------------------------------------------

_CHAIN_FILE = "catalog-data/rdbms/migrations/catalog_db/001_initial.sql"
_CHAIN_BODY = "CREATE TABLE products (sku TEXT PRIMARY KEY);"


def _planted(
    *,
    reader_entity: bool = True,
    carried_chain: str = _CHAIN_BODY,
    reader_seeds: bool = False,
) -> GeneratedTree:
    """A synthetic language's output, faithful unless a flag plants a defect."""
    entity_file = "entities/catalog_db/product.src"
    entity_body = f"class {_ENTITY_NAME}: ..."
    seed_file = "seeds/catalog_db.src"

    def consumer(name: str, writes: bool) -> ConsumerTree:
        files: dict[str, str] = {"migrations/catalog_db/001_initial.sql": carried_chain}
        if name != _READER_NAME or reader_entity:
            files[entity_file] = entity_body
        if writes or reader_seeds:
            files[seed_file] = "seed rows"
        return ConsumerTree(name=name, writes=writes, files=files)

    return GeneratedTree(
        owner_chain={_CHAIN_FILE: _CHAIN_BODY},
        consumers=(consumer(_WRITER_NAME, True), consumer(_READER_NAME, False)),
    )


def run_self_test() -> None:
    """Non-vacuity self-test, step 1 of every invocation.

    Raises:
        AssertionError: A proof failed -- the gate aborts before trusting any real comparison.
    """

    def found(tree: GeneratedTree) -> list[str]:
        return violations_in(tree, block_markers=_BLOCK_MARKERS, entity_name=_ENTITY_NAME)

    assert not found(_planted()), f"self-test: a faithful language must report nothing: {found(_planted())}"
    print("[OK] a faithful planted language reports nothing")

    no_entity = found(_planted(reader_entity=False))
    assert any("no entity module" in line for line in no_entity), (
        f"self-test: a consumer that emits no entity module must be reported: {no_entity}"
    )
    print(f"[OK] a planted consumer with no entity module is reported ({len(no_entity)} violation(s))")

    drifted = found(_planted(carried_chain=_CHAIN_BODY + "-- drift"))
    assert any("byte for byte" in line for line in drifted), (
        f"self-test: a carried chain that differs from the canonical one must be reported: {drifted}"
    )
    print(f"[OK] a planted drifted chain is reported ({len(drifted)} violation(s))")

    seeded = found(_planted(reader_seeds=True))
    assert any("read-only consumer emits the shared seed" in line for line in seeded), (
        f"self-test: a reader that seeds the shared block must be reported: {seeded}"
    )
    print(f"[OK] a planted reader seed is reported ({len(seeded)} violation(s))")

    def generate(language: str, out_dir: Path) -> GeneratedTree:
        return _planted(reader_entity=(language != "planted_blind"))

    blind_exit = run_gate(languages=frozenset({"planted_faithful", "planted_blind"}), generate=generate)
    assert blind_exit == EXIT_FAIL, f"self-test: run_gate must fail a planted blind language, got {blind_exit}"
    print(f"[OK] run_gate fails a planted entity-blind language (exit={blind_exit})")

    vacuous_exit = run_gate(languages=frozenset({"planted_faithful"}), generate=generate)
    assert vacuous_exit == EXIT_VACUOUS, (
        f"self-test: run_gate must refuse a single-language run, got {vacuous_exit}"
    )
    print(f"[OK] run_gate refuses a single-language run as vacuous (exit={vacuous_exit})")


def main() -> int:
    """CLI entry point; returns 0 (holds / self-test passed), 1 (gap), 2 (vacuous or self-test failed)."""
    parser = argparse.ArgumentParser(
        description=(
            "Shared-RDBMS realization gate: every registered language emits the entity modules, the "
            "carried migration chain and the writer-only seed of a consumed shared RDBMS block "
            "(generates the shared fixture per language)."
        ),
    )
    parser.add_argument("--debug", action="store_true", help="Enable DEBUG logging")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run only the non-vacuity self-test and skip the real check",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    try:
        run_self_test()
    except AssertionError as exc:
        logger.error("NON-VACUITY SELF-TEST FAILED: %s", exc)
        return EXIT_VACUOUS
    logger.info("non-vacuity self-test: PASS")

    if args.self_test:
        return EXIT_OK
    return run_gate()


if __name__ == "__main__":
    sys.exit(main())
