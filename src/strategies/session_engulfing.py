"""Research hypothesis: H1/M5 EMA trend, M1 engulfing, London/New York.

Not a reproduction of a published profitable system. No orders or live defaults.
"""

import math

import pandas as pd
import talib

from src.strategies.xauusd_m1_scalper import ScalperSignal, XAUUSDM1Scalper


class SessionEngulfing(XAUUSDM1Scalper):
    strategy_id = "h1_m5_m1_session_engulfing_v1"
    experimental = True
    history_bars = 800

    def __init__(self):
        super().__init__()
        self.last_setup = "WAIT"
        self.last_checks = []

    @staticmethod
    def session_open(decision):
        london = decision.tz_convert("Europe/London")
        new_york = decision.tz_convert("America/New_York")
        return decision.weekday() < 5 and (8 <= london.hour < 12 or 8 <= new_york.hour < 12)

    @staticmethod
    def hourly(m15, decision):
        grouped = m15.resample("1h", label="left", closed="left")
        frame = grouped.agg({"open": "first", "high": "max", "low": "min", "close": "last"})
        # Four aligned closed M15 candles, never a partial H1 candle.
        frame = frame.loc[(grouped.close.count() == 4) & (frame.index + pd.Timedelta(hours=1) <= decision)]
        return frame.dropna()

    def predict(self, m1, m5, m15, *, spread=None):
        self.last_setup = "WAIT"
        self.last_checks = []

        def wait(reason):
            return ScalperSignal(0, 0, None, None, "Session engulfing: " + reason)

        if not all(isinstance(f.index, pd.DatetimeIndex) and f.index.tz is not None
                   for f in (m1, m5, m15)) or m1.empty:
            return wait("Timezone-aware closed candles required")
        decision = m1.index[-1] + pd.Timedelta(minutes=1)
        if not self.session_open(decision):
            return wait("Outside London 08-12 / New York 08-12")
        baseline = super().predict(m1, m5, m15, spread=spread)
        if not baseline.direction and baseline.reason != "No valid setup":
            return wait(baseline.reason)
        if spread is None:
            return wait("Spread required")
        if any((f.index != f.index.floor(f"{minutes}min")).any()
               for f, minutes in ((m1, 1), (m5, 5), (m15, 15))):
            return wait("Unaligned candle timestamps")
        h1 = self.hourly(m15, decision)
        if len(h1) < 150:
            return wait("Need 150 complete H1 bars for EMA warm-up")
        age = decision - (h1.index[-1] + pd.Timedelta(hours=1))
        if not pd.Timedelta(0) <= age < pd.Timedelta(hours=1) or not (
            h1.index[-3:].to_series().diff().dropna() == pd.Timedelta(hours=1)
        ).all():
            return wait("Stale or gapped H1 context")
        a = self.indicators(m1)
        last, previous = a.iloc[-1], a.iloc[-2]

        def ema(frame, period):
            return float(talib.EMA(frame.close.to_numpy(dtype=float), timeperiod=period)[-1])

        h20, h50 = ema(h1, 20), ema(h1, 50)
        m20, m50 = ema(m5, 20), ema(m5, 50)
        entry_ema = ema(m1, 20)
        atr = float(last.atr)
        if not all(math.isfinite(v) for v in (h20, h50, m20, m50, entry_ema, atr)) or atr <= 0:
            return wait("Invalid indicators")
        buy = (previous.close < previous.open and last.close > last.open
               and last.open <= previous.close and last.close >= previous.open)
        sell = (previous.close > previous.open and last.close < last.open
                and last.open >= previous.close and last.close <= previous.open)
        direction = 1 if buy else -1 if sell else 0
        if not direction:
            return wait("No M1 body engulfing")
        checks = [
            ("H1 close/EMA20/EMA50 aligned", direction * (h1.close.iloc[-1] - h20) > 0
             and direction * (h20 - h50) > 0),
            ("M5 close/EMA20/EMA50 aligned", direction * (m5.close.iloc[-1] - m20) > 0
             and direction * (m20 - m50) > 0),
            ("M1 two-candle pullback touches EMA20", min(previous.low, last.low) <= entry_ema <= max(previous.high, last.high)),
            ("M1 closes back with trend", direction * (last.close - entry_ema) > 0),
        ]
        self.last_checks = [{"label": label, "passed": bool(ok)} for label, ok in checks]
        if not all(ok for _, ok in checks):
            return wait("MTF or pullback conditions failed")
        stop = (min(previous.low, last.low) - .1 * atr if direction == 1
                else max(previous.high, last.high) + .1 * atr)
        # Budget $1-$3 using future_entry with the research dataset's 0.001 tick.
        from src.strategies.entry_support import future_entry
        plan = future_entry(ScalperSignal(direction, .6, float(stop), None, "research"),
                            {"bid": float(last.close), "ask": float(last.close + spread),
                             "tick_size": .001, "minimum_stop_distance": 0},
                            last, 0, .5, self.risk_reward)
        if plan["status"] != "REVIEW":
            return wait("Invalid conditional entry")
        stop = plan["stop_loss"]
        distance = direction * (plan["entry"] - stop)
        if not 1 <= distance <= 3:
            return wait("Conditional entry to structural SL outside $1-$3")
        self.last_setup = "H1_M5_M1_ENGULFING"
        return ScalperSignal(direction, .6, float(stop),
                             float(plan["entry"] + direction * distance * self.risk_reward),
                             "Research H1/M5 trend + M1 engulfing; news/DXY unfiltered")
