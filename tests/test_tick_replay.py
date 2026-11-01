import pandas as pd
import pytest

from src.research.tick_replay import TickReplay

DECISION = pd.Timestamp("2026-10-29T08:00:00Z")


def replay(rows):
    return TickReplay(
        pd.DataFrame(
            {
                "time_msc": [int(DECISION.timestamp() * 1000) + int(s * 1000) for s, _, _ in rows],
                "bid": [b for _, b, _ in rows],
                "ask": [a for _, _, a in rows],
            }
        )
    )


def run(ticks, side="BUY"):
    bars = pd.DataFrame(index=pd.date_range(DECISION, periods=3, freq="min"))
    plan = {
        "side": side,
        "entry": 100.0,
        "stop_loss": 99.0 if side == "BUY" else 101.0,
        "take_profit": 102.0 if side == "BUY" else 98.0,
    }
    return ticks.simulate(bars, 0, 3, plan, quote_time=DECISION, slippage=0.01, fee_price=0.02)


def test_trigger_after_fifteen_seconds_never_fills():
    ticks = replay([(0, 99.7, 99.8), (14.999, 99.8, 99.9), (15, 100, 100.1), (20, 102, 102.1)])
    assert run(ticks) is None


def test_fill_before_expiry_and_tp_before_sl_uses_tick_order():
    ticks = replay(
        [(0, 99.7, 99.8), (5, 100, 100.1), (6, 102.1, 102.2), (10, 98, 98.1), (16, 100, 100.1)]
    )
    trade = run(ticks)
    assert trade["outcome"] == "TP"
    assert trade["entry"] == pytest.approx(100.11)
    assert trade["exit_price"] == pytest.approx(101.99)


def test_short_uses_bid_for_entry_ask_for_stop_and_gap():
    ticks = replay([(0, 100.5, 100.6), (5, 99.9, 100), (6, 102, 102.1), (16, 102, 102.1)])
    trade = run(ticks, "SELL")
    assert trade["outcome"] == "SL"
    assert trade["entry"] == pytest.approx(99.89)
    assert trade["exit_price"] == pytest.approx(102.11)
    assert trade["net_r"] < -1


def test_missing_pending_coverage_is_unknown_not_unfilled():
    result = run(replay([(0, 99.7, 99.8), (4, 99.8, 99.9)]))
    assert result["unknown"] and not result["filled"]


def test_gap_after_fill_is_an_unresolved_position():
    result = run(replay([(0, 99.7, 99.8), (5, 100, 100.1), (16, 100, 100.1), (60, 98, 98.1)]))
    assert result["unknown"] and result["filled"]


def test_quote_at_decision_never_uses_future_tick():
    ticks = replay([(-1, 99.7, 99.8), (1, 102, 102.1)])
    quote = ticks.quote_at(DECISION)
    assert quote["ask"] == 99.8 and quote["time"] < DECISION
    assert ticks.quote_at(DECISION - pd.Timedelta(seconds=20)) is None


def test_invalid_quote_is_rejected():
    with pytest.raises(ValueError):
        replay([(0, 100, 99)])


def test_tick_on_shortened_quote_deadline_is_expired():
    ticks = replay([(-5, 99.7, 99.8), (10, 100, 100.1), (16, 100, 100.1)])
    bars = pd.DataFrame(index=pd.date_range(DECISION, periods=3, freq="min"))
    plan = {"side": "BUY", "entry": 100, "stop_loss": 99, "take_profit": 102}
    assert ticks.simulate(bars, 0, 3, plan, quote_time=DECISION - pd.Timedelta(seconds=5)) is None


def test_stop_before_target_is_resolved_in_actual_tick_order():
    trade = run(
        replay(
            [(0, 99.7, 99.8), (5, 100, 100.1), (6, 98.9, 99), (10, 102.1, 102.2), (16, 100, 100.1)]
        )
    )
    assert trade["outcome"] == "SL"


def test_segment_close_uses_last_in_segment_quote():
    ticks = replay(
        [(0, 99.7, 99.8), (5, 100, 100.1)]
        + [(second, 100, 100.1) for second in (16, 30, 60, 90, 120, 150, 179, 181)]
    )
    trade = run(ticks)
    assert trade["outcome"] == "SEGMENT_END"
    assert pd.Timestamp(trade["exit_time_utc"]) == DECISION + pd.Timedelta(seconds=179)


def test_gap_before_segment_end_cannot_be_hidden_by_next_segment_quote():
    ticks = replay(
        [(0, 99.7, 99.8), (5, 100, 100.1)]
        + [(second, 100, 100.1) for second in (16, 30, 60, 90, 120, 181)]
    )
    trade = run(ticks)
    assert trade["unknown"] and trade["filled"]
