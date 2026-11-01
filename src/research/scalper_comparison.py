"""Causal, single-position OHLC comparison. Research only; never sends orders."""

import math

import numpy as np
import pandas as pd

from src.strategies.adaptive_scalper import AdaptiveScalper
from src.strategies.entry_support import future_entry
from src.strategies.m5_m1_pullback import M5M1Pullback, M5M1QualityPullback, M5M1RegimePullback
from src.strategies.scalping_data import prepare_scalping_data
from src.strategies.orb_mtf import ORB5MTF, RollingM1M5, ConfirmedM1M5
from src.strategies.session_engulfing import SessionEngulfing
from src.strategies.xauusd_m1_scalper import XAUUSDM1Scalper


def simulate_trade(bars, start, end, plan, spreads, *, slippage=0.0, fee_price=0.0, max_hold=120):
    """One-bar pending proxy. Both exits touched => stop first, including fill bar."""
    direction = 1 if plan["side"] == "BUY" else -1
    first = bars.iloc[start]
    trigger, stop, target = plan["entry"], plan["stop_loss"], plan["take_profit"]
    entry_spread = float(spreads.iloc[start])
    if direction == 1:
        if first["high"] + entry_spread < trigger:
            return None
        entry = max(trigger, first["open"] + entry_spread) + slippage
    else:
        if first["low"] > trigger:
            return None
        entry = min(trigger, first["open"]) - slippage
    if direction * (entry - stop) <= 0:
        return None
    # Budget includes adverse stop slippage and supplied round-trip commission.
    risk = abs(entry - stop) + slippage + fee_price
    if not math.isfinite(risk) or risk <= 0:
        return None
    if direction * (target - entry) <= 0:
        exit_price = (
            float(first["open"]) + (entry_spread if direction == -1 else 0) - direction * slippage
        )
        return {
            "entry_time_utc": bars.index[start].isoformat(),
            "exit_time_utc": bars.index[start].isoformat(),
            "exit_index": start,
            "side": plan["side"],
            "entry": entry,
            "stop_loss": stop,
            "take_profit": target,
            "exit_price": exit_price,
            "outcome": "GAP_THROUGH_TARGET",
            "ambiguous_path": False,
            "net_r": (direction * (exit_price - entry) - fee_price) / risk,
        }
    finish = min(end, start + max_hold)
    ambiguous = False
    exit_price = None
    outcome = "TIMEOUT" if finish < end else "SEGMENT_END"
    for j in range(start, finish):
        bar = bars.iloc[j]
        if j > start and bars.index[j] - bars.index[j - 1] != pd.Timedelta(minutes=1):
            # Exit at next observed open; do not pretend the missing path is known.
            exit_price = float(bar["open"]) + (float(spreads.iloc[j]) if direction == -1 else 0)
            exit_price -= direction * slippage
            outcome = "DATA_GAP"
            break
        spread = float(spreads.iloc[j]) if direction == -1 else 0
        high, low, opened = (float(bar[key]) + spread for key in ("high", "low", "open"))
        stop_hit = low <= stop if direction == 1 else high >= stop
        target_hit = high >= target if direction == 1 else low <= target
        if stop_hit:
            # Stop gaps receive adverse open fills rather than guaranteed SL prices.
            exit_price = (
                min(stop, opened) if direction == 1 else max(stop, opened)
            ) - direction * slippage
            outcome = "SL"
            ambiguous = bool(target_hit or j == start)
            break
        if target_hit:
            exit_price = target - direction * slippage
            outcome = "TP"
            break
        exit_price = float(bar["close"]) + spread - direction * slippage
    return {
        "entry_time_utc": bars.index[start].isoformat(),
        "exit_time_utc": bars.index[j].isoformat(),
        "exit_index": j,
        "side": plan["side"],
        "entry": entry,
        "stop_loss": stop,
        "take_profit": target,
        "exit_price": exit_price,
        "outcome": outcome,
        "ambiguous_path": ambiguous,
        "net_r": (direction * (exit_price - entry) - fee_price) / risk,
    }


def summarize(trades, initial_equity=10000.0, risk_percent=0.5):
    equity = peak = initial_equity
    max_drawdown = 0.0
    results = [trade["net_r"] for trade in trades]
    for result in results:
        equity = max(0.0, equity * (1 + risk_percent / 100 * result))
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, (peak - equity) / peak * 100)
        if equity == 0:
            break
    profits = sum(max(0, result) for result in results)
    losses = -sum(min(0, result) for result in results)
    return {
        "trades": len(results),
        "win_rate": sum(result > 0 for result in results) / len(results) if results else None,
        "expectancy_r": sum(results) / len(results) if results else None,
        "total_r": sum(results),
        "profit_factor": profits / losses if losses else None,
        "ending_equity": equity,
        "return_percent": (equity / initial_equity - 1) * 100,
        "max_closed_trade_drawdown_percent": max_drawdown,
        "ambiguous_trades": sum(trade["ambiguous_path"] for trade in trades),
        "gap_trades": sum(trade["outcome"] == "DATA_GAP" for trade in trades),
    }


def compare(
    bars,
    spreads,
    *,
    tick_size=0.001,
    stop_distance=0.0,
    slippage_ticks=2,
    fee_price=0.0,
    max_hold=120,
    risk_percent=0.5,
    initial_equity=10000.0,
    progress=None,
    tick_replay=None,
    strategies=("pullback", "adaptive"),
    use_prefilter=True,
    min_net_reward_risk=0.0,
):
    if not bars.index.is_monotonic_increasing or bars.index.has_duplicates:
        raise ValueError("History must be chronological and unique")
    if len(bars) <= 3500:
        raise ValueError("Need more than 3500 closed M1 bars, including warm-up")
    if not bars.index.equals(spreads.index) or not all(
        math.isfinite(v) and v >= 0 for v in spreads
    ):
        raise ValueError("Missing, negative or nonfinite historical spreads")
    settings = (tick_size, risk_percent, initial_equity)
    if not all(math.isfinite(v) and v > 0 for v in settings) or not 0 < risk_percent <= 5:
        raise ValueError("Invalid tick size, risk or initial equity")
    if (
        not all(math.isfinite(v) and v >= 0 for v in (stop_distance, slippage_ticks, fee_price, min_net_reward_risk))
        or max_hold < 1
    ):
        raise ValueError("Invalid cost or holding settings")
    prepared = prepare_scalping_data(bars, bars.index[-1] + pd.Timedelta(minutes=1))
    # TA-Lib indicators are causal: precomputation does not use later prices.
    enriched = {key: XAUUSDM1Scalper.indicators(frame) for key, frame in prepared.items()}
    # Locate closed candles once. Scanning the complete history at every decision
    # is quadratic on year-long datasets; searchsorted preserves <= close time.
    positions = {
        key: (frame.index + pd.Timedelta(minutes=minutes)).searchsorted(bars.index, side="right")
        for (key, minutes), frame in zip(
            (("M1", 1), ("M5", 5), ("M15", 15)), enriched.values(), strict=True
        )
    }
    warmup = 3300
    split = warmup + int((len(bars) - warmup) * 0.7)
    all_trades, reports, events = [], {}, []
    factories = {
        "m1_m5_confirmed": ConfirmedM1M5,
        "m1_m5_breakout": RollingM1M5,
        "session_engulfing": SessionEngulfing,
        "orb5_mtf": ORB5MTF,
        "pullback": XAUUSDM1Scalper,
        "adaptive": AdaptiveScalper,
        "m5_m1": M5M1Pullback,
        "m5_m1_quality": M5M1QualityPullback,
        "m5_m1_regime": M5M1RegimePullback,
    }
    if (
        not strategies
        or len(set(strategies)) != len(strategies)
        or any(name not in factories for name in strategies)
    ):
        raise ValueError("Select unique known strategy names")
    for name in strategies:
        strategy = factories[name]()
        strategy.indicators = lambda frame: frame
        candidates = None
        a = enriched["M1"]
        if use_prefilter and name == "session_engulfing":
            previous_close, previous_open = a.close.shift(), a.open.shift()
            buy = ((previous_close < previous_open) & (a.close > a.open)
                   & (a.open <= previous_close) & (a.close >= previous_open))
            sell = ((previous_close > previous_open) & (a.close < a.open)
                    & (a.open >= previous_close) & (a.close <= previous_open))
            decision = a.index + pd.Timedelta(minutes=1)
            london = decision.tz_convert("Europe/London")
            new_york = decision.tz_convert("America/New_York")
            session = ((decision.weekday < 5)
                       & (((london.hour >= 8) & (london.hour < 12))
                          | ((new_york.hour >= 8) & (new_york.hour < 12))))
            candidates = np.flatnonzero(((buy | sell) & session).to_numpy()) + 1
        if use_prefilter and name in ("orb5_mtf", "m1_m5_breakout", "m1_m5_confirmed"):
            high = a.high.shift().rolling(5, min_periods=5).max()
            low = a.low.shift().rolling(5, min_periods=5).min()
            candidates = np.flatnonzero(((a.close > high) | (a.close < low)).to_numpy()) + 1
        if (
            use_prefilter
            and tick_replay is None
            and name in ("pullback", "m5_m1", "m5_m1_quality", "m5_m1_regime")
            and {"ema21", "rsi", "adx"}.issubset(a.columns)
        ):
            # Necessary baseline conditions only; full predict still performs all
            # price, gap, MTF, spread and subclass checks on every candidate.
            buy = (
                (a["close"].shift() <= a["ema21"].shift())
                & (a["close"] > a["ema21"])
                & (a["close"] > a["open"])
                & (a["rsi"] > 50)
                & (a["rsi"] < 75)
            )
            sell = (
                (a["close"].shift() >= a["ema21"].shift())
                & (a["close"] < a["ema21"])
                & (a["close"] < a["open"])
                & (a["rsi"] < 50)
                & (a["rsi"] > 25)
            )
            candidates = (
                np.flatnonzero(((buy | sell) & (a["adx"] > strategy.adx_threshold)).to_numpy()) + 1
            )
        reports[name] = {}
        for segment, begin, end in (("development", warmup, split), ("holdout", split, len(bars))):
            trades = []
            signals = 0
            cost_rejected_signals = 0
            missing_quotes = unknown_windows = unresolved_positions = 0
            i = begin
            last_progress = -1
            while i < end:
                if candidates is not None:
                    candidate = candidates.searchsorted(i)
                    if candidate >= len(candidates) or candidates[candidate] >= end:
                        break
                    i = int(candidates[candidate])
                if progress and i // 500 != last_progress:
                    progress(name, segment, i, len(bars))
                    last_progress = i // 500
                if bars.index[i] - bars.index[i - 1] != pd.Timedelta(minutes=1):
                    i += 1
                    continue
                decision = bars.index[i]
                frames = [
                    enriched[key].iloc[max(0, positions[key][i] - getattr(strategy, "history_bars", 240)) : positions[key][i]]
                    for key in ("M1", "M5", "M15")
                ]
                observed_quote = tick_replay.quote_at(decision) if tick_replay is not None else None
                if tick_replay is not None and observed_quote is None:
                    missing_quotes += 1
                    i += 1
                    continue
                spread = (
                    observed_quote["ask"] - observed_quote["bid"]
                    if observed_quote is not None
                    else float(spreads.iloc[i - 1])
                )
                signal = strategy.predict(*frames, spread=spread)
                if signal.direction == 0:
                    i += 1
                    continue
                signals += 1
                candle = bars.iloc[i - 1]
                quote = {
                    "bid": float(candle["close"]),
                    "ask": float(candle["close"]) + spread,
                    "tick_size": tick_size,
                    "minimum_stop_distance": stop_distance,
                }
                if observed_quote is not None:
                    quote.update(bid=observed_quote["bid"], ask=observed_quote["ask"])
                plan = future_entry(signal, quote, candle, 0, risk_percent, strategy.risk_reward)
                direction = signal.direction
                total_cost = 2 * slippage_ticks * tick_size + fee_price
                net_risk = direction * (plan["entry"] - plan["stop_loss"]) + total_cost
                net_reward = direction * (plan["take_profit"] - plan["entry"]) - total_cost
                if min_net_reward_risk and (net_risk <= 0 or net_reward / net_risk < min_net_reward_risk):
                    cost_rejected_signals += 1
                    i += 1
                    continue
                if tick_replay is not None:
                    trade = tick_replay.simulate(
                        bars,
                        i,
                        end,
                        plan,
                        quote_time=observed_quote["time"],
                        slippage=slippage_ticks * tick_size,
                        fee_price=fee_price,
                        max_hold=max_hold,
                    )
                    if trade is not None and trade.get("unknown"):
                        events.append(
                            {
                                "strategy": name,
                                "segment": segment,
                                "decision_utc": decision.isoformat(),
                                "status": "UNKNOWN",
                                "filled": trade["filled"],
                                "reason": trade["reason"],
                            }
                        )
                        unknown_windows += 1
                        if trade["filled"]:
                            unresolved_positions += 1
                            break  # Never assume an unresolved position is flat to enter again.
                        i += 1
                        continue
                else:
                    trade = simulate_trade(
                        bars,
                        i,
                        end,
                        plan,
                        spreads,
                        slippage=slippage_ticks * tick_size,
                        fee_price=fee_price,
                        max_hold=max_hold,
                    )
                if trade is None:
                    if tick_replay is not None:
                        events.append(
                            {
                                "strategy": name,
                                "segment": segment,
                                "decision_utc": decision.isoformat(),
                                "status": "EXPIRED_UNFILLED",
                                "filled": False,
                                "reason": "No trigger before pending expiry",
                            }
                        )
                    i += 1
                    continue
                trade.update(
                    strategy=name,
                    segment=segment,
                    setup_type=getattr(strategy, "last_setup", "TREND_PULLBACK"),
                )
                trades.append(trade)
                all_trades.append(trade)
                if tick_replay is not None:
                    events.append(
                        {
                            "strategy": name,
                            "segment": segment,
                            "decision_utc": decision.isoformat(),
                            "status": "CLOSED",
                            "filled": True,
                            "reason": trade["outcome"],
                        }
                    )
                i = trade["exit_index"] + 1
            reports[name][segment] = dict(
                summarize(trades, initial_equity, risk_percent),
                signals=signals,
                cost_rejected_signals=cost_rejected_signals,
                missing_decision_quotes=missing_quotes,
                unknown_tick_windows=unknown_windows,
                unresolved_positions=unresolved_positions,
                observed_paths_complete=not (
                    missing_quotes or unknown_windows or unresolved_positions
                ),
            )
    return {
        "results": reports,
        "trades": all_trades,
        "execution_events": events,
        "split_time_utc": bars.index[split].isoformat(),
        "warmup_bars": warmup,
        "verdict": "RESEARCH_ONLY_NOT_PROOF_OF_SUPERIORITY",
    }
