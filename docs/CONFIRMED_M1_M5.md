# Nâng cấp xác nhận M1/M5 và chi tiết entry, SL, TP

Ngày 01/11/2026. Profile `scalping` hiện dùng `m1_m5_confirmed`, mã riêng `confirmed_rolling5_m1_m5_v1`. Đây là bản thử nghiệm nhằm cải thiện chất lượng tín hiệu; chưa xác nhận lợi nhuận live. Không lọc phiên, M15 chỉ làm bối cảnh, không tự gửi lệnh. Chạy không có profile vẫn giữ mặc định rolling M5/M15 trước đó.

## Điều kiện BUY

1. M5 EMA9 > EMA21, ADX14 ≥20 và EMA21 hiện tại cao hơn EMA21 ba nến M5 trước. Bốn nến dùng đo độ dốc phải liên tục.
2. Nến M1 đã đóng trên high của năm M1 trước ít nhất 0,1 ATR14; không dùng chính nến xác nhận để tính biên.
3. Nến M1 tăng, thân ≥40% toàn bộ high–low; close cách EMA21 M1 không quá 1,5 ATR.
4. Có spread, spread ≤0,1 ATR M1 và biên nến xác nhận ≤2,5 ATR. Dữ liệu OHLC, timestamp, tính liên tục và đồng bộ phải hợp lệ.

SELL đối xứng: M5 giảm, độ dốc giảm, M1 đóng dưới low năm nến trước với thân giảm đủ lớn. Các ngưỡng là giả thuyết cố định trước phép so sánh, chưa được chứng minh tối ưu.

## Entry, SL và TP

| Mức | BUY | SELL |
|---|---|---|
| Entry có điều kiện | Ask phải chạm BUY STOP ở max(Ask hiện tại + khoảng đệm broker; high M1 xác nhận + spread + tick), làm tròn lên tick | Bid phải chạm SELL STOP ở min(Bid hiện tại − khoảng đệm broker; low M1 xác nhận − tick), làm tròn xuống tick |
| SL cấu trúc | Low của 5 M1 trước −0,1 ATR, làm tròn xuống tick và thỏa khoảng cách broker | High của 5 M1 trước +0,1 ATR, làm tròn lên tick và thỏa khoảng cách broker |
| Khoảng rủi ro giá R | Entry − SL | SL − Entry |
| TP toàn bộ | Entry +2R, làm tròn lên tick | Entry −2R, làm tròn xuống tick |

Khoảng đệm broker là max(tick-size; trade_stops_level × point). 2R là kế hoạch trước commission/slippage; bước sizing broker vẫn yêu cầu R:R ròng ít nhất 1,5 khi đủ điều kiện tính lot. Không hạ TP để làm đẹp win rate. Không dùng xác suất dự báo close sau 5 phút làm xác suất TP trước SL.

Ví dụ giả định BUY, không phải giá thị trường hiện tại: high nến xác nhận 4.001,000, spread 0,240, tick 0,001, Ask hiện tại thấp hơn mốc phá high và không bị khoảng cách broker chi phối; entry xấp xỉ 4.001,241. Nếu low năm nến trước 3.999,000 và ATR=1,000 thì SL khoảng 3.998,900, R khoảng 2,341 và TP khoảng 4.005,923. Làm tròn thực tế có thể chênh một tick. Bot tính giá cụ thể từ quote và thông số broker khi có setup.

Màn hình có bảng giá entry/SL/TP, khoảng cách Entry–SL/Entry–TP và panel **Chi tiet Entry / SL / TP** giải thích nến xác nhận, biên cấu trúc và cách tính. Khi WAIT, không tạo giá entry giả. Khi có lot, hiển thị mức lỗ ước tính tại SL và lợi nhuận ròng ước tính tại TP; các mức này vẫn có thể khác khi gap/trượt giá.

Ảnh chụp kế hoạch hết hạn theo mốc hiển thị (tối đa 15 giây từ quote hoặc 180 giây từ mở nến). Hết hạn cần phân tích lại; nếu bạn đã đặt pending thủ công thì phải tự kiểm tra/hủy trên MT5, bot không hủy hoặc sửa lệnh. Không dời SL xa hơn để giữ lệnh thua.

## So sánh trên dữ liệu đã lưu

50.000 M1 MT5, 10/09–30/10/2026; làm ấm 3.300 nến, phần còn lại chia 70/30 thời gian. Số dưới đây thuộc holdout 30%, vốn ảo đầu phần 10.000 USD, risk 0,5% mỗi lệnh, lot liên tục. Phí khứ hồi giả định 0,10 đơn vị giá, slippage bất lợi 0,002 mỗi chiều, RR kế hoạch ròng ≥1,5. Chưa xác minh phí/swap broker.

| Kịch bản | Bản | Lệnh | Win rate | PF | Return | DD đóng lệnh |
|---|---|---:|---:|---:|---:|---:|
| Spread lịch sử | M1/M5 trước | 273 | 32,60% | 0,82 | −15,80% | 21,51% |
| Spread lịch sử | Có xác nhận mới | 80 | 36,25% | 1,003 | −0,10% | 8,34% |
| Spread ×1,5 | M1/M5 trước | 269 | 31,60% | 0,78 | −18,58% | 24,87% |
| Spread ×1,5 | Có xác nhận mới | 68 | 39,71% | 1,16 | +3,12% | 6,34% |

Win rate quan sát ở spread gốc tăng 3,65 điểm phần trăm, đổi lại số lệnh giảm. Spread tăng còn loại thêm tín hiệu qua bộ lọc 0,1 ATR, nên hai kịch bản không có cùng tập lệnh; return cao hơn không có nghĩa chi phí cao làm chiến lược tốt hơn.

**Bản gốc phí vẫn âm nhẹ; chưa chứng minh lợi thế ổn định.** PF lớn hơn 1 rất ít nhưng equity lũy kế vẫn có thể âm. Mẫu chỉ một broker/giai đoạn đã được xem trước; chưa có kiểm chứng riêng bản này trên HistData nhiều năm, tick bid/ask hoặc demo mới. Chưa kết luận cải thiện win rate có ý nghĩa thống kê. Hai lệnh bản mới mỗi kịch bản gặp gap dữ liệu, một lệnh có đường giá nến mơ hồ.

Mô phỏng OHLC giữ pending một phút, khác hạn kế hoạch 15 giây của assistant; ưu tiên SL khi không rõ thứ tự, thoát sau tối đa 120 nến hoặc cuối phần, gap thoát ở open tiếp theo. DD chỉ đo ở đóng lệnh. Chưa mô phỏng lot tối thiểu, margin, Kelly hoặc thao tác thực tế. Không dùng sổ lệnh mô phỏng làm lịch sử Kelly.

## Chạy cấu hình nâng cấp

```powershell
.\venv\Scripts\python.exe run_mt5_assistant.py --symbol XAUUSD --profile scalping --forecast-model reports/m1_forecast/model.json --color always
```

Phần dự báo 5 phút là tùy chọn hiển thị, chưa lọc BUY/SELL của chiến lược. Có thể bỏ `--forecast-model` nếu chỉ cần entry/SL/TP. Dùng `--strategy m1_m5_breakout` nếu muốn đối chiếu bản cũ; không dùng cùng `--profile`. Kelly có mã riêng nên chưa đủ lịch sử thì không đề xuất lot.

Tái lập so sánh:

```powershell
.\venv\Scripts\python.exe -u -m scripts.compare_scalper_strategies --csv reports/market_data/mt5/history.csv --point 0.001 --tick-size 0.001 --strategies m1_m5_breakout m1_m5_confirmed --fee-price 0.10 --min-net-rr 1.5 --output reports/confirmed_m1_m5
.\venv\Scripts\python.exe -u -m scripts.compare_scalper_strategies --csv reports/market_data/mt5/history.csv --point 0.001 --tick-size 0.001 --strategies m1_m5_breakout m1_m5_confirmed --fee-price 0.10 --min-net-rr 1.5 --spread-multiplier 1.5 --output reports/confirmed_m1_m5_stress
```

Các thư mục chứa JSON tham số/hash lúc chạy và từng giao dịch. Sau lần chạy spread gốc đã thêm trường giải thích biên/SL cho màn hình, không đổi quy tắc tín hiệu hay công thức giá. 68 bài kiểm tra đạt, gồm bộ lọc mới, giá entry/SL/TP làm tròn theo hai hướng, luồng assistant và backtest.
