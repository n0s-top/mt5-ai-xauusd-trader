from datetime import datetime, timezone

import pytest

from src.strategies.kelly_sizing import STRATEGY_ID, estimate_kelly, load_results, size_with_broker


def test_quarter_kelly_conservative_probability_and_cap():
    report = estimate_kelly([2] * 60 + [-1] * 40)
    assert report["status"] == "READY"
    assert report["full_kelly"] == pytest.approx(0.4)
    assert report["conservative_win_rate"] < 0.6
    assert report["conservative_win_rate"] < report["win_rate"] < report["win_rate_upper"] <= 1
    assert report["risk_percent"] == 0.5


@pytest.mark.parametrize(
    "results,status",
    [
        ([2] * 10, "INSUFFICIENT_DATA"),
        ([2] * 50, "UNBALANCED_SAMPLE"),
        ([-1] * 50, "UNBALANCED_SAMPLE"),
        ([1] * 20 + [-1] * 80, "NO_EDGE"),
    ],
)
def test_no_lot_budget_without_evidence(results, status):
    report = estimate_kelly(results)
    assert report["status"] == status
    assert report["risk_percent"] == 0


def test_fraction_and_payoff_ceiling_reduce_budget():
    results = [3] * 55 + [-1] * 45
    full = estimate_kelly(results, fraction=1, risk_cap_percent=5)
    small = estimate_kelly(results, fraction=0.1, risk_cap_percent=5, payoff_ceiling=1.5)
    assert 0 < small["risk_percent"] < full["risk_percent"]
    assert small["payoff_ratio"] == 1.5


def test_nonfinite_results_rejected():
    with pytest.raises(ValueError):
        estimate_kelly([float("nan")] * 50)


def test_strategy_histories_are_not_mixed(tmp_path):
    path = tmp_path / "history.csv"
    path.write_text(
        "trade_id,closed_at_utc,symbol,strategy_id,net_r\n"
        f"a,2026-10-28T00:00:00Z,XAUUSDc,{STRATEGY_ID},2\n"
        "b,2026-10-28T00:00:00Z,XAUUSDc,adaptive_trend_breakout_v1,-1\n",
        encoding="utf-8",
    )
    now = datetime(2026, 10, 29, tzinfo=timezone.utc)
    assert load_results(path, "XAUUSDc", now=now) == [2]
    assert load_results(path, "XAUUSDc", now=now, strategy_id="adaptive_trend_breakout_v1") == [-1]


def test_history_filters_strategy_symbol_age_and_sorts(tmp_path):
    path = tmp_path / "history.csv"
    path.write_text(
        "trade_id,closed_at_utc,symbol,strategy_id,net_r\n"
        f"a,2026-10-28T00:00:00Z,XAUUSDc,{STRATEGY_ID},2\n"
        f"b,2026-10-27T00:00:00Z,XAUUSDc,{STRATEGY_ID},-1\n"
        "c,2026-10-28T00:00:00Z,XAUUSDc,other,10\n"
        f"d,2026-01-01T00:00:00Z,XAUUSDc,{STRATEGY_ID},99\n",
        encoding="utf-8",
    )
    assert load_results(path, "XAUUSDc", now=datetime(2026, 10, 29, tzinfo=timezone.utc)) == [-1, 2]


@pytest.mark.parametrize(
    "row", ["a,2026-10-28T00:00:00Z", "b,2027-01-01T00:00:00Z", "b,2026-10-28T00:00:00"]
)
def test_duplicate_or_invalid_time_rejected(tmp_path, row):
    path = tmp_path / "history.csv"
    path.write_text(
        "trade_id,closed_at_utc,symbol,strategy_id,net_r\n"
        f"a,2026-10-28T00:00:00Z,XAUUSDc,{STRATEGY_ID},2\n"
        f"{row},XAUUSDc,{STRATEGY_ID},-1\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_results(path, "XAUUSDc", now=datetime(2026, 10, 29, tzinfo=timezone.utc))


def sizing(**overrides):
    settings = {
        "equity": 10000,
        "risk_percent": 0.5,
        "free_margin": 10000,
        "volume_min": 0.01,
        "volume_max": 100,
        "volume_step": 0.01,
        "loss_for_volume": lambda v: v * 200,
        "margin_for_volume": lambda v: v * 1000,
        "cost_per_lot": 10,
    }
    settings.update(overrides)
    return size_with_broker(**settings)


def test_rounds_down_including_cost_and_respects_margin_buffer():
    result = sizing()
    assert result["volume"] == 0.23
    assert result["estimated_risk"] == pytest.approx(48.3)
    assert result["estimated_risk"] <= result["risk_budget"]
    constrained = sizing(free_margin=100)
    assert constrained["volume"] == 0.05
    assert constrained["estimated_margin"] == 50


@pytest.mark.parametrize(
    "overrides",
    [
        {"equity": 1},
        {"free_margin": 1},
        {"loss_for_volume": lambda v: None},
        {"margin_for_volume": lambda v: float("nan")},
    ],
)
def test_broker_failure_or_minimum_lot_blocks(overrides):
    with pytest.raises(ValueError):
        sizing(**overrides)
