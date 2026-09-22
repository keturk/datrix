#!/usr/bin/env python3
"""Behaviour-parity gate: discovers every registered language (or platform)
package's module-level and class-method function definitions, groups them
into ROLES -- never by raw name, so a language token in a name can never
hide a parallel implementation -- classifies every role with two or more
member packages as ``identical``, ``same-behaviour``, or ``divergent``
using the behaviour-skeleton extractor, resolves each role to its owning
shared domain, reads the declared exemption surfaces, and fails exactly the
roles the language-axis behaviour-parity invariants say must fail.

A per-target difference in generator BEHAVIOUR -- what is read from the
model, what is validated, what is emitted -- is a defect with as many copies
as there are disagreeing packages, never a choice to adjudicate. No language
is the reference: when copies disagree, the reconciliation takes the
strongest behaviour on each axis (fails closed, reads everything the DSL
declares, most secure, most correct output), and this gate cannot know which
copy that is. It therefore names every group of disagreeing packages, never
one "lagging" side.

Two grouping keys, tried in order for every function:

1. **Signature role** -- the role-defining component of a signature is the
   PRODUCT it declares: a return annotation naming a type of the shared
   codegen layer (``datrix_codegen_common.*`` -- a frozen artifact context,
   a plan, a render result), found anywhere in the annotation (through
   ``list[...]``/``tuple[...]``/``dict[...]`` arguments, ``X | None`` unions
   and forward-reference strings). Every function producing the same shared
   product is one role regardless of name and regardless of which inputs it
   takes to build it: a ``Command`` plus a ``Service``, a ``ServicePaths``,
   a ``TypeResolver`` or a language-private transpiler core all describe
   the same job. Parameter types never enter the key -- measured on the
   live tree, they identify INPUTS, not jobs (every function taking a
   ``Service`` and returning a ``str`` is hundreds of different jobs), and
   a return type outside the shared codegen layer (``GeneratedFile``,
   ``TranspileResult``, a builtin) says nothing about which job either.
2. **Normalized-name role** -- for a function declaring no shared product,
   its bare name with this package's own declared name tokens
   (``LanguageCapabilityDeclaration.name_tokens`` plus the registered id on
   the language axis; the bare registered name(s) on the platform axis)
   stripped as whole ``_``-delimited segments.

Gate verdicts (language-axis invariants I1 and I2)
--------------------------------------------------
- ``identical`` and ``same-behaviour`` fail unless every member is a
  pre-binding adapter (recognized by AST shape in ``behaviour_skeleton``;
  there is no written exemption for this bucket).
- ``divergent`` is judged without a reference language. The role's member
  packages are partitioned into SKELETON GROUPS: two packages share a group
  when the sets of ``(behaviour skeleton, behaviour arity)`` pairs their
  members contribute to the role are equal. Every package that declares the
  construct ``unsupported(reason)`` on one of the declared surfaces below is
  set aside. The role PASSES iff at most one group remains; otherwise it
  FAILS with one reason naming every remaining group -- the gate cannot
  know which group carries the correct behaviour, so it names all of them.
  A role every member of which declares the construct unsupported passes (a
  declared hole everywhere) and is still reported.
- A failure counts toward the exit code only when the role's domain is in
  scope; every other role is reported and never fails (the migration-only
  scope below). The platform axis is measured, not reconciled: it is
  report-only and never fails.

Domain resolution ladder (first hit wins)
-----------------------------------------
1. A signature role's product type reverse-looked-up in the shared parity
   registry's rich context-type map, when it maps to exactly one domain id
   (the test-plan context every ``*_test`` domain binds maps to many and
   never resolves here).
2. The product type's defining module basename under
   ``datrix_codegen_common.context_models`` or
   ``datrix_codegen_common.orchestration.contexts`` -- ``_render_contexts`` /
   ``_contexts`` / ``_context`` suffix and ``persistence_`` prefix stripped
   -- when it is a universe id.
3. Every member's source module -- ``micro_generators/<id>.py``,
   ``hooks/<id>_hooks.py``, ``orchestration/<id>_context_builders.py`` or
   ``<id>_frozen_builders.py``, ``generators/<id>/...`` -- when every member
   resolves and all resolve to the SAME universe id.
4. The literal ``undomained``.

Membership is always tested against ``SHARED_CONTEXT_TYPES``: no domain id
is ever fabricated, and disagreeing members fall through to ``undomained``.

Declared exemption surfaces (a member package is set aside on ANY one)
----------------------------------------------------------------------
1. Its ``DomainDeclaration.status == "unsupported"`` for the role's domain
   (read through ``supported_domain_parity.stance_table_by_language``).
2. The role's domain is a key of its
   ``LanguageCapabilityDeclaration.on_demand_domains``.
3. Every member it contributes to the role is an ``@emit_adapter``-marked
   function (the decorator resolved through the member's own import table
   to the shared layer's ``emit_adapter``) whose emit-table rows all belong
   to builtin groups its ``builtin_group_stances`` declares ``unsupported``.

An ``undomained`` role admits only the third surface. Exemptions are
role-keyed -- renaming a function never touches one -- and no classification
file exists (invariant I11): the typed declaration on the plugin is the
only surface, and it records a capability hole, never a reason to behave
differently.

How surface 3 finds a language's emit tables: every module under the
language package's ``src/<import root>`` is imported
(``pkgutil.walk_packages`` with a raising ``onerror``) and every module-level
``EmitTable`` instance is collected by ``isinstance``, deduplicated by
identity. No per-language table variable name and no table-module path is
assumed: the tables live in differently-named variables
(``PYTHON_EMIT_TABLE``, ``DOTNET_EMIT_TABLE``, ...) and in more than one
module per package (a language's instance-call table can live beside its
expression visitor rather than in ``transpiler/emit_tables.py``). Each
registered emit callable is matched to the AST-scanned member by
``(resolved defining file, __qualname__)``, and the row's builtin group is
read from ``BUILTIN_REGISTRY``. An ``@emit_adapter``-marked member no table
registers is a failure naming the member, never a skip.

Scope (migration-only)
----------------------
``--scope <id>[,<id>...]`` -- universe ids plus the literal ``undomained`` --
overrides ``datrix/scripts/config/behaviour-parity-scope.json``'s ``domains``
list, read only when ``--scope`` is absent. ``--buckets <id>[,<id>...]`` --
verdict names (``identical``, ``same-behaviour``, ``divergent``) --
overrides the file's ``buckets`` list the same way, gating every role of
that verdict across EVERY domain regardless of ``domains``/``--scope``. A
role is in scope when either half admits it. File present: its ``domains``
list is the domain scope (empty means no role fails by domain) and its
``buckets`` list (absent key means none) is the bucket scope. File absent:
every domain is in scope and no bucket is -- the hard-zero end state once
the migration is over. An unknown id in either place is a usage error naming
the valid options.

Fail-closed rule: an unparseable file, an unparseable string annotation, a
member the skeleton extractor cannot classify, an ``@emit_adapter`` member
with no row, or an emit callable without a usable identity is a reported
failure naming the member -- never a skip.

Exit codes: 0 no in-scope failing role; 1 at least one in-scope failing
role; 2 usage error, discovery/parse failure, or self-test failure.
``--axis platforms`` and ``--report-only`` render the report and exit 0.

Usage:
    python behaviour_parity.py --self-test
    python behaviour_parity.py --axis languages [--scope queue,cache] [--buckets identical] [--debug]
    python behaviour_parity.py --axis languages --report-only [--debug]
    python behaviour_parity.py --axis platforms [--debug]
"""

from __future__ import annotations

import argparse
import ast
import dataclasses
import functools
import importlib
import json
import logging
import pkgutil
import sys
import tempfile
import textwrap
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import CodeType, MappingProxyType
from typing import Final, Literal, TypeVar

_LIBRARY_DIR = Path(__file__).resolve().parent.parent
if _LIBRARY_DIR.exists() and str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from datrix_codegen_common.parity.domain_declaration import DomainDeclaration  # noqa: E402
from datrix_codegen_common.parity.domain_registry import (  # noqa: E402
    _RICH_CONTEXT_TYPES,
    SHARED_CONTEXT_TYPES,
)
from datrix_codegen_common.transpiler.builtin_registry import (  # noqa: E402
    BUILTIN_REGISTRY,
    ArityContract,
    BuiltinDecl,
    BuiltinGroup,
    BuiltinKey,
    Receiver,
)
from datrix_codegen_common.transpiler.emit_dsl import (  # noqa: E402
    KNOWN_CHAIN_STEPS,
    EmitTable,
    emit_adapter,
    emit_decl,
)
from datrix_common.plugin.capability_resolution import declaration_for_language  # noqa: E402
from datrix_common.plugin.language_capability import BuiltinGroupStance  # noqa: E402
from shared.registered_targets import (  # noqa: E402
    AXIS_LANGUAGES,
    AXIS_PLATFORMS,
    DATRIX_DIR,
    WORKSPACE_ROOT,
    discover_all_other_package_src_dirs,
    discover_all_package_locations,
    discover_target_package_src_dirs,
    registered_language_names,
    registered_platform_names,
)

from test.behaviour_skeleton import (  # noqa: E402
    FunctionSource,
    SkeletonError,
    behaviour_arity,
    behaviour_skeleton,
    build_import_table,
    is_pre_binding_adapter,
    is_rendering_leaf,
    normalized_source,
    parse_module_or_raise,
    plumbing_parameter_names,
)
from test.supported_domain_parity import stance_table_by_language  # noqa: E402

logger = logging.getLogger(__name__)

EXIT_OK: Final[int] = 0
#: At least one role whose domain is in scope fails the gate.
EXIT_FAIL: Final[int] = 1
#: Also argparse's own usage-error exit code: a failed self-test, a
#: single-package axis, an unknown scope or bucket id, and a
#: parse/discovery failure all mean "nothing was proven".
EXIT_USAGE: Final[int] = 2

_MIN_PACKAGES_FOR_COMPARISON: Final[int] = 2
#: Must match ``shared.registered_targets``' fold separator -- kept as a local
#: literal rather than importing that module's private constant.
_LABEL_JOIN_SEPARATOR: Final[str] = "+"
#: A return annotation names a shared PRODUCT when the type it resolves to,
#: through the function's own file's import table, lives in the shared
#: codegen layer -- the same layer the pre-binding-adapter exemption
#: recognizes a delegation target in. Types of ``datrix_common`` (the AST,
#: config, paths, ``GeneratedFile``, ``TranspileResult``) are the pipeline's
#: shared INPUTS and generic outputs and never key a role.
_SHARED_CODEGEN_LAYER_PREFIX: Final[str] = "datrix_codegen_common."
#: ``typing.Literal``'s subscript holds VALUES, not types; its arguments are
#: never resolved as annotations.
_LITERAL_QUALIFIED_NAMES: Final[frozenset[str]] = frozenset({"typing.Literal", "typing_extensions.Literal"})
#: ``ast.stmt`` attribute names whose value is a statement list this scanner
#: descends into to find a def nested inside a non-function, non-class
#: container (If/While/For/With/Try main body + else + finally).
_CONTAINER_BODY_ATTRS: Final[tuple[str, ...]] = ("body", "orelse", "finalbody")
_NAME_SEGMENT_SEPARATOR: Final[str] = "_"
#: Bound on ``_resolve_static_reexport``'s recursion -- a re-export chases at
#: most one or two package ``__init__`` hops in practice; this only guards
#: against an accidental import cycle, never a real resolution depth.
_MAX_REEXPORT_HOPS: Final[int] = 5

_FunctionDefNode = ast.FunctionDef | ast.AsyncFunctionDef
#: The three bucket labels, exactly as printed and accepted (invariant I12:
#: these three spellings are the whole verdict vocabulary).
Verdict = Literal["identical", "same-behaviour", "divergent"]
_VERDICT_IDENTICAL: Final[Verdict] = "identical"
_VERDICT_SAME_BEHAVIOUR: Final[Verdict] = "same-behaviour"
_VERDICT_DIVERGENT: Final[Verdict] = "divergent"
#: One member's measured behaviour: its skeleton and its role-level arity --
#: the pair ``_classify_role`` compares and ``skeleton_groups`` partitions on.
BehaviourPair = tuple[str, int]

#: The domain of a role the resolution ladder maps to no shared domain id.
#: Also a valid ``--scope`` id, so the roles that resolve nowhere can be gated.
UNDOMAINED: Final[str] = "undomained"
_SCOPE_SEPARATOR: Final[str] = ","
_SCOPE_FILE_DOMAINS_KEY: Final[str] = "domains"
_SCOPE_FILE_BUCKETS_KEY: Final[str] = "buckets"
#: The only valid --buckets / scope-file "buckets" entries: the three verdict
#: names a role can classify as. Gating a bucket fails every role of that
#: verdict across EVERY domain, independent of the domains list.
_VALID_BUCKET_IDS: Final[frozenset[str]] = frozenset(
    {_VERDICT_IDENTICAL, _VERDICT_SAME_BEHAVIOUR, _VERDICT_DIVERGENT}
)
#: The migration-only scope list; read only when ``--scope`` is absent, and
#: only while it exists (its absence means every domain is in scope).
BEHAVIOUR_PARITY_SCOPE_PATH: Final[Path] = DATRIX_DIR / "scripts" / "config" / "behaviour-parity-scope.json"
#: The declared-status literal shared by ``DomainDeclaration`` and
#: ``BuiltinGroupStance`` that sets a member package aside.
_UNSUPPORTED_STATUS: Final[str] = "unsupported"
#: The marker decorator, resolved structurally through a member's own import
#: table -- derived from the real callable so a rename of the shared layer's
#: symbol fails this constant rather than silently matching nothing.
_EMIT_ADAPTER_QUALIFIED_NAME: Final[str] = f"{emit_adapter.__module__}.{emit_adapter.__qualname__}"
#: Only a product type defined under one of these shared modules is eligible
#: for ladder step 2 (module-basename resolution).
_ELIGIBLE_CONTEXT_MODULE_PREFIXES: Final[tuple[str, ...]] = (
    "datrix_codegen_common.context_models.",
    "datrix_codegen_common.orchestration.contexts.",
)
#: Longest first: ``pubsub_render_contexts`` must strip ``_render_contexts``
#: (leaving ``pubsub``), never the shorter ``_contexts`` it also ends with.
_CONTEXT_MODULE_SUFFIXES: Final[tuple[str, ...]] = ("_render_contexts", "_contexts", "_context")
_CONTEXT_MODULE_PREFIX: Final[str] = "persistence_"
#: Ladder step 3: the four owning-module shapes a member's source path spells
#: a domain-id candidate with. The candidate is always checked against the
#: universe afterwards; the shapes never fabricate an id.
_PY_SUFFIX: Final[str] = ".py"
_MICRO_GENERATORS_DIR: Final[str] = "micro_generators"
_HOOKS_DIR: Final[str] = "hooks"
_HOOKS_MODULE_SUFFIX: Final[str] = "_hooks.py"
_ORCHESTRATION_DIR: Final[str] = "orchestration"
_ORCHESTRATION_MODULE_SUFFIXES: Final[tuple[str, ...]] = ("_context_builders.py", "_frozen_builders.py")
_GENERATORS_DIR: Final[str] = "generators"

#: ``(resolved defining file, __qualname__)`` -- the identity an AST-scanned
#: member and a registered emit callable are matched on.
AdapterIdentity = tuple[Path, str]
_NO_ADAPTERS: Final[Mapping[AdapterIdentity, frozenset[str]]] = MappingProxyType({})
_NO_GROUP_STANCES: Final[Mapping[str, BuiltinGroupStance]] = MappingProxyType({})
_DeclaredValue = TypeVar("_DeclaredValue")


# ---------------------------------------------------------------------------
# Role keys
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SignatureRole:
    """Every function whose signature declares this shared product -- the
    fully-qualified shared-codegen-layer type its return annotation names --
    is one role, regardless of name and of the inputs it takes."""

    product_type: str


@dataclass(frozen=True)
class NameRole:
    """A role for a function declaring no shared product: its bare name with
    its own package's name tokens stripped."""

    normalized_name: str


RoleKey = SignatureRole | NameRole


@dataclass(frozen=True)
class RoleVerdict:
    """One role's classification, naming every member by ``package:file:line``.

    ``group_and_classify_roles`` leaves ``domain`` as ``None`` -- grouping
    and classification never resolve a domain; ``evaluate_role`` fills it in
    from the resolution ladder (``resolve_domain``) and records the filled-in
    verdict on its ``RoleEvaluation``.
    """

    role_key: RoleKey
    kind: Literal["signature", "name"]
    domain: str | None
    verdict: Verdict
    members: tuple[FunctionSource, ...]
    adapter_exempt: bool
    rendering_leaf_exempt: bool


# ---------------------------------------------------------------------------
# Token vocabulary
# ---------------------------------------------------------------------------


def tokens_for(axis: str, label: str) -> frozenset[str]:
    """The name-token vocabulary for one registered target label.

    On the language axis: ``declaration_for_language(name).name_tokens |
    {name}`` for every registered name folded into *label*. On the platform
    axis: the bare registered name(s) only -- platform declarations carry no
    ``name_tokens`` field.

    Args:
        axis: ``AXIS_LANGUAGES`` or ``AXIS_PLATFORMS``.
        label: A ``discover_target_package_src_dirs`` label -- a single
            registered name, or several joined by ``_LABEL_JOIN_SEPARATOR``
            when they share one package.

    Returns:
        The frozenset of lowercase ``_``-segment tokens identifying this
        target for normalized-name grouping.
    """
    names = label.split(_LABEL_JOIN_SEPARATOR)
    if axis != AXIS_LANGUAGES:
        return frozenset(names)
    tokens: set[str] = set()
    for name in names:
        tokens |= declaration_for_language(name).name_tokens | {name}
    return frozenset(tokens)


def normalized_name(bare_name: str, tokens: frozenset[str]) -> str:
    """*bare_name* with every whole ``_``-delimited segment equal to a token
    in *tokens* removed, rejoined with ``_``.

    A private helper's leading underscore produces one empty first segment,
    which matches no token and is kept, so ``_py_coerce`` normalizes to
    ``_coerce`` and stays distinct from a public ``coerce``. A name made of
    nothing but tokens (``def python(self)``) has nothing left to identify
    it and keeps its bare spelling rather than collapsing into an empty name
    shared with every other such function.

    Args:
        bare_name: The function/method's bare name.
        tokens: This package's token vocabulary (``tokens_for``'s result).

    Returns:
        The token-stripped name.
    """
    segments = bare_name.split(_NAME_SEGMENT_SEPARATOR)
    kept = [segment for segment in segments if segment.lower() not in tokens]
    if not any(kept):
        return bare_name
    return _NAME_SEGMENT_SEPARATOR.join(kept)


# ---------------------------------------------------------------------------
# Annotation resolution (signature-role key)
# ---------------------------------------------------------------------------


def _qualified_name_of(node: ast.expr, import_table: dict[str, str]) -> str | None:
    """Resolve a bare ``Name`` or a ``Name``-rooted attribute chain
    (``contexts.CqrsCommandContext``, ``pkg.sub.Type``) to a fully-qualified
    name via *import_table*.

    A bare name absent from the import table is a builtin or a type defined
    in the same module -- its own spelling IS its qualified name, and it is
    never shared-typed. ``None`` means the expression is neither shape (a
    call, a subscript, a chain not rooted at a name) or is a chain whose root
    is not an import.

    Args:
        node: The expression to resolve (an annotation root).
        import_table: ``{local name: fully-qualified "module.attr"}``.

    Returns:
        The fully-qualified name, or ``None`` for an unresolvable shape.
    """
    if isinstance(node, ast.Name):
        if node.id in import_table:
            return import_table[node.id]
        return node.id
    attrs: list[str] = []
    while isinstance(node, ast.Attribute):
        attrs.append(node.attr)
        node = node.value
    if not attrs or not isinstance(node, ast.Name) or node.id not in import_table:
        return None
    return ".".join([import_table[node.id], *reversed(attrs)])


def _parse_string_annotation(annotation: ast.Constant) -> ast.expr:
    """Re-parse a forward-reference string annotation (``"Command"``) as an
    expression.

    Args:
        annotation: A string ``Constant`` used as an annotation.

    Returns:
        The parsed expression.

    Raises:
        SkeletonError: If the string is not a parseable expression -- an
            annotation this scanner cannot classify is a failure, never a
            silently unshared type.
    """
    text = str(annotation.value)
    try:
        return ast.parse(text, mode="eval").body
    except SyntaxError as exc:
        raise SkeletonError(
            f"String annotation {text!r} at line {annotation.lineno} does not parse as an "
            f'expression: {exc}. Expected a forward reference such as "Command" or '
            f'"list[Command]". Fix: spell the annotation as a valid type expression.'
        ) from exc


def _is_literal_subscript(node: ast.Subscript, import_table: dict[str, str]) -> bool:
    """Whether *node* is ``Literal[...]`` -- a value subscript whose
    arguments are never types."""
    qualified = _qualified_name_of(node.value, import_table)
    return qualified in _LITERAL_QUALIFIED_NAMES


def _subscript_type_arguments(node: ast.Subscript) -> list[ast.expr]:
    """The type arguments of a subscripted annotation in source order
    (``list[X]`` -> ``[X]``; ``dict[K, V]`` -> ``[K, V]``): generic
    containers are transparent to the product key."""
    subscript = node.slice
    if isinstance(subscript, ast.Tuple):
        return list(subscript.elts)
    return [subscript]


def shared_product_type(annotation: ast.expr | None, import_table: dict[str, str]) -> str | None:
    """The fully-qualified shared-codegen-layer type *annotation* names --
    the product a signature declares -- or ``None`` if it names none.

    Searches the annotation depth-first in source order: a forward-reference
    string is re-parsed, a generic container's type arguments are searched
    in turn (so ``list[X]``, ``tuple[X, ...]`` and ``dict[str, X]`` all
    declare ``X``), a ``X | None`` union searches both sides, and a
    ``Literal[...]`` declares nothing. A language-private type, a
    ``datrix_common`` type, a builtin and a missing annotation are all
    ``None``: not a shared product.

    Args:
        annotation: The ``FunctionDef.returns`` expression (or any annotation
            expression), or ``None`` if unannotated.
        import_table: The function's own file's import table.

    Returns:
        The fully-qualified shared product type name, or ``None``.

    Raises:
        SkeletonError: If a string annotation does not parse.
    """
    if annotation is None:
        return None
    if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
        annotation = _parse_string_annotation(annotation)
    if isinstance(annotation, ast.Subscript):
        if _is_literal_subscript(annotation, import_table):
            return None
        return _first_shared_product_type(_subscript_type_arguments(annotation), import_table)
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        return _first_shared_product_type([annotation.left, annotation.right], import_table)
    resolved = _qualified_name_of(annotation, import_table)
    if resolved is not None and resolved.startswith(_SHARED_CODEGEN_LAYER_PREFIX):
        return _resolve_static_reexport(resolved)
    return None


def _first_shared_product_type(candidates: list[ast.expr], import_table: dict[str, str]) -> str | None:
    for candidate in candidates:
        product = shared_product_type(candidate, import_table)
        if product is not None:
            return product
    return None


# ---------------------------------------------------------------------------
# Re-export canonicalization (two files importing the same shared type
# through different paths must key the identical SignatureRole)
# ---------------------------------------------------------------------------


@functools.cache
def _package_src_locations() -> Mapping[str, Path]:
    """``{import_name: src_dir}`` for every discovered ``datrix-*`` package.

    The same generic, on-disk filesystem discovery every other cross-package
    scanner in this module already uses (never a hardcoded
    ``datrix-codegen-<x>`` path) -- computed once per process and reused by
    every ``_resolve_static_reexport`` call.
    """
    return discover_all_package_locations(WORKSPACE_ROOT)


def _locate_module_file(module_name: str) -> tuple[Path, Path] | None:
    """The on-disk ``(src_dir, file_path)`` backing *module_name*, or
    ``None`` if its top-level import root is not a discovered on-disk
    package, or neither a package ``__init__.py`` nor a module ``.py`` file
    exists for it there.

    A synthetic module path a self-test fabricates purely in an import table
    (never written to disk) resolves here too: its top-level segment can
    still be a real package (e.g. ``datrix_codegen_common``), but the deeper
    path segments name no real file, so this returns ``None`` and the caller
    leaves the qualified name unchanged rather than guessing.

    Args:
        module_name: A dotted module path (e.g. ``"datrix_codegen_common.platform"``).

    Returns:
        ``(src_dir, file_path)`` for the resolved file, or ``None``.
    """
    parts = module_name.split(".")
    src_dir = _package_src_locations().get(parts[0])
    if src_dir is None:
        return None
    relative_parts = parts[1:]
    if not relative_parts:
        file_path = src_dir / "__init__.py"
        return (src_dir, file_path) if file_path.is_file() else None
    package_init = src_dir.joinpath(*relative_parts) / "__init__.py"
    if package_init.is_file():
        return src_dir, package_init
    module_file = src_dir.joinpath(*relative_parts[:-1], f"{relative_parts[-1]}.py")
    return (src_dir, module_file) if module_file.is_file() else None


def _defines_locally(module: ast.Module, attr_name: str) -> bool:
    """Whether *attr_name* is bound by a module-level class/function
    definition or assignment in *module* -- i.e. this module is where it is
    actually DEFINED, not merely re-exported from elsewhere."""
    for stmt in module.body:
        if isinstance(stmt, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and stmt.name == attr_name:
            return True
        if isinstance(stmt, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == attr_name for target in stmt.targets
        ):
            return True
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name) and stmt.target.id == attr_name:
            return True
    return False


def _resolve_static_reexport(qualified_name: str, *, _hops: int = 0) -> str:
    """Canonicalize *qualified_name* (``module.attr``) by following
    package-``__init__``-style re-exports back to the module that actually
    DEFINES the name -- purely by static AST inspection of files already on
    disk, never a real import.

    Two files that import the SAME shared type through different paths (one
    through a package's re-exporting ``__init__.py``, the other straight
    from the defining submodule) must key one identical ``SignatureRole``,
    or the role silently splits into two, each of which can then fall below
    the two-package comparison floor and vanish from the report -- exactly
    what happened to AWS's ``provision_queue``/``provision_serverless``
    before this canonicalization existed (AWS imported ``ManagedServicePlan``
    from ``datrix_codegen_common.platform``, Azure/Docker from
    ``datrix_codegen_common.platform.value_objects``; the two textually
    distinct qualified names hid AWS's declarations from the role Azure and
    Docker shared).

    Never a real import: a self-test's synthetic, unimportable module path
    (module docstring, case (e): "parsed as text; nothing is imported") must
    resolve identically whether or not this canonicalization runs, so a hop
    that cannot be resolved on disk leaves *qualified_name* unchanged rather
    than raising or guessing.

    Args:
        qualified_name: A dotted ``module.attr`` name already known to start
            with the shared codegen layer prefix.

    Returns:
        The canonical ``module.attr`` spelling, or *qualified_name*
        unchanged if it is already canonical, is not backed by an on-disk
        file, or the hop limit is reached.

    Raises:
        SkeletonError: Propagates from ``parse_module_or_raise`` if a
            resolved on-disk file cannot be parsed -- a real file this
            canonicalization can locate is held to the same fail-closed
            standard as every other file this gate reads.
    """
    if _hops >= _MAX_REEXPORT_HOPS:
        return qualified_name
    module_name, _, attr_name = qualified_name.rpartition(".")
    if not module_name:
        return qualified_name
    located = _locate_module_file(module_name)
    if located is None:
        return qualified_name
    src_dir, file_path = located
    module = parse_module_or_raise(file_path)
    if _defines_locally(module, attr_name):
        return qualified_name
    package = _dotted_package_for_file(src_dir, file_path)
    reexported = build_import_table(module, package).get(attr_name)
    if reexported is None or reexported == qualified_name:
        return qualified_name
    return _resolve_static_reexport(reexported, _hops=_hops + 1)


def _bare_name(fn: FunctionSource) -> str:
    """``ClassName.method`` -> ``method``; a module-level name unchanged."""
    return fn.qualified_name.rsplit(".", 1)[-1]


def _role_key_for(fn: FunctionSource, tokens: frozenset[str]) -> RoleKey:
    """The two-key ladder for one function.

    Args:
        fn: The function to key.
        tokens: This function's own package's token vocabulary.

    Returns:
        A ``SignatureRole`` if *fn*'s return annotation declares a shared
        product, else a ``NameRole``.

    Raises:
        SkeletonError: If *fn*'s return annotation cannot be classified,
            naming the member.
    """
    try:
        product_type = shared_product_type(fn.node.returns, fn.import_table)
    except SkeletonError as exc:
        raise SkeletonError(
            f"Cannot key the role of {fn.qualified_name} ({fn.package}:{fn.file_path}:{fn.line_number}): {exc}"
        ) from exc
    if product_type is not None:
        return SignatureRole(product_type=product_type)
    return NameRole(normalized_name=normalized_name(_bare_name(fn), tokens))


# ---------------------------------------------------------------------------
# Function collection (module-level + class-method defs only)
# ---------------------------------------------------------------------------


def _collect_module_and_method_defs(
    body: list[ast.stmt], enclosing_class: str | None
) -> list[tuple[_FunctionDefNode, str | None]]:
    """Recursively collect every module-level or class-method function def
    reachable through non-function statement containers (If/While/For/With/
    Try), pairing each with its nearest enclosing class name.

    Never descends into a function's own body -- a nested function is a
    closure, not a declaration this scanner tracks. A class nested inside
    another class resets ``enclosing_class`` to its own name (single-level
    qualification, ``ClassName.method_name``).

    Args:
        body: A statement list (a module body or a class body).
        enclosing_class: The nearest enclosing class's name, or ``None``.

    Returns:
        ``(node, enclosing_class)`` pairs, in source order.
    """
    found: list[tuple[_FunctionDefNode, str | None]] = []
    for stmt in body:
        if isinstance(stmt, ast.ClassDef):
            found.extend(_collect_module_and_method_defs(stmt.body, stmt.name))
            continue
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found.append((stmt, enclosing_class))
            continue
        for attr in _CONTAINER_BODY_ATTRS:
            nested_body = getattr(stmt, attr, None)
            if nested_body:
                found.extend(_collect_module_and_method_defs(nested_body, enclosing_class))
        for handler in getattr(stmt, "handlers", ()):
            found.extend(_collect_module_and_method_defs(handler.body, enclosing_class))
    return found


def _decorated_source_segment(source_lines: list[str], node: _FunctionDefNode) -> str:
    """Verbatim source text of *node*, decorators included: whole source
    lines from the first decorator's line (or the ``def`` line) through the
    function's last line.

    Args:
        source_lines: The file's source, ``splitlines(keepends=True)``.
        node: The function/method AST node.

    Returns:
        The decorator(s) + def + body, as literal source text.

    Raises:
        SkeletonError: If ``node.end_lineno`` is unavailable.
    """
    if node.end_lineno is None:
        raise SkeletonError(
            f"AST node for {node.name!r} at line {node.lineno} has no end_lineno -- "
            f"expected ast.parse() to populate it (requires Python >= 3.8)."
        )
    start_line = node.decorator_list[0].lineno if node.decorator_list else node.lineno
    return "".join(source_lines[start_line - 1 : node.end_lineno])


def _dotted_package_for_file(src_dir: Path, file_path: Path) -> str:
    """The dotted package *file_path* lives in, for resolving its relative
    imports: ``pkg/sub/mod.py`` and ``pkg/sub/__init__.py`` alike live in
    ``pkg.sub`` (a package's ``__init__`` IS its package).

    Args:
        src_dir: The package's src root (e.g. ``.../src/datrix_codegen_python``).
        file_path: A ``.py`` file under *src_dir*.

    Returns:
        The dotted package path.
    """
    relative = file_path.relative_to(src_dir)
    return ".".join([src_dir.name, *relative.parts[:-1]])


def _qualified_def_name(node: _FunctionDefNode, enclosing_class: str | None) -> str:
    return f"{enclosing_class}.{node.name}" if enclosing_class else node.name


def collect_function_sources(src_dir: Path, package: str) -> list[FunctionSource]:
    """AST-walk every ``.py`` file under *src_dir* for module-level and
    class-method function/method definitions, building one ``FunctionSource``
    per declaration with its decorated source text and its own file's import
    table.

    Args:
        src_dir: A package's source root (e.g. a language's
            ``src/datrix_codegen_python`` directory).
        package: The label recorded on every returned ``FunctionSource`` (a
            registered language/platform name, or a folded label).

    Returns:
        Every declaration found, in file-then-source order. Empty if
        *src_dir* does not exist.

    Raises:
        SkeletonError: If a ``.py`` file under *src_dir* cannot be parsed --
            propagates unmodified, never caught here.
    """
    sources: list[FunctionSource] = []
    if not src_dir.is_dir():
        return sources
    for py_file in sorted(src_dir.rglob("*.py")):
        module = parse_module_or_raise(py_file)
        import_table = build_import_table(module, _dotted_package_for_file(src_dir, py_file))
        source_lines = py_file.read_text(encoding="utf-8-sig").splitlines(keepends=True)
        for node, enclosing_class in _collect_module_and_method_defs(module.body, None):
            sources.append(
                FunctionSource(
                    package=package,
                    file_path=py_file,
                    line_number=node.lineno,
                    qualified_name=_qualified_def_name(node, enclosing_class),
                    node=node,
                    source_text=_decorated_source_segment(source_lines, node),
                    import_table=import_table,
                )
            )
    return sources


def collect_bare_names(src_dir: Path) -> frozenset[str]:
    """Every bare function/method name defined (module-level or as a class
    method) anywhere under *src_dir* -- the exclusion set for name roles.

    Args:
        src_dir: A non-target package's source root.

    Returns:
        The frozenset of bare names. Empty if *src_dir* does not exist.

    Raises:
        SkeletonError: If a ``.py`` file under *src_dir* cannot be parsed.
    """
    if not src_dir.is_dir():
        return frozenset()
    names: set[str] = set()
    for py_file in sorted(src_dir.rglob("*.py")):
        module = parse_module_or_raise(py_file)
        names.update(node.name for node, _ in _collect_module_and_method_defs(module.body, None))
    return frozenset(names)


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def _role_plumbing(members: Iterable[FunctionSource]) -> frozenset[str]:
    """The ROLE-LEVEL plumbing parameter set: the union of every member's own
    ``plumbing_parameter_names``, so a parameter name any member drops as
    language-private plumbing is dropped for every member, not just the one
    whose own annotation is private."""
    return frozenset[str]().union(*(plumbing_parameter_names(member) for member in members))


def _behaviour_pair(member: FunctionSource, plumbing: frozenset[str]) -> BehaviourPair:
    """One member's ``(behaviour skeleton, role-level behaviour arity)``.

    Raises:
        SkeletonError: Propagates from the extractor on an unclassifiable
            construct -- never caught here.
    """
    return (behaviour_skeleton(member), behaviour_arity(member, extra_plumbing=plumbing))


def _classify_role(members: tuple[FunctionSource, ...]) -> Verdict:
    """The classification ladder for one role.

    Args:
        members: Two or more ``FunctionSource``s in this role, from >= 2
            distinct packages.

    Returns:
        ``identical`` if every member's ``normalized_source`` is equal; else
        ``same-behaviour`` if every member's ``_behaviour_pair`` is equal,
        with arity computed role-level (``_role_plumbing``) -- two members
        whose statement-level skeletons match but that read a different
        number of REAL inputs (the geo query builder shape) still do NOT
        behave the same; else ``divergent``.

    Raises:
        SkeletonError: Propagates from the extractor on an unclassifiable
            construct -- never caught here.
    """
    if len({normalized_source(member) for member in members}) == 1:
        return _VERDICT_IDENTICAL
    plumbing = _role_plumbing(members)
    if len({_behaviour_pair(member, plumbing) for member in members}) == 1:
        return _VERDICT_SAME_BEHAVIOUR
    return _VERDICT_DIVERGENT


def role_label(role_key: RoleKey) -> str:
    """A stable, sortable, human-readable label for one role key."""
    if isinstance(role_key, NameRole):
        return role_key.normalized_name
    return f"-> {role_key.product_type}"


def _require_min_packages(axis: str, labels: frozenset[str]) -> None:
    """Raise if fewer than ``_MIN_PACKAGES_FOR_COMPARISON`` distinct packages
    are being compared -- the guard against a vacuous scan, exercised
    directly by the self-test (never through a live registry).

    Args:
        axis: The axis being validated, named in the error.
        labels: The folded target labels to validate.

    Raises:
        ValueError: If fewer than ``_MIN_PACKAGES_FOR_COMPARISON`` remain.
    """
    if len(labels) < _MIN_PACKAGES_FOR_COMPARISON:
        raise ValueError(
            f"Behaviour-parity comparison requires at least {_MIN_PACKAGES_FOR_COMPARISON} "
            f"distinct registered 'datrix.{axis}' packages; got {len(labels)} "
            f"({sorted(labels)}). Registered names sharing one package are folded into a "
            f"single entry, so a name count above this floor does not imply a comparable "
            f"package count above it."
        )


def _distinct_packages(members: list[FunctionSource]) -> int:
    return len({member.package for member in members})


def _is_excluded_name_role(key: RoleKey, members: list[FunctionSource], other_bare_names: frozenset[str]) -> bool:
    """A name role any of whose members' bare names is also defined in a
    non-target package is excluded entirely; a signature role never is --
    its identity is the shared type, not the name."""
    if not isinstance(key, NameRole):
        return False
    return any(_bare_name(member) in other_bare_names for member in members)


def group_and_classify_roles(
    target_src_dirs: dict[str, Path],
    tokens_by_label: dict[str, frozenset[str]],
    other_src_dirs: list[Path],
) -> list[RoleVerdict]:
    """Core scan: collect every target package's functions, key them into
    roles, keep roles with >= 2 distinct member packages, apply the
    other-package name exclusion, and classify each.

    Pure and dependency-injected -- no registry/entry-point call inside, so
    the self-test exercises it directly with a synthetic package map and
    injected tokens, never a live plugin.

    Args:
        target_src_dirs: ``{label: src_dir}`` for every package to compare.
        tokens_by_label: ``{label: token vocabulary}`` for every label in
            *target_src_dirs* (from ``tokens_for``, or injected by the
            self-test).
        other_src_dirs: Every OTHER package's src dir -- a ``NameRole`` any
            of whose member names is also bare-defined here is excluded.

    Returns:
        One ``RoleVerdict`` per qualifying role, ``domain=None``, sorted by
        role label.

    Raises:
        SkeletonError: Propagates from an unparseable or unclassifiable
            member.
    """
    other_bare_names = frozenset().union(*(collect_bare_names(src_dir) for src_dir in other_src_dirs))

    by_role: dict[RoleKey, list[FunctionSource]] = {}
    for label, src_dir in target_src_dirs.items():
        package_tokens = tokens_by_label[label]
        for fn in collect_function_sources(src_dir, label):
            by_role.setdefault(_role_key_for(fn, package_tokens), []).append(fn)

    verdicts: list[RoleVerdict] = []
    for key, members in by_role.items():
        if _distinct_packages(members) < _MIN_PACKAGES_FOR_COMPARISON:
            continue
        if _is_excluded_name_role(key, members, other_bare_names):
            continue
        members_tuple = tuple(members)
        verdicts.append(
            RoleVerdict(
                role_key=key,
                kind="signature" if isinstance(key, SignatureRole) else "name",
                domain=None,
                verdict=_classify_role(members_tuple),
                members=members_tuple,
                adapter_exempt=all(is_pre_binding_adapter(member) for member in members_tuple),
                rendering_leaf_exempt=all(is_rendering_leaf(member) for member in members_tuple),
            )
        )
    return sorted(verdicts, key=lambda verdict: role_label(verdict.role_key))


def discover_roles_for(axis: str, target_src_dirs: Mapping[str, Path], workspace_root: Path) -> list[RoleVerdict]:
    """Scan the already-resolved *target_src_dirs* on *axis*: refuse a
    vacuous comparison, collect every other package's bare names, build each
    label's token vocabulary via the live registry, and delegate to
    ``group_and_classify_roles``.

    Args:
        axis: ``AXIS_LANGUAGES`` or ``AXIS_PLATFORMS``.
        target_src_dirs: ``{label: src_dir}`` from
            ``discover_target_package_src_dirs``.
        workspace_root: The monorepo root.

    Returns:
        Every qualifying ``RoleVerdict``.

    Raises:
        ValueError: Fewer than two distinct packages are being compared.
        SkeletonError: An unparseable or unclassifiable member.
    """
    _require_min_packages(axis, frozenset(target_src_dirs))
    other_src_dirs = discover_all_other_package_src_dirs(workspace_root, frozenset(target_src_dirs.values()))
    tokens_by_label = {label: tokens_for(axis, label) for label in target_src_dirs}
    return group_and_classify_roles(dict(target_src_dirs), tokens_by_label, other_src_dirs)


def discover_roles(axis: str, target_names: frozenset[str], workspace_root: Path) -> list[RoleVerdict]:
    """Resolve *axis*'s registered *target_names* to on-disk src dirs via the
    live registry, then scan them with ``discover_roles_for``.

    Args:
        axis: ``AXIS_LANGUAGES`` or ``AXIS_PLATFORMS``.
        target_names: Registered names on that axis to compare.
        workspace_root: The monorepo root.

    Returns:
        Every qualifying ``RoleVerdict``.

    Raises:
        ValueError: A registered name resolves to no on-disk package, or
            fewer than two distinct packages resolve.
        SkeletonError: An unparseable or unclassifiable member.
    """
    target_src_dirs = discover_target_package_src_dirs(axis, target_names, workspace_root)
    return discover_roles_for(axis, target_src_dirs, workspace_root)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _display_path(file_path: Path, workspace_root: Path) -> str:
    """*file_path* relative to *workspace_root* when it lies under it, else
    as given -- a display concern only; the verdict keeps the absolute path."""
    if file_path.is_relative_to(workspace_root):
        return file_path.relative_to(workspace_root).as_posix()
    return str(file_path)


def member_reference(member: FunctionSource, workspace_root: Path) -> str:
    """``package:file:line (qualified_name)`` for one role member."""
    return f"{member.package}:{_display_path(member.file_path, workspace_root)}:{member.line_number} ({member.qualified_name})"


def verdict_line(verdict: RoleVerdict, workspace_root: Path) -> str:
    """One report line for *verdict*."""
    members = ", ".join(member_reference(member, workspace_root) for member in verdict.members)
    suffixes = [
        label
        for flag, label in (
            (verdict.adapter_exempt, "adapter-exempt"),
            (verdict.rendering_leaf_exempt, "rendering-leaf-exempt"),
        )
        if flag
    ]
    suffix_text = "".join(f" {label}" for label in suffixes)
    return (
        f"VERDICT kind={verdict.kind} role={role_label(verdict.role_key)} "
        f"verdict={verdict.verdict}{suffix_text} members=[{members}]"
    )


def _log_bucket_counts(verdicts: Sequence[RoleVerdict]) -> None:
    """The per-bucket summary line every report ends with."""
    counts = Counter(verdict.verdict for verdict in verdicts)
    adapter_exempt_counts = Counter(verdict.verdict for verdict in verdicts if verdict.adapter_exempt)
    leaf_exempt_counts = Counter(verdict.verdict for verdict in verdicts if verdict.rendering_leaf_exempt)
    logger.info(
        "BEHAVIOUR-PARITY REPORT: %d role(s) -- %d %s (%d adapter-exempt, %d rendering-leaf-exempt), "
        "%d %s (%d adapter-exempt, %d rendering-leaf-exempt), %d %s.",
        len(verdicts),
        counts[_VERDICT_IDENTICAL],
        _VERDICT_IDENTICAL,
        adapter_exempt_counts[_VERDICT_IDENTICAL],
        leaf_exempt_counts[_VERDICT_IDENTICAL],
        counts[_VERDICT_SAME_BEHAVIOUR],
        _VERDICT_SAME_BEHAVIOUR,
        adapter_exempt_counts[_VERDICT_SAME_BEHAVIOUR],
        leaf_exempt_counts[_VERDICT_SAME_BEHAVIOUR],
        counts[_VERDICT_DIVERGENT],
        _VERDICT_DIVERGENT,
    )


def render_report(verdicts: Sequence[RoleVerdict], workspace_root: Path, *, debug: bool) -> None:
    """Log one line per role and the per-bucket counts -- the report-only
    rendering used for the platform axis and ``--report-only``; nothing here
    evaluates a gate.

    Args:
        verdicts: Every classified role.
        workspace_root: Root that member paths are displayed relative to.
        debug: Also log ``identical``/``same-behaviour`` roles at INFO (they
            log at DEBUG otherwise); ``divergent`` roles always log at INFO.
    """
    for verdict in verdicts:
        line = verdict_line(verdict, workspace_root)
        if debug or verdict.verdict == _VERDICT_DIVERGENT:
            logger.info(line)
        else:
            logger.debug(line)
    _log_bucket_counts(verdicts)


# ---------------------------------------------------------------------------
# Domain resolution (the role -> shared-domain ladder)
# ---------------------------------------------------------------------------


def _type_qualname(context_type: type) -> str:
    return f"{context_type.__module__}.{context_type.__qualname__}"


@functools.cache
def _rich_context_type_qualnames() -> Mapping[str, tuple[str, ...]]:
    """Reverse map ``"module.QualName" -> (domain_id, ...)`` over every type
    registered for every shared parity registry domain.

    Built lazily on first use and cached for the process: the registry is
    itself computed at import time, so a first-call cache (rather than a
    module-level constant) avoids any import-order hazard, and
    ``resolve_domain`` runs once per role over hundreds of roles. A domain
    that registers several distinct types (a multi-context micro-generator)
    contributes one reverse-map entry per type, all pointing back at that one
    domain id. A type shared by SEVERAL domains -- the test-plan context
    every ``*_test`` domain binds -- maps to every one of them; ladder step 1
    requires EXACTLY one, so such a type never resolves there.
    """
    reverse: dict[str, list[str]] = {}
    for domain_id, context_types in _RICH_CONTEXT_TYPES.items():
        for context_type in context_types:
            reverse.setdefault(_type_qualname(context_type), []).append(domain_id)
    return MappingProxyType({qualname: tuple(ids) for qualname, ids in reverse.items()})


def _domain_from_rich_context_type(product_type: str) -> str | None:
    """Ladder step 1: *product_type* is a rich context type of exactly one
    domain. ``None`` is a probe result ("no hit"), not an error."""
    reverse = _rich_context_type_qualnames()
    if product_type not in reverse:
        return None
    ids = reverse[product_type]
    return ids[0] if len(ids) == 1 else None


def _strip_context_module_affixes(basename: str) -> str:
    """``persistence_cache`` -> ``cache``; ``pubsub_render_contexts`` ->
    ``pubsub``; ``entity`` unchanged."""
    if basename.startswith(_CONTEXT_MODULE_PREFIX):
        basename = basename[len(_CONTEXT_MODULE_PREFIX) :]
    for suffix in _CONTEXT_MODULE_SUFFIXES:
        if basename.endswith(suffix):
            return basename[: -len(suffix)]
    return basename


def _domain_from_module_basename(module_qualname: str) -> str | None:
    """Ladder step 2: the product type's OWN defining module basename, affixes
    stripped, when the module lives under an eligible shared context-model
    package and the result is a universe id."""
    if not module_qualname.startswith(_ELIGIBLE_CONTEXT_MODULE_PREFIXES):
        return None
    candidate = _strip_context_module_affixes(module_qualname.rsplit(".", 1)[-1])
    return candidate if candidate in SHARED_CONTEXT_TYPES else None


def _orchestration_module_candidate(name: str) -> str | None:
    for suffix in _ORCHESTRATION_MODULE_SUFFIXES:
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return None


def _source_module_candidate(parts: tuple[str, ...]) -> str | None:
    """The domain-id candidate one member's path spells through the four
    owning-module shapes, or ``None`` when the path has none of them. The
    caller checks the candidate against the universe; this never does."""
    if len(parts) < 2:
        return None
    parent, name = parts[-2], parts[-1]
    if parent == _MICRO_GENERATORS_DIR and name.endswith(_PY_SUFFIX):
        return name[: -len(_PY_SUFFIX)]
    if parent == _HOOKS_DIR and name.endswith(_HOOKS_MODULE_SUFFIX):
        return name[: -len(_HOOKS_MODULE_SUFFIX)]
    if parent == _ORCHESTRATION_DIR:
        return _orchestration_module_candidate(name)
    if _GENERATORS_DIR in parts[:-1]:
        return parts[parts.index(_GENERATORS_DIR) + 1]
    return None


def _member_source_domain(member: FunctionSource) -> str | None:
    """Ladder step 3, one member: the universe id its source module spells,
    or ``None``."""
    candidate = _source_module_candidate(member.file_path.parts)
    if candidate is None or candidate not in SHARED_CONTEXT_TYPES:
        return None
    return candidate


def _domain_from_member_source_modules(role: RoleVerdict) -> str | None:
    """Ladder step 3, whole role: every member resolves, and to the SAME id.
    Disagreeing members fall through (``None``) -- never a guess."""
    resolved: set[str] = set()
    for member in role.members:
        candidate = _member_source_domain(member)
        if candidate is None:
            return None
        resolved.add(candidate)
    return resolved.pop() if len(resolved) == 1 else None


def resolve_domain(role: RoleVerdict) -> str:
    """The role -> shared-domain ladder, first hit wins (module docstring).

    Args:
        role: A classified role (``domain`` may be ``None``).

    Returns:
        A ``SHARED_CONTEXT_TYPES`` key, or ``UNDOMAINED`` when no step hits.
        Never raises for a role that maps to no domain -- that is what
        ``UNDOMAINED`` means; an unparseable member is a ``SkeletonError``
        raised upstream, never converted into ``UNDOMAINED`` here.
    """
    if isinstance(role.role_key, SignatureRole):
        product_type = role.role_key.product_type
        rich = _domain_from_rich_context_type(product_type)
        if rich is not None:
            return rich
        by_module = _domain_from_module_basename(product_type.rsplit(".", 1)[0])
        if by_module is not None:
            return by_module
    by_source = _domain_from_member_source_modules(role)
    return by_source if by_source is not None else UNDOMAINED


# ---------------------------------------------------------------------------
# Declared exemption surfaces
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExemptionSurfaces:
    """The three declared surfaces a member package may be set aside on,
    keyed by member package label, read ONCE by the caller and passed in -- never
    fetched inside the exemption check -- so the self-test injects synthetic
    tables exactly as the role-grouping self-test injects synthetic tokens.

    ``adapter_groups_by_language`` is surface 3 pre-resolved: for every
    language, ``adapter_group_index`` over its emit tables.
    """

    stance_table: Mapping[str, Mapping[str, DomainDeclaration]]
    on_demand_by_language: Mapping[str, Mapping[str, str]]
    builtin_group_stances_by_language: Mapping[str, Mapping[str, BuiltinGroupStance]]
    adapter_groups_by_language: Mapping[str, Mapping[AdapterIdentity, frozenset[str]]]

    @classmethod
    def none(cls) -> ExemptionSurfaces:
        """No language declares anything: no member package is set aside."""
        return cls(MappingProxyType({}), MappingProxyType({}), MappingProxyType({}), MappingProxyType({}))


def _adapter_identity(emit_function: object, table_key: str) -> AdapterIdentity:
    """``(resolved defining file, __qualname__)`` of a registered emit callable.

    Raises:
        ValueError: The callable carries no code object or qualified name
            (a ``functools.partial``, an arbitrary callable instance) -- it
            cannot be matched to an AST-scanned member, so the read fails
            closed naming the registration.
    """
    code = getattr(emit_function, "__code__", None)
    qualname = getattr(emit_function, "__qualname__", None)
    if not isinstance(code, CodeType) or not isinstance(qualname, str):
        raise ValueError(
            f"behaviour_parity:emit function {table_key!r} ({emit_function!r}) carries no __code__/__qualname__; "
            f"the gate matches @emit_adapter members on (defining file, qualified name). Fix: register a "
            f"module-level function or a method, not an arbitrary callable object."
        )
    return (Path(code.co_filename).resolve(), qualname)


def _row_groups_by_emit_function(
    table: EmitTable[object], registry: Mapping[BuiltinKey, BuiltinDecl]
) -> dict[str, set[str]]:
    """``{emit-function key: builtin group names}`` over every row of *table*."""
    groups: dict[str, set[str]] = {}
    for key in sorted(table.declared_keys):
        if key not in registry:
            raise ValueError(
                f"behaviour_parity:emit-table row {key!r} is not a key of the supplied builtin registry, so its "
                f"builtin group cannot be read. Fix: pass the registry the table was validated against."
            )
        group_name = registry[key].group.value
        for decl in table.rows_for(*key):
            groups.setdefault(decl.emit_function, set()).add(group_name)
    return groups


def adapter_group_index(
    emit_tables: Sequence[EmitTable[object]], registry: Mapping[BuiltinKey, BuiltinDecl]
) -> Mapping[AdapterIdentity, frozenset[str]]:
    """``(defining file, __qualname__) -> builtin group names`` for every emit
    callable the given tables register -- the reverse lookup surface 3 reads.

    A callable registered in several tables, or referenced by rows of several
    groups, maps to the union of its groups.

    Args:
        emit_tables: Every ``EmitTable`` one language constructs.
        registry: The builtin registry the tables were validated against
            (``BUILTIN_REGISTRY`` for a real language; synthetic in the
            self-test).

    Returns:
        The read-only index.

    Raises:
        ValueError: A row's key is missing from *registry*, a registered
            callable is referenced by no row, or a callable carries no usable
            identity -- each fails closed naming the offender.
    """
    index: dict[AdapterIdentity, set[str]] = {}
    for table in emit_tables:
        groups_by_name = _row_groups_by_emit_function(table, registry)
        for name, emit_function in table.registered_emit_functions.items():
            if name not in groups_by_name:
                raise ValueError(
                    f"behaviour_parity:emit function {name!r} is registered but referenced by no row of its "
                    f"EmitTable; its builtin group cannot be read. Fix: reference it from a declared row."
                )
            index.setdefault(_adapter_identity(emit_function, name), set()).update(groups_by_name[name])
    return MappingProxyType({identity: frozenset(groups) for identity, groups in index.items()})


def _raise_walk_error(package_name: str) -> None:
    raise ValueError(
        f"behaviour_parity:cannot import package {package_name!r} while collecting its EmitTables; an "
        f"unimportable package hides every table it may define, so the scan refuses to continue. Fix: make "
        f"the package import cleanly under the running interpreter."
    )


def _import_module_or_raise(module_name: str) -> object:
    try:
        return importlib.import_module(module_name)
    except Exception as exc:  # noqa: BLE001 -- re-raised with the fail-closed reason
        raise ValueError(
            f"behaviour_parity:cannot import module {module_name!r} while collecting its package's EmitTables "
            f"({type(exc).__name__}: {exc}); an unimportable module hides every table it may define, so the "
            f"scan refuses to continue. Fix: make the module import cleanly under the running interpreter."
        ) from exc


def collect_emit_tables(src_dir: Path) -> tuple[EmitTable[object], ...]:
    """Every module-level ``EmitTable`` instance any module under *src_dir*
    defines, deduplicated by identity (a table re-imported into another
    module is one table).

    Imports the package root and every module ``pkgutil.walk_packages``
    finds beneath it; a module that fails to import aborts the collection
    naming it (module docstring, "How surface 3 finds a language's emit
    tables"). No table variable name and no table-module path is assumed.

    Args:
        src_dir: The package's importable root (``.../src/<import root>``);
            its directory name IS the import name.

    Returns:
        Every distinct ``EmitTable`` the package constructs, in discovery
        order.

    Raises:
        ValueError: A module or package under *src_dir* cannot be imported.
    """
    import_root = src_dir.name
    modules = [_import_module_or_raise(import_root)]
    for info in pkgutil.walk_packages([str(src_dir)], prefix=f"{import_root}.", onerror=_raise_walk_error):
        modules.append(_import_module_or_raise(info.name))
    tables: dict[int, EmitTable[object]] = {}
    for module in modules:
        for value in vars(module).values():
            if isinstance(value, EmitTable):
                tables.setdefault(id(value), value)
    return tuple(tables.values())


def is_emit_adapter_member(member: FunctionSource) -> bool:
    """Whether *member* carries the ``@emit_adapter`` marker, recognized
    STRUCTURALLY: one of its decorators resolves through the member's own
    import table to the shared layer's ``emit_adapter`` (bare name or
    module-qualified attribute alike). A same-named decorator imported from
    anywhere else is not the marker -- the fail-closed direction for an
    exemption."""
    return any(
        _qualified_name_of(decorator, member.import_table) == _EMIT_ADAPTER_QUALIFIED_NAME
        for decorator in member.node.decorator_list
    )


def _adapter_groups_for_member(
    member: FunctionSource, adapter_groups: Mapping[AdapterIdentity, frozenset[str]]
) -> frozenset[str]:
    """The builtin groups the emit-table rows dispatching to *member* belong to.

    Raises:
        ValueError: *member* is ``@emit_adapter``-marked but no table
            registers it -- a failure naming the member, never a skip.
    """
    identity: AdapterIdentity = (member.file_path.resolve(), member.qualified_name)
    if identity not in adapter_groups:
        raise ValueError(
            f"behaviour_parity:{member.package}:{member.file_path}:{member.line_number} ({member.qualified_name}) "
            f"is marked @emit_adapter but no EmitTable of {member.package!r} registers it, so its builtin group "
            f"cannot be read and the gate refuses to skip it. Every @emit_adapter function must be referenced by "
            f"a declared (category, method) row. Fix: register the function in a row, or remove the marker."
        )
    return adapter_groups[identity]


def _domain_declared_unsupported(
    stance_table: Mapping[str, Mapping[str, DomainDeclaration]], language: str, domain: str
) -> bool:
    """Surface 1: *language*'s ``DomainDeclaration`` for *domain* is ``unsupported``."""
    if language not in stance_table or domain not in stance_table[language]:
        return False
    return stance_table[language][domain].status == _UNSUPPORTED_STATUS


def _domain_on_demand(on_demand_by_language: Mapping[str, Mapping[str, str]], language: str, domain: str) -> bool:
    """Surface 2: *domain* is a key of *language*'s ``on_demand_domains``."""
    return language in on_demand_by_language and domain in on_demand_by_language[language]


def _groups_declared_unsupported(stances: Mapping[str, BuiltinGroupStance], groups: frozenset[str]) -> bool:
    """Every group in *groups* has an ``unsupported`` stance. An empty set
    is never exempt (``all`` over nothing would be vacuously true)."""
    return bool(groups) and all(group in stances and stances[group].status == _UNSUPPORTED_STATUS for group in groups)


def _adapter_member_exempt(member: FunctionSource, language: str, surfaces: ExemptionSurfaces) -> bool:
    """Surface 3 for one member: an ``@emit_adapter``-marked member whose
    rows' builtin groups *language* all declares ``unsupported``. A language
    with no collected tables or no group stances is simply not exempt on
    this surface (an unregistered marked member still raises)."""
    if not is_emit_adapter_member(member):
        return False
    adapter_groups = (
        surfaces.adapter_groups_by_language[language]
        if language in surfaces.adapter_groups_by_language
        else _NO_ADAPTERS
    )
    stances = (
        surfaces.builtin_group_stances_by_language[language]
        if language in surfaces.builtin_group_stances_by_language
        else _NO_GROUP_STANCES
    )
    return _groups_declared_unsupported(stances, _adapter_groups_for_member(member, adapter_groups))


def is_role_exempt(role: RoleVerdict, domain: str, language: str, surfaces: ExemptionSurfaces) -> bool:
    """True iff *language* -- a member package of *role* -- declares the
    construct unsupported on ANY of the three declared surfaces.

    Surfaces 1 and 2 are domain-keyed and apply only to a role resolved to a
    shared domain; an ``UNDOMAINED`` role admits only surface 3. Surface 3
    requires EVERY member *language* contributes to the role to be a marked
    adapter over unsupported groups -- one behaviour-bearing non-adapter
    member is enough to deny it.

    Args:
        role: The ``divergent`` role.
        domain: ``resolve_domain(role)``.
        language: The member package label.
        surfaces: The declared surfaces, read once by the caller.

    Returns:
        Whether *language* is exempt for *role*.

    Raises:
        ValueError: A marked adapter member of *language* resolves to no
            emit-table row.
    """
    if domain != UNDOMAINED and (
        _domain_declared_unsupported(surfaces.stance_table, language, domain)
        or _domain_on_demand(surfaces.on_demand_by_language, language, domain)
    ):
        return True
    own_members = [member for member in role.members if member.package == language]
    return bool(own_members) and all(_adapter_member_exempt(member, language, surfaces) for member in own_members)


def _merge_declared(
    mappings: Iterable[Mapping[str, _DeclaredValue]], label: str, surface: str
) -> Mapping[str, _DeclaredValue]:
    """One declaration table for one package label: the registered names
    folded into *label* (``registered_targets.fold_names_by_src_dir``) each
    carry a declaration, and a key two of them declare differently is
    ambiguous -- refused, never resolved by order."""
    merged: dict[str, _DeclaredValue] = {}
    for mapping in mappings:
        for key, value in mapping.items():
            if key in merged and merged[key] != value:
                raise ValueError(
                    f"behaviour_parity:the registered names folded into package label {label!r} declare "
                    f"conflicting {surface} for {key!r}; one package must carry one declaration per key."
                )
            merged[key] = value
    return MappingProxyType(merged)


def live_exemption_surfaces(
    target_src_dirs: Mapping[str, Path], registry: Mapping[BuiltinKey, BuiltinDecl]
) -> ExemptionSurfaces:
    """Read the three declared surfaces for every language package label from
    the live registry: domain stances through
    ``supported_domain_parity.stance_table_by_language``, ``on_demand_domains``
    and ``builtin_group_stances`` through ``declaration_for_language``, and the
    adapter index through ``collect_emit_tables`` + ``adapter_group_index``.

    Args:
        target_src_dirs: ``{label: src_dir}`` for every compared language
            package.
        registry: The builtin registry the languages' tables were validated
            against.

    Returns:
        The surfaces, keyed by label.

    Raises:
        ValueError: A folded label declares conflicting values, a package
            cannot be imported, or an emit table cannot be indexed.
    """
    stance_table: dict[str, Mapping[str, DomainDeclaration]] = {}
    on_demand: dict[str, Mapping[str, str]] = {}
    group_stances: dict[str, Mapping[str, BuiltinGroupStance]] = {}
    adapter_groups: dict[str, Mapping[AdapterIdentity, frozenset[str]]] = {}
    for label, src_dir in target_src_dirs.items():
        names = label.split(_LABEL_JOIN_SEPARATOR)
        declarations = [declaration_for_language(name) for name in names]
        stance_table[label] = _merge_declared(stance_table_by_language(names).values(), label, "domain stances")
        on_demand[label] = _merge_declared(
            [declaration.on_demand_domains for declaration in declarations], label, "on_demand_domains"
        )
        group_stances[label] = _merge_declared(
            [declaration.builtin_group_stances for declaration in declarations], label, "builtin_group_stances"
        )
        tables = collect_emit_tables(src_dir)
        adapter_groups[label] = adapter_group_index(tables, registry)
        logger.info(
            "exemption surfaces for %s: %d domain stance(s), %d on-demand domain(s), %d builtin-group stance(s), "
            "%d EmitTable(s) registering %d emit function(s)",
            label,
            len(stance_table[label]),
            len(on_demand[label]),
            len(group_stances[label]),
            len(tables),
            len(adapter_groups[label]),
        )
    return ExemptionSurfaces(
        MappingProxyType(stance_table),
        MappingProxyType(on_demand),
        MappingProxyType(group_stances),
        MappingProxyType(adapter_groups),
    )


# ---------------------------------------------------------------------------
# Scope
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GateScope:
    """The gate's full in-scope surface. A role is in scope when EITHER half
    admits it: its resolved domain is in ``domains`` (or ``domains`` is
    ``None``, meaning every domain), OR its verdict is in ``buckets``. The
    two halves grow independently and neither is ever read as narrowing the
    other -- Section 6 step 2 needs to gate the whole ``identical`` bucket
    while ``domains`` still lists no domain at all.

    Attributes:
        domains: The in-scope shared domain ids, or ``None`` for every
            domain (the hard-zero end state once the migration scope file
            is deleted).
        buckets: The verdict names (drawn from ``_VALID_BUCKET_IDS``) gated
            across every domain regardless of ``domains``. Empty means no
            bucket-wide gating.
    """

    domains: frozenset[str] | None
    buckets: frozenset[str]


def parse_scope_argument(value: str | None) -> tuple[str, ...] | None:
    """``--scope``'s raw value -> the ids it names (``None`` when absent).

    Raises:
        ValueError: ``--scope`` was given but names no id.
    """
    if value is None:
        return None
    ids = tuple(part.strip() for part in value.split(_SCOPE_SEPARATOR) if part.strip())
    if not ids:
        raise ValueError(
            f"behaviour_parity:--scope was given but names no domain id; expected a {_SCOPE_SEPARATOR!r}-separated "
            f"list of shared domain ids and/or {UNDOMAINED!r}. Fix: pass at least one id, or omit --scope to "
            f"use the scope file."
        )
    return ids


def parse_buckets_argument(value: str | None) -> tuple[str, ...] | None:
    """``--buckets``'s raw value -> the verdict-bucket ids it names (``None`` when absent).

    Raises:
        ValueError: ``--buckets`` was given but names no id.
    """
    if value is None:
        return None
    ids = tuple(part.strip() for part in value.split(_SCOPE_SEPARATOR) if part.strip())
    if not ids:
        raise ValueError(
            f"behaviour_parity:--buckets was given but names no verdict-bucket id; expected a "
            f"{_SCOPE_SEPARATOR!r}-separated list drawn from {sorted(_VALID_BUCKET_IDS)}. Fix: pass at least one "
            f"id, or omit --buckets to use the scope file."
        )
    return ids


def _validate_scope_ids(ids: Iterable[str], universe: frozenset[str], origin: str) -> frozenset[str]:
    valid = universe | {UNDOMAINED}
    unknown = sorted(set(ids) - valid)
    if unknown:
        raise ValueError(
            f"behaviour_parity:unknown scope id(s) {unknown} in {origin}; valid options are {sorted(valid)}. "
            f"Fix: pass a shared domain id or {UNDOMAINED!r}."
        )
    return frozenset(ids)


def _validate_bucket_ids(ids: Iterable[str], origin: str) -> frozenset[str]:
    unknown = sorted(set(ids) - _VALID_BUCKET_IDS)
    if unknown:
        raise ValueError(
            f"behaviour_parity:unknown bucket id(s) {unknown} in {origin}; valid options are "
            f"{sorted(_VALID_BUCKET_IDS)}. Fix: pass one or more of {sorted(_VALID_BUCKET_IDS)}."
        )
    return frozenset(ids)


def _parse_scope_file(scope_path: Path) -> dict[str, object]:
    """Parse the scope file JSON, refusing anything that is not a JSON object.

    Raises:
        ValueError: The file is not valid JSON, or is valid JSON that is not
            an object.
    """
    expected = (
        f"a JSON object with a {_SCOPE_FILE_DOMAINS_KEY!r} array of domain-id strings and an optional "
        f"{_SCOPE_FILE_BUCKETS_KEY!r} array of verdict-bucket-id strings"
    )
    try:
        data = json.loads(scope_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"behaviour_parity:scope file {scope_path} is not valid JSON ({exc}); expected {expected}."
        ) from exc
    if not isinstance(data, dict):
        raise ValueError(f"behaviour_parity:malformed scope file {scope_path}: expected {expected}.")
    return data


def _read_scope_file(scope_path: Path) -> list[str]:
    """The ``domains`` list of the scope file, shape-validated.

    Raises:
        ValueError: The file is malformed (see ``_parse_scope_file``), lacks
            the ``domains`` key, or lists a non-string.
    """
    data = _parse_scope_file(scope_path)
    if _SCOPE_FILE_DOMAINS_KEY not in data:
        raise ValueError(
            f"behaviour_parity:malformed scope file {scope_path}: expected a {_SCOPE_FILE_DOMAINS_KEY!r} array of "
            f"domain-id strings."
        )
    domains = data[_SCOPE_FILE_DOMAINS_KEY]
    if not isinstance(domains, list) or not all(isinstance(domain, str) for domain in domains):
        raise ValueError(
            f"behaviour_parity:malformed scope file {scope_path}: {_SCOPE_FILE_DOMAINS_KEY!r} must be an array of "
            f"domain-id strings, got {domains!r}."
        )
    return domains


def _read_scope_buckets(scope_path: Path) -> list[str]:
    """The optional ``buckets`` list of the scope file; ``[]`` when the key
    is absent (no bucket-wide gating) -- unlike ``domains`` this key is not
    mandatory, so an existing scope file with no ``buckets`` key keeps
    today's behaviour unchanged.

    Raises:
        ValueError: The file is malformed (see ``_parse_scope_file``), or
            ``buckets`` is present but not an array of strings.
    """
    buckets = _parse_scope_file(scope_path).get(_SCOPE_FILE_BUCKETS_KEY, [])
    if not isinstance(buckets, list) or not all(isinstance(bucket, str) for bucket in buckets):
        raise ValueError(
            f"behaviour_parity:malformed scope file {scope_path}: {_SCOPE_FILE_BUCKETS_KEY!r} must be an array of "
            f"verdict-bucket-id strings, got {buckets!r}; valid options are {sorted(_VALID_BUCKET_IDS)}. "
            f"Fix: set {_SCOPE_FILE_BUCKETS_KEY!r} to an array of zero or more of {sorted(_VALID_BUCKET_IDS)}."
        )
    return buckets


def load_scope(
    explicit_scope: Sequence[str] | None,
    explicit_buckets: Sequence[str] | None,
    universe: frozenset[str],
    scope_path: Path,
) -> GateScope:
    """Resolve the gate's full scope: which domains and which verdict
    buckets may fail.

    Domains: ``--scope`` given -> its ids (the file is not read for
    domains). ``--scope`` absent and *scope_path* present -> the file's
    ``domains`` list (empty means no role fails by domain). Both absent ->
    ``None``, meaning EVERY domain is in scope: the hard-zero end state once
    the migration scope file is deleted.

    Buckets: ``--buckets`` given -> its ids (the file is not read for
    buckets). ``--buckets`` absent -> the file's ``buckets`` list if
    *scope_path* exists (empty or missing key means no bucket-wide gate),
    else empty. A role is in scope when EITHER half admits it.

    Args:
        explicit_scope: ``parse_scope_argument``'s result.
        explicit_buckets: ``parse_buckets_argument``'s result.
        universe: ``SHARED_CONTEXT_TYPES``' keys (or a synthetic universe).
        scope_path: The scope file read for whichever half has no explicit
            override.

    Returns:
        The resolved ``GateScope``.

    Raises:
        ValueError: An unknown domain id, an unknown bucket id (naming the
            valid options), or a malformed scope file.
    """
    if explicit_scope is not None:
        domains = _validate_scope_ids(explicit_scope, universe, "--scope")
    elif not scope_path.exists():
        domains = None
    else:
        domains = _validate_scope_ids(_read_scope_file(scope_path), universe, str(scope_path))

    if explicit_buckets is not None:
        buckets = _validate_bucket_ids(explicit_buckets, "--buckets")
    elif not scope_path.exists():
        buckets = frozenset()
    else:
        buckets = _validate_bucket_ids(_read_scope_buckets(scope_path), str(scope_path))

    return GateScope(domains=domains, buckets=buckets)


# ---------------------------------------------------------------------------
# Gate evaluation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RoleEvaluation:
    """One role's gate outcome: its verdict with ``domain`` filled in, whether
    that domain is in scope, and the reasons it fails (empty = passes)."""

    verdict: RoleVerdict
    domain: str
    in_scope: bool
    failure_reasons: tuple[str, ...]

    @property
    def fails(self) -> bool:
        return bool(self.failure_reasons)

    @property
    def fails_in_scope(self) -> bool:
        """The only condition that moves the exit code."""
        return self.fails and self.in_scope


def _behaviour_by_package(role: RoleVerdict) -> dict[str, frozenset[BehaviourPair]]:
    """``{package label: the set of behaviour pairs its members contribute}``,
    arity measured role-level exactly as ``_classify_role`` measures it."""
    plumbing = _role_plumbing(role.members)
    collected: dict[str, set[BehaviourPair]] = {}
    for member in role.members:
        collected.setdefault(member.package, set()).add(_behaviour_pair(member, plumbing))
    return {package: frozenset(pairs) for package, pairs in collected.items()}


def skeleton_groups(role: RoleVerdict) -> tuple[frozenset[str], ...]:
    """Partition *role*'s member packages into skeleton groups: two packages
    share a group when the SETS of behaviour pairs their members contribute
    to the role are equal -- a missing variant or an extra one is a
    difference either way. No package is privileged: a group is a group
    whichever language is in it.

    Args:
        role: A classified role.

    Returns:
        The groups, each a frozenset of package labels, ordered by their
        sorted members so the report is stable.
    """
    groups: dict[frozenset[BehaviourPair], set[str]] = {}
    for package, pairs in _behaviour_by_package(role).items():
        groups.setdefault(pairs, set()).add(package)
    return tuple(sorted((frozenset(members) for members in groups.values()), key=sorted))


def _group_text(group: Iterable[str]) -> str:
    return "{" + ", ".join(sorted(group)) + "}"


def _duplicate_skeleton_reasons(verdict: RoleVerdict) -> tuple[str, ...]:
    """``identical``/``same-behaviour``: fail unless every member is a
    pre-binding adapter or a rendering leaf (AST shape; no written
    exemption). ``same-behaviour`` compares role-level arity (plumbing names
    dropped across every member), so this failure also covers a role whose
    members read the same real parameter count once plumbing is reconciled."""
    if verdict.adapter_exempt or verdict.rendering_leaf_exempt:
        return ()
    packages = sorted({member.package for member in verdict.members})
    return (
        f"{verdict.verdict}: one behaviour skeleton lives in {len(packages)} packages {packages} and the members "
        f"are not pre-binding adapters or rendering leaves",
    )


def _divergence_reasons(verdict: RoleVerdict, domain: str, surfaces: ExemptionSurfaces) -> tuple[str, ...]:
    """``divergent``: partition the member packages into skeleton groups,
    set aside every package that declares the construct unsupported on a
    declared surface, and pass iff at most one group remains. Otherwise one
    reason names every remaining group -- the gate cannot know which group
    carries the correct behaviour, so it names all of them. A role every
    member of which declares the construct unsupported passes: a declared
    hole everywhere.

    Raises:
        ValueError: A marked adapter member of any package resolves to no
            emit-table row (``is_role_exempt`` fails closed).
    """
    packages = sorted({member.package for member in verdict.members})
    declaring = frozenset(package for package in packages if is_role_exempt(verdict, domain, package, surfaces))
    remaining = [group - declaring for group in skeleton_groups(verdict) if group - declaring]
    if len(remaining) <= 1:
        return ()
    groups_text = " vs ".join(_group_text(group) for group in remaining)
    declared_text = (
        "no member declares the construct unsupported"
        if not declaring
        else f"only {_group_text(declaring)} declare(s) the construct unsupported"
    )
    return (
        f"members split into {len(remaining)} skeleton groups: {groups_text}; {declared_text} for domain "
        f"{domain!r} on any declared surface",
    )


def evaluate_role(verdict: RoleVerdict, *, scope: GateScope, surfaces: ExemptionSurfaces) -> RoleEvaluation:
    """Resolve *verdict*'s domain, decide whether it is in *scope*, and
    compute its failure reasons -- for EVERY role, in scope or not, so an
    out-of-scope failure is reported rather than hidden.

    Args:
        verdict: A classified role.
        scope: The resolved domains/buckets scope.
        surfaces: The declared exemption surfaces.

    Returns:
        The evaluation, its verdict carrying the resolved domain.

    Raises:
        ValueError: A marked adapter member resolves to no emit-table row.
        SkeletonError: A member's skeleton cannot be extracted.
    """
    domain = resolve_domain(verdict)
    if verdict.verdict == _VERDICT_DIVERGENT:
        reasons = _divergence_reasons(verdict, domain, surfaces)
    else:
        reasons = _duplicate_skeleton_reasons(verdict)
    return RoleEvaluation(
        verdict=dataclasses.replace(verdict, domain=domain),
        domain=domain,
        in_scope=scope.domains is None or domain in scope.domains or verdict.verdict in scope.buckets,
        failure_reasons=reasons,
    )


def evaluate_roles(
    verdicts: Sequence[RoleVerdict], *, scope: GateScope, surfaces: ExemptionSurfaces
) -> list[RoleEvaluation]:
    """``evaluate_role`` over every verdict, order preserved."""
    return [evaluate_role(verdict, scope=scope, surfaces=surfaces) for verdict in verdicts]


def gate_exit_code(evaluations: Sequence[RoleEvaluation]) -> int:
    """``EXIT_FAIL`` iff any role fails in scope, else ``EXIT_OK``."""
    return EXIT_FAIL if any(evaluation.fails_in_scope for evaluation in evaluations) else EXIT_OK


def axis_gates(axis: str, *, report_only: bool) -> bool:
    """Whether verdicts on *axis* are evaluated against the gate. Only the
    language axis gates, and only when the run is not ``--report-only``; the
    platform axis is measured, never reconciled, so it is always report-only."""
    return axis == AXIS_LANGUAGES and not report_only


def evaluation_line(evaluation: RoleEvaluation, workspace_root: Path) -> str:
    """One gate-report line: ``PASS``, ``FAIL`` (in scope) or ``REPORTED``
    (fails, out of scope), then the verdict line, the domain, the scope
    state and every failure reason."""
    base = verdict_line(evaluation.verdict, workspace_root)
    scope_text = "in-scope" if evaluation.in_scope else "out-of-scope"
    if not evaluation.fails:
        return f"PASS {base} domain={evaluation.domain} {scope_text}"
    status = "FAIL" if evaluation.in_scope else "REPORTED"
    reasons = "; ".join(evaluation.failure_reasons)
    return f"{status} {base} domain={evaluation.domain} {scope_text} reasons=[{reasons}]"


def _log_evaluation(evaluation: RoleEvaluation, workspace_root: Path, *, debug: bool) -> None:
    line = evaluation_line(evaluation, workspace_root)
    if evaluation.fails_in_scope:
        logger.error(line)
    elif evaluation.fails or debug:
        logger.info(line)
    else:
        logger.debug(line)


def _scope_text(scope: GateScope) -> str:
    domains_text = "every domain (no scope file: hard zero)" if scope.domains is None else f"{sorted(scope.domains)}"
    buckets_text = f"{sorted(scope.buckets)}" if scope.buckets else "none"
    return f"domains={domains_text} buckets={buckets_text}"


def render_gate_report(
    evaluations: Sequence[RoleEvaluation], workspace_root: Path, *, scope: GateScope, debug: bool
) -> None:
    """Log one line per role (in-scope failures at ERROR, out-of-scope
    failures at INFO, passes at DEBUG unless *debug*), the per-bucket
    counts, the per-domain counts, and the gate summary.

    Args:
        evaluations: Every evaluated role.
        workspace_root: Root that member paths are displayed relative to.
        scope: The scope the evaluations were made under (for the summary).
        debug: Also log passing roles at INFO.
    """
    for evaluation in evaluations:
        _log_evaluation(evaluation, workspace_root, debug=debug)
    _log_bucket_counts([evaluation.verdict for evaluation in evaluations])
    domain_counts = Counter(evaluation.domain for evaluation in evaluations)
    logger.info(
        "BEHAVIOUR-PARITY DOMAINS: %d role(s) resolved to a shared domain, %d undomained; per domain: %s",
        sum(count for domain, count in domain_counts.items() if domain != UNDOMAINED),
        domain_counts[UNDOMAINED],
        dict(sorted(domain_counts.items())),
    )
    failing_in_scope = sum(evaluation.fails_in_scope for evaluation in evaluations)
    failing_out_of_scope = sum(evaluation.fails and not evaluation.in_scope for evaluation in evaluations)
    logger.info(
        "BEHAVIOUR-PARITY GATE: scope=%s -- %d role(s) FAIL in scope, %d failing role(s) REPORTED out of scope, "
        "%d role(s) pass.",
        _scope_text(scope),
        failing_in_scope,
        failing_out_of_scope,
        len(evaluations) - failing_in_scope - failing_out_of_scope,
    )


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

_SELF_TEST_ALPHA: Final[str] = "alpha"
_SELF_TEST_BETA: Final[str] = "beta"
_SELF_TEST_GAMMA: Final[str] = "gamma"
_SELF_TEST_OTHER: Final[str] = "other_pkg"
_SELF_TEST_MODULE: Final[str] = "mod.py"
#: A path root for synthetic members whose path only feeds the domain
#: ladder's step 3 (never read from disk).
_SELF_TEST_TREE: Final[Path] = Path("self-test-tree")
_SELF_TEST_REASON: Final[str] = "self-test synthetic reason -- never a real capability gap"
#: A synthetic builtin key and emit-function key for the synthetic EmitTable
#: surface 3 is exercised with -- deliberately no real registry row.
_SELF_TEST_BUILTIN_KEY: Final[BuiltinKey] = ("SelfTestOrder", "ship")
_SELF_TEST_EMIT_FUNCTION: Final[str] = "self_test_ship"
_SELF_TEST_UNKNOWN_SCOPE_ID: Final[str] = "bogus"
_SELF_TEST_UNKNOWN_BUCKET_ID: Final[str] = "not-a-verdict"
#: The synthetic importable package ``collect_emit_tables`` is exercised on.
_SELF_TEST_PACKAGE: Final[str] = "behaviour_parity_self_test_pkg"
#: The self-test's three-package divergent tree: two packages agreeing on
#: one behaviour, a third adding a fail-closed raise.
_SELF_TEST_AGREEING_SOURCE: Final[str] = "def divergent_thing(command):\n    return command.name\n"
_SELF_TEST_RAISING_SOURCE: Final[str] = (
    "def divergent_thing(command):\n    if not command.body:\n        raise ValueError('empty')\n    return command.name\n"
)
_SELF_TEST_DIVERGENT_ROLE: Final[str] = "divergent_thing"


@emit_adapter
def _self_test_emit_adapter(value: str) -> str:
    """The marked emit callable the self-test's synthetic ``EmitTable``
    registers -- defined here so its ``(defining file, __qualname__)``
    identity is this module's, matching a member the self-test parses from
    source text with ``file_path=Path(__file__)``. Registered by no language."""
    return value


def _assert(condition: bool, label: str) -> bool:
    """Print [OK]/[FAIL] for one self-test assertion and return it."""
    print(f"[OK] {label}" if condition else f"[FAIL] {label}")
    return condition


def _write_module(dir_path: Path, source: str, module_name: str = _SELF_TEST_MODULE) -> None:
    """Write one synthetic module for the self-test -- never a real package."""
    dir_path.mkdir(parents=True, exist_ok=True)
    (dir_path / module_name).write_text(textwrap.dedent(source), encoding="utf-8")


def _function_source(code: str, *, package: str, file_path: Path) -> FunctionSource:
    """A ``FunctionSource`` for the first top-level function in *code*, parsed
    as text with its own import table -- synthetic, nothing imported."""
    dedented = textwrap.dedent(code)
    module = ast.parse(dedented)
    node = next(node for node in module.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)))
    return FunctionSource(
        package=package,
        file_path=file_path,
        line_number=node.lineno,
        qualified_name=node.name,
        node=node,
        source_text=_decorated_source_segment(dedented.splitlines(keepends=True), node),
        import_table=build_import_table(module, package),
    )


def _synthetic_role(
    role_key: RoleKey, members: Sequence[FunctionSource], verdict: Verdict = _VERDICT_DIVERGENT
) -> RoleVerdict:
    """A hand-built role for the ladder/exemption cases (the scanner's own
    grouping is proven by cases (a)-(i))."""
    return RoleVerdict(
        role_key=role_key,
        kind="signature" if isinstance(role_key, SignatureRole) else "name",
        domain=None,
        verdict=verdict,
        members=tuple(members),
        adapter_exempt=False,
        rendering_leaf_exempt=False,
    )


def _plain_member(package: str, file_path: Path, name: str = "build_thing") -> FunctionSource:
    return _function_source(f"def {name}(value):\n    return value.strip()\n", package=package, file_path=file_path)


def _two_universe_ids() -> tuple[str, str]:
    """Two distinct real universe ids, computed -- never spelled -- so the
    self-test fabricates no domain id."""
    ids = sorted(SHARED_CONTEXT_TYPES)
    return ids[0], ids[1]


def _unsupported_declaration(domain: str) -> DomainDeclaration:
    return DomainDeclaration(domain_id=domain, status="unsupported", reason=_SELF_TEST_REASON)


def _supported_declaration(domain: str) -> DomainDeclaration:
    return DomainDeclaration(domain_id=domain, status="supported", structural_pattern="*/self_test/*.txt")


def _surfaces(
    *,
    stances: Mapping[str, Mapping[str, DomainDeclaration]] | None = None,
    on_demand: Mapping[str, Mapping[str, str]] | None = None,
    group_stances: Mapping[str, Mapping[str, BuiltinGroupStance]] | None = None,
    adapter_groups: Mapping[str, Mapping[AdapterIdentity, frozenset[str]]] | None = None,
) -> ExemptionSurfaces:
    """Synthetic surfaces with every omitted surface empty."""
    return ExemptionSurfaces(
        stance_table=stances if stances is not None else {},
        on_demand_by_language=on_demand if on_demand is not None else {},
        builtin_group_stances_by_language=group_stances if group_stances is not None else {},
        adapter_groups_by_language=adapter_groups if adapter_groups is not None else {},
    )


def _synthetic_registry(group: BuiltinGroup) -> Mapping[BuiltinKey, BuiltinDecl]:
    category, method = _SELF_TEST_BUILTIN_KEY
    return {
        _SELF_TEST_BUILTIN_KEY: BuiltinDecl(
            category=category,
            method=method,
            receiver=Receiver.STATIC,
            arity=ArityContract(min_args=0, max_args=0),
            group=group,
            rationale="self-test synthetic builtin -- never a real registry row",
        )
    }


def _synthetic_emit_table(group: BuiltinGroup) -> EmitTable[object]:
    """A real, validated ``EmitTable`` over the synthetic registry whose one
    row dispatches to ``_self_test_emit_adapter``."""
    return EmitTable(
        {_SELF_TEST_BUILTIN_KEY: emit_decl(sorted(KNOWN_CHAIN_STEPS)[0], _SELF_TEST_EMIT_FUNCTION)},
        registry=_synthetic_registry(group),
        emit_functions={_SELF_TEST_EMIT_FUNCTION: _self_test_emit_adapter},
    )


def _adapter_member(package: str) -> FunctionSource:
    """A member parsed from source text that spells THIS module's synthetic
    adapter with the real marker import, at this module's own path -- so its
    identity equals the registered callable's."""
    source = (
        f"from {emit_adapter.__module__} import {emit_adapter.__qualname__}\n\n"
        f"@{emit_adapter.__qualname__}\n"
        f"def {_self_test_emit_adapter.__name__}(value: str) -> str:\n"
        f"    return value\n"
    )
    return _function_source(source, package=package, file_path=Path(__file__))


class _RecordingHandler(logging.Handler):
    """Collects the formatted messages the gate report logs, so a case can
    assert a failure line names its role."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def _recorded_gate_lines(evaluations: Sequence[RoleEvaluation], scope: GateScope) -> list[str]:
    """Render the gate report into a recording handler (nothing reaches the
    real handlers) and return every line."""
    handler = _RecordingHandler()
    previous_level, previous_propagate = logger.level, logger.propagate
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    try:
        render_gate_report(evaluations, _SELF_TEST_TREE, scope=scope, debug=False)
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
        logger.propagate = previous_propagate
    return handler.messages


def _tokens(*labels: str) -> dict[str, frozenset[str]]:
    """Injected token vocabularies: each synthetic package's own label is
    its only token, so no real plugin is ever loaded by the self-test."""
    return {label: frozenset({label}) for label in labels}


def _scan(root: Path, labels: tuple[str, ...], other_labels: tuple[str, ...] = ()) -> list[RoleVerdict]:
    """Run the core scan over the synthetic packages ``root/<label>``."""
    return group_and_classify_roles(
        {label: root / label for label in labels},
        _tokens(*labels),
        [root / label for label in other_labels],
    )


def _name_roles(verdicts: list[RoleVerdict], name: str) -> list[RoleVerdict]:
    return [v for v in verdicts if isinstance(v.role_key, NameRole) and v.role_key.normalized_name == name]


def _signature_roles(verdicts: list[RoleVerdict]) -> list[RoleVerdict]:
    return [v for v in verdicts if isinstance(v.role_key, SignatureRole)]


def _single_role_with_verdict(matches: list[RoleVerdict], expected: Verdict) -> bool:
    return len(matches) == 1 and matches[0].verdict == expected


def _self_test_case_identical() -> bool:
    """(a) Byte-identical bodies across 3 synthetic packages land in exactly
    one ``identical`` role."""
    with tempfile.TemporaryDirectory(prefix="behaviour-parity-selftest-a-") as tmp:
        root = Path(tmp)
        body = "def helper_thing(value):\n    return value.strip()\n"
        for label in (_SELF_TEST_ALPHA, _SELF_TEST_BETA, _SELF_TEST_GAMMA):
            _write_module(root / label, body)
        verdicts = _scan(root, (_SELF_TEST_ALPHA, _SELF_TEST_BETA, _SELF_TEST_GAMMA))
        matches = _name_roles(verdicts, "helper_thing")
        return _single_role_with_verdict(matches, _VERDICT_IDENTICAL) and len(matches[0].members) == 3


def _self_test_case_same_behaviour() -> bool:
    """(b) Equal skeletons with different rendering (different string
    literals, different parameter names) land in ``same-behaviour``."""
    with tempfile.TemporaryDirectory(prefix="behaviour-parity-selftest-b-") as tmp:
        root = Path(tmp)
        _write_module(
            root / _SELF_TEST_ALPHA,
            "def rendered_thing(command):\n"
            "    if command.is_valid:\n"
            "        return 'alpha-ok'\n"
            "    return 'alpha-no'\n",
        )
        _write_module(
            root / _SELF_TEST_BETA,
            "def rendered_thing(cmd):\n    if cmd.is_valid:\n        return 'beta-ok'\n    return 'beta-no'\n",
        )
        verdicts = _scan(root, (_SELF_TEST_ALPHA, _SELF_TEST_BETA))
        return _single_role_with_verdict(_name_roles(verdicts, "rendered_thing"), _VERDICT_SAME_BEHAVIOUR)


def _self_test_case_divergent() -> bool:
    """(c) An added fail-closed raise branch lands the role in ``divergent``."""
    with tempfile.TemporaryDirectory(prefix="behaviour-parity-selftest-c-") as tmp:
        root = Path(tmp)
        _write_module(root / _SELF_TEST_ALPHA, _SELF_TEST_AGREEING_SOURCE)
        _write_module(root / _SELF_TEST_BETA, _SELF_TEST_RAISING_SOURCE)
        verdicts = _scan(root, (_SELF_TEST_ALPHA, _SELF_TEST_BETA))
        return _single_role_with_verdict(_name_roles(verdicts, _SELF_TEST_DIVERGENT_ROLE), _VERDICT_DIVERGENT)


def _self_test_case_token_split_unification() -> bool:
    """(d) A role visible ONLY after stripping each package's own injected
    language token (``build_alpha_x`` / ``build_beta_x`` -> ``build_x``);
    the raw names must not form roles of their own."""
    with tempfile.TemporaryDirectory(prefix="behaviour-parity-selftest-d-") as tmp:
        root = Path(tmp)
        _write_module(root / _SELF_TEST_ALPHA, "def build_alpha_x(value):\n    return value.strip()\n")
        _write_module(root / _SELF_TEST_BETA, "def build_beta_x(value):\n    return value.strip()\n")
        verdicts = _scan(root, (_SELF_TEST_ALPHA, _SELF_TEST_BETA))
        matches = _name_roles(verdicts, "build_x")
        unified = len(matches) == 1 and _distinct_packages(list(matches[0].members)) == 2
        raw_names_absent = not _name_roles(verdicts, "build_alpha_x") and not _name_roles(verdicts, "build_beta_x")
        return unified and raw_names_absent


def _self_test_case_signature_unification() -> bool:
    """(e) A role visible ONLY via a shared-typed signature: unrelated names,
    a fake shared-codegen-layer module path synthesized purely in the import
    table (parsed as text; nothing is imported), one member declaring the
    product through a forward-reference string wrapped in ``list[...]``, and
    differing inputs -- a language-private transpiler core and an extra
    shared-typed container parameter on one side only -- that must not
    split the role."""
    with tempfile.TemporaryDirectory(prefix="behaviour-parity-selftest-e-") as tmp:
        root = Path(tmp)
        shared_import = (
            "from datrix_common.datrix_model.containers import Service\n"
            "from datrix_codegen_common.orchestration.contexts.fake import CommandModel, ContextModel\n\n"
        )
        _write_module(
            root / _SELF_TEST_ALPHA,
            shared_import + "from alpha.core import AlphaCore\n\n"
            "def build_alpha_completely_different_name(cmd: CommandModel, core: AlphaCore) -> ContextModel:\n"
            "    return ContextModel()\n",
        )
        _write_module(
            root / _SELF_TEST_BETA,
            shared_import
            + "def build_beta_totally_unrelated_name(service: Service, cmd: 'CommandModel') -> 'list[ContextModel]':\n"
            "    return [ContextModel()]\n",
        )
        verdicts = _scan(root, (_SELF_TEST_ALPHA, _SELF_TEST_BETA))
        matches = _signature_roles(verdicts)
        unified = (
            len(matches) == 1
            and matches[0].role_key == SignatureRole("datrix_codegen_common.orchestration.contexts.fake.ContextModel")
            and _distinct_packages(list(matches[0].members)) == 2
        )
        return unified and not _name_roles(verdicts, "build_completely_different_name")


def _self_test_case_inputs_never_key_a_role() -> bool:
    """(e2) A shared-typed INPUT with no shared product keys a NAME role,
    never a signature role -- and a ``datrix_common`` return type is not a
    product either -- so hundreds of different jobs over one ``Service`` can
    never collapse into one role."""
    with tempfile.TemporaryDirectory(prefix="behaviour-parity-selftest-e2-") as tmp:
        root = Path(tmp)
        body = (
            "from datrix_common.datrix_model.containers import Service\n"
            "from datrix_common.generation.generator import GeneratedFile\n\n"
            "def {label}_label(service: Service) -> str:\n"
            "    return service.name\n\n"
            "def render_{label}_file(service: Service) -> GeneratedFile:\n"
            "    return GeneratedFile(service.name)\n"
        )
        for label in (_SELF_TEST_ALPHA, _SELF_TEST_BETA):
            _write_module(root / label, body.format(label=label))
        verdicts = _scan(root, (_SELF_TEST_ALPHA, _SELF_TEST_BETA))
        return (
            not _signature_roles(verdicts)
            and _single_role_with_verdict(_name_roles(verdicts, "label"), _VERDICT_SAME_BEHAVIOUR)
            and _single_role_with_verdict(_name_roles(verdicts, "render_file"), _VERDICT_SAME_BEHAVIOUR)
        )


def _self_test_case_adapter_exempt() -> bool:
    """(f) A pre-binding-adapter role (identical single-return-of-shared-call
    bodies) is marked ``adapter_exempt``; a non-adapter role is not."""
    with tempfile.TemporaryDirectory(prefix="behaviour-parity-selftest-f-") as tmp:
        root = Path(tmp)
        body = (
            "from datrix_codegen_common.algorithms.entity import build_entity_context\n\n"
            "def build_adapter_thing(entity, language_id):\n"
            "    return build_entity_context(entity, language_id)\n\n"
            "def build_deciding_thing(entity, language_id):\n"
            "    return build_entity_context(entity.name, language_id)\n"
        )
        _write_module(root / _SELF_TEST_ALPHA, body)
        _write_module(root / _SELF_TEST_BETA, body)
        verdicts = _scan(root, (_SELF_TEST_ALPHA, _SELF_TEST_BETA))
        adapters = _name_roles(verdicts, "build_adapter_thing")
        deciders = _name_roles(verdicts, "build_deciding_thing")
        return (
            _single_role_with_verdict(adapters, _VERDICT_IDENTICAL)
            and adapters[0].adapter_exempt
            and _single_role_with_verdict(deciders, _VERDICT_IDENTICAL)
            and not deciders[0].adapter_exempt
        )


def _self_test_case_excluded_by_other_package() -> bool:
    """(g) A name also bare-defined in a non-axis package is excluded
    entirely, even though >= 2 target packages define it."""
    with tempfile.TemporaryDirectory(prefix="behaviour-parity-selftest-g-") as tmp:
        root = Path(tmp)
        body = "def shared_named_helper(value):\n    return value.strip()\n"
        for label in (_SELF_TEST_ALPHA, _SELF_TEST_BETA, _SELF_TEST_OTHER):
            _write_module(root / label, body)
        with_other = _scan(root, (_SELF_TEST_ALPHA, _SELF_TEST_BETA), other_labels=(_SELF_TEST_OTHER,))
        without_other = _scan(root, (_SELF_TEST_ALPHA, _SELF_TEST_BETA))
        return not _name_roles(with_other, "shared_named_helper") and bool(
            _name_roles(without_other, "shared_named_helper")
        )


def _self_test_case_min_packages_refused() -> bool:
    """(h) A one-package map is refused, never silently compared."""
    try:
        _require_min_packages(AXIS_LANGUAGES, frozenset({_SELF_TEST_ALPHA}))
    except ValueError:
        return True
    return False


def _self_test_case_unparseable_member_fails_closed() -> bool:
    """(i) A syntax error in one member's file aborts the scan naming the
    file -- never a silent skip of that package."""
    with tempfile.TemporaryDirectory(prefix="behaviour-parity-selftest-i-") as tmp:
        root = Path(tmp)
        _write_module(root / _SELF_TEST_ALPHA, "def fine_thing(value):\n    return value\n")
        _write_module(root / _SELF_TEST_BETA, "def broken_thing(value:\n    return value\n")
        try:
            _scan(root, (_SELF_TEST_ALPHA, _SELF_TEST_BETA))
        except SkeletonError as exc:
            return _SELF_TEST_MODULE in str(exc)
        return False


def _self_test_case_domain_step_one() -> bool:
    """(j) Ladder step 1: a product type that is exactly one domain's rich
    context type resolves to that domain; a type several domains share
    (the test-plan context) never resolves at step 1 and, with members
    spelling no owning module, falls all the way to ``undomained``."""
    reverse = _rich_context_type_qualnames()
    unique = [(qualname, ids[0]) for qualname, ids in reverse.items() if len(ids) == 1]
    shared = [qualname for qualname, ids in reverse.items() if len(ids) > 1]
    if not unique or not shared:
        return False
    members = [
        _plain_member(label, _SELF_TEST_TREE / label / _SELF_TEST_MODULE)
        for label in (_SELF_TEST_ALPHA, _SELF_TEST_BETA)
    ]
    unique_role = _synthetic_role(SignatureRole(unique[0][0]), members)
    shared_role = _synthetic_role(SignatureRole(shared[0]), members)
    return resolve_domain(unique_role) == unique[0][1] and resolve_domain(shared_role) == UNDOMAINED


def _self_test_case_domain_step_two() -> bool:
    """(k) Ladder step 2: an unregistered type defined under a shared
    context-model module resolves through its module basename -- the
    ``persistence_`` prefix and the ``_render_contexts`` suffix stripped --
    while the same basename under an ineligible module does not."""
    domain, _ = _two_universe_ids()
    members = [
        _plain_member(label, _SELF_TEST_TREE / label / _SELF_TEST_MODULE)
        for label in (_SELF_TEST_ALPHA, _SELF_TEST_BETA)
    ]
    prefixed = SignatureRole(f"{_ELIGIBLE_CONTEXT_MODULE_PREFIXES[0]}{_CONTEXT_MODULE_PREFIX}{domain}.SyntheticContext")
    suffixed = SignatureRole(
        f"{_ELIGIBLE_CONTEXT_MODULE_PREFIXES[1]}{domain}{_CONTEXT_MODULE_SUFFIXES[0]}.SyntheticContext"
    )
    ineligible = SignatureRole(f"datrix_codegen_common.algorithms.{domain}.SyntheticContext")
    return (
        resolve_domain(_synthetic_role(prefixed, members)) == domain
        and resolve_domain(_synthetic_role(suffixed, members)) == domain
        and resolve_domain(_synthetic_role(ineligible, members)) == UNDOMAINED
    )


def _self_test_case_domain_step_three() -> bool:
    """(l) Ladder step 3: members under all four owning-module shapes agreeing
    on one universe id resolve to it; one disagreeing member, or a shape
    spelling a non-universe id, falls through to ``undomained``."""
    domain, other = _two_universe_ids()
    agreeing = [
        _plain_member(
            _SELF_TEST_ALPHA, _SELF_TEST_TREE / _SELF_TEST_ALPHA / _MICRO_GENERATORS_DIR / f"{domain}{_PY_SUFFIX}"
        ),
        _plain_member(
            _SELF_TEST_BETA, _SELF_TEST_TREE / _SELF_TEST_BETA / _HOOKS_DIR / f"{domain}{_HOOKS_MODULE_SUFFIX}"
        ),
        _plain_member(
            _SELF_TEST_GAMMA,
            _SELF_TEST_TREE / _SELF_TEST_GAMMA / _ORCHESTRATION_DIR / f"{domain}{_ORCHESTRATION_MODULE_SUFFIXES[1]}",
        ),
        _plain_member(
            _SELF_TEST_OTHER, _SELF_TEST_TREE / _SELF_TEST_OTHER / _GENERATORS_DIR / domain / _SELF_TEST_MODULE
        ),
    ]
    disagreeing = [
        *agreeing[:3],
        _plain_member(
            _SELF_TEST_OTHER, _SELF_TEST_TREE / _SELF_TEST_OTHER / _MICRO_GENERATORS_DIR / f"{other}{_PY_SUFFIX}"
        ),
    ]
    non_universe = [
        *agreeing[:3],
        _plain_member(_SELF_TEST_OTHER, _SELF_TEST_TREE / _SELF_TEST_OTHER / _MICRO_GENERATORS_DIR / "not_a_domain.py"),
    ]
    key = NameRole("build_thing")
    return (
        resolve_domain(_synthetic_role(key, agreeing)) == domain
        and resolve_domain(_synthetic_role(key, disagreeing)) == UNDOMAINED
        and resolve_domain(_synthetic_role(key, non_universe)) == UNDOMAINED
    )


def _self_test_case_domain_surfaces() -> bool:
    """(m) Surfaces 1 and 2: an ``unsupported`` stance or an on-demand entry
    for the ROLE'S domain sets the member package aside; a stance for another
    domain, a ``supported`` stance, no declaration at all, and any
    domain-keyed declaration on an ``undomained`` role do not."""
    domain, other = _two_universe_ids()
    role = _synthetic_role(
        NameRole("build_thing"),
        [
            _plain_member(label, _SELF_TEST_TREE / label / _MICRO_GENERATORS_DIR / f"{domain}{_PY_SUFFIX}")
            for label in (_SELF_TEST_ALPHA, _SELF_TEST_BETA)
        ],
    )
    beta = _SELF_TEST_BETA
    unsupported_here = _surfaces(stances={beta: {domain: _unsupported_declaration(domain)}})
    unsupported_elsewhere = _surfaces(stances={beta: {other: _unsupported_declaration(other)}})
    supported_here = _surfaces(stances={beta: {domain: _supported_declaration(domain)}})
    on_demand_here = _surfaces(on_demand={beta: {domain: _SELF_TEST_REASON}})
    on_demand_elsewhere = _surfaces(on_demand={beta: {other: _SELF_TEST_REASON}})
    undomained_keyed = _surfaces(
        stances={beta: {UNDOMAINED: _unsupported_declaration(UNDOMAINED)}},
        on_demand={beta: {UNDOMAINED: _SELF_TEST_REASON}},
    )
    return (
        not is_role_exempt(role, domain, beta, ExemptionSurfaces.none())
        and is_role_exempt(role, domain, beta, unsupported_here)
        and not is_role_exempt(role, domain, beta, unsupported_elsewhere)
        and not is_role_exempt(role, domain, beta, supported_here)
        and is_role_exempt(role, domain, beta, on_demand_here)
        and not is_role_exempt(role, domain, beta, on_demand_elsewhere)
        and not is_role_exempt(role, UNDOMAINED, beta, undomained_keyed)
    )


def _self_test_case_builtin_group_surface() -> bool:
    """(n) Surface 3: a marked adapter member whose synthetic ``EmitTable``
    row's builtin group the language declares ``unsupported`` is exempt --
    on an ``undomained`` role and on a domained one alike; a ``supported``
    stance, no stance, or a behaviour-bearing non-adapter member beside the
    adapter denies it."""
    group = sorted(BuiltinGroup, key=lambda member: member.value)[0]
    index = adapter_group_index((_synthetic_emit_table(group),), _synthetic_registry(group))
    beta = _SELF_TEST_BETA
    alpha_member = _plain_member(_SELF_TEST_ALPHA, _SELF_TEST_TREE / _SELF_TEST_ALPHA / _SELF_TEST_MODULE)
    adapter = _adapter_member(beta)
    role = _synthetic_role(NameRole(adapter.qualified_name), [alpha_member, adapter])
    mixed = _synthetic_role(
        NameRole(adapter.qualified_name), [alpha_member, adapter, _plain_member(beta, Path(__file__), name="deciding")]
    )
    unsupported = _surfaces(
        group_stances={beta: {group.value: BuiltinGroupStance("unsupported", _SELF_TEST_REASON)}},
        adapter_groups={beta: index},
    )
    supported = _surfaces(
        group_stances={beta: {group.value: BuiltinGroupStance("supported")}}, adapter_groups={beta: index}
    )
    unstanced = _surfaces(adapter_groups={beta: index})
    domain, _ = _two_universe_ids()
    return (
        index == {(Path(__file__).resolve(), _self_test_emit_adapter.__qualname__): frozenset({group.value})}
        and is_emit_adapter_member(adapter)
        and not is_emit_adapter_member(alpha_member)
        and is_role_exempt(role, UNDOMAINED, beta, unsupported)
        and is_role_exempt(role, domain, beta, unsupported)
        and not is_role_exempt(role, UNDOMAINED, beta, supported)
        and not is_role_exempt(role, UNDOMAINED, beta, unstanced)
        and not is_role_exempt(mixed, UNDOMAINED, beta, unsupported)
    )


def _self_test_case_builtin_group_surface_fails_closed() -> bool:
    """(o) Surface 3 failure paths: a marked adapter no table registers raises
    naming the member; a table over a registry missing its row raises; a
    same-named decorator from another module is not the marker."""
    group = sorted(BuiltinGroup, key=lambda member: member.value)[0]
    adapter = _adapter_member(_SELF_TEST_BETA)
    role = _synthetic_role(
        NameRole(adapter.qualified_name),
        [_plain_member(_SELF_TEST_ALPHA, _SELF_TEST_TREE / _SELF_TEST_ALPHA / _SELF_TEST_MODULE), adapter],
    )
    try:
        is_role_exempt(role, UNDOMAINED, _SELF_TEST_BETA, ExemptionSurfaces.none())
        return False
    except ValueError as exc:
        if adapter.qualified_name not in str(exc):
            return False
    try:
        adapter_group_index((_synthetic_emit_table(group),), {})
        return False
    except ValueError as exc:
        if repr(_SELF_TEST_BUILTIN_KEY) not in str(exc):
            return False
    impostor = _function_source(
        f"from somewhere_else import {emit_adapter.__qualname__}\n\n@{emit_adapter.__qualname__}\ndef build_thing(value):\n    return value\n",
        package=_SELF_TEST_BETA,
        file_path=Path(__file__),
    )
    return not is_emit_adapter_member(impostor)


def _self_test_case_scope_rules() -> bool:
    """(p) Scope: ``--scope``/``--buckets`` override the file, each half's
    file list applies when its flag is absent, an absent file means every
    domain and no bucket, an old-style domains-only file still loads with
    ``buckets=frozenset()``, and an unknown id (either origin, either half),
    an empty ``--scope``/``--buckets`` or a malformed file are refused
    naming the problem."""
    domain, other = _two_universe_ids()
    universe = frozenset(SHARED_CONTEXT_TYPES)
    with tempfile.TemporaryDirectory(prefix="behaviour-parity-selftest-p-") as tmp:
        present = Path(tmp) / "scope.json"
        present.write_text(json.dumps({_SCOPE_FILE_DOMAINS_KEY: [domain, UNDOMAINED]}), encoding="utf-8")
        with_buckets = Path(tmp) / "with-buckets.json"
        with_buckets.write_text(
            json.dumps({_SCOPE_FILE_DOMAINS_KEY: [domain], _SCOPE_FILE_BUCKETS_KEY: [_VERDICT_IDENTICAL]}),
            encoding="utf-8",
        )
        absent = Path(tmp) / "missing.json"
        malformed = Path(tmp) / "malformed.json"
        malformed.write_text(json.dumps({"other_key": [domain]}), encoding="utf-8")
        unknown_in_file = Path(tmp) / "unknown.json"
        unknown_in_file.write_text(
            json.dumps({_SCOPE_FILE_DOMAINS_KEY: [_SELF_TEST_UNKNOWN_SCOPE_ID]}), encoding="utf-8"
        )
        unknown_bucket_in_file = Path(tmp) / "unknown-bucket.json"
        unknown_bucket_in_file.write_text(
            json.dumps({_SCOPE_FILE_DOMAINS_KEY: [], _SCOPE_FILE_BUCKETS_KEY: [_SELF_TEST_UNKNOWN_BUCKET_ID]}),
            encoding="utf-8",
        )
        non_list_buckets_in_file = Path(tmp) / "non-list-buckets.json"
        non_list_buckets_in_file.write_text(
            json.dumps({_SCOPE_FILE_DOMAINS_KEY: [], _SCOPE_FILE_BUCKETS_KEY: _VERDICT_IDENTICAL}),
            encoding="utf-8",
        )
        non_string_bucket_in_file = Path(tmp) / "non-string-bucket.json"
        non_string_bucket_in_file.write_text(
            json.dumps({_SCOPE_FILE_DOMAINS_KEY: [], _SCOPE_FILE_BUCKETS_KEY: [_VERDICT_IDENTICAL, 1]}),
            encoding="utf-8",
        )
        rules_hold = (
            load_scope(None, None, universe, present)
            == GateScope(domains=frozenset({domain, UNDOMAINED}), buckets=frozenset())
            and load_scope(None, None, universe, absent) == GateScope(domains=None, buckets=frozenset())
            and load_scope((other,), None, universe, present)
            == GateScope(domains=frozenset({other}), buckets=frozenset())
            and load_scope(None, None, universe, with_buckets)
            == GateScope(domains=frozenset({domain}), buckets=frozenset({_VERDICT_IDENTICAL}))
            and load_scope(None, (_VERDICT_SAME_BEHAVIOUR,), universe, with_buckets)
            == GateScope(domains=frozenset({domain}), buckets=frozenset({_VERDICT_SAME_BEHAVIOUR}))
            and parse_scope_argument(f"{domain} {_SCOPE_SEPARATOR} {other}") == (domain, other)
            and parse_scope_argument(None) is None
            and parse_buckets_argument(f"{_VERDICT_IDENTICAL}{_SCOPE_SEPARATOR}{_VERDICT_SAME_BEHAVIOUR}")
            == (_VERDICT_IDENTICAL, _VERDICT_SAME_BEHAVIOUR)
            and parse_buckets_argument(None) is None
        )
        refusals_hold = (
            _refuses(
                lambda: load_scope((_SELF_TEST_UNKNOWN_SCOPE_ID,), None, universe, absent),
                _SELF_TEST_UNKNOWN_SCOPE_ID,
                UNDOMAINED,
            )
            and _refuses(
                lambda: load_scope(None, None, universe, unknown_in_file),
                _SELF_TEST_UNKNOWN_SCOPE_ID,
                str(unknown_in_file),
            )
            and _refuses(
                lambda: load_scope(None, None, universe, malformed), str(malformed), _SCOPE_FILE_DOMAINS_KEY
            )
            and _refuses(lambda: parse_scope_argument(_SCOPE_SEPARATOR), "--scope")
            and _refuses(
                lambda: load_scope(None, (_SELF_TEST_UNKNOWN_BUCKET_ID,), universe, absent),
                _SELF_TEST_UNKNOWN_BUCKET_ID,
                "--buckets",
            )
            and _refuses(
                lambda: load_scope(None, None, universe, unknown_bucket_in_file),
                _SELF_TEST_UNKNOWN_BUCKET_ID,
                str(unknown_bucket_in_file),
            )
            and _refuses(
                lambda: load_scope(None, None, universe, non_list_buckets_in_file),
                str(non_list_buckets_in_file),
                _SCOPE_FILE_BUCKETS_KEY,
                *sorted(_VALID_BUCKET_IDS),
            )
            and _refuses(
                lambda: load_scope(None, None, universe, non_string_bucket_in_file),
                str(non_string_bucket_in_file),
                _SCOPE_FILE_BUCKETS_KEY,
                *sorted(_VALID_BUCKET_IDS),
            )
            and _refuses(lambda: parse_buckets_argument(_SCOPE_SEPARATOR), "--buckets")
        )
        return rules_hold and refusals_hold


def _refuses(action: Callable[[], object], *expected_texts: str) -> bool:
    """Whether *action* raises ``ValueError`` whose message contains every one
    of *expected_texts*."""
    try:
        action()
    except ValueError as exc:
        return all(expected in str(exc) for expected in expected_texts)
    return False


def _divergent_tree_verdicts(domain: str) -> list[RoleVerdict]:
    """The synthetic three-package divergent tree under a real universe
    domain's owning-module shape: alpha and beta agree, gamma adds a
    fail-closed raise. Cases (q1)-(q3) and (r) all judge this one role."""
    with tempfile.TemporaryDirectory(prefix="behaviour-parity-selftest-divergent-") as tmp:
        root = Path(tmp)
        for label, source in (
            (_SELF_TEST_ALPHA, _SELF_TEST_AGREEING_SOURCE),
            (_SELF_TEST_BETA, _SELF_TEST_AGREEING_SOURCE),
            (_SELF_TEST_GAMMA, _SELF_TEST_RAISING_SOURCE),
        ):
            _write_module(root / label / _MICRO_GENERATORS_DIR, source, f"{domain}{_PY_SUFFIX}")
        return _scan(root, (_SELF_TEST_ALPHA, _SELF_TEST_BETA, _SELF_TEST_GAMMA))


def _self_test_case_skeleton_groups_fail_naming_every_group() -> bool:
    """(q1) A divergent role whose members split into two skeleton groups,
    no package declaring the construct unsupported, FAILS with one reason
    naming BOTH groups -- there is no reference language, so the gate cannot
    single out one side as lagging. Reordering the packages (so the group
    holding the raise comes first alphabetically) names the same groups."""
    domain, _ = _two_universe_ids()
    verdicts = _divergent_tree_verdicts(domain)
    role = _name_roles(verdicts, _SELF_TEST_DIVERGENT_ROLE)
    if not _single_role_with_verdict(role, _VERDICT_DIVERGENT):
        return False
    groups = skeleton_groups(role[0])
    evaluation = evaluate_role(role[0], scope=GateScope(domains=None, buckets=frozenset()), surfaces=ExemptionSurfaces.none())
    agreeing_group = _group_text((_SELF_TEST_ALPHA, _SELF_TEST_BETA))
    raising_group = _group_text((_SELF_TEST_GAMMA,))
    reason = evaluation.failure_reasons[0] if evaluation.failure_reasons else ""
    return (
        groups == (frozenset({_SELF_TEST_ALPHA, _SELF_TEST_BETA}), frozenset({_SELF_TEST_GAMMA}))
        and evaluation.fails_in_scope
        and len(evaluation.failure_reasons) == 1
        and "2 skeleton groups" in reason
        and agreeing_group in reason
        and raising_group in reason
        and "no member declares the construct unsupported" in reason
    )


def _self_test_case_declaring_package_set_aside() -> bool:
    """(q2) The same role PASSES when the package in the odd group declares
    the construct unsupported for the role's domain: one group remains. A
    declaration on a package in the OTHER group does not rescue it -- two
    groups still remain (one of them smaller) -- and the reason names the
    declaring package as the only one set aside."""
    domain, _ = _two_universe_ids()
    role = _name_roles(_divergent_tree_verdicts(domain), _SELF_TEST_DIVERGENT_ROLE)[0]
    no_scope = GateScope(domains=None, buckets=frozenset())
    odd_declares = evaluate_role(
        role, scope=no_scope, surfaces=_surfaces(stances={_SELF_TEST_GAMMA: {domain: _unsupported_declaration(domain)}})
    )
    other_declares = evaluate_role(
        role, scope=no_scope, surfaces=_surfaces(stances={_SELF_TEST_ALPHA: {domain: _unsupported_declaration(domain)}})
    )
    other_reason = other_declares.failure_reasons[0] if other_declares.failure_reasons else ""
    return (
        not odd_declares.fails
        and other_declares.fails_in_scope
        and _group_text((_SELF_TEST_BETA,)) in other_reason
        and _group_text((_SELF_TEST_GAMMA,)) in other_reason
        and f"only {_group_text((_SELF_TEST_ALPHA,))} declare(s)" in other_reason
    )


def _self_test_case_every_member_declares() -> bool:
    """(q3) A divergent role every member of which declares the construct
    unsupported passes -- a declared hole everywhere -- and is still
    reported: the evaluation exists, carries its domain, and prints a PASS
    line naming the role."""
    domain, _ = _two_universe_ids()
    verdicts = _divergent_tree_verdicts(domain)
    no_scope = GateScope(domains=None, buckets=frozenset())
    everyone = _surfaces(
        stances={
            label: {domain: _unsupported_declaration(domain)}
            for label in (_SELF_TEST_ALPHA, _SELF_TEST_BETA, _SELF_TEST_GAMMA)
        }
    )
    evaluations = evaluate_roles(verdicts, scope=no_scope, surfaces=everyone)
    lines = _recorded_gate_lines(evaluations, no_scope)
    return (
        len(evaluations) == 1
        and not evaluations[0].fails
        and evaluations[0].domain == domain
        and gate_exit_code(evaluations) == EXIT_OK
        and any(line.startswith("PASS ") and f"role={_SELF_TEST_DIVERGENT_ROLE}" in line for line in lines)
    )


def _self_test_case_bucket_labels() -> bool:
    """(q4) The bucket labels printed and accepted are exactly ``identical``,
    ``same-behaviour`` and ``divergent`` (invariant I12): the verdict type,
    the ``--buckets`` vocabulary, every verdict line and the summary line
    all spell them, and nothing else."""
    expected = frozenset({"identical", "same-behaviour", "divergent"})
    domain, _ = _two_universe_ids()
    verdicts = _divergent_tree_verdicts(domain)
    no_scope = GateScope(domains=None, buckets=frozenset())
    lines = _recorded_gate_lines(evaluate_roles(verdicts, scope=no_scope, surfaces=ExemptionSurfaces.none()), no_scope)
    summary = next((line for line in lines if line.startswith("BEHAVIOUR-PARITY REPORT:")), "")
    return (
        _VALID_BUCKET_IDS == expected
        and frozenset(Verdict.__args__) == expected
        and any(f"verdict={_VERDICT_DIVERGENT} " in line for line in lines)
        and all(f" {label} (" in summary or f" {label}." in summary for label in expected)
    )


def _self_test_case_gate_outcome() -> bool:
    """(r) End to end on a synthetic three-package tree: a divergent role in a
    real universe domain with NO declaration fails in scope (exit 1, the
    FAIL line names the role and every group); the same role with a synthetic
    ``unsupported`` stance passes (exit 0); with the domain out of ``--scope``
    it is REPORTED but does not fail (exit 0); an identical non-adapter role
    fails while an adapter-exempt one passes; and the platform axis never
    gates."""
    domain, other = _two_universe_ids()
    verdicts = _divergent_tree_verdicts(domain)
    if not _single_role_with_verdict(_name_roles(verdicts, _SELF_TEST_DIVERGENT_ROLE), _VERDICT_DIVERGENT):
        return False
    evaluate = functools.partial(evaluate_roles, verdicts)
    no_scope = GateScope(domains=None, buckets=frozenset())
    undeclared = evaluate(scope=no_scope, surfaces=ExemptionSurfaces.none())
    declared = evaluate(
        scope=no_scope, surfaces=_surfaces(stances={_SELF_TEST_GAMMA: {domain: _unsupported_declaration(domain)}})
    )
    out_of_scope_gate = GateScope(domains=frozenset({other}), buckets=frozenset())
    out_of_scope = evaluate(scope=out_of_scope_gate, surfaces=ExemptionSurfaces.none())
    in_scope = evaluate(scope=GateScope(domains=frozenset({domain}), buckets=frozenset()), surfaces=ExemptionSurfaces.none())
    undeclared_lines = _recorded_gate_lines(undeclared, no_scope)
    out_of_scope_lines = _recorded_gate_lines(out_of_scope, out_of_scope_gate)
    return (
        gate_exit_code(undeclared) == EXIT_FAIL
        and undeclared[0].domain == domain
        and any(
            line.startswith("FAIL ")
            and f"role={_SELF_TEST_DIVERGENT_ROLE}" in line
            and _group_text((_SELF_TEST_ALPHA, _SELF_TEST_BETA)) in line
            and _group_text((_SELF_TEST_GAMMA,)) in line
            for line in undeclared_lines
        )
        and gate_exit_code(declared) == EXIT_OK
        and gate_exit_code(out_of_scope) == EXIT_OK
        and out_of_scope[0].fails
        and any(
            line.startswith("REPORTED ") and f"role={_SELF_TEST_DIVERGENT_ROLE}" in line for line in out_of_scope_lines
        )
        and gate_exit_code(in_scope) == EXIT_FAIL
        and _duplicate_buckets_gate_correctly()
        and not axis_gates(AXIS_PLATFORMS, report_only=False)
        and axis_gates(AXIS_LANGUAGES, report_only=False)
        and not axis_gates(AXIS_LANGUAGES, report_only=True)
    )


def _duplicate_buckets_gate_correctly() -> bool:
    """Case (r)'s duplicate-bucket half: the adapter/decider tree of case (f)
    -- the adapter-exempt identical role passes, the deciding one fails."""
    with tempfile.TemporaryDirectory(prefix="behaviour-parity-selftest-r2-") as tmp:
        root = Path(tmp)
        body = (
            "from datrix_codegen_common.algorithms.entity import build_entity_context\n\n"
            "def build_adapter_thing(entity, language_id):\n"
            "    return build_entity_context(entity, language_id)\n\n"
            "def build_deciding_thing(entity, language_id):\n"
            "    return build_entity_context(entity.name, language_id)\n"
        )
        _write_module(root / _SELF_TEST_ALPHA, body)
        _write_module(root / _SELF_TEST_BETA, body)
        verdicts = _scan(root, (_SELF_TEST_ALPHA, _SELF_TEST_BETA))
    evaluations = {
        role_label(evaluation.verdict.role_key): evaluation
        for evaluation in evaluate_roles(
            verdicts,
            scope=GateScope(domains=None, buckets=frozenset()),
            surfaces=ExemptionSurfaces.none(),
        )
    }
    return (
        not evaluations["build_adapter_thing"].fails
        and evaluations["build_deciding_thing"].fails_in_scope
        and evaluations["build_deciding_thing"].domain == UNDOMAINED
    )


def _self_test_case_bucket_scope_gate() -> bool:
    """(t) Bucket-wide scope: a planted 'identical'-verdict role, with an
    EMPTY domains scope (so the domains half admits nothing), still FAILs
    when its verdict bucket is scoped (``buckets={"identical"}``), and is
    only REPORTED (fails, out of scope) when no bucket is scoped
    (``buckets=frozenset()``) -- the bucket key gates a verdict across every
    domain independently of the domains list."""
    domain, _ = _two_universe_ids()
    identical_body = "def shared_identical_thing(command):\n    return command.name\n"
    with tempfile.TemporaryDirectory(prefix="behaviour-parity-selftest-t-") as tmp:
        root = Path(tmp)
        for label in (_SELF_TEST_ALPHA, _SELF_TEST_BETA):
            _write_module(root / label / _MICRO_GENERATORS_DIR, identical_body, f"{domain}{_PY_SUFFIX}")
        verdicts = _scan(root, (_SELF_TEST_ALPHA, _SELF_TEST_BETA))
    if not _single_role_with_verdict(_name_roles(verdicts, "shared_identical_thing"), _VERDICT_IDENTICAL):
        return False
    evaluate = functools.partial(evaluate_roles, verdicts, surfaces=ExemptionSurfaces.none())
    bucket_gated = evaluate(scope=GateScope(domains=frozenset(), buckets=frozenset({_VERDICT_IDENTICAL})))
    bucket_ungated = evaluate(scope=GateScope(domains=frozenset(), buckets=frozenset()))
    return (
        gate_exit_code(bucket_gated) == EXIT_FAIL
        and bucket_gated[0].in_scope
        and gate_exit_code(bucket_ungated) == EXIT_OK
        and not bucket_ungated[0].in_scope
        and bucket_ungated[0].fails
    )


def _self_test_case_collect_emit_tables() -> bool:
    """(s) ``collect_emit_tables`` finds a table defined in a NESTED module of a
    synthetic importable package (no table-module name assumed), deduplicates
    a re-import, and refuses a package with an unimportable module naming it."""
    table_source = f"""
        from datrix_codegen_common.transpiler.builtin_registry import ArityContract, BuiltinDecl, BuiltinGroup, Receiver
        from datrix_codegen_common.transpiler.emit_dsl import EmitTable, emit_adapter, emit_decl

        @emit_adapter
        def ship(value):
            return value

        _REGISTRY = {{
            {_SELF_TEST_BUILTIN_KEY!r}: BuiltinDecl(
                category={_SELF_TEST_BUILTIN_KEY[0]!r}, method={_SELF_TEST_BUILTIN_KEY[1]!r}, receiver=Receiver.STATIC,
                arity=ArityContract(min_args=0, max_args=0), group=sorted(BuiltinGroup, key=lambda g: g.value)[0],
                rationale="self-test synthetic builtin",
            )
        }}
        NESTED_TABLE = EmitTable(
            {{{_SELF_TEST_BUILTIN_KEY!r}: emit_decl({sorted(KNOWN_CHAIN_STEPS)[0]!r}, {_SELF_TEST_EMIT_FUNCTION!r})}},
            registry=_REGISTRY,
            emit_functions={{{_SELF_TEST_EMIT_FUNCTION!r}: ship}},
        )
        """
    with tempfile.TemporaryDirectory(prefix="behaviour-parity-selftest-s-") as tmp:
        package_dir = Path(tmp) / _SELF_TEST_PACKAGE
        _write_module(package_dir, "", "__init__.py")
        _write_module(package_dir / "sub", "", "__init__.py")
        _write_module(package_dir / "sub", table_source, "tables.py")
        _write_module(
            package_dir,
            f"from {_SELF_TEST_PACKAGE}.sub.tables import NESTED_TABLE\n\nREIMPORTED = NESTED_TABLE\n",
            "reimport.py",
        )
        sys.path.insert(0, tmp)
        try:
            tables = collect_emit_tables(package_dir)
            found = len(tables) == 1 and _SELF_TEST_BUILTIN_KEY in tables[0].declared_keys
            _write_module(package_dir, "def broken(value:\n    return value\n", "broken.py")
            _forget_self_test_package()
            refused = _refuses(lambda: collect_emit_tables(package_dir), f"{_SELF_TEST_PACKAGE}.broken")
        finally:
            sys.path.remove(tmp)
            _forget_self_test_package()
    return found and refused


def _self_test_case_try_except_structure() -> bool:
    """(u) A member that wraps its only call in ``try/except ...: return
    False`` diverges from a sibling that makes the same call unguarded --
    the new try/except BOUNDARY, not just the extra ``return``, is what must
    show, since both members already contribute a matching ``return False``
    line inside their own control flow."""
    with tempfile.TemporaryDirectory(prefix="behaviour-parity-selftest-u-") as tmp:
        root = Path(tmp)
        _write_module(
            root / _SELF_TEST_ALPHA,
            "def guarded_thing(command):\n"
            "    if not command.ready:\n"
            "        return False\n"
            "    return True\n",
        )
        _write_module(
            root / _SELF_TEST_BETA,
            "def guarded_thing(command):\n"
            "    try:\n"
            "        if not command.ready:\n"
            "            return False\n"
            "    except ValueError:\n"
            "        return False\n"
            "    return True\n",
        )
        verdicts = _scan(root, (_SELF_TEST_ALPHA, _SELF_TEST_BETA))
        return _single_role_with_verdict(_name_roles(verdicts, "guarded_thing"), _VERDICT_DIVERGENT)


def _self_test_case_behaviour_arity() -> bool:
    """(v) Two members whose statement-level skeletons render identically
    but read a different number of real parameters (arity 3 vs 2, the geo
    query builder shape) land in ``divergent`` AND split into two skeleton
    groups, so the arity difference reaches the gate rather than hiding
    behind an equal statement-line skeleton."""
    with tempfile.TemporaryDirectory(prefix="behaviour-parity-selftest-v-") as tmp:
        root = Path(tmp)
        _write_module(root / _SELF_TEST_ALPHA, "def build_point(field, rest):\n    return field\n")
        _write_module(root / _SELF_TEST_BETA, "def build_point(entity_name, field, rest):\n    return field\n")
        verdicts = _scan(root, (_SELF_TEST_ALPHA, _SELF_TEST_BETA))
        matches = _name_roles(verdicts, "build_point")
        return _single_role_with_verdict(matches, _VERDICT_DIVERGENT) and len(skeleton_groups(matches[0])) == 2


def _self_test_case_rendering_leaf_exempt() -> bool:
    """(w) A role whose every member's body is a docstring-only carrier (the
    ``registry_definition`` shape -- no ``return`` at all) is
    ``rendering_leaf_exempt`` though it is not a pre-binding adapter."""
    with tempfile.TemporaryDirectory(prefix="behaviour-parity-selftest-w-") as tmp:
        root = Path(tmp)
        body = 'def registry_thing():\n    """\n    generator thing { }\n    """\n'
        _write_module(root / _SELF_TEST_ALPHA, body)
        _write_module(root / _SELF_TEST_BETA, body)
        verdicts = _scan(root, (_SELF_TEST_ALPHA, _SELF_TEST_BETA))
        matches = _name_roles(verdicts, "registry_thing")
        return (
            _single_role_with_verdict(matches, _VERDICT_IDENTICAL)
            and matches[0].rendering_leaf_exempt
            and not matches[0].adapter_exempt
        )


def _self_test_case_rendering_leaf_denies_private_callee() -> bool:
    """(x) A body with no branch and no attribute chain, but that calls a
    same-package sibling function, is NOT rendering-leaf-exempt --
    delegating to language-private logic is behaviour even when the
    delegating body itself makes no branch -- and the role stays
    ``same-behaviour`` (i.e. still fails the gate)."""
    with tempfile.TemporaryDirectory(prefix="behaviour-parity-selftest-x-") as tmp:
        root = Path(tmp)
        body = (
            "def _own_private_helper(value):\n    return value\n\n"
            "def leafy_thing(value):\n    return _own_private_helper(value)\n"
        )
        _write_module(root / _SELF_TEST_ALPHA, body)
        _write_module(root / _SELF_TEST_BETA, body)
        verdicts = _scan(root, (_SELF_TEST_ALPHA, _SELF_TEST_BETA))
        matches = _name_roles(verdicts, "leafy_thing")
        return _single_role_with_verdict(matches, _VERDICT_IDENTICAL) and not matches[0].rendering_leaf_exempt


def _self_test_case_role_level_arity() -> bool:
    """(y) Role-level arity: a parameter name a PRIVATE-annotated sibling
    drops as language-private plumbing is dropped for a SHARED-annotated
    member of the same role too (the ``emit_break_statement``/
    ``emit_continue_statement`` shape, where one language's file-scope
    subclass happens to live inside the shared layer while its siblings'
    live in their own packages) -- the role lands in ``same-behaviour``, not
    ``divergent``. A second, differently named role planted in the same
    synthetic tree, where one member takes a real extra unannotated
    parameter beside the same plumbing-shaped one, still lands in
    ``divergent``: the role-level rule drops a shared NAME, never a genuine
    extra input."""
    with tempfile.TemporaryDirectory(prefix="behaviour-parity-selftest-y-") as tmp:
        root = Path(tmp)
        _write_module(
            root / _SELF_TEST_ALPHA,
            "from datrix_common.transpiler.scope import FileScope\n\n\n"
            "def dispatch_role(scope: FileScope):\n"
            "    return scope\n\n\n"
            "def other_role(scope: FileScope, value):\n"
            "    return value\n",
        )
        _write_module(
            root / _SELF_TEST_BETA,
            "from behaviour_parity_selftest_beta.scope import BScope\n\n\n"
            "def dispatch_role(scope: BScope):\n"
            "    return scope\n\n\n"
            "def other_role(scope: BScope, value, extra):\n"
            "    return value\n",
        )
        _write_module(
            root / _SELF_TEST_GAMMA,
            "from behaviour_parity_selftest_gamma.scope import CScope\n\n\n"
            "def dispatch_role(scope: CScope):\n"
            "    return scope\n",
        )
        verdicts = _scan(root, (_SELF_TEST_ALPHA, _SELF_TEST_BETA, _SELF_TEST_GAMMA))
        dispatch = _name_roles(verdicts, "dispatch_role")
        other = _name_roles(verdicts, "other_role")
        return (
            _single_role_with_verdict(dispatch, _VERDICT_SAME_BEHAVIOUR)
            and len(dispatch[0].members) == 3
            and _single_role_with_verdict(other, _VERDICT_DIVERGENT)
        )


def _self_test_case_rendering_leaf_private_parameter_exemption() -> bool:
    """(z) A role reading nothing but a language-private parameter's
    attributes -- directly, and through a derived root bound from one --
    alongside a role whose trivial return makes no such read at all (the
    ``_ambient_request_import_line`` shape) lands ``same-behaviour
    rendering-leaf-exempt``, not a bare ``same-behaviour`` failure: neither
    member carries behaviour the skeleton itself would ever expose."""
    with tempfile.TemporaryDirectory(prefix="behaviour-parity-selftest-z-") as tmp:
        root = Path(tmp)
        _write_module(
            root / _SELF_TEST_ALPHA,
            "from behaviour_parity_selftest_alpha.ctx import AlphaContext\n\n\n"
            "def build_import_line(ctx: AlphaContext, helper):\n"
            "    module = ctx.transpiler.module_name\n"
            '    return f"import {module}.{helper}"\n',
        )
        _write_module(
            root / _SELF_TEST_BETA,
            "from behaviour_parity_selftest_beta.ctx import BetaContext\n\n\n"
            "def build_import_line(_ctx: BetaContext, helper):\n"
            '    return f"import {helper}"\n',
        )
        verdicts = _scan(root, (_SELF_TEST_ALPHA, _SELF_TEST_BETA))
        matches = _name_roles(verdicts, "build_import_line")
        return (
            _single_role_with_verdict(matches, _VERDICT_SAME_BEHAVIOUR)
            and matches[0].rendering_leaf_exempt
            and not matches[0].adapter_exempt
        )


def _forget_self_test_package() -> None:
    """Drop the synthetic package's modules from ``sys.modules`` so the case
    re-imports from disk and leaves nothing behind."""
    for name in [
        name for name in sys.modules if name == _SELF_TEST_PACKAGE or name.startswith(f"{_SELF_TEST_PACKAGE}.")
    ]:
        del sys.modules[name]


def run_self_test() -> bool:
    """Prove the gate's non-vacuity: each synthetic role lands in exactly its
    bucket, the refusal path refuses, a broken member fails closed, every
    ladder step and every exemption surface both fires and declines on
    synthetic input, the scope rules hold, and a synthetic divergent role
    with no declaration fails the gate while a declared one does not.

    Returns:
        True iff every assertion passed.
    """
    ok = True
    ok &= _assert(_self_test_case_identical(), "(a) byte-identical bodies land in exactly one 'identical' role")
    ok &= _assert(
        _self_test_case_same_behaviour(), "(b) equal skeletons, differing rendering, land in 'same-behaviour'"
    )
    ok &= _assert(_self_test_case_divergent(), "(c) an added raise branch lands the role in 'divergent'")
    ok &= _assert(
        _self_test_case_token_split_unification(),
        "(d) a role unified only by stripping each package's own language token",
    )
    ok &= _assert(
        _self_test_case_signature_unification(),
        "(e) a role unified only by its shared product type, names unrelated, differing inputs ignored",
    )
    ok &= _assert(
        _self_test_case_inputs_never_key_a_role(),
        "(e2) a shared-typed input with no shared product keys a name role, never a signature role",
    )
    ok &= _assert(
        _self_test_case_adapter_exempt(),
        "(f) a pre-binding-adapter role is adapter-exempt; a behaviour-bearing one is not",
    )
    ok &= _assert(
        _self_test_case_excluded_by_other_package(), "(g) a name also defined in a non-axis package is excluded"
    )
    ok &= _assert(_self_test_case_min_packages_refused(), "(h) a one-package map is refused, never silently compared")
    ok &= _assert(
        _self_test_case_unparseable_member_fails_closed(), "(i) an unparseable member aborts the scan naming its file"
    )
    ok &= _assert(
        _self_test_case_domain_step_one(),
        "(j) ladder step 1: a single-domain rich context type resolves; a many-domain type never does",
    )
    ok &= _assert(
        _self_test_case_domain_step_two(),
        "(k) ladder step 2: an eligible context module's basename resolves, affixes stripped; an ineligible one does not",
    )
    ok &= _assert(
        _self_test_case_domain_step_three(),
        "(l) ladder step 3: four owning-module shapes agreeing resolve; disagreement or a non-universe id is undomained",
    )
    ok &= _assert(
        _self_test_case_domain_surfaces(),
        "(m) surfaces 1+2: an unsupported stance / on-demand entry for the role's domain sets the package aside; "
        "wrong domain, supported, none, or an undomained role do not",
    )
    ok &= _assert(
        _self_test_case_builtin_group_surface(),
        "(n) surface 3: a marked adapter over an unsupported builtin group sets the package aside; supported, "
        "unstanced, or a behaviour-bearing sibling member do not",
    )
    ok &= _assert(
        _self_test_case_builtin_group_surface_fails_closed(),
        "(o) surface 3 fails closed: an unregistered marked adapter and a registry-less row raise naming the "
        "offender; a same-named foreign decorator is not the marker",
    )
    ok &= _assert(
        _self_test_case_scope_rules(),
        "(p) scope: --scope overrides the file, the file applies when --scope is absent, no file means every "
        "domain; unknown ids, an empty --scope and a malformed file are refused",
    )
    ok &= _assert(
        _self_test_case_skeleton_groups_fail_naming_every_group(),
        "(q1) a divergent role split into two skeleton groups with no declaration FAILs with one reason naming "
        "both groups -- no reference language, no lagging side",
    )
    ok &= _assert(
        _self_test_case_declaring_package_set_aside(),
        "(q2) the same role passes when the odd group's package declares the construct unsupported; a "
        "declaration in the other group leaves two groups and is named as the only one set aside",
    )
    ok &= _assert(
        _self_test_case_every_member_declares(),
        "(q3) a role every member of which declares the construct unsupported passes and is still reported",
    )
    ok &= _assert(
        _self_test_case_bucket_labels(),
        "(q4) the bucket labels printed and accepted are exactly identical / same-behaviour / divergent",
    )
    ok &= _assert(
        _self_test_case_gate_outcome(),
        "(r) gate: an undeclared divergent role FAILs in scope (exit 1, naming the role and every group); "
        "declared unsupported or out of scope it does not (exit 0); duplicate buckets fail unless adapter-exempt; "
        "the platform axis never gates",
    )
    ok &= _assert(
        _self_test_case_bucket_scope_gate(),
        "(t) buckets: a verdict-bucket gates every role of that verdict across every domain, independent of an "
        "empty domains scope; ungated the same role is reported only",
    )
    ok &= _assert(
        _self_test_case_collect_emit_tables(),
        "(s) emit tables: a table in a nested module of a synthetic package is found once; an unimportable module "
        "refuses the collection naming it",
    )
    ok &= _assert(
        _self_test_case_try_except_structure(),
        "(u) a try/except wrapper around an otherwise-matching call diverges from an unguarded sibling",
    )
    ok &= _assert(
        _self_test_case_behaviour_arity(),
        "(v) matching statement lines with a different real parameter count land in 'divergent' and split into "
        "two skeleton groups",
    )
    ok &= _assert(
        _self_test_case_rendering_leaf_exempt(),
        "(w) a docstring-only-body role is rendering-leaf-exempt though it is not a pre-binding adapter",
    )
    ok &= _assert(
        _self_test_case_rendering_leaf_denies_private_callee(),
        "(x) a leaf-shaped body calling a same-package private helper is denied the rendering-leaf exemption",
    )
    ok &= _assert(
        _self_test_case_role_level_arity(),
        "(y) role-level arity: a plumbing name any member drops is dropped for a shared-annotated sibling too, so "
        "a same-named parameter differing only in where its private subclass lives no longer splits the role; a "
        "genuine extra parameter beside it still does",
    )
    ok &= _assert(
        _self_test_case_rendering_leaf_private_parameter_exemption(),
        "(z) a role reading only a language-private parameter's attributes (directly and through a derived "
        "root), beside a role with no such read, lands same-behaviour rendering-leaf-exempt",
    )
    return ok


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Behaviour-parity gate: role grouping, behaviour-skeleton classification, domain resolution, "
            "declared exemptions and migration scope."
        )
    )
    parser.add_argument("--self-test", action="store_true", help="Run only the non-vacuity self-test.")
    parser.add_argument("--axis", choices=(AXIS_LANGUAGES, AXIS_PLATFORMS), default=AXIS_LANGUAGES)
    parser.add_argument(
        "--scope",
        default=None,
        help=(
            f"{_SCOPE_SEPARATOR!r}-separated shared domain ids and/or {UNDOMAINED!r} whose roles may fail; "
            f"overrides {BEHAVIOUR_PARITY_SCOPE_PATH.name}. Language axis only."
        ),
    )
    parser.add_argument(
        "--buckets",
        default=None,
        help=(
            f"{_SCOPE_SEPARATOR!r}-separated verdict-bucket ids, drawn from {sorted(_VALID_BUCKET_IDS)}, gated "
            f"across EVERY domain regardless of --scope/{BEHAVIOUR_PARITY_SCOPE_PATH.name}'s domains list; "
            f"overrides the file's {_SCOPE_FILE_BUCKETS_KEY!r} list. Language axis only."
        ),
    )
    parser.add_argument(
        "--report-only", action="store_true", help="Render the classification report only; exit 0 regardless."
    )
    parser.add_argument("--debug", action="store_true", help="Log every role, not just failing/divergent ones.")
    return parser


def _refuse_gate_options_when_not_gating(args: argparse.Namespace) -> None:
    """``--scope``/``--buckets`` shape a gate; on a run that renders a report
    only they would be silently ignored, so they are refused instead."""
    given = [name for name, value in (("--scope", args.scope), ("--buckets", args.buckets)) if value is not None]
    if given:
        raise ValueError(
            f"behaviour_parity: {given} only apply to a gating run (--axis {AXIS_LANGUAGES} without --report-only); "
            f"the {args.axis} axis {'with --report-only ' if args.report_only else ''}renders a report and never "
            f"fails. Fix: drop the option(s), or run the language axis without --report-only."
        )


def _run_scan(args: argparse.Namespace) -> int:
    """Discover, classify and -- on a gating run -- evaluate and gate.

    Returns:
        ``EXIT_OK`` or ``EXIT_FAIL`` (``gate_exit_code``); ``EXIT_OK`` for a
        report-only run.

    Raises:
        ValueError: A usage/discovery error (unknown scope or bucket id,
            unresolvable package, unimportable module, unregistered adapter).
        SkeletonError: An unparseable or unclassifiable member.
    """
    axis: str = args.axis
    target_names = registered_language_names() if axis == AXIS_LANGUAGES else registered_platform_names()
    target_src_dirs = discover_target_package_src_dirs(axis, target_names, WORKSPACE_ROOT)
    if not axis_gates(axis, report_only=args.report_only):
        _refuse_gate_options_when_not_gating(args)
        render_report(discover_roles_for(axis, target_src_dirs, WORKSPACE_ROOT), WORKSPACE_ROOT, debug=args.debug)
        return EXIT_OK
    scope = load_scope(
        parse_scope_argument(args.scope),
        parse_buckets_argument(args.buckets),
        frozenset(SHARED_CONTEXT_TYPES),
        BEHAVIOUR_PARITY_SCOPE_PATH,
    )
    logger.info("behaviour-parity gate: packages=%s scope=%s", sorted(target_src_dirs), _scope_text(scope))
    verdicts = discover_roles_for(axis, target_src_dirs, WORKSPACE_ROOT)
    surfaces = live_exemption_surfaces(target_src_dirs, BUILTIN_REGISTRY)
    evaluations = evaluate_roles(verdicts, scope=scope, surfaces=surfaces)
    render_gate_report(evaluations, WORKSPACE_ROOT, scope=scope, debug=args.debug)
    return gate_exit_code(evaluations)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Returns:
        ``EXIT_OK`` (self-test passed and no in-scope role fails, or the run
        was report-only), ``EXIT_FAIL`` (at least one in-scope role fails),
        ``EXIT_USAGE`` (self-test failed, usage error, fewer than two
        registered packages, or a discovery/parse error).
    """
    args = _build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if not run_self_test():
        logger.error("BEHAVIOUR-PARITY SELF-TEST FAILED -- aborting before any real scan is trusted.")
        return EXIT_USAGE
    logger.info("behaviour-parity self-test: PASS")

    if args.self_test:
        return EXIT_OK

    try:
        return _run_scan(args)
    except (ValueError, SkeletonError) as exc:
        logger.error("BEHAVIOUR-PARITY SCAN CANNOT RUN: %s", exc)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
