# Kiến trúc hệ thống

LuậtGT gồm ứng dụng web và hệ thống KAG cho dữ liệu pháp luật. WebApp quản lý nghiệp vụ, nội dung được kiểm duyệt và lịch sử người dùng. KAG xây dựng đồ thị, truy hồi nguồn và tạo câu trả lời dựa trên căn cứ đã kiểm tra.

## Thành phần và nơi lưu dữ liệu

| Thành phần | Vai trò |
| --- | --- |
| React + TypeScript | Giao diện USER/ADMIN; gọi API Spring Boot bằng JWT của người dùng. |
| Spring Boot | Một ứng dụng monolith theo MVC: xác thực, nội dung, ôn thi, mức phạt, phản hồi và tích hợp KAG. |
| Python KAG | Builder, Retriever, Solver, Evaluation và HTTP API. Tái sử dụng SDK và bộ điều phối OpenSPG KAG. |
| OpenSPG Server | Quản lý project/schema và tiếp nhận thao tác ghi graph từ SDK. |
| Neo4j | Lưu node, quan hệ pháp lý, vector nội dung và index tìm kiếm vector. |
| WebApp MySQL | Lưu tài khoản, nội dung/đơn vị pháp lý được duyệt, bài thi, lịch sử chat và phản hồi. |
| OpenSPG MySQL | Lưu metadata của OpenSPG; tách biệt với MySQL nghiệp vụ. |
| Redis | Hỗ trợ giới hạn truy cập của WebApp. |
| MinIO | Lưu tệp/ảnh; hai stack có kho riêng. |
| HAProxy | Cổng vào cho Python HTTP API, nơi Spring Boot gửi yêu cầu KAG. |

Hai file Compose ở root khai báo 11 services: 5 cho WebApp, 6 cho KAG. Services được khai báo không đồng nghĩa đang chạy hoặc sẵn sàng. Chi tiết cổng, mạng và mounts nằm trong [Docker](../docker/README.md).

## Xây dựng đồ thị và embedding

```text
Nguồn pháp luật + schema + quan hệ
  → Builder kiểm tra dữ liệu và lập kế hoạch node/cạnh
  → Vectorizer tạo hoặc dùng lại embedding
  → Writer gửi graph qua OpenSPG Server
  → Neo4j lưu graph và vector
```

Builder dùng nguồn trong `data/`, schema/contract trong `kag/schema/` và manifest quan hệ. Nó kiểm tra định danh, thuộc tính bắt buộc, kiểu dữ liệu và provenance. Runner chia công việc thành batch, lưu tiến độ ngoài repo, ghi node trước cạnh và đọc lại graph để xác minh.

Embedding nội dung được tạo qua vectorizer upstream và adapter của dự án. Cấu hình lựa chọn provider hoặc replay từ checkpoint; vector thiếu không tự động cho phép gọi provider. Vector được lưu trên node Neo4j:

| Nội dung | Thuộc tính vector |
| --- | --- |
| `LegalDocument.title` | `_title_vector` |
| `LegalUnit.text` | `_text_vector` |
| `TrafficSign.ten` | `_ten_vector` |
| `TrafficSign.moTa` | `_mo_ta_vector` |

Retriever yêu cầu vector 3072 chiều, hữu hạn, khác zero; mỗi target có một index `ONLINE` dùng cosine. Khi nhận câu hỏi, dịch vụ tạo query embedding để tìm trong các index này. Query embedding phục vụ truy hồi, không được ghi thành node pháp luật.

Ghi graph chỉ được runtime cho phép trong scope `FRESH_SAMPLE` với các điều kiện kiểm soát riêng. Ghi production vẫn bị chặn. [Runner](runner.md) và [phạm vi writer](production-writer-scope.md) mô tả cấu hình, replay và điều kiện ghi.

## Luồng câu hỏi

```text
Người dùng
  → React
  → Spring Boot: xác thực, giới hạn truy cập, tạo bản ghi chat
  → KagClient → HAProxy → Python HTTP API
  → Planner → Retriever → Neo4j
  → Deduce kiểm căn cứ → SafeLegalGenerator
  → Spring Boot kiểm publication và trích dẫn, lưu kết quả
  → React hiển thị câu trả lời hoặc trạng thái chưa thể trả lời
```

1. Backend gửi câu hỏi, định danh người dùng và schema identity. Query token là thông tin xác thực giữa dịch vụ; browser chỉ giữ JWT WebApp.
2. Python API kiểm release, nguồn, backend, publication, ngày truy vấn và ngân sách xử lý. Dịch vụ cần bộ tệp xác minh phù hợp trước khi nhận truy vấn.
3. Planner và pipeline lặp của OpenSPG KAG điều phối truy hồi và suy luận. Executor pháp lý giữ câu hỏi gốc, nguồn và ngữ cảnh giữa các lượt.
4. Retriever tìm vector trên bốn trường nội dung, rồi đọc lại node theo ID để lấy nguyên văn. Mở rộng quan hệ một hop có giới hạn, mặc định tắt.
5. Deduce chọn căn cứ và kiểm điều kiện áp dụng, hiệu lực, xung đột. SafeLegalGenerator kiểm nguồn, span và liên kết với yêu cầu hiện tại; kết quả ghép các trích đoạn đã xác minh, không gọi thêm model để viết câu trả lời tự do.
6. Spring Boot chỉ lưu câu trả lời khi văn bản và đơn vị nguồn đã xuất bản, đáp ứng điều kiện hiệu lực của WebApp và quote khớp nguồn. Lịch sử thuộc về từng người dùng.

Chế độ `Trích nội dung văn bản: ...` phục vụ tra nội dung của một văn bản xác định. Kết quả ghi rõ không xác nhận hiệu lực hiện hành. Với câu hỏi về áp dụng pháp luật, thiếu căn cứ đáng tin cậy dẫn tới từ chối trả lời.

## Truy cập graph

Đường đọc và ghi có trách nhiệm khác nhau:

- SDK/writer dùng OpenSPG Server để quản lý project/schema và ghi graph.
- `Neo4jRetrievalClient` và verifier đọc trực tiếp Neo4j bằng các câu truy vấn được cho phép.
- Trong cấu hình SAMPLE Community, Python API dùng `BrokerRetrievalClient` gửi operation DTO tới broker trong OpenSPG Server. Python API không giữ credential DB hoặc đọc DB trực tiếp ở đường này.

Danh tính project, namespace và physical database phải khớp dữ liệu được phục vụ. Tên host hay một receipt cũ không đủ xác nhận quyền truy cập. Xem [backend identity](backend-identity.md).

## Hợp đồng HTTP và chính sách tương thích

Hợp đồng được triển khai trong [Python API](../kag/http_api/app.py), [DTO/projection](../kag/http_api/contract.py) và [KagClient](../WebApp/backend/src/main/java/vn/luatgt/integration/KagClient.java).

- Query nhận `{user_id,message,context_id,schema_contract}`; `context_id` phải rỗng. Backend gửi token và headers release/snapshot/`as_of`. Lịch sử chat không tự trở thành ngữ cảnh hội thoại.
- Native Solver trả `AnswerResult`, hỗ trợ căn cứ từ document/unit/sign và trạng thái abstention.
- Response thành công của v1 chỉ biểu diễn trích dẫn `LegalUnit.text` nguyên trường, đủ publication; không hỗ trợ citation document/sign. Không cắt nguồn hoặc đổi ID để ép kết quả vừa hợp đồng.
- `answer` tối đa 20.000 UTF-16 units; 1–20 citations có `doc_id,unit_id,sign_id,evidence_id,field,start,end,quote`. `sign_id=null`, `field=text`, `start=0`; `end` tính theo Unicode code points.
- Native abstention được Python trả bằng HTTP 503 `KAG_ABSTAINED`, `native_state=abstained`. KagClient kiểm cấu trúc, headers và request identity rồi chuyển sang trạng thái chat `KAG_ABSTAINED`. Các lỗi khác dẫn tới `UNAVAILABLE`.
- Native answer không biểu diễn được bằng v1 trả `V1_RESULT_UNREPRESENTABLE`. Đây là giới hạn tích hợp, không phải bằng chứng thiếu dữ liệu pháp luật.
- Python SSE phát `done` sau khi kết quả được kiểm tra. Backend còn nhận `delta/done` theo hợp đồng tương thích; giao diện chat hiện dùng REST.
- `/v1/health` kiểm liveness, không thay thế readiness cho query/retrieve/vector.
- `/v1/operations/sample`, `/v1/pipeline/status`, `/v1/benchmark/datasets` phục vụ ADMIN kiểm tra. Các endpoint này không chạy builder hoặc benchmark.

`KAG_BASE_URL` trong Docker trỏ tới `http://kag-ingress:8080`; truy cập ingress từ host mặc định dùng cổng 38000. Cổng OpenSPG không phải endpoint chat. Cấu hình cụ thể và secrets xem [cài đặt](INSTALL.md) và [Docker](../docker/README.md).

## Evaluation Framework

Implementation tại [`kag/evaluation/`](../kag/evaluation/__init__.py) nhận runtime do caller cung cấp:

- G1 gọi Retriever hiện tại để đo truy hồi và xếp hạng.
- G2 gọi public `answer()/aanswer()` để đánh giá câu trả lời, trích dẫn và abstention.
- Generation lấy gold từ source span cụ thể; model không tự tạo gold.
- Dataset, gold và QID dùng cho đánh giá, không đưa vào query hoặc điều khiển Solver.
- `PROVISIONAL` giữ các nhãn chưa hoàn chỉnh; `FROZEN` khóa phiên bản và nội dung. Freeze không tự biến dataset thành benchmark chính thức.
- Metric thiếu điều kiện đánh giá giữ `null` và lý do. Report hiện giữ `PAPER_ELIGIBLE=NO`.

Bộ câu hỏi chính thức chưa hoàn thành. [Benchmark](../benchmark/README.md) hướng dẫn lifecycle, eligibility, CLI và cách gọi G1/G2.

## Bản đồ mã nguồn

- `kag/builder/`: kiểm dữ liệu, graph plan, codec, vectorizer và writer adapters.
- `kag/runner.py`, `run_state.py`, `verify.py`: điều phối, state/ledger/locks và xác minh graph.
- `kag/retriever/`: query embedding, vector search, đọc nguồn và mở rộng quan hệ.
- `kag/legal_solver.py`, `legal_prompts.py`: public answer API, executors và kiểm căn cứ.
- `kag/http_api/`: transport, auth, serving runtime, broker, ngân sách provider và inspection.
- `kag/evaluation/`: dataset, generation, review/freeze, metrics và reports.
- `WebApp/`: ứng dụng nghiệp vụ và nội dung xuất bản độc lập với graph.

Local `kag` dùng chung namespace với upstream `vendor/KAG`. Bootstrap ghép module paths và registry; các adapter pháp lý nằm ở root để tránh tranh namespace `kag.solver`. Không đổi thứ tự import, di chuyển package hoặc bỏ `__init__.py` khi tích hợp. Phiên bản vendor, dependency và cách initialize nằm trong [runtime Python](runtime.md).

Schema và contract Python là nguồn chuẩn; Java đóng gói cùng các file này, không tạo schema riêng. Nội dung WebApp được kiểm duyệt riêng, không tự đồng bộ thành graph. [Mô hình miền](domain_model.md) và [schema](schema.md) mô tả định danh và quan hệ.

## Entrypoints và lệnh ổn định

Từ root repository sau khi chuẩn bị runtime:

```sh
python -B -m kag --help
python -B -m kag.evaluation --help
```

Runtime CLI có `run`, `resume`, `verify` với `--config` và `--run-id`; xem [runner](runner.md). `verify` không ghi graph nhưng cập nhật artifacts/log của run ngoài repo.

Library API chính là `Retriever.retrieve`, `build_pipeline(retriever, llm)`, `answer(question, pipeline=..., as_of=...)` và `aanswer(...)`. HTTP server chạy bằng `python -B -m kag.http_api.server` với cấu hình phục vụ phù hợp.

Evaluation CLI có `validate`, `freeze`, `import-legacy`, `generate`, `validate-generated`; G1/G2 là library API. Khởi động ứng dụng không tự build graph hoặc chạy benchmark.
