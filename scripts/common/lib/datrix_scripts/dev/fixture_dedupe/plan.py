"""Where each group's one copy lives, and which copies stay where they are.

Placement: a file group's copy is its sorted-first movable copy, moved to
``<corpus>/shared/<package>/<path in the package>``; every other movable copy is deleted. A literal
group's copy is ``<corpus>/shared/inline/<sorted-first module, workspace-relative, without .py>/<NAME><kind>``
(``.../<module>/<Class.function>/<NAME><kind>`` for a literal bound inside a class or function), taken from its sorted-first literal assigned to one name; every literal assigned to one name is rewritten
to read it.

Kept in place:

* a copy inside a directory a test or a case collector reads whole (``walks``);
* a copy already in the shared ``datrix-testing`` fixture set: the shared accessors read it there;
* every copy of a ``.dcfg`` group (file or literal) whose placed text the capture holds a secret finding
  or a refused load for, in a package that captures the corpus (``secret_screen``); the screen is rerun
  without the flagged groups until it flags none of the groups that move;
* every copy of a ``.dtrx`` group (file or literal) whose placed text the formatter's corpus walk refuses
  (``format_screen``): a template, a partial source or a deliberately broken text, rerun the same way;
* every copy of a group whose moved copy names a file it could no longer reach from the shared place
  (``follow``), and a copy a fixture that stays names when that fixture could not reach the copy's shared
  place: deleting either would change what the reference reads. The plan is rebuilt with what the screen
  flags and what the references hold until neither holds anything new;
* a copy whose bytes differ from the copy that moves (normalized-equal only): deleting it would change the
  bytes its readers read. The copy that moves is the sorted-first of the largest class of byte-equal copies;
* the one copy of a group left with fewer than two movable copies: one copy is no duplicate to share.

A literal not assigned to one name cannot be rewritten to ``NAME = shared_fixture(...)``: it is refused and
listed for a hand edit. Only the literals holding one exact text read a group's shared file (the largest
class of equal texts holding an assigned literal); a literal whose text differs, or holds what a shared file
read as text does not give back (a carriage return), is refused and stays as written. A placement colliding with an existing file or another group's placement is
refused with the whole group, its literals listed for a hand edit.

Once the plan settles, the test-module sites reading a copy that leaves, and the literals that move, are
rewritten to read the shared copies (``sites``); a site that cannot be is listed for a hand edit and holds
nothing.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from datrix_testing.corpus import INLINE_DIR

from datrix_scripts.dev.fixture_dedupe.follow import FollowedReferences, follow_references
from datrix_scripts.dev.fixture_dedupe.format_screen import format_findings
from datrix_scripts.dev.fixture_dedupe.groups import (
    FileGroup,
    LiteralGroup,
    LiteralSite,
    SplitGroup,
    file_groups,
    literal_groups,
)
from datrix_scripts.dev.fixture_dedupe.layout import (
    TreeRoots,
    corpus_root,
    shared_fixtures_dir,
    shared_root,
)
from datrix_scripts.dev.fixture_dedupe.secret_screen import PlacedText, screen, screened_packages
from datrix_scripts.dev.fixture_dedupe.sites import SitePlan, find_sites
from datrix_scripts.dev.fixture_dedupe.walks import RefusedWalk, Walks, find_walks
from datrix_scripts.framework_repos import PackageMarker, workspace_package_dirs
from datrix_scripts.gates.ratchet.fixture_budget_gate import (
    DCFG_KIND,
    DTRX_KIND,
    SHARED_PACKAGE,
    FixtureFile,
    FixtureScanError,
    fixture_files,
    read_fixture,
)

SHARED_SET_REASON: Final = "already in the shared datrix-testing fixture set, read there by its accessors"
SCREEN_REASON: Final = "a screen of the corpus flags its placed text"
LONE_COPY_REASON: Final = "the group's only movable copy: one copy is no duplicate to share"
FOLLOW_REASON: Final = "a reference of its copy cannot follow it to the shared place"
READER_REASON: Final = "a fixture that stays reads it and cannot reach the shared place"
BYTES_REASON: Final = "its bytes differ from the copy that moves, so deleting it would change the bytes its readers read"
NOT_ASSIGNED_REASON: Final = "not assigned to one name, so no NAME = shared_fixture(...) rewrite applies"
NO_ASSIGNED_LITERAL: Final = "no literal of the group is assigned to one name"
TEXT_REASON: Final = "its text differs from the literal that moves, so reading the shared file would change its value"
UNREADABLE_REASON: Final = "its text holds a carriage return or a lone surrogate, which a shared file read as text does not give back"
LONE_LITERAL_REASON: Final = "no two literals of the group hold one exact text: one literal is no duplicate to share"
_TEXT_ENCODING: Final = "utf-8"
_FILE_KEY: Final = "file"
_LITERAL_KEY: Final = "literal"


@dataclass(frozen=True)
class KeptCopy:
    """A copy that stays where it is, and why."""

    path: Path
    reason: str


@dataclass(frozen=True)
class FilePlacement:
    """What happens to one file group.

    Attributes:
        group: The group.
        source: The copy that moves; ``None`` when nothing moves.
        target: Where it moves.
        deleted: The copies deleted.
        kept: The copies that stay, each with its reason.
        refusal: Why the group moves nothing, when it does not.
    """

    group: FileGroup
    source: Path | None
    target: Path | None
    deleted: tuple[Path, ...]
    kept: tuple[KeptCopy, ...]
    refusal: str | None


@dataclass(frozen=True)
class RefusedLiteral:
    """A literal of a group the tool does not rewrite, and why: it is edited by hand."""

    site: LiteralSite
    reason: str


@dataclass(frozen=True)
class LiteralPlacement:
    """What happens to one literal group.

    Attributes:
        group: The group.
        target: The shared file its text moves to; ``None`` when it does not move.
        source: The literal whose text is written there.
        rewritten: The literals rewritten to read the shared file.
        refused: The literals left for a hand edit.
        refusal: Why the group moves nothing, when it does not.
    """

    group: LiteralGroup
    target: Path | None
    source: LiteralSite | None
    rewritten: tuple[LiteralSite, ...]
    refused: tuple[RefusedLiteral, ...]
    refusal: str | None


@dataclass(frozen=True)
class Plan:
    """The whole dedupe plan of one workspace.

    Attributes:
        base_dir: The workspace root.
        corpus: The corpus root.
        packages: The package directories holding a ``tests/`` tree.
        fixtures: Every counted fixture file of those trees and of the shared set.
        files: Each file group's placement.
        literals: Each literal group's placement.
        splits: The normalized-equal file groups their references split.
        walks: The directories read whole, and the walk sites that cannot be evaluated.
        screened: The packages whose capture screened the placed ``.dcfg`` texts.
        screen_findings: Each flagged group's findings, by group key.
        followed: The move map, and where every reference lands once the copies move.
        sites: The test-module sites rewritten to read the shared copies, and the ones left for a hand edit.
    """

    base_dir: Path
    corpus: Path
    packages: tuple[Path, ...]
    fixtures: tuple[FixtureFile, ...]
    files: tuple[FilePlacement, ...]
    literals: tuple[LiteralPlacement, ...]
    splits: tuple[SplitGroup, ...]
    walks: Walks
    screened: tuple[str, ...]
    screen_findings: Mapping[str, list[str]]
    followed: FollowedReferences
    sites: SitePlan

    @property
    def refused_walks(self) -> tuple[RefusedWalk, ...]:
        """The walk sites whose directory cannot be evaluated: the plan cannot prove what they read."""
        return self.walks.refused


def file_target(base_dir: Path, fixture: FixtureFile) -> Path:
    """Where *fixture*'s group copy lives once moved: ``shared/<package>/<path in the package>``."""
    return shared_root(base_dir) / fixture.package / fixture.path.relative_to(base_dir / fixture.package)


def literal_target(base_dir: Path, site: LiteralSite, kind: str) -> Path:
    """Where a literal group's text lives once moved: ``shared/inline/<module without .py>/<NAME><kind>``, with
    the dotted name of the class or function holding the literal as one more directory when it is not at
    module level, so a name each test function binds for itself places once per function."""
    module = site.module.relative_to(base_dir).with_suffix("")
    directory = shared_root(base_dir) / INLINE_DIR / module
    if site.scope:
        directory = directory / site.scope
    return directory / f"{site.name}{kind}"


def file_key(group: FileGroup) -> str:
    """The key naming a file group in screen findings."""
    return f"{_FILE_KEY}:{group.members[0].path.as_posix()}"


def literal_key(group: LiteralGroup) -> str:
    """The key naming a literal group in screen findings."""
    first = group.members[0]
    return f"{_LITERAL_KEY}:{first.module.as_posix()}:{first.line}:{first.column}"


def place_file(
    base_dir: Path, group: FileGroup, walks: Walks, flagged: str | None, held: Mapping[Path, str]
) -> FilePlacement:
    """The placement of *group*: walked, shared and *held* copies (each with its reason) kept; *flagged* (the
    screen's reason, or a reference of the group's copy that cannot follow it) moves nothing."""
    shared = shared_fixtures_dir(base_dir).resolve()
    kept: list[KeptCopy] = []
    movable: list[FixtureFile] = []
    for member in group.members:
        walked = walks.reader_of(member.path)
        if walked is not None:
            kept.append(KeptCopy(member.path, walked.describe(base_dir)))
        elif member.path.resolve().is_relative_to(shared):
            kept.append(KeptCopy(member.path, SHARED_SET_REASON))
        elif member.path in held:
            kept.append(KeptCopy(member.path, held[member.path]))
        else:
            movable.append(member)
    if flagged is None:
        movable, differing = _byte_equal(movable)
        kept.extend(KeptCopy(member.path, BYTES_REASON) for member in differing)
    if flagged is not None or len(movable) < 2:
        reason = flagged if flagged is not None else LONE_COPY_REASON
        kept.extend(KeptCopy(member.path, reason) for member in movable)
        return FilePlacement(group, None, None, (), tuple(kept), reason)
    target = file_target(base_dir, movable[0])
    if target.exists():
        refusal = f"its placement {target.relative_to(base_dir).as_posix()} already exists"
        kept.extend(KeptCopy(member.path, refusal) for member in movable)
        return FilePlacement(group, None, None, (), tuple(kept), refusal)
    return FilePlacement(group, movable[0].path, target, tuple(m.path for m in movable[1:]), tuple(kept), None)


def _byte_equal(copies: Sequence[FixtureFile]) -> tuple[list[FixtureFile], list[FixtureFile]]:
    """*copies* split into the copies that share one copy and the rest: the largest class of byte-equal
    copies (of equal size, the one holding the sorted-first copy), and the copies of every other class."""
    classes: dict[str, list[FixtureFile]] = {}
    for copy in copies:
        classes.setdefault(read_fixture(copy.path), []).append(copy)
    if not classes:
        return [], []
    chosen = max(classes.values(), key=len)
    return chosen, [copy for copy in copies if copy not in chosen]


def _readable(text: str) -> bool:
    """Whether a shared file holding *text* reads back as *text* through ``read_text(encoding="utf-8")``:
    no carriage return (newline translation drops it) and no unencodable surrogate."""
    if "\r" in text:
        return False
    try:
        text.encode(_TEXT_ENCODING)
    except UnicodeEncodeError:
        return False
    return True


def _text_class(group: LiteralGroup) -> tuple[list[LiteralSite], list[RefusedLiteral]]:
    """The literals of *group* that read one shared text -- the largest class of equal, readable texts
    holding a literal assigned to one name (of equal size, the one met first) -- and the rest refused."""
    refused: list[RefusedLiteral] = []
    classes: dict[str, list[LiteralSite]] = {}
    for site in group.members:
        if _readable(site.text):
            classes.setdefault(site.text, []).append(site)
        else:
            refused.append(RefusedLiteral(site, UNREADABLE_REASON))
    candidates = [members for members in classes.values() if any(site.name is not None for site in members)]
    chosen = max(candidates, key=len) if candidates else []
    refused.extend(RefusedLiteral(site, TEXT_REASON) for site in group.members if _readable(site.text) and site not in chosen)
    return chosen, refused


def place_literal(base_dir: Path, group: LiteralGroup, flagged: str | None, taken: set[Path]) -> LiteralPlacement:
    """The placement of *group*; *flagged* (the screen's reason) moves nothing; *taken* collects placements.

    Only literals of one exact text read the shared file (the one whose text it holds); a literal whose text
    differs, or that a shared file cannot give back, is refused and stays as written."""
    if flagged is not None:
        return LiteralPlacement(group, None, None, (), (), flagged)
    if not any(site.name is not None for site in group.members):
        unassigned = tuple(RefusedLiteral(site, NOT_ASSIGNED_REASON) for site in group.members)
        return LiteralPlacement(group, None, None, (), unassigned, NO_ASSIGNED_LITERAL)
    sharing, refused = _text_class(group)
    if len(sharing) < 2:
        return LiteralPlacement(group, None, None, (), (), LONE_LITERAL_REASON)
    assigned = [site for site in sharing if site.name is not None]
    unassigned = [RefusedLiteral(site, NOT_ASSIGNED_REASON) for site in sharing if site.name is None]
    target = literal_target(base_dir, assigned[0], group.kind)
    if target in taken or target.exists():
        refusal = f"its placement {target.relative_to(base_dir).as_posix()} is taken by another group or an existing file"
        return LiteralPlacement(group, None, None, (), tuple(RefusedLiteral(s, refusal) for s in group.members), refusal)
    taken.add(target)
    return LiteralPlacement(group, target, assigned[0], tuple(assigned), (*unassigned, *refused), None)


def _placed_texts(
    base_dir: Path, files: Sequence[FilePlacement], literals: Sequence[LiteralPlacement], kind: str
) -> list[PlacedText]:
    """The texts of *kind* the plan writes into the corpus, keyed by group."""
    corpus = corpus_root(base_dir)
    placed = [
        PlacedText(file_key(placement.group), placement.target.relative_to(corpus), placement.source.read_bytes())
        for placement in files
        if placement.group.kind == kind and placement.source is not None and placement.target is not None
    ]
    placed.extend(
        PlacedText(literal_key(placement.group), placement.target.relative_to(corpus), placement.source.text.encode("utf-8"))
        for placement in literals
        if placement.group.kind == kind and placement.source is not None and placement.target is not None
    )
    return placed


def _placements(
    base_dir: Path,
    groups: Sequence[FileGroup],
    literal_set: Sequence[LiteralGroup],
    walks: Walks,
    holds: _Holds,
) -> tuple[list[FilePlacement], list[LiteralPlacement]]:
    files = [place_file(base_dir, group, walks, holds.groups.get(file_key(group)), holds.copies) for group in groups]
    taken: set[Path] = set()
    literals = [place_literal(base_dir, group, holds.groups.get(literal_key(group)), taken) for group in literal_set]
    return files, literals


def _leaving(placement: FilePlacement) -> tuple[Path, ...]:
    """The package copies *placement* takes out of their tree: the moved one and the deleted ones."""
    moved = () if placement.source is None else (placement.source,)
    return (*moved, *placement.deleted)


def move_map(files: Sequence[FilePlacement]) -> dict[Path, Path]:
    """Each copy *files* takes out of its tree, mapped to the copy that replaces it: the moved copy and each
    deleted copy to the group's shared place."""
    moves: dict[Path, Path] = {}
    for placement in files:
        if placement.source is None or placement.target is None:
            continue
        moves[placement.source] = placement.target
        moves.update({deleted: placement.target for deleted in placement.deleted})
    return moves


def literal_rewrites(literals: Sequence[LiteralPlacement]) -> list[tuple[LiteralSite, Path]]:
    """Each literal *literals* rewrites, with the shared file it reads once rewritten."""
    return [(site, placement.target) for placement in literals if placement.target is not None for site in placement.rewritten]


def moved_copies(files: Sequence[FilePlacement]) -> dict[Path, Path]:
    """Each copy *files* moves, mapped to its shared place."""
    return {placement.source: placement.target for placement in files if placement.source and placement.target}


@dataclass
class _Holds:
    """What stays where it is while a plan settles.

    Attributes:
        groups: Each group that moves nothing, by group key, with its reason.
        copies: Each copy that stays where it is, with its reason.
    """

    groups: dict[str, str] = field(default_factory=dict)
    copies: dict[Path, str] = field(default_factory=dict)


def _reference_holds(base_dir: Path, followed: FollowedReferences, files: Sequence[FilePlacement], holds: _Holds) -> bool:
    """Hold what each reference that cannot follow reads: the group of a moved reader moves nothing, and a
    leaving copy a staying reader names stays with it. Whether anything new is held."""
    group_of = {placement.source: placement.group for placement in files if placement.source is not None}
    fresh = False
    for refused in followed.refused:
        reader = refused.reference.source
        shown = f"{reader.relative_to(base_dir).as_posix()} names '{refused.reference.literal}'"
        if reader in group_of and file_key(group_of[reader]) not in holds.groups:
            holds.groups[file_key(group_of[reader])] = f"{FOLLOW_REASON}: {shown}, and {refused.reason}"
            fresh = True
        elif reader not in group_of and refused.reference.target in followed.moves and refused.reference.target not in holds.copies:
            holds.copies[refused.reference.target] = f"{READER_REASON}: {shown}, and {refused.reason}"
            fresh = True
    return fresh


def _packages(base_dir: Path) -> list[Path]:
    packages = workspace_package_dirs(base_dir, any_of=frozenset({PackageMarker.TESTS}))
    if not packages:
        raise FixtureScanError(
            f"no datrix-* directory under {base_dir} holds a tests/ tree, so there is nothing to dedupe. "
            "Fix: point -BaseDir at the workspace root."
        )
    if not corpus_root(base_dir).is_dir():
        raise FixtureScanError(
            f"corpus root {corpus_root(base_dir)} does not exist, so no copy has a shared place. "
            "Fix: point -BaseDir at the workspace root, or restore the corpus."
        )
    return packages


def build_plan(base_dir: Path) -> Plan:
    """The dedupe plan of the workspace at *base_dir*.

    Raises:
        FixtureScanError: No package or no corpus, or a counted file cannot be read or parsed.
        ScreenError: A screened package's model set or capture cannot run.
    """
    packages = _packages(base_dir)
    walks = find_walks(packages)
    every_file = [fixture for package in packages for fixture in fixture_files(package / PackageMarker.TESTS.value, package.name)]
    every_file.extend(fixture_files(shared_fixtures_dir(base_dir), SHARED_PACKAGE))
    groups, splits = file_groups(every_file, TreeRoots(base_dir, packages))
    literal_set = literal_groups(packages)
    screened = screened_packages(packages)
    holds = _Holds()
    findings: dict[str, list[str]] = {}
    while True:
        files, literals = _placements(base_dir, groups, literal_set, walks, holds)
        removed = frozenset(path for placement in files for path in _leaving(placement))
        new = format_findings(_placed_texts(base_dir, files, literals, DTRX_KIND))
        new.update(screen(corpus_root(base_dir), screened, _placed_texts(base_dir, files, literals, DCFG_KIND), removed))
        if new:
            findings.update(new)
            holds.groups.update({key: f"{SCREEN_REASON}: {'; '.join(found)}" for key, found in new.items()})
            continue
        followed = follow_references(base_dir, packages, every_file, move_map(files), moved_copies(files))
        if not _reference_holds(base_dir, followed, files, holds):
            break
    sites = find_sites(base_dir, packages, followed.moves, literal_rewrites(literals))
    return Plan(
        base_dir=base_dir,
        corpus=corpus_root(base_dir),
        packages=tuple(packages),
        fixtures=tuple(every_file),
        files=tuple(files),
        literals=tuple(literals),
        splits=tuple(splits),
        walks=walks,
        screened=tuple(package.name for package in screened),
        screen_findings=findings,
        followed=followed,
        sites=sites,
    )
