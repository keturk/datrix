"""The exact checks of /consolidate-to-design: is the design folder well formed, and may a converted
consolidated file be deleted?

DESIGN CHECK (exact)
    Per design: the number (three digits, 010 or more, unique); at most 100 lines; a ``Status:`` and a
    ``Depends on:`` line (the label plain or bold, the value possibly wrapped onto further lines), every
    dependency an existing LOWER-numbered design; no mention of any design with an
    equal or higher number; every design guideline G1..Gn answered under ``## Design guidelines conformance``
    (the set is read from design-principles.md, as the edit guard reads it); no placeholder, deferral or
    reference to a consolidated file or findings file; and target consistency as a set comparison -- when a
    design names a ``datrix-codegen-<key>`` repository of a target kind (language, platform, generator), its
    ``## Target consistency`` section names every registered target of that kind.

CLOSE (exact)
    A consolidated file is deleted only when the design check passes and every file path cited by each of its
    sections (except the sections the caller proved already fixed) and exists in the workspace appears in some
    design. A cited path that no design mentions means a defect was not carried; nothing is deleted.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from datrix_scripts.skill.common import AssistError, read_text
from datrix_scripts.skill.design_inventory import (
    CODEGEN_PREFIX,
    DEPENDS_LABEL,
    DESIGN_STEM,
    FIRST_NUMBER,
    MAX_DESIGN_LINES,
    STATUS_LABEL,
    DesignDoc,
    design_text,
    header_value,
    load_designs,
    registered_targets,
    unit_paths,
)
from datrix_scripts.skill.findings_source import SourceFile, parse_source

GUIDELINES_PARTS: Final = ("datrix", "docs", "architecture", "design-principles.md")
CONFORMANCE_HEADING: Final = "Design guidelines conformance"
CONSISTENCY_HEADING: Final = "Target consistency"
TAIL_COMPONENTS: Final = 2

_GUIDELINE_DEFINITION: Final = re.compile(r"^\*\*G(\d+)\.", re.MULTILINE)
_ANSWER: Final = re.compile(r"^[ \t]*[-*][ \t]+\**G(\d+)\**[ \t]*:\**[ \t]*\S", re.MULTILINE)
_PLACEHOLDER: Final = re.compile(
    r"\bTBD\b|\bTODO\b|verify during implementation|\bfor now\b|\blater phase\b|\bdecide later\b", re.IGNORECASE)
_FINDING_REFERENCE: Final = re.compile(
    r"consolidated-\d{3}|\bfindings[/\\]|\bfindings? (?:file|report|inbox)\b", re.IGNORECASE)
_EFFORT_FIGURE: Final = re.compile(
    r"\b\d+(?:[-–]\d+)?[ \t]*(?:person-)?(?:hours?|days?|weeks?|sprints?)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Problem:
    design: str
    message: str
    #: ``review`` problems may be false positives (a retention period in days); the others never are.
    review: bool = False


def guideline_ids(workspace: Path) -> set[int]:
    """The design guidelines every design must answer, read from the architecture document that defines them."""
    path = workspace.joinpath(*GUIDELINES_PARTS)
    if not path.is_file():
        raise AssistError(f"The design guidelines document {path} does not exist. Run the check in a workspace "
                          "that holds datrix/docs/architecture/design-principles.md.")
    ids = {int(number) for number in _GUIDELINE_DEFINITION.findall(read_text(path))}
    if not ids:
        raise AssistError(f"{path} defines no guideline of the form '**G1. ...'; expected G1..Gn.")
    return ids


def _section(text: str, heading: str) -> str:
    """The body under ``## <heading>`` up to the next ``## ``; empty when the design has no such section."""
    match = re.search(rf"^##[ \t]+{re.escape(heading)}[ \t]*$(.*?)(?=^##[ \t]|\Z)", text,
                      re.MULTILINE | re.DOTALL | re.IGNORECASE)
    return match.group(1) if match else ""


def _numbering(designs: Sequence[DesignDoc]) -> list[Problem]:
    problems = [Problem(d.stem, f"number {d.number:03d} is below {FIRST_NUMBER:03d}")
                for d in designs if d.number < FIRST_NUMBER]
    seen: dict[int, str] = {}
    for design in designs:
        if design.number in seen:
            problems.append(Problem(design.stem, f"shares number {design.number:03d} with {seen[design.number]}"))
        seen.setdefault(design.number, design.stem)
    return problems


def _dependencies(design: DesignDoc, line: str, by_stem: dict[str, DesignDoc]) -> list[Problem]:
    problems: list[Problem] = []
    for stem in DESIGN_STEM.findall(line):
        target = by_stem.get(stem)
        if target is None:
            problems.append(Problem(design.stem, f"depends on {stem}, which does not exist"))
        elif target.number >= design.number:
            problems.append(Problem(design.stem, f"depends on {stem}, which is not lower-numbered"))
    return problems


def _header(design: DesignDoc, text: str, by_stem: dict[str, DesignDoc]) -> list[Problem]:
    problems: list[Problem] = []
    if design.lines > MAX_DESIGN_LINES:
        problems.append(Problem(design.stem, f"{design.lines} lines; at most {MAX_DESIGN_LINES}. Split it by seam"))
    if not header_value(text, STATUS_LABEL):
        problems.append(Problem(design.stem, "no 'Status:' line"))
    depends = header_value(text, DEPENDS_LABEL)
    if depends is None:
        problems.append(Problem(design.stem, "no 'Depends on:' line (write 'Depends on: none')"))
        return problems
    return problems + _dependencies(design, depends, by_stem)


def _forward_references(design: DesignDoc, text: str, designs: Sequence[DesignDoc]) -> list[Problem]:
    return [Problem(design.stem, f"names {other.stem}, which has an equal or higher number")
            for other in designs if other.stem != design.stem and other.number >= design.number
            and other.stem in text]


def _conformance(design: DesignDoc, text: str, required: set[int]) -> list[Problem]:
    answered = {int(number) for number in _ANSWER.findall(_section(text, CONFORMANCE_HEADING))}
    missing = sorted(required - answered)
    if not missing:
        return []
    return [Problem(design.stem, f"'{CONFORMANCE_HEADING}' lacks answers for "
                                 + ", ".join(f"G{number}" for number in missing))]


def _wording(design: DesignDoc, text: str) -> list[Problem]:
    problems = [Problem(design.stem, f"placeholder or deferral '{m.group(0)}'") for m in _PLACEHOLDER.finditer(text)]
    problems += [Problem(design.stem, f"refers to a consolidated or findings file: '{m.group(0)}'")
                 for m in _FINDING_REFERENCE.finditer(text)]
    problems += [Problem(design.stem, f"effort figure '{m.group(0)}' (a retention period is fine; a size is a "
                                      "census, never hours or days)", review=True)
                 for m in _EFFORT_FIGURE.finditer(text)]
    return problems


def _names_target(text: str, key: str) -> bool:
    return f"{CODEGEN_PREFIX}{key}" in text


def _mentions_target(section: str, key: str) -> bool:
    return _names_target(section, key) or re.search(rf"\b{re.escape(key)}\b", section, re.IGNORECASE) is not None


def _target_consistency(design: DesignDoc, text: str, targets: dict[str, tuple[str, ...]]) -> list[Problem]:
    section = _section(text, CONSISTENCY_HEADING)
    outside = text.replace(section, "")
    problems: list[Problem] = []
    for kind, keys in targets.items():
        reached = [key for key in keys if _names_target(outside, key)]
        absent = [key for key in keys if not _mentions_target(section, key)]
        if reached and absent:
            problems.append(Problem(design.stem, f"names {kind} target(s) {', '.join(reached)} but its "
                                                 f"'{CONSISTENCY_HEADING}' section omits registered {kind} "
                                                 f"target(s): {', '.join(absent)}"))
    return problems


def check_designs(workspace: Path, directory: Path) -> list[Problem]:
    """Every problem of every design in ``directory``."""
    designs = load_designs(workspace, directory)
    by_stem = {d.stem: d for d in designs}
    required = guideline_ids(workspace)
    targets = registered_targets(workspace)
    problems = _numbering(designs)
    for design in designs:
        text = design_text(design.path)
        problems += _header(design, text, by_stem)
        problems += _forward_references(design, text, designs)
        problems += _conformance(design, text, required)
        problems += _wording(design, text)
        problems += _target_consistency(design, text, targets)
    return problems


def render_problems(problems: Sequence[Problem], design_count: int) -> str:
    if not problems:
        return f"PASS: {design_count} design(s) well formed.\n"
    lines = [f"FAIL: {len(problems)} problem(s) in {design_count} design(s).", ""]
    lines += [f"- {p.design}: {p.message}{' [review]' if p.review else ''}" for p in problems]
    return "\n".join(lines) + "\n"


# --- close ---------------------------------------------------------------------------------------------


@dataclass
class CloseResult:
    design_problems: list[Problem] = field(default_factory=list)
    uncarried: dict[str, list[str]] = field(default_factory=dict)
    uncheckable: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not (self.design_problems or self.uncarried)


def _covered(path: str, designs_text: str) -> bool:
    tail = "/".join(path.split("/")[-TAIL_COMPONENTS:])
    return path in designs_text or tail in designs_text


def _consolidated(files: Sequence[Path]) -> list[SourceFile]:
    sources = [parse_source(path) for path in files]
    raw = [source.name for source in sources if not source.consolidated]
    if raw:
        raise AssistError(f"Not consolidated files: {', '.join(raw)}. Pass consolidated-NNN-<slug>.md files only.")
    return sources


def _carried(workspace: Path, source: SourceFile, fixed: set[str], designs_text: str, result: CloseResult) -> None:
    """Add to ``result`` each unfixed section of ``source`` whose cited files no design mentions.

    Only a cited path that exists in the workspace has to appear in a design: an abbreviated path
    (``.../x.py``) or a deleted file cannot be matched, and a section left with no existing cited file
    is listed for the skill to confirm."""
    for unit in source.units:
        if unit.unit_id in fixed:
            continue
        paths = [path for path in unit_paths(unit) if (workspace / path).is_file()]
        missing = [path for path in paths if not _covered(path, designs_text)]
        if not paths:
            result.uncheckable.append(f"{unit.unit_id} ({source.name}): cites no file that exists")
        elif missing:
            result.uncarried[unit.unit_id] = missing


def close_findings(workspace: Path, directory: Path, files: Sequence[Path], fixed: set[str],
                   apply: bool) -> CloseResult:
    """Check ``files`` against the designs; delete them when ``apply`` and everything passes."""
    sources = _consolidated(files)
    unit_ids = {unit.unit_id for source in sources for unit in source.units}
    unknown = sorted(fixed - unit_ids)
    if unknown:
        raise AssistError(f"--fixed names sections that are not in the files given: {', '.join(unknown)}. "
                          f"Expected ids such as {sorted(unit_ids)[0]}.")
    designs_text = "\n".join(design_text(d.path) for d in load_designs(workspace, directory)).replace("\\", "/")
    result = CloseResult(design_problems=[p for p in check_designs(workspace, directory) if not p.review])
    for source in sources:
        _carried(workspace, source, fixed, designs_text, result)
    if apply and result.passed:
        for path in files:
            path.unlink()
            result.deleted.append(path.name)
    return result


def render_close(result: CloseResult, apply: bool) -> str:
    if result.design_problems:
        lines = ["FAIL: the designs have problems; nothing deleted.", ""]
        lines += [f"- {p.design}: {p.message}" for p in result.design_problems]
    elif result.uncarried:
        lines = ["FAIL: these sections cite files no design mentions, so a defect was not carried; nothing "
                 "deleted. Carry it, or pass --fixed <id> when the code proves it already fixed.", ""]
        lines += [f"- {unit_id}: {', '.join(f'`{m}`' for m in missing)}"
                  for unit_id, missing in result.uncarried.items()]
    else:
        verb = f"deleted {', '.join(result.deleted)}" if result.deleted else "ready to delete (run with --apply)"
        lines = [f"PASS: every cited file of every unfixed section is in a design; {verb}."]
    if result.uncheckable:
        lines += ["", "Sections with no cited file that exists, which this check cannot prove carried; confirm each "
                      "yourself:"]
        lines += [f"- {entry}" for entry in result.uncheckable]
    if apply and not result.passed:
        lines.append("--apply was given but nothing was deleted.")
    return "\n".join(lines) + "\n"
