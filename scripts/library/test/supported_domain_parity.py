"""Cross-language SUPPORTED-domain-set parity gate (G3 final).

Generalizes ``shared39_supported_parity.py`` (java<->python only) into a gate
over EVERY registered ``datrix.languages`` entry point -- so dotnet (and any
future ``datrix-codegen-<lang>``) is actually covered, not silently excluded
by a two-language hardcoding. That is the ONE change from the superseded gate:
more TARGETS. The DOMAIN scope is unchanged --
G3 has never required every registered language to
implement every other language's PRIVATE domains (e.g. java's
``function``/``helper``/``dev_scripts``); it requires agreement only on the
domains multiple languages could plausibly commit a cross-language-stable
structural glob for -- the seven rich cross-language domains
that are also shared-39 members. See ``_RICH_AND_SHARED39_IDS`` below for the
cited source of that restriction.

**Language set is never hardcoded.** ``registered_language_names`` derives
the comparison universe from ``importlib.metadata.entry_points(group=
"datrix.languages")`` at runtime, so a future ``datrix-codegen-<lang>``
package is picked up automatically with no edit to this script. (The domain
SCOPE restriction below is a different axis -- WHICH domains are compared,
not WHICH languages -- and is deliberately a named, cited constant, not a
target list; see ``_RICH_AND_SHARED39_IDS``.)

**The MariaDB engine boundary needs no special-case code.** The
MariaDB engine boundary is an ENGINE CHOICE inside the ``rdbms``/migration
domains, not a withheld domain -- it never shows up as a domain-set diff at
this script's grain. This script compares by ``domain_id`` (a coarser grain
than per-engine), so MariaDB is naturally never a domain-id-level diff. Do
not add a per-engine special case here.

**Supersedes ``shared39_supported_parity.py``.** That script's cross-language
assertion (java's and python's SUPPORTED sets agree, restricted to
``_RICH_AND_SHARED39_IDS``) is strictly implied by this script's assertion
(EVERY registered language's set, restricted to the SAME
``_RICH_AND_SHARED39_IDS``, is identical): if all N registered languages'
restricted sets pairwise agree, then in particular java's and python's do
too -- a straight generalization from 2 targets to N, same invariant. Its
second assertion (8 infra-family ``_test`` domains excluded from the
restricted set) was already vacuous by construction -- those 8 domains are
shared-39 members that are provably disjoint from the seven rich domains
(``_RICH_AND_SHARED39_IDS ∩ _INFRA_FAMILY_TEST_DOMAINS == ∅``), so the
restricted set could never contain one regardless of what either language
declares. ``shared39_supported_parity.py`` and its ``.ps1`` wrapper are
therefore deleted rather than kept as a redundant, narrower gate.

**Built-in non-vacuity self-test, every invocation.** Before any real
comparison is trusted, ``run_self_test`` feeds the comparator a synthetic
matching pair (must report zero divergence) and a synthetic forced-mismatch
pair (must report the missing domain). A parity gate that cannot detect a
real divergence is worthless -- this mirrors the self-test pattern already
used by ``reference-example-parity-gate.ps1``, ``check-generated-file-ratchet.ps1``,
and ``check-docs-conformance.ps1``. This tests the COMPARATOR mechanism
itself (domain-scope-agnostic); the domain-scope restriction is separately
proven live by temporarily removing a real, in-scope glob (see task
05-27's How-Solved for the command + output).

**Fails loud on an empty/single-target discovery.** Fewer than 2 registered
languages makes a cross-language comparison vacuous; ``check_supported_domain_parity``
refuses to silently "pass" that case and exits 2 instead.

Usage:
    python supported_domain_parity.py
    python supported_domain_parity.py --debug
    python supported_domain_parity.py --self-test
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Mapping
from importlib.metadata import entry_points
from typing import Final, cast

from datrix_codegen_common.parity.domain_registry import (
    _RICH_CONTEXT_TYPES,
    SHARED_CONTEXT_TYPES,
)
from datrix_codegen_common.testkit.gates.domain_self_consistency import (
    DomainDeclaringPlugin,
)
from datrix_common.generation.discovery import get_language_plugin
from datrix_common.plugin.registry import LANGUAGES_GROUP

#: A cross-language parity comparison over 0 or 1 language is vacuous (there
#: is nothing to compare against) -- discovery returning fewer than this many
#: registered languages is a fail-loud condition, never a silent "pass".
_MIN_LANGUAGES_FOR_COMPARISON: Final[int] = 2

#: G3's DOMAIN-scope restriction (inherited
#: unchanged from the superseded ``shared39_supported_parity.py`` -- NOT a
#: target/language list, so it does not violate the no-hardcoded-targets
#: rule; it answers "which domains", not "which languages"). Sourced from
#: :mod:`datrix_codegen_common.parity.domain_registry`:
#: ``_RICH_CONTEXT_TYPES`` is the seven domains that each have a
#: dedicated SHARED context-model type (entity, schema, service_layer,
#: cache, pubsub, cqrs, jobs -- the same seven the pre-D9
#: ``parity/contract.py`` ``DOMAIN_CONTRACTS`` covered), intersected with
#: ``SHARED_CONTEXT_TYPES`` (every domain id any ``COMMON_GENERATOR_
#: REGISTRATIONS`` entry declares -- the "shared-39" universe D9 governs).
#: Every one of the seven IS a shared-39 member (``_build_shared_context_
#: types`` maps every COMMON registration's domain id, rich or not), so the
#: intersection equals ``frozenset(_RICH_CONTEXT_TYPES)`` today -- taken as
#: an intersection anyway (never a bare literal) so this scope tracks
#: ``SHARED_CONTEXT_TYPES`` if that ever changes, matching the superseded
#: gate's own defensive style. G3 restricts to this scope because these are
#: the only domains multiple languages could plausibly commit a
#: cross-language-stable structural glob for; a language's OWN additional
#: domain outside this set (java's ``function``/``helper``/``dev_scripts``,
#: python's/typescript's various ``_test`` domains) is a legitimate private
#: addition, never a G3 violation.
_RICH_AND_SHARED39_IDS: Final[frozenset[str]] = frozenset(_RICH_CONTEXT_TYPES) & frozenset(
    SHARED_CONTEXT_TYPES
)

#: Synthetic language names used only by the self-test below. Deliberately
#: NOT real registered language names (`python`/`dotnet`/`java`/`typescript`)
#: -- the self-test proves the COMPARATOR's discriminating power, it must
#: never influence which real languages get compared.
_SELF_TEST_LANGUAGE_A: Final[str] = "self_test_lang_a"
_SELF_TEST_LANGUAGE_B: Final[str] = "self_test_lang_b"

#: Synthetic domain ids (neutral e-commerce domain, per repo domain-isolation
#: rules) used only by the self-test below.
_SELF_TEST_DOMAIN_SHARED: Final[str] = "self_test_order"
_SELF_TEST_DOMAIN_FORCED_GAP: Final[str] = "self_test_shipment"


def configure_logging(debug: bool = False) -> None:
    """Configure logging output."""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def registered_language_names() -> frozenset[str]:
    """Return every language name registered under the ``datrix.languages`` group.

    Derived from the installed entry points -- never a hardcoded literal --
    so a future language package is picked up automatically with no edit here.

    Returns:
        The frozenset of every installed ``datrix.languages`` entry-point name.

    Raises:
        RuntimeError: If entry-point discovery itself fails (queryable
            ``importlib.metadata`` failure, not a plugin-load failure).
    """
    try:
        eps = list(entry_points(group=LANGUAGES_GROUP))
    except Exception as e:
        raise RuntimeError(
            f"Failed to discover '{LANGUAGES_GROUP}' entry points: {e}. "
            f"Expected the 'datrix.languages' entry-point group to be "
            f"queryable via importlib.metadata.entry_points(). Fix: verify "
            f"at least one datrix-codegen-<lang> package is installed into "
            f"the active environment (D:\\datrix\\.venv)."
        ) from e
    return frozenset(ep.name for ep in eps)


def supported_domain_ids(language_name: str) -> frozenset[str]:
    """Return the FULL set of domain ids *language_name*'s plugin declares 'supported'.

    Unrestricted -- includes the language's own private domains (e.g. java's
    ``function``/``helper``/``dev_scripts``), not just the G3 comparison
    scope. Callers that need the G3 comparison set intersect this with
    ``_RICH_AND_SHARED39_IDS`` (see ``check_supported_domain_parity``).

    Args:
        language_name: A ``datrix.languages`` entry-point name (e.g.
            ``"python"``, ``"dotnet"``).

    Returns:
        The frozenset of domain ids for which the plugin's
        ``domain_declarations`` records ``status == "supported"``.
    """
    plugin = get_language_plugin(language_name)
    # `get_language_plugin` returns the base `LanguagePlugin` protocol, which
    # deliberately does not list `domain_declarations` (see
    # `DomainDeclaringPlugin`'s own docstring). Every concrete language
    # plugin class attaches `domain_declarations` regardless; this cast
    # asserts that structural fact without importing any concrete
    # `datrix-codegen-<lang>` package.
    declaring_plugin = cast(DomainDeclaringPlugin, plugin)
    return frozenset(
        domain_id
        for domain_id, declaration in declaring_plugin.domain_declarations.items()
        if declaration.status == "supported"
    )


def compare_supported_domain_sets(
    per_language: Mapping[str, frozenset[str]],
) -> dict[str, frozenset[str]]:
    """Compare every language's supported-domain set against the union of all.

    Args:
        per_language: ``{language_name: supported_domain_ids}`` for every
            language under comparison.

    Returns:
        ``{language_name: missing_domain_ids}`` -- the domains present in at
        least one OTHER language's supported set but absent from this
        language's own set. Every value is the empty set iff every
        language's supported-domain set is identical (G3's POS acceptance
        property).

    Raises:
        ValueError: If *per_language* has fewer than
            ``_MIN_LANGUAGES_FOR_COMPARISON`` entries -- comparing 0 or 1
            language's set against itself is vacuously "equal" and must
            never be silently reported as parity holding.
    """
    if len(per_language) < _MIN_LANGUAGES_FOR_COMPARISON:
        raise ValueError(
            f"compare_supported_domain_sets requires at least "
            f"{_MIN_LANGUAGES_FOR_COMPARISON} languages to compare, got "
            f"{len(per_language)} ({sorted(per_language)}). A parity "
            f"comparison over fewer than 2 languages is vacuous -- pass a "
            f"larger *per_language* mapping."
        )
    union_ids: frozenset[str] = frozenset[str]().union(*per_language.values())
    return {name: union_ids - ids for name, ids in per_language.items()}


def run_self_test() -> None:
    """Prove the comparator can detect a forced mismatch before any real
    comparison is trusted (non-vacuity requirement).

    Feeds :func:`compare_supported_domain_sets` a synthetic MATCHING pair
    (both synthetic languages declare the same one domain -- must report
    zero divergence for both) and a synthetic MISMATCHED pair (one language
    is missing a domain the other declares -- must report exactly that
    domain as missing). A comparator that either false-positives on the
    matching pair or fails to detect the forced gap cannot be trusted for
    the real comparison that follows.

    Raises:
        AssertionError: If either synthetic case does not produce the
            expected result.
    """
    matching_pair = {
        _SELF_TEST_LANGUAGE_A: frozenset({_SELF_TEST_DOMAIN_SHARED}),
        _SELF_TEST_LANGUAGE_B: frozenset({_SELF_TEST_DOMAIN_SHARED}),
    }
    matching_result = compare_supported_domain_sets(matching_pair)
    if any(matching_result.values()):
        raise AssertionError(
            f"Non-vacuity self-test FAILED: compare_supported_domain_sets "
            f"reported a divergence for a synthetic MATCHING pair "
            f"({matching_result}) -- the comparator is over-triggering and "
            f"cannot be trusted to judge a real comparison."
        )

    mismatched_pair = {
        _SELF_TEST_LANGUAGE_A: frozenset({_SELF_TEST_DOMAIN_SHARED, _SELF_TEST_DOMAIN_FORCED_GAP}),
        _SELF_TEST_LANGUAGE_B: frozenset({_SELF_TEST_DOMAIN_SHARED}),
    }
    mismatched_result = compare_supported_domain_sets(mismatched_pair)
    missing_for_b = mismatched_result.get(_SELF_TEST_LANGUAGE_B, frozenset())
    if _SELF_TEST_DOMAIN_FORCED_GAP not in missing_for_b:
        raise AssertionError(
            f"Non-vacuity self-test FAILED: compare_supported_domain_sets "
            f"did not detect the forced mismatch (expected "
            f"{_SELF_TEST_DOMAIN_FORCED_GAP!r} to be reported missing for "
            f"{_SELF_TEST_LANGUAGE_B!r}, got {mismatched_result}) -- a "
            f"parity gate that cannot detect a real divergence is worthless."
        )
    if mismatched_result.get(_SELF_TEST_LANGUAGE_A):
        raise AssertionError(
            f"Non-vacuity self-test FAILED: compare_supported_domain_sets "
            f"reported {_SELF_TEST_LANGUAGE_A!r} as missing domains it "
            f"actually declares ({mismatched_result[_SELF_TEST_LANGUAGE_A]}) "
            f"-- the comparator's per-language result is asymmetric/wrong."
        )


def check_supported_domain_parity() -> int:
    """Compare every registered language's derived supported-domain set,
    restricted to the G3 domain scope (``_RICH_AND_SHARED39_IDS``).

    Returns:
        Exit code (0 = every registered language's RESTRICTED supported set
        agrees, 1 = a divergence was found for at least one language within
        that restricted scope, 2 = fewer than ``_MIN_LANGUAGES_FOR_COMPARISON``
        languages are registered -- a cross-language comparison over 0 or 1
        language is vacuous and must fail loud rather than silently "pass").
    """
    logger = logging.getLogger(__name__)
    languages = sorted(registered_language_names())

    if len(languages) < _MIN_LANGUAGES_FOR_COMPARISON:
        logger.error(
            "G3 CANNOT RUN: only %d language(s) registered under '%s' (%s) "
            "-- at least %d are required for a cross-language parity "
            "comparison. Expected: 2+ installed datrix-codegen-<lang> "
            "packages, each registering a 'datrix.languages' entry point in "
            "its own pyproject.toml. Fix: install the missing language "
            "package(s) into D:\\datrix\\.venv (editable install), or "
            "verify entry-point registration if a package is installed but "
            "not appearing here.",
            len(languages), LANGUAGES_GROUP, languages, _MIN_LANGUAGES_FOR_COMPARISON,
        )
        return 2

    logger.info(
        "Comparing %d registered languages: %s (restricted to the %d rich "
        "cross-language / shared-39 domains: %s)",
        len(languages), languages, len(_RICH_AND_SHARED39_IDS), sorted(_RICH_AND_SHARED39_IDS),
    )
    per_language_supported = {
        name: supported_domain_ids(name) & _RICH_AND_SHARED39_IDS for name in languages
    }
    missing_by_language = compare_supported_domain_sets(per_language_supported)

    ok = True
    for name in languages:
        missing = missing_by_language[name]
        if missing:
            ok = False
            logger.error(
                "G3 VIOLATION: %s's derived supported-domain set (restricted "
                "to the rich cross-language/shared-39 scope) is missing %d "
                "domain(s) that at least one other registered language "
                "supports: %s. %s.supported(restricted)=%s",
                name, len(missing), sorted(missing), name, sorted(per_language_supported[name]),
            )

    if ok:
        agreed = per_language_supported[languages[0]]
        logger.info(
            "G3 holds: all %d registered languages' (%s) derived "
            "supported-domain sets, restricted to the rich cross-language/"
            "shared-39 scope, are identical: %s",
            len(languages), languages, sorted(agreed),
        )

    return 0 if ok else 1


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 = G3 holds, 1 = a divergence was found, 2 = the
        non-vacuity self-test failed or fewer than 2 languages are
        registered).
    """
    parser = argparse.ArgumentParser(
        description=(
            "Prove every registered datrix.languages plugin's derived "
            "SUPPORTED domain set, restricted to the rich cross-language / "
            "shared-39 domain scope, is identical (G3 final)."
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
    logger.info(
        "Non-vacuity self-test passed: the comparator reports zero "
        "divergence for a synthetic matching pair and correctly detects a "
        "synthetic forced mismatch."
    )

    if args.self_test:
        return 0

    return check_supported_domain_parity()


if __name__ == "__main__":
    sys.exit(main())
