import json

import numpy as np
import pandas as pd
import pytest

from src.research.m1_forecast import (CLASSES, FEATURES, forecast_features, forecast_labels,
                                      forecast_snapshot, predict_probabilities)


def bars():
    close = 2000 + np.arange(3000) * .01 + np.sin(np.arange(3000) / 10)
    return pd.DataFrame(dict(open=close-.1, high=close+.2, low=close-.2, close=close),
                        index=pd.date_range("2025-01-01", periods=3000, freq="min", tz="UTC"))


def model():
    return dict(features=list(FEATURES), classes=list(CLASSES), mean=[0]*len(FEATURES),
                scale=[1]*len(FEATURES), coef=[[0]*len(FEATURES)]*3, intercept=[0]*3,
                temperature=1., horizon_minutes=5, allowed_symbols=["XAUUSD"],
                label_cost_price=.344, validation_status="RESEARCH_ONLY")


def test_features_do_not_change_when_future_prices_change():
    data = bars()
    original = forecast_features(data)
    cutoff = data.index[1800]
    data.loc[data.index > cutoff, ["open", "high", "low", "close"]] *= 2
    changed = forecast_features(data)
    pd.testing.assert_frame_equal(original.loc[:cutoff], changed.loc[:cutoff])
    pd.testing.assert_frame_equal(original.loc[:cutoff], forecast_features(bars().loc[:cutoff]))


def test_labels_exclude_gap_and_last_five_candles():
    data = bars()
    gap = data.index[1502]
    before = data.index[1500]
    data = data.drop(gap)
    features = forecast_features(data)
    labels = forecast_labels(data, features)
    assert before not in labels.index
    assert not labels.index.isin(data.index[-5:]).any()


def test_json_forecast_is_normalized_and_rejects_other_symbol(tmp_path):
    path = tmp_path / "model.json"
    path.write_text(json.dumps(model()), encoding="utf-8")
    forecast = forecast_snapshot(path, bars(), "XAUUSD")
    assert sum(forecast["probabilities"].values()) == pytest.approx(1)
    assert forecast["horizon_minutes"] == 5
    with pytest.raises(ValueError, match="symbol"):
        forecast_snapshot(path, bars(), "BTCUSD")


def test_invalid_model_scale_and_invalid_prices_are_rejected():
    features = forecast_features(bars()).iloc[-1:]
    artifact = model()
    artifact["scale"][0] = 0
    with pytest.raises(ValueError, match="parameters"):
        predict_probabilities(artifact, features)
    data = bars()
    data.iloc[-1, data.columns.get_loc("high")] = 1
    with pytest.raises(ValueError, match="geometry"):
        forecast_features(data)
