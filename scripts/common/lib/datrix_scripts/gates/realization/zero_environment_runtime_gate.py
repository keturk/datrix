#!/usr/bin/env python3
"""Zero-environment runtime census gate -- every registered language is
obligated to bake deployment-static values at generation time.

The zero-environment runtime architecture bakes every deployment-static value
a generated service needs into literal constants at generation time, so the
running service consults no environment variable. That is a portable
decision, and every registered language is obligated to it. Each language
plugin states the code idioms that spell an environment read in its own
emitted code on its ``LanguageCapabilityDeclaration``
(``zero_environment_runtime``: a member access such as ``os.environ``, an
import of an environment-reading module). This gate generates the registered
``serverless`` example once per registered language and has that language's
own conformance probes parse every emitted source file and match the idioms
on the parse tree (``LanguageConformanceProbes.idiom_occurrences``): a string
literal or a comment that spells an idiom is not a read, the same text written
as code is, and a file that does not parse stops the census instead of reading
as "no read". What the census may find is decided by the KIND of the
language's entry in ``scripts/config/zero-environment-runtime-baseline.json``
-- nothing else selects the rule:

* ``reviewed_exemptions`` -- every emitted file that reads the environment is
  listed by its path relative to the generated root, with a written reason,
  as a justification of that specific read. An unlisted read and a stale
  entry are both violations. A registered language with NO entry is held to
  this kind with an empty list: it may carry no environment read, so adding a
  language needs no edit here.
* ``pinned_count`` -- a decrease-only count of environment-reading emitted
  files, for a language that delivers runtime facts through the environment
  by design. The count may fall (``--update-baseline`` lowers it) and may
  never rise; the writer refuses to raise it.

A registered language that states no idioms, or supplies no conformance
probes to read its tree with, fails the gate, naming it, and a baseline entry
naming a language that is not registered is stale and fails.

The language set is derived from the installed ``datrix.languages`` entry
points at runtime, never a hardcoded list, each language's idioms come from
its own declaration and each tree is read through that language's own probes,
never a table in this script. Emitted test harnesses count too, because a
harness that reads the environment is still emitted into the generated
project -- a ``reviewed_exemptions`` language lists them as exemptions with
that reason.

Runs a built-in non-vacuity self-test on every invocation: this module names
no registered target (``datrix_scripts.registered_targets.self_test_gate_names_no_target``),
the census over a planted idiom reading (exactly the files it reports, asked
for exactly the declared idioms, an unparseable file raising through), the
comparator against both entry kinds (missing exemption, stale exemption,
count over and under the pin, the same census passing under one kind and
failing under the other, no entry), the entry-kind validation, the baseline
writer (lowers a pin, refuses to raise one, carries exemptions through), and
every registered language supplying a declaration and a probe reading. The
census run itself requires at least one read the committed baseline lists as
a reviewed exemption: a census that sees none of them is broken, not clean.

Repo-level validation script (per the datrix showcase boundary -- no pytest
suite lives in datrix).

This module is what ``gates/realization/zero-environment-runtime-gate.ps1``
(and its ``.sh`` twin) runs, in gate mode (``datrix_scripts.gate_log.run_as_gate``):
the last line is the ``[GATE] zero-environment-runtime PASSED|FAILED exit=<n>
log=<path>`` verdict.

Usage:
    .\\scripts\\gates\\realization\\zero-environment-runtime-gate.ps1
    .\\scripts\\gates\\realization\\zero-environment-runtime-gate.ps1 -Dbg
    .\\scripts\\gates\\realization\\zero-environment-runtime-gate.ps1 -SelfTest
    .\\scripts\\gates\\realization\\zero-environment-runtime-gate.ps1 -UpdateBaseline
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from datrix_codegen_kernel.parity.conformance_probes import (
    IdiomOccurrence,
    UnparseableGeneratedFileError,
    language_conformance_probes,
)
from datrix_common.errors.plugin import PluginNotFoundError, PluginValidationError
from datrix_common.plugin._capability_declarations import declaration_for_language
from datrix_common.plugin.code_idiom import CodeIdiom, MemberAccessIdiom
from datrix_common.plugin.language_capability import (
    ZeroEnvironmentRuntimeDeclaration,
)

from datrix_scripts.gate_harness import EXIT_PASS, WRAPPER_DEBUG_FLAG, report_condition
from datrix_scripts.gate_log import gate_child, run_as_gate
from datrix_scripts.generated_example import generate_example
from datrix_scripts.paths import SHOWCASE_DIR, WORKSPACE_DIR
from datrix_scripts.registered_targets import (
    registered_language_names,
    report_gate_names_no_target,
)
from datrix_scripts.test.wrappers import REALIZATION_GATES_DIR, run_self_test, self_test_check
from datrix_scripts.test_projects import get_project_by_name

logger = logging.getLogger(__name__)

GATE: Final = "zero-environment-runtime"
MODULE: Final = "datrix_scripts.gates.realization.zero_environment_runtime_gate"
WRAPPER: Final = "zero-environment-runtime-gate"

DATRIX_DIR: Final[Path] = SHOWCASE_DIR
BASELINE_PATH: Final[Path] = (
    DATRIX_DIR / "scripts" / "config" / "zero-environment-runtime-baseline.json"
)
#: The registered example every language's census generates: it emits the
#: service runtime, the settings module, the container serverless entrypoint
#: and the emitted test harnesses.
EXAMPLE_NAME: Final[str] = "serverless"
#: Generation scratch space, outside every package repository, cleaned per run.
_GATE_OUTPUT_ROOT: Final[Path] = WORKSPACE_DIR / ".tmp" / "zero-environment-runtime"

_MIN_LANGUAGES_FOR_COMPARISON: Final[int] = 2

EXIT_OK: Final[int] = 0
EXIT_FAIL: Final[int] = 1
EXIT_USAGE: Final[int] = 2

#: The two baseline entry kinds -- a closed set -- and the one payload key each
#: kind owns. The kind alone selects which rule a language's census is held to.
ENTRY_KIND_EXEMPTIONS: Final[str] = "reviewed_exemptions"
ENTRY_KIND_PINNED_COUNT: Final[str] = "pinned_count"
_ENTRY_KIND_KEY: Final[str] = "kind"
_EXEMPTIONS_KEY: Final[str] = "exemptions"
_PINNED_COUNT_KEY: Final[str] = "pinned_count"
_EXEMPTION_PATH_KEY: Final[str] = "path"
_EXEMPTION_REASON_KEY: Final[str] = "reason"
_ENTRY_PAYLOAD_KEYS: Final[Mapping[str, str]] = {
    ENTRY_KIND_EXEMPTIONS: _EXEMPTIONS_KEY,
    ENTRY_KIND_PINNED_COUNT: _PINNED_COUNT_KEY,
}

#: The ``_comment`` block ``--update-baseline`` writes; the committed file
#: carries the same text.
_BASELINE_COMMENT: Final[tuple[str, ...]] = (
    "Zero-environment runtime census, per registered datrix.languages package.",
    "Each language's tree is the registered 'serverless' example generated for it,",
    "read through the language's own conformance probes. Every language entry",
    "carries a 'kind'. reviewed_exemptions: every emitted file that reads the",
    "environment is listed by its path relative to the generated root, with a",
    "written reason (hand-authored; an unlisted read and a stale entry both fail).",
    "pinned_count: a decrease-only count of environment-reading emitted files, for",
    "a language that delivers runtime facts through the environment by design; only",
    "-UpdateBaseline writes it, and never upward. A language with no entry is held",
    "to reviewed_exemptions with an empty list.",
)

#: Reads the occurrences of the given idioms off the parse trees of a generated
#: root: a language's ``LanguageConformanceProbes.idiom_occurrences``.
IdiomReader = Callable[[Path, Sequence[CodeIdiom]], tuple[IdiomOccurrence, ...]]

_SELF_TEST_LANGUAGE: Final[str] = "self_test_zero_env_lang"
_SELF_TEST_IDIOM: Final[MemberAccessIdiom] = MemberAccessIdiom(("SELF_TEST_ENV", "read"))
_SELF_TEST_READING_PATH: Final[str] = "svc/src/reads.src"
_SELF_TEST_HARNESS_PATH: Final[str] = "svc/tests/harness.src"


@dataclass(frozen=True)
class LanguageCensus:
    """The environment-reading emitted files of one language's generated tree."""

    language: str
    reads: frozenset[str]


@dataclass(frozen=True)
class Exemption:
    """One reviewed environment read a language's generated tree carries on purpose."""

    path: str
    reason: str


# ---------------------------------------------------------------------------
# Census
# ---------------------------------------------------------------------------


def census_language(
    language: str, generated_root: Path, idioms: Sequence[CodeIdiom], read: IdiomReader
) -> LanguageCensus:
    """Every emitted file under *generated_root* an environment-read idiom occurs in, as
    the posix path relative to the root (the key the baseline's exemptions use).

    Raises:
        UnparseableGeneratedFileError: An emitted source file does not parse (raised by *read*).
    """
    occurrences = read(generated_root, idioms)
    for occurrence in occurrences:
        logger.debug(
            "READ language=%s path=%s line=%d text=%r",
            language,
            occurrence.relative_path,
            occurrence.line,
            occurrence.text,
        )
    return LanguageCensus(
        language=language,
        reads=frozenset(occurrence.relative_path for occurrence in occurrences),
    )


def idiom_reader(language: str) -> IdiomReader:
    """*language*'s own parse-tree reading of code idioms.

    Raises:
        ValueError: *language* is not registered or declares no (or incomplete) conformance probes.
    """
    try:
        return language_conformance_probes(language).idiom_occurrences
    except (PluginNotFoundError, PluginValidationError) as exc:
        raise ValueError(
            f"{language}: supplies no conformance probes to read its generated tree with ({exc}). "
            f"Fix: declare complete conformance probes on the language plugin."
        ) from exc


def example_source() -> Path:
    """The ``system.dtrx`` of the registered example every census generates.

    Raises:
        ValueError: The example is not in the example registry.
    """
    project = get_project_by_name(EXAMPLE_NAME)
    if project is None:
        raise ValueError(
            f"The example {EXAMPLE_NAME!r} is not in scripts/config/test-projects.json, so no "
            f"language's tree can be generated. Fix: restore its registry entry."
        )
    return DATRIX_DIR / str(project["path"])


# ---------------------------------------------------------------------------
# Baseline
# ---------------------------------------------------------------------------


def load_baseline() -> dict[str, dict[str, object]]:
    """The per-language baseline entries, keyed by registered language name.

    Raises:
        ValueError: If the file exists but is not an object carrying a
            ``languages`` object whose every value is an object.
    """
    if not BASELINE_PATH.exists():
        return {}
    data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    languages = data["languages"] if isinstance(data, dict) and "languages" in data else None
    if not isinstance(languages, dict):
        raise ValueError(
            f"Malformed {BASELINE_PATH}: expected an object with a 'languages' "
            f"object keyed by registered language name."
        )
    for language, entry in languages.items():
        if not isinstance(entry, dict):
            raise ValueError(
                f"{BASELINE_PATH}: languages.{language} must be an object carrying a "
                f"'{_ENTRY_KIND_KEY}' and its payload; got {entry!r}."
            )
    return languages


def entry_kind(language: str, entry: Mapping[str, object]) -> str:
    """The kind of *language*'s baseline entry, validated against its payload.

    Raises:
        ValueError: If ``kind`` is absent or not one of the two valid kinds,
            the entry carries the payload key the OTHER kind owns, the entry
            lacks the payload key its own kind owns, or it carries any key
            beyond the kind and its payload.
    """
    where = f"{BASELINE_PATH}: languages.{language}"
    valid = sorted(_ENTRY_PAYLOAD_KEYS)
    if _ENTRY_KIND_KEY not in entry:
        raise ValueError(
            f"{where} has no '{_ENTRY_KIND_KEY}'. Valid kinds: {valid}. Fix: add "
            f"'{_ENTRY_KIND_KEY}': '{ENTRY_KIND_EXEMPTIONS}' (every environment-reading emitted file "
            f"listed with a written reason) or '{ENTRY_KIND_PINNED_COUNT}' (a decrease-only count, "
            f"for a language that delivers runtime facts through the environment by design)."
        )
    kind = entry[_ENTRY_KIND_KEY]
    if not isinstance(kind, str) or kind not in _ENTRY_PAYLOAD_KEYS:
        raise ValueError(
            f"{where} has unknown kind {kind!r}. Valid kinds: {valid}. Fix: use one of them."
        )
    payload_key = _ENTRY_PAYLOAD_KEYS[kind]
    for other_kind, other_key in _ENTRY_PAYLOAD_KEYS.items():
        if other_kind != kind and other_key in entry:
            raise ValueError(
                f"{where} is kind '{kind}' but carries '{other_key}', which belongs to kind "
                f"'{other_kind}'. Fix: carry only '{payload_key}', or change the kind."
            )
    if payload_key not in entry:
        raise ValueError(
            f"{where} is kind '{kind}' but carries no '{payload_key}'. Fix: add the "
            f"'{payload_key}' payload its kind owns."
        )
    unknown = sorted(set(entry) - {_ENTRY_KIND_KEY, payload_key})
    if unknown:
        raise ValueError(
            f"{where} carries unrecognized key(s) {unknown}. Fix: keep only "
            f"'{_ENTRY_KIND_KEY}' and '{payload_key}'."
        )
    return kind


def _carries_text(item: Mapping[str, object], key: str) -> bool:
    """Whether *item* carries a non-blank string under *key*."""
    return key in item and isinstance(item[key], str) and bool(str(item[key]).strip())


def parse_exemptions(language: str, entry: Mapping[str, object]) -> tuple[Exemption, ...]:
    """The reviewed exemption list of a ``reviewed_exemptions`` entry.

    Raises:
        ValueError: If the entry has no ``exemptions`` list, an item lacks a
            path or a non-empty reason, carries any other key, or a path is listed twice.
    """
    raw = entry[_EXEMPTIONS_KEY] if _EXEMPTIONS_KEY in entry else None
    if not isinstance(raw, list):
        raise ValueError(
            f"{BASELINE_PATH}: languages.{language} is a '{ENTRY_KIND_EXEMPTIONS}' entry, so it "
            f"must carry an '{_EXEMPTIONS_KEY}' list (each item: path + reason). Fix: add the "
            f"list, empty if the language carries no environment read."
        )
    seen: set[str] = set()
    exemptions: list[Exemption] = []
    for item in raw:
        if not isinstance(item, dict) or not _carries_text(item, _EXEMPTION_PATH_KEY):
            raise ValueError(
                f"{BASELINE_PATH}: languages.{language}.exemptions item {item!r} "
                f"has no '{_EXEMPTION_PATH_KEY}'. Fix: name the emitted file by its path relative "
                f"to the generated root."
            )
        path = str(item[_EXEMPTION_PATH_KEY])
        if not _carries_text(item, _EXEMPTION_REASON_KEY):
            raise ValueError(
                f"{BASELINE_PATH}: languages.{language}.exemptions[{path!r}] "
                f"has no written reason. An exemption without a reason is silence. "
                f"Fix: state why this file reads the environment."
            )
        unknown = sorted(set(item) - {_EXEMPTION_PATH_KEY, _EXEMPTION_REASON_KEY})
        if unknown:
            raise ValueError(
                f"{BASELINE_PATH}: languages.{language}.exemptions[{path!r}] carries unrecognized "
                f"key(s) {unknown}. Fix: keep only '{_EXEMPTION_PATH_KEY}' and '{_EXEMPTION_REASON_KEY}'."
            )
        if path in seen:
            raise ValueError(
                f"{BASELINE_PATH}: languages.{language}.exemptions lists "
                f"{path!r} twice. Fix: keep one entry."
            )
        seen.add(path)
        exemptions.append(Exemption(path=path, reason=str(item[_EXEMPTION_REASON_KEY])))
    return tuple(exemptions)


def parse_pinned_count(language: str, entry: Mapping[str, object]) -> int:
    """The pinned count of a ``pinned_count`` entry.

    Raises:
        ValueError: If the entry has no non-negative integer ``pinned_count``.
    """
    count = entry[_PINNED_COUNT_KEY] if _PINNED_COUNT_KEY in entry else None
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise ValueError(
            f"{BASELINE_PATH}: languages.{language} is a '{ENTRY_KIND_PINNED_COUNT}' entry, so it "
            f"must carry a non-negative integer '{_PINNED_COUNT_KEY}'. Fix: run with "
            f"--update-baseline to lower it to the live count, or write the count by hand."
        )
    return count


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


def _exemption_problems(census: LanguageCensus, exemptions: tuple[Exemption, ...]) -> list[str]:
    problems: list[str] = []
    exempted = {exemption.path for exemption in exemptions}
    for path in sorted(census.reads - exempted):
        problems.append(
            f"{census.language}: {path} reads the environment but carries no reviewed "
            f"exemption. Fix: bake the value at generation time, or add an exemption with a "
            f"written reason to {BASELINE_PATH} (a language that delivers runtime facts through "
            f"the environment by design carries a '{ENTRY_KIND_PINNED_COUNT}' entry at its live "
            f"count instead)."
        )
    for path in sorted(exempted - census.reads):
        problems.append(
            f"{census.language}: exemption {path} names an emitted file with no "
            f"environment read (or no such file in the generated '{EXAMPLE_NAME}' example). "
            f"Fix: remove the stale entry from {BASELINE_PATH}."
        )
    return problems


def _pinned_count_problems(census: LanguageCensus, pinned: int) -> list[str]:
    live = len(census.reads)
    if live > pinned:
        return [
            f"{census.language}: {live} emitted file(s) read the environment, "
            f"above the pinned decrease-only count of {pinned}. A new environment read "
            f"appeared. Fix: bake the new value at generation time instead."
        ]
    if live < pinned:
        logger.info(
            "%s: %d environment-reading emitted file(s), below the pinned %d -- "
            "run with --update-baseline to lower the pin.",
            census.language,
            live,
            pinned,
        )
    return []


def evaluate(census: LanguageCensus, entry: Mapping[str, object] | None) -> list[str]:
    """Every way *census* disagrees with its language's baseline entry.

    The entry's kind alone selects the rule: ``reviewed_exemptions`` (or no
    entry, an empty list) holds the census to its reviewed exemption list;
    ``pinned_count`` holds it to a decrease-only count.
    """
    if entry is None:
        return _exemption_problems(census, ())
    if entry_kind(census.language, entry) == ENTRY_KIND_PINNED_COUNT:
        return _pinned_count_problems(census, parse_pinned_count(census.language, entry))
    return _exemption_problems(census, parse_exemptions(census.language, entry))


def stale_entry_problems(
    baseline: Mapping[str, Mapping[str, object]], registered: frozenset[str]
) -> list[str]:
    """A baseline entry naming a language that is not registered is stale."""
    return [
        f"{BASELINE_PATH}: languages.{language} names a language that is not registered "
        f"(registered: {sorted(registered)}). Fix: remove the stale entry."
        for language in sorted(set(baseline) - registered)
    ]


def _listed_exemptions(baseline: Mapping[str, Mapping[str, object]]) -> dict[str, frozenset[str]]:
    """Language -> the emitted paths its baseline entry lists as reviewed
    exemptions, for every ``reviewed_exemptions`` entry that lists at least one."""
    listed: dict[str, frozenset[str]] = {}
    for language, entry in sorted(baseline.items()):
        if entry_kind(language, entry) != ENTRY_KIND_EXEMPTIONS:
            continue
        paths = frozenset(exemption.path for exemption in parse_exemptions(language, entry))
        if paths:
            listed[language] = paths
    return listed


def live_read_problems(
    censuses: Mapping[str, LanguageCensus], baseline: Mapping[str, Mapping[str, object]]
) -> list[str]:
    """The live census must find at least one read the committed baseline lists as a
    reviewed exemption -- a census that sees none of them is broken, not clean. The
    reads come from the baseline, never a language or path pinned in this module."""
    listed = _listed_exemptions(baseline)
    found = [
        f"{language}:{path}"
        for language, census in sorted(censuses.items())
        for path in sorted(census.reads & listed.get(language, frozenset()))
    ]
    if found or not listed:
        return []
    return [
        f"the census read none of the {sum(len(paths) for paths in listed.values())} environment "
        f"read(s) {BASELINE_PATH} lists as reviewed exemptions. A census that sees none of them is "
        f"broken, not clean. Fix: the languages' idiom reading (idiom_occurrences) or the declared "
        f"idioms."
    ]


def summary_line(census: LanguageCensus, entry: Mapping[str, object] | None, problem_count: int) -> str:
    """One census line per language, naming the entry kind that selected its rule."""
    live = len(census.reads)
    if entry is not None and entry_kind(census.language, entry) == ENTRY_KIND_PINNED_COUNT:
        pinned = parse_pinned_count(census.language, entry)
        comparison = "<=" if live <= pinned else ">"
        return (
            f"language={census.language} entry_kind={ENTRY_KIND_PINNED_COUNT}: {live} {comparison} "
            f"pinned {pinned}, {problem_count} problem(s)"
        )
    exemptions = () if entry is None else parse_exemptions(census.language, entry)
    return (
        f"language={census.language} entry_kind={ENTRY_KIND_EXEMPTIONS}: {live} "
        f"environment-reading emitted file(s), {len(exemptions)} reviewed exemption(s), "
        f"{problem_count} problem(s)"
    )


def _require_min_languages(language_names: frozenset[str]) -> None:
    if len(language_names) < _MIN_LANGUAGES_FOR_COMPARISON:
        logger.error(
            "Zero-environment census requires at least %d registered 'datrix.languages' "
            "packages; got %d (%s).",
            _MIN_LANGUAGES_FOR_COMPARISON,
            len(language_names),
            sorted(language_names),
        )
        raise SystemExit(EXIT_USAGE)


def _declaration_for(language: str) -> ZeroEnvironmentRuntimeDeclaration | None:
    return declaration_for_language(language).zero_environment_runtime


def _undeclared_problem(language: str) -> str:
    return (
        f"{language}: states no zero_environment_runtime idioms on its "
        f"LanguageCapabilityDeclaration, so its generated tree cannot be censused. Every "
        f"registered language is obligated to state the code idioms that spell an "
        f"environment read in its own emitted code. Fix: declare a "
        f"ZeroEnvironmentRuntimeDeclaration naming them."
    )


def scan_all_registered_languages() -> tuple[dict[str, LanguageCensus], list[str]]:
    """Generate the example for, and census, every registered language; a language
    that states no idioms or supplies no probe reading is reported, never skipped.

    Raises:
        ValueError: The example is not registered.
        RuntimeError: Generating the example for a language failed.
        UnparseableGeneratedFileError: An emitted source file does not parse.
    """
    language_names = registered_language_names()
    _require_min_languages(language_names)
    source = example_source()
    shutil.rmtree(_GATE_OUTPUT_ROOT, ignore_errors=True)
    censuses: dict[str, LanguageCensus] = {}
    unread: list[str] = []
    for language in sorted(language_names):
        declaration = _declaration_for(language)
        if declaration is None:
            unread.append(_undeclared_problem(language))
            continue
        try:
            read = idiom_reader(language)
        except ValueError as exc:
            unread.append(str(exc))
            continue
        generated = generate_example(language, source, _GATE_OUTPUT_ROOT / language)
        censuses[language] = census_language(language, generated, declaration.environment_read_idioms, read)
    return censuses, unread


# ---------------------------------------------------------------------------
# Baseline writer
# ---------------------------------------------------------------------------


def write_baseline(
    censuses: Mapping[str, LanguageCensus],
    existing: Mapping[str, Mapping[str, object]],
    path: Path = BASELINE_PATH,
) -> None:
    """Lower every ``pinned_count`` entry to its live census.

    The ratchet is decrease-only, so a writer that could raise a pin would
    defeat it: a live count above the existing pin raises. Entries of kind
    ``reviewed_exemptions`` are hand-authored and carried over untouched -- the
    writer never invents a reason -- and a pinned entry whose language has no
    census is carried over untouched. Every entry keeps its ``kind``.

    Raises:
        ValueError: A ``pinned_count`` entry's live count is above its pin, or
            an existing entry is malformed.
    """
    languages: dict[str, object] = {}
    for language in sorted(existing):
        entry = existing[language]
        if entry_kind(language, entry) != ENTRY_KIND_PINNED_COUNT or language not in censuses:
            languages[language] = entry
            continue
        live = len(censuses[language].reads)
        pinned = parse_pinned_count(language, entry)
        if live > pinned:
            raise ValueError(
                f"{language}: {live} emitted file(s) read the environment, above the pinned "
                f"decrease-only count of {pinned}; --update-baseline refuses to raise a pin. "
                f"Fix: bake the new value at generation time instead."
            )
        languages[language] = {_ENTRY_KIND_KEY: ENTRY_KIND_PINNED_COUNT, _PINNED_COUNT_KEY: live}
    payload = {"_comment": list(_BASELINE_COMMENT), "languages": languages}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Non-vacuity self-test
# ---------------------------------------------------------------------------


def _raises(call: Callable[[], object], error: type[Exception] = ValueError) -> bool:
    """Whether calling *call* raises *error*."""
    try:
        call()
    except error:
        return True
    return False


def _self_test_census(tmp_root: Path) -> tuple[bool, LanguageCensus]:
    """The census reports exactly the files the language's reading found -- one file
    however many reads it holds -- and asks the reading for exactly the declared idioms;
    a file the reading cannot parse raises through instead of reading as no read."""
    asked: list[tuple[CodeIdiom, ...]] = []

    def planted_reader(generated_root: Path, idioms: Sequence[CodeIdiom]) -> tuple[IdiomOccurrence, ...]:
        asked.append(tuple(idioms))
        return (
            IdiomOccurrence(_SELF_TEST_IDIOM, _SELF_TEST_READING_PATH, 1, 1, "SELF_TEST_ENV.read"),
            IdiomOccurrence(_SELF_TEST_IDIOM, _SELF_TEST_READING_PATH, 4, 4, "SELF_TEST_ENV.read"),
            IdiomOccurrence(_SELF_TEST_IDIOM, _SELF_TEST_HARNESS_PATH, 2, 2, "SELF_TEST_ENV.read"),
        )

    def unparseable_reader(generated_root: Path, idioms: Sequence[CodeIdiom]) -> tuple[IdiomOccurrence, ...]:
        raise UnparseableGeneratedFileError(_SELF_TEST_READING_PATH, "planted syntax error")

    census = census_language(_SELF_TEST_LANGUAGE, tmp_root, (_SELF_TEST_IDIOM,), planted_reader)
    ok = report_condition(
        census.reads == frozenset({_SELF_TEST_READING_PATH, _SELF_TEST_HARNESS_PATH})
        and asked == [(_SELF_TEST_IDIOM,)],
        "planted reading: exactly the two files it found are reads, and it was asked for exactly the declared idiom",
    )
    ok &= report_condition(
        _raises(
            lambda: census_language(_SELF_TEST_LANGUAGE, tmp_root, (_SELF_TEST_IDIOM,), unparseable_reader),
            UnparseableGeneratedFileError,
        ),
        "an emitted file the reading cannot parse raises through the census, never reads as no read",
    )
    reading_only = LanguageCensus(_SELF_TEST_LANGUAGE, frozenset({_SELF_TEST_READING_PATH}))
    return ok, reading_only


def _exemptions_entry(*paths: str) -> dict[str, object]:
    return {
        _ENTRY_KIND_KEY: ENTRY_KIND_EXEMPTIONS,
        _EXEMPTIONS_KEY: [{_EXEMPTION_PATH_KEY: path, _EXEMPTION_REASON_KEY: "planted"} for path in paths],
    }


def _pinned_entry(count: int) -> dict[str, object]:
    return {_ENTRY_KIND_KEY: ENTRY_KIND_PINNED_COUNT, _PINNED_COUNT_KEY: count}


def _self_test_comparator(census: LanguageCensus) -> bool:
    clean = LanguageCensus(_SELF_TEST_LANGUAGE, frozenset())
    ok = True
    ok &= report_condition(
        evaluate(census, _exemptions_entry(_SELF_TEST_READING_PATH)) == [],
        "reviewed_exemptions + exact exemption list: no problem",
    )
    ok &= report_condition(
        len(evaluate(census, _exemptions_entry())) == 1,
        "reviewed_exemptions + missing exemption: exactly one problem",
    )
    ok &= report_condition(
        len(evaluate(census, _exemptions_entry(_SELF_TEST_READING_PATH, "svc/src/gone.src"))) == 1,
        "reviewed_exemptions + stale exemption: exactly one problem",
    )
    ok &= report_condition(
        evaluate(census, _pinned_entry(1)) == [] and evaluate(census, _pinned_entry(5)) == [],
        "pinned_count + count at or below the pin: no problem",
    )
    ok &= report_condition(
        len(evaluate(census, _pinned_entry(0))) == 1,
        "pinned_count + count above the pin: exactly one problem",
    )
    ok &= report_condition(
        len(evaluate(census, None)) == 1 and evaluate(clean, None) == [],
        "no entry + one read: exactly one problem; no entry + no read: none",
    )
    ok &= report_condition(
        evaluate(census, _pinned_entry(1)) == [] and len(evaluate(census, _exemptions_entry())) == 1,
        "the same one-read census passes against a pinned_count entry of 1 and fails against an "
        "empty reviewed_exemptions entry: the entry kind alone selects the branch",
    )
    for label, item in (
        ("without a written reason", {_EXEMPTION_PATH_KEY: "x.src", _EXEMPTION_REASON_KEY: " "}),
        ("keyed by a template instead of an emitted path", {"template": "x.j2", _EXEMPTION_REASON_KEY: "r"}),
        ("carrying an unrecognized key", {_EXEMPTION_PATH_KEY: "x.src", _EXEMPTION_REASON_KEY: "r", "line": 3}),
    ):
        ok &= report_condition(
            _raises(lambda item=item: parse_exemptions(_SELF_TEST_LANGUAGE, {_EXEMPTIONS_KEY: [item]})),
            f"an exemption {label} is rejected",
        )
    ok &= report_condition(
        len(live_read_problems({_SELF_TEST_LANGUAGE: clean}, {_SELF_TEST_LANGUAGE: _exemptions_entry("a.src")})) == 1
        and live_read_problems({_SELF_TEST_LANGUAGE: census}, {_SELF_TEST_LANGUAGE: _exemptions_entry(_SELF_TEST_READING_PATH)})
        == [],
        "a live census reading none of the listed exemptions is one problem; reading one of them is none",
    )
    return ok


def _self_test_entry_kind() -> bool:
    ok = True
    ok &= report_condition(
        entry_kind(_SELF_TEST_LANGUAGE, _exemptions_entry()) == ENTRY_KIND_EXEMPTIONS
        and entry_kind(_SELF_TEST_LANGUAGE, _pinned_entry(3)) == ENTRY_KIND_PINNED_COUNT,
        "entry_kind returns the kind of a well-formed entry of each kind",
    )
    rejected: tuple[tuple[str, dict[str, object]], ...] = (
        ("a missing kind", {_EXEMPTIONS_KEY: []}),
        ("an unknown kind", {_ENTRY_KIND_KEY: "realized", _EXEMPTIONS_KEY: []}),
        (
            "a pinned_count entry carrying exemptions",
            {**_pinned_entry(1), _EXEMPTIONS_KEY: []},
        ),
        (
            "a reviewed_exemptions entry carrying pinned_count",
            {**_exemptions_entry(), _PINNED_COUNT_KEY: 1},
        ),
        ("a pinned_count entry lacking its count", {_ENTRY_KIND_KEY: ENTRY_KIND_PINNED_COUNT}),
        ("a reviewed_exemptions entry lacking its list", {_ENTRY_KIND_KEY: ENTRY_KIND_EXEMPTIONS}),
        ("an entry carrying an unrecognized key", {**_pinned_entry(1), "reason": "planted"}),
    )
    for label, entry in rejected:
        ok &= report_condition(
            _raises(lambda entry=entry: entry_kind(_SELF_TEST_LANGUAGE, entry)),
            f"entry_kind rejects {label}",
        )
    return ok


def _self_test_stale_entries() -> bool:
    registered = frozenset({"alpha", "beta"})
    stale = stale_entry_problems({"alpha": _pinned_entry(1), "gamma": _exemptions_entry()}, registered)
    registered_only = stale_entry_problems({"alpha": _pinned_entry(1)}, registered)
    return report_condition(
        len(stale) == 1 and "gamma" in stale[0] and registered_only == [],
        "a baseline entry naming an unregistered language is one stale-entry problem; registered ones are not",
    )


def _self_test_baseline_writer(tmp_root: Path, census: LanguageCensus) -> bool:
    """The writer lowers a pinned entry to the live count, refuses to raise one,
    and carries a reviewed_exemptions entry (and a language with no census)
    through unchanged, every entry keeping its kind."""
    ok = True
    target = tmp_root / "written-baseline.json"
    exemptions = _exemptions_entry("svc/src/a.src", "svc/src/b.src")
    untouched_pin = _pinned_entry(9)
    existing: dict[str, dict[str, object]] = {
        "self_exemptions": exemptions,
        "self_pinned": _pinned_entry(4),
        "self_uncensused": untouched_pin,
    }
    censuses = {
        "self_exemptions": census,
        "self_pinned": LanguageCensus("self_pinned", census.reads),
    }
    write_baseline(censuses, existing, target)
    written = json.loads(target.read_text(encoding="utf-8"))["languages"]
    ok &= report_condition(
        written["self_pinned"] == _pinned_entry(1),
        "write_baseline lowers a pinned_count entry from 4 to the live count 1, keeping its kind",
    )
    ok &= report_condition(
        json.dumps(written["self_exemptions"]) == json.dumps(exemptions)
        and json.dumps(written["self_uncensused"]) == json.dumps(untouched_pin),
        "write_baseline carries a reviewed_exemptions entry and an uncensused pinned entry through unchanged",
    )
    untouched = target.read_text(encoding="utf-8")
    refused = _raises(
        lambda: write_baseline(
            {"self_pinned": LanguageCensus("self_pinned", census.reads)},
            {"self_pinned": _pinned_entry(0)},
            target,
        )
    )
    ok &= report_condition(
        refused and target.read_text(encoding="utf-8") == untouched,
        "write_baseline refuses to raise a pinned_count entry (live 1 against a pin of 0) and writes nothing",
    )
    return ok


def _self_test_registered_readings() -> bool:
    """Every registered language states its idioms and supplies its own probe reading,
    and the committed baseline is well formed and names only registered languages."""
    problems: list[str] = []
    registered = registered_language_names()
    for language in sorted(registered):
        if _declaration_for(language) is None:
            problems.append(_undeclared_problem(language))
            continue
        try:
            idiom_reader(language)
        except ValueError as exc:
            problems.append(str(exc))
    try:
        baseline = load_baseline()
        problems.extend(stale_entry_problems(baseline, registered))
        _listed_exemptions(baseline)
    except ValueError as exc:
        problems.append(f"committed baseline is malformed ({exc})")
    return report_condition(
        not problems,
        f"every registered language states its idioms and supplies a probe reading, and the committed "
        f"baseline is well formed ({problems or 'no problem'})",
    )


def self_test() -> bool:
    ok = report_gate_names_no_target(__file__)
    tmp_root = Path(tempfile.mkdtemp(prefix="zero-environment-runtime-selftest-"))
    try:
        census_ok, census = _self_test_census(tmp_root)
        ok &= census_ok
        ok &= _self_test_comparator(census)
        ok &= _self_test_entry_kind()
        ok &= _self_test_stale_entries()
        ok &= _self_test_baseline_writer(tmp_root, census)
        ok &= _self_test_registered_readings()
        refused = False
        try:
            _require_min_languages(frozenset({_SELF_TEST_LANGUAGE}))
        except SystemExit as exc:
            refused = exc.code == EXIT_USAGE
        ok &= report_condition(refused, "single-language guard refuses a one-language set, never a silent pass")
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    return ok


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _census_problems(update_baseline: bool) -> tuple[int, list[str]]:
    """The census of every registered language against the baseline: the number of
    languages scanned and every problem found.

    Raises:
        ValueError: The baseline is malformed, the example is unregistered, or an emitted
            source file does not parse.
        RuntimeError: Generating the example for a language failed.
    """
    censuses, unread = scan_all_registered_languages()
    baseline = load_baseline()
    if update_baseline:
        write_baseline(censuses, baseline)
        logger.info("baseline written: %s", BASELINE_PATH)
        baseline = load_baseline()
    problems = list(unread)
    problems.extend(stale_entry_problems(baseline, registered_language_names()))
    for language in sorted(censuses):
        census = censuses[language]
        entry = baseline[language] if language in baseline else None
        for template in sorted(census.reads):
            logger.debug("READ language=%s template=%s", language, template)
        language_problems = evaluate(census, entry)
        logger.info("%s", summary_line(census, entry, len(language_problems)))
        problems.extend(language_problems)
    problems.extend(live_read_problems(censuses, baseline))
    return len(censuses) + len(unread), problems


def build_parser() -> argparse.ArgumentParser:
    """The gate's options: exactly the wrapper's parameters, spelled exactly."""
    parser = argparse.ArgumentParser(
        prog=WRAPPER,
        description=(
            "Zero-environment runtime census: every registered language's generated tree is held "
            "to the rule its baseline entry kind selects -- reviewed per-read exemptions "
            "(reviewed_exemptions) or a decrease-only pinned count (pinned_count)."
        ),
        allow_abbrev=False,
    )
    parser.add_argument(WRAPPER_DEBUG_FLAG, dest="debug", action="store_true", help="Enable DEBUG logging")
    parser.add_argument(
        "--self-test", action="store_true", help="Run only the non-vacuity self-test and the wrapper seam check"
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Lower every pinned_count entry to its live census (never raises one)",
    )
    return parser


def _run(args: argparse.Namespace) -> int:
    """Run the self-test, or the census once the non-vacuity self-test has passed."""
    from datrix_scripts.test.test import ensure_packages
    from datrix_scripts.venv import require_packages

    if not ensure_packages(os.environ, require_packages):
        return EXIT_FAIL
    if args.self_test:
        code = run_self_test(
            [self_test_check("non_vacuity", self_test)], wrapper=WRAPPER, module=MODULE, parser=build_parser(),
            folder=REALIZATION_GATES_DIR,
        )
        return EXIT_OK if code == EXIT_PASS else EXIT_USAGE
    if not self_test():
        logger.error("NON-VACUITY SELF-TEST FAILED -- aborting before any real census is trusted.")
        return EXIT_USAGE
    logger.info("non-vacuity self-test: PASS")
    return _run_census(update_baseline=args.update_baseline)


def _run_census(*, update_baseline: bool) -> int:
    """Census every registered language against its baseline entry (lowering pins first on request)."""
    try:
        scanned, problems = _census_problems(update_baseline)
    except (ValueError, RuntimeError) as exc:
        logger.error("Zero-environment census failed: %s", exc)
        return EXIT_USAGE

    for problem in problems:
        logger.error("%s", problem)
    logger.info(
        "ZERO-ENVIRONMENT RUNTIME CENSUS: %d registered language(s) scanned, %d problem(s).",
        scanned,
        len(problems),
    )
    return EXIT_FAIL if problems else EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point: the gate in gate mode (a claimed log and the verdict line)."""
    return run_as_gate(GATE, MODULE, gate_child(build_parser, _run), argv)


if __name__ == "__main__":
    sys.exit(main())
