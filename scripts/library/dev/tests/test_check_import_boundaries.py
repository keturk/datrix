"""Unit tests for the import-boundary scanner's allowed-subtree rule model.

Proves the platform -> codegen-common subtree contract is enforced exactly:
every allowed language-agnostic subtree is permitted, and every denied
language-shaped subtree (and every language generator package) is flagged.

Covers task 64-02: guard that the ``allowed_subtrees`` carve-out does not
silently stop enforcing the denied subtree list.
"""

import importlib.util
import sys
import types
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Scanner module bootstrap
# ---------------------------------------------------------------------------
# check-import-boundaries.py has a hyphen in its name, which prevents normal
# import syntax.  We load it by file path and register it under a safe alias
# so subsequent attribute access works just like a normal module import.

_SCANNER_PATH = (
    Path(__file__).resolve().parents[4] / "scripts" / "dev" / "check-import-boundaries.py"
)

_MODULE_ALIAS = "check_import_boundaries"

if _MODULE_ALIAS not in sys.modules:
    _spec = importlib.util.spec_from_file_location(_MODULE_ALIAS, _SCANNER_PATH)
    if _spec is None or _spec.loader is None:
        raise ImportError(f"Could not load scanner module from {_SCANNER_PATH}")
    _mod: types.ModuleType = importlib.util.module_from_spec(_spec)
    sys.modules[_MODULE_ALIAS] = _mod
    _spec.loader.exec_module(_mod)  # type: ignore[union-attr]

_scanner = sys.modules[_MODULE_ALIAS]

is_forbidden_import = _scanner.is_forbidden_import
BOUNDARY_RULES = _scanner.BOUNDARY_RULES
BoundaryRule = _scanner.BoundaryRule
PLATFORM_CODEGEN_COMMON_ALLOWED_SUBTREES = _scanner.PLATFORM_CODEGEN_COMMON_ALLOWED_SUBTREES

# ---------------------------------------------------------------------------
# Constants referenced in the tests — pulled from the module so changes to
# the constant propagate to both the rule and the tests automatically.
# ---------------------------------------------------------------------------

# All six allowed subtree roots.  The test asserts explicit membership so a
# silent shrink of the constant fails here.
_EXPECTED_ALLOWED_SUBTREES: frozenset[str] = frozenset(
    [
        "datrix_codegen_common.gendsl",
        "datrix_codegen_common.dashboards",
        "datrix_codegen_common.algorithms.serverless",
        "datrix_codegen_common.context_models.serverless",
        "datrix_codegen_common.context_models.replayable_ingestion",
        "datrix_codegen_common.enums",
    ]
)

# A representative platform source package used throughout the positive and
# negative cases.
_PLATFORM_SOURCE = "datrix_codegen_aws"

# The forbidden prefix that platform rules list for datrix_codegen_common.
_COMMON_PREFIX = "datrix_codegen_common"

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _is_forbidden(source: str, imported: str) -> bool:
    """Call is_forbidden_import using the platform rule's allowed_subtrees."""
    rule = BOUNDARY_RULES[source]
    for prefix in rule.forbidden_prefixes:
        if is_forbidden_import(source, imported, prefix, rule.allowed_subtrees):
            return True
    return False


# ---------------------------------------------------------------------------
# Test classes
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExpectedAllowedSubtreeSet:
    """The module constant matches the expected set exactly."""

    def test_constant_contains_all_expected_subtrees(self) -> None:
        for subtree in _EXPECTED_ALLOWED_SUBTREES:
            assert subtree in PLATFORM_CODEGEN_COMMON_ALLOWED_SUBTREES, (
                f"Expected {subtree!r} in PLATFORM_CODEGEN_COMMON_ALLOWED_SUBTREES "
                f"but it is absent — the constant was silently shrunk."
            )

    def test_constant_has_no_extra_subtrees(self) -> None:
        extra = PLATFORM_CODEGEN_COMMON_ALLOWED_SUBTREES - _EXPECTED_ALLOWED_SUBTREES
        assert not extra, (
            f"PLATFORM_CODEGEN_COMMON_ALLOWED_SUBTREES contains unexpected extra subtrees: {extra!r}. "
            f"Adding a seventh subtree requires a doc + rule edit and review."
        )


@pytest.mark.unit
class TestPlatformAllowedSubtrees:
    """Platform -> codegen-common subtree contract: allowed imports must NOT be flagged."""

    @pytest.mark.parametrize(
        "imported_module",
        [
            # gendsl root and children
            "datrix_codegen_common.gendsl",
            "datrix_codegen_common.gendsl.compiler",
            "datrix_codegen_common.gendsl.executor",
            "datrix_codegen_common.gendsl.registry_adapter",
            "datrix_codegen_common.gendsl.scope",
            # dashboards root and children
            "datrix_codegen_common.dashboards",
            "datrix_codegen_common.dashboards.builder",
            "datrix_codegen_common.dashboards.models",
            # algorithms.serverless (narrow leaf, not the full algorithms subtree)
            "datrix_codegen_common.algorithms.serverless",
            # context_models.serverless
            "datrix_codegen_common.context_models.serverless",
            # context_models.replayable_ingestion
            "datrix_codegen_common.context_models.replayable_ingestion",
            # enums root (DatabaseEngine lives inside as an attribute, module is enums)
            "datrix_codegen_common.enums",
        ],
    )
    def test_allowed_subtree_is_not_forbidden(self, imported_module: str) -> None:
        assert not _is_forbidden(_PLATFORM_SOURCE, imported_module), (
            f"Allowed import {imported_module!r} was incorrectly flagged as forbidden "
            f"for platform package {_PLATFORM_SOURCE!r}."
        )

    @pytest.mark.parametrize(
        "platform_source",
        [
            "datrix_codegen_docker",
            "datrix_codegen_k8s",
            "datrix_codegen_aws",
            "datrix_codegen_azure",
        ],
    )
    def test_gendsl_allowed_for_all_platform_packages(self, platform_source: str) -> None:
        """Each platform package carries the same allowed_subtrees carve-out."""
        assert not _is_forbidden(platform_source, "datrix_codegen_common.gendsl"), (
            f"datrix_codegen_common.gendsl should be allowed for {platform_source!r} "
            f"but was flagged as forbidden."
        )


@pytest.mark.unit
class TestPlatformDeniedSubtrees:
    """Platform -> codegen-common subtree contract: denied imports MUST be flagged."""

    @pytest.mark.parametrize(
        "imported_module",
        [
            # transpiler subtree is explicitly walled off
            "datrix_codegen_common.transpiler.shared_transpiler",
            # language-shaped context_models subtrees
            "datrix_codegen_common.context_models.entity",
            # language-shaped algorithms subtrees
            "datrix_codegen_common.algorithms.entity",
            # language generator packages
            "datrix_codegen_python",
            "datrix_codegen_python.generators.api",
            "datrix_codegen_typescript",
        ],
    )
    def test_denied_import_is_flagged(self, imported_module: str) -> None:
        assert _is_forbidden(_PLATFORM_SOURCE, imported_module), (
            f"Denied import {imported_module!r} was NOT flagged as forbidden "
            f"for platform package {_PLATFORM_SOURCE!r} — the deny list stopped being enforced."
        )


@pytest.mark.unit
class TestDottedBoundaryPrecision:
    """Subtree matching uses an exact-or-child rule, not raw string prefix matching."""

    def test_enums_other_is_not_treated_as_enums_subtree(self) -> None:
        """'enums_other' must NOT be permitted as a child of the 'enums' subtree."""
        imported = "datrix_codegen_common.enums_other"
        assert _is_forbidden(_PLATFORM_SOURCE, imported), (
            f"'datrix_codegen_common.enums_other' should be forbidden "
            f"(it is NOT a child of datrix_codegen_common.enums) but was permitted. "
            f"The subtree matcher must require a '.' separator, not a raw string prefix."
        )

    def test_enums_child_is_allowed(self) -> None:
        """'datrix_codegen_common.enums.DatabaseEngine' (from import form) is permitted."""
        imported = "datrix_codegen_common.enums.DatabaseEngine"
        assert not _is_forbidden(_PLATFORM_SOURCE, imported), (
            f"'datrix_codegen_common.enums.DatabaseEngine' should be allowed "
            f"(it is a direct child of the enums subtree) but was flagged as forbidden."
        )

    def test_algorithms_serverless_child_is_allowed(self) -> None:
        """A sub-module of algorithms.serverless is permitted."""
        imported = "datrix_codegen_common.algorithms.serverless.plan"
        assert not _is_forbidden(_PLATFORM_SOURCE, imported), (
            f"'datrix_codegen_common.algorithms.serverless.plan' should be allowed "
            f"(it is a child of the algorithms.serverless subtree) but was flagged."
        )

    def test_algorithms_serverless_sibling_is_denied(self) -> None:
        """'algorithms.serverlessX' must NOT be treated as a child of 'algorithms.serverless'."""
        imported = "datrix_codegen_common.algorithms.serverlessX"
        assert _is_forbidden(_PLATFORM_SOURCE, imported), (
            f"'datrix_codegen_common.algorithms.serverlessX' should be forbidden "
            f"(it is NOT a child of algorithms.serverless) but was permitted."
        )


@pytest.mark.unit
class TestCarveoutDoesNotLeakToOtherPackages:
    """The allowed_subtrees carve-out only applies to packages that explicitly opt in."""

    def test_datrix_common_still_forbids_codegen_python(self) -> None:
        """datrix_common has no allowed_subtrees; datrix_codegen_python must be forbidden."""
        source = "datrix_common"
        imported = "datrix_codegen_python"
        assert _is_forbidden(source, imported), (
            f"'datrix_codegen_python' should be forbidden for 'datrix_common' "
            f"(it has no allowed_subtrees carve-out) but was permitted. "
            f"The carve-out must not leak to packages that did not opt in."
        )

    def test_datrix_common_has_empty_allowed_subtrees(self) -> None:
        """Confirm that datrix_common's rule has no allowed_subtrees."""
        rule = BOUNDARY_RULES["datrix_common"]
        assert rule.allowed_subtrees == frozenset(), (
            f"datrix_common's BoundaryRule should have empty allowed_subtrees "
            f"but found: {rule.allowed_subtrees!r}"
        )

    def test_datrix_codegen_common_still_forbids_codegen_python(self) -> None:
        """datrix_codegen_common itself (not a platform) forbids datrix_codegen_python."""
        source = "datrix_codegen_common"
        imported = "datrix_codegen_python"
        assert _is_forbidden(source, imported), (
            f"'datrix_codegen_python' should be forbidden for 'datrix_codegen_common' "
            f"but was permitted."
        )

    def test_platform_rule_allowed_subtrees_is_nonempty(self) -> None:
        """Confirm that each platform rule carries a non-empty allowed_subtrees."""
        for platform in ("datrix_codegen_docker", "datrix_codegen_k8s", "datrix_codegen_aws", "datrix_codegen_azure"):
            rule = BOUNDARY_RULES[platform]
            assert rule.allowed_subtrees, (
                f"Platform rule for {platform!r} should have non-empty allowed_subtrees "
                f"but found: {rule.allowed_subtrees!r}"
            )
