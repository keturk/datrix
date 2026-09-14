"""UserAPI route handlers."""

import datetime
import json
import random
import re
import string
import uuid

import bcrypt
import validators
from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query
from fastapi import status as http_status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from ecommerce_user_service._cache_helpers import _get_redis
from ecommerce_user_service.auth import (
    get_current_user,
    require_providers,
    require_roles,
)
from ecommerce_user_service.dependencies import require_service_endpoint
from ecommerce_user_service.enums.user_role import UserRole
from ecommerce_user_service.enums.user_status import UserStatus
from ecommerce_user_service.event_outbox import buffer_events as _datrix_buffer_events
from ecommerce_user_service.functions import send_password_reset_email
from ecommerce_user_service.models.user_db.user import User
from ecommerce_user_service.models.user_db.user_session import UserSession
from ecommerce_user_service.mq import producer as _mq_producer
from ecommerce_user_service.rate_limit.rate_limit_dependency import (
    enforce_plan_rate_limit,
)
from ecommerce_user_service.schemas.change_password_request import ChangePasswordRequest
from ecommerce_user_service.schemas.forgot_password_request import ForgotPasswordRequest
from ecommerce_user_service.schemas.login_request import LoginRequest
from ecommerce_user_service.schemas.login_response import LoginResponse
from ecommerce_user_service.schemas.logout_request import LogoutRequest
from ecommerce_user_service.schemas.register_request import RegisterRequest
from ecommerce_user_service.schemas.reset_password_request import ResetPasswordRequest
from ecommerce_user_service.schemas.session_validation_response import (
    SessionValidationResponse,
)
from ecommerce_user_service.schemas.update_profile_request import UpdateProfileRequest
from ecommerce_user_service.schemas.update_user_status_request import (
    UpdateUserStatusRequest,
)
from ecommerce_user_service.schemas.user_db.user import (
    UserCreate,
    UserResponse,
    UserUpdate,
)
from ecommerce_user_service.schemas.user_db.user_session import (
    UserSessionCreate,
    UserSessionResponse,
)
from ecommerce_user_service.schemas.validate_session_request import (
    ValidateSessionRequest,
)
from ecommerce_user_service.schemas.verify_email_request import VerifyEmailRequest
from ecommerce_user_service.services.user_db.user_service import UserService
from ecommerce_user_service.services.user_db.user_session_service import (
    UserSessionService,
)
from ecommerce_user_service.user_db.session import get_user_db_db

router = APIRouter(
    prefix="/api/v1",
    tags=["UserAPI"],
)


async def generate_session_token() -> str:
    return (
        f"session_{''.join(random.choices(string.ascii_letters + string.digits, k=64))}"
    )


@router.get(
    "/users",
    response_model=list[UserResponse],
    dependencies=[Depends(require_providers(["identity", "test_auth"]))],
)
async def list_users(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    user_db: AsyncSession = Depends(get_user_db_db),
    current_user=Depends(require_roles([UserRole.admin])),
    _rate_limit=Depends(enforce_plan_rate_limit),
) -> list[User]:
    service = UserService(user_db)
    return await service.get_all(skip=skip, limit=limit)


@router.post(
    "/users",
    response_model=UserResponse,
    status_code=http_status.HTTP_201_CREATED,
    dependencies=[Depends(require_providers(["identity", "test_auth"]))],
)
async def create_user(
    body: UserCreate = Body(...),
    user_db: AsyncSession = Depends(get_user_db_db),
    current_user=Depends(require_roles([UserRole.admin])),
    _rate_limit=Depends(enforce_plan_rate_limit),
) -> User:
    service = UserService(user_db)
    return await service.create(body)


@router.post("/register", response_model=UserResponse)
async def post_register(
    request: RegisterRequest = Body(...),
    user_db: AsyncSession = Depends(get_user_db_db),
    _rate_limit=Depends(enforce_plan_rate_limit),
) -> User:
    if not bool(validators.email(request.email)):
        raise HTTPException(status_code=422, detail="Invalid email format")
    if len(request.password) < 8:
        raise HTTPException(
            status_code=422, detail="Password must be at least 8 characters"
        )
    if (
        (not bool(re.search(r"[a-z]", request.password)))
        or (not bool(re.search(r"[A-Z]", request.password)))
    ) or (not bool(re.search(r"\d", request.password))):
        raise HTTPException(
            status_code=422,
            detail="Password must contain lowercase, uppercase, and numbers",
        )
    existing: User | None = (
        (await user_db.execute(select(User).where(User.email == request.email)))
        .scalars()
        .first()
    )
    if existing is not None:
        raise HTTPException(status_code=422, detail="Email already registered")
    _user_svc = UserService(user_db)
    user = await _user_svc.create(
        UserCreate(
            **{
                "email": request.email,
                "password_hash": bcrypt.hashpw(
                    request.password.encode(), bcrypt.gensalt()
                ).decode(),
                "first_name": request.first_name,
                "last_name": request.last_name,
                "role": UserRole.customer,
                "status": UserStatus.pending,
                "email_verification_token": "".join(
                    random.choices(string.ascii_letters + string.digits, k=32)
                ),
            }
        )
    )
    return user


@router.post("/login", response_model=LoginResponse)
async def post_login(
    http_request: Request,
    request: LoginRequest = Body(...),
    user_db: AsyncSession = Depends(get_user_db_db),
    _rate_limit=Depends(enforce_plan_rate_limit),
) -> LoginResponse:
    # 'firstOrFail()' throws NotFoundException if no match
    user = (
        (await user_db.execute(select(User).where(User.email == request.email)))
        .scalars()
        .first()
    )
    if user is None:
        raise HTTPException(status_code=404, detail="Not found")
    if not bcrypt.checkpw(request.password.encode(), user.password_hash.encode()):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.can_login:
        raise HTTPException(status_code=401, detail="Account is not active or verified")
    token: str = await generate_session_token()
    _user_session_svc = UserSessionService(user_db)
    session = await _user_session_svc.create(
        UserSessionCreate(
            **{
                "user_id": user.id,
                "token": token,
                "device_name": http_request.headers.get("user-agent", ""),
                "ip_address": http_request.client.host,
                "user_agent": http_request.headers.get("user-agent", ""),
                "expires_at": (
                    datetime.datetime.now(datetime.timezone.utc)
                    + datetime.timedelta(days=30)
                ),
                "last_activity_at": datetime.datetime.now(datetime.timezone.utc),
            }
        )
    )
    user.last_login_at = datetime.datetime.now(datetime.timezone.utc)
    _user_svc = UserService(user_db)
    user = await _user_svc.update(
        user.id,
        UserUpdate(**{"last_login_at": datetime.datetime.now(datetime.timezone.utc)}),
    )
    # Store session in cache for fast validation
    await __import__("asyncio").gather(
        _get_redis().hset(
            ("session:" + f":{str(token)}"),
            mapping={
                str(_k): json.dumps(_v, default=str)
                for _k, _v in {
                    "sessionId": token,
                    "userId": user.id,
                    "lastActivity": datetime.datetime.now(datetime.timezone.utc),
                }.items()
            },
        ),
        _get_redis().expire(("session:" + f":{str(token)}"), 2592000),
    )
    async with _datrix_buffer_events():
        _producer_instance = await _mq_producer.get_producer()
        await _producer_instance.publish_user_logged_in(
            user.id,
            datetime.datetime.now(datetime.timezone.utc),
            http_request.client.host,
        )
    return LoginResponse(user=user, token=token, expires_at=session.expires_at)


@router.post(
    "/logout", dependencies=[Depends(require_providers(["identity", "test_auth"]))]
)
async def post_logout(
    request: LogoutRequest = Body(...),
    user_db: AsyncSession = Depends(get_user_db_db),
    current_user=Depends(get_current_user),
    _rate_limit=Depends(enforce_plan_rate_limit),
) -> None:
    token: str = current_user.token
    session: UserSession | None = (
        (await user_db.execute(select(UserSession).where(UserSession.token == token)))
        .scalars()
        .first()
    )
    if session is not None:
        if session is None:
            raise HTTPException(status_code=404, detail="Not found")
        await user_db.delete(session)
        await user_db.commit()
    await _get_redis().delete(("session:" + f":{str(token)}"))


@router.get(
    "/me",
    response_model=UserResponse,
    dependencies=[Depends(require_providers(["identity", "test_auth"]))],
)
async def get_me(
    user_db: AsyncSession = Depends(get_user_db_db),
    current_user=Depends(get_current_user),
    _rate_limit=Depends(enforce_plan_rate_limit),
) -> User:
    return await UserService(user_db).get(current_user.profile_id)


@router.put(
    "/me",
    response_model=UserResponse,
    dependencies=[Depends(require_providers(["identity", "test_auth"]))],
)
async def put_me(
    request: UpdateProfileRequest = Body(...),
    user_db: AsyncSession = Depends(get_user_db_db),
    current_user=Depends(get_current_user),
    _rate_limit=Depends(enforce_plan_rate_limit),
) -> User:
    user = await UserService(user_db).get(current_user.profile_id)
    if request.first_name is not None:
        user.first_name = request.first_name
    if request.last_name is not None:
        user.last_name = request.last_name
    if request.phone_number is not None:
        user.phone_number = request.phone_number
    if request.shipping_address is not None:
        user.shipping_address = request.shipping_address
    if request.billing_address is not None:
        user.billing_address = request.billing_address
    _user_svc = UserService(user_db)
    user = await _user_svc.update(
        user.id,
        UserUpdate(
            **{
                "billing_address": request.billing_address,
                "first_name": request.first_name,
                "last_name": request.last_name,
                "phone_number": request.phone_number,
                "shipping_address": request.shipping_address,
            }
        ),
    )
    return user


@router.put(
    "/me/password", dependencies=[Depends(require_providers(["identity", "test_auth"]))]
)
async def put_me_password(
    request: ChangePasswordRequest = Body(...),
    user_db: AsyncSession = Depends(get_user_db_db),
    current_user=Depends(get_current_user),
    _rate_limit=Depends(enforce_plan_rate_limit),
) -> None:
    user = await UserService(user_db).get(current_user.profile_id)
    if not bcrypt.checkpw(
        request.current_password.encode(), user.password_hash.encode()
    ):
        raise HTTPException(status_code=422, detail="Current password is incorrect")
    user.password_hash = bcrypt.hashpw(
        request.new_password.encode(), bcrypt.gensalt()
    ).decode()
    _user_svc = UserService(user_db)
    user = await _user_svc.update(
        user.id,
        UserUpdate(
            **{
                "password_hash": bcrypt.hashpw(
                    request.new_password.encode(), bcrypt.gensalt()
                ).decode()
            }
        ),
    )


@router.post("/verify-email", response_model=UserResponse)
async def post_verify_email(
    request: VerifyEmailRequest = Body(...),
    user_db: AsyncSession = Depends(get_user_db_db),
    _rate_limit=Depends(enforce_plan_rate_limit),
) -> User:
    user = (
        (
            await user_db.execute(
                select(User).where(User.email_verification_token == request.token)
            )
        )
        .scalars()
        .first()
    )
    if user is None:
        raise HTTPException(status_code=404, detail="Not found")
    user.email_verified_at = datetime.datetime.now(datetime.timezone.utc)
    user.email_verification_token = None
    user.status = UserStatus.active
    _user_svc = UserService(user_db)
    user = await _user_svc.update(
        user.id,
        UserUpdate(
            **{
                "email_verification_token": None,
                "email_verified_at": datetime.datetime.now(datetime.timezone.utc),
                "status": UserStatus.active,
            }
        ),
    )
    return user


@router.post("/forgot-password")
async def post_forgot_password(
    request: ForgotPasswordRequest = Body(...),
    user_db: AsyncSession = Depends(get_user_db_db),
    _rate_limit=Depends(enforce_plan_rate_limit),
) -> None:
    user: User | None = (
        (await user_db.execute(select(User).where(User.email == request.email)))
        .scalars()
        .first()
    )
    if user is not None:
        user.password_reset_token = "".join(
            random.choices(string.ascii_letters + string.digits, k=32)
        )
        user.password_reset_expiry = datetime.datetime.now(
            datetime.timezone.utc
        ) + datetime.timedelta(hours=24)
        user_db.add(user)
        await user_db.commit()
        await user_db.refresh(user)
        await send_password_reset_email(user)


@router.post("/reset-password", response_model=UserResponse)
async def post_reset_password(
    request: ResetPasswordRequest = Body(...),
    user_db: AsyncSession = Depends(get_user_db_db),
    _rate_limit=Depends(enforce_plan_rate_limit),
) -> User:
    user = (
        (
            await user_db.execute(
                select(User).where(User.password_reset_token == request.token)
            )
        )
        .scalars()
        .first()
    )
    if user is None:
        raise HTTPException(status_code=404, detail="Not found")
    if (user.password_reset_expiry is None) or (
        datetime.datetime.now(datetime.timezone.utc) > user.password_reset_expiry
    ):
        raise HTTPException(status_code=422, detail="Password reset token has expired")
    user.password_hash = bcrypt.hashpw(
        request.new_password.encode(), bcrypt.gensalt()
    ).decode()
    user.password_reset_token = None
    user.password_reset_expiry = None
    _user_svc = UserService(user_db)
    user = await _user_svc.update(
        user.id,
        UserUpdate(
            **{
                "password_hash": bcrypt.hashpw(
                    request.new_password.encode(), bcrypt.gensalt()
                ).decode(),
                "password_reset_expiry": None,
                "password_reset_token": None,
            }
        ),
    )
    return user


@router.post(
    "/service/validate-session",
    response_model=SessionValidationResponse,
    include_in_schema=False,
    dependencies=[Depends(require_service_endpoint)],
)
async def post_service_validate_session(
    request: ValidateSessionRequest = Body(...),
    user_db: AsyncSession = Depends(get_user_db_db),
    current_user=Depends(get_current_user),
    _rate_limit=Depends(enforce_plan_rate_limit),
) -> SessionValidationResponse:
    session: UserSession | None = (
        (
            await user_db.execute(
                select(UserSession).where(UserSession.token == request.token)
            )
        )
        .scalars()
        .first()
    )
    if (session is None) or session.is_expired:
        return SessionValidationResponse(valid=False, user=None)
    session.last_activity_at = datetime.datetime.now(datetime.timezone.utc)
    user_db.add(session)
    await user_db.commit()
    await user_db.refresh(session)
    return SessionValidationResponse(valid=True, user=session.user)


@router.get(
    "/users/{id}/user_sessions",
    response_model=list[UserSessionResponse],
    dependencies=[Depends(require_providers(["test_auth"]))],
)
async def list_user_sessions(
    id: uuid.UUID = Path(...),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    user_db: AsyncSession = Depends(get_user_db_db),
    current_user=Depends(get_current_user),
    _rate_limit=Depends(enforce_plan_rate_limit),
) -> list[UserSession]:
    # Verify parent exists (raises EntityNotFoundError -> 404)
    user_service = UserService(user_db)
    await user_service.get(id)
    # Get children
    user_session_service = UserSessionService(user_db)
    return await user_session_service.get_by_user(user_id=id, skip=skip, limit=limit)


# @internal marks endpoints as internal-only, not exposed through the API gateway
@router.get(
    "/service/{id}",
    response_model=UserResponse,
    include_in_schema=False,
    dependencies=[Depends(require_service_endpoint)],
)
async def get_service_by_id(
    id: uuid.UUID = Path(...),
    user_db: AsyncSession = Depends(get_user_db_db),
    current_user=Depends(get_current_user),
    _rate_limit=Depends(enforce_plan_rate_limit),
) -> User:
    service = UserService(user_db)
    return await service.get(id)


@router.get(
    "/users/{id}",
    response_model=UserResponse,
    dependencies=[Depends(require_providers(["identity", "test_auth"]))],
)
async def get_user(
    id: uuid.UUID = Path(...),
    user_db: AsyncSession = Depends(get_user_db_db),
    current_user=Depends(require_roles([UserRole.admin])),
    _rate_limit=Depends(enforce_plan_rate_limit),
) -> User:
    service = UserService(user_db)
    return await service.get(id)


@router.put(
    "/users/{id}",
    response_model=UserResponse,
    dependencies=[Depends(require_providers(["identity", "test_auth"]))],
)
async def update_user(
    body: UserUpdate = Body(...),
    id: uuid.UUID = Path(...),
    user_db: AsyncSession = Depends(get_user_db_db),
    current_user=Depends(require_roles([UserRole.admin])),
    _rate_limit=Depends(enforce_plan_rate_limit),
) -> User:
    service = UserService(user_db)
    return await service.update(id, body)


@router.delete(
    "/users/{id}",
    status_code=http_status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_providers(["identity", "test_auth"]))],
)
async def delete_user(
    id: uuid.UUID = Path(...),
    user_db: AsyncSession = Depends(get_user_db_db),
    current_user=Depends(require_roles([UserRole.admin])),
    _rate_limit=Depends(enforce_plan_rate_limit),
) -> None:
    service = UserService(user_db)
    await service.delete(id)


@router.put(
    "/{id}/status",
    response_model=UserResponse,
    dependencies=[Depends(require_providers(["identity", "test_auth"]))],
)
async def put_by_id_status(
    request: UpdateUserStatusRequest = Body(...),
    id: uuid.UUID = Path(...),
    user_db: AsyncSession = Depends(get_user_db_db),
    current_user=Depends(require_roles([UserRole.admin])),
    _rate_limit=Depends(enforce_plan_rate_limit),
) -> User:
    service = UserService(user_db)
    user = await service.get(id)
    if user is None:
        raise HTTPException(status_code=404, detail="Not found")
    user.status = request.status
    _user_svc = UserService(user_db)
    user = await _user_svc.update(user.id, UserUpdate(**{"status": request.status}))
    return user
