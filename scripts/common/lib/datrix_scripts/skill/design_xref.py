"""The cross-design index /verify-design reads instead of grepping the design folder name by name.

DECISION REFERENCES (exact)
    Every ``NNN Dk`` and ``NNN §k`` in a design names design NNN's decision or section k. A reference to a design
    number no file has, or to a decision the named design has no ``### Dk`` heading for, is an error. A reference
    to a higher-numbered design is listed for review: a pointer ("320 deletes it") is fine, a premise is not.

ALLOCATIONS (exact)
    A diagnostic code (``DBO001``, ``BLT003.regex_pattern``) or a backticked upper-snake name (``CHECK_ADDED``)
    written in a design's ``Size`` section is allocated by that design. A name two designs allocate is an error,
    and so is a use of an allocated name in a design numbered below the one that allocates it.

INDEX (exact)
    Every diagnostic code and backticked upper-snake name, with the design allocating it and every design naming
    it, so a reviewer checks what each name means in each design without a search per name.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from datrix_scripts.skill.design_inventory import DesignDoc, design_text, load_designs

SIZE_HEADING: Final = re.compile(r"^##[ \t]+(?:\d+\.[ \t]*)?Size[ \t]*$", re.MULTILINE | re.IGNORECASE)
_NEXT_SECTION: Final = re.compile(r"^##[ \t]", re.MULTILINE)
_DECISION_REFERENCE: Final = re.compile(r"\b(\d{3}) (D\d+|§\d+)\b")
_DECISION_HEADING: Final = r"^###[ \t]+{decision}\b"
_DIAGNOSTIC: Final = re.compile(r"\b[A-Z]{3}\d{3}(?:\.[a-z][a-z_]*)?\b")
_UPPER_SNAKE: Final = re.compile(r"`([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)`")


@dataclass(frozen=True)
class XrefProblem:
    design: str
    line: int
    message: str


@dataclass(frozen=True)
class NameEntry:
    name: str
    allocated_by: tuple[str, ...]
    named_in: tuple[str, ...]


@dataclass
class Xref:
    errors: list[XrefProblem] = field(default_factory=list)
    pointers: list[XrefProblem] = field(default_factory=list)
    names: list[NameEntry] = field(default_factory=list)


def _size_section(text: str) -> str:
    """The body of the design's ``Size`` section; empty when it has none."""
    heading = SIZE_HEADING.search(text)
    if heading is None:
        return ""
    following = _NEXT_SECTION.search(text, heading.end())
    return text[heading.end(): following.start() if following else len(text)]


def _names(text: str) -> set[str]:
    return set(_DIAGNOSTIC.findall(text)) | set(_UPPER_SNAKE.findall(text))


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _reference_problems(design: DesignDoc, text: str, match: re.Match[str], target: DesignDoc | None,
                        target_text: str) -> tuple[list[XrefProblem], list[XrefProblem]]:
    """The errors and the later-design pointers one ``NNN Dk`` / ``NNN §k`` reference makes."""
    line, part = _line_of(text, match.start()), match.group(2)
    if target is None:
        return [XrefProblem(design.stem, line, f"'{match.group(0)}' names design {match.group(1)}, which no file "
                                               "in the design folder has")], []
    errors = []
    if part.startswith("D") and not re.search(_DECISION_HEADING.format(decision=part), target_text, re.MULTILINE):
        errors.append(XrefProblem(design.stem, line, f"'{match.group(0)}': {target.stem} has no '### {part}' heading"))
    pointers = []
    if target.number > design.number:
        pointers.append(XrefProblem(design.stem, line, f"'{match.group(0)}' points at a later design: a pointer "
                                                       "is fine, a premise is not"))
    return errors, pointers


def _decision_references(design: DesignDoc, texts: dict[str, str], by_number: dict[int, DesignDoc],
                         xref: Xref) -> None:
    text = texts[design.stem]
    for match in _DECISION_REFERENCE.finditer(text):
        target = by_number.get(int(match.group(1)))
        errors, pointers = _reference_problems(design, text, match, target, texts[target.stem] if target else "")
        xref.errors += errors
        xref.pointers += pointers


def _allocators(designs: Sequence[DesignDoc], texts: dict[str, str]) -> dict[str, list[DesignDoc]]:
    """Each name a design's Size section writes, with the designs that write it, by number."""
    allocated: dict[str, list[DesignDoc]] = {}
    for design in designs:
        for name in _names(_size_section(texts[design.stem])):
            allocated.setdefault(name, []).append(design)
    return allocated


def _namers(designs: Sequence[DesignDoc], texts: dict[str, str]) -> dict[str, list[str]]:
    """Each name, with every design that names it anywhere, by number."""
    named: dict[str, list[str]] = {}
    for design in designs:
        for name in _names(texts[design.stem]):
            named.setdefault(name, []).append(design.stem)
    return named


def _allocation_errors(name: str, owners: Sequence[DesignDoc], designs: Sequence[DesignDoc],
                       named_in: Sequence[str]) -> list[XrefProblem]:
    first = owners[0]
    errors = [XrefProblem(owner.stem, 0, f"allocates {name}, which {first.stem} also allocates in its Size section")
              for owner in owners[1:]]
    errors += [XrefProblem(design.stem, 0, f"names {name} before {first.stem}, which allocates it")
               for design in designs if design.number < first.number and design.stem in named_in]
    return errors


def build_xref(workspace: Path, directory: Path) -> Xref:
    """The cross-design index of every design in ``directory``."""
    designs = load_designs(workspace, directory)
    texts = {design.stem: design_text(design.path) for design in designs}
    by_number = {design.number: design for design in designs}
    xref = Xref()
    for design in designs:
        _decision_references(design, texts, by_number, xref)
    allocated, named = _allocators(designs, texts), _namers(designs, texts)
    for name, owners in sorted(allocated.items()):
        xref.errors += _allocation_errors(name, owners, designs, named.get(name, []))
    xref.names = [NameEntry(name, tuple(owner.stem for owner in allocated.get(name, [])), tuple(stems))
                  for name, stems in sorted(named.items())]
    return xref


def _problem_lines(problems: Sequence[XrefProblem]) -> list[str]:
    return [f"- {p.design}{f':{p.line}' if p.line else ''}: {p.message}" for p in problems]


def render_xref(xref: Xref) -> str:
    lines = ["# Design cross-reference", ""]
    lines += [f"## Errors ({len(xref.errors)})", ""] + (_problem_lines(xref.errors) or ["None."]) + [""]
    lines += [f"## Pointers at later designs, to judge ({len(xref.pointers)})", ""]
    lines += (_problem_lines(xref.pointers) or ["None."]) + [""]
    lines += ["## Names", "", "| Name | Allocated by | Named in |", "|---|---|---|"]
    lines += [f"| `{entry.name}` | {', '.join(entry.allocated_by) or '-'} | {', '.join(entry.named_in)} |"
              for entry in xref.names]
    return "\n".join(lines) + "\n"
