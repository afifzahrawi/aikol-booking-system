# Make the live site use the database named in a staging secret.
#
#   .\deploy\cloud-run\promote-database-secret.ps1
#
# Copies the newest version of one Secret Manager secret into another as a NEW
# version, without the value ever being shown. The previous version of the
# target stays in Secret Manager, so switching back is a matter of enabling it
# again and redeploying. Services pick up the new value when a new revision
# starts; the script ends by listing the commands to force that.
param(
    [string]$ProjectId = "aikol-booking-system",
    [string]$From = "database-url-supabase",
    [string]$To = "database-url"
)

$ErrorActionPreference = "Continue"
$file = [IO.Path]::GetTempFileName()
try {
    gcloud secrets versions access latest --secret $From --project $ProjectId --out-file $file
    if ($LASTEXITCODE -ne 0) { throw "Could not read secret '$From'." }
    gcloud secrets versions add $To --project $ProjectId --data-file $file
    if ($LASTEXITCODE -ne 0) { throw "Could not write secret '$To'." }
    Write-Host "Secret '$To' now holds the value of '$From'. Its earlier versions are kept."
} finally {
    Remove-Item $file -Force -ErrorAction SilentlyContinue
}
