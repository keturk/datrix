"""ShippingAPI route handlers."""

import datetime
import decimal
import hashlib
import hmac
import json
import logging
import uuid
from collections.abc import Mapping
from enum import Enum as PyEnum

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query
from pydantic import JsonValue
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from ecommerce_shipping_service._cache_helpers import _get_redis
from ecommerce_shipping_service._json_helpers import _json_index
from ecommerce_shipping_service.auth import (
    get_current_user,
    require_providers,
    require_roles,
)
from ecommerce_shipping_service.config._secrets_resolver import (
    get_secret as _get_webhook_secret,
)
from ecommerce_shipping_service.dependencies import require_service_endpoint
from ecommerce_shipping_service.enums.shipment_status import ShipmentStatus
from ecommerce_shipping_service.enums.shipping_carrier import ShippingCarrier
from ecommerce_shipping_service.event_outbox import (
    buffer_events as _datrix_buffer_events,
)
from ecommerce_shipping_service.functions import (
    calculate_estimated_delivery,
    generate_tracking_number,
    get_estimated_days,
    select_carrier,
)
from ecommerce_shipping_service.models.shipping_db.shipment import Shipment
from ecommerce_shipping_service.models.shipping_db.shipment_event import ShipmentEvent
from ecommerce_shipping_service.mq import producer as _mq_producer
from ecommerce_shipping_service.rate_limit.rate_limit_dependency import (
    enforce_plan_rate_limit,
)
from ecommerce_shipping_service.schemas.add_tracking_event_request import (
    AddTrackingEventRequest,
)
from ecommerce_shipping_service.schemas.address import Address
from ecommerce_shipping_service.schemas.create_shipment_request import (
    CreateShipmentRequest,
)
from ecommerce_shipping_service.schemas.fed_ex_webhook_request import (
    FedExWebhookRequest,
)
from ecommerce_shipping_service.schemas.get_shipping_rates_request import (
    GetShippingRatesRequest,
)
from ecommerce_shipping_service.schemas.shipment_tracking import ShipmentTracking
from ecommerce_shipping_service.schemas.shipping_db.shipment import (
    ShipmentCreate,
    ShipmentResponse,
    ShipmentUpdate,
)
from ecommerce_shipping_service.schemas.shipping_db.shipment_event import (
    ShipmentEventCreate,
    ShipmentEventResponse,
)
from ecommerce_shipping_service.schemas.shipping_db.shipment_item import (
    ShipmentItemCreate,
)
from ecommerce_shipping_service.schemas.shipping_rate_response import (
    ShippingRateResponse,
)
from ecommerce_shipping_service.schemas.update_shipment_status_request import (
    UpdateShipmentStatusRequest,
)
from ecommerce_shipping_service.services.shipping_db.shipment_event_service import (
    ShipmentEventService,
)
from ecommerce_shipping_service.services.shipping_db.shipment_item_service import (
    ShipmentItemService,
)
from ecommerce_shipping_service.services.shipping_db.shipment_service import (
    ShipmentService,
)
from ecommerce_shipping_service.shipping_db.session import get_shipping_db_db

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Inlined runtime
# ---------------------------------------------------------------------------
# A real module in datrix-codegen-python, inlined here rather than written as
# template text, so its behaviour is unit tested by calling it. Emitted only
# when a handler below needs it.
#: Layouts a provider's signature header can take.
HEADER_LAYOUT_PREFIXED = "prefixed"
HEADER_LAYOUT_KEYED_LIST = "keyed_list"

#: Where a scheme's replay timestamp comes from, when it has one.
TIMESTAMP_NONE = "none"
TIMESTAMP_SEPARATE_HEADER = "separate_header"
TIMESTAMP_SIGNATURE_HEADER = "signature_header"

#: Digest encodings a keyed-hash scheme can use.
ENCODING_HEX = "hex"
ENCODING_BASE64 = "base64"

#: Placeholders a declared signed-payload template may carry.
PAYLOAD_BODY = "{body}"
PAYLOAD_TIMESTAMP = "{timestamp}"

#: Returned when verification succeeded. Status 0 is not an HTTP status; it is
#: the sentinel for "no failure", chosen so a caller cannot mistake a truthy
#: status for success.
ACCEPTED = (0, "")


def _keyed_list_fields(header_value: str, separator: str) -> dict[str, list[str]]:
    """Parse a ``k=v`` element list into every value seen per key.

    Values are collected per key rather than overwritten: a provider rolling an
    endpoint secret emits one signature per active secret, and keeping only the
    last would reject valid traffic for the whole overlap window.

    Args:
        header_value: The raw signature header.
        separator: The declared element separator.

    Returns:
        Key -> every value carried under it, in order.
    """
    fields: dict[str, list[str]] = {}
    for element in header_value.split(separator):
        key, _, value = element.strip().partition("=")
        fields.setdefault(key, []).append(value)
    return fields


def _signed_payload(template: str, raw_body: bytes, timestamp_raw: str) -> bytes:
    """Build the exact bytes the signature is computed over.

    The body is spliced in as RAW BYTES, never decoded and re-encoded: providers
    are explicit that any mutation of the raw body -- re-encoding, whitespace,
    key reordering -- breaks verification.

    Args:
        template: The provider's declared payload template.
        raw_body: The request body exactly as received.
        timestamp_raw: The resolved timestamp, as text.

    Returns:
        The bytes to HMAC.
    """
    before, _, after = template.partition(PAYLOAD_BODY)
    prefix = before.replace(PAYLOAD_TIMESTAMP, timestamp_raw).encode("utf-8")
    suffix = after.replace(PAYLOAD_TIMESTAMP, timestamp_raw).encode("utf-8")
    return prefix + raw_body + suffix


def _encoded_digest(
    secret: str, payload: bytes, digest_name: str, encoding: str
) -> str:
    """Compute the expected signature in the provider's declared encoding."""
    digest = hmac.new(secret.encode("utf-8"), payload, getattr(hashlib, digest_name))
    if encoding == ENCODING_BASE64:
        import base64

        return base64.b64encode(digest.digest()).decode("ascii")
    return digest.hexdigest()


def webhook_signature_failure(
    *,
    raw_body: bytes,
    headers: Mapping[str, str],
    secret: str,
    signature_header: str,
    digest_name: str,
    header_layout: str,
    signature_prefix: str | None = None,
    element_separator: str | None = None,
    signature_key: str | None = None,
    timestamp_source: str = TIMESTAMP_NONE,
    timestamp_header: str | None = None,
    timestamp_key: str | None = None,
    tolerance_seconds: int = 0,
    signed_payload_template: str = PAYLOAD_BODY,
    encoding: str = ENCODING_HEX,
    now: int = 0,
) -> tuple[int, str]:
    """Verify a webhook signature against its provider's declared scheme.

    Args:
        raw_body: The request body exactly as received.
        headers: The request headers.
        secret: The endpoint's shared secret.
        signature_header: Header carrying the signature.
        digest_name: ``hashlib`` algorithm name.
        header_layout: ``prefixed`` or ``keyed_list``.
        signature_prefix: For a prefixed layout, the prefix to strip.
        element_separator: For a keyed list, the element separator.
        signature_key: For a keyed list, the key holding signatures.
        timestamp_source: Where the replay timestamp comes from.
        timestamp_header: Header carrying it, when separate.
        timestamp_key: Key carrying it, when inside the signature header.
        tolerance_seconds: Replay window.
        signed_payload_template: What the signature is computed over.
        encoding: ``hex`` or ``base64``.
        now: Current epoch seconds; supplied by the caller so this stays pure.

    Returns:
        :data:`ACCEPTED`, or ``(status, reason)`` where status is 400 for a
        request malformed before the check could run and 401 for a check that
        ran and failed. The reason is for server-side logging only.
    """
    header_value = headers.get(signature_header)
    if not header_value:
        return 400, f"webhook signature missing header={signature_header}"

    fields: dict[str, list[str]] = {}
    if header_layout == HEADER_LAYOUT_PREFIXED:
        # `is None` rather than falsy: an EMPTY prefix is a real layout -- a
        # bare keyed-hash header carries the digest and nothing else -- and
        # treating it as "not declared" would reject every such webhook.
        if signature_prefix is None:
            return 400, "webhook signature layout is not declared"
        if not header_value.startswith(signature_prefix):
            return 400, "webhook signature header malformed"
        signatures = [header_value[len(signature_prefix) :]]
    else:
        if not element_separator or not signature_key:
            return 400, "webhook signature layout is not declared"
        fields = _keyed_list_fields(header_value, element_separator)
        # ONLY the declared key is collected. Every other key is discarded,
        # which is what makes a lower or test-only scheme carried in the same
        # header unusable as a downgrade.
        signatures = fields.get(signature_key, [])
        if not signatures:
            return 400, "webhook signature header carries no usable signature"

    timestamp_raw = ""
    if timestamp_source != TIMESTAMP_NONE:
        if timestamp_source == TIMESTAMP_SEPARATE_HEADER:
            timestamp_raw = headers.get(timestamp_header or "", "")
            if not timestamp_raw:
                return (
                    400,
                    f"webhook timestamp header missing header={timestamp_header}",
                )
        else:
            values = fields.get(timestamp_key or "", [])
            if not values:
                return 400, "webhook signature header carries no timestamp"
            timestamp_raw = values[0]
        try:
            timestamp = int(timestamp_raw)
        except ValueError:
            return 400, "webhook timestamp is not an integer"
        if abs(now - timestamp) > tolerance_seconds:
            return (
                400,
                f"webhook timestamp outside tolerance seconds={tolerance_seconds}",
            )

    expected = _encoded_digest(
        secret,
        _signed_payload(signed_payload_template, raw_body, timestamp_raw),
        digest_name,
        encoding,
    )
    # ANY declared signature may match, and every comparison is constant-time.
    # `==` here would leak the digest one byte at a time under timing analysis.
    if not any(hmac.compare_digest(expected, candidate) for candidate in signatures):
        return 401, "webhook signature mismatch"
    return ACCEPTED


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
    return ShipmentStatus.equalsKeyword(event_type, ShipmentStatus.in_transit)


@router.post(
    "",
    response_model=ShipmentResponse,
    include_in_schema=False,
    dependencies=[Depends(require_service_endpoint)],
)
async def post_endpoint(
    request: CreateShipmentRequest = Body(...),
    shipping_db: AsyncSession = Depends(get_shipping_db_db),
    current_user=Depends(get_current_user),
    _rate_limit=Depends(enforce_plan_rate_limit),
) -> Shipment:
    carrier: ShippingCarrier = select_carrier(request.destination, request.weight)
    estimated_delivery: datetime.datetime = calculate_estimated_delivery(
        carrier, request.destination
    )
    _shipment_svc = ShipmentService(shipping_db)
    shipment = await _shipment_svc.create(
        ShipmentCreate(
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
    )
    for item in request.items:
        _shipment_item_svc = ShipmentItemService(shipping_db)
        _entity = await _shipment_item_svc.create(
            ShipmentItemCreate(
                **{
                    "shipment_id": shipment.id,
                    "product_id": item.product_id,
                    "quantity": item.quantity,
                }
            )
        )
    _shipment_event_svc = ShipmentEventService(shipping_db)
    _entity = await _shipment_event_svc.create(
        ShipmentEventCreate(
            **{
                "shipment_id": shipment.id,
                "timestamp": datetime.datetime.now(datetime.timezone.utc),
                "status": ShipmentStatus.pending,
                "location": "Warehouse",
                "description": "Shipment created, awaiting pickup",
            }
        )
    )
    async with _datrix_buffer_events():
        _producer_instance = await _mq_producer.get_producer()
        await _producer_instance.publish_shipment_created(shipment.id, request.order_id)
    await __import__("asyncio").gather(
        _get_redis().incr(
            (
                "shipments:daily:"
                + f":{str(datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d'))}"
            )
        ),
        _get_redis().expire(
            (
                "shipments:daily:"
                + f":{str(datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d'))}"
            ),
            86400,
        ),
    )
    logger.info(
        "shipment_created shipment_id=%s order_id=%s carrier=%s tracking_number=%s",
        shipment.id,
        request.order_id,
        carrier,
        shipment.tracking_number,
    )
    return shipment


@router.post("/rates")
async def post_rates(
    request: GetShippingRatesRequest = Body(...),
    _rate_limit=Depends(enforce_plan_rate_limit),
) -> list[ShippingRateResponse]:
    rates: list[ShippingRateResponse] = []
    rates.append(
        ShippingRateResponse(
            carrier=ShippingCarrier.fed_ex,
            rate=await calculate_rate(
                ShippingCarrier.fed_ex, request.destination, request.weight
            ),
            estimated_days=get_estimated_days(
                ShippingCarrier.fed_ex, request.destination
            ),
        )
    )
    rates.append(
        ShippingRateResponse(
            carrier=ShippingCarrier.ups,
            rate=await calculate_rate(
                ShippingCarrier.ups, request.destination, request.weight
            ),
            estimated_days=get_estimated_days(ShippingCarrier.ups, request.destination),
        )
    )
    rates.append(
        ShippingRateResponse(
            carrier=ShippingCarrier.usps,
            rate=await calculate_rate(
                ShippingCarrier.usps, request.destination, request.weight
            ),
            estimated_days=get_estimated_days(
                ShippingCarrier.usps, request.destination
            ),
        )
    )
    return rates


# Inbound carrier status callback. The sender is an external machine, so
# the endpoint carries no user auth — authenticity comes from a keyed
# hash over the raw body, verified against a logical secret handle
# declared in config/shipping-service.dcfg before the body is trusted.
# The carrier publishes no registry signature envelope, so the
# sender-generic hmac scheme declares every wire detail here.
@router.post("/webhook/fedex")
async def post_webhook_fedex(
    http_request: Request,
    request: FedExWebhookRequest = Body(...),
    shipping_db: AsyncSession = Depends(get_shipping_db_db),
    _rate_limit=Depends(enforce_plan_rate_limit),
) -> None:
    _raw_body = await http_request.body()
    _secret = await _get_webhook_secret("carrier_webhook_secret")
    _status, _reason = webhook_signature_failure(
        raw_body=_raw_body,
        headers=http_request.headers,
        secret=_secret,
        signature_header="X-Carrier-Signature",
        digest_name="sha256",
        header_layout="prefixed",
        signature_prefix="",
        encoding="hex",
    )
    if _status:
        logger.warning("webhook hmac verification failed reason=%s", _reason)
        raise HTTPException(status_code=_status, detail="Webhook verification failed")
    tracking_number: str = _json_index(request.payload, "trackingNumber")
    event_type: str = _json_index(request.payload, "eventType")
    location: str = (
        _json_index(request.payload, "location")
        if _json_index(request.payload, "location") is not None
        else "Unknown"
    )
    shipment: Shipment | None = (
        (
            await shipping_db.execute(
                select(Shipment).where(Shipment.tracking_number == tracking_number)
            )
        )
        .scalars()
        .first()
    )
    if shipment is None:
        logger.warning(
            "webhook_received_for_unknown_tracking_number tracking_number=%s",
            tracking_number,
        )
        return
    new_status: ShipmentStatus = await map_fed_ex_status(event_type)
    _shipment_event_svc = ShipmentEventService(shipping_db)
    _entity = await _shipment_event_svc.create(
        ShipmentEventCreate(
            **{
                "shipment_id": shipment.id,
                "timestamp": datetime.datetime.now(datetime.timezone.utc),
                "status": new_status,
                "location": location,
                "description": _json_index(request.payload, "description"),
            }
        )
    )
    if shipment.status != new_status:
        shipment.status = new_status
        if new_status == ShipmentStatus.delivered:
            shipment.actual_delivery = datetime.datetime.now(datetime.timezone.utc)
        shipping_db.add(shipment)
        await shipping_db.commit()
        await shipping_db.refresh(shipment)
    await _get_redis().delete(("shipment:" + f":{str(tracking_number)}"))


# Public tracking endpoint - no authentication required
@router.get("/track/{tracking_number}", response_model=ShipmentTracking)
async def get_track_by_tracking_number(
    tracking_number: str = Path(...),
    shipping_db: AsyncSession = Depends(get_shipping_db_db),
    _rate_limit=Depends(enforce_plan_rate_limit),
) -> ShipmentTracking:
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
    )(await _get_redis().hgetall(("shipment:" + f":{str(tracking_number)}")))
    shipment = (
        (
            await shipping_db.execute(
                select(Shipment).where(Shipment.tracking_number == tracking_number)
            )
        )
        .scalars()
        .first()
    )
    if shipment is None:
        raise HTTPException(status_code=404, detail="Not found")
    events: list[ShipmentEvent] = list(
        (
            await shipping_db.execute(
                select(ShipmentEvent)
                .where(ShipmentEvent.shipment_id == shipment.id)
                .order_by(ShipmentEvent.timestamp.asc())
            )
        )
        .scalars()
        .all()
    )
    await __import__("asyncio").gather(
        _get_redis().hset(
            ("shipment:" + f":{str(tracking_number)}"),
            mapping={
                str(_k): json.dumps(_v, default=str)
                for _k, _v in {
                    "trackingNumber": tracking_number,
                    "status": shipment.status,
                    "estimatedDelivery": shipment.estimated_delivery,
                }.items()
            },
        ),
        _get_redis().expire(("shipment:" + f":{str(tracking_number)}"), 1800),
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


@router.get(
    "/order/{order_id}",
    response_model=ShipmentResponse,
    dependencies=[Depends(require_providers(["identity", "test_auth"]))],
)
async def get_order_by_order_id(
    order_id: uuid.UUID = Path(...),
    shipping_db: AsyncSession = Depends(get_shipping_db_db),
    current_user=Depends(get_current_user),
    _rate_limit=Depends(enforce_plan_rate_limit),
) -> Shipment:
    result = (
        (
            await shipping_db.execute(
                select(Shipment).where(Shipment.order_id == order_id)
            )
        )
        .scalars()
        .first()
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Not found")
    return result


@router.get(
    "/{id}/shipment_events",
    response_model=list[ShipmentEventResponse],
    dependencies=[Depends(require_providers(["test_auth"]))],
)
async def list_shipment_events(
    id: uuid.UUID = Path(...),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    shipping_db: AsyncSession = Depends(get_shipping_db_db),
    current_user=Depends(get_current_user),
    _rate_limit=Depends(enforce_plan_rate_limit),
) -> list[ShipmentEvent]:
    # Verify parent exists (raises EntityNotFoundError -> 404)
    shipment_service = ShipmentService(shipping_db)
    await shipment_service.get(id)
    # Get children
    shipment_event_service = ShipmentEventService(shipping_db)
    return await shipment_event_service.get_by_shipment(
        shipment_id=id, skip=skip, limit=limit
    )


@router.post(
    "/{id}/events",
    response_model=ShipmentEventResponse,
    dependencies=[Depends(require_providers(["identity", "test_auth"]))],
)
async def post_by_id_events(
    request: AddTrackingEventRequest = Body(...),
    id: uuid.UUID = Path(...),
    shipping_db: AsyncSession = Depends(get_shipping_db_db),
    current_user=Depends(require_roles(["Admin"])),
    _rate_limit=Depends(enforce_plan_rate_limit),
) -> ShipmentEvent:
    service = ShipmentService(shipping_db)
    shipment = await service.get(id)
    if shipment is None:
        raise HTTPException(status_code=404, detail="Not found")
    _shipment_event_svc = ShipmentEventService(shipping_db)
    event = await _shipment_event_svc.create(
        ShipmentEventCreate(
            **{
                "shipment_id": shipment.id,
                "timestamp": datetime.datetime.now(datetime.timezone.utc),
                "status": request.status,
                "location": request.location,
                "description": request.description,
            }
        )
    )
    if shipment.status != request.status:
        shipment.status = request.status
        if request.status == ShipmentStatus.delivered:
            shipment.actual_delivery = datetime.datetime.now(datetime.timezone.utc)
        _shipment_svc = ShipmentService(shipping_db)
        shipment = await _shipment_svc.update(
            shipment.id,
            ShipmentUpdate(
                **{
                    "actual_delivery": datetime.datetime.now(datetime.timezone.utc),
                    "status": request.status,
                }
            ),
        )
    await _get_redis().delete(("shipment:" + f":{str(shipment.tracking_number)}"))
    return event


@router.put(
    "/{id}/status",
    response_model=ShipmentResponse,
    dependencies=[Depends(require_providers(["identity", "test_auth"]))],
)
async def put_by_id_status(
    request: UpdateShipmentStatusRequest = Body(...),
    id: uuid.UUID = Path(...),
    shipping_db: AsyncSession = Depends(get_shipping_db_db),
    current_user=Depends(require_roles(["Admin"])),
    _rate_limit=Depends(enforce_plan_rate_limit),
) -> Shipment:
    service = ShipmentService(shipping_db)
    shipment = await service.get(id)
    if shipment is None:
        raise HTTPException(status_code=404, detail="Not found")
    old_status: ShipmentStatus = shipment.status
    shipment.status = request.status
    if request.status == ShipmentStatus.delivered:
        shipment.actual_delivery = datetime.datetime.now(datetime.timezone.utc)
    _shipment_svc = ShipmentService(shipping_db)
    shipment = await _shipment_svc.update(
        shipment.id,
        ShipmentUpdate(
            **{
                "actual_delivery": datetime.datetime.now(datetime.timezone.utc),
                "status": request.status,
            }
        ),
    )
    _shipment_event_svc = ShipmentEventService(shipping_db)
    _entity = await _shipment_event_svc.create(
        ShipmentEventCreate(
            **{
                "shipment_id": shipment.id,
                "timestamp": datetime.datetime.now(datetime.timezone.utc),
                "status": request.status,
                "location": (
                    request.location if request.location is not None else "Unknown"
                ),
                "description": (
                    request.description
                    if request.description is not None
                    else f"Status updated to {(request.status.value if isinstance(request.status, PyEnum) else request.status)}"
                ),
            }
        )
    )
    # Invalidate cache on status change
    await _get_redis().delete(("shipment:" + f":{str(shipment.tracking_number)}"))
    logger.info(
        "shipment_status_updated shipment_id=%s old_status=%s new_status=%s",
        id,
        old_status,
        request.status,
    )
    return shipment


@router.get(
    "/{id}",
    response_model=ShipmentResponse,
    dependencies=[Depends(require_providers(["identity", "test_auth"]))],
)
async def get_shipment(
    id: uuid.UUID = Path(...),
    shipping_db: AsyncSession = Depends(get_shipping_db_db),
    current_user=Depends(get_current_user),
    _rate_limit=Depends(enforce_plan_rate_limit),
) -> Shipment:
    service = ShipmentService(shipping_db)
    return await service.get(id)
