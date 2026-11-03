"""The ``fixture-author.ps1 needs`` command: one inventory of what the packages' tests read and need.

Discovery (``needs``) finds the test modules of the packages run and the inputs each reads; reading
(``needs_reading``) has the local model say what each test needs. This module turns the reading into
``needs.json`` and proves it whole before writing it:

- one row per module discovery found, ``kind: "module"``, with its inputs and, per test function, the
  declarations its assertions depend on; one row per tree reader of the packages run, ``kind: "tree"``.
  Rows are sorted by module path, keys sorted, and the file written as bytes, so a rerun on an unchanged
  tree (whose answers the reading cached) writes the same file;
- the module rows are read back from the bytes about to be written and compared with the modules
  discovery found: a module found and not inventoried (its answer refused) stops the command, naming it
  with why, and nothing is written. No local model stops it the same way.

The summary prints, per package, the modules, the inputs read, the declarations needed, the distinct
declaration paths and the local tests, then the union of declaration kinds per service-level block family.
A declaration belongs to the family of the nearest block declared in the same test whose path encloses its
own (itself, when it is a block); the family is the block class's name less ``Block``, lowercased
(``RdbmsBlock`` is ``rdbms``). A service also declares its identity and its REST, GraphQL and WebSocket
APIs, which are no ``Block`` subclasses: they open the families ``identity`` and ``api``.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final, cast

from datrix_common.datrix_model.api import GraphqlApi, RestApi, WebsocketApi
from datrix_common.datrix_model.base import Block, QualifiedBlock
from datrix_common.datrix_model.identity import IdentityBlock

from datrix_scripts.dev.fixture_author.needs import (
    TREE_READERS,
    ModuleInput,
    ModuleInputs,
    NeedsScanError,
    TreeReader,
    needs_packages,
    tree_reader_failures,
    workspace_inputs,
)
from datrix_scripts.dev.fixture_author.needs_reading import (
    Declaration,
    ModuleNeeds,
    NeedsReader,
    NeedsReading,
    TestNeeds,
    node_kinds,
    read_needs,
)
from datrix_scripts.gate_harness import UsageError
from datrix_scripts.gates.ratchet.fixture_budget_gate import FixtureScanError
from datrix_scripts.local_llm import LocalLlmPool, LocalLlmSettings, LocalLlmUnavailable
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.skill.common import EXIT_NO_MODEL, AssistError, ContentFilter

logger = logging.getLogger(__name__)

#: The inventory the command writes: a working file, never committed.
NEEDS_FILE: Final[Path] = WORKSPACE_DIR / ".tmp" / "fixture-author" / "needs.json"
#: The ``kind`` of a row: a test module, or a reader of a whole tree.
MODULE_ROW: Final = "module"
TREE_ROW: Final = "tree"
#: The exit codes beside 0 and ``EXIT_NO_MODEL``: the inventory is not whole (or a tree reader moved, or a
#: test module cannot be parsed), and a tree or file the inventory must read is missing.
EXIT_INCOMPLETE: Final = 1
EXIT_SCAN: Final = 2

_ROWS: Final = "rows"
_KIND: Final = "kind"
_MODULE: Final = "module"
_PATH_SEPARATOR: Final = "."
_BLOCK_BASES: Final[tuple[type[object], ...]] = (Block, QualifiedBlock)
#: The service-level declarations that are no ``Block`` subclass, with the family each opens.
_UNBLOCKED_FAMILIES: Final[Mapping[type[object], str]] = {
    IdentityBlock: "identity",
    RestApi: "api",
    GraphqlApi: "api",
    WebsocketApi: "api",
}


@dataclass(frozen=True)
class PackageSummary:
    """One package's share of the inventory, as the summary prints it."""

    package: str
    modules: int
    inputs: int
    declarations: int
    paths: int
    local: int


def select_packages(workspace: Path, name: str) -> list[Path]:
    """The packages *name* selects: every workspace package holding ``tests/`` when empty, else that one.

    Raises:
        UsageError: *name* is no workspace package holding ``tests/``.
    """
    packages = needs_packages(workspace)
    if not name:
        return packages
    chosen = [package for package in packages if package.name == name]
    if not chosen:
        raise UsageError(
            f"-Package {name!r} is no workspace package holding tests/; the packages that do: "
            f"{[package.name for package in packages]}."
        )
    return chosen


def tree_readers_of(packages: Sequence[Path]) -> tuple[TreeReader, ...]:
    """The tree readers living in *packages*."""
    names = {package.name for package in packages}
    return tuple(reader for reader in TREE_READERS if PurePosixPath(reader.module).parts[0] in names)


def _label(path: Path, workspace: Path) -> str:
    return path.relative_to(workspace).as_posix()


def _input_row(each: ModuleInput, workspace: Path) -> dict[str, object]:
    return {
        "form": each.form.value,
        "name": each.name,
        "lines": list(each.lines),
        "path": None if each.path is None else _label(each.path, workspace),
        "unresolved": None if each.unresolved is None else each.unresolved.value,
    }


def _declaration_row(declaration: Declaration) -> dict[str, object]:
    return {"kind": declaration.kind, "path": declaration.path, "facts": list(declaration.facts)}


def _test_row(test: TestNeeds) -> dict[str, object]:
    return {
        "name": test.name,
        "declarations": [_declaration_row(each) for each in test.declarations],
        "local": test.local,
    }


def _module_row(needs: ModuleNeeds, workspace: Path) -> dict[str, object]:
    return {
        _KIND: MODULE_ROW,
        _MODULE: _label(needs.found.module, workspace),
        "package": needs.found.package,
        "inputs": [_input_row(each, workspace) for each in needs.found.inputs],
        "tests": [_test_row(test) for test in needs.tests],
    }


def _tree_row(reader: TreeReader) -> dict[str, object]:
    return {
        _KIND: TREE_ROW,
        _MODULE: reader.module,
        "package": PurePosixPath(reader.module).parts[0],
        "symbol": reader.symbol,
        "reads": reader.reads,
    }


def needs_document(reading: NeedsReading, readers: Sequence[TreeReader], workspace: Path) -> dict[str, object]:
    """The inventory: a module row per module read, a tree row per reader, sorted by module path then kind."""
    rows = [*(_module_row(each, workspace) for each in reading.needs), *(_tree_row(reader) for reader in readers)]
    return {_ROWS: sorted(rows, key=lambda row: (str(row[_MODULE]), str(row[_KIND])))}


def render(document: Mapping[str, object]) -> bytes:
    """The bytes of *document*: keys sorted, fixed separators and newlines, UTF-8, so equal documents are equal bytes."""
    return (json.dumps(document, sort_keys=True, indent=1, ensure_ascii=False) + "\n").encode("utf-8")


def uninventoried(found: Sequence[ModuleInputs], rendered: bytes, workspace: Path) -> list[str]:
    """The modules discovery *found* that the module rows of *rendered* do not hold, by path: found − inventoried."""
    document = cast("dict[str, list[dict[str, object]]]", json.loads(rendered.decode("utf-8")))
    inventoried = {row[_MODULE] for row in document[_ROWS] if row[_KIND] == MODULE_ROW}
    return sorted({_label(each.module, workspace) for each in found} - inventoried)


def block_families(kinds: Mapping[str, type[object]]) -> dict[str, str]:
    """Each block kind of *kinds* with its family: the class name less ``Block``, lowercased; and the identity
    and API kinds of a service, which are no blocks, with the family they open."""
    suffix = Block.__name__
    families = {
        name: name.removesuffix(suffix).lower()
        for name, node in kinds.items()
        if issubclass(node, _BLOCK_BASES) and node not in _BLOCK_BASES
    }
    families.update({node.__name__: family for node, family in _UNBLOCKED_FAMILIES.items()})
    return families


def declaration_parts(path: str) -> tuple[str, ...]:
    """The segments of a declaration's qualified *path*."""
    return tuple(path.split(_PATH_SEPARATOR))


def declared_blocks(
    declarations: Sequence[Declaration], families: Mapping[str, str]
) -> list[tuple[tuple[str, ...], str]]:
    """The blocks one test declares, each as its path segments with its family."""
    return [(declaration_parts(each.path), families[each.kind]) for each in declarations if each.kind in families]


def enclosing_family(declaration: Declaration, blocks: Sequence[tuple[tuple[str, ...], str]]) -> str | None:
    """The family of the nearest block of *blocks* whose path encloses *declaration*'s, if any."""
    parts = declaration_parts(declaration.path)
    enclosing = [(len(prefix), family) for prefix, family in blocks if parts[: len(prefix)] == prefix]
    return max(enclosing)[1] if enclosing else None


def family_kinds(reading: NeedsReading, families: Mapping[str, str]) -> dict[str, tuple[str, ...]]:
    """The declaration kinds needed under each block family, both sorted."""
    union: dict[str, set[str]] = defaultdict(set)
    for module in reading.needs:
        for test in module.tests:
            blocks = declared_blocks(test.declarations, families)
            for declaration in test.declarations:
                family = enclosing_family(declaration, blocks)
                if family is not None:
                    union[family].add(declaration.kind)
    return {family: tuple(sorted(kinds)) for family, kinds in sorted(union.items())}


def package_summaries(reading: NeedsReading) -> list[PackageSummary]:
    """Each package's modules, inputs read, declarations needed, distinct declaration paths and local tests, by name."""
    by_package: dict[str, list[ModuleNeeds]] = defaultdict(list)
    for module in reading.needs:
        by_package[module.found.package].append(module)
    summaries: list[PackageSummary] = []
    for package, modules in sorted(by_package.items()):
        tests = [test for module in modules for test in module.tests]
        declarations = [declaration for test in tests for declaration in test.declarations]
        summaries.append(PackageSummary(
            package=package,
            modules=len(modules),
            inputs=sum(len(module.found.inputs) for module in modules),
            declarations=len(declarations),
            paths=len({declaration.path for declaration in declarations}),
            local=sum(test.local is not None for test in tests),
        ))
    return summaries


def print_summary(reading: NeedsReading, families: Mapping[str, str]) -> None:
    """Print each package's summary line, then each block family with the kinds needed under it."""
    for each in package_summaries(reading):
        print(
            f"{each.package}: {each.modules} module(s), {each.inputs} input(s) read, {each.declarations} "
            f"declaration(s) needed, {each.paths} distinct path(s), {each.local} local test(s)"
        )
    for family, kinds in family_kinds(reading, families).items():
        print(f"family {family}: {', '.join(kinds)}")


def _print_uninventoried(missing: Sequence[str], reading: NeedsReading, workspace: Path, output: Path) -> None:
    problems = {_label(each.module, workspace): each.problems for each in reading.refused}
    print(f"ERROR: {len(missing)} module(s) found and not inventoried; {output} is not written:")
    for label in missing:
        print(f"  {label}: {'; '.join(problems.get(label, ('no row was built for it',)))}")


@dataclass(frozen=True)
class Inventory:
    """One inventory as it is about to be written: what discovery found, what reading said, the bytes, and
    the modules found and not inventoried (*missing*, empty when the bytes are whole)."""

    found: tuple[ModuleInputs, ...]
    reading: NeedsReading
    readers: tuple[TreeReader, ...]
    rendered: bytes
    missing: tuple[str, ...]


def build_inventory(reader: NeedsReader, packages: Sequence[Path]) -> Inventory:
    """Discover *packages*' inputs, read their needs, render the inventory and compare it with what was found.

    Raises:
        LocalLlmUnavailable: no local model can read.
        NeedsScanError: a tree or file the inventory must read is missing.
        FixtureScanError: a test module cannot be parsed.
    """
    readers = tree_readers_of(packages)
    found = tuple(workspace_inputs(reader.workspace, packages))
    reading = read_needs(reader, found)
    rendered = render(needs_document(reading, readers, reader.workspace))
    missing = tuple(uninventoried(found, rendered, reader.workspace))
    return Inventory(found, reading, readers, rendered, missing)


def run_needs(reader: NeedsReader, packages: Sequence[Path], output: Path) -> int:
    """Inventory *packages*: discover, read, prove found − inventoried = ∅, write *output*, print the summary.

    The exit code: 0 written; ``EXIT_INCOMPLETE`` a module found is not inventoried, a tree reader moved
    or a test module cannot be parsed; ``EXIT_SCAN`` a tree or file the inventory must read is missing;
    ``EXIT_NO_MODEL`` no local model can read. Only 0 writes *output*.
    """
    failures = tree_reader_failures(reader.workspace, tree_readers_of(packages))
    if failures:
        print("\n".join(f"ERROR: {failure}" for failure in failures))
        return EXIT_INCOMPLETE
    try:
        inventory = build_inventory(reader, packages)
    except FixtureScanError as error:
        print(f"ERROR: {error}")
        return EXIT_INCOMPLETE
    except NeedsScanError as error:
        print(f"ERROR: {error}")
        return EXIT_SCAN
    except LocalLlmUnavailable as error:
        print(f"ERROR: no local model can read the tests; {output} is not written: {error}")
        return EXIT_NO_MODEL
    if inventory.missing:
        _print_uninventoried(inventory.missing, inventory.reading, reader.workspace, output)
        return EXIT_INCOMPLETE
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(inventory.rendered)
    print_summary(inventory.reading, block_families(node_kinds()))
    modules, trees = len(inventory.reading.needs), len(inventory.readers)
    print(f"{output}: {modules} module row(s), {trees} tree row(s)")
    logger.info("needs written path=%s modules=%d trees=%d", output, modules, trees)
    return 0


def run_needs_command(package: str, settings: LocalLlmSettings, output: Path = NEEDS_FILE) -> int:
    """``fixture-author.ps1 needs [-Package <p>]``: inventory every package holding ``tests/``, or *package*.

    Raises:
        UsageError: *package* is no workspace package holding ``tests/``.
    """
    packages = select_packages(WORKSPACE_DIR, package)
    try:
        content = ContentFilter(WORKSPACE_DIR)
    except AssistError as error:
        print(f"ERROR: {error}")
        return EXIT_INCOMPLETE
    pool = LocalLlmPool(settings, report=lambda line: logger.info("%s", line))
    return run_needs(NeedsReader(WORKSPACE_DIR, pool, content), packages, output)


__all__ = [
    "EXIT_INCOMPLETE",
    "EXIT_SCAN",
    "MODULE_ROW",
    "NEEDS_FILE",
    "TREE_ROW",
    "Inventory",
    "PackageSummary",
    "block_families",
    "build_inventory",
    "declaration_parts",
    "declared_blocks",
    "enclosing_family",
    "family_kinds",
    "needs_document",
    "package_summaries",
    "print_summary",
    "render",
    "run_needs",
    "run_needs_command",
    "select_packages",
    "tree_readers_of",
    "uninventoried",
]
