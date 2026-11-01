"""Reproduce ORB5 MTF research on saved histories without connecting to MT5."""
import hashlib
import json
from pathlib import Path

import pandas as pd

from src.research.scalper_comparison import compare


def main():
    output = Path("reports/orb5_mtf")
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    for source in ("mt5", "histdata"):
        path = Path(f"reports/market_data/{source}/history.csv")
        bars = pd.read_csv(path)
        bars.index = pd.to_datetime(bars.pop("time"), unit="s", utc=True)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        groups = [("2026_09_10", bars)] if source == "mt5" else bars.groupby(bars.index.year)
        for year, frame in groups:
            spreads = frame.spread * .001 if source == "mt5" else pd.Series(.24, index=frame.index)
            for scenario, multiplier in (("fee", 1.), ("stress", 1.5)):
                key = f"{source}_{year}_{scenario}"
                result = compare(frame, spreads * multiplier, strategies=("orb5_mtf",), fee_price=.10)
                trades = result.pop("trades")
                pd.DataFrame(trades).to_csv(output / f"{key}_trades.csv", index=False)
                result["metadata"] = dict(source_sha256=digest, source=str(path), bars=len(frame),
                    start=str(frame.index[0]), end=str(frame.index[-1]), fee_price=.10,
                    spread_multiplier=multiplier, slippage_each_side=.002,
                    max_hold_bars=120, risk_percent=.5, initial_equity=10000,
                    execution="M1 OHLC pending 1 minute, not live 15 seconds; stop first",
                    swap="not modeled", sizing="continuous fixed risk, not Kelly")
                result["metadata"]["code_sha256"] = {
                    name: hashlib.sha256(Path(name).read_bytes()).hexdigest()
                    for name in ("src/strategies/orb_mtf.py", "src/research/scalper_comparison.py",
                                 "src/strategies/entry_support.py", "scripts/backtest_orb_mtf.py")
                }
                (output / f"{key}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
                for segment, stats in result["results"]["orb5_mtf"].items():
                    rows.append(dict(case=key, segment=segment, **stats))
                print(key, result["results"]["orb5_mtf"], flush=True)
    pd.DataFrame(rows).to_csv(output / "summary.csv", index=False)


if __name__ == "__main__":
    main()
