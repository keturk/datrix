"""Diagnostic area fixtures authored from the diagnostic catalog: needs, area plan, scaffold, verification.

Drafting an area with a local model, verified by these rules round by round, is
:mod:`datrix_scripts.dev.fixture_author.drafting`.

What a package's diagnostics fixtures must prove is written down in the catalog: one provoking
source per catalog variant. This module reads it and checks a written area against it; it names no
code, variant, family or language.

* **Needs.** A package's needs are the catalog variants its fixtures provoke: the target-check
  variants for the package whose session registers the target checks, every other variant for the
  rest, less the variants the package proves by a code test instead (the ``PROVEN_BY_CODE_TEST``
  mapping one test module under its ``tests/`` assigns).
* **Area plan.** Each needed variant goes to the area of its code's family, lowercased. A variant
  whose code ends analysis goes to ``<family>-halt`` (anything after it would never be reported); an
  area holding a code read off seed documents is a seeded project directory
  ``<area>-seeded/system.dtrx`` with its own configuration and ``seed/``: the suffix keeps it from
  ever being the diagnostics root's own ``seed/``, which every area beside it reads as its seed
  documents. Target-check variants go to one area, ``targets``, declaring ``// @analysis targets``:
  the area names no language, and is one input per registered backend language.
* **Scaffold.** A project root (the package's ``tests/fixtures/diagnostics/``, or a seeded area's
  directory) holds the system configuration and the datasource templates, copied from the fixture
  corpus when absent: a ``.dcfg`` import never leaves its project root.
* **Verification.** An area is read exactly as its whole-analysis case reads it: the package's
  case session, the area's inputs from its diagnostics fixtures, and the ``diagnostic-codes``
  observer of the ``analyze`` stage over variants. The reported set is compared with the annotated
  set; what is reported and not annotated is a cascade, what is annotated and not reported is not
  provoked. Every input of an area is analyzed -- each profile it lists and, for the target-check
  area, each language -- so a variant reported under one language only is not provoked under the
  others.
"""

from __future__ import annotations

import ast
import importlib
import logging
import shutil
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from datrix_common.constants import DATRIX_FILE_EXTENSION
from datrix_language.parser.dcfg_parser import parse_dcfg
from datrix_semantic.diagnostics.catalog import DiagnosticCatalog
from datrix_semantic.diagnostics.security_families import code_family
from datrix_testing.cases.annotation_reading import AnnotationError
from datrix_testing.cases.annotations import (
    AREA_STEM,
    CONFIG_TEMPLATES,
    DIAGNOSTIC_CONFIGS,
    DIAGNOSTIC_FIXTURES,
    DIAGNOSTIC_INPUT_PREFIX,
    PROJECT_FIXTURE_SOURCE,
    AnnotationCorpus,
    collect_annotations,
    diagnostic_fixture_of,
)
from datrix_testing.cases.errors import RegistryError, SelectorError
from datrix_testing.cases.model import Case
from datrix_testing.cases.observers import DIAGNOSTIC_CODES, UNLOCATED, VARIANT_SEPARATOR, location_file
from datrix_testing.cases.package import INPUTS_MODULE, TESTS_DIRECTORY, PackageCases
from datrix_testing.cases.runner import observe_case
from datrix_testing.cases.stages import AnalysisStageResult, StageCache, StageError
from datrix_testing.corpus import CORPUS_ROOT

from datrix_scripts.local_llm import LocalLlmSettings
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.skill.common import AssistError, ContentFilter

logger = logging.getLogger(__name__)

#: The mapping a package's census test assigns: variant to the code test proving it.
PROVEN_BY_CODE_NAME: Final[str] = "PROVEN_BY_CODE_TEST"
#: The suffix of the area holding a family's codes that end analysis.
HALT_SUFFIX: Final[str] = "-halt"
#: The suffix of a seeded area's directory: never the root's seed-documents directory itself.
SEEDED_SUFFIX: Final[str] = "-seeded"
#: The area holding every target-check variant: one input per registered backend language.
TARGETS_AREA: Final[str] = "targets"
#: The configuration kind a project's system ``.dcfg`` declares.
SYSTEM_CONFIG_KIND: Final[str] = "system"
#: The scaffold every project root holds, under its configuration directory, as the corpus commits it.
SYSTEM_CONFIG: Final[Path] = Path(DIAGNOSTIC_CONFIGS) / "system.dcfg"
DATASOURCE_TEMPLATES: Final[Path] = Path(DIAGNOSTIC_CONFIGS) / CONFIG_TEMPLATES / "datasources.dcfg"
SCAFFOLD_FILES: Final[tuple[Path, ...]] = (SYSTEM_CONFIG, DATASOURCE_TEMPLATES)
#: The separator of an area input's profile (``diagnostics/<area>@<profile>``).
_PROFILE_SEPARATOR: Final[str] = "@"
_PYTHON_SUFFIX: Final[str] = ".py"
_TEST_MODULE_GLOB: Final[str] = "test_*.py"


class FixtureAuthorError(Exception):
    """The package's state does not let the tool act; the message says what and how to fix it."""


# --------------------------------------------------------------------------- needs


def catalog_variants(catalog: DiagnosticCatalog, *, target_checks: bool) -> frozenset[str]:
    """The ``<CODE>.<variant>`` names of *catalog*: its target-check variants when *target_checks*,
    else every variant analysis reports."""
    return frozenset(
        f"{code}{VARIANT_SEPARATOR}{name}"
        for code, entry in catalog.codes.items()
        for name, variant in entry.variants.items()
        if variant.target_check is target_checks
    )


def package_needs(
    catalog: DiagnosticCatalog, *, owns_target_checks: bool, proven_by_code: Iterable[str]
) -> tuple[str, ...]:
    """The variants a package's diagnostics fixtures must provoke, sorted: those of its kind
    (:func:`catalog_variants`) less those it proves by a code test."""
    return tuple(sorted(catalog_variants(catalog, target_checks=owns_target_checks) - frozenset(proven_by_code)))


def _assigns_at_module_level(path: Path, name: str) -> bool:
    """Whether the Python module at *path* assigns *name* at module level (read off its syntax tree)."""
    text = path.read_text(encoding="utf-8")
    if name not in text:
        return False
    for node in ast.parse(text, filename=str(path)).body:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        if any(isinstance(target, ast.Name) and target.id == name for target in targets):
            return True
    return False


def proven_by_code_module(root: Path) -> str:
    """The dotted name of the one test module under *root*'s ``tests/`` (its fixtures excluded)
    assigning :data:`PROVEN_BY_CODE_NAME`.

    Raises:
        FixtureAuthorError: No module or several assign it.
    """
    tests_root = root / TESTS_DIRECTORY
    fixtures = tests_root / DIAGNOSTIC_FIXTURES.parts[0]
    found = [
        path
        for path in sorted(tests_root.rglob(_TEST_MODULE_GLOB))
        if not path.is_relative_to(fixtures) and _assigns_at_module_level(path, PROVEN_BY_CODE_NAME)
    ]
    if len(found) != 1:
        raise FixtureAuthorError(
            f"{root.name}: {len(found)} test module(s) under {tests_root} assign {PROVEN_BY_CODE_NAME} "
            f"({[str(path) for path in found]}); expected exactly one -- the census test of the package's "
            f"diagnostics fixtures, mapping each variant no fixture can provoke to the code test proving it. "
            f"Fix: name the mapping {PROVEN_BY_CODE_NAME} in that one module."
        )
    return ".".join(found[0].relative_to(root).with_suffix("").parts)


def proven_by_code(root: Path) -> frozenset[str]:
    """The variants the package at *root* proves by a code test, read off its census module.

    The package's session must be prepared first (``prepare_package_session``), so its tests import.

    Raises:
        FixtureAuthorError: :func:`proven_by_code_module` refuses, or the mapping is no mapping of
            variant names.
    """
    module_name = proven_by_code_module(root)
    mapping = getattr(importlib.import_module(module_name), PROVEN_BY_CODE_NAME)
    if not isinstance(mapping, Mapping) or not all(isinstance(key, str) for key in mapping):
        raise FixtureAuthorError(
            f"{module_name}.{PROVEN_BY_CODE_NAME} is a {type(mapping).__name__}; expected a mapping of "
            f"'<CODE>.<variant>' to the code test proving it."
        )
    return frozenset(mapping)


# --------------------------------------------------------------------------- area plan


@dataclass(frozen=True)
class AreaPlan:
    """One area project the tool writes.

    Attributes:
        name: The area, :data:`AREA_STEM`.
        variants: The variants it provokes, sorted.
        seeded: It is a project directory ``<name>/`` (``<family>-seeded``) with its own configuration
            and ``seed/``.
        target_checks: Its header declares ``// @analysis targets``: it is analyzed and then checked
            against its targets, once for every registered backend language.
    """

    name: str
    variants: tuple[str, ...]
    seeded: bool = False
    target_checks: bool = False

    def root(self, diagnostics: Path) -> Path:
        """The project root its configuration lives under: its own directory when seeded."""
        return diagnostics / self.name if self.seeded else diagnostics

    def entry(self, diagnostics: Path) -> Path:
        """The ``.dtrx`` it is analyzed from."""
        if self.seeded:
            return diagnostics / self.name / PROJECT_FIXTURE_SOURCE
        return diagnostics / f"{self.name}{DATRIX_FILE_EXTENSION}"


def _require_area_name(name: str) -> str:
    if AREA_STEM.fullmatch(name) is None:
        raise FixtureAuthorError(
            f"area {name!r} is not an area name ({AREA_STEM.pattern}); the area name is derived from a "
            f"catalog code's family, so that family breaks the form."
        )
    return name


def variant_code(variant: str) -> str:
    """The code of ``<CODE>.<variant>``."""
    return variant.partition(VARIANT_SEPARATOR)[0]


def analysis_area_name(code: str, *, halting: frozenset[str]) -> str:
    """The area of an analysis variant of *code*: its family lowercased, ``<family>-halt`` when *code*
    ends analysis."""
    family = code_family(code).lower()
    return _require_area_name(f"{family}{HALT_SUFFIX}" if code in halting else family)


def analysis_areas(
    needs: Iterable[str], *, halting: frozenset[str], seed_document_codes: frozenset[str]
) -> tuple[AreaPlan, ...]:
    """The analysis areas of *needs*, by name: an area holding a code read off seed documents is
    seeded, its directory ``<area>-seeded``."""
    grouped: dict[str, list[str]] = {}
    for variant in needs:
        grouped.setdefault(analysis_area_name(variant_code(variant), halting=halting), []).append(variant)
    areas: list[AreaPlan] = []
    for name, variants in grouped.items():
        seeded = any(variant_code(variant) in seed_document_codes for variant in variants)
        area_name = _require_area_name(f"{name}{SEEDED_SUFFIX}") if seeded else name
        areas.append(AreaPlan(area_name, tuple(sorted(variants)), seeded=seeded))
    return tuple(sorted(areas, key=lambda area: area.name))


def target_check_areas(needs: Iterable[str]) -> tuple[AreaPlan, ...]:
    """The one area :data:`TARGETS_AREA` holding every target-check variant of *needs*, none when
    *needs* is empty. It names no language: the annotation reader makes it one input per registered
    backend language, and refuses it when none is registered."""
    variants = tuple(sorted(needs))
    if not variants:
        return ()
    return (AreaPlan(_require_area_name(TARGETS_AREA), variants, target_checks=True),)


def plan_areas(
    needs: Iterable[str],
    *,
    owns_target_checks: bool,
    halting: frozenset[str],
    seed_document_codes: frozenset[str],
) -> tuple[AreaPlan, ...]:
    """The areas a package's *needs* go to (:func:`target_check_areas` or :func:`analysis_areas`)."""
    if owns_target_checks:
        return target_check_areas(needs)
    return analysis_areas(needs, halting=halting, seed_document_codes=seed_document_codes)


def select_area(areas: tuple[AreaPlan, ...], name: str) -> AreaPlan:
    """The planned area *name*.

    Raises:
        FixtureAuthorError: The plan holds no such area.
    """
    for area in areas:
        if area.name == name:
            return area
    raise FixtureAuthorError(f"no planned area is named {name!r}; the planned areas are {[a.name for a in areas]}.")


# --------------------------------------------------------------------------- scaffold


def ensure_scaffold(project_root: Path, corpus_root: Path = CORPUS_ROOT) -> list[Path]:
    """Copy each :data:`SCAFFOLD_FILES` file the corpus at *corpus_root* commits into *project_root*
    where it is absent; return the files written. A present file is never overwritten.

    Raises:
        FixtureAuthorError: The corpus lacks a scaffold file.
    """
    written: list[Path] = []
    for relative in SCAFFOLD_FILES:
        source = corpus_root / relative
        if not source.is_file():
            raise FixtureAuthorError(
                f"the fixture corpus commits no {relative.as_posix()} at {source}; the scaffold of every "
                f"diagnostics project root is copied from it."
            )
        target = project_root / relative
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        logger.debug("scaffold_written path=%s", target)
        written.append(target)
    return written


def system_owner(project_root: Path) -> str:
    """The system the scaffold's system configuration declares (``config system <owner>``): the
    name an area's ``system`` declaration must carry.

    Raises:
        FixtureAuthorError: The file is absent or declares another configuration kind.
    """
    path = project_root / SYSTEM_CONFIG
    if not path.is_file():
        raise FixtureAuthorError(f"{path} is absent; write the scaffold first (-Scaffold).")
    declaration = parse_dcfg(path.read_text(encoding="utf-8"), str(path))
    if declaration.kind != SYSTEM_CONFIG_KIND:
        raise FixtureAuthorError(
            f"{path} declares a '{declaration.kind}' configuration; the scaffold's system configuration "
            f"declares 'config {SYSTEM_CONFIG_KIND} <owner>'."
        )
    return declaration.owner


# --------------------------------------------------------------------------- verification


@dataclass(frozen=True)
class LocatedDiagnostic:
    """One diagnostic the analysis reported, where it fired.

    Attributes:
        variant: ``<CODE>.<variant>``.
        file: Its file relative to the project directory (posix), as a case writes it; ``?`` when
            its location names no file, ``UNLOCATED`` when it has no location.
        line: Its 1-based line, or ``None`` when unlocated.
        message: Its rendered message.
    """

    variant: str
    file: str
    line: int | None
    message: str


@dataclass(frozen=True)
class AreaVerdict:
    """One area input's whole analysis compared with its annotations.

    Attributes:
        input_name: ``diagnostics/<area>``, with ``+<language>`` when it runs its target checks and
            ``@<profile>`` when its area lists several profiles.
        reported: The variants the analysis reported.
        annotated: The variants its ``@expect`` annotations name.
        output: The analyzer's output, one reported diagnostic per line.
        refused: Why the area could not be analyzed or its annotations not read; empty when it was.
        located: Each reported diagnostic with the file and line it fired at.
    """

    input_name: str
    reported: frozenset[str] = frozenset()
    annotated: frozenset[str] = frozenset()
    output: tuple[str, ...] = ()
    refused: str = ""
    located: tuple[LocatedDiagnostic, ...] = ()

    @property
    def profile(self) -> str | None:
        """The profile the input runs, when its area lists several (``@profiles``)."""
        _, separator, profile = self.input_name.partition(_PROFILE_SEPARATOR)
        return profile if separator else None

    @property
    def cascade(self) -> tuple[str, ...]:
        """Reported and not annotated."""
        return tuple(sorted(self.reported - self.annotated))

    @property
    def not_provoked(self) -> tuple[str, ...]:
        """Annotated and not reported."""
        return tuple(sorted(self.annotated - self.reported))

    @property
    def passed(self) -> bool:
        """Analyzed, and reports exactly what it annotates."""
        return not self.refused and self.reported == self.annotated


def area_input_names(input_names: Iterable[str], area: str) -> list[str]:
    """The inputs of *input_names* read off *area*, sorted: every language and profile it runs."""
    return sorted(name for name in input_names if diagnostic_fixture_of(name) == area)


def not_provoked_inputs(verdicts: Iterable[AreaVerdict]) -> dict[str, tuple[str, ...]]:
    """Each annotated variant some analyzed input of its area does not report, with those inputs:
    a variant must fire under every language and profile its area runs."""
    missing: dict[str, list[str]] = {}
    for verdict in verdicts:
        if verdict.refused:
            continue
        for variant in verdict.not_provoked:
            missing.setdefault(variant, []).append(verdict.input_name)
    return {variant: tuple(sorted(names)) for variant, names in sorted(missing.items())}


def _whole_analysis_case(corpus: AnnotationCorpus, input_name: str) -> Case:
    for found in corpus.cases:
        if found.case.input == input_name and found.case.observer == DIAGNOSTIC_CODES:
            return found.case
    raise FixtureAuthorError(f"{input_name} yields no whole-analysis case; its annotations name no '@expect'.")


def _verdict(package: PackageCases, cache: StageCache, corpus: AnnotationCorpus, input_name: str) -> AreaVerdict:
    case = _whole_analysis_case(corpus, input_name)
    annotated = frozenset(str(item) for item in case.expectation or ())
    try:
        observation = observe_case(package.registry, cache, case)
    except (StageError, SelectorError, RegistryError) as error:
        return AreaVerdict(input_name, annotated=annotated, refused=f"{type(error).__name__}: {error}")
    reported = frozenset(observation.value) if isinstance(observation.value, frozenset) else frozenset()
    return AreaVerdict(input_name, reported, annotated, observation.context, located=_located(cache, case))


def _located(cache: StageCache, case: Case) -> tuple[LocatedDiagnostic, ...]:
    """Each diagnostic of the analysis *case* observed, where it fired (the stage result is cached,
    so this runs no second analysis)."""
    result = cache.result(case.input, case.stage)
    if not isinstance(result, AnalysisStageResult):
        return ()
    project_dir = result.project.path.parent
    return tuple(
        LocatedDiagnostic(
            f"{diagnostic.code}{VARIANT_SEPARATOR}{diagnostic.variant}",
            location_file(diagnostic.location, project_dir) if diagnostic.location is not None else UNLOCATED,
            diagnostic.location.line if diagnostic.location is not None else None,
            diagnostic.message,
        )
        for diagnostic in result.result.diagnostics
    )


def verify_areas(package: PackageCases, areas: Iterable[str]) -> list[AreaVerdict]:
    """Each input of each area in *areas* analyzed as its whole-analysis case reads it, compared with
    its annotations. The diagnostics fixtures are collected once; when collection refuses them, every
    area carries that refusal.

    Raises:
        FixtureAuthorError: An area has no fixture under the package's diagnostics directory.
    """
    names = list(areas)
    try:
        corpus = collect_annotations(package.tests_root, package.inputs)
    except AnnotationError as error:
        return [AreaVerdict(f"{DIAGNOSTIC_INPUT_PREFIX}{area}", refused=str(error)) for area in names]
    cache = StageCache(package.registry, package.inputs.extended(projects=corpus.projects, sources={}))
    verdicts: list[AreaVerdict] = []
    for area in names:
        inputs = area_input_names(corpus.areas, area)
        if not inputs:
            raise FixtureAuthorError(
                f"{package.name} has no area project '{area}' under {package.tests_root / DIAGNOSTIC_FIXTURES}."
            )
        verdicts.extend(_verdict(package, cache, corpus, name) for name in inputs)
    return verdicts


def has_case_inputs(root: Path) -> bool:
    """Whether the package at *root* carries a case session (``tests/case_inputs.py``)."""
    return (root / TESTS_DIRECTORY / f"{INPUTS_MODULE}{_PYTHON_SUFFIX}").is_file()


# --------------------------------------------------------------------------- the run


@dataclass(frozen=True)
class DiagnosticsSession:
    """One package's diagnostics fixtures as the catalog asks for them.

    Attributes:
        package: Its case session.
        owns_target_checks: Its session registers the target checks.
        proven_by_code: The variants it proves by a code test.
        needs: The variants its fixtures must provoke.
        areas: Where they go.
    """

    package: PackageCases
    owns_target_checks: bool
    proven_by_code: frozenset[str]
    needs: tuple[str, ...]
    areas: tuple[AreaPlan, ...]

    @property
    def diagnostics(self) -> Path:
        """The package's diagnostics fixtures directory."""
        return self.package.tests_root / DIAGNOSTIC_FIXTURES


def load_diagnostics_session(root: Path) -> DiagnosticsSession:
    """Load the package at *root* as its pytest session does, then read its needs and plan its areas.

    Raises:
        FixtureAuthorError: Its proven-by-code mapping cannot be read (:func:`proven_by_code`), or
            an area cannot be planned.
    """
    from datrix_semantic.analyzer import analysis_halting_codes
    from datrix_semantic.diagnostics.report import CATALOG
    from datrix_semantic.validators.error_codes import SEED_DOCUMENT_CODES
    from datrix_testing.cases.package import load_package
    from datrix_testing.cases.stages import target_checks_registered

    package = load_package(root)
    owns_target_checks = target_checks_registered()
    proven = proven_by_code(package.root)
    needs = package_needs(CATALOG, owns_target_checks=owns_target_checks, proven_by_code=proven)
    areas = plan_areas(
        needs,
        owns_target_checks=owns_target_checks,
        halting=analysis_halting_codes(),
        seed_document_codes=SEED_DOCUMENT_CODES,
    )
    return DiagnosticsSession(package, owns_target_checks, proven, needs, areas)


def print_plan(session: DiagnosticsSession, areas: tuple[AreaPlan, ...]) -> None:
    """Print the needs and *areas*, with each area's variants when one area is printed."""
    kind = "target-check" if session.owns_target_checks else "analysis"
    print(
        f"{session.package.name}: {len(session.needs)} {kind} variant(s) needed, "
        f"{len(session.proven_by_code)} proven by code; {len(session.areas)} area(s) planned"
    )
    for area in areas:
        traits = ["seeded"] if area.seeded else []
        if area.target_checks:
            traits.append("target checks, one input per registered language")
        on_disk = "on disk" if area.entry(session.diagnostics).exists() else "absent"
        suffix = f" [{', '.join(traits)}]" if traits else ""
        print(f"  {area.name}{suffix}: {len(area.variants)} variant(s), {on_disk}")
        if len(areas) == 1:
            print("\n".join(f"    {variant}" for variant in area.variants))


def print_verdict(verdict: AreaVerdict, shown: int) -> None:
    """Print one area input's verdict, and the analyzer's output (at most *shown* lines) when it failed."""
    if verdict.passed:
        print(f"[ OK ] {verdict.input_name}: {len(verdict.reported)} variant(s) reported, each annotated")
        return
    print(f"[FAIL] {verdict.input_name}")
    if verdict.refused:
        print(f"  refused: {verdict.refused}")
        return
    print(f"  cascade (reported, not annotated): {list(verdict.cascade)}")
    print(f"  not provoked (annotated, not reported): {list(verdict.not_provoked)}")
    print("\n".join(f"    {line}" for line in verdict.output[:shown]))


def _scaffold(session: DiagnosticsSession, areas: tuple[AreaPlan, ...]) -> int:
    roots = sorted({session.diagnostics, *(area.root(session.diagnostics) for area in areas)})
    for root in roots:
        written = ensure_scaffold(root)
        status = ", ".join(path.relative_to(root).as_posix() for path in written) or "present"
        print(f"{root}: {status}")
    return 0


def _verify(session: DiagnosticsSession, areas: tuple[AreaPlan, ...], shown: int) -> int:
    present = [area.name for area in areas if area.entry(session.diagnostics).exists()]
    if not present:
        raise FixtureAuthorError(
            f"none of the {len(areas)} planned area(s) is on disk under {session.diagnostics}; "
            f"there is nothing to verify."
        )
    verdicts = verify_areas(session.package, present)
    for verdict in verdicts:
        print_verdict(verdict, shown)
    for variant, inputs in not_provoked_inputs(verdicts).items():
        print(f"[MISS] {variant}: not provoked under {', '.join(inputs)}")
    failed = sum(not verdict.passed for verdict in verdicts)
    print(f"{len(verdicts) - failed} of {len(verdicts)} area input(s) report exactly what they annotate")
    return 1 if failed else 0


#: The analyzer output lines shown under a failed area.
OUTPUT_SHOWN: Final[int] = 20
#: The action that drafts each absent area with a local model: the run's default.
DRAFT_ACTION: Final[str] = "draft"


def _absent_areas(session: DiagnosticsSession, areas: tuple[AreaPlan, ...], *, named: bool) -> list[AreaPlan]:
    """The areas of *areas* not on disk: an area is never drafted over. One the run *named* is
    refused when present; the rest present are passed over, each said so."""
    absent = [area for area in areas if not area.entry(session.diagnostics).exists()]
    for area in areas:
        if area not in absent:
            if named:
                raise FixtureAuthorError(
                    f"area {area.name} is on disk at {area.entry(session.diagnostics)}; the tool never drafts over an "
                    f"area. Check it with -Verify, or finish it by hand."
                )
            print(f"[SKIP] {area.name}: on disk at {area.entry(session.diagnostics)}")
    return absent


def _draft(session: DiagnosticsSession, areas: tuple[AreaPlan, ...], settings: LocalLlmSettings, *, named: bool) -> int:
    from datrix_semantic.diagnostics.report import CATALOG

    # drafting builds on this module, so it is imported where it is used.
    from datrix_scripts.dev.fixture_author.drafting import draft_package

    absent = _absent_areas(session, areas, named=named)
    if not absent:
        print("every planned area is on disk; nothing to draft")
        return 0
    try:
        content = ContentFilter(WORKSPACE_DIR)
    except AssistError as error:
        raise FixtureAuthorError(str(error)) from error
    return draft_package(session.package, CATALOG, absent, settings, content=content)


def run_diagnostics(root: Path, action: str, area: str, settings: LocalLlmSettings | None = None) -> int:
    """Run *action* (``draft``, ``plan``, ``scaffold`` or ``verify``) on the package at *root*, over
    its planned areas or the one *area* names; return the exit code (1 when an area fails or the
    package's state refuses the run; drafting's own codes otherwise). Drafting reads *settings*."""
    try:
        session = load_diagnostics_session(root)
        areas = (select_area(session.areas, area),) if area else session.areas
        if action == DRAFT_ACTION:
            if settings is None:
                raise FixtureAuthorError("drafting asks a local model, and no local model settings were given.")
            return _draft(session, areas, settings, named=bool(area))
        if action == "plan":
            print_plan(session, areas)
            return 0
        if action == "scaffold":
            return _scaffold(session, tuple(a for a in areas if a.seeded))
        return _verify(session, areas, OUTPUT_SHOWN)
    except FixtureAuthorError as error:
        print(f"ERROR: {error}")
        return 1


__all__ = [
    "DATASOURCE_TEMPLATES",
    "DRAFT_ACTION",
    "HALT_SUFFIX",
    "OUTPUT_SHOWN",
    "PROVEN_BY_CODE_NAME",
    "SCAFFOLD_FILES",
    "SYSTEM_CONFIG",
    "TARGETS_AREA",
    "AreaPlan",
    "AreaVerdict",
    "DiagnosticsSession",
    "FixtureAuthorError",
    "LocatedDiagnostic",
    "analysis_area_name",
    "analysis_areas",
    "area_input_names",
    "catalog_variants",
    "ensure_scaffold",
    "has_case_inputs",
    "load_diagnostics_session",
    "not_provoked_inputs",
    "package_needs",
    "plan_areas",
    "print_plan",
    "print_verdict",
    "proven_by_code",
    "proven_by_code_module",
    "run_diagnostics",
    "select_area",
    "system_owner",
    "target_check_areas",
    "variant_code",
    "verify_areas",
]
