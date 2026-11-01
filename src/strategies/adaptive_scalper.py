"""Experimental trend-regime filter with pullback and confirmed breakout setups."""

import math

import pandas as pd

from src.strategies.xauusd_m1_scalper import ScalperSignal, XAUUSDM1Scalper


class AdaptiveScalper(XAUUSDM1Scalper):
    strategy_id = "adaptive_trend_breakout_v1"
    experimental = True

    def __init__(self):
        super().__init__(max_spread_atr=0.10, max_candle_atr=2.5)
        self.last_checks = []
        self.last_setup = "WAIT"

    def predict(self, m1, m5, m15, *, spread=None):
        self.last_checks = []
        self.last_setup = "WAIT"
        baseline = super().predict(m1, m5, m15, spread=spread)
        # Preserve every upstream data, synchronization and spread rejection.
        if baseline.direction == 0 and baseline.reason != "No valid setup":
            return baseline
        a, b, c = (self.indicators(frame) for frame in (m1, m5, m15))
        last, momentum, trend = a.iloc[-1], b.iloc[-1], c.iloc[-1]
        try:
            required = [last[key] for key in ("close", "open", "ema21", "atr", "rsi", "adx")]
            required += [momentum[key] for key in ("adx", "ema9", "ema21", "atr")]
            required += [trend["close"], trend["ema200"], b["ema21"].iloc[-4]]
            if (
                not all(math.isfinite(value) for value in required)
                or min(last["atr"], momentum["atr"]) <= 0
            ):
                return ScalperSignal(0, 0, None, None, "Adaptive indicators unavailable")
            direction = 1 if trend["close"] > trend["ema200"] else -1
            checks = [
                (
                    "M15 va M5 cung huong",
                    direction * (trend["close"] - trend["ema200"]) > 0
                    and direction * (momentum["ema9"] - momentum["ema21"]) > 0,
                ),
                ("M5 ADX >= 25: tranh di ngang", momentum["adx"] >= 25),
                (
                    "EMA21 M5 co do doc cung huong",
                    direction * (momentum["ema21"] - b["ema21"].iloc[-4]) > 0,
                ),
                (
                    "EMA M5 tach nhau >= 0.1 ATR",
                    abs(momentum["ema9"] - momentum["ema21"]) >= 0.1 * momentum["atr"],
                ),
                (
                    "Khong duoi gia qua 1 ATR tu EMA21",
                    abs(last["close"] - last["ema21"]) <= last["atr"],
                ),
                ("Co quote spread de kiem tra", spread is not None),
            ]
            self.last_checks = [
                {"label": label, "passed": bool(passed)} for label, passed in checks
            ]
            if not all(passed for _, passed in checks):
                return ScalperSignal(0, 0, None, None, "No valid setup")
            if baseline.direction:
                self.last_setup = "TREND_PULLBACK"
                return baseline
            previous = a.iloc[-21:-1]
            volume = a["tick_volume"].iloc[-21:]
            if not all(math.isfinite(value) and value >= 0 for value in volume):
                raise ValueError("Invalid tick volume")
            volume_ok = (
                volume.iloc[:-1].mean() > 0 and volume.iloc[-1] >= 1.2 * volume.iloc[:-1].mean()
            )
            continuity = (
                not isinstance(a.index, pd.DatetimeIndex)
                or (a.index[-21:].to_series().diff().dropna() == pd.Timedelta(minutes=1)).all()
            )
            level = float(previous["high"].max() if direction == 1 else previous["low"].min())
            breakout = direction * (last["close"] - level) > 0.1 * last["atr"]
            rsi_ok = 50 < last["rsi"] < 75 if direction == 1 else 25 < last["rsi"] < 50
            extra = [
                ("Dong nen vuot vung 20 nen + 0.1 ATR", breakout),
                ("Tick volume >= 1.2 lan trung binh 20 nen", volume_ok),
                ("Du lieu 20 nen lien tuc", continuity),
                (
                    "Nen va RSI xac nhan breakout",
                    direction * (last["close"] - last["open"]) > 0
                    and rsi_ok
                    and last["adx"] > self.adx_threshold,
                ),
            ]
            self.last_checks.extend(
                {"label": label, "passed": bool(passed)} for label, passed in extra
            )
            if not all(passed for _, passed in extra):
                return ScalperSignal(0, 0, None, None, "No valid setup")
            price, atr = float(last["close"]), float(last["atr"])
            swing = float(
                a["low"].iloc[-self.swing_lookback :].min()
                if direction == 1
                else a["high"].iloc[-self.swing_lookback :].max()
            )
            distance = max(self.atr_sl_multiplier * atr, direction * (price - swing) + 0.1 * atr)
            self.last_setup = "TREND_BREAKOUT"
            return ScalperSignal(
                direction,
                0.6,
                price - direction * distance,
                price + direction * distance * self.risk_reward,
                "Adaptive trend + closed 20-bar breakout + tick volume",
            )
        except (KeyError, TypeError, ValueError):
            return ScalperSignal(0, 0, None, None, "Adaptive setup data unavailable")
