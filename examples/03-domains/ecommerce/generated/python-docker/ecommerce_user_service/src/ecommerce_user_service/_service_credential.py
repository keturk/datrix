"""Managed machine-identity credential acquisition for inter-service calls.

Generated for service-to-service (auth(service)) callers. The credential is the
platform's own machine identity, never a self-signed application token and never
a static shared secret.

Strategy: oidc-client-credentials
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time

import httpx

logger = logging.getLogger(__name__)

# Path to the machine service-account credentials the Zitadel provisioning
# init-job writes after creating the platform machine identity. The file lives on
# a shared volume mounted read-only into every service; services depend on the
# init-job completing, so it is present before the first inter-service call.
# This literal mirrors datrix-codegen-docker's _MACHINE_CREDENTIALS_CONTAINER_PATH.
_MACHINE_CREDENTIALS_FILE: str = "/machine-credentials/credentials.json"

# Refresh the cached token this many seconds before its real expiry so an
# in-flight request never presents an already-expired token.
_TOKEN_EXPIRY_SKEW_SECONDS: float = 30.0

# Required keys in the credentials file. ``audience`` is the reserved Zitadel
# project-audience scope (``urn:zitadel:iam:org:project:id:<projectId>:aud``) that
# places the machine project in the token's ``aud`` claim so the callee's JWKS
# guard accepts it. ``instanceOrigin`` is the Zitadel instance base URL,
# doubling as the Management-API base (``{instanceOrigin}/management/v1/...``)
# -- consumed by ``_provider_metadata.py``'s write-back client.
_REQUIRED_CREDENTIAL_KEYS: tuple[str, ...] = (
    "clientId",
    "clientSecret",
    "tokenUrl",
    "hostHeader",
    "audience",
    "instanceOrigin",
)

_token_lock = asyncio.Lock()

# Machine tokens cached by the client-credentials audience/scope they were
# minted for. Inter-service calls use the machine-project audience the callee's
# JWKS guard accepts (the empty-string key -> creds["audience"]); a provider
# management-API write (``_provider_metadata.py``) uses that API's OWN reserved
# audience -- a DIFFERENT ``aud`` -- so each is cached under its own key and one
# never masks the other.
_cached_tokens: dict[str, tuple[str, float]] = {}


def _load_machine_credentials() -> dict[str, str]:
    """Return the Zitadel machine service-account credentials the init-job wrote.

    Returns:
        Mapping with ``clientId``, ``clientSecret``, ``tokenUrl``, ``hostHeader``,
        ``audience``, and ``instanceOrigin``.

    Raises:
        RuntimeError: When the file is absent, malformed, or missing a key.
    """
    try:
        with open(_MACHINE_CREDENTIALS_FILE, encoding="utf-8") as handle:
            raw: object = json.load(handle)
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"Machine credentials file '{_MACHINE_CREDENTIALS_FILE}' not found. "
            "The Zitadel provisioning init-job mints the machine service account "
            "and writes this file; ensure this service depends on that job and "
            "mounts the shared machine-credentials volume."
        ) from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Machine credentials file '{_MACHINE_CREDENTIALS_FILE}' is not valid "
            f"JSON: {exc}."
        ) from exc
    if not isinstance(raw, dict):
        raise RuntimeError(
            f"Machine credentials file '{_MACHINE_CREDENTIALS_FILE}' must contain "
            "a JSON object."
        )
    creds: dict[str, str] = {}
    missing: list[str] = []
    for key in _REQUIRED_CREDENTIAL_KEYS:
        value = raw.get(key)
        if isinstance(value, str) and value:
            creds[key] = value
        else:
            missing.append(key)
    if missing:
        raise RuntimeError(
            f"Machine credentials file '{_MACHINE_CREDENTIALS_FILE}' is missing "
            f"required keys {missing}. Regenerate and redeploy so the init-job "
            "rewrites the file."
        )
    return creds


def _decode_token_expiry(token: str) -> float:
    """Return the JWT ``exp`` (epoch seconds), or ``0.0`` when it cannot be read."""
    parts = token.split(".")
    if len(parts) != 3:
        return 0.0
    payload_b64 = parts[1]
    padding = "=" * (-len(payload_b64) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload_b64 + padding)
        claims: object = json.loads(decoded)
    except (ValueError, json.JSONDecodeError):
        return 0.0
    if not isinstance(claims, dict):
        return 0.0
    exp = claims.get("exp")
    if isinstance(exp, (int, float)):
        return float(exp)
    return 0.0


async def _acquire_zitadel_machine_token(scope_audience: str = "") -> str:
    """Return a cached or freshly minted Zitadel machine access token.

    Exchanges the platform machine service-account's client_id/secret for an
    RS256 access token via the OAuth2 ``client_credentials`` grant. The token is
    cached per requested audience until shortly before its ``exp``.

    Args:
        scope_audience: The client-credentials audience/scope to mint the token
            for. Empty (the default) means the machine-project audience baked in
            the credentials file (``creds["audience"]``) -- the inter-service
            audience the callee's JWKS guard accepts. A non-empty value (a
            provider management-API's own reserved audience) mints and caches a
            token scoped to THAT audience instead, without disturbing the
            inter-service token.

    Raises:
        RuntimeError: When the token endpoint rejects the request or returns no
            access token.
    """
    # Cache key is the requested scope verbatim -- "" for the default
    # machine-project token, the reserved audience for a provider management-API
    # token -- so the two never share a slot.
    cached = _cached_tokens.get(scope_audience)
    if cached is not None and time.time() < cached[1] - _TOKEN_EXPIRY_SKEW_SECONDS:
        return cached[0]
    async with _token_lock:
        cached = _cached_tokens.get(scope_audience)
        if cached is not None and time.time() < cached[1] - _TOKEN_EXPIRY_SKEW_SECONDS:
            return cached[0]
        creds = _load_machine_credentials()
        audience = scope_audience or creds["audience"]
        form = {
            "grant_type": "client_credentials",
            "scope": f"openid {audience}",
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(
                creds["tokenUrl"],
                data=form,
                auth=(creds["clientId"], creds["clientSecret"]),
                headers={"Host": creds["hostHeader"]},
            )
        if response.status_code != 200:
            raise RuntimeError(
                "Failed to acquire Zitadel machine token via client_credentials "
                f"(HTTP {response.status_code}): {response.text[:300]}. "
                "Verify the machine service account exists and its secret matches "
                "the credentials file."
            )
        body: object = response.json()
        token = body.get("access_token") if isinstance(body, dict) else None
        if not isinstance(token, str) or not token:
            raise RuntimeError(
                "Zitadel token response did not contain an 'access_token'."
            )
        expires_in = body.get("expires_in") if isinstance(body, dict) else None
        fallback_expiry = time.time() + (
            float(expires_in) if isinstance(expires_in, (int, float)) else 0.0
        )
        expiry = _decode_token_expiry(token) or fallback_expiry
        _cached_tokens[scope_audience] = (token, expiry)
        logger.debug(
            "zitadel_machine_token_acquired audience=%s expiry=%s", audience, expiry
        )
        return token


async def acquire_provider_metadata_credential(audience: str) -> str:
    """Return a machine token scoped to a provider management-API's own audience.

    A provider's own management API gates on a DIFFERENT ``aud`` than sibling
    services do: sibling services accept the machine-project audience baked in
    the credentials file, but the provider management API accepts only its own
    reserved API audience. The write-back client (``_provider_metadata.py``)
    calls this with the platform-declared ``token_audience`` so the metadata
    write is authenticated against the management API, not a peer service.

    Args:
        audience: The reserved provider management-API audience/scope string
            (the platform's declared
            ``IdentityWriteBackDeclaration.token_audience``). An empty string
            falls back to the machine-project audience -- for a platform whose
            management API happens to accept the inter-service audience. Never a
            peer service's network address.

    Returns:
        The bearer token string scoped to ``audience``.

    Raises:
        RuntimeError: When the token endpoint rejects the request or returns no
            access token.
    """
    return await _acquire_zitadel_machine_token(scope_audience=audience)


async def acquire_service_credential() -> str:
    """Return the managed machine-identity credential for an outbound call.

    The credential's audience is the machine identity provider's OWN resource,
    resolved internally per strategy (the callee validates every service credential
    against the same machine provider, so the audience is a system constant, not a
    per-callee value). It is never the callee's network address.

    Returns:
        The bearer credential string to place on the outbound request.

    Raises:
        RuntimeError: When the platform credential cannot be obtained.
    """
    # Docker/self-host: the platform machine identity is a Zitadel service account.
    # The minted token is audience-scoped to the machine project (baked in the
    # credentials file) and authenticates to every peer.
    return await _acquire_zitadel_machine_token()
