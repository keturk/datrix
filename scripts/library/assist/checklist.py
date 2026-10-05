"""The conformance checklist /verify-implementation reviews against: drafted by a local model, checked.

A local model reads the design document section by section and lists every requirement it states --
the decision id when the design numbers it, the requirement in one sentence, the set of surfaces it
ranges over, the lines that state it, and a phrase quoted from those lines. Two checks keep the
draft honest:

* every quote must appear, whitespace aside, in the lines its item cites -- an item whose quote is
  not there is listed as unverified;
* every requirement-bearing line of the design (a decision id, or must / must not / never / always /
  shall / required / forbidden / fail closed / fail loud, outside code fences) must fall inside some
  item's lines -- a line no item covers is listed, so a dropped requirement is visible.

The skill still reads the design in full and owns the final checklist; this is the draft it edits.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from shared.local_llm import LocalLlmPool
from shared.local_reading import MAX_CHUNK_CHARS

from assist.common import (
    FENCE,
    ContentFilter,
    MarkdownSection,
    ask_json,
    markdown_sections,
    object_list,
    parallel,
    read_text,
    section_body,
    string_list,
    workspace_label,
)

LOG = logging.getLogger(__name__)

SIGNAL = re.compile(
    r"\b[DG]\d+\b|\b(must not|must|never|always|shall|required|forbidden|fails? closed|fails? loud)\b",
    re.IGNORECASE)
_WHITESPACE = re.compile(r"\s+")

EXTRACT_SYSTEM = (
    "You extract the requirements a design document states, for a reviewer who will check each one "
    "against code. Lines are numbered 'N| text'. For EVERY requirement, decision or invariant in the text "
    "you are given (a numbered decision, a must / must not / never / always rule, an invariant over a set "
    "of targets), give: id (the design's own id such as D3 or G2 if it has one, else an empty string); "
    "requirement (one sentence, faithful to the text, no interpretation); surfaces (the languages, "
    "platforms, packages, files or positions it applies to, as the text names them; empty when it names "
    "none); first_line and last_line (the line numbers that state it); quote (a phrase of at least six "
    "words copied exactly from those lines). Leave out background, motivation and examples that state no "
    "rule. Never invent a requirement the text does not state.")

EXTRACT_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "requirements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "requirement": {"type": "string"},
                    "surfaces": {"type": "array", "items": {"type": "string"}},
                    "first_line": {"type": "integer"},
                    "last_line": {"type": "integer"},
                    "quote": {"type": "string"},
                },
                "required": ["id", "requirement", "surfaces", "first_line", "last_line", "quote"],
            },
        },
    },
    "required": ["requirements"],
}


@dataclass(frozen=True)
class Requirement:
    ident: str
    text: str
    surfaces: tuple[str, ...]
    first: int
    last: int
    quote: str
    quote_found: bool


@dataclass
class Checklist:
    design: str
    lines: int
    requirements: list[Requirement] = field(default_factory=list)
    uncovered: list[tuple[int, str]] = field(default_factory=list)
    note: str = ""

    @property
    def unverified(self) -> list[Requirement]:
        return [r for r in self.requirements if not r.quote_found]


def _squeezed(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip().lower()


def signal_lines(lines: list[str]) -> list[int]:
    """The line numbers outside code fences and headings that carry a decision id or a requirement word.

    A heading names a section; the lines under it state the requirement, and those are what an item cites.
    """
    found: list[int] = []
    in_fence = False
    for number, line in enumerate(lines, start=1):
        if line.lstrip().startswith(FENCE):
            in_fence = not in_fence
            continue
        if not in_fence and not line.lstrip().startswith("#") and SIGNAL.search(line):
            found.append(number)
    return found


def _batches(sections: list[MarkdownSection], lines: list[str]) -> list[tuple[int, int]]:
    """Consecutive sections grouped into line ranges that fit one request."""
    batches: list[tuple[int, int]] = []
    start, size = 0, 0
    for section in sections:
        chars = sum(len(line) + 8 for line in lines[section.start - 1:section.end])
        if start and size + chars > MAX_CHUNK_CHARS:
            batches.append((start, section.start - 1))
            start, size = 0, 0
        if not start:
            start = section.start
        size += chars
    if start:
        batches.append((start, len(lines)))
    return batches


def _as_int(value: object, default: int) -> int:
    return value if isinstance(value, int) else default


def _requirement(item: dict[str, object], lines: list[str], batch: tuple[int, int]) -> Requirement:
    first = min(max(_as_int(item.get("first_line"), batch[0]), batch[0]), batch[1])
    last = min(max(_as_int(item.get("last_line"), first), first), batch[1])
    quote = str(item.get("quote", "")).strip()
    stated = _squeezed(" ".join(lines[first - 1:last]))
    found = bool(quote) and _squeezed(quote) in stated
    return Requirement(str(item.get("id", "")).strip(), str(item.get("requirement", "")).strip(),
                       tuple(string_list(item.get("surfaces"))), first, last, quote, found)


def draft_checklist(workspace: Path, pool: LocalLlmPool, design: Path) -> Checklist:
    """The design's requirements as a checklist draft, with both checks applied."""
    text = read_text(design)
    lines = text.splitlines()
    label = workspace_label(workspace, design)
    section = ContentFilter(workspace).section(label, text)
    sections = markdown_sections(lines, max_level=3)
    batches = _batches(sections, lines)

    def ask(batch: tuple[int, int]) -> list[Requirement]:
        answer = ask_json(pool, EXTRACT_SYSTEM, section_body(section, batch[0], batch[1]), EXTRACT_SCHEMA)
        return [_requirement(item, lines, batch) for item in object_list(answer.get("requirements"))]

    requirements = sorted((r for found in parallel(batches, ask) for r in found), key=lambda r: (r.first, r.last))
    covered = {n for r in requirements if r.quote_found for n in range(r.first, r.last + 1)}
    uncovered = [(n, lines[n - 1].strip()) for n in signal_lines(lines) if n not in covered]
    return Checklist(label, len(lines), requirements, uncovered, section.note)


def render(checklist: Checklist) -> str:
    lines = [f"# Conformance checklist draft -- {checklist.design}", "",
             f"{len(checklist.requirements)} requirement(s) drafted by a local model from {checklist.lines} lines. "
             "Each cites the design lines that state it; open them before you rely on the wording.", ""]
    for number, r in enumerate(checklist.requirements, start=1):
        ident = f"[{r.ident}] " if r.ident else ""
        surfaces = f" Surfaces: {', '.join(r.surfaces)}." if r.surfaces else ""
        flag = "" if r.quote_found else " **(quote not found at these lines: verify)**"
        lines.append(f"{number}. {ident}{r.text}{surfaces} ({checklist.design}:{r.first}-{r.last}){flag}")
    lines += ["", "## Requirement-bearing lines no item covers", "",
              "Each carries a decision id or a must/never/always word. Add an item, or decide it states no "
              "requirement.", ""]
    lines += [f"- {checklist.design}:{n}: {text}" for n, text in checklist.uncovered] or ["None."]
    if checklist.note:
        lines += ["", checklist.note]
    return "\n".join(lines) + "\n"
