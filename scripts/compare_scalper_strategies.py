"""Compare terminal strategies on closed M1 data; never submit MT5 orders."""

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.research.scalper_comparison import compare
from src.research.tick_replay import TickReplay


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="XAUUSDc")
    parser.add_argument(
        "--strategies",
        nargs="+",
        choices=("pullback", "adaptive", "m5_m1", "m5_m1_quality", "m5_m1_regime"),
        default=["pullback", "adaptive"],
    )
    parser.add_argument(
        "--csv", type=Path, help="UTC epoch-seconds M1 CSV, including spread in points"
    )
    parser.add_argument("--encoding", default="utf-8")
    parser.add_argument("--mt5-bars", type=int, default=10000)
    parser.add_argument("--point", type=float, help="Broker point size; required with --csv")
    parser.add_argument("--tick-size", type=float, help="Broker tick size; required with --csv")
    parser.add_argument(
        "--stop-distance", type=float, help="Override minimum stop distance in price units"
    )
    parser.add_argument("--spread-price", type=float, help="Override all spreads in price units")
    parser.add_argument("--spread-multiplier", type=float, default=1)
    parser.add_argument(
        "--fee-price",
        type=float,
        default=0,
        help="Round-trip fee per lot divided by account-currency price-value per lot",
    )
    parser.add_argument("--slippage-ticks", type=int, default=2)
    parser.add_argument("--max-hold", type=int, default=120)
    parser.add_argument("--risk-percent", type=float, default=0.5)
    parser.add_argument("--initial-equity", type=float, default=10000)
    parser.add_argument("--output", type=Path, default=Path("reports/scalper_comparison"))
    tick_options = parser.add_mutually_exclusive_group()
    tick_options.add_argument(
        "--ticks",
        action="store_true",
        help="Replay MT5 bid/ask history with 15-second pending expiry",
    )
    tick_options.add_argument(
        "--ticks-csv", type=Path, help="Replay CSV/gzip with time_msc, bid, ask"
    )
    parser.add_argument("--max-ticks", type=int, default=2000000)
    args = parser.parse_args()
    if args.mt5_bars < 3501:
        parser.error("--mt5-bars must exceed 3500")
    if not math.isfinite(args.spread_multiplier) or args.spread_multiplier <= 0:
        parser.error("--spread-multiplier must be finite and positive")
    stop_distance = 0.0
    if args.csv:
        if args.point is None or args.tick_size is None:
            parser.error("--csv requires --point and --tick-size")
        raw = pd.read_csv(args.csv, encoding=args.encoding)
        source = str(args.csv)
        point, tick_size = args.point, args.tick_size
    else:
        import MetaTrader5 as mt5

        if not mt5.initialize(timeout=10000):
            raise SystemExit("Cannot connect to MT5; open and log in first")
        try:
            if not mt5.symbol_select(args.symbol, True):
                raise ValueError("Symbol unavailable")
            broker = mt5.symbol_info(args.symbol)
            data = mt5.copy_rates_from_pos(args.symbol, mt5.TIMEFRAME_M1, 1, args.mt5_bars)
            if broker is None or data is None:
                raise ValueError("MT5 history unavailable")
            raw = pd.DataFrame(data)
            point, tick_size = broker.point, broker.trade_tick_size
            stop_distance = broker.trade_stops_level * broker.point
            source = "MT5 closed M1 bars"
        finally:
            mt5.shutdown()
    if not all(math.isfinite(value) and value > 0 for value in (point, tick_size)):
        parser.error("Point and tick size must be finite and positive")
    if args.stop_distance is not None:
        stop_distance = args.stop_distance
    raw["time"] = pd.to_datetime(raw["time"], unit="s", utc=True)
    bars = raw.set_index("time")
    # Do not silently include a forming/future candle, even for externally provided CSVs.
    bars = bars.loc[bars.index + pd.Timedelta(minutes=1) <= pd.Timestamp.now(tz="UTC")]
    if args.spread_price is not None:
        spreads = pd.Series(args.spread_price, index=bars.index)
    elif "spread" in bars:
        spreads = bars["spread"].astype(float) * point
    else:
        parser.error("History has no spread column; provide --spread-price explicitly")
    spreads = spreads * args.spread_multiplier
    replay = None
    tick_data = None
    if args.ticks or args.ticks_csv:
        if len(bars) <= 3500 or args.max_ticks < 1:
            parser.error("Tick replay requires >3500 bars and a positive --max-ticks")
        if args.ticks_csv:
            tick_data = pd.read_csv(
                args.ticks_csv, usecols=["time_msc", "bid", "ask"], nrows=args.max_ticks + 1
            )
            if len(tick_data) > args.max_ticks:
                parser.error("Tick file exceeds --max-ticks")
        else:
            import MetaTrader5 as mt5

            if not mt5.initialize(timeout=10000):
                raise SystemExit("Cannot connect to MT5 for historical ticks")
            chunks, total = [], 0
            try:
                if not mt5.symbol_select(args.symbol, True):
                    raise ValueError("Symbol unavailable for tick download")
                cursor = bars.index[3300] - pd.Timedelta(minutes=1)
                until = bars.index[-1] + pd.Timedelta(minutes=1)
                while cursor < until:
                    finish = min(cursor + pd.Timedelta(hours=1), until)
                    raw_ticks = mt5.copy_ticks_range(
                        args.symbol,
                        cursor.to_pydatetime(),
                        finish.to_pydatetime(),
                        mt5.COPY_TICKS_INFO,
                    )
                    if raw_ticks is None:
                        raise ValueError("MT5 failed to download a tick interval; no OHLC fallback")
                    if len(raw_ticks):
                        chunk = pd.DataFrame(raw_ticks)[["time_msc", "bid", "ask"]]
                        total += len(chunk)
                        if total > args.max_ticks:
                            raise ValueError(
                                "Tick limit exceeded; reduce --mt5-bars or raise --max-ticks"
                            )
                        chunks.append(chunk)
                    print(f"Ticks through {finish}: {total}", flush=True)
                    cursor = finish
            finally:
                mt5.shutdown()
            if not chunks:
                raise SystemExit("No historical ticks available; cannot replay")
            # MT5 range endpoints are inclusive: remove identical boundary events.
            tick_data = pd.concat(chunks, ignore_index=True).drop_duplicates()
        adjusted = tick_data.copy()
        adjusted["ask"] = (
            adjusted["bid"] + (adjusted["ask"] - adjusted["bid"]) * args.spread_multiplier
        )
        replay = TickReplay(adjusted)
    print(f"Closed bars: {len(bars)} | {bars.index.min()} to {bars.index.max()}", flush=True)
    print(
        "Tick replay: 15-second pending lifetime, observed bid/ask ordering."
        if replay
        else "Research proxy: one-minute pending lifetime; not the live 15-second lifetime.",
        flush=True,
    )
    result = compare(
        bars,
        spreads,
        tick_size=tick_size,
        stop_distance=stop_distance,
        slippage_ticks=args.slippage_ticks,
        fee_price=args.fee_price,
        max_hold=args.max_hold,
        risk_percent=args.risk_percent,
        initial_equity=args.initial_equity,
        progress=lambda name, segment, i, n: print(f"{name} | {segment} | {i}/{n}", flush=True),
        tick_replay=replay,
        strategies=tuple(args.strategies),
    )
    trades = result.pop("trades")
    events = result.pop("execution_events")
    result["metadata"] = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "symbol": args.symbol,
        "strategies": args.strategies,
        "bars": len(bars),
        "history_sha256": hashlib.sha256(bars.to_csv().encode()).hexdigest(),
        "start_utc": bars.index[0].isoformat(),
        "end_utc": bars.index[-1].isoformat(),
        "point": point,
        "tick_size": tick_size,
        "current_stop_distance": stop_distance,
        "spread_multiplier": args.spread_multiplier,
        "spread_override": args.spread_price,
        "fee_price": args.fee_price,
        "fees_supplied": args.fee_price > 0,
        "slippage_ticks": args.slippage_ticks,
        "max_hold_bars": args.max_hold,
        "risk_percent": args.risk_percent,
        "initial_virtual_equity": args.initial_equity,
        "execution_proxy": "M1 OHLC, pending expires after one bar; SL first on ambiguous paths",
        "sizing_proxy": "Continuous normalized risk; no broker lot rounding/margin or Kelly",
        "zero_spread_bars": int((spreads == 0).sum()),
        "spread_price_min": float(spreads.min()),
        "spread_price_median": float(spreads.median()),
        "spread_price_max": float(spreads.max()),
        "strategy_code_sha256": {
            name: hashlib.sha256(
                (Path(__file__).resolve().parents[1] / name).read_bytes()
            ).hexdigest()
            for name in (
                "src/strategies/xauusd_m1_scalper.py",
                "src/strategies/adaptive_scalper.py",
                "src/strategies/m5_m1_pullback.py",
                "src/strategies/entry_support.py",
                "src/research/scalper_comparison.py",
            )
        },
    }
    args.output.mkdir(parents=True, exist_ok=True)
    if replay is not None:
        tick_data.to_csv(args.output / "ticks.csv.gz", index=False)
        result["metadata"].update(
            execution_proxy="Observed bid/ask tick replay; pending expires strictly before 15-second deadline",
            tick_rows=len(tick_data),
            tick_sha256=hashlib.sha256(tick_data.to_csv(index=False).encode()).hexdigest(),
            max_observed_tick_gap_seconds=30,
            tick_start_utc=replay.data.index[0].isoformat(),
            tick_end_utc=replay.data.index[-1].isoformat(),
        )
        result["metadata"]["strategy_code_sha256"]["src/research/tick_replay.py"] = hashlib.sha256(
            (Path(__file__).resolve().parents[1] / "src/research/tick_replay.py").read_bytes()
        ).hexdigest()
        pd.DataFrame(
            events, columns=["strategy", "segment", "decision_utc", "status", "filled", "reason"]
        ).to_csv(args.output / "execution_events.csv", index=False)
    export = bars.reset_index()
    export["time"] = export["time"].dt.as_unit("s").astype("int64")
    export.to_csv(args.output / "history.csv", index=False)
    columns = [
        "strategy",
        "segment",
        "setup_type",
        "entry_time_utc",
        "exit_time_utc",
        "exit_index",
        "side",
        "entry",
        "stop_loss",
        "take_profit",
        "exit_price",
        "outcome",
        "ambiguous_path",
        "net_r",
    ]
    pd.DataFrame(trades, columns=columns).to_csv(args.output / "trades.csv", index=False)
    (args.output / "report.json").write_text(
        json.dumps(result, indent=2, allow_nan=False), encoding="utf-8"
    )
    lines = [
        "# So sánh chiến lược: " + ", ".join(args.strategies),
        "",
        "**Nghiên cứu mô phỏng, chưa chứng minh chiến lược nào tốt hơn.**",
        "",
        f"Dữ liệu: {len(bars)} nến M1, từ {bars.index[0]} đến {bars.index[-1]}.",
        f"Mốc holdout: {result['split_time_utc']}. Hai phần đều dùng dữ liệu trước đó để làm ấm chỉ báo.",
        "",
        "| Chiến lược | Phần | Tín hiệu | Lệnh | Win rate | Kỳ vọng R/lệnh | Tổng R | Drawdown đóng lệnh |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, segments in result["results"].items():
        for segment, stats in segments.items():
            win = f"{stats['win_rate']:.1%}" if stats["win_rate"] is not None else "N/A"
            expectation = (
                f"{stats['expectancy_r']:.3f}" if stats["expectancy_r"] is not None else "N/A"
            )
            lines.append(
                f"| {name} | {segment} | {stats['signals']} | {stats['trades']} | {win} | "
                f"{expectation} | {stats['total_r']:.2f} | {stats['max_closed_trade_drawdown_percent']:.2f}% |"
            )
    lines += [
        "",
        "## Giả định và giới hạn",
        "",
        "- Giữ nguyên tham số hai chiến lược; chia 70/30 theo thời gian sau 3.300 nến làm ấm. Không huấn luyện/tối ưu trên holdout.",
        "- Holdout là phần tách theo thời gian trong công cụ; không bảo đảm người phát triển chưa từng xem giai đoạn này. Không phải xác nhận độc lập về lợi nhuận.",
        "- Chỉ dùng nến đã đóng tại lúc phát tín hiệu. Một vị thế mỗi chiến lược; không chồng lệnh trong từng phần.",
        "- Dùng stop-entry cùng hàm tạo giá của terminal; giá bid OHLC và spread cố định trong mỗi nến. Spread tại quyết định lấy từ nến trước.",
        "- Lệnh chờ tồn tại tối đa một nến M1, KHÁC thời hạn 15 giây của terminal. Không có tick nên không thể xác định khớp trong 15 giây.",
        "- Cả SL/TP bị chạm: tính SL trước. Nến khớp chạm SL cũng tính SL, dù không rõ thứ tự thực tế. Gap SL khớp tại giá mở bất lợi.",
        "- Thoát sau số nến tối đa hoặc cuối phần; gặp khoảng trống dữ liệu thì thoát tại giá mở tiếp theo quan sát được.",
        "- Trượt giá bất lợi ở cả vào/ra; TP cũng trừ trượt giá. Phí mặc định bằng 0 nếu chưa nhập --fee-price; kết quả khi đó CHƯA gồm commission/swap.",
        "- Equity là tài khoản ảo và lot liên tục; không mô phỏng lot tối thiểu, margin, Kelly hay các vị thế ngoài chiến lược. Drawdown chỉ đo ở các lệnh đã đóng.",
        "- Khoảng cách stop tối thiểu dùng thông số broker hiện tại nếu lấy trực tiếp MT5; có thể khác thông số lịch sử.",
        "- Mẫu ngắn hoặc ít lệnh không đủ kết luận; cần dữ liệu dài hơn, tick replay, kiểm tra nhiều giai đoạn và demo.",
        "- Báo cáo không tự đổi chiến lược mặc định và không đưa dữ liệu mô phỏng vào nhật ký Kelly thực tế.",
        "",
    ]
    if replay is not None:
        # Remove OHLC-only assumptions rather than presenting contradictory execution rules.
        ohlc_prefixes = ("- Dùng stop-entry", "- Lệnh chờ tồn tại", "- Cả SL/TP", "- Thoát sau")
        lines = [line for line in lines if not line.startswith(ohlc_prefixes)]
        lines += [
            "## Chế độ tick đang dùng",
            "",
            f"Lần chạy này dùng {len(tick_data)} tick bid/ask, từ {replay.data.index[0]} đến {replay.data.index[-1]}.",
            "- Lấy quote tại/trước lúc quyết định, tuổi tối đa 15 giây; không dùng quote tương lai để tạo tín hiệu.",
            "- Lệnh chờ hết hạn tại mốc sớm hơn giữa quyết định +15 giây và giây quote +15 giây. Tick đúng mốc hết hạn không được khớp.",
            "- BUY khớp Ask, thoát Bid; SELL khớp Bid, thoát Ask. SL dùng quote thực tế sau gap; TP không nhận cải thiện giá vượt mục tiêu.",
            "- Khoảng trống tick >30 giây là dữ liệu chưa xác định; không coi là giá đứng yên. Vị thế đã khớp nhưng thiếu đường thoát sẽ dừng phần đánh giá đó.",
            "- Tick cùng millisecond giữ thứ tự nguồn và đánh dấu ambiguous_path; không bảo đảm biết thứ tự thực tế trong cùng millisecond.",
            "- Thiếu quote quyết định và cửa sổ không xác định được đếm riêng. Không tự chuyển sang OHLC.",
            "- Thống kê lợi nhuận chỉ gồm các lệnh có kết quả xác định; có vị thế chưa giải quyết thì đây không phải kết quả đầy đủ của phần dữ liệu đó.",
            "- execution_events.csv ghi mỗi tín hiệu có quote: đã đóng, hết hạn chưa khớp hoặc không xác định; ticks.csv.gz lưu dữ liệu để chạy lại.",
            "- Đây vẫn là mô phỏng: chưa mô hình hóa độ trễ phân tích/gửi lệnh, độ sâu thị trường, khớp một phần, lot tối thiểu hoặc margin.",
            "",
            "| Chiến lược | Phần | Thiếu quote quyết định | Cửa sổ tick không xác định | Vị thế chưa giải quyết |",
            "|---|---|---:|---:|---:|",
        ]
        for name, segments in result["results"].items():
            for segment, stats in segments.items():
                lines.append(
                    f"| {name} | {segment} | {stats['missing_decision_quotes']} | "
                    f"{stats['unknown_tick_windows']} | {stats['unresolved_positions']} |"
                )
    report = "\n".join(lines)
    (args.output / "REPORT.md").write_text(report, encoding="utf-8")
    print(json.dumps(result["results"], indent=2), flush=True)
    print(f"Report: {args.output / 'REPORT.md'}", flush=True)


if __name__ == "__main__":
    main()
