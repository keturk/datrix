"""OrderAPI route handlers."""

import datetime
import logging
import math
import uuid
from decimal import Decimal
from enum import Enum as PyEnum

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, Security
from fastapi.security import APIKeyHeader
from pydantic import JsonValue
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ecommerce_order_service.auth import require_route
from ecommerce_order_service.clients.product_service_client import (
    get_product_service_client,
)
from ecommerce_order_service.clients.product_service_responses import (
    ProductServiceAvailabilityResponseResponse,
    ProductServiceProductResponse,
    ProductServiceReservationResponseResponse,
    decode_product_service_availability_response_response,
    decode_product_service_product_response,
    decode_product_service_reservation_response_response,
)
from ecommerce_order_service.constants import MAX_PAGE_SIZE
from ecommerce_order_service.enums.order_status import OrderStatus
from ecommerce_order_service.event_outbox import buffer_events as _datrix_buffer_events
from ecommerce_order_service.functions import generate_order_number
from ecommerce_order_service.models.order_db.idempotency_key import IdempotencyKey
from ecommerce_order_service.models.order_db.order import Order
from ecommerce_order_service.order_db.session import get_order_db_db, order_db_session
from ecommerce_order_service.rate_limit.rate_limit_dependency import (
    enforce_plan_rate_limit,
)
from ecommerce_order_service.schemas.cancel_order_request import CancelOrderRequest
from ecommerce_order_service.schemas.confirm_payment_request import (
    ConfirmPaymentRequest,
)
from ecommerce_order_service.schemas.create_order_request import CreateOrderRequest
from ecommerce_order_service.schemas.order_db.idempotency_key import (
    IdempotencyKeyCreate,
)
from ecommerce_order_service.schemas.order_db.order import (
    OrderCreate,
    OrderResponse,
    OrderUpdate,
)
from ecommerce_order_service.schemas.order_db.order_item import OrderItemCreate
from ecommerce_order_service.schemas.paginated_orders import PaginatedOrders
from ecommerce_order_service.schemas.update_shipment_request import (
    UpdateShipmentRequest,
)
from ecommerce_order_service.services.order_db.idempotency_key_service import (
    IdempotencyKeyService,
)
from ecommerce_order_service.services.order_db.order_item_service import (
    OrderItemService,
)
from ecommerce_order_service.services.order_db.order_service import OrderService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/orders",
    tags=["OrderAPI"],
)

# OpenAPI apiKey security schemes, one per API-key provider a route below
# admits. They only document the requirement: the API-key credential
# middleware has already authenticated a presented key before any route runs.
_api_key_scheme_customer_keys = APIKeyHeader(
    name="X-Customer-Api-Key", scheme_name="customerKeys", auto_error=False
)


async def check_idempotency(
    idempotency_key: str | None, operation: str
) -> JsonValue | None:
    async with order_db_session() as order_db:
        if idempotency_key is None:
            return None
        existing: IdempotencyKey | None = (
            (
                await order_db.execute(
                    select(IdempotencyKey).where(
                        IdempotencyKey.key == idempotency_key,
                        IdempotencyKey.operation == operation,
                        IdempotencyKey.expires_at
                        > datetime.datetime.now(datetime.timezone.utc),
                    )
                )
            )
            .scalars()
            .first()
        )
        if existing is not None:
            logger.info(
                "idempotent_request_detected key=%s operation=%s",
                idempotency_key,
                operation,
            )
            return existing.response
        return None


async def store_idempotency(
    idempotency_key: str | None,
    operation: str,
    resource_id: uuid.UUID,
    response: JsonValue,
) -> None:
    async with order_db_session() as order_db:
        if idempotency_key is None:
            return
        _idempotency_key_svc = IdempotencyKeyService(order_db)
        _entity = await _idempotency_key_svc.create(
            IdempotencyKeyCreate(
                **{
                    "key": idempotency_key,
                    "operation": operation,
                    "resource_id": resource_id,
                    "response": response,
                    "expires_at": (
                        datetime.datetime.now(datetime.timezone.utc)
                        + datetime.timedelta(hours=24)
                    ),
                }
            )
        )


# Paginated list endpoint with optional filtering
@router.get(
    "",
    response_model=PaginatedOrders,
    dependencies=[Security(_api_key_scheme_customer_keys)],
)
async def get_endpoint(
    page: int = Query(default=1),
    per_page: int = Query(default=20),
    status: OrderStatus | None = Query(default=None),
    order_db: AsyncSession = Depends(get_order_db_db),
    current_user=Depends(
        require_route(
            providers=["identity", "customerKeys", "test_auth"],
            roles=[],
            principal_types=["human"],
        )
    ),
    _rate_limit=Depends(enforce_plan_rate_limit),
) -> PaginatedOrders:
    customer_id: uuid.UUID = current_user.user().id
    query = select(Order).where(Order.customer_id == customer_id)
    if status is not None:
        query = query.where(Order.status == status)
    total: int = (
        await order_db.execute(select(func.count()).select_from((query).subquery()))
    ).scalar() or 0
    capped_per_page: int = min(per_page, MAX_PAGE_SIZE)
    orders: list[Order] = list(
        (
            await order_db.execute(
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
            "currentPage": page,
            "perPage": capped_per_page,
            "totalItems": total,
            "totalPages": math.ceil((total / capped_per_page)),
            "hasNextPage": (page < math.ceil((total / capped_per_page))),
            "hasPrevPage": (page > 1),
        },
    )


@router.post("", response_model=OrderResponse)
async def post_endpoint(
    request: CreateOrderRequest = Body(...),
    order_db: AsyncSession = Depends(get_order_db_db),
    current_user=Depends(
        require_route(
            providers=["identity", "test_auth"], roles=[], principal_types=["human"]
        )
    ),
    _rate_limit=Depends(enforce_plan_rate_limit),
) -> Order:
    # Check idempotency to prevent duplicate orders on retry
    cached: JsonValue | None = await check_idempotency(
        request.idempotency_key, "create_order"
    )
    if cached is not None:
        return cached
    customer_id: uuid.UUID = current_user.user().id
    reservation_id: uuid.UUID = uuid.uuid4()
    # Cross-service call('config/service.dcfg') : check product availability via ProductService
    availability: ProductServiceAvailabilityResponseResponse = (
        decode_product_service_availability_response_response(
            await get_product_service_client().post_json(
                "/api/v1/products/service/check-availability",
                body=request.items,
                idempotent=True,
            )
        )
    )
    if not availability.all_available:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVENTORY_UNAVAILABLE",
                "message": "Some products are not available",
                "items": [x for x in availability.items if (not x.available)],
            },
        )
    # Cross-service call('config/service.dcfg') : reserve inventory
    reservation: ProductServiceReservationResponseResponse = (
        decode_product_service_reservation_response_response(
            await get_product_service_client().post_json(
                "/api/v1/products/service/reserve-inventory",
                body={
                    "reservationId": reservation_id,
                    "items": request.items,
                    "ttlSeconds": 600,
                },
                idempotent=False,
            )
        )
    )
    if not reservation.success:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "RESERVATION_FAILED",
                "message": "Failed to reserve inventory",
                "error": reservation.error,
            },
        )
    _order_svc = OrderService(order_db)
    order = await _order_svc.create(
        OrderCreate(
            **{
                "order_number": generate_order_number(),
                "customer_id": customer_id,
                "shipping_address": request.shipping_address,
                "billing_address": (
                    request.billing_address
                    if request.billing_address is not None
                    else request.shipping_address
                ),
                "status": OrderStatus.pending,
                "inventory_reservation_id": reservation_id,
                "subtotal": Decimal(str(0)),
                "tax": Decimal(str(0)),
                "shipping_cost": Decimal(str(0)),
                "discount": Decimal(str(0)),
            }
        )
    )
    for item in request.items:
        # Fetch product details from ProductService for denormalization
        product: ProductServiceProductResponse = (
            decode_product_service_product_response(
                await get_product_service_client().get_json(
                    f"/api/v1/products/service/{item.product_id}", idempotent=True
                )
            )
        )
        _order_item_svc = OrderItemService(order_db)
        _entity = await _order_item_svc.create(
            OrderItemCreate(
                **{
                    "order_id": order.id,
                    "product_id": item.product_id,
                    "product_name": product.name,
                    "quantity": item.quantity,
                    "unit_price": product.price,
                }
            )
        )
    order.calculate_totals()
    await order_db.refresh(order)
    await store_idempotency(request.idempotency_key, "create_order", order.id, order)
    return order


@router.get("/service/{id}", response_model=OrderResponse, include_in_schema=False)
async def get_service_by_id(
    id_: uuid.UUID = Path(..., alias="id"),
    order_db: AsyncSession = Depends(get_order_db_db),
    current_user=Depends(
        require_route(
            providers=["platform", "test_auth"], roles=[], principal_types=["machine"]
        )
    ),
    _rate_limit=Depends(enforce_plan_rate_limit),
) -> Order:
    service = OrderService(order_db)
    return await service.get(id_)


@router.post(
    "/{id}/confirm-payment", response_model=OrderResponse, include_in_schema=False
)
async def post_by_id_confirm_payment(
    request: ConfirmPaymentRequest = Body(...),
    id_: uuid.UUID = Path(..., alias="id"),
    order_db: AsyncSession = Depends(get_order_db_db),
    current_user=Depends(
        require_route(
            providers=["platform", "test_auth"], roles=[], principal_types=["machine"]
        )
    ),
    _rate_limit=Depends(enforce_plan_rate_limit),
) -> Order:
    service = OrderService(order_db)
    order = await service.get(id_)
    if order is None:
        raise HTTPException(status_code=404, detail="Not found")
    order.payment_id = request.payment_id
    order.status = OrderStatus.confirmed
    _order_svc = OrderService(order_db)
    order = await _order_svc.update(
        order.id,
        OrderUpdate(**{"payment_id": order.payment_id, "status": order.status}),
    )
    return order


@router.post(
    "/{id}/update-shipment", response_model=OrderResponse, include_in_schema=False
)
async def post_by_id_update_shipment(
    request: UpdateShipmentRequest = Body(...),
    id_: uuid.UUID = Path(..., alias="id"),
    order_db: AsyncSession = Depends(get_order_db_db),
    current_user=Depends(
        require_route(
            providers=["platform", "test_auth"], roles=[], principal_types=["machine"]
        )
    ),
    _rate_limit=Depends(enforce_plan_rate_limit),
) -> Order:
    service = OrderService(order_db)
    order = await service.get(id_)
    if order is None:
        raise HTTPException(status_code=404, detail="Not found")
    order.shipment_id = request.shipment_id
    _order_svc = OrderService(order_db)
    order = await _order_svc.update(
        order.id, OrderUpdate(**{"shipment_id": order.shipment_id})
    )
    return order


@router.put("/{id}/cancel", response_model=OrderResponse)
async def put_by_id_cancel(
    request: CancelOrderRequest = Body(...),
    id_: uuid.UUID = Path(..., alias="id"),
    order_db: AsyncSession = Depends(get_order_db_db),
    current_user=Depends(
        require_route(
            providers=["identity", "test_auth"], roles=[], principal_types=["human"]
        )
    ),
    _rate_limit=Depends(enforce_plan_rate_limit),
) -> Order:
    service = OrderService(order_db)
    order = await service.get(id_)
    if order is None:
        raise HTTPException(status_code=404, detail="Not found")
    if (order.customer_id != current_user.user().id) and (
        not (any(str(_r).lower() == str("admin").lower() for _r in current_user.roles))
    ):
        raise HTTPException(
            status_code=403, detail="Cannot cancel another user's order"
        )
    if not order.can_cancel:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "ORDER_NOT_CANCELLABLE",
                "message": f"Order cannot be cancelled in status: {(order.status.value if isinstance(order.status, PyEnum) else order.status)}",
            },
        )
    async with _datrix_buffer_events():
        if order_db.in_transaction():
            await order_db.commit()
        async with order_db.begin() as session:
            order.status = OrderStatus.cancelled
            order.cancellation_reason = (
                request.reason
                if request.reason is not None
                else "Cancelled by customer"
            )
            _order_svc = OrderService(order_db)
            order = await _order_svc.update(
                order.id,
                OrderUpdate(
                    **{
                        "cancellation_reason": order.cancellation_reason,
                        "status": order.status,
                    }
                ),
                _commit=False,
            )
    return order


@router.get("/{id}", response_model=OrderResponse)
async def get_by_id(
    id_: uuid.UUID = Path(..., alias="id"),
    order_db: AsyncSession = Depends(get_order_db_db),
    current_user=Depends(
        require_route(
            providers=["identity", "test_auth"], roles=[], principal_types=["human"]
        )
    ),
    _rate_limit=Depends(enforce_plan_rate_limit),
) -> Order:
    service = OrderService(order_db)
    order = await service.get(id_)
    if order is None:
        raise HTTPException(status_code=404, detail="Not found")
    if (order.customer_id != current_user.user().id) and (
        not (any(str(_r).lower() == str("admin").lower() for _r in current_user.roles))
    ):
        raise HTTPException(status_code=403, detail="Access denied")
    return order
