"""Independently reconcile saved trade ledgers, equity and input/code hashes."""

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


def main():
    root = Path("reports/scalping_candidates")
    checked = 0
    for path in root.glob("*/report.json"):
        report = json.loads(path.read_text(encoding="utf-8"))
        for filename, expected in report["metadata"]["code_sha256"].items():
            assert hashlib.sha256(Path(filename).read_bytes()).hexdigest() == expected, filename
        source = path.parent.name.split("_")[0]
        source_path = Path("reports/market_data") / source / "history.csv"
        assert (
            hashlib.sha256(source_path.read_bytes()).hexdigest()
            == report["metadata"]["input_sha256"]
        )
        trades = pd.read_csv(path.parent / "trades.csv")
        for segment, stats in report["results"].items():
            ledger = trades[trades.segment == segment] if len(trades) else trades
            curve = np.load(path.parent / f"equity_{segment}.npz")["equity"]
            assert len(ledger) == stats["trades"]
            assert np.isclose(10000 + ledger.net_pnl.sum(), stats["ending_equity"])
            assert np.isclose(curve[-1], stats["ending_equity"])
            values = np.r_[10000, curve]
            assert np.isclose(
                100 * np.max(1 - values / np.maximum.accumulate(values)),
                stats["drawdown_m1_close_percent"],
            )
            assert np.isclose(ledger.commission.sum(), stats["commission_cost"])
            assert np.isclose(ledger.carry_cost.sum(), stats["carry_cost"])
            capital = 10000 + ledger.net_pnl.cumsum().shift(fill_value=0)
            assert (ledger.initial_risk <= capital * 0.005 + 1e-7).all()
            assert (ledger.ounces * ledger.entry <= capital * 2 + 1e-7).all()
            checked += 1
    assert checked == 72, checked
    print(f"PASS: {checked} segment ledgers, equity curves, risk/notional caps and hashes")


if __name__ == "__main__":
    main()
