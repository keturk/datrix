"""Tests for BUILTIN_REGISTRY and render_builtin_mappings_skeleton().

Verifies:
- Registry covers every (category, method) from the Python and TypeScript mapper tables.
- Keys mapped by both languages are CANONICAL; single-language keys are LANGUAGE_SPECIFIC.
- Each BuiltinDecl's receiver matches the Python mapper's transform for the same key.
- Each BuiltinDecl's arity brackets the Python mapper's placeholder/default counts.
- render_builtin_mappings_skeleton() emits one NotImplementedError slot per CANONICAL key
  and the rendered module is valid Python (ast.parse succeeds).
- No emission strings appear in builtin_registry.py.
- BuiltinCoverage is distinct from any MappingRequirement enum.

Relocated from datrix-codegen-common/tests/unit/transpiler/ to avoid cross-package
boundary violations: datrix_codegen_common must not import datrix_codegen_python
or datrix_codegen_typescript.  These tests are cross-package by design and belong
at the repo level (datrix/tests/integration/).
"""

from __future__ import annotations

import ast
import inspect
import re

import pytest

from datrix_codegen_common.transpiler.builtin_registry import (
    BUILTIN_REGISTRY,
    BuiltinCoverage,
    BuiltinDecl,
    BuiltinKey,
    Receiver,
)
from datrix_codegen_common.transpiler.builtin_mappings_skeleton import (
    render_builtin_mappings_skeleton,
)
from datrix_codegen_python.transpiler.builtins import (
    PYTHON_BUILTIN_MAPPINGS,
    PYTHON_EMAIL_MAPPINGS,
    PYTHON_SMS_MAPPINGS,
    PYTHON_PUSH_MAPPINGS,
)
from datrix_codegen_typescript.transpiler.builtins import (
    TS_BUILTIN_MAPPINGS,
    TS_EMAIL_MAPPINGS,
    TS_SMS_MAPPINGS,
    TS_PUSH_MAPPINGS,
)


# ---------------------------------------------------------------------------
# Helpers: collect the full (category, method) key sets for each language.
# Provider-specific tables (Email, SMS, Push) contribute their keys too --
# they are part of the mapper's effective key set.
# ---------------------------------------------------------------------------

def _py_all_keys() -> frozenset[BuiltinKey]:
    """All keys the Python mapper can emit (base + at least one provider variant)."""
    keys: set[BuiltinKey] = set(PYTHON_BUILTIN_MAPPINGS)
    for provider_map in PYTHON_EMAIL_MAPPINGS.values():
        keys.update(provider_map)
    for provider_map in PYTHON_SMS_MAPPINGS.values():
        keys.update(provider_map)
    for provider_map in PYTHON_PUSH_MAPPINGS.values():
        keys.update(provider_map)
    return frozenset(keys)


def _ts_all_keys() -> frozenset[BuiltinKey]:
    """All keys the TypeScript mapper can emit (base + at least one provider variant)."""
    keys: set[BuiltinKey] = set(TS_BUILTIN_MAPPINGS)
    for provider_map in TS_EMAIL_MAPPINGS.values():
        keys.update(provider_map)
    for provider_map in TS_SMS_MAPPINGS.values():
        keys.update(provider_map)
    for provider_map in TS_PUSH_MAPPINGS.values():
        keys.update(provider_map)
    return frozenset(keys)


# ---------------------------------------------------------------------------
# Test: registry covers every key from both language mapper tables.
# ---------------------------------------------------------------------------

class TestRegistryCoversAllLanguageKeys:
    """BUILTIN_REGISTRY must contain an entry for every key in either language."""

    def test_covers_all_python_keys(self) -> None:
        py_keys = _py_all_keys()
        missing = py_keys - set(BUILTIN_REGISTRY)
        assert not missing, (
            f"BUILTIN_REGISTRY is missing {len(missing)} Python mapper key(s): "
            f"{sorted(missing)}"
        )

    def test_covers_all_typescript_keys(self) -> None:
        ts_keys = _ts_all_keys()
        missing = ts_keys - set(BUILTIN_REGISTRY)
        assert not missing, (
            f"BUILTIN_REGISTRY is missing {len(missing)} TypeScript mapper key(s): "
            f"{sorted(missing)}"
        )


# ---------------------------------------------------------------------------
# Test: coverage classification is consistent with actual language membership.
# ---------------------------------------------------------------------------

class TestCoverageClassification:
    """Keys in both languages are CANONICAL; single-language keys are LANGUAGE_SPECIFIC."""

    def test_both_language_keys_are_canonical(self) -> None:
        py_keys = _py_all_keys()
        ts_keys = _ts_all_keys()
        intersection = py_keys & ts_keys
        wrong: list[BuiltinKey] = []
        for key in intersection:
            decl = BUILTIN_REGISTRY.get(key)
            if decl is not None and decl.coverage != BuiltinCoverage.CANONICAL:
                wrong.append(key)
        assert not wrong, (
            f"Keys in BOTH Python and TypeScript should be CANONICAL, but are not: "
            f"{sorted(wrong)}"
        )

    def test_single_language_keys_are_language_specific(self) -> None:
        py_keys = _py_all_keys()
        ts_keys = _ts_all_keys()
        py_only = py_keys - ts_keys
        ts_only = ts_keys - py_keys
        single_language = py_only | ts_only
        wrong: list[BuiltinKey] = []
        for key in single_language:
            decl = BUILTIN_REGISTRY.get(key)
            if decl is not None and decl.coverage != BuiltinCoverage.LANGUAGE_SPECIFIC:
                wrong.append(key)
        assert not wrong, (
            f"Keys in exactly ONE language should be LANGUAGE_SPECIFIC, but are not: "
            f"{sorted(wrong)}"
        )

    def test_canonical_keys_exist_in_registry(self) -> None:
        canonical = [
            k for k, d in BUILTIN_REGISTRY.items()
            if d.coverage == BuiltinCoverage.CANONICAL
        ]
        assert len(canonical) > 0, "No CANONICAL keys found in registry"

    def test_language_specific_keys_exist_in_registry(self) -> None:
        ls_keys = [
            k for k, d in BUILTIN_REGISTRY.items()
            if d.coverage == BuiltinCoverage.LANGUAGE_SPECIFIC
        ]
        assert len(ls_keys) > 0, "No LANGUAGE_SPECIFIC keys found in registry"


# ---------------------------------------------------------------------------
# Test: BuiltinDecl integrity
# ---------------------------------------------------------------------------

class TestBuiltinDeclIntegrity:
    """Every BuiltinDecl in the registry has valid field values."""

    def test_all_entries_are_builtin_decl(self) -> None:
        for key, decl in BUILTIN_REGISTRY.items():
            assert isinstance(decl, BuiltinDecl), f"Entry {key!r} is not a BuiltinDecl"

    def test_key_matches_decl_category_method(self) -> None:
        for (cat, meth), decl in BUILTIN_REGISTRY.items():
            assert decl.category == cat, (
                f"Key ({cat!r}, {meth!r}) has decl.category={decl.category!r}"
            )
            assert decl.method == meth, (
                f"Key ({cat!r}, {meth!r}) has decl.method={decl.method!r}"
            )

    def test_receiver_is_valid_enum(self) -> None:
        valid = set(Receiver)
        for key, decl in BUILTIN_REGISTRY.items():
            assert decl.receiver in valid, f"{key!r}: invalid receiver {decl.receiver!r}"

    def test_arity_min_lte_max(self) -> None:
        for key, decl in BUILTIN_REGISTRY.items():
            if decl.arity.max_args is not None:
                assert decl.arity.min_args <= decl.arity.max_args, (
                    f"{key!r}: min_args={decl.arity.min_args} > max_args={decl.arity.max_args}"
                )

    def test_python_mapper_receiver_matches_registry(self) -> None:
        """Python mapper transform must equal registry receiver.value for every shared key.

        The registry uses Python as the reference implementation for all zero-arg
        Array PROPERTY receivers.  Any key present in both BUILTIN_REGISTRY and
        PYTHON_BUILTIN_MAPPINGS must have matching receiver/transform values.
        """
        py_base_keys: set[BuiltinKey] = set(PYTHON_BUILTIN_MAPPINGS)
        mismatches: list[str] = []
        for key in py_base_keys:
            decl = BUILTIN_REGISTRY.get(key)
            if decl is None:
                continue
            bm = PYTHON_BUILTIN_MAPPINGS[key]
            if bm.transform != decl.receiver.value:
                mismatches.append(
                    f"({key[0]!r}, {key[1]!r}): "
                    f"mapper transform={bm.transform!r} != registry receiver={decl.receiver.value!r}"
                )
        assert not mismatches, (
            f"Python mapper transform disagrees with registry receiver for "
            f"{len(mismatches)} key(s):\n" + "\n".join(sorted(mismatches))
        )

    def test_python_mapper_arity_within_registry_bounds(self) -> None:
        """Python mapper DSL calling convention must fall within registry arity bounds."""
        py_base_keys: set[BuiltinKey] = set(PYTHON_BUILTIN_MAPPINGS)
        violations: list[str] = []
        for key in py_base_keys:
            decl = BUILTIN_REGISTRY.get(key)
            if decl is None:
                continue
            bm = PYTHON_BUILTIN_MAPPINGS[key]
            indices = [int(m) for m in re.findall(r"\{(\d+)\}", bm.expression)]
            if not indices:
                total_placeholders = 0
            elif bm.transform == "static_call":
                total_placeholders = max(indices) + 1
            else:
                # method_on_target / property_on_target: {0} is the implicit target
                total_placeholders = max(indices)  # {1}->1 arg, {2}->2 args, etc.
            # Defaults fill trailing placeholder slots, reducing the caller's minimum
            min_caller_args = total_placeholders - len(bm.defaults)
            max_caller_args = total_placeholders
            reg_min = decl.arity.min_args
            reg_max = decl.arity.max_args
            if reg_min > max_caller_args:
                violations.append(
                    f"({key[0]!r}, {key[1]!r}): "
                    f"registry min_args={reg_min} > mapper max_caller_args={max_caller_args} "
                    f"(expression cannot hold that many args)"
                )
            if reg_max is not None and reg_max < max_caller_args:
                violations.append(
                    f"({key[0]!r}, {key[1]!r}): "
                    f"registry max_args={reg_max} < mapper max_caller_args={max_caller_args}"
                )
        assert not violations, (
            f"Python mapper DSL calling convention is outside registry arity bounds "
            f"for {len(violations)} key(s):\n" + "\n".join(sorted(violations))
        )

    def test_no_emission_strings(self) -> None:
        """No Python or TS emission strings should appear in the registry module."""
        import datrix_codegen_common.transpiler.builtin_registry as registry_mod
        source = inspect.getsource(registry_mod)
        # These are characteristic of per-language emission (import statements, method calls)
        emission_markers = [
            ".strip()",
            ".trim()",
            "math.floor",
            "Math.floor",
            "import datetime",
            "import re",
        ]
        for marker in emission_markers:
            assert marker not in source, (
                f"Emission string {marker!r} found in builtin_registry.py -- "
                "emission strings must NOT appear in the shared registry"
            )


# ---------------------------------------------------------------------------
# Test: BuiltinCoverage is distinct from any MappingRequirement
# ---------------------------------------------------------------------------

class TestBuiltinCoverageDistinctness:
    """BuiltinCoverage must not be merged with or confused with MappingRequirement."""

    def test_builtin_coverage_has_expected_members(self) -> None:
        member_names = {m.name for m in BuiltinCoverage}
        assert "CANONICAL" in member_names
        assert "LANGUAGE_SPECIFIC" in member_names

    def test_builtin_coverage_values_are_strings(self) -> None:
        for member in BuiltinCoverage:
            assert isinstance(member.value, str), (
                f"BuiltinCoverage.{member.name}.value should be str, got {type(member.value)}"
            )

    def test_builtin_coverage_is_not_mapping_requirement(self) -> None:
        # MappingRequirement (Design 015) should NOT be the same class.
        # We just verify BuiltinCoverage is its own distinct enum class.
        assert BuiltinCoverage.__name__ == "BuiltinCoverage"
        member_names = {m.name for m in BuiltinCoverage}
        # MappingRequirement members are CORE_REQUIRED, USED_REQUIRED, EXPERIMENTAL
        assert "CORE_REQUIRED" not in member_names
        assert "USED_REQUIRED" not in member_names
        assert "EXPERIMENTAL" not in member_names


# ---------------------------------------------------------------------------
# Test: render_builtin_mappings_skeleton()
# ---------------------------------------------------------------------------

class TestRenderBuiltinMappingsSkeleton:
    """render_builtin_mappings_skeleton() emits a valid skeleton module."""

    def test_renders_without_error(self) -> None:
        text = render_builtin_mappings_skeleton()
        assert isinstance(text, str)
        assert len(text) > 100

    def test_contains_one_slot_per_canonical_key(self) -> None:
        text = render_builtin_mappings_skeleton()
        canonical_keys = [
            key
            for key, decl in BUILTIN_REGISTRY.items()
            if decl.coverage == BuiltinCoverage.CANONICAL
        ]
        for (cat, meth) in canonical_keys:
            assert f'"{cat}"' in text, f"Category {cat!r} not found in skeleton"
            assert f'"{meth}"' in text, f"Method {meth!r} not found in skeleton"

    def test_raises_not_implemented_error_in_skeleton(self) -> None:
        text = render_builtin_mappings_skeleton()
        assert "NotImplementedError" in text, (
            "Skeleton must raise NotImplementedError for unfilled slots"
        )

    def test_language_specific_keys_excluded_from_skeleton(self) -> None:
        text = render_builtin_mappings_skeleton()
        ls_keys = [
            key
            for key, decl in BUILTIN_REGISTRY.items()
            if decl.coverage == BuiltinCoverage.LANGUAGE_SPECIFIC
        ]
        # Language-specific keys should NOT appear as skeleton slots.
        for (cat, meth) in ls_keys:
            slot_pattern = f'("{cat}", "{meth}"): _UNFILLED'
            assert slot_pattern not in text, (
                f"LANGUAGE_SPECIFIC key ({cat!r}, {meth!r}) should not be a "
                f"skeleton slot but found: {slot_pattern!r}"
            )

    def test_no_emission_strings_in_skeleton(self) -> None:
        text = render_builtin_mappings_skeleton()
        emission_markers = [".strip()", ".trim()", "math.floor", "Math.floor"]
        for marker in emission_markers:
            assert marker not in text, (
                f"Emission string {marker!r} found in skeleton output -- "
                "skeleton must not contain emission strings"
            )

    def test_skeleton_count_matches_canonical_count(self) -> None:
        text = render_builtin_mappings_skeleton()
        canonical_count = sum(
            1 for d in BUILTIN_REGISTRY.values()
            if d.coverage == BuiltinCoverage.CANONICAL
        )
        # Each canonical key produces exactly one "): _UNFILLED(" slot call in the skeleton.
        slot_count = text.count("): _UNFILLED(")
        assert slot_count == canonical_count, (
            f"Expected {canonical_count} _UNFILLED slots, got {slot_count}"
        )

    def test_skeleton_module_parses_as_valid_python(self) -> None:
        """The rendered skeleton must be valid Python source (ast.parse must not raise)."""
        text = render_builtin_mappings_skeleton()
        try:
            ast.parse(text)
        except SyntaxError as exc:
            raise AssertionError(
                f"render_builtin_mappings_skeleton() produced invalid Python: {exc}\n"
                f"--- skeleton start ---\n{text[:500]}\n--- skeleton end (truncated) ---"
            ) from exc


# ---------------------------------------------------------------------------
# Test: registry size sanity check
# ---------------------------------------------------------------------------

class TestRegistrySize:
    """Registry should be substantial -- not a stub."""

    def test_registry_has_minimum_entries(self) -> None:
        # Both mapper tables have ~500+ entries combined.
        assert len(BUILTIN_REGISTRY) >= 300, (
            f"Registry has only {len(BUILTIN_REGISTRY)} entries -- likely incomplete"
        )

    def test_canonical_coverage_substantial(self) -> None:
        canonical = [d for d in BUILTIN_REGISTRY.values() if d.coverage == BuiltinCoverage.CANONICAL]
        assert len(canonical) >= 200, (
            f"Only {len(canonical)} CANONICAL entries -- expected 200+"
        )
