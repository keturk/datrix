"""Shared-vocabulary scanner and its ratchet."""

from __future__ import annotations

import ast
import enum
import importlib
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

# The provider-literal ratchet must enumerate provider ids from the
# installed datrix.platforms entry points, never a hardcoded
# "aws"/"azure"/"docker"/"local" literal: registered_platform_names() comes
# from the shared scripts package (datrix_scripts, on PYTHONPATH).
from datrix_scripts.gate_harness import NamedCheck, report_step
from import_boundaries._ast_common import (
    _SELF_TEST_SCRATCH_ROOT,
    CLI_SCRIPT,
    PackageInfo,
    _check,
    _self_test_write_manifest,
    self_test_check,
    tighten_only_messages,
    write_count_baseline,
)
from import_boundaries.taxonomy import LANGUAGES_ENTRY_POINT_GROUP

# ---------------------------------------------------------------------------
# G1 Shared-Vocabulary Ratchet (Decision D3, Invariant I2)
#
# Fails when a datrix-codegen-{lang} module declares a module-level
# frozenset/set/dict whose normalized member set equals a member set already
# declared in datrix_codegen_kernel.enums, OR in one of the additional
# non-enums.py canonical homes named in
# _ADDITIONAL_SHARED_VOCABULARY_SOURCES (a vocabulary moved out of enums.py
# for a layering reason, e.g. LOG_BUILTIN_METHODS). The LANGUAGE packages
# this ratchet polices are the discovered taxonomy's ``language_packages``
# (discover_generator_taxonomy), threaded in by main(), so a new language
# generator is policed from the commit that registers its entry point.


def _import_shared_enums_module() -> ModuleType:
    """Import and return ``datrix_codegen_kernel.enums``, the single module
    every G1 canonical-source harvest function (Enum and non-Enum alike)
    reads live at scan time -- never a hardcoded mirror of its content.

    Returns:
        The imported ``datrix_codegen_kernel.enums`` module object.

    Raises:
        RuntimeError: if the module cannot be imported (the shared
            vocabulary layer is not installed in the active venv).
    """
    try:
        from datrix_codegen_kernel import enums as shared_enums
    except ImportError as exc:
        raise RuntimeError(
            "Failed to import datrix_codegen_kernel.enums -- the G1 "
            "shared-vocabulary ratchet requires datrix-codegen-kernel "
            "installed in the active environment (D:\\datrix\\.venv). Fix: "
            "run this script via check-import-boundaries.ps1, which "
            "activates the venv first."
        ) from exc
    return shared_enums


def _shared_enum_members() -> dict[str, dict[str, str]]:
    """Every ``str, Enum`` class declared in ``datrix_codegen_kernel.enums``,
    keyed by class name, mapped to ``{member_name: member_value}``.

    Read from the INSTALLED package at scan time -- never a hardcoded mirror
    of enums.py's content -- so an Enum vocabulary added there later is
    picked up with zero edit to this scanner. This covers ONLY the ``str,
    Enum`` half of the canonical source; ``_shared_non_enum_vocabularies``
    covers the plain dict/set/frozenset half (Decision D3's DSL exception-
    status map, the NoSQL unsupported-method map, and the NoSQL
    supported-method set are deliberately not Enums -- see that function).

    Returns:
        Mapping of enum class name -> {member name -> member value}.

    Raises:
        RuntimeError: if datrix_codegen_kernel.enums cannot be imported (the
            shared vocabulary layer is not installed in the active venv).
    """
    shared_enums = _import_shared_enums_module()

    members: dict[str, dict[str, str]] = {}
    for name, candidate in vars(shared_enums).items():
        if (
            isinstance(candidate, type)
            and issubclass(candidate, enum.Enum)
            and candidate is not enum.Enum
        ):
            members[name] = {item.name: str(item.value) for item in candidate}
    return members


# AST call-target names recognized as wrapping a set/frozenset display when
# deciding whether a module-level assignment in enums.py is a container
# constant (see ``_is_module_level_container_assignment``).
_VOCABULARY_CONTAINER_CALL_NAMES: frozenset[str] = frozenset({"frozenset", "set"})

#: A vocabulary member as both sides spell it: a string, or an integer key such
#: as an HTTP status code (``bool`` is never one -- it is a flag, not a member).
VocabularyMember = str | int


def _is_vocabulary_member(value: object) -> bool:
    """True for a string or a non-``bool`` integer."""
    return isinstance(value, str) or (isinstance(value, int) and not isinstance(value, bool))


def _is_module_level_container_assignment(stmt: ast.stmt) -> str | None:
    """Return the assigned name if *stmt* is a module-level ``Assign``/
    ``AnnAssign`` to a single bare ``Name`` whose right-hand side is a dict
    display, a set display, or a ``frozenset(...)``/``set(...)`` call --
    else ``None``.

    This is a SHAPE test only (does this statement declare a container
    constant?), never a name test -- no vocabulary name is ever hardcoded
    here, so a new dict/set/frozenset constant added to ``enums.py`` later
    is picked up with zero edit to this scanner, mirroring
    ``_shared_enum_members``'s "read live, never mirrored" property for the
    Enum half. The RHS's own inner shape is deliberately not inspected any
    further here (a ``frozenset(...)`` call's argument may be a literal
    display or a generator expression -- both count as "container-shaped";
    the actual member VALUES always come from
    the live imported object in ``_non_enum_vocabulary_member_set``, never
    from re-parsing this argument).

    Args:
        stmt: A top-level statement from ``enums.py``'s module body.

    Returns:
        The assigned identifier, or ``None`` if *stmt* is not a qualifying
        module-level container assignment.
    """
    if isinstance(stmt, ast.Assign):
        if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
            return None
        name_node = stmt.targets[0]
        value_node = stmt.value
    elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
        if not isinstance(stmt.target, ast.Name):
            return None
        name_node = stmt.target
        value_node = stmt.value
    else:
        return None

    if isinstance(value_node, (ast.Dict, ast.Set)):
        return name_node.id
    if (
        isinstance(value_node, ast.Call)
        and isinstance(value_node.func, ast.Name)
        and value_node.func.id in _VOCABULARY_CONTAINER_CALL_NAMES
    ):
        return name_node.id
    return None


def _non_enum_vocabulary_member_set(
    name: str, runtime_value: object
) -> frozenset[VocabularyMember]:
    """Resolve *runtime_value* (the live object bound to *name* in the
    imported ``enums.py``) to its canonical member-value set.

    A ``dict``'s canonical member set is its KEYS -- that is what a
    redeclaring copy duplicates (e.g. ``DSL_EXCEPTION_HTTP_STATUS``'s keys,
    never its status-code values; ``DSL_EXCEPTION_DEFAULT_DETAIL``'s
    integer status-code keys). A ``set``/``frozenset``'s canonical member
    set is its elements directly.

    Args:
        name: The module-level identifier this value is bound to (for error
            messages only).
        runtime_value: The actual object ``getattr(enums_module, name)``.

    Returns:
        The frozenset of canonical members (strings or integers).

    Raises:
        TypeError: if *runtime_value* is not a dict/set/frozenset, or any of
            its keys/elements is neither a string nor an integer. A canonical declaration whose
            members cannot be determined must fail loudly here, never be
            silently skipped -- a silently-skipped canonical source is the
            exact coverage gap this harvest exists to close.
    """
    if isinstance(runtime_value, dict):
        candidate_members = runtime_value.keys()
        shape = "dict keys"
    elif isinstance(runtime_value, (frozenset, set)):
        candidate_members = runtime_value
        shape = "set/frozenset elements"
    else:
        raise TypeError(
            f"G1 harvest: '{name}' in datrix_codegen_kernel.enums has a "
            f"module-level dict/set/frozenset assignment shape but its live "
            f"value is a {type(runtime_value).__name__}, not a dict/set/"
            f"frozenset. Expected the runtime type to match the declared "
            f"shape. Fix: keep '{name}' bound to a dict/set/frozenset, or "
            f"restructure it so it is no longer a bare module-level "
            f"assignment (e.g. move it behind a function)."
        )

    members: set[VocabularyMember] = set()
    for element in candidate_members:
        if not _is_vocabulary_member(element):
            raise TypeError(
                f"G1 harvest: '{name}' in datrix_codegen_kernel.enums has a "
                f"member ({element!r}, type {type(element).__name__}) among "
                f"its {shape} that is neither a str nor an int. Expected "
                f"every member to be a str or an int so it can be compared "
                f"against a redeclaring copy's literals. Fix: make '{name}' "
                f"string- or integer-keyed/valued, or valid options are to "
                f"exclude it from module-level container declarations in "
                f"enums.py."
            )
        members.add(element)
    return frozenset(members)


# Declared homes for a canonical shared vocabulary that lives OUTSIDE
# enums.py. Each entry is (dotted module path, attribute name). This exists
# only for a vocabulary that was deliberately MOVED out of enums.py because
# its derivation is shaped like the layer it lives beside (e.g.
# LOG_BUILTIN_METHODS is `frozenset(method for category, method in
# BUILTIN_REGISTRY if category == "Log")`, and enums.py -- the
# target-neutral vocabulary module -- must not import the transpiler to
# compute it; see datrix_codegen_common/transpiler/builtin_registry.py).
#
# This is deliberately NOT a general "scan every container in this module"
# rule the way `_shared_non_enum_vocabularies` scans enums.py: a home module
# outside enums.py may also declare module-level containers whose members
# are not strings (e.g. builtin_registry.py's `UI_BUILTIN_GROUPS`, a
# frozenset of `BuiltinGroup` enum members, and `BUILTIN_REGISTRY`, a dict
# keyed by `(category, method)` tuples) -- `_non_enum_vocabulary_member_set`
# correctly raises TypeError on those, so scanning the whole module would
# break the ratchet on every run instead of harvesting the one vocabulary
# that was actually moved there. Naming the exact attribute keeps the
# harvest working without hardcoding a mirror of the moved value, and the
# `hasattr` check below fails loud (not silently) the moment the declared
# attribute is renamed or removed, so this list cannot go silently stale.
_ADDITIONAL_SHARED_VOCABULARY_SOURCES: tuple[tuple[str, str], ...] = (
    ("datrix_codegen_common.transpiler.builtin_registry", "LOG_BUILTIN_METHODS"),
)


def _additional_shared_non_enum_vocabularies() -> dict[str, frozenset[VocabularyMember]]:
    """Canonical member sets for the shared vocabularies declared in
    ``_ADDITIONAL_SHARED_VOCABULARY_SOURCES`` -- vocabulary homes outside
    ``enums.py`` that hold a canonical set moved there for a layering
    reason.

    Returns:
        Mapping of attribute name -> canonical member-value set, one entry
        per declared source.

    Raises:
        RuntimeError: if a declared module cannot be imported, or if a
            declared attribute is missing from the imported module (the
            declared home has gone stale -- renamed, removed, or moved
            again without updating this list).
        TypeError: if a declared attribute's members cannot be determined
            as strings (propagated from ``_non_enum_vocabulary_member_set``).
    """
    vocabularies: dict[str, frozenset[VocabularyMember]] = {}
    for module_path, attr_name in _ADDITIONAL_SHARED_VOCABULARY_SOURCES:
        try:
            module = importlib.import_module(module_path)
        except ImportError as exc:
            raise RuntimeError(
                f"G1 harvest: failed to import declared shared-vocabulary "
                f"home '{module_path}' (for attribute '{attr_name}') -- is "
                f"the package that provides it installed in the active "
                f"environment (D:\\datrix\\.venv)? Fix: run this script via "
                f"check-import-boundaries.ps1, which activates the venv "
                f"first, or correct the module path in "
                f"_ADDITIONAL_SHARED_VOCABULARY_SOURCES if the module moved."
            ) from exc
        if not hasattr(module, attr_name):
            raise RuntimeError(
                f"G1 harvest: declared shared-vocabulary home "
                f"'{module_path}.{attr_name}' is missing -- '{attr_name}' "
                f"is not an attribute of the imported '{module_path}' "
                f"module. Expected _ADDITIONAL_SHARED_VOCABULARY_SOURCES "
                f"and the installed package to agree. Fix: reinstall the "
                f"owning package in the active environment, or if "
                f"'{attr_name}' was renamed or moved again, update "
                f"_ADDITIONAL_SHARED_VOCABULARY_SOURCES in "
                f"check_import_boundaries.py to match -- never drop the "
                f"entry, or this vocabulary silently stops being policed."
            )
        runtime_value = getattr(module, attr_name)
        vocabularies[attr_name] = _non_enum_vocabulary_member_set(attr_name, runtime_value)
    return vocabularies


def _shared_non_enum_vocabularies() -> dict[str, frozenset[VocabularyMember]]:
    """Every module-level ``dict``/``set``/``frozenset`` constant DECLARED IN
    ``enums.py``'s own source (never an imported symbol merely visible
    through it, e.g. ``BUILTIN_REGISTRY``) that is not a ``str, Enum`` class,
    mapped to its canonical member-value set -- merged with the additional
    declared homes in ``_ADDITIONAL_SHARED_VOCABULARY_SOURCES`` (canonical
    vocabularies that were moved out of enums.py; see that constant).

    Covers value-derived declarations the AST cannot evaluate on its own --
    e.g. a ``frozenset(<generator expression>)`` derived from another
    table, not a literal display. The AST is used ONLY to decide WHICH names are
    container-shaped constants (``_is_module_level_container_assignment``);
    the member set always comes from the live imported object, which
    already carries the fully-derived value regardless of how it was
    computed.

    No vocabulary name is ever hardcoded for the enums.py half: a dict/set/
    frozenset constant added to ``enums.py`` later is harvested with zero
    edit here, the same generality property ``_shared_enum_members`` already
    has for the Enum half (Decision D3, Invariant I2; design principle 16 --
    shared layers ask, target plugins answer). Only a vocabulary that no
    longer lives in enums.py needs an entry in
    ``_ADDITIONAL_SHARED_VOCABULARY_SOURCES``.

    Returns:
        Mapping of module-level constant name -> canonical member-value set.

    Raises:
        RuntimeError: if datrix_codegen_kernel.enums cannot be imported, if
            a name the AST identifies as a module-level assignment is
            missing from the imported module (source/installed-package
            mismatch), or if a declared additional home is missing or
            unimportable (propagated from
            ``_additional_shared_non_enum_vocabularies``).
        TypeError: if a qualifying container's members cannot be determined
            as strings (propagated from ``_non_enum_vocabulary_member_set``).
    """
    shared_enums = _import_shared_enums_module()
    source_path = Path(shared_enums.__file__)
    source_code = source_path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source_code, filename=str(source_path))

    vocabularies: dict[str, frozenset[VocabularyMember]] = {}
    for stmt in tree.body:
        name = _is_module_level_container_assignment(stmt)
        if name is None:
            continue
        if not hasattr(shared_enums, name):
            raise RuntimeError(
                f"G1 harvest: '{name}' is assigned at module level in "
                f"{source_path} but is not an attribute of the imported "
                f"datrix_codegen_kernel.enums module. Expected the source "
                f"file and the installed package to agree. Fix: reinstall "
                f"datrix-codegen-kernel in the active environment (D:\\"
                f"datrix\\.venv)."
            )
        runtime_value = getattr(shared_enums, name)
        vocabularies[name] = _non_enum_vocabulary_member_set(name, runtime_value)

    vocabularies.update(_additional_shared_non_enum_vocabularies())
    return vocabularies


@dataclass(frozen=True)
class SharedVocabularyHit:
    """One module-level container in a language package whose normalized
    member set duplicates a datrix_codegen_kernel.enums vocabulary -- an
    Enum class's value set or a plain module-level dict/set/frozenset's
    key/element set alike."""

    file_path: Path
    line_number: int
    container_name: str
    matched_vocabulary: str


def _resolve_vocabulary_element(
    node: ast.AST, enum_members: dict[str, dict[str, str]]
) -> tuple[VocabularyMember, bool] | None:
    """Resolve one set/frozenset/dict-key element to ``(value, is_bare)``.

    ``is_bare`` is True for a plain string or integer constant (``"all"``,
    ``401``), False for a
    qualified enum-member reference (``QueryTerminal.ALL``) resolved through
    *enum_members* to the member's real value (``"all"``) -- both forms
    compare equal once resolved, but only the bare form counts toward
    "hardcodes the literal" (see ``_normalize_container`` docstring).

    Returns:
        ``None`` for any other node shape (a Name, an f-string, a call, an
        ``EnumClass.MEMBER`` pair the enum does not actually declare, ...) --
        such an element means the container is not a closed vocabulary
        literal at all, and the caller skips it entirely.
    """
    if isinstance(node, ast.Constant) and _is_vocabulary_member(node.value):
        return node.value, True
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        member_map = enum_members.get(node.value.id)
        if member_map is not None and node.attr in member_map:
            return member_map[node.attr], False
    return None


@dataclass(frozen=True)
class _NormalizedContainer:
    """A module-level container literal, resolved to its member value set."""

    values: frozenset[VocabularyMember]
    has_bare_literal: bool


def _normalize_container(
    node: ast.AST, enum_members: dict[str, dict[str, str]]
) -> _NormalizedContainer | None:
    """Normalize a module-level ``frozenset(...)``/``set(...)``/``{...}``/
    dict-literal RHS to its member value set, resolving both bare string
    literals and qualified ``EnumClass.MEMBER`` references to the same
    underlying strings so the two forms compare equal (see
    ``_resolve_vocabulary_element``).

    Returns:
        ``None`` if *node* is not a recognized set/frozenset/dict literal,
        has zero elements, or contains any element that is not a bare string
        or integer or a resolvable qualified enum-member reference -- an unrecognized
        element means "not provably a closed vocabulary literal", not
        "clean"; the caller simply cannot compare a partially-unresolvable
        container against a specific enum's exact member set.
    """
    elements: list[ast.AST]
    if isinstance(node, ast.Call):
        func = node.func
        if not (isinstance(func, ast.Name) and func.id in ("frozenset", "set")):
            return None
        if len(node.args) != 1 or not isinstance(
            node.args[0], (ast.Set, ast.List, ast.Tuple)
        ):
            return None
        elements = list(node.args[0].elts)
    elif isinstance(node, ast.Set):
        elements = list(node.elts)
    elif isinstance(node, ast.Dict):
        if any(key is None for key in node.keys):
            return None  # a **spread entry -- not a closed literal
        elements = [key for key in node.keys if key is not None]
    else:
        return None

    if not elements:
        return None

    values: set[VocabularyMember] = set()
    has_bare_literal = False
    for element in elements:
        resolved = _resolve_vocabulary_element(element, enum_members)
        if resolved is None:
            return None
        value, is_bare = resolved
        values.add(value)
        has_bare_literal = has_bare_literal or is_bare

    return _NormalizedContainer(
        values=frozenset(values), has_bare_literal=has_bare_literal
    )


def scan_file_for_shared_vocabulary(
    file_path: Path,
    enum_members: dict[str, dict[str, str]],
    non_enum_vocabularies: dict[str, frozenset[VocabularyMember]],
) -> list[SharedVocabularyHit]:
    """AST-walk *file_path* for module-level set/frozenset/dict declarations
    whose normalized member set equals a ``datrix_codegen_kernel.enums``
    vocabulary's own value set (Decision D3, Invariant I2) -- an Enum
    class's value set, or a plain module-level dict's key set / set's
    frozenset's element set (``non_enum_vocabularies``) alike. G1's own
    specification never restricts the canonical side to Enum classes; a
    name -> value lookup table like ``DSL_EXCEPTION_HTTP_STATUS`` or a
    member set like ``NOSQL_SUPPORTED_METHODS`` is exactly as canonical as
    ``HTTPMethod``, and a bare-literal redeclaration of either is the same
    defect.

    A hit requires TWO conditions: the normalized member set exactly equals
    some enum class's value set, AND the container includes at least one
    BARE STRING OR INTEGER LITERAL element. A container built ENTIRELY from qualified
    enum-member references (e.g. ``frozenset({QueryTerminal.ALL,
    QueryTerminal.FIRST, QueryTerminal.FIRST_OR_FAIL, QueryTerminal.COUNT})``,
    the real, already-compliant case at
    ``datrix-codegen-python/.../_transpiler_query_builder.py:19-24``) is
    CONSUMING the enum, not hardcoding it, and must not be flagged -- only a
    container containing at least one hand-spelled string is "the DSL
    vocabulary re-scattered after being centralised" (design doc S2.3).

    Only module-level (top-of-file) ``Assign``/``AnnAssign`` statements are
    scanned -- a set built inside a function body is a local computation,
    never a closed-world vocabulary table.

    Args:
        file_path: Path to Python source file.
        enum_members: Output of ``_shared_enum_members()``.
        non_enum_vocabularies: Output of ``_shared_non_enum_vocabularies()``.

    Returns:
        List of hits found in the file, in source order.

    Raises:
        SyntaxError: propagated from ast.parse (caller decides how to report).
        OSError: propagated if the file cannot be read.
    """
    source_code = file_path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source_code, filename=str(file_path))

    canonical_value_sets: dict[str, frozenset[VocabularyMember]] = {
        class_name: frozenset(values.values())
        for class_name, values in enum_members.items()
    }
    canonical_value_sets.update(non_enum_vocabularies)

    hits: list[SharedVocabularyHit] = []
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign):
            targets = stmt.targets
            value_node = stmt.value
        elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
            targets = [stmt.target]
            value_node = stmt.value
        else:
            continue

        normalized = _normalize_container(value_node, enum_members)
        if normalized is None or not normalized.has_bare_literal:
            continue

        matched_vocabulary = next(
            (
                vocabulary_name
                for vocabulary_name, value_set in canonical_value_sets.items()
                if value_set == normalized.values
            ),
            None,
        )
        if matched_vocabulary is None:
            continue

        container_name = ", ".join(
            target.id for target in targets if isinstance(target, ast.Name)
        )
        hits.append(
            SharedVocabularyHit(
                file_path=file_path,
                line_number=stmt.lineno,
                container_name=container_name or "<unknown>",
                matched_vocabulary=matched_vocabulary,
            )
        )

    return hits


def scan_shared_vocabulary(
    packages: dict[str, PackageInfo],
    monorepo_root: Path,
    language_packages: tuple[str, ...],
) -> dict[Path, list[SharedVocabularyHit]]:
    """Scan every ``.py`` file under each language package's ``src/`` tree
    for module-level vocabulary duplication against
    ``datrix_codegen_kernel.enums``.

    Args:
        packages: Package name -> PackageInfo, as returned by discover_packages().
        monorepo_root: Monorepo root for relative path reporting.
        language_packages: The discovered taxonomy's language packages
            (``GeneratorTaxonomy.language_packages``).

    Returns:
        Mapping of file path -> hits in that file (files with zero hits omitted).
    """
    results: dict[Path, list[SharedVocabularyHit]] = {}
    enum_members = _shared_enum_members()
    non_enum_vocabularies = _shared_non_enum_vocabularies()

    for package_name in language_packages:
        package_info = packages.get(package_name)
        if package_info is None:
            continue

        for py_file in package_info.src_dir.rglob("*.py"):
            try:
                hits = scan_file_for_shared_vocabulary(
                    py_file, enum_members, non_enum_vocabularies
                )
            except SyntaxError as e:
                rel_path = py_file.relative_to(monorepo_root)
                print(
                    f"ERROR: Failed to parse {rel_path}:{e.lineno} - {e.msg}. "
                    f"A policed file that cannot be parsed would escape this scan "
                    f"(a silent blind spot); fix its syntax or encoding.",
                    file=sys.stderr,
                )
                sys.exit(2)
            except (OSError, UnicodeDecodeError) as e:
                rel_path = py_file.relative_to(monorepo_root)
                print(
                    f"ERROR: Failed to read {rel_path} - {e}. A policed file that "
                    f"cannot be read would escape this scan; resolve the read error.",
                    file=sys.stderr,
                )
                sys.exit(2)

            if hits:
                results[py_file] = hits

    return results


_SHARED_VOCABULARY_BASELINE_HEADER = (
    "# G1 Shared-Vocabulary Ratchet Baseline (Decision D3, Invariant I2)\n"
    "#\n"
    "# Frozen per-file counts of module-level frozenset/set/dict\n"
    "# declarations in the four datrix-codegen-{lang} packages whose\n"
    "# normalized member set duplicates a datrix_codegen_kernel.enums\n"
    "# vocabulary. Any INCREASE in a file's count fails\n"
    "# datrix/scripts/scan/check-import-boundaries.ps1 --check-shared-vocabulary.\n"
    "# Decreases are always allowed and should be captured by re-running\n"
    "# with --update-baseline once a later change deletes a redundant\n"
    "# container (the terminal state is 0 for every entry here).\n"
    "#\n"
    "# Format:\n"
    "#   [[baseline]]\n"
    '#   file = "path/relative/to/monorepo-root, forward slashes"\n'
    "#   count = <int>\n"
)


def write_shared_vocabulary_baseline(baseline_path: Path, counts: dict[str, int]) -> None:
    """Write ``counts`` to the shared-vocabulary baseline TOML as
    ``[[baseline]] file=... count=...`` entries, sorted by file for
    deterministic diffs.

    Args:
        baseline_path: Path to the shared-vocabulary baseline TOML file to write.
        counts: Mapping of relative file path (forward slashes) -> hit count.
    """
    write_count_baseline(
        baseline_path, counts, key_field="file", header=_SHARED_VOCABULARY_BASELINE_HEADER
    )


def check_shared_vocabulary_ratchet(
    current_counts: dict[str, int],
    baseline: dict[str, int],
) -> list[str]:
    """One message per file whose shared-vocabulary count rose above its
    baseline, sorted by file path."""
    return tighten_only_messages(current_counts, baseline, "shared-vocabulary")


def _self_test_shared_vocabulary_scanner() -> bool:
    """scan_file_for_shared_vocabulary detects a bare-literal redeclaration
    of a known enum's member set, does NOT flag a container built entirely
    from qualified enum-member references, and does NOT flag an unrelated
    container whose members don't match any known vocabulary -- PLUS (added
    when the canonical-source harvest was widened past ``str, Enum``
    classes) the non-Enum harvest actually contains the three enums.py-
    declared dict/frozenset canonical vocabularies plus one vocabulary
    declared OUTSIDE enums.py (``LOG_BUILTIN_METHODS``, harvested via
    ``_ADDITIONAL_SHARED_VOCABULARY_SOURCES``), a harvest restricted to Enum
    classes alone would have missed every one of them, and each non-Enum
    shape's bare-literal redeclaration is detected while its importing form
    is not."""
    report_step(
        "Self-test 13/24: shared-vocabulary scanner (detection + exemption "
        "non-vacuity, Enum and non-Enum canonical sources alike)"
    )
    ok = True

    enum_members = {
        "QueryTerminal": {
            "ALL": "all",
            "FIRST": "first",
            "FIRST_OR_FAIL": "firstOrFail",
            "COUNT": "count",
        },
    }

    scratch_dir = _SELF_TEST_SCRATCH_ROOT / f"shared-vocab-scanner-{uuid.uuid4().hex}"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    try:
        bare_literal_file = scratch_dir / "bare_literal.py"
        bare_literal_file.write_text(
            '_TERMINAL_METHODS = frozenset({"all", "first", "firstOrFail", "count"})\n',
            encoding="utf-8",
        )
        bare_hits = scan_file_for_shared_vocabulary(bare_literal_file, enum_members, {})
        ok &= _check(
            "bare-string redeclaration of QueryTerminal's four members is flagged",
            len(bare_hits) == 1 and bare_hits[0].matched_vocabulary == "QueryTerminal",
        )

        qualified_only_file = scratch_dir / "qualified_only.py"
        qualified_only_file.write_text(
            "from datrix_codegen_kernel.enums import QueryTerminal\n\n"
            "_QB_EXECUTE_TERMINALS = frozenset({\n"
            "    QueryTerminal.ALL,\n"
            "    QueryTerminal.FIRST,\n"
            "    QueryTerminal.FIRST_OR_FAIL,\n"
            "    QueryTerminal.COUNT,\n"
            "})\n",
            encoding="utf-8",
        )
        qualified_hits = scan_file_for_shared_vocabulary(
            qualified_only_file, enum_members, {}
        )
        ok &= _check(
            "a container built entirely from qualified QueryTerminal.X references is NOT flagged",
            qualified_hits == [],
        )

        unrelated_file = scratch_dir / "unrelated.py"
        unrelated_file.write_text(
            '_HTTP_STATUS_CATEGORIES = frozenset({"informational", "success", "error"})\n',
            encoding="utf-8",
        )
        unrelated_hits = scan_file_for_shared_vocabulary(unrelated_file, enum_members, {})
        ok &= _check(
            "an unrelated container matching no known vocabulary is NOT flagged",
            unrelated_hits == [],
        )

        # --- Non-Enum canonical-source harvest completeness -----------------
        # A harvest restricted to `str, Enum` classes (the pre-widening
        # behaviour) is what `_shared_enum_members()` alone still returns;
        # proving these three names are ABSENT from it, while the widened
        # `_shared_non_enum_vocabularies()` DOES contain them, is the direct
        # proof that an Enum-only harvest would FAIL to cover them.
        from datrix_codegen_kernel.enums import (
            DSL_EXCEPTION_DEFAULT_DETAIL,
            DSL_EXCEPTION_HTTP_STATUS,
            NOSQL_SUPPORTED_METHODS,
            NOSQL_UNSUPPORTED_METHODS,
        )

        enum_only_harvest = _shared_enum_members()
        non_enum_harvest = _shared_non_enum_vocabularies()
        for vocabulary_name in (
            "DSL_EXCEPTION_HTTP_STATUS",
            "NOSQL_UNSUPPORTED_METHODS",
            "NOSQL_SUPPORTED_METHODS",
        ):
            ok &= _check(
                f"a str,Enum-only harvest does not contain {vocabulary_name} "
                f"(proves an Enum-only harvest FAILS to cover a non-Enum "
                f"canonical source)",
                vocabulary_name not in enum_only_harvest,
            )
        ok &= _check(
            "the widened harvest contains DSL_EXCEPTION_HTTP_STATUS's keys",
            non_enum_harvest.get("DSL_EXCEPTION_HTTP_STATUS")
            == frozenset(DSL_EXCEPTION_HTTP_STATUS.keys()),
        )
        ok &= _check(
            "the widened harvest contains NOSQL_UNSUPPORTED_METHODS's keys",
            non_enum_harvest.get("NOSQL_UNSUPPORTED_METHODS")
            == frozenset(NOSQL_UNSUPPORTED_METHODS.keys()),
        )
        ok &= _check(
            "the widened harvest contains NOSQL_SUPPORTED_METHODS's members",
            non_enum_harvest.get("NOSQL_SUPPORTED_METHODS")
            == frozenset(NOSQL_SUPPORTED_METHODS),
        )

        # --- Container-shape detection: a value-DERIVED frozenset ------------
        # enums.py declares no generator-expression-derived constant today,
        # so a synthetic module proves the AST shape test still counts a
        # ``frozenset(<genexpr>)`` assignment (plain and annotated) as a
        # container constant, and still rejects a non-container call.
        derived_shape_source = (
            "_ROWS = (('Log', 'info'), ('Log', 'warn'), ('Http', 'get'))\n"
            "DERIVED_PLAIN = frozenset(m for c, m in _ROWS if c == 'Log')\n"
            "DERIVED_ANNOTATED: frozenset[str] = frozenset(m for c, m in _ROWS)\n"
            "NOT_A_CONTAINER = sorted(m for c, m in _ROWS)\n"
        )
        derived_shape_names = [
            _is_module_level_container_assignment(stmt)
            for stmt in ast.parse(derived_shape_source).body
        ]
        ok &= _check(
            "a frozenset(<generator expression>) assignment is container-shaped, "
            "plain and annotated alike, while a non-container call is not",
            derived_shape_names == [None, "DERIVED_PLAIN", "DERIVED_ANNOTATED", None],
        )

        # --- Non-Enum shape 1: dict-keys (DSL_EXCEPTION_HTTP_STATUS) --------
        dict_shape_bare_file = scratch_dir / "dict_shape_bare.py"
        dict_shape_bare_file.write_text(
            f"_EXCEPTION_STATUS_MAP = {DSL_EXCEPTION_HTTP_STATUS!r}\n",
            encoding="utf-8",
        )
        dict_shape_bare_hits = scan_file_for_shared_vocabulary(
            dict_shape_bare_file, {}, non_enum_harvest
        )
        ok &= _check(
            "a bare dict literal redeclaring DSL_EXCEPTION_HTTP_STATUS's keys is flagged",
            len(dict_shape_bare_hits) == 1
            and dict_shape_bare_hits[0].matched_vocabulary
            == "DSL_EXCEPTION_HTTP_STATUS",
        )

        dict_shape_importing_file = scratch_dir / "dict_shape_importing.py"
        dict_shape_importing_file.write_text(
            "from datrix_codegen_kernel.enums import DSL_EXCEPTION_HTTP_STATUS\n\n"
            "def status_for(exc_name: str) -> int:\n"
            "    return DSL_EXCEPTION_HTTP_STATUS[exc_name]\n",
            encoding="utf-8",
        )
        dict_shape_importing_hits = scan_file_for_shared_vocabulary(
            dict_shape_importing_file, {}, non_enum_harvest
        )
        ok &= _check(
            "importing DSL_EXCEPTION_HTTP_STATUS instead of redeclaring it is NOT flagged",
            dict_shape_importing_hits == [],
        )

        # --- Integer-keyed dict (DSL_EXCEPTION_DEFAULT_DETAIL) --------------
        ok &= _check(
            "the harvest holds DSL_EXCEPTION_DEFAULT_DETAIL's integer status-code keys",
            non_enum_harvest.get("DSL_EXCEPTION_DEFAULT_DETAIL")
            == frozenset(DSL_EXCEPTION_DEFAULT_DETAIL.keys()),
        )
        int_shape_file = scratch_dir / "int_shape.py"
        int_shape_file.write_text(
            f"_DEFAULT_DETAIL = {DSL_EXCEPTION_DEFAULT_DETAIL!r}\n"
            "_FLAGS = {True: 'on', False: 'off'}\n",
            encoding="utf-8",
        )
        int_shape_hits = scan_file_for_shared_vocabulary(int_shape_file, {}, non_enum_harvest)
        ok &= _check(
            "a bare dict literal redeclaring DSL_EXCEPTION_DEFAULT_DETAIL's integer "
            "keys is flagged; a bool-keyed dict is no vocabulary",
            [hit.matched_vocabulary for hit in int_shape_hits]
            == ["DSL_EXCEPTION_DEFAULT_DETAIL"],
        )

        # --- Non-Enum shape 2: dict-keys (NOSQL_UNSUPPORTED_METHODS) --------
        second_dict_shape_bare_file = scratch_dir / "second_dict_shape_bare.py"
        second_dict_shape_bare_file.write_text(
            f"_NOSQL_UNSUPPORTED = {NOSQL_UNSUPPORTED_METHODS!r}\n",
            encoding="utf-8",
        )
        second_dict_shape_bare_hits = scan_file_for_shared_vocabulary(
            second_dict_shape_bare_file, {}, non_enum_harvest
        )
        ok &= _check(
            "a bare dict literal redeclaring NOSQL_UNSUPPORTED_METHODS's keys is flagged",
            len(second_dict_shape_bare_hits) == 1
            and second_dict_shape_bare_hits[0].matched_vocabulary
            == "NOSQL_UNSUPPORTED_METHODS",
        )

        second_dict_shape_importing_file = scratch_dir / "second_dict_shape_importing.py"
        second_dict_shape_importing_file.write_text(
            "from datrix_codegen_kernel.enums import NOSQL_UNSUPPORTED_METHODS\n\n"
            "def reason_for(method: str) -> str:\n"
            "    return NOSQL_UNSUPPORTED_METHODS[method]\n",
            encoding="utf-8",
        )
        second_dict_shape_importing_hits = scan_file_for_shared_vocabulary(
            second_dict_shape_importing_file, {}, non_enum_harvest
        )
        ok &= _check(
            "importing NOSQL_UNSUPPORTED_METHODS instead of redeclaring it is NOT flagged",
            second_dict_shape_importing_hits == [],
        )

        # --- Non-Enum shape 3: frozenset elements (NOSQL_SUPPORTED_METHODS) -
        frozenset_shape_bare_file = scratch_dir / "frozenset_shape_bare.py"
        frozenset_shape_bare_file.write_text(
            f"_NOSQL_SUPPORTED = {frozenset(NOSQL_SUPPORTED_METHODS)!r}\n",
            encoding="utf-8",
        )
        frozenset_shape_bare_hits = scan_file_for_shared_vocabulary(
            frozenset_shape_bare_file, {}, non_enum_harvest
        )
        ok &= _check(
            "a bare frozenset literal redeclaring NOSQL_SUPPORTED_METHODS's members is flagged",
            len(frozenset_shape_bare_hits) == 1
            and frozenset_shape_bare_hits[0].matched_vocabulary == "NOSQL_SUPPORTED_METHODS",
        )

        frozenset_shape_importing_file = scratch_dir / "frozenset_shape_importing.py"
        frozenset_shape_importing_file.write_text(
            "from datrix_codegen_kernel.enums import NOSQL_SUPPORTED_METHODS\n\n"
            "def is_nosql_supported(method: str) -> bool:\n"
            "    return method in NOSQL_SUPPORTED_METHODS\n",
            encoding="utf-8",
        )
        frozenset_shape_importing_hits = scan_file_for_shared_vocabulary(
            frozenset_shape_importing_file, {}, non_enum_harvest
        )
        ok &= _check(
            "importing NOSQL_SUPPORTED_METHODS instead of redeclaring it is NOT flagged",
            frozenset_shape_importing_hits == [],
        )

        # --- Non-Enum shape 4: a vocabulary moved OUT of enums.py -----------
        # LOG_BUILTIN_METHODS used to live in enums.py; it now lives in
        # datrix_codegen_common.transpiler.builtin_registry (a kernel-closure
        # cut: enums.py must not import the transpiler). Proves
        # _ADDITIONAL_SHARED_VOCABULARY_SOURCES actually harvests a moved
        # declaration -- without this, a language package that hand-copies
        # the Log builtin method set would go unflagged (the exact coverage
        # gap this list exists to close).
        from datrix_codegen_common.transpiler.builtin_registry import LOG_BUILTIN_METHODS
        from datrix_codegen_kernel import enums as shared_enums_module

        ok &= _check(
            "LOG_BUILTIN_METHODS is not an attribute of enums.py itself "
            "(proves it truly moved out, so its harvest coverage can only "
            "come from _ADDITIONAL_SHARED_VOCABULARY_SOURCES, not from the "
            "enums.py AST scan)",
            not hasattr(shared_enums_module, "LOG_BUILTIN_METHODS"),
        )
        ok &= _check(
            "the widened harvest contains LOG_BUILTIN_METHODS's members even "
            "though it is declared outside enums.py",
            non_enum_harvest.get("LOG_BUILTIN_METHODS") == frozenset(LOG_BUILTIN_METHODS),
        )

        moved_shape_bare_file = scratch_dir / "moved_shape_bare.py"
        moved_shape_bare_file.write_text(
            f"_LOG_METHODS = {frozenset(LOG_BUILTIN_METHODS)!r}\n",
            encoding="utf-8",
        )
        moved_shape_bare_hits = scan_file_for_shared_vocabulary(
            moved_shape_bare_file, {}, non_enum_harvest
        )
        ok &= _check(
            "a language package hand-copying LOG_BUILTIN_METHODS's members "
            "as a bare frozenset literal is flagged even though the "
            "canonical source moved out of enums.py",
            len(moved_shape_bare_hits) == 1
            and moved_shape_bare_hits[0].matched_vocabulary == "LOG_BUILTIN_METHODS",
        )

        moved_shape_importing_file = scratch_dir / "moved_shape_importing.py"
        moved_shape_importing_file.write_text(
            "from datrix_codegen_common.transpiler.builtin_registry import (\n"
            "    LOG_BUILTIN_METHODS,\n"
            ")\n\n"
            "def is_log_method(method: str) -> bool:\n"
            "    return method in LOG_BUILTIN_METHODS\n",
            encoding="utf-8",
        )
        moved_shape_importing_hits = scan_file_for_shared_vocabulary(
            moved_shape_importing_file, {}, non_enum_harvest
        )
        ok &= _check(
            "importing LOG_BUILTIN_METHODS from its moved home instead of "
            "redeclaring it is NOT flagged",
            moved_shape_importing_hits == [],
        )
    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)

    return ok


def _self_test_shared_vocabulary_build_fixture_monorepo(tmp_root: Path) -> Path:
    """Build a minimal isolated monorepo: one datrix-codegen-python package
    (a LANGUAGE package by its manifest's ``datrix.languages`` entry point)
    whose module IMPORTS QueryTerminal (clean, no local redeclaration), plus
    a baseline TOML freezing that file at count 0."""
    _self_test_write_manifest(
        tmp_root, "datrix-codegen-python", "datrix_codegen_python",
        entry_point_groups={LANGUAGES_ENTRY_POINT_GROUP: {"python": "PythonLanguagePlugin"}},
    )
    package_src = tmp_root / "datrix-codegen-python" / "src" / "datrix_codegen_python"
    package_src.mkdir(parents=True, exist_ok=True)
    (package_src / "__init__.py").write_text("", encoding="utf-8")

    module_path = package_src / "sample_query_chain.py"
    module_path.write_text(
        "from datrix_codegen_kernel.enums import QueryTerminal\n\n"
        "def is_terminal(method: str) -> bool:\n"
        "    return method in {t.value for t in QueryTerminal}\n",
        encoding="utf-8",
    )

    config_dir = tmp_root / "datrix" / "scripts" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "shared-vocabulary-baseline.toml").write_text(
        "[[baseline]]\n"
        'file = "datrix-codegen-python/src/datrix_codegen_python/sample_query_chain.py"\n'
        "count = 0\n",
        encoding="utf-8",
    )
    return module_path


def _self_test_shared_vocabulary_run_cli(tmp_root: Path) -> subprocess.CompletedProcess[str]:
    """Invoke THIS script as a real subprocess against the isolated fixture."""
    return subprocess.run(
        [
            sys.executable,
            str(CLI_SCRIPT),
            "--base-dir",
            str(tmp_root),
            "--check-shared-vocabulary",
            "--skip-auto-self-test",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _self_test_shared_vocabulary_non_enum_cli_cycle(
    tmp_root: Path,
    module_path: Path,
    clean_source: str,
    *,
    vocabulary_name: str,
    container_name: str,
    literal_source: str,
) -> bool:
    """Run one mutate -> detect -> revert -> clear CLI round-trip for a
    single non-Enum canonical vocabulary against the already-clean fixture
    at *module_path*, restoring *clean_source* before returning either way.

    Args:
        tmp_root: The isolated fixture monorepo root (for CLI invocation).
        module_path: The fixture module file to mutate in place.
        clean_source: The known-clean source to append to / restore.
        vocabulary_name: The canonical vocabulary this cycle redeclares
            (for assertion messages only).
        container_name: The bare container's assigned name in the planted
            source line (e.g. ``_EXCEPTION_STATUS_MAP``).
        literal_source: The full ``name = <literal>`` statement to append.

    Returns:
        True iff every assertion in this cycle passed.
    """
    ok = True
    module_path.write_text(clean_source + "\n" + literal_source, encoding="utf-8")
    failing_result = _self_test_shared_vocabulary_run_cli(tmp_root)
    ok &= _check(
        f"redeclaring {vocabulary_name} as a bare {container_name} literal "
        f"exits 1, got {failing_result.returncode}",
        failing_result.returncode == 1,
    )
    ok &= _check(
        f"{vocabulary_name} redeclaration failure output names the mutated file",
        module_path.name in failing_result.stdout,
    )
    ok &= _check(
        f"{vocabulary_name} redeclaration failure output names the exact count delta (0 -> 1)",
        "increased from baseline 0 to 1" in failing_result.stdout,
    )

    module_path.write_text(clean_source, encoding="utf-8")
    reverted_result = _self_test_shared_vocabulary_run_cli(tmp_root)
    ok &= _check(
        f"reverting the {vocabulary_name} mutation clears the failure, "
        f"got exit {reverted_result.returncode}",
        reverted_result.returncode == 0,
    )
    return ok


def _self_test_shared_vocabulary_cli_non_vacuity() -> bool:
    """End-to-end proof the G1 shared-vocabulary ratchet actually FIRES --
    for the Enum-sourced case AND, added when the harvest was widened past
    ``str, Enum`` classes, for each of the three non-Enum canonical shapes.

    Starts from a fixture that IMPORTS QueryTerminal (the design's required
    POSITIVE case: exits 0), mutates it to ALSO bare-string-redeclare
    QueryTerminal's four members (the required NEGATIVE case: exits 1, names
    the file and the exact count delta), reverts and proves it clears, then
    repeats one mutate/detect/revert cycle per non-Enum vocabulary
    (``DSL_EXCEPTION_HTTP_STATUS`` and ``NOSQL_UNSUPPORTED_METHODS`` as bare
    dict literals redeclaring their keys, ``NOSQL_SUPPORTED_METHODS`` as a bare
    frozenset literal redeclaring its members) against the SAME clean
    fixture file.
    """
    report_step(
        "Self-test 14/24: shared-vocabulary ratchet CLI mutation non-vacuity "
        "(fixture importing QueryTerminal exits 0; redeclaring its four "
        "members as bare literals exits 1; reverting clears it -- plus one "
        "mutate/detect/revert cycle per non-Enum canonical vocabulary)"
    )
    ok = True
    tmp_root = _SELF_TEST_SCRATCH_ROOT / f"shared-vocab-cli-{uuid.uuid4().hex}"
    tmp_root.mkdir(parents=True, exist_ok=True)
    try:
        module_path = _self_test_shared_vocabulary_build_fixture_monorepo(tmp_root)
        clean_source = module_path.read_text(encoding="utf-8")

        clean_result = _self_test_shared_vocabulary_run_cli(tmp_root)
        ok &= _check(
            f"fixture importing QueryTerminal (no redeclaration) exits 0, got {clean_result.returncode}",
            clean_result.returncode == 0,
        )

        from datrix_codegen_kernel.enums import QueryTerminal

        # The redeclaration is built from the live enum, so the mutation
        # stays a full-vocabulary copy whenever a member is added or removed.
        query_terminal_literal = frozenset(member.value for member in QueryTerminal)
        module_path.write_text(
            clean_source + f"\n_TERMINAL_METHODS = {query_terminal_literal!r}\n",
            encoding="utf-8",
        )
        failing_result = _self_test_shared_vocabulary_run_cli(tmp_root)
        ok &= _check(
            f"redeclaring every QueryTerminal member as a bare literal exits 1, got {failing_result.returncode}",
            failing_result.returncode == 1,
        )
        ok &= _check(
            "failure output names the mutated file",
            "sample_query_chain.py" in failing_result.stdout,
        )
        ok &= _check(
            "failure output names the exact count delta (0 -> 1)",
            "increased from baseline 0 to 1" in failing_result.stdout,
        )

        module_path.write_text(clean_source, encoding="utf-8")
        reverted_result = _self_test_shared_vocabulary_run_cli(tmp_root)
        ok &= _check(
            f"reverting the mutation clears the failure, got exit {reverted_result.returncode}",
            reverted_result.returncode == 0,
        )

        from datrix_codegen_kernel.enums import (
            DSL_EXCEPTION_HTTP_STATUS,
            NOSQL_SUPPORTED_METHODS,
            NOSQL_UNSUPPORTED_METHODS,
        )

        ok &= _self_test_shared_vocabulary_non_enum_cli_cycle(
            tmp_root,
            module_path,
            clean_source,
            vocabulary_name="DSL_EXCEPTION_HTTP_STATUS",
            container_name="dict",
            literal_source=f"_EXCEPTION_STATUS_MAP = {DSL_EXCEPTION_HTTP_STATUS!r}\n",
        )
        ok &= _self_test_shared_vocabulary_non_enum_cli_cycle(
            tmp_root,
            module_path,
            clean_source,
            vocabulary_name="NOSQL_UNSUPPORTED_METHODS",
            container_name="dict",
            literal_source=f"_NOSQL_UNSUPPORTED = {NOSQL_UNSUPPORTED_METHODS!r}\n",
        )
        ok &= _self_test_shared_vocabulary_non_enum_cli_cycle(
            tmp_root,
            module_path,
            clean_source,
            vocabulary_name="NOSQL_SUPPORTED_METHODS",
            container_name="frozenset",
            literal_source=f"_NOSQL_SUPPORTED = {frozenset(NOSQL_SUPPORTED_METHODS)!r}\n",
        )
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    return ok


def self_test_checks() -> list[NamedCheck]:
    """The shared-vocabulary scanner's self-tests, each a check the CLI's ``--self-test`` runs."""
    return [
        self_test_check(_self_test_shared_vocabulary_scanner),
        self_test_check(_self_test_shared_vocabulary_cli_non_vacuity),
    ]
