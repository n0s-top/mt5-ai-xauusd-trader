# Demo Donchian 55/20 trên MT5

Đã tích hợp lựa chọn `donchian_55_20` vào trợ lý. Đây là bản **hỗ trợ giao dịch
thủ công trên tài khoản demo**, không gửi/sửa/hủy lệnh tự động. Mặc định M5/M1
của lệnh chạy cũ được giữ nguyên; chọn rõ Donchian bằng lệnh dưới.

## Khởi động

Mở MT5 và đăng nhập **tài khoản demo**, chọn đúng symbol của broker rồi chạy:

```powershell
.\venv\Scripts\python.exe run_mt5_assistant.py --symbol XAUUSD --strategy donchian_55_20 --color always
```

Donchian tự chọn sizing fixed, risk tối đa 0,5% cho một unit. Có thể ghi rõ:

```powershell
.\venv\Scripts\python.exe run_mt5_assistant.py --symbol XAUUSD --strategy donchian_55_20 --sizing fixed --risk-percent 0.5 --color always
```

Nhấn Enter để lấy phân tích mới, `q` để thoát. Mỗi lần chỉ phân tích một lần;
không theo dõi hay đóng vị thế khi bạn để cửa sổ chờ. Không dùng Kelly của bản M1.
Trợ lý sẽ chặn kế hoạch trên tài khoản thật hoặc khi không đọc được chế độ tài khoản.

## Quy tắc được hiển thị

- Dùng các phiên **D1 đã đóng**, gộp nến Chủ nhật ngắn vào thứ Hai. Chủ nhật không
  được dùng riêng khi thứ Hai chưa đóng. Lấy tối đa 1.000 nến D1 để làm ấm ATR20.
- BUY: mức Bid vượt đỉnh 55 phiên một tick. Giá BUY_STOP theo Ask có cộng spread
  hiện tại; SL theo Bid ở dưới mốc breakout 2 ATR20.
- SELL: Bid xuyên đáy 55 phiên một tick. SL trên mốc breakout 2 ATR20, quy đổi sang
  Ask bằng spread hiện tại. Mức SL được làm tròn bất lợi theo tick-size broker.
- **Không có TP cố định, không ép RR 1:2.** BUY thoát theo đáy 20 phiên, SELL
  thoát theo đỉnh 20 phiên, hoặc tại SL bảo vệ. Phải xem xét lại sau mỗi phiên D1.
- Hai bảng BUY/SELL là **hai phương án thay thế**, không phải yêu cầu đặt đồng thời.
  Chỉ một unit; không thêm vị thế. Sau khi khớp phải hủy lệnh chờ còn lại bằng tay.
- Nếu bất kỳ breakout nào đã chạm trong D1 hiện tại, bản demo không đuổi giá và
  không đưa lot cho phương án còn lại. Nếu symbol có giao dịch trong ngày, có
  vị thế hoặc lệnh chờ, trợ lý cũng chặn đề xuất vào mới.

## Lot, rủi ro và thời hạn

Lot được tính bằng `order_calc_profit` và `order_calc_margin` của broker, gồm
phí khứ hồi `--cost-per-lot` nếu đã khai báo và `--slippage-ticks` (mặc định 2).
Làm tròn lot xuống theo volume-step; không ép lên minimum lot nếu vượt risk.
Giữ nguyên trần rủi ro toàn tài khoản và phần đệm margin, thêm trần notional 2× equity.

Giá/lot của snapshot chỉ dùng tối đa 15 giây và không qua mốc đổi ngày UTC.
Làm mới trước khi thao tác. Mức kênh D1 có thể vẫn hiển thị khi thị trường đóng,
nhưng quote cũ sẽ làm trạng thái BLOCKED và không có lot.

Phí qua đêm chưa được tính vào ngân sách SL; gap có thể gây lỗ vượt SL. Các giả
định financing 3%/8% trong backtest không được dùng thay swap thực tế của broker.
Lệnh chờ thủ công còn tồn tại trong MT5 không tự hết hạn cùng snapshot: phải hủy
hoặc đặt expiry trong MT5 và tính lại khi đổi phiên. Spread thay đổi có thể làm
lệch mức Ask kích hoạt/thoát so với mốc Bid, cần kiểm tra lại khi refresh.

## Xem xét vị thế đã mở

Lấy ticket của **vị thế Donchian demo bạn đã đặt**, rồi chỉ định rõ, ví dụ ticket 123456:

```powershell
.\venv\Scripts\python.exe run_mt5_assistant.py --symbol XAUUSD --strategy donchian_55_20 --position-ticket 123456 --color always
```

Trợ lý không tự nhận một giao dịch bất kỳ là của chiến lược. Vị thế phải có SL
hợp lệ đã đặt từ khi vào; không suy đoán ATR lúc vào bằng ATR hiện tại.

- `REVIEW_PROTECTIVE_STOP`: xem xét mức bảo vệ theo kênh 20 phiên; chỉ đề xuất
  siết hoặc giữ SL hiện có, không nới SL.
- `EXIT_MANUAL_NOW`: quote mới cho thấy điều kiện SL/kênh thoát đã bị chạm;
  bạn phải kiểm tra và xử lý bằng tay trong MT5.
- Nếu khoảng cách sửa SL chưa đáp ứng broker, không sửa sang mức bất hợp lệ;
  kiểm tra điều kiện thoát và mức bảo vệ hiện có. Trợ lý không sửa lệnh.

## Nhật ký và kiểm chứng

Mã chiến lược riêng: `donchian_55_20_d1_demo_v1`. Nhật ký mặc định nằm ở
`logs/assistant_events.jsonl`. Đây là log **phân tích**, không phải log giao dịch
đã khớp và không phải lịch sử lợi nhuận Kelly. Dùng MT5 statement để đối chiếu
giá khớp, spread, phí/swap và kết quả thực tế.

Có thể lưu snapshot một lần để đối chiếu:

```powershell
.\venv\Scripts\python.exe run_mt5_assistant.py --symbol XAUUSD --strategy donchian_55_20 --once --output reports/donchian_demo/latest.json --color always
```

Bản kiểm chứng lịch sử dùng OHLC, unit liên tục và chi phí giả định; bản demo
dùng broker lot, Ask/Bid, khoảng cách stop và quote hiện tại. Bản demo chặn các
breakout đã chạm trước thời điểm quan sát, nên không khẳng định khớp đúng mọi
lệnh trong backtest. Chưa có bằng chứng lợi nhuận demo/live mới.
Xem [kết quả nghiên cứu](PUBLISHED_STRATEGIES_CHECK.md).
