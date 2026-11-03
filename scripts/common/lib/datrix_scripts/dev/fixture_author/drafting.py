"""Drafting an area project with a local model, round by round, each round verified by one analysis.

Each planned variant of an area is asked for alone (:mod:`datrix_scripts.dev.fixture_author.prompting`):
the model answers one fragment and the files it reads. A fragment is checked before it is written --
a string literal that looks like a raw secret queues the variant at once and nothing of it is
written; a path outside the fragment's own names, a ``.dcfg`` that does not parse, an annotation
that cannot be read or names another variant, an undocumented tag, or a security code's ``@expect``
without that code's tag is sent back. The fragments that pass are assembled under the area's
header and ``system`` declaration and written, and the area is analyzed once, as its whole-analysis
case reads it (:func:`datrix_scripts.dev.fixture_author.diagnostics.verify_areas`). Each reported
diagnostic is matched to the ``@expect`` on its line:

* one firing where no ``@expect`` of it stands (a cascade) goes back to the fragment holding that
  line, with the instruction to move the provoking construct into its own service or module;
* an ``@expect`` its variant does not fire on (not provoked) goes back to its fragment;
* a diagnostic no fragment holds, or an area that cannot be analyzed, goes back to every fragment
  new in that round.

At most :data:`MAX_ROUNDS` rounds per area. A variant still failing is taken out of the area and
written, with its last analysis output and draft, to ``<queue>/<area>.md``; the area is written
with the rest once its analysis reports exactly what it annotates. A profile an ``@profile`` names
is listed in the area's ``@profiles`` header and appended to every ``.dcfg`` the area reads that
lacks it, extending the test profile. When no local model can serve, the run stops before it
writes anything; one that stops mid-area removes what that area wrote.
"""

from __future__ import annotations

import logging
import re
import tempfile
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from functools import cache
from pathlib import Path
from typing import Final

from datrix_common.config.dcfg.errors import DcfgSyntaxError
from datrix_common.config.secret_hygiene import looks_like_raw_secret
from datrix_common.testing.tag_vocabulary import documented_tags
from datrix_language.parser.dcfg_parser import parse_dcfg
from datrix_semantic.diagnostics.catalog import DiagnosticCatalog
from datrix_semantic.diagnostics.security_families import security_tags_of
from datrix_testing.cases.annotation_reading import (
    ANALYSIS_DIRECTIVE,
    EXPECT,
    LINE_COMMENT_MARKER,
    PROFILES_DIRECTIVE,
    REASON_DIRECTIVE,
    TAGS_DIRECTIVE,
    TARGETS_ANALYSIS,
    AnnotatedFixture,
    AnnotationError,
    read_annotations,
)
from datrix_testing.cases.annotations import DIAGNOSTIC_FIXTURES
from datrix_testing.cases.fences import line_literals
from datrix_testing.cases.package import PackageCases
from datrix_testing.context import TEST_PROFILE
from datrix_testing.parsing import PARSER_REFUSALS, parse_as_written

from datrix_scripts.dev.fixture_author.diagnostics import (
    SYSTEM_CONFIG,
    AreaPlan,
    AreaVerdict,
    FixtureAuthorError,
    ensure_scaffold,
    system_owner,
    variant_code,
    verify_areas,
)
from datrix_scripts.dev.fixture_author.prompting import (
    ANALYZER_OUTPUT_HEADING,
    CASCADE_INSTRUCTION,
    DRAFT_SCHEMA,
    NOT_PROVOKED_INSTRUCTION,
    SEED_SUFFIX,
    SYNTAX_REFERENCE,
    DraftFiles,
    allowed_path,
    area_reason,
    catalog_entry,
    old_example,
    system_prompt,
    user_prompt,
    variant_names,
)
from datrix_scripts.local_llm import LocalLlmPool, LocalLlmSettings, LocalLlmUnavailable
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.skill.common import EXIT_NO_MODEL, ContentFilter, NoModelAnswer, ask_json, object_list, parallel

logger = logging.getLogger(__name__)

#: The rounds a variant is drafted in before it is queued.
MAX_ROUNDS: Final[int] = 4
#: The feature tag every area's header carries: the area proves the analyzer's diagnostics.
HEADER_TAG: Final[str] = "error-messages"
#: Where a variant still failing is written for a person to finish.
QUEUE_DIR: Final[Path] = WORKSPACE_DIR / ".tmp" / "fixture-author" / "queue"
#: The analyzer output lines one feedback or queue entry carries.
FEEDBACK_OUTPUT_LINES: Final[int] = 40
#: The version every area's system declares.
SYSTEM_VERSION: Final[str] = "1.0.0"
_DCFG_SUFFIX: Final[str] = ".dcfg"
_PROBE_NAME: Final[str] = "probe.dtrx"
_QUEUE_SUFFIX: Final[str] = ".md"


class ProblemKind(Enum):
    """Why a draft goes back to the model."""

    DRAFT = "draft"
    CASCADE = "cascade"
    NOT_PROVOKED = "not provoked"
    REFUSED = "refused"


@dataclass(frozen=True)
class Problem:
    """One reason a variant's draft failed."""

    kind: ProblemKind
    text: str


@dataclass(frozen=True)
class QueuedVariant:
    """A variant the run could not land, for a person to finish.

    Attributes:
        variant: ``<CODE>.<variant>``.
        problems: Why its last draft failed.
        output: The analyzer output its last analysis showed it.
        draft: Its last draft; ``None`` when the draft held a secret literal, which is never repeated.
    """

    variant: str
    problems: tuple[str, ...]
    output: tuple[str, ...] = ()
    draft: DraftFiles | None = None


@dataclass(frozen=True)
class AreaOutcome:
    """What one area's drafting landed and queued."""

    area: AreaPlan
    entry: Path
    landed: tuple[str, ...]
    queued: tuple[QueuedVariant, ...]
    queue_file: Path | None


@dataclass(frozen=True)
class Drafter:
    """What drafting every area of one package reads.

    Attributes:
        package: The package's case session; its diagnostics fixtures are where areas are written.
        catalog: The diagnostic catalog the prompts quote.
        pool: The local model servers.
        content: The customer-term filter every prompt part passes.
        queue_dir: Where queued variants are written.
        reference: The syntax reference text.
        examples: The diagnostics directory the old per-code fixtures are read from, as examples.
        max_rounds: The rounds per area.
    """

    package: PackageCases
    catalog: DiagnosticCatalog
    pool: LocalLlmPool
    content: ContentFilter
    queue_dir: Path
    reference: str
    examples: Path
    max_rounds: int = MAX_ROUNDS

    @property
    def diagnostics(self) -> Path:
        """The package's diagnostics fixtures directory."""
        return self.package.tests_root / DIAGNOSTIC_FIXTURES


# --------------------------------------------------------------------------- the draft


def _is_canonical_uuid(value: str) -> bool:
    try:
        return str(uuid.UUID(value)) == value
    except ValueError:
        return False


def secret_literal_lines(text: str) -> list[int]:
    """The 1-based lines of *text* holding a string literal ``looks_like_raw_secret`` flags.

    A canonical lowercase UUID is no secret: it is the shape a container database's ``id``
    (``RdbmsConfig.id: UUID``) is declared as, and every owner configuration writes one.
    """
    return [
        number
        for number, line in enumerate(text.splitlines(), start=1)
        if any(looks_like_raw_secret(literal) and not _is_canonical_uuid(literal) for literal in line_literals(line))
    ]


def parse_draft(answer: Mapping[str, object]) -> DraftFiles | Problem:
    """The draft a model's JSON *answer* states, or why it states none."""
    source = answer.get("source")
    configs = answer.get("configs")
    if not isinstance(source, str) or not source.strip() or not isinstance(configs, list):
        return Problem(ProblemKind.DRAFT, 'the answer is not {"source": <text>, "configs": [...]}.')
    files = [(item.get("path"), item.get("text")) for item in object_list(configs)]
    if len(files) != len(configs) or not all(isinstance(p, str) and isinstance(t, str) for p, t in files):
        return Problem(ProblemKind.DRAFT, 'each entry of configs is {"path": <text>, "text": <text>}.')
    return DraftFiles(source, tuple((str(path), str(text)) for path, text in files))


def secret_sites(draft: DraftFiles) -> list[str]:
    """Where *draft* holds a secret-looking literal (``<file>:<line>``), never the value."""
    named = [("fragment", draft.source), *draft.files]
    return [f"{label}:{line}" for label, text in named for line in secret_literal_lines(text)]


@cache
def _vocabulary() -> frozenset[str]:
    return documented_tags()


def header_tags(area: AreaPlan) -> tuple[str, ...]:
    """The tags an area's header carries: :data:`HEADER_TAG` and the security tags every code of the
    area shares, so each of its security ``@expect`` carries its code's tag."""
    required = [security_tags_of(variant_code(variant)) for variant in area.variants]
    shared = frozenset.intersection(*required) if required else frozenset()
    return (HEADER_TAG, *sorted(shared))


def with_profiles(text: str, profiles: Sequence[str], source: str) -> str:
    """*text*, a ``.dcfg``, declaring every profile of *profiles* it lacks as
    ``profile <p> as "<p>" extends test {}``; unchanged when it declares no profile (a template
    library) or every one.

    Raises:
        FixtureAuthorError: The text does not end its declaration with ``}``, or does not declare
            the appended profiles once they are appended.
    """
    declared = {profile.name for profile in parse_dcfg(text, source).profiles}
    missing = [profile for profile in profiles if profile not in declared]
    if not declared or not missing:
        return text
    body = text.rstrip()
    if not body.endswith("}"):
        raise FixtureAuthorError(f"{source} does not end its config declaration with '}}'.")
    added = "".join(f'\n  profile {name} as "{name}" extends {TEST_PROFILE} {{}}\n' for name in missing)
    updated = f"{body[:-1].rstrip()}\n{added}}}\n"
    now = {profile.name for profile in parse_dcfg(updated, source).profiles}
    if not set(profiles) <= now:
        raise FixtureAuthorError(f"{source} does not declare {sorted(set(profiles) - now)} after they were appended.")
    return updated


# --------------------------------------------------------------------------- one area's run


@dataclass(frozen=True)
class _Span:
    variant: str
    first: int
    last: int


@dataclass(frozen=True)
class _Layout:
    """Where each variant's fragment and files stand in the written area."""

    entry_file: str
    spans: tuple[_Span, ...]
    owners: Mapping[str, str]

    def owner(self, file: str, line: int | None) -> str | None:
        if file == self.entry_file and line is not None:
            return next((span.variant for span in self.spans if span.first <= line <= span.last), None)
        return self.owners.get(file)


@dataclass(frozen=True)
class _Site:
    """One ``@expect``: the variant, where it stands, and the profiles it is limited to."""

    variant: str
    file: str
    line: int
    profiles: tuple[str, ...]

    def holds_in(self, profile: str | None) -> bool:
        return not self.profiles or profile in self.profiles


@dataclass
class _AreaRun:
    drafter: Drafter
    area: AreaPlan
    root: Path
    entry: Path
    owner: str
    system: str
    drafts: dict[str, DraftFiles] = field(default_factory=dict)
    problems: dict[str, list[Problem]] = field(default_factory=dict)
    outputs: dict[str, tuple[str, ...]] = field(default_factory=dict)
    passing: set[str] = field(default_factory=set)
    queued: dict[str, QueuedVariant] = field(default_factory=dict)
    written: set[Path] = field(default_factory=set)
    scaffold: tuple[Path, ...] = ()
    clean: tuple[str, ...] = ()

    def ordered(self, variants: Iterable[str]) -> list[str]:
        chosen = set(variants)
        return [variant for variant in self.area.variants if variant in chosen]


def area_header(area: AreaPlan, variants: Sequence[str], profiles: Sequence[str]) -> list[str]:
    """The header lines of *area* holding *variants*: its tags, reason, the ``@analysis`` line it
    declares and the *profiles* it lists."""
    lines = [
        f"{LINE_COMMENT_MARKER} @{TAGS_DIRECTIVE} {', '.join(header_tags(area))}",
        f"{LINE_COMMENT_MARKER} @{REASON_DIRECTIVE} {area_reason(area, variants)}",
    ]
    if area.target_checks:
        lines.append(f"{LINE_COMMENT_MARKER} @{ANALYSIS_DIRECTIVE} {TARGETS_ANALYSIS}")
    if profiles:
        lines.append(f"{LINE_COMMENT_MARKER} @{PROFILES_DIRECTIVE} {', '.join(profiles)}")
    return lines


def _assemble(run: _AreaRun, drafts: Mapping[str, DraftFiles], profiles: Sequence[str]) -> tuple[str, tuple[_Span, ...]]:
    """The area file holding *drafts* (in plan order) under its header and ``system`` declaration."""
    lines = area_header(run.area, list(drafts), profiles)
    lines.extend([f"system {run.owner}('{SYSTEM_CONFIG.as_posix()}') : version('{SYSTEM_VERSION}') {{}}", ""])
    spans: list[_Span] = []
    for variant, draft in drafts.items():
        first = len(lines) + 1
        lines.append(f"{LINE_COMMENT_MARKER} {variant}")
        lines.extend(draft.source.strip("\n").splitlines())
        spans.append(_Span(variant, first, len(lines)))
        lines.append("")
    return "\n".join(lines) + "\n", tuple(spans)


def _annotation_problems(variant: str, fixture: AnnotatedFixture) -> list[str]:
    expects = [annotation for annotation in fixture.annotations if annotation.kind == EXPECT]
    problems: list[str] = []
    if not any(annotation.payload == variant for annotation in expects):
        problems.append(f"the fragment writes no '{LINE_COMMENT_MARKER} @{EXPECT} {variant}'.")
    foreign = sorted({annotation.payload for annotation in expects if annotation.payload != variant})
    if foreign:
        problems.append(f"the fragment annotates {foreign}; it annotates its own variant only.")
    if len(expects) != len(fixture.annotations):
        problems.append(f"the fragment writes annotations other than @{EXPECT}.")
    unknown = sorted({tag for annotation in fixture.annotations for tag in annotation.tags} - _vocabulary())
    if unknown:
        problems.append(f"the tags {unknown} are no documented feature tags.")
    required = security_tags_of(variant_code(variant))
    carried = [set(fixture.tags) | set(annotation.tags) for annotation in expects]
    if required and any(not required & tags for tags in carried):
        problems.append(f"each @{EXPECT} of {variant_code(variant)} carries one of the tags {sorted(required)}.")
    return problems


def _config_problems(path: str, text: str) -> list[str]:
    if not path.endswith(_DCFG_SUFFIX):
        return []
    try:
        declaration = parse_dcfg(text, path)
    except DcfgSyntaxError as error:
        return [f"{path} does not parse: {error}"]
    declared = {profile.name for profile in declaration.profiles}
    if declared and TEST_PROFILE not in declared:
        return [f"{path} declares the profiles {sorted(declared)} and not '{TEST_PROFILE}'."]
    return []


def _path_problems(run: _AreaRun, variant: str, draft: DraftFiles, claimed: Mapping[str, str]) -> list[str]:
    names = variant_names(variant)
    allowed = f"{names.config_prefix}...{_DCFG_SUFFIX}" + (f" or seed/<Entity>{SEED_SUFFIX}" if run.area.seeded else "")
    problems: list[str] = []
    seen: set[str] = set()
    for path, text in draft.files:
        if not allowed_path(path, names, seeded=run.area.seeded):
            problems.append(f"{path!r} is not a path this fragment may write: {allowed}.")
            continue
        target = run.root / path
        if path in seen or claimed.get(path, variant) != variant or (target.exists() and target not in run.written):
            problems.append(f"{path} is written by another fragment or already exists; choose another name.")
        seen.add(path)
        problems.extend(_config_problems(path, text))
    return problems


def _precheck(run: _AreaRun, variant: str, draft: DraftFiles, claimed: Mapping[str, str]) -> list[str]:
    """Why *draft* cannot be written, read without an analysis: its paths, configurations,
    annotations and parse -- a fragment the parser refuses (a second ``system``, a duplicate
    entity) would make the whole area unreadable, so it goes back alone before the area is written."""
    problems = _path_problems(run, variant, draft, claimed)
    text, (span,) = _assemble(run, {variant: draft}, ())
    with tempfile.TemporaryDirectory(prefix="fixture-author-") as temporary:
        probe = Path(temporary) / _PROBE_NAME
        probe.write_text(text, encoding="utf-8")
        try:
            fixture = read_annotations(probe)
            parse_as_written(probe, text=text)
        except (AnnotationError, *PARSER_REFUSALS) as error:
            return [*problems, _fragment_message(str(error), probe, span.first)]
    return problems + _annotation_problems(variant, fixture)


def _fragment_message(message: str, probe: Path, note_line: int) -> str:
    """*message*, about the line ``<probe>:<n>`` of the probe file, about line ``n`` of the fragment
    instead (the fragment starts on the line after the note naming its variant)."""
    pattern = re.compile(f"{re.escape(str(probe))}:(\\d+)")
    return pattern.sub(lambda found: f"fragment line {int(found.group(1)) - note_line}", message)


def _write(run: _AreaRun, path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    run.written.add(path)


def _profiles_used(paths: Iterable[Path]) -> tuple[str, ...]:
    used = {profile for path in paths for annotation in read_annotations(path).annotations for profile in annotation.profiles}
    return (TEST_PROFILE, *sorted(used - {TEST_PROFILE})) if used else ()


def _declare_profiles(run: _AreaRun, wanted: Mapping[str, str], profiles: Sequence[str]) -> None:
    """Append *profiles* to every ``.dcfg`` the area reads that lacks one: its drafts' and its root's
    system configuration."""
    for path, config in wanted.items():
        if path.endswith(_DCFG_SUFFIX):
            _write(run, run.root / path, with_profiles(config, profiles, path))
    system = run.root / SYSTEM_CONFIG
    current = system.read_text(encoding="utf-8")
    updated = with_profiles(current, profiles, SYSTEM_CONFIG.as_posix())
    if updated != current:
        system.write_text(updated, encoding="utf-8")


def _write_area(run: _AreaRun, variants: Sequence[str]) -> _Layout:
    """Write the area holding *variants*' fragments and files; remove the files of any other draft."""
    drafts = {variant: run.drafts[variant] for variant in run.ordered(variants)}
    wanted = {path: text for draft in drafts.values() for path, text in draft.files}
    owners = {path: variant for variant, draft in drafts.items() for path, _ in draft.files}
    stale = [path for path in run.written if path != run.entry and path.relative_to(run.root).as_posix() not in wanted]
    for path in stale:
        path.unlink(missing_ok=True)
        run.written.discard(path)
    for path, text in wanted.items():
        _write(run, run.root / path, text)
    text, spans = _assemble(run, drafts, ())
    _write(run, run.entry, text)
    profiles = _profiles_used([run.entry, *(run.root / path for path in wanted if path.endswith(SEED_SUFFIX))])
    if profiles:
        text, spans = _assemble(run, drafts, profiles)
        _write(run, run.entry, text)
        _declare_profiles(run, wanted, profiles)
    return _Layout(run.entry.name, spans, owners)


def _sites(run: _AreaRun, layout: _Layout) -> list[_Site]:
    files = [run.entry, *(run.root / path for path in layout.owners if path.endswith(SEED_SUFFIX))]
    return [
        _Site(annotation.payload, path.relative_to(run.entry.parent).as_posix(), annotation.target, annotation.profiles)
        for path in files
        for annotation in read_annotations(path).annotations
        if annotation.kind == EXPECT
    ]


_Found = dict[str, list[Problem]]
_Shown = dict[str, list[str]]


def _located_problems(
    verdict: AreaVerdict, layout: _Layout, expected: set[tuple[str, int, str]], suspects: Sequence[str],
    problems: _Found, shown: _Shown,
) -> set[tuple[str, int | None, str]]:
    """Record each located diagnostic of *verdict* against the fragment holding it (every suspect
    when none does): shown always, a cascade when no ``@expect`` of it stands there. Return those
    that fired where they are expected."""
    fired: set[tuple[str, int | None, str]] = set()
    for diagnostic in verdict.located:
        owner = layout.owner(diagnostic.file, diagnostic.line)
        targets = [owner] if owner is not None else list(suspects)
        for variant in targets:
            shown.setdefault(variant, []).append(
                f"{diagnostic.variant} at {diagnostic.file}:{diagnostic.line}: {diagnostic.message}"
            )
        key = (diagnostic.file, diagnostic.line, diagnostic.variant)
        if key in expected:
            fired.add(key)
            continue
        problem = Problem(
            ProblemKind.CASCADE,
            f"{verdict.input_name}: {diagnostic.variant} fired at {diagnostic.file}:{diagnostic.line}, "
            f"where no @{EXPECT} of it stands.",
        )
        for variant in targets:
            problems.setdefault(variant, []).append(problem)
    return fired


def _verdict_problems(
    verdict: AreaVerdict, layout: _Layout, sites: list[_Site], suspects: Sequence[str], problems: _Found, shown: _Shown
) -> None:
    """Record each variant's problems in one area input's analysis, and the diagnostics it is shown."""
    if verdict.refused:
        for variant in suspects:
            problems.setdefault(variant, []).append(Problem(ProblemKind.REFUSED, f"{verdict.input_name}: {verdict.refused}"))
        return
    held = [site for site in sites if site.holds_in(verdict.profile)]
    expected = {(site.file, site.line, site.variant) for site in held}
    fired = _located_problems(verdict, layout, expected, suspects, problems, shown)
    for site in held:
        if (site.file, site.line, site.variant) not in fired:
            problems.setdefault(site.variant, []).append(Problem(
                ProblemKind.NOT_PROVOKED,
                f"{verdict.input_name}: '@{EXPECT} {site.variant}' describes {site.file}:{site.line}, "
                f"and it does not fire there.",
            ))


def _analyze(run: _AreaRun, variants: Sequence[str], suspects: Sequence[str]) -> _Found:
    """Write the area holding *variants*, analyze it once, and return each variant's problems
    (recording the analyzer output each is shown)."""
    try:
        layout = _write_area(run, variants)
        sites = _sites(run, layout)
    except AnnotationError as error:
        return {variant: [Problem(ProblemKind.REFUSED, str(error))] for variant in suspects}
    problems: _Found = {}
    shown: _Shown = {}
    for verdict in verify_areas(run.drafter.package, [run.area.name]):
        _verdict_problems(verdict, layout, sites, suspects, problems, shown)
    for variant in variants:
        run.outputs[variant] = tuple(dict.fromkeys(shown.get(variant, [])))[:FEEDBACK_OUTPUT_LINES]
    return problems


def _feedback(run: _AreaRun, variant: str) -> str:
    """What the model is told about *variant*'s failed draft."""
    problems = run.problems.get(variant, [])
    lines = [f"- {problem.text}" for problem in problems]
    kinds = {problem.kind for problem in problems}
    if ProblemKind.CASCADE in kinds:
        lines.append(CASCADE_INSTRUCTION)
    if ProblemKind.NOT_PROVOKED in kinds:
        lines.append(NOT_PROVOKED_INSTRUCTION)
    if kinds & {ProblemKind.CASCADE, ProblemKind.NOT_PROVOKED}:
        output = run.outputs.get(variant, ())
        lines.append(f"{ANALYZER_OUTPUT_HEADING} (in this fragment):\n" + ("\n".join(output) or "nothing fired in it"))
    return "\n".join(lines)


def _ask(run: _AreaRun, variant: str) -> DraftFiles | Problem:
    drafter = run.drafter
    feedback = _feedback(run, variant) if variant in run.problems else ""
    user = user_prompt(
        variant=variant,
        catalog=drafter.catalog,
        area=run.area,
        example=old_example(drafter.examples, variant),
        reference=drafter.reference,
        feedback=feedback,
        previous=run.drafts.get(variant) if feedback else None,
        withheld=drafter.content.carries_term,
    )
    try:
        answer = ask_json(drafter.pool, run.system, user, DRAFT_SCHEMA)
    except NoModelAnswer as error:
        return Problem(ProblemKind.DRAFT, str(error))
    return parse_draft(answer)


def _queue(run: _AreaRun, variant: str, problems: Sequence[str], draft: DraftFiles | None) -> None:
    run.queued[variant] = QueuedVariant(variant, tuple(problems), run.outputs.get(variant, ()), draft)
    run.passing.discard(variant)


def _queue_failing(run: _AreaRun, variant: str) -> None:
    _queue(run, variant, [problem.text for problem in run.problems.get(variant, [])], run.drafts.get(variant))


def _take_answer(run: _AreaRun, variant: str, answer: DraftFiles | Problem, claimed: dict[str, str]) -> bool:
    """Record *variant*'s *answer*; whether it is written and analyzed this round."""
    if isinstance(answer, Problem):
        run.problems[variant] = [answer]
        return False
    secrets = secret_sites(answer)
    if secrets:
        run.drafts.pop(variant, None)
        refusal = (f"the draft holds a string literal that looks like a raw secret at {secrets}; it is refused "
                   f"and never written (the value is not repeated).")
        _queue(run, variant, [refusal], None)
        return False
    run.drafts[variant] = answer
    problems = _precheck(run, variant, answer, claimed)
    if problems:
        run.problems[variant] = [Problem(ProblemKind.DRAFT, problem) for problem in problems]
        return False
    claimed.update((path, variant) for path, _ in answer.files)
    return True


def _judge(run: _AreaRun, present: Sequence[str], suspects: Sequence[str]) -> None:
    """Analyze the area holding *present*; each variant passes or carries its problems."""
    problems = _analyze(run, present, suspects)
    for variant in present:
        if problems.get(variant):
            run.problems[variant] = problems[variant]
            run.passing.discard(variant)
        else:
            run.problems.pop(variant, None)
            run.passing.add(variant)
    run.clean = () if any(problems.get(variant) for variant in present) else tuple(present)


def _round(run: _AreaRun) -> bool:
    """Ask for every variant not passing or queued, then write and analyze the area once; whether
    anything was asked."""
    asking = [variant for variant in run.area.variants if variant not in run.passing and variant not in run.queued]
    if not asking:
        return False
    answers = parallel(asking, lambda variant: _ask(run, variant))
    claimed = {path: variant for variant in run.passing for path, _ in run.drafts[variant].files}
    new = [variant for variant, answer in zip(asking, answers, strict=True) if _take_answer(run, variant, answer, claimed)]
    present = run.ordered([*run.passing, *new])
    if present:
        _judge(run, present, new or present)
    return True


def _settle(run: _AreaRun) -> None:
    """Queue every variant still failing, then rewrite the area without them until its analysis
    reports exactly what it annotates; remove the area when nothing is left."""
    for variant in run.area.variants:
        if variant not in run.passing and variant not in run.queued:
            _queue_failing(run, variant)
    while run.passing:
        present = run.ordered(run.passing)
        if run.clean == tuple(present):
            return
        _judge(run, present, present)
        for variant in present:
            if variant not in run.passing:
                _queue_failing(run, variant)
    _remove_written(run)


def _remove_written(run: _AreaRun) -> None:
    """Remove every file the run wrote (a seeded area's scaffold included), and every directory left
    empty under the diagnostics directory."""
    removed = [*run.written, *run.scaffold]
    for path in removed:
        path.unlink(missing_ok=True)
    diagnostics = run.drafter.diagnostics
    parents = {
        parent for path in removed for parent in path.parents
        if parent.is_relative_to(diagnostics) and parent != diagnostics
    }
    for directory in sorted(parents, key=lambda path: len(path.parts), reverse=True):
        if directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()
    run.written.clear()


def queue_text(package: str, area: AreaPlan, entry: Path, queued: Sequence[QueuedVariant], catalog: DiagnosticCatalog) -> str:
    """The queue file of *area*: each variant a person finishes by hand, with why it failed, its last
    analysis output and its last draft."""
    lines = [
        f"# Fixture-author queue: area {area.name}",
        "",
        f"Each variant below is not in {entry}. Finish each by hand under the same rule -- one construct, its "
        f"`{LINE_COMMENT_MARKER} @{EXPECT} <CODE>.<variant>`, nothing else reported -- then run "
        f"`fixture-author.ps1 diagnostics -Package {package} -Area {area.name} -Verify` and delete this file.",
    ]
    for item in queued:
        lines.extend(["", f"## {item.variant}", "", catalog_entry(catalog, item.variant), "", "### Why"])
        lines.extend(f"- {problem}" for problem in item.problems or ("no draft was answered",))
        lines.extend(["", "### Last analysis output", "", "```text", *(item.output or ("(none)",)), "```"])
        if item.draft is not None:
            lines.extend(["", "### Last draft", "", "```text", item.draft.rendered(), "```"])
    return "\n".join(lines) + "\n"


def _write_queue(run: _AreaRun) -> Path | None:
    path = run.drafter.queue_dir / f"{run.area.name}{_QUEUE_SUFFIX}"
    if not run.queued:
        path.unlink(missing_ok=True)
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    queued = [run.queued[variant] for variant in run.area.variants if variant in run.queued]
    path.write_text(queue_text(run.drafter.package.name, run.area, run.entry, queued, run.drafter.catalog), encoding="utf-8")
    return path


def draft_area(drafter: Drafter, area: AreaPlan) -> AreaOutcome:
    """Draft *area* round by round, write what passes, queue the rest.

    Raises:
        LocalLlmUnavailable: No local model can serve; what the area wrote is removed first.
    """
    root = area.root(drafter.diagnostics)
    entry = area.entry(drafter.diagnostics)
    scaffolded = ensure_scaffold(root)
    owner = system_owner(root)
    run = _AreaRun(drafter, area, root, entry, owner, system_prompt(area, root, owner))
    if area.seeded:
        run.scaffold = tuple(scaffolded)
    finished = False
    try:
        for _ in range(drafter.max_rounds):
            if not _round(run):
                break
        _settle(run)
        finished = True
    finally:
        if not finished:
            _remove_written(run)
    landed = tuple(run.ordered(run.passing))
    queued = tuple(run.queued[variant] for variant in area.variants if variant in run.queued)
    return AreaOutcome(area, entry, landed, queued, _write_queue(run))


def print_outcome(outcome: AreaOutcome) -> None:
    """One line per area: what landed where, and where the queued variants were written."""
    if not outcome.queued:
        print(f"[ OK ] {outcome.area.name}: {len(outcome.landed)} variant(s) landed in {outcome.entry}")
        return
    where = f"in {outcome.entry}" if outcome.landed else "(the area is not written)"
    print(
        f"[QUEUE] {outcome.area.name}: {len(outcome.landed)} variant(s) landed {where}; "
        f"{len(outcome.queued)} queued in {outcome.queue_file}"
    )


def draft_package(
    package: PackageCases,
    catalog: DiagnosticCatalog,
    areas: Sequence[AreaPlan],
    settings: LocalLlmSettings,
    *,
    content: ContentFilter,
    queue_dir: Path = QUEUE_DIR,
    examples: Path | None = None,
) -> int:
    """Draft each of *areas* (none of which is on disk) into *package*, its old per-code fixtures
    read from *examples* (default its own diagnostics directory); the exit code: 0 every variant
    landed, 1 a variant was queued, :data:`EXIT_NO_MODEL` no local model could serve (the run stops;
    nothing is written before a model is ready)."""
    pool = LocalLlmPool(settings, report=lambda line: logger.info("%s", line))
    outcomes: list[AreaOutcome] = []
    try:
        pool.activate()
        reference = SYNTAX_REFERENCE.read_text(encoding="utf-8")
        drafter = Drafter(package, catalog, pool, content, queue_dir, reference,
                          examples or package.tests_root / DIAGNOSTIC_FIXTURES)
        for area in areas:
            outcomes.append(draft_area(drafter, area))
            print_outcome(outcomes[-1])
    except LocalLlmUnavailable as error:
        print(f"ERROR: no local model can draft: {error}")
        return EXIT_NO_MODEL
    return 1 if any(outcome.queued for outcome in outcomes) else 0


__all__ = [
    "FEEDBACK_OUTPUT_LINES",
    "HEADER_TAG",
    "MAX_ROUNDS",
    "QUEUE_DIR",
    "SYSTEM_VERSION",
    "AreaOutcome",
    "Drafter",
    "Problem",
    "ProblemKind",
    "QueuedVariant",
    "area_header",
    "draft_area",
    "draft_package",
    "header_tags",
    "parse_draft",
    "print_outcome",
    "queue_text",
    "secret_literal_lines",
    "secret_sites",
    "with_profiles",
]
