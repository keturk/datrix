"""Problem-type parity gate -- every registered language answers errors with
RFC 7807 ``type`` URNs from one registry and realizes every framework family
or declares the hole.

A generated service's error body carries a ``type`` member naming the error
class. A client keyed on it must see one vocabulary whichever language served
the request, so the vocabulary has one home:
``datrix_common.generation.problem_types`` (``urn:datrix:error:<slug>``; a
declared DSL exception derives its slug from its class name through the
shared exception-declaration algorithm, a framework error uses a registered
family). Before this gate, python and java spelled the URNs, typescript
composed ``https://api.example.com/<service>/errors/<slug>`` and .NET emitted
``https://httpstatuses.com/<status>`` for everything.

The gate censuses the ``.py`` and ``.j2`` sources under every registered
language package for ``urn:datrix:error:`` literals and holds each language to:

* **Spelling.** Every literal slug is a registered family. A private slug is a
  defect with no exemption path: register the family or spell the registered
  one. (A slug the generator composes at runtime for a declared exception is
  not a literal and is minted by the shared algorithm.)
* **Realization.** Every registered family is spelled by the language or
  declared unrealized with a reason on its
  ``LanguageCapabilityDeclaration.unrealized_problem_types``. Neither fails
  naming the language and family; both is a stale declaration and fails; a
  family no language spells is a dead registry entry and fails.

Language set from the installed ``datrix.languages`` entry points at runtime;
registry from datrix-common at runtime; holes from each language's own
declaration -- never a table in this script. Runs a built-in non-vacuity
self-test on every invocation. Repo-level validation script (per the datrix
showcase boundary -- no pytest suite lives in datrix).
"""

from __future__ import annotations

import argparse
import logging
import re
import shutil
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

_LIBRARY_DIR = Path(__file__).resolve().parent.parent
if _LIBRARY_DIR.exists() and str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from datrix_common.generation.problem_types import (  # noqa: E402
    FRAMEWORK_PROBLEM_TYPES,
    PROBLEM_TYPE_URN_PREFIX,
    ProblemType,
)
from datrix_common.plugin.capability_resolution import declaration_for_language  # noqa: E402

from shared.registered_targets import registered_language_names  # noqa: E402
from test.parallel_implementation_drift import (  # noqa: E402
    AXIS_LANGUAGES,
    WORKSPACE_ROOT,
    discover_target_package_src_dirs,
)

logger = logging.getLogger(__name__)

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


@dataclass(frozen=True, slots=True)
class Spelling:
    language: str
    relative_path: str
    line: int
    slug: str


@dataclass(frozen=True, slots=True)
class LanguageCensus:
    language: str
    package: str
    spellings: tuple[Spelling, ...]


def _iter_source_files(src_dir: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(src_dir.rglob("*")):
        if not path.is_file() or path.suffix not in _SOURCE_SUFFIXES:
            continue
        if any(part in _SKIP_DIR_NAMES for part in path.relative_to(src_dir).parts):
            continue
        files.append(path)
    return files


def census_source(language: str, package: str, src_dir: Path) -> LanguageCensus:
    """Every literal ``urn:datrix:error:<slug>`` under ``src_dir`` (``.py`` and ``.j2``)."""
    spellings: list[Spelling] = []
    for path in _iter_source_files(src_dir):
        relative = path.relative_to(src_dir).as_posix()
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for match in _URN_LITERAL_RE.finditer(line):
                spellings.append(Spelling(language, relative, line_number, match.group(1)))
    return LanguageCensus(language, package, tuple(spellings))


@dataclass(frozen=True, slots=True)
class LanguageVerdict:
    language: str
    realized: frozenset[str]
    declared_holes: frozenset[str]


def realized_families(census: LanguageCensus, registry: tuple[ProblemType, ...]) -> frozenset[str]:
    families = {problem_type.family for problem_type in registry}
    return frozenset(spelling.slug for spelling in census.spellings if spelling.slug in families)


def evaluate(
    registry: tuple[ProblemType, ...],
    censuses: Mapping[str, LanguageCensus],
    declared_holes: Mapping[str, Mapping[str, str]],
) -> tuple[list[str], dict[str, LanguageVerdict]]:
    families = frozenset(problem_type.family for problem_type in registry)
    problems: list[str] = []
    verdicts: dict[str, LanguageVerdict] = {}
    for language in sorted(censuses):
        census = censuses[language]
        for spelling in census.spellings:
            if spelling.slug not in families:
                problems.append(
                    f"{census.package}: {spelling.relative_path}:{spelling.line}: spells "
                    f"{PROBLEM_TYPE_URN_PREFIX}{spelling.slug!s}, which is not a registered "
                    f"problem-type family. Fix: spell a registered family, or register it in "
                    f"datrix_common.generation.problem_types so every target mints it."
                )
        holes = declared_holes.get(language, {})
        for family, reason in sorted(holes.items()):
            if family not in families:
                problems.append(
                    f"{language}: declares unrealized_problem_types[{family!r}], which is not a "
                    f"registered family. Registered: {', '.join(sorted(families))}."
                )
            elif not reason.strip():
                problems.append(
                    f"{language}: unrealized_problem_types[{family!r}] carries an empty reason."
                )
        realized = realized_families(census, registry)
        hole_set = frozenset(holes)
        for family in sorted(families):
            if family in realized and family in hole_set:
                problems.append(
                    f"{language}: declares problem type {family!r} unrealized, but its sources "
                    f"spell it. Fix: remove the stale declaration."
                )
            elif family not in realized and family not in hole_set:
                problems.append(
                    f"{language}: neither spells problem type {PROBLEM_TYPE_URN_PREFIX}{family} "
                    f"nor declares it unrealized. Fix: answer with the registered URN, or declare "
                    f"the hole with a reason on unrealized_problem_types."
                )
        verdicts[language] = LanguageVerdict(language, realized, hole_set)
    realized_anywhere = frozenset().union(*(verdict.realized for verdict in verdicts.values()))
    for family in sorted(families - realized_anywhere):
        problems.append(
            f"registry: problem type {family!r} is spelled by no registered language. A type "
            f"nobody mints is a dead contract. Fix: realize it or remove it from the registry."
        )
    return problems, verdicts


def _require_min_languages(language_names: frozenset[str]) -> None:
    if len(language_names) < _MIN_LANGUAGES_FOR_COMPARISON:
        print(
            f"Error: {len(language_names)} registered language(s) "
            f"({', '.join(sorted(language_names)) or 'none'}); a cross-language parity gate "
            f"needs at least {_MIN_LANGUAGES_FOR_COMPARISON}. Install the language packages.",
            file=sys.stderr,
        )
        raise SystemExit(EXIT_USAGE)


def scan_all_registered_languages() -> tuple[dict[str, LanguageCensus], dict[str, Mapping[str, str]]]:
    language_names = registered_language_names()
    _require_min_languages(language_names)
    src_dirs = discover_target_package_src_dirs(AXIS_LANGUAGES, language_names, WORKSPACE_ROOT)
    censuses: dict[str, LanguageCensus] = {}
    holes: dict[str, Mapping[str, str]] = {}
    for language, src_dir in sorted(src_dirs.items()):
        # ``src_dir`` is ``<package>/src/<import_name>``.
        package = src_dir.parents[1].name
        censuses[language] = census_source(language, package, src_dir)
        holes[language] = declaration_for_language(language).unrealized_problem_types
        logger.debug(
            "census language=%s package=%s spellings=%d",
            language, package, len(censuses[language].spellings),
        )
    return censuses, holes


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
            elif problem_type.family in verdict.declared_holes:
                cells.append("declared".ljust(10))
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


def _planted(language: str, slugs: tuple[str, ...]) -> LanguageCensus:
    spellings = tuple(Spelling(language, "planted.j2", i + 1, slug) for i, slug in enumerate(slugs))
    return LanguageCensus(language, f"datrix-codegen-{language}", spellings)


def _self_test_comparator(registry: tuple[ProblemType, ...]) -> bool:
    ok = True
    full = tuple(problem_type.family for problem_type in registry)
    clean = {"alpha": _planted("alpha", full), "beta": _planted("beta", full)}
    problems, _ = evaluate(registry, clean, {})
    ok &= _assert(problems == [], "two fully realizing languages report no problem")

    private = {"alpha": _planted("alpha", full + ("private-thing",)), "beta": clean["beta"]}
    problems, _ = evaluate(registry, private, {})
    ok &= _assert(len(problems) == 1 and "not a registered problem-type family" in problems[0],
                  "an unregistered literal slug is one problem")

    missing = full[-1]
    partial_slugs = full[:-1]
    partial = {"alpha": _planted("alpha", partial_slugs), "beta": clean["beta"]}
    problems, _ = evaluate(registry, partial, {})
    ok &= _assert(len(problems) == 1 and missing in problems[0] and "neither spells" in problems[0],
                  "an undeclared unrealized family is one problem")
    problems, verdicts = evaluate(registry, partial, {"alpha": {missing: "planted reason"}})
    ok &= _assert(problems == [], "a declared hole with a reason passes")
    ok &= _assert(missing in verdicts["alpha"].declared_holes, "the verdict records the declared hole")
    problems, _ = evaluate(registry, partial, {"alpha": {missing: " "}})
    ok &= _assert(len(problems) == 1 and "empty reason" in problems[0], "a reasonless hole is one problem")
    problems, _ = evaluate(registry, clean, {"alpha": {missing: "planted"}})
    ok &= _assert(len(problems) == 1 and "stale declaration" in problems[0],
                  "a spelled-but-declared family is one problem")
    problems, _ = evaluate(registry, clean, {"alpha": {"no-such-family": "planted"}})
    ok &= _assert(len(problems) == 1 and "not a registered family" in problems[0],
                  "an unknown family in a declaration is one problem")
    nobody = {"alpha": _planted("alpha", partial_slugs), "beta": _planted("beta", partial_slugs)}
    problems, _ = evaluate(registry, nobody, {"alpha": {missing: "p"}, "beta": {missing: "p"}})
    ok &= _assert(len(problems) == 1 and "dead contract" in problems[0], "a family nobody spells is one problem")
    return ok


def _self_test_census(tmp_root: Path) -> bool:
    src = tmp_root / "datrix-codegen-fixture" / "src" / "pkg"
    (src / "templates").mkdir(parents=True)
    (src / "__pycache__").mkdir()
    (src / "templates" / "planted.j2").write_text(
        "type = 'urn:datrix:error:validation'\n"
        "prefix = 'urn:datrix:error:'\n"
        "other = `${PREFIX}http-${status}`\n",
        encoding="utf-8",
    )
    (src / "handler.py").write_text('URN = "urn:datrix:error:internal"\n', encoding="utf-8")
    (src / "notes.md").write_text("urn:datrix:error:ignored-because-markdown\n", encoding="utf-8")
    (src / "__pycache__" / "stale.py").write_text("'urn:datrix:error:ignored-because-cache'\n", encoding="utf-8")
    census = census_source("fixture", "datrix-codegen-fixture", src)
    slugs = sorted(spelling.slug for spelling in census.spellings)
    return _assert(
        slugs == ["internal", "validation"],
        f"planted sources yield exactly their two literal slugs; the bare prefix is not one (got {slugs})",
    )


def _self_test_live_read() -> bool:
    censuses, _ = scan_all_registered_languages()
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
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    ok &= _self_test_comparator(FRAMEWORK_PROBLEM_TYPES)
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
    censuses, holes = scan_all_registered_languages()
    problems, verdicts = evaluate(FRAMEWORK_PROBLEM_TYPES, censuses, holes)
    print(f"\nProblem-type census ({len(censuses)} registered language(s), "
          f"{len(FRAMEWORK_PROBLEM_TYPES)} families):")
    print(render_report(FRAMEWORK_PROBLEM_TYPES, verdicts))
    if problems:
        print(f"\nError: {len(problems)} problem-type parity violation(s):", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return EXIT_FAIL
    print("\nEvery registered language spells problem types from the registry and realizes or "
          "declares every family.")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
