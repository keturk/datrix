"""Target-literal and identity-rule scanners and their ratchet."""

from __future__ import annotations

import ast
import functools
import re
import shutil
import subprocess
import sys
import uuid
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# The provider-literal ratchet must enumerate provider ids from the
# installed datrix.platforms entry points, never a hardcoded
# "aws"/"azure"/"docker"/"local" literal: registered_platform_names() comes
# from the shared scripts package (datrix_scripts, on PYTHONPATH).
from datrix_common.config.datasource.identity_config import (
    IdentityProvider as ConfigIdentityProvider,
)

from datrix_scripts.gate_harness import NamedCheck, report_step
from datrix_scripts.registered_targets import (
    AXIS_LANGUAGES,
    entry_point_module_roots,
    owned_identity_provider_type_names,
    registered_language_names,
    registered_platform_names,
)
from datrix_scripts.target_literal_positions import (
    target_name_literal_hits,
)
from datrix_scripts.scan.import_boundaries._ast_common import (
    _SELF_TEST_SCRATCH_ROOT,
    _TYPE_REFERENCE_CALL_NAMES,
    CLI_COMMAND,
    LANGUAGE_CORE_PACKAGES,
    PackageInfo,
    _check,
    _identifier_carries_target_name,
    _identifiers_in_type_expression,
    _self_test_write_manifest,
    declaration_identifiers,
    self_test_check,
    tighten_only_messages,
    write_count_baseline,
)
from datrix_scripts.scan.import_boundaries._module_resolution import _is_datrix_module_path

# ---------------------------------------------------------------------------
# I1 Target-Literal Ratchet (Decision D1, Invariant I1)
#
# The I1 ratchet polices the DERIVED shared-package set
# (discover_shared_packages -- every discovered package registering none of
# datrix.languages/datrix.platforms/datrix.generators/datrix.extensions;
# datrix_common, datrix_codegen_common, and datrix_cli today, never a
# hardcoded list). "Shared layers ask questions, target plugins answer
# them" — datrix_language and the leaf
# datrix_codegen_{python,typescript,aws,azure,docker,sql,component} packages
# are OWNERS of target identity and are exempt from this scan (they always
# register a taxonomy entry point, so discover_shared_packages never
# classifies them as shared).

# Central table / dict / class names known TODAY to encode closed-world target
# policy in a shared layer. The list is frozen: each entry is scheduled for
# deletion (the inline comment records where it lived and when it went), and
# the ratchet's job is to make sure nothing NEW joins this list while the
# remaining entries are removed.
TARGET_LITERAL_CENTRAL_NAMES: frozenset[str] = frozenset(
    {
        "Language",  # enums.py:13-18 (deleted 07-03)
        "ProjectLanguage",  # enums.py:26-30 (deleted 07-03)
        "GENERATORS_BY_LANGUAGE",  # enums.py:33 (deleted 06-04)
        "DeploymentProvider",  # enums.py:82-97 (deleted 07-03)
        "PROVIDER_GENERATORS",  # enums.py:289 (deleted 07-03)
        "_TARGET_KIND_MAP",  # dgen/parser.py:36, validator.py:30 (deleted 06-02)
        "_KNOWN_DEFINITION_MODULES",  # dgen/compiler.py:153-161 (deleted 06-02)
        "EMAIL_REALIZATION",  # provisioning.py:60-81 (deleted 07-04)
        "SMS_REALIZATION",  # provisioning.py:92-109 (deleted 07-04)
        "PUSH_REALIZATION",  # provisioning.py:~129 (deleted 07-04)
        "_DEFAULT_BACKEND_BY_PROVIDER",  # secret_backend.py:175-178 (deleted 07-04)
        "VALID_PROVIDERS_BY_RUNTIME",  # deployment_validation.py:29-42 (deleted 07-04)
        "_SERVERLESS_PLATFORM_BY_PROVIDER",  # hosting_validation.py:22-26 (deleted 07-04)
        "_PLATFORM_INFRA_CLASSES",  # auth_resolver.py:54-71 (deleted 07-05)
    }
)

# Enum-qualified member accesses (Attribute nodes like `DeploymentProvider.AWS`)
# recognized as target-literal references. Keyed by the enum class name so a
# bare identifier collision (e.g. a local variable named `AWS`) never matches --
# only `<ClassName>.<MEMBER>` attribute access counts.
TARGET_LITERAL_ENUM_MEMBERS: dict[str, frozenset[str]] = {
    "Language": frozenset({"PYTHON", "TYPESCRIPT", "SQL"}),
    "ProjectLanguage": frozenset({"PYTHON", "TYPESCRIPT"}),
    "DeploymentProvider": frozenset({"LOCAL", "EXISTING", "AWS", "AZURE"}),
}

#: The two hit kinds matched against the frozen names above.
CentralNameKind = Literal["central_table_name", "enum_member_qualified"]

# Platform-token identifier-shape match: mirrors
# _identifier_carries_target_name (G2, language tokens) but over registered
# PLATFORM tokens, restricted to the same declaration/type-reference
# positions scan_file_for_shared_target_names already scopes to (class/
# function defs, annotated/plain module- or class-level assignment targets,
# type references) -- reusing _identifier_segments and
# _identifiers_in_type_expression unmodified. "local" is EXCLUDED from the
# platform-token vocabulary for this check specifically: it is a registered
# datrix.platforms id that is also an ordinary English word, the exact reason
# G2 excludes platforms entirely. The vocabulary stays derived from the
# registry; only this word-collision set is hand-kept, and the self-test
# asserts every excluded token is still a registered platform so a stale
# exclusion fails loud.
_PLATFORM_TOKEN_EXCLUSIONS: frozenset[str] = frozenset({"local"})


def _platform_token_vocabulary() -> frozenset[str]:
    """Registered platform tokens, minus the English-word collision(s)."""
    return frozenset(registered_platform_names()) - _PLATFORM_TOKEN_EXCLUSIONS


def _target_literal_vocabulary() -> frozenset[str]:
    """Registered language names union registered platform names, INCLUDING
    "local" (unlike _platform_token_vocabulary, which excludes it as an
    English-word collision for the identifier-segment shape), union the identity
    provider types an installed platform package owns. As a whole string in a
    str-equality/key position, or a whole dotted import-path segment, "local"
    is a target identity, not English prose; the isinstance kind matches
    identifier SEGMENTS, so it drops the English-word collisions itself
    (``_target_type_check_hits``).
    An identity provider type's rules belong to the package that integrates the
    provider, so a shared layer comparing against one is the same defect as a
    shared layer comparing against a platform name; the owned types are derived
    from the installed platform declarations, never listed here."""
    return (
        frozenset(registered_language_names())
        | frozenset(registered_platform_names())
        | _owned_identity_types()
    )


@functools.lru_cache(maxsize=1)
def _owned_identity_types() -> frozenset[str]:
    """The identity provider types an installed platform package owns, read once per run."""
    return owned_identity_provider_type_names()


#: Files that define or bridge the closed ``.dcfg`` identity provider vocabulary
#: (the enum itself, its bridge to the planner's open identifiers, and the built-in
#: ``external`` rules): they may name the enum's members and the provider-type
#: strings, and they are exempt from the identity rules below.
IDENTITY_VOCABULARY_HOME_SUFFIXES: tuple[str, ...] = (
    "config/datasource/identity_config.py",
    "identity/planner/config_bridge.py",
    "identity/authored_issuer_rules.py",
)

#: The shared tree where NO identity provider type's rule may live: a hit of an
#: identity kind here is a hard failure, and no baseline entry is admitted for it.
IDENTITY_RULES_HARD_ZERO_PREFIX: str = "datrix-common/src/datrix_common/identity/"

#: The target-literal kinds that name an identity provider type.
IDENTITY_RULE_KINDS: frozenset[str] = frozenset(
    {"identity_provider_member", "target_name_literal", "target_type_check", "target_module_import"}
)


def _is_identity_vocabulary_home(file_path: Path) -> bool:
    """Whether *file_path* is one of the identity vocabulary's home files."""
    posix = file_path.as_posix()
    return any(posix.endswith(suffix) for suffix in IDENTITY_VOCABULARY_HOME_SUFFIXES)


def _identity_provider_member_hits(
    tree: ast.AST, flagged_values: frozenset[str]
) -> list[tuple[str, int, str]]:
    """Find ``IdentityProvider.<MEMBER>`` attribute reads naming a flagged provider type.

    The enum is recognised through the names an ``identity_config`` import binds
    ``IdentityProvider`` to (any ``as`` alias), so ``IdentityProviderType.ZITADEL`` and
    ``ConfigIdentityProvider.ZITADEL`` are as visible as ``IdentityProvider.ZITADEL``.
    A member is flagged when its VALUE is in *flagged_values* (the owned provider
    types and the built-in ``external``); the credential kind ``apiKey`` names no
    provider product and is never flagged.

    Returns:
        ``(identifier, line_number, matched provider type)`` per hit.
    """
    aliases = _identity_provider_aliases(tree)
    if not aliases:
        return []
    value_by_member = {member.name: member.value for member in ConfigIdentityProvider}
    hits: list[tuple[str, int, str]] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in aliases
            and value_by_member.get(node.attr) in flagged_values
        ):
            hits.append((f"{node.value.id}.{node.attr}", node.lineno, value_by_member[node.attr]))
    return hits


def _identity_provider_aliases(tree: ast.AST) -> set[str]:
    """The names an ``identity_config`` import binds ``IdentityProvider`` to."""
    return {
        imported.asname or imported.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module is not None
        and node.module.split(".")[-1] == "identity_config"
        for imported in node.names
        if imported.name == "IdentityProvider"
    }


def _identity_flagged_values() -> frozenset[str]:
    """Provider types whose members/literals a shared layer must not name: the owned
    types plus the built-in ``external`` type."""
    return _owned_identity_types() | {ConfigIdentityProvider.EXTERNAL.value}


#: Every target-literal hit kind.
TargetLiteralKind = Literal[
    "central_table_name",
    "enum_member_qualified",
    "platform_token_identifier",
    "platform_token_module_name",
    "target_name_literal",
    "target_type_check",
    "target_module_import",
    "identity_provider_member",
]


@dataclass(frozen=True)
class TargetLiteralHit:
    """One occurrence of a target-literal identifier in a shared-layer file."""

    file_path: Path
    line_number: int
    identifier: str
    kind: TargetLiteralKind
    # The registered target token *identifier* carries as a segment, is
    # exactly equal to, or (for target_module_import) appears as a dotted-
    # path segment of. Populated for the two platform_token_* kinds and the
    # three target_* kinds -- the frozen-name matches (central_table_name /
    # enum_member_qualified) match an exact known name, not a vocabulary
    # member, so they carry no "matched" vocabulary member.
    matched_target: str | None = None


# A heuristic dotted-import-path shape: one or more '.'-separated Python
# identifier segments, at least two segments (a bare identifier is never a
# module path). Matches "datrix_codegen_aws.dgen.aws_definitions"; never
# matches a plain single word or a non-identifier string.
_DOTTED_MODULE_PATH_RE: re.Pattern[str] = re.compile(
    r"[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)+"
)


def _platform_token_in_dotted_string(
    value: str, platform_names: frozenset[str]
) -> str | None:
    """The platform token a dotted-module-path-shaped string carries in any
    of its '.'-separated segments, or ``None`` -- ``value`` itself is never
    matched whole; only a genuine dotted-path shape is considered, and each
    segment is matched via the same identifier-segment algorithm
    ``_identifier_carries_target_name`` already applies to real identifiers.
    """
    if not _DOTTED_MODULE_PATH_RE.fullmatch(value):
        return None
    for segment in value.split("."):
        matched = _identifier_carries_target_name(segment, platform_names)
        if matched is not None:
            return matched
    return None


def _scoped_plain_assign_values(tree: ast.Module) -> list[tuple[ast.expr, int]]:
    """Every ``(value, line_number)`` of a plain (unannotated) ``ast.Assign``
    declared at MODULE top level or immediate CLASS-BODY level -- the exact
    same scope ``_scoped_plain_assign_targets`` restricts its TARGETS to,
    applied to the VALUE side instead so a dotted-module-path string literal
    assigned there can be inspected. A function-body-local assignment is out
    of scope for the same reason it is out of scope for
    ``_scoped_plain_assign_targets``: an ordinary local variable's value is
    not a declaration.
    """
    values: list[tuple[ast.expr, int]] = []
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign):
            values.append((stmt.value, stmt.lineno))
        elif isinstance(stmt, ast.ClassDef):
            for class_stmt in stmt.body:
                if isinstance(class_stmt, ast.Assign):
                    values.append((class_stmt.value, class_stmt.lineno))
    return values


def _platform_token_module_path_string_hits(
    tree: ast.Module, platform_names: frozenset[str]
) -> list[tuple[str, int, str]]:
    """``(string, line_number, matched_platform)`` for every dotted-module-
    path-shaped string literal assigned as a plain value, a dict value, or a
    list/tuple/set element, at the same module-/class-body scope
    ``_scoped_plain_assign_values`` restricts to -- an ordinary function-
    local string is out of scope, exactly like the identifier-shape match.
    """
    hits: list[tuple[str, int, str]] = []
    for value, _line in _scoped_plain_assign_values(tree):
        for element in _assigned_value_elements(value):
            if isinstance(element, ast.Constant) and isinstance(element.value, str):
                matched = _platform_token_in_dotted_string(element.value, platform_names)
                if matched is not None:
                    hits.append((element.value, element.lineno, matched))
    return hits


def _assigned_value_elements(value: ast.expr) -> list[ast.expr]:
    """The expressions an assigned value holds: a dict's values, a
    list/tuple/set's elements, or the value itself."""
    if isinstance(value, ast.Dict):
        return list(value.values)
    if isinstance(value, (ast.List, ast.Tuple, ast.Set)):
        return list(value.elts)
    return [value]


def _platform_token_identifier_hits(
    tree: ast.Module, platform_names: frozenset[str]
) -> list[tuple[str, int, str]]:
    """``(identifier, line_number, matched_platform)`` for every declaration
    or type-reference identifier carrying a registered platform token as an
    identifier segment.

    Scoped to the EXACT declaration/type-reference positions
    ``scan_file_for_shared_target_names`` (the shared-target-name ratchet) already restricts language-
    token matching to -- class/function/method DEFINITIONS, a dataclass
    field or type alias at module/class-body level (annotated or plain
    assignment), and a type reference (isinstance/issubclass argument, base
    class, parameter/return annotation, the value of a ``TypeAlias``
    annotated assignment -- a string in any other annotated value is data,
    not a forward reference). Never a
    bare local variable, function parameter, loop variable, or attribute
    READ -- an unscoped scan over an open, runtime-derived vocabulary is
    exactly what produced G2's own 305-false-positive result for the
    (excluded) "local" case; the same false-positive mode would reproduce
    for every OTHER platform token (e.g. "aws" as a local variable name) if
    this match were not scoped identically.
    """
    hits: list[tuple[str, int, str]] = []
    for identifier, line_number, _kind in declaration_identifiers(tree):
        matched = _identifier_carries_target_name(identifier, platform_names)
        if matched is not None:
            hits.append((identifier, line_number, matched))
    return hits


def _platform_token_module_name_hits(
    file_path: Path, monorepo_root: Path, platform_names: frozenset[str]
) -> list[tuple[str, int, str]]:
    """``(component, line_number, matched_platform)`` for every path
    component of *file_path*'s path relative to *monorepo_root* (directory
    names and the filename stem, split on '/' by the relative-path
    computation and on '_'/camelCase by ``_identifier_carries_target_name``)
    that carries a registered platform token as a segment -- catches a file
    at a path like ``deployment/azure_naming.py``. Reported at line 1: this
    is a file-level match, not tied to any single AST node.
    """
    hits: list[tuple[str, int, str]] = []
    rel_parts = file_path.relative_to(monorepo_root).parts
    components = (*rel_parts[:-1], Path(rel_parts[-1]).stem)
    for component in components:
        matched = _identifier_carries_target_name(component, platform_names)
        if matched is not None:
            hits.append((component, 1, matched))
    return hits


# ---------------------------------------------------------------------------
# Target-Literal Ratchet -- key/comparand/isinstance/import-path shapes
#
# The pre-existing target-literal kinds above match a frozen central-table/
# enum-member name list plus a declaration/type-reference identifier shape.
# They miss a target name used as a dict key, a `.get()` argument, an
# `==`/`in` comparand, an `isinstance`/`issubclass` class argument, or a
# dotted import-module segment -- real target-identity leaks a shared layer
# must not carry, in positions the identifier-shape match never visits. The
# three kinds below close that gap, scoped to exactly the AST positions
# enumerated in each kind's docstring -- never a generic "any string near a
# vocabulary word" scan, which would flag every docstring and log message.


def _owning_package_import_root(file_path: Path, monorepo_root: Path) -> str | None:
    """The import-root directory name (e.g. ``datrix_codegen_typescript_core``)
    that *file_path* lives under, resolved via *monorepo_root*-relative path
    segments only -- the same ``<package-dir>/src/<import-root>/...`` layout
    ``_platform_token_module_name_hits`` already assumes, never a substring
    match on the path string. Returns ``None`` when the path does not have
    at least that three-segment prefix (never expected for a file this
    scanner actually reaches, since every caller iterates a discovered
    package's own ``src_dir``).
    """
    rel_parts = file_path.relative_to(monorepo_root).parts
    if len(rel_parts) < 3 or rel_parts[1] != "src":
        return None
    return rel_parts[2]


def _language_core_own_language_names() -> dict[str, str]:
    """Map each ``LANGUAGE_CORE_PACKAGES`` key (a language-core library's own
    import root, e.g. ``datrix_codegen_typescript_core``) to the registered
    language name of the backend package it serves (e.g. ``typescript``),
    read live from ``entry_point_module_roots(AXIS_LANGUAGES)`` (inverted) --
    never a hardcoded core-package-to-language literal.

    Returns:
        ``{core import root: served language's registered name}``.

    Raises:
        ValueError: A ``LANGUAGE_CORE_PACKAGES`` value names a backend import
            root with no matching installed ``datrix.languages`` entry
            point -- a real configuration inconsistency between the mapping
            and the installed distributions, never silently skipped.
    """
    import_root_to_language = {
        import_root: language_name
        for language_name, import_root in entry_point_module_roots(AXIS_LANGUAGES).items()
    }
    served: dict[str, str] = {}
    for core_import_root, backend_import_root in LANGUAGE_CORE_PACKAGES.items():
        language_name = import_root_to_language.get(backend_import_root)
        if language_name is None:
            raise ValueError(
                f"LANGUAGE_CORE_PACKAGES entry {core_import_root!r} names backend "
                f"import root {backend_import_root!r}, which has no matching "
                f"installed 'datrix.languages' entry point. Installed entry-point "
                f"import roots: {sorted(import_root_to_language)}. Fix: verify the "
                f"backend package is installed into the active environment and its "
                f"pyproject.toml entry-point module path matches "
                f"{backend_import_root!r}."
            )
        served[core_import_root] = language_name
    return served


def _is_own_language_excluded(
    file_path: Path, monorepo_root: Path, matched_target: str
) -> bool:
    """True when *matched_target* names the language whose own core package
    *file_path* lives under (``LANGUAGE_CORE_PACKAGES``) -- e.g. a
    "typescript" hit inside ``datrix_codegen_typescript_core`` is that
    language's own home, not a target-identity leak. Scoped ONLY to the
    three new target-literal kinds; the two pre-existing
    platform-token kinds keep their own, separate
    ``_PLATFORM_TOKEN_EXCLUSIONS`` mechanism and never call this.
    """
    owning_root = _owning_package_import_root(file_path, monorepo_root)
    if owning_root is None or owning_root not in LANGUAGE_CORE_PACKAGES:
        return False
    served_language = _language_core_own_language_names()[owning_root]
    return matched_target.casefold() == served_language.casefold()


def _target_type_check_hits(
    tree: ast.Module, target_literal_names: frozenset[str]
) -> list[tuple[str, int, str]]:
    """``(identifier, line_number, matched_target)`` for every
    ``isinstance``/``issubclass`` call whose second argument (or a ``Tuple``
    element of it) is a type expression carrying a *target_literal_names*
    token as an identifier segment (``_identifier_carries_target_name``).

    Reuses ``_identifiers_in_type_expression`` -- the same type-expression
    walk the pre-existing ``platform_token_identifier`` kind already applies
    to ``isinstance``/``issubclass`` arguments -- against the full
    languages-union-platforms vocabulary rather than the platform-only one,
    so a language-named class (``isinstance(c, PythonRuntimeConfig)``) is
    caught here even though it is invisible to the platform-scoped kind.

    Two shapes are not target type checks:

    - a ``_PLATFORM_TOKEN_EXCLUSIONS`` word as an identifier segment
      (``isinstance(node, _LOCAL_BINDERS)``): the match here is the same
      identifier-segment shape as ``platform_token_identifier``, where
      "local" is the English word, not the platform;
    - the whole test of an ``assert`` (``assert isinstance(parsed, X)``):
      it narrows a value its caller already typed and selects no behaviour,
      exactly like the parameter annotation this scan never counts. A type
      check that branches (``if``/``return``/a boolean operand) still counts.
    """
    segment_names = target_literal_names - _PLATFORM_TOKEN_EXCLUSIONS
    hits: list[tuple[str, int, str]] = []
    for call_arg in _branching_type_check_arguments(tree):
        for identifier, lineno in _identifiers_in_type_expression(call_arg):
            matched = _identifier_carries_target_name(identifier, segment_names)
            if matched is not None:
                hits.append((identifier, lineno, matched))
    return hits


def _branching_type_check_arguments(tree: ast.Module) -> Iterator[ast.expr]:
    """The class arguments of every ``isinstance``/``issubclass`` call that is
    not the whole test of an ``assert``, in AST-walk order."""
    narrowing = {
        id(node.test) for node in ast.walk(tree) if isinstance(node, ast.Assert)
    }
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
            continue
        if node.func.id in _TYPE_REFERENCE_CALL_NAMES and id(node) not in narrowing:
            yield from node.args[1:]


def _target_module_import_hits(
    tree: ast.Module, target_literal_names: frozenset[str]
) -> list[tuple[str, int, str]]:
    """``(dotted module path, line_number, matched_target)`` for every
    ``ast.ImportFrom``/``ast.Import`` node whose dotted module path
    (``node.module`` for ``ImportFrom``, each ``alias.name`` for ``Import``)
    has a ``.``-split segment exactly equal to a *target_literal_names*
    member (``from datrix_common.config.platform.docker import X`` yields
    one hit naming ``docker``). Exact per-segment string equality only --
    unlike the identifier-shape kinds, a module path is never re-split on
    ``_``/camelCase, so ``datrix_codegen_python`` (one dotted segment) is
    not itself a hit. One hit per qualifying module path -- the first
    matching segment -- since a single import statement is one occurrence
    of the shape.
    """
    hits: list[tuple[str, int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        for module_path in _imported_module_paths(node):
            matched = next(
                (
                    segment
                    for segment in module_path.split(".")
                    if segment in target_literal_names
                ),
                None,
            )
            if matched is not None:
                hits.append((module_path, node.lineno, matched))
    return hits


def _imported_module_paths(node: ast.Import | ast.ImportFrom) -> list[str]:
    """The dotted module paths an import statement names: ``node.module`` of
    a ``from`` import that has one, each alias of a plain ``import``."""
    if isinstance(node, ast.ImportFrom):
        return [node.module] if node.module is not None else []
    return [alias.name for alias in node.names]


def _foreign_bound_names(tree: ast.Module) -> frozenset[str]:
    """Names the module binds ONLY by importing them from outside Datrix's own
    module graph (``from tree_sitter import Language``, ``import tree_sitter``).

    Every ``TARGET_LITERAL_CENTRAL_NAMES``/``TARGET_LITERAL_ENUM_MEMBERS`` entry
    is a Datrix-defined table or enum, so a reference whose name resolves to a
    third-party import (tree-sitter's own ``Language`` class) is a name
    collision, never that table. A relative import is Datrix's own. A name the
    module also defines or assigns itself is not foreign: the reference could be
    the local binding, so it stays a hit.
    """
    imported: set[str] = set()
    local: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module is not None and not _is_datrix_module_path(node.module):
                imported.update(alias.asname or alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            imported.update(
                alias.asname or alias.name.split(".")[0]
                for alias in node.names
                if not _is_datrix_module_path(alias.name)
            )
        elif isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            local.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            local.add(node.id)
    return frozenset(imported - local)


def _attribute_root_name(node: ast.Attribute) -> str | None:
    """The bare name an attribute chain starts from (``tree_sitter`` in
    ``tree_sitter.Language``), or ``None`` when it starts from a call,
    subscript or other expression."""
    value: ast.expr = node.value
    while isinstance(value, ast.Attribute):
        value = value.value
    return value.id if isinstance(value, ast.Name) else None


def _central_name_matches(
    tree: ast.Module, foreign: frozenset[str]
) -> Iterator[tuple[str, int, CentralNameKind]]:
    """``(identifier, line_number, kind)`` for every definition of, or
    reference to, a ``TARGET_LITERAL_CENTRAL_NAMES`` entry and every
    ``TARGET_LITERAL_ENUM_MEMBERS`` member read, in AST-walk order. A
    reference bound by a third-party import (*foreign*) -- the bare name, an
    attribute read off a third-party module, or a member read off a
    third-party name spelled like the enum -- is a collision, not a hit."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            if node.id in TARGET_LITERAL_CENTRAL_NAMES and node.id not in foreign:
                yield node.id, node.lineno, "central_table_name"
        elif isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in TARGET_LITERAL_CENTRAL_NAMES:
                yield node.name, node.lineno, "central_table_name"
        elif isinstance(node, ast.Attribute):
            yield from _attribute_central_matches(node, foreign)


def _attribute_central_matches(
    node: ast.Attribute, foreign: frozenset[str]
) -> Iterator[tuple[str, int, CentralNameKind]]:
    """The central-name and enum-member matches of one attribute read."""
    if _attribute_root_name(node) in foreign:
        return
    if node.attr in TARGET_LITERAL_CENTRAL_NAMES:
        yield node.attr, node.lineno, "central_table_name"
    if (
        isinstance(node.value, ast.Name)
        and node.value.id in TARGET_LITERAL_ENUM_MEMBERS
        and node.attr in TARGET_LITERAL_ENUM_MEMBERS[node.value.id]
    ):
        yield f"{node.value.id}.{node.attr}", node.lineno, "enum_member_qualified"


def scan_file_for_target_literals(
    file_path: Path,
    monorepo_root: Path,
    platform_names: frozenset[str],
    target_literal_names: frozenset[str],
) -> list[TargetLiteralHit]:
    """AST-walk *file_path* for target-literal identifiers.

    Seven match kinds:
      - ``central_table_name``: any ``ast.Name``/``ast.ClassDef``/``ast.FunctionDef``
        (or ``ast.AsyncFunctionDef``) whose identifier is exactly one of
        ``TARGET_LITERAL_CENTRAL_NAMES`` (definition sites AND reference sites
        both count -- a table is a defect whether it's being defined or
        consumed), plus any ``ast.Attribute`` whose ``attr`` itself is one of
        ``TARGET_LITERAL_CENTRAL_NAMES`` (e.g. a module-qualified
        ``enums.GENERATORS_BY_LANGUAGE`` reference).
      - ``enum_member_qualified``: any ``ast.Attribute`` node whose ``value`` is
        an ``ast.Name`` with ``id`` in ``TARGET_LITERAL_ENUM_MEMBERS`` and whose
        ``attr`` is in the corresponding member frozenset (e.g. `Language.PYTHON`,
        `DeploymentProvider.AWS`) -- NOT a bare `AWS` identifier alone.
        Neither frozen-name kind counts a reference the module binds only by a
        third-party import (``tree_sitter.Language``) -- see
        ``_foreign_bound_names``.
      - ``platform_token_identifier``: a declaration/type-reference identifier
        (class/function def, module-/class-level field or type alias, type
        reference) carrying a registered platform token as an identifier
        segment -- see ``_platform_token_identifier_hits``. ``"local"`` is
        excluded (English-word collision, see ``_PLATFORM_TOKEN_EXCLUSIONS``).
      - ``platform_token_module_name``: the file's own path (relative to
        *monorepo_root*, split on both ``/`` and ``_``/camelCase) or a
        dotted-module-path-shaped string literal assigned at module-/class-
        level scope carries a registered platform token -- see
        ``_platform_token_module_name_hits`` / ``_platform_token_module_path_string_hits``.
      - ``target_name_literal``: a string constant exactly equal to a
        ``_target_literal_vocabulary()`` member (registered language names
        UNION registered platform names, INCLUDING ``"local"``) in a
        comparison/key/``.get()``/dict-key/match-value position -- see
        ``_target_name_literal_hits``.
      - ``target_type_check``: an ``isinstance``/``issubclass`` call whose
        class argument carries a ``_target_literal_vocabulary()`` token
        (minus the English-word collisions) as an identifier segment, unless
        the call is the whole test of an ``assert`` -- see
        ``_target_type_check_hits``.
      - ``target_module_import``: an ``ast.ImportFrom``/``ast.Import`` node
        whose dotted module path has a ``.``-split segment exactly equal to
        a ``_target_literal_vocabulary()`` member -- see
        ``_target_module_import_hits``.

    The three new kinds above are dropped for a file inside a
    ``LANGUAGE_CORE_PACKAGES`` package when the matched token names that
    package's own served language (``_is_own_language_excluded``). The two
    pre-existing platform-token kinds are unaffected; they keep their own,
    separate ``_PLATFORM_TOKEN_EXCLUSIONS`` mechanism.

    Args:
        file_path: Path to Python source file.
        monorepo_root: Monorepo root, for the module-name-from-path match and
            the own-language exclusion's package resolution.
        platform_names: Registered platform tokens minus the "local"
            English-word collision, from ``_platform_token_vocabulary()`` --
            feeds the two pre-existing platform-token kinds only.
        target_literal_names: Registered language names UNION registered
            platform names, INCLUDING "local", from
            ``_target_literal_vocabulary()`` -- feeds the three new kinds
            only.

    Returns:
        List of hits found in the file, in AST-walk order (the two
        pre-existing platform-token kinds, then the three new kinds, are
        appended after the frozen-name-match walk).

    Raises:
        SyntaxError: propagated from ast.parse (caller decides how to report).
        OSError: propagated if the file cannot be read.
    """
    # utf-8-sig transparently strips a leading UTF-8 BOM (U+FEFF) so a
    # BOM-prefixed file can never fail ast.parse and be silently skipped
    # (scanner integrity).
    source_code = file_path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source_code, filename=str(file_path))

    hits = [
        TargetLiteralHit(
            file_path=file_path, line_number=line_number, identifier=identifier, kind=kind
        )
        for identifier, line_number, kind in _central_name_matches(
            tree, _foreign_bound_names(tree)
        )
    ]

    hits.extend(
        _matched_hits(
            file_path,
            "platform_token_identifier",
            _platform_token_identifier_hits(tree, platform_names),
        )
    )
    hits.extend(
        _matched_hits(
            file_path,
            "platform_token_module_name",
            _platform_token_module_name_hits(file_path, monorepo_root, platform_names),
        )
    )
    hits.extend(
        _matched_hits(
            file_path,
            "platform_token_module_name",
            _platform_token_module_path_string_hits(tree, platform_names),
        )
    )

    identity_home = _is_identity_vocabulary_home(file_path)

    def _kept(matches: Iterable[tuple[str, int, str]]) -> list[tuple[str, int, str]]:
        return [
            match
            for match in matches
            if _keeps_target_match(file_path, monorepo_root, identity_home, match[2])
        ]

    name_literals = (
        (value, line_number, value)
        for value, line_number in target_name_literal_hits(tree, target_literal_names)
    )
    hits.extend(_matched_hits(file_path, "target_name_literal", _kept(name_literals)))
    hits.extend(
        _matched_hits(
            file_path,
            "target_type_check",
            _kept(_target_type_check_hits(tree, target_literal_names)),
        )
    )
    hits.extend(
        _matched_hits(
            file_path,
            "target_module_import",
            _kept(_target_module_import_hits(tree, target_literal_names)),
        )
    )

    if not identity_home:
        hits.extend(
            _matched_hits(
                file_path,
                "identity_provider_member",
                _identity_provider_member_hits(tree, _identity_flagged_values()),
            )
        )

    return hits


def _matched_hits(
    file_path: Path,
    kind: TargetLiteralKind,
    matches: Iterable[tuple[str, int, str]],
) -> list[TargetLiteralHit]:
    """One *kind* hit per ``(identifier, line_number, matched_target)``."""
    return [
        TargetLiteralHit(
            file_path=file_path,
            line_number=line_number,
            identifier=identifier,
            kind=kind,
            matched_target=matched,
        )
        for identifier, line_number, matched in matches
    ]


def _keeps_target_match(
    file_path: Path, monorepo_root: Path, identity_home: bool, matched: str
) -> bool:
    """Whether a target_* kind match counts: not the file's own served
    language (``_is_own_language_excluded``), and not an owned identity
    provider type named inside the identity vocabulary's home files."""
    if _is_own_language_excluded(file_path, monorepo_root, matched):
        return False
    return not (identity_home and matched in _owned_identity_types())


def scan_target_literals(
    packages: dict[str, PackageInfo],
    monorepo_root: Path,
    shared_packages: tuple[str, ...],
) -> dict[Path, list[TargetLiteralHit]]:
    """Scan every ``.py`` file under each of *shared_packages*' ``src/`` tree
    (via *packages*, as already discovered by ``discover_packages``) for
    target-literal identifiers.

    Args:
        packages: Package name -> PackageInfo, as returned by discover_packages().
        monorepo_root: Monorepo root for relative path reporting.
        shared_packages: The DERIVED shared-package set
            (``discover_shared_packages``) -- every discovered package
            registering none of the four taxonomy entry-point groups.

    Returns:
        Mapping of file path -> hits in that file (files with zero hits omitted).
    """
    results: dict[Path, list[TargetLiteralHit]] = {}
    platform_names = _platform_token_vocabulary()
    target_literal_names = _target_literal_vocabulary()

    for package_name in shared_packages:
        package_info = packages.get(package_name)
        if package_info is None:
            continue

        for py_file in package_info.src_dir.rglob("*.py"):
            try:
                hits = scan_file_for_target_literals(
                    py_file, monorepo_root, platform_names, target_literal_names
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


_TARGET_LITERAL_BASELINE_HEADER = (
    "# I1 Target-Literal Ratchet Baseline\n"
    "#\n"
    "# Frozen per-file counts of target-literal identifiers (language/provider\n"
    "# names hardcoded in a shared layer -- Decision D1, Invariant I1).\n"
    "# Any INCREASE in a file's count fails datrix/scripts/scan/check-import-boundaries.ps1\n"
    "# --check-target-literals. Decreases are always allowed and should be captured\n"
    "# by re-running with --update-baseline once a later change deletes an identifier\n"
    "# (the terminal state is 0 for every entry here).\n"
    "#\n"
    "# Format:\n"
    "#   [[baseline]]\n"
    '#   file = "path/relative/to/monorepo-root, forward slashes"\n'
    "#   count = <int>\n"
)


def write_target_literal_baseline(baseline_path: Path, counts: dict[str, int]) -> None:
    """Write ``counts`` to the baseline TOML as ``[[baseline]] file=... count=...``
    entries, sorted by file for deterministic diffs.

    Args:
        baseline_path: Path to the target-literal baseline TOML file to write.
        counts: Mapping of relative file path (forward slashes) -> hit count.
    """
    write_count_baseline(
        baseline_path, counts, key_field="file", header=_TARGET_LITERAL_BASELINE_HEADER
    )


def check_target_literal_ratchet(
    current_counts: dict[str, int],
    baseline: dict[str, int],
) -> list[str]:
    """One message per file whose target-literal count rose above its
    baseline, sorted by file path."""
    return tighten_only_messages(current_counts, baseline, "target-literal")


def check_identity_rules_hard_zero(
    hits_by_file: dict[Path, list[TargetLiteralHit]],
    baseline: dict[str, int],
    monorepo_root: Path,
) -> list[str]:
    """Hold the shared identity tree at a HARD ZERO for identity provider type rules.

    An identity provider type's issuer / JWKS / audience rules belong to the package
    that integrates the provider and are resolved from the plugin registry; nothing
    under ``IDENTITY_RULES_HARD_ZERO_PREFIX`` may name an owned provider type (as a
    comparison, key, type check or import path) or an ``IdentityProvider`` member of
    one. Unlike the decrease-only ratchet, no baseline entry is admitted for that tree.

    Args:
        hits_by_file: The target-literal scan result.
        baseline: The frozen per-file counts.
        monorepo_root: Monorepo root for relative path reporting.

    Returns:
        One message per identity-rule hit in the tree, and one per baseline entry
        naming a file in it.
    """
    owned = _owned_identity_types()
    messages: list[str] = []
    for file_path, hits in sorted(hits_by_file.items()):
        rel = str(file_path.relative_to(monorepo_root)).replace("\\", "/")
        if not rel.startswith(IDENTITY_RULES_HARD_ZERO_PREFIX):
            continue
        for hit in hits:
            names_identity_type = hit.kind == "identity_provider_member" or (
                hit.kind in IDENTITY_RULE_KINDS and hit.matched_target in owned
            )
            if names_identity_type:
                messages.append(
                    f"{rel}:{hit.line_number}: identity provider type "
                    f"{hit.matched_target!r} is named here ({hit.kind}: {hit.identifier}); "
                    f"the shared identity tree holds no provider type's rules -- they belong "
                    f"to the package that integrates the provider (hard zero, no baseline)"
                )
    for rel in sorted(baseline):
        if rel.startswith(IDENTITY_RULES_HARD_ZERO_PREFIX):
            messages.append(
                f"{rel}: the target-literal baseline names a file in the shared identity "
                f"tree, which is held at hard zero -- delete the entry"
            )
    return messages


def _self_test_platform_token_build_fixture_monorepo(tmp_root: Path) -> Path:
    """Build a minimal isolated monorepo: one ``datrix-common`` package (no
    entry points -> classified SHARED by ``discover_shared_packages``) with
    a module carrying NO platform-token identifier, plus a target-literal
    baseline TOML freezing that file at count 0."""
    _self_test_write_manifest(
        tmp_root, "datrix-common", "datrix_common", entry_point_groups={}
    )
    package_src = tmp_root / "datrix-common" / "src" / "datrix_common"
    package_src.mkdir(parents=True, exist_ok=True)
    (package_src / "__init__.py").write_text("", encoding="utf-8")

    module_path = package_src / "sample_platform_neutral.py"
    module_path.write_text(
        "def resolve_something() -> None:\n    return None\n", encoding="utf-8"
    )

    config_dir = tmp_root / "datrix" / "scripts" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "target-literal-baseline.toml").write_text(
        "[[baseline]]\n"
        'file = "datrix-common/src/datrix_common/sample_platform_neutral.py"\n'
        "count = 0\n",
        encoding="utf-8",
    )
    return module_path


def _self_test_platform_token_run_cli(tmp_root: Path) -> subprocess.CompletedProcess[str]:
    """Run the boundary scan as a real subprocess against the isolated fixture."""
    return subprocess.run(
        [
            *CLI_COMMAND,
            "--base-dir",
            str(tmp_root),
            "--check-target-literals",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _self_test_platform_token_scanner() -> bool:
    """The I1 platform-token identifier/module-name shape match: a
    declaration named ``build_azure_thing`` is a ``platform_token_identifier``
    hit naming ``azure``; ``local_cache`` produces ZERO hits (the "local"
    English-word exclusion holds); a file at ``deployment/azure_naming.py``
    is a ``platform_token_module_name`` hit naming ``azure``; every excluded
    token is still a registered platform name (a stale exclusion fails
    loud) -- PLUS a real CLI mutation proof (plant ``build_azure_thing`` in
    a derived shared-package fixture, prove the I1 ratchet fires, prove it
    clears on revert), mirroring the G2 shared-target-name ratchet's own
    CLI-mutation non-vacuity shape rather than an in-process call alone."""
    report_step(
        "Self-test 21/24: platform-token identifier/module-name shape match "
        "(direct scanner assertions + CLI mutation non-vacuity)"
    )
    ok = True

    scratch_dir = _SELF_TEST_SCRATCH_ROOT / f"platform-token-scanner-{uuid.uuid4().hex}"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    try:
        platform_names = _platform_token_vocabulary()
        target_literal_names = _target_literal_vocabulary()

        azure_file = scratch_dir / "azure_thing.py"
        azure_file.write_text(
            "def build_azure_thing() -> None:\n    return None\n", encoding="utf-8"
        )
        azure_hits = scan_file_for_target_literals(
            azure_file, scratch_dir, platform_names, target_literal_names
        )
        ok &= _check(
            "build_azure_thing() is a platform_token_identifier hit naming 'azure'",
            any(
                h.kind == "platform_token_identifier" and h.matched_target == "azure"
                for h in azure_hits
            ),
        )

        local_file = scratch_dir / "local_helper.py"
        local_file.write_text("local_cache: dict = {}\n", encoding="utf-8")
        local_hits = scan_file_for_target_literals(
            local_file, scratch_dir, platform_names, target_literal_names
        )
        ok &= _check(
            "a module-level 'local_cache' declaration produces ZERO hits -- "
            "'local' is excluded from the platform-token vocabulary",
            local_hits == [],
        )

        module_name_dir = scratch_dir / "deployment"
        module_name_dir.mkdir(parents=True, exist_ok=True)
        module_name_file = module_name_dir / "azure_naming.py"
        module_name_file.write_text("VALUE = 1\n", encoding="utf-8")
        module_name_hits = scan_file_for_target_literals(
            module_name_file, scratch_dir, platform_names, target_literal_names
        )
        ok &= _check(
            "deployment/azure_naming.py is a platform_token_module_name hit naming 'azure'",
            any(
                h.kind == "platform_token_module_name" and h.matched_target == "azure"
                for h in module_name_hits
            ),
        )

        ok &= _check(
            "every _PLATFORM_TOKEN_EXCLUSIONS member is a registered platform name "
            "(a stale exclusion for a retired platform fails loud)",
            _PLATFORM_TOKEN_EXCLUSIONS <= frozenset(registered_platform_names()),
        )
    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)

    tmp_root = _SELF_TEST_SCRATCH_ROOT / f"platform-token-cli-{uuid.uuid4().hex}"
    tmp_root.mkdir(parents=True, exist_ok=True)
    try:
        module_path = _self_test_platform_token_build_fixture_monorepo(tmp_root)

        clean_result = _self_test_platform_token_run_cli(tmp_root)
        ok &= _check(
            f"clean shared-package fixture exits 0, got {clean_result.returncode}",
            clean_result.returncode == 0,
        )

        module_path.write_text(
            "def build_azure_thing() -> None:\n    return None\n", encoding="utf-8"
        )
        failing_result = _self_test_platform_token_run_cli(tmp_root)
        ok &= _check(
            f"planted build_azure_thing exits 1, got {failing_result.returncode}",
            failing_result.returncode == 1,
        )
        ok &= _check(
            "failure output names the mutated file",
            "sample_platform_neutral.py" in failing_result.stdout,
        )
        ok &= _check(
            "failure output names the exact count delta (0 -> 1)",
            "increased from baseline 0 to 1" in failing_result.stdout,
        )

        module_path.write_text(
            "def resolve_something() -> None:\n    return None\n", encoding="utf-8"
        )
        reverted_result = _self_test_platform_token_run_cli(tmp_root)
        ok &= _check(
            f"reverting the mutation clears the failure, got exit {reverted_result.returncode}",
            reverted_result.returncode == 0,
        )
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)

    return ok


def _self_test_target_literal_new_kinds() -> bool:
    """The key/comparand/isinstance/import-path target-literal shapes:
    direct scanner assertions for every one-hit and zero-hit case the design
    enumerates, the own-language exclusion holding for all three new kinds
    inside a language-core package and NOT holding for an ordinary shared
    package -- PLUS a real CLI mutation proof (plant a bare `== "python"`
    comparison in a derived shared-package fixture, prove the ratchet
    fires, prove it clears on revert), reusing
    ``_self_test_platform_token_build_fixture_monorepo`` /
    ``_self_test_platform_token_run_cli`` (the fixture shape is generic to
    any target-literal-ratchet mutation, not specific to the platform-token
    kinds)."""
    report_step(
        "Self-test 22/24: target-literal key/comparand/isinstance/import-path "
        "shapes (direct scanner assertions + own-language exclusion + CLI "
        "mutation non-vacuity)"
    )
    ok = True

    scratch_dir = _SELF_TEST_SCRATCH_ROOT / f"target-literal-new-kinds-{uuid.uuid4().hex}"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    try:
        platform_names = _platform_token_vocabulary()
        target_literal_names = _target_literal_vocabulary()
        new_kinds = ("target_name_literal", "target_type_check", "target_module_import")

        def _scan(relative_name: str, source: str) -> list[TargetLiteralHit]:
            file_path = scratch_dir / relative_name
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(source, encoding="utf-8")
            return scan_file_for_target_literals(
                file_path, scratch_dir, platform_names, target_literal_names
            )

        # One-hit cases.
        get_hits = _scan("dot_get.py", 'def f(configs):\n    return configs.get("azure")\n')
        ok &= _check(
            "configs.get('azure') is one target_name_literal hit naming 'azure'",
            sum(
                1
                for h in get_hits
                if h.kind == "target_name_literal" and h.matched_target == "azure"
            )
            == 1,
        )

        eq_hits = _scan(
            "eq_compare.py", 'def f(language):\n    return language.value == "python"\n'
        )
        ok &= _check(
            "language.value == 'python' is one target_name_literal hit naming 'python'",
            sum(
                1
                for h in eq_hits
                if h.kind == "target_name_literal" and h.matched_target == "python"
            )
            == 1,
        )

        in_hits = _scan(
            "in_compare.py", 'def f(x):\n    return x in ("python", "typescript")\n'
        )
        ok &= _check(
            'x in ("python", "typescript") is exactly two target_name_literal hits',
            sum(1 for h in in_hits if h.kind == "target_name_literal") == 2,
        )

        subscript_hits = _scan("subscript.py", 'def f(m):\n    return m["docker"]\n')
        ok &= _check(
            "m['docker'] is one target_name_literal hit naming 'docker'",
            sum(
                1
                for h in subscript_hits
                if h.kind == "target_name_literal" and h.matched_target == "docker"
            )
            == 1,
        )

        dict_hits = _scan("dict_key.py", 'VALUE = {"typescript": 1}\n')
        ok &= _check(
            "{'typescript': 1} is one target_name_literal hit naming 'typescript'",
            sum(
                1
                for h in dict_hits
                if h.kind == "target_name_literal" and h.matched_target == "typescript"
            )
            == 1,
        )

        isinstance_hits = _scan(
            "isinstance_azure.py",
            "class AzurePlatformConfig:\n    pass\n\n\n"
            "def f(c):\n    return isinstance(c, AzurePlatformConfig)\n",
        )
        ok &= _check(
            "isinstance(c, AzurePlatformConfig) is one target_type_check hit naming 'azure'",
            sum(
                1
                for h in isinstance_hits
                if h.kind == "target_type_check" and h.matched_target == "azure"
            )
            == 1,
        )

        import_hits = _scan(
            "module_import.py", "from datrix_common.config.platform.docker import X\n"
        )
        ok &= _check(
            "importing datrix_common.config.platform.docker is one "
            "target_module_import hit naming 'docker'",
            sum(
                1
                for h in import_hits
                if h.kind == "target_module_import" and h.matched_target == "docker"
            )
            == 1,
        )

        # Zero-hit cases.
        docstring_hits = _scan("docstring.py", '"""Mentions python in prose, not code."""\n')
        ok &= _check(
            "a module docstring mentioning 'python' produces ZERO new-kind hits",
            not any(h.kind in new_kinds for h in docstring_hits),
        )

        log_hits = _scan(
            "log_call.py",
            "import logging\n\nlogger = logging.getLogger(__name__)\n\n\n"
            'def f():\n    logger.info("python")\n',
        )
        ok &= _check(
            "logger.info('python') produces ZERO new-kind hits",
            not any(h.kind in new_kinds for h in log_hits),
        )

        substring_hits = _scan("substring_compare.py", 'def f(x):\n    return "pythonic" == x\n')
        ok &= _check(
            "'pythonic' == x produces ZERO hits -- substring, not exact equality",
            not any(h.kind in new_kinds for h in substring_hits),
        )

        isinstance_base_hits = _scan(
            "isinstance_base.py",
            "class BasePlatformConfig:\n    pass\n\n\n"
            "def f(c):\n    return isinstance(c, BasePlatformConfig)\n",
        )
        ok &= _check(
            "isinstance(c, BasePlatformConfig) produces ZERO target_type_check hits "
            "-- no vocabulary token as a segment",
            not any(h.kind == "target_type_check" for h in isinstance_base_hits),
        )

        local_segment_hits = _scan(
            "isinstance_local_segment.py",
            "class VariableDeclaration:\n    pass\n\n\n"
            "_LOCAL_BINDERS = (VariableDeclaration,)\n\n\n"
            "def f(c):\n    return isinstance(c, _LOCAL_BINDERS)\n",
        )
        ok &= _check(
            "isinstance(c, _LOCAL_BINDERS) produces ZERO target_type_check hits "
            "-- 'local' as an identifier segment is the English word",
            not any(h.kind == "target_type_check" for h in local_segment_hits),
        )

        narrowing_source = (
            "class PythonRuntimeConfig:\n    pass\n\n\n"
            "def narrow(c: object) -> PythonRuntimeConfig:\n"
            "    assert isinstance(c, PythonRuntimeConfig)\n"
            "    return c\n"
        )
        narrowing_hits = _scan("isinstance_assert.py", narrowing_source)
        ok &= _check(
            "assert isinstance(c, PythonRuntimeConfig) produces ZERO target_type_check "
            "hits -- a narrowing assert selects no behaviour",
            not any(h.kind == "target_type_check" for h in narrowing_hits),
        )
        dispatch_hits = _scan(
            "isinstance_dispatch.py",
            narrowing_source
            + "\n\ndef dispatch(c: object) -> bool:\n"
            "    assert c is not None and isinstance(c, PythonRuntimeConfig)\n"
            "    if isinstance(c, PythonRuntimeConfig):\n"
            "        return True\n"
            "    return False\n",
        )
        ok &= _check(
            "an isinstance inside a compound assert test and one in an if test "
            "are exactly two target_type_check hits naming 'python'",
            sum(
                1
                for h in dispatch_hits
                if h.kind == "target_type_check" and h.matched_target == "python"
            )
            == 2,
        )

        import_base_hits = _scan(
            "module_import_base.py", "from datrix_common.config.platform.base import X\n"
        )
        ok &= _check(
            "importing datrix_common.config.platform.base produces ZERO "
            "target_module_import hits -- 'base' is not a vocabulary member",
            not any(h.kind == "target_module_import" for h in import_base_hits),
        )

        # Own-language exclusion: the SAME content, once inside
        # datrix_codegen_typescript_core (excluded) and once inside an
        # ordinary shared package (not excluded), for all three new kinds.
        core_source = (
            "class TypescriptPlatformConfig:\n    pass\n\n\n"
            "def f(configs, c):\n"
            '    configs.get("typescript")\n'
            "    isinstance(c, TypescriptPlatformConfig)\n"
            "    from datrix_common.config.platform.typescript import X\n"
        )
        core_file = (
            scratch_dir
            / "datrix-codegen-typescript-core"
            / "src"
            / "datrix_codegen_typescript_core"
            / "own_language.py"
        )
        core_file.parent.mkdir(parents=True, exist_ok=True)
        core_file.write_text(core_source, encoding="utf-8")
        core_hits = scan_file_for_target_literals(
            core_file, scratch_dir, platform_names, target_literal_names
        )
        ok &= _check(
            "a 'typescript' hit of all three new kinds is suppressed inside "
            "datrix_codegen_typescript_core (own-language exclusion)",
            not any(
                h.kind in new_kinds and h.matched_target == "typescript" for h in core_hits
            ),
        )

        other_file = scratch_dir / "datrix-common" / "src" / "datrix_common" / "own_language.py"
        other_file.parent.mkdir(parents=True, exist_ok=True)
        other_file.write_text(core_source, encoding="utf-8")
        other_hits = scan_file_for_target_literals(
            other_file, scratch_dir, platform_names, target_literal_names
        )
        ok &= _check(
            "the SAME 'typescript' hits are NOT suppressed inside any other package",
            sum(
                1
                for h in other_hits
                if h.kind in new_kinds and h.matched_target == "typescript"
            )
            == 3,
        )
    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)

    tmp_root = _SELF_TEST_SCRATCH_ROOT / f"target-literal-new-kinds-cli-{uuid.uuid4().hex}"
    tmp_root.mkdir(parents=True, exist_ok=True)
    try:
        module_path = _self_test_platform_token_build_fixture_monorepo(tmp_root)

        clean_result = _self_test_platform_token_run_cli(tmp_root)
        ok &= _check(
            f"clean shared-package fixture exits 0, got {clean_result.returncode}",
            clean_result.returncode == 0,
        )

        module_path.write_text(
            'def resolve_something(language) -> bool:\n    return language == "python"\n',
            encoding="utf-8",
        )
        failing_result = _self_test_platform_token_run_cli(tmp_root)
        ok &= _check(
            f"planted == 'python' comparison exits 1, got {failing_result.returncode}",
            failing_result.returncode == 1,
        )
        ok &= _check(
            "failure output names the mutated file",
            "sample_platform_neutral.py" in failing_result.stdout,
        )
        ok &= _check(
            "failure output names the exact count delta (0 -> 1)",
            "increased from baseline 0 to 1" in failing_result.stdout,
        )

        module_path.write_text(
            "def resolve_something() -> None:\n    return None\n", encoding="utf-8"
        )
        reverted_result = _self_test_platform_token_run_cli(tmp_root)
        ok &= _check(
            f"reverting the mutation clears the failure, got exit {reverted_result.returncode}",
            reverted_result.returncode == 0,
        )
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)

    return ok


def _self_test_identity_provider_rules() -> bool:
    """Identity provider type rules stay out of the shared layers.

    Direct scanner assertions for the owned-type string literal and the
    ``IdentityProvider`` member kind (planted ``provider_type == <owned type>`` and an
    ``IdentityProviderType.<built-in external member>`` read; no owned type is a member),
    the zero-hit cases (a docstring, the
    credential kind ``apiKey``, the vocabulary's own home files), and the hard-zero
    check over the shared identity tree."""
    report_step(
        "Self-test 25/25: identity provider type rules (owned-type literal, "
        "IdentityProvider member, home-file exemption, hard zero)"
    )
    ok = True
    owned = sorted(_owned_identity_types())
    ok &= _check(
        "at least two identity provider types are owned by installed platform packages "
        "(the vocabulary is derived, and non-vacuous)",
        len(owned) >= 2,
    )
    if len(owned) < 2:
        return False
    first = owned[0]
    members = {m.value: m.name for m in ConfigIdentityProvider}
    scratch_dir = _SELF_TEST_SCRATCH_ROOT / f"identity-rules-{uuid.uuid4().hex}"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    try:
        platform_names = _platform_token_vocabulary()
        target_literal_names = _target_literal_vocabulary()
        ok &= _check(
            "the target-literal vocabulary carries every owned identity provider type",
            frozenset(owned) <= target_literal_names,
        )

        def _scan(relative_name: str, source: str) -> list[TargetLiteralHit]:
            file_path = scratch_dir / relative_name
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(source, encoding="utf-8")
            return scan_file_for_target_literals(
                file_path, scratch_dir, platform_names, target_literal_names
            )

        compare_hits = _scan(
            "owned_compare.py", f'def f(provider_type):\n    return provider_type == "{first}"\n'
        )
        ok &= _check(
            f"provider_type == '{first}' is one target_name_literal hit naming it",
            sum(
                1
                for h in compare_hits
                if h.kind == "target_name_literal" and h.matched_target == first
            )
            == 1,
        )

        import_line = (
            "from datrix_common.config.datasource.identity_config import "
            "IdentityProvider as IdentityProviderType\n\n\n"
        )
        ok &= _check(
            "no owned provider type is an IdentityProvider member (the .dcfg vocabulary "
            "is open-world: an owned type is the owning package's string)",
            not (frozenset(owned) & frozenset(members)),
        )
        external_member = members[ConfigIdentityProvider.EXTERNAL.value]
        member_hits = _scan(
            "external_member.py",
            import_line
            + "def f(t):\n"
            + f"    return t is IdentityProviderType.{external_member}\n",
        )
        ok &= _check(
            "an IdentityProviderType.<built-in external member> read is exactly one "
            "identity_provider_member hit (an import alias is followed)",
            sum(1 for h in member_hits if h.kind == "identity_provider_member") == 1,
        )

        docstring_hits = _scan("owned_docstring.py", f'"""Mentions {first} in prose."""\n')
        ok &= _check(
            "an owned type named in a docstring is ZERO identity-kind hits",
            not any(h.kind in IDENTITY_RULE_KINDS for h in docstring_hits),
        )

        api_key_hits = _scan(
            "api_key_member.py",
            import_line
            + f"def f(t):\n    return t is IdentityProviderType.{members['apiKey']}\n",
        )
        ok &= _check(
            "the credential kind apiKey is NOT an identity_provider_member hit",
            not any(h.kind == "identity_provider_member" for h in api_key_hits),
        )

        home_hits = _scan(
            "config/datasource/identity_config.py",
            import_line + f'def f(t):\n    return t == "{first}" or t is IdentityProviderType.{external_member}\n',
        )
        ok &= _check(
            "the vocabulary's own home file (identity_config.py) is exempt from both kinds",
            not any(h.kind in IDENTITY_RULE_KINDS for h in home_hits),
        )

        identity_tree_file = (
            scratch_dir / "datrix-common" / "src" / "datrix_common" / "identity" / "rules.py"
        )
        identity_tree_file.parent.mkdir(parents=True, exist_ok=True)
        identity_tree_file.write_text(
            f'def f(provider_type):\n    return provider_type == "{first}"\n', encoding="utf-8"
        )
        tree_hits = scan_file_for_target_literals(
            identity_tree_file, scratch_dir, platform_names, target_literal_names
        )
        hard_zero = check_identity_rules_hard_zero(
            {identity_tree_file: tree_hits}, {}, scratch_dir
        )
        ok &= _check(
            "an owned type compared inside the shared identity tree is a hard-zero failure",
            len(hard_zero) == 1 and first in hard_zero[0],
        )
        baseline_message = check_identity_rules_hard_zero(
            {}, {"datrix-common/src/datrix_common/identity/rules.py": 1}, scratch_dir
        )
        ok &= _check(
            "a baseline entry naming a file in the shared identity tree is refused",
            len(baseline_message) == 1,
        )
        clean = check_identity_rules_hard_zero({}, {}, scratch_dir)
        ok &= _check("no hits and no baseline entries is clean", clean == [])
    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)
    return ok


def _self_test_central_name_collisions() -> bool:
    """The frozen-name kinds count the Datrix table or enum, never a third-party
    name spelled the same: ``tree_sitter.Language`` (imported by name or read off
    the module) is zero hits; the same name imported from a Datrix module, or
    relatively, is a hit; and a third-party import the module shadows with its
    own definition is still a hit."""
    report_step(
        "Self-test 26/26: frozen central names bound by a third-party import "
        "are collisions, not hits"
    )

    def _matches(source: str) -> list[tuple[str, CentralNameKind]]:
        tree = ast.parse(source)
        return [
            (identifier, kind)
            for identifier, _, kind in _central_name_matches(tree, _foreign_bound_names(tree))
        ]

    ok = _check(
        "Language imported from tree_sitter and used as annotation and call is ZERO hits",
        _matches(
            "from tree_sitter import Language\n"
            "def f(x: Language) -> Language:\n    return Language(x)\n"
        )
        == [],
    )
    ok &= _check(
        "tree_sitter.Language read off an imported third-party module is ZERO hits",
        _matches("import tree_sitter\nLANG = tree_sitter.Language(1)\n") == [],
    )
    datrix_matches = _matches(
        "from datrix_common.enums import Language\n"
        "def f(x: Language) -> None:\n    return None\nY = Language.PYTHON\n"
    )
    ok &= _check(
        "Language imported from a Datrix module is two central_table_name hits and one "
        f"enum_member_qualified hit, got {datrix_matches}",
        sorted(datrix_matches)
        == [
            ("Language", "central_table_name"),
            ("Language", "central_table_name"),
            ("Language.PYTHON", "enum_member_qualified"),
        ],
    )
    ok &= _check(
        "Language imported relatively is a hit",
        _matches("from .enums import Language\nX = Language\n")
        == [("Language", "central_table_name")],
    )
    ok &= _check(
        "a third-party Language the module shadows with its own class stays a hit "
        "(the definition and the reference)",
        len(_matches("from tree_sitter import Language\nclass Language:\n    pass\nX = Language\n"))
        == 2,
    )
    return ok


def self_test_checks() -> list[NamedCheck]:
    """The target-literal scanner's self-tests, each a check the CLI's ``--self-test`` runs."""
    return [
        self_test_check(_self_test_platform_token_scanner),
        self_test_check(_self_test_target_literal_new_kinds),
        self_test_check(_self_test_identity_provider_rules),
        self_test_check(_self_test_central_name_collisions),
    ]
