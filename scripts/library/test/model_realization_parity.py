"""Model-realization capability-declaration parity gate.

Every installed ``datrix.platforms`` plugin declares a ``PlatformCapabilityDeclaration``
carrying a REQUIRED ``model_realizations`` mapping -- one ``ModelRealization`` per provider
(API family) the platform realizes, whose ``flavors`` is a per-flavor mapping
``Mapping[str, ModelFlavorCell]``: each declared placement carries ITS
OWN ``schema_constrained_output``/``pricing``/``managed_keys``/``managed_transport`` -- nothing
is inherited from the provider level or from another flavor's cell.

``ModelRealization`` itself already rejects an out-of-domain flavor key, and an inconsistent
managed/non-managed cell, at construction time
(``datrix_common.plugin.model_realization.ModelRealization.__post_init__``). This gate exists
for the class of defect that construction-time check CANNOT catch, because neither
``PlatformCapabilityDeclaration.model_realizations`` nor a ``ModelRealization.flavors`` value is
runtime-typechecked against installed third-party plugins: a plugin's declared realization or
flavor cell can be any object that merely looks right, and a genuine ``ModelFlavorCell`` can
carry a ``schema_constrained_output`` that was never really stated (Python does not enforce
``Literal`` membership at construction time). This gate proves the SHAPE of every installed
platform's ``model_realizations`` mapping: every flavor key is in the closed placement domain,
every cell is a real ``ModelFlavorCell`` with every dataclass field present, and every cell's
``schema_constrained_output`` is one of the closed literal modes -- each check catching a defect
none of the others, nor ``ModelRealization``'s own validation, would.

The platform set is never hardcoded: it is enumerated from the installed ``datrix.platforms``
entry points at run time via ``shared.registered_targets.registered_platform_names``.
"""

from __future__ import annotations

import argparse
import dataclasses
import logging
import sys
from pathlib import Path
from typing import Final, get_args

_LIBRARY_DIR = Path(__file__).resolve().parent.parent
if _LIBRARY_DIR.exists() and str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from shared.registered_targets import registered_platform_names  # noqa: E402

from datrix_common.config.serverless.models import ServerlessPlatform  # noqa: E402
from datrix_common.deployment.cache_connection_identity import CacheConnectionIdentity  # noqa: E402
from datrix_common.deployment.rdbms_connection_identity import RdbmsConnectionIdentity  # noqa: E402
from datrix_common.deployment.secret_backend import SecretBackend  # noqa: E402
from datrix_common.deployment.signing_backend import SigningBackend  # noqa: E402
from datrix_common.plugin.capability import (
    # noqa: E402
    BlockRealization,
    DeployableConstruct,
    PlatformCapabilityDeclaration,
)
from datrix_common.plugin.capability_resolution import declaration_for_provider  # noqa: E402
from datrix_common.plugin.identity import RuntimeId  # noqa: E402
from datrix_common.plugin.model_realization import (
    # noqa: E402
    ModelFlavorCell,
    ModelRealization,
    SchemaConstrainedOutputMode,
)

logger = logging.getLogger(__name__)

#: A comparison over 0 or 1 platform is vacuous (mirrors block_realization_parity).
_MIN_PLATFORMS_FOR_COMPARISON: Final[int] = 2

#: The closed placement domain a ``ModelRealization.flavors`` entry may name.
_VALID_FLAVORS: Final[frozenset[str]] = frozenset({"container", "external", "managed", "direct"})

#: The closed set of legal ``ModelFlavorCell.schema_constrained_output`` values, derived from the
#: real ``Literal`` alias rather than hand-typed here -- a future mode added to
#: ``SchemaConstrainedOutputMode`` is picked up with no edit to this gate.
_VALID_SCHEMA_CONSTRAINED_OUTPUT_MODES: Final[frozenset[str]] = frozenset(
    get_args(SchemaConstrainedOutputMode)
)

#: Every ``ModelFlavorCell`` field this gate requires to be genuinely present -- read from
#: the real ``ModelFlavorCell`` dataclass rather than hardcoded field-by-field; kept as an
#: explicit constant here ONLY as the gate's own cross-check that the dataclass has not
#: silently dropped a field the contract requires (``run_self_test`` compares this against
#: ``_required_cell_field_names()``, which derives the real list from ``dataclasses.fields`` at
#: runtime instead of trusting this literal alone).
_EXPECTED_CELL_FIELD_NAMES: Final[frozenset[str]] = frozenset({
    "schema_constrained_output", "pricing", "managed_keys", "managed_transport",
})


@dataclasses.dataclass(frozen=True)
class ModelRealizationViolation:
    """One finding: a platform whose declaration is missing/unconstructible, whose cell for
    ``provider``/``flavor`` names a flavor outside the closed domain, or whose cell is missing,
    malformed, or omits a required per-flavor value."""

    platform: str
    provider: str | None
    flavor: str | None
    reason: str


def _required_cell_field_names() -> frozenset[str]:
    """The real field names on ``ModelFlavorCell`` as landed, not a hand-maintained literal."""
    return frozenset(f.name for f in dataclasses.fields(ModelFlavorCell))


def _cell_violations(
    platform: str, provider: str, flavor: str, cell: object
) -> list[ModelRealizationViolation]:
    """Check that *cell* is a real, fully-populated, validly-valued ``ModelFlavorCell``.

    Three independent checks, each catching a defect the others -- and
    ``ModelRealization.__post_init__`` -- do not:

    1. ``cell`` is not a ``ModelFlavorCell`` instance at all -- a plugin author's object that
       merely looks right (``model_realizations``/``.flavors`` values are never runtime-checked
       against installed third-party plugins).
    2. ``cell`` IS a ``ModelFlavorCell`` instance but is missing one of its own dataclass fields
       (checked via ``dataclasses.fields`` + ``hasattr`` rather than a fixed attribute list, so a
       future field addition to ``ModelFlavorCell`` is covered without a gate edit) --
       unreachable through the dataclass's own constructor, but not through a
       corrupted/partially-rehydrated instance.
    3. ``cell.schema_constrained_output`` is not one of the closed literal modes --
       ``ModelRealization._validate_cell`` validates ``managed_transport``/``managed_keys``/
       ``pricing`` by flavor, but never this field's VALUE, so a cell that never really states it
       (``None``, or any other placeholder) constructs without error and would otherwise reach
       ``resolve_model_realization`` silently -- exactly the per-flavor-cell invariant that
       nothing is inherited from another flavor or the provider level, turned into its most
       literal violation.
    """
    if not isinstance(cell, ModelFlavorCell):
        return [ModelRealizationViolation(
            platform=platform, provider=provider, flavor=flavor,
            reason=f"flavor cell is not a ModelFlavorCell instance (got {type(cell).__name__})",
        )]
    missing = sorted(name for name in _required_cell_field_names() if not hasattr(cell, name))
    if missing:
        return [ModelRealizationViolation(
            platform=platform, provider=provider, flavor=flavor,
            reason=f"omits required per-flavor value(s): {missing}",
        )]
    if cell.schema_constrained_output not in _VALID_SCHEMA_CONSTRAINED_OUTPUT_MODES:
        return [ModelRealizationViolation(
            platform=platform, provider=provider, flavor=flavor,
            reason=(
                f"omits a required per-flavor value: schema_constrained_output="
                f"{cell.schema_constrained_output!r} is not one of "
                f"{sorted(_VALID_SCHEMA_CONSTRAINED_OUTPUT_MODES)}"
            ),
        )]
    return []


def _declaration_violations(
    platform: str, decl: PlatformCapabilityDeclaration
) -> list[ModelRealizationViolation]:
    """Check the SHAPE of one platform's ``model_realizations`` mapping."""
    violations: list[ModelRealizationViolation] = []
    for provider, realization in dict(decl.model_realizations).items():
        flavors = dict(realization.flavors)
        bad_flavors = set(flavors) - _VALID_FLAVORS
        if bad_flavors:
            violations.append(ModelRealizationViolation(
                platform=platform, provider=provider, flavor=None,
                reason=(
                    f"declares flavor(s) {sorted(bad_flavors)} outside the closed domain "
                    f"{sorted(_VALID_FLAVORS)}"
                ),
            ))
        for flavor, cell in flavors.items():
            if flavor not in _VALID_FLAVORS:
                continue  # already reported above
            violations.extend(_cell_violations(platform, provider, flavor, cell))
    return violations


def all_violations(
    per_platform: dict[str, PlatformCapabilityDeclaration],
) -> list[ModelRealizationViolation]:
    """Run the shape check over every platform's declaration.

    Raises:
        ValueError: If fewer than ``_MIN_PLATFORMS_FOR_COMPARISON`` platforms are supplied.
    """
    if len(per_platform) < _MIN_PLATFORMS_FOR_COMPARISON:
        raise ValueError(
            f"all_violations requires at least {_MIN_PLATFORMS_FOR_COMPARISON} platforms, "
            f"got {len(per_platform)} ({sorted(per_platform)})."
        )
    violations: list[ModelRealizationViolation] = []
    for platform, decl in per_platform.items():
        violations.extend(_declaration_violations(platform, decl))
    return violations


# ---------------------------------------------------------------------------
# Non-vacuity self-test
# ---------------------------------------------------------------------------

_SELF_TEST_PLATFORM_A: Final[str] = "self_test_platform_a"
_SELF_TEST_PLATFORM_B: Final[str] = "self_test_platform_b"
_SELF_TEST_PROVIDER: Final[str] = "self_test_provider"
_SELF_TEST_OFFENDING_FLAVOR: Final[str] = "self_test_bogus_flavor"


def _synthetic_declaration(
    platform_label: str, *, model_realizations: dict[str, ModelRealization]
) -> PlatformCapabilityDeclaration:
    """A minimal, valid ``PlatformCapabilityDeclaration`` for the self-test only -- never a
    stand-in for a real platform. Every other required field takes the same minimal value
    ``block_realization_parity._synthetic_declaration`` uses; only ``model_realizations`` varies.
    """
    return PlatformCapabilityDeclaration(
        deployable_constructs=frozenset({DeployableConstruct.REST_API}),
        platform_label=platform_label,
        default_secret_backend=SecretBackend.FILE,
        crypto_signing_backend=SigningBackend.LOCAL_KEY,
        rdbms_connection_identity=RdbmsConnectionIdentity.PASSWORD,
        cache_connection_identity=CacheConnectionIdentity.PASSWORD,
        supported_secret_backends=frozenset({SecretBackend.FILE}),
        supported_runtimes=frozenset({RuntimeId("self-test-runtime")}),
        serverless_compute_model=ServerlessPlatform.CONTAINER,
        block_realizations={
            ("rdbms", "container"): BlockRealization(
                supported=True, structural_pattern="*/infra/rdbms/container/*.py"
            )
        },
        model_realizations=model_realizations,
    )


def _realization(flavor: str) -> ModelRealization:
    """A well-formed, single-flavor ModelRealization for the self-test's clean side."""
    return ModelRealization(
        sampling=False,
        tool_calling=True,
        attachments=frozenset(),
        flavors={flavor: ModelFlavorCell(
            schema_constrained_output="always", pricing=False,
            managed_keys=(), managed_transport=None,
        )},
    )


@dataclasses.dataclass(frozen=True)
class _RealizationLike:
    """A minimal stand-in exposing exactly the ``.flavors`` shape ``_declaration_violations``
    reads off a provider's realization. ``ModelRealization.__post_init__`` now rejects an
    out-of-domain flavor key at construction time (the closed placement-flavor domain), so a
    REAL ``ModelRealization`` can no longer carry one -- this stand-in proves
    ``_declaration_violations``'s own flavor-domain check still catches a plugin's
    ``model_realizations`` value that never went through that constructor at all, which the type
    system permits (``PlatformCapabilityDeclaration.model_realizations`` is typed
    ``Mapping[str, ModelRealization]`` with no runtime enforcement)."""

    flavors: dict[str, ModelFlavorCell]


def _realization_with_incomplete_cell(flavor: str) -> ModelRealization:
    """A ModelRealization whose one flavor cell never really states its
    ``schema_constrained_output`` -- the per-flavor-cell invariant that nothing is inherited,
    turned into its most literal violation. ``ModelFlavorCell.schema_constrained_output`` is a
    ``Literal``
    with no runtime enforcement, and neither ``ModelRealization.__post_init__`` nor
    ``ModelFlavorCell`` itself validates this field's VALUE (unlike ``managed_transport``/
    ``managed_keys``/``pricing``, which ARE validated by ``ModelRealization._validate_cell``), so
    a cell like this one constructs without error and would otherwise reach
    ``resolve_model_realization`` silently. Proving THIS gate catches it is the point of the
    self-test's third scenario.
    """
    return ModelRealization(
        sampling=False, tool_calling=True, attachments=frozenset(),
        flavors={flavor: ModelFlavorCell(
            schema_constrained_output=None,  # type: ignore[arg-type]
            pricing=False, managed_keys=(), managed_transport=None,
        )},
    )


def run_self_test() -> list[str]:
    """Prove the comparator detects BOTH a bad flavor name AND an incomplete cell before any
    real run is trusted, and that this module's own field-name documentation has not drifted
    from ``ModelFlavorCell``'s real fields.

    Four checks:
    0. ``_EXPECTED_CELL_FIELD_NAMES`` still matches ``ModelFlavorCell``'s real dataclass fields.
    1. A matching pair (both platforms declare only valid, complete flavors) -> zero violations.
    2. Platform B's realization names a flavor outside the closed domain -> exactly one
       violation naming B and the bogus flavor.
    3. Platform B declares a cell that OMITS a required per-flavor value (the "nothing is
       inherited" invariant) -> exactly one violation naming B and the flavor.

    Returns:
        Failure descriptions -- empty means the comparator is sound.
    """
    problems: list[str] = []

    actual_fields = _required_cell_field_names()
    if actual_fields != _EXPECTED_CELL_FIELD_NAMES:
        problems.append(
            f"self-test: ModelFlavorCell's real fields {sorted(actual_fields)} no longer match "
            f"this module's _EXPECTED_CELL_FIELD_NAMES {sorted(_EXPECTED_CELL_FIELD_NAMES)} -- "
            "update _EXPECTED_CELL_FIELD_NAMES to match the landed dataclass."
        )

    clean = _realization("direct")

    # Scenario 1: matching pair.
    matching = {
        _SELF_TEST_PLATFORM_A: _synthetic_declaration("A", model_realizations={_SELF_TEST_PROVIDER: clean}),
        _SELF_TEST_PLATFORM_B: _synthetic_declaration("B", model_realizations={_SELF_TEST_PROVIDER: clean}),
    }
    matching_violations = all_violations(matching)
    if matching_violations:
        problems.append(
            f"self-test: a synthetic MATCHING pair reported {len(matching_violations)} "
            f"violation(s) -- over-triggering: {matching_violations}"
        )

    # Scenario 2: bad flavor name -- a realization-like object that never went through
    # ModelRealization's own constructor (which now rejects this itself at construction time).
    bad_flavor_cell = ModelFlavorCell(
        schema_constrained_output="always", pricing=False,
        managed_keys=(), managed_transport=None,
    )
    bad_flavor_realization = _RealizationLike(flavors={_SELF_TEST_OFFENDING_FLAVOR: bad_flavor_cell})
    divergent_flavor = {
        _SELF_TEST_PLATFORM_A: _synthetic_declaration("A", model_realizations={_SELF_TEST_PROVIDER: clean}),
        _SELF_TEST_PLATFORM_B: _synthetic_declaration(
            "B",
            model_realizations={_SELF_TEST_PROVIDER: bad_flavor_realization},  # type: ignore[dict-item]
        ),
    }
    flavor_violations = all_violations(divergent_flavor)
    flavor_hits = [
        v for v in flavor_violations
        if v.platform == _SELF_TEST_PLATFORM_B and "outside the closed domain" in v.reason
    ]
    if len(flavor_hits) != 1:
        problems.append(
            f"self-test: expected exactly one bad-flavor violation for platform B, "
            f"got {flavor_violations}"
        )
    a_hits_flavor = [v for v in flavor_violations if v.platform == _SELF_TEST_PLATFORM_A]
    if a_hits_flavor:
        problems.append(f"self-test: platform A (valid flavors only) was reported: {a_hits_flavor}")

    # Scenario 3: incomplete cell (the design acceptance property this task adds).
    incomplete = _realization_with_incomplete_cell("direct")
    divergent_cell = {
        _SELF_TEST_PLATFORM_A: _synthetic_declaration("A", model_realizations={_SELF_TEST_PROVIDER: clean}),
        _SELF_TEST_PLATFORM_B: _synthetic_declaration("B", model_realizations={_SELF_TEST_PROVIDER: incomplete}),
    }
    cell_violations = all_violations(divergent_cell)
    cell_hits = [
        v for v in cell_violations
        if v.platform == _SELF_TEST_PLATFORM_B and v.flavor == "direct"
    ]
    if len(cell_hits) != 1:
        problems.append(
            f"self-test: expected exactly one incomplete-cell violation for platform B's "
            f"'direct' flavor, got {cell_violations}"
        )
    a_hits_cell = [v for v in cell_violations if v.platform == _SELF_TEST_PLATFORM_A]
    if a_hits_cell:
        problems.append(f"self-test: platform A (complete cells only) was reported: {a_hits_cell}")

    return problems


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def check_model_realization_parity() -> int:
    """Run the real gate over every installed platform.

    Returns:
        0 = every platform's ``model_realizations`` is present and well-formed; 1 = at least one
        violation (including a declaration that cannot be constructed because the required field is
        absent -- reported naming the platform, never as a raw traceback); 2 = fewer than
        ``_MIN_PLATFORMS_FOR_COMPARISON`` platforms registered.
    """
    platforms = sorted(registered_platform_names())
    if len(platforms) < _MIN_PLATFORMS_FOR_COMPARISON:
        logger.error(
            "Invariant 6 CANNOT RUN: only %d platform(s) registered (%s) -- at least %d required.",
            len(platforms), platforms, _MIN_PLATFORMS_FOR_COMPARISON,
        )
        return 2

    per_platform: dict[str, PlatformCapabilityDeclaration] = {}
    for name in platforms:
        try:
            per_platform[name] = declaration_for_provider(name)
        except TypeError as exc:
            logger.error(
                "Invariant 6 VIOLATION: platform %r's PlatformCapabilityDeclaration cannot be "
                "constructed -- the required model_realizations field is absent: %s",
                name, exc,
            )
            return 1

    violations = all_violations(per_platform)
    for v in violations:
        logger.error(
            "VIOLATION platform=%s provider=%s flavor=%s reason=%s",
            v.platform, v.provider, v.flavor, v.reason,
        )
    if violations:
        logger.error(
            "Invariant 6 VIOLATION: %d malformed model_realizations cell(s) across %d platform(s).",
            len(violations), len(platforms),
        )
        return 1

    logger.info(
        "Invariant 6 holds: every one of %d registered platform(s) (%s) declares a well-formed "
        "model_realizations mapping.",
        len(platforms), platforms,
    )
    return 0


def configure_logging(debug: bool = False) -> None:
    """Configure logging output."""
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO, format="%(levelname)s: %(message)s"
    )


def main() -> int:
    """Entry point. 0 = holds, 1 = violation, 2 = self-test failed or too few platforms."""
    parser = argparse.ArgumentParser(
        description="Prove every installed datrix.platforms plugin declares a well-formed "
        "model_realizations mapping."
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--self-test", action="store_true",
        help="Run only the non-vacuity self-test and skip the real comparison",
    )
    args = parser.parse_args()
    configure_logging(debug=args.debug)

    problems = run_self_test()
    if problems:
        logger.error("Non-vacuity self-test FAILED:")
        for p in problems:
            logger.error("  %s", p)
        return 2
    logger.info("Non-vacuity self-test passed.")
    if args.self_test:
        return 0
    return check_model_realization_parity()


if __name__ == "__main__":
    sys.exit(main())
