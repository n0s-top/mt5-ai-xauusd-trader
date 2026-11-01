import pytest

from src.strategies.entry_support import build_entry_plan
from src.strategies.xauusd_m1_scalper import ScalperSignal


def quote():
    return dict(bid=2000, ask=2000.2, tick_size=0.01, tick_value=1,
                volume_min=0.01, volume_max=100, volume_step=0.01)


@pytest.mark.parametrize("direction,sl,tp", [(1, 1998, 2005), (-1, 2002, 1995)])
def test_live_price_and_risk_budget(direction, sl, tp):
    plan = build_entry_plan(ScalperSignal(direction, 0.6, sl, tp, "setup"),
                            quote(), equity=10000)
    assert plan.status == "REVIEW"
    assert plan.entry == (2000.2 if direction == 1 else 2000)
    assert 0 < plan.estimated_risk <= 50
    assert plan.reward_risk >= 1.5


@pytest.mark.parametrize("change", [{"tick_value": 0}, {"bid": float("nan")},
                                    {"ask": 2004}, {"volume_min": 1}])
def test_blocks_unsafe_entries(change):
    snapshot = quote()
    snapshot.update(change)
    plan = build_entry_plan(ScalperSignal(1, 0.6, 1998, 2005, "setup"),
                            snapshot, equity=10000)
    assert plan.status == "BLOCKED"
    assert plan.volume is None


def test_hold_needs_no_quote():
    assert build_entry_plan(ScalperSignal(0, 0, None, None, "No setup"), {},
                            equity=10000).status == "WAIT"


@pytest.mark.parametrize("direction", [1, -1])
def test_future_entry_explains_actual_rounded_prices(direction):
    from src.strategies.entry_support import future_entry
    from src.strategies.xauusd_m1_scalper import ScalperSignal

    plan = future_entry(ScalperSignal(direction, .6, 1998 if direction == 1 else 2002, None, "test"),
                        {"bid": 2000., "ask": 2000.24, "tick_size": .001},
                        {"high": 2001., "low": 1999.}, 0, .5)
    detail = plan["entry_details"]
    assert detail["trigger_price"] == plan["entry"]
    assert detail["risk_distance"] == pytest.approx(abs(plan["entry"] - plan["stop_loss"]))
    assert detail["reward_distance"] == pytest.approx(abs(plan["take_profit"] - plan["entry"]))
    assert plan["trigger_quote"] == ("ASK" if direction == 1 else "BID")
