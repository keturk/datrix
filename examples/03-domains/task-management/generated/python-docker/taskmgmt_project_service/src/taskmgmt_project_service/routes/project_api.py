"""ProjectAPI route handlers."""

from fastapi import (
    APIRouter,
    Body,
    Depends,
    Path,
    Query,
)
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession
from taskmgmt_project_service.db.session import get_db_db
from taskmgmt_project_service.auth import get_current_user
from taskmgmt_project_service.models.db.project import Project
from taskmgmt_project_service.schemas.db.project import (
    ProjectCreate,
    ProjectUpdate,
    ProjectResponse,
)
from taskmgmt_project_service.services.db.project_service import ProjectService
import uuid

router = APIRouter(
    prefix="/api/v1/projects",
    tags=["ProjectAPI"],
)


@router.get("/", response_model=list[ProjectResponse])
async def list_projects(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_db),
    current_user=Depends(get_current_user),
) -> list[Project]:
    service = ProjectService(db)
    return await service.get_all(skip=skip, limit=limit)


@router.post("/", response_model=ProjectResponse, status_code=http_status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreate = Body(...),
    db: AsyncSession = Depends(get_db_db),
    current_user=Depends(get_current_user),
) -> Project:
    service = ProjectService(db)
    return await service.create(body)


@router.get("/{id}", response_model=ProjectResponse)
async def get_project(
    id: uuid.UUID = Path(...),
    db: AsyncSession = Depends(get_db_db),
    current_user=Depends(get_current_user),
) -> Project:
    service = ProjectService(db)
    return await service.get(id)


@router.patch("/{id}", response_model=ProjectResponse)
async def update_project(
    id: uuid.UUID = Path(...),
    body: ProjectUpdate = Body(...),
    db: AsyncSession = Depends(get_db_db),
    current_user=Depends(get_current_user),
) -> Project:
    service = ProjectService(db)
    return await service.update(id, body)


@router.delete("/{id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_project(
    id: uuid.UUID = Path(...),
    db: AsyncSession = Depends(get_db_db),
    current_user=Depends(get_current_user),
) -> None:
    service = ProjectService(db)
    await service.delete(id)
