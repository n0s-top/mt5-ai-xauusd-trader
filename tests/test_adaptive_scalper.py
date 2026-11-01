import numpy as np
import pytest

from src.strategies.adaptive_scalper import AdaptiveScalper
from tests.test_scalper_upgrade import setup_signal


def prepared(monkeypatch, direction=1, breakout=False):
    data = setup_signal(direction)
    m1, m5 = data["M1"], data["M5"]
    m5.loc[m5.index[-4], "ema21"] = 2000 - direction
    if breakout:
        m1.loc[m1.index[-2], "close"] = 2000 + direction
        m1.loc[m1.index[-1], ["open", "close", "high", "low", "ema21", "tick_volume"]] = (
            [2001, 2003, 2004, 2000, 2002, 130]
            if direction == 1
            else [1999, 1997, 2000, 1996, 1998, 130]
        )
    bot = AdaptiveScalper()
    monkeypatch.setattr(bot, "indicators", lambda frame: frame)
    return bot, data


@pytest.mark.parametrize("direction", [1, -1])
def test_pullback_preserved_in_valid_trend(monkeypatch, direction):
    bot, data = prepared(monkeypatch, direction)
    signal = bot.predict(*data.values(), spread=0.1)
    assert signal.direction == direction
    assert bot.last_setup == "TREND_PULLBACK"
    assert all(check["passed"] for check in bot.last_checks)


@pytest.mark.parametrize("direction", [1, -1])
def test_breakout_requires_closed_range_and_volume(monkeypatch, direction):
    bot, data = prepared(monkeypatch, direction, breakout=True)
    signal = bot.predict(*data.values(), spread=0.1)
    assert signal.direction == direction
    assert bot.last_setup == "TREND_BREAKOUT"
    assert direction * (data["M1"]["close"].iloc[-1] - signal.stop_loss) > 0
    data["M1"].loc[data["M1"].index[-1], "tick_volume"] = 100
    assert bot.predict(*data.values(), spread=0.1).direction == 0
    assert bot.last_setup == "WAIT"


@pytest.mark.parametrize(
    "failure", ["sideways", "flat_slope", "extension", "no_quote", "spread", "nan"]
)
def test_regime_and_safety_filters(monkeypatch, failure):
    bot, data = prepared(monkeypatch)
    spread = 0.1
    if failure == "sideways":
        data["M5"].loc[data["M5"].index[-1], "adx"] = 15
    elif failure == "flat_slope":
        data["M5"]["ema21"] = 2000
    elif failure == "extension":
        data["M1"].loc[data["M1"].index[-1], "ema21"] = 1998
    elif failure == "no_quote":
        spread = None
    elif failure == "spread":
        spread = 1
    else:
        data["M5"].loc[data["M5"].index[-1], "adx"] = np.nan
    assert bot.predict(*data.values(), spread=spread).direction == 0


def test_data_rejection_is_never_bypassed_by_breakout(monkeypatch):
    bot, data = prepared(monkeypatch, breakout=True)
    data["M15"] = data["M15"].iloc[:-1]
    result = bot.predict(*data.values(), spread=0.1)
    assert result.direction == 0 and result.reason == "Insufficient history"
