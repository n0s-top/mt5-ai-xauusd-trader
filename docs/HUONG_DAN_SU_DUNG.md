# Hướng dẫn sử dụng bot hỗ trợ vào lệnh

Mặc định luôn hiện entry/SL/TP **tham khảo** khi WAIT và dữ liệu còn hợp lệ. Có hướng M5 thì hiện một kịch bản theo hướng đó; chưa có hướng rõ thì hiện hai kịch bản BUY/SELL độc lập, không phải đặt đồng thời. Các kịch bản WAIT giữ nhãn `REFERENCE_ONLY`, không đề xuất lot và không biến thành tín hiệu vào lệnh. Dữ liệu lỗi, thiếu lịch sử/ATR hoặc snapshot hết hạn thì không dựng giá tham khảo.

Profile `scalping` đã nâng lên **M1/M5 có xác nhận** (`m1_m5_confirmed`), kèm giải thích cụ thể entry, SL, TP. Xem [quy tắc, ví dụ giá và kết quả so sánh](CONFIRMED_M1_M5.md). Win rate holdout MT5 tăng từ 32,60% lên 36,25%, nhưng return sau phí vẫn −0,10%; chưa chứng minh lợi nhuận ổn định.

## Dự báo 5 phút với điểm vào M1

Đã có [mô hình dự báo UP/FLAT/DOWN trong 5 phút](M1_FORECAST.md), hiển thị bằng tùy chọn `--forecast-model`. Đây là xác suất hướng giá, không phải xác suất thắng lệnh; mức cải thiện trên dữ liệu kiểm tra còn nhỏ nên chỉ dùng nghiên cứu.

```powershell
.\venv\Scripts\python.exe run_mt5_assistant.py --symbol XAUUSD --profile scalping --forecast-model reports/m1_forecast/model.json --color always
```

Nếu file mô hình chưa có, chạy `.\venv\Scripts\python.exe -m scripts.train_m1_forecast` trước. Phần dự báo không tự tạo hoặc gửi lệnh.

## Hai cấu hình theo lựa chọn của bạn

**1. Scalping XAUUSD M1/M5** — breakout 5 nến có xác nhận ADX/độ dốc M5, thân nến và giới hạn đuổi giá M1; không lọc phiên, M15 chỉ làm bối cảnh. Kelly chưa đủ lịch sử đúng mã mới thì không đề xuất lot. Bản này vẫn thử nghiệm: holdout MT5 sau chi phí giả định có 80 lệnh, win rate 36,25%, return −0,10%; chưa chứng minh lợi nhuận.

```powershell
.\venv\Scripts\python.exe run_mt5_assistant.py --symbol XAUUSD --profile scalping --color always
```

**2. Theo xu hướng D1** — Donchian 55/20, fixed sizing, risk mặc định 0,5%, chỉ demo. Trong các ca có phí đã kiểm tra, CAGR thấp nhất khoảng 1,32%/năm và drawdown đóng ngày cao nhất 5,64%. Đây là số mô phỏng theo giả định chi phí, chưa xác nhận live.

```powershell
.\venv\Scripts\python.exe run_mt5_assistant.py --symbol XAUUSD --profile trend --color always
```

Chạy từng cấu hình khi cần; không dùng đồng thời `--profile` và `--strategy`. Hai cấu hình không cộng tín hiệu hay tự chuyển chế độ. Cả hai chỉ hỗ trợ thao tác thủ công, không gửi lệnh. Không truyền hai tùy chọn này sẽ dùng `m1_m5_confirmed`, giống profile `scalping`. Dùng tên symbol đúng tại broker.

Đã [nâng cấp lựa chọn M1/M5 và bộ kiểm chứng sau chi phí](QUANT_UPGRADE.md): thêm `--strategy m1_m5_breakout`, backtest có `--min-net-rr`, trạng thái đánh giá và kiểm tra tick thiếu dữ liệu. Kết quả mới vẫn chưa chứng minh lợi thế; giữ mặc định hiện tại. Có thể xem lệnh chạy thử và giới hạn trong báo cáo nâng cấp.

Bot mặc định dùng **breakout M1/M5 có xác nhận, không lọc phiên** (`m1_m5_confirmed`). M15 chỉ làm bối cảnh. Bạn đặt lệnh thủ công trong MT5; bot không tự gửi lệnh và không chạy phân tích nền. Holdout MT5 có win rate 36,25%, return −0,10% sau chi phí giả định; bản này vẫn thử nghiệm, chưa kiểm chứng BTCUSD. Các kết quả ORB v1 bên dưới không áp dụng cho mặc định mới.

### Tùy chọn cũ: breakout 5 nến MTF — không lọc phiên

```powershell
.\venv\Scripts\python.exe run_mt5_assistant.py --symbol XAUUSD --strategy orb5_mtf --color always
```

- Biên: high/low của 5 nến M1 liên tục trước nến xác nhận, không gồm chính nến xác nhận.
- Xét mọi giờ có dữ liệu hợp lệ, không chờ phiên New York, không giới hạn breakout đầu tiên mỗi ngày. Mỗi lần nhấn Enter là một ảnh chụp phân tích; lặp lại cùng nến có thể hiện cùng setup.
- BUY: M1 đóng trên biên và trên open, M5 EMA9 > EMA21, M15 close > EMA200. SELL đối xứng. Chỉ dùng nến đã đóng.
- SL ngoài biên đối diện thêm 0,1 ATR14 M1; TP kế hoạch theo 2R. Giá vào có điều kiện, chi phí và quy tắc broker tiếp tục được kiểm tra bởi bot.
- Bỏ qua khi thiếu nến, lệch khung, spread quá 0,15 ATR hoặc nến vượt 3 ATR. Không hiện kịch bản pullback thay cho ORB khi đang WAIT.
- Mã lịch sử riêng: `rolling5_mtf_m1_v2`; không dùng lịch sử Kelly của ORB v1. Mặc định dùng Kelly; chưa đủ lịch sử đúng mã thì không đề xuất lot. Có thể dùng `--sizing fixed --risk-percent 0.5` để tính lot theo mức rủi ro cố định.

Đây là rolling breakout, không còn biên mở cửa phiên. [Backtest ORB v1 ngày 01/11/2026](ORB5_MTF_BACKTEST.md) là kết quả lịch sử của quy tắc cũ; xem [backtest rolling mới](QUANT_UPGRADE.md) để đánh giá bản hiện tại. Sau khi sửa mã, thoát bot bằng `q` và chạy lại để áp dụng.

Đã [so sánh thêm ba bản pullback nhiều lệnh hơn](SCALPER_ALTERNATIVES_BACKTEST.md) trên cùng dữ liệu MT5 và HistData 2026, sau phí giả định và spread tăng 50%. Các bản có 108–157 lệnh holdout MT5 và 357–613 lệnh holdout HistData ở spread gốc, nhưng đều âm; chưa chọn thay ORB mặc định.

Đã viết [quy tắc và backtest H1/M5/M1 engulfing theo phiên](SESSION_ENGULFING_BACKTEST.md) từ ý tưởng scalping bạn cung cấp. Holdout HistData 2026 có 26 lệnh, +0,16% sau chi phí giả định; khi spread tăng 50% chỉ còn 2 lệnh, −1,00%. Bản này chỉ để nghiên cứu, chưa có bộ lọc DXY/tin tức/VWAP hoặc chốt từng phần; chưa thêm vào bot live.

Xem [đánh giá chọn chiến lược từ dữ liệu đã có](STRATEGY_SELECTION.md): nhóm scalping được so riêng theo kỳ vọng sau phí và độ bền khi tăng spread; nhóm D1 đánh giá riêng theo CAGR/drawdown. Donchian 55/20 D1 là ứng viên ưu tiên nếu chấp nhận giữ nhiều ngày và ưu tiên drawdown thấp. Đánh giá này không tự đổi chiến lược mặc định hoặc chứng minh lợi nhuận live.

## 1. Khởi động

Mở MetaTrader 5 trên máy, đăng nhập tài khoản demo và kiểm tra kết nối mạng. Chỉ chiến lược Donchian D1 có chặn tài khoản thật riêng; ORB là hỗ trợ phân tích thủ công.

Mở terminal tại thư mục dự án rồi chạy:

```powershell
.\venv\Scripts\python.exe run_mt5_assistant.py --color always
```

Môi trường hiện tại đã cài các thư viện cần thiết. Trên máy khác, cần Python 3.11 cùng các thư viện `MetaTrader5`, `TA-Lib`, `pandas`, `numpy` và `rich`.

Nếu broker dùng tên vàng khác, chỉ định đúng symbol:

```powershell
.\venv\Scripts\python.exe run_mt5_assistant.py --symbol XAUUSD --color always
```

Symbol mặc định là `XAUUSDc`. Bot lấy khoảng 5.000 nến M1 để dựng M5 và bối cảnh M15. Donchian D1 tùy chọn cần ít nhất 55 phiên D1 đã đóng.

## 2. Các phím điều khiển

Nhập lệnh rồi nhấn Enter:

| Thao tác | Kết quả |
| --- | --- |
| Chỉ nhấn **Enter** | Dọn màn hình, lấy giá mới và phân tích một lần |
| `c` | Dọn màn hình, không lấy giá |
| `h` | Xem trợ giúp |
| `l` | Xem tóm tắt nhật ký gần nhất, không lấy giá mới |
| `q` | Thoát bot |
| `Ctrl+C` | Dừng bot |

Sau mỗi lần phân tích, bot chờ thao tác tiếp theo. Giá trên màn hình không tự cập nhật. Nếu bạn sửa mã nguồn khi bot đang mở, hãy thoát bằng `q` rồi chạy lại.

## 3. Đọc kết quả

### Tùy chọn: Donchian 55/20 D1, chỉ demo

Chọn `--strategy donchian_55_20` để dùng bản D1 với fixed sizing và risk tối đa 0,5%. Bản D1 có kết quả dài hạn trên MT5/HistData vẫn dương trong ca tăng chi phí; chưa xác nhận lợi nhuận live. Đây là chiến lược theo xu hướng ngày. Xem [quy tắc và cách dùng](DONCHIAN_DEMO.md) và [bằng chứng backtest](PUBLISHED_STRATEGIES_CHECK.md).

```powershell
.\venv\Scripts\python.exe run_mt5_assistant.py --symbol XAUUSD --strategy donchian_55_20 --color always
```

### Tùy chọn cũ: M5 chọn hướng, M1 vào lệnh

Bản `m5_m1` được giữ để đối chiếu, không còn là mặc định. Chọn rõ bằng:

```powershell
.\venv\Scripts\python.exe run_mt5_assistant.py --strategy m5_m1 --color always
```

Mã chiến lược là `m5_m1_pullback_v1`. M5 EMA9 trên EMA21 chọn BUY, dưới chọn SELL;
M1 vẫn phải xác nhận nhịp hồi rồi đóng vượt lại EMA21, màu nến, RSI và ADX như
Pullback cũ. Giữ nguyên giới hạn spread 0,15 ATR, nến tối đa 3 ATR, SL/TP và
kiểm tra rủi ro. M15 trái hướng chỉ tạo cảnh báo, không chặn tín hiệu hoặc
kịch bản giá tham khảo; M15 không còn là một điều kiện đạt/chưa đạt để vào lệnh.

Đây là chiến lược cũ để đối chiếu, vẫn đang thử nghiệm và chưa có
bằng chứng lợi nhuận ngoài mẫu. Kelly không lấy lịch sử của bản khác.
Thêm giao dịch không bảo đảm tăng lợi nhuận. Nếu chưa có nhịp hồi
M1 hoặc các bộ lọc chi phí không đạt, bot vẫn WAIT.

Để tái lập phép thử cùng tick lịch sử đã lưu:

```powershell
.\venv\Scripts\python.exe -u -m scripts.compare_scalper_strategies --csv reports/scalper_ticks/history.csv --point 0.001 --tick-size 0.001 --ticks-csv reports/scalper_ticks/ticks.csv.gz --strategies pullback m5_m1 --output reports/m5_m1_comparison
```

Xem `reports/m5_m1_comparison/REPORT.md` và từng lệnh trong `trades.csv`.
Đây là cùng giai đoạn tick đã dùng cho các thử nghiệm trước, không phải tập
kiểm chứng độc lập mới. Kết quả vẫn chưa gồm commission/swap chưa cung cấp.

### Bộ lọc M5/M1 thử nghiệm

Thêm lựa chọn `--strategy m5_m1_quality`, mã `m5_m1_quality_pullback_v1`.
Bản này giữ điều kiện pullback, SL/TP và bộ lọc chi phí của M5/M1; chỉ phát tín hiệu
khi có spread, EMA21 M5 dốc cùng hướng so với 3 nến trước, EMA9/EMA21 M5 cách nhau
ít nhất 0,1 ATR M5 và giá đóng M1 cách EMA21 không quá 1 ATR M1. Cửa sổ đo độ dốc
phải liên tục. Bảng bộ lọc hiển thị điều kiện đạt/chưa đạt khi có setup nền.
Kelly và nhật ký dùng mã chiến lược riêng.

**Chưa được chọn thay mặc định.** Trên dữ liệu cục bộ 5.000 nến và 392.118 tick,
phần holdout của M5/M1 có 4 lệnh, tổng −1,098R; bản lọc có 2 lệnh, tổng −2,087R.
Khi spread tăng 50%, bản lọc không có lệnh khớp; không thể xem đó là lợi thế.
Mẫu rất nhỏ, chưa gồm commission/swap, dùng lại dữ liệu cũ và chưa phải kiểm chứng
độc lập. Các ngưỡng là giả thuyết kỹ thuật, chưa được tối ưu hay chứng minh hiệu quả.

Chạy thử để quan sát tín hiệu:

```powershell
.\venv\Scripts\python.exe run_mt5_assistant.py --strategy m5_m1_quality --color always
```

Tái lập so sánh với spread gốc; thêm `--spread-multiplier 1.5` và đổi `--output`
để kiểm tra spread tăng:

```powershell
.\venv\Scripts\python.exe -u -m scripts.compare_scalper_strategies --csv reports/scalper_ticks/history.csv --point 0.001 --tick-size 0.001 --ticks-csv reports/scalper_ticks/ticks.csv.gz --strategies m5_m1 m5_m1_quality --output reports/m5_m1_quality
```

Xem báo cáo tại `reports/m5_m1_quality/REPORT.md` và
`reports/m5_m1_quality_stress/REPORT.md`. Đây là tập dữ liệu khác về độ dài so với
`ALL_STRATEGIES_SELECTION.md`; không đối chiếu trực tiếp tổng R giữa hai báo cáo.

### Chiến lược thích nghi mới

Chọn `--strategy adaptive` để dùng mã `adaptive_trend_breakout_v1`; đây không còn là mặc định.
Đây là **bản thử nghiệm**, chưa có bằng chứng ngoài mẫu chứng minh tốt hơn bản cũ.
Nhãn này luôn hiển thị trong kết quả; các bài kiểm tra phần mềm không chứng minh lợi nhuận.

Các bộ lọc chung của bản mới:

- M15 và động lượng EMA9/EMA21 trên M5 cùng hướng.
- ADX M5 ít nhất 25; EMA21 M5 dốc cùng hướng so với 3 nến trước.
- EMA9 và EMA21 M5 cách nhau ít nhất 0,1 ATR M5.
- Giá M1 không cách EMA21 quá 1 ATR M1, để hạn chế đuổi giá.
- Có bid/ask; spread không vượt 0,1 ATR M1, nến không rộng quá 2,5 ATR M1.
- Các kiểm tra lịch sử, nến đóng, timestamp, OHLC và đồng bộ khung vẫn áp dụng.

Nếu bộ lọc đạt, bot ưu tiên setup **TREND_PULLBACK** theo quy tắc hồi EMA21 đã có.
Khi không có pullback, bot xét **TREND_BREAKOUT**: nến M1 đóng vượt đỉnh/đáy
20 nến trước ít nhất 0,1 ATR; tick volume đạt ít nhất 1,2 lần trung bình 20 nến
trước; màu nến, RSI và ADX M1 xác nhận cùng hướng. Nến tín hiệu không được dùng
để tính vùng breakout hoặc trung bình volume trước đó. Tick volume chỉ là số
tick do broker ghi nhận, không đại diện toàn bộ khối lượng giao dịch vàng.

Không đạt thì WAIT. Kịch bản tham khảo khi WAIT vẫn không phải lệnh được xác nhận.
SL vẫn dùng ATR và vùng swing; TP vẫn theo R:R, cùng các kiểm tra phí, trượt giá,
margin và tổng rủi ro đã mô tả. Chưa có thuật toán tối ưu điểm thoát mới được kiểm chứng.

Chạy bản mới:

```powershell
.\venv\Scripts\python.exe run_mt5_assistant.py --strategy adaptive --color always
```

Đối chiếu với bản pullback cũ:

```powershell
.\venv\Scripts\python.exe run_mt5_assistant.py --strategy pullback --color always
```

Nhật ký ghi riêng `strategy_id`, `setup_type` và các bộ lọc. Kelly chỉ đọc các
dòng có đúng mã chiến lược đang chọn; không lấy thành tích bản cũ để tính lot
cho bản mới. Các ngưỡng trên là lựa chọn kỹ thuật cần kiểm thử, chưa phải tham số
tối ưu được chứng minh trên dữ liệu broker của bạn.

| Màu / trạng thái | Ý nghĩa |
| --- | --- |
| Xanh lá / BUY | Hướng mua; TP cũng hiển thị xanh lá |
| Đỏ / SELL | Hướng bán; SL cũng hiển thị đỏ |
| Vàng / WAIT | Chưa đủ điều kiện vào lệnh |
| Đỏ / BLOCKED | Dữ liệu hoặc điều kiện kiểm tra không hợp lệ; đọc lý do |
| REVIEW | Có kịch bản đủ điều kiện để bạn xem xét, không phải xác nhận đã đặt lệnh |
| Xanh cyan | Giá kích hoạt và thông tin nổi bật |

Bot chỉ đưa một hướng ưu tiên khi xu hướng M15 và động lượng M5 đồng thuận. Nếu trái chiều hoặc chưa rõ, bot báo chờ và không chọn hướng tùy ý. Bảng chỉ báo cho biết cơ sở của kết quả, không phải xác suất thắng.

Khi `WAIT` nhưng có hướng ưu tiên, bot có thể hiển thị một kịch bản **tham khảo**. Điều này không đổi khuyến nghị chờ thành khuyến nghị vào lệnh.

Nếu spread hoặc biên độ nến vượt ngưỡng, bot vẫn hiển thị giá kích hoạt, SL, TP
tham khảo khi dữ liệu hợp lệ và M15/M5 cùng hướng. Lot sẽ là N/A, kèm lý do
đang chặn vào lệnh. Dữ liệu cũ/lỗi hoặc các khung trái hướng sẽ không được dùng
để tạo giá tham khảo tùy ý.

| Thông tin | Cách đọc |
| --- | --- |
| BID / ASK | Giá bán / mua hiện tại; spread là chênh lệch hai giá |
| Giá kích hoạt | Mức giá có điều kiện cho kịch bản BUY STOP hoặc SELL STOP |
| SL | Giá cắt lỗ |
| TP | Giá chốt lời |
| Risk : Reward | Tỷ lệ khoảng cắt lỗ và khoảng chốt lời |
| Lot đề xuất | Khối lượng theo phương pháp quản lý vốn đang chọn |
| Lot mô phỏng | Khối lượng giả định của kịch bản chưa đủ điều kiện; không phải Kelly |
| Lỗ ước tính tại SL | Ước tính bằng đồng tiền tài khoản, có giả định phí và trượt giá đã cấu hình |
| Margin ước tính | Ký quỹ cho khối lượng đang tính |
| Hết hạn | Thời điểm cần phân tích lại, hiển thị theo UTC+7 |

Với BUY, bán để đóng vị thế ở TP hoặc SL. Với SELL, mua lại để đóng vị thế. Đây không phải đề xuất mở thêm vị thế ngược chiều.

Kịch bản có thời hạn tối đa khoảng 15 giây và có thể ngắn hơn do tuổi dữ liệu. Nhấn Enter để kiểm tra lại khi hết hạn hoặc khi giá thay đổi. Giá mục tiêu là kịch bản có điều kiện, không bảo đảm thị trường sẽ chạm tới.

## 4. Lot và Kelly

### Đa khung thời gian và xác suất thắng

Mặc định bot chỉ dùng **M1/M5/M15**, không tải hay hiển thị H1/H4.
Nếu muốn xem lại bối cảnh khung lớn, thêm `--higher-timeframes`; khi đó bot đọc tối đa
300 nến đóng H1 và H4 từ MT5. Hai khung này là **bối cảnh**: BUY khi giá > EMA21 > EMA200,
SELL khi giá < EMA21 < EMA200; các trường hợp khác là WAIT. Nếu trái với hướng
đang xem, bot hiển thị cảnh báo đa khung. H1/H4 chưa thay đổi quy tắc vào lệnh
hoặc tự biến kịch bản tham khảo thành tín hiệu đã xác nhận.

Bảng H1/H4 có đỉnh/đáy 20 nến đóng để tham khảo vùng giá. Đây là biên độ lịch sử,
không phải dự đoán chắc chắn về hỗ trợ/kháng cự hay điểm thoát tối ưu.
Thiếu lịch sử, nến cũ, khoảng trống gần nhất hoặc timestamp không đúng mốc UTC
sẽ hiển thị UNAVAILABLE cho khung đó. Bot vẫn phân tích các khung hiện có;
không coi dữ liệu thiếu là đồng thuận. Lần tải đầu có thể chưa đủ nến, hãy
kiểm tra biểu đồ H1/H4 trong MT5 rồi nhấn Enter lại.

**Xác suất thắng của từng setup chưa được kiểm chứng**, nên bot không gán phần
trăm từ số chỉ báo đồng thuận. Nếu nhật ký Kelly đủ dữ liệu, bot hiển thị tỷ lệ
thắng lịch sử và khoảng Wilson 95% cho tỷ lệ đó. Khoảng này dựa trên mô hình
nhị thức với giả định về tính độc lập/ổn định, không bảo đảm xác suất giao dịch
kế tiếp; các giao dịch có thể phụ thuộc nhau và thị trường có thể đổi trạng thái.

Để thêm AI dự báo có cơ sở, cần bộ dữ liệu với nhãn đúng câu hỏi: TP chạm trước
SL trong thời hạn xác định, sau khi tính spread/phí/trượt giá. Cần chia tập theo
thời gian, tránh các nhãn giao dịch chồng lấn giữa train/test, đánh giá walk-forward,
hiệu chỉnh xác suất trên dữ liệu riêng và kiểm tra Brier score, log loss cùng
biểu đồ calibration trên tập chưa dùng huấn luyện. Chỉ tích hợp mô hình khi
có bằng chứng tốt hơn chiến lược hiện tại sau chi phí. Phần này là yêu cầu cho
bước huấn luyện tiếp theo, **chưa có mô hình mới được huấn luyện hoặc kích hoạt**.

Tham khảo: [Hiệu chỉnh xác suất — scikit-learn](https://scikit-learn.org/stable/modules/calibration.html),
[Đọc nến MT5 theo khung](https://www.mql5.com/en/docs/python_metatrader5/mt5copyratesfrompos_py).

Mặc định bot dùng **¼ Kelly**, trần rủi ro **0,5% equity**. Kelly cần tối thiểu 50 giao dịch đã đóng của đúng chiến lược, có cả giao dịch thắng và thua.

Tạo `logs/kelly_history.csv` theo [mẫu CSV](examples/kelly_history_template.csv). Mỗi dòng là một giao dịch đã đóng hoàn toàn:

| Cột | Nội dung |
| --- | --- |
| `trade_id` | Mã giao dịch duy nhất |
| `closed_at_utc` | Thời điểm đóng có múi giờ, ví dụ `2026-10-28T08:00:00Z` |
| `symbol` | Đúng tên broker, ví dụ `XAUUSDc` |
| `strategy_id` | Mặc định `m5_m1_pullback_v1`; `adaptive_trend_breakout_v1` với `--strategy adaptive`; `m1_pullback_breakout_v1` với `--strategy pullback` |
| `net_r` | Lãi/lỗ ròng sau phí, swap chia cho số tiền rủi ro ban đầu tại SL |

Ví dụ cách tính: lãi ròng 20 với rủi ro ban đầu 10 thì `net_r = 2`; lỗ ròng 12 với rủi ro ban đầu 10 thì `net_r = -1.2`. Đây chỉ là ví dụ định dạng, không phải kết quả thực tế của bot.

Không nhập từng lần khớp hoặc từng lần chốt một phần thành các giao dịch riêng. Không trộn lịch sử từ chiến lược khác. Bot không tự suy ra các giao dịch thủ công trong MT5 có thuộc chiến lược này hay không.

Bot lấy tối đa 200 giao dịch gần nhất trong 180 ngày, dùng ước tính tỷ lệ thắng thận trọng rồi tính Kelly phân đoạn. Thiếu dữ liệu, dữ liệu sai hoặc lợi thế không dương thì không có lot Kelly.

```powershell
.\venv\Scripts\python.exe run_mt5_assistant.py --kelly-history logs/kelly_history.csv --kelly-fraction 0.25 --risk-percent 0.5 --color always
```

Để chủ động chọn cách tính rủi ro cố định:

```powershell
.\venv\Scripts\python.exe run_mt5_assistant.py --sizing fixed --risk-percent 0.5 --color always
```

Các lot mô phỏng khi `WAIT` luôn được ghi rõ là theo trần rủi ro cố định, không dùng Kelly của những tín hiệu đã xác nhận.

### Vì sao lot là N/A?

- Equity bằng 0: chỉ phân tích giá, không tính lot.
- Kelly chưa đủ dữ liệu hoặc không có lợi thế dương.
- Lot tối thiểu của broker vượt ngân sách rủi ro.
- Không đủ margin hoặc MT5 không tính được lỗ/margin.

Bot không làm tròn lot lên để ép đạt lot tối thiểu. Các số tiền dùng đồng tiền tài khoản: tài khoản USC hiển thị USC, không phải USD.

## 5. Tùy chọn hữu ích

### Kiểm tra điều kiện và rủi ro toàn tài khoản

Bảng **Điều kiện vào lệnh** đánh dấu đạt/chưa đạt cho 8 quy tắc của hướng đang xem:
xu hướng M15, động lượng M5, nhịp hồi rồi vượt EMA21 trên M1, màu nến M1,
vùng RSI, ADX, spread và biên độ nến. Ví dụ `6/8` là số điều kiện đạt,
**không phải xác suất thắng 75%**. Điều kiện chưa đạt giải thích vì sao bot vẫn báo chờ.

Bot đọc các vị thế và lệnh chờ trên toàn tài khoản để ước tính tổng lỗ thêm
tới SL, mặc định giới hạn **2% equity**. Với vị thế đang mở, equity đã gồm
lãi/lỗ thả nổi nên rủi ro được tính từ giá hiện tại tới SL. Với lệnh chờ,
tính từ giá đặt tới SL. Bot cộng rủi ro các lệnh, không bù trừ vị thế ngược chiều.
Ngân sách còn lại có thể giảm lot mới xuống dưới mức rủi ro Kelly hoặc cố định đã chọn.

Nếu có lệnh thiếu SL, SL không hợp lệ, loại lệnh chưa hỗ trợ hoặc lỗi đọc dữ liệu,
bot vẫn có thể hiển thị kịch bản giá nhưng sẽ không đề xuất lot. Giới hạn volume
cùng chiều của broker cũng được xét khi tính lot mới. Đây là ước tính,
không phải cam kết SL được khớp đúng giá. Với symbol đang phân tích, bot cộng thêm
phí khứ hồi `--cost-per-lot` cho cả vị thế và lệnh chờ vào ngân sách rủi ro
(trường `cost_reserve` trong nhật ký). Đây là khoản dự phòng bảo thủ, có thể gồm
cả phần phí mở lệnh đã trả. Phí của symbol khác chưa được cấu hình nên chưa được
cộng; swap, trượt giá và gap của lệnh hiện có cũng chưa được tính.
Các lệnh stop-limit hiện chưa được mô hình hóa và sẽ chặn lot mới.

Bảng giá bổ sung **R:R sau phí/trượt giá** và **lãi ròng ước tính tại TP** khi
tính được lot. Nếu R:R ròng dưới 1:1,5 thì không đề xuất lot. Với kịch bản
tham khảo, khoảng cách tới giá kích hoạt được hiển thị bằng giá và ATR.
Snapshot hết hạn trong lúc xử lý sẽ bị chặn; nhấn Enter để lấy lại dữ liệu.

| Tham số | Công dụng |
| --- | --- |
| `--color always` | Bật màu chủ động |
| `--color never` | Tắt màu |
| `--risk-percent 0.5` | Trần rủi ro 0,5% vốn, không phải 50% |
| `--max-total-risk 2` | Trần tổng rủi ro tại SL toàn tài khoản là 2% vốn |
| `--cost-per-lot 7` | Phí khứ hồi ước tính mỗi lot, theo đồng tiền tài khoản |
| `--slippage-ticks 2` | Dự phòng 2 tick bất lợi ở cả điểm vào và điểm cắt lỗ |
| `--output logs/entry_plan.json` | Lưu thêm kết quả JSON sau mỗi lần phân tích |
| `--once` | Phân tích ngay một lần rồi thoát; không chờ Enter |
| `--help` | Liệt kê toàn bộ tham số |

Mặc định kết quả chỉ hiện trong terminal. Tệp `logs/entry_plan.json` cũ có thể không phản ánh lần phân tích mới nhất nếu bạn không dùng `--output`. Giờ trong JSON là UTC; giao diện terminal hiển thị UTC+7.

## 6. Xử lý sự cố

### So sánh chiến lược bằng backtest

Bot terminal hiện có 3 lựa chọn: `pullback` (M15/M5/M1), `adaptive`
(lọc xu hướng, pullback hoặc breakout) và `m5_m1` (M5 chọn hướng, M1 tìm điểm vào,
M15 chỉ cảnh báo). Mặc định công cụ so sánh chỉ chạy hai bản đầu;
để kiểm tra cả ba bằng tick, chỉ định đủ tên:

```powershell
.\venv\Scripts\python.exe -u -m scripts.compare_scalper_strategies --ticks --mt5-bars 10000 --max-ticks 3000000 --strategies pullback adaptive m5_m1 --output reports/all_strategies_ticks
```

Đối chiếu trên cùng dữ liệu, cùng chi phí và cùng mốc kiểm tra. Không xếp bản
không có lệnh là tốt nhất vì lợi nhuận bằng 0. Xếp hạng quan sát được theo kỳ vọng
R/lệnh cần ghi kèm số lệnh và drawdown; kết quả tốt nhất trong mẫu không tự
chứng minh lợi thế tương lai. Nếu ít lệnh, kỳ vọng không dương, còn đường giá
không xác định hoặc thiếu phí thực tế thì chưa đủ cơ sở chọn để giao dịch thật.

Giữ MT5 đăng nhập, mở terminal tại thư mục dự án rồi chạy:

```powershell
.\venv\Scripts\python.exe -u -m scripts.compare_scalper_strategies --mt5-bars 10000
```

Công cụ chỉ đọc nến M1 đã đóng, không gửi lệnh và không dùng vốn tài khoản.
Nó so sánh Pullback và Adaptive với cùng dữ liệu, rủi ro mặc định 0,5% của
tài khoản **ảo** 10.000, spread lịch sử và 2 tick trượt giá bất lợi mỗi phía.
Mặc định chưa tính commission/swap; `--fee-price` bổ sung phí khứ hồi quy đổi
sang đơn vị giá: phí mỗi lot / giá trị tiền tài khoản của một đơn vị biến động giá mỗi lot.
Phải dùng đúng đơn vị của symbol/tài khoản, không lấy USD thay USC.

Kết quả nằm trong `reports/scalper_comparison/`:

- `REPORT.md`: bảng so sánh và các giả định.
- `report.json`: thống kê, tham số, mốc tách dữ liệu và dấu vân tay dữ liệu/mã chiến lược.
- `trades.csv`: từng lệnh mô phỏng, kết quả R, lý do thoát và cờ đường giá mơ hồ.
- `history.csv`: dữ liệu nguồn có thể chạy lại; cột `time` là epoch giây UTC, `spread` là point của broker.

Ví dụ chạy lại từ CSV đã lưu, với point/tick của `XAUUSDc` đang dùng là 0,001:

```powershell
.\venv\Scripts\python.exe -u -m scripts.compare_scalper_strategies --csv reports/scalper_comparison/history.csv --point 0.001 --tick-size 0.001 --output reports/scalper_comparison_replay
```

Kiểm tra spread tăng 50% trên đúng dữ liệu đó:

```powershell
.\venv\Scripts\python.exe -u -m scripts.compare_scalper_strategies --csv reports/scalper_comparison/history.csv --point 0.001 --tick-size 0.001 --spread-multiplier 1.5 --output reports/scalper_comparison_stress
```

Nếu broker có stop distance khác 0, dùng `--stop-distance` để tái lập đúng tham số
trong `report.json`. Không tự áp dụng thông số 0,001 cho broker khác.
Nếu CSV không có spread, phải cung cấp `--spread-price` bằng đơn vị giá; không
ngầm dùng spread bằng 0.

Công cụ dành 3.300 nến đầu làm ấm chỉ báo, chia phần còn lại 70/30 theo thời gian.
Mỗi phần không cho lệnh đi qua ranh giới; phần sau vẫn được dùng lịch sử trước đó
để tính chỉ báo. Không tối ưu tham số trong công cụ, nhưng mốc holdout này không
bảo đảm người phát triển chưa từng xem giai đoạn dữ liệu đó.

**Giới hạn:** chỉ có OHLC M1 nên thời hạn lệnh chờ được xấp xỉ thành một nến,
không khớp chính xác thời hạn 15 giây của bot. Khi SL/TP cùng chạm, tính SL trước;
không biết SL có xảy ra trước khi khớp lệnh trong nến đó hay không nên dùng cách
tính bất lợi. Gap SL nhận giá mở bất lợi. Spread cố định trong mỗi nến cũng chỉ
là xấp xỉ. Lệnh được đóng sau tối đa 120 nến hoặc cuối phần dữ liệu.

Kết quả vốn dùng lot liên tục, không xét lot tối thiểu, margin hoặc Kelly; drawdown
chỉ tính sau các lệnh đã đóng. Không dùng các giao dịch mô phỏng này làm nhật ký
Kelly thực tế. Mẫu ngắn và ít lệnh không chứng minh chiến lược nào tốt nhất.
Công cụ không tự đổi chiến lược đang chạy.

### Mô phỏng bằng tick bid/ask và hạn 15 giây

Để kiểm tra gần cơ chế thời hạn của terminal hơn bản OHLC, chạy:

```powershell
.\venv\Scripts\python.exe -u -m scripts.compare_scalper_strategies --ticks --mt5-bars 5000 --output reports/scalper_ticks
```

MT5 cần đăng nhập và có lịch sử tick của symbol. Công cụ tải theo từng giờ,
chỉ cho phần đánh giá sau 3.300 nến làm ấm, giới hạn mặc định 2.000.000 tick.
Nếu vượt giới hạn, giảm số nến hoặc chủ động tăng `--max-ticks`.
Nếu MT5 không trả tick thì dừng/báo thiếu dữ liệu, không tự dùng nến thay thế.

Trong chế độ này, bot dùng quote tại hoặc trước thời điểm quyết định, tuổi tối
đa 15 giây; không dùng tick tương lai để tạo tín hiệu. Deadline của lệnh chờ
là mốc sớm hơn giữa thời điểm quyết định +15 giây và giây quote +15 giây,
giống cách terminal giới hạn tuổi kế hoạch. Tick đúng mốc hết hạn không được khớp.
BUY vào theo Ask, ra theo Bid; SELL vào theo Bid, ra theo Ask. Thứ tự SL/TP
theo các tick quan sát được. SL gap nhận quote bất lợi, không được bảo đảm giá SL.

Tick trùng millisecond được giữ theo thứ tự dữ liệu và gắn cờ `ambiguous_path`,
vì không bảo đảm biết thứ tự thực tế trong cùng millisecond. Khoảng trống tick
trên 30 giây là chưa xác định; có thể là thiếu dữ liệu hoặc ít quote, công cụ
không tự coi giá đứng yên. Nếu đã khớp nhưng không xác định được đường thoát,
dừng phần đánh giá đó và đếm vị thế chưa giải quyết. Kết quả lãi/lỗ chỉ gồm
các lệnh có kết quả xác định, không phải kết quả đầy đủ nếu còn vị thế như vậy.

Báo cáo lưu thêm `ticks.csv.gz` và `execution_events.csv`. Tệp events phân biệt
tín hiệu đã đóng, hết hạn chưa khớp và không xác định. Đếm riêng số phút thiếu
quote quyết định; thiếu quote không đồng nghĩa không có tín hiệu hoặc không khớp.

Chạy lại từ đúng dữ liệu đã lưu:

```powershell
.\venv\Scripts\python.exe -u -m scripts.compare_scalper_strategies --csv reports/scalper_ticks/history.csv --point 0.001 --tick-size 0.001 --ticks-csv reports/scalper_ticks/ticks.csv.gz --output reports/scalper_ticks_replay
```

Đây vẫn là mô phỏng, giả định có thể phân tích và đặt lệnh ngay lúc nến đóng.
Chưa xét độ trễ thao tác thực tế, độ sâu thị trường, khớp một phần, lot tối thiểu,
margin hay phí chưa cung cấp. Không dùng kết quả làm xác suất thắng hoặc lịch sử
Kelly thực tế. Giữ nguyên tham số và kiểm tra trên các giai đoạn mới trước khi kết luận.

### Kiểm tra nhật ký

Mỗi lần phân tích mới được lưu vào `logs/assistant_events.jsonl`, gồm thời điểm UTC,
trạng thái, lý do, kịch bản giá/lot, các kiểm tra và thời gian xử lý.
Log xoay vòng khi đạt khoảng 2 MB, giữ thêm 3 bản sao; có thể vượt nhẹ giới hạn
với một bản ghi lớn. Chỉ ghi khi phân tích, không có tiến trình nền.
Log không ghi thông tin đăng nhập hoặc mã tài khoản, nhưng có equity và kết quả
phân tích, nên kiểm tra nội dung trước khi chia sẻ.

Nhập `l` trong bot, hoặc chạy lệnh sau để xem tóm tắt mà không kết nối MT5:

```powershell
.\venv\Scripts\python.exe run_mt5_assistant.py --log-summary
```

Tóm tắt xét tối đa 200 dòng gần nhất của tệp hiện tại, đếm WAIT/REVIEW/BLOCKED
và các lý do thường gặp. Đây không phải báo cáo kết quả giao dịch hoặc lợi nhuận.
Đổi nơi ghi bằng `--log-file logs/ten_khac.jsonl`; dùng `--no-log` nếu không muốn lưu.
Log lỗi hoặc JSON không ghi được sẽ có cảnh báo riêng; kết quả phân tích vẫn hiển thị.

Các tệp `mt5_assistant.stderr.log`, `mt5_assistant.stdout.log`, `mt5_assistant.pid`
là dữ liệu từ bản chạy nền cũ, không phản ánh phiên terminal hiện tại.

| Thông báo / tình huống | Cách xử lý |
| --- | --- |
| Không kết nối MT5 | Mở MT5, đăng nhập và kiểm tra mạng |
| Không tìm thấy symbol | Dùng `--symbol` với tên chính xác trong Market Watch |
| Giá hoặc nến quá cũ | Kiểm tra kết nối, phiên giao dịch và giờ máy; thử lại bằng Enter |
| Thiếu lịch sử | Mở biểu đồ M1 của symbol trong MT5 và đợi tải thêm dữ liệu |
| Kelly INSUFFICIENT_DATA | Bổ sung nhật ký giao dịch đúng định dạng; không tự gán tỷ lệ thắng |
| Không có màu | Chạy với `--color always`, ưu tiên Windows Terminal |

Lot và mức giá là ước tính tại thời điểm phân tích. Bot cộng gộp rủi ro tại SL của các vị thế/lệnh chờ hỗ trợ; phí chưa khai báo, swap và gap có thể khiến lỗ thực tế vượt dự tính. Kiểm tra margin, vị thế và giá trong MT5 trước khi tự đặt lệnh.
## Chạy demo Donchian 55/20 trên D1

Mở MT5 và đăng nhập tài khoản **demo**, rồi chạy:

```powershell
.\venv\Scripts\python.exe run_mt5_assistant.py --symbol XAUUSD --strategy donchian_55_20 --color always
```

Bản này dùng risk cố định tối đa 0,5%, SL 2 ATR20, thoát theo kênh 20 phiên,
không có TP cố định và không tự gửi lệnh. Xem [hướng dẫn demo](DONCHIAN_DEMO.md)
để quản lý vị thế theo ticket và đọc các điều kiện chặn.

Đã backtest riêng biến thể **55/20 nến M1**: cả 12 ca holdout đều âm.
Xem [kết quả Donchian M1](DONCHIAN_M1_BACKTEST.md); không chuyển kết quả D1 sang M1.

Đã kiểm tra thêm [ORB, Noise Area/VWAP và EMA/VWAP trên vàng](SCALPING_CANDIDATES_CHECK.md): có kết quả sau phí, stress spread và giới hạn dữ liệu; chưa đủ bằng chứng chọn chiến lược có lợi nhuận ổn định.

## Phiên bản thử nghiệm M5/M1 Regime v2

Đã bổ sung mẫu lịch sử từ MT5 và HistData. Xem [dữ liệu nhiều nguồn](MARKET_DATA.md)
để tải lại, kiểm tra chất lượng và dùng cho backtest.
Đã hoàn tất so sánh ba phiên bản; xem [kết quả backtest](MULTISOURCE_BACKTEST_RESULTS.md).
Đã kiểm tra thêm các chiến lược từ nghiên cứu công khai; xem
[Momentum, AQR và Turtle/Donchian](PUBLISHED_STRATEGIES_CHECK.md).

```powershell
.\venv\Scripts\python.exe run_mt5_assistant.py --symbol XAUUSD --strategy m5_m1_regime --color always
```

Mã chiến lược `m5_m1_regime_pullback_v2` kế thừa bộ lọc `m5_m1_quality`, bổ sung:

- Cửa sổ 21 nến M1 và 13 nến M5 có timestamp liên tục.
- Hiệu suất dịch chuyển M5 trên 12 khoảng nến ít nhất 0,3: độ dịch chuyển ròng
  chia tổng biến động tuyệt đối; hướng ròng phải cùng hướng lệnh.
- ATR hiện tại trong khoảng 0,5–2 lần trung vị ATR của 20 nến M1 trước.
- Thân nến kích hoạt ít nhất 30% biên độ; đóng trong 35% gần đỉnh khi BUY,
  gần đáy khi SELL.
- SL cấu trúc cách giá đóng nến tín hiệu không quá 3 ATR. Giá kích hoạt có thể
  xa hơn; lot vẫn tính theo giá kích hoạt và chi phí thực tế.

Bảng kiểm tra giải thích điều kiện bị chặn. Kelly dùng lịch sử riêng theo mã v2.
Giữ nguyên quản trị tài khoản, kiểm tra RR sau chi phí và đặt lệnh thủ công.
M15 vẫn chỉ là ngữ cảnh. Confidence không phải xác suất thắng đã hiệu chỉnh.

Tái lập so sánh trên dữ liệu tick đã lưu:

```powershell
.\venv\Scripts\python.exe -u -m scripts.compare_scalper_strategies --csv reports/scalper_ticks/history.csv --point 0.001 --tick-size 0.001 --ticks-csv reports/scalper_ticks/ticks.csv.gz --strategies m5_m1 m5_m1_quality m5_m1_regime --output reports/m5_m1_regime
```

Kết quả trong `reports/m5_m1_regime/REPORT.md`: trên phần holdout, bản mặc định
có 4 lệnh, tổng −1,098R; bản quality có 2 lệnh, −2,087R; bản regime có 1 lệnh,
−1,073R. Bản regime cũng lỗ −2,091R trên phần development với 2 lệnh.
**Chưa có bằng chứng cải thiện lợi nhuận; không thay mặc định `m5_m1`.**
Mẫu rất nhỏ, dùng lại dữ liệu cũ, chưa phải kiểm chứng độc lập mới và chưa gồm
commission/swap chưa cung cấp. Các ngưỡng là giả thuyết kỹ thuật.
Có thể thêm `--fee-price` cho phí khứ hồi quy đổi sang đơn vị giá và
`--spread-multiplier 1.5` để kiểm tra spread tăng.

