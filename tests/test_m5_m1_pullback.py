import pandas as pd
import pytest

from src.strategies.m5_m1_pullback import M5M1Pullback, M5M1QualityPullback
from src.strategies.xauusd_m1_scalper import XAUUSDM1Scalper
from tests.test_scalper_upgrade import setup_signal


@pytest.mark.parametrize("direction", [1, -1])
def test_m15_opposition_warns_but_does_not_gate_m5_setup(monkeypatch, direction):
    frames = setup_signal(direction)
    frames["M15"]["ema200"] = 2001 + direction
    original, candidate = XAUUSDM1Scalper(), M5M1Pullback()
    for strategy in (original, candidate):
        monkeypatch.setattr(strategy, "indicators", lambda frame: frame)
    assert original.predict(*frames.values(), spread=0.1).direction == 0
    result = candidate.predict(*frames.values(), spread=0.1)
    assert result.direction == direction
    assert "M15 context only" in result.reason


def test_missing_m15_does_not_invent_a_data_gate(monkeypatch):
    frames = setup_signal(1)
    candidate = M5M1Pullback()
    monkeypatch.setattr(candidate, "indicators", lambda frame: frame)
    assert candidate.predict(frames["M1"], frames["M5"], pd.DataFrame(), spread=0.1).direction == 1


@pytest.mark.parametrize("failure", ["spread", "m5_flat", "m5_gap"])
def test_execution_and_m5_safety_checks_remain(monkeypatch, failure):
    frames = setup_signal(1)
    candidate = M5M1Pullback()
    monkeypatch.setattr(candidate, "indicators", lambda frame: frame)
    spread = 0.1
    if failure == "spread":
        spread = 1
    elif failure == "m5_flat":
        frames["M5"]["ema9"] = frames["M5"]["ema21"]
    else:
        frames["M5"] = frames["M5"].drop(frames["M5"].index[-2])
    assert candidate.predict(*frames.values(), spread=spread).direction == 0


@pytest.mark.parametrize("direction", [1, -1])
@pytest.mark.parametrize("failure", [None, "slope", "separation", "stretch", "quote", "atr"])
def test_quality_filters_both_directions(monkeypatch, direction, failure):
    frames = setup_signal(direction)
    m5 = frames["M5"]
    m5.loc[m5.index[-4], "ema21"] = 2000 - direction * 0.5
    if failure == "slope":
        m5.loc[m5.index[-4], "ema21"] = 2000 + direction * 0.5
    elif failure == "separation":
        m5.loc[m5.index[-1], "ema9"] = 2000 + direction * 0.01
    elif failure == "stretch":
        frames["M1"].loc[frames["M1"].index[-1], "ema21"] = 2000 - direction * 2
    elif failure == "atr":
        m5.loc[m5.index[-1], "atr"] = float("nan")
    strategy = M5M1QualityPullback()
    monkeypatch.setattr(strategy, "indicators", lambda frame: frame)
    baseline = M5M1Pullback()
    monkeypatch.setattr(baseline, "indicators", lambda frame: frame)
    assert baseline.predict(*frames.values(), spread=0.1).direction == direction
    result = strategy.predict(*frames.values(), spread=None if failure == "quote" else 0.1)
    assert result.direction == (direction if failure is None else 0)
    if failure is None:
        assert all(check["passed"] for check in strategy.last_checks)
        assert strategy.last_setup == "QUALITY_PULLBACK"
    else:
        assert result.stop_loss is None and result.take_profit is None
        assert strategy.last_setup == "WAIT"


def test_quality_resets_diagnostics_after_previous_signal(monkeypatch):
    frames = setup_signal(1)
    frames["M5"].loc[frames["M5"].index[-4], "ema21"] = 1999.5
    strategy = M5M1QualityPullback()
    monkeypatch.setattr(strategy, "indicators", lambda frame: frame)
    assert strategy.predict(*frames.values(), spread=0.1).direction == 1
    assert strategy.predict(*frames.values(), spread=1).direction == 0
    assert strategy.last_checks == [] and strategy.last_setup == "WAIT"


@pytest.mark.parametrize("direction", [1, -1])
@pytest.mark.parametrize("failure", [None, "noise", "volatility", "wick", "stop", "gap", "history"])
def test_regime_filters_and_diagnostics(monkeypatch, direction, failure):
    from src.strategies.m5_m1_pullback import M5M1RegimePullback

    frames = setup_signal(direction)
    m1, m5 = frames["M1"], frames["M5"]
    m5.loc[m5.index[-4], "ema21"] = 2000 - direction * 0.5
    for i, index in enumerate(m5.index[-13:]):
        close = 2000 + direction * (i - 6) * 0.1
        m5.loc[index, ["open", "high", "low", "close"]] = [close, close + 2, close - 2, close]
    m1.loc[m1.index[-1], ["open", "high", "low", "close"]] = (
        [2000, 2001.2, 1999.8, 2001] if direction == 1 else [2000, 2000.2, 1998.8, 1999]
    )
    if failure == "noise":
        for i, index in enumerate(m5.index[-13:]):
            close = 2000 + (1 if i % 2 else -1)
            m5.loc[index, ["open", "high", "low", "close"]] = [close, close + 2, close - 2, close]
    elif failure == "volatility":
        m1.loc[m1.index[-21:-1], "atr"] = 0.5
    elif failure == "wick":
        m1.loc[m1.index[-1], "high" if direction == 1 else "low"] = 2003 if direction == 1 else 1997
    elif failure == "stop":
        m1.loc[m1.index[-3], "low" if direction == 1 else "high"] = 1990 if direction == 1 else 2010
    elif failure == "gap":
        frames["M5"] = m5.drop(m5.index[-10])
    elif failure == "history":
        m1.loc[m1.index[-10], "atr"] = float("nan")
    strategy = M5M1RegimePullback()
    monkeypatch.setattr(strategy, "indicators", lambda frame: frame)
    result = strategy.predict(*frames.values(), spread=0.1)
    assert result.direction == (direction if failure is None else 0)
    assert strategy.last_setup == ("REGIME_PULLBACK" if failure is None else "WAIT")
    if failure is None:
        assert all(item["passed"] for item in strategy.last_checks)
        assert strategy.strategy_id != M5M1QualityPullback.strategy_id
        assert strategy.predict(*frames.values(), spread=1).direction == 0
        assert strategy.last_checks == []
    else:
        assert result.stop_loss is None and result.take_profit is None
        assert any(not item["passed"] for item in strategy.last_checks)
