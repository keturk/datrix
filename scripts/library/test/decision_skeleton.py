#!/usr/bin/env python3
"""Decision-skeleton extraction: reduces a function's AST to the ordered
sequence of decisions it makes over its parameters -- branches, loops, match
arms, returns, raises, asserts, loop exits, and any assignment or expression
statement that reads model data -- with every rendering choice (string
literals, f-strings, identifier names, docstrings, annotations, decorators)
collapsed away. Two functions that ask the same questions of the same data in
the same order produce an equal skeleton no matter how differently they are
written; two functions that ask different questions never do.

Also recognizes the one AST shape a decision-parity role never needs to
reconcile: a "pre-binding adapter" whose entire body is a single return of a
call into the shared codegen layer, passing its own parameters straight
through (plus, at most, this package's own constants, state and casing
callables).

Rendering rules
---------------
One skeleton line per decision, in source order:

    if <pred> / else / endif          for <iter> / else / endfor
    while <pred> / else / endwhile    match <subject> / case <pattern> [if <guard>] / endmatch
    return <expr>                     raise
    assert <pred>                     break / continue
    = <expr>        (an assignment whose value reads model data and is not a rename)
    <expr>          (a bare expression statement that reads model data;
                     a yield always)

A *model chain* is an attribute chain rooted at a parameter (rendered
``P.<attr>...`` -- the parameter's own name is discarded, only the fact that
it IS a parameter survives), at ``self`` (rendered ``self.<attr>...``), or at
a *derived root* (below). ``self``/``cls`` are never ``P``. Expressions render as:

    model chain            -> its chain text
    Call                   -> <callee chain or 'call'>(<operands>)
    Compare/BoolOp/UnaryOp -> operands joined by operator names (eq, and, not, ...)
    comprehension          -> comp(for <iter> if <cond> ...)   (never the element)
    Dict/List/Tuple/Set    -> {…} / […] / (…) of <operands>
    Subscript              -> <operand>[<operand>]
    NamedExpr/Await/Starred-> their inner value
    Yield/YieldFrom        -> yield <expr>
    str Constant -> S      JoinedStr (f-string) -> F      other Constant -> its literal
    IfExp                  -> ifexp(<test>)
    everything else        -> _

where an *operand* renders itself when it contains a model chain anywhere
and collapses to ``_`` otherwise (so a nested call over model data is kept,
a nested call over nothing model-rooted is one ``_``). Keyword arguments are
ordered by keyword name so argument order never leaks into the skeleton.
Docstrings, annotations, decorators and local identifier names never appear.

Derived roots
-------------
A local name bound exactly once from a model-rooted expression is a *derived
root* and renders as its binding chain, so a decision over a collection
element survives: ``for f in entity.fields: if f.required`` renders
``for P.fields / if P.fields[*].required / endif / endfor``. Bindings that
derive: a ``for``/``async for`` target (the element is spelled
``<iterable>[*]``), a comprehension target (same spelling, scoped to the
comprehension), a plain or annotated assignment to a name, a walrus,
``with <expr> as name``, and ``case`` pattern captures over a model-rooted
subject. Unpacking spells positions: ``for name, entity in
block.entities.items()`` binds ``name -> P.entities.items()[*][0]`` and
``entity -> P.entities.items()[*][1]``; a starred target spells ``[i:]``; a
class-pattern keyword capture spells ``.<attr>``, a mapping capture
``[<key>]`` and a mapping ``**rest`` ``[**]``. Derived roots compose (a root
bound from another root resolves through it) and are computed
flow-insensitively to a fixed point, so binding order never matters.

The conservative floor: a name bound more than once, bound anywhere from a
non-model expression (an import, an ``except ... as``, a nested ``def`` or
``class``, an augmented assignment, a ``global``/``nonlocal`` declaration),
or sharing a parameter's name stays a plain local and renders ``_``. An
assignment whose every bound name is a derived root that is read somewhere
in the function is a rename and contributes no line of its own -- its read
is carried by every use; an assignment nobody reads keeps its ``= <expr>``
line.

Fail-closed rule
----------------
A file that cannot be parsed, a function snippet that cannot be re-parsed,
and a statement or pattern kind this module does not know how to classify
each raise ``SkeletonError`` naming the offending file/function -- never a
silent skip and never a default skeleton. Expressions, by contrast, never
raise: an unrecognized expression shape is *classifiable* (it is not a
decision) and collapses to ``_``.

This module is a pure, dependency-free library: it never touches the plugin
registry, never loads a language package, and is exercised end to end by its
own ``--self-test``. The role-grouping scanner that consumes it is built
separately and hands it ``FunctionSource`` instances.

Usage:
    python decision_skeleton.py --self-test
"""

from __future__ import annotations

import argparse
import ast
import logging
import shutil
import sys
import tempfile
import textwrap
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Final

logger = logging.getLogger(__name__)

EXIT_OK: Final[int] = 0
#: Also argparse's own usage-error exit code; the CLI exposes nothing but
#: ``--self-test``, so both failure modes mean "nothing was proven".
EXIT_SELF_TEST_FAILED: Final[int] = 2

_FunctionDefNode = ast.FunctionDef | ast.AsyncFunctionDef
_ComprehensionNode = ast.ListComp | ast.SetComp | ast.GeneratorExp | ast.DictComp

#: A pre-binding adapter's callee must resolve, through the function's own
#: import table, to a symbol whose fully-qualified name starts with this
#: prefix: the shared codegen layer every language generator delegates to.
_SHARED_LAYER_MODULE_PREFIX: Final[str] = "datrix_codegen_common."

#: Skeleton tokens. ``P`` is the placeholder for ANY parameter (the actual
#: name never appears); ``self`` renders literally so the package's own state
#: stays distinguishable from model data flowing in.
_PARAM_TOKEN: Final[str] = "P"
_SELF_TOKEN: Final[str] = "self"
_SELF_NAME: Final[str] = "self"
_CLS_NAME: Final[str] = "cls"
_STRING_TOKEN: Final[str] = "S"
_FSTRING_TOKEN: Final[str] = "F"
_ANONYMOUS_CALLEE: Final[str] = "call"
_COLLAPSED: Final[str] = "_"
_WILDCARD_IMPORT: Final[str] = "*"
#: Spelling of "one element of" a model-rooted iterable, appended to the
#: iterable's chain for a loop or comprehension target.
_ELEMENT_SUFFIX: Final[str] = "[*]"
#: Spelling of a mapping pattern's ``**rest`` capture.
_MAPPING_REST_SUFFIX: Final[str] = "[**]"

_COMPARE_OP_NAMES: Final[dict[type[ast.cmpop], str]] = {
    ast.Eq: "eq",
    ast.NotEq: "ne",
    ast.Lt: "lt",
    ast.LtE: "le",
    ast.Gt: "gt",
    ast.GtE: "ge",
    ast.Is: "is",
    ast.IsNot: "is_not",
    ast.In: "in",
    ast.NotIn: "not_in",
}
_BOOL_OP_NAMES: Final[dict[type[ast.boolop], str]] = {ast.And: "and", ast.Or: "or"}
_UNARY_OP_NAMES: Final[dict[type[ast.unaryop], str]] = {
    ast.Not: "not",
    ast.USub: "neg",
    ast.UAdd: "pos",
    ast.Invert: "invert",
}

#: Statement kinds that carry no decision and no nested statement list. The
#: ``type X = ...`` alias statement only exists from Python 3.12 on; the
#: repository's floor is 3.11, so it joins the set exactly when the running
#: interpreter can parse one.
_TYPE_ALIAS_STATEMENT_KINDS: Final[tuple[type[ast.stmt], ...]] = (ast.TypeAlias,) if sys.version_info >= (3, 12) else ()
_NO_DECISION_STATEMENT_KINDS: Final[tuple[type[ast.stmt], ...]] = (
    ast.Pass,
    ast.Import,
    ast.ImportFrom,
    ast.Global,
    ast.Nonlocal,
    ast.Delete,
    *_TYPE_ALIAS_STATEMENT_KINDS,
)

_EMPTY_ROOTS: Final[Mapping[str, str]] = MappingProxyType({})


class SkeletonError(Exception):
    """A file, function, statement or pattern could not be parsed or
    classified for skeleton extraction. Never caught and silenced: every
    unparseable or unclassifiable member is reported by name, never skipped."""


@dataclass(frozen=True)
class FunctionSource:
    """One collected function/method, ready for skeleton extraction and role
    grouping. The role-grouping scanner builds these from real packages; this
    module only consumes the shape (its own self-test builds instances from
    synthetic source, never from a real package)."""

    package: str
    file_path: Path
    line_number: int
    qualified_name: str
    node: _FunctionDefNode
    source_text: str
    import_table: dict[str, str]  # local name -> fully-qualified "module.attr"


def parse_module_or_raise(file_path: Path) -> ast.Module:
    """Parse *file_path*, failing closed rather than skipping it.

    Args:
        file_path: The ``.py`` file to parse.

    Returns:
        The parsed ``ast.Module``.

    Raises:
        SkeletonError: If the file cannot be read or parsed, naming the file.
    """
    try:
        source = file_path.read_text(encoding="utf-8-sig")
        return ast.parse(source, filename=str(file_path))
    except (SyntaxError, OSError) as exc:
        raise SkeletonError(
            f"Cannot extract decision skeletons from {file_path}: {exc}. A role "
            f"with an unparseable member is a gate failure naming the file, never "
            f"a silent skip. Fix: make the file parse under the running interpreter "
            f"or remove it from the scanned package."
        ) from exc


# ---------------------------------------------------------------------------
# Import-table resolution
# ---------------------------------------------------------------------------


def build_import_table(module: ast.Module, package: str) -> dict[str, str]:
    """Resolve every import in *module* to ``{local name: fully-qualified
    "module.attr"}``, including imports nested under ``if TYPE_CHECKING:`` or
    inside a function body (``ast.walk`` descends into every statement list,
    so no special case is needed).

    Args:
        module: The parsed module AST.
        package: The dotted package *module* lives in -- for
            ``pkg/sub/mod.py`` and for ``pkg/sub/__init__.py`` alike this is
            ``"pkg.sub"`` (a package's ``__init__`` IS its package). Needed to
            resolve a relative ``from . import x`` / ``from ..sub import x``.

    Returns:
        ``{local name: fully-qualified name}`` for every ``import``/``from``
        binding anywhere in the module.

    Implementation notes:
        A bare ``import x.y`` (no ``as``) binds only the top-level name ``x``
        in the namespace, so it maps ``x -> "x"``; a later ``x.y.foo(...)``
        resolves through that root by attribute access. ``from X import *``
        binds no resolvable name and is dropped -- a callee that can only be
        reached through a wildcard import therefore never resolves to the
        shared layer, which is the fail-closed direction for an exemption.
    """
    table: dict[str, str] = {}
    for node in ast.walk(module):
        if isinstance(node, ast.Import):
            table.update(_import_bindings(node))
        elif isinstance(node, ast.ImportFrom):
            table.update(_import_from_bindings(node, package))
    return table


def _import_bindings(node: ast.Import) -> dict[str, str]:
    """``import a.b.c as w`` binds ``w -> "a.b.c"``; unaliased ``import a.b.c``
    binds only the root ``a -> "a"``."""
    bindings: dict[str, str] = {}
    for alias in node.names:
        root = alias.name.split(".")[0]
        bindings[alias.asname or root] = alias.name if alias.asname else root
    return bindings


def _import_from_bindings(node: ast.ImportFrom, package: str) -> dict[str, str]:
    """``from X import Y [as Z]`` binds ``Z`` (or ``Y``) ``-> "X.Y"``, with a
    relative ``X`` resolved against *package*; ``from X import *`` binds nothing."""
    base = _resolve_relative_module(node.module, node.level, package)
    bindings: dict[str, str] = {}
    for alias in node.names:
        if alias.name == _WILDCARD_IMPORT:
            continue
        bindings[alias.asname or alias.name] = f"{base}.{alias.name}" if base else alias.name
    return bindings


def _resolve_relative_module(module: str | None, level: int, package: str) -> str:
    """Resolve a ``from``-import's dotted module against *package* for a
    relative import (``level > 0``); return *module* unchanged for an
    absolute one (``level == 0``).

    Args:
        module: The ``ImportFrom.module`` value (``None`` for ``from . import x``).
        level: The ``ImportFrom.level`` value (0 = absolute).
        package: The dotted package the importing module lives in.

    Returns:
        The absolute dotted module path (empty for an absolute ``from``
        with no module, which the grammar does not produce).
    """
    if level == 0:
        return module or ""
    parts = package.split(".")
    ascend = level - 1
    base_parts = parts[: len(parts) - ascend] if ascend else parts
    base = ".".join(base_parts)
    return f"{base}.{module}" if module else base


# ---------------------------------------------------------------------------
# Scope: parameters, derived roots, and what a name means
# ---------------------------------------------------------------------------


def _function_parameter_names(node: _FunctionDefNode) -> frozenset[str]:
    """Every parameter name eligible to render as the placeholder ``P``:
    positional-only, positional, keyword-only, ``*args``, ``**kwargs``.
    ``self``/``cls`` are excluded -- ``self`` renders as the literal ``self``
    and ``cls`` is never a model root.

    Args:
        node: The function/method AST node.

    Returns:
        The frozenset of ``P``-eligible parameter names.
    """
    args = node.args
    names = {a.arg for a in (*args.posonlyargs, *args.args, *args.kwonlyargs)}
    if args.vararg is not None:
        names.add(args.vararg.arg)
    if args.kwarg is not None:
        names.add(args.kwarg.arg)
    return frozenset(names - {_SELF_NAME, _CLS_NAME})


@dataclass(frozen=True)
class _Binding:
    """One site where a scope binds *name*. ``source`` is the expression the
    name is bound from, with ``path`` the spelling appended to that
    expression's rendering (``[*]`` for a loop element, ``[1]`` for an
    unpacked position, ``.attr`` for a class-pattern keyword capture);
    ``source`` is ``None`` for a binding that is never model data -- an
    import, an ``except ... as``, a nested ``def``/``class``, an augmented
    assignment, a ``global``/``nonlocal`` declaration -- which exists only to
    be counted."""

    name: str
    source: ast.expr | None
    path: str


@dataclass(frozen=True)
class RenderScope:
    """What every name means inside one scope: the ``P``-eligible parameter
    names, the derived-root table (``{local name: binding chain}``), and the
    set of names the scope reads anywhere (used to tell a rename from an
    unread assignment). Built once per function, layered for a nested
    ``def`` (its parameters join ``P``, its own bindings shadow the outer
    table) and for a comprehension (its targets shadow the outer table for
    the comprehension's own clauses)."""

    param_names: frozenset[str]
    derived_roots: Mapping[str, str]
    loaded_names: frozenset[str]

    @classmethod
    def for_function(cls, node: _FunctionDefNode) -> RenderScope:
        """The top-level scope of *node*."""
        return cls._build(
            _function_parameter_names(node), _EMPTY_ROOTS, _collect_bindings(node.body), _loaded_names(node)
        )

    def nested(self, node: _FunctionDefNode) -> RenderScope:
        """The scope of a ``def`` nested inside this scope: outer parameters
        and derived roots stay visible (a closure reads them) unless the
        nested function binds the same name."""
        param_names = self.param_names | _function_parameter_names(node)
        return self._build(param_names, self.derived_roots, _collect_bindings(node.body), _loaded_names(node))

    def for_comprehension(self, node: _ComprehensionNode) -> RenderScope:
        """The scope of one comprehension: its targets, bound from their
        iterables, layered over this scope."""
        bindings = [
            binding
            for generator in node.generators
            for binding in _target_bindings(generator.target, generator.iter, _ELEMENT_SUFFIX)
        ]
        return self._build(self.param_names, self.derived_roots, bindings, self.loaded_names)

    @classmethod
    def _build(
        cls,
        param_names: frozenset[str],
        inherited: Mapping[str, str],
        bindings: list[_Binding],
        loaded_names: frozenset[str],
    ) -> RenderScope:
        roots = _resolve_derived_roots(param_names, inherited, bindings)
        return cls(param_names=param_names, derived_roots=MappingProxyType(roots), loaded_names=loaded_names)


def _resolve_derived_roots(
    param_names: frozenset[str],
    inherited: Mapping[str, str],
    bindings: list[_Binding],
) -> dict[str, str]:
    """Resolve the derived-root table for one scope to a fixed point.

    A name is a candidate when the scope binds it exactly once, from a real
    expression, and it is not a parameter (parameters are already roots and
    are never shadowed). Each pass resolves every candidate whose source
    contains a model chain under the table so far and renders to something
    other than ``_``; the loop ends when a pass resolves nothing. Because
    every candidate is bound once and resolution only ever adds entries,
    the loop terminates and no chain can reference itself.
    """
    counts = Counter(binding.name for binding in bindings)
    never_derived = param_names | {_SELF_NAME, _CLS_NAME}
    roots = {name: chain for name, chain in inherited.items() if name not in counts and name not in never_derived}
    candidates = {
        binding.name: binding
        for binding in bindings
        if counts[binding.name] == 1 and binding.name not in never_derived and binding.source is not None
    }
    while candidates:
        resolved = _resolve_pass(candidates, RenderScope(param_names, MappingProxyType(roots), frozenset()))
        if not resolved:
            break
        roots.update(resolved)
        candidates = {name: binding for name, binding in candidates.items() if name not in resolved}
    return roots


def _resolve_pass(candidates: Mapping[str, _Binding], scope: RenderScope) -> dict[str, str]:
    resolved: dict[str, str] = {}
    for name, binding in candidates.items():
        if binding.source is None or not _contains_model_chain(binding.source, scope):
            continue
        rendered = render_expr(binding.source, scope)
        if rendered != _COLLAPSED:
            resolved[name] = f"{rendered}{binding.path}"
    return resolved


def _loaded_names(node: _FunctionDefNode) -> frozenset[str]:
    """Every name read anywhere under *node*, nested scopes included (a
    closure reading an outer local is a read of it)."""
    return frozenset(sub.id for sub in ast.walk(node) if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load))


def _collect_bindings(body: list[ast.stmt]) -> list[_Binding]:
    """Every binding site in one scope's statement list, descending into
    ``if``/loop/``with``/``try``/``match`` blocks but never into a nested
    ``def`` or ``class`` (those are their own scopes; only their names bind
    here). Walrus targets bind in the enclosing function scope wherever they
    appear, comprehension conditions included."""
    bindings: list[_Binding] = []
    for stmt in body:
        bindings.extend(_own_bindings(stmt))
        bindings.extend(_walrus_bindings(stmt))
        for nested in _nested_blocks(stmt):
            bindings.extend(_collect_bindings(nested))
    return bindings


def _own_bindings(stmt: ast.stmt) -> list[_Binding]:
    """The bindings one statement performs itself (not those of its nested
    blocks): the kinds that bind a name FROM an expression here, every other
    binding kind (counted only) in ``_counted_only_bindings``."""
    match stmt:
        case ast.Assign(targets=targets, value=value):
            return [binding for target in targets for binding in _target_bindings(target, value, "")]
        case ast.AnnAssign(target=target, value=ast.expr() as value):
            return _target_bindings(target, value, "")
        case ast.For(target=target, iter=iterable) | ast.AsyncFor(target=target, iter=iterable):
            return _target_bindings(target, iterable, _ELEMENT_SUFFIX)
        case ast.With(items=items) | ast.AsyncWith(items=items):
            return [
                binding
                for item in items
                if item.optional_vars is not None
                for binding in _target_bindings(item.optional_vars, item.context_expr, "")
            ]
        case ast.Match(subject=subject, cases=cases):
            return [binding for case in cases for binding in _pattern_bindings(case.pattern, subject, "")]
        case _:
            return _counted_only_bindings(stmt)


def _counted_only_bindings(stmt: ast.stmt) -> list[_Binding]:
    """Bindings that are never model data and exist only to be counted, so
    the name they bind can never become a derived root: an augmented
    assignment, an ``except ... as``, a nested ``def``/``class`` name, an
    import, a ``global``/``nonlocal`` declaration, a ``type`` alias."""
    match stmt:
        case ast.AugAssign(target=ast.Name(id=name)):
            return [_Binding(name, None, "")]
        case ast.Try(handlers=handlers) | ast.TryStar(handlers=handlers):
            return [_Binding(handler.name, None, "") for handler in handlers if handler.name is not None]
        case ast.FunctionDef(name=name) | ast.AsyncFunctionDef(name=name) | ast.ClassDef(name=name):
            return [_Binding(name, None, "")]
        case ast.Import(names=aliases) | ast.ImportFrom(names=aliases):
            return [
                _Binding(alias.asname or alias.name.split(".")[0], None, "")
                for alias in aliases
                if alias.name != _WILDCARD_IMPORT
            ]
        case ast.Global(names=names) | ast.Nonlocal(names=names):
            return [_Binding(name, None, "") for name in names]
        case _:
            if isinstance(stmt, _TYPE_ALIAS_STATEMENT_KINDS):
                return [_Binding(stmt.name.id, None, "")]
            return []


def _walrus_bindings(stmt: ast.stmt) -> list[_Binding]:
    return [
        _Binding(named.target.id, named.value, "")
        for expression in _direct_expressions(stmt)
        for named in ast.walk(expression)
        if isinstance(named, ast.NamedExpr)
    ]


def _direct_expressions(stmt: ast.stmt) -> list[ast.expr]:
    """The expressions one statement holds directly (its test, value,
    targets, iterable, context managers, handler types, case guards) --
    never the statements of its nested blocks."""
    expressions: list[ast.expr] = []
    for child in ast.iter_child_nodes(stmt):
        match child:
            case ast.expr():
                expressions.append(child)
            case ast.withitem(context_expr=context_expr, optional_vars=optional_vars):
                expressions.append(context_expr)
                if optional_vars is not None:
                    expressions.append(optional_vars)
            case ast.ExceptHandler(type=ast.expr() as handler_type):
                expressions.append(handler_type)
            case ast.match_case(guard=ast.expr() as guard):
                expressions.append(guard)
    return expressions


def _nested_blocks(stmt: ast.stmt) -> list[list[ast.stmt]]:
    """The statement lists nested in *stmt* that belong to the SAME scope."""
    match stmt:
        case (
            ast.If(body=body, orelse=orelse)
            | ast.For(body=body, orelse=orelse)
            | ast.AsyncFor(body=body, orelse=orelse)
            | ast.While(body=body, orelse=orelse)
        ):
            return [body, orelse]
        case ast.With(body=body) | ast.AsyncWith(body=body):
            return [body]
        case (
            ast.Try(body=body, handlers=handlers, orelse=orelse, finalbody=finalbody)
            | ast.TryStar(body=body, handlers=handlers, orelse=orelse, finalbody=finalbody)
        ):
            return [body, *(handler.body for handler in handlers), orelse, finalbody]
        case ast.Match(cases=cases):
            return [case.body for case in cases]
        case _:
            return []


def _target_bindings(target: ast.expr, source: ast.expr, path: str) -> list[_Binding]:
    """The names an assignment/loop/with target binds from *source*, each
    with the position spelling that reaches it. An attribute or subscript
    target stores into an existing object and binds no name."""
    match target:
        case ast.Name(id=name):
            return [_Binding(name, source, path)]
        case ast.Tuple(elts=elts) | ast.List(elts=elts):
            return _unpacked_bindings(elts, source, path)
        case _:
            return []


def _unpacked_bindings(elts: list[ast.expr], source: ast.expr, path: str) -> list[_Binding]:
    bindings: list[_Binding] = []
    for index, elt in enumerate(elts):
        if isinstance(elt, ast.Starred):
            bindings.extend(_target_bindings(elt.value, source, f"{path}[{index}:]"))
        else:
            bindings.extend(_target_bindings(elt, source, f"{path}[{index}]"))
    return bindings


def _pattern_bindings(pattern: ast.pattern, subject: ast.expr, path: str) -> list[_Binding]:
    """The names a ``case`` pattern captures from *subject*, each with the
    spelling of the piece it captures. Alternatives of an or-pattern must
    bind the same names; a name captured at the same position in every
    alternative counts once, one captured at differing positions is bound
    twice and drops to the conservative floor."""
    match pattern:
        case ast.MatchAs(name=None):
            return []
        case ast.MatchAs(name=str() as name, pattern=None):
            return [_Binding(name, subject, path)]
        case ast.MatchAs(name=str() as name, pattern=ast.pattern() as inner):
            return [_Binding(name, subject, path), *_pattern_bindings(inner, subject, path)]
        case ast.MatchSequence(patterns=patterns):
            return _sequence_pattern_bindings(patterns, subject, path)
        case ast.MatchMapping():
            return _mapping_pattern_bindings(pattern, subject, path)
        case ast.MatchClass():
            return _class_pattern_bindings(pattern, subject, path)
        case ast.MatchOr(patterns=alternatives):
            seen: dict[tuple[str, str], _Binding] = {}
            for alternative in alternatives:
                for binding in _pattern_bindings(alternative, subject, path):
                    seen.setdefault((binding.name, binding.path), binding)
            return list(seen.values())
        case _:
            return []


def _mapping_pattern_bindings(pattern: ast.MatchMapping, subject: ast.expr, path: str) -> list[_Binding]:
    """``case {"key": value, **rest}``: each value captures ``<subject>[<key>]``,
    the rest capture ``<subject>[**]``."""
    bindings = [
        binding
        for key, item in zip(pattern.keys, pattern.patterns, strict=True)
        for binding in _pattern_bindings(item, subject, f"{path}[{_mapping_key_text(key)}]")
    ]
    if pattern.rest is not None:
        bindings.append(_Binding(pattern.rest, subject, f"{path}{_MAPPING_REST_SUFFIX}"))
    return bindings


def _class_pattern_bindings(pattern: ast.MatchClass, subject: ast.expr, path: str) -> list[_Binding]:
    """``case Kind(first, name=n)``: a positional sub-pattern captures
    ``<subject>[i]``, a keyword sub-pattern captures ``<subject>.<attr>``."""
    positional = [
        binding
        for index, item in enumerate(pattern.patterns)
        for binding in _pattern_bindings(item, subject, f"{path}[{index}]")
    ]
    keyword = [
        binding
        for attr, item in zip(pattern.kwd_attrs, pattern.kwd_patterns, strict=True)
        for binding in _pattern_bindings(item, subject, f"{path}.{attr}")
    ]
    return [*positional, *keyword]


def _sequence_pattern_bindings(patterns: list[ast.pattern], subject: ast.expr, path: str) -> list[_Binding]:
    bindings: list[_Binding] = []
    for index, item in enumerate(patterns):
        if isinstance(item, ast.MatchStar):
            if item.name is not None:
                bindings.append(_Binding(item.name, subject, f"{path}[{index}:]"))
            continue
        bindings.extend(_pattern_bindings(item, subject, f"{path}[{index}]"))
    return bindings


def _mapping_key_text(key: ast.expr) -> str:
    """A mapping pattern's key, spelled like any constant in the skeleton."""
    if not isinstance(key, ast.Constant):
        return _COLLAPSED
    return _STRING_TOKEN if isinstance(key.value, str) else repr(key.value)


def _model_chain_root(node: ast.expr, scope: RenderScope) -> str | None:
    """If *node* is an attribute chain rooted at a parameter, at ``self``, or
    at a derived root, return its rendered chain text (``P.<attr>...``,
    ``self.<attr>...``, or ``<binding chain>.<attr>...`` -- the root's ACTUAL
    name is discarded); otherwise return ``None``.

    This is a shape probe, not an error path: ``None`` means "not a model
    chain", and every caller decides what a non-chain renders as.

    Args:
        node: The expression to test.
        scope: The enclosing scope.

    Returns:
        The rendered chain text, or ``None`` if *node* is not a model chain.
    """
    parts: list[str] = []
    cursor: ast.expr = node
    while isinstance(cursor, ast.Attribute):
        parts.append(cursor.attr)
        cursor = cursor.value
    if not isinstance(cursor, ast.Name):
        return None
    if cursor.id == _SELF_NAME:
        root = _SELF_TOKEN
    elif cursor.id in scope.param_names:
        root = _PARAM_TOKEN
    elif cursor.id in scope.derived_roots:
        root = scope.derived_roots[cursor.id]
    else:
        return None
    return ".".join([root, *reversed(parts)])


def _contains_model_chain(node: ast.expr, scope: RenderScope) -> bool:
    """Whether *node* contains a model chain anywhere in its expression tree
    -- the test deciding whether an operand renders itself or collapses to
    ``_``, and whether an assignment/expression statement is a decision."""
    return any(isinstance(sub, ast.expr) and _model_chain_root(sub, scope) is not None for sub in ast.walk(node))


# ---------------------------------------------------------------------------
# Expression rendering
# ---------------------------------------------------------------------------


def render_expr(node: ast.expr, scope: RenderScope) -> str:
    """Render one expression to its decision-skeleton text (dispatch table in
    the module docstring). Never renders an identifier name, annotation,
    decorator or docstring, and never raises: an expression shape with no
    row in the table is classifiable -- it is not a decision -- and
    collapses to ``_``.

    The model-chain probe runs FIRST, before any node-kind dispatch, so a
    bare ``command.name`` renders as ``P.name`` instead of falling through the
    generic-``Attribute`` catch-all.

    Args:
        node: The expression to render.
        scope: The enclosing scope (``RenderScope.for_function`` for a
            whole function).

    Returns:
        The rendered skeleton text for this expression.
    """
    chain = _model_chain_root(node, scope)
    if chain is not None:
        return chain
    match node:
        case ast.Call():
            return _render_call(node, scope)
        case ast.Compare():
            return _render_compare(node, scope)
        case ast.BoolOp(op=op, values=values):
            return f" {_BOOL_OP_NAMES[type(op)]} ".join(render_expr(value, scope) for value in values)
        case ast.UnaryOp(op=op, operand=operand):
            return f"{_UNARY_OP_NAMES[type(op)]}({render_expr(operand, scope)})"
        case ast.ListComp() | ast.SetComp() | ast.GeneratorExp() | ast.DictComp():
            return _render_comprehension(node, scope)
        case ast.Constant(value=str()):
            return _STRING_TOKEN
        case ast.Constant(value=value):
            return repr(value)
        case ast.JoinedStr():
            return _FSTRING_TOKEN
        case ast.IfExp(test=test):
            return f"ifexp({render_expr(test, scope)})"
        case _:
            return _render_structural(node, scope)


def _render_structural(node: ast.expr, scope: RenderScope) -> str:
    """The structural expression kinds: containers and subscripts render their
    model-rooted operands (a returned tuple/dict of model reads IS the shape
    of what a function produces), thin wrappers render their inner value, a
    yield renders like a return. Everything else -- arithmetic and string
    concatenation, lambdas, non-model names and attributes, slices,
    t-strings -- is rendering and collapses to ``_``."""
    match node:
        case ast.Dict(values=values):
            return "{" + _render_operands(values, scope) + "}"
        case ast.Set(elts=elts):
            return "{" + _render_operands(elts, scope) + "}"
        case ast.List(elts=elts):
            return "[" + _render_operands(elts, scope) + "]"
        case ast.Tuple(elts=elts):
            return "(" + _render_operands(elts, scope) + ")"
        case ast.Subscript(value=value, slice=index):
            return f"{_render_operand(value, scope)}[{_render_operand(index, scope)}]"
        case ast.NamedExpr(value=value) | ast.Await(value=value) | ast.Starred(value=value):
            return render_expr(value, scope)
        case ast.Yield(value=None):
            return "yield None"
        case ast.Yield(value=ast.expr() as value) | ast.YieldFrom(value=value):
            return f"yield {render_expr(value, scope)}"
        case _:
            return _COLLAPSED


def _render_operand(node: ast.expr, scope: RenderScope) -> str:
    """An operand of a call, container or subscript: rendered when it contains
    a model chain anywhere, else ``_``."""
    return render_expr(node, scope) if _contains_model_chain(node, scope) else _COLLAPSED


def _render_operands(nodes: list[ast.expr], scope: RenderScope) -> str:
    return ", ".join(_render_operand(node, scope) for node in nodes)


def _render_call(node: ast.Call, scope: RenderScope) -> str:
    """``<callee>(<operands>)``: the callee renders as its model chain when
    it is one, else the literal word ``call``. Positional arguments keep
    source order; keyword arguments are ordered by keyword name (the name
    itself never appears) so two adapters spelling the same keywords in a
    different order compare equal; ``**spread`` arguments come last."""
    callee_chain = _model_chain_root(node.func, scope)
    callee_text = callee_chain if callee_chain is not None else _ANONYMOUS_CALLEE
    ordered_keywords = sorted(node.keywords, key=lambda keyword: (keyword.arg is None, keyword.arg or ""))
    operands = [*node.args, *(keyword.value for keyword in ordered_keywords)]
    return f"{callee_text}({_render_operands(operands, scope)})"


def _render_compare(node: ast.Compare, scope: RenderScope) -> str:
    parts = [render_expr(node.left, scope)]
    for op, comparator in zip(node.ops, node.comparators, strict=True):
        parts.append(_COMPARE_OP_NAMES[type(op)])
        parts.append(render_expr(comparator, scope))
    return " ".join(parts)


def _render_comprehension(node: _ComprehensionNode, scope: RenderScope) -> str:
    """``comp(for <iter> if <cond> ...)``: only the iteration sources and the
    filter predicates -- never the element expression, which is rendering.
    Rendered in the comprehension's own scope, so a target bound from a
    model iterable is a derived root inside its conditions."""
    inner = scope.for_comprehension(node)
    clauses: list[str] = []
    for generator in node.generators:
        clauses.append(f"for {render_expr(generator.iter, inner)}")
        clauses.extend(f"if {render_expr(condition, inner)}" for condition in generator.ifs)
    return f"comp({' '.join(clauses)})"


def _render_pattern(pattern: ast.pattern, scope: RenderScope) -> str:
    """A ``case`` arm's pattern: matched values render through the expression
    table (so a model-rooted value keeps its chain and an enum member
    collapses to ``_``), alternatives join with ``or``, captures and
    wildcards are ``_``, structural patterns keep their sub-patterns."""
    match pattern:
        case ast.MatchValue(value=value):
            return render_expr(value, scope)
        case ast.MatchSingleton(value=value):
            return repr(value)
        case ast.MatchOr(patterns=patterns):
            return " or ".join(_render_pattern(alternative, scope) for alternative in patterns)
        case ast.MatchAs(pattern=None) | ast.MatchStar():
            return _COLLAPSED
        case ast.MatchAs(pattern=ast.pattern() as inner):
            return _render_pattern(inner, scope)
        case ast.MatchSequence(patterns=patterns):
            return "[" + ", ".join(_render_pattern(item, scope) for item in patterns) + "]"
        case ast.MatchMapping(patterns=patterns):
            return "{" + ", ".join(_render_pattern(item, scope) for item in patterns) + "}"
        case ast.MatchClass(patterns=patterns, kwd_patterns=kwd_patterns):
            rendered = [_render_pattern(item, scope) for item in (*patterns, *kwd_patterns)]
            return "class(" + ", ".join(rendered) + ")"
        case _:
            raise SkeletonError(
                f"Cannot render match pattern kind {type(pattern).__name__!r} at line "
                f"{pattern.lineno}: the pattern grammar known to this extractor is "
                f"{sorted(cls.__name__ for cls in ast.pattern.__subclasses__())}. Fix: add a "
                f"rendering row for the new pattern kind."
            )


# ---------------------------------------------------------------------------
# Decision skeleton (statement-level)
# ---------------------------------------------------------------------------


def decision_skeleton(fn: FunctionSource) -> str:
    """The ordered, rendering-blind decision skeleton for *fn*.

    Args:
        fn: The function to extract a skeleton from.

    Returns:
        Newline-joined skeleton lines, in source order.

    Raises:
        SkeletonError: If a statement or pattern kind cannot be classified,
            naming the function and file.
    """
    lines: list[str] = []
    try:
        _emit_block(fn.node.body, RenderScope.for_function(fn.node), lines)
    except SkeletonError as exc:
        raise SkeletonError(
            f"Cannot extract the decision skeleton of {fn.qualified_name} "
            f"({fn.package}:{fn.file_path}:{fn.line_number}): {exc}"
        ) from exc
    return "\n".join(lines)


def _emit_block(body: list[ast.stmt], scope: RenderScope, lines: list[str]) -> None:
    for stmt in body:
        _emit_statement(stmt, scope, lines)


def _emit_statement(stmt: ast.stmt, scope: RenderScope, lines: list[str]) -> None:
    """Append the line(s) one statement contributes and recurse into every
    nested statement list. Every statement kind in the grammar is named
    here; an unknown kind raises rather than being walked past, because a
    container this dispatch does not know about could hide decisions.

    A nested ``def`` is walked in its own layered scope (its parameters are
    parameters too; its bindings shadow the outer table); ``with``/``try``/
    nested ``class`` bodies are walked transparently -- they contribute no
    line but may hold decisions.
    """
    if isinstance(stmt, _NO_DECISION_STATEMENT_KINDS):
        return
    match stmt:
        case ast.If(test=test, body=body, orelse=orelse):
            lines.append(f"if {render_expr(test, scope)}")
            _emit_block(body, scope, lines)
            _emit_else(orelse, scope, lines)
            lines.append("endif")
        case ast.For(iter=header, body=body, orelse=orelse) | ast.AsyncFor(iter=header, body=body, orelse=orelse):
            _emit_loop("for", header, body, orelse, scope, lines)
        case ast.While(test=header, body=body, orelse=orelse):
            _emit_loop("while", header, body, orelse, scope, lines)
        case ast.Match(subject=subject, cases=cases):
            _emit_match(subject, cases, scope, lines)
        case ast.FunctionDef(body=body) | ast.AsyncFunctionDef(body=body):
            _emit_block(body, scope.nested(stmt), lines)
        case ast.ClassDef(body=body) | ast.With(body=body) | ast.AsyncWith(body=body):
            _emit_block(body, scope, lines)
        case (
            ast.Try(body=body, handlers=handlers, orelse=orelse, finalbody=finalbody)
            | ast.TryStar(body=body, handlers=handlers, orelse=orelse, finalbody=finalbody)
        ):
            for nested in (body, *(handler.body for handler in handlers), orelse, finalbody):
                _emit_block(nested, scope, lines)
        case (
            ast.Return()
            | ast.Raise()
            | ast.Assert()
            | ast.Break()
            | ast.Continue()
            | ast.Assign()
            | ast.AnnAssign()
            | ast.AugAssign()
            | ast.Expr()
        ):
            lines.extend(_simple_statement_lines(stmt, scope))
        case _:
            raise SkeletonError(
                f"Cannot classify statement kind {type(stmt).__name__!r} at line {stmt.lineno}: "
                f"the statement grammar known to this extractor is "
                f"{sorted(cls.__name__ for cls in ast.stmt.__subclasses__())}. Fix: add a dispatch "
                f"row for the new statement kind (a decision-free kind joins "
                f"_NO_DECISION_STATEMENT_KINDS)."
            )


def _simple_statement_lines(stmt: ast.stmt, scope: RenderScope) -> list[str]:
    """Zero or one skeleton line for a statement with no nested block. A bare
    ``return`` is normalized to ``return None`` (identical semantics); a
    ``yield`` statement is a produced value and always renders, like a
    return; an assignment renders only when its value reads model data and
    it is not a rename (every bound name a derived root that is read
    somewhere -- the read is then carried by each use); any other expression
    statement renders only when it reads model data."""
    match stmt:
        case ast.Return(value=None):
            return ["return None"]
        case ast.Return(value=ast.expr() as value):
            return [f"return {render_expr(value, scope)}"]
        case ast.Raise():
            return ["raise"]
        case ast.Assert(test=test):
            return [f"assert {render_expr(test, scope)}"]
        case ast.Break():
            return ["break"]
        case ast.Continue():
            return ["continue"]
        case ast.Assign(value=value) | ast.AugAssign(value=value) | ast.AnnAssign(value=ast.expr() as value):
            if not _contains_model_chain(value, scope) or _is_rename(stmt, scope):
                return []
            return [f"= {render_expr(value, scope)}"]
        case ast.AnnAssign(value=None):
            return []
        case ast.Expr(value=(ast.Yield() | ast.YieldFrom()) as value):
            return [render_expr(value, scope)]
        case ast.Expr(value=value):
            return [render_expr(value, scope)] if _contains_model_chain(value, scope) else []
        case _:
            raise SkeletonError(
                f"Statement kind {type(stmt).__name__!r} at line {stmt.lineno} reached the simple-statement "
                f"renderer without a rendering row. Fix: add one, or route the kind through _emit_statement."
            )


def _is_rename(stmt: ast.stmt, scope: RenderScope) -> bool:
    """Whether an assignment merely names model data that is read later:
    every name it binds is a derived root and is loaded somewhere in the
    function. Such an assignment adds no line -- its read appears at every
    use. An augmented assignment never qualifies (its target is rebound and
    so is never a derived root), nor does an assignment nobody reads."""
    names = [binding.name for binding in _own_bindings(stmt)]
    return bool(names) and all(name in scope.derived_roots and name in scope.loaded_names for name in names)


def _emit_else(orelse: list[ast.stmt], scope: RenderScope, lines: list[str]) -> None:
    if not orelse:
        return
    lines.append("else")
    _emit_block(orelse, scope, lines)


def _emit_loop(
    keyword: str,
    header: ast.expr,
    body: list[ast.stmt],
    orelse: list[ast.stmt],
    scope: RenderScope,
    lines: list[str],
) -> None:
    lines.append(f"{keyword} {render_expr(header, scope)}")
    _emit_block(body, scope, lines)
    _emit_else(orelse, scope, lines)
    lines.append(f"end{keyword}")


def _emit_match(
    subject: ast.expr,
    cases: list[ast.match_case],
    scope: RenderScope,
    lines: list[str],
) -> None:
    lines.append(f"match {render_expr(subject, scope)}")
    for case in cases:
        guard = f" if {render_expr(case.guard, scope)}" if case.guard is not None else ""
        lines.append(f"case {_render_pattern(case.pattern, scope)}{guard}")
        _emit_block(case.body, scope, lines)
    lines.append("endmatch")


# ---------------------------------------------------------------------------
# Source normalization (the `identical` comparator)
# ---------------------------------------------------------------------------


def normalized_source(fn: FunctionSource) -> str:
    """*fn*'s source with its docstring spliced out, dedented, and every
    whitespace-only line dropped -- the comparator for the ``identical``
    verdict (two functions whose bodies are byte-identical once
    rendering-neutral whitespace and the docstring are gone).

    Re-parses ``fn.source_text`` (a self-contained, possibly decorated
    function snippet) rather than cross-referencing original-file line
    numbers, and removes the docstring by its exact source coordinates so a
    docstring sharing a line with the ``def`` or with the next statement is
    handled the same as a multi-line one.

    Args:
        fn: The function to normalize.

    Returns:
        The normalized source, lines joined with ``\\n``, no trailing newline.

    Raises:
        SkeletonError: If the snippet does not re-parse as exactly one
            function definition, naming the function and file.
    """
    dedented = textwrap.dedent(fn.source_text)
    try:
        snippet = ast.parse(dedented)
    except SyntaxError as exc:
        raise SkeletonError(
            f"Cannot normalize the source of {fn.qualified_name} ({fn.package}:{fn.file_path}:"
            f"{fn.line_number}): the collected snippet does not parse: {exc}. Fix: collect the "
            f"function's whole decorated source segment, not a partial line range."
        ) from exc
    if len(snippet.body) != 1 or not isinstance(snippet.body[0], (ast.FunctionDef, ast.AsyncFunctionDef)):
        raise SkeletonError(
            f"Cannot normalize the source of {fn.qualified_name} ({fn.package}:{fn.file_path}:"
            f"{fn.line_number}): expected the snippet to hold exactly one function definition, "
            f"found {[type(stmt).__name__ for stmt in snippet.body]}."
        )
    without_docstring = _without_docstring(dedented, snippet.body[0])
    return "\n".join(line.rstrip() for line in without_docstring.splitlines() if line.strip())


def _without_docstring(text: str, fn_node: _FunctionDefNode) -> str:
    """*text* with *fn_node*'s docstring literal removed by its exact
    (line, column) span. Any whitespace-only line this leaves behind is
    dropped by the caller."""
    if not _has_docstring(fn_node.body):
        return text
    docstring = fn_node.body[0]
    if docstring.end_lineno is None or docstring.end_col_offset is None:
        raise SkeletonError(
            f"Docstring node of {fn_node.name!r} at line {docstring.lineno} carries no end position; "
            f"expected ast.parse() to populate end_lineno/end_col_offset (Python >= 3.8)."
        )
    lines = text.splitlines(keepends=True)
    before = "".join(lines[: docstring.lineno - 1]) + lines[docstring.lineno - 1][: docstring.col_offset]
    after = lines[docstring.end_lineno - 1][docstring.end_col_offset :] + "".join(lines[docstring.end_lineno :])
    return before + after


def _has_docstring(body: list[ast.stmt]) -> bool:
    if not body or not isinstance(body[0], ast.Expr):
        return False
    return isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str)


def _body_without_docstring(body: list[ast.stmt]) -> list[ast.stmt]:
    return body[1:] if _has_docstring(body) else body


# ---------------------------------------------------------------------------
# Pre-binding-adapter recognition
# ---------------------------------------------------------------------------


def is_pre_binding_adapter(fn: FunctionSource) -> bool:
    """Whether *fn* is the exempt pre-binding-adapter shape: a function whose
    body (after any docstring) is exactly one ``return`` of a call (or
    ``await``-ed call) that resolves through ``fn.import_table`` to a symbol
    under the shared codegen layer, with every argument a pass-through.
    Recognition is by AST shape only; there is no written exemption.

    A pass-through argument is a bare name (the adapter's own parameter, or
    this package's module-level constant or casing callable), a ``self``-
    rooted or otherwise non-parameter-rooted attribute chain (this package's
    own state, an enum member, a module attribute), a literal constant, or a
    ``*name``/``**name`` spread of a bare name. A ``P.<attr>`` argument is
    NOT a pass-through: forwarding a *piece* of a parameter is the adapter
    deciding which piece, which is exactly the decision this exemption must
    not hide. Every other argument shape (a nested call, arithmetic, a
    container, a comprehension, a lambda, a conditional) denies the exemption.

    Args:
        fn: The function to test.

    Returns:
        True iff *fn* has the pre-binding-adapter shape.
    """
    body = _body_without_docstring(fn.node.body)
    if len(body) != 1 or not isinstance(body[0], ast.Return):
        return False
    returned = body[0].value
    if isinstance(returned, ast.Await):
        returned = returned.value
    if not isinstance(returned, ast.Call):
        return False
    scope = RenderScope.for_function(fn.node)
    if not _is_shared_layer_callee(returned.func, fn.import_table, scope.param_names):
        return False
    arguments = (*returned.args, *(keyword.value for keyword in returned.keywords))
    return all(_is_pass_through_argument(argument, scope) for argument in arguments)


def _is_shared_layer_callee(func: ast.expr, import_table: dict[str, str], param_names: frozenset[str]) -> bool:
    """Whether a call's callee resolves, via *import_table*, to a name under
    the shared codegen layer. A callee that is a parameter (shadowing an
    import), a ``self`` method, or anything but a plain imported name or an
    imported module's attribute does not resolve -- and an unresolved callee
    is never exempt."""
    match func:
        case ast.Name(id=name):
            if name in param_names or name not in import_table:
                return False
            qualified = import_table[name]
        case ast.Attribute(value=ast.Name(id=root), attr=attr):
            if root in param_names or root == _SELF_NAME or root not in import_table:
                return False
            qualified = f"{import_table[root]}.{attr}"
        case _:
            return False
    return qualified.startswith(_SHARED_LAYER_MODULE_PREFIX)


def _is_pass_through_argument(argument: ast.expr, scope: RenderScope) -> bool:
    match argument:
        case ast.Name() | ast.Constant() | ast.Starred(value=ast.Name()):
            return True
        case ast.Attribute():
            chain = _model_chain_root(argument, scope)
            return chain is None or chain.split(".")[0] == _SELF_TOKEN
        case _:
            return False


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------


def _assert(condition: bool, label: str) -> bool:
    """Print [OK]/[FAIL] for one self-test assertion and return it."""
    print(f"[OK] {label}" if condition else f"[FAIL] {label}")
    return condition


def _function_source_from_code(code: str, package: str = "self_test") -> FunctionSource:
    """Build a ``FunctionSource`` for the first top-level function in *code*
    -- self-test only, never loads a real plugin or package."""
    dedented = textwrap.dedent(code)
    module = ast.parse(dedented)
    fn_node = next(node for node in module.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)))
    lines = dedented.splitlines(keepends=True)
    start = (fn_node.decorator_list[0].lineno if fn_node.decorator_list else fn_node.lineno) - 1
    source_text = "".join(lines[start : fn_node.end_lineno])
    return FunctionSource(
        package=package,
        file_path=Path("<self-test>"),
        line_number=fn_node.lineno,
        qualified_name=fn_node.name,
        node=fn_node,
        source_text=source_text,
        import_table=build_import_table(module, package),
    )


def _skeleton_of(code: str) -> str:
    """Self-test shorthand: the decision skeleton of the first function in *code*."""
    return decision_skeleton(_function_source_from_code(code))


#: Rendering-only tokens from the skeleton-equality variants below; none may
#: ever appear in a skeleton.
_RENDERING_TOKENS_THAT_MUST_NOT_LEAK: Final[tuple[str, ...]] = (
    "Docstring",
    "docstring",
    "command",
    "cmd",
    "build_thing",
    "build_widget",
    "Command",
    "Context",
    "cached",
    "thing",
    "widget",
)

_VARIANT_A_CODE: Final[str] = '''
    def build_thing(command):
        """Docstring A."""
        if command.kind == "thing":
            return f"thing:{command.name}"
        return None
    '''
_VARIANT_B_CODE: Final[str] = '''
    def build_widget(cmd):
        """A completely different, much longer docstring."""
        if cmd.kind == "thing":
            return f"thing:{cmd.name}"
        return None
    '''
#: Same decisions as variant A under every rendering difference the design
#: names: annotations, a decorator, a different string literal, a different
#: f-string, different parameter and function names, no docstring.
_VARIANT_RENDERED_CODE: Final[str] = """
    @cached
    def build_widget(cmd: Command, /) -> Context:
        if cmd.kind == "widget-kind":
            return f"widget {cmd.name!r} built"
        return None
    """

#: Every statement kind and every match-pattern kind in the grammar, plus
#: every expression kind that the dispatch table has a row for, in one
#: function -- the sweep proving nothing raises on a classifiable construct
#: and that the statement dispatch names the whole grammar. The ``type``
#: alias statement is appended only where the interpreter can parse it.
_GRAMMAR_SWEEP_CODE: Final[str] = '''
    async def sweep(self, entity, *rest, flag=False, **extra):
        """Docstring."""
        import os
        from typing import TYPE_CHECKING
        global counter
        counter = entity.count + 1
        total: int = entity.count
        bare: int
        y = [f for f in entity.fields if f.required]
        z = {k: v for k, v in entity.mapping.items()}
        w = {f.name for f in entity.fields}
        g = (f for f in entity.fields)
        lam = lambda q: q + 1
        t = (entity.a, entity.b)
        lst = [entity.a, 1, "s"]
        st = {1, 2}
        d = {"k": entity.a, **extra}
        sub = entity.fields[0].name
        sl = entity.fields[1:2]
        star = os.path.join(*rest, **extra)
        counter += 1
        if (n := entity.name) and not flag or counter > 1 < 2:
            pass
        elif -counter is not None:
            del lam
        v = await entity.load()
        fs = f"{entity.name!r:>10}{counter}"
        cmp = entity.a if flag else entity.b
        b = b"bytes"
        e = ...
        async for item in entity.stream:
            continue
        else:
            pass
        for item in entity.items:
            if item:
                break
        else:
            pass
        while entity.pending:
            entity.pending = False
        else:
            pass
        try:
            risky = entity.load()
        except ValueError as exc:
            raise RuntimeError("wrapped") from exc
        else:
            pass
        finally:
            pass
        try:
            pass
        except* TypeError:
            pass
        with entity.lock:
            pass
        async with entity.async_lock as guard:
            pass
        match entity.kind:
            case "a" | "b":
                return 1
            case [first, *others]:
                return 2
            case {"key": value, **rest_of_mapping}:
                return 3
            case Kind(name=name) if name:
                return 4
            case None:
                return 5
            case _:
                pass
        def inner(p):
            nonlocal y
            y = p
            yield entity.name
            yield from entity.fields
            yield
        class Local:
            attr: int = 0
            def method(self, q):
                return q
        assert entity.valid, "must be valid"
        return
    '''
_TYPE_ALIAS_SWEEP_CODE: Final[str] = """
    def alias_sweep(entity):
        type Alias = int
        return entity
    """


def _grammar_sweep_holds() -> bool:
    """Every statement kind and match-pattern kind in the running
    interpreter's grammar appears in the sweep, every function in it
    skeletonizes, and every expression in it renders -- with no exception.
    A kind the grammar has and the sweep lacks fails this (the sweep is
    proven complete, not assumed), so a new Python statement kind fails the
    self-test until the dispatch and the sweep both name it."""
    code = _GRAMMAR_SWEEP_CODE
    if _TYPE_ALIAS_STATEMENT_KINDS:
        code += _TYPE_ALIAS_SWEEP_CODE
    module = ast.parse(textwrap.dedent(code))
    if not _grammar_sweep_is_complete(module):
        return False
    functions = [node for node in module.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    try:
        return all(_sweep_function_renders(fn_node) for fn_node in functions)
    except (SkeletonError, AttributeError, TypeError, KeyError, ValueError) as exc:
        logger.error("grammar sweep raised %s: %s", type(exc).__name__, exc)
        return False


def _grammar_sweep_is_complete(module: ast.Module) -> bool:
    """``grammar - sweep`` must be empty for statement kinds and for
    match-pattern kinds: the seam between what Python can parse and what the
    dispatch names, computed rather than assumed."""
    present_statement_kinds = {type(node) for node in ast.walk(module) if isinstance(node, ast.stmt)}
    present_pattern_kinds = {type(node) for node in ast.walk(module) if isinstance(node, ast.pattern)}
    missing_statements = set(ast.stmt.__subclasses__()) - present_statement_kinds
    missing_patterns = set(ast.pattern.__subclasses__()) - present_pattern_kinds
    if not missing_statements and not missing_patterns:
        return True
    logger.error(
        "grammar sweep is incomplete: missing statements=%s patterns=%s",
        sorted(cls.__name__ for cls in missing_statements),
        sorted(cls.__name__ for cls in missing_patterns),
    )
    return False


def _sweep_function_renders(fn_node: _FunctionDefNode) -> bool:
    """Skeletonize one sweep function and render every expression in it;
    exceptions propagate to the caller, an empty skeleton is a failure."""
    fn = _function_source_from_code(ast.unparse(fn_node))
    skeleton = decision_skeleton(fn)
    scope = RenderScope.for_function(fn.node)
    for node in ast.walk(fn.node):
        if isinstance(node, ast.expr):
            render_expr(node, scope)
    if skeleton:
        return True
    logger.error("grammar sweep produced an empty skeleton for %s", fn_node.name)
    return False


def _run_skeleton_equality_checks() -> bool:
    ok = True
    variant_a = _function_source_from_code(_VARIANT_A_CODE)
    variant_b = _function_source_from_code(_VARIANT_B_CODE)
    ok &= _assert(
        decision_skeleton(variant_a) == decision_skeleton(variant_b),
        "(1) rendering-only variants (names, docstrings) produce equal skeletons",
    )

    variant_added_raise = _function_source_from_code(
        '''
        def build_thing(command):
            """Docstring A."""
            if command.kind == "thing":
                return f"thing:{command.name}"
            if not command.body:
                raise ValueError("empty")
            return None
        '''
    )
    ok &= _assert(
        decision_skeleton(variant_a) != decision_skeleton(variant_added_raise),
        "(2) an added fail-closed raise changes the skeleton",
    )

    variant_added_model_read = _function_source_from_code(
        '''
        def build_thing(command):
            """Docstring A."""
            block_name = command.block_name
            if command.kind == "thing":
                return f"thing:{command.name}"
            return None
        '''
    )
    ok &= _assert(
        decision_skeleton(variant_a) != decision_skeleton(variant_added_model_read),
        "(3) an added model-rooted assignment changes the skeleton",
    )
    return ok


def _run_adapter_checks() -> bool:
    ok = True
    adapter = _function_source_from_code(
        """
        from datrix_codegen_common.algorithms.entity import build_entity_context

        def build_context(entity, language_id):
            return build_entity_context(entity, language_id)
        """
    )
    ok &= _assert(is_pre_binding_adapter(adapter), "(4) single-return shared-call adapter recognized")

    nested_call = _function_source_from_code(
        """
        from datrix_codegen_common.algorithms.entity import build_entity_context, resolve_extra

        def build_context(entity, language_id):
            return build_entity_context(resolve_extra(entity), language_id)
        """
    )
    ok &= _assert(not is_pre_binding_adapter(nested_call), "(5) a nested call in an argument is not an adapter")

    private_callee = _function_source_from_code(
        """
        from datrix_codegen_python.helpers import build_entity_context_python

        def build_context(entity, language_id):
            return build_entity_context_python(entity, language_id)
        """
    )
    ok &= _assert(
        not is_pre_binding_adapter(private_callee),
        "(6) a callee not resolving to datrix_codegen_common is not an adapter",
    )
    return ok


def _run_source_and_import_checks() -> bool:
    ok = True
    type_checking_module = ast.parse(
        textwrap.dedent(
            """
            from typing import TYPE_CHECKING
            if TYPE_CHECKING:
                from datrix_codegen_common.algorithms.entity import build_entity_context

            def build_context(entity, language_id):
                return build_entity_context(entity, language_id)
            """
        )
    )
    tc_table = build_import_table(type_checking_module, "self_test")
    ok &= _assert(
        "build_entity_context" in tc_table
        and tc_table["build_entity_context"] == "datrix_codegen_common.algorithms.entity.build_entity_context",
        "(7) an import guarded by TYPE_CHECKING resolves in the import table",
    )

    tmp_dir = Path(tempfile.mkdtemp(prefix="decision-skeleton-selftest-"))
    try:
        broken_file = tmp_dir / "broken.py"
        broken_file.write_text("def broken(:\n    pass\n", encoding="utf-8")
        try:
            parse_module_or_raise(broken_file)
            fail_closed = False
        except SkeletonError as exc:
            fail_closed = str(broken_file) in str(exc)
        ok &= _assert(fail_closed, "(8) an unparseable file raises SkeletonError naming the file")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    return ok


def _run_extended_skeleton_checks() -> bool:
    ok = True
    variant_a = _function_source_from_code(_VARIANT_A_CODE)
    variant_b = _function_source_from_code(_VARIANT_B_CODE)
    variant_rendered = _function_source_from_code(_VARIANT_RENDERED_CODE)
    ok &= _assert(
        decision_skeleton(variant_a) == decision_skeleton(variant_rendered),
        "(9) annotations, a decorator, a string literal and an f-string leave the skeleton equal",
    )

    variant_other_predicate = _function_source_from_code(
        '''
        def build_thing(command):
            """Docstring A."""
            if command.category == "thing":
                return f"thing:{command.name}"
            return None
        '''
    )
    variant_added_branch = _function_source_from_code(
        '''
        def build_thing(command):
            """Docstring A."""
            if command.kind == "thing":
                return f"thing:{command.name}"
            else:
                return command.fallback
            return None
        '''
    )
    ok &= _assert(
        decision_skeleton(variant_a) != decision_skeleton(variant_other_predicate)
        and decision_skeleton(variant_a) != decision_skeleton(variant_added_branch),
        "(10) a different predicate or an added else-branch changes the skeleton",
    )

    skeleton_texts = "\n".join(decision_skeleton(fn) for fn in (variant_a, variant_b, variant_rendered))
    ok &= _assert(
        not any(token in skeleton_texts for token in _RENDERING_TOKENS_THAT_MUST_NOT_LEAK),
        "(11) no docstring, parameter name, function name, annotation, decorator or literal leaks into a skeleton",
    )

    self_rooted = _skeleton_of("def f(self, entity):\n    return self.name\n")
    param_rooted = _skeleton_of("def f(self, entity):\n    return entity.name\n")
    ok &= _assert(
        self_rooted == "return self.name" and param_rooted == "return P.name" and self_rooted != param_rooted,
        "(12) a self-rooted chain renders literally and stays distinct from a parameter-rooted one",
    )

    match_a = _skeleton_of(
        """
        def resolve(collection):
            match collection.kind:
                case Kind.ARRAY | Kind.SET:
                    return collection.element
                case Kind.MAP:
                    raise TypeError("unsupported")
        """
    )
    match_b = _skeleton_of(
        """
        def resolve(collection):
            match collection.kind:
                case Kind.ARRAY | Kind.SET:
                    return collection.element
                case Kind.MAP:
                    return collection.key
        """
    )
    match_a_renamed = _skeleton_of(
        """
        def resolve_type(coll):
            match coll.kind:
                case CollectionKind.ARRAY | CollectionKind.SET:
                    return coll.element
                case CollectionKind.MAP:
                    raise TypeMappingError("Map collections are not supported here")
        """
    )
    ok &= _assert(
        match_a != match_b and match_a == match_a_renamed,
        "(13) match arms are decisions: a differing arm body changes the skeleton, renaming does not",
    )

    dict_a = _skeleton_of('def ctx(entity):\n    return {"name": entity.name}\n')
    dict_b = _skeleton_of('def ctx(entity):\n    return {"name": entity.name, "table": entity.table}\n')
    dict_a_relabelled = _skeleton_of('def ctx(e):\n    return {"label": e.name}\n')
    ok &= _assert(
        dict_a != dict_b and dict_a == dict_a_relabelled,
        "(14) a model read inside a returned container changes the skeleton; its key labels do not",
    )
    return ok


def _run_extended_adapter_checks() -> bool:
    ok = True
    model_piece_forwarded = _function_source_from_code(
        """
        from datrix_codegen_common.algorithms.entity import build_entity_context

        def build_context(self, entity):
            return build_entity_context(entity.fields, self.language_id, to_snake, LANGUAGE_ID, "python")
        """
    )
    own_state_forwarded = _function_source_from_code(
        """
        from datrix_codegen_common.algorithms.entity import build_entity_context

        def build_context(self, entity, *rest, **options):
            return build_entity_context(
                entity, self.profile.naming.caser, to_snake, LANGUAGE_ID, "python", *rest, **options
            )
        """
    )
    ok &= _assert(
        not is_pre_binding_adapter(model_piece_forwarded) and is_pre_binding_adapter(own_state_forwarded),
        "(15) forwarding a piece of a parameter denies the exemption; own state, constants and spreads do not",
    )

    async_module_alias = _function_source_from_code(
        '''
        import datrix_codegen_common.algorithms.entity as shared_entity

        async def build_context(entity, language_id):
            """Docstring."""
            return await shared_entity.build_entity_context(entity, language_id=language_id)
        '''
    )
    ok &= _assert(
        is_pre_binding_adapter(async_module_alias),
        "(16) an async adapter awaiting an aliased shared-module attribute call is recognized",
    )

    shadowed_callee = _function_source_from_code(
        """
        from datrix_codegen_common.algorithms.entity import build_entity_context

        def build_context(build_entity_context, entity):
            return build_entity_context(entity)
        """
    )
    two_statements = _function_source_from_code(
        """
        from datrix_codegen_common.algorithms.entity import build_entity_context

        def build_context(entity):
            context = build_entity_context(entity)
            return context
        """
    )
    ok &= _assert(
        not is_pre_binding_adapter(shadowed_callee) and not is_pre_binding_adapter(two_statements),
        "(17) a parameter shadowing the shared import, or a second statement, denies the exemption",
    )
    return ok


def _run_extended_source_checks() -> bool:
    ok = True
    relative_module = ast.parse(
        textwrap.dedent(
            """
            from . import sibling
            from .sub import leaf as renamed
            from ..parent_pkg.other import thing
            from x import *
            import a.b.c
            import a.b.c as abc
            """
        )
    )
    relative_table = build_import_table(relative_module, "root.pkg")
    ok &= _assert(
        relative_table
        == {
            "sibling": "root.pkg.sibling",
            "renamed": "root.pkg.sub.leaf",
            "thing": "root.parent_pkg.other.thing",
            "a": "a",
            "abc": "a.b.c",
        },
        "(18) relative imports resolve against the package, aliases bind, wildcard imports bind nothing",
    )

    docstring_only_a = _function_source_from_code(
        '''
        @staticmethod
        def build(entity):
            """One docstring."""
            name = entity.name
            return name
        '''
    )
    docstring_only_b = _function_source_from_code(
        '''
        @staticmethod
        def build(entity):
            """Another, much

            longer docstring."""

            name = entity.name
            return name
        '''
    )
    body_differs = _function_source_from_code(
        '''
        @staticmethod
        def build(entity):
            """One docstring."""
            name = entity.table
            return name
        '''
    )
    ok &= _assert(
        normalized_source(docstring_only_a) == normalized_source(docstring_only_b)
        and normalized_source(docstring_only_a) != normalized_source(body_differs)
        and "docstring" not in normalized_source(docstring_only_a),
        "(19) normalized source drops the docstring and blank lines, and still sees a body difference",
    )
    return ok


def _run_derived_root_checks() -> bool:
    ok = True
    loop_required = _skeleton_of(
        """
        def first_required(entity):
            for field in entity.fields:
                if field.required:
                    return field
            return None
        """
    )
    loop_unique = _skeleton_of(
        """
        def first_unique(entity):
            for column in entity.fields:
                if column.unique:
                    return column
            return None
        """
    )
    ok &= _assert(
        loop_required != loop_unique
        and loop_required == "for P.fields\nif P.fields[*].required\nreturn P.fields[*]\nendif\nendfor\nreturn None",
        "(21) a predicate on a loop variable bound from a model collection is a decision, spelled <iterable>[*]",
    )

    alias = _skeleton_of(
        """
        def pick(cmd):
            block = cmd.block_name
            if block:
                return 1
            return 0
        """
    )
    inline = _skeleton_of(
        """
        def pick(cmd):
            if cmd.block_name:
                return 1
            return 0
        """
    )
    other_read = _skeleton_of(
        """
        def pick(cmd):
            if cmd.name:
                return 1
            return 0
        """
    )
    ok &= _assert(
        alias == inline and alias != other_read,
        "(22) a once-bound local alias of a model chain is a rename: it preserves the decision and adds no line",
    )

    twice_bound = _skeleton_of(
        """
        def pick(cmd):
            block = cmd.block_name
            block = cmd.fallback_name
            if block:
                return 1
            return 0
        """
    )
    twice_bound_other_use = _skeleton_of(
        """
        def pick(cmd):
            block = cmd.block_name
            block = cmd.fallback_name
            if block.kind:
                return 1
            return 0
        """
    )
    ok &= _assert(
        twice_bound == twice_bound_other_use and "\nif _\n" in twice_bound,
        "(23) a name bound twice stays a plain local: variants differing only after the second binding compare equal",
    )

    unpack_root = _skeleton_of(
        """
        def roots(block):
            for name, entity in block.entities.items():
                if entity.is_root:
                    return name
            return None
        """
    )
    unpack_leaf = _skeleton_of(
        """
        def leaves(block):
            for key, item in block.entities.items():
                if item.is_leaf:
                    return key
            return None
        """
    )
    ok &= _assert(
        unpack_root != unpack_leaf
        and unpack_root
        == (
            "for P.entities.items()\nif P.entities.items()[*][1].is_root\n"
            "return P.entities.items()[*][0]\nendif\nendfor\nreturn None"
        ),
        "(24) tuple-unpacking over a model mapping spells each position; a predicate on the unpacked item is a decision",
    )

    chained = _skeleton_of(
        """
        def check(entity):
            fields = entity.fields
            for field in fields:
                constraint = field.constraint
                if constraint.kind == "unique" and (label := constraint.label) and label == "x":
                    raise ValueError("dup")
        """
    )
    chained_inline = _skeleton_of(
        """
        def check(entity):
            for field in entity.fields:
                if field.constraint.kind == "unique" and (label := field.constraint.label) and label == "x":
                    raise ValueError("dup")
        """
    )
    ok &= _assert(
        chained == chained_inline
        and chained
        == (
            "for P.fields\n"
            "if P.fields[*].constraint.kind eq S and P.fields[*].constraint.label"
            " and P.fields[*].constraint.label eq S\n"
            "raise\nendif\nendfor"
        ),
        "(25) derived roots compose through a second derived root and a walrus, matching the fully inlined form",
    )

    captures = _skeleton_of(
        """
        def guard(entity):
            with entity.lock as held_lock:
                if held_lock.contended:
                    raise RuntimeError("busy")
            match entity.kind:
                case Kind(name=kind_name) if kind_name:
                    return kind_name
                case other:
                    return other
        """
    )
    ok &= _assert(
        captures
        == (
            "if P.lock.contended\nraise\nendif\nmatch P.kind\ncase class(_) if P.kind.name\n"
            "return P.kind.name\ncase _\nreturn P.kind\nendmatch"
        ),
        "(26) with-as and case captures over a model-rooted subject are derived roots (keyword capture spells .attr)",
    )
    return ok


def run_self_test() -> bool:
    """Prove the properties this module's design acceptance rests on: equal
    skeletons for rendering-only variants, unequal skeletons for
    decision-differing variants, adapter recognition by shape only, import
    resolution through TYPE_CHECKING and relative imports, fail-closed
    parsing, derived-root resolution, and a whole-grammar sweep that raises
    on nothing classifiable.

    Returns:
        True iff every assertion passed.
    """
    ok = True
    ok &= _run_skeleton_equality_checks()
    ok &= _run_adapter_checks()
    ok &= _run_source_and_import_checks()
    ok &= _run_extended_skeleton_checks()
    ok &= _run_extended_adapter_checks()
    ok &= _run_extended_source_checks()
    ok &= _assert(
        _grammar_sweep_holds(),
        "(20) every statement and match-pattern kind in the grammar is swept and none raises",
    )
    ok &= _run_derived_root_checks()
    return ok


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. This module is a library for the decision-parity
    role-grouping scanner; it exposes only ``--self-test``.

    Returns:
        0 if the self-test passed, 2 otherwise.
    """
    parser = argparse.ArgumentParser(description="Decision-skeleton extractor self-test.")
    parser.add_argument("--self-test", action="store_true", required=True, help="Run the non-vacuity self-test.")
    parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    if not run_self_test():
        logger.error("DECISION-SKELETON SELF-TEST FAILED.")
        return EXIT_SELF_TEST_FAILED
    logger.info("decision-skeleton self-test: PASS")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
