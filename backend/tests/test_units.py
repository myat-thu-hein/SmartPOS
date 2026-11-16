"""Unit conversion (pure unit tests)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.errors import ValidationFailed
from app.models.enums import BaseUnit
from app.services.units import allowed_units, from_base, to_base


@pytest.mark.parametrize(
    ("qty", "unit", "base", "expected"),
    [
        ("1", "kg", BaseUnit.GRAM, "1000"),
        ("0.25", "KG", BaseUnit.GRAM, "250"),
        ("100", "g", BaseUnit.GRAM, "100"),
        ("1.5", "L", BaseUnit.MILLILITRE, "1500"),
        ("30", "ml", BaseUnit.MILLILITRE, "30"),
        ("3", "piece", BaseUnit.PIECE, "3"),
        ("0.0004", "kg", BaseUnit.GRAM, "0.4"),
    ],
)
def test_standard_conversions(qty: str, unit: str, base: BaseUnit, expected: str) -> None:
    assert to_base(Decimal(qty), unit, base) == Decimal(expected)


def test_custom_pack_units() -> None:
    assert to_base(Decimal(2), "tray", BaseUnit.PIECE, {"tray": Decimal(30)}) == Decimal(60)
    assert from_base(Decimal(45), "tray", BaseUnit.PIECE, {"tray": Decimal(30)}) == Decimal("1.5")
    assert "tray" in allowed_units(BaseUnit.PIECE, {"Tray": Decimal(30)})


@pytest.mark.parametrize(
    ("unit", "base"),
    [("kg", BaseUnit.MILLILITRE), ("ml", BaseUnit.GRAM), ("piece", BaseUnit.GRAM), ("l", BaseUnit.PIECE)],
)
def test_incompatible_units_are_rejected(unit: str, base: BaseUnit) -> None:
    with pytest.raises(ValidationFailed) as exc:
        to_base(Decimal(1), unit, base)
    assert exc.value.code == "incompatible_unit"


def test_unknown_unit_is_rejected() -> None:
    with pytest.raises(ValidationFailed) as exc:
        to_base(Decimal(1), "bucket", BaseUnit.GRAM)
    assert exc.value.code == "unknown_unit"
