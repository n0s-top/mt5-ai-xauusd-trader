import numpy as np
import pandas as pd
import pytest

from src.research.intraday_candidates import METHODS, prepare, run


def fixture_frame():
    days = pd.bdate_range("2026-02-16", periods=30)
    index = pd.DatetimeIndex(
        np.concatenate(
            [
                pd.date_range(
                    str(day.date()) + " 09:30", periods=391, freq="min", tz="America/New_York"
                )
                .tz_convert("UTC")
                .to_numpy()
                for day in days
            ]
        )
    )
    values = 2000 + np.arange(len(index)) * 0.001 + np.sin(np.arange(len(index)) / 50)
    return pd.DataFrame(
        {
            "open": values,
            "high": values + 0.2,
            "low": values - 0.2,
            "close": values + 0.05,
            "tick_volume": 100,
        },
        index=index,
    )


def test_future_prices_do_not_change_past_signals():
    frame = fixture_frame()
    cutoff = 24 * 391
    changed = frame.copy()
    changed.iloc[cutoff:, :4] *= 1.1
    a, b = prepare(frame), prepare(changed)
    for method in METHODS:
        for field in a["plans"][method]:
            np.testing.assert_allclose(
                a["plans"][method][field][:cutoff],
                b["plans"][method][field][:cutoff],
                equal_nan=True,
            )


def test_no_volume_rejects_vwap_and_keeps_orb():
    frame = fixture_frame()
    frame["tick_volume"] = 0
    data = prepare(frame)
    assert not data["volume_available"]
    assert np.isfinite(data["plans"]["orb5"]["direction"]).any()
    with pytest.raises(ValueError, match="volume"):
        run(data, "noise_vwap_tick", np.full(len(frame), 0.1), 0, len(frame))


def test_new_york_dst_and_incomplete_opening_range():
    frame = fixture_frame()
    data = prepare(frame)
    for date, utc_hour in (("2026-02-17", 14), ("2026-03-10", 13)):
        pos = frame.index.get_loc(pd.Timestamp(date + f" {utc_hour}:35", tz="UTC"))
        assert data["minute"][pos] == 5
        assert np.isfinite(data["plans"]["orb5"]["direction"][pos]) == (date != "2026-02-17")
    missing = pd.Timestamp("2026-03-10 13:32", tz="UTC")
    bad = prepare(frame.drop(missing))
    mask = bad["day"] == "2026-03-10"
    assert not np.isfinite(bad["plans"]["orb5"]["direction"][mask]).any()


@pytest.mark.parametrize("direction", [1, -1])
def test_ema_entry_bar_stop_and_accounting(direction):
    frame = fixture_frame()
    i = 20 * 391 + 30
    frame.iloc[i, frame.columns.get_loc("low")] = frame.open.iloc[i] - 10
    frame.iloc[i, frame.columns.get_loc("high")] = frame.open.iloc[i] + 10
    data = prepare(frame)
    plan = data["plans"]["ema_vwap15_tick_proxy"]
    plan["direction"][:] = np.nan
    plan["direction"][i] = direction
    plan["stop"][i] = frame.open.iloc[i] - direction
    plan["expiry"][i] = data["time"][i] + 3600
    stats, trades, curve = run(data, "ema_vwap15_tick_proxy", np.full(len(frame), 0.1), i, i + 3)
    assert len(trades) == 1
    trade = trades[0]
    assert trade["entry_time_utc"] == trade["exit_time_utc"]
    assert trade["outcome"] == "SL" and trade["ambiguous_path"]
    assert trade["net_pnl"] < 0
    assert trade["initial_risk"] <= 50.000001
    assert curve[-1] == pytest.approx(10000 + trade["net_pnl"])
    assert stats["commission_cost"] == pytest.approx(trade["ounces"] * 0.1)
