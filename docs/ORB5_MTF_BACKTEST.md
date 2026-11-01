# Backtest ORB5 MTF, xác nhận M1

Ngày kiểm tra: 01/11/2026. Mã `orb5_mtf_m1_v1`. Kết quả chưa chứng minh lợi thế dương ổn định hoặc ít lỗ nhất. Không đổi tham số sau khi xem kết quả; không đặt lệnh.

## Kết quả phần kiểm tra cuối

Dùng 3.300 nến làm ấm rồi chia 70/30 theo thời gian riêng từng nguồn/năm. Mỗi phần reset vốn 10.000 USD, rủi ro cố định 0,5% mỗi lệnh, lot liên tục. Return là của phần kiểm tra, không phải lợi nhuận năm.

| Dữ liệu | Lệnh | Win rate | PF | Return | DD đóng lệnh |
|---|---:|---:|---:|---:|---:|
| MT5 09–10/2026 | 3 | 100% | Không xác định | +2,98% | 0% |
| HistData 2024 | 5 | 40% | 1,26 | +0,26% | 0,51% |
| HistData 2025 | 18 | 38,89% | 0,89 | −0,64% | 3,26% |
| HistData 2026 | 10 | 20% | 0,28 | −2,63% | 3,58% |

Khi tăng spread 50%, return holdout lần lượt +2,98%, +0,45%, −2,50%, −3,11%. Số lệnh thay đổi do bộ lọc spread loại thêm tín hiệu, nên không so sánh như cùng một tập lệnh. Không dùng mức lỗ thấp hơn bản khác để suy ra lợi thế: số lệnh và thời gian giữ khác nhau.

## Cách mô phỏng và giới hạn

- Giữ quy tắc ORB5 09:30 New York có DST; chỉ lần đóng M1 đầu tiên ngoài biên được xét, M5 EMA9/21 và M15 close/EMA200 phải đồng hướng. Dựng khung hoàn chỉnh, chỉ lấy nến đóng trước quyết định. Bộ lọc tăng tốc chỉ chọn ứng viên; hàm predict vẫn kiểm tra đầy đủ.
- Dùng cùng `future_entry` của terminal: sau xác nhận M1, còn cần giá chạm stop-entry ngoài high/low nến tín hiệu; không giả định mua/bán ngay giá close. TP kế hoạch được tính lại theo entry 2R.
- MT5: 50.000 nến, spread lịch sử nhân point 0,001. HistData: 995.813 nến 2024–2026, spread giả định 0,24. Commission khứ hồi giả định 0,10 đơn vị giá, slippage bất lợi 0,002 mỗi chiều; chưa xác minh biểu phí broker, chưa tính swap.
- Mô phỏng OHLC cho lệnh chờ tồn tại một phút, khác thời hạn 15 giây của terminal. Nếu chạm cả SL/TP thì tính SL trước; thoát tối đa 120 nến hoặc cuối phần kiểm tra. Terminal không tự quản lý lệnh/thoát sau 120 nến, nên đây là giả định nghiên cứu bổ sung.
- Chỉ báo backtest được tính trên lịch sử tích lũy; terminal lấy cửa sổ khoảng 5.000 M1, nên giá trị EMA làm ấm có thể khác. Chưa mô phỏng lot tối thiểu, margin, Kelly, độ trễ hoặc thao tác Enter thủ công.
- DD chỉ đo equity khi đóng lệnh, không phải drawdown intrabar. Hai lệnh holdout HistData 2026 gặp gap dữ liệu, thoát tại open kế tiếp quan sát được.
- Các nguồn có giai đoạn trùng nhau, dữ liệu đã dùng trong các thử nghiệm trước; phần cuối không phải mẫu độc lập mới. Mẫu MT5 ba lệnh không đủ kết luận.

## Kiểm tra tick

Đã replay bid/ask có sẵn trên 10.000 nến từ 20/10 đến 29/10/2026, lệnh chờ hết hạn trước mốc 15 giây, cùng phí/slippage ở trên. Development có 3 tín hiệu, 1 lệnh khớp, +1,951R; holdout không có tín hiệu/lệnh, return 0% không chứng minh hiệu quả. Không có cửa sổ tick hoặc vị thế không xác định trong lần chạy. Một lệnh có tick trùng millisecond nên thứ tự trong millisecond còn bất định.

## Tái lập

```powershell
.\venv\Scripts\python.exe -u -m scripts.backtest_orb_mtf
.\venv\Scripts\python.exe -u -m scripts.compare_scalper_strategies --csv reports/all_strategies_ticks/history.csv --point 0.001 --tick-size 0.001 --ticks-csv reports/all_strategies_ticks/ticks.csv.gz --strategies orb5_mtf --fee-price 0.10 --output reports/orb5_mtf_ticks
```

Kết quả từng lệnh, JSON tham số và hash dữ liệu: `reports/orb5_mtf/`; tick: `reports/orb5_mtf_ticks/`. Tổng hợp: `reports/orb5_mtf/summary.csv`. 30 bài kiểm tra ORB, bộ mô phỏng và tick replay đã đạt.
