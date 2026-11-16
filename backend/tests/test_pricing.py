"""Pricing engine (pure unit tests)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.models.enums import DiscountKind
from app.services.pricing import (
    DiscountSpec,
    PricingSettings,
    calculate,
    discount_amount,
    loyalty_points_earned,
    percent_of,
    proportional_points,
    round_half_up,
)

EXCLUSIVE = PricingSettings(
    tax_rate_bps=700, prices_include_tax=False, service_charge_bps=1000, service_charge_taxable=True
)
INCLUSIVE = PricingSettings(
    tax_rate_bps=700, prices_include_tax=True, service_charge_bps=0, service_charge_taxable=True
)


def test_round_half_up() -> None:
    assert round_half_up(Decimal("0.5")) == 1
    assert round_half_up(Decimal("1.49")) == 1
    assert round_half_up(Decimal("2.5")) == 3
    assert percent_of(1050, 700) == 74  # 73.5 -> 74


def test_exclusive_tax_with_service_charge() -> None:
    # 2 x 120.00 + 1 x 60.00 = 300.00; service 10% = 30.00; VAT 7% on 330.00 = 23.10
    result = calculate([24000, 6000], EXCLUSIVE)
    assert result.subtotal_minor == 30000
    assert result.service_charge_minor == 3000
    assert result.tax_minor == 2310
    assert result.total_minor == 35310


def test_service_charge_not_taxable() -> None:
    settings = PricingSettings(700, False, 1000, service_charge_taxable=False)
    result = calculate([30000], settings)
    assert result.tax_minor == 2100
    assert result.total_minor == 30000 + 3000 + 2100


def test_inclusive_tax_is_extracted_not_added() -> None:
    # Menu price 107.00 includes 7% VAT of 7.00.
    result = calculate([10700], INCLUSIVE)
    assert result.total_minor == 10700
    assert result.tax_minor == 700


def test_inclusive_tax_with_service_charge() -> None:
    settings = PricingSettings(700, True, 1000, True)
    result = calculate([10700], settings)
    assert result.service_charge_minor == 1070
    assert result.total_minor == 11770
    assert result.tax_minor == round_half_up(Decimal(11770) * 700 / 10700)


def test_percent_discount_applies_before_service_and_tax() -> None:
    result = calculate([30000], EXCLUSIVE, DiscountSpec(DiscountKind.PERCENT, 1000))
    assert result.discount_minor == 3000
    assert result.net_minor == 27000
    assert result.service_charge_minor == 2700
    assert result.tax_minor == round_half_up(Decimal(29700) * 7 / 100)


def test_fixed_discount_is_capped_at_subtotal() -> None:
    assert discount_amount(5000, DiscountSpec(DiscountKind.FIXED, 8000)) == 5000
    result = calculate([5000], EXCLUSIVE, DiscountSpec(DiscountKind.FIXED, 8000))
    assert result.total_minor == 0


def test_loyalty_discount_is_capped() -> None:
    result = calculate([5000], INCLUSIVE, DiscountSpec(DiscountKind.FIXED, 1000), loyalty_discount_minor=9999)
    assert result.loyalty_discount_minor == 4000
    assert result.total_minor == 0


def test_invalid_inputs() -> None:
    with pytest.raises(ValueError):
        calculate([-1], EXCLUSIVE)
    with pytest.raises(ValueError):
        discount_amount(100, DiscountSpec(DiscountKind.PERCENT, 10001))


def test_zero_tax_rate() -> None:
    result = calculate([12345], PricingSettings(0, True, 0, True))
    assert result.tax_minor == 0 and result.total_minor == 12345


def test_loyalty_points_calculations() -> None:
    assert loyalty_points_earned(12000, 2500) == 4
    assert loyalty_points_earned(2499, 2500) == 0
    assert loyalty_points_earned(0, 2500) == 0
    assert proportional_points(10, 5000, 10000) == 5
    assert proportional_points(10, 3333, 10000) == 3
    assert proportional_points(10, 10000, 10000) == 10
    assert proportional_points(0, 10, 10) == 0
