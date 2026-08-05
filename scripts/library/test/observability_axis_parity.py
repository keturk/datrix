"""Cross-target observability-AXIS parity gate.

Proves the language/platform split for observability provider realization is
consistent across EVERY registered target -- the invariant whose absence let
two generation-breaking defects ship green:

1. A language declared it realized providers in a category that only the
   PLATFORM can realize (one language declared every logging backend
   realized while others declared none), so the SAME config generated
   cleanly on one language and failed generation outright on another.
2. The language-axis validator policed a platform-only category, so a
   provider the resolved platform natively realizes (and actually
   provisions) was rejected for every project using that language.

Both are CROSS-TARGET consistency defects. Per-package conformance suites
cannot detect either by construction: each package validates its own
declaration in isolation, so every package can be internally green while
disagreeing with the others about the same portable field. This gate is the
repo-level backstop that compares targets.

Two legs, both with their target sets derived from the installed entry
points at runtime -- never a hardcoded language/provider literal:

* **Leg 1 (declaration identity).** For every category in
  ``PLATFORM_ONLY_OBSERVABILITY_CATEGORIES``, every registered language must
  declare exactly the empty set. A language claiming to realize a
  platform-only category is the defect class (1) above.
* **Leg 2 (validator agreement).** For each platform-only category, a
  provider that at least one registered PLATFORM declares native must
  validate cleanly against EVERY registered language. A language that
  rejects it is the defect class (2) above.

Repo-level validation script (per the datrix showcase boundary -- no pytest
suite lives in datrix).

Usage:
    python observability_axis_parity.py
    python observability_axis_parity.py --debug
    python observability_axis_parity.py --self-test
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.metadata import entry_points
from typing import Final

from datrix_common.config.observability.models import (
    AlertingConfig,
    AlertingProvider,
    LoggingConfig,
    LoggingProvider,
    MetricsConfig,
    MetricsProvider,
    ObservabilityProfileConfig,
    TracingConfig,
    TracingProvider,
    VisualizationConfig,
    VisualizationProvider,
)
from datrix_common.errors.generation import GenerationError
from datrix_common.plugin.capability_resolution import (
    declaration_for_language,
    declaration_for_provider,
    validate_language_provider_realization,
)
from datrix_common.plugin.language_capability import (
    PLATFORM_ONLY_OBSERVABILITY_CATEGORIES,
    LanguageCapabilityDeclaration,
)
from datrix_common.plugin.registry import LANGUAGES_GROUP, PLATFORM_GROUP

#: Checking "every language agrees" over zero languages is vacuous -- it
#: would report a clean gate while proving nothing. Fail loud instead.
_MIN_LANGUAGES: Final[int] = 1

#: Leg 2 needs at least one registered platform to source a natively-realized
#: provider from; with none, there is no (category, provider) pair to agree
#: about and the leg would pass vacuously.
_MIN_PLATFORMS: Final[int] = 1


@dataclass(frozen=True)
class _CategoryBinding:
    """How one observability category is spelled on the profile config.

    Mirrors the five fixed categories ``LanguageCapabilityDeclaration`` and
    ``PlatformCapabilityDeclaration`` are both keyed by. This is a MODEL
    shape (which categories the config has), never a target list -- the
    languages and providers this gate compares are always discovered.
    """

    field_name: str
    config_cls: type
    provider_enum: type


#: The five categories, bound to their profile-config spelling so this gate
#: can build a real ``ObservabilityProfileConfig`` for any of them.
_CATEGORY_BINDINGS: Final[dict[str, _CategoryBinding]] = {
    "metrics": _CategoryBinding("metrics", MetricsConfig, MetricsProvider),
    "tracing": _CategoryBinding("tracing", TracingConfig, TracingProvider),
    "logging": _CategoryBinding("logging", LoggingConfig, LoggingProvider),
    "visualization": _CategoryBinding("visualization", VisualizationConfig, VisualizationProvider),
    "alerting": _CategoryBinding("alerting", AlertingConfig, AlertingProvider),
}

#: Synthetic language label used only by the self-test. Deliberately NOT a
#: real registered language name -- the self-test proves the comparators'
#: discriminating power and must never influence the real comparison.
_SELF_TEST_LANGUAGE: Final[str] = "self_test_lang"


def configure_logging(debug: bool = False) -> None:
    """Configure logging output."""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def _discover_names(group: str) -> frozenset[str]:
    """Return every entry-point name registered under *group*.

    Args:
        group: The entry-point group to enumerate (e.g. ``datrix.languages``).

    Returns:
        The frozenset of installed entry-point names in that group.

    Raises:
        RuntimeError: If entry-point discovery itself fails.
    """
    try:
        return frozenset(ep.name for ep in entry_points(group=group))
    except Exception as e:
        raise RuntimeError(
            f"Failed to discover {group!r} entry points: {e}. Expected the "
            f"group to be queryable via importlib.metadata.entry_points(). "
            f"Fix: verify the datrix packages are installed into the active "
            f"environment (D:\\datrix\\.venv)."
        ) from e


def registered_language_names() -> frozenset[str]:
    """Return every registered ``datrix.languages`` name (never hardcoded)."""
    return _discover_names(LANGUAGES_GROUP)


def registered_platform_names() -> frozenset[str]:
    """Return every registered ``datrix.platforms`` name (never hardcoded)."""
    return _discover_names(PLATFORM_GROUP)


def platform_native_providers(platform_names: frozenset[str]) -> dict[str, frozenset[str]]:
    """Union each category's natively-realized providers across the platforms.

    Args:
        platform_names: Registered platform entry-point names.

    Returns:
        ``{category: {provider_value, ...}}`` -- every provider at least one
        registered platform declares native for that category.
    """
    union: dict[str, set[str]] = {category: set() for category in _CATEGORY_BINDINGS}
    for name in sorted(platform_names):
        declaration = declaration_for_provider(name)
        for category, providers in declaration.native_observability_providers.items():
            if category in union:
                # Platforms declare these as either the provider enum member
                # or its `.value`; both are valid (the enums are StrEnum) but
                # mixing them makes this gate's own output unreadable. Coerce
                # to the plain value so every downstream compare and message
                # sees one shape.
                union[category].update(str(provider) for provider in providers)
    return {category: frozenset(values) for category, values in union.items()}


def find_platform_only_claims(
    per_language: Mapping[str, LanguageCapabilityDeclaration],
) -> dict[str, dict[str, frozenset[str]]]:
    """Leg 1 comparator: languages claiming to realize a platform-only category.

    Pure -- takes declarations, touches no registry -- so the self-test can
    feed it synthetic declarations.

    Args:
        per_language: ``{language_name: declaration}`` under comparison.

    Returns:
        ``{language_name: {category: claimed_providers}}`` for every language
        declaring a non-empty set in a platform-only category. Empty when the
        invariant holds.
    """
    violations: dict[str, dict[str, frozenset[str]]] = {}
    for name in sorted(per_language):
        declared = per_language[name].realized_observability_providers
        claimed = {
            category: frozenset(declared.get(category, frozenset()))
            for category in sorted(PLATFORM_ONLY_OBSERVABILITY_CATEGORIES)
            if declared.get(category)
        }
        if claimed:
            violations[name] = claimed
    return violations


def derive_platform_realized_only(
    per_language: Mapping[str, LanguageCapabilityDeclaration],
    native: Mapping[str, frozenset[str]],
) -> dict[str, frozenset[str]]:
    """Categories a PLATFORM realizes and NO registered language realizes.

    Leg 2's scope, derived from the declarations themselves rather than from
    ``PLATFORM_ONLY_OBSERVABILITY_CATEGORIES``. Deriving it from that constant
    would make the gate blind to the exact defect the constant can have:
    dropping a category from it silently drops that category from the check
    too, so reintroducing the original "language axis rejects a
    platform-provisioned provider" defect would pass unnoticed. A category no
    language realizes but some platform does can only ever be rejected
    WRONGLY on the language axis -- that conclusion needs no constant.

    Args:
        per_language: ``{language_name: declaration}`` under comparison.
        native: ``{category: natively-realized providers}`` across platforms.

    Returns:
        ``{category: providers}`` for every category that at least one
        platform realizes and no language claims.
    """
    scoped: dict[str, frozenset[str]] = {}
    for category, providers in native.items():
        if not providers:
            continue
        if any(
            declaration.realized_observability_providers.get(category)
            for declaration in per_language.values()
        ):
            # Some language genuinely realizes this category, so a rejection
            # on the language axis is legitimate, not a defect.
            continue
        scoped[category] = frozenset(providers)
    return scoped


def build_observability_config(category: str, provider_value: str) -> ObservabilityProfileConfig:
    """Build a real profile config declaring *provider_value* in *category*.

    Args:
        category: One of the five observability categories.
        provider_value: A provider value valid for that category's enum.

    Returns:
        An ``ObservabilityProfileConfig`` with only that category configured.

    Raises:
        KeyError: If *category* is not one of the five bound categories.
    """
    binding = _CATEGORY_BINDINGS[category]
    provider = binding.provider_enum(provider_value)
    return ObservabilityProfileConfig(**{binding.field_name: binding.config_cls(provider=provider)})


def find_rejecting_languages(
    per_language: Mapping[str, LanguageCapabilityDeclaration],
    category: str,
    provider_value: str,
) -> dict[str, str]:
    """Leg 2 comparator: languages whose axis rejects a platform-realized pair.

    Pure -- takes declarations, touches no registry.

    Args:
        per_language: ``{language_name: declaration}`` under comparison.
        category: The observability category to configure.
        provider_value: The provider value at least one platform realizes.

    Returns:
        ``{language_name: error_message}`` for every language that raised.
        Empty when every language accepts the pair.
    """
    observability = build_observability_config(category, provider_value)
    rejecting: dict[str, str] = {}
    for name in sorted(per_language):
        try:
            validate_language_provider_realization(per_language[name], observability)
        except GenerationError as e:
            rejecting[name] = str(e)
    return rejecting


def _assert_self_test_leg1() -> None:
    """Prove leg 1's comparator detects a claim and passes a clean declaration."""
    category = sorted(PLATFORM_ONLY_OBSERVABILITY_CATEGORIES)[0]
    provider_value = sorted(m.value for m in _CATEGORY_BINDINGS[category].provider_enum)[0]

    clean = {
        _SELF_TEST_LANGUAGE: LanguageCapabilityDeclaration(
            language_label=_SELF_TEST_LANGUAGE,
            realized_observability_providers={c: frozenset() for c in _CATEGORY_BINDINGS},
        )
    }
    if find_platform_only_claims(clean):
        raise AssertionError(
            "Non-vacuity self-test FAILED (leg 1): a synthetic declaration "
            "that claims NOTHING in any platform-only category was reported "
            "as violating -- the comparator over-triggers and cannot judge "
            "the real declarations."
        )

    claiming = {
        _SELF_TEST_LANGUAGE: LanguageCapabilityDeclaration(
            language_label=_SELF_TEST_LANGUAGE,
            realized_observability_providers={category: frozenset({provider_value})},
        )
    }
    detected = find_platform_only_claims(claiming)
    if provider_value not in detected.get(_SELF_TEST_LANGUAGE, {}).get(category, frozenset()):
        raise AssertionError(
            f"Non-vacuity self-test FAILED (leg 1): the comparator did not "
            f"detect a synthetic language claiming {provider_value!r} in the "
            f"platform-only category {category!r} (got {detected}) -- a gate "
            f"that cannot detect the real divergence is worthless."
        )


def _assert_self_test_leg2() -> None:
    """Prove leg 2 is meaningful: the validator still bites on the language axis.

    Leg 2 asserts every language ACCEPTS a platform-realized pair. That
    result is only informative if the validator can still reject something --
    a neutered validator would make leg 2 pass vacuously. So this feeds it a
    language-REALIZABLE category with a provider the synthetic declaration
    does not declare, and requires a rejection.
    """
    language_axis_categories = sorted(set(_CATEGORY_BINDINGS) - PLATFORM_ONLY_OBSERVABILITY_CATEGORIES)
    if not language_axis_categories:
        raise AssertionError(
            "Non-vacuity self-test FAILED (leg 2): every observability "
            "category is marked platform-only, so the language axis polices "
            "nothing and leg 2 can never be meaningful. Expected at least one "
            "language-realizable category (metrics/tracing). Fix: review "
            "PLATFORM_ONLY_OBSERVABILITY_CATEGORIES."
        )

    category = language_axis_categories[0]
    provider_value = sorted(m.value for m in _CATEGORY_BINDINGS[category].provider_enum)[0]
    realizes_nothing = {
        _SELF_TEST_LANGUAGE: LanguageCapabilityDeclaration(
            language_label=_SELF_TEST_LANGUAGE,
            realized_observability_providers={category: frozenset()},
        )
    }
    if not find_rejecting_languages(realizes_nothing, category, provider_value):
        raise AssertionError(
            f"Non-vacuity self-test FAILED (leg 2): the language-axis "
            f"validator accepted {provider_value!r} in the language-realizable "
            f"category {category!r} for a synthetic language declaring NOTHING "
            f"realized. Expected a GenerationError. The validator no longer "
            f"rejects anything, so leg 2's clean result would be vacuous."
        )

    platform_only = sorted(PLATFORM_ONLY_OBSERVABILITY_CATEGORIES)[0]
    po_provider = sorted(m.value for m in _CATEGORY_BINDINGS[platform_only].provider_enum)[0]
    rejecting = find_rejecting_languages(realizes_nothing, platform_only, po_provider)
    if rejecting:
        raise AssertionError(
            f"Non-vacuity self-test FAILED (leg 2): the language-axis "
            f"validator REJECTED {po_provider!r} in the platform-only category "
            f"{platform_only!r} ({rejecting}). Platform-only categories must "
            f"be skipped on the language axis -- this is exactly the defect "
            f"that rejected a platform-provisioned provider for every project."
        )


def run_self_test() -> None:
    """Prove both comparators discriminate before any real comparison is trusted.

    Raises:
        AssertionError: If either leg's comparator cannot detect its defect
            class, or false-positives on a clean input.
    """
    _assert_self_test_leg1()
    _assert_self_test_leg2()


def check_observability_axis_parity() -> int:
    """Run both legs against the real registered targets.

    Returns:
        Exit code (0 = both legs hold, 1 = a violation was found, 2 = too few
        registered targets for a non-vacuous comparison).
    """
    logger = logging.getLogger(__name__)
    languages = sorted(registered_language_names())
    platforms = sorted(registered_platform_names())

    if len(languages) < _MIN_LANGUAGES:
        logger.error(
            "CANNOT RUN: %d language(s) registered under '%s' -- at least %d "
            "required. Expected installed datrix-codegen-<lang> package(s) "
            "each registering a 'datrix.languages' entry point. Fix: install "
            "the language package(s) into D:\\datrix\\.venv (editable).",
            len(languages), LANGUAGES_GROUP, _MIN_LANGUAGES,
        )
        return 2
    if len(platforms) < _MIN_PLATFORMS:
        logger.error(
            "CANNOT RUN: %d platform(s) registered under '%s' -- at least %d "
            "required to source a natively-realized provider for leg 2. Fix: "
            "install the platform package(s) into D:\\datrix\\.venv.",
            len(platforms), PLATFORM_GROUP, _MIN_PLATFORMS,
        )
        return 2

    per_language = {name: declaration_for_language(name) for name in languages}
    native = platform_native_providers(frozenset(platforms))
    platform_only = sorted(PLATFORM_ONLY_OBSERVABILITY_CATEGORIES)
    logger.info(
        "Comparing %d language(s) %s against %d platform(s) %s over "
        "platform-only categories %s",
        len(languages), languages, len(platforms), platforms, platform_only,
    )

    ok = True

    claims = find_platform_only_claims(per_language)
    for name, claimed in claims.items():
        ok = False
        logger.error(
            "AXIS VIOLATION (leg 1): language %r declares it realizes "
            "provider(s) in platform-only category/categories %s. Those are "
            "provisioned by the resolved PLATFORM, never by language-emitted "
            "code, so every language must declare them empty -- a non-empty "
            "claim here is how the same config generates on one language and "
            "fails generation on another. Fix: declare frozenset() for %s in "
            "that package's LanguageCapabilityDeclaration.",
            name, {c: sorted(v) for c, v in claimed.items()}, sorted(claimed),
        )

    leg2_scope = derive_platform_realized_only(per_language, native)
    if not leg2_scope:
        logger.error(
            "CANNOT RUN leg 2: no category is realized by a platform while "
            "unrealized by every language, so there is no pair whose "
            "acceptance proves anything. Expected at least one such category "
            "(dashboards/alert rules are provisioned by the platform). Fix: "
            "verify the platform capability declarations still enumerate "
            "their native observability providers.",
        )
        return 2
    logger.info(
        "leg 2 scope (derived from declarations, NOT from the platform-only "
        "constant): %s", sorted(leg2_scope),
    )

    for category, providers in sorted(leg2_scope.items()):
        # EVERY natively-realized provider, not a representative: the defect
        # this leg exists to catch was one specific provider (the dashboard
        # one) being rejected, and a single-representative check would miss it
        # whenever another provider happened to sort first.
        category_ok = True
        for provider_value in sorted(providers):
            rejecting = find_rejecting_languages(per_language, category, provider_value)
            for name, message in rejecting.items():
                ok = False
                category_ok = False
                logger.error(
                    "AXIS VIOLATION (leg 2): language %r rejects %s provider "
                    "%r, which at least one registered platform natively "
                    "realizes and actually provisions. A platform-provisioned "
                    "provider must never be rejected on the language axis -- "
                    "this breaks generation for every project on that "
                    "language. Validator said: %s",
                    name, category, provider_value, message,
                )
        if category_ok:
            logger.info(
                "leg 2 holds for %s: every language accepts all %d "
                "platform-realized provider(s): %s",
                category, len(providers), sorted(providers),
            )

    if ok:
        logger.info(
            "Observability-axis parity holds: all %d registered language(s) "
            "declare every platform-only category (%s) empty, and each accepts "
            "the platform-realized provider for it.",
            len(languages), platform_only,
        )

    return 0 if ok else 1


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 = parity holds, 1 = a violation was found, 2 = the
        non-vacuity self-test failed or too few registered targets).
    """
    parser = argparse.ArgumentParser(
        description=(
            "Prove every registered language agrees with the platform axis "
            "about platform-only observability categories."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run only the non-vacuity self-test and skip the real comparison",
    )
    args = parser.parse_args()

    configure_logging(debug=args.debug)
    logger = logging.getLogger(__name__)

    try:
        run_self_test()
    except AssertionError as e:
        logger.error(
            "Non-vacuity self-test FAILED -- aborting before any real "
            "comparison is trusted: %s", e,
        )
        return 2
    logger.info("Non-vacuity self-test passed (both legs discriminate)")

    if args.self_test:
        return 0

    return check_observability_axis_parity()


if __name__ == "__main__":
    sys.exit(main())
