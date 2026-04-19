"""Internal API dependency for ecommerce.ProductService.

Generated only when the service has internal endpoints. Validates X-Internal-Token
header against INTERNAL_API_TOKEN from config.
"""

import os

from fastapi import Depends, Header, HTTPException, status


INTERNAL_API_TOKEN = os.environ["INTERNAL_API_TOKEN"]


async def require_internal(
    x_internal_token: str = Header(..., alias="X-Internal-Token"),
) -> None:
    """Raise 403 if X-Internal-Token does not match INTERNAL_API_TOKEN."""
    if x_internal_token != INTERNAL_API_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing internal API token",
        )
