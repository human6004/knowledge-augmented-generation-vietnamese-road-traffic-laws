# KAG luật giao thông đường bộ Việt Nam

Ứng dụng Knowledge-Augmented Generation tra cứu và trả lời câu hỏi pháp lý từ
văn bản, đơn vị nội dung và biển báo. Core Python đã có Builder, Retriever,
Solver và Evaluation Framework. LuậtGT cung cấp giao diện React và backend
Spring Boot; HTTP adapter nối backend với core Python chưa được triển khai.

## Bản đồ tính năng và mã nguồn

- **Deterministic Builder** kiểm tra nguồn/schema, lập kế hoạch node/cạnh,
  giữ native Integer và gộp provenance xác định. Adapter tái sử dụng writer và
  vectorizer OpenSPG KAG, bổ sung retry/checkpoint, scope và kiểm chứng readback.
  Mã: [graph plan](kag/builder/graph_plan.py), [writer](kag/builder/writer_adapter.py),
  [vectorizer](kag/builder/resilient_vectorizer.py), [runner](kag/runner.py).
- **OpenSPG + Neo4j** cung cấp project/schema, lưu graph và index vector.
  Retriever và verifier đọc Neo4j trực tiếp; writer/SDK dùng API OpenSPG.
  Mã: [readback verifier](kag/verify.py), [backend identity](kag/backend_identity.py).
- **Legal Retriever** truy hồi bốn trường nội dung, giữ exact ID và nguyên văn
  nguồn; mở rộng quan hệ một hop có giới hạn, mặc định tắt.
  Mã: [Retriever](kag/retriever/retriever.py), [Neo4j reader](kag/retriever/neo4j.py).
- **Legal Solver** dùng `KAGIterativePlanner` và `KAGIterativePipeline` từ upstream
  đã pin, ghép executor/prompt/generator pháp lý. Kết quả chỉ dùng nguồn đã đọc
  lại từ server; thiếu căn cứ, hiệu lực hoặc applicability thì abstain.
  Mã: [public answer API và safe generator](kag/legal_solver.py),
  [legal prompts](kag/legal_prompts.py).
- **Evaluation Framework** có typed dataset, lifecycle, G1 retrieval, G2 answer/
  citations và báo cáo có hash. Gold/QID phục vụ đánh giá, không điều khiển inference.
  Mã: [G1/G2](kag/evaluation/evaluate.py), [dataset](kag/evaluation/dataset.py),
  [reports](kag/evaluation/report.py).
- **WebApp LuậtGT** đã có quản lý nội dung, ôn/thi, chat client và schema identity.
  HTTP query adapter còn thiếu; một số trang quản trị KAG vẫn là chức năng chờ tích hợp.
  Mã: [routes](WebApp/frontend/src/App.tsx), [user pages](WebApp/frontend/src/pages/server/UserPages.tsx),
  [chat service](WebApp/backend/src/main/java/vn/luatgt/service/ChatService.java),
  [KagClient](WebApp/backend/src/main/java/vn/luatgt/integration/KagClient.java).
- **Admin** quản lý nội dung/đơn vị pháp lý, nhập dữ liệu, tài khoản, phản hồi,
  mức phạt, schema identity và kiểm tra MySQL/Redis/MinIO. Pipeline/graph/benchmark
  đang là trang chờ tích hợp. Mã: [admin pages](WebApp/frontend/src/pages/server/AdminPages.tsx),
  [schema page](WebApp/frontend/src/pages/server/KagSchemaPage.tsx),
  [operations](WebApp/frontend/src/pages/server/OperationsPages.tsx),
  [moderation](WebApp/backend/src/main/java/vn/luatgt/service/ModerationService.java).

```text
Nguồn + schema → deterministic plan → guarded KAG builder → OpenSPG → Neo4j
Câu hỏi → upstream iterative planner/pipeline
              ├→ Legal Retriever → đọc Neo4j trực tiếp → evidence nguồn
              └→ legal deduction + safe generator → AnswerResult / abstention

Dataset đánh giá → G1: Retriever / G2: public answer API → metrics + reports
React → Spring KagClient → HTTP query adapter [chưa triển khai] → core Python
```

Chi tiết package, transport và namespace: [kiến trúc sản phẩm](docs/architecture.md).

## Trạng thái triển khai

Builder/Retriever/Solver/Evaluation và nghiệp vụ WebApp đã có code. HTTP query
adapter và management integration KAG chưa có. [Bootstrap](kag/bootstrap.py)
đã xử lý preload local Solver; [regression import-order](tests/runtime/test_bootstrap.py)
kiểm cả initialize-first, preload-builder và preload-solver.
Mã đã triển khai không đồng nghĩa graph production đã build hoặc benchmark pháp
lý đã đạt. **Production WRITE vẫn BLOCKED**. Import SDK phải qua bootstrap
đúng thứ tự; import/smoke PASS không là legal-domain hoặc production release.

## Bắt đầu

Từ root repository, lấy submodule đúng pin nếu checkout mới chưa có:

```sh
git submodule update --init vendor/KAG
```

Runtime chuẩn là **CPython 3.10.16, Linux amd64**. Làm theo
[setup runtime](docs/runtime.md); các lệnh sau chỉ xem giao diện CLI:

```sh
python -B -m kag --help
python -B -m kag.evaluation --help
```

CLI [runtime](kag/__main__.py) có `run`, `resume`, `verify`, dùng config tường minh và lưu bằng
chứng ngoài repo. CLI [evaluation](kag/evaluation/__main__.py) có `validate`, `freeze`, `import-legacy`;
G1/G2 là library API, không có lệnh benchmark live tự động. Xem
[kiến trúc và entrypoints](docs/architecture.md#entrypoints-và-lệnh-ổn-định),
[vận hành runtime](docs/runner.md) và [hướng dẫn WebApp](WebApp/README.MD).
`verify` không ghi graph nhưng có thể cập nhật receipt/log của run ngoài repo.

## Đánh giá và benchmark

G1 đo Retriever hiện tại; G2 dùng public Solver API và kiểm citations. Dataset
PROVISIONAL/FROZEN, eligibility và nơi lưu evidence được hướng dẫn tại
[benchmark](benchmark/README.md); API nội bộ tại
[Evaluation Framework](docs/architecture.md#evaluation-framework).
Smoke synthetic/sample không thay thế official benchmark. Không chạy full
benchmark hoặc provider từ thao tác setup.

## Kiểm thử

Sau [setup runtime chuẩn](docs/runtime.md), từ root repository:

```sh
python -B -m unittest discover -s tests/runtime -p 'test_*.py' -v
```

[Hướng dẫn test](tests/README.md) giải thích từng suite, chạy process riêng,
fixtures và canonical lock mount. Test WebApp nằm trong hướng dẫn
[backend](WebApp/backend/README.md#chạy) và
[frontend](WebApp/frontend/README.md#phát-triển-và-kiểm-thử).

## Dữ liệu và nguồn chuẩn

Corpus tại `data/` có phạm vi graph 91 văn bản, 55.597 đơn vị nội dung và 887
bản ghi biển báo; eval không thuộc retrieval corpus. Xem [dataset](data/README.md),
[datasheet](data/DATASHEET.md) và [giấy phép](data/LICENSE.md).

Schema `VietRoadTraffic` có `LegalDocument`, `LegalUnit`, `TrafficSign`, mười
predicate; 75 thuộc tính node logical gồm 69 khai báo và sáu `id/name` kế thừa
`Thing`. Penalty nằm trên LegalUnit; provenance nằm trên cạnh. Nguồn chuẩn:
[schema](kag/schema/VietRoadTraffic.schema),
[contract](kag/schema/schema_contract.json),
[mô hình miền](docs/domain_model.md) và [quy tắc schema](docs/schema.md).
Không sửa corpus, schema, gold hoặc input đã khóa để làm smoke PASS.

## Cấu trúc và tích hợp

- `kag/`: core ứng dụng, runtime, legal adapters và evaluation.
- `vendor/KAG/`: upstream OpenSPG KAG, pin
  `fdab15b3929d2ee40dfcdd388f90233096a6afc9`; không đặt code ứng dụng ở đây.
- `WebApp/`: React/Spring và nguồn nghiệp vụ được kiểm duyệt riêng.
- `docker/`: runtime Python và hạ tầng hai stack độc lập; xem [Docker](docker/README.md).
- `tests/`: [kiểm thử theo trách nhiệm](tests/README.md); `benchmark/` và `scripts/`
  là workspace dành riêng, implementation hoạt động nằm trong `kag/`.
  Root `scripts/` chưa có wrapper; script hạ tầng ở [docker](docker/README.md),
  nhập/kiểm tra nghiệp vụ ở [WebApp/scripts](WebApp/README.MD).
  Dùng CLI hiện có, không cần wrapper/runner mới.
  Import/build/verify-stack có side effects; xem hướng dẫn subsystem trước khi chạy.
- `docs/`: tài liệu kiến trúc, vận hành và design lịch sử; chỉ mục ở bên dưới.

`KAG_BASE_URL` dành cho HTTP adapter cổng 8000, không phải OpenSPG cổng 28887.
Native `AnswerResult` và hợp đồng Java khác nhau về abstention, loại citation
và validation nguồn. Xem [gap và chính sách API đề xuất](docs/architecture.md#hợp-đồng-http-và-chính-sách-tương-thích-đề-xuất).
H1/H2 chưa bắt đầu; tài liệu này không triển khai API hoặc mở WRITE.

## Tài liệu chi tiết

- [Kiến trúc sản phẩm](docs/architecture.md): package, upstream, transport, API và compatibility HTTP đề xuất.
- [Runtime Python](docs/runtime.md): interpreter, dependency/vendor pin, setup và bootstrap.
- [Vận hành Builder](docs/runner.md): run/resume/verify, config, ledger, outbox và lock.
- [Backend identity](docs/backend-identity.md): physical database và routing trước dispatch.
- [Writer scope](docs/production-writer-scope.md): preconditions và production WRITE còn khóa.
- [Mô hình miền](docs/domain_model.md): identity, cây đơn vị, quan hệ pháp lý và phạm vi graph.
- [Schema kỹ thuật](docs/schema.md): property/predicate, codec, SAFE_EDGE và yêu cầu Builder.
- [Retrieval và frozen slice](docs/retrieval-demo.md): exact ranking; sample lịch sử không là official benchmark.
- [Benchmark](benchmark/README.md): datasets, library G1/G2 và reports.
- [Dữ liệu](data/README.md), [WebApp](WebApp/README.MD), [backend](WebApp/backend/README.md),
  [frontend](WebApp/frontend/README.md), [Docker](docker/README.md), [tests](tests/README.md).

Design trong [docs/superpowers/specs](docs/superpowers/specs/) giữ quyết định và
checkpoint lịch sử; tên scope, stage, release/gate và input paths trong machine
contracts vẫn ổn định. Báo cáo phase ngoài repo là bằng chứng tại thời điểm chạy,
không tự xác nhận runtime hoặc graph đang hoạt động hôm nay.
