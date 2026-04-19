"""PaymentAPI route handlers."""

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
from ecommerce_payment_service.db.session import get_db_db
from ecommerce_payment_service.auth import get_current_user, require_roles
from decimal import Decimal
from ecommerce_payment_service.constants import MAX_PAGE_SIZE
from ecommerce_payment_service.enums.payment_method import PaymentMethod
from ecommerce_payment_service.enums.payment_status import PaymentStatus
from ecommerce_payment_service.functions import generate_transaction_id
from ecommerce_payment_service.functions import process_payment_async
from ecommerce_payment_service.integrations.payment_client import StripePaymentClient
from ecommerce_payment_service.models.db.payment import Payment
from ecommerce_payment_service.models.db.refund import Refund
from ecommerce_payment_service.schemas.db.payment import PaymentResponse
from ecommerce_payment_service.schemas.db.refund import RefundResponse
from ecommerce_payment_service.schemas.process_payment_request import ProcessPaymentRequest
from ecommerce_payment_service.schemas.refund_payment_request import RefundPaymentRequest
from ecommerce_payment_service.schemas.stripe_webhook_request import StripeWebhookRequest
from ecommerce_payment_service.services.db.payment_service import PaymentService
from ecommerce_payment_service.services.db.refund_service import RefundService
from fastapi import HTTPException
from pydantic import JsonValue
from sqlalchemy import select
import datetime
import decimal
import json
import logging
import uuid

logger = logging.getLogger(__name__)
pay_pal_gateway = object()  # Gateway not configured
stripe_gateway = StripePaymentClient()

router = APIRouter(
    prefix="/api/v1/payments",
    tags=["PaymentAPI"],
)


async def process_refund_via_gateway(payment: uuid.UUID, refund: uuid.UUID) -> bool:
    success: bool = False
    transaction_id: str | None = None
    try:
        if (payment.method == PaymentMethod.credit_card) or (
            payment.method == PaymentMethod.debit_card
        ):
            result: JsonValue = stripe_gateway.refund(
                {"transaction_id": payment.transaction_id, "amount": (refund.amount.amount * 100)}
            )
            success = result.success
            transaction_id = result.refund_transaction_id
            if not success:
                refund.error_message = result.error or "Stripe refund failed"
        elif payment.method == PaymentMethod.pay_pal:
            result: JsonValue = pay_pal_gateway.refund(
                {"transaction_id": payment.transaction_id, "amount": refund.amount}
            )
            success = result.success
            transaction_id = result.refund_transaction_id
            if not success:
                refund.error_message = result.error or "PayPal refund failed"
        elif payment.method == PaymentMethod.bank_transfer:
            logger.info("bank_transfer_refund_requires_manual_processing")
            refund.error_message = "Bank transfer refunds require manual processing"
            return False
        if success and (transaction_id != None):
            refund.refund_transaction_id = transaction_id
    except Exception as e:
        logger.error("refund_processing_error")
        refund.error_message = f"Gateway error: {e.message}"
        return False
    return success


@router.get("/my-payments", response_model=list[PaymentResponse])
async def get_my_payments(
    page: int = Query(default=None),
    per_page: int = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_db),
    current_user=Depends(get_current_user),
) -> list[Payment]:
    customer_id: uuid.UUID = current_user.id
    capped_per_page: int = min(per_page, MAX_PAGE_SIZE)
    return list(
        (
            await db.execute(
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


@router.post("/process", response_model=PaymentResponse, status_code=http_status.HTTP_201_CREATED)
async def post_process(
    request: ProcessPaymentRequest = Body(...),
    db: AsyncSession = Depends(get_db_db),
    current_user=Depends(get_current_user),
) -> Payment:
    customer_id: uuid.UUID = current_user.id
    payment = Payment(
        **{
            "order_id": request.order_id,
            "customer_id": customer_id,
            "amount": request.amount,
            "method": request.method,
            "transaction_id": generate_transaction_id(),
            "status": PaymentStatus.pending,
        }
    )
    db.add(payment)
    await db.flush()
    await db.refresh(payment)
    process_payment_async(payment, request.card_token)
    return payment


@router.post("/webhook/stripe", status_code=http_status.HTTP_201_CREATED)
async def post_webhook_stripe(
    request: StripeWebhookRequest = Body(...),
    db: AsyncSession = Depends(get_db_db),
) -> None:
    event_type: str = request.payload.type
    data: JsonValue = request.payload.data.object
    if event_type == "payment_intent.succeeded":
        transaction_id: str = data.metadata.transaction_id
        payment: Payment | None = (
            (await db.execute(select(Payment).where(Payment.transaction_id == transaction_id)))
            .scalars()
            .first()
        )
        if (payment != None) and (payment.status == PaymentStatus.processing):
            payment.status = PaymentStatus.completed
            payment.processed_at = datetime.datetime.now(tz=datetime.timezone.utc)
            payment.gateway_response = json.dumps(data)
            db.add(payment)
            await db.commit()
            await db.refresh(payment)
    elif event_type == "payment_intent.payment_failed":
        transaction_id: str = data.metadata.transaction_id
        payment: Payment | None = (
            (await db.execute(select(Payment).where(Payment.transaction_id == transaction_id)))
            .scalars()
            .first()
        )
        if (payment != None) and (payment.status == PaymentStatus.processing):
            payment.status = PaymentStatus.failed
            payment.error_message = (
                data.last_payment_error.message if data.last_payment_error is not None else None
            ) or "Payment failed"
            payment.gateway_response = json.dumps(data)
            db.add(payment)
            await db.commit()
            await db.refresh(payment)


@router.get("/{id}", response_model=PaymentResponse)
async def get_payment(
    id: uuid.UUID = Path(...),
    db: AsyncSession = Depends(get_db_db),
    current_user=Depends(get_current_user),
) -> Payment:
    service = PaymentService(db)
    return await service.get(id)


@router.get("/order/{order_id}", response_model=PaymentResponse)
async def get_order(
    order_id: uuid.UUID = Path(...),
    db: AsyncSession = Depends(get_db_db),
    current_user=Depends(get_current_user),
) -> Payment:
    result = (
        (await db.execute(select(Payment).where(Payment.order_id == order_id))).scalars().first()
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Not found")
    return result


@router.post(
    "/{id}/refund", response_model=RefundResponse, status_code=http_status.HTTP_201_CREATED
)
async def post_refund(
    id: uuid.UUID = Path(...),
    request: RefundPaymentRequest = Body(...),
    db: AsyncSession = Depends(get_db_db),
    current_user=Depends(require_roles(["admin"])),
) -> Refund:
    service = PaymentService(db)
    payment = await service.get(id)
    if payment is None:
        raise HTTPException(status_code=404, detail="Not found")
    if not payment.can_refund:
        raise HTTPException(
            status_code=422, detail=f"Cannot refund payment in status: {payment.status}"
        )
    total_refunded: decimal.Decimal = Decimal(str(0))
    for refund in payment.refunds:
        if refund.is_successful:
            total_refunded = total_refunded + refund.amount
    if (total_refunded + request.amount).amount > payment.amount.amount:
        raise HTTPException(status_code=422, detail="Refund amount exceeds original payment")
    refund = Refund(
        **{
            "payment": payment,
            "amount": request.amount,
            "reason": request.reason,
            "status": PaymentStatus.pending,
        }
    )
    db.add(refund)
    await db.flush()
    await db.refresh(refund)
    success: bool = await process_refund_via_gateway(payment, refund)
    if success:
        refund.status = PaymentStatus.completed
        refund.processed_at = datetime.datetime.now(tz=datetime.timezone.utc)
        db.add(refund)
        await db.commit()
        await db.refresh(refund)
        new_total_refunded: decimal.Decimal = total_refunded + request.amount
        if new_total_refunded.amount >= payment.amount.amount:
            payment.status = PaymentStatus.refunded
            db.add(payment)
            await db.commit()
            await db.refresh(payment)
    else:
        refund.status = PaymentStatus.failed
        db.add(refund)
        await db.commit()
        await db.refresh(refund)
    return refund


@router.get("/payments/{id}/refunds", response_model=list[RefundResponse])
async def list_payment_refunds(
    id: uuid.UUID = Path(...),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_db),
    current_user=Depends(get_current_user),
) -> list[Refund]:
    # Verify parent exists (raises EntityNotFoundError -> 404)
    payment_service = PaymentService(db)
    await payment_service.get(id)
    # Get children
    refund_service = RefundService(db)
    return await refund_service.get_by_payment(payment_id=id, skip=skip, limit=limit)
