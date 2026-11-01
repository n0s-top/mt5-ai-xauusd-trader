# Backtest Donchian 55/20 trên M1

Ngày chạy: 01/11/2026. **55/20 ở đây là 55/20 nến phút**, không phải tín hiệu
D1 được mô phỏng khớp lệnh bằng M1. Chiến lược demo D1 không bị thay đổi.

Đã chạy 12 cấu hình: mẫu MT5 50.000 nến và HistData chia năm 2024/2025/2026,
mỗi mẫu ba mức chi phí. Mỗi cấu hình dùng 200 nến đầu làm ấm, sau đó chia 70/30
theo thời gian, reset equity 10.000 USD riêng cho development và holdout.
Đây là dữ liệu đã từng được xem trong các thử nghiệm trước, không gọi là tập
ngoài mẫu độc lập hoàn toàn.

## Kết quả holdout có phí

HistData giả định spread 0,24 đơn vị giá; MT5 dùng spread nến lịch sử.
Thêm phí khứ hồi giả định 0,10, slippage bất lợi 0,002 mỗi chiều và phí giữ vị thế
giả định 3%/năm theo notional tuyệt đối. Các giả định này không phải phí/swap
thực tế broker đã xác minh.

| Mẫu | Lệnh | Win rate | PF ròng | Return | DD mark close M1 |
| --- | ---: | ---: | ---: | ---: | ---: |
| MT5 09–10/2026 | 355 | 25,63% | 0,646 | −13,83% | 16,46% |
| HistData 2024 | 2.396 | 24,50% | 0,689 | −47,17% | 47,83% |
| HistData 2025 | 2.315 | 27,60% | 0,906 | −23,75% | 30,68% |
| HistData 2026 đến 23/10 | 1.822 | 27,88% | 0,781 | −39,09% | 41,52% |

Trong ca chưa thêm commission/financing (vẫn có spread và slippage), return lần
lượt −12,20%; −36,12%; −13,88%; −33,21%. Khi tăng spread 50%, thêm phí và financing
8%/năm, return lần lượt −14,62%; −58,11%; −34,35%; −45,66%.

**Cả 12 ca đều âm trên holdout. Chưa có cơ sở đưa biến thể M1 vào demo.**
Giữ lựa chọn Donchian D1 đang có; không dùng các kết quả dương của D1 để quảng bá
cho M1. Các mức lợi nhuận là mô phỏng, không phải kết quả tài khoản thực tế.

## Quy tắc và cách khớp

- Entry: Bid vượt đỉnh hoặc xuyên đáy **55 nến M1 trước** một tick. SL ban đầu
  cách mốc fill Bid 2 Wilder ATR20 của nến trước. Thoát theo kênh 20 M1 hoặc SL;
  không TP cố định, không thêm unit, một vị thế tại một thời điểm.
- BUY vào Ask, thoát Bid; SELL vào Bid, thoát Ask. Spread được coi hằng trong
  mỗi nến. Kênh SELL được quy đổi sang Ask bằng spread đã biết ở nến trước.
- Risk 0,5% là **trần**, không phải mức thực tế bắt buộc; cap notional 2× vốn
  có thể làm risk thấp hơn đáng kể. Sizing là ounce liên tục tại giá fill mô phỏng,
  không có minimum lot, volume-step, margin call hoặc lệnh pending lot cố định.
- Entry cần 55 phút trước liên tục. Nếu đang giữ gặp gap, thoát ở open tiếp theo
  quan sát được, cộng chi phí; không dựng đường giá cho phút thiếu. Quy tắc này
  có thể đóng vị thế tại mở cửa sau cuối tuần và khác chiến lược giữ qua gap.
- Không vào lại trong nến vừa thoát. Nếu entry/SL hoặc hai hướng cùng chạm,
  tính stop bất lợi và ghi `ambiguous_path`. Có thể lỗ hơn 1R khi gap/spread đổi.
- Cuối mỗi phần, vị thế còn mở được thanh lý có tính phí. Financing tính số giây
  thực tế giữ vị thế; 0%, 3%, 8% là giả định chung, không thay swap broker.
- Equity mark từng close M1 gồm lãi/lỗ thả nổi; DD không gồm cực trị trong nến.
  R là PnL ròng chia risk SL ước tính khi vào, không gồm financing tương lai.

Mẫu hai nguồn có thời gian giao nhau nên không cộng thành mẫu thị trường độc lập.
Backtest OHLC không xác nhận thứ tự tick hoặc khả năng khớp thực tế. Các nến
HistData có timestamp mâu thuẫn đã bị cách ly trong bước chuẩn hóa trước đó.

## Chạy lại và đọc báo cáo

```powershell
.\venv\Scripts\python.exe -u -m scripts.backtest_donchian_m1
```

Chỉ chạy mẫu MT5:

```powershell
.\venv\Scripts\python.exe -u -m scripts.backtest_donchian_m1 --source mt5
```

Kết quả tại `reports/donchian_m1/`:

- `REPORT.md`, `summary.csv`, `summary.json`: đủ mọi ca, cả development và holdout.
- Mỗi thư mục có `trades.csv`, `report.json` kèm SHA256 dữ liệu và mã nguồn.
- `equity_daily_*.csv`: equity cuối ngày để xem nhanh.
- `equity_*.npz`: toàn bộ equity close M1; đọc bằng `numpy.load(..., allow_pickle=False)`,
  hai mảng `time` (epoch seconds UTC) và `equity`.

Kiểm tra hồi quy bao gồm không nhìn trước giá, khớp Bid/Ask, gap xuyên SL,
chi phí/financing, entry/SL mơ hồ và giữ nguyên khoản thiếu hụt khi equity âm
trong kịch bản gap cực đoan, thay vì che lỗ bằng cách chặn equity ở 0.
