"""Build reviewable entry plans; never submit orders."""

import math
from dataclasses import asdict, dataclass
from decimal import ROUND_FLOOR, Decimal
from math import isfinite

from src.strategies.xauusd_m1_scalper import ScalperSignal


@dataclass(frozen=True)
class EntryPlan:
    status: str
    reason: str
    side: str = "WAIT"
    entry: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    reward_risk: float | None = None
    volume: float | None = None
    estimated_risk: float | None = None

    def to_dict(self):
        return asdict(self)


def build_entry_plan(
    signal: ScalperSignal,
    quote: dict,
    *,
    equity: float,
    risk_percent: float = 0.5,
    min_reward_risk: float = 1.5,
) -> EntryPlan:
    """Quote tick_value must be loss value per lot in the account currency."""
    if signal.direction == 0:
        return EntryPlan("WAIT", signal.reason)
    try:
        keys = ("bid", "ask", "tick_size", "tick_value", "volume_min", "volume_max", "volume_step")
        bid, ask, tick_size, tick_value, vmin, vmax, step = (float(quote[key]) for key in keys)
        sl, tp = float(signal.stop_loss), float(signal.take_profit)
        values = (
            bid,
            ask,
            tick_size,
            tick_value,
            vmin,
            vmax,
            step,
            equity,
            risk_percent,
            min_reward_risk,
            sl,
            tp,
        )
        if not all(isfinite(v) and v > 0 for v in values):
            raise ValueError("Values must be finite and positive")
        if ask < bid or vmax < vmin or risk_percent > 100 or min_reward_risk < 1:
            raise ValueError("Invalid quote or risk settings")
        if signal.direction not in (-1, 1):
            raise ValueError("Invalid direction")
        entry = ask if signal.direction == 1 else bid
        risk = signal.direction * (entry - sl)
        reward = signal.direction * (tp - entry)
        if risk <= 0 or reward <= 0 or reward / risk < min_reward_risk:
            return EntryPlan("BLOCKED", "Live entry invalidates SL/TP or minimum reward/risk")
        budget = equity * risk_percent / 100
        loss_per_lot = risk / tick_size * tick_value
        raw_volume = min(budget / loss_per_lot, vmax)
        volume = float(
            (Decimal(str(raw_volume)) / Decimal(str(step))).to_integral_value(rounding=ROUND_FLOOR)
            * Decimal(str(step))
        )
        if volume < vmin or volume <= 0:
            return EntryPlan("BLOCKED", "Minimum broker volume exceeds risk budget")
        return EntryPlan(
            "REVIEW",
            signal.reason,
            "BUY" if signal.direction == 1 else "SELL",
            entry,
            sl,
            tp,
            reward / risk,
            volume,
            volume * loss_per_lot,
        )
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        return EntryPlan("BLOCKED", f"Invalid entry inputs: {exc}")


def future_entry(signal, quote, candle, equity, risk_percent, risk_reward=2.0):
    """Conditional breakout scenario, not a forecast or an order."""
    if signal.direction == 0:
        return {"status": "WAIT", "reason": signal.reason}
    direction = signal.direction
    step = quote["tick_size"]
    spread = quote["ask"] - quote["bid"]
    minimum_distance = quote.get("minimum_stop_distance", 0)
    if (
        direction not in (-1, 1)
        or not all(
            math.isfinite(value) and value > 0
            for value in (step, quote["bid"], quote["ask"], candle["high"], candle["low"])
        )
        or spread < 0
    ):
        raise ValueError("Invalid quote for conditional entry")
    buffer = max(step, minimum_distance)
    if direction == 1:
        trigger = (
            math.ceil(max(quote["ask"] + buffer, candle["high"] + spread + step) / step) * step
        )
    else:
        trigger = math.floor(min(quote["bid"] - buffer, candle["low"] - step) / step) * step
    stop = signal.stop_loss
    if stop is None or not math.isfinite(stop) or stop <= 0 or direction * (trigger - stop) <= 0:
        raise ValueError("Invalid stop for conditional entry")
    if direction == 1:
        stop = math.floor(min(stop, trigger - minimum_distance) / step) * step
    else:
        stop = math.ceil(max(stop, trigger + minimum_distance) / step) * step
    target = trigger + direction * abs(trigger - stop) * risk_reward
    target = (math.ceil(target / step) if direction == 1 else math.floor(target / step)) * step
    if not math.isfinite(target) or target <= 0:
        raise ValueError("Invalid target for conditional entry")
    plan = {
        "status": "REVIEW",
        "reason": signal.reason,
        "side": "BUY" if direction == 1 else "SELL",
        "entry": trigger,
        "stop_loss": stop,
        "take_profit": target,
        "reward_risk": risk_reward,
        "volume": None,
        "estimated_risk": None,
    }
    if math.isfinite(equity) and equity > 0:
        adjusted = ScalperSignal(direction, signal.confidence, stop, target, signal.reason)
        entry_quote = dict(quote)
        entry_quote.update(
            bid=trigger - spread if direction == 1 else trigger,
            ask=trigger if direction == 1 else trigger + spread,
        )
        plan = build_entry_plan(
            adjusted, entry_quote, equity=equity, risk_percent=risk_percent
        ).to_dict()
    else:
        plan["sizing_note"] = "Equity is zero; analysis only, no lot recommendation"
    plan.update(
        entry_type="BUY_STOP" if direction == 1 else "SELL_STOP",
        trigger_quote="ASK" if direction == 1 else "BID",
        exit_action="SELL_TO_CLOSE" if direction == 1 else "BUY_TO_CLOSE",
        scenario="Conditional price scenario; not a guaranteed forecast",
        entry_details={
            "trigger_price": trigger,
            "signal_high": float(candle["high"]),
            "signal_low": float(candle["low"]),
            "spread_price": float(spread),
            "tick_size": float(step),
            "minimum_stop_distance": float(minimum_distance),
            "risk_distance": float(abs(trigger - stop)),
            "reward_distance": float(abs(target - trigger)),
            "trigger_rule": "Ask vuot high nen + spread + tick; thoa khoang cach broker" if direction == 1 else "Bid xuyen low nen - tick; thoa khoang cach broker",
            "stop_rule": "SL theo cau truc chien luoc, lam tron tick; khong doi SL xa hon sau khi vao",
            "target_rule": f"TP theo entry va SL, RR ke hoach {risk_reward:g}R truoc phi",
            "cancel_rule": "Chi xem xet khi setup con hop le; huy ke hoach khi het han snapshot, gia/SL/TP khong con hop le",
        },
    )
    return plan
