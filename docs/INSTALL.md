# Cài đặt LuậtGT trên Windows

Dành cho lần cài đầu. Máy đã có dữ liệu dùng [UPDATE](UPDATE.md), không tạo lại secrets.

## Bước 1 — Cài công cụ

Cài [Git for Windows](https://git-scm.com/install/windows) và [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/) theo yêu cầu Windows/WSL 2 của Docker. Bật ảo hóa, chọn Linux containers và đợi Docker Engine chạy.

Compose cần **từ 2.20.3** để hỗ trợ [include](https://docs.docker.com/compose/how-tos/multiple-compose-files/include/). Không cần Python, Java hay Node trên host. Dự án chưa công bố cấu hình máy tối thiểu đã đo; cần đủ RAM/disk cho 12 services, build và sao lưu.

Mở PowerShell, kiểm engine và Compose:

```powershell
docker version
docker compose version
```

Kết quả: thấy Docker Client/Server và phiên bản Compose phù hợp. Build cần mạng để tải source, images và dependencies.

## Bước 2 — Tải source

Chạy tại thư mục muốn chứa dự án:

```powershell
git clone --recurse-submodules https://github.com/human6004/knowledge-augmented-generation-vietnamese-road-traffic-laws.git
Set-Location knowledge-augmented-generation-vietnamese-road-traffic-laws
```

Kết quả: có source và `vendor/KAG` đúng phiên bản. **Các lệnh còn lại chạy tại thư mục gốc này, trong cùng cửa sổ PowerShell.** Source được cấp riêng cũng phải có `.env.example` và Compose chính tự include file KAG; không dùng hướng dẫn stack cũ để bù file thiếu.

## Bước 3 — Đặt cấu hình và mật khẩu

Tạo `.env` riêng; lệnh từ chối ghi đè cấu hình đã có:

```powershell
if (Test-Path -LiteralPath .env) { throw 'Đã có .env; dùng UPDATE.' }
Copy-Item -LiteralPath .env.example -Destination .env -ErrorAction Stop
notepad .env
```

Trong trình quản lý mật khẩu, sinh **chín giá trị độc lập**, mỗi giá trị 64 ký tự hexadecimal ngẫu nhiên (32 bytes). Điền các ô trống:

`ADMIN_PASSWORD`, `DB_PASSWORD`, `MYSQL_ROOT_PASSWORD`, `REDIS_PASSWORD`, `JWT_SECRET`, `MINIO_PASSWORD`, `KAG_MYSQL_PASSWORD`, `KAG_NEO4J_PASSWORD`, `KAG_MINIO_PASSWORD`.

Đặt `ADMIN_EMAIL`; lưu email/mật khẩu ADMIN để đăng nhập. Giữ `COMPOSE_PROJECT_NAME=luatgt`, `KAG_STATE_DIR=../luatgt-state` cho cài thông thường. Lưu file; không commit hoặc chia sẻ secrets. Không có mật khẩu ADMIN mặc định.

## Bước 4 — Tạo bốn token dịch vụ

Compose cần token riêng cho query, inspection, Builder và gateway. Với đường state mặc định, chạy một lần:

```powershell
$state = [IO.Path]::GetFullPath((Join-Path $PWD '..\luatgt-state'))
[IO.Directory]::CreateDirectory($state) | Out-Null
$rng = [Security.Cryptography.RandomNumberGenerator]::Create()
try {
    foreach ($name in 'query','inspect','builder','egress') {
        $bytes = New-Object byte[] 32
        $rng.GetBytes($bytes)
        $token = [Text.Encoding]::ASCII.GetBytes([BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant())
        $file = [IO.File]::Open((Join-Path $state "$name.token"), [IO.FileMode]::CreateNew)
        try { $file.Write($token, 0, $token.Length) } finally { $file.Dispose() }
    }
} finally { $rng.Dispose() }
```

Kết quả: `query.token`, `inspect.token`, `builder.token`, `egress.token` trong `../luatgt-state`, ngoài repo. File đã tồn tại sẽ gây lỗi, không bị ghi đè. Nếu đổi `KAG_STATE_DIR`, sửa `$state` cho khớp trước khi chạy.

Trong **Properties → Security**, giới hạn quyền đọc `.env` và state cho người vận hành, giữ quyền Docker Desktop cần để đọc chúng. Chưa cần tạo graph ở bước này.

## Bước 5 — Khởi động

```powershell
docker compose up -d --build
```

Lệnh build và chạy **12 services trong project `luatgt`**. Compose chính tự include `docker-compose.kag.yml`; không ghép hai file bằng `-f` hoặc chạy KAG riêng. Đợi tải dependencies và khởi tạo databases; chỉ tiếp tục khi lệnh kết thúc không lỗi.

## Bước 6 — Mở WebApp

```powershell
docker compose ps -a
```

Kết quả: 12 services được khởi động; các service có healthcheck chuyển sang `healthy`. Mở [WebApp](http://127.0.0.1:8081), dùng ADMIN ở Bước 3 hoặc chọn **Chưa có tài khoản? Đăng ký** để tạo USER. ADMIN vào tổng quan; USER vào chat. Đổi `.env` không đặt lại mật khẩu tài khoản cũ.

ADMIN nhập và duyệt nội dung theo [USER-GUIDE](USER-GUIDE.md). Dữ liệu trong repo không tự nạp vào MySQL/graph. Chatbot cần [cấu hình riêng](../docker/README.md#cấu-hình-chatbot); cài mặc định chưa sẵn sàng để hỏi luật hoặc dựng graph production.

**Chưa xác minh trọn quy trình trên máy sạch.** Các bước trên được đối chiếu source local; khởi động container không xác nhận chất lượng chatbot.

## Lỗi thường gặp

- Không kết nối Docker: mở Docker Desktop, kiểm Linux containers/WSL 2.
- Thiếu cấu hình/token: kiểm Bước 3–4; có thể chạy `docker compose config -q` mà không khởi động.
- Cổng bị dùng: đổi biến cổng tương ứng theo [Docker](../docker/README.md#cổng-và-mạng), rồi dùng địa chỉ mới.
- WebApp lỗi `502`: xem log backend/frontend theo [vận hành Docker](../docker/README.md#vận-hành). Sai email/mật khẩu trả `401`.
- Build không tải dependencies: kiểm thông báo mạng/registry; không đổi image pin tùy tiện.

Dừng/chạy lại theo [Docker](../docker/README.md#vận-hành). Không dùng `down -v`, xóa volumes hoặc prune để sửa lỗi.
