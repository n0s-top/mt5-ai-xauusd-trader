from io import StringIO
from types import SimpleNamespace

import pandas as pd
import pytest
from rich.console import Console

from src.strategies.donchian_demo import (
    Donchian5520,
    channel_levels,
    closed_daily,
    snapshot_donchian,
)
from src.strategies.terminal_view import render_plan


@pytest.fixture
def feed():
    now = pd.Timestamp("2026-10-29T08:00:00Z").to_pydatetime()
    days = pd.bdate_range(end="2026-10-29", periods=120, tz="UTC")
    data = pd.DataFrame(
        {
            "time": days.as_unit("s").asi8,
            "open": 2000.0,
            "high": 2010.0,
            "low": 1990.0,
            "close": 2000.0,
        }
    )
    data.loc[data.index[-1], ["high", "low"]] = [2002.0, 1998.0]
    broker = SimpleNamespace(
        trade_tick_size=0.01,
        point=0.01,
        trade_stops_level=2,
        volume_min=0.01,
        volume_max=100,
        volume_step=0.01,
        volume_limit=0,
    )
    api = SimpleNamespace(
        ACCOUNT_TRADE_MODE_DEMO=0,
        ORDER_TYPE_BUY=0,
        ORDER_TYPE_SELL=1,
        TIMEFRAME_D1=1440,
        terminal_info=lambda: SimpleNamespace(connected=True),
        symbol_select=lambda *a: True,
        account_info=lambda: SimpleNamespace(
            trade_mode=0, equity=100000, margin_free=100000, currency="USD"
        ),
        symbol_info=lambda s: broker,
        symbol_info_tick=lambda s: SimpleNamespace(
            time=now.timestamp() - 1, bid=2000.0, ask=2000.1
        ),
        copy_rates_from_pos=lambda *a: data,
        positions_get=lambda: (),
        orders_get=lambda: (),
        history_deals_get=lambda *a: (),
        order_calc_profit=lambda action, symbol, volume, entry, exit: (
            (exit - entry) * volume * 100 * (1 if action == 0 else -1)
        ),
        order_calc_margin=lambda action, symbol, volume, entry: volume * 1000,
    )
    return api, data, broker, now


def snapshot(feed, **kwargs):
    api, _, _, now = feed
    return snapshot_donchian(api, "XAUUSD", 0.5, now=now, **kwargs)


def test_two_alternatives_use_closed_channels_and_fixed_risk_without_tp(feed):
    plan = snapshot(feed, cost_per_lot=10)
    assert plan["status"] == "REVIEW"
    assert plan["levels"]["entry_high_55"] == 2010
    assert plan["levels"]["atr20"] == pytest.approx(20)
    buy, sell = plan["entry_scenarios"]
    assert buy["entry"] == pytest.approx(2010.11)
    assert buy["stop_loss"] == pytest.approx(1970.01)
    assert sell["entry"] == pytest.approx(1989.99)
    assert sell["stop_loss"] == pytest.approx(2030.09)
    for candidate in (buy, sell):
        assert candidate["take_profit"] is None
        assert 0 < candidate["estimated_risk"] <= 500
        assert candidate["volume"] * 100 * candidate["entry"] <= 200000


def test_live_account_cannot_produce_demo_lot(feed):
    api, _, _, _ = feed
    api.account_info = lambda: SimpleNamespace(trade_mode=2)
    plan = snapshot(feed)
    assert plan["status"] == "BLOCKED"
    assert "DEMO" in plan["reason"]
    assert plan["entry_scenarios"] == []


def test_stale_quote_retains_levels_without_sizing(feed):
    api, _, _, now = feed
    api.symbol_info_tick = lambda s: SimpleNamespace(
        time=now.timestamp() - 100, bid=2000, ask=2000.1
    )
    plan = snapshot(feed)
    assert plan["status"] == "BLOCKED" and plan["levels"]
    assert plan["entry_scenarios"] == []
    assert "expires_at_utc" not in plan


def test_notional_cap_binds_when_atr_is_small(feed):
    _, data, _, _ = feed
    data["high"] = 2000.2
    data["low"] = 1999.8
    data.loc[data.index[-1], ["high", "low"]] = [2000.1, 1999.9]
    plan = snapshot(feed)
    assert plan["status"] == "REVIEW"
    for candidate in plan["entry_scenarios"]:
        assert candidate["volume"] * 100 * candidate["entry"] <= 200000


def test_management_calls_for_manual_exit_when_stop_is_crossed(feed):
    api, _, _, _ = feed
    api.positions_get = lambda: (SimpleNamespace(symbol="XAUUSD", ticket=7, type=0, sl=2001),)
    plan = snapshot(feed, position_ticket=7)
    assert plan["management"]["action"] == "EXIT_MANUAL_NOW"
    assert not plan["management"]["broker_distance_allows_modify"]


@pytest.mark.parametrize(
    "reason",
    ["position", "pending", "history_missing", "traded_today", "missed", "minimum_lot", "kelly"],
)
def test_no_duplicate_or_unsafe_entries(feed, reason):
    api, data, broker, _ = feed
    if reason == "position":
        api.positions_get = lambda: (SimpleNamespace(symbol="XAUUSD"),)
    elif reason == "pending":
        api.orders_get = lambda: (SimpleNamespace(symbol="XAUUSD"),)
    elif reason == "history_missing":
        api.history_deals_get = lambda *a: None
    elif reason == "traded_today":
        api.history_deals_get = lambda *a: (SimpleNamespace(symbol="XAUUSD"),)
    elif reason == "missed":
        data.loc[data.index[-1], "high"] = 2011
    elif reason == "minimum_lot":
        broker.volume_min = 2
    plan = snapshot(feed, sizing="kelly" if reason == "kelly" else "fixed")
    assert plan["status"] in ("BLOCKED", "WAIT")
    assert not any(p.get("volume") for p in plan["entry_scenarios"])


@pytest.mark.parametrize("buy", [True, False])
def test_management_never_loosens_existing_sl_and_has_no_entry(feed, buy):
    api, _, _, _ = feed
    old = 1995 if buy else 2005
    api.positions_get = lambda: (
        SimpleNamespace(symbol="XAUUSD", ticket=7, type=0 if buy else 1, sl=old),
    )
    plan = snapshot(feed, position_ticket=7)
    assert plan["status"] == "REVIEW"
    assert plan["management"]["suggested_sl"] == old
    assert plan["entry_scenarios"] == []


def test_sunday_stub_is_not_used_before_monday_has_closed():
    days = pd.bdate_range(end="2026-10-23", periods=60, tz="UTC")
    raw = pd.DataFrame(
        {"time": days.as_unit("s").asi8, "open": 100, "high": 101, "low": 99, "close": 100}
    )
    stub = pd.DataFrame(
        {
            "time": [int(pd.Timestamp("2026-10-25T00:00Z").timestamp())],
            "open": [100],
            "high": [500],
            "low": [99],
            "close": [100],
        }
    )
    closed = closed_daily(pd.concat([raw, stub]), pd.Timestamp("2026-10-26T08:00Z"))
    assert channel_levels(closed)["entry_high_55"] == 101


def test_daily_renderer_explains_no_fixed_tp(feed):
    stream = StringIO()
    render_plan(snapshot(feed), Console(file=stream, no_color=True, width=120))
    text = stream.getvalue()
    assert "DEMO" in text and "D1" in text and "Khong co TP co dinh" in text


def test_assistant_dispatches_without_m1_or_scalper_sizing(monkeypatch, feed):
    import run_mt5_assistant as assistant

    api, _, _, now = feed

    class Clock:
        @staticmethod
        def now(tz=None):
            return now

        fromisoformat = staticmethod(__import__("datetime").datetime.fromisoformat)

    monkeypatch.setattr(assistant, "datetime", Clock)
    monkeypatch.setattr(assistant, "mt5", api)
    monkeypatch.setattr(
        assistant, "future_entry", lambda *a, **k: pytest.fail("D1 must not use a fixed-TP M1 plan")
    )
    plan = assistant.snapshot("XAUUSD", 0.5, Donchian5520(), sizing="fixed")
    assert plan["strategy_id"] == Donchian5520.strategy_id
    assert plan["status"] == "REVIEW"


@pytest.mark.parametrize("strategy_args", [[], ["--strategy", "donchian_55_20"]])
def test_cli_defaults_donchian_to_fixed_sizing(monkeypatch, feed, strategy_args):
    import run_mt5_assistant as assistant

    api, _, _, _ = feed
    api.initialize = lambda **kwargs: True
    api.shutdown = lambda: None
    monkeypatch.setattr(assistant, "mt5", api)
    seen = []

    def capture(*args, **kwargs):
        assert isinstance(args[2], Donchian5520)
        seen.append(kwargs["sizing"])
        return {"symbol": "XAUUSD", "status": "BLOCKED", "reason": "test"}

    monkeypatch.setattr(assistant, "snapshot", capture)
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_mt5_assistant.py",
            *strategy_args,
            "--once",
            "--no-log",
            "--color",
            "never",
        ],
    )
    assistant.main()
    assert seen == ["fixed"]
