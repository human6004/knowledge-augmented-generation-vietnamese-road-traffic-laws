# Cập nhật LuậtGT, giữ dữ liệu

Cập nhật source và service cần đổi; giữ dữ liệu, volumes và artifacts vận hành.
Điều kiện cài đặt: [INSTALL](INSTALL.md). Dùng UI: [USER-GUIDE](USER-GUIDE.md).

## 1. Kiểm source và phạm vi thay đổi

Chạy từ root repository:

```powershell
git branch --show-current
git rev-parse HEAD
git status --short
git submodule status vendor/KAG
git fetch origin
git log --oneline 'HEAD..@{upstream}'
git diff --name-only HEAD '@{upstream}'
```

Bản source chính nằm trên `main`. Nếu branch đang dùng chưa có upstream, đối chiếu
ref/revision được người quản lý chọn trước khi cập nhật. Tree có thay đổi local:
dừng pull, lưu patch và bản copy file untracked ở nơi riêng; không ghi đè hoặc tự
stash/reset.

Đọc diff để chọn mục cập nhật bên dưới. Nếu thay `kag/`, broker có bind source
chỉ đọc nên đổi source cũng có thể làm proof drift; chọn cửa sổ bảo trì trước
khi pull. Thay schema, migrations, corpus hoặc networking cần mục 7.

Khi tree sạch và upstream/revision đã được chọn:

```powershell
git pull --ff-only
git submodule update --init vendor/KAG
git rev-parse HEAD
git -C vendor/KAG rev-parse HEAD
```

Không dùng `submodule update --remote`. Pin hiện tại:
`fdab15b3929d2ee40dfcdd388f90233096a6afc9`. Nếu fast-forward bị từ chối,
để người quản lý xử lý divergence; không force/reset/rebase để vượt lỗi.

## 2. Giữ env và artifacts đang dùng

```powershell
$KagEnv = 'C:/kag-local/secrets/kag.env'
$WebEnv = '.env'
pwsh -NoProfile -File docker/check-config.ps1 -Stack WebApp -WebAppEnvFile $WebEnv
pwsh -NoProfile -File docker/check-config.ps1 -Stack Kag -KagEnvFile $KagEnv
```

Thay đường dẫn ví dụ bằng env installation hiện có. Checker KAG cần RTK trong
PATH và cached API image đúng ID khai báo. Giữ nguyên project, storage revision,
volume names, token/credentials, ledger/lock và paths ngoài Git. Không chạy
initializer để tạo lại installation. Không xuất toàn bộ env/Compose config
ra nơi chia sẻ.

Trước thay đổi ảnh hưởng dữ liệu, có backup nhất quán và cách phục hồi đã chuẩn bị
cho databases, object storage, release/catalog/proofs/publication, env và ledger.
Giữ image cũ cùng commit/image identity để có phương án rollback service.

## 3. Chỉ frontend

Khi chỉ React/styles thay đổi và backend contract tương thích:

```powershell
docker compose --env-file $WebEnv -f docker-compose.yml build frontend
docker compose --env-file $WebEnv -f docker-compose.yml up -d --no-deps --no-build --pull never frontend
docker compose --env-file $WebEnv -f docker-compose.yml ps frontend
curl.exe --fail http://127.0.0.1:8081/
```

Reload trình duyệt, kiểm đăng nhập, routes và history/citations đã lưu.
Chỉ gửi câu hỏi mới khi cần kiểm inference và được cấp budget.

## 4. Backend

Đọc migrations trước; Flyway tự chạy khi backend startup. Thay schema/database
cần kế hoạch ở mục 7 trước. Build thành công chưa chứng minh migration thành công.

```powershell
docker compose --env-file $WebEnv -f docker-compose.yml build backend
docker compose --env-file $WebEnv -f docker-compose.yml up -d --no-deps --no-build --pull never backend
curl.exe --fail http://127.0.0.1:8080/actuator/health
docker compose --env-file $WebEnv -f docker-compose.yml logs --tail 100 backend
```

Dockerfile chạy Maven verify. Kiểm login, phân quyền và contract WebApp → KAG.
Backend vẫn dùng `http://kag-ingress:8080` qua external ingress network.
Cập nhật frontend cùng lúc khi UI/API contract yêu cầu.

## KAG API

Cập nhật sau khi đối chiếu tương thích code/schema/source/proof và có kế hoạch
đo lại authority. `kag-api` đóng gói source; `openspg-server` bind `kag/` chỉ đọc.
Đổi source có thể ảnh hưởng broker cùng với API.

Build offline cần cached runtime đúng identity, wheels và vendor Git objects
đúng pin:

```powershell
docker compose --env-file $KagEnv -f docker-compose.kag.yml build kag-api
$ApiImage = '<STEP8_API_IMAGE-dang-cau-hinh>'
docker image inspect --format '{{.Id}}' $ApiImage
```

Cập nhật `STEP8_API_IMAGE_ID` bằng ID vừa đối chiếu; giữ nguyên những env/
credentials/paths khác. Không đổi vendor hoặc model để vượt lỗi build.

```powershell
pwsh -NoProfile -File docker/check-config.ps1 -Stack Kag -KagEnvFile $KagEnv
docker compose --env-file $KagEnv -f docker-compose.kag.yml up -d --no-deps --no-build --pull never kag-api
```

Recreate có thể đổi container identity hoặc IP. Đo lại isolation, DNS, code và
backend identity, rồi pin supplemental SAMPLE/query proofs cho deployment cuối.
Xem [operational proof và rebind](../docker/README.md#operational-proof-và-rebind).
Sau ghi pin file, restart cùng API container để reload; tránh recreate thêm
sau khi đã ràng buộc proof. Liveness có thể lên trong khi query vẫn bị chặn.

Không sửa descriptor, graph hoặc publication để ép READY; Git không cung cấp
một script tự cấp đầy đủ serving authority cho máy mới.

## 6. Chỉ tài liệu

Nếu diff chỉ có Markdown: cập nhật source an toàn, kiểm links/file paths;
không cần build hoặc restart services.

## 7. Database/schema/graph hoặc Compose networking

Thay migrations, schema, corpus, storage revision, mounts, project/network hoặc
graph inputs cần review tương thích, backup phục hồi được và kế hoạch riêng.
Phạm vi gồm MySQL WebApp, OpenSPG MySQL/Neo4j, MinIO, Redis cùng các artifacts
release/catalog/proofs/publication và credentials/ledger ngoài Git.

Giữ volume names/project/storage revision để không tạo nhầm database rỗng.
Backup cần nhất quán với ứng dụng; không tùy ý copy live database files.
Restore/build graph khác cập nhật frontend hoặc API. Đọc
[vận hành](runner.md), [backend identity](backend-identity.md),
[writer scope](production-writer-scope.md) và [Docker](../docker/README.md).

Không xóa volumes, prune, reset graph/database, xoay credentials hoặc reset
ledger để cập nhật. Production WRITE giữ `BLOCKED`.

## 8. Kiểm sau cập nhật và xử lý lỗi

```powershell
docker compose --env-file $KagEnv -f docker-compose.kag.yml ps
docker compose --env-file $WebEnv -f docker-compose.yml ps
curl.exe --fail http://127.0.0.1:8080/actuator/health
curl.exe --silent --output NUL --write-out '%{http_code}' http://127.0.0.1:38000/v1/health
docker compose --env-file $WebEnv -f docker-compose.yml logs --tail 100 frontend backend
docker compose --env-file $KagEnv -f docker-compose.kag.yml logs --tail 100 kag-ingress kag-api
```

KAG health qua ingress không token dự kiến trả 401; chỉ chứng minh ingress
phản hồi. Nếu đổi `STEP8_API_PORT`, dùng port đã cấu hình. Đọc authenticated
liveness/readiness qua Admin Hạ tầng/Tổng quan; kiểm capabilities và graph
fingerprint riêng với release artifact. Không đưa service token vào browser.

USER kiểm UI và history đã lưu. `KAG_ABSTAINED` là native thiếu căn cứ được
backend xác minh; lỗi `NOT_READY/RELEASE_UNAVAILABLE`, runtime/provider hoặc
response không hợp lệ được xử lý là unavailable. Đọc history trước gửi lại;
chỉ chạy câu SAMPLE khi publication/readiness, credentials và budget hợp lệ.

Nếu lỗi sau build, giữ logs đã che secrets và đối chiếu commit/image/contract.
Rollback service bằng image đã xác minh theo kế hoạch người vận hành.
Rollback database sau migration cần quy trình riêng; không bỏ safety.
Hướng dẫn này chưa xác minh fresh install, migration hoặc restore trên máy khác.
