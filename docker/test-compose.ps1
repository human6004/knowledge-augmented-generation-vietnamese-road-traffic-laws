param([string]$Docker = 'docker')
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskTempBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$taskTempRoot = Join-Path $taskTempBase ("luatgt-compose-" + [Guid]::NewGuid().ToString('N'))
function Assert-Task([bool]$Condition, [string]$Message) { if (!$Condition) { throw $Message } }
try {
    $null = New-Item -ItemType Directory -Path "$taskTempRoot/docker"
    Copy-Item -LiteralPath "$PSScriptRoot/init-env.ps1" -Destination "$taskTempRoot/docker/init-env.ps1"
    & "$taskTempRoot/docker/init-env.ps1" -Kag
    Assert-Task (!(Test-Path -LiteralPath "$taskTempRoot/.env")) 'KAG bootstrap không được tạo cấu hình WebApp.'
    Assert-Task (@(Get-Content "$taskTempRoot/.env.kag" | Where-Object { $_ -notmatch '^OPENSPG_[A-Z0-9_]+=' }).Count -eq 0) 'KAG env phải chỉ chứa biến OpenSPG.'
    & "$taskTempRoot/docker/init-env.ps1"
    Assert-Task (!(Select-String -LiteralPath "$taskTempRoot/.env" -Pattern '^OPENSPG_')) 'WebApp env không được chứa biến OpenSPG.'
    $taskWebappHash = (Get-FileHash "$taskTempRoot/.env").Hash
    $taskKagHash = (Get-FileHash "$taskTempRoot/.env.kag").Hash
    & "$taskTempRoot/docker/init-env.ps1" -Update
    & "$taskTempRoot/docker/init-env.ps1" -Kag
    Assert-Task ($taskWebappHash -eq (Get-FileHash "$taskTempRoot/.env").Hash) 'Update đã đổi cấu hình WebApp hiện có.'
    Assert-Task ($taskKagHash -eq (Get-FileHash "$taskTempRoot/.env.kag").Hash) 'Update đã đổi cấu hình KAG hiện có.'
    foreach ($taskPair in @(@('docker-compose.yml','.env'),@('docker-compose.kag.yml','.env.kag'))) {
        & $Docker compose --project-directory $taskRoot --env-file "$taskTempRoot/$($taskPair[1])" -f "$taskRoot/$($taskPair[0])" config --quiet
        Assert-Task ($LASTEXITCODE -eq 0) "$($taskPair[0]) phải kiểm tra được với env riêng, không cần env của stack còn lại."
    }
    Remove-Item -LiteralPath "$taskTempRoot/.env.kag"
    Add-Content -LiteralPath "$taskTempRoot/.env" -Value 'OPENSPG_NEO4J_PASSWORD=legacy-test-value'
    & "$taskTempRoot/docker/init-env.ps1" -Kag
    Assert-Task ([bool](Select-String -LiteralPath "$taskTempRoot/.env.kag" -Pattern '^OPENSPG_NEO4J_PASSWORD=legacy-test-value$')) 'Tách cấu hình cũ phải giữ mật khẩu OpenSPG.'
    Write-Output 'PASS: independent WebApp/KAG env initialization and Compose interpolation; credentials preserved on repeat and legacy migration.'
} finally {
    $taskResolved = [IO.Path]::GetFullPath($taskTempRoot)
    if (!$taskResolved.StartsWith($taskTempBase, [StringComparison]::OrdinalIgnoreCase) -or !(Split-Path -Leaf $taskResolved).StartsWith('luatgt-compose-')) { throw 'Đường dẫn dọn fixture không hợp lệ.' }
    if (Test-Path -LiteralPath $taskResolved) { Remove-Item -LiteralPath $taskResolved -Recurse -Force }
}
