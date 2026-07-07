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
SQL_CODEGEN_COMMON_ALLOWED_SUBTREES = _scanner.SQL_CODEGEN_COMMON_ALLOWED_SUBTREES
scan_file_for_provider_conditionals = _scanner.scan_file_for_provider_conditionals
check_provider_conditional_ratchet = _scanner.check_provider_conditional_ratchet

# ---------------------------------------------------------------------------
# Constants referenced in the tests — pulled from the module so changes to
# the constant propagate to both the rule and the tests automatically.
# ---------------------------------------------------------------------------

# All allowed subtree roots.  The test asserts explicit membership so a
# silent shrink of the constant fails here.
_EXPECTED_ALLOWED_SUBTREES: frozenset[str] = frozenset(
    [
        "datrix_codegen_common.gendsl",
        "datrix_codegen_common.dashboards",
        "datrix_codegen_common.algorithms.serverless",
        "datrix_codegen_common.context_models.serverless",
        "datrix_codegen_common.context_models.replayable_ingestion",
        "datrix_codegen_common.enums",
        "datrix_codegen_common.platform",
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
            # platform provider helpers/protocols
            "datrix_codegen_common.platform",
            "datrix_codegen_common.platform.runtime",
            "datrix_codegen_common.platform.value_objects",
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
        for platform in ("datrix_codegen_docker", "datrix_codegen_aws", "datrix_codegen_azure"):
            rule = BOUNDARY_RULES[platform]
            assert rule.allowed_subtrees, (
                f"Platform rule for {platform!r} should have non-empty allowed_subtrees "
                f"but found: {rule.allowed_subtrees!r}"
            )


@pytest.mark.unit
class TestSqlBoundaryRuleCoverage:
    """BOUNDARY_RULES contains an entry for datrix_codegen_sql and it enforces
    the sibling-language prohibition absolutely.

    Covers task 78-14: closing the scanner gap for the SQL generator package.
    """

    def test_sql_rule_exists_in_boundary_rules(self) -> None:
        """datrix_codegen_sql must have an entry in BOUNDARY_RULES."""
        assert "datrix_codegen_sql" in BOUNDARY_RULES, (
            "datrix_codegen_sql is absent from BOUNDARY_RULES — the SQL package "
            "is unrestricted and cross-language imports would go undetected."
        )

    def test_sql_rule_has_sql_codegen_common_allowed_subtrees(self) -> None:
        """The SQL rule must carry the SQL_CODEGEN_COMMON_ALLOWED_SUBTREES carve-out."""
        rule = BOUNDARY_RULES["datrix_codegen_sql"]
        assert rule.allowed_subtrees == SQL_CODEGEN_COMMON_ALLOWED_SUBTREES, (
            f"datrix_codegen_sql's allowed_subtrees should equal SQL_CODEGEN_COMMON_ALLOWED_SUBTREES "
            f"but found: {rule.allowed_subtrees!r}"
        )

    @pytest.mark.parametrize(
        "imported_module",
        [
            "datrix_codegen_typescript",
            "datrix_codegen_typescript.generators.persistence.mikroorm_migration_adapter",
            "datrix_codegen_python",
            "datrix_codegen_python.generators.api",
            "datrix_cli",
        ],
    )
    def test_sql_sibling_language_imports_are_forbidden(self, imported_module: str) -> None:
        """Sibling language and CLI imports must be flagged as forbidden for SQL."""
        rule = BOUNDARY_RULES["datrix_codegen_sql"]
        is_forbidden = any(
            is_forbidden_import("datrix_codegen_sql", imported_module, prefix, rule.allowed_subtrees)
            for prefix in rule.forbidden_prefixes
        )
        assert is_forbidden, (
            f"Import {imported_module!r} was NOT flagged as forbidden for datrix_codegen_sql — "
            f"the sibling-language prohibition must be absolute."
        )

    @pytest.mark.parametrize(
        "imported_module",
        [
            # gendsl subtree — SQL's GenDSL entry point
            "datrix_codegen_common.gendsl",
            "datrix_codegen_common.gendsl.compiler",
            "datrix_codegen_common.gendsl.executor",
            "datrix_codegen_common.gendsl.test_harness",
            # migration context model — SQL-specific but language-agnostic
            "datrix_codegen_common.context_models.migration",
            # migration orchestration adapter — shared SQL + TS migration adapter
            "datrix_codegen_common.orchestration.migration_adapter",
        ],
    )
    def test_sql_allowed_codegen_common_subtrees_are_not_forbidden(self, imported_module: str) -> None:
        """Language-agnostic codegen-common subtrees that SQL legitimately imports must not be flagged."""
        rule = BOUNDARY_RULES["datrix_codegen_sql"]
        is_forbidden = any(
            is_forbidden_import("datrix_codegen_sql", imported_module, prefix, rule.allowed_subtrees)
            for prefix in rule.forbidden_prefixes
        )
        assert not is_forbidden, (
            f"Allowed import {imported_module!r} was incorrectly flagged as forbidden "
            f"for datrix_codegen_sql — check SQL_CODEGEN_COMMON_ALLOWED_SUBTREES."
        )

    @pytest.mark.parametrize(
        "imported_module",
        [
            # transpiler is explicitly walled off
            "datrix_codegen_common.transpiler.shared_transpiler",
            # language-shaped context_models subtrees
            "datrix_codegen_common.context_models.entity",
            "datrix_codegen_common.context_models.schema",
            # algorithms subtrees (not serverless)
            "datrix_codegen_common.algorithms.entity",
        ],
    )
    def test_sql_denied_codegen_common_subtrees_are_forbidden(self, imported_module: str) -> None:
        """Language-shaped codegen-common subtrees must remain forbidden for SQL."""
        rule = BOUNDARY_RULES["datrix_codegen_sql"]
        is_forbidden = any(
            is_forbidden_import("datrix_codegen_sql", imported_module, prefix, rule.allowed_subtrees)
            for prefix in rule.forbidden_prefixes
        )
        assert is_forbidden, (
            f"Denied import {imported_module!r} was NOT flagged as forbidden for datrix_codegen_sql — "
            f"the allowed_subtrees carve-out must not be too broad."
        )


@pytest.mark.unit
class TestComponentBoundaryRuleCoverage:
    """BOUNDARY_RULES contains an entry for datrix_codegen_component and it enforces
    the sibling-language prohibition absolutely.

    Covers task 78-14: closing the scanner gap for the Component generator package.
    """

    def test_component_rule_exists_in_boundary_rules(self) -> None:
        """datrix_codegen_component must have an entry in BOUNDARY_RULES."""
        assert "datrix_codegen_component" in BOUNDARY_RULES, (
            "datrix_codegen_component is absent from BOUNDARY_RULES — the Component package "
            "is unrestricted and cross-language imports would go undetected."
        )

    def test_component_rule_has_empty_allowed_subtrees(self) -> None:
        """Component's rule has no allowed_subtrees (datrix_codegen_common is not restricted)."""
        rule = BOUNDARY_RULES["datrix_codegen_component"]
        assert rule.allowed_subtrees == frozenset(), (
            f"datrix_codegen_component's BoundaryRule should have empty allowed_subtrees "
            f"(datrix_codegen_common is not forbidden for Component) but found: {rule.allowed_subtrees!r}"
        )

    @pytest.mark.parametrize(
        "imported_module",
        [
            "datrix_codegen_typescript",
            "datrix_codegen_typescript.generators.api",
            "datrix_codegen_python",
            "datrix_codegen_python.generators.api",
            "datrix_cli",
        ],
    )
    def test_component_sibling_language_imports_are_forbidden(self, imported_module: str) -> None:
        """Sibling language and CLI imports must be flagged as forbidden for Component."""
        rule = BOUNDARY_RULES["datrix_codegen_component"]
        is_forbidden = any(
            is_forbidden_import("datrix_codegen_component", imported_module, prefix, rule.allowed_subtrees)
            for prefix in rule.forbidden_prefixes
        )
        assert is_forbidden, (
            f"Import {imported_module!r} was NOT flagged as forbidden for datrix_codegen_component — "
            f"the sibling-language prohibition must be absolute."
        )

    @pytest.mark.parametrize(
        "imported_module",
        [
            # Component freely imports datrix_codegen_common (not restricted)
            "datrix_codegen_common.gendsl.compiler",
            "datrix_codegen_common.gendsl.executor",
            "datrix_codegen_common.algorithms.serverless",
            "datrix_codegen_common.algorithms.nosql_connection",
            "datrix_codegen_common.context_models.serverless",
        ],
    )
    def test_component_codegen_common_imports_are_not_forbidden(self, imported_module: str) -> None:
        """datrix_codegen_common imports must NOT be flagged for Component (it is not restricted)."""
        rule = BOUNDARY_RULES["datrix_codegen_component"]
        is_forbidden = any(
            is_forbidden_import("datrix_codegen_component", imported_module, prefix, rule.allowed_subtrees)
            for prefix in rule.forbidden_prefixes
        )
        assert not is_forbidden, (
            f"Import {imported_module!r} was incorrectly flagged as forbidden for datrix_codegen_component — "
            f"datrix_codegen_common is not restricted for Component."
        )


@pytest.mark.unit
class TestProviderConditionalScanner:
    """The I6 successor ratchet's AST scanner (design 023, invariant I6, DI-4/DI-5).

    Proves the detector matches the known DI-5-deferred conditional shapes
    (`== ProviderId(...)`, `<deployment>.provider.value == "..."`,
    `str(<deployment>.provider) != "..."`, and `match`/`case` over a provider
    subject counted ONCE regardless of arm count) while excluding the
    look-alike shapes that must NOT ratchet: other provider axes
    (StorageProvider/EmailProvider/etc.), the `resolve_provider_identity`
    boundary function's own rewrap, and `in`/`not in` dict-dispatch lookups.
    """

    def _scan_source(self, tmp_path: Path, source: str) -> list:
        file_path = tmp_path / "sample.py"
        file_path.write_text(source, encoding="utf-8")
        return scan_file_for_provider_conditionals(file_path)

    def test_providerid_equality_compare_is_detected(self, tmp_path: Path) -> None:
        source = (
            "def f(provider):\n"
            "    if provider == ProviderId('azure'):\n"
            "        return True\n"
            "    return False\n"
        )
        hits = self._scan_source(tmp_path, source)
        assert len(hits) == 1
        assert hits[0].kind == "providerid_compare"

    def test_providerid_inequality_via_helper_call_is_detected(self, tmp_path: Path) -> None:
        source = (
            "def f(deployment):\n"
            "    if resolve_provider_identity(deployment) != ProviderId('aws'):\n"
            "        return None\n"
            "    return 1\n"
        )
        hits = self._scan_source(tmp_path, source)
        assert len(hits) == 1
        assert hits[0].kind == "providerid_compare"

    def test_deployment_provider_value_compare_is_detected(self, tmp_path: Path) -> None:
        source = (
            "class G:\n"
            "    def f(self):\n"
            "        if self._deployment.provider.value == 'azure':\n"
            "            return True\n"
            "        return False\n"
        )
        hits = self._scan_source(tmp_path, source)
        assert len(hits) == 1
        assert hits[0].kind == "deployment_provider_value_compare"

    def test_str_wrapped_deployment_provider_compare_is_detected(self, tmp_path: Path) -> None:
        source = (
            "class G:\n"
            "    def f(self):\n"
            "        if str(self._deployment.provider) != 'aws':\n"
            "            return []\n"
            "        return None\n"
        )
        hits = self._scan_source(tmp_path, source)
        assert len(hits) == 1
        assert hits[0].kind == "deployment_provider_value_compare"

    def test_match_case_over_provider_subject_counts_once(self, tmp_path: Path) -> None:
        """A 3-arm match/case is ONE site, not three -- the arms' own
        `p == ProviderId(...)` guards must not be double-counted on top of
        the match-subject hit."""
        source = (
            "def f(provider_id):\n"
            "    match provider_id:\n"
            "        case p if p == ProviderId('aws'):\n"
            "            return 'a'\n"
            "        case p if p == ProviderId('azure'):\n"
            "            return 'b'\n"
            "        case p if p == ProviderId('local'):\n"
            "            return 'c'\n"
            "        case _:\n"
            "            raise ValueError('unknown')\n"
        )
        hits = self._scan_source(tmp_path, source)
        assert len(hits) == 1, f"expected exactly 1 hit (the match subject), got {hits!r}"
        assert hits[0].kind == "match_case_provider_subject"

    def test_other_provider_axis_value_compare_is_excluded(self, tmp_path: Path) -> None:
        """StorageProvider/EmailProvider/etc. `.value` comparisons are a
        DIFFERENT axis from the deployment/infrastructure provider and must
        never ratchet here."""
        source = (
            "class G:\n"
            "    def f(self, storage_block, email_config, metrics):\n"
            "        a = storage_block.config.provider == StorageProvider.MINIO\n"
            "        b = str(email_config.provider.value) == 'sendgrid'\n"
            "        c = str(metrics.provider.value) == 'prometheus'\n"
            "        return a, b, c\n"
        )
        hits = self._scan_source(tmp_path, source)
        assert hits == [], f"other-axis provider comparisons must not ratchet, got {hits!r}"

    def test_boundary_function_rewrap_is_excluded(self, tmp_path: Path) -> None:
        """The `resolve_provider_identity` boundary function's own
        `ProviderId(x.value)` rewrap is not a comparison and must not count."""
        source = (
            "def resolve_provider_identity(deployment):\n"
            "    return ProviderId(deployment.provider.value)\n"
        )
        hits = self._scan_source(tmp_path, source)
        assert hits == [], f"the boundary rewrap itself must not ratchet, got {hits!r}"

    def test_dict_dispatch_membership_lookup_is_excluded(self, tmp_path: Path) -> None:
        """A frozenset/dict `in`/`not in` dispatch-table lookup is a
        different successor shape (not yet in this ratchet's scope) and
        must not be flagged as a providerid_compare."""
        source = (
            "_WHEEL_DEPLOYED_PROVIDERS = frozenset({ProviderId('aws'), ProviderId('azure')})\n"
            "\n"
            "def f(provider):\n"
            "    if provider not in _WHEEL_DEPLOYED_PROVIDERS:\n"
            "        return []\n"
            "    return None\n"
        )
        hits = self._scan_source(tmp_path, source)
        assert hits == [], f"dict-dispatch 'not in' lookups must not ratchet, got {hits!r}"

    def test_non_deployment_rooted_provider_attr_value_is_excluded(self, tmp_path: Path) -> None:
        """`cfg.provider` (not rooted at `deployment`/`self._deployment`) must
        not match the deployment-provider `.value` form even though it has
        the identical `.provider`/`.value` shape."""
        source = (
            "def f(cfg):\n"
            "    bucket = cfg.container if str(cfg.provider) == 'azure_blob' else cfg.bucket\n"
            "    return bucket\n"
        )
        hits = self._scan_source(tmp_path, source)
        assert hits == [], f"non-deployment-rooted .provider comparisons must not ratchet, got {hits!r}"


@pytest.mark.unit
class TestProviderConditionalRatchet:
    """``check_provider_conditional_ratchet`` fires on any per-file INCREASE
    over the frozen baseline and never on a decrease or unchanged count."""

    def test_ratchet_is_clean_when_current_matches_baseline(self) -> None:
        baseline = {"datrix-codegen-python/src/datrix_codegen_python/foo.py": 3}
        current = {"datrix-codegen-python/src/datrix_codegen_python/foo.py": 3}
        assert check_provider_conditional_ratchet(current, baseline) == []

    def test_ratchet_fires_on_increase(self) -> None:
        baseline = {"datrix-codegen-python/src/datrix_codegen_python/foo.py": 3}
        current = {"datrix-codegen-python/src/datrix_codegen_python/foo.py": 4}
        messages = check_provider_conditional_ratchet(current, baseline)
        assert len(messages) == 1
        assert "foo.py" in messages[0]
        assert "increased from baseline 3 to 4" in messages[0]

    def test_ratchet_allows_decrease(self) -> None:
        """Decreases (the DI-5 direction) must never be flagged."""
        baseline = {"datrix-codegen-python/src/datrix_codegen_python/foo.py": 3}
        current = {"datrix-codegen-python/src/datrix_codegen_python/foo.py": 1}
        assert check_provider_conditional_ratchet(current, baseline) == []

    def test_ratchet_fires_on_new_file_with_no_baseline_entry(self) -> None:
        """A file absent from the baseline is treated as baseline 0 -- any
        hit in a brand-new file is itself an increase."""
        baseline: dict[str, int] = {}
        current = {"datrix-codegen-typescript/src/datrix_codegen_typescript/new_file.py": 1}
        messages = check_provider_conditional_ratchet(current, baseline)
        assert len(messages) == 1
        assert "increased from baseline 0 to 1" in messages[0]
