"""Conservative fractional Kelly estimates from strategy-specific net R results."""

import csv
import math
from datetime import datetime, timezone
from decimal import ROUND_FLOOR, Decimal
from pathlib import Path

STRATEGY_ID = "m1_pullback_breakout_v1"


def estimate_kelly(
    results, *, fraction=0.25, risk_cap_percent=0.5, min_trades=50, payoff_ceiling=None
):
    if not 0 < fraction <= 1 or not 0 < risk_cap_percent <= 5 or min_trades < 30:
        raise ValueError("Invalid Kelly settings: fraction (0,1], cap (0,5]%, minimum >=30")
    values = [float(value) for value in results]
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Trade results must be finite")
    n = len(values)
    report = {
        "status": "INSUFFICIENT_DATA",
        "trades": n,
        "min_trades": min_trades,
        "fractional_kelly": fraction,
        "risk_cap_percent": risk_cap_percent,
        "risk_percent": 0.0,
    }
    if n < min_trades:
        return report
    wins = [value for value in values if value > 0]
    losses = [-value for value in values if value < 0]
    if not wins or not losses:
        report["status"] = "UNBALANCED_SAMPLE"
        return report
    p = len(wins) / n
    payoff = (math.fsum(wins) / len(wins)) / (math.fsum(losses) / len(losses))
    if not math.isfinite(payoff) or payoff <= 0:
        raise ValueError("Invalid historical payoff ratio")
    if payoff_ceiling is not None:
        if not math.isfinite(payoff_ceiling) or payoff_ceiling <= 0:
            raise ValueError("Payoff ceiling must be finite and positive")
        payoff = min(payoff, payoff_ceiling)
    # 95% Wilson lower bound; breakeven trades count against the win probability.
    z = 1.96
    lower = (p + z * z / (2 * n) - z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / (
        1 + z * z / n
    )
    full = p - (1 - p) / payoff
    conservative = lower - (1 - lower) / payoff
    selected = min(risk_cap_percent, max(0.0, conservative) * fraction * 100)
    report.update(
        status="READY" if selected > 0 else "NO_EDGE",
        win_rate=p,
        conservative_win_rate=lower,
        win_rate_upper=(p + z * z / (2 * n) + z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)))
        / (1 + z * z / n),
        payoff_ratio=payoff,
        full_kelly=full,
        conservative_kelly=conservative,
        risk_percent=selected,
    )
    return report


def load_results(path, symbol, *, window=200, max_age_days=180, now=None, strategy_id=STRATEGY_ID):
    """Require one fully closed trade per row, normalized by its initial cash risk."""
    now = now or datetime.now(timezone.utc)
    records = []
    seen = set()
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"trade_id", "closed_at_utc", "symbol", "strategy_id", "net_r"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("Kelly CSV requires: " + ", ".join(sorted(required)))
        for row in reader:
            if row["symbol"] != symbol or row["strategy_id"] != strategy_id:
                continue
            identity = row["trade_id"].strip()
            if not identity or identity in seen:
                raise ValueError("Missing or duplicate trade_id in Kelly history")
            seen.add(identity)
            closed = datetime.fromisoformat(row["closed_at_utc"].replace("Z", "+00:00"))
            if closed.tzinfo is None or closed > now:
                raise ValueError("Kelly close timestamps must be timezone-aware and not future")
            result = float(row["net_r"])
            if not math.isfinite(result):
                raise ValueError("Invalid net_r in Kelly history")
            if (now - closed).total_seconds() <= max_age_days * 86400:
                records.append((closed, identity, result))
    records.sort()
    return [record[2] for record in records[-window:]]


def size_with_broker(
    *,
    equity,
    risk_percent,
    free_margin,
    volume_min,
    volume_max,
    volume_step,
    loss_for_volume,
    margin_for_volume,
    cost_per_lot=0.0,
):
    """Callbacks must calculate loss/margin in account currency; never send orders."""
    inputs = (equity, risk_percent, free_margin, volume_min, volume_max, volume_step)
    if not all(math.isfinite(x) and x > 0 for x in inputs) or volume_max < volume_min:
        raise ValueError("Invalid equity, margin or broker volume specifications")
    if not math.isfinite(cost_per_lot) or cost_per_lot < 0:
        raise ValueError("Cost per lot must be finite and nonnegative")
    budget = equity * risk_percent / 100
    probe = loss_for_volume(volume_min)
    if probe is None or not math.isfinite(probe) or probe <= 0:
        raise ValueError("Broker could not calculate stop loss")
    loss_per_lot = probe / volume_min + cost_per_lot

    def rounded(value):
        return float(
            (Decimal(str(value)) / Decimal(str(volume_step))).to_integral_value(
                rounding=ROUND_FLOOR
            )
            * Decimal(str(volume_step))
        )

    volume = rounded(min(budget / loss_per_lot, volume_max))
    if volume < volume_min:
        raise ValueError("Minimum lot exceeds Kelly risk budget")
    margin = margin_for_volume(volume)
    if margin is None or not math.isfinite(margin) or margin < 0:
        raise ValueError("Broker could not calculate margin")
    # Keep half of currently free margin available as a buffer.
    if margin > free_margin * 0.5:
        volume = rounded(volume * free_margin * 0.5 / margin)
    if volume < volume_min:
        raise ValueError("Insufficient free margin for minimum lot")
    loss = loss_for_volume(volume)
    margin = margin_for_volume(volume)
    if loss is None or margin is None or not all(math.isfinite(x) for x in (loss, margin)):
        raise ValueError("Broker calculation failed for final volume")
    loss += cost_per_lot * volume
    if loss <= 0 or loss > budget + 1e-8 or margin < 0 or margin > free_margin * 0.5 + 1e-8:
        raise ValueError("Final lot exceeds risk or margin budget")
    return {
        "volume": volume,
        "estimated_risk": loss,
        "risk_budget": budget,
        "estimated_margin": margin,
        "effective_risk_percent": loss / equity * 100,
    }
