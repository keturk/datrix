"""OrderAPI route handlers."""

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
from ecommerce_order_service.db.session import get_db_db
from ecommerce_order_service.db.session import db_session
from ecommerce_order_service.auth import get_current_user, require_roles
from decimal import Decimal
from ecommerce_order_service.clients.product_service_client import ProductServiceClient
from ecommerce_order_service.constants import MAX_PAGE_SIZE
from ecommerce_order_service.dependencies import require_internal
from ecommerce_order_service.enums.order_status import OrderStatus
from ecommerce_order_service.functions import generate_order_number
from ecommerce_order_service.models.db.idempotency_key import IdempotencyKey
from ecommerce_order_service.models.db.order import Order
from ecommerce_order_service.models.db.order_item import OrderItem
from ecommerce_order_service.schemas.cancel_order_request import CancelOrderRequest
from ecommerce_order_service.schemas.confirm_payment_request import ConfirmPaymentRequest
from ecommerce_order_service.schemas.create_order_request import CreateOrderRequest
from ecommerce_order_service.schemas.db.order import OrderResponse
from ecommerce_order_service.schemas.db.order_item import OrderItemResponse
from ecommerce_order_service.schemas.paginated_orders import PaginatedOrders
from ecommerce_order_service.schemas.update_shipment_request import UpdateShipmentRequest
from ecommerce_order_service.services.db.order_item_service import OrderItemService
from ecommerce_order_service.services.db.order_service import OrderService
from fastapi import HTTPException
from pydantic import JsonValue
from sqlalchemy import func
from sqlalchemy import select
import datetime
import logging
import math
import uuid

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/orders",
    tags=["OrderAPI"],
)


async def check_idempotency(idempotency_key: str | None, operation: str) -> JsonValue | None:
    async with db_session() as db:
        if idempotency_key == None:
            return None
        existing: IdempotencyKey | None = (
            (
                await db.execute(
                    select(IdempotencyKey).where(
                        IdempotencyKey.key == idempotency_key,
                        IdempotencyKey.operation == operation,
                        IdempotencyKey.expires_at > datetime.datetime.now(tz=datetime.timezone.utc),
                    )
                )
            )
            .scalars()
            .first()
        )
        if existing != None:
            logger.info("idempotent_request_detected")
            return existing.response
        return None


async def store_idempotency(
    idempotency_key: str | None, operation: str, resource_id: uuid.UUID, response: JsonValue
) -> None:
    async with db_session() as db:
        if idempotency_key == None:
            return
        _entity = IdempotencyKey(
            **{
                "key": idempotency_key,
                "operation": operation,
                "resource_id": resource_id,
                "response": response,
                "expires_at": (
                    datetime.datetime.now(tz=datetime.timezone.utc) + datetime.timedelta(hours=24)
                ),
            }
        )
        db.add(_entity)
        await db.flush()
        await db.refresh(_entity)


@router.get("/", response_model=PaginatedOrders)
async def get_endpoint(
    page: int = Query(default=None),
    per_page: int = Query(default=None),
    status: OrderStatus | None = Query(default=None),
    db: AsyncSession = Depends(get_db_db),
    current_user=Depends(get_current_user),
) -> PaginatedOrders:
    customer_id: uuid.UUID = current_user.id
    query = select(Order).where(Order.customer_id == customer_id)
    if status != None:
        query = query.where(Order.status == status)
    total: int = (
        await db.execute(select(func.count()).select_from((query).subquery()))
    ).scalar() or 0
    capped_per_page: int = min(per_page, MAX_PAGE_SIZE)
    orders: list[Order] = list(
        (
            await db.execute(
                query.order_by(Order.created_at.desc())
                .offset(((page - 1) * capped_per_page))
                .limit(capped_per_page)
            )
        )
        .scalars()
        .all()
    )
    return PaginatedOrders(
        data=orders,
        pagination={
            "current_page": page,
            "per_page": capped_per_page,
            "total_items": total,
            "total_pages": math.ceil((total / capped_per_page)),
            "has_next_page": (page < math.ceil((total / capped_per_page))),
            "has_prev_page": (page > 1),
        },
    )


@router.post("/", response_model=OrderResponse, status_code=http_status.HTTP_201_CREATED)
async def post_endpoint(
    request: CreateOrderRequest = Body(...),
    db: AsyncSession = Depends(get_db_db),
    current_user=Depends(get_current_user),
) -> Order:
    product_service_client = ProductServiceClient()
    cached: JsonValue | None = await check_idempotency(request.idempotency_key, "create_order")
    if cached != None:
        return cached
    customer_id: uuid.UUID = current_user.id
    reservation_id: uuid.UUID = str(uuid.uuid4())
    availability: dict[str, object] = (
        _r := await product_service_client.post("/internal/check-availability", json=request.items),
        _r.raise_for_status(),
        _r.json(),
    )[2]
    if not availability["all_available"]:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVENTORY_UNAVAILABLE",
                "message": "Some products are not available",
                "items": [x for x in availability["items"] if (not x.available)],
            },
        )
    reservation: dict[str, object] = (
        _r := await product_service_client.post(
            "/internal/reserve-inventory",
            json={"reservation_id": reservation_id, "items": request.items, "ttl_seconds": 600},
        ),
        _r.raise_for_status(),
        _r.json(),
    )[2]
    if not reservation["success"]:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "RESERVATION_FAILED",
                "message": "Failed to reserve inventory",
                "error": reservation["error"],
            },
        )
    order = Order(
        **{
            "order_number": generate_order_number(),
            "customer_id": customer_id,
            "shipping_address": request.shipping_address,
            "billing_address": (request.billing_address or request.shipping_address),
            "status": OrderStatus.pending,
            "inventory_reservation_id": reservation_id,
            "subtotal": Decimal(str(0)),
            "tax": Decimal(str(0)),
            "shipping_cost": Decimal(str(0)),
            "discount": Decimal(str(0)),
        }
    )
    db.add(order)
    await db.flush()
    await db.refresh(order)
    for item in request.items:
        product: dict[str, object] = (
            _r := await product_service_client.get(f"/internal/{item.product_id}"),
            _r.raise_for_status(),
            _r.json(),
        )[2]
        _entity = OrderItem(
            **{
                "order": order,
                "product_id": item.product_id,
                "product_name": product["name"],
                "quantity": item.quantity,
                "unit_price": product["price"],
            }
        )
        db.add(_entity)
        await db.flush()
        await db.refresh(_entity)
    order.calculate_totals()
    db.add(order)
    await db.commit()
    await db.refresh(order)
    await store_idempotency(request.idempotency_key, "create_order", order.id, order)
    return order


@router.get("/{id}", response_model=OrderResponse)
async def get_endpoint_2(
    id: uuid.UUID = Path(...),
    db: AsyncSession = Depends(get_db_db),
    current_user=Depends(get_current_user),
) -> Order:
    service = OrderService(db)
    order = await service.get(id)
    if order is None:
        raise HTTPException(status_code=404, detail="Not found")
    if (order.customer_id != current_user.id) and (not ("admin" in (current_user.roles or []))):
        raise HTTPException(status_code=403, detail="Access denied")
    return order


@router.put("/{id}/cancel", response_model=OrderResponse)
async def put_cancel(
    id: uuid.UUID = Path(...),
    request: CancelOrderRequest = Body(...),
    db: AsyncSession = Depends(get_db_db),
    current_user=Depends(get_current_user),
) -> Order:
    service = OrderService(db)
    order = await service.get(id)
    if order is None:
        raise HTTPException(status_code=404, detail="Not found")
    if (order.customer_id != current_user.id) and (not ("admin" in (current_user.roles or []))):
        raise HTTPException(status_code=403, detail="Cannot cancel another user's order")
    if not order.can_cancel:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "ORDER_NOT_CANCELLABLE",
                "message": f"Order cannot be cancelled in status: {order.status}",
            },
        )
    async with db.session.begin() as session:
        order.status = OrderStatus.cancelled
        order.cancellation_reason = request.reason or "Cancelled by customer"
        db.add(order)
        await db.commit()
        await db.refresh(order)
    return order


@router.get(
    "/internal/{id}", response_model=OrderResponse, dependencies=[Depends(require_internal)]
)
async def get_internal(
    id: uuid.UUID = Path(...),
    db: AsyncSession = Depends(get_db_db),
) -> Order:
    service = OrderService(db)
    return await service.get(id)


@router.post(
    "/{id}/confirm-payment",
    response_model=OrderResponse,
    status_code=http_status.HTTP_201_CREATED,
    dependencies=[Depends(require_internal)],
)
async def post_confirm_payment(
    id: uuid.UUID = Path(...),
    request: ConfirmPaymentRequest = Body(...),
    db: AsyncSession = Depends(get_db_db),
) -> Order:
    service = OrderService(db)
    order = await service.get(id)
    if order is None:
        raise HTTPException(status_code=404, detail="Not found")
    order.payment_id = request.payment_id
    order.status = OrderStatus.confirmed
    db.add(order)
    await db.commit()
    await db.refresh(order)
    return order


@router.post(
    "/{id}/update-shipment",
    response_model=OrderResponse,
    status_code=http_status.HTTP_201_CREATED,
    dependencies=[Depends(require_internal)],
)
async def post_update_shipment(
    id: uuid.UUID = Path(...),
    request: UpdateShipmentRequest = Body(...),
    db: AsyncSession = Depends(get_db_db),
) -> Order:
    service = OrderService(db)
    order = await service.get(id)
    if order is None:
        raise HTTPException(status_code=404, detail="Not found")
    order.shipment_id = request.shipment_id
    db.add(order)
    await db.commit()
    await db.refresh(order)
    return order


@router.get("/orders/{id}/order_items", response_model=list[OrderItemResponse])
async def list_order_items(
    id: uuid.UUID = Path(...),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_db),
    current_user=Depends(get_current_user),
) -> list[OrderItem]:
    # Verify parent exists (raises EntityNotFoundError -> 404)
    order_service = OrderService(db)
    await order_service.get(id)
    # Get children
    order_item_service = OrderItemService(db)
    return await order_item_service.get_by_order(order_id=id, skip=skip, limit=limit)
