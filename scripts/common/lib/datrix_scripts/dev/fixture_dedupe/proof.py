"""The files a plan writes, and the static proof that writing them changes no bytes any reader reads.

A plan's write set: each shared file it creates (each moved copy, its references rewritten; each moving
literal's text), each file it changes (a staying fixture whose references are rewritten, a test module whose
sites are) and each copy it deletes. Over the tree the write leaves -- planned, before anything is written,
or on disk once it is -- the proof holds when:

* every moved text equals each copy it replaces, byte for byte, once the reference literals rewritten in it
  are mapped back; every staying fixture rewritten equals its old bytes the same way; every moved literal's
  shared file reads back, as text, as the literal's text;
* every reference resolves: each fixture still in a tree names, in text order, the files it named before at
  their new places, and each of them is a file there (consumed - produced is empty);
* every rewritten test module equals its old bytes once each replacement is mapped back to the expression
  it replaced and the accessor import taken out, it parses and imports the accessor, and each replacement's
  accessor call reads a shared file holding the bytes the old expression read (that file's rewritten
  references mapped back), or, for a literal, the literal's text.

The old bytes are read before anything is written, and kept: the same proof runs on the written tree.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol

from datrix_scripts.dev.fixture_dedupe.follow import Rewrite, mapped_back, placed_text
from datrix_scripts.dev.fixture_dedupe.layout import TreeRoots, shared_root
from datrix_scripts.dev.fixture_dedupe.plan import Plan, moved_copies
from datrix_scripts.dev.fixture_dedupe.references import named_files
from datrix_scripts.dev.fixture_dedupe.sites import (
    ACCESSOR,
    ACCESSOR_MODULE,
    ModuleEdit,
    SiteRewrite,
    accessor_argument,
    edit_spans,
    rewritten_source,
)
from datrix_scripts.gates.ratchet.fixture_budget_gate import FixtureScanError

_ENCODING: Final = "utf-8"
_ESCAPED: Final = "surrogateescape"


class Tree(Protocol):
    """The files of a workspace as a proof reads them."""

    def is_file(self, path: Path) -> bool:
        """Whether *path* is a file."""
        ...

    def read(self, path: Path) -> bytes:
        """The bytes of the file at *path*.

        Raises:
            FileNotFoundError: *path* is no file.
        """
        ...


@dataclass(frozen=True)
class WriteSet:
    """The files a plan creates, changes and deletes.

    Attributes:
        created: Each shared file created, with its bytes.
        changed: Each existing file rewritten, with its new bytes.
        deleted: Each copy deleted.
    """

    created: Mapping[Path, bytes]
    changed: Mapping[Path, bytes]
    deleted: tuple[Path, ...]

    @property
    def replaced(self) -> tuple[Path, ...]:
        """Every existing file the write changes or deletes: the files whose old bytes the proof compares
        against, and a rollback puts back."""
        return (*self.changed, *self.deleted)


class PlannedTree:
    """The workspace as it is once a write set is written, read before anything is."""

    def __init__(self, write: WriteSet) -> None:
        self._written = {**write.created, **write.changed}
        self._gone = frozenset(write.deleted)

    def is_file(self, path: Path) -> bool:
        """Whether *path* is a file once the write is written."""
        if path in self._written:
            return True
        return path not in self._gone and path.is_file()

    def read(self, path: Path) -> bytes:
        """The bytes of *path* once the write is written."""
        if path in self._written:
            return self._written[path]
        if path in self._gone:
            raise FileNotFoundError(f"{path} is deleted by the write")
        return path.read_bytes()


class DiskTree:
    """The workspace as it is on disk."""

    def is_file(self, path: Path) -> bool:
        """Whether *path* is a file on disk."""
        return path.is_file()

    def read(self, path: Path) -> bytes:
        """The bytes of *path* on disk."""
        return path.read_bytes()


@dataclass(frozen=True)
class Proof:
    """The result of proving a write.

    Attributes:
        failures: Each way the tree differs from what its readers read before, one line each.
        texts: How many moved and rewritten texts were compared with the copies they replace.
        references: How many references were resolved over the tree.
        sites: How many rewritten test sites were read back.
    """

    failures: tuple[str, ...]
    texts: int
    references: int
    sites: int


def _encoded(text: str) -> bytes:
    return text.encode(_ENCODING, errors=_ESCAPED)


def _decoded(data: bytes) -> str:
    return data.decode(_ENCODING, errors=_ESCAPED)


def _as_read_text(data: bytes) -> str:
    """*data* as ``Path.read_text(encoding="utf-8")`` returns it: decoded, line endings translated.

    Raises:
        UnicodeDecodeError: *data* is not UTF-8.
    """
    return data.decode(_ENCODING).replace("\r\n", "\n").replace("\r", "\n")


def _rewrites_by_file(rewrites: Sequence[Rewrite]) -> dict[Path, list[Rewrite]]:
    by_file: dict[Path, list[Rewrite]] = defaultdict(list)
    for rewrite in rewrites:
        by_file[rewrite.reference.source].append(rewrite)
    return by_file


def write_set(plan: Plan) -> WriteSet:
    """The files *plan* creates, changes and deletes, with the bytes of each one written.

    Raises:
        FixtureScanError: A fixture or module differs from the text the plan read, or two placements share a
            path.
    """
    rewrites = plan.followed.rewrites
    created: dict[Path, bytes] = {}
    deleted: list[Path] = []
    texts = [
        (placement.target, _encoded(placed_text(placement.source, rewrites)))
        for placement in plan.files
        if placement.source is not None and placement.target is not None
    ]
    texts.extend(
        (placement.target, placement.source.text.encode(_ENCODING))
        for placement in plan.literals
        if placement.source is not None and placement.target is not None
    )
    for target, data in texts:
        if target in created:
            raise FixtureScanError(f"two placements write {target}. Fix: report the plan's groups.")
        created[target] = data
    for placement in plan.files:
        if placement.source is not None:
            deleted.extend((placement.source, *placement.deleted))
    moved = moved_copies(plan.files)
    changed = {
        reader: _encoded(placed_text(reader, rewrites))
        for reader in sorted({rewrite.reference.source for rewrite in rewrites})
        if reader not in moved
    }
    changed.update({edit.module: rewritten_source(edit) for edit in plan.sites.edits})
    return WriteSet(created, changed, tuple(deleted))


class _Prover:
    """One proof of a plan's write over one tree."""

    def __init__(self, plan: Plan, tree: Tree, old: Mapping[Path, bytes]) -> None:
        self._plan = plan
        self._tree = tree
        self._old = old
        self._rewrites = _rewrites_by_file(plan.followed.rewrites)
        self._moved = moved_copies(plan.files)
        self._source_of = {target: source for source, target in self._moved.items()}
        self.failures: list[str] = []

    def shown(self, path: Path) -> str:
        return path.relative_to(self._plan.base_dir).as_posix()

    def _read_back(self, path: Path, rewrites: Sequence[Rewrite]) -> bytes:
        """The bytes of *path* in the tree with *rewrites* mapped back.

        Raises:
            FileNotFoundError: *path* is no file in the tree.
            FixtureScanError: A rewritten literal is not where its rewrite puts it.
        """
        return _encoded(mapped_back(_decoded(self._tree.read(path)), rewrites))

    def _compare(self, path: Path, rewrites: Sequence[Rewrite], copies: Sequence[Path]) -> int:
        try:
            back = self._read_back(path, rewrites)
        except (FileNotFoundError, FixtureScanError) as exc:
            self.failures.append(f"{self.shown(path)}: cannot be read back ({exc})")
            return 0
        for copy in copies:
            if back != self._old[copy]:
                self.failures.append(
                    f"{self.shown(path)}: its bytes, rewritten references mapped back, differ from "
                    f"{self.shown(copy)}, which it replaces"
                )
        return len(copies)

    def texts(self) -> int:
        """Prove every moved text, every rewritten staying fixture and every moved literal."""
        count = 0
        for placement in self._plan.files:
            if placement.source is not None and placement.target is not None:
                copies = (placement.source, *placement.deleted)
                count += self._compare(placement.target, self._rewrites.get(placement.source, []), copies)
        for reader, rewrites in self._rewrites.items():
            if reader not in self._moved:
                count += self._compare(reader, rewrites, (reader,))
        for placement in self._plan.literals:
            if placement.source is None or placement.target is None:
                continue
            count += 1
            if self._text_of(placement.target) != placement.source.text:
                self.failures.append(
                    f"{self.shown(placement.target)}: does not read back as the text of "
                    f"{self.shown(placement.source.module)}:{placement.source.line} {placement.source.name}"
                )
        return count

    def _text_of(self, path: Path) -> str:
        """The text ``read_text`` gives for *path* in the tree; empty with a failure when it cannot."""
        try:
            return _as_read_text(self._tree.read(path))
        except (FileNotFoundError, UnicodeDecodeError) as exc:
            self.failures.append(f"{self.shown(path)}: cannot be read as text ({exc})")
            return ""

    def references(self) -> int:
        """Resolve every reference of every fixture still in a tree over the tree."""
        kinds = {self._moved.get(fixture.path, fixture.path): fixture.kind for fixture in self._plan.fixtures}
        tree_root_of = TreeRoots(self._plan.base_dir, self._plan.packages)
        reach = (shared_root(self._plan.base_dir),)
        count = 0
        for placed, expected in self._plan.followed.expected.items():
            count += len(expected)
            for missing in (target for target in expected if not self._tree.is_file(target)):
                self.failures.append(f"{self.shown(placed)}: names {self.shown(missing)}, which is no file (consumed - produced)")
            try:
                text = _decoded(self._tree.read(placed))
            except FileNotFoundError:
                self.failures.append(f"{self.shown(placed)}: is no file, yet it stays in its tree")
                continue
            found = named_files(placed, text, kinds[placed], tree_root_of(placed), is_file=self._tree.is_file, reach=reach)
            if found != expected:
                self.failures.append(
                    f"{self.shown(placed)}: names {[self.shown(path) for path in found]}, "
                    f"not {[self.shown(path) for path in expected]}"
                )
        return count

    def sites(self) -> int:
        """Read back every rewritten test module and every site in it."""
        count = 0
        for edit in self._plan.sites.edits:
            if self._module(edit):
                count += len(edit.rewrites)
                for rewrite in edit.rewrites:
                    self._site(rewrite)
        return count

    def _module(self, edit: ModuleEdit) -> bool:
        """Whether *edit*'s module, mapped back, is its old bytes, parses and imports the accessor."""
        old = self._old[edit.module]
        try:
            new = self._tree.read(edit.module)
            back = module_mapped_back(edit, old, new)
            tree = ast.parse(new)
        except (FileNotFoundError, FixtureScanError, SyntaxError, ValueError) as exc:
            self.failures.append(f"{self.shown(edit.module)}: cannot be read back ({exc})")
            return False
        if back != old:
            self.failures.append(f"{self.shown(edit.module)}: differs from its old bytes beyond its rewritten sites")
            return False
        if not _imports_accessor(tree):
            self.failures.append(f"{self.shown(edit.module)}: does not import {ACCESSOR} from {ACCESSOR_MODULE}")
            return False
        return True

    def _site(self, rewrite: SiteRewrite) -> None:
        where = f"{self.shown(rewrite.module)}:{rewrite.line}"
        try:
            shared = shared_root(self._plan.base_dir) / accessor_argument(rewrite.replacement)
        except FixtureScanError as exc:
            self.failures.append(f"{where}: {exc}")
            return
        if shared != rewrite.shared:
            self.failures.append(f"{where}: {rewrite.replacement} reads {self.shown(shared)}, not {self.shown(rewrite.shared)}")
            return
        if rewrite.read is None:
            try:
                # Parenthesized: an implicit concatenation may span lines.
                value = ast.literal_eval(ast.parse(f"({rewrite.written})", mode="eval").body)
            except (SyntaxError, ValueError) as exc:
                self.failures.append(f"{where}: the literal it replaces cannot be evaluated ({exc})")
                return
            if self._text_of(shared) != value:
                self.failures.append(f"{where}: {rewrite.replacement} reads other text than the literal it replaces")
            return
        source = self._source_of.get(shared)
        if source is None:
            self.failures.append(f"{where}: {self.shown(shared)} is no moved copy")
            return
        try:
            back = self._read_back(shared, self._rewrites.get(source, []))
        except (FileNotFoundError, FixtureScanError) as exc:
            self.failures.append(f"{where}: {self.shown(shared)} cannot be read back ({exc})")
            return
        if back != self._old[rewrite.read]:
            self.failures.append(f"{where}: {rewrite.replacement} reads other bytes than {self.shown(rewrite.read)}")


def _imports_accessor(tree: ast.Module) -> bool:
    return any(
        isinstance(node, ast.ImportFrom)
        and node.module == ACCESSOR_MODULE
        and any(alias.name == ACCESSOR and alias.asname is None for alias in node.names)
        for node in tree.body
    )


def module_mapped_back(edit: ModuleEdit, old: bytes, new: bytes) -> bytes:
    """*new*, *edit*'s module once written, with each replacement mapped back to the bytes of *old* it
    replaced and the accessor import taken out: *old* again when the write changed nothing else.

    Raises:
        FixtureScanError: A replacement is not written where the edit puts it, or *old* is not the module
            the edit was planned on.
    """
    pieces: list[bytes] = []
    cursor = 0
    shift = 0
    for start, end, text in edit_spans(edit, old):
        at = start + shift
        if at < cursor or new[at : at + len(text)] != text:
            raise FixtureScanError(f"{edit.module}: {_decoded(text)!r} is not written at byte {at}")
        pieces.extend((new[cursor:at], old[start:end]))
        cursor = at + len(text)
        shift += len(text) - (end - start)
    pieces.append(new[cursor:])
    return b"".join(pieces)


def prove(plan: Plan, tree: Tree, old: Mapping[Path, bytes]) -> Proof:
    """Prove *plan*'s write over *tree* (planned or written), *old* holding the bytes of every file it
    replaces as they were before anything was written."""
    prover = _Prover(plan, tree, old)
    texts = prover.texts()
    references = prover.references()
    sites = prover.sites()
    return Proof(tuple(prover.failures), texts, references, sites)
