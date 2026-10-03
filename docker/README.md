Dockerfile của backend, frontend và MinIO nằm tại đây. Hai stack dùng hai file Compose tại root repository, chạy các lệnh dưới đây từ root.

| Stack | File Compose | Project | Cấu hình môi trường |
| --- | --- | --- | --- |
| WebApp | `docker-compose.yml` | `webapp` | `.env` |
| KAG / OpenSPG | `docker-compose.kag.yml` | `kag` | `.env.kag` |

Hai stack có image, mạng, database, tài khoản và volume riêng. Không có dependency Compose giữa hai stack. WebApp tích hợp với adapter KAG qua HTTP `KAG_BASE_URL` và cùng phiên bản schema contract. Chạy/dừng/build từng stack bằng file tương ứng; không ghép hai file bằng nhiều cờ `-f` vào một project.

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

Đây là schema MySQL mới; Flyway V1/V2 đã chuyển cú pháp từ PostgreSQL, V3 thêm đơn vị pháp lý. Không chạy các migration này lên PostgreSQL. Volume cũ `webapp_postgres-data` không bị sửa/xóa và không tự chuyển dữ liệu sang MySQL. Người dùng đã xác nhận chưa có dữ liệu cần chuyển.

Backend build từ root để Maven đóng gói trực tiếp `kag/schema/schema_contract.json` và `VietRoadTraffic.schema` cùng source Java. Build context chỉ lấy source WebApp và hai file schema; runtime/core KAG không nằm trong image Java. Khi contract đổi cần build lại backend.

```powershell
# Build hoặc dừng riêng WebApp:
docker compose build backend frontend minio
docker compose down
```

## Chạy KAG / OpenSPG độc lập

```powershell
./docker/init-env.ps1 -Kag
docker compose --env-file .env.kag -f docker-compose.kag.yml up -d --build
./docker/check-config.ps1 -Stack Kag
docker compose --env-file .env.kag -f docker-compose.kag.yml logs --tail 100 openspg-server
```

KAG/OpenSPG gồm server, MySQL metadata, Neo4j và MinIO, chạy trực tiếp dưới project `kag`, không cần profile hay WebApp đang chạy. Adapter/builder/retriever/solver Python của project chưa triển khai; stack này hiện khởi chạy engine OpenSPG, chưa phải dịch vụ hỏi đáp KAG hoàn chỉnh.

Tham chiếu [Compose chính thức](https://github.com/OpenSPG/openspg/blob/ceeb3ef549df79ca4c4878e7ff452c73584991f3/dev/release/docker-compose-west.yml), đối chiếu [KAG đã pin](https://github.com/OpenSPG/KAG/blob/fdab15b3929d2ee40dfcdd388f90233096a6afc9/README.md). MySQL upstream có sẵn SQL khởi tạo OpenSPG; không thay bằng image MySQL trắng hoặc PostgreSQL.

| Dịch vụ | Địa chỉ từ host | Địa chỉ trong mạng KAG |
| --- | --- | --- |
| OpenSPG UI/API | http://127.0.0.1:28887 | http://openspg-server:8887 |
| MySQL metadata | 127.0.0.1:23306 | openspg-mysql:3306 |
| Neo4j Browser / Bolt | http://127.0.0.1:27474 / 127.0.0.1:27687 | openspg-neo4j:7687 |
| MinIO API / Console | http://127.0.0.1:29000 / http://127.0.0.1:29001 | openspg-minio:9000 |

Các cổng chỉ bind localhost, không trùng WebApp hoặc stack cũ trong ảnh. Mạng KAG là `kag_openspg`; các alias `mysql`, `neo4j`, `minio` chỉ dùng bên trong mạng này. Tên volume giữ nguyên:

```text
kag_openspg-mysql-data
kag_openspg-neo4j-data
kag_openspg-neo4j-logs
kag_openspg-minio-data
```

```powershell
# Build/pull hoặc dừng riêng KAG:
docker compose --env-file .env.kag -f docker-compose.kag.yml build openspg-minio
docker compose --env-file .env.kag -f docker-compose.kag.yml pull openspg-server openspg-mysql openspg-neo4j
docker compose --env-file .env.kag -f docker-compose.kag.yml down
```

Muốn chạy cả hai, chạy lần lượt hai lệnh `up` ở trên; chúng vẫn là hai project độc lập. Các lệnh `down` giữ volume. Không dùng `down -v` nếu cần giữ dữ liệu. Không tự lấy dữ liệu từ stack `vietroadtraffic_b2c` hoặc các volume tên cũ.

## Biến môi trường và kiểm tra

`.env.example` và `.env.kag.example` là hai mẫu cấu hình không chứa mật khẩu. `docker/init-env.ps1` tạo `.env` chỉ cho WebApp; `-Kag` tạo `.env.kag` chỉ cho OpenSPG. Chạy lại `-Update` hoặc `-Kag` chỉ bổ sung biến thiếu, giữ thông tin hiện có. Khi lần đầu tách cấu hình cũ, `-Kag` tái sử dụng các biến `OPENSPG_*` trong `.env` nếu có. Cấu hình local hiện tại đã chuyển các biến này sang `.env.kag`, giữ nguyên giá trị. `WebApp/scripts/init-env.ps1` tiếp tục hoạt động bằng cách gọi script chung.

```powershell
# Kiểm tra cả hai cấu hình, tên project, dependency, cổng, volume:
./docker/check-config.ps1
# Kiểm tra bootstrap/env độc lập trong fixture tạm; không cần Docker Engine:
./docker/test-compose.ps1
```

Trong OpenSPG UI, cấu hình lưu trữ MinIO theo URL `minio://openspg-minio:9000?accessKey=<OPENSPG_MINIO_USER>&secretKey=<OPENSPG_MINIO_PASSWORD>` với giá trị từ `.env.kag`. Nếu image có kết nối mặc định dùng mật khẩu mẫu upstream, cập nhật kết nối trước khi upload/build. MySQL và Neo4j nhận kết nối/mật khẩu trực tiếp qua tham số server.

Image server/MySQL/Neo4j mặc định dùng `latest` như upstream. Để tái lập bộ đã kiểm thử, đặt `OPENSPG_SERVER_IMAGE`, `OPENSPG_MYSQL_IMAGE`, `OPENSPG_NEO4J_IMAGE` trong `.env.kag` thành image `@sha256:...`. MinIO dùng Dockerfile đã pin nguồn của project. JVM mặc định 2–8 GB, Neo4j heap tối đa 4 GB và page cache 1 GB. Có thể chỉnh `OPENSPG_JAVA_XMS`, `OPENSPG_JAVA_XMX`, `OPENSPG_BUILDER_CONCURRENCY` (mặc định 4).

OpenSPG engine không cung cấp `/v1/query` và `/v1/query/stream` mà WebApp gọi. Giữ `KAG_BASE_URL` trong `.env` cho adapter Python tại cổng 8000; không trỏ tới OpenSPG UI cổng 28887. Không tự import dataset/schema hoặc bật ingestion khi khởi động. Các xác nhận server trong [schema.md](../docs/schema.md#xác-nhận-bắt-buộc-trước-ingestion) vẫn chờ thực hiện trước ingestion.
