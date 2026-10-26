"""Regression tests for closed-candle preparation and scalper safety gates."""

import numpy as np
import pandas as pd
import pytest

from src.strategies.scalping_data import prepare_scalping_data
from src.strategies.xauusd_m1_scalper import XAUUSDM1Scalper


def candles(n=3300):
    index = pd.date_range("2026-10-20", periods=n, freq="min", tz="UTC")
    return pd.DataFrame(
        {"open": 2000.0, "high": 2002.0, "low": 1998.0, "close": 2001.0, "tick_volume": 100.0},
        index=index,
    )


def test_excludes_forming_candle_and_incomplete_higher_timeframes():
    frame = candles(3301)
    result = prepare_scalping_data(frame, frame.index[-1] + pd.Timedelta(seconds=30))
    assert len(result["M1"]) == 3300
    assert len(result["M15"]) == 220
    damaged = frame.drop(frame.index[-3])
    result = prepare_scalping_data(damaged, frame.index[-1] + pd.Timedelta(seconds=30))
    assert len(result["M15"]) == 219


@pytest.mark.parametrize(
    "column,value", [("close", np.inf), ("low", 2005.0), ("tick_volume", -1), ("open", 0.0)]
)
def test_rejects_corrupt_market_data(column, value):
    frame = candles(30)
    frame.loc[frame.index[-1], column] = value
    with pytest.raises(ValueError):
        prepare_scalping_data(frame, frame.index[-1] + pd.Timedelta(minutes=1))


def setup_signal(direction=1):
    frame = candles()
    data = prepare_scalping_data(frame, frame.index[-1] + pd.Timedelta(minutes=1))
    for item in data.values():
        item["ema9"] = 2000.0 + direction
        item["ema21"] = 2000.0
        item["ema200"] = 2001.0 - direction
        item["rsi"] = 50.0 + direction * 10
        item["adx"] = 30.0
        item["atr"] = 2.0
    m1 = data["M1"]
    m1.loc[m1.index[-2], "close"] = 2000.0
    m1.loc[m1.index[-1], "close"] = 2000.0 + direction
    return data


@pytest.mark.parametrize("direction", [1, -1])
def test_direction_and_structural_stop(monkeypatch, direction):
    data = setup_signal(direction)
    bot = XAUUSDM1Scalper()
    monkeypatch.setattr(bot, "indicators", lambda frame: frame)
    signal = bot.predict(*data.values(), spread=0.1)
    assert signal.direction == direction
    price = data["M1"]["close"].iloc[-1]
    assert direction * (price - signal.stop_loss) > 0
    assert abs(signal.take_profit - price) / abs(price - signal.stop_loss) == pytest.approx(2.0)
    assert bot.predict(*data.values(), spread=1.0).direction == 0
    data["M15"] = data["M15"].iloc[:-1]
    assert bot.predict(*data.values()).direction == 0


@pytest.mark.parametrize(
    "kwargs", [{"risk_reward": 0}, {"atr_sl_multiplier": np.nan}, {"swing_lookback": 1}]
)
def test_rejects_unsafe_configuration(kwargs):
    with pytest.raises(ValueError):
        XAUUSDM1Scalper(**kwargs)
