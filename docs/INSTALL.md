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
git clone --recurse-submodules https://github.com/human6004/luatgt-kag.git
Set-Location luatgt-kag
```

Kết quả: có source và `vendor/KAG` đúng phiên bản. **Các lệnh còn lại chạy tại thư mục gốc này, trong cùng cửa sổ PowerShell.** Source được cấp riêng cũng phải có `.env.example` và Compose chính tự include file KAG; không dùng hướng dẫn stack cũ để bù file thiếu.

## Bước 3 — Tự động tạo mật khẩu và token

**Chỉ chạy một lần khi cài mới**, trong thư mục gốc `luatgt-kag`. Sao chép và chạy nguyên khối PowerShell dưới đây. Lệnh sẽ tự tạo `.env` với **9 mật khẩu/khóa độc lập**, mỗi giá trị là 64 ký tự hexadecimal ngẫu nhiên, đồng thời tạo **4 file token**. Không cần tự nhập từng mật khẩu hoặc chạy thêm lệnh tạo token.

```powershell
if (Test-Path -LiteralPath .env) { throw 'Đã có .env; dùng UPDATE, không tạo lại secrets.' }
if (-not (Test-Path -LiteralPath .env.example -PathType Leaf)) { throw 'Thiếu .env.example' }

$state = [IO.Path]::GetFullPath((Join-Path $PWD.Path '..\luatgt-state'))
$tokenNames = @('query', 'inspect', 'builder', 'egress')
foreach ($name in $tokenNames) {
    if (Test-Path -LiteralPath (Join-Path $state "$name.token")) { throw "Token $name đã tồn tại; không ghi đè." }
}

$keys = @('ADMIN_PASSWORD', 'DB_PASSWORD', 'MYSQL_ROOT_PASSWORD', 'REDIS_PASSWORD',
          'JWT_SECRET', 'MINIO_PASSWORD', 'KAG_MYSQL_PASSWORD',
          'KAG_NEO4J_PASSWORD', 'KAG_MINIO_PASSWORD')
$content = [IO.File]::ReadAllText((Join-Path $PWD.Path '.env.example'))
foreach ($key in $keys) {
    if ($content -notmatch "(?m)^$key=(?=\r?$)") { throw "Thiếu ô trống $key trong .env.example" }
}

$rng = [Security.Cryptography.RandomNumberGenerator]::Create()
try {
    foreach ($key in $keys) {
        $bytes = New-Object byte[] 32
        $rng.GetBytes($bytes)
        $secret = [BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant()
        $content = [regex]::Replace($content, "(?m)^$key=(?=\r?$)", "$key=$secret")
    }
    [IO.Directory]::CreateDirectory($state) | Out-Null
    foreach ($name in $tokenNames) {
        $bytes = New-Object byte[] 32
        $rng.GetBytes($bytes)
        $secret = [Text.Encoding]::ASCII.GetBytes([BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant())
        $file = [IO.File]::Open((Join-Path $state "$name.token"), [IO.FileMode]::CreateNew)
        try { $file.Write($secret, 0, $secret.Length) } finally { $file.Dispose() }
    }
    $bytes = [Text.Encoding]::UTF8.GetBytes($content)
    $file = [IO.File]::Open((Join-Path $PWD.Path '.env'), [IO.FileMode]::CreateNew)
    try { $file.Write($bytes, 0, $bytes.Length) } finally { $file.Dispose() }
} finally { $rng.Dispose() }
Write-Host 'Đã tạo .env và 4 file token. Xem ADMIN_EMAIL / ADMIN_PASSWORD trong .env để đăng nhập.'
```

Sau khi chạy, mở `notepad .env` để xem và **lưu lại** `ADMIN_EMAIL` cùng `ADMIN_PASSWORD` (đã được tạo ngẫu nhiên). Có thể đổi email Admin trước khi chạy Docker. Giữ `COMPOSE_PROJECT_NAME=luatgt` và `KAG_STATE_DIR=../luatgt-state` cho lần cài thông thường. Không chia sẻ hoặc commit `.env` và các token.

## Bước 4 — Kiểm tra token đã tạo

Bốn file `query.token`, `inspect.token`, `builder.token`, `egress.token` đã được tạo tự động trong `../luatgt-state` (ngoài repo). **Không cần chạy lại bước tạo token.** Có thể kiểm tra tên file bằng:

```powershell
Get-ChildItem ..\luatgt-state -Filter *.token -Name
```

Nếu `.env` hoặc token đã tồn tại, đoạn lệnh ở Bước 3 sẽ từ chối ghi đè; **không xóa hay tạo lại secrets của lần cài trước**. Với đường state khác mặc định, cần điều chỉnh đường dẫn `$state` cho khớp `KAG_STATE_DIR` trước khi chạy.

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
