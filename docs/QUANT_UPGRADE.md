# Nâng cấp kiểm chứng và lựa chọn M1/M5

Ngày 01/11/2026. Đã triển khai mã và kiểm tra trên dữ liệu XAUUSD có sẵn; chưa kiểm chứng BTCUSD và chưa chứng minh lợi nhuận live. Không thêm cơ chế tự đặt lệnh.

## Thay đổi

- Thêm `--strategy m1_m5_breakout`, mã `rolling5_m1_m5_v1`: M1 đóng vượt high/low của 5 nến trước, màu nến cùng hướng và M5 EMA9/21 đồng hướng. M15 chỉ là bối cảnh; không lọc phiên. Đây là lựa chọn riêng, không ghi đè lịch sử Kelly của bản M5/M1 pullback hoặc rolling M5/M15.
- Giữ các kiểm tra nến đóng, dữ liệu đồng bộ, OHLC hợp lệ, spread tối đa 0,15 ATR, nến tối đa 3 ATR. SL ngoài biên đối diện thêm 0,1 ATR; hàm lập kế hoạch dùng stop-entry ngoài nến xác nhận, TP theo entry 2R.
- Backtest có `--min-net-rr`: trước khi mô phỏng khớp, loại kế hoạch không đạt R:R sau phí và slippage. Với hướng d, giá kích hoạt E, SL S, TP T và chi phí C = phí khứ hồi + 2 × slippage: risk = d(E−S)+C, reward = d(T−E)−C. Không dùng giá tương lai để lọc.
- Mặc định `--min-net-rr 0` giữ hành vi nghiên cứu cũ; dùng `1.5` để kiểm tra gần hơn với điều kiện RR ở bước sizing của assistant. Đây là kiểm tra giá kế hoạch, chưa bảo đảm RR khi có gap thực tế và chưa mô phỏng đầy đủ sizing broker.
- JSON có `cost_rejected_signals`. Báo cáo mới hiển thị số tín hiệu bị loại do chi phí và trạng thái đánh giá: `INCOMPLETE_DATA`, `INSUFFICIENT_SAMPLE`, `UNDEFINED_METRICS`, `NO_OBSERVED_EDGE` hoặc `REQUIRES_STRESS_AND_FORWARD_TEST`.
- Thiếu tick/vị thế chưa xác định ở bất kỳ phần nào sẽ ưu tiên trạng thái `INCOMPLETE_DATA`, kể cả phần đã đóng đang dương. Không tự nâng chiến lược thành mặc định. Ngưỡng 30 lệnh chỉ là sàng lọc thực dụng, không phải ý nghĩa thống kê.

## Kiểm chứng sau nâng cấp

50.000 nến MT5 10/09–30/10/2026, làm ấm 3.300 M1, chia phần còn lại 70/30 theo thời gian. Phí giả định 0,10 đơn vị giá khứ hồi, slippage bất lợi 0,002 mỗi chiều, risk 0,5% vốn ảo, vốn đầu mỗi phần 10.000 USD. Chưa xác minh biểu phí/swap broker, chưa tính swap, lot tối thiểu hoặc margin.

| Mẫu nến holdout | Lệnh | Return | Kết luận |
|---|---:|---:|---|
| Rolling M5/M15 hiện tại | 184 | −5,85% | NO_OBSERVED_EDGE |
| M1/M5 mới | 273 | −15,80% | NO_OBSERVED_EDGE |
| Rolling M5/M15, spread ×1,5 | 183 | −6,69% | NO_OBSERVED_EDGE |
| M1/M5 mới, spread ×1,5 | 269 | −18,58% | NO_OBSERVED_EDGE |

Bộ lọc RR 1,5 không loại tín hiệu nào trong các lần chạy này; không có bằng chứng rằng riêng bộ lọc này cải thiện lợi nhuận. M1/M5 tăng số lệnh nhưng lỗ nhiều hơn; chưa chọn thay mặc định `orb5_mtf` (hiện là rolling, không phải ORB mở cửa phiên).

Tick replay M1/M5 trên mẫu 10.000 nến 20/10–29/10/2026: development đóng được 5 lệnh, holdout đóng được 7 lệnh. Phần holdout đã xác định ghi nhận +0,44%, nhưng mỗi phần đều có một vị thế khớp chưa xác định được kết quả do thiếu phủ tick. Vì vậy **không biết equity cuối thực tế và không dùng +0,44% để xác nhận lợi thế**. Sáu trong bảy lệnh holdout đã đóng có tick trùng millisecond, còn bất định về thứ tự trong millisecond.

Tick replay dùng quote bid/ask và hạn pending 15 giây. Mô phỏng nến dùng pending một phút, SL trước khi không rõ đường giá; giới hạn giữ 120 nến, DD đo khi đóng lệnh. Hai mẫu nến/tick có thời gian và phần chia khác nhau nên không so trực tiếp số return của chúng. Dữ liệu đã được xem trước, chưa phải forward test độc lập mới.

## Chạy thử thủ công

```powershell
.\venv\Scripts\python.exe run_mt5_assistant.py --symbol XAUUSD --strategy m1_m5_breakout --color always
```

Dùng đúng tên symbol tại broker. Kelly vẫn yêu cầu lịch sử giao dịch thật/đã đóng đúng symbol và mã chiến lược; thiếu lịch sử thì không đề xuất lot. Không lấy lệnh backtest làm lịch sử Kelly.

## Tái lập backtest

```powershell
.\venv\Scripts\python.exe -u -m scripts.compare_scalper_strategies --csv reports/market_data/mt5/history.csv --point 0.001 --tick-size 0.001 --strategies orb5_mtf m1_m5_breakout --fee-price 0.10 --min-net-rr 1.5 --output reports/quant_upgrade_mt5
.\venv\Scripts\python.exe -u -m scripts.compare_scalper_strategies --csv reports/market_data/mt5/history.csv --point 0.001 --tick-size 0.001 --strategies orb5_mtf m1_m5_breakout --fee-price 0.10 --min-net-rr 1.5 --spread-multiplier 1.5 --output reports/quant_upgrade_mt5_stress
.\venv\Scripts\python.exe -u -m scripts.compare_scalper_strategies --csv reports/all_strategies_ticks/history.csv --point 0.001 --tick-size 0.001 --ticks-csv reports/all_strategies_ticks/ticks.csv.gz --strategies m1_m5_breakout --fee-price 0.10 --min-net-rr 1.5 --output reports/quant_upgrade_ticks
```

Mỗi thư mục có report JSON, nguồn dữ liệu/hash mã, sổ lệnh và báo cáo Markdown; bản tick có execution_events ghi vị thế UNKNOWN. Trạng thái đánh giá được áp dụng sau mô phỏng trong lần chạy đầu và lưu hash riêng, không sửa lợi nhuận gốc.

67 bài kiểm tra đạt, gồm tương thích luồng assistant, M1/M5 không phụ thuộc M15, bộ lọc chi phí trước khớp và không xác nhận kết quả tick thiếu dữ liệu.
