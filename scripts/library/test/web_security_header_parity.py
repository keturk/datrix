"""Web security header parity gate -- every registered platform that hosts a
web client realizes the ONE declared security-header set from
`datrix_common.generation.web_security_headers`, with no declarable hole: a
generated static site is either fronted by the full header set its own
topology requires, or it is a defect, never a documented gap.

Every static-site hosting realization -- docker/local's loopback nginx
container, AWS's CloudFront response-headers policy, Azure's Static Web Apps
`staticwebapp.config.json` -- consumes
`datrix_common.generation.web_security_headers.build_web_security_headers`,
but none of the three spells a header NAME literally in its own package
source: each threads the shared builder's `WebSecurityHeaderSet.as_header_dict()`
straight into its own rendering primitive (a Jinja loop, a CDK IR list, a JSON
object), so a census of `.py`/`.j2` source text -- the technique
`framework_header_parity.py` and `problem_type_parity.py` use for a WIRE
NAME spelled directly in source -- finds nothing to compare on any of the
three. This gate instead DRIVES the real generation composition for one
shared fixture (app, web target, environment): it renders each platform's
real artifact (the nginx server block, the CloudFront response-headers
policy IR, the `staticwebapp.config.json` payload) from a `WebSecurityHeaderSet`
built by the same shared function every platform calls, then parses the
EMITTED artifact structurally -- nginx `add_header` directives, the CDK
policy's typed security-header slots plus its `ResponseCustomHeader` call
list, the parsed JSON `globalHeaders` object --
to prove the artifact actually carries what the shared builder computed,
never merely that the platform's source happens to call the right function.

Strict-Transport-Security is the one family whose PRESENCE is itself
topology-dependent -- `build_web_security_headers` omits it, correctly, on a
loopback profile (HSTS is meaningless over plain HTTP). This is not a
per-platform declared hole (the design states the header set is mandatory
everywhere a platform realizes `static_web_hosting`): it is read from the
platform's own `PlatformCapabilityDeclaration.static_web_hosting.origin`
(`"loopback_port"` vs `"domain"`) and used to compute that platform's own
topology-correct expected family set via the SAME shared builder, never a
hand-typed exemption.

Platform set from the installed `datrix.platforms` entry points at runtime;
the declared header set read from `datrix_common.generation.web_security_headers`
at runtime -- never a table in this script. Runs a built-in non-vacuity
self-test on every invocation. Repo-level validation script (per the datrix
showcase boundary -- no pytest suite lives in datrix).
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

_LIBRARY_DIR = Path(__file__).resolve().parent.parent
if _LIBRARY_DIR.exists() and str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from datrix_common.generation.template_generator import TemplateGenerator  # noqa: E402
from datrix_common.generation.web_security_headers import (  # noqa: E402
    WebSecurityHeaderSet,
    build_web_security_headers,
)
from datrix_common.plugin.capability_resolution import declaration_for_provider  # noqa: E402
from shared.registered_targets import (  # noqa: E402
    AXIS_PLATFORMS,
    WORKSPACE_ROOT,
    discover_target_package_src_dirs,
    registered_platform_names,
)

if TYPE_CHECKING:
    from datrix_codegen_aws.iac.cdk_ir import CallExpr, Expr
    from datrix_common.plugin.capability_cells import StaticWebHostingRealization

logger = logging.getLogger(__name__)

EXIT_OK: Final[int] = 0
EXIT_FAIL: Final[int] = 1
EXIT_USAGE: Final[int] = 2

_MIN_PLATFORMS_FOR_COMPARISON: Final[int] = 2

#: Matches `discover_target_package_src_dirs`'s own fold-label join --
#: several registered `datrix.platforms` names sharing one package (e.g.
#: "azure+azure-vm", "docker+local") are folded into one comparison label;
#: this splits it back to the constituent names when the per-name
#: `static_web_hosting` declaration must be read individually. Kept as a
#: private literal rather than importing the module-private separator
#: constant, mirroring `behaviour_parity.py`'s own `_LABEL_JOIN_SEPARATOR`.
_LABEL_JOIN_SEPARATOR: Final[str] = "+"

#: The exact CSP directive tokens a Content-Security-Policy value must never
#: contain (the shared builder's own contract -- see its module docstring),
#: spelled exactly as the Content-Security-Policy grammar itself spells them
#: (always lowercase, hyphenated) -- a case-sensitive substring search, never
#: case-folded, so a platform cannot dodge the check by re-casing the token.
_UNSAFE_CSP_TOKENS: Final[tuple[str, ...]] = ("unsafe-inline", "unsafe-eval")

#: One shared fixture (app, web target, environment) every platform's
#: artifact is rendered against -- domain-neutral placeholders, never a real
#: or customer origin. `is_loopback` is the one input that varies, resolved
#: per platform from its own `static_web_hosting.origin` declaration.
_FIXTURE_API_ORIGIN: Final[str] = "https://api.fixture.example"
_FIXTURE_IDENTITY_AUTHORITY: Final[str] = "https://auth.fixture.example"

#: nginx `add_header <Name> "<Value>" always;` directive -- the exact
#: grammar `web_static_site_nginx.conf.j2`'s header loop emits (see its own
#: header block comment: "never a second, hand-written header list"). A
#: header VALUE never contains a literal `" always;`, so this is an exact
#: structural parse of one directive line, not a loose scan. Applied only at
#: nginx BRACE DEPTH 1 (directly inside `server { }`, before any nested
#: `location { }`) -- see `_docker_driver`: a `location` block's own
#: `add_header Cache-Control ...` directives are a real, legitimate part of
#: the emitted config but are scoped to that location only (nginx's own
#: semantics: directives at server level apply to every response; a
#: location's directives apply only inside it) and are not part of the
#: shared security-header set, so counting them would be a false positive.
_NGINX_ADD_HEADER_RE: Final[re.Pattern[str]] = re.compile(r'^\s*add_header\s+(\S+)\s+"(.*)"\s+always;\s*$')

#: The nginx brace depth the security-header loop is emitted at: directly
#: inside `server { }` (depth 1), never inside a nested `location { }`
#: (depth 2+). See `_NGINX_ADD_HEADER_RE`.
_NGINX_SERVER_BLOCK_DEPTH: Final[int] = 1


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
    `datrix_common.generation.web_security_headers` -- never a literal tuple
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
    package: str
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
        for family in sorted(realized - families):
            problems.append(
                f"{census.package} ({platform}): emits header {family!r}, which is "
                f"not part of the one declared web-security header set "
                f"(datrix_common.generation.web_security_headers). Fix: remove the "
                f"hand-written header, or thread it through build_web_security_headers "
                f"so every platform stays on the one declared set."
            )
        for family in sorted(census.expected_families - realized):
            problems.append(
                f"{census.package} ({platform}): does not realize declared header "
                f"family {family!r} for its own topology. Fix: thread "
                f"build_web_security_headers's output for this header into the "
                f"platform's rendering path -- there is no declared-hole escape for "
                f"this gate."
            )
        for spelling in census.header_spellings:
            expected_value = census.expected_headers.get(spelling.header_name)
            if expected_value is None or spelling.value == expected_value:
                continue
            problems.append(
                f"{census.package} ({platform}): {spelling.relative_path}:{spelling.line}: "
                f"emits {spelling.header_name!r} as {spelling.value!r}, but the one declared "
                f"set computes {expected_value!r} for this platform's topology. Fix: emit "
                f"build_web_security_headers's value unchanged -- a platform never rewrites "
                f"a declared header value."
            )
        for sample in census.csp_samples:
            for token in _UNSAFE_CSP_TOKENS:
                if token in sample.directive_text:
                    problems.append(
                        f"{census.package} ({platform}): {sample.relative_path}:"
                        f"{sample.line}: Content-Security-Policy contains {token!r}, "
                        f"forbidden regardless of family completeness. Fix: remove "
                        f"the unsafe directive token from the CSP the platform emits."
                    )
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
# Platform-axis resolution (which packages realize static_web_hosting, and
# in what origin shape)
# ---------------------------------------------------------------------------


def _resolve_platform_origin(
    label: str, realizations: Mapping[str, StaticWebHostingRealization]
) -> tuple[str | None, str | None]:
    """Return `(origin, unrealized_reason)` for one folded platform *label*
    given the `StaticWebHostingRealization` of each of its constituent
    registered names.

    Exactly one element of the pair is non-`None`. Every constituent name
    unrealized yields `(None, joined reasons)` -- set aside, never counted as
    passing silently. At least one realized name yields its origin; two
    realized names within the SAME package that disagree on origin is a real
    configuration defect (the platform axis assumes one physical realization
    per package) and raises rather than picking one silently.

    Args:
        label: The folded platform label (`discover_target_package_src_dirs`
            output), e.g. `"docker+local"`.
        realizations: `{registered name: its static_web_hosting declaration}`
            for every name folded into *label*.

    Returns:
        `(origin, None)` when realized, `(None, reason)` when not.

    Raises:
        ValueError: Two realized constituent names disagree on origin.
    """
    realized_origins = {
        name: realization.origin for name, realization in realizations.items() if realization.is_realized
    }
    if not realized_origins:
        reasons = "; ".join(f"{name}: {realization.reason}" for name, realization in sorted(realizations.items()))
        return None, reasons
    distinct_origins = frozenset(realized_origins.values())
    if len(distinct_origins) != 1:
        raise ValueError(
            f"{label}: registered names {sorted(realized_origins)} realize "
            f"static_web_hosting with disagreeing origins {sorted(distinct_origins)} "
            f"-- the platform axis assumes one physical realization per package. "
            f"Fix: reconcile the declarations, or split the package so each origin "
            f"shape gets its own comparison entry."
        )
    return next(iter(distinct_origins)), None


# ---------------------------------------------------------------------------
# Per-platform drivers -- each renders the REAL artifact for the shared
# fixture and parses it structurally. Genuinely different techniques per
# platform (a Jinja-rendered nginx block, a CDK IR call tree, a JSON
# payload), so dispatch is a closed table keyed by the package's import
# name, mirroring field_error_path_parity.py's per-language technique
# dispatch -- never a generic file-text census (see module docstring for why
# that technique finds nothing here).
# ---------------------------------------------------------------------------


def _parse_server_level_add_headers(rendered: str) -> dict[str, str]:
    """Parse every `add_header` directive at nginx brace depth 1 (directly
    inside `server { }`) out of *rendered* -- tracking brace depth per line
    so a `location { }` block's own, differently-scoped `add_header`
    directives (Cache-Control) are excluded by nginx's own block structure,
    never by indentation or a hand-picked line range."""
    depth = 0
    headers: dict[str, str] = {}
    for line in rendered.splitlines():
        if depth == _NGINX_SERVER_BLOCK_DEPTH:
            match = _NGINX_ADD_HEADER_RE.match(line)
            if match:
                headers[match.group(1)] = match.group(2)
        depth += line.count("{") - line.count("}")
    return headers


def _docker_driver(src_dir: Path, header_set: WebSecurityHeaderSet) -> dict[str, str]:
    """Render docker's real nginx server block and parse its server-level
    `add_header` directives -- the header names are Jinja variables in the
    template (`{{ name }}`/`{{ value }}`), never literal source text, so
    only the RENDERED artifact carries them."""
    from datrix_codegen_docker.generators.compose._web_static_site import (
        render_static_site_nginx_conf,
    )

    template_gen = TemplateGenerator(template_dir=src_dir / "templates", target_language="docker")
    rendered = render_static_site_nginx_conf(template_gen, header_set, spa_fallback_paths=())
    headers = _parse_server_level_add_headers(rendered)
    if not headers:
        raise ValueError(
            "docker's rendered nginx static-site config carries zero server-level "
            "'add_header ... always;' directives for the fixture header set -- "
            "render_static_site_nginx_conf's template or header loop changed shape; "
            "update _parse_server_level_add_headers in web_security_header_parity.py "
            "to match."
        )
    return headers


def _keyword_value(call: CallExpr, keyword_name: str, *, context: str) -> Expr:
    """Return *call*'s keyword argument named *keyword_name*, raising with
    *context* if none matches -- the one keyword-lookup primitive both
    `_literal_str_keyword` and `_extract_aws_response_headers` walk the CDK
    IR through (the CDK IR walk's own structural-parse discipline; see
    module docstring: "parsing each artifact structurally... never a
    single-line regex")."""
    for keyword in call.keywords:
        if keyword.name == keyword_name:
            return keyword.value
    raise ValueError(
        f"{context}: carries no {keyword_name!r} keyword. "
        f"build_response_headers_policy's IR shape changed; update the parity "
        f"gate's CDK IR walk to match."
    )


def _literal_str_keyword(call: CallExpr, keyword_name: str, *, context: str) -> str:
    """Return the string `Literal.value` of *call*'s keyword argument named
    *keyword_name*, via `_keyword_value`, raising with *context* if it is not
    a string `Literal`."""
    from datrix_codegen_aws.iac.cdk_ir import Literal

    value = _keyword_value(call, keyword_name, context=context)
    if isinstance(value, Literal) and isinstance(value.value, str):
        return value.value
    raise ValueError(
        f"{context}: keyword {keyword_name!r} is not a string Literal ({value!r}). "
        f"build_response_headers_policy's IR shape changed; update the parity "
        f"gate's CDK IR walk to match."
    )


#: CloudFront's typed security-header slot (`ResponseSecurityHeadersBehavior`
#: keyword) -> the wire header CloudFront emits for it. CloudFront refuses
#: these headers as custom headers, so the AWS realization carries them only
#: here; each slot is decoded back to its wire value below.
_CLOUDFRONT_SECURITY_SLOT_HEADERS: Final[dict[str, str]] = {
    "content_security_policy": "Content-Security-Policy",
    "strict_transport_security": "Strict-Transport-Security",
    "content_type_options": "X-Content-Type-Options",
    "referrer_policy": "Referrer-Policy",
}

#: The value CloudFront's `X-Content-Type-Options` slot emits.
_CLOUDFRONT_CONTENT_TYPE_OPTIONS_VALUE: Final[str] = "nosniff"


def _as_call(expr: Expr, *, context: str) -> CallExpr:
    """Return *expr* as a `CallExpr`, raising with *context* otherwise."""
    from datrix_codegen_aws.iac.cdk_ir import CallExpr

    if isinstance(expr, CallExpr):
        return expr
    raise ValueError(
        f"{context} is not a CallExpr ({expr!r}). build_response_headers_policy's "
        f"IR shape changed; update the parity gate's CDK IR walk to match."
    )


def _literal_keyword(call: CallExpr, keyword_name: str, *, context: str) -> object:
    """Return the `Literal.value` of *call*'s keyword *keyword_name*."""
    from datrix_codegen_aws.iac.cdk_ir import Literal

    value = _keyword_value(call, keyword_name, context=context)
    if isinstance(value, Literal):
        return value.value
    raise ValueError(
        f"{context}: keyword {keyword_name!r} is not a Literal ({value!r}). "
        f"build_response_headers_policy's IR shape changed."
    )


def _decode_aws_hsts(slot: CallExpr) -> str:
    """`ResponseHeadersStrictTransportSecurity(access_control_max_age=Duration.seconds(N),
    include_subdomains=..., preload=...)` -> the header value CloudFront emits."""
    from datrix_codegen_aws.iac.cdk_ir import Literal

    context = "ResponseHeadersStrictTransportSecurity"
    max_age_call = _as_call(_keyword_value(slot, "access_control_max_age", context=context), context=context)
    if len(max_age_call.args) != 1 or not isinstance(max_age_call.args[0], Literal):
        raise ValueError(f"{context}: access_control_max_age is not Duration.seconds(<literal>).")
    value = f"max-age={max_age_call.args[0].value}"
    if _literal_keyword(slot, "include_subdomains", context=context) is True:
        value += "; includeSubDomains"
    if _literal_keyword(slot, "preload", context=context) is True:
        value += "; preload"
    return value


def _decode_aws_referrer_policy(slot: CallExpr) -> str:
    """`ResponseHeadersReferrerPolicy(referrer_policy=cloudfront.HeadersReferrerPolicy.X)`
    -> the `Referrer-Policy` token CloudFront emits (`X` lower-cased, `_` -> `-`)."""
    from datrix_codegen_aws.iac.cdk_ir import AttrRef

    member = _keyword_value(slot, "referrer_policy", context="ResponseHeadersReferrerPolicy")
    if not isinstance(member, AttrRef):
        raise ValueError(
            f"ResponseHeadersReferrerPolicy: referrer_policy is not a "
            f"HeadersReferrerPolicy member ({member!r})."
        )
    return member.attr.lower().replace("_", "-")


def _decode_aws_security_slot(slot_name: str, slot: CallExpr) -> str:
    """The wire value CloudFront emits for one typed security-header slot."""
    if slot_name == "content_security_policy":
        return _literal_str_keyword(slot, "content_security_policy", context="ResponseHeadersContentSecurityPolicy")
    if slot_name == "strict_transport_security":
        return _decode_aws_hsts(slot)
    if slot_name == "content_type_options":
        return _CLOUDFRONT_CONTENT_TYPE_OPTIONS_VALUE
    if slot_name == "referrer_policy":
        return _decode_aws_referrer_policy(slot)
    raise ValueError(
        f"No decoder for CloudFront security-header slot {slot_name!r}; "
        f"_CLOUDFRONT_SECURITY_SLOT_HEADERS and _decode_aws_security_slot disagree."
    )


def _extract_aws_security_headers(policy_call: CallExpr) -> dict[str, str]:
    """Every header the policy's typed `security_headers_behavior` emits."""
    behavior = _as_call(
        _keyword_value(policy_call, "security_headers_behavior", context="ResponseHeadersPolicy"),
        context="ResponseHeadersPolicy.security_headers_behavior",
    )
    headers: dict[str, str] = {}
    for keyword in behavior.keywords:
        slot = _as_call(keyword.value, context=f"ResponseSecurityHeadersBehavior.{keyword.name}")
        if _literal_keyword(slot, "override", context=keyword.name) is not True:
            raise ValueError(
                f"ResponseSecurityHeadersBehavior.{keyword.name} does not override the "
                f"origin's copy -- an origin header could replace the declared value."
            )
        if keyword.name not in _CLOUDFRONT_SECURITY_SLOT_HEADERS:
            raise ValueError(
                f"ResponseSecurityHeadersBehavior carries slot {keyword.name!r}, which "
                f"this gate cannot decode. Known slots: "
                f"{sorted(_CLOUDFRONT_SECURITY_SLOT_HEADERS)}. Fix: add its decoder to "
                f"web_security_header_parity.py."
            )
        headers[_CLOUDFRONT_SECURITY_SLOT_HEADERS[keyword.name]] = _decode_aws_security_slot(
            keyword.name, slot
        )
    return headers


def _extract_aws_response_headers(policy_call: CallExpr) -> dict[str, str]:
    """Walk `build_response_headers_policy`'s returned
    `cloudfront.ResponseHeadersPolicy(...)` CDK IR -- already a typed,
    structured AST-equivalent Datrix itself builds -- to extract every
    `(header, value)` pair CloudFront will emit: each typed slot of
    `security_headers_behavior` decoded to its wire header, plus every
    `ResponseCustomHeader(...)` of `custom_headers_behavior`. A header that
    appears in both halves is a defect (CloudFront refuses a security header
    as a custom header), reported by name."""
    headers = _extract_aws_security_headers(policy_call)
    for name, value in _extract_aws_custom_headers(policy_call).items():
        if name.lower() in {existing.lower() for existing in headers}:
            raise ValueError(
                f"AWS response-headers policy carries {name!r} both as a typed "
                f"security header and as a custom header; CloudFront refuses the policy."
            )
        headers[name] = value
    return headers


def _extract_aws_custom_headers(policy_call: CallExpr) -> dict[str, str]:
    """Every `(header, value)` pair of the policy's `custom_headers_behavior`."""
    from datrix_codegen_aws.iac.cdk_ir import CallExpr, ListLiteral

    behavior_call = _keyword_value(policy_call, "custom_headers_behavior", context="ResponseHeadersPolicy")
    if not isinstance(behavior_call, CallExpr):
        raise ValueError(
            f"ResponseHeadersPolicy: 'custom_headers_behavior' is not a CallExpr "
            f"({behavior_call!r}). build_response_headers_policy's IR shape changed."
        )
    custom_headers = _keyword_value(behavior_call, "custom_headers", context="ResponseCustomHeadersBehavior")
    if not isinstance(custom_headers, ListLiteral):
        raise ValueError(
            f"ResponseCustomHeadersBehavior: 'custom_headers' is not a ListLiteral "
            f"({custom_headers!r}). build_response_headers_policy's IR shape changed."
        )
    headers: dict[str, str] = {}
    for element in custom_headers.elements:
        if not isinstance(element, CallExpr):
            raise ValueError(
                f"ResponseCustomHeadersBehavior.custom_headers element is not a "
                f"CallExpr ({element!r}). build_response_headers_policy's IR shape "
                f"changed."
            )
        name = _literal_str_keyword(element, "header", context="ResponseCustomHeader")
        value = _literal_str_keyword(element, "value", context="ResponseCustomHeader")
        headers[name] = value
    return headers


def _aws_driver(src_dir: Path, header_set: WebSecurityHeaderSet) -> dict[str, str]:  # noqa: ARG001
    """Build AWS's real CloudFront response-headers policy IR and walk it --
    `src_dir` is unused (AWS's builder is pure over `header_set`) but kept
    for a uniform driver signature across all three platforms."""
    from datrix_codegen_aws.iac.build_web_static_site_stack import build_response_headers_policy

    policy_call = build_response_headers_policy(header_set)
    return _extract_aws_response_headers(policy_call)


def _azure_driver(src_dir: Path, header_set: WebSecurityHeaderSet) -> dict[str, str]:  # noqa: ARG001
    """Render azure's real `staticwebapp.config.json` and parse its
    `globalHeaders` object -- `src_dir` is unused (azure's renderer is pure
    over `header_set`) but kept for a uniform driver signature."""
    from datrix_codegen_azure.generators.static_web_app_config import render_staticwebapp_config

    rendered = render_staticwebapp_config(header_set, spa_fallback_paths=())
    payload = json.loads(rendered)
    global_headers = payload.get("globalHeaders")
    if not isinstance(global_headers, dict):
        raise ValueError(
            "azure's rendered staticwebapp.config.json carries no 'globalHeaders' "
            "object -- render_staticwebapp_config's shape changed; update the "
            "parity gate's JSON extraction to match."
        )
    return {str(name): str(value) for name, value in global_headers.items()}


#: Closed dispatch table: package import name -> the function that drives
#: its real generation composition and returns `{header name: value}` for
#: the shared fixture. A registered platform whose package has no entry here
#: is a loud failure (see `scan_all_registered_platforms`), never a silent
#: skip -- a new static-site-hosting platform lands with its own driver, not
#: by falling through unnoticed.
_PLATFORM_DRIVERS: Final[dict[str, Callable[[Path, WebSecurityHeaderSet], dict[str, str]]]] = {
    "datrix_codegen_docker": _docker_driver,
    "datrix_codegen_aws": _aws_driver,
    "datrix_codegen_azure": _azure_driver,
}


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


def scan_all_registered_platforms() -> tuple[dict[str, PlatformCensus], dict[str, str]]:
    """Census every package backing a registered `datrix.platforms` entry
    that realizes `static_web_hosting`, driving its real generation
    composition for the shared fixture. A package whose realizing name(s)
    all declare the capability unrealized is set aside in the second return
    value with its reason -- never counted as passing silently (see module
    docstring).

    Returns:
        `({label: PlatformCensus}, {label: unrealized reason})`.

    Raises:
        ValueError: A realizing package has no entry in `_PLATFORM_DRIVERS`,
            or its constituent registered names disagree on origin (see
            `_resolve_platform_origin`).
    """
    platform_names = registered_platform_names()
    _require_min_platforms(platform_names)
    src_dirs = discover_target_package_src_dirs(AXIS_PLATFORMS, platform_names, WORKSPACE_ROOT)
    censuses: dict[str, PlatformCensus] = {}
    unrealized: dict[str, str] = {}
    for label, src_dir in sorted(src_dirs.items()):
        package = src_dir.parents[1].name
        member_names = label.split(_LABEL_JOIN_SEPARATOR)
        realizations = {name: declaration_for_provider(name).static_web_hosting for name in member_names}
        origin, reason = _resolve_platform_origin(label, realizations)
        if origin is None:
            unrealized[label] = reason or ""
            logger.debug("platform=%s package=%s unrealized reason=%s", label, package, reason)
            continue
        is_loopback = origin == "loopback_port"
        import_name = src_dir.name
        driver = _PLATFORM_DRIVERS.get(import_name)
        if driver is None:
            raise ValueError(
                f"{package} ({import_name}) realizes static_web_hosting "
                f"(origin={origin!r}) but web_security_header_parity.py has no "
                f"census driver for it in _PLATFORM_DRIVERS. Fix: add one that "
                f"drives this platform's real generation composition and returns "
                f"its effective {{header name: value}} set."
            )
        header_set = _fixture_header_set(is_loopback=is_loopback)
        effective_headers = driver(src_dir, header_set)
        artifact_label = f"{import_name} (rendered fixture artifact)"
        header_spellings = tuple(
            HeaderSpelling(label, artifact_label, 0, header_name, effective_headers[header_name])
            for header_name in sorted(effective_headers)
        )
        csp_header_name = _csp_header_name(header_set)
        csp_value = effective_headers.get(csp_header_name)
        csp_samples = (CspSample(label, artifact_label, 0, csp_value),) if csp_value is not None else ()
        censuses[label] = PlatformCensus(label, package, header_spellings, csp_samples, header_set.as_header_dict())
        logger.debug(
            "census platform=%s package=%s origin=%s realized=%d",
            label,
            package,
            origin,
            len(header_spellings),
        )
    return censuses, unrealized


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
    return PlatformCensus(platform, f"datrix-codegen-{platform}", spellings, samples, expected_headers)


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


def _self_test_origin_resolution() -> bool:
    from datrix_common.plugin.capability_cells import StaticWebHostingRealization

    ok = True
    unrealized_only = {
        "docker": StaticWebHostingRealization(status="unrealized", reason="planted: no loopback pairing"),
    }
    origin, reason = _resolve_platform_origin("docker", unrealized_only)
    ok &= _assert(
        origin is None and reason == "docker: planted: no loopback pairing",
        "every-name-unrealized yields (None, reason)",
    )

    single_realized = {
        "local": StaticWebHostingRealization(status="realized", origin="loopback_port"),
    }
    origin, reason = _resolve_platform_origin("docker+local", single_realized)
    ok &= _assert(origin == "loopback_port" and reason is None, "one realized name yields its origin")

    agreeing = {
        "azure": StaticWebHostingRealization(status="realized", origin="domain"),
        "azure-vm": StaticWebHostingRealization(status="realized", origin="domain"),
    }
    origin, reason = _resolve_platform_origin("azure+azure-vm", agreeing)
    ok &= _assert(origin == "domain" and reason is None, "two agreeing realized names yield their shared origin")

    disagreeing = {
        "alpha": StaticWebHostingRealization(status="realized", origin="domain"),
        "beta": StaticWebHostingRealization(status="realized", origin="loopback_port"),
    }
    try:
        _resolve_platform_origin("alpha+beta", disagreeing)
        ok &= _assert(False, "two disagreeing realized names raise")
    except ValueError:
        ok &= _assert(True, "two disagreeing realized names raise")
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


def _self_test_live_scan(families: frozenset[str]) -> bool:
    """The live scan must find every declared family realized by at least one
    REAL registered platform -- driving the real generation composition, not
    a fixture. A scan that finds nothing is broken, not clean."""
    censuses, _ = scan_all_registered_platforms()
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


def self_test() -> bool:
    print("Non-vacuity self-test:")
    families = declared_header_families()
    ok = _assert(len(families) >= 2, "the shared builder declares at least two header families")
    ok &= _self_test_comparator(
        families,
        _fixture_header_set(is_loopback=False).as_header_dict(),
        _fixture_header_set(is_loopback=True).as_header_dict(),
    )
    ok &= _self_test_origin_resolution()
    ok &= _self_test_topology_families(families)
    ok &= _self_test_min_platforms()
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
        censuses, unrealized = scan_all_registered_platforms()
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    problems, verdicts = evaluate(families, censuses)
    print(
        f"\nWeb security header census ({len(censuses)} realizing platform(s), "
        f"{len(families)} declared header family(ies)):"
    )
    print(render_report(families, verdicts))
    if unrealized:
        print("\nPlatforms declaring static_web_hosting unrealized (set aside, not counted):")
        for label, reason in sorted(unrealized.items()):
            print(f"  - {label}: {reason}")
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
