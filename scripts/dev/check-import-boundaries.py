#!/usr/bin/env python3
"""Cross-package import boundary scanner for Datrix monorepo.

Enforces architectural dependency rules by scanning all Python source files
in each package's src/, tests/, fixtures/, and helpers/ directories (when they
exist) and checking imports against forbidden prefix rules. Uses AST parsing -
no package installation required.

Also implements the I1 target-literal ratchet:
opt-in via --check-target-literals, it AST-scans the three shared-layer
src/ trees (datrix_common, datrix_codegen_common, datrix_cli) for known
closed-world target-identity identifiers and fails if any file's count
increases past its frozen baseline (scripts/config/target-literal-baseline.toml).
--update-baseline recomputes and overwrites that baseline.

Also implements the I6 successor ratchet (invariant I6, DI-4/DI-5):
opt-in via --check-provider-conditionals, it AST-scans the LANGUAGE
package src/ trees (LANGUAGE_PACKAGES, the declared taxonomy) for
platform-identity CONDITIONALS -- the successor forms of the removed
DeploymentProvider branches (`== ProviderId(...)`, `.value == "..."`,
`match`/`case` over a provider) -- and fails if any file's count increases
past its frozen baseline (scripts/config/provider-conditional-baseline.toml).
These sites are DI-5-deferred; the ratchet freezes them so they cannot grow,
and drives to zero as each cluster is migrated onto a decision engine.
--update-baseline (combined with --check-provider-conditionals) recomputes
and overwrites that baseline.

Also implements the function-level-import ratchet (D4/I6):
opt-in via --check-function-level-imports, it AST-scans ONLY the
datrix-common src/ tree for function-level imports (an Import/ImportFrom AST
node that is not a direct top-level statement of its module -- nested in a
function/method body, an `if TYPE_CHECKING:` block, or a `try`/`except`) and
fails if any file's count increases past its frozen baseline
(scripts/config/function-level-import-baseline.toml). A one-shot sweep of
every site is deliberately rejected; the ratchet freezes the count so it
cannot grow while later work promotes deferred imports back to module top as
the changes that touch each file allow.
--update-baseline (combined with --check-function-level-imports) recomputes
and overwrites that baseline.

Self-test (--self-test): proves the rule model (BOUNDARY_RULES, the allowed-
subtree carve-outs), the AST scanners (provider-conditional,
function-level-import), and both ratchet comparators are non-vacuous --
including a real mutation-based CLI proof (plants a regression in an
isolated fixture monorepo, proves the CLI detects it, proves it clears on
revert). The self-test runs automatically as step 1 of EVERY normal
invocation of this script (not only when --self-test is passed): a run whose
self-test fails aborts before any real finding is reported, since a checker
that cannot prove its own logic cannot be trusted. Pass --self-test alone to
run only the self-test and skip the real scan. --skip-auto-self-test is an
internal flag used solely by the self-test's own nested CLI invocation (to
avoid it recursively re-running the self-test on itself) and is not intended
for direct use.

Exit codes:
    0: Clean (no violations) or --warn mode
    1: Violations found in fail mode (import-boundary and/or I1/I6/function-
       level-import ratchets), or a self-test failure
    2: Usage error, configuration error, or (with --check-target-literals,
       --check-provider-conditionals, or --check-function-level-imports) a
       missing baseline file
"""

import argparse
import ast
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class BoundaryRule:
    """Per-package boundary rule: forbidden prefixes plus subtree carve-outs.

    An import that matches a forbidden prefix is still permitted when it
    starts with one of ``allowed_subtrees`` — used to admit the narrow,
    language-agnostic platform -> codegen-common edges while keeping the
    language-shaped subtrees walled off.
    """

    forbidden_prefixes: tuple[str, ...]
    allowed_subtrees: frozenset[str] = frozenset()


# The closed set of language-agnostic datrix_codegen_common subtrees that
# platform generators (docker, aws, azure) are permitted to import.
# Adding a seventh subtree requires a doc + rule edit and review.
#
# Covers all 13 distinct datrix_codegen_common modules that platforms import today:
#   gendsl.*       — GenDSL compiler/executor/registry/scope
#   dashboards.*   — shared Grafana dashboard builder (builder, models)
#   algorithms.serverless            — serverless block plan algorithm
#   context_models.serverless        — serverless plan/render context models
#   context_models.replayable_ingestion — frozen, language-agnostic ingestion plan
#   enums           — shared enums (e.g. DatabaseEngine)
#
# Platforms remain FORBIDDEN from: transpiler.*, language-shaped context_models.*
# (entity/schema/service/endpoint/cache/pubsub/cqrs/jobs/project), and
# language-shaped algorithms.* (same suffixes).
PLATFORM_CODEGEN_COMMON_ALLOWED_SUBTREES: frozenset[str] = frozenset(
    [
        "datrix_codegen_common.gendsl",
        "datrix_codegen_common.dashboards",
        "datrix_codegen_common.algorithms.serverless",
        "datrix_codegen_common.context_models.serverless",
        "datrix_codegen_common.context_models.replayable_ingestion",
        "datrix_codegen_common.enums",
        "datrix_codegen_common.platform",
        # D8 shared decision engines + D9/D10 conformance layers:
        # target-neutral infrastructure decisions every platform legitimately
        # consumes -- NOT language-shaped. pooling: the unified pooled-resource
        # context builder (DI-5); secrets: the shared secret-manifest /
        # handle-derivation decision layer (rendering stays per-target); seed:
        # config-seed planning; parity: the D6/D9 BlockRealization /
        # DomainDeclaration types platforms declare their capabilities with;
        # orchestration.resolved_runtime_plan: the target-neutral resolved
        # runtime plan; testkit: the D10 conformance kit each target package
        # consumes as a dev-dependency in its own test tree.
        "datrix_codegen_common.pooling",
        "datrix_codegen_common.secrets",
        "datrix_codegen_common.seed",
        "datrix_codegen_common.parity",
        "datrix_codegen_common.orchestration.resolved_runtime_plan",
        "datrix_codegen_common.testkit",
        # The shared container-image supply primitives (union requirements +
        # content-hash base-image tag).
        # THREE platform plugins need this ONE algorithm -- docker (emits the
        # base image, bakes the tag into every per-service Dockerfile FROM
        # line), aws (its deploy script builds/pushes exactly that tag), and
        # azure (its ACR site-config image reference). A platform plugin may
        # never import a sibling platform plugin to get it (that would make
        # AWS uninstallable without Docker -- see the platform->platform
        # prohibition in BOUNDARY_RULES below), so the algorithm lives in the
        # shared codegen layer and every platform imports it from here.
        # Redundant with the broader ``datrix_codegen_common.platform`` entry
        # above; listed explicitly so this edge is reviewable on its own.
        "datrix_codegen_common.platform.container_image_supply",
    ]
)

# The closed set of language-agnostic datrix_codegen_common subtrees that the
# SQL generator is permitted to import.  SQL is a schema/DDL generator — it is
# not a language generator, but it is not a platform generator either, so it
# carries its own narrower carve-out rather than the platform set.
#
# Covers the datrix_codegen_common modules that SQL imports today:
#   gendsl.*                          — GenDSL compiler/executor (shared entry point)
#   context_models.migration          — SQL migration state model (language-agnostic)
#   orchestration.migration_adapter   — migration adapter shared by SQL + TS (language-agnostic)
#
# SQL remains FORBIDDEN from: transpiler.*, language-shaped context_models.*
# (entity/schema/service/endpoint/cache/pubsub/cqrs/jobs/project), algorithms.*,
# dashboards.*, and the platform-specific subtrees.
SQL_CODEGEN_COMMON_ALLOWED_SUBTREES: frozenset[str] = frozenset(
    [
        "datrix_codegen_common.gendsl",
        "datrix_codegen_common.context_models.migration",
        "datrix_codegen_common.orchestration.migration_adapter",
        # D9 conformance types SQL declares its domain support with (kit-CI):
        # the same target-neutral DomainDeclaration / SHARED_CONTEXT_TYPES
        # layer platforms consume -- not language-shaped.
        "datrix_codegen_common.parity",
        # D10 testkit is a dev-dependency of every target package (its gates /
        # capability harness are target-neutral); SQL's kit-CI test consumes the
        # shared domain-self-consistency gate the same way platform kit-CI tests do.
        "datrix_codegen_common.testkit",
    ]
)

# ---------------------------------------------------------------------------
# Generator taxonomy -- the ONE place the package roles are declared.
#
# Datrix is a multi-language, multi-platform generator: these sets grow. A
# package's ROLE cannot be inferred from its name (datrix_codegen_sql and
# datrix_codegen_component are neither language nor platform generators), so the
# taxonomy is declared rather than discovered -- but it is declared ONCE, and
# every boundary rule below is DERIVED from it. Adding a language is one entry
# here, not an edit to eight scattered forbidden-prefix tuples.
#
# Omitting a language package here is NOT a silent no-op. A package absent from
# LANGUAGE_PACKAGES gets no BoundaryRule at all, so the scanner would happily let
# it import a sibling language generator or datrix_cli -- "a silent checker
# mistaken for an approving one", the same defect the platform rules once had
# (see the sibling-platform note below).
LANGUAGE_PACKAGES: tuple[str, ...] = (
    "datrix_codegen_python",
    "datrix_codegen_typescript",
    "datrix_codegen_dotnet",
    "datrix_codegen_java",
)

PLATFORM_PACKAGES: tuple[str, ...] = (
    "datrix_codegen_docker",
    "datrix_codegen_aws",
    "datrix_codegen_azure",
)


def _siblings(package: str, group: tuple[str, ...]) -> tuple[str, ...]:
    """Every member of ``group`` except ``package`` itself."""
    return tuple(name for name in group if name != package)


# Boundary rules: source package -> BoundaryRule
# forbidden_prefixes: imports whose prefix matches are forbidden
# allowed_subtrees: specific sub-prefixes that override the broader forbidden prefix
BOUNDARY_RULES: dict[str, BoundaryRule] = {
    "datrix_common": BoundaryRule(
        forbidden_prefixes=(
            "datrix_language",
            "datrix_cli",
            "datrix_codegen_",  # Wildcard: any package starting with datrix_codegen_
            "datrix_extensions",
        ),
    ),
    "datrix_language": BoundaryRule(
        forbidden_prefixes=(
            "datrix_cli",
            "datrix_codegen_",  # Wildcard
        ),
    ),
    "datrix_codegen_common": BoundaryRule(
        forbidden_prefixes=(*LANGUAGE_PACKAGES, *PLATFORM_PACKAGES, "datrix_cli"),
    ),
    # Language generators: each forbids every SIBLING language package. They share
    # code through datrix-codegen-common, never through direct imports -- importing a
    # sibling re-introduces the O(N^2) coupling the shared layer exists to prevent
    # (see "Cross-language parity is verified by per-language conformance, never by
    # comparison" in datrix-common/docs/architecture/import-boundaries.md).
    **{
        language: BoundaryRule(forbidden_prefixes=_siblings(language, LANGUAGE_PACKAGES))
        for language in LANGUAGE_PACKAGES
    },
    # SQL generator: forbidden from sibling language packages and from the bulk of
    # datrix_codegen_common (it is not a language generator, so the transpiler and
    # language-shaped subtrees are off-limits).  SQL_CODEGEN_COMMON_ALLOWED_SUBTREES
    # carves out the narrow language-agnostic subtrees SQL legitimately uses.
    "datrix_codegen_sql": BoundaryRule(
        forbidden_prefixes=(
            *LANGUAGE_PACKAGES,
            "datrix_codegen_common",
            "datrix_cli",
        ),
        allowed_subtrees=SQL_CODEGEN_COMMON_ALLOWED_SUBTREES,
    ),
    # Component generator: forbidden from sibling language packages and datrix_cli.
    # Component is a language-agnostic scaffolding generator — it is not a language
    # generator, but unlike SQL it legitimately imports datrix_codegen_common freely
    # (gendsl, algorithms.serverless, context_models.serverless, etc.), so
    # datrix_codegen_common is NOT on its forbidden list.
    "datrix_codegen_component": BoundaryRule(
        forbidden_prefixes=(*LANGUAGE_PACKAGES, "datrix_cli"),
    ),
    # Platform generators keep datrix_codegen_common on forbidden_prefixes but carry
    # PLATFORM_CODEGEN_COMMON_ALLOWED_SUBTREES to admit the language-agnostic
    # subtrees they legitimately consume. The transpiler and language-shaped
    # context_models/algorithms subtrees remain forbidden.
    #
    # SIBLING PLATFORM PLUGINS ARE FORBIDDEN TOO. Each platform
    # forbids every OTHER platform. This edge was once missing from every
    # platform's rule -- not because it was permitted, but because nobody had
    # written it, so a silent checker was mistaken for an approving one. A platform
    # plugin importing a sibling platform plugin (e.g. aws importing docker to
    # reuse the base-image tag algorithm) means the importing platform can no
    # longer be installed without the imported one, and would grow into a
    # three-way coupling the moment a second platform needed the same code.
    # The correct home for anything two platforms share is the shared codegen
    # layer (PLATFORM_CODEGEN_COMMON_ALLOWED_SUBTREES above): shared layers
    # ask, target plugins answer (design principle 16; CLAUDE.md's
    # generality-preserving design rule).
    **{
        platform: BoundaryRule(
            forbidden_prefixes=(
                "datrix_codegen_common",
                *LANGUAGE_PACKAGES,
                *_siblings(platform, PLATFORM_PACKAGES),
                "datrix_cli",
            ),
            allowed_subtrees=PLATFORM_CODEGEN_COMMON_ALLOWED_SUBTREES,
        )
        for platform in PLATFORM_PACKAGES
    },
    "datrix_extensions": BoundaryRule(
        forbidden_prefixes=(
            "datrix_cli",
            *LANGUAGE_PACKAGES,
            "datrix_codegen_common",
            *PLATFORM_PACKAGES,
            "datrix_language",
        ),
    ),
}


# ---------------------------------------------------------------------------
# I1 Target-Literal Ratchet (Decision D1, Invariant I1)
#
# The three shared-layer package names the I1 ratchet polices (D1: "shared
# layers ask questions, target plugins answer them" — datrix_language and the
# leaf datrix_codegen_{python,typescript,aws,azure,docker,sql,component}
# packages are OWNERS of target identity and are exempt from this scan).
TARGET_LITERAL_SHARED_PACKAGES: tuple[str, ...] = (
    "datrix_common",
    "datrix_codegen_common",
    "datrix_cli",
)

# Central table / dict / class names known TODAY to encode closed-world target
# policy in a shared layer. The list is frozen: each entry is scheduled for
# deletion (the inline comment records where it lived and when it went), and
# the ratchet's job is to make sure nothing NEW joins this list while the
# remaining entries are removed.
TARGET_LITERAL_CENTRAL_NAMES: frozenset[str] = frozenset(
    {
        "Language",  # enums.py:13-18 (deleted 07-03)
        "ProjectLanguage",  # enums.py:26-30 (deleted 07-03)
        "GENERATORS_BY_LANGUAGE",  # enums.py:33 (deleted 06-04)
        "DeploymentProvider",  # enums.py:82-97 (deleted 07-03)
        "PROVIDER_GENERATORS",  # enums.py:289 (deleted 07-03)
        "_TARGET_KIND_MAP",  # gendsl/parser.py:36, validator.py:30 (deleted 06-02)
        "_KNOWN_DEFINITION_MODULES",  # gendsl/compiler.py:153-161 (deleted 06-02)
        "EMAIL_REALIZATION",  # provisioning.py:60-81 (deleted 07-04)
        "SMS_REALIZATION",  # provisioning.py:92-109 (deleted 07-04)
        "PUSH_REALIZATION",  # provisioning.py:~129 (deleted 07-04)
        "_DEFAULT_BACKEND_BY_PROVIDER",  # secret_backend.py:175-178 (deleted 07-04)
        "VALID_PROVIDERS_BY_RUNTIME",  # deployment_validation.py:29-42 (deleted 07-04)
        "_SERVERLESS_PLATFORM_BY_PROVIDER",  # hosting_validation.py:22-26 (deleted 07-04)
        "_PLATFORM_INFRA_CLASSES",  # auth_resolver.py:54-71 (deleted 07-05)
    }
)

# Enum-qualified member accesses (Attribute nodes like `DeploymentProvider.AWS`)
# recognized as target-literal references. Keyed by the enum class name so a
# bare identifier collision (e.g. a local variable named `AWS`) never matches --
# only `<ClassName>.<MEMBER>` attribute access counts.
TARGET_LITERAL_ENUM_MEMBERS: dict[str, frozenset[str]] = {
    "Language": frozenset({"PYTHON", "TYPESCRIPT", "SQL"}),
    "ProjectLanguage": frozenset({"PYTHON", "TYPESCRIPT"}),
    "DeploymentProvider": frozenset({"LOCAL", "EXISTING", "AWS", "AZURE"}),
}


# ---------------------------------------------------------------------------
# I6 Successor Ratchet (invariant I6, DI-4/DI-5)
#
# The literal `DeploymentProvider.` grep is already empty (DI-3 deleted the
# enum). I6's successor form is a closed-world platform-identity CONDITIONAL
# built on the open `ProviderId` value object (datrix_common.plugin.identity)
# instead of the retired enum. These conditionals are legitimate TODAY (DI-4
# scope was reduced to the 3 Python + 1 TypeScript sites; every other site is
# deliberately deferred to DI-5) but must not be allowed to grow while they
# wait for a decision-engine replacement. Only the LANGUAGE (leaf/owner)
# packages are policed here -- unlike I1, this is NOT a shared-layer scan;
# leaf packages are the legitimate
# owners of target identity (D1), so the defect is the CONDITIONAL shape
# itself (branch-per-provider, DI-5's job to collapse), not package location.
#
# Derived from LANGUAGE_PACKAGES (the single taxonomy declaration above) so a new
# language generator is policed by this ratchet from its first commit, rather than
# silently accumulating provider conditionals until someone remembers this tuple.
# A package with no src/ tree yet contributes no files and no baseline entries.
PROVIDER_CONDITIONAL_LANGUAGE_PACKAGES: tuple[str, ...] = LANGUAGE_PACKAGES


# ---------------------------------------------------------------------------
# Function-Level-Import Ratchet (D4/I6)
#
# The rule: deferred function-level imports move back to module top under a
# ratchet -- a 668 baseline, monotonically decreasing (superseded by an
# orchestrator-frozen 657 ceiling for the pre-decomposition tree -- see the
# frozen baseline file's own header). A
# function-level import is any `Import`/`ImportFrom` AST node that is not a
# direct top-level statement of its module -- nested inside a function body,
# a method body, an `if TYPE_CHECKING:` block, or a `try`/`except`. Scoped to
# `datrix-common` ONLY (unlike I1/I6 above): this is that package's own
# intra-package layering effort (D4/I6 concerns `datrix-common`'s model/
# semantic/config/generation layering specifically), not a monorepo-wide
# metric. Do not extend this tuple to other packages.
FUNCTION_LEVEL_IMPORT_PACKAGES: tuple[str, ...] = ("datrix_common",)

# Root name(s) recognized as "the deployment/infrastructure provider" for the
# `.value`/`str(...)` detection forms below. Restricting to these roots (a
# bare `deployment` variable, or `self._deployment` / `self.deployment`) is
# what separates a genuine deployment-provider comparison from the many OTHER
# provider axes in the same files (StorageProvider, EmailProvider, SmsProvider,
# SearchProvider, PaymentProvider, metrics/tracing provider) which all reach
# their own `.provider` off a *different* config object (e.g. `cfg.provider`,
# `email_config.provider`, `metrics_config.provider`) and must NOT ratchet here.
_DEPLOYMENT_ROOT_ATTRS: frozenset[str] = frozenset({"deployment", "_deployment"})


def _is_providerid_call(node: ast.AST) -> bool:
    """True if *node* is a call to the ``ProviderId`` constructor (bare or
    module-qualified), e.g. ``ProviderId("azure")`` or ``identity.ProviderId(x)``.
    """
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "ProviderId"
    if isinstance(func, ast.Attribute):
        return func.attr == "ProviderId"
    return False


def _is_deployment_root(node: ast.AST) -> bool:
    """True if *node* is the deployment-config object itself: a bare
    ``deployment`` name, or an attribute access ending in ``deployment``/
    ``_deployment`` (e.g. ``self._deployment``, ``self.deployment``).
    """
    if isinstance(node, ast.Name):
        return node.id in _DEPLOYMENT_ROOT_ATTRS
    if isinstance(node, ast.Attribute):
        return node.attr in _DEPLOYMENT_ROOT_ATTRS
    return False


def _is_deployment_provider_attr(node: ast.AST) -> bool:
    """True if *node* is ``<deployment-root>.provider`` (the raw provider
    field read off the deployment config, before any ``.value``/``str()``).
    """
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "provider"
        and _is_deployment_root(node.value)
    )


def _is_deployment_provider_value_expr(node: ast.AST) -> bool:
    """True if *node* stringifies the DEPLOYMENT provider specifically --
    ``<deployment-root>.provider.value`` or ``str(<deployment-root>.provider)``
    (including the redundant ``str(<deployment-root>.provider.value)`` form).
    Deliberately narrower than "any `.provider.value`" so the many other
    provider axes (storage/email/sms/search/payment/metrics/tracing) --
    which share the `.provider`/`.value` shape but hang off a *different*
    config object -- never match (see ``_DEPLOYMENT_ROOT_ATTRS``).
    """
    if isinstance(node, ast.Attribute) and node.attr == "value":
        return _is_deployment_provider_attr(node.value)
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "str"
        and len(node.args) == 1
    ):
        arg = node.args[0]
        return _is_deployment_provider_attr(arg) or _is_deployment_provider_value_expr(
            arg
        )
    return False


def _provider_conditional_compare_kind(
    node: ast.Compare,
) -> Literal["providerid_compare", "deployment_provider_value_compare"] | None:
    """Classify a single ``ast.Compare`` node as a provider-conditional hit,
    or ``None`` if it isn't one.

    Only simple binary comparisons (exactly one operator) are considered --
    chained comparisons (``a == b == c``) are not a shape this ratchet's
    known sites use. Two forms match, checked against BOTH sides of the
    comparison:

      - ``providerid_compare``: either side is a call to ``ProviderId(...)``
        (covers ``== ProviderId(...)``, ``ProviderId(...) ==``, ``!=
        ProviderId(...)``, and a ``match``/``case`` guard's ``p ==
        ProviderId("aws")`` -- ``ProviderId`` names exactly ONE axis
        (deployment/infrastructure provider identity), so no other-axis
        exclusion is needed for this form).
      - ``deployment_provider_value_compare``: either side stringifies the
        deployment provider specifically (``_is_deployment_provider_value_expr``),
        covering ``deployment.provider.value == "..."`` and
        ``str(self._deployment.provider) != "aws"``.

    Only Eq/NotEq operators count (``==``/``!=``) -- an ``in``/``not in``
    membership test (e.g. a dict-dispatch-table lookup) is a different
    successor shape not yet in this ratchet's scope.
    """
    if len(node.ops) != 1 or not isinstance(node.ops[0], (ast.Eq, ast.NotEq)):
        return None

    sides = [node.left, node.comparators[0]]

    if any(_is_providerid_call(side) for side in sides):
        return "providerid_compare"
    if any(_is_deployment_provider_value_expr(side) for side in sides):
        return "deployment_provider_value_compare"
    return None


def _match_subject_is_provider(subject: ast.AST) -> bool:
    """True if a ``match`` statement's subject expression names a provider
    identity (e.g. ``match provider_id:``) -- a bare ``Name`` or the ``attr``
    of an ``Attribute`` chain whose final segment contains "provider"
    (case-insensitive).
    """
    if isinstance(subject, ast.Name):
        return "provider" in subject.id.lower()
    if isinstance(subject, ast.Attribute):
        return "provider" in subject.attr.lower()
    return False


@dataclass(frozen=True)
class ProviderConditionalHit:
    """One occurrence of a platform-identity conditional in a language-package file."""

    file_path: Path
    line_number: int
    kind: Literal[
        "providerid_compare",
        "deployment_provider_value_compare",
        "match_case_provider_subject",
    ]


@dataclass(frozen=True)
class PackageInfo:
    """Package metadata for scanning."""

    name: str  # e.g., datrix_common
    root: Path  # e.g., d:/datrix/datrix-common
    src_dir: Path  # e.g., d:/datrix/datrix-common/src/datrix_common


@dataclass(frozen=True)
class Violation:
    """Represents a single import boundary violation."""

    file_path: Path
    line_number: int
    imported_module: str
    source_package: str
    forbidden_prefix: str


@dataclass(frozen=True)
class AllowlistEntry:
    """Represents a single allowlist entry."""

    file_pattern: str
    import_prefix: str
    issue_url: str


@dataclass(frozen=True)
class TargetLiteralHit:
    """One occurrence of a target-literal identifier in a shared-layer file."""

    file_path: Path
    line_number: int
    identifier: str
    kind: Literal["central_table_name", "enum_member_qualified"]


@dataclass(frozen=True)
class TargetLiteralBaselineEntry:
    """One frozen per-file count in the I1 ratchet baseline."""

    file: str  # path relative to monorepo root, forward slashes
    count: int


@dataclass(frozen=True)
class FunctionLevelImportHit:
    """One function-level (non-module-top) import statement in a
    ``datrix-common`` file (invariant I6 successor)."""

    file_path: Path
    line_number: int


def is_forbidden_import(
    source_package: str,
    imported_module: str,
    forbidden_prefix: str,
    allowed_subtrees: frozenset[str] = frozenset(),
) -> bool:
    """Check if an import violates a forbidden prefix rule.

    An import that matches a forbidden prefix is still permitted when it
    starts with one of the ``allowed_subtrees`` entries — used to admit
    the narrow, language-agnostic platform -> codegen-common edges.

    Subtree matching uses an exact-or-child rule:
        subtree ``s`` matches ``m`` when ``m == s`` or ``m.startswith(s + ".")``.
    This ensures ``enums`` matches ``enums`` and ``enums.foo`` but never
    ``enums_other``.

    Args:
        source_package: The package doing the importing (e.g., datrix_common)
        imported_module: The full dotted import name (e.g., datrix_language.parser)
        forbidden_prefix: The forbidden prefix (may end with _ for wildcard)
        allowed_subtrees: Fully-qualified subtree roots that override the
            forbidden prefix for this source package.

    Returns:
        True if the import is forbidden, False otherwise
    """
    # Self-imports are always allowed
    if (
        imported_module.startswith(source_package + ".")
        or imported_module == source_package
    ):
        return False

    # Handle wildcard prefixes (e.g., datrix_codegen_)
    if forbidden_prefix.endswith("_"):
        # Wildcard match: imported module starts with prefix
        matched = imported_module.startswith(forbidden_prefix)
    else:
        # Exact prefix match (or module.submodule)
        matched = (
            imported_module.startswith(forbidden_prefix + ".")
            or imported_module == forbidden_prefix
        )

    if not matched:
        return False

    # The import matches a forbidden prefix; check whether an allowed subtree
    # carves it out.  A subtree ``s`` covers ``m`` when ``m == s`` or
    # ``m.startswith(s + ".")``.
    for subtree in allowed_subtrees:
        if imported_module == subtree or imported_module.startswith(subtree + "."):
            return False

    return True


def extract_imports_from_file(file_path: Path) -> list[tuple[int, str]]:
    """Extract all imports from a Python file using AST.

    Args:
        file_path: Path to Python source file

    Returns:
        List of (line_number, imported_module_name) tuples

    Raises:
        SyntaxError: If the file cannot be parsed
        OSError: If the file cannot be read
    """
    # utf-8-sig transparently strips a leading UTF-8 BOM (U+FEFF) so a
    # BOM-prefixed file can never fail ast.parse and be silently skipped
    # (scanner integrity).
    source_code = file_path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source_code, filename=str(file_path))

    imports: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            # import foo, bar.baz
            for alias in node.names:
                imports.append((node.lineno, alias.name))

        elif isinstance(node, ast.ImportFrom):
            # from foo import bar
            # Skip relative imports (node.level > 0)
            if node.level == 0 and node.module is not None:
                imports.append((node.lineno, node.module))

    return imports


def discover_packages(base_dir: Path) -> dict[str, PackageInfo]:
    """Discover all datrix-* packages in the monorepo.

    Args:
        base_dir: Monorepo root directory

    Returns:
        Dictionary mapping package names to PackageInfo objects
    """
    packages: dict[str, PackageInfo] = {}

    for candidate in base_dir.iterdir():
        if not candidate.is_dir():
            continue

        # Only process datrix-* directories
        if not candidate.name.startswith("datrix-"):
            continue

        src_dir = candidate / "src"
        if not src_dir.exists():
            continue

        # Find the package name by looking for the actual package directory under src/
        # e.g., datrix-common/src/datrix_common/ -> package name is datrix_common
        package_dirs = [
            d for d in src_dir.iterdir() if d.is_dir() and d.name.startswith("datrix")
        ]

        if not package_dirs:
            continue

        # Use the first datrix* directory name as the package name
        package_name = package_dirs[0].name
        packages[package_name] = PackageInfo(
            name=package_name,
            root=candidate,
            src_dir=src_dir / package_name,
        )

    return packages


def scan_package_for_violations(
    package_info: PackageInfo,
    monorepo_root: Path,
    verbose: bool,
) -> list[Violation]:
    """Scan a single package for import boundary violations.

    Args:
        package_info: Package metadata
        monorepo_root: Monorepo root for relative path calculation
        verbose: Print each file being scanned

    Returns:
        List of violations found
    """
    violations: list[Violation] = []

    # Get the boundary rule for this package; no rule means no restrictions
    rule = BOUNDARY_RULES.get(package_info.name)
    if rule is None:
        return violations

    # Directories to scan: src/, tests/, fixtures/, helpers/
    scan_dirs = [package_info.src_dir]

    # Add optional directories if they exist
    for dir_name in ["tests", "fixtures", "helpers"]:
        optional_dir = package_info.root / dir_name
        if optional_dir.exists() and optional_dir.is_dir():
            scan_dirs.append(optional_dir)

    # Walk all .py files under all scan directories
    for scan_dir in scan_dirs:
        for py_file in scan_dir.rglob("*.py"):
            if verbose:
                rel_path = py_file.relative_to(monorepo_root)
                print(f"Scanning: {rel_path}", file=sys.stderr)

            try:
                imports = extract_imports_from_file(py_file)
            except SyntaxError as e:
                rel_path = py_file.relative_to(monorepo_root)
                print(
                    f"ERROR: Failed to parse {rel_path}:{e.lineno} - {e.msg}. "
                    f"A policed file that cannot be parsed would escape this scan "
                    f"(a silent blind spot); fix its syntax or encoding.",
                    file=sys.stderr,
                )
                sys.exit(2)
            except OSError as e:
                rel_path = py_file.relative_to(monorepo_root)
                print(
                    f"ERROR: Failed to read {rel_path} - {e}. A policed file that "
                    f"cannot be read would escape this scan; resolve the read error.",
                    file=sys.stderr,
                )
                sys.exit(2)

            # Check each import against forbidden prefixes, respecting allowed subtrees
            for line_num, imported_module in imports:
                for forbidden_prefix in rule.forbidden_prefixes:
                    if is_forbidden_import(
                        package_info.name,
                        imported_module,
                        forbidden_prefix,
                        rule.allowed_subtrees,
                    ):
                        violations.append(
                            Violation(
                                file_path=py_file,
                                line_number=line_num,
                                imported_module=imported_module,
                                source_package=package_info.name,
                                forbidden_prefix=forbidden_prefix,
                            )
                        )
                        break  # Only report first matching forbidden prefix

    return violations


def scan_file_for_target_literals(file_path: Path) -> list[TargetLiteralHit]:
    """AST-walk *file_path* for target-literal identifiers.

    Two match kinds:
      - ``central_table_name``: any ``ast.Name``/``ast.ClassDef``/``ast.FunctionDef``
        (or ``ast.AsyncFunctionDef``) whose identifier is exactly one of
        ``TARGET_LITERAL_CENTRAL_NAMES`` (definition sites AND reference sites
        both count -- a table is a defect whether it's being defined or
        consumed), plus any ``ast.Attribute`` whose ``attr`` itself is one of
        ``TARGET_LITERAL_CENTRAL_NAMES`` (e.g. a module-qualified
        ``enums.GENERATORS_BY_LANGUAGE`` reference).
      - ``enum_member_qualified``: any ``ast.Attribute`` node whose ``value`` is
        an ``ast.Name`` with ``id`` in ``TARGET_LITERAL_ENUM_MEMBERS`` and whose
        ``attr`` is in the corresponding member frozenset (e.g. `Language.PYTHON`,
        `DeploymentProvider.AWS`) -- NOT a bare `AWS` identifier alone.

    Args:
        file_path: Path to Python source file.

    Returns:
        List of hits found in the file, in AST-walk order.

    Raises:
        SyntaxError: propagated from ast.parse (caller decides how to report).
        OSError: propagated if the file cannot be read.
    """
    # utf-8-sig transparently strips a leading UTF-8 BOM (U+FEFF) so a
    # BOM-prefixed file can never fail ast.parse and be silently skipped
    # (scanner integrity).
    source_code = file_path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source_code, filename=str(file_path))

    hits: list[TargetLiteralHit] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in TARGET_LITERAL_CENTRAL_NAMES:
            hits.append(
                TargetLiteralHit(
                    file_path=file_path,
                    line_number=node.lineno,
                    identifier=node.id,
                    kind="central_table_name",
                )
            )
        elif (
            isinstance(node, ast.ClassDef) and node.name in TARGET_LITERAL_CENTRAL_NAMES
        ):
            hits.append(
                TargetLiteralHit(
                    file_path=file_path,
                    line_number=node.lineno,
                    identifier=node.name,
                    kind="central_table_name",
                )
            )
        elif (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in TARGET_LITERAL_CENTRAL_NAMES
        ):
            hits.append(
                TargetLiteralHit(
                    file_path=file_path,
                    line_number=node.lineno,
                    identifier=node.name,
                    kind="central_table_name",
                )
            )
        elif isinstance(node, ast.Attribute):
            if node.attr in TARGET_LITERAL_CENTRAL_NAMES:
                hits.append(
                    TargetLiteralHit(
                        file_path=file_path,
                        line_number=node.lineno,
                        identifier=node.attr,
                        kind="central_table_name",
                    )
                )
            if (
                isinstance(node.value, ast.Name)
                and node.value.id in TARGET_LITERAL_ENUM_MEMBERS
                and node.attr in TARGET_LITERAL_ENUM_MEMBERS[node.value.id]
            ):
                hits.append(
                    TargetLiteralHit(
                        file_path=file_path,
                        line_number=node.lineno,
                        identifier=f"{node.value.id}.{node.attr}",
                        kind="enum_member_qualified",
                    )
                )

    return hits


def scan_target_literals(
    packages: dict[str, PackageInfo],
    monorepo_root: Path,
) -> dict[Path, list[TargetLiteralHit]]:
    """Scan every ``.py`` file under each of ``TARGET_LITERAL_SHARED_PACKAGES``'
    ``src/`` tree (via *packages*, as already discovered by ``discover_packages``)
    for target-literal identifiers.

    Args:
        packages: Package name -> PackageInfo, as returned by discover_packages().
        monorepo_root: Monorepo root for relative path reporting.

    Returns:
        Mapping of file path -> hits in that file (files with zero hits omitted).
    """
    results: dict[Path, list[TargetLiteralHit]] = {}

    for package_name in TARGET_LITERAL_SHARED_PACKAGES:
        package_info = packages.get(package_name)
        if package_info is None:
            continue

        for py_file in package_info.src_dir.rglob("*.py"):
            try:
                hits = scan_file_for_target_literals(py_file)
            except SyntaxError as e:
                rel_path = py_file.relative_to(monorepo_root)
                print(
                    f"ERROR: Failed to parse {rel_path}:{e.lineno} - {e.msg}. "
                    f"A policed file that cannot be parsed would escape this scan "
                    f"(a silent blind spot); fix its syntax or encoding.",
                    file=sys.stderr,
                )
                sys.exit(2)
            except OSError as e:
                rel_path = py_file.relative_to(monorepo_root)
                print(
                    f"ERROR: Failed to read {rel_path} - {e}. A policed file that "
                    f"cannot be read would escape this scan; resolve the read error.",
                    file=sys.stderr,
                )
                sys.exit(2)

            if hits:
                results[py_file] = hits

    return results


def load_target_literal_baseline(baseline_path: Path) -> dict[str, int]:
    """Load ``{relative_file: frozen_count}`` from the baseline TOML.

    Args:
        baseline_path: Path to the target-literal baseline TOML file.

    Returns:
        An empty dict if the file does not exist yet (first-ever run,
        before this task's `--update-baseline` freezes it).
    """
    if not baseline_path.exists():
        return {}

    try:
        import tomllib  # Python 3.11+
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            print(
                "Warning: TOML library not available. Install tomli for baseline support.",
                file=sys.stderr,
            )
            return {}

    with baseline_path.open("rb") as f:
        data = tomllib.load(f)

    counts: dict[str, int] = {}
    for entry in data.get("baseline", []):
        if not isinstance(entry, dict):
            continue

        file_rel = entry.get("file", "")
        count = entry.get("count")

        if file_rel and isinstance(count, int):
            counts[file_rel] = count

    return counts


def write_target_literal_baseline(baseline_path: Path, counts: dict[str, int]) -> None:
    """Write ``counts`` to the baseline TOML as ``[[baseline]] file=... count=...``
    entries, sorted by file for deterministic diffs.

    Args:
        baseline_path: Path to the target-literal baseline TOML file to write.
        counts: Mapping of relative file path (forward slashes) -> hit count.
    """
    header = (
        "# I1 Target-Literal Ratchet Baseline\n"
        "#\n"
        "# Frozen per-file counts of target-literal identifiers (language/provider\n"
        "# names hardcoded in a shared layer -- Decision D1, Invariant I1).\n"
        "# Any INCREASE in a file's count fails datrix/scripts/dev/check-import-boundaries.py\n"
        "# --check-target-literals. Decreases are always allowed and should be captured\n"
        "# by re-running with --update-baseline once a later change deletes an identifier\n"
        "# (the terminal state is 0 for every entry here).\n"
        "#\n"
        "# Format:\n"
        "#   [[baseline]]\n"
        '#   file = "path/relative/to/monorepo-root, forward slashes"\n'
        "#   count = <int>\n"
    )

    lines = [header]
    for file_rel in sorted(counts.keys()):
        lines.append("\n[[baseline]]\n")
        lines.append(f'file = "{file_rel}"\n')
        lines.append(f"count = {counts[file_rel]}\n")

    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text("".join(lines), encoding="utf-8")


def check_target_literal_ratchet(
    current_counts: dict[str, int],
    baseline: dict[str, int],
) -> list[str]:
    """Compare *current_counts* against *baseline*; return one message per
    file whose count INCREASED (baseline missing == baseline 0). Never flags
    a decrease -- the ratchet only tightens.

    Args:
        current_counts: Relative file path -> current hit count.
        baseline: Relative file path -> frozen baseline count.

    Returns:
        List of human-readable ratchet-failure messages, one per regressed
        file, sorted by file path.
    """
    messages: list[str] = []

    for file_rel in sorted(current_counts.keys()):
        current = current_counts[file_rel]
        frozen = baseline.get(file_rel, 0)
        if current > frozen:
            messages.append(
                f"{file_rel}: target-literal count increased from baseline "
                f"{frozen} to {current}"
            )

    return messages


def _walk_for_provider_conditionals(
    node: ast.AST,
    file_path: Path,
    hits: list[ProviderConditionalHit],
) -> None:
    """Recursively walk *node* collecting ``ProviderConditionalHit``s.

    A custom walker (rather than ``ast.walk``) is required for exactly one
    reason: a ``match provider_id:`` statement is counted ONCE, as the
    ``match_case_provider_subject`` hit at the ``match`` line -- NOT once
    plus once again per ``case p if p == ProviderId(...):`` guard. Each
    ``case`` guard is itself an ``ast.Compare`` that would otherwise ALSO
    satisfy ``providerid_compare``, double-counting the same logical site.
    So when a qualifying ``ast.Match`` is found, its ``case`` guards are
    skipped while patterns and bodies are still walked normally (a guard
    is only ever the provider-identity check the match already counted;
    unrelated real conditionals inside a case body are not exempted).
    """
    if isinstance(node, ast.Match):
        if _match_subject_is_provider(node.subject):
            hits.append(
                ProviderConditionalHit(
                    file_path=file_path,
                    line_number=node.lineno,
                    kind="match_case_provider_subject",
                )
            )
        for case in node.cases:
            # Deliberately skip case.guard -- see docstring above.
            for stmt in case.body:
                _walk_for_provider_conditionals(stmt, file_path, hits)
        return

    if isinstance(node, ast.Compare):
        kind = _provider_conditional_compare_kind(node)
        if kind is not None:
            hits.append(
                ProviderConditionalHit(
                    file_path=file_path, line_number=node.lineno, kind=kind
                )
            )

    for child in ast.iter_child_nodes(node):
        _walk_for_provider_conditionals(child, file_path, hits)


def scan_file_for_provider_conditionals(
    file_path: Path,
) -> list[ProviderConditionalHit]:
    """AST-walk *file_path* for platform-identity conditionals (I6 successor
    ratchet, DI-4/DI-5).

    See ``_provider_conditional_compare_kind`` and ``_match_subject_is_provider``
    for the exact matched/excluded shapes.

    Args:
        file_path: Path to Python source file.

    Returns:
        List of hits found in the file, in AST-walk order.

    Raises:
        SyntaxError: propagated from ast.parse (caller decides how to report).
        OSError: propagated if the file cannot be read.
    """
    # utf-8-sig transparently strips a leading UTF-8 BOM (U+FEFF) so a
    # BOM-prefixed file can never fail ast.parse and be silently skipped
    # (scanner integrity).
    source_code = file_path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source_code, filename=str(file_path))

    hits: list[ProviderConditionalHit] = []
    _walk_for_provider_conditionals(tree, file_path, hits)
    return hits


def scan_provider_conditionals(
    packages: dict[str, PackageInfo],
    monorepo_root: Path,
) -> dict[Path, list[ProviderConditionalHit]]:
    """Scan every ``.py`` file under each of ``PROVIDER_CONDITIONAL_LANGUAGE_PACKAGES``'
    ``src/`` tree (via *packages*, as already discovered by ``discover_packages``)
    for platform-identity conditionals.

    Args:
        packages: Package name -> PackageInfo, as returned by discover_packages().
        monorepo_root: Monorepo root for relative path reporting.

    Returns:
        Mapping of file path -> hits in that file (files with zero hits omitted).
    """
    results: dict[Path, list[ProviderConditionalHit]] = {}

    for package_name in PROVIDER_CONDITIONAL_LANGUAGE_PACKAGES:
        package_info = packages.get(package_name)
        if package_info is None:
            continue

        for py_file in package_info.src_dir.rglob("*.py"):
            try:
                hits = scan_file_for_provider_conditionals(py_file)
            except SyntaxError as e:
                rel_path = py_file.relative_to(monorepo_root)
                print(
                    f"ERROR: Failed to parse {rel_path}:{e.lineno} - {e.msg}. "
                    f"A policed file that cannot be parsed would escape this scan "
                    f"(a silent blind spot); fix its syntax or encoding.",
                    file=sys.stderr,
                )
                sys.exit(2)
            except OSError as e:
                rel_path = py_file.relative_to(monorepo_root)
                print(
                    f"ERROR: Failed to read {rel_path} - {e}. A policed file that "
                    f"cannot be read would escape this scan; resolve the read error.",
                    file=sys.stderr,
                )
                sys.exit(2)

            if hits:
                results[py_file] = hits

    return results


def load_provider_conditional_baseline(baseline_path: Path) -> dict[str, int]:
    """Load ``{relative_file: frozen_count}`` from the provider-conditional
    baseline TOML.

    Args:
        baseline_path: Path to the provider-conditional baseline TOML file.

    Returns:
        An empty dict if the file does not exist yet (first-ever run, before
        this task's `--update-baseline` freezes it).
    """
    if not baseline_path.exists():
        return {}

    try:
        import tomllib  # Python 3.11+
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            print(
                "Warning: TOML library not available. Install tomli for baseline support.",
                file=sys.stderr,
            )
            return {}

    with baseline_path.open("rb") as f:
        data = tomllib.load(f)

    counts: dict[str, int] = {}
    for entry in data.get("baseline", []):
        if not isinstance(entry, dict):
            continue

        file_rel = entry.get("file", "")
        count = entry.get("count")

        if file_rel and isinstance(count, int):
            counts[file_rel] = count

    return counts


def write_provider_conditional_baseline(
    baseline_path: Path, counts: dict[str, int]
) -> None:
    """Write ``counts`` to the provider-conditional baseline TOML as
    ``[[baseline]] file=... count=...`` entries, sorted by file for
    deterministic diffs.

    Args:
        baseline_path: Path to the provider-conditional baseline TOML file to write.
        counts: Mapping of relative file path (forward slashes) -> hit count.
    """
    header = (
        "# I6 Successor Ratchet Baseline (invariant I6, DI-4/DI-5)\n"
        "#\n"
        "# Frozen per-file counts of platform-identity CONDITIONALS in the language\n"
        "# packages (datrix_codegen_python, datrix_codegen_typescript) -- the successor\n"
        "# form of the removed DeploymentProvider branches (the literal\n"
        "# `grep DeploymentProvider.` is already empty; DI-3 deleted the enum). These\n"
        "# sites are DI-5-deferred: legitimate today, but frozen so they cannot grow\n"
        "# while each cluster is migrated onto a decision engine.\n"
        "# Any INCREASE in a file's count fails datrix/scripts/dev/check-import-boundaries.py\n"
        "# --check-provider-conditionals. Decreases are always allowed and should be\n"
        "# captured by re-running with --update-baseline once a DI-5 change collapses a\n"
        "# cluster -- reaching 0 everywhere is the DI-5 end-state.\n"
        "#\n"
        "# Format:\n"
        "#   [[baseline]]\n"
        '#   file = "path/relative/to/monorepo-root, forward slashes"\n'
        "#   count = <int>\n"
    )

    lines = [header]
    for file_rel in sorted(counts.keys()):
        lines.append("\n[[baseline]]\n")
        lines.append(f'file = "{file_rel}"\n')
        lines.append(f"count = {counts[file_rel]}\n")

    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text("".join(lines), encoding="utf-8")


def check_provider_conditional_ratchet(
    current_counts: dict[str, int],
    baseline: dict[str, int],
) -> list[str]:
    """Compare *current_counts* against *baseline*; return one message per
    file whose count INCREASED (baseline missing == baseline 0). Never flags
    a decrease -- the ratchet only tightens (and reaching 0 is the DI-5 goal).

    Args:
        current_counts: Relative file path -> current hit count.
        baseline: Relative file path -> frozen baseline count.

    Returns:
        List of human-readable ratchet-failure messages, one per regressed
        file, sorted by file path.
    """
    messages: list[str] = []

    for file_rel in sorted(current_counts.keys()):
        current = current_counts[file_rel]
        frozen = baseline.get(file_rel, 0)
        if current > frozen:
            messages.append(
                f"{file_rel}: provider-conditional count increased from baseline "
                f"{frozen} to {current}"
            )

    return messages


def scan_file_for_function_level_imports(
    file_path: Path,
) -> list[FunctionLevelImportHit]:
    """AST-walk *file_path* for function-level imports (D4/I6 successor).

    A hit is any ``ast.Import``/``ast.ImportFrom`` node that is NOT a direct
    top-level statement of the module -- i.e., not a member of ``tree.body``
    itself, but nested one or more levels deeper (inside a function/method
    body, an ``if TYPE_CHECKING:`` block, a ``try``/``except``, etc.).
    Implementation: collect the ``id()`` of every node in ``tree.body`` (the
    top-level statement list) into a set, then ``ast.walk(tree)`` collecting
    every ``Import``/``ImportFrom`` node; a node counts as a hit iff its
    ``id()`` is not in the top-level set.

    Args:
        file_path: Path to Python source file.

    Returns:
        List of hits found in the file, in AST-walk order.

    Raises:
        SyntaxError: propagated from ast.parse (caller decides how to report).
        OSError: propagated if the file cannot be read.
    """
    # utf-8-sig transparently strips a leading UTF-8 BOM (U+FEFF) so a
    # BOM-prefixed file can never fail ast.parse and be silently skipped
    # (scanner integrity).
    source_code = file_path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source_code, filename=str(file_path))

    top_level_ids = {id(node) for node in tree.body}

    hits: list[FunctionLevelImportHit] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.Import, ast.ImportFrom))
            and id(node) not in top_level_ids
        ):
            hits.append(
                FunctionLevelImportHit(file_path=file_path, line_number=node.lineno)
            )
    return hits


def scan_function_level_imports(
    packages: dict[str, PackageInfo],
    monorepo_root: Path,
) -> dict[Path, list[FunctionLevelImportHit]]:
    """Scan every ``.py`` file under each of ``FUNCTION_LEVEL_IMPORT_PACKAGES``'
    ``src/`` tree (via *packages*, as already discovered by ``discover_packages``)
    for function-level imports.

    Args:
        packages: Package name -> PackageInfo, as returned by discover_packages().
        monorepo_root: Monorepo root for relative path reporting.

    Returns:
        Mapping of file path -> hits in that file (files with zero hits omitted).
    """
    results: dict[Path, list[FunctionLevelImportHit]] = {}

    for package_name in FUNCTION_LEVEL_IMPORT_PACKAGES:
        package_info = packages.get(package_name)
        if package_info is None:
            continue

        for py_file in package_info.src_dir.rglob("*.py"):
            try:
                hits = scan_file_for_function_level_imports(py_file)
            except SyntaxError as e:
                rel_path = py_file.relative_to(monorepo_root)
                print(
                    f"ERROR: Failed to parse {rel_path}:{e.lineno} - {e.msg}. "
                    f"A policed file that cannot be parsed would escape this scan "
                    f"(a silent blind spot); fix its syntax or encoding.",
                    file=sys.stderr,
                )
                sys.exit(2)
            except OSError as e:
                rel_path = py_file.relative_to(monorepo_root)
                print(
                    f"ERROR: Failed to read {rel_path} - {e}. A policed file that "
                    f"cannot be read would escape this scan; resolve the read error.",
                    file=sys.stderr,
                )
                sys.exit(2)

            if hits:
                results[py_file] = hits

    return results


def load_function_level_import_baseline(baseline_path: Path) -> dict[str, int]:
    """Load ``{relative_file: frozen_count}`` from the function-level-import
    baseline TOML.

    Args:
        baseline_path: Path to the function-level-import baseline TOML file.

    Returns:
        An empty dict if the file does not exist yet (first-ever run, before
        this task's `--update-baseline` freezes it).
    """
    if not baseline_path.exists():
        return {}

    try:
        import tomllib  # Python 3.11+
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            print(
                "Warning: TOML library not available. Install tomli for baseline support.",
                file=sys.stderr,
            )
            return {}

    with baseline_path.open("rb") as f:
        data = tomllib.load(f)

    counts: dict[str, int] = {}
    for entry in data.get("baseline", []):
        if not isinstance(entry, dict):
            continue

        file_rel = entry.get("file", "")
        count = entry.get("count")

        if file_rel and isinstance(count, int):
            counts[file_rel] = count

    return counts


def write_function_level_import_baseline(
    baseline_path: Path, counts: dict[str, int]
) -> None:
    """Write ``counts`` to the function-level-import baseline TOML as
    ``[[baseline]] file=... count=...`` entries, sorted by file for
    deterministic diffs.

    Args:
        baseline_path: Path to the function-level-import baseline TOML file to write.
        counts: Mapping of relative file path (forward slashes) -> hit count.
    """
    header = (
        "# Function-Level-Import Ratchet Baseline (D4/I6)\n"
        "#\n"
        "# Frozen per-file counts of function-level imports (any Import/ImportFrom\n"
        "# AST node that is not a direct top-level statement of its module --\n"
        "# nested in a function/method body, an `if TYPE_CHECKING:` block, or a\n"
        "# `try`/`except`) in datrix-common's src/ tree ONLY. D4 requires these to\n"
        '# "move back to module top with a ratchet": this baseline freezes the\n'
        "# count measured immediately after the Service/Shared decomposition\n"
        "# landed, so it reflects those import relocations rather than a stale\n"
        "# pre-decomposition number. Any INCREASE in a file's count fails\n"
        "# datrix/scripts/dev/check-import-boundaries.py\n"
        "# --check-function-level-imports. Decreases are always allowed and should\n"
        "# be captured by re-running with --update-baseline once later work\n"
        "# promotes more deferred imports back to module top -- a one-shot sweep of\n"
        "# all sites is deliberately rejected; each area migrates with the work\n"
        "# that next touches it.\n"
        "#\n"
        "# Format:\n"
        "#   [[baseline]]\n"
        '#   file = "path/relative/to/monorepo-root, forward slashes"\n'
        "#   count = <int>\n"
    )

    lines = [header]
    for file_rel in sorted(counts.keys()):
        lines.append("\n[[baseline]]\n")
        lines.append(f'file = "{file_rel}"\n')
        lines.append(f"count = {counts[file_rel]}\n")

    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text("".join(lines), encoding="utf-8")


def check_function_level_import_ratchet(
    current_counts: dict[str, int],
    baseline: dict[str, int],
) -> list[str]:
    """Compare *current_counts* against *baseline*; return one message per
    file whose count INCREASED (baseline missing == baseline 0). Never flags
    a decrease -- the ratchet only tightens.

    Args:
        current_counts: Relative file path -> current hit count.
        baseline: Relative file path -> frozen baseline count.

    Returns:
        List of human-readable ratchet-failure messages, one per regressed
        file, sorted by file path.
    """
    messages: list[str] = []

    for file_rel in sorted(current_counts.keys()):
        current = current_counts[file_rel]
        frozen = baseline.get(file_rel, 0)
        if current > frozen:
            messages.append(
                f"{file_rel}: function-level-import count increased from baseline "
                f"{frozen} to {current}"
            )

    return messages


def load_allowlist(allowlist_path: Path) -> list[AllowlistEntry]:
    """Load allowlist entries from TOML file.

    Args:
        allowlist_path: Path to allowlist TOML file

    Returns:
        List of allowlist entries (empty if file doesn't exist)
    """
    if not allowlist_path.exists():
        return []

    try:
        import tomllib  # Python 3.11+
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            print(
                "Warning: TOML library not available. Install tomli for allowlist support.",
                file=sys.stderr,
            )
            return []

    with allowlist_path.open("rb") as f:
        data = tomllib.load(f)

    entries: list[AllowlistEntry] = []
    for entry in data.get("allow", []):
        if not isinstance(entry, dict):
            continue

        file_pattern = entry.get("file", "")
        import_prefix = entry.get("import", "")
        issue_url = entry.get("issue", "")

        if file_pattern and import_prefix and issue_url:
            entries.append(
                AllowlistEntry(
                    file_pattern=file_pattern,
                    import_prefix=import_prefix,
                    issue_url=issue_url,
                )
            )

    return entries


def is_allowlisted(
    violation: Violation, allowlist: list[AllowlistEntry], monorepo_root: Path
) -> bool:
    """Check if a violation is allowlisted.

    Args:
        violation: The violation to check
        allowlist: List of allowlist entries
        monorepo_root: Monorepo root for relative path matching

    Returns:
        True if the violation is allowlisted, False otherwise
    """
    # Normalize to forward slashes for cross-platform matching
    rel_path = str(violation.file_path.relative_to(monorepo_root)).replace("\\", "/")

    for entry in allowlist:
        # Normalize allowlist pattern to forward slashes too
        pattern = entry.file_pattern.replace("\\", "/")
        # Simple substring matching for file patterns
        if pattern in rel_path and violation.imported_module.startswith(
            entry.import_prefix
        ):
            return True

    return False


def format_violation(violation: Violation, monorepo_root: Path) -> str:
    """Format a violation for output.

    Args:
        violation: The violation to format
        monorepo_root: Monorepo root for relative path calculation

    Returns:
        Formatted violation string
    """
    rel_path = violation.file_path.relative_to(monorepo_root)
    # Use forward slashes for consistency
    rel_path_str = str(rel_path).replace("\\", "/")

    return (
        f"{rel_path_str}:{violation.line_number}\n"
        f"  forbidden import: {violation.imported_module}\n"
        f"  rule: {violation.source_package} must not import {violation.forbidden_prefix}"
    )


def auto_detect_base_dir(script_path: Path) -> Path:
    """Auto-detect monorepo root by walking up from script location.

    Args:
        script_path: Path to this script

    Returns:
        Monorepo root directory

    Raises:
        FileNotFoundError: If monorepo root cannot be found
    """
    # Script is at datrix/scripts/dev/check-import-boundaries.py
    # Monorepo root is 3 levels up
    current = script_path.resolve().parent
    for _ in range(3):
        current = current.parent

    # Verify this looks like the monorepo root
    if (current / "datrix-common").exists():
        return current

    raise FileNotFoundError(
        f"Could not auto-detect monorepo root from {script_path}. "
        f"Use --base-dir to specify manually."
    )


# ---------------------------------------------------------------------------
# Self-Test (--self-test)
#
# Proves the rule model, the AST scanners, and the ratchet comparators are
# non-vacuous: every check below is exercised against both a known-good and a
# known-bad case, and the CLI mutation proof plants a real regression in an
# isolated fixture and proves detection + clearing on revert. Runs
# automatically as step 1 of every normal invocation (see main()); can also
# be run standalone via --self-test. Real files are written under
# D:\datrix\.tmp\ per this project's temp-file policy -- never
# unittest.mock/SimpleNamespace.
# ---------------------------------------------------------------------------

_SELF_TEST_SCRATCH_ROOT = Path("D:/datrix/.tmp/check_import_boundaries_selftest")

_GREEN = "\033[92m"
_RED = "\033[91m"
_CYAN = "\033[96m"
_RESET = "\033[0m"


def _step(message: str) -> None:
    print(f"\n{_CYAN}=== {message}{_RESET}")


def _check(label: str, condition: bool) -> bool:
    """Print [OK]/[FAIL] for one self-test assertion and return it."""
    if condition:
        print(f"{_GREEN}[OK]{_RESET} {label}")
    else:
        print(f"{_RED}[FAIL]{_RESET} {label}")
    return condition


def _rule_forbids(source_package: str, imported_module: str) -> bool:
    """True if any of source_package's forbidden_prefixes flags imported_module."""
    rule = BOUNDARY_RULES[source_package]
    return any(
        is_forbidden_import(source_package, imported_module, prefix, rule.allowed_subtrees)
        for prefix in rule.forbidden_prefixes
    )


def _self_test_allowed_denied_subtrees() -> bool:
    """The platform allowed-subtree carve-out constant is frozen exactly, and
    every representative allowed/denied import is classified correctly."""
    _step("Self-test 1/9: platform allowed/denied codegen-common subtrees")
    ok = True

    expected_allowed_subtrees: frozenset[str] = frozenset(
        [
            "datrix_codegen_common.gendsl",
            "datrix_codegen_common.dashboards",
            "datrix_codegen_common.algorithms.serverless",
            "datrix_codegen_common.context_models.serverless",
            "datrix_codegen_common.context_models.replayable_ingestion",
            "datrix_codegen_common.enums",
            "datrix_codegen_common.platform",
            "datrix_codegen_common.pooling",
            "datrix_codegen_common.secrets",
            "datrix_codegen_common.seed",
            "datrix_codegen_common.parity",
            "datrix_codegen_common.orchestration.resolved_runtime_plan",
            "datrix_codegen_common.testkit",
            "datrix_codegen_common.platform.container_image_supply",
        ]
    )
    ok &= _check(
        "PLATFORM_CODEGEN_COMMON_ALLOWED_SUBTREES matches the frozen expected set exactly "
        "(a silent shrink or an unreviewed addition would fail here)",
        PLATFORM_CODEGEN_COMMON_ALLOWED_SUBTREES == expected_allowed_subtrees,
    )

    platform_source = "datrix_codegen_aws"
    allowed_cases = (
        "datrix_codegen_common.gendsl",
        "datrix_codegen_common.gendsl.compiler",
        "datrix_codegen_common.dashboards.builder",
        "datrix_codegen_common.algorithms.serverless",
        "datrix_codegen_common.algorithms.serverless.plan",
        "datrix_codegen_common.context_models.serverless",
        "datrix_codegen_common.context_models.replayable_ingestion",
        "datrix_codegen_common.enums",
        "datrix_codegen_common.enums.DatabaseEngine",
        "datrix_codegen_common.platform.runtime",
    )
    for imported in allowed_cases:
        ok &= _check(
            f"allowed subtree not forbidden: {platform_source} -> {imported}",
            not _rule_forbids(platform_source, imported),
        )

    for platform in ("datrix_codegen_docker", "datrix_codegen_aws", "datrix_codegen_azure"):
        ok &= _check(
            f"gendsl carve-out applies to platform package {platform}",
            not _rule_forbids(platform, "datrix_codegen_common.gendsl"),
        )

    denied_cases = (
        "datrix_codegen_common.transpiler.parity_checker",
        "datrix_codegen_common.context_models.entity",
        "datrix_codegen_common.algorithms.entity",
        "datrix_codegen_python",
        "datrix_codegen_python.generators.api",
        "datrix_codegen_typescript",
    )
    for imported in denied_cases:
        ok &= _check(
            f"denied subtree flagged: {platform_source} -> {imported}",
            _rule_forbids(platform_source, imported),
        )

    return ok


def _self_test_dotted_precision_and_carveout() -> bool:
    """Subtree matching is exact-or-child (not raw prefix), and the carve-out
    never leaks to a package that did not opt in."""
    _step("Self-test 2/9: dotted-boundary precision and carve-out non-leakage")
    ok = True
    platform_source = "datrix_codegen_aws"

    ok &= _check(
        "'enums_other' is NOT a child of 'enums' -> forbidden",
        _rule_forbids(platform_source, "datrix_codegen_common.enums_other"),
    )
    ok &= _check(
        "'enums.DatabaseEngine' IS a child of 'enums' -> allowed",
        not _rule_forbids(platform_source, "datrix_codegen_common.enums.DatabaseEngine"),
    )
    ok &= _check(
        "'algorithms.serverless.plan' IS a child of 'algorithms.serverless' -> allowed",
        not _rule_forbids(platform_source, "datrix_codegen_common.algorithms.serverless.plan"),
    )
    ok &= _check(
        "'algorithms.serverlessX' is a SIBLING, not a child -> forbidden",
        _rule_forbids(platform_source, "datrix_codegen_common.algorithms.serverlessX"),
    )

    ok &= _check(
        "datrix_common's BoundaryRule has empty allowed_subtrees",
        BOUNDARY_RULES["datrix_common"].allowed_subtrees == frozenset(),
    )
    ok &= _check(
        "datrix_common still forbids datrix_codegen_python (no carve-out to leak from)",
        _rule_forbids("datrix_common", "datrix_codegen_python"),
    )
    ok &= _check(
        "datrix_codegen_common itself still forbids datrix_codegen_python",
        _rule_forbids("datrix_codegen_common", "datrix_codegen_python"),
    )
    for platform in ("datrix_codegen_docker", "datrix_codegen_aws", "datrix_codegen_azure"):
        ok &= _check(
            f"platform rule for {platform} carries a non-empty allowed_subtrees",
            bool(BOUNDARY_RULES[platform].allowed_subtrees),
        )

    return ok


def _self_test_sql_and_component_coverage() -> bool:
    """BOUNDARY_RULES covers datrix_codegen_sql and datrix_codegen_component,
    each enforcing the sibling-language prohibition absolutely."""
    _step("Self-test 3/9: SQL and Component boundary rule coverage")
    ok = True

    ok &= _check(
        "datrix_codegen_sql has a BOUNDARY_RULES entry",
        "datrix_codegen_sql" in BOUNDARY_RULES,
    )
    sql_rule = BOUNDARY_RULES["datrix_codegen_sql"]
    ok &= _check(
        "datrix_codegen_sql carries SQL_CODEGEN_COMMON_ALLOWED_SUBTREES exactly",
        sql_rule.allowed_subtrees == SQL_CODEGEN_COMMON_ALLOWED_SUBTREES,
    )
    for imported in ("datrix_codegen_typescript", "datrix_codegen_python", "datrix_cli"):
        ok &= _check(
            f"SQL sibling-language/CLI import forbidden: {imported}",
            _rule_forbids("datrix_codegen_sql", imported),
        )
    for imported in (
        "datrix_codegen_common.gendsl",
        "datrix_codegen_common.context_models.migration",
        "datrix_codegen_common.orchestration.migration_adapter",
    ):
        ok &= _check(
            f"SQL allowed codegen_common subtree NOT forbidden: {imported}",
            not _rule_forbids("datrix_codegen_sql", imported),
        )
    for imported in (
        "datrix_codegen_common.transpiler.parity_checker",
        "datrix_codegen_common.context_models.entity",
        "datrix_codegen_common.algorithms.entity",
    ):
        ok &= _check(
            f"SQL denied codegen_common subtree forbidden: {imported}",
            _rule_forbids("datrix_codegen_sql", imported),
        )

    ok &= _check(
        "datrix_codegen_component has a BOUNDARY_RULES entry",
        "datrix_codegen_component" in BOUNDARY_RULES,
    )
    ok &= _check(
        "datrix_codegen_component has empty allowed_subtrees (codegen_common unrestricted)",
        BOUNDARY_RULES["datrix_codegen_component"].allowed_subtrees == frozenset(),
    )
    for imported in ("datrix_codegen_typescript", "datrix_codegen_python", "datrix_cli"):
        ok &= _check(
            f"Component sibling-language/CLI import forbidden: {imported}",
            _rule_forbids("datrix_codegen_component", imported),
        )
    for imported in (
        "datrix_codegen_common.gendsl.compiler",
        "datrix_codegen_common.algorithms.serverless",
        "datrix_codegen_common.context_models.serverless",
    ):
        ok &= _check(
            f"Component codegen_common import NOT forbidden: {imported}",
            not _rule_forbids("datrix_codegen_component", imported),
        )

    return ok


#: The three platform generator packages. Each must forbid the OTHER TWO.
_PLATFORM_PACKAGES: tuple[str, ...] = (
    "datrix_codegen_docker",
    "datrix_codegen_aws",
    "datrix_codegen_azure",
)


def _self_test_platform_to_platform_prohibition() -> bool:
    """A platform plugin may never import a SIBLING platform plugin.

    The pre-existing self-tests only ever proved platform -> LANGUAGE imports
    are flagged; the platform -> PLATFORM edge was absent from every rule, so
    an aws -> docker import passed the checker in silence. This check pins the
    prohibition in the rule model for all six ordered sibling pairs, and
    proves the shared-layer escape route (importing the same algorithm from
    ``datrix_codegen_common.platform.container_image_supply``) is NOT flagged
    -- otherwise the rule would forbid the correct fix along with the wrong one.
    """
    _step("Self-test 4/9: platform -> sibling-platform import prohibition")
    ok = True

    for source in _PLATFORM_PACKAGES:
        siblings = [p for p in _PLATFORM_PACKAGES if p != source]
        for sibling in siblings:
            ok &= _check(
                f"sibling platform import forbidden: {source} -> {sibling}",
                _rule_forbids(source, sibling),
            )
            ok &= _check(
                f"sibling platform submodule import forbidden: {source} -> "
                f"{sibling}.generators.images.base_image_builder",
                _rule_forbids(source, f"{sibling}.generators.images.base_image_builder"),
            )

    # The correct home for shared platform logic must stay importable, or the
    # rule above would forbid the fix as well as the defect.
    for source in _PLATFORM_PACKAGES:
        ok &= _check(
            f"shared container-image-supply layer NOT forbidden: {source} -> "
            "datrix_codegen_common.platform.container_image_supply",
            not _rule_forbids(
                source, "datrix_codegen_common.platform.container_image_supply"
            ),
        )

    # A platform importing ITSELF is not a sibling import.
    for source in _PLATFORM_PACKAGES:
        ok &= _check(
            f"self-import not flagged: {source} -> {source}.generators",
            not _rule_forbids(source, f"{source}.generators"),
        )

    return ok


def _self_test_build_platform_fixture_monorepo(
    tmp_root: Path, *, import_sibling: bool
) -> Path:
    """Build a minimal isolated monorepo with a real datrix-codegen-aws package.

    Its one module imports either a SIBLING PLATFORM (docker -- a violation)
    or the shared codegen-common container-image-supply layer (the correct,
    permitted edge), so the same fixture proves both directions.
    """
    package_src = tmp_root / "datrix-codegen-aws" / "src" / "datrix_codegen_aws"
    package_src.mkdir(parents=True, exist_ok=True)
    (package_src / "__init__.py").write_text("", encoding="utf-8")

    module_path = package_src / "deploy_supply_context.py"
    module_path.write_text(
        _self_test_platform_module_source(import_sibling=import_sibling),
        encoding="utf-8",
    )
    return module_path


def _self_test_platform_module_source(*, import_sibling: bool) -> str:
    """Source for the platform fixture module: the violating import, or the fix."""
    if import_sibling:
        import_line = (
            "from datrix_codegen_docker.generators.images.base_image_builder import (\n"
            "    compute_base_image_tag,\n"
            ")"
        )
    else:
        import_line = (
            "from datrix_codegen_common.platform.container_image_supply import (\n"
            "    compute_base_image_tag,\n"
            ")"
        )
    return f"{import_line}\n\n\ndef f() -> str:\n    return compute_base_image_tag('x', 'app')\n"


def _self_test_run_boundary_cli(tmp_root: Path) -> "subprocess.CompletedProcess[str]":
    """Invoke THIS script's plain import-boundary scan against an isolated fixture."""
    return subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "--base-dir",
            str(tmp_root),
            "--skip-auto-self-test",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _self_test_platform_cli_non_vacuity() -> bool:
    """End-to-end proof the platform -> platform prohibition actually FIRES.

    Plants a real aws -> docker import in a real, isolated fixture monorepo,
    proves the scanner exits 1 and names it, then rewrites the SAME module to
    import the shared codegen-common layer instead and proves the failure
    clears (exit 0) -- i.e. the rule flags the defect and permits the fix.
    """
    _step(
        "Self-test 9/9: platform -> platform CLI mutation non-vacuity "
        "(plant a real aws -> docker import, prove detection, prove the shared-layer fix clears it)"
    )
    ok = True
    tmp_root = _SELF_TEST_SCRATCH_ROOT / f"platform-boundary-{uuid.uuid4().hex}"
    tmp_root.mkdir(parents=True, exist_ok=True)
    try:
        module_path = _self_test_build_platform_fixture_monorepo(
            tmp_root, import_sibling=True
        )

        violating_result = _self_test_run_boundary_cli(tmp_root)
        ok &= _check(
            "aws -> docker sibling-platform import exits 1, got "
            f"{violating_result.returncode}",
            violating_result.returncode == 1,
        )
        combined = violating_result.stdout + violating_result.stderr
        ok &= _check(
            "failure output names the forbidden imported package (datrix_codegen_docker)",
            "datrix_codegen_docker" in combined,
        )
        ok &= _check(
            "failure output names the violating file (deploy_supply_context.py)",
            "deploy_supply_context.py" in combined,
        )

        module_path.write_text(
            _self_test_platform_module_source(import_sibling=False), encoding="utf-8"
        )
        fixed_result = _self_test_run_boundary_cli(tmp_root)
        ok &= _check(
            "rewriting the SAME import to the shared codegen-common layer clears the "
            f"failure, got exit {fixed_result.returncode}",
            fixed_result.returncode == 0,
        )
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    return ok


def _self_test_provider_conditional_scanner() -> bool:
    """scan_file_for_provider_conditionals detects every known DI-5-deferred
    conditional shape and excludes every look-alike that must not ratchet."""
    _step("Self-test 5/9: provider-conditional AST scanner (detection + exclusion)")
    ok = True
    scratch_dir = _SELF_TEST_SCRATCH_ROOT / f"provider-scanner-{uuid.uuid4().hex}"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    cases: tuple[tuple[str, str, int, str], ...] = (
        (
            "providerid_eq.py",
            "def f(provider):\n    if provider == ProviderId('azure'):\n        return True\n"
            "    return False\n",
            1,
            "providerid_compare",
        ),
        (
            "providerid_ne_helper.py",
            "def f(deployment):\n    if resolve_provider_identity(deployment) != ProviderId('aws'):\n"
            "        return None\n    return 1\n",
            1,
            "providerid_compare",
        ),
        (
            "deployment_value_eq.py",
            "class G:\n    def f(self):\n        if self._deployment.provider.value == 'azure':\n"
            "            return True\n        return False\n",
            1,
            "deployment_provider_value_compare",
        ),
        (
            "deployment_str_ne.py",
            "class G:\n    def f(self):\n        if str(self._deployment.provider) != 'aws':\n"
            "            return []\n        return None\n",
            1,
            "deployment_provider_value_compare",
        ),
        (
            "match_case.py",
            "def f(provider_id):\n"
            "    match provider_id:\n"
            "        case p if p == ProviderId('aws'):\n"
            "            return 'a'\n"
            "        case p if p == ProviderId('azure'):\n"
            "            return 'b'\n"
            "        case _:\n"
            "            raise ValueError('unknown')\n",
            1,
            "match_case_provider_subject",
        ),
        (
            "other_axis_excluded.py",
            "class G:\n"
            "    def f(self, storage_block, email_config):\n"
            "        a = storage_block.config.provider == StorageProvider.MINIO\n"
            "        b = str(email_config.provider.value) == 'sendgrid'\n"
            "        return a, b\n",
            0,
            "",
        ),
        (
            "boundary_rewrap_excluded.py",
            "def resolve_provider_identity(deployment):\n"
            "    return ProviderId(deployment.provider.value)\n",
            0,
            "",
        ),
        (
            "dict_dispatch_excluded.py",
            "_DEPLOYED = frozenset({ProviderId('aws'), ProviderId('azure')})\n\n"
            "def f(provider):\n    if provider not in _DEPLOYED:\n        return []\n"
            "    return None\n",
            0,
            "",
        ),
        (
            "non_deployment_rooted_excluded.py",
            "def f(cfg):\n"
            "    return cfg.container if str(cfg.provider) == 'azure_blob' else cfg.bucket\n",
            0,
            "",
        ),
    )
    try:
        for filename, source, expected_count, expected_kind in cases:
            file_path = scratch_dir / filename
            file_path.write_text(source, encoding="utf-8")
            hits = scan_file_for_provider_conditionals(file_path)
            ok &= _check(
                f"{filename}: expected {expected_count} hit(s), got {len(hits)}",
                len(hits) == expected_count,
            )
            if expected_kind and hits:
                ok &= _check(
                    f"{filename}: hit kind == {expected_kind!r}",
                    hits[0].kind == expected_kind,
                )
    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)
    return ok


def _self_test_function_level_import_scanner() -> bool:
    """scan_file_for_function_level_imports counts zero for module-top
    imports and exactly one for each nested (function/TYPE_CHECKING/
    try-except) import."""
    _step("Self-test 6/9: function-level-import AST scanner")
    ok = True
    scratch_dir = _SELF_TEST_SCRATCH_ROOT / f"fli-scanner-{uuid.uuid4().hex}"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    cases: tuple[tuple[str, str, int], ...] = (
        (
            "module_top.py",
            "from __future__ import annotations\n\nimport os\nfrom pathlib import Path\n\n\n"
            "def f() -> None:\n    return None\n",
            0,
        ),
        ("function_body.py", "def f() -> object:\n    import json\n\n    return json\n", 1),
        (
            "type_checking_block.py",
            "from __future__ import annotations\n\nfrom typing import TYPE_CHECKING\n\n"
            "if TYPE_CHECKING:\n    from pathlib import Path\n\n\n"
            'def f(p: "Path") -> None:\n    return None\n',
            1,
        ),
        (
            "try_except.py",
            "try:\n    import tomllib\nexcept ImportError:\n    tomllib = None\n",
            1,
        ),
    )
    try:
        for filename, source, expected_count in cases:
            file_path = scratch_dir / filename
            file_path.write_text(source, encoding="utf-8")
            hits = scan_file_for_function_level_imports(file_path)
            ok &= _check(
                f"{filename}: expected {expected_count} hit(s), got {len(hits)}",
                len(hits) == expected_count,
            )
    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)
    return ok


def _self_test_ratchets() -> bool:
    """Both ratchet comparators fire on any per-file increase, never on a
    decrease, and treat a baseline-absent file as baseline 0."""
    _step("Self-test 7/9: ratchet comparators (regression / no-regression / missing-baseline-as-zero)")
    ok = True

    clean = check_provider_conditional_ratchet(
        {"datrix-codegen-python/src/datrix_codegen_python/foo.py": 3},
        {"datrix-codegen-python/src/datrix_codegen_python/foo.py": 3},
    )
    ok &= _check("provider-conditional ratchet: clean when current == baseline", clean == [])

    increase = check_provider_conditional_ratchet(
        {"datrix-codegen-python/src/datrix_codegen_python/foo.py": 4},
        {"datrix-codegen-python/src/datrix_codegen_python/foo.py": 3},
    )
    ok &= _check(
        "provider-conditional ratchet: fires once on a real increase, naming file + delta",
        len(increase) == 1 and "foo.py" in increase[0] and "increased from baseline 3 to 4" in increase[0],
    )

    decrease = check_provider_conditional_ratchet(
        {"datrix-codegen-python/src/datrix_codegen_python/foo.py": 1},
        {"datrix-codegen-python/src/datrix_codegen_python/foo.py": 3},
    )
    ok &= _check("provider-conditional ratchet: allows a decrease", decrease == [])

    missing_baseline = check_provider_conditional_ratchet(
        {"datrix-codegen-typescript/src/datrix_codegen_typescript/new_file.py": 1}, {}
    )
    ok &= _check(
        "provider-conditional ratchet: a file absent from baseline is treated as baseline 0",
        len(missing_baseline) == 1 and "increased from baseline 0 to 1" in missing_baseline[0],
    )

    fli_clean = check_function_level_import_ratchet(
        {"datrix-common/src/datrix_common/foo.py": 2},
        {"datrix-common/src/datrix_common/foo.py": 2},
    )
    ok &= _check("function-level-import ratchet: clean when current == baseline", fli_clean == [])

    fli_increase = check_function_level_import_ratchet(
        {"datrix-common/src/datrix_common/foo.py": 3},
        {"datrix-common/src/datrix_common/foo.py": 2},
    )
    ok &= _check(
        "function-level-import ratchet: fires once on a real increase, naming file + delta",
        len(fli_increase) == 1
        and "foo.py" in fli_increase[0]
        and "increased from baseline 2 to 3" in fli_increase[0],
    )

    fli_decrease = check_function_level_import_ratchet(
        {"datrix-common/src/datrix_common/foo.py": 1},
        {"datrix-common/src/datrix_common/foo.py": 5},
    )
    ok &= _check("function-level-import ratchet: allows a decrease", fli_decrease == [])

    fli_missing_baseline = check_function_level_import_ratchet(
        {"datrix-common/src/datrix_common/new_file.py": 1}, {}
    )
    ok &= _check(
        "function-level-import ratchet: a file absent from baseline is treated as baseline 0",
        len(fli_missing_baseline) == 1
        and "increased from baseline 0 to 1" in fli_missing_baseline[0],
    )

    return ok


def _self_test_module_source(function_level_import_count: int) -> str:
    """A module with exactly *function_level_import_count* function-body imports."""
    lines = ["def f() -> None:"]
    if function_level_import_count == 0:
        lines.append("    return None")
    else:
        for i in range(function_level_import_count):
            lines.append(f"    import json as _json_{i}")
        lines.append("    return None")
    return "\n".join(lines) + "\n"


def _self_test_build_fixture_monorepo(tmp_root: Path, initial_import_count: int) -> Path:
    """Build a minimal isolated monorepo: one datrix-common package with one
    module carrying *initial_import_count* function-level imports, plus a
    baseline TOML freezing exactly that count."""
    package_src = tmp_root / "datrix-common" / "src" / "datrix_common"
    package_src.mkdir(parents=True, exist_ok=True)
    (package_src / "__init__.py").write_text("", encoding="utf-8")

    module_path = package_src / "sample_module.py"
    module_path.write_text(_self_test_module_source(initial_import_count), encoding="utf-8")

    config_dir = tmp_root / "datrix" / "scripts" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    baseline_path = config_dir / "function-level-import-baseline.toml"
    baseline_path.write_text(
        "[[baseline]]\n"
        'file = "datrix-common/src/datrix_common/sample_module.py"\n'
        f"count = {initial_import_count}\n",
        encoding="utf-8",
    )
    return module_path


def _self_test_run_cli(tmp_root: Path) -> "subprocess.CompletedProcess[str]":
    """Invoke THIS script as a real subprocess against the isolated fixture.

    --skip-auto-self-test prevents the nested invocation from recursively
    re-running the self-test (which would otherwise spawn this same
    subprocess again, without end).
    """
    return subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "--base-dir",
            str(tmp_root),
            "--check-function-level-imports",
            "--skip-auto-self-test",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _self_test_cli_non_vacuity() -> bool:
    """End-to-end proof that --check-function-level-imports actually detects
    a regression: run as a real subprocess against a real, isolated,
    temporarily-mutated fixture tree -- never a simulated one, and never the
    real datrix-common source tree."""
    _step(
        "Self-test 8/9: function-level-import CLI mutation non-vacuity "
        "(plant a real regression, prove detection, prove it clears on revert)"
    )
    ok = True
    tmp_root = _SELF_TEST_SCRATCH_ROOT / f"cli-non-vacuity-{uuid.uuid4().hex}"
    tmp_root.mkdir(parents=True, exist_ok=True)
    try:
        module_path = _self_test_build_fixture_monorepo(tmp_root, initial_import_count=1)

        clean_result = _self_test_run_cli(tmp_root)
        ok &= _check(
            f"clean fixture (count matches baseline) exits 0, got {clean_result.returncode}",
            clean_result.returncode == 0,
        )

        module_path.write_text(_self_test_module_source(2), encoding="utf-8")
        failing_result = _self_test_run_cli(tmp_root)
        ok &= _check(
            f"mutated fixture (count exceeds baseline) exits 1, got {failing_result.returncode}",
            failing_result.returncode == 1,
        )
        ok &= _check(
            "failure output names the mutated file",
            "sample_module.py" in failing_result.stdout,
        )
        ok &= _check(
            "failure output names the exact count delta (1 -> 2)",
            "increased from baseline 1 to 2" in failing_result.stdout,
        )

        module_path.write_text(_self_test_module_source(1), encoding="utf-8")
        reverted_result = _self_test_run_cli(tmp_root)
        ok &= _check(
            f"reverting the mutation clears the failure, got exit {reverted_result.returncode}",
            reverted_result.returncode == 0,
        )
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    return ok


def run_self_test() -> bool:
    """Run every self-test check; return True iff all passed.

    This is the checker's own non-vacuity proof: the rule-model constants,
    the AST scanners, and the ratchet comparators are exercised against
    known-good and known-bad cases (including a real mutation-based CLI
    proof), so a change that silently breaks any of them is caught before
    the checker's findings are trusted.
    """
    results = [
        _self_test_allowed_denied_subtrees(),
        _self_test_dotted_precision_and_carveout(),
        _self_test_sql_and_component_coverage(),
        _self_test_platform_to_platform_prohibition(),
        _self_test_provider_conditional_scanner(),
        _self_test_function_level_import_scanner(),
        _self_test_ratchets(),
        _self_test_cli_non_vacuity(),
        _self_test_platform_cli_non_vacuity(),
    ]
    print()
    if all(results):
        print(f"{_GREEN}SELF-TEST PASSED{_RESET}: rule model, scanners, and ratchets are non-vacuous.")
        return True
    print(f"{_RED}SELF-TEST FAILED{_RESET}: see failures above.")
    return False


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 = clean/warn mode, 1 = violations found, 2 = error)
    """
    parser = argparse.ArgumentParser(
        description="Cross-package import boundary scanner for Datrix monorepo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-w",
        "--warn",
        action="store_true",
        help="Warning mode: report violations but exit 0",
    )
    parser.add_argument(
        "-b",
        "--base-dir",
        type=Path,
        help="Monorepo root directory (default: auto-detect)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print each file being scanned",
    )
    parser.add_argument(
        "--check-target-literals",
        action="store_true",
        help=(
            "Run the I1 target-literal ratchet check (invariant I1) "
            "in addition to the import-boundary check"
        ),
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help=(
            "Recompute current per-file counts and overwrite the frozen baseline(s), "
            "then exit 0. Updates target-literal-baseline.toml unless "
            "--check-provider-conditionals is passed (without --check-target-literals), "
            "in which case it updates provider-conditional-baseline.toml instead. "
            "Pass both --check-target-literals and --check-provider-conditionals to "
            "update both baselines in one run."
        ),
    )
    parser.add_argument(
        "--check-provider-conditionals",
        action="store_true",
        help=(
            "Run the I6 successor ratchet check (invariant I6, DI-4/DI-5) "
            "in addition to the import-boundary check"
        ),
    )
    parser.add_argument(
        "--check-function-level-imports",
        action="store_true",
        help=(
            "Run the function-level-import ratchet check (D4/I6) "
            "in addition to the import-boundary check. Scoped to "
            "datrix-common's src/ tree only."
        ),
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help=(
            "Run the self-test suite (rule-model, AST-scanner, and ratchet "
            "invariants, including a real mutation-based CLI non-vacuity proof) "
            "and exit -- does not run the import-boundary scan itself. The "
            "self-test also runs automatically as step 1 of every OTHER "
            "invocation of this script; pass this flag to run only the self-test."
        ),
    )
    parser.add_argument(
        "--skip-auto-self-test",
        action="store_true",
        help=argparse.SUPPRESS,  # internal: used only by the self-test's own nested CLI call
    )

    args = parser.parse_args()

    if args.skip_auto_self_test and args.self_test:
        print(
            "Error: --self-test and --skip-auto-self-test are mutually exclusive.",
            file=sys.stderr,
        )
        return 2

    if not args.skip_auto_self_test:
        self_test_passed = run_self_test()
        if args.self_test:
            return 0 if self_test_passed else 1
        if not self_test_passed:
            print(
                "\nError: self-test failed -- the checker itself is not provably "
                "correct, so its findings cannot be trusted. Fix the self-test "
                "failure(s) above before relying on this gate's result.",
                file=sys.stderr,
            )
            return 1

    # Determine monorepo root
    if args.base_dir:
        monorepo_root = args.base_dir.resolve()
    else:
        try:
            monorepo_root = auto_detect_base_dir(Path(__file__))
        except FileNotFoundError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 2

    if not monorepo_root.exists():
        print(f"Error: Monorepo root not found: {monorepo_root}", file=sys.stderr)
        return 2

    # Load allowlist
    allowlist_path = (
        monorepo_root
        / "datrix"
        / "scripts"
        / "config"
        / "import-boundary-allowlist.toml"
    )
    allowlist = load_allowlist(allowlist_path)

    # Discover packages
    packages = discover_packages(monorepo_root)
    if not packages:
        print(f"Error: No datrix packages found in {monorepo_root}", file=sys.stderr)
        return 2

    if args.verbose:
        print(f"Found {len(packages)} packages:", file=sys.stderr)
        for pkg_name in sorted(packages.keys()):
            print(f"  - {pkg_name}", file=sys.stderr)
        print("", file=sys.stderr)

    # Scan all packages
    all_violations: list[Violation] = []
    for package_name, package_info in sorted(packages.items()):
        violations = scan_package_for_violations(
            package_info,
            monorepo_root,
            args.verbose,
        )
        all_violations.extend(violations)

    # Filter out allowlisted violations
    non_allowlisted_violations = [
        v for v in all_violations if not is_allowlisted(v, allowlist, monorepo_root)
    ]

    # I1 target-literal ratchet (invariant I1) — opt-in via
    # --check-target-literals so existing no-flag import-boundary callers
    # keep their current behavior.
    target_literal_baseline_path = (
        monorepo_root / "datrix" / "scripts" / "config" / "target-literal-baseline.toml"
    )
    # I6 successor ratchet (invariant I6, DI-4/DI-5) — opt-in via
    # --check-provider-conditionals.
    provider_conditional_baseline_path = (
        monorepo_root
        / "datrix"
        / "scripts"
        / "config"
        / "provider-conditional-baseline.toml"
    )
    # Function-level-import ratchet (D4/I6) — opt-in
    # via --check-function-level-imports.
    function_level_import_baseline_path = (
        monorepo_root
        / "datrix"
        / "scripts"
        / "config"
        / "function-level-import-baseline.toml"
    )

    if args.update_baseline:
        updated_any = False

        # Provider-conditional baseline updates when explicitly requested via
        # --check-provider-conditionals. Function-level-import baseline
        # updates when explicitly requested via --check-function-level-imports.
        # Target-literal baseline updates unless one of those two OTHER
        # ratchets was requested without --check-target-literals also being
        # requested (preserves the pre-existing --update-baseline-alone =>
        # target-literal behavior for existing callers).
        if args.check_provider_conditionals:
            provider_hits_by_file = scan_provider_conditionals(packages, monorepo_root)
            current_counts = {
                str(file_path.relative_to(monorepo_root)).replace("\\", "/"): len(hits)
                for file_path, hits in provider_hits_by_file.items()
            }
            write_provider_conditional_baseline(
                provider_conditional_baseline_path, current_counts
            )
            print(
                f"Updated I6 provider-conditional baseline: {len(current_counts)} file(s) "
                f"recorded at {provider_conditional_baseline_path.relative_to(monorepo_root)}"
            )
            updated_any = True

        if args.check_function_level_imports:
            function_level_hits_by_file = scan_function_level_imports(packages, monorepo_root)
            current_counts = {
                str(file_path.relative_to(monorepo_root)).replace("\\", "/"): len(hits)
                for file_path, hits in function_level_hits_by_file.items()
            }
            write_function_level_import_baseline(
                function_level_import_baseline_path, current_counts
            )
            print(
                f"Updated function-level-import baseline: {len(current_counts)} file(s) "
                f"recorded at {function_level_import_baseline_path.relative_to(monorepo_root)}"
            )
            updated_any = True

        if args.check_target_literals or not (
            args.check_provider_conditionals or args.check_function_level_imports
        ):
            target_literal_hits_by_file = scan_target_literals(packages, monorepo_root)
            current_counts = {
                str(file_path.relative_to(monorepo_root)).replace("\\", "/"): len(hits)
                for file_path, hits in target_literal_hits_by_file.items()
            }
            write_target_literal_baseline(target_literal_baseline_path, current_counts)
            print(
                f"Updated I1 target-literal baseline: {len(current_counts)} file(s) "
                f"recorded at {target_literal_baseline_path.relative_to(monorepo_root)}"
            )
            updated_any = True

        if updated_any:
            return 0

    target_literal_messages: list[str] = []
    if args.check_target_literals:
        if not target_literal_baseline_path.exists():
            print(
                f"Error: I1 target-literal baseline not found at "
                f"{target_literal_baseline_path}. Run "
                f"'check-import-boundaries.py --check-target-literals --update-baseline' "
                f"first to freeze the initial baseline.",
                file=sys.stderr,
            )
            return 2

        baseline = load_target_literal_baseline(target_literal_baseline_path)
        target_literal_hits_by_file = scan_target_literals(packages, monorepo_root)
        current_counts = {
            str(file_path.relative_to(monorepo_root)).replace("\\", "/"): len(hits)
            for file_path, hits in target_literal_hits_by_file.items()
        }
        target_literal_messages = check_target_literal_ratchet(current_counts, baseline)

    provider_conditional_messages: list[str] = []
    if args.check_provider_conditionals:
        if not provider_conditional_baseline_path.exists():
            print(
                f"Error: I6 provider-conditional baseline not found at "
                f"{provider_conditional_baseline_path}. Run "
                f"'check-import-boundaries.py --check-provider-conditionals --update-baseline' "
                f"first to freeze the initial baseline.",
                file=sys.stderr,
            )
            return 2

        baseline = load_provider_conditional_baseline(
            provider_conditional_baseline_path
        )
        provider_hits_by_file = scan_provider_conditionals(packages, monorepo_root)
        current_counts = {
            str(file_path.relative_to(monorepo_root)).replace("\\", "/"): len(hits)
            for file_path, hits in provider_hits_by_file.items()
        }
        provider_conditional_messages = check_provider_conditional_ratchet(
            current_counts, baseline
        )

    function_level_import_messages: list[str] = []
    if args.check_function_level_imports:
        if not function_level_import_baseline_path.exists():
            print(
                f"Error: function-level-import baseline not found at "
                f"{function_level_import_baseline_path}. Run "
                f"'check-import-boundaries.py --check-function-level-imports --update-baseline' "
                f"first to freeze the initial baseline.",
                file=sys.stderr,
            )
            return 2

        baseline = load_function_level_import_baseline(
            function_level_import_baseline_path
        )
        function_level_hits_by_file = scan_function_level_imports(packages, monorepo_root)
        current_counts = {
            str(file_path.relative_to(monorepo_root)).replace("\\", "/"): len(hits)
            for file_path, hits in function_level_hits_by_file.items()
        }
        function_level_import_messages = check_function_level_import_ratchet(
            current_counts, baseline
        )

    # Report violations / ratchet failures
    if (
        non_allowlisted_violations
        or target_literal_messages
        or provider_conditional_messages
        or function_level_import_messages
    ):
        mode = "Warning" if args.warn else "Error"

        if non_allowlisted_violations:
            print(
                f"{mode}: Found {len(non_allowlisted_violations)} import boundary violations:\n"
            )
            for violation in non_allowlisted_violations:
                print(format_violation(violation, monorepo_root))
                print()  # Blank line between violations

        if target_literal_messages:
            print(
                f"{mode}: I1 target-literal ratchet failed for "
                f"{len(target_literal_messages)} file(s):\n"
            )
            for message in target_literal_messages:
                print(message)
            print()

        if provider_conditional_messages:
            print(
                f"{mode}: I6 provider-conditional ratchet failed for "
                f"{len(provider_conditional_messages)} file(s):\n"
            )
            for message in provider_conditional_messages:
                print(message)
            print()

        if function_level_import_messages:
            print(
                f"{mode}: function-level-import ratchet failed for "
                f"{len(function_level_import_messages)} file(s):\n"
            )
            for message in function_level_import_messages:
                print(message)
            print()

        if args.warn:
            return 0
        return 1

    # Clean
    if args.verbose:
        print("No import boundary violations found.", file=sys.stderr)
        if args.check_target_literals:
            print("No I1 target-literal ratchet regressions found.", file=sys.stderr)
        if args.check_provider_conditionals:
            print(
                "No I6 provider-conditional ratchet regressions found.", file=sys.stderr
            )
        if args.check_function_level_imports:
            print(
                "No function-level-import ratchet regressions found.", file=sys.stderr
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
