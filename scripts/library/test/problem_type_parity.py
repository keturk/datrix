"""Problem-type parity gate -- every registered language answers errors with
RFC 7807 ``type`` URNs from one registry and is obligated to every framework
family.

A generated service's error body carries a ``type`` member naming the error
class. A client keyed on it must see one vocabulary whichever language served
the request, so the vocabulary has one home:
``datrix_common.datrix_model.problem_types`` (``urn:datrix:error:<slug>``; a
declared DSL exception derives its slug from its class name through the
shared exception-declaration algorithm, a framework error uses a registered
family). Before this gate, the languages disagreed: some spelled the URNs,
typescript composed ``https://api.example.com/<service>/errors/<slug>``, and
another emitted ``https://httpstatuses.com/<status>`` for everything.

The gate censuses the ``.py`` and ``.j2`` sources under every package
implementing each registered language -- its backend and every language core
the backend requires -- and holds each language to:

* **Reference, never literal.** A language renders a framework problem type
  from the registry, so its sources carry no ``urn:datrix:error:<slug>``
  literal at all -- a registered slug and a private one fail alike, with no
  exemption path. The bare prefix stays legal: the shared exception-declaration
  algorithm composes a declared exception's URN from it at runtime.
* **Realization.** A family is *realized* by a language when a ``.j2`` source
  references its template global ``PROBLEM_<FAMILY_UPPER_SNAKE>`` or renders the
  bare-status table (``GENERIC_PROBLEM_FAMILY_BY_STATUS``, which realizes every
  family that table holds), or a ``.py`` source calls
  ``problem_type_for("<family>")``. Every registered language is
  obligated to realize every registered family. A (language, family) cell a
  language does not realize is an *unspelled cell*; no declaration can excuse
  it. A family no language realizes is a dead registry entry and fails
  outright.

The unspelled cells are counted per language and held to a two-directional
pin in ``scripts/config/problem-type-parity-baseline.toml``: a count above the
pin fails (a family stopped being spelled, or a new family was registered
unspelled -- spell it, never raise the pin), and a count below the pin fails
until the pin is lowered in the same change (an improvement must be banked). A
language absent from the table is pinned at zero. Every counted cell is printed
on every run, never silent.

Language set from the installed ``datrix.languages`` entry points at runtime;
registry from datrix-common at runtime -- never a table in this script. Runs a
built-in non-vacuity self-test on every invocation. Repo-level validation
script (per the datrix showcase boundary -- no pytest suite lives in datrix).
"""

from __future__ import annotations

import argparse
import logging
import re
import shutil
import sys
import tempfile
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Final

_LIBRARY_DIR = Path(__file__).resolve().parent.parent
if _LIBRARY_DIR.exists() and str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from datrix_codegen_common.generation.problem_template_globals import (  # noqa: E402
    problem_family_global_name,
)
from datrix_common.datrix_model.problem_types import (  # noqa: E402
    FRAMEWORK_PROBLEM_TYPES,
    GENERIC_PROBLEM_FAMILY_BY_STATUS,
    PROBLEM_TYPE_URN_PREFIX,
    ProblemType,
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
BASELINE_PATH: Final[Path] = DATRIX_DIR / "scripts" / "config" / "problem-type-parity-baseline.toml"
_BASELINE_LANGUAGES_KEY: Final[str] = "languages"

EXIT_OK: Final[int] = 0
EXIT_FAIL: Final[int] = 1
EXIT_USAGE: Final[int] = 2

_SOURCE_SUFFIXES: Final[frozenset[str]] = frozenset({".py", ".j2"})
_SKIP_DIR_NAMES: Final[frozenset[str]] = frozenset({"__pycache__", "node_modules"})
_MIN_LANGUAGES_FOR_COMPARISON: Final[int] = 2

#: A literal problem-type URN: the prefix followed by at least one slug
#: character. The bare prefix (a composition site for runtime-built URNs) is
#: deliberately not a match.
_URN_LITERAL_RE: Final[re.Pattern[str]] = re.compile(
    re.escape(PROBLEM_TYPE_URN_PREFIX) + r"([a-z0-9][a-z0-9-]*)"
)

#: A template reference to a family global: ``PROBLEM_`` plus upper-snake words.
#: Whether the name is a family's is decided against the registry afterwards
#: (``PROBLEM_TYPES`` and the like are globals but not families).
_TEMPLATE_REFERENCE_RE: Final[re.Pattern[str]] = re.compile(r"\bPROBLEM_([A-Z][A-Z0-9_]*)\b")

#: The template global holding the registry's bare-status -> family table.
_GENERIC_TABLE_GLOBAL: Final[str] = "GENERIC_PROBLEM_FAMILY_BY_STATUS"

#: A ``.py`` reference to a registered family: ``problem_type_for("<family>")``.
_LOOKUP_REFERENCE_RE: Final[re.Pattern[str]] = re.compile(
    r"\bproblem_type_for\(\s*[\"']([a-z0-9][a-z0-9-]*)[\"']\s*\)"
)


@dataclass(frozen=True, slots=True)
class Spelling:
    language: str
    package: str
    relative_path: str
    line: int
    slug: str


@dataclass(frozen=True, slots=True)
class LanguageCensus:
    language: str
    spellings: tuple[Spelling, ...]
    """Every literal ``urn:datrix:error:<slug>`` -- each one a defect."""
    references: tuple[Spelling, ...] = ()
    """Every registry reference -- ``PROBLEM_<FAMILY>`` in a ``.j2`` source,
    ``problem_type_for("<family>")`` in a ``.py`` source; ``slug`` is the
    family the reference names."""


def _iter_source_files(src_dir: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(src_dir.rglob("*")):
        if not path.is_file() or path.suffix not in _SOURCE_SUFFIXES:
            continue
        if any(part in _SKIP_DIR_NAMES for part in path.relative_to(src_dir).parts):
            continue
        files.append(path)
    return files


def _line_references(
    suffix: str, line: str, family_by_global: Mapping[str, str]
) -> list[str]:
    """The families *line* references, by the reference form its file type uses."""
    if suffix == ".j2":
        referenced = [
            family_by_global[match.group(0)]
            for match in _TEMPLATE_REFERENCE_RE.finditer(line)
            if match.group(0) in family_by_global
        ]
        if _GENERIC_TABLE_GLOBAL in line:
            # A template that renders the whole bare-status table realizes every
            # family in it: a family minted only from a status (not-found, conflict,
            # rate-limit-exceeded, ...) has no per-family reference to carry without
            # re-typing the status table the registry owns.
            referenced.extend(GENERIC_PROBLEM_FAMILY_BY_STATUS.values())
        return referenced
    return [match.group(1) for match in _LOOKUP_REFERENCE_RE.finditer(line)]


def census_sources(
    language: str,
    src_dirs: tuple[Path, ...],
    registry: tuple[ProblemType, ...] = FRAMEWORK_PROBLEM_TYPES,
) -> LanguageCensus:
    """Every literal ``urn:datrix:error:<slug>`` and every registry reference
    (``.py`` and ``.j2``) under every package implementing *language* -- its
    backend and each language core.

    Each ``src_dir`` is ``<package>/src/<import_name>``; a spelling or
    reference records the package it was found in.
    """
    family_by_global = {
        problem_family_global_name(problem_type.family): problem_type.family for problem_type in registry
    }
    spellings: list[Spelling] = []
    references: list[Spelling] = []
    for src_dir in src_dirs:
        package = src_dir.parents[1].name
        for path in _iter_source_files(src_dir):
            relative = path.relative_to(src_dir).as_posix()
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                for match in _URN_LITERAL_RE.finditer(line):
                    spellings.append(Spelling(language, package, relative, line_number, match.group(1)))
                for family in _line_references(path.suffix, line, family_by_global):
                    references.append(Spelling(language, package, relative, line_number, family))
    return LanguageCensus(language, tuple(spellings), tuple(references))


@dataclass(frozen=True, slots=True)
class LanguageVerdict:
    language: str
    realized: frozenset[str]


@dataclass(frozen=True, slots=True)
class Evaluation:
    """What one comparison found, split by whether a pin may count it."""

    problems: list[str]
    """Findings no pin can absorb: a literal slug that is not a registered
    family, and a registered family no language spells."""
    unspelled: Mapping[str, tuple[str, ...]]
    """Per language, the sorted registered families its census does not spell
    -- the cells the baseline pins."""
    verdicts: Mapping[str, LanguageVerdict]


def realized_families(census: LanguageCensus, registry: tuple[ProblemType, ...]) -> frozenset[str]:
    families = {problem_type.family for problem_type in registry}
    return frozenset(reference.slug for reference in census.references if reference.slug in families)


def evaluate(
    registry: tuple[ProblemType, ...],
    censuses: Mapping[str, LanguageCensus],
) -> Evaluation:
    families = frozenset(problem_type.family for problem_type in registry)
    problems: list[str] = []
    verdicts: dict[str, LanguageVerdict] = {}
    unspelled: dict[str, tuple[str, ...]] = {}
    for language in sorted(censuses):
        census = censuses[language]
        for spelling in census.spellings:
            registration = (
                "a registered family"
                if spelling.slug in families
                else "not a registered problem-type family"
            )
            problems.append(
                f"{spelling.package}: {spelling.relative_path}:{spelling.line}: spells the literal "
                f"{PROBLEM_TYPE_URN_PREFIX}{spelling.slug!s} ({registration}). A language renders a "
                f"problem type from the registry and carries no URN literal; there is no exemption "
                f"path. Fix: reference the family (PROBLEM_<FAMILY> in a template, "
                f"problem_type_for(\"<family>\") in Python), or register it in "
                f"datrix_common.datrix_model.problem_types so every target mints it."
            )
        realized = realized_families(census, registry)
        verdicts[language] = LanguageVerdict(language, realized)
        unspelled[language] = tuple(sorted(families - realized))
    realized_anywhere = frozenset().union(*(verdict.realized for verdict in verdicts.values()))
    for family in sorted(families - realized_anywhere):
        problems.append(
            f"registry: problem type {family!r} is spelled by no registered language. A type "
            f"nobody mints is a dead contract. Fix: realize it or remove it from the registry."
        )
    return Evaluation(problems, unspelled, verdicts)


# ---------------------------------------------------------------------------
# Two-directional pin over the unspelled cells
# ---------------------------------------------------------------------------


def _baseline_error(path: Path, what: str, fix: str) -> ValueError:
    return ValueError(f"problem_type_parity:{path} {what}. Fix: {fix}")


def load_baseline(path: Path = BASELINE_PATH) -> Mapping[str, int]:
    """Load the per-language pin of unspelled (language, family) cells.

    Only a ``[languages]`` table of non-negative integers is legal. A language
    absent from it is pinned at zero.

    Raises:
        ValueError: The file is missing, is not valid TOML, carries an
            unrecognized top-level key, lacks the ``[languages]`` table, or
            holds a count that is negative or not an integer (a ``bool`` is
            not one).
    """
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise _baseline_error(
            path,
            f"cannot be read ({exc})",
            "restore the file, seeded from a live run of the gate (never from a document).",
        ) from exc
    except tomllib.TOMLDecodeError as exc:
        raise _baseline_error(path, f"is not valid TOML ({exc})", "correct the syntax.") from exc
    unknown = sorted(set(raw) - {_BASELINE_LANGUAGES_KEY})
    if unknown:
        raise _baseline_error(
            path,
            f"has unrecognized top-level key(s) {unknown}; the only legal table is [{_BASELINE_LANGUAGES_KEY}]",
            "remove the key.",
        )
    table = raw.get(_BASELINE_LANGUAGES_KEY)
    if not isinstance(table, dict):
        raise _baseline_error(
            path,
            f"carries no [{_BASELINE_LANGUAGES_KEY}] table of language = count entries",
            f"add the [{_BASELINE_LANGUAGES_KEY}] table, seeded from a live run of the gate.",
        )
    counts: dict[str, int] = {}
    for language, count in table.items():
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise _baseline_error(
                path,
                f"pins {language!r} at {count!r}; expected a non-negative integer (a bool is not one)",
                "write the live unspelled-cell count for the language.",
            )
        counts[language] = count
    return MappingProxyType(counts)


def ratchet_problems(
    unspelled: Mapping[str, Sequence[str]],
    baseline: Mapping[str, int],
    registered: frozenset[str],
) -> list[str]:
    """Compare each registered language's unspelled-cell count with its pin.

    A count ABOVE the pin and a count BELOW it are both problems -- exact
    match is the only passing state -- and a pin naming a language that is not
    registered is stale. A registered language absent from *baseline* is
    pinned at exactly zero.
    """
    problems: list[str] = []
    for language in sorted(registered):
        families = tuple(unspelled.get(language, ()))
        live = len(families)
        pinned = baseline.get(language, 0)
        if live > pinned:
            problems.append(
                f"{language}: EXCEED -- {live} unspelled problem-type cell(s) against a pin of "
                f"{pinned} (+{live - pinned}): {', '.join(families)}. A family stopped being realized "
                f"or a new family was registered unrealized. Fix: reference the family in the "
                f"language's sources (PROBLEM_<FAMILY> in a template, problem_type_for(\"<family>\") "
                f"in Python); never raise the pin in {BASELINE_PATH.name}."
            )
        elif live < pinned:
            problems.append(
                f"{language}: BELOW -- {live} unspelled problem-type cell(s) against a pin of "
                f"{pinned} (-{pinned - live}). An improvement must be banked. Fix: lower "
                f"[{_BASELINE_LANGUAGES_KEY}] {language} to {live} in {BASELINE_PATH.name} in the "
                f"same change."
            )
    for language in sorted(set(baseline) - registered):
        problems.append(
            f"{BASELINE_PATH.name}: stale pin -- it names language {language!r}, which is not "
            f"registered (registered: {', '.join(sorted(registered))}). Fix: remove the entry."
        )
    return problems


def _require_min_languages(language_names: frozenset[str]) -> None:
    if len(language_names) < _MIN_LANGUAGES_FOR_COMPARISON:
        print(
            f"Error: {len(language_names)} registered language(s) "
            f"({', '.join(sorted(language_names)) or 'none'}); a cross-language parity gate "
            f"needs at least {_MIN_LANGUAGES_FOR_COMPARISON}. Install the language packages.",
            file=sys.stderr,
        )
        raise SystemExit(EXIT_USAGE)


def scan_all_registered_languages() -> dict[str, LanguageCensus]:
    language_names = registered_language_names()
    _require_min_languages(language_names)
    src_dirs = discover_target_package_src_dirs(AXIS_LANGUAGES, language_names, WORKSPACE_ROOT)
    censuses: dict[str, LanguageCensus] = {}
    for language, language_src_dirs in sorted(src_dirs.items()):
        censuses[language] = census_sources(language, language_src_dirs)
        logger.debug(
            "census language=%s packages=%s spellings=%d",
            language,
            [src_dir.parents[1].name for src_dir in language_src_dirs],
            len(censuses[language].spellings),
        )
    return censuses


def render_report(registry: tuple[ProblemType, ...], verdicts: Mapping[str, LanguageVerdict]) -> str:
    languages = sorted(verdicts)
    width = max(len("family"), *(len(problem_type.family) for problem_type in registry))
    lines = ["  " + "family".ljust(width) + "  " + "  ".join(lang.ljust(10) for lang in languages)]
    for problem_type in registry:
        cells: list[str] = []
        for language in languages:
            verdict = verdicts[language]
            if problem_type.family in verdict.realized:
                cells.append("realized".ljust(10))
            else:
                cells.append("MISSING".ljust(10))
        lines.append("  " + problem_type.family.ljust(width) + "  " + "  ".join(cells))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Non-vacuity self-test
# ---------------------------------------------------------------------------


def _assert(condition: bool, label: str) -> bool:
    print(f"  {'PASS' if condition else 'FAIL'}: {label}")
    return condition


def _planted(
    language: str, slugs: tuple[str, ...], *, literals: tuple[str, ...] = ()
) -> LanguageCensus:
    """A census where *slugs* are registry references and *literals* are URN literals."""
    references = tuple(
        Spelling(language, f"datrix-codegen-{language}", "planted.j2", i + 1, slug) for i, slug in enumerate(slugs)
    )
    spellings = tuple(
        Spelling(language, f"datrix-codegen-{language}", "planted.j2", i + 1, slug) for i, slug in enumerate(literals)
    )
    return LanguageCensus(language, spellings, references)


def _self_test_comparator(registry: tuple[ProblemType, ...]) -> bool:
    ok = True
    full = tuple(problem_type.family for problem_type in registry)
    clean = {"alpha": _planted("alpha", full), "beta": _planted("beta", full)}
    evaluation = evaluate(registry, clean)
    ok &= _assert(
        evaluation.problems == [] and all(cells == () for cells in evaluation.unspelled.values()),
        "two fully realizing languages report no problem and no unspelled cell",
    )

    private = {"alpha": _planted("alpha", full, literals=("private-thing",)), "beta": clean["beta"]}
    evaluation = evaluate(registry, private)
    ok &= _assert(
        len(evaluation.problems) == 1 and "not a registered problem-type family" in evaluation.problems[0],
        "a spelled private slug is one unpinned hard problem",
    )

    literal = {"alpha": _planted("alpha", full, literals=(full[0],)), "beta": clean["beta"]}
    evaluation = evaluate(registry, literal)
    ok &= _assert(
        len(evaluation.problems) == 1
        and "a registered family" in evaluation.problems[0]
        and "no exemption path" in evaluation.problems[0]
        and all(cells == () for cells in evaluation.unspelled.values()),
        "a literal URN of a REGISTERED family still fails, with no exemption, and does not count as realization",
    )
    only_literals = {"alpha": _planted("alpha", (), literals=full), "beta": clean["beta"]}
    evaluation = evaluate(registry, only_literals)
    ok &= _assert(
        evaluation.unspelled["alpha"] == tuple(sorted(full)),
        "a language that spells every family only as literals realizes none of them",
    )

    missing = full[-1]
    partial_slugs = full[:-1]
    partial = {"alpha": _planted("alpha", partial_slugs), "beta": clean["beta"]}
    evaluation = evaluate(registry, partial)
    ok &= _assert(
        evaluation.problems == []
        and evaluation.unspelled["alpha"] == (missing,)
        and evaluation.unspelled["beta"] == ()
        and missing not in evaluation.verdicts["alpha"].realized,
        "a partially-spelling language is exactly one unspelled cell and zero hard problems",
    )
    nobody = {"alpha": _planted("alpha", partial_slugs), "beta": _planted("beta", partial_slugs)}
    evaluation = evaluate(registry, nobody)
    ok &= _assert(
        len(evaluation.problems) == 1 and "dead contract" in evaluation.problems[0],
        "a family nobody spells is one unpinned hard problem, whatever any pin says",
    )
    return ok


def _self_test_ratchet(registry: tuple[ProblemType, ...]) -> bool:
    ok = True
    full = tuple(problem_type.family for problem_type in registry)
    registered = frozenset({"alpha", "beta"})
    one_cell = {"alpha": (full[-1],), "beta": ()}
    problems = ratchet_problems(one_cell, {"alpha": 1}, registered)
    ok &= _assert(problems == [], "an exact-pin match is clean")
    problems = ratchet_problems(one_cell, {"alpha": 0}, registered)
    ok &= _assert(
        len(problems) == 1 and "EXCEED" in problems[0] and full[-1] in problems[0],
        "a count above the pin is one EXCEED problem naming the unspelled family",
    )
    problems = ratchet_problems(one_cell, {"alpha": 2}, registered)
    ok &= _assert(
        len(problems) == 1 and "BELOW" in problems[0] and "lower" in problems[0],
        "a count below the pin is one BELOW problem that says to lower the pin",
    )
    problems = ratchet_problems(one_cell, {}, registered)
    ok &= _assert(
        len(problems) == 1 and "EXCEED" in problems[0] and "pin of 0" in problems[0],
        "an unpinned language with one unspelled family is EXCEED against an implicit pin of 0",
    )
    problems = ratchet_problems(one_cell, {"alpha": 1, "gamma": 3}, registered)
    ok &= _assert(
        len(problems) == 1 and "stale pin" in problems[0] and "gamma" in problems[0],
        "a pin naming an unregistered language is one stale-pin problem",
    )
    return ok


def _self_test_baseline_loader(tmp_root: Path) -> bool:
    ok = True
    good = tmp_root / "good.toml"
    good.write_text("[languages]\nalpha = 3\nbeta = 0\n", encoding="utf-8")
    ok &= _assert(dict(load_baseline(good)) == {"alpha": 3, "beta": 0}, "a well-formed baseline loads")
    empty_table = tmp_root / "empty-table.toml"
    empty_table.write_text("[languages]\n", encoding="utf-8")
    ok &= _assert(dict(load_baseline(empty_table)) == {}, "an empty [languages] table loads (every language at zero)")
    rejected: tuple[tuple[str, Path, str], ...] = (
        ("an unrecognized top-level key", tmp_root / "key.toml", "[languages]\nalpha = 1\n[extra]\nx = 1\n"),
        ("a missing [languages] table", tmp_root / "no-table.toml", "alpha = 1\n"),
        ("a negative count", tmp_root / "negative.toml", "[languages]\nalpha = -1\n"),
        ("a bool count", tmp_root / "bool.toml", "[languages]\nalpha = true\n"),
        ("a non-integer count", tmp_root / "string.toml", '[languages]\nalpha = "7"\n'),
        ("invalid TOML", tmp_root / "invalid.toml", "[languages\nalpha = 1\n"),
    )
    for label, path, text in rejected:
        path.write_text(text, encoding="utf-8")
        try:
            load_baseline(path)
        except ValueError as exc:
            ok &= _assert(path.name in str(exc), f"the loader rejects {label}, naming the file")
        else:
            ok &= _assert(False, f"the loader rejects {label}")
    try:
        load_baseline(tmp_root / "absent.toml")
    except ValueError as exc:
        ok &= _assert("absent.toml" in str(exc), "the loader rejects a missing file, naming it")
    else:
        ok &= _assert(False, "the loader rejects a missing file")
    return ok


def _self_test_census(tmp_root: Path) -> bool:
    src = tmp_root / "datrix-codegen-fixture" / "src" / "pkg"
    (src / "templates").mkdir(parents=True)
    (src / "__pycache__").mkdir()
    (src / "templates" / "planted.j2").write_text(
        "type = 'urn:datrix:error:validation'\n"
        "prefix = 'urn:datrix:error:'\n"
        "other = `${PREFIX}http-${status}`\n"
        "kind = {{ PROBLEM_REQUEST_VALIDATION }}\n"
        "table = {{ PROBLEM_TYPES | tojson }}\n"
        "event = {{ PROBLEM_RESPONSE_LOG_EVENT }}\n"
        "status = {{ GENERIC_PROBLEM_FAMILY_BY_STATUS | tojson }}\n",
        encoding="utf-8",
    )
    (src / "handler.py").write_text(
        'URN = "urn:datrix:error:internal"\nTYPE = problem_type_for("bad-request")\n'
        'OTHER = problem_type_for(family)\n',
        encoding="utf-8",
    )
    (src / "notes.md").write_text(
        "urn:datrix:error:ignored-because-markdown\nPROBLEM_INTERNAL\n", encoding="utf-8"
    )
    (src / "__pycache__" / "stale.py").write_text("'urn:datrix:error:ignored-because-cache'\n", encoding="utf-8")
    census = census_sources("fixture", (src,))
    slugs = sorted(spelling.slug for spelling in census.spellings)
    references = sorted(reference.slug for reference in census.references)
    ok = _assert(
        slugs == ["internal", "validation"],
        f"planted sources yield exactly their two literal slugs; the bare prefix is not one (got {slugs})",
    )
    generic = sorted(set(GENERIC_PROBLEM_FAMILY_BY_STATUS.values()))
    expected = sorted(["bad-request", "request-validation", *GENERIC_PROBLEM_FAMILY_BY_STATUS.values()])
    ok &= _assert(
        references == expected,
        "a PROBLEM_REQUEST_VALIDATION template reference, a problem_type_for(\"bad-request\") call and a "
        "rendered GENERIC_PROBLEM_FAMILY_BY_STATUS table count as realization; PROBLEM_TYPES, a "
        f"variable argument and markdown do not (got {references}, generic={generic})",
    )
    return ok


def _self_test_language_core(tmp_root: Path) -> bool:
    """A fixture language split into a backend and a core: a URN spelled only
    in the core is part of the language's census, recorded against the core
    package; a backend-only census (the pre-split blindness) misses it."""
    backend = tmp_root / "datrix-codegen-splitlang" / "src" / "datrix_codegen_splitlang"
    core = tmp_root / "datrix-codegen-splitlang-core" / "src" / "datrix_codegen_splitlang_core"
    backend.mkdir(parents=True)
    core.mkdir(parents=True)
    (backend / "plugin.py").write_text("NAME = 'splitlang'\n", encoding="utf-8")
    (core / "errors.py").write_text('URN = problem_type_for("internal").urn\n', encoding="utf-8")
    split = census_sources("splitlang", (backend, core))
    backend_only = census_sources("splitlang", (backend,))
    found = [(reference.package, reference.slug) for reference in split.references]
    return _assert(
        found == [("datrix-codegen-splitlang-core", "internal")] and not backend_only.references,
        f"a fixture language split into a backend and a core: the census sees the URN planted in the core "
        f"(got {found}); a backend-only census does not",
    )


def _self_test_live_read() -> bool:
    censuses = scan_all_registered_languages()
    realizers = sorted(
        language for language, census in censuses.items()
        if "internal" in realized_families(census, FRAMEWORK_PROBLEM_TYPES)
    )
    return _assert(
        len(realizers) >= _MIN_LANGUAGES_FOR_COMPARISON,
        f"live census finds the internal problem type on >= 2 languages (found: {realizers})",
    )


def self_test() -> bool:
    print("Non-vacuity self-test:")
    tmp_root = Path(tempfile.mkdtemp(prefix="problem-type-gate-"))
    try:
        ok = _self_test_census(tmp_root)
        ok &= _self_test_language_core(tmp_root)
        ok &= _self_test_baseline_loader(tmp_root)
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    ok &= _self_test_comparator(FRAMEWORK_PROBLEM_TYPES)
    ok &= _self_test_ratchet(FRAMEWORK_PROBLEM_TYPES)
    ok &= _self_test_live_read()
    return ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--debug", action="store_true", help="Enable debug logging.")
    parser.add_argument("--self-test", action="store_true", help="Run only the non-vacuity self-test.")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO, format="%(levelname)s %(message)s")
    if not self_test():
        print("Error: non-vacuity self-test FAILED; the real comparison cannot be trusted.", file=sys.stderr)
        return EXIT_USAGE
    if args.self_test:
        return EXIT_OK
    try:
        baseline = load_baseline()
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    censuses = scan_all_registered_languages()
    evaluation = evaluate(FRAMEWORK_PROBLEM_TYPES, censuses)
    problems = evaluation.problems + ratchet_problems(evaluation.unspelled, baseline, frozenset(censuses))
    print(f"\nProblem-type census ({len(censuses)} registered language(s), "
          f"{len(FRAMEWORK_PROBLEM_TYPES)} families):")
    print(render_report(FRAMEWORK_PROBLEM_TYPES, evaluation.verdicts))
    for language in sorted(evaluation.unspelled):
        for family in evaluation.unspelled[language]:
            print(f"PINNED GAP language={language} family={family}")
    if problems:
        print(f"\nError: {len(problems)} problem-type parity violation(s):", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return EXIT_FAIL
    pinned_cells = sum(len(cells) for cells in evaluation.unspelled.values())
    print(f"\nEvery registered language spells every registry family except the {pinned_cells} "
          f"unspelled cell(s) pinned in {BASELINE_PATH.name}.")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
