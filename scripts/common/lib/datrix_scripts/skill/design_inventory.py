"""The facts /consolidate-to-design needs before it designs anything, read by a script instead of by the model.

REGISTERED TARGETS (exact)
    Every ``datrix-codegen-*`` repository whose ``pyproject.toml`` registers an entry point in the language,
    platform or generator (client and artifact) group is one target of that kind, keyed by the repository name
    after ``datrix-codegen-``. The set is read from registration, never listed by hand, so the next target
    appears here without a change to this module.

DESIGNS (exact)
    Every ``NNN-<slug>.md`` in the design folder (the ``000-`` index excluded): number, title, status, the
    designs it depends on, its line count, and whether an implementation ledger exists for it. A design that
    is implemented or being implemented is never edited, so only the others take an added defect.

NUMBERING (exact)
    The first design is 010 and each next one is 10 higher. The inventory prints the number an appended design
    takes and the free numbers inside each gap, for an insertion.

UNCONVERTED SECTIONS (exact)
    Every ``## N.`` section of every ``consolidated-NNN-*.md`` in the findings folder, with the files it cites
    and the repositories those files sit in. A consolidated file still in the folder is unconverted.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from datrix_scripts.skill.common import read_text
from datrix_scripts.skill.findings import references
from datrix_scripts.skill.findings_assemble import SourceFile, Unit

DESIGN_DIR_PARTS: Final = ("design",)
FIRST_NUMBER: Final = 10
NUMBER_STEP: Final = 10
INSERT_STEP: Final = 5
MAX_DESIGN_LINES: Final = 100
IMPLEMENTED_STATUS: Final = "implemented"
CODEGEN_PREFIX: Final = "datrix-codegen-"
#: Target kind -> the entry-point group whose registration makes a repository one target of that kind.
TARGET_GROUPS: Final[dict[str, str]] = {
    "language": "datrix.languages",
    "platform": "datrix.platforms",
    "generator": "datrix.generators",
}
GAP_PREVIEW: Final = 3

DESIGN_NAME: Final = re.compile(r"^(\d{3,4})-([a-z0-9][a-z0-9-]*)\.md$")
DESIGN_STEM: Final = re.compile(r"\d{3,4}-[a-z0-9][a-z0-9-]*")
_STATUS: Final = re.compile(r"^Status:[ \t]*(.+?)[ \t]*$", re.MULTILINE)
_DEPENDS: Final = re.compile(r"^Depends on:[ \t]*(.*)$", re.MULTILINE)
_TITLE: Final = re.compile(r"^#[ \t]+(.+?)[ \t]*$", re.MULTILINE)
_LINE_SUFFIX: Final = re.compile(r":\d+(?:-\d+)?$")
_REPO: Final = re.compile(r"^(datrix[\w-]*)/")


@dataclass(frozen=True)
class DesignDoc:
    path: Path
    number: int
    stem: str
    title: str
    status: str
    depends: tuple[str, ...]
    lines: int
    in_progress: bool

    @property
    def extendable(self) -> bool:
        """A design that is neither implemented nor being implemented can take another defect."""
        return not self.in_progress and self.status.lower() != IMPLEMENTED_STATUS


def design_dir(workspace: Path) -> Path:
    return workspace.joinpath(*DESIGN_DIR_PARTS)


def ledger_path(workspace: Path, stem: str) -> Path:
    """The implementer's ledger for a design; its presence means the design is being implemented."""
    return workspace / ".tmp" / f"implement-direct-{stem}.md"


def design_text(path: Path) -> str:
    """A design file's text with LF line ends (a Windows editor may have written CRLF, which ``$`` in the
    header patterns does not match)."""
    return read_text(path).replace("\r\n", "\n")


def _first(pattern: re.Pattern[str], text: str) -> str:
    match = pattern.search(text)
    return match.group(1) if match else ""


def parse_design(workspace: Path, path: Path) -> DesignDoc:
    """One design file's header facts."""
    match = DESIGN_NAME.match(path.name)
    if match is None:
        raise ValueError(f"'{path.name}' is not NNN-<slug>.md")
    text = design_text(path)
    return DesignDoc(path, int(match.group(1)), path.stem, _first(_TITLE, text), _first(_STATUS, text),
                     tuple(DESIGN_STEM.findall(_first(_DEPENDS, text))), len(text.splitlines()),
                     ledger_path(workspace, path.stem).is_file())


def load_designs(workspace: Path, directory: Path) -> list[DesignDoc]:
    """Every numbered design in ``directory`` (the ``000-`` index excluded), by number."""
    if not directory.is_dir():
        return []
    paths = [p for p in directory.glob("*.md") if DESIGN_NAME.match(p.name) and not p.name.startswith("000-")]
    return sorted((parse_design(workspace, p) for p in paths), key=lambda doc: doc.number)


def registered_targets(workspace: Path) -> dict[str, tuple[str, ...]]:
    """Target kind -> the keys of the repositories that register an entry point of that kind's group."""
    found: dict[str, list[str]] = {kind: [] for kind in TARGET_GROUPS}
    for pyproject in sorted(workspace.glob(f"{CODEGEN_PREFIX}*/pyproject.toml")):
        groups = _entry_point_groups(tomllib.loads(read_text(pyproject)))
        key = pyproject.parent.name[len(CODEGEN_PREFIX):]
        for kind, group in TARGET_GROUPS.items():
            if groups.get(group):
                found[kind].append(key)
    return {kind: tuple(keys) for kind, keys in found.items()}


def _entry_point_groups(data: dict[str, object]) -> dict[str, object]:
    """The ``[project.entry-points]`` table of a parsed pyproject; empty when the repository has none."""
    project = data.get("project")
    points = project.get("entry-points") if isinstance(project, dict) else None
    return points if isinstance(points, dict) else {}


def next_number(designs: Sequence[DesignDoc]) -> int:
    """The number a design appended after every existing one takes."""
    return max((d.number for d in designs), default=FIRST_NUMBER - NUMBER_STEP) + NUMBER_STEP


def free_gaps(designs: Sequence[DesignDoc]) -> list[tuple[int, int, list[int]]]:
    """For each adjacent pair of designs with free numbers between them: both numbers and the free ones,
    multiples of 5 first (the numbers an insertion should take)."""
    taken = {d.number for d in designs}
    gaps: list[tuple[int, int, list[int]]] = []
    for low, high in zip(designs, designs[1:], strict=False):
        free = [n for n in range(low.number + 1, high.number) if n not in taken]
        free.sort(key=lambda n: (n % INSERT_STEP != 0, n))
        if free:
            gaps.append((low.number, high.number, free))
    return gaps


def unit_text(unit: Unit) -> str:
    return "\n".join(unit.body)


def unit_paths(unit: Unit) -> list[str]:
    """The repository-relative file paths a section cites (line numbers dropped), each once."""
    paths = {_LINE_SUFFIX.sub("", reference) for reference in references(unit_text(unit))}
    return sorted(path for path in paths if "/" in path)


def repos_of(paths: Sequence[str]) -> list[str]:
    """The repositories ``paths`` sit in."""
    return sorted({match.group(1) for path in paths if (match := _REPO.match(path))})


def consolidated_units(sources: Sequence[SourceFile]) -> list[tuple[SourceFile, Unit]]:
    return [(source, unit) for source in sources if source.consolidated for unit in source.units]


def render_inventory(workspace: Path, targets: dict[str, tuple[str, ...]], designs: Sequence[DesignDoc],
                     sources: Sequence[SourceFile]) -> str:
    """The inventory as markdown."""
    lines = ["# Design inventory", "", "## Registered targets (from entry points)", ""]
    lines += [f"- {kind}: {', '.join(keys) or 'none'}" for kind, keys in targets.items()]
    lines += ["", "## Designs", ""]
    if designs:
        lines += ["| Design | Status | Lines | Depends on | Extendable |", "|---|---|---|---|---|"]
        lines += [f"| {d.stem} | {d.status or 'none'} | {d.lines}{' OVER' if d.lines > MAX_DESIGN_LINES else ''} | "
                  f"{', '.join(d.depends) or 'none'} | {'yes' if d.extendable else 'no'} |" for d in designs]
    else:
        lines.append("None yet: the first design is 010.")
    lines += ["", "## Numbering", "", f"Appended design: {next_number(designs):03d}."]
    lines += [f"- between {low:03d} and {high:03d}: {', '.join(f'{n:03d}' for n in free[:GAP_PREVIEW])}"
              for low, high, free in free_gaps(designs)]
    units = consolidated_units(sources)
    lines += ["", f"## Unconverted sections ({len(units)} in {len({s.name for s, _ in units})} file(s))", "",
              "| Id | File | Section | Cited files | Repositories |", "|---|---|---|---|---|"]
    for source, unit in units:
        paths = unit_paths(unit)
        lines.append(f"| {unit.unit_id} | {source.name} | {unit.title} | {len(paths)} | "
                     f"{', '.join(repos_of(paths)) or 'none'} |")
    return "\n".join(lines) + "\n"
