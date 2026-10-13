# Windows: chuột phải > Run with PowerShell
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
Get-ChildItem images\*.tar.gz | ForEach-Object { docker load -i $_.FullName }
if (-not (Test-Path .env)) { Copy-Item env.example .env; Write-Warning "Đã tạo .env — hãy đổi mật khẩu/API key" }
docker compose --env-file .env up -d
docker compose ps
Write-Host "OpenSPG: http://localhost:8887  Web: http://localhost:8080"
