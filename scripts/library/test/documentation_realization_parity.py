"""Documentation-realization parity gate (Decision 39, invariants I2 and I6).

Every registered ``datrix.languages`` target either emits an authored ``///``
DSL comment onto its declared PUBLISHED documentation surface (an OpenAPI
operation summary/description, a schema field description, a C# XML doc
comment, ...) and a plain ``//`` comment onto its SOURCE-commentary surface
only -- or the target carries a typed, counted exemption in
``scripts/config/documentation-realization-exemptions.json`` explaining why
it cannot.

WHAT THIS GATE CHECKS -- SIX CONSTRUCT KINDS, TWO SURFACES EACH
-----------------------------------------------------------------
``endpoint``, ``entity``, ``field``, ``enum_value``, ``struct_field``,
``function``, each checked on its ``published`` surface (must carry the
``///`` text) and its ``source`` surface (must carry the ``//`` text, and
must NEVER carry it on the published surface -- the I2 leak guard).

Targets are discovered from the ``datrix.languages`` entry-point group at
runtime -- never a hardcoded ``python``/``typescript``/``java``/``dotnet``
literal -- so a future ``datrix-codegen-<lang>`` package is covered with no
edit here. Fewer than two registered targets makes the comparison vacuous
and fails loud (exit 2).

GENERATION: THE REAL PIPELINE, NOT A HAND-BUILT CONTEXT
---------------------------------------------------------
Generates one small fixture project (module constants below) via
``datrix_cli.pipeline.generation.GenerationPipeline`` -- the exact code path
``datrix generate`` / ``generate.ps1`` runs -- once per registered target.
``reference_example_parity.py``'s own docstring records why a hand-built
``Application``/``CodegenContext`` (``parse_fixture_with_semantics`` +
``attach_default_configs`` + a package-private test context) is NOT the
generator and drifts from it; this gate follows that same lesson.

ASSERTING ON GENERATED ARTIFACTS, NOT A RUNNING SERVICE (task amendment)
---------------------------------------------------------------------------
This environment has no NuGet connectivity, so a generated .NET project can
never be restored/built/started here. Per the task's binding amendment, this
gate asserts over the GENERATED SOURCE ARTIFACTS themselves, parsed
structurally (never a line-oriented regex over the whole file):

- Python: the real ``ast`` module (keyword-argument string constants named
  ``summary``/``description`` on any call, plus a class/function/async-
  function docstring via ``ast.get_docstring`` -- the landing site for a
  construct with no decorator/keyword surface: an enum value's text folds
  into the enclosing ``Enum`` class's own docstring, a service function's
  text becomes its own docstring) plus the real ``tokenize`` module
  (COMMENT tokens) -- never a substring search.
- TypeScript / Java: a hand-rolled but genuinely structural lexer
  (:func:`_classify_spans`) that separates STRING/LINE_COMMENT/XMLDOC/
  DOC_BLOCK/BLOCK_COMMENT spans from code, so a marker sentence sitting
  inside a string literal is never confused with the same text sitting
  inside a comment. Published-surface values are extracted two ways:
  finding a decorator anchor (``@ApiOperation(``, ``@Operation(``, ...)
  OUTSIDE any string/comment span and then bracket-depth-tracking to the
  matching close, collecting every string literal inside that span
  (:func:`_bracketed_call_strings`); and reading ``/** ... */`` JSDoc/Javadoc
  doc-comment blocks (:func:`_doc_block_published_texts`) -- the landing
  site for a construct with no decorator surface (an enum value, a service
  function, an entity's DTO class), distinguished structurally from a plain
  ``/* ... */`` block comment by the lexer's own ``/**`` opener, exactly as
  ``///`` is distinguished from ``//``.
- C# (dotnet): consecutive ``///`` lines are grouped into one XML doc block
  and parsed as real XML (``xml.etree.ElementTree``), pulling ``<summary>``/
  ``<remarks>``/``<param>`` element text -- ``<param>``'s ``name`` attribute
  attributes a struct field's doc to the right record component -- never a
  regex over the XML shape.

Two targets' own packages prove a real end-to-end document for this feature:
python asserts against a real FastAPI router's ``.openapi()``, and typescript
against a real ``tsc`` + ``SwaggerModule.createDocument()`` run over an
npm-installed dependency set. java and dotnet do NOT: their suites assert over
the generated artifacts (springdoc reads the emitted annotations at request
time, and there is no NuGet connectivity here to compile a ``.xml`` doc file),
which is the same rung of the ladder this gate stands on. So this gate is the
repo-level cross-target census, and for java/dotnet the artifact assertion is
the strongest proof currently available in this environment -- stated plainly
rather than implied to be a live-document check.

Repo-level validation **script** (per the datrix showcase boundary -- no
pytest suite lives in datrix), following the runtime-discovery +
non-vacuity-self-test shape of ``block_realization_parity.py`` and
``pooled_cache_realization_gate.py``.
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import re
import shutil
import sys
import tokenize
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field as dataclass_field
from pathlib import Path
from typing import Final

# Add library directory to sys.path to import from shared (this file lives at
# library/test/, shared/ lives at the sibling library/shared/).
_LIBRARY_DIR = Path(__file__).resolve().parent.parent
if _LIBRARY_DIR.exists() and str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from shared.registered_targets import registered_language_names  # noqa: E402

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Roots
# ---------------------------------------------------------------------------
# This file: datrix/scripts/library/test/documentation_realization_parity.py
# parents[0]=.../library/test, [1]=.../library, [2]=.../scripts, [3]=<datrix>,
# [4]=<the monorepo workspace root>.
_HERE: Final[Path] = Path(__file__).resolve()
DATRIX_DIR: Final[Path] = _HERE.parents[3]
WORKSPACE_ROOT: Final[Path] = _HERE.parents[4]

EXEMPTIONS_PATH: Final[Path] = (
    DATRIX_DIR / "scripts" / "config" / "documentation-realization-exemptions.json"
)
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
    from datrix_cli.pipeline.generation import GenerationPipeline, PipelineConfig
    from datrix_common.generation.validation_level import ValidationLevel
    from datrix_common.plugin.identity import LanguageId

    _ensure_language_plugins_registered()

    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    # ValidationLevel.FAST runs fix_imports + format_files but SKIPS
    # validate_files -- which is where dotnet's post-generation hook runs a
    # real `dotnet build` and java's runs a real `mvnw compile`. Per this
    # gate's binding task amendment, the property under test is "the target
    # emits the right documentation into the right construct," not "the
    # target's toolchain can restore/build/compile it" -- this sandbox has
    # zero NuGet connectivity (dotnet) and an incompatible default JDK
    # release (java), so STANDARD's build-validation step fails for reasons
    # unrelated to documentation realization and would make this gate
    # perpetually red for a property it does not test.
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
    """Structurally extracted text surfaces from one target's generated tree.

    ``published_strings`` holds every string value this target's own
    published-documentation mechanism carries (an OpenAPI-decorator keyword
    argument, an XML ``<summary>``/``<remarks>`` element, ...).
    ``source_comments`` holds every plain source-commentary comment's text
    (``#``/``//``, never ``///``).
    """

    published_strings: frozenset[str]
    source_comments: frozenset[str]

    def has_published(self, text: str) -> bool:
        return any(text in s for s in self.published_strings)

    def has_source_comment(self, text: str) -> bool:
        return any(text in s for s in self.source_comments)


def _python_index(files: list[Path]) -> ArtifactTextIndex:
    """Real ``ast`` + ``tokenize`` extraction for generated Python.

    Published: the string value of any call keyword argument named
    ``summary`` or ``description`` (covers the route decorator, ``Field(...)``,
    and ``strawberry.field(...)``/``strawberry.type(...)`` alike, without
    hand-listing each callee -- the keyword name IS the documentation
    contract per ``datrix_codegen_python``'s own realization), plus the
    docstring of any class/function/async-function definition
    (``ast.get_docstring`` -- a real AST query, never a substring search)
    -- the landing site for a construct with no decorator/keyword surface:
    an enum value's text folds into the enclosing ``Enum`` class's own
    docstring, a service function's text becomes its own docstring.
    Source: every ``#`` comment token's text (``tokenize.COMMENT`` -- a real
    comment token, never a substring inside a string literal).
    """
    import ast

    published: set[str] = set()
    comments: set[str] = set()
    for f in files:
        if f.suffix != ".py":
            continue
        text = f.read_text(encoding="utf-8")
        try:
            tree = ast.parse(text, filename=str(f))
        except SyntaxError as exc:
            raise ValueError(f"generated Python file failed to parse: {f}: {exc}") from exc
        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                docstring = ast.get_docstring(node)
                if docstring:
                    published.add(docstring)
            if not isinstance(node, ast.Call):
                continue
            for kw in node.keywords:
                if (
                    kw.arg in ("summary", "description")
                    and isinstance(kw.value, ast.Constant)
                    and isinstance(kw.value.value, str)
                ):
                    published.add(kw.value.value)
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type != tokenize.COMMENT:
                continue
            body = tok.string[1:]
            if body.startswith(" "):
                body = body[1:]
            comments.add(body.rstrip())
    return ArtifactTextIndex(frozenset(published), frozenset(comments))


#: Common backslash-escape decodings applied while lexing a C-family string
#: literal (TS/Java/C#) -- an escaped quote/backslash must become the real
#: character, or a marker text containing an apostrophe (e.g. "product's")
#: fails containment against the raw ``\'``-escaped source text.
_STRING_ESCAPES: Final[dict[str, str]] = {
    "'": "'", '"': '"', "`": "`", "\\": "\\", "n": "\n", "t": "\t", "r": "\r",
}

_Span = tuple[int, int, str, str]  # (start, end, kind, value)


def _classify_spans(text: str) -> list[_Span]:
    """Real character-by-character lexing of a C-family (TS/Java/C#) source
    file into typed spans: ``STRING``, ``LINE_COMMENT`` (``//``), ``XMLDOC``
    (``///``), ``DOC_BLOCK`` (``/** ... */``, the JSDoc/Javadoc doc-comment
    convention), ``BLOCK_COMMENT`` (``/* ... */``, never a doc surface),
    ``OTHER`` (code). String/char/template-literal quoting respects
    backslash escapes. ``DOC_BLOCK`` is distinguished from ``BLOCK_COMMENT``
    by its literal ``/**`` opener, checked before the generic ``/*`` check,
    exactly mirroring how ``XMLDOC`` (``///``) is distinguished from
    ``LINE_COMMENT`` (``//``) by checking the three-char prefix first. This
    is the structural foundation every extractor below builds on -- never a
    line-oriented regex over the raw file text.
    """
    spans: list[_Span] = []
    n = len(text)
    i = 0
    start_other = 0

    def flush(end: int) -> None:
        nonlocal start_other
        if end > start_other:
            spans.append((start_other, end, "OTHER", text[start_other:end]))
        start_other = end

    while i < n:
        three = text[i:i + 3]
        two = text[i:i + 2]
        if three == "///":
            flush(i)
            j = text.find("\n", i)
            j = n if j == -1 else j
            spans.append((i, j, "XMLDOC", text[i + 3:j]))
            i = j
            start_other = i
            continue
        if three == "/**" and text[i:i + 4] != "/**/":
            flush(i)
            close = text.find("*/", i + 3)
            body_end = n if close == -1 else close
            end = n if close == -1 else close + 2
            spans.append((i, end, "DOC_BLOCK", text[i + 3:body_end]))
            i = end
            start_other = i
            continue
        if two == "//":
            flush(i)
            j = text.find("\n", i)
            j = n if j == -1 else j
            spans.append((i, j, "LINE_COMMENT", text[i + 2:j]))
            i = j
            start_other = i
            continue
        if two == "/*":
            flush(i)
            close = text.find("*/", i + 2)
            body_end = n if close == -1 else close
            end = n if close == -1 else close + 2
            spans.append((i, end, "BLOCK_COMMENT", text[i + 2:body_end]))
            i = end
            start_other = i
            continue
        c = text[i]
        if c in "\"'`":
            flush(i)
            quote = c
            j = i + 1
            value_chars: list[str] = []
            while j < n:
                ch = text[j]
                if ch == "\\" and j + 1 < n:
                    nxt = text[j + 1]
                    value_chars.append(_STRING_ESCAPES.get(nxt, nxt))
                    j += 2
                    continue
                if ch == quote:
                    j += 1
                    break
                value_chars.append(ch)
                j += 1
            j = min(j, n)
            spans.append((i, j, "STRING", "".join(value_chars)))
            i = j
            start_other = i
            continue
        i += 1
    flush(n)
    return spans


def _group_consecutive_spans(spans: list[_Span], kind: str) -> list[list[str]]:
    """Group consecutive spans of *kind* into blocks, bridged by whitespace-
    only OTHER spans between them (a multi-line ``//`` note word-wrapped by a
    formatter, or a multi-line ``///`` XML doc, both land as several
    adjacent same-kind spans separated only by the newline/indentation
    between physical lines -- they belong to one logical comment, not
    several unrelated ones)."""
    blocks: list[list[str]] = []
    current: list[str] = []
    for (_, _, k, v) in spans:
        if k == kind:
            current.append(v)
            continue
        if k == "OTHER" and v.strip() == "":
            continue
        if current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    return blocks


def _line_comments(spans: list[_Span]) -> set[str]:
    """Every plain ``//`` comment's text, as both the single-line form (so a
    short, standalone note still matches) and the whole word-wrapped block
    joined with spaces (so a formatter that wraps one long note across
    several ``//`` lines still yields the complete sentence as one string).
    """
    texts: set[str] = set()
    for block in _group_consecutive_spans(spans, "LINE_COMMENT"):
        joined = " ".join(line.strip() for line in block if line.strip())
        if joined:
            texts.add(joined)
        for line in block:
            if line.strip():
                texts.add(line.strip())
    return texts


def _scan_call_body(text: str, spans: list[_Span], start_pos: int) -> set[str]:
    """From *start_pos* (immediately after an anchor's opening ``(``),
    bracket-depth-track forward through *spans* to the matching close,
    collecting every STRING span's value encountered while inside the call.
    Depth counts any of ``( { [`` / ``) } ]`` uniformly -- sufficient to find
    the call's own closing bracket without needing to distinguish paren vs.
    brace, since generated code is always bracket-balanced.
    """
    depth = 1
    strings: set[str] = set()
    for (s, e, k, v) in spans:
        if e <= start_pos:
            continue
        if k == "OTHER":
            local = v[max(0, start_pos - s):]
            for ch in local:
                if ch in "({[":
                    depth += 1
                elif ch in ")}]":
                    depth -= 1
                    if depth == 0:
                        return strings
        elif k == "STRING":
            if depth >= 1:
                strings.add(v)
    return strings


def _bracketed_call_strings(text: str, spans: list[_Span], anchor_re: re.Pattern[str]) -> set[str]:
    """Every string literal inside a balanced-bracket call whose anchor
    (e.g. ``@ApiOperation(``) matches *anchor_re*, found only within OTHER
    (code, not string/comment) spans."""
    strings: set[str] = set()
    for (s, e, k, v) in spans:
        if k != "OTHER":
            continue
        for m in anchor_re.finditer(v):
            abs_after_open = s + m.end()
            strings |= _scan_call_body(text, spans, abs_after_open)
    return strings


def _xmldoc_published_texts(spans: list[_Span]) -> set[str]:
    """Group consecutive ``///`` (XMLDOC) spans into blocks (see
    :func:`_group_consecutive_spans`), then parse each block as real XML
    (wrapped in a synthetic root) and pull ``<summary>``/``<remarks>``/
    ``<param>`` element text. Never a regex over the XML shape.

    A ``<param name="...">`` element's text is attributed to its ``name``
    attribute (``"{name}: {text}"``) rather than added bare -- the
    compiler-recognized landing site for a positional record component's
    PUBLISHED comment when multiple documented components share one doc
    block above the record declaration (see
    ``datrix_codegen_dotnet.documentation.build_struct_field_param_tag``),
    so a text this construct kind actually carries is distinguishable from
    a sibling component's ``<param>`` text rather than merged into one
    undifferentiated pool.
    """
    texts: set[str] = set()
    for lines in _group_consecutive_spans(spans, "XMLDOC"):
        joined = "\n".join(lines)
        try:
            root = ET.fromstring(f"<doc>{joined}</doc>")
        except ET.ParseError:
            continue
        for tag in ("summary", "remarks"):
            for el in root.findall(tag):
                if el.text and el.text.strip():
                    texts.add(el.text.strip())
        for el in root.findall("param"):
            if not (el.text and el.text.strip()):
                continue
            text = el.text.strip()
            name = el.get("name")
            texts.add(f"{name}: {text}" if name else text)
    return texts


_DOC_BLOCK_LINE_PREFIX_RE: Final[re.Pattern[str]] = re.compile(r"^[ \t]*\*[ \t]?")


def _doc_block_published_texts(spans: list[_Span]) -> set[str]:
    """Extract published text from ``/** ... */`` JSDoc/Javadoc doc-comment
    blocks -- the TypeScript/Java landing site for a construct with no
    decorator surface (an enum value, a service function, an entity's DTO
    class), the C-family analogue of dotnet's ``/// <summary>``.
    :func:`_classify_spans` already distinguishes this convention
    structurally from a plain ``/* ... */`` block comment (never a doc
    surface) by its literal ``/**`` opener, mirroring the ``///`` vs ``//``
    distinction it already draws for dotnet.

    Each ``DOC_BLOCK`` span's raw (stripped) content is kept as-is -- a
    single-line published text still matches by containment even with its
    conventional leading ``" * "`` intact -- and a second, cleaned
    reconstruction strips that leading ``" * "`` continuation marker from
    every physical line and rejoins them, so a published text that would
    otherwise straddle the marker (a multi-paragraph doc block) still
    matches as one contiguous string. Never a regex over the whole file --
    both forms are read from the span :func:`_classify_spans` already
    isolated.
    """
    texts: set[str] = set()
    for (_, _, kind, value) in spans:
        if kind != "DOC_BLOCK":
            continue
        raw = value.strip()
        if raw:
            texts.add(raw)
        cleaned_lines = [
            _DOC_BLOCK_LINE_PREFIX_RE.sub("", line, count=1).strip()
            for line in value.split("\n")
        ]
        cleaned = "\n".join(line for line in cleaned_lines if line)
        if cleaned:
            texts.add(cleaned)
    return texts


#: Per-target published-surface annotation anchors (TS/Java only -- dotnet's
#: published surface is XML doc, handled separately). Anchor regex captures
#: through the opening ``(`` so `_bracketed_call_strings` can start counting
#: bracket depth at 1 immediately after the match.
_ANNOTATION_ANCHORS: Final[dict[str, tuple[str, ...]]] = {
    "typescript": (
        r"@ApiOperation\s*\(", r"@ApiProperty(?:Optional)?\s*\(", r"@ApiSchema\s*\(",
    ),
    "java": (r"@Operation\s*\(", r"@Schema\s*\("),
}

_SOURCE_EXTENSION: Final[dict[str, str]] = {
    "typescript": ".ts",
    "java": ".java",
    "dotnet": ".cs",
}


def _c_family_index(files: list[Path], target: str) -> ArtifactTextIndex:
    """Structural extraction for TS/Java/C#, dispatched by *target*.

    Raises:
        ValueError: *target* has no registered probe (see module docstring
            -- per-target extraction logic is inherent to genuinely
            different published-doc syntax across languages; a target
            reaching here without one fails loud rather than being silently
            skipped).
    """
    extension = _SOURCE_EXTENSION.get(target)
    if extension is None:
        raise ValueError(
            f"documentation-realization-parity-gate has no structural artifact "
            f"probe registered for target {target!r}. Registered probes: "
            f"python (ast/tokenize), {sorted(_SOURCE_EXTENSION)} (structural "
            f"lexer). Add a probe for this target rather than silently "
            f"skipping it -- see _c_family_index / _python_index."
        )
    anchors = tuple(re.compile(p) for p in _ANNOTATION_ANCHORS.get(target, ()))
    use_xmldoc = target == "dotnet"
    #: Every c-family target other than dotnet uses the ``/** ... */``
    #: JSDoc/Javadoc doc-block convention (dotnet's doc-block equivalent is
    #: XML ``///``, read by ``use_xmldoc`` above) -- never a hardcoded
    #: ``("typescript", "java")`` tuple, so a future c-family target is
    #: covered with no edit here.
    use_doc_block = not use_xmldoc

    published: set[str] = set()
    comments: set[str] = set()
    for f in files:
        if f.suffix != extension:
            continue
        text = f.read_text(encoding="utf-8")
        spans = _classify_spans(text)
        comments |= _line_comments(spans)
        for anchor_re in anchors:
            published |= _bracketed_call_strings(text, spans, anchor_re)
        if use_xmldoc:
            published |= _xmldoc_published_texts(spans)
        if use_doc_block:
            published |= _doc_block_published_texts(spans)
    return ArtifactTextIndex(frozenset(published), frozenset(comments))


def build_index(target: str, files: list[Path]) -> ArtifactTextIndex:
    """Dispatch to the right structural extractor for *target*."""
    if target == "python":
        return _python_index(files)
    return _c_family_index(files, target)


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
    from datrix_language.transformers import ASTTransformer
    from datrix_language.transformers.cst_utils import TransformContext
    from datrix_language.transformers.doc_comments import (
        attach_documentation,
        build_comment_index,
    )

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
    picks up that language's comment marker, and a formatter
    (google-java-format, ruff, CSharpier) rewraps the result at its own
    column limit. A raw substring search therefore reports a genuinely
    emitted run as missing the moment a formatter breaks it across lines --
    which is exactly what java's own output does. Stripping one leading
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
# Exemption file (reviewed, typed holes -- never silence)
# ---------------------------------------------------------------------------

_EXEMPTION_REQUIRED_FIELDS: Final[tuple[str, ...]] = (
    "target", "construct_kind", "surface", "reason",
)


def load_exemptions(config_path: Path = EXEMPTIONS_PATH) -> tuple[dict[tuple[str, str, str], str], int]:
    """Load and validate the exemption file.

    Returns:
        ``({(target, construct_kind, surface): reason}, pinned_count)``.

    Raises:
        ValueError: Missing/malformed file, an entry missing a non-empty
            required field, or the live entry count does not match
            ``pinned_count``.
    """
    if not config_path.exists():
        raise ValueError(
            f"Missing exemption file {config_path}. It pins the catalogued "
            f"documentation-realization holes. Restore it from git; the gate "
            f"never creates it."
        )
    data = json.loads(config_path.read_text(encoding="utf-8"))
    entries = data.get("exemptions")
    pinned_count = data.get("pinned_count")
    if not isinstance(entries, list) or not isinstance(pinned_count, int) or isinstance(pinned_count, bool):
        raise ValueError(
            f"Malformed exemption file {config_path}: expected an object with "
            f"'pinned_count' (int) and 'exemptions' (array of "
            f"{{target, construct_kind, surface, reason}})."
        )
    exemptions: dict[tuple[str, str, str], str] = {}
    for entry in entries:
        for field_name in _EXEMPTION_REQUIRED_FIELDS:
            if not isinstance(entry.get(field_name), str) or not entry[field_name].strip():
                raise ValueError(
                    f"Exemption entry {entry!r} in {config_path} is missing a "
                    f"non-empty {field_name!r}."
                )
        key = (entry["target"], entry["construct_kind"], entry["surface"])
        exemptions[key] = entry["reason"]
    if len(entries) != pinned_count:
        raise ValueError(
            f"Exemption file {config_path} has {len(entries)} entries but "
            f"'pinned_count' is pinned at {pinned_count}. Update pinned_count "
            f"in the same change that adds or removes an entry."
        )
    return exemptions, pinned_count


# ---------------------------------------------------------------------------
# Non-vacuity self-test
# ---------------------------------------------------------------------------


def run_self_test() -> list[str]:
    """Prove the fixture and every structural extractor are non-vacuous
    BEFORE any real comparison is trusted.

    1. Every marker text the fixture claims to carry is actually present in
       the fixture DSL source (a scan that can only return zero is not
       evidence -- this proves the fixture itself is not empty/wrong).
    2. The Python extractor finds a known-present published summary/
       description and a known-present source comment in a synthetic
       snippet it has never seen, and does NOT leak the comment into the
       published set -- plus a known-present docstring on a plain
       (no-decorator) function.
    3. The C-family (TS/Java) extractor does the same, via the real
       bracket-depth-tracking annotation-argument scan, plus a known-present
       ``/** ... */`` doc block, and does NOT treat a sibling plain
       ``/* ... */`` block comment as published.
    4. The dotnet XML-doc extractor finds known-present ``<summary>``/
       ``<remarks>``/``<param>`` text (the ``<param>`` case attributed to
       its ``name``) and a known-present plain ``//`` source comment.

    Returns:
        A list of failure descriptions -- empty means every extractor is sound.
    """
    problems: list[str] = []

    for marker in _all_marker_texts():
        if marker not in _SERVICE_DTRX:
            problems.append(
                f"self-test: marker text {marker!r} is not present in the "
                f"fixture DSL itself -- the fixture is inconsistent with its "
                f"own constants."
            )

    synth_py = (
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n\n\n"
        "@router.get(\"/x\", summary=\"SELF_TEST_PY_SUMMARY\", description=\"SELF_TEST_PY_DESC\")\n"
        "async def handler():\n"
        "    # SELF_TEST_PY_SOURCE_NOTE\n"
        "    pass\n"
        "\n\n"
        "def documented_helper():\n"
        "    \"\"\"SELF_TEST_PY_DOCSTRING\"\"\"\n"
        "    return None\n"
    )
    import tempfile
    tmp_dir = Path(tempfile.mkdtemp(prefix="doc-realization-selftest-py-"))
    try:
        py_file = tmp_dir / "handler.py"
        py_file.write_text(synth_py, encoding="utf-8")
        py_index = _python_index([py_file])
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    if not py_index.has_published("SELF_TEST_PY_SUMMARY") or not py_index.has_published("SELF_TEST_PY_DESC"):
        problems.append(
            f"self-test: python extractor did not find a known-present "
            f"published summary/description (found: {sorted(py_index.published_strings)})"
        )
    if not py_index.has_source_comment("SELF_TEST_PY_SOURCE_NOTE"):
        problems.append(
            f"self-test: python extractor did not find a known-present source "
            f"comment (found: {sorted(py_index.source_comments)})"
        )
    if py_index.has_published("SELF_TEST_PY_SOURCE_NOTE"):
        problems.append("self-test: python extractor leaked a source comment into the published set")
    if not py_index.has_published("SELF_TEST_PY_DOCSTRING"):
        problems.append(
            f"self-test: python extractor did not find a known-present "
            f"docstring on a plain (no-decorator) function "
            f"(found: {sorted(py_index.published_strings)})"
        )

    synth_ts = (
        "@ApiOperation({ summary: 'SELF_TEST_TS_SUMMARY', description: 'SELF_TEST_TS_DESC' })\n"
        "async handler() {\n"
        "  // SELF_TEST_TS_SOURCE_NOTE\n"
        "  return this.svc.find();\n"
        "}\n"
    )
    ts_spans = _classify_spans(synth_ts)
    ts_published = _bracketed_call_strings(synth_ts, ts_spans, re.compile(r"@ApiOperation\s*\("))
    ts_comments = _line_comments(ts_spans)
    if "SELF_TEST_TS_SUMMARY" not in ts_published or "SELF_TEST_TS_DESC" not in ts_published:
        problems.append(
            f"self-test: C-family extractor did not find a known-present "
            f"published summary/description (found: {sorted(ts_published)})"
        )
    if not any("SELF_TEST_TS_SOURCE_NOTE" in c for c in ts_comments):
        problems.append(
            f"self-test: C-family extractor did not find a known-present "
            f"source comment (found: {sorted(ts_comments)})"
        )
    if "SELF_TEST_TS_SOURCE_NOTE" in ts_published:
        problems.append("self-test: C-family extractor leaked a source comment into the published set")

    synth_doc_block = (
        "/**\n"
        " * SELF_TEST_DOC_BLOCK_TEXT\n"
        " */\n"
        "export class SelfTestClass {}\n"
        "/* SELF_TEST_PLAIN_BLOCK_COMMENT_NOT_DOC */\n"
        "export class SelfTestOther {}\n"
    )
    doc_block_spans = _classify_spans(synth_doc_block)
    doc_block_published = _doc_block_published_texts(doc_block_spans)
    if not any("SELF_TEST_DOC_BLOCK_TEXT" in t for t in doc_block_published):
        problems.append(
            f"self-test: doc-block extractor did not find a known-present "
            f"/** ... */ published text (found: {sorted(doc_block_published)})"
        )
    if any("SELF_TEST_PLAIN_BLOCK_COMMENT_NOT_DOC" in t for t in doc_block_published):
        problems.append(
            "self-test: doc-block extractor treated a plain /* ... */ block "
            "comment (no doubled-star opener) as a published doc block"
        )

    synth_cs = (
        "    /// <summary>\n"
        "    /// SELF_TEST_CS_SUMMARY\n"
        "    /// </summary>\n"
        "    /// <remarks>\n"
        "    /// SELF_TEST_CS_REMARKS\n"
        "    /// </remarks>\n"
        "    /// <param name=\"selfTestWidgetCount\">\n"
        "    /// SELF_TEST_CS_PARAM_TEXT\n"
        "    /// </param>\n"
        "    public IActionResult Handler() {\n"
        "        // SELF_TEST_CS_SOURCE_NOTE\n"
        "        return Ok();\n"
        "    }\n"
    )
    cs_spans = _classify_spans(synth_cs)
    cs_published = _xmldoc_published_texts(cs_spans)
    cs_comments = _line_comments(cs_spans)
    if not any("SELF_TEST_CS_SUMMARY" in t for t in cs_published) or not any(
        "SELF_TEST_CS_REMARKS" in t for t in cs_published
    ):
        problems.append(
            f"self-test: dotnet XML-doc extractor did not find known-present "
            f"<summary>/<remarks> text (found: {sorted(cs_published)})"
        )
    if not any("SELF_TEST_CS_PARAM_TEXT" in t for t in cs_published):
        problems.append(
            f"self-test: dotnet XML-doc extractor did not find a known-present "
            f"<param> text (found: {sorted(cs_published)})"
        )
    if not any("selfTestWidgetCount" in t for t in cs_published):
        problems.append(
            "self-test: dotnet XML-doc extractor did not attribute the "
            "<param> text to its 'name' attribute"
        )
    if not any("SELF_TEST_CS_SOURCE_NOTE" in c for c in cs_comments):
        problems.append(
            f"self-test: dotnet extractor did not find a known-present plain "
            f"// source comment (found: {sorted(cs_comments)})"
        )
    if any("SELF_TEST_CS_SOURCE_NOTE" in t for t in cs_published):
        problems.append("self-test: dotnet extractor leaked a // source comment into the XML doc published set")

    problems.extend(_coverage_census_self_test())

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
    unexempted_holes: list[dict[str, str]]
    exempted: list[dict[str, str]]
    generation_failures: dict[str, str]
    result: str
    #: Per target: attached runs, how many reached an artifact, and the ones
    #: that did not (Decision 39 invariant 1's decrease-only ratchet).
    coverage: dict[str, dict[str, object]] = dataclass_field(default_factory=dict)


def run_gate(*, debug: bool = False, update_coverage_baseline: bool = False) -> tuple[int, GateReport]:
    """Full gate run. Returns ``(exit_code, report)``.

    Runs two comparisons over the same generated fixture: the per-cell
    realization check (every (construct_kind, surface) cell populated or
    exempted) and the coverage census (attached runs that reach no artifact,
    against the decrease-only baseline).

    Exit codes:
        0: every registered target's every (construct_kind, surface) cell is
           populated or carries a reviewed exemption, and no target's
           coverage holes exceed its pinned baseline.
        1: at least one unexempted hole, a stale exemption (exempted but now
           populated), a coverage regression past the baseline, a generation
           failure, or an exemption-file count mismatch.
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
        return EXIT_VACUOUS, GateReport(targets, {}, [], [], {}, "VACUOUS")

    try:
        exemptions, pinned_count = load_exemptions()
    except ValueError as exc:
        logger.error("EXEMPTION FILE INVALID: %s", exc)
        return EXIT_FAIL, GateReport(targets, {}, [], [], {}, "EXEMPTION_FILE_INVALID")

    try:
        coverage_baseline = load_coverage_baseline()
    except ValueError as exc:
        logger.error("COVERAGE BASELINE INVALID: %s", exc)
        return EXIT_FAIL, GateReport(targets, {}, [], [], {}, "COVERAGE_BASELINE_INVALID")

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
            index = build_index(target, files)
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
    unexempted: list[SurfaceCheck] = []
    exempted_hits: list[SurfaceCheck] = []
    stale: list[tuple[str, str, str]] = []

    seen_keys: set[tuple[str, str, str]] = set()
    for target in targets:
        if target in generation_failures:
            census[target] = {"checked": 0, "populated": 0, "exempted": 0, "unexempted_holes": 1}
            continue
        checks = per_target_checks[target]
        checked = len(checks)
        populated = 0
        exempted_count = 0
        for c in checks:
            key = (c.target, c.construct_kind, c.surface)
            seen_keys.add(key)
            if c.populated:
                populated += 1
                if key in exemptions:
                    stale.append(key)
                continue
            if key in exemptions:
                exempted_count += 1
                exempted_hits.append(c)
                logger.info(
                    "EXEMPTED target=%s construct_kind=%s surface=%s reason=%s",
                    c.target, c.construct_kind, c.surface, exemptions[key],
                )
            else:
                unexempted.append(c)
                logger.error(
                    "UNEXEMPTED HOLE target=%s construct_kind=%s surface=%s evidence=%s",
                    c.target, c.construct_kind, c.surface, c.evidence,
                )
        census[target] = {
            "checked": checked,
            "populated": populated,
            "exempted": exempted_count,
            "unexempted_holes": checked - populated - exempted_count,
        }

    for target, counts in census.items():
        logger.info(
            "CENSUS target=%s checked=%d populated=%d exempted=%d unexempted_holes=%d",
            target, counts["checked"], counts["populated"], counts["exempted"], counts["unexempted_holes"],
        )

    if stale:
        for key in stale:
            logger.error(
                "STALE EXEMPTION: target=%s construct_kind=%s surface=%s is exempted "
                "in %s but the artifact now carries the text -- remove the entry and "
                "decrement pinned_count.",
                key[0], key[1], key[2], EXEMPTIONS_PATH,
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
                targets, census, [], [], generation_failures, "COVERAGE_BASELINE_NOT_WRITTEN",
            )
        write_coverage_baseline({t: len(h) for t, h in per_target_holes.items()})
        logger.info("Coverage baseline re-pinned: %s", COVERAGE_BASELINE_PATH)

    result = "PASS"
    exit_code = EXIT_OK
    if generation_failures or unexempted or stale or coverage_regressions:
        result = "FAIL"
        exit_code = EXIT_FAIL

    report = GateReport(
        targets=targets,
        census=census,
        unexempted_holes=[
            {"target": c.target, "construct_kind": c.construct_kind, "surface": c.surface, "evidence": c.evidence}
            for c in unexempted
        ],
        exempted=[
            {"target": c.target, "construct_kind": c.construct_kind, "surface": c.surface,
             "reason": exemptions[(c.target, c.construct_kind, c.surface)]}
            for c in exempted_hits
        ],
        generation_failures=generation_failures,
        result=result,
        coverage=coverage,
    )
    _write_report(report, pinned_count)

    if exit_code == EXIT_OK:
        logger.info(
            "DOCUMENTATION-REALIZATION PARITY HOLDS: %d target(s) (%s), zero "
            "unexempted holes, %d reviewed exemption(s) (pinned_count=%d); "
            "coverage census within baseline on every target.",
            len(targets), targets, len(exempted_hits), pinned_count,
        )
    return exit_code, report


def _write_report(report: GateReport, pinned_count: int) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "result": report.result,
        "targets": report.targets,
        "census": report.census,
        "unexempted_holes": report.unexempted_holes,
        "exempted": report.exempted,
        "generation_failures": report.generation_failures,
        "pinned_exemption_count": pinned_count,
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
            "documentation surfaces in a real generated fixture, or carries "
            "a reviewed exemption (Decision 39 I2/I6)."
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
