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

Two kinds of reference reach wherever their path leads: an ``include`` (the parser joins it to the
including file's directory) and a declaration's config path, the ``.dcfg`` a header names
(``system Shop('config/system.dcfg')``, joined to the project root by the config loader). Every other
reference is *confined*: its loader refuses a path leaving the project root (a ``.dcfg`` import, a seed
path, an asset or content path).
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from datrix_scripts.gates.ratchet.fixture_budget_gate import DCFG_KIND, DTRX_KIND, read_fixture, string_lexemes

#: A path literal: no blank, a suffix, never absolute.
_PATH_LITERAL: Final = re.compile(r"[A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]+)*\.[A-Za-z0-9]{1,8}")
_INCLUDE_BEFORE: Final = re.compile(r"(?<![\w-])include\s*['\"]$")
#: A declaration header's config argument: ``Name('`` (dotted names included) right before the literal.
_HEADER_ARGUMENT_BEFORE: Final = re.compile(r"(?<![\w.])[A-Za-z_][\w.]*\s*\(\s*['\"]$")
#: How far before a literal the ``include`` keyword or a header is looked for.
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
        base: The directory it resolves against (the source's own for ``FILE_RULE``; the project root
            found for ``PROJECT_RULE``).
        confined: Whether its loader refuses a path leaving *base*.
    """

    source: Path
    offset: int
    literal: str
    rule: str
    target: Path
    base: Path
    confined: bool


@dataclass(frozen=True)
class Resolution:
    """Where a path literal lands: the directory it resolved against, and the file it names."""

    base: Path
    target: Path


def _on_disk(path: Path) -> bool:
    return path.is_file()


def reference_rule(text: str, offset: int, kind: str) -> str:
    """The rule the literal at *offset* of fixture *text* (of *kind*) resolves by."""
    window = max(0, offset - _INCLUDE_WINDOW)
    if kind == SEED_KIND or _INCLUDE_BEFORE.search(text, window, offset) is not None:
        return FILE_RULE
    return PROJECT_RULE


def reference_confined(text: str, offset: int, kind: str, literal: str) -> bool:
    """Whether the loader of the literal at *offset* of fixture *text* (of *kind*) refuses a path leaving its
    base: every reference but a ``.dtrx`` include and a ``.dtrx`` header's ``.dcfg`` config argument."""
    if kind != DTRX_KIND:
        return True
    window = max(0, offset - _INCLUDE_WINDOW)
    if _INCLUDE_BEFORE.search(text, window, offset) is not None:
        return False
    return not (literal.endswith(DCFG_KIND) and _HEADER_ARGUMENT_BEFORE.search(text, window, offset) is not None)


def _search_bases(directory: Path, tree_root: Path, rule: str) -> list[Path]:
    if rule == FILE_RULE:
        return [directory]
    bases = [directory, *directory.parents]
    return [base for base in bases if base.is_relative_to(tree_root)]


def resolve_reference(
    source: Path,
    literal: str,
    rule: str,
    tree_root: Path,
    *,
    is_file: Callable[[Path], bool] = _on_disk,
    reach: Sequence[Path] = (),
) -> Resolution | None:
    """Where *literal*, written in *source*, lands under *tree_root* by *rule*; ``None`` when it names no file.

    A path leaving *tree_root* and every directory of *reach*, through ``..`` or a link, names nothing.
    *is_file* answers whether a path is a file (the disk by default; a tree whose copies have moved, when
    the moves are being proven before they are written).
    """
    if _PATH_LITERAL.fullmatch(literal) is None:
        return None
    roots = [tree_root.resolve(), *(directory.resolve() for directory in reach)]
    for base in _search_bases(source.parent, tree_root, rule):
        candidate = Path(os.path.normpath(base / literal))
        resolved = candidate.resolve()
        if any(resolved.is_relative_to(root) for root in roots) and is_file(candidate):
            return Resolution(base, candidate)
    return None


def fixture_references(path: Path, kind: str, tree_root: Path) -> list[Reference]:
    """The files the fixture at *path* (of *kind*, lying under *tree_root*) names, in text order."""
    text = read_fixture(path)
    found: list[Reference] = []
    for offset, literal in string_lexemes(text, kind):
        rule = reference_rule(text, offset, kind)
        resolution = resolve_reference(path, literal, rule, tree_root)
        if resolution is not None:
            confined = reference_confined(text, offset, kind, literal)
            found.append(Reference(path, offset, literal, rule, resolution.target, resolution.base, confined))
    return found


def named_files(
    path: Path,
    text: str,
    kind: str,
    tree_root: Path,
    *,
    is_file: Callable[[Path], bool],
    reach: Sequence[Path],
) -> tuple[Path, ...]:
    """The files fixture *text* (of *kind*), lying at *path* under *tree_root*, names in text order: each
    literal resolved by its rule over the tree *is_file* answers for, the directories of *reach* included."""
    found: list[Path] = []
    for offset, literal in string_lexemes(text, kind):
        rule = reference_rule(text, offset, kind)
        resolution = resolve_reference(path, literal, rule, tree_root, is_file=is_file, reach=reach)
        if resolution is not None:
            found.append(resolution.target)
    return tuple(found)
