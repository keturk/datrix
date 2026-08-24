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
`match`/`case` over a provider), PLUS a second AST pattern class (D5): a
bare `<var> == "<provider-id>"` comparison with no `ProviderId`/`.provider`
wrapper, and a closed-world provider-id collection literal such as
`frozenset({"azure"})` -- and fails if any file's count increases past its
frozen baseline (scripts/config/provider-conditional-baseline.toml).
These sites are DI-5-deferred; the ratchet freezes them so they cannot grow,
and drives to zero as each cluster is migrated onto a decision engine.
--update-baseline (combined with --check-provider-conditionals) recomputes
and overwrites that baseline.

Also implements a DISTINCT, stricter D6.1 check that runs unconditionally
whenever --check-provider-conditionals is passed: the same two D5 patterns
plus the pre-existing ProviderId/match-case forms, applied to the three
SHARED packages (datrix_common, datrix_codegen_common, datrix_cli) and held
at a hard zero with no baseline file to grandfather a hit into -- any single
occurrence fails, since shared layers must never encode platform-specific
policy (Principle 10, D1).

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

Also implements the G1 shared-vocabulary ratchet (Decision D3, Invariant I2):
opt-in via --check-shared-vocabulary, it AST-scans the LANGUAGE package src/
trees (LANGUAGE_PACKAGES, the declared taxonomy) for a module-level
frozenset/set/dict whose normalized member set duplicates a vocabulary
already declared in datrix_codegen_common.enums (read live from the
installed package at scan time, never mirrored) -- the DSL vocabulary
re-scattered as hand-rolled string literals after being centralised -- and
fails if any file's count increases past its frozen baseline
(scripts/config/shared-vocabulary-baseline.toml). A container built entirely
from qualified EnumClass.MEMBER references is CONSUMING the enum, not
hardcoding it, and is never flagged. The canonical side of this comparison
covers every module-level member-set declaration in enums.py, not only
``str, Enum`` classes: a plain module-level dict's KEY set (e.g.
DSL_EXCEPTION_HTTP_STATUS, NOSQL_UNSUPPORTED_METHODS) or a set/frozenset's
element set (e.g. LOG_BUILTIN_METHODS, itself derived from BUILTIN_REGISTRY
rather than hand-listed) is exactly as canonical as an Enum class's value
set, and a bare-literal redeclaration of either is the same defect.
--update-baseline (combined with --check-shared-vocabulary) recomputes and
overwrites that baseline.

Also implements the G2 shared-layer target-name ratchet (Decision D4, Invariant I3):
opt-in via --check-shared-target-names, it AST-scans ONLY datrix_codegen_common's
src/ tree (SHARED_TARGET_NAME_PACKAGES, a single-package tuple -- deliberately
narrower than I1's three-package scope) for any class, function, dataclass field,
type alias, or type reference whose identifier carries a registered LANGUAGE name
as an identifier segment (read live via registered_language_names() --
datrix.platforms is never consulted, since the registered platform name "local" is
also an ordinary English word). This is a DIFFERENT check from I1: I1 matches a
frozen list of specific central-table names, G2 matches the SHAPE of an identifier
against an open, runtime-derived vocabulary, so it would catch a brand-new
language-named class I1's frozen list has never heard of. Fails if any file's
count increases past its frozen baseline
(scripts/config/shared-target-name-baseline.toml).
--update-baseline (combined with --check-shared-target-names) recomputes and
overwrites that baseline.

Also implements the G3 cross-package vocabulary ratchet (Decision D2.1-D2.4):
opt-in via --check-cross-package-vocabulary, it AST-scans EVERY discovered
datrix-* package's src/ tree (via discover_packages() -- not only the four
LANGUAGE packages G1 scans) for a module-level set/frozenset/dict/tuple
literal, normalizes each one's member set, and fails when the SAME
normalized member set is declared with a bare string literal in two or
more DISTINCT packages -- independent of whether either copy also
duplicates a datrix_codegen_common.enums vocabulary (that comparison is
G1's job; G3 compares packages against each other directly, with no
notion of a canonical source). A value set declared twice within the SAME
package is a different, already-tracked defect (intra-package DRY, not
G3) and is never counted here. A container built entirely from qualified
EnumClass.MEMBER references is CONSUMING a vocabulary, not hardcoding it,
and is never flagged -- the same has_bare_literal gate G1 uses, classified
PURELY BY AST SHAPE (never by resolving against datrix_codegen_common.enums
the way G1 does -- G3 must never consult that module). Fails if
any file's count increases past its frozen baseline
(scripts/config/cross-package-vocabulary-baseline.toml).
--update-baseline (combined with --check-cross-package-vocabulary)
recomputes and overwrites that baseline.

Self-test (--self-test): proves the rule model (BOUNDARY_RULES, the allowed-
subtree carve-outs), the AST scanners (provider-conditional,
function-level-import, shared-vocabulary, shared-target-name,
cross-package-vocabulary), and the ratchet comparators are non-vacuous --
including a real mutation-based CLI proof (plants a
regression in an isolated fixture monorepo, proves the CLI detects it,
proves it clears on revert). The self-test runs automatically as step 1 of
EVERY normal invocation of this script (not only when --self-test is
passed): a run whose self-test fails aborts before any real finding is
reported, since a checker that cannot prove its own logic cannot be trusted.
Pass --self-test alone to run only the self-test and skip the real scan.
--skip-auto-self-test is an internal flag used solely by the self-test's own
nested CLI invocation (to avoid it recursively re-running the self-test on
itself) and is not intended for direct use.

Exit codes:
    0: Clean (no violations) or --warn mode
    1: Violations found in fail mode (import-boundary and/or I1/I6/function-
       level-import/shared-vocabulary/shared-target-name/cross-package-
       vocabulary ratchets), or a self-test failure
    2: Usage error, configuration error, or (with --check-target-literals,
       --check-provider-conditionals, --check-function-level-imports,
       --check-shared-vocabulary, --check-shared-target-names, or
       --check-cross-package-vocabulary) a missing baseline file
"""

import argparse
import ast
import enum
import re
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Literal

# D5: the provider-literal ratchet must enumerate provider ids from the
# installed datrix.platforms entry points, never a hardcoded
# "aws"/"azure"/"docker"/"local" literal. registered_platform_names() lives
# under scripts/library/shared/ (a script tree, not an installed package),
# so it is reached the same way reference_example_parity.py reaches
# shared.registered_targets: insert scripts/library/ onto sys.path.
_LIBRARY_DIR = Path(__file__).resolve().parent.parent / "library"
if _LIBRARY_DIR.exists() and str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from shared.registered_targets import (  # noqa: E402
    registered_language_names,
    registered_platform_names,
)


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
# platform generators (docker, aws, azure) are permitted to import. Every entry
# carries a written reason directly above it, and the set is frozen a second
# time in this script's own self-test, so adding one is a reviewed act rather
# than an edit that quietly widens the boundary.
#
# Matching is exact-or-child, never raw prefix: an entry naming a MODULE admits
# that module and its children and nothing else beside it. That precision is
# what lets a mixed package expose only its neutral half -- see
# ``algorithms.cqrs_projection_receivers``, which is allowed while its sibling
# ``algorithms.cqrs`` stays denied.
#
# The bar for an entry is that the fact is target-neutral AND genuinely crosses
# the axis: a platform provisions the resource an emitted consumer binds, so a
# single definition is the only thing that keeps the two from drifting. When a
# module holds such a fact next to a language-shaped one, the fix is to split
# the module -- never to admit the whole thing.
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
        # The canonical, subscriber-scoped Azure Service Bus subscription-name
        # algorithm -- a deterministic infrastructure-naming function with
        # zero per-target variation, sibling in kind to the already-allowed
        # ``algorithms.serverless``. Consumed by azure src (the Service Bus
        # topic/subscription provisioning builder in
        # ``resource_mapping/_pubsub.py``), plus the Python and .NET
        # messaging-runtime emit helpers, so the name a subscriber binds at
        # runtime and the name Azure provisions can never drift out of sync.
        "datrix_codegen_common.algorithms.servicebus_naming",
        # The peek-lock duration written into the provisioned Service Bus
        # entity, and the renewal budget the emitted consumer uses. THE SAME
        # FACT crosses both axes -- azure provisions ``lockDuration``, the
        # language emitters renew against it -- so it is a shared constant by
        # construction, exactly like ``servicebus_naming`` above (it exists
        # because the two provisioning code paths had already drifted to PT30S
        # vs PT1M for the one fact). Azure imports only the duration constant.
        "datrix_codegen_common.algorithms.servicebus_lock_renewal",
        # The (physical topic, receiver base) pairs a service's CQRS
        # projections bind. Provisioning and consumer emission MUST derive
        # their receiver set from one function or the consumer binds entities
        # nothing created -- the defect this module's own canonical marker
        # records. Split out of ``algorithms.cqrs`` for this rule rather than
        # admitted through it: that module also builds ``CqrsContext``, a
        # language-shaped surface, and carving out the whole module to reach
        # the neutral half would have handed every platform the other half.
        "datrix_codegen_common.algorithms.cqrs_projection_receivers",
        # Shared raise-site bodies for the W5 guards. The rate-limit guard here
        # exists BECAUSE aws, azure and docker each wrote their own copy of it;
        # the per-platform declaration is the field rows each passes in, not the
        # guard. Every caller raises the same ``GenerationError``, so no
        # per-target exception type crosses this edge either.
        "datrix_codegen_common.generation.raise_site_guards",
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
    # Angular client-target generator: forbidden from every backend language generator and
    # datrix_cli -- a frontend client target is not a language generator, but (like Component)
    # legitimately imports datrix_codegen_common freely (the shared client contract builder,
    # GenDSL registrations), so datrix_codegen_common is NOT on its forbidden list. Without
    # this entry the scanner has NO rule for this package at all ("no rule means no
    # restrictions", :945-948) -- silently unguarded, not merely permissive by design.
    "datrix_codegen_angular": BoundaryRule(
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


# D6.1 second half: the SHARED packages the provider-literal pattern's scan
# scope extends to, held at a HARD ZERO (not the language packages' decrease-
# only ratchet against a grandfathered baseline -- see
# check_shared_package_provider_literals below for why the enforcement shape
# is deliberately different). Mirrors TARGET_LITERAL_SHARED_PACKAGES exactly:
# the three packages D1 names as the shared layer that must never encode
# platform-specific policy itself.
PROVIDER_LITERAL_SHARED_PACKAGES: tuple[str, ...] = (
    "datrix_common",
    "datrix_codegen_common",
    "datrix_cli",
)


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


def _string_literal_value(node: ast.AST) -> str | None:
    """Bare string-literal value of *node*, or None for any other expression
    shape (a Name, an f-string, a call, ...). Both D5 sub-patterns below only
    fire on an ACTUAL literal, never a variable that merely happens to be
    assigned a provider-id string elsewhere -- that keeps the ratchet
    precise (see ``_provider_literal_compare_kind``'s docstring for why a
    look-alike like ``"consul"`` must never match).
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _provider_literal_compare_kind(
    node: ast.Compare, provider_ids: frozenset[str]
) -> Literal["provider_literal_compare"] | None:
    """D5's first provider-literal sub-pattern (invariant I6 successor,
    second AST pattern class): a plain Eq/NotEq comparison whose comparand
    (either side) is a bare string literal exactly equal to a REGISTERED
    platform provider id -- e.g. ``backend == "azure"``. This is the
    successor form the existing ``_provider_conditional_compare_kind`` does
    not cover: no ``ProviderId(...)`` wrapper, no ``.provider`` root, just a
    plain variable compared to a plain provider-name string.

    Only called for a Compare node the FIRST (ProviderId-shaped) pattern
    already rejected -- see ``_walk_for_provider_conditionals`` -- so the two
    never double-count the same node.

    Specificity comes entirely from membership in *provider_ids* (enumerated
    from the installed ``datrix.platforms`` entry points at scan time, never
    hardcoded): a literal equal to some OTHER string -- e.g. ``"consul"``, a
    service-discovery type, or ``"elasticsearch"``, a search backend -- never
    matches, however provider-adjacent the surrounding code looks.

    Args:
        node: The `ast.Compare` node under consideration.
        provider_ids: The registered platform provider ids for this scan run.

    Returns:
        ``"provider_literal_compare"`` on a match, else ``None``.
    """
    if len(node.ops) != 1 or not isinstance(node.ops[0], (ast.Eq, ast.NotEq)):
        return None
    sides = [node.left, node.comparators[0]]
    if any(_string_literal_value(side) in provider_ids for side in sides):
        return "provider_literal_compare"
    return None


def _provider_literal_container_ids(
    node: ast.AST, provider_ids: frozenset[str]
) -> frozenset[str]:
    """Provider ids among a List/Tuple/Set literal's OWN elements (D5's
    second provider-literal sub-pattern).

    Catches a closed-world provider-id collection literal wherever it is
    DEFINED -- ``frozenset({"azure"})``, ``{"aws", "azure"}``,
    ``("aws", "azure")`` -- not only when it sits directly inside a
    ``Compare``/``in`` test. This is the shape the confirmed real site at
    ``datrix-codegen-dotnet/.../generators/service/_infra_secret_handles.py:31``
    needs: ``_ALWAYS_REQUIRES_CREDENTIALS = frozenset({"azure"})`` is a
    collection-literal DEFINITION; the later ``backend in
    _ALWAYS_REQUIRES_CREDENTIALS`` membership test (a different line) compares
    against a bare ``Name``, which a Compare-only scan would never resolve
    back to the literal. Scanning every qualifying collection literal as its
    own node -- independent of its parent -- closes that gap.

    CLOSED-WORLD requirement (the precision fix a real scan run surfaced):
    every string-literal element of the collection must ITSELF be a
    registered provider id, not merely at-least-one. A collection that mixes
    a provider id with an OTHER axis's own literal -- e.g.
    ``SUPPORTED_STORAGE_PROVIDERS = frozenset({"s3", "minio", "azure_blob",
    "local"})`` in ``datrix-codegen-dotnet/.../generators/persistence/
    storage_generator.py`` -- is that StorageProvider axis's own closed
    world (``s3``/``minio``/``azure_blob`` are never registered platform
    provider ids), not a platform-identity collection; "local" landing in it
    is coincidental token overlap, not a deployment-platform conditional, and
    must not ratchet. A genuine platform-identity collection (like
    ``_ALWAYS_REQUIRES_CREDENTIALS`` above) is drawn ENTIRELY from
    ``provider_ids`` with no off-axis sibling literal, so the subset check
    below distinguishes the two without any axis-name heuristic.

    Args:
        node: Any AST node; only `ast.List`/`ast.Tuple`/`ast.Set` produce hits.
        provider_ids: The registered platform provider ids for this scan run.

    Returns:
        *node*'s string-literal elements when they are a non-empty subset of
        *provider_ids* (i.e. closed-world), else an empty frozenset.
    """
    if not isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return frozenset()
    string_literals = frozenset(
        value for elt in node.elts if (value := _string_literal_value(elt)) is not None
    )
    if not string_literals or not string_literals.issubset(provider_ids):
        return frozenset()
    return string_literals


@dataclass(frozen=True)
class ProviderConditionalHit:
    """One occurrence of a platform-identity conditional in a language-package file."""

    file_path: Path
    line_number: int
    kind: Literal[
        "providerid_compare",
        "deployment_provider_value_compare",
        "match_case_provider_subject",
        "provider_literal_compare",
        "provider_literal_container",
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
            import tomli as tomllib  # type: ignore[no-redef, import-not-found]
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
    provider_ids: frozenset[str],
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

    D5 second pattern class (added by this task): every ``ast.Compare`` node
    the existing ``ProviderId``-shaped pattern rejects is ALSO checked against
    ``_provider_literal_compare_kind`` (a bare literal comparand), and every
    ``ast.List``/``ast.Tuple``/``ast.Set`` node encountered anywhere in the
    walk is checked against ``_provider_literal_container_ids`` (a
    closed-world provider-id collection literal). Neither new check can
    double-count a node the first three forms already claimed, because the
    literal-compare check only runs when the ProviderId-shaped check returned
    ``None``, and the container check is a disjoint node type (a Compare node
    is never simultaneously a List/Tuple/Set node).
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
                _walk_for_provider_conditionals(stmt, file_path, hits, provider_ids)
        return

    if isinstance(node, ast.Compare):
        compare_kind: (
            Literal[
                "providerid_compare",
                "deployment_provider_value_compare",
                "provider_literal_compare",
            ]
            | None
        ) = _provider_conditional_compare_kind(node)
        if compare_kind is None:
            compare_kind = _provider_literal_compare_kind(node, provider_ids)
        kind = compare_kind
        if kind is not None:
            hits.append(
                ProviderConditionalHit(
                    file_path=file_path, line_number=node.lineno, kind=kind
                )
            )
    elif isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        if _provider_literal_container_ids(node, provider_ids):
            hits.append(
                ProviderConditionalHit(
                    file_path=file_path,
                    line_number=node.lineno,
                    kind="provider_literal_container",
                )
            )

    for child in ast.iter_child_nodes(node):
        _walk_for_provider_conditionals(child, file_path, hits, provider_ids)


def scan_file_for_provider_conditionals(
    file_path: Path, provider_ids: frozenset[str]
) -> list[ProviderConditionalHit]:
    """AST-walk *file_path* for platform-identity conditionals (I6 successor
    ratchet, DI-4/DI-5, plus the D5 provider-literal patterns).

    See ``_provider_conditional_compare_kind``, ``_match_subject_is_provider``,
    ``_provider_literal_compare_kind``, and ``_provider_literal_container_ids``
    for the exact matched/excluded shapes.

    Args:
        file_path: Path to Python source file.
        provider_ids: The registered platform provider ids this scan run
            checks literals against (see ``registered_platform_names()``).

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
    _walk_for_provider_conditionals(tree, file_path, hits, provider_ids)
    return hits


def scan_provider_conditionals(
    packages: dict[str, PackageInfo],
    monorepo_root: Path,
) -> dict[Path, list[ProviderConditionalHit]]:
    """Scan every ``.py`` file under each of ``PROVIDER_CONDITIONAL_LANGUAGE_PACKAGES``'
    ``src/`` tree (via *packages*, as already discovered by ``discover_packages``)
    for platform-identity conditionals. Provider ids are derived once per
    call via ``registered_platform_names()`` -- never hardcoded -- and passed
    to every per-file scan.

    Args:
        packages: Package name -> PackageInfo, as returned by discover_packages().
        monorepo_root: Monorepo root for relative path reporting.

    Returns:
        Mapping of file path -> hits in that file (files with zero hits omitted).
    """
    results: dict[Path, list[ProviderConditionalHit]] = {}
    provider_ids = registered_platform_names()

    for package_name in PROVIDER_CONDITIONAL_LANGUAGE_PACKAGES:
        package_info = packages.get(package_name)
        if package_info is None:
            continue

        for py_file in package_info.src_dir.rglob("*.py"):
            try:
                hits = scan_file_for_provider_conditionals(py_file, provider_ids)
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


def scan_shared_package_provider_literals(
    packages: dict[str, PackageInfo],
    monorepo_root: Path,
) -> dict[Path, list[ProviderConditionalHit]]:
    """Scan every ``.py`` file under each of ``PROVIDER_LITERAL_SHARED_PACKAGES``'
    ``src/`` tree for platform-identity conditionals -- REUSES
    ``scan_file_for_provider_conditionals`` (the two D5 sub-patterns plus the
    pre-existing ``ProviderId``/``match``-case forms) unmodified; only the
    package SCOPE differs from ``scan_provider_conditionals`` (which targets
    ``PROVIDER_CONDITIONAL_LANGUAGE_PACKAGES``).

    Args:
        packages: Package name -> PackageInfo, as returned by discover_packages().
        monorepo_root: Monorepo root for relative path reporting.

    Returns:
        Mapping of file path -> hits in that file (files with zero hits omitted).
    """
    results: dict[Path, list[ProviderConditionalHit]] = {}
    provider_ids = registered_platform_names()

    for package_name in PROVIDER_LITERAL_SHARED_PACKAGES:
        package_info = packages.get(package_name)
        if package_info is None:
            continue

        for py_file in package_info.src_dir.rglob("*.py"):
            try:
                hits = scan_file_for_provider_conditionals(py_file, provider_ids)
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


def check_shared_package_provider_literals(
    hits_by_file: dict[Path, list[ProviderConditionalHit]],
    monorepo_root: Path,
) -> list[str]:
    """Return one message per hit found in a shared package -- ANY hit fails.

    Unlike ``check_provider_conditional_ratchet`` (decrease-only against a
    frozen, non-zero baseline for the language packages), this comparator
    has no baseline at all: a shared package's provider-literal count must
    be exactly zero, always. Returns an empty list only when
    ``hits_by_file`` is empty.

    Args:
        hits_by_file: Output of `scan_shared_package_provider_literals`.
        monorepo_root: Monorepo root for relative path reporting.

    Returns:
        List of human-readable failure messages, one per hit, sorted by
        (file, line).
    """
    messages: list[str] = []
    for file_path in sorted(hits_by_file):
        rel_path = file_path.relative_to(monorepo_root)
        for hit in sorted(hits_by_file[file_path], key=lambda h: h.line_number):
            messages.append(
                f"{rel_path}:{hit.line_number}: shared-package provider-literal "
                f"conditional ({hit.kind}) -- shared layers must never encode "
                "platform-specific policy (Principle 10, D1). Fix: replace this "
                "conditional with a PlatformCapabilityDeclaration/LanguagePlugin "
                "field the affected platform declares, and ask the resolved "
                "plugin instead of comparing a provider identifier here."
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


# ---------------------------------------------------------------------------
# G1 Shared-Vocabulary Ratchet (Decision D3, Invariant I2)
#
# Fails when a datrix-codegen-{lang} module declares a module-level
# frozenset/set/dict whose normalized member set equals a member set already
# declared in datrix_codegen_common.enums. The four LANGUAGE packages this
# ratchet polices -- reuses LANGUAGE_PACKAGES (the single taxonomy
# declaration near the top of this file) so a new language generator is
# policed from its first commit, with no edit here.
SHARED_VOCABULARY_LANGUAGE_PACKAGES: tuple[str, ...] = LANGUAGE_PACKAGES


def _import_shared_enums_module() -> ModuleType:
    """Import and return ``datrix_codegen_common.enums``, the single module
    every G1 canonical-source harvest function (Enum and non-Enum alike)
    reads live at scan time -- never a hardcoded mirror of its content.

    Returns:
        The imported ``datrix_codegen_common.enums`` module object.

    Raises:
        RuntimeError: if the module cannot be imported (the shared
            vocabulary layer is not installed in the active venv).
    """
    try:
        from datrix_codegen_common import enums as shared_enums
    except ImportError as exc:
        raise RuntimeError(
            "Failed to import datrix_codegen_common.enums -- the G1 "
            "shared-vocabulary ratchet requires datrix-codegen-common "
            "installed in the active environment (D:\\datrix\\.venv). Fix: "
            "run this script via check-import-boundaries.ps1, which "
            "activates the venv first."
        ) from exc
    return shared_enums


def _shared_enum_members() -> dict[str, dict[str, str]]:
    """Every ``str, Enum`` class declared in ``datrix_codegen_common.enums``,
    keyed by class name, mapped to ``{member_name: member_value}``.

    Read from the INSTALLED package at scan time -- never a hardcoded mirror
    of enums.py's content -- so an Enum vocabulary added there later is
    picked up with zero edit to this scanner. This covers ONLY the ``str,
    Enum`` half of the canonical source; ``_shared_non_enum_vocabularies``
    covers the plain dict/set/frozenset half (Decision D3's DSL exception-
    status map, the NoSQL unsupported-method map, and the derived
    log-builtin-method set are deliberately not Enums -- see that function).

    Returns:
        Mapping of enum class name -> {member name -> member value}.

    Raises:
        RuntimeError: if datrix_codegen_common.enums cannot be imported (the
            shared vocabulary layer is not installed in the active venv).
    """
    shared_enums = _import_shared_enums_module()

    members: dict[str, dict[str, str]] = {}
    for name, candidate in vars(shared_enums).items():
        if (
            isinstance(candidate, type)
            and issubclass(candidate, enum.Enum)
            and candidate is not enum.Enum
        ):
            members[name] = {item.name: str(item.value) for item in candidate}
    return members


# AST call-target names recognized as wrapping a set/frozenset display when
# deciding whether a module-level assignment in enums.py is a container
# constant (see ``_is_module_level_container_assignment``).
_VOCABULARY_CONTAINER_CALL_NAMES: frozenset[str] = frozenset({"frozenset", "set"})


def _is_module_level_container_assignment(stmt: ast.stmt) -> str | None:
    """Return the assigned name if *stmt* is a module-level ``Assign``/
    ``AnnAssign`` to a single bare ``Name`` whose right-hand side is a dict
    display, a set display, or a ``frozenset(...)``/``set(...)`` call --
    else ``None``.

    This is a SHAPE test only (does this statement declare a container
    constant?), never a name test -- no vocabulary name is ever hardcoded
    here, so a new dict/set/frozenset constant added to ``enums.py`` later
    is picked up with zero edit to this scanner, mirroring
    ``_shared_enum_members``'s "read live, never mirrored" property for the
    Enum half. The RHS's own inner shape is deliberately not inspected any
    further here (a ``frozenset(...)`` call's argument may be a literal
    display or a generator expression -- e.g. ``LOG_BUILTIN_METHODS`` -- both
    count as "container-shaped"; the actual member VALUES always come from
    the live imported object in ``_non_enum_vocabulary_member_set``, never
    from re-parsing this argument).

    Args:
        stmt: A top-level statement from ``enums.py``'s module body.

    Returns:
        The assigned identifier, or ``None`` if *stmt* is not a qualifying
        module-level container assignment.
    """
    if isinstance(stmt, ast.Assign):
        if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
            return None
        name_node = stmt.targets[0]
        value_node = stmt.value
    elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
        if not isinstance(stmt.target, ast.Name):
            return None
        name_node = stmt.target
        value_node = stmt.value
    else:
        return None

    if isinstance(value_node, (ast.Dict, ast.Set)):
        return name_node.id
    if (
        isinstance(value_node, ast.Call)
        and isinstance(value_node.func, ast.Name)
        and value_node.func.id in _VOCABULARY_CONTAINER_CALL_NAMES
    ):
        return name_node.id
    return None


def _non_enum_vocabulary_member_set(name: str, runtime_value: object) -> frozenset[str]:
    """Resolve *runtime_value* (the live object bound to *name* in the
    imported ``enums.py``) to its canonical member-value set.

    A ``dict``'s canonical member set is its KEYS -- that is what a
    redeclaring copy duplicates (e.g. ``DSL_EXCEPTION_HTTP_STATUS``'s keys,
    never its status-code values). A ``set``/``frozenset``'s canonical
    member set is its elements directly.

    Args:
        name: The module-level identifier this value is bound to (for error
            messages only).
        runtime_value: The actual object ``getattr(enums_module, name)``.

    Returns:
        The frozenset of canonical member strings.

    Raises:
        TypeError: if *runtime_value* is not a dict/set/frozenset, or any of
            its keys/elements is not a string. A canonical declaration whose
            members cannot be determined must fail loudly here, never be
            silently skipped -- a silently-skipped canonical source is the
            exact coverage gap this harvest exists to close.
    """
    if isinstance(runtime_value, dict):
        candidate_members = runtime_value.keys()
        shape = "dict keys"
    elif isinstance(runtime_value, (frozenset, set)):
        candidate_members = runtime_value
        shape = "set/frozenset elements"
    else:
        raise TypeError(
            f"G1 harvest: '{name}' in datrix_codegen_common.enums has a "
            f"module-level dict/set/frozenset assignment shape but its live "
            f"value is a {type(runtime_value).__name__}, not a dict/set/"
            f"frozenset. Expected the runtime type to match the declared "
            f"shape. Fix: keep '{name}' bound to a dict/set/frozenset, or "
            f"restructure it so it is no longer a bare module-level "
            f"assignment (e.g. move it behind a function)."
        )

    members: set[str] = set()
    for element in candidate_members:
        if not isinstance(element, str):
            raise TypeError(
                f"G1 harvest: '{name}' in datrix_codegen_common.enums has a "
                f"non-string member ({element!r}, type "
                f"{type(element).__name__}) among its {shape}. Expected "
                f"every member to be a str so it can be compared against a "
                f"redeclaring copy's string literals. Fix: make '{name}' "
                f"string-keyed/valued, or valid options are to exclude it "
                f"from module-level container declarations in enums.py."
            )
        members.add(element)
    return frozenset(members)


def _shared_non_enum_vocabularies() -> dict[str, frozenset[str]]:
    """Every module-level ``dict``/``set``/``frozenset`` constant DECLARED IN
    ``enums.py``'s own source (never an imported symbol merely visible
    through it, e.g. ``BUILTIN_REGISTRY``) that is not a ``str, Enum`` class,
    mapped to its canonical member-value set.

    Covers value-derived declarations the AST cannot evaluate on its own --
    e.g. ``LOG_BUILTIN_METHODS = frozenset(method for category, method in
    BUILTIN_REGISTRY if category == "Log")``, a generator expression, not a
    literal display. The AST is used ONLY to decide WHICH names are
    container-shaped constants (``_is_module_level_container_assignment``);
    the member set always comes from the live imported object, which
    already carries the fully-derived value regardless of how it was
    computed.

    No vocabulary name is ever hardcoded: a dict/set/frozenset constant
    added to ``enums.py`` later is harvested with zero edit here, the same
    generality property ``_shared_enum_members`` already has for the Enum
    half (Decision D3, Invariant I2; design principle 16 -- shared layers
    ask, target plugins answer).

    Returns:
        Mapping of module-level constant name -> canonical member-value set.

    Raises:
        RuntimeError: if datrix_codegen_common.enums cannot be imported, or
            if a name the AST identifies as a module-level assignment is
            missing from the imported module (source/installed-package
            mismatch).
        TypeError: if a qualifying container's members cannot be determined
            as strings (propagated from ``_non_enum_vocabulary_member_set``).
    """
    shared_enums = _import_shared_enums_module()
    source_path = Path(shared_enums.__file__)
    source_code = source_path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source_code, filename=str(source_path))

    vocabularies: dict[str, frozenset[str]] = {}
    for stmt in tree.body:
        name = _is_module_level_container_assignment(stmt)
        if name is None:
            continue
        if not hasattr(shared_enums, name):
            raise RuntimeError(
                f"G1 harvest: '{name}' is assigned at module level in "
                f"{source_path} but is not an attribute of the imported "
                f"datrix_codegen_common.enums module. Expected the source "
                f"file and the installed package to agree. Fix: reinstall "
                f"datrix-codegen-common in the active environment (D:\\"
                f"datrix\\.venv)."
            )
        runtime_value = getattr(shared_enums, name)
        vocabularies[name] = _non_enum_vocabulary_member_set(name, runtime_value)
    return vocabularies


@dataclass(frozen=True)
class SharedVocabularyHit:
    """One module-level container in a language package whose normalized
    member set duplicates a datrix_codegen_common.enums vocabulary -- an
    Enum class's value set or a plain module-level dict/set/frozenset's
    key/element set alike."""

    file_path: Path
    line_number: int
    container_name: str
    matched_vocabulary: str


def _resolve_vocabulary_element(
    node: ast.AST, enum_members: dict[str, dict[str, str]]
) -> tuple[str, bool] | None:
    """Resolve one set/frozenset/dict-key element to ``(value, is_bare)``.

    ``is_bare`` is True for a plain string constant (``"all"``), False for a
    qualified enum-member reference (``QueryTerminal.ALL``) resolved through
    *enum_members* to the member's real value (``"all"``) -- both forms
    compare equal once resolved, but only the bare form counts toward
    "hardcodes the literal" (see ``_normalize_container`` docstring).

    Returns:
        ``None`` for any other node shape (a Name, an f-string, a call, an
        ``EnumClass.MEMBER`` pair the enum does not actually declare, ...) --
        such an element means the container is not a closed vocabulary
        literal at all, and the caller skips it entirely.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value, True
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        member_map = enum_members.get(node.value.id)
        if member_map is not None and node.attr in member_map:
            return member_map[node.attr], False
    return None


@dataclass(frozen=True)
class _NormalizedContainer:
    """A module-level container literal, resolved to its member value set."""

    values: frozenset[str]
    has_bare_literal: bool


def _normalize_container(
    node: ast.AST, enum_members: dict[str, dict[str, str]]
) -> "_NormalizedContainer | None":
    """Normalize a module-level ``frozenset(...)``/``set(...)``/``{...}``/
    dict-literal RHS to its member value set, resolving both bare string
    literals and qualified ``EnumClass.MEMBER`` references to the same
    underlying strings so the two forms compare equal (see
    ``_resolve_vocabulary_element``).

    Returns:
        ``None`` if *node* is not a recognized set/frozenset/dict literal,
        has zero elements, or contains any element that is not a bare string
        or a resolvable qualified enum-member reference -- an unrecognized
        element means "not provably a closed vocabulary literal", not
        "clean"; the caller simply cannot compare a partially-unresolvable
        container against a specific enum's exact member set.
    """
    elements: list[ast.AST]
    if isinstance(node, ast.Call):
        func = node.func
        if not (isinstance(func, ast.Name) and func.id in ("frozenset", "set")):
            return None
        if len(node.args) != 1 or not isinstance(
            node.args[0], (ast.Set, ast.List, ast.Tuple)
        ):
            return None
        elements = list(node.args[0].elts)
    elif isinstance(node, ast.Set):
        elements = list(node.elts)
    elif isinstance(node, ast.Dict):
        if any(key is None for key in node.keys):
            return None  # a **spread entry -- not a closed literal
        elements = [key for key in node.keys if key is not None]
    else:
        return None

    if not elements:
        return None

    values: set[str] = set()
    has_bare_literal = False
    for element in elements:
        resolved = _resolve_vocabulary_element(element, enum_members)
        if resolved is None:
            return None
        value, is_bare = resolved
        values.add(value)
        has_bare_literal = has_bare_literal or is_bare

    return _NormalizedContainer(
        values=frozenset(values), has_bare_literal=has_bare_literal
    )


def scan_file_for_shared_vocabulary(
    file_path: Path,
    enum_members: dict[str, dict[str, str]],
    non_enum_vocabularies: dict[str, frozenset[str]],
) -> list[SharedVocabularyHit]:
    """AST-walk *file_path* for module-level set/frozenset/dict declarations
    whose normalized member set equals a ``datrix_codegen_common.enums``
    vocabulary's own value set (Decision D3, Invariant I2) -- an Enum
    class's value set, or a plain module-level dict's key set / set's
    frozenset's element set (``non_enum_vocabularies``) alike. G1's own
    specification never restricts the canonical side to Enum classes; a
    name -> value lookup table like ``DSL_EXCEPTION_HTTP_STATUS`` or a
    derived set like ``LOG_BUILTIN_METHODS`` is exactly as canonical as
    ``HTTPMethod``, and a bare-literal redeclaration of either is the same
    defect.

    A hit requires TWO conditions: the normalized member set exactly equals
    some enum class's value set, AND the container includes at least one
    BARE STRING LITERAL element. A container built ENTIRELY from qualified
    enum-member references (e.g. ``frozenset({QueryTerminal.ALL,
    QueryTerminal.FIRST, QueryTerminal.FIRST_OR_FAIL, QueryTerminal.COUNT})``,
    the real, already-compliant case at
    ``datrix-codegen-python/.../_transpiler_query_builder.py:19-24``) is
    CONSUMING the enum, not hardcoding it, and must not be flagged -- only a
    container containing at least one hand-spelled string is "the DSL
    vocabulary re-scattered after being centralised" (design doc S2.3).

    Only module-level (top-of-file) ``Assign``/``AnnAssign`` statements are
    scanned -- a set built inside a function body is a local computation,
    never a closed-world vocabulary table.

    Args:
        file_path: Path to Python source file.
        enum_members: Output of ``_shared_enum_members()``.
        non_enum_vocabularies: Output of ``_shared_non_enum_vocabularies()``.

    Returns:
        List of hits found in the file, in source order.

    Raises:
        SyntaxError: propagated from ast.parse (caller decides how to report).
        OSError: propagated if the file cannot be read.
    """
    source_code = file_path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source_code, filename=str(file_path))

    canonical_value_sets: dict[str, frozenset[str]] = {
        class_name: frozenset(values.values())
        for class_name, values in enum_members.items()
    }
    canonical_value_sets.update(non_enum_vocabularies)

    hits: list[SharedVocabularyHit] = []
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign):
            targets = stmt.targets
            value_node = stmt.value
        elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
            targets = [stmt.target]
            value_node = stmt.value
        else:
            continue

        normalized = _normalize_container(value_node, enum_members)
        if normalized is None or not normalized.has_bare_literal:
            continue

        matched_vocabulary = next(
            (
                vocabulary_name
                for vocabulary_name, value_set in canonical_value_sets.items()
                if value_set == normalized.values
            ),
            None,
        )
        if matched_vocabulary is None:
            continue

        container_name = ", ".join(
            target.id for target in targets if isinstance(target, ast.Name)
        )
        hits.append(
            SharedVocabularyHit(
                file_path=file_path,
                line_number=stmt.lineno,
                container_name=container_name or "<unknown>",
                matched_vocabulary=matched_vocabulary,
            )
        )

    return hits


def scan_shared_vocabulary(
    packages: dict[str, PackageInfo],
    monorepo_root: Path,
) -> dict[Path, list[SharedVocabularyHit]]:
    """Scan every ``.py`` file under each of
    ``SHARED_VOCABULARY_LANGUAGE_PACKAGES``' ``src/`` tree for module-level
    vocabulary duplication against ``datrix_codegen_common.enums``.

    Args:
        packages: Package name -> PackageInfo, as returned by discover_packages().
        monorepo_root: Monorepo root for relative path reporting.

    Returns:
        Mapping of file path -> hits in that file (files with zero hits omitted).
    """
    results: dict[Path, list[SharedVocabularyHit]] = {}
    enum_members = _shared_enum_members()
    non_enum_vocabularies = _shared_non_enum_vocabularies()

    for package_name in SHARED_VOCABULARY_LANGUAGE_PACKAGES:
        package_info = packages.get(package_name)
        if package_info is None:
            continue

        for py_file in package_info.src_dir.rglob("*.py"):
            try:
                hits = scan_file_for_shared_vocabulary(
                    py_file, enum_members, non_enum_vocabularies
                )
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


def load_shared_vocabulary_baseline(baseline_path: Path) -> dict[str, int]:
    """Load ``{relative_file: frozen_count}`` from the shared-vocabulary
    baseline TOML.

    Args:
        baseline_path: Path to the shared-vocabulary baseline TOML file.

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
            import tomli as tomllib  # type: ignore[no-redef, import-not-found]
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


def write_shared_vocabulary_baseline(baseline_path: Path, counts: dict[str, int]) -> None:
    """Write ``counts`` to the shared-vocabulary baseline TOML as
    ``[[baseline]] file=... count=...`` entries, sorted by file for
    deterministic diffs.

    Args:
        baseline_path: Path to the shared-vocabulary baseline TOML file to write.
        counts: Mapping of relative file path (forward slashes) -> hit count.
    """
    header = (
        "# G1 Shared-Vocabulary Ratchet Baseline (Decision D3, Invariant I2)\n"
        "#\n"
        "# Frozen per-file counts of module-level frozenset/set/dict\n"
        "# declarations in the four datrix-codegen-{lang} packages whose\n"
        "# normalized member set duplicates a datrix_codegen_common.enums\n"
        "# vocabulary. Any INCREASE in a file's count fails\n"
        "# datrix/scripts/dev/check-import-boundaries.py --check-shared-vocabulary.\n"
        "# Decreases are always allowed and should be captured by re-running\n"
        "# with --update-baseline once a later change deletes a redundant\n"
        "# container (the terminal state is 0 for every entry here).\n"
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


def check_shared_vocabulary_ratchet(
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
                f"{file_rel}: shared-vocabulary count increased from baseline "
                f"{frozen} to {current}"
            )
    return messages


# ---------------------------------------------------------------------------
# G2 Shared-Layer Target-Name Ratchet (Decision D4, Invariant I3)
#
# The single shared-layer package this ratchet polices. `datrix_common` and
# `datrix_cli` are deliberately excluded (design §8): they hold platform
# config-schema models (AwsPlatformConfig, AzureCosmosConfig,
# DockerHealthcheckConfig, ...) whose relocation into the platform packages
# is a separate Decision-22-shaped question, and documented public API
# (PythonFileScope, TypeScriptFileScope -- both listed as canonical imports
# in datrix-common/docs/contributing/ai-agent-rules/canonical-imports.md),
# so renaming them would be a breaking change to a published surface. Kept
# as its own tuple (not reused from TARGET_LITERAL_SHARED_PACKAGES, whose
# three-package scope belongs to the I1 ratchet only) per this file's
# established one-tuple-per-ratchet precedent (see
# PROVIDER_LITERAL_SHARED_PACKAGES above).
SHARED_TARGET_NAME_PACKAGES: tuple[str, ...] = (
    "datrix_codegen_common",
)

# Registered-target identifier-segment call names this ratchet treats as a
# TYPE reference (the second argument names a class/type, not a value).
_TYPE_REFERENCE_CALL_NAMES: frozenset[str] = frozenset({"isinstance", "issubclass"})

_CAMEL_TO_SNAKE_RE1 = re.compile(r"(.)([A-Z][a-z]+)")
_CAMEL_TO_SNAKE_RE2 = re.compile(r"([a-z0-9])([A-Z])")


def _identifier_segments(identifier: str) -> tuple[str, ...]:
    """Tokenize *identifier* into lowercase segments, splitting on ``_`` and
    at camelCase word boundaries (``fooBar`` -> ``foo``, ``bar``;
    ``PythonStructFieldRow`` -> ``python``, ``struct``, ``field``, ``row``).
    """
    with_boundaries = _CAMEL_TO_SNAKE_RE1.sub(r"\1_\2", identifier)
    with_boundaries = _CAMEL_TO_SNAKE_RE2.sub(r"\1_\2", with_boundaries)
    return tuple(seg.lower() for seg in with_boundaries.split("_") if seg)


def _identifier_carries_target_name(
    identifier: str, target_names: frozenset[str]
) -> str | None:
    """Return the registered target name *identifier* carries as a segment
    (or a contiguous run of adjacent camelCase segments -- e.g.
    ``TypeScript`` tokenizes as ``type`` + ``script``, which must still
    match the single registered target name ``typescript``), or ``None`` if
    it carries none.

    Segment-EXACT matching (never bare substring) is deliberate: ``java``
    must never match inside a hypothetical ``javascript`` identifier (a
    single, unsplit segment, since it has no internal capital or
    underscore) -- only a genuine identifier segment, or an exact
    concatenation of adjacent segments, counts.

    Args:
        identifier: The identifier to test.
        target_names: Registered language names, lowercased
            (``registered_language_names()``).

    Returns:
        The matched target name, or ``None``.
    """
    segments = _identifier_segments(identifier)
    for start in range(len(segments)):
        for end in range(start + 1, len(segments) + 1):
            candidate = "".join(segments[start:end])
            if candidate in target_names:
                return candidate
    return None


def _identifiers_in_type_expression(node: ast.AST) -> list[tuple[str, int]]:
    """Every ``(identifier, line_number)`` pair reachable from *node* by
    walking ONLY the syntactic shapes a type expression / isinstance
    argument can take: a bare name, a dotted attribute (``mod.Name``), a
    ``X | Y`` union, a generic subscript (``Callable[..., X | Y]``,
    ``Union[X, Y]``), a tuple of names (the ``isinstance(x, (A, B))`` form),
    or a string forward-reference.

    Does NOT descend into a function/lambda body, a comprehension, or any
    other executable-statement context -- this is only ever called on an
    annotation / isinstance-argument / base-class / type-alias-value
    expression, which is what keeps an ordinary local variable (e.g.
    ``local_cache = {}`` inside a function body) out of scope entirely: it
    is never a type expression (see the module docstring for why this
    matters -- a bare local variable can coincidentally be named after a
    registered language, e.g. ``java = fetch_stat()``).
    """
    results: list[tuple[str, int]] = []
    stack: list[ast.AST] = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, ast.Name):
            results.append((current.id, current.lineno))
        elif isinstance(current, ast.Attribute):
            results.append((current.attr, current.lineno))
        elif isinstance(current, ast.BinOp) and isinstance(current.op, ast.BitOr):
            stack.extend([current.left, current.right])
        elif isinstance(current, ast.Subscript):
            stack.append(current.value)
            stack.append(current.slice)
        elif isinstance(current, (ast.Tuple, ast.List)):
            stack.extend(current.elts)
        elif isinstance(current, ast.Constant) and isinstance(current.value, str):
            results.append((current.value, current.lineno))
    return results


@dataclass(frozen=True)
class SharedTargetNameHit:
    """One shared-layer identifier carrying a registered target name as an
    identifier segment (Decision D4, Invariant I3)."""

    file_path: Path
    line_number: int
    identifier: str
    matched_target: str
    kind: Literal["class_def", "function_def", "field_or_alias", "type_reference"]


def _scoped_plain_assign_targets(tree: ast.Module) -> list[tuple[str, int]]:
    """Every ``(identifier, line_number)`` target of a plain (unannotated)
    ``ast.Assign`` statement declared at MODULE top level or immediate
    CLASS-BODY level -- never inside a function/method body.

    This is the scoped counterpart to the ``ast.AnnAssign`` handling in
    ``scan_file_for_shared_target_names``: an annotated declaration
    (``StructSliceBuilder: TypeAlias = ...``) is always a genuine module- or
    class-level declaration syntactically, but a PLAIN assignment
    (``PYTHON_BASE_IMAGE_DIR = "python-base"``) is syntactically identical
    to an ordinary function-local variable assignment -- the only thing
    that distinguishes a real module constant from
    ``def f(): python_helper = 1`` is WHERE the statement sits in the tree.
    Restricting to ``tree.body`` and each ``ClassDef.body`` (a SCOPED
    traversal, never a blanket ``ast.walk``) is what keeps a function-body
    assignment out of scope, exactly like the declaration/type-reference-only
    dispatch in ``scan_file_for_shared_target_names`` keeps a bare local
    variable out of scope.

    Args:
        tree: The parsed module AST.

    Returns:
        ``(identifier, line_number)`` pairs for every ``ast.Name`` target of
        a qualifying plain ``Assign`` statement.
    """
    targets: list[tuple[str, int]] = []
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign):
            targets.extend(
                (target.id, stmt.lineno)
                for target in stmt.targets
                if isinstance(target, ast.Name)
            )
        elif isinstance(stmt, ast.ClassDef):
            for class_stmt in stmt.body:
                if isinstance(class_stmt, ast.Assign):
                    targets.extend(
                        (target.id, class_stmt.lineno)
                        for target in class_stmt.targets
                        if isinstance(target, ast.Name)
                    )
    return targets


def scan_file_for_shared_target_names(
    file_path: Path, target_names: frozenset[str]
) -> list[SharedTargetNameHit]:
    """AST-walk *file_path* for shared-layer identifiers that carry a
    registered target name as an identifier segment: a class or
    function/method DEFINITION, a dataclass field or type alias declared at
    module or class-body level (either annotated, e.g. ``x: TypeAlias =
    ...``, or a plain assignment, e.g. ``PYTHON_BASE_IMAGE_DIR = "..."``), or
    a type reference (an ``isinstance()``/``issubclass()`` argument, a base
    class, a type annotation, or a type-alias union member).

    Deliberately scoped to DECLARATION and TYPE-REFERENCE positions only --
    never a bare local variable, function parameter, loop variable, or
    attribute READ inside a function body. A qualified attribute access
    (``some_obj.python_package``) is never emitted as its own hit kind: it is
    a READ of a field declared somewhere else -- G2's own contract is
    declarations "in datrix_codegen_common source", and counting a read as a
    declaration is a scanner false positive, not a genuine hit (confirmed by
    the residual-hit review: every attribute-access hit measured was a read
    of a ``datrix_common.paths.ServicePaths`` field, a package this design
    explicitly fences out of scope). A type expression's own attribute chain
    (``mod.Name`` in an annotation, base class, or ``isinstance`` argument)
    still resolves via ``_identifiers_in_type_expression`` and is still
    emitted as ``type_reference`` -- that is a genuine signal a plain
    attribute-access sweep would also have caught, so removing the blanket
    attribute-access kind loses no real coverage. See the module-level
    "vocabulary is datrix.languages only" note in this task's spec: an
    unscoped scan flagged 305 unrelated occurrences of the segment "local" in
    datrix-common/src alone, zero of them a target-named SURFACE -- part of
    why platforms are excluded from the vocabulary entirely. Restricting to
    declaration/type-reference positions catches every confirmed offender
    (the struct-slice dataclasses, the ``StructSliceBuilder`` union, the
    ``build_struct_context`` isinstance ladder,
    ``CqrsBusRegistration.import_line_python``, and the plain module-level
    constant ``PYTHON_BASE_IMAGE_DIR``) while leaving ordinary local code and
    reads of out-of-scope packages' fields untouched.

    Args:
        file_path: Path to Python source file.
        target_names: Registered language names (lowercased), from
            ``registered_language_names()``.

    Returns:
        List of hits found in the file, in AST-walk order.

    Raises:
        SyntaxError: propagated from ast.parse (caller decides how to report).
        OSError: propagated if the file cannot be read.
    """
    source_code = file_path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source_code, filename=str(file_path))

    hits: list[SharedTargetNameHit] = []

    def _emit(identifier: str, line_number: int, kind: str) -> None:
        matched = _identifier_carries_target_name(identifier, target_names)
        if matched is not None:
            hits.append(
                SharedTargetNameHit(
                    file_path=file_path,
                    line_number=line_number,
                    identifier=identifier,
                    matched_target=matched,
                    kind=kind,  # type: ignore[arg-type]
                )
            )

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            _emit(node.name, node.lineno, "class_def")
            for base in node.bases:
                for identifier, lineno in _identifiers_in_type_expression(base):
                    _emit(identifier, lineno, "type_reference")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _emit(node.name, node.lineno, "function_def")
            all_args = [
                *node.args.args,
                *node.args.kwonlyargs,
                node.args.vararg,
                node.args.kwarg,
            ]
            for arg in all_args:
                if arg is not None and arg.annotation is not None:
                    for identifier, lineno in _identifiers_in_type_expression(arg.annotation):
                        _emit(identifier, lineno, "type_reference")
            if node.returns is not None:
                for identifier, lineno in _identifiers_in_type_expression(node.returns):
                    _emit(identifier, lineno, "type_reference")
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            _emit(node.target.id, node.lineno, "field_or_alias")
            if node.value is not None:
                for identifier, lineno in _identifiers_in_type_expression(node.value):
                    _emit(identifier, lineno, "type_reference")
            for identifier, lineno in _identifiers_in_type_expression(node.annotation):
                _emit(identifier, lineno, "type_reference")
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in _TYPE_REFERENCE_CALL_NAMES:
                for call_arg in node.args[1:]:
                    for identifier, lineno in _identifiers_in_type_expression(call_arg):
                        _emit(identifier, lineno, "type_reference")

    for identifier, line_number in _scoped_plain_assign_targets(tree):
        _emit(identifier, line_number, "field_or_alias")

    return hits


def scan_shared_target_names(
    packages: dict[str, PackageInfo],
    monorepo_root: Path,
) -> dict[Path, list[SharedTargetNameHit]]:
    """Scan every ``.py`` file under each of ``SHARED_TARGET_NAME_PACKAGES``'
    ``src/`` tree for identifiers carrying a registered target-name segment.

    Args:
        packages: Package name -> PackageInfo, as returned by discover_packages().
        monorepo_root: Monorepo root for relative path reporting.

    Returns:
        Mapping of file path -> hits in that file (files with zero hits omitted).
    """
    results: dict[Path, list[SharedTargetNameHit]] = {}
    target_names = frozenset(name.lower() for name in registered_language_names())

    for package_name in SHARED_TARGET_NAME_PACKAGES:
        package_info = packages.get(package_name)
        if package_info is None:
            continue

        for py_file in package_info.src_dir.rglob("*.py"):
            try:
                hits = scan_file_for_shared_target_names(py_file, target_names)
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


def load_shared_target_name_baseline(baseline_path: Path) -> dict[str, int]:
    """Load ``{relative_file: frozen_count}`` from the shared-target-name
    baseline TOML. Returns an empty dict if the file does not exist yet."""
    if not baseline_path.exists():
        return {}

    try:
        import tomllib  # Python 3.11+
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef, import-not-found]
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


def write_shared_target_name_baseline(baseline_path: Path, counts: dict[str, int]) -> None:
    """Write ``counts`` to the shared-target-name baseline TOML as
    ``[[baseline]] file=... count=...`` entries, sorted by file."""
    header = (
        "# G2 Shared-Layer Target-Name Ratchet Baseline (Decision D4, Invariant I3)\n"
        "#\n"
        "# Frozen per-file counts of shared-layer identifiers (class, function,\n"
        "# dataclass field, type alias, or type reference) carrying a registered\n"
        "# language name as an identifier segment, in datrix_codegen_common.\n"
        "# Any INCREASE in a file's count fails\n"
        "# datrix/scripts/dev/check-import-boundaries.py --check-shared-target-names.\n"
        "# Decreases are always allowed and should be captured by re-running with\n"
        "# --update-baseline once a later change deletes a target-named surface.\n"
        "# The terminal state is a single reviewed exemption entry --\n"
        "# container_image_supply.py count 1, the scope-fenced PYTHON_BASE_IMAGE_DIR\n"
        "# (the shared per-system base-image directory name every platform emitter\n"
        "# must agree on byte-for-byte) -- every other entry drives to 0 as later\n"
        "# migration work removes each remaining target-named surface. The four\n"
        "# sql/nosql-substring identifiers considered during this ratchet's design\n"
        "# (sql_engine, sql_dialect, NoSQLSeedWriter, NoSqlFilterSyntax) are NOT hits\n"
        "# under this ratchet's languages-only vocabulary (sql is not a registered\n"
        "# datrix.languages entry) -- they are proven non-matches by this ratchet's\n"
        "# own self-test, not baseline entries.\n"
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


def check_shared_target_name_ratchet(
    current_counts: dict[str, int],
    baseline: dict[str, int],
) -> list[str]:
    """Compare *current_counts* against *baseline*; return one message per
    file whose count INCREASED (baseline missing == baseline 0). Never flags
    a decrease -- the ratchet only tightens."""
    messages: list[str] = []
    for file_rel in sorted(current_counts.keys()):
        current = current_counts[file_rel]
        frozen = baseline.get(file_rel, 0)
        if current > frozen:
            messages.append(
                f"{file_rel}: shared-target-name count increased from baseline "
                f"{frozen} to {current}"
            )
    return messages


# ---------------------------------------------------------------------------
# G3 Cross-Package Vocabulary Ratchet (Decision D2.1-D2.4, Property 2)
#
# Fails when a module-level set/frozenset/dict/tuple literal's normalized
# member set is declared -- with at least one bare string literal -- in TWO
# OR MORE DISTINCT datrix-* packages. Unlike G1 (source-keyed: "does this
# language package redeclare something datrix_codegen_common.enums
# declares?"), G3 is keyed on duplication ACROSS packages with no notion of
# a canonical source -- it catches a vocabulary hand-copied between two
# packages that have no shared enum to key off at all. Scope is every
# package discover_packages() finds (not just LANGUAGE_PACKAGES), since a
# cross-package duplicate can involve any two datrix-* packages, including
# a language package and a shared layer.
# ---------------------------------------------------------------------------


def _resolve_g3_vocabulary_element(node: ast.AST) -> tuple[str, bool] | None:
    """Resolve one set/frozenset/dict-key/tuple element to ``(value,
    is_bare)`` for G3's classification -- PURELY BY AST SHAPE, never by
    resolving a qualified reference's runtime value the way G1's
    ``_resolve_vocabulary_element`` does. G3 must never consult
    ``datrix_codegen_common.enums`` (that canonical-vocabulary comparison
    is G1's job; G3 compares packages against EACH OTHER); reusing G1's
    resolver -- which can only recognize a qualified ``EnumClass.MEMBER``
    reference when ``EnumClass`` happens to be harvested from
    ``datrix_codegen_common.enums`` -- would silently make every qualified
    reference to any OTHER enum (e.g. ``ChangeKind`` from
    ``datrix_common.migration.differ``, ``TracingProvider`` from
    ``datrix_common.config.observability.models``) unresolvable, which
    would drop the WHOLE container (not just exempt it) and could hide a
    genuinely duplicated bare-literal sibling in the same container.

    A qualified reference (``EnumClass.MEMBER``, i.e. ``ast.Attribute``
    whose value is a bare ``ast.Name``) is recognized by shape alone and
    treated as non-bare (``is_bare=False``) -- it is "consuming" a named
    fact, not hardcoding one, regardless of which module that name comes
    from. Its symbolic dotted form (``"EnumClass.MEMBER"``) stands in as
    its comparison value: this is exact for a container built ENTIRELY of
    qualified references (excluded via ``has_bare_literal`` regardless of
    what its value resolves to) and is a documented, deliberate
    approximation for the rare MIXED bare+qualified container, where it
    still correctly keeps the bare portion in scope for comparison instead
    of silently dropping the entire container.

    Returns:
        ``None`` for any other node shape (a Name, an f-string, a call,
        ...) -- such an element means the container is not a closed
        vocabulary literal at all, and the caller skips it entirely.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value, True
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        return f"{node.value.id}.{node.attr}", False
    return None


def _normalize_container_g3(node: ast.AST) -> "_NormalizedContainer | None":
    """Same contract as ``_normalize_container``, extended to recognize a
    bare module-level ``ast.Tuple`` RHS (``_X = ("a", "b")``, no
    ``frozenset()``/``set()`` wrapper) -- G1 never needed this shape; G3's
    own scope explicitly includes it ("set/frozenset/dict/tuple" literals).
    Per-element resolution uses ``_resolve_g3_vocabulary_element`` (shape-
    based, never consults ``datrix_codegen_common.enums``), so a qualified
    ``EnumClass.MEMBER`` element still counts as "consuming", not
    "declaring", exactly as it does for G1, and a partially-dynamic tuple
    (an element that is neither a bare string nor a qualified attribute
    reference) is still "not provably a closed vocabulary literal" and
    returns ``None``, the same as every other unrecognized shape.

    Returns:
        ``None`` if *node* is not a recognized set/frozenset/dict/tuple
        literal, has zero elements, or contains any element that is not a
        bare string or a qualified attribute reference.
    """
    elements: list[ast.AST]
    if isinstance(node, ast.Tuple):
        elements = list(node.elts)
    elif isinstance(node, ast.Call):
        func = node.func
        if not (isinstance(func, ast.Name) and func.id in ("frozenset", "set")):
            return None
        if len(node.args) != 1 or not isinstance(
            node.args[0], (ast.Set, ast.List, ast.Tuple)
        ):
            return None
        elements = list(node.args[0].elts)
    elif isinstance(node, ast.Set):
        elements = list(node.elts)
    elif isinstance(node, ast.Dict):
        if any(key is None for key in node.keys):
            return None  # a **spread entry -- not a closed literal
        elements = [key for key in node.keys if key is not None]
    else:
        return None

    if not elements:
        return None

    values: set[str] = set()
    has_bare_literal = False
    for element in elements:
        resolved = _resolve_g3_vocabulary_element(element)
        if resolved is None:
            return None
        value, is_bare = resolved
        values.add(value)
        has_bare_literal = has_bare_literal or is_bare

    return _NormalizedContainer(
        values=frozenset(values), has_bare_literal=has_bare_literal
    )


@dataclass(frozen=True)
class CrossPackageVocabularyHit:
    """One module-level container in ``file_path`` whose normalized member
    set is ALSO declared (identically, with at least one bare string
    literal) in at least one other datrix-* package."""

    file_path: Path
    line_number: int
    container_name: str
    matched_packages: frozenset[str]  # every OTHER package declaring the same set


@dataclass(frozen=True)
class _ModuleContainerDeclaration:
    """One module-level bare-literal container declaration found while
    scanning a single file -- an intermediate value used only to group
    declarations across packages by normalized member set; never returned
    to a caller outside this ratchet's own scan pipeline."""

    file_path: Path
    line_number: int
    container_name: str
    values: frozenset[str]


def _scan_file_for_module_containers(
    file_path: Path,
) -> list[_ModuleContainerDeclaration]:
    """AST-walk *file_path* for module-level ``Assign``/``AnnAssign``
    statements whose value is a bare-literal set/frozenset/dict/tuple
    container (``_normalize_container_g3``), returning one declaration per
    qualifying statement in source order. A container built entirely from
    qualified ``EnumClass.MEMBER`` references (no bare string literal) is
    excluded here -- the same ``has_bare_literal`` gate G1 uses -- since it
    is consumption, not declaration.

    Args:
        file_path: Path to Python source file.

    Returns:
        List of declarations found in the file, in source order.

    Raises:
        SyntaxError: propagated from ast.parse (caller decides how to report).
        OSError: propagated if the file cannot be read.
    """
    source_code = file_path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source_code, filename=str(file_path))

    declarations: list[_ModuleContainerDeclaration] = []
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign):
            targets = stmt.targets
            value_node = stmt.value
        elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
            targets = [stmt.target]
            value_node = stmt.value
        else:
            continue

        normalized = _normalize_container_g3(value_node)
        if normalized is None or not normalized.has_bare_literal:
            continue

        container_name = ", ".join(
            target.id for target in targets if isinstance(target, ast.Name)
        )
        declarations.append(
            _ModuleContainerDeclaration(
                file_path=file_path,
                line_number=stmt.lineno,
                container_name=container_name or "<unknown>",
                values=normalized.values,
            )
        )
    return declarations


def scan_cross_package_vocabulary(
    packages: dict[str, PackageInfo],
    monorepo_root: Path,
) -> dict[Path, list[CrossPackageVocabularyHit]]:
    """AST-walk EVERY discovered datrix-* package's src/ tree (not just
    LANGUAGE_PACKAGES) for module-level set/frozenset/dict/tuple literals;
    group by normalized member set across ALL packages; report one hit per
    (file, container) whose normalized set is also declared, with a bare
    string literal, in >=1 OTHER package. Applies the same qualified-
    reference exemption G1 does -- a container built entirely from
    qualified ``EnumClass.MEMBER`` references (no bare string literal) is
    consumption, not duplication, and is never flagged -- but classifies it
    PURELY BY AST SHAPE (``_resolve_g3_vocabulary_element``), never by
    resolving against ``datrix_codegen_common.enums`` the way G1's
    ``scan_file_for_shared_vocabulary`` does: that canonical-vocabulary
    comparison is G1's job, and G3 compares packages against each other
    directly, with no notion of a canonical source or which specific enum
    module a qualified reference happens to come from.

    The grouping key is the normalized member-value set's CONTENT, never
    the container's name or file path -- a re-spelled table under a
    different name is exactly the case this ratchet exists to catch. A
    value set declared twice within the SAME package (even across two
    files) is a different, already-tracked defect (G1/DRY, not G3) and is
    never counted here: a "group" only counts once it spans two or more
    DISTINCT packages.

    Args:
        packages: Package name -> PackageInfo, as returned by discover_packages().
        monorepo_root: Monorepo root for relative path reporting.

    Returns:
        Mapping of file path -> hits in that file (files with zero hits omitted).
    """
    declarations_by_package: dict[str, list[_ModuleContainerDeclaration]] = {}
    for package_name, package_info in sorted(packages.items()):
        package_declarations: list[_ModuleContainerDeclaration] = []
        for py_file in sorted(package_info.src_dir.rglob("*.py")):
            try:
                package_declarations.extend(
                    _scan_file_for_module_containers(py_file)
                )
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
        declarations_by_package[package_name] = package_declarations

    # Group by normalized value set -> the set of DISTINCT packages that
    # declare it with a bare literal.
    packages_by_value_set: dict[frozenset[str], set[str]] = {}
    for package_name, package_declarations in declarations_by_package.items():
        for declaration in package_declarations:
            packages_by_value_set.setdefault(declaration.values, set()).add(
                package_name
            )

    results: dict[Path, list[CrossPackageVocabularyHit]] = {}
    for package_name, package_declarations in declarations_by_package.items():
        for declaration in package_declarations:
            member_packages = packages_by_value_set[declaration.values]
            if len(member_packages) < 2:
                continue
            other_packages = frozenset(member_packages - {package_name})
            results.setdefault(declaration.file_path, []).append(
                CrossPackageVocabularyHit(
                    file_path=declaration.file_path,
                    line_number=declaration.line_number,
                    container_name=declaration.container_name,
                    matched_packages=other_packages,
                )
            )
    return results


def load_cross_package_vocabulary_baseline(baseline_path: Path) -> dict[str, int]:
    """Load ``{relative_file: frozen_count}`` from the cross-package-
    vocabulary baseline TOML.

    Args:
        baseline_path: Path to the cross-package-vocabulary baseline TOML file.

    Returns:
        An empty dict if the file does not exist yet.
    """
    if not baseline_path.exists():
        return {}

    try:
        import tomllib  # Python 3.11+
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef, import-not-found]
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


def write_cross_package_vocabulary_baseline(
    baseline_path: Path, counts: dict[str, int]
) -> None:
    """Write ``counts`` to the cross-package-vocabulary baseline TOML as
    ``[[baseline]] file=... count=...`` entries, sorted by file for
    deterministic diffs. Per-entry human-written D9 "keep forever" reasons
    are hand-added as comments directly above their ``[[baseline]]`` block
    after this function runs -- this function only (re)writes the header
    and the mechanical file/count entries, never a reason.

    Args:
        baseline_path: Path to the cross-package-vocabulary baseline TOML file to write.
        counts: Mapping of relative file path (forward slashes) -> hit count.
    """
    header = (
        "# G3 Cross-Package Vocabulary Ratchet Baseline (Decision D2.1-D2.4, Property 2)\n"
        "#\n"
        "# Frozen per-file counts of module-level set/frozenset/dict/tuple\n"
        "# declarations whose normalized member set is declared -- with a\n"
        "# bare string literal -- identically in two or more datrix-*\n"
        "# packages (every package discover_packages() finds, not only the\n"
        "# four language packages). Any INCREASE in a file's count fails\n"
        "# datrix/scripts/dev/check-import-boundaries.py\n"
        "# --check-cross-package-vocabulary. Decreases are always allowed\n"
        "# and should be captured by re-running with --update-baseline once\n"
        "# a later change deletes or hoists a redundant container.\n"
        "#\n"
        "# A handful of entries below are KNOWN-LEGITIMATE duplicates --\n"
        "# each carries a written reason directly above its [[baseline]]\n"
        "# entry (design decision D9) and must never be driven to zero; see\n"
        "# each comment for why. Every other entry drives to 0 as later\n"
        "# consolidation work removes the redundant copy.\n"
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


def check_cross_package_vocabulary_ratchet(
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
                f"{file_rel}: cross-package-vocabulary count increased from "
                f"baseline {frozen} to {current}"
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
    _step("Self-test 1/17: platform allowed/denied codegen-common subtrees")
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
            "datrix_codegen_common.algorithms.servicebus_naming",
            "datrix_codegen_common.algorithms.servicebus_lock_renewal",
            "datrix_codegen_common.algorithms.cqrs_projection_receivers",
            "datrix_codegen_common.generation.raise_site_guards",
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
        "datrix_codegen_common.algorithms.servicebus_lock_renewal",
        "datrix_codegen_common.algorithms.cqrs_projection_receivers",
        "datrix_codegen_common.generation.raise_site_guards",
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
        # The language-shaped half of the CQRS split. Its neutral sibling
        # ``algorithms.cqrs_projection_receivers`` is in allowed_cases above:
        # this pair is what proves the split bought something, rather than the
        # carve-out having quietly admitted the context-model surface too.
        "datrix_codegen_common.algorithms.cqrs",
        # Subtree matching is exact-or-child, so allowing
        # ``generation.raise_site_guards`` must NOT admit its siblings.
        "datrix_codegen_common.generation.service_predicates",
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
    _step("Self-test 2/17: dotted-boundary precision and carve-out non-leakage")
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
    _step("Self-test 3/17: SQL and Component boundary rule coverage")
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
    _step("Self-test 4/17: platform -> sibling-platform import prohibition")
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
        "Self-test 9/17: platform -> platform CLI mutation non-vacuity "
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


def _self_test_provider_literal_build_fixture_monorepo(tmp_root: Path) -> Path:
    """Build a minimal isolated monorepo: one datrix-codegen-python package
    with a module carrying NO provider-literal conditional, plus a baseline
    TOML freezing that file at count 0."""
    package_src = tmp_root / "datrix-codegen-python" / "src" / "datrix_codegen_python"
    package_src.mkdir(parents=True, exist_ok=True)
    (package_src / "__init__.py").write_text("", encoding="utf-8")

    module_path = package_src / "sample_backend.py"
    module_path.write_text(
        "def resolve(backend: str) -> bool:\n    return backend == 'elasticsearch'\n",
        encoding="utf-8",
    )

    config_dir = tmp_root / "datrix" / "scripts" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    baseline_path = config_dir / "provider-conditional-baseline.toml"
    baseline_path.write_text(
        "[[baseline]]\n"
        'file = "datrix-codegen-python/src/datrix_codegen_python/sample_backend.py"\n'
        "count = 0\n",
        encoding="utf-8",
    )
    return module_path


def _self_test_provider_literal_run_cli(
    tmp_root: Path,
) -> "subprocess.CompletedProcess[str]":
    """Invoke THIS script as a real subprocess against the isolated fixture."""
    return subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "--base-dir",
            str(tmp_root),
            "--check-provider-conditionals",
            "--skip-auto-self-test",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _self_test_provider_literal_cli_non_vacuity() -> bool:
    """End-to-end proof the D5 provider-literal ratchet actually FIRES.

    Plants a real ``== "azure"`` conditional in a real, isolated fixture
    monorepo whose baseline freezes the file at 0, proves the scanner exits 1
    and names the file plus the exact count delta, then reverts the mutation
    and proves the failure clears (exit 0). This is the manifest's required
    NEGATIVE acceptance proof ("a planted new `== \"azure\"` conditional in
    ANY language package fails the ratchet"), run against a synthetic fixture
    monorepo rather than the real committed baseline.
    """
    _step(
        "Self-test 10/17: provider-literal ratchet CLI mutation non-vacuity "
        '(plant a real == "azure" conditional, prove detection, prove it clears on revert)'
    )
    ok = True
    tmp_root = _SELF_TEST_SCRATCH_ROOT / f"provider-literal-cli-{uuid.uuid4().hex}"
    tmp_root.mkdir(parents=True, exist_ok=True)
    try:
        module_path = _self_test_provider_literal_build_fixture_monorepo(tmp_root)

        clean_result = _self_test_provider_literal_run_cli(tmp_root)
        ok &= _check(
            f"clean fixture (no provider literal) exits 0, got {clean_result.returncode}",
            clean_result.returncode == 0,
        )

        module_path.write_text(
            "def resolve(backend: str) -> bool:\n    return backend == 'azure'\n",
            encoding="utf-8",
        )
        failing_result = _self_test_provider_literal_run_cli(tmp_root)
        ok &= _check(
            f"planted '== \"azure\"' conditional exits 1, got {failing_result.returncode}",
            failing_result.returncode == 1,
        )
        ok &= _check(
            "failure output names the mutated file",
            "sample_backend.py" in failing_result.stdout,
        )
        ok &= _check(
            "failure output names the exact count delta (0 -> 1)",
            "increased from baseline 0 to 1" in failing_result.stdout,
        )

        module_path.write_text(
            "def resolve(backend: str) -> bool:\n    return backend == 'elasticsearch'\n",
            encoding="utf-8",
        )
        reverted_result = _self_test_provider_literal_run_cli(tmp_root)
        ok &= _check(
            f"reverting the mutation clears the failure, got exit {reverted_result.returncode}",
            reverted_result.returncode == 0,
        )
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    return ok


def _self_test_shared_package_provider_literal_build_fixture_monorepo(
    tmp_root: Path,
) -> Path:
    """Build a minimal isolated monorepo: one datrix-common package with a
    module carrying NO provider-literal conditional (clean shared-package
    fixture -- no baseline file needed, since the shared-package check has
    none)."""
    package_src = tmp_root / "datrix-common" / "src" / "datrix_common"
    package_src.mkdir(parents=True, exist_ok=True)
    (package_src / "__init__.py").write_text("", encoding="utf-8")

    module_path = package_src / "sample_orchestrator.py"
    module_path.write_text(
        "def resolve(backend: str) -> bool:\n    return backend == 'elasticsearch'\n",
        encoding="utf-8",
    )

    # The shared-package check has no baseline of its own, but it shares the
    # --check-provider-conditionals flag with the language-package ratchet,
    # which DOES require its baseline file to exist. This fixture monorepo
    # has no language package, so an empty (header-only) baseline is correct
    # -- it must merely exist, not carry any [[baseline]] entries.
    config_dir = tmp_root / "datrix" / "scripts" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "provider-conditional-baseline.toml").write_text(
        "# empty: no language package present in this fixture monorepo\n",
        encoding="utf-8",
    )
    return module_path


def _self_test_shared_package_provider_literal_cli_non_vacuity() -> bool:
    """End-to-end proof the shared-package zero-tolerance check actually FIRES.

    Plants a real ``== "azure"`` conditional in a SHARED package (datrix-common)
    in an isolated fixture monorepo carrying NO baseline entry for it (there
    is no baseline mechanism for shared packages at all), proves the scanner
    exits 1, then reverts and proves it clears. This is the manifest's
    required NEGATIVE acceptance proof for D6.1's shared-package half.
    """
    _step(
        "Self-test 11/17: shared-package provider-literal zero-tolerance CLI "
        'mutation non-vacuity (plant a real == "azure" conditional in '
        "datrix-common, prove detection, prove it clears on revert)"
    )
    ok = True
    tmp_root = _SELF_TEST_SCRATCH_ROOT / f"shared-provider-literal-{uuid.uuid4().hex}"
    tmp_root.mkdir(parents=True, exist_ok=True)
    try:
        module_path = _self_test_shared_package_provider_literal_build_fixture_monorepo(
            tmp_root
        )

        clean_result = _self_test_provider_literal_run_cli(tmp_root)
        ok &= _check(
            f"clean shared-package fixture exits 0, got {clean_result.returncode}",
            clean_result.returncode == 0,
        )

        module_path.write_text(
            "def resolve(backend: str) -> bool:\n    return backend == 'azure'\n",
            encoding="utf-8",
        )
        failing_result = _self_test_provider_literal_run_cli(tmp_root)
        ok &= _check(
            "planted shared-package '== \"azure\"' conditional exits 1, got "
            f"{failing_result.returncode}",
            failing_result.returncode == 1,
        )
        ok &= _check(
            "failure output names the mutated shared-package file",
            "sample_orchestrator.py" in failing_result.stdout,
        )
        ok &= _check(
            "failure output identifies it as a SHARED-package violation, not "
            "a baseline-ratchet message",
            "shared-package provider-literal" in failing_result.stdout,
        )

        module_path.write_text(
            "def resolve(backend: str) -> bool:\n    return backend == 'elasticsearch'\n",
            encoding="utf-8",
        )
        reverted_result = _self_test_provider_literal_run_cli(tmp_root)
        ok &= _check(
            f"reverting clears the failure, got exit {reverted_result.returncode}",
            reverted_result.returncode == 0,
        )
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    return ok


def _self_test_shared_vocabulary_scanner() -> bool:
    """scan_file_for_shared_vocabulary detects a bare-literal redeclaration
    of a known enum's member set, does NOT flag a container built entirely
    from qualified enum-member references, and does NOT flag an unrelated
    container whose members don't match any known vocabulary -- PLUS (added
    when the canonical-source harvest was widened past ``str, Enum``
    classes) the non-Enum harvest actually contains the three dict/frozenset
    canonical vocabularies, a harvest restricted to Enum classes alone would
    have missed every one of them, and each non-Enum shape's bare-literal
    redeclaration is detected while its importing form is not."""
    _step(
        "Self-test 12/17: shared-vocabulary scanner (detection + exemption "
        "non-vacuity, Enum and non-Enum canonical sources alike)"
    )
    ok = True

    enum_members = {
        "QueryTerminal": {
            "ALL": "all",
            "FIRST": "first",
            "FIRST_OR_FAIL": "firstOrFail",
            "COUNT": "count",
        },
    }

    scratch_dir = _SELF_TEST_SCRATCH_ROOT / f"shared-vocab-scanner-{uuid.uuid4().hex}"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    try:
        bare_literal_file = scratch_dir / "bare_literal.py"
        bare_literal_file.write_text(
            '_TERMINAL_METHODS = frozenset({"all", "first", "firstOrFail", "count"})\n',
            encoding="utf-8",
        )
        bare_hits = scan_file_for_shared_vocabulary(bare_literal_file, enum_members, {})
        ok &= _check(
            "bare-string redeclaration of QueryTerminal's four members is flagged",
            len(bare_hits) == 1 and bare_hits[0].matched_vocabulary == "QueryTerminal",
        )

        qualified_only_file = scratch_dir / "qualified_only.py"
        qualified_only_file.write_text(
            "from datrix_codegen_common.enums import QueryTerminal\n\n"
            "_QB_EXECUTE_TERMINALS = frozenset({\n"
            "    QueryTerminal.ALL,\n"
            "    QueryTerminal.FIRST,\n"
            "    QueryTerminal.FIRST_OR_FAIL,\n"
            "    QueryTerminal.COUNT,\n"
            "})\n",
            encoding="utf-8",
        )
        qualified_hits = scan_file_for_shared_vocabulary(
            qualified_only_file, enum_members, {}
        )
        ok &= _check(
            "a container built entirely from qualified QueryTerminal.X references is NOT flagged",
            qualified_hits == [],
        )

        unrelated_file = scratch_dir / "unrelated.py"
        unrelated_file.write_text(
            '_HTTP_STATUS_CATEGORIES = frozenset({"informational", "success", "error"})\n',
            encoding="utf-8",
        )
        unrelated_hits = scan_file_for_shared_vocabulary(unrelated_file, enum_members, {})
        ok &= _check(
            "an unrelated container matching no known vocabulary is NOT flagged",
            unrelated_hits == [],
        )

        # --- Non-Enum canonical-source harvest completeness -----------------
        # A harvest restricted to `str, Enum` classes (the pre-widening
        # behaviour) is what `_shared_enum_members()` alone still returns;
        # proving these three names are ABSENT from it, while the widened
        # `_shared_non_enum_vocabularies()` DOES contain them, is the direct
        # proof that an Enum-only harvest would FAIL to cover them.
        from datrix_codegen_common.enums import (
            DSL_EXCEPTION_HTTP_STATUS,
            LOG_BUILTIN_METHODS,
            NOSQL_UNSUPPORTED_METHODS,
        )

        enum_only_harvest = _shared_enum_members()
        non_enum_harvest = _shared_non_enum_vocabularies()
        for vocabulary_name in (
            "DSL_EXCEPTION_HTTP_STATUS",
            "NOSQL_UNSUPPORTED_METHODS",
            "LOG_BUILTIN_METHODS",
        ):
            ok &= _check(
                f"a str,Enum-only harvest does not contain {vocabulary_name} "
                f"(proves an Enum-only harvest FAILS to cover a non-Enum "
                f"canonical source)",
                vocabulary_name not in enum_only_harvest,
            )
        ok &= _check(
            "the widened harvest contains DSL_EXCEPTION_HTTP_STATUS's keys",
            non_enum_harvest.get("DSL_EXCEPTION_HTTP_STATUS")
            == frozenset(DSL_EXCEPTION_HTTP_STATUS.keys()),
        )
        ok &= _check(
            "the widened harvest contains NOSQL_UNSUPPORTED_METHODS's keys",
            non_enum_harvest.get("NOSQL_UNSUPPORTED_METHODS")
            == frozenset(NOSQL_UNSUPPORTED_METHODS.keys()),
        )
        ok &= _check(
            "the widened harvest contains LOG_BUILTIN_METHODS's members "
            "(value-derived from BUILTIN_REGISTRY, not a literal display)",
            non_enum_harvest.get("LOG_BUILTIN_METHODS")
            == frozenset(LOG_BUILTIN_METHODS),
        )

        # --- Non-Enum shape 1: dict-keys (DSL_EXCEPTION_HTTP_STATUS) --------
        dict_shape_bare_file = scratch_dir / "dict_shape_bare.py"
        dict_shape_bare_file.write_text(
            f"_EXCEPTION_STATUS_MAP = {DSL_EXCEPTION_HTTP_STATUS!r}\n",
            encoding="utf-8",
        )
        dict_shape_bare_hits = scan_file_for_shared_vocabulary(
            dict_shape_bare_file, {}, non_enum_harvest
        )
        ok &= _check(
            "a bare dict literal redeclaring DSL_EXCEPTION_HTTP_STATUS's keys is flagged",
            len(dict_shape_bare_hits) == 1
            and dict_shape_bare_hits[0].matched_vocabulary
            == "DSL_EXCEPTION_HTTP_STATUS",
        )

        dict_shape_importing_file = scratch_dir / "dict_shape_importing.py"
        dict_shape_importing_file.write_text(
            "from datrix_codegen_common.enums import DSL_EXCEPTION_HTTP_STATUS\n\n"
            "def status_for(exc_name: str) -> int:\n"
            "    return DSL_EXCEPTION_HTTP_STATUS[exc_name]\n",
            encoding="utf-8",
        )
        dict_shape_importing_hits = scan_file_for_shared_vocabulary(
            dict_shape_importing_file, {}, non_enum_harvest
        )
        ok &= _check(
            "importing DSL_EXCEPTION_HTTP_STATUS instead of redeclaring it is NOT flagged",
            dict_shape_importing_hits == [],
        )

        # --- Non-Enum shape 2: dict-keys (NOSQL_UNSUPPORTED_METHODS) --------
        second_dict_shape_bare_file = scratch_dir / "second_dict_shape_bare.py"
        second_dict_shape_bare_file.write_text(
            f"_NOSQL_UNSUPPORTED = {NOSQL_UNSUPPORTED_METHODS!r}\n",
            encoding="utf-8",
        )
        second_dict_shape_bare_hits = scan_file_for_shared_vocabulary(
            second_dict_shape_bare_file, {}, non_enum_harvest
        )
        ok &= _check(
            "a bare dict literal redeclaring NOSQL_UNSUPPORTED_METHODS's keys is flagged",
            len(second_dict_shape_bare_hits) == 1
            and second_dict_shape_bare_hits[0].matched_vocabulary
            == "NOSQL_UNSUPPORTED_METHODS",
        )

        second_dict_shape_importing_file = scratch_dir / "second_dict_shape_importing.py"
        second_dict_shape_importing_file.write_text(
            "from datrix_codegen_common.enums import NOSQL_UNSUPPORTED_METHODS\n\n"
            "def reason_for(method: str) -> str:\n"
            "    return NOSQL_UNSUPPORTED_METHODS[method]\n",
            encoding="utf-8",
        )
        second_dict_shape_importing_hits = scan_file_for_shared_vocabulary(
            second_dict_shape_importing_file, {}, non_enum_harvest
        )
        ok &= _check(
            "importing NOSQL_UNSUPPORTED_METHODS instead of redeclaring it is NOT flagged",
            second_dict_shape_importing_hits == [],
        )

        # --- Non-Enum shape 3: frozenset elements (LOG_BUILTIN_METHODS) -----
        frozenset_shape_bare_file = scratch_dir / "frozenset_shape_bare.py"
        frozenset_shape_bare_file.write_text(
            f"_LOG_METHODS = {frozenset(LOG_BUILTIN_METHODS)!r}\n",
            encoding="utf-8",
        )
        frozenset_shape_bare_hits = scan_file_for_shared_vocabulary(
            frozenset_shape_bare_file, {}, non_enum_harvest
        )
        ok &= _check(
            "a bare frozenset literal redeclaring LOG_BUILTIN_METHODS's members is flagged",
            len(frozenset_shape_bare_hits) == 1
            and frozenset_shape_bare_hits[0].matched_vocabulary == "LOG_BUILTIN_METHODS",
        )

        frozenset_shape_importing_file = scratch_dir / "frozenset_shape_importing.py"
        frozenset_shape_importing_file.write_text(
            "from datrix_codegen_common.enums import LOG_BUILTIN_METHODS\n\n"
            "def is_log_builtin(method: str) -> bool:\n"
            "    return method in LOG_BUILTIN_METHODS\n",
            encoding="utf-8",
        )
        frozenset_shape_importing_hits = scan_file_for_shared_vocabulary(
            frozenset_shape_importing_file, {}, non_enum_harvest
        )
        ok &= _check(
            "importing LOG_BUILTIN_METHODS instead of redeclaring it is NOT flagged",
            frozenset_shape_importing_hits == [],
        )
    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)

    return ok


def _self_test_shared_vocabulary_build_fixture_monorepo(tmp_root: Path) -> Path:
    """Build a minimal isolated monorepo: one datrix-codegen-python package
    whose module IMPORTS QueryTerminal (clean, no local redeclaration), plus
    a baseline TOML freezing that file at count 0."""
    package_src = tmp_root / "datrix-codegen-python" / "src" / "datrix_codegen_python"
    package_src.mkdir(parents=True, exist_ok=True)
    (package_src / "__init__.py").write_text("", encoding="utf-8")

    module_path = package_src / "sample_query_chain.py"
    module_path.write_text(
        "from datrix_codegen_common.enums import QueryTerminal\n\n"
        "def is_terminal(method: str) -> bool:\n"
        "    return method in {t.value for t in QueryTerminal}\n",
        encoding="utf-8",
    )

    config_dir = tmp_root / "datrix" / "scripts" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "shared-vocabulary-baseline.toml").write_text(
        "[[baseline]]\n"
        'file = "datrix-codegen-python/src/datrix_codegen_python/sample_query_chain.py"\n'
        "count = 0\n",
        encoding="utf-8",
    )
    return module_path


def _self_test_shared_vocabulary_run_cli(tmp_root: Path) -> "subprocess.CompletedProcess[str]":
    """Invoke THIS script as a real subprocess against the isolated fixture."""
    return subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "--base-dir",
            str(tmp_root),
            "--check-shared-vocabulary",
            "--skip-auto-self-test",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _self_test_shared_vocabulary_non_enum_cli_cycle(
    tmp_root: Path,
    module_path: Path,
    clean_source: str,
    *,
    vocabulary_name: str,
    container_name: str,
    literal_source: str,
) -> bool:
    """Run one mutate -> detect -> revert -> clear CLI round-trip for a
    single non-Enum canonical vocabulary against the already-clean fixture
    at *module_path*, restoring *clean_source* before returning either way.

    Args:
        tmp_root: The isolated fixture monorepo root (for CLI invocation).
        module_path: The fixture module file to mutate in place.
        clean_source: The known-clean source to append to / restore.
        vocabulary_name: The canonical vocabulary this cycle redeclares
            (for assertion messages only).
        container_name: The bare container's assigned name in the planted
            source line (e.g. ``_EXCEPTION_STATUS_MAP``).
        literal_source: The full ``name = <literal>`` statement to append.

    Returns:
        True iff every assertion in this cycle passed.
    """
    ok = True
    module_path.write_text(clean_source + "\n" + literal_source, encoding="utf-8")
    failing_result = _self_test_shared_vocabulary_run_cli(tmp_root)
    ok &= _check(
        f"redeclaring {vocabulary_name} as a bare {container_name} literal "
        f"exits 1, got {failing_result.returncode}",
        failing_result.returncode == 1,
    )
    ok &= _check(
        f"{vocabulary_name} redeclaration failure output names the mutated file",
        module_path.name in failing_result.stdout,
    )
    ok &= _check(
        f"{vocabulary_name} redeclaration failure output names the exact count delta (0 -> 1)",
        "increased from baseline 0 to 1" in failing_result.stdout,
    )

    module_path.write_text(clean_source, encoding="utf-8")
    reverted_result = _self_test_shared_vocabulary_run_cli(tmp_root)
    ok &= _check(
        f"reverting the {vocabulary_name} mutation clears the failure, "
        f"got exit {reverted_result.returncode}",
        reverted_result.returncode == 0,
    )
    return ok


def _self_test_shared_vocabulary_cli_non_vacuity() -> bool:
    """End-to-end proof the G1 shared-vocabulary ratchet actually FIRES --
    for the Enum-sourced case AND, added when the harvest was widened past
    ``str, Enum`` classes, for each of the three non-Enum canonical shapes.

    Starts from a fixture that IMPORTS QueryTerminal (the design's required
    POSITIVE case: exits 0), mutates it to ALSO bare-string-redeclare
    QueryTerminal's four members (the required NEGATIVE case: exits 1, names
    the file and the exact count delta), reverts and proves it clears, then
    repeats one mutate/detect/revert cycle per non-Enum vocabulary
    (``DSL_EXCEPTION_HTTP_STATUS`` and ``NOSQL_UNSUPPORTED_METHODS`` as bare
    dict literals redeclaring their keys, ``LOG_BUILTIN_METHODS`` as a bare
    frozenset literal redeclaring its members) against the SAME clean
    fixture file.
    """
    _step(
        "Self-test 13/17: shared-vocabulary ratchet CLI mutation non-vacuity "
        "(fixture importing QueryTerminal exits 0; redeclaring its four "
        "members as bare literals exits 1; reverting clears it -- plus one "
        "mutate/detect/revert cycle per non-Enum canonical vocabulary)"
    )
    ok = True
    tmp_root = _SELF_TEST_SCRATCH_ROOT / f"shared-vocab-cli-{uuid.uuid4().hex}"
    tmp_root.mkdir(parents=True, exist_ok=True)
    try:
        module_path = _self_test_shared_vocabulary_build_fixture_monorepo(tmp_root)
        clean_source = module_path.read_text(encoding="utf-8")

        clean_result = _self_test_shared_vocabulary_run_cli(tmp_root)
        ok &= _check(
            f"fixture importing QueryTerminal (no redeclaration) exits 0, got {clean_result.returncode}",
            clean_result.returncode == 0,
        )

        module_path.write_text(
            clean_source
            + '\n_TERMINAL_METHODS = frozenset({"all", "first", "firstOrFail", "count"})\n',
            encoding="utf-8",
        )
        failing_result = _self_test_shared_vocabulary_run_cli(tmp_root)
        ok &= _check(
            f"redeclaring QueryTerminal's four members as bare literals exits 1, got {failing_result.returncode}",
            failing_result.returncode == 1,
        )
        ok &= _check(
            "failure output names the mutated file",
            "sample_query_chain.py" in failing_result.stdout,
        )
        ok &= _check(
            "failure output names the exact count delta (0 -> 1)",
            "increased from baseline 0 to 1" in failing_result.stdout,
        )

        module_path.write_text(clean_source, encoding="utf-8")
        reverted_result = _self_test_shared_vocabulary_run_cli(tmp_root)
        ok &= _check(
            f"reverting the mutation clears the failure, got exit {reverted_result.returncode}",
            reverted_result.returncode == 0,
        )

        from datrix_codegen_common.enums import (
            DSL_EXCEPTION_HTTP_STATUS,
            LOG_BUILTIN_METHODS,
            NOSQL_UNSUPPORTED_METHODS,
        )

        ok &= _self_test_shared_vocabulary_non_enum_cli_cycle(
            tmp_root,
            module_path,
            clean_source,
            vocabulary_name="DSL_EXCEPTION_HTTP_STATUS",
            container_name="dict",
            literal_source=f"_EXCEPTION_STATUS_MAP = {DSL_EXCEPTION_HTTP_STATUS!r}\n",
        )
        ok &= _self_test_shared_vocabulary_non_enum_cli_cycle(
            tmp_root,
            module_path,
            clean_source,
            vocabulary_name="NOSQL_UNSUPPORTED_METHODS",
            container_name="dict",
            literal_source=f"_NOSQL_UNSUPPORTED = {NOSQL_UNSUPPORTED_METHODS!r}\n",
        )
        ok &= _self_test_shared_vocabulary_non_enum_cli_cycle(
            tmp_root,
            module_path,
            clean_source,
            vocabulary_name="LOG_BUILTIN_METHODS",
            container_name="frozenset",
            literal_source=f"_LOG_METHODS = {frozenset(LOG_BUILTIN_METHODS)!r}\n",
        )
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    return ok


def _self_test_shared_target_name_scanner() -> bool:
    """_identifier_carries_target_name detects a target-name segment
    (including a compound camelCase target like TypeScript across two
    adjacent segments), rejects a look-alike single-segment word (java vs.
    javascript) and every sql/nosql-substring look-alike named in the
    design, and the full scanner does not flag a bare local variable inside
    a function body but DOES detect a plain module-level constant via the
    scoped Assign path."""
    _step("Self-test 14/17: shared-target-name scanner (segment matching + non-flood proof)")
    ok = True

    target_names = frozenset({"python", "typescript", "java", "dotnet"})

    ok &= _check(
        "PythonStructFieldRow carries the segment 'python'",
        _identifier_carries_target_name("PythonStructFieldRow", target_names) == "python",
    )
    ok &= _check(
        "TypeScriptStructTemplateSlice carries 'typescript' across two adjacent camelCase segments",
        _identifier_carries_target_name("TypeScriptStructTemplateSlice", target_names) == "typescript",
    )
    ok &= _check(
        "import_line_python carries the segment 'python'",
        _identifier_carries_target_name("import_line_python", target_names) == "python",
    )
    ok &= _check(
        "a hypothetical 'javascript' identifier does NOT match 'java' (no bare-substring false positive)",
        _identifier_carries_target_name("javascript", target_names) is None,
    )
    ok &= _check(
        "a target-neutral name (FooSliceProtocol) matches nothing",
        _identifier_carries_target_name("FooSliceProtocol", target_names) is None,
    )

    # The design named these four sql/nosql-substring identifiers as
    # look-alikes: the substring denotes a database technology
    # (postgresql/mysql dialects, the NoSQL store category), "sql" is not a
    # registered datrix.languages entry, and widening this vocabulary to any
    # group containing "sql" must break these assertions loudly.
    for lookalike in ("sql_engine", "sql_dialect", "NoSQLSeedWriter", "NoSqlFilterSyntax"):
        ok &= _check(
            f"{lookalike!r} is NOT flagged ('sql' is not a registered language)",
            _identifier_carries_target_name(lookalike, target_names) is None,
        )

    scratch_dir = _SELF_TEST_SCRATCH_ROOT / f"shared-target-scanner-{uuid.uuid4().hex}"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    try:
        non_flood_file = scratch_dir / "non_flood.py"
        non_flood_file.write_text(
            "def resolve_something() -> dict[str, object]:\n"
            "    local_cache = {}\n"
            "    is_local = True\n"
            "    for local in range(3):\n"
            "        local_cache[local] = is_local\n"
            "    return local_cache\n",
            encoding="utf-8",
        )
        non_flood_hits = scan_file_for_shared_target_names(non_flood_file, target_names)
        ok &= _check(
            "bare local variables/loop variables named 'local'/'local_cache'/'is_local' "
            "inside a function body produce ZERO hits",
            non_flood_hits == [],
        )

        function_body_assign_file = scratch_dir / "function_body_assign.py"
        function_body_assign_file.write_text(
            "def f() -> None:\n    python_helper = 1\n    return None\n",
            encoding="utf-8",
        )
        function_body_assign_hits = scan_file_for_shared_target_names(
            function_body_assign_file, target_names
        )
        ok &= _check(
            "a plain assignment INSIDE a function body (python_helper = 1) is NOT "
            "flagged -- the scoped Assign path covers module/class level only",
            function_body_assign_hits == [],
        )

        declaration_file = scratch_dir / "declaration.py"
        declaration_file.write_text("class PythonFooSlice:\n    value: str\n", encoding="utf-8")
        declaration_hits = scan_file_for_shared_target_names(declaration_file, target_names)
        ok &= _check(
            "a class declaration carrying a target-name segment IS flagged",
            len(declaration_hits) >= 1
            and any(h.matched_target == "python" for h in declaration_hits),
        )

        module_constant_file = scratch_dir / "module_constant.py"
        module_constant_file.write_text(
            'PYTHON_BASE_IMAGE_DIR = "python-base"\n', encoding="utf-8"
        )
        module_constant_hits = scan_file_for_shared_target_names(
            module_constant_file, target_names
        )
        ok &= _check(
            "a plain MODULE-level constant (PYTHON_BASE_IMAGE_DIR) IS flagged via "
            "the scoped Assign path, matched_target == 'python'",
            len(module_constant_hits) == 1
            and module_constant_hits[0].matched_target == "python"
            and module_constant_hits[0].kind == "field_or_alias",
        )

        # Declaration-vs-read precision pair (D4 residual-hit review): a
        # module DECLARING a field named for a target must still be flagged
        # after attribute_access was dropped as a declaration kind, while a
        # module that only READS an identically-named attribute off some
        # other object -- e.g. datrix-common's own ``ServicePaths.python_package``
        # -- must NOT be, because a read is not a declaration under G2's own
        # contract. Both live in ONE file so a single AST walk exercises the
        # AnnAssign declaration path and the plain-Attribute read in the same
        # scan, proving the narrowing removed exactly the false-positive kind
        # and nothing else.
        declaration_vs_read_file = scratch_dir / "declaration_vs_read.py"
        declaration_vs_read_file.write_text(
            "python_package: str = 'shared_pkg'\n"
            "\n"
            "def describe(paths: object) -> str:\n"
            "    return paths.python_package\n",
            encoding="utf-8",
        )
        declaration_vs_read_hits = scan_file_for_shared_target_names(
            declaration_vs_read_file, target_names
        )
        ok &= _check(
            "a module-level DECLARATION named 'python_package' IS flagged "
            "(exactly once, via the scoped Assign path)",
            len(declaration_vs_read_hits) == 1
            and declaration_vs_read_hits[0].identifier == "python_package"
            and declaration_vs_read_hits[0].matched_target == "python"
            and declaration_vs_read_hits[0].kind == "field_or_alias",
        )

        read_only_file = scratch_dir / "read_only.py"
        read_only_file.write_text(
            "def describe(paths: object) -> str:\n"
            "    return paths.python_package\n",
            encoding="utf-8",
        )
        read_only_hits = scan_file_for_shared_target_names(read_only_file, target_names)
        ok &= _check(
            "a bare READ of 'some_obj.python_package' (no local declaration of "
            "that name) produces ZERO hits -- attribute_access was dropped as a "
            "declaration kind because a read is not a declaration",
            read_only_hits == [],
        )
    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)

    return ok


def _self_test_shared_target_name_build_fixture_monorepo(tmp_root: Path) -> Path:
    """Build a minimal isolated monorepo: one datrix-codegen-common package
    with a module declaring a target-NEUTRAL class, plus a baseline TOML
    freezing that file at count 0."""
    package_src = tmp_root / "datrix-codegen-common" / "src" / "datrix_codegen_common"
    package_src.mkdir(parents=True, exist_ok=True)
    (package_src / "__init__.py").write_text("", encoding="utf-8")

    module_path = package_src / "sample_slice.py"
    module_path.write_text(
        "class FooSliceProtocol:\n    value: str\n",
        encoding="utf-8",
    )

    config_dir = tmp_root / "datrix" / "scripts" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "shared-target-name-baseline.toml").write_text(
        "[[baseline]]\n"
        'file = "datrix-codegen-common/src/datrix_codegen_common/sample_slice.py"\n'
        "count = 0\n",
        encoding="utf-8",
    )
    return module_path


def _self_test_shared_target_name_run_cli(tmp_root: Path) -> "subprocess.CompletedProcess[str]":
    """Invoke THIS script as a real subprocess against the isolated fixture."""
    return subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "--base-dir",
            str(tmp_root),
            "--check-shared-target-names",
            "--skip-auto-self-test",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _self_test_shared_target_name_cli_non_vacuity() -> bool:
    """End-to-end proof the G2 shared-target-name ratchet actually FIRES.

    Starts from a fixture declaring a target-NEUTRAL class (the design's
    required POSITIVE case: exits 0), mutates it to a target-NAMED class
    (the required NEGATIVE case: exits 1, names the file), then reverts and
    proves it clears.
    """
    _step(
        "Self-test 15/17: shared-target-name ratchet CLI mutation non-vacuity "
        "('class PythonFooSlice' exits 1; 'class FooSliceProtocol' exits 0)"
    )
    ok = True
    tmp_root = _SELF_TEST_SCRATCH_ROOT / f"shared-target-cli-{uuid.uuid4().hex}"
    tmp_root.mkdir(parents=True, exist_ok=True)
    try:
        module_path = _self_test_shared_target_name_build_fixture_monorepo(tmp_root)
        clean_source = module_path.read_text(encoding="utf-8")

        clean_result = _self_test_shared_target_name_run_cli(tmp_root)
        ok &= _check(
            f"target-neutral fixture (FooSliceProtocol) exits 0, got {clean_result.returncode}",
            clean_result.returncode == 0,
        )

        module_path.write_text("class PythonFooSlice:\n    value: str\n", encoding="utf-8")
        failing_result = _self_test_shared_target_name_run_cli(tmp_root)
        ok &= _check(
            f"target-named fixture (PythonFooSlice) exits 1, got {failing_result.returncode}",
            failing_result.returncode == 1,
        )
        ok &= _check(
            "failure output names the mutated file",
            "sample_slice.py" in failing_result.stdout,
        )
        ok &= _check(
            "failure output names the exact count delta (0 -> 1)",
            "increased from baseline 0 to 1" in failing_result.stdout,
        )

        module_path.write_text(clean_source, encoding="utf-8")
        reverted_result = _self_test_shared_target_name_run_cli(tmp_root)
        ok &= _check(
            f"reverting the mutation clears the failure, got exit {reverted_result.returncode}",
            reverted_result.returncode == 0,
        )
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    return ok


def _self_test_provider_conditional_scanner() -> bool:
    """scan_file_for_provider_conditionals detects every known DI-5-deferred
    conditional shape (ProviderId-shaped, deployment-provider-value, match/case,
    and -- added by this task -- the two D5 provider-literal sub-patterns) and
    excludes every look-alike that must not ratchet."""
    _step("Self-test 5/17: provider-conditional AST scanner (detection + exclusion)")
    ok = True
    provider_ids = registered_platform_names()
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
        (
            "provider_literal_eq.py",
            "def f(backend):\n    if backend == 'azure':\n        return True\n"
            "    return False\n",
            1,
            "provider_literal_compare",
        ),
        (
            "provider_literal_container.py",
            "_ALWAYS_REQUIRES_CREDENTIALS: frozenset = frozenset({'azure'})\n\n"
            "def f(backend):\n    return backend in _ALWAYS_REQUIRES_CREDENTIALS\n",
            1,
            "provider_literal_container",
        ),
        (
            "provider_literal_inline_membership.py",
            "def f(provider_name):\n    return provider_name in ('aws', 'azure')\n",
            1,
            "provider_literal_container",
        ),
        (
            "non_provider_literal_excluded.py",
            "def f(discovery_type):\n    return discovery_type.lower() == 'consul'\n",
            0,
            "",
        ),
        (
            "provider_literal_in_log_excluded.py",
            "import logging\n\n_LOGGER = logging.getLogger(__name__)\n\n"
            "def f() -> None:\n    _LOGGER.info('azure backend selected')\n",
            0,
            "",
        ),
        (
            "provider_literal_in_docstring_excluded.py",
            'def f() -> None:\n    """Selects the azure backend when configured."""\n'
            "    return None\n",
            0,
            "",
        ),
        (
            "provider_literal_mixed_axis_excluded.py",
            "SUPPORTED_STORAGE_PROVIDERS: frozenset = frozenset(\n"
            "    {'s3', 'minio', 'azure_blob', 'local'}\n)\n",
            0,
            "",
        ),
    )
    try:
        for filename, source, expected_count, expected_kind in cases:
            file_path = scratch_dir / filename
            file_path.write_text(source, encoding="utf-8")
            hits = scan_file_for_provider_conditionals(file_path, provider_ids)
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
    _step("Self-test 6/17: function-level-import AST scanner")
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
    """All three ratchet comparators fire on any per-file increase, never on
    a decrease, and treat a baseline-absent file as baseline 0."""
    _step("Self-test 7/17: ratchet comparators (regression / no-regression / missing-baseline-as-zero)")
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

    shared_vocab_clean = check_shared_vocabulary_ratchet(
        {"datrix-codegen-python/src/datrix_codegen_python/foo.py": 2},
        {"datrix-codegen-python/src/datrix_codegen_python/foo.py": 2},
    )
    ok &= _check(
        "shared-vocabulary ratchet: clean when current == baseline", shared_vocab_clean == []
    )

    shared_vocab_increase = check_shared_vocabulary_ratchet(
        {"datrix-codegen-python/src/datrix_codegen_python/foo.py": 3},
        {"datrix-codegen-python/src/datrix_codegen_python/foo.py": 2},
    )
    ok &= _check(
        "shared-vocabulary ratchet: fires once on a real increase, naming file + delta",
        len(shared_vocab_increase) == 1
        and "foo.py" in shared_vocab_increase[0]
        and "increased from baseline 2 to 3" in shared_vocab_increase[0],
    )

    shared_vocab_decrease = check_shared_vocabulary_ratchet(
        {"datrix-codegen-python/src/datrix_codegen_python/foo.py": 1},
        {"datrix-codegen-python/src/datrix_codegen_python/foo.py": 5},
    )
    ok &= _check(
        "shared-vocabulary ratchet: allows a decrease", shared_vocab_decrease == []
    )

    shared_vocab_missing_baseline = check_shared_vocabulary_ratchet(
        {"datrix-codegen-python/src/datrix_codegen_python/new_file.py": 1}, {}
    )
    ok &= _check(
        "shared-vocabulary ratchet: a file absent from baseline is treated as baseline 0",
        len(shared_vocab_missing_baseline) == 1
        and "increased from baseline 0 to 1" in shared_vocab_missing_baseline[0],
    )

    shared_target_name_clean = check_shared_target_name_ratchet(
        {"datrix-codegen-common/src/datrix_codegen_common/foo.py": 2},
        {"datrix-codegen-common/src/datrix_codegen_common/foo.py": 2},
    )
    ok &= _check(
        "shared-target-name ratchet: clean when current == baseline",
        shared_target_name_clean == [],
    )

    shared_target_name_increase = check_shared_target_name_ratchet(
        {"datrix-codegen-common/src/datrix_codegen_common/foo.py": 3},
        {"datrix-codegen-common/src/datrix_codegen_common/foo.py": 2},
    )
    ok &= _check(
        "shared-target-name ratchet: fires once on a real increase, naming file + delta",
        len(shared_target_name_increase) == 1
        and "foo.py" in shared_target_name_increase[0]
        and "increased from baseline 2 to 3" in shared_target_name_increase[0],
    )

    shared_target_name_decrease = check_shared_target_name_ratchet(
        {"datrix-codegen-common/src/datrix_codegen_common/foo.py": 1},
        {"datrix-codegen-common/src/datrix_codegen_common/foo.py": 5},
    )
    ok &= _check(
        "shared-target-name ratchet: allows a decrease", shared_target_name_decrease == []
    )

    shared_target_name_missing_baseline = check_shared_target_name_ratchet(
        {"datrix-codegen-common/src/datrix_codegen_common/new_file.py": 1}, {}
    )
    ok &= _check(
        "shared-target-name ratchet: a file absent from baseline is treated as baseline 0",
        len(shared_target_name_missing_baseline) == 1
        and "increased from baseline 0 to 1" in shared_target_name_missing_baseline[0],
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
        "Self-test 8/17: function-level-import CLI mutation non-vacuity "
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


def _self_test_cross_package_vocabulary_scanner() -> bool:
    """scan_cross_package_vocabulary finds a normalized value-set duplicate
    across two real discovered packages, does NOT flag a set genuinely
    unique to one package, does NOT flag the same set declared twice within
    ONE package, does NOT flag a container built entirely from qualified
    EnumClass.MEMBER references, and DOES recognize a bare tuple literal as
    a candidate container shape."""
    _step(
        "Self-test 16/17: cross-package-vocabulary scanner (cross-package "
        "duplicate detection + same-package/qualified-enum/uniqueness "
        "exemptions + bare-tuple recognition)"
    )
    ok = True
    tmp_root = _SELF_TEST_SCRATCH_ROOT / f"cross-pkg-vocab-scanner-{uuid.uuid4().hex}"
    tmp_root.mkdir(parents=True, exist_ok=True)
    try:
        alpha_src = tmp_root / "datrix-codegen-alpha" / "src" / "datrix_codegen_alpha"
        beta_src = tmp_root / "datrix-codegen-beta" / "src" / "datrix_codegen_beta"
        alpha_src.mkdir(parents=True, exist_ok=True)
        beta_src.mkdir(parents=True, exist_ok=True)
        (alpha_src / "__init__.py").write_text("", encoding="utf-8")
        (beta_src / "__init__.py").write_text("", encoding="utf-8")

        # alpha.dup and beta.dup: genuine cross-package duplicate.
        (alpha_src / "dup.py").write_text(
            '_ALPHA_TERMINALS = ("all", "first", "count")\n', encoding="utf-8"
        )
        (beta_src / "dup.py").write_text(
            '_BETA_TERMINALS = ("all", "first", "count")\n', encoding="utf-8"
        )
        # alpha.unique: genuinely unique to alpha -- never flagged.
        (alpha_src / "unique.py").write_text(
            '_ALPHA_UNIQUE = frozenset({"only", "in", "alpha"})\n', encoding="utf-8"
        )
        # beta.same_package_twice_a / _b: same value set, twice, but both
        # declarations are in package beta -- not cross-package, never flagged.
        (beta_src / "same_package_twice_a.py").write_text(
            '_BETA_LOCAL_A = frozenset({"local", "only"})\n', encoding="utf-8"
        )
        (beta_src / "same_package_twice_b.py").write_text(
            '_BETA_LOCAL_B = frozenset({"local", "only"})\n', encoding="utf-8"
        )

        packages = discover_packages(tmp_root)
        hits = scan_cross_package_vocabulary(packages, tmp_root)

        alpha_dup_hits = hits.get(alpha_src / "dup.py", [])
        beta_dup_hits = hits.get(beta_src / "dup.py", [])
        ok &= _check(
            "a bare tuple literal duplicated across alpha and beta is flagged "
            "on both sides",
            len(alpha_dup_hits) == 1
            and len(beta_dup_hits) == 1
            and alpha_dup_hits[0].matched_packages == frozenset({"datrix_codegen_beta"})
            and beta_dup_hits[0].matched_packages == frozenset({"datrix_codegen_alpha"}),
        )

        ok &= _check(
            "a value set unique to one package is not flagged",
            (alpha_src / "unique.py") not in hits,
        )

        ok &= _check(
            "the same value set declared twice within ONE package is not "
            "cross-package and is not flagged",
            (beta_src / "same_package_twice_a.py") not in hits
            and (beta_src / "same_package_twice_b.py") not in hits,
        )

        # A container built entirely from qualified EnumClass.MEMBER
        # references must never be flagged, even when duplicated verbatim
        # across packages -- it is consumption, not declaration.
        (alpha_src / "qualified.py").write_text(
            "import enum\n\n"
            "class Sample(enum.Enum):\n"
            '    ALL = "all"\n'
            '    FIRST = "first"\n\n'
            "_ALPHA_QUALIFIED = frozenset({Sample.ALL, Sample.FIRST})\n",
            encoding="utf-8",
        )
        (beta_src / "qualified.py").write_text(
            "import enum\n\n"
            "class Sample(enum.Enum):\n"
            '    ALL = "all"\n'
            '    FIRST = "first"\n\n'
            "_BETA_QUALIFIED = frozenset({Sample.ALL, Sample.FIRST})\n",
            encoding="utf-8",
        )
        packages = discover_packages(tmp_root)
        hits_with_qualified = scan_cross_package_vocabulary(packages, tmp_root)
        ok &= _check(
            "a container built entirely from qualified EnumClass.MEMBER "
            "references is never flagged, even duplicated across packages",
            (alpha_src / "qualified.py") not in hits_with_qualified
            and (beta_src / "qualified.py") not in hits_with_qualified,
        )

        # A MIXED container (one bare literal + one qualified reference to
        # an enum from an ARBITRARY module -- not datrix_codegen_common.enums)
        # must still have its bare portion recognized: G3 classifies the
        # qualified element by AST SHAPE alone (never by resolving it
        # against datrix_codegen_common.enums), so an enum from any other
        # module must not silently make the whole container invisible.
        (alpha_src / "mixed.py").write_text(
            "import enum\n\n"
            "class OtherEnum(enum.Enum):\n"
            '    JAEGER = "jaeger"\n\n'
            '_ALPHA_MIXED = frozenset({OtherEnum.JAEGER, "otel"})\n',
            encoding="utf-8",
        )
        (beta_src / "mixed.py").write_text(
            "import enum\n\n"
            "class OtherEnum(enum.Enum):\n"
            '    JAEGER = "jaeger"\n\n'
            '_BETA_MIXED = frozenset({OtherEnum.JAEGER, "otel"})\n',
            encoding="utf-8",
        )
        packages = discover_packages(tmp_root)
        hits_with_mixed = scan_cross_package_vocabulary(packages, tmp_root)
        alpha_mixed_hits = hits_with_mixed.get(alpha_src / "mixed.py", [])
        beta_mixed_hits = hits_with_mixed.get(beta_src / "mixed.py", [])
        ok &= _check(
            "a MIXED bare+qualified container (qualified element from an "
            "enum outside datrix_codegen_common.enums) still has its bare "
            "portion recognized and flagged as a cross-package duplicate, "
            "not silently dropped",
            len(alpha_mixed_hits) == 1 and len(beta_mixed_hits) == 1,
        )
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    return ok


def _self_test_cross_package_vocabulary_build_fixture_monorepo(
    tmp_root: Path,
) -> tuple[Path, Path]:
    """Build a minimal isolated monorepo with TWO fixture packages
    (datrix-codegen-alpha, datrix-codegen-beta), neither importing anything
    from datrix_codegen_common.enums, and a baseline TOML freezing both
    files at count 0. Returns (alpha_module_path, beta_module_path)."""
    alpha_src = tmp_root / "datrix-codegen-alpha" / "src" / "datrix_codegen_alpha"
    beta_src = tmp_root / "datrix-codegen-beta" / "src" / "datrix_codegen_beta"
    alpha_src.mkdir(parents=True, exist_ok=True)
    beta_src.mkdir(parents=True, exist_ok=True)
    (alpha_src / "__init__.py").write_text("", encoding="utf-8")
    (beta_src / "__init__.py").write_text("", encoding="utf-8")

    alpha_module = alpha_src / "sample_alpha.py"
    beta_module = beta_src / "sample_beta.py"
    # Clean fixtures: each package declares its OWN, non-overlapping constant.
    alpha_module.write_text('_ALPHA_ONLY = frozenset({"a", "b"})\n', encoding="utf-8")
    beta_module.write_text('_BETA_ONLY = frozenset({"c", "d"})\n', encoding="utf-8")

    config_dir = tmp_root / "datrix" / "scripts" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "cross-package-vocabulary-baseline.toml").write_text(
        "[[baseline]]\n"
        'file = "datrix-codegen-alpha/src/datrix_codegen_alpha/sample_alpha.py"\n'
        "count = 0\n\n"
        "[[baseline]]\n"
        'file = "datrix-codegen-beta/src/datrix_codegen_beta/sample_beta.py"\n'
        "count = 0\n",
        encoding="utf-8",
    )
    return alpha_module, beta_module


def _self_test_cross_package_vocabulary_run_cli(
    tmp_root: Path,
) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "--base-dir",
            str(tmp_root),
            "--check-cross-package-vocabulary",
            "--skip-auto-self-test",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _self_test_cross_package_vocabulary_cli_non_vacuity() -> bool:
    """End-to-end proof the G3 ratchet actually FIRES: two clean,
    non-overlapping fixture packages exit 0; mutating beta to redeclare
    alpha's exact member set (a genuine cross-package duplicate) exits 1,
    names BOTH files, and reports the exact count delta; reverting clears
    it. Also proves a same-package (not cross-package) duplicate is NOT
    flagged by G3, and that a bare tuple literal is recognized (proven by
    the scanner-level self-test, ``_self_test_cross_package_vocabulary_scanner``,
    which this CLI proof complements with a real subprocess round-trip)."""
    _step(
        "Self-test 17/17: cross-package-vocabulary ratchet CLI mutation "
        "non-vacuity (two non-overlapping fixture packages exit 0; "
        "redeclaring alpha's set in beta exits 1; reverting clears it)"
    )
    ok = True
    tmp_root = _SELF_TEST_SCRATCH_ROOT / f"cross-pkg-vocab-cli-{uuid.uuid4().hex}"
    tmp_root.mkdir(parents=True, exist_ok=True)
    try:
        alpha_module, beta_module = _self_test_cross_package_vocabulary_build_fixture_monorepo(
            tmp_root
        )
        clean_beta_source = beta_module.read_text(encoding="utf-8")

        clean_result = _self_test_cross_package_vocabulary_run_cli(tmp_root)
        ok &= _check(
            f"two non-overlapping fixture packages exit 0, got {clean_result.returncode}",
            clean_result.returncode == 0,
        )

        # Cross-package duplicate: beta redeclares alpha's exact member set.
        beta_module.write_text(
            clean_beta_source + '\n_BETA_DUPLICATE = frozenset({"a", "b"})\n',
            encoding="utf-8",
        )
        failing_result = _self_test_cross_package_vocabulary_run_cli(tmp_root)
        ok &= _check(
            f"cross-package duplicate exits 1, got {failing_result.returncode}",
            failing_result.returncode == 1,
        )
        ok &= _check(
            "failure output names the beta file",
            beta_module.name in failing_result.stdout,
        )
        ok &= _check(
            "failure output names the exact count delta (0 -> 1)",
            "increased from baseline 0 to 1" in failing_result.stdout,
        )

        beta_module.write_text(clean_beta_source, encoding="utf-8")
        reverted_result = _self_test_cross_package_vocabulary_run_cli(tmp_root)
        ok &= _check(
            f"reverting clears the failure, got exit {reverted_result.returncode}",
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
        _self_test_provider_literal_cli_non_vacuity(),
        _self_test_shared_package_provider_literal_cli_non_vacuity(),
        _self_test_shared_vocabulary_scanner(),
        _self_test_shared_vocabulary_cli_non_vacuity(),
        _self_test_shared_target_name_scanner(),
        _self_test_shared_target_name_cli_non_vacuity(),
        _self_test_cross_package_vocabulary_scanner(),
        _self_test_cross_package_vocabulary_cli_non_vacuity(),
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
            "Run the I6 successor ratchet check (invariant I6, DI-4/DI-5) -- both the "
            "ProviderId-shaped pattern and the plain-string-literal pattern (D5) -- "
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
        "--check-shared-vocabulary",
        action="store_true",
        help=(
            "Run the G1 shared-vocabulary ratchet check (Decision D3, "
            "Invariant I2) in addition to the import-boundary check. Fails "
            "when a datrix-codegen-{lang} module declares a module-level "
            "frozenset/set/dict whose normalized member set duplicates a "
            "vocabulary already declared in datrix_codegen_common.enums."
        ),
    )
    parser.add_argument(
        "--check-shared-target-names",
        action="store_true",
        help=(
            "Run the G2 shared-layer target-name ratchet check (Decision D4, "
            "Invariant I3) in addition to the import-boundary check. Fails "
            "when a class, function, dataclass field, type alias, or type "
            "reference declared in datrix_codegen_common carries a "
            "registered LANGUAGE name (datrix.languages only, never "
            "datrix.platforms) as an identifier segment."
        ),
    )
    parser.add_argument(
        "--check-cross-package-vocabulary",
        action="store_true",
        help=(
            "Run the G3 cross-package vocabulary ratchet check (Decision "
            "D2.1-D2.4) in addition to the import-boundary check. Fails "
            "when a module-level set/frozenset/dict/tuple literal's "
            "normalized member set is declared, with a bare string "
            "literal, identically in two or more datrix-* packages -- "
            "every discovered package, not only the four language "
            "packages G1 scans -- independent of whether either copy "
            "also duplicates a datrix_codegen_common.enums vocabulary."
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
    # G1 shared-vocabulary ratchet (Decision D3, Invariant I2) — opt-in
    # via --check-shared-vocabulary.
    shared_vocabulary_baseline_path = (
        monorepo_root
        / "datrix"
        / "scripts"
        / "config"
        / "shared-vocabulary-baseline.toml"
    )
    # G2 shared-layer target-name ratchet (Decision D4, Invariant I3) — opt-in
    # via --check-shared-target-names.
    shared_target_name_baseline_path = (
        monorepo_root
        / "datrix"
        / "scripts"
        / "config"
        / "shared-target-name-baseline.toml"
    )
    # G3 cross-package vocabulary ratchet (Decision D2.1-D2.4) — opt-in via
    # --check-cross-package-vocabulary.
    cross_package_vocabulary_baseline_path = (
        monorepo_root
        / "datrix"
        / "scripts"
        / "config"
        / "cross-package-vocabulary-baseline.toml"
    )

    # D6.1 shared-package zero-tolerance check (distinct from the I6
    # language-package ratchet above) -- runs UNCONDITIONALLY whenever
    # --check-provider-conditionals is passed, in both --update-baseline and
    # normal-scan modes. It has no baseline file to seed or grandfather into,
    # so it is computed once here rather than inside either mode's branch.
    shared_package_provider_literal_messages: list[str] = []
    if args.check_provider_conditionals:
        shared_package_hits_by_file = scan_shared_package_provider_literals(
            packages, monorepo_root
        )
        shared_package_provider_literal_messages = check_shared_package_provider_literals(
            shared_package_hits_by_file, monorepo_root
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

        if args.check_shared_vocabulary:
            shared_vocabulary_hits_by_file = scan_shared_vocabulary(packages, monorepo_root)
            current_counts = {
                str(file_path.relative_to(monorepo_root)).replace("\\", "/"): len(hits)
                for file_path, hits in shared_vocabulary_hits_by_file.items()
            }
            write_shared_vocabulary_baseline(shared_vocabulary_baseline_path, current_counts)
            print(
                f"Updated G1 shared-vocabulary baseline: {len(current_counts)} file(s) "
                f"recorded at {shared_vocabulary_baseline_path.relative_to(monorepo_root)}"
            )
            updated_any = True

        if args.check_shared_target_names:
            shared_target_name_hits_by_file = scan_shared_target_names(
                packages, monorepo_root
            )
            current_counts = {
                str(file_path.relative_to(monorepo_root)).replace("\\", "/"): len(hits)
                for file_path, hits in shared_target_name_hits_by_file.items()
            }
            write_shared_target_name_baseline(shared_target_name_baseline_path, current_counts)
            print(
                f"Updated G2 shared-target-name baseline: {len(current_counts)} file(s) "
                f"recorded at {shared_target_name_baseline_path.relative_to(monorepo_root)}"
            )
            updated_any = True

        if args.check_cross_package_vocabulary:
            cross_package_vocabulary_hits_by_file = scan_cross_package_vocabulary(
                packages, monorepo_root
            )
            current_counts = {
                str(file_path.relative_to(monorepo_root)).replace("\\", "/"): len(hits)
                for file_path, hits in cross_package_vocabulary_hits_by_file.items()
            }
            write_cross_package_vocabulary_baseline(
                cross_package_vocabulary_baseline_path, current_counts
            )
            print(
                f"Updated G3 cross-package-vocabulary baseline: {len(current_counts)} "
                f"file(s) recorded at "
                f"{cross_package_vocabulary_baseline_path.relative_to(monorepo_root)}"
            )
            updated_any = True

        if args.check_target_literals or not (
            args.check_provider_conditionals
            or args.check_function_level_imports
            or args.check_shared_vocabulary
            or args.check_shared_target_names
            or args.check_cross_package_vocabulary
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

        if shared_package_provider_literal_messages:
            print(
                f"Error: shared-package provider-literal zero-tolerance check failed "
                f"for {len(shared_package_provider_literal_messages)} occurrence(s) -- "
                "these packages have no baseline to update; fix the code instead:\n"
            )
            for message in shared_package_provider_literal_messages:
                print(message)
            print()
            return 1

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

    shared_vocabulary_messages: list[str] = []
    if args.check_shared_vocabulary:
        if not shared_vocabulary_baseline_path.exists():
            print(
                f"Error: G1 shared-vocabulary baseline not found at "
                f"{shared_vocabulary_baseline_path}. Run "
                f"'check-import-boundaries.py --check-shared-vocabulary --update-baseline' "
                f"first to freeze the initial baseline.",
                file=sys.stderr,
            )
            return 2

        baseline = load_shared_vocabulary_baseline(shared_vocabulary_baseline_path)
        shared_vocabulary_hits_by_file = scan_shared_vocabulary(packages, monorepo_root)
        current_counts = {
            str(file_path.relative_to(monorepo_root)).replace("\\", "/"): len(hits)
            for file_path, hits in shared_vocabulary_hits_by_file.items()
        }
        shared_vocabulary_messages = check_shared_vocabulary_ratchet(
            current_counts, baseline
        )

    shared_target_name_messages: list[str] = []
    if args.check_shared_target_names:
        if not shared_target_name_baseline_path.exists():
            print(
                f"Error: G2 shared-target-name baseline not found at "
                f"{shared_target_name_baseline_path}. Run "
                f"'check-import-boundaries.py --check-shared-target-names --update-baseline' "
                f"first to freeze the initial baseline.",
                file=sys.stderr,
            )
            return 2

        baseline = load_shared_target_name_baseline(shared_target_name_baseline_path)
        shared_target_name_hits_by_file = scan_shared_target_names(packages, monorepo_root)
        current_counts = {
            str(file_path.relative_to(monorepo_root)).replace("\\", "/"): len(hits)
            for file_path, hits in shared_target_name_hits_by_file.items()
        }
        shared_target_name_messages = check_shared_target_name_ratchet(
            current_counts, baseline
        )

    cross_package_vocabulary_messages: list[str] = []
    if args.check_cross_package_vocabulary:
        if not cross_package_vocabulary_baseline_path.exists():
            print(
                f"Error: G3 cross-package-vocabulary baseline not found at "
                f"{cross_package_vocabulary_baseline_path}. Run "
                f"'check-import-boundaries.py --check-cross-package-vocabulary "
                f"--update-baseline' first to freeze the initial baseline.",
                file=sys.stderr,
            )
            return 2

        baseline = load_cross_package_vocabulary_baseline(
            cross_package_vocabulary_baseline_path
        )
        cross_package_vocabulary_hits_by_file = scan_cross_package_vocabulary(
            packages, monorepo_root
        )
        current_counts = {
            str(file_path.relative_to(monorepo_root)).replace("\\", "/"): len(hits)
            for file_path, hits in cross_package_vocabulary_hits_by_file.items()
        }
        cross_package_vocabulary_messages = check_cross_package_vocabulary_ratchet(
            current_counts, baseline
        )

    # Report violations / ratchet failures
    if (
        non_allowlisted_violations
        or target_literal_messages
        or provider_conditional_messages
        or shared_package_provider_literal_messages
        or function_level_import_messages
        or shared_vocabulary_messages
        or shared_target_name_messages
        or cross_package_vocabulary_messages
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

        if shared_package_provider_literal_messages:
            print(
                f"{mode}: shared-package provider-literal zero-tolerance check "
                f"failed for {len(shared_package_provider_literal_messages)} "
                f"occurrence(s) (no baseline -- any hit fails):\n"
            )
            for message in shared_package_provider_literal_messages:
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

        if shared_vocabulary_messages:
            print(
                f"{mode}: G1 shared-vocabulary ratchet failed for "
                f"{len(shared_vocabulary_messages)} file(s):\n"
            )
            for message in shared_vocabulary_messages:
                print(message)
            print()

        if shared_target_name_messages:
            print(
                f"{mode}: G2 shared-target-name ratchet failed for "
                f"{len(shared_target_name_messages)} file(s):\n"
            )
            for message in shared_target_name_messages:
                print(message)
            print()

        if cross_package_vocabulary_messages:
            print(
                f"{mode}: G3 cross-package-vocabulary ratchet failed for "
                f"{len(cross_package_vocabulary_messages)} file(s):\n"
            )
            for message in cross_package_vocabulary_messages:
                print(message)
            print()

        if args.warn:
            return 0
        return 1

    # Clean
    if args.check_provider_conditionals:
        shared_package_list = ", ".join(PROVIDER_LITERAL_SHARED_PACKAGES)
        print(
            "Shared-package provider-literal zero-tolerance check: 0 hits "
            f"({shared_package_list})."
        )

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
        if args.check_shared_vocabulary:
            print(
                "No G1 shared-vocabulary ratchet regressions found.", file=sys.stderr
            )
        if args.check_shared_target_names:
            print(
                "No G2 shared-target-name ratchet regressions found.", file=sys.stderr
            )
        if args.check_cross_package_vocabulary:
            print(
                "No G3 cross-package-vocabulary ratchet regressions found.",
                file=sys.stderr,
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
