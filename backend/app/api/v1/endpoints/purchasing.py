"""Suppliers and purchase orders."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import RestaurantContext, require
from app.core.permissions import Permission
from app.db.session import get_db
from app.models.enums import PurchaseOrderStatus
from app.schemas.common import Page, PageParams
from app.schemas.purchasing import (
    CancelPurchaseOrder,
    PurchaseOrderCreate,
    PurchaseOrderListItem,
    PurchaseOrderOut,
    PurchaseOrderUpdate,
    ReceiveRequest,
    SupplierCreate,
    SupplierIngredientIn,
    SupplierIngredientOut,
    SupplierIngredientUpdate,
    SupplierOut,
    SupplierUpdate,
)
from app.services import purchasing
from app.utils.types import IdempotencyKey

router = APIRouter()
sup_read = require(Permission.SUPPLIERS_READ)
sup_write = require(Permission.SUPPLIERS_WRITE)
po_read = require(Permission.PURCHASING_READ)
po_write = require(Permission.PURCHASING_WRITE)


@router.get("/suppliers", response_model=list[SupplierOut], tags=["suppliers"])
def list_suppliers(
    include_inactive: bool = False, ctx: RestaurantContext = Depends(sup_read), db: Session = Depends(get_db)
) -> list[SupplierOut]:
    return purchasing.list_suppliers(db, ctx, include_inactive)


@router.post("/suppliers", response_model=SupplierOut, status_code=status.HTTP_201_CREATED, tags=["suppliers"])
def create_supplier(
    data: SupplierCreate, ctx: RestaurantContext = Depends(sup_write), db: Session = Depends(get_db)
) -> SupplierOut:
    return purchasing.create_supplier(db, ctx, data)


@router.get("/suppliers/{supplier_id}", response_model=SupplierOut, tags=["suppliers"])
def get_supplier(
    supplier_id: uuid.UUID, ctx: RestaurantContext = Depends(sup_read), db: Session = Depends(get_db)
) -> SupplierOut:
    return SupplierOut.model_validate(purchasing.get_supplier(db, ctx, supplier_id))


@router.patch("/suppliers/{supplier_id}", response_model=SupplierOut, tags=["suppliers"])
def update_supplier(
    supplier_id: uuid.UUID,
    data: SupplierUpdate,
    ctx: RestaurantContext = Depends(sup_write),
    db: Session = Depends(get_db),
) -> SupplierOut:
    return purchasing.update_supplier(db, ctx, supplier_id, data)


@router.get("/suppliers/{supplier_id}/ingredients", response_model=list[SupplierIngredientOut], tags=["suppliers"])
def supplier_ingredients(
    supplier_id: uuid.UUID, ctx: RestaurantContext = Depends(sup_read), db: Session = Depends(get_db)
) -> list[SupplierIngredientOut]:
    return purchasing.list_supplier_ingredients(db, ctx, supplier_id)


@router.post(
    "/suppliers/{supplier_id}/ingredients",
    response_model=SupplierIngredientOut,
    status_code=status.HTTP_201_CREATED,
    tags=["suppliers"],
)
def add_supplier_ingredient(
    supplier_id: uuid.UUID,
    data: SupplierIngredientIn,
    ctx: RestaurantContext = Depends(sup_write),
    db: Session = Depends(get_db),
) -> SupplierIngredientOut:
    return purchasing.add_supplier_ingredient(db, ctx, supplier_id, data)


@router.patch(
    "/suppliers/{supplier_id}/ingredients/{link_id}", response_model=SupplierIngredientOut, tags=["suppliers"]
)
def update_supplier_ingredient(
    supplier_id: uuid.UUID,
    link_id: uuid.UUID,
    data: SupplierIngredientUpdate,
    ctx: RestaurantContext = Depends(sup_write),
    db: Session = Depends(get_db),
) -> SupplierIngredientOut:
    return purchasing.update_supplier_ingredient(db, ctx, supplier_id, link_id, data)


@router.delete(
    "/suppliers/{supplier_id}/ingredients/{link_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["suppliers"]
)
def remove_supplier_ingredient(
    supplier_id: uuid.UUID,
    link_id: uuid.UUID,
    ctx: RestaurantContext = Depends(sup_write),
    db: Session = Depends(get_db),
) -> Response:
    purchasing.remove_supplier_ingredient(db, ctx, supplier_id, link_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/purchase-orders", response_model=Page[PurchaseOrderListItem], tags=["purchase-orders"])
def list_purchase_orders(
    status_filter: list[PurchaseOrderStatus] | None = Query(None, alias="status"),
    supplier_id: uuid.UUID | None = None,
    params: PageParams = Depends(),
    ctx: RestaurantContext = Depends(po_read),
    db: Session = Depends(get_db),
) -> Page[PurchaseOrderListItem]:
    items, total = purchasing.list_purchase_orders(db, ctx, params, status=status_filter, supplier_id=supplier_id)
    return Page(items=items, total=total, page=params.page, page_size=params.page_size)


@router.post(
    "/purchase-orders", response_model=PurchaseOrderOut, status_code=status.HTTP_201_CREATED, tags=["purchase-orders"]
)
def create_purchase_order(
    data: PurchaseOrderCreate, ctx: RestaurantContext = Depends(po_write), db: Session = Depends(get_db)
) -> PurchaseOrderOut:
    po = purchasing.create_purchase_order(db, ctx, data)
    return purchasing.po_out(db, purchasing.load_po(db, ctx, po.id))


@router.get("/purchase-orders/{po_id}", response_model=PurchaseOrderOut, tags=["purchase-orders"])
def get_purchase_order(
    po_id: uuid.UUID, ctx: RestaurantContext = Depends(po_read), db: Session = Depends(get_db)
) -> PurchaseOrderOut:
    return purchasing.po_out(db, purchasing.load_po(db, ctx, po_id))


@router.patch("/purchase-orders/{po_id}", response_model=PurchaseOrderOut, tags=["purchase-orders"])
def update_purchase_order(
    po_id: uuid.UUID,
    data: PurchaseOrderUpdate,
    ctx: RestaurantContext = Depends(po_write),
    db: Session = Depends(get_db),
) -> PurchaseOrderOut:
    return purchasing.update_purchase_order(db, ctx, po_id, data)


@router.post("/purchase-orders/{po_id}/submit", response_model=PurchaseOrderOut, tags=["purchase-orders"])
def submit_purchase_order(
    po_id: uuid.UUID, ctx: RestaurantContext = Depends(po_write), db: Session = Depends(get_db)
) -> PurchaseOrderOut:
    return purchasing.submit_purchase_order(db, ctx, po_id)


@router.post(
    "/purchase-orders/{po_id}/receive",
    response_model=PurchaseOrderOut,
    tags=["purchase-orders"],
    summary="Receive a full or partial delivery (Idempotency-Key header required)",
)
def receive_purchase_order(
    po_id: uuid.UUID,
    data: ReceiveRequest,
    response: Response,
    key: IdempotencyKey = Header(..., alias="Idempotency-Key"),
    ctx: RestaurantContext = Depends(po_write),
    db: Session = Depends(get_db),
) -> PurchaseOrderOut:
    po, replayed = purchasing.receive_purchase_order(db, ctx, po_id, data, key)
    if replayed:
        response.headers["Idempotent-Replayed"] = "true"
    return po


@router.post("/purchase-orders/{po_id}/cancel", response_model=PurchaseOrderOut, tags=["purchase-orders"])
def cancel_purchase_order(
    po_id: uuid.UUID,
    data: CancelPurchaseOrder,
    ctx: RestaurantContext = Depends(po_write),
    db: Session = Depends(get_db),
) -> PurchaseOrderOut:
    return purchasing.cancel_purchase_order(db, ctx, po_id, data)
