"""Compare existing M1 alternatives on matching saved data; never submit orders."""

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from src.research.scalper_comparison import compare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", nargs="+", type=int, default=[2026])
    parser.add_argument("--strategies", nargs="+", default=["orb5_mtf", "pullback", "m5_m1", "m5_m1_quality"])
    parser.add_argument("--output", type=Path, default=Path("reports/scalper_alternatives"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    strategies = tuple(args.strategies)
    rows = []
    code = {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in (
        "src/strategies/xauusd_m1_scalper.py", "src/strategies/m5_m1_pullback.py",
        "src/strategies/orb_mtf.py", "src/strategies/entry_support.py",
        "src/strategies/session_engulfing.py",
        "src/research/scalper_comparison.py", "scripts/backtest_scalper_alternatives.py")}
    for source in ("mt5", "histdata"):
        path = Path(f"reports/market_data/{source}/history.csv")
        bars = pd.read_csv(path)
        bars.index = pd.to_datetime(bars.pop("time"), unit="s", utc=True)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        groups = [("2026_09_10", bars)] if source == "mt5" else (
            (year, frame) for year, frame in bars.groupby(bars.index.year) if year in args.years
        )
        for period, frame in groups:
            spreads = frame.spread * .001 if source == "mt5" else pd.Series(.24, index=frame.index)
            for scenario, multiplier in (("fee", 1.), ("stress", 1.5)):
                key = f"{source}_{period}_{scenario}"
                print(f"Starting {key}: {len(frame)} bars", flush=True)
                result = compare(frame, spreads * multiplier, strategies=strategies, fee_price=.10,
                    progress=lambda name, segment, i, n: print(
                        f"{key} {name} {segment}: {i}/{n}", flush=True) if i % 10000 < 50 else None)
                trades = result.pop("trades")
                pd.DataFrame(trades).to_csv(args.output / f"{key}_trades.csv", index=False)
                result["metadata"] = dict(source=str(path), source_sha256=digest,
                    code_sha256=code, bars=len(frame), start=str(frame.index[0]), end=str(frame.index[-1]),
                    fee_price=.10, spread_multiplier=multiplier, slippage_each_side=.002,
                    risk_percent=.5, initial_equity=10000, max_hold_bars=120,
                    execution="M1 OHLC, one-minute pending; SL first on ambiguous paths",
                    sizing="continuous fixed risk, not Kelly; no broker lot/margin simulation",
                    swap="not modeled")
                (args.output / f"{key}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
                for strategy, segments in result["results"].items():
                    for segment, stats in segments.items():
                        rows.append(dict(case=key, strategy=strategy, segment=segment, **stats))
                        print(key, strategy, segment, stats["trades"], stats["return_percent"], flush=True)
                pd.DataFrame(rows).to_csv(args.output / "summary.csv", index=False)


if __name__ == "__main__":
    main()
