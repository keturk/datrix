"""Plan and assemble a findings consolidation, so /consolidate-findings reviews a plan instead of reading
every findings file in full and typing it out again.

UNITS (exact)
    Every findings file splits into units with a stable id. A raw (agent-written) file is one unit whose
    id is its file stem. A consolidated file is one unit per ``## `` section, ``C009.1``, ``C009.2``, ...
    in order (a consolidated file with no ``## `` section is the one unit ``C009.1``). A unit's text is
    the source's own lines; nothing is summarised.

PLAN (a lead from a local model; the skill corrects it)
    For each raw unit a local model names the existing theme it belongs to (and a section it duplicates)
    or a new theme; a second ask names themes that are one theme. The script turns the answers into
    ``findings-plan.json`` (themes, each an ordered list of sections, each a list of unit ids) and
    ``findings-plan.md``, the view the skill reviews. Every answer is checked: an id the model invents is
    dropped, and a raw unit it does not place becomes its own theme, flagged.

ASSEMBLE (exact)
    From the plan the skill approved: a plan that drops, repeats or invents a unit is refused. Each theme
    file is written by carrying every unit's lines verbatim (headings demoted under the section heading,
    cp1252 mojibake restored). A kept file keeps its preamble and takes in the Where and Related lines of
    the files folded into it; every ``consolidated-NNN`` reference to a folded or renamed file is
    repointed. Output carrying a registered customer term is refused. Every non-blank source line must
    survive in the output before anything is written; with ``--apply`` the files are written, the
    no-loss check of ``findings.check_consolidation`` runs, and the superseded sources are deleted only
    when it passes.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from datrix_scripts.local_llm import LocalLlmPool
from datrix_scripts.skill.common import (
    FENCE,
    AssistError,
    ContentFilter,
    ask_json,
    markdown_sections,
    object_list,
    parallel,
    read_text,
    section_body,
)
from datrix_scripts.skill.findings import (
    CONSOLIDATED_PREFIX,
    ConsolidationCheck,
    check_consolidation,
    finding_files,
)

LOG = logging.getLogger(__name__)

NEW_THEME = "NEW"
MAX_SECTIONS_PER_THEME = 12
PLACEMENT_BATCH = 6
UNIT_EXCERPT_LINES = 24
SLUG_MAX_CHARS = 60
ALSO_REPORTED = "**Also reported as:**"
PREAMBLE_SCOPE = "**Scope:**"
PREAMBLE_WHERE = "**Where:**"
PREAMBLE_RELATED = "**Related:**"
_MERGED_PREAMBLE = (PREAMBLE_SCOPE, PREAMBLE_WHERE, PREAMBLE_RELATED)

_CONSOLIDATED_NAME = re.compile(r"^consolidated-(\d{3})-([a-z0-9-]+)\.md$")
_REFERENCE = re.compile(r"consolidated-(\d{3})(-[a-z0-9-]+)?(\.md)?")
_SECTION_NUMBER = re.compile(r"^\d+\.\s+")
_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_NOT_SLUG = re.compile(r"[^a-z0-9]+")
_REPO = re.compile(r"\b(datrix(?:-[a-z]+)*)/")
#: A UTF-8 sequence read as cp1252: a lead byte character followed by one or two continuation characters.
_MOJIBAKE_RUN = re.compile(r"[Â-ï][^\x00-\x7f]{1,2}")
#: The one common sequence cp1252 cannot encode back (0x9d is undefined there).
_RIGHT_QUOTE_MOJIBAKE = ("â€\u009d", "”")


# --- units --------------------------------------------------------------------------------------------


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


def _units_by_id(sources: Sequence[SourceFile]) -> dict[str, Unit]:
    return {unit.unit_id: unit for source in sources for unit in source.units}


def _preamble_value(preamble: Sequence[str], prefix: str) -> str:
    return next((line[len(prefix):].strip() for line in preamble if line.startswith(prefix)), "")


# --- the plan -----------------------------------------------------------------------------------------


@dataclass
class Theme:
    file: str
    slug: str
    title: str
    scope: str
    sections: list[list[str]]
    review: list[str] = field(default_factory=list)

    def unit_ids(self) -> list[str]:
        return [unit_id for section in self.sections for unit_id in section]

    def to_json(self) -> dict[str, object]:
        return {"file": self.file, "slug": self.slug, "title": self.title, "scope": self.scope,
                "sections": self.sections, "review": self.review}


def slugify(title: str) -> str:
    slug = _NOT_SLUG.sub("-", title.lower()).strip("-")
    return slug[:SLUG_MAX_CHARS].rstrip("-") or "finding"


def _theme_of(source: SourceFile) -> Theme:
    match = _CONSOLIDATED_NAME.match(source.name)
    slug = match.group(2) if match else slugify(source.title)
    return Theme(source.name, slug, source.title, _preamble_value(source.preamble, PREAMBLE_SCOPE),
                 [[unit.unit_id] for unit in source.units])


def _new_theme(title: str) -> Theme:
    return Theme("", slugify(title), title, "", [], ["new theme: name it, and write its Scope if it has more "
                                                      "than one section"])


PLACE_SYSTEM = (
    "You sort new findings from Datrix, a multi-language code generator, into existing themes. A theme is a "
    "group of findings one person would fix and review together: the same seam, construct or contract; the "
    "same defect seen from another target, layer or test; one finding testing or documenting another; the "
    "same generator, template family or script. Different severity, kind or target does not separate them. "
    "For each new finding answer: theme (the id of the existing theme it belongs to, e.g. 'C009', or 'NEW' "
    "when no theme fits); duplicate_of (the id of a section in that theme describing the SAME defect, e.g. "
    "'C009.3', else ''); new_theme (when theme is 'NEW': a short name for the theme it starts, naming the "
    "seam or subsystem, not the single defect; else ''). Prefer an existing theme when unsure.")

PLACE_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {"placements": {"type": "array", "items": {
        "type": "object",
        "properties": {"unit": {"type": "string"}, "theme": {"type": "string"},
                       "duplicate_of": {"type": "string"}, "new_theme": {"type": "string"}},
        "required": ["unit", "theme", "duplicate_of", "new_theme"]}}},
    "required": ["placements"],
}

FOLD_SYSTEM = (
    "You review the themes of a findings inbox from Datrix, a multi-language code generator. A theme is a "
    "group of findings one person would fix and review together. Name every set of themes that are really "
    "ONE theme (the same seam, construct, contract, subsystem or script) as one fold: into (the id that "
    "keeps them) and from (the ids folded into it). Themes that merely share a package are not one theme. "
    "Answer an empty list when no themes should fold.")

FOLD_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {"folds": {"type": "array", "items": {
        "type": "object",
        "properties": {"into": {"type": "string"}, "from": {"type": "array", "items": {"type": "string"}}},
        "required": ["into", "from"]}}},
    "required": ["folds"],
}


@dataclass
class _PlanState:
    themes: dict[str, Theme]
    units: dict[str, Unit]
    new_names: dict[str, str] = field(default_factory=dict)

    def theme_key_of_unit(self, unit_id: str) -> str:
        return next((key for key, theme in self.themes.items() if unit_id in theme.unit_ids()), "")


def _catalogue(state: _PlanState) -> str:
    lines: list[str] = []
    for key, theme in state.themes.items():
        lines.append(f"{key}: {theme.title}")
        lines.extend(f"  {section[0]}: {state.units[section[0]].title}" for section in theme.sections)
    return "\n".join(lines)


def _unit_excerpt(unit: Unit) -> str:
    return "\n".join([f"--- new finding {unit.unit_id} ---", f"# {unit.title}", *unit.body[:UNIT_EXCERPT_LINES]])


def _place(state: _PlanState, unit: Unit, answer: dict[str, object]) -> None:
    """Put one raw unit where the model said, checking every id it gave."""
    theme_key = str(answer.get("theme", "")).strip()
    duplicate = str(answer.get("duplicate_of", "")).strip()
    if theme_key == NEW_THEME:
        name = str(answer.get("new_theme", "")).strip() or unit.title
        key = state.new_names.setdefault(name.lower(), f"N{len(state.new_names) + 1}")
        state.themes.setdefault(key, _new_theme(name)).sections.append([unit.unit_id])
        return
    theme = state.themes.get(theme_key)
    if theme is None:
        _unplaced(state, unit, f"the model named theme '{theme_key}', which does not exist")
        return
    target = next((section for section in theme.sections if duplicate and section[0] == duplicate), None)
    if target is not None:
        target.append(unit.unit_id)
        theme.review.append(f"{unit.unit_id} merged into section {duplicate} as the same defect: confirm")
        return
    theme.sections.append([unit.unit_id])
    theme.review.append(f"{unit.unit_id} added by the model: confirm it belongs")


def _unplaced(state: _PlanState, unit: Unit, reason: str) -> None:
    key = f"N{len(state.new_names) + 1}"
    state.new_names[f"unplaced:{unit.unit_id}"] = key
    theme = _new_theme(unit.title)
    theme.sections.append([unit.unit_id])
    theme.review.append(f"{unit.unit_id} not placed: {reason}")
    state.themes[key] = theme


def _place_batch(pool: LocalLlmPool, content: ContentFilter, catalogue: str,
                 batch: Sequence[Unit]) -> list[tuple[Unit, dict[str, object]]]:
    text = catalogue + "\n\n" + "\n\n".join(_unit_excerpt(unit) for unit in batch)
    section = content.section("themes and new findings", text)
    answer = ask_json(pool, PLACE_SYSTEM, section_body(section), PLACE_SCHEMA)
    by_unit = {str(item.get("unit", "")).strip(): item for item in object_list(answer.get("placements"))}
    return [(unit, by_unit.get(unit.unit_id, {})) for unit in batch]


def _apply_folds(state: _PlanState, answer: dict[str, object]) -> None:
    for fold in object_list(answer.get("folds")):
        raw_from = fold.get("from")
        keys = [str(fold.get("into", "")).strip(), *(str(k).strip() for k in raw_from)] \
            if isinstance(raw_from, list) else []
        present = list(dict.fromkeys(key for key in keys if key in state.themes))
        if len(present) < 2:
            continue
        home = min(present, key=lambda key: (not state.themes[key].file, key))
        for key in present:
            if key == home:
                continue
            folded = state.themes.pop(key)
            state.themes[home].sections.extend(folded.sections)
            state.themes[home].review.append(f"folded in {folded.file or folded.title} (model): confirm")


def draft_plan(directory: Path, workspace: Path, pool: LocalLlmPool | None) -> list[Theme]:
    """The themes a local model proposes; without ``pool``, every raw unit is its own new theme."""
    sources = load_sources(directory)
    state = _PlanState({f"C{s.number}": _theme_of(s) for s in sources if s.consolidated}, _units_by_id(sources))
    raw_units = [unit for source in sources if not source.consolidated for unit in source.units]
    if pool is None:
        for unit in raw_units:
            _unplaced(state, unit, "no model was asked (--no-model)")
        return list(state.themes.values())
    content = ContentFilter(workspace)
    catalogue = _catalogue(state)
    batches = [raw_units[i:i + PLACEMENT_BATCH] for i in range(0, len(raw_units), PLACEMENT_BATCH)]
    for placements in parallel(batches, lambda batch: _place_batch(pool, content, catalogue, batch)):
        for unit, answer in placements:
            if answer:
                _place(state, unit, answer)
            else:
                _unplaced(state, unit, "the model gave no placement for it")
    fold_section = content.section("themes", _catalogue(state))
    _apply_folds(state, ask_json(pool, FOLD_SYSTEM, section_body(fold_section), FOLD_SCHEMA))
    return list(state.themes.values())


def plan_json(themes: Sequence[Theme]) -> str:
    return json.dumps({"themes": [theme.to_json() for theme in themes]}, indent=2, ensure_ascii=False) + "\n"


def _changed(theme: Theme) -> bool:
    """A theme the plan alters: new, or holding a unit that is not its own file's section in place."""
    own = [unit_id for unit_id in theme.unit_ids() if unit_id.startswith("C")]
    prefix = f"C{theme.file[len(CONSOLIDATED_PREFIX):len(CONSOLIDATED_PREFIX) + 3]}." if theme.file else ""
    return not theme.file or len(own) != len(theme.unit_ids()) or any(not u.startswith(prefix) for u in own) \
        or bool(theme.review)


def _theme_lines(theme: Theme, units: dict[str, Unit]) -> list[str]:
    """A changed theme: its new, merged and moved sections in full; its untouched sections as a count."""
    lines = [f"## {theme.file or 'NEW'} — {theme.title}", ""]
    if theme.scope and not theme.file:
        lines += [f"Scope: {theme.scope}", ""]
    prefix = f"C{theme.file[len(CONSOLIDATED_PREFIX):len(CONSOLIDATED_PREFIX) + 3]}." if theme.file else "\0"
    untouched = 0
    for index, section in enumerate(theme.sections, start=1):
        if len(section) == 1 and section[0].startswith(prefix):
            untouched += 1
            continue
        lines.append(f"{index}. `{section[0]}` {units[section[0]].title}")
        lines += [f"    + `{unit_id}` {units[unit_id].title}" for unit_id in section[1:]]
    if untouched:
        lines.append(f"(+ {untouched} section(s) of its own, unchanged)")
    flags = list(theme.review)
    if len(theme.sections) > MAX_SECTIONS_PER_THEME:
        flags.append(f"{len(theme.sections)} sections: split along its most natural seam")
    return lines + ["", *(f"- REVIEW: {flag}" for flag in flags), ""] if flags else lines + [""]


def render_plan(themes: Sequence[Theme], units: dict[str, Unit], plan_path: Path) -> str:
    """The view the skill reviews: only the themes the plan changes, with unit ids and review flags."""
    raw = sum(1 for unit in units.values() if not unit.unit_id.startswith("C"))
    changed = [theme for theme in themes if _changed(theme)]
    lines = ["# Findings plan", "",
             f"{len(units)} unit(s) ({raw} raw) into {len(themes)} theme file(s); {len(changed)} theme(s) change. "
             f"Edit `{plan_path}` (move unit ids between sections and themes, rename, write Scope lines), then "
             "run `findings-assemble`. Open a unit's source only where the grouping is in doubt.", ""]
    for theme in changed:
        lines += _theme_lines(theme, units)
    unchanged = [theme.file for theme in themes if not _changed(theme)]
    if unchanged:
        lines += ["## Unchanged", "", *(f"- {name}" for name in unchanged), ""]
    return "\n".join(lines)


# --- assembly -----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class AssembledFile:
    name: str
    text: str
    sections: int


@dataclass
class Assembly:
    files: list[AssembledFile]
    delete: list[str]
    units_in: int
    lost_lines: dict[str, list[str]] = field(default_factory=dict)
    term_files: list[str] = field(default_factory=list)

    @property
    def safe(self) -> bool:
        return not (self.lost_lines or self.term_files)


def load_plan(path: Path) -> list[Theme]:
    try:
        data = json.loads(read_text(path))
    except json.JSONDecodeError as exc:
        raise AssistError(f"Plan {path} is not valid JSON ({exc}). Fix the file, or run findings-plan again.") from exc
    themes: list[Theme] = []
    for item in object_list(data.get("themes") if isinstance(data, dict) else None):
        sections = item.get("sections")
        if not isinstance(sections, list) or not all(isinstance(s, list) and s for s in sections):
            raise AssistError(f"Plan theme '{item.get('title')}' has no sections, or a section that is not a "
                              "non-empty list of unit ids. Give every section as [\"<unit id>\", ...].")
        themes.append(Theme(str(item.get("file", "")), str(item.get("slug", "")), str(item.get("title", "")),
                            str(item.get("scope", "")), [[str(u) for u in s] for s in sections]))
    return themes


def validate_plan(themes: Sequence[Theme], sources: Sequence[SourceFile]) -> None:
    """Refuse a plan that drops, repeats or invents a unit, or names a theme file wrongly."""
    known = _units_by_id(sources)
    placed = [unit_id for theme in themes for unit_id in theme.unit_ids()]
    problems = [f"unit '{u}' is not in the findings folder" for u in dict.fromkeys(placed) if u not in known]
    problems += [f"unit '{u}' is placed {placed.count(u)} times" for u in dict.fromkeys(placed) if placed.count(u) > 1]
    problems += [f"unit '{u}' ({known[u].source}) is placed nowhere" for u in known if u not in placed]
    names = {source.name for source in sources if source.consolidated}
    homes = [theme.file for theme in themes if theme.file]
    problems += [f"theme file '{f}' is not a consolidated file in the folder" for f in homes if f not in names]
    problems += [f"theme file '{f}' is home to {homes.count(f)} themes" for f in dict.fromkeys(homes) if homes.count(f) > 1]
    problems += [f"theme '{t.title}' has slug '{t.slug}' (lowercase words joined by '-')" for t in themes
                 if not _SLUG.match(t.slug)]
    problems += [f"a theme with slug '{t.slug}' has no title" for t in themes if not t.title.strip()]
    if problems:
        raise AssistError("The plan cannot be assembled:\n  - " + "\n  - ".join(problems)
                          + "\nEdit the plan JSON so every unit id appears exactly once, then run again.")


def _destinations(themes: Sequence[Theme], sources: Sequence[SourceFile]) -> list[str]:
    """Each theme's file name: a kept file keeps its number, a new theme takes the next free one."""
    numbers = [int(source.number) for source in sources if source.consolidated]
    next_number = max(numbers, default=0) + 1
    names: list[str] = []
    for theme in themes:
        match = _CONSOLIDATED_NAME.match(theme.file)
        if match:
            number = match.group(1)
        else:
            number = f"{next_number:03d}"
            next_number += 1
        names.append(f"{CONSOLIDATED_PREFIX}{number}-{theme.slug}.md")
    return names


def _reference_map(themes: Sequence[Theme], destinations: Sequence[str],
                   sources: Sequence[SourceFile]) -> dict[str, str]:
    """Old consolidated number -> the stem of the file that now holds it (its first unit's theme)."""
    theme_of_unit = {u: destinations[i] for i, theme in enumerate(themes) for u in theme.unit_ids()}
    kept = {theme.file: destinations[i] for i, theme in enumerate(themes) if theme.file}
    mapping: dict[str, str] = {}
    for source in sources:
        if source.consolidated:
            target = kept.get(source.name) or theme_of_unit[source.units[0].unit_id]
            mapping[source.number] = Path(target).stem
    return mapping


def repoint(text: str, mapping: dict[str, str]) -> str:
    """Every ``consolidated-NNN[-slug][.md]`` reference renamed to the file that now holds NNN."""

    def rename(match: re.Match[str]) -> str:
        stem = mapping.get(match.group(1))
        if stem is None:
            return match.group(0)
        if match.group(2) is None:
            return stem[:len(CONSOLIDATED_PREFIX) + 3]
        return stem + (match.group(3) or "")

    return _REFERENCE.sub(rename, text)


def _section_lines(index: int, section: Sequence[str], units: dict[str, Unit]) -> list[str]:
    first = units[section[0]]
    lines = [f"## {index}. {first.title}", "", *first.body]
    for unit_id in section[1:]:
        other = units[unit_id]
        lines += ["", f"{ALSO_REPORTED} {other.title}", "", *other.body]
    return lines + [""]


def _repos_cited(units: Sequence[Unit]) -> list[str]:
    text = "\n".join(line for unit in units for line in unit.body)
    return sorted(set(_REPO.findall(text)))


def _join_values(*values: str) -> str:
    return "; ".join(dict.fromkeys(value for value in values if value))


def _preamble(theme: Theme, home: SourceFile | None, folded: Sequence[SourceFile], units: Sequence[Unit]) -> list[str]:
    """A kept file's own preamble, with the plan's Scope and the folded files' Where and Related lines."""
    base = list(home.preamble) if home else []
    extra = [line for source in folded for line in source.preamble if not line.startswith(_MERGED_PREAMBLE)]
    where = _join_values(_preamble_value(base, PREAMBLE_WHERE),
                         *(_preamble_value(s.preamble, PREAMBLE_WHERE) for s in folded))
    if not where:
        where = ", ".join(f"`{repo}`" for repo in _repos_cited(units))
    related = _join_values(_preamble_value(base, PREAMBLE_RELATED),
                           *(_preamble_value(s.preamble, PREAMBLE_RELATED) for s in folded))
    body = [line for line in base if not line.startswith(_MERGED_PREAMBLE)] + extra
    lines = [f"{PREAMBLE_SCOPE} {theme.scope}"] if theme.scope else []
    lines += [f"{PREAMBLE_WHERE} {where}"] if where else []
    lines += [f"{PREAMBLE_RELATED} {related}"] if related else []
    return lines + ([""] + body if body else [])


def _drop_self_related(text: str, stem: str) -> str:
    """A Related line never names its own file (a fold can make it do so)."""
    own = stem[:len(CONSOLIDATED_PREFIX) + 3]
    lines = []
    for line in text.splitlines():
        if line.startswith(PREAMBLE_RELATED):
            parts = [part for part in line[len(PREAMBLE_RELATED):].split(";") if own not in part]
            line = f"{PREAMBLE_RELATED}{';'.join(parts)}" if parts else ""
            if not line:
                continue
        lines.append(line)
    return "\n".join(lines)


def _normalized_line(line: str) -> str:
    return _SECTION_NUMBER.sub("", line.strip().lstrip("#").strip())


def _carried_lines(source: SourceFile, mapping: dict[str, str]) -> list[str]:
    """The source lines that must survive: every non-blank unit line and every unit title."""
    lines = [unit.title for unit in source.units]
    lines += [line for unit in source.units for line in unit.body]
    lines += [line for line in source.preamble if not line.startswith(_MERGED_PREAMBLE)]
    return [normal for line in lines if (normal := _normalized_line(repoint(line, mapping)))]


def assemble(themes: Sequence[Theme], sources: Sequence[SourceFile], content: ContentFilter) -> Assembly:
    """Every theme file's text, the sources it supersedes, and whether anything would be lost."""
    validate_plan(themes, sources)
    units = _units_by_id(sources)
    by_name = {source.name: source for source in sources}
    destinations = _destinations(themes, sources)
    mapping = _reference_map(themes, destinations, sources)
    files: list[AssembledFile] = []
    for theme, name in zip(themes, destinations):
        home = by_name.get(theme.file)
        theme_units = [units[u] for u in theme.unit_ids()]
        folded = [by_name[n] for n, number in ((s.name, s.number) for s in sources if s.consolidated)
                  if n != theme.file and Path(name).stem == mapping[number]]
        lines = [f"# {theme.title}", "", *_preamble(theme, home, folded, theme_units), ""]
        for index, section in enumerate(theme.sections, start=1):
            lines += _section_lines(index, section, units)
        text = _drop_self_related(repoint("\n".join(lines), mapping), Path(name).stem).rstrip() + "\n"
        files.append(AssembledFile(name, text, len(theme.sections)))
    written = {f.name for f in files}
    result = Assembly(files, sorted(s.name for s in sources if s.name not in written), len(units))
    output_lines = {_normalized_line(line) for f in files for line in f.text.splitlines()}
    output_lines |= {_normalized_line(repoint(units[u].title, mapping)) for t in themes for u in t.unit_ids()}
    for source in sources:
        lost = [line for line in _carried_lines(source, mapping) if line not in output_lines]
        if lost:
            result.lost_lines[source.name] = lost
    result.term_files = [f.name for f in files if content.carries_term(f.text)]
    return result


def write_assembly(directory: Path, assembly: Assembly) -> None:
    """Every theme file into ``directory``, UTF-8 with LF line ends as the agents write them."""
    for assembled in assembly.files:
        (directory / assembled.name).write_text(assembled.text, encoding="utf-8", newline="\n")


def apply_assembly(directory: Path, assembly: Assembly) -> ConsolidationCheck:
    """Write the theme files, run the no-loss check, and delete the superseded sources only when it passes."""
    write_assembly(directory, assembly)
    doomed = [directory / name for name in assembly.delete]
    result = check_consolidation(directory, doomed)
    if result.passed:
        for path in doomed:
            path.unlink()
    return result


def render_assembly(assembly: Assembly, target: Path) -> str:
    raw = sum(1 for name in assembly.delete if not name.startswith(CONSOLIDATED_PREFIX))
    lines = [f"{assembly.units_in} unit(s) in, {len(assembly.files)} theme file(s) out "
             f"({sum(f.sections for f in assembly.files)} sections); {len(assembly.delete)} source(s) superseded "
             f"({raw} raw). Files in {target}:"]
    lines += [f"  {f.name}  ({f.sections} section(s))" for f in assembly.files]
    for name, lost in assembly.lost_lines.items():
        lines.append(f"LOST from {name}: " + " | ".join(lost[:5]) + (" ..." if len(lost) > 5 else ""))
    lines += [f"CUSTOMER TERM in {name}: redact the source unit it came from, then run again"
              for name in assembly.term_files]
    return "\n".join(lines) + "\n"
