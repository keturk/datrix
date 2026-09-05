#!/usr/bin/env python3
"""Migration upgrade-op family gate: the cross-package half of the upgrade-op
duplication census.

The census that produced this gate read both bodies of six
``_build_upgrade_op_for_*`` symbols across the two targets that define them
(python's Alembic ``migration_generator.py`` and dotnet's FluentMigrator
``_fluentmigrator_ops.py``) and reached two conclusions worth pinning:

* **Five of the six are genuinely divergent, not collapsible.** Each entry in
  ``parallel-implementation-drift-classification.json`` was reclassified to
  ``collapsibility.mechanism = "none"`` against the bodies rather than against
  the label, and both private copies must therefore still exist -- a later
  "cleanup" that deleted one would be deleting a target's real behaviour. The
  ``_build_upgrade_op_for_field_added`` entry additionally records a behaviour
  gap that has since been CLOSED: dotnet emitted no default at all, so a
  non-nullable ``FIELD_ADDED`` the shared change policy classifies *safe*
  rendered a migration that failed at apply time on any populated table.
  ``FluentMigratorColumn`` now carries a default-bearing field, so the entry is
  back to ``intentional`` describing only the ORM-API divergence -- and this
  gate holds both halves of that: the status, and the field that earns it.
* **One genuinely shared fact was found and hoisted.** Both targets reassembled
  the ``INDEX_ADDED`` JSON detail payload into its ``SnapshotIndex`` with
  byte-identical semantics and byte-identical error text. That parse now lives
  once, in ``datrix_codegen_common.algorithms.migration_upgrade_op_index``, and
  this gate holds it there: each target must CALL the shared parser the exact
  number of times its own paths need, and neither may redefine it.

**Why this is a script and not a pytest module.** Every check above compares
two generator packages' sources, from a check that would otherwise sit inside
``datrix-codegen-common``. A unit test that imports two generator packages to
compare their bodies is the exact shape the repo boundary forbids -- each
``datrix-*`` package tests only its own surface -- and repo-level validation
belongs as a script under ``datrix/scripts/test/``. The shared parser's own
behaviour (input -> ``SnapshotIndex``) is a different question and stays where
it belongs, as a unit test in ``datrix-codegen-common``, which owns the
function; only the cross-package census moved here.

**Target packages are resolved through the registry.** The two languages this
family spans are named -- they are a fact about which targets carry this
duplicate, not a claim about which targets exist -- but their packages are
resolved through the installed ``datrix.languages`` entry points, so a named
language that is not installed fails loud by name instead of letting its half
of the comparison pass vacuously.

Structural resolution only, never a text match: call sites are found by reading
each module's import bindings and matching resolved callees, so an aliased
import is followed and a same-suffix private wrapper is not miscounted. Both
false-positive shapes have bitten this chain before, so both are proven every
run by the built-in non-vacuity self-test, along with the two directions that
prove the resolver can find a call at all.

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
import importlib
import json
import logging
import shutil
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Final

_LIBRARY_DIR = Path(__file__).resolve().parent.parent
if _LIBRARY_DIR.exists() and str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from datrix_common.plugin.registry import LANGUAGES_GROUP, entry_points  # noqa: E402
from shared.registered_targets import registered_language_names  # noqa: E402

logger = logging.getLogger(__name__)

EXIT_OK: Final[int] = 0
EXIT_FAIL: Final[int] = 1
EXIT_USAGE: Final[int] = 2

_HERE = Path(__file__).resolve()
DATRIX_DIR: Final[Path] = _HERE.parents[3]
CLASSIFICATION_PATH: Final[Path] = (
    DATRIX_DIR / "scripts" / "config" / "parallel-implementation-drift-classification.json"
)

#: The six upgrade-op builders the census read in full and reclassified as
#: genuinely divergent. Each must keep exactly one definition per target.
RECLASSIFIED_SYMBOLS: Final[tuple[str, ...]] = (
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

#: The pre-hoist private name, which must not survive in either target.
RETIRED_PRIVATE_SYMBOL: Final[str] = "_index_from_index_added_detail"

#: The two registered languages whose migration generators carry this family,
#: and the exact number of resolved call sites each has for the shared parser.
#: python has two INDEX_ADDED detail call paths (the render path and the chain
#: audit); dotnet has one, in `_build_upgrade_op_for_index_added`. A count, not
#: a ">= 1": a path silently losing its call is the regression this pins.
SHARED_PARSER_CALL_SITES: Final[dict[str, int]] = {"python": 2, "dotnet": 1}

#: The language whose migration column model must carry the backfill default,
#: and where that model lives inside its own package.
_DEFAULT_BEARING_LANGUAGE: Final[str] = "dotnet"
_MIGRATION_OPS_RELATIVE_PATH: Final[tuple[str, ...]] = (
    "generators",
    "persistence",
    "_fluentmigrator_ops.py",
)
_MIGRATION_COLUMN_CLASS: Final[str] = "FluentMigratorColumn"

#: The classification entry whose status records that the backfill-default
#: behaviour gap is closed. `tracked` is what an entry says while a gap is
#: open; leaving it behind once the gap is closed makes the field mean nothing.
_CLOSED_GAP_SYMBOL: Final[str] = "_build_upgrade_op_for_field_added"
_CLOSED_GAP_STATUS: Final[str] = "intentional"


class GateConfigurationError(RuntimeError):
    """The packages or the classification file this gate reads could not be
    resolved."""


def _language_module_roots() -> dict[str, str]:
    """Registered language name -> its plugin's top-level module root.

    Read from each entry point's DECLARED module rather than by loading the
    plugin: this gate only needs to know which package the code lives in.
    """
    return {ep.name: ep.module.split(".")[0] for ep in entry_points(group=LANGUAGES_GROUP)}


def language_source_root(language: str) -> Path:
    """The top-level source directory of *language*'s codegen package.

    Args:
        language: A registered ``datrix.languages`` entry-point name.

    Returns:
        The absolute directory holding that package's modules.

    Raises:
        GateConfigurationError: If the language is not registered, has no
            resolvable module root, or cannot be imported. Never a silent skip:
            an absent half of a two-target comparison would pass vacuously.
    """
    registered = registered_language_names()
    if language not in registered:
        raise GateConfigurationError(
            f"Language {language!r} is not registered; installed languages are "
            f"{sorted(registered)}. This gate compares the migration upgrade-op family "
            f"across {sorted(SHARED_PARSER_CALL_SITES)}, so a missing one cannot be "
            f"skipped. Fix: install the datrix-codegen-{language} package into "
            f"D:\\datrix\\.venv, or retire this gate if the target is gone."
        )
    module_roots = _language_module_roots()
    import_name = module_roots.get(language)
    if import_name is None:
        raise GateConfigurationError(
            f"Registered language {language!r} declares no entry-point module in the "
            f"'{LANGUAGES_GROUP}' group; got {sorted(module_roots)}. Fix: repair that "
            f"package's entry-point declaration."
        )
    try:
        module = importlib.import_module(import_name)
    except ImportError as exc:
        raise GateConfigurationError(
            f"Cannot import {import_name!r} to locate {language}'s source tree: {exc}. "
            f"Fix: install the datrix packages in editable mode into D:\\datrix\\.venv."
        ) from exc
    module_file = getattr(module, "__file__", None)
    if module_file is None:
        raise GateConfigurationError(
            f"Package {import_name!r} has no __file__, so its source tree cannot be "
            f"located. Expected a regular package with an __init__.py."
        )
    return Path(module_file).resolve().parent


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


#: Parsed source of every scanned root, keyed by root. This gate asks ~18
#: questions of the same two trees per invocation (six symbols x two targets,
#: plus the call-site and redefinition scans); re-parsing per question is what
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


def _load_classification() -> dict[str, dict[str, object]]:
    """The drift-classification entries, keyed by symbol.

    Raises:
        GateConfigurationError: If the file is absent or malformed.
    """
    if not CLASSIFICATION_PATH.exists():
        raise GateConfigurationError(
            f"Drift classification file not found at {CLASSIFICATION_PATH}. Expected the "
            f"parallel-implementation drift classification this gate pins entries in. "
            f"Fix: restore the file, or retire this gate if the classification moved."
        )
    try:
        document = json.loads(CLASSIFICATION_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GateConfigurationError(
            f"{CLASSIFICATION_PATH} is not valid JSON: {exc}. Expected an object with a "
            f"'classifications' member. Fix: repair the file."
        ) from exc
    classifications = document.get("classifications")
    if not isinstance(classifications, dict):
        raise GateConfigurationError(
            f"{CLASSIFICATION_PATH} has no 'classifications' object (top-level keys: "
            f"{sorted(document)}). Expected symbol -> entry. Fix: repair the file."
        )
    return classifications


def check_reclassified_entries(classifications: dict[str, dict[str, object]]) -> list[str]:
    """Every reclassified symbol keeps ``mechanism: none`` with its own reason.

    The collapsibility reason must differ from the legitimacy reason: an entry
    that repeats one string for both has answered only one of the two questions
    the classification asks.
    """
    problems: list[str] = []
    for symbol in RECLASSIFIED_SYMBOLS:
        entry = classifications.get(symbol)
        if entry is None:
            problems.append(
                f"classification entry for {symbol!r} is gone; the census reclassified it "
                f"rather than hoisting it, so the entry must survive. Present entries: "
                f"{len(classifications)}."
            )
            continue
        collapsibility = entry.get("collapsibility")
        if not isinstance(collapsibility, dict):
            problems.append(f"{symbol}: entry has no 'collapsibility' object")
            continue
        mechanism = collapsibility.get("mechanism")
        if mechanism != "none":
            problems.append(
                f"{symbol}: collapsibility.mechanism is {mechanism!r}, expected 'none' -- "
                f"the census read both bodies and found no shared mechanism."
            )
        if collapsibility.get("reason") == entry.get("reason"):
            problems.append(
                f"{symbol}: collapsibility.reason repeats the legitimacy reason verbatim, "
                f"so 'why is this legitimate' and 'what would remove it' are not both "
                f"answered."
            )
    return problems


def check_closed_gap_status(classifications: dict[str, dict[str, object]]) -> list[str]:
    """The backfill-default gap is closed, so its entry says ``intentional``."""
    entry = classifications.get(_CLOSED_GAP_SYMBOL)
    if entry is None:
        return [f"classification entry for {_CLOSED_GAP_SYMBOL!r} is gone"]
    status = entry.get("status")
    if status == _CLOSED_GAP_STATUS:
        return []
    return [
        f"{_CLOSED_GAP_SYMBOL}: status is {status!r}, expected {_CLOSED_GAP_STATUS!r}. "
        f"dotnet now emits a database-side backfill default for an incrementally added "
        f"non-nullable column, so only the ORM-API divergence (Alembic kw_parts strings "
        f"vs a typed {_MIGRATION_COLUMN_CLASS}) remains; 'tracked' is what an entry says "
        f"while a behaviour gap is open."
    ]


def check_both_private_copies_survive(roots: dict[str, Path]) -> list[str]:
    """Each reclassified symbol keeps exactly one definition per target."""
    problems: list[str] = []
    for symbol in RECLASSIFIED_SYMBOLS:
        per_language = {
            language: definitions_of(root, symbol) for language, root in sorted(roots.items())
        }
        total = sum(len(hits) for hits in per_language.values())
        if total != len(roots):
            problems.append(
                f"{symbol} was reclassified, not hoisted, so each of {sorted(roots)} must "
                f"still define it exactly once -- found "
                f"{ {language: [f'{path}:{line}' for path, line in hits] for language, hits in per_language.items()} }."
            )
    return problems


def check_migration_column_carries_a_default(root: Path) -> list[str]:
    """The migration column model declares a default-bearing field.

    This is the positive replacement for the pin that recorded the gap: the
    field is what lets an incremental ``add_column`` op backfill the rows a
    populated table already holds.
    """
    ops_path = root.joinpath(*_MIGRATION_OPS_RELATIVE_PATH)
    if not ops_path.exists():
        return [
            f"{_DEFAULT_BEARING_LANGUAGE}'s migration ops module is not at {ops_path}. "
            f"Expected the module declaring {_MIGRATION_COLUMN_CLASS}. Fix: re-point this "
            f"gate at its new location if the module moved."
        ]
    tree = ast.parse(ops_path.read_text(encoding="utf-8"), filename=str(ops_path))
    column_fields: set[str] = set()
    found_class = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != _MIGRATION_COLUMN_CLASS:
            continue
        found_class = True
        for stmt in node.body:
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                column_fields.add(stmt.target.id)
    if not found_class:
        return [f"{ops_path} declares no {_MIGRATION_COLUMN_CLASS} class"]
    if not column_fields:
        return [f"{_MIGRATION_COLUMN_CLASS} must declare annotated fields; it declares none"]
    if not {field for field in column_fields if "default" in field}:
        return [
            f"{_MIGRATION_COLUMN_CLASS} declares no default field, so an incremental ADD "
            f"COLUMN cannot carry the database-side backfill default a NOT NULL add to a "
            f"populated table requires. Declared fields: {sorted(column_fields)}."
        ]
    return []


def check_shared_parser_reachability(roots: dict[str, Path]) -> list[str]:
    """Each target calls the shared parser the exact number of times its own
    paths need, and neither redefines the parse."""
    problems: list[str] = []
    for language, root in sorted(roots.items()):
        expected = SHARED_PARSER_CALL_SITES[language]
        hits = call_sites(root)
        if len(hits) != expected:
            problems.append(
                f"{language} has {len(hits)} resolved call site(s) of {SHARED_SYMBOL}, "
                f"expected {expected}. Resolved: "
                f"{[f'{path}:{line}' for path, line in hits]}. A path that stopped calling "
                f"the shared parser has re-grown a private copy of it."
            )
        for symbol in (SHARED_SYMBOL, RETIRED_PRIVATE_SYMBOL):
            redefinitions = definitions_of(root, symbol)
            if redefinitions:
                problems.append(
                    f"{language} redefines {symbol!r} at "
                    f"{[f'{path}:{line}' for path, line in redefinitions]}; the parse has "
                    f"one home, {SHARED_MODULE}."
                )
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
        f"def {RECLASSIFIED_SYMBOLS[0]}(self, change):\n    return change\n",
    )
    if len(definitions_of(tmp_path, RECLASSIFIED_SYMBOLS[0])) != 1:
        problems.append("a planted definition was not found by the definition scan")
    if definitions_of(tmp_path, SHARED_SYMBOL):
        problems.append("the definition scan invented a definition that is not there")
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
)


def run_self_test() -> list[str]:
    """Prove the call-site and definition resolvers are non-vacuous in both
    directions before any real comparison is trusted.

    Returns:
        Problem descriptions; empty means the gate is sound.
    """
    problems: list[str] = []
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
    roots = {
        language: language_source_root(language) for language in sorted(SHARED_PARSER_CALL_SITES)
    }
    logger.info("scanned_targets targets=%s", sorted(roots))
    classifications = _load_classification()

    problems: list[str] = []
    problems.extend(check_reclassified_entries(classifications))
    problems.extend(check_closed_gap_status(classifications))
    problems.extend(check_both_private_copies_survive(roots))
    problems.extend(check_migration_column_carries_a_default(roots[_DEFAULT_BEARING_LANGUAGE]))
    problems.extend(check_shared_parser_reachability(roots))

    if problems:
        for problem in problems:
            logger.error("MIGRATION UPGRADE-OP FAMILY: %s", problem)
        return EXIT_FAIL
    logger.info(
        "MIGRATION UPGRADE-OP FAMILY GATE PASSED: %d reclassified symbol(s) still defined "
        "once per target across %s, %s has one home with %s call site(s).",
        len(RECLASSIFIED_SYMBOLS),
        sorted(roots),
        SHARED_SYMBOL,
        SHARED_PARSER_CALL_SITES,
    )
    return EXIT_OK


def _parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Migration upgrade-op family gate: the six reclassified upgrade-op builders "
            "keep one definition per target with mechanism 'none', and the one hoisted "
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
        1 = at least one violation, 2 = self-test failure or an unresolvable
        target/classification file.
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
