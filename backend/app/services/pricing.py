"""Authoritative order pricing (pure functions, integer minor units).

The browser never supplies prices or totals: everything is recomputed here
from catalog prices and restaurant settings.

Calculation order
-----------------
1. ``subtotal``         = sum(unit price x quantity) where unit price = base price + modifier deltas
2. ``discount``         = PERCENT: round(subtotal x rate) / FIXED: min(value, subtotal)
3. ``loyalty_discount`` = redeemed points x point value (cannot exceed what is left)
4. ``net``              = subtotal - discount - loyalty_discount
5. ``service_charge``   = round(net x service rate)   (0 for takeaway when configured dine-in only)
6. tax
   * prices exclude tax: tax = round((net + taxable service) x rate); total = net + service + tax
   * prices include tax: total = net + service; tax (already included) =
     round((net + taxable service) x rate / (1 + rate))

All rounding is "round half up" to the nearest minor unit (satang).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.models.enums import DiscountKind

BPS = 10_000


def round_half_up(value: Decimal) -> int:
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def percent_of(amount: int, bps: int) -> int:
    return round_half_up(Decimal(amount) * Decimal(bps) / Decimal(BPS))


@dataclass(frozen=True)
class PricingSettings:
    tax_rate_bps: int
    prices_include_tax: bool
    service_charge_bps: int
    service_charge_taxable: bool


@dataclass(frozen=True)
class DiscountSpec:
    kind: DiscountKind
    value: int  # bps for PERCENT, minor units for FIXED


@dataclass(frozen=True)
class PricingResult:
    subtotal_minor: int
    discount_minor: int
    loyalty_discount_minor: int
    net_minor: int
    service_charge_minor: int
    tax_minor: int
    total_minor: int
    prices_include_tax: bool


def line_total(unit_price_minor: int, quantity: int) -> int:
    if quantity <= 0:
        raise ValueError("Quantity must be positive")
    return unit_price_minor * quantity


def discount_amount(subtotal_minor: int, discount: DiscountSpec | None) -> int:
    if discount is None or subtotal_minor <= 0:
        return 0
    if discount.kind == DiscountKind.PERCENT:
        if not 0 <= discount.value <= BPS:
            raise ValueError("Percentage discount must be between 0 and 10000 bps")
        return min(percent_of(subtotal_minor, discount.value), subtotal_minor)
    if discount.value < 0:
        raise ValueError("Fixed discount must not be negative")
    return min(discount.value, subtotal_minor)


def calculate(
    line_totals: list[int],
    settings: PricingSettings,
    discount: DiscountSpec | None = None,
    loyalty_discount_minor: int = 0,
) -> PricingResult:
    if any(t < 0 for t in line_totals):
        raise ValueError("Line totals must not be negative")
    subtotal = sum(line_totals)
    disc = discount_amount(subtotal, discount)
    after_discount = subtotal - disc
    loyalty = max(0, min(loyalty_discount_minor, after_discount))
    net = after_discount - loyalty
    service = percent_of(net, settings.service_charge_bps)
    taxable = net + (service if settings.service_charge_taxable else 0)
    rate = Decimal(settings.tax_rate_bps)
    if settings.prices_include_tax:
        tax = round_half_up(Decimal(taxable) * rate / (Decimal(BPS) + rate)) if rate else 0
        total = net + service
    else:
        tax = round_half_up(Decimal(taxable) * rate / Decimal(BPS))
        total = net + service + tax
    return PricingResult(
        subtotal_minor=subtotal,
        discount_minor=disc,
        loyalty_discount_minor=loyalty,
        net_minor=net,
        service_charge_minor=service,
        tax_minor=tax,
        total_minor=total,
        prices_include_tax=settings.prices_include_tax,
    )


def loyalty_points_earned(eligible_minor: int, spend_per_point_minor: int) -> int:
    """Whole points earned for an eligible amount (fractions are not carried over)."""
    if spend_per_point_minor <= 0 or eligible_minor <= 0:
        return 0
    return eligible_minor // spend_per_point_minor


def proportional_points(points: int, part_minor: int, whole_minor: int) -> int:
    """Points corresponding to `part` of `whole`, rounded down."""
    if whole_minor <= 0 or points <= 0:
        return 0
    return min(points, points * part_minor // whole_minor)
