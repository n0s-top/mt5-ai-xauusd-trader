"""XAUUSD M1 trend-pullback scalping signal generator.

Returns signals only. Does not place orders.
Uses closed candles from M1, M5 and M15.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class ScalperSignal:
    direction: int
    confidence: float
    stop_loss: float | None
    take_profit: float | None
    reason: str


class XAUUSDM1Scalper:
    def __init__(
        self,
        atr_sl_multiplier: float = 1.5,
        risk_reward: float = 2.0,
        adx_threshold: float = 20.0,
        max_spread_atr: float = 0.15,
        max_candle_atr: float = 3.0,
        swing_lookback: int = 5,
    ):
        settings = [atr_sl_multiplier, risk_reward, adx_threshold, max_spread_atr, max_candle_atr]
        if not np.isfinite(settings).all() or any(value <= 0 for value in settings):
            raise ValueError("Strategy parameters must be finite and positive")
        if risk_reward < 1 or adx_threshold > 100:
            raise ValueError("risk_reward must be >= 1 and ADX threshold <= 100")
        if not isinstance(swing_lookback, int) or not 2 <= swing_lookback <= 200:
            raise ValueError("swing_lookback must be an integer between 2 and 200")
        self.atr_sl_multiplier = atr_sl_multiplier
        self.risk_reward = risk_reward
        self.adx_threshold = adx_threshold
        self.max_spread_atr = max_spread_atr
        self.max_candle_atr = max_candle_atr
        self.swing_lookback = swing_lookback

    @staticmethod
    def indicators(df: pd.DataFrame) -> pd.DataFrame:
        import talib

        result = df.copy()
        close = result["close"].to_numpy(dtype=np.float64)
        high = result["high"].to_numpy(dtype=np.float64)
        low = result["low"].to_numpy(dtype=np.float64)

        result["ema9"] = talib.EMA(close, timeperiod=9)
        result["ema21"] = talib.EMA(close, timeperiod=21)
        result["ema200"] = talib.EMA(close, timeperiod=200)
        result["rsi"] = talib.RSI(close, timeperiod=14)
        result["adx"] = talib.ADX(high, low, close, timeperiod=14)
        result["atr"] = talib.ATR(high, low, close, timeperiod=14)

        return result

    def predict(
        self,
        m1: pd.DataFrame,
        m5: pd.DataFrame,
        m15: pd.DataFrame,
        *,
        spread: float | None = None,
    ) -> ScalperSignal:

        hold = ScalperSignal(0, 0.0, None, None, "No valid setup")

        if min(len(m1), len(m5), len(m15)) < 220:
            return ScalperSignal(0, 0.0, None, None, "Insufficient history")

        # Fail closed on malformed data, gaps around the setup, or stale context.
        for frame, minutes in ((m1, 1), (m5, 5), (m15, 15)):
            required_columns = {"open", "high", "low", "close"}
            if not required_columns.issubset(frame.columns):
                return ScalperSignal(0, 0.0, None, None, "Missing OHLC data")
            prices = frame[["open", "high", "low", "close"]]
            if not np.isfinite(prices.to_numpy(dtype=float)).all() or (prices <= 0).any().any():
                return ScalperSignal(0, 0.0, None, None, "Invalid OHLC data")
            if ((frame["high"] < prices.max(axis=1)) | (frame["low"] > prices.min(axis=1))).any():
                return ScalperSignal(0, 0.0, None, None, "Invalid OHLC geometry")
            if isinstance(frame.index, pd.DatetimeIndex):
                if (
                    frame.index.tz is None
                    or frame.index.hasnans
                    or not frame.index.is_monotonic_increasing
                    or frame.index.has_duplicates
                ):
                    return ScalperSignal(0, 0.0, None, None, "Invalid candle timestamps")
                if not (
                    frame.index[-self.swing_lookback :].to_series().diff().dropna()
                    == pd.Timedelta(minutes=minutes)
                ).all():
                    return ScalperSignal(0, 0.0, None, None, "Recent candle gap")

        if all(isinstance(frame.index, pd.DatetimeIndex) for frame in (m1, m5, m15)):
            decision_time = m1.index[-1] + pd.Timedelta(minutes=1)
            for frame, minutes in ((m5, 5), (m15, 15)):
                age = decision_time - (frame.index[-1] + pd.Timedelta(minutes=minutes))
                if age < pd.Timedelta(0) or age >= pd.Timedelta(minutes=minutes):
                    return ScalperSignal(0, 0.0, None, None, "Unsynchronized timeframes")

        a = self.indicators(m1)
        b = self.indicators(m5)
        c = self.indicators(m15)

        # Input must contain only fully closed candles.
        last = a.iloc[-1]
        prev = a.iloc[-2]
        trend = c.iloc[-1]
        momentum = b.iloc[-1]

        required = [
            last["ema9"],
            last["ema21"],
            last["rsi"],
            last["adx"],
            last["atr"],
            trend["ema200"],
            momentum["ema9"],
            momentum["ema21"],
            prev["ema21"],
            trend["close"],
            last["open"],
        ]

        if not np.isfinite(required).all():
            return hold

        price = float(last["close"])
        atr = float(last["atr"])

        if atr <= 0:
            return hold

        if spread is not None and (
            not np.isfinite(spread) or spread < 0 or spread > atr * self.max_spread_atr
        ):
            return ScalperSignal(0, 0.0, None, None, "Spread exceeds ATR budget")
        if last["high"] - last["low"] > atr * self.max_candle_atr:
            return ScalperSignal(0, 0.0, None, None, "Abnormal candle range")

        sl_distance = atr * self.atr_sl_multiplier

        buy = (
            trend["close"] > trend["ema200"]
            and momentum["ema9"] > momentum["ema21"]
            and prev["close"] <= prev["ema21"]
            and last["close"] > last["ema21"]
            and last["close"] > last["open"]
            and last["rsi"] > 50
            and last["rsi"] < 75
            and last["adx"] > self.adx_threshold
        )

        sell = (
            trend["close"] < trend["ema200"]
            and momentum["ema9"] < momentum["ema21"]
            and prev["close"] >= prev["ema21"]
            and last["close"] < last["ema21"]
            and last["close"] < last["open"]
            and last["rsi"] < 50
            and last["rsi"] > 25
            and last["adx"] > self.adx_threshold
        )

        if buy:
            sl_distance = max(
                sl_distance, price - float(a["low"].iloc[-self.swing_lookback :].min()) + 0.1 * atr
            )
            return ScalperSignal(
                direction=1,
                confidence=0.6,
                stop_loss=price - sl_distance,
                take_profit=price + sl_distance * self.risk_reward,
                reason="M1 BUY pullback + M5/M15 trend",
            )

        if sell:
            sl_distance = max(
                sl_distance, float(a["high"].iloc[-self.swing_lookback :].max()) - price + 0.1 * atr
            )
            return ScalperSignal(
                direction=-1,
                confidence=0.6,
                stop_loss=price + sl_distance,
                take_profit=price - sl_distance * self.risk_reward,
                reason="M1 SELL pullback + M5/M15 trend",
            )

        return hold
