param([switch]$Kag, [switch]$Update)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskFile = if ($Kag) { '.env.kag' } else { '.env' }
$taskEnv = Join-Path $taskRoot $taskFile
if ((Test-Path -LiteralPath $taskEnv) -and !($Kag -or $Update)) { throw "$taskFile đã tồn tại; dùng -Update để bổ sung biến còn thiếu." }
function New-TaskSecret {
    $taskBytes = [byte[]]::new(32)
    $taskRng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $taskRng.GetBytes($taskBytes) } finally { $taskRng.Dispose() }
    return [BitConverter]::ToString($taskBytes).Replace('-', '').ToLowerInvariant()
}
if ($Kag) {
    $taskValues = @(
        "OPENSPG_MYSQL_PASSWORD=$(New-TaskSecret)",
        "OPENSPG_NEO4J_PASSWORD=$(New-TaskSecret)",
        'OPENSPG_MINIO_USER=minio',
        "OPENSPG_MINIO_PASSWORD=$(New-TaskSecret)"
    )
    # Reuse credentials from the previous combined configuration when first separating KAG.
    $taskLegacyFile = Join-Path $taskRoot '.env'
    if (!(Test-Path -LiteralPath $taskEnv) -and (Test-Path -LiteralPath $taskLegacyFile)) {
        $taskLegacy = @([IO.File]::ReadAllLines($taskLegacyFile) | Where-Object { $_ -match '^OPENSPG_[A-Z0-9_]+=' })
        $taskLegacyKeys = @($taskLegacy | ForEach-Object { ($_ -split '=', 2)[0] })
        $taskValues = @($taskValues | Where-Object { ($_ -split '=', 2)[0] -notin $taskLegacyKeys }) + $taskLegacy
    }
} else {
    $taskValues = @(
        "DB_PASSWORD=$(New-TaskSecret)",
        "MYSQL_ROOT_PASSWORD=$(New-TaskSecret)",
        "REDIS_PASSWORD=$(New-TaskSecret)",
        "JWT_SECRET=$(New-TaskSecret)",
        'MINIO_USER=luatgt-local',
        "MINIO_PASSWORD=$(New-TaskSecret)",
        'ADMIN_EMAIL=admin@luatgt.local',
        "ADMIN_PASSWORD=$(New-TaskSecret)",
        'KAG_BASE_URL=http://host.docker.internal:8000'
    )
}
if (Test-Path -LiteralPath $taskEnv) {
    $taskKeys = @([IO.File]::ReadAllLines($taskEnv) | Where-Object { $_ -match '^([A-Z0-9_]+)=' } | ForEach-Object { ($_ -split '=', 2)[0] })
    $taskMissing = @($taskValues | Where-Object { ($_ -split '=', 2)[0] -notin $taskKeys })
    if ($taskMissing.Count) { [IO.File]::AppendAllLines($taskEnv, [string[]](@('') + $taskMissing), [Text.UTF8Encoding]::new($false)) }
    Write-Output "Đã bổ sung biến còn thiếu vào $taskFile; giữ nguyên thông tin hiện có."
} else {
    [IO.File]::WriteAllLines($taskEnv, [string[]]$taskValues, [Text.UTF8Encoding]::new($false))
    Write-Output "Đã tạo $taskFile. Thông tin đăng nhập nằm trong file này."
}
