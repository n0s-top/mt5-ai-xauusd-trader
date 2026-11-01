import pandas as pd
import pytest

from src.strategies.orb_mtf import ORB5MTF, RollingM1M5, ConfirmedM1M5


def frames(date="2026-10-29T13:36Z", direction=1):
    decision = pd.Timestamp(date)
    result = []
    for minutes in (1, 5, 15):
        index = pd.date_range(end=decision.floor(f"{minutes}min") - pd.Timedelta(minutes=minutes),
                              periods=500, freq=f"{minutes}min")
        result.append(pd.DataFrame(dict(open=100., high=101., low=99., close=100.), index=index))
    result[0].iloc[-1] = [100, 103 if direction == 1 else 101,
                          99 if direction == 1 else 97, 102 if direction == 1 else 98]
    return result


@pytest.fixture
def strategy(monkeypatch):
    obj = ORB5MTF()

    def indicators(frame):
        return frame.assign(ema9=101., ema21=99., ema200=99., rsi=55., adx=30., atr=2.)

    monkeypatch.setattr(obj, "indicators", indicators)
    return obj


def test_first_breakout_and_structural_stop(strategy):
    signal = strategy.predict(*frames(), spread=.1)
    assert signal.direction == 1
    assert signal.stop_loss == pytest.approx(98.8)
    assert signal.take_profit > 102


def test_no_session_filter(strategy):
    assert strategy.predict(*frames("2026-11-03T14:36Z"), spread=.1).direction == 1
    assert strategy.predict(*frames("2026-11-03T13:36Z"), spread=.1).direction == 1
    assert strategy.predict(*frames("2026-11-01T09:10Z"), spread=.1).direction == 1


def test_missing_opening_minute(strategy):
    data = frames()
    data[0] = data[0].drop(pd.Timestamp("2026-10-29T13:31Z"))
    assert strategy.predict(*data, spread=.1).direction == 0


def test_previous_breakout_is_not_repeated(strategy):
    data = frames("2026-10-29T13:37Z")
    data[0].loc[pd.Timestamp("2026-10-29T13:35Z"), ["high", "close"]] = [103., 102.]
    assert strategy.predict(*data, spread=.1).direction == 0


def test_opposed_mtf_and_missing_spread(strategy):
    assert strategy.predict(*frames(direction=-1), spread=.1).direction == 0
    assert strategy.predict(*frames(), spread=None).direction == 0


def test_future_m15_blocked(strategy):
    data = frames()
    data[2].index = data[2].index + pd.Timedelta(minutes=15)
    assert strategy.predict(*data, spread=.1).direction == 0


def test_old_breakout_does_not_block_new_range(strategy):
    data = frames("2026-11-01T09:10Z")
    data[0].iloc[-20, data[0].columns.get_loc("high")] = 105.
    data[0].iloc[-20, data[0].columns.get_loc("close")] = 104.
    assert strategy.predict(*data, spread=.1).direction == 1
    assert strategy.strategy_id == "rolling5_mtf_m1_v2"


def test_m1_m5_candidate_does_not_require_m15(strategy):
    candidate = RollingM1M5()
    candidate.indicators = strategy.indicators
    data = frames()
    data[2] = data[2].iloc[:0]
    signal = candidate.predict(*data, spread=.1)
    assert signal.direction == 1
    assert candidate.strategy_id != strategy.strategy_id
    assert not any("M15" in c["label"] for c in candidate.last_checks)


@pytest.mark.parametrize("failure", [None, "adx", "body"])
def test_confirmed_candidate_requires_trend_and_strong_trigger(failure):
    import numpy as np

    candidate = ConfirmedM1M5()

    def indicators(frame):
        return frame.assign(ema9=101., ema21=np.linspace(98., 99., len(frame)),
                            ema200=99., rsi=55., adx=19. if failure == "adx" else 30., atr=2.)

    candidate.indicators = indicators
    data = frames()
    if failure == "body":
        data[0].iloc[-1, data[0].columns.get_loc("open")] = 101.9
    signal = candidate.predict(*data, spread=.1)
    assert (signal.direction == 1) == (failure is None)
    if failure is None:
        assert candidate.last_levels["range_low"] == 99.
        assert signal.stop_loss == pytest.approx(98.8)
