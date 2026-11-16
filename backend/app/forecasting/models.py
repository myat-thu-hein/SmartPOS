"""Demand forecasting models behind one interface.

Each model is fitted on a single product's daily history (``values`` are
quantities per day; ``NaN`` marks a day when the restaurant had no sales at all
and is treated as "closed", not as zero demand) and predicts horizons
``h = 1..H`` days after the last history day.

Stage 1 baselines: moving average, seasonal naive, day-of-week average.
Stage 2: a ridge regression on calendar and lag features (scikit-learn).
Which one is "best" is decided by measured backtests, never assumed.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np


def observed(values: np.ndarray) -> np.ndarray:
    return values[~np.isnan(values)]


class Forecaster(ABC):
    name: str = ""
    version: str = "1"
    label: str = ""
    description: str = ""
    min_history: int = 1  # observed days required

    def __init__(self) -> None:
        self.start: date | None = None
        self.values: np.ndarray = np.array([])

    def fit(self, start: date, values: np.ndarray) -> Forecaster:
        if len(observed(values)) < self.min_history:
            raise ValueError(f"{self.name} needs at least {self.min_history} observed days")
        self.start = start
        self.values = values.astype(float)
        self._fit()
        return self

    def _fit(self) -> None:  # noqa: B027 - optional hook
        pass

    @property
    def end(self) -> date:
        assert self.start is not None
        return self.start + timedelta(days=len(self.values) - 1)

    def predict(self, horizons: list[int]) -> np.ndarray:
        return np.clip(np.array([self._predict_one(h) for h in horizons], dtype=float), 0, None)

    @abstractmethod
    def _predict_one(self, h: int) -> float: ...

    def _recent_mean(self, window: int) -> float:
        recent = observed(self.values)[-window:]
        return float(recent.mean()) if len(recent) else 0.0


class MovingAverage(Forecaster):
    name = "moving_average"
    label = "7-day moving average"
    description = "Average of the last 7 trading days. Robust with very little history."
    min_history = 1

    def __init__(self, window: int = 7) -> None:
        super().__init__()
        self.window = window

    def _predict_one(self, h: int) -> float:
        return self._recent_mean(self.window)


class SeasonalNaive(Forecaster):
    name = "seasonal_naive"
    label = "Seasonal naive (same weekday last week)"
    description = "Repeats the most recent sales on the same weekday."
    min_history = 7

    def _predict_one(self, h: int) -> float:
        n = len(self.values)
        target = n - 1 + h
        k = math.ceil(h / 7)
        while target - 7 * k >= 0:
            v = self.values[target - 7 * k]
            if not np.isnan(v):
                return float(v)
            k += 1
        return self._recent_mean(7)


class DayOfWeekAverage(Forecaster):
    name = "dow_average"
    label = "Day-of-week average (last 4 weeks)"
    description = "Average sales of the same weekday over the last four weeks."
    min_history = 14

    def __init__(self, weeks: int = 4) -> None:
        super().__init__()
        self.weeks = weeks

    def _predict_one(self, h: int) -> float:
        n = len(self.values)
        target = n - 1 + h
        samples = []
        k = math.ceil(h / 7)
        while target - 7 * k >= 0 and len(samples) < self.weeks:
            v = self.values[target - 7 * k]
            if not np.isnan(v):
                samples.append(v)
            k += 1
        return float(np.mean(samples)) if samples else self._recent_mean(28)


@dataclass(frozen=True)
class RidgeFit:
    """Ridge regression with an unpenalised intercept, solved in closed form.

    Minimises ||y - Xw - b||² + alpha·||w||²: centre X and y, solve
    (XcᵀXc + alpha·I) w = Xcᵀyc, then b = mean(y) - mean(X)·w. This is what
    scikit-learn's Ridge(alpha) computes, without the scikit-learn/SciPy
    dependency (about 190 MB of the deployment bundle).
    """

    coef: np.ndarray
    intercept: float

    @classmethod
    def fit(cls, x: np.ndarray, y: np.ndarray, alpha: float = 1.0) -> RidgeFit:
        x_mean, y_mean = x.mean(axis=0), float(y.mean())
        xc, yc = x - x_mean, y - y_mean
        gram = xc.T @ xc + alpha * np.eye(x.shape[1])
        coef = np.linalg.solve(gram, xc.T @ yc)
        return cls(coef=coef, intercept=y_mean - float(x_mean @ coef))

    def predict(self, x: np.ndarray) -> np.ndarray:
        return x @ self.coef + self.intercept


class RidgeLagRegression(Forecaster):
    """Direct multi-horizon ridge regression.

    Features for a target day ``t = origin + h``: weekday one-hot of t, the
    7- and 28-day means at the origin, the latest same-weekday value at or
    before the origin, and the horizon. Training samples are built only from
    data inside the fitted history, so there is no look-ahead.
    """

    name = "ridge_lags"
    version = "1"
    label = "Ridge regression (weekday + lag features)"
    description = "Machine-learning model (ridge regression) using weekday patterns and recent demand levels."
    min_history = 35
    max_train_horizon = 7

    def __init__(self, alpha: float = 1.0) -> None:
        super().__init__()
        self.alpha = alpha
        self.model: RidgeFit | None = None
        self._fallback = 0.0

    def _features(self, origin: int, h: int) -> list[float] | None:
        assert self.start is not None
        hist = self.values[: origin + 1]
        obs = observed(hist)
        if len(obs) < 7:
            return None
        ma7 = float(obs[-7:].mean())
        ma28 = float(obs[-28:].mean())
        target = origin + h
        same = None
        k = math.ceil(h / 7)
        while target - 7 * k >= 0:
            v = self.values[target - 7 * k]
            if not np.isnan(v):
                same = float(v)
                break
            k += 1
        weekday = (self.start + timedelta(days=target)).weekday()
        one_hot = [1.0 if weekday == d else 0.0 for d in range(7)]
        return [*one_hot, ma7, ma28, ma7 if same is None else same, h / 7]

    def _fit(self) -> None:
        rows, targets = [], []
        n = len(self.values)
        for origin in range(27, n - 1):
            for h in range(1, self.max_train_horizon + 1):
                t = origin + h
                if t >= n or np.isnan(self.values[t]):
                    continue
                feats = self._features(origin, h)
                if feats is not None:
                    rows.append(feats)
                    targets.append(self.values[t])
        self._fallback = self._recent_mean(7)
        if len(rows) < 10:
            self.model = None
            return
        self.model = RidgeFit.fit(np.array(rows, dtype=float), np.array(targets, dtype=float), self.alpha)

    def _predict_one(self, h: int) -> float:
        if self.model is None:
            return self._fallback
        feats = self._features(len(self.values) - 1, h)
        if feats is None:
            return self._fallback
        return float(self.model.predict(np.array([feats]))[0])


MODEL_CLASSES: dict[str, type[Forecaster]] = {
    cls.name: cls for cls in (MovingAverage, SeasonalNaive, DayOfWeekAverage, RidgeLagRegression)
}
# Simpler models first: they win ties during automatic selection.
SELECTION_ORDER = ["moving_average", "seasonal_naive", "dow_average", "ridge_lags"]
FALLBACK_CHAIN = ["dow_average", "seasonal_naive", "moving_average"]


def create(name: str) -> Forecaster:
    if name not in MODEL_CLASSES:
        raise KeyError(name)
    return MODEL_CLASSES[name]()
