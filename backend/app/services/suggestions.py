"""POS add-on suggestions mined from the restaurant's own sales.

Three explainable sources, in this order:

* **Customer's usual**: products the selected customer has ordered in at least
  two separate visits in the last year.
* **Ordered together** (association rules over settled orders in the last
  90 days). For a cart item A and another product B::

      support(A, B) = orders containing both
      confidence    = support(A, B) / orders containing A
      lift          = confidence / (orders containing B / all orders)

  B qualifies when it shared at least ``MIN_PAIR_ORDERS`` orders with A and
  ``lift > MIN_LIFT`` (1.3), i.e. it is bought with A more often than by chance.
* **Popular now**: best sellers in this hour of the day over the last four
  weeks (or this week's best sellers when the hour is quiet), used when the
  cart is empty.

Only active, available products that are not already in the cart are suggested.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.api.deps import RestaurantContext
from app.core.permissions import Permission
from app.models import Order, OrderItem, Product
from app.models.enums import OrderStatus
from app.schemas.catalog import ProductSuggestion
from app.services import analytics

LOOKBACK_DAYS = 90
MIN_PAIR_ORDERS = 3
MIN_LIFT = 1.3
MIN_CUSTOMER_VISITS = 2
POPULAR_WINDOW_DAYS = 28
MIN_POPULAR_QUANTITY = 3


def _settled(ctx: RestaurantContext, since: datetime) -> list:
    return [
        Order.restaurant_id == ctx.restaurant_id,
        Order.status != OrderStatus.CANCELLED,
        Order.payment_status.in_(analytics.SETTLED),
        Order.paid_at >= since,
    ]


def _basket(ctx: RestaurantContext, since: datetime):
    """One row per (order, product) in settled orders since ``since``."""
    return (
        select(OrderItem.order_id, OrderItem.product_id)
        .join(Order, Order.id == OrderItem.order_id)
        .where(*_settled(ctx, since))
        .distinct()
        .subquery()
    )


def _ordered_together(
    db: Session,
    ctx: RestaurantContext,
    cart: list[uuid.UUID],
    names: dict[uuid.UUID, str],
    menu: dict[uuid.UUID, str],
) -> list[ProductSuggestion]:
    since = datetime.now(UTC) - timedelta(days=LOOKBACK_DAYS)
    basket = _basket(ctx, since)
    total = db.scalar(select(func.count(distinct(basket.c.order_id)))) or 0
    if not total:
        return []
    counts = dict(db.execute(select(basket.c.product_id, func.count()).group_by(basket.c.product_id)).all())
    a, b = basket.alias("a"), basket.alias("b")
    pairs = db.execute(
        select(a.c.product_id, b.c.product_id, func.count())
        .join(b, (a.c.order_id == b.c.order_id) & (a.c.product_id != b.c.product_id))
        .where(a.c.product_id.in_(cart), b.c.product_id.not_in(cart))
        .group_by(a.c.product_id, b.c.product_id)
        .having(func.count() >= MIN_PAIR_ORDERS)
    ).all()
    best: dict[uuid.UUID, ProductSuggestion] = {}
    for anchor, candidate, together in pairs:
        if candidate not in names or not counts.get(anchor) or not counts.get(candidate):
            continue
        confidence = together / counts[anchor]
        lift = confidence / (counts[candidate] / total)
        if lift <= MIN_LIFT:
            continue
        current = best.get(candidate)
        if current is None or confidence > current.score:
            best[candidate] = ProductSuggestion(
                product_id=candidate,
                product_name=names[candidate],
                kind="ordered_together",
                reason=f"In {confidence:.0%} of orders with {menu[anchor].split(' (')[0]}",
                score=round(confidence, 3),
                evidence={"orders_together": together, "orders_with_item": counts[anchor], "lift": round(lift, 2)},
            )
    return sorted(best.values(), key=lambda s: -s.score)


def _customer_usual(
    db: Session, ctx: RestaurantContext, customer_id: uuid.UUID, cart: list[uuid.UUID], names: dict[uuid.UUID, str]
) -> list[ProductSuggestion]:
    since = datetime.now(UTC) - timedelta(days=365)
    rows = db.execute(
        select(OrderItem.product_id, func.count(distinct(Order.id)))
        .join(Order, Order.id == OrderItem.order_id)
        .where(*_settled(ctx, since), Order.customer_id == customer_id, OrderItem.product_id.not_in(cart))
        .group_by(OrderItem.product_id)
        .having(func.count(distinct(Order.id)) >= MIN_CUSTOMER_VISITS)
        .order_by(func.count(distinct(Order.id)).desc())
    ).all()
    return [
        ProductSuggestion(
            product_id=pid,
            product_name=names[pid],
            kind="customer_usual",
            reason=f"Ordered on {visits} visits by this customer",
            score=float(visits),
            evidence={"visits": visits},
        )
        for pid, visits in rows
        if pid in names
    ]


def _popular_now(
    db: Session, ctx: RestaurantContext, cart: list[uuid.UUID], names: dict[uuid.UUID, str]
) -> list[ProductSuggestion]:
    """Best sellers at this hour of the day; this week's best sellers when the hour is quiet."""
    since = datetime.now(UTC) - timedelta(days=POPULAR_WINDOW_DAYS)
    hour = analytics.local_now(ctx).hour
    local_hour = func.extract("hour", func.timezone(ctx.restaurant.timezone, Order.paid_at))
    sold = func.sum(OrderItem.quantity)
    base = (
        select(OrderItem.product_id, sold)
        .join(Order, Order.id == OrderItem.order_id)
        .where(OrderItem.product_id.not_in(cart))
        .group_by(OrderItem.product_id)
        .having(sold >= MIN_POPULAR_QUANTITY)
        .order_by(sold.desc())
    )
    rows = db.execute(base.where(*_settled(ctx, since), local_hour == hour)).all()
    label = f"around {hour:02d}:00–{(hour + 1) % 24:02d}:00 in the last 4 weeks"
    if not rows:
        rows = db.execute(base.where(*_settled(ctx, datetime.now(UTC) - timedelta(days=7)))).all()
        label = "in the last 7 days"
    rows = sorted((r for r in rows if r[0] in names), key=lambda r: (-r[1], names[r[0]]))
    return [
        ProductSuggestion(
            product_id=pid,
            product_name=names[pid],
            kind="popular_now",
            reason=f"{int(qty)} sold {label}",
            score=float(qty),
            evidence={"quantity": int(qty), "hour": hour},
        )
        for pid, qty in rows
    ]


def suggest(
    db: Session,
    ctx: RestaurantContext,
    cart: list[uuid.UUID],
    customer_id: uuid.UUID | None = None,
    limit: int = 4,
) -> list[ProductSuggestion]:
    cart = list(dict.fromkeys(cart))
    # Only sellable products, never something already in the cart.
    menu = dict(db.execute(select(Product.id, Product.name).where(Product.restaurant_id == ctx.restaurant_id)).all())
    sellable = db.scalars(
        select(Product.id).where(
            Product.restaurant_id == ctx.restaurant_id,
            Product.is_active.is_(True),
            Product.is_available.is_(True),
        )
    ).all()
    names = {pid: menu[pid] for pid in sellable if pid not in cart}
    if not names:
        return []
    found: list[ProductSuggestion] = []
    # A known customer's own habits come first, then what other guests pair with the cart.
    if customer_id is not None and ctx.can(Permission.CUSTOMERS_READ):
        found += _customer_usual(db, ctx, customer_id, cart, names)
    if cart:
        found += _ordered_together(db, ctx, cart, names, menu)
    if not cart:
        found += _popular_now(db, ctx, cart, names)
    seen: set[uuid.UUID] = set()
    out = []
    for suggestion in found:
        if suggestion.product_id in seen:
            continue
        seen.add(suggestion.product_id)
        out.append(suggestion)
        if len(out) == limit:
            break
    return out
