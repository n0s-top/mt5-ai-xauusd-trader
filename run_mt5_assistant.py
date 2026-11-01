"""Read live MT5 data and publish manual entry plans. Never submit orders."""

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

import MetaTrader5 as mt5
import pandas as pd
from rich.console import Console
from rich.text import Text

from src.strategies.account_risk import assess_exposure
from src.strategies.adaptive_scalper import AdaptiveScalper
from src.strategies.assistant_log import record_analysis, summarize_log
from src.strategies.donchian_demo import Donchian5520, snapshot_donchian
from src.strategies.entry_support import future_entry
from src.strategies.higher_timeframes import analyze_context
from src.strategies.kelly_sizing import STRATEGY_ID, estimate_kelly, load_results, size_with_broker
from src.strategies.m5_m1_pullback import M5M1Pullback, M5M1QualityPullback, M5M1RegimePullback
from src.strategies.orb_mtf import ORB5MTF, RollingM1M5, ConfirmedM1M5
from src.research.m1_forecast import forecast_snapshot
from src.strategies.scalping_data import prepare_scalping_data
from src.strategies.setup_checklist import setup_checklist
from src.strategies.terminal_view import render_plan
from src.strategies.xauusd_m1_scalper import ScalperSignal, XAUUSDM1Scalper


def apply_sizing(
    plan,
    symbol,
    broker,
    account,
    *,
    sizing,
    risk_percent,
    kelly_history,
    kelly_fraction,
    min_trades,
    cost_per_lot,
    slippage_ticks,
    exposure=None,
    strategy_id=STRATEGY_ID,
):
    plan["sizing_mode"] = sizing
    selected_risk = risk_percent
    if sizing == "kelly":
        try:
            results = (
                load_results(kelly_history, symbol, strategy_id=strategy_id)
                if kelly_history
                else []
            )
            report = estimate_kelly(
                results,
                fraction=kelly_fraction,
                risk_cap_percent=risk_percent,
                min_trades=min_trades,
                payoff_ceiling=plan.get("reward_risk"),
            )
        except FileNotFoundError:
            report = {
                "status": "INSUFFICIENT_DATA",
                "trades": 0,
                "min_trades": min_trades,
                "risk_percent": 0.0,
                "reason": "Create Kelly history from docs/examples/kelly_history_template.csv",
            }
        except (OSError, ValueError, OverflowError) as exc:
            report = {
                "status": "INVALID_HISTORY",
                "trades": 0,
                "risk_percent": 0.0,
                "reason": str(exc),
            }
        plan["kelly"] = report
        selected_risk = report["risk_percent"]
    # Never keep a fixed-risk lot when Kelly is unavailable or negative.
    plan.update(volume=None, estimated_risk=None)
    if plan["status"] != "REVIEW":
        return
    if not math.isfinite(account.equity) or account.equity <= 0:
        plan["sizing_note"] = "Equity is zero; analysis only, no lot recommendation"
        return
    if selected_risk <= 0:
        plan["sizing_note"] = "Kelly unavailable or no positive edge; no lot recommendation"
        return
    if exposure is not None:
        if exposure["status"] != "READY":
            plan["sizing_note"] = "Account risk: " + exposure.get("reason", exposure["status"])
            return
        selected_risk = min(selected_risk, exposure["available_percent"])
    try:
        buy = plan["side"] == "BUY"
        direction = 1 if buy else -1
        action = mt5.ORDER_TYPE_BUY if buy else mt5.ORDER_TYPE_SELL
        distance = getattr(broker, "trade_stops_level", 0) * getattr(broker, "point", 0)
        current = plan["ask"] if buy else plan["bid"]
        if (
            min(
                direction * (plan["entry"] - current),
                abs(plan["entry"] - plan["stop_loss"]),
                abs(plan["take_profit"] - plan["entry"]),
            )
            + 1e-9
            < distance
        ):
            raise ValueError("Conditional entry violates broker minimum stop distance")
        slip = slippage_ticks * broker.trade_tick_size
        adverse_entry = plan["entry"] + direction * slip
        adverse_stop = plan["stop_loss"] - direction * slip

        def loss(volume):
            profit = mt5.order_calc_profit(action, symbol, volume, adverse_entry, adverse_stop)
            return -profit if profit is not None else None

        def net_reward(volume):
            profit = mt5.order_calc_profit(
                action, symbol, volume, adverse_entry, plan["take_profit"] - direction * slip
            )
            return profit - cost_per_lot * volume if profit is not None else None

        probe_loss = loss(broker.volume_min)
        probe_reward = net_reward(broker.volume_min)
        if (
            probe_loss is None
            or probe_reward is None
            or not all(math.isfinite(value) for value in (probe_loss, probe_reward))
        ):
            raise ValueError("Cannot calculate net reward/risk")
        probe_risk = probe_loss + cost_per_lot * broker.volume_min
        if probe_risk <= 0 or probe_reward / probe_risk < 1.5:
            raise ValueError("Net reward/risk after costs and slippage is below 1.5")
        max_volume = broker.volume_max
        volume_limit = getattr(broker, "volume_limit", 0)
        if exposure is not None and volume_limit > 0:
            max_volume = min(
                max_volume, volume_limit - exposure["buy_volume" if buy else "sell_volume"]
            )
        sizing_result = size_with_broker(
            equity=account.equity,
            risk_percent=selected_risk,
            free_margin=account.margin_free,
            volume_min=broker.volume_min,
            volume_max=max_volume,
            volume_step=broker.volume_step,
            loss_for_volume=loss,
            margin_for_volume=lambda volume: mt5.order_calc_margin(
                action, symbol, volume, adverse_entry
            ),
            cost_per_lot=cost_per_lot,
        )
        reward = net_reward(sizing_result["volume"])
        if (
            reward is None
            or not math.isfinite(reward)
            or reward / sizing_result["estimated_risk"] < 1.5
        ):
            raise ValueError("Final net reward/risk is below 1.5")
        plan.update(
            sizing_result,
            selected_risk_percent=selected_risk,
            cost_per_lot=cost_per_lot,
            slippage_ticks=slippage_ticks,
            estimated_net_profit=reward,
            net_reward_risk=reward / sizing_result["estimated_risk"],
        )
        plan.pop("sizing_note", None)
    except (ValueError, TypeError, AttributeError, OverflowError) as exc:
        plan["sizing_note"] = f"Lot blocked: {exc}"


def preferred_direction(frames, require_m15=True):
    """Use agreeing M15 trend and M5 momentum; never break a tie arbitrarily."""
    if len(frames["M5"]) < 220 or (require_m15 and len(frames["M15"]) < 220):
        return 0
    momentum = XAUUSDM1Scalper.indicators(frames["M5"]).iloc[-1]
    if not require_m15:
        values = [momentum["ema9"], momentum["ema21"]]
        if not all(math.isfinite(value) for value in values):
            return 0
        return 1 if values[0] > values[1] else -1 if values[0] < values[1] else 0
    trend = XAUUSDM1Scalper.indicators(frames["M15"]).iloc[-1]
    values = [trend["close"], trend["ema200"], momentum["ema9"], momentum["ema21"]]
    if not all(math.isfinite(value) for value in values):
        return 0
    if trend["close"] > trend["ema200"] and momentum["ema9"] > momentum["ema21"]:
        return 1
    if trend["close"] < trend["ema200"] and momentum["ema9"] < momentum["ema21"]:
        return -1
    return 0


def indicator_summary(frames):
    rows = []
    for timeframe in ("M15", "M5", "M1"):
        if frames[timeframe].empty:
            continue
        last = XAUUSDM1Scalper.indicators(frames[timeframe]).iloc[-1]
        if timeframe == "M15":
            keys = ("close", "ema200")
        elif timeframe == "M5":
            keys = ("ema9", "ema21")
        else:
            keys = ("rsi", "adx", "atr")
        if any(key not in last or not math.isfinite(last[key]) for key in keys):
            continue
        state = "CONTEXT"
        if timeframe != "M1":
            first, second = (float(last[key]) for key in keys)
            state = "BUY" if first > second else "SELL" if first < second else "WAIT"
        rows.append(
            {
                "timeframe": timeframe,
                "values": " | ".join(f"{key.upper()} {last[key]:.2f}" for key in keys),
                "state": state,
            }
        )
    return rows


def snapshot(
    symbol,
    risk_percent,
    strategy,
    *,
    sizing="kelly",
    kelly_history=None,
    kelly_fraction=0.25,
    min_trades=50,
    cost_per_lot=0.0,
    slippage_ticks=2,
    max_total_risk=2.0,
    include_higher_timeframes=False,
    position_ticket=None,
    forecast_model=None,
):
    if isinstance(strategy, Donchian5520):
        plan = snapshot_donchian(
            mt5,
            symbol,
            risk_percent,
            now=datetime.now(timezone.utc),
            sizing=sizing,
            cost_per_lot=cost_per_lot,
            slippage_ticks=slippage_ticks,
            max_total_risk=max_total_risk,
            position_ticket=position_ticket,
        )
        if plan.get("expires_at_utc") and datetime.now(timezone.utc) >= datetime.fromisoformat(
            plan["expires_at_utc"]
        ):
            plan.update(
                status="BLOCKED",
                reason="Snapshot expired; refresh before acting",
                entry_scenarios=[],
                management=None,
            )
        return plan
    info = mt5.terminal_info()
    if info is None or not info.connected:
        raise ValueError("MT5 is disconnected")
    if not mt5.symbol_select(symbol, True):
        raise ValueError(f"Symbol unavailable: {symbol}")
    tick = mt5.symbol_info_tick(symbol)
    broker = mt5.symbol_info(symbol)
    account = mt5.account_info()
    if tick is None or broker is None or account is None:
        raise ValueError("Missing quote, broker specifications or account data")
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 1, 5000)
    if rates is None or len(rates) == 0:
        raise ValueError("No closed M1 candles available")
    now = datetime.now(timezone.utc)
    quote_age = now.timestamp() - tick.time
    # Broker and Windows clocks can differ by a fraction of a second.
    if not -2 <= quote_age <= 15:
        raise ValueError(f"Quote is stale or in the future (age={quote_age:.2f}s)")
    candles = pd.DataFrame(rates)
    candles["time"] = pd.to_datetime(candles["time"], unit="s", utc=True)
    frames = prepare_scalping_data(candles, asof=pd.Timestamp(now))
    if frames["M1"].empty:
        raise ValueError("No closed M1 candles available")
    latest = frames["M1"].index[-1]
    if not 60 <= now.timestamp() - latest.timestamp() <= 180:
        raise ValueError("Latest closed candle is stale or in the future")
    signal = strategy.predict(frames["M1"], frames["M5"], frames["M15"], spread=tick.ask - tick.bid)
    quote = {
        "bid": tick.bid,
        "ask": tick.ask,
        "tick_size": broker.trade_tick_size,
        "tick_value": broker.trade_tick_value_loss,
        "volume_min": broker.volume_min,
        "volume_max": broker.volume_max,
        "volume_step": broker.volume_step,
        "minimum_stop_distance": getattr(broker, "trade_stops_level", 0)
        * getattr(broker, "point", 0),
    }
    exposure = assess_exposure(
        mt5.positions_get(),
        mt5.orders_get(),
        equity=account.equity,
        cap_percent=max_total_risk,
        symbol=symbol,
        calc_profit=mt5.order_calc_profit,
        cost_per_lot=cost_per_lot,
    )
    plan = future_entry(
        signal,
        quote,
        frames["M1"].iloc[-1],
        account.equity,
        risk_percent,
        getattr(strategy, "risk_reward", 2.0),
    )
    plan.update(bid=tick.bid, ask=tick.ask)
    levels = getattr(strategy, "last_levels", {})
    if levels and "entry_details" in plan:
        plan["entry_details"].update(levels)
        buy = signal.direction == 1
        anchor = levels["range_low" if buy else "range_high"]
        plan["entry_details"]["stop_rule"] = (
            f"SL: {'day' if buy else 'dinh'} 5 nen truoc {anchor:.3f} "
            f"{'-' if buy else '+'} 0.1 ATR ({levels['stop_buffer']:.3f}), lam tron tick"
        )
    apply_sizing(
        plan,
        symbol,
        broker,
        account,
        sizing=sizing,
        risk_percent=risk_percent,
        kelly_history=kelly_history,
        kelly_fraction=kelly_fraction,
        min_trades=min_trades,
        cost_per_lot=cost_per_lot,
        slippage_ticks=slippage_ticks,
        exposure=exposure,
        strategy_id=getattr(strategy, "strategy_id", STRATEGY_ID),
    )
    reference_reasons = {"No valid setup", "Spread exceeds ATR budget", "Abnormal candle range"}
    always_reference = getattr(strategy, "always_reference", False)
    if signal.direction == 0 and (signal.reason in reference_reasons or (
        always_reference and getattr(strategy, "last_reference_safe", False)
    )):
        # Unsatisfied entry conditions do not turn into new trade recommendations.
        try:
            requires_m15 = getattr(strategy, "requires_m15", True)
            preferred = preferred_direction(frames, require_m15=requires_m15)
            if preferred == 0 and not always_reference:
                raise ValueError(
                    "M15 trend and M5 momentum do not agree; wait for a clear direction"
                )
            if preferred:
                plan["preferred_side"] = "BUY" if preferred == 1 else "SELL"
            plan["direction_reason"] = (
                "M15 EMA200 trend agrees with M5 EMA9/EMA21 momentum"
                if requires_m15
                else "M5 EMA9/EMA21 selects direction; M15 is warning only"
            )
            if preferred == 0:
                plan["direction_reason"] = "No agreed direction; two independent reference scenarios, not simultaneous orders"
            annotated = XAUUSDM1Scalper.indicators(frames["M1"])
            atr = float(annotated["atr"].iloc[-1])
            if not math.isfinite(atr) or atr <= 0:
                raise ValueError("ATR unavailable for reference scenarios")
            candle = frames["M1"].iloc[-1]
            lookback = getattr(strategy, "swing_lookback", 5)
            distance = atr * getattr(strategy, "atr_sl_multiplier", 1.5)
            close = float(candle["close"])
            stops = {
                1: min(
                    close - distance, float(frames["M1"]["low"].iloc[-lookback:].min()) - 0.1 * atr
                ),
                -1: max(
                    close + distance, float(frames["M1"]["high"].iloc[-lookback:].max()) + 0.1 * atr
                ),
            }
            if isinstance(strategy, ORB5MTF):
                stops = {1: float(frames["M1"].low.iloc[-6:-1].min()) - .1 * atr,
                         -1: float(frames["M1"].high.iloc[-6:-1].max()) + .1 * atr}
            plan["reference_scenarios"] = []
            for direction in ((preferred,) if preferred else (1, -1)):
                reference = future_entry(
                    ScalperSignal(
                        direction, 0, stops[direction], None, "Unconfirmed reference scenario"
                    ),
                    quote,
                    candle,
                    0,
                    risk_percent,
                    getattr(strategy, "risk_reward", 2.0),
                )
                reference.update(bid=tick.bid, ask=tick.ask)
                apply_sizing(
                    reference,
                    symbol,
                    broker,
                    account,
                    sizing="fixed",
                    risk_percent=risk_percent,
                    kelly_history=None,
                    kelly_fraction=kelly_fraction,
                    min_trades=min_trades,
                    cost_per_lot=cost_per_lot,
                    slippage_ticks=slippage_ticks,
                    exposure=exposure,
                )
                if always_reference or signal.reason != "No valid setup":
                    reference.update(
                        volume=None,
                        estimated_risk=None,
                        sizing_note="Entry blocked: " + signal.reason,
                    )
                    for key in (
                        "estimated_margin",
                        "estimated_net_profit",
                        "net_reward_risk",
                        "risk_budget",
                        "effective_risk_percent",
                        "selected_risk_percent",
                    ):
                        reference.pop(key, None)
                reference.update(
                    status="REFERENCE_ONLY",
                    currency=account.currency,
                    sizing_mode="hypothetical_fixed_risk",
                    reference_risk_percent=risk_percent,
                    warning="Entry conditions not met. Hypothetical fixed-risk lot, not Kelly or an entry recommendation.",
                )
                reference["distance_to_entry"] = abs(
                    reference["entry"] - (tick.ask if direction == 1 else tick.bid)
                )
                reference["distance_atr"] = reference["distance_to_entry"] / atr
                plan["reference_scenarios"].append(reference)
        except (ValueError, TypeError, KeyError) as exc:
            plan["reference_note"] = str(exc)
    plan.update(
        symbol=symbol,
        strategy_id=getattr(strategy, "strategy_id", STRATEGY_ID),
        experimental=getattr(strategy, "experimental", False),
        setup_type=getattr(
            strategy, "last_setup", "TREND_PULLBACK" if signal.direction else "WAIT"
        ),
        strategy_checks=getattr(strategy, "last_checks", []),
        indicators=indicator_summary(frames),
        account_risk=exposure,
        equity=account.equity,
        currency=account.currency,
        risk_percent=risk_percent,
        candle_time_utc=latest.isoformat(),
        generated_at_utc=now.isoformat(),
        expires_at_utc=datetime.fromtimestamp(
            min(tick.time + 15, latest.timestamp() + 180), timezone.utc
        ).isoformat(),
    )
    direction = signal.direction or {"BUY": 1, "SELL": -1}.get(plan.get("preferred_side"), 0)
    if forecast_model is not None:
        try:
            plan["forecast"] = forecast_snapshot(forecast_model, frames["M1"], symbol)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            plan["forecast"] = {"validation_status": "UNAVAILABLE", "reason": str(exc)}
    if not getattr(strategy, "requires_m15", True) and direction:
        plan["direction_reason"] = "M5 EMA9/EMA21 selects direction; M15 is warning only"
        m15_state = next(
            (row["state"] for row in plan["indicators"] if row["timeframe"] == "M15"), "UNAVAILABLE"
        )
        if m15_state in ("BUY", "SELL") and m15_state != ("BUY" if direction == 1 else "SELL"):
            plan["mtf_warning"] = "M15 nguoc huong M5; chi canh bao, khong chan setup M5/M1"
    plan["higher_timeframes"] = {}
    context_frames = (
        (("H1", 60, "TIMEFRAME_H1"), ("H4", 240, "TIMEFRAME_H4"))
        if include_higher_timeframes
        else ()
    )
    for label, minutes, constant in context_frames:
        try:
            bars = mt5.copy_rates_from_pos(symbol, getattr(mt5, constant), 1, 300)
            plan["higher_timeframes"][label] = analyze_context(
                bars, minutes, datetime.now(timezone.utc), XAUUSDM1Scalper.indicators
            )
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError) as exc:
            plan["higher_timeframes"][label] = {"state": "UNAVAILABLE", "reason": str(exc)}
    plan["setup_probability"] = {
        "status": "UNVALIDATED",
        "value": None,
        "reason": "No out-of-sample calibrated model for this entry/exit setup",
    }
    if direction and isinstance(strategy, ORB5MTF):
        plan["setup_checks"] = strategy.last_checks
    elif direction:
        side = "BUY" if direction == 1 else "SELL"
        conflicts = [
            label
            for label, context in plan["higher_timeframes"].items()
            if context["state"] in ("BUY", "SELL") and context["state"] != side
        ]
        if conflicts:
            plan["mtf_warning"] = (
                plan.get("mtf_warning", "")
                + " Huong dang xem nguoc xu huong "
                + ", ".join(conflicts)
            ).strip()
    if direction:
        enriched = {key: XAUUSDM1Scalper.indicators(frame) for key, frame in frames.items()}
        plan["setup_checks"] = setup_checklist(
            enriched["M1"],
            enriched["M5"],
            enriched["M15"],
            direction,
            tick.ask - tick.bid,
            adx_threshold=getattr(strategy, "adx_threshold", 20),
            max_spread_atr=getattr(strategy, "max_spread_atr", 0.15),
            max_candle_atr=getattr(strategy, "max_candle_atr", 3),
            require_m15=getattr(strategy, "requires_m15", True),
        )
        if plan["setup_type"] == "TREND_BREAKOUT":
            plan["setup_checks"] = [
                check
                for check in plan["setup_checks"]
                if check["label"] != "M1 hoi va vuot lai EMA21"
            ]
    if datetime.now(timezone.utc).timestamp() >= min(tick.time + 15, latest.timestamp() + 180):
        plan.update(
            status="BLOCKED",
            reason="Snapshot expired during analysis; press Enter again",
            volume=None,
            estimated_risk=None,
        )
        plan.pop("reference_scenarios", None)
    return plan


def publish(path, plan):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(plan, indent=2, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


def display(plan, console=None):
    render_plan(plan, console)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="XAUUSDc")
    parser.add_argument("--forecast-model", type=Path,
                        help="Optional JSON five-minute direction forecast; research display only")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--profile", choices=("scalping", "trend"),
                           help="scalping: experimental confirmed M1/M5 breakout; trend: Donchian D1 demo")
    selection.add_argument(
        "--strategy",
        choices=(
            "m1_m5_confirmed",
            "m1_m5_breakout",
            "orb5_mtf",
            "adaptive",
            "pullback",
            "m5_m1",
            "m5_m1_quality",
            "m5_m1_regime",
            "donchian_55_20",
        ),
        default=None,
        help="Entry strategy (default: experimental m1_m5_confirmed, no session filter)",
    )
    parser.add_argument(
        "--higher-timeframes",
        action="store_true",
        help="Optionally show H1/H4 context; disabled by default",
    )
    parser.add_argument("--risk-percent", type=float, default=0.5)
    parser.add_argument(
        "--max-total-risk",
        type=float,
        default=2.0,
        help="Account-wide estimated stop risk cap in percent of equity",
    )
    parser.add_argument(
        "--sizing",
        choices=("kelly", "fixed"),
        default=None,
        help="Default: fixed for Donchian demo, Kelly for M1 strategies",
    )
    parser.add_argument(
        "--position-ticket",
        type=int,
        help="Explicit Donchian demo position to review; never modifies it",
    )
    parser.add_argument("--kelly-history", type=Path, default=Path("logs/kelly_history.csv"))
    parser.add_argument("--kelly-fraction", type=float, default=0.25)
    parser.add_argument("--min-trades", type=int, default=50)
    parser.add_argument(
        "--cost-per-lot",
        type=float,
        default=0,
        help="Round-trip commission/fees per lot in account currency",
    )
    parser.add_argument("--slippage-ticks", type=int, default=2)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--color", choices=("auto", "always", "never"), default="auto")
    parser.add_argument("--output", type=Path, help="Optional JSON snapshot path")
    parser.add_argument("--log-file", type=Path, default=Path("logs/assistant_events.jsonl"))
    parser.add_argument("--no-log", action="store_true", help="Disable analysis event logging")
    parser.add_argument(
        "--log-summary",
        action="store_true",
        help="Summarize log and exit without connecting to MT5",
    )
    args = parser.parse_args()
    args.strategy = args.strategy or {
        "scalping": "m1_m5_confirmed", "trend": "donchian_55_20"
    }.get(args.profile, "m1_m5_confirmed")
    if args.forecast_model and args.strategy == "donchian_55_20":
        parser.error("--forecast-model is for M1 analysis; select a scalping strategy")
    args.sizing = args.sizing or ("fixed" if args.strategy == "donchian_55_20" else "kelly")
    if args.position_ticket is not None and (
        args.position_ticket <= 0 or args.strategy != "donchian_55_20"
    ):
        parser.error("--position-ticket requires Donchian and a positive ticket")
    if args.strategy == "donchian_55_20" and (args.sizing != "fixed" or args.risk_percent > 0.5):
        parser.error("Donchian demo requires fixed sizing and risk <= 0.5%")
    if not 0 < args.risk_percent <= 5:
        parser.error("--risk-percent must be in (0, 5]")
    if not 0 < args.max_total_risk <= 10:
        parser.error("--max-total-risk must be in (0, 10]")
    if not 0 < args.kelly_fraction <= 1 or not 30 <= args.min_trades <= 200:
        parser.error("--kelly-fraction must be in (0, 1]; --min-trades between 30 and 200")
    if not math.isfinite(args.cost_per_lot) or args.cost_per_lot < 0 or args.slippage_ticks < 0:
        parser.error("Costs and slippage must be finite and nonnegative")
    strategy = {
        "m1_m5_confirmed": ConfirmedM1M5,
        "m1_m5_breakout": RollingM1M5,
        "orb5_mtf": ORB5MTF,
        "adaptive": AdaptiveScalper,
        "pullback": XAUUSDM1Scalper,
        "m5_m1": M5M1Pullback,
        "m5_m1_quality": M5M1QualityPullback,
        "m5_m1_regime": M5M1RegimePullback,
        "donchian_55_20": Donchian5520,
    }[args.strategy]()
    console = Console(
        force_terminal=True if args.color == "always" else None,
        no_color=True if args.color == "never" else False if args.color == "always" else None,
        color_system="standard" if args.color == "always" else "auto",
    )
    if args.log_summary:
        try:
            console.print(Text(summarize_log(args.log_file), style="cyan"))
        except OSError as exc:
            console.print(Text(f"Khong doc duoc log: {exc}", style="yellow"))
        return
    frames_label = (
        "D1 Donchian 55/20 | DEMO" if args.strategy == "donchian_55_20" else "M1 / M5 / M15"
    )
    if not getattr(strategy, "requires_m15", True):
        frames_label = "M1 / M5 | M15 context only"
    console.print(Text(f"Bot ho tro {args.symbol} | {frames_label}", style="bold cyan"))
    console.print(
        Text(
            "Enter: phan tich | l: xem log | c: don man hinh | h: tro giup | q: thoat", style="dim"
        )
    )
    try:
        while True:
            if not args.once:
                command = input("\n[Enter] Phan tich | [q] Thoat: ").strip().lower()
                if command in ("q", "quit", "exit"):
                    break
                if command == "c":
                    console.clear()
                    continue
                if command == "l":
                    try:
                        console.print(Text(summarize_log(args.log_file), style="cyan"))
                    except OSError as exc:
                        console.print(Text(f"Khong doc duoc log: {exc}", style="yellow"))
                    continue
                if command == "h":
                    console.print(
                        Text(
                            "BUY xanh la | SELL do | WAIT vang | Gia vao xanh cyan\n"
                            "Enter chi phan tich mot lan. WAIT la chua xac nhan vao lenh.\n"
                            "Lot mo phong khong phai Kelly. N/A: xem ly do duoi bang.\n"
                            "l xem log; c don man hinh; q thoat; bot khong tu dat lenh.",
                            style="cyan",
                        )
                    )
                    continue
                if command:
                    print("Nhan Enter de phan tich, hoac q de thoat.")
                    continue
                console.clear()
            started = perf_counter()
            error_type = None
            try:
                if not mt5.initialize(timeout=10000):
                    raise ValueError("Cannot connect to the local MT5 terminal")
                plan = snapshot(
                    args.symbol,
                    args.risk_percent,
                    strategy,
                    sizing=args.sizing,
                    kelly_history=args.kelly_history,
                    kelly_fraction=args.kelly_fraction,
                    min_trades=args.min_trades,
                    cost_per_lot=args.cost_per_lot,
                    slippage_ticks=args.slippage_ticks,
                    max_total_risk=args.max_total_risk,
                    include_higher_timeframes=args.higher_timeframes,
                    position_ticket=args.position_ticket,
                    forecast_model=args.forecast_model,
                )
            except Exception as exc:
                error_type = type(exc).__name__
                plan = {
                    "status": "BLOCKED",
                    "reason": str(exc),
                    "symbol": args.symbol,
                    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                }
            finally:
                mt5.shutdown()
            elapsed_ms = (perf_counter() - started) * 1000
            if args.output:
                try:
                    publish(args.output, plan)
                except (OSError, ValueError) as exc:
                    console.print(Text(f"Khong luu duoc JSON: {exc}", style="yellow"))
            display(plan, console)
            if not args.no_log:
                try:
                    record_analysis(args.log_file, plan, elapsed_ms, error_type)
                except (OSError, ValueError) as exc:
                    console.print(Text(f"Khong ghi duoc log: {exc}", style="yellow"))
            console.print(Text(f"Thoi gian phan tich: {elapsed_ms:.0f} ms", style="dim"))
            if args.once:
                return
    except (KeyboardInterrupt, EOFError):
        pass
    print("Da dung bot.")


if __name__ == "__main__":
    main()
