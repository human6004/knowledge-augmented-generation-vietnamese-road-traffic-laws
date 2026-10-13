Hai cấu hình triển khai chính: `docker-compose.yml` cho WebApp và `docker-compose.kag.yml` cho KAG/OpenSPG/API/HAProxy, tổng 11 services (5 + 6). Chạy lệnh từ root repository. Số services khai báo không chứng minh tất cả đang chạy/healthy.

Dùng PowerShell 7 (`pwsh`) cho scripts UTF-8; Windows PowerShell 5.1 có thể đọc sai tiếng Việt và báo ParserError trước khi kiểm Compose.

Clone repo chưa đủ để chạy SAMPLE. Cần vendor đúng pin, cached runtime/API/MinIO images đúng identity, offline FastAPI wheel và vendor Git objects khi build, external env/tokens, graph SAMPLE/release/proof, publication còn hiệu lực và provider/proxy đúng route. Chat proxy tại host cổng 8317 không thuộc 11 services Compose. Không tự restore/build graph hoặc mở provider khi kiểm cấu hình.

SAMPLE Community query dùng `STEP8_QUERY_PROFILE=community-query-1.0` cùng proof hash do operator pin, publication/snapshot WebApp thực tế và ledger bền vững dùng chung. API vẫn chỉ nối readbus nội bộ, không có credential database. HAProxy gateway nghe `:8898` trong container, không publish host port; ACL tra Docker DNS `kag-api` và kiểm token riêng. Bootstrap tắt gateway bằng ACL khi query profile rỗng. Hai file ledger/lock là các bind writable duy nhất; chỉ `egress.token` vào ingress.

Proxy chat ngoài Compose phải chạy trên máy người nhận: `STEP8_CHAT_PROXY_HOST` mặc định `host.docker.internal`, `STEP8_CHAT_PROXY_PORT` mặc định `8317`. Có thể chọn DNS host/port riêng; không điền IP container/Wi-Fi hoặc URL vào biến host. Docker Desktop cung cấp host gateway; Linux cần proxy có DNS và listener cho Docker truy cập, firewall giới hạn Docker, không tự mở LAN/Internet. `/v1/models` và `/v1/chat/completions` đi qua proxy; `/v1/embeddings` giữ provider đã attested `api.vilao.ai:443`. Credentials, model route và proof phải do operator cung cấp/kiểm chứng; đổi endpoint không cấp serving authority.

Profile thông thường giới hạn embedding 3, chat 7; caller cũ vẫn 3/3. Ledger đếm trước send, tắt retry/redirect. Query cần ít nhất 4 chat attempts còn lại; cache embedding chỉ tái sử dụng khi câu hỏi/hash/model/vector khớp. Profile phát triển SAMPLE được cấp riêng dùng proof `h1-community-query-2.0`, `development_policy.scope=SAMPLE_DEVELOPMENT`, hash yêu cầu phê duyệt và baseline counts; limits embedding/chat là `null`. Operator phải pin lại toàn bộ proof. Ledger/lock/binding và mọi attempts lịch sử giữ nguyên; không reset để đổi profile. Deadline 180 giây, tối đa 5 iteration và không retry vẫn áp dụng. Bỏ policy cần trở về proof có cap hợp lệ; ledger vượt cap sẽ fail closed.

Readiness kiểm tra graph/broker/proof/model metadata thật, không gọi inference. Response thiếu/sai model bị chặn và vẫn tính attempt. Ngoại lệ phát triển chỉ nhận response version đã được trace upstream chứng minh và pin trong `model_route`; đây là chứng cứ request route/response version, không chứng minh exact backend identity hay high thinking. `KAG_QUERY_TIMEOUT_SECONDS=180` đồng bộ timeout query/SSE WebApp, mặc định 30. `KAG_INSPECTION_TIMEOUT_SECONDS=25` cho inspection SAMPLE kiểm graph đầy đủ, mặc định 2, phạm vi 2–25 giây. Câu hỏi bắt đầu đúng `Trích nội dung văn bản: ` và chứa duy nhất một số hiệu có thể trả nguyên văn nguồn kèm nhãn không xác nhận hiệu lực hiện hành; citation vẫn kiểm document, toàn span, parent/context và publication. Câu hỏi pháp luật hiện hành vẫn abstain khi hiệu lực từng phần thiếu phạm vi xác minh. Readiness không chứng minh đáp án pháp lý. Production authority vẫn DENY/BLOCKED.

## WebApp

WebApp giữ project `webapp`, MySQL nghiệp vụ, Redis, MinIO, Spring Boot và React hiện có. Không dùng database/volume OpenSPG hoặc legacy.

`docker/init-env.ps1` chỉ tạo/bổ sung cấu hình WebApp, không ghi đè credentials hiện có. Cung cấp `KAG_TOKEN_FILE` và `KAG_INSPECT_TOKEN_FILE` trỏ tới hai file token khác nhau bên ngoài repository. Backend mount chúng tại `/run/secrets/kag_query_token` và `/run/secrets/kag_inspect_token`; browser chỉ dùng JWT WebApp.

Docker backend dùng `KAG_BASE_URL=http://kag-ingress:8080`, nối network ingress có sẵn. Điền cùng `STEP8_KAG_PROJECT` trong env WebApp và KAG; khởi động KAG trước WebApp để external network tồn tại. Java chạy trực tiếp trên host dùng `http://127.0.0.1:38000`. Host ports vẫn chỉ bind localhost. Không cần IP máy tác giả hoặc IP container cố định.

```powershell
./docker/check-config.ps1 -Stack WebApp -WebAppEnvFile <external-webapp-env>
```

Backend build đóng gói schema gốc, không đưa Python/vendor vào Java image. Flyway chỉ chạy trên database WebApp được cấp quyền. Tests H2/mock không thay thế MySQL thật.

## KAG primary Compose

`docker-compose.kag.yml` sử dụng sáu service Step8: `openspg-mysql`, `openspg-neo4j`, `openspg-minio`, `openspg-server`, `kag-api`, `kag-ingress`. External `STEP8_KAG_PROJECT` bắt buộc có tiền tố `kag-s8-`; volumes/networks thuộc project đó. Không tái sử dụng project `kag`, `docker` hoặc legacy storage.

Fresh sample dùng `STEP8_DATABASE='vietroadtraffic'` và `STEP8_NEO4J_STORAGE_REVISION='-fresh-20261011'` để khởi tạo default database trên volume mới; volume trước giữ rollback. Runner FRESH_SAMPLE phải đối chiếu volume revised và physical identity trước WRITE.

`POST /v1/retrieve/vector` nhận `evidence_id` từ release SAMPLE sealed, không gọi embedding/chat. Runtime kiểm toàn bộ graph, provenance, database và source trước/sau retrieval. Enterprise giữ attestation reader RBAC riêng. Community dùng proof `h1-community-sample-1.0`: broker chỉ đọc trong OpenSPG server giữ DB credential; API chỉ giữ broker token, kiểm physical identity/read-only, hash code, DNS/IP binding và actual TCP denial tới DB/Java. Proof thiếu hoặc drift → 503; không tuyên bố tài khoản Community least-privilege. NL/query và production WRITE giữ gate riêng.

Community cấu hình external `STEP8_BROKER_CREDENTIALS_DIR`, `STEP8_BROKER_DATABASE_ID`, `STEP8_BROKER_SERVER_ID`, `STEP8_BROKER_URL='http://openspg-server:8899'`. Backend-only directory chứa `neo4j.password` và `broker.token`; API-only directory chứa cùng broker token và `sample-proof.sha256`, không có DB credential. Static `STEP8_SAMPLE_PROOF_SHA256` phải rỗng trong mode này. Mint proof từ actual container/network IDs sau deployment, ghi hash vào file rồi restart cùng API container; không recreate làm lệch identity. Khi chuyển máy hoặc recreate container, đo lại isolation/DNS/backend identity và pin lại supplemental SAMPLE/query proofs cùng hash gateway config; không sao chép IP cũ, không sửa descriptor/graph/publication để né gate. IDs trong receipt là provenance operator; runtime independently kiểm DNS/IP, TCP denial, code và backend trạng thái. Initializer để broker chưa cấu hình, không cấp serving authority.

Direct live runner dùng `ProviderBudget` với ledger cố định xuyên Retriever/Planner/Deduce. Reserve trước transport, mọi failure/timeout tính attempt; SDK/planner/JSON retries tắt. Không suy ra HTTP query READY từ direct retrieval hoặc provider response.

Catalog SAMPLE có thể giữ `parent_id`/`unit_id` nguồn nằm ngoài sample. Parent hiện diện phải cùng document; mọi endpoint trong `graph_context` phải có trong catalog. Release ngoài SAMPLE vẫn yêu cầu đầy đủ parent closure.

Dùng external env do `docker/init-step8-env.ps1` tạo và wheel cache/vendor objects đã xác minh. `docker/init-env.ps1 -Kag` và `.env.kag` giữ compatibility lịch sử; không dùng cho primary Compose mới.

```powershell
./docker/check-config.ps1 -Stack Kag -KagEnvFile <external-kag-env>
./docker/test-compose.ps1 -KagEnvFile <external-kag-env>
```

`check-config.ps1` kiểm cấu hình không startup/pull/build. `test-compose.ps1` còn tạo fixture/env thử trong thư mục tạm và kiểm cached API image identity; không phải thao tác chỉ đọc filesystem. Mạng `private` internal chỉ chứa DB/MySQL/MinIO/OpenSPG; `readbus` internal chứa OpenSPG/API/HAProxy. Java bind `127.0.0.1:8887`, broker không publish host port. HAProxy nối `readbus` và `ingress`, chỉ publish `127.0.0.1:38000`. API không nối mạng DB. API/HAProxy giữ non-root, read-only rootfs, cap-drop ALL, no-new-privileges và resource limits zero swap.

Production WRITE BLOCKED; operational proof và provider egress DENY. Liveness 200 không thành readiness. Release artifact không chứng minh physical Neo4j identity, live indexes hoặc source readback. Không mở quyền bằng biến môi trường.

`/v1/pipeline/status` và `/v1/benchmark/datasets` là inspect-only GET. Không có endpoint chạy pipeline/benchmark. Progress chưa đo và metrics chưa chạy giữ null. `STEP8_EVALUATION_ENABLED` chỉ đọc dataset tại `<STEP8_RELEASE_DIR>/evaluation` qua mount read-only hiện có; không tạo/đóng băng/sửa dataset. FROZEN integrity không thay thế gold review, graph catalog hoặc quyền chạy benchmark.

Question Generation và G1/G2 Framework đã có trong `kag/evaluation/`; bộ câu hỏi chính thức chưa hoàn thành. SAMPLE 32 nodes / 22 edges / 42 vectors không chứng minh chất lượng toàn corpus hoặc production readiness. Publication/proof có thời hạn; không sửa ngày/hash của sealed bundle để làm readiness PASS.

Chỉ dùng `docker-compose.kag.yml` cho KAG và `docker-compose.yml` cho WebApp, kể cả kiểm thử và recovery. Cached image phải khớp exact local identity và source đã review trước deployment.

## Bảo toàn và migration

Không restart/migrate legacy, restore/build graph hoặc gọi provider từ scripts config. Migration runtime cần phê duyệt riêng; source/static PASS không thành migration PASS. Không dùng prune/xóa volumes. Giữ external credentials, backup và dataset.
