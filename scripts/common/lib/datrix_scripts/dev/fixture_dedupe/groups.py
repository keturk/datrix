"""The groups of one fixture: files, and inline literals.

Two fixture files are one when their normalized content is equal (the budget gate's ``normalized``) and
every reference each makes (``references``) resolves to files that are one, recursively. A referenced file
of no fixture kind (a ``.csv``, an image) is one with another when their bytes are equal. A file reached
again while its own identity is being decided stands for its position on that chain, so a cycle compares
by shape.

Two inline literals are one when their normalized text is equal; a literal's kind is the fixture kind its
text is written in (``fixture_text_kind``). Only plain string constants are grouped: an f-string's text is
not its value.
"""

from __future__ import annotations

import ast
import hashlib
from collections import defaultdict
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from datrix_scripts.dev.fixture_dedupe.references import fixture_references
from datrix_scripts.gates.ratchet.fixture_budget_gate import (
    FixtureFile,
    duplicate_groups,
    fixture_kind,
    fixture_text_kind,
    is_fixture,
    literal_modules,
    normalized,
    parse_module,
    read_fixture,
    string_literals,
)

_SEPARATOR: Final = "\x1f"
_CYCLE: Final = "cycle"


@dataclass(frozen=True)
class FileGroup:
    """Two or more fixture files that are one fixture, in path order."""

    kind: str
    members: tuple[FixtureFile, ...]


@dataclass(frozen=True)
class SplitGroup:
    """Files of equal normalized content that are not one fixture: their references differ."""

    kind: str
    members: tuple[FixtureFile, ...]
    parts: tuple[tuple[Path, ...], ...]


@dataclass(frozen=True)
class LiteralSite:
    """One inline fixture literal.

    Attributes:
        module: The module holding it.
        line: Its first line.
        column: Its column on that line.
        name: The one name it is assigned to (``NAME = "..."``), else ``None``.
        text: Its text.
        scope: The dotted name of the class or function it lies in (``Test.test_x``); empty at module level.
    """

    module: Path
    line: int
    column: int
    name: str | None
    text: str
    scope: str = ""


@dataclass(frozen=True)
class LiteralGroup:
    """Two or more inline literals of one kind whose normalized text is equal, in module and line order."""

    kind: str
    members: tuple[LiteralSite, ...]


class FixtureIdentity:
    """The recursive identity of fixture files: equal keys are one fixture."""

    def __init__(self, tree_root_of: Callable[[Path], Path]) -> None:
        self._tree_root_of = tree_root_of
        self._known: dict[Path, str] = {}
        self._chain: list[Path] = []
        self._cyclic = False

    def key(self, path: Path) -> str:
        """The identity key of the file at *path*."""
        if path in self._known:
            return self._known[path]
        if path in self._chain:
            self._cyclic = True
            return f"{_CYCLE}:{len(self._chain) - self._chain.index(path)}"
        outer_cyclic, self._cyclic = self._cyclic, False
        self._chain.append(path)
        try:
            key = self._compute(path)
        finally:
            self._chain.pop()
        if not self._cyclic:
            self._known[path] = key
        self._cyclic = self._cyclic or outer_cyclic
        return key

    def _compute(self, path: Path) -> str:
        if not is_fixture(path.name):
            return hashlib.sha256(path.read_bytes()).hexdigest()
        kind = fixture_kind(path.name)
        parts = [kind, normalized(read_fixture(path), kind)]
        for reference in fixture_references(path, kind, self._tree_root_of(path)):
            parts.append(f"{reference.rule}:{reference.literal}={self.key(reference.target)}")
        return hashlib.sha256(_SEPARATOR.join(parts).encode("utf-8", errors="surrogateescape")).hexdigest()


def file_groups(
    files: Sequence[FixtureFile], tree_root_of: Callable[[Path], Path]
) -> tuple[list[FileGroup], list[SplitGroup]]:
    """The groups of one fixture among *files*, and the normalized-equal groups their references split.

    *tree_root_of* names the tree a file's project-root references resolve within.
    """
    identity = FixtureIdentity(tree_root_of)
    groups: list[FileGroup] = []
    splits: list[SplitGroup] = []
    for normal_group in duplicate_groups(files):
        by_key: dict[str, list[FixtureFile]] = defaultdict(list)
        for fixture in normal_group:
            by_key[identity.key(fixture.path)].append(fixture)
        parts = sorted((tuple(member.path for member in part) for part in by_key.values()), key=lambda p: p[0].as_posix())
        kind = normal_group[0].kind
        if len(parts) > 1:
            splits.append(SplitGroup(kind, tuple(normal_group), tuple(parts)))
        groups.extend(FileGroup(kind, tuple(part)) for part in by_key.values() if len(part) > 1)
    return sorted(groups, key=lambda group: group.members[0].path.as_posix()), splits


def _assigned_names(tree: ast.Module) -> dict[int, str]:
    """``id`` of each string constant assigned to one plain name, mapped to that name."""
    names: dict[int, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            names[id(node.value)] = node.targets[0].id
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            names[id(node.value)] = node.target.id
    return names


def _formatted_parts(tree: ast.Module) -> set[int]:
    return {id(part) for node in ast.walk(tree) if isinstance(node, ast.JoinedStr) for part in node.values}


def module_literal_sites(module: Path) -> list[LiteralSite]:
    """The plain string constants of *module* the budget gate counts as inline fixture literals."""
    tree = parse_module(module)
    counted = {(line, text) for line, text in string_literals(tree) if fixture_text_kind(text) is not None}
    if not counted:
        return []
    names = _assigned_names(tree)
    formatted = _formatted_parts(tree)
    sites: list[LiteralSite] = []
    for node, scope in _scoped_nodes(tree, ""):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)) or id(node) in formatted:
            continue
        if (node.lineno, node.value) in counted:
            sites.append(LiteralSite(module, node.lineno, node.col_offset, names.get(id(node)), node.value, scope))
    return sorted(sites, key=lambda site: (site.line, site.column))


def _scoped_nodes(node: ast.AST, scope: str) -> Iterator[tuple[ast.AST, str]]:
    """Every node under *node*, with the dotted name of the innermost class or function holding it."""
    for child in ast.iter_child_nodes(node):
        yield child, scope
        inner = scope
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            inner = f"{scope}.{child.name}" if scope else child.name
        yield from _scoped_nodes(child, inner)


def literal_groups(packages: Sequence[Path]) -> list[LiteralGroup]:
    """The groups of equal inline fixture literals assigned to one name, across the counted modules of
    *packages*. A literal assigned to no name is in no group: it names no fixture another site could share."""
    by_text: dict[tuple[str, str], list[LiteralSite]] = defaultdict(list)
    for package in packages:
        for module in literal_modules(package):
            for site in module_literal_sites(module):
                kind = fixture_text_kind(site.text)
                if kind is not None and site.name is not None:
                    by_text[(kind, normalized(site.text, kind))].append(site)
    groups = [
        LiteralGroup(kind, tuple(sorted(sites, key=lambda site: (site.module.as_posix(), site.line, site.column))))
        for (kind, _text), sites in by_text.items()
        if len(sites) > 1
    ]
    return sorted(groups, key=lambda group: (group.members[0].module.as_posix(), group.members[0].line))
