"""
Replace a module constant by its string literal in every module importing it, and drop it from
their imports (the name goes from the statement; a statement left with no name goes whole). An
import nothing reads any more goes too. The value comes from the constant itself, so it is never
retyped; a name only inside a plain string is not a use and stays.

A module the recipe cannot rewrite safely is left unchanged and listed as REFUSED <file>:<line>: a
use inside an f-string (the literal would need its quotes checked: edit it by hand, then run again),
an aliased import or one from another module, an import sharing its line, a module rebinding the
name, an attribute read of it, a read with no import. A module holding the name that the parser
could not read is listed the same way. Anything listed makes the exit code 1.

Usage:
  run-codemod.ps1 14_inline_constant MODULE NAME [paths...]
  bowler run scripts/codemods/lib/14_inline_constant.py -- my_pkg.names SYSTEM_FILE my-pkg/tests

Previews a diff; run-codemod -Write writes it.
"""

from __future__ import annotations

import ast
import importlib
import json
import os
import re
import symtable
import sys
from collections.abc import Iterator
from pathlib import Path

from bowler import Query
from bowler.types import LN, SYMBOL, TOKEN, Capture, Filename, Leaf

from _shared import finish

_MIN_ARGS = 2
_FSTRING_PREFIX = re.compile(r"^[A-Za-z]*[fF][A-Za-z]*['\"]")


def _constant_literal(module: str, name: str) -> str:
    """The source text of the string constant *module*.*name*; exits when it is absent or no string."""
    value = getattr(importlib.import_module(module), name, None)
    if not isinstance(value, str):
        raise SystemExit(f"{module}.{name} is not a string constant: {value!r}")
    return json.dumps(value, ensure_ascii=False)


def _enclosing_import(leaf: Leaf) -> LN | None:
    """The import statement holding *leaf*, or None."""
    node = leaf.parent
    while node is not None:
        if node.type in (SYMBOL.import_from, SYMBOL.import_name):
            return node
        node = node.parent
    return None


def _imported_module(statement: LN) -> str:
    """The dotted module a ``from`` statement names, with its leading dots."""
    words: list[str] = []
    for child in statement.children[1:]:
        if child.type == TOKEN.NAME and child.value == "import":
            break
        words.append(str(child).strip())
    return "".join(words)


def _is_imported_name(leaf: Leaf, statement: LN, module: str) -> bool:
    """True when *leaf* is a plain name of ``from <module> import ...`` (no alias)."""
    return (
        statement.type == SYMBOL.import_from
        and _imported_module(statement) == module
        and (leaf.parent is statement or leaf.parent.type == SYMBOL.import_as_names)
    )


def _is_keyword_of_call(leaf: Leaf) -> bool:
    """True when *leaf* is the keyword of ``f(<leaf>=value)``: a parameter's name, not a read."""
    parent = leaf.parent
    return parent.type == SYMBOL.argument and parent.children[0] is leaf and parent.children[1].type == TOKEN.EQUAL


def _reads_in_fstring(leaf: Leaf, name: str) -> bool:
    """True when the f-string *leaf* reads *name* in a replacement field."""
    if not _FSTRING_PREFIX.match(leaf.value):
        return False
    return any(isinstance(node, ast.Name) and node.id == name for node in ast.walk(ast.parse(leaf.value, mode="eval")))


def _scopes(table: symtable.SymbolTable) -> Iterator[symtable.SymbolTable]:
    """*table* and every scope nested in it."""
    yield table
    for child in table.get_children():
        yield from _scopes(child)


def _rebinding_scope(source: str, name: str) -> symtable.SymbolTable | None:
    """The first scope of *source* binding *name* other than by import, or None."""
    for scope in _scopes(symtable.symtable(source, "<module>", "exec")):
        if name in scope.get_identifiers():
            symbol = scope.lookup(name)
            if symbol.is_assigned() or symbol.is_parameter() or symbol.is_namespace():
                return scope
    return None


def _drop_statement(statement: LN) -> None:
    """Remove the ``simple_stmt`` *statement*; its comments and its blank-line separation stay for what follows."""
    following = statement.next_sibling
    prefix = statement.prefix
    if statement.prev_sibling is None or statement.prev_sibling.type == TOKEN.INDENT:
        # What comes first in a file or block has no blank line above it, and a block's INDENT token already
        # holds its indentation.
        following.prefix = prefix.rstrip(" \t") + following.prefix.lstrip()
    elif "#" in prefix or "\n" not in following.prefix:
        following.prefix = prefix.rstrip(" \t") + following.prefix
    statement.remove()


def _drop_imported_name(leaf: Leaf) -> None:
    """Remove *leaf* from its import; a statement left with no name goes whole."""
    names = leaf.parent
    if names.type != SYMBOL.import_as_names or len([c for c in names.children if c.type != TOKEN.COMMA]) == 1:
        _drop_statement(_enclosing_import(leaf).parent)
        return
    comma = leaf.next_sibling
    if comma is None:
        leaf.prev_sibling.remove()
        leaf.remove()
        return
    following = comma.next_sibling or names.next_sibling
    # A comment trailing the removed name's line goes with it; a comment above the next name stays.
    following.prefix = "\n" + following.prefix.split("\n", 1)[1] if "\n" in following.prefix else leaf.prefix
    comma.remove()
    leaf.remove()


class _InlineConstant:
    """The Bowler modifier: inlines the constant in each module, and keeps what it refused and visited."""

    def __init__(self, module: str, name: str, literal: str) -> None:
        self.module = module
        self.name = name
        self.literal = literal
        self.refused: list[str] = []
        self.visited: set[str] = set()

    def _name_refusal(self, leaf: Leaf, statement: LN | None) -> str | None:
        """Why the name *leaf* (in the import *statement*, if any) cannot be rewritten, or None."""
        if statement is None:
            previous = leaf.prev_sibling
            return f"attribute read of {self.name}" if previous is not None and previous.type == TOKEN.DOT else None
        if not _is_imported_name(leaf, statement, self.module):
            return f"{self.name} is aliased or imported from elsewhere"
        if len(statement.parent.children) > 2:
            return "the import shares its line with other code"
        return None

    def _sites(self, root: LN) -> tuple[list[Leaf], list[Leaf], list[tuple[int, str]]]:
        """The names to drop from imports, the reads to inline, and each refused use as (line, reason)."""
        imports: list[Leaf] = []
        reads: list[Leaf] = []
        refusals: list[tuple[int, str]] = []
        for leaf in root.leaves():
            if leaf.type == TOKEN.STRING and _reads_in_fstring(leaf, self.name):
                refusals.append((leaf.get_lineno(), f"{self.name} is read inside an f-string"))
            if leaf.type != TOKEN.NAME or leaf.value != self.name or _is_keyword_of_call(leaf):
                continue
            statement = _enclosing_import(leaf)
            reason = self._name_refusal(leaf, statement)
            if reason is not None:
                refusals.append((leaf.get_lineno(), reason))
            elif statement is None:
                reads.append(leaf)
            else:
                imports.append(leaf)
        return imports, reads, refusals

    def __call__(self, node: LN, capture: Capture, filename: Filename) -> LN | None:
        self.visited.add(_file_key(filename))
        imports, reads, refusals = self._sites(node)
        if reads and not imports:
            refusals.append((reads[0].get_lineno(), f"{self.name} is read but not imported from {self.module}"))
        rebinding = _rebinding_scope(str(node), self.name)
        if rebinding is not None:
            refusals.append((rebinding.get_lineno(), f"{self.name} is rebound in {rebinding.get_name()}"))
        if refusals:
            self.refused.extend(f"REFUSED {filename}:{line}: {reason}" for line, reason in refusals)
            return None
        for leaf in reads:
            leaf.replace(Leaf(TOKEN.STRING, self.literal, prefix=leaf.prefix))
        for leaf in imports:
            _drop_imported_name(leaf)
        return None


def _file_key(filename: str) -> str:
    """One spelling of a file path, whichever way a path argument named it."""
    return os.path.normcase(os.path.abspath(filename))


def _python_files(paths: list[str]) -> Iterator[Path]:
    """The Python files Bowler reads under *paths*: named files, and walked ones outside dot-folders."""
    for path in paths:
        if os.path.isfile(path):
            yield Path(path)
            continue
        for folder, subfolders, files in os.walk(path):
            subfolders[:] = [sub for sub in subfolders if not sub.startswith(".")]
            yield from (Path(folder) / file for file in files if file.endswith(".py") and not file.startswith("."))


def _unread_files(paths: list[str], name: str, visited: set[str]) -> list[str]:
    """The files holding *name* that the modifier never saw: Bowler only logs a file it cannot parse."""
    word = re.compile(rb"\b" + re.escape(name.encode()) + rb"\b")
    return sorted(
        f"REFUSED {file}:1: {name} is in this file but the parser could not read it"
        for file in _python_files(paths)
        if _file_key(str(file)) not in visited and word.search(file.read_bytes())
    )


def main() -> None:
    if len(sys.argv) <= _MIN_ARGS:
        raise SystemExit("Usage: 14_inline_constant MODULE NAME [paths...]")
    module, name = sys.argv[1:3]
    paths = sys.argv[3:] or ["."]

    modifier = _InlineConstant(module, name, _constant_literal(module, name))
    query = finish(Query(*paths).select_root().modify(modifier))
    refused = modifier.refused + _unread_files(paths, name, modifier.visited)
    for line in refused:
        print(line, file=sys.stderr)
    if refused or query.retcode:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
