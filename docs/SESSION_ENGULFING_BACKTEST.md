# H1/M5/M1 engulfing — quy tắc và backtest

Ngày chạy: 01/11/2026. Mã `h1_m5_m1_session_engulfing_v1`. Chỉ nghiên cứu; không thêm vào lựa chọn live và không đổi ORB mặc định.

## Nguồn ý tưởng và phạm vi

[M4Markets](https://m4markets.com/education/xau-usd-scalping-strategy/) mô tả việc kết hợp bối cảnh, nhịp hồi, xác nhận nến, phiên giao dịch và chi phí. Bài không đưa bộ quy tắc H1/M5/M1 định lượng hay kết quả kiểm định cho bản này. [Bài TradingView của Ombabibi](https://www.tradingview.com/chart/XAUUSD/0ifwJoVz-My-XAUUSD-Scalping-Strategy-Entry-Stop-Loss-Management/) dùng bối cảnh M30/M15, SL khoảng 1–3 đơn vị giá và chốt 70% sau khi giá đi thuận 1 đơn vị. Không đồng nhất bài đó với bản H1 dưới đây. [MetaGold](https://fxmetagold.com/blog/gold-scalping) là nguồn hướng dẫn bổ sung, không phải chứng cứ backtest của mã này.

Bản thử nghiệm chỉ định lượng phần EMA, engulfing, phiên và SL/TP. Chưa dùng DXY, lịch tin CPI/NFP/FOMC, VWAP, H4, FVG/order block, hoặc thoát từng phần. Dữ liệu hiện có không cung cấp lịch tin và DXY đồng bộ; HistData không có volume thực để xác minh VWAP. Vì vậy đây là một giả thuyết từ ý tưởng bạn gửi, không phải kiểm chứng toàn bộ nội dung hoặc tái lập kết quả của tác giả.

## Quy tắc cố định trước khi chạy

1. Xét quyết định khi nến M1 đã đóng, thứ Hai–thứ Sáu, trong 08:00–12:00 giờ London hoặc 08:00–12:00 giờ New York, tự điều chỉnh DST.
2. BUY khi H1 close > EMA20 > EMA50 và M5 close > EMA20 > EMA50. SELL đối xứng. H1 chỉ lấy giờ có đủ bốn M15 đã đóng, tối thiểu 150 H1 để làm ấm, ba H1 cuối liên tục và không cũ quá một giờ.
3. BUY engulfing M1: nến trước giảm, nến mới tăng; open mới ≤ close trước, close mới ≥ open trước. SELL đối xứng. Phạm vi high/low của hai nến phải chứa EMA20 M1 và nến mới đóng về phía xu hướng của EMA20.
4. Dùng stop-entry của hệ thống: BUY chờ vượt high nến xác nhận cộng spread và một tick; SELL chờ xuyên low một tick. Tick-size của lần kiểm tra là 0,001; khoảng cách stop tối thiểu giả định bằng 0. Không vào ngay giá close.
5. SL ở ngoài low/high của hai nến thêm 0,1 ATR14 M1, làm tròn tick. Chỉ nhận khoảng entry–SL từ 1 đến 3 đơn vị giá XAUUSD (USD/ounce), không quy đổi sang “pip”. TP toàn bộ vị thế tại 2R theo giá kế hoạch. Không chốt từng phần.
6. Spread phải có và không quá 0,15 ATR M1; nến xác nhận không quá 3 ATR. Dùng kiểm tra OHLC/timestamp/liên tục/đồng bộ của hệ thống. Không áp dụng RSI/ADX như điều kiện vào lệnh riêng của bản này.
7. Một vị thế tại một thời điểm, không giới hạn một tín hiệu mỗi phiên. Risk cố định 0,5% vốn ảo. Đóng sau tối đa 120 nến nếu chưa chạm SL/TP, hoặc cuối phần dữ liệu. Đây là giới hạn giữ của bộ mô phỏng, không phải lời hứa lệnh sẽ kết thúc sau vài phút.

Chỉ báo EMA dùng TA-Lib; mỗi lần xét lấy tối đa 800 nến của từng khung M1/M5/M15 và dựng lại H1 từ M15. Bộ lọc tăng tốc chỉ bỏ các phút không có engulfing/không thuộc phiên; predict vẫn xét đủ điều kiện trên dữ liệu đóng.

## Kết quả holdout

Mỗi nguồn làm ấm 3.300 M1 trước khi chia phần còn lại 70/30 theo thời gian. Điều kiện 150 H1 có thể tiếp tục chặn tín hiệu đầu phần development; vẫn giữ cùng mốc chia với các phép thử trước. Reset vốn 10.000 USD cho từng phần, lot liên tục.

| Dữ liệu | Spread | Lệnh | Win rate | PF | Return | DD đóng lệnh |
|---|---|---:|---:|---:|---:|---:|
| MT5 09–10/2026 | Lịch sử | 2 | 50% | 1,88 | +0,44% | 0,50% |
| MT5 09–10/2026 | Lịch sử ×1,5 | 2 | 50% | 1,89 | +0,44% | 0,50% |
| HistData 2026 | 0,24 | 26 | 34,62% | 1,03 | +0,16% | 6,92% |
| HistData 2026 | 0,36 | 2 | 0% | 0 | −1,00% | 1,00% |

HistData 2026 development có 69 lệnh, +7,25%; khi tăng spread có 20 lệnh, +4,48%. MT5 development có 16 lệnh, khoảng −0,85% ở cả hai mức spread. Không chọn theo phần development đẹp hơn holdout.

Holdout HistData spread gốc có trung vị giữ 5 phút, trung bình 7,85 phút, tối đa 28 phút theo thời gian nến. Một lệnh gặp gap dữ liệu. Các giao dịch cùng phút vẫn không có thứ tự tick xác định.

## Chi phí, giới hạn và kết luận

- MT5: 50.000 M1 với spread nến lịch sử nhân point 0,001. HistData: 286.270 M1 năm 2026, spread giả định 0,24. Hai nguồn trùng một phần giai đoạn, không độc lập.
- Cả hai mức spread đều thêm commission khứ hồi giả định 0,10 đơn vị giá, slippage bất lợi 0,002 mỗi chiều; chưa tính swap và chưa xác minh biểu phí broker.
- Mô phỏng OHLC cho lệnh chờ sống một phút, khác thời hạn live 15 giây. Nếu đường giá không rõ thì ưu tiên SL, kể cả nến khớp. Gap thoát tại open kế tiếp quan sát được. Không có tick replay cho kết quả của bản này.
- DD chỉ đo equity khi đóng lệnh, không phải DD intrabar. Chưa mô phỏng Kelly, lot tối thiểu, margin, độ trễ, kiểm tra RR ròng ở bước sizing broker hoặc thao tác Enter.
- Mẫu này đã được xem trong các thử nghiệm trước. Lần chạy đầu chỉ kiểm tra 2026; sau đó đã [bổ sung năm 2024/2025](STRATEGY_SELECTION.md), vẫn chưa có dữ liệu thị trường độc lập mới. Những bộ lọc bị bỏ như tin tức/DXY có thể làm thay đổi cả số lệnh lẫn lợi nhuận.
- **Chưa đủ bằng chứng thay ORB.** HistData có nhiều lệnh hơn ORB (26 so với 10 ở cùng phần holdout), nhưng lợi nhuận sát 0, DD 6,92%, và kết quả âm khi tăng spread. Spread cao còn loại phần lớn tín hiệu, nên hai mức spread không có cùng tập lệnh. Không chỉnh tham số để làm đẹp kết quả này.

## Tái lập

```powershell
.\venv\Scripts\python.exe -u -m scripts.backtest_scalper_alternatives --strategies session_engulfing --output reports/session_engulfing
.\venv\Scripts\python.exe -m pytest tests/test_session_engulfing.py tests/test_scalper_comparison.py -q
```

Kết quả từng lệnh, summary và JSON tham số/hash nguồn/mã: `reports/session_engulfing/`. Đã đối chiếu 153 dòng giao dịch với số lệnh, tổng R, equity lũy kế, phí/slippage và thời gian vào/ra. 23 bài kiểm tra đạt; các kiểm tra mới dùng TA-Lib thật thay cho mock toàn cục của bộ test, gồm BUY/SELL, DST/phiên, H1 chưa đóng/thiếu nến, spread, cấu trúc engulfing, hướng M5, SL quá rộng và khung tương lai. Sau khi chạy chỉ sửa chú thích tick-size trong mã chiến lược, không đổi logic; hash mã lưu trong JSON thuộc phiên bản lúc chạy.
