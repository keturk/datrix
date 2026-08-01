"""JWKS-based identity validation core for library.BookService.

Loads the identity provider plan from the deployment-static path baked at
generation time (``_bootstrap.IDENTITY_PROVIDER_PLAN_PATH``).  Resolves signing
keys via ``PyJWKClient`` with per-provider caching, and performs full token
validation: signature, expiry, issuer, audience, and algorithm allow-list.

Environment reads — exactly one, by design.  Plan *location* still reads no
environment variables.  Plan *content* does: a provider entry may declare
``allowedAudienceRefs``, a list of environment-variable NAMES (never values)
whose contents are unioned into the effective audience allow-list at runtime.
This exists because some accepted ``aud`` values are assigned by the identity
provider at provisioning time and so cannot be baked into a static plan — the
Entra v2 access token case, whose ``aud`` is the app registration's
deploy-time-assigned client-ID GUID delivered as the
``IDENTITY_<PROVIDER>_AUDIENCE_CLIENT_ID`` app setting.  The runtime contract is

    effective_audiences = allowedAudiences U {env[name] for name in refs}

and it FAILS CLOSED: a declared ref whose environment variable is unset or empty
raises ``JwksValidationError`` (``provider_config_error``).  It can never degrade
to an empty allow-list, which this module reads as "no audience constraint" (the
JWT decode is then passed ``audience=None``) — that degradation would drop
audience enforcement entirely for the affected provider.

Algorithm allow-list comes from the plan — symmetric algorithms (HS*) and
``alg: none`` are always rejected.  JWKS key rotation is handled by refreshing
the JWKS cache on unknown ``kid`` before rejecting (DN38).  JWKS refresh failure
fails closed.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any

import jwt
from jwt import PyJWKClient, PyJWKClientError, PyJWTError
from jwt.exceptions import (
    DecodeError,
    ExpiredSignatureError,
    InvalidAudienceError,
    InvalidIssuerError,
    InvalidSignatureError,
    PyJWKSetError,
)

from library_book_service.config import _bootstrap

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_JWT_ALGORITHM_ENV_VAR: str = "JWT_ALGORITHM"
_SYMMETRIC_ALG_PREFIXES: tuple[str, ...] = ("HS",)
_ALG_NONE: str = "none"

# ---------------------------------------------------------------------------
# Reason codes — string constants used in generated runtime code.
# Mirror of AuthReasonCode from datrix-common (kept inline to avoid runtime
# dependency on the framework package in generated services).
# ---------------------------------------------------------------------------

_REASON_MISSING_TOKEN: str = "missing_token"
_REASON_MALFORMED_TOKEN: str = "malformed_token"
_REASON_EXPIRED_TOKEN: str = "expired_token"
_REASON_BAD_SIGNATURE: str = "bad_signature"
_REASON_ISSUER_MISMATCH: str = "issuer_mismatch"
_REASON_AUDIENCE_MISMATCH: str = "audience_mismatch"
_REASON_PROVIDER_MISMATCH: str = "provider_mismatch"
_REASON_JWKS_REFRESH_FAILED: str = "jwks_refresh_failed"
_REASON_PROVIDER_CONFIG: str = "provider_config_error"
_REASON_REQUIRED_FIELD_MISSING: str = "required_identity_field_missing"

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class JwksValidationError(Exception):
    """Raised when JWKS-based token validation fails.

    Attributes:
        reason_code: One of the ``_REASON_*`` string constants identifying
            the failure category.  Never exposed in client HTTP responses.
    """

    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code: str = reason_code


# ---------------------------------------------------------------------------
# Plan loading
# ---------------------------------------------------------------------------

_cached_plan: dict[str, Any] | None = None
_cached_plan_path: str | None = None

# Filename of the identity provider plan artifact bundled INTO this service
# package (beside ``config/_bootstrap.py``). Emitted per-service so it ships in
# the service wheel and resolves regardless of CWD — the same delivery pattern
# as ``config/remote_defaults.json``.
_PLAN_ARTIFACT_FILENAME: str = "identity-provider-plan.json"


def _bundled_plan_path() -> Path | None:
    """Return the module-relative path to the bundled plan, or None when unknown.

    ``_bootstrap`` lives in the service's ``config`` package, so the bundled plan
    sits next to it inside the installed wheel.  ``Path(__file__)``-style
    resolution is CWD-independent (unlike a bare relative ``open(...)``), so it
    resolves under site-packages on Azure App Service / any wheel install.

    Returns ``None`` when the bootstrap module exposes no ``__file__`` (e.g. a
    dynamically constructed module), in which case the baked mount path is used.
    """
    bootstrap_file = getattr(_bootstrap, "__file__", None)
    if not bootstrap_file:
        return None
    return Path(bootstrap_file).with_name(_PLAN_ARTIFACT_FILENAME)


def _resolve_plan_path() -> str:
    """Resolve the on-disk identity provider plan path (no environment reads).

    Resolution order (deployment-static, CWD-independent):

    1. The plan artifact BUNDLED beside ``_bootstrap`` inside the installed
       service package (``config/identity-provider-plan.json``). This ships in
       the service wheel and always resolves under site-packages regardless of
       the process working directory — the primary path for wheel deployments
       (Azure App Service, AWS).
    2. The deployment-static ``_bootstrap.IDENTITY_PROVIDER_PLAN_PATH`` constant
       — used when the plan is mounted at a fixed absolute path rather than
       bundled (e.g. the docker-compose read-only mount).

    Returns:
        The resolved plan path as a string.

    Raises:
        RuntimeError: When neither a bundled artifact nor a baked path is
            available.
    """
    bundled = _bundled_plan_path()
    if bundled is not None and bundled.is_file():
        return str(bundled)
    baked_path = _bootstrap.IDENTITY_PROVIDER_PLAN_PATH or ""
    if baked_path:
        return baked_path
    raise RuntimeError(
        "Identity provider plan not found: no bundled plan artifact beside "
        "_bootstrap (%r) and the deployment-static 'IDENTITY_PROVIDER_PLAN_PATH' "
        "bootstrap constant is empty. The plan must ship inside the service "
        "package (config/%s) or be mounted at the baked path. Regenerate the "
        "service." % (str(bundled), _PLAN_ARTIFACT_FILENAME)
    )


def _load_provider_plan() -> dict[str, Any]:
    """Load and cache the identity provider plan (no environment reads).

    The plan is resolved by :func:`_resolve_plan_path` — bundled artifact first
    (CWD-independent, ships in the wheel), then the deployment-static mount path.

    Returns:
        Parsed plan dict.

    Raises:
        RuntimeError: When no plan can be resolved or the file cannot be read.
    """
    global _cached_plan, _cached_plan_path
    plan_path = _resolve_plan_path()
    if _cached_plan is not None and _cached_plan_path == plan_path:
        return _cached_plan
    with open(plan_path, encoding="utf-8") as fh:
        plan: dict[str, Any] = json.load(fh)
    _cached_plan = plan
    _cached_plan_path = plan_path
    logger.debug(
        "identity_plan_loaded path=%s providers=%s",
        plan_path,
        list(plan.get("providers", {}).keys()),
    )
    return plan


def load_provider_plan() -> dict[str, Any]:
    """Public accessor for the cached identity provider plan.

    Surface guards, profile projection, and delegation validation resolve
    ``surfaces`` / ``providers`` through this single loader so plan loading and
    caching live in exactly one place (DRY).

    Returns:
        The parsed provider plan dict.

    Raises:
        RuntimeError: When the baked ``IDENTITY_PROVIDER_PLAN_PATH`` is empty or the file cannot be read.
    """
    return _load_provider_plan()


# ---------------------------------------------------------------------------
# Deterministic local-user-id resolver
# ---------------------------------------------------------------------------


def local_user_id(provider_name: str, subject: str) -> str:
    """Resolve the stable local user id for (provider, sub) from the provider plan.

    Reads ``localIdentity.mode`` and — for ``deterministicUuid5`` — the frozen
    namespace from the provider plan entry.  The namespace is never declared as a
    literal in this package; it is always read from the plan at runtime.

    Modes:
        deterministicUuid5: ``uuidv5(namespace, "<provider>:<sub>")`` — UUID-shaped,
            stateless, uniform across all services for the same ``(provider, sub)`` pair.
        subjectText: raw subject verbatim — the app-level schema uses TEXT columns.

    The ``projected`` mode is handled by the profile store path instead; calling
    this resolver for a projected provider is a configuration error.

    Args:
        provider_name: Logical provider name (must be present in the plan).
        subject: Raw JWT ``sub`` claim.

    Returns:
        Resolved local user id string.

    Raises:
        JwksValidationError: When ``localIdentity.mode`` is ``projected`` or unknown.
        RuntimeError: When the provider plan cannot be loaded.
        KeyError: When ``provider_name`` is absent from the plan.
    """
    plan = load_provider_plan()
    entry: dict[str, Any] = plan["providers"][provider_name]
    local_identity: dict[str, Any] = entry["localIdentity"]
    mode: str = local_identity["mode"]
    if mode == "deterministicUuid5":
        namespace: uuid.UUID = uuid.UUID(local_identity["namespace"])
        return str(uuid.uuid5(namespace, "%s:%s" % (provider_name, subject)))
    if mode == "subjectText":
        return subject
    raise JwksValidationError(
        reason_code=_REASON_PROVIDER_CONFIG,
        message=(
            "local_user_id called for provider '%s' in mode '%s'; "
            "the 'projected' mode resolves via the profile store, not the "
            "deterministic resolver.  "
            "Fix: use load_or_create_profile for projected providers, or "
            "reconfigure the provider to use 'deterministicUuid5' or 'subjectText'."
            % (provider_name, mode)
        ),
    )


# ---------------------------------------------------------------------------
# JWKS client cache (keyed by provider name + jwksUri)
# ---------------------------------------------------------------------------

_jwks_clients: dict[str, PyJWKClient] = {}


def _get_jwks_client(
    provider_name: str, jwks_uri: str, cache_ttl_seconds: int
) -> PyJWKClient:
    """Return a cached ``PyJWKClient`` for the given provider.

    Args:
        provider_name: Logical provider name (used as cache key prefix).
        jwks_uri: The provider's JWKS endpoint URI.
        cache_ttl_seconds: JWKS cache TTL in seconds.

    Returns:
        Shared ``PyJWKClient`` instance for this provider.
    """
    cache_key = "%s|%s" % (provider_name, jwks_uri)
    if cache_key not in _jwks_clients:
        _jwks_clients[cache_key] = PyJWKClient(
            jwks_uri,
            cache_keys=True,
            lifespan=cache_ttl_seconds,
        )
        logger.debug(
            "identity_jwks_client_created provider=%s jwks_uri=%s ttl=%s",
            provider_name,
            jwks_uri,
            cache_ttl_seconds,
        )
    return _jwks_clients[cache_key]


# ---------------------------------------------------------------------------
# Algorithm guard
# ---------------------------------------------------------------------------


def _assert_asymmetric_algorithm(alg: str, provider_name: str) -> None:
    """Raise ``JwksValidationError`` when ``alg`` is symmetric or ``none``.

    Args:
        alg: JWS algorithm identifier.
        provider_name: Provider name for diagnostics.

    Raises:
        JwksValidationError: When the algorithm is rejected.
    """
    if alg.lower() == _ALG_NONE or any(
        alg.startswith(p) for p in _SYMMETRIC_ALG_PREFIXES
    ):
        raise JwksValidationError(
            reason_code=_REASON_BAD_SIGNATURE,
            message=(
                "Rejected algorithm '%s' for provider '%s': symmetric algorithms "
                "(HS*) and 'none' are not permitted.  Use an asymmetric algorithm "
                "(RS*, ES*, PS*)." % (alg, provider_name)
            ),
        )


# ---------------------------------------------------------------------------
# Role extraction
# ---------------------------------------------------------------------------


def _resolve_claim_path(claims: dict[str, Any], claim_path: str) -> Any:
    """Resolve a (possibly dotted) claim path against the decoded claims.

    Traverses nested mappings segment by segment so providers whose roles live
    under a nested object (e.g. ``realm_access.roles``) resolve correctly,
    while a flat key (``roles``) still works as a single-segment path.  Returns
    ``None`` when any segment is missing or a non-mapping value is reached before
    the path is fully consumed — never a flat lookup of a key literally named
    ``"realm_access.roles"``.

    Args:
        claims: Decoded JWT claims dict.
        claim_path: Dot-separated claim path (e.g. ``"realm_access.roles"``).

    Returns:
        The value at the claim path, or ``None`` when it cannot be resolved.
    """
    cursor: Any = claims
    for segment in claim_path.split("."):
        if not isinstance(cursor, dict):
            return None
        cursor = cursor.get(segment)
    return cursor


def _extract_roles(claims: dict[str, Any], provider: dict[str, Any]) -> list[str]:
    """Extract Datrix role strings from token claims using the provider's roleSource.

    Two claim shapes are supported:

    * **Map shape** -- the self-host (Zitadel) default role claim
      ``urn:zitadel:iam:org:project:roles`` resolves to a mapping
      ``{roleKey: {orgId: orgDomain}}``. The role KEYS are the role names; the
      nested ``{orgId: orgDomain}`` values are organization metadata and are not
      role names.
    * **Array shape** -- ``external`` OIDC providers may deliver the claim as a
      flat list of role-name strings (e.g. ``["editor", "viewer"]``).

    Every raw role name is then normalized through ``roleMappings`` (provider-local
    role name -> Datrix role name); unmapped names pass through unchanged.

    Args:
        claims: Decoded JWT claims dict.
        provider: Provider plan entry dict.

    Returns:
        List of normalized role name strings.
    """
    role_source: dict[str, Any] | None = provider.get("roleSource")
    claim_path: str = (
        "roles" if role_source is None else role_source.get("claimPath", "roles")
    )
    raw_claim: Any = _resolve_claim_path(claims, claim_path)
    if isinstance(raw_claim, dict):
        raw_roles: list[str] = [str(key) for key in raw_claim]
    elif isinstance(raw_claim, list):
        raw_roles = [str(item) for item in raw_claim]
    else:
        raw_roles = []
    role_mappings: dict[str, str] = provider.get("roleMappings", {})
    return [role_mappings.get(raw, raw) for raw in raw_roles]


# ---------------------------------------------------------------------------
# Provider selection
# ---------------------------------------------------------------------------


def _token_audiences(unverified_payload: dict[str, Any]) -> set[str]:
    """Return the token's ``aud`` claim normalized to a set of strings.

    The JWT ``aud`` claim is either a single string or a list of strings
    (RFC 7519).  Both shapes are normalized so provider selection can intersect
    it against each provider's ``allowedAudiences``.

    Args:
        unverified_payload: The decoded (unverified) JWT payload.

    Returns:
        Set of audience strings; empty when ``aud`` is absent or malformed.
    """
    raw: Any = unverified_payload.get("aud")
    if isinstance(raw, str):
        return {raw}
    if isinstance(raw, list):
        return {str(item) for item in raw}
    return set()


def _effective_audiences(provider_name: str, provider: dict[str, Any]) -> list[str]:
    """Return the provider's effective audience allow-list, failing closed on unset refs.

    The effective allow-list is the union of the static ``allowedAudiences`` and
    the resolved values of every environment variable NAMED in
    ``allowedAudienceRefs``.  Refs exist for audiences the identity provider
    assigns at provisioning time (the Entra v2 access token ``aud`` is the app
    registration's deploy-time client-ID GUID), which cannot be baked into a
    static plan.

    A declared ref whose environment variable is unset or empty is a deployment
    wiring defect, and it FAILS CLOSED with ``provider_config_error``.  It must
    never silently yield an empty allow-list: an empty allow-list means "no
    audience constraint" — :func:`_select_provider` prefers such a provider as
    unconstrained, and the JWT decode is then passed ``audience=None``.
    Degrading here would therefore drop audience enforcement entirely.

    Args:
        provider_name: Logical provider name (for diagnostics).
        provider: Provider plan entry dict.

    Returns:
        The effective audience allow-list, static entries first, then resolved
        refs in declaration order, de-duplicated.

    Raises:
        JwksValidationError: When a declared ref's environment variable is unset
            or empty.
    """
    audiences: list[str] = [str(a) for a in provider.get("allowedAudiences", [])]
    seen: set[str] = set(audiences)
    for raw_ref in provider.get("allowedAudienceRefs", []):
        ref_name: str = str(raw_ref)
        value: str = os.environ.get(ref_name, "").strip()
        if not value:
            logger.error(
                "identity_audience_ref_unresolved provider=%s env_var=%s reason_code=%s",
                provider_name,
                ref_name,
                _REASON_PROVIDER_CONFIG,
            )
            raise JwksValidationError(
                reason_code=_REASON_PROVIDER_CONFIG,
                message=(
                    "Provider '%s' declares the late-bound audience reference '%s' "
                    "in 'allowedAudienceRefs', but the environment variable '%s' is "
                    "unset or empty.  Expected: the audience value assigned by the "
                    "identity provider at provisioning time (for Entra, the app "
                    "registration's client-ID GUID).  Validation fails closed rather "
                    "than falling back to an unconstrained audience allow-list.  "
                    "Fix: deliver '%s' to this service as an application setting / "
                    "environment variable at deploy time."
                    % (provider_name, ref_name, ref_name, ref_name)
                ),
            )
        if value not in seen:
            seen.add(value)
            audiences.append(value)
    return audiences


def _select_provider(
    providers: dict[str, Any],
    token_iss: str,
    token_aud: set[str],
) -> tuple[str, dict[str, Any]] | None:
    """Select the provider plan entry matching the token's issuer and audience.

    A single OIDC instance (e.g. one Zitadel server) can host multiple projects
    that all share one issuer URL and differ only by audience (the project id
    carried in the token ``aud``).  Matching by issuer alone lets the
    first-declared provider win for every token from that instance, so a
    workforce token would be validated against the customer provider's
    ``allowedAudiences`` and fail with an audience mismatch.

    Selection rules, applied in order:

    1. Gather every provider whose ``issuer`` equals ``token_iss``.
    2. When exactly one matches, use it (audience is enforced later by decode).
    3. When several share the issuer, prefer the one whose non-empty EFFECTIVE
       audience allow-list intersects the token ``aud``.
    4. Otherwise prefer a provider that does not constrain audience (an empty
       effective allow-list accepts any audience).
    5. Otherwise fall back to the first issuer match so validation still fails
       closed with a deterministic ``audience_mismatch``.

    "Effective" means :func:`_effective_audiences` — static ``allowedAudiences``
    unioned with the resolved ``allowedAudienceRefs`` environment variables.  A
    declared ref that cannot be resolved raises rather than collapsing to an
    empty allow-list, so rule 4 can never be reached by an unresolved ref.

    Args:
        providers: The plan ``providers`` map (name -> entry).
        token_iss: The token's ``iss`` claim.
        token_aud: The token's ``aud`` claim normalized to a set.

    Returns:
        ``(provider_name, provider_entry)`` for the selected provider, or
        ``None`` when no provider's issuer matches the token.

    Raises:
        JwksValidationError: When an issuer-matched provider declares an audience
            ref whose environment variable is unset or empty.
    """
    issuer_matches: list[tuple[str, dict[str, Any]]] = [
        (name, entry)
        for name, entry in providers.items()
        if entry.get("issuer", "") == token_iss
    ]
    if not issuer_matches:
        return None
    if len(issuer_matches) == 1:
        return issuer_matches[0]
    resolved: list[tuple[str, dict[str, Any], set[str]]] = [
        (name, entry, set(_effective_audiences(name, entry)))
        for name, entry in issuer_matches
    ]
    for name, entry, allowed in resolved:
        if allowed & token_aud:
            return (name, entry)
    for name, entry, allowed in resolved:
        if not allowed:
            return (name, entry)
    return issuer_matches[0]


def resolve_provider_name(claims: dict[str, Any]) -> str | None:
    """Return the logical provider name that owns the given verified claims.

    Attributes a validated token to its true provider using the SAME issuer +
    audience selection as :func:`validate_token_claims` (via :func:`_select_provider`).
    A single OIDC instance can host several providers that share one issuer and
    differ only by audience (the project id in ``aud``); matching by issuer alone
    would mis-attribute a token to the first provider sharing that issuer.

    Surface guards call this to attribute a validated token to its true provider
    and then enforce the surface's provider allow-list: a genuine token whose
    provider is not permitted on a surface is an authorization denial (403), not a
    validation failure (401) — e.g. a workforce token on a customer-only surface.

    Args:
        claims: Verified JWT claims (as returned by :func:`validate_token_claims`).

    Returns:
        The logical provider name whose issuer + audience own the claims, or
        ``None`` when no provider's issuer matches (only possible for claims that
        did not originate from :func:`validate_token_claims`).

    Raises:
        JwksValidationError: When an issuer-matched provider declares an audience
            ref whose environment variable is unset or empty (fail-closed).
    """
    plan = _load_provider_plan()
    providers: dict[str, Any] = plan.get("providers", {})
    token_iss: str = str(claims.get("iss", ""))
    token_aud: set[str] = _token_audiences(claims)
    selection = _select_provider(providers, token_iss, token_aud)
    return None if selection is None else selection[0]


# ---------------------------------------------------------------------------
# Core validation
# ---------------------------------------------------------------------------


async def validate_token_claims(token: str) -> dict[str, Any]:
    """Validate a JWT and return its verified claims.

    All tokens are validated through the identity provider plan via JWKS.
    An unrecognized issuer fails closed with a reason code.

    Steps:
    1. Decode unverified payload to extract the ``iss`` and ``aud`` claims.
    2. Load provider plan, match provider by issuer (disambiguating by audience
       when several providers share one issuer), validate via JWKS.

    JWKS refresh failure fails closed: ``JwksValidationError`` with
    ``reason_code="jwks_refresh_failed"`` is raised rather than allowing
    an unverifiable token through.

    Args:
        token: Raw JWT Bearer token string (no ``Bearer `` prefix).

    Returns:
        Verified claims dict with ``roles`` key populated.

    Raises:
        JwksValidationError: On any validation failure.
    """
    # Decode unverified payload first to extract the issuer for provider matching.
    try:
        unverified_payload: dict[str, Any] = jwt.decode(
            token, options={"verify_signature": False}
        )
    except PyJWTError as exc:
        raise JwksValidationError(
            reason_code=_REASON_MALFORMED_TOKEN,
            message="Token payload could not be decoded: %s" % exc,
        ) from exc

    token_iss: str = str(unverified_payload.get("iss", ""))

    # Load provider plan and validate via JWKS.
    plan = _load_provider_plan()
    providers: dict[str, Any] = plan.get("providers", {})

    # Decode unverified header to identify algorithm and kid for JWKS lookup.
    try:
        unverified_header: dict[str, Any] = jwt.get_unverified_header(token)
    except PyJWTError as exc:
        raise JwksValidationError(
            reason_code=_REASON_MALFORMED_TOKEN,
            message="Token header could not be decoded: %s" % exc,
        ) from exc

    token_alg: str = str(unverified_header.get("alg", ""))
    token_kid: str = str(unverified_header.get("kid", ""))

    # Match provider by issuer, disambiguating by audience when several
    # providers share one issuer (e.g. multiple Zitadel projects on a single
    # instance — identical issuer URL, distinct project-id audiences).
    token_aud: set[str] = _token_audiences(unverified_payload)
    selection = _select_provider(providers, token_iss, token_aud)
    if selection is None:
        raise JwksValidationError(
            reason_code=_REASON_PROVIDER_MISMATCH,
            message=(
                "No configured provider matches the token issuer.  "
                "Ensure the provider plan includes a provider with issuer "
                "matching the token's 'iss' claim."
            ),
        )
    matched_provider_name, matched_provider = selection

    allowed_algorithms: list[str] = matched_provider.get("allowedAlgorithms", [])

    # Guard: reject symmetric / none from the plan allow-list itself.
    for alg in allowed_algorithms:
        _assert_asymmetric_algorithm(alg, matched_provider_name)

    # Guard: token algorithm must be in plan allow-list.
    if token_alg not in allowed_algorithms:
        raise JwksValidationError(
            reason_code=_REASON_BAD_SIGNATURE,
            message=(
                "Token algorithm '%s' is not in the provider '%s' allow-list %r.  "
                "The token must be signed with an algorithm declared in the "
                "provider plan 'allowedAlgorithms'."
                % (token_alg, matched_provider_name, allowed_algorithms)
            ),
        )
    # Double-guard: reject symmetric regardless of plan allow-list.
    _assert_asymmetric_algorithm(token_alg, matched_provider_name)

    jwks_uri: str = matched_provider.get("jwksUri", "")
    cache_ttl: int = int(matched_provider["jwksCacheTtlSeconds"])
    jwks_client = _get_jwks_client(matched_provider_name, jwks_uri, cache_ttl)

    # Resolve signing key — on unknown kid, refresh JWKS once (DN38).
    try:
        signing_key = await asyncio.to_thread(
            jwks_client.get_signing_key_from_jwt, token
        )
    except (PyJWKClientError, PyJWKSetError):
        logger.warning(
            "identity_jwks_key_miss provider=%s kid=%s refreshing",
            matched_provider_name,
            token_kid or "(none)",
        )
        try:
            await asyncio.to_thread(jwks_client.fetch_data)
            signing_key = await asyncio.to_thread(
                jwks_client.get_signing_key_from_jwt, token
            )
        except Exception as refresh_exc:
            logger.warning(
                "identity_jwks_refresh_failed provider=%s reason_code=%s",
                matched_provider_name,
                _REASON_JWKS_REFRESH_FAILED,
            )
            raise JwksValidationError(
                reason_code=_REASON_JWKS_REFRESH_FAILED,
                message=(
                    "JWKS refresh failed for provider '%s': %s.  "
                    "The token cannot be verified (fail-closed)."
                    % (matched_provider_name, refresh_exc)
                ),
            ) from refresh_exc

    # Full verification with asymmetric key.  Audiences are the EFFECTIVE list:
    # static allowedAudiences U resolved allowedAudienceRefs (fails closed when a
    # declared ref's env var is unset — never an unconstrained empty list).
    allowed_audiences: list[str] = _effective_audiences(
        matched_provider_name, matched_provider
    )
    try:
        claims: dict[str, Any] = jwt.decode(
            token,
            signing_key.key,
            algorithms=allowed_algorithms,
            issuer=token_iss,
            audience=allowed_audiences if allowed_audiences else None,
            options={"require": ["exp", "iss"]},
        )
    except ExpiredSignatureError as exc:
        raise JwksValidationError(
            reason_code=_REASON_EXPIRED_TOKEN,
            message="Token has expired.",
        ) from exc
    except InvalidSignatureError as exc:
        raise JwksValidationError(
            reason_code=_REASON_BAD_SIGNATURE,
            message="Token signature is invalid.",
        ) from exc
    except InvalidAudienceError as exc:
        raise JwksValidationError(
            reason_code=_REASON_AUDIENCE_MISMATCH,
            message="Token audience does not match the expected audience.",
        ) from exc
    except InvalidIssuerError as exc:
        raise JwksValidationError(
            reason_code=_REASON_ISSUER_MISMATCH,
            message="Token issuer does not match the configured issuer.",
        ) from exc
    except DecodeError as exc:
        raise JwksValidationError(
            reason_code=_REASON_MALFORMED_TOKEN,
            message="Token could not be decoded: %s" % exc,
        ) from exc
    except PyJWTError as exc:
        raise JwksValidationError(
            reason_code=_REASON_BAD_SIGNATURE,
            message="Token verification failed: %s" % exc,
        ) from exc

    # Populate roles from provider roleSource / roleMappings.
    claims["roles"] = _extract_roles(claims, matched_provider)

    # Edge-enforce required identityFields (attributeMappings with guarantee=required).
    # Claims declared guarantee=required must be present in the verified token; a missing
    # claim is an opaque 401 (reason code to logs only) rather than a downstream 500.
    attribute_mappings: dict[str, Any] = matched_provider.get("attributeMappings", {})
    for field_name, field_cfg in attribute_mappings.items():
        if str(field_cfg.get("guarantee", "")) == "required":
            claim_path: str = str(field_cfg.get("claimPath", field_name))
            if _resolve_claim_path(claims, claim_path) is None:
                logger.warning(
                    "identity_auth_failed reason_code=%s field=%s provider=%s",
                    _REASON_REQUIRED_FIELD_MISSING,
                    field_name,
                    matched_provider_name,
                )
                raise JwksValidationError(
                    reason_code=_REASON_REQUIRED_FIELD_MISSING,
                    message=(
                        "Required identity field '%s' (claim path '%s') is absent from the "
                        "verified token for provider '%s'.  "
                        "The provider must include this claim in every issued token."
                        % (field_name, claim_path, matched_provider_name)
                    ),
                )

    return claims
