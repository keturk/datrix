"""Secrets resolution by logical handle. Auto-generated. Do not edit.

Resolves a logical secret handle (e.g. ``jwt_private_key``, ``db_password``) to
its concrete value using the backend baked at generation time from
``SecretBackendPolicy``.  Authentication uses the no-env ``_credentials`` module;
endpoints / paths come from ``_bootstrap`` constants.  No environment variables
are read at runtime.

Rendered backend names come from ``config._secret_manifest.SECRET_REFERENCES`` —
the single source of truth built at generation time from ``SecretReferenceManifest``.
The resolver never derives names itself.

Each handle is cached with a per-handle TTL (from the manifest, falling back to
``_DEFAULT_SECRET_TTL_SECONDS``) measured on a MONOTONIC clock. A long-lived
process that caches a secret forever never sees a rotation; a per-handle TTL plus
lazy refresh makes a rotated secret propagate within the TTL the next time the
handle is requested, **provided the backend is reachable**. On a refresh that
fails while a prior value is cached, the resolver serves the stale value and warns
(rotation is best-effort, availability is preserved) UNLESS the deployment opts
into fail-closed refresh, in which case the stale value is rejected. A handle with
no prior cached value and a failed/absent fetch always raises (the fail-closed
initial-miss contract). ``invalidate_secret`` is the single pre-TTL eviction path,
used by credential-aware wrappers to force one early refetch; it is throttled per
handle and never loops.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time

from library_book_service.config import _bootstrap, _secret_manifest

logger = logging.getLogger(__name__)

# Backend selected at generation time from SecretBackendPolicy.default_backend.
_BACKEND: str = "docker-secret"

# In-process cache: handle -> (value, expires_at_monotonic_seconds).
# expires_at uses a MONOTONIC clock (time.monotonic) so wall-clock jumps never
# expire or extend a cached secret. A value is served while _now() < expires_at.
_SECRET_CACHE: dict[str, tuple[str, float]] = {}

# Default cache TTL (seconds) baked from SecretBackendPolicy.default_secret_ttl_seconds.
# Used when a handle has no per-handle ttl_seconds override. 0 means "no expiry".
_DEFAULT_SECRET_TTL_SECONDS: int = 300

# When true, a refresh failure with a prior cached value is fatal (the stale value
# is NOT served); when false, the stale value is served with a warning.
# Baked from SecretBackendPolicy.fail_closed_on_secret_refresh.
_FAIL_CLOSED_ON_SECRET_REFRESH: bool = False

# Per-handle single-flight locks. Different handles may refresh concurrently;
# concurrent refreshes for the same handle collapse to one backend read.
_REFRESH_LOCKS: dict[str, asyncio.Lock] = {}

# Throttle repeated early invalidations for the same handle to prevent a tight
# invalidate/refetch loop when a downstream service repeatedly returns the same
# definitive credential failure.
_INVALIDATION_THROTTLE_SECONDS: float = 1.0
_LAST_INVALIDATED_AT: dict[str, float] = {}


def _now() -> float:
    """Return the current MONOTONIC time in seconds (immune to wall-clock jumps)."""
    return time.monotonic()


def _refresh_lock_for(handle: str) -> asyncio.Lock:
    """Return the process-local single-flight lock for *handle*."""
    lock = _REFRESH_LOCKS.get(handle)
    if lock is None:
        lock = asyncio.Lock()
        _REFRESH_LOCKS[handle] = lock
    return lock


def _ttl_for(handle: str) -> int:
    """Return the cache TTL (seconds) for *handle*.

    Reads the per-handle ``ttl_seconds`` baked into
    ``_secret_manifest.SECRET_REFERENCES``. Falls back to
    ``_DEFAULT_SECRET_TTL_SECONDS`` only when the manifest entry omits
    ``ttl_seconds`` (older manifests). ``0`` means no expiry.

    Args:
        handle: Logical secret handle.

    Returns:
        The TTL in seconds (>= 0).
    """
    ref = _secret_manifest.SECRET_REFERENCES.get(handle)
    if ref is None or "ttl_seconds" not in ref:
        return _DEFAULT_SECRET_TTL_SECONDS
    return int(ref["ttl_seconds"])  # type: ignore[call-overload]


def _store(handle: str, value: str) -> None:
    """Cache *value* for *handle* with its resolved expiry.

    A handle whose TTL is 0 never expires (expires_at is +inf).
    """
    ttl = _ttl_for(handle)
    expires_at = float("inf") if ttl == 0 else _now() + ttl
    _SECRET_CACHE[handle] = (value, expires_at)


def _get_rendered_name(handle: str) -> str:
    """Look up the backend-specific rendered name for a logical handle.

    The rendered name is read from ``_secret_manifest.SECRET_REFERENCES`` — the
    data-only manifest built at generation time.  This resolver never derives
    names from prefix + separator + handle; all derivation happens once in
    ``SecretReferenceManifest`` during code generation.

    Args:
        handle: Logical secret handle (e.g. ``"jwt_private_key"``).

    Returns:
        Backend-specific secret name, path, or leaf filename.

    Raises:
        KeyError: When ``handle`` is not in the manifest (indicates a code-generation
            bug — the resolver and manifest must be generated from the same service
            definition).
    """
    ref = _secret_manifest.SECRET_REFERENCES.get(handle)
    if ref is None:
        raise KeyError(
            "Secret handle %r is not declared in the generated _secret_manifest. "
            "Declared handles: %s. "
            "This is a code-generation error — regenerate the service so the "
            "resolver and manifest are built from the same service definition."
            % (handle, sorted(_secret_manifest.SECRET_REFERENCES.keys()))
        )
    return str(ref["rendered_name"])


async def _fetch_from_backend(handle: str) -> str | None:
    """Fetch ``handle`` from a mounted secrets directory (file backend).

    Reads the file at ``SECRETS_DIR_PATH / rendered_name``.  File read only;
    no environment variables are consulted.  Returns ``None`` when the file is absent.
    Never logs secret values.

    Args:
        handle: Logical secret handle.

    Returns:
        File contents (stripped), or ``None`` if the file is absent.

    Raises:
        RuntimeError: When ``SECRETS_DIR_PATH`` is not baked (None or empty).
    """
    if not _bootstrap.SECRETS_DIR_PATH:
        raise RuntimeError(
            "SECRETS_DIR_PATH is not baked; cannot read mounted secret files. "
            "The generator must bake the secrets directory path at generation time. "
            "Regenerate with a resolved secrets_dir_path."
        )
    leaf = _get_rendered_name(handle)
    secret_path = os.path.join(_bootstrap.SECRETS_DIR_PATH, leaf)
    try:
        with open(secret_path) as fh:
            value = fh.read().rstrip("\n")
        logger.debug("secret_fetched backend=%s handle=%s", _BACKEND, handle)
        return value
    except FileNotFoundError:
        return None


async def get_secret(handle: str) -> str:
    """Resolve a required secret by logical handle with TTL-bounded caching.

    Resolves ``handle`` through the backend baked at generation time
    (``_BACKEND = "docker-secret"``).  Rendered backend names are
    read from ``_secret_manifest.SECRET_REFERENCES`` — never derived inline.

    A cached value is returned while it is unexpired (per-handle TTL from the
    manifest, falling back to ``_DEFAULT_SECRET_TTL_SECONDS``). On expiry the
    backend is re-read so a rotated secret propagates. Concurrent expired/missing
    reads for one handle collapse to a single backend fetch via a per-handle
    single-flight lock. If the re-read fails and a prior value is cached, the
    prior value is served with a warning unless ``_FAIL_CLOSED_ON_SECRET_REFRESH``
    is true. An initial miss (no prior value, fetch returns None) always raises —
    the fail-closed initial contract.

    Args:
        handle: Logical secret handle (e.g. ``"jwt_private_key"``).

    Returns:
        The resolved secret value string.

    Raises:
        RuntimeError: When the secret is absent from the backend on an initial
            miss, or when the backend cannot be reached and either no prior value
            is cached or fail-closed refresh is enabled.  The error message names
            the handle but never includes the secret value.
    """
    cached = _SECRET_CACHE.get(handle)
    if cached is not None:
        value, expires_at = cached
        if _now() < expires_at:
            return value

    async with _refresh_lock_for(handle):
        refreshed = _SECRET_CACHE.get(handle)
        if refreshed is not None:
            value, expires_at = refreshed
            if _now() < expires_at:
                return value

        try:
            fetched = await _fetch_from_backend(handle)
        except Exception as exc:  # backend unreachable / SDK error on refresh
            if cached is not None and not _FAIL_CLOSED_ON_SECRET_REFRESH:
                logger.warning(
                    "secret_refresh_failed_serving_stale backend=%s handle=%s error=%s",
                    _BACKEND,
                    handle,
                    exc,
                )
                return cached[0]
            raise

        if fetched is None:
            if cached is not None and not _FAIL_CLOSED_ON_SECRET_REFRESH:
                logger.warning(
                    "secret_refresh_absent_serving_stale backend=%s handle=%s",
                    _BACKEND,
                    handle,
                )
                return cached[0]
            raise RuntimeError(
                "Required secret %r not found in backend %r. "
                "Ensure the secret is provisioned in the deployment environment "
                "with the rendered name %r."
                % (handle, _BACKEND, _get_rendered_name(handle))
            )

        _store(handle, fetched)
        logger.info("secret_resolved backend=%s handle=%s", _BACKEND, handle)
        return fetched


def invalidate_secret(handle: str, reason: str) -> None:
    """Evict *handle* from the cache so the next get_secret refetches it.

    Intended for generated credential-aware wrappers ONLY: a wrapper that
    classifies a downstream error as a DEFINITIVE credential failure (e.g. an
    authentication-rejected response) calls this to drop the stale credential
    BEFORE its TTL expires, then retries the original operation at most once.
    A non-credential / transient error MUST NOT call this.

    The eviction is idempotent and throttled per handle; the subsequent
    get_secret is the single refetch and is protected by the per-handle
    single-flight lock. This helper never loops and never retries on its own.

    Args:
        handle: Logical secret handle to evict.
        reason: Short, value-free classification string for the log line.
    """
    now = _now()
    previous = _LAST_INVALIDATED_AT.get(handle)
    if previous is not None and now - previous < _INVALIDATION_THROTTLE_SECONDS:
        logger.warning(
            "secret_invalidation_throttled backend=%s handle=%s reason=%s",
            _BACKEND,
            handle,
            reason,
        )
        return
    _LAST_INVALIDATED_AT[handle] = now

    if handle in _SECRET_CACHE:
        del _SECRET_CACHE[handle]
        logger.warning(
            "secret_invalidated backend=%s handle=%s reason=%s",
            _BACKEND,
            handle,
            reason,
        )
