"""Evaluate a test module's path expression without running the module.

A test reaches a fixture through a root (``Path(__file__).resolve().parent / "fixtures"``) joined with
string literals and constants. The evaluator follows exactly what a reader can follow from the text:

* string and integer constants, and f-strings whose parts evaluate;
* ``__file__`` (the module's own path), ``Path(...)``/``PurePath(...)``, ``str(...)``;
* ``/`` and ``+``, ``.parent``, ``.parents[N]``, ``.name``, ``.stem``, ``.suffix``, ``.resolve()``,
  ``.absolute()``, ``.joinpath(...)``, ``.with_name(...)``, ``.with_suffix(...)``;
* a name bound once in the enclosing function or at module level, or imported: from another module of the
  same ``tests/`` tree it is evaluated there the same way; from an installed module (never one under a
  ``tests/`` tree) it is the module's value;
* a pytest fixture parameter: a fixture taking no parameter whose body returns one expression, in the
  module or a ``conftest.py`` between it and its ``tests/`` root;
* an attribute of an evaluated object, and an instance of an installed class built from evaluated arguments.

Anything else raises :class:`UnevaluableError` naming the expression: the caller refuses the site.
"""

from __future__ import annotations

import ast
import importlib
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePath
from types import ModuleType
from typing import Final

from datrix_scripts.framework_repos import PackageMarker

_TESTS_DIR: Final = PackageMarker.TESTS.value
_CONFTEST: Final = "conftest.py"
_PYTHON_SUFFIX: Final = ".py"
_PACKAGE_INIT: Final = "__init__.py"
_FILE_NAME: Final = "__file__"
_PATH_TYPES: Final = frozenset({"Path", "PurePath", "PurePosixPath", "PureWindowsPath"})
_PATH_ATTRIBUTES: Final = frozenset({"parent", "name", "stem", "suffix"})
_NO_ARGUMENT_METHODS: Final = frozenset({"resolve", "absolute"})
_ONE_ARGUMENT_METHODS: Final = frozenset({"with_name", "with_suffix"})
_FIXTURE_DECORATOR: Final = "fixture"
_STR_CALL: Final = "str"
_MAX_DEPTH: Final = 64

#: What an evaluated expression may be: a path, a text, an index, or an installed object an attribute is read off.
Value = PurePath | str | int | object


class UnevaluableError(Exception):
    """An expression the evaluator cannot follow from the text; the message names it and why."""


@dataclass
class ModuleScope:
    """What one module binds: its path, its ``tests/`` root, its module-level names and its imports.

    Attributes:
        path: The module.
        tests_root: The ``tests/`` directory the module lies under.
        tree: The parsed module.
        bindings: Each name assigned exactly once at module level, with its value expression.
        imports: Each imported name: ``(module, level, attribute)``; *attribute* is empty for ``import x``.
    """

    path: Path
    tests_root: Path
    tree: ast.Module
    bindings: dict[str, ast.expr] = field(default_factory=dict)
    imports: dict[str, tuple[str, int, str]] = field(default_factory=dict)


def _record_import(scope: ModuleScope, node: ast.Import | ast.ImportFrom) -> None:
    if isinstance(node, ast.Import):
        for alias in node.names:
            bound = alias.asname or alias.name.split(".", 1)[0]
            scope.imports[bound] = (alias.name if alias.asname else bound, 0, "")
        return
    for alias in node.names:
        scope.imports[alias.asname or alias.name] = (node.module or "", node.level, alias.name)


def _assigned_names(node: ast.AST) -> list[tuple[str, ast.expr | None]]:
    """The names *node* assigns, each with its value when it is the one plain target (else ``None``)."""
    if isinstance(node, ast.Assign):
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            return [(node.targets[0].id, node.value)]
        return [(name.id, None) for target in node.targets for name in ast.walk(target) if isinstance(name, ast.Name)]
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return [(node.target.id, node.value)]
    if isinstance(node, (ast.AugAssign, ast.For, ast.With, ast.NamedExpr)):
        return [(name.id, None) for name in ast.walk(node) if isinstance(name, ast.Name) and isinstance(name.ctx, ast.Store)]
    return []


def _assignments(statements: Sequence[ast.stmt]) -> Iterator[tuple[str, ast.expr | None]]:
    for statement in statements:
        for node in ast.walk(statement):
            yield from _assigned_names(node)


def single_bindings(statements: Sequence[ast.stmt]) -> dict[str, ast.expr]:
    """Each name *statements* (walked whole) assign exactly once, with one plain target, mapped to its value."""
    seen: dict[str, ast.expr | None] = {}
    rebound: set[str] = set()
    for name, value in _assignments(statements):
        if name in seen:
            rebound.add(name)
        seen[name] = value
    return {name: value for name, value in seen.items() if name not in rebound and value is not None}


def module_scope(path: Path, tests_root: Path, tree: ast.Module) -> ModuleScope:
    """The scope of the module at *path* under *tests_root*, parsed as *tree*."""
    scope = ModuleScope(path=path, tests_root=tests_root, tree=tree)
    definitions = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    scope.bindings = single_bindings([node for node in tree.body if not isinstance(node, definitions)])
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            _record_import(scope, node)
    return scope


def parse_module_file(path: Path) -> ast.Module:
    """The module at *path*, parsed.

    Raises:
        UnevaluableError: It cannot be read or parsed.
    """
    try:
        return ast.parse(path.read_bytes(), filename=str(path))
    except (OSError, SyntaxError, ValueError) as exc:
        raise UnevaluableError(f"{path} cannot be parsed ({exc})") from exc


def _is_fixture_decorator(decorator: ast.expr) -> bool:
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    if isinstance(target, ast.Attribute):
        return target.attr == _FIXTURE_DECORATOR
    return isinstance(target, ast.Name) and target.id == _FIXTURE_DECORATOR


def _returned_expression(function: ast.FunctionDef) -> ast.expr | None:
    body = function.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    if len(body) == 1 and isinstance(body[0], ast.Return) and body[0].value is not None:
        return body[0].value
    return None


def _fixture_function(tree: ast.Module, name: str) -> ast.FunctionDef | None:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            if any(_is_fixture_decorator(decorator) for decorator in node.decorator_list):
                return node
    return None


class StaticEvaluator:
    """Evaluates path expressions of the test modules of one workspace; parsed scopes are kept."""

    def __init__(self) -> None:
        self._scopes: dict[Path, ModuleScope] = {}

    def scope(self, path: Path, tests_root: Path, tree: ast.Module | None = None) -> ModuleScope:
        """The scope of the module at *path* (parsed now unless *tree* is given)."""
        if path not in self._scopes:
            parsed = tree if tree is not None else parse_module_file(path)
            self._scopes[path] = module_scope(path, tests_root, parsed)
        return self._scopes[path]

    def evaluate(
        self, expression: ast.expr, scope: ModuleScope, local: Mapping[str, ast.expr] | None = None, depth: int = 0
    ) -> Value:
        """The value of *expression* in *scope*, with *local* the enclosing function's single bindings.

        Raises:
            UnevaluableError: Some part of the expression cannot be followed from the text.
        """
        if depth > _MAX_DEPTH:
            raise UnevaluableError(f"{ast.unparse(expression)} nests deeper than {_MAX_DEPTH} steps")
        handler = _HANDLERS.get(type(expression))
        if handler is None:
            raise UnevaluableError(f"{ast.unparse(expression)} is a {type(expression).__name__}, which is not followed")
        return handler(self, expression, scope, local or {}, depth + 1)

    def path(self, expression: ast.expr, scope: ModuleScope, local: Mapping[str, ast.expr] | None = None) -> Path:
        """*expression* evaluated to a path.

        Raises:
            UnevaluableError: It cannot be evaluated, or is no path.
        """
        value = self.evaluate(expression, scope, local)
        if not isinstance(value, PurePath):
            raise UnevaluableError(f"{ast.unparse(expression)} evaluates to {value!r}, not a path")
        return Path(value)

    def name(self, name: str, scope: ModuleScope, local: Mapping[str, ast.expr], depth: int) -> Value:
        """The value *name* holds in *scope* (``__file__``, a local or module binding, an import, a fixture)."""
        if name == _FILE_NAME:
            return scope.path
        if name in local:
            return self.evaluate(local[name], scope, {}, depth)
        if name in scope.bindings:
            return self.evaluate(scope.bindings[name], scope, {}, depth)
        if name in scope.imports:
            module, level, attribute = scope.imports[name]
            return self._imported(scope, module, level, attribute, depth)
        return self._fixture(name, scope, depth)

    def _imported(self, scope: ModuleScope, module: str, level: int, attribute: str, depth: int) -> Value:
        local_file = _tests_module_file(scope, module, level)
        if local_file is not None:
            if not attribute:
                raise UnevaluableError(f"module {module} of the tests tree is imported whole; its names are not followed")
            return self.name(attribute, self.scope(local_file, scope.tests_root), {}, depth)
        if level > 0:
            raise UnevaluableError(f"relative import of {attribute} from {'.' * level}{module} names no module file")
        loaded = _installed_module(module)
        if not attribute:
            return loaded
        if hasattr(loaded, attribute):
            value: Value = getattr(loaded, attribute)
            return value
        return _installed_module(f"{module}.{attribute}")

    def _fixture(self, name: str, scope: ModuleScope, depth: int) -> Value:
        for candidate in _fixture_files(scope):
            fixture_scope = self.scope(candidate, scope.tests_root)
            function = _fixture_function(fixture_scope.tree, name)
            if function is None:
                continue
            returned = _returned_expression(function)
            if function.args.args or returned is None:
                raise UnevaluableError(
                    f"fixture {name} ({candidate}:{function.lineno}) takes parameters or is not one return"
                )
            return self.evaluate(returned, fixture_scope, {}, depth)
        raise UnevaluableError(f"{name} is bound by no single assignment, import or fixture the text shows")


def _tests_module_file(scope: ModuleScope, module: str, level: int) -> Path | None:
    """The file of *module* (imported at *level*) when it is a module of *scope*'s ``tests/`` tree."""
    parts = [part for part in module.split(".") if part]
    if not parts:
        return None
    bases = [scope.path.parents[level - 1]] if level > 0 else [scope.tests_root.parent, scope.path.parent, scope.tests_root]
    root = scope.tests_root.resolve()
    for base in bases:
        stem = base.joinpath(*parts)
        for candidate in (stem.with_name(stem.name + _PYTHON_SUFFIX), stem / _PACKAGE_INIT):
            if candidate.is_file() and candidate.resolve().is_relative_to(root):
                return candidate
    return None


def _fixture_files(scope: ModuleScope) -> list[Path]:
    """The module itself, then each ``conftest.py`` from its directory up to its ``tests/`` root."""
    found = [scope.path]
    for directory in [scope.path.parent, *scope.path.parent.parents]:
        conftest = directory / _CONFTEST
        if conftest.is_file() and conftest != scope.path:
            found.append(conftest)
        if directory == scope.tests_root:
            break
    return found


def _installed_module(module: str) -> ModuleType:
    try:
        loaded = importlib.import_module(module)
    except ImportError as exc:
        raise UnevaluableError(f"module {module} does not import ({exc})") from exc
    origin = getattr(loaded, "__file__", None)
    if origin is not None and _TESTS_DIR in Path(origin).parts:
        raise UnevaluableError(f"module {module} lies under a tests/ tree; a test module is never run to read a name")
    return loaded


def _evaluate_constant(
    evaluator: StaticEvaluator, node: ast.expr, scope: ModuleScope, local: Mapping[str, ast.expr], depth: int
) -> Value:
    assert isinstance(node, ast.Constant)
    if isinstance(node.value, (str, int)) and not isinstance(node.value, bool):
        return node.value
    raise UnevaluableError(f"constant {node.value!r} is no text or index")


def _text(value: Value, expression: ast.expr) -> str:
    if isinstance(value, (str, int, PurePath)):
        return str(value)
    raise UnevaluableError(f"{ast.unparse(expression)} evaluates to {type(value).__name__}, not text")


def _evaluate_joined(
    evaluator: StaticEvaluator, node: ast.expr, scope: ModuleScope, local: Mapping[str, ast.expr], depth: int
) -> Value:
    assert isinstance(node, ast.JoinedStr)
    parts: list[str] = []
    for part in node.values:
        if isinstance(part, ast.Constant):
            parts.append(str(part.value))
        elif isinstance(part, ast.FormattedValue) and part.format_spec is None and part.conversion == -1:
            parts.append(_text(evaluator.evaluate(part.value, scope, local, depth), part.value))
        else:
            raise UnevaluableError(f"{ast.unparse(node)} formats with a conversion or a format spec")
    return "".join(parts)


def _evaluate_name(
    evaluator: StaticEvaluator, node: ast.expr, scope: ModuleScope, local: Mapping[str, ast.expr], depth: int
) -> Value:
    assert isinstance(node, ast.Name)
    return evaluator.name(node.id, scope, local, depth)


def _evaluate_attribute(
    evaluator: StaticEvaluator, node: ast.expr, scope: ModuleScope, local: Mapping[str, ast.expr], depth: int
) -> Value:
    assert isinstance(node, ast.Attribute)
    base = evaluator.evaluate(node.value, scope, local, depth)
    if isinstance(base, PurePath):
        if node.attr not in _PATH_ATTRIBUTES:
            raise UnevaluableError(f"{ast.unparse(node)} reads path attribute {node.attr}, which is not followed")
        value: Value = getattr(base, node.attr)
        return value
    if isinstance(base, (str, int)) or not hasattr(base, node.attr):
        raise UnevaluableError(f"{ast.unparse(node)}: {type(base).__name__} has no attribute {node.attr} to read")
    found: Value = getattr(base, node.attr)
    return found


def _evaluate_subscript(
    evaluator: StaticEvaluator, node: ast.expr, scope: ModuleScope, local: Mapping[str, ast.expr], depth: int
) -> Value:
    assert isinstance(node, ast.Subscript)
    if not (isinstance(node.value, ast.Attribute) and node.value.attr == "parents"):
        raise UnevaluableError(f"{ast.unparse(node)} indexes something other than .parents")
    base = evaluator.evaluate(node.value.value, scope, local, depth)
    index = evaluator.evaluate(node.slice, scope, local, depth)
    if not isinstance(base, PurePath) or not isinstance(index, int):
        raise UnevaluableError(f"{ast.unparse(node)} is no path's parents[<index>]")
    if index >= len(base.parents):
        raise UnevaluableError(f"{ast.unparse(node)}: {base} has only {len(base.parents)} parents")
    return base.parents[index]


def _evaluate_binary(
    evaluator: StaticEvaluator, node: ast.expr, scope: ModuleScope, local: Mapping[str, ast.expr], depth: int
) -> Value:
    assert isinstance(node, ast.BinOp)
    left = evaluator.evaluate(node.left, scope, local, depth)
    right = evaluator.evaluate(node.right, scope, local, depth)
    if isinstance(node.op, ast.Div) and isinstance(left, PurePath) and isinstance(right, (str, PurePath)):
        return left / right
    if isinstance(node.op, ast.Add) and isinstance(left, str) and isinstance(right, str):
        return left + right
    raise UnevaluableError(f"{ast.unparse(node)} combines {type(left).__name__} and {type(right).__name__}")


def _arguments(
    evaluator: StaticEvaluator, node: ast.Call, scope: ModuleScope, local: Mapping[str, ast.expr], depth: int
) -> tuple[list[Value], dict[str, Value]]:
    if any(isinstance(argument, ast.Starred) for argument in node.args) or any(k.arg is None for k in node.keywords):
        raise UnevaluableError(f"{ast.unparse(node)} unpacks its arguments")
    positional = [evaluator.evaluate(argument, scope, local, depth) for argument in node.args]
    named = {str(keyword.arg): evaluator.evaluate(keyword.value, scope, local, depth) for keyword in node.keywords}
    return positional, named


def _path_method(base: PurePath, method: str, positional: Sequence[Value], node: ast.Call) -> Value:
    texts = [_text(value, node) for value in positional]
    if method in _NO_ARGUMENT_METHODS and not texts:
        return Path(base).resolve() if method == "resolve" else Path(base).absolute()
    if method == "joinpath":
        return base.joinpath(*texts)
    if method in _ONE_ARGUMENT_METHODS and len(texts) == 1:
        return base.with_name(texts[0]) if method == "with_name" else base.with_suffix(texts[0])
    raise UnevaluableError(f"{ast.unparse(node)} calls path method {method}, which is not followed")


def _callee_name(function: ast.expr) -> str:
    if isinstance(function, ast.Attribute):
        return function.attr
    return function.id if isinstance(function, ast.Name) else ""


def _evaluate_call(
    evaluator: StaticEvaluator, node: ast.expr, scope: ModuleScope, local: Mapping[str, ast.expr], depth: int
) -> Value:
    assert isinstance(node, ast.Call)
    positional, named = _arguments(evaluator, node, scope, local, depth)
    function = node.func
    callee = _callee_name(function)
    if isinstance(function, ast.Attribute) and callee not in _PATH_TYPES:
        receiver = evaluator.evaluate(function.value, scope, local, depth)
        if isinstance(receiver, PurePath) and not named:
            return _path_method(receiver, function.attr, positional, node)
    if callee in _PATH_TYPES and not named:
        return Path(*[_text(value, node) for value in positional])
    if callee == _STR_CALL and len(positional) == 1 and not named:
        return _text(positional[0], node)
    target = evaluator.evaluate(function, scope, local, depth)
    if isinstance(target, type):
        built: Value = target(*positional, **named)
        return built
    raise UnevaluableError(f"{ast.unparse(node)} calls something other than a path, str() or an installed class")


_Handler = Callable[[StaticEvaluator, ast.expr, ModuleScope, Mapping[str, ast.expr], int], Value]
_HANDLERS: Final[Mapping[type[ast.expr], _Handler]] = {
    ast.Constant: _evaluate_constant,
    ast.JoinedStr: _evaluate_joined,
    ast.Name: _evaluate_name,
    ast.Attribute: _evaluate_attribute,
    ast.Subscript: _evaluate_subscript,
    ast.BinOp: _evaluate_binary,
    ast.Call: _evaluate_call,
}
