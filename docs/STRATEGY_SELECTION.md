# Chọn chiến lược từ dữ liệu đã có

Ngày đánh giá: 01/11/2026.

## Scalping: chưa có ứng viên đạt

So sánh năm ứng viên trên cùng bốn ca: MT5 09–10/2026 và HistData 2026, mỗi nguồn có spread gốc và tăng 50%, cùng phí giả định 0,10 và slippage 0,002 mỗi chiều. Cùng risk 0,5%, chia 70/30, warm-up 3.300 M1, reset vốn 10.000 USD mỗi phần. Không gộp các nguồn trùng thời kỳ thành mẫu độc lập.

Quy tắc sàng lọc lần này: mỗi ca có ít nhất 30 lệnh, kỳ vọng R và return dương, PF > 1 ở cả bốn ca. Mốc 30 chỉ là ngưỡng thực dụng, không chứng minh ý nghĩa thống kê. Đây là đánh giá lại dữ liệu đã xem, không phải tiêu chí được đăng ký trước hay kiểm định ngoài mẫu độc lập.

| Chiến lược | Ít lệnh nhất/ca | Kỳ vọng R xấu nhất | Return xấu nhất | DD đóng lệnh cao nhất | Đạt |
|---|---:|---:|---:|---:|---|
| m5_m1 | 154 | -0.238 | -17.08% | 19.80% | Không |
| pullback | 107 | -0.247 | -12.69% | 15.91% | Không |
| m5_m1_quality | 132 | -0.252 | -15.62% | 18.92% | Không |
| orb5_mtf | 3 | -0.787 | -3.11% | 3.58% | Không |
| session_engulfing | 2 | -1.000 | -1.00% | 6.92% | Không |

Thứ tự bảng chỉ theo kỳ vọng R trong ca xấu nhất; không phải chứng minh chiến lược đứng đầu có lợi thế. Ngay cả bỏ điều kiện 30 lệnh, các ứng viên vẫn không đạt vì có ca kỳ vọng âm.

## Bổ sung engulfing trên 2024–2025

Giữ nguyên mọi tham số từ lần thử 2026; không tìm lại ngưỡng để sửa kết quả. Đây là kiểm tra độ ổn định thêm, chưa phải dữ liệu thị trường mới.

| Ca | Lệnh holdout | PF | Return | DD đóng lệnh |
|---|---:|---:|---:|---:|
| histdata_2024_fee | 10 | 1.89 | +2.22% | 1.99% |
| histdata_2024_stress | 0 | N/A | +0.00% | 0.00% |
| histdata_2025_fee | 47 | 1.26 | +3.65% | 6.05% |
| histdata_2025_stress | 6 | 3.70 | +2.72% | 0.50% |

## D1: ứng viên ưu tiên theo mục tiêu drawdown thấp

Ứng viên theo quy tắc ở dưới: `donchian55_20`. Không coi đây là lựa chọn scalping.

Sàng lọc riêng các ca D1 có phí giữ 3% hoặc 8%/năm: CAGR dương ở mọi ca, DD đóng ngày không quá 10%; xếp hạng bằng CAGR thấp nhất chia DD cao nhất qua hai nguồn và hai cửa sổ. Hai cửa sổ từ 2018 và 2024 giao nhau; chỉ đánh giá độ nhạy, không cộng thành các fold độc lập.

| Chiến lược D1 | CAGR thấp nhất | DD ngày cao nhất | Đạt |
|---|---:|---:|---|
| donchian55_20 | 1.32% | 5.64% | Có |
| buy_hold_1x | 7.35% | 43.14% | Không |
| turtle_s2_pyramid4 | 3.20% | 25.49% | Không |
| trend_1_3_12_weekly_vol40_cap2 | 3.21% | 64.85% | Không |
| turtle_s1_single | 0.11% | 5.91% | Có |
| tsmom12_vol40_cap2 | -1.36% | 76.51% | Không |
| turtle_s1_pyramid4 | -0.43% | 22.94% | Không |
| donchian20_10 | -0.36% | 8.43% | Không |

## Giới hạn và quyết định

Không có chiến lược tốt nhất tuyệt đối được suy ra từ tập này. Donchian D1 là ứng viên phù hợp hơn nếu chấp nhận giữ nhiều ngày và ưu tiên drawdown thấp; scalping chưa chọn được bản đủ cơ sở để nâng lên mặc định. Không thay cấu hình live trong phép đánh giá.
Các số liệu là mô phỏng: chưa xác minh phí/swap broker, không tính lot tối thiểu, margin và thao tác thực tế. Intraday dùng OHLC với pending một phút, khác live 15 giây; DD chỉ đo khi đóng lệnh. D1 có phí giữ giả định và DD đóng ngày, nên không xếp chung return/DD của D1 và M1.
Phạm vi gồm năm ứng viên intraday đồng điều kiện và tám phương pháp D1 đã có. Các bản ORB phiên gốc, regime và Donchian M1 đã kiểm tra bằng bộ quy tắc/chi phí khác, không trộn vào bảng đồng điều kiện. Xem các báo cáo nguồn để biết chúng cũng chưa chứng minh độ bền scalping qua các giai đoạn.
Dữ liệu đã xem nhiều lần nên có rủi ro chọn mẫu. Cần khóa quy tắc và theo dõi dữ liệu demo mới trước khi khẳng định hiệu quả; không dùng kết quả mô phỏng làm lịch sử Kelly thực tế.

## Tái lập

```powershell
.\venv\Scripts\python.exe -u -m scripts.backtest_scalper_alternatives --years 2024 2025 --strategies session_engulfing --output reports/session_engulfing_crossyear
.\venv\Scripts\python.exe -m scripts.select_research_strategy
```

Nguồn: `reports/scalper_alternatives/`, `reports/session_engulfing/`, `reports/session_engulfing_crossyear/`, `reports/published_strategies/`. JSON kết luận và hash CSV đầu vào: `reports/strategy_selection/selection.json`.

Đọc thêm: [scalping đồng điều kiện](SCALPER_ALTERNATIVES_BACKTEST.md), [quy tắc engulfing](SESSION_ENGULFING_BACKTEST.md), [D1 và nguồn nghiên cứu](PUBLISHED_STRATEGIES_CHECK.md), [ORB phiên](SCALPING_CANDIDATES_CHECK.md), [các bản regime](MULTISOURCE_BACKTEST_RESULTS.md), [Donchian M1](DONCHIAN_M1_BACKTEST.md).
