param(
    [Parameter(Mandatory = $true)][string]$Email,
    [Parameter(Mandatory = $true)][string]$FullName,
    [string]$ProjectId = "aikol-booking-system",
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"
if ($Email -notmatch '^[^@\s]+@iium\.edu\.my$') {
    throw "Use the administrator's IIUM email address."
}

$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$python = Join-Path $repo '.venv\Scripts\python.exe'
$manage = Join-Path $repo 'aikol_booking\manage.py'
$gcloudCommand = Get-Command gcloud.cmd -ErrorAction SilentlyContinue
$gcloud = if ($gcloudCommand) { $gcloudCommand.Source } else {
    Join-Path $env:LOCALAPPDATA 'Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd'
}
if (-not (Test-Path -LiteralPath $gcloud)) { throw "Google Cloud CLI not found." }
if (-not (Test-Path -LiteralPath $python)) { throw "Project virtual environment not found." }

$secretVariables = @{
    DJANGO_SECRET_KEY = 'django-secret-key'
    DJANGO_CREDENTIAL_ENCRYPTION_KEY = 'credential-encryption-key'
    DATABASE_URL = 'database-url'
    R2_ACCESS_KEY_ID = 'r2-access-key-id'
    R2_SECRET_ACCESS_KEY = 'r2-secret-access-key'
    R2_ENDPOINT_URL = 'r2-endpoint-url'
}
$environmentNames = @($secretVariables.Keys) + @(
    'DJANGO_SETTINGS_MODULE', 'DJANGO_ALLOWED_HOSTS', 'R2_BUCKET_NAME',
    'R2_BACKUP_BUCKET_NAME', 'AIKOL_BOOTSTRAP_EMAIL', 'PSYCOPG_IMPL'
)
$previous = @{}
foreach ($name in $environmentNames) {
    $previous[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}

try {
    foreach ($name in $secretVariables.Keys) {
        $value = & $gcloud secrets versions access latest `
            --secret $secretVariables[$name] --project $ProjectId
        if ($LASTEXITCODE -ne 0 -or -not $value) {
            throw "Could not load required production secret $($secretVariables[$name])."
        }
        [Environment]::SetEnvironmentVariable($name, $value, 'Process')
    }
    # Neon's URL requests channel binding, but the Windows libpq bundled with
    # the local psycopg binary does not recognize that connection option. TLS
    # remains mandatory in production settings; only this local option is removed.
    $env:DATABASE_URL = $env:DATABASE_URL -replace '(?i)([?&])channel_binding=[^&]*&', '$1'
    $env:DATABASE_URL = $env:DATABASE_URL -replace '(?i)[?&]channel_binding=[^&]*$', ''
    $env:DJANGO_SETTINGS_MODULE = 'config.settings.production'
    $env:DJANGO_ALLOWED_HOSTS = 'aikol-booking-qn23bk3fqa-as.a.run.app'
    $env:R2_BUCKET_NAME = 'aikol-booking-media'
    $env:R2_BACKUP_BUCKET_NAME = 'aikol-booking-backups'
    $env:AIKOL_BOOTSTRAP_EMAIL = $Email
    # The local Windows binary implementation exits with heap corruption when
    # connecting to Neon. The pure-Python wrapper uses the installed libpq.
    $env:PSYCOPG_IMPL = 'python'

    Push-Location (Join-Path $repo 'aikol_booking')
    try {
        $checkDatabase = 'import sys; from django.db import connection; connection.ensure_connection(); print("Production database connection works.")'
        $checkOutput = & $python $manage shell -c $checkDatabase 2>&1
        $checkExitCode = $LASTEXITCODE
        Write-Host "Database check exit code: $checkExitCode; output lines: $(@($checkOutput).Count)"
        foreach ($line in $checkOutput) {
            Write-Host (([string]$line) -replace 'postgres(?:ql)?://[^\s]+', '[database URL redacted]')
        }
        if ($checkExitCode -eq -1073740940) {
            throw 'The local Windows PostgreSQL client crashed. Do not retry locally; use a cloud-side administrator bootstrap.'
        }
        if ($checkExitCode -ne 0) { throw 'Production database connection check failed.' }
        if ($CheckOnly) {
            Write-Host 'Production database connection works. No account was changed.'
            return
        }
        & $python $manage createsuperuser --email $Email --full_name $FullName
        if ($LASTEXITCODE -ne 0) { throw 'Administrator creation failed.' }

        $markStaff = 'import os; from django.contrib.auth import get_user_model; from django.utils import timezone; u = get_user_model().objects.get(email=os.environ["AIKOL_BOOTSTRAP_EMAIL"]); u.affiliation = "STAFF"; u.email_verified = True; u.email_verified_at = timezone.now(); u.save(update_fields=["affiliation", "email_verified", "email_verified_at"])'
        & $python $manage shell -c $markStaff
        if ($LASTEXITCODE -ne 0) { throw 'Account exists, but staff affiliation needs review.' }
    }
    finally { Pop-Location }
    Write-Host 'Administrator created. Sign in and change the password after the first login.'
}
finally {
    foreach ($name in $environmentNames) {
        [Environment]::SetEnvironmentVariable($name, $previous[$name], 'Process')
    }
}
