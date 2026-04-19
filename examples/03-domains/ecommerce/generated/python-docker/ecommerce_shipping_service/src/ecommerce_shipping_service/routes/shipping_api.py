"""ShippingAPI route handlers."""

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
from ecommerce_shipping_service.db.session import get_db_db
from ecommerce_shipping_service.auth import get_current_user, require_roles
from ecommerce_shipping_service._cache_helpers import _get_redis
from ecommerce_shipping_service.dependencies import require_internal
from ecommerce_shipping_service.enums.shipment_status import ShipmentStatus
from ecommerce_shipping_service.enums.shipping_carrier import ShippingCarrier
from ecommerce_shipping_service.functions import calculate_estimated_delivery
from ecommerce_shipping_service.functions import generate_tracking_number
from ecommerce_shipping_service.functions import get_estimated_days
from ecommerce_shipping_service.functions import select_carrier
from ecommerce_shipping_service.models.db.shipment import Shipment
from ecommerce_shipping_service.models.db.shipment_event import ShipmentEvent
from ecommerce_shipping_service.models.db.shipment_item import ShipmentItem
from ecommerce_shipping_service.mq.producer import producer_instance as _producer_instance
from ecommerce_shipping_service.schemas.add_tracking_event_request import AddTrackingEventRequest
from ecommerce_shipping_service.schemas.address import Address
from ecommerce_shipping_service.schemas.create_shipment_request import CreateShipmentRequest
from ecommerce_shipping_service.schemas.db.shipment import ShipmentResponse
from ecommerce_shipping_service.schemas.db.shipment_event import ShipmentEventResponse
from ecommerce_shipping_service.schemas.fed_ex_webhook_request import FedExWebhookRequest
from ecommerce_shipping_service.schemas.get_shipping_rates_request import GetShippingRatesRequest
from ecommerce_shipping_service.schemas.shipment_tracking import ShipmentTracking
from ecommerce_shipping_service.schemas.shipping_rate_response import ShippingRateResponse
from ecommerce_shipping_service.schemas.update_shipment_status_request import (
    UpdateShipmentStatusRequest,
)
from ecommerce_shipping_service.services.db.shipment_event_service import ShipmentEventService
from ecommerce_shipping_service.services.db.shipment_service import ShipmentService
from fastapi import HTTPException
from pydantic import JsonValue
from sqlalchemy import select
import datetime
import decimal
import json
import logging
import uuid

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/shipments",
    tags=["ShippingAPI"],
)


async def calculate_rate(
    carrier: ShippingCarrier, destination: Address, weight: decimal.Decimal
) -> decimal.Decimal:
    base_rate: float = 5.99
    weight_rate: float = weight * 0.5
    if destination.country != "US":
        base_rate = 25.99
        weight_rate = weight * 1.5
    carrier_multiplier: float = 1.0
    if carrier == ShippingCarrier.fed_ex:
        carrier_multiplier = 1.2
    if carrier == ShippingCarrier.ups:
        carrier_multiplier = 1.1
    return (base_rate + weight_rate) * carrier_multiplier


async def map_fed_ex_status(event_type: str) -> ShipmentStatus:
    if event_type == "PU":
        return ShipmentStatus.picked_up
    if event_type == "IT":
        return ShipmentStatus.in_transit
    if event_type == "OD":
        return ShipmentStatus.out_for_delivery
    if event_type == "DL":
        return ShipmentStatus.delivered
    if event_type == "DE":
        return ShipmentStatus.failed
    return ShipmentStatus.in_transit


@router.post(
    "/",
    response_model=ShipmentResponse,
    status_code=http_status.HTTP_201_CREATED,
    dependencies=[Depends(require_internal)],
)
async def post_endpoint(
    request: CreateShipmentRequest = Body(...),
    db: AsyncSession = Depends(get_db_db),
) -> Shipment:
    carrier: ShippingCarrier = select_carrier(request.destination, request.weight)
    estimated_delivery: datetime.datetime = calculate_estimated_delivery(
        carrier, request.destination
    )
    shipment = Shipment(
        **{
            "order_id": request.order_id,
            "tracking_number": generate_tracking_number(),
            "carrier": carrier,
            "destination": request.destination,
            "weight": request.weight,
            "status": ShipmentStatus.pending,
            "estimated_delivery": estimated_delivery,
        }
    )
    db.add(shipment)
    await db.flush()
    await db.refresh(shipment)
    for item in request.items:
        _entity = ShipmentItem(
            **{"shipment": shipment, "product_id": item.product_id, "quantity": item.quantity}
        )
        db.add(_entity)
        await db.flush()
        await db.refresh(_entity)
    _entity = ShipmentEvent(
        **{
            "shipment": shipment,
            "timestamp": datetime.datetime.now(tz=datetime.timezone.utc),
            "status": ShipmentStatus.pending,
            "location": "Warehouse",
            "description": "Shipment created, awaiting pickup",
        }
    )
    db.add(_entity)
    await db.flush()
    await db.refresh(_entity)
    await _producer_instance.publish_shipment_created(shipment.id, request.order_id)
    await _get_redis().incr(datetime.datetime.now(tz=datetime.timezone.utc).strftime("YYYY-MM-DD"))
    logger.info("shipment_created")
    return shipment


@router.post("/rates", status_code=http_status.HTTP_201_CREATED)
async def post_rates(
    request: GetShippingRatesRequest = Body(...),
) -> list[ShippingRateResponse]:
    rates: list[ShippingRateResponse] = []
    rates.append(
        {
            "carrier": ShippingCarrier.fed_ex,
            "rate": await calculate_rate(
                ShippingCarrier.fed_ex, request.destination, request.weight
            ),
            "estimated_days": get_estimated_days(ShippingCarrier.fed_ex, request.destination),
        }
    )
    rates.append(
        {
            "carrier": ShippingCarrier.ups,
            "rate": await calculate_rate(ShippingCarrier.ups, request.destination, request.weight),
            "estimated_days": get_estimated_days(ShippingCarrier.ups, request.destination),
        }
    )
    rates.append(
        {
            "carrier": ShippingCarrier.usps,
            "rate": await calculate_rate(ShippingCarrier.usps, request.destination, request.weight),
            "estimated_days": get_estimated_days(ShippingCarrier.usps, request.destination),
        }
    )
    return rates


@router.post("/webhook/fedex", status_code=http_status.HTTP_201_CREATED)
async def post_webhook_fedex(
    request: FedExWebhookRequest = Body(...),
    db: AsyncSession = Depends(get_db_db),
) -> None:
    tracking_number: str = request.payload.tracking_number
    event_type: str = request.payload.event_type
    location: str = request.payload.location or "Unknown"
    shipment: Shipment | None = (
        (await db.execute(select(Shipment).where(Shipment.tracking_number == tracking_number)))
        .scalars()
        .first()
    )
    if shipment == None:
        logger.warning("webhook_received_for_unknown_tracking_number")
        return
    new_status: ShipmentStatus = await map_fed_ex_status(event_type)
    _entity = ShipmentEvent(
        **{
            "shipment": shipment,
            "timestamp": datetime.datetime.now(tz=datetime.timezone.utc),
            "status": new_status,
            "location": location,
            "description": request.payload.description,
        }
    )
    db.add(_entity)
    await db.flush()
    await db.refresh(_entity)
    if shipment.status != new_status:
        shipment.status = new_status
        if new_status == ShipmentStatus.delivered:
            shipment.actual_delivery = datetime.datetime.now(tz=datetime.timezone.utc)
        db.add(shipment)
        await db.commit()
        await db.refresh(shipment)
    await _get_redis().delete(f"shipment_cache:{str(tracking_number)}")


@router.get("/{id}", response_model=ShipmentResponse)
async def get_shipment(
    id: uuid.UUID = Path(...),
    db: AsyncSession = Depends(get_db_db),
    current_user=Depends(get_current_user),
) -> Shipment:
    service = ShipmentService(db)
    return await service.get(id)


@router.get("/order/{order_id}", response_model=ShipmentResponse)
async def get_order(
    order_id: uuid.UUID = Path(...),
    db: AsyncSession = Depends(get_db_db),
    current_user=Depends(get_current_user),
) -> Shipment:
    result = (
        (await db.execute(select(Shipment).where(Shipment.order_id == order_id))).scalars().first()
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Not found")
    return result


@router.get("/track/{tracking_number}", response_model=ShipmentTracking)
async def get_track(
    tracking_number: str = Path(...),
    db: AsyncSession = Depends(get_db_db),
) -> ShipmentTracking:
    cached: JsonValue | None = (
        json.loads(_raw)
        if (_raw := await _get_redis().get(f"shipment_cache:{str(tracking_number)}")) is not None
        else None
    )
    shipment = (
        (await db.execute(select(Shipment).where(Shipment.tracking_number == tracking_number)))
        .scalars()
        .first()
    )
    if shipment is None:
        raise HTTPException(status_code=404, detail="Not found")
    events: list[ShipmentEvent] = list(
        (
            await db.execute(
                select(ShipmentEvent)
                .where(ShipmentEvent.shipment_id == shipment.id)
                .order_by(ShipmentEvent.timestamp.asc())
            )
        )
        .scalars()
        .all()
    )
    await _get_redis().set(
        f"shipment_cache:{str(tracking_number)}",
        json.dumps(
            {
                "tracking_number": tracking_number,
                "status": shipment.status,
                "estimated_delivery": shipment.estimated_delivery,
            },
            default=str,
        ),
    )
    return ShipmentTracking(
        tracking_number=tracking_number,
        status=shipment.status,
        carrier=shipment.carrier,
        destination=shipment.destination,
        estimated_delivery=shipment.estimated_delivery,
        actual_delivery=shipment.actual_delivery,
        events=events,
    )


@router.patch("/{id}/status", response_model=ShipmentResponse)
async def put_status(
    id: uuid.UUID = Path(...),
    request: UpdateShipmentStatusRequest = Body(...),
    db: AsyncSession = Depends(get_db_db),
    current_user=Depends(require_roles(["admin"])),
) -> Shipment:
    service = ShipmentService(db)
    shipment = await service.get(id)
    if shipment is None:
        raise HTTPException(status_code=404, detail="Not found")
    old_status: ShipmentStatus = shipment.status
    shipment.status = request.status
    if request.status == ShipmentStatus.delivered:
        shipment.actual_delivery = datetime.datetime.now(tz=datetime.timezone.utc)
    db.add(shipment)
    await db.commit()
    await db.refresh(shipment)
    _entity = ShipmentEvent(
        **{
            "shipment": shipment,
            "timestamp": datetime.datetime.now(tz=datetime.timezone.utc),
            "status": request.status,
            "location": (request.location or "Unknown"),
            "description": (request.description or f"Status updated to {request.status}"),
        }
    )
    db.add(_entity)
    await db.flush()
    await db.refresh(_entity)
    await _get_redis().delete(f"shipment_cache:{str(shipment.tracking_number)}")
    logger.info("shipment_status_updated")
    return shipment


@router.post(
    "/{id}/events", response_model=ShipmentEventResponse, status_code=http_status.HTTP_201_CREATED
)
async def post_events(
    id: uuid.UUID = Path(...),
    request: AddTrackingEventRequest = Body(...),
    db: AsyncSession = Depends(get_db_db),
    current_user=Depends(require_roles(["admin"])),
) -> ShipmentEvent:
    service = ShipmentService(db)
    shipment = await service.get(id)
    if shipment is None:
        raise HTTPException(status_code=404, detail="Not found")
    event = ShipmentEvent(
        **{
            "shipment": shipment,
            "timestamp": datetime.datetime.now(tz=datetime.timezone.utc),
            "status": request.status,
            "location": request.location,
            "description": request.description,
        }
    )
    db.add(event)
    await db.flush()
    await db.refresh(event)
    if shipment.status != request.status:
        shipment.status = request.status
        if request.status == ShipmentStatus.delivered:
            shipment.actual_delivery = datetime.datetime.now(tz=datetime.timezone.utc)
        db.add(shipment)
        await db.commit()
        await db.refresh(shipment)
    await _get_redis().delete(f"shipment_cache:{str(shipment.tracking_number)}")
    return event


@router.get("/shipments/{id}/shipment_events", response_model=list[ShipmentEventResponse])
async def list_shipment_events(
    id: uuid.UUID = Path(...),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_db),
    current_user=Depends(get_current_user),
) -> list[ShipmentEvent]:
    # Verify parent exists (raises EntityNotFoundError -> 404)
    shipment_service = ShipmentService(db)
    await shipment_service.get(id)
    # Get children
    shipment_event_service = ShipmentEventService(db)
    return await shipment_event_service.get_by_shipment(shipment_id=id, skip=skip, limit=limit)
