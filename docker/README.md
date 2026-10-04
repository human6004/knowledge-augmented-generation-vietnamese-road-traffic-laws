Dockerfile của backend, frontend và MinIO nằm tại đây. Hai stack dùng hai file Compose tại root repository, chạy các lệnh dưới đây từ root.

| Stack | File Compose | Project | Cấu hình môi trường |
| --- | --- | --- | --- |
| WebApp | `docker-compose.yml` | `webapp` | `.env` |
| KAG / OpenSPG | `docker-compose.kag.yml` | `kag` | `.env.kag` |

Hai stack có image, mạng, database, tài khoản và volume riêng. Không có dependency Compose giữa hai stack. WebApp tích hợp với adapter KAG qua HTTP `KAG_BASE_URL` và cùng identity schema contract (`namespace`, `schema_sha256`, `contract_sha256`). Chạy/dừng/build từng stack bằng file tương ứng; không ghép hai file bằng nhiều cờ `-f` vào một project.

## Điều kiện chạy

- Docker Desktop đang chạy ở chế độ Linux containers, có Docker Compose.
- PowerShell 7 (`pwsh`) để chạy các script `.ps1` UTF-8; Windows PowerShell 5.1 có thể đọc sai file không có BOM.
- Chạy lệnh từ root repository. Cần mạng cho lần pull image hoặc build MinIO đầu tiên; MinIO build từ nguồn nên có thể mất nhiều phút.
- Cần đủ RAM và dung lượng Docker cho tổng số stack đang chạy. JVM OpenSPG mặc định 2–8 GB; Neo4j heap 1–4 GB và page cache 1 GB. Kiểm tra bằng `docker stats --no-stream` khi chạy nhiều stack.

## Chạy WebApp độc lập

```powershell
./docker/init-env.ps1 # Chỉ chạy khi chưa có .env
# Nếu .env đã có: ./docker/init-env.ps1 -Update
docker compose up -d --build
./docker/check-config.ps1 -Stack WebApp
./WebApp/scripts/verify-stack.ps1
```

WebApp gồm frontend, backend Spring Boot, MySQL nghiệp vụ, Redis và MinIO. Giao diện ở http://127.0.0.1:8081, API ở http://127.0.0.1:8080/api. WebApp chạy được mà không cần OpenSPG hoặc `.env.kag`; chat KAG báo chưa khả dụng khi adapter Python chưa chạy.

Backend dùng tài khoản `luatgt` và `DB_PASSWORD`, không dùng root. MySQL 8.4.11 ở `127.0.0.1:3306`, database `luatgt`, volume `webapp_kag-data`; Redis/MinIO dùng `webapp_redis-data` và `webapp_minio-data`. Văn bản dùng `utf8mb4_0900_bin`, thời gian lưu UTC.

Flyway V1/V2 dùng cú pháp MySQL, V3 thêm đơn vị pháp lý. Không chạy các migration này lên PostgreSQL. Volume `webapp_postgres-data` không bị sửa/xóa và không tự chuyển dữ liệu sang MySQL.

Backend build từ root để Maven đóng gói trực tiếp `kag/schema/schema_contract.json` và `VietRoadTraffic.schema` cùng source Java tại `WebApp/`. Build context chỉ lấy source WebApp và hai file schema; runtime/core KAG không nằm trong image Java. Backend kiểm tra SHA-256 của schema đóng gói khớp `runtime_contract.schema_sha256`; khi contract hoặc schema đổi cần build lại backend. Namespace vẫn là `VietRoadTraffic`, với 75 thuộc tính logical, 69 thuộc tính khai báo và sáu thuộc tính `id/name` kế thừa OpenSPG `Thing`.

```powershell
# Build hoặc dừng riêng WebApp:
docker compose build backend frontend minio
docker compose down
```

## Chạy KAG / OpenSPG độc lập

```powershell
./docker/init-env.ps1 -Kag # Chỉ cần khi chưa có .env.kag
docker compose --env-file .env.kag -f docker-compose.kag.yml up -d --build
./docker/check-config.ps1 -Stack Kag
docker compose --env-file .env.kag -f docker-compose.kag.yml logs --tail 100 openspg-server
```

KAG/OpenSPG gồm server, MySQL metadata, Neo4j và MinIO, chạy trực tiếp dưới project `kag`, không cần profile hay WebApp đang chạy. Adapter/builder/retriever/solver Python của project chưa triển khai; stack này hiện khởi chạy engine OpenSPG, chưa phải dịch vụ hỏi đáp KAG hoàn chỉnh.

OpenSPG Server là lớp API và điều phối. MySQL lưu metadata, project và schema OpenSPG. Neo4j lưu knowledge graph và phục vụ tìm kiếm. MinIO lưu object. Các thành phần Python kết nối theo sơ đồ:

```text
KAG Python
Builder / Retriever / Solver
          |
          | HTTP
          v
    OpenSPG Server
      /    |    \
     v     v     v
  MySQL  Neo4j  MinIO
 metadata graph storage
```

Python chạy trực tiếp trên Windows dùng địa chỉ OpenSPG `http://127.0.0.1:28887`. Tên service như `openspg-server` chỉ phân giải được trong mạng Docker của stack.

Tham chiếu [Compose chính thức](https://github.com/OpenSPG/openspg/blob/ceeb3ef549df79ca4c4878e7ff452c73584991f3/dev/release/docker-compose-west.yml), đối chiếu [KAG đã pin](https://github.com/OpenSPG/KAG/blob/fdab15b3929d2ee40dfcdd388f90233096a6afc9/README.md). MySQL upstream có sẵn SQL khởi tạo OpenSPG; không thay bằng image MySQL trắng hoặc PostgreSQL.

| Dịch vụ | Địa chỉ từ host | Địa chỉ trong mạng KAG |
| --- | --- | --- |
| OpenSPG UI/API | http://127.0.0.1:28887 | http://openspg-server:8887 |
| MySQL metadata | 127.0.0.1:23306 | openspg-mysql:3306 |
| Neo4j Browser / Bolt | http://127.0.0.1:27474 / 127.0.0.1:27687 | openspg-neo4j:7687 |
| MinIO API / Console | http://127.0.0.1:29000 / http://127.0.0.1:29001 | openspg-minio:9000 |

Các cổng chỉ bind localhost. Mạng KAG là `kag_openspg`; các alias `mysql`, `neo4j`, `minio` chỉ dùng bên trong mạng này. Tên volume:

```text
kag_openspg-mysql-data
kag_openspg-neo4j-data
kag_openspg-neo4j-logs
kag_openspg-minio-data
```

Chọn từng lệnh dưới đây theo tác vụ, không chạy cả khối tuần tự. `restart` chỉ áp dụng khi container còn tồn tại; sau `down`, dùng `up -d`.

```powershell
# Trạng thái: MySQL/Neo4j cần healthy; server/MinIO cần running.
docker compose --env-file .env.kag -f docker-compose.kag.yml ps
# Log của server; thay tên service để xem MySQL, Neo4j hoặc MinIO.
docker compose --env-file .env.kag -f docker-compose.kag.yml logs --tail 200 openspg-server
# Dừng và gỡ container/network, giữ dữ liệu trong volume.
docker compose --env-file .env.kag -f docker-compose.kag.yml down
# Khởi động lại các container hiện có.
docker compose --env-file .env.kag -f docker-compose.kag.yml restart
# Chạy lại sau down; tái sử dụng volume hiện có.
docker compose --env-file .env.kag -f docker-compose.kag.yml up -d
# Build/pull riêng KAG khi cần cập nhật image.
docker compose --env-file .env.kag -f docker-compose.kag.yml build openspg-minio
docker compose --env-file .env.kag -f docker-compose.kag.yml pull openspg-server openspg-mysql openspg-neo4j
```

`restart` không áp dụng thay đổi `.env.kag` hoặc Compose. Sau khi chỉnh cấu hình, dùng `up -d` để Compose cập nhật container. Server dùng entrypoint `java`; JVM flags đứng trước đúng một `-jar`.

## Persistence và backup

`down` giữ bốn named volume KAG; `up -d` gắn lại các volume đó. Dữ liệu trong MySQL, Neo4j và MinIO lưu ở volume, không nằm trong `.env.kag` hay source repository. Giữ `.env.kag` để tiếp tục dùng đúng credential.

**`down -v` xóa volume và dữ liệu KAG.** Chỉ dùng khi chủ động reset một môi trường test có dữ liệu được phép xóa. Không dùng global prune để dọn riêng project này.

Trước khi cập nhật image hoặc reset dữ liệu, backup riêng MySQL metadata, Neo4j và MinIO bằng công cụ phù hợp từng dịch vụ. Nếu backup bằng bản sao volume, dừng riêng stack KAG để dữ liệu nhất quán, sao lưu đủ bốn volume, rồi khởi động lại. Không xem việc giữ volume trên cùng Docker Desktop là một bản backup. Lưu credential riêng, ngoài Git.

## Chạy song song

Với WebApp, chạy lần lượt hai lệnh `up` của từng stack. Project `webapp` và `kag` có mạng, volume và cổng riêng. Dùng đúng file Compose và env khi xem log hoặc dừng một stack.

Với project `D:\study\HoiThao\kag-legal-assistant`, giữ nguyên các container `release-openspg-*`, mounts và volume của project đó. Stack KAG hiện tại dùng tên container do Compose sinh và các cổng host riêng ở bảng trên; project cũ có thể tiếp tục chạy trên 8887, 3306, 7474, 7687, 9000 và 9001. Nếu cổng hiện tại bị chiếm, xác định chủ sở hữu trước khi xử lý. Không chạy Compose từ project cũ để vận hành project này, không dừng hoặc xóa container cũ, không dùng chung volume.

Không tự lấy dữ liệu từ stack `vietroadtraffic_b2c` hoặc các volume tên cũ.

## Biến môi trường và kiểm tra

`.env.example` và `.env.kag.example` là hai mẫu cấu hình không chứa mật khẩu. `docker/init-env.ps1` tạo `.env` chỉ cho WebApp; `-Kag` tạo `.env.kag` chỉ cho OpenSPG. Chạy lại `-Update` hoặc `-Kag` chỉ bổ sung biến thiếu, giữ thông tin hiện có. Khi `.env.kag` chưa tồn tại, `-Kag` tái sử dụng các biến `OPENSPG_*` trong `.env` nếu có. Không xóa hoặc tạo lại `.env.kag` chỉ để restart. `WebApp/scripts/init-env.ps1` gọi script chung.

```powershell
# Kiểm tra cả hai cấu hình, tên project, dependency, cổng, volume:
./docker/check-config.ps1
# Kiểm tra bootstrap/env độc lập trong fixture tạm; không cần Docker Engine:
./docker/test-compose.ps1
```

Trong OpenSPG UI, cấu hình lưu trữ MinIO theo URL `minio://openspg-minio:9000?accessKey=<OPENSPG_MINIO_USER>&secretKey=<OPENSPG_MINIO_PASSWORD>` với giá trị từ `.env.kag`. Nếu image có kết nối mặc định dùng mật khẩu mẫu upstream, cập nhật kết nối trước khi upload/build. MySQL và Neo4j nhận kết nối/mật khẩu trực tiếp qua tham số server.

Image server/MySQL/Neo4j mặc định dùng `latest` như upstream. Để tái lập bộ đã kiểm thử, đặt `OPENSPG_SERVER_IMAGE`, `OPENSPG_MYSQL_IMAGE`, `OPENSPG_NEO4J_IMAGE` trong `.env.kag` thành image `@sha256:...`. MinIO dùng Dockerfile đã pin nguồn của project. JVM mặc định 2–8 GB, Neo4j heap tối đa 4 GB và page cache 1 GB. Có thể chỉnh `OPENSPG_JAVA_XMS`, `OPENSPG_JAVA_XMX`, `OPENSPG_BUILDER_CONCURRENCY` (mặc định 4).

OpenSPG engine không cung cấp `/v1/query` và `/v1/query/stream` mà WebApp gọi. Giữ `KAG_BASE_URL` trong `.env` cho adapter Python tại cổng 8000; không trỏ tới OpenSPG UI cổng 28887. Không tự import dataset/schema hoặc bật ingestion khi khởi động. Core KAG sẽ triển khai riêng; Builder phải tuân thủ [contract runtime](../docs/schema.md#contract-runtime-và-yêu-cầu-builder), kiểm tra dữ liệu, codec và gộp provenance xác định trước khi ghi graph.
