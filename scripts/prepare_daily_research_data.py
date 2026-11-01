"""Build daily gold research feeds; keep independent providers separate."""

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from scripts.download_market_data import histdata_archive
from src.research.market_data import normalize_m1, quarantine_conflicts, read_histdata


def daily_from_minutes(frame):
    data = frame.copy()
    data.index = pd.to_datetime(data.pop("time"), unit="s", utc=True)
    # Fixed 22:00 UTC session; not claimed to be COMEX settlement or broker D1.
    session = (data.index + pd.Timedelta(hours=2)).floor("D")
    daily = data.groupby(session).agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        minute_rows=("close", "count"),
    )
    daily.index.name = "time"
    return daily


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("reports/published_strategies/data"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = {"sources": [], "errors": []}
    import MetaTrader5 as mt5

    if mt5.initialize(timeout=10000):
        try:
            rates = mt5.copy_rates_from_pos("XAUUSD", mt5.TIMEFRAME_D1, 1, 10000)
            if rates is None or not len(rates):
                raise ValueError("MT5 D1 unavailable")
            frame = pd.DataFrame(rates)
            frame["time"] = pd.to_datetime(frame["time"], unit="s", utc=True)
            native_rows = len(frame)
            frame["time"] = frame["time"] + pd.to_timedelta(
                (frame["time"].dt.day_of_week == 6).astype(int), unit="D"
            )
            frame = frame.groupby("time", sort=True, as_index=False).agg(
                {
                    "open": "first",
                    "high": "max",
                    "low": "min",
                    "close": "last",
                    "tick_volume": "sum",
                }
            )
            path = args.output / "mt5_daily.csv"
            frame.to_csv(path, index=False)
            manifest["sources"].append(
                {
                    "source": "MT5",
                    "bars": len(frame),
                    "native_rows": native_rows,
                    "file": str(path),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "session": "Native D1; Sunday stub merged into following Monday to avoid 6-day ATR week",
                }
            )
            print(f"MT5: {len(frame)} D1 bars", flush=True)
        finally:
            mt5.shutdown()
    else:
        manifest["errors"].append({"source": "MT5", "reason": "Terminal unavailable"})
    parts, archives = [], []
    for year in range(2016, 2024):
        try:
            archive, meta = histdata_archive(str(year), Path("reports/market_data/histdata/raw"))
            clean, rejected = quarantine_conflicts(read_histdata(archive))
            clean, quality = normalize_m1(clean, asof=pd.Timestamp.now(tz="UTC"))
            parts.append(daily_from_minutes(clean))
            meta.update(quality, conflicting_rows_quarantined=len(rejected))
            archives.append(meta)
            if len(rejected):
                rejected.to_csv(args.output / f"quarantine_{year}.csv", index=False)
            print(f"HistData {year}: {len(clean)} M1 -> {len(parts[-1])} D1 bars", flush=True)
        except (ValueError, OSError) as exc:
            manifest["errors"].append({"source": "HistData", "year": year, "reason": str(exc)})
    recent = pd.read_csv("reports/market_data/histdata/history.csv")
    parts.append(daily_from_minutes(recent))
    # Annual files can straddle a UTC session boundary. Aggregate these fragments,
    # preserving first open/last close rather than retaining duplicate daily rows.
    combined = pd.concat(parts).sort_index(kind="stable")
    daily = combined.groupby(level=0).agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "minute_rows": "sum"}
    )
    path = args.output / "histdata_daily.csv"
    daily.to_csv(path)
    manifest["sources"].append(
        {
            "source": "HistData",
            "bars": len(daily),
            "file": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "session": "22:00 UTC fixed daily boundary; no synthetic missing minutes",
            "archives": archives,
            "recent_m1_sha256": hashlib.sha256(
                Path("reports/market_data/histdata/history.csv").read_bytes()
            ).hexdigest(),
            "sessions_under_1000_minutes": int((daily.minute_rows < 1000).sum()),
        }
    )
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Saved daily feeds: {args.output} | errors: {len(manifest['errors'])}", flush=True)
    if manifest["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
