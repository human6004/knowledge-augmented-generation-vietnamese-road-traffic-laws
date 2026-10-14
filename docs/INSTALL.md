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

Chạy trong thư mục gốc `luatgt-kag`. Đoạn PowerShell dưới đây tạo `.env` nếu chưa có, với **9 mật khẩu/khóa độc lập**, mỗi giá trị là 64 ký tự hexadecimal ngẫu nhiên, và tạo các token còn thiếu. Nếu đã được cấp `.env` để cài mới trên máy riêng, giữ file đó và chạy cùng đoạn lệnh để tự tạo 4 token. `.env` và token đã tồn tại không bị ghi đè. Máy có database cũ phải giữ bộ secrets tương ứng, dùng [UPDATE](UPDATE.md).

```powershell
$ErrorActionPreference = 'Stop'
$createEnv = -not (Test-Path -LiteralPath .env)
$envSource = if ($createEnv) { '.env.example' } else { '.env' }
$content = [IO.File]::ReadAllText((Join-Path $PWD.Path $envSource))
$stateSetting = [regex]::Match($content, '(?m)^KAG_STATE_DIR=([^\r\n]+)')
if (-not $stateSetting.Success) { throw 'Cần đặt KAG_STATE_DIR trong .env hoặc .env.example.' }
$statePath = $stateSetting.Groups[1].Value.Trim().Trim([char]34, [char]39)
if ([string]::IsNullOrWhiteSpace($statePath)) { throw 'KAG_STATE_DIR không được để trống.' }
$state = [IO.Path]::GetFullPath((Join-Path $PWD.Path $statePath))
$tokenNames = @('query', 'inspect', 'builder', 'egress')

$keys = @('ADMIN_PASSWORD', 'DB_PASSWORD', 'MYSQL_ROOT_PASSWORD', 'REDIS_PASSWORD',
          'JWT_SECRET', 'MINIO_PASSWORD', 'KAG_MYSQL_PASSWORD',
          'KAG_NEO4J_PASSWORD', 'KAG_MINIO_PASSWORD')
foreach ($key in $keys) {
    if ($createEnv -and $content -notmatch "(?m)^$key=(?=\r?$)") { throw "Thiếu ô trống $key trong .env.example" }
    if (-not $createEnv -and $content -notmatch "(?m)^$key=\S+(?=\r?$)") { throw "Thiếu giá trị $key trong .env" }
}

$rng = [Security.Cryptography.RandomNumberGenerator]::Create()
try {
    foreach ($key in $(if ($createEnv) { $keys })) {
        $bytes = New-Object byte[] 32
        $rng.GetBytes($bytes)
        $secret = [BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant()
        $content = [regex]::Replace($content, "(?m)^$key=(?=\r?$)", "$key=$secret")
    }
    [IO.Directory]::CreateDirectory($state) | Out-Null
    foreach ($name in $tokenNames) {
        if (Test-Path -LiteralPath (Join-Path $state "$name.token")) { continue }
        $bytes = New-Object byte[] 32
        $rng.GetBytes($bytes)
        $secret = [Text.Encoding]::ASCII.GetBytes([BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant())
        $file = [IO.File]::Open((Join-Path $state "$name.token"), [IO.FileMode]::CreateNew)
        try { $file.Write($secret, 0, $secret.Length) } finally { $file.Dispose() }
    }
    if ($createEnv) {
        $bytes = [Text.Encoding]::UTF8.GetBytes($content)
        $file = [IO.File]::Open((Join-Path $PWD.Path '.env'), [IO.FileMode]::CreateNew)
        try { $file.Write($bytes, 0, $bytes.Length) } finally { $file.Dispose() }
    }
} finally { $rng.Dispose() }
Write-Host 'Đã chuẩn bị .env và token; giữ nguyên các file đã có. Xem ADMIN_EMAIL / ADMIN_PASSWORD trong .env để đăng nhập.'
```

Sau khi chạy, mở `notepad .env` để xem và **lưu lại** `ADMIN_EMAIL` cùng `ADMIN_PASSWORD`. Có thể đổi email Admin trước khi chạy Docker. Cài mới dùng `COMPOSE_PROJECT_NAME=luatgt` và `KAG_STATE_DIR=./.secrets`. Thư mục `.secrets/` nằm trong repo local nhưng không được đưa lên GitHub hoặc vào Docker build context. Không commit `.env` và token; mỗi máy nên tạo bộ secrets riêng.

## Bước 4 — Kiểm tra token đã tạo

Bốn file `query.token`, `inspect.token`, `builder.token`, `egress.token` nằm trong thư mục được chỉ định bởi `KAG_STATE_DIR`. Với cài mới mặc định, kiểm tra:

```powershell
Get-ChildItem .\.secrets -Filter *.token -Name
```

Đoạn lệnh ở Bước 3 đọc đường dẫn từ `.env` nếu file đã tồn tại. Cài đặt cũ dùng `../luatgt-state` vẫn giữ nguyên đường dẫn đó. **Không xóa hay tạo lại secrets của lần cài trước.** Khi dùng đường state khác, thay đường dẫn trong lệnh kiểm tra cho khớp.

Trong **Properties → Security**, giới hạn quyền đọc `.env` và state cho người vận hành, giữ quyền Docker Desktop cần để đọc chúng. Chưa cần tạo graph ở bước này.


## Bước 5 — Khởi động

Sau khi hoàn tất tạo `.env` và 4 token, chạy tại thư mục gốc `luatgt-kag`:

```powershell
docker compose up -d --build
```

Docker Compose sẽ tự build các image cần thiết và khởi động 12 services trong project `luatgt`.

Image `luatgt-kag:local` được build từ source code trong repository, không cần tải từ Docker Hub hoặc đăng nhập Docker Hub.

Compose chính tự include `docker-compose.kag.yml`. Không cần chạy KAG riêng hoặc ghép hai file bằng `-f`.

Lần cài đầu có thể mất nhiều thời gian vì Docker cần tải images và dependencies. Hãy đợi lệnh chạy xong.

Sau đó kiểm tra:

```powershell
Write-Host "Exit code: $LASTEXITCODE"
docker compose ps -a
```

Nếu exit code là `0`, lệnh Compose đã hoàn thành thành công. Tiếp tục kiểm tra trạng thái các services.

Nếu exit code khác `0`, hoặc có service `Exited` hoặc `Unhealthy`, kiểm tra log của service đó trước khi tiếp tục.

Không xóa Docker volumes, không tạo lại `.env` hoặc token để xử lý lỗi khởi động.


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
