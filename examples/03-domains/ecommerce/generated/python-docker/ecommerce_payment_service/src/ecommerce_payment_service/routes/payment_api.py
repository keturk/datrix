"""PaymentAPI route handlers."""

import datetime
import decimal
import hashlib
import hmac
import logging
import time
import uuid
from collections.abc import Mapping
from decimal import Decimal
from enum import Enum as PyEnum

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query
from pydantic import JsonValue
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from ecommerce_payment_service._datrix_helpers import _datrix_exc_message
from ecommerce_payment_service._json_helpers import (
    _json_data,
    _json_index,
    _json_serialize,
)
from ecommerce_payment_service.auth import (
    get_current_user,
    require_providers,
    require_roles,
)
from ecommerce_payment_service.config._secrets_resolver import (
    get_secret as _get_webhook_secret,
)
from ecommerce_payment_service.constants import MAX_PAGE_SIZE
from ecommerce_payment_service.enums.payment_method import PaymentMethod
from ecommerce_payment_service.enums.payment_status import PaymentStatus
from ecommerce_payment_service.functions import (
    generate_transaction_id,
    process_payment_async,
)
from ecommerce_payment_service.integrations.payment_client import StripePaymentGateway
from ecommerce_payment_service.models.payment_db.payment import Payment
from ecommerce_payment_service.models.payment_db.refund import Refund
from ecommerce_payment_service.payment_db.session import get_payment_db_db
from ecommerce_payment_service.schemas.payment_db.payment import (
    PaymentCreate,
    PaymentResponse,
    PaymentUpdate,
)
from ecommerce_payment_service.schemas.payment_db.refund import (
    RefundCreate,
    RefundResponse,
    RefundUpdate,
)
from ecommerce_payment_service.schemas.process_payment_request import (
    ProcessPaymentRequest,
)
from ecommerce_payment_service.schemas.refund_payment_request import (
    RefundPaymentRequest,
)
from ecommerce_payment_service.schemas.stripe_webhook_request import (
    StripeWebhookRequest,
)
from ecommerce_payment_service.services.payment_db.payment_service import PaymentService
from ecommerce_payment_service.services.payment_db.refund_service import RefundService

logger = logging.getLogger(__name__)
stripe_gateway = StripePaymentGateway()

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
    prefix="/api/v1/payments",
    tags=["PaymentAPI"],
)


async def process_refund_via_gateway(payment: Payment, refund: Refund) -> bool:
    success: bool = False
    transaction_id: str | None = None
    # 'try/catch' for error handling with external gateway calls
    try:
        if (payment.method == PaymentMethod.credit_card) or (
            payment.method == PaymentMethod.debit_card
        ):
            result: JsonValue = stripe_gateway.refund(
                {
                    "transaction_id": payment.transaction_id,
                    "amount": (refund.amount * 100),
                }
            )
            success = _json_index(result, "success")
            transaction_id = _json_index(result, "refundTransactionId")
            if not success:
                refund.error_message = (
                    _json_index(result, "error")
                    if _json_index(result, "error") is not None
                    else "Stripe refund failed"
                )
        elif payment.method == PaymentMethod.pay_pal:
            logger.info(
                "pay_pal_refund_skipped_configure_pay_pal_as_payment_provider_to_enable_gateway_refunds payment_id=%s refund_id=%s",
                payment.id,
                refund.id,
            )
            refund.error_message = (
                "PayPal refunds require PayPal payment integration in integrations.dcfg"
            )
            return False
        elif payment.method == PaymentMethod.bank_transfer:
            logger.info(
                "bank_transfer_refund_requires_manual_processing payment_id=%s refund_id=%s amount=%s",
                payment.id,
                refund.id,
                refund.amount,
            )
            refund.error_message = "Bank transfer refunds require manual processing"
            return False
        if success and (transaction_id is not None):
            refund.refund_transaction_id = transaction_id
    except Exception as e:
        logger.error(
            "refund_processing_error payment_id=%s error=%s",
            payment.id,
            _datrix_exc_message(e),
        )
        refund.error_message = f"Gateway error: {(_datrix_exc_message(e).value if isinstance(_datrix_exc_message(e), PyEnum) else _datrix_exc_message(e))}"
        return False
    return success


@router.get(
    "/my-payments",
    response_model=list[PaymentResponse],
    dependencies=[Depends(require_providers(["identity", "test_auth"]))],
)
async def get_my_payments(
    page: int = Query(default=1),
    per_page: int = Query(default=20),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    payment_db: AsyncSession = Depends(get_payment_db_db),
    current_user=Depends(get_current_user),
) -> list[Payment]:
    customer_id: uuid.UUID = current_user.id
    capped_per_page: int = min(per_page, MAX_PAGE_SIZE)
    return list(
        (
            await payment_db.execute(
                select(Payment)
                .where(Payment.customer_id == customer_id)
                .order_by(Payment.created_at.desc())
                .offset(((page - 1) * capped_per_page))
                .limit(capped_per_page)
            )
        )
        .scalars()
        .all()
    )


@router.post(
    "/process",
    response_model=PaymentResponse,
    dependencies=[Depends(require_providers(["identity", "test_auth"]))],
)
async def post_process(
    request: ProcessPaymentRequest = Body(...),
    payment_db: AsyncSession = Depends(get_payment_db_db),
    current_user=Depends(get_current_user),
) -> Payment:
    customer_id: uuid.UUID = current_user.id
    _payment_svc = PaymentService(payment_db)
    payment = await _payment_svc.create(
        PaymentCreate(
            **{
                "order_id": request.order_id,
                "customer_id": customer_id,
                "amount": request.amount,
                "method": request.method,
                "transaction_id": generate_transaction_id(),
                "status": PaymentStatus.pending,
            }
        )
    )
    # Delegate to async processing function
    await process_payment_async(payment, request.card_token, payment_db, _commit=True)
    return payment


# Inbound payment-gateway callback. The sender is an external machine,
# so the endpoint carries no user auth — authenticity comes from the
# gateway's payload signature, verified against a logical secret handle
# declared in config/payment-service.dcfg before the body is trusted.
@router.post("/webhook/stripe")
async def post_webhook_stripe(
    http_request: Request,
    request: StripeWebhookRequest = Body(...),
    payment_db: AsyncSession = Depends(get_payment_db_db),
) -> None:
    _raw_body = await http_request.body()
    _secret = await _get_webhook_secret("payment_webhook_secret")
    _status, _reason = webhook_signature_failure(
        raw_body=_raw_body,
        headers=http_request.headers,
        secret=_secret,
        signature_header="Stripe-Signature",
        digest_name="sha256",
        header_layout="keyed_list",
        signature_prefix=None,
        element_separator=",",
        signature_key="v1",
        signed_payload_template="{timestamp}.{body}",
        timestamp_source="signature_header",
        timestamp_header=None,
        timestamp_key="t",
        tolerance_seconds=300,
        now=int(time.time()),
    )
    if _status:
        logger.warning("webhook verification failed reason=%s", _reason)
        raise HTTPException(status_code=_status, detail="Webhook verification failed")
    event_type: str = _json_index(request.payload, "type")
    data: JsonValue = _json_data(
        _json_index(_json_index(request.payload, "data"), "object")
    )
    if event_type == "payment_intent.succeeded":
        transaction_id: str = _json_index(
            _json_index(data, "metadata"), "transactionId"
        )
        payment: Payment | None = (
            (
                await payment_db.execute(
                    select(Payment).where(Payment.transaction_id == transaction_id)
                )
            )
            .scalars()
            .first()
        )
        if (payment is not None) and (payment.status == PaymentStatus.processing):
            payment.status = PaymentStatus.completed
            payment.processed_at = datetime.datetime.now(datetime.timezone.utc)
            payment.gateway_response = _json_serialize(data)
            payment_db.add(payment)
            await payment_db.commit()
            await payment_db.refresh(payment)
    elif event_type == "payment_intent.payment_failed":
        transaction_id: str = _json_index(
            _json_index(data, "metadata"), "transactionId"
        )
        payment: Payment | None = (
            (
                await payment_db.execute(
                    select(Payment).where(Payment.transaction_id == transaction_id)
                )
            )
            .scalars()
            .first()
        )
        if (payment is not None) and (payment.status == PaymentStatus.processing):
            payment.status = PaymentStatus.failed
            payment.error_message = (
                (
                    _json_index(data, "last_payment_error").message
                    if _json_index(data, "last_payment_error") is not None
                    else None
                )
                if (
                    _json_index(data, "last_payment_error").message
                    if _json_index(data, "last_payment_error") is not None
                    else None
                )
                is not None
                else "Payment failed"
            )
            payment.gateway_response = _json_serialize(data)
            payment_db.add(payment)
            await payment_db.commit()
            await payment_db.refresh(payment)


@router.get(
    "/order/{order_id}",
    response_model=PaymentResponse,
    dependencies=[Depends(require_providers(["identity", "test_auth"]))],
)
async def get_order_by_order_id(
    order_id: uuid.UUID = Path(...),
    payment_db: AsyncSession = Depends(get_payment_db_db),
    current_user=Depends(get_current_user),
) -> Payment:
    result = (
        (await payment_db.execute(select(Payment).where(Payment.order_id == order_id)))
        .scalars()
        .first()
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Not found")
    return result


@router.get(
    "/{id}/refunds",
    response_model=list[RefundResponse],
    dependencies=[Depends(require_providers(["test_auth"]))],
)
async def list_payment_refunds(
    id: uuid.UUID = Path(...),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    payment_db: AsyncSession = Depends(get_payment_db_db),
    current_user=Depends(get_current_user),
) -> list[Refund]:
    # Verify parent exists (raises EntityNotFoundError -> 404)
    payment_service = PaymentService(payment_db)
    await payment_service.get(id)
    # Get children
    refund_service = RefundService(payment_db)
    return await refund_service.get_by_payment(payment_id=id, skip=skip, limit=limit)


@router.post(
    "/{id}/refund",
    response_model=RefundResponse,
    dependencies=[Depends(require_providers(["identity", "test_auth"]))],
)
async def post_by_id_refund(
    request: RefundPaymentRequest = Body(...),
    id: uuid.UUID = Path(...),
    payment_db: AsyncSession = Depends(get_payment_db_db),
    current_user=Depends(require_roles(["Admin"])),
) -> Refund:
    service = PaymentService(payment_db)
    payment = await service.get(id)
    if payment is None:
        raise HTTPException(status_code=404, detail="Not found")
    if not payment.can_refund:
        raise HTTPException(
            status_code=422,
            detail=f"Cannot refund payment in status: {(payment.status.value if isinstance(payment.status, PyEnum) else payment.status)}",
        )
    # Calculate total already refunded to prevent over-refunding
    total_refunded: decimal.Decimal = Decimal(str(0))
    for refund in payment.refunds:
        if refund.is_successful:
            total_refunded = total_refunded.append(refund.amount)
    if total_refunded.append(request.amount) > payment.amount:
        raise HTTPException(
            status_code=422, detail="Refund amount exceeds original payment"
        )
    _refund_svc = RefundService(payment_db)
    refund = await _refund_svc.create(
        RefundCreate(
            **{
                "payment_id": payment.id,
                "amount": request.amount,
                "reason": request.reason,
                "status": PaymentStatus.pending,
            }
        )
    )
    success: bool = await process_refund_via_gateway(payment, refund)
    if success:
        refund.status = PaymentStatus.completed
        refund.processed_at = datetime.datetime.now(datetime.timezone.utc)
        _refund_svc = RefundService(payment_db)
        refund = await _refund_svc.update(
            refund.id,
            RefundUpdate(
                **{
                    "processed_at": datetime.datetime.now(datetime.timezone.utc),
                    "status": PaymentStatus.completed,
                }
            ),
        )
        new_total_refunded: decimal.Decimal = total_refunded.append(request.amount)
        if new_total_refunded.amount >= payment.amount:
            payment.status = PaymentStatus.refunded
            _payment_svc = PaymentService(payment_db)
            payment = await _payment_svc.update(
                payment.id, PaymentUpdate(**{"status": PaymentStatus.refunded})
            )
    else:
        refund.status = PaymentStatus.failed
        _refund_svc = RefundService(payment_db)
        refund = await _refund_svc.update(
            refund.id, RefundUpdate(**{"status": PaymentStatus.failed})
        )
    return refund


@router.get(
    "/{id}",
    response_model=PaymentResponse,
    dependencies=[Depends(require_providers(["identity", "test_auth"]))],
)
async def get_payment(
    id: uuid.UUID = Path(...),
    payment_db: AsyncSession = Depends(get_payment_db_db),
    current_user=Depends(get_current_user),
) -> Payment:
    service = PaymentService(payment_db)
    return await service.get(id)
