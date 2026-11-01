from datetime import datetime
from types import SimpleNamespace

import pandas as pd
import pytest

pytest.importorskip("MetaTrader5")

import run_mt5_assistant as assistant
from src.strategies.xauusd_m1_scalper import ScalperSignal


@pytest.fixture
def live_snapshot(monkeypatch):
    now = pd.Timestamp("2026-10-29T08:44:35Z")

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now.to_pydatetime()

    monkeypatch.setattr(assistant, "datetime", Clock)
    api = SimpleNamespace(
        terminal_info=None,
        symbol_select=None,
        symbol_info_tick=None,
        symbol_info=None,
        account_info=None,
        copy_rates_from_pos=None,
        positions_get=lambda: (),
        orders_get=lambda: (),
        TIMEFRAME_M1=1,
        ORDER_TYPE_BUY=0,
        ORDER_TYPE_SELL=1,
        order_calc_profit=lambda action, symbol, volume, entry, exit: (
            (exit - entry) * volume * 100 * (1 if action == 0 else -1)
        ),
        order_calc_margin=lambda action, symbol, volume, entry: volume * 1000,
    )
    monkeypatch.setattr(assistant, "mt5", api)
    monkeypatch.setattr(api, "terminal_info", lambda: SimpleNamespace(connected=True))
    monkeypatch.setattr(api, "symbol_select", lambda *args: True)
    monkeypatch.setattr(
        api,
        "symbol_info_tick",
        lambda symbol: SimpleNamespace(time=int(now.timestamp()) - 1, bid=2000, ask=2000.1),
    )
    monkeypatch.setattr(
        api,
        "symbol_info",
        lambda symbol: SimpleNamespace(
            trade_tick_size=0.01,
            trade_tick_value_loss=1,
            volume_min=0.01,
            volume_max=100,
            volume_step=0.01,
        ),
    )
    monkeypatch.setattr(
        api,
        "account_info",
        lambda: SimpleNamespace(equity=10000, currency="USD", margin_free=10000),
    )
    times = pd.date_range(end=now.floor("min") - pd.Timedelta(minutes=1), periods=5000, freq="min")
    bars = pd.DataFrame(
        {
            "time": times.as_unit("s").asi8,
            "open": 2000.0,
            "high": 2002.0,
            "low": 1998.0,
            "close": 2001.0,
            "tick_volume": 100,
        }
    )
    monkeypatch.setattr(api, "copy_rates_from_pos", lambda *args: bars)
    return SimpleNamespace(
        predict=lambda *args, **kwargs: ScalperSignal(1, 0.6, 1998, 2005, "Test setup")
    )


def test_epoch_seconds_are_prepared_and_live_equity_sizes_plan(live_snapshot):
    plan = assistant.snapshot("XAUUSDc", 0.5, live_snapshot, sizing="fixed")
    assert plan["status"] == "REVIEW"
    assert plan["candle_time_utc"] == "2026-10-29T08:43:00+00:00"
    assert 0 < plan["estimated_risk"] <= 50


def test_zero_equity_keeps_price_analysis_without_lot(monkeypatch, live_snapshot):
    monkeypatch.setattr(
        assistant.mt5, "account_info", lambda: SimpleNamespace(equity=0, currency="USC")
    )
    plan = assistant.snapshot("XAUUSDc", 0.5, live_snapshot)
    assert plan["status"] == "REVIEW"
    assert plan["volume"] is None
    assert "zero" in plan["sizing_note"]


def test_stale_quote_is_rejected(monkeypatch, live_snapshot):
    monkeypatch.setattr(
        assistant.mt5,
        "symbol_info_tick",
        lambda symbol: SimpleNamespace(time=1, bid=2000, ask=2000.1),
    )
    with pytest.raises(ValueError, match="stale"):
        assistant.snapshot("XAUUSDc", 0.5, live_snapshot)


@pytest.mark.parametrize("offset,allowed", [(1, True), (30, False)])
def test_clock_skew_is_bounded(monkeypatch, live_snapshot, offset, allowed):
    tick_time = int(pd.Timestamp("2026-10-29T08:44:35Z").timestamp()) + offset
    monkeypatch.setattr(
        assistant.mt5,
        "symbol_info_tick",
        lambda symbol: SimpleNamespace(time=tick_time, bid=2000, ask=2000.1),
    )
    if allowed:
        assert assistant.snapshot("XAUUSDc", 0.5, live_snapshot)["status"] == "REVIEW"
    else:
        with pytest.raises(ValueError, match="future"):
            assistant.snapshot("XAUUSDc", 0.5, live_snapshot)


@pytest.mark.parametrize("direction", [1, -1])
def test_future_trigger_and_opposite_exit(direction):
    quote = {
        "bid": 2000,
        "ask": 2000.1,
        "tick_size": 0.01,
        "tick_value": 1,
        "volume_min": 0.01,
        "volume_max": 100,
        "volume_step": 0.01,
    }
    signal = ScalperSignal(
        direction, 0.6, 1998 if direction == 1 else 2002, 2005 if direction == 1 else 1995, "setup"
    )
    plan = assistant.future_entry(signal, quote, {"high": 2001, "low": 1999}, 10000, 0.5)
    assert plan["status"] == "REVIEW"
    assert direction * (plan["entry"] - (quote["ask"] if direction == 1 else quote["bid"])) > 0
    assert direction * (plan["take_profit"] - plan["entry"]) > 0
    assert plan["reward_risk"] >= 2 - 1e-8
    assert plan["exit_action"] == ("SELL_TO_CLOSE" if direction == 1 else "BUY_TO_CLOSE")
    assert 0 < plan["estimated_risk"] <= 50


def test_quit_does_not_connect_or_analyze(monkeypatch):
    from unittest.mock import Mock

    connect = Mock()
    analyze = Mock()
    monkeypatch.setattr(assistant, "mt5", SimpleNamespace(initialize=connect))
    monkeypatch.setattr(assistant, "snapshot", analyze)
    monkeypatch.setattr("sys.argv", ["run_mt5_assistant.py", "--no-log"])
    monkeypatch.setattr("builtins.input", lambda prompt: "q")
    assistant.main()
    connect.assert_not_called()
    analyze.assert_not_called()


def test_enter_analyzes_once_then_waits_again(monkeypatch):
    from unittest.mock import Mock

    connect = Mock(return_value=True)
    disconnect = Mock()
    analyze = Mock(return_value={"symbol": "XAUUSDc", "status": "WAIT", "reason": "No setup"})
    monkeypatch.setattr(assistant, "mt5", SimpleNamespace(initialize=connect, shutdown=disconnect))
    monkeypatch.setattr(assistant, "snapshot", analyze)
    monkeypatch.setattr("sys.argv", ["run_mt5_assistant.py", "--no-log"])
    commands = iter(["", "q"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(commands))
    assistant.main()
    connect.assert_called_once()
    analyze.assert_called_once()
    disconnect.assert_called_once()


def test_default_kelly_does_not_fall_back_to_fixed_lot(live_snapshot):
    plan = assistant.snapshot("XAUUSDc", 0.5, live_snapshot)
    assert plan["status"] == "REVIEW"
    assert plan["kelly"]["status"] == "INSUFFICIENT_DATA"
    assert plan["volume"] is None
    assert plan["estimated_risk"] is None


def test_m5_only_reference_survives_m15_opposition(monkeypatch, live_snapshot):
    live_snapshot.requires_m15 = False
    live_snapshot.strategy_id = "m5_m1_pullback_v1"
    live_snapshot.predict = lambda *args, **kwargs: ScalperSignal(
        0, 0, None, None, "No valid setup"
    )
    monkeypatch.setattr(
        assistant.XAUUSDM1Scalper,
        "indicators",
        lambda frame: frame.assign(
            ema200=2002.0, ema9=2001.0, ema21=2000.0, rsi=60.0, adx=30.0, atr=2.0
        ),
    )
    plan = assistant.snapshot("XAUUSDc", 0.5, live_snapshot)
    assert plan["status"] == "WAIT"
    assert plan["preferred_side"] == "BUY"
    assert plan["reference_scenarios"][0]["side"] == "BUY"
    assert "M15" in plan["mtf_warning"]
    assert len(plan["setup_checks"]) == 7
    assert all("M15" not in check["label"] for check in plan["setup_checks"])


def test_ready_kelly_uses_broker_profit_and_margin(tmp_path, live_snapshot):
    from src.strategies.kelly_sizing import STRATEGY_ID

    history = tmp_path / "trades.csv"
    history.write_text(
        "trade_id,closed_at_utc,symbol,strategy_id,net_r\n"
        + "".join(
            f"{i},2026-10-28T00:00:00Z,XAUUSDc,{STRATEGY_ID},{2 if i < 60 else -1}\n"
            for i in range(100)
        ),
        encoding="utf-8",
    )
    plan = assistant.snapshot("XAUUSDc", 0.5, live_snapshot, kelly_history=history)
    assert plan["kelly"]["status"] == "READY"
    assert plan["sizing_mode"] == "kelly"
    assert plan["volume"] > 0
    assert 0 < plan["estimated_risk"] <= plan["risk_budget"] <= 50
    assert plan["estimated_margin"] <= 5000
    live_snapshot.strategy_id = "adaptive_trend_breakout_v1"
    new_plan = assistant.snapshot("XAUUSDc", 0.5, live_snapshot, kelly_history=history)
    assert new_plan["kelly"]["status"] == "INSUFFICIENT_DATA"
    assert new_plan["kelly"]["trades"] == 0
    assert new_plan["volume"] is None


def test_broker_calculation_failure_never_keeps_old_lot(monkeypatch, live_snapshot):
    monkeypatch.setattr(assistant.mt5, "order_calc_profit", lambda *args: None)
    plan = assistant.snapshot("XAUUSDc", 0.5, live_snapshot, sizing="fixed")
    assert plan["volume"] is None
    assert "blocked" in plan["sizing_note"]


def test_minimum_stop_distance_adjusts_future_prices():
    quote = {
        "bid": 2000,
        "ask": 2000.1,
        "tick_size": 0.01,
        "tick_value": 1,
        "volume_min": 0.01,
        "volume_max": 100,
        "volume_step": 0.01,
        "minimum_stop_distance": 5,
    }
    plan = assistant.future_entry(
        ScalperSignal(1, 0.6, 1998, 2005, "setup"), quote, {"high": 2001, "low": 1999}, 10000, 0.5
    )
    assert plan["entry"] - quote["ask"] >= 5 - 1e-8
    assert plan["entry"] - plan["stop_loss"] >= 5 - 1e-8


@pytest.mark.parametrize("equity", [10000, 0])
@pytest.mark.parametrize("direction", [1, -1])
def test_wait_shows_only_preferred_side_and_honest_lot(
    monkeypatch, live_snapshot, equity, direction
):
    live_snapshot.predict = lambda *args, **kwargs: ScalperSignal(
        0, 0, None, None, "No valid setup"
    )
    monkeypatch.setattr(
        assistant.XAUUSDM1Scalper,
        "indicators",
        lambda frame: frame.assign(
            atr=2.0, ema200=2001.0 - direction, ema9=2000.0 + direction, ema21=2000.0
        ),
    )
    monkeypatch.setattr(
        assistant.mt5,
        "account_info",
        lambda: SimpleNamespace(equity=equity, currency="USD", margin_free=10000),
    )
    plan = assistant.snapshot("XAUUSDc", 0.5, live_snapshot)
    assert plan["status"] == "WAIT"
    assert plan["volume"] is None
    scenarios = plan["reference_scenarios"]
    assert [item["side"] for item in scenarios] == ["BUY" if direction == 1 else "SELL"]
    assert plan["preferred_side"] == scenarios[0]["side"]
    for item in scenarios:
        assert item["status"] == "REFERENCE_ONLY"
        assert item["entry"] > 0 and item["stop_loss"] > 0 and item["take_profit"] > 0
        assert item["sizing_mode"] == "hypothetical_fixed_risk"
        assert (item["volume"] is not None) == (equity > 0)


def test_safety_rejection_does_not_generate_reference_scenarios(live_snapshot):
    live_snapshot.predict = lambda *args, **kwargs: ScalperSignal(
        0, 0, None, None, "Invalid OHLC data"
    )
    plan = assistant.snapshot("XAUUSDc", 0.5, live_snapshot)
    assert "reference_scenarios" not in plan


@pytest.mark.parametrize("momentum", [2001., 2000.])
def test_confirmed_wait_has_reference_prices_without_lots(monkeypatch, live_snapshot, momentum):
    monkeypatch.setattr(assistant.XAUUSDM1Scalper, "indicators",
                        staticmethod(lambda frame: frame.assign(atr=2., ema200=2000., ema9=momentum,
                                                    ema21=2000., adx=30., rsi=55.)))
    plan = assistant.snapshot("XAUUSDc", .5, assistant.ConfirmedM1M5())
    assert plan["status"] == "WAIT"
    scenarios = plan["reference_scenarios"]
    assert [s["side"] for s in scenarios] == (["BUY"] if momentum > 2000 else ["BUY", "SELL"])
    for scenario in scenarios:
        assert scenario["status"] == "REFERENCE_ONLY"
        assert scenario["volume"] is None
        assert scenario["entry"] > 0 and scenario["stop_loss"] > 0 and scenario["take_profit"] > 0
    if momentum == 2000:
        assert "preferred_side" not in plan


@pytest.mark.parametrize("reason", ["Spread exceeds ATR budget", "Abnormal candle range"])
def test_market_filter_keeps_reference_prices_but_never_lots(monkeypatch, live_snapshot, reason):
    live_snapshot.predict = lambda *args, **kwargs: ScalperSignal(0, 0, None, None, reason)
    monkeypatch.setattr(
        assistant.XAUUSDM1Scalper,
        "indicators",
        lambda frame: frame.assign(atr=2.0, ema200=2000.0, ema9=2001.0, ema21=2000.0),
    )
    plan = assistant.snapshot("XAUUSDc", 0.5, live_snapshot)
    assert plan["status"] == "WAIT" and plan["reason"] == reason
    assert len(plan["reference_scenarios"]) == 1
    reference = plan["reference_scenarios"][0]
    assert reference["entry"] > 0 and reference["stop_loss"] > 0 and reference["take_profit"] > 0
    assert reference["volume"] is None and reference["estimated_risk"] is None
    assert reason in reference["sizing_note"]
    assert "estimated_margin" not in reference


def test_conflicting_timeframes_wait_without_a_direction(monkeypatch, live_snapshot):
    live_snapshot.predict = lambda *args, **kwargs: ScalperSignal(
        0, 0, None, None, "No valid setup"
    )
    monkeypatch.setattr(
        assistant.XAUUSDM1Scalper,
        "indicators",
        lambda frame: frame.assign(ema200=2000.0, ema9=1999.0, ema21=2000.0),
    )
    plan = assistant.snapshot("XAUUSDc", 0.5, live_snapshot)
    assert plan["status"] == "WAIT"
    assert "reference_scenarios" not in plan
    assert "preferred_side" not in plan
    assert "do not agree" in plan["reference_note"]


def test_existing_positions_reduce_new_trade_budget(monkeypatch, live_snapshot):
    monkeypatch.setattr(
        assistant.mt5,
        "positions_get",
        lambda: [
            SimpleNamespace(type=0, symbol="XAUUSDc", volume=0.36, price_current=2000, sl=1995)
        ],
    )
    plan = assistant.snapshot("XAUUSDc", 0.5, live_snapshot, sizing="fixed")
    assert plan["account_risk"]["stop_risk"] == pytest.approx(180)
    assert plan["volume"] > 0
    assert plan["risk_budget"] == pytest.approx(20)
    assert plan["estimated_risk"] + plan["account_risk"]["stop_risk"] <= 200


def test_existing_cost_reserve_reduces_new_trade_budget(monkeypatch, live_snapshot):
    monkeypatch.setattr(
        assistant.mt5,
        "positions_get",
        lambda: [
            SimpleNamespace(type=0, symbol="XAUUSDc", volume=0.36, price_current=2000, sl=1995)
        ],
    )
    plan = assistant.snapshot(
        "XAUUSDc", 0.5, live_snapshot, sizing="fixed", cost_per_lot=10
    )
    assert plan["account_risk"]["cost_reserve"] == pytest.approx(3.6)
    assert plan["risk_budget"] == pytest.approx(16.4)
    assert plan["volume"] > 0
    assert plan["estimated_risk"] + plan["account_risk"]["stop_risk"] <= 200


def test_unprotected_existing_position_suppresses_lot(monkeypatch, live_snapshot):
    monkeypatch.setattr(
        assistant.mt5,
        "positions_get",
        lambda: [SimpleNamespace(type=0, symbol="XAUUSDc", volume=0.1, price_current=2000, sl=0)],
    )
    plan = assistant.snapshot("XAUUSDc", 0.5, live_snapshot, sizing="fixed")
    assert plan["account_risk"]["status"] == "UNKNOWN"
    assert plan["volume"] is None
    assert "Account risk" in plan["sizing_note"]


def test_costs_can_invalidate_net_reward_risk(live_snapshot):
    plan = assistant.snapshot("XAUUSDc", 0.5, live_snapshot, sizing="fixed", cost_per_lot=500)
    assert plan["volume"] is None
    assert "reward/risk" in plan["sizing_note"]


def test_symbol_directional_volume_limit_is_respected(monkeypatch, live_snapshot):
    broker = assistant.mt5.symbol_info("XAUUSDc")
    broker.volume_limit = 0.02
    monkeypatch.setattr(assistant.mt5, "symbol_info", lambda symbol: broker)
    plan = assistant.snapshot("XAUUSDc", 0.5, live_snapshot, sizing="fixed")
    assert plan["volume"] == 0.02


def test_slow_analysis_cannot_publish_an_expired_entry(monkeypatch, live_snapshot):
    times = iter(
        [
            pd.Timestamp("2026-10-29T08:44:35Z").to_pydatetime(),
            pd.Timestamp("2026-10-29T08:44:55Z").to_pydatetime(),
        ]
    )

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return next(times)

    monkeypatch.setattr(assistant, "datetime", Clock)
    plan = assistant.snapshot("XAUUSDc", 0.5, live_snapshot, sizing="fixed")
    assert plan["status"] == "BLOCKED"
    assert plan["volume"] is None
    assert "expired" in plan["reason"]


def test_log_summary_never_connects_to_mt5(monkeypatch, tmp_path):
    from unittest.mock import Mock

    connect = Mock()
    monkeypatch.setattr(assistant.mt5, "initialize", connect, raising=False)
    monkeypatch.setattr(
        "sys.argv",
        ["run_mt5_assistant.py", "--log-summary", "--log-file", str(tmp_path / "missing.jsonl")],
    )
    assistant.main()
    connect.assert_not_called()


def test_log_write_failure_does_not_hide_analysis(monkeypatch, capsys):
    from unittest.mock import Mock

    monkeypatch.setattr(
        assistant, "mt5", SimpleNamespace(initialize=lambda **kwargs: True, shutdown=lambda: None)
    )
    monkeypatch.setattr(
        assistant,
        "snapshot",
        lambda *args, **kwargs: {"symbol": "XAUUSDc", "status": "WAIT", "reason": "No valid setup"},
    )
    monkeypatch.setattr(assistant, "record_analysis", Mock(side_effect=OSError("disk full")))
    monkeypatch.setattr("sys.argv", ["run_mt5_assistant.py", "--once", "--color", "never"])
    assistant.main()
    text = capsys.readouterr().out
    assert "WAIT" in text and "Khong ghi duoc log" in text
