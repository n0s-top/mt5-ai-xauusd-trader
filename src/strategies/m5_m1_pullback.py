"""M5 momentum selects direction; M1 pullback confirms; M15 is context only."""

import math
from dataclasses import replace

import pandas as pd

from src.strategies.xauusd_m1_scalper import ScalperSignal, XAUUSDM1Scalper


class M5M1Pullback(XAUUSDM1Scalper):
    requires_m15 = False
    strategy_id = "m5_m1_pullback_v1"
    experimental = True

    def predict(self, m1, m5, m15, *, spread=None):
        signal = super().predict(m1, m5, m15, spread=spread)
        if signal.direction:
            return replace(signal, reason="M1 pullback + M5 momentum; M15 context only")
        return signal


class M5M1QualityPullback(M5M1Pullback):
    """Experimental M5/M1 filters; thresholds are hypotheses, not fitted estimates."""

    strategy_id = "m5_m1_quality_pullback_v1"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.last_checks = []
        self.last_setup = "WAIT"

    def predict(self, m1, m5, m15, *, spread=None):
        self.last_checks = []
        self.last_setup = "WAIT"
        baseline = super().predict(m1, m5, m15, spread=spread)
        if not baseline.direction:
            return baseline
        a, b = self.indicators(m1), self.indicators(m5)
        last, momentum = a.iloc[-1], b.iloc[-1]
        previous_ema = b["ema21"].iloc[-4]
        values = [last["atr"], momentum["atr"], previous_ema]
        if not all(math.isfinite(value) for value in values) or min(values[:2]) <= 0:
            return ScalperSignal(0, 0, None, None, "Quality indicators unavailable")
        checks = [
            ("Co quote spread de kiem tra", spread is not None),
            (
                "Du lieu do doc M5 lien tuc",
                not isinstance(b.index, pd.DatetimeIndex)
                or (b.index[-4:].to_series().diff().dropna() == pd.Timedelta(minutes=5)).all(),
            ),
            (
                "EMA21 M5 co do doc cung huong",
                baseline.direction * (momentum["ema21"] - previous_ema) > 0,
            ),
            (
                "EMA M5 tach nhau >= 0.1 ATR",
                abs(momentum["ema9"] - momentum["ema21"]) >= 0.1 * momentum["atr"],
            ),
            (
                "Khong duoi gia qua 1 ATR tu EMA21",
                abs(last["close"] - last["ema21"]) <= last["atr"],
            ),
        ]
        self.last_checks = [{"label": label, "passed": bool(ok)} for label, ok in checks]
        failed = [label for label, ok in checks if not ok]
        if failed:
            return ScalperSignal(0, 0, None, None, "Quality filter: " + "; ".join(failed))
        self.last_setup = "QUALITY_PULLBACK"
        return replace(baseline, reason="M1 pullback + M5 slope/separation + bounded extension")


class M5M1RegimePullback(M5M1QualityPullback):
    """Causal regime and trigger filters. Experimental, with separate Kelly history.

    Fixed thresholds are research hypotheses; confidence is not a win probability.
    Only closed candles are accepted, as in the parent strategy.
    """

    strategy_id = "m5_m1_regime_pullback_v2"

    def predict(self, m1, m5, m15, *, spread=None):
        baseline = super().predict(m1, m5, m15, spread=spread)
        if not baseline.direction:
            return baseline
        self.last_setup = "WAIT"
        a, b = self.indicators(m1), self.indicators(m5)
        last = a.iloc[-1]
        atr = float(last["atr"])
        # Compare current ATR with earlier values, excluding the trigger candle.
        history = a["atr"].iloc[-21:-1]
        closes = b["close"].iloc[-13:]
        values = [*history, *closes, baseline.stop_loss]
        if not all(math.isfinite(value) and value > 0 for value in values):
            self.last_checks.append({"label": "Regime history valid", "passed": False})
            return ScalperSignal(0, 0, None, None, "Regime history unavailable")
        travel = float(closes.diff().abs().sum())
        efficiency = abs(float(closes.iloc[-1] - closes.iloc[0])) / travel if travel else 0.0
        candle_range = float(last["high"] - last["low"])
        body = abs(float(last["close"] - last["open"]))
        location = (
            float(last["close"] - last["low"])
            if baseline.direction == 1
            else float(last["high"] - last["close"])
        )
        checks = []
        for frame, minutes, window in ((a, 1, 21), (b, 5, 13)):
            continuous = (
                isinstance(frame.index, pd.DatetimeIndex)
                and (
                    frame.index[-window:].to_series().diff().dropna()
                    == pd.Timedelta(minutes=minutes)
                ).all()
            )
            checks.append((f"Continuous M{minutes} regime window", continuous))
        checks.extend(
            [
                ("M5 directional efficiency >= 0.3", efficiency >= 0.3),
                (
                    "M5 net move agrees with entry",
                    baseline.direction * (closes.iloc[-1] - closes.iloc[0]) > 0,
                ),
                ("ATR within 0.5-2x prior median", 0.5 <= atr / float(history.median()) <= 2.0),
                ("Trigger body >= 30% of range", candle_range > 0 and body >= 0.3 * candle_range),
                (
                    "Trigger closes in directional 35%",
                    candle_range > 0 and location >= 0.65 * candle_range,
                ),
                (
                    "Structural stop <= 3 ATR",
                    abs(float(last["close"]) - baseline.stop_loss) <= 3 * atr,
                ),
            ]
        )
        self.last_checks.extend({"label": label, "passed": bool(ok)} for label, ok in checks)
        failed = [label for label, ok in checks if not ok]
        if failed:
            return ScalperSignal(0, 0, None, None, "Regime filter: " + "; ".join(failed))
        self.last_setup = "REGIME_PULLBACK"
        return replace(
            baseline, reason="M1 confirmed pullback + directional M5 regime + stable volatility"
        )
