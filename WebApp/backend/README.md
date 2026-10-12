# Backend LuậtGT

Spring Boot 3.5.16 / Java 21, monolith theo MVC. Backend phục vụ REST/SSE, quản lý tài khoản, nội dung, học/thi và tích hợp KAG Python. Xem [kiến trúc](../../docs/architecture.md).

## Cấu trúc

```text
src/main/java/vn/luatgt/
├── controller/    Nhận HTTP, kiểm DTO, gọi service
├── dto/           Request DTO và ràng buộc đầu vào
├── service/       Nghiệp vụ và giao dịch
├── repository/    Spring Data JPA và khóa bản ghi
├── model/         JPA entity
├── integration/   KAG HTTP và MinIO
├── config/        Security/JWT và giới hạn request
└── exception/     Chuyển lỗi nghiệp vụ thành HTTP
src/main/resources/
├── application.yml
└── db/migration/  Flyway
```

Controller không truy cập repository; API không trả entity trực tiếp. Các package chạy trong một ứng dụng, dùng một MySQL.

## Chạy

Chạy stack theo [Docker WebApp](../../docker/README.md#webapp). API ở `http://127.0.0.1:8080/api`, health ở `/actuator/health`.

Để chạy Java trên host, chuẩn bị MySQL/Redis/MinIO và đặt biến môi trường theo [application.yml](src/main/resources/application.yml): `DB_PASSWORD`, `REDIS_URL`, `JWT_SECRET`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `MINIO_USER`, `MINIO_PASSWORD`. Đặt thêm `DB_URL`, `DB_USER`, `MINIO_URL` nếu khác mặc định. `REDIS_URL` phải chứa mật khẩu khi Redis yêu cầu xác thực; Java không tự đọc `.env`.

Từ `WebApp/backend/`, với Java 21 và Maven:

```powershell
mvn spring-boot:run
```

ADMIN bootstrap chỉ tạo khi email chưa tồn tại; không đặt lại mật khẩu hoặc nâng USER thành ADMIN. Tự đăng ký chỉ tạo USER.

Kiểm thử mặc định dùng H2 chế độ MySQL và mock dịch vụ ngoài:

```powershell
mvn verify
```

H2 không thay thế MySQL thật. Để chạy cùng suite trên MySQL, chỉ dùng **database kiểm thử riêng, rỗng**: Flyway và tests sẽ tạo bảng/tài khoản/nội dung. Từ `WebApp/backend/`:

```powershell
$env:TEST_DB_URL = "jdbc:mysql://127.0.0.1:3306/luatgt_test?connectionTimeZone=UTC&forceConnectionTimeZoneToSession=true"
$env:TEST_DB_USER = "luatgt_test"
$env:TEST_DB_PASSWORD = "<mật khẩu kiểm thử>"
mvn verify
Remove-Item Env:TEST_DB_URL, Env:TEST_DB_USER, Env:TEST_DB_PASSWORD
```

## API

Tiền tố `/api`; mọi API trừ đăng ký, đăng nhập và health yêu cầu `Authorization: Bearer <accessToken>`. JWT hết hạn sau một giờ. Logout hoặc khóa tài khoản thu hồi token.

- Tài khoản: `/auth/register`, `/auth/login`, `/auth/me`, `/auth/logout`.
- Học/thi: `/questions`, `/study/{questionId}/answer`, `/progress`, `/exams`; đáp án JSON dùng chỉ số từ 0.
- Tra cứu: `/documents`, `/units`, `/signs`, `/penalties`; USER chỉ thấy nội dung được phép tra cứu.
- Chat: `POST /chat`, `POST /chat/stream`, `GET /chat`; lịch sử gắn với tài khoản.
- Quản trị: `/admin/imports/{questions|signs|documents|units}/preview` và `/confirm`, nội dung/xuất bản, tài khoản, phản hồi, báo cáo và hạ tầng.

Endpoint và DTO cụ thể nằm trong [controller](src/main/java/vn/luatgt/controller/) và [dto](src/main/java/vn/luatgt/dto/). Preview không ghi; confirm kiểm lại và ghi toàn bộ hoặc rollback. Sửa/xuất bản dùng version chống ghi đè.

Thi hạng B ghim `B-2025-06`: 30 câu, 20 phút, đạt từ 27 và không sai/bỏ trống câu điểm liệt. Server giữ thời gian, đáp án và ảnh snapshot; kiểm quyền sở hữu bài thi. Cấu hình này không tự cập nhật theo thay đổi quy định.

## Chuẩn hóa dữ liệu

Schema dùng chung: [schema_contract.json](../../kag/schema/schema_contract.json) và [VietRoadTraffic.schema](../../kag/schema/VietRoadTraffic.schema), namespace `VietRoadTraffic`. Maven đóng gói hai file; backend kiểm SHA-256 của schema. Thay schema/contract cần build lại backend.

UUID là khóa quản trị; `externalId` giữ nguyên `doc_id`, `unit_id`, `sign_id` nguồn. Import nhận snake_case nguồn hoặc alias graph từ contract, từ chối ID/alias xung đột và kiểu sai. Bản nháp có thể thiếu trường graph; xuất bản WebApp không xác nhận ingestion readiness.

`LegalUnit` giữ hierarchy cùng văn bản; chặn cha thiếu, chu trình và cha khác văn bản. Xuất bản cần `reviewed=true` và văn bản nguồn đã xuất bản. Câu hỏi cần xác nhận đáp án/điểm liệt/ảnh; biển báo cần ảnh và metadata pháp lý tương ứng. Mức phạt dùng số nguyên không âm và văn bản nguồn hợp lệ.

MinIO lưu tệp; DB giữ khóa và MIME. Backend nhận PNG/JPEG tối đa 5 MB, 4096×4096; PDF 20 MB; ZIP 20 MB nén, 50 MB giải nén, 1000 mục. ZIP câu hỏi ghép theo `externalId`, ZIP biển báo theo `ma_bien`; mã có nhiều biến thể trả `unmatched` để gắn thủ công. SVG/WebP chưa được nhận.

Luồng nhập câu hỏi và kiểm duyệt: [WebApp](../README.MD#dữ-liệu-và-nghiệp-vụ).

## Hợp đồng KAG Python

[KagClient](src/main/java/vn/luatgt/integration/KagClient.java) gọi `POST /v1/query` và `POST /v1/query/stream`. Request gồm `user_id`, `message`, `context_id` rỗng và identity `schema_contract`; backend thêm release/snapshot/as_of headers.

`KAG_BASE_URL` mặc định cho Java host là `http://127.0.0.1:38000`; Docker dùng `http://kag-ingress:8080`. Query/inspection dùng `KAG_TOKEN_FILE`/`KAG_INSPECT_TOKEN_FILE` riêng; browser chỉ giữ JWT WebApp. Đặt `KAG_RELEASE_ID` và `KAG_WEBAPP_SNAPSHOT_ID` khớp release đang phục vụ; cấu hình network theo [Docker KAG](../../docker/README.md#kag-primary-compose).

Success v1 cần answer và 1–20 citations `LegalUnit.text`, quote nguyên trường, document/unit đã xuất bản và còn hiệu lực. Native document/sign citations chưa biểu diễn được qua projection này. Sai/thiếu căn cứ bị từ chối cả câu trả lời; không bỏ support để ép success.

Native abstention hợp lệ được kiểm qua response 503 `KAG_ABSTAINED`, `native_state=abstained` và identity release, rồi lưu `KAG_ABSTAINED`. Lỗi upstream/response khác lưu `UNAVAILABLE`. SSE cần terminal `done`; frontend hiện dùng REST. Chi tiết: [hợp đồng HTTP](../../docs/architecture.md#hợp-đồng-http-và-chính-sách-tương-thích).

Admin `/admin/kag/status`, `/pipeline`, `/benchmark/datasets`, `/sample` và `/retrieve` đọc readiness, receipt, SAMPLE và eligibility; không chạy builder/benchmark. SAMPLE chưa phải production; Production WRITE bị chặn.
