# Run the restore_database command as a one-off Cloud Run job.
#
#   .\deploy\cloud-run\restore-database.ps1 -Check                  # open the newest backup, change nothing
#   .\deploy\cloud-run\restore-database.ps1 -TargetSecret database-url-supabase   # load it
#
# The job uses the image already built by deploy.ps1 and reads the target
# database from the Secret Manager secret named by -TargetSecret, so the
# connection string is never typed here.
param(
    [string]$ProjectId = "aikol-booking-system",
    [string]$Region = "asia-southeast1",
    [string]$TargetSecret = "database-url",
    [string]$BackupBucket = "aikol-booking-backups",
    [string]$MediaBucket = "aikol-booking-media",
    [string]$BackupKey = "",
    [switch]$Check
)

$ErrorActionPreference = "Continue"
$image = "$Region-docker.pkg.dev/$ProjectId/aikol-booking/web:latest"
$runtime = "aikol-runtime@$ProjectId.iam.gserviceaccount.com"
$secrets = "DJANGO_SECRET_KEY=django-secret-key:latest,DJANGO_CREDENTIAL_ENCRYPTION_KEY=credential-encryption-key:latest,DATABASE_URL=${TargetSecret}:latest,R2_ACCESS_KEY_ID=r2-access-key-id:latest,R2_SECRET_ACCESS_KEY=r2-secret-access-key:latest,R2_ENDPOINT_URL=r2-endpoint-url:latest"
$environment = "DJANGO_SETTINGS_MODULE=config.settings.production,R2_BUCKET_NAME=$MediaBucket,R2_BACKUP_BUCKET_NAME=$BackupBucket,DJANGO_ALLOWED_HOSTS=localhost"

$command = "python manage.py restore_database"
if ($Check) { $command += " --check" }
if ($BackupKey) { $command += " --key $BackupKey" }

gcloud run jobs deploy aikol-restore --project $ProjectId --image $image --region $Region --service-account $runtime --cpu 1 --memory 1Gi --max-retries 0 --task-timeout 15m --set-env-vars $environment --set-secrets $secrets --command sh --args "-c,$command"
if ($LASTEXITCODE -ne 0) { throw "Could not define the restore job." }
gcloud run jobs execute aikol-restore --project $ProjectId --region $Region --wait
$exit = $LASTEXITCODE
Write-Host ""
Write-Host "Job output (last lines):"
gcloud logging read "resource.type=cloud_run_job AND resource.labels.job_name=aikol-restore" --project $ProjectId --limit 40 --freshness 10m --order desc --format "value(textPayload)" | Select-Object -First 40
if ($exit -ne 0) { throw "The restore job failed." }
