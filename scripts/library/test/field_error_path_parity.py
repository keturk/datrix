"""Field-error-path parity gate -- every registered language spells
`request-validation` problem-body `errors[].field` paths with ONE dot-separated,
`body`-prefix-free, `[n]`-array-indexed rule
(`datrix_common.datrix_model.problem_types.FIELD_ERROR_PATH_RULE`).

Unlike the problem-type and framework-header registries, this is not a table of
named families: there is exactly ONE rule, so the gate holds each language to
that one rule. It is a hard zero: every registered language is obligated to
realize it, and no declaration excuses a language that does not.

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
* A language with no known construction technique censuses to zero sites,
  which `evaluate()` reports as a language that does not realize the rule.

Language set from the installed `datrix.languages` entry points at runtime --
never a table in this script. Runs a built-in non-vacuity self-test on every
invocation. Repo-level validation script (per the datrix showcase boundary --
no pytest suite lives in datrix).
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

from datrix_common.datrix_model.problem_types import (  # noqa: E402
    FIELD_ERROR_PATH_RULE,
    FieldErrorCode,
    FieldErrorLocation,
)

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

#: The located fixture that proves `location` and `code` beside the body path:
#: a missing path parameter, a query value of the wrong type and an unknown body
#: field, as pydantic reports them, and the `(location, field, code)` entries the
#: registry's vocabulary derives from them.
_CANONICAL_LOCATED_ERRORS: Final[tuple[dict[str, object], ...]] = (
    {"loc": ("path", "sku"), "type": "missing"},
    {"loc": ("query", "limit"), "type": "int_parsing"},
    {"loc": _CANONICAL_LOC, "type": "extra_forbidden"},
)
_CANONICAL_LOCATED: Final[tuple[tuple[str, str, str], ...]] = (
    (FieldErrorLocation.PATH, "sku", FieldErrorCode.REQUIRED),
    (FieldErrorLocation.QUERY, "limit", FieldErrorCode.INVALID),
    (FieldErrorLocation.BODY, _CANONICAL_PATH, FieldErrorCode.UNKNOWN_FIELD),
)
_CANONICAL_PATH_FIELD_NAMES: Final[dict[str, str]] = {"sku": "sku"}


@dataclass(frozen=True, slots=True)
class RealizationSite:
    """One place a language's source spells a field-error-path construction --
    a candidate realization or divergence, found by the census."""

    language: str
    package: str
    """The package repo the site lives in -- a language's backend or one of its cores."""
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
_PYTHON_CLASSIFIER_DEF_RE: Final[re.Pattern[str]] = re.compile(r"def\s+classify_request_validation\(")
_TS_BUILDER_DEF_RE: Final[re.Pattern[str]] = re.compile(r"function\s+joinPath\(")
_TS_ARRAY_BRACKET_RE: Final[re.Pattern[str]] = re.compile(r"\$\{parentPath\}\[\$\{property\}\]")
_TS_DOT_JOIN_RE: Final[re.Pattern[str]] = re.compile(r"\$\{parentPath\}\.\$\{property\}")


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
    name = f"_field_error_path_census_{path.stem}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load a module spec for {path}.")
    module = importlib.util.module_from_spec(spec)
    # A dataclass resolves its string annotations through its own module's entry
    # in sys.modules, so the module is registered for the length of the exec.
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        del sys.modules[name]
    return module


def _classifier_divergence(path: Path) -> str | None:
    """What `classify_request_validation` produces for the located canonical
    fixture when that differs from the registry's derivation, else `None`.

    The classifier takes the body formatter as an argument; the realization that
    ships beside it (`field_error_path.py`) is the one it is executed with."""
    classify = getattr(_load_module_from_path(path), "classify_request_validation", None)
    if classify is None:
        return None
    formatter_path = path.with_name("field_error_path.py")
    formatter = getattr(_load_module_from_path(formatter_path), "format_field_error_path", None)
    if formatter is None:
        return f"no format_field_error_path beside {path.name}"
    refusal = classify(
        _CANONICAL_LOCATED_ERRORS,
        path_field_names=_CANONICAL_PATH_FIELD_NAMES,
        format_body_path=formatter,
    )
    produced = tuple((e.location, e.field, e.code) for e in refusal.errors)
    if produced == _CANONICAL_LOCATED:
        return None
    return f"located entries {produced!r}, expected {_CANONICAL_LOCATED!r}"


def _census_python(package: str, src_dir: Path, files: list[Path]) -> tuple[RealizationSite, ...]:
    """Python realizes the rule with a real, callable mapping function --
    found by its definition, then EXECUTED against the canonical fixture. The
    request classifier is executed against the located fixture too: a path or
    query entry that lands in the wrong location, field or code is a divergence
    recorded at the classifier's definition."""
    sites: list[RealizationSite] = []
    for path in files:
        if path.suffix != ".py":
            continue
        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if _PYTHON_CLASSIFIER_DEF_RE.search(line):
                divergence = _classifier_divergence(path)
                if divergence is not None:
                    sites.append(
                        RealizationSite(
                            "python",
                            package,
                            path.relative_to(src_dir).as_posix(),
                            line_number,
                            f"{_CANONICAL_PATH} ({divergence})",
                        )
                    )
            if not _PYTHON_FORMATTER_DEF_RE.search(line):
                continue
            module = _load_module_from_path(path)
            formatter = getattr(module, "format_field_error_path", None)
            if formatter is None:
                continue
            produced = formatter(_CANONICAL_LOC)
            sites.append(
                RealizationSite("python", package, path.relative_to(src_dir).as_posix(), line_number, produced)
            )
    return tuple(sites)


def _census_typescript(package: str, src_dir: Path, files: list[Path]) -> tuple[RealizationSite, ...]:
    """TypeScript realizes the rule with a hand-written recursive builder over
    class-validator's own `ValidationError` tree (`request-validation.ts.j2`'s
    `joinPath`). class-validator's tree starts at the DTO's
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
                sites.append(RealizationSite("typescript", package, relative, line_number, _CANONICAL_PATH))
            else:
                sites.append(
                    RealizationSite(
                        "typescript",
                        package,
                        relative,
                        line_number,
                        f"{_CANONICAL_PATH} (missing the canonical `[n]`-index / `.`-join "
                        f"construction)",
                    )
                )
    return tuple(sites)


#: `{language: detector}` -- the plumbing that dispatches a discovered
#: language's sources to its own construction-technique census. A language
#: absent here (a future target, or one with no known technique yet) censuses
#: to zero sites, which `evaluate()` reports as a language that does not
#: realize the rule. This is NOT the retired per-family mapping shape: it
#: holds only a census FUNCTION, because there is no family axis on a
#: one-rule gate.
_CENSUS_DISPATCH: Final[Mapping[str, Callable[[str, Path, list[Path]], tuple[RealizationSite, ...]]]] = {
    "python": _census_python,
    "typescript": _census_typescript,
}


def census_sources(language: str, src_dirs: tuple[Path, ...]) -> tuple[RealizationSite, ...]:
    """Every field-error-path construction site for `language` under every
    package implementing it -- its backend and each language core. Each
    `src_dir` is `<package>/src/<import_name>`; a site records its package."""
    detector = _CENSUS_DISPATCH.get(language)
    if detector is None:
        return ()
    sites: list[RealizationSite] = []
    for src_dir in src_dirs:
        sites.extend(detector(src_dir.parents[1].name, src_dir, _iter_source_files(src_dir)))
    return tuple(sites)


# ---------------------------------------------------------------------------
# Comparator
# ---------------------------------------------------------------------------


def evaluate(
    canonical_path: str,
    censuses: Mapping[str, tuple[RealizationSite, ...]],
) -> tuple[list[str], dict[str, LanguageVerdict]]:
    """Every violation across every registered language, plus the per-language
    verdicts the report renders.

    A language realizes the rule when its census sites spell *canonical_path*
    exactly for the shared fixture. Every registered language is obligated to:
    an empty census is a language that does not realize the rule (fails, and no
    declaration can excuse it), and a divergent spelling is a violation naming
    the found spelling and the expected one.
    """
    problems: list[str] = []
    verdicts: dict[str, LanguageVerdict] = {}
    for language in sorted(censuses):
        sites = censuses[language]
        realized = any(site.spelled_path == canonical_path for site in sites)
        for site in sites:
            if site.spelled_path == canonical_path:
                continue
            problems.append(
                f"{language}: {site.package}: {site.relative_path}:{site.line}: spells field-error path "
                f"{site.spelled_path!r}, which diverges from the canonical form "
                f"{canonical_path!r} FIELD_ERROR_PATH_RULE derives. Fix: match the rule's "
                f"dot-separated, body-prefix-free, `[n]`-indexed form."
            )
        if not sites:
            problems.append(
                f"{language}: does not spell the canonical field-error path "
                f"({canonical_path!r}). Every registered language is obligated to realize "
                f"FIELD_ERROR_PATH_RULE. Fix: realize the rule's form in the language's sources."
            )
        verdicts[language] = LanguageVerdict(language, realized)
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


def scan_all_registered_languages() -> dict[str, tuple[RealizationSite, ...]]:
    """Census every registered `datrix.languages` package's `.py`/`.j2` sources
    for field-error-path construction sites."""
    language_names = registered_language_names()
    _require_min_languages(language_names)
    src_dirs = discover_target_package_src_dirs(AXIS_LANGUAGES, language_names, WORKSPACE_ROOT)
    censuses: dict[str, tuple[RealizationSite, ...]] = {}
    for language, language_src_dirs in sorted(src_dirs.items()):
        censuses[language] = census_sources(language, language_src_dirs)
        logger.debug("census language=%s sites=%d", language, len(censuses[language]))
    return censuses


def render_report(canonical_path: str, verdicts: Mapping[str, LanguageVerdict]) -> str:
    lines = [f"  canonical field-error path: {canonical_path!r}"]
    width = max(len("language"), *(len(language) for language in verdicts)) if verdicts else len("language")
    for language in sorted(verdicts):
        verdict = verdicts[language]
        status = "realized" if verdict.realized else "MISSING"
        lines.append(f"  {language.ljust(width)}  {status}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Non-vacuity self-test
# ---------------------------------------------------------------------------


def _assert(condition: bool, label: str) -> bool:
    print(f"  {'PASS' if condition else 'FAIL'}: {label}")
    return condition


def _planted(language: str, spelled_path: str) -> tuple[RealizationSite, ...]:
    return (RealizationSite(language, f"datrix-codegen-{language}", "planted.j2", 1, spelled_path),)


def _self_test_comparator() -> bool:
    ok = True
    canonical = _CANONICAL_PATH

    clean = {"alpha": _planted("alpha", canonical), "beta": _planted("beta", canonical)}
    problems, verdicts = evaluate(canonical, clean)
    ok &= _assert(problems == [], "two languages spelling the canonical path report no problem")
    ok &= _assert(verdicts["alpha"].realized, "the verdict records realization")

    divergent_path = "body." + canonical
    divergent = {"alpha": _planted("alpha", divergent_path), "beta": clean["beta"]}
    problems, _ = evaluate(canonical, divergent)
    ok &= _assert(
        len(problems) == 1 and divergent_path in problems[0] and canonical in problems[0],
        "a divergent spelling is one violation naming the found and expected paths",
    )

    unrealized = {"alpha": (), "beta": clean["beta"]}
    problems, verdicts = evaluate(canonical, unrealized)
    ok &= _assert(
        len(problems) == 1 and problems[0].startswith("alpha:") and "does not spell" in problems[0],
        "a language that realizes nothing is exactly one problem naming it, and evaluate takes no "
        "declaration input that could excuse it",
    )
    ok &= _assert(
        not verdicts["alpha"].realized and verdicts["beta"].realized,
        "the verdict marks only the non-realizing language missing",
    )
    return ok


#: A correct, self-contained `format_field_error_path` -- the planted
#: realization of the executed-formatter technique.
_CANONICAL_FORMATTER_SOURCE: Final[str] = (
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
    "    return ''.join(parts)\n"
)


#: A self-contained `classify_request_validation` for the self-test; the
#: `{location_expr}` hole is what decides each entry's location.
_FIXTURE_CLASSIFIER_SOURCE: Final[str] = (
    "from collections import namedtuple\n"
    "Entry = namedtuple('Entry', 'location field code')\n"
    "Result = namedtuple('Result', 'errors')\n"
    "CODES = {{'missing': 'required', 'extra_forbidden': 'unknown_field'}}\n"
    "def classify_request_validation(errors, *, path_field_names, format_body_path):\n"
    "    out = []\n"
    "    for error in errors:\n"
    "        loc = error['loc']\n"
    "        if loc[0] == 'body':\n"
    "            field = format_body_path(loc)\n"
    "        elif loc[0] == 'path':\n"
    "            field = path_field_names[loc[1]]\n"
    "        else:\n"
    "            field = loc[1]\n"
    "        out.append(Entry({location_expr}, field, CODES.get(error['type'], 'invalid')))\n"
    "    return Result(tuple(out))\n"
)


def _fixture_src(tmp_root: Path, package: str) -> Path:
    """A fixture ``<package>/src/<import_name>`` tree, the shape every
    discovered src dir has."""
    src = tmp_root / package / "src" / package.replace("-", "_")
    src.mkdir(parents=True)
    return src


def _self_test_census(tmp_root: Path) -> bool:
    ok = True

    py_good = _fixture_src(tmp_root, "python-good")
    (py_good / "field_error_path.py").write_text(_CANONICAL_FORMATTER_SOURCE, encoding="utf-8")
    sites = census_sources("python", (py_good,))
    ok &= _assert(
        len(sites) == 1 and sites[0].spelled_path == _CANONICAL_PATH,
        f"a correct python formatter's real execution produces the canonical path (got {sites})",
    )

    py_bad = _fixture_src(tmp_root, "python-bad")
    (py_bad / "field_error_path.py").write_text(
        "def format_field_error_path(loc):\n"
        "    return '.'.join(str(s) for s in loc)\n",
        encoding="utf-8",
    )
    sites = census_sources("python", (py_bad,))
    ok &= _assert(
        len(sites) == 1 and sites[0].spelled_path != _CANONICAL_PATH,
        f"a divergent python formatter's real execution surfaces its actual wrong output (got {sites})",
    )

    classified_good = _fixture_src(tmp_root, "python-classifier-good")
    (classified_good / "field_error_path.py").write_text(_CANONICAL_FORMATTER_SOURCE, encoding="utf-8")
    (classified_good / "request_validation.py").write_text(
        _FIXTURE_CLASSIFIER_SOURCE.format(location_expr="loc[0]"), encoding="utf-8"
    )
    sites = census_sources("python", (classified_good,))
    ok &= _assert(
        len(sites) == 1 and sites[0].spelled_path == _CANONICAL_PATH,
        f"a classifier placing path, query and body entries in their own locations is canonical (got {sites})",
    )

    classified_bad = _fixture_src(tmp_root, "python-classifier-bad")
    (classified_bad / "field_error_path.py").write_text(_CANONICAL_FORMATTER_SOURCE, encoding="utf-8")
    (classified_bad / "request_validation.py").write_text(
        _FIXTURE_CLASSIFIER_SOURCE.format(location_expr="'body'"), encoding="utf-8"
    )
    sites = census_sources("python", (classified_bad,))
    ok &= _assert(
        len(sites) == 2
        and any("located entries" in site.spelled_path for site in sites),
        f"a classifier reporting every entry at the body location surfaces a location divergence (got {sites})",
    )

    ts_good = _fixture_src(tmp_root, "typescript-good")
    (ts_good / "request-validation.ts.j2").write_text(
        "function joinPath(parentPath: string, property: string): string {\n"
        "  if (isArrayIndex) { return `${parentPath}[${property}]`; }\n"
        "  return parentPath === '' ? property : `${parentPath}.${property}`;\n"
        "}\n",
        encoding="utf-8",
    )
    sites = census_sources("typescript", (ts_good,))
    ok &= _assert(
        len(sites) == 1 and sites[0].spelled_path == _CANONICAL_PATH,
        f"a correct typescript builder censuses as canonical (got {sites})",
    )

    ts_bad = _fixture_src(tmp_root, "typescript-bad")
    (ts_bad / "request-validation.ts.j2").write_text(
        "function joinPath(parentPath: string, property: string): string {\n"
        "  return `${parentPath}.${property}`;\n"
        "}\n",
        encoding="utf-8",
    )
    sites = census_sources("typescript", (ts_bad,))
    ok &= _assert(
        len(sites) == 1 and sites[0].spelled_path != _CANONICAL_PATH,
        f"a builder missing the `[n]`-index construction censuses as divergent (got {sites})",
    )

    unknown_empty = _fixture_src(tmp_root, "unknown-language")
    (unknown_empty / "nothing.py").write_text(
        "def format_field_error_path(loc):\n    return 'never read'\n", encoding="utf-8",
    )
    sites = census_sources("self_test_unregistered_language", (unknown_empty,))
    ok &= _assert(sites == (), "a language with no known detector censuses to zero sites")

    return ok


def _self_test_language_core(tmp_root: Path) -> bool:
    """A fixture language split into a backend and a core: a realization that
    lives only in the core is censused for the language and recorded against
    the core package; a backend-only census (the pre-split blindness) sees
    nothing. The language key is whichever registered detector runs the
    executed-formatter technique, looked up by function, never by name."""
    language = next(name for name, detector in _CENSUS_DISPATCH.items() if detector is _census_python)
    backend = _fixture_src(tmp_root, "datrix-codegen-splitlang")
    core = _fixture_src(tmp_root, "datrix-codegen-splitlang-core")
    (backend / "plugin.py").write_text("NAME = 'splitlang'\n", encoding="utf-8")
    (core / "field_error_path.py").write_text(_CANONICAL_FORMATTER_SOURCE, encoding="utf-8")
    split = census_sources(language, (backend, core))
    backend_only = census_sources(language, (backend,))
    found = [(site.package, site.spelled_path) for site in split]
    return _assert(
        found == [("datrix-codegen-splitlang-core", _CANONICAL_PATH)] and backend_only == (),
        f"a fixture language split into a backend and a core: the census sees the realization planted in the "
        f"core (got {found}); a backend-only census does not",
    )


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
    censuses = scan_all_registered_languages()
    realizing = sorted(
        language
        for language in censuses
        if any(site.spelled_path == _CANONICAL_PATH for site in censuses[language])
    )
    return _assert(
        len(realizing) >= 1,
        f"live census finds at least one language realizing the rule (found: {realizing})",
    )


def self_test() -> bool:
    """Non-vacuity self-test: a planted realized language passes; a planted
    divergent spelling fails naming the divergence; a language that realizes
    nothing fails with no declaration to excuse it; fewer than two registered
    languages refuses with `EXIT_USAGE`; the live census finds at least one
    registered language realizing the rule (a scan that sees nothing is
    broken, not clean)."""
    print("Non-vacuity self-test:")
    tmp_root = Path(tempfile.mkdtemp(prefix="field-error-path-gate-"))
    try:
        ok = _self_test_census(tmp_root)
        ok &= _self_test_language_core(tmp_root)
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
    censuses = scan_all_registered_languages()
    problems, verdicts = evaluate(_CANONICAL_PATH, censuses)
    print(f"\nField-error-path census ({len(censuses)} registered language(s)):")
    print(render_report(_CANONICAL_PATH, verdicts))
    if problems:
        print(f"\nError: {len(problems)} field-error-path parity violation(s):", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return EXIT_FAIL
    print("\nEvery registered language realizes the field-error-path rule.")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
