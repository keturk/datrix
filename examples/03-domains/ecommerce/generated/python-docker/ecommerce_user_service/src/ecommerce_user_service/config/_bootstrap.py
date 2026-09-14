"""Deployment-static bootstrap constants. Auto-generated. Do not edit.

Baked at generation time from the resolved deployment. NOTHING here is read from
the environment at runtime.
"""

from __future__ import annotations

from typing import Final

PROVIDER: Final[str] = "local"
CREDENTIAL_KIND: Final[str] = "mounted-file"

#: The deployment profile this service was generated for. This is the service's
#: own environment identity -- what its app name, its startup log line and every
#: structured log record's `env` field report.
PROFILE: Final[str] = "test"

#: The CONFIG-STORE namespace, not the deployment identity: the label the config
#: store partitions its keys under, and part of the config-store / secrets-store
#: resource names on the platforms that derive them. Read by the config-store
#: backends and by nothing else. A .dcfg normally declares `configStore` once in
#: `base`, so several profiles legitimately share this value -- which is exactly
#: why PROFILE above exists separately.
ENVIRONMENT: Final[str] = "dev"
REGION: Final[str | None] = None
CONFIG_STORE_ENDPOINT: Final[str | None] = None
SECRETS_STORE_ENDPOINT: Final[str | None] = None
SECRET_PREFIX: Final[str] = ""
CONFIG_FILE_PATH: Final[str | None] = "/app/config/config-store.json"
SECRETS_DIR_PATH: Final[str | None] = "/run/secrets"
CREDENTIAL_FILE_PATH: Final[str | None] = "/run/credentials/service-credential.json"
IDENTITY_PROVIDER_PLAN_PATH: Final[str | None] = (
    "/app/config/identity/identity-providers.json"
)
