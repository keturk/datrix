"""Field-error-path parity gate -- every registered language spells
`request-validation` problem-body `errors[].field` paths with ONE dot-separated,
`body`-prefix-free, `[n]`-array-indexed rule
(`datrix_common.generation.problem_types.FIELD_ERROR_PATH_RULE`) or declares the
hole with a reason on `LanguageCapabilityDeclaration.unrealized_field_error_path`.

Unlike the problem-type and framework-header registries, this is not a table of
named families: there is exactly ONE rule, so `unrealized_field_error_path` is a
single optional reason string, not a per-family mapping, and this gate's
`evaluate()` mirrors that shape.

Realization is a runtime BEHAVIOUR, not a literal wire string every backend
spells identically (unlike a problem-type URN or a framework header name), so
there is no single cross-language regex to census for. Each realizing
language's construction technique is language-specific evidence, gathered by
reading its real source:

* **python** realizes the rule with a real, callable, unit-tested mapping
  function (`format_field_error_path`, inlined verbatim into the generated
  exception handler) -- censused by finding its definition and EXECUTING it
  against the shared canonical fixture, the only way to prove what a generic
  mapping *function* (not a literal string) actually produces.
* **typescript** realizes the rule with a hand-written recursive builder over
  class-validator's own `ValidationError` tree -- censused by confirming its
  two required construction lines (bracket-indexed, dot-joined) are present.
* **java** realizes the rule NATIVELY: Spring's `FieldError.getField()` and
  Jakarta Bean Validation's `ConstraintViolation.getPropertyPath()` already
  spell nested request-body errors in exactly this form -- censused by finding
  either accessor called on the framework's own validation-error object.
* A language with no known construction technique censuses to zero sites,
  which `evaluate()` correctly reports as an undeclared gap unless the
  language declares the hole.

Language set from the installed `datrix.languages` entry points at runtime;
declarations read from the packages -- never a table in this script. Runs a
built-in non-vacuity self-test on every invocation. Repo-level validation
script (per the datrix showcase boundary -- no pytest suite lives in datrix).
"""

from __future__ import annotations

import argparse
import importlib.util
import logging
import re
import shutil
import sys
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Final

_LIBRARY_DIR = Path(__file__).resolve().parent.parent
if _LIBRARY_DIR.exists() and str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from datrix_common.generation.problem_types import FIELD_ERROR_PATH_RULE  # noqa: E402
from datrix_common.plugin.capability_resolution import declaration_for_language  # noqa: E402

from shared.registered_targets import registered_language_names  # noqa: E402
from shared.registered_targets import (  # noqa: E402
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

#: The one worked example every census and self-test measures against: a
#: pydantic-style `loc` tuple naming a nested body field, and the dot path
#: `FIELD_ERROR_PATH_RULE` derives from it. Imported behaviour, not a re-typed
#: literal, so the fixture can never drift from the rule it tests.
_CANONICAL_LOC: Final[tuple[str | int, ...]] = ("body", "shippingAddress", "postalCode")
_CANONICAL_PATH: Final[str] = FIELD_ERROR_PATH_RULE.format(_CANONICAL_LOC)


@dataclass(frozen=True, slots=True)
class RealizationSite:
    """One place a language's source spells a field-error-path construction --
    a candidate realization or divergence, found by the census."""

    language: str
    relative_path: str
    line: int
    spelled_path: str
    """The literal example path this site produces for the shared canonical
    fixture loc (`FIELD_ERROR_PATH_RULE`'s own worked example) -- read from the
    evidence gathered against the real per-language sites, never invented."""


@dataclass(frozen=True, slots=True)
class LanguageVerdict:
    language: str
    realized: bool
    declared_reason: str | None


# ---------------------------------------------------------------------------
# Source discovery (shared with problem_type_parity.py / framework_header_parity.py)
# ---------------------------------------------------------------------------


def _iter_source_files(src_dir: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(src_dir.rglob("*")):
        if not path.is_file() or path.suffix not in _SOURCE_SUFFIXES:
            continue
        if any(part in _SKIP_DIR_NAMES for part in path.relative_to(src_dir).parts):
            continue
        files.append(path)
    return files


# ---------------------------------------------------------------------------
# Per-language census
# ---------------------------------------------------------------------------

_PYTHON_FORMATTER_DEF_RE: Final[re.Pattern[str]] = re.compile(r"def\s+format_field_error_path\(")
_TS_BUILDER_DEF_RE: Final[re.Pattern[str]] = re.compile(r"function\s+buildValidationFieldErrors\(")
_TS_ARRAY_BRACKET_RE: Final[re.Pattern[str]] = re.compile(r"\$\{parentPath\}\[\$\{error\.property\}\]")
_TS_DOT_JOIN_RE: Final[re.Pattern[str]] = re.compile(r"\$\{parentPath\}\.\$\{error\.property\}")
_JAVA_FIELD_ERROR_RE: Final[re.Pattern[str]] = re.compile(
    r"\bfe\.getField\(\)|\.getPropertyPath\(\)\.toString\(\)"
)


def _load_module_from_path(path: Path) -> ModuleType:
    """Dynamically load *path* as a standalone module.

    The only way to prove what a generic mapping FUNCTION (not a literal
    string) actually produces is to execute it -- so python's census loads
    the real, self-contained runtime file it finds and calls its function
    against the canonical fixture, rather than guessing its behaviour from
    text.

    Raises:
        ImportError: `path` cannot be turned into a loadable module spec.
    """
    spec = importlib.util.spec_from_file_location("_field_error_path_census", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load a module spec for {path}.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _census_python(src_dir: Path, files: list[Path]) -> tuple[RealizationSite, ...]:
    """Python realizes the rule with a real, callable mapping function --
    found by its definition, then EXECUTED against the canonical fixture."""
    sites: list[RealizationSite] = []
    for path in files:
        if path.suffix != ".py":
            continue
        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not _PYTHON_FORMATTER_DEF_RE.search(line):
                continue
            module = _load_module_from_path(path)
            formatter = getattr(module, "format_field_error_path", None)
            if formatter is None:
                continue
            produced = formatter(_CANONICAL_LOC)
            sites.append(
                RealizationSite("python", path.relative_to(src_dir).as_posix(), line_number, produced)
            )
    return tuple(sites)


def _census_typescript(src_dir: Path, files: list[Path]) -> tuple[RealizationSite, ...]:
    """TypeScript realizes the rule with a hand-written recursive builder over
    class-validator's own `ValidationError` tree (`main.ts.j2`'s
    `buildValidationFieldErrors`). class-validator's tree starts at the DTO's
    own properties (no `body` wrapper), so the rule is realized exactly when
    the builder joins named segments with `.` and numeric-string segments
    with `[n]`; a builder present but missing either construction line is a
    divergence, not silence."""
    sites: list[RealizationSite] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not _TS_BUILDER_DEF_RE.search(line):
                continue
            relative = path.relative_to(src_dir).as_posix()
            if _TS_ARRAY_BRACKET_RE.search(text) and _TS_DOT_JOIN_RE.search(text):
                sites.append(RealizationSite("typescript", relative, line_number, _CANONICAL_PATH))
            else:
                sites.append(
                    RealizationSite(
                        "typescript",
                        relative,
                        line_number,
                        f"{_CANONICAL_PATH} (missing the canonical `[n]`-index / `.`-join "
                        f"construction)",
                    )
                )
    return tuple(sites)


def _census_java(src_dir: Path, files: list[Path]) -> tuple[RealizationSite, ...]:
    """Java realizes the rule NATIVELY: Spring's `FieldError.getField()` and
    Jakarta Bean Validation's `ConstraintViolation.getPropertyPath()` already
    spell nested request-body errors in exactly this dot/`[n]` form -- java IS
    the reference behaviour `FIELD_ERROR_PATH_RULE` models -- so a call site
    realizes the rule with no further construction to verify."""
    sites: list[RealizationSite] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if _JAVA_FIELD_ERROR_RE.search(line):
                sites.append(
                    RealizationSite("java", path.relative_to(src_dir).as_posix(), line_number, _CANONICAL_PATH)
                )
    return tuple(sites)


#: `{language: detector}` -- the plumbing that dispatches a discovered
#: language's sources to its own construction-technique census. A language
#: absent here (a future target, or one with no known technique yet) censuses
#: to zero sites, which `evaluate()` correctly reports as an undeclared gap
#: unless that language declares `unrealized_field_error_path`. This is NOT
#: the retired per-family mapping shape: it holds no reason, only a census
#: FUNCTION, because there is no family axis on a one-rule gate.
_CENSUS_DISPATCH: Final[Mapping[str, Callable[[Path, list[Path]], tuple[RealizationSite, ...]]]] = {
    "python": _census_python,
    "typescript": _census_typescript,
    "java": _census_java,
}


def census_source(language: str, src_dir: Path) -> tuple[RealizationSite, ...]:
    """Every field-error-path construction site under `src_dir` for `language`."""
    detector = _CENSUS_DISPATCH.get(language)
    if detector is None:
        return ()
    return detector(src_dir, _iter_source_files(src_dir))


# ---------------------------------------------------------------------------
# Comparator
# ---------------------------------------------------------------------------


def evaluate(
    canonical_path: str,
    censuses: Mapping[str, tuple[RealizationSite, ...]],
    declared_reasons: Mapping[str, str | None],
) -> tuple[list[str], dict[str, LanguageVerdict]]:
    """Every violation across every registered language, plus the per-language
    verdicts the report renders.

    A language realizes the rule when its census sites spell *canonical_path*
    exactly for the shared fixture; declares the hole when
    `unrealized_field_error_path` carries a non-empty reason; realizing AND
    declaring is a stale declaration (fails); neither is an unrealized,
    undeclared gap (fails); a divergent spelling that is neither the
    canonical path nor an empty census is a violation naming the found
    spelling and the expected one.
    """
    problems: list[str] = []
    verdicts: dict[str, LanguageVerdict] = {}
    for language in sorted(censuses):
        sites = censuses[language]
        reason = declared_reasons.get(language)
        declared = reason is not None
        realized = any(site.spelled_path == canonical_path for site in sites)
        for site in sites:
            if site.spelled_path == canonical_path:
                continue
            problems.append(
                f"{language}: {site.relative_path}:{site.line}: spells field-error path "
                f"{site.spelled_path!r}, which diverges from the canonical form "
                f"{canonical_path!r} FIELD_ERROR_PATH_RULE derives. Fix: match the rule's "
                f"dot-separated, body-prefix-free, `[n]`-indexed form."
            )
        if declared and not (reason or "").strip():
            problems.append(
                f"{language}: unrealized_field_error_path carries an empty/whitespace reason. "
                f"Fix: state why the language does not realize the rule."
            )
        if realized and declared:
            problems.append(
                f"{language}: declares unrealized_field_error_path, but its sources realize "
                f"the rule. Fix: remove the stale declaration."
            )
        elif not sites and not declared:
            problems.append(
                f"{language}: neither spells the canonical field-error path "
                f"({canonical_path!r}) nor declares unrealized_field_error_path. Fix: realize "
                f"FIELD_ERROR_PATH_RULE's form, or declare the hole with a reason."
            )
        verdicts[language] = LanguageVerdict(language, realized, reason)
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


def scan_all_registered_languages() -> tuple[dict[str, tuple[RealizationSite, ...]], dict[str, str | None]]:
    """Census every registered `datrix.languages` package's `.py`/`.j2` sources
    for field-error-path construction sites, and read each language's
    `unrealized_field_error_path` declaration."""
    language_names = registered_language_names()
    _require_min_languages(language_names)
    src_dirs = discover_target_package_src_dirs(AXIS_LANGUAGES, language_names, WORKSPACE_ROOT)
    censuses: dict[str, tuple[RealizationSite, ...]] = {}
    reasons: dict[str, str | None] = {}
    for language, src_dir in sorted(src_dirs.items()):
        censuses[language] = census_source(language, src_dir)
        reasons[language] = declaration_for_language(language).unrealized_field_error_path
        logger.debug(
            "census language=%s sites=%d declared=%s",
            language, len(censuses[language]), reasons[language] is not None,
        )
    return censuses, reasons


def render_report(canonical_path: str, verdicts: Mapping[str, LanguageVerdict]) -> str:
    lines = [f"  canonical field-error path: {canonical_path!r}"]
    width = max(len("language"), *(len(language) for language in verdicts)) if verdicts else len("language")
    for language in sorted(verdicts):
        verdict = verdicts[language]
        if verdict.realized:
            status = "realized"
        elif verdict.declared_reason is not None:
            status = "declared"
        else:
            status = "MISSING"
        lines.append(f"  {language.ljust(width)}  {status}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Non-vacuity self-test
# ---------------------------------------------------------------------------


def _assert(condition: bool, label: str) -> bool:
    print(f"  {'PASS' if condition else 'FAIL'}: {label}")
    return condition


def _planted(language: str, spelled_path: str) -> tuple[RealizationSite, ...]:
    return (RealizationSite(language, "planted.j2", 1, spelled_path),)


def _self_test_comparator() -> bool:
    ok = True
    canonical = _CANONICAL_PATH

    clean = {"alpha": _planted("alpha", canonical), "beta": _planted("beta", canonical)}
    problems, verdicts = evaluate(canonical, clean, {})
    ok &= _assert(problems == [], "two languages spelling the canonical path report no problem")
    ok &= _assert(verdicts["alpha"].realized, "the verdict records realization")

    divergent_path = "body." + canonical
    divergent = {"alpha": _planted("alpha", divergent_path), "beta": clean["beta"]}
    problems, _ = evaluate(canonical, divergent, {})
    ok &= _assert(
        len(problems) == 1 and divergent_path in problems[0] and canonical in problems[0],
        "a divergent spelling is one violation naming the found and expected paths",
    )

    reasonless = {"alpha": (), "beta": clean["beta"]}
    problems, _ = evaluate(canonical, reasonless, {"alpha": "  "})
    ok &= _assert(len(problems) == 1 and "empty" in problems[0], "an empty declared reason is one violation")

    stale = {"alpha": clean["alpha"], "beta": clean["beta"]}
    problems, _ = evaluate(canonical, stale, {"alpha": "planted reason"})
    ok &= _assert(
        len(problems) == 1 and "stale declaration" in problems[0],
        "realizing and declaring at once is one problem",
    )

    neither = {"alpha": (), "beta": clean["beta"]}
    problems, _ = evaluate(canonical, neither, {})
    ok &= _assert(
        len(problems) == 1 and "neither spells" in problems[0],
        "an undeclared unrealized gap is one problem",
    )

    genuine_hole = {"alpha": (), "beta": clean["beta"]}
    problems, verdicts = evaluate(canonical, genuine_hole, {"alpha": "a genuine reason"})
    ok &= _assert(problems == [], "a declared hole with a real reason passes")
    ok &= _assert(verdicts["alpha"].declared_reason == "a genuine reason", "the verdict records the declared reason")
    return ok


def _self_test_census(tmp_root: Path) -> bool:
    ok = True

    py_good = tmp_root / "python-good"
    py_good.mkdir(parents=True)
    (py_good / "field_error_path.py").write_text(
        "def format_field_error_path(loc):\n"
        "    segments = list(loc)\n"
        "    if segments and segments[0] == 'body':\n"
        "        segments = segments[1:]\n"
        "    parts = []\n"
        "    for segment in segments:\n"
        "        if isinstance(segment, int):\n"
        "            parts.append(f'[{segment}]')\n"
        "        elif parts:\n"
        "            parts.append(f'.{segment}')\n"
        "        else:\n"
        "            parts.append(str(segment))\n"
        "    return ''.join(parts)\n",
        encoding="utf-8",
    )
    sites = census_source("python", py_good)
    ok &= _assert(
        len(sites) == 1 and sites[0].spelled_path == _CANONICAL_PATH,
        f"a correct python formatter's real execution produces the canonical path (got {sites})",
    )

    py_bad = tmp_root / "python-bad"
    py_bad.mkdir(parents=True)
    (py_bad / "field_error_path.py").write_text(
        "def format_field_error_path(loc):\n"
        "    return '.'.join(str(s) for s in loc)\n",
        encoding="utf-8",
    )
    sites = census_source("python", py_bad)
    ok &= _assert(
        len(sites) == 1 and sites[0].spelled_path != _CANONICAL_PATH,
        f"a divergent python formatter's real execution surfaces its actual wrong output (got {sites})",
    )

    ts_good = tmp_root / "typescript-good"
    ts_good.mkdir(parents=True)
    (ts_good / "main.ts.j2").write_text(
        "function buildValidationFieldErrors(errors, parentPath = '') {\n"
        "  if (isArrayIndex) { path = `${parentPath}[${error.property}]`; }\n"
        "  else if (parentPath) { path = `${parentPath}.${error.property}`; }\n"
        "}\n",
        encoding="utf-8",
    )
    sites = census_source("typescript", ts_good)
    ok &= _assert(
        len(sites) == 1 and sites[0].spelled_path == _CANONICAL_PATH,
        f"a correct typescript builder censuses as canonical (got {sites})",
    )

    ts_bad = tmp_root / "typescript-bad"
    ts_bad.mkdir(parents=True)
    (ts_bad / "main.ts.j2").write_text(
        "function buildValidationFieldErrors(errors, parentPath = '') {\n"
        "  path = `${parentPath}.${error.property}`;\n"
        "}\n",
        encoding="utf-8",
    )
    sites = census_source("typescript", ts_bad)
    ok &= _assert(
        len(sites) == 1 and sites[0].spelled_path != _CANONICAL_PATH,
        f"a builder missing the `[n]`-index construction censuses as divergent (got {sites})",
    )

    java_good = tmp_root / "java-good"
    java_good.mkdir(parents=True)
    (java_good / "ExceptionHandler.java.j2").write_text(
        'errors.add(new FieldError(fe.getField(), message, "validation"));\n', encoding="utf-8",
    )
    sites = census_source("java", java_good)
    ok &= _assert(
        len(sites) == 1 and sites[0].spelled_path == _CANONICAL_PATH,
        f"a Spring FieldError.getField() call site censuses as canonical (got {sites})",
    )

    dotnet_empty = tmp_root / "dotnet-empty"
    dotnet_empty.mkdir(parents=True)
    (dotnet_empty / "Nothing.cs.j2").write_text("// no field-error construction here\n", encoding="utf-8")
    sites = census_source("dotnet", dotnet_empty)
    ok &= _assert(sites == (), "a language with no known detector censuses to zero sites")

    return ok


def _self_test_min_languages_refusal() -> bool:
    """A single registered language is not a cross-language comparison --
    `_require_min_languages` must refuse it with `EXIT_USAGE`, the same
    refuse-under-two floor every other axis-scanning gate in this repo
    carries."""
    try:
        _require_min_languages(frozenset({"only-one"}))
        return _assert(False, "a single-language set is refused")
    except SystemExit as exc:
        return _assert(exc.code == EXIT_USAGE, "a single-language set is refused")


def _self_test_live_read() -> bool:
    censuses, reasons = scan_all_registered_languages()
    realizing_or_declaring = sorted(
        language
        for language in censuses
        if any(site.spelled_path == _CANONICAL_PATH for site in censuses[language])
        or reasons.get(language) is not None
    )
    return _assert(
        len(realizing_or_declaring) >= 1,
        f"live census finds at least one language realizing or declaring the rule "
        f"(found: {realizing_or_declaring})",
    )


def self_test() -> bool:
    """Non-vacuity self-test: a planted realized language passes; a planted
    divergent spelling with no declared reason fails naming the divergence; a
    declared reason with an empty string fails; realizing AND declaring fails
    as a stale declaration; fewer than two registered languages refuses with
    `EXIT_USAGE`; the live census finds at least one registered language
    realizing OR declaring the rule (a scan that sees nothing is broken, not
    clean)."""
    print("Non-vacuity self-test:")
    tmp_root = Path(tempfile.mkdtemp(prefix="field-error-path-gate-"))
    try:
        ok = _self_test_census(tmp_root)
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    ok &= _self_test_comparator()
    ok &= _self_test_min_languages_refusal()
    ok &= _self_test_live_read()
    return ok


def main(argv: list[str] | None = None) -> int:
    """`--debug`, `--self-test`; same three exit codes as
    `problem_type_parity.main` (0 clean, 1 violation(s), 2 usage/self-test
    failure)."""
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
    censuses, reasons = scan_all_registered_languages()
    problems, verdicts = evaluate(_CANONICAL_PATH, censuses, reasons)
    print(f"\nField-error-path census ({len(censuses)} registered language(s)):")
    print(render_report(_CANONICAL_PATH, verdicts))
    if problems:
        print(f"\nError: {len(problems)} field-error-path parity violation(s):", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return EXIT_FAIL
    print("\nEvery registered language realizes the field-error-path rule or declares the hole.")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
