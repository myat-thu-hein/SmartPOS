"""Sales analytics computed from persisted transactions.

Dates are interpreted in the restaurant's time zone. A sale belongs to the
local day on which its order became fully paid (``paid_at``); a refund belongs
to the day it was recorded. Product and category filters select orders that
contain the product/category for order-level metrics, and only matching items
for item-level breakdowns.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import Date, and_, cast, exists, func, select
from sqlalchemy.orm import Session

from app.api.deps import RestaurantContext
from app.core.errors import ValidationFailed
from app.db.base import ZERO
from app.models import (
    Category,
    Ingredient,
    InventoryMovement,
    Order,
    OrderItem,
    Payment,
    Product,
    PurchaseOrder,
    PurchaseOrderReceipt,
    Refund,
    Supplier,
)
from app.models.enums import MovementType, OrderStatus, OrderType, PaymentStatus
from app.schemas.analytics import (
    CategorySales,
    DateRange,
    DayBucket,
    HourBucket,
    IngredientUsage,
    PaymentShare,
    PeriodComparison,
    ProductSales,
    SalesSummary,
    SupplierSpend,
)

SETTLED = (PaymentStatus.PAID, PaymentStatus.PARTIALLY_REFUNDED, PaymentStatus.REFUNDED)
MAX_RANGE_DAYS = 366


@dataclass(frozen=True)
class Filters:
    start_date: date
    end_date: date
    product_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    payment_method: str | None = None
    order_type: OrderType | None = None
    # Local time of day at which the last day of the range ends. Used so that a
    # period that is still in progress is compared with the same elapsed time.
    cutoff: time | None = None

    def shifted(self, days: int) -> Filters:
        return replace(
            self, start_date=self.start_date - timedelta(days=days), end_date=self.end_date - timedelta(days=days)
        )

    @property
    def days(self) -> int:
        return (self.end_date - self.start_date).days + 1


def validate_range(start: date, end: date) -> None:
    if end < start:
        raise ValidationFailed("end_date must be on or after start_date.")
    if (end - start).days + 1 > MAX_RANGE_DAYS:
        raise ValidationFailed(f"Date ranges are limited to {MAX_RANGE_DAYS} days.")


def local_now(ctx: RestaurantContext) -> datetime:
    return datetime.now(ZoneInfo(ctx.restaurant.timezone))


def local_today(ctx: RestaurantContext) -> date:
    return local_now(ctx).date()


def local_date_of(ctx: RestaurantContext, moment: datetime) -> date:
    """Calendar date of a timestamp in the restaurant's time zone."""
    return moment.astimezone(ZoneInfo(ctx.restaurant.timezone)).date()


def utc_bounds_for(timezone: str, start: date, end: date) -> tuple[datetime, datetime]:
    """UTC instants covering local dates start..end (inclusive) in `timezone`."""
    tz = ZoneInfo(timezone)
    lower = datetime.combine(start, time.min, tzinfo=tz).astimezone(UTC)
    upper = datetime.combine(end + timedelta(days=1), time.min, tzinfo=tz).astimezone(UTC)
    return lower, upper


def utc_bounds(ctx: RestaurantContext, start: date, end: date) -> tuple[datetime, datetime]:
    return utc_bounds_for(ctx.restaurant.timezone, start, end)


def bounds(ctx: RestaurantContext, f: Filters) -> tuple[datetime, datetime]:
    """UTC instants for the filter's local date range, honouring its cutoff time."""
    lower, upper = utc_bounds(ctx, f.start_date, f.end_date)
    if f.cutoff is not None:
        tz = ZoneInfo(ctx.restaurant.timezone)
        upper = min(upper, datetime.combine(f.end_date, f.cutoff, tzinfo=tz).astimezone(UTC))
    return lower, upper


def _local(ctx: RestaurantContext, column):
    return func.timezone(ctx.restaurant.timezone, column)


def _order_conditions(ctx: RestaurantContext, f: Filters, *, by_paid_at: bool = True) -> list:
    lower, upper = bounds(ctx, f)
    conditions = [
        Order.restaurant_id == ctx.restaurant_id,
        Order.status != OrderStatus.CANCELLED,
        Order.payment_status.in_(SETTLED),
    ]
    if by_paid_at:
        conditions += [Order.paid_at >= lower, Order.paid_at < upper]
    if f.order_type:
        conditions.append(Order.order_type == f.order_type)
    if f.payment_method:
        conditions.append(
            exists(select(Payment.id).where(Payment.order_id == Order.id, Payment.method_code == f.payment_method))
        )
    if f.product_id or f.category_id:
        conditions.append(exists(select(OrderItem.id).where(OrderItem.order_id == Order.id, *_item_conditions(f))))
    return conditions


def _item_conditions(f: Filters) -> list:
    conditions = []
    if f.product_id:
        conditions.append(OrderItem.product_id == f.product_id)
    if f.category_id:
        conditions.append(OrderItem.category_id == f.category_id)
    return conditions


def _minor(value: Decimal | int | float | None) -> int:
    return int(Decimal(value or 0).quantize(Decimal(1), ROUND_HALF_UP))


def _pct(new: float, old: float) -> float | None:
    if old == 0:
        return None
    return round((new - old) / old * 100, 1)


# --------------------------------------------------------------------------- summary


def summary(db: Session, ctx: RestaurantContext, f: Filters) -> SalesSummary:
    conditions = _order_conditions(ctx, f)
    row = db.execute(
        select(
            func.count(Order.id),
            func.coalesce(func.sum(Order.subtotal_minor), 0),
            func.coalesce(func.sum(Order.discount_minor + Order.loyalty_discount_minor), 0),
            func.coalesce(func.sum(Order.tax_minor), 0),
            func.coalesce(func.sum(Order.service_charge_minor), 0),
            func.coalesce(func.sum(Order.total_minor), 0),
        ).where(*conditions)
    ).one()
    count, gross, discounts, tax, service, billed = (int(v) for v in row)
    items_sold = int(
        db.scalar(
            select(func.coalesce(func.sum(OrderItem.quantity), 0))
            .join(Order, Order.id == OrderItem.order_id)
            .where(*conditions, *_item_conditions(f))
        )
        or 0
    )

    lower, upper = bounds(ctx, f)
    refund_rows = db.execute(
        select(Refund.amount_minor, Order.total_minor, Order.tax_minor, Order.service_charge_minor)
        .join(Order, Order.id == Refund.order_id)
        .where(
            Refund.restaurant_id == ctx.restaurant_id,
            Refund.created_at >= lower,
            Refund.created_at < upper,
            *_order_conditions(ctx, f, by_paid_at=False),
        )
    ).all()
    refunds = sum(r.amount_minor for r in refund_rows)
    refunds_ex_tax = sum(
        Decimal(r.amount_minor) * (r.total_minor - r.tax_minor - r.service_charge_minor) / r.total_minor
        for r in refund_rows
        if r.total_minor
    )

    usage = ingredient_consumption(db, ctx, f)
    ingredient_cost = sum(u.estimated_cost_minor for u in usage)
    cost_complete = all(u.cost_known for u in usage)
    revenue_ex_tax = Decimal(billed - tax - service) - refunds_ex_tax
    profit = _minor(revenue_ex_tax - ingredient_cost) if count else None
    return SalesSummary(
        range=DateRange(
            start_date=f.start_date, end_date=f.end_date, timezone=ctx.restaurant.timezone, cutoff_time=f.cutoff
        ),
        order_count=count,
        items_sold=items_sold,
        gross_sales_minor=gross,
        discounts_minor=discounts,
        refunds_minor=refunds,
        net_sales_minor=gross - discounts - refunds,
        tax_minor=tax,
        service_charge_minor=service,
        total_billed_minor=billed,
        total_collected_minor=billed - refunds,
        average_order_value_minor=billed // count if count else 0,
        estimated_ingredient_cost_minor=ingredient_cost,
        estimated_gross_profit_minor=profit,
        cost_data_complete=cost_complete,
        prices_include_tax=ctx.restaurant.prices_include_tax,
    )


def comparison(db: Session, ctx: RestaurantContext, f: Filters) -> PeriodComparison:
    """Compare a range with the preceding range of equal length.

    When the range ends today, both ranges stop at the current local time of day,
    so a day in progress is compared with the same hours of the previous day.
    """
    now = local_now(ctx)
    if f.cutoff is None and f.end_date == now.date():
        # Round up to the next minute so sales made moments ago are included.
        cutoff = (now + timedelta(minutes=1)).replace(second=0, microsecond=0)
        if cutoff.date() == now.date():
            f = replace(f, cutoff=cutoff.time())
    current = summary(db, ctx, f)
    previous = summary(db, ctx, f.shifted(f.days))
    return PeriodComparison(
        current=current,
        previous=previous,
        net_sales_change_pct=_pct(current.net_sales_minor, previous.net_sales_minor),
        order_count_change_pct=_pct(current.order_count, previous.order_count),
        aov_change_pct=_pct(current.average_order_value_minor, previous.average_order_value_minor),
    )


# --------------------------------------------------------------------------- breakdowns


def sales_by_hour(db: Session, ctx: RestaurantContext, f: Filters) -> list[HourBucket]:
    hour = func.extract("hour", _local(ctx, Order.paid_at))
    rows = db.execute(
        select(hour, func.count(Order.id), func.sum(Order.total_minor)).where(*_order_conditions(ctx, f)).group_by(hour)
    ).all()
    found = {int(h): (int(c), int(t)) for h, c, t in rows}
    return [
        HourBucket(hour=h, order_count=found.get(h, (0, 0))[0], total_billed_minor=found.get(h, (0, 0))[1])
        for h in range(24)
    ]


def sales_by_day(db: Session, ctx: RestaurantContext, f: Filters) -> list[DayBucket]:
    """Per local day. Net sales follow ``summary``: gross - discounts of orders paid that day,
    minus refunds recorded that day."""
    day = cast(_local(ctx, Order.paid_at), Date)
    rows = db.execute(
        select(
            day,
            func.count(Order.id),
            func.sum(Order.subtotal_minor),
            func.sum(Order.discount_minor + Order.loyalty_discount_minor),
            func.sum(Order.total_minor),
        )
        .where(*_order_conditions(ctx, f))
        .group_by(day)
    ).all()
    found = {d: (int(c), int(g), int(disc), int(t)) for d, c, g, disc, t in rows}
    lower, upper = bounds(ctx, f)
    refund_day = cast(_local(ctx, Refund.created_at), Date)
    refunds = dict(
        db.execute(
            select(refund_day, func.sum(Refund.amount_minor))
            .join(Order, Order.id == Refund.order_id)
            .where(
                Refund.restaurant_id == ctx.restaurant_id,
                Refund.created_at >= lower,
                Refund.created_at < upper,
                *_order_conditions(ctx, f, by_paid_at=False),
            )
            .group_by(refund_day)
        ).all()
    )
    out = []
    current = f.start_date
    while current <= f.end_date:
        c, g, disc, t = found.get(current, (0, 0, 0, 0))
        out.append(
            DayBucket(
                date=current,
                order_count=c,
                gross_sales_minor=g,
                net_sales_minor=g - disc - int(refunds.get(current) or 0),
                total_billed_minor=t,
            )
        )
        current += timedelta(days=1)
    return out


def sales_by_category(db: Session, ctx: RestaurantContext, f: Filters) -> list[CategorySales]:
    name = func.coalesce(OrderItem.category_name, "Uncategorised")
    rows = db.execute(
        select(name, func.sum(OrderItem.quantity), func.sum(OrderItem.line_total_minor))
        .join(Order, Order.id == OrderItem.order_id)
        .where(*_order_conditions(ctx, f), *_item_conditions(f))
        .group_by(name)
        .order_by(func.sum(OrderItem.line_total_minor).desc())
    ).all()
    total = sum(int(r[2]) for r in rows) or 1
    return [
        CategorySales(category_name=n, quantity=int(q), sales_minor=int(s), share_pct=round(int(s) / total * 100, 1))
        for n, q, s in rows
    ]


def _product_sales(db: Session, ctx: RestaurantContext, f: Filters) -> dict[uuid.UUID, tuple[int, int]]:
    rows = db.execute(
        select(OrderItem.product_id, func.sum(OrderItem.quantity), func.sum(OrderItem.line_total_minor))
        .join(Order, Order.id == OrderItem.order_id)
        .where(*_order_conditions(ctx, f), *_item_conditions(f))
        .group_by(OrderItem.product_id)
    ).all()
    return {pid: (int(q), int(s)) for pid, q, s in rows}


def _products(
    db: Session, ctx: RestaurantContext, ids: set[uuid.UUID] | None = None, active_only: bool = False
) -> dict[uuid.UUID, tuple[str, str | None]]:
    stmt = (
        select(Product.id, Product.name, Category.name)
        .join(Category, Category.id == Product.category_id)
        .where(Product.restaurant_id == ctx.restaurant_id)
    )
    if ids is not None:
        stmt = stmt.where(Product.id.in_(ids))
    if active_only:
        stmt = stmt.where(Product.is_active.is_(True))
    return {pid: (name, cat) for pid, name, cat in db.execute(stmt).all()}


def top_products(db: Session, ctx: RestaurantContext, f: Filters, limit: int = 10) -> list[ProductSales]:
    sales = _product_sales(db, ctx, f)
    names = _products(db, ctx, set(sales))
    ranked = sorted(sales.items(), key=lambda kv: (-kv[1][0], -kv[1][1]))[:limit]
    return [
        ProductSales(
            product_id=pid,
            product_name=names.get(pid, ("Unknown", None))[0],
            category_name=names.get(pid, ("", None))[1],
            quantity=q,
            sales_minor=s,
        )
        for pid, (q, s) in ranked
    ]


def slow_products(db: Session, ctx: RestaurantContext, f: Filters, limit: int = 10) -> list[ProductSales]:
    """Active products with the lowest sales, including products that did not sell at all."""
    sales = _product_sales(db, ctx, f)
    products = _products(db, ctx, active_only=True)
    if f.category_id:
        allowed = set(db.scalars(select(Product.id).where(Product.category_id == f.category_id)).all())
        products = {k: v for k, v in products.items() if k in allowed}
    ranked = sorted(
        products.items(), key=lambda kv: (sales.get(kv[0], (0, 0))[0], sales.get(kv[0], (0, 0))[1], kv[1][0])
    )[:limit]
    return [
        ProductSales(
            product_id=pid,
            product_name=name,
            category_name=cat,
            quantity=sales.get(pid, (0, 0))[0],
            sales_minor=sales.get(pid, (0, 0))[1],
        )
        for pid, (name, cat) in ranked
    ]


def payment_distribution(db: Session, ctx: RestaurantContext, f: Filters) -> list[PaymentShare]:
    lower, upper = bounds(ctx, f)
    order_conditions = _order_conditions(ctx, replace(f, payment_method=None), by_paid_at=False)
    rows = db.execute(
        select(
            Payment.method_code,
            Payment.method_name,
            Payment.is_simulated,
            func.count(Payment.id),
            func.sum(Payment.amount_minor),
        )
        .join(Order, Order.id == Payment.order_id)
        .where(
            Payment.restaurant_id == ctx.restaurant_id,
            Payment.created_at >= lower,
            Payment.created_at < upper,
            *order_conditions,
        )
        .group_by(Payment.method_code, Payment.method_name, Payment.is_simulated)
    ).all()
    refunds = dict(
        db.execute(
            select(Payment.method_code, func.sum(Refund.amount_minor))
            .join(Payment, Payment.id == Refund.payment_id)
            .join(Order, Order.id == Refund.order_id)
            .where(
                Refund.restaurant_id == ctx.restaurant_id,
                Refund.created_at >= lower,
                Refund.created_at < upper,
                *order_conditions,
            )
            .group_by(Payment.method_code)
        ).all()
    )
    if f.payment_method:
        rows = [r for r in rows if r[0] == f.payment_method]
    total = sum(int(r[4]) for r in rows) or 1
    return [
        PaymentShare(
            method_code=code,
            method_name=name,
            is_simulated=sim,
            payment_count=int(count),
            amount_minor=int(amount),
            refunded_minor=int(refunds.get(code, 0) or 0),
            share_pct=round(int(amount) / total * 100, 1),
        )
        for code, name, sim, count, amount in sorted(rows, key=lambda r: -int(r[4]))
    ]


def _movement_usage(
    db: Session, ctx: RestaurantContext, f: Filters, types: tuple[MovementType, ...]
) -> list[IngredientUsage]:
    """Net usage per ingredient, valued at the cost basis recorded on each movement.

    Movements written before cost snapshots existed fall back to the current
    moving-average cost.
    """
    lower, upper = bounds(ctx, f)
    cost = func.coalesce(InventoryMovement.unit_cost_minor, Ingredient.average_cost_minor)
    rows = db.execute(
        select(
            Ingredient.id,
            Ingredient.name,
            Ingredient.base_unit,
            -func.sum(InventoryMovement.quantity),
            -func.sum(InventoryMovement.quantity * cost),
            func.bool_and(cost > 0),
        )
        .join(Ingredient, Ingredient.id == InventoryMovement.ingredient_id)
        .where(
            InventoryMovement.restaurant_id == ctx.restaurant_id,
            InventoryMovement.movement_type.in_(types),
            InventoryMovement.created_at >= lower,
            InventoryMovement.created_at < upper,
        )
        .group_by(Ingredient.id, Ingredient.name, Ingredient.base_unit)
    ).all()
    out = [
        IngredientUsage(
            ingredient_id=i,
            ingredient_name=n,
            base_unit=u.value,
            quantity=q,
            estimated_cost_minor=_minor(value or ZERO),
            cost_known=bool(known),
        )
        for i, n, u, q, value, known in rows
        if q and q != 0
    ]
    return sorted(out, key=lambda u: -u.estimated_cost_minor)


def ingredient_consumption(db: Session, ctx: RestaurantContext, f: Filters) -> list[IngredientUsage]:
    """Net ingredient use by sales (deductions minus reversals), valued at the cost in effect at the time."""
    return _movement_usage(db, ctx, f, (MovementType.SALE, MovementType.SALE_REVERSAL))


def waste(db: Session, ctx: RestaurantContext, f: Filters) -> list[IngredientUsage]:
    return _movement_usage(db, ctx, f, (MovementType.WASTE,))


def purchases(db: Session, ctx: RestaurantContext, f: Filters) -> list[SupplierSpend]:
    lower, upper = bounds(ctx, f)
    rows = db.execute(
        select(
            Supplier.id,
            Supplier.name,
            func.count(PurchaseOrderReceipt.id),
            func.sum(PurchaseOrderReceipt.total_cost_minor),
        )
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderReceipt.purchase_order_id)
        .join(Supplier, Supplier.id == PurchaseOrder.supplier_id)
        .where(
            PurchaseOrderReceipt.restaurant_id == ctx.restaurant_id,
            PurchaseOrderReceipt.created_at >= lower,
            PurchaseOrderReceipt.created_at < upper,
        )
        .group_by(Supplier.id, Supplier.name)
    ).all()
    return sorted(
        [
            SupplierSpend(supplier_id=i, supplier_name=n, deliveries=int(c), amount_minor=int(a or 0))
            for i, n, c, a in rows
        ],
        key=lambda s: -s.amount_minor,
    )


def daily_product_quantities(
    db: Session, restaurant_id: uuid.UUID, timezone: str, start: date, end: date
) -> list[tuple[uuid.UUID, date, int]]:
    """Quantity sold per product per local day (used by forecasting)."""
    lower, upper = utc_bounds_for(timezone, start, end)
    day = cast(func.timezone(timezone, Order.paid_at), Date)
    rows = db.execute(
        select(OrderItem.product_id, day, func.sum(OrderItem.quantity))
        .join(Order, Order.id == OrderItem.order_id)
        .where(
            and_(
                Order.restaurant_id == restaurant_id,
                Order.status != OrderStatus.CANCELLED,
                Order.payment_status.in_(SETTLED),
                Order.paid_at >= lower,
                Order.paid_at < upper,
            )
        )
        .group_by(OrderItem.product_id, day)
    ).all()
    return [(pid, d, int(q)) for pid, d, q in rows]
