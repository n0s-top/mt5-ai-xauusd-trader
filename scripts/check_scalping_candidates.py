"""Compare fixed intraday gold proxies; never place orders."""

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.research.intraday_candidates import METHODS, prepare, run


def main():
    output = Path("reports/scalping_candidates")
    output.mkdir(parents=True, exist_ok=True)
    hashes = {
        p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
        for p in (
            "src/research/intraday_candidates.py",
            "src/research/published_strategies.py",
            "scripts/check_scalping_candidates.py",
        )
    }
    rows, audit = [], []
    for source in ("mt5", "histdata"):
        path = Path("reports/market_data") / source / "history.csv"
        frame = pd.read_csv(path)
        frame.index = pd.to_datetime(frame.pop("time"), unit="s", utc=True)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        groups = [("2026_09_10", frame)] if source == "mt5" else frame.groupby(frame.index.year)
        for period, bars in groups:
            data = prepare(bars)
            spreads = (
                bars.spread.to_numpy() * 0.001 if source == "mt5" else np.full(len(bars), 0.24)
            )
            split = 200 + int((len(bars) - 200) * 0.7)
            for method in METHODS:
                supported = method in ("orb5", "orb15") or data["volume_available"]
                audit.append(
                    {
                        "source": source,
                        "period": period,
                        "method": method,
                        "status": "GOLD_PROXY_ONLY" if supported else "NO_OBSERVED_VOLUME",
                    }
                )
                if not supported:
                    continue
                for scenario, multiplier, fee, carry in (
                    ("base_no_fee", 1, 0, 0),
                    ("fee_carry3pct", 1, 0.10, 0.03),
                    ("spread150_fee_carry8pct", 1.5, 0.10, 0.08),
                ):
                    key = f"{source}_{period}_{method}_{scenario}"
                    folder = output / key
                    folder.mkdir(exist_ok=True)
                    results, all_trades = {}, []
                    for segment, begin, end in (
                        ("development", 200, split),
                        ("holdout", split, len(bars)),
                    ):
                        stats, trades, curve = run(
                            data,
                            method,
                            spreads * multiplier,
                            begin,
                            end,
                            fee_price=fee,
                            annual_carry=carry,
                        )
                        results[segment] = stats
                        for trade in trades:
                            trade["segment"] = segment
                        all_trades.extend(trades)
                        np.savez_compressed(
                            folder / f"equity_{segment}.npz",
                            time=data["time"][begin:end],
                            equity=curve,
                        )
                        rows.append(
                            dict(
                                source=source,
                                period=period,
                                method=method,
                                scenario=scenario,
                                segment=segment,
                                **stats,
                            )
                        )
                    pd.DataFrame(all_trades).to_csv(folder / "trades.csv", index=False)
                    metadata = {
                        "input_sha256": digest,
                        "code_sha256": hashes,
                        "bars": len(bars),
                        "start": bars.index[0].isoformat(),
                        "end": bars.index[-1].isoformat(),
                        "split": bars.index[split].isoformat(),
                        "incomplete_sessions": data["incomplete_sessions"],
                        "spread_median": float(np.median(spreads * multiplier)),
                        "fee_price": fee,
                        "annual_carry": carry,
                        "proxy_only": True,
                    }
                    (folder / "report.json").write_text(
                        json.dumps(
                            {"metadata": metadata, "results": results}, indent=2, allow_nan=False
                        ),
                        encoding="utf-8",
                    )
                    print(f"DONE {key}: {results['holdout']}", flush=True)
    summary = pd.DataFrame(rows)
    summary.to_csv(output / "summary.csv", index=False)
    pd.DataFrame(audit).to_csv(output / "audit.csv", index=False)
    holdout = summary[summary.segment == "holdout"]
    (output / "REPORT.md").write_text(
        "# Gold intraday proxies (not original paper replications)\n\n"
        + holdout.to_csv(index=False),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
