#!/usr/bin/env python3
"""Behaviour-parity gate: discovers every registered language (or platform)
package's module-level and class-method function definitions -- on the
language axis, also every registered `transpiler_profile`-bearing
`datrix.generators` client-target package's -- groups them into ROLES --
never by raw name, so a language token in a name can never hide a parallel
implementation -- classifies every role with two or more
member packages as ``identical``, ``same-behaviour``, or ``divergent``
using the behaviour-skeleton extractor, resolves each role to its owning
shared domain, and counts the roles the language-axis behaviour-parity
invariants say must fail against a pinned, two-directional baseline.

A per-target difference in generator BEHAVIOUR -- what is read from the
model, what is validated, what is emitted -- is a defect with as many copies
as there are disagreeing packages, never a choice to adjudicate. No language
is the reference: when copies disagree, the reconciliation takes the
strongest behaviour on each axis (fails closed, reads everything the DSL
declares, most secure, most correct output), and this gate cannot know which
copy that is. It therefore names every group of disagreeing packages, never
one "lagging" side.

Grouping keys, tried in order for every function:

0. **Coordinate role** (platform axis only) -- the capability a function
   realizes, resolved from the platform package's own registration table
   rather than from file layout or name shape. Every platform builds closed
   ``RealizationTable``s (``load_realization_table``) pairing each
   ``(block_type, flavor)`` cell it offers with the ``plan_builder`` function
   that realizes it. A function that is the plan builder of cells of exactly
   one block type is keyed by that block type: every flavor builder of one
   block type in one package folds into ONE role, because flavors are one
   platform's own vocabulary (``rds``/``aurora``, ``flexible-server``,
   ``container``) and a flavor-level key would give each role a single
   member package, which no comparison ever reads. A builder bound to cells
   of several block types (one uniform builder serving the whole table) names
   no single capability and falls through to the keys below. The language
   axis never builds this index, so the key cannot apply to it. A platform
   package whose tables cannot be imported or located fails the scan: it is
   never silently keyed by name instead.
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

Role verdicts (language-axis invariants I1 and I2)
--------------------------------------------------
- ``identical`` and ``same-behaviour`` fail unless every member is a
  pre-binding adapter or a rendering leaf (recognized by AST shape in
  ``behaviour_skeleton``; there is no written exemption for this bucket).
- ``divergent`` is judged without a reference language. The role's member
  packages are partitioned into SKELETON GROUPS: two packages share a group
  when the sets of ``(behaviour skeleton, behaviour arity)`` pairs their
  members contribute to the role are equal. The role PASSES iff at most one
  group remains once the one declared surface below is applied; otherwise it
  FAILS with one reason naming every remaining group -- the gate cannot
  know which group carries the correct behaviour, so it names all of them.
  No capability declaration, builtin-group stance, domain stance or
  ``capability_gaps`` row sets a package aside: a capability a target does
  not realize is a counted gap, and its roles stay in the failing-role count
  until the behaviour is reconciled.

Population ratchet (the gate's verdict)
---------------------------------------
Every role the scan measures is in scope -- every bucket, every domain, and
a role the domain ladder resolves to ``undomained`` exactly like any other.
No file, flag or domain id narrows the measured population. The verdict is
one number per gated axis: the count of failing roles, compared in BOTH
directions with the pin in
``datrix/scripts/config/behaviour-parity-baseline.toml``.

- A count ABOVE the pin fails: a role regressed or a new failing role
  appeared.
- A count BELOW the pin fails too, unless the pin is lowered in the same
  change: a reconciliation is provable only once it is banked, and an
  un-banked decrease would let the next regression hide in the slack.
- The per-bucket split beside the pin (``identical`` / ``same_behaviour`` /
  ``divergent``) counts the FAILING roles by verdict. It is diagnostic and
  never part of the verdict: a split that no longer matches the live one is
  reported as a note and moves no exit code.

The baseline loader refuses an unrecognized top-level section or key. Both
axes gate, each against its own section (``[languages]``, ``[platforms]``).
The pins are seeded from a live run, never copied from a document.

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
The resolved domain orders the reconciliation worklist and serves the
``--scope`` report filter; it never changes a role's verdict, and an
``undomained`` role fails and is counted exactly like a domained one.

No set-aside
------------
No member package is ever set aside in the divergence check: a role is judged
by its members' skeleton groups alone, whatever any package declares. No
declaration is an input to a verdict, and no classification file exists
(invariant I11).

Report filters
--------------
``--scope <id>[,<id>...]`` -- universe ids plus the literal ``undomained`` --
and ``--buckets <id>[,<id>...]`` -- verdict names (``identical``,
``same-behaviour``, ``divergent``) -- choose which role lines the report
PRINTS; a role prints when it satisfies every filter given. They never reach
the verdict: the failing-role count, the ratchet comparison and the exit code
are computed over every role either way. An unknown id is a usage error
naming the valid options, and both filters are refused on a run that renders
no gate report.

Fail-closed rule: an unparseable file, an unparseable string annotation, a
member the skeleton extractor cannot classify, a baseline file that is
missing, malformed or carries an unrecognized key, or an axis with no
baseline section is a reported failure naming the offender -- never a skip.

Exit codes: 0 the failing-role count equals its pin; 1 the count differs from
its pin (above it: a regression; below it: an improvement whose pin was not
lowered in the same change); 2 usage error, discovery/parse failure, or
self-test failure. ``--report-only`` renders the report and exits 0 on
either axis.

Fingerprint pass (report-only)
-------------------------------
``--fingerprint`` runs a second, independent pass after the role report: it
takes every function in a role with fewer than ``_MIN_PACKAGES_FOR_COMPARISON``
distinct member packages -- the set no name/signature role compares
(``uncovered_functions``) -- and re-groups them across packages by a
BEHAVIOUR FINGERPRINT: the function's control shape (``skeleton_shape``,
every predicate/chain/operand dropped, only the ordered statement heads kept)
paired with the set of model attribute names it reads
(``model_attribute_names``). A pre-binding adapter, a rendering leaf, a
skeleton under ``FINGERPRINT_MIN_SKELETON_LINES`` lines, or a function
reading no model attribute is never a candidate -- too little behaviour to
identify a job, or nothing to identify one BY. A bucket that spans fewer than
two distinct packages is dropped the same way an under-covered role is.

Each surviving cross-package group is judged by the SAME verdict rules a
name/signature role uses (``_classify_role``): ``identical``,
``same-behaviour``, or ``divergent`` -- no second classifier. A group is also
labelled ``match`` when every member's exact behaviour skeleton is equal, or
``near-match`` when the shape and the model attributes agree but at least one
member's skeleton text differs (a divergent detail inside an otherwise
shared job). The pass never reaches the ratchet verdict, the baseline, or the
report filters -- it is report-only, and the exit code is identical with and
without ``--fingerprint``. It is gated only once its first measurement is
worked down, which this pass does not do.

Usage:
    python behaviour_parity.py --self-test
    python behaviour_parity.py --axis languages [--scope queue,cache] [--buckets identical] [--debug]
    python behaviour_parity.py --axis languages --report-only [--debug]
    python behaviour_parity.py --axis platforms [--scope queue,cache] [--buckets divergent] [--debug]
    python behaviour_parity.py --axis platforms --report-only [--debug]
    python behaviour_parity.py --axis languages --fingerprint [--debug]
"""

from __future__ import annotations

import argparse
import ast
import dataclasses
import functools
import importlib
import inspect
import logging
import sys
import tempfile
import textwrap
import tomllib
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from importlib.metadata import EntryPoint
from pathlib import Path
from types import FunctionType, MappingProxyType
from typing import Final, Literal

_LIBRARY_DIR = Path(__file__).resolve().parent.parent
if _LIBRARY_DIR.exists() and str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from datrix_codegen_common.testkit.fixtures.fixtureclient import (  # noqa: E402
    FIXTURECLIENT_CAPABILITY_DECLARATION,
    fixture_client_target_descriptor,
)
from datrix_codegen_common.parity.domain_registry import (  # noqa: E402
    _RICH_CONTEXT_TYPES,
    SHARED_CONTEXT_TYPES,
)
from datrix_codegen_common.transpiler.emit_dsl import emit_adapter  # noqa: E402
from datrix_common.errors.plugin import PluginNotFoundError  # noqa: E402
from datrix_common.plugin import registry as registry_module  # noqa: E402
from datrix_common.plugin.capability_resolution import declaration_for_language  # noqa: E402
from datrix_common.plugin.client_capability import ClientTargetCapabilityDeclaration  # noqa: E402
from datrix_common.plugin.descriptor import PluginDescriptor  # noqa: E402
from datrix_common.plugin.registry import GENERATOR_GROUP, PluginRegistry  # noqa: E402
from datrix_codegen_kernel.platform.realization_dsl import (  # noqa: E402
    RealizationCell,
    RealizationTable,
)
from shared.registered_targets import (  # noqa: E402
    AXIS_LANGUAGES,
    AXIS_PLATFORMS,
    DATRIX_DIR,
    WORKSPACE_ROOT,
    all_src_dirs,
    discover_all_other_package_src_dirs,
    discover_all_package_locations,
    discover_client_target_generator_src_dirs,
    discover_target_package_src_dirs,
    registered_client_target_generator_names,
    registered_language_names,
    registered_platform_names,
    resolve_target_src_dirs,
)

from test.behaviour_skeleton import (  # noqa: E402
    FunctionSource,
    SkeletonError,
    behaviour_arity,
    behaviour_skeleton,
    build_import_table,
    is_pre_binding_adapter,
    is_rendering_leaf,
    model_attribute_names,
    normalized_source,
    parse_module_or_raise,
    plumbing_parameter_names,
    skeleton_shape,
)

logger = logging.getLogger(__name__)

EXIT_OK: Final[int] = 0
#: The failing-role count differs from its pin, in either direction.
EXIT_FAIL: Final[int] = 1
#: Also argparse's own usage-error exit code: a failed self-test, a
#: single-package axis, an unknown filter id, an unreadable baseline, and a
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
#: The three bucket labels, exactly as printed and accepted -- these three
#: spellings are the whole verdict vocabulary.
Verdict = Literal["identical", "same-behaviour", "divergent"]
_VERDICT_IDENTICAL: Final[Verdict] = "identical"
_VERDICT_SAME_BEHAVIOUR: Final[Verdict] = "same-behaviour"
_VERDICT_DIVERGENT: Final[Verdict] = "divergent"
#: One member's measured behaviour: its skeleton and its role-level arity --
#: the pair ``_classify_role`` compares and ``skeleton_groups`` partitions on.
BehaviourPair = tuple[str, int]

#: The domain of a role the resolution ladder maps to no shared domain id.
#: Also a valid ``--scope`` id, so a report can be filtered to the roles that
#: resolve nowhere; the role is counted by the ratchet like any other.
UNDOMAINED: Final[str] = "undomained"
_FILTER_SEPARATOR: Final[str] = ","
#: The only valid ``--buckets`` entries: the three verdict names a role can
#: classify as.
_VALID_BUCKET_IDS: Final[frozenset[str]] = frozenset(
    {_VERDICT_IDENTICAL, _VERDICT_SAME_BEHAVIOUR, _VERDICT_DIVERGENT}
)
#: Only a product type defined under one of these shared modules is eligible
#: for ladder step 2 (module-basename resolution). The target-neutral context
#: models (serverless, migration, replayable ingestion, NoSQL connection) live
#: in the kernel; the language-shaped ones in the language layer.
_ELIGIBLE_CONTEXT_MODULE_PREFIXES: Final[tuple[str, ...]] = (
    "datrix_codegen_kernel.context_models.",
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


@dataclass(frozen=True)
class CoordinateRole:
    """A platform-axis role: the block type (capability) whose realization a
    function builds, resolved from the platform package's own
    ``RealizationTable`` registration -- never from file layout or name
    shape. Tried before the signature and name keys, on the platform axis
    only."""

    block_type: str


RoleKey = SignatureRole | NameRole | CoordinateRole
RoleKind = Literal["signature", "name", "coordinate"]


def role_kind(role_key: RoleKey) -> RoleKind:
    """The report spelling of *role_key*'s key type."""
    if isinstance(role_key, CoordinateRole):
        return "coordinate"
    if isinstance(role_key, SignatureRole):
        return "signature"
    return "name"


@dataclass(frozen=True)
class RoleVerdict:
    """One role's classification, naming every member by ``package:file:line``.

    ``group_and_classify_roles`` leaves ``domain`` as ``None`` -- grouping
    and classification never resolve a domain; ``evaluate_role`` fills it in
    from the resolution ladder (``resolve_domain``) and records the filled-in
    verdict on its ``RoleEvaluation``.
    """

    role_key: RoleKey
    kind: RoleKind
    domain: str | None
    verdict: Verdict
    members: tuple[FunctionSource, ...]
    adapter_exempt: bool
    rendering_leaf_exempt: bool


# ---------------------------------------------------------------------------
# Token vocabulary
# ---------------------------------------------------------------------------


#: Shared registry the client-target token fallback resolves against; not
#: ``Final`` -- the self-test temporarily substitutes a fixture registry
#: (under a monkeypatched entry-point seam) and restores this exact instance
#: afterward.
_CLIENT_TARGET_REGISTRY: PluginRegistry = PluginRegistry()


def _client_target_capability_declaration(
    name: str, registry: PluginRegistry | None = None
) -> ClientTargetCapabilityDeclaration:
    """The ``ClientTargetCapabilityDeclaration`` of the ``datrix.generators``
    native plugin registered as *name* -- construction-free (reads the
    already-discovered class's own ``descriptor``; the plugin is never
    instantiated), the client-target sibling of ``declaration_for_language``'s
    "read the plugin's own declared facts, never guess" contract.

    Args:
        name: A registered `datrix.generators` entry-point name.
        registry: Registry to resolve against; defaults to the module-level
            shared registry. Tests pass a registry seeded with fixture
            generator plugins.

    Returns:
        The plugin's declared `ClientTargetCapabilityDeclaration`.

    Raises:
        PluginNotFoundError: If *name* names no installed `datrix.generators`
            plugin, or that plugin's descriptor carries no
            `client_capabilities` -- naming the installed client-target
            generators actually available.
    """
    reg = registry if registry is not None else _CLIENT_TARGET_REGISTRY
    classes = reg.list_native_generator_classes()
    descriptor = getattr(classes.get(name), "descriptor", None)
    declaration = descriptor.client_capabilities if descriptor is not None else None
    if declaration is not None:
        return declaration
    available = sorted(
        candidate_name
        for candidate_name, candidate_cls in classes.items()
        if getattr(candidate_cls, "descriptor", None) is not None
        and candidate_cls.descriptor.client_capabilities is not None
    )
    raise PluginNotFoundError(
        f"No '{GENERATOR_GROUP}' plugin registered as {name!r} declares a "
        f"'client_capabilities' ClientTargetCapabilityDeclaration. Installed "
        f"client-target generator plugins with a capability declaration: "
        f"{', '.join(available) if available else '(none)'}. Fix: register "
        f"{name!r} under '{GENERATOR_GROUP}' with a PluginDescriptor carrying "
        f"a non-None client_capabilities, or spell a registered client-target "
        f"generator name."
    )


def _name_tokens_for_language_axis_member(name: str) -> frozenset[str]:
    """One language-axis member's own declared name tokens: a
    ``datrix.languages`` plugin's ``LanguageCapabilityDeclaration.name_tokens``,
    tried first -- falling back to a ``datrix.generators`` client-target
    plugin's ``ClientTargetCapabilityDeclaration.name_tokens`` when no
    language plugin is registered under *name*. Never guessed from the bare
    registered name alone -- ``tokens_for`` already unions that separately.

    Args:
        name: A single registered name folded into a `tokens_for` label.

    Returns:
        The member's own declared name-token vocabulary.

    Raises:
        PluginNotFoundError: If *name* resolves to neither a registered
            language plugin nor a registered client-target generator plugin
            with a capability declaration.
    """
    try:
        return declaration_for_language(name).name_tokens
    except PluginNotFoundError:
        return _client_target_capability_declaration(name).name_tokens


def tokens_for(axis: str, label: str) -> frozenset[str]:
    """The name-token vocabulary for one registered target label.

    On the language axis: each name folded into *label* contributes its OWN
    declared name tokens, unioned with the bare name itself --
    ``LanguageCapabilityDeclaration.name_tokens`` for a ``datrix.languages``
    plugin, tried first; a ``datrix.generators`` client-target plugin's
    ``ClientTargetCapabilityDeclaration.name_tokens`` on fall-back, when no
    language plugin resolves for that name (see
    ``_name_tokens_for_language_axis_member``). On the platform axis: the
    bare registered name(s) only -- platform declarations carry no
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
        tokens |= _name_tokens_for_language_axis_member(name) | {name}
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
        module_name: A dotted module path (e.g. ``"datrix_codegen_kernel.platform"``).

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
    from the ``platform`` package re-export, Azure/Docker from the
    ``platform.value_objects`` submodule; the two textually
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


#: ``(defining file, __qualname__)`` of a function -- what a registered plan
#: builder and a scanned ``FunctionSource`` both reduce to.
BuilderIdentity = tuple[Path, str]
#: Every registered plan builder that realizes exactly one block type.
CoordinateIndex = Mapping[BuilderIdentity, CoordinateRole]

_REALIZATION_LOADER_NAME: Final[str] = "load_realization_table"
#: Bound on following a plan builder through delegating adapters to the
#: function that holds the behaviour.
_MAX_BUILDER_HOPS: Final[int] = 5
_PACKAGE_INIT_STEM: Final[str] = "__init__"


def _function_identity(function: FunctionType) -> BuilderIdentity:
    return Path(function.__code__.co_filename).resolve(), function.__qualname__


def _defining_function(builder: object, description: str) -> FunctionType:
    """The function that holds *builder*'s behaviour.

    A bound method resolves to its function. A closure defined inside another
    function (the delegating adapter that gives a one-argument provisioner the
    two-argument plan-builder shape) resolves to the single callable it
    closes over. Anything else that is not a plain function is refused.

    Args:
        builder: A ``RealizationCell.plan_builder``.
        description: The cell, named in every error.

    Raises:
        ValueError: *builder* is not a function, a bound method, or a
            closure over exactly one callable, or the chain does not end.
    """
    current = builder
    for _ in range(_MAX_BUILDER_HOPS):
        if inspect.ismethod(current):
            current = current.__func__
            continue
        if not isinstance(current, FunctionType):
            raise ValueError(
                f"behaviour_parity:{description} binds a plan builder of type {type(current).__name__}, which is "
                f"neither a function nor a bound method. Fix: bind a plain function or bound method."
            )
        if "<locals>" not in current.__qualname__:
            return current
        delegates = [cell.cell_contents for cell in current.__closure__ or () if callable(cell.cell_contents)]
        if len(delegates) != 1:
            raise ValueError(
                f"behaviour_parity:{description} binds the nested function {current.__qualname__!r}, which closes "
                f"over {len(delegates)} callable(s); an adapter must delegate to exactly one so the function "
                f"holding the behaviour is identifiable. Fix: bind the delegate itself, or adapt it through a "
                f"closure over that one callable."
            )
        current = delegates[0]
    raise ValueError(
        f"behaviour_parity:{description} binds a plan builder that is still an adapter after {_MAX_BUILDER_HOPS} "
        f"delegation hops. Fix: bind the function that holds the behaviour."
    )


def coordinate_index_from_tables(tables: Iterable[RealizationTable]) -> dict[BuilderIdentity, CoordinateRole]:
    """``{builder identity: CoordinateRole}`` for every plan builder the
    *tables* bind to cells of exactly one block type.

    Every flavor builder of one block type resolves to that one role. A
    builder bound to cells of several block types names no single capability
    and is left out, so its function keeps its signature or name key.

    Args:
        tables: Closed ``RealizationTable``s of one or more platforms.

    Raises:
        ValueError: A cell's plan builder cannot be resolved to a function.
    """
    block_types: dict[BuilderIdentity, set[str]] = {}
    for table in tables:
        for (block_type, flavor), cell in table.items():
            if cell.plan_builder is None:
                continue
            function = _defining_function(cell.plan_builder, f"RealizationTable cell ({block_type!r}, {flavor!r})")
            block_types.setdefault(_function_identity(function), set()).add(block_type)
    return {
        identity: CoordinateRole(block_type=next(iter(kinds)))
        for identity, kinds in block_types.items()
        if len(kinds) == 1
    }


def _module_name_for(src_dir: Path, py_file: Path) -> str:
    package = _dotted_package_for_file(src_dir, py_file)
    return package if py_file.stem == _PACKAGE_INIT_STEM else f"{package}.{py_file.stem}"


def _is_loader_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
    return name == _REALIZATION_LOADER_NAME


def _table_names_in(module: ast.Module, py_file: Path) -> list[str]:
    """The module-level names bound to ``load_realization_table(...)`` results.

    Raises:
        ValueError: A ``load_realization_table`` call is not the value of a
            module-level assignment, so the table it builds cannot be located
            by name.
    """
    names: list[str] = []
    for stmt in module.body:
        if isinstance(stmt, ast.AnnAssign) and _is_loader_call(stmt.value) and isinstance(stmt.target, ast.Name):
            names.append(stmt.target.id)
        elif (
            isinstance(stmt, ast.Assign)
            and _is_loader_call(stmt.value)
            and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
        ):
            names.append(stmt.targets[0].id)
    calls = sum(1 for node in ast.walk(module) if _is_loader_call(node))
    if calls != len(names):
        raise ValueError(
            f"behaviour_parity:{py_file} calls {_REALIZATION_LOADER_NAME} {calls} time(s) but only {len(names)} "
            f"call(s) are the value of a module-level assignment. Fix: bind each table to a module-level name so "
            f"the gate can locate it."
        )
    return names


def _import_table(module_name: str, attribute: str, platform_label: str) -> RealizationTable:
    """The ``RealizationTable`` *module_name* binds to *attribute*.

    Raises:
        ValueError: The module cannot be imported, lacks the attribute, or the
            attribute is not a mapping of ``RealizationCell``.
    """
    where = f"platform {platform_label!r} table {module_name}.{attribute}"
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise ValueError(
            f"behaviour_parity:cannot import {module_name} to read {where} ({exc}). Fix: install the platform "
            f"package into the shared venv."
        ) from exc
    table = getattr(module, attribute, None)
    if not isinstance(table, Mapping) or not all(isinstance(cell, RealizationCell) for cell in table.values()):
        raise ValueError(
            f"behaviour_parity:{where} is not a mapping of RealizationCell (found {type(table).__name__}). Fix: "
            f"bind the result of {_REALIZATION_LOADER_NAME} to that name."
        )
    return table


def platform_realization_tables(platform_label: str, src_dirs: Sequence[Path]) -> list[RealizationTable]:
    """Every ``RealizationTable`` the platform package under *src_dirs*
    builds, located by parsing its source for ``load_realization_table``
    call sites and imported by the module and name each one is bound to.

    Args:
        platform_label: The platform package label, named in errors.
        src_dirs: The package's src roots.

    Raises:
        ValueError: A table cannot be located or imported, or the package
            builds none -- a platform with no registration table would
            silently key every function by name.
    """
    tables: list[RealizationTable] = []
    for src_dir in src_dirs:
        for py_file in sorted(src_dir.rglob("*.py")):
            for name in _table_names_in(parse_module_or_raise(py_file), py_file):
                tables.append(_import_table(_module_name_for(src_dir, py_file), name, platform_label))
    if not tables:
        raise ValueError(
            f"behaviour_parity:platform {platform_label!r} builds no RealizationTable under "
            f"{[str(src_dir) for src_dir in src_dirs]}; the coordinate role key has nothing to resolve. Fix: "
            f"register the platform's cells through {_REALIZATION_LOADER_NAME}."
        )
    return tables


def platform_coordinate_index(
    target_src_dirs: Mapping[str, tuple[Path, ...]],
) -> dict[BuilderIdentity, CoordinateRole]:
    """The coordinate index of every platform in *target_src_dirs* -- the one
    place the platform axis reads each package's own registration tables.

    Raises:
        ValueError: A platform's tables cannot be located, imported or resolved.
    """
    tables: list[RealizationTable] = []
    for label, src_dirs in target_src_dirs.items():
        tables.extend(platform_realization_tables(label, src_dirs))
    return coordinate_index_from_tables(tables)


def _coordinate_role_key_for(fn: FunctionSource, index: CoordinateIndex) -> CoordinateRole | None:
    """The role *fn*'s registration identifies, or ``None`` when *fn* is no
    registered plan builder of a single block type -- the caller then keys it
    by the existing signature-then-name ladder, unchanged."""
    return index.get((fn.file_path.resolve(), fn.qualified_name))


def _role_key_for(
    fn: FunctionSource, tokens: frozenset[str], coordinate_index: CoordinateIndex | None = None
) -> RoleKey:
    """The key ladder for one function: coordinate (only when a
    *coordinate_index* is supplied -- the platform axis), then signature,
    then normalized name.

    Args:
        fn: The function to key.
        tokens: This function's own package's token vocabulary.
        coordinate_index: The platform axis's registered plan builders, or
            ``None`` on an axis with no coordinate key.

    Returns:
        A ``CoordinateRole`` if *fn* is a registered plan builder of one block
        type, else a ``SignatureRole`` if its return annotation declares a
        shared product, else a ``NameRole``.

    Raises:
        SkeletonError: If *fn*'s return annotation cannot be classified,
            naming the member.
    """
    if coordinate_index is not None:
        coordinate = _coordinate_role_key_for(fn, coordinate_index)
        if coordinate is not None:
            return coordinate
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
    if isinstance(role_key, CoordinateRole):
        return f"coordinate:{role_key.block_type}"
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


def key_functions_by_role(
    target_src_dirs: Mapping[str, tuple[Path, ...]],
    tokens_by_label: Mapping[str, frozenset[str]],
    coordinate_index: CoordinateIndex | None = None,
) -> dict[RoleKey, list[FunctionSource]]:
    """Collect every target's functions -- across EVERY package implementing
    it, a language core included -- and key each into its role (the key
    ladder of ``_role_key_for``) -- every role, including those with a single
    member package. A core's functions carry their target's label, so they are
    members of the same target, never of a separate package.

    Args:
        target_src_dirs: ``{label: (src dir, ...)}`` for every target to compare.
        tokens_by_label: ``{label: token vocabulary}`` for every label in
            *target_src_dirs*.
        coordinate_index: The platform axis's registered plan builders;
            ``None`` on an axis with no coordinate key.

    Returns:
        ``{role key: members}``, every qualifying and non-qualifying role
        alike -- the caller decides what "qualifying" means.

    Raises:
        SkeletonError: An unparseable file or an unclassifiable annotation.
    """
    by_role: dict[RoleKey, list[FunctionSource]] = {}
    for label, src_dirs in target_src_dirs.items():
        package_tokens = tokens_by_label[label]
        for src_dir in src_dirs:
            for fn in collect_function_sources(src_dir, label):
                by_role.setdefault(_role_key_for(fn, package_tokens, coordinate_index), []).append(fn)
    return by_role


def classify_keyed_roles(
    by_role: Mapping[RoleKey, list[FunctionSource]], other_src_dirs: list[Path]
) -> list[RoleVerdict]:
    """The rest of today's ``group_and_classify_roles``: keep roles with
    >= 2 distinct packages, apply the other-package name exclusion, classify.

    Args:
        by_role: Every role's members, from ``key_functions_by_role``.
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
                kind=role_kind(key),
                domain=None,
                verdict=_classify_role(members_tuple),
                members=members_tuple,
                adapter_exempt=all(is_pre_binding_adapter(member) for member in members_tuple),
                rendering_leaf_exempt=all(is_rendering_leaf(member) for member in members_tuple),
            )
        )
    return sorted(verdicts, key=lambda verdict: role_label(verdict.role_key))


def group_and_classify_roles(
    target_src_dirs: Mapping[str, tuple[Path, ...]],
    tokens_by_label: dict[str, frozenset[str]],
    other_src_dirs: list[Path],
    coordinate_index: CoordinateIndex | None = None,
) -> list[RoleVerdict]:
    """Core scan: collect every target package's functions, key them into
    roles, keep roles with >= 2 distinct member packages, apply the
    other-package name exclusion, and classify each.

    Pure and dependency-injected -- no registry/entry-point call inside, so
    the self-test exercises it directly with a synthetic package map and
    injected tokens, never a live plugin.

    Args:
        target_src_dirs: ``{label: (src dir, ...)}`` for every target to compare.
        tokens_by_label: ``{label: token vocabulary}`` for every label in
            *target_src_dirs* (from ``tokens_for``, or injected by the
            self-test).
        other_src_dirs: Every OTHER package's src dir -- a ``NameRole`` any
            of whose member names is also bare-defined here is excluded.
        coordinate_index: The platform axis's registered plan builders;
            ``None`` on an axis with no coordinate key.

    Returns:
        One ``RoleVerdict`` per qualifying role, ``domain=None``, sorted by
        role label.

    Raises:
        SkeletonError: Propagates from an unparseable or unclassifiable
            member.
    """
    return classify_keyed_roles(
        key_functions_by_role(target_src_dirs, tokens_by_label, coordinate_index), other_src_dirs
    )


@dataclass(frozen=True)
class RoleScan:
    """One scan's classified roles plus the keyed map they were built from --
    the fingerprint pass reads the roles no multi-package verdict covers."""

    verdicts: list[RoleVerdict]
    by_role: Mapping[RoleKey, tuple[FunctionSource, ...]]


def discover_role_scan(
    axis: str, target_src_dirs: Mapping[str, tuple[Path, ...]], workspace_root: Path
) -> RoleScan:
    """``discover_roles_for`` returning the keyed map too: refuse a vacuous
    comparison, collect every other package's bare names, build each label's
    token vocabulary via the live registry, key every function into its
    role, and classify.

    Every src dir implementing a compared target -- a language core included
    -- belongs to that target, never to the "other package" set whose bare
    names exclude name roles.

    Args:
        axis: ``AXIS_LANGUAGES`` or ``AXIS_PLATFORMS``.
        target_src_dirs: ``{label: (src dir, ...)}`` from
            ``discover_target_package_src_dirs``.
        workspace_root: The monorepo root.

    Returns:
        The classified roles and the keyed map they were built from.

    Raises:
        ValueError: Fewer than two distinct packages are being compared.
        SkeletonError: An unparseable or unclassifiable member.
    """
    _require_min_packages(axis, frozenset(target_src_dirs))
    other_src_dirs = discover_all_other_package_src_dirs(workspace_root, all_src_dirs(target_src_dirs))
    tokens_by_label = {label: tokens_for(axis, label) for label in target_src_dirs}
    coordinate_index = platform_coordinate_index(target_src_dirs) if axis == AXIS_PLATFORMS else None
    by_role = key_functions_by_role(dict(target_src_dirs), tokens_by_label, coordinate_index)
    verdicts = classify_keyed_roles(by_role, other_src_dirs)
    return RoleScan(verdicts=verdicts, by_role={key: tuple(members) for key, members in by_role.items()})


def discover_roles_for(
    axis: str, target_src_dirs: Mapping[str, tuple[Path, ...]], workspace_root: Path
) -> list[RoleVerdict]:
    """Scan the already-resolved *target_src_dirs* on *axis* and return only
    the classified roles -- ``discover_role_scan(...).verdicts``.

    Args:
        axis: ``AXIS_LANGUAGES`` or ``AXIS_PLATFORMS``.
        target_src_dirs: ``{label: (src dir, ...)}`` from
            ``discover_target_package_src_dirs``.
        workspace_root: The monorepo root.

    Returns:
        Every qualifying ``RoleVerdict``.

    Raises:
        ValueError: Fewer than two distinct packages are being compared.
        SkeletonError: An unparseable or unclassifiable member.
    """
    return discover_role_scan(axis, target_src_dirs, workspace_root).verdicts


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
    rendering used by ``--report-only``; nothing here evaluates a gate.

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
# Fingerprint pass (report-only)
# ---------------------------------------------------------------------------

#: A skeleton shorter than this carries too little behaviour to identify a job
#: across languages: six lines is one guarded raise inside one loop plus a
#: return -- anything smaller (a single if/return, a lone loop) recurs across
#: unrelated jobs in every package and would bury the report in coincidences.
FINGERPRINT_MIN_SKELETON_LINES: Final[int] = 6

FingerprintMatch = Literal["match", "near-match"]
_FINGERPRINT_MATCH: Final[FingerprintMatch] = "match"
_FINGERPRINT_NEAR_MATCH: Final[FingerprintMatch] = "near-match"


@dataclass(frozen=True)
class BehaviourFingerprint:
    """What makes two uncovered functions candidates for one job: the same
    control shape reading the same model attributes."""

    shape: tuple[str, ...]
    model_attributes: frozenset[str]


@dataclass(frozen=True)
class FingerprintGroup:
    fingerprint: BehaviourFingerprint
    members: tuple[FunctionSource, ...]
    verdict: Verdict  # _classify_role(members) -- the existing verdict rules
    match: FingerprintMatch  # "match": every member's skeleton string equal; else "near-match"


def uncovered_functions(by_role: Mapping[RoleKey, Sequence[FunctionSource]]) -> list[FunctionSource]:
    """Members of every role with fewer than ``_MIN_PACKAGES_FOR_COMPARISON``
    distinct packages -- the functions no name/signature role compares.

    A role with >= 2 packages counts as covered even if the other-package
    name exclusion later drops it: that exclusion is a deliberate decision
    about the role, and the pass must not re-open it under another key.

    Args:
        by_role: Every role's members, from ``key_functions_by_role`` (via
            ``RoleScan.by_role``).

    Returns:
        Every member of an under-covered role, in role-then-source order.
    """
    functions: list[FunctionSource] = []
    for members in by_role.values():
        if len({member.package for member in members}) < _MIN_PACKAGES_FOR_COMPARISON:
            functions.extend(members)
    return functions


def _fingerprint_from_skeleton(fn: FunctionSource, skeleton: str) -> BehaviourFingerprint | None:
    """``fingerprint_of``'s classification given *fn*'s already-extracted
    *skeleton* -- shared so ``fingerprint_groups`` never extracts a member's
    skeleton twice."""
    if is_pre_binding_adapter(fn) or is_rendering_leaf(fn):
        return None
    if len(skeleton.splitlines()) < FINGERPRINT_MIN_SKELETON_LINES:
        return None
    attributes = model_attribute_names(fn)
    if not attributes:
        return None
    return BehaviourFingerprint(shape=skeleton_shape(skeleton), model_attributes=attributes)


def fingerprint_of(fn: FunctionSource) -> BehaviourFingerprint | None:
    """``None`` when *fn* is not a fingerprint candidate: a pre-binding
    adapter, a rendering leaf, a skeleton under
    ``FINGERPRINT_MIN_SKELETON_LINES`` lines, or no model attribute read.

    Args:
        fn: The candidate function.

    Returns:
        The fingerprint, or ``None``.

    Raises:
        SkeletonError: Propagated unmodified (fail closed, naming the member).
    """
    return _fingerprint_from_skeleton(fn, behaviour_skeleton(fn))


def _fingerprint_cache_key(fn: FunctionSource) -> tuple[Path, int, str]:
    """``FunctionSource`` is a frozen dataclass but holds an AST node and a
    dict, so the skeleton cache is keyed on this instead of the instance."""
    return (fn.file_path, fn.line_number, fn.qualified_name)


def fingerprint_groups(functions: Sequence[FunctionSource]) -> list[FingerprintGroup]:
    """Bucket *functions* by ``fingerprint_of``; keep buckets whose members
    span >= ``_MIN_PACKAGES_FOR_COMPARISON`` distinct packages; classify
    each with ``_classify_role``. Sorted by (verdict, match, first member
    reference) so the report is stable.

    Args:
        functions: Candidate functions, typically ``uncovered_functions``'s
            result.

    Returns:
        Every qualifying group.

    Raises:
        SkeletonError: Propagates from an unparseable or unclassifiable
            member -- never caught here (fail closed).
    """
    skeleton_cache: dict[tuple[Path, int, str], str] = {}

    def _skeleton(fn: FunctionSource) -> str:
        key = _fingerprint_cache_key(fn)
        cached = skeleton_cache.get(key)
        if cached is None:
            cached = behaviour_skeleton(fn)
            skeleton_cache[key] = cached
        return cached

    buckets: dict[BehaviourFingerprint, list[FunctionSource]] = {}
    for fn in functions:
        fingerprint = _fingerprint_from_skeleton(fn, _skeleton(fn))
        if fingerprint is not None:
            buckets.setdefault(fingerprint, []).append(fn)

    groups: list[FingerprintGroup] = []
    for fingerprint, members in buckets.items():
        if len({member.package for member in members}) < _MIN_PACKAGES_FOR_COMPARISON:
            continue
        members_tuple = tuple(members)
        distinct_skeletons = {_skeleton(member) for member in members_tuple}
        match: FingerprintMatch = _FINGERPRINT_MATCH if len(distinct_skeletons) == 1 else _FINGERPRINT_NEAR_MATCH
        groups.append(
            FingerprintGroup(
                fingerprint=fingerprint,
                members=members_tuple,
                verdict=_classify_role(members_tuple),
                match=match,
            )
        )
    return sorted(
        groups, key=lambda group: (group.verdict, group.match, member_reference(group.members[0], WORKSPACE_ROOT))
    )


def fingerprint_line(group: FingerprintGroup, workspace_root: Path) -> str:
    """``FINGERPRINT verdict=<v> match=<match|near-match> lines=<n>
    packages=[a, b] attributes=[...] members=[<member_reference>, ...]``."""
    packages = sorted({member.package for member in group.members})
    attributes = sorted(group.fingerprint.model_attributes)
    members = ", ".join(member_reference(member, workspace_root) for member in group.members)
    return (
        f"FINGERPRINT verdict={group.verdict} match={group.match} lines={len(group.fingerprint.shape)} "
        f"packages={packages} attributes={attributes} members=[{members}]"
    )


def render_fingerprint_report(
    groups: Sequence[FingerprintGroup], uncovered_count: int, workspace_root: Path
) -> None:
    """Log one INFO line per group (never ERROR -- the pass is report-only)
    and the summary:
    ``BEHAVIOUR-PARITY FINGERPRINT (report-only): <g> group(s) -- <m> match,
    <n> near-match; <d> divergent; <u> uncovered function(s) fingerprinted;
    min skeleton lines=<FINGERPRINT_MIN_SKELETON_LINES>``.

    Args:
        groups: Every fingerprint group (``fingerprint_groups``'s result).
        uncovered_count: The count of functions fed into the pass, for the
            summary line.
        workspace_root: Root that member paths are displayed relative to.
    """
    for group in groups:
        logger.info(fingerprint_line(group, workspace_root))
    verdict_counts = Counter(group.verdict for group in groups)
    match_counts = Counter(group.match for group in groups)
    logger.info(
        "BEHAVIOUR-PARITY FINGERPRINT (report-only): %d group(s) -- %d %s, %d %s; %d %s; "
        "%d uncovered function(s) fingerprinted; min skeleton lines=%d",
        len(groups),
        match_counts[_FINGERPRINT_MATCH],
        _FINGERPRINT_MATCH,
        match_counts[_FINGERPRINT_NEAR_MATCH],
        _FINGERPRINT_NEAR_MATCH,
        verdict_counts[_VERDICT_DIVERGENT],
        _VERDICT_DIVERGENT,
        uncovered_count,
        FINGERPRINT_MIN_SKELETON_LINES,
    )


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
# Report filters
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReportFilter:
    """Which role lines the gate report PRINTS. A filter never reaches the
    verdict: the failing-role count, the ratchet comparison and the exit code
    are computed over every role whatever is printed.

    Attributes:
        domains: The shared domain ids (plus ``UNDOMAINED``) whose roles print,
            or ``None`` for every domain.
        buckets: The verdict names (drawn from ``_VALID_BUCKET_IDS``) whose
            roles print, or ``None`` for every bucket.
    """

    domains: frozenset[str] | None
    buckets: frozenset[str] | None

    @classmethod
    def unfiltered(cls) -> ReportFilter:
        """Print every role."""
        return cls(domains=None, buckets=None)

    @property
    def is_unfiltered(self) -> bool:
        return self.domains is None and self.buckets is None

    def admits(self, evaluation: RoleEvaluation) -> bool:
        """Whether *evaluation*'s role line prints: its domain and its verdict
        each satisfy the filter that is set."""
        domain_ok = self.domains is None or evaluation.domain in self.domains
        bucket_ok = self.buckets is None or evaluation.verdict.verdict in self.buckets
        return domain_ok and bucket_ok


def parse_scope_argument(value: str | None) -> tuple[str, ...] | None:
    """``--scope``'s raw value -> the ids it names (``None`` when absent).

    Raises:
        ValueError: ``--scope`` was given but names no id.
    """
    if value is None:
        return None
    ids = tuple(part.strip() for part in value.split(_FILTER_SEPARATOR) if part.strip())
    if not ids:
        raise ValueError(
            f"behaviour_parity:--scope was given but names no domain id; expected a {_FILTER_SEPARATOR!r}-separated "
            f"list of shared domain ids and/or {UNDOMAINED!r}. Fix: pass at least one id, or omit --scope to "
            f"print every domain."
        )
    return ids


def parse_buckets_argument(value: str | None) -> tuple[str, ...] | None:
    """``--buckets``'s raw value -> the verdict-bucket ids it names (``None`` when absent).

    Raises:
        ValueError: ``--buckets`` was given but names no id.
    """
    if value is None:
        return None
    ids = tuple(part.strip() for part in value.split(_FILTER_SEPARATOR) if part.strip())
    if not ids:
        raise ValueError(
            f"behaviour_parity:--buckets was given but names no verdict-bucket id; expected a "
            f"{_FILTER_SEPARATOR!r}-separated list drawn from {sorted(_VALID_BUCKET_IDS)}. Fix: pass at least one "
            f"id, or omit --buckets to print every bucket."
        )
    return ids


def _validate_scope_ids(ids: Iterable[str], universe: frozenset[str]) -> frozenset[str]:
    valid = universe | {UNDOMAINED}
    unknown = sorted(set(ids) - valid)
    if unknown:
        raise ValueError(
            f"behaviour_parity:unknown scope id(s) {unknown} in --scope; valid options are {sorted(valid)}. "
            f"Fix: pass a shared domain id or {UNDOMAINED!r}."
        )
    return frozenset(ids)


def _validate_bucket_ids(ids: Iterable[str]) -> frozenset[str]:
    unknown = sorted(set(ids) - _VALID_BUCKET_IDS)
    if unknown:
        raise ValueError(
            f"behaviour_parity:unknown bucket id(s) {unknown} in --buckets; valid options are "
            f"{sorted(_VALID_BUCKET_IDS)}. Fix: pass one or more of {sorted(_VALID_BUCKET_IDS)}."
        )
    return frozenset(ids)


def build_report_filter(
    explicit_scope: Sequence[str] | None, explicit_buckets: Sequence[str] | None, universe: frozenset[str]
) -> ReportFilter:
    """Resolve ``--scope``/``--buckets`` into the filter that chooses which
    role lines the report prints. Reads no file and moves no verdict.

    Args:
        explicit_scope: ``parse_scope_argument``'s result.
        explicit_buckets: ``parse_buckets_argument``'s result.
        universe: ``SHARED_CONTEXT_TYPES``' keys (or a synthetic universe).

    Returns:
        The filter; an absent option leaves its half unfiltered.

    Raises:
        ValueError: An unknown domain id or an unknown bucket id, naming the
            valid options.
    """
    return ReportFilter(
        domains=None if explicit_scope is None else _validate_scope_ids(explicit_scope, universe),
        buckets=None if explicit_buckets is None else _validate_bucket_ids(explicit_buckets),
    )


# ---------------------------------------------------------------------------
# Gate evaluation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RoleEvaluation:
    """One role's gate outcome: its verdict with ``domain`` filled in, and the
    reasons it fails (empty = passes). Every role is evaluated and counted --
    there is no in-scope/out-of-scope split."""

    verdict: RoleVerdict
    domain: str
    failure_reasons: tuple[str, ...]

    @property
    def fails(self) -> bool:
        return bool(self.failure_reasons)


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


def _divergence_reasons(verdict: RoleVerdict) -> tuple[str, ...]:
    """``divergent``: partition the member packages into skeleton groups and
    pass iff at most one group exists. Otherwise one reason names every group
    -- the gate cannot know which group carries the correct behaviour, so it
    names all of them. No package is set aside: no capability declaration,
    builtin-group stance, ``capability_gaps`` row or emission-trigger
    declaration is read, so a capability a target does not realize, or
    realizes under a different trigger, leaves its role failing.
    """
    groups = skeleton_groups(verdict)
    if len(groups) <= 1:
        return ()
    groups_text = " vs ".join(_group_text(group) for group in groups)
    return (f"members split into {len(groups)} skeleton groups: {groups_text}",)


def evaluate_role(verdict: RoleVerdict) -> RoleEvaluation:
    """Resolve *verdict*'s domain and compute its failure reasons -- for EVERY
    role, whatever its domain (``undomained`` included) or bucket, so every
    failing role is counted.

    Args:
        verdict: A classified role.

    Returns:
        The evaluation, its verdict carrying the resolved domain.

    Raises:
        SkeletonError: A member's skeleton cannot be extracted.
    """
    domain = resolve_domain(verdict)
    if verdict.verdict == _VERDICT_DIVERGENT:
        reasons = _divergence_reasons(verdict)
    else:
        reasons = _duplicate_skeleton_reasons(verdict)
    return RoleEvaluation(
        verdict=dataclasses.replace(verdict, domain=domain),
        domain=domain,
        failure_reasons=reasons,
    )


def evaluate_roles(verdicts: Sequence[RoleVerdict]) -> list[RoleEvaluation]:
    """``evaluate_role`` over every verdict, order preserved."""
    return [evaluate_role(verdict) for verdict in verdicts]


def axis_gates(axis: str, *, report_only: bool) -> bool:
    """Whether verdicts on *axis* are evaluated against the gate. Both axes
    gate, each against its own pinned section; a run gates unless it is
    ``--report-only``.

    Raises:
        ValueError: *axis* is neither axis -- an unknown axis never gates by
            default.
    """
    if axis not in _BASELINE_AXES:
        raise ValueError(
            f"behaviour_parity:unknown axis {axis!r}; valid axes are {sorted(_BASELINE_AXES)}. "
            f"Fix: pass one of the valid axes."
        )
    return not report_only


# ---------------------------------------------------------------------------
# Population ratchet (decrease-only, two-directional)
# ---------------------------------------------------------------------------

BEHAVIOUR_PARITY_BASELINE_PATH: Final[Path] = DATRIX_DIR / "scripts" / "config" / "behaviour-parity-baseline.toml"
#: The axes carrying a pinned section. A section is named by its axis id, so
#: this one set is also the set of valid top-level keys.
_BASELINE_AXES: Final[frozenset[str]] = frozenset({AXIS_LANGUAGES, AXIS_PLATFORMS})
_BASELINE_FAILING_ROLES_KEY: Final[str] = "failing_roles"
_BASELINE_BUCKETS_KEY: Final[str] = "buckets"
_BASELINE_AXIS_KEYS: Final[frozenset[str]] = frozenset({_BASELINE_FAILING_ROLES_KEY, _BASELINE_BUCKETS_KEY})


def _bucket_key(verdict: str) -> str:
    """The baseline spelling of a verdict name: ``same-behaviour`` ->
    ``same_behaviour``, so the keys are valid bare TOML keys."""
    return verdict.replace("-", "_")


_BASELINE_BUCKET_KEYS: Final[frozenset[str]] = frozenset(_bucket_key(verdict) for verdict in _VALID_BUCKET_IDS)


@dataclass(frozen=True)
class AxisBaseline:
    """One axis's pinned failing-role count plus its diagnostic split of those
    failing roles by verdict bucket.

    The split is never part of the verdict: only ``failing_roles`` is
    compared. ``diagnostic_split_notes`` reports a split that no longer
    matches the live one, so a stale diagnostic is visible without ever
    moving the exit code.

    Raises:
        ValueError: A count is negative.
    """

    failing_roles: int
    identical: int
    same_behaviour: int
    divergent: int

    def __post_init__(self) -> None:
        negative = sorted(
            name
            for name, count in (*self.bucket_counts().items(), (_BASELINE_FAILING_ROLES_KEY, self.failing_roles))
            if count < 0
        )
        if negative:
            raise ValueError(f"counts must not be negative; got a negative value for {negative}.")

    def bucket_counts(self) -> dict[str, int]:
        """The split keyed by baseline bucket key."""
        return {
            _bucket_key(_VERDICT_IDENTICAL): self.identical,
            _bucket_key(_VERDICT_SAME_BEHAVIOUR): self.same_behaviour,
            _bucket_key(_VERDICT_DIVERGENT): self.divergent,
        }


def _require_count(value: object, location: str) -> int:
    """*value* as an integer count. A bool is not a count, though it is an
    ``int`` subclass; a negative integer is refused by ``AxisBaseline``.

    Raises:
        ValueError: *value* is not an integer, naming *location*.
    """
    if type(value) is not int:
        raise ValueError(f"{location} must be a non-negative integer; got {value!r} ({type(value).__name__}).")
    return value


def _require_table_with_exact_keys(where: str, table: object, valid: frozenset[str]) -> dict[str, object]:
    """*table* as a TOML table carrying exactly the keys *valid*.

    Raises:
        ValueError: *table* is not a table, carries an unrecognized key, or
            lacks a required one -- naming *where* and every offending key.
    """
    if not isinstance(table, dict):
        raise ValueError(f"{where} must be a table with {sorted(valid)}; got {table!r}.")
    unknown = sorted(set(table) - valid)
    missing = sorted(valid - set(table))
    if unknown or missing:
        raise ValueError(
            f"{where} must carry exactly {sorted(valid)}; unrecognized key(s) {unknown}, missing key(s) {missing}. "
            f"Fix: remove the unrecognized key(s) and seed the missing ones from a live run of the gate."
        )
    return table


def _parse_axis_baseline(path: Path, axis: str, section: object) -> AxisBaseline:
    """One axis section of the baseline file, shape-validated.

    Raises:
        ValueError: *section* is not a table, carries an unrecognized or
            missing key, or a non-integer or negative count -- naming the
            file and the offending key.
    """
    where = f"behaviour_parity:{path}: [{axis}]"
    table = _require_table_with_exact_keys(where, section, _BASELINE_AXIS_KEYS)
    buckets_where = f"{where}.{_BASELINE_BUCKETS_KEY}"
    buckets = _require_table_with_exact_keys(buckets_where, table[_BASELINE_BUCKETS_KEY], _BASELINE_BUCKET_KEYS)
    counts = {key: _require_count(buckets[key], f"{buckets_where}.{key}") for key in sorted(_BASELINE_BUCKET_KEYS)}
    failing = _require_count(table[_BASELINE_FAILING_ROLES_KEY], f"{where}.{_BASELINE_FAILING_ROLES_KEY}")
    try:
        return AxisBaseline(
            failing_roles=failing,
            identical=counts[_bucket_key(_VERDICT_IDENTICAL)],
            same_behaviour=counts[_bucket_key(_VERDICT_SAME_BEHAVIOUR)],
            divergent=counts[_bucket_key(_VERDICT_DIVERGENT)],
        )
    except ValueError as exc:
        raise ValueError(f"{where}: {exc}") from exc


def load_baseline(path: Path = BEHAVIOUR_PARITY_BASELINE_PATH) -> Mapping[str, AxisBaseline]:
    """Load and validate the decrease-only, two-directional ratchet baseline.

    Args:
        path: The TOML baseline file.

    Returns:
        One ``AxisBaseline`` per axis section present in the file, keyed by
        axis id.

    Raises:
        ValueError: The file is missing, unreadable or malformed TOML, has no
            axis section, carries an unrecognized top-level or nested key, or
            holds a count that is negative or not an integer.
    """
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(
            f"behaviour_parity:cannot read the baseline file {path} ({exc}). Fix: restore it, seeded from a "
            f"live run of the gate."
        ) from exc
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"behaviour_parity:{path} is not valid TOML ({exc}). Fix: correct the syntax.") from exc
    unknown = sorted(set(raw) - _BASELINE_AXES)
    if unknown:
        raise ValueError(
            f"behaviour_parity:{path} has unrecognized top-level key(s) {unknown}; valid sections are "
            f"{sorted(_BASELINE_AXES)}. Fix: remove the key."
        )
    if not raw:
        raise ValueError(
            f"behaviour_parity:{path} carries no axis section; expected one of {sorted(_BASELINE_AXES)}. "
            f"Fix: seed a section from a live run of the gate."
        )
    return MappingProxyType({axis: _parse_axis_baseline(path, axis, section) for axis, section in raw.items()})


def failing_role_count(evaluations: Sequence[RoleEvaluation]) -> int:
    """The number of failing roles over EVERY evaluation -- an ``undomained``
    role counts exactly like a domained one."""
    return sum(evaluation.fails for evaluation in evaluations)


def failing_bucket_split(evaluations: Sequence[RoleEvaluation]) -> dict[str, int]:
    """The failing roles counted by verdict bucket, keyed by baseline bucket
    key, every bucket present."""
    counts = Counter(_bucket_key(evaluation.verdict.verdict) for evaluation in evaluations if evaluation.fails)
    return {key: counts[key] for key in sorted(_BASELINE_BUCKET_KEYS)}


def _split_text(split: Mapping[str, int]) -> str:
    return ", ".join(f"{key}={count}" for key, count in sorted(split.items()))


def evaluate_population_ratchet(
    axis: str,
    *,
    live_failing_roles: int,
    live_buckets: Mapping[str, int],
    baseline: Mapping[str, AxisBaseline],
) -> list[str]:
    """Two-directional comparison of *live_failing_roles* with the axis's pin.

    A live count ABOVE the pin is a regression; a live count BELOW the pin is
    an improvement that was not banked -- the pin must be lowered in the same
    change that produces it, or the next regression hides in the slack. An
    exact match is the only passing state.

    Args:
        axis: The gated axis (``AXIS_LANGUAGES`` or ``AXIS_PLATFORMS``).
        live_failing_roles: The count this run just computed.
        live_buckets: This run's failing roles by verdict bucket, keyed like
            the baseline; diagnostic only, never part of the comparison.
        baseline: The loaded baseline.

    Returns:
        Empty on an exact match, else one problem string naming the direction,
        the delta, the live split and the fix.

    Raises:
        KeyError: *axis* has no baseline section (a caller bug: gate the axis
            before calling).
        ValueError: *live_buckets* does not sum to *live_failing_roles*.
    """
    if axis not in baseline:
        raise KeyError(
            f"behaviour_parity:the baseline has no section for axis {axis!r}; pinned axes: {sorted(baseline)}. "
            f"Fix: gate only a pinned axis, or seed a section for this axis from a live run."
        )
    if sum(live_buckets.values()) != live_failing_roles:
        raise ValueError(
            f"behaviour_parity:the live bucket split {dict(live_buckets)} does not sum to the live failing-role "
            f"count {live_failing_roles}."
        )
    pin = baseline[axis].failing_roles
    if live_failing_roles == pin:
        return []
    live_text = f"live split: {_split_text(live_buckets)}"
    file_name = BEHAVIOUR_PARITY_BASELINE_PATH.name
    if live_failing_roles > pin:
        return [
            f"{axis} axis: {live_failing_roles} failing role(s) EXCEED the pinned {pin} by "
            f"{live_failing_roles - pin} ({live_text}). A role regressed or a new failing role appeared. "
            f"Fix: reconcile the failing roles listed above; never raise the pin in {file_name} to admit them."
        ]
    return [
        f"{axis} axis: {live_failing_roles} failing role(s) is BELOW the pinned {pin} by "
        f"{pin - live_failing_roles} ({live_text}). An improvement must be banked in the same change. "
        f"Fix: set {_BASELINE_FAILING_ROLES_KEY} = {live_failing_roles} and the [{axis}.{_BASELINE_BUCKETS_KEY}] "
        f"counts to the live split in {file_name}."
    ]


def diagnostic_split_notes(
    axis: str, *, live_buckets: Mapping[str, int], baseline: Mapping[str, AxisBaseline]
) -> list[str]:
    """Notes for a baseline bucket split that no longer matches the live
    split. A note is never a problem: the split is diagnostic, so a stale one
    is reported and the verdict -- the failing-role count against its pin --
    is untouched.

    Args:
        axis: The gated axis; it must have a baseline section.
        live_buckets: This run's failing roles by verdict bucket, keyed like
            the baseline.
        baseline: The loaded baseline.

    Returns:
        Empty when the split matches, else one note naming both splits.
    """
    pinned = baseline[axis].bucket_counts()
    if pinned == dict(live_buckets):
        return []
    return [
        f"{axis} axis: the pinned bucket split ({_split_text(pinned)}) differs from the live split "
        f"({_split_text(live_buckets)}); it is diagnostic and moves no verdict. Fix: update the "
        f"[{axis}.{_BASELINE_BUCKETS_KEY}] counts in {BEHAVIOUR_PARITY_BASELINE_PATH.name}."
    ]


def population_problems(
    axis: str, evaluations: Sequence[RoleEvaluation], baseline: Mapping[str, AxisBaseline]
) -> list[str]:
    """``evaluate_population_ratchet`` over every evaluation of *axis* -- the
    gate's whole verdict. Empty means the failing-role count equals its pin."""
    return evaluate_population_ratchet(
        axis,
        live_failing_roles=failing_role_count(evaluations),
        live_buckets=failing_bucket_split(evaluations),
        baseline=baseline,
    )


def gate_exit_code(problems: Sequence[str]) -> int:
    """``EXIT_FAIL`` iff the ratchet reports any problem, else ``EXIT_OK``."""
    return EXIT_FAIL if problems else EXIT_OK


# ---------------------------------------------------------------------------
# Gate report
# ---------------------------------------------------------------------------


def evaluation_line(evaluation: RoleEvaluation, workspace_root: Path) -> str:
    """One gate-report line: ``PASS`` or ``FAIL``, then the verdict line, the
    domain and every failure reason."""
    base = verdict_line(evaluation.verdict, workspace_root)
    if not evaluation.fails:
        return f"PASS {base} domain={evaluation.domain}"
    reasons = "; ".join(evaluation.failure_reasons)
    return f"FAIL {base} domain={evaluation.domain} reasons=[{reasons}]"


def _log_evaluation(evaluation: RoleEvaluation, workspace_root: Path, *, debug: bool) -> None:
    line = evaluation_line(evaluation, workspace_root)
    if evaluation.fails or debug:
        logger.info(line)
    else:
        logger.debug(line)


def render_gate_report(
    evaluations: Sequence[RoleEvaluation], workspace_root: Path, *, report_filter: ReportFilter, debug: bool
) -> None:
    """Log one line per role the filter admits (failing roles at INFO, passes
    at DEBUG unless *debug*), then the per-bucket counts, the per-domain counts
    and the gate summary -- the last three over EVERY role, so the filter
    changes what prints and never what is counted.

    Args:
        evaluations: Every evaluated role.
        workspace_root: Root that member paths are displayed relative to.
        report_filter: Which role lines print.
        debug: Also log passing roles at INFO.
    """
    shown = [evaluation for evaluation in evaluations if report_filter.admits(evaluation)]
    for evaluation in shown:
        _log_evaluation(evaluation, workspace_root, debug=debug)
    if not report_filter.is_unfiltered:
        logger.info(
            "BEHAVIOUR-PARITY REPORT FILTER: %d of %d role line(s) printed (domains=%s, buckets=%s); the filter "
            "never changes the failing-role count or the exit code.",
            len(shown),
            len(evaluations),
            "all" if report_filter.domains is None else sorted(report_filter.domains),
            "all" if report_filter.buckets is None else sorted(report_filter.buckets),
        )
    _log_bucket_counts([evaluation.verdict for evaluation in evaluations])
    domain_counts = Counter(evaluation.domain for evaluation in evaluations)
    logger.info(
        "BEHAVIOUR-PARITY DOMAINS: %d role(s) resolved to a shared domain, %d undomained; per domain: %s",
        sum(count for domain, count in domain_counts.items() if domain != UNDOMAINED),
        domain_counts[UNDOMAINED],
        dict(sorted(domain_counts.items())),
    )
    failing = failing_role_count(evaluations)
    logger.info(
        "BEHAVIOUR-PARITY GATE: %d role(s) FAIL (%s), %d role(s) pass -- every role is counted, undomained included.",
        failing,
        _split_text(failing_bucket_split(evaluations)),
        len(evaluations) - failing,
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
_SELF_TEST_UNKNOWN_SCOPE_ID: Final[str] = "bogus"
_SELF_TEST_UNKNOWN_BUCKET_ID: Final[str] = "not-a-verdict"
#: The self-test's three-package divergent tree: two packages agreeing on
#: one behaviour, a third adding a fail-closed raise.
_SELF_TEST_AGREEING_SOURCE: Final[str] = "def divergent_thing(command):\n    return command.name\n"
_SELF_TEST_RAISING_SOURCE: Final[str] = (
    "def divergent_thing(command):\n    if not command.body:\n        raise ValueError('empty')\n    return command.name\n"
)
_SELF_TEST_DIVERGENT_ROLE: Final[str] = "divergent_thing"
#: Names/tokens for the generator-axis merge self-test cases below -- never a
#: real registered generator.
_SELF_TEST_CLIENT_TARGET_NAME: Final[str] = "behaviour_parity_selftest_client_target"
_SELF_TEST_NON_CLIENT_TARGET_NAME: Final[str] = "behaviour_parity_selftest_non_client_target"
_SELF_TEST_CLIENT_TARGET_TOKENS: Final[frozenset[str]] = frozenset({"selftestclienttarget", "widget"})
_SELF_TEST_SRCDIR_TARGET_NAME: Final[str] = "behaviour_parity_selftest_srcdir_target"
#: Must start with "datrix" -- ``discover_all_package_locations`` only picks
#: up ``src/`` subdirectories spelled that way.
_SELF_TEST_SRCDIR_MODULE_ROOT: Final[str] = "datrix_behaviour_parity_selftest_srcdir_module"


class _SelfTestClientTargetGenerator:
    """A synthetic native ``datrix.generators`` plugin carrying the complete
    client-target bundle discovery requires (the testkit fixture renderer's
    hooks and transpiler profile, this target's own capabilities) -- the
    fixture ``registered_client_target_generator_names``/``tokens_for``
    fallback self-test cases register via a monkeypatched entry-point
    provider. Never a real generator; never instantiated (the scan reads
    only its class-level ``descriptor``)."""

    descriptor = fixture_client_target_descriptor(
        _SELF_TEST_CLIENT_TARGET_NAME,
        dataclasses.replace(
            FIXTURECLIENT_CAPABILITY_DECLARATION,
            target_label="Self-Test Client",
            name_tokens=_SELF_TEST_CLIENT_TARGET_TOKENS,
        ),
    )


class _SelfTestNonClientTargetGenerator:
    """A synthetic native ``datrix.generators`` plugin with NO
    ``transpiler_profile`` (mirrors ``sql``/``component``) -- must be
    excluded by ``registered_client_target_generator_names``."""

    descriptor = PluginDescriptor(name=_SELF_TEST_NON_CLIENT_TARGET_NAME, phase="artifacts")


class _SelfTestSrcDirGenerator:
    """A synthetic client-target generator class whose ``__module__`` is
    overridden (below) to a planted on-disk package name, for the
    src-dir-resolution self-test case."""

    descriptor = fixture_client_target_descriptor(
        _SELF_TEST_SRCDIR_TARGET_NAME,
        dataclasses.replace(
            FIXTURECLIENT_CAPABILITY_DECLARATION,
            target_label="Self-Test SrcDir",
            name_tokens=frozenset({"selftestsrcdir"}),
        ),
    )


_SelfTestSrcDirGenerator.__module__ = _SELF_TEST_SRCDIR_MODULE_ROOT


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
        kind=role_kind(role_key),
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


def _marked_adapter_member(package: str, file_path: Path) -> FunctionSource:
    """A member parsed from source text that carries the real ``@emit_adapter``
    marker, spelled through the shared layer's own import path, whose body
    differs from ``_plain_member``'s -- the shape the retired builtin-group
    set-aside used to excuse."""
    source = (
        f"from {emit_adapter.__module__} import {emit_adapter.__qualname__}\n\n"
        f"@{emit_adapter.__qualname__}\n"
        f"def build_thing(value: str) -> str:\n"
        f"    return value\n"
    )
    return _function_source(source, package=package, file_path=file_path)


class _RecordingHandler(logging.Handler):
    """Collects the formatted messages the gate report logs, so a case can
    assert a failure line names its role. ``levels`` parallels ``messages``
    one entry per record, so a case can also prove nothing was logged at or
    above a given severity (the fingerprint pass's report-only claim)."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.messages: list[str] = []
        self.levels: list[int] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())
        self.levels.append(record.levelno)


def _recorded_gate_lines(
    evaluations: Sequence[RoleEvaluation], report_filter: ReportFilter = ReportFilter.unfiltered()
) -> list[str]:
    """Render the gate report into a recording handler (nothing reaches the
    real handlers) and return every line."""
    handler = _RecordingHandler()
    previous_level, previous_propagate = logger.level, logger.propagate
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    try:
        render_gate_report(evaluations, _SELF_TEST_TREE, report_filter=report_filter, debug=False)
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
        {label: (root / label,) for label in labels},
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
            "from datrix_codegen_kernel.generation.generator import GeneratedFile\n\n"
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


def _self_test_case_declared_hole_still_fails() -> bool:
    """(n) NEGATIVE: a divergent role whose package used to be set aside as a
    declared hole STILL FAILS. Two plants, both shapes a retired set-aside
    excused -- a role in a real domain whose beta member would have been
    declared ``unsupported`` (or emitted on demand) for that domain, and a role
    whose beta member is an ``@emit_adapter``-marked function over a builtin
    group that would have been declared ``unsupported``. ``evaluate_role``
    takes the role alone -- no declaration has an input left to carry it --
    so each role is judged by its skeleton groups and fails naming both."""
    domain, _ = _two_universe_ids()

    def domain_path(package: str) -> Path:
        return _SELF_TEST_TREE / package / _MICRO_GENERATORS_DIR / f"{domain}{_PY_SUFFIX}"

    in_domain = _synthetic_role(
        NameRole("build_thing"),
        [
            _plain_member(_SELF_TEST_ALPHA, domain_path(_SELF_TEST_ALPHA)),
            _marked_adapter_member(_SELF_TEST_BETA, domain_path(_SELF_TEST_BETA)),
        ],
    )
    marked_adapter = _synthetic_role(
        NameRole("build_thing"),
        [
            _plain_member(_SELF_TEST_ALPHA, _SELF_TEST_TREE / _SELF_TEST_ALPHA / _SELF_TEST_MODULE),
            _marked_adapter_member(_SELF_TEST_BETA, _SELF_TEST_TREE / _SELF_TEST_BETA / _SELF_TEST_MODULE),
        ],
    )
    domained = evaluate_role(in_domain)
    undomained = evaluate_role(marked_adapter)
    return (
        list(inspect.signature(evaluate_role).parameters) == ["verdict"]
        and domained.domain == domain
        and domained.fails
        and undomained.domain == UNDOMAINED
        and undomained.fails
        and all(
            _group_text((package,)) in evaluation.failure_reasons[0]
            for evaluation in (domained, undomained)
            for package in (_SELF_TEST_ALPHA, _SELF_TEST_BETA)
        )
    )


#: Names of the declaration types and fields a parity verdict used to read to
#: excuse a divergent role. Matched against the AST of this module -- an
#: import, a name or an attribute -- never against its prose.
_REMOVED_DECLARATION_NAMES: Final[frozenset[str]] = frozenset(
    {
        "DomainDeclaration",
        "stance_table_by_language",
        "capability_gaps",
        "CapabilityGap",
        "on_demand_domains",
    }
)


def _declaration_names_referenced(source: str) -> list[str]:
    """Every removed-declaration name *source* imports, names or reads as an
    attribute -- by AST, so a docstring or comment describing the retired
    mechanism is never a hit."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.alias):
            found.add(node.name.rsplit(".", 1)[-1])
        elif isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
    return sorted(found & _REMOVED_DECLARATION_NAMES)


def _self_test_case_no_declaration_reader() -> bool:
    """(o) This module reads no declaration to excuse a divergent role: its
    own AST imports, names and reads none of the retired declaration types or
    fields (the emission-trigger table included). NON-VACUITY: the same
    matcher finds each one planted in a synthetic source, whether imported,
    named or read as an attribute."""
    planted = (
        "from datrix_codegen_kernel.parity.domain_declaration import DomainDeclaration\n"
        "def read(declaration):\n"
        "    return stance_table_by_language, declaration.capability_gaps, declaration.on_demand_domains\n"
    )
    return _declaration_names_referenced(planted) == sorted(
        {"DomainDeclaration", "stance_table_by_language", "capability_gaps", "on_demand_domains"}
    ) and not _declaration_names_referenced(Path(__file__).read_text(encoding="utf-8"))


def _self_test_case_report_filters() -> bool:
    """(p) Report filters: ``--scope``/``--buckets`` name the role lines that
    print -- a role prints when its domain AND its verdict satisfy every
    filter given -- and an unknown id (either option) or an empty option is
    refused naming the problem."""
    domain, other = _two_universe_ids()
    universe = frozenset(SHARED_CONTEXT_TYPES)
    evaluations = evaluate_roles(_divergent_tree_verdicts(domain))
    only = evaluations[0]
    admits = {
        "unfiltered": ReportFilter.unfiltered().admits(only),
        "own domain": build_report_filter((domain,), None, universe).admits(only),
        "other domain": build_report_filter((other,), None, universe).admits(only),
        "undomained": build_report_filter((UNDOMAINED,), None, universe).admits(only),
        "own bucket": build_report_filter(None, (_VERDICT_DIVERGENT,), universe).admits(only),
        "other bucket": build_report_filter(None, (_VERDICT_IDENTICAL,), universe).admits(only),
        "both match": build_report_filter((domain,), (_VERDICT_DIVERGENT,), universe).admits(only),
        "domain matches, bucket does not": build_report_filter((domain,), (_VERDICT_IDENTICAL,), universe).admits(only),
    }
    filters_hold = (
        admits["unfiltered"]
        and admits["own domain"]
        and not admits["other domain"]
        and not admits["undomained"]
        and admits["own bucket"]
        and not admits["other bucket"]
        and admits["both match"]
        and not admits["domain matches, bucket does not"]
        and build_report_filter(None, None, universe).is_unfiltered
        and parse_scope_argument(f"{domain} {_FILTER_SEPARATOR} {other}") == (domain, other)
        and parse_scope_argument(None) is None
        and parse_buckets_argument(f"{_VERDICT_IDENTICAL}{_FILTER_SEPARATOR}{_VERDICT_SAME_BEHAVIOUR}")
        == (_VERDICT_IDENTICAL, _VERDICT_SAME_BEHAVIOUR)
        and parse_buckets_argument(None) is None
    )
    refusals_hold = (
        _refuses(
            lambda: build_report_filter((_SELF_TEST_UNKNOWN_SCOPE_ID,), None, universe),
            _SELF_TEST_UNKNOWN_SCOPE_ID,
            UNDOMAINED,
            "--scope",
        )
        and _refuses(
            lambda: build_report_filter(None, (_SELF_TEST_UNKNOWN_BUCKET_ID,), universe),
            _SELF_TEST_UNKNOWN_BUCKET_ID,
            "--buckets",
            *sorted(_VALID_BUCKET_IDS),
        )
        and _refuses(lambda: parse_scope_argument(_FILTER_SEPARATOR), "--scope")
        and _refuses(lambda: parse_buckets_argument(_FILTER_SEPARATOR), "--buckets")
    )
    return filters_hold and refusals_hold


def _refuses(
    action: Callable[[], object], *expected_texts: str, error_type: type[Exception] = ValueError
) -> bool:
    """Whether *action* raises *error_type* (``ValueError`` by default) whose
    message contains every one of *expected_texts*."""
    try:
        action()
    except error_type as exc:
        return all(expected in str(exc) for expected in expected_texts)
    return False


def _divergent_tree_verdicts(domain: str) -> list[RoleVerdict]:
    """The synthetic three-package divergent tree under a real universe
    domain's owning-module shape: alpha and beta agree, gamma adds a
    fail-closed raise. Cases (q1) and (r) both judge this one role."""
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
    """(q1) A divergent role whose members split into two skeleton groups
    FAILS with one reason naming BOTH groups -- there is no reference
    language, so the gate cannot single out one side as lagging. Reordering
    the packages (so the group holding the raise comes first alphabetically)
    names the same groups."""
    domain, _ = _two_universe_ids()
    verdicts = _divergent_tree_verdicts(domain)
    role = _name_roles(verdicts, _SELF_TEST_DIVERGENT_ROLE)
    if not _single_role_with_verdict(role, _VERDICT_DIVERGENT):
        return False
    groups = skeleton_groups(role[0])
    evaluation = evaluate_role(role[0])
    agreeing_group = _group_text((_SELF_TEST_ALPHA, _SELF_TEST_BETA))
    raising_group = _group_text((_SELF_TEST_GAMMA,))
    reason = evaluation.failure_reasons[0] if evaluation.failure_reasons else ""
    return (
        groups == (frozenset({_SELF_TEST_ALPHA, _SELF_TEST_BETA}), frozenset({_SELF_TEST_GAMMA}))
        and evaluation.fails
        and len(evaluation.failure_reasons) == 1
        and "2 skeleton groups" in reason
        and agreeing_group in reason
        and raising_group in reason
    )


def _self_test_case_bucket_labels() -> bool:
    """(q4) The bucket labels printed and accepted are exactly ``identical``,
    ``same-behaviour`` and ``divergent`` (invariant I12): the verdict type,
    the ``--buckets`` vocabulary, every verdict line and the summary line
    all spell them, and nothing else."""
    expected = frozenset({"identical", "same-behaviour", "divergent"})
    domain, _ = _two_universe_ids()
    verdicts = _divergent_tree_verdicts(domain)
    lines = _recorded_gate_lines(evaluate_roles(verdicts))
    summary = next((line for line in lines if line.startswith("BEHAVIOUR-PARITY REPORT:")), "")
    return (
        _VALID_BUCKET_IDS == expected
        and frozenset(Verdict.__args__) == expected
        and any(f"verdict={_VERDICT_DIVERGENT} " in line for line in lines)
        and all(f" {label} (" in summary or f" {label}." in summary for label in expected)
    )


def _baseline_pinning(failing_roles: int) -> Mapping[str, AxisBaseline]:
    """A synthetic ``languages`` baseline pinning *failing_roles*, the whole
    pin in the ``divergent`` bucket (the split only has to sum to the pin)."""
    pin = AxisBaseline(failing_roles=failing_roles, identical=0, same_behaviour=0, divergent=failing_roles)
    return {AXIS_LANGUAGES: pin}


def _self_test_case_gate_outcome() -> bool:
    """(r) End to end on a synthetic three-package tree: a divergent role in a
    real universe domain FAILs (the FAIL line
    names the role and every group) and is counted; a baseline pinning exactly
    that count exits 0; the identical non-adapter role fails while an
    adapter-exempt one passes; and both axes gate unless the run is
    ``--report-only`` (an unknown axis is refused)."""
    domain, _ = _two_universe_ids()
    verdicts = _divergent_tree_verdicts(domain)
    if not _single_role_with_verdict(_name_roles(verdicts, _SELF_TEST_DIVERGENT_ROLE), _VERDICT_DIVERGENT):
        return False
    evaluations = evaluate_roles(verdicts)
    lines = _recorded_gate_lines(evaluations)
    at_pin = population_problems(AXIS_LANGUAGES, evaluations, _baseline_pinning(1))
    return (
        evaluations[0].domain == domain
        and failing_role_count(evaluations) == 1
        and failing_bucket_split(evaluations) == {"identical": 0, "same_behaviour": 0, "divergent": 1}
        and any(
            line.startswith("FAIL ")
            and f"role={_SELF_TEST_DIVERGENT_ROLE}" in line
            and _group_text((_SELF_TEST_ALPHA, _SELF_TEST_BETA)) in line
            and _group_text((_SELF_TEST_GAMMA,)) in line
            for line in lines
        )
        and any(line.startswith("BEHAVIOUR-PARITY GATE: 1 role(s) FAIL") for line in lines)
        and not any("in scope" in line or "in-scope" in line for line in lines)
        and gate_exit_code(at_pin) == EXIT_OK
        and _duplicate_buckets_gate_correctly()
        and axis_gates(AXIS_PLATFORMS, report_only=False)
        and axis_gates(AXIS_LANGUAGES, report_only=False)
        and not axis_gates(AXIS_PLATFORMS, report_only=True)
        and not axis_gates(AXIS_LANGUAGES, report_only=True)
        and _refuses(lambda: axis_gates("not-an-axis", report_only=False), "not-an-axis", AXIS_PLATFORMS)
    )


def _duplicate_buckets_gate_correctly() -> bool:
    """Case (r)'s duplicate-bucket half: the adapter/decider tree of case (f)
    -- the adapter-exempt identical role passes, the deciding one fails and,
    resolving to no domain, is counted all the same."""
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
    evaluations = evaluate_roles(verdicts)
    by_label = {role_label(evaluation.verdict.role_key): evaluation for evaluation in evaluations}
    return (
        not by_label["build_adapter_thing"].fails
        and by_label["build_deciding_thing"].fails
        and by_label["build_deciding_thing"].domain == UNDOMAINED
        and failing_role_count(evaluations) == 1
        and failing_bucket_split(evaluations) == {"identical": 1, "same_behaviour": 0, "divergent": 0}
    )


def _undomained_tree_verdicts() -> list[RoleVerdict]:
    """The three-package divergent tree of ``_divergent_tree_verdicts`` with
    every member under a path no ladder step reads a domain from: the one
    role resolves to ``undomained``."""
    with tempfile.TemporaryDirectory(prefix="behaviour-parity-selftest-undomained-") as tmp:
        root = Path(tmp)
        for label, source in (
            (_SELF_TEST_ALPHA, _SELF_TEST_AGREEING_SOURCE),
            (_SELF_TEST_BETA, _SELF_TEST_AGREEING_SOURCE),
            (_SELF_TEST_GAMMA, _SELF_TEST_RAISING_SOURCE),
        ):
            _write_module(root / label, source)
        return _scan(root, (_SELF_TEST_ALPHA, _SELF_TEST_BETA, _SELF_TEST_GAMMA))


def _self_test_case_undomained_role_counted() -> bool:
    """(r1) A failing role the domain ladder resolves to ``undomained`` is
    COUNTED -- by the failing-role count and by the ratchet -- exactly like a
    domained one: alone it is one failing role, beside a domained failing
    role it makes two, and a pin that omits it fails the gate."""
    domain, _ = _two_universe_ids()
    undomained = evaluate_roles(_undomained_tree_verdicts())
    domained = evaluate_roles(_divergent_tree_verdicts(domain))
    both = [*undomained, *domained]
    omitted = population_problems(AXIS_LANGUAGES, undomained, _baseline_pinning(0))
    counted = population_problems(AXIS_LANGUAGES, undomained, _baseline_pinning(1))
    return (
        len(undomained) == 1
        and undomained[0].domain == UNDOMAINED
        and undomained[0].fails
        and failing_role_count(undomained) == 1
        and failing_role_count(both) == 2
        and failing_bucket_split(both) == {"identical": 0, "same_behaviour": 0, "divergent": 2}
        and gate_exit_code(omitted) == EXIT_FAIL
        and "EXCEED" in omitted[0]
        and gate_exit_code(counted) == EXIT_OK
    )


def _self_test_case_population_ratchet_both_directions() -> bool:
    """(r2) The ratchet fails in BOTH directions and only an exact match
    passes: a pin one BELOW the live count (a regression) and a pin one ABOVE
    it (an improvement that was not banked) each exit 1, naming their
    direction, the delta, the live split and the fix; a pin equal to the live
    count exits 0; an axis with no baseline section raises naming the pinned
    axes; a live split that does not sum to the live count is refused; and a
    stale bucket split is a note that never moves the verdict."""
    evaluations = evaluate_roles(_undomained_tree_verdicts())
    live = failing_role_count(evaluations)
    split = {"identical": 0, "same_behaviour": 0, "divergent": live}
    pinned = _baseline_pinning(live)
    stale = {AXIS_LANGUAGES: AxisBaseline(failing_roles=live, identical=live, same_behaviour=0, divergent=0)}
    stale_notes = diagnostic_split_notes(AXIS_LANGUAGES, live_buckets=split, baseline=stale)

    def ratchet(pin: int, count: int = live, buckets: Mapping[str, int] = split) -> list[str]:
        return evaluate_population_ratchet(
            AXIS_LANGUAGES, live_failing_roles=count, live_buckets=buckets, baseline=_baseline_pinning(pin)
        )

    regression, unbanked, exact = ratchet(live - 1), ratchet(live + 1), ratchet(live)
    return (
        live == 1
        and exact == []
        and len(regression) == 1
        and "EXCEED" in regression[0]
        and "by 1" in regression[0]
        and "divergent=1" in regression[0]
        and len(unbanked) == 1
        and "BELOW" in unbanked[0]
        and "banked in the same change" in unbanked[0]
        and f"{_BASELINE_FAILING_ROLES_KEY} = {live}" in unbanked[0]
        and gate_exit_code(regression) == EXIT_FAIL
        and gate_exit_code(unbanked) == EXIT_FAIL
        and gate_exit_code(exact) == EXIT_OK
        and _refuses(
            lambda: evaluate_population_ratchet(
                AXIS_PLATFORMS, live_failing_roles=live, live_buckets=split, baseline=pinned
            ),
            AXIS_PLATFORMS,
            AXIS_LANGUAGES,
            error_type=KeyError,
        )
        and _refuses(lambda: ratchet(live, live + 1), "does not sum")
        and diagnostic_split_notes(AXIS_LANGUAGES, live_buckets=split, baseline=pinned) == []
        and len(stale_notes) == 1
        and "identical=1" in stale_notes[0]
        and "divergent=1" in stale_notes[0]
        and "moves no verdict" in stale_notes[0]
        and population_problems(AXIS_LANGUAGES, evaluations, stale) == []
    )


_BASELINE_FIXTURE_VALID: Final[str] = (
    "[languages]\nfailing_roles = 3\n\n[languages.buckets]\nidentical = 1\nsame_behaviour = 1\ndivergent = 1\n"
)


def _self_test_case_baseline_loader() -> bool:
    """(r3) The baseline loader accepts a well-formed file and REFUSES, naming
    the file and the offending key, an unrecognized top-level section, an
    unrecognized key inside an axis section, an unrecognized or missing bucket
    key, a negative or non-integer count, a file with no axis section,
    malformed TOML, and a missing file. A pin edited alone -- the split left
    stale -- still loads: the split is diagnostic."""
    valid = _BASELINE_FIXTURE_VALID
    cases: dict[str, tuple[str, tuple[str, ...]]] = {
        "typo-top-level": (valid + "\n[platfroms]\nfailing_roles = 0\n", ("top-level key(s) ['platfroms']",)),
        "typo-platforms-key": (
            valid + "\n[platforms]\nfailing_roles = 0\ntypo_key = 1\n\n[platforms.buckets]\n"
            "identical = 0\nsame_behaviour = 0\ndivergent = 0\n",
            ("[platforms]", "unrecognized key(s) ['typo_key']"),
        ),
        "typo-axis-key": (
            valid.replace("failing_roles = 3", "failing_roles = 3\ntypo_key = 1"),
            ("unrecognized key(s) ['typo_key']",),
        ),
        "typo-bucket-key": (
            valid.replace("divergent = 1", "divergent = 1\nsame_behavior = 1"),
            ("unrecognized key(s) ['same_behavior']",),
        ),
        "missing-bucket": (valid.replace("divergent = 1\n", ""), ("missing key(s) ['divergent']",)),
        "negative": (valid.replace("failing_roles = 3", "failing_roles = -3"), ("negative", "failing_roles")),
        "float": (valid.replace("failing_roles = 3", "failing_roles = 3.0"), ("failing_roles", "integer")),
        "bool": (valid.replace("identical = 1", "identical = true"), ("identical", "integer")),
        "empty": ("", ("no axis section",)),
        "malformed": ("[languages\nfailing_roles = 3\n", ("not valid TOML",)),
    }
    with tempfile.TemporaryDirectory(prefix="behaviour-parity-selftest-r3-") as tmp:
        root = Path(tmp)
        valid_path = root / "valid.toml"
        valid_path.write_text(_BASELINE_FIXTURE_VALID, encoding="utf-8")
        pin_only_path = root / "pin-only.toml"
        pin_only_path.write_text(valid.replace("failing_roles = 3", "failing_roles = 4"), encoding="utf-8")
        both_axes_path = root / "both-axes.toml"
        both_axes_path.write_text(
            valid + "\n[platforms]\nfailing_roles = 2\n\n[platforms.buckets]\n"
            "identical = 0\nsame_behaviour = 0\ndivergent = 2\n",
            encoding="utf-8",
        )
        loads = (
            load_baseline(valid_path)
            == {AXIS_LANGUAGES: AxisBaseline(failing_roles=3, identical=1, same_behaviour=1, divergent=1)}
            and load_baseline(pin_only_path)
            == {AXIS_LANGUAGES: AxisBaseline(failing_roles=4, identical=1, same_behaviour=1, divergent=1)}
            and load_baseline(both_axes_path)
            == {
                AXIS_LANGUAGES: AxisBaseline(failing_roles=3, identical=1, same_behaviour=1, divergent=1),
                AXIS_PLATFORMS: AxisBaseline(failing_roles=2, identical=0, same_behaviour=0, divergent=2),
            }
        )
        refusals = True
        for name, (text, expected) in cases.items():
            path = root / f"{name}.toml"
            path.write_text(text, encoding="utf-8")
            refusals &= _refuses(lambda path=path: load_baseline(path), str(path), *expected)
        missing = root / "missing.toml"
        refusals &= _refuses(lambda: load_baseline(missing), str(missing), "cannot read")
    return loads and refusals


def _self_test_case_filters_never_move_the_verdict() -> bool:
    """(t) ``--scope``/``--buckets`` change which role lines PRINT and nothing
    else: with a filter that admits no role the divergent role's line is
    absent from the report, yet the gate summary still counts it as failing
    and the ratchet verdict -- hence the exit code -- is identical to the
    unfiltered run's."""
    domain, other = _two_universe_ids()
    universe = frozenset(SHARED_CONTEXT_TYPES)
    evaluations = evaluate_roles(_divergent_tree_verdicts(domain))
    baseline = _baseline_pinning(1)
    unfiltered = _recorded_gate_lines(evaluations)
    filtered_out = _recorded_gate_lines(evaluations, build_report_filter((other,), None, universe))
    bucket_filtered_out = _recorded_gate_lines(evaluations, build_report_filter(None, (_VERDICT_IDENTICAL,), universe))

    def role_lines(lines: list[str]) -> list[str]:
        return [line for line in lines if line.startswith(("FAIL ", "PASS "))]

    def summary(lines: list[str]) -> str:
        return next((line for line in lines if line.startswith("BEHAVIOUR-PARITY GATE:")), "")

    return (
        len(role_lines(unfiltered)) == 1
        and role_lines(filtered_out) == []
        and role_lines(bucket_filtered_out) == []
        and summary(unfiltered) == summary(filtered_out) == summary(bucket_filtered_out)
        and any(line.startswith("BEHAVIOUR-PARITY REPORT FILTER: 0 of 1") for line in filtered_out)
        and not any("REPORT FILTER" in line for line in unfiltered)
        and gate_exit_code(population_problems(AXIS_LANGUAGES, evaluations, baseline)) == EXIT_OK
        and gate_exit_code(population_problems(AXIS_LANGUAGES, evaluations, _baseline_pinning(0))) == EXIT_FAIL
    )


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
            "from datrix_codegen_common.transpiler.scope import FileScope\n\n\n"
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


def _self_test_case_client_target_generator_names() -> bool:
    """(z1) A native ``datrix.generators`` class declaring a non-``None``
    ``descriptor.transpiler_profile`` is included by
    ``registered_client_target_generator_names`` when injected into a
    fixture ``PluginRegistry``; a sibling declaring
    ``transpiler_profile=None`` (mirroring ``sql``/``component``) is
    excluded."""
    fixture_entry_points = (
        EntryPoint(
            name=_SELF_TEST_CLIENT_TARGET_NAME,
            value=f"{__name__}:_SelfTestClientTargetGenerator",
            group=GENERATOR_GROUP,
        ),
        EntryPoint(
            name=_SELF_TEST_NON_CLIENT_TARGET_NAME,
            value=f"{__name__}:_SelfTestNonClientTargetGenerator",
            group=GENERATOR_GROUP,
        ),
    )

    def _fixture_entry_points(*, group: str) -> list[EntryPoint]:
        return [ep for ep in fixture_entry_points if ep.group == group]

    original_entry_points = registry_module.entry_points
    try:
        registry_module.entry_points = _fixture_entry_points
        fixture_registry = PluginRegistry()
        names = registered_client_target_generator_names(registry=fixture_registry)
    finally:
        registry_module.entry_points = original_entry_points
    return _SELF_TEST_CLIENT_TARGET_NAME in names and _SELF_TEST_NON_CLIENT_TARGET_NAME not in names


def _self_test_case_client_target_token_fallback() -> bool:
    """(z2) ``tokens_for`` falls back to a synthetic
    ``ClientTargetCapabilityDeclaration.name_tokens`` fixture when no
    ``LanguageCapabilityDeclaration`` resolves for the label. The real
    language registry is pre-warmed first (a real, unpatched name) so its
    process-wide, never-reset discovery cache is not poisoned by the
    patched entry-point seam below: ``PluginRegistry`` discovery is
    idempotent and never re-scans once cached, so the pre-warm call locks
    in the real language plugins before the patch takes effect."""
    real_language = sorted(registered_language_names())[0]
    declaration_for_language(real_language)  # pre-warm; never re-scanned below

    def _fixture_entry_points(*, group: str) -> list[EntryPoint]:
        if group != GENERATOR_GROUP:
            return []
        return [
            EntryPoint(
                name=_SELF_TEST_CLIENT_TARGET_NAME,
                value=f"{__name__}:_SelfTestClientTargetGenerator",
                group=group,
            )
        ]

    global _CLIENT_TARGET_REGISTRY  # noqa: PLW0603 -- deliberate test-only substitution, restored in finally
    previous_registry = _CLIENT_TARGET_REGISTRY
    original_entry_points = registry_module.entry_points
    try:
        registry_module.entry_points = _fixture_entry_points
        _CLIENT_TARGET_REGISTRY = PluginRegistry()
        tokens = tokens_for(AXIS_LANGUAGES, _SELF_TEST_CLIENT_TARGET_NAME)
    finally:
        registry_module.entry_points = original_entry_points
        _CLIENT_TARGET_REGISTRY = previous_registry
    expected = _SELF_TEST_CLIENT_TARGET_TOKENS | {_SELF_TEST_CLIENT_TARGET_NAME}
    return tokens == expected


def _self_test_case_merged_axis_group_and_classify() -> bool:
    """(z3) ``group_and_classify_roles`` -- already dependency-injected, no
    registry call inside -- fed a merged ``target_src_dirs`` containing one
    LANGUAGE fixture and one GENERATOR fixture produces a role spanning
    both, with neither treated as an 'other package' exclusion of the
    other: the generator-axis merge needs no special-casing at this layer."""
    with tempfile.TemporaryDirectory(prefix="behaviour-parity-selftest-z3-") as tmp:
        root = Path(tmp)
        lang_label = "selftest_lang_fixture"
        generator_label = "selftest_generator_fixture"
        body = "def merged_axis_thing(value):\n    return value.strip()\n"
        _write_module(root / lang_label, body)
        _write_module(root / generator_label, body)
        verdicts = _scan(root, (lang_label, generator_label))
        matches = _name_roles(verdicts, "merged_axis_thing")
        return _single_role_with_verdict(matches, _VERDICT_IDENTICAL) and _distinct_packages(
            list(matches[0].members)
        ) == 2


def _self_test_case_merged_axis_min_packages_still_refused() -> bool:
    """(z4) A merged (language + generator) set of size 1 is still refused
    -- ``_require_min_packages`` is generic over a label's origin, so the
    generator-axis merge in ``_run_scan`` does not weaken the floor."""
    try:
        _require_min_packages(AXIS_LANGUAGES, frozenset({"selftest_generator_fixture"}))
    except ValueError:
        return True
    return False


def _self_test_case_client_target_generator_src_dir_resolution() -> bool:
    """(z5) ``discover_client_target_generator_src_dirs`` resolves a
    planted fixture ``datrix.generators`` class to its on-disk ``src/``
    directory, and raises -- naming the unresolved name and the discovered
    roots -- when a requested name cannot be resolved to a
    transpiler_profile-bearing class."""
    with tempfile.TemporaryDirectory(prefix="behaviour-parity-selftest-z5-") as tmp:
        root = Path(tmp)
        package_src = root / "datrix-selftest-srcdir-fixture" / "src" / _SELF_TEST_SRCDIR_MODULE_ROOT
        package_src.mkdir(parents=True)

        def _fixture_entry_points(*, group: str) -> list[EntryPoint]:
            if group != GENERATOR_GROUP:
                return []
            return [
                EntryPoint(
                    name=_SELF_TEST_SRCDIR_TARGET_NAME,
                    value=f"{__name__}:_SelfTestSrcDirGenerator",
                    group=group,
                )
            ]

        original_entry_points = registry_module.entry_points
        resolves_correctly = False
        raised_naming_both = False
        try:
            registry_module.entry_points = _fixture_entry_points
            resolved = discover_client_target_generator_src_dirs(
                frozenset({_SELF_TEST_SRCDIR_TARGET_NAME}), root, registry=PluginRegistry()
            )
            resolves_correctly = resolved == {_SELF_TEST_SRCDIR_TARGET_NAME: (package_src,)}

            unresolvable_name = "bogus-unresolvable-name"
            try:
                discover_client_target_generator_src_dirs(
                    frozenset({_SELF_TEST_SRCDIR_TARGET_NAME, unresolvable_name}),
                    root,
                    registry=PluginRegistry(),
                )
            except ValueError as exc:
                message = str(exc)
                raised_naming_both = unresolvable_name in message and _SELF_TEST_SRCDIR_TARGET_NAME in message
        finally:
            registry_module.entry_points = original_entry_points
    return resolves_correctly and raised_naming_both


def _self_test_case_language_core_is_a_member_not_an_other_package() -> bool:
    """(z6) A fixture language split into a backend and a core: target
    discovery resolves BOTH packages under the language's one label, the core
    never lands in the "other package" set, and a function defined only in the
    core is compared as that language's member. Fed the pre-split shape -- the
    core scanned as an other package -- the same role is excluded, which is
    exactly the blindness this case exists to keep closed."""
    split_label, plain_label = "selftest_split_lang", "selftest_plain_lang"
    backend, core, plain, shared = (
        "datrix_selftest_split",
        "datrix_selftest_split_core",
        "datrix_selftest_plain",
        "datrix_selftest_shared",
    )
    with tempfile.TemporaryDirectory(prefix="behaviour-parity-selftest-z6-") as tmp:
        root = Path(tmp)
        for import_name in (backend, core, plain, shared):
            (root / import_name.replace("_", "-") / "src" / import_name).mkdir(parents=True)
        locations = discover_all_package_locations(root)
        resolved = resolve_target_src_dirs(
            AXIS_LANGUAGES, {split_label: (backend, core), plain_label: (plain,)}, locations
        )
        body = "def core_planted_thing(value):\n    return value.strip()\n"
        _write_module(locations[core], body)
        _write_module(locations[plain], body)
        _write_module(locations[backend], "def backend_only_thing(value):\n    return value\n")
        others = discover_all_other_package_src_dirs(root, all_src_dirs(resolved))
        verdicts = group_and_classify_roles(resolved, _tokens(split_label, plain_label), others)
        seen = _name_roles(verdicts, "core_planted_thing")
        blind = _name_roles(
            group_and_classify_roles(
                {split_label: (locations[backend],), plain_label: (locations[plain],)},
                _tokens(split_label, plain_label),
                [locations[core], locations[shared]],
            ),
            "core_planted_thing",
        )
    return (
        resolved == {split_label: (locations[backend], locations[core]), plain_label: (locations[plain],)}
        and others == [locations[shared]]
        and _single_role_with_verdict(seen, _VERDICT_IDENTICAL)
        and {member.package for member in seen[0].members} == {split_label, plain_label}
        and not blind
    )


# ---------------------------------------------------------------------------
# Fingerprint pass self-test fixtures (fp1-fp5)
# ---------------------------------------------------------------------------

_FINGERPRINT_ALPHA_SOURCE: Final[str] = (
    "def resolve_widget_limits(entity):\n"
    "    for field in entity.fields:\n"
    "        if field.required:\n"
    "            raise ValueError(field.name)\n"
    "    if entity.limits:\n"
    "        return entity.limits.maximum\n"
    "    return None\n"
)
# Renamed function, renamed parameter/local, different message -- same job.
_FINGERPRINT_BETA_RENAMED_SOURCE: Final[str] = (
    "def compute_caps(ent):\n"
    "    for f in ent.fields:\n"
    "        if f.required:\n"
    "            raise KeyError('missing ' + f.name)\n"
    "    if ent.limits:\n"
    "        return ent.limits.maximum\n"
    "    return None\n"
)
# Same control shape and attributes, inverted predicate -- a near match that diverges.
_FINGERPRINT_BETA_NEAR_SOURCE: Final[str] = _FINGERPRINT_BETA_RENAMED_SOURCE.replace(
    "if f.required", "if not f.required"
)
# Under FINGERPRINT_MIN_SKELETON_LINES (4 lines): fails only the size gate.
_FINGERPRINT_UNDERSIZE_ALPHA_SOURCE: Final[str] = (
    "def resolve_widget_limits(entity):\n"
    "    if entity.limits:\n"
    "        return entity.limits.maximum\n"
    "    return None\n"
)
_FINGERPRINT_UNDERSIZE_BETA_SOURCE: Final[str] = (
    "def compute_caps(ent):\n"
    "    if ent.limits:\n"
    "        return ent.limits.maximum\n"
    "    return None\n"
)
# Plenty of skeleton lines, but every model read is self-rooted: fails only the
# no-model-attribute gate.
_FINGERPRINT_NO_MODEL_ALPHA_SOURCE: Final[str] = (
    "def resolve_widget_limits(self, values):\n"
    "    total = 0\n"
    "    for value in values:\n"
    "        if self.cache.enabled:\n"
    "            total += value\n"
    "        else:\n"
    "            total -= value\n"
    "    if self.cache.limit and total > self.cache.limit:\n"
    "        raise ValueError('too big')\n"
    "    return total\n"
)
_FINGERPRINT_NO_MODEL_BETA_SOURCE: Final[str] = (
    "def compute_caps(self, amounts):\n"
    "    sum_ = 0\n"
    "    for amount in amounts:\n"
    "        if self.cache.enabled:\n"
    "            sum_ += amount\n"
    "        else:\n"
    "            sum_ -= amount\n"
    "    if self.cache.limit and sum_ > self.cache.limit:\n"
    "        raise ValueError('too big')\n"
    "    return sum_\n"
)


def _self_test_case_fingerprint_renamed_pair_reported() -> bool:
    """(fp1) NON-VACUITY: a cross-language pair no name/signature role groups
    (different names, no shared product) is reported as exactly one
    FINGERPRINT group spanning both packages, match="match", verdict not
    divergent -- and its rendered line names both members."""
    with tempfile.TemporaryDirectory(prefix="behaviour-parity-selftest-fp1-") as tmp:
        root = Path(tmp)
        _write_module(root / _SELF_TEST_ALPHA, _FINGERPRINT_ALPHA_SOURCE)
        _write_module(root / _SELF_TEST_BETA, _FINGERPRINT_BETA_RENAMED_SOURCE)
        labels = (_SELF_TEST_ALPHA, _SELF_TEST_BETA)
        by_role = key_functions_by_role({label: (root / label,) for label in labels}, _tokens(*labels))
        uncovered = uncovered_functions(by_role)
        groups = fingerprint_groups(uncovered)
        if len(groups) != 1:
            return False
        group = groups[0]
        members_named = {member.qualified_name for member in group.members} == {
            "resolve_widget_limits",
            "compute_caps",
        }
        big_enough = len(behaviour_skeleton(group.members[0]).splitlines()) >= FINGERPRINT_MIN_SKELETON_LINES
        line = fingerprint_line(group, root)
        return (
            members_named
            and big_enough
            and group.match == _FINGERPRINT_MATCH
            and group.verdict != _VERDICT_DIVERGENT
            and "resolve_widget_limits" in line
            and "compute_caps" in line
        )


def _self_test_case_fingerprint_near_match_divergent() -> bool:
    """(fp2) The inverted-predicate variant lands in one group with
    match="near-match" and verdict="divergent"."""
    with tempfile.TemporaryDirectory(prefix="behaviour-parity-selftest-fp2-") as tmp:
        root = Path(tmp)
        _write_module(root / _SELF_TEST_ALPHA, _FINGERPRINT_ALPHA_SOURCE)
        _write_module(root / _SELF_TEST_BETA, _FINGERPRINT_BETA_NEAR_SOURCE)
        labels = (_SELF_TEST_ALPHA, _SELF_TEST_BETA)
        by_role = key_functions_by_role({label: (root / label,) for label in labels}, _tokens(*labels))
        groups = fingerprint_groups(uncovered_functions(by_role))
        if len(groups) != 1:
            return False
        group = groups[0]
        return group.match == _FINGERPRINT_NEAR_MATCH and group.verdict == _VERDICT_DIVERGENT


def _self_test_case_fingerprint_covered_pair_absent() -> bool:
    """(fp3) The same body under the SAME name in both packages forms a name
    role (covered) and produces no fingerprint group."""
    with tempfile.TemporaryDirectory(prefix="behaviour-parity-selftest-fp3-") as tmp:
        root = Path(tmp)
        _write_module(root / _SELF_TEST_ALPHA, _FINGERPRINT_ALPHA_SOURCE)
        _write_module(root / _SELF_TEST_BETA, _FINGERPRINT_ALPHA_SOURCE)
        labels = (_SELF_TEST_ALPHA, _SELF_TEST_BETA)
        by_role = key_functions_by_role({label: (root / label,) for label in labels}, _tokens(*labels))
        uncovered = uncovered_functions(by_role)
        not_reopened = all(fn.qualified_name != "resolve_widget_limits" for fn in uncovered)
        return not_reopened and fingerprint_groups(uncovered) == []


def _self_test_case_fingerprint_thresholds() -> bool:
    """(fp4) A renamed pair whose skeleton is under
    FINGERPRINT_MIN_SKELETON_LINES, a renamed pair that reads no model
    attribute (self-only state), and two renamed copies inside ONE package
    each produce no group."""
    ok = True
    with tempfile.TemporaryDirectory(prefix="behaviour-parity-selftest-fp4a-") as tmp:
        root = Path(tmp)
        _write_module(root / _SELF_TEST_ALPHA, _FINGERPRINT_UNDERSIZE_ALPHA_SOURCE)
        _write_module(root / _SELF_TEST_BETA, _FINGERPRINT_UNDERSIZE_BETA_SOURCE)
        labels = (_SELF_TEST_ALPHA, _SELF_TEST_BETA)
        by_role = key_functions_by_role({label: (root / label,) for label in labels}, _tokens(*labels))
        ok = ok and fingerprint_groups(uncovered_functions(by_role)) == []
    with tempfile.TemporaryDirectory(prefix="behaviour-parity-selftest-fp4b-") as tmp:
        root = Path(tmp)
        _write_module(root / _SELF_TEST_ALPHA, _FINGERPRINT_NO_MODEL_ALPHA_SOURCE)
        _write_module(root / _SELF_TEST_BETA, _FINGERPRINT_NO_MODEL_BETA_SOURCE)
        labels = (_SELF_TEST_ALPHA, _SELF_TEST_BETA)
        by_role = key_functions_by_role({label: (root / label,) for label in labels}, _tokens(*labels))
        ok = ok and fingerprint_groups(uncovered_functions(by_role)) == []
    with tempfile.TemporaryDirectory(prefix="behaviour-parity-selftest-fp4c-") as tmp:
        root = Path(tmp)
        _write_module(root / _SELF_TEST_ALPHA, f"{_FINGERPRINT_ALPHA_SOURCE}\n\n{_FINGERPRINT_BETA_RENAMED_SOURCE}")
        labels = (_SELF_TEST_ALPHA,)
        by_role = key_functions_by_role({label: (root / label,) for label in labels}, _tokens(*labels))
        uncovered = uncovered_functions(by_role)
        ok = ok and len(uncovered) == 2 and fingerprint_groups(uncovered) == []
    return ok


def _self_test_case_fingerprint_report_only() -> bool:
    """(fp5) render_fingerprint_report over the fp1+fp2 groups logs every
    line below ERROR, one line per group, and a summary naming the group
    count and FINGERPRINT_MIN_SKELETON_LINES -- captured with
    _RecordingHandler, nothing reaching the real handlers."""
    groups: list[FingerprintGroup] = []
    uncovered_total = 0
    for beta_source in (_FINGERPRINT_BETA_RENAMED_SOURCE, _FINGERPRINT_BETA_NEAR_SOURCE):
        with tempfile.TemporaryDirectory(prefix="behaviour-parity-selftest-fp5-") as tmp:
            root = Path(tmp)
            _write_module(root / _SELF_TEST_ALPHA, _FINGERPRINT_ALPHA_SOURCE)
            _write_module(root / _SELF_TEST_BETA, beta_source)
            labels = (_SELF_TEST_ALPHA, _SELF_TEST_BETA)
            by_role = key_functions_by_role({label: (root / label,) for label in labels}, _tokens(*labels))
            uncovered = uncovered_functions(by_role)
            uncovered_total += len(uncovered)
            scan_groups = fingerprint_groups(uncovered)
            if len(scan_groups) != 1:
                return False
            groups.extend(scan_groups)
    handler = _RecordingHandler()
    previous_level, previous_propagate = logger.level, logger.propagate
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    try:
        render_fingerprint_report(groups, uncovered_total, _SELF_TEST_TREE)
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
        logger.propagate = previous_propagate
    below_error = bool(handler.levels) and all(level < logging.ERROR for level in handler.levels)
    line_count_ok = len(handler.messages) == len(groups) + 1
    summary = handler.messages[-1] if handler.messages else ""
    summary_ok = (
        "BEHAVIOUR-PARITY FINGERPRINT (report-only)" in summary
        and f"{len(groups)} group" in summary
        and f"{uncovered_total} uncovered" in summary
        and f"min skeleton lines={FINGERPRINT_MIN_SKELETON_LINES}" in summary
    )
    return below_error and line_count_ok and summary_ok


#: Package-name root of the synthetic platform packages the coordinate-key
#: cases import. Never a real package.
_SELF_TEST_PLATFORM_PREFIX: Final[str] = "behaviour_parity_selftest_platform"
_SELF_TEST_PLATFORM_MODULE: Final[str] = "tables.py"
_SELF_TEST_PLATFORM_ALPHA_SOURCE: Final[str] = '''
    from datrix_codegen_kernel.platform.realization_dsl import load_realization_table
    from datrix_common.plugin.capability_cells import BlockRealization

    _CELL = BlockRealization(structural_pattern="*/infra/main.tf")


    class Infra:
        def provision_database(self, block):
            return block.name


    def _adapt(provision):
        def plan_builder(block, service):
            del service
            return provision(block)

        return plan_builder


    def alpha_cache_plan(block, service):
        return service.name


    def alpha_uniform_plan(block, service):
        return None


    def alpha_helper(value):
        return value.strip()


    _DATABASE_BUILDER = _adapt(Infra().provision_database)

    ALPHA_TABLE = load_realization_table(
        platform_label="alpha",
        block_realizations={
            ("rdbms", "small"): _CELL,
            ("rdbms", "large"): _CELL,
            ("cache", "small"): _CELL,
            ("queue", "small"): _CELL,
            ("nosql", "small"): _CELL,
        },
        plan_builders={
            ("rdbms", "small"): _DATABASE_BUILDER,
            ("rdbms", "large"): _DATABASE_BUILDER,
            ("cache", "small"): alpha_cache_plan,
            ("queue", "small"): alpha_uniform_plan,
            ("nosql", "small"): alpha_uniform_plan,
        },
    )
'''
_SELF_TEST_PLATFORM_BETA_SOURCE: Final[str] = '''
    from datrix_codegen_kernel.platform.realization_dsl import load_realization_table
    from datrix_common.plugin.capability_cells import BlockRealization

    _CELL = BlockRealization(structural_pattern="*/infra/main.bicep")


    class BetaInfra:
        def make_db_plan(self, block, service):
            return service.name


    def beta_redis_builder(block, service):
        return block.name


    def beta_helper(value):
        return value.strip()


    BETA_TABLE = load_realization_table(
        platform_label="beta",
        block_realizations={("rdbms", "tiny"): _CELL, ("cache", "tiny"): _CELL},
        plan_builders={
            ("rdbms", "tiny"): BetaInfra().make_db_plan,
            ("cache", "tiny"): beta_redis_builder,
        },
    )
'''
_SELF_TEST_PLATFORM_NO_TABLE_SOURCE: Final[str] = "def plain_function(value):\n    return value\n"
_SELF_TEST_PLATFORM_UNBOUND_TABLE_SOURCE: Final[str] = '''
    from datrix_codegen_kernel.platform.realization_dsl import load_realization_table


    def build_table():
        return load_realization_table(platform_label="gamma", block_realizations={}, plan_builders={})
'''


def _two_delegate_adapter(first: Callable[..., object], second: Callable[..., object]) -> Callable[..., object]:
    """A nested function closing over TWO callables: the shape
    ``_defining_function`` must refuse, since no single function holds its
    behaviour."""

    def plan_builder(block: object, service: object) -> tuple[object, object]:
        return first(block), second(service)

    return plan_builder


def _write_platform_package(root: Path, label: str, source: str) -> Path:
    """One synthetic platform package ``root/<prefix>_<label>`` holding one
    module; returns its src dir."""
    src_dir = root / f"{_SELF_TEST_PLATFORM_PREFIX}_{label}"
    _write_module(src_dir, source, _SELF_TEST_PLATFORM_MODULE)
    return src_dir


def _purge_synthetic_platform_modules() -> None:
    for name in [name for name in sys.modules if name.startswith(_SELF_TEST_PLATFORM_PREFIX)]:
        del sys.modules[name]


def _self_test_case_coordinate_key() -> bool:
    """(c1) Two synthetic platform packages register plan builders through
    ``load_realization_table``. The coordinate index resolves a builder bound
    to several flavors of ONE block type (through a delegating adapter over a
    bound method, and through a plain bound method) to that block type's role,
    leaves a uniform builder bound to several block types out, and keys a
    function that is no plan builder by the unchanged name ladder. The scan
    with the index finds MORE roles than the same scan keyed by name alone, and
    a scan given no index never produces a coordinate role (the language axis
    passes none)."""
    with tempfile.TemporaryDirectory(prefix="behaviour-parity-selftest-c1-") as tmp:
        root = Path(tmp)
        alpha_dir = _write_platform_package(root, _SELF_TEST_ALPHA, _SELF_TEST_PLATFORM_ALPHA_SOURCE)
        beta_dir = _write_platform_package(root, _SELF_TEST_BETA, _SELF_TEST_PLATFORM_BETA_SOURCE)
        target_src_dirs = {_SELF_TEST_ALPHA: (alpha_dir,), _SELF_TEST_BETA: (beta_dir,)}
        sys.path.insert(0, str(root))
        importlib.invalidate_caches()
        try:
            index = platform_coordinate_index(target_src_dirs)
        finally:
            sys.path.remove(str(root))
            _purge_synthetic_platform_modules()
        tokens = _tokens(_SELF_TEST_ALPHA, _SELF_TEST_BETA)
        by_qualified = {
            fn.qualified_name: fn
            for label, src_dirs in target_src_dirs.items()
            for src_dir in src_dirs
            for fn in collect_function_sources(src_dir, label)
        }
        with_index = group_and_classify_roles(target_src_dirs, tokens, [], index)
        without_index = group_and_classify_roles(target_src_dirs, tokens, [])
        coordinate_roles = {
            verdict.role_key: {member.qualified_name for member in verdict.members}
            for verdict in with_index
            if isinstance(verdict.role_key, CoordinateRole)
        }
        rdbms, cache = CoordinateRole("rdbms"), CoordinateRole("cache")
        return (
            len(index) == 4
            and _coordinate_role_key_for(by_qualified["Infra.provision_database"], index) == rdbms
            and _coordinate_role_key_for(by_qualified["BetaInfra.make_db_plan"], index) == rdbms
            and _coordinate_role_key_for(by_qualified["alpha_cache_plan"], index) == cache
            and _coordinate_role_key_for(by_qualified["alpha_uniform_plan"], index) is None
            and _coordinate_role_key_for(by_qualified["alpha_helper"], index) is None
            and _role_key_for(by_qualified["alpha_uniform_plan"], tokens[_SELF_TEST_ALPHA], index)
            == NameRole("uniform_plan")
            and _role_key_for(by_qualified["alpha_helper"], tokens[_SELF_TEST_ALPHA], index) == NameRole("helper")
            and coordinate_roles
            == {
                rdbms: {"Infra.provision_database", "BetaInfra.make_db_plan"},
                cache: {"alpha_cache_plan", "beta_redis_builder"},
            }
            and len(with_index) == len(without_index) + len(coordinate_roles)
            and not any(isinstance(verdict.role_key, CoordinateRole) for verdict in without_index)
            and role_label(rdbms) == "coordinate:rdbms"
            and _role_key_for(by_qualified["Infra.provision_database"], tokens[_SELF_TEST_ALPHA])
            == NameRole("provision_database")
        )


def _self_test_case_coordinate_key_fails_closed() -> bool:
    """(c2) A platform whose tables cannot be located or resolved fails the
    scan naming the cause, never keying that platform by name instead: a
    package building no table, a ``load_realization_table`` call that is not
    a module-level assignment, an unimportable module, an adapter closing over
    two callables, and a builder that is not a function are each refused."""
    with tempfile.TemporaryDirectory(prefix="behaviour-parity-selftest-c2-") as tmp:
        root = Path(tmp)
        no_table = _write_platform_package(root, "notable", _SELF_TEST_PLATFORM_NO_TABLE_SOURCE)
        unbound = _write_platform_package(root, "unbound", _SELF_TEST_PLATFORM_UNBOUND_TABLE_SOURCE)
        return (
            _refuses(lambda: platform_realization_tables("notable", [no_table]), "builds no RealizationTable", "notable")
            and _refuses(
                lambda: platform_realization_tables("unbound", [unbound]), "module-level assignment", "tables.py"
            )
            and _refuses(
                lambda: platform_coordinate_index({"notable": (no_table,), "unbound": (unbound,)}),
                "builds no RealizationTable",
            )
            and _refuses(
                lambda: _import_table("behaviour_parity_selftest_missing_module", "TABLE", "gamma"),
                "cannot import",
                "gamma",
            )
            and _refuses(lambda: _defining_function(_two_delegate_adapter(print, repr), "cell"), "closes over 2")
            and _refuses(lambda: _defining_function(len, "cell"), "neither a function nor a bound method")
        )


#: The floor on live coordinate roles: block types whose plan builders are
#: registered by at least two platform packages. Measured on the live tree
#: (rdbms, cache, pubsub, queue, nosql, storage, serverless); a regression to
#: name-only grouping, an unresolvable registration or a platform that stops
#: registering a block type's builder drops the count below it.
_PLATFORM_COORDINATE_ROLE_FLOOR: Final[int] = 7


def _self_test_case_live_coordinate_floor() -> bool:
    """(c3) The live platform index resolves at least
    ``_PLATFORM_COORDINATE_ROLE_FLOOR`` block types that two or more platform
    packages register a plan builder for. Name-only grouping resolves none of
    them, so a regression to it fails here before any real scan is trusted."""
    target_src_dirs = discover_target_package_src_dirs(AXIS_PLATFORMS, registered_platform_names(), WORKSPACE_ROOT)
    try:
        index = platform_coordinate_index(target_src_dirs)
    except (ValueError, SkeletonError) as exc:
        logger.error("behaviour_parity:the live platform coordinate index cannot be built: %s", exc)
        return False
    labels_by_role: dict[CoordinateRole, set[str]] = {}
    for (file_path, _), role in index.items():
        for label, src_dirs in target_src_dirs.items():
            if any(file_path.is_relative_to(src_dir.resolve()) for src_dir in src_dirs):
                labels_by_role.setdefault(role, set()).add(label)
    spanning = [role for role, labels in labels_by_role.items() if len(labels) >= _MIN_PACKAGES_FOR_COMPARISON]
    logger.info(
        "behaviour-parity self-test: %d live coordinate role(s) span two or more platform packages (floor %d): %s",
        len(spanning),
        _PLATFORM_COORDINATE_ROLE_FLOOR,
        sorted(role.block_type for role in spanning),
    )
    return len(spanning) >= _PLATFORM_COORDINATE_ROLE_FLOOR


def run_self_test() -> bool:
    """Prove the gate's non-vacuity: each synthetic role lands in exactly its
    bucket, the refusal path refuses, a broken member fails closed, every
    ladder step fires and declines on synthetic input, no declared hole
    excuses a divergent role, an
    undomained failing role is counted, the ratchet fails in both directions
    and the baseline loader refuses an unknown key, and the report filters
    never move the verdict.

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
        _self_test_case_declared_hole_still_fails(),
        "(n) NEG: a divergent role whose package would have been declared unsupported (or on-demand) for its "
        "domain, and one whose member is an @emit_adapter over a builtin group that would have been declared "
        "unsupported, STILL FAIL naming both groups -- evaluate_role takes the role alone",
    )
    ok &= _assert(
        _self_test_case_no_declaration_reader(),
        "(o) no declaration reader: this module's own AST imports, names and reads no domain stance, builtin-group "
        "stance, capability-gap row or on-demand table; the matcher finds each one planted in a synthetic source",
    )
    ok &= _assert(
        _self_test_case_report_filters(),
        "(p) report filters: --scope/--buckets choose which role lines print (a role prints when its domain and "
        "verdict satisfy every filter given); unknown ids and empty options are refused",
    )
    ok &= _assert(
        _self_test_case_skeleton_groups_fail_naming_every_group(),
        "(q1) a divergent role split into two skeleton groups FAILs with one reason naming both groups -- no "
        "reference language, no lagging side",
    )
    ok &= _assert(
        _self_test_case_bucket_labels(),
        "(q4) the bucket labels printed and accepted are exactly identical / same-behaviour / divergent",
    )
    ok &= _assert(
        _self_test_case_gate_outcome(),
        "(r) gate: a divergent role FAILs and is counted (naming the role and every group, no in-scope split in "
        "the printed verdict); a pin equal to the live count exits 0; duplicate buckets fail unless "
        "adapter-exempt; both axes gate unless --report-only, and an unknown axis is refused",
    )
    ok &= _assert(
        _self_test_case_undomained_role_counted(),
        "(r1) an undomained failing role is COUNTED like a domained one -- by the failing-role count, the bucket "
        "split and the ratchet; a pin that omits it fails",
    )
    ok &= _assert(
        _self_test_case_population_ratchet_both_directions(),
        "(r2) ratchet: a live count above the pin fails (regression), a live count below the pin fails (an "
        "unbanked improvement), only an exact match passes; an unpinned axis raises; a stale bucket split is a "
        "note, never a verdict",
    )
    ok &= _assert(
        _self_test_case_baseline_loader(),
        "(r3) baseline loader: a well-formed file (and one whose pin alone was edited) loads; an unrecognized "
        "top-level or nested key, a missing or unknown bucket key, a negative/float/bool count, an empty, "
        "malformed or missing file are each refused naming the file and the key",
    )
    ok &= _assert(
        _self_test_case_filters_never_move_the_verdict(),
        "(t) filters never move the verdict: a filter that admits no role removes its line from the report, yet "
        "the gate summary and the ratchet verdict equal the unfiltered run's",
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
    ok &= _assert(
        _self_test_case_client_target_generator_names(),
        "(z1) a transpiler_profile-bearing native generator class is included by "
        "registered_client_target_generator_names; a transpiler_profile=None sibling is excluded",
    )
    ok &= _assert(
        _self_test_case_client_target_token_fallback(),
        "(z2) tokens_for falls back to a ClientTargetCapabilityDeclaration.name_tokens fixture when no "
        "LanguageCapabilityDeclaration resolves for the label",
    )
    ok &= _assert(
        _self_test_case_merged_axis_group_and_classify(),
        "(z3) group_and_classify_roles fed a merged language+generator target_src_dirs produces a role "
        "spanning both, neither excluded as an 'other package'",
    )
    ok &= _assert(
        _self_test_case_merged_axis_min_packages_still_refused(),
        "(z4) a merged language+generator set of size 1 is still refused -- the floor is not weakened",
    )
    ok &= _assert(
        _self_test_case_client_target_generator_src_dir_resolution(),
        "(z5) discover_client_target_generator_src_dirs resolves a planted fixture to its on-disk src/ "
        "directory, and raises naming the unresolved name and the discovered roots when it cannot",
    )
    ok &= _assert(
        _self_test_case_language_core_is_a_member_not_an_other_package(),
        "(z6) a fixture language split into a backend and a core resolves both packages under one label; "
        "a function planted only in the core is compared as that language's member, and the core is never "
        "an 'other package' (fed as one, the role is excluded)",
    )
    ok &= _assert(
        _self_test_case_fingerprint_renamed_pair_reported(),
        "(fp1) NON-VACUITY: a renamed cross-language pair no name/signature role covers is reported as one "
        "FINGERPRINT group naming both members",
    )
    ok &= _assert(
        _self_test_case_fingerprint_near_match_divergent(),
        "(fp2) an inverted-predicate variant lands in the same group as near-match/divergent",
    )
    ok &= _assert(
        _self_test_case_fingerprint_covered_pair_absent(),
        "(fp3) a pair sharing one name (covered by a name role) produces no fingerprint group",
    )
    ok &= _assert(
        _self_test_case_fingerprint_thresholds(),
        "(fp4) an under-size pair, a no-model-attribute pair, and two renamed copies in one package each "
        "produce no fingerprint group",
    )
    ok &= _assert(
        _self_test_case_fingerprint_report_only(),
        "(fp5) render_fingerprint_report logs every line below ERROR, one per group plus a summary naming "
        "the group count and FINGERPRINT_MIN_SKELETON_LINES",
    )
    ok &= _assert(
        _self_test_case_coordinate_key(),
        "(c1) coordinate key: plan builders registered through load_realization_table (one through a delegating "
        "adapter over a bound method) resolve to their block type, folding flavors; a uniform multi-block-type "
        "builder and a non-builder keep the name key; the scan finds more roles than name-only grouping; no index, "
        "no coordinate role",
    )
    ok &= _assert(
        _self_test_case_coordinate_key_fails_closed(),
        "(c2) coordinate key fails closed: a platform with no table, an unbound load_realization_table call, an "
        "unimportable module, a two-delegate adapter and a non-function builder are each refused naming the cause",
    )
    ok &= _assert(
        _self_test_case_live_coordinate_floor(),
        f"(c3) the live platform index resolves at least {_PLATFORM_COORDINATE_ROLE_FLOOR} block types that two or "
        f"more platform packages register a plan builder for -- the floor name-only grouping cannot reach",
    )
    return ok


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Behaviour-parity gate: role grouping, behaviour-skeleton classification, domain resolution "
            "and the pinned, two-directional failing-role ratchet."
        )
    )
    parser.add_argument("--self-test", action="store_true", help="Run only the non-vacuity self-test.")
    parser.add_argument("--axis", choices=(AXIS_LANGUAGES, AXIS_PLATFORMS), default=AXIS_LANGUAGES)
    parser.add_argument(
        "--scope",
        default=None,
        help=(
            f"{_FILTER_SEPARATOR!r}-separated shared domain ids and/or {UNDOMAINED!r} whose role lines the report "
            f"prints. A report filter only: it never changes the failing-role count or the exit code."
        ),
    )
    parser.add_argument(
        "--buckets",
        default=None,
        help=(
            f"{_FILTER_SEPARATOR!r}-separated verdict-bucket ids, drawn from {sorted(_VALID_BUCKET_IDS)}, whose "
            f"role lines the report prints. A report filter only: it never changes the failing-role count or the "
            f"exit code."
        ),
    )
    parser.add_argument(
        "--report-only", action="store_true", help="Render the classification report only; exit 0 regardless."
    )
    parser.add_argument("--debug", action="store_true", help="Log every role, not just failing/divergent ones.")
    parser.add_argument(
        "--fingerprint",
        action="store_true",
        help=(
            "Also run the report-only skeleton-fingerprint grouping pass over functions no name/signature "
            "role covers; never affects the exit code."
        ),
    )
    return parser


def _refuse_gate_options_when_not_gating(args: argparse.Namespace) -> None:
    """``--scope``/``--buckets`` filter the gate report; on a run that renders
    a report only they would be silently ignored, so they are refused instead."""
    given = [name for name, value in (("--scope", args.scope), ("--buckets", args.buckets)) if value is not None]
    if given:
        raise ValueError(
            f"behaviour_parity: {given} only apply to a gating run (without --report-only); a --report-only run "
            f"renders a role report and never fails. Fix: drop the option(s), or drop --report-only."
        )


def _run_scan(args: argparse.Namespace) -> int:
    """Discover, classify and -- on a gating run -- evaluate every role and
    compare the failing-role count with its pin.

    Returns:
        ``EXIT_OK`` or ``EXIT_FAIL`` (``gate_exit_code`` over the ratchet's
        problems); ``EXIT_OK`` for a report-only run.

    Raises:
        ValueError: A usage/discovery error (unknown scope or bucket id,
            unresolvable package, an unreadable or malformed baseline, an
            axis with no baseline section).
        SkeletonError: An unparseable or unclassifiable member.
    """
    axis: str = args.axis
    target_names = registered_language_names() if axis == AXIS_LANGUAGES else registered_platform_names()
    target_src_dirs = discover_target_package_src_dirs(axis, target_names, WORKSPACE_ROOT)
    if axis == AXIS_LANGUAGES:
        generator_names = registered_client_target_generator_names()
        target_src_dirs = {
            **target_src_dirs,
            **discover_client_target_generator_src_dirs(generator_names, WORKSPACE_ROOT),
        }
    if not axis_gates(axis, report_only=args.report_only):
        _refuse_gate_options_when_not_gating(args)
        scan = discover_role_scan(axis, target_src_dirs, WORKSPACE_ROOT)
        render_report(scan.verdicts, WORKSPACE_ROOT, debug=args.debug)
        if args.fingerprint:
            _run_fingerprint_pass(scan, WORKSPACE_ROOT)
        return EXIT_OK
    report_filter = build_report_filter(
        parse_scope_argument(args.scope), parse_buckets_argument(args.buckets), frozenset(SHARED_CONTEXT_TYPES)
    )
    baseline = load_baseline()
    if axis not in baseline:
        raise ValueError(
            f"behaviour_parity:{BEHAVIOUR_PARITY_BASELINE_PATH} has no [{axis}] section to gate the {axis} axis "
            f"against; sections present: {sorted(baseline)}. Fix: seed the section from a live run of the gate."
        )
    logger.info(
        "behaviour-parity gate: packages=%s baseline=%s", sorted(target_src_dirs), BEHAVIOUR_PARITY_BASELINE_PATH.name
    )
    scan = discover_role_scan(axis, target_src_dirs, WORKSPACE_ROOT)
    evaluations = evaluate_roles(scan.verdicts)
    render_gate_report(evaluations, WORKSPACE_ROOT, report_filter=report_filter, debug=args.debug)
    if args.fingerprint:
        _run_fingerprint_pass(scan, WORKSPACE_ROOT)
    problems = population_problems(axis, evaluations, baseline)
    for problem in problems:
        logger.error("BEHAVIOUR-PARITY RATCHET: %s", problem)
    if not problems:
        logger.info(
            "BEHAVIOUR-PARITY RATCHET: %s axis -- %d failing role(s) match the pin in %s.",
            axis,
            failing_role_count(evaluations),
            BEHAVIOUR_PARITY_BASELINE_PATH.name,
        )
    for note in diagnostic_split_notes(axis, live_buckets=failing_bucket_split(evaluations), baseline=baseline):
        logger.warning("BEHAVIOUR-PARITY RATCHET: %s", note)
    return gate_exit_code(problems)


def _run_fingerprint_pass(scan: RoleScan, workspace_root: Path) -> None:
    """The report-only fingerprint pass over *scan*'s uncovered roles --
    never called on the exit-code path; its result is logged only."""
    uncovered = uncovered_functions(scan.by_role)
    render_fingerprint_report(fingerprint_groups(uncovered), len(uncovered), workspace_root)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Returns:
        ``EXIT_OK`` (self-test passed and the failing-role count equals its
        pin, or the run was report-only), ``EXIT_FAIL`` (the count differs
        from its pin), ``EXIT_USAGE`` (self-test failed, usage error, an
        unreadable baseline, fewer than two registered packages, or a
        discovery/parse error).
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
