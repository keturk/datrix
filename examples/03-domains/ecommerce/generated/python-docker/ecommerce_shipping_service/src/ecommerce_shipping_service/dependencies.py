"""Service endpoint dependency for ecommerce.ShippingService.

Generated when the service has service-to-service endpoints. Validates
inbound machine-identity credentials through the provider-plan path
(``identity.validate_token_claims``) and enforces the provider allow-list
declared in the DSL (``auth(service, providers: [...]``). The caller presents
its platform-managed machine identity; there is no self-signed service token.
"""

from __future__ import annotations

import logging
from typing import Final

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ecommerce_shipping_service.identity import (
    JwksValidationError,
    resolve_provider_name,
    validate_token_claims,
)

logger = logging.getLogger(__name__)

_service_endpoint_bearer = HTTPBearer(auto_error=True)

# DSL-declared provider allow-list for auth(service, providers: [...]) endpoints.
# Built from the union of all providers across every service endpoint in this service.
# A token whose provider is not in this set is rejected with 401 even if the
# JWT signature and claims are otherwise valid — user tokens from non-service
# providers (e.g. customer, test_auth) are not machine identities.
_ALLOWED_SERVICE_PROVIDERS: Final[frozenset[str]] = frozenset(
    {
        "platform",
    }
)


async def require_service_endpoint(
    credentials: HTTPAuthorizationCredentials = Depends(_service_endpoint_bearer),
) -> None:
    """Raise 401 if the inbound machine-identity credential is not valid.

    Validation has two stages:
    1. Token signature, issuer, audience, and expiry are verified via the
       provider-plan JWKS path (``validate_token_claims``).  A token that
       fails this check is rejected immediately.
    2. The resolved provider name is checked against the DSL-declared
       allow-list (``_ALLOWED_SERVICE_PROVIDERS``).  A validly signed user
       token from a non-service provider (e.g. ``customer``, ``test_auth``)
       is rejected here — it is a valid credential but not a machine identity.

    A self-signed service token is never accepted here.
    """
    try:
        claims = await validate_token_claims(credentials.credentials)
    except JwksValidationError as exc:
        logger.warning("service_credential_rejected reason=%s", exc.reason_code)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired service credential",
        ) from exc
    provider = resolve_provider_name(claims) or ""
    if provider not in _ALLOWED_SERVICE_PROVIDERS:
        logger.warning(
            "service_credential_rejected reason=%s provider=%s allowed=%s",
            "provider_not_allowed",
            provider,
            sorted(_ALLOWED_SERVICE_PROVIDERS),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired service credential",
        )
    logger.debug("service_credential_accepted")
