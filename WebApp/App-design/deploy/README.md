# Docker riêng cho kag-legal

Thay thế `docker-compose-west.yml` của OpenSPG. Image gốc chỉ dùng làm lớp nền khi build; sau đó mọi thứ
được gắn tên `kag-legal-*:1.0.0` và đóng thành **một tệp** để chia sẻ.

| Bước | Lệnh |
|---|---|
| 1. Cấu hình | `cp env.example .env` rồi đổi mật khẩu |
| 2. Build | `./build.sh` |
| 3. Chạy thử | `docker compose up -d` |
| 4. Đóng gói | `./pack.sh` → `dist/kag-legal-bundle-1.0.0.tar.gz` |
| 5. Máy bạn bè | giải nén → `./install.sh` (hoặc `install.ps1` trên Windows) |

Khác biệt so với compose gốc:
- mật khẩu, cổng, bộ nhớ đọc từ `.env` (không viết cứng);
- volume có tên (dữ liệu không mất khi xoá container);
- healthcheck + `depends_on: service_healthy` (server chờ DB sẵn sàng);
- neo4j tự nạp `dumps/legal.dump` ở lần chạy đầu;
- cổng MySQL/Neo4j/MinIO chỉ bind 127.0.0.1;
- múi giờ Asia/Ho_Chi_Minh.

Lưu ý: image OpenSPG theo giấy phép Apache-2.0 — giữ LICENSE khi phân phối lại.
