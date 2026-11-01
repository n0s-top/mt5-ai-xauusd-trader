import pandas as pd
import pytest

from src.research.scalper_comparison import simulate_trade, summarize


def candles(rows):
    return pd.DataFrame(
        rows,
        columns=["open", "high", "low", "close"],
        index=pd.date_range("2026-10-20", periods=len(rows), freq="min", tz="UTC"),
    )


def simulate(bars, side="BUY", **kwargs):
    plan = {
        "side": side,
        "entry": 100,
        "stop_loss": 99 if side == "BUY" else 101,
        "take_profit": 102 if side == "BUY" else 98,
    }
    return simulate_trade(
        bars,
        0,
        len(bars),
        plan,
        pd.Series(0.1, index=bars.index),
        slippage=0.01,
        fee_price=0.02,
        **kwargs,
    )


@pytest.mark.parametrize("side", ["BUY", "SELL"])
def test_both_exits_hit_uses_stop_first_including_costs(side):
    trade = simulate(candles([[100, 103, 97, 100]]), side)
    assert trade["outcome"] == "SL"
    assert trade["net_r"] == pytest.approx(-1)
    assert trade["ambiguous_path"]


def test_gap_stop_does_not_guarantee_the_sl_price():
    trade = simulate(candles([[100, 100.5, 99.5, 100], [97, 98, 96, 97]]))
    assert trade["outcome"] == "SL"
    assert trade["exit_price"] < 99
    assert trade["net_r"] < -1


def test_untriggered_order_does_not_become_a_trade():
    assert simulate(candles([[98, 99, 97, 98]])) is None


def test_spread_and_fees_are_charged_on_timeout():
    trade = simulate(candles([[100, 100.2, 99.8, 100]]))
    assert trade["outcome"] == "SEGMENT_END"
    assert trade["net_r"] < 0


def test_gap_over_target_is_recorded_not_silently_dropped():
    trade = simulate(candles([[105, 106, 104, 105]]))
    assert trade["outcome"] == "GAP_THROUGH_TARGET"
    assert trade["net_r"] < 0


def test_missing_path_is_reported_as_data_gap():
    bars = candles([[100, 100.5, 99.5, 100], [98, 98.5, 97, 98]])
    bars.index = pd.DatetimeIndex([bars.index[0], bars.index[1] + pd.Timedelta(minutes=5)])
    trade = simulate(bars)
    assert trade["outcome"] == "DATA_GAP" and trade["net_r"] < -1


def test_empty_summary_does_not_invent_a_win_rate():
    report = summarize([])
    assert report["trades"] == 0 and report["win_rate"] is None
    assert report["ending_equity"] == 10000


def test_cost_gate_rejects_before_execution(monkeypatch):
    import src.research.scalper_comparison as engine
    from src.strategies.xauusd_m1_scalper import ScalperSignal

    class SignalStrategy:
        risk_reward = 2
        indicators = staticmethod(lambda frame: frame)

        def predict(self, *args, **kwargs):
            return ScalperSignal(1, .6, 99., 102., "fixture")

    monkeypatch.setattr(engine, "XAUUSDM1Scalper", SignalStrategy)
    bars = candles([[100, 100.2, 99.8, 100]] * 3501)
    bars["tick_volume"] = 100
    report = engine.compare(bars, pd.Series(.1, index=bars.index), strategies=("pullback",),
                            fee_price=1., min_net_reward_risk=1.5)
    assert not report["trades"]
    for stats in report["results"]["pullback"].values():
        assert stats["cost_rejected_signals"] == stats["signals"] > 0


def test_equity_and_drawdown_use_net_r():
    report = summarize(
        [
            {"net_r": 1, "ambiguous_path": False, "outcome": "TP"},
            {"net_r": -1, "ambiguous_path": True, "outcome": "SL"},
        ],
        risk_percent=1,
    )
    assert report["ending_equity"] == pytest.approx(9999)
    assert report["max_closed_trade_drawdown_percent"] == pytest.approx(1)


def test_comparison_does_not_expose_current_or_future_prices(monkeypatch):
    import src.research.scalper_comparison as engine
    from src.strategies.xauusd_m1_scalper import ScalperSignal

    seen = []

    class SpyStrategy:
        risk_reward = 2

        @staticmethod
        def indicators(frame):
            return frame

        def predict(self, m1, m5, m15, *, spread):
            decision = m1.index[-1] + pd.Timedelta(minutes=1)
            assert m5.index[-1] + pd.Timedelta(minutes=5) <= decision
            assert m15.index[-1] + pd.Timedelta(minutes=15) <= decision
            assert all(frame["high"].max() <= 102 for frame in (m1, m5, m15))
            seen.append(decision)
            return ScalperSignal(0, 0, None, None, "No setup")

    monkeypatch.setattr(engine, "XAUUSDM1Scalper", SpyStrategy)
    monkeypatch.setattr(engine, "AdaptiveScalper", SpyStrategy)
    bars = candles([[100, 102, 99, 100]] * 3501)
    bars["tick_volume"] = 100
    bars.loc[bars.index[-1], ["open", "high", "low", "close"]] = [200, 201, 199, 200]
    report = engine.compare(bars, pd.Series(0.1, index=bars.index))
    assert seen and max(seen) == bars.index[-1]
    assert report["results"]["adaptive"]["holdout"]["win_rate"] is None


def test_comparison_rejects_missing_spread_observations():
    from src.research.scalper_comparison import compare

    bars = candles([[100, 102, 99, 100]] * 3501)
    spreads = pd.Series(0.1, index=bars.index)
    spreads.iloc[-1] = float("nan")
    with pytest.raises(ValueError, match="spreads"):
        compare(bars, spreads)


@pytest.mark.parametrize("direction", [1, -1])
def test_prefilter_matches_full_scan_with_trades_and_gaps(monkeypatch, direction):
    import numpy as np

    from src.research.scalper_comparison import compare
    from src.strategies.xauusd_m1_scalper import XAUUSDM1Scalper

    n = 3601
    phase = np.arange(n)
    close = 2000 + direction * phase * 0.002 + np.sin(phase / 3) * 0.5
    opened = np.r_[close[0], close[:-1]]
    bars = pd.DataFrame(
        {
            "open": opened,
            "high": np.maximum(opened, close) + 0.2,
            "low": np.minimum(opened, close) - 0.2,
            "close": close,
            "tick_volume": 100,
        },
        index=pd.date_range("2025-01-01", periods=n, freq="min", tz="UTC"),
    ).drop(pd.Timestamp("2025-01-03T08:10Z"))

    def indicators(frame):
        frame = frame.copy()
        frame["ema21"] = frame["close"].ewm(span=21, adjust=False).mean()
        frame["ema9"] = frame["ema21"] + direction * 0.2
        frame["ema200"] = frame["close"] - direction
        frame["rsi"] = 50 + direction * 10
        frame["adx"] = 30.0
        frame["atr"] = 1.0
        return frame

    monkeypatch.setattr(XAUUSDM1Scalper, "indicators", staticmethod(indicators))
    spreads = pd.Series(0.05, index=bars.index)
    strategies = ("pullback", "m5_m1", "m5_m1_quality", "m5_m1_regime")
    fast = compare(bars, spreads, strategies=strategies)
    slow = compare(bars, spreads, strategies=strategies, use_prefilter=False)
    assert fast == slow
    assert fast["trades"]
    assert any(trade["side"] == ("BUY" if direction == 1 else "SELL") for trade in fast["trades"])
