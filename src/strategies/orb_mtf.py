"""Experimental rolling five-bar breakout, without a trading-session filter."""

import math

import pandas as pd

from src.strategies.xauusd_m1_scalper import ScalperSignal, XAUUSDM1Scalper


class ORB5MTF(XAUUSDM1Scalper):
    always_reference = True
    strategy_id = "rolling5_mtf_m1_v2"
    experimental = True

    def __init__(self):
        super().__init__()
        self.last_checks = []
        self.last_setup = "WAIT"
        self.last_levels = {}
        self.last_reference_safe = False

    def predict(self, m1, m5, m15, *, spread=None):
        self.last_checks = []
        self.last_setup = "WAIT"
        self.last_levels = {}
        self.last_reference_safe = False

        def wait(reason):
            return ScalperSignal(0, 0, None, None, "Rolling5: " + reason)

        if not all(isinstance(f.index, pd.DatetimeIndex) for f in (m1, m5, m15)):
            return wait("Timezone-aware candle timestamps required")
        # Reuse OHLC, continuity, alignment, spread and abnormal-candle guards.
        baseline = super().predict(m1, m5, m15, spread=spread)
        self.last_reference_safe = bool(baseline.direction or baseline.reason in {
            "No valid setup", "Spread exceeds ATR budget", "Abnormal candle range"
        })
        if not baseline.direction and baseline.reason != "No valid setup":
            return wait(baseline.reason)
        if spread is None:
            self.last_reference_safe = False
            return wait("Live spread required")
        if not (m1.index[-6:].to_series().diff().dropna() == pd.Timedelta(minutes=1)).all():
            self.last_reference_safe = False
            return wait("Five-bar range candle gap")
        # Exclude the confirmation candle; no New York anchor or daily quota.
        opening = m1.iloc[-6:-1]
        high, low = float(opening.high.max()), float(opening.low.min())
        a, b = (self.indicators(f).iloc[-1] for f in (m1, m5))
        c = self.indicators(m15).iloc[-1] if self.requires_m15 else None
        values = [a.atr, b.ema9, b.ema21]
        if c is not None:
            values.extend([c.close, c.ema200])
        if not all(math.isfinite(v) for v in values) or a.atr <= 0 or high <= low:
            self.last_reference_safe = False
            return wait("Indicators or opening range unavailable")
        direction = 1 if a.close > high else -1 if a.close < low else 0
        checks = [
            ("M1 close outside previous five bars", direction != 0),
            ("M5 EMA9/21 agrees", direction * (b.ema9 - b.ema21) > 0),
            ("M1 candle agrees", direction * (a.close - a.open) > 0),
        ]
        if c is not None:
            checks.append(("M15 close/EMA200 agrees", direction * (c.close - c.ema200) > 0))
        self.last_checks = [{"label": label, "passed": bool(ok)} for label, ok in checks]
        if not all(ok for _, ok in checks):
            return wait("Waiting for rolling M1 breakout with timeframe agreement")
        stop = low - 0.1 * a.atr if direction == 1 else high + 0.1 * a.atr
        self.last_levels = {"range_high": high, "range_low": low, "stop_buffer": float(.1 * a.atr)}
        distance = direction * (a.close - stop)
        self.last_setup = "ROLLING5_MTF_M1"
        return ScalperSignal(direction, 0.6, float(stop),
                             float(a.close + direction * distance * self.risk_reward),
                             "Rolling five-bar M1 breakout + M5/M15; experimental")


class RollingM1M5(ORB5MTF):
    """Separate research candidate: M5 selects direction, M1 confirms breakout."""

    requires_m15 = False
    strategy_id = "rolling5_m1_m5_v1"

    def predict(self, m1, m5, m15, *, spread=None):
        from dataclasses import replace

        signal = super().predict(m1, m5, m15, spread=spread)
        if signal.direction:
            self.last_setup = "ROLLING5_M1_M5"
            return replace(signal, reason="Rolling five-bar M1 breakout + M5 momentum; experimental")
        return signal


class ConfirmedM1M5(RollingM1M5):
    """Experimental quality filters, fixed before comparison; no win-rate claim."""

    strategy_id = "confirmed_rolling5_m1_m5_v1"

    def __init__(self):
        super().__init__()
        self.max_spread_atr = .10
        self.max_candle_atr = 2.5

    def predict(self, m1, m5, m15, *, spread=None):
        signal = super().predict(m1, m5, m15, spread=spread)
        if not signal.direction:
            return signal
        self.last_setup = "WAIT"
        a, b = self.indicators(m1), self.indicators(m5)
        last, trend = a.iloc[-1], b.iloc[-1]
        values = [last.ema21, trend.adx, b.ema21.iloc[-4]]
        if not all(math.isfinite(value) for value in values):
            self.last_reference_safe = False
            return ScalperSignal(0, 0, None, None, "Confirmation indicators unavailable")
        direction = signal.direction
        level = m1.high.iloc[-6:-1].max() if direction == 1 else m1.low.iloc[-6:-1].min()
        width = last.high - last.low
        checks = [
            ("M5 ADX >= 20", trend.adx >= 20),
            ("M5 EMA21 slope agrees", direction * (trend.ema21 - b.ema21.iloc[-4]) > 0),
            ("M5 slope window continuous", (m5.index[-4:].to_series().diff().dropna() == pd.Timedelta(minutes=5)).all()),
            ("M1 body >= 40% of range", width > 0 and abs(last.close - last.open) >= .4 * width),
            ("Breakout close >= 0.1 ATR beyond range", direction * (last.close - level) >= .1 * last.atr),
            ("M1 extension from EMA21 <= 1.5 ATR", abs(last.close - last.ema21) <= 1.5 * last.atr),
        ]
        self.last_checks.extend({"label": label, "passed": bool(ok)} for label, ok in checks)
        if not all(ok for _, ok in checks):
            return ScalperSignal(0, 0, None, None, "Confirmation failed: " + "; ".join(label for label, ok in checks if not ok))
        self.last_setup = "CONFIRMED_ROLLING5_M1_M5"
        return signal
