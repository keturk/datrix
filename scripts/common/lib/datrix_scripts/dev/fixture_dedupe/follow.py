"""The references that follow their file once a plan's copies move.

A move map sends each copy leaving a package tree to the copy that replaces it: the moved copy to its
shared place, each deleted copy to its group's shared copy. Once the copies move, every fixture still in a
tree -- each moved copy at its shared place, and every file that stays -- must name the file it named
before, at that file's new place (its shared copy, or the file itself where it stays).

A reference that still does, read by its own rule from where its file now lies, is left as written. One
that does not is rewritten to the relative path of that file's new place, against the base its rule
resolves from:

* an ``include`` or a ``.dseed`` path against its file's directory;
* a project-root path against the project root, which moves with its file: the directory as many levels
  above the file's new place as the old root lay above its old place.

A reference cannot follow, and is refused, when:

* its loader confines it to its base and the file's new place lies outside it (``references``: every
  reference but an ``include`` and a header's config path);
* the file's new place lies in a ``tests/`` tree other than its own: across packages only the shared
  corpus is read;
* its rewritten path, read back by its rule over the moved tree, lands on another file or on none.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from datrix_scripts.dev.fixture_dedupe.layout import TreeRoots, shared_root
from datrix_scripts.dev.fixture_dedupe.references import Reference, fixture_references, resolve_reference
from datrix_scripts.gates.ratchet.fixture_budget_gate import FixtureFile, FixtureScanError, read_fixture


@dataclass(frozen=True)
class Rewrite:
    """A reference rewritten to reach its file's new place.

    Attributes:
        reference: The reference as written, in its file at its old place.
        placed: Where its file lies once the copies move.
        target: Where the file it names lies once the copies move.
        literal: The path it is rewritten to.
    """

    reference: Reference
    placed: Path
    target: Path
    literal: str


@dataclass(frozen=True)
class RefusedReference:
    """A reference that cannot reach its file's new place, and why."""

    reference: Reference
    placed: Path
    target: Path
    reason: str


@dataclass(frozen=True)
class FollowedReferences:
    """Where every reference of a plan lands once its copies move.

    Attributes:
        moves: Each copy leaving a package tree, mapped to the copy that replaces it.
        rewrites: The references rewritten, in file and text order.
        refused: The references that cannot follow, in file and text order.
        read: How many references were read.
        expected: Each fixture still in a tree, keyed by where it lies once the copies move, with the files
            its references must name from there, in text order: each file it named, at that file's new place.
    """

    moves: Mapping[Path, Path]
    rewrites: tuple[Rewrite, ...]
    refused: tuple[RefusedReference, ...]
    read: int
    expected: Mapping[Path, tuple[Path, ...]]


class MovedTree:
    """The files of a workspace once a move map is applied: each placed copy is there, each leaving one gone."""

    def __init__(self, moves: Mapping[Path, Path]) -> None:
        self._placed = frozenset(moves.values())
        self._gone = frozenset(moves)

    def is_file(self, path: Path) -> bool:
        """Whether *path* is a file once the copies move."""
        if path in self._placed:
            return True
        return path not in self._gone and path.is_file()


def _ancestor(directory: Path, levels: int) -> Path:
    return directory if levels == 0 else directory.parents[levels - 1]


class _Follower:
    """Follows the references of one workspace's fixtures over its moved tree."""

    def __init__(self, base_dir: Path, packages: Sequence[Path], moves: Mapping[Path, Path]) -> None:
        self._moves = moves
        self._tree = MovedTree(moves)
        self._tree_root_of = TreeRoots(base_dir, packages)
        self._base_dir = base_dir
        self._shared = shared_root(base_dir)
        self.rewrites: list[Rewrite] = []
        self.refused: list[RefusedReference] = []
        self.read = 0
        self.expected: dict[Path, tuple[Path, ...]] = {}

    def follow_file(self, path: Path, kind: str, placed: Path) -> None:
        """Follow every reference of the fixture at *path*, which lies at *placed* once the copies move."""
        references = fixture_references(path, kind, self._tree_root_of(path))
        self.expected[placed] = tuple(self._moves.get(reference.target, reference.target) for reference in references)
        for reference in references:
            self.read += 1
            self._follow(reference, placed)

    def _follow(self, reference: Reference, placed: Path) -> None:
        target = self._moves.get(reference.target, reference.target)
        levels = len(reference.source.parent.relative_to(reference.base).parts)
        base = _ancestor(placed.parent, levels)
        if self._lands(placed, reference.literal, reference.rule, base, target):
            return
        literal = Path(os.path.relpath(target, base)).as_posix()
        reason = self._refusal(reference, placed, base, target, literal)
        if reason:
            self.refused.append(RefusedReference(reference, placed, target, reason))
            return
        self.rewrites.append(Rewrite(reference, placed, target, literal))

    def _lands(self, placed: Path, literal: str, rule: str, base: Path, target: Path) -> bool:
        resolution = resolve_reference(
            placed, literal, rule, self._tree_root_of(placed), is_file=self._tree.is_file, reach=(self._shared,)
        )
        return resolution is not None and resolution.base == base and resolution.target == target

    def _refusal(self, reference: Reference, placed: Path, base: Path, target: Path, literal: str) -> str:
        """Why *reference*, rewritten to *literal*, cannot follow its file; empty when it can."""
        resolved = target.resolve()
        if reference.confined and not resolved.is_relative_to(base.resolve()):
            return f"its loader confines it to {self._shown(base)}, and its file now lies at {self._shown(target)}"
        own_tree = self._tree_root_of(placed)
        if not (resolved.is_relative_to(own_tree) or resolved.is_relative_to(self._shared.resolve())):
            return f"its file now lies at {self._shown(target)}, in another package's tests/ tree"
        if not self._lands(placed, literal, reference.rule, base, target):
            return f"the rewritten path {literal!r}, read back by its rule, does not land on {self._shown(target)}"
        return ""

    def _shown(self, path: Path) -> str:
        return path.relative_to(self._base_dir).as_posix()


def follow_references(
    base_dir: Path,
    packages: Sequence[Path],
    fixtures: Sequence[FixtureFile],
    moves: Mapping[Path, Path],
    moved_to: Mapping[Path, Path],
) -> FollowedReferences:
    """Where every reference of *fixtures* lands once the copies of *moves* move (*moved_to*: each moved
    copy's shared place; every other key of *moves* is deleted): the references rewritten to follow their
    file, and the ones that cannot.

    Raises:
        FixtureScanError: A fixture cannot be read.
    """
    follower = _Follower(base_dir, packages, moves)
    for fixture in fixtures:
        if fixture.path in moves and fixture.path not in moved_to:
            continue
        follower.follow_file(fixture.path, fixture.kind, moved_to.get(fixture.path, fixture.path))
    return FollowedReferences(moves, tuple(follower.rewrites), tuple(follower.refused), follower.read, follower.expected)


def rewritten_text(text: str, rewrites: Sequence[Rewrite]) -> str:
    """*text* with each of *rewrites* (all of one file) applied at its offset.

    Raises:
        FixtureScanError: A rewrite's literal is not written at its offset in *text*.
    """
    result = text
    for rewrite in sorted(rewrites, key=lambda one: one.reference.offset, reverse=True):
        start = rewrite.reference.offset
        end = start + len(rewrite.reference.literal)
        if result[start:end] != rewrite.reference.literal:
            raise FixtureScanError(
                f"{rewrite.reference.source}: {rewrite.reference.literal!r} is not written at offset {start}, so "
                "its rewrite would change other text. Fix: rebuild the plan from the files as they are now."
            )
        result = f"{result[:start]}{rewrite.literal}{result[end:]}"
    return result


def mapped_back(text: str, rewrites: Sequence[Rewrite]) -> str:
    """*text*, the text of a fixture once *rewrites* (all of one file) were applied, with each rewritten
    literal mapped back to the literal it replaced: the inverse of :func:`rewritten_text`.

    Raises:
        FixtureScanError: A rewritten literal is not written where its rewrite puts it in *text*.
    """
    pieces: list[str] = []
    cursor = 0
    shift = 0
    for rewrite in sorted(rewrites, key=lambda one: one.reference.offset):
        start = rewrite.reference.offset + shift
        end = start + len(rewrite.literal)
        if start < cursor or text[start:end] != rewrite.literal:
            raise FixtureScanError(
                f"{rewrite.placed}: the rewritten literal {rewrite.literal!r} is not written at offset {start}, so "
                f"the text is not {rewrite.reference.source} with its references rewritten."
            )
        pieces.extend((text[cursor:start], rewrite.reference.literal))
        cursor = end
        shift += len(rewrite.literal) - len(rewrite.reference.literal)
    pieces.append(text[cursor:])
    return "".join(pieces)


def reference_rewrites(rewrites: Sequence[Rewrite]) -> dict[Path, dict[str, str]]:
    """Each fixture *rewrites* rewrite, by its resolved path at its old place, mapped from each reference
    as written to the text replacing it: what a semantic dump read before the move records instead of the
    reference (``datrix_testing.semantic_baseline``, ``rewritten``).

    Raises:
        FixtureScanError: One reference text of a file is rewritten to two texts, so a dump of the node
            holding it could not be translated.
    """
    texts: dict[Path, dict[str, str]] = {}
    for rewrite in rewrites:
        in_file = texts.setdefault(rewrite.reference.source.resolve(), {})
        known = in_file.setdefault(rewrite.reference.literal, rewrite.literal)
        if known != rewrite.literal:
            raise FixtureScanError(
                f"{rewrite.reference.source}: the reference {rewrite.reference.literal!r} is rewritten both to "
                f"{known!r} and to {rewrite.literal!r}, so the semantic baseline cannot translate it. Fix: give the "
                "two references their own text."
            )
    return texts


def placed_text(source: Path, rewrites: Sequence[Rewrite]) -> str:
    """The text the fixture at *source* holds once those of *rewrites* written in it are applied."""
    return rewritten_text(read_fixture(source), [rewrite for rewrite in rewrites if rewrite.reference.source == source])
