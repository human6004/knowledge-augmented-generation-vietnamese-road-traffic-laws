# Cài đặt LuậtGT lần đầu

LuậtGT dùng KAG để tìm nội dung nguồn, trả lời kèm căn cứ và từ chối trả lời
khi thiếu bằng chứng. WebApp có tài khoản USER/ADMIN. Hướng dẫn này dành cho
**SAMPLE**, không cấp quyền build graph production hoặc chạy benchmark chính thức.

Đọc [cách sử dụng](USER-GUIDE.md) và [cập nhật giữ dữ liệu](UPDATE.md).

## 1. Điều kiện trước khi nhận bàn giao

**FRESH_INSTALL_NOT_VERIFIED**: chưa thử máy sạch. `git clone` không chứa graph
trong Docker volumes, tài khoản, publication hay credentials. Không bảo đảm
chatbot chạy ngay sau clone/up.

Ngày 12/10/2026, source được kiểm ở branch `codex/d05-d07-runner-verify-rehearsal`,
HEAD `d1d9c4fa308571f9cad6c6842bac8bfc67ecbd57` **cộng thay đổi local chưa commit**.
Remote branch vẫn ở HEAD đó; sửa trạng thái chat, diagnostic KAG, cleanup frontend,
portability và tài liệu bàn giao
chưa được phát hành đầy đủ trên GitHub. Remote default HEAD là
`0ae41304074103d843d326852a36266d99010597`. Người nhận cần chủ dự án cung cấp
revision/bundle đã nghiệm thu và manifest SHA-256; chưa có revision phát hành
đầy đủ thì chưa thể nhận bản tương đương qua GitHub. Khi chủ dự án phát hành,
dùng SHA commit/release mới chứa đủ các thay đổi này; HEAD nêu trên chỉ là baseline.

Yêu cầu chủ dự án/người vận hành cung cấp qua kênh riêng:

- Source đã nghiệm thu, submodule `vendor/KAG` đúng commit
  `fdab15b3929d2ee40dfcdd388f90233096a6afc9`.
- Bộ Docker images và manifest identity tương thích Compose: ba OpenSPG images
  pin digest trong `docker-compose.kag.yml`, runtime
  `vietroadtraffic-kag-runtime:d0.2`, MinIO KAG và API image. KAG dùng
  `pull_policy: never`; không có images trong cache sẽ không startup.
- Offline wheels đúng `requirements-http-api.txt`, gồm FastAPI 0.115.12;
  vendor Git objects lấy từ submodule đã checkout. Runtime/API cache phải khớp
  các `STEP8_*_IMAGE_ID`; đổi tag đơn thuần không làm identity hợp lệ.
- Gói backup SAMPLE được duyệt, manifest/hash và quy trình restore riêng cho
  máy mới; dữ liệu WebApp tương ứng gồm văn bản/units đã xuất bản. Nguồn JSONL
  trong Git không tự tạo Neo4j graph hoặc dữ liệu MySQL WebApp.
- Release descriptor, source catalog, graph/backend/authority receipts,
  SAMPLE/query proofs, embedding cache, publication và snapshot WebApp khớp nhau;
  API/broker/gateway token files tách riêng, ledger và lock bền vững.
- Provider credentials riêng, chat proxy được cấp quyền và model route đúng policy.
  Proxy chat chạy ngoài 11 services; repository không cài hoặc khởi động nó.

Các artifact này hiện ở workspace vận hành ngoài Git; lấy từ chủ dự án,
không lấy ngẫu nhiên từ Internet hoặc chép credentials thật vào tài liệu.
Proof mạng của máy cũ không dùng nguyên xi trên máy mới: operator cần đo lại
database/server identity, read-only, isolation, Docker DNS và pin supplemental
proof theo deployment thực. Không tự sửa ngày/hash publication để mở gate.

Baseline SAMPLE: **32 nodes / 22 edges / 42 vectors**, database `vietroadtraffic`,
namespace `VietRoadTraffic`, fingerprint
`3fbfd44d0f81e9139b3c34dffb11e2930240e8a6a3e5b58c8ed534e7af987d49`.
Publication đang kiểm có `serving_until=2026-10-18`; đây là thời hạn artifact
SAMPLE hiện tại, không bảo đảm còn hợp lệ vào ngày người nhận cài đặt.

Giới hạn nghiệm thu ngày 12/10/2026: Query/Retrieval/Vector readiness và một native
abstention qua WebApp/history đã LIVE_PASS trên máy hiện tại. Production readiness
chưa được chứng minh; Production WRITE vẫn BLOCKED. Planner RuntimeError lịch sử
chưa xác định nguyên nhân gốc. Proxy binary khớp route receipt nhưng hash config
proxy hiện khác hash lịch sử; drift chưa được giải thích hoàn toàn. Metadata
được policy hiện hữu chấp nhận không chứng minh exact upstream model identity
hoặc reliability/billing. Người vận hành cần đối chiếu các bằng chứng này trước
bàn giao; không sửa hash, model hay policy để che drift.

## 2. Phần mềm và máy

- Windows x64: Docker Desktop dùng Linux containers/WSL2, Git, PowerShell 7
  (`pwsh`), trình duyệt. Docker phải có plugin `docker compose`, BuildKit và
  `additional_contexts`. Scripts hiện gọi `rtk`; cần RTK trong PATH, lấy binary
  đã kiểm chứng từ bộ bàn giao. Không dùng Windows PowerShell 5.1 cho scripts UTF-8.
- Chạy toàn bộ bằng Docker không cần cài Java/Node/Python trên host. Phát triển
  riêng: Node 24/pnpm 10.11.0, Java 21/Maven; KAG dùng CPython 3.10.16 Linux amd64.
- Máy nghiệm thu cấp Docker khoảng 7,62 GiB RAM, 12 CPU; 11 containers lúc idle
  dùng khoảng 3,3 GiB. Riêng tổng memory limits KAG là 5,25 GiB, chưa gồm WebApp,
  build và hệ điều hành. Gợi ý máy host RAM 16 GiB, Docker từ 8 GiB, CPU 4 core,
  SSD còn ít nhất 30 GiB cho SAMPLE/images/build. Đây là mức chuẩn bị đề xuất,
  chưa đo minimum, peak hoặc tải nhiều người; backup/corpus lớn cần thêm dung lượng.

```powershell
rtk git --version
rtk proxy pwsh --version
rtk proxy docker version
rtk proxy docker compose version
rtk proxy docker info --format '{{.OSType}} {{.Architecture}} {{.MemTotal}}'
```

## 3. Lấy source và submodule

Trong PowerShell 7, clone vào thư mục riêng. Branch dưới đây là branch đã kiểm;
vẫn phải nhận phần source local chưa phát hành theo mục 1 trước khi triển khai.

```powershell
rtk git clone --branch codex/d05-d07-runner-verify-rehearsal https://github.com/human6004/knowledge-augmented-generation-vietnamese-road-traffic-laws.git
Set-Location knowledge-augmented-generation-vietnamese-road-traffic-laws
# Sau khi nhận SHA release đã phát hành từ chủ dự án:
$ReleaseRevision = '<SHA-commit-release-da-nghiem-thu>'
rtk git checkout --detach $ReleaseRevision
rtk git submodule update --init vendor/KAG
rtk git rev-parse HEAD
rtk git -C vendor/KAG rev-parse HEAD
rtk git -C vendor/KAG status --short
```

Các lệnh sau chạy từ root repository. Không đổi upstream pin. Chuẩn bị cached
images bằng gói image archive của operator (`rtk proxy docker load -i <archive>`),
đối chiếu manifest; build runtime từ source là quy trình riêng trong
[runtime](runtime.md), không tự thay cache identity của initializer.

## 4. Tạo `.env` và cấu hình KAG riêng

Chỉ dùng initializer khi **cài mới**, thư mục secrets mới chưa tồn tại.
Ví dụ `C:/kag-local` là đường dẫn người nhận tự chọn, không phải đường dẫn máy tác giả.

```powershell
rtk proxy pwsh -NoProfile -File docker/init-env.ps1
rtk proxy pwsh -NoProfile -File docker/init-step8-env.ps1 -OutputDirectory C:/kag-local/secrets -WheelDirectory C:/kag-local/offline-wheels -ProjectName kag-s8-local
```

Lệnh đầu tạo `.env` WebApp và credentials ngẫu nhiên. Lệnh thứ hai tạo external
`C:/kag-local/secrets/kag.env`, tokens, thư mục release/credentials và ledger
placeholder `{}`; **readiness vẫn DENY**. Initializer không tạo graph, provider
keys, serving proof hoặc publication. Giá trị API image ID mặc định là cache
lịch sử; operator phải chọn identity image đã bàn giao/build, không mặc định
coi đó là image mới đã nghiệm thu.

Để dùng tên `.env.kag`, sao chép `kag.env` trong cùng thư mục external qua trình
quản lý file thành `C:/kag-local/secrets/.env.kag`; giữ quyền truy cập hạn chế.
Không dùng `docker/init-env.ps1 -Kag` hoặc `.env.kag.example` cho primary Compose:
chúng là compatibility `OPENSPG_*` cũ, thiếu biến `STEP8_*`.
Không tạo `.env.kag` mới trên máy đã cài.

Mở `.env` bằng editor riêng; thêm các biến sau, thay đường dẫn/token theo gói
được cấp. Không đăng file env hoặc ảnh chứa secrets lên GitHub.

```dotenv
STEP8_KAG_PROJECT=kag-s8-local
KAG_BASE_URL=http://kag-ingress:8080
KAG_TOKEN_FILE=C:/kag-local/secrets/query.token
KAG_INSPECT_TOKEN_FILE=C:/kag-local/secrets/inspect.token
KAG_RELEASE_ID=<release-id-do-operator-cap>
KAG_WEBAPP_SNAPSHOT_ID=<snapshot-id-do-operator-cap>
KAG_QUERY_TIMEOUT_SECONDS=180
KAG_INSPECTION_TIMEOUT_SECONDS=25
```

`STEP8_KAG_PROJECT` trong hai env phải giống nhau, bắt đầu bằng `kag-s8-`.
Query/inspect là hai tokens khác nhau, khớp API; browser chỉ giữ JWT WebApp.
Tài khoản ADMIN nằm trong `.env`: `ADMIN_EMAIL`, `ADMIN_PASSWORD`; không dùng
mật khẩu mẫu công khai. USER đăng ký qua UI.

Operator hoàn thiện external `.env.kag` bằng dữ liệu máy mới, giữ định dạng
`KEY='value'`, không trùng key. Các nhóm bắt buộc xem trực tiếp
[initializer](../docker/init-step8-env.ps1) và [Compose](../docker-compose.kag.yml):

- Images/cache/build: `STEP8_API_IMAGE`, `STEP8_API_IMAGE_ID`,
  `STEP8_RUNTIME_IMAGE`, `STEP8_RUNTIME_IMAGE_ID`, `STEP8_MINIO_IMAGE`,
  `STEP8_MINIO_IMAGE_ID`, `STEP8_HTTP_WHEELS_DIR`, `STEP8_VENDOR_OBJECTS_DIR`.
- Release/reader/broker: `STEP8_RELEASE_DIR`, `STEP8_RELEASE_ID`,
  `STEP8_API_CREDENTIALS_DIR`, `STEP8_BROKER_CREDENTIALS_DIR`,
  `STEP8_BROKER_DATABASE_ID`, `STEP8_BROKER_SERVER_ID`,
  `STEP8_BROKER_URL='http://openspg-server:8899'`; broker giữ DB credential,
  API giữ broker token và proof pins, không giữ DB password.
- Query/provider: `STEP8_QUERY_PROFILE`, `STEP8_CHAT_URL`, `STEP8_CHAT_MODEL`,
  `STEP8_EMBEDDING_URL`, `STEP8_EMBEDDING_MODEL`, gateway credentials,
  `STEP8_ATTEMPT_LEDGER_FILE`, `STEP8_ATTEMPT_LOCK_FILE` và policy được cấp.
  Provider keys nằm trong API-only `chat.key`/`embedding.key`, không đưa vào frontend.
- Proxy: `STEP8_CHAT_PROXY_HOST='host.docker.internal'`,
  `STEP8_CHAT_PROXY_PORT='8317'` hoặc DNS/port riêng đã kiểm chứng.
  Linux cần listener/firewall cho Docker truy cập; không mở LAN tùy tiện.
- Graph SAMPLE được bàn giao dùng `STEP8_DATABASE='vietroadtraffic'`,
  `STEP8_READ_ONLY_DATABASES='vietroadtraffic'` và storage revision đúng volume
  đã duyệt. Không tự copy revision máy tác giả hoặc tạo graph rỗng rồi coi READY.

Không hardcode IP Docker/Wi-Fi. `STEP8_CHAT_URL` loopback là logical identity
trong policy sealed; transport thực qua ingress gateway. Đổi URL/model cần
operator kiểm proof, không tự sửa để vượt gate. Chi tiết: [Docker](../docker/README.md).

## 5. Chạy KAG trước, WebApp sau

**Chỉ chạy sau khi operator hoàn tất provisioning SAMPLE/artifacts ở mục 1–4.**
Các lệnh này startup services đã chuẩn bị; không phải quy trình restore hoặc mint
proof. Máy mới sẽ chưa query được cho tới khi operator đo/pin proof thực.

```powershell
$KagEnv = 'C:/kag-local/secrets/.env.kag'
$WebEnv = '.env'
rtk proxy pwsh -NoProfile -File docker/check-config.ps1 -Stack Kag -KagEnvFile $KagEnv
rtk proxy docker compose --env-file $KagEnv -f docker-compose.kag.yml up -d --no-build --pull never
rtk proxy pwsh -NoProfile -File docker/check-config.ps1 -Stack WebApp -WebAppEnvFile $WebEnv
rtk proxy docker compose --env-file $WebEnv -f docker-compose.yml build frontend backend minio
rtk proxy docker compose --env-file $WebEnv -f docker-compose.yml up -d --no-build
```

WebApp build lần đầu cần registry/npm/Maven/GitHub access hoặc cache tương ứng.
Backend Dockerfile chạy Maven verify và Flyway trên MySQL WebApp khi startup;
không trỏ DB_URL vào database cũ/khác. KAG API build offline chỉ cần nếu operator
chưa cấp đúng API image: xem [cập nhật API](UPDATE.md#kag-api); proof phải khớp code.

Kiểm đúng 6 + 5 services, trạng thái running; healthcheck hiện chỉ có ở một số service:

```powershell
rtk proxy docker compose --env-file $KagEnv -f docker-compose.kag.yml config --services
rtk proxy docker compose --env-file $WebEnv -f docker-compose.yml config --services
rtk proxy docker compose --env-file $KagEnv -f docker-compose.kag.yml ps
rtk proxy docker compose --env-file $WebEnv -f docker-compose.yml ps
rtk proxy curl.exe --fail http://127.0.0.1:8080/actuator/health
rtk proxy curl.exe --silent --output NUL --write-out '%{http_code}' http://127.0.0.1:38000/v1/health
```

KAG6: `openspg-mysql`, `openspg-neo4j`, `openspg-minio`, `openspg-server`,
`kag-api`, `kag-ingress`. WebApp5: `mysql`, `redis`, `minio`, `backend`, `frontend`.
KAG health không kèm token trả 401; lệnh curl trên chỉ kiểm ingress reachable.
Nếu operator kiểm trực tiếp readiness/inspection bằng service token, cần header
`X-KAG-Release-ID` khớp release đã cấp; thiếu/sai header có thể trả
`RELEASE_MISMATCH`, không đủ bằng chứng kết luận source hoặc proof đã drift.
Backend health công khai là `/actuator/health` (UP); `/api/health` không phải
endpoint kiểm công khai. Liveness 200 có token vẫn không chứng minh readiness.
Đăng nhập ADMIN → Hạ tầng/Tổng quan,
kiểm Query/Retrieval/Vector READY và graph fingerprint; release artifact có thể
hiện `NOT_READY · ARTIFACTS_ONLY` riêng, không thay thế capability readiness.

Mở **http://127.0.0.1:8081**. Backend host 8080; ingress host mặc định 38000;
MinIO console 9001. KAG API 8000 và gateway 8898 không publish host;
OpenSPG Java 8887 chỉ nghe loopback container. Nếu đổi `STEP8_API_PORT`, dùng
port host tương ứng. Các host ports chỉ bind localhost.

## 6. Dừng, chạy lại, xem lỗi

Giữ cùng `$KagEnv`, `$WebEnv`, project và working directory:

```powershell
rtk proxy docker compose --env-file $WebEnv -f docker-compose.yml stop
rtk proxy docker compose --env-file $KagEnv -f docker-compose.kag.yml stop
# Khởi động lại các container đã có: KAG trước, WebApp sau.
rtk proxy docker compose --env-file $KagEnv -f docker-compose.kag.yml start
rtk proxy docker compose --env-file $WebEnv -f docker-compose.yml start
rtk proxy docker compose --env-file $WebEnv -f docker-compose.yml logs --tail 100 frontend backend
rtk proxy docker compose --env-file $KagEnv -f docker-compose.kag.yml logs --tail 100 kag-ingress kag-api
```

Không gửi logs chưa kiểm secrets cho người khác. Thiếu external network: kiểm
KAG đã chạy và project hai env giống nhau. Thiếu token/bind/cache: bổ sung artifact
từ operator, không tạo file rỗng. `401/403`: kiểm credentials/scope.
`CONCURRENCY_LIMIT`: query đang chạy; đợi kết thúc rồi kiểm trạng thái, không tự
gửi lại inference. `NOT_READY/RELEASE_UNAVAILABLE`: xem proofs, graph, provider,
thời hạn publication. `KAG_ABSTAINED` với `native_state=abstained` là thiếu căn cứ,
khác lỗi hạ tầng dù HTTP 503. Không bypass safety.
