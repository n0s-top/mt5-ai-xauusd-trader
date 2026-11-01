"""Fixed-rule gold adaptations of ORB, noise/VWAP and EMA pullback research.

US-equity stock selection and exchange volume are not replicated by spot gold.
All timestamps are bar openings; signals from closes execute next minute.
"""

import math

import numpy as np
import pandas as pd

from src.research.published_strategies import validate_daily, wilder_atr

METHODS = (
    "orb5",
    "orb15",
    "orb5_rvol_tick",
    "orb15_rvol_tick",
    "noise_vwap_tick",
    "ema_vwap15_tick_proxy",
)


def prepare(frame):
    frame = validate_daily(frame)
    if not (frame.index == frame.index.floor("min")).all():
        raise ValueError("M1 timestamps required")
    local = frame.index.tz_convert("America/New_York")
    minute = local.hour * 60 + local.minute - 570
    in_session = (minute >= 0) & (minute < 390) & (local.day_of_week < 5)
    data = frame.copy()
    data["minute"] = minute
    data["day"] = local.strftime("%Y-%m-%d")
    data["row"] = np.arange(len(data))
    data["volume"] = pd.to_numeric(data.get("tick_volume", pd.Series(0, index=data.index)))
    if not np.isfinite(data.volume).all() or (data.volume < 0).any():
        raise ValueError("Invalid tick volume")
    session = data.loc[in_session].copy()
    if session.empty:
        raise ValueError("No New York 09:30-16:00 weekday observations")
    daily = session.groupby("day", sort=True).agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        rows=("row", "count"),
    )
    daily.index = pd.DatetimeIndex(pd.to_datetime(daily.index, utc=True))
    atr = wilder_atr(daily, 14).shift()
    previous_close = daily.close.shift()
    lookup = {
        date.strftime("%Y-%m-%d"): (atr.loc[date], previous_close.loc[date]) for date in daily.index
    }
    volume_available = bool((session.volume > 0).all())
    pv = (session.high + session.low + session.close) / 3 * session.volume
    session["vwap"] = pv.groupby(session.day).cumsum() / session.volume.groupby(
        session.day
    ).cumsum().replace(0, np.nan)
    first_open = session.groupby("day").open.transform("first")
    session["move"] = (session.close / first_open - 1).abs()
    session["sigma"] = session.groupby("minute")["move"].transform(
        lambda x: x.shift().rolling(14, min_periods=14).mean()
    )
    result = {
        "index": frame.index,
        "time": frame.index.as_unit("s").asi8,
        **{k: frame[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close")},
        "minute": np.asarray(minute),
        "in_session": np.asarray(in_session),
        "day": data.day.to_numpy(),
        "volume_available": volume_available,
        "session_rows": len(session),
        "incomplete_sessions": int((daily.rows != 390).sum()),
        "plans": {},
    }
    for method in METHODS:
        result["plans"][method] = {
            "direction": np.full(len(frame), np.nan),
            "trigger": np.full(len(frame), np.nan),
            "stop": np.full(len(frame), np.nan),
            "expiry": np.zeros(len(frame), dtype=np.int64),
            "exit_direction": np.full(len(frame), np.nan),
        }
    opening_volumes = {5: [], 15: []}
    for day, group in session.groupby("day", sort=True):
        date = pd.Timestamp(day, tz="America/New_York")
        expiry = int((date + pd.Timedelta(hours=16)).tz_convert("UTC").timestamp())
        daily_atr, prev_close = lookup[day]
        for length in (5, 15):
            opening = group.loc[group.minute < length]
            complete = np.array_equal(opening.minute.to_numpy(), np.arange(length))
            volume = float(opening.volume.sum()) if complete else np.nan
            old = opening_volumes[length][-14:]
            rvol = (
                volume / np.mean(old)
                if len(old) == 14 and np.isfinite(old).all() and np.mean(old) > 0
                else np.nan
            )
            opening_volumes[length].append(volume)
            if not complete or not np.isfinite(daily_atr) or daily_atr <= 0:
                continue
            direction = np.sign(opening.close.iloc[-1] - opening.open.iloc[0])
            if not direction:
                continue
            rows = group.loc[group.minute >= length, "row"].to_numpy()
            trigger = (
                float(opening.high.max() + 0.001)
                if direction == 1
                else float(opening.low.min() - 0.001)
            )
            for filtered in (False, True):
                if filtered and (not volume_available or not np.isfinite(rvol) or rvol < 1):
                    continue
                method = f"orb{length}" + ("_rvol_tick" if filtered else "")
                plan = result["plans"][method]
                plan["direction"][rows] = direction
                plan["trigger"][rows] = trigger
                plan["stop"][rows] = 0.10 * daily_atr  # fixed distance at the fill
                plan["expiry"][rows] = expiry
        if volume_available and group.minute.iloc[0] == 0 and np.isfinite(prev_close):
            opened = float(group.open.iloc[0])
            for row in group.loc[(group.minute + 1) % 30 == 0].itertuples():
                if not np.isfinite(row.sigma) or not np.isfinite(row.vwap):
                    continue
                i = row.row + 1
                if (
                    i >= len(frame)
                    or result["time"][i] - int(row.Index.timestamp()) != 60
                    or result["time"][i] >= expiry
                ):
                    continue
                upper = max(opened, prev_close) * (1 + row.sigma)
                lower = min(opened, prev_close) * (1 - row.sigma)
                direction = (
                    1
                    if row.close > max(upper, row.vwap)
                    else -1
                    if row.close < min(lower, row.vwap)
                    else 0
                )
                plan = result["plans"]["noise_vwap_tick"]
                plan["direction"][i] = direction
                plan["stop"][i] = max(upper, row.vwap) if direction == 1 else min(lower, row.vwap)
                plan["expiry"][i] = expiry
    if volume_available:
        bars = frame.resample("15min").agg(
            {"open": "first", "high": "max", "low": "min", "close": "last"}
        )
        counts = frame.close.resample("15min").count()
        bars = bars.loc[counts == 15].copy()
        bars["ema50"] = bars.close.ewm(span=50, adjust=False, min_periods=50).mean()
        bars["ema200"] = bars.close.ewm(span=200, adjust=False, min_periods=200).mean()
        bars["atr"] = wilder_atr(bars, 14)
        bars["vwap"] = session.vwap.reindex(bars.index + pd.Timedelta(minutes=14)).to_numpy()
        plan = result["plans"]["ema_vwap15_tick_proxy"]
        for row in bars.dropna().itertuples():
            when = row.Index + pd.Timedelta(minutes=15)
            i = frame.index.get_indexer([when])[0]
            if i < 0 or not in_session[i]:
                continue
            direction = (
                1
                if row.close > row.ema200
                and row.ema50 > row.ema200
                and row.low <= row.ema50
                and row.close > row.ema50
                and row.close > row.open
                and row.close > row.vwap
                else -1
                if row.close < row.ema200
                and row.ema50 < row.ema200
                and row.high >= row.ema50
                and row.close < row.ema50
                and row.close < row.open
                and row.close < row.vwap
                else 0
            )
            if direction:
                plan["direction"][i] = direction
                plan["stop"][i] = (
                    row.low - 0.5 * row.atr if direction == 1 else row.high + 0.5 * row.atr
                )
            plan["exit_direction"][i] = np.sign(row.close - row.ema50)
            plan["expiry"][i] = int(
                (when.tz_convert("America/New_York").normalize() + pd.Timedelta(hours=16))
                .tz_convert("UTC")
                .timestamp()
            )
    return result


def run(data, method, spreads, begin, end, *, fee_price=0.10, annual_carry=0.03):
    if method not in METHODS:
        raise ValueError("Unknown method")
    if method not in ("orb5", "orb15") and not data["volume_available"]:
        raise ValueError("Observed positive volume required; no synthetic VWAP/RVOL")
    n = len(data["index"])
    spread = np.asarray(spreads, dtype=float)
    if (
        len(spread) != n
        or not np.isfinite(spread).all()
        or (spread < 0).any()
        or not 0 <= begin < end <= n
    ):
        raise ValueError("Invalid spread or interval")
    if not all(math.isfinite(v) and v >= 0 for v in (fee_price, annual_carry)):
        raise ValueError("Invalid costs")
    plan = data["plans"][method]
    op, hi, lo, cl, times = (data[k] for k in ("open", "high", "low", "close", "time"))
    index = data["index"]
    orb = method.startswith("orb")
    noise = method == "noise_vwap_tick"
    cash, quantity, direction = 10000.0, 0.0, 0
    stop = expiry = target = 0.0
    entry = None
    used = set()
    trades = []
    curve = np.full(end - begin, 10000.0)

    def close(i, reference, outcome, ambiguous=False):
        nonlocal cash, quantity, entry
        fill = reference - direction * 0.002
        commission = abs(quantity) * fee_price / 2
        cash += quantity * fill - commission
        pnl = cash - entry["capital"]
        trades.append(
            {
                "entry_time_utc": index[entry["i"]].isoformat(),
                "exit_time_utc": index[i].isoformat(),
                "side": "BUY" if direction == 1 else "SELL",
                "entry": entry["price"],
                "exit_price": fill,
                "ounces": abs(quantity),
                "initial_risk": entry["risk"],
                "net_pnl": pnl,
                "net_r": pnl / entry["risk"],
                "commission": entry["commission"] + commission,
                "carry_cost": entry["carry"],
                "outcome": outcome,
                "ambiguous_path": bool(ambiguous),
            }
        )
        quantity, entry = 0.0, None

    for i in range(begin, end):
        signal = plan["direction"][i]
        exited = False
        if quantity:
            elapsed = times[i] - times[i - 1]
            financing = abs(quantity) * cl[i - 1] * annual_carry * elapsed / (365.25 * 86400)
            cash -= financing
            entry["carry"] += financing
            quote_open = op[i] + (spread[i] if direction == -1 else 0)
            if elapsed != 60 or times[i] >= expiry:
                close(i, quote_open, "DATA_GAP" if elapsed != 60 else "SESSION_END")
                exited = True
            elif noise and np.isfinite(signal) and signal != direction:
                close(i, quote_open, "GRID_EXIT")
                exited = not bool(signal)
            elif (
                not orb
                and not noise
                and np.isfinite(plan["exit_direction"][i])
                and plan["exit_direction"][i] != direction
            ):
                close(i, quote_open, "EMA_CLOSE_EXIT")
                exited = True
            elif not noise:
                high = hi[i] + (spread[i] if direction == -1 else 0)
                low = lo[i] + (spread[i] if direction == -1 else 0)
                stopped = low <= stop if direction == 1 else high >= stop
                profit = bool(target) and (high >= target if direction == 1 else low <= target)
                if stopped:
                    close(
                        i,
                        min(quote_open, stop) if direction == 1 else max(quote_open, stop),
                        "SL",
                        profit,
                    )
                    exited = True
                elif profit:
                    close(i, target, "TP")
                    exited = True
        if not quantity and not exited and np.isfinite(signal) and signal and data["in_session"][i]:
            day = data["day"][i]
            if orb and day in used:
                curve[i - begin] = cash
                continue
            direction = int(signal)
            reference = op[i]
            if orb:
                trigger = plan["trigger"][i]
                if not (hi[i] >= trigger if direction == 1 else lo[i] <= trigger):
                    curve[i - begin] = cash
                    continue
                reference = max(op[i], trigger) if direction == 1 else min(op[i], trigger)
                bid_stop = reference - direction * plan["stop"][i]
            else:
                bid_stop = plan["stop"][i]
            fill = reference + (spread[i] if direction == 1 else 0) + direction * 0.002
            stop = bid_stop + (spread[i] if direction == -1 else 0)
            distance = direction * (fill - (stop - direction * 0.002)) + fee_price
            if not np.isfinite(distance) or distance <= 0 or stop <= 0 or fill <= 0:
                curve[i - begin] = cash
                continue
            capital = cash
            amount = min(capital * 0.005 / distance, 2 * capital / fill)
            quantity = direction * amount
            commission = amount * fee_price / 2
            cash -= quantity * fill + commission
            entry = {
                "i": i,
                "price": fill,
                "capital": capital,
                "risk": amount * distance,
                "commission": commission,
                "carry": 0.0,
            }
            used.add(day)
            expiry = plan["expiry"][i]
            target = (
                reference
                + direction * 3 * abs(reference - bid_stop)
                + (spread[i] if direction == -1 else 0)
                if not orb and not noise
                else 0.0
            )
            if orb and (lo[i] <= stop if direction == 1 else hi[i] + spread[i] >= stop):
                close(i, stop, "AMBIGUOUS_ENTRY_STOP", True)
            elif not orb and not noise:
                high = hi[i] + (spread[i] if direction == -1 else 0)
                low = lo[i] + (spread[i] if direction == -1 else 0)
                stopped = low <= stop if direction == 1 else high >= stop
                profit = high >= target if direction == 1 else low <= target
                if stopped:
                    close(
                        i,
                        min(reference, stop)
                        if direction == 1
                        else max(reference + spread[i], stop),
                        "SL",
                        profit,
                    )
                elif profit:
                    close(i, target, "TP")
        marked = cash + quantity * (cl[i] + (spread[i] if quantity < 0 else 0))
        curve[i - begin] = marked
        if marked <= 0:
            if quantity:
                close(i, cl[i] + (spread[i] if direction == -1 else 0), "EQUITY_EXHAUSTED")
            curve[i - begin :] = cash
            break
    if quantity:
        close(end - 1, cl[end - 1] + (spread[end - 1] if direction == -1 else 0), "SEGMENT_END")
        curve[-1] = cash
    pnl = np.array([t["net_pnl"] for t in trades])
    values = np.r_[10000.0, curve]
    losses = -float(pnl[pnl < 0].sum())
    stats = {
        "trades": len(trades),
        "win_rate": float(np.mean(pnl > 0)) if len(pnl) else None,
        "profit_factor": float(pnl[pnl > 0].sum()) / losses if losses else None,
        "total_r": float(sum(t["net_r"] for t in trades)),
        "ending_equity": float(curve[-1]),
        "return_percent": float((curve[-1] / 10000 - 1) * 100),
        "drawdown_m1_close_percent": float(
            np.max(1 - values / np.maximum.accumulate(values)) * 100
        ),
        "ambiguous_trades": sum(t["ambiguous_path"] for t in trades),
        "gap_exits": sum(t["outcome"] == "DATA_GAP" for t in trades),
        "commission_cost": float(sum(t["commission"] for t in trades)),
        "carry_cost": float(sum(t["carry_cost"] for t in trades)),
    }
    return stats, trades, curve
