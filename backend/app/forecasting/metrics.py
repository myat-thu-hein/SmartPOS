"""Forecast accuracy metrics.

* MAE  - mean absolute error, in units sold. Always defined when there is data.
* RMSE - root mean squared error; penalises large misses more than MAE.
* MAPE - mean absolute percentage error. It is undefined when the actual value
  is zero (division by zero), so zero-actual points are excluded and counted
  separately. When every actual value is zero MAPE is reported as ``None``
  rather than a misleading number.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class MetricResult:
    points: int
    mae: float | None
    rmse: float | None
    mape: float | None
    mape_points: int
    zero_actual_points: int

    @property
    def note(self) -> str | None:
        if self.points == 0:
            return "No evaluation points were available."
        if self.mape is None:
            return "MAPE is undefined because every actual value was zero."
        if self.zero_actual_points:
            return f"MAPE excludes {self.zero_actual_points} point(s) where the actual value was zero."
        return None


def _validate(actual: Sequence[float], predicted: Sequence[float]) -> None:
    if len(actual) != len(predicted):
        raise ValueError("actual and predicted must have the same length")
    if any(math.isnan(v) for v in [*actual, *predicted]):
        raise ValueError("NaN values must be removed before computing metrics")


def mae(actual: Sequence[float], predicted: Sequence[float]) -> float | None:
    _validate(actual, predicted)
    if not actual:
        return None
    return sum(abs(a - p) for a, p in zip(actual, predicted, strict=True)) / len(actual)


def rmse(actual: Sequence[float], predicted: Sequence[float]) -> float | None:
    _validate(actual, predicted)
    if not actual:
        return None
    return math.sqrt(sum((a - p) ** 2 for a, p in zip(actual, predicted, strict=True)) / len(actual))


def mape(actual: Sequence[float], predicted: Sequence[float]) -> tuple[float | None, int, int]:
    """Return (MAPE in percent, points used, zero-actual points excluded)."""
    _validate(actual, predicted)
    pairs = [(a, p) for a, p in zip(actual, predicted, strict=True) if a != 0]
    zeros = len(actual) - len(pairs)
    if not pairs:
        return None, 0, zeros
    return sum(abs((a - p) / a) for a, p in pairs) / len(pairs) * 100, len(pairs), zeros


def evaluate(actual: Sequence[float], predicted: Sequence[float]) -> MetricResult:
    m, used, zeros = mape(actual, predicted)
    return MetricResult(
        points=len(actual),
        mae=mae(actual, predicted),
        rmse=rmse(actual, predicted),
        mape=m,
        mape_points=used,
        zero_actual_points=zeros,
    )
