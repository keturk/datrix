"""Application settings assembled at startup. Auto-generated. Do not edit.

Assembled from baked bootstrap constants, config-store values, and resolved
secrets at service startup.  All connection strings are composed here from
non-secret parts (host/port/db from the config store ``connections``
namespace) and credential parts (password from the secrets backend).

The only environment reads in this module are the trusted-caller settings
(Azure runtime path + managed gateway, via ``_require_env``) -- deploy-time ARM
outputs delivered as Azure Web App Application Settings, static for the
deployment's lifetime. A service that only CALLS peers reads the audience alone;
the issuer and trusted-principal allowlist are read only by a service that
validates inbound callers. Every other field is read from the config store or the
secrets backend, never the environment.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from library_book_service.config import _bootstrap

# ---------------------------------------------------------------------------
# Baked security / middleware constants (authored from service config at
# code-generation time; no environment reads).
# ---------------------------------------------------------------------------
DEBUG: bool = False
ALLOWED_HOSTS: list[str] = ["book-service.example.com", "localhost"]
CORS_ORIGINS: list[str] = ["https://app.example.com"]
CORS_METHODS: list[str] = ["GET", "POST", "PATCH", "DELETE", "OPTIONS"]
CORS_HEADERS: list[str] = ["Authorization", "Content-Type"]

# ---------------------------------------------------------------------------
# Baked DB pool constants (authored from service config at generation time).
# ---------------------------------------------------------------------------
DB_POOL_SIZE: int = 20
DB_MAX_OVERFLOW: int = 20

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AppSettings:
    """Frozen application settings assembled at startup.

    Fields are populated once during the lifespan ``startup`` phase via
    :func:`assemble_settings`.  No import-time construction occurs; any module
    that needs settings must call :func:`get_settings` after startup has run.
    """

    app_name: str
    environment: str
    host: str
    port: int
    book_db_host: str
    book_db_port: int
    book_db_database: str
    book_db_user: str
    book_db_async_driver: str
    book_db_password_handle: str
    db_pool_size: int
    db_max_overflow: int
    bootstrap_servers: str


_settings: AppSettings | None = None


def get_settings() -> AppSettings:
    """Return the assembled AppSettings.  Raises if called before startup."""
    if _settings is None:
        raise RuntimeError(
            "AppSettings have not been assembled yet. "
            "Call assemble_settings() during the lifespan startup phase before "
            "accessing settings. Ensure the startup lifespan handler runs before "
            "any request handler or background task that calls get_settings()."
        )
    return _settings


async def assemble_settings(
    config_client: object,
    secrets: object,
) -> AppSettings:
    """Assemble AppSettings from bootstrap, config store, and secrets.

    Fails loud (raises ``RuntimeError``) when any required namespace key or
    secret handle is absent.  No environment variables are read.

    Args:
        config_client: ``RemoteConfigClient`` instance (from ``config.remote_config``).
        secrets: ``_secrets_resolver`` module for resolving secret handles.

    Returns:
        Populated :class:`AppSettings` instance.

    Raises:
        RuntimeError: When a required config-store key or secret is absent.
    """
    from library_book_service.config.remote_config import ConnectionsKeys

    _book_db_host = config_client.get_string(
        ConnectionsKeys.NAMESPACE, ConnectionsKeys.BOOK_DB_HOST
    )
    _book_db_port = config_client.get_int(
        ConnectionsKeys.NAMESPACE, ConnectionsKeys.BOOK_DB_PORT
    )
    _book_db_database = config_client.get_string(
        ConnectionsKeys.NAMESPACE, ConnectionsKeys.BOOK_DB_DATABASE
    )
    _book_db_user = config_client.get_string(
        ConnectionsKeys.NAMESPACE, ConnectionsKeys.BOOK_DB_USER
    )
    bootstrap_servers = config_client.get_string(
        ConnectionsKeys.NAMESPACE, ConnectionsKeys.MQ_BROKERS
    )

    global _settings
    _settings = AppSettings(
        app_name=_bootstrap.ENVIRONMENT + "-library_book_service",
        environment=_bootstrap.ENVIRONMENT,
        host="0.0.0.0",
        port=8000,
        book_db_host=_book_db_host,
        book_db_port=_book_db_port,
        book_db_database=_book_db_database,
        book_db_user=_book_db_user,
        book_db_async_driver="postgresql+asyncpg",
        book_db_password_handle="book_db_password",
        db_pool_size=20,
        db_max_overflow=20,
        bootstrap_servers=bootstrap_servers,
    )
    logger.info("app_settings_assembled environment=%s", _bootstrap.ENVIRONMENT)
    return _settings
