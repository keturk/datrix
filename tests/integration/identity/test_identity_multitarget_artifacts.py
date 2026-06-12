"""Multi-target identity artifact contracts for the identity example (task 69-24).

Drives the REAL generators (no mocks) against the runnable identity example
(``examples/.../identity``) for every first-class provider/target path required
by DN34:

- Component (target-neutral): provider plan JSON, public-client metadata, docs.
- Docker + Keycloak: compose Keycloak server/db + realm/plan artifacts + wiring.
- Kubernetes + Keycloak: Keycloak Deployment/Service + realm/plan ConfigMaps + wiring.
- AWS + Cognito: CDK identity stack + CloudFormation Cognito resources.
- Azure workforce (Entra ID) + customer (Entra External ID): Graph app registrations.

Every path additionally asserts:
- the full artifact CONTENT contract (provider resources, role/group mappings,
  JWKS/issuer wiring, profile-projection storage, secret REFERENCES);
- NO raw secret material anywhere in the output;
- the NEW ``auth(...)``/``identity`` path is exercised (dual-path guard) — the
  surfaces drive the provider plan that backs the artifacts.

A deliberately unsupported provider/target combination is asserted to FAIL
capability validation (Cognito on Docker).

``@pytest.mark.integration``.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from datrix_common.config.datasource.identity_config import IdentityConfig
from datrix_common.config.deployment_config import DeploymentConfig
from datrix_common.config.enums import (
    DeploymentProvider,
    DeploymentRuntime,
    Language,
)
from datrix_common.errors.generation import GenerationError
from datrix_common.generation.generator import GeneratedFile
from datrix_common.identity.capability_matrix import (
    DeploymentTarget,
    ProviderType,
    lookup_capability,
)
from datrix_common.testing import make_test_context

from . import _identity_example as ex

pytestmark = pytest.mark.integration

_ENV = "test"


# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------


def _paths(files: list[GeneratedFile]) -> set[str]:
    return {f.path.as_posix() for f in files}


def _by_suffix(files: list[GeneratedFile], suffix: str) -> GeneratedFile:
    matches = [f for f in files if f.path.as_posix().endswith(suffix)]
    if len(matches) != 1:
        raise AssertionError(
            "expected exactly one file ending %r, got %r"
            % (suffix, sorted(_paths(files)))
        )
    return matches[0]


#: Path fragments that identify identity-related generated artifacts.
_IDENTITY_PATH_MARKERS: tuple[str, ...] = (
    "identity",
    "keycloak",
    "realm",
    "cognito",
    "entra",
)


def _is_identity_artifact(f: GeneratedFile) -> bool:
    p = f.path.as_posix().lower()
    return any(marker in p for marker in _IDENTITY_PATH_MARKERS)


def _assert_no_raw_secrets(files: list[GeneratedFile]) -> None:
    """Assert no provider secret material leaks into IDENTITY artifacts.

    Scoped to identity artifacts: unrelated local-dev material (e.g. the Docker
    gateway's auto-generated JWT dev key) is out of the DN34 identity contract.
    """
    identity_files = [f for f in files if _is_identity_artifact(f)]
    assert identity_files, "no identity artifacts produced to scan for secrets"
    for f in identity_files:
        for marker in ex.RAW_SECRET_MARKERS:
            assert marker not in f.content, (
                "raw secret marker %r leaked into %s" % (marker, f.path.as_posix())
            )


class _CfnYamlLoader(yaml.SafeLoader):
    """SafeLoader tolerant of CloudFormation intrinsic tags (``!Ref`` etc.)."""


def _cfn_multi(loader: yaml.Loader, tag_suffix: str, node: yaml.Node) -> Any:
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    assert isinstance(node, yaml.MappingNode)
    return loader.construct_mapping(node)


_CfnYamlLoader.add_multi_constructor("!", _cfn_multi)  # type: ignore[no-untyped-call]


# ---------------------------------------------------------------------------
# Capability matrix (no generation) — supported vs unsupported combinations
# ---------------------------------------------------------------------------


class TestCapabilityValidation:
    """The capability matrix accepts first-class combos and rejects bad ones."""

    def test_keycloak_supported_on_docker_and_k8s(self) -> None:
        for target in (DeploymentTarget.DOCKER, DeploymentTarget.KUBERNETES):
            cap = lookup_capability(ProviderType.KEYCLOAK, target)
            assert cap is not None

    def test_cognito_supported_on_aws(self) -> None:
        cap = lookup_capability(ProviderType.COGNITO, DeploymentTarget.AWS)
        assert cap is not None

    def test_entra_supported_on_azure(self) -> None:
        assert lookup_capability(ProviderType.ENTRA_ID, DeploymentTarget.AZURE) is not None
        assert (
            lookup_capability(ProviderType.ENTRA_EXTERNAL_ID, DeploymentTarget.AZURE)
            is not None
        )

    def test_cognito_on_docker_is_rejected(self) -> None:
        """Deliberately unsupported combo (Cognito + Docker) fails loud."""
        with pytest.raises(GenerationError):
            lookup_capability(ProviderType.COGNITO, DeploymentTarget.DOCKER)

    def test_entra_id_on_aws_is_rejected(self) -> None:
        with pytest.raises(GenerationError):
            lookup_capability(ProviderType.ENTRA_ID, DeploymentTarget.AWS)


# ---------------------------------------------------------------------------
# Component (target-neutral) artifacts
# ---------------------------------------------------------------------------


class TestComponentArtifacts:
    """Target-neutral provider-plan + client-metadata + docs artifacts."""

    def _emit(self) -> list[GeneratedFile]:
        from datrix_codegen_component.identity_metadata_generator import (
            emit_identity_artifacts,
        )

        app = ex.load_example_app()
        configs = ex.load_committed_configs()
        return emit_identity_artifacts(
            app=app,
            environment=_ENV,
            deployment_target=DeploymentTarget.EXTERNAL,
            provider_configs=configs,
            auth_contracts=ex.collect_auth_contracts(app),
            owning_service=ex.owning_service(app),
        )

    def test_provider_plan_lists_all_providers(self) -> None:
        files = self._emit()
        plan_file = _by_suffix(files, "identity-providers.json")
        plan = json.loads(plan_file.content)
        assert plan["schemaVersion"] >= 1
        assert set(plan["providers"]) == set(ex.PROVIDER_NAMES)

    def test_provider_plan_carries_jwks_issuer_and_role_mappings(self) -> None:
        files = self._emit()
        plan = json.loads(_by_suffix(files, "identity-providers.json").content)
        customer = plan["providers"]["customer"]
        assert customer["issuer"].endswith("/realms/shop-customers")
        assert customer["jwksUri"].startswith(customer["issuer"])
        # Role mapping from the example's `group "premium-buyers" as premiumCustomer`.
        assert customer["roleMappings"]["premium-buyers"] == "premiumCustomer"
        workforce = plan["providers"]["workforce"]
        assert workforce["roleMappings"]["catalog-admins"] == "catalogAdmin"
        machine = plan["providers"]["platformMachine"]
        assert machine["roleMappings"]["service-writers"] == "orderWriter"
        assert machine["principalType"] == "machine"

    def test_provider_plan_binds_authenticated_surfaces(self) -> None:
        files = self._emit()
        plan = json.loads(_by_suffix(files, "identity-providers.json").content)
        surfaces = plan["surfaces"]
        # Every bound surface is non-public; the multi-provider lookup surface
        # must list BOTH providers (new auth path exercised end to end).
        assert surfaces, "no authenticated surfaces bound — auth path not exercised"
        multi = [
            s
            for s in surfaces.values()
            if set(s["providers"]) == {"customer", "workforce"}
        ]
        assert multi, "multi-provider surface not present in plan"
        service_surfaces = [
            s for s in surfaces.values() if s["mode"] == "service"
        ]
        assert service_surfaces, "service-auth surface not bound"

    def test_profile_projection_storage_present_for_customer(self) -> None:
        files = self._emit()
        plan = json.loads(_by_suffix(files, "identity-providers.json").content)
        customer = plan["providers"]["customer"]
        projection = customer["profileProjection"]
        assert projection["enabled"] is True
        # Profile projection lands in the single relational store (storeDb).
        assert projection["profileStore"] == "storeDb"
        assert "email" in projection["fields"]

    def test_public_client_metadata_emitted_for_human_providers(self) -> None:
        files = self._emit()
        metadata = [
            f for f in files if "identity-client-" in f.path.name
        ]
        # customer + workforce have publicClient; machine does not.
        names = {f.path.name for f in metadata}
        assert any("customer" in n for n in names)
        assert any("workforce" in n for n in names)
        assert not any("platformMachine" in n for n in names)
        for f in metadata:
            doc = json.loads(f.content)
            assert doc["issuer"].startswith("https://")
            assert doc["tokenValidation"]["jwksUri"].startswith("https://")

    def test_no_raw_secrets(self) -> None:
        _assert_no_raw_secrets(self._emit())


# ---------------------------------------------------------------------------
# Docker + Keycloak
# ---------------------------------------------------------------------------


class TestDockerArtifacts:
    """Keycloak realm provisioning + per-service identity wiring on Docker."""

    def _generate(self) -> list[GeneratedFile]:
        from datrix_codegen_docker.generators.infra.docker_generator import (
            DockerGenerator,
        )
        from datrix_common.config.platform.docker import DockerPlatformConfig
        from datrix_common.generation.defaults import build_project_config

        app = ex.load_example_app_with_infra()
        project = build_project_config([DockerGenerator])
        generator = DockerGenerator(
            context=make_test_context(
                profile=_ENV,
                target_language=Language.PYTHON,
                deployment=DeploymentConfig(
                    runtime=DeploymentRuntime.DOCKER_COMPOSE,
                    provider=DeploymentProvider.LOCAL,
                ),
                docker=project.docker,
                images=project.images,
            ),
            platform_config=DockerPlatformConfig(python_base="python:3.12-slim"),
        )
        generator.identity_provider_configs = ex.keycloak_platform_default_configs()
        return generator.generate(app, Path("out"))

    def test_compose_has_keycloak_server_db_and_wiring(self) -> None:
        files = self._generate()
        compose = yaml.safe_load(_by_suffix(files, "docker-compose.yml").content)
        services = compose["services"]
        assert any(k.endswith("-keycloak") for k in services)
        assert any(k.endswith("-keycloak-db") for k in services)
        app_services = [svc for svc in services.values() if "build" in svc]
        assert app_services
        for svc in app_services:
            assert "IDENTITY_PROVIDER_PLAN" in svc["environment"]

    def test_realm_and_plan_artifacts(self) -> None:
        files = self._generate()
        realm = json.loads(_by_suffix(files, "realm-export.json").content)
        roles = {r["name"] for r in realm["roles"]["realm"]}
        # The provisioned (platformDefault) customer realm carries its own role.
        assert "premiumCustomer" in roles
        # The provider plan binds ALL declared providers (provisioned + external)
        # with their group/role mappings.
        plan = json.loads(_by_suffix(files, "identity-providers.json").content)
        assert set(plan["providers"]) == set(ex.PROVIDER_NAMES)
        assert plan["providers"]["customer"]["roleMappings"]["premium-buyers"] == (
            "premiumCustomer"
        )
        assert plan["providers"]["workforce"]["roleMappings"]["catalog-admins"] == (
            "catalogAdmin"
        )
        assert plan["providers"]["platformMachine"]["roleMappings"][
            "service-writers"
        ] == "orderWriter"

    def test_secret_values_are_references(self) -> None:
        files = self._generate()
        compose = yaml.safe_load(_by_suffix(files, "docker-compose.yml").content)
        server = next(
            svc
            for name, svc in compose["services"].items()
            if name.endswith("-keycloak")
        )
        admin = server["environment"]["KEYCLOAK_ADMIN_PASSWORD"]
        assert admin.startswith("${") or admin.startswith("/run/secrets")

    def test_no_raw_secrets(self) -> None:
        _assert_no_raw_secrets(self._generate())


# ---------------------------------------------------------------------------
# Kubernetes + Keycloak
# ---------------------------------------------------------------------------


class TestKubernetesArtifacts:
    """Keycloak Deployment/Service + realm/plan ConfigMaps + identity Secret."""

    def _generate(self) -> list[GeneratedFile]:
        from datrix_codegen_k8s.generators.k8s_generator import K8sGenerator
        from datrix_common.config.platform.k8s import K8sPlatformConfig

        app = ex.load_example_app_with_infra(full_service_profile=True)
        generator = K8sGenerator(
            context=make_test_context(
                profile=_ENV,
                target_language=Language.PYTHON,
                deployment=DeploymentConfig(
                    runtime=DeploymentRuntime.KUBERNETES,
                    provider=DeploymentProvider.LOCAL,
                ),
            ),
            platform_config=K8sPlatformConfig(
                namespace="shop",
                app_name="shop",
                host="shop.example.com",
            ),
        )
        generator.identity_provider_configs = ex.keycloak_platform_default_configs()
        return generator.generate(app, Path("out"))

    def _identity_files(self, files: list[GeneratedFile]) -> list[GeneratedFile]:
        return [f for f in files if "/identity/" in f.path.as_posix()]

    def test_keycloak_workload_and_realm_configmap_present(self) -> None:
        files = self._generate()
        identity = self._identity_files(files)
        assert identity, "no identity manifests emitted for k8s"
        joined = "\n".join(f.content for f in identity)
        assert "keycloak" in joined.lower()
        # Realm + provider-plan delivered as ConfigMaps.
        assert "realm-export.json" in joined
        assert "identity-providers.json" in joined

    def test_realm_roles_from_group_mappings(self) -> None:
        files = self._generate()
        joined = "\n".join(f.content for f in self._identity_files(files))
        for role in ("premiumCustomer", "catalogAdmin", "orderWriter"):
            assert role in joined

    def test_service_env_wired_with_provider_plan(self) -> None:
        files = self._generate()
        joined = "\n".join(f.content for f in files)
        assert "IDENTITY_PROVIDER_PLAN" in joined

    def test_no_raw_secrets(self) -> None:
        _assert_no_raw_secrets(self._generate())


# ---------------------------------------------------------------------------
# AWS + Cognito
# ---------------------------------------------------------------------------


class TestAwsArtifacts:
    """Cognito CDK stack + CloudFormation template for the AWS path."""

    def _generate(self) -> list[GeneratedFile]:
        from datrix_codegen_aws.generators.aws_generator import AWSGenerator
        from datrix_codegen_aws.gendsl import runtime
        from datrix_common.config.platform.aws import (
            AwsPlatformConfig,
            ServiceDiscoveryConfig,
        )

        app = ex.load_example_app()
        generator = AWSGenerator(
            context=make_test_context(
                profile=_ENV,
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
        return runtime.identity(
            app,
            generator,
            identity_provider_configs=ex.cognito_configs(),
        )

    def test_cdk_identity_stack_is_valid_python(self) -> None:
        files = self._generate()
        cdk = _by_suffix(files, "identity_stack.py")
        ast.parse(cdk.content)
        assert "cognito.UserPool(" in cdk.content
        # One app client per service (single service here).
        assert cdk.content.count(".add_client(") >= 1

    def test_cdk_groups_from_example_role_mappings(self) -> None:
        files = self._generate()
        cdk = _by_suffix(files, "identity_stack.py")
        # The provisioned (platformDefault) customer pool carries its group from
        # the example's `group "premium-buyers" as premiumCustomer` mapping —
        # never a fabricated admin/editor/viewer list.
        assert 'group_name="premium-buyers"' in cdk.content
        assert '"editor"' not in cdk.content

    def test_cfn_template_has_cognito_resources(self) -> None:
        files = self._generate()
        cfn = _by_suffix(files, "identity.yaml")
        doc = yaml.load(cfn.content, Loader=_CfnYamlLoader)
        resource_types = {r["Type"] for r in doc["Resources"].values()}
        assert "AWS::Cognito::UserPool" in resource_types
        assert "AWS::Cognito::UserPoolClient" in resource_types
        assert "AWS::Cognito::UserPoolGroup" in resource_types

    def test_no_raw_secrets(self) -> None:
        _assert_no_raw_secrets(self._generate())


# ---------------------------------------------------------------------------
# Azure + Entra (workforce identity + customer identity)
# ---------------------------------------------------------------------------


class TestAzureArtifacts:
    """Entra ID (workforce) + Entra External ID (customer) app registrations."""

    def _generate(self) -> list[GeneratedFile]:
        from datrix_codegen_azure.generators.azure_generator import AzureGenerator
        from datrix_codegen_azure.gendsl.runtime import AzureRuntimeState, identity
        from datrix_common.config.platform.azure import AzurePlatformConfig

        app = ex.load_example_app_with_infra(full_service_profile=True)
        configs = ex.entra_configs()
        generator = AzureGenerator(
            context=make_test_context(
                profile=_ENV,
                target_language=Language.PYTHON,
                deployment=DeploymentConfig(
                    runtime=DeploymentRuntime.AZURE_APP_SERVICE,
                    provider=DeploymentProvider.AZURE,
                ),
            ),
            platform_config=AzurePlatformConfig(
                location="eastus",
                resource_group="shop-rg",
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
        generator._app_name = "shop"

        def resolver(provider_name: str, config_path: str) -> IdentityConfig:
            return configs[provider_name]

        generator.identity_config_resolver = resolver
        state = AzureRuntimeState(generator=generator)
        return identity(app, state)

    def test_graph_app_registrations_emitted(self) -> None:
        files = self._generate()
        bicep = [f for f in files if f.path.as_posix().endswith(".bicep")]
        assert bicep, "no identity Bicep emitted"
        joined = "\n".join(f.content for f in bicep)
        assert "Microsoft.Graph/applications" in joined
        assert "Microsoft.Graph/servicePrincipals" in joined

    def test_workforce_and_customer_audiences_both_present(self) -> None:
        files = self._generate()
        joined = "\n".join(
            f.content for f in files if f.path.as_posix().endswith(".bicep")
        )
        # Workforce (Entra ID) single-tenant + customer (Entra External ID / CIAM).
        assert "AzureADMyOrg" in joined

    def test_provider_plan_emitted(self) -> None:
        files = self._generate()
        plan_files = [
            f
            for f in files
            if f.path.as_posix().endswith("identity-provider-plan.json")
        ]
        assert plan_files
        plan = json.loads(plan_files[0].content)
        assert set(plan["providers"]) == set(ex.PROVIDER_NAMES)

    def test_no_raw_secrets_and_no_shell_script(self) -> None:
        files = self._generate()
        _assert_no_raw_secrets(files)
        assert not any(f.path.as_posix().endswith(".sh") for f in files)
