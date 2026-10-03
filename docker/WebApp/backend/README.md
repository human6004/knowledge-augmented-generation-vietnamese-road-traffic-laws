# Backend LuậtGT

Một ứng dụng Spring Boot 3.5.16 / Java 21, kiến trúc **monolith, MVC**. React là lớp hiển thị; backend phục vụ REST và SSE. KAG Python là tích hợp bên ngoài, được xây dựng riêng sau.

```text
src/main/java/vn/luatgt/
├── Application.java           Điểm khởi động duy nhất
├── controller/                Nhận HTTP, kiểm tra DTO, gọi service
├── dto/                       Các request DTO và ràng buộc đầu vào
├── service/                   Xác thực, nhập dữ liệu, học, thi, chat, lưu tệp
├── model/                     JPA entity, không trả trực tiếp qua HTTP
├── repository/                Spring Data JPA, truy vấn và khóa bản ghi
├── integration/               HTTP KAG và MinIO
├── config/                    Security/JWT và giới hạn request
└── exception/                 Chuyển lỗi nghiệp vụ thành HTTP
src/main/resources/
├── application.yml
└── db/migration/             Flyway: core và moderation/law versions
```

Controller không truy cập repository. Service giữ giao dịch và quy tắc nghiệp vụ. Repository không xử lý HTTP. Các package cùng chạy trong một tiến trình và dùng một PostgreSQL; không có service nội bộ riêng hoặc event bus.

## Chạy

Từ thư mục gốc, với Docker Desktop đã cài và chạy:

```powershell
./scripts/init-env.ps1
docker compose up -d --build
```

API: `http://127.0.0.1:8080/api`; health: `/actuator/health`. Mật khẩu ADMIN lấy từ `.env`, không phải tài khoản demo trên FE. Tự đăng ký chỉ tạo USER. Bootstrap chỉ tạo ADMIN nếu email chưa tồn tại; không tự nâng USER thành ADMIN, không đặt lại mật khẩu ADMIN cũ.

Để chạy Java trên máy, khởi động `docker compose up -d postgres redis minio`, đặt các biến `DB_PASSWORD`, `REDIS_URL`, `JWT_SECRET`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `MINIO_USER`, `MINIO_PASSWORD` trong môi trường rồi chạy `mvn spring-boot:run` tại `backend`. `REDIS_URL` phải chứa mật khẩu từ `.env`; Java không tự đọc `.env`.

```powershell
cd backend
mvn verify
```

Test dùng H2 chế độ PostgreSQL và mock Redis/MinIO/KAG. Kiểm thử hạ tầng Docker dùng `scripts/verify-stack.ps1` trên stack đang chạy. MinIO được build từ [bản nguồn chính thức có bản vá 2025-10-15](https://github.com/minio/minio/releases/tag/RELEASE.2025-10-15T17-29-55Z); upstream đã archive. Cấu hình này phục vụ phát triển local, cần chọn hệ thống S3 được duy trì trước khi triển khai production.

## API

Mọi API trừ đăng ký, đăng nhập và health yêu cầu `Authorization: Bearer <accessToken>`. JWT hết hạn sau 1 giờ. Logout thu hồi toàn bộ token của tài khoản; khóa USER cũng thu hồi token. Không lưu token vào cookie nên xác thực API dùng bearer, không dùng session cookie.

| Nhóm | Endpoint |
|---|---|
| Tài khoản | `POST /auth/register`, `POST /auth/login`, `GET /auth/me`, `POST /auth/logout` |
| Nội dung USER | `GET /questions?chapter=1`, `GET /signs`, `GET /documents` — chỉ bản đã xuất bản/còn hiệu lực |
| Ôn tập | `POST /study/{questionId}/answer` với `{ "selected": 0 }`; `GET /progress` |
| Thi thử | `POST /exams`, `GET /exams/{id}`, `PUT /exams/{id}/answers/{questionId}`, `POST /exams/{id}/submit`, `GET /exams` |
| Chat | `POST /chat` hoặc `POST /chat/stream`; `GET /chat` lấy lịch sử của chính tài khoản |
| ADMIN | `GET /admin/questions`, `/admin/signs`, `/admin/documents`; `GET /admin/users`; `PATCH /admin/users/{id}` với `{ "enabled": false }` |
| Nhập hàng loạt | `POST /admin/imports/{questions\|signs\|documents}/preview` rồi `/confirm` với `{ "rows": [...], "updateExisting": false }` |
| Sửa/kiểm duyệt | `PUT /admin/content/{id}` với `{ "version": 0, "data": {...} }`; `POST /admin/content/{id}/publication` với `{ "version": 1, "published": true }` |
| Tệp | `POST /admin/content/{id}/media` multipart `file`; `POST /admin/signs/images-zip` multipart `file`; `GET /content/{id}/media` |

Tiền tố bảng là `/api`. Đáp án đánh chỉ số **0**. Preview chỉ kiểm tra; confirm kiểm tra lại và ghi toàn bộ hoặc rollback. Mặc định bỏ qua mã đã có; cập nhật luôn quay về bản nháp. Các thao tác sửa/xuất bản dùng version chống ghi đè dữ liệu đã thay đổi.

Hạng B hiện ghim bộ quy tắc **B-2025-06**: 30 câu, 20 phút, đạt 27 và không sai/bỏ trống câu điểm liệt; quota 8/1/1/1/9/9 câu thường chương 1–6 cộng 1 câu điểm liệt. [Nguồn cấu trúc đề năm 2025](https://xaydungchinhsach.chinhphu.vn/cau-truc-bo-de-dung-de-sat-hach-cap-giay-phep-lai-xe-cac-hang-tu-1-6-119250513103938925.htm). Đây là cấu hình của bộ mẫu, chưa tuyên bố cập nhật mọi thay đổi quy định sau năm 2025. Server quyết định hạn chót, chấm bằng bản chụp câu hỏi lúc bắt đầu; không gửi đáp án/cờ điểm liệt khi bài đang làm. Mỗi người chỉ đọc/ghi bài thi của chính mình. Nộp lại trả cùng kết quả.

## Chuẩn hóa dữ liệu

Câu hỏi: `externalId`, `text`, `chapter` (1–6), `options` (2–4 chuỗi), `correctAnswer` (0-based hoặc null khi nháp), `critical` (boolean hoặc null), `source`, `imageRequired`, `reviewed`. Xuất bản yêu cầu đáp án và điểm liệt được xác nhận, `reviewed=true`, nguồn và ảnh nếu cần.

Biển báo: nhận trực tiếp `sign_id`, `ma_bien`, `nhom`, `ten`, `mo_ta`, giữ `doc_id`, `unit_id`, `qcvn`, `so_hieu`, `bien_phu_variant`, `ngay_hieu_luc`, `ngay_het_hieu_luc`; bổ sung alias chuẩn `externalId`, `code`, `group`, `name`, `meaning`. Nội dung `mo_ta` bị cắt trong mẫu phải được bổ sung trước khi duyệt. Xuất bản cần ảnh, metadata pháp lý, ngày hiệu lực và xác nhận kiểm duyệt.

Văn bản: `externalId`/`doc_id`, `title`, `so_hieu`, `source`, ngày hiệu lực/hết hiệu lực; upload PDF riêng. Tệp/ảnh do MinIO lưu, DB chỉ giữ khóa và MIME. Client nhập JSON không được tự đặt khóa tài nguyên. Ảnh PNG/JPEG tối đa 5 MB, 4096×4096; PDF tối đa 20 MB; ZIP 20 MB nén, 50 MB giải nén, 1000 mục. Ảnh ZIP biển báo ghép theo `ma_bien`, ví dụ `DP.127.png`; ZIP câu hỏi theo `externalId`, ví dụ `Q301.png`. Nếu cùng mã có nhiều biến thể/phiên bản, trả `unmatched` để gắn ảnh theo ID thay vì đoán. SVG/WebP cần xử lý bổ sung; không nhận vào backend hiện tại.

`docs/imports/questions-draft.json` chứa bản trích PDF, luôn cần duyệt. Script `scripts/prepare_question_bank.py` kiểm tra đủ 600 số câu và 2–4 đáp án, lấy đáp án từ gạch chân và giữ trang nguồn. Bộ mẫu có 60 câu điểm liệt với nguồn Chính phủ và 318 ảnh trong ZIP khoảng 16.9 MB; provenance của các câu 204/301/302/352 nằm tại `docs/imports/question-audit.json`. Mọi câu có `reviewed=false` cho đến khi được kiểm duyệt; pipeline không xuất bản tự động. `scripts/extract_questions.py` dùng cùng pipeline. FE dùng API thật, không lấy dữ liệu demo thay thế khi lỗi.

## Hợp đồng KAG Python

`POST /v1/query` nhận `{ "user_id": "uuid", "message": "...", "context_id": "..." }`, trả `{ "answer": "...", "citations": [{ "doc_id": "...", "unit_id": "...", "quote": "..." }] }`. Mỗi trích dẫn phải thuộc văn bản đã xuất bản, còn hiệu lực trên BE. Không có căn cứ thì BE từ chối câu trả lời.

`POST /v1/query/stream` cùng request, trả SSE `event: delta` với `data: {"text":"..."}`, kết thúc bằng `event: done` với response đầy đủ như REST. BE proxy delta, kiểm tra và lưu kết quả cuối; nếu stream lỗi hoặc không có done, phát `error`, không đánh dấu câu trả lời hoàn tất. Frontend phải coi delta là nội dung tạm và chỉ xác nhận khi có done. Timeout đọc 30 giây, response 256 KB, circuit breaker và rate limit Redis. KAG chưa chạy thì REST trả 503; SSE trả event error. Không có câu trả lời giả.

Pipeline dựng graph/vector, benchmark và cấu hình KAG chờ core Python; các trang tương ứng hiển thị chưa triển khai. Tra cứu mức phạt có cấu trúc chạy độc lập với KAG và chỉ dùng dữ liệu đã kiểm duyệt gắn văn bản còn hiệu lực. Trang hạ tầng kiểm tra DB/Redis/MinIO, không điều khiển Docker.

## Nghiệp vụ bổ sung và chạy kiểm tra thật

| Nhóm | Endpoint (tiền tố `/api`) |
|---|---|
| Xuất bản câu hỏi hàng loạt | `POST /admin/questions/publication-batch`, `{rows:[{id,version}],reviewed:true,published:true}`, tối đa 600, giao dịch nguyên khối |
| ZIP câu hỏi | `POST /admin/questions/images-zip`, multipart `file` |
| Ảnh snapshot bài thi | `GET /exams/{id}/questions/{questionId}/media`, chỉ chủ bài |
| Lịch sử nội dung | `GET /admin/content/{id}/history` |
| Quan hệ văn bản | `GET/POST /admin/law-relations`, `PUT /admin/law-relations/{id}`, predecessor/successor UUID, type REPLACES/AMENDS, effectiveDate, note, version |
| Mức phạt | `GET /penalties`; `GET/POST /admin/penalties`, `PUT /admin/penalties/{id}`, documentId, data, published, version |
| Phản hồi/kiểm duyệt chat | `POST /chat/{id}/feedback`, feedback HELPFUL/WRONG/NO_BASIS/OUTDATED và note; `GET /admin/chatlogs?pending=true`; `POST /admin/chatlogs/{id}/resolve`, note |
| Báo cáo/hạ tầng | `GET /admin/reports`, `GET /admin/infrastructure` |

Lịch sử lưu JSON trước mỗi lần sửa/nhập ghi đè/đổi xuất bản/gắn ảnh. Quan hệ văn bản chặn tự tham chiếu và chu trình; REPLACES đã có hiệu lực với văn bản kế nhiệm xuất bản/còn hiệu lực làm văn bản cũ không còn được tra cứu hoặc dùng làm căn cứ. AMENDS giữ văn bản gốc, cần quản trị cập nhật nội dung/mức phạt tương ứng. Sửa quan hệ và mức phạt dùng version chống ghi đè.

Mức phạt `data`: behavior, vehicle, unit_id, minFine/maxFine (đồng), points (0–12), additional, reviewed. Các số là số nguyên không âm; maxFine >= minFine. Xuất bản cần reviewed=true và văn bản cha đã xuất bản/còn hiệu lực; không suy đoán mức phạt từ chatbot.

Từ thư mục gốc chạy `scripts/import-question-bank.ps1` để nhập nháp/ghép ảnh, kiểm duyệt trên UI rồi `scripts/verify-stack.ps1 -WithExam`. Compose cung cấp FE ở cổng 8081 (Nginx proxy `/api`); Vite local vẫn dùng proxy cổng 8080. Lệnh/script không được chạy Docker tự động bởi agent.
