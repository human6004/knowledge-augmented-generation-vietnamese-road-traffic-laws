$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskEnv = Join-Path $taskRoot '.env'
if (Test-Path -LiteralPath $taskEnv) { throw '.env đã tồn tại; không ghi đè thông tin đăng nhập.' }
function New-TaskSecret {
    $taskBytes = [byte[]]::new(32)
    $taskRng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $taskRng.GetBytes($taskBytes) } finally { $taskRng.Dispose() }
    return [BitConverter]::ToString($taskBytes).Replace('-', '').ToLowerInvariant()
}
$taskValues = @(
    "DB_PASSWORD=$(New-TaskSecret)",
    "REDIS_PASSWORD=$(New-TaskSecret)",
    "JWT_SECRET=$(New-TaskSecret)",
    'MINIO_USER=luatgt-local',
    "MINIO_PASSWORD=$(New-TaskSecret)",
    'ADMIN_EMAIL=admin@luatgt.local',
    "ADMIN_PASSWORD=$(New-TaskSecret)",
    'KAG_BASE_URL=http://host.docker.internal:8000'
)
[IO.File]::WriteAllLines($taskEnv, $taskValues, [Text.UTF8Encoding]::new($false))
Write-Output 'Đã tạo .env với mật khẩu ngẫu nhiên. Thông tin ADMIN nằm trong .env.'
