"""Download independent XAUUSD M1 samples from MT5 and HistData. Never trade."""

import argparse
import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

import pandas as pd

from src.research.market_data import export_source, read_histdata


class DownloadForm(HTMLParser):
    def __init__(self):
        super().__init__()
        self.active = False
        self.fields = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form":
            self.active = attrs.get("id") == "file_down"
        if self.active and tag == "input" and attrs.get("type") == "hidden":
            self.fields[attrs["name"]] = attrs.get("value", "")

    def handle_endtag(self, tag):
        if tag == "form":
            self.active = False


def histdata_archive(period, destination):
    if not re.fullmatch(r"20\d{2}(?:0[1-9]|1[0-2])?", period):
        raise ValueError("HistData periods must be YYYY or YYYYMM")
    suffix = f"{period[:4]}/{int(period[4:])}" if len(period) == 6 else period
    url = (
        "https://www.histdata.com/download-free-forex-historical-data/"
        f"?/ascii/1-minute-bar-quotes/XAUUSD/{suffix}"
    )
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / f"XAUUSD_M1_{period}.zip"
    cached = target.exists()
    if not cached:
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
        with opener.open(url, timeout=30) as response:
            form = DownloadForm()
            form.feed(response.read(2_000_000).decode("utf-8"))
        fields = form.fields
        if (
            not fields.get("tk")
            or fields.get("fxpair") != "XAUUSD"
            or fields.get("platform") != "ASCII"
            or fields.get("timeframe") != "M1"
            or fields.get("date") != period[:4]
            or fields.get("datemonth") != period
        ):
            raise ValueError(f"No matching HistData M1 download form for {period}")
        request = urllib.request.Request(
            "https://www.histdata.com/get.php",
            data=urllib.parse.urlencode(fields).encode("ascii"),
            headers={"Referer": url},
        )
        with opener.open(request, timeout=60) as response:
            payload = response.read(40_000_001)
        if len(payload) > 40_000_000 or not payload.startswith(b"PK"):
            raise ValueError("Download is not a ZIP archive or exceeds 40 MB")
        temporary = target.with_suffix(".zip.tmp")
        temporary.write_bytes(payload)
        try:
            with zipfile.ZipFile(temporary) as archive:
                if not any(item.filename.lower().endswith(".csv") for item in archive.infolist()):
                    raise ValueError("Downloaded ZIP has no CSV")
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    return target, {
        "period": period,
        "url": url,
        "archive": str(target),
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "cache_used": cached,
    }


def download_mt5(symbol, count, output):
    import MetaTrader5 as mt5

    if not mt5.initialize(timeout=10000):
        raise ValueError("Cannot connect to MT5; open the logged-in terminal")
    try:
        if not mt5.symbol_select(symbol, True):
            raise ValueError(f"MT5 symbol unavailable: {symbol}")
        info = mt5.symbol_info(symbol)
        bars = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 1, count)
        if info is None or bars is None or not len(bars):
            raise ValueError(f"MT5 history unavailable (code {mt5.last_error()[0]})")
        return export_source(
            bars,
            output / "mt5",
            {
                "source": "MT5 connected broker",
                "symbol": symbol,
                "requested_bars": count,
                "point": info.point,
                "tick_size": info.trade_tick_size,
                "spread_kind": "Broker historical bar spread in points; not a tick path",
                "volume_kind": "Broker tick volume",
            },
        )
    finally:
        mt5.shutdown()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sources", nargs="+", choices=("mt5", "histdata"), default=["mt5", "histdata"]
    )
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--mt5-bars", type=int, default=50000)
    parser.add_argument(
        "--histdata-periods", nargs="+", default=["2024", "2025", "202609", "202610"]
    )
    parser.add_argument("--output", type=Path, default=Path("reports/market_data"))
    args = parser.parse_args()
    if args.mt5_bars < 1 or len(set(args.sources)) != len(args.sources):
        parser.error("Require positive bar count and unique sources")
    for period in args.histdata_periods:
        if not re.fullmatch(r"20\d{2}(?:0[1-9]|1[0-2])?", period):
            parser.error("HistData periods must be YYYY or YYYYMM")
    args.output.mkdir(parents=True, exist_ok=True)
    report = {"created_at_utc": datetime.now(timezone.utc).isoformat(), "sources": [], "errors": []}
    if "mt5" in args.sources:
        try:
            report["sources"].append(download_mt5(args.symbol, args.mt5_bars, args.output))
            print(f"MT5: {report['sources'][-1]['bars']} closed M1 bars", flush=True)
        except (ValueError, OSError) as exc:
            report["errors"].append({"source": "mt5", "reason": str(exc)})
    if "histdata" in args.sources:
        parts, archives = [], []
        for period in dict.fromkeys(args.histdata_periods):
            try:
                target, metadata = histdata_archive(period, args.output / "histdata" / "raw")
                data = read_histdata(target)
                # Reject wrong-period downloads, even if the server returns a valid ZIP.
                local = pd.to_datetime(data["time"], unit="s", utc=True) - pd.Timedelta(hours=5)
                fmt = "%Y%m" if len(period) == 6 else "%Y"
                if not (local.dt.strftime(fmt) == period).all():
                    raise ValueError("Archive timestamps do not match requested period")
                parts.append(data)
                archives.append(metadata)
                print(f"HistData {period}: {len(data)} M1 bars", flush=True)
            except (ValueError, OSError, urllib.error.URLError, zipfile.BadZipFile) as exc:
                report["errors"].append(
                    {"source": "histdata", "period": period, "reason": str(exc)}
                )
                print(f"HistData {period}: unavailable ({type(exc).__name__})", flush=True)
            time.sleep(0.5)
        if parts:
            try:
                report["sources"].append(
                    export_source(
                        pd.concat(parts, ignore_index=True),
                        args.output / "histdata",
                        {
                            "source": "HistData",
                            "symbol": "XAUUSD",
                            "input_timezone": "Fixed EST / UTC-5, no DST",
                            "spread_kind": "Unavailable: supply explicit assumed spread for OHLC research",
                            "volume_kind": "Placeholder field, not observed tick volume",
                            "point": None,
                            "tick_size": None,
                            "archives": archives,
                        },
                        conflict_policy="quarantine",
                    )
                )
            except (ValueError, OSError) as exc:
                report["errors"].append(
                    {"source": "histdata", "stage": "validation", "reason": str(exc)}
                )
    report["note"] = (
        "Keep feeds separate. Overlapping times across providers are not independent market samples. "
        "HistData M1 lacks observed spread; neither CSV supplies tick paths. "
        "Use explicit costs for OHLC research; do not infer live profitability or Kelly edge."
    )
    target = args.output / "catalog.json"
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = [
        "# XAUUSD M1 data catalog",
        "",
        f"Created: {report['created_at_utc']}",
        "",
        "| Source | Clean bars | Start UTC | End UTC | Conflicting minutes quarantined |",
        "| --- | ---: | --- | --- | ---: |",
    ]
    for source in report["sources"]:
        lines.append(
            f"| {source['source']} | {source['bars']:,} | {source['start_utc']} | "
            f"{source['end_utc']} | {source['conflicting_timestamps_quarantined']:,} |"
        )
    lines.extend(
        [
            "",
            report["note"],
            "",
            "Identical duplicates are removed. Every conflicting timestamp is excluded, with all "
            "revisions preserved in histdata/quarantine.csv. Missing minutes are never filled.",
            "",
            "HistData input time: fixed EST (UTC-5), including summer, per provider documentation. "
            "MT5 input time: epoch seconds as supplied by its API. Normalized CSVs use UTC.",
            "",
            "Per-source manifest.json includes SHA256, archive provenance, gap counts and spread capability.",
            "",
            "Sources: [HistData FAQ](https://www.histdata.com/f-a-q/), "
            "[MT5 documentation](https://www.mql5.com/en/docs/python_metatrader5/mt5copyratesrange_py).",
            "",
        ]
    )
    if report["errors"]:
        lines.extend(
            ["## Download errors", "", "```json", json.dumps(report["errors"], indent=2), "```", ""]
        )
    (args.output / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    print(
        f"Catalog: {target} | sources: {len(report['sources'])} | errors: {len(report['errors'])}"
    )
    if report["errors"] or len(report["sources"]) < len(args.sources):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
