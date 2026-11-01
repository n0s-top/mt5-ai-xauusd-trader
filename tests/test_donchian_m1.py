import numpy as np
import pandas as pd
import pytest

from src.research.donchian_m1 import prepare, run


def candles(n=100):
    return pd.DataFrame(
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0},
        index=pd.date_range("2025-01-01", periods=n, freq="min", tz="UTC"),
    )


def test_channels_exclude_current_bar_and_future_prices():
    frame = candles()
    frame.iloc[60] = [100, 105, 99.5, 104]
    a = prepare(frame)
    assert a["upper"][60] == pytest.approx(101.001)
    changed = frame.copy()
    changed.iloc[70:] *= 2
    b = prepare(changed)
    for key in ("upper", "lower", "exit_upper", "exit_lower", "atr"):
        np.testing.assert_allclose(a[key][:71], b[key][:71], equal_nan=True)


def test_buy_ask_fill_adverse_gap_and_money_reconciliation():
    frame = candles(63)
    frame.iloc[60] = [102, 103, 101.5, 102]
    frame.iloc[61] = [97, 98, 96, 97]
    data = prepare(frame)
    stats, trades, curve = run(data, np.full(len(frame), 0.2), 60, 63, fee_price=0.1)
    trade = trades[0]
    assert trade["side"] == "BUY"
    assert trade["entry"] == pytest.approx(102.202)
    assert trade["exit_price"] == pytest.approx(96.998)
    assert trade["net_r"] < -1
    expected = trade["ounces"] * (trade["exit_price"] - trade["entry"]) - trade["commission"]
    assert trade["net_pnl"] == pytest.approx(expected)
    assert curve[-1] == pytest.approx(10000 + sum(t["net_pnl"] for t in trades))
    assert stats["max_m1_close_drawdown_percent"] > 0


def test_short_executes_bid_entry_and_ask_exit():
    frame = candles(63)
    frame.iloc[60] = [100, 100.5, 98, 98.5]
    frame.iloc[61] = [100, 102, 99.5, 101]
    _, trades, _ = run(prepare(frame), np.full(len(frame), 0.2), 60, 63, fee_price=0.1)
    trade = trades[0]
    assert trade["side"] == "SELL"
    assert trade["entry"] == pytest.approx(98.997)
    assert trade["exit_price"] == pytest.approx(101.202)
    expected = trade["ounces"] * (trade["entry"] - trade["exit_price"]) - trade["commission"]
    assert trade["net_pnl"] == pytest.approx(expected)


def test_ambiguous_entry_stop_is_adverse_and_never_reenters_same_bar():
    frame = candles(61)
    frame.iloc[60] = [100, 106, 94, 100]
    stats, trades, _ = run(prepare(frame), np.full(len(frame), 0.1), 60, 61)
    assert len(trades) == 1
    assert trades[0]["net_pnl"] < 0
    assert trades[0]["ambiguous_path"]
    assert stats["ambiguous_trades"] == 1


def test_missing_minutes_exit_open_and_block_fresh_entries():
    frame = candles(63)
    frame.iloc[60] = [102, 103, 101.5, 102]
    frame.index = frame.index[:61].append(frame.index[61:] + pd.Timedelta(minutes=10))
    stats, trades, _ = run(prepare(frame), np.full(len(frame), 0.1), 60, 63)
    assert trades[0]["outcome"] == "DATA_GAP"
    assert stats["gap_exits"] == 1
    assert len(trades) == 1


def test_financing_charges_actual_elapsed_seconds():
    frame = candles(63)
    frame.iloc[60] = [102, 103, 101.5, 102]
    _, trades, _ = run(prepare(frame), np.full(len(frame), 0.1), 60, 63, annual_carry=0.08)
    t = trades[0]
    assert t["carry_cost"] == pytest.approx(t["ounces"] * 102 * 0.08 * 60 / (365.25 * 86400))


def test_equity_prefix_does_not_change_when_future_prices_change():
    rng = np.random.default_rng(19)
    close = 100 + np.cumsum(rng.normal(0, 0.3, 1000))
    frame = candles(1000)
    frame["close"] = close
    frame["open"] = np.r_[close[0], close[:-1]]
    frame["high"] = frame[["open", "close"]].max(axis=1) + 0.1
    frame["low"] = frame[["open", "close"]].min(axis=1) - 0.1
    altered = frame.copy()
    altered.iloc[800:] *= 2
    a = run(prepare(frame), np.full(len(frame), 0.1), 200, 1000)
    b = run(prepare(altered), np.full(len(frame), 0.1), 200, 1000)
    assert a[1]
    np.testing.assert_allclose(a[2][:600], b[2][:600])


def test_extreme_gap_keeps_negative_equity_instead_of_hiding_shortfall():
    frame = candles(63)
    frame["high"] = 100.001
    frame["low"] = 99.999
    frame.iloc[60] = [100.002, 100.003, 100.0019, 100.002]
    frame.iloc[61] = [1, 1.1, 0.9, 1]
    stats, trades, curve = run(prepare(frame), np.zeros(len(frame)), 60, 63)
    assert stats["equity_exhausted"]
    assert curve[-1] < 0
    assert stats["max_m1_close_drawdown_percent"] > 100
    assert curve[-1] == pytest.approx(10000 + sum(t["net_pnl"] for t in trades))
