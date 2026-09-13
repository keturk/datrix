"""Model-realization capability-declaration parity gate.

Every installed ``datrix.platforms`` plugin declares a ``PlatformCapabilityDeclaration``
(``datrix_common.plugin.capability``) carrying a REQUIRED ``model_realizations`` mapping --
one ``ModelRealization`` per provider (API family) the platform realizes, each cell's
``flavors`` drawn from the closed placement domain ``container | external | managed | direct``.

Scoped to that single field: does every installed platform's declaration construct, and does
every cell reference only a flavor from the closed domain. A platform realizing zero providers
is NOT a violation (an empty mapping is a statement); only a missing or malformed declaration is.

The platform set is never hardcoded: it is enumerated from the installed ``datrix.platforms``
entry points at run time via ``shared.registered_targets.registered_platform_names``.
"""

from __future__ import annotations

import argparse
import dataclasses
import logging
import sys
from pathlib import Path
from typing import Final

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
from datrix_common.plugin.model_realization import ModelRealization  # noqa: E402

logger = logging.getLogger(__name__)

#: A comparison over 0 or 1 platform is vacuous (mirrors block_realization_parity).
_MIN_PLATFORMS_FOR_COMPARISON: Final[int] = 2

#: The closed placement domain a ``ModelRealization.flavors`` entry may name.
_VALID_FLAVORS: Final[frozenset[str]] = frozenset({"container", "external", "managed", "direct"})


@dataclasses.dataclass(frozen=True)
class ModelRealizationViolation:
    """One finding: a platform whose declaration is missing/unconstructible, or whose cell for
    ``provider`` names a flavor outside the closed domain."""

    platform: str
    provider: str | None
    reason: str


def _declaration_violations(
    platform: str, decl: PlatformCapabilityDeclaration
) -> list[ModelRealizationViolation]:
    """Check the SHAPE of one platform's ``model_realizations`` mapping."""
    violations: list[ModelRealizationViolation] = []
    for provider, realization in dict(decl.model_realizations).items():
        bad_flavors = set(realization.flavors) - _VALID_FLAVORS
        if bad_flavors:
            violations.append(
                ModelRealizationViolation(
                    platform=platform,
                    provider=provider,
                    reason=(
                        f"declares flavor(s) {sorted(bad_flavors)} outside the closed domain "
                        f"{sorted(_VALID_FLAVORS)}"
                    ),
                )
            )
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
    ``block_realization_parity._synthetic_declaration`` uses; only ``model_realizations`` varies."""
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
    return ModelRealization(
        flavors=frozenset({flavor}),
        sampling=False,
        tool_calling=True,
        schema_constrained_output="always",
        attachments=frozenset(),
        pricing=False,
    )


def run_self_test() -> list[str]:
    """Prove the comparator detects a forced divergence before any real run is trusted.

    A matching pair (both platforms declare only valid flavors) must report zero violations; an
    offending pair (platform B declares a cell whose flavor is outside the closed domain) must
    report exactly one violation naming platform B and the bogus flavor, and none for A.

    Returns:
        Failure descriptions -- empty means the comparator is sound.
    """
    problems: list[str] = []
    clean = _realization("direct")
    offending = _realization(_SELF_TEST_OFFENDING_FLAVOR)

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

    divergent = {
        _SELF_TEST_PLATFORM_A: _synthetic_declaration("A", model_realizations={_SELF_TEST_PROVIDER: clean}),
        _SELF_TEST_PLATFORM_B: _synthetic_declaration("B", model_realizations={_SELF_TEST_PROVIDER: offending}),
    }
    divergent_violations = all_violations(divergent)
    b_hits = [
        v for v in divergent_violations
        if v.platform == _SELF_TEST_PLATFORM_B and v.provider == _SELF_TEST_PROVIDER
    ]
    if len(b_hits) != 1:
        problems.append(
            f"self-test: expected exactly one violation for platform B's out-of-domain flavor "
            f"{_SELF_TEST_OFFENDING_FLAVOR!r}, got {divergent_violations}"
        )
    a_hits = [v for v in divergent_violations if v.platform == _SELF_TEST_PLATFORM_A]
    if a_hits:
        problems.append(f"self-test: platform A (valid flavors only) was reported: {a_hits}")

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
        logger.error("VIOLATION platform=%s provider=%s reason=%s", v.platform, v.provider, v.reason)
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
