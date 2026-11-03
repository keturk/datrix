"""What drafting the corpus library sends a local model, and what it accepts back.

A drafting *unit* is one family file ``services/<family>.dtrx`` with the owner configs its services name,
holding the union of its family's needs over every entry that reads it; or one entry's system: the
``system`` declaration of ``<entry>.dtrx`` and the config it names. The model answers one unit at a time:
the unit's source, the configs it writes, and the renames it made where two needs collide. An answer is
read before anything of it is written:

- a string literal that looks like a raw secret refuses the unit at once: it is queued and nothing of it
  is written;
- a family source parses alone and declares services, no system and no include; a system source declares
  one system naming the unit's system config, no service and no include;
- a config lies under ``config/`` (never among the templates), parses, and is the unit's own: one its
  services already name or a new one no other unit writes (a system unit writes its system config only);
  a service's config imports the datasource templates;
- a rename moves facts of one of the unit's needs (none listed: the whole need) to a path no need and no
  other rename holds. ``renames.json`` records every rename, so a test reading the old path is repointed to
  the new one.
"""

from __future__ import annotations

import json
import tempfile
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final

from datrix_common.config.dcfg.errors import DcfgSyntaxError
from datrix_common.datrix_model.containers import Application
from datrix_language.parser.dcfg_parser import parse_dcfg
from datrix_testing.cases.annotations import DIAGNOSTIC_CONFIGS
from datrix_testing.corpus import ENTRY_SUFFIX
from datrix_testing.parsing import PARSER_REFUSALS, parse_as_written

from datrix_scripts.dev.fixture_author.diagnostics import DATASOURCE_TEMPLATES
from datrix_scripts.dev.fixture_author.drafting import Problem, parse_draft
from datrix_scripts.dev.fixture_author.library_check import CONFIG_SUFFIX
from datrix_scripts.dev.fixture_author.library_plan import LibraryPlan, union_declarations
from datrix_scripts.dev.fixture_author.needs_reading import Declaration
from datrix_scripts.dev.fixture_author.prompting import (
    FEEDBACK_HEADING,
    PREVIOUS_DRAFT_HEADING,
    WITHHELD,
    DraftFiles,
    reference_excerpt,
)
from datrix_scripts.skill.common import object_list

#: The directory of the family files, under the corpus root.
SERVICES_DIR: Final = "services"
#: The datasource templates every service config imports, relative to the corpus root.
TEMPLATES: Final = DATASOURCE_TEMPLATES.as_posix()
#: The name of an entry's system unit: this prefix and the entry.
SYSTEM_UNIT_PREFIX: Final = "system-"
#: The config kind of a service's owner config, which builds its blocks from the templates.
SERVICE_CONFIG_KIND: Final = "service"
#: The heading the unprovided needs and errors are sent under before the unit's first draft.
LACKING_HEADING: Final = "WHAT THE CORPUS LACKS NOW"
#: The answer every unit request is constrained to.
LIBRARY_SCHEMA: Final[dict[str, object]] = {
    "type": "object",
    "properties": {
        "source": {"type": "string"},
        "configs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"path": {"type": "string"}, "text": {"type": "string"}},
                "required": ["path", "text"],
            },
        },
        "renames": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string"},
                    "path": {"type": "string"},
                    "to": {"type": "string"},
                    "facts": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["kind", "path", "to", "facts"],
            },
        },
    },
    "required": ["source", "configs", "renames"],
}

_TEMPLATES_DIR: Final = PurePosixPath(TEMPLATES).parent
_PARENT: Final = ".."
_RENAMES_KEY: Final = "renames"
_RENAME_FIELDS: Final = ("kind", "path", "to")
_FACTS_KEY: Final = "facts"


class LibraryDraftError(Exception):
    """``renames.json`` cannot be read, or a corpus entry has a form the library cannot draft."""


@dataclass(frozen=True)
class DraftUnit:
    """One file the model drafts, with the configs it reads, and the needs it must provide.

    Attributes:
        name: The family, or ``system-<entry>`` for an entry's system.
        source: The file drafted, relative to the corpus root: ``services/<family>.dtrx`` or ``<entry>.dtrx``.
        entries: The entries reading it.
        needs: The union of its declarations over those entries.
        system_config: For an entry's system, the config its declaration names; ``None`` for a family.
    """

    name: str
    source: str
    entries: tuple[str, ...]
    needs: tuple[Declaration, ...]
    system_config: str | None = None

    @property
    def is_system(self) -> bool:
        """Whether the unit is an entry's system rather than a family."""
        return self.system_config is not None


@dataclass(frozen=True, order=True)
class Rename:
    """Facts of the need *kind* at *path* (none listed: the whole need) moved to the path *to*."""

    kind: str
    path: str
    to: str
    facts: tuple[str, ...]

    def as_json(self) -> dict[str, object]:
        """The rename as ``renames.json`` holds it."""
        return {"kind": self.kind, "path": self.path, "to": self.to, _FACTS_KEY: list(self.facts)}


@dataclass(frozen=True)
class UnitDraft:
    """One unit's answer: its source and configs, and the renames it made."""

    files: DraftFiles
    renames: tuple[Rename, ...]


@dataclass(frozen=True)
class Claims:
    """What a unit's draft may not take: the configs another unit owns, the paths a need holds and the
    renames already recorded (one made again is no collision; another taking their paths is)."""

    configs: Mapping[str, str]
    paths: frozenset[str]
    renames: frozenset[Rename]


def system_unit_name(entry: str) -> str:
    """The name of the unit drafting *entry*'s system."""
    return f"{SYSTEM_UNIT_PREFIX}{entry}"


def family_source(family: str) -> str:
    """The family file of *family*, relative to the corpus root."""
    return f"{SERVICES_DIR}/{family}{ENTRY_SUFFIX}"


def new_system_config(entry: str) -> str:
    """The system config a new entry's system names, relative to the corpus root."""
    return f"{DIAGNOSTIC_CONFIGS}/{entry}-system{CONFIG_SUFFIX}"


def plan_units(plan: LibraryPlan, system_configs: Mapping[str, str]) -> dict[str, DraftUnit]:
    """One unit per family of *plan*, its needs unioned over every entry holding it, and one per entry's
    system, naming the config of *system_configs* (by entry)."""
    by_family: dict[str, list[Declaration]] = defaultdict(list)
    readers: dict[str, set[str]] = defaultdict(set)
    for entry in plan.entries:
        for family, needs in entry.families.items():
            by_family[family].extend(needs)
            readers[family].add(entry.entry)
    units = {
        family: DraftUnit(family, family_source(family), tuple(sorted(readers[family])), union_declarations(needs))
        for family, needs in sorted(by_family.items())
    }
    for entry in plan.entries:
        name = system_unit_name(entry.entry)
        units[name] = DraftUnit(name, f"{entry.entry}{ENTRY_SUFFIX}", (entry.entry,), entry.system,
                                system_configs[entry.entry])
    return units


def _renamed(need: Declaration, renames: Sequence[Rename]) -> list[Declaration]:
    moved = [rename for rename in renames if (rename.kind, rename.path) == (need.kind, need.path)]
    whole = any(not rename.facts for rename in moved)
    taken = {fact for rename in moved for fact in rename.facts}
    kept = [] if whole else [Declaration(need.kind, need.path, tuple(f for f in need.facts if f not in taken))]
    return kept + [Declaration(need.kind, rename.to, rename.facts or need.facts) for rename in moved]


def apply_renames(needs: Iterable[Declaration], renames: Sequence[Rename]) -> tuple[Declaration, ...]:
    """*needs* with every rename applied: a moved fact is needed at its new path, the rest at the old one."""
    return union_declarations(renamed for need in needs for renamed in _renamed(need, renames))


def read_renames(path: Path) -> tuple[Rename, ...]:
    """The renames ``renames.json`` at *path* records; none when it does not exist.

    Raises:
        LibraryDraftError: the file is no ``{"renames": [{kind, path, to, facts}]}`` document.
    """
    if not path.is_file():
        return ()
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise LibraryDraftError(f"{path} is not JSON: {error}. Fix: restore it or delete it.") from error
    rows = document.get(_RENAMES_KEY) if isinstance(document, dict) else None
    renames = [_rename(row) for row in object_list(rows)]
    if not isinstance(rows, list) or len(renames) != len(rows) or not all(renames):
        raise LibraryDraftError(
            f"{path} is not {{\"renames\": [{{\"kind\", \"path\", \"to\", \"facts\": [...]}}]}}. Fix: restore it."
        )
    return tuple(sorted(rename for rename in renames if rename is not None))


def write_renames(path: Path, renames: Iterable[Rename]) -> None:
    """Write *renames*, sorted and each once, to ``renames.json`` at *path*."""
    rows = [rename.as_json() for rename in sorted(set(renames))]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({_RENAMES_KEY: rows}, indent=2) + "\n", encoding="utf-8")


def _rename(row: Mapping[str, object]) -> Rename | None:
    fields = [row.get(name) for name in _RENAME_FIELDS]
    facts = row.get(_FACTS_KEY)
    if not all(isinstance(value, str) and value for value in fields) or not isinstance(facts, list):
        return None
    if not all(isinstance(fact, str) for fact in facts):
        return None
    kind, path, to = (str(value) for value in fields)
    return Rename(kind, path, to, tuple(str(fact) for fact in facts))


def parse_unit_answer(answer: Mapping[str, object]) -> UnitDraft | str:
    """The draft a model's JSON *answer* states, or why it states none."""
    files = parse_draft(answer)
    if isinstance(files, Problem):
        return files.text
    rows = answer.get(_RENAMES_KEY)
    renames = [_rename(row) for row in object_list(rows)]
    if not isinstance(rows, list) or len(renames) != len(rows) or not all(renames):
        return 'each entry of renames is {"kind": <text>, "path": <text>, "to": <text>, "facts": [<text>]}.'
    return UnitDraft(files, tuple(rename for rename in renames if rename is not None))


def _parsed_source(unit: DraftUnit, text: str) -> Application | str:
    with tempfile.TemporaryDirectory(prefix="fixture-author-library-") as temporary:
        probe = Path(temporary) / unit.source
        probe.parent.mkdir(parents=True, exist_ok=True)
        probe.write_text(text, encoding="utf-8")
        try:
            return parse_as_written(probe, require_system=unit.is_system, text=text)
        except PARSER_REFUSALS as error:
            return f"{unit.source} does not parse: {str(error).replace(str(probe), unit.source)}"


def source_problems(unit: DraftUnit, text: str) -> list[str]:
    """Why *text* cannot be *unit*'s source, read off its parse alone."""
    named = "".join(text.split())
    if named.endswith(ENTRY_SUFFIX) and "\n" not in text.strip():
        return [f"the source is the file name {text.strip()!r}; it must be the whole .dtrx text of {unit.source}."]
    application = _parsed_source(unit, text)
    if isinstance(application, str):
        return [application]
    problems = [f"{unit.source} includes {d.path!r}: the tool writes the includes." for d in application.include_directives]
    if not unit.is_system:
        if application.system is not None:
            problems.append(f"{unit.source} declares a system: a family file holds services only.")
        if not application.services:
            problems.append(f"{unit.source} declares no service.")
        return problems
    if application.services:
        problems.append(f"{unit.source}: the system draft declares services {sorted(application.services)}; "
                        "it holds the system declaration only.")
    system = application.system
    if system is None or system.config_path != unit.system_config:
        named = None if system is None else system.config_path
        problems.append(f"the system declaration names the config {named!r}; it must name {unit.system_config!r}.")
    return problems


def _config_path_problem(unit: DraftUnit, path: str, own: frozenset[str], claims: Claims, exists: Callable[[str], bool]) -> str | None:
    posix = PurePosixPath(path)
    if posix.is_absolute() or _PARENT in posix.parts or posix.parts[:1] != (DIAGNOSTIC_CONFIGS,) or posix.suffix != CONFIG_SUFFIX:
        return f"{path!r} is not a config path: write {DIAGNOSTIC_CONFIGS}/<name>{CONFIG_SUFFIX}."
    if posix.is_relative_to(_TEMPLATES_DIR):
        return f"{path} is a template library; the unit never writes it."
    if unit.is_system:
        return None if path == unit.system_config else f"{path}: the system draft writes {unit.system_config} only."
    owner = claims.configs.get(path, unit.name)
    if owner != unit.name:
        return f"{path} belongs to {owner}; choose another name."
    if path not in own and exists(path):
        return f"{path} already exists in the corpus and none of this file's services names it; choose another name."
    return None


def _config_text_problems(path: str, text: str) -> list[str]:
    try:
        declaration = parse_dcfg(text, path)
    except DcfgSyntaxError as error:
        return [f"{path} does not parse: {error}"]
    imported = {each.path for each in declaration.imports}
    if declaration.kind == SERVICE_CONFIG_KIND and TEMPLATES not in imported:
        return [f'{path} does not import "{TEMPLATES}": a service config builds its blocks from the templates.']
    return []


def config_problems(unit: DraftUnit, draft: DraftFiles, own: frozenset[str], claims: Claims, exists: Callable[[str], bool]) -> list[str]:
    """Why a config of *draft* cannot be written: its path, its ownership (*own*: the configs *unit*'s
    services already name; *claims*: another unit's) or its text."""
    problems: list[str] = []
    seen: set[str] = set()
    for path, text in draft.files:
        problem = _config_path_problem(unit, path, own, claims, exists)
        if path in seen:
            problem = f"{path} is written twice."
        seen.add(path)
        problems.extend([problem] if problem else _config_text_problems(path, text))
    if unit.is_system and unit.system_config not in seen and not exists(str(unit.system_config)):
        problems.append(f"the system config {unit.system_config} is not written.")
    return problems


def rename_problems(unit: DraftUnit, renames: Sequence[Rename], claims: Claims) -> list[str]:
    """Why a rename of *unit*'s draft cannot be recorded."""
    needs = {(need.kind, need.path): need for need in unit.needs}
    problems: list[str] = []
    targets = {recorded.to for recorded in claims.renames}
    for rename in renames:
        if rename in claims.renames:
            continue
        need = needs.get((rename.kind, rename.path))
        if need is None:
            problems.append(f"the rename of {rename.kind} {rename.path!r} names no need of this unit.")
        elif not set(rename.facts) <= set(need.facts):
            problems.append(f"the rename of {rename.path!r} moves {sorted(set(rename.facts) - set(need.facts))}, "
                            f"facts the need does not hold.")
        if rename.to in claims.paths or rename.to in targets:
            problems.append(f"the rename to {rename.to!r} takes a path a need or another rename already holds.")
        targets.add(rename.to)
    return problems


def need_line(need: Declaration) -> str:
    """*need* as one line of a prompt or a queue file."""
    facts = f"; facts: {'; '.join(need.facts)}" if need.facts else ""
    return f"- {need.kind} {need.path}{facts}"


def library_system_prompt(templates: str, example: str) -> str:
    """The rules every unit request shares, the datasource *templates* and an *example* service file with its
    config."""
    sections = [
        "You write part of the shared fixture corpus that a code generator's test suites read: Datrix .dtrx "
        "sources and .dcfg configs. Answer one JSON object: {\"source\": <the whole .dtrx text of the unit's "
        "file, never its path>, \"configs\": "
        "[{\"path\": <relative to the corpus root>, \"text\": <the .dcfg>}], \"renames\": [{\"kind\", \"path\", "
        "\"to\", \"facts\": [...]}]}.",
        "RULES:\n"
        "- Declare every need with its kind at a path ending with the need's path, holding each listed fact "
        "(<key> <value>: the key names what is read, the rest the value it holds).\n"
        "- Keep every declaration already in the file; extend it. Keep every needed name. Only when two needs "
        "cannot both hold (one path, facts that conflict), declare one at a new path and list it in renames "
        "with the facts it moved; otherwise renames is [].\n"
        f"- A family file holds services only: no system, no include (the tool writes the includes). Each "
        f"service names its own owner config, {DIAGNOSTIC_CONFIGS}/<kebab-service-name>{CONFIG_SUFFIX}, which "
        f"imports \"{TEMPLATES}\", builds its blocks from those templates and declares profile test.\n"
        "- An entry's system draft is the system declaration alone, naming the config path you are given.\n"
        "- Security: httpSecurity lists explicit hosts and origins, never \"*\"; a container uses the "
        "templates (ssl = false is theirs); a secret is a handle declared in a secrets block, never a value. "
        "A draft holding a literal that looks like a secret is refused and never written.\n"
        "- Service names are unique across the corpus: never declare a service another file declares.",
        f"DATASOURCE TEMPLATES ({TEMPLATES}):\n{templates}",
    ]
    if example:
        sections.append(f"AN EXISTING SERVICE AND ITS CONFIG (the shape to follow):\n{example}")
    return "\n\n".join(sections)


def library_user_prompt(
    *,
    unit: DraftUnit,
    current: Mapping[str, str],
    elsewhere: Sequence[str],
    reference: str,
    problems: Sequence[str],
    previous: UnitDraft | None,
    withheld: Callable[[str], bool],
) -> str:
    """The request for *unit*: its needs, its *current* files, the services declared *elsewhere*, the syntax
    reference's matching sections and what failed; a part *withheld* flags is replaced by ``WITHHELD``."""

    def part(text: str) -> str:
        return WITHHELD if withheld(text) else text

    lines = [part(need_line(need)) for need in unit.needs] or ["- none: the problems below say what is lacking"]
    sections = [
        f"UNIT: {unit.name}; FILE: {unit.source}; READ BY THE ENTRIES: {', '.join(unit.entries)}",
        "NEEDS:\n" + "\n".join(lines),
    ]
    if unit.is_system:
        sections.append(f"THE SYSTEM CONFIG IT NAMES: {unit.system_config}")
    sections.extend(f"CURRENT {path}:\n{part(text)}" for path, text in current.items())
    if elsewhere:
        sections.append(f"SERVICES DECLARED ELSEWHERE: {', '.join(elsewhere)}")
    excerpt = reference_excerpt(reference, "\n".join(need_line(need) for need in unit.needs) or unit.name)
    if excerpt:
        sections.append(f"SYNTAX REFERENCE (excerpts):\n{part(excerpt)}")
    if problems:
        heading = FEEDBACK_HEADING if previous is not None else LACKING_HEADING
        sections.append(f"{heading}:\n" + "\n".join(part(f"- {problem}") for problem in problems))
    if previous is not None:
        sections.append(f"{PREVIOUS_DRAFT_HEADING}:\n{part(previous.files.rendered())}")
    return "\n\n".join(sections)


def unit_queue_text(unit: DraftUnit, problems: Sequence[str], draft: UnitDraft | None) -> str:
    """The queue file of *unit*: its needs, why it failed and its last draft, for a person to finish."""
    lines = [
        f"# Fixture-author queue: corpus library unit {unit.name}",
        "",
        f"{unit.source} and its configs do not provide the needs below in the entries {', '.join(unit.entries)}. "
        "Finish them by hand under the same rules -- each need declared once, every needed name kept or its "
        "rename recorded in renames.json, configs importing the templates, no secret literal -- then run "
        "`fixture-author.ps1 library` and delete this file.",
        "",
        "## Needs",
        "",
        *(need_line(need) for need in unit.needs),
        "",
        "## Why",
        "",
        *(f"- {problem}" for problem in problems or ("no draft was answered",)),
    ]
    if draft is not None:
        lines.extend(["", "## Last draft", "", "```text", draft.files.rendered(), "```"])
    return "\n".join(lines) + "\n"


__all__ = [
    "LACKING_HEADING",
    "LIBRARY_SCHEMA",
    "SERVICES_DIR",
    "SERVICE_CONFIG_KIND",
    "SYSTEM_UNIT_PREFIX",
    "TEMPLATES",
    "Claims",
    "DraftUnit",
    "LibraryDraftError",
    "Rename",
    "UnitDraft",
    "apply_renames",
    "config_problems",
    "family_source",
    "library_system_prompt",
    "library_user_prompt",
    "need_line",
    "new_system_config",
    "parse_unit_answer",
    "plan_units",
    "read_renames",
    "rename_problems",
    "source_problems",
    "system_unit_name",
    "unit_queue_text",
    "write_renames",
]
