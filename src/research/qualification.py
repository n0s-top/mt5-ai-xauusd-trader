"""Describe research readiness; never promote a strategy or place orders."""

import math


def assess_research(result, minimum_trades=30):
    """A sample-count screen is operational, not statistical significance."""
    assessment = {}
    for name, segments in result["results"].items():
        holdout = segments["holdout"]
        incomplete = any(s.get("missing_decision_quotes", 0) or s.get("unknown_tick_windows", 0)
                         or s.get("unresolved_positions", 0) for s in segments.values())
        metrics = [holdout.get("expectancy_r"), holdout.get("profit_factor"), holdout.get("return_percent")]
        if incomplete:
            status = "INCOMPLETE_DATA"
        elif holdout["trades"] < minimum_trades:
            status = "INSUFFICIENT_SAMPLE"
        elif any(v is None or not math.isfinite(v) for v in metrics):
            status = "UNDEFINED_METRICS"
        elif metrics[0] <= 0 or metrics[1] <= 1 or metrics[2] <= 0:
            status = "NO_OBSERVED_EDGE"
        else:
            status = "REQUIRES_STRESS_AND_FORWARD_TEST"
        assessment[name] = dict(status=status, minimum_trades=minimum_trades,
                                auto_promote=False, live_profitability_verified=False)
    return assessment
