# LuậtGT

Ứng dụng tra cứu pháp luật giao thông, quản lý văn bản/biển báo và ôn thi hạng B. React gọi API Spring Boot; chat tích hợp KAG Python. Xem [kiến trúc sản phẩm](../docs/architecture.md) để biết các thành phần và giới hạn phục vụ.

## Cấu trúc

- [frontend/](frontend/README.md): giao diện React/TypeScript/Vite.
- [backend/](backend/README.md): monolith Spring Boot/Java 21 theo MVC; dùng MySQL, Redis và MinIO.
- `docs/imports/`: câu hỏi nháp, ZIP ảnh và metadata nguồn.
- `scripts/`: chuẩn hóa, nhập câu hỏi và kiểm tra hạ tầng/API.

## Chạy bằng Docker

Khởi tạo môi trường và chạy stack từ root repository theo [Docker WebApp](../docker/README.md#webapp). Nếu đã có `.env`, `./docker/init-env.ps1 -Update` bổ sung biến còn thiếu.

WebApp và KAG có Compose/env riêng. Chat cần KAG ingress, token files, release/proof và dữ liệu WebApp đã xuất bản khớp nguồn; xem [KAG primary Compose](../docker/README.md#kag-primary-compose). Clone repository chưa đủ để phục vụ chat.

Giao diện: `http://127.0.0.1:8081`. API: `http://127.0.0.1:8080/api`. ADMIN được bootstrap bằng `ADMIN_EMAIL`/`ADMIN_PASSWORD`; người học tự đăng ký USER. Đổi env không đặt lại tài khoản ADMIN đã có.

Sau khi stack chạy, từ root repository:

```powershell
./WebApp/scripts/verify-stack.ps1
./WebApp/scripts/import-question-bank.ps1
```

Script nhập giữ câu hỏi ở trạng thái nháp, bỏ qua mã đã tồn tại. Vào **Ngân hàng câu hỏi**, đối chiếu nguồn, đáp án, điểm liệt và ảnh trước khi duyệt xuất bản. Khi đủ câu đã duyệt cho các chương, kiểm tra luồng thi:

```powershell
./WebApp/scripts/verify-stack.ps1 -WithExam
```

Script kiểm tra tạo tài khoản thử và giữ lịch sử học/thi của chúng; `-WithExam` cần ngân hàng đã xuất bản. Chạy từng lượt để tránh giới hạn đăng nhập.

## Dữ liệu và nghiệp vụ

- Bộ câu hỏi đi kèm gồm 600 câu nháp, 60 câu điểm liệt và 318 ảnh. Dữ liệu trích PDF vẫn cần kiểm duyệt; không tự xuất bản.
- Biển báo nhập JSON/CSV/XLSX cùng ZIP PNG/JPEG theo mã; cần nguồn pháp lý và ảnh được duyệt.
- Văn bản giữ PDF nguồn, metadata, phiên bản, ngày hiệu lực và quan hệ sửa đổi/thay thế. Mức phạt gắn với văn bản được phép tra cứu.
- Thi hạng B dùng cấu hình `B-2025-06`: 30 câu, 20 phút, đạt từ 27 và không sai/bỏ trống câu điểm liệt. Server chấm bằng đáp án đã duyệt và snapshot bài thi.
- Admin Graph/Pipeline/Benchmark đọc SAMPLE, receipt và dataset eligibility; Retrieval có thao tác kiểm tra giới hạn. Các trang này không chạy builder hoặc benchmark.

SAMPLE dùng cho phạm vi kiểm tra đã cấu hình. Production WRITE bị chặn; bộ câu hỏi benchmark chính thức chưa hoàn thành. Health MySQL/Redis/MinIO không xác nhận KAG readiness.

## Phát triển local

Lệnh chạy Java và kiểm thử database: [backend](backend/README.md#chạy). Lệnh cài/chạy/test/typecheck/build UI: [frontend](frontend/README.md#phát-triển-và-kiểm-thử). Quy tắc giao diện và MVC: [rule.md](rule.md).

Các lệnh dưới đây chạy từ `WebApp/`:

```powershell
python scripts/check_question_bank.py
python scripts/prepare_question_bank.py
```

`check_question_bank.py` kiểm số lượng, ảnh và checksum offline. `prepare_question_bank.py` cần `pdfplumber`, `Pillow` và mạng để lấy nguồn điểm liệt; ghi lại assets/nháp. Sao lưu các chỉnh sửa thủ công trước khi chuẩn hóa lại. Cả hai không thay thế kiểm duyệt nội dung.
