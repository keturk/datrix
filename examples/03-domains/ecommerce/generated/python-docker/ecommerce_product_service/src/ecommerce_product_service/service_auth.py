"""Service-to-service authentication for ecommerce.ProductService.

JWT-based machine identity for internal API calls between services.
Tokens are issued by the configured identity provider (managed machine identity).
Only asymmetric algorithms (RS*, ES*, PS*) are used — symmetric (HS*) and
``alg: none`` are rejected.
"""

from __future__ import annotations

import logging

import jwt
from jwt import InvalidTokenError

from ecommerce_product_service.config._secrets_resolver import get_secret
from ecommerce_product_service.config.settings import get_settings

logger = logging.getLogger(__name__)

_ISSUER: str = "datrix-service-auth"
_REJECTED_ALG_PREFIXES: tuple[str, ...] = ("HS",)
_REJECTED_ALG_NONE: str = "none"


def _assert_asymmetric_algorithm(algorithm: str) -> None:
    """Raise ``InvalidTokenError`` when the algorithm is symmetric or ``none``.

    Args:
        algorithm: JWS algorithm identifier to check.

    Raises:
        InvalidTokenError: When a symmetric (HS*) or ``none`` algorithm is used.
    """
    if algorithm.lower() == _REJECTED_ALG_NONE or any(
        algorithm.startswith(p) for p in _REJECTED_ALG_PREFIXES
    ):
        raise InvalidTokenError(
            "Service auth algorithm '%s' is rejected: only asymmetric algorithms "
            "(RS*, ES*, PS*) are permitted for service-to-service tokens.  "
            "Update SERVICE_JWT_ALGORITHM to use an asymmetric algorithm." % algorithm
        )


async def verify_service_token(token: str) -> dict[str, object]:
    """Verify a service-to-service JWT.

    Resolves the asymmetric public key through the secrets resolver on each
    verification (RESOLVE_ON_ACCESS) so a rotated key propagates after TTL
    expiry; the key is never snapshotted into frozen settings. Symmetric
    algorithms (HS*) and ``none`` are always rejected.

    Args:
        token: JWT to verify (no Bearer prefix).

    Returns:
        Decoded token claims.

    Raises:
        InvalidTokenError: If token is invalid, expired, uses a rejected algorithm,
            or is not a service token.
    """
    settings = get_settings()
    algorithm: str = settings.jwt_algorithm
    _assert_asymmetric_algorithm(algorithm)
    public_key = await get_secret("jwt_public_key")
    decoded: dict[str, object] = jwt.decode(
        token,
        public_key,
        algorithms=[algorithm],
        options={"require": ["exp"]},
    )
    if decoded.get("type") != "service":
        raise InvalidTokenError("Token type is not service")
    if decoded.get("iss") != _ISSUER:
        raise InvalidTokenError("Invalid token issuer")
    if not decoded.get("sub"):
        raise InvalidTokenError("Token missing sub claim")
    return decoded
