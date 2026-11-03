"""What the shared fixture corpus must hold: the needs of ``needs.json``, placed by entry and by family.

The corpus library is drafted from this plan and checked against it by ``library_check``. Only a test
whose input can be shared is placed; a test with a ``local`` reason keeps its input in its package.

- **Entry.** A test goes to the entry ``library``, unless its package distributes ``datrix.platforms``
  entry points: then to the entry named by that package's sorted-first entry-point name, where its
  platform profiles live. The platforms are read from the installed entry points, never listed.
- **System choices.** An entry holds one ``system``, so a system-level declaration (``System``,
  ``Application``) is the entry's system whatever path the test spells for it. A fact of it is a choice
  when its key resolves on the analyzed system to scalar values only and its value is one their types can
  take (a text value is one word): a choice holds one value, a collection holds many, and prose is no
  value. Where the tests of one entry hold different values for one choice, the value
  most of them hold stays (ties to the smaller value) and every test holding another moves, with all its
  declarations, to the entry ``<entry>-<key>-<value>`` (``<key>-<value>`` off ``library``): one entry
  per combination of minority choices.
- **Family.** A declaration goes to the family of the nearest block of its test whose path encloses its
  own (``needs_command.enclosing_family``); one that no block encloses, to the sorted-first family of the
  blocks it encloses, else to its test's sorted-first family, else to ``core``: the services that hold
  no block. System-level declarations belong to the entry, in no family.
- **Union.** Per entry and family the declarations are unioned by kind and path, their facts unioned and
  sorted.

A fact is ``<key> <value>``: the first word names what is read, the rest the value it holds, with one
pair of surrounding quotes dropped. A fact with no value reads that the key is present.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from importlib.metadata import entry_points
from pathlib import Path
from typing import Final, cast

from datrix_common.datrix_model.containers import Application, System
from datrix_common.plugin.registry import PLATFORM_GROUP

from datrix_scripts.dev.fixture_author.needs_command import (
    MODULE_ROW,
    declaration_parts,
    declared_blocks,
    enclosing_family,
)
from datrix_scripts.dev.fixture_author.needs_reading import Declaration

#: The entry every test is placed in unless its package is a platform's or a system choice moves it.
LIBRARY_ENTRY: Final = "library"
#: The family of a declaration that no block of its test encloses or is enclosed by.
CORE_FAMILY: Final = "core"
#: The declaration kinds that are an entry's system rather than a service's.
SYSTEM_KINDS: Final[frozenset[str]] = frozenset({Application.__name__, System.__name__})

_FACT_SEPARATOR: Final = " "
_QUOTES: Final = ("'", '"')
_ENTRY_SEPARATOR: Final = "-"
_SLUG_BREAK: Final = re.compile(r"[^a-z0-9]+")
_DIST_BREAK: Final = re.compile(r"[-_.]+")
_DIGEST_CHARS: Final = 8

#: Whether a fact of a system-level declaration is a choice: ``(kind, key, value) -> bool``.
ChoiceKeys = Callable[[str, str, str], bool]


class LibraryPlanError(Exception):
    """``needs.json`` cannot be read as an inventory, or the plan's vocabulary cannot be built."""


@dataclass(frozen=True)
class NeededTest:
    """One test function whose input can be shared, with the declarations its assertions read."""

    package: str
    module: str
    name: str
    declarations: tuple[Declaration, ...]


@dataclass(frozen=True)
class NeedsInventory:
    """The tests of ``needs.json`` to place, and how many tests keep a local input."""

    tests: tuple[NeededTest, ...]
    local: int


@dataclass(frozen=True)
class EntryPlan:
    """One corpus entry: the tests that read it, its system's declarations and each family's."""

    entry: str
    tests: tuple[NeededTest, ...]
    system: tuple[Declaration, ...]
    families: Mapping[str, tuple[Declaration, ...]]

    def needs(self) -> tuple[Declaration, ...]:
        """Every declaration the entry must provide: its system's, then each family's in name order."""
        return (*self.system, *(need for family in sorted(self.families) for need in self.families[family]))


@dataclass(frozen=True)
class LibraryPlan:
    """Every entry the needs place, by name, and how many tests keep a local input."""

    entries: tuple[EntryPlan, ...]
    local: int

    def entry(self, name: str) -> EntryPlan:
        """The entry called *name*.

        Raises:
            KeyError: the plan places no test in *name*, naming the entries it holds.
        """
        for each in self.entries:
            if each.entry == name:
                return each
        raise KeyError(f"the plan holds no entry {name!r}; it holds {[each.entry for each in self.entries]}")


def fact_parts(fact: str) -> tuple[str, str]:
    """The key of *fact* and the value it holds, one pair of surrounding quotes dropped."""
    key, _, value = fact.strip().partition(_FACT_SEPARATOR)
    value = value.strip()
    if len(value) > 1 and value[0] == value[-1] and value[0] in _QUOTES:
        value = value[1:-1]
    return key, value


def _text(value: object, where: str) -> str:
    if not isinstance(value, str):
        raise LibraryPlanError(f"{where} is {value!r}, not text. Fix: rerun fixture-author.ps1 needs.")
    return value


def _field(row: Mapping[str, object], key: str, where: str) -> object:
    if key not in row:
        raise LibraryPlanError(f"{where} has no {key!r}. Fix: rerun fixture-author.ps1 needs.")
    return row[key]


def _objects(value: object, where: str) -> list[Mapping[str, object]]:
    if not isinstance(value, list) or not all(isinstance(each, dict) for each in value):
        raise LibraryPlanError(f"{where} is not a list of objects. Fix: rerun fixture-author.ps1 needs.")
    return cast("list[Mapping[str, object]]", value)


def _declaration(value: Mapping[str, object], where: str) -> Declaration:
    facts = _field(value, "facts", where)
    if not isinstance(facts, list):
        raise LibraryPlanError(f"{where} facts are not a list. Fix: rerun fixture-author.ps1 needs.")
    return Declaration(
        kind=_text(_field(value, "kind", where), f"{where} kind"),
        path=_text(_field(value, "path", where), f"{where} path"),
        facts=tuple(_text(fact, f"{where} fact") for fact in facts),
    )


@dataclass(frozen=True)
class InventoriedTest:
    """One test function of an inventoried module: the declarations it reads, and why its input stays in its
    package (``None`` when it can be shared)."""

    name: str
    declarations: tuple[Declaration, ...]
    local: str | None


@dataclass(frozen=True)
class InventoriedModule:
    """One module row of ``needs.json``: a test module reading at least one input, with its test functions."""

    package: str
    module: str
    tests: tuple[InventoriedTest, ...]


def _module_row(row: Mapping[str, object], index: int) -> InventoriedModule:
    where = f"needs row {index}"
    module = _text(_field(row, "module", where), f"{where} module")
    package = _text(_field(row, "package", where), f"{where} package")
    tests: list[InventoriedTest] = []
    for test in _objects(_field(row, "tests", where), f"{module} tests"):
        name = _text(_field(test, "name", module), f"{module} test name")
        at = f"{module}::{name}"
        declarations = tuple(
            _declaration(each, f"{at} declaration")
            for each in _objects(_field(test, "declarations", at), f"{at} declarations")
        )
        local = _field(test, "local", at)
        tests.append(InventoriedTest(name, declarations, None if local is None else _text(local, f"{at} local")))
    return InventoriedModule(package, module, tuple(tests))


def read_inventory_modules(path: Path) -> tuple[InventoriedModule, ...]:
    """Every module row of ``needs.json`` at *path*, in file order.

    Raises:
        LibraryPlanError: *path* is missing, is not JSON, or a row lacks a field the inventory writes.
    """
    if not path.is_file():
        raise LibraryPlanError(f"{path} does not exist. Fix: run fixture-author.ps1 needs first.")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise LibraryPlanError(f"{path} is not JSON ({error}). Fix: rerun fixture-author.ps1 needs.") from error
    if not isinstance(document, dict):
        raise LibraryPlanError(f"{path} holds no object. Fix: rerun fixture-author.ps1 needs.")
    return tuple(
        _module_row(row, index)
        for index, row in enumerate(_objects(document.get("rows"), f"{path} rows"))
        if _field(row, "kind", f"needs row {index}") == MODULE_ROW
    )


def read_needs_inventory(path: Path) -> NeedsInventory:
    """The tests ``needs.json`` at *path* lists: those whose input can be shared, and the local count.

    Raises:
        LibraryPlanError: *path* is missing, is not JSON, or a row lacks a field the inventory writes.
    """
    shared: list[NeededTest] = []
    local = 0
    for row in read_inventory_modules(path):
        for test in row.tests:
            if test.local is not None:
                local += 1
            else:
                shared.append(NeededTest(row.package, row.module, test.name, test.declarations))
    return NeedsInventory(tests=tuple(shared), local=local)


def _distribution(name: str) -> str:
    return _DIST_BREAK.sub(_ENTRY_SEPARATOR, name).lower()


def platform_entries() -> dict[str, str]:
    """Each installed distribution registering ``datrix.platforms`` entry points, by normalized name,
    with its sorted-first entry-point name: the corpus entry its tests read.

    Raises:
        LibraryPlanError: an entry point belongs to no distribution, so its package cannot be named.
    """
    names: dict[str, list[str]] = defaultdict(list)
    for point in entry_points(group=PLATFORM_GROUP):
        if point.dist is None:
            raise LibraryPlanError(
                f"the {PLATFORM_GROUP!r} entry point {point.name!r} belongs to no installed distribution, so "
                "the package whose tests read its entry is unknown. Fix: install the platform package."
            )
        names[_distribution(point.dist.name)].append(point.name)
    return {dist: sorted(points)[0] for dist, points in sorted(names.items())}


def _slug(text: str) -> str:
    slug = _SLUG_BREAK.sub(_ENTRY_SEPARATOR, text.lower()).strip(_ENTRY_SEPARATOR)
    return slug or hashlib.sha256(text.encode("utf-8")).hexdigest()[:_DIGEST_CHARS]


def _choices(test: NeededTest, is_choice: ChoiceKeys) -> dict[str, str]:
    """The system choices *test* reads, by key; of two values read for one key, the smaller."""
    held: dict[str, str] = {}
    for declaration in test.declarations:
        if declaration.kind not in SYSTEM_KINDS:
            continue
        for fact in declaration.facts:
            key, value = fact_parts(fact)
            if value and is_choice(declaration.kind, key, value):
                held[key] = min(held.get(key, value), value)
    return held


def _split_entry(base: str, minority: Sequence[tuple[str, str]]) -> str:
    parts = [] if base == LIBRARY_ENTRY else [base]
    parts.extend(f"{_slug(key)}{_ENTRY_SEPARATOR}{_slug(value)}" for key, value in minority)
    return _ENTRY_SEPARATOR.join(parts)


def _place_choices(base: str, tests: Sequence[NeededTest], is_choice: ChoiceKeys) -> Iterator[tuple[str, NeededTest]]:
    """Each test of the entry *base* with the entry it reads: *base*, or the split its minority choices name."""
    held = [_choices(test, is_choice) for test in tests]
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    for choices in held:
        for key, value in choices.items():
            counts[key][value] += 1
    majority = {key: min(values.items(), key=lambda item: (-item[1], item[0]))[0] for key, values in counts.items()}
    for test, choices in zip(tests, held, strict=True):
        minority = sorted((key, value) for key, value in choices.items() if value != majority[key])
        yield (_split_entry(base, minority) if minority else base), test


def _test_families(test: NeededTest, families: Mapping[str, str]) -> Iterator[tuple[Declaration, str | None]]:
    """Each declaration of *test* with its family; ``None`` for a system-level one."""
    blocks = declared_blocks(test.declarations, families)
    test_family = min((family for _, family in blocks), default=CORE_FAMILY)
    for declaration in test.declarations:
        if declaration.kind in SYSTEM_KINDS:
            yield declaration, None
            continue
        family = enclosing_family(declaration, blocks)
        if family is None:
            parts = declaration_parts(declaration.path)
            enclosed = sorted(family for prefix, family in blocks if prefix[: len(parts)] == parts)
            family = enclosed[0] if enclosed else test_family
        yield declaration, family


def union_declarations(declarations: Iterable[Declaration]) -> tuple[Declaration, ...]:
    """*declarations* unioned by kind and path, each one's facts unioned and sorted, in path order."""
    facts: dict[tuple[str, str], set[str]] = defaultdict(set)
    for declaration in declarations:
        facts[(declaration.path, declaration.kind)].update(declaration.facts)
    return tuple(Declaration(kind, path, tuple(sorted(held))) for (path, kind), held in sorted(facts.items()))


def _entry_plan(entry: str, tests: Sequence[NeededTest], families: Mapping[str, str]) -> EntryPlan:
    system: list[Declaration] = []
    by_family: dict[str, list[Declaration]] = defaultdict(list)
    for test in tests:
        for declaration, family in _test_families(test, families):
            if family is None:
                system.append(declaration)
            else:
                by_family[family].append(declaration)
    return EntryPlan(
        entry=entry,
        tests=tuple(tests),
        system=union_declarations(system),
        families={family: union_declarations(held) for family, held in sorted(by_family.items())},
    )


def plan_library(
    inventory: NeedsInventory,
    families: Mapping[str, str],
    platforms: Mapping[str, str],
    is_choice: ChoiceKeys,
) -> LibraryPlan:
    """Place every shareable test of *inventory* in its entry and each of its declarations in its family.

    Args:
        inventory: The tests to place (``read_needs_inventory``).
        families: Each block kind with its family (``needs_command.block_families``).
        platforms: Each platform distribution with the entry its tests read (``platform_entries``).
        is_choice: Whether a key of a system-level declaration is a choice (``library_check``).

    Raises:
        LibraryPlanError: a block family is named ``core``, so the services holding no block have no family.
    """
    if CORE_FAMILY in families.values():
        raise LibraryPlanError(
            f"a block kind opens the family {CORE_FAMILY!r}, the family of services holding no block. Fix: "
            "rename CORE_FAMILY."
        )
    by_base: dict[str, list[NeededTest]] = defaultdict(list)
    for test in inventory.tests:
        by_base[platforms.get(_distribution(test.package), LIBRARY_ENTRY)].append(test)
    placed: dict[str, list[NeededTest]] = defaultdict(list)
    for base, tests in by_base.items():
        for entry, test in _place_choices(base, tests, is_choice):
            placed[entry].append(test)
    entries = tuple(_entry_plan(entry, tests, families) for entry, tests in sorted(placed.items()))
    return LibraryPlan(entries=entries, local=inventory.local)


__all__ = [
    "CORE_FAMILY",
    "LIBRARY_ENTRY",
    "SYSTEM_KINDS",
    "ChoiceKeys",
    "EntryPlan",
    "InventoriedModule",
    "InventoriedTest",
    "LibraryPlan",
    "LibraryPlanError",
    "NeededTest",
    "NeedsInventory",
    "fact_parts",
    "plan_library",
    "platform_entries",
    "read_inventory_modules",
    "read_needs_inventory",
    "union_declarations",
]
