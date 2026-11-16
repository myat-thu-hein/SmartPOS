"""Loyalty points ledger.

Rules (configurable per restaurant):
* Earn: when an order becomes fully paid, the customer earns
  floor(order total / spend-per-point) points. A partial unique index ensures
  an order can earn only once.
* Redeem: points are reserved as a discount when the order is confirmed.
* Refunds reverse earned points proportionally to the refunded amount.
  A full refund also restores redeemed points.
* Cancelling an unpaid order restores redeemed points.

The cached ``Customer.loyalty_balance`` is updated in the same transaction as
each ledger entry while the customer row is locked.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ValidationFailed
from app.models import Customer, LoyaltyTransaction, Order, Restaurant
from app.models.enums import LoyaltyTransactionType
from app.services.pricing import loyalty_points_earned, proportional_points


def lock_customer(db: Session, restaurant_id: uuid.UUID, customer_id: uuid.UUID) -> Customer:
    customer = db.scalar(
        select(Customer)
        .where(Customer.id == customer_id, Customer.restaurant_id == restaurant_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if customer is None:
        raise ValidationFailed("Customer not found.", code="customer_not_found")
    return customer


def post(
    db: Session,
    customer: Customer,
    tx_type: LoyaltyTransactionType,
    points: int,
    *,
    order_id: uuid.UUID | None = None,
    reason: str | None = None,
    actor_user_id: uuid.UUID | None = None,
    related_transaction_id: uuid.UUID | None = None,
) -> LoyaltyTransaction:
    if points == 0:
        raise ValueError("Loyalty transactions must change the balance")
    new_balance = customer.loyalty_balance + points
    if new_balance < 0:
        raise ValidationFailed(
            "The customer does not have enough loyalty points.",
            code="insufficient_points",
            details={"balance": customer.loyalty_balance, "requested": -points},
        )
    customer.loyalty_balance = new_balance
    entry = LoyaltyTransaction(
        restaurant_id=customer.restaurant_id,
        customer_id=customer.id,
        order_id=order_id,
        transaction_type=tx_type,
        points=points,
        balance_after=new_balance,
        reason=reason,
        created_by=actor_user_id,
        related_transaction_id=related_transaction_id,
    )
    db.add(entry)
    db.flush()
    return entry


def _order_tx(db: Session, order_id: uuid.UUID, tx_type: LoyaltyTransactionType) -> LoyaltyTransaction | None:
    return db.scalar(
        select(LoyaltyTransaction).where(
            LoyaltyTransaction.order_id == order_id, LoyaltyTransaction.transaction_type == tx_type
        )
    )


def _reversed_points(db: Session, related_id: uuid.UUID) -> int:
    return int(
        db.scalar(
            select(func.coalesce(func.sum(LoyaltyTransaction.points), 0)).where(
                LoyaltyTransaction.related_transaction_id == related_id,
                LoyaltyTransaction.transaction_type == LoyaltyTransactionType.REVERSAL,
            )
        )
        or 0
    )


def redeem_for_order(db: Session, order: Order, actor_user_id: uuid.UUID | None) -> None:
    if not order.loyalty_points_redeemed or order.customer_id is None:
        return
    if _order_tx(db, order.id, LoyaltyTransactionType.REDEEM) is not None:
        return
    customer = lock_customer(db, order.restaurant_id, order.customer_id)
    post(
        db,
        customer,
        LoyaltyTransactionType.REDEEM,
        -order.loyalty_points_redeemed,
        order_id=order.id,
        reason="Redeemed as order discount",
        actor_user_id=actor_user_id,
    )


def restore_redeemed(db: Session, order: Order, reason: str, actor_user_id: uuid.UUID | None) -> int:
    redeem = _order_tx(db, order.id, LoyaltyTransactionType.REDEEM)
    if redeem is None:
        return 0
    outstanding = -redeem.points - _reversed_points(db, redeem.id)
    if outstanding <= 0:
        return 0
    customer = lock_customer(db, order.restaurant_id, redeem.customer_id)
    post(
        db,
        customer,
        LoyaltyTransactionType.REVERSAL,
        outstanding,
        order_id=order.id,
        reason=reason,
        actor_user_id=actor_user_id,
        related_transaction_id=redeem.id,
    )
    return outstanding


def earn_for_order(db: Session, restaurant: Restaurant, order: Order, actor_user_id: uuid.UUID | None) -> int:
    if not restaurant.loyalty_enabled or order.customer_id is None:
        return 0
    if _order_tx(db, order.id, LoyaltyTransactionType.EARN) is not None:
        return 0
    points = loyalty_points_earned(order.total_minor, restaurant.loyalty_spend_per_point_minor)
    if points <= 0:
        return 0
    customer = lock_customer(db, order.restaurant_id, order.customer_id)
    post(
        db,
        customer,
        LoyaltyTransactionType.EARN,
        points,
        order_id=order.id,
        reason=f"Earned on order total {order.total_minor / 100:.2f}",
        actor_user_id=actor_user_id,
    )
    return points


def reverse_for_refund(db: Session, order: Order, actor_user_id: uuid.UUID | None) -> int:
    """Bring reversed points in line with the total refunded so far."""
    earn = _order_tx(db, order.id, LoyaltyTransactionType.EARN)
    if earn is None:
        return 0
    target = proportional_points(earn.points, order.amount_refunded_minor, order.amount_paid_minor)
    already = -_reversed_points(db, earn.id)
    delta = target - already
    if delta <= 0:
        return 0
    customer = lock_customer(db, order.restaurant_id, earn.customer_id)
    # Never push the balance below zero: if the customer already spent the
    # points, reverse what is available and record the shortfall in the reason.
    reversible = min(delta, customer.loyalty_balance)
    if reversible <= 0:
        return 0
    reason = "Reversed after refund"
    if reversible < delta:
        reason += f" ({delta - reversible} points already spent and not reversed)"
    post(
        db,
        customer,
        LoyaltyTransactionType.REVERSAL,
        -reversible,
        order_id=order.id,
        reason=reason,
        actor_user_id=actor_user_id,
        related_transaction_id=earn.id,
    )
    return reversible


def earned_for_order(db: Session, order_id: uuid.UUID) -> int | None:
    earn = _order_tx(db, order_id, LoyaltyTransactionType.EARN)
    return earn.points if earn else None
