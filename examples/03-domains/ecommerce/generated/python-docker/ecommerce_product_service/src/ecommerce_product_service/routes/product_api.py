"""ProductAPI route handlers."""

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
from ecommerce_product_service.db.session import get_db_db
from ecommerce_product_service.auth import get_current_user, require_roles
from ecommerce_product_service._cache_helpers import _get_redis
from ecommerce_product_service.dependencies import require_internal
from ecommerce_product_service.enums.product_status import ProductStatus
from ecommerce_product_service.enums.reservation_status import ReservationStatus
from ecommerce_product_service.models.db.inventory_reservation import InventoryReservation
from ecommerce_product_service.models.db.product import Product
from ecommerce_product_service.mq.producer import producer_instance as _producer_instance
from ecommerce_product_service.schemas.availability_item import AvailabilityItem
from ecommerce_product_service.schemas.availability_response import AvailabilityResponse
from ecommerce_product_service.schemas.bulk_product_request import BulkProductRequest
from ecommerce_product_service.schemas.check_availability_request import CheckAvailabilityRequest
from ecommerce_product_service.schemas.confirm_reservation_request import ConfirmReservationRequest
from ecommerce_product_service.schemas.create_product_request import CreateProductRequest
from ecommerce_product_service.schemas.db.product import (
    ProductCreate,
    ProductUpdate,
    ProductResponse,
)
from ecommerce_product_service.schemas.db.product import ProductResponse
from ecommerce_product_service.schemas.release_reservation_request import ReleaseReservationRequest
from ecommerce_product_service.schemas.reservation_response import ReservationResponse
from ecommerce_product_service.schemas.reserve_inventory_request import ReserveInventoryRequest
from ecommerce_product_service.schemas.update_inventory_request import UpdateInventoryRequest
from ecommerce_product_service.services.db.product_service import ProductService
from fastapi import HTTPException
from pydantic import JsonValue
from sqlalchemy import select
import datetime
import json
import logging
import uuid

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/products",
    tags=["ProductAPI"],
)


@router.get("/", response_model=list[ProductResponse])
async def list_products(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_db),
) -> list[Product]:
    service = ProductService(db)
    return await service.get_all(skip=skip, limit=limit)


@router.post("/", response_model=ProductResponse, status_code=http_status.HTTP_201_CREATED)
async def create_product(
    body: ProductCreate = Body(...),
    db: AsyncSession = Depends(get_db_db),
    current_user=Depends(require_roles(["admin"])),
) -> Product:
    service = ProductService(db)
    return await service.create(body)


@router.get("/search", response_model=list[ProductResponse])
async def get_search(
    query: str = Query(default=...),
    limit: int | None = Query(default=None),
    offset: int | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db_db),
) -> list[Product]:
    return list(
        (
            await db.execute(
                select(Product)
                .where(Product.name.ilike(f"%{query}%"))
                .where(Product.status == ProductStatus.active)
                .limit((limit or 20))
                .offset((offset or 0))
            )
        )
        .scalars()
        .all()
    )


@router.post("/", response_model=ProductResponse, status_code=http_status.HTTP_201_CREATED)
async def post_endpoint(
    request: CreateProductRequest = Body(...),
    db: AsyncSession = Depends(get_db_db),
    current_user=Depends(require_roles(["admin"])),
) -> Product:
    product = Product(
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
    db.add(product)
    await db.flush()
    await db.refresh(product)
    product.generate_slug(request.name)
    db.add(product)
    await db.commit()
    await db.refresh(product)
    await _producer_instance.publish_product_created(product.id, product.name, product.price)
    return product


@router.post(
    "/internal/check-availability",
    response_model=AvailabilityResponse,
    status_code=http_status.HTTP_201_CREATED,
    dependencies=[Depends(require_internal)],
)
async def post_internal_check_availability(
    request: CheckAvailabilityRequest = Body(...),
    db: AsyncSession = Depends(get_db_db),
) -> AvailabilityResponse:
    availability: list[AvailabilityItem] = []
    all_available: bool = True
    for item in request.items:
        product: Product | None = await db.get(Product, item.product_id)
        if (product == None) or (product.inventory < item.quantity):
            all_available = False
            availability.append(
                {
                    "product_id": item.product_id,
                    "available": False,
                    "available_quantity": (
                        (product.inventory if product is not None else None) or 0
                    ),
                }
            )
        else:
            availability.append(
                {
                    "product_id": item.product_id,
                    "available": True,
                    "available_quantity": product.inventory,
                }
            )
    return AvailabilityResponse(all_available=all_available, items=availability)


@router.post(
    "/internal/reserve-inventory",
    response_model=ReservationResponse,
    status_code=http_status.HTTP_201_CREATED,
    dependencies=[Depends(require_internal)],
)
async def post_internal_reserve_inventory(
    request: ReserveInventoryRequest = Body(...),
    db: AsyncSession = Depends(get_db_db),
) -> ReservationResponse:
    async with db.session.begin() as session:
        for item in request.items:
            service = ProductService(db)
            product = await service.get(item.product_id)
            if product is None:
                raise HTTPException(status_code=404, detail="Not found")
            if product.inventory < item.quantity:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "INSUFFICIENT_INVENTORY",
                        "product_id": item.product_id,
                        "requested": item.quantity,
                        "available": product.inventory,
                    },
                )
            product.inventory = product.inventory - item.quantity
            db.add(product)
            await db.commit()
            await db.refresh(product)
            _entity = InventoryReservation(
                **{
                    "reservation_id": request.reservation_id,
                    "product_id": item.product_id,
                    "quantity": item.quantity,
                    "expires_at": (
                        datetime.datetime.now(tz=datetime.timezone.utc)
                        + datetime.timedelta(seconds=request.ttl_seconds)
                    ),
                    "status": ReservationStatus.reserved,
                }
            )
            db.add(_entity)
            await db.flush()
            await db.refresh(_entity)
    product_ids: list[uuid.UUID] = [i.product_id for i in request.items]
    await _producer_instance.publish_inventory_reserved(request.reservation_id, product_ids)
    return ReservationResponse(success=True, reservation_id=request.reservation_id)


@router.post(
    "/internal/confirm-reservation",
    status_code=http_status.HTTP_201_CREATED,
    dependencies=[Depends(require_internal)],
)
async def post_internal_confirm_reservation(
    request: ConfirmReservationRequest = Body(...),
    db: AsyncSession = Depends(get_db_db),
) -> None:
    reservations: list[InventoryReservation] = list(
        (
            await db.execute(
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
        db.add(reservation)
        await db.commit()
        await db.refresh(reservation)
    logger.info("inventory_reservation_confirmed")


@router.post(
    "/internal/release-reservation",
    status_code=http_status.HTTP_201_CREATED,
    dependencies=[Depends(require_internal)],
)
async def post_internal_release_reservation(
    request: ReleaseReservationRequest = Body(...),
    db: AsyncSession = Depends(get_db_db),
) -> None:
    reservations: list[InventoryReservation] = list(
        (
            await db.execute(
                select(InventoryReservation).where(
                    InventoryReservation.reservation_id == request.reservation_id,
                    InventoryReservation.status == ReservationStatus.reserved,
                )
            )
        )
        .scalars()
        .all()
    )
    async with db.session.begin() as session:
        for reservation in reservations:
            product: Product | None = await db.get(Product, reservation.product_id)
            if product != None:
                product.inventory = product.inventory + reservation.quantity
                db.add(product)
                await db.commit()
                await db.refresh(product)
            reservation.status = ReservationStatus.released
            db.add(reservation)
            await db.commit()
            await db.refresh(reservation)
    await _producer_instance.publish_inventory_released(
        request.reservation_id, "Released by request"
    )
    logger.info("inventory_reservation_released")


@router.post(
    "/internal/bulk",
    response_model=list[ProductResponse],
    status_code=http_status.HTTP_201_CREATED,
    dependencies=[Depends(require_internal)],
)
async def post_internal_bulk(
    request: BulkProductRequest = Body(...),
    db: AsyncSession = Depends(get_db_db),
) -> list[Product]:
    return list(
        (await db.execute(select(Product).where(Product.id.in_(request.ids)))).scalars().all()
    )


@router.get("/{id}", response_model=ProductResponse)
async def get_product(
    id: uuid.UUID = Path(...),
    db: AsyncSession = Depends(get_db_db),
) -> Product:
    service = ProductService(db)
    return await service.get(id)


@router.patch("/{id}", response_model=ProductResponse)
async def update_product(
    id: uuid.UUID = Path(...),
    body: ProductUpdate = Body(...),
    db: AsyncSession = Depends(get_db_db),
    current_user=Depends(require_roles(["admin"])),
) -> Product:
    service = ProductService(db)
    return await service.update(id, body)


@router.delete("/{id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_product(
    id: uuid.UUID = Path(...),
    db: AsyncSession = Depends(get_db_db),
    current_user=Depends(require_roles(["admin"])),
) -> None:
    service = ProductService(db)
    await service.delete(id)


@router.get("/slug/{slug}", response_model=ProductResponse)
async def get_slug(
    slug: str = Path(...),
    db: AsyncSession = Depends(get_db_db),
) -> Product:
    cached: JsonValue | None = (
        json.loads(_raw)
        if (_raw := await _get_redis().get(f"product_cache:{str(f'slug:{slug}')}")) is not None
        else None
    )
    if cached != None:
        return cached
    product = (await db.execute(select(Product).where(Product.slug == slug))).scalars().first()
    if product is None:
        raise HTTPException(status_code=404, detail="Not found")
    await _get_redis().set(f"product_cache:{str(product.id)}", json.dumps(product, default=str))
    return product


@router.get("/category/{category_id}", response_model=list[ProductResponse])
async def get_category(
    category_id: uuid.UUID = Path(...),
    limit: int | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db_db),
) -> list[Product]:
    return list(
        (
            await db.execute(
                select(Product)
                .where(Product.category_id == category_id)
                .where(Product.status == ProductStatus.active)
                .order_by(Product.name.asc())
                .limit((limit or 50))
            )
        )
        .scalars()
        .all()
    )


@router.patch("/{id}/inventory", response_model=ProductResponse)
async def put_inventory(
    id: uuid.UUID = Path(...),
    request: UpdateInventoryRequest = Body(...),
    db: AsyncSession = Depends(get_db_db),
    current_user=Depends(require_roles(["admin"])),
) -> Product:
    service = ProductService(db)
    product = await service.get(id)
    if product is None:
        raise HTTPException(status_code=404, detail="Not found")
    old_inventory: int = product.inventory
    product.inventory = request.inventory
    db.add(product)
    await db.commit()
    await db.refresh(product)
    await _producer_instance.publish_inventory_updated(product.id, old_inventory, request.inventory)
    return product


@router.put("/{id}/publish", response_model=ProductResponse)
async def put_publish(
    id: uuid.UUID = Path(...),
    db: AsyncSession = Depends(get_db_db),
    current_user=Depends(require_roles(["admin"])),
) -> Product:
    service = ProductService(db)
    product = await service.get(id)
    if product is None:
        raise HTTPException(status_code=404, detail="Not found")
    product.publish()
    return product


@router.get(
    "/internal/{id}", response_model=ProductResponse, dependencies=[Depends(require_internal)]
)
async def get_internal(
    id: uuid.UUID = Path(...),
    db: AsyncSession = Depends(get_db_db),
) -> Product:
    service = ProductService(db)
    return await service.get(id)
