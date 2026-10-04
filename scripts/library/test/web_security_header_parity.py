"""Web security header parity gate -- every registered platform that hosts a
web client realizes the ONE declared security-header set from
`datrix_codegen_kernel.platform.web_security_headers`, with no declarable hole: a
generated static site is either fronted by the full header set its own
topology requires, or it is a defect, never a documented gap.

Every static-site hosting realization consumes
`datrix_codegen_kernel.platform.web_security_headers.build_web_security_headers`,
but none spells a header NAME literally in its own package source: each threads
the shared builder's `WebSecurityHeaderSet.as_header_dict()` straight into its
own rendering primitive (a Jinja loop, a CDK IR list, a JSON object), so a
census of `.py`/`.j2` source text -- the technique `framework_header_parity.py`
and `problem_type_parity.py` use for a WIRE NAME spelled directly in source --
finds nothing to compare. How a platform's rendered artifact is read therefore
belongs to the platform: each registered platform declares a
`PlatformConformanceProbes` (`PlatformPlugin.declared_conformance_probes()`,
`datrix_codegen_kernel.parity.conformance_probes`) whose
`realized_web_security_headers(header_set)` renders the platform's real artifact
for one shared fixture header set and parses the EMITTED artifact structurally.
This gate holds the comparison and the fixture and NEVER names a platform; its
self-test proves that first (`shared.registered_targets.target_references_in_module`).

Strict-Transport-Security is the one family whose PRESENCE is itself
topology-dependent -- `build_web_security_headers` omits it, correctly, on a
loopback profile (HSTS is meaningless over plain HTTP). This is not a
per-platform declared hole (the design states the header set is mandatory
everywhere a platform realizes `static_web_hosting`): it is read from the
platform's own `PlatformCapabilityDeclaration.static_web_hosting.origin`
(`"loopback_port"` vs `"domain"`) and used to compute that platform's own
topology-correct expected family set via the SAME shared builder, never a
hand-typed exemption. The census is keyed by registered platform NAME, so every
registered platform is proven individually, never folded with another that
shares a package. A platform whose static web hosting declares no origin is a
defect that fails the run, never a skip; a probe that returns no header fails.

Platform set from the installed `datrix.platforms` entry points at runtime; the
declared header set read from `datrix_codegen_kernel.platform.web_security_headers`
at runtime -- never a table in this script. Runs a built-in non-vacuity
self-test on every invocation. Repo-level validation script (per the datrix
showcase boundary -- no pytest suite lives in datrix).
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

_LIBRARY_DIR = Path(__file__).resolve().parent.parent
if _LIBRARY_DIR.exists() and str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from datrix_codegen_kernel.parity.conformance_probes import (  # noqa: E402
    PlatformConformanceProbes,
    conformance_probes_of_platform_class,
    platform_conformance_probes,
)
from datrix_codegen_kernel.platform.web_security_headers import (  # noqa: E402
    WebSecurityHeaderSet,
    build_web_security_headers,
)
from datrix_common.errors.plugin import PluginValidationError  # noqa: E402
from datrix_common.plugin.capability_resolution import declaration_for_provider  # noqa: E402
from shared.registered_targets import (  # noqa: E402
    registered_platform_names,
    self_test_gate_names_no_target,
)

if TYPE_CHECKING:
    from datrix_common.plugin.capability import PlatformCapabilityDeclaration

logger = logging.getLogger(__name__)

EXIT_OK: Final[int] = 0
EXIT_FAIL: Final[int] = 1
EXIT_USAGE: Final[int] = 2

_MIN_PLATFORMS_FOR_COMPARISON: Final[int] = 2

#: The static-hosting origin shape a loopback platform declares; every other
#: declared origin is a domain-fronted topology.
_LOOPBACK_ORIGIN: Final[str] = "loopback_port"

#: The exact CSP directive tokens a Content-Security-Policy value must never
#: contain (the shared builder's own contract -- see its module docstring),
#: spelled exactly as the Content-Security-Policy grammar itself spells them
#: (always lowercase, hyphenated) -- a case-sensitive substring search, never
#: case-folded, so a platform cannot dodge the check by re-casing the token.
_UNSAFE_CSP_TOKENS: Final[tuple[str, ...]] = ("unsafe-inline", "unsafe-eval")

#: One shared fixture header set every platform's artifact is rendered
#: against -- domain-neutral placeholders, never a real or customer origin.
#: `is_loopback` is the one input that varies, resolved per platform from its
#: own `static_web_hosting.origin` declaration.
_FIXTURE_API_ORIGIN: Final[str] = "https://api.fixture.example"
_FIXTURE_IDENTITY_AUTHORITY: Final[str] = "https://auth.fixture.example"

#: Names used only by the self-test's fixture probes -- deliberately not
#: registered platform names.
_SELF_TEST_PLATFORM: Final[str] = "self_test_platform"


# ---------------------------------------------------------------------------
# Declared header-family vocabulary
# ---------------------------------------------------------------------------


def _fixture_header_set(*, is_loopback: bool) -> WebSecurityHeaderSet:
    """The one shared fixture's `WebSecurityHeaderSet`, computed by the SAME
    builder every platform calls -- `is_loopback` is the only axis that
    varies per platform topology."""
    return build_web_security_headers(
        api_origin=_FIXTURE_API_ORIGIN,
        identity_authority=_FIXTURE_IDENTITY_AUTHORITY,
        tile_origin=None,
        used_builtin_rows=frozenset(),
        is_loopback=is_loopback,
    )


def _topology_families(*, is_loopback: bool) -> frozenset[str]:
    """The header-name vocabulary a platform of this topology is expected to
    realize -- read from `as_header_dict()`'s own keys, never a literal
    tuple, so a loopback profile's correct HSTS omission falls out of the
    shared builder itself rather than a per-platform exemption."""
    return frozenset(_fixture_header_set(is_loopback=is_loopback).as_header_dict())


def declared_header_families() -> frozenset[str]:
    """The header-family vocabulary read from
    `datrix_codegen_kernel.platform.web_security_headers` -- never a literal tuple
    in this script. The full (non-loopback) set is the union vocabulary the
    report and the "realized by no platform" dead-entry check compare
    against; a loopback platform's own expected set
    (`_topology_families(is_loopback=True)`) is a subset of it."""
    return _topology_families(is_loopback=False)


def _csp_header_name(sample: WebSecurityHeaderSet) -> str:
    """The wire name `as_header_dict()` uses for the CSP value -- found by
    matching the dict entry whose value IS `sample.content_security_policy`,
    never a re-typed `"Content-Security-Policy"` literal."""
    for header_name, value in sample.as_header_dict().items():
        if value == sample.content_security_policy:
            return header_name
    raise ValueError(
        "WebSecurityHeaderSet.as_header_dict() carries no entry equal to "
        "its own content_security_policy field -- the shared builder's "
        "shape changed; update _csp_header_name to match."
    )


# ---------------------------------------------------------------------------
# Census
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class HeaderSpelling:
    """One realized header found in a platform's rendered artifact: its NAME
    and the VALUE the artifact actually emits for it (the CSP value is also
    captured separately for the unsafe-token check -- see `CspSample`)."""

    platform: str
    relative_path: str
    line: int
    header_name: str
    value: str


@dataclass(frozen=True, slots=True)
class CspSample:
    """One emitted Content-Security-Policy VALUE found in a platform's
    rendered artifact, censused for the `unsafe-inline`/`unsafe-eval`
    negative check."""

    platform: str
    relative_path: str
    line: int
    directive_text: str


@dataclass(frozen=True, slots=True)
class PlatformCensus:
    platform: str
    header_spellings: tuple[HeaderSpelling, ...]
    csp_samples: tuple[CspSample, ...]
    expected_headers: Mapping[str, str]
    """This platform's own topology-correct declared header set -- the
    `{name: value}` the shared builder computes for the fixture at this
    platform's declared `static_web_hosting.origin` -- NOT the full declared
    vocabulary; a loopback platform's set correctly excludes
    Strict-Transport-Security. Both the expected family NAMES and the
    expected VALUES are read from this one mapping."""

    @property
    def expected_families(self) -> frozenset[str]:
        return frozenset(self.expected_headers)


@dataclass(frozen=True, slots=True)
class PlatformVerdict:
    platform: str
    realized: frozenset[str]
    expected_families: frozenset[str]


def realized_families(census: PlatformCensus) -> frozenset[str]:
    return frozenset(spelling.header_name for spelling in census.header_spellings)


# ---------------------------------------------------------------------------
# Comparator (pure -- exercised directly by the self-test with planted
# censuses, never only through the live scan)
# ---------------------------------------------------------------------------


def evaluate(
    families: frozenset[str],
    censuses: Mapping[str, PlatformCensus],
) -> tuple[list[str], dict[str, PlatformVerdict]]:
    """Every violation across every registered platform, plus the per-platform
    verdicts the report renders.

    A family in `census.expected_families` that the platform does not
    realize is a violation naming the platform and family -- no declared-hole
    escape (see module docstring). A realized family outside the declared
    vocabulary entirely is also a violation (a platform emitting a header the
    shared builder never produced). A realized family whose emitted VALUE
    differs from the value the shared builder computed for the platform's
    topology is a violation naming the header, the emitted value and the
    declared one -- one declared set means one set of values, not merely one
    set of names (a weakened `Referrer-Policy` or a CSP missing a directive
    carries a correct name). Any `CspSample` whose `directive_text` contains
    `unsafe-inline` or `unsafe-eval` is a violation naming the platform and
    the offending sample, regardless of which families are otherwise
    realized or what their values are -- the checks are independent.
    """
    problems: list[str] = []
    verdicts: dict[str, PlatformVerdict] = {}
    for platform in sorted(censuses):
        census = censuses[platform]
        realized = realized_families(census)
        problems.extend(_family_problems(platform, census, realized, families))
        problems.extend(_value_problems(platform, census))
        problems.extend(_csp_problems(platform, census))
        verdicts[platform] = PlatformVerdict(platform, realized, census.expected_families)
    realized_anywhere: frozenset[str] = (
        frozenset().union(*(verdict.realized for verdict in verdicts.values())) if verdicts else frozenset()
    )
    for family in sorted(families - realized_anywhere):
        problems.append(
            f"registry: family {family!r} is realized by no registered platform. A "
            f"header nobody emits is a dead contract. Fix: realize it on at least "
            f"one platform, or remove it from the shared builder."
        )
    return problems, verdicts


def _family_problems(
    platform: str,
    census: PlatformCensus,
    realized: frozenset[str],
    families: frozenset[str],
) -> list[str]:
    """Violations of the header NAME set: an emitted family outside the declared
    vocabulary, and a declared family the platform does not realize."""
    problems: list[str] = []
    for family in sorted(realized - families):
        problems.append(
            f"{platform}: emits header {family!r}, which is "
            f"not part of the one declared web-security header set "
            f"(datrix_codegen_kernel.platform.web_security_headers). Fix: remove the "
            f"hand-written header, or thread it through build_web_security_headers "
            f"so every platform stays on the one declared set."
        )
    for family in sorted(census.expected_families - realized):
        problems.append(
            f"{platform}: does not realize declared header "
            f"family {family!r} for its own topology. Fix: thread "
            f"build_web_security_headers's output for this header into the "
            f"platform's rendering path -- there is no declared-hole escape for "
            f"this gate."
        )
    return problems


def _value_problems(platform: str, census: PlatformCensus) -> list[str]:
    """Violations of the header VALUES: an emitted value that differs from the one
    the shared builder computed for the platform's topology."""
    problems: list[str] = []
    for spelling in census.header_spellings:
        expected_value = census.expected_headers.get(spelling.header_name)
        if expected_value is None or spelling.value == expected_value:
            continue
        problems.append(
            f"{platform}: {spelling.relative_path}:{spelling.line}: "
            f"emits {spelling.header_name!r} as {spelling.value!r}, but the one declared "
            f"set computes {expected_value!r} for this platform's topology. Fix: emit "
            f"build_web_security_headers's value unchanged -- a platform never rewrites "
            f"a declared header value."
        )
    return problems


def _csp_problems(platform: str, census: PlatformCensus) -> list[str]:
    """Violations of the CSP negative check: every unsafe token in an emitted CSP."""
    return [
        f"{platform}: {sample.relative_path}:"
        f"{sample.line}: Content-Security-Policy contains {token!r}, "
        f"forbidden regardless of family completeness. Fix: remove "
        f"the unsafe directive token from the CSP the platform emits."
        for sample in census.csp_samples
        for token in _UNSAFE_CSP_TOKENS
        if token in sample.directive_text
    ]


def render_report(families: frozenset[str], verdicts: Mapping[str, PlatformVerdict]) -> str:
    platforms = sorted(verdicts)
    width = max([len("family"), *(len(family) for family in families)] or [len("family")])
    lines = ["  " + "family".ljust(width) + "  " + "  ".join(p.ljust(14) for p in platforms)]
    for family in sorted(families):
        cells: list[str] = []
        for platform in platforms:
            verdict = verdicts[platform]
            if family in verdict.realized:
                cells.append("realized".ljust(14))
            elif family not in verdict.expected_families:
                cells.append("n/a (topology)".ljust(14))
            else:
                cells.append("MISSING".ljust(14))
        lines.append("  " + family.ljust(width) + "  " + "  ".join(cells))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Platform axis: which registered platforms host a static site, and in what
# origin shape
# ---------------------------------------------------------------------------


def _declared_hosting_origin(declaration: PlatformCapabilityDeclaration) -> str | None:
    """The origin a platform's static web hosting declares, or `None` when it
    serves no static site."""
    hosting = declaration.static_web_hosting
    return None if hosting is None else hosting.origin


def _require_origin(platform: str, declaration: PlatformCapabilityDeclaration) -> str:
    """The static-hosting origin of *platform*, which declares static web hosting.

    Raises:
        ValueError: The platform declares static web hosting with no origin.
    """
    origin = _declared_hosting_origin(declaration)
    if origin is None:
        raise ValueError(
            f"{platform}: declares static_web_hosting with no origin. Expected a "
            f"topology the header set can be computed for ('{_LOOPBACK_ORIGIN}' or a "
            f"domain origin). Fix: declare the origin on that platform's capability "
            f"declaration."
        )
    return origin


# ---------------------------------------------------------------------------
# Live scan
# ---------------------------------------------------------------------------


def _require_min_platforms(platform_names: frozenset[str]) -> None:
    if len(platform_names) < _MIN_PLATFORMS_FOR_COMPARISON:
        print(
            f"Error: {len(platform_names)} registered platform(s) "
            f"({', '.join(sorted(platform_names)) or 'none'}); a cross-platform parity "
            f"gate needs at least {_MIN_PLATFORMS_FOR_COMPARISON}. Install the "
            f"datrix-codegen-<platform> packages.",
            file=sys.stderr,
        )
        raise SystemExit(EXIT_USAGE)


def census_platform(platform: str, probes: PlatformConformanceProbes, *, is_loopback: bool) -> PlatformCensus:
    """Census one platform: render its artifact through *probes* for the shared fixture.

    Raises:
        ValueError: The probe returned no header (a probe that finds nothing
            proves nothing).
    """
    header_set = _fixture_header_set(is_loopback=is_loopback)
    effective_headers = dict(probes.realized_web_security_headers(header_set))
    if not effective_headers:
        raise ValueError(
            f"probe for {platform!r} emitted no header for the fixture header set; a "
            f"census that finds nothing proves nothing. Expected every header of the "
            f"declared set. Fix: make the platform's realized_web_security_headers read "
            f"the headers its rendered artifact carries."
        )
    artifact_label = f"{platform} (rendered fixture artifact)"
    header_spellings = tuple(
        HeaderSpelling(platform, artifact_label, 0, header_name, effective_headers[header_name])
        for header_name in sorted(effective_headers)
    )
    csp_value = effective_headers.get(_csp_header_name(header_set))
    csp_samples = (CspSample(platform, artifact_label, 0, csp_value),) if csp_value is not None else ()
    return PlatformCensus(platform, header_spellings, csp_samples, header_set.as_header_dict())


def scan_all_registered_platforms() -> dict[str, PlatformCensus]:
    """Census every registered `datrix.platforms` name that realizes static web hosting.

    Each name is read through its own conformance probes, driving the platform's
    real generation composition for the shared fixture. The census is keyed by
    registered name, so two names sharing one package are each proven.

    Returns:
        `{registered name: PlatformCensus}`.

    Raises:
        PluginValidationError: A realizing platform declares no (or incomplete)
            conformance probes.
        ValueError: A platform declares hosting with no origin, or its probe
            returned no header.
    """
    platform_names = registered_platform_names()
    _require_min_platforms(platform_names)
    censuses: dict[str, PlatformCensus] = {}
    for name in sorted(platform_names):
        declaration = declaration_for_provider(name)
        if declaration.static_web_hosting is None:
            logger.info("platform %s declares no static web hosting; not censused", name)
            continue
        origin = _require_origin(name, declaration)
        censuses[name] = census_platform(
            name, platform_conformance_probes(name), is_loopback=origin == _LOOPBACK_ORIGIN
        )
        logger.debug(
            "census platform=%s origin=%s realized=%d", name, origin, len(censuses[name].header_spellings)
        )
    if len(censuses) < _MIN_PLATFORMS_FOR_COMPARISON:
        raise ValueError(
            f"only {len(censuses)} registered platform(s) ({sorted(censuses)}) declare static web "
            f"hosting; a cross-platform parity gate needs at least {_MIN_PLATFORMS_FOR_COMPARISON}."
        )
    return censuses


# ---------------------------------------------------------------------------
# Non-vacuity self-test
# ---------------------------------------------------------------------------


def _assert(condition: bool, label: str) -> bool:
    print(f"  {'PASS' if condition else 'FAIL'}: {label}")
    return condition


#: The value a planted census emits for a header the declared set does not
#: carry (the out-of-vocabulary case) -- it has no declared value to copy.
_PLANTED_UNDECLARED_VALUE: Final[str] = "planted"


def _planted_census(
    platform: str,
    header_names: tuple[str, ...],
    *,
    expected_headers: Mapping[str, str],
    overrides: Mapping[str, str] | None = None,
) -> PlatformCensus:
    """A synthetic census emitting *header_names*, each with its declared
    value from *expected_headers* unless *overrides* supplies another; the
    CSP sample carries whatever value the census emits for the CSP header,
    exactly as the live scan derives it."""
    emitted = {
        name: (overrides or {}).get(name, expected_headers.get(name, _PLANTED_UNDECLARED_VALUE))
        for name in header_names
    }
    spellings = tuple(
        HeaderSpelling(platform, "planted", index + 1, name, emitted[name]) for index, name in enumerate(header_names)
    )
    csp_name = _csp_header_name(_fixture_header_set(is_loopback=False))
    samples = (CspSample(platform, "planted", 1, emitted[csp_name]),) if csp_name in emitted else ()
    return PlatformCensus(platform, spellings, samples, expected_headers)


def _self_test_comparator(
    families: frozenset[str], expected: Mapping[str, str], loopback_expected: Mapping[str, str]
) -> bool:
    ok = True
    full = tuple(sorted(families))
    csp_name = _csp_header_name(_fixture_header_set(is_loopback=False))
    clean = {
        "alpha": _planted_census("alpha", full, expected_headers=expected),
        "beta": _planted_census("beta", full, expected_headers=expected),
    }
    problems, verdicts = evaluate(families, clean)
    ok &= _assert(problems == [], "two fully realizing platforms report no problem")

    missing_family = sorted(families)[-1]
    partial_names = tuple(name for name in full if name != missing_family)
    partial = {
        "alpha": _planted_census("alpha", partial_names, expected_headers=expected),
        "beta": clean["beta"],
    }
    problems, _ = evaluate(families, partial)
    ok &= _assert(
        len(problems) == 1 and missing_family in problems[0] and "does not realize" in problems[0],
        "a platform missing a family it is expected to realize is exactly one problem",
    )

    hsts_family = next(family for family in families if family not in loopback_expected)
    loopback_names = tuple(name for name in full if name != hsts_family)
    loopback_clean = {
        "alpha": _planted_census("alpha", loopback_names, expected_headers=loopback_expected),
        "beta": clean["beta"],
    }
    problems, verdicts = evaluate(families, loopback_clean)
    ok &= _assert(
        problems == [],
        "a loopback platform legitimately omitting Strict-Transport-Security is not a violation",
    )
    ok &= _assert(
        hsts_family not in verdicts["alpha"].expected_families,
        "the loopback platform's verdict records the topology-narrowed expected set",
    )

    unregistered = {
        "alpha": _planted_census("alpha", full + ("X-Hand-Rolled-Header",), expected_headers=expected),
        "beta": clean["beta"],
    }
    problems, _ = evaluate(families, unregistered)
    ok &= _assert(
        len(problems) == 1 and "X-Hand-Rolled-Header" in problems[0] and "not part of" in problems[0],
        "a realized header outside the declared vocabulary is exactly one problem",
    )

    weakened_family = next(name for name in full if name != csp_name)
    weakened_value = f"{expected[weakened_family]}-weakened"
    weakened = {
        "alpha": _planted_census("alpha", full, expected_headers=expected, overrides={weakened_family: weakened_value}),
        "beta": clean["beta"],
    }
    problems, _ = evaluate(families, weakened)
    ok &= _assert(
        len(problems) == 1
        and weakened_family in problems[0]
        and weakened_value in problems[0]
        and repr(expected[weakened_family]) in problems[0]
        and "declared set computes" in problems[0],
        "a realized family carrying a value other than the declared one is exactly one problem naming the "
        "header, the emitted value and the declared value",
    )

    for token in _UNSAFE_CSP_TOKENS:
        unsafe_csp = f"{expected[csp_name]}; {token}"
        unsafe = {
            "alpha": _planted_census("alpha", full, expected_headers=expected, overrides={csp_name: unsafe_csp}),
            "beta": clean["beta"],
        }
        problems, _ = evaluate(families, unsafe)
        token_problems = [problem for problem in problems if f"contains {token!r}" in problem]
        value_problems = [problem for problem in problems if "declared set computes" in problem]
        ok &= _assert(
            len(problems) == 2
            and len(token_problems) == 1
            and len(value_problems) == 1
            and csp_name in value_problems[0],
            f"a CSP containing {token!r} is exactly one unsafe-token problem (plus the CSP value divergence) "
            f"despite full family realization",
        )

    nobody = {
        "alpha": _planted_census("alpha", partial_names, expected_headers=expected),
        "beta": _planted_census("beta", partial_names, expected_headers=expected),
    }
    problems, _ = evaluate(families, nobody)
    ok &= _assert(
        any("dead contract" in problem and missing_family in problem for problem in problems),
        "a family nobody realizes anywhere is reported as a dead contract",
    )
    return ok


def _self_test_topology_families(families: frozenset[str]) -> bool:
    ok = True
    loopback = _topology_families(is_loopback=True)
    ok &= _assert(
        loopback <= families and len(families - loopback) == 1,
        "the loopback family set is the full set minus exactly one family",
    )
    ok &= _assert(
        next(iter(families - loopback)) not in loopback,
        "the one loopback-omitted family is Strict-Transport-Security's own family",
    )
    return ok


def _self_test_min_platforms() -> bool:
    try:
        _require_min_platforms(frozenset({"only-one"}))
        return _assert(False, "fewer than two registered platforms is refused")
    except SystemExit as exc:
        return _assert(exc.code == EXIT_USAGE, "fewer than two registered platforms is refused")


class _ConformantFixtureProbes:
    """A fixture platform whose artifact carries exactly the declared header set."""

    def realized_web_security_headers(self, header_set: WebSecurityHeaderSet) -> Mapping[str, str]:
        return dict(header_set.as_header_dict())


class _DivergentFixtureProbes:
    """A fixture platform whose artifact weakens one declared header value."""

    def realized_web_security_headers(self, header_set: WebSecurityHeaderSet) -> Mapping[str, str]:
        headers = dict(header_set.as_header_dict())
        victim = next(name for name in sorted(headers) if headers[name] != header_set.content_security_policy)
        headers[victim] = f"{headers[victim]}-weakened"
        return headers


class _EmptyFixtureProbes:
    """A fixture platform whose probe finds no header in its artifact."""

    def realized_web_security_headers(self, header_set: WebSecurityHeaderSet) -> Mapping[str, str]:
        return {}


class _FixturePlatformWithoutProbes:
    """A fixture platform class with no `declared_conformance_probes` member."""


def _self_test_probe_dispatch(families: frozenset[str]) -> bool:
    """Drive the gate's real dispatch with in-process fixture probes whose
    platform name is not a registered one."""
    ok = True
    for is_loopback in (False, True):
        topology = "loopback" if is_loopback else "domain"
        census = census_platform(_SELF_TEST_PLATFORM, _ConformantFixtureProbes(), is_loopback=is_loopback)
        problems, _ = evaluate(families, {_SELF_TEST_PLATFORM: census})
        dead_contract_only = all("dead contract" in problem for problem in problems)
        ok &= _assert(dead_contract_only, f"a conformant fixture probe ({topology}) reports no platform problem")

    divergent = census_platform(_SELF_TEST_PLATFORM, _DivergentFixtureProbes(), is_loopback=False)
    problems, _ = evaluate(families, {_SELF_TEST_PLATFORM: divergent})
    ok &= _assert(
        any("declared set computes" in problem for problem in problems),
        "a fixture probe whose artifact weakens a header value is a violation",
    )

    try:
        census_platform(_SELF_TEST_PLATFORM, _EmptyFixtureProbes(), is_loopback=False)
        ok &= _assert(False, "a fixture probe returning no header fails")
    except ValueError as exc:
        ok &= _assert(
            _SELF_TEST_PLATFORM in str(exc) and "emitted no header" in str(exc),
            "a fixture probe returning no header fails naming the platform",
        )

    try:
        conformance_probes_of_platform_class(_SELF_TEST_PLATFORM, _FixturePlatformWithoutProbes)
        ok &= _assert(False, "a fixture platform with no probe member fails")
    except PluginValidationError as exc:
        ok &= _assert(
            _SELF_TEST_PLATFORM in str(exc) and "declares no conformance probes" in str(exc),
            "a fixture platform with no probe member fails with the accessor's message",
        )
    return ok


def _self_test_live_scan(families: frozenset[str]) -> bool:
    """The live scan must find every declared family realized by at least one
    REAL registered platform -- driving the real generation composition, not
    a fixture. A scan that finds nothing is broken, not clean."""
    censuses = scan_all_registered_platforms()
    realized_anywhere: frozenset[str] = (
        frozenset().union(*(realized_families(census) for census in censuses.values())) if censuses else frozenset()
    )
    ok = _assert(
        families <= realized_anywhere,
        f"live census finds every declared family realized somewhere (missing: {sorted(families - realized_anywhere)})",
    )
    problems, _ = evaluate(families, censuses)
    ok &= _assert(
        problems == [],
        f"the live registered platform set passes evaluate() with no violations (problems: {problems})",
    )
    return ok


def _self_test_names_no_target() -> bool:
    """This gate enumerates platforms from registration and must name none."""
    failures = self_test_gate_names_no_target(__file__)
    for line in failures:
        print(f"  FAIL: {line}")
    return _assert(not failures, "this gate names no registered target (imports and name literals)")


def self_test() -> bool:
    print("Non-vacuity self-test:")
    if not _self_test_names_no_target():
        return False
    families = declared_header_families()
    ok = _assert(len(families) >= 2, "the shared builder declares at least two header families")
    ok &= _self_test_comparator(
        families,
        _fixture_header_set(is_loopback=False).as_header_dict(),
        _fixture_header_set(is_loopback=True).as_header_dict(),
    )
    ok &= _self_test_topology_families(families)
    ok &= _self_test_min_platforms()
    ok &= _self_test_probe_dispatch(families)
    ok &= _self_test_live_scan(families)
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

    families = declared_header_families()
    try:
        censuses = scan_all_registered_platforms()
    except (ValueError, PluginValidationError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    problems, verdicts = evaluate(families, censuses)
    print(
        f"\nWeb security header census ({len(censuses)} realizing platform(s), "
        f"{len(families)} declared header family(ies)):"
    )
    print(render_report(families, verdicts))
    if problems:
        print(f"\nError: {len(problems)} web-security-header parity violation(s):", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return EXIT_FAIL
    print(
        "\nEvery registered platform realizing static_web_hosting emits the one "
        "declared security-header set for its own topology, with no unsafe CSP token."
    )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
