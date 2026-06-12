"""Shared helpers for the identity multi-target tests (task 69-24).

Loads the runnable identity example (``examples/.../identity``) and its provider
``.dcfg`` files into real objects (no mocks):

- ``load_example_app`` parses + semantically analyses the example, returning the
  validated :class:`Application` with its hoisted ``identity`` block.
- ``load_committed_configs`` reads the three committed provider ``.dcfg`` files
  (Keycloak / external mode — valid on every target) into ``IdentityConfig``.
- ``collect_auth_contracts`` returns the deduplicated effective auth contracts
  for the example's REST surfaces (used to drive the shared identity planner).

The committed configs use Keycloak in ``external`` mode so the *same example*
parses and validates for every deployment target.  Tests that exercise a
target's native provisioning path (Docker/K8s Keycloak realms, AWS Cognito,
Azure Entra) substitute target-appropriate configs via the ``*_configs``
factories below — the example AST (providers, surfaces, role mappings) is shared.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from datrix_common.config.datasource.identity_config import IdentityConfig
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
from datrix_common.datrix_model.auth_contract import AuthContract
from datrix_common.datrix_model.containers import Application
from datrix_common.datrix_model.enumeration import enumerate_rest_endpoints
from datrix_common.testing.fixtures import attach_default_configs
from datrix_common.testing.parsing import parse_fixture_with_semantics

# ---------------------------------------------------------------------------
# Example location
# ---------------------------------------------------------------------------

EXAMPLE_DIR: Path = (
    Path(__file__).resolve().parents[3]
    / "examples"
    / "02-features"
    / "01-core-data-modeling"
    / "identity"
)
SYSTEM_DTRX: Path = EXAMPLE_DIR / "system.dtrx"
IDENTITY_CONFIG_DIR: Path = EXAMPLE_DIR / "config" / "identity"

#: Logical provider names declared in the example identity block.
PROVIDER_NAMES: tuple[str, ...] = ("customer", "workforce", "platformMachine")


# ---------------------------------------------------------------------------
# Example loading
# ---------------------------------------------------------------------------


def load_example_app() -> Application:
    """Parse + semantically analyse the identity example.

    Returns:
        The validated Application with its ``identity`` block populated.
    """
    app = parse_fixture_with_semantics(SYSTEM_DTRX)
    if app.identity is None:
        raise AssertionError(
            "identity example lost its identity block during parsing — "
            "the include-merge must hoist app.identity"
        )
    return app


def load_example_app_with_infra(*, full_service_profile: bool = False) -> Application:
    """Parse the example and attach default infra configs for platform targets.

    Docker/K8s/Azure generators read ``block.config`` for the rdbms block and
    the service deployment profile, which test-parsed apps lack.  This attaches
    defaults so those generators can run against the example.

    Args:
        full_service_profile: When True, replace the service config with a full
            K8s deployment profile (replicas/resources/healthCheck/readiness/
            scaling) that the K8s manifest builder requires.

    Returns:
        The validated Application with infra configs attached.
    """
    app = load_example_app()
    attach_default_configs(app)
    if full_service_profile:
        for idx, svc in enumerate(app.services.values()):
            svc.config = _K8S_PROFILE(8000 + idx)
    return app


def _K8S_PROFILE(port: int) -> ServiceConfigProfileConfig:
    return ServiceConfigProfileConfig(
        port=port,
        replicas=2,
        resources=ResourceConfig(
            requests=ResourceSpec(cpu="100m", memory="128Mi"),
            limits=ResourceSpec(cpu="500m", memory="512Mi"),
        ),
        healthCheck=HealthCheckConfig(path="/health", initialDelay="15s", period="20s"),
        readinessCheck=ReadinessCheckConfig(
            type="http", path="/health", initialDelay="5s", period="10s"
        ),
        scaling=ScalingConfig(
            replicas=ScalingReplicas(min=2, max=10),
            triggers=[
                ScalingTrigger(metric="cpu", target=70),
                ScalingTrigger(metric="memory", target=80),
            ],
        ),
    )


def load_committed_configs() -> dict[str, IdentityConfig]:
    """Load the three committed provider ``.dcfg`` files into IdentityConfig.

    Returns:
        Map of logical provider name → resolved IdentityConfig (Keycloak,
        external mode).
    """
    return {
        "customer": _load_dcfg(IDENTITY_CONFIG_DIR / "customer.dcfg"),
        "workforce": _load_dcfg(IDENTITY_CONFIG_DIR / "workforce.dcfg"),
        "platformMachine": _load_dcfg(IDENTITY_CONFIG_DIR / "platform-machine.dcfg"),
    }


def committed_config_paths() -> list[Path]:
    """Return the on-disk paths of the committed provider ``.dcfg`` files."""
    return sorted(IDENTITY_CONFIG_DIR.glob("*.dcfg"))


def _load_dcfg(path: Path) -> IdentityConfig:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return IdentityConfig.model_validate(data)


def collect_auth_contracts(app: Application) -> tuple[AuthContract, ...]:
    """Collect deduplicated effective AuthContracts across the example surfaces."""
    seen: set[str] = set()
    contracts: list[AuthContract] = []
    for ownership in enumerate_rest_endpoints(app):
        contract = ownership.endpoint.auth_contract
        if contract.surface_id in seen:
            continue
        seen.add(contract.surface_id)
        contracts.append(contract)
    return tuple(contracts)


def owning_service(app: Application) -> Any:
    """Return the single service that owns the identity block."""
    services = list(app.services.values())
    if len(services) != 1:
        raise AssertionError(
            "identity example must have exactly one service; got %d" % len(services)
        )
    return services[0]


# ---------------------------------------------------------------------------
# Target-specific provider config factories (share the example AST)
# ---------------------------------------------------------------------------

_CUSTOMER_GROUPS = {"premium-buyers": "premiumCustomer"}
_WORKFORCE_GROUPS = {"catalog-admins": "catalogAdmin"}
_MACHINE_GROUPS = {"service-writers": "orderWriter"}


def keycloak_platform_default_configs() -> dict[str, IdentityConfig]:
    """Keycloak configs for the Docker/K8s native-realm artifact path.

    Keycloak is application-level: exactly ONE provider may provision the realm
    (``mode=platformDefault``); the others federate as ``external``.  The
    ``customer`` provider owns the provisioned realm here; ``workforce`` and
    ``platformMachine`` are external.  Role mappings for all three providers
    still flow into the plan (and the realm role set) from the example's group
    mappings — only realm/server provisioning is single-provider.
    """
    return {
        "customer": _keycloak_config(
            audience="customer",
            realm="shop-customers",
            issuer="https://auth.shop.example.com/realms/shop-customers",
            mode="platformDefault",
            with_public_client=True,
        ),
        "workforce": _keycloak_config(
            audience="workforce",
            realm="shop-staff",
            issuer="https://auth.shop.example.com/realms/shop-staff",
            mode="external",
            with_public_client=True,
        ),
        "platformMachine": _keycloak_config(
            audience="machine",
            realm="shop-machines",
            issuer="https://auth.shop.example.com/realms/shop-machines",
            mode="external",
            with_public_client=False,
        ),
    }


def cognito_configs() -> dict[str, IdentityConfig]:
    """AWS Cognito configs for the AWS artifact path.

    Cognito is application-level: exactly ONE provider provisions the User Pool
    (``mode=platformDefault``); the others are ``external`` (federated identity
    providers / pre-existing pools).  ``customer`` owns the pool here.
    """
    return {
        "customer": _cognito_config(audience="customer", mode="platformDefault"),
        "workforce": _cognito_config(audience="workforce", mode="external"),
        "platformMachine": _cognito_config(
            audience="machine", mode="external", with_public_client=False
        ),
    }


def entra_configs() -> dict[str, IdentityConfig]:
    """Azure Entra configs: customer -> Entra External ID, workforce -> Entra ID."""
    return {
        "customer": _entra_external_config(),
        "workforce": _entra_id_config(),
        "platformMachine": _entra_id_machine_config(),
    }


# ---------------------------------------------------------------------------
# Provider config builders (real IdentityConfig, secret refs only)
# ---------------------------------------------------------------------------


def _groups_for(audience: str) -> dict[str, str]:
    if audience == "customer":
        return _CUSTOMER_GROUPS
    if audience == "workforce":
        return _WORKFORCE_GROUPS
    return _MACHINE_GROUPS


def _keycloak_config(
    *,
    audience: str,
    realm: str,
    issuer: str,
    mode: str,
    with_public_client: bool,
) -> IdentityConfig:
    name = audience.upper()
    data: dict[str, Any] = {
        "provider": "keycloak",
        "audience": audience,
        "mode": mode,
        "issuer": issuer,
        "clientId": "shop-%s" % audience,
        "clientSecret": {"provider": "env", "name": "IDENTITY_%s_CLIENT_SECRET" % name},
        "keycloak": {
            "realm": realm,
            "host": "auth.shop.example.com",
            "port": 8443,
            "adminUser": "admin",
            "adminPassword": {
                "provider": "env",
                "name": "IDENTITY_%s_ADMIN_PASSWORD" % name,
            },
            "dbEngine": "postgres",
        },
        "roleSource": {"claimPath": "realm_access.roles", "guarantee": "optional"},
    }
    if with_public_client:
        data["publicClient"] = {
            "baseUrls": {
                "test": "https://shop.example.com",
                "production": "https://shop.example.com",
            },
            "flows": ["authorization_code"],
        }
    if audience == "customer":
        data["profileProjection"] = {
            "enabled": True,
            "fields": {
                "email": {"source": "email", "owner": "provider", "syncPolicy": "syncOnAuth"},
            },
        }
    return IdentityConfig.model_validate(data)


def _cognito_config(
    *, audience: str, mode: str = "platformDefault", with_public_client: bool = True
) -> IdentityConfig:
    name = audience.upper()
    data: dict[str, Any] = {
        "provider": "cognito",
        "audience": audience,
        "mode": mode,
        "issuer": "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_%s" % audience,
        "clientId": "shop-%s-client" % audience,
        "clientSecret": {
            "provider": "aws-secrets-manager",
            "name": "identity/%s-client-secret" % audience,
        },
        "cognito": {"region": "us-east-1"},
        "roleSource": {"claimPath": "cognito:groups", "guarantee": "optional"},
    }
    if with_public_client:
        data["publicClient"] = {
            "baseUrls": {
                "test": "https://shop.example.com",
                "production": "https://shop.example.com",
            },
            "flows": ["authorization_code"],
        }
    if audience == "customer":
        data["profileProjection"] = {
            "enabled": True,
            "fields": {
                "email": {"source": "email", "owner": "provider", "syncPolicy": "syncOnAuth"},
            },
        }
    _ = name
    return IdentityConfig.model_validate(data)


def _entra_external_config() -> IdentityConfig:
    return IdentityConfig.model_validate(
        {
            "provider": "entra-external-id",
            "audience": "customer",
            "mode": "platformDefault",
            "issuer": "https://shop.ciamlogin.com/tenant-ext/v2.0",
            "clientId": "shop-customer-app",
            "clientSecret": {"provider": "azure-key-vault", "name": "customer-client-secret"},
            "entraExternalId": {"tenantId": "tenant-ext"},
            "publicClient": {
                "baseUrls": {
                    "test": "https://shop.example.com",
                    "production": "https://shop.example.com",
                },
                "flows": ["authorization_code"],
            },
        }
    )


def _entra_id_config() -> IdentityConfig:
    return IdentityConfig.model_validate(
        {
            "provider": "entra-id",
            "audience": "workforce",
            "mode": "platformDefault",
            "issuer": "https://login.microsoftonline.com/tenant-abc/v2.0",
            "clientId": "shop-backoffice-app",
            "clientSecret": {"provider": "azure-key-vault", "name": "workforce-client-secret"},
            "entraId": {"tenantId": "tenant-abc"},
            "publicClient": {
                "baseUrls": {
                    "test": "https://backoffice.shop.example.com",
                    "production": "https://backoffice.shop.example.com",
                },
                "flows": ["authorization_code"],
            },
        }
    )


def _entra_id_machine_config() -> IdentityConfig:
    return IdentityConfig.model_validate(
        {
            "provider": "entra-id",
            "audience": "machine",
            "mode": "platformDefault",
            "issuer": "https://login.microsoftonline.com/tenant-abc/v2.0",
            "clientId": "shop-service-app",
            "clientSecret": {"provider": "azure-key-vault", "name": "machine-client-secret"},
            "entraId": {"tenantId": "tenant-abc"},
        }
    )


# ---------------------------------------------------------------------------
# Raw-secret detection
# ---------------------------------------------------------------------------

#: Substrings that would indicate a raw secret leaked into a generated artifact.
RAW_SECRET_MARKERS: tuple[str, ...] = (
    "BEGIN PRIVATE KEY",
    "BEGIN RSA PRIVATE KEY",
    "-----BEGIN",
)
