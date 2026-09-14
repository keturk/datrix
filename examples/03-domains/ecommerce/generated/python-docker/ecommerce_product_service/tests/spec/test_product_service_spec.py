"""Specification tests for ecommerce.ProductService.

Auto-generated from DSL test blocks. Run with:
    pytest tests/spec/ -v -m spec
"""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

import pytest

from ecommerce_product_service.enums.product_status import ProductStatus
from ecommerce_product_service.schemas.product_db.category import CategoryCreate
from ecommerce_product_service.schemas.product_db.inventory_reservation import (
    InventoryReservationCreate,
)
from ecommerce_product_service.schemas.product_db.product import (
    ProductCreate,
    ProductUpdate,
)
from ecommerce_product_service.services._base import ValidationError
from ecommerce_product_service.services.product_db.category_service import (
    CategoryService,
)
from ecommerce_product_service.services.product_db.inventory_reservation_service import (
    InventoryReservationService,
)
from ecommerce_product_service.services.product_db.product_service import ProductService


@pytest.mark.spec
async def test_validation_rejects_non_positive_reservation_quantity(
    db_session, event_spy
):
    """validation rejects non-positive reservation quantity"""
    _category_svc = CategoryService(db_session)
    category = await _category_svc.create(
        CategoryCreate(**{"name": "Test Category", "slug": "test-category"})
    )
    await db_session.refresh(category)
    _product_svc = ProductService(db_session)
    product = await _product_svc.create(
        ProductCreate(
            **{
                "name": "SpecTestProduct",
                "description": "Test product for spec",
                "price": Decimal(str(29.99)),
                "status": ProductStatus.active,
                "slug": "spec-test-product",
                "category_id": category.id,
                "images": [],
                "tags": [],
            }
        )
    )
    await db_session.refresh(product)
    with pytest.raises(ValidationError, match="Reservation quantity must be positive"):
        _inventory_reservation_svc = InventoryReservationService(db_session)
        _entity = await _inventory_reservation_svc.create(
            InventoryReservationCreate(
                **{
                    "reservation_id": uuid.uuid4(),
                    "product_id": product.id,
                    "quantity": 0,
                    "expires_at": (
                        datetime.datetime.now(datetime.timezone.utc)
                        + datetime.timedelta(days=1)
                    ),
                }
            )
        )


@pytest.mark.spec
async def test_after_update_emits_inventory_updated_on_inventory_change(
    db_session, event_spy
):
    """afterUpdate emits InventoryUpdated on inventory change"""
    _category_svc = CategoryService(db_session)
    category = await _category_svc.create(
        CategoryCreate(
            **{"name": "Inventory Test Category", "slug": "inventory-test-category"}
        )
    )
    await db_session.refresh(category)
    _product_svc = ProductService(db_session)
    product = await _product_svc.create(
        ProductCreate(
            **{
                "name": "SpecInventoryProduct",
                "description": "Test product for inventory spec",
                "price": Decimal(str(19.99)),
                "status": ProductStatus.active,
                "slug": "spec-inventory-product",
                "category_id": category.id,
                "images": [],
                "tags": [],
            }
        )
    )
    await db_session.refresh(product)

    _product_svc = ProductService(db_session)
    product = await _product_svc.update(product.id, ProductUpdate(**{"inventory": 50}))
    assert event_spy.has(
        "InventoryUpdated", product_id=product.id, old_quantity=0, new_quantity=50
    )


@pytest.mark.spec
async def test_publish_transitions_product_from_draft_to_active(db_session, event_spy):
    """publish transitions product from Draft to Active"""
    _category_svc = CategoryService(db_session)
    category = await _category_svc.create(
        CategoryCreate(
            **{"name": "Publish Test Category", "slug": "publish-test-category"}
        )
    )
    await db_session.refresh(category)
    _product_svc = ProductService(db_session)
    product = await _product_svc.create(
        ProductCreate(
            **{
                "name": "SpecDraftProduct",
                "description": "Draft product for publish spec",
                "price": Decimal(str(39.99)),
                "status": ProductStatus.draft,
                "slug": "spec-draft-product",
                "category_id": category.id,
                "images": [],
                "tags": [],
            }
        )
    )
    await db_session.refresh(product)
    await product.publish(db_session, _commit=True)
    assert product.status == ProductStatus.active


@pytest.mark.spec
async def test_discontinue_marks_product_as_discontinued(db_session, event_spy):
    """discontinue marks product as Discontinued"""
    _category_svc = CategoryService(db_session)
    category = await _category_svc.create(
        CategoryCreate(
            **{"name": "Discontinue Test Category", "slug": "discontinue-test-category"}
        )
    )
    await db_session.refresh(category)
    _product_svc = ProductService(db_session)
    product = await _product_svc.create(
        ProductCreate(
            **{
                "name": "SpecActiveProduct",
                "description": "Active product for discontinue spec",
                "price": Decimal(str(59.99)),
                "status": ProductStatus.active,
                "slug": "spec-active-product",
                "category_id": category.id,
                "images": [],
                "tags": [],
            }
        )
    )
    await db_session.refresh(product)
    await product.discontinue(db_session, _commit=True)
    assert product.status == ProductStatus.discontinued
