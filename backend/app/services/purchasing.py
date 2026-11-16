"""Suppliers and purchase orders.

Purchase order lifecycle: DRAFT -> SUBMITTED -> PARTIALLY_RECEIVED -> RECEIVED,
with CANCELLED allowed before everything has been received. Receiving creates
PURCHASE_RECEIPT inventory movements (updating moving-average cost). Each
delivery needs an idempotency key so a retried request cannot receive twice.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.api.deps import RestaurantContext
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.permissions import Permission
from app.db.base import ZERO
from app.models import (
    Ingredient,
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseOrderReceipt,
    PurchaseOrderReceiptLine,
    Supplier,
    SupplierIngredient,
)
from app.models.enums import MovementType, PurchaseOrderStatus
from app.repositories.tenant import get_owned, scoped
from app.schemas.common import PageParams, paginate
from app.schemas.purchasing import (
    CancelPurchaseOrder,
    PurchaseOrderCreate,
    PurchaseOrderItemIn,
    PurchaseOrderItemOut,
    PurchaseOrderListItem,
    PurchaseOrderOut,
    PurchaseOrderUpdate,
    ReceiptOut,
    ReceiveRequest,
    SupplierCreate,
    SupplierIngredientIn,
    SupplierIngredientOut,
    SupplierIngredientUpdate,
    SupplierOut,
    SupplierUpdate,
)
from app.services import realtime
from app.services.audit import record_audit
from app.services.inventory import COST_QUANTUM, StockChange, apply_stock_changes, convert
from app.services.restaurants import next_counter

OPEN_PO_STATUSES = (PurchaseOrderStatus.SUBMITTED, PurchaseOrderStatus.PARTIALLY_RECEIVED)


def _po_event(db: Session, ctx: RestaurantContext, po: PurchaseOrder, event_type: str) -> None:
    realtime.emit(
        db,
        ctx.restaurant_id,
        event_type,
        entity_id=po.id,
        actor_user_id=ctx.user_id,
        data={"display_number": po_display(po.po_number), "status": po.status.value},
    )


def po_display(number: int) -> str:
    return f"PO-{number:05d}"


def _cost_per_base(ingredient: Ingredient, cost_per_unit: Decimal, unit: str | None) -> Decimal:
    factor = convert(ingredient, Decimal(1), unit)
    if factor <= 0:
        raise ValidationFailed("Invalid unit for the price.")
    return (cost_per_unit / factor).quantize(COST_QUANTUM, ROUND_HALF_UP)


def _minor(value: Decimal) -> int:
    return int(value.quantize(Decimal(1), ROUND_HALF_UP))


# --------------------------------------------------------------------------- suppliers


def list_suppliers(db: Session, ctx: RestaurantContext, include_inactive: bool) -> list[SupplierOut]:
    stmt = scoped(Supplier, ctx.restaurant_id)
    if not include_inactive:
        stmt = stmt.where(Supplier.is_active.is_(True))
    suppliers = db.scalars(stmt.order_by(Supplier.name)).all()
    links = dict(
        db.execute(
            select(SupplierIngredient.supplier_id, func.count())
            .where(SupplierIngredient.restaurant_id == ctx.restaurant_id)
            .group_by(SupplierIngredient.supplier_id)
        ).all()
    )
    open_pos = dict(
        db.execute(
            select(PurchaseOrder.supplier_id, func.count())
            .where(PurchaseOrder.restaurant_id == ctx.restaurant_id, PurchaseOrder.status.in_(OPEN_PO_STATUSES))
            .group_by(PurchaseOrder.supplier_id)
        ).all()
    )
    out = []
    for supplier in suppliers:
        row = SupplierOut.model_validate(supplier)
        row.ingredient_count = links.get(supplier.id, 0)
        row.open_purchase_orders = open_pos.get(supplier.id, 0)
        out.append(row)
    return out


def get_supplier(db: Session, ctx: RestaurantContext, supplier_id: uuid.UUID) -> Supplier:
    return get_owned(db, Supplier, supplier_id, ctx.restaurant_id, "Supplier")


def _unique_supplier(db: Session, ctx: RestaurantContext, name: str, exclude: uuid.UUID | None = None) -> None:
    stmt = scoped(Supplier, ctx.restaurant_id).where(func.lower(Supplier.name) == name.lower())
    if exclude:
        stmt = stmt.where(Supplier.id != exclude)
    if db.scalar(stmt):
        raise Conflict("A supplier with this name already exists.")


def create_supplier(db: Session, ctx: RestaurantContext, data: SupplierCreate) -> SupplierOut:
    _unique_supplier(db, ctx, data.name)
    supplier = Supplier(restaurant_id=ctx.restaurant_id, **data.model_dump())
    db.add(supplier)
    record_audit(
        db,
        action="supplier.created",
        actor_user_id=ctx.user_id,
        restaurant_id=ctx.restaurant_id,
        entity_type="supplier",
        details={"name": data.name},
        ip_address=ctx.ip,
    )
    realtime.emit(db, ctx.restaurant_id, "supplier.changed", actor_user_id=ctx.user_id)
    db.commit()
    return SupplierOut.model_validate(supplier)


def update_supplier(db: Session, ctx: RestaurantContext, supplier_id: uuid.UUID, data: SupplierUpdate) -> SupplierOut:
    supplier = get_supplier(db, ctx, supplier_id)
    changes = data.model_dump(exclude_unset=True)
    if changes.get("name"):
        _unique_supplier(db, ctx, changes["name"], exclude=supplier.id)
    for field, value in changes.items():
        if value is not None or field in {"contact_name", "phone", "email", "address", "notes"}:
            setattr(supplier, field, value)
    realtime.emit(db, ctx.restaurant_id, "supplier.changed", actor_user_id=ctx.user_id)
    db.commit()
    return SupplierOut.model_validate(supplier)


def _link_out(link: SupplierIngredient, ingredient: Ingredient) -> SupplierIngredientOut:
    out = SupplierIngredientOut.model_validate(link)
    out.ingredient_name = ingredient.name
    out.base_unit = ingredient.base_unit.value
    return out


def list_supplier_ingredients(
    db: Session, ctx: RestaurantContext, supplier_id: uuid.UUID
) -> list[SupplierIngredientOut]:
    supplier = get_supplier(db, ctx, supplier_id)
    rows = db.execute(
        select(SupplierIngredient, Ingredient)
        .join(Ingredient, Ingredient.id == SupplierIngredient.ingredient_id)
        .where(SupplierIngredient.supplier_id == supplier.id)
        .order_by(Ingredient.name)
    ).all()
    return [_link_out(link, ingredient) for link, ingredient in rows]


def _ingredient(db: Session, ctx: RestaurantContext, ingredient_id: uuid.UUID) -> Ingredient:
    return get_owned(
        db, Ingredient, ingredient_id, ctx.restaurant_id, "Ingredient", options=(selectinload(Ingredient.units),)
    )


def add_supplier_ingredient(
    db: Session, ctx: RestaurantContext, supplier_id: uuid.UUID, data: SupplierIngredientIn
) -> SupplierIngredientOut:
    supplier = get_supplier(db, ctx, supplier_id)
    ingredient = _ingredient(db, ctx, data.ingredient_id)
    if db.scalar(
        select(SupplierIngredient).where(
            SupplierIngredient.supplier_id == supplier.id, SupplierIngredient.ingredient_id == ingredient.id
        )
    ):
        raise Conflict("This ingredient is already linked to the supplier.")
    link = SupplierIngredient(
        restaurant_id=ctx.restaurant_id,
        supplier_id=supplier.id,
        ingredient_id=ingredient.id,
        supplier_sku=data.supplier_sku,
        lead_time_days=data.lead_time_days,
    )
    _apply_link_values(link, ingredient, data.unit_cost_minor, data.min_order_quantity, data.unit)
    db.add(link)
    if ingredient.default_supplier_id is None:
        ingredient.default_supplier_id = supplier.id
    realtime.emit(db, ctx.restaurant_id, "supplier.changed", actor_user_id=ctx.user_id)
    db.commit()
    return _link_out(link, ingredient)


def _apply_link_values(
    link: SupplierIngredient, ingredient: Ingredient, cost: Decimal | None, moq: Decimal | None, unit: str | None
) -> None:
    if cost is not None:
        link.unit_cost_minor = _cost_per_base(ingredient, cost, unit)
    if moq is not None:
        link.min_order_quantity = convert(ingredient, moq, unit)


def update_supplier_ingredient(
    db: Session, ctx: RestaurantContext, supplier_id: uuid.UUID, link_id: uuid.UUID, data: SupplierIngredientUpdate
) -> SupplierIngredientOut:
    link = db.scalar(
        select(SupplierIngredient).where(
            SupplierIngredient.id == link_id,
            SupplierIngredient.supplier_id == supplier_id,
            SupplierIngredient.restaurant_id == ctx.restaurant_id,
        )
    )
    if link is None:
        raise NotFound("Supplier ingredient not found.")
    ingredient = _ingredient(db, ctx, link.ingredient_id)
    changes = data.model_dump(exclude_unset=True)
    if "supplier_sku" in changes:
        link.supplier_sku = data.supplier_sku
    if "lead_time_days" in changes:
        link.lead_time_days = data.lead_time_days
    _apply_link_values(link, ingredient, data.unit_cost_minor, data.min_order_quantity, data.unit)
    realtime.emit(db, ctx.restaurant_id, "supplier.changed", actor_user_id=ctx.user_id)
    db.commit()
    return _link_out(link, ingredient)


def remove_supplier_ingredient(db: Session, ctx: RestaurantContext, supplier_id: uuid.UUID, link_id: uuid.UUID) -> None:
    link = db.scalar(
        select(SupplierIngredient).where(
            SupplierIngredient.id == link_id,
            SupplierIngredient.supplier_id == supplier_id,
            SupplierIngredient.restaurant_id == ctx.restaurant_id,
        )
    )
    if link is not None:
        db.delete(link)
        realtime.emit(db, ctx.restaurant_id, "supplier.changed", actor_user_id=ctx.user_id)
        db.commit()


# --------------------------------------------------------------------------- purchase orders


def _po_query(ctx: RestaurantContext):
    return scoped(PurchaseOrder, ctx.restaurant_id).options(
        selectinload(PurchaseOrder.items),
        selectinload(PurchaseOrder.receipts).selectinload(PurchaseOrderReceipt.lines),
    )


def load_po(db: Session, ctx: RestaurantContext, po_id: uuid.UUID, *, for_update: bool = False) -> PurchaseOrder:
    if for_update:
        get_owned(db, PurchaseOrder, po_id, ctx.restaurant_id, "Purchase order", for_update=True)
    po = db.scalar(_po_query(ctx).where(PurchaseOrder.id == po_id).execution_options(populate_existing=True))
    if po is None:
        raise NotFound("Purchase order not found.")
    return po


def po_out(db: Session, po: PurchaseOrder) -> PurchaseOrderOut:
    out = PurchaseOrderOut.model_validate(po)
    out.display_number = po_display(po.po_number)
    out.supplier_name = db.scalar(select(Supplier.name).where(Supplier.id == po.supplier_id))
    ingredients = (
        {
            i.id: i
            for i in db.scalars(
                select(Ingredient).where(Ingredient.id.in_({item.ingredient_id for item in po.items}))
            ).all()
        }
        if po.items
        else {}
    )
    items = []
    for item in po.items:
        row = PurchaseOrderItemOut.model_validate(item)
        ingredient = ingredients.get(item.ingredient_id)
        row.ingredient_name = ingredient.name if ingredient else None
        row.base_unit = ingredient.base_unit.value if ingredient else None
        row.quantity_remaining = item.quantity_ordered - item.quantity_received
        row.line_total_minor = _minor(item.quantity_ordered * item.unit_cost_minor)
        items.append(row)
    out.items = items
    out.receipts = [ReceiptOut.model_validate(r) for r in po.receipts]
    out.received_total_minor = sum(r.total_cost_minor for r in po.receipts)
    return out


def _build_items(
    db: Session, ctx: RestaurantContext, supplier: Supplier, items: list[PurchaseOrderItemIn]
) -> list[PurchaseOrderItem]:
    links = {
        link.ingredient_id: link
        for link in db.scalars(select(SupplierIngredient).where(SupplierIngredient.supplier_id == supplier.id)).all()
    }
    built = []
    for position, data in enumerate(items):
        ingredient = _ingredient(db, ctx, data.ingredient_id)
        if not ingredient.is_active:
            raise ValidationFailed(f"{ingredient.name} is inactive.")
        unit = data.unit or ingredient.base_unit.value
        base_qty = convert(ingredient, data.quantity, unit)
        if base_qty <= 0:
            raise ValidationFailed(f"Quantity for {ingredient.name} is too small.")
        if data.unit_cost_minor is not None:
            cost = _cost_per_base(ingredient, data.unit_cost_minor, unit)
        elif links.get(ingredient.id) and links[ingredient.id].unit_cost_minor is not None:
            cost = links[ingredient.id].unit_cost_minor
        else:
            cost = ingredient.average_cost_minor
        built.append(
            PurchaseOrderItem(
                position=position,
                ingredient_id=ingredient.id,
                quantity_ordered=base_qty,
                input_quantity=data.quantity,
                input_unit=unit,
                unit_cost_minor=cost or ZERO,
            )
        )
    return built


def _estimate(po: PurchaseOrder) -> int:
    return _minor(sum((i.quantity_ordered * i.unit_cost_minor for i in po.items), ZERO))


def create_purchase_order(
    db: Session, ctx: RestaurantContext, data: PurchaseOrderCreate, *, commit: bool = True
) -> PurchaseOrder:
    supplier = get_supplier(db, ctx, data.supplier_id)
    if not supplier.is_active:
        raise ValidationFailed("This supplier is inactive.")
    po = PurchaseOrder(
        restaurant_id=ctx.restaurant_id,
        po_number=next_counter(db, ctx.restaurant_id, "po_number"),
        supplier_id=supplier.id,
        status=PurchaseOrderStatus.DRAFT,
        expected_delivery_date=data.expected_delivery_date,
        notes=data.notes,
        created_by=ctx.user_id,
        items=_build_items(db, ctx, supplier, data.items),
    )
    po.estimated_total_minor = _estimate(po)
    db.add(po)
    db.flush()
    record_audit(
        db,
        action="purchase_order.created",
        actor_user_id=ctx.user_id,
        restaurant_id=ctx.restaurant_id,
        entity_type="purchase_order",
        entity_id=po.id,
        details={"supplier": supplier.name},
        ip_address=ctx.ip,
    )
    _po_event(db, ctx, po, "po.created")
    if commit:
        db.commit()
    return po


def update_purchase_order(
    db: Session, ctx: RestaurantContext, po_id: uuid.UUID, data: PurchaseOrderUpdate
) -> PurchaseOrderOut:
    po = load_po(db, ctx, po_id, for_update=True)
    if po.status != PurchaseOrderStatus.DRAFT:
        raise Conflict("Only draft purchase orders can be edited.", code="po_not_editable")
    fields = data.model_fields_set
    if "expected_delivery_date" in fields:
        po.expected_delivery_date = data.expected_delivery_date
    if "notes" in fields:
        po.notes = data.notes
    if data.items is not None:
        supplier = get_supplier(db, ctx, po.supplier_id)
        po.items.clear()
        db.flush()
        po.items.extend(_build_items(db, ctx, supplier, data.items))
    po.estimated_total_minor = _estimate(po)
    _po_event(db, ctx, po, "po.updated")
    db.commit()
    return po_out(db, load_po(db, ctx, po.id))


def submit_purchase_order(db: Session, ctx: RestaurantContext, po_id: uuid.UUID) -> PurchaseOrderOut:
    po = load_po(db, ctx, po_id, for_update=True)
    if po.status == PurchaseOrderStatus.SUBMITTED:
        return po_out(db, po)
    if po.status != PurchaseOrderStatus.DRAFT:
        raise Conflict("Only draft purchase orders can be submitted.", code="invalid_transition")
    if not po.items:
        raise ValidationFailed("Add at least one item before submitting.")
    po.status = PurchaseOrderStatus.SUBMITTED
    po.submitted_at = datetime.now(UTC)
    po.submitted_by = ctx.user_id
    record_audit(
        db,
        action="purchase_order.submitted",
        actor_user_id=ctx.user_id,
        restaurant_id=ctx.restaurant_id,
        entity_type="purchase_order",
        entity_id=po.id,
        details={"estimated_total_minor": po.estimated_total_minor},
        ip_address=ctx.ip,
    )
    _po_event(db, ctx, po, "po.submitted")
    db.commit()
    return po_out(db, load_po(db, ctx, po.id))


def receive_purchase_order(
    db: Session, ctx: RestaurantContext, po_id: uuid.UUID, data: ReceiveRequest, idempotency_key: str
) -> tuple[PurchaseOrderOut, bool]:
    def replay() -> tuple[PurchaseOrderOut, bool] | None:
        existing = db.scalar(
            scoped(PurchaseOrderReceipt, ctx.restaurant_id).where(
                PurchaseOrderReceipt.idempotency_key == idempotency_key
            )
        )
        if existing is None:
            return None
        if existing.purchase_order_id != po_id:
            raise Conflict("This idempotency key was already used for another delivery.", code="idempotency_key_reused")
        return po_out(db, load_po(db, ctx, po_id)), True

    early = replay()
    if early:
        return early
    po = load_po(db, ctx, po_id, for_update=True)
    late = replay()  # A duplicate may have committed while we waited for the lock.
    if late:
        return late
    if po.status not in OPEN_PO_STATUSES:
        raise Conflict("Only submitted purchase orders can be received.", code="po_not_receivable")
    items = {i.id: i for i in po.items}
    if len({line.item_id for line in data.lines}) != len(data.lines):
        raise ValidationFailed("Each purchase order line may appear once per delivery.")
    receipt = PurchaseOrderReceipt(
        restaurant_id=ctx.restaurant_id,
        purchase_order_id=po.id,
        idempotency_key=idempotency_key,
        notes=data.notes,
        received_by=ctx.user_id,
    )
    db.add(receipt)
    db.flush()
    changes, total = [], ZERO
    for line in data.lines:
        item = items.get(line.item_id)
        if item is None:
            raise ValidationFailed("A delivery line does not belong to this purchase order.")
        ingredient = _ingredient(db, ctx, item.ingredient_id)
        unit = line.unit or item.input_unit
        qty = convert(ingredient, line.quantity, unit)
        remaining = item.quantity_ordered - item.quantity_received
        if qty > remaining:
            raise ValidationFailed(
                f"{ingredient.name}: received quantity exceeds the {remaining} "
                f"{ingredient.base_unit.value} still outstanding.",
                code="over_receipt",
            )
        cost = (
            _cost_per_base(ingredient, line.unit_cost_minor, unit)
            if line.unit_cost_minor is not None
            else item.unit_cost_minor
        )
        item.quantity_received += qty
        receipt.lines.append(
            PurchaseOrderReceiptLine(
                purchase_order_item_id=item.id, ingredient_id=ingredient.id, quantity=qty, unit_cost_minor=cost
            )
        )
        total += qty * cost
        changes.append(
            StockChange(
                ingredient.id,
                qty,
                MovementType.PURCHASE_RECEIPT,
                f"Received on {po_display(po.po_number)}",
                unit_cost_minor=cost if cost else None,
                input_quantity=line.quantity,
                input_unit=unit,
            )
        )
    receipt.total_cost_minor = _minor(total)
    apply_stock_changes(
        db,
        ctx.restaurant,
        changes,
        actor_user_id=ctx.user_id,
        purchase_order_id=po.id,
        purchase_order_receipt_id=receipt.id,
    )
    fully = all(i.quantity_received >= i.quantity_ordered for i in po.items)
    po.status = PurchaseOrderStatus.RECEIVED if fully else PurchaseOrderStatus.PARTIALLY_RECEIVED
    if fully:
        po.received_at = datetime.now(UTC)
    record_audit(
        db,
        action="purchase_order.received",
        actor_user_id=ctx.user_id,
        restaurant_id=ctx.restaurant_id,
        entity_type="purchase_order",
        entity_id=po.id,
        details={"receipt_id": str(receipt.id), "total_cost_minor": receipt.total_cost_minor, "fully_received": fully},
        ip_address=ctx.ip,
    )
    _po_event(db, ctx, po, "po.received")
    supplier_name = db.scalar(select(Supplier.name).where(Supplier.id == po.supplier_id))
    realtime.notify(
        db,
        ctx.restaurant_id,
        kind="PO_RECEIVED",
        title=f"{po_display(po.po_number)} {'fully received' if fully else 'partly received'}",
        body=f"Delivery from {supplier_name} added to stock." + ("" if fully else " Some lines are still outstanding."),
        link=f"/purchase-orders/{po.id}",
        permission=Permission.PURCHASING_READ,
        entity_type="purchase_order",
        entity_id=po.id,
        actor_user_id=ctx.user_id,
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        result = replay()
        if result:
            return result
        raise
    return po_out(db, load_po(db, ctx, po.id)), False


def cancel_purchase_order(
    db: Session, ctx: RestaurantContext, po_id: uuid.UUID, data: CancelPurchaseOrder
) -> PurchaseOrderOut:
    po = load_po(db, ctx, po_id, for_update=True)
    if po.status == PurchaseOrderStatus.CANCELLED:
        return po_out(db, po)
    if po.status == PurchaseOrderStatus.RECEIVED:
        raise Conflict("Fully received purchase orders cannot be cancelled.", code="invalid_transition")
    po.status = PurchaseOrderStatus.CANCELLED
    po.cancelled_at = datetime.now(UTC)
    po.cancel_reason = data.reason
    record_audit(
        db,
        action="purchase_order.cancelled",
        actor_user_id=ctx.user_id,
        restaurant_id=ctx.restaurant_id,
        entity_type="purchase_order",
        entity_id=po.id,
        details={"reason": data.reason},
        ip_address=ctx.ip,
    )
    _po_event(db, ctx, po, "po.cancelled")
    db.commit()
    return po_out(db, load_po(db, ctx, po.id))


def list_purchase_orders(
    db: Session,
    ctx: RestaurantContext,
    params: PageParams,
    *,
    status: list[PurchaseOrderStatus] | None,
    supplier_id: uuid.UUID | None,
) -> tuple[list[PurchaseOrderListItem], int]:
    stmt = (
        scoped(PurchaseOrder, ctx.restaurant_id)
        .options(selectinload(PurchaseOrder.items))
        .order_by(PurchaseOrder.created_at.desc(), PurchaseOrder.po_number.desc())
    )
    if status:
        stmt = stmt.where(PurchaseOrder.status.in_(status))
    if supplier_id:
        stmt = stmt.where(PurchaseOrder.supplier_id == supplier_id)
    pos, total = paginate(db, stmt, params)
    names = dict(
        db.execute(select(Supplier.id, Supplier.name).where(Supplier.restaurant_id == ctx.restaurant_id)).all()
    )
    return [
        PurchaseOrderListItem(
            id=po.id,
            po_number=po.po_number,
            display_number=po_display(po.po_number),
            supplier_id=po.supplier_id,
            supplier_name=names.get(po.supplier_id, "?"),
            status=po.status,
            expected_delivery_date=po.expected_delivery_date,
            estimated_total_minor=po.estimated_total_minor,
            item_count=len(po.items),
            created_at=po.created_at,
        )
        for po in pos
    ], total


def incoming_quantities(db: Session, restaurant_id: uuid.UUID) -> dict[uuid.UUID, Decimal]:
    """Outstanding quantity on submitted / partially received purchase orders."""
    rows = db.execute(
        select(
            PurchaseOrderItem.ingredient_id,
            func.sum(PurchaseOrderItem.quantity_ordered - PurchaseOrderItem.quantity_received),
        )
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderItem.purchase_order_id)
        .where(PurchaseOrder.restaurant_id == restaurant_id, PurchaseOrder.status.in_(OPEN_PO_STATUSES))
        .group_by(PurchaseOrderItem.ingredient_id)
    ).all()
    return {ingredient_id: qty for ingredient_id, qty in rows if qty and qty > 0}
