"""What one Python file defines, imports and references, read from its syntax tree.

Runs in worker processes during a large refresh, so everything here is a pure function
of its arguments and returns plain picklable data.
"""

from __future__ import annotations

import ast
import builtins
import re
from dataclasses import dataclass

from datrix_scripts.logic_map import Marker, parse_markers

SYMBOL_CLASS = "class"
SYMBOL_FUNCTION = "function"
SYMBOL_METHOD = "method"
SYMBOL_VARIABLE = "variable"
SYMBOL_ATTRIBUTE = "attribute"

# How a name is used at a reference site. A call through a bare name and a call through
# an attribute are kept apart: a bare-name call can be resolved through the file's
# imports, a method call cannot be resolved without the receiver's type.
REF_NAME = "name"
REF_CALL = "call"
REF_ATTR = "attr"
REF_ATTR_CALL = "attr_call"

# Names that are never worth recording as references: every builtin, and the receiver
# parameters every method has.
_IGNORED_NAMES = frozenset(dir(builtins)) | {"self", "cls"}

MAX_SIGNATURE_CHARS = 300
MAX_DOC_CHARS = 300
MAX_VALUE_CHARS = 80

_WHITESPACE = re.compile(r"\s+")

_DEFINITIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
_ASSIGNMENTS = (ast.Assign, ast.AnnAssign)


@dataclass(frozen=True)
class SymbolFact:
    name: str
    qualname: str
    kind: str
    line: int
    end_line: int
    signature: str
    doc: str


@dataclass(frozen=True)
class ImportFact:
    """One imported name. ``module`` is absolute; ``name`` is empty for ``import module``."""

    module: str
    name: str
    alias: str
    line: int

    @property
    def bound_name(self) -> str:
        """The name the import binds in the importing file."""
        if self.alias:
            return self.alias
        return self.name or self.module.split(".", 1)[0]


@dataclass(frozen=True)
class RefFact:
    name: str
    kind: str
    lines: tuple[int, ...]


@dataclass(frozen=True)
class FileFacts:
    module_doc: str
    line_count: int
    symbols: tuple[SymbolFact, ...]
    imports: tuple[ImportFact, ...]
    refs: tuple[RefFact, ...]
    markers: tuple[Marker, ...]
    # Empty when the file parsed; otherwise the syntax error, and symbols/imports/refs are empty.
    parse_error: str


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 3] + "..."


def first_paragraph(docstring: str | None) -> str:
    """The docstring's first paragraph on one line, clipped."""
    if not docstring:
        return ""
    paragraph = docstring.strip().split("\n\n", 1)[0]
    return _clip(_WHITESPACE.sub(" ", paragraph).strip(), MAX_DOC_CHARS)


def _decorators(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> str:
    return "".join(f"@{ast.unparse(d)} " for d in node.decorator_list)


def _function_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    returns = f" -> {ast.unparse(node.returns)}" if node.returns is not None else ""
    return f"{_decorators(node)}{prefix} {node.name}({ast.unparse(node.args)}){returns}"


def _class_signature(node: ast.ClassDef) -> str:
    bases = [ast.unparse(b) for b in node.bases] + [ast.unparse(k) for k in node.keywords]
    inherits = f"({', '.join(bases)})" if bases else ""
    return f"{_decorators(node)}class {node.name}{inherits}"


def _assignment_signature(name: str, node: ast.Assign | ast.AnnAssign) -> str:
    annotation = f": {ast.unparse(node.annotation)}" if isinstance(node, ast.AnnAssign) else ""
    value = f" = {_clip(ast.unparse(node.value), MAX_VALUE_CHARS)}" if node.value is not None else ""
    return f"{name}{annotation}{value}"


def _assigned_names(node: ast.Assign | ast.AnnAssign) -> list[str]:
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    return [t.id for t in targets if isinstance(t, ast.Name)]


class _SymbolCollector:
    """Walks definitions scope by scope, keeping each symbol's qualified name."""

    def __init__(self) -> None:
        self.symbols: list[SymbolFact] = []

    def scope(self, body: list[ast.stmt], prefix: str, in_class: bool, in_function: bool) -> None:
        for node in body:
            if isinstance(node, _DEFINITIONS):
                self._definition(node, prefix, in_class)
            elif isinstance(node, _ASSIGNMENTS) and not in_function:
                self._assignment(node, prefix, in_class)
            else:
                # Definitions inside if/try/with/for blocks (TYPE_CHECKING imports,
                # platform branches) belong to the enclosing scope.
                for child_body in _nested_bodies(node):
                    self.scope(child_body, prefix, in_class, in_function)

    def _definition(self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef, prefix: str,
                    in_class: bool) -> None:
        qualname = f"{prefix}{node.name}"
        if isinstance(node, ast.ClassDef):
            kind, signature = SYMBOL_CLASS, _class_signature(node)
        else:
            kind = SYMBOL_METHOD if in_class else SYMBOL_FUNCTION
            signature = _function_signature(node)
        self.symbols.append(SymbolFact(
            name=node.name, qualname=qualname, kind=kind, line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            signature=_clip(signature, MAX_SIGNATURE_CHARS), doc=first_paragraph(ast.get_docstring(node)),
        ))
        is_class = isinstance(node, ast.ClassDef)
        self.scope(node.body, f"{qualname}.", in_class=is_class, in_function=not is_class)

    def _assignment(self, node: ast.Assign | ast.AnnAssign, prefix: str, in_class: bool) -> None:
        kind = SYMBOL_ATTRIBUTE if in_class else SYMBOL_VARIABLE
        for name in _assigned_names(node):
            self.symbols.append(SymbolFact(
                name=name, qualname=f"{prefix}{name}", kind=kind, line=node.lineno,
                end_line=node.end_lineno or node.lineno,
                signature=_clip(_assignment_signature(name, node), MAX_SIGNATURE_CHARS), doc="",
            ))


def _nested_bodies(node: ast.stmt) -> list[list[ast.stmt]]:
    bodies: list[list[ast.stmt]] = []
    for field in ("body", "orelse", "finalbody"):
        value = getattr(node, field, None)
        if isinstance(value, list) and value and isinstance(value[0], ast.stmt):
            bodies.append(value)
    bodies.extend(handler.body for handler in getattr(node, "handlers", ()))
    bodies.extend(case.body for case in getattr(node, "cases", ()))
    return bodies


def _resolve_relative(module: str, is_package: bool, level: int, target: str | None) -> str:
    """The absolute module a ``from ... import`` names, resolved against ``module``."""
    package = module if is_package else module.rpartition(".")[0]
    parts = package.split(".") if package else []
    base = parts[: len(parts) - (level - 1)] if level > 1 else parts
    return ".".join([*base, target] if target else base)


def _imports(tree: ast.Module, module: str, is_package: bool) -> list[ImportFact]:
    facts: list[ImportFact] = []
    for node in ast.walk(tree):
        # Each imported name carries its own line, which differs from the statement's in a
        # parenthesized multi-line import.
        if isinstance(node, ast.Import):
            facts.extend(ImportFact(a.name, "", a.asname or "", a.lineno) for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            source = (
                _resolve_relative(module, is_package, node.level, node.module)
                if node.level else node.module or ""
            )
            facts.extend(ImportFact(source, a.name, a.asname or "", a.lineno) for a in node.names)
    return facts


def _references(tree: ast.Module) -> list[RefFact]:
    called = {id(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)}
    sites: dict[tuple[str, str], set[int]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id not in _IGNORED_NAMES:
            key = (node.id, REF_CALL if id(node) in called else REF_NAME)
        elif isinstance(node, ast.Attribute):
            key = (node.attr, REF_ATTR_CALL if id(node) in called else REF_ATTR)
        else:
            continue
        sites.setdefault(key, set()).add(node.lineno)
    return [RefFact(name, kind, tuple(sorted(lines))) for (name, kind), lines in sorted(sites.items())]


def extract_file(data: bytes, rel_path: str, module: str, is_package: bool) -> FileFacts:
    """Everything the index records about one file's content."""
    text = data.decode("utf-8-sig", errors="replace")
    lines = text.splitlines()
    markers = tuple(parse_markers(lines, rel_path))
    try:
        tree = ast.parse(data, filename=rel_path)
    except (SyntaxError, ValueError) as exc:
        return FileFacts("", len(lines), (), (), (), markers, f"{type(exc).__name__}: {exc}")
    collector = _SymbolCollector()
    collector.scope(tree.body, "", in_class=False, in_function=False)
    return FileFacts(
        module_doc=first_paragraph(ast.get_docstring(tree)),
        line_count=len(lines),
        symbols=tuple(collector.symbols),
        imports=tuple(_imports(tree, module, is_package)),
        refs=tuple(_references(tree)),
        markers=markers,
        parse_error="",
    )


def extract_job(job: tuple[bytes, str, str, bool]) -> FileFacts:
    """``extract_file`` for a process pool, which maps over single arguments."""
    return extract_file(*job)
