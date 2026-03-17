"""TaskAPI route handlers."""

from fastapi import (
    APIRouter,
    Body,
    Depends,
    Path,
    Query,
)
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession
from taskmgmt_task_service.db.session import get_db_db
from taskmgmt_task_service.auth import get_current_user
from taskmgmt_task_service.models.db.task import Task
from taskmgmt_task_service.schemas.db.task import TaskCreate, TaskUpdate, TaskResponse
from taskmgmt_task_service.services.db.task_service import TaskService
import uuid

router = APIRouter(
    prefix="/api/v1/tasks",
    tags=["TaskAPI"],
)


@router.get("/", response_model=list[TaskResponse])
async def list_tasks(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_db),
    current_user=Depends(get_current_user),
) -> list[Task]:
    service = TaskService(db)
    return await service.get_all(skip=skip, limit=limit)


@router.post("/", response_model=TaskResponse, status_code=http_status.HTTP_201_CREATED)
async def create_task(
    body: TaskCreate = Body(...),
    db: AsyncSession = Depends(get_db_db),
    current_user=Depends(get_current_user),
) -> Task:
    service = TaskService(db)
    return await service.create(body)


@router.get("/{id}", response_model=TaskResponse)
async def get_task(
    id: uuid.UUID = Path(...),
    db: AsyncSession = Depends(get_db_db),
    current_user=Depends(get_current_user),
) -> Task:
    service = TaskService(db)
    return await service.get(id)


@router.patch("/{id}", response_model=TaskResponse)
async def update_task(
    id: uuid.UUID = Path(...),
    body: TaskUpdate = Body(...),
    db: AsyncSession = Depends(get_db_db),
    current_user=Depends(get_current_user),
) -> Task:
    service = TaskService(db)
    return await service.update(id, body)


@router.delete("/{id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_task(
    id: uuid.UUID = Path(...),
    db: AsyncSession = Depends(get_db_db),
    current_user=Depends(get_current_user),
) -> None:
    service = TaskService(db)
    await service.delete(id)
