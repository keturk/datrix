"""Findings files split into units with a stable id.

UNITS (exact)
    A raw (agent-written) file is one unit whose id is its file stem. A consolidated file is one unit per
    ``## `` section, ``C009.1``, ``C009.2``, ... in order (a consolidated file with no ``## `` section is
    the one unit ``C009.1``). A unit's text is the source's own lines, headings demoted one level and
    cp1252 mojibake restored; nothing is summarised.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from datrix_scripts.skill.common import FENCE, markdown_sections, read_text
from datrix_scripts.skill.findings import finding_files

_CONSOLIDATED_NAME = re.compile(r"^consolidated-(\d{3})-([a-z0-9-]+)\.md$")
_SECTION_NUMBER = re.compile(r"^\d+\.\s+")
#: A UTF-8 sequence read as cp1252: a lead byte character followed by one or two continuation characters.
_MOJIBAKE_RUN = re.compile(r"[Â-ï][^\x00-\x7f]{1,2}")
#: The one common sequence cp1252 cannot encode back (0x9d is undefined there).
_RIGHT_QUOTE_MOJIBAKE = ("â€\u009d", "”")


@dataclass(frozen=True)
class Unit:
    unit_id: str
    source: str
    title: str
    body: tuple[str, ...]


@dataclass(frozen=True)
class SourceFile:
    name: str
    number: str
    title: str
    preamble: tuple[str, ...]
    units: tuple[Unit, ...]

    @property
    def consolidated(self) -> bool:
        return bool(self.number)


def repair_mojibake(text: str) -> str:
    """``text`` with UTF-8 sequences that were read as cp1252 (``â€”`` for ``—``) restored."""

    def repair(match: re.Match[str]) -> str:
        run = match.group(0)
        try:
            return run.encode("cp1252").decode("utf-8")
        except UnicodeError:
            return run

    return _MOJIBAKE_RUN.sub(repair, text.replace(*_RIGHT_QUOTE_MOJIBAKE))


def _demoted(lines: Sequence[str]) -> tuple[str, ...]:
    """``lines`` with every markdown heading outside a code fence one level deeper."""
    result: list[str] = []
    in_fence = False
    for line in lines:
        if line.lstrip().startswith(FENCE):
            in_fence = not in_fence
        heading = not in_fence and re.match(r"^#+ ", line) is not None
        result.append("#" + line if heading else line)
    return tuple(result)


def _trimmed(lines: Sequence[str]) -> tuple[str, ...]:
    """``lines`` without leading and trailing blank lines."""
    items = list(lines)
    while items and not items[0].strip():
        items.pop(0)
    while items and not items[-1].strip():
        items.pop()
    return tuple(items)


def _whole_file_unit(unit_id: str, name: str, lines: list[str]) -> tuple[str, Unit]:
    """A file that is one finding: its H1 is the title, everything else the body."""
    titles = [s for s in markdown_sections(lines, 1) if s.level == 1]
    if not titles:
        return Path(name).stem, Unit(unit_id, name, Path(name).stem, _trimmed(_demoted(lines)))
    head = titles[0]
    body = lines[:head.start - 1] + lines[head.start:]
    return head.heading, Unit(unit_id, name, head.heading, _trimmed(_demoted(body)))


def parse_source(path: Path) -> SourceFile:
    """One findings file split into its units."""
    lines = repair_mojibake(read_text(path)).splitlines()
    match = _CONSOLIDATED_NAME.match(path.name)
    if match is None:
        title, unit = _whole_file_unit(path.stem, path.name, lines)
        return SourceFile(path.name, "", title, (), (unit,))
    number = match.group(1)
    sections = markdown_sections(lines, 2)
    numbered = [s for s in sections if s.level == 2]
    if not numbered:
        title, unit = _whole_file_unit(f"C{number}.1", path.name, lines)
        return SourceFile(path.name, number, title, (), (unit,))
    head = next((s for s in sections if s.level == 1), None)
    title = head.heading if head else path.stem
    preamble = [line for s in sections if s.level < 2 for line in lines[s.start - 1:s.end]
                if not (s.level == 1 and line.lstrip().startswith("# "))]
    units = tuple(
        Unit(f"C{number}.{index}", path.name, _SECTION_NUMBER.sub("", s.heading), _trimmed(lines[s.start:s.end]))
        for index, s in enumerate(numbered, start=1))
    return SourceFile(path.name, number, title, _trimmed(preamble), units)


def load_sources(directory: Path) -> list[SourceFile]:
    return [parse_source(path) for path in finding_files(directory)]
