# Store a PostgreSQL connection string in Secret Manager without it appearing on
# screen, in shell history or in any chat.
#
#   .\deploy\cloud-run\set-database-secret.ps1                      # a staging secret
#   .\deploy\cloud-run\set-database-secret.ps1 -SecretName database-url   # the live one
#
# The string is typed or pasted at a hidden prompt, written to a temporary file
# only long enough for gcloud to read it, and the file is removed straight away.
param(
    [string]$ProjectId = "aikol-booking-system",
    [string]$SecretName = "database-url-supabase",
    [string]$RuntimeServiceAccount = "aikol-runtime"
)

$ErrorActionPreference = "Continue"
$secure = Read-Host "Paste the connection string (hidden)" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try { $url = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr).Trim() }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }

if ($url -notmatch '^postgres(ql)?://') { throw "That is not a postgres:// connection string." }
if ($url -match '\[YOUR-PASSWORD\]|\[PASSWORD\]') { throw "The password placeholder is still in the string. Put the real password in." }
if ($url -match 'db\.[a-z0-9]+\.supabase\.co') { throw "That is the direct connection, which Cloud Run cannot reach (IPv6 only). Use the Session pooler string (host ends pooler.supabase.com)." }

$file = [IO.Path]::GetTempFileName()
try {
    [IO.File]::WriteAllText($file, $url)
    $null = gcloud secrets describe $SecretName --project $ProjectId 2>&1
    if ($LASTEXITCODE -ne 0) {
        gcloud secrets create $SecretName --project $ProjectId --replication-policy automatic --data-file $file
    } else {
        gcloud secrets versions add $SecretName --project $ProjectId --data-file $file
    }
    if ($LASTEXITCODE -ne 0) { throw "Could not store the secret." }
    gcloud secrets add-iam-policy-binding $SecretName --project $ProjectId --member "serviceAccount:$RuntimeServiceAccount@$ProjectId.iam.gserviceaccount.com" --role roles/secretmanager.secretAccessor | Out-Null
    Write-Host "Stored in secret '$SecretName'."
} finally {
    Remove-Item $file -Force -ErrorAction SilentlyContinue
    $url = $null
}
