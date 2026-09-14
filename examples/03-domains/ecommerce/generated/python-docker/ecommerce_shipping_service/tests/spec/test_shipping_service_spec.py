"""Specification tests for ecommerce.ShippingService.

Auto-generated from DSL test blocks. Run with:
    pytest tests/spec/ -v -m spec
"""

from __future__ import annotations

import datetime
import uuid

import pytest

from ecommerce_shipping_service.enums.shipment_status import ShipmentStatus
from ecommerce_shipping_service.enums.shipping_carrier import ShippingCarrier
from ecommerce_shipping_service.schemas.shipping_db.shipment import (
    ShipmentCreate,
    ShipmentUpdate,
)
from ecommerce_shipping_service.services.shipping_db.shipment_service import (
    ShipmentService,
)


@pytest.mark.spec
async def test_computed_is_delivered_reflects_delivered_status(db_session, event_spy):
    """computed isDelivered reflects Delivered status"""
    _shipment_svc = ShipmentService(db_session)
    shipment = await _shipment_svc.create(
        ShipmentCreate(
            **{
                "order_id": uuid.uuid4(),
                "tracking_number": "SPEC-TRACK-001",
                "carrier": ShippingCarrier.fed_ex,
                "status": ShipmentStatus.delivered,
                "destination": {
                    "street": "123 Main St",
                    "city": "Springfield",
                    "state": "IL",
                    "zipCode": "62701",
                    "country": "US",
                },
                "weight": 2.5,
                "actual_delivery": datetime.datetime.now(datetime.timezone.utc),
            }
        )
    )
    await db_session.refresh(shipment)
    assert shipment.is_delivered == True


@pytest.mark.spec
async def test_computed_is_in_progress_for_in_transit_status(db_session, event_spy):
    """computed isInProgress for InTransit status"""
    _shipment_svc = ShipmentService(db_session)
    shipment = await _shipment_svc.create(
        ShipmentCreate(
            **{
                "order_id": uuid.uuid4(),
                "tracking_number": "SPEC-TRACK-002",
                "carrier": ShippingCarrier.ups,
                "status": ShipmentStatus.in_transit,
                "destination": {
                    "street": "456 Oak Ave",
                    "city": "Shelbyville",
                    "state": "IL",
                    "zipCode": "62565",
                    "country": "US",
                },
                "weight": 1.75,
            }
        )
    )
    await db_session.refresh(shipment)
    assert shipment.is_in_progress == True


@pytest.mark.spec
async def test_mark_delivered_sets_status_and_actual_delivery(db_session, event_spy):
    """markDelivered sets status and actualDelivery"""
    _shipment_svc = ShipmentService(db_session)
    shipment = await _shipment_svc.create(
        ShipmentCreate(
            **{
                "order_id": uuid.uuid4(),
                "tracking_number": "SPEC-TRACK-003",
                "carrier": ShippingCarrier.usps,
                "status": ShipmentStatus.in_transit,
                "destination": {
                    "street": "789 Elm St",
                    "city": "Capital City",
                    "state": "IL",
                    "zipCode": "62702",
                    "country": "US",
                },
                "weight": 3.25,
            }
        )
    )
    await db_session.refresh(shipment)
    await shipment.mark_delivered(db_session, _commit=True)
    assert shipment.status == ShipmentStatus.delivered
    assert shipment.actual_delivery is not None


@pytest.mark.spec
async def test_mark_failed_sets_status_and_failure_reason(db_session, event_spy):
    """markFailed sets status and failureReason"""
    _shipment_svc = ShipmentService(db_session)
    shipment = await _shipment_svc.create(
        ShipmentCreate(
            **{
                "order_id": uuid.uuid4(),
                "tracking_number": "SPEC-TRACK-004",
                "carrier": ShippingCarrier.dhl,
                "status": ShipmentStatus.out_for_delivery,
                "destination": {
                    "street": "321 Pine Rd",
                    "city": "Ogdenville",
                    "state": "IL",
                    "zipCode": "62703",
                    "country": "US",
                },
                "weight": 5.0,
            }
        )
    )
    await db_session.refresh(shipment)
    await shipment.mark_failed(db_session, "Recipient not available", _commit=True)
    assert shipment.status == ShipmentStatus.failed
    assert shipment.failure_reason == "Recipient not available"


@pytest.mark.spec
async def test_after_update_emits_shipment_dispatched_when_in_transit(
    db_session, event_spy
):
    """afterUpdate emits ShipmentDispatched when InTransit"""
    _shipment_svc = ShipmentService(db_session)
    shipment = await _shipment_svc.create(
        ShipmentCreate(
            **{
                "order_id": uuid.uuid4(),
                "tracking_number": "SPEC-TRACK-005",
                "carrier": ShippingCarrier.fed_ex,
                "status": ShipmentStatus.pending,
                "destination": {
                    "street": "555 Oak Blvd",
                    "city": "Greenfield",
                    "state": "WI",
                    "zipCode": "53220",
                    "country": "US",
                },
                "weight": 2.0,
            }
        )
    )
    await db_session.refresh(shipment)

    _shipment_svc = ShipmentService(db_session)
    shipment = await _shipment_svc.update(
        shipment.id, ShipmentUpdate(**{"status": ShipmentStatus.in_transit})
    )
    assert event_spy.has(
        "ShipmentDispatched",
        shipment_id=shipment.id,
        order_id=shipment.order_id,
        tracking_number=shipment.tracking_number,
    )


@pytest.mark.spec
async def test_after_update_emits_shipment_delivered_when_delivered(
    db_session, event_spy
):
    """afterUpdate emits ShipmentDelivered when Delivered"""
    _shipment_svc = ShipmentService(db_session)
    shipment = await _shipment_svc.create(
        ShipmentCreate(
            **{
                "order_id": uuid.uuid4(),
                "tracking_number": "SPEC-TRACK-006",
                "carrier": ShippingCarrier.ups,
                "status": ShipmentStatus.in_transit,
                "destination": {
                    "street": "888 Willow Ave",
                    "city": "Riverside",
                    "state": "CA",
                    "zipCode": "92501",
                    "country": "US",
                },
                "weight": 4.5,
                "actual_delivery": datetime.datetime.now(datetime.timezone.utc),
            }
        )
    )
    await db_session.refresh(shipment)

    _shipment_svc = ShipmentService(db_session)
    shipment = await _shipment_svc.update(
        shipment.id, ShipmentUpdate(**{"status": ShipmentStatus.delivered})
    )
    assert event_spy.has(
        "ShipmentDelivered",
        shipment_id=shipment.id,
        order_id=shipment.order_id,
        delivered_at=(
            shipment.actual_delivery
            if shipment.actual_delivery is not None
            else datetime.datetime.now(datetime.timezone.utc)
        ),
    )
