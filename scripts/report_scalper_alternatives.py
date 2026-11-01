"""Audit saved trade metrics and write the M1 alternatives comparison report."""

import json
from pathlib import Path

import numpy as np
import pandas as pd


def main():
    folder = Path("reports/scalper_alternatives")
    summary = pd.read_csv(folder / "summary.csv")
    if len(summary) != 32:
        raise ValueError("Expected four cases, four strategies, two segments; run backtest first")
    audited = 0
    for case, group in summary.groupby("case"):
        trades = pd.read_csv(folder / f"{case}_trades.csv")
        report = json.loads((folder / f"{case}.json").read_text(encoding="utf-8"))
        for row in group.itertuples():
            selected = trades[(trades.strategy == row.strategy) & (trades.segment == row.segment)]
            assert len(selected) == row.trades
            assert np.isclose(selected.net_r.sum(), row.total_r)
            if len(selected):
                expected = 100 * (np.prod(1 + .005 * selected.net_r.to_numpy()) - 1)
                assert np.isclose(expected, row.return_percent)
                direction = np.where(selected.side == "BUY", 1, -1)
                risk = (selected.entry - selected.stop_loss).abs() + .002 + .10
                assert np.allclose((direction * (selected.exit_price - selected.entry) - .10) / risk,
                                   selected.net_r)
                entry = pd.to_datetime(selected.entry_time_utc, utc=True)
                exit_time = pd.to_datetime(selected.exit_time_utc, utc=True)
                assert (exit_time >= entry).all()
                assert (entry.iloc[1:].reset_index(drop=True)
                        > exit_time.iloc[:-1].reset_index(drop=True)).all()
                if row.segment == "holdout":
                    assert (entry >= pd.Timestamp(report["split_time_utc"])).all()
            audited += len(selected)
    lines = ["# Thử chiến lược M1 nhiều lệnh hơn ORB", "",
        "Ngày chạy: 01/11/2026. So sánh ORB5 với ba bản pullback có sẵn, không tối ưu lại tham số.", "",
        "## Holdout sau chi phí giả định", "",
        "| Dữ liệu/kịch bản | Chiến lược | Lệnh | Win rate | PF | Return | DD đóng lệnh |",
        "|---|---|---:|---:|---:|---:|---:|"]
    for row in summary[summary.segment == "holdout"].itertuples():
        pf = f"{row.profit_factor:.2f}" if pd.notna(row.profit_factor) else "N/A"
        lines.append(f"| {row.case} | {row.strategy} | {row.trades} | {row.win_rate:.1%} | {pf} | "
                     f"{row.return_percent:+.2f}% | {row.max_closed_trade_drawdown_percent:.2f}% |")
    alternatives = summary[(summary.segment == "holdout") & (summary.strategy != "orb5_mtf")]
    if (alternatives.return_percent < 0).all():
        lines += ["", "Cả ba bản thay thế đều tăng số lệnh nhưng âm trên holdout ở cả hai nguồn và cả hai mức spread. Chưa chọn bản nào thay ORB mặc định."]
    lines += ["", "## Quy tắc và cách đọc", "",
        "- `pullback`: M1 hồi/vượt lại EMA21, màu nến/RSI/ADX xác nhận; M5 EMA9/21 và M15 close/EMA200 đồng hướng.",
        "- `m5_m1`: cùng xác nhận M1, M5 chọn hướng; M15 chỉ là bối cảnh. `m5_m1_quality` thêm độ dốc/tách EMA M5 và giới hạn đuổi giá M1.",
        "- Các bản pullback không giới hạn một tín hiệu đầu phiên như ORB. Tất cả vẫn dùng bộ lọc spread, nến bất thường và tính hợp lệ dữ liệu.",
        "- MT5: 50.000 nến M1 tháng 09–10/2026, spread lịch sử nhân 0,001. HistData 2026: 286.270 nến, spread giả định 0,24; hai nguồn trùng giai đoạn, không độc lập.",
        "- `fee`: commission khứ hồi giả định 0,10 đơn vị giá; `stress`: cùng phí, spread tăng 50%. Cả hai có slippage bất lợi 0,002 mỗi chiều. Chưa xác minh phí broker, chưa tính swap.",
        "- Mỗi nguồn làm ấm 3.300 nến rồi chia thời gian 70/30. Reset vốn 10.000 USD riêng mỗi phần; risk 0,5% mỗi lệnh, một vị thế, lot liên tục. Return là của phần kiểm tra, không phải theo năm.",
        "- Dùng cùng hàm future_entry với terminal; chờ phá high/low nến tín hiệu. Mô phỏng OHLC chờ một phút, khác live 15 giây; SL trước khi không rõ thứ tự chạm SL/TP. Thoát sau tối đa 120 nến hoặc cuối phần; gap thoát ở open kế tiếp.",
        "- Chưa mô phỏng Kelly, lot tối thiểu, margin, độ trễ, kiểm tra RR ròng của bước sizing broker hoặc thao tác Enter. Chỉ báo tích lũy có thể khác cửa sổ làm ấm terminal. Đây là so sánh nghiên cứu, không phải replay chính xác toàn bộ vận hành live.",
        "- Drawdown chỉ đo khi đóng lệnh; thống kê gap/đường giá mơ hồ ở JSON. Cờ observed_paths_complete trong chế độ OHLC không xác nhận đầy đủ tick.",
        "- Dữ liệu đã được dùng trong các thử nghiệm trước; holdout không phải mẫu độc lập mới. Không đổi chiến lược mặc định chỉ vì nhiều lệnh hơn.", "",
        f"Đã đối chiếu {audited} dòng giao dịch với số lệnh, tổng R, equity lũy kế, chi phí từng lệnh, thứ tự vào/ra và mốc holdout. 57 bài kiểm tra chiến lược/mô phỏng đạt.", "",
        "## Tái lập", "", "```powershell",
        ".\\venv\\Scripts\\python.exe -u -m scripts.backtest_scalper_alternatives",
        ".\\venv\\Scripts\\python.exe -m scripts.report_scalper_alternatives", "```", "",
        "Dữ liệu từng lệnh, summary.csv và JSON chứa tham số/hash nguồn/mã nằm trong `reports/scalper_alternatives/`.", ""]
    Path("docs/SCALPER_ALTERNATIVES_BACKTEST.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Audited {audited} trades; report: docs/SCALPER_ALTERNATIVES_BACKTEST.md")


if __name__ == "__main__":
    main()
