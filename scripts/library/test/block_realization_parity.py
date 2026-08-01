"""Cross-platform capability-declaration parity gate (D1).

Every installed ``datrix.platforms`` plugin declares a
``PlatformCapabilityDeclaration`` (``datrix_common.plugin.capability``) --
the platform-axis counterpart of the language-axis
``supported_domain_parity.py`` gate. That declaration is consumed by
production capability resolution and by each platform package's own kit
CI, but until this gate, no repo-level script ever compared declarations
ACROSS platforms: a ``(block_type, flavor)`` cell one platform realizes and
another has never even considered was invisible to every existing check.

This gate computes the UNION of every capability coordinate any installed
platform declares, across SEVEN surfaces, and fails loud if another
installed platform has made no decision at all about that coordinate --
unless the gap is a reviewed, typed entry in
``datrix/scripts/config/platform-capability-holes.json``.

THE SEVEN SURFACES:

1. ``block_realizations`` -- ``(block_type, flavor)`` cells.
2. ``supported_secret_backends`` -- a per-platform value set.
3. ``native_observability_providers`` -- a per-platform value set, PER
   CATEGORY (metrics/tracing/logging/visualization/alerting).
4. ``supported_runtimes`` -- a per-platform value set.
5. Identity ``(provider_type, feature)`` cells (``identity_feature_realizations``,
   gated by ``identity_provider_realizations``).
6. Every remaining optional scalar/mapping field on the declaration --
   derived MECHANICALLY from ``dataclasses.fields()`` (see
   ``_assert_scalar_field_partition_complete`` below) rather than
   hand-listed, so a future field addition to
   ``PlatformCapabilityDeclaration`` cannot silently slip past every
   surface unchecked.
7. ``unrealizable_surfaces`` -- ``{surface_name: reason}``.

Target set is NEVER hardcoded: platforms are enumerated from the installed
``datrix.platforms`` entry points at run time
(:func:`~shared.registered_targets.registered_platform_names`).
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Final

# Add library directory to sys.path to import from shared (this file lives at
# library/test/, shared/ lives at the sibling library/shared/).
_LIBRARY_DIR = Path(__file__).resolve().parent.parent
if _LIBRARY_DIR.exists() and str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from shared.registered_targets import registered_platform_names  # noqa: E402

from datrix_common.config.serverless.models import ServerlessPlatform  # noqa: E402
from datrix_common.deployment.cache_connection_identity import CacheConnectionIdentity  # noqa: E402
from datrix_common.deployment.rdbms_connection_identity import RdbmsConnectionIdentity  # noqa: E402
from datrix_common.deployment.secret_backend import SecretBackend  # noqa: E402
from datrix_common.deployment.signing_backend import SigningBackend  # noqa: E402
from datrix_common.plugin.capability import (  # noqa: E402
    BlockRealization,
    PlatformCapabilityDeclaration,
)
from datrix_common.plugin.capability_resolution import declaration_for_provider  # noqa: E402
from datrix_common.plugin.identity import RuntimeId  # noqa: E402

logger = logging.getLogger(__name__)

_HERE = Path(__file__).resolve()
#: This file lives at <datrix>/scripts/library/test/block_realization_parity.py --
#: parents[3] is <datrix> (the datrix package root: parents[0]=.../library/test,
#: [1]=.../library, [2]=.../scripts, [3]=<datrix>).
DATRIX_DIR: Path = _HERE.parents[3]
HOLES_PATH: Path = DATRIX_DIR / "scripts" / "config" / "platform-capability-holes.json"

#: A cross-platform comparison over 0 or 1 platform is vacuous.
_MIN_PLATFORMS_FOR_COMPARISON: Final[int] = 2

_OBSERVABILITY_CATEGORIES: Final[tuple[str, ...]] = (
    "metrics", "tracing", "logging", "visualization", "alerting",
)

#: Optional/defaulted PlatformCapabilityDeclaration fields already owned by
#: one of the SIX NAMED surfaces above (never re-checked generically as a
#: "surface 6 scalar" -- each has its own dedicated comparison function).
_SURFACE_OWNED_OPTIONAL_FIELDS: Final[frozenset[str]] = frozenset({
    "native_observability_providers",   # surface 3
    "identity_provider_realizations",   # surface 5
    "identity_feature_realizations",    # surface 5
    "unrealizable_surfaces",            # surface 7
})

#: Surface-6 optional fields compared by PER-VALUE union membership (the
#: field is itself a set/mapping of discrete values -- a MAPPING is compared
#: by its KEY set, e.g. "which channels does native_notification_vendors
#: name", never its values).
_SET_SHAPED_SCALAR_FIELDS: Final[tuple[str, ...]] = (
    "supported_config_stores",
    "container_scaffold_runtimes",
    "platform_allowed_host_patterns",
    "native_cloud_helper_packages",
    "native_notification_vendors",
    "supported_gateway_types",
    "injected_test_identity_providers",
)

#: Surface-6 optional fields compared by WHOLE-VALUE truthy/non-None
#: presence (a bare bool, an Optional[str], or an Optional[dataclass] --
#: there is no natural "per-member" grain to compare).
_PRESENCE_SHAPED_SCALAR_FIELDS: Final[tuple[str, ...]] = (
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
)

#: Fields that carry an explanatory RATIONALE for another field's already-
#: compared value rather than an independent per-platform capability
#: coordinate of their own. ``declared_capability_reasons`` maps
#: ``{field_name: reason}`` for OTHER fields on this same dataclass (see its
#: docstring) -- its own key set is "which fields did this platform bother
#: to explain," which is not a capability fact and is not comparable across
#: platforms: a platform that never deviates from a field's default has
#: nothing to explain and correctly has no key for it, while a platform that
#: does deviate is already caught by that field's own surface (e.g.
#: ``gateway_terminates_tls`` via ``_PRESENCE_SHAPED_SCALAR_FIELDS``).
#: Requiring every platform to also carry a matching reasons-map key would
#: manufacture busywork violations with no capability-parity meaning.
#: ``declared_set_exclusions`` is the same shape of thing one level up: a
#: ``{surface: {coordinate: reason}}`` rationale for why a SET-SHAPED
#: surface's coordinate is intentionally absent, consulted (via
#: ``_is_set_excluded``) by the comparison functions of the surfaces it
#: covers rather than compared as an independent coordinate set of its own.
#: Deliberately its own bucket (not folded into ``_SURFACE_OWNED_OPTIONAL_FIELDS``,
#: which is reserved for fields with a real dedicated comparison function) so
#: it stays a reviewed, explicit exclusion rather than a silent catch-all.
_EXPLANATORY_METADATA_FIELDS: Final[frozenset[str]] = frozenset({
    "declared_capability_reasons",
    "declared_set_exclusions",
})


def configure_logging(debug: bool = False) -> None:
    """Configure logging output."""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def _assert_scalar_field_partition_complete() -> None:
    """Fail loud if a NEW optional field was added to the dataclass and
    triaged into none of the three buckets above.

    This is the mechanical guard against the exact failure mode this gate
    exists to prevent: a future field lands on
    ``PlatformCapabilityDeclaration`` and silently escapes every surface.
    Every OPTIONAL field (one with a default) must be a member of EXACTLY
    ONE of: ``_SURFACE_OWNED_OPTIONAL_FIELDS``, ``_SET_SHAPED_SCALAR_FIELDS``,
    ``_PRESENCE_SHAPED_SCALAR_FIELDS``.

    Raises:
        AssertionError: If any optional field is unaccounted for, or is
            claimed by more than one bucket.
    """
    optional_fields = {
        f.name
        for f in dataclasses.fields(PlatformCapabilityDeclaration)
        if f.default is not dataclasses.MISSING
        or f.default_factory is not dataclasses.MISSING
    }
    buckets = (
        _SURFACE_OWNED_OPTIONAL_FIELDS,
        frozenset(_SET_SHAPED_SCALAR_FIELDS),
        frozenset(_PRESENCE_SHAPED_SCALAR_FIELDS),
        _EXPLANATORY_METADATA_FIELDS,
    )
    accounted: set[str] = set()
    overlaps: set[str] = set()
    for bucket in buckets:
        overlaps |= accounted & bucket
        accounted |= bucket
    missing = optional_fields - accounted
    extra = accounted - optional_fields
    if missing or extra or overlaps:
        raise AssertionError(
            "PlatformCapabilityDeclaration's optional-field partition is "
            f"incomplete or wrong. Unaccounted-for fields (add to a bucket "
            f"in block_realization_parity.py): {sorted(missing)}. Stale "
            f"field names naming nothing on the dataclass (remove): "
            f"{sorted(extra)}. Fields claimed by more than one bucket "
            f"(fix -- exactly one bucket each): {sorted(overlaps)}."
        )


@dataclasses.dataclass(frozen=True)
class SurfaceViolation:
    """One (platform, surface, coordinate) gap: the platform makes no
    decision at all about a coordinate at least one OTHER installed
    platform declares."""

    platform: str
    surface: str
    coordinate: str
    declaring_platforms: tuple[str, ...]


def _is_set_excluded(
    decl: PlatformCapabilityDeclaration, surface: str, coordinate: str
) -> bool:
    """True when *decl* declares *coordinate* an intentional exclusion for
    *surface* via ``declared_set_exclusions`` -- widens what counts as
    "declared" without requiring any platform to populate the field."""
    return coordinate in decl.declared_set_exclusions.get(surface, {})


def _block_realization_gaps(
    per_platform: dict[str, PlatformCapabilityDeclaration],
) -> list[SurfaceViolation]:
    """Surface 1: union of ``(block_type, flavor)`` keys vs. each platform's
    own ``block_realizations`` dict. Presence as a KEY (regardless of the
    ``supported`` bool) counts as "declared" -- ``BlockRealization`` already
    forces a reason on ``supported=False``, so a present key is always a
    real decision. A coordinate keyed under this platform's own
    ``declared_set_exclusions["block_realizations"]`` also counts as
    declared."""
    union: dict[str, set[str]] = {}
    for platform, decl in per_platform.items():
        for block_type, flavor in decl.block_realizations:
            union.setdefault(f"{block_type}:{flavor}", set()).add(platform)

    violations: list[SurfaceViolation] = []
    for coordinate, declaring in union.items():
        block_type, _, flavor = coordinate.partition(":")
        for platform, decl in per_platform.items():
            if (block_type, flavor) not in decl.block_realizations and not _is_set_excluded(
                decl, "block_realizations", coordinate
            ):
                violations.append(
                    SurfaceViolation(
                        platform, "block_realizations", coordinate, tuple(sorted(declaring))
                    )
                )
    return violations


def _value_set_gaps(
    per_platform: dict[str, PlatformCapabilityDeclaration],
    surface: str,
    values_for: Callable[[PlatformCapabilityDeclaration], set[str]],
    *,
    exclusion_surface: str | None,
) -> list[SurfaceViolation]:
    """Generic per-value-union gap check for a plain set/mapping-keys-shaped
    field. Shared by surfaces 2, 3 (per category), 4, 5, 7, and the
    surface-6 SET_SHAPED fields.

    *exclusion_surface* is the ``declared_set_exclusions`` key a platform
    may declare a coordinate under to widen "declared" without actually
    holding the value -- ``None`` for surfaces
    ``PlatformCapabilityDeclaration`` does not support exclusions for
    (identity feature cells: absence there is already a permanent,
    self-explaining structural fact)."""
    union: dict[str, set[str]] = {}
    per_platform_values = {p: values_for(d) for p, d in per_platform.items()}
    for platform, values in per_platform_values.items():
        for value in values:
            union.setdefault(value, set()).add(platform)

    violations: list[SurfaceViolation] = []
    for coordinate, declaring in union.items():
        for platform, values in per_platform_values.items():
            if coordinate in values:
                continue
            if exclusion_surface and _is_set_excluded(
                per_platform[platform], exclusion_surface, coordinate
            ):
                continue
            violations.append(
                SurfaceViolation(platform, surface, coordinate, tuple(sorted(declaring)))
            )
    return violations


def _secret_backend_gaps(
    per_platform: dict[str, PlatformCapabilityDeclaration],
) -> list[SurfaceViolation]:
    """Surface 2."""
    return _value_set_gaps(
        per_platform,
        "supported_secret_backends",
        lambda d: {b.value for b in d.supported_secret_backends},
        exclusion_surface="supported_secret_backends",
    )


def _observability_gaps(
    per_platform: dict[str, PlatformCapabilityDeclaration],
) -> list[SurfaceViolation]:
    """Surface 3 -- one independent union PER CATEGORY. A metrics-only value
    must never be compared against the tracing set."""
    violations: list[SurfaceViolation] = []
    for category in _OBSERVABILITY_CATEGORIES:
        def _values_for_category(
            d: PlatformCapabilityDeclaration, category: str = category
        ) -> set[str]:
            return set(d.native_observability_providers.get(category, frozenset()))

        category_violations = _value_set_gaps(
            per_platform,
            f"native_observability_providers:{category}",
            _values_for_category,
            exclusion_surface=f"native_observability_providers:{category}",
        )
        violations.extend(category_violations)
    return violations


def _runtime_gaps(
    per_platform: dict[str, PlatformCapabilityDeclaration],
) -> list[SurfaceViolation]:
    """Surface 4."""
    return _value_set_gaps(
        per_platform,
        "supported_runtimes",
        lambda d: {r.value for r in d.supported_runtimes},
        exclusion_surface="supported_runtimes",
    )


def _identity_feature_gaps(
    per_platform: dict[str, PlatformCapabilityDeclaration],
) -> list[SurfaceViolation]:
    """Surface 5: union of ``(provider_type, feature)`` keys across every
    platform's ``identity_feature_realizations``. A provider type a platform
    does not realize AT ALL (absent from its own ``identity_provider_realizations``)
    structurally cannot have any feature cells for it either -- every one of
    that provider's feature coordinates is reported as a gap for that
    platform, which is the correct, literal reading of D1's "identity
    (provider_type, feature) cells" grain. No exclusion mechanism: absence
    here is already a permanent, self-explaining structural fact -- see
    `_value_set_gaps`."""
    return _value_set_gaps(
        per_platform,
        "identity_feature_realizations",
        lambda d: {f"{p}:{f}" for (p, f) in d.identity_feature_realizations},
        exclusion_surface=None,
    )


def _unrealizable_surface_gaps(
    per_platform: dict[str, PlatformCapabilityDeclaration],
) -> list[SurfaceViolation]:
    """Surface 7."""
    return _value_set_gaps(
        per_platform,
        "unrealizable_surfaces",
        lambda d: set(d.unrealizable_surfaces),
        exclusion_surface="unrealizable_surfaces",
    )


def _scalar_set_shaped_gaps(
    per_platform: dict[str, PlatformCapabilityDeclaration],
) -> list[SurfaceViolation]:
    """Surface 6a: the SET_SHAPED optional fields, per-value union."""
    violations: list[SurfaceViolation] = []
    for field_name in _SET_SHAPED_SCALAR_FIELDS:
        def _values(d: PlatformCapabilityDeclaration, fname: str = field_name) -> set[str]:
            raw = getattr(d, fname)
            if isinstance(raw, dict):
                return {str(k) for k in raw}
            return {str(v) for v in raw}
        violations.extend(
            _value_set_gaps(
                per_platform,
                f"scalar:{field_name}",
                _values,
                exclusion_surface=f"scalar:{field_name}",
            )
        )
    return violations


def _scalar_presence_shaped_gaps(
    per_platform: dict[str, PlatformCapabilityDeclaration],
) -> list[SurfaceViolation]:
    """Surface 6b: the PRESENCE_SHAPED optional fields. ``coordinate`` is the
    bare field name (there is only one boolean/None-ness question per
    field, not a per-member set).

    "Declared" means the platform's value DIFFERS from the dataclass
    default -- never bare Python truthiness. Most presence-shaped fields
    default to ``False``/``None``, where truthiness and "differs from
    default" happen to coincide, but a field could in principle default
    to a truthy value, where a meaningful, explicit deviation would be
    falsy: truthiness alone would treat that real, declared fact as
    indistinguishable from never having been declared at all. Comparing
    against the field's own default -- read mechanically via
    ``dataclasses.fields()``, not hand-encoded -- is correct for every
    default polarity a field might use.

    ``gateway_terminates_tls`` is the reason this field needed an
    ``Optional[bool]`` rather than a plain ``bool``: a plain bool's
    default is itself a valid declared value (``True``), so an
    undeclared platform (implicitly defaulting) and a platform that
    explicitly confirmed the default-coinciding fact were both
    indistinguishable ``True`` -- no comparison against the default
    could ever separate them. ``None`` closes that gap: it is a value
    no explicit declaration ever produces, so "differs from default"
    is finally equivalent to "was actually declared."

    A field left at its default is ALSO treated as declared when the
    platform names it in ``declared_capability_reasons`` -- an explicit,
    reviewed rationale for staying at the default (e.g. "this platform has
    no CDN cache-invalidation SDK") is itself a real decision, not an
    oversight, even though the value alone is indistinguishable from never
    having been considered.
    """
    field_defaults = {
        f.name: f.default
        for f in dataclasses.fields(PlatformCapabilityDeclaration)
        if f.name in _PRESENCE_SHAPED_SCALAR_FIELDS
    }
    violations: list[SurfaceViolation] = []
    for field_name in _PRESENCE_SHAPED_SCALAR_FIELDS:
        default = field_defaults[field_name]
        declaring_platforms = {
            p for p, d in per_platform.items() if getattr(d, field_name) != default
        }
        if not declaring_platforms:
            continue
        for platform, decl in per_platform.items():
            if (
                getattr(decl, field_name) == default
                and field_name not in decl.declared_capability_reasons
            ):
                violations.append(
                    SurfaceViolation(
                        platform, "scalar", field_name, tuple(sorted(declaring_platforms))
                    )
                )
    return violations


def all_surface_violations(
    per_platform: dict[str, PlatformCapabilityDeclaration],
) -> list[SurfaceViolation]:
    """Run all seven surfaces' comparisons and return every violation.

    Raises:
        ValueError: If *per_platform* has fewer than
            ``_MIN_PLATFORMS_FOR_COMPARISON`` entries.
    """
    if len(per_platform) < _MIN_PLATFORMS_FOR_COMPARISON:
        raise ValueError(
            f"all_surface_violations requires at least "
            f"{_MIN_PLATFORMS_FOR_COMPARISON} platforms, got {len(per_platform)} "
            f"({sorted(per_platform)})."
        )
    violations: list[SurfaceViolation] = []
    violations.extend(_block_realization_gaps(per_platform))
    violations.extend(_secret_backend_gaps(per_platform))
    violations.extend(_observability_gaps(per_platform))
    violations.extend(_runtime_gaps(per_platform))
    violations.extend(_identity_feature_gaps(per_platform))
    violations.extend(_scalar_set_shaped_gaps(per_platform))
    violations.extend(_scalar_presence_shaped_gaps(per_platform))
    violations.extend(_unrealizable_surface_gaps(per_platform))
    return violations


# ---------------------------------------------------------------------------
# Exemption file
# ---------------------------------------------------------------------------


def load_holes() -> tuple[dict[tuple[str, str, str], str], int]:
    """Load and validate ``platform-capability-holes.json``.

    Returns:
        ``({(platform, surface, coordinate): reason}, expected_count)``.

    Raises:
        ValueError: If the file is missing, malformed, an entry has an
            empty reason, or the entry count does not match the pinned
            ``expected_count``.
    """
    if not HOLES_PATH.exists():
        raise ValueError(
            f"Missing exemption file {HOLES_PATH}. It pins the catalogued "
            f"platform-capability holes. Restore it from git; the gate "
            f"never creates it."
        )
    data = json.loads(HOLES_PATH.read_text(encoding="utf-8"))
    entries = data.get("holes")
    expected = data.get("expected_count")
    if not isinstance(entries, list) or not isinstance(expected, int):
        raise ValueError(
            f"Malformed exemption file {HOLES_PATH}: expected an object "
            f"with 'expected_count' (int) and 'holes' (array of "
            f"{{platform, surface, coordinate, reason}})."
        )
    holes: dict[tuple[str, str, str], str] = {}
    for entry in entries:
        for key in ("platform", "surface", "coordinate", "reason"):
            if not isinstance(entry.get(key), str) or not entry[key].strip():
                raise ValueError(
                    f"Exemption entry {entry!r} is missing a non-empty "
                    f"{key!r}."
                )
        holes[(entry["platform"], entry["surface"], entry["coordinate"])] = entry["reason"]
    if len(entries) != expected:
        raise ValueError(
            f"Exemption file {HOLES_PATH} has {len(entries)} entries but "
            f"'expected_count' is pinned at {expected}. Update the count in "
            f"the same change that adds or removes an entry."
        )
    return holes, expected


# ---------------------------------------------------------------------------
# Non-vacuity self-test
# ---------------------------------------------------------------------------

_SELF_TEST_PLATFORM_A: Final[str] = "self_test_platform_a"
_SELF_TEST_PLATFORM_B: Final[str] = "self_test_platform_b"
_SELF_TEST_FORCED_GAP_FLAVOR: Final[str] = "self_test_forced_gap_flavor"


def _synthetic_declaration(
    platform_label: str,
    *,
    extra_flavor: str | None = None,
    set_exclusions: dict[str, dict[str, str]] | None = None,
) -> PlatformCapabilityDeclaration:
    """A minimal, valid ``PlatformCapabilityDeclaration`` for the self-test
    only -- never a stand-in for a real platform."""
    block_realizations = {
        ("rdbms", "container"): BlockRealization(
            supported=True, structural_pattern="*/infra/rdbms/container/*.py"
        )
    }
    if extra_flavor:
        block_realizations[("rdbms", extra_flavor)] = BlockRealization(
            supported=True, structural_pattern=f"*/infra/rdbms/{extra_flavor}/*.py"
        )
    return PlatformCapabilityDeclaration(
        platform_label=platform_label,
        default_secret_backend=SecretBackend.FILE,
        crypto_signing_backend=SigningBackend.LOCAL_KEY,
        rdbms_connection_identity=RdbmsConnectionIdentity.PASSWORD,
        cache_connection_identity=CacheConnectionIdentity.PASSWORD,
        supported_secret_backends=frozenset({SecretBackend.FILE}),
        supported_runtimes=frozenset({RuntimeId("self-test-runtime")}),
        serverless_compute_model=ServerlessPlatform.CONTAINER,
        block_realizations=block_realizations,
        declared_set_exclusions=set_exclusions or {},
    )


def run_self_test() -> list[str]:
    """Prove the comparator detects a real, forced divergence before any
    real comparison is trusted.

    Matching pair (identical declarations save for `platform_label`) must
    report zero violations. Mismatched pair (platform A declares one extra
    `(rdbms, self_test_forced_gap_flavor)` cell platform B never
    considered) must report exactly one violation naming platform B and
    that coordinate.

    Returns:
        A list of failure descriptions -- empty means the comparator is sound.
    """
    problems: list[str] = []

    matching = {
        _SELF_TEST_PLATFORM_A: _synthetic_declaration("A"),
        _SELF_TEST_PLATFORM_B: _synthetic_declaration("B"),
    }
    matching_violations = all_surface_violations(matching)
    if matching_violations:
        problems.append(
            f"self-test: a synthetic MATCHING pair reported "
            f"{len(matching_violations)} violation(s) -- the comparator is "
            f"over-triggering: {matching_violations}"
        )

    mismatched = {
        _SELF_TEST_PLATFORM_A: _synthetic_declaration(
            "A", extra_flavor=_SELF_TEST_FORCED_GAP_FLAVOR
        ),
        _SELF_TEST_PLATFORM_B: _synthetic_declaration("B"),
    }
    mismatched_violations = all_surface_violations(mismatched)
    forced_gap_hits = [
        v
        for v in mismatched_violations
        if v.platform == _SELF_TEST_PLATFORM_B
        and v.surface == "block_realizations"
        and v.coordinate == f"rdbms:{_SELF_TEST_FORCED_GAP_FLAVOR}"
    ]
    if not forced_gap_hits:
        problems.append(
            f"self-test: a synthetic platform plugin missing one union cell "
            f"did not fail -- expected a block_realizations violation for "
            f"{_SELF_TEST_PLATFORM_B!r} at coordinate "
            f"'rdbms:{_SELF_TEST_FORCED_GAP_FLAVOR}', got: "
            f"{mismatched_violations}"
        )
    a_hits = [v for v in mismatched_violations if v.platform == _SELF_TEST_PLATFORM_A]
    if a_hits:
        problems.append(
            f"self-test: platform A (the one that DECLARED the extra cell) "
            f"was itself reported missing something -- asymmetric/wrong "
            f"comparator: {a_hits}"
        )

    forced_gap_coordinate = f"rdbms:{_SELF_TEST_FORCED_GAP_FLAVOR}"

    excluded = {
        _SELF_TEST_PLATFORM_A: _synthetic_declaration(
            "A", extra_flavor=_SELF_TEST_FORCED_GAP_FLAVOR
        ),
        _SELF_TEST_PLATFORM_B: _synthetic_declaration(
            "B",
            set_exclusions={
                "block_realizations": {
                    forced_gap_coordinate: "self-test: intentionally absent"
                }
            },
        ),
    }
    excluded_violations = all_surface_violations(excluded)
    excluded_gap_hits = [
        v
        for v in excluded_violations
        if v.platform == _SELF_TEST_PLATFORM_B
        and v.surface == "block_realizations"
        and v.coordinate == forced_gap_coordinate
    ]
    if excluded_gap_hits:
        problems.append(
            f"self-test: platform B declared the forced-gap coordinate "
            f"{forced_gap_coordinate!r} in declared_set_exclusions but the "
            f"comparator still reported it as a violation -- an exclusion "
            f"must satisfy the gap: {excluded_gap_hits}"
        )

    bogus_excluded = {
        _SELF_TEST_PLATFORM_A: _synthetic_declaration(
            "A", extra_flavor=_SELF_TEST_FORCED_GAP_FLAVOR
        ),
        _SELF_TEST_PLATFORM_B: _synthetic_declaration(
            "B",
            set_exclusions={
                "block_realizations": {
                    "rdbms:some_other_flavor_entirely": "self-test: wrong coordinate"
                }
            },
        ),
    }
    bogus_excluded_violations = all_surface_violations(bogus_excluded)
    bogus_excluded_gap_hits = [
        v
        for v in bogus_excluded_violations
        if v.platform == _SELF_TEST_PLATFORM_B
        and v.surface == "block_realizations"
        and v.coordinate == forced_gap_coordinate
    ]
    if not bogus_excluded_gap_hits:
        problems.append(
            "self-test: platform B declared an exclusion for an unrelated "
            f"coordinate ('rdbms:some_other_flavor_entirely'), which must NOT "
            f"satisfy the real gap at {forced_gap_coordinate!r} -- the "
            f"comparator swallowed the violation anyway: {bogus_excluded_violations}"
        )

    return problems


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def check_block_realization_parity() -> int:
    """Run the real gate over every installed platform.

    Returns:
        Exit code (0 = every union coordinate is declared or exempted,
        1 = at least one unexempted gap, 2 = fewer than
        ``_MIN_PLATFORMS_FOR_COMPARISON`` platforms registered).
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

    per_platform = {name: declaration_for_provider(name) for name in platforms}
    holes, _ = load_holes()
    violations = all_surface_violations(per_platform)

    unexempted = [
        v for v in violations
        if (v.platform, v.surface, v.coordinate) not in holes
    ]

    for v in violations:
        exempted = (v.platform, v.surface, v.coordinate) in holes
        marker = "EXEMPTED" if exempted else "VIOLATION"
        logger.info(
            "%s platform=%s surface=%s coordinate=%s (declared by: %s)",
            marker, v.platform, v.surface, v.coordinate, ", ".join(v.declaring_platforms),
        )

    if unexempted:
        by_surface: dict[str, int] = {}
        for v in unexempted:
            by_surface[v.surface] = by_surface.get(v.surface, 0) + 1
        logger.error(
            "D1 VIOLATION: %d unexempted platform-capability gap(s) across "
            "%d surface(s): %s. Add a reviewed entry to %s (with a real "
            "reason) or fix the declaration.",
            len(unexempted), len(by_surface), by_surface, HOLES_PATH,
        )
        return 1

    logger.info(
        "D1 holds: every union coordinate across %d platforms (%s) is "
        "declared or exempted. %d total gap(s), all covered by %s.",
        len(platforms), platforms, len(violations), HOLES_PATH,
    )
    return 0


def main() -> int:
    """Entry point.

    Returns:
        Exit code: 0 = D1 holds, 1 = an unexempted gap was found, 2 = the
        self-test failed or fewer than 2 platforms are registered.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Prove every installed datrix.platforms plugin's declared "
            "capability coordinates -- across all seven capability surfaces "
            "-- are complete relative to the union all platforms declare "
            "(D1)."
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
        _assert_scalar_field_partition_complete()
    except AssertionError as e:
        logger.error("SCALAR-FIELD PARTITION CHECK FAILED: %s", e)
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
