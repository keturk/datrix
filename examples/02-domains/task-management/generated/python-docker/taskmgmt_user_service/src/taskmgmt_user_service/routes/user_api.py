"""UserAPI route handlers."""

from fastapi import (
    APIRouter,
    Body,
    Depends,
    Path,
    Query,
)
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession
from taskmgmt_user_service.db.session import get_db_db
from taskmgmt_user_service.auth import get_current_user
from taskmgmt_user_service.models.db.user import User
from taskmgmt_user_service.schemas.db.user import UserCreate, UserUpdate, UserResponse
from taskmgmt_user_service.services.db.user_service import UserService
import uuid

router = APIRouter(
    prefix="/api/v1/users",
    tags=["UserAPI"],
)


@router.get("/", response_model=list[UserResponse])
async def list_users(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_db),
    current_user=Depends(get_current_user),
) -> list[User]:
    service = UserService(db)
    return await service.get_all(skip=skip, limit=limit)


@router.post("/", response_model=UserResponse, status_code=http_status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate = Body(...),
    db: AsyncSession = Depends(get_db_db),
    current_user=Depends(get_current_user),
) -> User:
    service = UserService(db)
    return await service.create(body)


@router.get("/{id}", response_model=UserResponse)
async def get_user(
    id: uuid.UUID = Path(...),
    db: AsyncSession = Depends(get_db_db),
    current_user=Depends(get_current_user),
) -> User:
    service = UserService(db)
    return await service.get(id)


@router.patch("/{id}", response_model=UserResponse)
async def update_user(
    id: uuid.UUID = Path(...),
    body: UserUpdate = Body(...),
    db: AsyncSession = Depends(get_db_db),
    current_user=Depends(get_current_user),
) -> User:
    service = UserService(db)
    return await service.update(id, body)


@router.delete("/{id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_user(
    id: uuid.UUID = Path(...),
    db: AsyncSession = Depends(get_db_db),
    current_user=Depends(get_current_user),
) -> None:
    service = UserService(db)
    await service.delete(id)
