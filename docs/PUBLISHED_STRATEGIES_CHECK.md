# Kiểm chứng các chiến lược được tìm trên Internet

Ngày kiểm tra: 01/11/2026. Đã kiểm tra toàn bộ các hướng được nêu: Time Series
Momentum, trend following AQR, Donchian/Turtle và Forecast-to-Fill.

**Có ứng viên có lãi trong backtest dài hạn, nhưng chưa có bản nào được xác nhận
lợi nhuận live trên tài khoản này. Theo yêu cầu thay ứng viên của người dùng,
Donchian 55/20 D1 một unit hiện được chọn làm mặc định cho assistant demo,
ưu tiên độ bền theo chi phí và drawdown thay vì CAGR cao nhất.**

## Dữ liệu và phạm vi

- HistData: 2.790 nến D1, 04/01/2016–23/10/2026. Đã tải thêm M1 2016–2023,
  kết hợp mẫu sạch 2024–2026. Ranh giới phiên cố định 22:00 UTC. Không điền phút thiếu.
- MT5: 2.649 nến D1, 09/08/2016–29/10/2026. Gộp 524 nến Chủ nhật ngắn vào thứ Hai.
  Giữ phiên broker, không ép hai nguồn trùng giá hay giờ đóng cửa.
- Hai cửa sổ đánh giá: từ 2018 và từ 2024; dùng lịch sử trước đó cho chỉ báo.
  Hai cửa sổ giao nhau, không cộng thành hai tập độc lập. Năm 2026 chưa đầy đủ.
- 8 phương pháp gồm mua giữ làm đối chứng; 2 nguồn × 2 cửa sổ × 3 kịch bản
  chi phí × 8 phương pháp = **96 trường hợp**. Không tối ưu tham số theo lợi nhuận.

Các phiên HistData có ít hơn 1.000 phút được giữ và gắn thống kê trong manifest
(58 phiên). Một số có thể là ngày giao dịch ngắn hoặc dữ liệu thiếu, cần đối chiếu
tick trước khi khẳng định các mức phá đỉnh/đáy và stop là hoàn chỉnh.

## Kết quả MT5 từ 2018 đến 29/10/2026

Spread giả định 0,24, phí khứ hồi 0,10 và slippage 0,002 mỗi chiều, đơn vị giá
trên ounce. Phí giữ vị thế giả định 3%/năm trên trị tuyệt đối notional, tính cả
cuối tuần và cả hai hướng. Đây **không phải swap thực tế đã xác minh của broker**.

| Phương pháp | CAGR mô phỏng | Drawdown đóng ngày |
| --- | ---: | ---: |
| Mua giữ vàng 1× | 11,52% | 32,14% |
| Momentum 12 tháng, vol target 40%, cap 2× | 8,95% | 66,87% |
| Trend 1/3/12 tháng, tái cân bằng tuần, cùng risk target | 10,29% | 56,43% |
| Donchian 20/10, một unit | 0,34% | 5,67% |
| **Donchian 55/20, một unit** | **2,00%** | **4,59%** |
| Turtle S1, bộ lọc lệnh trước, một unit | 0,73% | 4,58% |
| Turtle S1, tối đa 4 unit | 1,36% | 18,97% |
| Turtle S2, tối đa 4 unit | 5,37% | 21,34% |

HistData cho hướng kết quả tương tự: Donchian 55/20 đạt CAGR 1,98%, DD 4,15%;
momentum 12 tháng đạt 8,77% nhưng DD 67,36%. Không coi kiểm tra hai nguồn cùng
thời kỳ là bằng chứng từ hai thị trường độc lập.

Donchian 55/20 trong ca spread 0,36 và phí giữ vị thế 8%/năm vẫn dương:
CAGR 1,33%, DD 5,60% trên MT5; CAGR 1,31%, DD 5,65% trên HistData.
Đây là độ nhạy theo giả định chi phí, không bảo đảm sẽ vượt mọi mức swap broker.

## Kết luận theo từng hướng

**Time Series Momentum:** có thể có lợi nhuận mô phỏng dài hạn, nhưng khi áp dụng
riêng vàng với target vol 40% và cap 2×, drawdown lớn. Trong ca financing 8%,
bản 12 tháng âm CAGR trên cả hai nguồn. Không chọn chỉ dựa vào CAGR gần đây cao.
Nghiên cứu gốc dùng futures excess returns và nhiều tài sản; bản này dùng spot,
EWMA volatility alpha 0,02, tái cân bằng tháng và khớp open phiên tiếp theo.
[Nguồn gốc](https://www.aqr.com/insights/research/journal-article/time-series-momentum).

**AQR trend following:** đã kiểm tra bản áp dụng riêng vàng với tín hiệu trung bình
1/3/12 tháng, cập nhật tuần. Không tái lập danh mục AQR đầy đủ vì thiếu chuỗi rolled
futures của các tài sản khác và mô hình chi phí/risk của danh mục đó.
[Phương pháp công bố](https://www.aqr.com/-/media/AQR/Documents/Insights/Journal-Article/Demystifying-Managed-Futures.pdf).

**Donchian/Turtle:** trong các ca đã chạy, 55/20 một unit là ứng viên ưu tiên cho
demo nếu mục tiêu là drawdown thấp. Khoảng 36 vòng vào/thoát trên mẫu dài và 9
vòng trên mẫu từ 2024 là ít; lựa chọn sau khi xem nhiều phương pháp còn có rủi ro
thiên lệch chọn mẫu. Lợi nhuận phần lớn đến từ giữ xu hướng; không chứng minh alpha
so với mua giữ. Risk khác nhau nên không so CAGR đơn thuần để xếp hạng.

Bản Turtle dùng N=Wilder ATR20, SL 2N, thêm unit mỗi 0,5N, tối đa 4 unit; S1 có
lọc lệnh 20/10 giả lập trước và failsafe 55 ngày. Risk giảm còn 0,5%/unit, cap
notional 2× tại mỗi lần vào/thêm, không có cơ chế giảm notional theo drawdown hay
giới hạn tương quan nhiều thị trường của hệ gốc. Không vào lại trong ngày sau
khi thoát; thứ tự entry/stop hoặc add/stop mơ hồ được tính bất lợi. Vì vậy đây là
**bản điều chỉnh được công khai**, không gắn nhãn bản sao chính xác hệ Turtle gốc.
[Quy tắc gốc](https://www.tradingblox.com/originalturtles/originalturtlerules.pdf).

**Forecast-to-Fill:** chưa tái lập được. Thiếu tham số fit theo từng fold; quy tắc
giảm vị thế chưa duy nhất. Số 43% là quy đổi risk, không tương đương kết quả gốc;
baseline T+1 và bảng latency chưa thống nhất. Chưa có kiểm chứng live.
Không tự chọn tham số thay thế để báo kết quả của bài viết.
[Bài được kiểm tra](https://arxiv.org/html/2511.08571v1).

## Giới hạn thực thi

Equity khởi đầu 10.000 USD, giao dịch ounce liên tục; chưa mô phỏng lot tối thiểu,
margin call, thuế, lịch swap thật hay phí futures roll. Cash không được trả lãi.
Financing trong các ca 0%, 3%, 8% là giả định chung, không quy đổi swap hiện tại
thành lịch sử. Equity được mark theo close mỗi ngày, gồm phí giữ và lãi/lỗ thả nổi;
DD không bao gồm cực trị intraday. Sharpe dùng cash rate 0 và annualization 252.

Các mức channel/ATR chỉ dùng nến trước. TSMOM quyết định trước open khớp; giữ
nguyên số ounce giữa các kỳ tái cân bằng. Tại cuối cửa sổ, mọi vị thế đều được
thanh lý và tính chi phí. Có kiểm tra hồi quy thay đổi giá tương lai mà không
làm đổi tín hiệu hay equity quá khứ, và kiểm tra phí cuối tuần, gap xuyên SL.

Không chuyển kết quả D1 thành nhãn lợi nhuận cho M1. Chưa có giao dịch demo/live
độc lập mới theo ứng viên 55/20; giữ trạng thái nghiên cứu.

## Tái lập và kiểm tra chi tiết

```powershell
.\venv\Scripts\python.exe -u -m scripts.prepare_daily_research_data
.\venv\Scripts\python.exe -u -m scripts.check_published_strategies
```

Kết quả nằm trong `reports/published_strategies/`:

- `REPORT.md`, `summary.csv`: đủ 96 trường hợp, kể cả các ca bất lợi.
- `yearly.csv`: lợi nhuận từng năm; 2026 là một phần năm.
- `audit.json`: trạng thái tái lập và khác biệt với các nguồn công bố.
- `data/manifest.json`: nguồn, phiên giao dịch, gap, SHA256 dữ liệu.
- Mỗi thư mục kết quả có `equity.csv`, `orders.csv`, `report.json` và SHA256 mã nguồn.

ZIP cũ được cache; dùng lại cache để tái lập. Các CSV/ZIP/report trong `reports/`
được Git bỏ qua theo cấu hình dự án hiện có.
