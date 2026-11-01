# Kết quả kiểm chứng chiến lược ngày 01/11/2026

**Chưa có bằng chứng để thay chiến lược mặc định bằng quality hoặc regime.**
Đã chạy xong 11 bộ kiểm tra, mỗi bộ gồm ba chiến lược với tham số cố định,
không lỗi chạy. Dữ liệu gồm 995.813 nến HistData và 50.000 nến MT5, giữ riêng
từng nguồn. Nến trùng thời gian giữa hai nguồn không được tính là mẫu độc lập.

## Kết quả trên phần 30% cuối mỗi bộ

Mỗi ô ghi **tổng R / số lệnh**. HistData ở bảng này dùng spread giả định 0,24
đơn vị giá; MT5 dùng spread lịch sử nến. Cả hai có trượt giá bất lợi 2 tick,
**chưa gồm commission/swap chưa được cung cấp**.

| Nguồn/giai đoạn | Mặc định m5_m1 | Quality | Regime v2 |
| --- | ---: | ---: | ---: |
| HistData 2024 | −1,38R / 68 | +1,32R / 60 | +1,96R / 37 |
| HistData 2025 | −51,48R / 817 | −53,58R / 687 | −28,23R / 348 |
| HistData 2026 đến 23/10 | −1,94R / 613 | −17,83R / 521 | −13,25R / 219 |
| MT5 09–10/2026 | −33,08R / 157 | −30,28R / 135 | −18,08R / 51 |

Phần kiểm tra bắt đầu tại 12/09/2024 21:57 UTC cho bộ năm 2024,
15/09/2025 00:42 UTC cho bộ năm 2025. Xem timestamp chính xác của mọi bộ
trong `report.json`. Tên năm/giai đoạn trong bảng là toàn bộ cửa sổ đầu vào,
không phải toàn bộ thời gian đều thuộc phần kiểm tra.

Trên MT5, kỳ vọng mỗi lệnh lần lượt là −0,211R, −0,224R và −0,354R.
Profit factor lần lượt 0,712; 0,697; 0,548. Regime giảm tổng lỗ và drawdown
nhờ giao dịch ít hơn, nhưng không cho thấy lợi thế mỗi lệnh tốt hơn.
Drawdown đóng lệnh của bản mặc định là 18,40% trên MT5 và 38,09% trên
HistData 2025, với risk mô phỏng 0,5% mỗi lệnh.

Các ca HistData tăng spread lên 0,36, có và không có phí giả định 0,10,
vẫn lỗ ở phần kiểm tra năm 2025 và 2026 cho cả ba chiến lược. Các ca MT5
tăng spread 50% kèm phí giả định 0,10 cũng đều lỗ. Vài kết quả dương năm
2024 có số lệnh nhỏ, không chứng minh lợi thế ổn định qua các giai đoạn.

Không thay mặc định, không tăng risk và không nhập giao dịch mô phỏng vào Kelly.
Giữ các phiên bản mới ở trạng thái thử nghiệm; kết quả hiện tại không đáp ứng
điều kiện xác nhận một chiến lược có kỳ vọng dương ổn định.

## Giới hạn của phép kiểm chứng

- Đây là mô phỏng **OHLC M1**, không phải tick replay. Pending được giữ một nến,
  khác thời hạn 15 giây của trợ lý. Kết quả không xác nhận chất lượng khớp lệnh thật.
- Mỗi bộ dùng 3.300 nến làm ấm, phần còn lại chia 70/30 theo thứ tự thời gian.
  Không tối ưu tham số theo kết quả; không coi phần dữ liệu đã từng xem là
  kiểm chứng ngoài mẫu độc lập hoàn toàn.
- Spread HistData và phí ở các ca stress là giả định, không phải dữ liệu chi phí
  thực tế. Dữ liệu MT5/HistData có khác biệt giá tại cùng timestamp chưa được
  xác định đầy đủ nguyên nhân; không tự dịch giờ để ép khớp hai nguồn.
- Lệnh chạm cả SL/TP trong cùng nến dùng SL trước; gap thoát tại giá mở tiếp theo.
  Không điền giá vào phút thiếu. Equity/lot là mô phỏng; DD chỉ đo ở đóng lệnh,
  chưa gồm lỗ thả nổi, lot tối thiểu, margin hoặc vị thế ngoài chiến lược.

## Báo cáo và tái lập

- [Báo cáo đầy đủ tại máy](../reports/market_data_backtest/REPORT.md): 33 dòng
  kết quả holdout theo chiến lược và kịch bản chi phí.
- `reports/market_data_backtest/summary.csv`: 66 dòng gồm development và holdout.
- `reports/market_data_backtest/summary.json`: số liệu cùng thông tin dữ liệu,
  tham số, SHA256 mã nguồn và SHA256 CSV đầu vào.
- Mỗi thư mục con có `trades.csv`, `monthly.csv`, `report.json`, `progress.log`.
- `prefilter_parity.json`: đối chiếu tăng tốc với quét đầy đủ trên 5.000 nến MT5,
  giống hoàn toàn với 56 giao dịch. Kiểm tra hồi quy có cả BUY, SELL và gap.

```powershell
.\venv\Scripts\python.exe -u -m scripts.run_market_data_backtests
```

Xem [hướng dẫn dữ liệu](MARKET_DATA.md) để tải lại mẫu và hiểu các giả định chi phí.
