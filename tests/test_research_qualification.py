from src.research.qualification import assess_research


def assess(**changes):
    stats = dict(trades=100, expectancy_r=.1, profit_factor=1.2, return_percent=3)
    stats.update(changes)
    return assess_research({"results": {"candidate": {"development": {}, "holdout": stats}}})["candidate"]


def test_positive_closed_returns_cannot_hide_unresolved_position():
    assert assess(unresolved_positions=1)["status"] == "INCOMPLETE_DATA"


def test_small_sample_is_not_qualified():
    assert assess(trades=7)["status"] == "INSUFFICIENT_SAMPLE"


def test_negative_expectancy_is_rejected():
    assert assess(expectancy_r=-.1)["status"] == "NO_OBSERVED_EDGE"


def test_positive_backtest_still_needs_forward_validation():
    report = assess()
    assert report["status"] == "REQUIRES_STRESS_AND_FORWARD_TEST"
    assert not report["auto_promote"]
    assert not report["live_profitability_verified"]
