import numpy as np
import pandas as pd
import pytest

from scripts.prepare_daily_research_data import daily_from_minutes
from src.research.published_strategies import METHODS, evaluate, metrics, trend_targets


def history(n=650):
    rng = np.random.default_rng(17)
    close = 100 * np.exp(np.cumsum(rng.normal(0.001, 0.01, n)))
    opened = np.r_[close[0], close[:-1]]
    return pd.DataFrame(
        {
            "open": opened,
            "close": close,
            "high": np.maximum(opened, close) + 0.5,
            "low": np.minimum(opened, close) - 0.5,
        },
        index=pd.bdate_range("2019-01-01", periods=n, tz="UTC"),
    )


@pytest.mark.parametrize("method", METHODS[:3])
def test_trend_target_never_uses_current_or_future_candle(method):
    original = history()
    altered = original.copy()
    altered.iloc[500:, :] *= 4
    a, b = trend_targets(original, method), trend_targets(altered, method)
    pd.testing.assert_series_equal(a.iloc[:501], b.iloc[:501])


@pytest.mark.parametrize("method", METHODS)
def test_equity_prefix_is_unchanged_when_future_prices_change(method):
    frame = history()
    changed = frame.copy()
    changed.iloc[600:, :] *= 1.8
    kwargs = {"start": frame.index[300], "carry": 0.03}
    _, a, orders = evaluate(frame, method, **kwargs)
    _, b, _ = evaluate(changed, method, **kwargs)
    pd.testing.assert_series_equal(a.iloc[: 600 - 300], b.iloc[: 600 - 300])
    assert not orders.empty


def test_flat_buy_hold_charges_both_sides_and_calendar_financing():
    frame = pd.DataFrame(
        {"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0},
        index=pd.date_range("2024-01-05", periods=2, freq="3D", tz="UTC"),
    )
    result, curve, orders = evaluate(frame, "buy_hold_1x", start=frame.index[0], carry=0.03)
    execution = 100 * (0.24 + 0.10 + 2 * 0.002)
    finance = 10000 * 0.03 * 3 / 365.25
    assert result["summary"]["execution_cost_usd"] == pytest.approx(execution)
    assert result["summary"]["carry_cost_usd"] == pytest.approx(finance)
    assert curve.iloc[-1] == pytest.approx(10000 - execution - finance)
    assert len(orders) == 2


def test_turtle_prior_channel_and_adverse_gap_stop():
    frame = pd.DataFrame(
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0},
        index=pd.bdate_range("2024-01-01", periods=65, tz="UTC"),
    )
    frame.iloc[60] = [100, 103, 100, 102]
    frame.iloc[61] = [95, 96, 94, 95]
    _, _, orders = evaluate(frame, "donchian20_10", start=frame.index[55])
    assert orders.iloc[0].reference_price == pytest.approx(101.001)
    assert orders.iloc[1].reference_price == 95
    assert orders.iloc[1].reason == "stop_or_channel"
    assert orders.iloc[1].time == frame.index[61].isoformat()


def test_drawdown_includes_first_loss_from_initial_equity():
    curve = pd.Series([9000, 9500], index=pd.bdate_range("2024-01-01", periods=2, tz="UTC"))
    assert metrics(curve)["daily_close_drawdown_percent"] == pytest.approx(10)


def test_daily_session_uses_actual_rows_without_filling_missing_minutes():
    frame = pd.DataFrame(
        {
            "time": [1704146340, 1704146400],
            "open": [100, 102],
            "high": [101, 103],
            "low": [99, 101],
            "close": [100, 102],
        },
    )
    result = daily_from_minutes(frame)
    assert result.minute_rows.sum() == 2
    assert result.index.tz is not None


def test_monthly_strategy_does_not_rebalance_daily():
    frame = history()
    _, _, orders = evaluate(frame, "tsmom12_vol40_cap2", start=frame.index[300])
    dates = pd.to_datetime(orders.loc[orders.reason == "rebalance", "time"], utc=True)
    assert len(dates) < 20
    assert len(dates) == dates.dt.strftime("%Y-%m").nunique()
