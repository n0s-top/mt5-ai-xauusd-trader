"""Validate closed higher-timeframe data and describe context, not entry signals."""

import math

import numpy as np
import pandas as pd


def analyze_context(rates, minutes, now, indicators):
    if rates is None or len(rates) < 220:
        raise ValueError("Insufficient higher-timeframe history")
    frame = pd.DataFrame(rates)
    required = ["open", "high", "low", "close"]
    if not {"time", *required}.issubset(frame.columns):
        raise ValueError("Missing higher-timeframe OHLC/timestamps")
    frame["time"] = pd.to_datetime(frame["time"], unit="s", utc=True)
    frame = frame.set_index("time")
    if frame.index.hasnans or frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
        raise ValueError("Invalid higher-timeframe timestamps")
    interval = pd.Timedelta(minutes=minutes)
    if (frame.index != frame.index.floor(f"{minutes}min")).any():
        raise ValueError("Unaligned higher-timeframe bars")
    prices = frame[required].to_numpy(dtype=float)
    if not np.isfinite(prices).all() or (prices <= 0).any():
        raise ValueError("Invalid higher-timeframe prices")
    if (
        (frame["high"] < frame[required].max(axis=1)) | (frame["low"] > frame[required].min(axis=1))
    ).any():
        raise ValueError("Invalid higher-timeframe OHLC geometry")
    frame = frame.loc[frame.index + interval <= pd.Timestamp(now)]
    if (
        len(frame) < 220
        or not pd.Timedelta(0) <= pd.Timestamp(now) - (frame.index[-1] + interval) < interval
    ):
        raise ValueError("Stale higher-timeframe candles")
    if not (frame.index[-3:].to_series().diff().dropna() == interval).all():
        raise ValueError("Recent higher-timeframe candle gap")
    last = indicators(frame).iloc[-1]
    if not all(math.isfinite(last[key]) for key in ("close", "ema21", "ema200")):
        raise ValueError("Higher-timeframe indicators unavailable")
    state = "WAIT"
    if last["close"] > last["ema21"] > last["ema200"]:
        state = "BUY"
    elif last["close"] < last["ema21"] < last["ema200"]:
        state = "SELL"
    return {
        "state": state,
        "close": float(last["close"]),
        "ema21": float(last["ema21"]),
        "ema200": float(last["ema200"]),
        "range_low": float(frame["low"].iloc[-20:].min()),
        "range_high": float(frame["high"].iloc[-20:].max()),
        "candle_time_utc": frame.index[-1].isoformat(),
        "bars": len(frame),
    }
