"""Causal single-gold adaptations of published trend rules, not paper replication.

Spot/CFD data lack futures roll/excess returns and a multi-asset portfolio. All
deviations, especially single-market risk, are explicit in the research runner.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

METHODS = (
    "buy_hold_1x",
    "tsmom12_vol40_cap2",
    "trend_1_3_12_weekly_vol40_cap2",
    "donchian20_10",
    "donchian55_20",
    "turtle_s1_single",
    "turtle_s1_pyramid4",
    "turtle_s2_pyramid4",
)


def validate_daily(data):
    frame = data.copy()
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
        raise ValueError("Timezone-aware daily index required")
    if frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
        raise ValueError("Daily candles must be unique and ordered")
    prices = frame[["open", "high", "low", "close"]]
    if frame.index.hasnans or not np.isfinite(prices.to_numpy()).all() or (prices <= 0).any().any():
        raise ValueError("Invalid daily prices or timestamps")
    if (frame.high < prices.max(axis=1)).any() or (frame.low > prices.min(axis=1)).any():
        raise ValueError("Invalid daily geometry")
    return frame


def wilder_atr(frame, period=20):
    previous = frame.close.shift()
    tr = pd.concat(
        [frame.high - frame.low, (frame.high - previous).abs(), (frame.low - previous).abs()],
        axis=1,
    ).max(axis=1)
    result = np.full(len(frame), np.nan)
    if len(frame) >= period:
        result[period - 1] = tr.iloc[:period].mean()
        for i in range(period, len(frame)):
            result[i] = ((period - 1) * result[i - 1] + tr.iloc[i]) / period
    return pd.Series(result, index=frame.index)


def trend_targets(frame, method):
    """Decision at close t; target applies at next available open, never at t."""
    if method not in METHODS[:3]:
        raise ValueError("Unknown trend method")
    target = pd.Series(np.nan, index=frame.index)
    returns = frame.close.pct_change()
    vol = returns.ewm(alpha=0.02, adjust=False, min_periods=60).std(bias=True) * np.sqrt(261)
    closes = frame.close.to_numpy()
    months = (
        frame.index.to_period("M")
        if frame.index.tz is None
        else frame.index.tz_localize(None).to_period("M")
    )
    # Rebalance on first observed session after a calendar boundary, using the
    # preceding close. Missing days never become filled/artificial price bars.
    held = 0.0
    for i in range(len(frame)):
        if method == "buy_hold_1x":
            target.iloc[i] = 1.0
            continue
        if i < 1:
            continue
        monthly = months[i] != months[i - 1]
        weekly = frame.index[i].isocalendar()[:2] != frame.index[i - 1].isocalendar()[:2]
        rebalance = monthly if method == "tsmom12_vol40_cap2" else weekly
        history_end = i - 1
        if not rebalance:
            target.iloc[i] = held
            continue
        horizons = (12,) if method == "tsmom12_vol40_cap2" else (1, 3, 12)
        signs = []
        for horizon in horizons:
            anchor = frame.index[history_end] - pd.DateOffset(months=horizon)
            j = frame.index.searchsorted(anchor, side="right") - 1
            if j < 0:
                break
            signs.append(float(np.sign(closes[history_end] / closes[j] - 1)))
        if (
            len(signs) == len(horizons)
            and np.isfinite(vol.iloc[history_end])
            and vol.iloc[history_end] > 0
        ):
            held = float(np.mean(signs)) * min(2.0, 0.40 / float(vol.iloc[history_end]))
        target.iloc[i] = held
    return target.fillna(0.0)


@dataclass
class Book:
    cash: float = 10000.0
    quantity: float = 0.0
    spread: float = 0.24
    slippage: float = 0.002
    fee: float = 0.10
    carry: float = 0.0
    orders: list = field(default_factory=list)
    total_cost: float = 0.0
    total_carry: float = 0.0

    def equity(self, price):
        return self.cash + self.quantity * price

    def trade(self, delta, reference, when, reason):
        if abs(delta) < 1e-10:
            return
        cost = abs(delta) * (self.spread / 2 + self.slippage + self.fee / 2)
        self.cash -= delta * reference + cost
        self.quantity += delta
        self.total_cost += cost
        self.orders.append(
            {
                "time": when.isoformat(),
                "delta_oz": delta,
                "reference_price": reference,
                "cost_usd": cost,
                "reason": reason,
            }
        )

    def finance(self, price, days):
        charge = abs(self.quantity) * price * self.carry * days / 365.25
        self.cash -= charge
        self.total_carry += charge


def metrics(equity, *, initial=10000.0):
    if equity.empty:
        raise ValueError("No evaluation observations")
    values = np.r_[initial, equity.to_numpy(dtype=float)]
    returns = values[1:] / values[:-1] - 1
    peaks = np.maximum.accumulate(values)
    days = max(1, (equity.index[-1] - equity.index[0]).days + 1)
    years = days / 365.25
    cagr = (values[-1] / initial) ** (1 / years) - 1 if values[-1] > 0 else -1.0
    deviation = float(np.std(returns, ddof=1)) if len(returns) > 1 else 0.0
    return {
        "start": equity.index[0].isoformat(),
        "end": equity.index[-1].isoformat(),
        "observations": len(equity),
        "ending_equity": float(values[-1]),
        "return_percent": float((values[-1] / initial - 1) * 100),
        "cagr_percent": float(cagr * 100),
        "daily_close_drawdown_percent": float(np.max(1 - values / peaks) * 100),
        "sharpe_zero_cash_rate": float(np.mean(returns) / deviation * np.sqrt(252))
        if deviation
        else None,
    }


def run_trend(frame, method, *, start, spread=0.24, fee=0.10, carry=0.0):
    frame = validate_daily(frame)
    targets = trend_targets(frame, method)
    book = Book(spread=spread, fee=fee, carry=carry)
    equity, active = {}, 0
    last_weight = None
    for i, (when, row) in enumerate(frame.iterrows()):
        if when < start:
            continue
        if i:
            book.finance(float(frame.close.iloc[i - 1]), (when - frame.index[i - 1]).days)
        available = book.equity(float(row.open))
        weight = float(targets.iloc[i])
        # Hold quantities between scheduled rebalances, rather than covert daily
        # volatility rebalancing. A calendar rebalance can keep the same weight.
        scheduled = i == 0 or (
            frame.index[i].month != frame.index[i - 1].month
            if method == "tsmom12_vol40_cap2"
            else frame.index[i].isocalendar()[:2] != frame.index[i - 1].isocalendar()[:2]
        )
        if method == "buy_hold_1x":
            scheduled = last_weight is None
        if last_weight is None or scheduled:
            desired = max(0, available) * weight / float(row.open)
            book.trade(desired - book.quantity, float(row.open), when, "rebalance")
            last_weight = weight
        active += bool(book.quantity)
        equity[when] = book.equity(float(row.close))
        if equity[when] <= 0:
            book.trade(-book.quantity, float(row.close), when, "insolvent")
            raise ValueError("Strategy equity exhausted")
    last = next(reversed(equity))
    book.trade(-book.quantity, float(frame.loc[last, "close"]), last, "end_of_sample")
    equity[last] = book.cash
    curve = pd.Series(equity, name="equity")
    return curve, book, {"active_days": active, "ambiguous_days": 0}


def run_turtle(frame, method, *, start, spread=0.24, fee=0.10, carry=0.0):
    """Daily conservative execution; risk 0.5%/unit, capped 2x at each add.

    S1 uses last completed *virtual* 20/10 trade, including skipped signals.
    No re-entry on the same day after an exit. Day-range ambiguity is adverse.
    This is a disclosed adaptation, not the original portfolio risk system.
    """
    frame = validate_daily(frame)
    if method not in METHODS[3:]:
        raise ValueError("Unknown turtle method")
    atr = wilder_atr(frame).shift()
    high20, low20 = frame.high.rolling(20).max().shift(), frame.low.rolling(20).min().shift()
    high55, low55 = frame.high.rolling(55).max().shift(), frame.low.rolling(55).min().shift()
    high10, low10 = frame.high.rolling(10).max().shift(), frame.low.rolling(10).min().shift()
    s1 = method.startswith("turtle_s1")
    short_system = s1 or method == "donchian20_10"
    pyramid = 4 if "pyramid4" in method else 1
    book = Book(spread=spread, fee=fee, carry=carry)
    equity = {}
    units = 0
    stop = last_add = unit_n = 0.0
    virtual = None
    last_winner = False
    ambiguous = active = 0
    for i, (when, row) in enumerate(frame.iterrows()):
        if i < 55:
            continue
        n = float(atr.iloc[i])
        if not np.isfinite(n) or n <= 0:
            continue
        opened, high, low = float(row.open), float(row.high), float(row.low)
        # Capture previous completed virtual outcome for this day's real entries.
        skip20 = last_winner
        if virtual is not None:
            direction, entry, virtual_stop = virtual
            barrier = (
                max(virtual_stop, low10.iloc[i])
                if direction == 1
                else min(virtual_stop, high10.iloc[i])
            )
            if low <= barrier if direction == 1 else high >= barrier:
                fill = min(opened, barrier) if direction == 1 else max(opened, barrier)
                last_winner = direction * (fill - entry) > 0
                virtual = None
        else:
            up, down = high > high20.iloc[i], low < low20.iloc[i]
            if up or down:
                direction = 1 if up else -1
                entry = (
                    max(opened, high20.iloc[i] + 0.001)
                    if up
                    else min(opened, low20.iloc[i] - 0.001)
                )
                virtual_stop = entry - direction * 2 * n
                if (up and down) or (
                    low <= virtual_stop if direction == 1 else high >= virtual_stop
                ):
                    last_winner = False
                else:
                    virtual = (direction, entry, virtual_stop)
        if when < start:
            continue
        book.finance(float(frame.close.iloc[i - 1]), (when - frame.index[i - 1]).days)
        was_held = bool(book.quantity)
        exited = False
        if was_held:
            direction = 1 if book.quantity > 0 else -1
            exit_channel = (
                (low10 if short_system else low20).iloc[i]
                if direction == 1
                else (high10 if short_system else high20).iloc[i]
            )
            barrier = max(stop, exit_channel) if direction == 1 else min(stop, exit_channel)
            if low <= barrier if direction == 1 else high >= barrier:
                price = min(opened, barrier) if direction == 1 else max(opened, barrier)
                book.trade(-book.quantity, price, when, "stop_or_channel")
                units = 0
                exited = True
        if not book.quantity and not exited:
            use55 = not short_system or (s1 and skip20)
            upper = (high55 if use55 else high20).iloc[i] + 0.001
            lower = (low55 if use55 else low20).iloc[i] - 0.001
            up, down = high >= upper, low <= lower
            if up or down:
                direction = 1 if up else -1
                price = max(opened, upper) if up else min(opened, lower)
                capital = max(0, book.equity(price))
                amount = min(capital * 0.005 / (2 * n), 2 * capital / price)
                book.trade(direction * amount, price, when, "entry55" if use55 else "entry20")
                units, unit_n, last_add = 1, n, price
                stop = price - direction * 2 * n
                # An unknown entry/stop ordering is resolved adversely, not ignored.
                if (up and down) or (low <= stop if direction == 1 else high >= stop):
                    book.trade(-book.quantity, stop, when, "ambiguous_entry_stop")
                    ambiguous += 1
                    exited = True
                    units = 0
        while book.quantity and not exited and units < pyramid:
            direction = 1 if book.quantity > 0 else -1
            trigger = last_add + direction * 0.5 * unit_n
            if not (high >= trigger if direction == 1 else low <= trigger):
                break
            price = max(opened, trigger) if direction == 1 else min(opened, trigger)
            capital = max(0, book.equity(price))
            headroom = max(0, 2 * capital / price - abs(book.quantity))
            amount = min(capital * 0.005 / (2 * unit_n), headroom)
            if amount <= 0:
                break
            book.trade(direction * amount, price, when, "add_unit")
            units += 1
            last_add = price
            stop = (
                max(stop, price - 2 * unit_n) if direction == 1 else min(stop, price + 2 * unit_n)
            )
            if low <= stop if direction == 1 else high >= stop:
                book.trade(-book.quantity, stop, when, "ambiguous_add_stop")
                ambiguous += 1
                exited = True
                units = 0
        active += was_held or bool(book.quantity)
        equity[when] = book.equity(float(row.close))
        if equity[when] <= 0:
            raise ValueError("Strategy equity exhausted")
    last = next(reversed(equity))
    book.trade(-book.quantity, float(frame.loc[last, "close"]), last, "end_of_sample")
    equity[last] = book.cash
    return (
        pd.Series(equity, name="equity"),
        book,
        {"active_days": int(active), "ambiguous_days": ambiguous},
    )


def evaluate(frame, method, *, start, spread=0.24, fee=0.10, carry=0.0):
    if method not in METHODS:
        raise ValueError("Unknown strategy")
    settings = (spread, fee, carry)
    if not all(np.isfinite(x) and x >= 0 for x in settings):
        raise ValueError("Costs must be finite and nonnegative")
    start = pd.Timestamp(start)
    if start.tzinfo is None or not (frame.index >= start).any():
        raise ValueError("Evaluation start must be aware and within data")
    run = run_trend if method in METHODS[:3] else run_turtle
    curve, book, diagnostics = run(
        frame, method, start=start, **{"spread": spread, "fee": fee, "carry": carry}
    )
    summary = dict(
        metrics(curve),
        **diagnostics,
        orders=len(book.orders),
        execution_cost_usd=book.total_cost,
        carry_cost_usd=book.total_carry,
    )
    yearly = []
    previous = 10000.0
    for year, values in curve.groupby(curve.index.year):
        yearly.append(dict(year=int(year), **metrics(values, initial=previous)))
        previous = float(values.iloc[-1])
    return {"summary": summary, "yearly": yearly}, curve, pd.DataFrame(book.orders)
