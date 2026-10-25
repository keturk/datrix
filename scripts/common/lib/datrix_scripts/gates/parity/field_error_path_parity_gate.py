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
  emitted code the gate cannot execute. The gate generates the registered
  example for the language and reads the emitted files through the language's
  own conformance probes (`idiom_occurrences`, a parse-tree reading): the
  builder's anchor must be defined, every declared construction must occur
  inside each emitted definition, and the declared call must occur outside
  them. Jinja source is never read, and a string literal or comment neither
  hides nor fakes an occurrence; an emitted file that does not parse fails the
  run.

Both techniques prove the realization is called: a realization nothing calls is
not on the emission path.

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
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final

from datrix_codegen_kernel.parity.conformance_probes import (
    IdiomOccurrence,
    UnparseableGeneratedFileError,
    language_conformance_probes,
)
from datrix_common.datrix_model.problem_types import (  # noqa: E402
    FIELD_ERROR_PATH_RULE,
    FieldErrorCode,
    FieldErrorLocation,
)
from datrix_common.errors.plugin import PluginNotFoundError, PluginValidationError
from datrix_common.plugin._capability_declarations import declaration_for_language  # noqa: E402
from datrix_common.plugin.code_idiom import (
    CallIdiom,
    CodeIdiom,
    FunctionIdiom,
    InterpolatedStringIdiom,
)
from datrix_common.plugin.language_capability import (  # noqa: E402
    ExecutedFieldErrorPathFormatter,
    ExecutedLocatedClassifier,
    FieldErrorPathRealization,
    TemplateFieldErrorPathConstruction,
)

from datrix_scripts.function_sources import iter_source_files  # noqa: E402
from datrix_scripts.gate_harness import report_condition  # noqa: E402
from datrix_scripts.gate_log import gate_child, run_as_gate  # noqa: E402
from datrix_scripts.gates.parity.gate_entry import ParityGate, gate_parser  # noqa: E402
from datrix_scripts.generated_example import generate_example
from datrix_scripts.paths import SHOWCASE_DIR, WORKSPACE_DIR
from datrix_scripts.registered_targets import (  # noqa: E402
    AXIS_LANGUAGES,
    WORKSPACE_ROOT,
    discover_target_package_src_dirs,
    registered_language_names,  # noqa: E402
    report_gate_names_no_target,
)
from datrix_scripts.test_projects import get_project_by_name
from datrix_scripts.venv import module_name  # noqa: E402

logger = logging.getLogger(__name__)

GATE: Final = "field-error-path-parity"
WRAPPER: Final = "field-error-path-parity-gate"
MODULE: Final = "datrix_scripts.gates.parity.field_error_path_parity_gate"

EXIT_OK: Final[int] = 0
EXIT_FAIL: Final[int] = 1
EXIT_USAGE: Final[int] = 2

_SOURCE_SUFFIXES: Final[frozenset[str]] = frozenset({".py", ".j2"})
_SKIP_DIR_NAMES: Final[frozenset[str]] = frozenset({"__pycache__", "node_modules"})
_MIN_LANGUAGES_FOR_COMPARISON: Final[int] = 2

#: The registered example (``scripts/config/test-projects.json``) generated for
#: every language whose realization lives in emitted code.
EXAMPLE_NAME: Final[str] = "cqrs"
_GATE_OUTPUT_ROOT: Final[Path] = WORKSPACE_DIR / ".tmp" / "field-error-path-parity"

#: A language's parse-tree reading of code idioms under a generated root.
IdiomReader = Callable[[Path, Sequence[CodeIdiom]], tuple[IdiomOccurrence, ...]]

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
    """Where the site lives: the package repo (a language's backend or one of its
    cores) for an executed formatter, the generated example for emitted code."""
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
    """Declared-but-unproven facts: a module outside the language's distribution,
    an absent function or emitted builder, an uncalled realization, a classifier
    that places an entry wrongly, a language with no probe reading."""


@dataclass(frozen=True, slots=True)
class LanguageVerdict:
    language: str
    realized: bool


# ---------------------------------------------------------------------------
# Source discovery (shared with problem_type_parity_gate / framework_header_parity_gate)
# ---------------------------------------------------------------------------


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
        for path in iter_source_files(src_dir, _SOURCE_SUFFIXES, _SKIP_DIR_NAMES):
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


def _within(occurrence: IdiomOccurrence, definition: IdiomOccurrence) -> bool:
    """Whether *occurrence* lies inside *definition*'s span in the same emitted file."""
    return (
        occurrence.relative_path == definition.relative_path
        and definition.line <= occurrence.line
        and occurrence.end_line <= definition.end_line
    )


def _template_site(
    language: str,
    realization: TemplateFieldErrorPathConstruction,
    definition: IdiomOccurrence,
    occurrences: Sequence[IdiomOccurrence],
) -> RealizationSite:
    """The site one emitted definition of the builder realizes: canonical when every
    declared construction occurs inside it, else annotated with what is missing."""
    missing = [
        construction
        for construction in realization.constructions
        if not any(o.idiom == construction and _within(o, definition) for o in occurrences)
    ]
    spelled = (
        _CANONICAL_PATH
        if not missing
        else f"{_CANONICAL_PATH} (missing the declared construction(s) {missing!r})"
    )
    return RealizationSite(
        language, f"generated {EXAMPLE_NAME}", definition.relative_path, definition.line, spelled
    )


def _census_template(
    language: str,
    generated_root: Path,
    realization: TemplateFieldErrorPathConstruction,
    read: IdiomReader,
) -> LanguageCensus:
    """Census the language's emitted files under *generated_root*, read through *read*.

    Raises:
        UnparseableGeneratedFileError: An emitted source file does not parse.
    """
    occurrences = read(
        generated_root, (realization.anchor, *realization.constructions, realization.call_site)
    )
    definitions = [o for o in occurrences if o.idiom == realization.anchor]
    if not definitions:
        return LanguageCensus(
            (),
            (f"declared anchor {realization.anchor!r} is defined in no file the language emitted for "
             f"the registered example {EXAMPLE_NAME!r}: the builder it names is not emitted. Fix: "
             f"emit the builder, or correct the declared anchor.",),
        )
    sites = tuple(_template_site(language, realization, d, occurrences) for d in definitions)
    called = any(
        o.idiom == realization.call_site and not any(_within(o, d) for d in definitions)
        for o in occurrences
    )
    if called:
        return LanguageCensus(sites, ())
    return LanguageCensus(
        sites,
        (f"declared call site {realization.call_site!r} occurs nowhere outside the builder's own "
         f"definition in the emitted files: the realization is defined but not on the emission "
         f"path. Fix: call it from the emitted code, or correct the declared call_site.",),
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
            f"supplies no conformance probes to read its generated tree with ({exc}). "
            f"Fix: declare complete conformance probes on the language plugin."
        ) from exc


def example_source() -> Path:
    """The ``system.dtrx`` of the registered example the emitted-code census generates.

    Raises:
        ValueError: The example is not in the example registry.
    """
    project = get_project_by_name(EXAMPLE_NAME)
    if project is None:
        raise ValueError(
            f"The example {EXAMPLE_NAME!r} is not in scripts/config/test-projects.json, so no "
            f"language's emitted code can be generated. Fix: restore its registry entry."
        )
    return SHOWCASE_DIR / str(project["path"])


def census_language(
    language: str,
    src_dirs: tuple[Path, ...],
    realization: FieldErrorPathRealization,
) -> LanguageCensus:
    """Census one language by the technique its declaration names: an executed
    formatter under every package implementing it (its backend and each language
    core), emitted code on the registered example generated for it. Dispatches on
    the declaration TYPE, a closed set in the shared declaration module.

    Raises:
        ValueError: The example is not registered.
        RuntimeError: Generating the example for the language failed.
        UnparseableGeneratedFileError: An emitted source file does not parse.
    """
    if isinstance(realization, ExecutedFieldErrorPathFormatter):
        return _census_executed(language, src_dirs, realization)
    if isinstance(realization, TemplateFieldErrorPathConstruction):
        try:
            read = idiom_reader(language)
        except ValueError as exc:
            return LanguageCensus((), (str(exc),))
        generated = generate_example(language, example_source(), _GATE_OUTPUT_ROOT / language)
        return _census_template(language, generated, realization, read)
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
    declares; a language that declares none is `None`, never skipped.

    Raises:
        ValueError: The example is not registered.
        RuntimeError: Generating the example for a language failed.
        UnparseableGeneratedFileError: An emitted source file does not parse.
    """
    language_names = registered_language_names()
    _require_min_languages(language_names)
    src_dirs = discover_target_package_src_dirs(AXIS_LANGUAGES, language_names, WORKSPACE_ROOT)
    shutil.rmtree(_GATE_OUTPUT_ROOT, ignore_errors=True)
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


def _planted(language: str, spelled_path: str) -> LanguageCensus:
    return LanguageCensus(
        (RealizationSite(language, f"datrix-codegen-{language}", "planted.j2", 1, spelled_path),), ()
    )


def _self_test_comparator() -> bool:
    ok = True
    canonical = _CANONICAL_PATH

    clean = {"alpha": _planted("alpha", canonical), "beta": _planted("beta", canonical)}
    problems, verdicts = evaluate(canonical, clean)
    ok &= report_condition(problems == [], "two languages spelling the canonical path report no problem")
    ok &= report_condition(verdicts["alpha"].realized, "the verdict records realization")

    divergent_path = "body." + canonical
    divergent = {"alpha": _planted("alpha", divergent_path), "beta": clean["beta"]}
    problems, _ = evaluate(canonical, divergent)
    ok &= report_condition(
        len(problems) == 1 and divergent_path in problems[0] and canonical in problems[0],
        "a divergent spelling is one violation naming the found and expected paths",
    )

    undeclared = {"alpha": None, "beta": clean["beta"]}
    problems, verdicts = evaluate(canonical, undeclared)
    ok &= report_condition(
        len(problems) == 1
        and problems[0].startswith("alpha:")
        and "declares no field-error-path realization" in problems[0],
        "a language declaring None is exactly one problem naming it, and evaluate takes no "
        "declaration input that could excuse it",
    )
    ok &= report_condition(
        not verdicts["alpha"].realized and verdicts["beta"].realized,
        "the verdict marks only the undeclaring language missing",
    )

    defective = {
        "alpha": LanguageCensus(clean["alpha"].sites, ("declared call site 'x' matches nothing",)),
        "beta": clean["beta"],
    }
    problems, verdicts = evaluate(canonical, defective)
    ok &= report_condition(
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

_FIXTURE_TEMPLATE_DECLARATION: Final[TemplateFieldErrorPathConstruction] = (
    TemplateFieldErrorPathConstruction(
        anchor=FunctionIdiom("buildPath"),
        constructions=(
            InterpolatedStringIdiom("{parentPath}[{property}]"),
            InterpolatedStringIdiom("{parentPath}.{property}"),
        ),
        call_site=CallIdiom("buildPath"),
    )
)
#: The emitted module the planted readings place the builder in: defined on
#: lines 1-4, both constructions inside it, called on line 6.
_FIXTURE_EMITTED_PATH: Final[str] = "svc/src/request-validation.src"
_FIXTURE_DEFINITION: Final[IdiomOccurrence] = IdiomOccurrence(
    _FIXTURE_TEMPLATE_DECLARATION.anchor, _FIXTURE_EMITTED_PATH, 1, 4, "buildPath(parentPath, property)"
)
_FIXTURE_BRACKET: Final[IdiomOccurrence] = IdiomOccurrence(
    _FIXTURE_TEMPLATE_DECLARATION.constructions[0], _FIXTURE_EMITTED_PATH, 2, 2, "{parentPath}[{property}]"
)
_FIXTURE_DOT: Final[IdiomOccurrence] = IdiomOccurrence(
    _FIXTURE_TEMPLATE_DECLARATION.constructions[1], _FIXTURE_EMITTED_PATH, 3, 3, "{parentPath}.{property}"
)
_FIXTURE_CALL: Final[IdiomOccurrence] = IdiomOccurrence(
    _FIXTURE_TEMPLATE_DECLARATION.call_site, _FIXTURE_EMITTED_PATH, 6, 6, "buildPath"
)


@dataclass
class _PlantedReader:
    """A reading that answers with planted occurrences and records what it was asked:
    what a language's probes would read off the parse trees of an emitted tree."""

    occurrences: tuple[IdiomOccurrence, ...]
    asked: list[CodeIdiom]

    def __call__(self, generated_root: Path, idioms: Sequence[CodeIdiom]) -> tuple[IdiomOccurrence, ...]:
        self.asked.extend(idioms)
        return tuple(o for o in self.occurrences if o.idiom in idioms)


def _planted_reader(*occurrences: IdiomOccurrence) -> _PlantedReader:
    return _PlantedReader(occurrences, [])


def _unparseable_reader(generated_root: Path, idioms: Sequence[CodeIdiom]) -> tuple[IdiomOccurrence, ...]:
    raise UnparseableGeneratedFileError(_FIXTURE_EMITTED_PATH, "unexpected token at 1:1")


def _fixture_src(tmp_root: Path, package: str) -> Path:
    """A fixture ``<package>/src/<import_name>`` tree, the shape every
    discovered src dir has."""
    src = tmp_root / package / "src" / module_name(package)
    src.mkdir(parents=True)
    return src


@contextlib.contextmanager
def _importable(*src_dirs: Path) -> Iterator[None]:
    """Make each fixture `<package>/src` importable for the length of a check,
    then drop the paths and every module imported through them."""
    roots = [str(src_dir.parent) for src_dir in src_dirs]
    names = {module_name(src_dir.parents[1].name) for src_dir in src_dirs}
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
    module = module_name(module_package)
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


def _self_test_executed(tmp_root: Path) -> bool:
    ok = True

    good = _executed_fixture(tmp_root, "fx-exec-good", classifier_location_expr="loc[0]")
    with _importable(good):
        census = census_language(_FIXTURE_LANGUAGE, (good,), _executed("fx-exec-good", classifier=True))
    ok &= report_condition(
        len(census.sites) == 1
        and census.sites[0].spelled_path == _CANONICAL_PATH
        and not census.defects,
        f"a correct formatter, a correct classifier and a call site pass with the canonical path (got {census})",
    )

    bad = _executed_fixture(tmp_root, "fx-exec-bad", formatter_source=_DIVERGENT_FORMATTER_SOURCE)
    with _importable(bad):
        census = census_language(_FIXTURE_LANGUAGE, (bad,), _executed("fx-exec-bad"))
    ok &= report_condition(
        len(census.sites) == 1 and census.sites[0].spelled_path != _CANONICAL_PATH,
        f"a divergent formatter's real execution surfaces its actual wrong output (got {census})",
    )

    misplacing = _executed_fixture(tmp_root, "fx-exec-misplaced", classifier_location_expr="'body'")
    with _importable(misplacing):
        census = census_language(
            _FIXTURE_LANGUAGE, (misplacing,), _executed("fx-exec-misplaced", classifier=True)
        )
    ok &= report_condition(
        any("located entries" in defect for defect in census.defects),
        f"a classifier reporting every entry at the body location is a defect (got {census})",
    )

    uncalled = _executed_fixture(tmp_root, "fx-exec-uncalled", call_source=None)
    with _importable(uncalled):
        census = census_language(_FIXTURE_LANGUAGE, (uncalled,), _executed("fx-exec-uncalled"))
    ok &= report_condition(
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
    ok &= report_condition(
        any("not on the emission path" in defect for defect in census.defects),
        "a call site spelled only inside the realization's own file does not count as a call",
    )

    elsewhere = _executed_fixture(tmp_root, "fx-exec-elsewhere")
    inside = _executed_fixture(tmp_root, "fx-exec-inside")
    with _importable(elsewhere, inside):
        census = census_language(_FIXTURE_LANGUAGE, (inside,), _executed("fx-exec-elsewhere"))
    ok &= report_condition(
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
    ok &= report_condition(
        any("does not exist" in defect for defect in census.defects),
        f"a declared function the module lacks is a defect (got {census})",
    )
    return ok


def _self_test_template() -> bool:
    ok = True
    declaration = _FIXTURE_TEMPLATE_DECLARATION
    root = _GATE_OUTPUT_ROOT / "self-test"

    good = _planted_reader(_FIXTURE_DEFINITION, _FIXTURE_BRACKET, _FIXTURE_DOT, _FIXTURE_CALL)
    census = _census_template(_FIXTURE_LANGUAGE, root, declaration, good)
    ok &= report_condition(
        len(census.sites) == 1
        and census.sites[0].spelled_path == _CANONICAL_PATH
        and census.sites[0].relative_path == _FIXTURE_EMITTED_PATH
        and not census.defects,
        f"an emitted builder holding every construction, called outside itself, censuses as canonical "
        f"(got {census})",
    )
    ok &= report_condition(
        good.asked == [declaration.anchor, *declaration.constructions, declaration.call_site],
        f"the census asks the language's reading for the anchor, every construction and the call "
        f"(asked {good.asked})",
    )

    no_bracket = _planted_reader(_FIXTURE_DEFINITION, _FIXTURE_DOT, _FIXTURE_CALL)
    census = _census_template(_FIXTURE_LANGUAGE, root, declaration, no_bracket)
    ok &= report_condition(
        len(census.sites) == 1
        and census.sites[0].spelled_path != _CANONICAL_PATH
        and repr(declaration.constructions[0]) in census.sites[0].spelled_path,
        f"a builder missing the `[n]`-index construction is divergent and names it (got {census})",
    )

    outside = replace(_FIXTURE_BRACKET, line=8, end_line=8)
    elsewhere = replace(_FIXTURE_BRACKET, relative_path="svc/src/other.src")
    census = _census_template(
        _FIXTURE_LANGUAGE,
        root,
        declaration,
        _planted_reader(_FIXTURE_DEFINITION, outside, elsewhere, _FIXTURE_DOT, _FIXTURE_CALL),
    )
    ok &= report_condition(
        len(census.sites) == 1 and census.sites[0].spelled_path != _CANONICAL_PATH,
        f"a construction outside the builder's span, or in another file, does not count (got {census})",
    )

    second = replace(_FIXTURE_DEFINITION, relative_path="svc2/src/request-validation.src")
    census = _census_template(
        _FIXTURE_LANGUAGE,
        root,
        declaration,
        _planted_reader(_FIXTURE_DEFINITION, second, _FIXTURE_BRACKET, _FIXTURE_DOT, _FIXTURE_CALL),
    )
    divergent = [site.relative_path for site in census.sites if site.spelled_path != _CANONICAL_PATH]
    ok &= report_condition(
        len(census.sites) == 2 and divergent == [second.relative_path],
        f"every emitted definition is held to the constructions; the one lacking them diverges "
        f"(got {census})",
    )

    no_anchor = _planted_reader(_FIXTURE_BRACKET, _FIXTURE_DOT, _FIXTURE_CALL)
    census = _census_template(_FIXTURE_LANGUAGE, root, declaration, no_anchor)
    ok &= report_condition(
        not census.sites and any("anchor" in defect for defect in census.defects),
        f"emitted code without the declared builder definition is a defect (got {census})",
    )

    uncalled = _planted_reader(_FIXTURE_DEFINITION, _FIXTURE_BRACKET, _FIXTURE_DOT)
    census = _census_template(_FIXTURE_LANGUAGE, root, declaration, uncalled)
    ok &= report_condition(
        any("not on the emission path" in defect for defect in census.defects),
        f"a builder nothing calls is a defect (got {census})",
    )

    self_call = replace(_FIXTURE_CALL, line=3, end_line=3)
    census = _census_template(
        _FIXTURE_LANGUAGE,
        root,
        declaration,
        _planted_reader(_FIXTURE_DEFINITION, _FIXTURE_BRACKET, _FIXTURE_DOT, self_call),
    )
    ok &= report_condition(
        any("not on the emission path" in defect for defect in census.defects),
        f"a call only inside the builder's own definition does not count as a call (got {census})",
    )

    try:
        _census_template(_FIXTURE_LANGUAGE, root, declaration, _unparseable_reader)
        refused = False
    except UnparseableGeneratedFileError:
        refused = True
    ok &= report_condition(
        refused, "an emitted file the language cannot parse fails the census, never reads as clean"
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
    ok &= report_condition(
        found == [("datrix-codegen-splitlang-core", _CANONICAL_PATH)]
        and not split.defects
        and not backend_only.sites,
        f"an executed realization planted in the core is found and recorded against it (got {found}); "
        f"a backend-only census does not find it",
    )
    return ok


def _self_test_min_languages_refusal() -> bool:
    """A single registered language is not a cross-language comparison --
    `_require_min_languages` must refuse it with `EXIT_USAGE`, the same
    refuse-under-two floor every other axis-scanning gate in this repo
    carries."""
    try:
        _require_min_languages(frozenset({"only-one"}))
        return report_condition(False, "a single-language set is refused")
    except SystemExit as exc:
        return report_condition(exc.code == EXIT_USAGE, "a single-language set is refused")


def _self_test_registered_readings() -> bool:
    """Every registered language whose realization lives in emitted code resolves its
    own parse-tree reading; one that cannot is reported by the census, never skipped."""
    emitted = sorted(
        language
        for language in registered_language_names()
        if isinstance(
            declaration_for_language(language).field_error_path_realization,
            TemplateFieldErrorPathConstruction,
        )
    )
    unread: list[str] = []
    for language in emitted:
        try:
            idiom_reader(language)
        except ValueError as exc:
            unread.append(f"{language}: {exc}")
    return report_condition(
        not unread,
        f"every registered language realizing the rule in emitted code resolves its probe reading "
        f"({len(emitted)} language(s); unread: {unread})",
    )


def self_test() -> bool:
    """Non-vacuity self-test: this module names no registered target, a fixture
    language per technique (good and bad), a module outside the language's src
    dirs, an uncalled realization (a call inside the builder's own definition is
    not a call), a construction outside the emitted builder, an emitted file that
    does not parse, a language declaring nothing, a realization planted in a
    language core, fewer than two registered languages, and every registered
    emitted-code language resolving its probe reading. The live census is itself a
    hard zero over every registered language, so a scan that sees nothing fails."""
    print("Non-vacuity self-test:")
    ok = report_gate_names_no_target(__file__)
    tmp_root = Path(tempfile.mkdtemp(prefix="field-error-path-gate-"))
    try:
        ok &= _self_test_executed(tmp_root)
        ok &= _self_test_language_core(tmp_root)
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    ok &= _self_test_template()
    ok &= _self_test_comparator()
    ok &= _self_test_min_languages_refusal()
    ok &= _self_test_registered_readings()
    return ok


def build_parser() -> argparse.ArgumentParser:
    """The options ``field-error-path-parity-gate.ps1`` passes: ``-Dbg`` and ``-SelfTest``."""
    return gate_parser(WRAPPER, __doc__.split("\n\n")[0])


def compare_censuses(args: argparse.Namespace) -> int:
    """The real comparison: every registered language's census against the canonical path."""
    del args  # The gate takes no option besides -Dbg and -SelfTest.
    try:
        censuses = scan_all_registered_languages()
    except (ValueError, RuntimeError) as exc:
        print(f"Error: the field-error-path census failed: {exc}", file=sys.stderr)
        return EXIT_USAGE
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


GATE_SPEC: Final = ParityGate(
    gate=GATE,
    wrapper=WRAPPER,
    module=MODULE,
    build_parser=build_parser,
    self_test=self_test,
    compare=compare_censuses,
    self_test_failed=EXIT_USAGE,
)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the gate: 0 clean, 1 violation(s), 2 usage or self-test failure."""
    return run_as_gate(GATE, MODULE, gate_child(build_parser, GATE_SPEC.run), argv)


if __name__ == "__main__":
    sys.exit(main())
