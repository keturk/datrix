"""PushDeviceApi route handlers."""

from fastapi import APIRouter, Body, Depends

from ecommerce_notification_service.auth import require_route
from ecommerce_notification_service.schemas.register_device_request import (
    RegisterDeviceRequest,
)

router = APIRouter(
    prefix="/push",
    tags=["PushDeviceApi"],
)


@router.post("/devices")
async def post_devices(
    request: RegisterDeviceRequest = Body(...),
    current_user=Depends(
        require_route(
            providers=["identity", "test_auth"], roles=[], principal_types=["human"]
        )
    ),
) -> None:
    pass


@router.post("/devices/unregister")
async def post_devices_unregister(
    request: RegisterDeviceRequest = Body(...),
    current_user=Depends(
        require_route(
            providers=["identity", "test_auth"], roles=[], principal_types=["human"]
        )
    ),
) -> None:
    pass
