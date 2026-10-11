param([string]$Docker = 'docker', [Parameter(Mandatory=$true)][string]$KagEnvFile)
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
    $taskTokenFile = Join-Path $taskTempRoot 'kag-query.test-token'
    $taskInspectFile = Join-Path $taskTempRoot 'kag-inspect.test-token'
    [IO.File]::WriteAllText($taskTokenFile, ('t' * 64), [Text.Encoding]::ASCII)
    [IO.File]::WriteAllText($taskInspectFile, ('i' * 64), [Text.Encoding]::ASCII)
    Add-Content -LiteralPath "$taskTempRoot/.env" -Value "KAG_TOKEN_FILE=$($taskTokenFile.Replace('\', '/'))"
    Add-Content -LiteralPath "$taskTempRoot/.env" -Value "KAG_INSPECT_TOKEN_FILE=$($taskInspectFile.Replace('\', '/'))"
    $taskWebappHash = (Get-FileHash "$taskTempRoot/.env").Hash
    $taskKagHash = (Get-FileHash "$taskTempRoot/.env.kag").Hash
    & "$taskTempRoot/docker/init-env.ps1" -Update
    & "$taskTempRoot/docker/init-env.ps1" -Kag
    Assert-Task ($taskWebappHash -eq (Get-FileHash "$taskTempRoot/.env").Hash) 'Update đã đổi cấu hình WebApp hiện có.'
    Assert-Task ($taskKagHash -eq (Get-FileHash "$taskTempRoot/.env.kag").Hash) 'Update đã đổi cấu hình KAG hiện có.'
    foreach ($taskPair in ,@('docker-compose.yml','.env')) {
        & $Docker compose --project-directory $taskRoot --env-file "$taskTempRoot/$($taskPair[1])" -f "$taskRoot/$($taskPair[0])" config --quiet
        Assert-Task ($LASTEXITCODE -eq 0) "$($taskPair[0]) phải kiểm tra được với env riêng, không cần env của stack còn lại."
    }
    $taskFixtureEnv = Join-Path $taskTempRoot 'kag.env'
    $taskGenerated = Join-Path $taskTempRoot 'step8-init'
    $taskWheelEnv = ([IO.File]::ReadAllLines($KagEnvFile) | Where-Object { $_ -match "^STEP8_HTTP_WHEELS_DIR='([^']+)'$" })
    if (!$taskWheelEnv -or $taskWheelEnv -notmatch "^STEP8_HTTP_WHEELS_DIR='([^']+)'$") { throw 'Offline wheel fixture missing.' }
    & "$PSScriptRoot/init-step8-env.ps1" -OutputDirectory $taskGenerated -WheelDirectory $Matches[1] -ProjectName 'kag-s8-init-test' -ApiImageId 'sha256:d854da5ecb3d9e26b110723ffc466e3568b6b8b1ed765fc49265f066c43c8d2a'
    Assert-Task ([bool](Select-String -LiteralPath "$taskGenerated/kag.env" -Pattern "^STEP8_API_IMAGE_ID='sha256:d854da5ecb3d9e26b110723ffc466e3568b6b8b1ed765fc49265f066c43c8d2a'$")) 'Initializer must preserve the explicitly verified API image identity.'
    Assert-Task (Test-Path -LiteralPath "$taskGenerated/broker-credentials" -PathType Container) 'Initializer must create a separate empty broker credential directory.'
    Assert-Task (@(Get-ChildItem -LiteralPath "$taskGenerated/broker-credentials").Count -eq 0) 'Initializer must not create broker credentials or activate serving.'
    foreach ($taskKey in @('STEP8_BROKER_URL','STEP8_BROKER_DATABASE_ID','STEP8_BROKER_SERVER_ID')) {
        Assert-Task ([bool](Select-String -LiteralPath "$taskGenerated/kag.env" -Pattern "^$taskKey=''$")) 'Initializer must leave broker identity and routing disabled.'
    }
    Copy-Item -LiteralPath $KagEnvFile -Destination $taskFixtureEnv
    $taskBrokerFixture = Join-Path $taskTempRoot 'broker-credentials'
    [void][IO.Directory]::CreateDirectory($taskBrokerFixture)
    $taskFixtureText = [IO.File]::ReadAllText($taskFixtureEnv)
    foreach ($taskKey in @('STEP8_BROKER_CREDENTIALS_DIR','STEP8_BROKER_URL','STEP8_BROKER_DATABASE_ID','STEP8_BROKER_SERVER_ID','STEP8_QUERY_PROFILE','STEP8_PROVIDER_BIND','STEP8_PROVIDER_CLIENT')) {
        $taskFixtureText = $taskFixtureText -replace "(?m)^$taskKey='[^']*'\r?\n?", ''
    }
    $taskFixtureText += "`nSTEP8_BROKER_CREDENTIALS_DIR='$($taskBrokerFixture.Replace('\','/'))'`nSTEP8_BROKER_URL=''`nSTEP8_BROKER_DATABASE_ID=''`nSTEP8_BROKER_SERVER_ID=''`n"
    $taskFixtureText += "STEP8_QUERY_PROFILE=''`nSTEP8_PROVIDER_BIND='127.0.0.1'`nSTEP8_PROVIDER_CLIENT='127.0.0.1'`n"
    if ($taskFixtureText -notmatch "(?m)^STEP8_API_IMAGE='([^']*)'") { throw 'Fixture API image declaration missing.' }
    $taskFixtureImage = $Matches[1]
    $taskFixtureImageId = & rtk proxy docker image inspect --format '{{.Id}}' $taskFixtureImage 2>$null
    if ($LASTEXITCODE -or ($taskFixtureImageId -join '').Trim() -notmatch '^sha256:[0-9a-f]{64}$') { throw 'Fixture requires an existing local API image; no pull allowed.' }
    $taskFixtureImageId = ($taskFixtureImageId -join '').Trim()
    $taskFixtureText = $taskFixtureText -replace "(?m)^STEP8_API_IMAGE_ID='[^']*'\r?\n?", ''
    $taskFixtureText += "`nSTEP8_API_IMAGE_ID='$taskFixtureImageId'`n"
    [IO.File]::WriteAllText($taskFixtureEnv,$taskFixtureText,[Text.UTF8Encoding]::new($false))
    # Old source-only fixtures predate image verification; add the accepted public identity only to this disposable fixture.
    if (!(Select-String -LiteralPath $taskFixtureEnv -Pattern '^STEP8_API_IMAGE_ID=')) {
        Add-Content -LiteralPath $taskFixtureEnv -Value "STEP8_API_IMAGE_ID='sha256:d854da5ecb3d9e26b110723ffc466e3568b6b8b1ed765fc49265f066c43c8d2a'"
    }
    & "$PSScriptRoot/check-step8-config.ps1" -EnvFile $taskFixtureEnv -ComposeFile "$taskRoot/docker-compose.kag.yml"
    & "$PSScriptRoot/check-step8-config.ps1" -EnvFile $taskFixtureEnv -ComposeFile "$taskRoot/docker-compose.step8.kag.yml"
    & "$PSScriptRoot/check-config.ps1" -Docker $Docker -Stack All -WebAppEnvFile "$taskTempRoot/.env" -KagEnvFile $taskFixtureEnv
    $taskComposeText = [IO.File]::ReadAllText("$taskRoot/docker-compose.kag.yml")
    $taskGuardCases = @(
        @('db-network','networks: [readbus]','networks: [private]','Exact private/readbus/ingress service network memberships required.'),
        @('java-bind','--server.address=127.0.0.1','--server.address=0.0.0.0','OpenSPG Java must use the fixed supervisor and loopback-only HTTP bind.'),
        @('broker-mount','target: /run/broker-credentials','target: /run/not-approved','Separate exact read-only broker mounts required.')
        @('ledger-mount','target: /provider-state/attempts.json','target: /provider-state/other','Unexpected writable/host-control API mount.'),
        @('gateway-public','KAG_PROVIDER_BIND: ${STEP8_PROVIDER_BIND:-127.0.0.1}','KAG_PROVIDER_BIND: 0.0.0.0','Exact private provider bind/client IPv4 required.')
    )
    foreach ($taskCase in $taskGuardCases) {
        $taskRejectedCompose = Join-Path $taskTempRoot ($taskCase[0]+'.yml')
        [IO.File]::WriteAllText($taskRejectedCompose,$taskComposeText.Replace($taskCase[1],$taskCase[2]),[Text.UTF8Encoding]::new($false))
        $taskRejected = $false
        try { & "$PSScriptRoot/check-step8-config.ps1" -EnvFile $taskFixtureEnv -ComposeFile $taskRejectedCompose }
        catch { $taskRejected = $_.Exception.Message -eq $taskCase[3] }
        Assert-Task $taskRejected 'Network, Java bind and broker mount mutations must fail closed.'
    }
    $taskRejectedEnv = Join-Path $taskTempRoot 'unverified-api.env'
    $taskRejectedText = [IO.File]::ReadAllText($taskFixtureEnv) -replace "(?m)^STEP8_API_IMAGE_ID='[^']*'", ("STEP8_API_IMAGE_ID='sha256:"+('1'*64)+"'")
    [IO.File]::WriteAllText($taskRejectedEnv,$taskRejectedText,[Text.UTF8Encoding]::new($false))
    $taskRejected = $false
    try { & "$PSScriptRoot/check-step8-config.ps1" -EnvFile $taskRejectedEnv -ComposeFile "$taskRoot/docker-compose.kag.yml" }
    catch { $taskRejected = $_.Exception.Message -eq 'API image must use a distinct Step8 identity and verified cache declaration.' }
    Assert-Task $taskRejected 'Unverified API image identity must fail closed.'
    $taskBrokerRejectedEnv = Join-Path $taskTempRoot 'broker-with-reader.env'
    $taskBrokerRejectedText = [IO.File]::ReadAllText($taskFixtureEnv)
    $taskBrokerRejectedValues = @{
        STEP8_DATABASE='vietroadtraffic'; STEP8_READ_ONLY_DATABASES='vietroadtraffic'
        STEP8_NEO4J_STORAGE_REVISION='-fresh-broker-test'; STEP8_READER_USERNAME='reader-fixture'
        STEP8_BROKER_URL='http://openspg-server:8899'
        STEP8_BROKER_DATABASE_ID='fixture-database'; STEP8_BROKER_SERVER_ID='fixture-server'
    }
    foreach ($taskKey in $taskBrokerRejectedValues.Keys) {
        $taskBrokerRejectedText = $taskBrokerRejectedText -replace "(?m)^$taskKey='[^']*'\r?\n?", ''
        $taskBrokerRejectedText += "`n$taskKey='$($taskBrokerRejectedValues[$taskKey])'`n"
    }
    [IO.File]::WriteAllText($taskBrokerRejectedEnv,$taskBrokerRejectedText,[Text.UTF8Encoding]::new($false))
    $taskRejected = $false
    try { & "$PSScriptRoot/check-step8-config.ps1" -EnvFile $taskBrokerRejectedEnv -ComposeFile "$taskRoot/docker-compose.kag.yml" }
    catch { $taskRejected = $_.Exception.Message -eq 'API database credentials denied with broker.' }
    Assert-Task $taskRejected 'Broker routing must reject direct API database credentials.'
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
