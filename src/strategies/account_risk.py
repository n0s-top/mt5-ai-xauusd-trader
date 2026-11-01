"""Account-wide gross stop risk estimates, without offsetting hedged positions."""

import math


def assess_exposure(
    positions, orders, *, equity, cap_percent, symbol, calc_profit, cost_per_lot=0.0
):
    """Reserve configured round-trip costs for the selected symbol conservatively."""
    if not math.isfinite(cap_percent) or not 0 < cap_percent <= 10:
        raise ValueError("Account risk cap must be in (0, 10]%")
    if not math.isfinite(cost_per_lot) or cost_per_lot < 0:
        raise ValueError("Cost per lot must be finite and nonnegative")
    report = {
        "status": "READY",
        "positions": 0,
        "orders": 0,
        "stop_risk": 0.0,
        "cost_reserve": 0.0,
        "available_percent": 0.0,
        "cap_percent": cap_percent,
        "buy_volume": 0.0,
        "sell_volume": 0.0,
    }
    if positions is None or orders is None:
        return dict(
            report, status="UNKNOWN", reason="Cannot read all open positions/pending orders"
        )
    report.update(positions=len(positions), orders=len(orders))
    if not math.isfinite(equity) or equity <= 0:
        return dict(report, status="NO_EQUITY", reason="Equity must be positive")
    try:
        for pending, collection in ((False, positions), (True, orders)):
            for item in collection:
                if item.type not in ((2, 3, 4, 5) if pending else (0, 1)):
                    raise ValueError("Unsupported order type; stop risk is unknown")
                buy = item.type in (0, 2, 4)
                action = 0 if buy else 1
                volume = item.volume_current if pending else item.volume
                price = item.price_open if pending else item.price_current
                stop = item.sl
                if not all(math.isfinite(v) and v > 0 for v in (volume, price, stop)):
                    raise ValueError("An existing position/order has no valid SL or price")
                # Equity already includes floating P&L: measure further loss from current price.
                if (buy and stop >= price) or (not buy and stop <= price):
                    raise ValueError("An existing SL is already crossed or invalid")
                profit = calc_profit(action, item.symbol, volume, price, stop)
                if profit is None or not math.isfinite(profit) or profit > 0:
                    raise ValueError("Cannot calculate existing stop risk")
                report["stop_risk"] += -profit
                if item.symbol == symbol:
                    report["buy_volume" if buy else "sell_volume"] += volume
                    cost = cost_per_lot * volume
                    report["cost_reserve"] += cost
                    report["stop_risk"] += cost
        if not math.isfinite(report["stop_risk"]):
            raise ValueError("Nonfinite account stop risk")
        report["used_percent"] = report["stop_risk"] / equity * 100
        report["available_percent"] = max(0.0, cap_percent - report["used_percent"])
        if report["available_percent"] == 0:
            report.update(status="LIMIT_REACHED", reason="Account stop risk cap is exhausted")
    except (ValueError, TypeError, AttributeError, OverflowError) as exc:
        report.update(status="UNKNOWN", available_percent=0.0, reason=str(exc))
    return report
