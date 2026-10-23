"""Local-model leads for /consolidate-to-design: does each defect still hold, and which sections make one design?

VERIFY (a lead from a local model; exact where marked)
    Exact: every file a section cites that no longer exists. Lead: for each section whose cited files exist, a
    local model reads those files and says STILL HOLDS, FIXED or UNCLEAR about the defect, citing ``path:line``;
    citations and quotes are checked against what it was sent. The skill proves a verdict before acting on it.

PLAN (a lead from a local model; the skill corrects it)
    Each consolidated file's sections are grouped into fix shapes (sections one implementer fixes with one
    change), then shapes that are really one are merged and a shape that belongs to an existing, extendable
    design is named to it. Every id the model answers is checked: an invented id is dropped and a section it
    does not place becomes its own flagged shape. The plan lists, per shape, its size and the registered
    targets its cited files sit in, which is the evidence for the design's target consistency table.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from datrix_scripts.local_llm import LocalLlmPool
from datrix_scripts.local_reading import ReadScope, ReadScopeError, ask_local, read_section
from datrix_scripts.skill.common import ContentFilter, ask_json, object_list, parallel, section_body, string_list
from datrix_scripts.skill.design_inventory import (
    CODEGEN_PREFIX,
    DesignDoc,
    consolidated_units,
    repos_of,
    unit_paths,
    unit_text,
)
from datrix_scripts.skill.findings_assemble import SourceFile, Unit

VERDICT_HOLDS: Final = "STILL HOLDS"
VERDICT_FIXED: Final = "FIXED"
VERDICT_UNCLEAR: Final = "UNCLEAR"
VERDICTS: Final = (VERDICT_HOLDS, VERDICT_FIXED, VERDICT_UNCLEAR)
MAX_FILES_PER_SECTION: Final = 6
CLAIM_LINES: Final = 40
EXCERPT_LINES: Final = 6
EXCERPT_PATHS: Final = 6
LARGE_SHAPE_SECTIONS: Final = 8
MERGE_LIMIT_SECTIONS: Final = 6
LARGE_SHAPE_FILES: Final = 25

VERIFY_QUESTION: Final = (
    "A report claims this defect exists in the files below:\n\n{claim}\n\nDoes the defect still exist in the "
    "files as they are now? Begin your answer with exactly one of STILL HOLDS, FIXED or UNCLEAR on its own "
    "line, then give the evidence in at most 6 lines, citing path:line for every claim.")

SHAPE_SYSTEM: Final = (
    "You group the defect sections of one findings theme from Datrix, a multi-language code generator, into fix "
    "shapes. A fix shape is a set of sections that one implementer fixes with one change: the same root cause, "
    "the same seam, the same remedy, the same generator or template family, or the same files. One shape is "
    "written up as one design of about 100 lines, which holds about four or five sections, so group every "
    "section that shares a seam or remedy with another into one shape, up to about six sections. Make a "
    "section a shape of its own only when no other section of the theme shares its seam or remedy. Answer "
    "shapes: each with a title naming the seam and the units (section ids) it holds. Every section id belongs "
    "to exactly one shape.")

SHAPE_SCHEMA: Final[dict[str, object]] = {
    "type": "object",
    "properties": {"shapes": {"type": "array", "items": {
        "type": "object",
        "properties": {"title": {"type": "string"}, "units": {"type": "array", "items": {"type": "string"}}},
        "required": ["title", "units"]}}},
    "required": ["shapes"],
}

GLOBAL_SYSTEM: Final = (
    "You review the fix shapes proposed for a findings inbox from Datrix, a multi-language code generator. "
    "Name every set of shapes that are really ONE fix (the same root cause, seam or remedy, across different "
    "files or targets, or the same generator or template family) as one merge: into (the id that keeps them) "
    "and from (the ids merged into it); a merged shape holds at most about six sections. Then name "
    "every shape that belongs in an existing design listed below as one extension: shape and design (the design "
    "id). Answer empty lists when there are none. Shapes that merely share a package are not one fix.")

GLOBAL_SCHEMA: Final[dict[str, object]] = {
    "type": "object",
    "properties": {
        "merges": {"type": "array", "items": {
            "type": "object",
            "properties": {"into": {"type": "string"}, "from": {"type": "array", "items": {"type": "string"}}},
            "required": ["into", "from"]}},
        "extends": {"type": "array", "items": {
            "type": "object",
            "properties": {"shape": {"type": "string"}, "design": {"type": "string"}},
            "required": ["shape", "design"]}},
    },
    "required": ["merges", "extends"],
}


# --- verify --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Verification:
    unit_id: str
    source: str
    title: str
    verdict: str
    evidence: str
    gone: tuple[str, ...]


def _verdict(answer: str) -> str:
    first = answer.strip().splitlines()[0].strip().upper() if answer.strip() else ""
    return next((verdict for verdict in VERDICTS if first.startswith(verdict)), VERDICT_UNCLEAR)


def _verify_unit(workspace: Path, scope: ReadScope, pool: LocalLlmPool, content: ContentFilter,
                 source: SourceFile, unit: Unit) -> Verification:
    paths = unit_paths(unit)
    present = [path for path in paths if (workspace / path).is_file()]
    gone = tuple(path for path in paths if path not in present)
    if not present:
        reason = "no cited file exists any more" if paths else "cites no file"
        return Verification(unit.unit_id, source.name, unit.title, VERDICT_UNCLEAR, reason, gone)
    claim = section_body(content.section(f"{unit.unit_id} {unit.title}", unit_text(unit)), 1, CLAIM_LINES)
    try:
        sections = [read_section(scope, path) for path in scope.files(present[:MAX_FILES_PER_SECTION])]
    except ReadScopeError as exc:
        return Verification(unit.unit_id, source.name, unit.title, VERDICT_UNCLEAR, f"Not read: {exc}", gone)
    answer = ask_local(pool, VERIFY_QUESTION.format(claim=claim), sections)
    return Verification(unit.unit_id, source.name, unit.title, _verdict(answer.text), answer.render(), gone)


def verify_units(workspace: Path, pool: LocalLlmPool, sources: Sequence[SourceFile]) -> list[Verification]:
    """A verdict lead for every consolidated section."""
    scope = ReadScope(workspace)
    content = ContentFilter(workspace)
    return parallel(consolidated_units(sources),
                    lambda pair: _verify_unit(workspace, scope, pool, content, pair[0], pair[1]))


def exact_gone(sources: Sequence[SourceFile], workspace: Path) -> list[Verification]:
    """Without a model: the sections whose cited files are all gone, or which cite none."""
    found: list[Verification] = []
    for source, unit in consolidated_units(sources):
        paths = unit_paths(unit)
        gone = tuple(path for path in paths if not (workspace / path).is_file())
        if not paths or len(gone) == len(paths):
            reason = "cites no file" if not paths else "no cited file exists any more"
            found.append(Verification(unit.unit_id, source.name, unit.title, VERDICT_UNCLEAR, reason, gone))
    return found


def render_verification(results: Sequence[Verification], note: str = "") -> str:
    """The verdicts as markdown: counts first, then each section with its evidence."""
    lines = ["# Design verification", "", "Every verdict is a lead from a local model: prove it with a ranged "
             "read of the cited lines before acting on it.", ""]
    if note:
        lines += [note, ""]
    counts = {verdict: sum(1 for r in results if r.verdict == verdict) for verdict in VERDICTS}
    lines += [", ".join(f"{verdict}: {count}" for verdict, count in counts.items()), ""]
    for result in results:
        lines += [f"### {result.unit_id} ({result.source}): {result.verdict} -- {result.title}", ""]
        if result.gone:
            lines += ["Cited files that no longer exist (exact): " + ", ".join(f"`{p}`" for p in result.gone), ""]
        lines += [result.evidence, ""]
    return "\n".join(lines)


# --- plan ----------------------------------------------------------------------------------------------


@dataclass
class Shape:
    key: str
    title: str
    units: list[str]
    extends: str = ""
    review: list[str] = field(default_factory=list)


def _excerpt(unit: Unit) -> str:
    cites = ", ".join(unit_paths(unit)[:EXCERPT_PATHS])
    return "\n".join([f"Section {unit.unit_id}: {unit.title}", *unit.body[:EXCERPT_LINES], f"Cites: {cites}"])


def _theme_text(source: SourceFile) -> str:
    return "\n\n".join([f"Theme: {source.title}", *(_excerpt(unit) for unit in source.units)])


def _file_shapes(source: SourceFile, answer: dict[str, object]) -> list[tuple[str, list[str], list[str]]]:
    """(title, unit ids, review notes) per shape of one file, every answered id checked."""
    valid = {unit.unit_id: unit for unit in source.units}
    placed: set[str] = set()
    shapes: list[tuple[str, list[str], list[str]]] = []
    for item in object_list(answer.get("shapes")):
        ids = [i for i in dict.fromkeys(string_list(item.get("units"))) if i in valid and i not in placed]
        placed.update(ids)
        if ids:
            shapes.append((str(item.get("title", "")).strip() or valid[ids[0]].title, ids, []))
    for unit_id, unit in valid.items():
        if unit_id not in placed:
            shapes.append((unit.title, [unit_id], ["the model placed this section in no shape: confirm"]))
    return shapes


def _apply_global(shapes: dict[str, Shape], designs: Sequence[DesignDoc], answer: dict[str, object]) -> None:
    for merge in object_list(answer.get("merges")):
        raw_from = merge.get("from")
        keys = [str(merge.get("into", "")).strip(), *(str(k).strip() for k in raw_from)] \
            if isinstance(raw_from, list) else []
        present = list(dict.fromkeys(key for key in keys if key in shapes))
        for key in present[1:]:
            home = shapes[present[0]]
            if len(home.units) + len(shapes[key].units) > MERGE_LIMIT_SECTIONS:
                home.review.append(f"the model merges '{shapes[key].title}' in, left apart: the design would "
                                   f"exceed {MERGE_LIMIT_SECTIONS} sections")
                continue
            folded = shapes.pop(key)
            home.units.extend(folded.units)
            home.review.append(f"merged in '{folded.title}' (model): confirm it is one fix")
    extendable = {d.stem for d in designs if d.extendable}
    for extension in object_list(answer.get("extends")):
        shape = shapes.get(str(extension.get("shape", "")).strip())
        stem = str(extension.get("design", "")).strip()
        if shape is not None and stem in extendable:
            shape.extends = stem
            shape.review.append(f"the model places this in existing design {stem}: confirm")


def _catalogue(shapes: dict[str, Shape], designs: Sequence[DesignDoc]) -> str:
    lines = [f"{key}: {shape.title} ({len(shape.units)} section(s))" for key, shape in shapes.items()]
    lines += ["", "Existing designs you may extend:"]
    lines += [f"{d.stem}: {d.title}" for d in designs if d.extendable] or ["none"]
    return "\n".join(lines)


def draft_shapes(workspace: Path, pool: LocalLlmPool | None, sources: Sequence[SourceFile],
                 designs: Sequence[DesignDoc]) -> list[Shape]:
    """The fix shapes a local model proposes; without ``pool``, one shape per consolidated file."""
    files = [source for source in sources if source.consolidated]
    parts: list[list[tuple[str, list[str], list[str]]]]
    if pool is None:
        parts = [[(s.title, [u.unit_id for u in s.units], ["no model was asked (--no-model): split by remedy"])]
                 for s in files]
    else:
        content = ContentFilter(workspace)

        def ask(source: SourceFile) -> list[tuple[str, list[str], list[str]]]:
            body = section_body(content.section(source.name, _theme_text(source)))
            return _file_shapes(source, ask_json(pool, SHAPE_SYSTEM, body, SHAPE_SCHEMA))

        parts = parallel(files, ask)
    shapes: dict[str, Shape] = {}
    for title, ids, review in (shape for part in parts for shape in part):
        key = f"S{len(shapes) + 1}"
        shapes[key] = Shape(key, title, ids, review=review)
    if pool is not None and shapes:
        body = section_body(ContentFilter(workspace).section("shapes", _catalogue(shapes, designs)))
        _apply_global(shapes, designs, ask_json(pool, GLOBAL_SYSTEM, body, GLOBAL_SCHEMA))
    return list(shapes.values())


def targets_named(paths: Sequence[str], targets: dict[str, tuple[str, ...]]) -> dict[str, list[str]]:
    """Target kind -> the registered targets whose repository holds one of ``paths``."""
    return {kind: [key for key in keys if any(p.startswith(f"{CODEGEN_PREFIX}{key}/") for p in paths)]
            for kind, keys in targets.items()}


def render_shapes(shapes: Sequence[Shape], sources: Sequence[SourceFile], targets: dict[str, tuple[str, ...]]) -> str:
    """The plan as markdown for the skill to correct: sizes, reach, and a REVIEW line per model decision."""
    units = {unit.unit_id: unit for _source, unit in consolidated_units(sources)}
    lines = ["# Design plan", "", f"{len(units)} section(s) into {len(shapes)} proposed fix shape(s). A shape is "
             "what ONE design carries and a 100-line design holds about four or five sections: a plan with "
             "nearly as many shapes as sections has not grouped. Settle every REVIEW line, then write the "
             "designs.", ""]
    for shape in shapes:
        members = [units[unit_id] for unit_id in shape.units if unit_id in units]
        paths = sorted({path for unit in members for path in unit_paths(unit)})
        size = f"{len(members)} section(s), {sum(len(u.body) for u in members)} finding lines, {len(paths)} cited files"
        large = len(members) > LARGE_SHAPE_SECTIONS or len(paths) > LARGE_SHAPE_FILES
        lines += [f"## {shape.key}: {shape.title}", "", f"Size: {size}{' -- likely over 100 lines: split' if large else ''}"]
        reach = {kind: keys for kind, keys in targets_named(paths, targets).items() if keys}
        lines.append("Targets reached by cited files: " + ("; ".join(f"{k}: {', '.join(v)}" for k, v in reach.items())
                                                           or "none"))
        lines += [f"Repositories: {', '.join(repos_of(paths)) or 'none'}"]
        if shape.extends:
            lines.append(f"Extends existing design: {shape.extends}")
        lines += [f"- {unit.unit_id}: {unit.title}" for unit in members]
        lines += [f"REVIEW: {note}" for note in shape.review]
        lines.append("")
    return "\n".join(lines)
