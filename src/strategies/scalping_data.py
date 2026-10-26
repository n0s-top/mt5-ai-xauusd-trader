"""Prepare synchronized, fully closed M1/M5/M15 candles."""

import numpy as np
import pandas as pd


def prepare_scalping_data(
    df: pd.DataFrame,
    asof: pd.Timestamp,
):
    data = df.copy()

    if "time" in data.columns:
        data["time"] = pd.to_datetime(data["time"], utc=True)
        data = data.set_index("time")

    if not isinstance(data.index, pd.DatetimeIndex):
        raise ValueError("DatetimeIndex required")

    if data.index.tz is None:
        raise ValueError("DatetimeIndex must be timezone-aware (UTC)")

    data.index = data.index.tz_convert("UTC")
    data = data.sort_index()

    if data.index.has_duplicates:
        raise ValueError("Duplicate M1 timestamps")

    required = ["open", "high", "low", "close", "tick_volume"]

    if not set(required).issubset(data.columns):
        raise ValueError("Missing OHLCV columns")

    if data.index.hasnans or (data.index != data.index.floor("min")).any():
        raise ValueError("M1 timestamps must be valid minute openings")
    values = data[required].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("OHLCV must contain finite numbers")
    data[required] = values
    if (data[["open", "high", "low", "close"]] <= 0).any().any():
        raise ValueError("OHLC prices must be positive")
    if (data["tick_volume"] < 0).any():
        raise ValueError("Volume cannot be negative")
    if (data["high"] < data[["open", "close", "low"]].max(axis=1)).any() or (
        data["low"] > data[["open", "close"]].min(axis=1)
    ).any():
        raise ValueError("Invalid OHLC geometry")

    asof = pd.Timestamp(asof)

    if asof.tzinfo is None:
        raise ValueError("asof must be timezone-aware")

    asof = asof.tz_convert("UTC")

    # MT5 bar timestamps indicate bar opening time.
    # Only retain M1 candles that have fully closed.
    m1 = data.loc[data.index + pd.Timedelta(minutes=1) <= asof].copy()

    def aggregate(freq: str):
        bars = m1.resample(freq, label="left", closed="left").agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "tick_volume": "sum",
            }
        )

        counts = m1["close"].resample(freq, label="left", closed="left").count()

        expected = int(pd.Timedelta(freq) / pd.Timedelta(minutes=1))

        bars = bars.loc[counts == expected]

        # Remove any higher-timeframe candle not yet closed.
        bars = bars.loc[bars.index + pd.Timedelta(freq) <= asof]

        return bars.dropna()

    return {
        "M1": m1,
        "M5": aggregate("5min"),
        "M15": aggregate("15min"),
    }
