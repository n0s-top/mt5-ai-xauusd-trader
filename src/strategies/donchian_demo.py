"""Manual, demo-only D1 Donchian 55/20 plans. Never submits or modifies orders."""

import math
from datetime import timedelta

import pandas as pd

from src.research.published_strategies import validate_daily, wilder_atr
from src.strategies.account_risk import assess_exposure
from src.strategies.kelly_sizing import size_with_broker


class Donchian5520:
    strategy_id = "donchian_55_20_d1_demo_v1"
    experimental = True


def closed_daily(rates, now):
    frame = pd.DataFrame(rates).copy()
    if "time" not in frame:
        raise ValueError("Missing D1 timestamps")
    frame["time"] = pd.to_datetime(frame["time"], unit="s", utc=True)
    frame = validate_daily(frame.set_index("time"))
    frame = frame.loc[frame.index + pd.Timedelta(days=1) <= pd.Timestamp(now)].copy()
    # Match the research feed: Sunday stub belongs to the following Monday.
    frame.index = frame.index + pd.to_timedelta(
        (frame.index.day_of_week == 6).astype(int), unit="D"
    )
    frame = frame.groupby(level=0, sort=True).agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    )
    frame = frame.loc[frame.index + pd.Timedelta(days=1) <= pd.Timestamp(now)]
    if len(frame) < 55:
        raise ValueError("Need at least 55 fully closed D1 sessions")
    if pd.Timestamp(now) - frame.index[-1] > pd.Timedelta(days=4):
        raise ValueError("Closed D1 history is stale")
    if frame.index[-55:].to_series().diff().dropna().max() > pd.Timedelta(days=5):
        raise ValueError("Unexplained gap in the 55-session window")
    return frame


def channel_levels(frame):
    return {
        "entry_high_55": float(frame.high.iloc[-55:].max()),
        "entry_low_55": float(frame.low.iloc[-55:].min()),
        "exit_high_20": float(frame.high.iloc[-20:].max()),
        "exit_low_20": float(frame.low.iloc[-20:].min()),
        "atr20": float(wilder_atr(frame).iloc[-1]),
    }


def snapshot_donchian(
    api,
    symbol,
    risk_percent,
    *,
    now,
    sizing="fixed",
    cost_per_lot=0.0,
    slippage_ticks=2,
    max_total_risk=2.0,
    position_ticket=None,
):
    plan = {
        "symbol": symbol,
        "strategy_id": Donchian5520.strategy_id,
        "experimental": True,
        "timeframe": "D1",
        "status": "BLOCKED",
        "setup_type": "DONCHIAN_55_20",
        "generated_at_utc": now.isoformat(),
        "sizing_mode": "fixed",
        "risk_percent": risk_percent,
        "entry_scenarios": [],
        "take_profit": None,
        "volume": None,
        "exit_rule": "Khong co TP co dinh: BUY thoat khi pha day 20 phien D1, SELL khi pha dinh 20 phien. SL ban dau = 2 ATR20. Khong them vi the.",
        "demo_note": "Chi demo thu cong. Chon toi da MOT kich ban; huy lenh cho sau khi khop hoac truoc khi kenh D1 thay doi. Lam moi quote truoc khi thao tac.",
        "cost_note": "Rui ro SL gom phi/truot gia da khai bao; swap va lo do gap la chi phi bo sung, co the vuot ngan sach SL.",
    }
    terminal = api.terminal_info()
    if terminal is None or not terminal.connected or not api.symbol_select(symbol, True):
        raise ValueError("MT5 disconnected or symbol unavailable")
    account = api.account_info()
    if account is None or getattr(account, "trade_mode", None) != api.ACCOUNT_TRADE_MODE_DEMO:
        plan["reason"] = "Donchian demo requires an MT5 DEMO account; no live-account plan"
        return plan
    plan.update(equity=account.equity, currency=account.currency)
    if not math.isfinite(risk_percent) or not 0 < risk_percent <= 0.5:
        raise ValueError("Donchian demo risk must be in (0, 0.5]%")
    if (
        not math.isfinite(cost_per_lot)
        or cost_per_lot < 0
        or not math.isfinite(slippage_ticks)
        or slippage_ticks < 0
    ):
        raise ValueError("Invalid costs/slippage")
    broker, tick = api.symbol_info(symbol), api.symbol_info_tick(symbol)
    if broker is None or tick is None:
        raise ValueError("Missing broker specifications or quote")
    step = broker.trade_tick_size
    if (
        not all(math.isfinite(v) and v > 0 for v in (step, tick.bid, tick.ask))
        or tick.ask < tick.bid
    ):
        raise ValueError("Invalid quote or tick size")
    rates = api.copy_rates_from_pos(symbol, api.TIMEFRAME_D1, 0, 1000)
    frame = closed_daily(rates, now)
    levels = channel_levels(frame)
    if not math.isfinite(levels["atr20"]) or levels["atr20"] <= 0:
        raise ValueError("ATR20 unavailable")
    plan.update(
        levels=levels,
        candle_time_utc=frame.index[-1].isoformat(),
        bid=tick.bid,
        ask=tick.ask,
    )
    age = now.timestamp() - tick.time
    if not -2 <= age <= 15:
        plan["reason"] = "Quote stale/market closed: D1 levels only; refresh during trading hours"
        return plan
    plan["expires_at_utc"] = min(
        now + timedelta(seconds=15),
        pd.Timestamp(tick.time + 15, unit="s", tz="UTC").to_pydatetime(),
        now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1),
    ).isoformat()
    positions, orders = api.positions_get(), api.orders_get()
    exposure = assess_exposure(
        positions,
        orders,
        equity=account.equity,
        cap_percent=max_total_risk,
        symbol=symbol,
        calc_profit=api.order_calc_profit,
        cost_per_lot=cost_per_lot,
    )
    plan["account_risk"] = exposure
    if positions is None or orders is None:
        plan["reason"] = "Cannot read all positions/pending orders"
        return plan
    selected = [p for p in positions if p.symbol == symbol]
    spread = tick.ask - tick.bid

    def floor(price):
        return math.floor(price / step + 1e-9) * step

    def ceil(price):
        return math.ceil(price / step - 1e-9) * step

    if position_ticket is not None:
        matches = [p for p in selected if p.ticket == position_ticket]
        if len(matches) != 1:
            plan["reason"] = "Selected demo position ticket not found for this symbol"
            return plan
        pos = matches[0]
        if (
            pos.type not in (api.ORDER_TYPE_BUY, api.ORDER_TYPE_SELL)
            or not math.isfinite(pos.sl)
            or pos.sl <= 0
        ):
            plan["reason"] = (
                "Selected position requires an existing valid protective SL; entry-time ATR is unknown"
            )
            return plan
        buy = pos.type == api.ORDER_TYPE_BUY
        channel = floor(levels["exit_low_20"]) if buy else ceil(levels["exit_high_20"] + spread)
        proposed = max(pos.sl, channel) if buy else min(pos.sl, channel)
        crossed = tick.bid <= proposed if buy else tick.ask >= proposed
        minimum = getattr(broker, "trade_stops_level", 0) * getattr(broker, "point", 0)
        modifiable = (tick.bid - proposed if buy else proposed - tick.ask) >= minimum
        plan.update(
            status="REVIEW",
            reason="Manage only the explicitly selected demo position",
            management={
                "side": "BUY" if buy else "SELL",
                "action": "EXIT_MANUAL_NOW" if crossed else "REVIEW_PROTECTIVE_STOP",
                "existing_sl": pos.sl,
                "suggested_sl": proposed,
                "channel_exit": channel,
                "broker_distance_allows_modify": bool(modifiable),
            },
        )
        return plan
    if selected or any(o.symbol == symbol for o in orders):
        plan["reason"] = (
            "Symbol already has a position/pending order; no second unit. Use --position-ticket to review a known Donchian position"
        )
        return plan
    deals = api.history_deals_get(now.replace(hour=0, minute=0, second=0, microsecond=0), now)
    if deals is None:
        plan["reason"] = "Cannot read today's deals; no re-entry eligibility can be established"
        return plan
    if any(d.symbol == symbol for d in deals):
        plan["reason"] = "Symbol traded today; no same-day re-entry in this demo adaptation"
        return plan
    if sizing != "fixed":
        plan["reason"] = "Donchian demo uses fixed risk only; use --sizing fixed"
        return plan
    if exposure["status"] != "READY":
        plan["reason"] = "Account risk: " + exposure.get("reason", exposure["status"])
        return plan
    raw = pd.DataFrame(rates)
    times = pd.to_datetime(raw["time"], unit="s", utc=True)
    current = raw.loc[times == pd.Timestamp(now).floor("D")]
    if current.empty:
        plan["reason"] = (
            "No current D1 candle; cannot verify whether today's breakout was already missed"
        )
        return plan
    today = current.iloc[-1]
    bid_buy = ceil(levels["entry_high_55"] + step)
    bid_sell = floor(levels["entry_low_55"] - step)
    missed = (
        today.high >= bid_buy
        or today.low <= bid_sell
        or tick.bid >= bid_buy
        or tick.bid <= bid_sell
    )
    minimum = getattr(broker, "trade_stops_level", 0) * getattr(broker, "point", 0)
    for buy in (True, False):
        direction = 1 if buy else -1
        action = api.ORDER_TYPE_BUY if buy else api.ORDER_TYPE_SELL
        bid_trigger = bid_buy if buy else bid_sell
        entry = ceil(bid_trigger + spread) if buy else bid_trigger
        stop = (
            floor(bid_trigger - 2 * levels["atr20"])
            if buy
            else ceil(bid_trigger + 2 * levels["atr20"] + spread)
        )
        candidate = {
            "side": "BUY" if buy else "SELL",
            "status": "BLOCKED",
            "entry": entry,
            "trigger_bid": bid_trigger,
            "stop_loss": stop,
            "take_profit": None,
            "volume": None,
            "entry_type": "BUY_STOP" if buy else "SELL_STOP",
        }
        plan["entry_scenarios"].append(candidate)
        if missed:
            candidate["reason"] = "Breakout already touched today; do not chase or re-enter"
            continue
        if (
            stop <= 0
            or min(direction * (entry - (tick.ask if buy else tick.bid)), abs(entry - stop)) + 1e-9
            < minimum
        ):
            candidate["reason"] = "Fixed channel trigger/SL violates broker stop distance"
            continue
        slip = slippage_ticks * step
        try:

            def loss(volume, action=action, entry=entry, direction=direction, slip=slip, stop=stop):
                value = api.order_calc_profit(
                    action, symbol, volume, entry + direction * slip, stop - direction * slip
                )
                return -value if value is not None else None

            probe = api.order_calc_profit(action, symbol, 1.0, entry, entry + 1.0)
            if probe is None or not math.isfinite(probe) or probe == 0:
                raise ValueError("Cannot calculate account-currency notional cap")
            volume_cap = min(broker.volume_max, 2 * account.equity / (abs(probe) * entry))
            if getattr(broker, "volume_limit", 0) > 0:
                volume_cap = min(volume_cap, broker.volume_limit)
            result = size_with_broker(
                equity=account.equity,
                risk_percent=min(risk_percent, exposure["available_percent"]),
                free_margin=account.margin_free,
                volume_min=broker.volume_min,
                volume_max=volume_cap,
                volume_step=broker.volume_step,
                loss_for_volume=loss,
                margin_for_volume=lambda volume, action=action, entry=entry: api.order_calc_margin(
                    action, symbol, volume, entry
                ),
                cost_per_lot=cost_per_lot,
            )
            candidate.update(
                result, status="REVIEW", reason="Conditional D1 channel entry; choose only one side"
            )
        except (ValueError, TypeError, OverflowError) as exc:
            candidate["reason"] = "Lot blocked: " + str(exc)
    plan["status"] = (
        "REVIEW" if any(p["status"] == "REVIEW" for p in plan["entry_scenarios"]) else "WAIT"
    )
    plan["reason"] = "Two alternative channel scenarios, not simultaneous orders"
    return plan
