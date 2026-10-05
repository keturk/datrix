#!/usr/bin/env python3
"""Cross-language route wire-contract parity gate.

Two languages must answer the same route identically on the wire. This gate generates
each example project once per registered ``datrix.languages`` plugin, reads every API
route's wire contract out of the generated source through that language's own
conformance probe (``LanguageConformanceProbes.route_wire_contracts``), and compares the
contracts language against language, route by route:

* the route SET -- a (verb, path) one language registers and another does not;
* the success STATUS the framework answers when the handler returns normally;
* the success body's ENVELOPE (none / object / list / page / binary);
* the success body's MEDIA TYPE.

It is a static gate: no backend is booted, no request is made, no toolchain runs, so it
needs nothing beyond the framework itself. What it cannot see (a field's value, a runtime
projection) is out of its reach by construction; what it sees -- the verb, path, status,
envelope and media type each language's source commits to -- is the whole of what two
languages can disagree about without either being run.

A mismatch names the example, the route and the per-language values -- declared
coordinates only. It never names a generated file or echoes source text, so a report, log
line or results file can never carry a secret that happened to sit in a generated file.

Targets are enumerated from the ``datrix.languages`` entry-point group at run time and
read through each language's own probe; this file names no language, imports no target
package and carries no per-target table. A language with no probe, a probe that finds no
route, and fewer than two registered languages each fail loudly rather than pass
vacuously. A language that cannot realize a route declares it as a counted
``capability_gaps`` row on its own declaration, never as an exemption here.

Repo-level validation script (per the datrix showcase boundary -- no pytest suite lives in
datrix).
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

_LIBRARY_DIR = Path(__file__).resolve().parent.parent
if _LIBRARY_DIR.exists() and str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from shared.generated_example import generate_example  # noqa: E402
from shared.registered_targets import (  # noqa: E402
    registered_language_names,
    self_test_gate_names_no_target,
)

from datrix_codegen_kernel.parity.conformance_probes import (  # noqa: E402
    DocumentationSurfaces,
    EnumClassifierRender,
    LanguageConformanceProbes,
    ResponseBodyWireField,
    RouteWireContract,
    conformance_probes_of_language_plugin,
    language_conformance_probes,
)
from datrix_common.errors.plugin import PluginValidationError  # noqa: E402

logger = logging.getLogger(__name__)

_HERE = Path(__file__).resolve()
#: This file lives at <datrix>/scripts/library/test/route_wire_contract_parity.py --
#: parents[3] is <datrix>.
DATRIX_DIR: Path = _HERE.parents[3]

#: The examples every language is generated for: a resource CRUD API, and the CQRS example,
#: whose routes add commands, queries and custom verbs.
EXAMPLE_SOURCES: Final[tuple[Path, ...]] = (
    DATRIX_DIR / "examples" / "02-features" / "01-core-data-modeling" / "rest-api" / "system.dtrx",
    DATRIX_DIR / "examples" / "02-features" / "03-infrastructure-blocks" / "cqrs" / "system.dtrx",
)

#: Generation scratch space, outside every package repository and cleaned per run.
_GATE_OUTPUT_ROOT: Path = DATRIX_DIR.parent / ".tmp" / "route-wire-contract-gate"

#: A cross-language comparison over fewer than two languages is vacuous.
_MIN_LANGUAGES_FOR_COMPARISON: Final[int] = 2

#: Exit codes: 1 = a real divergence, 2 = nothing was (or could be) compared.
_DIVERGENCE_EXIT_CODE: Final[int] = 1
_CANNOT_COMPARE_EXIT_CODE: Final[int] = 2

MISMATCH_MISSING_ROUTE: Final[str] = "route-set"
MISMATCH_DUPLICATE_ROUTE: Final[str] = "duplicate-route"
MISMATCH_STATUS: Final[str] = "status"
MISMATCH_BODY_KIND: Final[str] = "body-envelope"
MISMATCH_MEDIA_TYPE: Final[str] = "media-type"

#: Synthetic identifiers used only by the self-test: not registered languages, so the
#: self-test proves the comparator's discriminating power without real generation.
_SELF_TEST_LANGUAGES: Final[tuple[str, str]] = ("self_test_lang_a", "self_test_lang_b")
_SELF_TEST_EXAMPLE: Final[str] = "self_test_example"
#: A string planted in a fixture contract's file path; the report must never carry it.
_SELF_TEST_CANARY: Final[str] = "CANARY-7f3a91-never-reported"


@dataclass(frozen=True)
class RouteMismatch:
    """One disagreement between languages over one route.

    Attributes:
        example: The example's directory name.
        verb: The route's lower-case HTTP verb.
        path: The route's normalized full path.
        kind: One of the ``MISMATCH_*`` constants.
        detail: ``language=value`` pairs (or the languages lacking the route), declared coordinates only.
    """

    example: str
    verb: str
    path: str
    kind: str
    detail: str

    def describe(self) -> str:
        """The one report line for this mismatch."""
        return f"example {self.example!r}: {self.verb.upper()} {self.path} -- {self.kind}: {self.detail}"


def configure_logging(debug: bool = False) -> None:
    """Configure logging output."""
    logging.basicConfig(level=logging.DEBUG if debug else logging.INFO, format="%(levelname)s: %(message)s")


def _by_key(
    example: str, language: str, contracts: Sequence[RouteWireContract], mismatches: list[RouteMismatch]
) -> dict[tuple[str, str], RouteWireContract]:
    """Index one language's contracts by route; a route registered twice is itself a mismatch."""
    indexed: dict[tuple[str, str], RouteWireContract] = {}
    for contract in contracts:
        if contract.key in indexed:
            mismatches.append(
                RouteMismatch(
                    example, contract.method, contract.path, MISMATCH_DUPLICATE_ROUTE, f"{language} registers it more than once"
                )
            )
            continue
        indexed[contract.key] = contract
    return indexed


def _differing_values(
    present: Mapping[str, RouteWireContract], attribute: str
) -> dict[str, str] | None:
    """``{language: value}`` for *attribute* when the languages holding the route disagree, else ``None``."""
    values = {language: str(getattr(contract, attribute)) for language, contract in present.items()}
    return values if len(set(values.values())) > 1 else None


def compare_route_contracts(
    example: str, contracts_by_language: Mapping[str, Sequence[RouteWireContract]]
) -> list[RouteMismatch]:
    """Compare every language's route contracts for one example against every other's.

    Args:
        example: The example's name, for the report.
        contracts_by_language: Each language's probe result.

    Returns:
        Every mismatch, ordered by route then kind; empty when the languages agree on every route.
    """
    mismatches: list[RouteMismatch] = []
    indexed = {
        language: _by_key(example, language, contracts, mismatches)
        for language, contracts in sorted(contracts_by_language.items())
    }
    routes: dict[tuple[str, str], dict[str, RouteWireContract]] = defaultdict(dict)
    for language, by_key in indexed.items():
        for key, contract in by_key.items():
            routes[key][language] = contract
    for (verb, path), present in sorted(routes.items()):
        absent = sorted(set(indexed) - set(present))
        if absent:
            mismatches.append(
                RouteMismatch(example, verb, path, MISMATCH_MISSING_ROUTE, f"registered by {sorted(present)}, absent from {absent}")
            )
            continue
        for kind, attribute in (
            (MISMATCH_STATUS, "success_status"),
            (MISMATCH_BODY_KIND, "body_kind"),
            (MISMATCH_MEDIA_TYPE, "media_type"),
        ):
            differing = _differing_values(present, attribute)
            if differing is not None:
                detail = ", ".join(f"{language}={value!r}" for language, value in sorted(differing.items()))
                mismatches.append(RouteMismatch(example, verb, path, kind, detail))
    return mismatches


def read_language_routes(language: str, probes: LanguageConformanceProbes, generated_root: Path) -> list[RouteWireContract]:
    """Read *language*'s route contracts through *probes*; a probe that finds no route is a failure.

    Raises:
        ValueError: the probe returned no route -- a census that finds nothing proves nothing.
    """
    contracts = list(probes.route_wire_contracts(generated_root))
    if not contracts:
        raise ValueError(
            f"The route probe for language {language!r} found no route in its generated example; "
            f"a census that finds nothing proves nothing. Fix: make the language's "
            f"route_wire_contracts read the routes its generator emits."
        )
    return contracts


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------


class _FixtureProbes:
    """An in-process fixture language whose probe returns a fixed route list."""

    def __init__(self, contracts: Sequence[RouteWireContract]) -> None:
        self._contracts = tuple(contracts)

    def response_body_wire_fields(self, generated_root: Path) -> tuple[ResponseBodyWireField, ...]:
        return ()

    def route_wire_contracts(self, generated_root: Path) -> tuple[RouteWireContract, ...]:
        return self._contracts

    def documentation_surfaces(self, generated_root: Path, files: Sequence[Path]) -> DocumentationSurfaces:
        return DocumentationSurfaces(frozenset(), frozenset())

    def render_enum_classifier(self, enum: object, paths: object) -> EnumClassifierRender:
        return EnumClassifierRender(())


class _FixturePluginWithoutProbes:
    """A fixture language plugin with no ``conformance_probes`` member."""


def _fixture_contract(
    verb: str = "get",
    path: str = "/api/v1/books",
    status: int = 200,
    body_kind: str = "page",
    media_type: str = "application/json",
    file_name: str = "fixture.src",
) -> RouteWireContract:
    return RouteWireContract(
        method=verb,
        path=path,
        success_status=status,
        body_kind=body_kind,  # type: ignore[arg-type]  # a fixture kind the comparator treats as an opaque string
        media_type=media_type,
        file_path=Path(file_name),
    )


def _kinds(mismatches: Sequence[RouteMismatch]) -> list[str]:
    return [mismatch.kind for mismatch in mismatches]


def _run_comparator_self_test() -> list[str]:
    """Prove the comparator reports every kind of disagreement and nothing else."""
    problems: list[str] = []
    lang_a, lang_b = _SELF_TEST_LANGUAGES

    def compare(a: Sequence[RouteWireContract], b: Sequence[RouteWireContract]) -> list[RouteMismatch]:
        return compare_route_contracts(_SELF_TEST_EXAMPLE, {lang_a: a, lang_b: b})

    same = [_fixture_contract(), _fixture_contract("delete", "/api/v1/books/{id}", 204, "none", "")]
    if compare(same, list(same)):
        problems.append("self-test: two languages with identical contracts were reported as mismatched.")

    cases: tuple[tuple[str, RouteWireContract, str], ...] = (
        ("status", _fixture_contract(status=201), MISMATCH_STATUS),
        ("body envelope", _fixture_contract(body_kind="list"), MISMATCH_BODY_KIND),
        ("media type", _fixture_contract(media_type="text/plain"), MISMATCH_MEDIA_TYPE),
    )
    for label, divergent, expected_kind in cases:
        found = compare([_fixture_contract()], [divergent])
        if _kinds(found) != [expected_kind]:
            problems.append(f"self-test: a planted {label} divergence was reported as {_kinds(found)}, expected [{expected_kind!r}].")
        elif lang_a not in found[0].detail or lang_b not in found[0].detail:
            problems.append(f"self-test: the {label} mismatch did not name both languages ({found[0].detail!r}).")

    verb_split = compare([_fixture_contract("put", "/api/v1/books/{id}")], [_fixture_contract("patch", "/api/v1/books/{id}")])
    if sorted(_kinds(verb_split)) != [MISMATCH_MISSING_ROUTE, MISMATCH_MISSING_ROUTE]:
        problems.append(
            f"self-test: one language registering PUT and the other PATCH for a path must report both "
            f"as route-set mismatches (got {_kinds(verb_split)})."
        )

    duplicated = compare([_fixture_contract(), _fixture_contract()], [_fixture_contract()])
    if _kinds(duplicated) != [MISMATCH_DUPLICATE_ROUTE]:
        problems.append(f"self-test: a route registered twice by one language was reported as {_kinds(duplicated)}.")
    return problems


def _run_no_disclosure_self_test() -> list[str]:
    """Prove a report carries declared coordinates only: no file path, no source text."""
    lang_a, lang_b = _SELF_TEST_LANGUAGES
    canary_file = f"{_SELF_TEST_CANARY}/routes.src"
    mismatches = compare_route_contracts(
        _SELF_TEST_EXAMPLE,
        {
            lang_a: [_fixture_contract(status=200, file_name=canary_file)],
            lang_b: [_fixture_contract(status=201, file_name=canary_file), _fixture_contract("post", "/x", file_name=canary_file)],
        },
    )
    if not mismatches:
        return ["self-test: the no-disclosure fixture produced no mismatch to inspect."]
    report = "\n".join(mismatch.describe() for mismatch in mismatches)
    if _SELF_TEST_CANARY in report or "routes.src" in report:
        return ["self-test: a mismatch report named a generated file; a report may carry declared coordinates only."]
    return []


def _run_probe_dispatch_self_test() -> list[str]:
    """Drive the real per-language read with fixture probes: empty fails, a route list passes, no probe member is refused."""
    problems: list[str] = []
    lang = _SELF_TEST_LANGUAGES[0]
    try:
        read_language_routes(lang, _FixtureProbes([]), Path("."))
    except ValueError as exc:
        if lang not in str(exc) or "proves nothing" not in str(exc):
            problems.append(f"self-test: the empty-probe refusal did not name the language or the reason ({exc}).")
    else:
        problems.append("self-test: a probe returning no route passed -- a census that finds nothing proves nothing.")

    if read_language_routes(lang, _FixtureProbes([_fixture_contract()]), Path(".")) != [_fixture_contract()]:
        problems.append("self-test: a probe's routes were not returned unchanged by read_language_routes.")

    try:
        conformance_probes_of_language_plugin(lang, _FixturePluginWithoutProbes())
    except PluginValidationError as exc:
        if lang not in str(exc) or "declares no conformance probes" not in str(exc):
            problems.append(f"self-test: a plugin with no probe member failed without the accessor's message ({exc}).")
    else:
        problems.append("self-test: a plugin with no probe member was not refused.")
    return problems


def _run_insufficient_target_refusal_self_test() -> list[str]:
    """Prove the gate refuses to run under fewer than two languages, by driving the real function.

    The refusal is the function's first statement and returns before any generation, so the
    calls are side-effect free; a severed guard would fall through into a real single-language
    run and fail loudly instead of passing.
    """
    problems: list[str] = []
    for insufficient in ([], sorted(registered_language_names())[:1]):
        code = check_route_wire_contract_parity(insufficient)
        if code != _CANNOT_COMPARE_EXIT_CODE:
            problems.append(
                f"self-test: check_route_wire_contract_parity did not refuse a target set of "
                f"{len(insufficient)} ({insufficient!r}) -- returned {code}, expected {_CANNOT_COMPARE_EXIT_CODE}."
            )
    return problems


def run_self_test() -> list[str]:
    """Prove this gate names no target, detects every planted divergence, and refuses to pass vacuously.

    Returns:
        Failure descriptions -- empty means the comparator is sound.
    """
    problems = list(self_test_gate_names_no_target(__file__))
    if problems:
        return problems
    problems.extend(_run_comparator_self_test())
    problems.extend(_run_no_disclosure_self_test())
    problems.extend(_run_probe_dispatch_self_test())
    problems.extend(_run_insufficient_target_refusal_self_test())
    return problems


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def _routes_of_language(language: str, source: Path) -> list[RouteWireContract] | None:
    """Generate *source* for *language* and read its routes; ``None`` (after logging) when it cannot be read."""
    output_dir = generate_example(language, source, _GATE_OUTPUT_ROOT / source.parent.name / language)
    try:
        probes = language_conformance_probes(language)
        return read_language_routes(language, probes, output_dir)
    except (PluginValidationError, ValueError) as exc:
        logger.error("ROUTE WIRE-CONTRACT VIOLATION: example %r, language %r: %s", source.parent.name, language, exc)
        return None


def _check_example(source: Path, languages: Sequence[str]) -> bool:
    """Compare every language's routes for one example; True when they all agree."""
    example = source.parent.name
    contracts_by_language: dict[str, list[RouteWireContract]] = {}
    for language in languages:
        contracts = _routes_of_language(language, source)
        if contracts is None:
            return False
        contracts_by_language[language] = contracts
    mismatches = compare_route_contracts(example, contracts_by_language)
    for mismatch in mismatches:
        logger.error("ROUTE WIRE-CONTRACT VIOLATION: %s", mismatch.describe())
    logger.info(
        "Example %r: %s routes per language; %d mismatch(es).",
        example,
        {language: len(contracts) for language, contracts in contracts_by_language.items()},
        len(mismatches),
    )
    return not mismatches


def check_route_wire_contract_parity(languages: Sequence[str] | None = None) -> int:
    """Run the real gate over every registered language.

    Args:
        languages: ``None`` -- the production value -- resolves the installed
            ``datrix.languages`` entry points at run time. An explicit sequence exists so the
            self-test can drive THIS function's insufficient-target refusal with a real short
            list: the refusal is the first statement, so a short list returns before any
            generation, and a severed guard falls through into a real single-language run
            that fails loudly instead of passing.

    Returns:
        0 = every language agrees on every route, 1 = at least one divergence or unreadable
        language, 2 = fewer than two languages are registered.
    """
    resolved = sorted(registered_language_names() if languages is None else languages)
    if len(resolved) < _MIN_LANGUAGES_FOR_COMPARISON:
        logger.error(
            "Route wire-contract gate CANNOT RUN: only %d language(s) registered (%s) -- at least %d are required.",
            len(resolved),
            resolved,
            _MIN_LANGUAGES_FOR_COMPARISON,
        )
        return _CANNOT_COMPARE_EXIT_CODE
    ok = True
    for source in EXAMPLE_SOURCES:
        ok = _check_example(source, resolved) and ok
    if ok:
        logger.info("Route wire contracts agree across %d languages (%s).", len(resolved), resolved)
        return 0
    return _DIVERGENCE_EXIT_CODE


def main() -> int:
    """Entry point.

    Returns:
        0 = languages agree, 1 = a divergence was found, 2 = the self-test failed or fewer than
        two languages are registered.
    """
    parser = argparse.ArgumentParser(
        description="Prove every registered datrix.languages plugin answers the same route identically on the wire."
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run only the non-vacuity self-test and skip real generation",
    )
    args = parser.parse_args()

    configure_logging(debug=args.debug)
    problems = run_self_test()
    if problems:
        logger.error("Non-vacuity self-test FAILED:")
        for problem in problems:
            logger.error("  %s", problem)
        return _CANNOT_COMPARE_EXIT_CODE
    logger.info("Non-vacuity self-test passed.")
    if args.self_test:
        return 0
    return check_route_wire_contract_parity()


if __name__ == "__main__":
    sys.exit(main())
