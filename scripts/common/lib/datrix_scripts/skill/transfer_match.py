"""Text matching for the absorb transfer check: what settles a design section without a model, and which
target text a model reads for the sections that remain.

EXACT SETTLEMENT
    A design section whose substantive lines all appear, whitespace and list markers aside, as lines of the
    target docs was copied there. It is PRESENT with the target lines as citations, and no model is asked.

ABSENT TERMS
    The numbers and words of a design section that occur nowhere in the target docs are found by plain
    search. A model may offer other words for them (it sees the design section, never the target text);
    each offer is searched in the targets too. A term no search finds is unresolved, and a section with
    unresolved terms cannot be PRESENT.

NARROWING
    The target docs are cut into parts (one per heading, long ones in windows). A section that is not settled
    is sent only the parts that share the most weighted terms with it, within one chunk: a term found in few
    parts weighs more than a term found in many. Every part keeps its original line numbers, so the citations
    a model gives are checked against exactly what it was sent.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass, replace

from datrix_scripts.knowledge.lookup import stem
from datrix_scripts.knowledge.store import split_words
from datrix_scripts.local_reading import Section
from datrix_scripts.skill.common import markdown_sections

MIN_TERM_CHARS = 3
MIN_LINE_CHARS = 12
# A section whose substantive text is shorter than this is too thin for an exact match to mean a copy.
MIN_VERBATIM_CHARS = 40
HEADING_LEVEL = 3
MAX_PART_CHARS = 6_000
# One chunk of target text, which leaves room for the design section and the answer in the model's window.
TARGET_BUDGET_CHARS = 24_000
# A part scoring below this share of the best part's score shares only common words with the section.
RELATIVE_FLOOR = 0.25
# A claim term is a number or a word of at least this many letters; shorter words are filler.
MIN_CLAIM_CHARS = 4
# Other words a model offers for an absent term count only when few target lines carry them: measured on the
# controlled designs, a real rewording matched one to three lines and the generic offers (access, plan,
# data) six to sixteen.
MAX_ALTERNATIVE_LINES = 3
_NUMBER = re.compile(r"\b\d+(?:\.\d+)?\b")
_STATUS = re.compile(r"^\W*status\s*:", re.IGNORECASE)
_LIST_MARKER = re.compile(r"^(?:[-*+>]\s+|\d+[.)]\s+)")
_SPACES = re.compile(r"\s+")
_RULE_ROW = re.compile(r"^[\s|:\-]+$")
_FENCE = "```"


@dataclass(frozen=True)
class Selection:
    """The target parts one design section is asked about."""

    sections: tuple[Section, ...]
    chosen: int
    total: int
    shared_terms: bool

    def note(self) -> str:
        """What was sent, for the answer's footer."""
        if self.shared_terms:
            return (f"Sent {self.chosen} of {self.total} target part(s): the ones sharing the most terms with "
                    "this section.")
        return (f"No target part shares a distinctive term with this section; sent the first {self.chosen} of "
                f"{self.total} target part(s).")


@dataclass(frozen=True)
class TargetIndex:
    """The target docs cut into parts, with every line and term indexed."""

    parts: tuple[Section, ...]
    lines: dict[str, tuple[str, int]]
    part_terms: tuple[frozenset[str], ...]
    frequency: dict[str, int]
    # The stem of every word and every number in the targets, and the stems of each line (for a phrase).
    stems: frozenset[str]
    numbers: frozenset[str]
    line_stems: tuple[tuple[str, int, frozenset[str]], ...]


@dataclass(frozen=True)
class LexicalCheck:
    """The terms of one design section that appear nowhere in the targets, and what became of them."""

    total: int
    found_elsewhere: tuple[tuple[str, str, str], ...]
    unresolved: tuple[str, ...]
    # Words the model judged to carry no claim (never a number); listed so a reader can overrule it.
    filler: tuple[str, ...] = ()
    # False when no other words were searched for (the model had not called the section PRESENT).
    searched: bool = True

    @property
    def has_findings(self) -> bool:
        return bool(self.found_elsewhere or self.unresolved or self.filler)

    @property
    def lowers_present(self) -> bool:
        """Whether a model's PRESENT for this section cannot stand: terms remain that no search found."""
        return bool(self.unresolved)

    def render(self, lowered: bool) -> str:
        """The section's lexical findings for the report."""
        absent = len(self.found_elsewhere) + len(self.unresolved) + len(self.filler)
        lines = [f"LEXICAL CHECK: {absent} of {self.total} term(s) of this section appear nowhere in the targets."]
        if lowered:
            lines.append(f"The model's PRESENT is not accepted: {len(self.unresolved)} term(s) stay unfound, so "
                         "the verdict is PARTIAL.")
        lines += [f'- found under other words: {term} -> "{alternative}" at {cite}'
                  for term, alternative, cite in self.found_elsewhere]
        if self.unresolved:
            heading = "not found" if self.searched else "absent (no other words searched)"
            lines.append(f"- {heading}: {', '.join(self.unresolved)}")
        if self.filler:
            lines.append(f"- set aside by the model as filler: {', '.join(self.filler)}")
        return "\n".join(lines)


def line_text(numbered: str) -> str:
    """The text of a ``Section`` line (``<number>| <text>``)."""
    return numbered.split("| ", 1)[-1]


def line_number(numbered: str) -> int:
    """The line number of a ``Section`` line."""
    return int(numbered.split("|", 1)[0])


def normalised(line: str) -> str:
    """``line`` without its list marker, table edges and repeated spaces."""
    return _SPACES.sub(" ", _LIST_MARKER.sub("", line.strip()).strip("| "))


def substantive_lines(lines: Sequence[str]) -> list[str]:
    """The normalised lines that state something: no heading, fence, table rule or fragment."""
    found: list[str] = []
    for line in lines:
        text = normalised(line)
        if len(text) >= MIN_LINE_CHARS and not text.startswith(("#", _FENCE)) and not _RULE_ROW.match(text):
            found.append(text)
    return found


def _terms(text: str) -> frozenset[str]:
    return frozenset(word for word in split_words(text) if len(word) >= MIN_TERM_CHARS)


def _windows(section: Section, first: int, last: int) -> list[Section]:
    """``section``'s lines ``first``..``last`` (0-based, end exclusive) in runs of at most MAX_PART_CHARS."""
    windows: list[Section] = []
    current: list[str] = []
    size = 0
    for line in section.lines[first:last]:
        if current and size + len(line) + 1 > MAX_PART_CHARS:
            windows.append(Section(section.label, tuple(current), section.note))
            current, size = [], 0
        current.append(line)
        size += len(line) + 1
    if current:
        windows.append(Section(section.label, tuple(current), section.note))
    return windows


def target_parts(sections: Sequence[Section]) -> list[Section]:
    """Each target doc cut at its headings (level 1-3), long parts in windows; line numbers are kept."""
    parts: list[Section] = []
    for section in sections:
        for heading in markdown_sections([line_text(line) for line in section.lines], HEADING_LEVEL):
            parts += _windows(section, heading.start - 1, heading.end)
    return parts


def build_target_index(sections: Sequence[Section]) -> TargetIndex:
    """Index the target docs: their parts, each normalised line's first place, and each part's terms."""
    lines: dict[str, tuple[str, int]] = {}
    for section in sections:
        for numbered in section.lines:
            text = normalised(line_text(numbered))
            if len(text) >= MIN_LINE_CHARS and text not in lines:
                lines[text] = (section.label, line_number(numbered))
    parts = tuple(target_parts(sections))
    part_terms = tuple(_terms("\n".join(line_text(line) for line in part.lines)) for part in parts)
    frequency: dict[str, int] = {}
    for terms in part_terms:
        for term in terms:
            frequency[term] = frequency.get(term, 0) + 1
    line_stems = tuple(
        (section.label, line_number(numbered), frozenset(stem(word) for word in split_words(line_text(numbered))))
        for section in sections
        for numbered in section.lines
    )
    stems = frozenset(word for _label, _number, words in line_stems for word in words)
    numbers = frozenset(
        number for section in sections for numbered in section.lines for number in _NUMBER.findall(line_text(numbered))
    )
    return TargetIndex(parts, lines, part_terms, frequency, stems, numbers, line_stems)


def claim_lines(lines: Sequence[str]) -> list[str]:
    """The normalised lines of a design section that state something: no heading, Status line, fence or rule."""
    kept: list[str] = []
    for line in lines:
        text = normalised(line)
        if text and not text.startswith(("#", _FENCE)) and not _STATUS.match(text) and not _RULE_ROW.match(text):
            kept.append(text)
    return kept


def claim_terms(lines: Sequence[str]) -> list[str]:
    """The numbers and the words of at least MIN_CLAIM_CHARS letters in a section's claim lines, each once."""
    found: dict[str, None] = {}
    for text in claim_lines(lines):
        for number in _NUMBER.findall(text):
            found[number] = None
        for word in split_words(text):
            if len(word) >= MIN_CLAIM_CHARS and not word.isdigit():
                found[word] = None
    return list(found)


def absent_terms(index: TargetIndex, terms: Sequence[str]) -> list[str]:
    """The terms that occur nowhere in the target docs (words by stem, numbers as written)."""
    return [
        term
        for term in terms
        if (term not in index.numbers if _NUMBER.fullmatch(term) else stem(term) not in index.stems)
    ]


def find_alternative(index: TargetIndex, phrase: str) -> str:
    """The first target line carrying every word of ``phrase`` (by stem) as ``path:line``. Empty when none
    does, when the phrase has no word of MIN_CLAIM_CHARS letters (filler would match everywhere), or when
    more than MAX_ALTERNATIVE_LINES lines carry it: a word the targets use everywhere evidences no claim."""
    words = split_words(phrase)
    if not any(len(word) >= MIN_CLAIM_CHARS for word in words):
        return ""
    wanted = {stem(word) for word in words}
    hits = [(label, number) for label, number, stems in index.line_stems if wanted <= stems]
    if not hits or len(hits) > MAX_ALTERNATIVE_LINES:
        return ""
    return f"{hits[0][0]}:{hits[0][1]}"


def _ranges(hits: Sequence[tuple[str, int]]) -> str:
    """``hits`` as ``path:first-last`` citations, consecutive lines joined, in the order files first appear."""
    by_file: dict[str, list[int]] = {}
    for label, number in hits:
        by_file.setdefault(label, []).append(number)
    cited: list[str] = []
    for label, numbers in by_file.items():
        run_first = run_last = None
        for number in sorted(set(numbers)):
            if run_first is not None and number == run_last + 1:
                run_last = number
                continue
            if run_first is not None:
                cited.append(_cite(label, run_first, run_last))
            run_first = run_last = number
        cited.append(_cite(label, run_first, run_last))
    return ", ".join(cited)


def _cite(label: str, first: int, last: int) -> str:
    return f"{label}:{first}" if first == last else f"{label}:{first}-{last}"


def verbatim_citations(index: TargetIndex, section_lines: Sequence[str]) -> str:
    """The target lines that carry every substantive line of the design section, as citations; empty when
    the section is not a copy of target text (or too thin to say)."""
    wanted = substantive_lines(section_lines)
    if sum(len(text) for text in wanted) < MIN_VERBATIM_CHARS:
        return ""
    hits: list[tuple[str, int]] = []
    for text in wanted:
        if text not in index.lines:
            return ""
        hits.append(index.lines[text])
    return _ranges(hits)


def _score(index: TargetIndex, section_terms: frozenset[str], part: int) -> float:
    total = len(index.parts)
    return sum(math.log(1 + total / index.frequency[term]) for term in section_terms & index.part_terms[part])


def _size(part: Section) -> int:
    return sum(len(line) + 1 for line in part.lines)


def _fitting(order: Sequence[int], index: TargetIndex, budget_chars: int) -> list[int]:
    """The parts of ``order`` that fit the budget together, taken in order, a too-large one skipped."""
    chosen: list[int] = []
    used = 0
    for part in order:
        size = _size(index.parts[part])
        if used + size <= budget_chars:
            chosen.append(part)
            used += size
    return chosen


def select_parts(index: TargetIndex, section_text: str, budget_chars: int = TARGET_BUDGET_CHARS) -> Selection:
    """The target parts to send for one design section: those sharing the most weighted terms with it that
    fit the budget; with no shared term, the first parts that fit."""
    section_terms = _terms(section_text)
    scores = [_score(index, section_terms, part) for part in range(len(index.parts))]
    best = max(scores, default=0.0)
    ranked = sorted((part for part in range(len(scores)) if scores[part] >= max(best * RELATIVE_FLOOR, 1e-9)),
                    key=lambda part: (-scores[part], part))
    shared = bool(ranked)
    chosen = sorted(_fitting(ranked if shared else range(len(index.parts)), index, budget_chars))
    sections: list[Section] = []
    noted: set[str] = set()
    for part in chosen:
        section = index.parts[part]
        sections.append(section if section.label not in noted else replace(section, note=""))
        noted.add(section.label)
    return Selection(tuple(sections), len(chosen), len(index.parts), shared)
