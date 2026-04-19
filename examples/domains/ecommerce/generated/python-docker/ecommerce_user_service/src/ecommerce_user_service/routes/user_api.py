"""UserAPI route handlers."""

from fastapi import (
    APIRouter,
    Body,
    Depends,
    HTTPException,
    Path,
    Query,
)
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession
from ecommerce_user_service.db.session import get_db_db
from ecommerce_user_service.auth import get_current_user, require_roles
from ecommerce_user_service._cache_helpers import _get_redis
from ecommerce_user_service.dependencies import require_internal
from ecommerce_user_service.enums.user_role import UserRole
from ecommerce_user_service.enums.user_status import UserStatus
from ecommerce_user_service.functions import generate_token
from ecommerce_user_service.functions import hash_password
from ecommerce_user_service.functions import send_password_reset_email
from ecommerce_user_service.functions import verify_password
from ecommerce_user_service.models.db.user import User
from ecommerce_user_service.models.db.user_session import UserSession
from ecommerce_user_service.mq.producer import producer_instance as _producer_instance
from ecommerce_user_service.schemas.change_password_request import ChangePasswordRequest
from ecommerce_user_service.schemas.db.user import UserCreate, UserUpdate, UserResponse
from ecommerce_user_service.schemas.db.user_session import UserSessionResponse
from ecommerce_user_service.schemas.forgot_password_request import ForgotPasswordRequest
from ecommerce_user_service.schemas.login_request import LoginRequest
from ecommerce_user_service.schemas.login_response import LoginResponse
from ecommerce_user_service.schemas.logout_request import LogoutRequest
from ecommerce_user_service.schemas.register_request import RegisterRequest
from ecommerce_user_service.schemas.reset_password_request import ResetPasswordRequest
from ecommerce_user_service.schemas.session_validation_response import SessionValidationResponse
from ecommerce_user_service.schemas.update_profile_request import UpdateProfileRequest
from ecommerce_user_service.schemas.update_user_status_request import UpdateUserStatusRequest
from ecommerce_user_service.schemas.validate_session_request import ValidateSessionRequest
from ecommerce_user_service.schemas.verify_email_request import VerifyEmailRequest
from ecommerce_user_service.services.db.user_service import UserService
from ecommerce_user_service.services.db.user_session_service import UserSessionService
from sqlalchemy import select
import datetime
import json
import random
import re
import string
import uuid
import validators

router = APIRouter(
    prefix="/api/v1",
    tags=["UserAPI"],
)


async def generate_session_token() -> str:
    return f"session_{''.join(random.choices(string.ascii_letters + string.digits, k=64))}"


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_db),
    current_user=Depends(require_roles([UserRole.admin])),
) -> list[User]:
    service = UserService(db)
    return await service.get_all(skip=skip, limit=limit)


@router.post("/users", response_model=UserResponse, status_code=http_status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate = Body(...),
    db: AsyncSession = Depends(get_db_db),
    current_user=Depends(require_roles([UserRole.admin])),
) -> User:
    service = UserService(db)
    return await service.create(body)


@router.post("/register", response_model=UserResponse, status_code=http_status.HTTP_201_CREATED)
async def post_register(
    request: RegisterRequest = Body(...),
    db: AsyncSession = Depends(get_db_db),
) -> User:
    if not bool(validators.email(request.email)):
        raise HTTPException(status_code=422, detail="Invalid email format")
    if len(request.password) < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters")
    if (
        (not bool(re.search(r"[a-z]", request.password)))
        or (not bool(re.search(r"[A-Z]", request.password)))
    ) or (not bool(re.search(r"\d", request.password))):
        raise HTTPException(
            status_code=422, detail="Password must contain lowercase, uppercase, and numbers"
        )
    existing: User | None = (
        (await db.execute(select(User).where(User.email == request.email))).scalars().first()
    )
    if existing != None:
        raise HTTPException(status_code=422, detail="Email already registered")
    user = User(
        **{
            "email": request.email,
            "password_hash": hash_password(request.password),
            "first_name": request.first_name,
            "last_name": request.last_name,
            "role": UserRole.customer,
            "status": UserStatus.pending,
            "email_verification_token": generate_token(),
        }
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


@router.post("/login", response_model=LoginResponse, status_code=http_status.HTTP_201_CREATED)
async def post_login(
    request: LoginRequest = Body(...),
    db: AsyncSession = Depends(get_db_db),
) -> LoginResponse:
    user = (await db.execute(select(User).where(User.email == request.email))).scalars().first()
    if user is None:
        raise HTTPException(status_code=404, detail="Not found")
    if not verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.can_login:
        raise HTTPException(status_code=401, detail="Account is not active or verified")
    token: str = await generate_session_token()
    session = UserSession(
        **{
            "user": user,
            "token": token,
            "device_name": request.headers.get("user-agent", ""),
            "ip_address": request.client.host,
            "user_agent": request.headers.get("user-agent", ""),
            "expires_at": (
                datetime.datetime.now(tz=datetime.timezone.utc) + datetime.timedelta(days=30)
            ),
            "last_activity_at": datetime.datetime.now(tz=datetime.timezone.utc),
        }
    )
    db.add(session)
    await db.flush()
    await db.refresh(session)
    user.last_login_at = datetime.datetime.now(tz=datetime.timezone.utc)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    await _get_redis().set(
        f"session_cache:{str(token)}",
        json.dumps(
            {
                "session_id": token,
                "user_id": user.id,
                "last_activity": datetime.datetime.now(tz=datetime.timezone.utc),
            },
            default=str,
        ),
    )
    await _producer_instance.publish_user_logged_in(
        user.id, datetime.datetime.now(tz=datetime.timezone.utc), request.client.host
    )
    return LoginResponse(user=user, token=token, expires_at=session.expires_at)


@router.post("/logout", status_code=http_status.HTTP_201_CREATED)
async def post_logout(
    request: LogoutRequest = Body(...),
    db: AsyncSession = Depends(get_db_db),
    current_user=Depends(get_current_user),
) -> None:
    token: str = current_user.token
    session: UserSession | None = (
        (await db.execute(select(UserSession).where(UserSession.token == token))).scalars().first()
    )
    if session != None:
        await db.delete(session)
        await db.commit()
    await _get_redis().delete(f"session_cache:{str(token)}")


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user=Depends(get_current_user),
) -> User:
    return current_user


@router.patch("/me", response_model=UserResponse)
async def put_me(
    request: UpdateProfileRequest = Body(...),
    db: AsyncSession = Depends(get_db_db),
    current_user=Depends(get_current_user),
) -> User:
    user: User = current_user
    if request.first_name != None:
        user.first_name = request.first_name
    if request.last_name != None:
        user.last_name = request.last_name
    if request.phone_number != None:
        user.phone_number = request.phone_number
    if request.shipping_address != None:
        user.shipping_address = request.shipping_address
    if request.billing_address != None:
        user.billing_address = request.billing_address
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.put("/me/password")
async def put_me_password(
    request: ChangePasswordRequest = Body(...),
    db: AsyncSession = Depends(get_db_db),
    current_user=Depends(get_current_user),
) -> None:
    user: User = current_user
    if not verify_password(request.current_password, user.password_hash):
        raise HTTPException(status_code=422, detail="Current password is incorrect")
    user.password_hash = hash_password(request.new_password)
    db.add(user)
    await db.commit()
    await db.refresh(user)


@router.post("/verify-email", response_model=UserResponse, status_code=http_status.HTTP_201_CREATED)
async def post_verify_email(
    request: VerifyEmailRequest = Body(...),
    db: AsyncSession = Depends(get_db_db),
) -> User:
    user = (
        (await db.execute(select(User).where(User.email_verification_token == request.token)))
        .scalars()
        .first()
    )
    if user is None:
        raise HTTPException(status_code=404, detail="Not found")
    user.email_verified_at = datetime.datetime.now(tz=datetime.timezone.utc)
    user.email_verification_token = None
    user.status = UserStatus.active
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/forgot-password", status_code=http_status.HTTP_201_CREATED)
async def post_forgot_password(
    request: ForgotPasswordRequest = Body(...),
    db: AsyncSession = Depends(get_db_db),
) -> None:
    user: User | None = (
        (await db.execute(select(User).where(User.email == request.email))).scalars().first()
    )
    if user != None:
        user.password_reset_token = generate_token()
        user.password_reset_expiry = datetime.datetime.now(
            tz=datetime.timezone.utc
        ) + datetime.timedelta(hours=24)
        db.add(user)
        await db.commit()
        await db.refresh(user)
        send_password_reset_email(user)


@router.post(
    "/reset-password", response_model=UserResponse, status_code=http_status.HTTP_201_CREATED
)
async def post_reset_password(
    request: ResetPasswordRequest = Body(...),
    db: AsyncSession = Depends(get_db_db),
) -> User:
    user = (
        (await db.execute(select(User).where(User.password_reset_token == request.token)))
        .scalars()
        .first()
    )
    if user is None:
        raise HTTPException(status_code=404, detail="Not found")
    if (user.password_reset_expiry == None) or (
        datetime.datetime.now(tz=datetime.timezone.utc) > user.password_reset_expiry
    ):
        raise HTTPException(status_code=422, detail="Password reset token has expired")
    user.password_hash = hash_password(request.new_password)
    user.password_reset_token = None
    user.password_reset_expiry = None
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post(
    "/internal/validate-session",
    response_model=SessionValidationResponse,
    status_code=http_status.HTTP_201_CREATED,
    dependencies=[Depends(require_internal)],
)
async def post_internal_validate_session(
    request: ValidateSessionRequest = Body(...),
    db: AsyncSession = Depends(get_db_db),
) -> SessionValidationResponse:
    session: UserSession | None = (
        (await db.execute(select(UserSession).where(UserSession.token == request.token)))
        .scalars()
        .first()
    )
    if (session == None) or session.is_expired:
        return SessionValidationResponse(valid=False, user=None)
    session.last_activity_at = datetime.datetime.now(tz=datetime.timezone.utc)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return SessionValidationResponse(valid=True, user=session.user)


@router.get("/users/{id}", response_model=UserResponse)
async def get_user(
    id: uuid.UUID = Path(...),
    db: AsyncSession = Depends(get_db_db),
    current_user=Depends(require_roles([UserRole.admin])),
) -> User:
    service = UserService(db)
    return await service.get(id)


@router.patch("/users/{id}", response_model=UserResponse)
async def update_user(
    id: uuid.UUID = Path(...),
    body: UserUpdate = Body(...),
    db: AsyncSession = Depends(get_db_db),
    current_user=Depends(require_roles([UserRole.admin])),
) -> User:
    service = UserService(db)
    return await service.update(id, body)


@router.delete("/users/{id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_user(
    id: uuid.UUID = Path(...),
    db: AsyncSession = Depends(get_db_db),
    current_user=Depends(require_roles([UserRole.admin])),
) -> None:
    service = UserService(db)
    await service.delete(id)


@router.patch("/{id}/status", response_model=UserResponse)
async def put_status(
    id: uuid.UUID = Path(...),
    request: UpdateUserStatusRequest = Body(...),
    db: AsyncSession = Depends(get_db_db),
    current_user=Depends(require_roles([UserRole.admin])),
) -> User:
    service = UserService(db)
    user = await service.get(id)
    if user is None:
        raise HTTPException(status_code=404, detail="Not found")
    user.status = request.status
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.get("/internal/{id}", response_model=UserResponse, dependencies=[Depends(require_internal)])
async def get_internal(
    id: uuid.UUID = Path(...),
    db: AsyncSession = Depends(get_db_db),
) -> User:
    service = UserService(db)
    return await service.get(id)


@router.get("/users/{id}/user_sessions", response_model=list[UserSessionResponse])
async def list_user_sessions(
    id: uuid.UUID = Path(...),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_db),
    current_user=Depends(get_current_user),
) -> list[UserSession]:
    # Verify parent exists (raises EntityNotFoundError -> 404)
    user_service = UserService(db)
    await user_service.get(id)
    # Get children
    user_session_service = UserSessionService(db)
    return await user_session_service.get_by_user(user_id=id, skip=skip, limit=limit)
