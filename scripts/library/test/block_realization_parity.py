"""Cross-platform capability parity gate.

Every installed ``datrix.platforms`` plugin declares a
``PlatformCapabilityDeclaration`` (``datrix_common.plugin.capability``) -- the
platform-axis counterpart of the language-axis ``supported_domain_parity.py``
gate. This gate compares those declarations ACROSS platforms at the CAPABILITY
level: an obligation exists for a block type, an observability category, an
identity feature, a runtime floor and a model provider -- never for the
implementation a capability is realized by. A platform that does not offer one
particular flavor, vendor product or provider has simply not got it in its
vocabulary; that is never a gap. A platform that realizes a capability by NO
implementation at all is a gap, recorded as a ``<kind>:<id>`` row in the
platform's own ``capability_gaps`` and still reported here (a row accounts for
the violation; it suppresses nothing in any other gate).

ONE EXTRACTOR, PURE COMPARATORS. :func:`extract_facts` is the only function
that reads attributes of a declaration (the partition guard additionally reads
the class's field list); every comparison is a pure function over
``Mapping[str, PlatformFacts]``. The extractor reads PRESENCE only, so it holds
on any cell shape, and the self-test plants :class:`PlatformFacts` directly and
constructs no declaration or cell.

THE SEVEN SURFACES:

1. ``block_types`` -- every block type any platform realizes by at least one
   flavor is realized by at least one flavor on every platform
   (``block_type:<id>`` row).
2. ``observability_categories`` -- every observability category any platform
   realizes by at least one native provider is so realized on every platform
   (``observability_category:<id>`` row).
3. ``supported_runtimes`` -- a platform declares at least one runtime when any
   other does (a floor; runtimes are vocabulary).
4. ``identity_features`` -- every identity feature any platform offers through
   at least one provider is offered through at least one provider on every
   platform (``identity_feature:<id>`` row).
5. ``static_web_hosting`` -- each platform's origin kind equals the one its OWN
   edge derives: ``domain`` when the edge binds custom domains, ``loopback_port``
   otherwise.
6. ``custom_domain_surfaces`` -- an edge-binding platform carries both surfaces;
   a platform whose edge binds no domain carries neither.
7. ``model_realizations`` -- a platform realizes at least one model provider
   with at least one flavor cell when any other does.

Surfaces 5-7 compare REQUIRED declaration fields, which the optional-field
partition alone could never see; :func:`_assert_field_partition_complete`
therefore partitions required and optional fields both, so a future field of
either kind cannot escape every comparison.

RETIRED SURFACES, each measured against the live platforms before removal:
secret backends and deployable constructs are construction-time floors of the
declaration and their members are product vocabulary; the set-shaped optional
fields (config-store engines, runtimes, host patterns, helper packages, vendor
tokens, gateway types, ...) are each platform's own vocabulary with a
legitimately empty set where a platform has no such product; the presence-shaped
optional fields (published host ports, edge origin ports, preflight entrypoint,
TLS-edge flags, CDN invalidation, ...) are per-platform topology facts that
differ by design between a loopback platform and a managed cloud. Each field
still lands in a named partition bucket so a future field is forced into one.

Target set is NEVER hardcoded: platforms are enumerated from the installed
``datrix.platforms`` entry points at run time
(:func:`~shared.registered_targets.registered_platform_names`).
"""

from __future__ import annotations

import argparse
import dataclasses
import logging
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Final, get_args

# Add library directory to sys.path to import from shared (this file lives at
# library/test/, shared/ lives at the sibling library/shared/).
_LIBRARY_DIR = Path(__file__).resolve().parent.parent
if _LIBRARY_DIR.exists() and str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from shared.registered_targets import registered_platform_names  # noqa: E402

from datrix_common.plugin.capability import (  # noqa: E402
    PlatformCapabilityDeclaration,
)
from datrix_common.plugin.capability_cells import (  # noqa: E402
    CustomDomainSurfaceName,
    StaticWebHostingOrigin,
)
from datrix_common.plugin.capability_resolution import declaration_for_provider  # noqa: E402

logger = logging.getLogger(__name__)

#: A cross-platform comparison over 0 or 1 platform is vacuous.
_MIN_PLATFORMS_FOR_COMPARISON: Final[int] = 2

_OBSERVABILITY_CATEGORIES: Final[tuple[str, ...]] = (
    "metrics", "tracing", "logging", "visualization", "alerting",
)

_ORIGIN_DOMAIN: Final[str] = "domain"
_ORIGIN_LOOPBACK: Final[str] = "loopback_port"
if frozenset({_ORIGIN_DOMAIN, _ORIGIN_LOOPBACK}) != frozenset(get_args(StaticWebHostingOrigin)):
    raise ValueError(
        "StaticWebHostingOrigin's members changed: this gate derives one origin kind per edge "
        f"and knows {sorted({_ORIGIN_DOMAIN, _ORIGIN_LOOPBACK})}, the vocabulary now holds "
        f"{sorted(get_args(StaticWebHostingOrigin))}. Fix: extend the origin comparison in "
        "block_realization_parity.py to the new member."
    )

#: The custom-domain surfaces an edge-binding platform must carry, derived from
#: the closed vocabulary itself.
_CUSTOM_DOMAIN_SURFACES: Final[frozenset[str]] = frozenset(get_args(CustomDomainSurfaceName))

#: Gap-row kinds (``<kind>:<id>``) a platform's own ``capability_gaps`` may use
#: to account for a capability it realizes by no implementation.
_GAP_KIND_BLOCK_TYPE: Final[str] = "block_type"
_GAP_KIND_OBSERVABILITY: Final[str] = "observability_category"
_GAP_KIND_IDENTITY: Final[str] = "identity_feature"

_RUNTIME_CAPABILITY: Final[str] = "runtime"
_MODEL_CAPABILITY: Final[str] = "model"

# ---------------------------------------------------------------------------
# Field partition buckets -- every PlatformCapabilityDeclaration field belongs
# to exactly one, so a future field cannot silently escape every comparison.
# ---------------------------------------------------------------------------

#: Optional fields owned by a dedicated surface above.
_SURFACE_OWNED_OPTIONAL_FIELDS: Final[frozenset[str]] = frozenset({
    "native_observability_providers",   # surface 2
    "identity_provider_realizations",   # surface 4 (providers; the features are compared)
    "identity_feature_realizations",    # surface 4
})

#: Optional fields whose floor the declaration enforces at construction (an
#: empty ``deployable_constructs`` is rejected there), leaving no cross-platform
#: comparison to make; the members are product vocabulary.
_CONSTRUCTION_ENFORCED_OPTIONAL_FIELDS: Final[frozenset[str]] = frozenset({
    "deployable_constructs",
})

#: Set-shaped optional fields whose members are product vocabulary (config-store
#: engines, runtimes, hosts, package names, vendor tokens, gateway types): each
#: platform's own vocabulary, legitimately empty on a platform with no such
#: product. The capability each stands for is enforced where it is resolved --
#: the notification-channel and websocket validators -- not by a cross-platform
#: union.
_VOCABULARY_SET_FIELDS: Final[frozenset[str]] = frozenset({
    "supported_config_stores",
    "container_scaffold_runtimes",
    "platform_allowed_host_patterns",
    "service_network_hosts",
    "native_cloud_helper_packages",
    "native_notification_vendors",
    "supported_gateway_types",
    "injected_test_identity_providers",
    "websocket_upgrade_runtimes",
    "non_evicting_cache_flavors",
})

#: Presence-shaped optional fields: per-platform topology facts (what the edge
#: terminates, which host ports a runtime publishes, what the deploy entrypoint
#: is, how a cache slice is delivered, ...). A loopback platform and a managed
#: cloud differ in them by design; a field one platform sets says nothing a
#: platform with a different edge could be missing. Where such a fact stands
#: for a capability, the declaration's own construction-time validators (the
#: custom-domain validator, the gateway-TLS check) and surface 5-6 here
#: enforce it.
_PLATFORM_FACT_FIELDS: Final[frozenset[str]] = frozenset({
    "platform_config_contract",
    "owns_provider_platform_generator",
    "provides_cdn_cache_invalidation",
    "identity_plan_wheel_deployed",
    "identity_deployment_target",
    "identity_write_back",
    "cdn_invalidation_realization",
    "requires_trusted_caller_behind_managed_gateway",
    "realizes_inprocess_async_hosting",
    "native_identity_provider",
    "gateway_terminates_tls",
    "rdbms_login_principal_is_per_service",
    "published_host_ports",
    "published_host_port_bindings",
    "edge_origin_host_port",
    "edge_path_routed_origins",
    "cache_pooled_slice_delivery",
    "publishes_gateway_behind_managed_edge",
    "trusted_edge_client_address_include",
    "deploy_preflight_entrypoint",
})

#: Fields that INVENTORY what a platform's own tooling writes into the generated
#: project tree, not a capability another platform could lack.
_EMISSION_INVENTORY_FIELDS: Final[frozenset[str]] = frozenset({
    "untracked_project_artifacts",
})

#: Fields that LEDGER the capabilities a platform realizes by no implementation,
#: each a typed gap row. The ledger is read here only as accounting for a
#: violation of surfaces 1, 2 and 4 and never compared as a coordinate set: a
#: platform with no known hole correctly carries no row.
_CAPABILITY_GAP_LEDGER_FIELDS: Final[frozenset[str]] = frozenset({
    "capability_gaps",
})

#: Fields the foundation has retired but a declaration may still carry until
#: their deletion lands. No surface reads them; they are subtracted from the
#: optional population so the guard holds on a declaration that still has them
#: and on one that no longer does. This constant is the only place the names
#: survive.
_RETIRED_FIELDS: Final[frozenset[str]] = frozenset({
    "declared_set_exclusions",
    "unrealizable_surfaces",
    "declared_capability_reasons",
})

_OPTIONAL_BUCKETS: Final[tuple[tuple[str, frozenset[str]], ...]] = (
    ("_SURFACE_OWNED_OPTIONAL_FIELDS", _SURFACE_OWNED_OPTIONAL_FIELDS),
    ("_CONSTRUCTION_ENFORCED_OPTIONAL_FIELDS", _CONSTRUCTION_ENFORCED_OPTIONAL_FIELDS),
    ("_VOCABULARY_SET_FIELDS", _VOCABULARY_SET_FIELDS),
    ("_PLATFORM_FACT_FIELDS", _PLATFORM_FACT_FIELDS),
    ("_EMISSION_INVENTORY_FIELDS", _EMISSION_INVENTORY_FIELDS),
    ("_CAPABILITY_GAP_LEDGER_FIELDS", _CAPABILITY_GAP_LEDGER_FIELDS),
    ("_RETIRED_FIELDS", _RETIRED_FIELDS),
)

#: Required fields compared by a dedicated surface: ``{field: surface that compares it}``.
_REQUIRED_FIELD_OWNERS: Final[Mapping[str, str]] = {
    "block_realizations": "block_types",
    "supported_runtimes": "supported_runtimes",
    "model_realizations": "model_realizations",
    "static_web_hosting": "static_web_hosting",
    "custom_domain_surfaces": "custom_domain_surfaces",
}

#: Required fields that are a value every platform must state, never a
#: capability another platform could lack.
_REQUIRED_PLATFORM_FACT_FIELDS: Final[frozenset[str]] = frozenset({
    "platform_label",
    "default_secret_backend",
    "crypto_signing_backend",
    "rdbms_connection_identity",
    "cache_connection_identity",
    "supported_secret_backends",
    "serverless_compute_model",
})

_REQUIRED_BUCKETS: Final[tuple[tuple[str, frozenset[str]], ...]] = (
    ("_REQUIRED_FIELD_OWNERS", frozenset(_REQUIRED_FIELD_OWNERS)),
    ("_REQUIRED_PLATFORM_FACT_FIELDS", _REQUIRED_PLATFORM_FACT_FIELDS),
)


def configure_logging(debug: bool = False) -> None:
    """Configure logging output."""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def _partition_problems(
    population: set[str],
    buckets: Sequence[tuple[str, frozenset[str]]],
    ignored_stale: frozenset[str],
) -> list[str]:
    """Describe fields of *population* unaccounted for, stale bucket names and
    names claimed by more than one bucket."""
    accounted: set[str] = set()
    overlaps: set[str] = set()
    for _, bucket in buckets:
        overlaps |= accounted & bucket
        accounted |= bucket
    missing = population - accounted
    stale = accounted - population - ignored_stale
    problems: list[str] = []
    if missing:
        problems.append(
            f"unaccounted-for fields (add each to exactly one bucket "
            f"{[name for name, _ in buckets]}): {sorted(missing)}"
        )
    if stale:
        problems.append(f"stale bucket names naming no field (remove): {sorted(stale)}")
    if overlaps:
        problems.append(f"fields claimed by more than one bucket (exactly one each): {sorted(overlaps)}")
    return problems


def _assert_field_partition_complete(fields: Sequence[dataclasses.Field[object]]) -> None:
    """Fail loud if a field of the declaration is triaged into no bucket.

    This is the mechanical guard against the failure mode this gate exists to
    prevent: a future field lands on ``PlatformCapabilityDeclaration`` and
    silently escapes every comparison. REQUIRED fields (no default) and OPTIONAL
    fields (a default or default factory) are partitioned separately, each field
    belonging to exactly one bucket. The field list is a parameter so the
    self-test plants lists instead of editing the dataclass.

    Raises:
        AssertionError: Naming unaccounted-for, stale and doubly-claimed fields,
            required and optional separately.
    """
    optional = {
        f.name
        for f in fields
        if f.default is not dataclasses.MISSING or f.default_factory is not dataclasses.MISSING
    }
    required = {f.name for f in fields} - optional
    problems = [
        f"required {problem}"
        for problem in _partition_problems(required, _REQUIRED_BUCKETS, frozenset())
    ]
    problems.extend(
        f"optional {problem}"
        for problem in _partition_problems(optional, _OPTIONAL_BUCKETS, _RETIRED_FIELDS)
    )
    if problems:
        raise AssertionError(
            "PlatformCapabilityDeclaration's field partition is incomplete or wrong "
            "(buckets live in block_realization_parity.py): " + "; ".join(problems) + "."
        )


@dataclasses.dataclass(frozen=True)
class SurfaceViolation:
    """One (platform, surface, coordinate) gap: the platform does not realize a
    capability (or fact) the comparison derives for it, while others do."""

    platform: str
    surface: str
    coordinate: str
    declaring_platforms: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class PlatformFacts:
    """Everything the comparisons read about one platform, extracted once."""

    platform: str
    block_types: frozenset[str]                    # block types with >= 1 offered flavor
    gap_surfaces: frozenset[str]                   # surfaces of the platform's own capability_gaps rows
    observability: Mapping[str, frozenset[str]]    # category -> native provider names
    runtimes: frozenset[str]                       # supported_runtimes, by value
    identity_features: frozenset[str]              # features with >= 1 offered (provider, feature) cell
    static_hosting_origin: str                     # "loopback_port" | "domain"
    binds_domains: bool                            # the platform's edge binds custom domains
    custom_domain_surfaces: frozenset[str]         # names of the custom-domain surfaces present
    model_flavor_counts: Mapping[str, int]         # model provider -> number of flavor cells


def extract_facts(platform: str, decl: PlatformCapabilityDeclaration) -> PlatformFacts:
    """The ONLY reader of a declaration's attributes. Presence only.

    Raises:
        ValueError: The declaration states no static-hosting origin or has not
            declared whether its gateway terminates TLS -- every registered
            platform states both, so an absent one is a defect, never a skip.
    """
    origin = decl.static_web_hosting.origin
    if origin is None:
        raise ValueError(
            f"Platform {platform!r} declares no static web hosting origin. Every registered "
            f"platform serves static web hosting (a loopback platform at a port). Fix: declare "
            f"origin {sorted(get_args(StaticWebHostingOrigin))} on its static_web_hosting."
        )
    binds_domains = decl.binds_custom_domains()
    if binds_domains is None:
        raise ValueError(
            f"Platform {platform!r} has not declared gateway_terminates_tls, so its edge "
            f"cannot be derived. Fix: declare gateway_terminates_tls on its capability declaration."
        )
    return PlatformFacts(
        platform=platform,
        block_types=frozenset(block_type for block_type, _ in decl.block_realizations),
        gap_surfaces=frozenset(gap.surface for gap in decl.capability_gaps),
        observability={
            category: frozenset(
                str(provider) for provider in decl.native_observability_providers.get(category, ())
            )
            for category in _OBSERVABILITY_CATEGORIES
        },
        runtimes=frozenset(runtime.value for runtime in decl.supported_runtimes),
        identity_features=frozenset(feature for _, feature in decl.identity_feature_realizations),
        static_hosting_origin=origin,
        binds_domains=binds_domains,
        custom_domain_surfaces=frozenset(decl.custom_domain_surfaces),
        model_flavor_counts={
            provider: len(realization.flavors)
            for provider, realization in decl.model_realizations.items()
        },
    )


def _coverage_gaps(
    facts: Mapping[str, PlatformFacts],
    surface: str,
    realized: Callable[[PlatformFacts], frozenset[str]],
    *,
    gap_kind: str | None,
) -> list[SurfaceViolation]:
    """A capability any platform realizes must be realized by every platform, or
    -- when *gap_kind* names a recorded gap kind -- carried as a
    ``<gap_kind>:<capability>`` row on the platform's own capability declaration.
    Compares capabilities, never the implementations a capability is realized
    by: a platform lacking one particular flavor, provider or vendor that
    another platform has is never a violation."""
    declaring: dict[str, set[str]] = {}
    for platform, platform_facts in facts.items():
        for capability in realized(platform_facts):
            declaring.setdefault(capability, set()).add(platform)
    return [
        SurfaceViolation(platform, surface, capability, tuple(sorted(platforms)))
        for capability, platforms in sorted(declaring.items())
        for platform, platform_facts in sorted(facts.items())
        if capability not in realized(platform_facts)
        and (gap_kind is None or f"{gap_kind}:{capability}" not in platform_facts.gap_surfaces)
    ]


def _realized_observability_categories(platform_facts: PlatformFacts) -> frozenset[str]:
    return frozenset(
        category for category, providers in platform_facts.observability.items() if providers
    )


def _runtime_floor(platform_facts: PlatformFacts) -> frozenset[str]:
    return frozenset({_RUNTIME_CAPABILITY}) if platform_facts.runtimes else frozenset()


def _model_floor(platform_facts: PlatformFacts) -> frozenset[str]:
    has_flavor = any(count > 0 for count in platform_facts.model_flavor_counts.values())
    return frozenset({_MODEL_CAPABILITY}) if has_flavor else frozenset()


def _static_web_hosting_gaps(facts: Mapping[str, PlatformFacts]) -> list[SurfaceViolation]:
    """A platform serves static web hosting at a custom domain exactly when its
    edge binds custom domains, and at a loopback port otherwise. Each platform
    is compared with its OWN edge, never with another platform: a docker runtime
    paired with a cloud provider is resolved by the provider's declaration, so
    there is no pairing-dependent origin to flatten."""
    violations: list[SurfaceViolation] = []
    for platform, platform_facts in sorted(facts.items()):
        expected = _ORIGIN_DOMAIN if platform_facts.binds_domains else _ORIGIN_LOOPBACK
        if platform_facts.static_hosting_origin != expected:
            agreeing = tuple(
                sorted(p for p, f in facts.items() if f.static_hosting_origin == expected)
            )
            violations.append(
                SurfaceViolation(
                    platform, "static_web_hosting", platform_facts.static_hosting_origin, agreeing
                )
            )
    return violations


def _custom_domain_gaps(facts: Mapping[str, PlatformFacts]) -> list[SurfaceViolation]:
    """An edge-binding platform carries every custom-domain surface; a platform
    whose edge binds no domain (a loopback platform) carries none. Compares each
    platform with the obligation its own edge derives, so a loopback platform
    correctly carrying neither surface is not a violation, and a platform
    missing a surface it is obligated to is."""
    violations: list[SurfaceViolation] = []
    for platform, platform_facts in sorted(facts.items()):
        expected = _CUSTOM_DOMAIN_SURFACES if platform_facts.binds_domains else frozenset()
        difference = platform_facts.custom_domain_surfaces ^ expected
        if difference:
            declaring = tuple(sorted(p for p, f in facts.items() if f.custom_domain_surfaces))
            violations.append(
                SurfaceViolation(
                    platform, "custom_domain_surfaces", ",".join(sorted(difference)), declaring
                )
            )
    return violations


def surface_violations(facts: Mapping[str, PlatformFacts]) -> list[SurfaceViolation]:
    """Run surfaces 1-7 over the extracted facts and return every violation.

    Raises:
        ValueError: If *facts* has fewer than ``_MIN_PLATFORMS_FOR_COMPARISON``
            entries.
    """
    if len(facts) < _MIN_PLATFORMS_FOR_COMPARISON:
        raise ValueError(
            f"surface_violations requires at least {_MIN_PLATFORMS_FOR_COMPARISON} platforms, "
            f"got {len(facts)} ({sorted(facts)})."
        )
    violations: list[SurfaceViolation] = []
    violations.extend(
        _coverage_gaps(facts, "block_types", lambda f: f.block_types, gap_kind=_GAP_KIND_BLOCK_TYPE)
    )
    violations.extend(
        _coverage_gaps(
            facts,
            "observability_categories",
            _realized_observability_categories,
            gap_kind=_GAP_KIND_OBSERVABILITY,
        )
    )
    violations.extend(_coverage_gaps(facts, "supported_runtimes", _runtime_floor, gap_kind=None))
    violations.extend(
        _coverage_gaps(
            facts, "identity_features", lambda f: f.identity_features, gap_kind=_GAP_KIND_IDENTITY
        )
    )
    violations.extend(_static_web_hosting_gaps(facts))
    violations.extend(_custom_domain_gaps(facts))
    violations.extend(_coverage_gaps(facts, "model_realizations", _model_floor, gap_kind=None))
    return violations


#: Gap kind that accounts for a violation of each coverage surface; a surface
#: absent here has no row kind (nothing can account for it).
_GAP_KIND_BY_SURFACE: Final[Mapping[str, str]] = {
    "block_types": _GAP_KIND_BLOCK_TYPE,
    "observability_categories": _GAP_KIND_OBSERVABILITY,
    "identity_features": _GAP_KIND_IDENTITY,
}


def _accounting_hint(violation: SurfaceViolation) -> str:
    """The exact ``capability_gaps`` row that would account for *violation*, or
    the fix when the surface has no row kind."""
    kind = _GAP_KIND_BY_SURFACE.get(violation.surface)
    if kind is None:
        return "fix the declaration (this surface has no gap-row kind)"
    return (
        f"realize it by at least one implementation, or record the row "
        f"'{kind}:{violation.coordinate}' in the platform's capability_gaps"
    )


# ---------------------------------------------------------------------------
# Non-vacuity self-test (plants facts; constructs no declaration or cell)
# ---------------------------------------------------------------------------

_SELF_TEST_PLATFORM_A: Final[str] = "self_test_platform_a"
_SELF_TEST_PLATFORM_B: Final[str] = "self_test_platform_b"
_SELF_TEST_BLOCK_TYPES: Final[frozenset[str]] = frozenset({"self_test_block_x", "self_test_block_y"})
_SELF_TEST_FEATURES: Final[frozenset[str]] = frozenset({"self_test_feature_x", "self_test_feature_y"})
_SELF_TEST_RUNTIME: Final[str] = "self_test_runtime"
_SELF_TEST_MODEL_PROVIDER: Final[str] = "self_test_model_provider"


def _facts(platform: str, **overrides: object) -> PlatformFacts:
    """A clean baseline platform (every block type, category, feature, runtime and
    model provider present; loopback origin; no edge binding; no custom-domain
    surfaces) with the named facts overridden."""
    baseline = PlatformFacts(
        platform=platform,
        block_types=_SELF_TEST_BLOCK_TYPES,
        gap_surfaces=frozenset(),
        observability={category: frozenset({f"{category}_provider"}) for category in _OBSERVABILITY_CATEGORIES},
        runtimes=frozenset({_SELF_TEST_RUNTIME}),
        identity_features=_SELF_TEST_FEATURES,
        static_hosting_origin=_ORIGIN_LOOPBACK,
        binds_domains=False,
        custom_domain_surfaces=frozenset(),
        model_flavor_counts={_SELF_TEST_MODEL_PROVIDER: 1},
    )
    return dataclasses.replace(baseline, **overrides)


def _pair(**b_overrides: object) -> dict[str, PlatformFacts]:
    """Platform A (clean baseline) and platform B (baseline with overrides)."""
    return {
        _SELF_TEST_PLATFORM_A: _facts(_SELF_TEST_PLATFORM_A),
        _SELF_TEST_PLATFORM_B: _facts(_SELF_TEST_PLATFORM_B, **b_overrides),
    }


def _expect_exactly(
    problems: list[str],
    case: str,
    violations: list[SurfaceViolation],
    expected: list[tuple[str, str, str]],
) -> None:
    """Record a problem unless *violations* is exactly the planted *expected*
    ``(platform, surface, coordinate)`` triples."""
    actual = sorted((v.platform, v.surface, v.coordinate) for v in violations)
    if actual != sorted(expected):
        problems.append(f"self-test [{case}]: expected exactly {sorted(expected)}, got {actual}")


def _self_test_coverage(problems: list[str]) -> None:
    """Criteria 1-3 and 6: capability-level comparison over planted facts."""
    _expect_exactly(problems, "clean pair", surface_violations(_pair()), [])
    absent_block = frozenset({"self_test_block_x"})
    _expect_exactly(
        problems,
        "a whole block type missing, no row",
        surface_violations(_pair(block_types=absent_block)),
        [(_SELF_TEST_PLATFORM_B, "block_types", "self_test_block_y")],
    )
    _expect_exactly(
        problems,
        "a whole block type missing, accounted by its row",
        surface_violations(
            _pair(block_types=absent_block, gap_surfaces=frozenset({"block_type:self_test_block_y"}))
        ),
        [],
    )
    # One flavor missing while another flavor of the same block type is realized:
    # both platforms realize the block type, so the facts are identical -- the old
    # coordinate-level false positive cannot be expressed at this grain.
    _expect_exactly(
        problems,
        "one flavor of a realized block type missing",
        surface_violations(_pair(block_types=_SELF_TEST_BLOCK_TYPES)),
        [],
    )
    emptied = {c: frozenset({"p"}) for c in _OBSERVABILITY_CATEGORIES}
    emptied["tracing"] = frozenset()
    _expect_exactly(
        problems,
        "one observability category empty",
        surface_violations(_pair(observability=emptied)),
        [(_SELF_TEST_PLATFORM_B, "observability_categories", "tracing")],
    )
    renamed = {c: frozenset({f"other_{c}_vendor"}) for c in _OBSERVABILITY_CATEGORIES}
    _expect_exactly(
        problems,
        "different provider names in every category",
        surface_violations(_pair(observability=renamed)),
        [],
    )
    _expect_exactly(
        problems,
        "an identity feature offered through no provider",
        surface_violations(_pair(identity_features=frozenset({"self_test_feature_x"}))),
        [(_SELF_TEST_PLATFORM_B, "identity_features", "self_test_feature_y")],
    )
    _expect_exactly(
        problems,
        "no runtime",
        surface_violations(_pair(runtimes=frozenset())),
        [(_SELF_TEST_PLATFORM_B, "supported_runtimes", _RUNTIME_CAPABILITY)],
    )
    _expect_exactly(
        problems,
        "different runtime names",
        surface_violations(_pair(runtimes=frozenset({"another_runtime"}))),
        [],
    )
    _expect_exactly(
        problems,
        "no model provider with a flavor cell",
        surface_violations(_pair(model_flavor_counts={_SELF_TEST_MODEL_PROVIDER: 0})),
        [(_SELF_TEST_PLATFORM_B, "model_realizations", _MODEL_CAPABILITY)],
    )
    _expect_exactly(
        problems,
        "a different model provider",
        surface_violations(_pair(model_flavor_counts={"another_provider": 2})),
        [],
    )


def _self_test_edge(problems: list[str]) -> None:
    """Criteria 4 and 5: each platform against its own edge."""
    _expect_exactly(
        problems,
        "binding edge with loopback origin",
        surface_violations(_pair(binds_domains=True, custom_domain_surfaces=_CUSTOM_DOMAIN_SURFACES)),
        [(_SELF_TEST_PLATFORM_B, "static_web_hosting", _ORIGIN_LOOPBACK)],
    )
    _expect_exactly(
        problems,
        "domain origin without a binding edge",
        surface_violations(_pair(static_hosting_origin=_ORIGIN_DOMAIN)),
        [(_SELF_TEST_PLATFORM_B, "static_web_hosting", _ORIGIN_DOMAIN)],
    )
    _expect_exactly(
        problems,
        "binding edge with matching origin and both surfaces",
        surface_violations(
            _pair(
                binds_domains=True,
                static_hosting_origin=_ORIGIN_DOMAIN,
                custom_domain_surfaces=_CUSTOM_DOMAIN_SURFACES,
            )
        ),
        [],
    )
    for missing in sorted(_CUSTOM_DOMAIN_SURFACES):
        _expect_exactly(
            problems,
            f"binding edge missing the {missing!r} surface",
            surface_violations(
                _pair(
                    binds_domains=True,
                    static_hosting_origin=_ORIGIN_DOMAIN,
                    custom_domain_surfaces=_CUSTOM_DOMAIN_SURFACES - {missing},
                )
            ),
            [(_SELF_TEST_PLATFORM_B, "custom_domain_surfaces", missing)],
        )
    _expect_exactly(
        problems,
        "loopback edge carrying a surface",
        surface_violations(_pair(custom_domain_surfaces=frozenset({"gateway"}))),
        [(_SELF_TEST_PLATFORM_B, "custom_domain_surfaces", "gateway")],
    )


def _planted_fields(
    required: Sequence[str], optional: Sequence[str]
) -> list[dataclasses.Field[object]]:
    """Field list of a synthetic dataclass with the given required/optional names."""
    spec: list[tuple[str, type] | tuple[str, type, object]] = [(name, int) for name in required]
    spec.extend((name, int, dataclasses.field(default=0)) for name in optional)
    return list(dataclasses.fields(dataclasses.make_dataclass("PlantedFields", spec)))


def _expect_partition_failure(
    problems: list[str], case: str, fields: Sequence[dataclasses.Field[object]], named: str
) -> None:
    """Record a problem unless the guard raises AssertionError naming *named*."""
    try:
        _assert_field_partition_complete(fields)
    except AssertionError as error:
        if named not in str(error):
            problems.append(f"self-test [{case}]: the guard raised without naming {named!r}: {error}")
        return
    problems.append(f"self-test [{case}]: the guard accepted a field list it must reject")


def _self_test_partition(problems: list[str]) -> None:
    """Criterion 7: the partition guard over live and planted field lists."""
    live = dataclasses.fields(PlatformCapabilityDeclaration)
    try:
        _assert_field_partition_complete(live)
    except AssertionError as error:
        problems.append(f"self-test [partition, live declaration]: {error}")
    without_retired = [f for f in live if f.name not in _RETIRED_FIELDS]
    try:
        _assert_field_partition_complete(without_retired)
    except AssertionError as error:
        problems.append(f"self-test [partition, declaration without retired fields]: {error}")
    required = sorted(_REQUIRED_PLATFORM_FACT_FIELDS | set(_REQUIRED_FIELD_OWNERS))
    optional = sorted(_VOCABULARY_SET_FIELDS)
    _expect_partition_failure(
        problems, "unaccounted required", _planted_fields([*required, "self_test_required"], optional),
        "self_test_required",
    )
    _expect_partition_failure(
        problems, "unaccounted optional", _planted_fields(required, [*optional, "self_test_optional"]),
        "self_test_optional",
    )
    _expect_partition_failure(
        problems, "stale bucket name", _planted_fields(required, optional[1:]), optional[0]
    )
    doubly_claimed = _partition_problems(
        {"self_test_field"},
        (("X", frozenset({"self_test_field"})), ("Y", frozenset({"self_test_field"}))),
        frozenset(),
    )
    if not any("more than one bucket" in p and "self_test_field" in p for p in doubly_claimed):
        problems.append(
            f"self-test [doubly claimed]: a field in two buckets was not reported: {doubly_claimed}"
        )


def run_self_test() -> list[str]:
    """Prove each comparison detects a planted divergence and stays silent on a
    clean or merely-different-vocabulary pair, before any real comparison is
    trusted.

    Returns:
        A list of failure descriptions -- empty means the comparators are sound.
    """
    problems: list[str] = []
    _self_test_coverage(problems)
    _self_test_edge(problems)
    _self_test_partition(problems)
    try:
        surface_violations({_SELF_TEST_PLATFORM_A: _facts(_SELF_TEST_PLATFORM_A)})
    except ValueError:
        return problems
    problems.append("self-test [one platform]: a single-platform comparison did not raise")
    return problems


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

#: Surfaces a live run unions over: each must have at least one realizing
#: platform, or the comparison is vacuous.
_LIVE_UNION_SURFACES: Final[tuple[tuple[str, Callable[[PlatformFacts], frozenset[str]]], ...]] = (
    ("block_types", lambda f: f.block_types),
    ("observability_categories", _realized_observability_categories),
    ("identity_features", lambda f: f.identity_features),
    ("supported_runtimes", _runtime_floor),
    ("model_realizations", _model_floor),
)


def _vacuous_live_surfaces(facts: Mapping[str, PlatformFacts]) -> list[str]:
    """Surfaces whose live union is empty (a comparison over nothing)."""
    return [
        surface
        for surface, realized in _LIVE_UNION_SURFACES
        if not any(realized(platform_facts) for platform_facts in facts.values())
    ]


def check_block_realization_parity() -> int:
    """Run the real gate over every installed platform.

    Returns:
        Exit code (0 = every capability is realized or carries its gap row,
        1 = at least one violation, 2 = fewer than
        ``_MIN_PLATFORMS_FOR_COMPARISON`` platforms registered or a vacuous
        live comparison).
    """
    platforms = sorted(registered_platform_names())
    if len(platforms) < _MIN_PLATFORMS_FOR_COMPARISON:
        logger.error(
            "D1 CANNOT RUN: only %d platform(s) registered (%s) -- at least "
            "%d are required. Fix: install the missing datrix-codegen-<x> "
            "platform package(s) into D:\\datrix\\.venv.",
            len(platforms), platforms, _MIN_PLATFORMS_FOR_COMPARISON,
        )
        return 2

    facts = {name: extract_facts(name, declaration_for_provider(name)) for name in platforms}
    vacuous = _vacuous_live_surfaces(facts)
    if vacuous:
        logger.error(
            "D1 CANNOT RUN: the live platforms realize nothing on surface(s) %s, so the "
            "comparison would be vacuous. Fix: check the extractor against the declarations.",
            vacuous,
        )
        return 2

    violations = surface_violations(facts)
    for v in violations:
        logger.error(
            "VIOLATION platform=%s surface=%s capability=%s (realized by: %s) -- %s",
            v.platform, v.surface, v.coordinate, ", ".join(v.declaring_platforms),
            _accounting_hint(v),
        )
    if violations:
        by_surface: dict[str, int] = {}
        for v in violations:
            by_surface[v.surface] = by_surface.get(v.surface, 0) + 1
        logger.error(
            "D1 VIOLATION: %d platform-capability gap(s) across %d surface(s): %s.",
            len(violations), len(by_surface), by_surface,
        )
        return 1

    logger.info(
        "D1 holds: every capability realized by any of %d platforms (%s) is realized by "
        "all of them, and each platform's static hosting and custom-domain surfaces match "
        "its own edge.",
        len(platforms), platforms,
    )
    return 0


def main() -> int:
    """Entry point.

    Returns:
        Exit code: 0 = D1 holds, 1 = a violation was found, 2 = the partition
        guard or self-test failed or fewer than 2 platforms are registered.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Prove every installed datrix.platforms plugin realizes every capability any "
            "platform realizes -- across the seven capability surfaces (block types, "
            "observability categories, runtime floor, identity features, static web hosting, "
            "custom-domain surfaces, model realizations) -- or carries its own gap row."
        ),
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run only the non-vacuity self-test and skip the real comparison",
    )
    args = parser.parse_args()

    configure_logging(debug=args.debug)

    try:
        _assert_field_partition_complete(dataclasses.fields(PlatformCapabilityDeclaration))
    except AssertionError as e:
        logger.error("FIELD PARTITION CHECK FAILED: %s", e)
        return 2

    try:
        problems = run_self_test()
    except Exception as e:  # noqa: BLE001 -- reported, never swallowed
        logger.error("Non-vacuity self-test raised unexpectedly: %s", e)
        return 2
    if problems:
        logger.error("Non-vacuity self-test FAILED:")
        for p in problems:
            logger.error("  %s", p)
        return 2
    logger.info("Non-vacuity self-test passed.")

    if args.self_test:
        return 0

    return check_block_realization_parity()


if __name__ == "__main__":
    sys.exit(main())
