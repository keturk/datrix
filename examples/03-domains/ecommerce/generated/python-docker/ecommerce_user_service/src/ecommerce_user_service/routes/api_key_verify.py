"""_api_key_verify route handlers."""

from fastapi import APIRouter, Body, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ecommerce_user_service.api_key_verification import (
    ApiKeyVerifyResponse,
    answer_api_key_verification,
)
from ecommerce_user_service.auth import require_route
from ecommerce_user_service.rate_limit.rate_limit_dependency import (
    enforce_plan_rate_limit,
)
from ecommerce_user_service.schemas.api_key_verify_request import _ApiKeyVerifyRequest
from ecommerce_user_service.user_db.session import get_user_db_db

router = APIRouter(
    prefix="/internal/identity/api-keys",
    tags=["_api_key_verify"],
)


@router.post(
    "/customerKeys/verify", response_model=ApiKeyVerifyResponse, include_in_schema=False
)
async def post_customer_keys_verify(
    request: _ApiKeyVerifyRequest = Body(...),
    user_db: AsyncSession = Depends(get_user_db_db),
    current_user=Depends(
        require_route(
            providers=["platform", "test_auth"], roles=[], principal_types=["machine"]
        )
    ),
    _rate_limit=Depends(enforce_plan_rate_limit),
) -> ApiKeyVerifyResponse:
    return await answer_api_key_verification(user_db, "customerKeys", request.key_hash)
