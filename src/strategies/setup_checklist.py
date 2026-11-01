"""Explain the existing signal rules; checks are not win probabilities."""

import math


def setup_checklist(
    m1,
    m5,
    m15,
    direction,
    spread,
    *,
    adx_threshold=20,
    max_spread_atr=0.15,
    max_candle_atr=3,
    require_m15=True,
):
    lengths = [len(m1), len(m5)] + ([len(m15)] if require_m15 else [])
    if direction not in (-1, 1) or min(lengths) < 2:
        return []
    last, previous, momentum = m1.iloc[-1], m1.iloc[-2], m5.iloc[-1]
    trend = m15.iloc[-1] if require_m15 else None
    try:
        values = [last[k] for k in ("close", "open", "high", "low", "ema21", "rsi", "adx", "atr")]
        values += [
            previous["close"],
            previous["ema21"],
            momentum["ema9"],
            momentum["ema21"],
            spread,
        ]
        if require_m15:
            values.extend([trend["close"], trend["ema200"]])
        if not all(math.isfinite(v) for v in values) or last["atr"] <= 0:
            return []
        buy = direction == 1
        checks = [
            (
                "Xu huong M15 / EMA200",
                not require_m15 or direction * (trend["close"] - trend["ema200"]) > 0,
            ),
            ("Dong luong M5 / EMA9-21", direction * (momentum["ema9"] - momentum["ema21"]) > 0),
            (
                "M1 hoi va vuot lai EMA21",
                direction * (previous["close"] - previous["ema21"]) <= 0
                and direction * (last["close"] - last["ema21"]) > 0,
            ),
            ("Nen M1 cung huong", direction * (last["close"] - last["open"]) > 0),
            ("RSI M1 trong vung", 50 < last["rsi"] < 75 if buy else 25 < last["rsi"] < 50),
            ("ADX M1 > nguong", last["adx"] > adx_threshold),
            ("Spread trong ngan sach ATR", 0 <= spread <= last["atr"] * max_spread_atr),
            (
                "Bien do nen khong bat thuong",
                last["high"] - last["low"] <= last["atr"] * max_candle_atr,
            ),
        ]
        if not require_m15:
            checks = checks[1:]
        return [{"label": label, "passed": bool(passed)} for label, passed in checks]
    except (KeyError, TypeError):
        return []
