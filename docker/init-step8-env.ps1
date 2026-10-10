param(
    [Parameter(Mandatory=$true)][string]$OutputDirectory,
    [Parameter(Mandatory=$true)][string]$WheelDirectory,
    [ValidatePattern('^kag-s8-[a-z0-9][a-z0-9-]*$')][string]$ProjectName = 'kag-s8-20261009',
    [ValidateRange(1024,65535)][int]$ApiPort = 38000,
    [ValidateRange(1024,65535)][int]$OpenSpgPort = 38887
)
$ErrorActionPreference = 'Stop'
$taskRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$taskOutput = [IO.Path]::GetFullPath($OutputDirectory)
$taskWheels = [IO.Path]::GetFullPath($WheelDirectory)
if ($taskOutput -eq $taskRoot -or $taskOutput.StartsWith($taskRoot+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Step8 secrets must stay outside the source repository.' }
if (Test-Path -LiteralPath $taskOutput) { throw 'Output directory already exists; no overwrite or credential rotation is allowed.' }
if ($ApiPort -eq $OpenSpgPort) { throw 'API and OpenSPG ports must differ.' }
for ($taskAncestor = [IO.DirectoryInfo]::new($taskOutput).Parent; $null -ne $taskAncestor; $taskAncestor = $taskAncestor.Parent) {
    if (Test-Path -LiteralPath (Join-Path $taskAncestor.FullName '.git')) { throw 'Do not generate secrets inside another repository.' }
}
$taskWheel = Join-Path $taskWheels 'fastapi-0.115.12-py3-none-any.whl'
if (!(Test-Path -LiteralPath $taskWheel -PathType Leaf)) { throw 'Verified offline FastAPI wheel missing.' }
$taskHash = [Security.Cryptography.SHA256]::Create()
$taskStream = [IO.File]::OpenRead($taskWheel)
try { $taskDigest = [BitConverter]::ToString($taskHash.ComputeHash($taskStream)).Replace('-','').ToLowerInvariant() }
finally { $taskStream.Dispose(); $taskHash.Dispose() }
if ($taskDigest -ne 'e94613d6c05e27be7ffebdd6ea5f388112e5e430c8f7d6494a9d1d88d43e814d') { throw 'Offline FastAPI wheel hash mismatch.' }
$taskVendor = Join-Path $taskRoot 'vendor/KAG'
$taskPin = & rtk proxy git -C $taskVendor rev-parse HEAD
if ($LASTEXITCODE -or ($taskPin -join '').Trim() -ne 'fdab15b3929d2ee40dfcdd388f90233096a6afc9') { throw 'Canonical vendor pin mismatch.' }
$taskDirty = & rtk proxy git -C $taskVendor status --porcelain --untracked-files=all
if ($LASTEXITCODE -or $taskDirty) { throw 'Vendor must remain unchanged.' }
$taskCommon = & rtk proxy git -C $taskVendor rev-parse --git-common-dir
if ($LASTEXITCODE) { throw 'Cannot locate vendor Git object store.' }
$taskCommon = ($taskCommon -join '').Trim()
if (![IO.Path]::IsPathRooted($taskCommon)) { $taskCommon = Join-Path $taskVendor $taskCommon }
$taskObjects = [IO.Path]::GetFullPath((Join-Path $taskCommon 'objects'))
if (!(Test-Path -LiteralPath $taskObjects -PathType Container)) { throw 'Canonical Git objects missing.' }
$taskWindows = $env:OS -eq 'Windows_NT'
$taskUid = 10001; $taskGid = 10001
if (!$taskWindows) {
    $taskUid = & rtk proxy id -u
    if ($LASTEXITCODE -or [int]$taskUid -le 0) { throw 'Generate Linux secrets as a non-root operator.' }
    $taskGid = & rtk proxy id -g
    if ($LASTEXITCODE -or [int]$taskGid -le 0) { throw 'Non-root group required.' }
}
function Protect-TaskDirectory([string]$Path) {
    if ($taskWindows) {
        $taskAcl = [Security.AccessControl.DirectorySecurity]::new()
        $taskOwner = [Security.Principal.WindowsIdentity]::GetCurrent().User
        $taskAcl.SetOwner($taskOwner)
        $taskAcl.SetAccessRuleProtection($true,$false)
        $taskInherit = [Security.AccessControl.InheritanceFlags]'ContainerInherit,ObjectInherit'
        $taskAcl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new($taskOwner,'FullControl',$taskInherit,'None','Allow'))
        $taskAcl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new([Security.Principal.SecurityIdentifier]::new('S-1-5-18'),'ReadAndExecute',$taskInherit,'None','Allow'))
        $taskDirectory = [IO.DirectoryInfo]::new($Path)
        if ($taskDirectory.PSObject.Methods['SetAccessControl']) { $taskDirectory.SetAccessControl($taskAcl) }
        else { [IO.FileSystemAclExtensions]::SetAccessControl($taskDirectory,$taskAcl) }
    } else {
        & rtk proxy chmod 700 -- $Path
        if ($LASTEXITCODE) { throw 'Cannot restrict secret directory permissions.' }
    }
}
function New-TaskSecret {
    $taskBytes = [byte[]]::new(32)
    $taskRng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $taskRng.GetBytes($taskBytes) } finally { $taskRng.Dispose() }
    return [BitConverter]::ToString($taskBytes).Replace('-','').ToLowerInvariant()
}
function Write-TaskNewFile([string]$Path,[string]$Value) {
    $taskFile = [IO.File]::Open($Path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
    try { $taskBytes = [Text.UTF8Encoding]::new($false).GetBytes($Value); $taskFile.Write($taskBytes,0,$taskBytes.Length) }
    finally { $taskFile.Dispose() }
    if (!$taskWindows) {
        & rtk proxy chmod 600 -- $Path
        if ($LASTEXITCODE) { throw 'Cannot restrict secret file permissions.' }
    }
}
$taskRelease = Join-Path $taskOutput 'release'
$taskCredentials = Join-Path $taskOutput 'api-credentials'
$taskQuery = Join-Path $taskOutput 'query.token'
$taskInspect = Join-Path $taskOutput 'inspect.token'
$taskValues = [ordered]@{
    STEP8_KAG_PROJECT=$ProjectName; STEP8_API_PORT=[string]$ApiPort; STEP8_OPENSPG_PORT=[string]$OpenSpgPort
    STEP8_API_IMAGE="${ProjectName}-api:source"; STEP8_RUNTIME_IMAGE='vietroadtraffic-kag-runtime:d0.2'
    STEP8_API_IMAGE_ID='sha256:d854da5ecb3d9e26b110723ffc466e3568b6b8b1ed765fc49265f066c43c8d2a'
    STEP8_RUNTIME_IMAGE_ID='sha256:25190ba8f51e8d158db0910858e9de3de1e1324d29d8b236d4d120268fa7bf33'
    STEP8_MINIO_IMAGE='kag-openspg-minio:latest'
    STEP8_MINIO_IMAGE_ID='sha256:5e65d87b41ed46cbdb6edcd5f0bc92ab947f0f9873d609b41e2c071f6028f532'
    STEP8_MYSQL_PASSWORD=(New-TaskSecret); STEP8_NEO4J_PASSWORD=(New-TaskSecret); STEP8_MINIO_PASSWORD=(New-TaskSecret)
    STEP8_QUERY_SECRET_FILE=$taskQuery; STEP8_INSPECT_SECRET_FILE=$taskInspect
    STEP8_RELEASE_DIR=$taskRelease; STEP8_RELEASE_ID=''
    STEP8_API_CREDENTIALS_DIR=$taskCredentials; STEP8_READER_USERNAME=''
    STEP8_EMBEDDING_URL=''; STEP8_EMBEDDING_MODEL=''; STEP8_CHAT_URL=''; STEP8_CHAT_MODEL=''
    STEP8_HTTP_WHEELS_DIR=$taskWheels; STEP8_VENDOR_OBJECTS_DIR=$taskObjects
    STEP8_API_UID=[string]$taskUid; STEP8_API_GID=[string]$taskGid
}
$taskLines = foreach ($taskEntry in $taskValues.GetEnumerator()) {
    $taskValue = ([string]$taskEntry.Value).Replace('\','/')
    if ($taskValue.Contains("'") -or $taskValue.Contains("`r") -or $taskValue.Contains("`n")) { throw 'Path/value cannot be represented safely in dotenv.' }
    "$($taskEntry.Key)='$taskValue'"
}
[void][IO.Directory]::CreateDirectory($taskOutput)
Protect-TaskDirectory $taskOutput
foreach ($taskDirectory in @($taskRelease,$taskCredentials)) {
    [void][IO.Directory]::CreateDirectory($taskDirectory); Protect-TaskDirectory $taskDirectory
}
Write-TaskNewFile $taskQuery (New-TaskSecret)
Write-TaskNewFile $taskInspect (New-TaskSecret)
Write-TaskNewFile (Join-Path $taskOutput 'kag.env') (($taskLines -join "`n")+"`n")
Write-Output 'Created independent Step8 env/tokens; existing credentials untouched. Empty release/reader configuration: readiness DENY. No Docker operation executed.'
