"""Audit published candidates and run reproducible single-gold adaptations."""

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from src.research.published_strategies import METHODS, evaluate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("reports/published_strategies/data"))
    parser.add_argument("--output", type=Path, default=Path("reports/published_strategies"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    code = Path("src/research/published_strategies.py")
    code_hash = hashlib.sha256(code.read_bytes()).hexdigest()
    scenarios = (
        ("execution_only", 0.24, 0.0),
        ("carry3pct", 0.24, 0.03),
        ("spread036_carry8pct", 0.36, 0.08),
    )
    rows, years, completed = [], [], []
    for source in ("histdata", "mt5"):
        path = args.data / f"{source}_daily.csv"
        frame = pd.read_csv(path)
        frame["time"] = pd.to_datetime(frame["time"], utc=True)
        frame = frame.set_index("time")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        for phase, start in (
            ("full_2018", "2018-01-01T00:00:00Z"),
            ("recent_2024", "2024-01-01T00:00:00Z"),
        ):
            for scenario, spread, carry in scenarios:
                for method in METHODS:
                    result, curve, orders = evaluate(
                        frame, method, start=start, spread=spread, fee=0.10, carry=carry
                    )
                    key = f"{source}_{phase}_{scenario}_{method}"
                    folder = args.output / key
                    folder.mkdir(parents=True, exist_ok=True)
                    curve.to_csv(folder / "equity.csv", index_label="time")
                    orders.to_csv(folder / "orders.csv", index=False)
                    metadata = {
                        "source": source,
                        "phase": phase,
                        "method": method,
                        "scenario": scenario,
                        "input_sha256": digest,
                        "code_sha256": code_hash,
                        "spread_price": spread,
                        "round_trip_fee_price": 0.10,
                        "slippage_per_side_price": 0.002,
                        "annual_carry_charged_on_absolute_notional": carry,
                        "replication_status": "SINGLE_GOLD_ADAPTATION_NOT_ORIGINAL_PAPER_OR_PORTFOLIO",
                    }
                    result["metadata"] = metadata
                    (folder / "report.json").write_text(
                        json.dumps(result, indent=2, allow_nan=False), encoding="utf-8"
                    )
                    rows.append(dict(metadata, **result["summary"]))
                    for year in result["yearly"]:
                        years.append(dict(metadata, **year))
                    completed.append(key)
                print(f"DONE {source} {phase} {scenario}: {len(METHODS)} methods", flush=True)
    pd.DataFrame(rows).to_csv(args.output / "summary.csv", index=False)
    pd.DataFrame(years).to_csv(args.output / "yearly.csv", index=False)
    audit = {
        "time_series_momentum": {
            "status": "ADAPTATION_TESTED",
            "deviations": [
                "Single spot/CFD gold, not a diversified futures portfolio",
                "Spot returns instead of futures excess/roll returns",
                "40% per-instrument vol target capped at 2x; not paper-exact sizing",
                "Monthly 12-month or weekly averaged 1/3/12-month directions; next-open fills",
                "Overnight financing explicitly stress tested",
            ],
        },
        "aqr_diversified_trend": {
            "status": "ORIGINAL_PORTFOLIO_NOT_REPRODUCIBLE_FROM_GOLD_ONLY",
            "tested_proxy": "trend_1_3_12_weekly_vol40_cap2",
            "missing": [
                "Other markets and their rolled futures returns",
                "Original historical cost model and portfolio risk scaling",
            ],
        },
        "turtles": {
            "status": "SINGLE_GOLD_ADAPTATIONS_TESTED",
            "deviations": [
                "Risk reduced to 0.5% equity per unit at initial 2N stop",
                "Maximum 2x notional at entry/add; no original multi-market correlation limits",
                "0 or 3 pyramids, N=Wilder20, prior-day channels, 20/10 or 55/20",
                "S1 virtual last-completed-trade filter and 55-day failsafe; filter known at previous close",
                "No same-day re-entry after exit; adverse entry/stop and add/stop ordering",
                "No original portfolio drawdown-based notional reduction",
            ],
        },
        "forecast_to_fill": {
            "status": "NOT_REPRODUCIBLE_AS_PUBLISHED_NO_INVENTED_BACKTEST",
            "source": "https://arxiv.org/html/2511.08571v1",
            "findings": [
                "EMA decay and fold-by-fold fitted parameters, theta, code and decision logs not supplied in the inspected article",
                "De-risking is described as halving or closing, without a unique reproducible selection rule",
                "Abstract states 43% CAGR; section 10 describes about 43% as scaling to 15% target from 0.91% realized volatility",
                "Method clarifications call T+1 baseline; latency table labels Sharpe 2.88 as T+0 and 2.28 as T+1",
                "Data through September 16 2025 are described as extended to October 31 2025 with carried-forward prices",
                "Overlapping six-month test windows advance monthly; full non-overlapping companion outputs not linked in inspected text",
                "The authors explicitly say continuous live validation has not yet been implemented",
            ],
        },
        "completed_cases": len(completed),
        "verdict": "HISTORICAL_GOLD_ADAPTATIONS_ONLY_NOT_PROOF_OF_FUTURE_OR_M1_PROFITABILITY",
    }
    (args.output / "audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    lines = [
        "# Published gold strategies: independent checks",
        "",
        "These are fixed-rule single-gold adaptations, not replication of multi-market futures studies. No live defaults or orders were changed.",
        "",
        "## Recent window, financing 3%/year (hypothetical)",
        "",
        "| Source | Method | CAGR | Daily-close max DD | Sharpe | Orders |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        if row["phase"] == "recent_2024" and row["scenario"] == "carry3pct":
            sharpe = (
                f"{row['sharpe_zero_cash_rate']:.2f}"
                if row["sharpe_zero_cash_rate"] is not None
                else "N/A"
            )
            lines.append(
                f"| {row['source']} | {row['method']} | {row['cagr_percent']:.2f}% | {row['daily_close_drawdown_percent']:.2f}% | {sharpe} | {row['orders']} |"
            )
    lines.extend(
        [
            "",
            "## Scope and execution assumptions",
            "",
            "- Data feeds stay separate. 2018+ and 2024+ are overlapping evaluations, never additive independent samples. 2026 is partial. Parameters were not fitted to these returns.",
            "- Both feeds use daily OHLC, with provider-specific session boundaries. MT5 Sunday stubs are combined with Monday; HistData sessions close at fixed 22:00 UTC. Missing observations are not filled.",
            "- Prior-close signals and channels only. TSMOM uses monthly/weekly next-open execution; quantities stay fixed between rebalances. Fractional ounces and USD equity; no broker lot rounding, margin calls or tax model.",
            "- Costs per ounce: half-spread each side, 0.002 slippage each side, half of 0.10 round-trip fee each side. Notional financing 0%, 3%, 8% annually charged to both longs and shorts, including calendar gaps. These are explicit assumptions, not verified broker swaps; execution-only excludes financing.",
            "- TSMOM EWMA volatility alpha=0.02 with 60 observations, annualization=261, target=40%, max notional 2x. Simple spot return replaces published excess futures return; no claim of reproducing original Sharpe.",
            "- Turtle risk is 0.5% per unit, not the original larger risk budget. Entries/adds obey a 2x notional cap; exposure can drift between trades. Stops can fill adversely through open gaps.",
            "- Turtle stop/channel exit takes precedence over new entries/adds; no same-day re-entry after exits. Unknown entry/stop or add/stop order is treated as a loss. Ambiguous counts are exported. Daily-close DD includes unrealized marked positions and finance but not intraday extremes.",
            "- Buy-and-hold is a required same-cost gold exposure control. Profitability in a gold bull market is not evidence of alpha; neither favorable results nor a single chosen cost scenario justify deployment.",
            "",
            "## Reproducibility audit",
            "",
            "See audit.json. AQR's complete diversified portfolio is not reproduced with gold alone. Forecast-to-Fill has missing fit parameters and non-equivalent headline/risk-scaled results; no arbitrary substitute is reported as the paper's backtest.",
            "",
            "## Sources",
            "",
            "- https://www.aqr.com/insights/research/journal-article/time-series-momentum",
            "- https://www.aqr.com/-/media/AQR/Documents/Insights/Journal-Article/Demystifying-Managed-Futures.pdf",
            "- https://www.tradingblox.com/originalturtles/originalturtlerules.pdf",
            "- https://arxiv.org/html/2511.08571v1",
            "",
            f"Completed cases: {len(completed)}. summary.csv, yearly.csv and each case's equity.csv/orders.csv/report.json retain every result, including unfavorable cases.",
            "",
        ]
    )
    (args.output / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Report: {args.output / 'REPORT.md'} | cases: {len(completed)}", flush=True)


if __name__ == "__main__":
    main()
