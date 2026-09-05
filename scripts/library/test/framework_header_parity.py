"""Framework header parity gate -- every registered language spells the
framework-minted HTTP headers from one registry and realizes every family or
declares the hole.

A generated service exchanges a handful of headers Datrix itself defines: the
trusted-caller token on an inter-service call, the delegated-user envelope,
the three rate-limit response headers, the inbound webhook shared secret and
the outbound webhook delivery headers. Each is a cross-language wire contract
(a python caller and a java callee must spell the same name), and each has one
home: ``datrix_common.generation.http_headers``. Two things went wrong before
this gate existed. Java re-typed the caller header as a private
``X-Datrix-Trusted-Caller`` with a different mechanism behind it, so a python
caller and a java callee could never talk. And a typescript test template kept
sending the retired ``X-Internal-Token`` long after every guard had moved on,
so the generated test exercised a header nothing reads.

The gate holds every registered language to two rules, from a census of the
``.py`` and ``.j2`` sources under its package:

* **Spelling.** A header under a framework prefix (``X-Datrix-``,
  ``X-RateLimit-``, ``X-Webhook-``) is either an exact registered name or a
  reviewed, counted exemption in
  ``scripts/config/framework-header-exemptions.json``. A retired name is a
  violation with no exemption path.
* **Realization.** Every registered family is realized by the language (its
  exact name spelled, or its registry constant referenced from python) or
  declared unrealized with a reason on that language's
  ``LanguageCapabilityDeclaration.unrealized_framework_headers``. Neither
  fails naming the language and the family; both at once is a stale
  declaration and fails too. A family no language realizes is a dead registry
  entry and fails.

Language set from the installed ``datrix.languages`` entry points at runtime;
registry from datrix-common at runtime; holes from each language's own
declaration -- never a table in this script. Runs a built-in non-vacuity
self-test on every invocation. Repo-level validation script (per the datrix
showcase boundary -- no pytest suite lives in datrix).
"""

from __future__ import annotations

import argparse
import json
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

from datrix_common.generation import http_headers as registry_module  # noqa: E402
from datrix_common.generation.http_headers import (  # noqa: E402
    FRAMEWORK_HEADER_PREFIXES,
    FRAMEWORK_HEADERS,
    RETIRED_HEADERS,
    FrameworkHeader,
)
from datrix_common.plugin.capability_resolution import declaration_for_language  # noqa: E402

from shared.registered_targets import registered_language_names  # noqa: E402
from test.parallel_implementation_drift import (  # noqa: E402
    AXIS_LANGUAGES,
    WORKSPACE_ROOT,
    discover_target_package_src_dirs,
)

logger = logging.getLogger(__name__)

_HERE = Path(__file__).resolve()
DATRIX_DIR: Final[Path] = _HERE.parents[3]
EXEMPTIONS_PATH: Final[Path] = (
    DATRIX_DIR / "scripts" / "config" / "framework-header-exemptions.json"
)

EXIT_OK: Final[int] = 0
EXIT_FAIL: Final[int] = 1
EXIT_USAGE: Final[int] = 2

#: The sources a language package emits headers from: templates carry the
#: spelled names; python carries registry-constant references and the literal
#: strings a generator assembles into emitted code.
_SOURCE_SUFFIXES: Final[frozenset[str]] = frozenset({".py", ".j2"})
_SKIP_DIR_NAMES: Final[frozenset[str]] = frozenset({"__pycache__", "node_modules"})
_MIN_LANGUAGES_FOR_COMPARISON: Final[int] = 2

#: Any ``X-``-prefixed header token; classification by framework prefix is a
#: separate, case-insensitive step so a lowercased spelling (Node lowercases
#: header names) is still the registered name.
_HEADER_TOKEN_RE: Final[re.Pattern[str]] = re.compile(
    r"(?<![A-Za-z0-9_])[Xx]-[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)+(?![A-Za-z0-9_-])"
)


# ---------------------------------------------------------------------------
# Registry view
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Registry:
    """The registry facts the comparator needs, in one immutable value."""

    headers: tuple[FrameworkHeader, ...]
    prefixes: tuple[str, ...]
    retired: tuple[str, ...]
    constant_families: Mapping[str, str]
    """``{python constant name: family}`` -- a ``.py`` file referencing the
    constant realizes the family without spelling the wire name."""

    def family_by_name(self) -> dict[str, str]:
        return {header.name.lower(): header.family for header in self.headers}

    def families(self) -> frozenset[str]:
        return frozenset(header.family for header in self.headers)

    def is_framework_prefixed(self, name: str) -> bool:
        lowered = name.lower()
        return any(lowered.startswith(prefix.lower()) for prefix in self.prefixes)

    def is_retired(self, name: str) -> bool:
        lowered = name.lower()
        return any(lowered == retired.lower() for retired in self.retired)


def registry_constant_families() -> dict[str, str]:
    """Derive ``{constant name: family}`` from the registry module's own
    exports, so a new family's constant is recognized with no edit here."""
    by_name = {header.name.lower(): header.family for header in FRAMEWORK_HEADERS}
    families: dict[str, str] = {}
    for exported in registry_module.__all__:
        if not exported.isupper():
            continue
        value = getattr(registry_module, exported)
        if isinstance(value, str) and value.lower() in by_name:
            families[exported] = by_name[value.lower()]
    return families


def live_registry() -> Registry:
    return Registry(
        headers=FRAMEWORK_HEADERS,
        prefixes=FRAMEWORK_HEADER_PREFIXES,
        retired=RETIRED_HEADERS,
        constant_families=registry_constant_families(),
    )


# ---------------------------------------------------------------------------
# Census
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Spelling:
    """One ``X-``-prefixed header token found in a language package source."""

    language: str
    relative_path: str
    line: int
    name: str


@dataclass(frozen=True, slots=True)
class LanguageCensus:
    language: str
    package: str
    spellings: tuple[Spelling, ...]
    constant_references: frozenset[str]
    """Registry constant names referenced from this package's ``.py`` files."""


def _iter_source_files(src_dir: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(src_dir.rglob("*")):
        if not path.is_file() or path.suffix not in _SOURCE_SUFFIXES:
            continue
        if any(part in _SKIP_DIR_NAMES for part in path.relative_to(src_dir).parts):
            continue
        files.append(path)
    return files


def census_source(language: str, package: str, src_dir: Path, registry: Registry) -> LanguageCensus:
    """Every ``X-`` header token and every registry-constant reference under
    ``src_dir`` (``.py`` and ``.j2`` only)."""
    constant_patterns = {
        name: re.compile(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])")
        for name in registry.constant_families
    }
    spellings: list[Spelling] = []
    constant_references: set[str] = set()
    for path in _iter_source_files(src_dir):
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(src_dir).as_posix()
        for line_number, line in enumerate(text.splitlines(), start=1):
            for match in _HEADER_TOKEN_RE.finditer(line):
                spellings.append(Spelling(language, relative, line_number, match.group(0)))
        if path.suffix == ".py":
            for name, pattern in constant_patterns.items():
                if pattern.search(text):
                    constant_references.add(name)
    return LanguageCensus(language, package, tuple(spellings), frozenset(constant_references))


# ---------------------------------------------------------------------------
# Exemptions
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Exemption:
    package: str
    header: str
    family: str
    reason: str

    def matches(self, package: str, header: str) -> bool:
        return self.package == package and self.header.lower() == header.lower()


def parse_exemptions(payload: Mapping[str, object], registry: Registry) -> tuple[Exemption, ...]:
    """Validate the exemption file's shape: a pinned count that equals the
    entry count, and every entry carrying package, header, a registered
    family and a non-empty reason."""
    raw_entries = payload.get("exemptions")
    if not isinstance(raw_entries, list):
        raise ValueError("framework-header-exemptions.json: 'exemptions' must be a list.")
    expected_count = payload.get("expected_count")
    if not isinstance(expected_count, int) or expected_count != len(raw_entries):
        raise ValueError(
            f"framework-header-exemptions.json: expected_count={expected_count!r} does not "
            f"equal the {len(raw_entries)} listed entries. Fix: remove or add the entry AND "
            f"update expected_count in the same change."
        )
    families = registry.families()
    exemptions: list[Exemption] = []
    for index, entry in enumerate(raw_entries):
        if not isinstance(entry, dict):
            raise ValueError(f"framework-header-exemptions.json: entry {index} is not an object.")
        package = entry.get("package")
        header = entry.get("header")
        family = entry.get("family")
        reason = entry.get("reason")
        if not all(isinstance(value, str) and value.strip() for value in (package, header, family, reason)):
            raise ValueError(
                f"framework-header-exemptions.json: entry {index} must carry non-empty "
                f"'package', 'header', 'family' and 'reason' strings."
            )
        assert isinstance(package, str) and isinstance(header, str)
        assert isinstance(family, str) and isinstance(reason, str)
        if family not in families:
            raise ValueError(
                f"framework-header-exemptions.json: entry {index} names unknown family "
                f"{family!r}. Registered families: {', '.join(sorted(families))}."
            )
        if not registry.is_framework_prefixed(header):
            raise ValueError(
                f"framework-header-exemptions.json: entry {index} header {header!r} carries no "
                f"framework prefix ({', '.join(registry.prefixes)}); only framework-prefixed "
                f"spellings need an exemption."
            )
        exemptions.append(Exemption(package, header, family, reason))
    return tuple(exemptions)


def load_exemptions(registry: Registry) -> tuple[Exemption, ...]:
    if not EXEMPTIONS_PATH.is_file():
        raise ValueError(f"Exemption file not found: {EXEMPTIONS_PATH}")
    payload = json.loads(EXEMPTIONS_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("framework-header-exemptions.json: top level must be an object.")
    return parse_exemptions(payload, registry)


# ---------------------------------------------------------------------------
# Comparator
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LanguageVerdict:
    language: str
    realized: frozenset[str]
    declared_holes: frozenset[str]


def realized_families(census: LanguageCensus, registry: Registry) -> frozenset[str]:
    by_name = registry.family_by_name()
    realized = {
        by_name[spelling.name.lower()]
        for spelling in census.spellings
        if spelling.name.lower() in by_name
    }
    realized.update(
        registry.constant_families[name] for name in census.constant_references
    )
    return frozenset(realized)


def _spelling_problems(
    census: LanguageCensus,
    registry: Registry,
    exemptions: tuple[Exemption, ...],
    used_exemptions: set[Exemption],
) -> list[str]:
    by_name = registry.family_by_name()
    problems: list[str] = []
    for spelling in census.spellings:
        where = f"{census.package}: {spelling.relative_path}:{spelling.line}"
        if registry.is_retired(spelling.name):
            problems.append(
                f"{where}: spells RETIRED framework header {spelling.name!r}. No consumer reads "
                f"it. Fix: use the registered header for the contract "
                f"(datrix_common.generation.http_headers) and delete the spelling."
            )
            continue
        if spelling.name.lower() in by_name or not registry.is_framework_prefixed(spelling.name):
            continue
        exemption = next(
            (entry for entry in exemptions if entry.matches(census.package, spelling.name)), None,
        )
        if exemption is None:
            problems.append(
                f"{where}: spells {spelling.name!r}, a framework-prefixed header that is not a "
                f"registered name. Fix: spell the registered name for its family, or add a "
                f"reviewed entry to {EXEMPTIONS_PATH.name} with a reason and bump expected_count."
            )
            continue
        used_exemptions.add(exemption)
    return problems


def _realization_problems(
    census: LanguageCensus,
    registry: Registry,
    declared_holes: Mapping[str, str],
) -> tuple[list[str], LanguageVerdict]:
    realized = realized_families(census, registry)
    families = registry.families()
    problems: list[str] = []
    for family, reason in sorted(declared_holes.items()):
        if family not in families:
            problems.append(
                f"{census.language}: declares unrealized_framework_headers[{family!r}], which is "
                f"not a registered family. Registered: {', '.join(sorted(families))}."
            )
        elif not reason.strip():
            problems.append(
                f"{census.language}: unrealized_framework_headers[{family!r}] carries an empty "
                f"reason. Fix: state why the language does not realize the family."
            )
    holes = frozenset(declared_holes)
    for family in sorted(families):
        if family in realized and family in holes:
            problems.append(
                f"{census.language}: declares family {family!r} unrealized, but its sources "
                f"realize it. Fix: remove the stale declaration."
            )
        elif family not in realized and family not in holes:
            problems.append(
                f"{census.language}: neither realizes family {family!r} nor declares it "
                f"unrealized. Fix: emit the registered header, or declare the hole with a reason "
                f"on the language's LanguageCapabilityDeclaration.unrealized_framework_headers."
            )
    return problems, LanguageVerdict(census.language, realized, holes)


def evaluate(
    registry: Registry,
    censuses: Mapping[str, LanguageCensus],
    declared_holes: Mapping[str, Mapping[str, str]],
    exemptions: tuple[Exemption, ...],
) -> tuple[list[str], dict[str, LanguageVerdict]]:
    """Every violation across every language, plus the per-language verdicts
    the report table renders."""
    problems: list[str] = []
    verdicts: dict[str, LanguageVerdict] = {}
    used_exemptions: set[Exemption] = set()
    for language in sorted(censuses):
        census = censuses[language]
        problems.extend(_spelling_problems(census, registry, exemptions, used_exemptions))
        realization_problems, verdict = _realization_problems(
            census, registry, declared_holes.get(language, {}),
        )
        problems.extend(realization_problems)
        verdicts[language] = verdict
    for exemption in exemptions:
        if exemption not in used_exemptions:
            problems.append(
                f"{EXEMPTIONS_PATH.name}: stale entry {exemption.package} / {exemption.header!r} "
                f"-- the package no longer spells it. Fix: remove the entry and decrement "
                f"expected_count."
            )
    realized_anywhere = frozenset().union(*(verdict.realized for verdict in verdicts.values()))
    for family in sorted(registry.families() - realized_anywhere):
        problems.append(
            f"registry: family {family!r} is realized by no registered language. A header nobody "
            f"emits is a dead contract. Fix: realize it or remove it from the registry."
        )
    return problems, verdicts


# ---------------------------------------------------------------------------
# Live scan
# ---------------------------------------------------------------------------


def _require_min_languages(language_names: frozenset[str]) -> None:
    if len(language_names) < _MIN_LANGUAGES_FOR_COMPARISON:
        print(
            f"Error: {len(language_names)} registered language(s) "
            f"({', '.join(sorted(language_names)) or 'none'}); a cross-language parity gate "
            f"needs at least {_MIN_LANGUAGES_FOR_COMPARISON}. Install the language packages.",
            file=sys.stderr,
        )
        raise SystemExit(EXIT_USAGE)


def scan_all_registered_languages(
    registry: Registry,
) -> tuple[dict[str, LanguageCensus], dict[str, Mapping[str, str]]]:
    language_names = registered_language_names()
    _require_min_languages(language_names)
    src_dirs = discover_target_package_src_dirs(AXIS_LANGUAGES, language_names, WORKSPACE_ROOT)
    censuses: dict[str, LanguageCensus] = {}
    holes: dict[str, Mapping[str, str]] = {}
    for language, src_dir in sorted(src_dirs.items()):
        # ``src_dir`` is ``<package>/src/<import_name>``; the package repo is
        # two levels up and is what the exemption file keys on.
        package = src_dir.parents[1].name
        censuses[language] = census_source(language, package, src_dir, registry)
        holes[language] = declaration_for_language(language).unrealized_framework_headers
        logger.debug(
            "census language=%s package=%s spellings=%d constant_refs=%s",
            language, package, len(censuses[language].spellings),
            sorted(censuses[language].constant_references),
        )
    return censuses, holes


def render_report(registry: Registry, verdicts: Mapping[str, LanguageVerdict]) -> str:
    languages = sorted(verdicts)
    width = max(len("family"), *(len(header.family) for header in registry.headers))
    lines = ["  " + "family".ljust(width) + "  " + "  ".join(lang.ljust(10) for lang in languages)]
    for header in registry.headers:
        cells: list[str] = []
        for language in languages:
            verdict = verdicts[language]
            if header.family in verdict.realized:
                cells.append("realized".ljust(10))
            elif header.family in verdict.declared_holes:
                cells.append("declared".ljust(10))
            else:
                cells.append("MISSING".ljust(10))
        lines.append("  " + header.family.ljust(width) + "  " + "  ".join(cells))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Non-vacuity self-test
# ---------------------------------------------------------------------------


def _assert(condition: bool, label: str) -> bool:
    print(f"  {'PASS' if condition else 'FAIL'}: {label}")
    return condition


def _planted_census(
    language: str, names: tuple[str, ...], constants: frozenset[str] = frozenset(),
) -> LanguageCensus:
    spellings = tuple(Spelling(language, "planted.j2", index + 1, name) for index, name in enumerate(names))
    return LanguageCensus(language, f"datrix-codegen-{language}", spellings, constants)


def _all_names(registry: Registry) -> tuple[str, ...]:
    return tuple(header.name for header in registry.headers)


def _self_test_comparator(registry: Registry) -> bool:
    ok = True
    full = _all_names(registry)
    clean = {"alpha": _planted_census("alpha", full), "beta": _planted_census("beta", full)}
    problems, _ = evaluate(registry, clean, {}, ())
    ok &= _assert(problems == [], "two fully realizing languages report no problem")

    retired = {"alpha": _planted_census("alpha", full + (registry.retired[0],)), "beta": clean["beta"]}
    problems, _ = evaluate(registry, retired, {}, ())
    ok &= _assert(len(problems) == 1 and "RETIRED" in problems[0], "a retired spelling is one problem")

    private = {"alpha": _planted_census("alpha", full + ("X-Datrix-Private-Thing",)), "beta": clean["beta"]}
    problems, _ = evaluate(registry, private, {}, ())
    ok &= _assert(
        len(problems) == 1 and "not a registered name" in problems[0],
        "an unregistered framework-prefixed spelling is one problem",
    )
    exemption = Exemption("datrix-codegen-alpha", "x-datrix-private-thing", "caller_token", "planted")
    problems, _ = evaluate(registry, private, {}, (exemption,))
    ok &= _assert(problems == [], "an exempted private spelling passes (case-insensitively)")
    problems, _ = evaluate(registry, clean, {}, (exemption,))
    ok &= _assert(len(problems) == 1 and "stale entry" in problems[0], "an unused exemption is one problem")

    foreign = {"alpha": _planted_census("alpha", full + ("X-Forwarded-For",)), "beta": clean["beta"]}
    problems, _ = evaluate(registry, foreign, {}, ())
    ok &= _assert(problems == [], "a non-framework X- header is not counted")

    missing_family = registry.headers[-1].family
    partial_names = tuple(name for name in full if name != registry.headers[-1].name)
    partial = {"alpha": _planted_census("alpha", partial_names), "beta": clean["beta"]}
    problems, _ = evaluate(registry, partial, {}, ())
    ok &= _assert(
        len(problems) == 1 and missing_family in problems[0] and "neither realizes" in problems[0],
        "an undeclared unrealized family is one problem",
    )
    problems, verdicts = evaluate(registry, partial, {"alpha": {missing_family: "planted reason"}}, ())
    ok &= _assert(problems == [], "a declared hole with a reason passes")
    ok &= _assert(missing_family in verdicts["alpha"].declared_holes, "the verdict records the declared hole")
    problems, _ = evaluate(registry, partial, {"alpha": {missing_family: "  "}}, ())
    ok &= _assert(len(problems) == 1 and "empty reason" in problems[0], "a reasonless hole is one problem")
    problems, _ = evaluate(registry, clean, {"alpha": {missing_family: "planted"}}, ())
    ok &= _assert(len(problems) == 1 and "stale declaration" in problems[0], "a realized-but-declared family is one problem")
    problems, _ = evaluate(registry, clean, {"alpha": {"no_such_family": "planted"}}, ())
    ok &= _assert(len(problems) == 1 and "not a registered family" in problems[0], "an unknown family in a declaration is one problem")

    nobody = {"alpha": _planted_census("alpha", partial_names), "beta": _planted_census("beta", partial_names)}
    holes = {"alpha": {missing_family: "planted"}, "beta": {missing_family: "planted"}}
    problems, _ = evaluate(registry, nobody, holes, ())
    ok &= _assert(len(problems) == 1 and "dead contract" in problems[0], "a family nobody realizes is one problem")

    constant_name = next(iter(registry.constant_families))
    via_constant = {
        "alpha": _planted_census(
            "alpha",
            tuple(n for n in full if n.lower() != _name_of_constant(registry, constant_name).lower()),
            frozenset({constant_name}),
        ),
        "beta": clean["beta"],
    }
    problems, _ = evaluate(registry, via_constant, {}, ())
    ok &= _assert(problems == [], "a registry constant reference realizes its family")
    return ok


def _name_of_constant(registry: Registry, constant_name: str) -> str:
    family = registry.constant_families[constant_name]
    return next(header.name for header in registry.headers if header.family == family)


def _self_test_census(tmp_root: Path, registry: Registry) -> bool:
    src = tmp_root / "datrix-codegen-fixture" / "src"
    (src / "templates").mkdir(parents=True)
    (src / "__pycache__").mkdir()
    (src / "templates" / "planted.j2").write_text(
        "headers['X-RateLimit-Limit'] = 1\nconst h = 'x-webhook-secret';\n", encoding="utf-8",
    )
    (src / "generator.py").write_text(
        "from datrix_common.generation.http_headers import CALLER_TOKEN_HEADER\n", encoding="utf-8",
    )
    (src / "notes.md").write_text("X-Datrix-Ignored-Because-Markdown\n", encoding="utf-8")
    (src / "__pycache__" / "stale.py").write_text("'X-Datrix-Ignored-Because-Cache'\n", encoding="utf-8")
    census = census_source("fixture", "datrix-codegen-fixture", src, registry)
    names = sorted(spelling.name for spelling in census.spellings)
    ok = _assert(
        names == ["X-RateLimit-Limit", "x-webhook-secret"],
        f"planted template yields exactly its two spellings (got {names})",
    )
    ok &= _assert(
        census.constant_references == frozenset({"CALLER_TOKEN_HEADER"}),
        "a python constant reference is censused",
    )
    ok &= _assert(
        realized_families(census, registry) == frozenset({"rate_limit_limit", "webhook_secret", "caller_token"}),
        "realized families come from spellings (case-insensitively) and constant references",
    )
    return ok


def _self_test_exemption_parsing(registry: Registry) -> bool:
    ok = True
    good = {"expected_count": 1, "exemptions": [
        {"package": "p", "header": "X-Datrix-Thing", "family": "caller_token", "reason": "r"},
    ]}
    ok &= _assert(len(parse_exemptions(good, registry)) == 1, "a well-formed exemption file parses")
    for label, payload in (
        ("a miscounted file is rejected", {**good, "expected_count": 2}),
        ("an unknown family is rejected", {"expected_count": 1, "exemptions": [{**good["exemptions"][0], "family": "nope"}]}),
        ("a non-framework header is rejected", {"expected_count": 1, "exemptions": [{**good["exemptions"][0], "header": "X-Forwarded-For"}]}),
        ("a reasonless entry is rejected", {"expected_count": 1, "exemptions": [{**good["exemptions"][0], "reason": " "}]}),
    ):
        try:
            parse_exemptions(payload, registry)
            ok &= _assert(False, label)
        except ValueError:
            ok &= _assert(True, label)
    return ok


def _self_test_live_read(registry: Registry) -> bool:
    """The live census must see a real, known realization: the caller token
    on at least two languages. A scan that finds nothing is broken, not clean."""
    censuses, _ = scan_all_registered_languages(registry)
    realizers = sorted(
        language for language, census in censuses.items()
        if "caller_token" in realized_families(census, registry)
    )
    return _assert(
        len(realizers) >= _MIN_LANGUAGES_FOR_COMPARISON,
        f"live census finds the caller-token header on >= 2 languages (found: {realizers})",
    )


def self_test() -> bool:
    print("Non-vacuity self-test:")
    registry = live_registry()
    ok = _assert(len(registry.constant_families) >= 1, "the registry exports at least one header constant")
    tmp_root = Path(tempfile.mkdtemp(prefix="framework-header-gate-"))
    try:
        ok &= _self_test_census(tmp_root, registry)
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    ok &= _self_test_comparator(registry)
    ok &= _self_test_exemption_parsing(registry)
    ok &= _self_test_live_read(registry)
    return ok


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--debug", action="store_true", help="Enable debug logging.")
    parser.add_argument("--self-test", action="store_true", help="Run only the non-vacuity self-test.")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    if not self_test():
        print("Error: non-vacuity self-test FAILED; the real comparison cannot be trusted.", file=sys.stderr)
        return EXIT_USAGE
    if args.self_test:
        return EXIT_OK

    registry = live_registry()
    try:
        exemptions = load_exemptions(registry)
        censuses, holes = scan_all_registered_languages(registry)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    problems, verdicts = evaluate(registry, censuses, holes, exemptions)
    print(f"\nFramework header census ({len(censuses)} registered language(s), "
          f"{len(registry.headers)} families, {len(exemptions)} reviewed exemption(s)):")
    print(render_report(registry, verdicts))
    if problems:
        print(f"\nError: {len(problems)} framework-header parity violation(s):", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return EXIT_FAIL
    print("\nEvery registered language spells the framework headers from the registry and "
          "realizes or declares every family.")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
