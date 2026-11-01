# Mẫu lịch sử XAUUSD từ nhiều nguồn

Đã tải ngày 01/11/2026, lưu tại `reports/market_data/`:

| Nguồn | Nến M1 sạch | Khoảng thời gian UTC |
| --- | ---: | --- |
| MT5 đang kết nối, XAUUSD | 50.000 | 10/09/2026 14:14 – 30/10/2026 20:56 |
| HistData, XAUUSD | 995.813 | 01/01/2024 23:00 – 23/10/2026 21:58 |

Tổng số dòng là 1.045.813, nhưng **không phải toàn bộ là các phút thị trường độc lập**:
39.511 phút trùng thời điểm giữa hai nguồn. Không ghép hai nguồn thành một chuỗi giá.
Giá đóng tại cùng timestamp cũng có thể khác; trung vị chênh lệch tuyệt đối trên
phần giao nhau là 5,767 USD/oz. Chưa kết luận khác biệt do nguồn giá hay căn chỉnh
giờ máy chủ; không tự dịch timestamp để ép hai nguồn khớp nhau.

HistData có 120 dòng trùng hoàn toàn đã bỏ. Ngoài ra, 2.111 dòng thuộc 1.021 timestamp
có giá mâu thuẫn đã được đưa vào `histdata/quarantine.csv`; toàn bộ các timestamp đó
bị loại khỏi bản sạch. Không chọn bản có lợi hơn cho backtest. Không điền nến giả
vào khoảng trống; số gap trong manifest bao gồm cả giờ nghỉ thị trường.

HistData tháng 10 hiện chỉ tới 23/10/2026; không coi đó là tháng đầy đủ.
Dukascopy đã được thử nhưng máy chủ tải dữ liệu từ chối kết nối, chưa tải được
mẫu từ nguồn này. Hai nguồn đã tải thành công là MT5 và HistData.

## Tải lại hoặc bổ sung

Chạy tại thư mục dự án, MT5 đang mở và đăng nhập:

```powershell
.\venv\Scripts\python.exe -u -m scripts.download_market_data --symbol XAUUSD --histdata-periods 2024 2025 202601 202602 202603 202604 202605 202606 202607 202608 202609 202610
```

ZIP đã có được dùng lại để tái lập dữ liệu; công cụ không tự làm mới một ZIP đã tải.
Muốn cập nhật tháng đang thiếu phần cuối, di chuyển ZIP tương ứng khỏi
`reports/market_data/histdata/raw/` rồi tải lại, hoặc dùng một thư mục `--output` mới.

Chỉ lấy MT5:

```powershell
.\venv\Scripts\python.exe -u -m scripts.download_market_data --sources mt5 --symbol XAUUSD --mt5-bars 50000
```

Chỉ lấy các tháng HistData, lưu riêng để giữ bộ cũ:

```powershell
.\venv\Scripts\python.exe -u -m scripts.download_market_data --sources histdata --histdata-periods 202501 202502 202503 --output reports/market_data_2025_q1
```

`--sources` mặc định tải cả hai nguồn. Giới hạn MT5 phụ thuộc lịch sử broker và
cài đặt Max bars in chart; không tự tăng cài đặt terminal. Nếu nguồn nào lỗi,
catalog ghi lỗi và tiến trình trả mã khác 0, không báo bộ tải thiếu là thành công.
CSV và ZIP lớn nằm trong `reports/`, được Git bỏ qua theo cấu hình hiện có.

## Dùng cho backtest

- `mt5/history.csv` có spread lịch sử theo point và tick volume của broker.
- `histdata/history.csv` chỉ có Bid OHLC. Cột volume là giá trị giữ chỗ, không
  phải khối lượng tick quan sát. Không có spread quan sát và không tự thêm spread 0.
- Cả hai CSV đều là M1; **không cung cấp đường đi tick** cho mô phỏng pending 15 giây.
- Mỗi nguồn có `manifest.json` ghi SHA256, khoảng thời gian, gap và thông tin nguồn.
  Tổng hợp trong `catalog.json` và `REPORT.md`.

Ví dụ chạy so sánh OHLC trên mẫu MT5 đã tải:

```powershell
.\venv\Scripts\python.exe -u -m scripts.compare_scalper_strategies --csv reports/market_data/mt5/history.csv --point 0.001 --tick-size 0.001 --strategies m5_m1 m5_m1_quality m5_m1_regime --output reports/market_data_mt5_comparison
```

Point/tick-size trong ví dụ là của symbol đã tải, không áp dụng chung cho mọi broker.
HistData yêu cầu thêm `--spread-price` với giả định được chỉ rõ, cùng phí quy đổi
`--fee-price` nếu có. Chưa cung cấp phí thì kết quả không bao gồm commission/swap.
Không trộn tick MT5 với nến HistData để khẳng định chất lượng khớp lệnh.

Đánh giá từng nguồn và từng giai đoạn riêng. Dữ liệu đã dùng để chọn bộ lọc không
còn là kiểm chứng độc lập cho lựa chọn đó. Việc tải thêm mẫu chưa chứng minh
chiến lược sinh lời.

## Chạy bộ backtest nhiều nguồn

Đã chạy xong 11 bộ kiểm tra ngày 01/11/2026. Xem
[kết quả và kết luận](MULTISOURCE_BACKTEST_RESULTS.md).

```powershell
.\venv\Scripts\python.exe -u -m scripts.run_market_data_backtests
```

Bộ chạy giữ nguyên tham số ba chiến lược, đánh giá riêng từng năm HistData
2024/2025/2026 và mẫu MT5. Mỗi bộ dùng 3.300 nến đầu làm ấm, sau đó chia
70/30 theo thời gian. Có 11 bộ kiểm tra, mỗi bộ gồm cả ba chiến lược:

- HistData mỗi năm: spread giả định 0,24; spread 0,36; spread 0,36 kèm phí
  khứ hồi giả định 0,10 đơn vị giá.
- MT5: spread nến quan sát; spread tăng 50% kèm phí giả định 0,10 đơn vị giá.

Phí giả định không phải phí thực tế broker. Mọi ca có trượt giá bất lợi 2 tick;
ca không cung cấp phí chưa bao gồm commission/swap. Kết quả là mô phỏng OHLC M1,
không phải tick replay xác nhận khớp lệnh trong thời hạn 15 giây của trợ lý.

Xem `reports/market_data_backtest/REPORT.md`, `summary.csv`, `summary.json` và
từng thư mục con chứa `report.json`, `trades.csv`, `monthly.csv`, `progress.log`.
SHA256 dữ liệu và mã nguồn được ghi để tái lập. Mỗi lần chạy xuất lại bộ kết quả
trong thư mục `--output`; dùng thư mục khác nếu muốn giữ phiên bản trước.

Tăng tốc bằng cách lấy vị trí nến đóng bằng tìm kiếm nhị phân và chỉ đánh giá
đầy đủ ở các nến có thể đạt điều kiện nền. Đã đối chiếu trên 5.000 nến MT5:
kết quả cả ba chiến lược giống hoàn toàn quét đầy đủ, gồm 56 giao dịch.
Bằng chứng nằm trong `reports/market_data_backtest/prefilter_parity.json`.
Các bài kiểm tra hồi quy cũng đối chiếu hai cách chạy cho BUY/SELL và dữ liệu có gap.

Múi giờ HistData được đổi từ **EST cố định UTC−5, không DST** theo
[FAQ chính thức](https://www.histdata.com/f-a-q/).
Thời gian MT5 giữ theo epoch của API, theo
[tài liệu MetaTrader 5](https://www.mql5.com/en/docs/python_metatrader5/mt5copyratesrange_py).
