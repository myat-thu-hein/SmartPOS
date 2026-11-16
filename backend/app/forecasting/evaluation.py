"""Rolling-origin (time-ordered) backtesting.

For each origin in the evaluation window the model is fitted only on data up
to and including that origin, then asked to predict the following days. Errors
are measured against what actually happened. Because every fit uses past data
only, the evaluation cannot leak future information.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np

from app.forecasting import models
from app.forecasting.metrics import MetricResult, evaluate


@dataclass(frozen=True)
class Series:
    key: str
    start: date
    values: np.ndarray


def backtest(model_name: str, series: list[Series], horizon: int, eval_origins: int = 14) -> MetricResult:
    actual: list[float] = []
    predicted: list[float] = []
    for s in series:
        n = len(s.values)
        first_origin = max(0, n - 1 - eval_origins)
        for origin in range(first_origin, n - 1):
            history = s.values[: origin + 1]
            if len(models.observed(history)) < models.MODEL_CLASSES[model_name].min_history:
                continue
            horizons = [h for h in range(1, horizon + 1) if origin + h < n and not np.isnan(s.values[origin + h])]
            if not horizons:
                continue
            model = models.create(model_name).fit(s.start, history)
            preds = model.predict(horizons)
            actual.extend(float(s.values[origin + h]) for h in horizons)
            predicted.extend(float(p) for p in preds)
    return evaluate(actual, predicted)
