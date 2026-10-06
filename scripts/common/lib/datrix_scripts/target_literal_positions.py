"""Target-identity positions: where a string constant names a target.

A string constant equal to a registered language or platform name is a *target
identity* only in a handful of syntactic positions; everywhere else (a docstring,
a log-message argument, an assignment right-hand side, an f-string segment) it is
prose. This module owns that position logic once, so the shared-layer ratchet
(``scan/check-import-boundaries.ps1 -CheckTargetLiterals``) and the cross-target
gates' self-scan (``datrix_scripts.registered_targets.target_references_in_module``)
cannot disagree about what counts.

The five positions:

* an operand of ``==`` / ``!=`` / ``in`` / ``not in``, or an element of a
  tuple/list/set operand of ``in`` / ``not in``;
* a subscript key (``m["azure"]``);
* the first positional argument of a ``.get(...)`` call;
* a dict-display key (``{"python": f}``);
* the value pattern of a ``match`` statement.
"""

from __future__ import annotations

import ast


def target_name_literal_compare_hits(
    node: ast.Compare, target_literal_names: frozenset[str]
) -> list[tuple[str, int]]:
    """``(value, line_number)`` for every target-name constant in a comparison.

    Covers a string constant exactly equal to a *target_literal_names* member
    appearing as the left/right operand of an ``Eq``/``NotEq``/``In``/``NotIn``
    comparison, plus every element of a ``List``/``Tuple``/``Set`` right operand
    of an ``In``/``NotIn`` (``x in ("python", "typescript")`` yields two hits).
    """
    hits: list[tuple[str, int]] = []

    def _record(candidate: ast.expr) -> None:
        if isinstance(candidate, ast.Constant) and isinstance(candidate.value, str):
            if candidate.value in target_literal_names:
                hits.append((candidate.value, candidate.lineno))

    prior: ast.expr = node.left
    for op, comparand in zip(node.ops, node.comparators, strict=True):
        if isinstance(op, (ast.Eq, ast.NotEq, ast.In, ast.NotIn)):
            _record(prior)
            _record(comparand)
            if isinstance(op, (ast.In, ast.NotIn)) and isinstance(
                comparand, (ast.List, ast.Tuple, ast.Set)
            ):
                for element in comparand.elts:
                    _record(element)
        prior = comparand
    return hits


def target_name_literal_hits(
    tree: ast.AST, target_literal_names: frozenset[str]
) -> list[tuple[str, int]]:
    """``(value, line_number)`` for every target-name constant in a target-identity position.

    Fails closed by construction: a string constant anywhere other than the five
    positions in the module docstring (a docstring, a ``logger.*`` call argument,
    a plain assignment right-hand side, an f-string literal segment) is never
    visited, so it is never a hit -- there is no generic "any string equal to a
    vocabulary word" fallback.
    """
    hits: list[tuple[str, int]] = []

    def _record(candidate: ast.expr) -> None:
        if isinstance(candidate, ast.Constant) and isinstance(candidate.value, str):
            if candidate.value in target_literal_names:
                hits.append((candidate.value, candidate.lineno))

    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            hits.extend(target_name_literal_compare_hits(node, target_literal_names))
        elif isinstance(node, ast.Subscript):
            _record(node.slice)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and node.args
        ):
            _record(node.args[0])
        elif isinstance(node, ast.Dict):
            for key in node.keys:
                if key is not None:
                    _record(key)
        elif isinstance(node, ast.MatchValue):
            _record(node.value)

    return hits
