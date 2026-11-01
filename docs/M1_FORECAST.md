# Dự báo hướng XAUUSD 5 phút, quan sát và vào lệnh trên M1

Đã thêm mô hình dự báo ba lớp để quan sát cùng kế hoạch vào lệnh M1. Đây là mô hình nghiên cứu, chưa có chiến lược giao dịch sinh lời được xác nhận và không thay đổi tín hiệu/lot hoặc tự đặt lệnh.

## Dự báo điều gì?

Sau khi nến M1 đóng, mô hình ước tính ba xác suất cho giá close sau đúng 5 phút:

- **UP:** tăng vượt ngưỡng.
- **DOWN:** giảm vượt ngưỡng.
- **FLAT:** biến động tuyệt đối chưa vượt ngưỡng; không có nghĩa là giá đứng yên.

Ngưỡng bằng max(0,25 ATR14 M1; 0,344 đơn vị giá). Số 0,344 gồm spread giả định 0,24 + commission khứ hồi 0,10 + slippage 0,002 mỗi chiều. Đây không phải phí broker đã xác minh. Ngưỡng này là định nghĩa nhãn nghiên cứu, không phải dự báo chính xác giá hay SL/TP.

Mô hình dùng hồi quy logistic đa lớp, đặc trưng giá M1, biến động và EMA20/50 trên M5/M15 đã đóng. Không dùng volume giả của HistData, DXY, lịch tin hoặc dữ liệu tương lai. Mô hình ước tính xác suất hướng giá, **không phải xác suất TP trước SL**. Đường đi trong 5 phút có thể chạm SL rồi mới đi đúng hướng.

## Cách kiểm tra

- Huấn luyện trên HistData 2024 đến trước 01/09/2025: 111.872 mẫu.
- Chọn temperature trong {0,5; 1; 1,5; 2} theo log loss của giai đoạn 09–12/2025: 22.592 mẫu. Không huấn luyện lại hệ số sau hiệu chỉnh.
- Kiểm tra năm 2026, không dùng nhãn 2026 để fit hoặc chọn temperature. Tại các ranh giới, loại mẫu có thời điểm hoàn tất nhãn đi qua ranh giới.
- Chọn mẫu mỗi 5 phút theo đồng hồ để khoảng nhãn không chồng lên nhau; dự báo trên terminal vẫn có thể cập nhật mỗi nến M1. Loại nhãn đi qua phút thiếu và loại bối cảnh M5/M15 chưa đóng hoặc cũ.
- Baseline cố định dùng phân bố lớp của tập huấn luyện. Baseline momentum đơn giản dùng hướng biến động 5 phút vừa qua và cùng ngưỡng nhãn.

| Tập kiểm tra | Số mẫu | Accuracy mô hình | Baseline cố định | Momentum đơn giản |
|---|---:|---:|---:|---:|
| HistData 2026 | 51.002 | 42,88% | 42,32% | 37,53% |
| MT5 09–10/2026 | 9.372 | 41,27% | 40,65% | 37,56% |

Log loss HistData 1,0443 so với baseline 1,0647; MT5 1,0486 so với 1,0685 (thấp hơn tốt hơn). Multiclass Brier lần lượt 0,6333 và 0,6362. Các điểm số này không tự chứng minh xác suất đã hiệu chỉnh tốt trong mọi chế độ thị trường; cần theo dõi reliability trên dữ liệu mới. Xem [tài liệu calibration của scikit-learn](https://scikit-learn.org/stable/modules/calibration.html).

**Mức cải thiện accuracy chỉ khoảng 0,56–0,62 điểm phần trăm so với baseline cố định. Chưa đủ để đưa ra quy tắc BUY/SELL dựa riêng vào mô hình.** Chưa mô phỏng lợi nhuận của việc kết hợp mô hình với stop-entry M1, SL/TP và hạn chờ của bot. Vì vậy không lấy accuracy này làm win rate giao dịch.

Hai nguồn trùng giai đoạn, không độc lập. Dữ liệu 2026 đã được xem trong các thử nghiệm chiến lược trước; đây là tách thời gian đối với lần fit mô hình này, chưa phải kiểm chứng độc lập trên dữ liệu mới. Chưa kiểm chứng BTCUSD hoặc broker khác. Nhãn MT5 cũng dùng ngưỡng chi phí giả định thống nhất 0,344 để so sánh, không dùng spread thực tế biến thiên của broker.

## Chạy

Huấn luyện và tái tạo JSON mô hình:

```powershell
.\venv\Scripts\python.exe -m scripts.train_m1_forecast
```

Hiển thị dự báo cùng cấu hình M1/M5:

```powershell
.\venv\Scripts\python.exe run_mt5_assistant.py --symbol XAUUSD --profile scalping --forecast-model reports/m1_forecast/model.json --color always
```

Mô hình cho phép `XAUUSD` và `XAUUSDc`, từ chối BTCUSD. Với tên broker khác cần kiểm chứng dữ liệu trước khi mở phạm vi. CLI không tự tải mô hình hoặc tự train. Nếu thiếu file, sai symbol hoặc thiếu dữ liệu, phần dự báo hiển thị UNAVAILABLE; kế hoạch chiến lược hiện có vẫn tách riêng. Không dùng cùng profile D1.

Khi nhấn Enter, bot dùng nến M1 đã đóng mới nhất; bộ dự báo có thể giữ nguyên trong cùng nến, dù tick hiện tại đã thay đổi. Mốc 5 phút tính từ close nến xác nhận, không từ lúc lệnh stop thực sự khớp. Giá thị trường vẫn phải vượt điều kiện entry của chiến lược nếu bạn quyết định đặt lệnh thủ công. Feature trên terminal được làm ấm bằng khoảng 5.000 M1 nên có thể khác nhẹ phép tính trên lịch sử tích lũy.

Artifact trong `reports/m1_forecast/`: `model.json` chứa hệ số/scaler/temperature và mốc chia, `evaluation.json` chứa điểm số/hash dữ liệu/mã, `predictions_2026.csv` chứa từng dự báo HistData kiểm tra. JSON chỉ chứa dữ liệu số, không tải pickle hay mã thực thi. Các artifact reports được Git bỏ qua như các báo cáo trước.

Kiểm tra tự động gồm thay đổi giá tương lai không làm đổi đặc trưng quá khứ, so với chỉ cung cấp tiền tố dữ liệu, nhãn không qua gap, chuẩn hóa xác suất, kiểm tra symbol/tham số và nhãn hiển thị xác suất.
