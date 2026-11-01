# Thử chiến lược M1 nhiều lệnh hơn ORB

Ngày chạy: 01/11/2026. So sánh ORB5 với ba bản pullback có sẵn, không tối ưu lại tham số.

## Holdout sau chi phí giả định

| Dữ liệu/kịch bản | Chiến lược | Lệnh | Win rate | PF | Return | DD đóng lệnh |
|---|---|---:|---:|---:|---:|---:|
| mt5_2026_09_10_fee | orb5_mtf | 3 | 100.0% | N/A | +2.98% | 0.00% |
| mt5_2026_09_10_fee | pullback | 108 | 25.9% | 0.67 | -12.69% | 15.91% |
| mt5_2026_09_10_fee | m5_m1 | 157 | 26.8% | 0.68 | -17.08% | 19.80% |
| mt5_2026_09_10_fee | m5_m1_quality | 135 | 25.9% | 0.67 | -15.62% | 18.39% |
| mt5_2026_09_10_stress | orb5_mtf | 3 | 100.0% | N/A | +2.98% | 0.00% |
| mt5_2026_09_10_stress | pullback | 107 | 26.2% | 0.67 | -12.25% | 15.48% |
| mt5_2026_09_10_stress | m5_m1 | 154 | 26.6% | 0.68 | -17.04% | 19.75% |
| mt5_2026_09_10_stress | m5_m1_quality | 132 | 25.8% | 0.66 | -15.58% | 18.34% |
| histdata_2026_fee | orb5_mtf | 10 | 20.0% | 0.28 | -2.63% | 3.58% |
| histdata_2026_fee | pullback | 357 | 32.5% | 0.90 | -12.27% | 13.31% |
| histdata_2026_fee | m5_m1 | 613 | 34.4% | 0.96 | -8.83% | 17.96% |
| histdata_2026_fee | m5_m1_quality | 521 | 33.2% | 0.91 | -14.70% | 18.92% |
| histdata_2026_stress | orb5_mtf | 8 | 12.5% | 0.01 | -3.11% | 3.11% |
| histdata_2026_stress | pullback | 133 | 29.3% | 0.72 | -12.31% | 13.04% |
| histdata_2026_stress | m5_m1 | 226 | 32.3% | 0.82 | -13.07% | 15.04% |
| histdata_2026_stress | m5_m1_quality | 191 | 30.9% | 0.79 | -13.05% | 13.91% |

Cả ba bản thay thế đều tăng số lệnh nhưng âm trên holdout ở cả hai nguồn và cả hai mức spread. Chưa chọn bản nào thay ORB mặc định.

## Quy tắc và cách đọc

- `pullback`: M1 hồi/vượt lại EMA21, màu nến/RSI/ADX xác nhận; M5 EMA9/21 và M15 close/EMA200 đồng hướng.
- `m5_m1`: cùng xác nhận M1, M5 chọn hướng; M15 chỉ là bối cảnh. `m5_m1_quality` thêm độ dốc/tách EMA M5 và giới hạn đuổi giá M1.
- Các bản pullback không giới hạn một tín hiệu đầu phiên như ORB. Tất cả vẫn dùng bộ lọc spread, nến bất thường và tính hợp lệ dữ liệu.
- MT5: 50.000 nến M1 tháng 09–10/2026, spread lịch sử nhân 0,001. HistData 2026: 286.270 nến, spread giả định 0,24; hai nguồn trùng giai đoạn, không độc lập.
- `fee`: commission khứ hồi giả định 0,10 đơn vị giá; `stress`: cùng phí, spread tăng 50%. Cả hai có slippage bất lợi 0,002 mỗi chiều. Chưa xác minh phí broker, chưa tính swap.
- Mỗi nguồn làm ấm 3.300 nến rồi chia thời gian 70/30. Reset vốn 10.000 USD riêng mỗi phần; risk 0,5% mỗi lệnh, một vị thế, lot liên tục. Return là của phần kiểm tra, không phải theo năm.
- Dùng cùng hàm future_entry với terminal; chờ phá high/low nến tín hiệu. Mô phỏng OHLC chờ một phút, khác live 15 giây; SL trước khi không rõ thứ tự chạm SL/TP. Thoát sau tối đa 120 nến hoặc cuối phần; gap thoát ở open kế tiếp.
- Chưa mô phỏng Kelly, lot tối thiểu, margin, độ trễ, kiểm tra RR ròng của bước sizing broker hoặc thao tác Enter. Chỉ báo tích lũy có thể khác cửa sổ làm ấm terminal. Đây là so sánh nghiên cứu, không phải replay chính xác toàn bộ vận hành live.
- Drawdown chỉ đo khi đóng lệnh; thống kê gap/đường giá mơ hồ ở JSON. Cờ observed_paths_complete trong chế độ OHLC không xác nhận đầy đủ tick.
- Dữ liệu đã được dùng trong các thử nghiệm trước; holdout không phải mẫu độc lập mới. Không đổi chiến lược mặc định chỉ vì nhiều lệnh hơn.

Đã đối chiếu 12693 dòng giao dịch với số lệnh, tổng R, equity lũy kế, chi phí từng lệnh, thứ tự vào/ra và mốc holdout. 57 bài kiểm tra chiến lược/mô phỏng đạt.

## Tái lập

```powershell
.\venv\Scripts\python.exe -u -m scripts.backtest_scalper_alternatives
.\venv\Scripts\python.exe -m scripts.report_scalper_alternatives
```

Dữ liệu từng lệnh, summary.csv và JSON chứa tham số/hash nguồn/mã nằm trong `reports/scalper_alternatives/`.
