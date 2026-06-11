"""Smoke tests for the canonical/language-specific builtin parity split (task 63-04).

The full behavioural test suite (missing canonical key fails; language-specific
key is report-only) is in task 63-08.  This file covers the smoke case: that
the real Python and TypeScript profiles produce no hard-failure issues.

Relocated from datrix-codegen-common/tests/unit/transpiler/ to avoid cross-package
boundary violations: datrix_codegen_common must not import datrix_codegen_python
or datrix_codegen_typescript.  These tests are cross-package by design and belong
at the repo level (datrix/tests/integration/).
"""

from __future__ import annotations

import dataclasses
import logging

import pytest

from datrix_common.transpiler.builtins import BuiltinMapping, BuiltinMethodMapperBase
from datrix_codegen_common.transpiler.builtin_registry import (
    BUILTIN_REGISTRY,
    BuiltinCoverage,
)
from datrix_codegen_common.transpiler.parity_checker import (
    _canonical_builtin_keys,
    validate_builtin_parity,
)
from datrix_codegen_common.transpiler.profile import BuiltinProfile
from datrix_codegen_python.profile import PYTHON_PROFILE
from datrix_codegen_typescript.profile import TS_PROFILE

# A canonical key guaranteed to appear in BUILTIN_REGISTRY with CANONICAL coverage.
# Using ("String", "trim") as it is stable and fundamental.
_CANONICAL_KEY: tuple[str, str] = ("String", "trim")

# A language-specific key that is genuinely in the registry as LANGUAGE_SPECIFIC.
# ("Regex", "findAll") exists only in the Python mapper -- it is absent from TS.
_LANG_SPECIFIC_KEY: tuple[str, str] = ("Regex", "findAll")


def _make_profile_with_mapper(
    base_profile: object,
    modified_mappings: dict[tuple[str, str], BuiltinMapping],
) -> object:
    """Return a new LanguageProfile whose builtin mapper uses *modified_mappings*.

    Constructs the mapper without registry validation (``registry=None``) so
    that test scenarios with intentionally missing CANONICAL keys can be built
    without triggering the mapper's own construction-time guard.

    Args:
        base_profile: A real :class:`~datrix_codegen_common.transpiler.profile.LanguageProfile`.
        modified_mappings: The mapping dict for the new mapper.

    Returns:
        A new ``LanguageProfile`` with the replacement ``BuiltinProfile``.
    """
    new_mapper = BuiltinMethodMapperBase(modified_mappings, registry=None)
    new_builtins = BuiltinProfile(mapper=new_mapper)
    return dataclasses.replace(base_profile, builtins=new_builtins)  # type: ignore[call-overload]


@pytest.mark.integration
class TestBuiltinParitySplitSmoke:
    def test_current_profiles_pass(self) -> None:
        issues = validate_builtin_parity({"python": PYTHON_PROFILE, "typescript": TS_PROFILE})
        assert issues == [], f"Builtin parity gaps: {issues}"


@pytest.mark.unit
class TestBuiltinParityCanonicalSplit:
    """Comprehensive tests for the canonical / language-specific split in validate_builtin_parity."""

    # ------------------------------------------------------------------
    # (a) Green baseline
    # ------------------------------------------------------------------

    def test_real_profiles_produce_no_issues(self) -> None:
        """Green baseline: real Python + TS profiles have zero hard-fail issues."""
        issues = validate_builtin_parity({"python": PYTHON_PROFILE, "typescript": TS_PROFILE})
        assert issues == [], (
            "Real production profiles must not produce any parity issues. "
            f"Found: {issues}"
        )

    # ------------------------------------------------------------------
    # (b) Missing canonical key -> hard failure
    # ------------------------------------------------------------------

    def test_missing_canonical_key_produces_hard_fail_issue(self) -> None:
        """A profile missing a CANONICAL key yields an issue naming that key + language."""
        assert _CANONICAL_KEY in BUILTIN_REGISTRY, (
            f"Test fixture {_CANONICAL_KEY!r} must be in BUILTIN_REGISTRY"
        )
        assert BUILTIN_REGISTRY[_CANONICAL_KEY].coverage is BuiltinCoverage.CANONICAL, (
            f"{_CANONICAL_KEY!r} must be CANONICAL coverage for this test"
        )

        # Build Python mapper with the canonical key removed.
        reduced_mappings = {
            k: v
            for k, v in PYTHON_PROFILE.builtins.mapper.mappings.items()
            if k != _CANONICAL_KEY
        }
        python_without_canonical = _make_profile_with_mapper(PYTHON_PROFILE, reduced_mappings)

        issues = validate_builtin_parity(
            {"python": python_without_canonical, "typescript": TS_PROFILE}
        )

        assert issues, "Expected at least one issue when a CANONICAL key is missing"
        # The issue must name the missing key and the language.
        combined = " ".join(issues)
        assert "python" in combined, (
            f"Issue must name the language 'python'. Issues: {issues}"
        )
        assert "String" in combined, (
            f"Issue must name the category of the missing key. Issues: {issues}"
        )
        assert "trim" in combined, (
            f"Issue must name the method of the missing key. Issues: {issues}"
        )

    def test_missing_canonical_key_in_second_language_also_fails(self) -> None:
        """A canonical key missing from TypeScript (not Python) also produces a hard-fail issue."""
        reduced_mappings = {
            k: v
            for k, v in TS_PROFILE.builtins.mapper.mappings.items()
            if k != _CANONICAL_KEY
        }
        ts_without_canonical = _make_profile_with_mapper(TS_PROFILE, reduced_mappings)

        issues = validate_builtin_parity(
            {"python": PYTHON_PROFILE, "typescript": ts_without_canonical}
        )

        assert issues, "Expected at least one issue when TS is missing a CANONICAL key"
        combined = " ".join(issues)
        assert "typescript" in combined, (
            f"Issue must name the language 'typescript'. Issues: {issues}"
        )
        assert "String" in combined
        assert "trim" in combined

    def test_missing_canonical_key_names_count_in_issue(self) -> None:
        """Issue message includes the count of missing canonical keys."""
        reduced_mappings = {
            k: v
            for k, v in PYTHON_PROFILE.builtins.mapper.mappings.items()
            if k != _CANONICAL_KEY
        }
        python_without_canonical = _make_profile_with_mapper(PYTHON_PROFILE, reduced_mappings)

        issues = validate_builtin_parity(
            {"python": python_without_canonical, "typescript": TS_PROFILE}
        )

        # The issue message format is:
        # "Builtin parity: language 'python' missing N CANONICAL builtin(s): [...]."
        assert any("CANONICAL" in issue for issue in issues), (
            f"Issue must mention 'CANONICAL'. Issues: {issues}"
        )

    # ------------------------------------------------------------------
    # (c) Language-specific key: present in one, absent in other -> report-only
    # ------------------------------------------------------------------

    def test_language_specific_key_produces_no_issue(self, caplog: pytest.LogCaptureFixture) -> None:
        """A language-specific key present in one profile and absent from another is report-only (no issue)."""
        # Verify the test fixture is actually LANGUAGE_SPECIFIC in the registry.
        assert _LANG_SPECIFIC_KEY in BUILTIN_REGISTRY, (
            f"Test fixture {_LANG_SPECIFIC_KEY!r} must be in BUILTIN_REGISTRY"
        )
        assert BUILTIN_REGISTRY[_LANG_SPECIFIC_KEY].coverage is BuiltinCoverage.LANGUAGE_SPECIFIC, (
            f"{_LANG_SPECIFIC_KEY!r} must be LANGUAGE_SPECIFIC coverage for this test"
        )

        # ("Regex", "findAll") is already present in Python mapper, absent from TS.
        # Verify this is the case with the real profiles.
        assert _LANG_SPECIFIC_KEY in PYTHON_PROFILE.builtins.mapper.mappings, (
            f"{_LANG_SPECIFIC_KEY!r} must be in Python mapper mappings for this test"
        )
        assert _LANG_SPECIFIC_KEY not in TS_PROFILE.builtins.mapper.mappings, (
            f"{_LANG_SPECIFIC_KEY!r} must be absent from TS mapper mappings for this test"
        )

        with caplog.at_level(logging.INFO, logger="datrix_codegen_common.transpiler.parity_checker"):
            issues = validate_builtin_parity(
                {"python": PYTHON_PROFILE, "typescript": TS_PROFILE}
            )

        # Must produce NO issue (report-only, not a hard failure).
        assert issues == [], (
            f"Language-specific key must not produce a hard-fail issue. Issues: {issues}"
        )

        # Must emit an INFO log for the asymmetric key.
        log_messages = [r.message for r in caplog.records if r.levelno == logging.INFO]
        lang_specific_logs = [
            m for m in log_messages if "builtin_language_specific" in m
        ]
        assert lang_specific_logs, (
            "Expected at least one 'builtin_language_specific' INFO log for the "
            f"asymmetric key {_LANG_SPECIFIC_KEY!r}. "
            f"INFO logs observed: {log_messages}"
        )

    def test_language_specific_log_names_key_and_presence(self, caplog: pytest.LogCaptureFixture) -> None:
        """The INFO log for a language-specific key names the key, present_in, and absent_in."""
        with caplog.at_level(logging.INFO, logger="datrix_codegen_common.transpiler.parity_checker"):
            validate_builtin_parity(
                {"python": PYTHON_PROFILE, "typescript": TS_PROFILE}
            )

        lang_specific_logs = [
            r.getMessage()
            for r in caplog.records
            if r.levelno == logging.INFO and "builtin_language_specific" in r.getMessage()
        ]
        assert lang_specific_logs, (
            "Expected 'builtin_language_specific' INFO log entries but found none"
        )

        # At least one log must reference the Regex.findAll language-specific key.
        regex_findall_log = next(
            (m for m in lang_specific_logs if "Regex" in m and "findAll" in m),
            None,
        )
        assert regex_findall_log is not None, (
            f"Expected a log entry mentioning Regex.findAll. "
            f"Language-specific logs: {lang_specific_logs}"
        )
        assert "python" in regex_findall_log, (
            f"Log must name the language that has the key (python). Log: {regex_findall_log}"
        )
        assert "typescript" in regex_findall_log, (
            f"Log must name the language that lacks the key (typescript). Log: {regex_findall_log}"
        )

    def test_synthetic_language_specific_key_not_in_registry_is_report_only(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A key present in one profile but absent from both registry and other profile is report-only."""
        # Add a completely synthetic key not in BUILTIN_REGISTRY to Python's mapper.
        SYNTHETIC_KEY: tuple[str, str] = ("FakeSynthetic", "onlyInThisLang")
        assert SYNTHETIC_KEY not in BUILTIN_REGISTRY, (
            f"Synthetic test key {SYNTHETIC_KEY!r} must not exist in BUILTIN_REGISTRY"
        )

        synthetic_mapping = BuiltinMapping(
            category="FakeSynthetic",
            method="onlyInThisLang",
            transform="static_call",
            expression="fakeSynthetic({0})",
            imports=frozenset(),
            defaults=(),
        )
        extended_mappings: dict[tuple[str, str], BuiltinMapping] = {
            **PYTHON_PROFILE.builtins.mapper.mappings,
            SYNTHETIC_KEY: synthetic_mapping,
        }
        python_with_extra = _make_profile_with_mapper(PYTHON_PROFILE, extended_mappings)

        with caplog.at_level(logging.INFO, logger="datrix_codegen_common.transpiler.parity_checker"):
            issues = validate_builtin_parity(
                {"python": python_with_extra, "typescript": TS_PROFILE}
            )

        # Must produce NO issue -- synthetic language-specific keys are report-only.
        assert issues == [], (
            f"A key absent from CANONICAL set must not produce a hard-fail issue. Issues: {issues}"
        )

        # Must emit an INFO log for the synthetic key.
        lang_specific_logs = [
            r.getMessage()
            for r in caplog.records
            if r.levelno == logging.INFO and "builtin_language_specific" in r.getMessage()
        ]
        synthetic_log = next(
            (m for m in lang_specific_logs if "FakeSynthetic" in m),
            None,
        )
        assert synthetic_log is not None, (
            f"Expected an INFO log for the synthetic key {SYNTHETIC_KEY!r}. "
            f"Language-specific logs: {lang_specific_logs}"
        )

    # ------------------------------------------------------------------
    # (d) Empty profiles -> explicit issue
    # ------------------------------------------------------------------

    def test_empty_profiles_mapping_produces_explicit_issue(self) -> None:
        """Passing an empty profiles dict produces an explicit issue, not a silent pass."""
        issues = validate_builtin_parity({})
        assert issues, "Expected an issue for empty profiles mapping"
        combined = " ".join(issues)
        assert "empty" in combined.lower(), (
            f"Issue for empty profiles must say 'empty'. Issues: {issues}"
        )

    # ------------------------------------------------------------------
    # (e) Intersection invariant: CANONICAL <= Python mapper & TS mapper
    # ------------------------------------------------------------------

    def test_canonical_keys_are_subset_of_both_real_mappers(self) -> None:
        """Every CANONICAL key is present in both the Python and TypeScript mapper."""
        canonical = _canonical_builtin_keys()
        assert canonical, "CANONICAL_BUILTINS must be non-empty (registry must have CANONICAL entries)"

        python_keys = frozenset(PYTHON_PROFILE.builtins.mapper.mappings.keys())
        ts_keys = frozenset(TS_PROFILE.builtins.mapper.mappings.keys())

        missing_from_python = sorted(canonical - python_keys)
        missing_from_ts = sorted(canonical - ts_keys)

        assert not missing_from_python, (
            f"CANONICAL keys missing from Python mapper (seed-green invariant broken): "
            f"{missing_from_python}"
        )
        assert not missing_from_ts, (
            f"CANONICAL keys missing from TypeScript mapper (seed-green invariant broken): "
            f"{missing_from_ts}"
        )

    def test_canonical_set_matches_builtin_registry_canonical_coverage(self) -> None:
        """_canonical_builtin_keys() returns exactly the BUILTIN_REGISTRY entries with CANONICAL coverage."""
        canonical = _canonical_builtin_keys()
        expected = frozenset(
            k for k, decl in BUILTIN_REGISTRY.items()
            if decl.coverage is BuiltinCoverage.CANONICAL
        )
        assert canonical == expected, (
            "_canonical_builtin_keys() must match the CANONICAL-filtered BUILTIN_REGISTRY exactly. "
            f"Difference: {canonical.symmetric_difference(expected)}"
        )

    def test_canonical_set_is_non_empty(self) -> None:
        """The canonical builtin set must not be empty (framework has real shared builtins)."""
        canonical = _canonical_builtin_keys()
        assert len(canonical) > 0, "CANONICAL set must be non-empty"

    def test_language_specific_keys_not_in_canonical_set(self) -> None:
        """All LANGUAGE_SPECIFIC registry entries are absent from the canonical set."""
        canonical = _canonical_builtin_keys()
        language_specific_in_canonical = [
            k
            for k, decl in BUILTIN_REGISTRY.items()
            if decl.coverage is BuiltinCoverage.LANGUAGE_SPECIFIC and k in canonical
        ]
        assert not language_specific_in_canonical, (
            f"LANGUAGE_SPECIFIC entries must not appear in the canonical set: "
            f"{language_specific_in_canonical}"
        )

    def test_geo_distance_km_is_canonical(self) -> None:
        """Geo.distanceKm was promoted to CANONICAL (mapped by both Python and TS in phase 63)."""
        geo_km_key: tuple[str, str] = ("Geo", "distanceKm")
        assert geo_km_key in BUILTIN_REGISTRY, "Geo.distanceKm must be in BUILTIN_REGISTRY"
        assert BUILTIN_REGISTRY[geo_km_key].coverage is BuiltinCoverage.CANONICAL, (
            "Geo.distanceKm must have CANONICAL coverage after phase 63 promotion"
        )
        canonical = _canonical_builtin_keys()
        assert geo_km_key in canonical, (
            "Geo.distanceKm must appear in the canonical builtin key set"
        )
        # Must be mapped by both real profiles.
        assert geo_km_key in PYTHON_PROFILE.builtins.mapper.mappings, (
            "Geo.distanceKm must be mapped by the Python profile"
        )
        assert geo_km_key in TS_PROFILE.builtins.mapper.mappings, (
            "Geo.distanceKm must be mapped by the TypeScript profile"
        )

    # ------------------------------------------------------------------
    # (f) Single-language profile -- canonical gap still detected
    # ------------------------------------------------------------------

    def test_single_profile_missing_canonical_key_produces_issue(self) -> None:
        """validate_builtin_parity works with any number of profiles (not just exactly 2)."""
        reduced_mappings = {
            k: v
            for k, v in PYTHON_PROFILE.builtins.mapper.mappings.items()
            if k != _CANONICAL_KEY
        }
        python_without_canonical = _make_profile_with_mapper(PYTHON_PROFILE, reduced_mappings)

        # Pass only a single language profile.
        issues = validate_builtin_parity({"only_lang": python_without_canonical})

        assert issues, (
            "Missing CANONICAL key must be detected even with a single-language profile"
        )
        combined = " ".join(issues)
        assert "only_lang" in combined, (
            f"Issue must name the language 'only_lang'. Issues: {issues}"
        )
