# Cập nhật code, giữ dữ liệu

Chạy trong PowerShell 7 tại root repository. Không cần cài lại toàn bộ Docker.
Giữ nguyên env, project names, storage revision, token files, ledger và volumes.
Điều kiện lần đầu: [INSTALL](INSTALL.md). Dùng UI: [USER-GUIDE](USER-GUIDE.md).

## 1. Kiểm source trước khi lấy bản mới

```powershell
rtk git branch --show-current
rtk git rev-parse HEAD
rtk git status --short
rtk git submodule status vendor/KAG
rtk git fetch origin
rtk git log --oneline 'HEAD..@{upstream}'
rtk git diff --name-only HEAD '@{upstream}'
```

Nếu branch chưa có upstream, dùng ref branch do chủ dự án xác nhận thay vì
đoán `main`. Nếu working tree có thay đổi local: **dừng cập nhật**, lưu patch/bản
copy gồm cả file untracked ở nơi riêng, trao đổi với người quản lý source.
Không ghi đè, tự stash hoặc checkout đè file. Đọc release notes/diff để phân
loại thay đổi; không pull phiên bản chưa được nghiệm thu tương thích.

Khi tree sạch và revision đúng branch đã được bàn giao:

```powershell
rtk git pull --ff-only
rtk git submodule update --init vendor/KAG
rtk git rev-parse HEAD
rtk git -C vendor/KAG rev-parse HEAD
```

Không dùng `submodule update --remote`. Nếu fast-forward bị từ chối, dừng để
người quản lý xử lý divergence; không reset/rebase/force. Ngày 12/10/2026, bản
sửa trạng thái chat/diagnostic KAG/cleanup/portability/handover còn local chưa
commit: pull remote hiện tại chưa cung cấp đầy đủ bản đã nghiệm thu. Chỉ cập nhật
sang SHA release mới sau khi chủ dự án công bố đầy đủ source và manifest.

## 2. Chọn env đang dùng

```powershell
$KagEnv = 'C:/kag-local/secrets/.env.kag'
$WebEnv = '.env'
rtk proxy pwsh -NoProfile -File docker/check-config.ps1 -Stack WebApp -WebAppEnvFile $WebEnv
rtk proxy pwsh -NoProfile -File docker/check-config.ps1 -Stack Kag -KagEnvFile $KagEnv
```

Thay đường dẫn ví dụ bằng env của installation hiện có; file KAG có thể tên
`kag.env`, không bắt buộc `.env.kag`. `STEP8_KAG_PROJECT` hai env phải cùng giá trị.
Không chạy initializer lại, không thay credentials/project/revision chỉ để update.
Không xuất toàn bộ `compose config`/env ra nơi chia sẻ vì có secrets.

Health backend công khai là `/actuator/health`. KAG `/v1/health` cần service token;
curl không token ở các mục sau dự kiến trả 401, chỉ chứng minh ingress reachable.
Đọc liveness/readiness có authentication qua UI Admin, không đưa service token
vào browser hoặc câu lệnh chia sẻ.

## 3. Chỉ frontend

Khi chỉ source React/styles thay đổi, backend contract không đổi:

```powershell
rtk proxy docker compose --env-file $WebEnv -f docker-compose.yml build frontend
rtk proxy docker compose --env-file $WebEnv -f docker-compose.yml up -d --no-deps --no-build --pull never frontend
rtk proxy docker compose --env-file $WebEnv -f docker-compose.yml ps frontend
rtk proxy curl.exe --fail http://127.0.0.1:8081/
```

Reload trình duyệt, đăng nhập USER/ADMIN, mở chat/lịch sử/citations và routes Admin.
Nếu đã có Node/dependencies: chạy `rtk proxy node node_modules/typescript/bin/tsc
--noEmit --incremental false`, `rtk npm test`, `rtk npm run build` trong
`WebApp/frontend` trước deployment. Không install dependency mới chỉ để cập nhật
image Docker. Thao tác frontend-only ở mục này đã chạy LIVE trên máy nghiệm thu.

## 4. Backend

Đọc migrations trong source trước. Nếu thay schema/database, áp dụng mục 7 trước;
Flyway tự chạy lúc backend startup. Không coi backend build PASS là migration PASS.

```powershell
rtk proxy docker compose --env-file $WebEnv -f docker-compose.yml build backend
rtk proxy docker compose --env-file $WebEnv -f docker-compose.yml up -d --no-deps --no-build --pull never backend
rtk proxy curl.exe --fail http://127.0.0.1:8080/actuator/health
rtk proxy docker compose --env-file $WebEnv -f docker-compose.yml logs --tail 100 backend
```

Dockerfile chạy Maven verify. Kiểm login, phân quyền, citation-source parity và
WebApp → KAG; cập nhật frontend cùng lúc chỉ khi UI/API contract yêu cầu.
Backend vẫn nối `http://kag-ingress:8080` qua external ingress network, không cần
IP máy tác giả. Mục này STATIC VERIFIED theo Dockerfile/Compose; lượt bàn giao
không rebuild/recreate backend.

## KAG API

Chỉ cập nhật sau review tương thích code/schema/source/proof và kế hoạch re-prove
do operator chấp thuận. `kag-api` đóng gói source; `openspg-server` bind source
`kag/` chỉ đọc nên broker cũng có thể bị ảnh hưởng ngay khi source đổi. Đây không
phải hot update toàn KAG. Tránh update khi đang query; người vận hành chọn cửa sổ
bảo trì phù hợp.

```powershell
rtk proxy docker compose --env-file $KagEnv -f docker-compose.kag.yml build kag-api
# Lấy ID image tag STEP8_API_IMAGE đang cấu hình; không in env chứa secrets.
$ApiImage = 'ten-image-tag-da-cau-hinh' # Thay bằng STEP8_API_IMAGE hiện có.
rtk proxy docker image inspect --format '{{.Id}}' $ApiImage
```

Operator cập nhật **đúng** `STEP8_API_IMAGE_ID` trong env hiện có, giữ nguyên
mọi passwords/tokens/ledger/path khác. Build cần runtime cache, offline wheels
và vendor objects đã verified; không tự pull/đổi vendor hoặc model để vượt lỗi.

```powershell
rtk proxy pwsh -NoProfile -File docker/check-config.ps1 -Stack Kag -KagEnvFile $KagEnv
rtk proxy docker compose --env-file $KagEnv -f docker-compose.kag.yml up -d --no-deps --no-build --pull never kag-api
rtk proxy curl.exe --silent --output NUL --write-out '%{http_code}' http://127.0.0.1:38000/v1/health
```

Recreate/code change có thể làm proof identity/code/isolation drift: liveness
có thể lên nhưng query/retrieval phải fail closed tới khi operator đo và pin lại
supplemental proof qua quy trình hiện có, rồi reload API đúng cách. Không sửa
descriptor/graph/publication để ép READY; không sao chép IP/identity cũ.
Không đưa lệnh mint proof tự động vào update vì Git không chứa workflow phục vụ
máy mới hoàn chỉnh. Hạng mục này STATIC VERIFIED; chưa chạy deployment trong task.

## 6. Chỉ tài liệu

Sau lấy source an toàn, không build/restart container nếu chỉ Markdown thay đổi.
Kiểm links/file paths; deployment images không cần chứa tài liệu mới.

## 7. Database/schema/graph hoặc Compose networking

Không tự nâng cấp khi diff có migrations, schema, corpus, storage revision,
mounts, project/network hoặc graph inputs. Cần review tương thích, backup phục hồi
được và kế hoạch riêng cho MySQL WebApp, OpenSPG MySQL/Neo4j, MinIO, Redis,
release/catalog/proofs/publication, env/tokens và ledger. Đọc
[vận hành](runner.md), [backend identity](backend-identity.md),
[writer scope](production-writer-scope.md) và [Docker](../docker/README.md).

Giữ volume names/project/storage revision để không vô tình tạo database mới rỗng.
Backup application-consistent của operator; không copy live database files tùy ý.
Proof/schema/graph update khác frontend-only update; chưa nghiệm thu migration
hoặc restore trong hướng dẫn này. Không reset graph/database, xóa volumes, prune,
xoay credentials hoặc ghi đè env. Production WRITE giữ BLOCKED.

## 8. Kiểm sau update và khi lỗi

```powershell
rtk proxy docker compose --env-file $KagEnv -f docker-compose.kag.yml ps
rtk proxy docker compose --env-file $WebEnv -f docker-compose.yml ps
rtk proxy curl.exe --fail http://127.0.0.1:8080/actuator/health
rtk proxy curl.exe --silent --output NUL --write-out '%{http_code}' http://127.0.0.1:38000/v1/health
rtk proxy docker compose --env-file $WebEnv -f docker-compose.yml logs --tail 100 frontend backend
rtk proxy docker compose --env-file $KagEnv -f docker-compose.kag.yml logs --tail 100 kag-ingress kag-api
```

Admin Hạ tầng/Tổng quan: kiểm capabilities và SAMPLE fingerprint riêng với
liveness/artifact. USER: kiểm chat UI, lịch sử, đối chiếu quote; không gửi inference
để thử đi thử lại. Chỉ chạy câu SAMPLE có sẵn khi budget/credentials, publication,
offline checks và readiness hợp lệ. `KAG_ABSTAINED` là native legal abstention;
`NOT_READY/RELEASE_UNAVAILABLE` và lỗi runtime/provider được WebApp lưu thành
`UNAVAILABLE`; native abstention đã xác minh được lưu riêng `KAG_ABSTAINED`.
Lịch sử giữ nguyên trạng thái, không backfill các record lỗi cũ.
Live abstention mới nhất chỉ bao phủ một negative SAMPLE qua REST/history;
Planner RuntimeError lịch sử và proxy config hash drift vẫn chưa được giải thích
hoàn toàn. Xem [USER-GUIDE](USER-GUIDE.md) và [giới hạn bàn giao](INSTALL.md#1-điều-kiện-trước-khi-nhận-bàn-giao).

Nếu lỗi sau build: giữ image cũ và logs an toàn, đối chiếu commit/image/contract;
chỉ rollback service bằng image đã xác minh theo kế hoạch operator. Không tự
rollback database sau migration hoặc bỏ safety. Chưa thử fresh install/migration
trên máy khác: **FRESH_INSTALL_NOT_VERIFIED**.
