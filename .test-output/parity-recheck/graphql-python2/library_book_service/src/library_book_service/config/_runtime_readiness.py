"""Strict runtime readiness check. Auto-generated. Do not edit.

Resolves every required config key and secret handle through the SAME runtime
clients the application uses (RemoteConfigClient from
``library_book_service.config.remote_config`` and the
``library_book_service.config._secrets_resolver`` module), proving the live
backend actually serves each item under the deployed identity. Reports status by
logical handle/key and rendered platform name. NEVER captures, logs, or returns a
resolved value.

Because it exercises the real resolution path against the real backend (Key
Vault / Secrets Manager / mounted files / remote config store), it catches
IAM/role denials, wrong mount paths, unreachable backend URLs, wrong
label/profile, and missing permissions that a static, generation-time preflight
can never prove.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

from library_book_service.config import _secrets_resolver
from library_book_service.config.remote_config import (
    ConnectionsKeys,
    RemoteConfigClient,
    RemoteConfigError,
)

logger = logging.getLogger(__name__)

# Kind discriminators for a readiness item.
_KIND_CONFIG = "config"
_KIND_SECRET = "secret"


class ReadinessStatus(str, Enum):
    """Outcome for a single required item."""

    OK = "ok"
    MISSING = "missing"
    ERROR = "error"


# Statuses that block readiness (flip ok=False, exit non-zero). Every required
# item either resolves to a real value or blocks: deployment preflight refuses
# to write a stand-in value into any secret, so a resolvable handle always
# carries the value an operator or Datrix actually provisioned.
_BLOCKING_STATUSES = (ReadinessStatus.MISSING, ReadinessStatus.ERROR)


@dataclass(frozen=True)
class ReadinessItem:
    """Per-item readiness result. Holds NO secret value -- only identity + status."""

    kind: str  # "config" | "secret"
    logical_name: str  # logical handle or config key
    rendered_name: str  # backend/platform-rendered name
    status: ReadinessStatus
    detail: str  # human-readable, value-free (e.g. "permission denied")


@dataclass(frozen=True)
class ReadinessReport:
    """Aggregate readiness result."""

    ok: bool
    items: tuple[ReadinessItem, ...]

    @property
    def failures(self) -> tuple[ReadinessItem, ...]:
        """Return the BLOCKING items (missing/error)."""
        return tuple(i for i in self.items if i.status in _BLOCKING_STATUSES)


# Required set baked from the runtime-requirements manifest.
# Each entry: (logical_name, rendered_name). Values are NEVER baked here.
_REQUIRED_SECRET_HANDLES: tuple[tuple[str, str], ...] = (
    ("book_db_password", "book_db_password"),
    ("jwt_public_key", "jwt_public_key"),
)

_REQUIRED_CONFIG_KEYS: tuple[tuple[str, str], ...] = (
    ("book_db_database", "book_db_database"),
    ("book_db_host", "book_db_host"),
    ("book_db_port", "book_db_port"),
    ("book_db_user", "book_db_user"),
    ("mq_brokers", "mq_brokers"),
    ("mq_port", "mq_port"),
)


def _value_free_detail(exc: BaseException) -> str:
    """Build a value-free diagnostic detail from an exception.

    Only the exception type name and its own message text are used. The
    resolver and config client guarantee value-free messages (they name the
    handle / key / rendered name, never the resolved value); this helper never
    formats a detail from a resolved value because no resolved value is ever
    bound in the probe frame beyond the resolution call.
    """
    return f"{type(exc).__name__}: {exc}"


async def _probe_secret(logical: str, rendered: str) -> ReadinessItem:
    """Resolve one required secret handle through the live resolver.

    The resolved value is never bound, inspected, logged, or returned: the
    resolution either succeeds -- proving the live backend serves the handle
    under the deployed identity -- or raises, which is what classifies the item.

    Args:
        logical: Logical secret handle (e.g. ``"db_password"``).
        rendered: Backend/platform-rendered name for the handle.

    Returns:
        A value-free :class:`ReadinessItem` for the handle.
    """
    try:
        # Resolve through the SAME resolver the app uses. The returned value is
        # deliberately not bound -- only the success/failure of the call matters.
        await _secrets_resolver.get_secret(logical)
    except RuntimeError as exc:
        # The resolver raises RuntimeError both for an absent secret (initial
        # miss) and for an unreachable / denied backend. An absent secret is
        # MISSING; any other RuntimeError is a backend ERROR. The resolver's
        # "not found" message names the handle and rendered name only.
        detail = _value_free_detail(exc)
        if "not found" in str(exc):
            return ReadinessItem(
                kind=_KIND_SECRET,
                logical_name=logical,
                rendered_name=rendered,
                status=ReadinessStatus.MISSING,
                detail=detail,
            )
        return ReadinessItem(
            kind=_KIND_SECRET,
            logical_name=logical,
            rendered_name=rendered,
            status=ReadinessStatus.ERROR,
            detail=detail,
        )
    except Exception as exc:  # noqa: BLE001 -- classify any backend/SDK error as ERROR
        return ReadinessItem(
            kind=_KIND_SECRET,
            logical_name=logical,
            rendered_name=rendered,
            status=ReadinessStatus.ERROR,
            detail=_value_free_detail(exc),
        )
    return ReadinessItem(
        kind=_KIND_SECRET,
        logical_name=logical,
        rendered_name=rendered,
        status=ReadinessStatus.OK,
        detail="resolved",
    )


def _probe_config(
    config_client: RemoteConfigClient,
    logical: str,
    rendered: str,
) -> ReadinessItem:
    """Resolve one required config key through the live config client.

    Reads the key from the ``connections`` namespace via the SAME
    ``RemoteConfigClient`` the app uses. The returned value is discarded
    immediately. A declared-but-unset key is MISSING; any other config error is
    ERROR.

    Args:
        config_client: The SAME ``RemoteConfigClient`` the application uses.
        logical: Logical config key name.
        rendered: Platform-rendered key name.

    Returns:
        A value-free :class:`ReadinessItem` for the key.
    """
    try:
        # The connections namespace holds the runtime connection scalars. The
        # generic ``get`` accessor proves the key resolves regardless of its
        # declared scalar type; the value is intentionally not bound.
        config_client.get(ConnectionsKeys.NAMESPACE, logical)
    except RemoteConfigError as exc:
        detail = _value_free_detail(exc)
        text = str(exc)
        if "no current value" in text or "not declared" in text:
            return ReadinessItem(
                kind=_KIND_CONFIG,
                logical_name=logical,
                rendered_name=rendered,
                status=ReadinessStatus.MISSING,
                detail=detail,
            )
        return ReadinessItem(
            kind=_KIND_CONFIG,
            logical_name=logical,
            rendered_name=rendered,
            status=ReadinessStatus.ERROR,
            detail=detail,
        )
    except Exception as exc:  # noqa: BLE001 -- classify any backend error as ERROR
        return ReadinessItem(
            kind=_KIND_CONFIG,
            logical_name=logical,
            rendered_name=rendered,
            status=ReadinessStatus.ERROR,
            detail=_value_free_detail(exc),
        )
    return ReadinessItem(
        kind=_KIND_CONFIG,
        logical_name=logical,
        rendered_name=rendered,
        status=ReadinessStatus.OK,
        detail="resolved",
    )


async def check_runtime_readiness(config_client: RemoteConfigClient) -> ReadinessReport:
    """Resolve every required item through the live clients. Returns a value-free report.

    Args:
        config_client: The SAME ``RemoteConfigClient`` the application uses.

    Returns:
        A :class:`ReadinessReport`. ``ok`` is True when no required config key
        or secret handle is MISSING or ERROR under the deployed identity.
    """
    items: list[ReadinessItem] = []
    for logical, rendered in _REQUIRED_SECRET_HANDLES:
        items.append(await _probe_secret(logical, rendered))
    for logical, rendered in _REQUIRED_CONFIG_KEYS:
        items.append(_probe_config(config_client, logical, rendered))
    report = ReadinessReport(
        ok=not any(i.status in _BLOCKING_STATUSES for i in items),
        items=tuple(items),
    )
    # Log identities and statuses ONLY -- never the resolved value.
    for item in report.items:
        logger.info(
            "readiness kind=%s name=%s rendered=%s status=%s",
            item.kind,
            item.logical_name,
            item.rendered_name,
            item.status.value,
        )
    return report
