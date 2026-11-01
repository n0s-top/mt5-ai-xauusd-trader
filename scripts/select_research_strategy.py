"""Screen saved results without fitting parameters or changing live defaults."""

import hashlib
import json
from pathlib import Path

import pandas as pd


def main():
    paths = [Path(p) for p in (
        "reports/scalper_alternatives/summary.csv",
        "reports/session_engulfing/summary.csv",
        "reports/session_engulfing_crossyear/summary.csv",
        "reports/published_strategies/summary.csv",
    )]
    common = pd.concat([pd.read_csv(p) for p in paths[:2]], ignore_index=True)
    common = common[common.segment == "holdout"]
    expected_cases = {"mt5_2026_09_10_fee", "mt5_2026_09_10_stress",
                      "histdata_2026_fee", "histdata_2026_stress"}
    records = []
    for name, group in common.groupby("strategy"):
        assert set(group.case) == expected_cases and len(group) == 4
        records.append(dict(strategy=name, minimum_trades=int(group.trades.min()),
            worst_expectancy_r=float(group.expectancy_r.min()),
            worst_return_percent=float(group.return_percent.min()),
            max_closed_trade_dd_percent=float(group.max_closed_trade_drawdown_percent.max()),
            qualifies=bool((group.trades >= 30).all() and (group.expectancy_r > 0).all()
                           and (group.profit_factor > 1).all() and (group.return_percent > 0).all())))
    scalpers = pd.DataFrame(records).sort_values("worst_expectancy_r", ascending=False)
    daily = pd.read_csv(paths[3])
    daily = daily[daily.scenario != "execution_only"]
    daily_rows = []
    for name, group in daily.groupby("method"):
        daily_rows.append(dict(strategy=name, minimum_cagr_percent=float(group.cagr_percent.min()),
            max_daily_close_dd_percent=float(group.daily_close_drawdown_percent.max()),
            conservative_return_dd=float(group.cagr_percent.min() / group.daily_close_drawdown_percent.max()),
            qualifies=bool((group.cagr_percent > 0).all() and (group.daily_close_drawdown_percent <= 10).all())))
    daily_table = pd.DataFrame(daily_rows).sort_values("conservative_return_dd", ascending=False)
    eligible = daily_table[daily_table.qualifies]
    preferred = eligible.iloc[0].strategy if len(eligible) else None
    crossyear = pd.read_csv(paths[2])
    crossyear = crossyear[(crossyear.segment == "holdout") & crossyear.case.str.startswith("histdata_")]
    assert set(crossyear.case) == {f"histdata_{year}_{case}" for year in (2024, 2025) for case in ("fee", "stress")}
    result = dict(scope="Observed candidate set only; no independent unseen validation",
        intraday_criteria="At least 30 trades per case, positive expectancy/return, PF>1 in all four matched cases",
        daily_criteria="All cost-inclusive cases positive CAGR, DD<=10%; rank min CAGR / max DD",
        scalping_selected=None if not scalpers.qualifies.any() else scalpers[scalpers.qualifies].iloc[0].strategy,
        daily_preferred=preferred,
        scalping=json.loads(scalpers.to_json(orient="records")),
        daily=json.loads(daily_table.to_json(orient="records")),
        engulfing_crossyear=json.loads(crossyear.to_json(orient="records")),
        sources={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    output = Path("reports/strategy_selection")
    output.mkdir(parents=True, exist_ok=True)
    (output / "selection.json").write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    lines = ["# Chọn chiến lược từ dữ liệu đã có", "", "Ngày đánh giá: 01/11/2026.", "",
        "## Scalping: chưa có ứng viên đạt", "",
        "So sánh năm ứng viên trên cùng bốn ca: MT5 09–10/2026 và HistData 2026, mỗi nguồn có spread gốc và tăng 50%, cùng phí giả định 0,10 và slippage 0,002 mỗi chiều. Cùng risk 0,5%, chia 70/30, warm-up 3.300 M1, reset vốn 10.000 USD mỗi phần. Không gộp các nguồn trùng thời kỳ thành mẫu độc lập.", "",
        "Quy tắc sàng lọc lần này: mỗi ca có ít nhất 30 lệnh, kỳ vọng R và return dương, PF > 1 ở cả bốn ca. Mốc 30 chỉ là ngưỡng thực dụng, không chứng minh ý nghĩa thống kê. Đây là đánh giá lại dữ liệu đã xem, không phải tiêu chí được đăng ký trước hay kiểm định ngoài mẫu độc lập.", "",
        "| Chiến lược | Ít lệnh nhất/ca | Kỳ vọng R xấu nhất | Return xấu nhất | DD đóng lệnh cao nhất | Đạt |",
        "|---|---:|---:|---:|---:|---|"]
    for row in scalpers.itertuples():
        lines.append(f"| {row.strategy} | {row.minimum_trades} | {row.worst_expectancy_r:+.3f} | {row.worst_return_percent:+.2f}% | {row.max_closed_trade_dd_percent:.2f}% | {'Có' if row.qualifies else 'Không'} |")
    lines += ["", "Thứ tự bảng chỉ theo kỳ vọng R trong ca xấu nhất; không phải chứng minh chiến lược đứng đầu có lợi thế. Ngay cả bỏ điều kiện 30 lệnh, các ứng viên vẫn không đạt vì có ca kỳ vọng âm.", "",
        "## Bổ sung engulfing trên 2024–2025", "",
        "Giữ nguyên mọi tham số từ lần thử 2026; không tìm lại ngưỡng để sửa kết quả. Đây là kiểm tra độ ổn định thêm, chưa phải dữ liệu thị trường mới.", "",
        "| Ca | Lệnh holdout | PF | Return | DD đóng lệnh |",
        "|---|---:|---:|---:|---:|"]
    for row in crossyear.itertuples():
        pf = f"{row.profit_factor:.2f}" if pd.notna(row.profit_factor) else "N/A"
        lines.append(f"| {row.case} | {row.trades} | {pf} | {row.return_percent:+.2f}% | {row.max_closed_trade_drawdown_percent:.2f}% |")
    lines += ["", "## D1: ứng viên ưu tiên theo mục tiêu drawdown thấp", "",
        f"Ứng viên theo quy tắc ở dưới: `{preferred}`. Không coi đây là lựa chọn scalping.", "",
        "Sàng lọc riêng các ca D1 có phí giữ 3% hoặc 8%/năm: CAGR dương ở mọi ca, DD đóng ngày không quá 10%; xếp hạng bằng CAGR thấp nhất chia DD cao nhất qua hai nguồn và hai cửa sổ. Hai cửa sổ từ 2018 và 2024 giao nhau; chỉ đánh giá độ nhạy, không cộng thành các fold độc lập.", "",
        "| Chiến lược D1 | CAGR thấp nhất | DD ngày cao nhất | Đạt |",
        "|---|---:|---:|---|"]
    for row in daily_table.itertuples():
        lines.append(f"| {row.strategy} | {row.minimum_cagr_percent:.2f}% | {row.max_daily_close_dd_percent:.2f}% | {'Có' if row.qualifies else 'Không'} |")
    lines += ["", "## Giới hạn và quyết định", "",
        "Không có chiến lược tốt nhất tuyệt đối được suy ra từ tập này. Donchian D1 là ứng viên phù hợp hơn nếu chấp nhận giữ nhiều ngày và ưu tiên drawdown thấp; scalping chưa chọn được bản đủ cơ sở để nâng lên mặc định. Không thay cấu hình live trong phép đánh giá.",
        "Các số liệu là mô phỏng: chưa xác minh phí/swap broker, không tính lot tối thiểu, margin và thao tác thực tế. Intraday dùng OHLC với pending một phút, khác live 15 giây; DD chỉ đo khi đóng lệnh. D1 có phí giữ giả định và DD đóng ngày, nên không xếp chung return/DD của D1 và M1.",
        "Phạm vi gồm năm ứng viên intraday đồng điều kiện và tám phương pháp D1 đã có. Các bản ORB phiên gốc, regime và Donchian M1 đã kiểm tra bằng bộ quy tắc/chi phí khác, không trộn vào bảng đồng điều kiện. Xem các báo cáo nguồn để biết chúng cũng chưa chứng minh độ bền scalping qua các giai đoạn.",
        "Dữ liệu đã xem nhiều lần nên có rủi ro chọn mẫu. Cần khóa quy tắc và theo dõi dữ liệu demo mới trước khi khẳng định hiệu quả; không dùng kết quả mô phỏng làm lịch sử Kelly thực tế.", "",
        "## Tái lập", "", "```powershell",
        ".\\venv\\Scripts\\python.exe -u -m scripts.backtest_scalper_alternatives --years 2024 2025 --strategies session_engulfing --output reports/session_engulfing_crossyear",
        ".\\venv\\Scripts\\python.exe -m scripts.select_research_strategy", "```", "",
        "Nguồn: `reports/scalper_alternatives/`, `reports/session_engulfing/`, `reports/session_engulfing_crossyear/`, `reports/published_strategies/`. JSON kết luận và hash CSV đầu vào: `reports/strategy_selection/selection.json`.", "",
        "Đọc thêm: [scalping đồng điều kiện](SCALPER_ALTERNATIVES_BACKTEST.md), [quy tắc engulfing](SESSION_ENGULFING_BACKTEST.md), [D1 và nguồn nghiên cứu](PUBLISHED_STRATEGIES_CHECK.md), [ORB phiên](SCALPING_CANDIDATES_CHECK.md), [các bản regime](MULTISOURCE_BACKTEST_RESULTS.md), [Donchian M1](DONCHIAN_M1_BACKTEST.md).", ""]
    Path("docs/STRATEGY_SELECTION.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(dict(scalping=result["scalping_selected"], daily=preferred)))
    print(scalpers.to_string(index=False))
    print(crossyear[["case", "trades", "return_percent"]].to_string(index=False))


if __name__ == "__main__":
    main()
