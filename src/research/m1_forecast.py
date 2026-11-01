"""Causal five-minute research forecasts; no orders and no win-rate claims."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

FEATURES = ("return1", "return3", "return5", "body", "range", "location",
            "volatility", "m5_trend", "m15_trend")
CLASSES = ("DOWN", "FLAT", "UP")


def forecast_features(bars):
    if (not isinstance(bars.index, pd.DatetimeIndex) or bars.index.tz is None
            or bars.index.has_duplicates or not bars.index.is_monotonic_increasing
            or bars.index.hasnans or (bars.index != bars.index.floor("min")).any()):
        raise ValueError("Unique chronological timezone-aware minute candles required")
    prices = bars[["open", "high", "low", "close"]].astype(float)
    if not np.isfinite(prices.to_numpy()).all() or (prices <= 0).any().any():
        raise ValueError("Invalid OHLC prices")
    if ((prices.high < prices.max(axis=1)) | (prices.low > prices.min(axis=1))).any():
        raise ValueError("Invalid OHLC geometry")
    close = prices.close
    tr = pd.concat([prices.high - prices.low, (prices.high - close.shift()).abs(),
                    (prices.low - close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean().replace(0, np.nan)
    result = pd.DataFrame(index=bars.index)
    for lag in (1, 3, 5):
        result[f"return{lag}"] = close.diff(lag) / atr
    result["body"] = (close - prices.open) / atr
    result["range"] = (prices.high - prices.low) / atr
    result["location"] = (close - prices.low) / (prices.high - prices.low).replace(0, np.nan)
    result["volatility"] = atr / atr.rolling(60, min_periods=60).median()
    decision = bars.index + pd.Timedelta(minutes=1)
    for minutes in (5, 15):
        grouped = close.resample(f"{minutes}min", closed="left", label="left")
        values = grouped.last().loc[grouped.count() == minutes]
        fast = values.ewm(span=20, adjust=False, min_periods=20).mean()
        slow = values.ewm(span=50, adjust=False, min_periods=50).mean()
        context = pd.DataFrame({"trend": (fast - slow).to_numpy(), "closed": values.index + pd.Timedelta(minutes=minutes)},
                               index=values.index + pd.Timedelta(minutes=minutes))
        aligned = context.reindex(decision, method="ffill")
        result[f"m{minutes}_trend"] = aligned.trend.to_numpy() / atr.to_numpy()
        ages = decision - pd.DatetimeIndex(aligned.closed)
        result.loc[(ages < pd.Timedelta(0)) | (ages >= pd.Timedelta(minutes=minutes)), f"m{minutes}_trend"] = np.nan
    contiguous = bars.index.to_series().diff().eq(pd.Timedelta(minutes=1)).rolling(60).sum().eq(60)
    result["atr"] = atr
    return result.loc[contiguous].replace([np.inf, -np.inf], np.nan).dropna()


def forecast_labels(bars, features, horizon=5, cost=.344):
    future = bars.close.shift(-horizon)
    elapsed = bars.index.to_series().shift(-horizon) - bars.index.to_series()
    valid = elapsed.eq(pd.Timedelta(minutes=horizon))
    movement = future - bars.close
    threshold = np.maximum(.25 * features.atr, cost)
    movement = movement.reindex(features.index)
    labels = pd.Series(np.where(movement > threshold, 2, np.where(movement < -threshold, 0, 1)),
                       index=features.index, dtype=int)
    return labels.loc[valid.reindex(features.index, fill_value=False)]


def predict_probabilities(model, features):
    if model.get("features") != list(FEATURES) or model.get("classes") != list(CLASSES):
        raise ValueError("Unsupported forecast schema")
    mean, scale = np.asarray(model["mean"]), np.asarray(model["scale"])
    coefficient, intercept = np.asarray(model["coef"]), np.asarray(model["intercept"])
    temperature = float(model["temperature"])
    if (mean.shape != (len(FEATURES),) or scale.shape != mean.shape
            or coefficient.shape != (3, len(FEATURES)) or intercept.shape != (3,)
            or not all(np.isfinite(v).all() for v in (mean, scale, coefficient, intercept))
            or (scale <= 0).any() or not np.isfinite(temperature) or temperature <= 0):
        raise ValueError("Invalid forecast model parameters")
    values = features.loc[:, FEATURES].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("Nonfinite forecast features")
    logits = ((values - mean) / scale @ coefficient.T + intercept) / temperature
    logits -= logits.max(axis=1, keepdims=True)
    weights = np.exp(logits)
    return weights / weights.sum(axis=1, keepdims=True)


def forecast_snapshot(path, bars, symbol):
    model = json.loads(Path(path).read_text(encoding="utf-8"))
    if symbol not in model["allowed_symbols"] or model.get("horizon_minutes") != 5:
        raise ValueError("Model not validated for this symbol/horizon")
    features = forecast_features(bars)
    if features.empty or features.index[-1] != bars.index[-1]:
        raise ValueError("Latest candles cannot support a fresh forecast")
    probability = predict_probabilities(model, features.iloc[-1:])[0]
    return dict(horizon_minutes=5, probabilities=dict(zip(CLASSES, map(float, probability))),
                direction=CLASSES[int(probability.argmax())],
                movement_threshold_price=float(max(.25 * features.atr.iloc[-1], model["label_cost_price"])),
                validation_status=model["validation_status"],
                note="Model direction probabilities, not trade win probability; research only")
