"""Run fixed-parameter multi-source cost sensitivity research, without live orders."""

import argparse
import hashlib
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

import pandas as pd

from src.research.scalper_comparison import compare, summarize

STRATEGIES = ("m5_m1", "m5_m1_quality", "m5_m1_regime")
CODE_FILES = (
    "src/research/scalper_comparison.py",
    "src/strategies/xauusd_m1_scalper.py",
    "src/strategies/m5_m1_pullback.py",
    "src/strategies/entry_support.py",
)


def run_job(job):
    started = perf_counter()
    folder = Path(job["output"]) / job["id"]
    folder.mkdir(parents=True, exist_ok=True)
    source = Path(job["csv"])
    bars = pd.read_csv(source)
    bars["time"] = pd.to_datetime(bars["time"], unit="s", utc=True)
    bars = bars.set_index("time")
    if job.get("year"):
        bars = bars.loc[bars.index.year == job["year"]].copy()
    spreads = (
        pd.Series(job["spread_price"], index=bars.index)
        if job["spread_price"] is not None
        else bars["spread"] * 0.001 * job["spread_multiplier"]
    )
    with (folder / "progress.log").open("w", encoding="utf-8") as log:

        def progress(strategy, segment, position, total):
            log.write(f"{strategy} {segment} {position}/{total}\n")
            log.flush()

        result = compare(
            bars,
            spreads,
            strategies=STRATEGIES,
            tick_size=0.001,
            slippage_ticks=2,
            fee_price=job["fee_price"],
            risk_percent=0.5,
            max_hold=120,
            progress=progress,
        )
    trades = result.pop("trades")
    result.pop("execution_events")
    trade_frame = pd.DataFrame(trades)
    if not trade_frame.empty:
        trade_frame.to_csv(folder / "trades.csv", index=False)
    else:
        pd.DataFrame(columns=["strategy", "segment", "net_r"]).to_csv(
            folder / "trades.csv", index=False
        )
    result["combined"] = {
        name: summarize([t for t in trades if t["strategy"] == name]) for name in STRATEGIES
    }
    monthly = []
    if trades:
        trade_frame["month_utc"] = pd.to_datetime(
            trade_frame["entry_time_utc"], utc=True
        ).dt.strftime("%Y-%m")
        for (strategy, segment, month), group in trade_frame.groupby(
            ["strategy", "segment", "month_utc"]
        ):
            monthly.append(
                dict(
                    strategy=strategy,
                    segment=segment,
                    month_utc=month,
                    **summarize(group.to_dict("records")),
                )
            )
    pd.DataFrame(monthly).to_csv(folder / "monthly.csv", index=False)
    root = Path(__file__).resolve().parents[1]
    result["metadata"] = dict(
        job,
        created_at_utc=datetime.now(timezone.utc).isoformat(),
        input_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        bars=len(bars),
        start_utc=bars.index[0].isoformat(),
        end_utc=bars.index[-1].isoformat(),
        spread_min=float(spreads.min()),
        spread_median=float(spreads.median()),
        spread_max=float(spreads.max()),
        parameters={
            "tick_size": 0.001,
            "stop_distance": 0,
            "slippage_ticks": 2,
            "max_hold_bars": 120,
            "risk_percent": 0.5,
        },
        code_sha256={
            name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in CODE_FILES
        },
        execution="M1 OHLC proxy, one-bar pending lifetime, stop first on ambiguous paths; not 15-second tick replay",
        commission_note="fee_price is an explicit hypothetical round-trip price cost; zero means fees not supplied",
        elapsed_seconds=perf_counter() - started,
    )
    (folder / "report.json").write_text(
        json.dumps(result, indent=2, allow_nan=False), encoding="utf-8"
    )
    return result


def build_jobs(data, output):
    jobs = []
    for year in (2024, 2025, 2026):
        for label, spread, fee in (
            ("spread024", 0.24, 0),
            ("spread036", 0.36, 0),
            ("spread036_fee010", 0.36, 0.10),
        ):
            jobs.append(
                {
                    "id": f"histdata_{year}_{label}",
                    "source": "HistData",
                    "year": year,
                    "csv": str(data / "histdata" / "history.csv"),
                    "output": str(output),
                    "cost_case": label,
                    "spread_price": spread,
                    "spread_multiplier": 1,
                    "fee_price": fee,
                }
            )
    for label, multiplier, fee in (("observed", 1, 0), ("spread150_fee010", 1.5, 0.10)):
        jobs.append(
            {
                "id": f"mt5_{label}",
                "source": "MT5",
                "year": None,
                "csv": str(data / "mt5" / "history.csv"),
                "output": str(output),
                "cost_case": label,
                "spread_price": None,
                "spread_multiplier": multiplier,
                "fee_price": fee,
            }
        )
    return jobs


def write_summary(results, output):
    rows = []
    for result in results:
        meta = result["metadata"]
        for name, segments in result["results"].items():
            for segment, stats in segments.items():
                rows.append(
                    dict(
                        job=meta["id"],
                        source=meta["source"],
                        year=meta["year"],
                        cost_case=meta["cost_case"],
                        strategy=name,
                        segment=segment,
                        **stats,
                    )
                )
    table = pd.DataFrame(rows)
    table.to_csv(output / "summary.csv", index=False)
    (output / "summary.json").write_text(
        json.dumps(results, indent=2, allow_nan=False), encoding="utf-8"
    )
    lines = [
        "# Kiểm chứng M5/M1 trên dữ liệu nhiều nguồn",
        "",
        "Tham số chiến lược được giữ nguyên. Không tối ưu ngưỡng theo kết quả. Không tự đổi mặc định hoặc gửi lệnh.",
        "",
        "## Holdout theo nguồn, năm và giả định chi phí",
        "",
        "| Nguồn/năm | Chi phí | Chiến lược | Lệnh | Win rate | Tổng R | R/lệnh | PF | DD đóng lệnh |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    def fmt(value, spec=".3f"):
        return format(value, spec) if value is not None else "N/A"

    for result in results:
        meta = result["metadata"]
        for name in STRATEGIES:
            s = result["results"][name]["holdout"]
            lines.append(
                f"| {meta['source']} {meta['year'] or '09-10/2026'} | {meta['cost_case']} | {name} | {s['trades']} | {fmt(s['win_rate'], '.1%')} | {s['total_r']:.2f} | {fmt(s['expectancy_r'])} | {fmt(s['profit_factor'])} | {s['max_closed_trade_drawdown_percent']:.2f}% |"
            )
    lines.extend(
        [
            "",
            "## Phương pháp và giới hạn",
            "",
            "- HistData chia riêng từng năm 2024, 2025, 2026; 2026 chỉ tới 23/10. MT5 giữ riêng giai đoạn 09-10/2026, có thời gian giao nhau với HistData. Không cộng hai nguồn thành mẫu độc lập.",
            "- Mỗi bộ dùng 3.300 nến đầu làm ấm, phần còn lại chia 70/30 theo thời gian. Chỉ nến đã đóng được nhìn thấy tại thời điểm quyết định. Không huấn luyện trên development; đây là hai phân đoạn đánh giá với tham số cố định.",
            "- Holdout không phải đảm bảo chưa từng được xem. Các thử nghiệm trước đã dùng một phần tháng 10/2026; kết quả ở giai đoạn đó không là kiểm chứng độc lập hoàn toàn.",
            "- HistData giả định spread 0,24 hoặc 0,36 đơn vị giá. fee010 là phí khứ hồi 0,10 đơn vị giá, chỉ là kịch bản, không phải phí broker đã xác minh. MT5 observed dùng spread nến của broker; spread150 nhân spread đó với 1,5. Các ca không có fee chưa gồm commission/swap.",
            "- Mọi ca có trượt giá bất lợi 2 tick (0,002) ở vào/ra. Tick-size 0,001 là giả định cho nguồn ngoài và theo symbol MT5 đã tải. Minimum stop distance bằng 0 do chưa có lịch sử thông số broker.",
            "- OHLC M1 chỉ là mô phỏng: pending tối đa một nến, khác thời hạn 15 giây ở trợ lý. SL trước nếu thứ tự trong nến không xác định; xuất số lệnh ambiguous và gap trong JSON. Không diễn giải là chất lượng khớp tick đã được xác nhận.",
            "- Một vị thế cho mỗi chiến lược. Risk mô phỏng 0,5%, equity khởi đầu 10.000 mỗi phần; DD chỉ đo tại đóng lệnh, chưa gồm lỗ thả nổi, lot tối thiểu, margin hoặc Kelly. Một R là rủi ro chuẩn hóa theo SL và chi phí mô phỏng.",
            "- Các timestamp HistData mâu thuẫn đã bị cách ly; không điền nến vào gap. Giá hai nguồn có thể khác; chưa tự căn chỉnh độ lệch giờ ngoài chuyển đổi múi giờ theo tài liệu nguồn.",
            "- Profit factor N/A khi không có khoản lỗ; không coi ít lệnh hoặc không có lệnh là chiến lược tốt. Kịch bản chi phí có thể thay đổi số lệnh vì bộ lọc spread.",
            "",
            "Mỗi thư mục con có report.json, trades.csv, monthly.csv và progress.log. summary.csv chứa cả development và holdout; SHA256 dữ liệu và mã nguồn được ghi trong từng report.json.",
            "",
        ]
    )
    (output / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("reports/market_data"))
    parser.add_argument("--output", type=Path, default=Path("reports/market_data_backtest"))
    parser.add_argument("--workers", type=int, default=2, choices=(1, 2))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    jobs = build_jobs(args.data, args.output)
    results, errors = [], []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_job, job): job for job in jobs}
        for future in as_completed(futures):
            job = futures[future]
            try:
                result = future.result()
                results.append(result)
                print(
                    f"DONE {job['id']} | {result['metadata']['bars']} bars | {result['metadata']['elapsed_seconds']:.1f}s",
                    flush=True,
                )
            except Exception as exc:
                errors.append({"job": job["id"], "error": str(exc)})
                print(f"ERROR {job['id']}: {exc}", flush=True)
    results.sort(key=lambda result: result["metadata"]["id"])
    write_summary(results, args.output)
    (args.output / "errors.json").write_text(json.dumps(errors, indent=2), encoding="utf-8")
    print(f"Report: {args.output / 'REPORT.md'} | jobs: {len(results)}/{len(jobs)}", flush=True)
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
