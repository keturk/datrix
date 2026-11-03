"""``fixture-author.ps1 library``: draft the shared fixture corpus to hold what the tests need.

The plan (``library_plan``) places every shareable need of ``needs.json`` in an entry and a family. Each
family is one drafting unit, ``services/<family>.dtrx`` with its owner configs, holding the union of the
family's needs over every entry reading it; each entry's system is another, the ``system`` declaration of
``<entry>.dtrx`` with its config (``library_drafts``). The tool owns the entry files: an entry includes
every family file holding its needs, each include added before its system declaration (a drafted system is
written under the includes).

The run works on a staging copy of the corpus. It checks every entry first (``library_check``) and asks
the model only for the units that check finds lacking: a need unprovided, an error located in the unit's
files, an entry that does not run (its system unit), or a family every service of an entry holds (the
``core`` unit, the services holding no block, adds the control service). Each round asks every failing unit
at once, writes what passes the read-only checks, appends to each written config every profile its entries
run that it lacks, rewrites the entries and checks every entry again under every profile it runs:
needed − provided = ∅ and no error. A draft holding a secret-looking literal is queued at once and never
written. After at most :data:`MAX_ROUNDS` rounds a unit still failing is taken out (its files restored) and
written to ``queue/library-<unit>.md`` with its needs, why and its last draft; the rest are checked again
until every unit left passes. Only then are the landed units' files, the entries they belong to and the
renames they made (``renames.json``) written to the corpus. When no local model can serve, the run stops
and writes nothing.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Final

from datrix_common.config.dcfg.errors import DcfgSyntaxError
from datrix_testing.corpus import CORPUS_ROOT, ENTRY_SUFFIX, corpus_entry
from datrix_testing.parsing import PARSER_REFUSALS, parse_as_written, register_installed_parsers

from datrix_scripts.dev.fixture_author.diagnostics import FixtureAuthorError
from datrix_scripts.dev.fixture_author.drafting import MAX_ROUNDS, QUEUE_DIR, secret_sites, with_profiles
from datrix_scripts.dev.fixture_author.library_check import EntryCheck, check_entry, entry_profiles, library_choices
from datrix_scripts.dev.fixture_author.library_drafts import (
    LIBRARY_SCHEMA,
    SERVICES_DIR,
    TEMPLATES,
    Claims,
    DraftUnit,
    LibraryDraftError,
    Rename,
    UnitDraft,
    apply_renames,
    config_problems,
    family_source,
    library_system_prompt,
    library_user_prompt,
    need_line,
    new_system_config,
    parse_unit_answer,
    plan_units,
    read_renames,
    rename_problems,
    source_problems,
    system_unit_name,
    unit_queue_text,
    write_renames,
)
from datrix_scripts.dev.fixture_author.library_plan import (
    CORE_FAMILY,
    SYSTEM_KINDS,
    EntryPlan,
    LibraryPlan,
    LibraryPlanError,
    plan_library,
    platform_entries,
    read_needs_inventory,
)
from datrix_scripts.dev.fixture_author.needs_command import EXIT_INCOMPLETE, NEEDS_FILE, block_families
from datrix_scripts.dev.fixture_author.needs_reading import (
    ANSWER_TOKENS,
    MIN_CONTEXT_TOKENS,
    context_window,
    node_kinds,
)
from datrix_scripts.dev.fixture_author.prompting import SYNTAX_REFERENCE
from datrix_scripts.gate_harness import UsageError
from datrix_scripts.local_llm import LocalLlmPool, LocalLlmSettings, LocalLlmUnavailable
from datrix_scripts.local_llm_usage import CHARS_PER_TOKEN
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.skill.common import (
    EXIT_NO_MODEL,
    AssistError,
    ContentFilter,
    NoModelAnswer,
    ask_json,
    parallel,
)

logger = logging.getLogger(__name__)

#: Where the renames made to keep two colliding needs apart are recorded, for the tests' repointing.
RENAMES_FILE: Final[Path] = WORKSPACE_DIR / ".tmp" / "fixture-author" / "renames.json"
#: The queue file of a unit: this prefix, the unit name, ``.md``.
QUEUE_PREFIX: Final = "library-"
#: The comment opening an entry file the tool composes around a drafted system.
ENTRY_HEADER: Final = "// The {entry} scenario of the shared fixture corpus. A test selects the service it reads by name."
_QUEUE_SUFFIX: Final = ".md"
#: The widest window, in tokens, a request is sent with: a unit whose prompt, last draft and answer need more
#: is queued at once, since no request would hold it whole (a prompt is never cut).
MAX_REQUEST_TOKENS: Final = 65536


@dataclass(frozen=True)
class LibraryDrafter:
    """What drafting the corpus library reads: the model pool, the content filter, the corpus written and
    each block kind's family."""

    pool: LocalLlmPool
    content: ContentFilter
    root: Path
    families: Mapping[str, str]
    reference: str
    queue_dir: Path = QUEUE_DIR
    renames_file: Path = RENAMES_FILE
    max_rounds: int = MAX_ROUNDS


@dataclass(frozen=True)
class QueuedUnit:
    """A unit the run could not land, for a person to finish."""

    unit: DraftUnit
    problems: tuple[str, ...]
    draft: UnitDraft | None


@dataclass(frozen=True)
class LibraryOutcome:
    """What one run landed, found already provided and queued, and the files it wrote."""

    landed: tuple[str, ...]
    provided: tuple[str, ...]
    queued: tuple[QueuedUnit, ...]
    queue_files: tuple[Path, ...]
    written: tuple[Path, ...]


@dataclass(frozen=True)
class _EntryBase:
    """An entry as the corpus holds it before the run: its text (``None`` when new), its direct includes and
    the line of its system declaration."""

    text: str | None
    includes: tuple[str, ...]
    system_line: int
    system_config: str


@dataclass
class _Run:
    drafter: LibraryDrafter
    plan: LibraryPlan
    units: dict[str, DraftUnit]
    staging: Path
    bases: dict[str, _EntryBase]
    prior: tuple[Rename, ...]
    system: str
    drafts: dict[str, UnitDraft] = field(default_factory=dict)
    problems: dict[str, list[str]] = field(default_factory=dict)
    passing: set[str] = field(default_factory=set)
    queued: dict[str, QueuedUnit] = field(default_factory=dict)
    written: dict[str, set[str]] = field(default_factory=dict)
    originals: dict[str, bytes | None] = field(default_factory=dict)
    asked: set[str] = field(default_factory=set)
    # This round's answers sent back before anything of them was written, with why.
    sent_back: dict[str, list[str]] = field(default_factory=dict)
    # The families every entry reading them does not run: unchecked, so not passing, and not asked.
    waiting: set[str] = field(default_factory=set)
    # The one context window the run's requests are sent with (one window loads each model once).
    window: int = MIN_CONTEXT_TOKENS


# --------------------------------------------------------------------------- the corpus as it stands


def _entry_base(root: Path, entry: str) -> _EntryBase:
    """*entry* of the corpus at *root* before the run.

    Raises:
        LibraryDraftError: the entry is a scenario directory, or declares no system naming a config.
    """
    try:
        path = corpus_entry(root, entry)
    except FileNotFoundError:
        return _EntryBase(None, (), 0, new_system_config(entry))
    if path.parent.resolve() != root.resolve():
        raise LibraryDraftError(f"{path} is a scenario directory; the library drafts {entry}{ENTRY_SUFFIX} entries only.")
    application = parse_as_written(path)
    system = application.system
    if system is None or system.location is None or system.location.line is None or not system.config_path:
        raise LibraryDraftError(f"{path} declares no located system naming a config. Fix: declare one.")
    own = [
        directive.path for directive in application.include_directives
        if directive.location is not None and directive.location.file_path is not None
        and Path(directive.location.file_path).resolve() == path.resolve()
    ]
    return _EntryBase(path.read_text(encoding="utf-8"), tuple(own), system.location.line, system.config_path)


def _service_configs(path: Path) -> list[str]:
    """The owner configs the services of the family file at *path* name; none when it is absent or does not
    parse (the check reports that)."""
    if not path.is_file():
        return []
    try:
        application = parse_as_written(path, require_system=False)
    except PARSER_REFUSALS:
        return []
    return sorted({service.config_path for service in application.services.values() if service.config_path})


def _services_elsewhere(run: _Run, unit: DraftUnit) -> list[str]:
    names: set[str] = set()
    for path in sorted((run.staging / SERVICES_DIR).glob(f"*{ENTRY_SUFFIX}")):
        if path.relative_to(run.staging).as_posix() == unit.source:
            continue
        try:
            names.update(parse_as_written(path, require_system=False).services)
        except PARSER_REFUSALS:
            continue
    return sorted(names)


def _own_configs(run: _Run, unit: DraftUnit) -> list[str]:
    if unit.is_system:
        return [str(unit.system_config)]
    return _service_configs(run.staging / unit.source)


def _current_files(run: _Run, unit: DraftUnit) -> dict[str, str]:
    paths = [unit.source, *_own_configs(run, unit)]
    return {path: (run.staging / path).read_text(encoding="utf-8") for path in paths if (run.staging / path).is_file()}


def _example(staging: Path) -> str:
    """The first family file of the corpus with the configs its services name: the shape a draft follows."""
    for path in sorted((staging / SERVICES_DIR).glob(f"*{ENTRY_SUFFIX}")):
        files = [path, *(staging / config for config in _service_configs(path))]
        if all(each.is_file() for each in files):
            return "\n\n".join(f"--- {each.relative_to(staging).as_posix()} ---\n{each.read_text(encoding='utf-8')}"
                               for each in files)
    return ""


# --------------------------------------------------------------------------- writing the staging copy


def _track(run: _Run, unit: str, relative: str) -> Path:
    """Record *relative* as written by *unit*, keeping the bytes the corpus held first; its staging path."""
    target = run.staging / relative
    if relative not in run.originals:
        run.originals[relative] = target.read_bytes() if target.is_file() else None
    run.written.setdefault(unit, set()).add(relative)
    return target


def _write(run: _Run, unit: str, relative: str, text: str) -> None:
    target = _track(run, unit, relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def _restore(run: _Run, unit: str) -> None:
    """Put back every file *unit* wrote as the corpus held it."""
    for relative in run.written.pop(unit, set()):
        target = run.staging / relative
        original = run.originals[relative]
        if original is None:
            target.unlink(missing_ok=True)
        else:
            target.write_bytes(original)


def _include_lines(paths: Sequence[str]) -> list[str]:
    return [f"include '{path}';" for path in paths]


def _compose(run: _Run, entry: str) -> str | None:
    """*entry*'s file: its includes of every family file the staging copy holds for it, and its system."""
    base = run.bases[entry]
    needed = sorted(
        unit.source for unit in run.units.values()
        if not unit.is_system and entry in unit.entries and (run.staging / unit.source).is_file()
    )
    system = system_unit_name(entry)
    if system in run.written:
        includes = sorted(set(base.includes) | set(needed))
        source = run.drafts[system].files.source.strip()
        return "\n".join([ENTRY_HEADER.format(entry=entry), *_include_lines(includes), "", source, ""])
    if base.text is None:
        return None
    lines = base.text.splitlines()
    at = base.system_line - 1
    missing = [path for path in needed if path not in base.includes]
    return "\n".join([*lines[:at], *_include_lines(missing), *lines[at:]]) + "\n"


def _write_entries(run: _Run) -> None:
    for entry in run.bases:
        target = run.staging / f"{entry}{ENTRY_SUFFIX}"
        text = _compose(run, entry)
        if text is None:
            target.unlink(missing_ok=True)
        else:
            target.write_text(text, encoding="utf-8")


def _profiles(run: _Run, unit: DraftUnit) -> tuple[str, ...]:
    """Every profile an entry reading *unit* runs, as the staging copy declares them."""
    profiles: list[str] = []
    for entry in unit.entries:
        path = run.staging / f"{entry}{ENTRY_SUFFIX}"
        if not path.is_file():
            continue
        try:
            profiles.extend(entry_profiles(path))
        except (ValueError, OSError, DcfgSyntaxError, *PARSER_REFUSALS):
            continue
    return tuple(dict.fromkeys(profiles))


def _write_draft(run: _Run, unit: DraftUnit, draft: UnitDraft) -> list[str]:
    """Write *draft* of *unit*, each config declaring every profile its entries run; why it could not be. A
    system's source is its entry's, which :func:`_compose` writes around it."""
    if unit.is_system:
        _track(run, unit.name, unit.source)
    else:
        _write(run, unit.name, unit.source, draft.files.source)
    profiles = _profiles(run, unit)
    try:
        for path, text in draft.files.files:
            _write(run, unit.name, path, with_profiles(text, profiles, path) if profiles else text)
    except (FixtureAuthorError, DcfgSyntaxError) as error:
        _restore(run, unit.name)
        return [str(error)]
    return []


# --------------------------------------------------------------------------- checking and attributing


def _renames(run: _Run) -> tuple[Rename, ...]:
    drafted = (rename for name in run.written for rename in run.drafts[name].renames)
    return tuple(sorted({*run.prior, *drafted}))


def _renamed_entry(entry: EntryPlan, renames: Sequence[Rename]) -> EntryPlan:
    families = {family: apply_renames(needs, renames) for family, needs in entry.families.items()}
    return replace(entry, system=apply_renames(entry.system, renames), families=families)


def _check_one(run: _Run, entry: EntryPlan) -> EntryCheck:
    """*entry* checked in the staging copy; one the parser refuses (two files declaring one service) does not
    run, with the parser's message."""
    try:
        return check_entry(run.staging, entry, run.drafter.families)
    except PARSER_REFUSALS as error:
        return EntryCheck(entry.entry, (), (str(error),), (), ())


def _check(run: _Run) -> list[EntryCheck]:
    _write_entries(run)
    renames = _renames(run)
    return [_check_one(run, _renamed_entry(entry, renames)) for entry in run.plan.entries]


def _need_owners(run: _Run) -> dict[tuple[str, str, str], str]:
    """Each ``(entry, kind, path)`` a family unit must provide, renames applied, with that unit."""
    renames = _renames(run)
    return {
        (entry, need.kind, need.path): unit.name
        for unit in run.units.values() if not unit.is_system
        for need in apply_renames(unit.needs, renames)
        for entry in unit.entries
    }


def _unit_files(run: _Run, unit: DraftUnit) -> list[str]:
    files = [unit.source, *_own_configs(run, unit), *run.written.get(unit.name, set())]
    return sorted({Path(path).name for path in files})


def _named_owners(run: _Run, entry: str, error: str) -> list[str]:
    """The units reading *entry* whose files *error* names."""
    readers = [unit for unit in run.units.values() if entry in unit.entries]
    return [unit.name for unit in readers if any(name in error for name in _unit_files(run, unit))]


def _error_owners(run: _Run, entry: str, error: str) -> list[str]:
    """The units *error* of *entry* is sent to: those whose files it names, else those asked this round,
    else the entry's system unit."""
    asked = [unit.name for unit in run.units.values() if entry in unit.entries and unit.name in run.asked]
    return _named_owners(run, entry, error) or asked or [system_unit_name(entry)]


def _control_unit(run: _Run, entry: str) -> str:
    """The ``core`` unit, made to read *entry*: it adds the control service an absence assertion reads."""
    core = run.units.get(CORE_FAMILY) or DraftUnit(CORE_FAMILY, family_source(CORE_FAMILY), (), ())
    if entry not in core.entries:
        core = replace(core, entries=tuple(sorted({*core.entries, entry})))
    run.units[CORE_FAMILY] = core
    return CORE_FAMILY


def _entry_problems(run: _Run, check: EntryCheck, owners: Mapping[tuple[str, str, str], str]) -> Iterator[tuple[str, str]]:
    system = system_unit_name(check.entry)
    if not check.profiles:
        # Its families' needs stay unchecked in this entry until it runs: its system unit fails meanwhile.
        families = sorted(unit.name for unit in run.units.values() if not unit.is_system and check.entry in unit.entries)
        problem = (f"the entry {check.entry} does not run, so the needs of {families} stay unchecked in it: "
                   f"{'; '.join(check.errors)}")
        owners = {name for error in check.errors for name in _named_owners(run, check.entry, error)}
        for owner in sorted({system, *owners}):
            yield owner, problem
        return
    for missing in check.unprovided:
        owner = system if missing.kind in SYSTEM_KINDS else owners.get((check.entry, missing.kind, missing.path), system)
        fact = f" fact {missing.fact!r}" if missing.fact is not None else ""
        yield owner, f"{check.entry}/{missing.profile}: {missing.kind} {missing.path}{fact}: {missing.reason}"
    for error in check.errors:
        for owner in _error_owners(run, check.entry, error):
            yield owner, f"{check.entry}: {error}"
    if check.uncontrolled:
        core = _control_unit(run, check.entry)
        yield core, (f"every service of the entry {check.entry} holds {list(check.uncontrolled)}: add to "
                     f"{family_source(CORE_FAMILY)} a service holding no block and no API, the control service an "
                     "absence assertion reads.")


def _judge(run: _Run) -> None:
    """Check every entry; each unit not queued passes or carries the problems sent to it, after those its
    answer was sent back with this round."""
    checks = _check(run)
    owners = _need_owners(run)
    found: dict[str, list[str]] = {name: list(problems) for name, problems in run.sent_back.items()}
    for check in checks:
        for owner, problem in _entry_problems(run, check, owners):
            found.setdefault(owner, []).append(problem)
    # An entry that does not run, or runs with an error, checks no need: a family with no clean entry
    # stays unchecked. It is asked only when an error names its files; otherwise it waits.
    clean = {check.entry for check in checks if check.profiles and not check.errors}
    unchecked = [
        unit for unit in run.units.values()
        if not unit.is_system and unit.entries and not clean & set(unit.entries)
    ]
    run.waiting = {unit.name for unit in unchecked if unit.name not in found}
    for unit in unchecked:
        found.setdefault(unit.name, []).append(
            f"waits on the entries {list(unit.entries)}, none of which runs clean, so its needs stay unchecked")
    for name in run.units:
        if name in run.queued:
            continue
        if found.get(name):
            run.problems[name] = found[name]
            run.passing.discard(name)
        else:
            run.problems.pop(name, None)
            run.passing.add(name)


# --------------------------------------------------------------------------- one round


def _user_prompt(run: _Run, unit: DraftUnit) -> str:
    return library_user_prompt(
        unit=unit,
        current=_current_files(run, unit),
        elsewhere=_services_elsewhere(run, unit),
        reference=run.drafter.reference,
        problems=run.problems.get(unit.name, []),
        previous=run.drafts.get(unit.name),
        withheld=run.drafter.content.carries_term,
    )


def _answer_tokens(run: _Run, unit: DraftUnit) -> int:
    """The tokens *unit*'s answer may take: its current files rewritten with a declaration per need, and the
    configs."""
    held = sum(len(text) for text in _current_files(run, unit).values())
    needed = sum(len(need_line(need)) for need in unit.needs)
    return ANSWER_TOKENS + (held + needed) // CHARS_PER_TOKEN


def _window(run: _Run, unit: DraftUnit, user: str) -> int:
    """The window holding *user*, the last draft a resend carries back and the answer."""
    return context_window(run.system, user + " " * (2 * _answer_tokens(run, unit) * CHARS_PER_TOKEN))


def _size(run: _Run) -> None:
    """Queue at once each unit no request holds whole, and set the run's window to the widest of the rest."""
    windows: list[int] = []
    for name, unit in run.units.items():
        needed = _window(run, unit, _user_prompt(run, unit))
        if needed > MAX_REQUEST_TOKENS:
            run.queued[name] = QueuedUnit(unit, (
                f"its request needs a {needed}-token window ({len(unit.needs)} needs), more than the "
                f"{MAX_REQUEST_TOKENS} a request is sent with, so no model reads it whole; finish it by hand.",
            ), None)
            continue
        windows.append(needed)
    run.window = max(windows, default=MIN_CONTEXT_TOKENS)


def _ask(run: _Run, name: str) -> UnitDraft | str:
    unit = run.units[name]
    user = _user_prompt(run, unit)
    try:
        answer = ask_json(run.drafter.pool, run.system, user, LIBRARY_SCHEMA, max_tokens=_answer_tokens(run, unit),
                          context_window=max(run.window, _window(run, unit, user)))
    except NoModelAnswer as error:
        return str(error)
    return parse_unit_answer(answer)


def _claims(run: _Run, unit: DraftUnit) -> Claims:
    configs = {
        path: other.name
        for other in run.units.values() if other.name != unit.name
        for path in [*_own_configs(run, other), *run.written.get(other.name, set())]
    }
    paths = frozenset(need.path for other in run.units.values() for need in other.needs)
    others = (rename for name in run.written if name != unit.name for rename in run.drafts[name].renames)
    return Claims(configs, paths, frozenset({*run.prior, *others}))


def _queue(run: _Run, name: str, problems: Sequence[str], draft: UnitDraft | None) -> None:
    _restore(run, name)
    run.queued[name] = QueuedUnit(run.units[name], tuple(problems), draft)
    run.passing.discard(name)


def _precheck(run: _Run, unit: DraftUnit, draft: UnitDraft) -> list[str]:
    def exists(path: str) -> bool:
        return (run.drafter.root / path).is_file()

    claims = _claims(run, unit)
    own = frozenset(_own_configs(run, unit))
    return [
        *source_problems(unit, draft.files.source),
        *config_problems(unit, draft.files, own, claims, exists),
        *rename_problems(unit, draft.renames, claims),
    ]


def _take(run: _Run, name: str, answer: UnitDraft | str) -> None:
    """Record *name*'s answer: refused and queued, sent back, or written to the staging copy."""
    if isinstance(answer, str):
        run.sent_back[name] = [answer]
        return
    secrets = secret_sites(answer.files)
    if secrets:
        run.drafts.pop(name, None)
        _queue(run, name, [f"the draft holds a string literal that looks like a raw secret at {secrets}; it is "
                           "refused and never written (the value is not repeated)."], None)
        return
    unit = run.units[name]
    problems = _precheck(run, unit, answer)
    run.drafts[name] = answer
    if problems:
        run.sent_back[name] = problems
        return
    _restore(run, name)
    problems = _write_draft(run, unit, answer)
    if problems:
        run.sent_back[name] = problems


def _round(run: _Run) -> bool:
    """Ask for every unit not passing or queued, write what passes the read-only checks and check every
    entry once; whether anything was asked."""
    idle = {*run.passing, *run.queued, *run.waiting}
    asking = [name for name in run.units if name not in idle]
    if not asking:
        return False
    answers = dict(zip(asking, parallel(asking, lambda name: _ask(run, name)), strict=True))
    run.asked = set(asking)
    run.sent_back = {}
    # The systems first: a family's configs declare the profiles its entries' systems run.
    for name in sorted(asking, key=lambda each: not run.units[each].is_system):
        _take(run, name, answers[name])
        _write_entries(run)
    _judge(run)
    return True


def _settle(run: _Run) -> None:
    """Queue every unit still failing, then check again without them until every unit left passes."""
    run.asked = set()
    run.sent_back = {}
    while True:
        failing = [name for name in run.units if name not in run.passing and name not in run.queued]
        if not failing:
            return
        for name in failing:
            _queue(run, name, run.problems.get(name, []), run.drafts.get(name))
        _judge(run)


# --------------------------------------------------------------------------- landing


def _land(run: _Run) -> list[Path]:
    """Copy each landed unit's files, the entries they belong to and the renames to the corpus."""
    root = run.drafter.root
    landed = [name for name in run.written if name in run.passing]
    paths = {path for name in landed for path in run.written[name]}
    entries = {f"{entry}{ENTRY_SUFFIX}" for name in landed for entry in run.units[name].entries}
    paths.update(entry for entry in entries if (run.staging / entry).is_file())
    written: list[Path] = []
    for relative in sorted(paths):
        source, target = run.staging / relative, root / relative
        if target.is_file() and target.read_bytes() == source.read_bytes():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        written.append(target)
    renames = _renames(run)
    if renames != run.prior:
        write_renames(run.drafter.renames_file, renames)
        written.append(run.drafter.renames_file)
    return written


def _write_queues(run: _Run) -> list[Path]:
    files: list[Path] = []
    for name in run.units:
        path = run.drafter.queue_dir / f"{QUEUE_PREFIX}{name}{_QUEUE_SUFFIX}"
        queued = run.queued.get(name)
        if queued is None:
            path.unlink(missing_ok=True)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(unit_queue_text(queued.unit, queued.problems, queued.draft), encoding="utf-8")
        files.append(path)
    return files


def _start(drafter: LibraryDrafter, plan: LibraryPlan, staging: Path) -> _Run:
    shutil.copytree(drafter.root, staging)
    bases = {entry.entry: _entry_base(staging, entry.entry) for entry in plan.entries}
    units = plan_units(plan, {entry: base.system_config for entry, base in bases.items()})
    templates = staging / TEMPLATES
    system = library_system_prompt(templates.read_text(encoding="utf-8") if templates.is_file() else "", _example(staging))
    return _Run(drafter, plan, units, staging, bases, read_renames(drafter.renames_file), system)


def draft_library(drafter: LibraryDrafter, plan: LibraryPlan) -> LibraryOutcome:
    """Check every entry of *plan*, draft each unit lacking something round by round, land what passes in
    the corpus and queue the rest.

    Raises:
        LocalLlmUnavailable: No local model can serve; nothing is written.
        LibraryDraftError: An entry or ``renames.json`` has a form the run cannot read.
    """
    register_installed_parsers()
    with tempfile.TemporaryDirectory(prefix="fixture-author-library-") as temporary:
        run = _start(drafter, plan, Path(temporary) / "corpus")
        _size(run)
        drafter.pool.activate(run.window)
        _judge(run)
        for _ in range(drafter.max_rounds):
            if not _round(run):
                break
        _settle(run)
        written = _land(run)
    landed = tuple(sorted(name for name in run.passing if name in run.written))
    provided = tuple(sorted(name for name in run.passing if name not in run.written))
    queued = tuple(run.queued[name] for name in sorted(run.queued))
    return LibraryOutcome(landed, provided, queued, tuple(_write_queues(run)), tuple(written))


def print_library_outcome(outcome: LibraryOutcome) -> None:
    """One line per unit landed, already provided and queued, and the files written."""
    for name in outcome.provided:
        print(f"[ OK ] {name}: already provided")
    for name in outcome.landed:
        print(f"[ OK ] {name}: landed")
    for queued in outcome.queued:
        print(f"[QUEUE] {queued.unit.name}: {len(queued.problems)} problem(s), queued")
    for path in [*outcome.written, *outcome.queue_files]:
        print(f"  wrote {path}")


def run_library(drafter: LibraryDrafter, plan: LibraryPlan) -> int:
    """Draft the library; the exit code: 0 every unit landed or was provided, 1 a unit was queued,
    :data:`EXIT_NO_MODEL` no local model could serve (nothing is written)."""
    try:
        outcome = draft_library(drafter, plan)
    except LocalLlmUnavailable as error:
        print(f"ERROR: no local model can draft the corpus library; nothing is written: {error}")
        return EXIT_NO_MODEL
    except LibraryDraftError as error:
        print(f"ERROR: {error}")
        return EXIT_INCOMPLETE
    print_library_outcome(outcome)
    return EXIT_INCOMPLETE if outcome.queued else 0


def run_library_command(settings: LocalLlmSettings, needs_file: Path = NEEDS_FILE, root: Path = CORPUS_ROOT) -> int:
    """``fixture-author.ps1 library``: plan the corpus from *needs_file* and draft it into *root*.

    Raises:
        UsageError: *needs_file* does not exist.
    """
    if not needs_file.is_file():
        raise UsageError(f"{needs_file} does not exist. Fix: run `fixture-author.ps1 needs` first; the library "
                         "is drafted from its inventory.")
    try:
        inventory = read_needs_inventory(needs_file)
        families = block_families(node_kinds())
        plan = plan_library(inventory, families, platform_entries(), library_choices(root))
        content = ContentFilter(WORKSPACE_DIR)
    except (LibraryPlanError, AssistError, ValueError, FileNotFoundError) as error:
        print(f"ERROR: {error}")
        return EXIT_INCOMPLETE
    pool = LocalLlmPool(settings, report=lambda line: logger.info("%s", line))
    reference = SYNTAX_REFERENCE.read_text(encoding="utf-8")
    return run_library(LibraryDrafter(pool, content, root, families, reference), plan)


__all__ = [
    "ENTRY_HEADER",
    "QUEUE_PREFIX",
    "RENAMES_FILE",
    "LibraryDrafter",
    "LibraryOutcome",
    "QueuedUnit",
    "draft_library",
    "print_library_outcome",
    "run_library",
    "run_library_command",
]
