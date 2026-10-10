"""Documentation-realization parity gate (Decision 39, invariants I2 and I6).

Every registered ``datrix.languages`` target emits an authored ``///``
DSL comment onto its declared PUBLISHED documentation surface (an OpenAPI
operation summary/description, a schema field description, a doc-comment
block, ...) and a plain ``//`` comment onto its SOURCE-commentary surface
only. The gate is a hard zero: an unpopulated (construct kind, surface) cell
is a hole that fails the gate, naming the target, the construct kind and the
surface, and no exemption of any kind exists.

WHAT THIS GATE CHECKS -- SIX CONSTRUCT KINDS, TWO SURFACES EACH
-----------------------------------------------------------------
``endpoint``, ``entity``, ``field``, ``enum_value``, ``struct_field``,
``function``, each checked on its ``published`` surface (must carry the
``///`` text) and its ``source`` surface (must carry the ``//`` text, and
must NEVER carry it on the published surface -- the I2 leak guard).

Targets are discovered from the ``datrix.languages`` entry-point group at
runtime -- never a hardcoded language-name literal -- so a future ``datrix-codegen-<lang>`` package is covered with no
edit here. Fewer than two registered targets makes the comparison vacuous
and fails loud (exit 2).

GENERATION: THE REAL PIPELINE, NOT A HAND-BUILT CONTEXT
---------------------------------------------------------
Generates one small fixture project (module constants below) via
``datrix_cli.pipeline.generation.GenerationPipeline`` -- the exact code path
``datrix generate`` / ``generate.ps1`` runs -- once per registered target.
A hand-built ``Application``/``CodegenContext`` (``parse_fixture_with_semantics``
+ ``attach_default_configs`` + a package-private test context) is NOT the
generator: it skips ConfigDSL resolution, ``DeploymentPlan.resolve()``,
``build_runtime_bootstrap()``, the secret-backend policy, the companion
generators and the post-generation language hooks, and a previous repo gate
built that way drifted until it could not generate at all. Calling the
pipeline cannot drift.

ASSERTING ON GENERATED ARTIFACTS, NOT A RUNNING SERVICE
---------------------------------------------------------
The property under test is where each target puts the author's text, so
this gate asserts over the GENERATED SOURCE ARTIFACTS themselves -- no
generated project is built or started -- parsed structurally (never a
line-oriented regex over the whole file).

HOW A TARGET'S ARTIFACTS ARE READ BELONGS TO THE TARGET: each registered
language declares a ``LanguageConformanceProbes``
(``LanguagePlugin.conformance_probes``,
``datrix_codegen_kernel.parity.conformance_probes``) whose
``documentation_surfaces(generated_root, files)`` returns the published and
source-comment text of its own generated files, using the parser its own syntax
needs (a language with a native AST uses it; a C-family language uses the shared
structural lexer ``datrix_codegen_kernel.parity.c_family_source_scan``). The
extractors themselves are proven by the owning packages' tests; this gate
holds the fixture, the per-cell comparison and the coverage census, and NEVER
names a target -- its self-test proves that first
(``datrix_scripts.registered_targets.target_references_in_module``). A probe that finds
no documentation surface at all fails the run.

Each registered target's own package proves a real end-to-end document for
this feature: python asserts against a real FastAPI router's ``.openapi()``,
and typescript against a real ``tsc`` + ``SwaggerModule.createDocument()`` run
over an npm-installed dependency set. This gate is the repo-level
cross-target census over the generated artifacts.

Repo-level validation **script** (per the datrix showcase boundary -- no
pytest suite lives in datrix), following the runtime-discovery +
non-vacuity-self-test shape of ``block_realization_parity.py`` and
``pooled_cache_realization_gate.py``.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from pathlib import Path
from typing import Final

from datrix_codegen_kernel.parity.conformance_probes import (
    DocumentationSurfaces,
    EnumClassifierRender,
    EventEnvelopeCensus,
    LanguageConformanceProbes,
    ResponseBodyWireField,
    RouteWireContract,
    conformance_probes_of_language_plugin,
    language_conformance_probes,
)
from datrix_common.errors.plugin import PluginValidationError

from datrix_scripts.paths import SHOWCASE_DIR, WORKSPACE_DIR
from datrix_scripts.registered_targets import (
    registered_language_names,
    self_test_gate_names_no_target,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Roots
# ---------------------------------------------------------------------------
DATRIX_DIR: Final[Path] = SHOWCASE_DIR
WORKSPACE_ROOT: Final[Path] = WORKSPACE_DIR

#: Decrease-only ratchet for the coverage census (Decision 39 invariant 1's
#: second half): per target, how many of the fixture's ATTACHED comment runs
#: reach no generated artifact at all.
COVERAGE_BASELINE_PATH: Final[Path] = (
    DATRIX_DIR / "scripts" / "config" / "documentation-coverage-baseline.json"
)
#: Scratch root for the fixture project and its per-target generated output.
#: Never inside a package repo (repo-boundaries.md) -- cleared/rewritten on
#: every invocation.
SCRATCH_ROOT: Final[Path] = WORKSPACE_ROOT / ".tmp" / "documentation-realization-parity-gate"
#: Machine-readable census, written on every run (pass or fail).
REPORT_PATH: Final[Path] = (
    WORKSPACE_ROOT / ".tmp" / "documentation-realization-parity-gate-report.json"
)

_MIN_TARGETS: Final[int] = 2
_PROFILE: Final[str] = "test"

CONSTRUCT_KINDS: Final[tuple[str, ...]] = (
    "endpoint", "entity", "field", "enum_value", "struct_field", "function",
)
SURFACES: Final[tuple[str, ...]] = ("published", "source")

EXIT_OK: Final[int] = 0
EXIT_FAIL: Final[int] = 1
EXIT_VACUOUS: Final[int] = 2


# ---------------------------------------------------------------------------
# Fixture DSL -- neutral e-commerce domain (repo-boundaries.md customer-
# domain-isolation rule). One documented construct per kind, published
# (``///``) plus an ADJACENT source-channel (``//``) sibling, mirroring the
# shape every per-language realization task's own fixture already uses.
# ---------------------------------------------------------------------------

ENDPOINT_PUBLISHED_SUMMARY: Final[str] = "Cancels a pending product listing."
ENDPOINT_PUBLISHED_DESCRIPTION: Final[str] = (
    "Removes the product from the active storefront catalog."
)
ENDPOINT_SOURCE_NOTE: Final[str] = (
    "Internal note: this endpoint predates the public API contract review, "
    "kept out of the public docs deliberately."
)

ENTITY_PUBLISHED_TEXT: Final[str] = (
    "Represents a purchasable product listed in the storefront catalog."
)
ENTITY_SOURCE_NOTE: Final[str] = (
    "Internal migration note: legacy catalog import table, not for API consumers."
)

FIELD_PUBLISHED_TEXT: Final[str] = "The product's shopper-facing display name."
FIELD_SOURCE_NOTE: Final[str] = (
    "Internal buyer note: legacy SKU migrated from the old catalog, not for API consumers."
)

ENUM_VALUE_PUBLISHED_TEXT: Final[str] = (
    "Product is visible and purchasable in the storefront catalog."
)
ENUM_VALUE_SOURCE_NOTE: Final[str] = (
    "Internal ops flag: inventory reconciliation is in progress, not for API consumers."
)

STRUCT_FIELD_PUBLISHED_TEXT: Final[str] = (
    "Total number of units currently available for purchase."
)
STRUCT_FIELD_SOURCE_NOTE: Final[str] = (
    "Internal warehouse slot reference, not for API consumers."
)

FUNCTION_PUBLISHED_TEXT: Final[str] = (
    "Calculates the discounted price for a product given a percentage off."
)
FUNCTION_SOURCE_NOTE: Final[str] = (
    "Internal: records each discount calculation attempt for later audit "
    "reconciliation, not for API consumers."
)


def _all_marker_texts() -> tuple[str, ...]:
    """Every marker text the fixture DSL is expected to carry verbatim --
    the non-vacuity self-test's fixture-consistency check reads this."""
    return (
        ENDPOINT_PUBLISHED_SUMMARY, ENDPOINT_PUBLISHED_DESCRIPTION, ENDPOINT_SOURCE_NOTE,
        ENTITY_PUBLISHED_TEXT, ENTITY_SOURCE_NOTE,
        FIELD_PUBLISHED_TEXT, FIELD_SOURCE_NOTE,
        ENUM_VALUE_PUBLISHED_TEXT, ENUM_VALUE_SOURCE_NOTE,
        STRUCT_FIELD_PUBLISHED_TEXT, STRUCT_FIELD_SOURCE_NOTE,
        FUNCTION_PUBLISHED_TEXT, FUNCTION_SOURCE_NOTE,
    )


_SYSTEM_DTRX: Final[str] = """include 'catalog-service.dtrx';

system catalog.System('config/system.dcfg') : version('1.0.0') {
}
"""

_SERVICE_DTRX: Final[str] = f"""service catalog.CatalogService('config/catalog-service.dcfg') : version('1.0.0'), description('documentation realization parity fixture') {{

    discovery {{ }}

    enum ProductStatus {{
        /// {ENUM_VALUE_PUBLISHED_TEXT}
        Available,
        // {ENUM_VALUE_SOURCE_NOTE}
        Reconciling,
        Discontinued
    }}

    struct ProductAvailability {{
        /// {STRUCT_FIELD_PUBLISHED_TEXT}
        Int unitsInStock;
        // {STRUCT_FIELD_SOURCE_NOTE}
        String warehouseSlot;
    }}

    /// {FUNCTION_PUBLISHED_TEXT}
    fn calculateDiscountedPrice(Decimal price, Int percentOff) -> Decimal {{
        return price;
    }}

    // {FUNCTION_SOURCE_NOTE}
    fn logDiscountAttempt(UUID productId, Int percentOff) -> Boolean {{
        return true;
    }}

    rdbms catalogDb {{

        /// {ENTITY_PUBLISHED_TEXT}
        entity Product {{
            UUID id : primaryKey, server = uuid();
            /// {FIELD_PUBLISHED_TEXT}
            String(200) title;
            // {FIELD_SOURCE_NOTE}
            String(50) legacySku;
            ProductStatus status = ProductStatus.Available;
        }}

        // {ENTITY_SOURCE_NOTE}
        entity Category {{
            UUID id : primaryKey, server = uuid();
            String(100) name;
        }}

    }}

    rest_api CatalogAPI : basePath("/api/v1"), rdbms(catalogDb) {{

        /// {ENDPOINT_PUBLISHED_SUMMARY}
        ///
        /// {ENDPOINT_PUBLISHED_DESCRIPTION}
        @path('/:id/cancel')
        post(UUID id) : auth(public) -> catalogDb.Product {{
            let Decimal ignoredDiscount = calculateDiscountedPrice(10.0, 5);
            return catalogDb.Product.findOrFail(id);
        }}

        // {ENDPOINT_SOURCE_NOTE}
        @path('/:id/archive')
        post(UUID id) : auth(public) -> catalogDb.Product {{
            let Boolean ignoredLogged = logDiscountAttempt(id, 5);
            return catalogDb.Product.findOrFail(id);
        }}

        @path('/:id/availability')
        get(UUID id) : auth(public) -> ProductAvailability {{
            return {{ unitsInStock: 10, warehouseSlot: "A1" }};
        }}

    }}

}}
"""

_SYSTEM_DCFG: Final[str] = """config system catalog.System {
  base {
    migrations {
      enabled = false;
    }
    deployment {
      runtime = "docker-compose";
      provider = "local";
    }
    defaultTimeout = 30000;
    maxPageSize = 100;
    platforms {
      docker {
        kafka_default_retention_ms = 604800000;
        infra {
          defaultHealthcheck {
            interval = "10s";
            timeout = "10s";
            retries = 10;
            startPeriod = "30s";
          }
          elasticsearchHealthcheck {
            interval = "10s";
            timeout = "5s";
            retries = 5;
            startPeriod = "30s";
          }
          rabbitmqHealthcheck {
            interval = "10s";
            timeout = "15s";
            retries = 20;
            startPeriod = "60s";
          }
          kafkaHealthcheck {
            interval = "10s";
            timeout = "15s";
            retries = 20;
            startPeriod = "60s";
          }
          jobWorkerHealthcheck {
            interval = "30s";
            timeout = "10s";
            retries = 3;
            startPeriod = "40s";
          }
          observabilityHealthcheck {
            interval = "15s";
            timeout = "10s";
            retries = 5;
            startPeriod = "30s";
          }
          pgbouncer {
            maxClientConn = 200;
            defaultPoolSize = 20;
          }
          elasticsearch {
            heap = "512m";
          }
          initScript {
            maxRetries = 30;
            retryDelaySeconds = 2;
          }
          multiRdbmsStartPeriodSeconds = 120;
        }
      }
    }
    observability {
      metrics {
        provider = "prometheus";
        endpoint = "/metrics";
        includeDefault = true;
      }
      tracing {
        provider = "jaeger";
        samplingRate = 0.1;
      }
      logging {
        level = "info";
        format = "json";
        provider = "loki";
      }
      visualization {
        provider = "grafana";
      }
      alerting {
        provider = "alertmanager";
      }
    }
    configStore {
      engine = "file";
      flavor = "container";
      applicationName = "catalog-system";
      environment = "dev";
      profiles {
        settings {
          kind = "freeform";
          keys {
            Boolean debugMode : description("Enable debug mode.") = false;
          }
        }
      }
    }
  }

  profile test as "test" extends base {
    alias env = "TEST";
    alias resource = "test";
  }

  profile production as "prod" extends base {
    alias env = "PROD";
    alias resource = "prod";

    deployment {
      runtime = "docker-compose";
      provider = "local";
    }
    observability {
      tracing {
        endpoint = "http://jaeger:4317";
      }
    }
    region = "us-east-1";
  }
}
"""

_SERVICE_DCFG: Final[str] = """config service catalog.CatalogService {
  base {
    port = 8000;
    flavor = "compose";
    replicas = 1;
    resources {
      requests {
        cpu = "100m";
        memory = "256Mi";
      }
      limits {
        cpu = "500m";
        memory = "512Mi";
      }
    }
    healthCheck {
      path = "/health";
      initialDelay = "10s";
    }
    rdbms catalogDb {
      id = "1742242c-5aff-4f6b-9401-0825619ae2e6";
      engine = "postgres";
      flavor = "container";
      host = "localhost";
      port = 5432;
      database = "catalog_products";
      poolSize = 20;
      maxOverflow = 20;
      asyncDriver = "postgresql+asyncpg";
      syncDriver = "postgresql+psycopg2";
      healthCheckSql = "SELECT 1";
      dockerImage = "postgres:17-alpine";
      volumePath = "/var/lib/postgresql/data";
      defaultUser = "postgres";
    }
    registration {
      tags = ["api", "catalog", "v1"];
      meta = {};
      healthCheck {
        type = "http";
        path = "/health";
        interval = "10s";
      }
    }
    resilience {
      defaults {
        timeout = "10s";
        retry {
          maxAttempts = 2;
          backoff {
            type = "exponential";
            initial = "100ms";
            multiplier = 2;
          }
        }
      }
    }
    httpSecurity {
      allowedHosts = ["catalog-service.example.com", "localhost"];
      corsOrigins = ["https://app.example.com"];
      corsMethods = ["GET", "POST", "PATCH", "DELETE", "OPTIONS"];
      corsHeaders = ["Authorization", "Content-Type"];
    }
    cacheOps {
      ttlSeconds = 300;
      keyMaxLength = 100;
      redisPoolSize = 10;
    }
    queueOps {
      sqsPollWaitSeconds = 20;
      sqsMaxMessagesPerPoll = 10;
      servicebusMaxWaitSeconds = 5;
    }
    kafkaOps {
      consumerPollTimeoutMs = 1000;
      keepalivePollTimeoutMs = 1000;
      maxPollIntervalMs = 600000;
    }
    messagingOps {
      rabbitmqPrefetchCount = 10;
    }
    downloadOps {
      timeoutSeconds = 300;
      chunkSizeBytes = 65536;
      maxRetries = 3;
      retryDelaySeconds = 1.0;
      retryableStatusCodes = [429, 500, 502, 503, 504];
    }
    remoteConfigOps {
      consulTimeoutSeconds = 5.0;
      appconfigMinPollSeconds = 15;
    }
    rateLimitOps {
      windowSeconds = 60;
    }
    microserviceClientOps {
      timeoutSeconds = 300;
      circuitBreakerFailMax = 5;
      circuitBreakerResetSeconds = 30;
      bulkheadMaxConcurrent = 10;
      integrationConnectTimeoutMs = 1000;
      integrationReadTimeoutMs = 30000;
      mailgunTimeoutSeconds = 30;
    }
    retryBudgetOps {
      window = 100;
      ratio = 0.1;
    }
    outboxOps {
      flushBatchSize = 500;
    }
    serviceCredentialOps {
      tokenExpirySkewSeconds = 30;
    }
  }

  profile test as "test" extends base {
    alias env = "TEST";
    alias resource = "test";
  }

  profile development as "dev" extends base {
    alias env = "DEV";
    alias resource = "dev";
  }

  profile production as "prod" extends base {
    alias env = "PROD";
    alias resource = "prod";

    flavor = "ecs-fargate";
    replicas = 2;
    replace rdbms catalogDb {
      id = "1742242c-5aff-4f6b-9401-0825619ae2e6";
      engine = "postgres";
      flavor = "rds";
      host = "postgres.internal";
      database = "catalog_products";
      poolSize = 40;
      maxOverflow = 20;
      ssl = true;
      asyncDriver = "postgresql+asyncpg";
      syncDriver = "postgresql+psycopg2";
      healthCheckSql = "SELECT 1";
    }
    strategy {
      rolling {
        maxUnavailable = "25%";
      }
    }
  }
}
"""


def write_fixture(root: Path) -> Path:
    """Write the fixture project fresh under *root*. Returns the ``system.dtrx`` path."""
    if root.exists():
        shutil.rmtree(root)
    (root / "config").mkdir(parents=True)
    (root / "system.dtrx").write_text(_SYSTEM_DTRX, encoding="utf-8")
    (root / "catalog-service.dtrx").write_text(_SERVICE_DTRX, encoding="utf-8")
    (root / "config" / "system.dcfg").write_text(_SYSTEM_DCFG, encoding="utf-8")
    (root / "config" / "catalog-service.dcfg").write_text(_SERVICE_DCFG, encoding="utf-8")
    return root / "system.dtrx"


# ---------------------------------------------------------------------------
# Generation -- the real pipeline (see module docstring)
# ---------------------------------------------------------------------------

_language_plugins_registered = False


def _ensure_language_plugins_registered() -> None:
    """Register datrix-language's parser implementations, exactly as
    ``datrix_cli.main`` does at startup. Idempotent; called once lazily."""
    global _language_plugins_registered
    if _language_plugins_registered:
        return
    from datrix_language.registration import register_all

    register_all()
    _language_plugins_registered = True


def generate_for_target(system_dtrx: Path, output_dir: Path, target: str) -> list[Path]:
    """Generate the fixture for *target* via the real generation pipeline.

    Args:
        system_dtrx: Absolute path to the fixture's ``system.dtrx``.
        output_dir: Destination directory (created fresh).
        target: A registered ``datrix.languages`` entry-point name.

    Returns:
        Every file path the pipeline reports as written.

    Raises:
        RuntimeError: The pipeline reported failure.
    """
    from datrix_cli.generation.validation_level import ValidationLevel
    from datrix_cli.pipeline.contract import PipelineConfig
    from datrix_cli.pipeline.generation import GenerationPipeline
    from datrix_common.plugin.identity import LanguageId

    _ensure_language_plugins_registered()

    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    # ValidationLevel.FAST runs fix_imports + format_files but SKIPS
    # validate_files -- which is where a language's post-generation hook runs
    # its toolchain's build/compile step. The property under test is "the
    # target emits the right documentation into the right construct," not
    # "the target's toolchain can restore/build/compile it", so a toolchain
    # failure unrelated to documentation realization must not make this gate
    # red for a property it does not test.
    result = GenerationPipeline().run(
        system_dtrx,
        output_dir,
        PipelineConfig(
            target_language=LanguageId(target),
            profile=_PROFILE,
            validation_level=ValidationLevel.FAST,
        ),
    )
    if not result.success:
        raise RuntimeError(
            f"pipeline reported failure for target {target!r}: "
            f"{'; '.join(result.errors) or 'success=False, no error text'}"
        )
    return list(result.files_written)


# ---------------------------------------------------------------------------
# Structural artifact parsing
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ArtifactTextIndex:
    """The documentation surfaces one target's probe read from its generated tree.

    ``surfaces.published`` holds every string value this target's own
    published-documentation mechanism carries (an OpenAPI-decorator keyword
    argument, a doc block, ...). ``surfaces.source_comments`` holds every plain
    source-commentary comment's text (``#``/``//``, never ``///``).
    """

    surfaces: DocumentationSurfaces

    @property
    def published_strings(self) -> frozenset[str]:
        return self.surfaces.published

    @property
    def source_comments(self) -> frozenset[str]:
        return self.surfaces.source_comments

    def has_published(self, text: str) -> bool:
        return any(text in s for s in self.published_strings)

    def has_source_comment(self, text: str) -> bool:
        return any(text in s for s in self.source_comments)


def index_from_probes(
    target: str, probes: LanguageConformanceProbes, generated_root: Path, files: Sequence[Path]
) -> ArtifactTextIndex:
    """Read *target*'s documentation surfaces through its own *probes*.

    Raises:
        ValueError: the probe found no documentation surface at all in the
            generated files (a probe that finds nothing proves nothing).
    """
    surfaces = probes.documentation_surfaces(generated_root, files)
    if not surfaces.published and not surfaces.source_comments:
        raise ValueError(
            f"probe for {target!r} found no documentation surface in the {len(files)} generated "
            f"file(s); a census that finds nothing proves nothing. Expected at least one "
            f"published or source-comment text from the fixture's documented constructs. Fix: "
            f"make the language's documentation_surfaces read the surfaces its generator emits."
        )
    return ArtifactTextIndex(surfaces)


def build_index(target: str, generated_root: Path, files: Sequence[Path]) -> ArtifactTextIndex:
    """Resolve *target*'s conformance probes and read its generated *files* through them.

    Raises:
        PluginValidationError: *target* declares no (or incomplete) conformance probes.
        ValueError: the probe found no documentation surface.
    """
    return index_from_probes(target, language_conformance_probes(target), generated_root, files)


# ---------------------------------------------------------------------------
# Per-construct-kind surface checks
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SurfaceCheck:
    target: str
    construct_kind: str
    surface: str
    populated: bool
    evidence: str


def check_all_surfaces(target: str, index: ArtifactTextIndex) -> list[SurfaceCheck]:
    """Run every (construct_kind, surface) cell against *index* for *target*."""
    checks: list[SurfaceCheck] = []

    endpoint_pub = index.has_published(ENDPOINT_PUBLISHED_SUMMARY) and index.has_published(
        ENDPOINT_PUBLISHED_DESCRIPTION
    )
    checks.append(SurfaceCheck(
        target, "endpoint", "published", endpoint_pub,
        f"summary+description present={endpoint_pub}",
    ))
    endpoint_src = index.has_source_comment(ENDPOINT_SOURCE_NOTE) and not index.has_published(
        ENDPOINT_SOURCE_NOTE
    )
    checks.append(SurfaceCheck(
        target, "endpoint", "source", endpoint_src,
        f"source comment present, absent from published={endpoint_src}",
    ))

    for kind, published_text, source_text in (
        ("entity", ENTITY_PUBLISHED_TEXT, ENTITY_SOURCE_NOTE),
        ("field", FIELD_PUBLISHED_TEXT, FIELD_SOURCE_NOTE),
        ("enum_value", ENUM_VALUE_PUBLISHED_TEXT, ENUM_VALUE_SOURCE_NOTE),
        ("struct_field", STRUCT_FIELD_PUBLISHED_TEXT, STRUCT_FIELD_SOURCE_NOTE),
        ("function", FUNCTION_PUBLISHED_TEXT, FUNCTION_SOURCE_NOTE),
    ):
        pub_ok = index.has_published(published_text)
        checks.append(SurfaceCheck(
            target, kind, "published", pub_ok, f"published text present={pub_ok}",
        ))
        src_ok = index.has_source_comment(source_text) and not index.has_published(source_text)
        checks.append(SurfaceCheck(
            target, kind, "source", src_ok,
            f"source comment present, absent from published={src_ok}",
        ))

    return checks


def census_target_checks(checks: Sequence[SurfaceCheck]) -> tuple[dict[str, int], list[SurfaceCheck]]:
    """The census counts and the holes of one target's surface checks.

    Every unpopulated cell is a hole; nothing can excuse one.

    Returns:
        ``({"checked", "populated", "holes"}, the unpopulated checks)``.
    """
    holes = [check for check in checks if not check.populated]
    counts = {
        "checked": len(checks),
        "populated": len(checks) - len(holes),
        "holes": len(holes),
    }
    return counts, holes


def gate_exit_code(
    generation_failures: Mapping[str, str],
    holes: Sequence[SurfaceCheck],
    coverage_regressions: Sequence[str],
) -> int:
    """The gate verdict: a generation failure, any hole, or a coverage
    regression fails it. There is no input that excuses a hole."""
    if generation_failures or holes or coverage_regressions:
        return EXIT_FAIL
    return EXIT_OK


# ---------------------------------------------------------------------------
# Coverage census -- attached runs vs. runs that reach an artifact
# ---------------------------------------------------------------------------
#
# The surface checks above ask "did THIS construct kind's text land on THIS
# declared surface". Decision 39's invariant 1 asks a second, wider question:
# of every comment run the parser ATTACHED to a node, how many reach no
# generated artifact at all? Produced-minus-consumed is asserted zero inside
# datrix-language (capture never loses a run); this is the other half --
# attached-but-unemitted -- and it is per target, because emission is.
#
# Deliberately a whole-tree text comparison rather than a channel-aware one:
# the question is coverage ("did this reach ANY artifact"), not placement
# ("did it reach the RIGHT surface", which the cells above already police).
# A run counts as emitted when every non-blank line of its normalized body
# appears somewhere in that target's output, which is what makes a multi-line
# run still match after each physical line picked up its own comment prefix.


@dataclass(frozen=True)
class AttachedRun:
    """One comment run the parser attached to a node in the fixture."""

    #: ``<NodeClass>@<line>`` -- identifies the run in gate output without
    #: depending on dict ordering.
    anchor: str
    text: str
    published: bool


def collect_attached_runs(fixture_root: Path) -> tuple[AttachedRun, ...]:
    """Every ``DocComment`` the real parser attaches over the fixture's own files.

    Runs the shipped capture pipeline exactly as
    ``TreeSitterParser._transform_tree`` does -- transform with
    ``inject_builtins=False`` (a builtin node's location points at
    ``builtins.dtrx``, so excluding builtins keeps the census scoped to the
    fixture's own comments) then attach against a freshly built index --
    and walks the resulting model with ``Node.walk()``.

    Floating runs attach to nothing by design (Decision 39, detached
    comments) and are therefore absent here: the invariant is about runs
    that WERE attached and then reached no artifact.
    """
    from datrix_language.parser.tree_sitter_datrix.parser import TreeSitterParser
    from datrix_language.transformers.cst_utils import TransformContext
    from datrix_language.transformers.doc_comments import (
        attach_documentation,
        build_comment_index,
    )
    from datrix_language.transformers.transformer import ASTTransformer

    parser = TreeSitterParser()
    runs: list[AttachedRun] = []
    for dtrx_file in sorted(fixture_root.rglob("*.dtrx")):
        source = dtrx_file.read_text(encoding="utf-8")
        tree = parser.parse_tree(source)
        transformer = ASTTransformer(
            TransformContext(source=source.encode("utf-8"), file_path=str(dtrx_file))
        )
        # require_system=False: the fixture's service file is included BY
        # system.dtrx rather than declaring its own system block, and comment
        # attachment is per-file and needs no system at all.
        app = transformer.transform(tree, require_system=False, inject_builtins=False)
        index = build_comment_index(tree.root_node, source, str(dtrx_file))
        attach_documentation(app, index)
        for node in app.walk():
            if node.doc is None:
                continue
            line = node.location.line if node.location is not None else 0
            runs.append(
                AttachedRun(
                    anchor=f"{type(node).__name__}@{dtrx_file.name}:{line}",
                    text=node.doc.text,
                    published=node.doc.published,
                )
            )
    return tuple(runs)


#: Leading comment punctuation stripped from each physical line before the
#: coverage comparison, longest first so ``///`` is not consumed as ``//``.
#: Stripping happens ONLY at a line's start, after its indent -- never
#: mid-line, where the same characters are operators.
_COMMENT_LINE_OPENERS: Final[tuple[str, ...]] = (
    "/**", "///", "//", "/*", "*/", "*", "--", "#",
)
_WHITESPACE_RUN: Final[re.Pattern[str]] = re.compile(r"\s+")


def _strip_comment_opener(line: str) -> str:
    """Remove one leading comment opener from an already-lstripped *line*."""
    for opener in _COMMENT_LINE_OPENERS:
        if line.startswith(opener):
            return line[len(opener):]
    return line


def normalize_for_coverage(text: str) -> str:
    """Collapse *text* to marker-free, single-spaced form for containment.

    Every target reflows author prose on the way out: each physical line
    picks up that language's comment marker, and a formatter (ruff, or any
    target's own) rewraps the result at its own column limit. A raw
    substring search therefore reports a genuinely emitted run as missing
    the moment a formatter breaks it across lines. Stripping one leading
    comment opener per line and collapsing all whitespace makes the
    comparison invariant to both.
    """
    stripped = (_strip_comment_opener(line.strip()) for line in text.split("\n"))
    return _WHITESPACE_RUN.sub(" ", " ".join(stripped)).strip()


def generated_output_blob(out_dir: Path) -> str:
    """Every text-decodable byte one target generated, normalized for coverage.

    Binary artifacts are skipped rather than guessed at; a comment run has
    no way to be "in" one.
    """
    chunks: list[str] = []
    for path in sorted(out_dir.rglob("*")):
        if not path.is_file():
            continue
        try:
            chunks.append(normalize_for_coverage(path.read_text(encoding="utf-8")))
        except (UnicodeDecodeError, OSError):
            continue
    return " ".join(chunks)


def coverage_fragments(text: str) -> tuple[str, ...]:
    """*text* split into the largest chunks a target can be asked to emit whole.

    The one split every published surface performs is
    ``summary_and_description`` (datrix-common): the first paragraph's first
    line becomes an OpenAPI operation's ``summary`` and the remainder its
    ``description`` -- two separate fields, often in two separate call
    keywords. Asking for the whole body as one contiguous string would
    therefore report every multi-paragraph run as unemitted on every target.
    Paragraphs (blank-line-separated blocks) are the granularity that split
    preserves, so they are the unit compared.
    """
    paragraphs = [normalize_for_coverage(p) for p in re.split(r"\n[ \t]*\n", text)]
    return tuple(p for p in paragraphs if p)


def run_reaches_output(run: AttachedRun, blob: str) -> bool:
    """Whether every paragraph of *run*'s body appears in the normalized *blob*."""
    fragments = coverage_fragments(run.text)
    return bool(fragments) and all(fragment in blob for fragment in fragments)


def coverage_holes(
    runs: tuple[AttachedRun, ...], blob: str
) -> tuple[AttachedRun, ...]:
    """The attached runs that reach no artifact in this target's output."""
    return tuple(run for run in runs if not run_reaches_output(run, blob))


def load_coverage_baseline() -> dict[str, int]:
    """Read the decrease-only per-target coverage-hole baseline.

    Returns:
        ``{target: max_allowed_holes}``; an empty mapping when the file does
        not exist yet (first-ever run, before ``--update-coverage-baseline``
        freezes it), which pins every target at zero.

    Raises:
        ValueError: The file exists but is not an object whose ``holes`` map
            carries non-negative integers.
    """
    if not COVERAGE_BASELINE_PATH.exists():
        return {}
    data = json.loads(COVERAGE_BASELINE_PATH.read_text(encoding="utf-8"))
    holes = data.get("holes")
    if not isinstance(holes, dict):
        raise ValueError(
            f"Malformed {COVERAGE_BASELINE_PATH}: expected an object with a "
            f"'holes' mapping of target -> non-negative integer, got {data!r}."
        )
    parsed: dict[str, int] = {}
    for target, count in holes.items():
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise ValueError(
                f"Malformed {COVERAGE_BASELINE_PATH}: holes[{target!r}] must be a "
                f"non-negative integer, got {count!r}."
            )
        parsed[str(target)] = count
    return parsed


def write_coverage_baseline(holes: dict[str, int]) -> None:
    """The only writer of ``COVERAGE_BASELINE_PATH`` -- invoked solely via
    ``--update-coverage-baseline``, a deliberate, manual re-freeze."""
    payload = {
        "_comment": [
            "Decrease-only ratchet (Decision 39 invariant 1): per registered",
            "datrix.languages target, how many of the documentation-realization",
            "fixture's ATTACHED comment runs reach NO generated artifact.",
            "A run whose count is HIGHER than the pinned value fails the gate --",
            "a target quietly stopped emitting documentation it used to emit.",
            "Attachment itself is policed separately, and at zero, by",
            "datrix-language's own produced-minus-consumed census.",
            "documentation-realization-parity-gate.ps1 -UpdateCoverageBaseline is",
            "the only writer; do not hand-guess the numbers.",
        ],
        "holes": dict(sorted(holes.items())),
    }
    COVERAGE_BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    COVERAGE_BASELINE_PATH.write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Non-vacuity self-test
# ---------------------------------------------------------------------------


def run_self_test() -> list[str]:
    """Prove this gate names no target and the fixture and comparison are
    non-vacuous BEFORE any real comparison is trusted.

    1. This gate names no registered target (imports or name literals).
    2. Every marker text the fixture claims to carry is actually present in
       the fixture DSL source (a scan that can only return zero is not
       evidence -- this proves the fixture itself is not empty/wrong).
    3. The gate's real dispatch, driven with in-process fixture probes whose
       language name is not a registered one, reads a conformant surface set,
       reports a planted unpopulated cell, fails on an empty probe result and
       fails on a plugin with no probe member. (The per-language extractors are
       proven by the owning packages' own tests.)
    4. A planted unpopulated cell is reported as a hole and fails the gate,
       with no exemption input to pass it.

    Returns:
        A list of failure descriptions -- empty means the comparison is sound.
    """
    problems: list[str] = list(self_test_gate_names_no_target(__file__))
    if problems:
        return problems

    for marker in _all_marker_texts():
        if marker not in _SERVICE_DTRX:
            problems.append(
                f"self-test: marker text {marker!r} is not present in the "
                f"fixture DSL itself -- the fixture is inconsistent with its "
                f"own constants."
            )

    problems.extend(_probe_dispatch_self_test())
    problems.extend(_hard_zero_self_test())
    problems.extend(_coverage_census_self_test())

    return problems


#: The fixture language's name -- deliberately not a registered one.
_SELF_TEST_LANGUAGE: Final[str] = "self_test_lang"


class _FixtureDocumentationProbes:
    """An in-process fixture language whose probe returns fixed surfaces."""

    def __init__(self, surfaces: DocumentationSurfaces) -> None:
        self._surfaces = surfaces

    def response_body_wire_fields(self, generated_root: Path) -> tuple[ResponseBodyWireField, ...]:
        return ()

    def route_wire_contracts(self, generated_root: Path) -> tuple[RouteWireContract, ...]:
        return ()

    def documentation_surfaces(self, generated_root: Path, files: Sequence[Path]) -> DocumentationSurfaces:
        return self._surfaces

    def render_enum_classifier(self, enum: object, paths: object) -> EnumClassifierRender:
        return EnumClassifierRender(())

    def event_envelopes(self, generated_root: Path) -> EventEnvelopeCensus:
        return EventEnvelopeCensus(published=(), consumed_keys={})


class _FixturePluginWithoutProbes:
    """A fixture language plugin with no `conformance_probes` member."""


def _fully_documented_surfaces() -> DocumentationSurfaces:
    """Surfaces carrying every marker text on its right side of the published/source divide."""
    published = {
        ENDPOINT_PUBLISHED_SUMMARY,
        ENDPOINT_PUBLISHED_DESCRIPTION,
        ENTITY_PUBLISHED_TEXT,
        FIELD_PUBLISHED_TEXT,
        ENUM_VALUE_PUBLISHED_TEXT,
        STRUCT_FIELD_PUBLISHED_TEXT,
        FUNCTION_PUBLISHED_TEXT,
    }
    comments = {
        ENDPOINT_SOURCE_NOTE,
        ENTITY_SOURCE_NOTE,
        FIELD_SOURCE_NOTE,
        ENUM_VALUE_SOURCE_NOTE,
        STRUCT_FIELD_SOURCE_NOTE,
        FUNCTION_SOURCE_NOTE,
    }
    return DocumentationSurfaces(frozenset(published), frozenset(comments))


def _probe_dispatch_self_test() -> list[str]:
    """Drive the gate's real surface reading and checking with fixture probes.

    A fully documented fixture passes every cell; a fixture whose published set
    lacks the entity text is reported as exactly that hole; a fixture that leaks
    a source note into the published set fails that construct's source cell; an
    empty probe result is refused; a plugin with no probe member is refused with
    the accessor's message.
    """
    problems: list[str] = []
    root = Path(".")

    def holes_for(surfaces: DocumentationSurfaces) -> list[SurfaceCheck]:
        index = index_from_probes(
            _SELF_TEST_LANGUAGE, _FixtureDocumentationProbes(surfaces), root, [root / "fixture.src"]
        )
        return census_target_checks(check_all_surfaces(_SELF_TEST_LANGUAGE, index))[1]

    full = _fully_documented_surfaces()
    if holes_for(full):
        problems.append("self-test: a fully documented fixture probe reported a hole -- over-triggering.")

    without_entity = DocumentationSurfaces(full.published - {ENTITY_PUBLISHED_TEXT}, full.source_comments)
    found = [(hole.construct_kind, hole.surface) for hole in holes_for(without_entity)]
    if found != [("entity", "published")]:
        problems.append(
            f"self-test: a fixture whose published set lacks the entity text must be exactly one "
            f"(entity, published) hole, got {found}."
        )

    leaking = DocumentationSurfaces(full.published | {FIELD_SOURCE_NOTE}, full.source_comments)
    found = [(hole.construct_kind, hole.surface) for hole in holes_for(leaking)]
    if found != [("field", "source")]:
        problems.append(
            f"self-test: a fixture leaking a source note into the published set must be exactly one "
            f"(field, source) hole, got {found}."
        )

    try:
        holes_for(DocumentationSurfaces(frozenset(), frozenset()))
    except ValueError as exc:
        if _SELF_TEST_LANGUAGE not in str(exc) or "found no documentation surface" not in str(exc):
            problems.append(f"self-test: the refusal of an empty probe result did not name the language ({exc}).")
    else:
        problems.append("self-test: a probe returning no documentation surface was not refused.")

    try:
        conformance_probes_of_language_plugin(_SELF_TEST_LANGUAGE, _FixturePluginWithoutProbes())
    except PluginValidationError as exc:
        if _SELF_TEST_LANGUAGE not in str(exc) or "declares no conformance probes" not in str(exc):
            problems.append(f"self-test: a plugin with no probe member failed without the accessor's message ({exc}).")
    else:
        problems.append("self-test: a plugin with no probe member was not refused.")
    return problems


def _hard_zero_self_test() -> list[str]:
    """Prove an unpopulated cell is a failure with no exemption path.

    Plants one fully populated target and one target with a single unpopulated
    (construct kind, surface) cell: the census must report exactly that cell as
    a hole, the verdict must pass the first and fail the second, and the verdict
    takes no exemption input that could turn the second into a pass.
    """
    problems: list[str] = []
    planted_kind, planted_surface = CONSTRUCT_KINDS[0], SURFACES[0]
    populated = [
        SurfaceCheck("planted-clean", kind, surface, True, "planted populated")
        for kind in CONSTRUCT_KINDS
        for surface in SURFACES
    ]
    with_hole = [
        SurfaceCheck(
            "planted-hole", kind, surface,
            (kind, surface) != (planted_kind, planted_surface),
            "planted populated" if (kind, surface) != (planted_kind, planted_surface) else "planted hole",
        )
        for kind in CONSTRUCT_KINDS
        for surface in SURFACES
    ]
    clean_counts, clean_holes = census_target_checks(populated)
    hole_counts, found_holes = census_target_checks(with_hole)
    cells = len(CONSTRUCT_KINDS) * len(SURFACES)
    if clean_holes or clean_counts != {"checked": cells, "populated": cells, "holes": 0}:
        problems.append(
            f"self-test: a fully populated target reported holes or a wrong census "
            f"(holes={clean_holes}, counts={clean_counts})."
        )
    if (
        [(hole.construct_kind, hole.surface) for hole in found_holes] != [(planted_kind, planted_surface)]
        or hole_counts != {"checked": cells, "populated": cells - 1, "holes": 1}
    ):
        problems.append(
            f"self-test: the planted unpopulated cell ({planted_kind}, {planted_surface}) was not "
            f"reported as exactly one hole (holes={found_holes}, counts={hole_counts}) -- the census "
            f"cannot see an unpopulated cell."
        )
    if gate_exit_code({}, clean_holes, []) != EXIT_OK:
        problems.append("self-test: a fully populated census with no regression did not pass the gate.")
    if gate_exit_code({}, found_holes, []) != EXIT_FAIL:
        problems.append(
            "self-test: a planted unpopulated cell did not fail the gate -- a hole must fail with no "
            "exemption path."
        )
    if gate_exit_code({"planted": "boom"}, clean_holes, []) != EXIT_FAIL:
        problems.append("self-test: a generation failure did not fail the gate.")
    if gate_exit_code({}, clean_holes, ["planted"]) != EXIT_FAIL:
        problems.append("self-test: a coverage regression did not fail the gate.")
    return problems


def _coverage_census_self_test() -> list[str]:
    """Prove the coverage census can return BOTH answers.

    A ratchet that can only ever report zero holes is not evidence. This
    plants one run whose text IS in the blob (single-line and multi-line,
    the latter with each physical line carrying its own comment prefix, the
    shape real output has) and one whose text is not, and requires the
    census to separate them.
    """
    problems: list[str] = []
    blob = normalize_for_coverage(
        "class Product:\n"
        "    # SELF_TEST_COVERAGE_PRESENT\n"
        "    ...\n"
        "  // SELF_TEST_COVERAGE_REFLOWED_ONE\n"
        "  // SELF_TEST_COVERAGE_REFLOWED_TWO\n"
        "@router.get('/x', summary='SELF_TEST_COVERAGE_SUMMARY',\n"
        "            description='SELF_TEST_COVERAGE_DESCRIPTION')\n"
    )
    present = AttachedRun("SelfTest@x:1", "SELF_TEST_COVERAGE_PRESENT", True)
    multiline = AttachedRun(
        "SelfTest@x:2",
        "SELF_TEST_COVERAGE_REFLOWED_ONE SELF_TEST_COVERAGE_REFLOWED_TWO",
        True,
    )
    absent = AttachedRun("SelfTest@x:3", "SELF_TEST_COVERAGE_ABSENT", False)
    split_across_fields = AttachedRun(
        "SelfTest@x:4",
        "SELF_TEST_COVERAGE_SUMMARY\n\nSELF_TEST_COVERAGE_DESCRIPTION",
        True,
    )
    half_emitted = AttachedRun(
        "SelfTest@x:5",
        "SELF_TEST_COVERAGE_SUMMARY\n\nSELF_TEST_COVERAGE_ABSENT_SECOND_PARAGRAPH",
        True,
    )

    holes = coverage_holes(
        (present, multiline, absent, split_across_fields, half_emitted), blob
    )
    hole_anchors = {h.anchor for h in holes}
    if present.anchor in hole_anchors:
        problems.append(
            "self-test: coverage census reported a run whose text IS in the "
            "generated blob as a hole -- it would under-report coverage."
        )
    if multiline.anchor in hole_anchors:
        problems.append(
            "self-test: coverage census reported a run the blob carries "
            "REFLOWED across two marker-prefixed lines as a hole -- marker "
            "stripping plus whitespace collapse is what keeps a formatter's "
            "line breaks from reading as lost documentation."
        )
    if absent.anchor not in hole_anchors:
        problems.append(
            "self-test: coverage census did NOT report a run whose text is "
            "absent from the generated blob -- the ratchet can only return "
            "zero and is therefore not evidence."
        )
    if split_across_fields.anchor in hole_anchors:
        problems.append(
            "self-test: coverage census reported a run whose two paragraphs "
            "the blob carries in SEPARATE fields (summary=/description=, the "
            "one split every published surface performs) as a hole."
        )
    if half_emitted.anchor not in hole_anchors:
        problems.append(
            "self-test: coverage census did NOT report a run whose SECOND "
            "paragraph is absent -- paragraph matching must require every "
            "paragraph, not merely one."
        )
    return problems


# ---------------------------------------------------------------------------
# Full gate run
# ---------------------------------------------------------------------------


@dataclass
class GateReport:
    targets: list[str]
    census: dict[str, dict[str, int]]
    holes: list[dict[str, str]]
    generation_failures: dict[str, str]
    result: str
    #: Per target: attached runs, how many reached an artifact, and the ones
    #: that did not (Decision 39 invariant 1's decrease-only ratchet).
    coverage: dict[str, dict[str, object]] = dataclass_field(default_factory=dict)


def run_gate(*, debug: bool = False, update_coverage_baseline: bool = False) -> tuple[int, GateReport]:
    """Full gate run. Returns ``(exit_code, report)``.

    Runs two comparisons over the same generated fixture: the per-cell
    realization check (every (construct_kind, surface) cell populated, a hard
    zero) and the coverage census (attached runs that reach no artifact,
    against the decrease-only baseline).

    Exit codes:
        0: every registered target's every (construct_kind, surface) cell is
           populated, and no target's coverage holes exceed its pinned
           baseline.
        1: at least one hole, a coverage regression past the baseline, or a
           generation failure.
        2: fewer than ``_MIN_TARGETS`` targets are registered.
    """
    targets = sorted(registered_language_names())
    if len(targets) < _MIN_TARGETS:
        logger.error(
            "DOCUMENTATION-REALIZATION GATE CANNOT RUN: only %d target(s) "
            "registered under 'datrix.languages' (%s) -- at least %d are "
            "required. Fix: install the missing datrix-codegen-<lang> "
            "package(s) into D:\\datrix\\.venv.",
            len(targets), targets, _MIN_TARGETS,
        )
        return EXIT_VACUOUS, GateReport(targets, {}, [], {}, "VACUOUS")

    try:
        coverage_baseline = load_coverage_baseline()
    except ValueError as exc:
        logger.error("COVERAGE BASELINE INVALID: %s", exc)
        return EXIT_FAIL, GateReport(targets, {}, [], {}, "COVERAGE_BASELINE_INVALID")

    fixture_root = SCRATCH_ROOT / "fixture"
    system_dtrx = write_fixture(fixture_root)

    attached_runs = collect_attached_runs(fixture_root)
    logger.info("COVERAGE CENSUS: %d attached comment run(s) in the fixture.", len(attached_runs))

    generation_failures: dict[str, str] = {}
    per_target_checks: dict[str, list[SurfaceCheck]] = {}
    per_target_holes: dict[str, tuple[AttachedRun, ...]] = {}
    for target in targets:
        out_dir = SCRATCH_ROOT / "generated" / target
        try:
            files = generate_for_target(system_dtrx, out_dir, target)
            index = build_index(target, out_dir, files)
            per_target_checks[target] = check_all_surfaces(target, index)
            per_target_holes[target] = coverage_holes(
                attached_runs, generated_output_blob(out_dir)
            )
            if debug:
                logger.debug(
                    "target=%s files_written=%d published_strings=%s",
                    target, len(files), sorted(index.published_strings),
                )
        except Exception as exc:  # noqa: BLE001 -- reported per-target, never swallowed
            generation_failures[target] = str(exc)
            logger.error("target=%s GENERATION/PARSE FAILED: %s", target, exc)

    census: dict[str, dict[str, int]] = {}
    holes_found: list[SurfaceCheck] = []

    for target in targets:
        if target in generation_failures:
            census[target] = {"checked": 0, "populated": 0, "holes": 1}
            continue
        census[target], target_holes = census_target_checks(per_target_checks[target])
        for hole in target_holes:
            logger.error(
                "HOLE target=%s construct_kind=%s surface=%s evidence=%s",
                hole.target, hole.construct_kind, hole.surface, hole.evidence,
            )
        holes_found.extend(target_holes)

    for target, counts in census.items():
        logger.info(
            "CENSUS target=%s checked=%d populated=%d holes=%d",
            target, counts["checked"], counts["populated"], counts["holes"],
        )

    coverage: dict[str, dict[str, object]] = {}
    coverage_regressions: list[str] = []
    for target in sorted(per_target_holes):
        holes = per_target_holes[target]
        pinned = coverage_baseline.get(target, 0)
        coverage[target] = {
            "attached_runs": len(attached_runs),
            "reached_artifact": len(attached_runs) - len(holes),
            "holes": len(holes),
            "pinned_holes": pinned,
            "hole_anchors": [h.anchor for h in holes],
        }
        for hole in holes:
            logger.warning(
                "COVERAGE HOLE target=%s anchor=%s channel=%s text=%r",
                target, hole.anchor,
                "published" if hole.published else "source",
                hole.text,
            )
        logger.info(
            "COVERAGE target=%s attached=%d reached=%d holes=%d pinned=%d",
            target, len(attached_runs), len(attached_runs) - len(holes), len(holes), pinned,
        )
        if len(holes) > pinned:
            coverage_regressions.append(target)
            logger.error(
                "COVERAGE REGRESSION target=%s: %d attached run(s) reach no "
                "artifact, above the pinned baseline of %d in %s. Either emit "
                "the documentation again, or re-pin with "
                "documentation-realization-parity-gate.ps1 -UpdateCoverageBaseline "
                "once the increase is understood and intended.",
                target, len(holes), pinned, COVERAGE_BASELINE_PATH,
            )

    if update_coverage_baseline:
        if generation_failures:
            logger.error(
                "Refusing to re-pin the coverage baseline: %d target(s) failed "
                "generation (%s), so their hole counts are not measurements.",
                len(generation_failures), sorted(generation_failures),
            )
            return EXIT_FAIL, GateReport(
                targets, census, [], generation_failures, "COVERAGE_BASELINE_NOT_WRITTEN",
            )
        write_coverage_baseline({t: len(h) for t, h in per_target_holes.items()})
        logger.info("Coverage baseline re-pinned: %s", COVERAGE_BASELINE_PATH)

    exit_code = gate_exit_code(generation_failures, holes_found, coverage_regressions)

    report = GateReport(
        targets=targets,
        census=census,
        holes=[
            {"target": c.target, "construct_kind": c.construct_kind, "surface": c.surface, "evidence": c.evidence}
            for c in holes_found
        ],
        generation_failures=generation_failures,
        result="PASS" if exit_code == EXIT_OK else "FAIL",
        coverage=coverage,
    )
    _write_report(report)

    if exit_code == EXIT_OK:
        logger.info(
            "DOCUMENTATION-REALIZATION PARITY HOLDS: %d target(s) (%s), zero holes; "
            "coverage census within baseline on every target.",
            len(targets), targets,
        )
    return exit_code, report


def _write_report(report: GateReport) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "result": report.result,
        "targets": report.targets,
        "census": report.census,
        "holes": report.holes,
        "generation_failures": report.generation_failures,
        "coverage": report.coverage,
    }
    REPORT_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    logger.info("Report written: %s", REPORT_PATH)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def configure_logging(debug: bool = False) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Documentation-realization parity gate: for every registered "
            "datrix.languages target, asserts a documented construct's "
            "author text reaches that target's declared published/source "
            "documentation surfaces in a real generated fixture; an "
            "unpopulated cell fails with no exemption path "
            "(Decision 39 I2/I6)."
        ),
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run only the non-vacuity self-test and skip the real comparison",
    )
    parser.add_argument(
        "--update-coverage-baseline",
        action="store_true",
        help=(
            "Re-pin the decrease-only coverage-hole baseline to this run's "
            "measured per-target counts (the only writer of the baseline file)"
        ),
    )
    args = parser.parse_args()

    configure_logging(debug=args.debug)

    try:
        problems = run_self_test()
    except Exception as exc:  # noqa: BLE001 -- reported, never swallowed
        logger.error("Non-vacuity self-test raised unexpectedly: %s", exc)
        return EXIT_VACUOUS
    if problems:
        logger.error("Non-vacuity self-test FAILED:")
        for p in problems:
            logger.error("  %s", p)
        return EXIT_VACUOUS
    logger.info("Non-vacuity self-test passed.")

    if args.self_test:
        return EXIT_OK

    exit_code, _report = run_gate(
        debug=args.debug, update_coverage_baseline=args.update_coverage_baseline
    )
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
