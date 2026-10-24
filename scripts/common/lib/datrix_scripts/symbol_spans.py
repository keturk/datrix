"""Where each function, class and module/class-level variable of a Python file sits, for the ``datrix-edit`` MCP server.

``read_symbol`` and the symbol edits of ``edit_lines`` (``datrix_scripts.line_edits``) name a symbol
by its dotted name (``Class.method``) instead of by line numbers. This module turns a file's lines
into the line span of every symbol, using the standard ``ast`` module, so a name always means what
the parser says it means.

A span runs from the first decorator (or the ``def``/``class``/assignment line) to the symbol's last
line, widened upward over the comment lines directly above it (no blank line between), which belong
to the symbol. Definitions inside ``if``/``try``/``with``/``for``/``while`` blocks belong to the
enclosing scope. Variables are listed only at module and class level, never inside a function.

Also imported by the Claude Code hook that runs the edit guards over an ``edit_lines`` call (through
``datrix_scripts.line_edits``), so this module imports nothing beyond the standard library.
"""

from __future__ import annotations

import ast
import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

SPAN_HASH_CHARS: Final = 8
MAX_LISTED_SYMBOLS: Final = 40
PYTHON_SUFFIX: Final = ".py"
PIN_SEPARATOR: Final = "@"

_DEFINITIONS: Final = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
_BLOCK_STATEMENTS: Final = (ast.If, ast.Try, ast.TryStar, ast.With, ast.AsyncWith, ast.For, ast.AsyncFor, ast.While)


class SymbolError(ValueError):
    """A symbol cannot be found or its file cannot be parsed; the message says what to send instead."""


@dataclass(frozen=True)
class SymbolSpan:
    """One symbol's dotted name, kind and 1-based inclusive line range."""

    qualname: str
    kind: str
    start: int
    end: int


def span_hash(texts: Sequence[str]) -> str:
    """The short hash of a symbol's lines that a symbol edit names it by (line texts, no endings)."""
    return hashlib.sha1("\n".join(texts).encode("utf-8")).hexdigest()[:SPAN_HASH_CHARS]


def _kind(node: ast.stmt) -> str:
    if isinstance(node, ast.ClassDef):
        return "class"
    if isinstance(node, ast.AsyncFunctionDef):
        return "async def"
    if isinstance(node, ast.FunctionDef):
        return "def"
    return "variable"


def _sub_blocks(node: ast.stmt) -> list[list[ast.stmt]]:
    """The statement lists a block statement holds (body, else, finally, handlers)."""
    blocks: list[list[ast.stmt]] = [getattr(node, "body", []), getattr(node, "orelse", []),
                                    getattr(node, "finalbody", [])]
    blocks.extend(handler.body for handler in getattr(node, "handlers", []))
    return [block for block in blocks if block]


def _first_line(node: ast.stmt, lines: Sequence[str]) -> int:
    first = min([node.lineno, *(decorator.lineno for decorator in getattr(node, "decorator_list", []))])
    while first > 1 and lines[first - 2].lstrip().startswith("#"):
        first -= 1
    return first


def _variable_names(node: ast.stmt) -> list[str]:
    if isinstance(node, ast.Assign):
        return [target.id for target in node.targets if isinstance(target, ast.Name)]
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return [node.target.id]
    return []


def _collect(body: Sequence[ast.stmt], prefix: str, variables: bool, lines: Sequence[str],
             spans: list[SymbolSpan]) -> None:
    for node in body:
        if isinstance(node, _DEFINITIONS):
            qualname = prefix + node.name
            spans.append(SymbolSpan(qualname, _kind(node), _first_line(node, lines), node.end_lineno or node.lineno))
            _collect(node.body, qualname + ".", variables and isinstance(node, ast.ClassDef), lines, spans)
        elif isinstance(node, _BLOCK_STATEMENTS):
            for block in _sub_blocks(node):
                _collect(block, prefix, variables, lines, spans)
        elif variables:
            for name in _variable_names(node):
                spans.append(SymbolSpan(prefix + name, "variable", _first_line(node, lines),
                                        node.end_lineno or node.lineno))


def find_spans(shown: str, lines: Sequence[str]) -> list[SymbolSpan]:
    """Every symbol of a Python file given as its line texts, in source order."""
    if not shown.endswith(PYTHON_SUFFIX):
        raise SymbolError(f"{shown}: symbol reads and edits work on Python ({PYTHON_SUFFIX}) files only; "
                          "use read_lines and edit_lines with line numbers for other files.")
    if any("\r" in line for line in lines):
        raise SymbolError(f"{shown} has a lone carriage return inside a line, so the parser's line numbers would "
                          "differ from the file's; use read_lines and edit_lines with line numbers for it.")
    try:
        tree = ast.parse("\n".join(lines) + "\n")
    except SyntaxError as exc:
        raise SymbolError(f"{shown} does not parse (line {exc.lineno}: {exc.msg}), so its symbols cannot be "
                          "located; use read_lines and edit_lines with line numbers for it.") from exc
    spans: list[SymbolSpan] = []
    _collect(tree.body, "", True, lines, spans)
    return sorted(spans, key=lambda span: (span.start, span.end))


def _unknown_symbol(shown: str, name: str, spans: Sequence[SymbolSpan]) -> SymbolError:
    names = list(dict.fromkeys(span.qualname for span in spans))
    listed = ", ".join(names[:MAX_LISTED_SYMBOLS]) + (
        f", ...(+{len(names) - MAX_LISTED_SYMBOLS})" if len(names) > MAX_LISTED_SYMBOLS else "")
    return SymbolError(f"{shown} has no symbol {name!r}. Name a function, class or module/class-level variable by "
                       f"its dotted name (Class.method). Symbols there: {listed or 'none'}.")


def _pinned_start(shown: str, symbol: str, pin: str) -> int:
    if not pin.isdecimal():
        raise SymbolError(f"{shown}: in {symbol!r} the text after '{PIN_SEPARATOR}' must be the symbol's first line "
                          f"number, e.g. 'name{PIN_SEPARATOR}120'.")
    return int(pin)


def select_span(shown: str, spans: Sequence[SymbolSpan], symbol: str) -> SymbolSpan:
    """The one span ``symbol`` names: ``a.b`` or, when the name is defined twice, ``a.b@<first line>``."""
    name, separator, pin = symbol.strip().partition(PIN_SEPARATOR)
    matches = [span for span in spans if span.qualname == name]
    if separator:
        start = _pinned_start(shown, symbol, pin)
        matches = [span for span in matches if span.start == start]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise _unknown_symbol(shown, name, spans)
    choices = ", ".join(f"{span.qualname}{PIN_SEPARATOR}{span.start} (lines {span.start}-{span.end})"
                        for span in matches)
    raise SymbolError(f"{shown}: {name!r} is defined more than once; name one of: {choices}.")
