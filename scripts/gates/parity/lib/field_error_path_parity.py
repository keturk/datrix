"""Field-error-path parity gate -- every registered language spells
`request-validation` problem-body `errors[].field` paths with ONE dot-separated,
`body`-prefix-free, `[n]`-array-indexed rule
(`datrix_common.datrix_model.problem_types.FIELD_ERROR_PATH_RULE`).

Unlike the problem-type and framework-header registries, this is not a table of
named families: there is exactly ONE rule, so the gate holds each language to
that one rule. It is a hard zero: every registered language is obligated to
realize it, and no declaration excuses a language that does not.

Realization is a runtime BEHAVIOUR, not a literal wire string every backend
spells identically, so there is no single cross-language regex to census for.
Each language DECLARES how it realizes the rule on its own
`LanguageCapabilityDeclaration.field_error_path_realization`, and this gate
holds only the two techniques that declaration can name -- a closed set in the
shared declaration module, never a language name:

* `ExecutedFieldErrorPathFormatter` -- the language inlines a reference
  function. The gate checks the declared module lies inside the language's own
  distribution, imports it and EXECUTES the function against the shared
  canonical fixture (the only way to prove what a mapping *function* produces).
  A declared request classifier is executed against the located fixture too.
* `TemplateFieldErrorPathConstruction` -- the language builds the path in
  template code. The gate checks the declared template exists in exactly one of
  the language's packages, the builder's anchor is present and every declared
  construction is present.

Both techniques also prove the declared call site matches in the language's
sources: a realization nothing calls is not on the emission path.

A language declaring nothing fails by name. Language set from the installed
`datrix.languages` entry points at runtime -- never a table in this script. Runs
a built-in non-vacuity self-test on every invocation. Repo-level validation
script (per the datrix showcase boundary -- no pytest suite lives in datrix).
"""

from __future__ import annotations

import argparse
import contextlib
import importlib
import importlib.util
import inspect
import logging
import re
import shutil
import sys
import tempfile
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from datrix_common.datrix_model.problem_types import (  # noqa: E402
    FIELD_ERROR_PATH_RULE,
    FieldErrorCode,
    FieldErrorLocation,
)
from datrix_common.plugin.capability_resolution import declaration_for_language  # noqa: E402
from datrix_common.plugin.language_capability import (  # noqa: E402
    ExecutedFieldErrorPathFormatter,
    ExecutedLocatedClassifier,
    FieldErrorPathRealization,
    TemplateFieldErrorPathConstruction,
)

from datrix_scripts.registered_targets import (  # noqa: E402
    AXIS_LANGUAGES,
    WORKSPACE_ROOT,
    discover_target_package_src_dirs,
    registered_language_names,  # noqa: E402
    self_test_gate_names_no_target,
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
    """One place a language's source realizes the field-error-path rule --
    a candidate realization or divergence, found by the census."""

    language: str
    package: str
    """The package repo the site lives in -- a language's backend or one of its cores."""
    relative_path: str
    line: int
    spelled_path: str
    """The path this site produces for the shared canonical fixture loc
    (`FIELD_ERROR_PATH_RULE`'s own worked example): the executed function's real
    output, or the canonical form when every declared construction is present,
    or the canonical form annotated with what is missing."""


@dataclass(frozen=True, slots=True)
class LanguageCensus:
    """What the gate found for one language that declared a realization."""

    sites: tuple[RealizationSite, ...]
    defects: tuple[str, ...]
    """Declared-but-unproven facts: a module or template outside the language's
    distribution, an absent anchor or function, an uncalled realization, a
    classifier that places an entry wrongly."""


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


def _package_of(src_dir: Path) -> str:
    """`<package>/src/<import_name>` -> `<package>`."""
    return src_dir.parents[1].name


def _containing_src_dir(path: Path, src_dirs: tuple[Path, ...]) -> Path | None:
    resolved = path.resolve()
    for src_dir in src_dirs:
        if resolved.is_relative_to(src_dir.resolve()):
            return src_dir
    return None


def _call_site_defect(
    call_site: str, src_dirs: tuple[Path, ...], *, excluding: frozenset[Path]
) -> str | None:
    """A defect when *call_site* matches in no `.j2`/`.py` source of the language
    (apart from *excluding*, the realization's own definition file)."""
    pattern = re.compile(call_site)
    for src_dir in src_dirs:
        for path in _iter_source_files(src_dir):
            if path.resolve() in excluding:
                continue
            if pattern.search(path.read_text(encoding="utf-8")):
                return None
    return (
        f"declared call site {call_site!r} matches no .j2/.py source of the language: the "
        f"realization is defined but not on the emission path. Fix: call it from the emitted "
        f"code, or correct the declared call_site."
    )


# ---------------------------------------------------------------------------
# Technique: executed formatter
# ---------------------------------------------------------------------------


def _import_declared_module(
    module_name: str, src_dirs: tuple[Path, ...]
) -> tuple[object | None, Path | None, str | None]:
    """Import *module_name* only when it lies inside one of the language's own
    src dirs. Returns `(module, origin, defect)`; a defect leaves the other two
    `None`. A declaration pointing into another distribution is a violation,
    never an execution."""
    try:
        spec = importlib.util.find_spec(module_name)
    except ImportError as exc:
        return None, None, f"declared module {module_name!r} is not importable ({exc})"
    if spec is None or spec.origin is None or spec.origin in ("built-in", "frozen"):
        return None, None, f"declared module {module_name!r} has no source file to execute"
    origin = Path(spec.origin)
    if _containing_src_dir(origin, src_dirs) is None:
        return (
            None,
            None,
            f"declared module {module_name!r} resolves to {origin}, outside this language's own "
            f"src dirs ({', '.join(str(d) for d in src_dirs)}); the gate executes only a module "
            f"inside the declaring language's distribution",
        )
    return importlib.import_module(module_name), origin, None


def _function_line(function: object) -> int | None:
    if not inspect.isfunction(function):
        return None
    try:
        return inspect.getsourcelines(function)[1]
    except OSError:
        return None


def _classifier_divergence(
    classifier: ExecutedLocatedClassifier,
    formatter: object,
    src_dirs: tuple[Path, ...],
) -> str | None:
    """What the declared classifier produces for the located canonical fixture
    when that differs from the registry's derivation, else `None`."""
    module, _, defect = _import_declared_module(classifier.module, src_dirs)
    if defect is not None:
        return f"located classifier: {defect}"
    classify = getattr(module, classifier.function, None)
    if classify is None:
        return f"located classifier {classifier.module}.{classifier.function} does not exist"
    refusal = classify(
        _CANONICAL_LOCATED_ERRORS,
        path_field_names=_CANONICAL_PATH_FIELD_NAMES,
        format_body_path=formatter,
    )
    produced = tuple((e.location, e.field, e.code) for e in refusal.errors)
    if produced == _CANONICAL_LOCATED:
        return None
    return (
        f"located classifier {classifier.module}.{classifier.function} produced located entries "
        f"{produced!r}, expected {_CANONICAL_LOCATED!r}"
    )


def _census_executed(
    language: str, src_dirs: tuple[Path, ...], realization: ExecutedFieldErrorPathFormatter
) -> LanguageCensus:
    module, origin, defect = _import_declared_module(realization.module, src_dirs)
    if defect is not None or origin is None:
        return LanguageCensus((), (defect or "declared module could not be imported",))
    formatter = getattr(module, realization.function, None)
    if formatter is None:
        return LanguageCensus(
            (), (f"declared function {realization.module}.{realization.function} does not exist",)
        )
    line = _function_line(formatter)
    if line is None:
        return LanguageCensus(
            (),
            (f"declared function {realization.module}.{realization.function} is not a plain function "
             f"defined in source",),
        )
    src_dir = _containing_src_dir(origin, src_dirs)
    if src_dir is None:
        return LanguageCensus((), (f"declared module {realization.module!r} left the language's src dirs",))
    site = RealizationSite(
        language,
        _package_of(src_dir),
        origin.resolve().relative_to(src_dir.resolve()).as_posix(),
        line,
        formatter(_CANONICAL_LOC),
    )
    defects: list[str] = []
    if realization.located_classifier is not None:
        divergence = _classifier_divergence(realization.located_classifier, formatter, src_dirs)
        if divergence is not None:
            defects.append(divergence)
    call_defect = _call_site_defect(
        realization.call_site, src_dirs, excluding=frozenset({origin.resolve()})
    )
    if call_defect is not None:
        defects.append(call_defect)
    return LanguageCensus((site,), tuple(defects))


# ---------------------------------------------------------------------------
# Technique: template construction
# ---------------------------------------------------------------------------


def _census_template(
    language: str, src_dirs: tuple[Path, ...], realization: TemplateFieldErrorPathConstruction
) -> LanguageCensus:
    holders = [src_dir for src_dir in src_dirs if (src_dir / realization.template).is_file()]
    if not holders:
        return LanguageCensus(
            (),
            (f"declared template {realization.template!r} exists under none of this language's "
             f"src dirs ({', '.join(str(d) for d in src_dirs)})",),
        )
    if len(holders) > 1:
        return LanguageCensus(
            (),
            (f"declared template {realization.template!r} exists in {len(holders)} of this "
             f"language's packages ({', '.join(_package_of(d) for d in holders)}); the path must "
             f"name exactly one",),
        )
    src_dir = holders[0]
    path = src_dir / realization.template
    if _containing_src_dir(path, (src_dir,)) is None:
        return LanguageCensus(
            (), (f"declared template {realization.template!r} resolves outside {src_dir}",)
        )
    text = path.read_text(encoding="utf-8")
    anchor = re.search(realization.anchor, text)
    if anchor is None:
        return LanguageCensus(
            (),
            (f"declared anchor {realization.anchor!r} is absent from {realization.template!r}: "
             f"the builder it names is not defined there",),
        )
    line = text.count("\n", 0, anchor.start()) + 1
    missing = [c for c in realization.constructions if re.search(c, text) is None]
    spelled = (
        _CANONICAL_PATH
        if not missing
        else f"{_CANONICAL_PATH} (missing the declared construction(s) {missing!r})"
    )
    site = RealizationSite(language, _package_of(src_dir), realization.template, line, spelled)
    defects: list[str] = []
    call_defect = _call_site_defect(realization.call_site, src_dirs, excluding=frozenset())
    if call_defect is not None:
        defects.append(call_defect)
    return LanguageCensus((site,), tuple(defects))


def census_language(
    language: str,
    src_dirs: tuple[Path, ...],
    realization: FieldErrorPathRealization,
) -> LanguageCensus:
    """Census one language under every package implementing it -- its backend
    and each language core -- by the technique its declaration names. Dispatches
    on the declaration TYPE, a closed set in the shared declaration module."""
    if isinstance(realization, ExecutedFieldErrorPathFormatter):
        return _census_executed(language, src_dirs, realization)
    if isinstance(realization, TemplateFieldErrorPathConstruction):
        return _census_template(language, src_dirs, realization)
    raise TypeError(
        f"{language}: field_error_path_realization is a {type(realization).__name__}; expected an "
        f"ExecutedFieldErrorPathFormatter or a TemplateFieldErrorPathConstruction."
    )


# ---------------------------------------------------------------------------
# Comparator
# ---------------------------------------------------------------------------


def evaluate(
    canonical_path: str,
    censuses: Mapping[str, LanguageCensus | None],
) -> tuple[list[str], dict[str, LanguageVerdict]]:
    """Every violation across every registered language, plus the per-language
    verdicts the report renders.

    A language realizes the rule when its declared realization is proven (no
    defect) and spells *canonical_path* exactly for the shared fixture. Every
    registered language is obligated to: a language that declared nothing
    (`None`) fails by name, a declared-but-unproven realization is a violation
    naming the defect, and a divergent spelling names the found and expected
    paths. No declaration can excuse a language.
    """
    problems: list[str] = []
    verdicts: dict[str, LanguageVerdict] = {}
    for language in sorted(censuses):
        census = censuses[language]
        if census is None:
            problems.append(
                f"{language}: declares no field-error-path realization on its "
                f"LanguageCapabilityDeclaration. Every registered language is obligated to realize "
                f"FIELD_ERROR_PATH_RULE and to declare how. Fix: set field_error_path_realization."
            )
            verdicts[language] = LanguageVerdict(language, False)
            continue
        divergent = [site for site in census.sites if site.spelled_path != canonical_path]
        for site in divergent:
            problems.append(
                f"{language}: {site.package}: {site.relative_path}:{site.line}: spells field-error path "
                f"{site.spelled_path!r}, which diverges from the canonical form "
                f"{canonical_path!r} FIELD_ERROR_PATH_RULE derives. Fix: match the rule's "
                f"dot-separated, body-prefix-free, `[n]`-indexed form."
            )
        for defect in census.defects:
            problems.append(f"{language}: {defect}")
        if not census.sites and not census.defects:
            problems.append(
                f"{language}: does not spell the canonical field-error path "
                f"({canonical_path!r}). Fix: realize the rule's form in the language's sources."
            )
        verdicts[language] = LanguageVerdict(
            language, bool(census.sites) and not divergent and not census.defects
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


def scan_all_registered_languages() -> dict[str, LanguageCensus | None]:
    """Census every registered `datrix.languages` package by the realization it
    declares; a language that declares none is `None`, never skipped."""
    language_names = registered_language_names()
    _require_min_languages(language_names)
    src_dirs = discover_target_package_src_dirs(AXIS_LANGUAGES, language_names, WORKSPACE_ROOT)
    censuses: dict[str, LanguageCensus | None] = {}
    for language, language_src_dirs in sorted(src_dirs.items()):
        realization = declaration_for_language(language).field_error_path_realization
        censuses[language] = (
            None if realization is None else census_language(language, language_src_dirs, realization)
        )
        logger.debug("census language=%s declared=%s", language, realization is not None)
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

_FIXTURE_LANGUAGE: Final[str] = "selftestlang"
_FIXTURE_CALL_SITE: Final[str] = r"render_path\(loc\)"
_FIXTURE_CALL_SOURCE: Final[str] = "result = render_path(loc)\n"


def _assert(condition: bool, label: str) -> bool:
    print(f"  {'PASS' if condition else 'FAIL'}: {label}")
    return condition


def _planted(language: str, spelled_path: str) -> LanguageCensus:
    return LanguageCensus(
        (RealizationSite(language, f"datrix-codegen-{language}", "planted.j2", 1, spelled_path),), ()
    )


def _raises_value_error(call: Callable[[], object]) -> bool:
    try:
        call()
    except ValueError:
        return True
    return False


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

    undeclared = {"alpha": None, "beta": clean["beta"]}
    problems, verdicts = evaluate(canonical, undeclared)
    ok &= _assert(
        len(problems) == 1
        and problems[0].startswith("alpha:")
        and "declares no field-error-path realization" in problems[0],
        "a language declaring None is exactly one problem naming it, and evaluate takes no "
        "declaration input that could excuse it",
    )
    ok &= _assert(
        not verdicts["alpha"].realized and verdicts["beta"].realized,
        "the verdict marks only the undeclaring language missing",
    )

    defective = {
        "alpha": LanguageCensus(clean["alpha"].sites, ("declared call site 'x' matches nothing",)),
        "beta": clean["beta"],
    }
    problems, verdicts = evaluate(canonical, defective)
    ok &= _assert(
        len(problems) == 1 and "matches nothing" in problems[0] and not verdicts["alpha"].realized,
        "a canonical spelling with a defect is one violation and is not realized",
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

_DIVERGENT_FORMATTER_SOURCE: Final[str] = (
    "def format_field_error_path(loc):\n    return '.'.join(str(s) for s in loc)\n"
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

_FIXTURE_BUILDER_SOURCE: Final[str] = (
    "function buildPath(parentPath: string, property: string): string {\n"
    "  if (isArrayIndex) { return `${parentPath}[${property}]`; }\n"
    "  return parentPath === '' ? property : `${parentPath}.${property}`;\n"
    "}\n"
    "const path = buildPath(parentPath, error.property);\n"
)
_FIXTURE_BUILDER_NO_BRACKET_SOURCE: Final[str] = (
    "function buildPath(parentPath: string, property: string): string {\n"
    "  return `${parentPath}.${property}`;\n"
    "}\n"
    "const path = buildPath(parentPath, error.property);\n"
)
_FIXTURE_TEMPLATE: Final[str] = "templates/request-validation.ts.j2"
_FIXTURE_TEMPLATE_DECLARATION: Final[TemplateFieldErrorPathConstruction] = (
    TemplateFieldErrorPathConstruction(
        template=_FIXTURE_TEMPLATE,
        anchor=r"function\s+buildPath\(",
        constructions=(r"\$\{parentPath\}\[\$\{property\}\]", r"\$\{parentPath\}\.\$\{property\}"),
        call_site=r"buildPath\(parentPath, error\.property\)",
    )
)


def _import_name(package: str) -> str:
    return package.replace("-", "_")


def _fixture_src(tmp_root: Path, package: str) -> Path:
    """A fixture ``<package>/src/<import_name>`` tree, the shape every
    discovered src dir has."""
    src = tmp_root / package / "src" / _import_name(package)
    src.mkdir(parents=True)
    return src


@contextlib.contextmanager
def _importable(*src_dirs: Path) -> Iterator[None]:
    """Make each fixture `<package>/src` importable for the length of a check,
    then drop the paths and every module imported through them."""
    roots = [str(src_dir.parent) for src_dir in src_dirs]
    names = {_import_name(src_dir.parents[1].name) for src_dir in src_dirs}
    sys.path[:0] = roots
    importlib.invalidate_caches()
    try:
        yield
    finally:
        for root in roots:
            sys.path.remove(root)
        for loaded in [m for m in sys.modules if m.split(".")[0] in names]:
            del sys.modules[loaded]


def _executed(
    module_package: str,
    *,
    classifier: bool = False,
    call_site: str = _FIXTURE_CALL_SITE,
) -> ExecutedFieldErrorPathFormatter:
    module = _import_name(module_package)
    return ExecutedFieldErrorPathFormatter(
        module=f"{module}.field_error_path",
        function="format_field_error_path",
        call_site=call_site,
        located_classifier=(
            ExecutedLocatedClassifier(f"{module}.request_validation", "classify_request_validation")
            if classifier
            else None
        ),
    )


def _executed_fixture(
    tmp_root: Path,
    package: str,
    *,
    formatter_source: str = _CANONICAL_FORMATTER_SOURCE,
    classifier_location_expr: str | None = None,
    call_source: str | None = _FIXTURE_CALL_SOURCE,
) -> Path:
    src = _fixture_src(tmp_root, package)
    (src / "field_error_path.py").write_text(formatter_source, encoding="utf-8")
    if classifier_location_expr is not None:
        (src / "request_validation.py").write_text(
            _FIXTURE_CLASSIFIER_SOURCE.format(location_expr=classifier_location_expr), encoding="utf-8"
        )
    if call_source is not None:
        (src / "handler.py.j2").write_text(call_source, encoding="utf-8")
    return src


def _template_fixture(tmp_root: Path, package: str, source: str | None) -> Path:
    src = _fixture_src(tmp_root, package)
    if source is not None:
        (src / "templates").mkdir()
        (src / _FIXTURE_TEMPLATE).write_text(source, encoding="utf-8")
    return src


def _self_test_executed(tmp_root: Path) -> bool:
    ok = True

    good = _executed_fixture(tmp_root, "fx-exec-good", classifier_location_expr="loc[0]")
    with _importable(good):
        census = census_language(_FIXTURE_LANGUAGE, (good,), _executed("fx-exec-good", classifier=True))
    ok &= _assert(
        len(census.sites) == 1
        and census.sites[0].spelled_path == _CANONICAL_PATH
        and not census.defects,
        f"a correct formatter, a correct classifier and a call site pass with the canonical path (got {census})",
    )

    bad = _executed_fixture(tmp_root, "fx-exec-bad", formatter_source=_DIVERGENT_FORMATTER_SOURCE)
    with _importable(bad):
        census = census_language(_FIXTURE_LANGUAGE, (bad,), _executed("fx-exec-bad"))
    ok &= _assert(
        len(census.sites) == 1 and census.sites[0].spelled_path != _CANONICAL_PATH,
        f"a divergent formatter's real execution surfaces its actual wrong output (got {census})",
    )

    misplacing = _executed_fixture(tmp_root, "fx-exec-misplaced", classifier_location_expr="'body'")
    with _importable(misplacing):
        census = census_language(
            _FIXTURE_LANGUAGE, (misplacing,), _executed("fx-exec-misplaced", classifier=True)
        )
    ok &= _assert(
        any("located entries" in defect for defect in census.defects),
        f"a classifier reporting every entry at the body location is a defect (got {census})",
    )

    uncalled = _executed_fixture(tmp_root, "fx-exec-uncalled", call_source=None)
    with _importable(uncalled):
        census = census_language(_FIXTURE_LANGUAGE, (uncalled,), _executed("fx-exec-uncalled"))
    ok &= _assert(
        len(census.defects) == 1 and "not on the emission path" in census.defects[0],
        f"a realization with no call site is a defect (got {census})",
    )

    own_file_only = _executed_fixture(
        tmp_root,
        "fx-exec-self-call",
        formatter_source=_CANONICAL_FORMATTER_SOURCE + "\n# render_path(loc)\n",
        call_source=None,
    )
    with _importable(own_file_only):
        census = census_language(_FIXTURE_LANGUAGE, (own_file_only,), _executed("fx-exec-self-call"))
    ok &= _assert(
        any("not on the emission path" in defect for defect in census.defects),
        "a call site spelled only inside the realization's own file does not count as a call",
    )

    elsewhere = _executed_fixture(tmp_root, "fx-exec-elsewhere")
    inside = _executed_fixture(tmp_root, "fx-exec-inside")
    with _importable(elsewhere, inside):
        census = census_language(_FIXTURE_LANGUAGE, (inside,), _executed("fx-exec-elsewhere"))
    ok &= _assert(
        not census.sites and any("outside this language's own src dirs" in d for d in census.defects),
        f"a formatter module outside the language's src dirs is a violation, never executed (got {census})",
    )

    absent = _executed_fixture(tmp_root, "fx-exec-absent")
    with _importable(absent):
        census = census_language(
            _FIXTURE_LANGUAGE,
            (absent,),
            ExecutedFieldErrorPathFormatter(
                module="fx_exec_absent.field_error_path",
                function="no_such_function",
                call_site=_FIXTURE_CALL_SITE,
            ),
        )
    ok &= _assert(
        any("does not exist" in defect for defect in census.defects),
        f"a declared function the module lacks is a defect (got {census})",
    )
    return ok


def _self_test_template(tmp_root: Path) -> bool:
    ok = True

    good = _template_fixture(tmp_root, "fx-tpl-good", _FIXTURE_BUILDER_SOURCE)
    census = census_language(_FIXTURE_LANGUAGE, (good,), _FIXTURE_TEMPLATE_DECLARATION)
    ok &= _assert(
        len(census.sites) == 1 and census.sites[0].spelled_path == _CANONICAL_PATH and not census.defects,
        f"a correct template builder with a call site censuses as canonical (got {census})",
    )

    no_bracket = _template_fixture(tmp_root, "fx-tpl-no-bracket", _FIXTURE_BUILDER_NO_BRACKET_SOURCE)
    census = census_language(_FIXTURE_LANGUAGE, (no_bracket,), _FIXTURE_TEMPLATE_DECLARATION)
    ok &= _assert(
        len(census.sites) == 1
        and census.sites[0].spelled_path != _CANONICAL_PATH
        and repr(_FIXTURE_TEMPLATE_DECLARATION.constructions[0]) in census.sites[0].spelled_path,
        f"a builder missing the `[n]`-index construction is divergent and names the missing regex (got {census})",
    )

    no_anchor = _template_fixture(tmp_root, "fx-tpl-no-anchor", "const x = 1;\n")
    census = census_language(_FIXTURE_LANGUAGE, (no_anchor,), _FIXTURE_TEMPLATE_DECLARATION)
    ok &= _assert(
        not census.sites and any("anchor" in defect for defect in census.defects),
        f"a template without the declared builder anchor is a defect (got {census})",
    )

    missing = _template_fixture(tmp_root, "fx-tpl-missing", None)
    census = census_language(_FIXTURE_LANGUAGE, (missing,), _FIXTURE_TEMPLATE_DECLARATION)
    ok &= _assert(
        not census.sites and any("exists under none" in defect for defect in census.defects),
        f"a declared template that exists nowhere is a defect (got {census})",
    )

    twin_a = _template_fixture(tmp_root, "fx-tpl-twin-a", _FIXTURE_BUILDER_SOURCE)
    twin_b = _template_fixture(tmp_root, "fx-tpl-twin-b", _FIXTURE_BUILDER_SOURCE)
    census = census_language(_FIXTURE_LANGUAGE, (twin_a, twin_b), _FIXTURE_TEMPLATE_DECLARATION)
    ok &= _assert(
        not census.sites and any("exists in 2" in defect for defect in census.defects),
        f"a template path present in two of the language's packages is refused (got {census})",
    )

    uncalled = _template_fixture(
        tmp_root, "fx-tpl-uncalled", _FIXTURE_BUILDER_SOURCE.rsplit("const path", 1)[0]
    )
    census = census_language(_FIXTURE_LANGUAGE, (uncalled,), _FIXTURE_TEMPLATE_DECLARATION)
    ok &= _assert(
        any("not on the emission path" in defect for defect in census.defects),
        f"a builder nothing calls is a defect (got {census})",
    )

    for bad_template in ("../escape.j2", "/abs/path.j2", "C:/drive/path.j2", "a\\b.j2", ""):
        ok &= _assert(
            _raises_value_error(
                lambda template=bad_template: TemplateFieldErrorPathConstruction(
                    template=template,
                    anchor="a",
                    constructions=("b",),
                    call_site="c",
                )
            ),
            f"a template path {bad_template!r} is refused at declaration construction",
        )
    return ok


def _self_test_language_core(tmp_root: Path) -> bool:
    """A fixture language split into a backend and a core: a realization that
    lives only in the core is censused for the language and recorded against
    the core package; a backend-only census (the pre-split blindness) does not
    find it."""
    ok = True

    backend = _fixture_src(tmp_root, "datrix-codegen-splitlang")
    core = _executed_fixture(tmp_root, "datrix-codegen-splitlang-core")
    (backend / "plugin.py").write_text("NAME = 'splitlang'\n", encoding="utf-8")
    declaration = _executed("datrix-codegen-splitlang-core")
    with _importable(backend, core):
        split = census_language(_FIXTURE_LANGUAGE, (backend, core), declaration)
        backend_only = census_language(_FIXTURE_LANGUAGE, (backend,), declaration)
    found = [(site.package, site.spelled_path) for site in split.sites]
    ok &= _assert(
        found == [("datrix-codegen-splitlang-core", _CANONICAL_PATH)]
        and not split.defects
        and not backend_only.sites,
        f"an executed realization planted in the core is found and recorded against it (got {found}); "
        f"a backend-only census does not find it",
    )

    template_core = _template_fixture(tmp_root, "datrix-codegen-tplsplit-core", _FIXTURE_BUILDER_SOURCE)
    template_backend = _template_fixture(tmp_root, "datrix-codegen-tplsplit", None)
    split = census_language(_FIXTURE_LANGUAGE, (template_backend, template_core), _FIXTURE_TEMPLATE_DECLARATION)
    found = [(site.package, site.spelled_path) for site in split.sites]
    ok &= _assert(
        found == [("datrix-codegen-tplsplit-core", _CANONICAL_PATH)] and not split.defects,
        f"a template realization planted in the core is found and recorded against it (got {found})",
    )
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
    censuses = scan_all_registered_languages()
    realizing = sorted(
        language
        for language, census in censuses.items()
        if census is not None
        and any(site.spelled_path == _CANONICAL_PATH for site in census.sites)
    )
    return _assert(
        len(realizing) >= 1,
        f"live census finds at least one language realizing the rule (found: {realizing})",
    )


def _self_test_names_no_target() -> bool:
    """This gate enumerates languages from registration and must name none."""
    failures = self_test_gate_names_no_target(__file__)
    for line in failures:
        print(f"  FAIL: {line}")
    return _assert(not failures, "this gate names no registered target (imports and name literals)")


def self_test() -> bool:
    """Non-vacuity self-test: this module names no registered target, a fixture
    language per technique (good and bad), a module outside the language's src
    dirs, an uncalled realization, a template path that escapes its package, a
    language declaring nothing, a realization
    planted in a language core, fewer than two registered languages, and a live
    census that finds at least one language realizing the rule (a scan that sees
    nothing is broken, not clean)."""
    print("Non-vacuity self-test:")
    ok = _self_test_names_no_target()
    tmp_root = Path(tempfile.mkdtemp(prefix="field-error-path-gate-"))
    try:
        ok &= _self_test_executed(tmp_root)
        ok &= _self_test_template(tmp_root)
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
