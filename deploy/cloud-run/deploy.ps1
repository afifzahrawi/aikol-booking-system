param(
    [Parameter(Mandatory = $true)][string]$ProjectId,
    [string]$Region = "asia-southeast1",
    [string]$Service = "aikol-booking",
    [string]$MaintenanceService = "aikol-maintenance",
    [string]$Repository = "aikol-booking",
    [string]$RuntimeServiceAccount = "aikol-runtime",
    [string]$MediaBucket = "aikol-booking-media",
    [string]$BackupBucket = "aikol-booking-backups"
)

$ErrorActionPreference = "Stop"
$runtimeAccount = "$RuntimeServiceAccount@$ProjectId.iam.gserviceaccount.com"
$schedulerAccount = "aikol-scheduler@$ProjectId.iam.gserviceaccount.com"
$image = "$Region-docker.pkg.dev/$ProjectId/$Repository/web:latest"

gcloud config set project $ProjectId
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com cloudscheduler.googleapis.com secretmanager.googleapis.com

gcloud artifacts repositories describe $Repository --location $Region 2>$null
if ($LASTEXITCODE -ne 0) {
    gcloud artifacts repositories create $Repository --repository-format docker --location $Region --description "AIKOL Booking images"
}

gcloud iam service-accounts describe $runtimeAccount 2>$null
if ($LASTEXITCODE -ne 0) {
    gcloud iam service-accounts create $RuntimeServiceAccount --display-name "AIKOL Booking runtime"
}

gcloud iam service-accounts describe $schedulerAccount 2>$null
if ($LASTEXITCODE -ne 0) {
    gcloud iam service-accounts create aikol-scheduler --display-name "AIKOL Scheduler invoker"
}

gcloud builds submit --tag $image .

$secretNames = @(
    "django-secret-key", "credential-encryption-key", "database-url",
    "r2-access-key-id", "r2-secret-access-key", "r2-endpoint-url"
)
foreach ($name in $secretNames) {
    gcloud secrets describe $name 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Create Secret Manager secret '$name' before deploying. See managed-cloud-deployment.md."
    }
    gcloud secrets add-iam-policy-binding $name --member "serviceAccount:$runtimeAccount" --role roles/secretmanager.secretAccessor | Out-Null
}

$secretMap = "DJANGO_SECRET_KEY=django-secret-key:latest,DJANGO_CREDENTIAL_ENCRYPTION_KEY=credential-encryption-key:latest,DATABASE_URL=database-url:latest,R2_ACCESS_KEY_ID=r2-access-key-id:latest,R2_SECRET_ACCESS_KEY=r2-secret-access-key:latest,R2_ENDPOINT_URL=r2-endpoint-url:latest"
$baseEnvironment = "DJANGO_SETTINGS_MODULE=config.settings.production,R2_BUCKET_NAME=$MediaBucket,R2_BACKUP_BUCKET_NAME=$BackupBucket,WEB_CONCURRENCY=1,GUNICORN_THREADS=4"
$bootstrapEnvironment = "$baseEnvironment,DJANGO_ALLOWED_HOSTS=localhost"

function Invoke-OperationalJob([string]$Name, [string]$Environment, [string]$Command) {
    gcloud run jobs deploy $Name --image $image --region $Region --service-account $runtimeAccount --cpu 1 --memory 512Mi --max-retries 0 --task-timeout 10m --set-env-vars $Environment --set-secrets $secretMap --command sh --args "-c,$Command"
    gcloud run jobs execute $Name --region $Region --wait
    if ($LASTEXITCODE -ne 0) { throw "The $Name job failed. Deployment is not complete." }
}

# An existing deployment is backed up and migrated BEFORE the new image serves a
# request. Migrations are additive, so the running code keeps working on the new
# schema; the reverse is not true, and a new release that expects a table the
# database does not have yet answers every request with an error until the
# migration lands.
$existingUrl = gcloud run services describe $Service --region $Region --format "value(status.url)" 2>$null
if ($LASTEXITCODE -eq 0 -and $existingUrl) {
    $publicHost = ([Uri]$existingUrl).Host
    $releaseEnvironment = "$baseEnvironment,DJANGO_ALLOWED_HOSTS=$publicHost"
    Invoke-OperationalJob "aikol-backup" $releaseEnvironment "python manage.py backup_database"
    Invoke-OperationalJob "aikol-migrate" $releaseEnvironment "python manage.py migrate --noinput && python manage.py createcachetable"
}

gcloud run deploy $Service --image $image --region $Region --platform managed --allow-unauthenticated --service-account $runtimeAccount --cpu 1 --memory 512Mi --concurrency 20 --min 0 --max 1 --timeout 30 --execution-environment gen2 --no-cpu-boost --set-env-vars $bootstrapEnvironment --set-secrets $secretMap
$publicUrl = gcloud run services describe $Service --region $Region --format "value(status.url)"
$publicHost = ([Uri]$publicUrl).Host
$environment = "$baseEnvironment,DJANGO_ALLOWED_HOSTS=$publicHost"
gcloud run services update $Service --region $Region --update-env-vars "DJANGO_ALLOWED_HOSTS=$publicHost" | Out-Null

$maintenanceEnvironment = "$environment,DJANGO_MAINTENANCE_SERVICE=1"
gcloud run deploy $MaintenanceService --image $image --region $Region --platform managed --no-allow-unauthenticated --service-account $runtimeAccount --cpu 1 --memory 512Mi --concurrency 1 --min 0 --max 1 --timeout 600 --execution-environment gen2 --no-cpu-boost --set-env-vars $maintenanceEnvironment --set-secrets $secretMap
$maintenanceUrl = gcloud run services describe $MaintenanceService --region $Region --format "value(status.url)"
$maintenanceHost = ([Uri]$maintenanceUrl).Host
gcloud run services update $MaintenanceService --region $Region --update-env-vars "^^^^@^^^^DJANGO_ALLOWED_HOSTS=$publicHost,$maintenanceHost" | Out-Null
gcloud run services add-iam-policy-binding $MaintenanceService --region $Region --member "serviceAccount:$schedulerAccount" --role roles/run.invoker | Out-Null

if (-not $existingUrl) {
    # First deployment: there was nothing to back up and no host to migrate under
    # until the service existed.
    Invoke-OperationalJob "aikol-migrate" $environment "python manage.py migrate --noinput && python manage.py createcachetable"
}
Write-Host "Deployment complete. Maintenance origin: $maintenanceUrl"
Write-Host "Public origin: $publicUrl"
Write-Host "Create the three scheduler triggers using the documented commands."
