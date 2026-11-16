"""CSV report exports.

Cells that a spreadsheet could interpret as a formula (starting with =, +, -,
@, tab or carriage return) are prefixed with a single quote to prevent CSV
injection.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Sequence
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import RestaurantContext
from app.models import Customer, DiningTable, Ingredient, InventoryMovement, Order
from app.models.enums import OrderStatus
from app.repositories.tenant import scoped
from app.services import analytics
from app.services.inventory import stock_value_minor
from app.services.tables import display_number

_DANGEROUS = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value: object) -> object:
    if isinstance(value, str) and value.startswith(_DANGEROUS):
        return "'" + value
    return value


def to_csv(header: Sequence[str], rows: Iterable[Sequence[object]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    for row in rows:
        writer.writerow([safe_cell(v) for v in row])
    # UTF-8 BOM so spreadsheet apps open Thai text correctly.
    return "﻿" + buffer.getvalue()


def money(minor: int | None) -> str:
    return f"{(minor or 0) / 100:.2f}"


def daily_sales_csv(db: Session, ctx: RestaurantContext, f: analytics.Filters) -> str:
    days = analytics.sales_by_day(db, ctx, f)
    rows = []
    for day in days:
        s = analytics.summary(
            db, ctx, analytics.Filters(day.date, day.date, f.product_id, f.category_id, f.payment_method, f.order_type)
        )
        rows.append(
            [
                day.date.isoformat(),
                s.order_count,
                s.items_sold,
                money(s.gross_sales_minor),
                money(s.discounts_minor),
                money(s.refunds_minor),
                money(s.net_sales_minor),
                money(s.tax_minor),
                money(s.service_charge_minor),
                money(s.total_billed_minor),
                money(s.total_collected_minor),
            ]
        )
    return to_csv(
        [
            "date",
            "orders",
            "items_sold",
            "gross_sales",
            "discounts",
            "refunds",
            "net_sales",
            "tax",
            "service_charge",
            "total_billed",
            "total_collected",
        ],
        rows,
    )


def product_sales_csv(db: Session, ctx: RestaurantContext, f: analytics.Filters) -> str:
    products = analytics.top_products(db, ctx, f, limit=10_000)
    return to_csv(
        ["product", "category", "quantity", "sales"],
        [[p.product_name, p.category_name or "", p.quantity, money(p.sales_minor)] for p in products],
    )


def orders_csv(db: Session, ctx: RestaurantContext, f: analytics.Filters) -> str:
    lower, upper = analytics.bounds(ctx, f)
    orders = db.scalars(
        scoped(Order, ctx.restaurant_id)
        .where(Order.created_at >= lower, Order.created_at < upper)
        .order_by(Order.created_at)
    ).all()
    tables = dict(
        db.execute(select(DiningTable.id, DiningTable.name).where(DiningTable.restaurant_id == ctx.restaurant_id)).all()
    )
    customers = dict(
        db.execute(select(Customer.id, Customer.name).where(Customer.restaurant_id == ctx.restaurant_id)).all()
    )
    tz = ZoneInfo(ctx.restaurant.timezone)

    def local(dt: datetime | None) -> str:
        return dt.astimezone(tz).strftime("%Y-%m-%d %H:%M") if dt else ""

    rows = [
        [
            display_number(ctx.restaurant.order_number_prefix, o.order_number),
            local(o.created_at),
            local(o.paid_at),
            o.order_type.value,
            o.status.value,
            o.payment_status.value,
            tables.get(o.table_id, ""),
            customers.get(o.customer_id, ""),
            money(o.subtotal_minor),
            money(o.discount_minor + o.loyalty_discount_minor),
            money(o.service_charge_minor),
            money(o.tax_minor),
            money(o.total_minor),
            money(o.amount_paid_minor),
            money(o.amount_refunded_minor),
            o.cancel_reason if o.status == OrderStatus.CANCELLED else "",
        ]
        for o in orders
    ]
    return to_csv(
        [
            "order",
            "created",
            "paid",
            "type",
            "status",
            "payment_status",
            "table",
            "customer",
            "subtotal",
            "discounts",
            "service_charge",
            "tax",
            "total",
            "paid_amount",
            "refunded",
            "cancel_reason",
        ],
        rows,
    )


def inventory_movements_csv(db: Session, ctx: RestaurantContext, f: analytics.Filters) -> str:
    lower, upper = analytics.bounds(ctx, f)
    rows = db.execute(
        select(InventoryMovement, Ingredient.name, Ingredient.base_unit)
        .join(Ingredient, Ingredient.id == InventoryMovement.ingredient_id)
        .where(
            InventoryMovement.restaurant_id == ctx.restaurant_id,
            InventoryMovement.created_at >= lower,
            InventoryMovement.created_at < upper,
        )
        .order_by(InventoryMovement.created_at)
    ).all()
    tz = ZoneInfo(ctx.restaurant.timezone)
    return to_csv(
        ["time", "ingredient", "type", "quantity", "unit", "balance_after", "unit_cost_basis_satang", "reason"],
        [
            [
                m.created_at.astimezone(tz).strftime("%Y-%m-%d %H:%M"),
                name,
                m.movement_type.value,
                m.quantity,
                unit.value,
                m.balance_after,
                m.unit_cost_minor if m.unit_cost_minor is not None else "",
                m.reason or "",
            ]
            for m, name, unit in rows
        ],
    )


def inventory_valuation_csv(db: Session, ctx: RestaurantContext) -> str:
    ingredients = db.scalars(
        scoped(Ingredient, ctx.restaurant_id).where(Ingredient.is_active.is_(True)).order_by(Ingredient.name)
    ).all()
    return to_csv(
        ["ingredient", "unit", "current_stock", "reorder_level", "safety_stock", "average_cost_satang", "stock_value"],
        [
            [
                i.name,
                i.base_unit.value,
                i.current_stock,
                i.reorder_level,
                i.safety_stock,
                i.average_cost_minor,
                money(stock_value_minor(i)),
            ]
            for i in ingredients
        ],
    )


def purchases_csv(db: Session, ctx: RestaurantContext, f: analytics.Filters) -> str:
    return to_csv(
        ["supplier", "deliveries", "amount"],
        [[s.supplier_name, s.deliveries, money(s.amount_minor)] for s in analytics.purchases(db, ctx, f)],
    )
