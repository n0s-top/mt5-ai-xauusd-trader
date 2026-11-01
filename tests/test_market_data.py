import json
import sys
import zipfile

import pandas as pd
import pytest

from scripts.download_market_data import DownloadForm, histdata_archive
from src.research.market_data import export_source, normalize_m1, read_histdata


def sample():
    return pd.DataFrame(
        {
            "time": [1735689600, 1735689660, 1735689720],
            "open": [2600.0] * 3,
            "high": [2602.0] * 3,
            "low": [2599.0] * 3,
            "close": [2601.0] * 3,
            "tick_volume": [0] * 3,
        }
    )


def test_histdata_fixed_est_in_summer_and_winter(tmp_path):
    path = tmp_path / "history.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "data.csv",
            "20250101 180000;2600;2602;2599;2601;0\n20250701 180000;3300;3302;3299;3301;0\n",
        )
        archive.writestr("status.txt", "Do not parse as price data")
    data = read_histdata(path)
    times = pd.to_datetime(data["time"], unit="s", utc=True)
    assert times.tolist() == [
        pd.Timestamp("2025-01-01T23:00:00Z"),
        pd.Timestamp("2025-07-01T23:00:00Z"),
    ]
    assert "spread" not in data


def test_normalization_deduplicates_sorts_preserves_gaps_and_excludes_forming():
    data = sample()
    data.loc[2, "time"] += 120
    data = pd.concat([data.iloc[::-1], data.iloc[[0]]], ignore_index=True)
    frame, quality = normalize_m1(data, asof=pd.Timestamp("2025-01-01T00:04:30Z"))
    assert frame["time"].tolist() == [1735689600, 1735689660]
    assert quality["duplicate_rows_removed"] == 1
    assert quality["forming_or_future_rows_excluded"] == 1
    frame, quality = normalize_m1(data, asof=pd.Timestamp("2025-01-02T00:00:00Z"))
    assert quality["gaps_over_one_minute"] == 1
    assert quality["max_gap_minutes"] == 3
    assert not quality["gaps_filled"]
    assert len(frame) == 3


@pytest.mark.parametrize(
    "column,value",
    [("time", 1735689601), ("high", 2500), ("close", float("nan")), ("tick_volume", -1)],
)
def test_rejects_bad_market_data(column, value):
    data = sample()
    data.loc[0, column] = value
    with pytest.raises(ValueError):
        normalize_m1(data, asof=pd.Timestamp("2025-01-02T00:00:00Z"))


def test_rejects_conflicting_source_candles_and_spread():
    data = sample()
    conflicting = data.iloc[[0]].copy()
    conflicting["close"] = 2600.5
    with pytest.raises(ValueError, match="Conflicting"):
        normalize_m1(pd.concat([data, conflicting]), asof=pd.Timestamp("2025-01-02T00:00Z"))
    data["spread"] = -1
    with pytest.raises(ValueError, match="spread"):
        normalize_m1(data, asof=pd.Timestamp("2025-01-02T00:00Z"))


def test_export_manifest_describes_real_capabilities(tmp_path):
    result = export_source(
        sample(), tmp_path, {"source": "test"}, asof=pd.Timestamp("2025-01-02T00:00Z")
    )
    assert result["bars"] == 3
    assert len(result["sha256"]) == 64
    assert not result["spread_available"]
    assert not result["suitable_for_tick_replay"]
    assert json.loads((tmp_path / "manifest.json").read_text())["sha256"] == result["sha256"]
    assert not (tmp_path / "history.csv.tmp").exists()


def test_quarantine_removes_all_revisions_of_ambiguous_minutes(tmp_path):
    data = sample()
    revision = data.iloc[[0]].copy()
    revision["close"] = 2600.5
    data = pd.concat([data, revision, data.iloc[[1]]], ignore_index=True)
    result = export_source(
        data,
        tmp_path,
        {"source": "test"},
        asof=pd.Timestamp("2025-01-02T00:00Z"),
        conflict_policy="quarantine",
    )
    assert result["conflicting_rows_quarantined"] == 2
    assert result["conflicting_timestamps_quarantined"] == 1
    assert result["duplicate_rows_removed"] == 1
    cleaned = pd.read_csv(tmp_path / "history.csv")
    assert cleaned["time"].tolist() == [1735689660, 1735689720]
    quarantined = pd.read_csv(tmp_path / "quarantine.csv")
    assert quarantined["time"].tolist() == [1735689600, 1735689600]


def test_download_form_ignores_other_forms():
    parser = DownloadForm()
    parser.feed(
        '<form id="file_down"><input type="hidden" name="fxpair" value="XAUUSD">'
        '</form><form id="other"><input type="hidden" name="fxpair" value="EURUSD"></form>'
    )
    assert parser.fields == {"fxpair": "XAUUSD"}


@pytest.mark.parametrize("period", ["202613", "../2025", "2025/10"])
def test_rejects_bad_period_before_network(period, tmp_path):
    with pytest.raises(ValueError, match="YYYY"):
        histdata_archive(period, tmp_path)


def test_cached_download_cli_exports_auditable_catalog(monkeypatch, tmp_path):
    from scripts.download_market_data import main

    destination = tmp_path / "histdata" / "raw"
    destination.mkdir(parents=True)
    with zipfile.ZipFile(destination / "XAUUSD_M1_202501.zip", "w") as archive:
        archive.writestr("data.csv", "20250101 180000;2600;2602;2599;2601;0\n")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "download_market_data",
            "--sources",
            "histdata",
            "--histdata-periods",
            "202501",
            "--output",
            str(tmp_path),
        ],
    )
    main()
    catalog = json.loads((tmp_path / "catalog.json").read_text())
    assert catalog["errors"] == []
    assert catalog["sources"][0]["bars"] == 1
    assert catalog["sources"][0]["archives"][0]["cache_used"]
    assert (tmp_path / "REPORT.md").exists()


def test_validation_errors_are_recorded_in_catalog(monkeypatch, tmp_path):
    from scripts.download_market_data import main

    destination = tmp_path / "histdata" / "raw"
    destination.mkdir(parents=True)
    with zipfile.ZipFile(destination / "XAUUSD_M1_202501.zip", "w") as archive:
        archive.writestr("data.csv", "20250101 180000;2600;2500;2599;2601;0\n")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "download_market_data",
            "--sources",
            "histdata",
            "--histdata-periods",
            "202501",
            "--output",
            str(tmp_path),
        ],
    )
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    catalog = json.loads((tmp_path / "catalog.json").read_text())
    assert catalog["sources"] == []
    assert catalog["errors"][0]["stage"] == "validation"
