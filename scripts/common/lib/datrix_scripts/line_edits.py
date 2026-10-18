"""Line-addressed reading and editing of workspace text files, for the ``datrix-edit`` MCP server.

An agent's ``Edit`` call re-sends the old text it replaces (``old_string``), padded until it is
unique in the file. Every later model response re-reads that payload, so in long editing sessions
the old text costs as much as the new. Here the old text is named, not re-sent: a reading shows
every line with a two-character hash, and an edit names a line range plus the hash of every line
in it. Each replaced line is still checked against what the agent saw, so a stale or mistaken
line number is refused with the lines now there, never applied.

One call may carry many edits across many files. Every line number refers to the file as it was
before the call (edits are applied bottom-up), every edit of the call is checked before any file
is written, and each file is replaced atomically. Untouched lines keep their own line endings;
new lines take the file's prevailing ending; a UTF-8 byte-order mark and a missing final newline
are kept. Only existing UTF-8 text files under the workspace root are read or written.

Also imported by the Claude Code hook that runs the edit guards over an ``edit_lines`` call, so
this module imports nothing beyond the standard library.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final, NamedTuple

LOG = logging.getLogger(__name__)

LINE_HASH_CHARS: Final = 2
MAX_FILE_BYTES: Final = 4 * 1024 * 1024
MAX_READ_LINES: Final = 2000
MAX_SHOWN_LINE_CHARS: Final = 2000
MAX_EDITS_PER_CALL: Final = 200
MAX_LISTED_LINES: Final = 80
MAX_SHOWN_MISMATCHES: Final = 5
UTF8_BOM: Final = "﻿"
CRLF: Final = "\r\n"
LF: Final = "\n"
TEMP_SUFFIX: Final = ".datrix-edit"

_LINE_RE: Final = re.compile(r"[^\n]*\n|[^\n]+\Z")
_WHITESPACE_RE: Final = re.compile(r"\s+")


class LineEditError(ValueError):
    """A read or edit cannot be carried out; the message says what is wrong and what to send."""


class Line(NamedTuple):
    text: str
    ending: str


def line_hash(text: str) -> str:
    """The short hash a reading shows beside a line and an edit names it by (its text, no ending)."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:LINE_HASH_CHARS]


@dataclass(frozen=True)
class TextFile:
    """One file's lines with their own endings, and what writing it back must keep."""

    lines: tuple[Line, ...]
    eol: str
    bom: bool
    final_newline: bool

    def render(self) -> str:
        return (UTF8_BOM if self.bom else "") + "".join(line.text + line.ending for line in self.lines)


def parse_text(text: str) -> TextFile:
    """Split decoded file text into lines, keeping each line's ending."""
    bom = text.startswith(UTF8_BOM)
    body = text[len(UTF8_BOM):] if bom else text
    lines: list[Line] = []
    for match in _LINE_RE.finditer(body):
        chunk = match.group(0)
        ending = CRLF if chunk.endswith(CRLF) else LF if chunk.endswith(LF) else ""
        lines.append(Line(chunk[: len(chunk) - len(ending)], ending))
    crlf = sum(1 for line in lines if line.ending == CRLF)
    lf = sum(1 for line in lines if line.ending == LF)
    # An empty file takes a final newline, like any file a line edit then writes lines into.
    return TextFile(tuple(lines), CRLF if crlf > lf else LF, bom, body.endswith(LF) or not body)


def resolve_in_scope(root: Path, raw_path: str) -> Path:
    """The existing regular file ``raw_path`` names under ``root`` (absolute or root-relative)."""
    if not raw_path.strip():
        raise LineEditError("'file_path' is required: an absolute path, or one relative to the workspace root.")
    candidate = Path(raw_path)
    resolved = (candidate if candidate.is_absolute() else root / candidate).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise LineEditError(f"{raw_path} is outside the workspace ({root}); only workspace files can be read or edited.")
    if not resolved.is_file():
        raise LineEditError(f"{raw_path} is not an existing file. Create new files with Write; "
                            "read_lines and edit_lines work on existing text files only.")
    return resolved


def load_text_file(path: Path) -> TextFile:
    data = path.read_bytes()
    if len(data) > MAX_FILE_BYTES:
        raise LineEditError(f"{path} is {len(data)} bytes, over the {MAX_FILE_BYTES}-byte limit for line edits; "
                            "use Read and Edit for it.")
    if b"\0" in data:
        raise LineEditError(f"{path} holds NUL bytes, so it is not a text file; line edits work on UTF-8 text only.")
    try:
        return parse_text(data.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise LineEditError(f"{path} is not valid UTF-8 ({exc.reason} at byte {exc.start}); "
                            "line edits work on UTF-8 text only, so use Read and Edit for it.") from exc


def display_path(root: Path, path: Path) -> str:
    return path.relative_to(root.resolve()).as_posix()


def _shown(text: str) -> str:
    if len(text) <= MAX_SHOWN_LINE_CHARS:
        return text
    return f"{text[:MAX_SHOWN_LINE_CHARS]} ...[+{len(text) - MAX_SHOWN_LINE_CHARS} chars]"


def numbered(number: int, text: str) -> str:
    """One line as a reading shows it: ``<number>:<hash>|<text>``."""
    return f"{number}:{line_hash(text)}|{_shown(text)}"


def read_lines(root: Path, raw_path: str, offset: int, limit: int) -> str:
    """Lines ``offset`` .. ``offset + limit - 1`` of a file, each numbered and hashed."""
    path = resolve_in_scope(root, raw_path)
    lines = load_text_file(path).lines
    shown = display_path(root, path)
    if not lines:
        return f"{shown}: empty file (insert into it with after=0, hash='')."
    if offset > len(lines):
        raise LineEditError(f"{shown} has {len(lines)} lines; 'offset' {offset} is past its end.")
    last = min(len(lines), offset + limit - 1)
    body = [numbered(number, lines[number - 1].text) for number in range(offset, last + 1)]
    return "\n".join([f"{shown}: lines {offset}-{last} of {len(lines)}", *body])


# ---------------------------------------------------------------------------
# edits
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Replace:
    """Replace lines ``start``..``end`` (inclusive); ``hashes`` names every one of them, in order."""

    file_path: str
    start: int
    end: int
    hashes: str
    text: str


@dataclass(frozen=True)
class Insert:
    """Insert lines after line ``after`` (0 = the top); ``hash`` names line ``after`` ('' for 0)."""

    file_path: str
    after: int
    hash: str
    text: str


Edit = Replace | Insert

_REPLACE_KEYS: Final = frozenset({"file_path", "start", "end", "hashes", "text"})
_INSERT_KEYS: Final = frozenset({"file_path", "after", "hash", "text"})
_EDIT_SHAPES: Final = ("replace {file_path, start, end, hashes, text} or "
                       "insert {file_path, after, hash, text}")


def _int_field(raw: dict[str, object], key: str, index: int) -> int:
    value = raw[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise LineEditError(f"Edit {index}: '{key}' must be an integer line number; got {value!r}.")
    return value


def _text_field(raw: dict[str, object], key: str, index: int) -> str:
    value = raw[key]
    if not isinstance(value, str):
        raise LineEditError(f"Edit {index}: '{key}' must be a string; got {value!r}.")
    return value


def parse_edit(raw: object, index: int) -> Edit:
    """One edit object of an ``edit_lines`` call, checked for shape only."""
    if not isinstance(raw, dict):
        raise LineEditError(f"Edit {index} must be an object: {_EDIT_SHAPES}; got {raw!r}.")
    keys = frozenset(raw)
    if keys == _REPLACE_KEYS:
        return Replace(_text_field(raw, "file_path", index), _int_field(raw, "start", index),
                       _int_field(raw, "end", index), _WHITESPACE_RE.sub("", _text_field(raw, "hashes", index)),
                       _text_field(raw, "text", index))
    if keys == _INSERT_KEYS:
        return Insert(_text_field(raw, "file_path", index), _int_field(raw, "after", index),
                      _text_field(raw, "hash", index).strip(), _text_field(raw, "text", index))
    raise LineEditError(f"Edit {index} has keys {sorted(keys)}; pass exactly the keys of {_EDIT_SHAPES}.")


def parse_edits(raw: object) -> list[Edit]:
    if not isinstance(raw, list) or not raw or len(raw) > MAX_EDITS_PER_CALL:
        raise LineEditError(f"'edits' is required: a list of 1 to {MAX_EDITS_PER_CALL} edit objects "
                            f"({_EDIT_SHAPES}).")
    return [parse_edit(item, index) for index, item in enumerate(raw, 1)]


def new_lines(text: str) -> list[str]:
    """The lines an edit's ``text`` holds: one trailing newline is ignored; '' holds none."""
    if text == "":
        return []
    body = text[:-1] if text.endswith(LF) else text
    return [line.removesuffix("\r") for line in body.split(LF)]


def _mismatch_report(shown: str, lines: tuple[Line, ...], edit: Replace) -> str:
    wanted = [edit.hashes[i:i + LINE_HASH_CHARS] for i in range(0, len(edit.hashes), LINE_HASH_CHARS)]
    current = [line_hash(lines[n - 1].text) for n in range(edit.start, edit.end + 1)]
    differing = [edit.start + i for i, (have, want) in enumerate(zip(current, wanted)) if have != want]
    listing = [f"  {numbered(n, lines[n - 1].text)}" for n in differing[:MAX_SHOWN_MISMATCHES]]
    more = len(differing) - MAX_SHOWN_MISMATCHES
    return "\n".join([
        f"{shown}: lines {edit.start}-{edit.end} are not the lines you named ({len(differing)} differ). "
        f"Now there (current hashes {''.join(current)}):", *listing,
        *([f"  ...and {more} more"] if more > 0 else []),
        "Nothing was written. Check the lines with read_lines and send the edit again."])


def _check_replace(shown: str, lines: tuple[Line, ...], edit: Replace) -> None:
    if not 1 <= edit.start <= edit.end <= len(lines):
        raise LineEditError(f"{shown}: lines {edit.start}-{edit.end} are not a range of its {len(lines)} lines "
                            "(1 <= start <= end <= last line). To insert, use {file_path, after, hash, text}.")
    expected_chars = LINE_HASH_CHARS * (edit.end - edit.start + 1)
    if len(edit.hashes) != expected_chars:
        raise LineEditError(f"{shown}: lines {edit.start}-{edit.end} need {expected_chars} hash characters "
                            f"({LINE_HASH_CHARS} per line, in order); got {len(edit.hashes)} ({edit.hashes!r}).")
    current = "".join(line_hash(lines[n - 1].text) for n in range(edit.start, edit.end + 1))
    if current != edit.hashes.lower():
        raise LineEditError(_mismatch_report(shown, lines, edit))


def _check_insert(shown: str, lines: tuple[Line, ...], edit: Insert) -> None:
    if not 0 <= edit.after <= len(lines):
        raise LineEditError(f"{shown}: 'after' {edit.after} is not a line of its {len(lines)} lines (0 = the top).")
    if not new_lines(edit.text):
        raise LineEditError(f"{shown}: an insert after line {edit.after} needs a non-empty 'text'.")
    expected = line_hash(lines[edit.after - 1].text) if edit.after else ""
    if edit.hash.lower() != expected:
        anchor = numbered(edit.after, lines[edit.after - 1].text) if edit.after else "the top (hash '')"
        raise LineEditError(f"{shown}: line {edit.after} is not the line you named (hash {edit.hash!r}). "
                            f"Now there: {anchor}. Nothing was written.")


def _span(edit: Edit) -> tuple[float, float]:
    """The edit's place in the file: a replace covers its lines, an insert the gap after a line."""
    if isinstance(edit, Replace):
        return float(edit.start), float(edit.end)
    return edit.after + 0.5, edit.after + 0.5


def _check_overlaps(shown: str, edits: list[Edit]) -> None:
    ordered = sorted(edits, key=_span)
    for earlier, later in zip(ordered, ordered[1:]):
        if _span(later)[0] <= _span(earlier)[1]:
            raise LineEditError(f"{shown}: two edits touch the same place ({_describe(earlier)} and "
                                f"{_describe(later)}). Merge them into one edit; nothing was written.")


def _describe(edit: Edit) -> str:
    return f"lines {edit.start}-{edit.end}" if isinstance(edit, Replace) else f"insert after line {edit.after}"


def _apply(before: TextFile, edits: list[Edit]) -> TextFile:
    lines = list(before.lines)
    # Bottom-up, so every line number still means what it meant in the file the agent read.
    for edit in sorted(edits, key=_span, reverse=True):
        added = [Line(text, before.eol) for text in new_lines(edit.text)]
        if isinstance(edit, Replace):
            lines[edit.start - 1:edit.end] = added
        else:
            lines[edit.after:edit.after] = added
    for index in range(len(lines) - 1):
        if not lines[index].ending:
            lines[index] = Line(lines[index].text, before.eol)
    if lines:
        last = lines[-1]
        lines[-1] = Line(last.text, (last.ending or before.eol) if before.final_newline else "")
    return TextFile(tuple(lines), before.eol, before.bom, before.final_newline and bool(lines))


def _hash_listing(first: int, texts: list[str]) -> str:
    listed = [f"{first + i}:{line_hash(text)}" for i, text in enumerate(texts[:MAX_LISTED_LINES])]
    more = len(texts) - MAX_LISTED_LINES
    return " ".join(listed) + (f" ...(+{more})" if more > 0 else "")


def _change_report(edit: Edit, shift: int) -> tuple[str, int]:
    """One line saying where an edit's lines now are (with their hashes), and the new shift."""
    added = new_lines(edit.text)
    if isinstance(edit, Insert):
        first = edit.after + shift + 1
        return (f"  after {edit.after} -> {first}-{first + len(added) - 1} (+{len(added)}): "
                f"{_hash_listing(first, added)}"), shift + len(added)
    removed = edit.end - edit.start + 1
    delta = len(added) - removed
    if not added:
        return f"  {edit.start}-{edit.end} -> deleted ({delta})", shift + delta
    first = edit.start + shift
    return (f"  {edit.start}-{edit.end} -> {first}-{first + len(added) - 1} ({delta:+d}): "
            f"{_hash_listing(first, added)}"), shift + delta


@dataclass(frozen=True)
class FileChange:
    """The planned result of one call's edits to one file."""

    path: Path
    shown: str
    before: TextFile
    after: TextFile
    edits: tuple[Edit, ...]

    def report(self) -> str:
        lines = [f"{self.shown}: {len(self.edits)} change(s), {len(self.before.lines)} -> "
                 f"{len(self.after.lines)} lines"]
        shift = 0
        for edit in sorted(self.edits, key=_span):
            line, shift = _change_report(edit, shift)
            lines.append(line)
        return "\n".join(lines)


def plan_edits(root: Path, raw_edits: object) -> list[FileChange]:
    """Check every edit of a call against the files as they are now; nothing is written."""
    edits = parse_edits(raw_edits)
    by_path: dict[Path, list[Edit]] = {}
    for edit in edits:
        by_path.setdefault(resolve_in_scope(root, edit.file_path), []).append(edit)
    changes: list[FileChange] = []
    for path, file_edits in by_path.items():
        before = load_text_file(path)
        shown = display_path(root, path)
        for edit in file_edits:
            if isinstance(edit, Replace):
                _check_replace(shown, before.lines, edit)
            else:
                _check_insert(shown, before.lines, edit)
        _check_overlaps(shown, file_edits)
        changes.append(FileChange(path, shown, before, _apply(before, file_edits), tuple(file_edits)))
    return changes


def _write_atomically(path: Path, text: str) -> None:
    temp = path.with_name(f".{path.name}.{os.getpid()}{TEMP_SUFFIX}")
    try:
        with open(temp, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def apply_edits(root: Path, raw_edits: object) -> str:
    """Check every edit of a call, then write each changed file; the report names the new lines."""
    changes = plan_edits(root, raw_edits)
    written: list[str] = []
    for change in changes:
        try:
            _write_atomically(change.path, change.after.render())
        except OSError as exc:
            done = ", ".join(written) or "none"
            raise LineEditError(f"Writing {change.shown} failed ({exc}); files already written: {done}. "
                                "Re-read the files that were not written before editing them again.") from exc
        written.append(change.shown)
        LOG.info("edit_lines wrote %s (%d edits)", change.shown, len(change.edits))
    return "\n".join(change.report() for change in changes)


def guard_edit(change: FileChange) -> tuple[str, str]:
    """The change as one ``old_string`` -> ``new_string`` pair over the lines it touches.

    For hooks written for ``Edit``: the lines the before and after texts share at both ends are
    dropped, and a pure insertion keeps one neighbouring line so ``old_string`` is never empty
    while the file has lines.
    """
    before, after = list(change.before.lines), list(change.after.lines)
    head = 0
    while head < min(len(before), len(after)) and before[head] == after[head]:
        head += 1
    tail = 0
    while tail < min(len(before), len(after)) - head and before[-1 - tail] == after[-1 - tail]:
        tail += 1
    if head + tail == len(before) and before:
        head, tail = (head - 1, tail) if head else (head, tail - 1)

    def joined(lines: list[Line]) -> str:
        return "".join(line.text + line.ending for line in lines[head:len(lines) - tail])

    return joined(before), joined(after)
