# Docker cho người vận hành LuậtGT

Hai cấu hình chính: [docker-compose.yml](../docker-compose.yml) cho WebApp và
[docker-compose.kag.yml](../docker-compose.kag.yml) cho KAG/OpenSPG/API/HAProxy.
Không dùng Compose profiles; mỗi stack khai báo services chạy trực tiếp.
Chạy lệnh từ root repository.

[Cài đặt](../docs/INSTALL.md) hướng dẫn lần đầu;
[cập nhật](../docs/UPDATE.md) hướng dẫn giữ dữ liệu. Clone chưa đủ để phục vụ chat:
graph, cached images, release/proofs/publication, secrets và provider route cần
chuẩn bị ngoài Git. Production WRITE giữ `BLOCKED`; benchmark chính thức chưa
hoàn thành.

## Công cụ và dependencies

Dùng Docker Linux containers `linux/amd64`, Compose có BuildKit/
`additional_contexts`, Git và PowerShell 7 (`pwsh`). Scripts
`init-step8-env.ps1`, `check-step8-config.ps1` và `test-compose.ps1` gọi RTK
bên trong; máy dùng các scripts đó cần `rtk` trong PATH. App/container không
phụ thuộc RTK.

- WebApp: MySQL `8.4.11`, Redis `7.4-bookworm`; MinIO build từ
  [Dockerfile](minio/Dockerfile). Backend build bằng Maven 3.9.16/Java 21;
  frontend build bằng Node 24/pnpm 10.11.0 và phục vụ qua Nginx.
- KAG: OpenSPG MySQL/Neo4j/server và HAProxy pin digest trong Compose.
  MinIO lấy từ `STEP8_MINIO_IMAGE` đúng cached identity được checker chấp nhận.
  Runtime `vietroadtraffic-kag-runtime:d0.2` dùng CPython 3.10.16 và dependencies
  đã pin; API thêm FastAPI 0.115.12 theo
  [requirements-http-api.txt](../requirements-http-api.txt).
- KAG API build offline với `network: none`, không pull, không dùng package index.
  Cần wheel đúng hash và Git objects của `vendor/KAG` đúng pin
  `fdab15b3929d2ee40dfcdd388f90233096a6afc9`. Runtime/API/MinIO cache phải khớp
  các `STEP8_*_IMAGE_ID`; tag trùng tên chưa đủ chứng minh identity.
- KAG services giữ `pull_policy: never`, `restart: "no"` và resource limits.
  Tổng giới hạn RAM là 5,25 GiB; đây là cấu hình giới hạn, chưa chứng minh capacity.

## WebApp

Project `webapp` gồm `mysql`, `redis`, `minio`, `backend`, `frontend`.
Backend đợi MySQL/Redis healthy và MinIO started; frontend phụ thuộc backend.
Dữ liệu dùng named volumes `webapp_kag-data`, `webapp_redis-data`,
`webapp_minio-data`, tách khỏi OpenSPG/legacy.

Host ports chỉ bind `127.0.0.1`: MySQL 3306, Redis 6379, MinIO 9000/console 9001,
backend 8080, frontend 8081. Health công khai backend: `/actuator/health`.

`docker/init-env.ps1` tạo `.env` WebApp; chế độ `-Update` chỉ bổ sung key còn thiếu,
không đổi credentials đã có. Cấu hình gồm DB/Redis/MinIO/JWT và tài khoản bootstrap
`ADMIN_EMAIL`/`ADMIN_PASSWORD`. ADMIN đã tồn tại không được đổi mật khẩu bằng cách
sửa bootstrap env.

Kết nối KAG:

- `KAG_BASE_URL=http://kag-ingress:8080` trong Docker. Java chạy trực tiếp trên host
  dùng `http://127.0.0.1:38000` theo port ingress đã cấu hình.
- `STEP8_KAG_PROJECT` trong env WebApp/KAG giống nhau. Backend nối network default
  WebApp và external `<project>_ingress`; startup KAG trước để network tồn tại.
- `KAG_TOKEN_FILE`/`KAG_INSPECT_TOKEN_FILE` trỏ tới hai token files khác nhau ngoài
  Git. Backend mount tại `/run/secrets/kag_query_token` và
  `/run/secrets/kag_inspect_token`. Browser chỉ dùng JWT WebApp.
- `KAG_RELEASE_ID` và `KAG_WEBAPP_SNAPSHOT_ID` khớp release/publication được cấp.
  Query timeout mặc định 30 giây, phạm vi 30–180; inspection mặc định 2 giây,
  phạm vi 2–25. SAMPLE query dùng 180 giây; inspection graph có thể cần 25 giây.

```powershell
$WebEnv = '.env'
pwsh -NoProfile -File docker/check-config.ps1 -Stack WebApp -WebAppEnvFile $WebEnv
```

Backend image đóng gói schema chung, không chứa Python/vendor. Flyway chạy trên
database WebApp khi startup; không dùng DB_URL trỏ vào OpenSPG hoặc database cũ.

## KAG primary Compose

Project từ `STEP8_KAG_PROJECT` phải khớp `kag-s8-[a-z0-9][a-z0-9-]*`.
Không tái dùng project/volumes legacy. Sáu services:

- `openspg-mysql`, `openspg-neo4j`, `openspg-minio`: lưu dữ liệu OpenSPG.
- `openspg-server`: đợi MySQL/Neo4j healthy và MinIO started, chạy Java cùng
  read broker khi broker identity đầy đủ.
- `kag-api`: API Python, một worker, chỉ nối readbus.
- `kag-ingress`: HAProxy, đợi API healthy, nối readbus và ingress.

Network `<project>_private` internal chứa ba data services và OpenSPG server.
`<project>_readbus` internal chứa server/API/HAProxy. `<project>_ingress` là bridge
để HAProxy nhận WebApp/host traffic và đưa provider traffic qua gateway.

Chỉ HAProxy publish `127.0.0.1:<STEP8_API_PORT>:8080`, mặc định host 38000.
API 8000, broker 8899 và provider gateway 8898 không publish host.
OpenSPG Java nghe `127.0.0.1:8887` bên trong container.
`STEP8_OPENSPG_PORT` do initializer ghi ra không tạo host port trong Compose chính.

Named volumes tách theo project:

- `<project>_openspg-mysql-data` → MySQL `/var/lib/mysql`.
- `<project>_openspg-neo4j-data<storage-revision>` → Neo4j `/data`;
  `<project>_openspg-neo4j-logs` → `/logs`.
- `<project>_openspg-minio-data` → MinIO `/data`.

Database `vietroadtraffic` cần storage revision riêng đúng dạng `-fresh-...`;
SAMPLE broker cần `STEP8_READ_ONLY_DATABASES='vietroadtraffic'`.
Giữ revision của installation hiện có; đổi revision chọn volume khác, không
tự chuyển dữ liệu hoặc chứng minh graph sẵn sàng.

API/HAProxy chạy non-root, root filesystem read-only, `cap_drop: ALL`,
`no-new-privileges`, CPU/PID/memory limits; swap bị tắt riêng hai services này.
API không có Docker socket, DB network hoặc DB password trong broker mode.

## External env, secrets và mounts

`docker/init-step8-env.ps1` tạo external `kag.env`, tokens và thư mục rỗng;
không overwrite thư mục có sẵn hoặc cấp serving authority. Truyền
`-ApiImageId` bằng identity đã đối chiếu, không tự chấp nhận default cache ID.
Không dùng `docker/init-env.ps1 -Kag` hoặc `.env.kag.example` cho Compose chính.

KAG env phải dùng `KEY='value'`, không trùng key. Thay paths bằng thư mục ngoài
Git của installation; ví dụ `C:/kag-local/secrets/kag.env`.
Các nhóm cần hoàn thiện:

- Images/build: `STEP8_API_IMAGE` theo `<project>-api:source`, các image IDs,
  `STEP8_RUNTIME_IMAGE`, `STEP8_MINIO_IMAGE`, `STEP8_HTTP_WHEELS_DIR`,
  `STEP8_VENDOR_OBJECTS_DIR`.
- Data/identity: DB passwords ngẫu nhiên riêng, `STEP8_DATABASE`,
  `STEP8_NEO4J_STORAGE_REVISION`, `STEP8_READ_ONLY_DATABASES`,
  `STEP8_BROKER_DATABASE_ID`/`STEP8_BROKER_SERVER_ID`.
- Serving: `STEP8_RELEASE_DIR`/`STEP8_RELEASE_ID`, API/broker/gateway credential
  directories, query/inspect token files và proof pins.
- Query: `STEP8_QUERY_PROFILE`, provider URL/model, chat proxy DNS/port,
  `STEP8_ATTEMPT_LEDGER_FILE` và `STEP8_ATTEMPT_LOCK_FILE`.

Mounts giữ đúng vai trò:

- OpenSPG server bind `kag/`, `docker/sample-server.sh` và broker credentials
  read-only. Broker directory chứa `neo4j.password` và `broker.token`.
- API bind release tại `/release` và API-only credentials tại
  `/run/api-credentials`, đều read-only. Broker mode dùng `broker.token` cùng
  `sample-proof.sha256`; query thêm `query-proof.sha256`, `chat.key`,
  `embedding.key` và `egress.token`. Không đặt DB password/`reader.password`
  vào API directory trong broker mode.
- Query/inspect tokens dùng Compose secrets. Gateway chỉ mount thư mục riêng
  chứa `egress.token` cùng `docker/kag-ingress/haproxy.cfg`, read-only.
- Hai ledger/lock file binds là writable mounts của API; lock phải cùng path
  ledger với suffix `.lock`. `/tmp` và `/run/kag-locks` là tmpfs.
  Không reset, thay file rỗng hoặc chia ledger riêng để né attempt limit.

Mọi bind source phải tồn tại; Compose không tự tạo host paths. Không đưa env,
token hoặc provider keys vào Git/frontend/logs chia sẻ.

## Operational proof và rebind

Compose luôn giữ `KAG_OPERATIONAL_PROOF=DENY`, `KAG_PRODUCTION_WRITE=BLOCKED`,
`KAG_PROVIDER_EGRESS=DENY`, `KAG_DEBUG_DUMP_CONFIG=0`.
Không đặt `KAG_PROJECT_ID`/`KAG_PROJECT_HOST_ADDR`, kể cả giá trị rỗng.
SAMPLE chỉ được phục vụ khi runtime kiểm các scoped proof độc lập; đổi env không
thay thế bằng chứng.

Community SAMPLE dùng broker chỉ đọc trong OpenSPG server giữ DB credential.
API giữ broker token và kiểm physical database/server identity, read-only,
graph/provenance/source readback, code hash, Docker DNS/IP và TCP denial tới
Neo4j/Java. Đây là isolation qua broker, không phải tuyên bố Neo4j Community
có reader RBAC least-privilege.

`STEP8_BROKER_URL='http://openspg-server:8899'` cần database SAMPLE đã seal
read-only. `STEP8_SAMPLE_PROOF_SHA256` phải rỗng trong broker mode; pin nằm ở
`sample-proof.sha256`. Query pin nằm ở `query-proof.sha256`.
Release, source snapshot, schema, publication và WebApp snapshot phải khớp nhau.

Khi chuyển máy, đổi source/network hoặc recreate container:

1. Hoàn tất deployment cần thay đổi; giữ dữ liệu và ledger cũ.
2. Người vận hành đo lại backend identity, read-only, graph/source, isolation,
   Docker DNS/IP và gateway config trên deployment thực.
3. Ràng buộc supplemental SAMPLE/query proofs vào release và deployment đó;
   ghi đúng hash vào pin files. Không sửa sealed descriptor/graph/publication
   hoặc kéo dài ngày hiệu lực để vượt gate.
4. Restart cùng API container để reload pins. Nếu recreate tiếp làm identity/
   network đổi, phải đo và ràng buộc lại.
5. Kiểm authenticated readiness cho từng capability trước phục vụ query.

Git không cung cấp script tự hoàn tất provisioning/rebind cho máy mới.
Proof thiếu hoặc drift thì capability bị chặn. Liveness và release artifact
tồn tại chưa chứng minh live indexes, source readback hay serving authority.

## Provider gateway và SAMPLE query

Chat proxy chạy ngoài Compose. `STEP8_CHAT_PROXY_HOST` mặc định
`host.docker.internal`; port mặc định 8317. Có thể chọn DNS host/port riêng đã
kiểm chứng; checker không nhận IP cố định, URL hoặc `localhost` làm proxy host.
Docker dùng host-gateway mapping; proxy cần listener/firewall cho Docker truy cập.

`STEP8_QUERY_PROFILE='community-query-1.0'` dùng logical config đã pin:

```dotenv
STEP8_EMBEDDING_URL='https://api.vilao.ai/v1'
STEP8_EMBEDDING_MODEL='dg/text-embedding-3-large'
STEP8_CHAT_URL='http://127.0.0.1:8317/v1'
STEP8_CHAT_MODEL='gemini-3.8-flash-high'
```

Transport thực qua `http://kag-ingress:8898/v1`. Gateway kiểm Docker DNS nguồn
`kag-api` và token riêng; query profile rỗng thì gateway tắt bằng ACL.
`/models` và `/chat/completions` tới chat proxy; `/embeddings` tới
`api.vilao.ai:443` với TLS verification. Đổi endpoint/model cần proof mới phù hợp
source/policy, không chỉ sửa env.

Profile thông thường có cap 3 embedding/7 chat attempts; query cần còn ít nhất
4 chat attempts. Reserve vào ledger trước send; failure/timeout vẫn tính attempt.
Client retry/redirect tắt; deadline query 180 giây, tối đa 5 iteration.
Cache embedding chỉ tái dùng khi câu hỏi/hash/model/vector khớp.
Policy phát triển SAMPLE chỉ nhận khi sealed query proof có authorization,
baseline và scope `SAMPLE_DEVELOPMENT`; không mở bằng request hoặc env,
không xóa ledger khi đổi policy.

Readiness không chạy inference; có thể đọc `/models` để kiểm authentication/
model route. Metadata model không chứng minh exact upstream backend identity,
reliability hoặc billing. Response model thiếu/sai bị chặn và vẫn tính attempt.

## Kiểm cấu hình và capabilities

```powershell
$KagEnv = 'C:/kag-local/secrets/kag.env'
pwsh -NoProfile -File docker/check-config.ps1 -Stack Kag -KagEnvFile $KagEnv
```

Checker đọc config và local API image identity; không startup/pull/build/provider
inference. `test-compose.ps1` tạo fixtures/env trong thư mục tạm, không phải thao
tác chỉ đọc filesystem.

KAG healthcheck nội bộ là liveness. Health qua ingress cần service token;
readiness dùng `/v1/health?mode=ready&capability=...` theo scope và release header.
Kiểm qua Admin để tokens ở backend. `POST /v1/retrieve/vector` dùng `evidence_id`
đã seal, không embedding/chat; `POST /v1/retrieve` có thể dùng embedding.
Readiness retrieval không tự cấp query hoặc production WRITE.

`/v1/pipeline/status` và `/v1/benchmark/datasets` là inspect-only GET.
Không có endpoint chạy pipeline/benchmark. `STEP8_EVALUATION_ENABLED` chỉ đọc
dataset tại `<STEP8_RELEASE_DIR>/evaluation` qua mount hiện có; không tạo/sửa/
đóng băng dataset. Artifact integrity không thay thế gold review hoặc quyền chạy.

## Bảo toàn và migration

Giữ external credentials, backups, datasets, release artifacts, ledger và volumes.
Không dùng prune, `down -v`, reset hoặc restore đè để xử lý lỗi.
Không tác động stack legacy khi vận hành hai Compose chính.

Migration schema/database/graph và production WRITE cần kế hoạch riêng với
scope/backup/authority được duyệt. Kiểm source/config chưa chứng minh migration,
fresh install hoặc production readiness.
