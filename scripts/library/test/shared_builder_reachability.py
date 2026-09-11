#!/usr/bin/env python3
"""Shared-builder reachability gate: every public ``build_*`` function declared
in ``datrix_codegen_common``'s ``algorithms/`` and ``context_models/`` modules
must have at least one production caller -- somewhere across
datrix-codegen-common itself, every registered language package, or datrix-cli
-- outside its own defining module and outside test code.

A shared context builder that is written, exported and unit-tested but never
called from any of those places looks complete by every signal except the one
that matters: it never executes on a real generation run. That shape has
recurred multiple times as machinery gets hoisted into this package for several
languages to share, and adopting it in one language while leaving another's
hoist half-finished is invisible to every other gate, because every other gate
asks whether the code is correct, never whether it runs.

**Why this is a script and not a pytest module.** Answering the question at all
requires reading every registered language package's source plus datrix-cli's,
from a check that conceptually belongs to datrix-codegen-common. That is a
cross-cutting conformance gate, and the repo boundary is explicit about where
one lives: repo-level validation is a script under ``datrix/scripts/test/``,
never a pytest module inside a package (a package tests only its own surface,
and a unit test importing several generator packages is exactly the coupling
the import-boundary rule exists to prevent). The gate's LOCATION was the defect;
its behaviour is carried over unchanged.

**The scanned package set is derived, never hardcoded.** The language packages
come from the installed ``datrix.languages`` entry points at run time, so a
newly installed language target joins the scan with no edit here, and the gate
refuses to run against fewer than two of them rather than passing vacuously.

Scan method: whole-tree AST import/call-graph resolution, never text matching.
Three corrections were required to make the walk match real Python call
semantics, each verified against a real function this scan must not miscall
dead:

1. **Cross-package resolution.** A hoisted builder's callers live in the
   packages that were hoisted FROM, not in the package the builder now lives in
   -- that is the entire point of a hoist. A caller search scoped to the
   defining package alone reports every correctly-wired hoist as dead. This is
   why the scan walks every scanned package's own import graph (following
   aliased imports, ``import X as Y`` and ``from X import Y as Z``, and
   attribute calls, ``module.build_x(...)``) rather than grepping one package
   for the function's bare name.
2. **Aliased-wrapper indirection.** A caller routinely delegates through a
   same-named private wrapper that keeps the pre-hoist name so its own call
   sites do not have to change, e.g. ``_extract_max_length(field)`` returning
   ``_shared_extract_max_length(field, ...)`` where
   ``_shared_extract_max_length`` is bound by
   ``from ... import extract_max_length as _shared_extract_max_length``.
   A regex anchored with ``\\b`` never matches inside ``_extract_max_length``,
   because the underscore is a word character -- and even a correct regex on the
   RIGHT name would still miss the call site, since the call site never spells
   ``extract_max_length`` at all, only its import alias. Resolving the call
   requires reading the aliased import binding, which only an AST walk (not a
   text search) can do.

   A package's own ``__init__.py`` re-exporting a definition from a submodule
   (``from datrix_codegen_common.algorithms.entity import build_entity_context``)
   is itself an ordinary import binding, so a caller that imports from the
   package root rather than the submodule is resolved by chasing that binding
   one hop further (bounded, to avoid an unbounded chase on a cyclic re-export).
3. **Thin delegation.** A third correction, for a shape a caller search cannot
   see because there is genuinely no caller and the code is still live. The
   shared domain registry requires one directly-importable
   ``build_<domain>_context`` per registered domain; for the test-axis domains
   that builder is a THIN WRAPPER -- its whole body is
   ``return TestPlanContext(kind=..., emissions=tuple(plan_<kind>_tests(...)))``
   -- while the production path builds the identical value generically inside
   ``TestGeneratorOrchestrator.generate_for_service``, with no per-kind branch
   (a kind->builder dispatch table is forbidden by design). The delegated
   ``plan_<kind>_tests`` IS what production runs; each language package hands it
   to the orchestrator at construction. So the scan resolves one level THROUGH
   such a wrapper's body: a definition with no direct caller counts as live when
   its entire body is one context construction whose payload delegates to a
   callee some module OUTSIDE this package binds, and whose constructed type
   some other production module builds.

   Both halves are load-bearing, and the single-statement requirement is what
   "thin" means. A builder that walks the model, branches, logs, or returns
   ``None`` for an absent block is never classified as a delegation, whatever
   types it touches -- which is why this refinement rescues the sixteen wrappers
   without rescuing a single genuinely orphaned builder.

This is a hard-zero gate, not a decrease-only ratchet: no exemption file and no
pinned baseline of known offenders. A baseline on a gate whose entire job is
"notice code nobody wired in" would silently exempt exactly the class of defect
it exists to catch -- and the delegation rule above is a structural predicate
over real call semantics, naming no function, precisely so that no exemption
list is needed. When this gate is red, the fix is to wire the named function
into its consuming package(s) or orchestrator, or to delete it -- never to add
its name here.

Built-in non-vacuity self-test, every invocation, before any real census is
trusted. Five planted fixture trees prove, in both directions, that the scanner
and the delegation rule still discriminate:

* a planted orphan build_* is reported dead by name, and wiring a real
  cross-module caller clears it;
* a caller reached ONLY through an aliased private wrapper is still resolved
  (the shape no text search can see);
* a thin wrapper over a production-bound plan is recognized as live, with the
  delegate and context type it resolved through recorded;
* a MULTI-STATEMENT builder touching the same production-bound plan and
  constructing the same production-built context type is STILL dead -- the half
  that matters most, since a delegation rule that rescued it would have quietly
  disabled the whole gate;
* a thin wrapper whose delegate nothing outside the defining package binds is
  an orphan with an extra hop, and is still dead.

Repo-level validation script (per the datrix showcase boundary -- no pytest
suite lives in datrix).

Usage::

    python shared_builder_reachability.py
    python shared_builder_reachability.py --debug
    python shared_builder_reachability.py --self-test
    python shared_builder_reachability.py --census
"""

from __future__ import annotations

import argparse
import ast
import importlib
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

from datrix_common.plugin.registry import LANGUAGES_GROUP, entry_points  # noqa: E402
from shared.registered_targets import registered_language_names  # noqa: E402

logger = logging.getLogger(__name__)

EXIT_OK: Final[int] = 0
EXIT_FAIL: Final[int] = 1
EXIT_USAGE: Final[int] = 2

#: The package owning the shared builders under scan.
DEFINING_PACKAGE: Final[str] = "datrix_codegen_common"

#: The CLI package. Not a target: it is the single pipeline host, and a shared
#: builder wired only into the pipeline (never into a language package) is
#: legitimately live, so its call graph belongs in the scan.
CLI_PACKAGE: Final[str] = "datrix_cli"

#: Direct subpackages of DEFINING_PACKAGE whose module-level ``build_*``
#: definitions this gate polices.
TARGET_SUBPACKAGES: Final[tuple[str, ...]] = ("algorithms", "context_models")

#: Bound on chasing ``__init__`` re-export hops, so a cyclic re-export cannot
#: make resolution loop forever.
_MAX_REEXPORT_DEPTH: Final[int] = 6

#: A cross-target gate compares targets; one target is not a comparison, and
#: passing with a truncated target set is how a gate silently stops covering
#: what it claims to (Decision 28 invariant 2).
_MIN_LANGUAGES_FOR_SCAN: Final[int] = 2


class ScanConfigurationError(RuntimeError):
    """The package set under scan could not be resolved, or is too small to
    carry the claim this gate makes."""


@dataclass(frozen=True)
class ReachabilityCensus:
    """Result of one reachability scan.

    Attributes:
        dead: Qualnames (``module.function``) with neither a resolved caller
            outside their own defining module nor a live thin delegation
            (see :func:`_thin_delegation_of`).
        callers: Qualname -> the (non-empty) set of calling modules, for every
            qualname that has at least one resolved caller.
        delegating: Qualname -> the delegation that keeps it live, for every
            definition with no direct external caller that is nonetheless a thin
            wrapper over a production-bound callee.
    """

    dead: frozenset[str]
    callers: Mapping[str, frozenset[str]]
    delegating: Mapping[str, _ThinDelegation]


@dataclass(frozen=True)
class _ThinDelegation:
    """A ``build_*`` wrapper whose entire body is one context construction that
    delegates its payload to a callee imported from another module.

    Attributes:
        context_type: Dotted name the constructed context type resolves to.
        delegate: Dotted name of the single imported callee the construction's
            arguments delegate to.
    """

    context_type: str
    delegate: str


def _package_src_root(import_name: str) -> Path:
    """The directory directly containing *import_name*'s top-level package
    directory (its own ``src/``).

    Derived from the imported package's own ``__file__`` rather than a
    hardcoded path, so the scan tracks wherever the packages are actually
    installed from.

    Args:
        import_name: Top-level package import name (e.g. ``datrix_cli``).

    Returns:
        The absolute ``src/`` directory holding that package.

    Raises:
        ScanConfigurationError: If the package cannot be imported, or is a
            namespace package with no ``__file__`` to locate it by.
    """
    try:
        module = importlib.import_module(import_name)
    except ImportError as exc:
        raise ScanConfigurationError(
            f"Cannot import package {import_name!r} to locate its source tree: {exc}. "
            f"Expected every scanned package to be installed into the active "
            f"environment. Fix: install the datrix packages in editable mode into "
            f"D:\\datrix\\.venv."
        ) from exc
    module_file = getattr(module, "__file__", None)
    if module_file is None:
        raise ScanConfigurationError(
            f"Package {import_name!r} has no __file__, so its source tree cannot be "
            f"located (a namespace package cannot be scanned). Expected a regular "
            f"package with an __init__.py. Fix: install it as a normal package."
        )
    return Path(module_file).resolve().parent.parent


def _language_package_names() -> dict[str, str]:
    """Registered language name -> its plugin's top-level module root.

    Read from each entry point's DECLARED module rather than by loading the
    plugin: this gate only needs to know which package the code lives in.

    Returns:
        ``{language name: import name}`` for every installed ``datrix.languages``
        entry point.
    """
    return {ep.name: ep.module.split(".")[0] for ep in entry_points(group=LANGUAGES_GROUP)}


def discover_package_src_roots() -> dict[str, Path]:
    """Every package this gate scans, mapped to its own ``src/`` directory.

    The set is the defining package, every registered language package, and the
    CLI -- the language half derived from the installed ``datrix.languages``
    entry points at run time, never a literal list.

    Returns:
        ``{import name: src directory}``.

    Raises:
        ScanConfigurationError: If a registered language has no resolvable
            module root, or fewer than :data:`_MIN_LANGUAGES_FOR_SCAN` languages
            are installed (a truncated target set is a configuration error, not
            a smaller pass).
    """
    language_names = sorted(registered_language_names())
    module_roots = _language_package_names()
    missing = [name for name in language_names if name not in module_roots]
    if missing:
        raise ScanConfigurationError(
            f"Registered language(s) {missing} have no resolvable entry-point module "
            f"root. Expected every name in the '{LANGUAGES_GROUP}' group to declare "
            f"a module. Fix: repair the offending package's entry-point declaration."
        )
    if len(language_names) < _MIN_LANGUAGES_FOR_SCAN:
        raise ScanConfigurationError(
            f"Only {len(language_names)} registered language(s) ({language_names}) are "
            f"installed; this gate needs at least {_MIN_LANGUAGES_FOR_SCAN} to make the "
            f"cross-package claim it makes. Expected the '{LANGUAGES_GROUP}' entry-point "
            f"group to carry every installed language target. Fix: install the "
            f"datrix-codegen-* packages into D:\\datrix\\.venv before running the gate."
        )
    import_names = (
        [DEFINING_PACKAGE] + [module_roots[name] for name in language_names] + [CLI_PACKAGE]
    )
    return {import_name: _package_src_root(import_name) for import_name in import_names}


def _module_name_for(path: Path, src_root: Path) -> str:
    """Dotted module name for *path*, a ``.py`` file under *src_root*."""
    rel = path.relative_to(src_root).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _resolve_from_base(node: ast.ImportFrom, own_package_parts: list[str]) -> list[str]:
    """The dotted package-part list a ``from ... import ...`` statement's module
    segment (if any) resolves to, absolute or relative."""
    if node.level == 0:
        return node.module.split(".") if node.module else []
    up = node.level - 1
    base = own_package_parts[: len(own_package_parts) - up] if up else list(own_package_parts)
    if node.module:
        base = base + node.module.split(".")
    return base


def _import_bindings(tree: ast.Module, current_module: str, is_package_init: bool) -> dict[str, str]:
    """Map every name a module-level or nested import introduces to the dotted
    string it refers to (a module, or ``module.attribute``).

    ``import a.b.c as w`` binds ``w`` -> ``"a.b.c"``. Unaliased ``import a.b.c``
    binds only the root ``a`` -> ``"a"`` (ordinary Python import semantics -- the
    rest of the chain is reached by attribute access starting from ``a``, which
    the call-chain reconstruction below already does). ``from X import Y [as Z]``
    binds ``Z`` (or ``Y``) -> ``"X.Y"``, absolute or relative per *node.level*.
    ``from X import *`` is dropped -- unresolvable without evaluating ``X``, and
    this codebase's production sources use none.
    """
    bindings: dict[str, str] = {}
    own_package_parts = current_module.split(".")
    if not is_package_init:
        own_package_parts = own_package_parts[:-1]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    bindings[alias.asname] = alias.name
                else:
                    root = alias.name.split(".")[0]
                    bindings[root] = root
        elif isinstance(node, ast.ImportFrom):
            base_dotted = ".".join(_resolve_from_base(node, own_package_parts))
            for alias in node.names:
                if alias.name == "*":
                    continue
                local = alias.asname or alias.name
                bindings[local] = f"{base_dotted}.{alias.name}" if base_dotted else alias.name
    return bindings


def _call_target_chains(tree: ast.Module) -> list[list[str]]:
    """Every ``Call``'s callee spelled as a dotted-name chain, e.g.
    ``["a", "b", "func"]`` for ``a.b.func(...)`` or ``["func"]`` for
    ``func(...)``. A callee that is not a plain name/attribute chain (a
    subscript, a call result, ...) cannot be resolved statically and is
    omitted."""
    chains: list[list[str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        chain = _chain_of(node.func)
        if chain is not None:
            chains.append(chain)
    return chains


def _resolve_to_definition(
    candidate: str,
    definition_qualnames: frozenset[str],
    bindings_by_module: Mapping[str, Mapping[str, str]],
    depth: int = 0,
) -> str | None:
    """Chase *candidate* (a dotted ``module....attr`` guess built from one call
    site's own import bindings) to a known definition qualname, following
    package ``__init__`` re-exports up to a bounded depth."""
    if candidate in definition_qualnames:
        return candidate
    if depth >= _MAX_REEXPORT_DEPTH or "." not in candidate:
        return None
    module_prefix, last_attr = candidate.rsplit(".", 1)
    local_bindings = bindings_by_module.get(module_prefix)
    if local_bindings and last_attr in local_bindings:
        return _resolve_to_definition(
            local_bindings[last_attr], definition_qualnames, bindings_by_module, depth + 1
        )
    return None


@dataclass(frozen=True)
class _RepositoryIndex:
    """Every ``.py`` file under a set of package src roots, parsed once.

    The two chain caches are filled on first use and reused for every
    subsequent question about the same module. Each of the four resolution
    passes one invocation performs (callers for the ``build_*`` predicate,
    delegate suppliers, context-type builders, callers for the alias probe)
    would otherwise re-walk all ~1500 trees; the trees do not change between
    them, so the walk is done once per chain kind and the passes differ only in
    what they resolve the chains against.
    """

    trees: dict[str, ast.Module]
    bindings_by_module: dict[str, dict[str, str]]
    call_chains_by_module: dict[str, list[list[str]]]
    reference_chains_by_module: dict[str, list[list[str]]]


def _build_repository_index(package_src_roots: Mapping[str, Path]) -> _RepositoryIndex:
    trees: dict[str, ast.Module] = {}
    bindings_by_module: dict[str, dict[str, str]] = {}
    for src_root in package_src_roots.values():
        for path in sorted(src_root.rglob("*.py")):
            module = _module_name_for(path, src_root)
            source = path.read_text(encoding="utf-8-sig")
            tree = ast.parse(source, filename=str(path))
            trees[module] = tree
            bindings_by_module[module] = _import_bindings(tree, module, path.name == "__init__.py")
    return _RepositoryIndex(
        trees=trees,
        bindings_by_module=bindings_by_module,
        call_chains_by_module={},
        reference_chains_by_module={},
    )


def _call_chains(index: _RepositoryIndex, module: str) -> list[list[str]]:
    """*module*'s call-callee chains, walked once and cached."""
    cached = index.call_chains_by_module.get(module)
    if cached is None:
        cached = _call_target_chains(index.trees[module])
        index.call_chains_by_module[module] = cached
    return cached


def _load_reference_chains(index: _RepositoryIndex, module: str) -> list[list[str]]:
    """*module*'s load-context name chains, walked once and cached."""
    cached = index.reference_chains_by_module.get(module)
    if cached is None:
        cached = _reference_chains(index.trees[module])
        index.reference_chains_by_module[module] = cached
    return cached


def _collect_definition_sites(
    index: _RepositoryIndex,
    defining_package: str,
    target_subpackages: tuple[str, ...],
    name_predicate: Callable[[str], bool],
) -> dict[str, str]:
    """qualname -> defining module, for every module-level function directly
    under ``{defining_package}.{one of target_subpackages}`` whose name
    satisfies *name_predicate*."""
    definition_module_of: dict[str, str] = {}
    for module, tree in index.trees.items():
        parts = module.split(".")
        if parts[0] != defining_package or len(parts) < 2 or parts[1] not in target_subpackages:
            continue
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and name_predicate(
                node.name
            ):
                definition_module_of[f"{module}.{node.name}"] = module
    return definition_module_of


def _callers_by_definition(
    index: _RepositoryIndex, definition_module_of: Mapping[str, str]
) -> dict[str, set[str]]:
    """qualname -> the set of OTHER modules containing a Call this scan can
    prove resolves to it."""
    definition_qualnames = frozenset(definition_module_of)
    callers: dict[str, set[str]] = {q: set() for q in definition_qualnames}
    for module in index.trees:
        local_bindings = index.bindings_by_module[module]
        for chain in _call_chains(index, module):
            candidate = _resolve_dotted(chain, local_bindings)
            if candidate is None:
                continue
            resolved = _resolve_to_definition(
                candidate, definition_qualnames, index.bindings_by_module
            )
            if resolved is None or module == definition_module_of[resolved]:
                continue
            callers[resolved].add(module)
    return callers


def _resolve_dotted(chain: list[str], local_bindings: Mapping[str, str]) -> str | None:
    """The dotted name *chain* refers to under *local_bindings*, or ``None``
    when its root is not an imported name (a builtin, a local, a parameter)."""
    root = chain[0]
    if root not in local_bindings:
        return None
    candidate = local_bindings[root]
    if len(chain) > 1:
        candidate = f"{candidate}.{'.'.join(chain[1:])}"
    return candidate


def _significant_body(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.stmt]:
    """*node*'s body with a leading docstring removed."""
    body = list(node.body)
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        return body[1:]
    return body


def _thin_delegation_of(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    local_bindings: Mapping[str, str],
) -> _ThinDelegation | None:
    """Classify *node* as a thin delegating wrapper, or ``None``.

    A thin wrapper is a function whose ENTIRE body (docstring aside) is one
    ``return T(...)``, where ``T`` is an imported name and the construction's
    arguments contain exactly one call to an imported callee. That callee is
    where the whole computation happens; the wrapper only names and wraps it.

    The single-statement requirement is what "thin" means, and it is what keeps
    this from rescuing a genuinely orphaned builder: a builder that walks the
    model, branches, logs, or returns ``None`` on an absent block has more than
    one statement and is never classified here, no matter what types it happens
    to touch.
    """
    body = _significant_body(node)
    if len(body) != 1:
        return None
    stmt = body[0]
    if not isinstance(stmt, ast.Return) or not isinstance(stmt.value, ast.Call):
        return None
    construction = stmt.value
    context_type = _resolve_dotted(_chain_of(construction.func) or [""], local_bindings)
    if context_type is None:
        return None
    delegates: set[str] = set()
    for argument in list(construction.args) + [kw.value for kw in construction.keywords]:
        for inner in ast.walk(argument):
            if not isinstance(inner, ast.Call):
                continue
            chain = _chain_of(inner.func)
            if chain is None:
                continue
            resolved = _resolve_dotted(chain, local_bindings)
            if resolved is not None:
                delegates.add(resolved)
    if len(delegates) != 1:
        return None
    return _ThinDelegation(context_type=context_type, delegate=delegates.pop())


def _chain_of(func: ast.expr) -> list[str] | None:
    """The dotted-name chain *func* spells, or ``None`` if it is not one."""
    if isinstance(func, ast.Name):
        return [func.id]
    if not isinstance(func, ast.Attribute):
        return None
    chain: list[str] = []
    cursor: ast.expr = func
    while isinstance(cursor, ast.Attribute):
        chain.append(cursor.attr)
        cursor = cursor.value
    if not isinstance(cursor, ast.Name):
        return None
    chain.append(cursor.id)
    chain.reverse()
    return chain


def _reference_chains(tree: ast.Module) -> list[list[str]]:
    """Every load-context dotted-name chain in *tree* -- calls included, but
    also a bare reference such as passing a function as an argument.

    A plan function handed to an orchestrator (``TestGeneratorOrchestrator(
    "cache_test", plan_cache_tests, self)``) is never spelled as a Call at the
    binding site, so a call-only scan cannot see production supplying it.
    """
    chains: list[list[str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
            chain = _chain_of(node)
            if chain is not None:
                chains.append(chain)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            chains.append([node.id])
    return chains


def _modules_by_target(
    index: _RepositoryIndex,
    targets: frozenset[str],
    chains_of: Callable[[_RepositoryIndex, str], list[list[str]]],
) -> dict[str, set[str]]:
    """target dotted name -> every module reaching it, in ONE tree pass.

    *chains_of* selects what counts as reaching: :func:`_call_chains` for
    "constructs/calls it", :func:`_load_reference_chains` for "binds it at all"
    (which a function passed as a value needs -- it is never a Call at its
    binding site). Resolving all targets in a single pass keeps this gate at two
    passes over the tree rather than two per candidate; a per-candidate scan is
    quadratic and a slow gate is a skipped gate.
    """
    found: dict[str, set[str]] = {target: set() for target in targets}
    if not targets:
        return found
    for module in index.trees:
        local_bindings = index.bindings_by_module[module]
        for chain in chains_of(index, module):
            candidate = _resolve_dotted(chain, local_bindings)
            if candidate is None:
                continue
            resolved = _resolve_to_definition(candidate, targets, index.bindings_by_module)
            if resolved is not None:
                found[resolved].add(module)
    return found


def _live_delegations(
    index: _RepositoryIndex,
    definition_module_of: Mapping[str, str],
    uncalled: frozenset[str],
    defining_package: str,
) -> dict[str, _ThinDelegation]:
    """The subset of *uncalled* definitions that are live thin delegations.

    A thin wrapper counts as live when BOTH halves of "production builds this
    same value from this same input" hold:

    1. Production SUPPLIES the delegate -- some module outside
       *defining_package* (a consuming language package, or the CLI) binds the
       delegated callee. This is what distinguishes a wrapper over a shared plan
       the languages already use from a wrapper over an internal helper nobody
       reaches.
    2. Production BUILDS the same context type -- some other module in the
       scanned tree constructs it. Wrapping a type nothing else ever constructs
       is an orphan with an extra hop, not a thin wrapper.
    """
    candidates: dict[str, _ThinDelegation] = {}
    for qualname in sorted(uncalled):
        module = definition_module_of[qualname]
        function_name = qualname.rsplit(".", 1)[1]
        node = next(
            (
                candidate
                for candidate in index.trees[module].body
                if isinstance(candidate, (ast.FunctionDef, ast.AsyncFunctionDef))
                and candidate.name == function_name
            ),
            None,
        )
        if node is None:
            continue
        delegation = _thin_delegation_of(node, index.bindings_by_module[module])
        if delegation is not None:
            candidates[qualname] = delegation
    if not candidates:
        return {}

    suppliers = _modules_by_target(
        index,
        frozenset(d.delegate for d in candidates.values()),
        _load_reference_chains,
    )
    builders = _modules_by_target(
        index,
        frozenset(d.context_type for d in candidates.values()),
        _call_chains,
    )
    live: dict[str, _ThinDelegation] = {}
    for qualname, delegation in candidates.items():
        supplied_outside = any(
            module.split(".")[0] != defining_package for module in suppliers[delegation.delegate]
        )
        built_elsewhere = builders[delegation.context_type] - {definition_module_of[qualname]}
        if supplied_outside and built_elsewhere:
            live[qualname] = delegation
    return live


def find_functions_without_production_callers(
    package_src_roots: Mapping[str, Path],
    defining_package: str,
    target_subpackages: tuple[str, ...],
    name_predicate: Callable[[str], bool],
) -> ReachabilityCensus:
    """Scan every ``.py`` file under *package_src_roots* and report, for every
    module-level function directly under
    ``{defining_package}.{subpackage in target_subpackages}`` whose name
    satisfies *name_predicate*, whether any OTHER module in the scanned tree
    contains a call this scan can prove resolves to it.

    Args:
        package_src_roots: Package import name -> its own ``src/`` dir. Every
            ``.py`` file under every one of these is both a candidate definition
            site (if it matches *defining_package* / *target_subpackages* /
            *name_predicate*) and a candidate caller.
        defining_package: The package import name owning the shared modules
            under scan (e.g. ``"datrix_codegen_common"``).
        target_subpackages: Direct subpackage names of *defining_package* to
            scan for definitions (e.g. ``("algorithms", "context_models")``).
        name_predicate: A definition's bare function name must satisfy this to
            be scanned at all.

    Returns:
        A :class:`ReachabilityCensus` naming every matching definition with zero
        resolved external callers AND no live thin delegation, the caller set
        for every one that has at least one caller, and the delegation that
        keeps each surviving thin wrapper live.
    """
    return _census_from_index(
        _build_repository_index(package_src_roots),
        defining_package,
        target_subpackages,
        name_predicate,
    )


def _census_from_index(
    index: _RepositoryIndex,
    defining_package: str,
    target_subpackages: tuple[str, ...],
    name_predicate: Callable[[str], bool],
) -> ReachabilityCensus:
    """The census for one *name_predicate* over an ALREADY-PARSED tree.

    Parsing six packages' whole source trees dominates this gate's runtime, and
    two predicates are asked of the same tree per invocation. Taking the index
    as a parameter is what keeps the gate at one parse rather than one per
    question -- a gate nobody waits for is a gate nobody runs.
    """
    definition_module_of = _collect_definition_sites(
        index, defining_package, target_subpackages, name_predicate
    )
    callers = _callers_by_definition(index, definition_module_of)
    uncalled = frozenset(q for q, mods in callers.items() if not mods)
    delegating = _live_delegations(index, definition_module_of, uncalled, defining_package)
    live_callers = {q: frozenset(mods) for q, mods in callers.items() if mods}
    return ReachabilityCensus(
        dead=uncalled - frozenset(delegating),
        callers=live_callers,
        delegating=delegating,
    )


def is_public_build_function(name: str) -> bool:
    """Whether *name* is one of the public shared builders this gate polices."""
    return name.startswith("build_")


# ---------------------------------------------------------------------------
# Real-tree correctness floors
#
# Over-reporting a correctly-wired builder is as much a gate failure as missing
# a genuinely dead one -- a reachability gate that cries wolf on correct code
# gets disabled, not fixed. Each floor below names a SPECIFIC hoisted function
# whose real wiring exercises one of the three resolution corrections, so it is
# a fact about that function, not a claim about which targets exist. The
# scanned package SET is still derived from the registry (see
# `discover_package_src_roots`); a floor naming a package that is not installed
# is a loud configuration error, never a silent skip.
# ---------------------------------------------------------------------------

#: Builders that are genuinely called in production today: none may be reported
#: dead.
_KNOWN_WIRED: Final[frozenset[str]] = frozenset(
    {
        "datrix_codegen_common.algorithms.extern_client_context.build_api_context",
        "datrix_codegen_common.algorithms.nosql_fields_context.build_fields_context",
        "datrix_codegen_common.algorithms.queue_context.build_queue_context",
        "datrix_codegen_common.algorithms.resilience_context.build_resilience_context",
        "datrix_codegen_common.algorithms.integration_context.build_integration_context",
    }
)

#: Correction 1 probe (cross-package callers). ``build_api_context`` was hoisted
#: INTO datrix-codegen-common, so its only real callers live in the packages it
#: was hoisted FROM. A scan looking only inside the defining package reports it
#: dead; these three prove the resolver finds callers in several packages, not
#: one by accident.
_CROSS_PACKAGE_PROBE: Final[str] = (
    "datrix_codegen_common.algorithms.extern_client_context.build_api_context"
)
_CROSS_PACKAGE_PROBE_CALLERS: Final[frozenset[str]] = frozenset(
    {"datrix_codegen_python", "datrix_codegen_typescript", "datrix_codegen_java"}
)

#: Correction 2 probe (aliased same-named private wrapper). ``extract_max_length``
#: is never called under its own name in any language package: every call site
#: imports it aliased as ``_shared_extract_max_length`` and delegates through a
#: private ``_extract_max_length``. It is not ``build_*``-prefixed, so it sits
#: outside the main gate's own iteration, but it exercises exactly the
#: resolution mechanism that gate depends on.
_ALIAS_PROBE_NAME: Final[str] = "extract_max_length"
_ALIAS_PROBE: Final[str] = "datrix_codegen_common.algorithms.scalar_defaults.extract_max_length"
_ALIAS_PROBE_CALLERS: Final[frozenset[str]] = frozenset(
    {"datrix_codegen_python", "datrix_codegen_dotnet"}
)

#: Correction 3 probe (thin delegation). Every registered test-axis domain's
#: ``build_<kind>_test_context`` lives in this module and has no caller anywhere.
_DELEGATION_PROBE_MODULE_PREFIX: Final[str] = (
    "datrix_codegen_common.algorithms.test_plan_context."
)


def _assert_probe_packages_installed(package_src_roots: Mapping[str, Path]) -> list[str]:
    """Every probe-expected package must be in the scanned set.

    A floor whose expected caller package is absent would otherwise pass
    vacuously (an empty expectation is trivially satisfied by nothing), which is
    the silent-skip shape this gate exists to prevent.

    Returns:
        Problem descriptions; empty means every probe package is scanned.
    """
    expected = _CROSS_PACKAGE_PROBE_CALLERS | _ALIAS_PROBE_CALLERS
    absent = sorted(expected - set(package_src_roots))
    if not absent:
        return []
    return [
        f"correctness-floor probe package(s) {absent} are not in the scanned set "
        f"{sorted(package_src_roots)}, so their floors would pass vacuously. Expected "
        f"every probe package to be installed and registered. Fix: install them, or "
        f"re-point the floor at a function whose wiring the installed set still "
        f"exercises."
    ]


def check_correctness_floors(census: ReachabilityCensus, alias_census: ReachabilityCensus) -> list[str]:
    """Prove the resolver still handles all three false-positive modes against
    the real tree.

    Args:
        census: The ``build_*`` census over the real installed package tree.
        alias_census: The same scan narrowed to :data:`_ALIAS_PROBE_NAME`.

    Returns:
        Problem descriptions; empty means every floor holds.
    """
    problems: list[str] = []

    false_positives = sorted(_KNOWN_WIRED & census.dead)
    if false_positives:
        problems.append(
            f"Genuinely-called build_* function(s) wrongly flagged dead: {false_positives}"
        )

    calling_packages = {
        module.split(".")[0] for module in census.callers.get(_CROSS_PACKAGE_PROBE, frozenset())
    }
    if not _CROSS_PACKAGE_PROBE_CALLERS <= calling_packages:
        problems.append(
            f"Expected {_CROSS_PACKAGE_PROBE.rsplit('.', 1)[1]} to be called from "
            f"{sorted(_CROSS_PACKAGE_PROBE_CALLERS)}; resolver found callers only in "
            f"{sorted(calling_packages)} -- cross-package resolution (correction 1) "
            f"has regressed."
        )

    if _ALIAS_PROBE in alias_census.dead:
        problems.append(
            f"{_ALIAS_PROBE_NAME} has real callers reached only through an aliased "
            f"private wrapper -- the resolver failed to follow the alias "
            f"(correction 2 has regressed)."
        )
    alias_packages = {
        module.split(".")[0] for module in alias_census.callers.get(_ALIAS_PROBE, frozenset())
    }
    if not _ALIAS_PROBE_CALLERS <= alias_packages:
        problems.append(
            f"Expected {_ALIAS_PROBE_NAME} to be called from {sorted(_ALIAS_PROBE_CALLERS)}; "
            f"resolver found callers only in {sorted(alias_packages)} -- alias resolution "
            f"(correction 2) has regressed."
        )

    problems.extend(_check_test_axis_delegations(census))
    return problems


def _check_test_axis_delegations(census: ReachabilityCensus) -> list[str]:
    """Correction 3 floor: every test-axis wrapper is live through its OWN
    ``plan_<kind>_tests`` delegate, and constructs ``TestPlanContext``.

    A rule that folded every wrapper onto one delegate would pass a bare
    "something was rescued" check while proving nothing, so the delegate each
    wrapper resolved through is compared against that wrapper's own kind.
    """
    problems: list[str] = []
    wrappers = {
        qualname: delegation
        for qualname, delegation in census.delegating.items()
        if qualname.startswith(_DELEGATION_PROBE_MODULE_PREFIX)
    }
    if not wrappers:
        return [
            "No test-axis wrapper was recognized as a live thin delegation -- the "
            "delegation rule has gone vacuous."
        ]
    for qualname, delegation in sorted(wrappers.items()):
        kind = qualname.rsplit(".", 1)[1].removeprefix("build_").removesuffix("_context")
        if not delegation.delegate.endswith(f".plan_{kind}s"):
            problems.append(
                f"{qualname} resolved to delegate {delegation.delegate!r}; expected its "
                f"own plan_{kind}s"
            )
        if not delegation.context_type.endswith(".TestPlanContext"):
            problems.append(
                f"{qualname} constructs {delegation.context_type!r}, not TestPlanContext"
            )
    still_dead = sorted(set(wrappers) & census.dead)
    if still_dead:
        problems.append(
            f"Test-axis wrapper(s) recognized as delegating are also reported dead: "
            f"{still_dead}"
        )
    return problems


# ---------------------------------------------------------------------------
# Non-vacuity self-test
# ---------------------------------------------------------------------------


def _write_module(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _check_planted_orphan_is_flagged_and_clears_when_wired(tmp_path: Path) -> list[str]:
    """Direction 1: a synthetic public ``build_*`` with no caller anywhere is
    flagged by name; adding a real cross-module caller clears it. Proves the
    gate can fail at all, and that it stops failing once the defect is fixed."""
    problems: list[str] = []
    defining_root = tmp_path / "defining_pkg" / "src"
    _write_module(defining_root / "fixture_common" / "__init__.py", "")
    _write_module(defining_root / "fixture_common" / "algorithms" / "__init__.py", "")
    _write_module(
        defining_root / "fixture_common" / "algorithms" / "widget.py",
        "def build_widget_context(x):\n    return x\n",
    )
    caller_root = tmp_path / "caller_pkg" / "src"
    _write_module(caller_root / "fixture_lang" / "__init__.py", "")
    _write_module(caller_root / "fixture_lang" / "generator.py", "def run():\n    return None\n")

    roots = {"fixture_common": defining_root, "fixture_lang": caller_root}
    expected_dead = frozenset({"fixture_common.algorithms.widget.build_widget_context"})
    census = find_functions_without_production_callers(
        roots, "fixture_common", ("algorithms",), is_public_build_function
    )
    if census.dead != expected_dead:
        problems.append(
            f"self-test: a planted orphan build_* was not flagged -- expected dead "
            f"{sorted(expected_dead)}, got {sorted(census.dead)}"
        )

    _write_module(
        caller_root / "fixture_lang" / "generator.py",
        "from fixture_common.algorithms.widget import build_widget_context\n\n\n"
        "def run():\n    return build_widget_context(1)\n",
    )
    census_after_wiring = find_functions_without_production_callers(
        roots, "fixture_common", ("algorithms",), is_public_build_function
    )
    if census_after_wiring.dead:
        problems.append(
            f"self-test: wiring the planted orphan into a consuming package did not "
            f"clear it -- still dead: {sorted(census_after_wiring.dead)}"
        )
    return problems


def _check_aliased_private_wrapper_is_resolved(tmp_path: Path) -> list[str]:
    """Direction 2: the caller never spells the shared function's real name
    anywhere -- it imports it under an alias and delegates through a private,
    same-named-as-the-old-local-helper wrapper. A text/regex scan for the real
    name (even a correct, word-boundary-anchored one) finds nothing here,
    because the name never appears at any call site. The AST resolver must still
    find it by following the import alias, proving indirection resolution is
    real rather than a name-matching coincidence."""
    problems: list[str] = []
    defining_root = tmp_path / "defining_pkg2" / "src"
    _write_module(defining_root / "fixture_common2" / "__init__.py", "")
    _write_module(defining_root / "fixture_common2" / "algorithms" / "__init__.py", "")
    _write_module(
        defining_root / "fixture_common2" / "algorithms" / "scalar.py",
        "def build_scalar_default(field):\n    return field\n",
    )
    caller_root = tmp_path / "caller_pkg2" / "src"
    _write_module(caller_root / "fixture_lang2" / "__init__.py", "")
    _write_module(
        caller_root / "fixture_lang2" / "test_factory.py",
        "from fixture_common2.algorithms.scalar import (\n"
        "    build_scalar_default as _shared_build_scalar_default,\n"
        ")\n\n\n"
        "def _build_scalar_default(field):\n"
        "    return _shared_build_scalar_default(field)\n\n\n"
        "def run(field):\n"
        "    return _build_scalar_default(field)\n",
    )

    roots = {"fixture_common2": defining_root, "fixture_lang2": caller_root}
    census = find_functions_without_production_callers(
        roots, "fixture_common2", ("algorithms",), is_public_build_function
    )
    if census.dead:
        problems.append(
            f"self-test: a caller reached only through an aliased private wrapper was "
            f"missed -- reported dead: {sorted(census.dead)}"
        )
    qualname = "fixture_common2.algorithms.scalar.build_scalar_default"
    expected_callers = frozenset({"fixture_lang2.test_factory"})
    if census.callers.get(qualname) != expected_callers:
        problems.append(
            f"self-test: aliased-wrapper caller set mismatch -- expected "
            f"{sorted(expected_callers)}, got {sorted(census.callers.get(qualname, frozenset()))}"
        )
    return problems


def _delegation_fixture_roots(tmp_path: Path, name: str) -> dict[str, Path]:
    """A two-package fixture tree modelling the thin-delegation shape.

    ``plans.plan_widget_tests`` is the shared plan; ``orchestrator`` builds
    ``PlanContext`` from whatever plan it is handed; the language package hands
    it ``plan_widget_tests`` as a VALUE (never calling it by name), exactly as
    every ``TestGeneratorOrchestrator`` construction site does.
    """
    common = f"fx_common_{name}"
    lang = f"fx_lang_{name}"
    defining_root = tmp_path / f"{name}_defining" / "src"
    caller_root = tmp_path / f"{name}_caller" / "src"
    _write_module(defining_root / common / "__init__.py", "")
    _write_module(defining_root / common / "algorithms" / "__init__.py", "")
    _write_module(defining_root / common / "context_models" / "__init__.py", "")
    _write_module(
        defining_root / common / "context_models" / "plan.py",
        "class PlanContext:\n"
        "    def __init__(self, kind, emissions):\n"
        "        self.kind = kind\n"
        "        self.emissions = emissions\n",
    )
    _write_module(
        defining_root / common / "plans.py",
        "def plan_widget_tests(service):\n    return [service]\n",
    )
    _write_module(
        defining_root / common / "orchestrator.py",
        f"from {common}.context_models.plan import PlanContext\n\n\n"
        "class Orchestrator:\n"
        "    def __init__(self, kind, plan):\n"
        "        self._kind = kind\n"
        "        self._plan = plan\n\n"
        "    def generate(self, service):\n"
        "        return PlanContext(kind=self._kind, emissions=tuple(self._plan(service)))\n",
    )
    _write_module(caller_root / lang / "__init__.py", "")
    _write_module(
        caller_root / lang / "generator.py",
        f"from {common}.orchestrator import Orchestrator\n"
        f"from {common}.plans import plan_widget_tests\n\n\n"
        "class WidgetTestGenerator:\n"
        "    def __init__(self):\n"
        '        self._orchestrator = Orchestrator("widget_test", plan_widget_tests)\n',
    )
    return {common: defining_root, lang: caller_root}


def _check_thin_wrapper_over_production_bound_plan_is_live(tmp_path: Path) -> list[str]:
    """Direction 3a: the wrapper has NO caller anywhere and the plan it
    delegates to is never *called* by name in the language package -- it is
    passed as a value. The scan must still recognize the wrapper as live, and
    record which delegate and context type made it so."""
    problems: list[str] = []
    roots = _delegation_fixture_roots(tmp_path, "live")
    common = "fx_common_live"
    _write_module(
        tmp_path / "live_defining" / "src" / common / "algorithms" / "widget_plan.py",
        f"from {common}.context_models.plan import PlanContext\n"
        f"from {common}.plans import plan_widget_tests\n\n\n"
        "def build_widget_test_context(service):\n"
        '    """Thin wrapper -- one construction, one delegated callee."""\n'
        '    return PlanContext(kind="widget_test", emissions=tuple(plan_widget_tests(service)))\n',
    )
    census = find_functions_without_production_callers(
        roots, common, ("algorithms",), is_public_build_function
    )
    qualname = f"{common}.algorithms.widget_plan.build_widget_test_context"
    if census.dead:
        problems.append(
            f"self-test: a thin wrapper over a production-bound plan was reported dead: "
            f"{sorted(census.dead)}"
        )
    expected = _ThinDelegation(
        context_type=f"{common}.context_models.plan.PlanContext",
        delegate=f"{common}.plans.plan_widget_tests",
    )
    if census.delegating.get(qualname) != expected:
        problems.append(
            f"self-test: thin-delegation record mismatch -- expected {expected}, got "
            f"{census.delegating.get(qualname)}"
        )
    return problems


def _check_multi_statement_builder_is_still_flagged(tmp_path: Path) -> list[str]:
    """Direction 3b -- the half that matters most: a builder touching the SAME
    production-bound plan and constructing the SAME production-built context
    type is STILL dead when its body does real work of its own. This is the
    exact shape of every genuinely orphaned builder this gate exists to catch,
    so a delegation rule that rescued it would have quietly disabled the gate."""
    problems: list[str] = []
    roots = _delegation_fixture_roots(tmp_path, "multi")
    common = "fx_common_multi"
    _write_module(
        tmp_path / "multi_defining" / "src" / common / "algorithms" / "widget_plan.py",
        f"from {common}.context_models.plan import PlanContext\n"
        f"from {common}.plans import plan_widget_tests\n\n\n"
        "def build_widget_test_context(service):\n"
        '    """Not thin: branches and computes before constructing."""\n'
        "    if service is None:\n"
        "        return None\n"
        "    emissions = tuple(plan_widget_tests(service))\n"
        '    return PlanContext(kind="widget_test", emissions=emissions)\n',
    )
    census = find_functions_without_production_callers(
        roots, common, ("algorithms",), is_public_build_function
    )
    qualname = f"{common}.algorithms.widget_plan.build_widget_test_context"
    if census.dead != frozenset({qualname}):
        problems.append(
            f"self-test: the delegation rule RESCUED a multi-statement orphaned builder "
            f"-- expected dead {{{qualname}}}, got {sorted(census.dead)}. The gate would "
            f"be disabled."
        )
    if qualname in census.delegating:
        problems.append(
            f"self-test: a multi-statement builder was classified as a thin delegation: "
            f"{census.delegating[qualname]}"
        )
    return problems


def _check_delegation_requires_production_to_supply_the_delegate(tmp_path: Path) -> list[str]:
    """Direction 3c: a thin wrapper is only live when something OUTSIDE the
    defining package binds its delegate. Here the plan function exists and the
    context type is production-built, but no language package ever names the
    plan -- so the wrapper is an orphan with an extra hop, and must be reported
    dead."""
    problems: list[str] = []
    roots = _delegation_fixture_roots(tmp_path, "unsupplied")
    common = "fx_common_unsupplied"
    lang = "fx_lang_unsupplied"
    # Drop the language package's binding of the plan function.
    _write_module(
        tmp_path / "unsupplied_caller" / "src" / lang / "generator.py",
        f"from {common}.orchestrator import Orchestrator\n\n\n"
        "class WidgetTestGenerator:\n"
        "    def __init__(self, plan):\n"
        '        self._orchestrator = Orchestrator("widget_test", plan)\n',
    )
    _write_module(
        tmp_path / "unsupplied_defining" / "src" / common / "algorithms" / "widget_plan.py",
        f"from {common}.context_models.plan import PlanContext\n"
        f"from {common}.plans import plan_widget_tests\n\n\n"
        "def build_widget_test_context(service):\n"
        '    """Thin, but nothing outside the package supplies the delegate."""\n'
        '    return PlanContext(kind="widget_test", emissions=tuple(plan_widget_tests(service)))\n',
    )
    census = find_functions_without_production_callers(
        roots, common, ("algorithms",), is_public_build_function
    )
    qualname = f"{common}.algorithms.widget_plan.build_widget_test_context"
    if census.dead != frozenset({qualname}):
        problems.append(
            f"self-test: a thin wrapper whose delegate nothing outside the defining "
            f"package binds was treated as live -- expected dead {{{qualname}}}, got "
            f"{sorted(census.dead)}"
        )
    if qualname in census.delegating:
        problems.append(
            f"self-test: an unsupplied delegate was recorded as a live delegation: "
            f"{census.delegating[qualname]}"
        )
    return problems


#: Every self-test check, in the order they run. Each receives a private
#: temporary directory root and returns its problems.
_SELF_TEST_CHECKS: Final[tuple[tuple[str, Callable[[Path], list[str]]], ...]] = (
    ("planted orphan is flagged, and clears once wired", _check_planted_orphan_is_flagged_and_clears_when_wired),
    ("aliased private wrapper is still resolved", _check_aliased_private_wrapper_is_resolved),
    ("thin wrapper over a production-bound plan is live", _check_thin_wrapper_over_production_bound_plan_is_live),
    ("multi-statement builder is STILL flagged dead", _check_multi_statement_builder_is_still_flagged),
    ("thin delegation requires production to supply the delegate", _check_delegation_requires_production_to_supply_the_delegate),
)


def run_self_test() -> list[str]:
    """Prove the scanner and the delegation rule are non-vacuous before any real
    census is trusted.

    Returns:
        Problem descriptions; empty means the gate is sound.
    """
    problems: list[str] = []
    tmp_root = Path(tempfile.mkdtemp(prefix="shared-builder-reachability-selftest-"))
    try:
        for index, (label, check) in enumerate(_SELF_TEST_CHECKS):
            check_problems = check(tmp_root / f"check{index}")
            if check_problems:
                problems.extend(f"{label}: {problem}" for problem in check_problems)
            else:
                logger.debug("self_test_check_ok label=%s", label)
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    return problems


# ---------------------------------------------------------------------------
# Gate entry points
# ---------------------------------------------------------------------------


def _censuses(package_src_roots: Mapping[str, Path]) -> tuple[ReachabilityCensus, ReachabilityCensus]:
    """The ``build_*`` census and the alias-probe census over the real tree.

    Both are derived from ONE parse of the scanned packages -- the tree does not
    change between the two questions, and re-parsing it doubles the gate's cost
    for nothing.
    """
    index = _build_repository_index(package_src_roots)
    census = _census_from_index(
        index, DEFINING_PACKAGE, TARGET_SUBPACKAGES, is_public_build_function
    )
    alias_census = _census_from_index(
        index, DEFINING_PACKAGE, TARGET_SUBPACKAGES, lambda name: name == _ALIAS_PROBE_NAME
    )
    return census, alias_census


def check_shared_builder_reachability() -> int:
    """Run the gate against the real installed package tree.

    Returns:
        Exit code: 0 = every shared builder is reachable and every correctness
        floor holds, 1 = a dead builder or a violated floor.
    """
    package_src_roots = discover_package_src_roots()
    logger.info("scanned_packages packages=%s", sorted(package_src_roots))
    floor_problems = _assert_probe_packages_installed(package_src_roots)
    census, alias_census = _censuses(package_src_roots)
    floor_problems.extend(check_correctness_floors(census, alias_census))

    ok = True
    if census.dead:
        ok = False
        logger.error(
            "SHARED-BUILDER REACHABILITY: public build_* function(s) in %s's %s modules "
            "have zero production callers across %s: %s. Either wire each into its "
            "consuming language package(s) / orchestrator, or delete it if it is "
            "genuinely unused.",
            DEFINING_PACKAGE,
            "/".join(TARGET_SUBPACKAGES),
            sorted(package_src_roots),
            sorted(census.dead),
        )
    for problem in floor_problems:
        ok = False
        logger.error("CORRECTNESS FLOOR: %s", problem)

    if not ok:
        return EXIT_FAIL
    logger.info(
        "SHARED-BUILDER REACHABILITY GATE PASSED: %d build_* definition(s), %d with "
        "resolved callers, %d live by thin delegation, 0 dead.",
        len(census.callers) + len(census.delegating) + len(census.dead),
        len(census.callers),
        len(census.delegating),
    )
    return EXIT_OK


def print_census() -> int:
    """Report the reachability census without rendering a verdict.

    Returns:
        Exit code: 0 always -- this is a measurement. The gate's own verdict on
        the same data is :func:`check_shared_builder_reachability`.
    """
    package_src_roots = discover_package_src_roots()
    census, _alias_census = _censuses(package_src_roots)
    for qualname, callers in sorted(census.callers.items()):
        logger.info(
            "reachable qualname=%s callers=%s",
            qualname,
            sorted({module.split(".")[0] for module in callers}),
        )
    for qualname, delegation in sorted(census.delegating.items()):
        logger.info(
            "live_by_delegation qualname=%s delegate=%s context_type=%s",
            qualname,
            delegation.delegate,
            delegation.context_type,
        )
    for qualname in sorted(census.dead):
        logger.info("dead qualname=%s", qualname)
    logger.info(
        "reachability_census packages=%d reachable=%d delegating=%d dead=%d",
        len(package_src_roots),
        len(census.callers),
        len(census.delegating),
        len(census.dead),
    )
    return EXIT_OK


def _parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Shared-builder reachability gate: every public build_* function in "
            "datrix_codegen_common's algorithms/ and context_models/ modules must have "
            "a production caller across the defining package, every registered language "
            "package, and datrix-cli. Hard zero -- no baseline, no exemption file."
        ),
    )
    parser.add_argument("--debug", action="store_true", help="Enable DEBUG logging")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run only the non-vacuity self-test and skip the real census",
    )
    parser.add_argument(
        "--census",
        action="store_true",
        help="Print the reachability census (a measurement, not a verdict) and exit 0",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point.

    Returns:
        Process exit code: 0 = gate passed (or a successful ``--self-test`` /
        ``--census``), 1 = a dead shared builder or a violated correctness
        floor, 2 = self-test failure or an unresolvable package set.
    """
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    problems = run_self_test()
    if problems:
        logger.error("NON-VACUITY SELF-TEST FAILED -- aborting before any real census:")
        for problem in problems:
            logger.error("  %s", problem)
        return EXIT_USAGE
    logger.info("non-vacuity self-test: PASS (%d checks)", len(_SELF_TEST_CHECKS))

    if args.self_test:
        return EXIT_OK

    try:
        if args.census:
            return print_census()
        return check_shared_builder_reachability()
    except ScanConfigurationError as exc:
        logger.error("ERROR: %s", exc)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
