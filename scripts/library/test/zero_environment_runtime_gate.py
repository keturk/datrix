#!/usr/bin/env python3
"""Zero-environment runtime census gate -- every registered language is
obligated to bake deployment-static values at generation time.

The zero-environment runtime architecture bakes every deployment-static value
a generated service needs into literal constants at generation time, so the
running service consults no environment variable. That is a portable
decision, and every registered language is obligated to it. Each language
plugin states the regular expressions that spell an environment read in its
own templates on its ``LanguageCapabilityDeclaration``
(``zero_environment_runtime``), and this gate censuses every template against
them. What the census may find is decided by the KIND of the language's entry
in ``scripts/config/zero-environment-runtime-baseline.json`` -- nothing else
selects the rule:

* ``reviewed_exemptions`` -- every template that reads the environment is
  listed with a written reason, as a justification of that specific read. An
  unlisted read and a stale entry are both violations. A registered language
  with NO entry is held to this kind with an empty list: it may carry no
  environment read, so adding a language needs no edit here.
* ``pinned_count`` -- a decrease-only count of environment-reading templates,
  for a language that delivers runtime facts through the environment by
  design. The count may fall (``--update-baseline`` lowers it) and may never
  rise; the writer refuses to raise it.

A registered language that states no idioms fails the gate, naming it, and a
baseline entry naming a language that is not registered is stale and fails.

The language set is derived from the installed ``datrix.languages`` entry
points at runtime, never a hardcoded list, and each language's idioms come
from its own declaration, never a table in this script. Templates are every
``.j2`` file under the ``src/`` tree of every package implementing the
language -- its backend and each language core the backend requires; test-harness
templates count too, because a harness that reads the environment is still
emitted into the generated project -- a ``reviewed_exemptions`` language
lists them as exemptions with that reason.

Runs a built-in non-vacuity self-test on every invocation: a synthetic
template tree with one planted read and one clean file, the comparator
against both entry kinds (missing exemption, stale exemption, count over and
under the pin, the same census passing under one kind and failing under the
other, no entry), the entry-kind validation, the baseline writer (lowers a
pin, refuses to raise one, carries exemptions through), and a live-tree proof
that the census sees a known real read.

Repo-level validation script (per the datrix showcase boundary -- no pytest
suite lives in datrix).

Usage:
    python zero_environment_runtime_gate.py
    python zero_environment_runtime_gate.py --debug
    python zero_environment_runtime_gate.py --self-test
    python zero_environment_runtime_gate.py --update-baseline
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
import sys
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

_LIBRARY_DIR = Path(__file__).resolve().parent.parent
if _LIBRARY_DIR.exists() and str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from datrix_common.plugin.capability_resolution import declaration_for_language  # noqa: E402
from datrix_common.plugin.language_capability import (  # noqa: E402
    ZeroEnvironmentRuntimeDeclaration,
)

from shared.registered_targets import registered_language_names  # noqa: E402
from shared.registered_targets import (  # noqa: E402
    AXIS_LANGUAGES,
    WORKSPACE_ROOT,
    discover_target_package_src_dirs,
)

logger = logging.getLogger(__name__)

_HERE = Path(__file__).resolve()
DATRIX_DIR: Final[Path] = _HERE.parents[3]
BASELINE_PATH: Final[Path] = (
    DATRIX_DIR / "scripts" / "config" / "zero-environment-runtime-baseline.json"
)

_TEMPLATE_SUFFIX: Final[str] = ".j2"
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
_ENTRY_PAYLOAD_KEYS: Final[Mapping[str, str]] = {
    ENTRY_KIND_EXEMPTIONS: _EXEMPTIONS_KEY,
    ENTRY_KIND_PINNED_COUNT: _PINNED_COUNT_KEY,
}

#: The ``_comment`` block ``--update-baseline`` writes; the committed file
#: carries the same text.
_BASELINE_COMMENT: Final[tuple[str, ...]] = (
    "Zero-environment runtime census, per registered datrix.languages package.",
    "Every language entry carries a 'kind'. reviewed_exemptions: every template",
    "that reads the environment is listed with a written reason (hand-authored;",
    "an unlisted read and a stale entry both fail). pinned_count: a decrease-only",
    "count of environment-reading templates, for a language that delivers runtime",
    "facts through the environment by design; only -UpdateBaseline writes it, and",
    "never upward. A language with no entry is held to reviewed_exemptions with an",
    "empty list.",
)

#: A described, currently-real environment read the live census must find:
#: ``(language, template path relative to the package's src/<import root>/)``.
#: Python's JWKS validator resolves ``allowedAudienceRefs`` through the
#: environment and is a reviewed exemption in the baseline. If that read is
#: ever removed, re-pin this constant to a still-live exemption in the same
#: change -- the self-test asserts the census finds a real read, never the
#: literal path in isolation.
_KNOWN_LIVE_READ: Final[tuple[str, str]] = ("python", "templates/api/identity.py.j2")

_SELF_TEST_LANGUAGE: Final[str] = "self_test_zero_env_lang"
_SELF_TEST_IDIOM: Final[str] = r"\bSELF_TEST_ENV\.read\b"
_SELF_TEST_TEMPLATE: Final[str] = "templates/reads.py.j2"


@dataclass(frozen=True)
class LanguageCensus:
    """The environment-reading templates one language's packages carry."""

    language: str
    src_dirs: tuple[Path, ...]
    reads: frozenset[str]


@dataclass(frozen=True)
class Exemption:
    """One reviewed environment read a language carries on purpose."""

    template: str
    reason: str


# ---------------------------------------------------------------------------
# Census
# ---------------------------------------------------------------------------


def census_templates(src_dirs: tuple[Path, ...], idioms: tuple[re.Pattern[str], ...]) -> frozenset[str]:
    """Every ``.j2`` template under any of *src_dirs* -- every package
    implementing one language, its backend and each language core -- that
    matches any idiom, as a posix path relative to its own package's src root
    (the key the baseline's exemptions use).

    File-level granularity: a template is a read when any line of it matches,
    so a docstring that mentions the idiom counts and needs an exemption too.
    That is deliberate -- a mention is cheap to exempt with a reason, and a
    matcher that tried to tell prose from code would be the eyeballing regex
    the seam discipline forbids.

    Raises:
        ValueError: Two of the language's packages carry a template at the
            same relative path, so one baseline key would name two files.
    """
    reads: dict[str, Path] = {}
    for src_dir in src_dirs:
        for template in sorted(src_dir.rglob(f"*{_TEMPLATE_SUFFIX}")):
            text = template.read_text(encoding="utf-8-sig")
            if not any(pattern.search(text) for pattern in idioms):
                continue
            key = template.relative_to(src_dir).as_posix()
            if key in reads:
                raise ValueError(
                    f"Two packages of one language carry an environment-reading template at "
                    f"{key!r}: {reads[key]} and {template}. A baseline key must name one file. "
                    f"Fix: keep the template in one package."
                )
            reads[key] = template
    return frozenset(reads)


def census_language(
    language: str, src_dirs: tuple[Path, ...], idioms: tuple[re.Pattern[str], ...]
) -> LanguageCensus:
    return LanguageCensus(
        language=language,
        src_dirs=src_dirs,
        reads=census_templates(src_dirs, idioms),
    )


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
    languages = data.get("languages") if isinstance(data, dict) else None
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
            f"'{_ENTRY_KIND_KEY}': '{ENTRY_KIND_EXEMPTIONS}' (every environment-reading template "
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


def parse_exemptions(language: str, entry: Mapping[str, object]) -> tuple[Exemption, ...]:
    """The reviewed exemption list of a ``reviewed_exemptions`` entry.

    Raises:
        ValueError: If the entry has no ``exemptions`` list, an item lacks a
            template or a non-empty reason, or a template is listed twice.
    """
    raw = entry.get(_EXEMPTIONS_KEY)
    if not isinstance(raw, list):
        raise ValueError(
            f"{BASELINE_PATH}: languages.{language} is a '{ENTRY_KIND_EXEMPTIONS}' entry, so it "
            f"must carry an '{_EXEMPTIONS_KEY}' list (each item: template + reason). Fix: add the "
            f"list, empty if the language carries no environment read."
        )
    seen: set[str] = set()
    exemptions: list[Exemption] = []
    for item in raw:
        template = item.get("template") if isinstance(item, dict) else None
        reason = item.get("reason") if isinstance(item, dict) else None
        if not isinstance(template, str) or not template:
            raise ValueError(
                f"{BASELINE_PATH}: languages.{language}.exemptions item {item!r} "
                f"has no 'template'. Fix: name the template path relative to the "
                f"package's src/<import root>/."
            )
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError(
                f"{BASELINE_PATH}: languages.{language}.exemptions[{template!r}] "
                f"has no written reason. An exemption without a reason is silence. "
                f"Fix: state why this template reads the environment."
            )
        if template in seen:
            raise ValueError(
                f"{BASELINE_PATH}: languages.{language}.exemptions lists "
                f"{template!r} twice. Fix: keep one entry."
            )
        seen.add(template)
        exemptions.append(Exemption(template=template, reason=reason))
    return tuple(exemptions)


def parse_pinned_count(language: str, entry: Mapping[str, object]) -> int:
    """The pinned count of a ``pinned_count`` entry.

    Raises:
        ValueError: If the entry has no non-negative integer ``pinned_count``.
    """
    count = entry.get(_PINNED_COUNT_KEY)
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
    exempted = {exemption.template for exemption in exemptions}
    for template in sorted(census.reads - exempted):
        problems.append(
            f"{census.language}: {template} reads the environment but carries no reviewed "
            f"exemption. Fix: bake the value at generation time, or add an exemption with a "
            f"written reason to {BASELINE_PATH} (a language that delivers runtime facts through "
            f"the environment by design carries a '{ENTRY_KIND_PINNED_COUNT}' entry at its live "
            f"count instead)."
        )
    for template in sorted(exempted - census.reads):
        problems.append(
            f"{census.language}: exemption {template} names a template with no "
            f"environment read (or no such template). Fix: remove the stale "
            f"entry from {BASELINE_PATH}."
        )
    return problems


def _pinned_count_problems(census: LanguageCensus, pinned: int) -> list[str]:
    live = len(census.reads)
    if live > pinned:
        return [
            f"{census.language}: {live} template(s) read the environment, "
            f"above the pinned decrease-only count of {pinned}. A new environment read "
            f"appeared. Fix: bake the new value at generation time instead."
        ]
    if live < pinned:
        logger.info(
            "%s: %d environment-reading template(s), below the pinned %d -- "
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
        f"environment-reading template(s), {len(exemptions)} reviewed exemption(s), "
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


def scan_all_registered_languages() -> tuple[dict[str, LanguageCensus], list[str]]:
    """Census every registered language; a language that states no idioms is
    reported, never skipped."""
    language_names = registered_language_names()
    _require_min_languages(language_names)
    src_dirs = discover_target_package_src_dirs(AXIS_LANGUAGES, language_names, WORKSPACE_ROOT)
    censuses: dict[str, LanguageCensus] = {}
    undeclared: list[str] = []
    for language, language_src_dirs in sorted(src_dirs.items()):
        declaration = _declaration_for(language)
        if declaration is None:
            undeclared.append(
                f"{language}: states no zero_environment_runtime idioms on its "
                f"LanguageCapabilityDeclaration, so its templates cannot be censused. Every "
                f"registered language is obligated to state the regular expressions that spell "
                f"an environment read in its own templates. Fix: declare a "
                f"ZeroEnvironmentRuntimeDeclaration naming them."
            )
            continue
        censuses[language] = census_language(language, language_src_dirs, declaration.compiled_idioms())
    return censuses, undeclared


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
                f"{language}: {live} template(s) read the environment, above the pinned "
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


def _assert(condition: bool, label: str) -> bool:
    print(f"[{'OK' if condition else 'FAIL'}] {label}")
    return condition


def _raises_value_error(call: Callable[[], object]) -> bool:
    """Whether calling *call* raises ``ValueError``."""
    try:
        call()
    except ValueError:
        return True
    return False


def _self_test_census(tmp_root: Path) -> tuple[bool, LanguageCensus]:
    src_dir = tmp_root / _SELF_TEST_LANGUAGE
    (src_dir / "templates").mkdir(parents=True)
    (src_dir / "templates" / "reads.py.j2").write_text(
        "value = SELF_TEST_ENV.read('X')\n", encoding="utf-8"
    )
    (src_dir / "templates" / "clean.py.j2").write_text("value = 1\n", encoding="utf-8")
    (src_dir / "templates" / "not_a_template.py").write_text(
        "SELF_TEST_ENV.read('ignored: not a template')\n", encoding="utf-8"
    )
    census = census_language(_SELF_TEST_LANGUAGE, (src_dir,), (re.compile(_SELF_TEST_IDIOM),))
    ok = _assert(
        census.reads == frozenset({_SELF_TEST_TEMPLATE}),
        "synthetic tree: exactly the planted template is a read; the clean template and "
        "the non-template file are not",
    )
    return ok, census


def _self_test_language_core(tmp_root: Path) -> bool:
    """A fixture language split into a backend and a core: a template read
    planted only in the core is part of the language's census; a backend-only
    census (the pre-split blindness) misses it; and the same relative template
    path carried by both packages is refused rather than folded into one key."""
    backend = tmp_root / "split_backend"
    core = tmp_root / "split_core"
    (backend / "templates").mkdir(parents=True)
    (core / "templates").mkdir(parents=True)
    (backend / "templates" / "clean.py.j2").write_text("value = 1\n", encoding="utf-8")
    (core / "templates" / "core_reads.py.j2").write_text("value = SELF_TEST_ENV.read('X')\n", encoding="utf-8")
    idioms = (re.compile(_SELF_TEST_IDIOM),)
    split = census_language(_SELF_TEST_LANGUAGE, (backend, core), idioms)
    backend_only = census_language(_SELF_TEST_LANGUAGE, (backend,), idioms)
    (backend / "templates" / "core_reads.py.j2").write_text("value = SELF_TEST_ENV.read('Y')\n", encoding="utf-8")
    collision_refused = _raises_value_error(lambda: census_language(_SELF_TEST_LANGUAGE, (backend, core), idioms))
    return _assert(
        split.reads == frozenset({"templates/core_reads.py.j2"}) and not backend_only.reads and collision_refused,
        "a fixture language split into a backend and a core: a read planted in the core is censused, a "
        "backend-only census misses it, and one relative path in both packages is refused",
    )


def _exemptions_entry(*templates: str) -> dict[str, object]:
    return {
        _ENTRY_KIND_KEY: ENTRY_KIND_EXEMPTIONS,
        _EXEMPTIONS_KEY: [{"template": template, "reason": "planted"} for template in templates],
    }


def _pinned_entry(count: int) -> dict[str, object]:
    return {_ENTRY_KIND_KEY: ENTRY_KIND_PINNED_COUNT, _PINNED_COUNT_KEY: count}


def _self_test_comparator(census: LanguageCensus) -> bool:
    clean = LanguageCensus(_SELF_TEST_LANGUAGE, census.src_dirs, frozenset())
    ok = True
    ok &= _assert(
        evaluate(census, _exemptions_entry(_SELF_TEST_TEMPLATE)) == [],
        "reviewed_exemptions + exact exemption list: no problem",
    )
    ok &= _assert(
        len(evaluate(census, _exemptions_entry())) == 1,
        "reviewed_exemptions + missing exemption: exactly one problem",
    )
    ok &= _assert(
        len(evaluate(census, _exemptions_entry(_SELF_TEST_TEMPLATE, "templates/gone.py.j2"))) == 1,
        "reviewed_exemptions + stale exemption: exactly one problem",
    )
    ok &= _assert(
        evaluate(census, _pinned_entry(1)) == [] and evaluate(census, _pinned_entry(5)) == [],
        "pinned_count + count at or below the pin: no problem",
    )
    ok &= _assert(
        len(evaluate(census, _pinned_entry(0))) == 1,
        "pinned_count + count above the pin: exactly one problem",
    )
    ok &= _assert(
        len(evaluate(census, None)) == 1 and evaluate(clean, None) == [],
        "no entry + one read: exactly one problem; no entry + no read: none",
    )
    ok &= _assert(
        evaluate(census, _pinned_entry(1)) == [] and len(evaluate(census, _exemptions_entry())) == 1,
        "the same one-read census passes against a pinned_count entry of 1 and fails against an "
        "empty reviewed_exemptions entry: the entry kind alone selects the branch",
    )
    ok &= _assert(
        _raises_value_error(
            lambda: parse_exemptions(
                _SELF_TEST_LANGUAGE,
                {_EXEMPTIONS_KEY: [{"template": "x.j2", "reason": " "}]},
            )
        ),
        "an exemption without a written reason is rejected",
    )
    return ok


def _self_test_entry_kind() -> bool:
    ok = True
    ok &= _assert(
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
        ok &= _assert(
            _raises_value_error(lambda entry=entry: entry_kind(_SELF_TEST_LANGUAGE, entry)),
            f"entry_kind rejects {label}",
        )
    return ok


def _self_test_stale_entries() -> bool:
    registered = frozenset({"alpha", "beta"})
    stale = stale_entry_problems({"alpha": _pinned_entry(1), "gamma": _exemptions_entry()}, registered)
    registered_only = stale_entry_problems({"alpha": _pinned_entry(1)}, registered)
    return _assert(
        len(stale) == 1 and "gamma" in stale[0] and registered_only == [],
        "a baseline entry naming an unregistered language is one stale-entry problem; registered ones are not",
    )


def _self_test_baseline_writer(tmp_root: Path, census: LanguageCensus) -> bool:
    """The writer lowers a pinned entry to the live count, refuses to raise one,
    and carries a reviewed_exemptions entry (and a language with no census)
    through unchanged, every entry keeping its kind."""
    ok = True
    target = tmp_root / "written-baseline.json"
    exemptions = _exemptions_entry("templates/a.py.j2", "templates/b.py.j2")
    untouched_pin = _pinned_entry(9)
    existing: dict[str, dict[str, object]] = {
        "self_exemptions": exemptions,
        "self_pinned": _pinned_entry(4),
        "self_uncensused": untouched_pin,
    }
    censuses = {
        "self_exemptions": census,
        "self_pinned": LanguageCensus("self_pinned", census.src_dirs, census.reads),
    }
    write_baseline(censuses, existing, target)
    written = json.loads(target.read_text(encoding="utf-8"))["languages"]
    ok &= _assert(
        written["self_pinned"] == _pinned_entry(1),
        "write_baseline lowers a pinned_count entry from 4 to the live count 1, keeping its kind",
    )
    ok &= _assert(
        json.dumps(written["self_exemptions"]) == json.dumps(exemptions)
        and json.dumps(written["self_uncensused"]) == json.dumps(untouched_pin),
        "write_baseline carries a reviewed_exemptions entry and an uncensused pinned entry through unchanged",
    )
    untouched = target.read_text(encoding="utf-8")
    refused = _raises_value_error(
        lambda: write_baseline(
            {"self_pinned": LanguageCensus("self_pinned", census.src_dirs, census.reads)},
            {"self_pinned": _pinned_entry(0)},
            target,
        )
    )
    ok &= _assert(
        refused and target.read_text(encoding="utf-8") == untouched,
        "write_baseline refuses to raise a pinned_count entry (live 1 against a pin of 0) and writes nothing",
    )
    return ok


def _self_test_live_read() -> bool:
    language, relative_template = _KNOWN_LIVE_READ
    language_names = registered_language_names()
    src_dirs = discover_target_package_src_dirs(AXIS_LANGUAGES, language_names, WORKSPACE_ROOT)
    language_src_dirs = src_dirs.get(language)
    declaration = _declaration_for(language) if language_src_dirs is not None else None
    if language_src_dirs is None or declaration is None:
        return _assert(False, f"live tree registers {language} with stated idioms")
    census = census_language(language, language_src_dirs, declaration.compiled_idioms())
    return _assert(
        relative_template in census.reads,
        f"live census (real tree) finds the known read {language}:{relative_template}",
    )


def self_test() -> bool:
    ok = True
    tmp_root = Path(tempfile.mkdtemp(prefix="zero-environment-runtime-selftest-"))
    try:
        census_ok, census = _self_test_census(tmp_root)
        ok &= census_ok
        ok &= _self_test_comparator(census)
        ok &= _self_test_entry_kind()
        ok &= _self_test_stale_entries()
        ok &= _self_test_baseline_writer(tmp_root, census)
        ok &= _self_test_language_core(tmp_root)
        ok &= _self_test_live_read()
        refused = False
        try:
            _require_min_languages(frozenset({_SELF_TEST_LANGUAGE}))
        except SystemExit as exc:
            refused = exc.code == EXIT_USAGE
        ok &= _assert(refused, "single-language guard refuses a one-language set, never a silent pass")
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    return ok


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Zero-environment runtime census: every registered language is held to the rule "
            "its baseline entry kind selects -- reviewed per-read exemptions "
            "(reviewed_exemptions) or a decrease-only pinned count (pinned_count)."
        ),
    )
    parser.add_argument("--debug", action="store_true", help="Enable DEBUG logging")
    parser.add_argument("--self-test", action="store_true", help="Run only the non-vacuity self-test")
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Lower every pinned_count entry to its live census (never raises one)",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    if not self_test():
        logger.error("NON-VACUITY SELF-TEST FAILED -- aborting before any real census is trusted.")
        return EXIT_USAGE
    logger.info("non-vacuity self-test: PASS")
    if args.self_test:
        return EXIT_OK

    try:
        censuses, undeclared = scan_all_registered_languages()
        baseline = load_baseline()
        if args.update_baseline:
            write_baseline(censuses, baseline)
            logger.info("baseline written: %s", BASELINE_PATH)
            baseline = load_baseline()
        problems = list(undeclared)
        problems.extend(stale_entry_problems(baseline, registered_language_names()))
        for language in sorted(censuses):
            census = censuses[language]
            entry = baseline.get(language)
            for template in sorted(census.reads):
                logger.debug("READ language=%s template=%s", language, template)
            language_problems = evaluate(census, entry)
            logger.info("%s", summary_line(census, entry, len(language_problems)))
            problems.extend(language_problems)
    except ValueError as exc:
        logger.error("Zero-environment census failed: %s", exc)
        return EXIT_USAGE

    for problem in problems:
        logger.error("%s", problem)
    logger.info(
        "ZERO-ENVIRONMENT RUNTIME CENSUS: %d registered language(s) scanned, %d problem(s).",
        len(censuses) + len(undeclared),
        len(problems),
    )
    return EXIT_FAIL if problems else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
