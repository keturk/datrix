#!/usr/bin/env python3
"""Migration upgrade-op family gate: the cross-package half of the upgrade-op
duplication census.

The census that produced this gate read the bodies of six
``_build_upgrade_op_for_*`` symbols across every target that defined them and
reached two conclusions worth pinning:

* **The six are genuinely target-specific, not collapsible** -- judged against
  the bodies rather than against the shared name -- so each target that
  carries the family must still define every one of them exactly once: a later
  "cleanup" that deleted one would be deleting a target's real behaviour.
* **One genuinely shared fact was found and hoisted.** The targets reassembled
  the ``INDEX_ADDED`` JSON detail payload into its ``SnapshotIndex`` with
  byte-identical semantics and byte-identical error text. That parse now lives
  once, in ``datrix_codegen_common.algorithms.migration_upgrade_op_index``, and
  this gate holds it there: each target must CALL the shared parser the exact
  number of times its own paths need, and none may redefine it.

**Why this is a script and not a pytest module.** Every check above reads a
generator package's sources against a module that lives in
``datrix-codegen-common``, and adding a target to the family makes it a
comparison across generator packages. A unit test that imports several
generator packages to compare their bodies is the exact shape the repo
boundary forbids -- each ``datrix-*`` package tests only its own surface -- and
repo-level validation belongs as a script under ``datrix/scripts/test/``. The
shared parser's own behaviour (input -> ``SnapshotIndex``) is a different
question and stays where it belongs, as a unit test in
``datrix-codegen-common``, which owns the function.

**The gate names no target.** Every registered ``datrix.languages`` package
is scanned -- its backend and each language core it requires -- resolved
through the registry, never a list in this module. Which languages carry the
family and how many call sites each one's own paths need are reviewed facts
held per registered language in
``scripts/config/migration-upgrade-op-family-baseline.json``:

* ``carries_divergent_family`` -- the language must define each of the six
  exactly once; a language NOT recorded as a carrier that defines any of them
  fails until it is recorded, so a new carrier is reviewed, never silently
  exempt. A baseline that records no carrier at all fails as vacuous.
* ``shared_parser_call_sites`` -- the exact count of resolved calls of the
  shared parser. A language with no entry is held to zero calls and no
  family, so adding a language needs no edit while it uses neither.

An entry naming a language that is not registered is stale and fails. The
self-test first proves this module names no registered target
(``datrix_scripts.registered_targets.self_test_gate_names_no_target``).

Structural resolution only, never a text match: call sites are found by reading
each module's import bindings and matching resolved callees, so an aliased
import is followed and a same-suffix private wrapper is not miscounted. Both
false-positive shapes have bitten this chain before, so both are proven every
run by the built-in non-vacuity self-test, along with the two directions that
prove the resolver can find a call at all, and the baseline comparison against
fixture languages in both directions.

Repo-level validation script (per the datrix showcase boundary -- no pytest
suite lives in datrix).

Usage::

    python migration_upgrade_op_family.py
    python migration_upgrade_op_family.py --debug
    python migration_upgrade_op_family.py --self-test
"""

from __future__ import annotations

import argparse
import ast
import json
import logging
import shutil
import sys
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from datrix_scripts.paths import SHOWCASE_DIR
from datrix_scripts.registered_targets import (
    AXIS_LANGUAGES,
    WORKSPACE_ROOT,
    discover_target_package_src_dirs,
    registered_language_names,
    self_test_gate_names_no_target,
)

logger = logging.getLogger(__name__)

EXIT_OK: Final[int] = 0
EXIT_FAIL: Final[int] = 1
EXIT_USAGE: Final[int] = 2

DATRIX_DIR: Final[Path] = SHOWCASE_DIR
BASELINE_PATH: Final[Path] = (
    DATRIX_DIR / "scripts" / "config" / "migration-upgrade-op-family-baseline.json"
)

_LANGUAGES_KEY: Final[str] = "languages"
_CARRIES_FAMILY_KEY: Final[str] = "carries_divergent_family"
_CALL_SITES_KEY: Final[str] = "shared_parser_call_sites"
_ENTRY_KEYS: Final[frozenset[str]] = frozenset({_CARRIES_FAMILY_KEY, _CALL_SITES_KEY})

#: The six upgrade-op builders the census read in full and found genuinely
#: target-specific. Each must keep exactly one definition per target.
DIVERGENT_SYMBOLS: Final[tuple[str, ...]] = (
    "_build_upgrade_op_for_entity_added",
    "_build_upgrade_op_for_field_added",
    "_build_upgrade_op_for_index_added",
    "_build_upgrade_op_for_nullable_changed",
    "_build_upgrade_op_for_relationship_added",
    "_build_upgrade_op_for_type_changed",
)

#: The one symbol the census DID hoist, and its new single home.
SHARED_MODULE: Final[str] = "datrix_codegen_common.algorithms.migration_upgrade_op_index"
SHARED_SYMBOL: Final[str] = "parse_index_added_detail"

#: The pre-hoist private name, which must not survive in any target.
RETIRED_PRIVATE_SYMBOL: Final[str] = "_index_from_index_added_detail"

class GateConfigurationError(RuntimeError):
    """The packages or the baseline this gate reads could not be resolved."""


@dataclass(frozen=True)
class FamilyEntry:
    """One registered language's reviewed facts about this family.

    Attributes:
        carries_divergent_family: The language defines each divergent symbol
            exactly once.
        shared_parser_call_sites: The exact number of resolved calls of the
            shared parser its own paths make.
    """

    carries_divergent_family: bool
    shared_parser_call_sites: int


#: What a registered language with no baseline entry is held to: it carries no
#: family and never calls the shared parser.
NO_ENTRY: Final[FamilyEntry] = FamilyEntry(carries_divergent_family=False, shared_parser_call_sites=0)


def _parse_entry(language: str, raw: object, source: Path) -> FamilyEntry:
    """Validate one baseline entry; a malformed one is a configuration error."""
    if not isinstance(raw, dict) or set(raw) != _ENTRY_KEYS:
        raise GateConfigurationError(
            f"{source}: entry for {language!r} must be an object with exactly the keys "
            f"{sorted(_ENTRY_KEYS)}, got {raw!r}. Fix: correct the entry."
        )
    carries = raw[_CARRIES_FAMILY_KEY]
    call_sites = raw[_CALL_SITES_KEY]
    if not isinstance(carries, bool):
        raise GateConfigurationError(
            f"{source}: {language!r}.{_CARRIES_FAMILY_KEY} must be true or false, got {carries!r}."
        )
    if isinstance(call_sites, bool) or not isinstance(call_sites, int) or call_sites < 0:
        raise GateConfigurationError(
            f"{source}: {language!r}.{_CALL_SITES_KEY} must be a non-negative integer, "
            f"got {call_sites!r}."
        )
    return FamilyEntry(carries_divergent_family=carries, shared_parser_call_sites=call_sites)


def load_baseline(path: Path) -> dict[str, FamilyEntry]:
    """Read the per-language reviewed facts from *path*.

    Raises:
        GateConfigurationError: The file is missing, is not JSON, or an entry is
            malformed. Never a silent default: a missing baseline would hold
            every language to no family and no calls and fail for the wrong reason.
    """
    if not path.is_file():
        raise GateConfigurationError(
            f"Baseline {path} does not exist. Expected a JSON object with a "
            f"'{_LANGUAGES_KEY}' mapping of registered language -> "
            f"{{{_CARRIES_FAMILY_KEY!r}: bool, {_CALL_SITES_KEY!r}: int}}. Fix: restore the file."
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GateConfigurationError(f"Baseline {path} is not valid JSON: {exc}.") from exc
    languages = raw.get(_LANGUAGES_KEY) if isinstance(raw, dict) else None
    if not isinstance(languages, dict):
        raise GateConfigurationError(
            f"Baseline {path} must be an object whose '{_LANGUAGES_KEY}' key is a mapping of "
            f"registered language -> entry; got {raw!r}."
        )
    return {language: _parse_entry(language, entry, path) for language, entry in languages.items()}


def language_source_roots() -> dict[str, tuple[Path, ...]]:
    """Every registered language -> the ``src/<import_name>`` directory of every
    package implementing it (its backend, then each language core it requires).

    Raises:
        GateConfigurationError: A registered language resolves to no on-disk
            package. Never a silent skip: an unscanned language would pass vacuously.
    """
    try:
        return discover_target_package_src_dirs(
            AXIS_LANGUAGES, registered_language_names(), WORKSPACE_ROOT
        )
    except ValueError as exc:
        raise GateConfigurationError(
            f"Cannot resolve the registered languages' source trees: {exc}. Fix: install the "
            f"datrix packages in editable mode into D:\\datrix\\.venv."
        ) from exc


def _local_bindings(tree: ast.Module, module: str, symbol: str) -> tuple[set[str], set[str]]:
    """Names *symbol* and *module* are bound to in this module's namespace.

    Resolves ``from <module> import <symbol> as <alias>`` and
    ``import <module> as <alias>`` so a call site that never spells the bare
    symbol is still resolved -- a text search cannot do this, and a bare-name
    search additionally matches an unrelated private wrapper whose name merely
    ends with the same token.

    Args:
        tree: The parsed module.
        module: Fully-qualified module the symbol is defined in.
        symbol: The function name as defined in *module*.

    Returns:
        ``(direct_names, module_names)`` -- names bound directly to the
        function, and names bound to the module itself for ``module.symbol(...)``
        calls.
    """
    direct: set[str] = set()
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == module:
            for alias in node.names:
                if alias.name == symbol:
                    direct.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == module:
                    modules.add(alias.asname or alias.name)
    return direct, modules


#: Parsed source of every scanned root, keyed by root. This gate asks many
#: questions of the same trees per invocation (six symbols per target, plus
#: the call-site and redefinition scans); re-parsing per question is what
#: made it take three times as long as the work it does.
_PARSED_ROOTS: dict[Path, list[tuple[Path, ast.Module]]] = {}


def _parsed_files(root: Path) -> list[tuple[Path, ast.Module]]:
    """Every ``.py`` file under *root*, parsed once and cached by root."""
    cached = _PARSED_ROOTS.get(root)
    if cached is None:
        cached = [
            (py_file, ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file)))
            for py_file in sorted(root.rglob("*.py"))
        ]
        _PARSED_ROOTS[root] = cached
    return cached


def call_sites(root: Path) -> list[tuple[Path, int]]:
    """Every resolved call site of the shared parser under *root*.

    Args:
        root: A package's own top-level source directory.

    Returns:
        ``(file, line)`` for each resolved call, structurally -- never a text
        match.
    """
    hits: list[tuple[Path, int]] = []
    for py_file, tree in _parsed_files(root):
        direct, modules = _local_bindings(tree, SHARED_MODULE, SHARED_SYMBOL)
        if not direct and not modules:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Name) and func.id in direct:
                hits.append((py_file, node.lineno))
            elif (
                isinstance(func, ast.Attribute)
                and func.attr == SHARED_SYMBOL
                and isinstance(func.value, ast.Name)
                and func.value.id in modules
            ):
                hits.append((py_file, node.lineno))
    return hits


def definitions_of(root: Path, symbol: str) -> list[tuple[Path, int]]:
    """Every ``def <symbol>`` under *root*."""
    found: list[tuple[Path, int]] = []
    for py_file, tree in _parsed_files(root):
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == symbol:
                found.append((py_file, node.lineno))
    return found


def _definitions_under(roots: tuple[Path, ...], symbol: str) -> list[tuple[Path, int]]:
    """Every ``def <symbol>`` under any of one language's package roots."""
    return [hit for root in roots for hit in definitions_of(root, symbol)]


def _call_sites_under(roots: tuple[Path, ...]) -> list[tuple[Path, int]]:
    """Every resolved shared-parser call under any of one language's package roots."""
    return [hit for root in roots for hit in call_sites(root)]


def _format_hits(hits: list[tuple[Path, int]]) -> list[str]:
    return [f"{path}:{line}" for path, line in hits]


def stale_entry_problems(baseline: Mapping[str, FamilyEntry], registered: frozenset[str]) -> list[str]:
    """One problem per baseline entry naming a language that is not registered."""
    return [
        f"Baseline entry {language!r} names a language that is not registered (registered: "
        f"{sorted(registered)}). Fix: remove the stale entry from {BASELINE_PATH.name}."
        for language in sorted(set(baseline) - registered)
    ]


def check_divergent_family(
    roots: Mapping[str, tuple[Path, ...]], baseline: Mapping[str, FamilyEntry]
) -> list[str]:
    """Each recorded carrier defines every divergent symbol exactly once, and a
    language not recorded as a carrier defines none of them."""
    carriers = sorted(
        language for language in roots if baseline.get(language, NO_ENTRY).carries_divergent_family
    )
    if not carriers:
        return [
            f"No registered language is recorded as carrying the upgrade-op family in "
            f"{BASELINE_PATH.name} (scanned: {sorted(roots)}), so the survival check would pass "
            f"vacuously. Fix: record the carrier, or retire this check if the family is gone."
        ]
    problems: list[str] = []
    for language, language_roots in sorted(roots.items()):
        carries = language in carriers
        for symbol in DIVERGENT_SYMBOLS:
            hits = _definitions_under(language_roots, symbol)
            if carries and len(hits) != 1:
                problems.append(
                    f"{language} carries the upgrade-op family, and {symbol} is genuinely "
                    f"target-specific, not hoisted, so it must define it exactly once -- found "
                    f"{_format_hits(hits)}. Deleting one deletes the target's real behaviour."
                )
            elif not carries and hits:
                problems.append(
                    f"{language} defines {symbol} at {_format_hits(hits)} but is not recorded as "
                    f"carrying the upgrade-op family. Fix: set {_CARRIES_FAMILY_KEY} for "
                    f"{language!r} in {BASELINE_PATH.name} once the whole family is in place."
                )
    return problems


def check_shared_parser_reachability(
    roots: Mapping[str, tuple[Path, ...]], baseline: Mapping[str, FamilyEntry]
) -> list[str]:
    """Each language calls the shared parser exactly the recorded number of
    times its own paths need, and none redefines the parse."""
    problems: list[str] = []
    for language, language_roots in sorted(roots.items()):
        expected = baseline.get(language, NO_ENTRY).shared_parser_call_sites
        hits = _call_sites_under(language_roots)
        if len(hits) != expected:
            problems.append(
                f"{language} has {len(hits)} resolved call site(s) of {SHARED_SYMBOL}, "
                f"expected {expected} ({_CALL_SITES_KEY} in {BASELINE_PATH.name}). Resolved: "
                f"{_format_hits(hits)}. Fewer means a path stopped calling the shared parser and "
                f"re-grew a private copy; more means a new path, so review it and record the "
                f"new count in the same change."
            )
        for symbol in (SHARED_SYMBOL, RETIRED_PRIVATE_SYMBOL):
            redefinitions = _definitions_under(language_roots, symbol)
            if redefinitions:
                problems.append(
                    f"{language} redefines {symbol!r} at {_format_hits(redefinitions)}; the "
                    f"parse has one home, {SHARED_MODULE}."
                )
    return problems


def evaluate(
    roots: Mapping[str, tuple[Path, ...]],
    baseline: Mapping[str, FamilyEntry],
    registered: frozenset[str],
) -> list[str]:
    """Every violation of this family across *roots* against *baseline*."""
    problems = stale_entry_problems(baseline, registered)
    problems.extend(check_divergent_family(roots, baseline))
    problems.extend(check_shared_parser_reachability(roots, baseline))
    return problems


# ---------------------------------------------------------------------------
# Non-vacuity self-test
# ---------------------------------------------------------------------------


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _check_resolver_finds_a_planted_call(tmp_path: Path) -> list[str]:
    """The resolver can find a call at all -- a scan that can only return zero
    is not evidence."""
    _write(
        tmp_path / "caller.py",
        f"from {SHARED_MODULE} import {SHARED_SYMBOL}\n"
        f"def go(d):\n    return {SHARED_SYMBOL}(d)\n",
    )
    hits = call_sites(tmp_path)
    if len(hits) == 1:
        return []
    return [f"a planted direct call was not resolved: {hits}"]


def _check_resolver_follows_an_import_alias(tmp_path: Path) -> list[str]:
    """The call site never spells the symbol -- only its alias."""
    _write(
        tmp_path / "aliased.py",
        f"from {SHARED_MODULE} import {SHARED_SYMBOL} as _shared_parse\n"
        "def go(d):\n    return _shared_parse(d)\n",
    )
    hits = call_sites(tmp_path)
    if len(hits) == 1:
        return []
    return [f"an aliased call was not resolved: {hits}"]


def _check_resolver_finds_a_module_qualified_call(tmp_path: Path) -> list[str]:
    """``import module as alias`` then ``alias.symbol(...)`` also resolves."""
    _write(
        tmp_path / "qualified.py",
        f"import {SHARED_MODULE} as _mod\n"
        f"def go(d):\n    return _mod.{SHARED_SYMBOL}(d)\n",
    )
    hits = call_sites(tmp_path)
    if len(hits) == 1:
        return []
    return [f"a module-qualified call was not resolved: {hits}"]


def _check_resolver_ignores_a_same_suffix_private_wrapper(tmp_path: Path) -> list[str]:
    """The false-positive shape this chain has already been bitten by twice: a
    private wrapper whose name merely ends with the shared symbol's name."""
    _write(
        tmp_path / "wrapper.py",
        f"def _{SHARED_SYMBOL}(d):\n    return d\n"
        f"def go(d):\n    return _{SHARED_SYMBOL}(d)\n",
    )
    hits = call_sites(tmp_path)
    if not hits:
        return []
    return [f"a same-suffix private wrapper was miscounted as a call: {hits}"]


def _check_resolver_ignores_a_bare_name_mention(tmp_path: Path) -> list[str]:
    """A docstring mention and a string constant are not calls."""
    _write(
        tmp_path / "mention.py",
        f'"""Docs mentioning {SHARED_SYMBOL} and nothing else."""\n'
        f"MESSAGE = {SHARED_SYMBOL!r}\n",
    )
    hits = call_sites(tmp_path)
    if not hits:
        return []
    return [f"a bare-name mention was miscounted as a call: {hits}"]


def _check_definition_scan_finds_a_planted_definition(tmp_path: Path) -> list[str]:
    """The definition scan the survival and redefinition checks rest on finds a
    definition it is pointed at, and does not invent one."""
    problems: list[str] = []
    _write(
        tmp_path / "defs.py",
        f"def {DIVERGENT_SYMBOLS[0]}(self, change):\n    return change\n",
    )
    if len(definitions_of(tmp_path, DIVERGENT_SYMBOLS[0])) != 1:
        problems.append("a planted definition was not found by the definition scan")
    if definitions_of(tmp_path, SHARED_SYMBOL):
        problems.append("the definition scan invented a definition that is not there")
    return problems


_FIXTURE_CARRIER: Final[str] = "self_test_family_carrier"
_FIXTURE_CALLER: Final[str] = "self_test_family_caller"
_FIXTURE_THIRD: Final[str] = "self_test_family_third"
_FIXTURE_CARRIER_CALLS: Final[int] = 2


def _write_family_fixture(tmp_path: Path, *, omit_symbol: str | None = None) -> dict[str, tuple[Path, ...]]:
    """Two fixture languages: a carrier defining the family (minus *omit_symbol*)
    and calling the shared parser twice, and a non-carrier calling it once."""
    carrier = tmp_path / _FIXTURE_CARRIER
    caller = tmp_path / _FIXTURE_CALLER
    definitions = "".join(
        f"def {symbol}(change, context):\n    return change\n"
        for symbol in DIVERGENT_SYMBOLS
        if symbol != omit_symbol
    )
    _write(carrier / "builders.py", definitions)
    _write(
        carrier / "render.py",
        f"from {SHARED_MODULE} import {SHARED_SYMBOL}\n"
        f"def render(d):\n    return {SHARED_SYMBOL}(d)\n"
        f"def audit(d):\n    return {SHARED_SYMBOL}(d)\n",
    )
    _write(
        caller / "adapter.py",
        f"import {SHARED_MODULE} as _mod\ndef index_of(d):\n    return _mod.{SHARED_SYMBOL}(d)\n",
    )
    return {_FIXTURE_CARRIER: (carrier,), _FIXTURE_CALLER: (caller,)}


def _fixture_baseline(*, carrier_calls: int = _FIXTURE_CARRIER_CALLS) -> dict[str, FamilyEntry]:
    return {
        _FIXTURE_CARRIER: FamilyEntry(carries_divergent_family=True, shared_parser_call_sites=carrier_calls),
        _FIXTURE_CALLER: FamilyEntry(carries_divergent_family=False, shared_parser_call_sites=1),
    }


def _fixture_registered() -> frozenset[str]:
    return frozenset({_FIXTURE_CARRIER, _FIXTURE_CALLER})


def _check_baseline_comparison_accepts_a_matching_tree(tmp_path: Path) -> list[str]:
    """A tree that matches its baseline exactly reports nothing."""
    problems = evaluate(_write_family_fixture(tmp_path), _fixture_baseline(), _fixture_registered())
    return [f"a matching fixture tree reported problems: {problems}"] if problems else []


def _check_baseline_comparison_rejects_each_divergence(tmp_path: Path) -> list[str]:
    """Each way a tree can diverge from its baseline is exactly one reported
    problem: a wrong count, a missing family member, an unrecorded carrier, a
    stale entry, and a baseline recording no carrier at all."""
    registered = _fixture_registered()
    roots = _write_family_fixture(tmp_path / "full")
    partial_roots = _write_family_fixture(tmp_path / "partial", omit_symbol=DIVERGENT_SYMBOLS[-1])
    # A second language carrying the same family with no baseline entry.
    unrecorded_roots = {**roots, _FIXTURE_THIRD: roots[_FIXTURE_CARRIER]}
    unrecorded_registered = registered | {_FIXTURE_THIRD}
    no_carrier = {
        _FIXTURE_CALLER: _fixture_baseline()[_FIXTURE_CALLER],
        _FIXTURE_CARRIER: FamilyEntry(carries_divergent_family=False, shared_parser_call_sites=2),
    }
    stale = {**_fixture_baseline(), _FIXTURE_THIRD: NO_ENTRY}
    cases: tuple[tuple[str, list[str], int], ...] = (
        ("a call count one below the record", evaluate(roots, _fixture_baseline(carrier_calls=3), registered), 1),
        ("a carrier missing one family member", evaluate(partial_roots, _fixture_baseline(), registered), 1),
        # Unrecorded: six definitions with no carrier record, and two calls against zero.
        (
            "a carrier with no baseline entry",
            evaluate(unrecorded_roots, _fixture_baseline(), unrecorded_registered),
            len(DIVERGENT_SYMBOLS) + 1,
        ),
        ("an entry naming an unregistered language", evaluate(roots, stale, registered), 1),
        # No carrier recorded: the vacuity refusal alone.
        ("a baseline recording no carrier", check_divergent_family(roots, no_carrier), 1),
    )
    return [
        f"{label}: expected {expected} problem(s), got {len(found)}: {found}"
        for label, found, expected in cases
        if len(found) != expected
    ]


def _check_baseline_loader_refuses_a_malformed_entry(tmp_path: Path) -> list[str]:
    """A count spelled as a boolean, a missing key, and a valid file each load as expected."""
    problems: list[str] = []
    malformed = (
        {_FIXTURE_CARRIER: {_CARRIES_FAMILY_KEY: True, _CALL_SITES_KEY: True}},
        {_FIXTURE_CARRIER: {_CARRIES_FAMILY_KEY: True}},
    )
    for index, languages in enumerate(malformed):
        path = tmp_path / f"malformed{index}.json"
        _write(path, json.dumps({_LANGUAGES_KEY: languages}))
        try:
            load_baseline(path)
        except GateConfigurationError:
            continue
        problems.append(f"load_baseline accepted a malformed entry: {languages}")
    valid = tmp_path / "valid.json"
    _write(valid, json.dumps({_LANGUAGES_KEY: {_FIXTURE_CARRIER: {_CARRIES_FAMILY_KEY: True, _CALL_SITES_KEY: 2}}}))
    if load_baseline(valid) != {_FIXTURE_CARRIER: _fixture_baseline()[_FIXTURE_CARRIER]}:
        problems.append("load_baseline misread a valid entry")
    return problems


#: Every self-test check, in the order they run.
_SELF_TEST_CHECKS: Final[tuple[tuple[str, Callable[[Path], list[str]]], ...]] = (
    ("resolver finds a planted direct call", _check_resolver_finds_a_planted_call),
    ("resolver follows an import alias", _check_resolver_follows_an_import_alias),
    ("resolver finds a module-qualified call", _check_resolver_finds_a_module_qualified_call),
    (
        "resolver ignores a same-suffix private wrapper",
        _check_resolver_ignores_a_same_suffix_private_wrapper,
    ),
    ("resolver ignores a bare-name mention", _check_resolver_ignores_a_bare_name_mention),
    ("definition scan finds a planted def and invents none", _check_definition_scan_finds_a_planted_definition),
    ("baseline comparison accepts a matching tree", _check_baseline_comparison_accepts_a_matching_tree),
    ("baseline comparison rejects each divergence", _check_baseline_comparison_rejects_each_divergence),
    ("baseline loader refuses a malformed entry", _check_baseline_loader_refuses_a_malformed_entry),
)


def run_self_test() -> list[str]:
    """Prove this gate names no registered target, and that the call-site and
    definition resolvers and the baseline comparison are non-vacuous in both
    directions, before any real comparison is trusted.

    Returns:
        Problem descriptions; empty means the gate is sound.
    """
    problems: list[str] = [
        f"gate names no registered target: {line}" for line in self_test_gate_names_no_target(__file__)
    ]
    tmp_root = Path(tempfile.mkdtemp(prefix="migration-upgrade-op-family-selftest-"))
    try:
        for index, (label, check) in enumerate(_SELF_TEST_CHECKS):
            check_problems = check(tmp_root / f"check{index}")
            if check_problems:
                problems.extend(f"{label}: {problem}" for problem in check_problems)
            else:
                logger.debug("self_test_check_ok label=%s", label)
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
        # The fixture roots are gone; drop their parses so the real comparison
        # starts from an empty cache rather than entries keyed by deleted dirs.
        _PARSED_ROOTS.clear()
    return problems


# ---------------------------------------------------------------------------
# Gate entry point
# ---------------------------------------------------------------------------


def check_migration_upgrade_op_family() -> int:
    """Run every cross-package check in this family.

    Returns:
        Exit code: 0 = every check holds, 1 = at least one violation.
    """
    roots = language_source_roots()
    baseline = load_baseline(BASELINE_PATH)
    logger.info("scanned_targets targets=%s", sorted(roots))

    problems = evaluate(roots, baseline, registered_language_names())
    if problems:
        for problem in problems:
            logger.error("MIGRATION UPGRADE-OP FAMILY: %s", problem)
        return EXIT_FAIL
    carriers = sorted(
        language for language in roots if baseline.get(language, NO_ENTRY).carries_divergent_family
    )
    call_counts = {
        language: baseline.get(language, NO_ENTRY).shared_parser_call_sites for language in sorted(roots)
    }
    logger.info(
        "MIGRATION UPGRADE-OP FAMILY GATE PASSED: %d target-specific symbol(s) still defined "
        "once per carrier across %s, %s has one home with %s call site(s).",
        len(DIVERGENT_SYMBOLS),
        carriers,
        SHARED_SYMBOL,
        call_counts,
    )
    return EXIT_OK


def _parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Migration upgrade-op family gate: the six target-specific upgrade-op builders "
            "keep one definition per target, and the one hoisted "
            "INDEX_ADDED detail parse keeps exactly one home with the call sites each "
            "target's own paths need."
        ),
    )
    parser.add_argument("--debug", action="store_true", help="Enable DEBUG logging")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run only the non-vacuity self-test and skip the real comparison",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point.

    Returns:
        Process exit code: 0 = gate passed (or a successful ``--self-test``),
        1 = at least one violation, 2 = self-test failure, an unresolvable
        target package, or a missing/malformed baseline.
    """
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    problems = run_self_test()
    if problems:
        logger.error("NON-VACUITY SELF-TEST FAILED -- aborting before any real comparison:")
        for problem in problems:
            logger.error("  %s", problem)
        return EXIT_USAGE
    logger.info("non-vacuity self-test: PASS (%d checks)", len(_SELF_TEST_CHECKS))

    if args.self_test:
        return EXIT_OK

    try:
        return check_migration_upgrade_op_family()
    except GateConfigurationError as exc:
        logger.error("ERROR: %s", exc)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
