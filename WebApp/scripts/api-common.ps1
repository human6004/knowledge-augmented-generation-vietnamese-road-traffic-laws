$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Net.Http
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskSettings = @{}
$taskEnvFile = Join-Path $taskRoot '.env'
if (!(Test-Path -LiteralPath $taskEnvFile)) { throw 'Tạo .env trước bằng scripts/init-env.ps1.' }
foreach ($taskLine in [IO.File]::ReadAllLines($taskEnvFile)) {
    if ($taskLine -match '^([A-Z_]+)=(.*)$') { $taskSettings[$Matches[1]] = $Matches[2] }
}
$taskHttp = [Net.Http.HttpClient]::new()
$taskHttp.Timeout = [TimeSpan]::FromSeconds(90)
function Invoke-TaskApi {
    param([string]$Method, [string]$Path, [object]$Body = $null, [string]$Token = '', [string]$File = '')
    $taskRequest = [Net.Http.HttpRequestMessage]::new([Net.Http.HttpMethod]::new($Method), "$BaseUrl$Path")
    if ($Token) { $taskRequest.Headers.Authorization = [Net.Http.Headers.AuthenticationHeaderValue]::new('Bearer', $Token) }
    try {
        if ($File) {
            $taskMultipart = [Net.Http.MultipartFormDataContent]::new()
            $taskStream = [IO.File]::OpenRead($File)
            $taskPart = [Net.Http.StreamContent]::new($taskStream)
            $taskPart.Headers.ContentType = [Net.Http.Headers.MediaTypeHeaderValue]::new('application/zip')
            $taskMultipart.Add($taskPart, 'file', [IO.Path]::GetFileName($File))
            $taskRequest.Content = $taskMultipart
        } elseif ($null -ne $Body) {
            $taskRequest.Content = [Net.Http.StringContent]::new(($Body | ConvertTo-Json -Depth 50 -Compress), [Text.Encoding]::UTF8, 'application/json')
        }
        $taskResponse = $taskHttp.SendAsync($taskRequest).GetAwaiter().GetResult()
        try {
            $taskText = $taskResponse.Content.ReadAsStringAsync().GetAwaiter().GetResult()
            $taskData = if ($taskText) { $taskText | ConvertFrom-Json } else { $null }
            if (!$taskResponse.IsSuccessStatusCode) {
                throw "HTTP $([int]$taskResponse.StatusCode) $Path : $($taskData.message)"
            }
            return $taskData
        } finally { $taskResponse.Dispose() }
    } finally { $taskRequest.Dispose() }
}
function Get-TaskAdminToken {
    $taskAuth = Invoke-TaskApi POST '/auth/login' @{email=$taskSettings.ADMIN_EMAIL; password=$taskSettings.ADMIN_PASSWORD}
    return $taskAuth.accessToken
}
function Wait-TaskBackend {
    $taskHealthUrl = ($BaseUrl -replace '/api/?$', '') + '/actuator/health'
    for ($taskAttempt = 0; $taskAttempt -lt 30; $taskAttempt++) {
        try {
            $taskHealth = $taskHttp.GetAsync($taskHealthUrl).GetAwaiter().GetResult()
            try { if ($taskHealth.IsSuccessStatusCode) { return } } finally { $taskHealth.Dispose() }
        } catch { }
        Start-Sleep -Seconds 2
    }
    throw 'Backend chưa sẵn sàng. Kiểm tra docker compose logs backend rồi chạy lại.'
}
function Assert-Task { param([bool]$Condition, [string]$Message); if (!$Condition) { throw $Message } }
