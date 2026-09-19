param(
    [string]$Token,
    [string]$ProjectId = "aikol-booking-system"
)

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$python = Join-Path $repo '.venv\Scripts\python.exe'
$decryptHelper = Join-Path $PSScriptRoot 'decrypt_handoff.py'
$gcloud = Join-Path $env:LOCALAPPDATA 'Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd'
if (-not (Test-Path -LiteralPath $python)) { throw "Project Python environment not found." }
if (-not (Test-Path -LiteralPath $decryptHelper)) { throw "Password handoff helper not found." }
if (-not (Test-Path -LiteralPath $gcloud)) { throw "Google Cloud CLI not found." }

if (-not $Token) {
    $logLines = & $gcloud logging read `
        'resource.type=cloud_run_job AND resource.labels.job_name=aikol-bootstrap-admin' `
        --project $ProjectId --limit 30 --format='value(textPayload)'
    if ($LASTEXITCODE -ne 0) { throw "Could not read the bootstrap job log." }
    $tokens = @($logLines | ForEach-Object {
        if ([string]$_ -match '^AIKOL_ADMIN_HANDOFF_TOKEN=(\S+)$') { $Matches[1] }
    })
    if ($tokens.Count -ne 1) { throw "Expected exactly one encrypted handoff token; found $($tokens.Count)." }
    $Token = $tokens[0]
}

$key = & $gcloud secrets versions access latest --secret credential-encryption-key --project $ProjectId
if ($LASTEXITCODE -ne 0 -or -not $key) { throw "Could not retrieve the encryption key." }

$previousKey = [Environment]::GetEnvironmentVariable('AIKOL_HANDOFF_KEY', 'Process')
$previousToken = [Environment]::GetEnvironmentVariable('AIKOL_HANDOFF_TOKEN', 'Process')
try {
    $env:AIKOL_HANDOFF_KEY = $key
    $env:AIKOL_HANDOFF_TOKEN = $Token
    & $python $decryptHelper
    if ($LASTEXITCODE -ne 0) { throw "Could not decrypt the handoff token." }
}
finally {
    [Environment]::SetEnvironmentVariable('AIKOL_HANDOFF_KEY', $previousKey, 'Process')
    [Environment]::SetEnvironmentVariable('AIKOL_HANDOFF_TOKEN', $previousToken, 'Process')
}
