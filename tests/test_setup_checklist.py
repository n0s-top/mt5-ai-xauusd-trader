import pandas as pd

from src.strategies.setup_checklist import setup_checklist


def test_checklist_reproduces_buy_conditions_and_explains_failure():
    m1 = pd.DataFrame(
        [
            {
                "open": 1999,
                "close": 2000,
                "high": 2002,
                "low": 1998,
                "ema21": 2000,
                "rsi": 60,
                "adx": 30,
                "atr": 2,
            },
            {
                "open": 2000,
                "close": 2001,
                "high": 2002,
                "low": 1999,
                "ema21": 2000,
                "rsi": 60,
                "adx": 30,
                "atr": 2,
            },
        ]
    )
    m5 = pd.DataFrame([{"ema9": 2001, "ema21": 2000}] * 2)
    m15 = pd.DataFrame([{"close": 2001, "ema200": 2000}] * 2)
    checks = setup_checklist(m1, m5, m15, 1, 0.1)
    assert len(checks) == 8 and all(item["passed"] for item in checks)
    m1.loc[1, "adx"] = 10
    failed = [item["label"] for item in setup_checklist(m1, m5, m15, 1, 0.1) if not item["passed"]]
    assert failed == ["ADX M1 > nguong"]


def test_missing_or_nonfinite_indicators_do_not_invent_conditions():
    frame = pd.DataFrame([{"close": 1}] * 2)
    assert setup_checklist(frame, frame, frame, 1, 0.1) == []
