"""Train on older data, calibrate chronologically, evaluate five-minute forecasts."""

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss
from sklearn.preprocessing import StandardScaler

from src.research.m1_forecast import CLASSES, FEATURES, forecast_features, forecast_labels, predict_probabilities


def scores(y, probabilities, prior):
    target = np.eye(3)[y]
    reference = np.tile(prior, (len(y), 1))
    return dict(samples=len(y), accuracy=float(accuracy_score(y, probabilities.argmax(axis=1))),
        baseline_accuracy=float(accuracy_score(y, reference.argmax(axis=1))),
        log_loss=float(log_loss(y, probabilities, labels=[0, 1, 2])),
        baseline_log_loss=float(log_loss(y, reference, labels=[0, 1, 2])),
        multiclass_brier=float(np.mean(np.sum((probabilities - target) ** 2, axis=1))),
        baseline_brier=float(np.mean(np.sum((reference - target) ** 2, axis=1))))


def main():
    output = Path("reports/m1_forecast")
    output.mkdir(parents=True, exist_ok=True)
    path = Path("reports/market_data/histdata/history.csv")
    bars = pd.read_csv(path)
    bars.index = pd.to_datetime(bars.pop("time"), unit="s", utc=True)
    features = forecast_features(bars)
    labels = forecast_labels(bars, features)
    # Evaluate nonoverlapping five-minute targets on a fixed clock grid.
    index = labels.index[(labels.index.minute + 1) % 5 == 0]
    x, y = features.loc[index, FEATURES], labels.loc[index]
    train_end, test_start = pd.Timestamp("2025-09-01", tz="UTC"), pd.Timestamp("2026-01-01", tz="UTC")
    label_end = index + pd.Timedelta(minutes=6)
    train = label_end < train_end
    calibration = (index >= train_end) & (label_end < test_start)
    test = index >= test_start
    scaler = StandardScaler().fit(x.loc[train])
    estimator = LogisticRegression(C=1., max_iter=300).fit(scaler.transform(x.loc[train]), y.loc[train])
    assert list(estimator.classes_) == [0, 1, 2]
    model = dict(features=list(FEATURES), classes=list(CLASSES), mean=scaler.mean_.tolist(),
        scale=scaler.scale_.tolist(), coef=estimator.coef_.tolist(), intercept=estimator.intercept_.tolist(),
        temperature=1., horizon_minutes=5, label_cost_price=.344,
        allowed_symbols=["XAUUSD", "XAUUSDc"], validation_status="RESEARCH_ONLY",
        training_last_label_utc=str(label_end[train][-1]), calibration_start_utc=str(index[calibration][0]),
        calibration_last_label_utc=str(label_end[calibration][-1]), test_start_utc=str(index[test][0]))
    losses = {}
    for value in (.5, 1., 1.5, 2.):
        model["temperature"] = value
        losses[value] = float(log_loss(y.loc[calibration], predict_probabilities(model, x.loc[calibration]), labels=[0, 1, 2]))
    model["temperature"] = min(losses, key=losses.get)
    prior = np.bincount(y.loc[train], minlength=3) / train.sum()
    result = dict(training_samples=int(train.sum()), calibration_samples=int(calibration.sum()),
        selected_temperature=model["temperature"], calibration_losses=losses,
        histdata_2026=scores(y.loc[test].to_numpy(), predict_probabilities(model, x.loc[test]), prior),
        input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        code_sha256={p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in (
            "src/research/m1_forecast.py", "scripts/train_m1_forecast.py")})
    other = pd.read_csv("reports/market_data/mt5/history.csv")
    other.index = pd.to_datetime(other.pop("time"), unit="s", utc=True)
    other_features = forecast_features(other)
    other_labels = forecast_labels(other, other_features)
    other_index = other_labels.index[(other_labels.index.minute + 1) % 5 == 0]
    result["mt5_2026"] = scores(other_labels.loc[other_index].to_numpy(),
                               predict_probabilities(model, other_features.loc[other_index]), prior)
    result["mt5_input_sha256"] = hashlib.sha256(Path("reports/market_data/mt5/history.csv").read_bytes()).hexdigest()
    def momentum_accuracy(frame, labels, index):
        movement = frame.loc[index, "return5"] * frame.loc[index, "atr"]
        limit = np.maximum(.25 * frame.loc[index, "atr"], .344)
        prediction = np.where(movement > limit, 2, np.where(movement < -limit, 0, 1))
        return float(accuracy_score(labels.loc[index], prediction))
    result["histdata_2026"]["momentum_accuracy"] = momentum_accuracy(features, labels, index[test])
    result["mt5_2026"]["momentum_accuracy"] = momentum_accuracy(other_features, other_labels, other_index)
    model["validation_status"] = "RESEARCH_ONLY_NO_VERIFIED_TRADING_EDGE"
    for name, data in (("model.json", model), ("evaluation.json", result)):
        (output / name).write_text(json.dumps(data, indent=2, allow_nan=False), encoding="utf-8")
    probabilities = predict_probabilities(model, x.loc[test])
    prediction = pd.DataFrame(probabilities, columns=CLASSES, index=x.loc[test].index)
    prediction["actual_class"] = y.loc[test]
    prediction.to_csv(output / "predictions_2026.csv", index_label="candle_open_utc")
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
