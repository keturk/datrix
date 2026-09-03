#!/usr/bin/env python3
"""Zero-environment runtime census gate -- every registered language is held
to the posture it declares.

The zero-environment runtime architecture bakes every deployment-static value
a generated service needs into literal constants at generation time, so the
running service consults no environment variable. That is a portable
decision, but its realization is per language, and a portable contract is
only portable if the targets that decline it say so out loud. Each language
plugin therefore declares its posture on its ``LanguageCapabilityDeclaration``
(``zero_environment_runtime``: realized or not, with the regular expressions
that spell an environment read in that language's own templates and, when
unrealized, a written reason). This gate is the census that holds every
language to that declaration:

* A language declaring the contract **realized** may carry environment reads
  only as reviewed, written exemptions in the baseline file. Every template
  that reads the environment must have an entry with a reason, and every
  entry must still match a real read -- an unlisted read and a stale entry
  are both violations.
* A language declaring the contract **unrealized** carries a pinned,
  decrease-only count of templates that read the environment. The count may
  fall (``--update-baseline`` re-pins it downward) and may never rise.
* A registered language that declares nothing fails the gate, naming it.

The language set is derived from the installed ``datrix.languages`` entry
points at runtime, never a hardcoded list, and each language's idiom comes
from its own declaration, never a table in this script. Templates are every
``.j2`` file under the language package's ``src/`` tree; test-harness
templates count too, because a harness that reads the environment is still
emitted into the generated project -- a realized language lists them as
exemptions with that reason.

Runs a built-in non-vacuity self-test on every invocation: a synthetic
template tree with one planted read and one clean file, the comparator
against realized and unrealized synthetic declarations (missing exemption,
stale exemption, count over and under the pin), the declaration's own
validation, and a live-tree proof that the census sees a known real read.

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
from test.parallel_implementation_drift import (  # noqa: E402
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


@dataclass(frozen=True)
class LanguageCensus:
    """The environment-reading templates one language's package carries."""

    language: str
    src_dir: Path
    reads: frozenset[str]


@dataclass(frozen=True)
class Exemption:
    """One reviewed environment read a realized language carries on purpose."""

    template: str
    reason: str


# ---------------------------------------------------------------------------
# Census
# ---------------------------------------------------------------------------


def census_templates(src_dir: Path, idioms: tuple[re.Pattern[str], ...]) -> frozenset[str]:
    """Every ``.j2`` template under *src_dir* that matches any idiom, as a
    posix path relative to *src_dir*.

    File-level granularity: a template is a read when any line of it matches,
    so a docstring that mentions the idiom counts and needs an exemption too.
    That is deliberate -- a mention is cheap to exempt with a reason, and a
    matcher that tried to tell prose from code would be the eyeballing regex
    the seam discipline forbids.
    """
    reads: set[str] = set()
    for template in sorted(src_dir.rglob(f"*{_TEMPLATE_SUFFIX}")):
        text = template.read_text(encoding="utf-8-sig")
        if any(pattern.search(text) for pattern in idioms):
            reads.add(template.relative_to(src_dir).as_posix())
    return frozenset(reads)


def census_language(language: str, src_dir: Path, declaration: ZeroEnvironmentRuntimeDeclaration) -> LanguageCensus:
    return LanguageCensus(
        language=language,
        src_dir=src_dir,
        reads=census_templates(src_dir, declaration.compiled_idioms()),
    )


# ---------------------------------------------------------------------------
# Baseline
# ---------------------------------------------------------------------------


def load_baseline() -> dict[str, dict[str, object]]:
    """The per-language baseline entries, keyed by registered language name.

    Raises:
        ValueError: If the file exists but is not an object carrying a
            ``languages`` object.
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
    return languages


def parse_exemptions(language: str, entry: dict[str, object]) -> tuple[Exemption, ...]:
    """The reviewed exemption list of a realized language's baseline entry.

    Raises:
        ValueError: If the entry has no ``exemptions`` list, an item lacks a
            template or a non-empty reason, or a template is listed twice.
    """
    raw = entry.get("exemptions")
    if not isinstance(raw, list):
        raise ValueError(
            f"{BASELINE_PATH}: languages.{language} declares the zero-environment "
            f"contract realized, so its entry must carry an 'exemptions' list "
            f"(each item: template + reason). Fix: add the list, empty if the "
            f"language carries no environment read."
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


def parse_pinned_count(language: str, entry: dict[str, object]) -> int:
    """The pinned count of an unrealized language's baseline entry.

    Raises:
        ValueError: If the entry has no non-negative integer ``pinned_count``.
    """
    count = entry.get("pinned_count")
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise ValueError(
            f"{BASELINE_PATH}: languages.{language} declares the zero-environment "
            f"contract unrealized, so its entry must carry a non-negative integer "
            f"'pinned_count'. Fix: run with --update-baseline to pin the live count."
        )
    return count


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


def evaluate(
    census: LanguageCensus,
    declaration: ZeroEnvironmentRuntimeDeclaration,
    entry: dict[str, object] | None,
) -> list[str]:
    """Every way *census* disagrees with what the language declared and pinned."""
    problems: list[str] = []
    if declaration.realized:
        exemptions = parse_exemptions(census.language, entry or {"exemptions": []})
        exempted = {exemption.template for exemption in exemptions}
        for template in sorted(census.reads - exempted):
            problems.append(
                f"{census.language}: {template} reads the environment but carries "
                f"no reviewed exemption. The language declares the zero-environment "
                f"contract realized. Fix: bake the value at generation time, or add "
                f"an exemption with a written reason to {BASELINE_PATH}."
            )
        for template in sorted(exempted - census.reads):
            problems.append(
                f"{census.language}: exemption {template} names a template with no "
                f"environment read (or no such template). Fix: remove the stale "
                f"entry from {BASELINE_PATH}."
            )
        return problems
    if entry is None:
        problems.append(
            f"{census.language}: declares the zero-environment contract unrealized "
            f"but {BASELINE_PATH} pins no count for it. Fix: run with "
            f"--update-baseline to pin the live count ({len(census.reads)})."
        )
        return problems
    pinned = parse_pinned_count(census.language, entry)
    if len(census.reads) > pinned:
        problems.append(
            f"{census.language}: {len(census.reads)} template(s) read the environment, "
            f"above the pinned decrease-only count of {pinned}. A new environment read "
            f"appeared. Fix: bake the new value at generation time instead."
        )
    elif len(census.reads) < pinned:
        logger.info(
            "%s: %d environment-reading template(s), below the pinned %d -- "
            "run with --update-baseline to lower the pin.",
            census.language,
            len(census.reads),
            pinned,
        )
    return problems


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


def scan_all_registered_languages() -> tuple[dict[str, LanguageCensus], dict[str, ZeroEnvironmentRuntimeDeclaration], list[str]]:
    """Census every registered language; undeclared languages are reported,
    never skipped."""
    language_names = registered_language_names()
    _require_min_languages(language_names)
    src_dirs = discover_target_package_src_dirs(AXIS_LANGUAGES, language_names, WORKSPACE_ROOT)
    censuses: dict[str, LanguageCensus] = {}
    declarations: dict[str, ZeroEnvironmentRuntimeDeclaration] = {}
    undeclared: list[str] = []
    for language, src_dir in sorted(src_dirs.items()):
        declaration = _declaration_for(language)
        if declaration is None:
            undeclared.append(
                f"{language}: declares no zero_environment_runtime posture on its "
                f"LanguageCapabilityDeclaration. Fix: declare a "
                f"ZeroEnvironmentRuntimeDeclaration (realized or not, with the "
                f"language's environment-read idioms and, if unrealized, a reason)."
            )
            continue
        declarations[language] = declaration
        censuses[language] = census_language(language, src_dir, declaration)
    return censuses, declarations, undeclared


# ---------------------------------------------------------------------------
# Non-vacuity self-test
# ---------------------------------------------------------------------------


def _assert(condition: bool, label: str) -> bool:
    print(f"[{'OK' if condition else 'FAIL'}] {label}")
    return condition


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
    declaration = ZeroEnvironmentRuntimeDeclaration(
        realized=True, environment_read_idioms=(_SELF_TEST_IDIOM,)
    )
    census = census_language(_SELF_TEST_LANGUAGE, src_dir, declaration)
    ok = _assert(
        census.reads == frozenset({"templates/reads.py.j2"}),
        "synthetic tree: exactly the planted template is a read; the clean template and "
        "the non-template file are not",
    )
    return ok, census


def _self_test_comparator(census: LanguageCensus) -> bool:
    realized = ZeroEnvironmentRuntimeDeclaration(
        realized=True, environment_read_idioms=(_SELF_TEST_IDIOM,)
    )
    unrealized = ZeroEnvironmentRuntimeDeclaration(
        realized=False, environment_read_idioms=(_SELF_TEST_IDIOM,), reason="self-test"
    )
    ok = True
    ok &= _assert(
        evaluate(census, realized, {"exemptions": [{"template": "templates/reads.py.j2", "reason": "planted"}]}) == [],
        "realized + exact exemption list: no problem",
    )
    ok &= _assert(
        len(evaluate(census, realized, {"exemptions": []})) == 1,
        "realized + missing exemption: exactly one problem",
    )
    stale = {"exemptions": [
        {"template": "templates/reads.py.j2", "reason": "planted"},
        {"template": "templates/gone.py.j2", "reason": "stale"},
    ]}
    ok &= _assert(
        len(evaluate(census, realized, stale)) == 1,
        "realized + stale exemption: exactly one problem",
    )
    ok &= _assert(
        evaluate(census, unrealized, {"pinned_count": 1}) == []
        and evaluate(census, unrealized, {"pinned_count": 5}) == [],
        "unrealized + count at or below the pin: no problem",
    )
    ok &= _assert(
        len(evaluate(census, unrealized, {"pinned_count": 0})) == 1,
        "unrealized + count above the pin: exactly one problem",
    )
    ok &= _assert(
        len(evaluate(census, unrealized, None)) == 1,
        "unrealized + no pinned entry: exactly one problem",
    )
    try:
        parse_exemptions(_SELF_TEST_LANGUAGE, {"exemptions": [{"template": "x.j2", "reason": " "}]})
        reasonless_rejected = False
    except ValueError:
        reasonless_rejected = True
    ok &= _assert(reasonless_rejected, "an exemption without a written reason is rejected")
    return ok


def _self_test_declaration_validation() -> bool:
    ok = True
    try:
        ZeroEnvironmentRuntimeDeclaration(realized=False, environment_read_idioms=(_SELF_TEST_IDIOM,))
        rejected = False
    except ValueError:
        rejected = True
    ok &= _assert(rejected, "an unrealized declaration without a reason is rejected at construction")
    try:
        ZeroEnvironmentRuntimeDeclaration(realized=True, environment_read_idioms=())
        rejected = False
    except ValueError:
        rejected = True
    ok &= _assert(rejected, "a declaration with no idiom is rejected at construction")
    return ok


def _self_test_live_read() -> bool:
    language, relative_template = _KNOWN_LIVE_READ
    language_names = registered_language_names()
    src_dirs = discover_target_package_src_dirs(AXIS_LANGUAGES, language_names, WORKSPACE_ROOT)
    src_dir = src_dirs.get(language)
    declaration = _declaration_for(language) if src_dir is not None else None
    if src_dir is None or declaration is None:
        return _assert(False, f"live tree registers {language} with a declared posture")
    census = census_language(language, src_dir, declaration)
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
        ok &= _self_test_declaration_validation()
        ok &= _self_test_live_read()
        try:
            _require_min_languages(frozenset({_SELF_TEST_LANGUAGE}))
            refused = False
        except SystemExit as exc:
            refused = exc.code == EXIT_USAGE
        ok &= _assert(refused, "single-language guard refuses a one-language set, never a silent pass")
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    return ok


# ---------------------------------------------------------------------------
# Baseline writer
# ---------------------------------------------------------------------------


def write_baseline(
    censuses: dict[str, LanguageCensus],
    declarations: dict[str, ZeroEnvironmentRuntimeDeclaration],
    existing: dict[str, dict[str, object]],
) -> None:
    """Re-pin every unrealized language's count to its live census. Realized
    languages' exemption lists are hand-authored and are carried over
    untouched -- the writer never invents a reason."""
    languages: dict[str, object] = {}
    for language in sorted(set(existing) | set(censuses)):
        declaration = declarations.get(language)
        if declaration is None or declaration.realized:
            if language in existing:
                languages[language] = existing[language]
            continue
        languages[language] = {"pinned_count": len(censuses[language].reads)}
    payload = {
        "_comment": [
            "Zero-environment runtime census, per registered datrix.languages package.",
            "A language whose LanguageCapabilityDeclaration.zero_environment_runtime",
            "is realized=True lists every template that reads the environment as a",
            "reviewed exemption with a written reason (hand-authored; the gate fails",
            "on an unlisted read and on a stale entry). A language declaring",
            "realized=False carries a decrease-only pinned_count of environment-",
            "reading templates; a live count above it fails.",
            "zero-environment-runtime-gate.ps1 -UpdateBaseline is the only writer of",
            "pinned_count values; do not hand-guess the numbers.",
        ],
        "languages": languages,
    }
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Zero-environment runtime census: every registered language is held to "
            "the zero_environment_runtime posture it declares -- reviewed exemptions "
            "when realized, a decrease-only pinned count when not."
        ),
    )
    parser.add_argument("--debug", action="store_true", help="Enable DEBUG logging")
    parser.add_argument("--self-test", action="store_true", help="Run only the non-vacuity self-test")
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Re-pin every unrealized language's count to its live census",
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
        censuses, declarations, undeclared = scan_all_registered_languages()
        baseline = load_baseline()
        if args.update_baseline:
            write_baseline(censuses, declarations, baseline)
            logger.info("baseline written: %s", BASELINE_PATH)
            baseline = load_baseline()
        problems = list(undeclared)
        for language in sorted(censuses):
            census = censuses[language]
            for template in sorted(census.reads):
                logger.debug("READ language=%s template=%s", language, template)
            logger.info(
                "language=%s realized=%s environment_reading_templates=%d",
                language,
                declarations[language].realized,
                len(census.reads),
            )
            problems.extend(evaluate(census, declarations[language], baseline.get(language)))
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
