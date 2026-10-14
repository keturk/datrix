"""Response-body transform census gate.

Every registered language serializes response-body fields under one declared rule, camelCase
wire keys; the parity rows of ``cases/response-bodies.parity.yaml`` prove it by reading each
language's emitted response classes. What those readings cannot see is a transform applied
AFTER serialization: a framework-level response transform (a global interceptor, a
response-model setting that changes how field names are serialized) rewrites every outgoing
body, so it is invisible to a reading of the response classes.

Each registered language declares the regular expressions that spell such a transform in its
own framework (``LanguageCapabilityDeclaration.response_body_transform_idioms``). This gate
generates the shared CQRS example once per registered language and greps the generated tree for
them; every hit must be a typed ``transform_exemptions`` entry of
``scripts/config/response-body-transform-exemptions.json`` (language, path suffix, matched text,
reason). An unreviewed hit, an entry that matches nothing (stale) and a language with no
declaration each fail by name, and the review file is refused if it carries any key other than
``_comment`` and ``transform_exemptions`` -- a response-body field that diverges from the rule
has no review shape at all.

This is a census over generated text, not a conformance-probe reading: it imports no probe.
Target set is NEVER hardcoded: languages are enumerated from the installed
``datrix.languages`` entry points at run time, and the self-test proves this module names none.

Repo-level validation script (per the datrix showcase boundary -- no pytest suite lives in
datrix).
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from datrix_common.errors.plugin import PluginNotFoundError, PluginValidationError
from datrix_common.plugin.capability_resolution import declaration_for_language

from datrix_scripts.generated_example import generate_example
from datrix_scripts.paths import CONFIG_DIR, SHOWCASE_DIR, WORKSPACE_DIR
from datrix_scripts.registered_targets import registered_language_names, self_test_gate_names_no_target

logger = logging.getLogger(__name__)

EXEMPTIONS_PATH: Final[Path] = CONFIG_DIR / "response-body-transform-exemptions.json"
EXAMPLE_SOURCE: Final[Path] = SHOWCASE_DIR / "examples" / "02-features" / "03-infrastructure-blocks" / "cqrs" / "system.dtrx"
#: Generation scratch space, outside every package repository, cleaned per run.
_GATE_OUTPUT_ROOT: Final[Path] = WORKSPACE_DIR / ".tmp" / "response-body-transform-census"

#: A census over fewer languages compares nothing.
_MIN_LANGUAGES: Final[int] = 2
EXIT_OK: Final[int] = 0
EXIT_VIOLATION: Final[int] = 1
EXIT_CANNOT_RUN: Final[int] = 2

#: Directories a census never descends into: dependency and VCS trees, not generated source.
_SKIP_DIRS: Final[frozenset[str]] = frozenset({"node_modules", ".git", "__pycache__", ".venv"})
#: A generated file larger than this is data (a lockfile, a bundle), not source an idiom could appear in.
_MAX_BYTES: Final[int] = 2_000_000
#: The only top-level keys the review file may carry.
_REVIEW_FILE_KEYS: Final[frozenset[str]] = frozenset({"_comment", "transform_exemptions"})
_ENTRY_KEYS: Final[tuple[str, ...]] = ("language", "path_suffix", "matched_text", "reason")

_SELF_TEST_LANGUAGE: Final[str] = "self_test_lang"
_SELF_TEST_INTERCEPTOR_LINE: Final[str] = "app.useGlobalInterceptors(new KeyRewriteInterceptor());"
_SELF_TEST_INTERCEPTOR_IDIOM: Final[str] = r"\buseGlobalInterceptors\("
_SELF_TEST_INTERCEPTOR_MATCH: Final[str] = "useGlobalInterceptors("


@dataclass(frozen=True)
class TransformHit:
    """One place a generated tree spells a response-body transform idiom.

    Attributes:
        language: The language whose tree holds the hit.
        relative_path: The file, relative to the generated root, in POSIX form.
        line: 1-based line number of the match.
        matched_text: The exact text the idiom matched.
    """

    language: str
    relative_path: str
    line: int
    matched_text: str


@dataclass(frozen=True)
class TransformExemption:
    """A reviewed generated-tree hit that does not transform a response body.

    Attributes:
        language: The language whose tree holds the hit.
        path_suffix: Trailing path segments of the file (POSIX), e.g. ``src/app.module.ts``.
        matched_text: The exact text the idiom matched.
        reason: Why this hit leaves every response body untouched.
    """

    language: str
    path_suffix: str
    matched_text: str
    reason: str

    def covers(self, hit: TransformHit) -> bool:
        """True when *hit* is the hit this entry reviewed."""
        return (
            hit.language == self.language
            and hit.matched_text == self.matched_text
            and hit.relative_path.endswith(self.path_suffix)
        )


def parse_transform_exemptions(data: object, source: Path) -> tuple[TransformExemption, ...]:
    """Validate the parsed review file *data* read from *source*.

    Raises:
        ValueError: *data* is not an object, carries a key outside ``_comment``/``transform_exemptions``,
            its ``transform_exemptions`` array is missing or malformed, or an entry lacks a non-empty field.
    """
    if not isinstance(data, dict):
        raise ValueError(f"Malformed review file {source}: expected an object with 'transform_exemptions'.")
    unknown = sorted(set(data) - _REVIEW_FILE_KEYS)
    if unknown:
        raise ValueError(
            f"Review file {source} carries unrecognized key(s) {unknown}; valid keys are {sorted(_REVIEW_FILE_KEYS)}. "
            f"A response-body field that diverges from the camelCase rule is a defect in that language's template "
            f"and has no review shape. Fix: delete the key and fix the template."
        )
    entries = data["transform_exemptions"] if "transform_exemptions" in data else None
    if not isinstance(entries, list):
        raise ValueError(f"Malformed review file {source}: expected 'transform_exemptions' (array of {list(_ENTRY_KEYS)}).")
    exemptions: list[TransformExemption] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError(f"Malformed review file {source}: entry {entry!r} is not an object of {list(_ENTRY_KEYS)}.")
        for key in _ENTRY_KEYS:
            if key not in entry or not isinstance(entry[key], str) or not entry[key].strip():
                raise ValueError(f"Transform exemption entry {entry!r} is missing a non-empty {key!r}.")
        exemptions.append(TransformExemption(*(entry[key] for key in _ENTRY_KEYS)))
    return tuple(exemptions)


def load_transform_exemptions(path: Path = EXEMPTIONS_PATH) -> tuple[TransformExemption, ...]:
    """Load and validate the review file.

    Raises:
        ValueError: The file is missing or malformed.
    """
    if not path.exists():
        raise ValueError(f"Missing review file {path}. It pins the reviewed response-body transform hits; restore it.")
    return parse_transform_exemptions(json.loads(path.read_text(encoding="utf-8")), path)


def response_transform_idioms(language: str) -> tuple[re.Pattern[str], ...]:
    """The compiled response-transform idioms *language* declares.

    Raises:
        ValueError: *language* has no capability declaration to read them from.
    """
    try:
        declaration = declaration_for_language(language)
    except (PluginNotFoundError, PluginValidationError) as exc:
        raise ValueError(
            f"language {language!r} declares no LanguageCapabilityDeclaration, so its response_body_transform_idioms "
            f"cannot be read ({exc}). Fix: add the declaration to the language package."
        ) from exc
    return declaration.compiled_response_body_transform_idioms()


def census_response_transforms(
    language: str, generated_root: Path, idioms: Sequence[re.Pattern[str]]
) -> list[TransformHit]:
    """Every line of the generated tree under *generated_root* that spells an idiom, by path then line."""
    hits: list[TransformHit] = []
    for path in sorted(generated_root.rglob("*")):
        if not path.is_file() or any(part in _SKIP_DIRS for part in path.parts) or path.stat().st_size > _MAX_BYTES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        relative = path.relative_to(generated_root).as_posix()
        for number, line in enumerate(text.splitlines(), start=1):
            hits.extend(
                TransformHit(language, relative, number, match.group(0)) for idiom in idioms for match in idiom.finditer(line)
            )
    return hits


def unexempted_transform_hits(hits: Sequence[TransformHit], exemptions: Sequence[TransformExemption]) -> list[TransformHit]:
    """The hits no exemption reviewed."""
    return [hit for hit in hits if not any(entry.covers(hit) for entry in exemptions)]


def stale_transform_exemptions(
    language: str, hits: Sequence[TransformHit], exemptions: Sequence[TransformExemption]
) -> list[TransformExemption]:
    """The *language* exemptions that cover no hit -- they no longer review anything."""
    return [entry for entry in exemptions if entry.language == language and not any(entry.covers(hit) for hit in hits)]


def language_problems(
    language: str, generated_root: Path, exemptions: Sequence[TransformExemption]
) -> list[str]:
    """Every unreviewed hit and stale entry of *language*'s generated tree; the refusal when it declares no idioms."""
    try:
        idioms = response_transform_idioms(language)
    except ValueError as exc:
        return [str(exc)]
    hits = census_response_transforms(language, generated_root, idioms)
    problems = [
        f"language {language!r} spells a response-body transform at {hit.relative_path}:{hit.line} ({hit.matched_text!r}). "
        f"A transform applied to every outgoing body changes the wire names the response classes declare. Fix: delete "
        f"the transform, or add a reviewed entry to 'transform_exemptions' in {EXEMPTIONS_PATH.name} if it leaves the "
        f"body untouched."
        for hit in unexempted_transform_hits(hits, exemptions)
    ]
    problems.extend(
        f"the transform exemption for language {entry.language!r} ({entry.path_suffix}, {entry.matched_text!r}) matches "
        f"nothing in the generated tree. Fix: delete it from {EXEMPTIONS_PATH.name}."
        for entry in stale_transform_exemptions(language, hits, exemptions)
    )
    return problems


def check_response_body_transforms(languages: Sequence[str] | None = None) -> int:
    """Run the census over every registered language.

    Args:
        languages: ``None`` -- the production value -- resolves the installed ``datrix.languages`` entry
            points; an explicit list exists so the self-test drives the insufficient-target refusal,
            which is the first statement and returns before any generation.

    Returns:
        0 every hit reviewed and no entry stale, 1 a violation, 2 fewer than two languages registered.
    """
    names = sorted(registered_language_names() if languages is None else languages)
    if len(names) < _MIN_LANGUAGES:
        logger.error("Response-body transform census CANNOT RUN: %d language(s) registered (%s).", len(names), names)
        return EXIT_CANNOT_RUN
    exemptions = load_transform_exemptions()
    shutil.rmtree(_GATE_OUTPUT_ROOT, ignore_errors=True)
    problems: list[str] = []
    for language in names:
        generated = generate_example(language, EXAMPLE_SOURCE, _GATE_OUTPUT_ROOT / language)
        problems.extend(language_problems(language, generated, exemptions))
    unknown = sorted({entry.language for entry in exemptions} - set(names))
    problems.extend(f"the review file names {language!r}, which is not a registered language" for language in unknown)
    for problem in problems:
        logger.error("RESPONSE-BODY TRANSFORM VIOLATION: %s", problem)
    if problems:
        return EXIT_VIOLATION
    logger.info("No unreviewed response-body transform in %d languages (%s).", len(names), names)
    return EXIT_OK


# ---------------------------------------------------------------------------
# Non-vacuity self-test
# ---------------------------------------------------------------------------


def _self_test_census() -> list[str]:
    """The census reports a planted hit at its coordinates, honours an exemption, flags a stale one,
    ignores a clean file, and refuses a language with no declaration."""
    problems: list[str] = []
    root = _GATE_OUTPUT_ROOT / "self-test"
    shutil.rmtree(root, ignore_errors=True)
    (root / "src").mkdir(parents=True)
    try:
        (root / "src" / "main.ts").write_text(f"bootstrap();\n{_SELF_TEST_INTERCEPTOR_LINE}\n", encoding="utf-8")
        (root / "src" / "clean.ts").write_text("app.useGlobalPipes(new ValidationPipe());\n", encoding="utf-8")
        hits = census_response_transforms(_SELF_TEST_LANGUAGE, root, (re.compile(_SELF_TEST_INTERCEPTOR_IDIOM),))
        planted = TransformHit(_SELF_TEST_LANGUAGE, "src/main.ts", 2, _SELF_TEST_INTERCEPTOR_MATCH)
        if hits != [planted]:
            problems.append(f"the census did not report exactly the planted hit at src/main.ts:2 (got {hits!r})")
        exemption = TransformExemption(_SELF_TEST_LANGUAGE, "src/main.ts", _SELF_TEST_INTERCEPTOR_MATCH, "self-test")
        if unexempted_transform_hits([planted], []) != [planted] or unexempted_transform_hits([planted], [exemption]):
            problems.append("an exemption did not decide exactly whether the planted hit is reported")
        if stale_transform_exemptions(_SELF_TEST_LANGUAGE, [], [exemption]) != [exemption]:
            problems.append("an exemption that matches no hit was not reported as stale")
        if stale_transform_exemptions(_SELF_TEST_LANGUAGE, [planted], [exemption]):
            problems.append("an exemption that covers a hit was reported as stale")
    finally:
        shutil.rmtree(root, ignore_errors=True)
    refusal = language_problems(_SELF_TEST_LANGUAGE, root, [])
    if len(refusal) != 1 or _SELF_TEST_LANGUAGE not in refusal[0]:
        problems.append(f"a language with no capability declaration was not refused by name (got {refusal!r})")
    return problems


def _self_test_review_file() -> list[str]:
    """The review file accepts only reviewed transform hits."""
    source = Path("self-test-review.json")
    reviewed = {"language": _SELF_TEST_LANGUAGE, "path_suffix": "src/main.ts", "matched_text": "x(", "reason": "self-test"}
    problems: list[str] = []
    if [entry.path_suffix for entry in parse_transform_exemptions({"transform_exemptions": [reviewed]}, source)] != [
        "src/main.ts"
    ]:
        problems.append("a well-formed review file did not parse to its one entry")
    for malformed, fragment in (
        ({"transform_exemptions": [], "exemptions": [reviewed]}, "'exemptions'"),
        ({"transform_exemptions": ["src/main.ts"]}, "is not an object"),
        ({"transform_exemptions": [{**reviewed, "reason": " "}]}, "'reason'"),
    ):
        try:
            parse_transform_exemptions(malformed, source)
        except ValueError as exc:
            if fragment not in str(exc):
                problems.append(f"the refusal of {malformed!r} did not say {fragment}")
            continue
        problems.append(f"a malformed review file was accepted: {malformed!r}")
    return problems


def run_self_test() -> list[str]:
    """Prove this gate names no target, finds a planted transform, and refuses a vacuous run."""
    problems = list(self_test_gate_names_no_target(__file__))
    if problems:
        return problems
    problems.extend(_self_test_census())
    problems.extend(_self_test_review_file())
    for insufficient in ([], sorted(registered_language_names())[:1]):
        if check_response_body_transforms(insufficient) != EXIT_CANNOT_RUN:
            problems.append(f"a census over {insufficient!r} was not refused")
    return problems


def main() -> int:
    """Entry point: the self-test always, then the census unless ``--self-test``."""
    parser = argparse.ArgumentParser(description="Census every registered language's generated tree for response-body transforms.")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--self-test", action="store_true", help="Run only the self-test and skip generation")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO, format="%(levelname)s: %(message)s")
    problems = run_self_test()
    if problems:
        logger.error("Self-test FAILED:")
        for problem in problems:
            logger.error("  %s", problem)
        return EXIT_CANNOT_RUN
    logger.info("Self-test passed.")
    if args.self_test:
        return EXIT_OK
    try:
        return check_response_body_transforms()
    except ValueError as exc:
        logger.error("Response-body transform census CANNOT RUN: %s", exc)
        return EXIT_CANNOT_RUN


if __name__ == "__main__":
    sys.exit(main())
