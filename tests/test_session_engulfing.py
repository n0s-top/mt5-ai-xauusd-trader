import numpy as np
import pandas as pd
import pytest
import sys

from src.strategies.session_engulfing import SessionEngulfing


@pytest.fixture(autouse=True)
def real_talib(monkeypatch):
    # Repository conftest globally replaces TA-Lib with zero-valued mocks.
    # These integration checks need actual EMA/ATR calculations.
    import src.strategies.session_engulfing as module
    monkeypatch.delitem(sys.modules, "talib", raising=False)
    real = pytest.importorskip("talib")
    monkeypatch.setattr(module, "talib", real)


def frames():
    decision = pd.Timestamp("2026-10-29T14:00Z")
    result = []
    for minutes in (1, 5, 15):
        index = pd.date_range(end=decision - pd.Timedelta(minutes=minutes),
                              periods=800, freq=f"{minutes}min")
        close = np.full(800, 120.) if minutes == 1 else np.linspace(100, 120, 800)
        result.append(pd.DataFrame(dict(open=close, high=close + .2, low=close - .2,
                                        close=close, tick_volume=100), index=index))
    result[0].loc[result[0].index[-2], ["open", "high", "low", "close"]] = [120.2, 120.3, 119.4, 119.8]
    result[0].loc[result[0].index[-1], ["open", "high", "low", "close"]] = [119.75, 120.5, 119.7, 120.4]
    return result


def test_real_indicators_accept_trend_engulfing_with_bounded_stop():
    signal = SessionEngulfing().predict(*frames(), spread=.05)
    assert signal.direction == 1, signal.reason
    assert signal.stop_loss < 119.4
    assert signal.take_profit > 120.5


def test_bearish_mirror():
    data = frames()
    for frame in data:
        old = frame.copy()
        frame["open"], frame["close"] = 240 - old.open, 240 - old.close
        frame["high"], frame["low"] = 240 - old.low, 240 - old.high
    signal = SessionEngulfing().predict(*data, spread=.05)
    assert signal.direction == -1, signal.reason


def test_session_dst_and_weekend():
    check = SessionEngulfing.session_open
    assert check(pd.Timestamp("2026-07-01T07:00Z"))
    assert check(pd.Timestamp("2026-12-01T08:00Z"))
    assert not check(pd.Timestamp("2026-12-01T07:00Z"))
    assert not check(pd.Timestamp("2026-12-05T14:00Z"))
    assert not check(pd.Timestamp("2026-12-01T03:00Z"))


def test_hourly_excludes_incomplete_hour_and_missing_quarter():
    data = frames()[2]
    decision = pd.Timestamp("2026-10-29T13:59Z")
    hourly = SessionEngulfing.hourly(data, decision)
    assert hourly.index[-1] + pd.Timedelta(hours=1) <= decision
    missing = data.drop(pd.Timestamp("2026-10-29T13:15Z"))
    assert pd.Timestamp("2026-10-29T13:00Z") not in SessionEngulfing.hourly(missing, decision + pd.Timedelta(minutes=1)).index


@pytest.mark.parametrize("kind", ["spread", "missing_spread", "no_engulfing", "opposed_m5", "wide_stop", "future_m15"])
def test_rejections(kind):
    data = frames()
    spread = .05
    if kind == "spread":
        spread = 2.
    elif kind == "missing_spread":
        spread = None
    elif kind == "no_engulfing":
        data[0].loc[data[0].index[-1], "open"] = 120.3
    elif kind == "opposed_m5":
        data[1]["close"] = np.linspace(140, 120, 800)
        data[1]["open"] = data[1].close
        data[1]["high"], data[1]["low"] = data[1].close + .2, data[1].close - .2
    elif kind == "wide_stop":
        data[0].loc[data[0].index[-2], "low"] = 115.
    elif kind == "future_m15":
        data[2].index += pd.Timedelta(minutes=15)
    assert SessionEngulfing().predict(*data, spread=spread).direction == 0
