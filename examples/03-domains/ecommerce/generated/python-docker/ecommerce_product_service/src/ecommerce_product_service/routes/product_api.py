"""ProductAPI route handlers."""

import datetime
import json
import logging
import uuid

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query
from fastapi import status as http_status
from pydantic import JsonValue
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ecommerce_product_service._cache_helpers import _get_redis
from ecommerce_product_service.auth import (
    get_current_user,
    require_providers,
    require_roles,
)
from ecommerce_product_service.dependencies import require_service_endpoint
from ecommerce_product_service.enums.product_status import ProductStatus
from ecommerce_product_service.enums.reservation_status import ReservationStatus
from ecommerce_product_service.event_outbox import (
    buffer_events as _datrix_buffer_events,
)
from ecommerce_product_service.models.product_db.inventory_reservation import (
    InventoryReservation,
)
from ecommerce_product_service.models.product_db.product import Product
from ecommerce_product_service.mq import producer as _mq_producer
from ecommerce_product_service.product_db.session import get_product_db_db
from ecommerce_product_service.rate_limit.rate_limit_dependency import (
    enforce_plan_rate_limit,
)
from ecommerce_product_service.schemas.availability_item import AvailabilityItem
from ecommerce_product_service.schemas.availability_response import AvailabilityResponse
from ecommerce_product_service.schemas.bulk_product_request import BulkProductRequest
from ecommerce_product_service.schemas.check_availability_request import (
    CheckAvailabilityRequest,
)
from ecommerce_product_service.schemas.confirm_reservation_request import (
    ConfirmReservationRequest,
)
from ecommerce_product_service.schemas.create_product_request import (
    CreateProductRequest,
)
from ecommerce_product_service.schemas.product_db.inventory_reservation import (
    InventoryReservationCreate,
    InventoryReservationUpdate,
)
from ecommerce_product_service.schemas.product_db.product import (
    ProductCreate,
    ProductResponse,
    ProductUpdate,
)
from ecommerce_product_service.schemas.release_reservation_request import (
    ReleaseReservationRequest,
)
from ecommerce_product_service.schemas.reservation_response import ReservationResponse
from ecommerce_product_service.schemas.reserve_inventory_request import (
    ReserveInventoryRequest,
)
from ecommerce_product_service.schemas.update_inventory_request import (
    UpdateInventoryRequest,
)
from ecommerce_product_service.services.product_db.inventory_reservation_service import (
    InventoryReservationService,
)
from ecommerce_product_service.services.product_db.product_service import ProductService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/products",
    tags=["ProductAPI"],
)


@router.get("", response_model=list[ProductResponse])
async def list_products(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    product_db: AsyncSession = Depends(get_product_db_db),
    _rate_limit=Depends(enforce_plan_rate_limit),
) -> list[Product]:
    service = ProductService(product_db)
    return await service.get_all(skip=skip, limit=limit)


# Full-text search endpoint
@router.get("/search", response_model=list[ProductResponse])
async def get_search(
    query: str = Query(default=...),
    limit: int | None = Query(default=None),
    offset: int | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    product_db: AsyncSession = Depends(get_product_db_db),
    _rate_limit=Depends(enforce_plan_rate_limit),
) -> list[Product]:
    return list(
        (
            await product_db.execute(
                select(Product)
                .where(
                    func.to_tsvector(
                        "english",
                        func.coalesce(Product.name, "")
                        + " "
                        + func.coalesce(Product.description, ""),
                    ).op("@@")(func.plainto_tsquery("english", query))
                )
                .where(Product.status == ProductStatus.active)
                .limit((limit if limit is not None else 20))
                .offset((offset if offset is not None else 0))
            )
        )
        .scalars()
        .all()
    )


@router.post(
    "",
    response_model=ProductResponse,
    dependencies=[Depends(require_providers(["identity", "test_auth"]))],
)
async def post_endpoint(
    request: CreateProductRequest = Body(...),
    product_db: AsyncSession = Depends(get_product_db_db),
    current_user=Depends(require_roles(["Admin"])),
    _rate_limit=Depends(enforce_plan_rate_limit),
) -> Product:
    _product_svc = ProductService(product_db)
    product = await _product_svc.create(
        ProductCreate(
            **{
                "name": request.name,
                "description": request.description,
                "price": request.price,
                "category_id": request.category_id,
                "inventory": request.inventory,
                "status": ProductStatus.draft,
                "images": [],
                "tags": [],
            }
        )
    )
    # Call trait method to generate URL slug
    product.generate_slug(request.name)
    await product_db.refresh(product)
    async with _datrix_buffer_events():
        _producer_instance = await _mq_producer.get_producer()
        await _producer_instance.publish_product_created(
            product.id, product.name, product.price
        )
    return product


# Internal endpoints for cross-service communication
@router.post(
    "/service/check-availability",
    response_model=AvailabilityResponse,
    include_in_schema=False,
    dependencies=[Depends(require_service_endpoint)],
)
async def post_service_check_availability(
    request: CheckAvailabilityRequest = Body(...),
    product_db: AsyncSession = Depends(get_product_db_db),
    current_user=Depends(get_current_user),
    _rate_limit=Depends(enforce_plan_rate_limit),
) -> AvailabilityResponse:
    availability: list[AvailabilityItem] = []
    all_available: bool = True
    for item in request.items:
        product = await product_db.get(Product, item.product_id)
        if (product is None) or (product.inventory < item.quantity):
            all_available = False
            availability.append(
                AvailabilityItem(
                    product_id=item.product_id,
                    available=False,
                    available_quantity=(
                        (product.inventory if product is not None else None)
                        if (product.inventory if product is not None else None)
                        is not None
                        else 0
                    ),
                )
            )
        else:
            availability.append(
                AvailabilityItem(
                    product_id=item.product_id,
                    available=True,
                    available_quantity=product.inventory,
                )
            )
    return AvailabilityResponse(all_available=all_available, items=availability)


@router.post(
    "/service/reserve-inventory",
    response_model=ReservationResponse,
    include_in_schema=False,
    dependencies=[Depends(require_service_endpoint)],
)
async def post_service_reserve_inventory(
    request: ReserveInventoryRequest = Body(...),
    product_db: AsyncSession = Depends(get_product_db_db),
    current_user=Depends(get_current_user),
    _rate_limit=Depends(enforce_plan_rate_limit),
) -> ReservationResponse:
    async with _datrix_buffer_events():
        if product_db.in_transaction():
            await product_db.commit()
        async with product_db.begin() as session:
            for item in request.items:
                service = ProductService(product_db)
                product = await service.get(item.product_id)
                if product is None:
                    raise HTTPException(status_code=404, detail="Not found")
                if product.inventory < item.quantity:
                    raise HTTPException(
                        status_code=422,
                        detail={
                            "code": "INSUFFICIENT_INVENTORY",
                            "productId": item.product_id,
                            "requested": item.quantity,
                            "available": product.inventory,
                        },
                    )
                product.inventory = product.inventory - item.quantity
                _product_svc = ProductService(product_db)
                product = await _product_svc.update(
                    product.id,
                    ProductUpdate(**{"inventory": (product.inventory - item.quantity)}),
                    _commit=False,
                )
                _inventory_reservation_svc = InventoryReservationService(product_db)
                _entity = await _inventory_reservation_svc.create(
                    InventoryReservationCreate(
                        **{
                            "reservation_id": request.reservation_id,
                            "product_id": item.product_id,
                            "quantity": item.quantity,
                            "expires_at": (
                                datetime.datetime.now(datetime.timezone.utc)
                                + datetime.timedelta(seconds=request.ttl_seconds)
                            ),
                            "status": ReservationStatus.reserved,
                        }
                    ),
                    _commit=False,
                )
    # Lambda expression: '.map(i => i.productId)'
    product_ids: list[uuid.UUID] = [i.product_id for i in request.items]
    async with _datrix_buffer_events():
        _producer_instance = await _mq_producer.get_producer()
        await _producer_instance.publish_inventory_reserved(
            request.reservation_id, product_ids
        )
    return ReservationResponse(success=True, reservation_id=request.reservation_id)


@router.post(
    "/service/confirm-reservation",
    include_in_schema=False,
    dependencies=[Depends(require_service_endpoint)],
)
async def post_service_confirm_reservation(
    request: ConfirmReservationRequest = Body(...),
    product_db: AsyncSession = Depends(get_product_db_db),
    current_user=Depends(get_current_user),
    _rate_limit=Depends(enforce_plan_rate_limit),
) -> None:
    reservations: list[InventoryReservation] = list(
        (
            await product_db.execute(
                select(InventoryReservation).where(
                    InventoryReservation.reservation_id == request.reservation_id,
                    InventoryReservation.status == ReservationStatus.reserved,
                )
            )
        )
        .scalars()
        .all()
    )
    for reservation in reservations:
        reservation.status = ReservationStatus.confirmed
        _inventory_reservation_svc = InventoryReservationService(product_db)
        reservation = await _inventory_reservation_svc.update(
            reservation.id,
            InventoryReservationUpdate(**{"status": ReservationStatus.confirmed}),
        )
    logger.info(
        "inventory_reservation_confirmed reservation_id=%s", request.reservation_id
    )


@router.post(
    "/service/release-reservation",
    include_in_schema=False,
    dependencies=[Depends(require_service_endpoint)],
)
async def post_service_release_reservation(
    request: ReleaseReservationRequest = Body(...),
    product_db: AsyncSession = Depends(get_product_db_db),
    current_user=Depends(get_current_user),
    _rate_limit=Depends(enforce_plan_rate_limit),
) -> None:
    reservations: list[InventoryReservation] = list(
        (
            await product_db.execute(
                select(InventoryReservation).where(
                    InventoryReservation.reservation_id == request.reservation_id,
                    InventoryReservation.status == ReservationStatus.reserved,
                )
            )
        )
        .scalars()
        .all()
    )
    async with _datrix_buffer_events():
        if product_db.in_transaction():
            await product_db.commit()
        async with product_db.begin() as session:
            for reservation in reservations:
                product = await product_db.get(Product, reservation.product_id)
                if product is not None:
                    product.inventory = product.inventory + reservation.quantity
                    _product_svc = ProductService(product_db)
                    product = await _product_svc.update(
                        product.id,
                        ProductUpdate(
                            **{"inventory": (product.inventory + reservation.quantity)}
                        ),
                        _commit=False,
                    )
                reservation.status = ReservationStatus.released
                _inventory_reservation_svc = InventoryReservationService(product_db)
                reservation = await _inventory_reservation_svc.update(
                    reservation.id,
                    InventoryReservationUpdate(
                        **{"status": ReservationStatus.released}
                    ),
                    _commit=False,
                )
    async with _datrix_buffer_events():
        _producer_instance = await _mq_producer.get_producer()
        await _producer_instance.publish_inventory_released(
            request.reservation_id, "Released by request"
        )
    logger.info(
        "inventory_reservation_released reservation_id=%s", request.reservation_id
    )


# 'whereIn(...)' filters by a set of values
@router.post(
    "/service/bulk",
    response_model=list[ProductResponse],
    include_in_schema=False,
    dependencies=[Depends(require_service_endpoint)],
)
async def post_service_bulk(
    request: BulkProductRequest = Body(...),
    product_db: AsyncSession = Depends(get_product_db_db),
    current_user=Depends(get_current_user),
    _rate_limit=Depends(enforce_plan_rate_limit),
) -> list[Product]:
    return list(
        (await product_db.execute(select(Product).where(Product.id.in_(request.ids))))
        .scalars()
        .all()
    )


@router.get("/category/{category_id}", response_model=list[ProductResponse])
async def get_category_by_category_id(
    category_id: uuid.UUID = Path(...),
    limit: int | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    product_db: AsyncSession = Depends(get_product_db_db),
    _rate_limit=Depends(enforce_plan_rate_limit),
) -> list[Product]:
    return list(
        (
            await product_db.execute(
                select(Product)
                .where(Product.category_id == category_id)
                .where(Product.status == ProductStatus.active)
                .order_by(Product.name.asc())
                .limit((limit if limit is not None else 50))
            )
        )
        .scalars()
        .all()
    )


@router.get(
    "/service/{id}",
    response_model=ProductResponse,
    include_in_schema=False,
    dependencies=[Depends(require_service_endpoint)],
)
async def get_service_by_id(
    id: uuid.UUID = Path(...),
    product_db: AsyncSession = Depends(get_product_db_db),
    current_user=Depends(get_current_user),
    _rate_limit=Depends(enforce_plan_rate_limit),
) -> Product:
    service = ProductService(product_db)
    return await service.get(id)


@router.get("/slug/{slug}", response_model=ProductResponse)
async def get_slug_by_slug(
    slug: str = Path(...),
    product_db: AsyncSession = Depends(get_product_db_db),
    _rate_limit=Depends(enforce_plan_rate_limit),
) -> Product:
    cached: JsonValue | None = (
        lambda _m: (
            None
            if not _m
            else {
                (k.decode() if isinstance(k, bytes) else str(k)): (
                    json.loads(v.decode() if isinstance(v, bytes) else v)
                )
                for k, v in _m.items()
            }
        )
    )(await _get_redis().hgetall(("product:" + f":{str(f'slug:{slug}')}")))
    if cached is not None:
        return cached
    product = (
        (await product_db.execute(select(Product).where(Product.slug == slug)))
        .scalars()
        .first()
    )
    if product is None:
        raise HTTPException(status_code=404, detail="Not found")
    await __import__("asyncio").gather(
        _get_redis().hset(
            ("product:" + f":{str(product.id)}"),
            mapping={
                str(_k): json.dumps(_v, default=str) for _k, _v in product.items()
            },
        ),
        _get_redis().expire(("product:" + f":{str(product.id)}"), 3600),
    )
    return product


@router.put(
    "/{id}/inventory",
    response_model=ProductResponse,
    dependencies=[Depends(require_providers(["identity", "test_auth"]))],
)
async def put_by_id_inventory(
    request: UpdateInventoryRequest = Body(...),
    id: uuid.UUID = Path(...),
    product_db: AsyncSession = Depends(get_product_db_db),
    current_user=Depends(require_roles(["Admin"])),
    _rate_limit=Depends(enforce_plan_rate_limit),
) -> Product:
    service = ProductService(product_db)
    product = await service.get(id)
    if product is None:
        raise HTTPException(status_code=404, detail="Not found")
    old_inventory: int = product.inventory
    product.inventory = request.inventory
    _product_svc = ProductService(product_db)
    product = await _product_svc.update(
        product.id, ProductUpdate(**{"inventory": request.inventory})
    )
    async with _datrix_buffer_events():
        _producer_instance = await _mq_producer.get_producer()
        await _producer_instance.publish_inventory_updated(
            product.id, old_inventory, request.inventory
        )
    return product


@router.put(
    "/{id}/publish",
    response_model=ProductResponse,
    dependencies=[Depends(require_providers(["identity", "test_auth"]))],
)
async def put_by_id_publish(
    id: uuid.UUID = Path(...),
    product_db: AsyncSession = Depends(get_product_db_db),
    current_user=Depends(require_roles(["Admin"])),
    _rate_limit=Depends(enforce_plan_rate_limit),
) -> Product:
    service = ProductService(product_db)
    product = await service.get(id)
    if product is None:
        raise HTTPException(status_code=404, detail="Not found")
    await product.publish(product_db, _commit=True)
    return product


@router.get("/{id}", response_model=ProductResponse)
async def get_product(
    id: uuid.UUID = Path(...),
    product_db: AsyncSession = Depends(get_product_db_db),
    _rate_limit=Depends(enforce_plan_rate_limit),
) -> Product:
    service = ProductService(product_db)
    return await service.get(id)


# Creation is not a plain resource verb here: the explicit post(...) below
# claims POST /api/v1/products so it can generate the slug and dispatch
# ProductCreated. Listing 'create' as well would give one route two
# declarations, and only the first would be reachable.
@router.put(
    "/{id}",
    response_model=ProductResponse,
    dependencies=[Depends(require_providers(["identity", "test_auth"]))],
)
async def update_product(
    body: ProductUpdate = Body(...),
    id: uuid.UUID = Path(...),
    product_db: AsyncSession = Depends(get_product_db_db),
    current_user=Depends(require_roles(["Admin"])),
    _rate_limit=Depends(enforce_plan_rate_limit),
) -> Product:
    service = ProductService(product_db)
    return await service.update(id, body)


@router.delete(
    "/{id}",
    status_code=http_status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_providers(["identity", "test_auth"]))],
)
async def delete_product(
    id: uuid.UUID = Path(...),
    product_db: AsyncSession = Depends(get_product_db_db),
    current_user=Depends(require_roles(["Admin"])),
    _rate_limit=Depends(enforce_plan_rate_limit),
) -> None:
    service = ProductService(product_db)
    await service.delete(id)
