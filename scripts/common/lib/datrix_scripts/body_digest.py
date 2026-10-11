"""A function body's comparison form: the digest two copies of one body share.

Shared by the shared-home body gate (a private copy of a shared-home function) and the
duplicate-body report (any two copies anywhere), so both agree on what "the same body" means.
A copy is usually a renamed one, so equality is measured on a normalized AST rather than on
names or text:

- the function's own name, decorators, annotations and docstring are dropped;
- every parameter and every locally bound name becomes a positional token;
- every constant collapses to its type name;
- attribute names, keyword-argument names and the names of non-local call
  targets are KEPT -- two functions that read different attributes or call
  different functions never compare equal.

A function qualifies at ``MIN_BODY_LINES`` lines and ``MIN_BODY_NODES`` AST nodes (measured on
the docstring-free body), which removes Protocol ``...`` stubs and one-line accessors.
"""

from __future__ import annotations

import ast
import copy
import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from datrix_scripts.behaviour_skeleton import FunctionSource, SkeletonError

#: The floor that removes Protocol ``...`` stubs and one-line accessors.
MIN_BODY_LINES: Final[int] = 8
MIN_BODY_NODES: Final[int] = 40

_LOCAL_TOKEN_PREFIX: Final[str] = "v"
_DIGEST_ENCODING: Final[str] = "utf-8"

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef


def _has_docstring(body: Sequence[ast.stmt]) -> bool:
    if not body or not isinstance(body[0], ast.Expr):
        return False
    return isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str)


def body_without_docstring(body: Sequence[ast.stmt]) -> list[ast.stmt]:
    """*body* with its leading docstring statement, if any, removed."""
    return list(body[1:] if _has_docstring(body) else body)


def _local_names(function: FunctionNode) -> frozenset[str]:
    """Every name the function binds anywhere (itself, parameters, stores,
    comprehension targets, ``except ... as``, nested defs, match captures)."""
    names: set[str] = {function.name}
    for node in ast.walk(function):
        if isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            names.add(node.id)
        elif isinstance(node, ast.ExceptHandler) and node.name is not None:
            names.add(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name is not None:
            names.add(node.name)
        elif isinstance(node, ast.MatchMapping) and node.rest is not None:
            names.add(node.rest)
    return frozenset(names)


class _BodyNormalizer(ast.NodeTransformer):
    """Rewrites one function into its comparison form (see the module docstring)."""

    def __init__(self, local_names: frozenset[str]) -> None:
        self._local_names = local_names
        self._tokens: dict[str, str] = {}

    def _token(self, name: str) -> str:
        if name not in self._tokens:
            self._tokens[name] = f"{_LOCAL_TOKEN_PREFIX}{len(self._tokens)}"
        return self._tokens[name]

    def _rename(self, name: str) -> str:
        return self._token(name) if name in self._local_names else name

    def visit_Name(self, node: ast.Name) -> ast.Name:
        return ast.Name(id=self._rename(node.id), ctx=node.ctx)

    def visit_arg(self, node: ast.arg) -> ast.arg:
        return ast.arg(arg=self._token(node.arg), annotation=None, type_comment=None)

    def visit_Constant(self, node: ast.Constant) -> ast.Constant:
        return ast.Constant(value=type(node.value).__name__)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> ast.Assign | None:
        if node.value is None:
            return None
        return ast.Assign(targets=[self.visit(node.target)], value=self.visit(node.value), type_comment=None)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> ast.ExceptHandler:
        self.generic_visit(node)
        node.name = None if node.name is None else self._rename(node.name)
        return node

    def visit_MatchAs(self, node: ast.MatchAs) -> ast.MatchAs:
        self.generic_visit(node)
        node.name = None if node.name is None else self._rename(node.name)
        return node

    def visit_MatchStar(self, node: ast.MatchStar) -> ast.MatchStar:
        node.name = None if node.name is None else self._rename(node.name)
        return node

    def visit_MatchMapping(self, node: ast.MatchMapping) -> ast.MatchMapping:
        self.generic_visit(node)
        node.rest = None if node.rest is None else self._rename(node.rest)
        return node

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.ClassDef:
        node.name = self._rename(node.name)
        node.decorator_list = []
        self.generic_visit(node)
        return node

    def _normalize_function(self, node: FunctionNode) -> FunctionNode:
        node.name = self._rename(node.name)
        node.decorator_list = []
        node.returns = None
        self.generic_visit(node)
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        normalized = self._normalize_function(node)
        assert isinstance(normalized, ast.FunctionDef)
        return normalized

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AsyncFunctionDef:
        normalized = self._normalize_function(node)
        assert isinstance(normalized, ast.AsyncFunctionDef)
        return normalized


def normalized_digest(function: FunctionNode) -> str:
    """The SHA-256 of *function*'s normalized AST (never mutates *function*)."""
    working = copy.deepcopy(function)
    working.body = body_without_docstring(working.body)
    normalized = _BodyNormalizer(_local_names(working)).visit(working)
    dumped = ast.dump(normalized, annotate_fields=True, include_attributes=False)
    return hashlib.sha256(dumped.encode(_DIGEST_ENCODING)).hexdigest()


def exact_digest(function: FunctionNode) -> str:
    """The SHA-256 of *function*'s docstring-free body with every name and constant kept."""
    body = body_without_docstring(function.body)
    dumped = "\n".join(ast.dump(statement, annotate_fields=True, include_attributes=False) for statement in body)
    return hashlib.sha256(dumped.encode(_DIGEST_ENCODING)).hexdigest()


def end_line(function: FunctionNode) -> int:
    """The last source line of *function*.

    Raises:
        SkeletonError: The node carries no end position.
    """
    if function.end_lineno is None:
        raise SkeletonError(
            f"Function {function.name!r} at line {function.lineno} carries no end position; expected "
            f"ast.parse() to populate end_lineno (Python >= 3.8). Fix: run the script under the repo venv."
        )
    return function.end_lineno


def measure_body(function: FunctionNode) -> tuple[int, int]:
    """``(lines, nodes)`` of the docstring-free body: the span from the first
    body statement to the function's last line, and the AST node count.

    Raises:
        SkeletonError: The node carries no end position.
    """
    body = body_without_docstring(function.body)
    if not body:
        return 0, 0
    lines = end_line(function) - body[0].lineno + 1
    nodes = sum(1 for statement in body for _ in ast.walk(statement))
    return lines, nodes


@dataclass(frozen=True)
class NormalizedFunction:
    """One function that cleared the floor, ready for comparison."""

    package: str
    qualified_name: str
    file_path: Path
    line_number: int
    end_line_number: int
    digest: str
    exact_digest: str
    is_public: bool

    @property
    def bare_name(self) -> str:
        return self.qualified_name.rsplit(".", 1)[-1]

    @property
    def identity(self) -> tuple[Path, int]:
        return self.file_path, self.line_number

    @property
    def line_count(self) -> int:
        return self.end_line_number - self.line_number + 1


def is_public(qualified_name: str) -> bool:
    """True when no segment of *qualified_name* starts with an underscore."""
    return not any(part.startswith("_") for part in qualified_name.split("."))


def qualifying_functions(sources: Sequence[FunctionSource]) -> list[NormalizedFunction]:
    """Every function in *sources* at or above the floor, normalized."""
    qualifying: list[NormalizedFunction] = []
    for source in sources:
        lines, nodes = measure_body(source.node)
        if lines < MIN_BODY_LINES or nodes < MIN_BODY_NODES:
            continue
        qualifying.append(
            NormalizedFunction(
                package=source.package,
                qualified_name=source.qualified_name,
                file_path=source.file_path,
                line_number=source.line_number,
                end_line_number=end_line(source.node),
                digest=normalized_digest(source.node),
                exact_digest=exact_digest(source.node),
                is_public=is_public(source.qualified_name),
            )
        )
    return qualifying
