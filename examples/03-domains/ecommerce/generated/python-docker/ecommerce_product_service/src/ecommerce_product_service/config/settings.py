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
from types import MappingProxyType
from typing import Final, Mapping

from ecommerce_product_service.config import _bootstrap

# ---------------------------------------------------------------------------
# Baked security / middleware constants (authored from service config at
# code-generation time; no environment reads).
# ---------------------------------------------------------------------------
DEBUG: bool = False
ALLOWED_HOSTS: list[str] = ["product-service.example.com", "localhost"]
CORS_ORIGINS: list[str] = ["https://app.example.com"]
CORS_METHODS: list[str] = ["GET", "POST", "PATCH", "DELETE", "OPTIONS"]
CORS_HEADERS: list[str] = ["Authorization", "Content-Type"]

# ---------------------------------------------------------------------------
# Baked DB pool constants (authored from service config at generation time).
# ---------------------------------------------------------------------------
DB_POOL_SIZE: int = 20
DB_MAX_OVERFLOW: int = 20

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Service configuration readable from DSL logic via Config.get/getInt/getBool.
#
# Baked from the RESOLVED per-profile service config at generation time, under
# the same flat key shape the Config.* builtins compute (the DSL key
# lowercased, dots replaced by underscores). Only sections declared readable
# are present -- infrastructure blocks, the logical-secret table, and peer /
# integration wiring are deliberately absent, because their values are
# connection material and secret handles and must not appear as literals here.
# ---------------------------------------------------------------------------
CONFIG_VALUES: Final[Mapping[str, object]] = MappingProxyType(
    {
        "cacheops_keymaxlength": 100,
        "cacheops_redispoolsize": 10,
        "cacheops_ttlseconds": 300,
        "downloadops_chunksizebytes": 65536,
        "downloadops_maxretries": 3,
        "downloadops_retryablestatuscodes": [429, 500, 502, 503, 504],
        "downloadops_retrydelayseconds": 1.0,
        "downloadops_timeoutseconds": 300,
        "environment": "test",
        "kafkaops_consumerpolltimeoutms": 1000,
        "kafkaops_keepalivepolltimeoutms": 1000,
        "kafkaops_maxpollintervalms": 600000,
        "messagingops_rabbitmqprefetchcount": 10,
        "microserviceclientops_bulkheadmaxconcurrent": 10,
        "microserviceclientops_circuitbreakerfailmax": 5,
        "microserviceclientops_circuitbreakerresetseconds": 30,
        "microserviceclientops_integrationconnecttimeoutms": 1000,
        "microserviceclientops_integrationreadtimeoutms": 30000,
        "microserviceclientops_mailguntimeoutseconds": 30,
        "microserviceclientops_timeoutseconds": 300.0,
        "outboxops_flushbatchsize": 500,
        "profile": "test",
        "provider": "local",
        "queueops_servicebusmaxwaitseconds": 5,
        "queueops_sqsmaxmessagesperpoll": 10,
        "queueops_sqspollwaitseconds": 20,
        "ratelimitops_windowseconds": 60,
        "remoteconfigops_appconfigminpollseconds": 15,
        "remoteconfigops_consultimeoutseconds": 5.0,
        "retrybudgetops_ratio": 0.1,
        "retrybudgetops_window": 100,
        "servicecredentialops_tokenexpiryskewseconds": 30.0,
    }
)


# ---------------------------------------------------------------------------
# Config-key resolution
# ---------------------------------------------------------------------------
# Inlined from datrix_codegen_python/runtime/config_values.py. A pure function
# of the mapping above -- so the generator's own suite tests its fail-loud
# behaviour by calling it, rather than by executing this rendered module.
class _ConfigKeyRequired:
    """Sentinel: the DSL call supplied no default, so absence is an error."""


#: Default marker for :func:`resolve_config_value`. A distinct sentinel rather
#: than ``None``: ``None`` is a legitimate configured value and a legitimate
#: DSL-supplied default, so using it here would make "no default given" and
#: "default is null" indistinguishable.
CONFIG_REQUIRED: type[_ConfigKeyRequired] = _ConfigKeyRequired


def config_key_lookup(key: str) -> str:
    """The flat lookup name for a DSL config key.

    Mirrors what the ``Config.*`` builtins compute at generation time -- the DSL
    key lowercased, dots replaced by underscores -- so the name a call site asks
    for is the name the baked mapping carries.

    Args:
        key: The config key exactly as written in the DSL.

    Returns:
        The flat key.
    """
    return key.replace(".", "_").lower()


def resolve_config_value(
    config_values: Mapping[str, object],
    key: str,
    default: object = CONFIG_REQUIRED,
) -> object:
    """Return the configured value for *key*, or *default* when one was given.

    Args:
        config_values: The values baked into this service at generation time.
        key: The config key exactly as written in the DSL, e.g.
            ``"validationReport.baseUrl"``.
        default: The default the DSL supplied. Absent means the DSL supplied
            none, and a missing key is then an error rather than a null.

    Returns:
        The configured value, or *default*.

    Raises:
        RuntimeError: When *key* is not configured and the DSL supplied no
            default. Failing here is the point -- see the module docstring.
    """
    lookup = config_key_lookup(key)
    if lookup in config_values:
        return config_values[lookup]
    if default is not CONFIG_REQUIRED:
        return default
    raise RuntimeError(
        f"Config key {key!r} is not configured for this service. "
        f"Configured keys: {sorted(config_values)}. "
        "Declare it in this service's .dcfg, or pass an explicit default at "
        "the call site to state that its absence is expected."
    )


_CONFIG_REQUIRED: Final[type[_ConfigKeyRequired]] = CONFIG_REQUIRED


def config_value(key: str, default: object = CONFIG_REQUIRED) -> object:
    """Return this service's configured value for *key*.

    Binds the baked ``CONFIG_VALUES`` to the shared resolver; see
    :func:`resolve_config_value` for the contract.
    """
    return resolve_config_value(CONFIG_VALUES, key, default)


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
    product_db_host: str
    product_db_port: int
    product_db_database: str
    product_db_user: str
    product_db_async_driver: str
    product_db_password_handle: str
    db_pool_size: int
    db_max_overflow: int
    store_endpoint: str
    docdb_host: str
    docdb_port: int
    docdb_database: str
    docdb_user: str
    redis_url: str
    mq_bootstrap_servers: str
    jwt_algorithm: str
    jwt_expiry: int
    jwt_audience: str
    jwt_issuer: str


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
    from ecommerce_product_service.config.remote_config import ConnectionsKeys

    _product_db_host = config_client.get_string(
        ConnectionsKeys.NAMESPACE, ConnectionsKeys.PRODUCT_DB_HOST
    )
    _product_db_port = config_client.get_int(
        ConnectionsKeys.NAMESPACE, ConnectionsKeys.PRODUCT_DB_PORT
    )
    _product_db_database = config_client.get_string(
        ConnectionsKeys.NAMESPACE, ConnectionsKeys.PRODUCT_DB_DATABASE
    )
    _product_db_user = config_client.get_string(
        ConnectionsKeys.NAMESPACE, ConnectionsKeys.PRODUCT_DB_USER
    )
    store_endpoint = config_client.get_string(
        ConnectionsKeys.NAMESPACE, ConnectionsKeys.STORE_ENDPOINT
    )
    _docdb_host = config_client.get_string(
        ConnectionsKeys.NAMESPACE, ConnectionsKeys.DOCDB_HOST
    )
    _docdb_port = config_client.get_int(
        ConnectionsKeys.NAMESPACE, ConnectionsKeys.DOCDB_PORT
    )
    _docdb_database = config_client.get_string(
        ConnectionsKeys.NAMESPACE, ConnectionsKeys.DOCDB_DATABASE
    )
    _docdb_user = config_client.get_string(
        ConnectionsKeys.NAMESPACE, ConnectionsKeys.DOCDB_USER
    )
    _cache_host = config_client.get_string(
        ConnectionsKeys.NAMESPACE, ConnectionsKeys.REDIS_HOST
    )
    _cache_port = config_client.get_int(
        ConnectionsKeys.NAMESPACE, ConnectionsKeys.REDIS_PORT
    )
    _cache_database = config_client.get_int(
        ConnectionsKeys.NAMESPACE, ConnectionsKeys.REDIS_DATABASE
    )
    redis_url = f"redis://{_cache_host}:{_cache_port}/{_cache_database}"
    mq_bootstrap_servers = config_client.get_string(
        ConnectionsKeys.NAMESPACE, ConnectionsKeys.MQ_BROKERS
    )

    global _settings
    _settings = AppSettings(
        app_name=_bootstrap.PROFILE + "-ecommerce_product_service",
        environment=_bootstrap.PROFILE,
        host="0.0.0.0",
        port=8004,
        product_db_host=_product_db_host,
        product_db_port=_product_db_port,
        product_db_database=_product_db_database,
        product_db_user=_product_db_user,
        product_db_async_driver="postgresql+asyncpg",
        product_db_password_handle="product_db_password",
        db_pool_size=20,
        db_max_overflow=20,
        store_endpoint=store_endpoint,
        docdb_host=_docdb_host,
        docdb_port=_docdb_port,
        docdb_database=_docdb_database,
        docdb_user=_docdb_user,
        redis_url=redis_url,
        mq_bootstrap_servers=mq_bootstrap_servers,
        jwt_algorithm="RS256",
        jwt_expiry=3600,
        jwt_audience="",
        jwt_issuer="",
    )
    logger.info("app_settings_assembled environment=%s", _bootstrap.PROFILE)
    return _settings
