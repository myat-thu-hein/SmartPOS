"""Printable receipt data built from order snapshots."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import RestaurantContext
from app.models import Customer, DiningTable, User
from app.models.enums import DiscountKind
from app.schemas.orders import Receipt, ReceiptLine, ReceiptPayment
from app.services.loyalty import earned_for_order
from app.services.orders import load_order
from app.services.tables import display_number

SIMULATED_NOTICE = (
    "Payments marked (simulated) were recorded by staff; SmartPOS did not receive confirmation "
    "from a payment provider. / การชำระเงินที่ระบุว่า (จำลอง) บันทึกโดยพนักงาน"
)


def build_receipt(db: Session, ctx: RestaurantContext, order_id: uuid.UUID) -> Receipt:
    order = load_order(db, ctx, order_id)
    restaurant = ctx.restaurant
    lines = []
    for item in order.items:
        lines.append(
            ReceiptLine(
                name=item.product_name,
                quantity=item.quantity,
                unit_price_minor=item.unit_price_minor,
                line_total_minor=item.line_total_minor,
                modifiers=[
                    f"{m.option_name}" + (f" (+{m.price_delta_minor / 100:.2f})" if m.price_delta_minor else "")
                    for m in item.modifiers
                ],
                notes=item.notes,
            )
        )
    discount_label = None
    if order.discount_kind is not None:
        discount_label = order.discount_name or "Discount"
        if order.discount_kind == DiscountKind.PERCENT and order.discount_value:
            discount_label += f" ({order.discount_value / 100:g}%)"
    table_name = db.scalar(select(DiningTable.name).where(DiningTable.id == order.table_id)) if order.table_id else None
    customer_name = (
        db.scalar(select(Customer.name).where(Customer.id == order.customer_id)) if order.customer_id else None
    )
    cashier = db.scalar(select(User.full_name).where(User.id == order.created_by)) if order.created_by else None
    payments = [
        ReceiptPayment(
            method_name=p.method_name + (" (simulated)" if p.is_simulated else ""),
            amount_minor=p.amount_minor,
            amount_tendered_minor=p.amount_tendered_minor,
            change_minor=p.change_minor,
            is_simulated=p.is_simulated,
            status=p.status.value,
            reference=p.reference,
            created_at=p.created_at,
        )
        for p in order.payments
    ]
    return Receipt(
        restaurant_name=restaurant.name,
        legal_name=restaurant.legal_name,
        branch_name=restaurant.branch_name,
        tax_id=restaurant.tax_id,
        address=restaurant.address,
        phone=restaurant.phone,
        header=restaurant.receipt_header,
        footer=restaurant.receipt_footer,
        currency=restaurant.currency,
        timezone=restaurant.timezone,
        order_id=order.id,
        display_number=display_number(restaurant.order_number_prefix, order.order_number),
        order_type=order.order_type,
        table_name=table_name,
        customer_name=customer_name,
        cashier_name=cashier,
        created_at=order.created_at,
        paid_at=order.paid_at,
        lines=lines,
        subtotal_minor=order.subtotal_minor,
        discount_minor=order.discount_minor,
        discount_label=discount_label,
        loyalty_discount_minor=order.loyalty_discount_minor,
        loyalty_points_redeemed=order.loyalty_points_redeemed,
        service_charge_minor=order.service_charge_minor,
        service_charge_bps=order.service_charge_bps,
        tax_minor=order.tax_minor,
        tax_rate_bps=order.tax_rate_bps,
        tax_label=restaurant.tax_label,
        prices_include_tax=order.prices_include_tax,
        total_minor=order.total_minor,
        amount_paid_minor=order.amount_paid_minor,
        amount_refunded_minor=order.amount_refunded_minor,
        balance_due_minor=max(order.total_minor - order.amount_paid_minor, 0),
        payment_status=order.payment_status,
        status=order.status,
        payments=payments,
        loyalty_points_earned=earned_for_order(db, order.id),
        simulated_payment_notice=SIMULATED_NOTICE if any(p.is_simulated for p in order.payments) else None,
    )
