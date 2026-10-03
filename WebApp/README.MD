# LuậtGT

Ứng dụng tra cứu giao thông, quản lý văn bản/biển báo và ôn thi hạng B. Frontend React dùng API Spring Boot thật; backend là monolith/MVC. Core KAG Python sẽ bổ sung sau, hiện chat báo dịch vụ chưa khả dụng khi chưa kết nối.

## Cấu trúc

- `frontend/`: React, TypeScript, Vite, Tailwind; trang người dùng và quản trị.
- `backend/`: một ứng dụng Spring Boot/Java 21; controller → service → repository, MySQL, Redis và MinIO.
- `docs/imports/`: 600 câu nháp, ZIP ảnh, nguồn điểm liệt và báo cáo đối chiếu.
- `scripts/`: chuẩn hóa PDF, nhập dữ liệu và kiểm tra hạ tầng/API.
- `../docker-compose.yml` và `../docker/`: stack WebApp gồm frontend, backend, MySQL, Redis, MinIO. OpenSPG nằm riêng trong `../docker-compose.kag.yml`.

## Chạy bằng Docker

Bạn tự chạy các lệnh dưới đây từ thư mục gốc repository (thư mục cha của `WebApp`). Không cần khởi động KAG trong giai đoạn này.

Nếu `.env` đã tồn tại từ cấu hình cũ, chạy `./docker/init-env.ps1 -Update` để bổ sung biến WebApp còn thiếu. WebApp dùng project `webapp` và `.env`; engine OpenSPG dùng Compose riêng, project `kag` và `.env.kag`, xem [hướng dẫn Docker](../docker/README.md#chạy-kag--openspg-độc-lập). API chat Python vẫn cần triển khai riêng. Các tính năng WebApp khác chạy được khi KAG tắt.

```powershell
# Chỉ chạy nếu chưa có .env; script không ghi đè file hiện hữu.
./docker/init-env.ps1
docker compose up -d --build
./WebApp/scripts/verify-stack.ps1
./WebApp/scripts/import-question-bank.ps1
```

Giao diện: http://127.0.0.1:8081. API: http://127.0.0.1:8080/api. Đăng nhập ADMIN bằng `ADMIN_EMAIL`/`ADMIN_PASSWORD` trong `.env`; tài khoản người học tự đăng ký, chỉ nhận USER. Nếu đổi thông tin ADMIN sau lần tạo đầu tiên, backend không tự đặt lại tài khoản đã có.

Sau khi nhập, vào **Ngân hàng câu hỏi**, đối chiếu đáp án, câu điểm liệt và ảnh rồi duyệt xuất bản. Script nhập không xuất bản tự động và mặc định bỏ qua mã đã tồn tại. Sau khi ngân hàng đủ các chương đã được duyệt:

```powershell
./WebApp/scripts/verify-stack.ps1 -WithExam
```

Script kiểm tra tạo tài khoản thử và giữ lịch sử học/thi của chúng; không sửa ngân hàng dữ liệu. Kiểm tra MySQL/Redis/MinIO, phân quyền, thu hồi JWT; `-WithExam` kiểm tra đề B, sở hữu bài, ẩn đáp án, ảnh MinIO, chấm 30/30, nộp lại và lưu tiến độ. Chỉ chạy một lượt tại một thời điểm, tránh giới hạn đăng nhập.

`mvn verify` mặc định dùng H2 chế độ MySQL và mock các dịch vụ ngoài. Build image và kiểm thử xuyên suốt trên Docker/MySQL thật cần Docker engine đang chạy; cách chạy bộ test trên database MySQL riêng có trong [backend/README.md](backend/README.md).

## Dữ liệu và nghiệp vụ

- Bộ PDF mẫu: đủ 600 câu có đáp án trích từ gạch chân, 60 câu điểm liệt đối chiếu [nguồn Chính phủ](https://xaydungchinhsach.chinhphu.vn/60-cau-hoi-ve-xu-ly-tinh-huong-mat-an-toan-giao-thong-nghiem-trong-119250513145731021.htm), 318 ảnh minh họa. Báo cáo `docs/imports/question-audit.json` ghi SHA256, các câu kiểm tra thủ công và nguồn. Tất cả vẫn là nháp, không coi trích xuất tự động là kiểm duyệt chuyên môn.
- Biển báo: nhập JSON/CSV/XLSX hàng loạt, giữ metadata pháp lý, ghép ZIP PNG/JPEG theo mã biển. Chưa có bộ dữ liệu/ảnh biển báo đầy đủ do người dùng cung cấp; ảnh trong bộ câu hỏi không tự trở thành thư viện biển báo.
- Văn bản: metadata, PDF nguồn, nháp/xuất bản, lịch sử sửa và quan hệ thay thế/sửa đổi có ngày hiệu lực; mức phạt có cấu trúc gắn với văn bản đã xuất bản/còn hiệu lực.
- Ôn tập, tiến độ và thi thử chấm bằng đáp án server đã kiểm duyệt, bản chụp bất biến khi tạo bài và thời gian server. Hạng B ghim cấu hình bộ mẫu `B-2025-06`.
- Quản trị: tài khoản, nhập dữ liệu, báo cáo, phản hồi/chat cần xử lý và kiểm tra kết nối hạ tầng thật. Trang cấu hình KAG đọc trực tiếp contract chung tại `kag/schema/schema_contract.json`; quản lý đơn vị pháp lý theo `unit_id`, `doc_id`, `parent_id` và giữ metadata nguồn. Các trang pipeline/graph/benchmark KAG vẫn hiển thị chưa triển khai.

## Phát triển local

```powershell
cd frontend
pnpm install --frozen-lockfile
pnpm dev --port 5174
# Vite proxy /api đến backend 127.0.0.1:8080
pnpm test
node node_modules/typescript/bin/tsc --noEmit
pnpm build
```

Backend/API và hợp đồng KAG: [backend/README.md](backend/README.md). Quy tắc giao diện/kiến trúc: [rule.md](rule.md). Chuẩn hóa lại PDF dùng `python scripts/prepare_question_bank.py` với `pdfplumber` và `Pillow`; script cần mạng để lấy nguồn điểm liệt. Không chạy lại nếu đã sửa thủ công bộ dữ liệu mà chưa lưu bản sao.

Kiểm tra tính toàn vẹn dữ liệu không cần mạng: `python scripts/check_question_bank.py` (600 câu nháp, 60 điểm liệt, 318 ảnh ZIP và checksum PDF). Kiểm tra này không thay thế kiểm duyệt nội dung.
