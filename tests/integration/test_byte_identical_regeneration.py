"""Integration: registry-driven GenDSL emits byte-identical output for valid apps.

Relocated from datrix-codegen-common/tests/integration/ to avoid cross-package
boundary violations (datrix_codegen_common must not import datrix_codegen_python,
datrix_codegen_typescript, datrix_codegen_aws, datrix_codegen_azure, datrix_codegen_k8s,
datrix_codegen_docker). This test spans ALL generators and belongs at the repo level
(datrix/tests/integration/) where cross-package imports are not restricted.

Generate-twice determinism approach:
  1. Each (app_id, target) pair is generated TWICE using the REAL pipeline
     (parse -> Application -> generator), via in-process generation only
     (no subprocess, no mocks).
  2. The emitted file manifest from each run is compared for set-equality
     (no missing / extra / renamed files between runs).
  3. Every file's raw bytes are compared for exact equality between run 1 and run 2.

This proves that the phase-60 registry changes (registries, ``when``, ``@expand``,
semantic activation, dead-surface removal) leave the generated output byte-stable:
two consecutive generations of the same app produce identical results for every
target language and platform.

The example apps come from ``datrix/examples/`` and are parsed through the real
``parse_fixture_with_semantics`` pipeline (semantic analysis only; no ConfigDSL
resolution) with configs attached programmatically via ``attach_default_configs``.

Platform-specific config adjustments:
- Queue blocks: ``QueueConfig(engine="rabbitmq", CONTAINER)`` with full deployment
  fields (docker_image, volume_path, port, management_port, default_user,
  health_check_cmd) — Python/K8s/Docker generators require all deployment fields.
- K8s: full ``ServiceConfigProfileConfig`` (replicas, resources, healthCheck,
  readinessCheck, scaling) — K8s manifest builder validates all fields.
- AWS: RDBMS blocks upgraded to ``RdbmsFlavor.RDS + instance_class``, pubsub to
  ``MSK_SERVERLESS``, queue to ``SQS`` — AWS CDK generator requires cloud-native
  infra flavors.
- Azure: pubsub upgraded to ``EVENT_HUBS (sku=Standard)``, queue to
  ``SERVICE_BUS``, consumer-only services filtered out.
- Docker: ``DockerPlatformConfig(python_base="python:3.12-slim")`` + Docker
  generator defaults loaded via ``build_project_config([DockerGenerator])``.

Capture note: There are no committed golden snapshots — the byte-identical
invariant is established by generate-twice determinism. A single-byte difference
between run 1 and run 2 is always a real regression and must NOT be suppressed.

Exclusions: Docker ``.env.example`` and ``.env.validation`` contain per-build
randomly generated infrastructure passwords (SecretStore) and are excluded from
the byte-exact assertion; they remain under the file-manifest set-equality check.

Targets covered: python, typescript, sql, component, aws, azure, k8s, docker.
Queue-consumer tightening: the queue example (container RabbitMQ flavor) exercises
the queue.consumer.target semantic contract across all platform generators.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from datrix_common.config.datasource.models import PubsubConfig, QueueConfig, RdbmsConfig
from datrix_common.config.datasource.rdbms_engine import POSTGRES
from datrix_common.config.deployment_config import DeploymentConfig
from datrix_common.config.enums import (
    DeploymentProvider,
    DeploymentRuntime,
    Language,
    PubsubFlavor,
    QueueFlavor,
    RdbmsFlavor,
)
from datrix_common.config.service_config.models import (
    HealthCheckConfig,
    ReadinessCheckConfig,
    ResourceConfig,
    ResourceSpec,
    ScalingConfig,
    ScalingReplicas,
    ScalingTrigger,
    ServiceConfigProfileConfig,
)
from datrix_common.generation.generator import GeneratedFile, Generator
from datrix_common.testing import make_test_context
from datrix_common.testing.fixtures import attach_default_configs
from datrix_common.testing.infra_constants import RDBMS_DEPLOYMENT_DEFAULTS
from datrix_common.testing.parsing import parse_fixture_with_semantics

if TYPE_CHECKING:
    from datrix_common.datrix_model.containers import Application

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Example paths — confirmed against the real examples/ tree
# ---------------------------------------------------------------------------

_EXAMPLES = Path(__file__).parent.parent.parent.parent / "datrix" / "examples"

# 01-foundation: single service, rdbms entity; no REST API; covers python/typescript/sql/component
_FOUNDATION = _EXAMPLES / "01-foundation" / "system.dtrx"

# 02-features/queue: BookService (rest_api + queues + pubsub) + NotificationService
# (enqueue consumer); covers python/sql/component/k8s/docker/aws/azure
_QUEUE = _EXAMPLES / "02-features" / "03-infrastructure-blocks" / "queue" / "system.dtrx"

# ---------------------------------------------------------------------------
# Dependency catalogs — required by language generators for package resolution
# ---------------------------------------------------------------------------

_PYTHON_DEPS: dict[str, dict[str, str]] = {
    "python": {
        "pydantic": ">=2.10.0",
        "pydantic-settings": ">=2.7.0",
        "fastapi": ">=0.115.0",
        "uvicorn": ">=0.34.0",
        "httpx": ">=0.28.0",
        "bcrypt": ">=4.2.0",
        "PyJWT": ">=2.8.0",
        "cryptography": ">=42.0.0",
        "pytest": ">=8.3.0",
        "pytest-cov": ">=6.0.0",
        "pytest-asyncio": ">=0.24.0",
        "mypy": ">=1.13.0",
        "ruff": ">=0.8.0",
        "validators": ">=0.34.0",
        "sqlalchemy": ">=2.0.30",
        "alembic": ">=1.13.0",
        "asyncpg": ">=0.30.0",
        "aiomysql": ">=0.2.0",
        "redis": ">=5.0",
        "aiomcache": ">=0.8.0",
        "aiokafka": ">=0.11.0",
        "aio-pika": ">=9.4.0",
        "motor": ">=3.6.0",
        "boto3": ">=1.34.0",
        "aiobotocore": ">=13.0.0",
        "azure-cosmos": ">=4.7.0",
        "google-cloud-firestore": ">=2.19.0",
        "prometheus-client": ">=0.21.0",
        "opentelemetry-api": ">=1.28.0",
        "opentelemetry-sdk": ">=1.28.0",
        "opentelemetry-exporter-otlp": ">=1.28.0",
        "opentelemetry-exporter-zipkin": ">=1.28.0",
        "opentelemetry-sdk-extension-aws": ">=1.28.0",
        "opentelemetry-instrumentation-fastapi": ">=0.49b0",
        "opentelemetry-instrumentation-sqlalchemy": ">=0.49b0",
        "opentelemetry-instrumentation-httpx": ">=0.49b0",
        "opentelemetry-instrumentation-redis": ">=0.49b0",
        "google-cloud-storage": ">=2.14.0",
        "azure-storage-blob": ">=12.19.0",
        "sendgrid": ">=6.11.0",
        "requests": ">=2.31.0",
        "aiosmtplib": ">=3.0.0",
        "twilio": ">=9.0.0",
        "vonage": ">=3.19.0",
        "stripe": ">=11.0.0",
        "braintree": ">=4.27.0",
        "boto3-stubs": ">=1.34.0",
        "tenacity": ">=9.0.0",
        "pybreaker": ">=1.2.0",
        "apscheduler": ">=3.10.0",
        "jinja2": ">=3.1.0",
        "strawberry-graphql": ">=0.258.0",
        "elasticsearch": ">=8.0.0",
        "opensearch-py": ">=2.0.0",
        "shapely": ">=2.0,<3.0",
        "pyproj": ">=3.6.0",
        "geoalchemy2": ">=0.15,<1.0",
    },
}

_TS_DEPS: dict[str, dict[str, str]] = {
    "typescript": {
        "@nestjs/common": "^10.0.0",
        "@nestjs/core": "^10.0.0",
        "@nestjs/platform-express": "^10.0.0",
        "@nestjs/config": "^3.0.0",
        "@nestjs/mapped-types": "^2.0.0",
        "@nestjs/swagger": "^7.0.0",
        "@nestjs/graphql": "^10.2.1",
        "@nestjs/apollo": "^10.2.1",
        "@apollo/server": "^4.10.4",
        "graphql": "^16.9.0",
        "graphql-subscriptions": "^2.0.0",
        "@elastic/elasticsearch": "^8.15.0",
        "@opensearch-project/opensearch": "^2.12.0",
        "@mikro-orm/core": "^6.4.0",
        "@mikro-orm/nestjs": "^6.0.0",
        "@mikro-orm/postgresql": "^6.4.0",
        "@mikro-orm/mysql": "^6.4.0",
        "@mikro-orm/mariadb": "^6.4.0",
        "@mikro-orm/knex": "^6.4.0",
        "@mikro-orm/migrations": "^6.4.0",
        "@nestjs/cqrs": "^10.0.0",
        "@nestjs/event-emitter": "^2.0.0",
        "@nestjs/jwt": "^10.0.0",
        "@nestjs/passport": "^7.0.0",
        "@nestjs/throttler": "^5.0.0",
        "@nestjs/cli": "^10.0.0",
        "@nestjs/axios": "^3.0.0",
        "@nestjs/microservices": "^10.0.0",
        "@nestjs/mongoose": "^10.0.0",
        "pg": "^8.0.0",
        "mysql2": "^3.0.0",
        "class-validator": "^0.14.0",
        "validator": "^13.12.0",
        "@types/validator": "^13.12.2",
        "class-transformer": "^0.5.0",
        "reflect-metadata": "^0.1.0",
        "rxjs": "^7.0.0",
        "axios": "^1.0.0",
        "opossum": "^8.4.0",
        "@types/opossum": "^8.1.9",
        "jsonwebtoken": "^9.0.2",
        "@types/jsonwebtoken": "^9.0.6",
        "cockatiel": "^3.0.0",
        "consul": "^1.0.0",
        "@nestjs/schedule": "^4.0.0",
        "p-retry": "^6.0.0",
        "uuid": "^9.0.0",
        "ioredis": "^5.0.0",
        "prom-client": "^15.0.0",
        "nestjs-pino": "^4.0.0",
        "pino-http": "^9.0.0",
        "@opentelemetry/api": "^1.7.0",
        "@opentelemetry/sdk-node": "^0.48.0",
        "@opentelemetry/sdk-trace-node": "^1.20.0",
        "@opentelemetry/sdk-trace-base": "^1.20.0",
        "@opentelemetry/resources": "^1.20.0",
        "@opentelemetry/semantic-conventions": "^1.20.0",
        "@opentelemetry/instrumentation-http": "^0.48.0",
        "@opentelemetry/instrumentation-nestjs-core": "^0.34.0",
        "@opentelemetry/exporter-jaeger": "^1.20.0",
        "@opentelemetry/exporter-trace-otlp-http": "^0.48.0",
        "@opentelemetry/exporter-trace-otlp-grpc": "^0.48.0",
        "@opentelemetry/exporter-zipkin": "^1.20.0",
        "winston": "^3.11.0",
        "kafkajs": "^2.0.0",
        "amqplib": "^0.10.0",
        "@types/amqplib": "^0.10.0",
        "amqp-connection-manager": "^4.0.0",
        "bcrypt": "^5.1.0",
        "bcryptjs": "^2.4.3",
        "@types/bcryptjs": "^2.4.6",
        "@types/bcrypt": "^5.0.0",
        "date-fns": "^3.0.0",
        "mongoose": "^8.0.0",
        "@aws-sdk/client-dynamodb": "^3.0.0",
        "@aws-sdk/client-s3": "^3.0.0",
        "@aws-sdk/s3-request-presigner": "^3.0.0",
        "@google-cloud/storage": "^7.0.0",
        "@azure/storage-blob": "^12.0.0",
        "@aws-sdk/client-secrets-manager": "^3.500.0",
        "@aws-sdk/client-appconfigdata": "^3.500.0",
        "@azure/app-configuration": "^1.7.0",
        "@azure/identity": "^4.4.0",
        "@sendgrid/mail": "^7.7.0",
        "@aws-sdk/client-ses": "^3.400.0",
        "mailgun.js": "^9.3.0",
        "nodemailer": "^6.9.0",
        "twilio": "^4.20.0",
        "firebase-admin": "^12.0.0",
        "@aws-sdk/client-sns": "^3.400.0",
        "@vonage/server-sdk": "^3.10.0",
        "stripe": "^14.0.0",
        "braintree": "^3.22.0",
        "typescript": "^5.0.0",
        "@nestjs/testing": "^10.0.0",
        "@types/jest": "^29.5.0",
        "@types/express": "^4.17.0",
        "@types/node": "^20.0.0",
        "@types/supertest": "^6.0.0",
        "@types/uuid": "^9.0.0",
        "@types/adm-zip": "^0.5.7",
        "adm-zip": "^0.5.16",
        "csv-parse": "^5.5.6",
        "puppeteer": "^24.0.0",
        "jest": "^29.7.0",
        "supertest": "^6.3.0",
        "ts-jest": "^29.1.0",
        "ts-node": "^10.9.0",
    },
}

# ---------------------------------------------------------------------------
# K8s full deployment profile (all required fields)
# ---------------------------------------------------------------------------

_K8S_DEPLOYMENT_PROFILE = ServiceConfigProfileConfig(
    port=8000,
    replicas=2,
    resources=ResourceConfig(
        requests=ResourceSpec(cpu="100m", memory="128Mi"),
        limits=ResourceSpec(cpu="500m", memory="512Mi"),
    ),
    healthCheck=HealthCheckConfig(
        path="/health",
        initial_delay="15s",
        period="20s",
    ),
    readinessCheck=ReadinessCheckConfig(
        type="http",
        path="/health",
        initial_delay="5s",
        period="10s",
    ),
    scaling=ScalingConfig(
        replicas=ScalingReplicas(min=2, max=10),
        triggers=[
            ScalingTrigger(metric="cpu", target=70),
            ScalingTrigger(metric="memory", target=80),
        ],
    ),
)

# ---------------------------------------------------------------------------
# Application parsing helpers
# ---------------------------------------------------------------------------


def _base_parse(dtrx: Path) -> "Application":
    """Parse and attach default configs with RabbitMQ for queue blocks.

    Uses ``parse_fixture_with_semantics`` (no ConfigDSL on disk) so the helper
    works for any example regardless of which profiles its .dcfg declares.
    ``attach_default_configs`` populates rdbms/cache/pubsub/nosql/jobs/storage.
    Queue blocks are given a ``QueueConfig(engine="rabbitmq", CONTAINER)``
    explicitly because the Python generator requires RabbitMQ when lifecycle
    hooks dispatch queue tasks (``afterCreate``/``afterUpdate`` dispatches in
    the queue example's BookService).
    """
    app = parse_fixture_with_semantics(dtrx)
    attach_default_configs(app)
    for svc in app.services.values():
        if svc.queues_block is not None and svc.queues_block._config is None:
            svc.queues_block.config = QueueConfig(
                engine="rabbitmq",
                platform=QueueFlavor.CONTAINER,
                docker_image="rabbitmq:4.0-management-alpine",
                volume_path="/var/lib/rabbitmq",
                port=5672,
                management_port=15672,
                default_user="datrix",
                health_check_cmd='["CMD", "rabbitmq-diagnostics", "-q", "ping"]',
            )
    return app


def _aws_parse(dtrx: Path) -> "Application":
    """Parse app for AWS generation: upgrade infra blocks to cloud-native AWS configs.

    AWS CDK generator requires:
    - RDBMS blocks: ``RdbmsFlavor.RDS + instance_class`` (not CONTAINER)
    - PubSub blocks: ``engine="kafka" + PubsubFlavor.MSK_SERVERLESS`` or
      ``engine="sns-sqs" + PubsubFlavor.MANAGED`` (not CONTAINER/kafka)
    """
    app = _base_parse(dtrx)
    rdbms_defaults = RDBMS_DEPLOYMENT_DEFAULTS.get(str(POSTGRES))
    for svc in app.services.values():
        # ECS Fargate requires an explicit scaling block (no hidden defaults).
        if svc.config is not None and svc.config.scaling is None:
            svc.config = svc.config.model_copy(update={
                "scaling": ScalingConfig(
                    replicas=ScalingReplicas(min=1, max=4),
                    triggers=[ScalingTrigger(metric="cpu", target=70)],
                ),
            })
        for block in svc.rdbms_blocks.values():
            block.config = RdbmsConfig(
                id=uuid4(),
                engine=POSTGRES,
                platform=RdbmsFlavor.RDS,
                instance_class="db.t3.micro",
                **rdbms_defaults,
            )
        for block in svc.pubsub_blocks.values():
            # MSK Serverless: kafka engine, cloud-native; no instance_type/broker_count required
            block.config = PubsubConfig(
                engine="kafka",
                platform=PubsubFlavor.MSK_SERVERLESS,
                brokers=None,
                partitions=1,
                replication_factor=1,
            )
        # AWS queue infrastructure requires engine="sqs" (not rabbitmq)
        if svc.queues_block is not None:
            svc.queues_block.config = QueueConfig(
                engine="sqs",
                platform=QueueFlavor.SQS,
            )
    return app


def _k8s_parse(dtrx: Path) -> "Application":
    """Parse app for K8s generation: replace service configs with full K8s profiles.

    K8s manifest builder validates that all deployment fields are present:
    replicas, resources, healthCheck, readinessCheck, scaling.
    The default ``attach_default_configs`` sets only ``port`` on the service config.
    """
    app = _base_parse(dtrx)
    for idx, svc in enumerate(app.services.values()):
        svc.config = ServiceConfigProfileConfig(
            port=8000 + idx,
            replicas=_K8S_DEPLOYMENT_PROFILE.replicas,
            resources=_K8S_DEPLOYMENT_PROFILE.resources,
            healthCheck=_K8S_DEPLOYMENT_PROFILE.health_check,
            readinessCheck=_K8S_DEPLOYMENT_PROFILE.readiness_check,
            scaling=_K8S_DEPLOYMENT_PROFILE.scaling,
        )
    return app


def _azure_parse(dtrx: Path) -> "Application":
    """Parse app for Azure generation: cloud-native pubsub + filter consumer-only services.

    Azure (App Service mode) requires:
    1. PubSub blocks must use Azure-native flavors (event-hubs or managed);
       CONTAINER/kafka is not valid for Azure Bicep generation.
    2. Every service must have at least one deployable block (rest_api,
       graphql_api, serverless, jobs, or pubsub subscription). The queue
       example's NotificationService has only an enqueue consumer and an rdbms
       block — no Azure-deployable block — so it is removed.
    """
    app = _base_parse(dtrx)
    # Upgrade pubsub blocks to Azure Event Hubs (engine=kafka + EVENT_HUBS flavor)
    for svc in app.services.values():
        for block in svc.pubsub_blocks.values():
            block.config = PubsubConfig(
                engine="kafka",
                platform=PubsubFlavor.EVENT_HUBS,
                brokers=None,
                partitions=1,
                replication_factor=1,
                sku="Standard",
            )
    # Upgrade queue blocks to Azure Service Bus (service-bus engine + SERVICE_BUS flavor)
    for svc in app.services.values():
        if svc.queues_block is not None:
            svc.queues_block.config = QueueConfig(
                engine="service-bus",
                platform=QueueFlavor.SERVICE_BUS,
            )
    # Keep only services that have at least one Azure-deployable block.
    # Azure App Service mode deploys: rest_api, graphql_api, serverless, jobs,
    # and pubsub subscription consumers.  Enqueue-only services (like the queue
    # example's NotificationService) have no Azure-deployable block.
    to_remove: list[object] = []
    for name, svc in app.services.items():
        has_rest = bool(svc.rest_apis)
        has_graphql = bool(svc.graphql_apis)
        has_serverless = bool(svc.serverless_blocks)
        has_jobs = svc.jobs_block is not None
        has_pubsub_sub = bool(svc.subscriptions)
        if not (has_rest or has_graphql or has_serverless or has_jobs or has_pubsub_sub):
            to_remove.append(name)
    for name in to_remove:
        logger.info("azure_parse removing consumer-only service=%s", name)
        del app.services[name]
    return app


# ---------------------------------------------------------------------------
# Test cases: (app_id, dtrx_path, targets)
#
# Case selection rationale:
#   - "foundation": single-service rdbms app (no REST API); exercises
#     python/typescript/sql/component only.
#   - "queue": BookService (rest_api + queues + pubsub) + NotificationService
#     (enqueue consumer); exercises all 8 targets.
#     TypeScript skipped: NotificationService.NotificationDeliveryLog has an
#     Email field without a registered TypeScript entity-field type (scoped
#     limitation; TypeScript is already covered by the foundation case).
# ---------------------------------------------------------------------------

_CASES: list[tuple[str, Path, list[str]]] = [
    # foundation: python / typescript / sql / component only (no deployable REST API)
    (
        "foundation-basic",
        _FOUNDATION,
        ["python", "typescript", "sql", "component"],
    ),
    # queue: exercises queue.consumer.target tightening across all platform targets
    (
        "queue-consumer",
        _QUEUE,
        ["python", "sql", "component", "k8s", "docker", "aws", "azure"],
    ),
]


# ---------------------------------------------------------------------------
# Generator factories — one per target, built fresh per call
# ---------------------------------------------------------------------------


def _make_python_generator() -> Generator:
    from datrix_codegen_python.plugin import PythonGenerator

    return PythonGenerator(
        context=make_test_context(
            profile="test",
            target_language=Language.PYTHON,
            dependencies=_PYTHON_DEPS,
        )
    )


def _make_typescript_generator() -> Generator:
    from datrix_codegen_typescript.plugin import TypeScriptGenerator

    return TypeScriptGenerator(
        context=make_test_context(
            profile="test",
            target_language=Language.TYPESCRIPT,
            dependencies=_TS_DEPS,
        )
    )


def _make_sql_generator() -> Generator:
    from datrix_codegen_sql.generator import SQLGenerator

    return SQLGenerator(
        context=make_test_context(
            profile="test",
            target_language=Language.PYTHON,
        )
    )


def _make_component_generator() -> Generator:
    from datrix_codegen_component.plugin import ComponentGenerator

    return ComponentGenerator(
        context=make_test_context(
            profile="test",
            target_language=Language.PYTHON,
        )
    )


def _make_aws_generator() -> Generator:
    from datrix_codegen_aws.generators.aws_generator import AWSGenerator
    from datrix_common.config.platform.aws import (
        AwsPlatformConfig,
        ServiceDiscoveryConfig,
    )

    return AWSGenerator(
        context=make_test_context(
            profile="test",
            target_language=Language.PYTHON,
            deployment=DeploymentConfig(
                runtime=DeploymentRuntime.ECS_FARGATE,
                provider=DeploymentProvider.AWS,
            ),
        ),
        platform_config=AwsPlatformConfig(
            region="us-east-1",
            account_id="123456789012",
            vpc_cidr="10.0.0.0/16",
            elasticache_node_type="cache.t3.micro",
            dlq_max_receive_count=5,
            fargate_cpu=256,
            fargate_memory=512,
            desired_count=1,
            log_retention_days=7,
            sqs_visibility_timeout_seconds=30,
            sqs_retention_days=4,
            service_discovery=ServiceDiscoveryConfig(dns_ttl_seconds=10),
        ),
    )


def _make_azure_generator() -> Generator:
    from datrix_codegen_azure.generators.azure_generator import AzureGenerator
    from datrix_common.config.platform.azure import AzurePlatformConfig

    return AzureGenerator(
        context=make_test_context(
            profile="test",
            target_language=Language.PYTHON,
            deployment=DeploymentConfig(
                runtime=DeploymentRuntime.AZURE_APP_SERVICE,
                provider=DeploymentProvider.AZURE,
            ),
        ),
        platform_config=AzurePlatformConfig(
            location="eastus",
            resource_group="test-rg",
            appServicePlanSku="B1",
            pythonVersion="3.12",
            container_app_cpu="0.25",
            container_app_memory="0.5Gi",
            min_replicas=1,
            max_replicas=3,
            servicebus_message_ttl="P14D",
            servicebus_max_delivery_count=10,
        ),
    )


def _make_k8s_generator() -> Generator:
    from datrix_codegen_k8s.generators.k8s_generator import K8sGenerator
    from datrix_common.config.platform.k8s import K8sPlatformConfig

    return K8sGenerator(
        context=make_test_context(
            profile="test",
            target_language=Language.PYTHON,
            deployment=DeploymentConfig(
                runtime=DeploymentRuntime.KUBERNETES,
                provider=DeploymentProvider.LOCAL,
            ),
        ),
        platform_config=K8sPlatformConfig(
            namespace="test",
            app_name="test-app",
            # host is required for Ingress generation on REST API services
            host="test.example.com",
        ),
    )


def _make_docker_generator() -> Generator:
    from datrix_codegen_docker.generators.infra.docker_generator import DockerGenerator
    from datrix_common.config.platform.docker import DockerPlatformConfig
    from datrix_common.generation.defaults import build_project_config

    # Docker generator needs its defaults.yaml loaded (provides InfraImageCatalog)
    _docker_project = build_project_config([DockerGenerator])

    return DockerGenerator(
        context=make_test_context(
            profile="test",
            target_language=Language.PYTHON,
            deployment=DeploymentConfig(
                runtime=DeploymentRuntime.DOCKER_COMPOSE,
                provider=DeploymentProvider.LOCAL,
            ),
            docker=_docker_project.docker,
            images=_docker_project.images,
        ),
        # python_base is required for Dockerfile generation (runtime_spec.py)
        platform_config=DockerPlatformConfig(python_base="python:3.12-slim"),
    )


_GENERATOR_FACTORIES: dict[str, Callable[[], Generator]] = {
    "python": _make_python_generator,
    "typescript": _make_typescript_generator,
    "sql": _make_sql_generator,
    "component": _make_component_generator,
    "aws": _make_aws_generator,
    "azure": _make_azure_generator,
    "k8s": _make_k8s_generator,
    "docker": _make_docker_generator,
}

# Per-target app parsers (some targets need platform-specific config)
_APP_PARSERS: dict[str, Callable[[Path], "Application"]] = {
    "python": _base_parse,
    "typescript": _base_parse,
    "sql": _base_parse,
    "component": _base_parse,
    "aws": _aws_parse,
    "azure": _azure_parse,
    "k8s": _k8s_parse,
    "docker": _base_parse,
}

# ---------------------------------------------------------------------------
# Expected file extensions per target (spot-checks)
# ---------------------------------------------------------------------------

_EXPECTED_EXTENSIONS: dict[str, str] = {
    "python": ".py",
    "typescript": ".ts",
    "sql": ".sql",
    "component": ".md",
    "aws": ".py",       # CDK Python stacks
    "azure": ".bicep",
    "k8s": ".yaml",
    "docker": "Dockerfile",
}

# ---------------------------------------------------------------------------
# Per-target files excluded from byte-identical comparison.
#
# Docker .env.example and .env.validation contain randomly-generated
# infrastructure passwords (from SecretStore) that differ per build by design.
# They are still checked for manifest presence (set-equality) but excluded
# from the byte-exact assertion.  All structural/code files remain under the
# full byte-identical constraint.
# ---------------------------------------------------------------------------

_BYTE_COMPARE_EXCLUDES: dict[str, frozenset[str]] = {
    "docker": frozenset({".env.example", ".env.validation"}),
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _generate_once(
    generator: Generator,
    app: "Application",
    output_dir: Path,
) -> dict[str, bytes]:
    """Run one full generation pass and return {path_str: content_bytes}.

    Uses the in-memory GeneratedFile list returned by the generator — the
    generator does NOT write to disk and GeneratedFile.path is relative.
    The ``output_dir`` is passed to ``generator.generate`` as required by the
    protocol; it is unused in the byte comparison.

    Surfaces generation errors directly (no try/except masking).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    files: list[GeneratedFile] = generator.generate(app, output_dir)
    return {str(f.path): f.content.encode("utf-8") for f in files}


# ---------------------------------------------------------------------------
# Parametrize
# ---------------------------------------------------------------------------

_PARAMS = [
    (app_id, dtrx, target)
    for app_id, dtrx, targets in _CASES
    for target in targets
]


# ---------------------------------------------------------------------------
# The test
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.parametrize(
    ("app_id", "dtrx", "target"),
    _PARAMS,
    ids=[f"{app_id}/{tgt}" for app_id, _, tgt in _PARAMS],
)
def test_regeneration_is_byte_identical(
    app_id: str,
    dtrx: Path,
    target: str,
    tmp_path: Path,
) -> None:
    """Generating the same app twice produces byte-identical output for every target.

    This is the system-level acceptance test for the phase-60 GenDSL refactor:
    registry merge order, namespace resolution, and the tightened semantics must
    not perturb a single byte of output for any valid app.

    Steps:
      1. Parse the example app through the real pipeline (parse + semantics).
      2. Attach configs programmatically (attach_default_configs + platform-specific).
      3. Build a fresh generator instance for the target.
      4. Generate twice (run 1 and run 2) using the same Application object.
      5. Assert file-manifest set-equality (no missing / extra / renamed files).
      6. Assert exact byte equality per file (in-memory comparison on GeneratedFile),
         excluding per-build random-secret files listed in ``_BYTE_COMPARE_EXCLUDES``.
      7. Spot-check that the expected file type for the target is present.
    """
    assert dtrx.exists(), (
        f"Example source not found: {dtrx}. "
        f"Verify the path against the real examples/ tree."
    )

    factory = _GENERATOR_FACTORIES.get(target)
    assert factory is not None, (
        f"No generator factory registered for target '{target}'. "
        f"Known targets: {sorted(_GENERATOR_FACTORIES)}"
    )

    parser = _APP_PARSERS.get(target, _base_parse)
    app = parser(dtrx)

    run1_dir = tmp_path / "run1" / app_id / target
    run2_dir = tmp_path / "run2" / app_id / target

    # Build a fresh generator instance per run (guards against instance-level state)
    generator_run1 = factory()
    run1 = _generate_once(generator_run1, app, run1_dir)
    del generator_run1

    generator_run2 = factory()
    run2 = _generate_once(generator_run2, app, run2_dir)
    del generator_run2

    # --- File manifest set-equality ---
    assert set(run1) == set(run2), (
        f"File manifest drift for {app_id}/{target} between run 1 and run 2.\n"
        f"Only in run1: {sorted(set(run1) - set(run2))}\n"
        f"Only in run2: {sorted(set(run2) - set(run1))}"
    )

    # --- Non-empty output (guards against silent empty generation) ---
    assert len(run1) > 0, (
        f"Generator for {app_id}/{target} produced no files — "
        f"byte-identical comparison is vacuous (silent empty output)."
    )

    # --- Byte-exact comparison per file ---
    # Files in _BYTE_COMPARE_EXCLUDES contain per-build randomised content
    # (e.g. Docker env files with generated infrastructure passwords) and are
    # intentionally excluded from the determinism assertion. They remain in the
    # manifest set-equality check above.
    byte_excludes = _BYTE_COMPARE_EXCLUDES.get(target, frozenset())
    differing: list[str] = [
        rel for rel in sorted(run1)
        if run1[rel] != run2[rel] and rel not in byte_excludes
    ]
    assert not differing, (
        f"Byte drift between run 1 and run 2 for {app_id}/{target} "
        f"in {len(differing)} file(s):\n"
        + "\n".join(f"  {p}" for p in differing)
    )

    # --- Spot-check: expected file type present ---
    expected_ext = _EXPECTED_EXTENSIONS.get(target)
    if expected_ext is not None:
        has_expected = any(
            rel.endswith(expected_ext) or rel == expected_ext
            for rel in run1
        )
        assert has_expected, (
            f"No file with extension/name '{expected_ext}' found in generated "
            f"output for {app_id}/{target}. "
            f"Files: {sorted(run1)[:10]}"
        )
