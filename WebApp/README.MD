# LuậtGT

Ứng dụng tra cứu giao thông, quản lý văn bản/biển báo và ôn thi hạng B. Frontend React dùng API Spring Boot thật; backend là monolith/MVC. Core Python có Builder, KAGIterativePlanner/Pipeline, Legal Retriever/Deduce/Safe Generator, Question Generation/Evaluation và HTTP API. Chat/citations và Admin SAMPLE đã có nghiệm thu 11–12/10/2026; không phải production acceptance. Xem [kiến trúc sản phẩm](../docs/architecture.md).

## Cấu trúc

- `frontend/`: React, TypeScript, Vite, Tailwind; trang người dùng và quản trị.
- `backend/`: một ứng dụng Spring Boot/Java 21; controller → service → repository, MySQL, Redis và MinIO.
- `docs/imports/`: 600 câu nháp, ZIP ảnh, nguồn điểm liệt và báo cáo đối chiếu.
- `scripts/`: chuẩn hóa PDF, nhập dữ liệu và kiểm tra hạ tầng/API.
- `../docker-compose.yml` và `../docker/`: stack WebApp gồm frontend, backend, MySQL, Redis, MinIO. OpenSPG nằm riêng trong `../docker-compose.kag.yml`.

## Chạy bằng Docker

Bạn tự chạy các lệnh dưới đây từ thư mục gốc repository (thư mục cha của `WebApp`). Nghiệp vụ WebApp chạy độc lập với engine OpenSPG/core Python.

Nếu `.env` đã tồn tại, `./docker/init-env.ps1 -Update` chỉ bổ sung biến WebApp còn thiếu. WebApp dùng project `webapp`; KAG dùng project `kag-s8-*` và external Step8 env, không dùng `.env.kag` lịch sử. Hai Compose khai báo 5 + 6 = 11 services. Cần image cache, graph/release/proof, provider/proxy và publication hợp lệ trước khi phục vụ SAMPLE; clone repo chưa đủ. Các tính năng WebApp khác chạy được khi KAG tắt.

Điều kiện chạy và kiểm cấu hình tại [Docker WebApp](../docker/README.md#webapp) và [KAG primary Compose](../docker/README.md#kag-primary-compose).
Sau khi stack đã chạy, từ root repository thực hiện workflow nghiệp vụ:

```powershell
./WebApp/scripts/verify-stack.ps1
./WebApp/scripts/import-question-bank.ps1
```

Giao diện: http://127.0.0.1:8081. API: http://127.0.0.1:8080/api. Đăng nhập ADMIN bằng `ADMIN_EMAIL`/`ADMIN_PASSWORD` trong `.env`; tài khoản người học tự đăng ký, chỉ nhận USER. Nếu đổi thông tin ADMIN sau lần tạo đầu tiên, backend không tự đặt lại tài khoản đã có.

Nếu đăng nhập báo `502`, kiểm tra Docker Desktop đang chạy và backend đã khởi động:

```powershell
docker compose ps -a
docker compose logs --tail=100 backend frontend
```

Frontend Nginx chuyển `/api` tới backend; `502` thường có nghĩa backend chưa sẵn sàng hoặc đã dừng. Đợi các dịch vụ khởi động xong rồi thử lại. Sai email/mật khẩu được backend trả về `401`, không phải `502`.

Sau `docker compose down`, có thể chỉ bật backend cùng MySQL, Redis và MinIO (các dịch vụ backend cần):

```powershell
docker compose up -d backend
```

API sẽ ở http://127.0.0.1:8080/api; lệnh này không bật giao diện frontend. Muốn chạy lại cả WebApp, dùng `docker compose up -d`. Các lệnh `down` giữ dữ liệu trong volume; tránh `docker compose down -v` nếu cần giữ dữ liệu.

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
- Quản trị: tài khoản, nhập dữ liệu, báo cáo, phản hồi/chat cần xử lý và kiểm tra kết nối hạ tầng thật. Trang cấu hình KAG đọc contract chung tại [`kag/schema/schema_contract.json`](../kag/schema/schema_contract.json), namespace `VietRoadTraffic`; schema có 75 thuộc tính logical, 69 thuộc tính khai báo và `id/name` kế thừa OpenSPG `Thing`. Backend đóng gói contract/schema, kiểm tra fingerprint schema theo `runtime_contract.schema_sha256` và gửi identity `{namespace, schema_sha256, contract_sha256}` cho adapter KAG. Quản lý đơn vị pháp lý theo `unit_id`, `doc_id`, `parent_id` và giữ metadata nguồn. Admin Graph đọc graph SAMPLE; Pipeline hiển thị slot runtime/receipt; Benchmark đọc dataset eligibility và kết quả đã có. Các trang không chạy build/benchmark.

Native `AnswerResult` có abstention và document/sign support citations, còn Java
chỉ chấp nhận 1..20 LegalUnit citations đã xuất bản/còn hiệu lực với exact quote.
Không thể nối bằng cách serialize trực tiếp hoặc bỏ citations không vừa schema.
[Hợp đồng HTTP](../docs/architecture.md#hợp-đồng-http-và-chính-sách-tương-thích)
giữ fail-closed và tách v1 với full native contract tương lai.
Health MySQL/Redis/MinIO không chứng minh KAG readiness. SAMPLE gồm 32 nodes /
22 edges / 42 vectors; bộ câu hỏi chính thức chưa hoàn thành. Production WRITE BLOCKED.

## Phát triển local

Lệnh cài/chạy/test/typecheck/build frontend được duy trì tại
[frontend/README.md](frontend/README.md#phát-triển-và-kiểm-thử), có cwd tường minh
và Vite proxy `/api` đến backend `127.0.0.1:8080`.

Backend/API và hợp đồng KAG: [backend/README.md](backend/README.md). Quy tắc giao diện/kiến trúc: [rule.md](rule.md). Các lệnh Python dưới đây chạy từ `WebApp/`, không phải root hoặc `frontend/`. Chuẩn hóa lại PDF dùng `python scripts/prepare_question_bank.py` với `pdfplumber` và `Pillow`; script cần mạng để lấy nguồn điểm liệt và ghi lại assets/nháp. Không chạy lại nếu đã sửa thủ công bộ dữ liệu mà chưa lưu bản sao.

Kiểm tra tính toàn vẹn dữ liệu không cần mạng: `python scripts/check_question_bank.py` (600 câu nháp, 60 điểm liệt, 318 ảnh ZIP và checksum PDF). Kiểm tra này không thay thế kiểm duyệt nội dung.
