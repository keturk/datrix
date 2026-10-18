"""Parity cases gate: every parity row, read on every registered target of its axis, compared
with its authored expectation.

A parity row (``cases/<area>.parity.yaml``; the row kind is
``datrix_testing.cases.parity``) names a fixture, a conformance probe, a facet of the probe's
return and the value every target must produce. This gate holds the one runner every row
shares: it discovers the targets from the installed entry points (a row whose probe
``LanguageConformanceProbes`` declares is read on every registered language, one
``PlatformConformanceProbes`` declares on every registered platform), builds each fixture
once per target (an example generated through the real pipeline, an enum the example
declares, or a web-security header-set fixture), resolves each target's own probes through
the kernel's accessors (fail closed: a target with no probe member, or one missing a method,
stops the run), narrows each probe's return with the facet the row selects
(``parity_observers.PROBE_READINGS``), and compares every reading with the expectation.

Two verdicts per row. The authored one decides: a target whose reading differs from the
expectation is a DIVERGENCE, so "every target agrees and every target is wrong" fails. The
mutual one informs: when the targets' readings differ from each other a DRIFT line names
every target's reading, which says which target moved when the expectation is the stale side.
A target whose capability declaration carries the ``capability_gaps`` surface a row names is
reported as a GAP -- counted and failing, never a pass. A target a probe does not apply to
(a platform that hosts no static site) is reported N/A and not compared.

A report line carries row ids, target names, readings and expectations only: no generated
file path and no exception text from a fixture or a probe (that is shown with ``--debug``),
which the no-disclosure canary self-test proves on every run.

Exit codes: 0 every row holds on every target; 1 a divergence, an unreadable row or a gap;
2 nothing could be compared -- the self-test failed, a row file or row is malformed, fewer
than two targets can read a row, a target's probes are missing or incomplete, a fixture
fails to build, a probe raised, or a probe returned another type than its Protocol's.

Repo-level validation script (per the datrix showcase boundary -- no pytest suite lives in
datrix).
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Protocol, TypeVar

from datrix_codegen_kernel.dgen.registry_adapter import spec_domain_id
from datrix_codegen_kernel.generation.discovery import get_language_plugin
from datrix_codegen_kernel.parity.conformance_probes import (
    DocumentationSurfaces,
    EnumClassifierRender,
    EventEnvelopeCensus,
    ResponseBodyWireField,
    RouteWireContract,
    conformance_probes_of_language_plugin,
    platform_conformance_probes,
)
from datrix_common.datrix_model.containers import Application
from datrix_common.errors.plugin import PluginValidationError
from datrix_common.paths import ServicePaths
from datrix_common.plugin.capability_resolution import declaration_for_language, declaration_for_provider
from datrix_common.testing.tag_vocabulary import documented_tags
from datrix_language.parser.tree_sitter_datrix.parser import TreeSitterParser
from datrix_language.registration import register_all
from datrix_testing.cases.compare import Observation, flow_text, verdict
from datrix_testing.cases.errors import SelectorError
from datrix_testing.cases.model import Case, CaseFileError
from datrix_testing.cases.parity import (
    AXIS_LANGUAGES,
    CAPABILITY_KEY,
    PARITY_STAGE,
    Axis,
    ParityRowError,
    corpus_problems,
    load_parity_rows,
    probe_axis,
    select_rows,
)

from datrix_scripts.generated_example import generate_example
from datrix_scripts.hook_modules import HookModuleError, load_suite_invocation
from datrix_scripts.paths import SHOWCASE_DIR, WORKSPACE_DIR
from datrix_scripts.registered_targets import (
    registered_language_names,
    registered_platform_names,
    self_test_gate_names_no_target,
)
from datrix_scripts.test_projects import get_project_by_name, list_projects
from parity_observers import (
    ENUM_KEY,
    PROBE_READINGS,
    ROUTE_WIRE_CONTRACTS,
    ProbeArgument,
    ProbeReadings,
    RenderedEnum,
    header_set_fixture,
    observer_specs,
)

logger = logging.getLogger(__name__)
_T = TypeVar("_T")

EXIT_OK: Final[int] = 0
EXIT_DIVERGENCE: Final[int] = 1
EXIT_CANNOT_COMPARE: Final[int] = 2

#: The committed parity rows.
CASES_DIR: Final[Path] = Path(__file__).resolve().parents[1] / "cases"
#: Where fixtures are generated: outside every package repository, one tree per (input, target).
FIXTURE_OUTPUT_ROOT: Final[Path] = WORKSPACE_DIR / ".tmp" / "parity-cases"
#: A cross-target comparison over fewer targets is vacuous.
MIN_TARGETS: Final[int] = 2
#: The DAL generator domain every enum-emitting language registers its enum sub-generator under.
_ENUM_DOMAIN: Final[str] = "enum"
#: The modules of this gate the no-target self-scan reads.
_GATE_MODULES: Final[tuple[str, ...]] = ("parity_cases.py", "parity_observers.py", "parity_cases_tool.py")


class CannotCompare(Exception):
    """Nothing can be compared for a row: a target's probes, a fixture or a probe call failed."""


@dataclass(frozen=True)
class Reading:
    """One target's reading of one row.

    Attributes:
        observation: The value the row's facet read, or ``None`` when it could not be read.
        failure: Why it could not be read (a reading's own words, never a path).
    """

    observation: Observation | None
    failure: str = ""

    def rendered(self) -> str:
        """The reading as a report writes it."""
        if self.observation is None:
            return f"<unreadable: {self.failure}>"
        return flow_text(self.observation.value)


@dataclass
class RowOutcome:
    """Every target's reading of one row.

    Attributes:
        row: The row.
        readings: The reading of every target the row's probe applies to.
        gaps: The targets carrying the row's capability gap, with the surface.
        not_applicable: The targets the probe does not apply to, with the reason.
    """

    row: Case
    readings: dict[str, Reading] = field(default_factory=dict)
    gaps: dict[str, str] = field(default_factory=dict)
    not_applicable: dict[str, str] = field(default_factory=dict)


class TargetAccess(Protocol):
    """How the gate reaches the targets: the registered ones in a real run, planted ones in the self-test."""

    def targets(self, axis: Axis) -> tuple[str, ...]:
        """The targets on *axis*."""
        ...

    def plugin_probes(self, target: str, axis: Axis) -> object:
        """*target*'s probes, through the kernel accessor (raises ``PluginValidationError``)."""
        ...

    def not_applicable(self, target: str, readings: ProbeReadings) -> str:
        """Why *readings*' probe does not apply to *target*; empty when it does."""
        ...

    def gap_surfaces(self, target: str, axis: Axis) -> frozenset[str]:
        """The ``capability_gaps`` surfaces *target* declares."""
        ...

    def probe_arguments(self, target: str, readings: ProbeReadings, row: Case) -> tuple[object, ...]:
        """The arguments *readings*' probe is called with for *row*'s fixture on *target*."""
        ...

    def wrap(self, target: str, readings: ProbeReadings, result: object) -> object:
        """*result* with whatever *target* declares about reading it."""
        ...


def _argument_key(readings: ProbeReadings, row: Case) -> tuple[str, ...]:
    return (row.input, *(str(row.selector[key]) for key in readings.argument_keys))


def _guarded(call: Callable[[], _T], what: str) -> _T:
    """*call*'s value; any failure becomes ``CannotCompare`` naming *what* and the error's type only."""
    try:
        return call()
    except CannotCompare:
        raise
    except Exception as error:
        logger.debug("%s failed: %s", what, error, exc_info=True)
        raise CannotCompare(f"{what} failed with {type(error).__name__} (rerun with --debug for its text)") from error


@dataclass
class ProbeCache:
    """Each probe is called once per (target, fixture, argument), however many rows read it."""

    results: dict[tuple[str, str, tuple[str, ...]], object] = field(default_factory=dict)
    probes: dict[str, object] = field(default_factory=dict)

    def _probes_of(self, access: TargetAccess, target: str, axis: Axis) -> object:
        if target not in self.probes:
            try:
                self.probes[target] = access.plugin_probes(target, axis)
            except PluginValidationError as error:
                raise CannotCompare(str(error)) from error
        return self.probes[target]

    def result(self, access: TargetAccess, target: str, readings: ProbeReadings, row: Case) -> object:
        """*readings*' probe called on *target* for *row*'s fixture.

        Raises:
            CannotCompare: The target's probes are missing or incomplete, its fixture cannot be
                built, or the probe raised; the message names the target, never the error's text.
        """
        key = (target, readings.probe, _argument_key(readings, row))
        if key in self.results:
            return self.results[key]
        probes = self._probes_of(access, target, probe_axis(readings.probe))
        arguments = _guarded(lambda: access.probe_arguments(target, readings, row), f"fixture {row.input!r} for {target!r}")
        result: object = _guarded(lambda: getattr(probes, readings.probe)(*arguments), f"probe {readings.probe!r} of {target!r}")
        self.results[key] = access.wrap(target, readings, result)
        return self.results[key]


def _capability_of(row: Case) -> str:
    value = row.selector[CAPABILITY_KEY] if CAPABILITY_KEY in row.selector else ""
    return value if isinstance(value, str) else ""


def _read_target(row: Case, readings: ProbeReadings, target: str, access: TargetAccess, cache: ProbeCache) -> Reading:
    reader = readings.facet_reading(row.selector)
    result = cache.result(access, target, readings, row)
    try:
        return Reading(reader.read(result, row.selector))
    except SelectorError as error:
        return Reading(None, str(error))
    except TypeError as error:
        # The probe broke its Protocol's return type: nothing about the row can be judged.
        raise CannotCompare(f"{target!r}: {error}") from error


def read_row(row: Case, access: TargetAccess, cache: ProbeCache) -> RowOutcome:
    """Read *row* on every target of its axis.

    Raises:
        CannotCompare: Fewer than two targets can read it, or a target's probe or fixture failed
            (a target carrying the row's capability gap is read too, and an unreadable one is a gap).
    """
    readings = PROBE_READINGS[row.observer]
    axis = probe_axis(row.observer)
    capability = _capability_of(row)
    outcome = RowOutcome(row)
    for target in access.targets(axis):
        reason = access.not_applicable(target, readings)
        if reason:
            outcome.not_applicable[target] = reason
            continue
        if capability and capability in access.gap_surfaces(target, axis):
            outcome.gaps[target] = capability
            try:
                outcome.readings[target] = _read_target(row, readings, target, access, cache)
            except CannotCompare as error:
                outcome.readings[target] = Reading(None, str(error))
            continue
        outcome.readings[target] = _read_target(row, readings, target, access, cache)
    if len(outcome.readings) < MIN_TARGETS:
        raise CannotCompare(
            f"row {row.id!r}: {len(outcome.readings)} target(s) on the {axis} axis can read it "
            f"({sorted(outcome.readings)}); a parity row compares at least {MIN_TARGETS}. Not applicable: "
            f"{dict(sorted(outcome.not_applicable.items()))}."
        )
    return outcome


def outcome_lines(outcome: RowOutcome) -> tuple[list[str], list[str]]:
    """``(failures, notes)`` for one row: DIVERGENCE / UNREADABLE / GAP lines, then DRIFT and N/A lines."""
    row = outcome.row
    expected = flow_text(row.expectation)
    failures: list[str] = []
    for target, reading in sorted(outcome.readings.items()):
        if target in outcome.gaps:
            failures.append(
                f"GAP {row.id} [{target}]: declares capability gap {outcome.gaps[target]}; read {reading.rendered()}, "
                f"expected {expected}"
            )
        elif reading.observation is None:
            failures.append(f"UNREADABLE {row.id} [{target}]: {reading.failure}; expected {expected}")
        else:
            judged = verdict(reading.observation, row.expectation)
            if not judged.matched:
                failures.append(
                    f"DIVERGENCE {row.id} [{target}]: read {judged.observed}, expected {judged.expected} ({judged.detail})"
                )
    notes: list[str] = []
    rendered = {target: reading.rendered() for target, reading in sorted(outcome.readings.items())}
    if len(set(rendered.values())) > 1:
        notes.append(f"DRIFT {row.id}: the targets disagree: " + "; ".join(f"{t}={v}" for t, v in rendered.items()))
    notes.extend(f"N/A {row.id} [{target}]: {reason}" for target, reason in sorted(outcome.not_applicable.items()))
    return failures, notes


@dataclass(frozen=True)
class GateReport:
    """The gate's verdict and every line it prints."""

    exit_code: int
    lines: tuple[str, ...]


def run_rows(rows: Sequence[Case], access: TargetAccess) -> GateReport:
    """Read and judge every row in *rows*."""
    cache = ProbeCache()
    try:
        outcomes = [read_row(row, access, cache) for row in rows]
    except CannotCompare as error:
        return GateReport(EXIT_CANNOT_COMPARE, (f"CANNOT COMPARE: {error}",))
    lines: list[str] = []
    failing_rows = 0
    readings = 0
    for outcome in outcomes:
        failures, notes = outcome_lines(outcome)
        lines.extend(failures)
        lines.extend(notes)
        failing_rows += bool(failures)
        readings += len(outcome.readings)
    lines.append(
        f"PARITY CASES: {len(outcomes)} row(s), {readings} reading(s): "
        f"{len(outcomes) - failing_rows} row(s) hold on every target, {failing_rows} fail."
    )
    return GateReport(EXIT_DIVERGENCE if failing_rows else EXIT_OK, tuple(lines))


# ---------------------------------------------------------------------------
# The registered targets
# ---------------------------------------------------------------------------


def _registered_domains(language: str) -> frozenset[str]:
    """The DAL generator domains *language*'s plugin registers a sub-generator under."""
    specs = get_language_plugin(language).generator.get_sub_generators()
    return frozenset(domain for domain in map(spec_domain_id, specs) if domain is not None)


def example_source(name: str) -> Path:
    """The ``system.dtrx`` of the registered example *name*.

    Raises:
        CannotCompare: *name* is not in the example registry.
    """
    project = get_project_by_name(name)
    if project is None:
        raise CannotCompare(f"input {name!r} is not an example of scripts/config/test-projects.json")
    return SHOWCASE_DIR / str(project["path"])


@dataclass
class LiveTargets:
    """The registered targets, read through their own probes on fixtures built for this run."""

    output_root: Path = FIXTURE_OUTPUT_ROOT
    _trees: dict[tuple[str, str], Path] = field(default_factory=dict)
    _applications: dict[str, Application] = field(default_factory=dict)

    def targets(self, axis: Axis) -> tuple[str, ...]:
        """The registered languages or platforms, from the installed entry points."""
        names = registered_language_names() if axis == AXIS_LANGUAGES else registered_platform_names()
        return tuple(sorted(names))

    def plugin_probes(self, target: str, axis: Axis) -> object:
        """*target*'s probes through the kernel accessor, which fails closed."""
        if axis == AXIS_LANGUAGES:
            return conformance_probes_of_language_plugin(target, get_language_plugin(target))
        return platform_conformance_probes(target)

    def not_applicable(self, target: str, readings: ProbeReadings) -> str:
        """A header row skips a platform hosting no static site; an enum row a language emitting no enum."""
        if readings.argument is ProbeArgument.HEADER_SET and declaration_for_provider(target).static_web_hosting is None:
            return "declares no static web hosting"
        if readings.argument is ProbeArgument.EXAMPLE_ENUM and _ENUM_DOMAIN not in _registered_domains(target):
            return f"registers no '{_ENUM_DOMAIN}' sub-generator"
        return ""

    def gap_surfaces(self, target: str, axis: Axis) -> frozenset[str]:
        """The surfaces of *target*'s declared ``capability_gaps``."""
        declaration = declaration_for_language(target) if axis == AXIS_LANGUAGES else declaration_for_provider(target)
        return frozenset(gap.surface for gap in declaration.capability_gaps)

    def probe_arguments(self, target: str, readings: ProbeReadings, row: Case) -> tuple[object, ...]:
        """The generated tree, the example's enum with its service paths, or the header set."""
        if readings.argument is ProbeArgument.HEADER_SET:
            return (header_set_fixture(row.input),)
        if readings.argument is ProbeArgument.EXAMPLE_ENUM:
            return self._enum_arguments(row.input, str(row.selector[ENUM_KEY]))
        if probe_axis(readings.probe) != AXIS_LANGUAGES:
            raise CannotCompare(f"{readings.probe!r} reads a generated tree, which is generated per language only")
        return (self._generated_tree(target, row.input),)

    def wrap(self, target: str, readings: ProbeReadings, result: object) -> object:
        """An enum render carries the target's declared idioms and unrecognized-value exception."""
        if readings.argument is not ProbeArgument.EXAMPLE_ENUM:
            return result
        if not isinstance(result, EnumClassifierRender):
            raise CannotCompare(f"{target!r}'s {readings.probe} returned a {type(result).__name__}")
        idioms = declaration_for_language(target).enum_classifier_idioms
        if idioms is None:
            raise CannotCompare(
                f"{target!r} declares no enum_classifier_idioms on its LanguageCapabilityDeclaration; its "
                f"rendered enum source cannot be read. Declare them on the language's capability declaration."
            )
        profile = get_language_plugin(target).transpiler_profile.language_profile
        return RenderedEnum(result, idioms, profile.errors.unrecognized_value_exception)

    def _generated_tree(self, language: str, name: str) -> Path:
        key = (name, language)
        if key not in self._trees:
            self._trees[key] = generate_example(language, example_source(name), self.output_root / name / language)
        return self._trees[key]

    def _enum_arguments(self, name: str, enum_name: str) -> tuple[object, ...]:
        if name not in self._applications:
            register_all()
            self._applications[name] = TreeSitterParser().parse_file(example_source(name))
        owners = [service for service in self._applications[name].services.values() if enum_name in service.enums]
        if len(owners) != 1:
            raise CannotCompare(
                f"example {name!r} declares enum {enum_name!r} in {len(owners)} service(s); exactly one is read"
            )
        return (owners[0].enums[enum_name], ServicePaths(owners[0].name))


# ---------------------------------------------------------------------------
# Tag selection
# ---------------------------------------------------------------------------


def select_parity_rows(rows: Sequence[Case], tags: Sequence[str]) -> tuple[Case, ...]:
    """The rows a ``-Tag`` run reads, under ``test.ps1``'s own ceiling (``MAX_TAGS_PER_RUN``).

    Raises:
        ParityRowError: The selection breaks a rule (see ``datrix_testing.cases.parity.select_rows``).
        HookModuleError: The shared ceiling cannot be loaded.
    """
    return select_rows(rows, tags, load_suite_invocation().MAX_TAGS_PER_RUN)


# ---------------------------------------------------------------------------
# Non-vacuity self-test
# ---------------------------------------------------------------------------

#: Fixture targets of the self-test -- never registered names.
_PLANTED_A: Final[str] = "self_test_lang_a"
_PLANTED_B: Final[str] = "self_test_lang_b"
#: Planted in every fixture path and probe error; the report must never carry it.
_CANARY: Final[str] = "CANARY-5e0c2b-never-reported"
_PLANTED_GAP: Final[str] = "domain:rest_api"


class _PlantedProbes:
    """A fixture language whose route probe returns a fixed route list, or raises."""

    def __init__(self, contracts: Sequence[RouteWireContract], *, fails: bool = False) -> None:
        self._contracts = tuple(contracts)
        self._fails = fails

    def response_body_wire_fields(self, generated_root: Path) -> tuple[ResponseBodyWireField, ...]:
        return ()

    def route_wire_contracts(self, generated_root: Path) -> tuple[RouteWireContract, ...]:
        if self._fails:
            raise RuntimeError(f"{generated_root}/{_CANARY}/routes.src cannot be read")
        return self._contracts

    def documentation_surfaces(self, generated_root: Path, files: Sequence[Path]) -> DocumentationSurfaces:
        return DocumentationSurfaces(frozenset(), frozenset())

    def render_enum_classifier(self, enum: object, paths: object) -> EnumClassifierRender:
        return EnumClassifierRender(())

    def event_envelopes(self, generated_root: Path) -> EventEnvelopeCensus:
        return EventEnvelopeCensus(published=(), consumed_keys={})


class _ProbesReturningList(_PlantedProbes):
    """A fixture language whose route probe breaks the Protocol's return type."""

    def route_wire_contracts(self, generated_root: Path) -> list[RouteWireContract]:  # the Protocol returns a tuple
        return list(super().route_wire_contracts(generated_root))


class _ProbesWithoutRoutes:
    """A fixture language whose probes lack the route method."""

    def response_body_wire_fields(self, generated_root: Path) -> tuple[ResponseBodyWireField, ...]:
        return ()


@dataclass(frozen=True)
class _PlantedPlugin:
    """A fixture language plugin carrying *probes* on the probe member the kernel accessor reads."""

    probes: object

    @property
    def conformance_probes(self) -> object:
        return self.probes


@dataclass
class _PlantedTargets:
    """Fixture languages read through the real accessor, the real probe call and the real readings."""

    plugins: Mapping[str, _PlantedPlugin]
    gaps: Mapping[str, frozenset[str]] = field(default_factory=dict)

    def targets(self, axis: Axis) -> tuple[str, ...]:
        return tuple(sorted(self.plugins)) if axis == AXIS_LANGUAGES else ()

    def plugin_probes(self, target: str, axis: Axis) -> object:
        return conformance_probes_of_language_plugin(target, self.plugins[target])

    def not_applicable(self, target: str, readings: ProbeReadings) -> str:
        return ""

    def gap_surfaces(self, target: str, axis: Axis) -> frozenset[str]:
        return self.gaps[target] if target in self.gaps else frozenset()

    def probe_arguments(self, target: str, readings: ProbeReadings, row: Case) -> tuple[object, ...]:
        return (FIXTURE_OUTPUT_ROOT / _CANARY / target,)

    def wrap(self, target: str, readings: ProbeReadings, result: object) -> object:
        return result


def _contract(status: int = 200) -> RouteWireContract:
    return RouteWireContract(
        "get", "/api/v1/books", status, "page", "application/json", Path(_CANARY) / "routes.src",
        frozenset({"skip", "limit"}),
    )


def _planted_row(row_id: str = "self-test.list-books", path: str = "/api/v1/books", capability: str = "") -> Case:
    selector: dict[str, str] = {"facet": "route", "verb": "get", "path": path}
    if capability:
        selector[CAPABILITY_KEY] = capability
    return Case.model_validate(
        {
            "id": row_id,
            "tags": ["parity", "rest-api"],
            "input": "self-test-example",
            "stage": PARITY_STAGE,
            "observer": ROUTE_WIRE_CONTRACTS,
            "selector": selector,
            "expectation": {"status": "200", "body": "page", "media-type": "application/json"},
            "reason": "The self-test's planted route.",
        }
    )


def _planted(status_a: int, status_b: int, gaps: Mapping[str, frozenset[str]] | None = None) -> _PlantedTargets:
    return _PlantedTargets(
        {
            _PLANTED_A: _PlantedPlugin(_PlantedProbes([_contract(status_a)])),
            _PLANTED_B: _PlantedPlugin(_PlantedProbes([_contract(status_b)])),
        },
        gaps or {},
    )


def _kinds(report: GateReport) -> list[str]:
    return [line.split(" ", 1)[0] for line in report.lines[:-1]]


def _self_test_verdicts() -> list[str]:
    """Two targets give two readings per row; one divergent target is one failure; agreed-and-wrong fails."""
    problems: list[str] = []
    agreed = run_rows([_planted_row()], _planted(200, 200))
    outcome = read_row(_planted_row(), _planted(200, 200), ProbeCache())
    if agreed.exit_code != EXIT_OK or _kinds(agreed) or len(outcome.readings) != MIN_TARGETS:
        problems.append(f"two agreeing, correct targets did not pass with two readings: {agreed.lines}")
    divergent = run_rows([_planted_row()], _planted(200, 201))
    failures = [line for line in divergent.lines if line.startswith("DIVERGENCE")]
    if divergent.exit_code != EXIT_DIVERGENCE or len(failures) != 1 or _PLANTED_B not in failures[0]:
        problems.append(f"one divergent target did not produce exactly one failure naming it: {divergent.lines}")
    if not any(line.startswith("DRIFT") for line in divergent.lines):
        problems.append("two disagreeing targets produced no DRIFT line")
    wrong = run_rows([_planted_row()], _planted(201, 201))
    if wrong.exit_code != EXIT_DIVERGENCE or _kinds(wrong) != ["DIVERGENCE", "DIVERGENCE"]:
        problems.append(f"two targets agreeing on a wrong value did not both fail (and drift nothing): {wrong.lines}")
    return problems


def _self_test_refusals() -> list[str]:
    """Unreadable rows fail, a gap fails as a gap, a missing probe method and a lone target stop the run."""
    problems: list[str] = []
    absent = run_rows([_planted_row(path="/api/v1/authors")], _planted(200, 200))
    if absent.exit_code != EXIT_DIVERGENCE or _kinds(absent) != ["UNREADABLE", "UNREADABLE"]:
        problems.append(f"a row selecting an unregistered route was not unreadable on both targets: {absent.lines}")
    gapped = run_rows([_planted_row(capability=_PLANTED_GAP)], _planted(200, 200, {_PLANTED_A: frozenset({_PLANTED_GAP})}))
    if gapped.exit_code != EXIT_DIVERGENCE or _kinds(gapped) != ["GAP"] or _PLANTED_A not in gapped.lines[0]:
        problems.append(f"a target carrying the row's capability gap was not reported as a failing gap: {gapped.lines}")
    lacking = _PlantedTargets(
        {_PLANTED_A: _PlantedPlugin(_ProbesWithoutRoutes()), _PLANTED_B: _PlantedPlugin(_PlantedProbes([_contract()]))}
    )
    missing = run_rows([_planted_row()], lacking)
    named = missing.lines[0] if missing.lines else ""
    if missing.exit_code != EXIT_CANNOT_COMPARE or _PLANTED_A not in named or ROUTE_WIRE_CONTRACTS not in named:
        problems.append(f"a target lacking the row's probe method did not stop the run naming it: {missing.lines}")
    alone = run_rows([_planted_row()], _PlantedTargets({_PLANTED_A: _PlantedPlugin(_PlantedProbes([_contract()]))}))
    if alone.exit_code != EXIT_CANNOT_COMPARE:
        problems.append(f"a row read on one target was not refused: {alone.lines}")
    mistyped = run_rows(
        [_planted_row()],
        _PlantedTargets(
            {
                _PLANTED_A: _PlantedPlugin(_ProbesReturningList([_contract()])),
                _PLANTED_B: _PlantedPlugin(_PlantedProbes([_contract()])),
            }
        ),
    )
    named = mistyped.lines[0] if mistyped.lines else ""
    if mistyped.exit_code != EXIT_CANNOT_COMPARE or _PLANTED_A not in named:
        problems.append(f"a probe breaking its return type did not stop the run naming the target: {mistyped.lines}")
    return problems


def _self_test_no_disclosure() -> list[str]:
    """A fixture path and a probe's error text never reach the report."""
    failing = _PlantedTargets(
        {
            _PLANTED_A: _PlantedPlugin(_PlantedProbes([], fails=True)),
            _PLANTED_B: _PlantedPlugin(_PlantedProbes([_contract()])),
        }
    )
    reports = (run_rows([_planted_row()], _planted(200, 201)), run_rows([_planted_row()], failing))
    if reports[1].exit_code != EXIT_CANNOT_COMPARE:
        return [f"a probe that raised did not stop the run: {reports[1].lines}"]
    if any(_CANARY in line for report in reports for line in report.lines):
        return ["a report carried a planted fixture path or a probe's error text"]
    return []


def _self_test_tag_selection() -> list[str]:
    """The tag selection obeys test.ps1 -Tag's ceiling and its must-exist rule."""
    rows = [_planted_row(), _planted_row("self-test.other").model_copy(update={"tags": ["parity", "pubsub"]})]
    problems: list[str] = []
    for tags in (["rest-api", "pubsub", "parity", "cors"], ["no-such-tag"]):
        try:
            select_parity_rows(rows, tags)
        except ParityRowError:
            continue
        problems.append(f"the tag selection {tags} was not refused")
    if [row.id for row in select_parity_rows(rows, ["rest-api"])] != ["self-test.list-books"]:
        problems.append("a one-tag selection did not keep exactly the row carrying the tag")
    return problems


def run_self_test() -> list[str]:
    """Prove the gate names no target, judges both verdicts, refuses to pass vacuously and discloses nothing.

    Returns:
        Failure descriptions; empty means the gate can be trusted.
    """
    lib = Path(__file__).resolve().parent
    problems = [problem for module in _GATE_MODULES for problem in self_test_gate_names_no_target(str(lib / module))]
    if problems:
        return problems
    for check in (_self_test_verdicts, _self_test_refusals, _self_test_no_disclosure, _self_test_tag_selection):
        problems.extend(f"self-test: {problem}" for problem in check())
    return problems


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def committed_rows() -> tuple[Case, ...]:
    """Every committed parity row, after the row checks.

    Raises:
        CaseFileError: A file does not load, or a row fails the parity checks (every problem listed).
    """
    rows = load_parity_rows(CASES_DIR)
    problems = corpus_problems(rows, observer_specs(list_projects()), documented_tags())
    if problems:
        raise CaseFileError("parity rows fail the checks:\n" + "\n".join(f"  {problem}" for problem in problems))
    return rows


def split_tags(raw: str) -> list[str]:
    """The tags of a comma-separated ``-Tag`` value."""
    return [tag.strip() for tag in raw.split(",") if tag.strip()]


def main(argv: Sequence[str] | None = None) -> int:
    """Run the self-test, then the selected rows (every row with no ``--tag``)."""
    parser = argparse.ArgumentParser(description="Read every parity row on every registered target of its axis.")
    parser.add_argument("--tag", default="", help="Comma-separated feature tags (at most the test.ps1 ceiling)")
    parser.add_argument("--self-test", action="store_true", help="Run only the self-test")
    parser.add_argument("--debug", action="store_true", help="Debug logging, including fixture and probe error text")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO, format="%(levelname)s: %(message)s")
    problems = run_self_test()
    if problems:
        print("Parity cases self-test FAILED:", *problems, sep="\n  ")
        return EXIT_CANNOT_COMPARE
    print("Parity cases self-test passed.")
    if args.self_test:
        return EXIT_OK
    try:
        rows = committed_rows()
        if args.tag:
            rows = select_parity_rows(rows, split_tags(args.tag))
    except (CaseFileError, ParityRowError, HookModuleError) as error:
        print(f"CANNOT COMPARE: {error}")
        return EXIT_CANNOT_COMPARE
    report = run_rows(rows, LiveTargets())
    print(*report.lines, sep="\n")
    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())
