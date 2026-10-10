"""Generated-suite parity gate: every registered language's generated project carries
its own emitted test suite, and those suites must agree.

Compares the structured result indices ``run_complete.py`` already wrote -- one per
generated project, ``<project>/.test_results/unit-tests-<stamp>/index.json``, produced
by ``datrix_scripts.generated_test_log_writer.GeneratedTestLogWriter`` -- and GENERATES AND RUNS
NOTHING itself. For every ``(example, runtime, provider)`` unit-tested in >= 2 registered
languages, the latest run's index of each language is read and three divergences are
reported:

  * ROLE GAP -- a test present in one language's suite and absent from another's: a
    language is silently emitting nothing for behaviour another language tests.
  * BEHAVIOUR GAP -- a test present in several languages' suites that passes in one and
    fails (or errors) in another: one source, two behaviours.
  * SKIP GAP -- a test one language skips and another runs. A skip is neither a pass nor
    a fail, so it is reported as its own category and never folded into either set; a
    test every language skips is not a divergence.

A test is identified by its service and its language-neutral case id
(``datrix_codegen_common.algorithms.test_case_identity``), which the index records beside
the framework-reported full name: a generated test carries the same case id in every
language however its framework names it (pytest ``classname::name``, Jest ``fullName``),
so module paths, ``describe`` titles and test wording never decide whether two languages
test the same thing. A test that carries no case id can match nothing, so it is reported
as an UNIDENTIFIED TEST -- its own failing category, never a role gap and never dropped.

THERE IS NO STORED BASELINE. The gate reads whatever the latest unit-test run of each
project wrote, prints every language's oldest and newest index timestamp, and REFUSES to
run (exit 2) rather than guess when the evidence is incomplete: a registered language with
no unit-tests index for an example another language has one for (and no entry in
parity-known-nongenerating.json), an index written before per-test records existed, a
service whose per-test records do not account for its counts, a service whose spec files
never ran, or fewer than two registered languages. A missing index is never read as
"zero tests, therefore zero gap": a language whose suite never ran is a worse signal than
a role gap, not a neutral one.

Only unit-test runs are compared. A deploy-test index records the docker lifecycle phases
of a live stack (build, up, health, database), not a flat per-test suite, and names no
passing test.

Built-in non-vacuity self-test, every invocation: a planted role gap, a planted behaviour
gap and a planted skip divergence are each detected, matching suites report nothing, fewer
than two languages is refused, and the discovery path is proven end to end over a
synthetic corpus written by the real index writer (pytest JUnit and Jest JSON both).

Usage:
    python generated_suite_parity.py
    python generated_suite_parity.py --generated-root D:/datrix/.generated
    python generated_suite_parity.py --list-limit 50
    python generated_suite_parity.py --debug
    python generated_suite_parity.py --self-test
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import os
import shutil
import sys
import xml.sax.saxutils as xml_utils
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Final, TypeVar

from artifact_role_parity import (
    DEFAULT_GENERATED_ROOT,
    KNOWN_NON_GENERATING_PATH,
    WORKSPACE_ROOT,
    example_id,
    known_non_generating_reason,
    load_known_non_generating,
    registered_example_relpaths,
)
from datrix_codegen_common.algorithms.test_case_identity import TEST_CASE_ID_PROPERTY
from datrix_scripts.generated_test_log_writer import (
    OUTCOME_ERROR,
    OUTCOME_FAILED,
    OUTCOME_PASSED,
    OUTCOME_SKIPPED,
    TEST_OUTCOMES,
    GeneratedTestLogWriter,
)
from datrix_scripts.registered_targets import registered_language_names

logger = logging.getLogger(__name__)

EXIT_OK: Final[int] = 0
EXIT_FAIL: Final[int] = 1
EXIT_USAGE: Final[int] = 2

_MIN_LANGUAGES: Final[int] = 2

#: Where a generated project's own test runner writes each run, and the run directory
#: and index file names it uses (``run_complete.py`` indexes the ``unit`` runs).
TEST_RESULTS_DIRNAME: Final[str] = ".test_results"
UNIT_RUN_DIR_PREFIX: Final[str] = "unit-tests-"
INDEX_FILENAME: Final[str] = "index.json"

#: Per-service ``counts`` keys whose sum is the number of per-test records the index
#: must carry for that service. ``suite_failures`` is excluded: a spec file that never
#: ran contributes no test, and the gate refuses an index that reports one.
_RECORDED_COUNT_KEYS: Final[tuple[str, ...]] = ("passed", "failed", "errors", "skipped")
_SUITE_FAILURES_KEY: Final[str] = "suite_failures"
#: The per-test record key holding the test's case id (``null`` when it carries none).
_CASE_KEY: Final[str] = "case"

#: How a test's outcome is classed for comparison. ``failed`` and ``error`` are both a
#: test that did not pass; ``skipped`` is a third state, never a pass or a fail.
_CLASS_PASS: Final[str] = "pass"
_CLASS_FAIL: Final[str] = "fail"
_CLASS_SKIP: Final[str] = "skip"
_OUTCOME_CLASS: Final[Mapping[str, str]] = {
    OUTCOME_PASSED: _CLASS_PASS,
    OUTCOME_FAILED: _CLASS_FAIL,
    OUTCOME_ERROR: _CLASS_FAIL,
    OUTCOME_SKIPPED: _CLASS_SKIP,
}

#: Gaps listed per (group, kind) before the report summarizes the rest; override with
#: ``--list-limit``.
_DEFAULT_LIST_LIMIT: Final[int] = 10

_SELF_TEST_LANGUAGE_A: Final[str] = "self_test_lang_a"
_SELF_TEST_LANGUAGE_B: Final[str] = "self_test_lang_b"
_SELF_TEST_LANGUAGE_C: Final[str] = "self_test_lang_c"
_SELF_TEST_EXAMPLE: Final[str] = "self_test_category/self_test_example"
_SELF_TEST_RUNTIME: Final[str] = "self_test_runtime"
_SELF_TEST_PROVIDER: Final[str] = "self_test_provider"
_SELF_TEST_SERVICE: Final[str] = "self_test_service"
_SELF_TEST_CASE_DOMAIN: Final[str] = "self_test"
_SELF_TEST_PYTEST_CLASS: Final[str] = "tests.unit.test_planted.TestPlanted"
_SELF_TEST_JEST_DESCRIBE: Final[str] = "Planted suite"
_SELF_TEST_STAMP: Final[str] = "20260101-000000"
_SELF_TEST_NEWER_STAMP: Final[str] = "20260102-000000"
#: Scratch root for the discovery self-test's synthetic corpus -- workspace-level per
#: the temp-file policy, PID-scoped so two concurrent gate runs never share a directory.
_SELF_TEST_SCRATCH_ROOT: Path = WORKSPACE_ROOT / ".test-output" / "generated-suite-self-test"

_T = TypeVar("_T")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


class IncompleteCorpusError(ValueError):
    """The generated corpus under the given root cannot support a comparison: a
    registered language has no unit-tests index for an example another language has
    one for, or fewer than two languages are registered."""


class MalformedSuiteIndexError(ValueError):
    """A unit-tests index is unreadable, belongs to a different project, predates
    per-test records, or does not account for the tests its own counts claim ran."""


@dataclasses.dataclass(frozen=True)
class SuiteIndex:
    """One language's unit-test suite outcome for one generated project, read from its
    already-written index.json.

    Attributes:
        language: The registered ``datrix.languages`` target the project was generated in.
        example: The example's posix path relative to ``datrix/examples``.
        runtime: The deployment runtime path segment (e.g. ``docker-compose``).
        provider: The provider path segment (e.g. ``local``).
        outcomes: ``{test key: outcome}`` -- every test the run executed that carries a
            case id, keyed by :func:`identity_key`; each outcome is one of ``TEST_OUTCOMES``.
        unidentified: ``<service>::<framework test name>`` of every test the run executed
            that carries no case id -- never comparable, always reported.
        source: Where the index was read from (a path, for the report).
        timestamp: The index's own ``timestamp``, so a reader sees how current it is.
    """

    language: str
    example: str
    runtime: str
    provider: str
    outcomes: Mapping[str, str]
    unidentified: tuple[str, ...]
    source: str
    timestamp: str

    @property
    def group_key(self) -> tuple[str, str, str]:
        """The cross-language comparison group this index belongs to."""
        return (self.example, self.runtime, self.provider)


@dataclasses.dataclass(frozen=True)
class RoleGap:
    """A test present in some language's suite and absent from another's, for the same
    ``(example, runtime, provider)``."""

    example: str
    runtime: str
    provider: str
    test_name: str
    present_in: tuple[str, ...]
    absent_from: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class BehaviourGap:
    """A test present in several languages' suites, for the same
    ``(example, runtime, provider)``, that passes in one and does not pass (fails or
    errors) in another."""

    example: str
    runtime: str
    provider: str
    test_name: str
    outcomes: dict[str, str]  # language -> outcome


@dataclasses.dataclass(frozen=True)
class SkipGap:
    """A test present in several languages' suites, for the same
    ``(example, runtime, provider)``, that one language skips and another runs."""

    example: str
    runtime: str
    provider: str
    test_name: str
    outcomes: dict[str, str]  # language -> outcome


@dataclasses.dataclass(frozen=True)
class UnidentifiedTest:
    """A test a language's suite ran that carries no case id, so no other language's
    test can ever be matched to it."""

    example: str
    runtime: str
    provider: str
    language: str
    test_name: str


@dataclasses.dataclass(frozen=True)
class SuiteComparison:
    """Every divergence :func:`compare_suites` found, by kind."""

    role_gaps: list[RoleGap]
    behaviour_gaps: list[BehaviourGap]
    skip_gaps: list[SkipGap]
    unidentified: list[UnidentifiedTest]

    @property
    def clean(self) -> bool:
        """True when no divergence of any kind was found."""
        return not (self.role_gaps or self.behaviour_gaps or self.skip_gaps or self.unidentified)

    def extend(self, other: SuiteComparison) -> None:
        """Add every divergence *other* found to this comparison."""
        self.role_gaps.extend(other.role_gaps)
        self.behaviour_gaps.extend(other.behaviour_gaps)
        self.skip_gaps.extend(other.skip_gaps)
        self.unidentified.extend(other.unidentified)


def _empty_comparison() -> SuiteComparison:
    """A comparison that has found nothing yet."""
    return SuiteComparison([], [], [], [])


def identity_key(service: str, case: str) -> str:
    """The identity a test is compared under: its service and its case id.

    The case id is the language-neutral identity every generated test carries
    (``datrix_codegen_common.algorithms.test_case_identity``), so the same test of the
    same item matches across languages however each framework names it.

    Args:
        service: The service the test ran in.
        case: The test's case id from the index's ``tests`` list.

    Returns:
        ``<service>::<case>``.
    """
    return f"{service}::{case}"


# ---------------------------------------------------------------------------
# Reading an index
# ---------------------------------------------------------------------------


def _malformed(index_path: Path, problem: str) -> MalformedSuiteIndexError:
    """Build the refusal for a bad index: what is wrong, where, and how to fix it."""
    return MalformedSuiteIndexError(
        f"GENERATED-SUITE PARITY GATE CANNOT RUN: unit-tests index {index_path} is not "
        f"usable: {problem}. Re-run that project's unit tests so its index is rewritten "
        f"by the current writer (run-complete.ps1 -All -L <language> -Skip4; Jon runs "
        f"this -- the gate never runs a suite itself)."
    )


def _expect(value: object, expected: type[_T], where: str, index_path: Path) -> _T:
    """Narrow one parsed-JSON value, refusing a wrong type loudly."""
    if not isinstance(value, expected):
        raise _malformed(
            index_path,
            f"{where} is a {type(value).__name__}, expected a {expected.__name__}",
        )
    return value


def _field(obj: Mapping[str, object], key: str, expected: type[_T], where: str, index_path: Path) -> _T:
    """One required key of a parsed-JSON object, refusing absence or a wrong type."""
    if key not in obj:
        raise _malformed(index_path, f"{where} has no {key!r} key")
    return _expect(obj[key], expected, f"{where}[{key!r}]", index_path)


def _expected_test_counts(data: Mapping[str, object], index_path: Path) -> dict[str, int]:
    """How many per-test records each service's counts say the index must carry.

    Raises:
        MalformedSuiteIndexError: A service reports a spec file that never ran.
    """
    expected: dict[str, int] = {}
    services = _field(data, "services", list, "index", index_path)
    for position, entry in enumerate(services):
        where = f"services[{position}]"
        service = _expect(entry, dict, where, index_path)
        name = _field(service, "name", str, where, index_path)
        if name in expected:
            raise _malformed(index_path, f"{where} repeats service {name!r}")
        counts = _field(service, "counts", dict, f"{where} ({name})", index_path)
        if _field(counts, _SUITE_FAILURES_KEY, int, f"{where}.counts", index_path) > 0:
            raise _malformed(
                index_path,
                f"service {name!r} reports {_SUITE_FAILURES_KEY} > 0: a spec file never "
                f"ran, so the tests it holds are missing from the index and its suite "
                f"cannot be compared",
            )
        expected[name] = sum(
            _field(counts, key, int, f"{where}.counts", index_path) for key in _RECORDED_COUNT_KEYS
        )
    return expected


@dataclasses.dataclass(frozen=True)
class _TestRecord:
    """One parsed per-test record of an index."""

    service: str
    test: str
    case: str | None
    outcome: str


def _record_case(record: Mapping[str, object], where: str, index_path: Path) -> str | None:
    """The record's case id, or ``None`` for a test that carries none.

    Raises:
        MalformedSuiteIndexError: The record has no ``case`` key (the index predates
            case ids), or its value is neither a string nor null.
    """
    if _CASE_KEY not in record:
        raise _malformed(
            index_path,
            f"{where} has no {_CASE_KEY!r} key -- it was written before per-test case ids "
            f"existed, so no test in it can be matched across languages",
        )
    case = record[_CASE_KEY]
    if case is None:
        return None
    return _expect(case, str, f"{where}[{_CASE_KEY!r}]", index_path)


def _parse_test_record(
    entry: object, position: int, services: Iterable[str], index_path: Path
) -> _TestRecord:
    """One per-test record.

    Raises:
        MalformedSuiteIndexError: The record is malformed, records an outcome outside the
            writer's vocabulary, or names a service the index's services list lacks.
    """
    where = f"tests[{position}]"
    record = _expect(entry, dict, where, index_path)
    service = _field(record, "service", str, where, index_path)
    outcome = _field(record, "outcome", str, where, index_path)
    test = _field(record, "test", str, where, index_path)
    case = _record_case(record, where, index_path)
    if outcome not in TEST_OUTCOMES:
        raise _malformed(
            index_path,
            f"{where} records outcome {outcome!r} for {service}::{test}; expected one of "
            f"{sorted(TEST_OUTCOMES)}",
        )
    if service not in set(services):
        raise _malformed(
            index_path,
            f"{where} names service {service!r}, which the index's services list does "
            f"not contain ({sorted(services)})",
        )
    return _TestRecord(service=service, test=test, case=case, outcome=outcome)


def _require_records_match_counts(
    recorded: Mapping[str, int], expected_by_service: Mapping[str, int], index_path: Path
) -> None:
    """Refuse a service whose per-test records do not add up to its own counts.

    Raises:
        MalformedSuiteIndexError: A service counts tests the index does not record -- it
            reported totals only, or no test report at all (its build died before the tests).
    """
    for service, expected in sorted(expected_by_service.items()):
        if recorded.get(service, 0) != expected:
            raise _malformed(
                index_path,
                f"service {service!r} counts {expected} test(s) but the index records "
                f"{recorded.get(service, 0)} per-test result(s) for it -- it reported totals "
                f"only, or no test report at all (its build died before the tests)",
            )


def _recorded_outcomes(
    data: Mapping[str, object], expected_by_service: Mapping[str, int], index_path: Path
) -> tuple[dict[str, str], tuple[str, ...]]:
    """Every per-test record of the index, checked against the per-service counts.

    Returns:
        ``({identity key: outcome}, unidentified)``: the outcome of every test that
        carries a case id, and ``<service>::<framework test name>`` of every test that
        carries none.

    Raises:
        MalformedSuiteIndexError: The index has no ``tests`` list (it predates per-test
            records), a record is malformed or predates case ids, two tests carry one
            case id, or a service's records do not add up to its counts.
    """
    if "tests" not in data:
        raise _malformed(
            index_path,
            "it has no 'tests' list -- it was written before per-test records existed, so "
            "the set of tests the run executed is unknown",
        )
    outcomes: dict[str, str] = {}
    unidentified: list[str] = []
    recorded: Counter[str] = Counter()
    for position, entry in enumerate(_field(data, "tests", list, "index", index_path)):
        record = _parse_test_record(entry, position, expected_by_service, index_path)
        recorded[record.service] += 1
        if record.case is None:
            unidentified.append(f"{record.service}::{record.test}")
            continue
        key = identity_key(record.service, record.case)
        if key in outcomes:
            raise MalformedSuiteIndexError(
                f"GENERATED-SUITE PARITY GATE CANNOT RUN: unit-tests index {index_path} "
                f"records two tests carrying the case id {key!r} (the second is "
                f"{record.test!r}). A generated suite renders each case of each item once; "
                f"the template that rendered this case twice must give each test its own "
                f"declared case (datrix_codegen_common.algorithms.test_case_identity)."
            )
        outcomes[key] = record.outcome
    _require_records_match_counts(recorded, expected_by_service, index_path)
    return outcomes, tuple(unidentified)


def parse_suite_index(
    index_path: Path, language: str, example: str, runtime: str, provider: str
) -> SuiteIndex:
    """Read one unit-tests index.json into a :class:`SuiteIndex`.

    Args:
        index_path: The run's ``index.json``.
        language: The language directory the project sits under; the index must agree.
        example: The example the project sits under; the index must agree.
        runtime: The runtime path segment the project sits under.
        provider: The provider path segment the project sits under.

    Returns:
        The index's per-test outcomes, keyed by :func:`identity_key`.

    Raises:
        MalformedSuiteIndexError: The file is unreadable, describes another project, or
            fails any check of :func:`_recorded_outcomes` / :func:`_expected_test_counts`.
    """
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise _malformed(index_path, f"it cannot be read as JSON ({exc})") from exc
    index = _expect(data, dict, "the document root", index_path)
    for key, expected in (("language", language), ("example", example)):
        found = _field(index, key, str, "index", index_path)
        if found != expected:
            raise _malformed(
                index_path,
                f"it records {key} {found!r} but sits under the {key} {expected!r} -- it "
                f"was written for another project",
            )
    outcomes, unidentified = _recorded_outcomes(
        index, _expected_test_counts(index, index_path), index_path
    )
    return SuiteIndex(
        language=language,
        example=example,
        runtime=runtime,
        provider=provider,
        outcomes=outcomes,
        unidentified=unidentified,
        source=str(index_path),
        timestamp=_field(index, "timestamp", str, "index", index_path),
    )


# ---------------------------------------------------------------------------
# Discovering the corpus
# ---------------------------------------------------------------------------


def require_comparable_languages(languages: Iterable[str]) -> list[str]:
    """The registered languages, refusing a set too small to compare.

    Raises:
        IncompleteCorpusError: Fewer than two languages are registered -- a
            cross-language comparison over one language is vacuous.
    """
    names = sorted(set(languages))
    if len(names) < _MIN_LANGUAGES:
        raise IncompleteCorpusError(
            f"GENERATED-SUITE PARITY GATE CANNOT RUN: {len(names)} registered language(s) "
            f"({names}); a cross-language comparison needs at least {_MIN_LANGUAGES}. "
            f"Install the second datrix-codegen-<language> package so its 'datrix.languages' "
            f"entry point registers."
        )
    return names


def latest_unit_run_dir(project: Path) -> Path | None:
    """The newest ``unit-tests-<stamp>`` run directory of a generated project.

    Run directories are named by sortable timestamp, so the lexicographically last one
    is the latest. An older run is never substituted for a newer one that wrote nothing.

    Args:
        project: A generated project directory.

    Returns:
        The newest run directory, or ``None`` when the project has never been unit-tested.
    """
    results = project / TEST_RESULTS_DIRNAME
    if not results.is_dir():
        return None
    runs = sorted(d for d in results.iterdir() if d.is_dir() and d.name.startswith(UNIT_RUN_DIR_PREFIX))
    return runs[-1] if runs else None


def _child_dirs(parent: Path) -> list[Path]:
    """Sorted immediate subdirectories of *parent*."""
    return sorted(p for p in parent.iterdir() if p.is_dir())


def _indices_under_provider(
    language: str, runtime: str, provider_dir: Path, examples: Sequence[str]
) -> list[SuiteIndex]:
    """Every registered example's latest unit-tests index under one ``<runtime>/<provider>``."""
    found: list[SuiteIndex] = []
    for example in examples:
        run_dir = latest_unit_run_dir(provider_dir / example)
        if run_dir is None:
            continue
        index_path = run_dir / INDEX_FILENAME
        if not index_path.is_file():
            raise _malformed(
                run_dir,
                f"the latest run directory holds no {INDEX_FILENAME} -- no service produced "
                f"a test report, so the run left nothing to compare",
            )
        found.append(parse_suite_index(index_path, language, example, runtime, provider_dir.name))
    return found


def missing_index_pairs(
    indices: Sequence[SuiteIndex], languages: Sequence[str], known: Mapping[str, str]
) -> list[tuple[str, str]]:
    """Every ``(example, language)`` with no index although another language has one.

    A pair the park file records as not generating is not missing: that language cannot
    produce a project to test, a fact already recorded once.

    Args:
        indices: Every discovered index.
        languages: The registered language names.
        known: The parked pairs (``load_known_non_generating``).

    Returns:
        The missing pairs, sorted.
    """
    have: dict[str, set[str]] = {}
    for suite in indices:
        have.setdefault(suite.example, set()).add(suite.language)
    missing: list[tuple[str, str]] = []
    for example in sorted(have):
        for language in languages:
            if language in have[example]:
                continue
            if known_non_generating_reason(known, example, language) is None:
                missing.append((example, language))
    return missing


def _incomplete_corpus_message(generated_root: Path, missing: Sequence[tuple[str, str]]) -> str:
    """The refusal naming every missing pair and the command that fills each language."""
    by_language: dict[str, list[str]] = {}
    for example, language in missing:
        by_language.setdefault(language, []).append(example)
    parts = [
        f"language={language}: {len(examples)} example(s) {examples}"
        for language, examples in sorted(by_language.items())
    ]
    languages = sorted(by_language)
    return (
        f"GENERATED-SUITE PARITY GATE CANNOT RUN: {len(missing)} (example, language) pair(s) "
        f"have no unit-tests index under {generated_root} although another registered "
        f"language has one for the same example, and the pair has no entry in "
        f"{KNOWN_NON_GENERATING_PATH.name}: {'; '.join(parts)}. A language whose suite never "
        f"ran is not a language with zero tests. Run each missing language's unit tests "
        f"first, once per language ({', '.join(languages)}): "
        f"run-complete.ps1 -All -L <language> -Skip4 (Step 3 writes the index this gate "
        f"reads; Jon runs this -- the gate never generates or runs a suite itself)."
    )


def discover_suite_indices(
    generated_root: Path,
    languages: Sequence[str],
    known: Mapping[str, str],
    examples: Sequence[str],
) -> list[SuiteIndex]:
    """Read every registered language's latest unit-tests index under *generated_root*.

    The layout is ``<language>/<runtime>/<provider>/<example>/.test_results/unit-tests-<stamp>/``.
    Reads only; never generates a project and never runs a suite.

    Args:
        generated_root: The ``generate.ps1`` output base.
        languages: The registered language names to look for.
        known: The parked pairs (``load_known_non_generating``).
        examples: The registered example relpaths to look for.

    Returns:
        Every index found, sorted by (language, example, runtime, provider).

    Raises:
        IncompleteCorpusError: A registered language has no index for an example another
            language has one for (and the pair is not parked), naming every such pair.
        MalformedSuiteIndexError: A found index is unusable (see :func:`parse_suite_index`).
    """
    indices: list[SuiteIndex] = []
    for language in sorted(languages):
        language_root = generated_root / language
        if not language_root.is_dir():
            continue
        for runtime_dir in _child_dirs(language_root):
            for provider_dir in _child_dirs(runtime_dir):
                indices.extend(_indices_under_provider(language, runtime_dir.name, provider_dir, examples))
    missing = missing_index_pairs(indices, languages, known)
    if missing:
        raise IncompleteCorpusError(_incomplete_corpus_message(generated_root, missing))
    return sorted(indices, key=lambda s: (s.language, s.example, s.runtime, s.provider))


def comparison_groups(
    indices: Sequence[SuiteIndex],
) -> dict[tuple[str, str, str], list[SuiteIndex]]:
    """Group indices by (example, runtime, provider), keeping the multi-language ones.

    Returns:
        ``{group_key: [index per language]}`` for every group unit-tested in at least
        ``_MIN_LANGUAGES`` languages, sorted by key.
    """
    by_key: dict[tuple[str, str, str], list[SuiteIndex]] = {}
    for suite in indices:
        by_key.setdefault(suite.group_key, []).append(suite)
    return {
        key: group
        for key, group in sorted(by_key.items())
        if len({s.language for s in group}) >= _MIN_LANGUAGES
    }


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


def _outcome_class(outcome: str) -> str:
    """The comparison class (pass / fail / skip) of a recorded outcome.

    Raises:
        ValueError: *outcome* is outside the writer's vocabulary.
    """
    if outcome not in _OUTCOME_CLASS:
        raise ValueError(
            f"Unknown test outcome {outcome!r}; expected one of {sorted(_OUTCOME_CLASS)} "
            f"(the vocabulary datrix_scripts.generated_test_log_writer records)."
        )
    return _OUTCOME_CLASS[outcome]


def _outcome_divergences(outcomes: Mapping[str, str]) -> tuple[bool, bool]:
    """How one test's outcomes across the languages it is present in diverge.

    Args:
        outcomes: ``{language: outcome}`` for the languages the test is present in.

    Returns:
        ``(is_skip_gap, is_behaviour_gap)``. A skip gap: at least one language skipped the
        test and at least one ran it. A behaviour gap: the languages that ran it disagree
        between a pass and a fail/error. Skipped outcomes never count toward either set.
    """
    classes = [_outcome_class(outcome) for outcome in outcomes.values()]
    ran = {cls for cls in classes if cls != _CLASS_SKIP}
    return bool(ran) and _CLASS_SKIP in classes, len(ran) > 1


def _compare_group(
    group_key: tuple[str, str, str], group: Sequence[SuiteIndex]
) -> SuiteComparison:
    """Compare one (example, runtime, provider)'s suites across its languages."""
    example, runtime, provider = group_key
    languages = [suite.language for suite in group]
    if len(set(languages)) != len(languages) or len(languages) < _MIN_LANGUAGES:
        raise ValueError(
            f"compare_suites needs one index from each of at least {_MIN_LANGUAGES} distinct "
            f"languages per (example, runtime, provider); {group_key} has {sorted(languages)}."
        )
    by_language = {suite.language: suite.outcomes for suite in group}
    names: set[str] = set()
    for suite_outcomes in by_language.values():
        names.update(suite_outcomes)
    comparison = _empty_comparison()
    for suite in sorted(group, key=lambda s: s.language):
        comparison.unidentified.extend(
            UnidentifiedTest(example, runtime, provider, suite.language, test)
            for test in suite.unidentified
        )
    for name in sorted(names):
        present = tuple(sorted(lang for lang, outcomes in by_language.items() if name in outcomes))
        absent = tuple(sorted(lang for lang, outcomes in by_language.items() if name not in outcomes))
        if absent:
            comparison.role_gaps.append(RoleGap(example, runtime, provider, name, present, absent))
        if len(present) < _MIN_LANGUAGES:
            continue
        outcomes = {lang: by_language[lang][name] for lang in present}
        is_skip_gap, is_behaviour_gap = _outcome_divergences(outcomes)
        if is_skip_gap:
            comparison.skip_gaps.append(SkipGap(example, runtime, provider, name, outcomes))
        if is_behaviour_gap:
            comparison.behaviour_gaps.append(BehaviourGap(example, runtime, provider, name, outcomes))
    return comparison


def compare_suites(indices: Sequence[SuiteIndex]) -> SuiteComparison:
    """Compare every language's test set and outcomes, per (example, runtime, provider).

    A test present in some languages' suites and absent from others' is a role gap. A
    test present in at least two languages whose outcomes are a pass in one and a fail
    or error in another is a behaviour gap (the comparison runs over the languages the
    test is present in, so a role gap never hides a behaviour gap). A test present in at
    least two languages that one skips and another runs is a skip gap. A test every
    present language skips, or whose outcomes agree, is no divergence. A test carrying no
    case id is reported as unidentified: it can never match another language's test, so
    it is neither counted as a role gap nor left out.

    Args:
        indices: One index per language for each group; groups are formed from
            ``SuiteIndex.group_key``.

    Returns:
        Every divergence found, in deterministic (group, test name) order.

    Raises:
        ValueError: A group has fewer than two distinct languages, or repeats one.
    """
    by_group: dict[tuple[str, str, str], list[SuiteIndex]] = {}
    for suite in indices:
        by_group.setdefault(suite.group_key, []).append(suite)
    merged = _empty_comparison()
    for group_key, group in sorted(by_group.items()):
        merged.extend(_compare_group(group_key, group))
    return merged


def skip_counts(indices: Sequence[SuiteIndex]) -> dict[str, int]:
    """How many tests each language skipped across *indices* (reported, never a gap by itself)."""
    counts: Counter[str] = Counter()
    for suite in indices:
        counts[suite.language] += sum(1 for outcome in suite.outcomes.values() if outcome == OUTCOME_SKIPPED)
    return dict(counts)


# ---------------------------------------------------------------------------
# The real run
# ---------------------------------------------------------------------------


def _log_corpus_currency(indices: Sequence[SuiteIndex], languages: Sequence[str]) -> None:
    """Print every language's index count and oldest/newest timestamp."""
    for language in languages:
        stamps = sorted(s.timestamp for s in indices if s.language == language)
        logger.info(
            "generated_suite_corpus language=%s indices=%d oldest=%s newest=%s",
            language, len(stamps), stamps[0] if stamps else "-", stamps[-1] if stamps else "-",
        )


def _log_gaps(kind: str, label: str, lines: Sequence[str], limit: int) -> None:
    """Log one group's gaps of one kind: a count line, then at most *limit* detail lines."""
    if not lines:
        return
    logger.error("%s %s count=%d", kind, label, len(lines))
    for line in lines[:limit]:
        logger.error("  %s", line)
    if len(lines) > limit:
        logger.error("  ... and %d more (raise --list-limit to list them)", len(lines) - limit)


def _report_group(
    group_key: tuple[str, str, str],
    group: Sequence[SuiteIndex],
    comparison: SuiteComparison,
    limit: int,
) -> None:
    """Log one group's totals, skip counts and every divergence found."""
    example, runtime, provider = group_key
    label = f"example={example} runtime={runtime} provider={provider}"
    logger.info(
        "generated_suite_group %s languages=%s tests=%s skipped=%s",
        label,
        sorted(s.language for s in group),
        {s.language: len(s.outcomes) for s in sorted(group, key=lambda s: s.language)},
        dict(sorted(skip_counts(group).items())),
    )
    if comparison.clean:
        logger.info("generated_suite_example_clean %s", label)
        return
    _log_gaps(
        "GENERATED-SUITE ROLE GAP", label,
        [f"test={g.test_name} present_in={list(g.present_in)} absent_from={list(g.absent_from)}"
         for g in comparison.role_gaps],
        limit,
    )
    _log_gaps(
        "GENERATED-SUITE BEHAVIOUR GAP", label,
        [f"test={g.test_name} outcomes={dict(sorted(g.outcomes.items()))}" for g in comparison.behaviour_gaps],
        limit,
    )
    _log_gaps(
        "GENERATED-SUITE SKIP GAP", label,
        [f"test={g.test_name} outcomes={dict(sorted(g.outcomes.items()))}" for g in comparison.skip_gaps],
        limit,
    )
    _log_gaps(
        "GENERATED-SUITE UNIDENTIFIED TEST", label,
        [f"test={g.test_name} language={g.language}" for g in comparison.unidentified],
        limit,
    )


def check_generated_suite_parity(
    generated_root: Path,
    limit: int,
    registered_languages: Iterable[str],
    known: Mapping[str, str],
    examples: Sequence[str],
) -> int:
    """Run the gate over every (example, runtime, provider) unit-tested in >= 2 languages.

    Args:
        generated_root: The ``generate.ps1`` output base to read.
        limit: Gaps listed per (group, kind) before the report summarizes the rest.
        registered_languages: The registered ``datrix.languages`` names (injected so the
            self-test can prove the refusal under a reduced set).
        known: The parked pairs (``load_known_non_generating``).
        examples: The registered example relpaths to look for.

    Returns:
        ``EXIT_OK`` when every comparable group's suites agree, ``EXIT_FAIL`` when a role,
        behaviour or skip gap or an unidentified test was found, ``EXIT_USAGE`` when no
        group is unit-tested in
        >= 2 languages (a vacuous comparison).

    Raises:
        IncompleteCorpusError: Fewer than two registered languages, or a language has no
            index for an example another language has one for.
        MalformedSuiteIndexError: A found index is unusable.
    """
    languages = require_comparable_languages(registered_languages)
    indices = discover_suite_indices(generated_root, languages, known, examples)
    _log_corpus_currency(indices, languages)
    groups = comparison_groups(indices)
    if not groups:
        logger.error(
            "GENERATED-SUITE PARITY GATE CANNOT RUN: no (example, runtime, provider) under %s "
            "is unit-tested in >= %d languages -- a cross-language comparison over fewer is "
            "vacuous. Run each language's unit tests first: run-complete.ps1 -All -L "
            "<language> -Skip4.",
            generated_root, _MIN_LANGUAGES,
        )
        return EXIT_USAGE
    totals = _empty_comparison()
    for group_key, group in groups.items():
        comparison = compare_suites(group)
        _report_group(group_key, group, comparison, limit)
        totals.extend(comparison)
    if totals.clean:
        logger.info(
            "GENERATED-SUITE PARITY GATE PASSED: %d group(s) unit-tested in >= %d languages, "
            "every language emitted the same tests and they passed the same.",
            len(groups), _MIN_LANGUAGES,
        )
        return EXIT_OK
    logger.error(
        "GENERATED-SUITE PARITY GATE FAILED: %d group(s) compared, %d role gap(s), %d "
        "behaviour gap(s), %d skip gap(s), %d unidentified test(s).",
        len(groups), len(totals.role_gaps), len(totals.behaviour_gaps), len(totals.skip_gaps),
        len(totals.unidentified),
    )
    return EXIT_FAIL


# ---------------------------------------------------------------------------
# Non-vacuity self-test
# ---------------------------------------------------------------------------


def _fixture_index(
    language: str, outcomes: Mapping[str, str], unidentified: tuple[str, ...] = ()
) -> SuiteIndex:
    """A synthetic in-memory index for the comparator's self-test."""
    return SuiteIndex(
        language=language,
        example=_SELF_TEST_EXAMPLE,
        runtime=_SELF_TEST_RUNTIME,
        provider=_SELF_TEST_PROVIDER,
        outcomes=outcomes,
        unidentified=unidentified,
        source="self-test fixture",
        timestamp="2026-01-01T00:00:00",
    )


def _planted_case(test: str) -> str:
    """The case id a planted test carries."""
    return f"{_SELF_TEST_CASE_DOMAIN}/{test}"


def _planted(test: str) -> str:
    """The comparison key of a planted test in the self-test's one service."""
    return identity_key(_SELF_TEST_SERVICE, _planted_case(test))


def _report_case(label: str, problems: list[str]) -> list[str]:
    """Log one self-test case as ``[OK]`` or ``[FAIL]`` and pass its problems through."""
    if problems:
        logger.error("[FAIL] %s", label)
        for problem in problems:
            logger.error("       %s", problem)
    else:
        logger.info("[OK] %s", label)
    return problems


def _self_test_role_gap() -> list[str]:
    """A test present in one language's index and absent from the other's is exactly one RoleGap."""
    only_a = _planted("only_in_a")
    shared = _planted("shared")
    found = compare_suites([
        _fixture_index(_SELF_TEST_LANGUAGE_A, {shared: OUTCOME_PASSED, only_a: OUTCOME_PASSED}),
        _fixture_index(_SELF_TEST_LANGUAGE_B, {shared: OUTCOME_PASSED}),
    ])
    expected = RoleGap(
        _SELF_TEST_EXAMPLE, _SELF_TEST_RUNTIME, _SELF_TEST_PROVIDER, only_a,
        (_SELF_TEST_LANGUAGE_A,), (_SELF_TEST_LANGUAGE_B,),
    )
    problems: list[str] = []
    if found.role_gaps != [expected]:
        problems.append(f"expected exactly the planted RoleGap {expected}, got {found.role_gaps}")
    if found.behaviour_gaps or found.skip_gaps:
        problems.append(f"a role gap alone reported other gaps: {found}")
    return problems


def _self_test_behaviour_gap() -> list[str]:
    """A test both languages emit with a pass in one and a fail in the other is exactly one
    BehaviourGap; a fail against an error is the same class and no gap."""
    shared = _planted("shared")
    steady = _planted("steady")
    found = compare_suites([
        _fixture_index(_SELF_TEST_LANGUAGE_A, {shared: OUTCOME_PASSED, steady: OUTCOME_FAILED}),
        _fixture_index(_SELF_TEST_LANGUAGE_B, {shared: OUTCOME_FAILED, steady: OUTCOME_ERROR}),
    ])
    expected = BehaviourGap(
        _SELF_TEST_EXAMPLE, _SELF_TEST_RUNTIME, _SELF_TEST_PROVIDER, shared,
        {_SELF_TEST_LANGUAGE_A: OUTCOME_PASSED, _SELF_TEST_LANGUAGE_B: OUTCOME_FAILED},
    )
    problems: list[str] = []
    if found.behaviour_gaps != [expected]:
        problems.append(f"expected exactly the planted BehaviourGap {expected}, got {found.behaviour_gaps}")
    if found.role_gaps or found.skip_gaps:
        problems.append(f"a behaviour gap alone reported other gaps: {found}")
    return problems


def _self_test_matching_pair() -> list[str]:
    """Two languages with identical names and outcomes report no gap of any kind."""
    outcomes = {
        _planted("alpha"): OUTCOME_PASSED,
        _planted("beta"): OUTCOME_FAILED,
        _planted("gamma"): OUTCOME_SKIPPED,
    }
    found = compare_suites([
        _fixture_index(_SELF_TEST_LANGUAGE_A, outcomes),
        _fixture_index(_SELF_TEST_LANGUAGE_B, dict(outcomes)),
    ])
    return [] if found.clean else [f"a matching pair reported a divergence: {found}"]


def _self_test_skip_category() -> list[str]:
    """A skip is its own category: skipped against passed is a SkipGap (never a behaviour or
    role gap), skipped in every language is no divergence, and three languages where one skips
    while two disagree report both the skip gap and the behaviour gap."""
    only_skip = _planted("skipped_in_a")
    both_skip = _planted("skipped_in_both")
    found = compare_suites([
        _fixture_index(_SELF_TEST_LANGUAGE_A, {only_skip: OUTCOME_SKIPPED, both_skip: OUTCOME_SKIPPED}),
        _fixture_index(_SELF_TEST_LANGUAGE_B, {only_skip: OUTCOME_PASSED, both_skip: OUTCOME_SKIPPED}),
    ])
    problems: list[str] = []
    expected = SkipGap(
        _SELF_TEST_EXAMPLE, _SELF_TEST_RUNTIME, _SELF_TEST_PROVIDER, only_skip,
        {_SELF_TEST_LANGUAGE_A: OUTCOME_SKIPPED, _SELF_TEST_LANGUAGE_B: OUTCOME_PASSED},
    )
    if found.skip_gaps != [expected]:
        problems.append(f"expected exactly the planted SkipGap {expected}, got {found.skip_gaps}")
    if found.role_gaps or found.behaviour_gaps:
        problems.append(f"a skip divergence alone was folded into another gap kind: {found}")

    three_way = _planted("three_way")
    only_in_two = _planted("only_in_two")
    triple = compare_suites([
        _fixture_index(_SELF_TEST_LANGUAGE_A, {three_way: OUTCOME_PASSED, only_in_two: OUTCOME_PASSED}),
        _fixture_index(_SELF_TEST_LANGUAGE_B, {three_way: OUTCOME_FAILED, only_in_two: OUTCOME_FAILED}),
        _fixture_index(_SELF_TEST_LANGUAGE_C, {three_way: OUTCOME_SKIPPED}),
    ])
    if [g.test_name for g in triple.skip_gaps] != [three_way]:
        problems.append(f"three-language skip divergence not reported once: {triple.skip_gaps}")
    if [g.test_name for g in triple.behaviour_gaps] != [only_in_two, three_way]:
        problems.append(
            f"a pass/fail disagreement among the languages a test is present in must be a "
            f"behaviour gap even when a third language lacks it: {triple.behaviour_gaps}"
        )
    if [g.test_name for g in triple.role_gaps] != [only_in_two]:
        problems.append(f"the test absent from the third language is exactly one role gap: {triple.role_gaps}")
    return problems


def _self_test_unidentified() -> list[str]:
    """A test carrying no case id is reported as unidentified -- never as a role gap,
    never dropped -- and keeps the comparison from being clean."""
    shared = _planted("shared")
    unmarked = f"{_SELF_TEST_SERVICE}::tests.unit.test_planted::test_unmarked"
    found = compare_suites([
        _fixture_index(_SELF_TEST_LANGUAGE_A, {shared: OUTCOME_PASSED}, (unmarked,)),
        _fixture_index(_SELF_TEST_LANGUAGE_B, {shared: OUTCOME_PASSED}),
    ])
    expected = UnidentifiedTest(
        _SELF_TEST_EXAMPLE, _SELF_TEST_RUNTIME, _SELF_TEST_PROVIDER, _SELF_TEST_LANGUAGE_A, unmarked,
    )
    problems: list[str] = []
    if found.unidentified != [expected]:
        problems.append(f"expected exactly the planted UnidentifiedTest {expected}, got {found.unidentified}")
    if found.role_gaps or found.behaviour_gaps or found.skip_gaps:
        problems.append(f"an unidentified test was folded into another gap kind: {found}")
    if found.clean:
        problems.append("a comparison holding an unidentified test reported clean")
    return problems


def _refusal(call: Callable[[], object], error: type[Exception]) -> tuple[bool, str]:
    """Run *call* and report whether it raised *error*, with the message when it did.

    A self-test helper: the caller asserts a refusal, so what it needs back is whether the
    call raised and what it said.

    Returns:
        ``(raised, message)``; ``message`` is empty when *call* ran to completion.
    """
    try:
        call()
    except error as exc:
        return True, str(exc)
    return False, ""


def _self_test_language_floor() -> list[str]:
    """Fewer than two languages is refused, two are accepted, and a one-language group is
    refused by the comparator."""
    problems: list[str] = []
    raised, message = _refusal(
        lambda: require_comparable_languages([_SELF_TEST_LANGUAGE_A]), IncompleteCorpusError
    )
    if not raised:
        problems.append("require_comparable_languages accepted a single registered language")
    elif _SELF_TEST_LANGUAGE_A not in message:
        problems.append(f"the refusal does not name the registered set: {message}")
    raised, _ = _refusal(lambda: require_comparable_languages([]), IncompleteCorpusError)
    if not raised:
        problems.append("require_comparable_languages accepted an empty registered set")
    accepted = require_comparable_languages([_SELF_TEST_LANGUAGE_B, _SELF_TEST_LANGUAGE_A])
    if accepted != [_SELF_TEST_LANGUAGE_A, _SELF_TEST_LANGUAGE_B]:
        problems.append(f"require_comparable_languages mangled a two-language set: {accepted}")
    lone = _fixture_index(_SELF_TEST_LANGUAGE_A, {})
    raised, _ = _refusal(lambda: compare_suites([lone]), ValueError)
    if not raised:
        problems.append("compare_suites accepted a group of a single language")
    # The real entry point refuses before it reads anything: the reduced registered set is
    # injected, and the root it would otherwise walk does not need to exist.
    raised, message = _refusal(
        lambda: check_generated_suite_parity(
            _SELF_TEST_SCRATCH_ROOT, _DEFAULT_LIST_LIMIT, [_SELF_TEST_LANGUAGE_A], {}, []
        ),
        IncompleteCorpusError,
    )
    if not raised:
        problems.append("check_generated_suite_parity ran under a single registered language")
    else:
        logger.info("self-test refusal text (single registered language): %s", message)
    return problems


def _self_test_outcome_vocabulary() -> list[str]:
    """Every outcome the index writer can record is classified, and an unknown one is refused."""
    problems: list[str] = []
    unclassified = TEST_OUTCOMES - set(_OUTCOME_CLASS)
    if unclassified:
        problems.append(f"the writer records outcomes this gate does not classify: {sorted(unclassified)}")
    stale = set(_OUTCOME_CLASS) - TEST_OUTCOMES
    if stale:
        problems.append(f"this gate classifies outcomes the writer never records: {sorted(stale)}")
    raised, _ = _refusal(lambda: _outcome_class("self_test_undeclared_outcome"), ValueError)
    if not raised:
        problems.append("_outcome_class accepted an outcome outside the writer's vocabulary")
    return problems


def _junit_report(cases: Mapping[str, str], unidentified: Sequence[str]) -> str:
    """A pytest-shaped JUnit XML report: one test per ``{name: outcome}`` entry, named the
    pytest way and recording its case id as the property a generated suite writes, plus
    one passing test per *unidentified* name that records none."""
    bodies = {
        OUTCOME_PASSED: "",
        OUTCOME_FAILED: '<failure type="AssertionError" message="planted">planted</failure>',
        OUTCOME_ERROR: '<error type="RuntimeError" message="planted">planted</error>',
        OUTCOME_SKIPPED: '<skipped message="planted"/>',
    }
    case_property = (
        f"<properties><property name={xml_utils.quoteattr(TEST_CASE_ID_PROPERTY)} "
        "value={value}/></properties>"
    )
    cases_xml = "".join(
        f'<testcase classname="{_SELF_TEST_PYTEST_CLASS}" name={xml_utils.quoteattr(name)}>'
        f"{case_property.format(value=xml_utils.quoteattr(_planted_case(name)))}{bodies[outcome]}</testcase>"
        for name, outcome in cases.items()
    )
    cases_xml += "".join(
        f'<testcase classname="{_SELF_TEST_PYTEST_CLASS}" name={xml_utils.quoteattr(name)}/>'
        for name in unidentified
    )
    return f'<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite>{cases_xml}</testsuite></testsuites>'


def _jest_report(cases: Mapping[str, str]) -> dict[str, object]:
    """A Jest ``--json`` report with one assertion per ``{name: outcome}`` entry, titled by
    its case id under a prose ``describe`` -- so its full name differs from the pytest
    report's while its case id matches."""
    statuses = {
        OUTCOME_PASSED: "passed",
        OUTCOME_FAILED: "failed",
        OUTCOME_ERROR: "failed",
        OUTCOME_SKIPPED: "pending",
    }
    assertions: list[dict[str, object]] = [
        {
            "title": _planted_case(name),
            "fullName": f"{_SELF_TEST_JEST_DESCRIBE} {_planted_case(name)}",
            "status": statuses[outcome],
            "failureMessages": ["planted"],
        }
        for name, outcome in cases.items()
    ]
    failed = any(a["status"] == "failed" for a in assertions)
    return {
        "testResults": [
            {
                "name": "/app/tests/planted.spec.ts",
                "status": "failed" if failed else "passed",
                "assertionResults": assertions,
            }
        ]
    }


def _plant_unit_run(
    root: Path,
    language: str,
    example: str,
    stamp: str,
    cases: Mapping[str, str],
    *,
    jest: bool,
    unidentified: Sequence[str] = (),
) -> Path:
    """Write one synthetic unit-tests run through the REAL index writer; return its run dir.

    The planted report is JUnit XML (the pytest shape) or Jest JSON, parsed and indexed by
    ``GeneratedTestLogWriter`` exactly as ``run_complete.py`` does, so the discovery
    self-test proves the producer's output is what this gate's reader accepts.
    *unidentified* plants pytest tests that record no case id.
    """
    project = root / language / _SELF_TEST_RUNTIME / _SELF_TEST_PROVIDER / example
    run_dir = project / TEST_RESULTS_DIRNAME / f"{UNIT_RUN_DIR_PREFIX}{stamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    report = run_dir / ("planted-report.json" if jest else "planted-report.xml")
    report.write_text(
        json.dumps(_jest_report(cases)) if jest else _junit_report(cases, unidentified),
        encoding="utf-8",
    )
    writer = GeneratedTestLogWriter(
        project_path=f"{language}/{_SELF_TEST_RUNTIME}/{_SELF_TEST_PROVIDER}/{example}",
        language=language,
        platform="docker",
        example=example,
        run_dir=run_dir,
        dtrx_source=f"datrix/examples/{example}/system.dtrx",
    )
    log_path = run_dir / "planted-service.log"
    if jest:
        writer.add_service_jest_json(_SELF_TEST_SERVICE, report, log_path)
    else:
        writer.add_service_junit_xml(_SELF_TEST_SERVICE, report, log_path)
    writer.write(0.1)
    return run_dir


def _plant_corpus(root: Path, examples: Mapping[str, tuple[Mapping[str, str], Mapping[str, str]]]) -> None:
    """Plant language A (pytest JUnit) and language B (Jest JSON) for each ``{example: (a, b)}``."""
    for example, (cases_a, cases_b) in examples.items():
        _plant_unit_run(root, _SELF_TEST_LANGUAGE_A, example, _SELF_TEST_STAMP, cases_a, jest=False)
        _plant_unit_run(root, _SELF_TEST_LANGUAGE_B, example, _SELF_TEST_STAMP, cases_b, jest=True)


def _self_test_discovery(scratch: Path) -> list[str]:
    """Discovery reads real writer output from both frameworks, groups it, and feeds the
    comparator the planted divergences."""
    problems: list[str] = []
    role_example = f"{_SELF_TEST_EXAMPLE}_role"
    behaviour_example = f"{_SELF_TEST_EXAMPLE}_behaviour"
    root = scratch / "discovery"
    _plant_corpus(root, {
        role_example: ({"alpha": OUTCOME_PASSED, "beta": OUTCOME_PASSED}, {"alpha": OUTCOME_PASSED}),
        behaviour_example: ({"alpha": OUTCOME_PASSED}, {"alpha": OUTCOME_FAILED}),
    })
    languages = [_SELF_TEST_LANGUAGE_A, _SELF_TEST_LANGUAGE_B]
    indices = discover_suite_indices(root, languages, {}, [role_example, behaviour_example])
    if len(indices) != 4:
        return [f"discover_suite_indices found {len(indices)} indices, expected the 4 planted"]
    groups = comparison_groups(indices)
    if len(groups) != 2:
        problems.append(f"comparison_groups returned {sorted(groups)}, expected the two planted groups")
    found = compare_suites(indices)
    if [g.test_name for g in found.role_gaps] != [_planted("beta")]:
        problems.append(f"the role gap planted through the real writer was not found: {found.role_gaps}")
    if [g.test_name for g in found.behaviour_gaps] != [_planted("alpha")]:
        problems.append(f"the behaviour gap planted through the real writer was not found: {found.behaviour_gaps}")
    if found.skip_gaps or found.unidentified:
        problems.append(f"unexpected skip gaps or unidentified tests over the planted corpus: {found}")
    problems += _framework_names_differ_while_cases_match(root, role_example)
    return problems


def _framework_names_differ_while_cases_match(root: Path, example: str) -> list[str]:
    """The two planted frameworks name the shared test differently and record one case id
    for it -- the property that makes the comparison above non-vacuous."""
    records: dict[str, list[dict[str, object]]] = {}
    for language in (_SELF_TEST_LANGUAGE_A, _SELF_TEST_LANGUAGE_B):
        project = root / language / _SELF_TEST_RUNTIME / _SELF_TEST_PROVIDER / example
        run_dir = latest_unit_run_dir(project)
        if run_dir is None:
            return [f"no planted run directory under {project}"]
        index = json.loads((run_dir / INDEX_FILENAME).read_text(encoding="utf-8"))
        records[language] = index["tests"]
    names_a = {r["test"] for r in records[_SELF_TEST_LANGUAGE_A]}
    names_b = {r["test"] for r in records[_SELF_TEST_LANGUAGE_B]}
    cases_a = {r[_CASE_KEY] for r in records[_SELF_TEST_LANGUAGE_A]}
    cases_b = {r[_CASE_KEY] for r in records[_SELF_TEST_LANGUAGE_B]}
    problems: list[str] = []
    if names_a & names_b:
        problems.append(f"the planted frameworks share test names {sorted(names_a & names_b)}; the "
                        f"case-id match is not being exercised")
    if cases_a & cases_b != {_planted_case("alpha")}:
        problems.append(f"the planted frameworks did not record one shared case id: {cases_a} / {cases_b}")
    return problems


def _self_test_missing_index(scratch: Path) -> list[str]:
    """A language with no index for an example another language has one for is refused,
    naming the pair; a parked pair is not missing."""
    problems: list[str] = []
    complete = f"{_SELF_TEST_EXAMPLE}_complete"
    lopsided = f"{_SELF_TEST_EXAMPLE}_lopsided"
    root = scratch / "missing"
    _plant_corpus(root, {complete: ({"alpha": OUTCOME_PASSED}, {"alpha": OUTCOME_PASSED})})
    _plant_unit_run(root, _SELF_TEST_LANGUAGE_A, lopsided, _SELF_TEST_STAMP, {"alpha": OUTCOME_PASSED}, jest=False)
    languages = [_SELF_TEST_LANGUAGE_A, _SELF_TEST_LANGUAGE_B]
    examples = [complete, lopsided]
    try:
        discover_suite_indices(root, languages, {}, examples)
        problems.append("discover_suite_indices read a corpus where one language never ran an example as complete")
    except IncompleteCorpusError as exc:
        message = str(exc)
        for fragment in (lopsided, _SELF_TEST_LANGUAGE_B, "run-complete.ps1"):
            if fragment not in message:
                problems.append(f"the refusal does not name {fragment!r}: {message}")
        logger.info("self-test refusal text (incomplete corpus): %s", message)
    parked = {example_id(lopsided): "self-test: this example cannot generate"}
    if len(discover_suite_indices(root, languages, parked, examples)) != 3:
        problems.append("a parked pair was still treated as a missing index, or the other indices were dropped")
    return problems


def _plant_index(path: Path, document: Mapping[str, object]) -> Path:
    """Write a hand-built index document (for the refusal cases a real writer never emits)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _valid_index_document(language: str, example: str) -> dict[str, object]:
    """A minimal index document the reader accepts; refusal cases mutate a copy of it."""
    return {
        "schema_version": 1,
        "language": language,
        "example": example,
        "timestamp": "2026-01-01T00:00:00",
        "services": [{
            "name": _SELF_TEST_SERVICE,
            "counts": {"passed": 1, "failed": 0, "errors": 0, "skipped": 0, "suite_failures": 0},
        }],
        "tests": [{
            "service": _SELF_TEST_SERVICE, "test": "test_alpha", _CASE_KEY: _planted_case("alpha"),
            "outcome": OUTCOME_PASSED,
        }],
    }


def _expect_refusal(case: str, index_path: Path, fragment: str) -> list[str]:
    """Parse *index_path* and require a MalformedSuiteIndexError mentioning *fragment*."""
    try:
        parse_suite_index(index_path, _SELF_TEST_LANGUAGE_A, _SELF_TEST_EXAMPLE, _SELF_TEST_RUNTIME, _SELF_TEST_PROVIDER)
    except MalformedSuiteIndexError as exc:
        return [] if fragment in str(exc) else [f"{case}: refused, but without naming {fragment!r}: {exc}"]
    return [f"{case}: an unusable index was accepted"]


def _self_test_index_refusals(scratch: Path) -> list[str]:
    """Each way an index can fail to account for its suite is refused loudly, and the
    unmodified document is accepted (the refusals are not a blanket reject)."""
    root = scratch / "refusals"
    language, example = _SELF_TEST_LANGUAGE_A, _SELF_TEST_EXAMPLE
    problems: list[str] = []

    valid = _plant_index(root / "valid.json", _valid_index_document(language, example))
    parsed = parse_suite_index(valid, language, example, _SELF_TEST_RUNTIME, _SELF_TEST_PROVIDER)
    if parsed.outcomes != {_planted("alpha"): OUTCOME_PASSED} or parsed.unidentified:
        problems.append(f"a valid index parsed to {dict(parsed.outcomes)} / {parsed.unidentified}")

    predates = _valid_index_document(language, example)
    del predates["tests"]
    problems += _expect_refusal("index without per-test records", _plant_index(root / "predates.json", predates), "no 'tests' list")

    no_cases = _valid_index_document(language, example)
    no_cases["tests"] = [{"service": _SELF_TEST_SERVICE, "test": "test_alpha", "outcome": OUTCOME_PASSED}]
    problems += _expect_refusal("index without per-test case ids", _plant_index(root / "no-cases.json", no_cases), "per-test case ids")

    totals_only = _valid_index_document(language, example)
    totals_only["tests"] = []
    problems += _expect_refusal("service with counts but no per-test records", _plant_index(root / "totals.json", totals_only), "per-test result")

    suite_failed = _valid_index_document(language, example)
    suite_failed["services"] = [{
        "name": _SELF_TEST_SERVICE,
        "counts": {"passed": 1, "failed": 0, "errors": 0, "skipped": 0, "suite_failures": 1},
    }]
    problems += _expect_refusal("spec file that never ran", _plant_index(root / "suite.json", suite_failed), _SUITE_FAILURES_KEY)

    duplicate = _valid_index_document(language, example)
    duplicate["services"] = [{
        "name": _SELF_TEST_SERVICE,
        "counts": {"passed": 2, "failed": 0, "errors": 0, "skipped": 0, "suite_failures": 0},
    }]
    duplicate["tests"] = [
        {"service": _SELF_TEST_SERVICE, "test": "test_alpha", _CASE_KEY: _planted_case("alpha"),
         "outcome": OUTCOME_PASSED},
        {"service": _SELF_TEST_SERVICE, "test": "test_alpha_again", _CASE_KEY: _planted_case("alpha"),
         "outcome": OUTCOME_FAILED},
    ]
    problems += _expect_refusal("two tests with one case id", _plant_index(root / "duplicate.json", duplicate), "carrying the case id")

    unknown = _valid_index_document(language, example)
    unknown["tests"] = [{
        "service": _SELF_TEST_SERVICE, "test": "test_alpha", _CASE_KEY: _planted_case("alpha"),
        "outcome": "self_test_undeclared_outcome",
    }]
    problems += _expect_refusal("outcome outside the vocabulary", _plant_index(root / "unknown.json", unknown), "expected one of")

    other_project = _valid_index_document(_SELF_TEST_LANGUAGE_B, example)
    problems += _expect_refusal("index written for another language", _plant_index(root / "other.json", other_project), "another project")
    return problems


def _self_test_latest_run(scratch: Path) -> list[str]:
    """The newest run directory is the one read, and a newest run that wrote no index is
    refused rather than replaced by an older run's verdict."""
    problems: list[str] = []
    example = f"{_SELF_TEST_EXAMPLE}_latest"
    root = scratch / "latest"
    languages = [_SELF_TEST_LANGUAGE_A]
    _plant_unit_run(root, _SELF_TEST_LANGUAGE_A, example, _SELF_TEST_STAMP, {"alpha": OUTCOME_PASSED}, jest=False)
    newer = _plant_unit_run(root, _SELF_TEST_LANGUAGE_A, example, _SELF_TEST_NEWER_STAMP, {"alpha": OUTCOME_FAILED}, jest=False)
    found = discover_suite_indices(root, languages, {}, [example])
    if [dict(s.outcomes) for s in found] != [{_planted("alpha"): OUTCOME_FAILED}]:
        problems.append(f"the newest run was not the one read: {[dict(s.outcomes) for s in found]}")
    (newer / INDEX_FILENAME).unlink()
    try:
        discover_suite_indices(root, languages, {}, [example])
        problems.append("a newest run with no index.json was replaced by an older run's index")
    except MalformedSuiteIndexError as exc:
        if INDEX_FILENAME not in str(exc):
            problems.append(f"the refusal does not name the missing {INDEX_FILENAME}: {exc}")
    return problems


class _CollectingHandler(logging.Handler):
    """A log handler that keeps every formatted message, so a self-test can assert on the
    report the gate printed."""

    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def _run_planted_gate(
    scratch: Path,
    name: str,
    corpus: Mapping[str, tuple[Mapping[str, str], Mapping[str, str]]],
    limit: int,
    unidentified_in_a: Sequence[str] = (),
) -> tuple[int, list[str]]:
    """Plant *corpus* under ``scratch/name``, run the real entry point over it, and return
    its exit code and everything it logged (kept off the console). *unidentified_in_a*
    adds language A tests that record no case id to every planted example."""
    root = scratch / name
    root.mkdir()
    for example, (cases_a, cases_b) in corpus.items():
        _plant_unit_run(
            root, _SELF_TEST_LANGUAGE_A, example, _SELF_TEST_STAMP, cases_a,
            jest=False, unidentified=unidentified_in_a,
        )
        _plant_unit_run(root, _SELF_TEST_LANGUAGE_B, example, _SELF_TEST_STAMP, cases_b, jest=True)
    handler = _CollectingHandler()
    propagate, level = logger.propagate, logger.level
    logger.addHandler(handler)
    logger.propagate = False
    logger.setLevel(logging.INFO)
    try:
        code = check_generated_suite_parity(
            root, limit, [_SELF_TEST_LANGUAGE_A, _SELF_TEST_LANGUAGE_B], {}, list(corpus)
        )
    finally:
        logger.removeHandler(handler)
        logger.propagate = propagate
        logger.setLevel(level)
    return code, handler.messages


def _self_test_exit_codes(scratch: Path) -> list[str]:
    """The real entry point exits 0 for agreeing suites and 1 for each gap kind, names the gap
    in its report, lists no more than the list limit, and exits 2 over an empty corpus."""
    problems: list[str] = []
    both = {"alpha": OUTCOME_PASSED}

    code, messages = _run_planted_gate(scratch, "agree", {_SELF_TEST_EXAMPLE: (both, dict(both))}, 10)
    if code != EXIT_OK or not any(m.startswith("GENERATED-SUITE PARITY GATE PASSED") for m in messages):
        problems.append(f"agreeing suites exited {code}, expected {EXIT_OK}: {messages}")

    planted = {
        "role": (
            {"alpha": OUTCOME_PASSED, "beta": OUTCOME_PASSED}, both,
            "GENERATED-SUITE ROLE GAP", f"test={_planted('beta')} present_in=['{_SELF_TEST_LANGUAGE_A}'] "
            f"absent_from=['{_SELF_TEST_LANGUAGE_B}']",
        ),
        "behaviour": (
            both, {"alpha": OUTCOME_FAILED},
            "GENERATED-SUITE BEHAVIOUR GAP", f"test={_planted('alpha')}",
        ),
        "skip": (
            both, {"alpha": OUTCOME_SKIPPED},
            "GENERATED-SUITE SKIP GAP", f"test={_planted('alpha')}",
        ),
    }
    for name, (cases_a, cases_b, headline, detail) in planted.items():
        code, messages = _run_planted_gate(scratch, name, {_SELF_TEST_EXAMPLE: (cases_a, cases_b)}, 10)
        if code != EXIT_FAIL:
            problems.append(f"a planted {name} gap exited {code}, expected {EXIT_FAIL}")
        if not any(m.startswith(headline) for m in messages):
            problems.append(f"the {name} gap report has no {headline!r} line: {messages}")
        if not any(detail in m for m in messages):
            problems.append(f"the {name} gap report does not name {detail!r}: {messages}")

    code, messages = _run_planted_gate(
        scratch, "unidentified", {_SELF_TEST_EXAMPLE: (both, dict(both))}, 10, ("test_unmarked",)
    )
    if code != EXIT_FAIL:
        problems.append(f"a planted unidentified test exited {code}, expected {EXIT_FAIL}")
    if not any(m.startswith("GENERATED-SUITE UNIDENTIFIED TEST") for m in messages):
        problems.append(f"the unidentified test report has no headline: {messages}")
    if not any(f"{_SELF_TEST_PYTEST_CLASS}::test_unmarked" in m for m in messages):
        problems.append(f"the unidentified test report does not name the test: {messages}")

    many = {"alpha": OUTCOME_PASSED, "beta": OUTCOME_PASSED, "gamma": OUTCOME_PASSED}
    _, messages = _run_planted_gate(scratch, "limit", {_SELF_TEST_EXAMPLE: (many, {})}, 1)
    listed = [m for m in messages if m.strip().startswith("test=")]
    if len(listed) != 1 or not any("and 2 more" in m for m in messages):
        problems.append(f"--list-limit 1 over 3 role gaps listed {len(listed)} and summarized: {messages}")

    code, messages = _run_planted_gate(scratch, "empty", {}, 10)
    if code != EXIT_USAGE:
        problems.append(f"an empty corpus exited {code}, expected {EXIT_USAGE}: {messages}")
    return problems


#: Self-test cases that need no files: ``(label, case)``. Each case returns its problems.
_IN_MEMORY_CASES: Final[tuple[tuple[str, Callable[[], list[str]]], ...]] = (
    (
        "role gap: a planted test present in one language only is reported as "
        "exactly that RoleGap",
        _self_test_role_gap,
    ),
    (
        "behaviour gap: a planted test passing in one language and failing in the other "
        "is reported as exactly that BehaviourGap",
        _self_test_behaviour_gap,
    ),
    (
        "non-vacuity: a matching pair (identical names and outcomes) reports zero gaps "
        "of any kind",
        _self_test_matching_pair,
    ),
    (
        "skip category: a skip against a run is its own SkipGap, never folded into role "
        "or behaviour gaps",
        _self_test_skip_category,
    ),
    (
        "unidentified test: a test carrying no case id is its own reported category, never "
        "a role gap and never dropped",
        _self_test_unidentified,
    ),
    (
        "language floor: fewer than two registered languages is refused, and so is a "
        "single-language group",
        _self_test_language_floor,
    ),
    (
        "outcome vocabulary: every outcome the index writer records is classified",
        _self_test_outcome_vocabulary,
    ),
)

#: Self-test cases that plant a synthetic corpus under a scratch root: ``(label, case)``.
_SCRATCH_CASES: Final[tuple[tuple[str, Callable[[Path], list[str]]], ...]] = (
    (
        "discovery: indices written by the real writer (pytest JUnit and Jest JSON) are "
        "read, grouped and compared by case id while the two frameworks name each test "
        "differently",
        _self_test_discovery,
    ),
    (
        "refusal: a language with no index for an example another language has one for "
        "is refused, naming the pair; a parked pair is not missing",
        _self_test_missing_index,
    ),
    (
        "refusal: an index predating per-test records or case ids, totals-only, holding a "
        "never-run spec file, two tests with one case id, an unknown outcome, or another "
        "project's is refused",
        _self_test_index_refusals,
    ),
    (
        "latest run: the newest run is read, and a newest run with no index is refused",
        _self_test_latest_run,
    ),
    (
        "exit codes: agreeing suites exit 0; a planted role, behaviour or skip gap or an "
        "unidentified test exits 1 and is named in the report; --list-limit bounds the "
        "listing; an empty corpus exits 2",
        _self_test_exit_codes,
    ),
)


def run_self_test() -> list[str]:
    """Prove the comparator, reader and refusals are non-vacuous before any real comparison
    is trusted. Logs one ``[OK]`` / ``[FAIL]`` line per property.

    Returns:
        Problem descriptions; empty means the gate is sound.
    """
    problems: list[str] = []
    for label, case in _IN_MEMORY_CASES:
        problems += _report_case(label, case())
    scratch = _SELF_TEST_SCRATCH_ROOT / str(os.getpid())
    if scratch.exists():
        shutil.rmtree(scratch)
    scratch.mkdir(parents=True)
    # Planting a corpus runs the real index writer, which logs every file it indexes; keep
    # that out of the self-test's own [OK]/[FAIL] lines.
    writer_logger = logging.getLogger(GeneratedTestLogWriter.__module__)
    writer_level = writer_logger.level
    writer_logger.setLevel(logging.WARNING)
    try:
        for label, scratch_case in _SCRATCH_CASES:
            problems += _report_case(label, scratch_case(scratch))
    finally:
        writer_logger.setLevel(writer_level)
        shutil.rmtree(scratch, ignore_errors=True)
    return problems


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _non_negative_int(raw: str) -> int:
    """argparse type: a count of at least zero.

    Raises:
        argparse.ArgumentTypeError: *raw* is not an integer, or is negative.
    """
    try:
        value = int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected a whole number, got {raw!r}") from exc
    if value < 0:
        raise argparse.ArgumentTypeError(f"expected a number >= 0, got {value}")
    return value


def _parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Generated-suite parity gate: for every (example, runtime, provider) "
            "unit-tested in >= 2 registered languages, the set of tests each language's "
            "generated suite ran must agree and so must which of them passed. Reads the "
            "index.json files run_complete.py already wrote -- generates and runs nothing."
        ),
    )
    parser.add_argument("--debug", action="store_true", help="Enable DEBUG logging")
    parser.add_argument(
        "--generated-root",
        type=Path,
        default=DEFAULT_GENERATED_ROOT,
        help=(
            "The generate.ps1 output base holding <language>/<runtime>/<provider>/<example> "
            f"trees (default: {DEFAULT_GENERATED_ROOT})"
        ),
    )
    parser.add_argument(
        "--list-limit",
        type=_non_negative_int,
        default=_DEFAULT_LIST_LIMIT,
        help=(
            "Gaps listed per (group, kind) before the rest are summarized "
            f"(default: {_DEFAULT_LIST_LIMIT})"
        ),
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run only the non-vacuity self-test and skip the real comparison",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point.

    Returns:
        Process exit code: 0 = every comparable group's suites agree (or a successful
        ``--self-test``), 1 = a role, behaviour or skip gap was found, 2 = the self-test
        failed, fewer than two languages are registered, the corpus is incomplete, an index
        is unusable, or no group is unit-tested in >= 2 languages.
    """
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    problems = run_self_test()
    if problems:
        logger.error("NON-VACUITY SELF-TEST FAILED -- aborting before any real comparison:")
        for problem in problems:
            logger.error("  %s", problem)
        return EXIT_USAGE
    logger.info("non-vacuity self-test: PASS")

    if args.self_test:
        return EXIT_OK

    try:
        return check_generated_suite_parity(
            args.generated_root,
            args.list_limit,
            registered_language_names(),
            load_known_non_generating(),
            registered_example_relpaths(),
        )
    except ValueError as exc:
        logger.error("%s", exc)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
