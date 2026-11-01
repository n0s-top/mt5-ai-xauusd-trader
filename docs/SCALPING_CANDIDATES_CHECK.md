# Kiểm chứng các ứng viên scalping trên XAUUSD

Đã chạy 36 trường hợp, mỗi trường hợp có development và holdout riêng: 72 sổ lệnh/equity. Chưa đủ bằng chứng chọn một chiến lược có lợi nhuận ổn định. Không thay cấu hình bot hay đặt lệnh.

## Kết quả sau chi phí

Bảng dùng kịch bản `fee_carry3pct`: spread lịch sử MT5 hoặc spread giả định 0,24 cho HistData, commission khứ hồi 0,10 đơn vị giá, slippage 0,002 mỗi chiều, financing giả định 3%/năm. Đây không phải biểu phí/swap broker đã xác minh. Return tính trong phần 30% cuối của từng bộ dữ liệu, không phải lợi nhuận năm.

| Nguồn | Biến thể | Lệnh holdout | Return | PF | DD close M1 |
| --- | --- | ---: | ---: | ---: | ---: |
| MT5 09–10/2026 | ORB 5m | 10 | +3,78% | 2,95 | 2,03% |
| MT5 09–10/2026 | ORB 15m | 11 | +2,70% | 2,24 | 1,94% |
| MT5 09–10/2026 | ORB 5m + RVOL tick | 4 | +2,51% | 4,93 | 1,68% |
| MT5 09–10/2026 | ORB 15m + RVOL tick | 5 | +2,18% | 3,37 | 1,49% |
| MT5 09–10/2026 | Noise Area + VWAP tick | 13 | +1,44% | 1,65 | 1,74% |
| MT5 09–10/2026 | EMA/VWAP M15 proxy | 9 | +1,21% | 2,15 | 0,69% |
| HistData 2024 | ORB 5m | 74 | +11,84% | 1,87 | 2,90% |
| HistData 2024 | ORB 15m | 68 | +2,04% | 1,16 | 2,90% |
| HistData 2025 | ORB 5m | 76 | −7,51% | 0,62 | 10,93% |
| HistData 2025 | ORB 15m | 66 | +1,60% | 1,09 | 7,41% |
| HistData 2026 | ORB 5m | 51 | −9,08% | 0,33 | 9,23% |
| HistData 2026 | ORB 15m | 49 | −7,30% | 0,42 | 9,15% |

Mẫu MT5 chỉ 50.000 nến M1; mỗi biến thể có 4–13 lệnh holdout nên chưa thể xếp hạng đáng tin cậy. HistData có 995.813 nến M1 năm 2024–2026. Các giai đoạn hai nguồn trùng nhau không độc lập. ORB 15m chịu chi phí tốt hơn ORB 5m trong một số năm, nhưng cả hai đều lỗ trên phần cuối 2026. Không tối ưu lại thông số để sửa kết quả âm.

## Phạm vi kiểm chứng và nguồn

1. [Nghiên cứu ORB gốc](https://alexandria.unisg.ch/server/api/core/bitstreams/3c2989c4-688d-4d78-8a71-f02690990d51/content) nghiên cứu cổ phiếu Mỹ và lựa chọn cổ phiếu theo relative volume. Bản vàng dùng phiên New York 09:30–16:00, có DST; range 5 hoặc 15 phút đầu. Hướng giao dịch theo thân range đầu; phá high/low thêm 0,001, SL cách entry 0,1 ATR14 của các phiên trước; tối đa một lệnh/phiên, không TP, đóng cuối phiên. ATR ở đây tính trên phiên vàng 09:30–16:00, khác dữ liệu daily cổ phiếu. RVOL tick so tổng tick volume range đầu với 14 phiên trước, ngưỡng ≥1. Không tái tạo bộ lọc cổ phiếu, top 20 hay volume tập trung.
2. [Mã nghiên cứu Noise Area/VWAP của tác giả](https://concretumgroup.com/python-backtesting-beat-the-market-an-effective-intraday-momentum-strategy-for-the-sp500-etf-spy/) dành cho SPY. Bản vàng lấy trung bình 14 quan sát trước của absolute return từ open ở cùng phút; biên trên/dưới điều chỉnh theo open hôm nay và close phiên trước. Xét tín hiệu mỗi 30 phút; close vượt cả biên trên và VWAP thì mua, dưới cả biên dưới và VWAP thì bán, còn lại flat. Thi hành tại open phút kế tiếp. Sizing ở đây khác volatility targeting của tác giả. Không có hard SL intrabar: khoảng cách tới biên chỉ dùng để sizing, không giới hạn chắc chắn khoản lỗ.
3. [Bài EMA/VWAP trên vàng được tham chiếu](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6650958): không truy cập được toàn văn từ nguồn gốc (HTTP 403), nên chưa xác minh đầy đủ phương pháp và kết quả công bố. `ema_vwap15_tick_proxy` là quy tắc thử nghiệm minh bạch, không phải tái lập bài báo: M15 hoàn chỉnh; EMA50/200 trên toàn bộ nến M15; long khi close và EMA50 trên EMA200, low chạm EMA50, close vượt EMA50/open/VWAP phiên; short đối xứng. SL low/high nến tín hiệu ±0,5 ATR14, TP 3 lần khoảng cách giá Bid entry–SL, thoát khi close M15 vượt EMA50 ngược hướng. Không mô phỏng bộ lọc tin tức, chốt một phần hoặc các điều kiện chưa xác minh.

HistData chỉ có volume 0 thay thế; **không thể kiểm tra VWAP hoặc RVOL thực trên nguồn này**. `audit.csv` đánh dấu 12 cặp nguồn/năm/phương pháp thiếu volume; không gán lợi nhuận bằng 0 cho các trường hợp không chạy. Trên MT5, tick volume chỉ là số lần cập nhật giá tại broker, không tương đương khối lượng giao dịch toàn thị trường.

## Quy tắc mô phỏng chung

- OHLC được coi là Bid; BUY vào Ask/thoát Bid, SELL vào Bid/thoát Ask. Spread hằng trong từng nến, không có đường đi tick. Phải xác minh quy ước giá/giờ broker trước khi dùng kết quả để giao dịch.
- Chỉ dùng nến đã đóng cho chỉ báo; range ORB kết thúc trước thời điểm cho phép entry; quyết định từ close vào open kế tiếp. Thiếu nến mở phiên thì bỏ range đó. Phiên thiếu phút vẫn được ghi nhận; báo cáo lưu số phiên thiếu. Sigma dùng 14 quan sát cùng phút có sẵn trước đó.
- Đang giữ gặp phút thiếu thì thoát tại open tiếp theo quan sát được, chịu spread/slippage/financing cả thời gian gap. Thoát cuối phiên ở open đầu tiên tại/sau 16:00; dữ liệu thiếu có thể khiến thời điểm thoát trễ. Không giả định có giá trong khoảng thiếu.
- Nến chạm cả SL/TP chọn SL trước. ORB chạm entry và SL trong cùng nến tính stop bất lợi, đánh dấu ambiguous. EMA vào ở open nên kiểm tra ngay SL/TP trong nến entry. DD từ equity tại close M1 chưa phản ánh cực trị intraminute.
- Equity đầu mỗi phần 10.000; sizing tối đa 0,5% theo khoảng cách stop/biên và phí, notional tối đa 2x, ounce liên tục, không pyramiding. Không mô phỏng lot step, margin call hay thanh khoản broker. Gap có thể làm lỗ vượt mức dự kiến.
- Bỏ 200 nến đầu, phần còn lại chia thời gian 70/30, giữ lịch sử chỉ báo trước điểm chia; reset vốn và ép đóng vị thế cuối mỗi phần. Đây là holdout theo thời gian, không phải dữ liệu hoàn toàn chưa từng được xem trong các lần nghiên cứu trước.
- Ba kịch bản: spread/slippage không commission/financing; thêm fee và carry 3%; stress spread ×1,5, cùng fee và carry 8%. Không cộng kết quả các kịch bản với nhau.

## Chạy lại và kiểm tra

```powershell
.\venv\Scripts\python.exe -m scripts.check_scalping_candidates
.\venv\Scripts\python.exe -m scripts.audit_scalping_results
.\venv\Scripts\python.exe -m pytest tests/test_intraday_candidates.py -q
```

[Summary đầy đủ](../reports/scalping_candidates/summary.csv) lưu 72 dòng. [Audit nguồn](../reports/scalping_candidates/audit.csv) lưu trạng thái hỗ trợ. Mỗi thư mục trường hợp có `trades.csv`, `report.json`, `equity_development.npz`, `equity_holdout.npz`; JSON lưu SHA256 dữ liệu/mã nguồn và thời điểm chia. Các file trong reports được sinh cục bộ, không mặc định đưa vào Git.

Audit độc lập đã đối chiếu đủ 72 phần: tổng PnL với equity cuối, số lệnh, commission, financing, DD tính lại từ curve, giới hạn risk/notional và hash. Năm test mới kiểm tra tính nhân quả khi thay giá tương lai, thiếu volume, DST/range thiếu phút, SL ngay nến entry cho BUY/SELL và hạch toán chi phí.

## Kiểm tra toàn dự án

Lần chạy `python -m pytest -q` sau thay đổi: **1.197 passed, 14 failed, 10 skipped, 4 errors**, tổng 1.225 test, 95,53 giây. Không thể coi toàn dự án đã đạt kiểm thử. Chạy riêng 29 test trong `test_intraday_candidates.py`, `test_donchian_m1.py`, `test_published_strategies.py`: tất cả đạt; lint các file mới đạt.

Các điểm cần xử lý ngoài bộ backtest mới:

- Bốn lỗi thiết lập: thiếu fixture `mocker` trong ba test decision support và một test reporting.
- Hai test governance về CODEOWNERS/quality gates thất bại.
- Bảy test model persistence/signature/path validation và config directory hardening thất bại.
- Một test PPO reshaping, hai test report/template rendering, một test bootstrap/execution audit và một test kiểm tra dependency thất bại.

Các nhóm lỗi trên chưa được sửa trong lần kiểm chứng chiến lược này; chưa xác định toàn bộ nguyên nhân hoặc phân biệt đầy đủ lỗi nền với ảnh hưởng thứ tự chạy. Không được hạ kiểm tra bảo mật hay bỏ test để làm kết quả xanh.
