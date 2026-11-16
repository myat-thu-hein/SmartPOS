"""Shared Pydantic field types."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from pydantic import Field, PlainSerializer, StringConstraints

# Quantities are exact decimals internally but are serialised as JSON numbers
# for convenient display in the browser.
Qty = Annotated[Decimal, PlainSerializer(lambda v: float(v), return_type=float, when_used="json")]
OptionalQty = Annotated[
    Decimal | None,
    PlainSerializer(lambda v: None if v is None else float(v), return_type=float | None, when_used="json"),
]
PositiveQtyIn = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=3)]
NonNegativeQtyIn = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=3)]

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=5000)]
IdempotencyKey = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_\-:.]+$")
]
