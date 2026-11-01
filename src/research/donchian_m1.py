"""Causal Donchian 55/20 on M1 bars, with explicit Bid/Ask OHLC execution.

This is a minute-horizon adaptation, not the published daily Turtle strategy.
"""

import math

import numpy as np
import pandas as pd

from src.research.published_strategies import validate_daily, wilder_atr


def prepare(frame, tick_size=0.001):
    frame = validate_daily(frame)
    if not math.isfinite(tick_size) or tick_size <= 0:
        raise ValueError("Positive tick size required")
    if (frame.index != frame.index.floor("min")).any():
        raise ValueError("M1 opening timestamps required")
    times = frame.index.as_unit("s").asi8
    step = pd.Series(times, index=frame.index).diff()
    return {
        "index": frame.index,
        "times": times,
        **{key: frame[key].to_numpy(dtype=float) for key in ("open", "high", "low", "close")},
        "upper": frame.high.rolling(55).max().shift().to_numpy() + tick_size,
        "lower": frame.low.rolling(55).min().shift().to_numpy() - tick_size,
        "exit_upper": frame.high.rolling(20).max().shift().to_numpy(),
        "exit_lower": frame.low.rolling(20).min().shift().to_numpy(),
        "atr": wilder_atr(frame).shift().to_numpy(),
        "continuous": (step.rolling(55).max() == 60).to_numpy(),
        "tick_size": tick_size,
    }


def run(
    data,
    spreads,
    begin,
    end,
    *,
    fee_price=0.0,
    slippage_ticks=2,
    annual_carry=0.0,
    risk_percent=0.5,
    initial_equity=10000.0,
):
    """Single unit, 2 ATR initial stop, opposite 20-bar exit; no fixed TP.

    Stop/channel is active during a held bar. No re-entry after an exit within
    that bar. Unknown entry/stop ordering is adverse. Gaps exit at observed open.
    Entry size is a continuous fill-time proxy, not a pre-submitted broker lot.
    """
    count = len(data["index"])
    spread = np.asarray(spreads, dtype=float)
    if len(spread) != count or not np.isfinite(spread).all() or (spread < 0).any():
        raise ValueError("Invalid or misaligned spreads")
    if not 55 <= begin < end <= count:
        raise ValueError("Invalid evaluation interval")
    if not all(math.isfinite(x) and x >= 0 for x in (fee_price, slippage_ticks, annual_carry)):
        raise ValueError("Invalid execution costs")
    if (
        not math.isfinite(risk_percent)
        or not 0 < risk_percent <= 0.5
        or not math.isfinite(initial_equity)
        or initial_equity <= 0
    ):
        raise ValueError("Invalid initial equity/risk")
    op, hi, lo, cl = (data[key] for key in ("open", "high", "low", "close"))
    upper, lower, ex_hi, ex_lo, atr = (
        data[key] for key in ("upper", "lower", "exit_upper", "exit_lower", "atr")
    )
    times, index = data["times"], data["index"]
    slip = slippage_ticks * data["tick_size"]
    cash, quantity, direction, stop = initial_equity, 0.0, 0, 0.0
    curve = np.full(end - begin, initial_equity, dtype=float)
    entry = None
    trades = []
    carry_total = commission_total = 0.0
    candidates = np.flatnonzero(data["continuous"] & (atr > 0) & ((hi >= upper) | (lo <= lower)))

    def close_position(i, reference, reason, ambiguous=False):
        nonlocal cash, quantity, entry, commission_total
        price = reference - direction * slip
        commission = abs(quantity) * fee_price / 2
        cash += quantity * price - commission
        commission_total += commission
        net = cash - entry["equity_before_entry"]
        trades.append(
            {
                "entry_time_utc": index[entry["index"]].isoformat(),
                "exit_time_utc": index[i].isoformat(),
                "side": "BUY" if direction == 1 else "SELL",
                "entry": entry["price"],
                "exit_price": price,
                "stop_loss": entry["stop"],
                "ounces": abs(quantity),
                "initial_risk": entry["risk"],
                "net_pnl": net,
                "net_r": net / entry["risk"],
                "carry_cost": entry["carry"],
                "commission": entry["commission"] + commission,
                "outcome": reason,
                "ambiguous_path": bool(ambiguous),
                "holding_minutes": (times[i] - times[entry["index"]]) / 60,
            }
        )
        quantity, entry = 0.0, None

    i = begin
    while i < end:
        if quantity == 0:
            offset = candidates.searchsorted(i)
            next_i = int(candidates[offset]) if offset < len(candidates) else end
            next_i = min(next_i, end)
            curve[i - begin : next_i - begin] = cash
            i = next_i
            if i >= end:
                break
        exited = False
        if quantity:
            elapsed = times[i] - times[i - 1]
            financing = abs(quantity) * cl[i - 1] * annual_carry * elapsed / (365.25 * 86400)
            cash -= financing
            entry["carry"] += financing
            carry_total += financing
            if elapsed != 60:
                # Unknown missing intraminute paths are not invented or held flat.
                close_position(i, op[i] + (spread[i] if direction == -1 else 0), "DATA_GAP")
                exited = True
            else:
                # Channel orders are based on previous bars/spread. Short stops
                # execute on Ask, long stops on Bid, using the fill bar spread.
                barrier = (
                    max(stop, ex_lo[i]) if direction == 1 else min(stop, ex_hi[i] + spread[i - 1])
                )
                touched = lo[i] <= barrier if direction == 1 else hi[i] + spread[i] >= barrier
                if touched:
                    opened = op[i] + (spread[i] if direction == -1 else 0)
                    fill = min(opened, barrier) if direction == 1 else max(opened, barrier)
                    close_position(i, fill, "STOP_OR_CHANNEL")
                    exited = True
        if not quantity and not exited:
            up, down = hi[i] >= upper[i], lo[i] <= lower[i]
            direction = 1 if up else -1
            reference = max(op[i], upper[i]) if up else min(op[i], lower[i])
            price = reference + (spread[i] if up else 0) + direction * slip
            stop = reference - 2 * atr[i] if up else reference + 2 * atr[i] + spread[i]
            distance = direction * (price - (stop - direction * slip)) + fee_price
            if price <= 0 or stop <= 0 or not math.isfinite(distance) or distance <= 0 or cash <= 0:
                curve[i - begin] = cash
                i += 1
                continue
            amount = min(cash * risk_percent / 100 / distance, 2 * cash / price)
            equity_before = cash
            commission = amount * fee_price / 2
            quantity = direction * amount
            cash -= quantity * price + commission
            commission_total += commission
            entry = {
                "index": i,
                "price": price,
                "stop": stop,
                "risk": amount * distance,
                "equity_before_entry": equity_before,
                "carry": 0.0,
                "commission": commission,
            }
            # Unknown ordering of two breakouts or entry and protective stop is
            # charged an adverse stop outcome; never use a favorable OHLC path.
            touched = lo[i] <= stop if up else hi[i] + spread[i] >= stop
            if (up and down) or touched:
                close_position(i, stop, "AMBIGUOUS_ENTRY_STOP", ambiguous=True)
        marked = cash + quantity * (cl[i] + (spread[i] if quantity < 0 else 0))
        curve[i - begin] = marked
        if marked <= 0:
            if quantity:
                close_position(i, cl[i] + (spread[i] if direction == -1 else 0), "EQUITY_EXHAUSTED")
            curve[i - begin :] = cash
            break
        i += 1
    if quantity:
        close_position(
            end - 1, cl[end - 1] + (spread[end - 1] if direction == -1 else 0), "SEGMENT_END"
        )
        curve[-1] = cash
    pnl = np.array([t["net_pnl"] for t in trades])
    peaks = np.maximum.accumulate(np.r_[initial_equity, curve])
    dd = float(np.max(1 - np.r_[initial_equity, curve] / peaks) * 100)
    profit, loss = float(pnl[pnl > 0].sum()), float(-pnl[pnl < 0].sum())
    stats = {
        "trades": len(trades),
        "win_rate": float(np.mean(pnl > 0)) if len(pnl) else None,
        "total_r": float(sum(t["net_r"] for t in trades)),
        "expectancy_r": float(np.mean([t["net_r"] for t in trades])) if trades else None,
        "profit_factor": profit / loss if loss else None,
        "net_profit": float(curve[-1] - initial_equity),
        "ending_equity": float(curve[-1]),
        "return_percent": float((curve[-1] / initial_equity - 1) * 100),
        "max_m1_close_drawdown_percent": dd,
        "ambiguous_trades": sum(t["ambiguous_path"] for t in trades),
        "gap_exits": sum(t["outcome"] == "DATA_GAP" for t in trades),
        "commission_cost": float(commission_total),
        "carry_cost": float(carry_total),
        "initial_equity": initial_equity,
        "risk_percent": risk_percent,
        "notional_cap": 2.0,
        "equity_exhausted": bool((curve <= 0).any()),
        "start_utc": index[begin].isoformat(),
        "end_utc": index[end - 1].isoformat(),
    }
    return stats, trades, curve
