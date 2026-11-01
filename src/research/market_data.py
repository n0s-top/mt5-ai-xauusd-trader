"""Validate and normalize independent M1 feeds without inventing spread or bars."""

import hashlib
import json
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd


def read_histdata(archive):
    """HistData ASCII M1: bid OHLC, fixed EST (UTC-5), no observed spread/volume.

    https://www.histdata.com/f-a-q/ explicitly excludes daylight saving changes.
    The zero volume field is kept only for compatibility, not as observed ticks.
    """
    parts = []
    with zipfile.ZipFile(archive) as zipped:
        for entry in zipped.infolist():
            if not entry.filename.lower().endswith(".csv"):
                continue
            if entry.file_size > 150_000_000:
                raise ValueError("HistData member exceeds 150 MB limit")
            with zipped.open(entry) as stream:
                part = pd.read_csv(
                    stream,
                    sep=";",
                    header=None,
                    names=["time", "open", "high", "low", "close", "tick_volume"],
                )
            local = pd.to_datetime(part["time"], format="%Y%m%d %H%M%S", errors="raise")
            utc = local.dt.tz_localize(timezone(timedelta(hours=-5))).dt.tz_convert("UTC")
            part["time"] = utc.dt.as_unit("ns").astype("int64") // 1_000_000_000
            parts.append(part)
    if not parts:
        raise ValueError("HistData archive has no CSV members")
    return pd.concat(parts, ignore_index=True)


def normalize_m1(data, *, asof):
    """Return closed candles plus quality counts. Conflicting duplicates fail."""
    frame = pd.DataFrame(data).copy()
    required = ["time", "open", "high", "low", "close", "tick_volume"]
    if frame.empty or not set(required).issubset(frame.columns):
        raise ValueError("Empty history or missing M1 OHLCV columns")
    for name in required:
        frame[name] = pd.to_numeric(frame[name], errors="raise")
    if not np.isfinite(frame[required].to_numpy(dtype=float)).all():
        raise ValueError("Nonfinite M1 values")
    if (frame["time"] % 60 != 0).any():
        raise ValueError("M1 timestamps must be integer epoch-second minute openings")
    prices = frame[["open", "high", "low", "close"]]
    if (
        (prices <= 0).any().any()
        or (frame["tick_volume"] < 0).any()
        or (frame["high"] < prices.max(axis=1)).any()
        or (frame["low"] > prices.min(axis=1)).any()
    ):
        raise ValueError("Invalid OHLC geometry, prices or volume")
    if "spread" in frame:
        frame["spread"] = pd.to_numeric(frame["spread"], errors="raise")
        if not np.isfinite(frame["spread"]).all() or (frame["spread"] < 0).any():
            raise ValueError("Invalid spread")
    compared = required + (["spread"] if "spread" in frame else [])
    duplicates = int(frame.duplicated("time").sum())
    distinct = frame.drop_duplicates(compared)
    if distinct.duplicated("time").any():
        raise ValueError("Conflicting candles at the same timestamp; do not merge feeds")
    frame = frame.drop_duplicates("time").sort_values("time").reset_index(drop=True)
    cutoff = pd.Timestamp(asof)
    if cutoff.tzinfo is None:
        raise ValueError("asof must be timezone aware")
    closed = frame["time"] + 60 <= cutoff.timestamp()
    excluded = int((~closed).sum())
    frame = frame.loc[closed].copy()
    if frame.empty:
        raise ValueError("No closed M1 candles")
    frame["time"] = frame["time"].astype("int64")
    gaps = frame["time"].diff().dropna()
    quality = {
        "bars": len(frame),
        "start_utc": pd.to_datetime(frame["time"].iloc[0], unit="s", utc=True).isoformat(),
        "end_utc": pd.to_datetime(frame["time"].iloc[-1], unit="s", utc=True).isoformat(),
        "duplicate_rows_removed": duplicates,
        "forming_or_future_rows_excluded": excluded,
        "gaps_over_one_minute": int((gaps > 60).sum()),
        "max_gap_minutes": float(gaps.max() / 60) if len(gaps) else 0.0,
        "gaps_filled": False,
        "gap_note": "Includes market closures; gaps are reported, never padded",
        "spread_available": "spread" in frame,
    }
    return frame, quality


def quarantine_conflicts(data):
    """Remove every candle at ambiguous timestamps; never pick a winning revision."""
    frame = pd.DataFrame(data).copy()
    compared = ["time", "open", "high", "low", "close", "tick_volume"]
    if "spread" in frame:
        compared.append("spread")
    distinct = frame.drop_duplicates(compared)
    ambiguous_times = distinct.loc[distinct.duplicated("time", keep=False), "time"].unique()
    ambiguous = frame["time"].isin(ambiguous_times)
    return frame.loc[~ambiguous].copy(), frame.loc[ambiguous].copy()


def export_source(data, directory, metadata, *, asof=None, conflict_policy="raise"):
    """Write a source-specific CSV and auditable manifest, without account details."""
    now = asof if asof is not None else datetime.now(timezone.utc)
    if conflict_policy not in ("raise", "quarantine"):
        raise ValueError("Unknown candle conflict policy")
    quarantine = pd.DataFrame()
    if conflict_policy == "quarantine":
        data, quarantine = quarantine_conflicts(data)
    frame, quality = normalize_m1(data, asof=now)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    if not quarantine.empty:
        quarantine.to_csv(directory / "quarantine.csv", index=False)
    quality.update(
        conflict_policy=conflict_policy,
        conflicting_rows_quarantined=len(quarantine),
        conflicting_timestamps_quarantined=int(quarantine["time"].nunique())
        if not quarantine.empty
        else 0,
    )
    target = directory / "history.csv"
    temporary = directory / "history.csv.tmp"
    frame.to_csv(temporary, index=False)
    temporary.replace(target)
    result = dict(metadata)
    result.update(
        quality,
        file=str(target),
        sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
        created_at_utc=pd.Timestamp(now).isoformat(),
        timeframe="M1",
        timezone="UTC",
        price_side="BID",
        contains_ticks=False,
        suitable_for_tick_replay=False,
    )
    manifest = directory / "manifest.json"
    manifest.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result
