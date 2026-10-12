# Cài đặt LuậtGT lần đầu

LuậtGT cung cấp WebApp cho USER/ADMIN, nối KAG để tra cứu luật giao thông và
đọc căn cứ nguồn. Hướng dẫn này dành cho triển khai **SAMPLE**. Production WRITE
giữ `BLOCKED`; bộ benchmark chính thức chưa hoàn thành.

Đọc [cách sử dụng](USER-GUIDE.md), [cập nhật giữ dữ liệu](UPDATE.md) và
[cấu hình Docker cho người vận hành](../docker/README.md).

## 1. Phần mềm và máy

- Windows x64, Docker Desktop dùng Linux containers/WSL2, Git, PowerShell 7
  (`pwsh`) và trình duyệt. Scripts UTF-8 dùng PowerShell 7.
- Initializer/checker KAG gọi RTK bên trong; máy dùng các scripts đó cần `rtk`
  trong PATH. App/container không cần RTK.
- Docker cần plugin `docker compose`, BuildKit và `additional_contexts`.
  KAG dùng nền tảng `linux/amd64`.
- Chạy bằng Docker không cần cài Java, Node hoặc Python trên host. Khi phát triển
  riêng: frontend dùng Node 24/pnpm 10.11.0, backend Java 21/Maven, KAG CPython
  3.10.16 với dependencies đã pin.
- Chuẩn bị RAM và SSD cho cả hai stack, images, build và backup. Tổng giới hạn
  RAM khai báo riêng KAG là 5,25 GiB; cần thêm dung lượng cho WebApp, Docker và
  hệ điều hành. Chưa xác định cấu hình tối thiểu hoặc khả năng chịu tải.

Kiểm công cụ:

```powershell
git --version
pwsh --version
docker version
docker compose version
docker info --format '{{.OSType}} {{.Architecture}} {{.MemTotal}}'
```

## 2. Lấy source và submodule

Clone branch `main`, rồi mở PowerShell 7 tại thư mục repository:

```powershell
git clone --branch main https://github.com/human6004/knowledge-augmented-generation-vietnamese-road-traffic-laws.git
git submodule update --init vendor/KAG
git rev-parse HEAD
git -C vendor/KAG rev-parse HEAD
git -C vendor/KAG status --short
```

Submodule `vendor/KAG` phải ở commit
`fdab15b3929d2ee40dfcdd388f90233096a6afc9`, không có thay đổi local.
Không dùng `submodule update --remote`. Khi triển khai, ghi lại commit source
và đối chiếu phiên bản đó với bộ artifacts/images do người vận hành cung cấp.

Các lệnh còn lại chạy từ root repository.

## 3. Chuẩn bị phần vận hành ngoài Git

Git chứa source, Compose, scripts, schema và dữ liệu nguồn. Clone không tạo graph
Neo4j, dữ liệu MySQL WebApp, tài khoản, publication, provider keys hoặc serving
proof. Chưa xác minh cài đặt hoàn chỉnh trên máy sạch.

Người vận hành cần chuẩn bị:

- Cached images đúng Compose và manifest identity: OpenSPG/HAProxy pin digest,
  runtime `vietroadtraffic-kag-runtime:d0.2`, MinIO KAG và API image tương thích.
  KAG dùng `pull_policy: never`; thiếu cache thì không startup.
- Offline wheels theo `requirements-http-api.txt`, gồm FastAPI 0.115.12 đúng hash;
  Git objects của submodule đúng pin khi build API.
- Graph SAMPLE và dữ liệu WebApp tương ứng, gồm văn bản/units được duyệt và
  xuất bản. Restore hoặc tạo graph cần kế hoạch vận hành riêng.
- Release descriptor, source catalog, backend/authority receipts, SAMPLE/query
  proofs, embedding cache và publication còn hiệu lực, cùng snapshot WebApp.
- External env, query/inspect tokens khác nhau, credentials riêng cho broker/API/
  gateway, ledger và lock bền vững.
- Provider credentials, chat proxy ngoài Compose và model route phù hợp proof.
  Repository không cài hoặc khởi động chat proxy.

Lấy bộ artifacts qua kênh bàn giao của dự án; đối chiếu hash/identity trước dùng.
Không đưa secrets vào Git. Proof gắn với deployment: chuyển máy hoặc recreate
container cần đo lại backend identity, read-only, isolation, Docker DNS và ràng
buộc proof mới. Không chép IP/identity máy cũ hay sửa ngày/hash sealed bundle
để mở readiness.

## 4. Tạo env và cấu hình

Chỉ khởi tạo khi cài mới. Ví dụ `C:/kag-local` là thư mục ngoài Git do người
vận hành chọn; thay bằng nơi lưu artifacts của bạn. Chuẩn bị wheel cache trước.
`$ApiImageId` phải là ID image API đã đối chiếu với bộ bàn giao:

```powershell
$ApiImageId = '<sha256-ID-image-API-da-doi-chieu>'
pwsh -NoProfile -File docker/init-env.ps1
pwsh -NoProfile -File docker/init-step8-env.ps1 -OutputDirectory C:/kag-local/secrets -WheelDirectory C:/kag-local/offline-wheels -ProjectName kag-s8-local -ApiImageId $ApiImageId
```

Lệnh đầu tạo `.env` WebApp với credentials ngẫu nhiên. Lệnh thứ hai tạo external
`C:/kag-local/secrets/kag.env`, tokens, thư mục release/credentials và ledger
placeholder `{}`. Initializer không tạo graph, provider keys, proof hoặc
publication; readiness vẫn chưa được cấp. Thư mục output phải chưa tồn tại.
Không dùng image ID mặc định của initializer thay cho ID image đã bàn giao.

Dùng trực tiếp `kag.env`; tên file không bắt buộc là `.env.kag`.
`docker/init-env.ps1 -Kag` và `.env.kag.example` thuộc cấu hình compatibility
`OPENSPG_*`, thiếu biến `STEP8_*` cho Compose chính.

Mở `.env` WebApp bằng editor riêng và thêm:

```dotenv
STEP8_KAG_PROJECT=kag-s8-local
KAG_BASE_URL=http://kag-ingress:8080
KAG_TOKEN_FILE=C:/kag-local/secrets/query.token
KAG_INSPECT_TOKEN_FILE=C:/kag-local/secrets/inspect.token
KAG_RELEASE_ID=<release-id-duoc-cap>
KAG_WEBAPP_SNAPSHOT_ID=<snapshot-id-duoc-cap>
KAG_QUERY_TIMEOUT_SECONDS=180
KAG_INSPECTION_TIMEOUT_SECONDS=25
```

`STEP8_KAG_PROJECT` hai env phải giống nhau và bắt đầu bằng `kag-s8-`.
Token files phải khớp KAG API; browser chỉ dùng JWT WebApp. Tài khoản ADMIN
khởi tạo từ `ADMIN_EMAIL`/`ADMIN_PASSWORD` trong `.env`; USER đăng ký qua UI.

Người vận hành hoàn thiện `kag.env` theo [Docker](../docker/README.md),
[initializer](../docker/init-step8-env.ps1) và [Compose](../docker-compose.kag.yml).
Giữ định dạng `KEY='value'`, không trùng key. Cần đúng paths, image IDs,
database/storage revision, broker identity, release, provider/model và proof pins.
SAMPLE broker dùng database `vietroadtraffic` đã seal read-only; storage revision
phải khớp volume được cấp. Không đổi revision để vô tình tạo graph rỗng.

Chat proxy dùng DNS host/port đã kiểm chứng; mặc định
`host.docker.internal:8317`. URL/model logical trong proof khác transport gateway;
không sửa endpoint hoặc model chỉ để vượt gate.

## 5. Chạy KAG trước, WebApp sau

Chỉ startup sau khi người vận hành chuẩn bị images, mounts và cấu hình phù hợp.
Đây là lệnh chạy services, không thay quy trình restore hoặc cấp serving proof:

```powershell
$KagEnv = 'C:/kag-local/secrets/kag.env'
$WebEnv = '.env'
pwsh -NoProfile -File docker/check-config.ps1 -Stack Kag -KagEnvFile $KagEnv
docker compose --env-file $KagEnv -f docker-compose.kag.yml up -d --no-build --pull never
pwsh -NoProfile -File docker/check-config.ps1 -Stack WebApp -WebAppEnvFile $WebEnv
docker compose --env-file $WebEnv -f docker-compose.yml build frontend backend minio
docker compose --env-file $WebEnv -f docker-compose.yml up -d --no-build
```

WebApp build cần registry/npm/Maven/GitHub access hoặc cache tương ứng. Backend
Dockerfile chạy Maven verify; Flyway chạy khi backend startup trên MySQL WebApp.
KAG API build offline chỉ cần khi chưa có image phù hợp: xem
[cập nhật API](UPDATE.md#kag-api). Build runtime có hướng dẫn riêng tại
[runtime](runtime.md).

Deployment mới cần người vận hành đo và pin lại proof sau startup, rồi reload
API theo [quy trình ràng buộc proof](../docker/README.md#operational-proof-và-rebind).
Container chạy hoặc healthcheck xanh chưa đủ để chat.

## 6. Mở UI và kiểm kết nối

```powershell
docker compose --env-file $KagEnv -f docker-compose.kag.yml ps
docker compose --env-file $WebEnv -f docker-compose.yml ps
curl.exe --fail http://127.0.0.1:8080/actuator/health
curl.exe --silent --output NUL --write-out '%{http_code}' http://127.0.0.1:38000/v1/health
```

Mở [LuậtGT](http://127.0.0.1:8081). Backend dùng host port 8080; KAG ingress
mặc định 38000; MinIO WebApp console 9001. Host ports chỉ bind localhost.
Nếu đổi `STEP8_API_PORT`, kiểm KAG bằng port đã chọn.

Backend health công khai là `/actuator/health`. KAG health qua ingress không có
service token trả 401: lệnh trên chỉ kiểm ingress phản hồi. Không đưa service token
vào browser. Đăng nhập ADMIN, mở **Hạ tầng** hoặc **Tổng quan** để đọc liveness,
Query/Retrieval/Vector readiness và graph fingerprint. Release artifact tồn tại
không thay cho capability readiness.

## 7. Dừng, chạy lại và xử lý lỗi

Giữ cùng env, project và thư mục làm việc:

```powershell
docker compose --env-file $WebEnv -f docker-compose.yml stop
docker compose --env-file $KagEnv -f docker-compose.kag.yml stop
docker compose --env-file $KagEnv -f docker-compose.kag.yml start
docker compose --env-file $WebEnv -f docker-compose.yml start
docker compose --env-file $WebEnv -f docker-compose.yml logs --tail 100 frontend backend
docker compose --env-file $KagEnv -f docker-compose.kag.yml logs --tail 100 kag-ingress kag-api
```

- Thiếu external network: kiểm KAG đã startup và project hai env giống nhau.
- Thiếu image, token hoặc bind mount: bổ sung đúng bộ artifacts; không tạo file
  rỗng thay credential/proof.
- `401/403`: kiểm token và scope. Kiểm readiness/inspection trực tiếp còn cần
  `X-KAG-Release-ID` khớp release; thiếu/sai header có thể trả `RELEASE_MISMATCH`.
- `CONCURRENCY_LIMIT`: đợi query hiện tại kết thúc, đọc lại trạng thái/lịch sử
  trước gửi lại.
- `NOT_READY/RELEASE_UNAVAILABLE`: người vận hành kiểm release, proofs, graph,
  provider route và thời hạn publication.
- `KAG_ABSTAINED` với `native_state=abstained` là thiếu căn cứ đã được xác minh,
  khác lỗi hạ tầng dù native API dùng HTTP 503.

Kiểm và che secrets trước chia sẻ logs. Không bỏ authentication, mở production
WRITE, xóa volumes hoặc reset ledger để xử lý lỗi.
