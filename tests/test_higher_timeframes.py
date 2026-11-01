import numpy as np
import pandas as pd
import pytest

from src.strategies.higher_timeframes import analyze_context


def bars(minutes=60):
    index = pd.date_range(end="2026-10-29T07:00:00Z", periods=300, freq=f"{minutes}min")
    return pd.DataFrame(
        {
            "time": index.as_unit("s").asi8,
            "open": 2000.0,
            "high": 2002.0,
            "low": 1998.0,
            "close": 2001.0,
        }
    )


@pytest.mark.parametrize("direction", [1, -1])
def test_context_and_closed_range(direction):
    context = analyze_context(
        bars(),
        60,
        pd.Timestamp("2026-10-29T08:10:00Z"),
        lambda frame: frame.assign(ema21=2001 - direction, ema200=2001 - 2 * direction),
    )
    assert context["state"] == ("BUY" if direction == 1 else "SELL")
    assert context["range_low"] == 1998
    assert context["range_high"] == 2002


@pytest.mark.parametrize("corruption", ["stale", "gap", "geometry", "nan", "duplicate"])
def test_corrupt_context_is_rejected(corruption):
    data = bars()
    now = pd.Timestamp("2026-10-29T08:10:00Z")
    if corruption == "stale":
        data = data.iloc[:-1]
    elif corruption == "gap":
        data = data.drop(data.index[-2])
    elif corruption == "geometry":
        data.loc[data.index[-1], "high"] = 1000
    elif corruption == "nan":
        data.loc[data.index[-1], "close"] = np.nan
    else:
        data.loc[data.index[-1], "time"] = data["time"].iloc[-2]
    with pytest.raises(ValueError):
        analyze_context(data, 60, now, lambda frame: frame.assign(ema21=2000, ema200=1999))


def test_forming_candle_is_excluded():
    data = bars()
    now = pd.Timestamp("2026-10-29T07:10:00Z")
    context = analyze_context(data, 60, now, lambda frame: frame.assign(ema21=2000, ema200=1999))
    assert context["bars"] == 299
    assert context["candle_time_utc"] == "2026-10-29T06:00:00+00:00"


def test_h4_closed_history_is_supported():
    data = bars(240)
    index = pd.date_range(end="2026-10-29T04:00:00Z", periods=300, freq="4h")
    data["time"] = index.as_unit("s").asi8
    context = analyze_context(
        data,
        240,
        pd.Timestamp("2026-10-29T09:00:00Z"),
        lambda frame: frame.assign(ema21=2000, ema200=1999),
    )
    assert context["state"] == "BUY"
    assert context["candle_time_utc"] == "2026-10-29T04:00:00+00:00"
