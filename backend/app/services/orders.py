"""Order lifecycle: pricing, state machine, stock deduction, payments, refunds.

State machine
-------------
DRAFT -> CONFIRMED -> PREPARING -> READY -> COMPLETED
DRAFT / CONFIRMED / PREPARING / READY -> CANCELLED (rules below)

* Stock is deducted when an order is CONFIRMED, using the active recipe version
  of each line (recorded on the line). Confirmation is idempotent.
* Editing a confirmed order reconciles stock against what this order has
  already consumed (sum of its movements), so nothing is deducted twice.
* Cancelling restores stock only if preparation had not started, unless the
  manager explicitly chooses otherwise.
* Every mutation locks the order row (``SELECT ... FOR UPDATE``) and commits
  order, stock, payment and loyalty changes in one transaction.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.api.deps import RestaurantContext
from app.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.core.permissions import Permission
from app.db.base import ZERO
from app.models import (
    Customer,
    DiningTable,
    Discount,
    InventoryMovement,
    ModifierGroup,
    ModifierOption,
    Order,
    OrderItem,
    OrderItemModifier,
    Payment,
    PaymentMethod,
    Product,
    Refund,
    User,
)
from app.models.enums import (
    DiscountKind,
    MovementType,
    OrderStatus,
    OrderType,
    PaymentMethodKind,
    PaymentStatus,
    SelectionType,
    TableStatus,
)
from app.repositories.tenant import get_owned, scoped
from app.schemas.common import PageParams, paginate
from app.schemas.orders import (
    CancelRequest,
    DiscountIn,
    OrderCreate,
    OrderDraftIn,
    OrderItemIn,
    OrderListItem,
    OrderOut,
    OrderQuote,
    OrderUpdate,
    PaymentCreate,
    PaymentOut,
    QuoteLine,
    RefundCreate,
    RefundOut,
)
from app.services import loyalty, realtime
from app.services.audit import record_audit
from app.services.inventory import StockChange, apply_stock_changes
from app.services.pricing import DiscountSpec, PricingResult, PricingSettings, calculate, line_total, percent_of
from app.services.recipes import active_recipes, effective_quantity, recipes_by_id
from app.services.restaurants import next_counter
from app.services.tables import display_number
from app.services.units import quantize

TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.DRAFT: {OrderStatus.CONFIRMED, OrderStatus.CANCELLED},
    OrderStatus.CONFIRMED: {OrderStatus.PREPARING, OrderStatus.CANCELLED},
    OrderStatus.PREPARING: {OrderStatus.READY, OrderStatus.CANCELLED},
    OrderStatus.READY: {OrderStatus.COMPLETED, OrderStatus.CANCELLED},
    OrderStatus.COMPLETED: set(),
    OrderStatus.CANCELLED: set(),
}
EDITABLE_STATUSES = {OrderStatus.DRAFT, OrderStatus.CONFIRMED, OrderStatus.PREPARING}
PAYABLE_STATUSES = {OrderStatus.CONFIRMED, OrderStatus.PREPARING, OrderStatus.READY, OrderStatus.COMPLETED}
ACTIVE_STATUSES = {OrderStatus.DRAFT, OrderStatus.CONFIRMED, OrderStatus.PREPARING, OrderStatus.READY}
SIMULATED_NOTE = "Recorded by staff (simulated). No payment provider confirmed this transfer."


def now() -> datetime:
    return datetime.now(UTC)


# --------------------------------------------------------------------------- line building


@dataclass
class LineSpec:
    product: Product
    quantity: int
    notes: str | None
    options: list[tuple[ModifierGroup, ModifierOption]] = field(default_factory=list)

    @property
    def unit_price_minor(self) -> int:
        return self.product.price_minor + sum(o.price_delta_minor for _, o in self.options)


def _build_lines(
    db: Session, ctx: RestaurantContext, items: list[OrderItemIn], already_on_order: set[uuid.UUID] | None = None
) -> list[LineSpec]:
    product_ids = {i.product_id for i in items}
    products = {
        p.id: p
        for p in db.scalars(
            scoped(Product, ctx.restaurant_id)
            .where(Product.id.in_(product_ids))
            .options(selectinload(Product.modifier_groups).selectinload(ModifierGroup.options))
        ).all()
    }
    already_on_order = already_on_order or set()
    lines = []
    for item in items:
        product = products.get(item.product_id)
        if product is None:
            raise ValidationFailed(
                "A product in the order does not exist.",
                code="product_not_found",
                details={"product_id": str(item.product_id)},
            )
        sellable = product.is_active and product.is_available
        if not sellable and product.id not in already_on_order:
            raise ValidationFailed(f"{product.name} is currently unavailable.", code="product_unavailable")
        lines.append(
            LineSpec(
                product=product,
                quantity=item.quantity,
                notes=item.notes,
                options=_resolve_modifiers(product, item.modifier_option_ids),
            )
        )
    return lines


def _resolve_modifiers(product: Product, option_ids: list[uuid.UUID]) -> list[tuple[ModifierGroup, ModifierOption]]:
    if len(option_ids) != len(set(option_ids)):
        raise ValidationFailed(f"Duplicate modifier selected for {product.name}.")
    available = {o.id: (g, o) for g in product.modifier_groups if g.is_active for o in g.options if o.is_active}
    chosen: dict[uuid.UUID, list[tuple[ModifierGroup, ModifierOption]]] = defaultdict(list)
    for option_id in option_ids:
        if option_id not in available:
            raise ValidationFailed(
                f"A selected modifier is not available for {product.name}.",
                code="invalid_modifier",
                details={"option_id": str(option_id)},
            )
        group, option = available[option_id]
        chosen[group.id].append((group, option))
    result: list[tuple[ModifierGroup, ModifierOption]] = []
    for group in product.modifier_groups:
        if not group.is_active:
            continue
        selected = chosen.get(group.id, [])
        if not selected and group.min_select > 0:
            defaults = [(group, o) for o in group.options if o.is_active and o.is_default]
            if len(defaults) >= group.min_select:
                selected = defaults[: group.max_select or len(defaults)]
        max_allowed = 1 if group.selection_type == SelectionType.SINGLE else group.max_select
        if len(selected) < group.min_select:
            raise ValidationFailed(
                f"Choose at least {group.min_select} option(s) for '{group.name}' on {product.name}.",
                code="modifier_required",
            )
        if max_allowed is not None and len(selected) > max_allowed:
            raise ValidationFailed(
                f"Choose at most {max_allowed} option(s) for '{group.name}' on {product.name}.", code="modifier_limit"
            )
        result.extend(selected)
    return result


# --------------------------------------------------------------------------- discounts & pricing


@dataclass
class ResolvedDiscount:
    spec: DiscountSpec
    discount_id: uuid.UUID | None
    name: str
    reason: str | None


def _resolve_discount(
    db: Session, ctx: RestaurantContext, discount_in: DiscountIn | None, subtotal_minor: int
) -> ResolvedDiscount | None:
    if discount_in is None:
        return None
    ctx.require(Permission.DISCOUNTS_APPLY)
    override = ctx.can(Permission.DISCOUNTS_OVERRIDE)
    if discount_in.discount_id is not None:
        discount = get_owned(db, Discount, discount_in.discount_id, ctx.restaurant_id, "Discount")
        if not discount.is_active:
            raise ValidationFailed("This discount is no longer active.", code="discount_inactive")
        if discount.requires_manager and not override:
            raise Forbidden("This discount requires a manager.", code="discount_requires_manager")
        resolved = ResolvedDiscount(
            DiscountSpec(discount.kind, discount.value), discount.id, discount.name, discount_in.reason
        )
    else:
        if not override:
            raise Forbidden("Only managers can apply custom discounts.", code="discount_requires_manager")
        assert discount_in.kind is not None and discount_in.value is not None
        label = f"{discount_in.value / 100:g}% off" if discount_in.kind == DiscountKind.PERCENT else "Custom discount"
        resolved = ResolvedDiscount(DiscountSpec(discount_in.kind, discount_in.value), None, label, discount_in.reason)
    if not override:
        limit = ctx.restaurant.max_cashier_discount_bps
        spec = resolved.spec
        too_big = (
            spec.value > limit if spec.kind == DiscountKind.PERCENT else spec.value > percent_of(subtotal_minor, limit)
        )
        if too_big:
            raise Forbidden(f"Discounts above {limit / 100:g}% need a manager.", code="discount_limit_exceeded")
    return resolved


def _settings_for(ctx: RestaurantContext, order_type: OrderType, order: Order | None = None) -> PricingSettings:
    restaurant = ctx.restaurant
    if order is not None and order.status != OrderStatus.DRAFT:
        # Confirmed orders keep the pricing rules they were confirmed with.
        return PricingSettings(
            order.tax_rate_bps, order.prices_include_tax, order.service_charge_bps, restaurant.service_charge_taxable
        )
    service = restaurant.service_charge_bps
    if restaurant.service_charge_dine_in_only and order_type != OrderType.DINE_IN:
        service = 0
    return PricingSettings(
        restaurant.tax_rate_bps, restaurant.prices_include_tax, service, restaurant.service_charge_taxable
    )


def _loyalty_discount(ctx: RestaurantContext, customer: Customer | None, points: int, after_discount_minor: int) -> int:
    if not points:
        return 0
    restaurant = ctx.restaurant
    if not restaurant.loyalty_enabled or restaurant.loyalty_point_value_minor <= 0:
        raise ValidationFailed("Loyalty redemption is not enabled for this restaurant.")
    if customer is None:
        raise ValidationFailed("Redeeming loyalty points requires a customer.")
    if points > customer.loyalty_balance:
        raise ValidationFailed(f"The customer has only {customer.loyalty_balance} points.", code="insufficient_points")
    value = points * restaurant.loyalty_point_value_minor
    if value > after_discount_minor:
        raise ValidationFailed(
            "Redeemed points cannot exceed the order value.",
            code="redemption_too_large",
            details={"max_points": after_discount_minor // restaurant.loyalty_point_value_minor},
        )
    return value


def _price(
    ctx: RestaurantContext,
    db: Session,
    order_type: OrderType,
    lines: list[LineSpec],
    discount_in: DiscountIn | None,
    customer: Customer | None,
    points: int,
    order: Order | None = None,
) -> tuple[PricingResult, ResolvedDiscount | None]:
    totals = [line_total(line.unit_price_minor, line.quantity) for line in lines]
    if any(line.unit_price_minor < 0 for line in lines):
        raise ValidationFailed("Modifier price adjustments cannot make an item negative.")
    subtotal = sum(totals)
    discount = _resolve_discount(db, ctx, discount_in, subtotal)
    settings = _settings_for(ctx, order_type, order)
    pre = calculate(totals, settings, discount.spec if discount else None)
    loyalty_value = _loyalty_discount(ctx, customer, points, pre.subtotal_minor - pre.discount_minor)
    result = calculate(totals, settings, discount.spec if discount else None, loyalty_value)
    return result, discount


def _customer(db: Session, ctx: RestaurantContext, customer_id: uuid.UUID | None) -> Customer | None:
    if customer_id is None:
        return None
    return get_owned(db, Customer, customer_id, ctx.restaurant_id, "Customer")


def quote(db: Session, ctx: RestaurantContext, data: OrderDraftIn) -> OrderQuote:
    lines = _build_lines(db, ctx, data.items)
    customer = _customer(db, ctx, data.customer_id)
    result, discount = _price(ctx, db, data.order_type, lines, data.discount, customer, data.loyalty_points_to_redeem)
    point_value = ctx.restaurant.loyalty_point_value_minor
    max_points = 0
    if customer and ctx.restaurant.loyalty_enabled and point_value > 0:
        max_points = min(customer.loyalty_balance, (result.subtotal_minor - result.discount_minor) // point_value)
    return OrderQuote(
        lines=[
            QuoteLine(
                product_id=line.product.id,
                product_name=line.product.name,
                unit_price_minor=line.unit_price_minor,
                quantity=line.quantity,
                line_total_minor=line.unit_price_minor * line.quantity,
                modifiers=[o.name for _, o in line.options],
            )
            for line in lines
        ],
        subtotal_minor=result.subtotal_minor,
        discount_minor=result.discount_minor,
        loyalty_discount_minor=result.loyalty_discount_minor,
        service_charge_minor=result.service_charge_minor,
        tax_minor=result.tax_minor,
        total_minor=result.total_minor,
        prices_include_tax=result.prices_include_tax,
        tax_rate_bps=ctx.restaurant.tax_rate_bps,
        service_charge_bps=_settings_for(ctx, data.order_type).service_charge_bps,
        discount_name=discount.name if discount else None,
        max_redeemable_points=max_points,
    )


# --------------------------------------------------------------------------- loading & output


def _order_options():
    return (
        selectinload(Order.items).selectinload(OrderItem.modifiers),
        selectinload(Order.payments),
        selectinload(Order.refunds),
    )


def load_order(db: Session, ctx: RestaurantContext, order_id: uuid.UUID, *, for_update: bool = False) -> Order:
    if for_update:
        # Lock the order row first, then load its children.
        get_owned(db, Order, order_id, ctx.restaurant_id, "Order", for_update=True)
    stmt = scoped(Order, ctx.restaurant_id).where(Order.id == order_id).options(*_order_options())
    order = db.scalar(stmt.execution_options(populate_existing=True))
    if order is None:
        raise NotFound("Order not found.")
    return order


def payment_out(payment: Payment) -> PaymentOut:
    out = PaymentOut.model_validate(payment)
    out.verification_note = SIMULATED_NOTE if payment.is_simulated else "Confirmed by payment provider."
    return out


def allowed_transitions(ctx: RestaurantContext, order: Order) -> list[OrderStatus]:
    allowed = []
    for target in TRANSITIONS[order.status]:
        try:
            _check_transition_permission(ctx, order, target)
            allowed.append(target)
        except Forbidden:
            continue
    order_rank = list(OrderStatus)
    return sorted(allowed, key=order_rank.index)


def order_out(db: Session, ctx: RestaurantContext, order: Order) -> OrderOut:
    out = OrderOut.model_validate(order)
    out.display_number = display_number(ctx.restaurant.order_number_prefix, order.order_number)
    out.balance_due_minor = max(order.total_minor - order.amount_paid_minor, 0)
    if order.table_id:
        out.table_name = db.scalar(select(DiningTable.name).where(DiningTable.id == order.table_id))
    if order.customer_id:
        out.customer_name = db.scalar(select(Customer.name).where(Customer.id == order.customer_id))
    if order.created_by:
        out.created_by_name = db.scalar(select(User.full_name).where(User.id == order.created_by))
    out.payments = [payment_out(p) for p in order.payments]
    out.refunds = [RefundOut.model_validate(r) for r in order.refunds]
    out.allowed_transitions = allowed_transitions(ctx, order)
    return out


def get_order_out(db: Session, ctx: RestaurantContext, order_id: uuid.UUID) -> OrderOut:
    return order_out(db, ctx, load_order(db, ctx, order_id))


# --------------------------------------------------------------------------- stock reconciliation


def _requirements(db: Session, ctx: RestaurantContext, order: Order) -> dict[uuid.UUID, Decimal]:
    """Ingredient quantities (base units) this order needs, by ingredient id.

    Lines keep the recipe version they were first deducted with; new lines use
    the product's active recipe.
    """
    pinned = recipes_by_id(db, {i.recipe_id for i in order.items if i.recipe_id})
    current = active_recipes(db, ctx.restaurant_id, {i.product_id for i in order.items if not i.recipe_id})
    needs: dict[uuid.UUID, Decimal] = defaultdict(lambda: ZERO)
    for item in order.items:
        recipe = pinned.get(item.recipe_id) if item.recipe_id else current.get(item.product_id)
        if recipe is not None:
            item.recipe_id = recipe.id
            for recipe_item in recipe.items:
                needs[recipe_item.ingredient_id] += effective_quantity(recipe_item) * item.quantity
        for modifier in item.modifiers:
            if modifier.ingredient_id and modifier.ingredient_quantity:
                needs[modifier.ingredient_id] += modifier.ingredient_quantity * item.quantity
    return {k: quantize(v) for k, v in needs.items() if v != 0}


def _consumed(db: Session, order_id: uuid.UUID) -> dict[uuid.UUID, Decimal]:
    rows = db.execute(
        select(InventoryMovement.ingredient_id, func.sum(InventoryMovement.quantity))
        .where(InventoryMovement.order_id == order_id)
        .group_by(InventoryMovement.ingredient_id)
    ).all()
    # Consumption movements are negative; "consumed" is the positive net amount.
    return {ingredient_id: -total for ingredient_id, total in rows if total != 0}


def reconcile_stock(
    db: Session, ctx: RestaurantContext, order: Order, reason: str, *, release_all: bool = False
) -> None:
    required = {} if release_all else _requirements(db, ctx, order)
    consumed = _consumed(db, order.id)
    changes = []
    for ingredient_id in sorted(set(required) | set(consumed)):
        delta = required.get(ingredient_id, ZERO) - consumed.get(ingredient_id, ZERO)
        if delta > 0:
            changes.append(StockChange(ingredient_id, -delta, MovementType.SALE, reason))
        elif delta < 0:
            changes.append(StockChange(ingredient_id, -delta, MovementType.SALE_REVERSAL, reason))
    apply_stock_changes(db, ctx.restaurant, changes, actor_user_id=ctx.user_id, order_id=order.id)


# --------------------------------------------------------------------------- create / update


def _apply_lines(order: Order, ctx: RestaurantContext, lines: list[LineSpec]) -> None:
    previous_recipes = {i.product_id: i.recipe_id for i in order.items if i.recipe_id}
    order.items.clear()
    for position, line in enumerate(lines):
        product = line.product
        item = OrderItem(
            restaurant_id=ctx.restaurant_id,
            position=position,
            product_id=product.id,
            product_name=product.name,
            product_sku=product.sku,
            category_id=product.category_id,
            category_name=product.category.name if product.category else None,
            base_price_minor=product.price_minor,
            unit_price_minor=line.unit_price_minor,
            quantity=line.quantity,
            line_total_minor=line.unit_price_minor * line.quantity,
            notes=line.notes,
            # Lines for a product already deducted keep their recipe version.
            recipe_id=previous_recipes.get(product.id),
        )
        for group, option in line.options:
            item.modifiers.append(
                OrderItemModifier(
                    modifier_option_id=option.id,
                    group_name=group.name,
                    option_name=option.name,
                    price_delta_minor=option.price_delta_minor,
                    ingredient_id=option.ingredient_id,
                    ingredient_quantity=option.ingredient_quantity,
                )
            )
        order.items.append(item)


def _apply_pricing(
    order: Order,
    result: PricingResult,
    discount: ResolvedDiscount | None,
    points: int,
    ctx: RestaurantContext,
    settings: PricingSettings,
) -> None:
    order.subtotal_minor = result.subtotal_minor
    order.discount_minor = result.discount_minor
    order.loyalty_discount_minor = result.loyalty_discount_minor
    order.service_charge_minor = result.service_charge_minor
    order.tax_minor = result.tax_minor
    order.total_minor = result.total_minor
    order.loyalty_points_redeemed = points if result.loyalty_discount_minor else 0
    order.tax_rate_bps = settings.tax_rate_bps
    order.service_charge_bps = settings.service_charge_bps
    order.prices_include_tax = settings.prices_include_tax
    if discount is None:
        order.discount_id = order.discount_name = order.discount_kind = order.discount_value = None
        order.discount_reason = order.discount_applied_by = None
    else:
        order.discount_id = discount.discount_id
        order.discount_name = discount.name
        order.discount_kind = discount.spec.kind
        order.discount_value = discount.spec.value
        order.discount_reason = discount.reason
        order.discount_applied_by = ctx.user_id


def _lock_table_for_order(db: Session, ctx: RestaurantContext, table_id: uuid.UUID) -> DiningTable:
    table = get_owned(db, DiningTable, table_id, ctx.restaurant_id, "Table", for_update=True)
    if not table.is_active:
        raise ValidationFailed("This table is inactive.")
    if table.status == TableStatus.CLEANING:
        raise Conflict("This table is being cleaned. Mark it available first.", code="table_not_ready")
    active = db.scalar(select(Order).where(Order.table_id == table.id, Order.status.in_(ACTIVE_STATUSES)))
    if active is not None:
        raise Conflict(
            "This table already has an active order. Add items to that order instead.",
            code="table_has_active_order",
            details={
                "order_id": str(active.id),
                "display_number": display_number(ctx.restaurant.order_number_prefix, active.order_number),
            },
        )
    return table


def create_order(
    db: Session, ctx: RestaurantContext, data: OrderCreate, idempotency_key: str | None
) -> tuple[OrderOut, bool]:
    """Create an order. Returns (order, replayed) where replayed is True when an
    earlier request with the same idempotency key already created it."""
    if idempotency_key:
        existing = db.scalar(scoped(Order, ctx.restaurant_id).where(Order.idempotency_key == idempotency_key))
        if existing is not None:
            return get_order_out(db, ctx, existing.id), True
    lines = _build_lines(db, ctx, data.items)
    customer = _customer(db, ctx, data.customer_id)
    result, discount = _price(ctx, db, data.order_type, lines, data.discount, customer, data.loyalty_points_to_redeem)
    table = _lock_table_for_order(db, ctx, data.table_id) if data.table_id else None
    order = Order(
        restaurant_id=ctx.restaurant_id,
        order_number=next_counter(db, ctx.restaurant_id, "order_number"),
        order_type=data.order_type,
        status=OrderStatus.DRAFT,
        payment_status=PaymentStatus.UNPAID,
        table_id=table.id if table else None,
        customer_id=customer.id if customer else None,
        notes=data.notes,
        idempotency_key=idempotency_key,
        created_by=ctx.user_id,
    )
    _apply_lines(order, ctx, lines)
    _apply_pricing(order, result, discount, data.loyalty_points_to_redeem, ctx, _settings_for(ctx, data.order_type))
    db.add(order)
    db.flush()
    if table is not None:
        table.status = TableStatus.OCCUPIED
        table.current_order_id = order.id
    if discount is not None:
        _audit_discount(db, ctx, order, discount)
    if data.confirm:
        _confirm(db, ctx, order)
    _order_event(db, ctx, order, "order.confirmed" if data.confirm else "order.created")
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if idempotency_key:
            existing = db.scalar(scoped(Order, ctx.restaurant_id).where(Order.idempotency_key == idempotency_key))
            if existing is not None:
                return get_order_out(db, ctx, existing.id), True
        raise
    return get_order_out(db, ctx, order.id), False


def _audit_discount(db: Session, ctx: RestaurantContext, order: Order, discount: ResolvedDiscount) -> None:
    record_audit(
        db,
        action="order.discount_applied",
        actor_user_id=ctx.user_id,
        restaurant_id=ctx.restaurant_id,
        entity_type="order",
        entity_id=order.id,
        details={
            "discount": discount.name,
            "kind": discount.spec.kind.value,
            "value": discount.spec.value,
            "amount_minor": order.discount_minor,
            "reason": discount.reason,
        },
        ip_address=ctx.ip,
    )


def update_order(db: Session, ctx: RestaurantContext, order_id: uuid.UUID, data: OrderUpdate) -> OrderOut:
    order = load_order(db, ctx, order_id, for_update=True)
    if order.status not in EDITABLE_STATUSES:
        raise Conflict(
            f"Orders cannot be changed once they are {order.status.value.lower()}.", code="order_not_editable"
        )
    if order.payment_status != PaymentStatus.UNPAID:
        raise Conflict("Orders cannot be changed after payment has started.", code="order_has_payments")
    confirmed = order.status != OrderStatus.DRAFT
    fields = data.model_fields_set
    if confirmed and ({"loyalty_points_to_redeem", "customer_id"} & fields or data.clear_customer):
        raise Conflict(
            "The customer and loyalty redemption are fixed once an order is confirmed.", code="order_customer_locked"
        )

    if data.items is not None:
        lines = _build_lines(db, ctx, data.items, already_on_order={i.product_id for i in order.items})
    else:
        lines = _lines_from_order(db, ctx, order)
    if data.clear_customer:
        customer = None
    else:
        customer = _customer(db, ctx, data.customer_id if "customer_id" in fields else order.customer_id)
    totals = [line_total(line.unit_price_minor, line.quantity) for line in lines]
    settings = _settings_for(ctx, order.order_type, order)

    if data.clear_discount:
        discount = None
    elif data.discount is not None:
        discount = _resolve_discount(db, ctx, data.discount, sum(totals))
    elif order.discount_kind is not None:
        # Keep the discount that was already authorised for this order.
        discount = ResolvedDiscount(
            DiscountSpec(order.discount_kind, order.discount_value or 0),
            order.discount_id,
            order.discount_name or "Discount",
            order.discount_reason,
        )
    else:
        discount = None
    pre = calculate(totals, settings, discount.spec if discount else None)
    after_discount = pre.subtotal_minor - pre.discount_minor
    if confirmed:
        points = order.loyalty_points_redeemed
        loyalty_value = order.loyalty_discount_minor
        if loyalty_value > after_discount:
            raise Conflict("The order value would fall below the redeemed loyalty points.", code="redemption_too_large")
    else:
        points = (
            data.loyalty_points_to_redeem
            if data.loyalty_points_to_redeem is not None
            else order.loyalty_points_redeemed
        )
        if customer is None:
            points = 0
        loyalty_value = _loyalty_discount(ctx, customer, points, after_discount)
    result = calculate(totals, settings, discount.spec if discount else None, loyalty_value)

    if data.items is not None:
        _apply_lines(order, ctx, lines)
    if "notes" in fields:
        order.notes = data.notes
    order.customer_id = customer.id if customer else None
    _apply_pricing(order, result, discount, points, ctx, settings)
    db.flush()
    if data.discount is not None and discount is not None:
        _audit_discount(db, ctx, order, discount)
    if confirmed and data.items is not None:
        reconcile_stock(db, ctx, order, f"Order {_num(ctx, order)} modified")
    record_audit(
        db,
        action="order.updated",
        actor_user_id=ctx.user_id,
        restaurant_id=ctx.restaurant_id,
        entity_type="order",
        entity_id=order.id,
        details={"fields": sorted(fields)},
        ip_address=ctx.ip,
    )
    _order_event(db, ctx, order, "order.updated")
    db.commit()
    return get_order_out(db, ctx, order.id)


def _lines_from_order(db: Session, ctx: RestaurantContext, order: Order) -> list[LineSpec]:
    items = [
        OrderItemIn(
            product_id=i.product_id,
            quantity=i.quantity,
            notes=i.notes,
            modifier_option_ids=[m.modifier_option_id for m in i.modifiers if m.modifier_option_id],
        )
        for i in order.items
    ]
    return _build_lines(db, ctx, items, already_on_order={i.product_id for i in order.items})


def _num(ctx: RestaurantContext, order: Order) -> str:
    return "#" + display_number(ctx.restaurant.order_number_prefix, order.order_number)


def _order_event(db: Session, ctx: RestaurantContext, order: Order, event_type: str) -> None:
    """Announce an order change on the live-update feed (same transaction as the change)."""
    realtime.emit(
        db,
        ctx.restaurant_id,
        event_type,
        entity_id=order.id,
        actor_user_id=ctx.user_id,
        data={
            "display_number": display_number(ctx.restaurant.order_number_prefix, order.order_number),
            "status": order.status.value,
            "payment_status": order.payment_status.value,
            "order_type": order.order_type.value,
            "table_id": str(order.table_id) if order.table_id else None,
        },
    )


# --------------------------------------------------------------------------- transitions


def _check_transition_permission(ctx: RestaurantContext, order: Order, target: OrderStatus) -> None:
    if target == OrderStatus.CONFIRMED:
        ctx.require(Permission.ORDERS_CREATE)
    elif target in (OrderStatus.PREPARING, OrderStatus.READY):
        ctx.require(Permission.KITCHEN_UPDATE)
    elif target == OrderStatus.COMPLETED:
        if not (ctx.can(Permission.KITCHEN_UPDATE) or ctx.can(Permission.ORDERS_COMPLETE)):
            raise Forbidden("You cannot complete orders.")
    elif target == OrderStatus.CANCELLED:
        if order.status == OrderStatus.DRAFT and ctx.can(Permission.ORDERS_CANCEL_DRAFT):
            return
        ctx.require(Permission.ORDERS_CANCEL)


def _confirm(db: Session, ctx: RestaurantContext, order: Order) -> None:
    order.status = OrderStatus.CONFIRMED
    order.confirmed_at = now()
    # Freeze the pricing rules the customer was quoted.
    db.flush()
    reconcile_stock(db, ctx, order, f"Order {_num(ctx, order)} confirmed")
    order.stock_committed = True
    loyalty.redeem_for_order(db, order, ctx.user_id)
    if order.total_minor == 0 and order.payment_status == PaymentStatus.UNPAID:
        order.payment_status = PaymentStatus.PAID
        order.paid_at = now()


def confirm_order(db: Session, ctx: RestaurantContext, order_id: uuid.UUID) -> OrderOut:
    ctx.require(Permission.ORDERS_CREATE)
    order = load_order(db, ctx, order_id, for_update=True)
    if order.status != OrderStatus.DRAFT:
        if order.status == OrderStatus.CANCELLED:
            raise Conflict("Cancelled orders cannot be confirmed.", code="invalid_transition")
        return order_out(db, ctx, order)  # Already confirmed: idempotent no-op.
    _confirm(db, ctx, order)
    _order_event(db, ctx, order, "order.confirmed")
    db.commit()
    return get_order_out(db, ctx, order.id)


def change_status(db: Session, ctx: RestaurantContext, order_id: uuid.UUID, target: OrderStatus) -> OrderOut:
    if target == OrderStatus.CONFIRMED:
        return confirm_order(db, ctx, order_id)
    if target == OrderStatus.CANCELLED:
        raise ValidationFailed("Use the cancel endpoint to cancel an order.")
    order = load_order(db, ctx, order_id, for_update=True)
    if order.status == target:
        return order_out(db, ctx, order)
    if target not in TRANSITIONS[order.status]:
        raise Conflict(
            f"An order cannot move from {order.status.value} to {target.value}.",
            code="invalid_transition",
            details={"from": order.status.value, "allowed": sorted(s.value for s in TRANSITIONS[order.status])},
        )
    _check_transition_permission(ctx, order, target)
    order.status = target
    stamp = {
        OrderStatus.PREPARING: "preparing_at",
        OrderStatus.READY: "ready_at",
        OrderStatus.COMPLETED: "completed_at",
    }[target]
    setattr(order, stamp, now())
    _order_event(db, ctx, order, f"order.{target.value.lower()}")
    db.commit()
    return get_order_out(db, ctx, order.id)


def cancel_order(
    db: Session, ctx: RestaurantContext, order_id: uuid.UUID, data: CancelRequest
) -> tuple[OrderOut, bool]:
    order = load_order(db, ctx, order_id, for_update=True)
    if order.status == OrderStatus.CANCELLED:
        return order_out(db, ctx, order), False
    if OrderStatus.CANCELLED not in TRANSITIONS[order.status]:
        raise Conflict("Completed orders cannot be cancelled. Record a refund instead.", code="invalid_transition")
    _check_transition_permission(ctx, order, OrderStatus.CANCELLED)
    if order.amount_paid_minor - order.amount_refunded_minor > 0:
        raise Conflict("Refund the payments recorded on this order before cancelling it.", code="order_has_payments")
    if data.restock_inventory and not ctx.can(Permission.ORDERS_CANCEL):
        raise Forbidden("Only managers can choose to restock a cancelled order.")
    previous = order.status
    restock = (
        data.restock_inventory
        if data.restock_inventory is not None
        else previous in (OrderStatus.DRAFT, OrderStatus.CONFIRMED)
    )
    restored = False
    if order.stock_committed and restock:
        reconcile_stock(db, ctx, order, f"Order {_num(ctx, order)} cancelled - stock restored", release_all=True)
        restored = True
    loyalty.restore_redeemed(db, order, "Order cancelled", ctx.user_id)
    order.status = OrderStatus.CANCELLED
    order.cancelled_at = now()
    order.cancelled_by = ctx.user_id
    order.cancel_reason = data.reason
    if order.table_id:
        _release_table(db, order)
    record_audit(
        db,
        action="order.cancelled",
        actor_user_id=ctx.user_id,
        restaurant_id=ctx.restaurant_id,
        entity_type="order",
        entity_id=order.id,
        details={"previous_status": previous.value, "reason": data.reason, "stock_restored": restored},
        ip_address=ctx.ip,
    )
    _order_event(db, ctx, order, "order.cancelled")
    db.commit()
    return get_order_out(db, ctx, order.id), restored


def _release_table(db: Session, order: Order) -> None:
    table = db.scalar(select(DiningTable).where(DiningTable.id == order.table_id).with_for_update())
    if table is None or table.current_order_id not in (order.id, None):
        return
    other = db.scalar(
        select(Order).where(Order.table_id == table.id, Order.id != order.id, Order.status.in_(ACTIVE_STATUSES))
    )
    if other is not None:
        table.current_order_id = other.id
        return
    table.current_order_id = None
    if table.status == TableStatus.OCCUPIED:
        table.status = TableStatus.AVAILABLE


# --------------------------------------------------------------------------- payments


def record_payment(
    db: Session, ctx: RestaurantContext, order_id: uuid.UUID, data: PaymentCreate, idempotency_key: str | None
) -> tuple[OrderOut, PaymentOut, bool]:
    if idempotency_key:
        replay = _payment_replay(db, ctx, order_id, data, idempotency_key)
        if replay is not None:
            return replay
    order = load_order(db, ctx, order_id, for_update=True)
    if idempotency_key:
        # A concurrent duplicate may have committed while we waited for the lock.
        replay = _payment_replay(db, ctx, order_id, data, idempotency_key)
        if replay is not None:
            return replay
    if order.status not in PAYABLE_STATUSES:
        raise Conflict(
            "Confirm the order before recording a payment."
            if order.status == OrderStatus.DRAFT
            else "Payments cannot be recorded for cancelled orders.",
            code="order_not_payable",
        )
    if order.payment_status not in (PaymentStatus.UNPAID, PaymentStatus.PARTIALLY_PAID):
        raise Conflict("This order is already fully paid.", code="order_already_paid")
    method = get_owned(db, PaymentMethod, data.payment_method_id, ctx.restaurant_id, "Payment method")
    if not method.is_active:
        raise ValidationFailed("This payment method is not active.")
    outstanding = order.total_minor - order.amount_paid_minor
    if data.amount_minor > outstanding:
        raise ValidationFailed(
            f"The amount exceeds the balance due ({outstanding / 100:.2f}).",
            code="amount_exceeds_balance",
            details={"balance_due_minor": outstanding},
        )
    change = 0
    tendered = None
    if method.kind == PaymentMethodKind.CASH:
        tendered = data.amount_tendered_minor or data.amount_minor
        if tendered < data.amount_minor:
            raise ValidationFailed("Cash tendered is less than the amount paid.", code="insufficient_tender")
        change = tendered - data.amount_minor
    elif data.amount_tendered_minor is not None and data.amount_tendered_minor != data.amount_minor:
        raise ValidationFailed("Change can only be given for cash payments.")
    payment = Payment(
        restaurant_id=ctx.restaurant_id,
        order_id=order.id,
        payment_method_id=method.id,
        method_code=method.code,
        method_name=method.name,
        method_kind=method.kind,
        is_simulated=method.is_simulated,
        amount_minor=data.amount_minor,
        amount_tendered_minor=tendered,
        change_minor=change,
        reference=data.reference,
        idempotency_key=idempotency_key,
        recorded_by=ctx.user_id,
    )
    db.add(payment)
    order.amount_paid_minor += data.amount_minor
    if order.amount_paid_minor >= order.total_minor:
        order.payment_status = PaymentStatus.PAID
        order.paid_at = now()
        loyalty.earn_for_order(db, ctx.restaurant, order, ctx.user_id)
    else:
        order.payment_status = PaymentStatus.PARTIALLY_PAID
    record_audit(
        db,
        action="payment.recorded",
        actor_user_id=ctx.user_id,
        restaurant_id=ctx.restaurant_id,
        entity_type="order",
        entity_id=order.id,
        details={"method": method.code, "amount_minor": data.amount_minor, "simulated": method.is_simulated},
        ip_address=ctx.ip,
    )
    _order_event(
        db, ctx, order, "order.paid" if order.payment_status == PaymentStatus.PAID else "order.payment_recorded"
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if idempotency_key:
            replay = _payment_replay(db, ctx, order_id, data, idempotency_key)
            if replay is not None:
                return replay
        raise
    return get_order_out(db, ctx, order.id), payment_out(payment), False


def _payment_replay(
    db: Session, ctx: RestaurantContext, order_id: uuid.UUID, data: PaymentCreate, key: str
) -> tuple[OrderOut, PaymentOut, bool] | None:
    existing = db.scalar(scoped(Payment, ctx.restaurant_id).where(Payment.idempotency_key == key))
    if existing is None:
        return None
    if (existing.order_id, existing.amount_minor, existing.payment_method_id) != (
        order_id,
        data.amount_minor,
        data.payment_method_id,
    ):
        raise Conflict("This idempotency key was already used for a different payment.", code="idempotency_key_reused")
    return get_order_out(db, ctx, order_id), payment_out(existing), True


def record_refund(
    db: Session, ctx: RestaurantContext, order_id: uuid.UUID, data: RefundCreate, idempotency_key: str | None
) -> tuple[OrderOut, RefundOut, bool]:
    ctx.require(Permission.REFUNDS_RECORD)
    if idempotency_key:
        existing = db.scalar(scoped(Refund, ctx.restaurant_id).where(Refund.idempotency_key == idempotency_key))
        if existing is not None:
            if (existing.order_id, existing.payment_id, existing.amount_minor) != (
                order_id,
                data.payment_id,
                data.amount_minor,
            ):
                raise Conflict(
                    "This idempotency key was already used for a different refund.", code="idempotency_key_reused"
                )
            return get_order_out(db, ctx, order_id), RefundOut.model_validate(existing), True
    order = load_order(db, ctx, order_id, for_update=True)
    if idempotency_key:
        existing = db.scalar(scoped(Refund, ctx.restaurant_id).where(Refund.idempotency_key == idempotency_key))
        if existing is not None:
            return get_order_out(db, ctx, order_id), RefundOut.model_validate(existing), True
    if order.payment_status not in (PaymentStatus.PAID, PaymentStatus.PARTIALLY_REFUNDED):
        raise Conflict("Only fully paid orders can be refunded.", code="order_not_refundable")
    payment = next((p for p in order.payments if p.id == data.payment_id), None)
    if payment is None:
        raise NotFound("Payment not found on this order.")
    refundable = payment.amount_minor - payment.refunded_minor
    if data.amount_minor > refundable:
        raise ValidationFailed(
            f"At most {refundable / 100:.2f} can be refunded on this payment.",
            code="refund_exceeds_payment",
            details={"refundable_minor": refundable},
        )
    refund = Refund(
        restaurant_id=ctx.restaurant_id,
        order_id=order.id,
        payment_id=payment.id,
        amount_minor=data.amount_minor,
        reason=data.reason,
        idempotency_key=idempotency_key,
        recorded_by=ctx.user_id,
    )
    db.add(refund)
    payment.refunded_minor += data.amount_minor
    order.amount_refunded_minor += data.amount_minor
    fully = order.amount_refunded_minor >= order.amount_paid_minor
    order.payment_status = PaymentStatus.REFUNDED if fully else PaymentStatus.PARTIALLY_REFUNDED
    db.flush()
    loyalty.reverse_for_refund(db, order, ctx.user_id)
    if fully:
        loyalty.restore_redeemed(db, order, "Order fully refunded", ctx.user_id)
    record_audit(
        db,
        action="refund.recorded",
        actor_user_id=ctx.user_id,
        restaurant_id=ctx.restaurant_id,
        entity_type="order",
        entity_id=order.id,
        details={"amount_minor": data.amount_minor, "payment_id": str(payment.id), "reason": data.reason},
        ip_address=ctx.ip,
    )
    _order_event(db, ctx, order, "order.refunded")
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise Conflict("This refund was already recorded.", code="duplicate_refund") from None
    return get_order_out(db, ctx, order.id), RefundOut.model_validate(refund), False


# --------------------------------------------------------------------------- listing


def list_orders(
    db: Session,
    ctx: RestaurantContext,
    params: PageParams,
    *,
    status: list[OrderStatus] | None,
    payment_status: PaymentStatus | None,
    order_type: OrderType | None,
    table_id: uuid.UUID | None,
    customer_id: uuid.UUID | None,
    start: datetime | None,
    end: datetime | None,
    search: str | None,
) -> tuple[list[OrderListItem], int]:
    stmt = scoped(Order, ctx.restaurant_id).order_by(Order.created_at.desc())
    if status:
        stmt = stmt.where(Order.status.in_(status))
    if payment_status:
        stmt = stmt.where(Order.payment_status == payment_status)
    if order_type:
        stmt = stmt.where(Order.order_type == order_type)
    if table_id:
        stmt = stmt.where(Order.table_id == table_id)
    if customer_id:
        stmt = stmt.where(Order.customer_id == customer_id)
    if start:
        stmt = stmt.where(Order.created_at >= start)
    if end:
        stmt = stmt.where(Order.created_at < end)
    if search:
        digits = "".join(ch for ch in search if ch.isdigit())
        conditions = [Order.notes.ilike(f"%{search.strip()}%")]
        if digits:
            conditions.append(Order.order_number == int(digits[:9]))
        stmt = stmt.where(or_(*conditions))
    orders, total = paginate(db, stmt, params)
    ids = [o.id for o in orders]
    counts = (
        dict(
            db.execute(
                select(OrderItem.order_id, func.sum(OrderItem.quantity))
                .where(OrderItem.order_id.in_(ids))
                .group_by(OrderItem.order_id)
            ).all()
        )
        if ids
        else {}
    )
    tables = (
        dict(
            db.execute(
                select(DiningTable.id, DiningTable.name).where(
                    DiningTable.id.in_({o.table_id for o in orders if o.table_id})
                )
            ).all()
        )
        if ids
        else {}
    )
    customers = (
        dict(
            db.execute(
                select(Customer.id, Customer.name).where(
                    Customer.id.in_({o.customer_id for o in orders if o.customer_id})
                )
            ).all()
        )
        if ids
        else {}
    )
    prefix = ctx.restaurant.order_number_prefix
    return [
        OrderListItem(
            id=o.id,
            order_number=o.order_number,
            display_number=display_number(prefix, o.order_number),
            order_type=o.order_type,
            status=o.status,
            payment_status=o.payment_status,
            table_name=tables.get(o.table_id),
            customer_name=customers.get(o.customer_id),
            item_count=int(counts.get(o.id, 0) or 0),
            total_minor=o.total_minor,
            amount_paid_minor=o.amount_paid_minor,
            created_at=o.created_at,
            paid_at=o.paid_at,
        )
        for o in orders
    ], total
