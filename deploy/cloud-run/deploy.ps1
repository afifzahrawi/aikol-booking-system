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

# Windows PowerShell 5.1 turns anything a native command writes to stderr into
# an error record, and under $ErrorActionPreference = "Stop" that record is
# fatal. gcloud writes routine notices to stderr ("Encryption: Google-managed
# key"), so "Stop" halts the deployment on information. Success is judged by
# exit code instead, through Invoke-Step, and the preference stays "Continue".
$ErrorActionPreference = "Continue"
$runtimeAccount = "$RuntimeServiceAccount@$ProjectId.iam.gserviceaccount.com"
$schedulerAccount = "aikol-scheduler@$ProjectId.iam.gserviceaccount.com"
$image = "$Region-docker.pkg.dev/$ProjectId/$Repository/web:latest"

# The parameter names are deliberately unusual. A script block passed in is
# evaluated inside this function's scope, so a plain $Name or $Command in the
# caller's block would resolve to the parameter here, not to the caller's
# variable — which is how a secret was once named after the step label.
function Invoke-Step([string]$StepLabel, [scriptblock]$StepBlock) {
    & $StepBlock
    if ($LASTEXITCODE -ne 0) { throw "$StepLabel failed (exit $LASTEXITCODE). Deployment is not complete." }
}

# True when the resource exists. Output and stderr are swallowed; only the exit
# code is read.
function Test-Resource([scriptblock]$ProbeBlock) {
    $null = & $ProbeBlock 2>&1
    return ($LASTEXITCODE -eq 0)
}

Invoke-Step "Selecting the project" { gcloud config set project $ProjectId }
Invoke-Step "Enabling APIs" { gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com cloudscheduler.googleapis.com secretmanager.googleapis.com }

if (-not (Test-Resource { gcloud artifacts repositories describe $Repository --location $Region })) {
    Invoke-Step "Creating the image repository" { gcloud artifacts repositories create $Repository --repository-format docker --location $Region --description "AIKOL Booking images" }
}
if (-not (Test-Resource { gcloud iam service-accounts describe $runtimeAccount })) {
    Invoke-Step "Creating the runtime service account" { gcloud iam service-accounts create $RuntimeServiceAccount --display-name "AIKOL Booking runtime" }
}
if (-not (Test-Resource { gcloud iam service-accounts describe $schedulerAccount })) {
    Invoke-Step "Creating the scheduler service account" { gcloud iam service-accounts create aikol-scheduler --display-name "AIKOL Scheduler invoker" }
}

Invoke-Step "Building the image" { gcloud builds submit --tag $image . }

$secretNames = @(
    "django-secret-key", "credential-encryption-key", "database-url",
    "r2-access-key-id", "r2-secret-access-key", "r2-endpoint-url"
)
foreach ($secretName in $secretNames) {
    if (-not (Test-Resource { gcloud secrets describe $secretName })) {
        throw "Create Secret Manager secret '$secretName' before deploying. See managed-cloud-deployment.md."
    }
    Invoke-Step "Granting access to secret $secretName" { gcloud secrets add-iam-policy-binding $secretName --member "serviceAccount:$runtimeAccount" --role roles/secretmanager.secretAccessor | Out-Null }
}

$secretMap = "DJANGO_SECRET_KEY=django-secret-key:latest,DJANGO_CREDENTIAL_ENCRYPTION_KEY=credential-encryption-key:latest,DATABASE_URL=database-url:latest,R2_ACCESS_KEY_ID=r2-access-key-id:latest,R2_SECRET_ACCESS_KEY=r2-secret-access-key:latest,R2_ENDPOINT_URL=r2-endpoint-url:latest"
$baseEnvironment = "DJANGO_SETTINGS_MODULE=config.settings.production,R2_BUCKET_NAME=$MediaBucket,R2_BACKUP_BUCKET_NAME=$BackupBucket,WEB_CONCURRENCY=1,GUNICORN_THREADS=4"
$bootstrapEnvironment = "$baseEnvironment,DJANGO_ALLOWED_HOSTS=localhost"

function Invoke-OperationalJob([string]$JobName, [string]$JobEnvironment, [string]$JobCommand) {
    Invoke-Step "Defining the $JobName job" { gcloud run jobs deploy $JobName --image $image --region $Region --service-account $runtimeAccount --cpu 1 --memory 512Mi --max-retries 0 --task-timeout 10m --set-env-vars $JobEnvironment --set-secrets $secretMap --command sh --args "-c,$JobCommand" }
    Invoke-Step "Running the $JobName job" { gcloud run jobs execute $JobName --region $Region --wait }
}

# An existing deployment is backed up and migrated BEFORE the new image serves a
# request. Migrations are additive, so the running code keeps working on the new
# schema; the reverse is not true, and a new release that expects a table the
# database does not have yet answers every request with an error until the
# migration lands.
$existingUrl = $null
if (Test-Resource { gcloud run services describe $Service --region $Region }) {
    $existingUrl = (gcloud run services describe $Service --region $Region --format "value(status.url)" 2>&1 | Where-Object { $_ -is [string] } | Select-Object -Last 1)
}
if ($existingUrl) {
    $publicHost = ([Uri]$existingUrl).Host
    $releaseEnvironment = "$baseEnvironment,DJANGO_ALLOWED_HOSTS=$publicHost"
    Invoke-OperationalJob "aikol-backup" $releaseEnvironment "python manage.py backup_database"
    Invoke-OperationalJob "aikol-migrate" $releaseEnvironment "python manage.py migrate --noinput && python manage.py createcachetable"
}

Invoke-Step "Deploying the public service" { gcloud run deploy $Service --image $image --region $Region --platform managed --allow-unauthenticated --service-account $runtimeAccount --cpu 1 --memory 512Mi --concurrency 20 --min 0 --max 1 --timeout 30 --execution-environment gen2 --no-cpu-boost --set-env-vars $bootstrapEnvironment --set-secrets $secretMap }
$publicUrl = (gcloud run services describe $Service --region $Region --format "value(status.url)" 2>&1 | Where-Object { $_ -is [string] } | Select-Object -Last 1)
$publicHost = ([Uri]$publicUrl).Host
$environment = "$baseEnvironment,DJANGO_ALLOWED_HOSTS=$publicHost"
Invoke-Step "Pinning the public hostname" { gcloud run services update $Service --region $Region --update-env-vars "DJANGO_ALLOWED_HOSTS=$publicHost" | Out-Null }

$maintenanceEnvironment = "$environment,DJANGO_MAINTENANCE_SERVICE=1"
Invoke-Step "Deploying the maintenance service" { gcloud run deploy $MaintenanceService --image $image --region $Region --platform managed --no-allow-unauthenticated --service-account $runtimeAccount --cpu 1 --memory 512Mi --concurrency 1 --min 0 --max 1 --timeout 600 --execution-environment gen2 --no-cpu-boost --set-env-vars $maintenanceEnvironment --set-secrets $secretMap }
$maintenanceUrl = (gcloud run services describe $MaintenanceService --region $Region --format "value(status.url)" 2>&1 | Where-Object { $_ -is [string] } | Select-Object -Last 1)
$maintenanceHost = ([Uri]$maintenanceUrl).Host
Invoke-Step "Pinning the maintenance hostnames" { gcloud run services update $MaintenanceService --region $Region --update-env-vars "^^^^@^^^^DJANGO_ALLOWED_HOSTS=$publicHost,$maintenanceHost" | Out-Null }
Invoke-Step "Allowing the scheduler to invoke maintenance" { gcloud run services add-iam-policy-binding $MaintenanceService --region $Region --member "serviceAccount:$schedulerAccount" --role roles/run.invoker | Out-Null }

if (-not $existingUrl) {
    # First deployment: there was nothing to back up and no host to migrate under
    # until the service existed.
    Invoke-OperationalJob "aikol-migrate" $environment "python manage.py migrate --noinput && python manage.py createcachetable"
}
Write-Host "Deployment complete. Maintenance origin: $maintenanceUrl"
Write-Host "Public origin: $publicUrl"
Write-Host "Create the three scheduler triggers using the documented commands."
