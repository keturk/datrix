"""Deployment-static bootstrap constants. Auto-generated. Do not edit.

Baked at generation time from the resolved deployment. NOTHING here is read from
the environment at runtime.
"""

from __future__ import annotations

from typing import Final

PROVIDER: Final[str] = "local"
CREDENTIAL_KIND: Final[str] = "mounted-file"
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
