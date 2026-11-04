"""The files a fixture names, resolved by the rules the language and the loaders apply.

A fixture names another file through a string literal:

* ``include '<path>'`` in a ``.dtrx`` resolves against the including file's directory (the parser's
  include rule);
* every path a ``.dseed`` names (``Entity from "x.csv"``, ``object "x" as "key"``) resolves against the
  ``.dseed``'s own directory (the seed file reader);
* every other path literal -- a declaration's config path, a ``.dcfg`` ``import``, an asset path -- resolves
  against the project root, the directory of the entry being read. A fixture does not record which entry
  reads it, so its root is the nearest directory, from the fixture's own up to its tree root, under which
  the literal names a file.

A literal that names no file under the tree root is no reference: it is a value (a route, a host, a key).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from datrix_scripts.gates.ratchet.fixture_budget_gate import read_fixture, string_lexemes

#: A path literal: no blank, a suffix, never absolute.
_PATH_LITERAL: Final = re.compile(r"[A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]+)*\.[A-Za-z0-9]{1,8}")
_INCLUDE_BEFORE: Final = re.compile(r"(?<![\w-])include\s*['\"]$")
#: How far before a literal the ``include`` keyword is looked for.
_INCLUDE_WINDOW: Final = 64
SEED_KIND: Final = ".dseed"
#: The rule a reference resolves by: against the naming file's directory, or against the project root.
FILE_RULE: Final = "file"
PROJECT_RULE: Final = "project"


@dataclass(frozen=True)
class Reference:
    """One file a fixture names.

    Attributes:
        source: The naming fixture.
        offset: Where the literal's value starts in the source text.
        literal: The literal as written.
        rule: ``FILE_RULE`` or ``PROJECT_RULE``.
        target: The file it resolves to.
    """

    source: Path
    offset: int
    literal: str
    rule: str
    target: Path


def reference_rule(text: str, offset: int, kind: str) -> str:
    """The rule the literal at *offset* of fixture *text* (of *kind*) resolves by."""
    window = max(0, offset - _INCLUDE_WINDOW)
    if kind == SEED_KIND or _INCLUDE_BEFORE.search(text, window, offset) is not None:
        return FILE_RULE
    return PROJECT_RULE


def _search_bases(directory: Path, tree_root: Path, rule: str) -> list[Path]:
    if rule == FILE_RULE:
        return [directory]
    bases = [directory, *directory.parents]
    return [base for base in bases if base.is_relative_to(tree_root)]


def resolve_literal(source: Path, literal: str, rule: str, tree_root: Path) -> Path | None:
    """The file *literal*, written in *source*, names under *tree_root* by *rule*; ``None`` when it names none.

    A path leaving *tree_root*, through ``..`` or a link, names nothing.
    """
    if _PATH_LITERAL.fullmatch(literal) is None:
        return None
    root = tree_root.resolve()
    for base in _search_bases(source.parent, tree_root, rule):
        candidate = Path(os.path.normpath(base / literal))
        if candidate.resolve().is_relative_to(root) and candidate.is_file():
            return candidate
    return None


def fixture_references(path: Path, kind: str, tree_root: Path) -> list[Reference]:
    """The files the fixture at *path* (of *kind*, lying under *tree_root*) names, in text order."""
    text = read_fixture(path)
    found: list[Reference] = []
    for offset, literal in string_lexemes(text, kind):
        rule = reference_rule(text, offset, kind)
        target = resolve_literal(path, literal, rule, tree_root)
        if target is not None:
            found.append(Reference(path, offset, literal, rule, target))
    return found
