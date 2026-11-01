"""Replay observable bid/ask events; missing paths are unknown, never assumed flat."""

import math

import numpy as np
import pandas as pd


class TickReplay:
    def __init__(self, ticks, max_gap_seconds=30):
        data = pd.DataFrame(ticks).copy()
        if not {"time_msc", "bid", "ask"}.issubset(data):
            raise ValueError("Ticks require time_msc, bid, ask")
        data["time_msc"] = pd.to_numeric(data["time_msc"], errors="raise")
        if (
            data.empty
            or not np.isfinite(data[["time_msc", "bid", "ask"]].to_numpy(dtype=float)).all()
        ):
            raise ValueError("Empty or nonfinite ticks")
        if (data["time_msc"] % 1 != 0).any():
            raise ValueError("Tick time_msc must be integer milliseconds")
        data.index = pd.to_datetime(data["time_msc"], unit="ms", utc=True)
        if (
            not data.index.is_monotonic_increasing
            or (data["bid"] <= 0).any()
            or (data["ask"] < data["bid"]).any()
        ):
            raise ValueError("Ticks must be ordered, positive and have ask >= bid")
        if not math.isfinite(max_gap_seconds) or max_gap_seconds <= 0:
            raise ValueError("Tick gap threshold must be positive")
        self.data = data
        self.max_gap = pd.Timedelta(seconds=max_gap_seconds)

    def quote_at(self, when):
        i = self.data.index.searchsorted(when, side="right") - 1
        if i < 0 or when - self.data.index[i] > pd.Timedelta(seconds=15):
            return None
        row = self.data.iloc[i]
        return {"bid": float(row["bid"]), "ask": float(row["ask"]), "time": self.data.index[i]}

    def simulate(
        self, bars, start, end, plan, *, quote_time, slippage=0.0, fee_price=0.0, max_hold=120
    ):
        decision = bars.index[start]
        expiry = min(
            decision + pd.Timedelta(seconds=15), quote_time.floor("s") + pd.Timedelta(seconds=15)
        )
        boundary = bars.index[end] if end < len(bars) else bars.index[-1] + pd.Timedelta(minutes=1)
        begin = self.data.index.searchsorted(decision, side="left")
        pending_end = self.data.index.searchsorted(min(expiry, boundary), side="left")
        coverage_end = min(pending_end, len(self.data) - 1)
        prior = self.data.index.searchsorted(quote_time, side="right") - 1
        begin = max(begin, prior + 1)
        covered = self.data.index[-1] >= min(expiry, boundary)
        if (
            prior < 0
            or not covered
            or (
                self.data.index[prior : coverage_end + 1].to_series().diff().dropna() > self.max_gap
            ).any()
        ):
            return {"unknown": True, "filled": False, "reason": "Incomplete pending tick window"}
        buy = plan["side"] == "BUY"
        direction = 1 if buy else -1
        trigger, stop, target = plan["entry"], plan["stop_loss"], plan["take_profit"]
        entry_index = None
        for i in range(begin, pending_end):
            price = float(self.data.iloc[i]["ask" if buy else "bid"])
            if direction * (price - trigger) >= 0:
                entry_index = i
                entry = price + direction * slippage
                break
        if entry_index is None:
            return None
        risk = direction * (entry - stop) + slippage + fee_price
        if not math.isfinite(risk) or risk <= 0:
            return {"unknown": True, "filled": True, "reason": "Invalid risk at tick fill"}
        entry_time = self.data.index[entry_index]
        deadline = min(entry_time + pd.Timedelta(minutes=max_hold), boundary)
        stop_index = self.data.index.searchsorted(deadline, side="left")
        exit_price = None
        last_processed = entry_index
        reason = "SEGMENT_END" if deadline == boundary else "TIMEOUT"
        for i in range(entry_index, min(stop_index + 1, len(self.data))):
            timestamp = self.data.index[i]
            if timestamp >= boundary:
                break
            if i > entry_index and timestamp - self.data.index[i - 1] > self.max_gap:
                return {"unknown": True, "filled": True, "reason": "Tick gap while position open"}
            last_processed = i
            price = float(self.data.iloc[i]["bid" if buy else "ask"])
            if direction * (price - stop) <= 0:
                exit_price, reason = price - direction * slippage, "SL"
                break
            if direction * (price - target) >= 0:
                exit_price, reason = target - direction * slippage, "TP"
                break
            exit_price = price - direction * slippage
            if timestamp >= deadline:
                break
        if exit_price is None:
            return {"unknown": True, "filled": True, "reason": "Missing exit quotes"}
        if reason in ("TIMEOUT", "SEGMENT_END") and (
            self.data.index[-1] < deadline
            or deadline - self.data.index[last_processed] > self.max_gap
        ):
            return {"unknown": True, "filled": True, "reason": "Incomplete timeout tick coverage"}
        # i can point at the first next-segment event: retain the last in-segment quote.
        i = last_processed
        exit_time = self.data.index[i]
        exit_bar = max(start, min(end - 1, bars.index.searchsorted(exit_time, side="right") - 1))
        return {
            "entry_time_utc": entry_time.isoformat(),
            "exit_time_utc": exit_time.isoformat(),
            "exit_index": int(exit_bar),
            "side": plan["side"],
            "entry": entry,
            "stop_loss": stop,
            "take_profit": target,
            "exit_price": exit_price,
            "outcome": reason,
            "ambiguous_path": self.data.index[entry_index : i + 1].has_duplicates,
            "net_r": (direction * (exit_price - entry) - fee_price) / risk,
        }
