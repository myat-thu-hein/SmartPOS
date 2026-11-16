"""Unit conversion for ingredient quantities.

Every ingredient has a base unit (g, ml or piece). Quantities entered in other
units are converted to the base unit before any calculation. Conversions
between dimensions (e.g. kg to ml) are never guessed: they raise an error.
Ingredient-specific pack units (tray, package, bottle...) can be defined per
ingredient with an explicit factor.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import ROUND_HALF_UP, Decimal

from app.core.errors import ValidationFailed
from app.models.enums import BaseUnit

QUANTUM = Decimal("0.001")

STANDARD_UNITS: dict[BaseUnit, dict[str, Decimal]] = {
    BaseUnit.GRAM: {"g": Decimal(1), "kg": Decimal(1000)},
    BaseUnit.MILLILITRE: {"ml": Decimal(1), "l": Decimal(1000)},
    BaseUnit.PIECE: {"piece": Decimal(1), "pcs": Decimal(1)},
}

_UNIT_DIMENSION = {unit: base for base, units in STANDARD_UNITS.items() for unit in units}
_DIMENSION_LABEL = {BaseUnit.GRAM: "mass", BaseUnit.MILLILITRE: "volume", BaseUnit.PIECE: "count"}


def quantize(value: Decimal) -> Decimal:
    return value.quantize(QUANTUM, rounding=ROUND_HALF_UP)


def normalise_unit(unit: str) -> str:
    return unit.strip().lower()


def to_base(
    quantity: Decimal, unit: str, base_unit: BaseUnit, custom_units: Mapping[str, Decimal] | None = None
) -> Decimal:
    """Convert `quantity` expressed in `unit` into the ingredient's base unit."""
    name = normalise_unit(unit)
    standard = STANDARD_UNITS[base_unit]
    if name in standard:
        return quantize(quantity * standard[name])
    custom = {normalise_unit(k): v for k, v in (custom_units or {}).items()}
    if name in custom:
        return quantize(quantity * custom[name])
    if name in _UNIT_DIMENSION:
        raise ValidationFailed(
            f"Cannot convert '{unit}' ({_DIMENSION_LABEL[_UNIT_DIMENSION[name]]}) into '{base_unit.value}' "
            f"({_DIMENSION_LABEL[base_unit]}). Define a pack unit for this ingredient if needed.",
            code="incompatible_unit",
        )
    raise ValidationFailed(
        f"Unknown unit '{unit}' for an ingredient measured in '{base_unit.value}'.", code="unknown_unit"
    )


def from_base(
    quantity: Decimal, unit: str, base_unit: BaseUnit, custom_units: Mapping[str, Decimal] | None = None
) -> Decimal:
    factor = to_base(Decimal(1), unit, base_unit, custom_units)
    return quantize(quantity / factor)


def allowed_units(base_unit: BaseUnit, custom_units: Mapping[str, Decimal] | None = None) -> list[str]:
    return list(STANDARD_UNITS[base_unit]) + sorted(normalise_unit(u) for u in (custom_units or {}))


def is_standard_unit(unit: str) -> bool:
    return normalise_unit(unit) in _UNIT_DIMENSION


def format_quantity(value: Decimal, unit: str) -> str:
    """Human-readable quantity in a base unit: 1500 g -> "1.5 kg", 2 pcs -> "2 pcs"."""
    if unit in ("g", "ml") and abs(value) >= 1000:
        return f"{value / 1000:,.2f}".rstrip("0").rstrip(".") + (" kg" if unit == "g" else " L")
    return f"{value:,.3f}".rstrip("0").rstrip(".") + f" {unit}"
