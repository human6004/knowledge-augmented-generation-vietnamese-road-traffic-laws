param([string]$Docker = 'docker', [ValidateSet('All','WebApp','Kag')][string]$Stack = 'All')
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskPorts = @{}
$taskVolumes = @{}
$taskStacks = if ($Stack -eq 'All') { @('webapp','kag') } else { @($Stack.ToLowerInvariant()) }
foreach ($taskStack in $taskStacks) {
    $taskFile = if ($taskStack -eq 'webapp') { 'docker-compose.yml' } else { 'docker-compose.kag.yml' }
    $taskEnv = if ($taskStack -eq 'webapp') { '.env' } else { '.env.kag' }
    $taskExpected = if ($taskStack -eq 'webapp') { @('mysql','redis','minio','backend','frontend') } else { @('openspg-server','openspg-mysql','openspg-neo4j','openspg-minio') }
    $taskJson = & $Docker compose --project-directory $taskRoot --env-file "$taskRoot/$taskEnv" -f "$taskRoot/$taskFile" config --format json
    if ($LASTEXITCODE) { throw "Compose $taskStack không hợp lệ; tạo $taskEnv bằng docker/init-env.ps1 trước." }
    $taskConfig = ($taskJson -join "`n") | ConvertFrom-Json
    if ($taskConfig.name -ne $taskStack) { throw "$taskFile phải giữ project $taskStack." }
    if (Compare-Object @($taskConfig.services.PSObject.Properties.Name) $taskExpected) { throw "$taskFile phải chỉ chứa các service của $taskStack." }
    foreach ($taskService in $taskConfig.services.PSObject.Properties) {
        if ($taskService.Value.profiles) { throw "$($taskService.Name) phải chạy trực tiếp trong Compose riêng, không cần profile." }
        foreach ($taskDependency in $taskService.Value.depends_on.PSObject.Properties.Name) {
            if ($taskDependency -notin $taskExpected) { throw "$($taskService.Name) có dependency khác stack." }
        }
        foreach ($taskPort in $taskService.Value.ports) {
            if ($taskPort.host_ip -ne '127.0.0.1') { throw "Cổng $($taskService.Name) phải chỉ bind localhost." }
            if ($taskPorts.ContainsKey($taskPort.published)) { throw "Trùng cổng $($taskPort.published)." }
            $taskPorts[$taskPort.published] = $true
        }
        foreach ($taskVolume in $taskService.Value.volumes) {
            if ($taskVolume.type -ne 'volume') { throw 'Dữ liệu phải dùng named volume.' }
        }
    }
    foreach ($taskVolume in $taskConfig.volumes.PSObject.Properties) {
        if ($taskVolumes.ContainsKey($taskVolume.Value.name)) { throw 'Hai stack không được dùng chung volume dữ liệu.' }
        $taskVolumes[$taskVolume.Value.name] = $true
    }
    if ($taskStack -eq 'webapp') {
        if ($taskConfig.services.backend.environment.DB_URL -notmatch '^jdbc:mysql://mysql:3306/luatgt\?') { throw 'Backend phải kết nối MySQL của WebApp.' }
        if ($taskConfig.services.mysql.environment.MYSQL_USER -ne 'luatgt') { throw 'Backend phải dùng tài khoản luatgt, không dùng root.' }
        if ($taskConfig.volumes.'kag-data'.name -ne 'webapp_kag-data') { throw 'MySQL WebApp phải giữ volume webapp_kag-data.' }
        if ($taskConfig.services.backend.build.context -ne $taskRoot) { throw 'Backend cần build từ root để đóng gói schema chung.' }
        if ($taskConfig.services.backend.environment.KAG_BASE_URL -match ':28887|:8887') { throw 'KAG_BASE_URL phải trỏ tới adapter Python, không phải OpenSPG UI.' }
    } else {
        foreach ($taskName in $taskExpected) {
            if (@($taskConfig.services.$taskName.networks.PSObject.Properties.Name) -notcontains 'openspg') { throw "$taskName thiếu mạng openspg." }
        }
        foreach ($taskName in @('openspg-mysql-data','openspg-neo4j-data','openspg-neo4j-logs','openspg-minio-data')) {
            if ($taskConfig.volumes.$taskName.name -ne "kag_$taskName") { throw "$taskName phải có tiền tố kag_." }
        }
    }
    Write-Output "PASS: Compose $taskStack, service/dependency scope, ports, volumes and build/API configuration."
}
