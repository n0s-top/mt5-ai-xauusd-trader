from types import SimpleNamespace

import pytest

from src.strategies.account_risk import assess_exposure


def assess(positions=(), orders=(), **kwargs):
    settings = {
        "equity": 10000,
        "cap_percent": 2,
        "symbol": "XAUUSDc",
        "calc_profit": lambda side, symbol, volume, price, stop: (
            (stop - price) * volume * 100 * (1 if side == 0 else -1)
        ),
    }
    settings.update(kwargs)
    return assess_exposure(positions, orders, **settings)


def position(**kwargs):
    defaults = {
        "type": 0,
        "symbol": "XAUUSDc",
        "price_open": 1990,
        "price_current": 2000,
        "sl": 1995,
        "volume": 0.1,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_current_equity_risk_and_pending_risk_are_added_without_hedge_offset():
    pending = SimpleNamespace(
        type=5, symbol="XAUUSDc", price_open=1998, sl=2003, volume_current=0.1
    )
    report = assess([position()], [pending])
    assert report["stop_risk"] == 100
    assert report["used_percent"] == 1
    assert report["available_percent"] == 1
    assert report["buy_volume"] == 0.1 and report["sell_volume"] == 0.1


def test_all_symbols_contribute_to_risk_but_not_symbol_volume():
    report = assess([position(symbol="OTHER")])
    assert report["stop_risk"] == 50
    assert report["buy_volume"] == 0


@pytest.mark.parametrize(
    "changes", [{"sl": 0}, {"sl": 2001}, {"type": 99}, {"volume": float("nan")}]
)
def test_unknown_or_unprotected_risk_blocks_budget(changes):
    report = assess([position(**changes)])
    assert report["status"] == "UNKNOWN" and report["available_percent"] == 0


def test_read_failure_is_not_treated_as_empty_account():
    assert assess(None)["status"] == "UNKNOWN"
    assert assess(orders=None)["status"] == "UNKNOWN"
    assert assess([position()], calc_profit=lambda *args: None)["status"] == "UNKNOWN"


def test_budget_exhaustion_and_zero_equity():
    assert assess([position(volume=1)])["status"] == "LIMIT_REACHED"
    assert assess(equity=0)["status"] == "NO_EQUITY"


def test_cost_reserve_covers_positions_and_pending_orders_of_selected_symbol():
    pending = SimpleNamespace(
        type=5, symbol="XAUUSDc", price_open=1998, sl=2003, volume_current=0.2
    )
    report = assess([position(), position(symbol="OTHER")], [pending], cost_per_lot=10)
    assert report["cost_reserve"] == pytest.approx(3)
    assert report["stop_risk"] == pytest.approx(203)
    assert report["status"] == "LIMIT_REACHED"
    assert report["available_percent"] == 0


@pytest.mark.parametrize("cost", [-1, float("nan"), float("inf")])
def test_invalid_cost_reserve_is_rejected(cost):
    with pytest.raises(ValueError, match="Cost per lot"):
        assess(cost_per_lot=cost)
