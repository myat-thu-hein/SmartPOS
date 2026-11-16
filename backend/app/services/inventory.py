"""Ingredient inventory: the only code path that changes stock balances.

Every change creates an immutable ``InventoryMovement`` and updates the cached
``Ingredient.current_stock`` in the same transaction while the ingredient row
is locked (``SELECT ... FOR UPDATE``). Rows are always locked in id order so
concurrent orders touching the same ingredients cannot deadlock.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import RestaurantContext
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.permissions import Permission
from app.db.base import ZERO
from app.models import (
    Ingredient,
    IngredientUnit,
    InventoryMovement,
    Restaurant,
    Supplier,
    User,
)
from app.models.enums import MovementType
from app.repositories.tenant import get_owned, scoped
from app.schemas.common import PageParams, paginate
from app.schemas.inventory import (
    IngredientCreate,
    IngredientOut,
    IngredientUnitIn,
    IngredientUpdate,
    InventorySummary,
    MovementCreate,
    MovementOut,
    StockCountCreate,
)
from app.services import realtime
from app.services.audit import record_audit
from app.services.units import allowed_units, format_quantity, is_standard_unit, normalise_unit, quantize, to_base

COST_QUANTUM = Decimal("0.0001")
MANUAL_MOVEMENT_TYPES = {MovementType.RECEIPT, MovementType.ISSUE, MovementType.ADJUSTMENT, MovementType.WASTE}


class InsufficientStock(Conflict):
    code = "insufficient_stock"


@dataclass(frozen=True)
class StockChange:
    ingredient_id: uuid.UUID
    quantity: Decimal  # signed, base units
    movement_type: MovementType
    reason: str | None = None
    unit_cost_minor: Decimal | None = None  # per base unit
    input_quantity: Decimal | None = None
    input_unit: str | None = None


# --------------------------------------------------------------------------- helpers


def custom_units(ingredient: Ingredient) -> dict[str, Decimal]:
    return {u.unit_name: u.factor_to_base for u in ingredient.units}


def convert(ingredient: Ingredient, quantity: Decimal, unit: str | None) -> Decimal:
    return to_base(quantity, unit or ingredient.base_unit.value, ingredient.base_unit, custom_units(ingredient))


def is_low_stock(ingredient: Ingredient) -> bool:
    return ingredient.current_stock <= ingredient.reorder_level


def stock_value_minor(ingredient: Ingredient) -> int:
    if ingredient.current_stock <= 0:
        return 0
    return int((ingredient.current_stock * ingredient.average_cost_minor).quantize(Decimal(1), ROUND_HALF_UP))


def lock_ingredients(db: Session, restaurant_id: uuid.UUID, ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, Ingredient]:
    """Lock ingredient rows in a deterministic order and return them by id."""
    wanted = sorted(set(ids))
    if not wanted:
        return {}
    rows = db.scalars(
        select(Ingredient)
        .where(Ingredient.restaurant_id == restaurant_id, Ingredient.id.in_(wanted))
        .order_by(Ingredient.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()
    found = {i.id: i for i in rows}
    missing = [i for i in wanted if i not in found]
    if missing:
        raise NotFound("Ingredient not found.", details={"ingredient_ids": [str(i) for i in missing]})
    return found


def apply_stock_changes(
    db: Session,
    restaurant: Restaurant,
    changes: list[StockChange],
    *,
    actor_user_id: uuid.UUID | None,
    order_id: uuid.UUID | None = None,
    purchase_order_id: uuid.UUID | None = None,
    purchase_order_receipt_id: uuid.UUID | None = None,
    allow_negative: bool | None = None,
) -> list[InventoryMovement]:
    """Apply signed stock changes atomically. The caller commits.

    Raises ``InsufficientStock`` (listing every short ingredient) before writing
    anything if a decrease would make stock negative and the restaurant does
    not explicitly allow negative stock.
    """
    changes = [c for c in changes if c.quantity != 0]
    if not changes:
        return []
    ingredients = lock_ingredients(db, restaurant.id, (c.ingredient_id for c in changes))
    permit_negative = restaurant.allow_negative_stock if allow_negative is None else allow_negative

    # Validate the net effect per ingredient before writing anything.
    net: dict[uuid.UUID, Decimal] = {}
    for change in changes:
        net[change.ingredient_id] = net.get(change.ingredient_id, ZERO) + change.quantity
    shortages = []
    for ingredient_id, delta in net.items():
        ingredient = ingredients[ingredient_id]
        if delta < 0 and ingredient.current_stock + delta < 0 and not permit_negative:
            shortages.append(
                {
                    "ingredient_id": str(ingredient_id),
                    "ingredient_name": ingredient.name,
                    "required": float(-delta),
                    "available": float(ingredient.current_stock),
                    "unit": ingredient.base_unit.value,
                }
            )
    if shortages:
        names = ", ".join(s["ingredient_name"] for s in shortages)
        raise InsufficientStock(f"Not enough stock for: {names}.", details={"shortages": shortages})

    before = {ingredient_id: ingredients[ingredient_id].current_stock for ingredient_id in net}
    movements = []
    for change in changes:
        ingredient = ingredients[change.ingredient_id]
        # A movement without an explicit cost (sale, waste, adjustment...) records the
        # moving-average cost in effect, so usage is later valued at the cost of the day.
        cost_basis = change.unit_cost_minor
        if cost_basis is None and ingredient.average_cost_minor > 0:
            cost_basis = ingredient.average_cost_minor
        if change.unit_cost_minor is not None and change.quantity > 0:
            _update_average_cost(ingredient, change.quantity, change.unit_cost_minor)
        ingredient.current_stock = quantize(ingredient.current_stock + change.quantity)
        movement = InventoryMovement(
            restaurant_id=restaurant.id,
            ingredient_id=ingredient.id,
            movement_type=change.movement_type,
            quantity=quantize(change.quantity),
            balance_after=ingredient.current_stock,
            unit_cost_minor=cost_basis,
            input_quantity=change.input_quantity,
            input_unit=change.input_unit,
            reason=change.reason,
            order_id=order_id,
            purchase_order_id=purchase_order_id,
            purchase_order_receipt_id=purchase_order_receipt_id,
            actor_user_id=actor_user_id,
        )
        db.add(movement)
        movements.append(movement)
    db.flush()
    _announce_stock_changes(db, restaurant, [ingredients[i] for i in net], before, actor_user_id)
    return movements


def _announce_stock_changes(
    db: Session,
    restaurant: Restaurant,
    changed: list[Ingredient],
    before: Mapping[uuid.UUID, Decimal],
    actor_user_id: uuid.UUID | None,
) -> None:
    """Live update for stock screens, plus alerts when an ingredient crosses its reorder
    level or runs out. Alerts fire on the crossing only, so they do not repeat."""
    realtime.emit(
        db,
        restaurant.id,
        "stock.changed",
        data={"ingredient_ids": [str(i.id) for i in changed]},
        actor_user_id=actor_user_id,
    )
    for ingredient in changed:
        was, now = before[ingredient.id], ingredient.current_stock
        unit = ingredient.base_unit.value
        if was > 0 >= now:
            realtime.notify(
                db,
                restaurant.id,
                kind="OUT_OF_STOCK",
                severity="critical",
                title=f"{ingredient.name} is out of stock",
                body=f"Stock is {format_quantity(now, unit)}. "
                + (
                    "Sales can continue, but stock stays negative until it is restocked or counted."
                    if restaurant.allow_negative_stock
                    else "Orders that use it cannot be confirmed until it is restocked."
                ),
                link="/inventory",
                permission=Permission.INVENTORY_READ,
                entity_type="ingredient",
                entity_id=ingredient.id,
                actor_user_id=actor_user_id,
            )
        elif ingredient.reorder_level > 0 and was > ingredient.reorder_level >= now:
            realtime.notify(
                db,
                restaurant.id,
                kind="LOW_STOCK",
                severity="warning",
                title=f"{ingredient.name} is running low",
                body=(
                    f"{format_quantity(now, unit)} left; "
                    f"the reorder level is {format_quantity(ingredient.reorder_level, unit)}."
                ),
                link="/forecasting?tab=recommendations",
                permission=Permission.INVENTORY_READ,
                entity_type="ingredient",
                entity_id=ingredient.id,
                actor_user_id=actor_user_id,
            )


def _update_average_cost(ingredient: Ingredient, quantity: Decimal, unit_cost: Decimal) -> None:
    """Moving weighted-average cost per base unit."""
    on_hand = max(ingredient.current_stock, ZERO)
    total_qty = on_hand + quantity
    if on_hand == 0 or ingredient.average_cost_minor == 0:
        new_cost = unit_cost
    else:
        new_cost = (on_hand * ingredient.average_cost_minor + quantity * unit_cost) / total_qty
    ingredient.average_cost_minor = new_cost.quantize(COST_QUANTUM, ROUND_HALF_UP)


# --------------------------------------------------------------------------- ingredients


def _ingredient_query(restaurant_id: uuid.UUID):
    return scoped(Ingredient, restaurant_id).options(selectinload(Ingredient.units))


def to_out(ingredient: Ingredient, supplier_names: Mapping[uuid.UUID, str] | None = None) -> IngredientOut:
    out = IngredientOut.model_validate(ingredient)
    out.is_low_stock = is_low_stock(ingredient)
    out.stock_value_minor = stock_value_minor(ingredient)
    out.allowed_units = allowed_units(ingredient.base_unit, custom_units(ingredient))
    if supplier_names and ingredient.default_supplier_id:
        out.default_supplier_name = supplier_names.get(ingredient.default_supplier_id)
    return out


def supplier_names(db: Session, restaurant_id: uuid.UUID) -> dict[uuid.UUID, str]:
    return dict(db.execute(select(Supplier.id, Supplier.name).where(Supplier.restaurant_id == restaurant_id)).all())


def list_ingredients(
    db: Session, ctx: RestaurantContext, *, search: str | None, low_stock_only: bool, include_inactive: bool
) -> list[IngredientOut]:
    stmt = _ingredient_query(ctx.restaurant_id)
    if not include_inactive:
        stmt = stmt.where(Ingredient.is_active.is_(True))
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(or_(Ingredient.name.ilike(like), Ingredient.sku.ilike(like)))
    if low_stock_only:
        stmt = stmt.where(Ingredient.current_stock <= Ingredient.reorder_level)
    names = supplier_names(db, ctx.restaurant_id)
    return [to_out(i, names) for i in db.scalars(stmt.order_by(Ingredient.name)).all()]


def get_ingredient(db: Session, ctx: RestaurantContext, ingredient_id: uuid.UUID) -> Ingredient:
    return get_owned(
        db, Ingredient, ingredient_id, ctx.restaurant_id, "Ingredient", options=(selectinload(Ingredient.units),)
    )


def _check_supplier(db: Session, ctx: RestaurantContext, supplier_id: uuid.UUID | None) -> None:
    if supplier_id is not None:
        get_owned(db, Supplier, supplier_id, ctx.restaurant_id, "Supplier")


def _check_unique(
    db: Session, ctx: RestaurantContext, name: str | None, sku: str | None, exclude: uuid.UUID | None = None
) -> None:
    conditions = []
    if name:
        conditions.append(func.lower(Ingredient.name) == name.lower())
    if sku:
        conditions.append(Ingredient.sku == sku)
    if not conditions:
        return
    stmt = scoped(Ingredient, ctx.restaurant_id).where(or_(*conditions))
    if exclude:
        stmt = stmt.where(Ingredient.id != exclude)
    if db.scalar(stmt) is not None:
        raise Conflict("An ingredient with this name or SKU already exists.")


def create_ingredient(db: Session, ctx: RestaurantContext, data: IngredientCreate) -> IngredientOut:
    _check_unique(db, ctx, data.name, data.sku)
    _check_supplier(db, ctx, data.default_supplier_id)
    ingredient = Ingredient(
        restaurant_id=ctx.restaurant_id,
        name=data.name,
        sku=data.sku,
        base_unit=data.base_unit,
        reorder_level=data.reorder_level,
        safety_stock=data.safety_stock,
        default_supplier_id=data.default_supplier_id,
    )
    db.add(ingredient)
    db.flush()
    for unit in data.units:
        _add_unit(db, ctx, ingredient, unit)
    if data.opening_stock:
        apply_stock_changes(
            db,
            ctx.restaurant,
            [
                StockChange(
                    ingredient_id=ingredient.id,
                    quantity=data.opening_stock,
                    movement_type=MovementType.OPENING,
                    reason="Opening stock",
                    unit_cost_minor=data.opening_unit_cost_minor,
                    input_quantity=data.opening_stock,
                    input_unit=data.base_unit.value,
                )
            ],
            actor_user_id=ctx.user_id,
        )
    record_audit(
        db,
        action="ingredient.created",
        actor_user_id=ctx.user_id,
        restaurant_id=ctx.restaurant_id,
        entity_type="ingredient",
        entity_id=ingredient.id,
        ip_address=ctx.ip,
    )
    realtime.emit(db, ctx.restaurant_id, "stock.changed", actor_user_id=ctx.user_id)
    db.commit()
    db.refresh(ingredient)
    return to_out(ingredient)


def update_ingredient(
    db: Session, ctx: RestaurantContext, ingredient_id: uuid.UUID, data: IngredientUpdate
) -> IngredientOut:
    ingredient = get_ingredient(db, ctx, ingredient_id)
    changes = data.model_dump(exclude_unset=True, exclude={"clear_default_supplier"})
    _check_unique(db, ctx, changes.get("name"), changes.get("sku"), exclude=ingredient.id)
    if "default_supplier_id" in changes:
        _check_supplier(db, ctx, changes["default_supplier_id"])
    for field, value in changes.items():
        if value is not None or field == "sku":
            setattr(ingredient, field, value)
    if data.clear_default_supplier:
        ingredient.default_supplier_id = None
    realtime.emit(db, ctx.restaurant_id, "stock.changed", actor_user_id=ctx.user_id)
    db.commit()
    db.refresh(ingredient)
    return to_out(ingredient, supplier_names(db, ctx.restaurant_id))


def _add_unit(db: Session, ctx: RestaurantContext, ingredient: Ingredient, data: IngredientUnitIn) -> None:
    name = normalise_unit(data.unit_name)
    if is_standard_unit(name):
        raise ValidationFailed(f"'{name}' is a standard unit and cannot be redefined.")
    if any(normalise_unit(u.unit_name) == name for u in ingredient.units):
        raise Conflict(f"The unit '{name}' is already defined for this ingredient.")
    unit = IngredientUnit(
        restaurant_id=ctx.restaurant_id, ingredient_id=ingredient.id, unit_name=name, factor_to_base=data.factor_to_base
    )
    ingredient.units.append(unit)
    db.flush()


def add_unit(db: Session, ctx: RestaurantContext, ingredient_id: uuid.UUID, data: IngredientUnitIn) -> IngredientOut:
    ingredient = get_ingredient(db, ctx, ingredient_id)
    _add_unit(db, ctx, ingredient, data)
    realtime.emit(db, ctx.restaurant_id, "stock.changed", actor_user_id=ctx.user_id)
    db.commit()
    return to_out(ingredient)


def remove_unit(db: Session, ctx: RestaurantContext, ingredient_id: uuid.UUID, unit_id: uuid.UUID) -> IngredientOut:
    ingredient = get_ingredient(db, ctx, ingredient_id)
    unit = next((u for u in ingredient.units if u.id == unit_id), None)
    if unit is None:
        raise NotFound("Unit not found.")
    ingredient.units.remove(unit)
    realtime.emit(db, ctx.restaurant_id, "stock.changed", actor_user_id=ctx.user_id)
    db.commit()
    return to_out(ingredient)


# --------------------------------------------------------------------------- manual movements


def record_manual_movement(db: Session, ctx: RestaurantContext, data: MovementCreate) -> MovementOut:
    if data.movement_type not in MANUAL_MOVEMENT_TYPES:
        raise ValidationFailed(
            "Only RECEIPT, ISSUE, ADJUSTMENT and WASTE movements can be recorded manually. "
            "Sales and purchase receipts are recorded automatically."
        )
    if data.quantity == 0:
        raise ValidationFailed("Quantity must not be zero.")
    if data.movement_type != MovementType.ADJUSTMENT and data.quantity < 0:
        raise ValidationFailed("Quantity must be positive; the movement type determines the direction.")
    ingredient = get_ingredient(db, ctx, data.ingredient_id)
    base_qty = convert(ingredient, abs(data.quantity), data.unit)
    if base_qty == 0:
        raise ValidationFailed("Quantity is too small for the ingredient's unit precision.")
    signed = base_qty if data.movement_type == MovementType.RECEIPT else -base_qty
    if data.movement_type == MovementType.ADJUSTMENT:
        signed = base_qty if data.quantity > 0 else -base_qty
    unit_cost = None
    if data.unit_cost_minor is not None:
        if data.movement_type != MovementType.RECEIPT:
            raise ValidationFailed("A unit cost can only be recorded for stock receipts.")
        # Convert the cost per entered unit into cost per base unit.
        per_entered = convert(ingredient, Decimal(1), data.unit)
        unit_cost = (data.unit_cost_minor / per_entered).quantize(COST_QUANTUM, ROUND_HALF_UP)
    [movement] = apply_stock_changes(
        db,
        ctx.restaurant,
        [
            StockChange(
                ingredient_id=ingredient.id,
                quantity=signed,
                movement_type=data.movement_type,
                reason=data.reason,
                unit_cost_minor=unit_cost,
                input_quantity=data.quantity,
                input_unit=data.unit or ingredient.base_unit.value,
            )
        ],
        actor_user_id=ctx.user_id,
    )
    record_audit(
        db,
        action=f"inventory.{data.movement_type.value.lower()}",
        actor_user_id=ctx.user_id,
        restaurant_id=ctx.restaurant_id,
        entity_type="ingredient",
        entity_id=ingredient.id,
        details={"quantity": str(signed), "reason": data.reason},
        ip_address=ctx.ip,
    )
    realtime.emit(db, ctx.restaurant_id, "stock.changed", actor_user_id=ctx.user_id)
    db.commit()
    return movement_out(movement, ingredient)


def record_stock_count(db: Session, ctx: RestaurantContext, data: StockCountCreate) -> MovementOut | None:
    ingredient = get_ingredient(db, ctx, data.ingredient_id)
    counted = convert(ingredient, data.counted_quantity, data.unit)
    lock_ingredients(db, ctx.restaurant_id, [ingredient.id])
    delta = counted - ingredient.current_stock
    if delta == 0:
        return None
    [movement] = apply_stock_changes(
        db,
        ctx.restaurant,
        [
            StockChange(
                ingredient_id=ingredient.id,
                quantity=delta,
                movement_type=MovementType.ADJUSTMENT,
                reason=f"{data.reason} (counted {counted} {ingredient.base_unit.value})",
                input_quantity=data.counted_quantity,
                input_unit=data.unit or ingredient.base_unit.value,
            )
        ],
        actor_user_id=ctx.user_id,
        allow_negative=True,
    )
    record_audit(
        db,
        action="inventory.stock_count",
        actor_user_id=ctx.user_id,
        restaurant_id=ctx.restaurant_id,
        entity_type="ingredient",
        entity_id=ingredient.id,
        details={"counted": str(counted), "delta": str(delta)},
        ip_address=ctx.ip,
    )
    realtime.emit(db, ctx.restaurant_id, "stock.changed", actor_user_id=ctx.user_id)
    db.commit()
    return movement_out(movement, ingredient)


def movement_out(
    movement: InventoryMovement, ingredient: Ingredient | None = None, actor_name: str | None = None
) -> MovementOut:
    out = MovementOut.model_validate(movement)
    ingredient = ingredient or movement.ingredient
    out.ingredient_name = ingredient.name
    out.base_unit = ingredient.base_unit.value
    out.actor_name = actor_name
    return out


def list_movements(
    db: Session,
    ctx: RestaurantContext,
    params: PageParams,
    *,
    ingredient_id: uuid.UUID | None = None,
    movement_type: MovementType | None = None,
    order_id: uuid.UUID | None = None,
    purchase_order_id: uuid.UUID | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> tuple[list[MovementOut], int]:
    stmt = (
        scoped(InventoryMovement, ctx.restaurant_id)
        .options(selectinload(InventoryMovement.ingredient))
        .order_by(InventoryMovement.created_at.desc(), InventoryMovement.id)
    )
    if ingredient_id:
        stmt = stmt.where(InventoryMovement.ingredient_id == ingredient_id)
    if movement_type:
        stmt = stmt.where(InventoryMovement.movement_type == movement_type)
    if order_id:
        stmt = stmt.where(InventoryMovement.order_id == order_id)
    if purchase_order_id:
        stmt = stmt.where(InventoryMovement.purchase_order_id == purchase_order_id)
    if start:
        stmt = stmt.where(InventoryMovement.created_at >= start)
    if end:
        stmt = stmt.where(InventoryMovement.created_at < end)
    items, total = paginate(db, stmt, params)
    actors = {m.actor_user_id for m in items if m.actor_user_id}
    names = dict(db.execute(select(User.id, User.full_name).where(User.id.in_(actors))).all()) if actors else {}
    return [movement_out(m, actor_name=names.get(m.actor_user_id)) for m in items], total


def summary(db: Session, ctx: RestaurantContext) -> InventorySummary:
    ingredients = db.scalars(scoped(Ingredient, ctx.restaurant_id).where(Ingredient.is_active.is_(True))).all()
    valued = [i for i in ingredients if i.average_cost_minor > 0]
    return InventorySummary(
        ingredient_count=len(ingredients),
        low_stock_count=sum(1 for i in ingredients if is_low_stock(i)),
        out_of_stock_count=sum(1 for i in ingredients if i.current_stock <= 0),
        total_value_minor=sum(stock_value_minor(i) for i in valued),
        valued_ingredient_count=len(valued),
        unvalued_ingredient_count=len(ingredients) - len(valued),
    )
