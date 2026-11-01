"""Backtest minute-horizon Donchian 55/20 on saved MT5/HistData M1 feeds."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.research.donchian_m1 import prepare, run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("reports/market_data"))
    parser.add_argument("--output", type=Path, default=Path("reports/donchian_m1"))
    parser.add_argument("--source", choices=("all", "mt5", "histdata"), default="all")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    hashes = {
        name: hashlib.sha256(Path(name).read_bytes()).hexdigest()
        for name in (
            "src/research/donchian_m1.py",
            "src/research/published_strategies.py",
            "scripts/backtest_donchian_m1.py",
        )
    }
    rows, reports = [], []
    for source in ("mt5", "histdata"):
        if args.source not in ("all", source):
            continue
        path = args.data / source / "history.csv"
        frame = pd.read_csv(path)
        frame["time"] = pd.to_datetime(frame["time"], unit="s", utc=True)
        frame = frame.set_index("time")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        groups = (
            [("2026_09_10", frame)]
            if source == "mt5"
            else [(str(year), group) for year, group in frame.groupby(frame.index.year)]
        )
        for period, bars in groups:
            prepared = prepare(bars)
            base_spreads = (
                bars.spread.to_numpy() * 0.001 if source == "mt5" else np.full(len(bars), 0.24)
            )
            warmup = 200
            split = warmup + int((len(bars) - warmup) * 0.7)
            if len(bars) <= warmup + 10:
                raise ValueError("Insufficient M1 bars")
            for scenario, multiplier, fee, carry in (
                ("base_no_fee", 1, 0, 0),
                ("fee_carry3pct", 1, 0.10, 0.03),
                ("spread150_fee_carry8pct", 1.5, 0.10, 0.08),
            ):
                key = f"{source}_{period}_{scenario}"
                folder = args.output / key
                folder.mkdir(parents=True, exist_ok=True)
                spreads = base_spreads * multiplier
                results, all_trades = {}, []
                for segment, begin, end in (
                    ("development", warmup, split),
                    ("holdout", split, len(bars)),
                ):
                    stats, trades, curve = run(
                        prepared, spreads, begin, end, fee_price=fee, annual_carry=carry
                    )
                    results[segment] = stats
                    for trade in trades:
                        trade["segment"] = segment
                    all_trades.extend(trades)
                    np.savez_compressed(
                        folder / f"equity_{segment}.npz",
                        time=prepared["times"][begin:end],
                        equity=curve,
                    )
                    pd.Series(curve, index=bars.index[begin:end], name="equity").resample(
                        "D"
                    ).last().dropna().to_csv(
                        folder / f"equity_daily_{segment}.csv", index_label="time"
                    )
                    rows.append(
                        dict(
                            source=source,
                            period=period,
                            scenario=scenario,
                            segment=segment,
                            **stats,
                        )
                    )
                pd.DataFrame(all_trades).to_csv(folder / "trades.csv", index=False)
                metadata = {
                    "source": source,
                    "period": period,
                    "scenario": scenario,
                    "bars": len(bars),
                    "input_sha256": digest,
                    "code_sha256": hashes,
                    "spread_kind": "observed broker bar spread"
                    if source == "mt5"
                    else "constant assumption",
                    "spread_median": float(np.median(spreads)),
                    "spread_multiplier": multiplier,
                    "round_trip_fee_price": fee,
                    "annual_carry": carry,
                    "slippage_ticks_each_side": 2,
                    "tick_size": 0.001,
                    "warmup_bars": warmup,
                    "split_time_utc": bars.index[split].isoformat(),
                    "strategy_id": "donchian_55_20_M1_research_v1",
                    "timeframe": "M1",
                    "no_fixed_tp": True,
                    "pyramiding": False,
                }
                report = {"metadata": metadata, "results": results}
                (folder / "report.json").write_text(
                    json.dumps(report, indent=2, allow_nan=False), encoding="utf-8"
                )
                reports.append(report)
                s = results["holdout"]
                print(
                    f"DONE {key}: holdout {s['trades']} trades | return {s['return_percent']:.2f}% | PF {s['profit_factor']}",
                    flush=True,
                )
    pd.DataFrame(rows).to_csv(args.output / "summary.csv", index=False)
    (args.output / "summary.json").write_text(
        json.dumps(reports, indent=2, allow_nan=False), encoding="utf-8"
    )
    lines = [
        "# Donchian 55/20 trên nến M1",
        "",
        "**55/20 là 55/20 nến PHÚT; không phải tín hiệu D1 được replay bằng M1. Không đổi bot demo D1.**",
        "",
        "| Nguồn/giai đoạn | Chi phí | Lệnh holdout | Win rate | Tổng R | PF | Return | DD mark M1 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in reports:
        m, s = r["metadata"], r["results"]["holdout"]
        pf = f"{s['profit_factor']:.3f}" if s["profit_factor"] is not None else "N/A"
        win = f"{s['win_rate']:.1%}" if s["win_rate"] is not None else "N/A"
        lines.append(
            f"| {m['source']} {m['period']} | {m['scenario']} | {s['trades']} | {win} | {s['total_r']:.2f} | {pf} | {s['return_percent']:.2f}% | {s['max_m1_close_drawdown_percent']:.2f}% |"
        )
    lines.extend(
        [
            "",
            "## Quy tắc và giả định",
            "",
            "- Đỉnh/đáy 55 và kênh thoát 20 dùng nến M1 trước, không gồm nến đang xét. SL ban đầu 2 Wilder ATR20 của nến trước, không TP cố định, một vị thế và không pyramiding.",
            "- Mỗi giai đoạn dùng 200 nến làm ấm, phần còn lại chia 70/30 theo thời gian. Hai phần reset equity 10.000 độc lập, ép thoát và tính phí ở cuối phần. HistData tách từng năm, MT5 riêng mẫu 50.000 nến. Dữ liệu từng được dùng trước; holdout không phải mẫu hoàn toàn chưa từng xem.",
            "- Risk tối đa 0,5% vốn mỗi lệnh, cap notional 2x. Ounce liên tục và sizing tại giá fill mô phỏng; không có lot tối thiểu/margin call, không bảo đảm lot pending tính trước sẽ có cùng risk khi gap.",
            "- BUY vào Ask, thoát Bid; SELL vào Bid, thoát Ask. Spread nến là hằng trong nến, không phải tick path. MT5 dùng spread lịch sử nến; HistData giả định 0,24. Ca stress nhân spread 1,5. Slippage bất lợi 0,002 mỗi chiều.",
            "- base_no_fee chưa gồm commission/swap. fee_carry3pct thêm phí khứ hồi 0,10 đơn vị giá và financing giả định 3%/năm; spread150_fee_carry8pct dùng 8%. Financing tính theo notional tuyệt đối và số giây giữ, không phải swap broker đã xác minh.",
            "- Kênh breakout chỉ cho vào khi 55 phút trước liên tục. Nếu đang giữ gặp gap, thoát tại open tiếp theo quan sát được, có spread và slippage; không giả định đường giá phút thiếu. Không vào lại trong cùng nến sau khi thoát.",
            "- Nến cùng chạm entry/SL hoặc cả hai hướng: tính stop bất lợi, ghi ambiguous_path. SL và kênh SELL chuyển sang Ask. Có thể mất hơn 1R khi gap hoặc spread thay đổi.",
            "- Equity mark từng close M1 gồm lãi/lỗ thả nổi, không gồm cực trị intraminute. PF theo PnL tiền ròng; R theo rủi ro SL ước tính tại entry, gồm phí/slippage nhưng chưa gồm financing tương lai.",
            "- Đây là backtest OHLC, không xác nhận thứ tự tick hay khớp broker thực tế. Dữ liệu các nguồn cùng thời kỳ không là mẫu độc lập; không cộng các kịch bản chi phí lại.",
            "",
            "Từng thư mục có trades.csv, report.json, equity_daily_*.csv và equity_*.npz lưu mọi equity close M1 kèm epoch seconds. summary.csv giữ cả development và holdout; SHA256 dữ liệu/mã nguồn được ghi để tái lập.",
            "",
        ]
    )
    (args.output / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Report: {args.output / 'REPORT.md'} | cases: {len(reports)}", flush=True)


if __name__ == "__main__":
    main()
