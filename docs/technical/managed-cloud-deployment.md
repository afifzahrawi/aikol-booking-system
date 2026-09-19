# Google Cloud Run deployment

## Selected stack

The production target is **Google Cloud Run with request-based billing**. It replaces the rejected
Oracle account path and removes VM patching, Docker-daemon maintenance and Caddy administration.

| Concern | Service | Free-allowance design |
| --- | --- | --- |
| Django | Cloud Run service | 1 vCPU, 512 MiB, concurrency 20, minimum 0, maximum 1 |
| Scheduled commands | Private request-billed Cloud Run service + Cloud Scheduler | Three authenticated schedules; no one-minute Job minimum |
| PostgreSQL | Neon Free | Pooled TLS connection URL |
| Images and database backups | Cloudflare R2 Standard | Separate media and backup buckets |
| Secrets | Google Secret Manager | Runtime account can read only named secrets |
| Container images | Artifact Registry | One repository with old-image cleanup |
| Email | Django outbox + administrator SMTP | Configured under **System → Settings** |

Google requires a billing account. Free allowance is not itself a hard spending cap. Keep maximum
instances at one, leave paid vulnerability scanning disabled, configure measured-usage alerts and
use the Cloud Run spend-cap preview when the account is eligible. No claim that production will
remain free is made until a representative load test and monitored pilot provide evidence.

Cloudflare budget alerts are informational and evaluate delayed billing data; they do not pause R2.
The application therefore enforces independent ceilings before upload: 2 GiB for media and 7 GiB
for backups. The backup command preserves at least seven recent copies, retains no more than fourteen
objects, and removes the oldest eligible copies when space is required. These limits intentionally
leave at least 1 GiB below R2's 10 GB-month Standard-storage allowance. Configure account-wide R2
budget alerts at USD 1, USD 3 and USD 5 as secondary warnings, never as the primary control.

## Prepared files

- `Dockerfile` builds an immutable image and collects static files without production secrets.
- `cloudbuild.yaml` is available for repository-triggered builds.
- `deploy/cloud-run/deploy.ps1` creates the public service, private maintenance service and one
  migration-only Cloud Run Job.
- `aikol_booking/.env.production.example` lists every runtime value.

The web container never migrates or backs up during a cold start. Release migration runs as an
explicit job; scheduled work uses the private maintenance service. This prevents concurrent cold
starts from racing a schema change and avoids the one-minute minimum for frequent Cloud Run Jobs.

## One-time account setup

Install the Google Cloud CLI, authenticate the authorised AIKOL owner, create a project, attach a
billing account and select that project. Configure alerts at 70%, 80% and 90% of the validated
free-allowance operating envelope. If available, add a conservative Cloud Run spend cap below that
boundary. Alerts are not cutoffs; spend-cap enforcement is a preview and can have reporting delay.

Create the Neon database and the two R2 Standard buckets first. Keep both buckets private; media
objects are delivered with one-hour signed URLs. Then create the six secrets without
putting their values on a command line or in Git:

```powershell
gcloud secrets create django-secret-key --replication-policy=automatic
gcloud secrets versions add django-secret-key --data-file=-
gcloud secrets create credential-encryption-key --replication-policy=automatic
gcloud secrets versions add credential-encryption-key --data-file=-
gcloud secrets create database-url --replication-policy=automatic
gcloud secrets versions add database-url --data-file=-
gcloud secrets create r2-access-key-id --replication-policy=automatic
gcloud secrets versions add r2-access-key-id --data-file=-
gcloud secrets create r2-secret-access-key --replication-policy=automatic
gcloud secrets versions add r2-secret-access-key --data-file=-
gcloud secrets create r2-endpoint-url --replication-policy=automatic
gcloud secrets versions add r2-endpoint-url --data-file=-
```

Each `versions add` command waits for a value on standard input. Paste it and finish with Ctrl+Z,
Enter in Windows PowerShell. Generate the two application keys locally:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(64))"
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Deploy

Choose Singapore (`asia-southeast1`) initially: it is close to Malaysia and widely supported by
the related Google services. The script discovers Cloud Run's exact generated hostname after the
first rollout and then restricts Django to that hostname:

```powershell
.\deploy\cloud-run\deploy.ps1 `
  -ProjectId "YOUR_PROJECT_ID" `
  -MediaBucket "aikol-booking-media" `
  -BackupBucket "aikol-booking-backups"
```

The script builds the image, deploys the web service, deploys the jobs, creates a pre-migration
backup and runs migrations. On a brand-new empty database the first backup is intentionally empty.

Map the public hostname to the Cloud Run service using Cloud Run domain mapping or a supported
HTTPS proxy. Keep the generated `run.app` hostname allowed for health checks and job operations.

## Scheduler setup

Grant the runtime identity permission to execute the three operational jobs:

```powershell
$project = "YOUR_PROJECT_ID"
$region = "asia-southeast1"
$runner = "aikol-scheduler@$project.iam.gserviceaccount.com"
```

Create exactly three schedules, which fit the current Cloud Scheduler free allowance. Replace
`MAINTENANCE_URL` with the private service URL printed by the deployment script. OIDC authentication
is checked by Cloud Run IAM before Django receives a request:

```powershell
gcloud scheduler jobs create http aikol-email-every-five-minutes --location $region --schedule "*/5 * * * *" --time-zone "Asia/Kuala_Lumpur" --uri "$maintenanceUrl/internal/maintenance/email/" --http-method POST --oidc-service-account-email $runner --oidc-token-audience $maintenanceUrl
gcloud scheduler jobs create http aikol-complete-nightly --location $region --schedule "15 0 * * *" --time-zone "Asia/Kuala_Lumpur" --uri "$maintenanceUrl/internal/maintenance/complete/" --http-method POST --oidc-service-account-email $runner --oidc-token-audience $maintenanceUrl
gcloud scheduler jobs create http aikol-backup-nightly --location $region --schedule "45 0 * * *" --time-zone "Asia/Kuala_Lumpur" --uri "$maintenanceUrl/internal/maintenance/backup/" --http-method POST --oidc-service-account-email $runner --oidc-token-audience $maintenanceUrl
```

Retention cleanup is never scheduled because it requires administrator review and confirmation.

## Cost controls

1. Keep request-based billing, minimum instances zero and maximum instances one.
2. Keep one current and one rollback image; delete older image versions automatically.
3. Do not enable Artifact Analysis vulnerability scanning.
4. Keep media private with signed R2 URLs; static assets remain in the Cloud Run image.
5. Keep INFO logging and avoid logging successful request bodies or personal data.
6. Review Cloud Run request, CPU, memory, egress and Artifact Registry storage monthly.
7. Configure a 90% alert and, where the account offers it, a conservative Cloud Run spend-cap
   budget. Spend caps are a final brake, not the primary traffic-control mechanism.
8. Keep `R2_MEDIA_SOFT_LIMIT_BYTES=2147483648`,
   `R2_BACKUP_SOFT_LIMIT_BYTES=7516192768`, and `R2_BACKUP_MAX_OBJECTS=14` unless a documented
   capacity review proves a lower value is required. Do not raise them while relying on R2's free
   allowance.

## Compute conservation and overload policy

- Keep minimum instances at zero and maximum instances at one until measured demand justifies a
  change.
- Put Cloudflare in front of the service. Cache static/media responses and reject abusive traffic
  before it reaches Cloud Run.
- Use bounded admission: at most 20 requests execute concurrently. Excess requests may wait only
  briefly; then return `503` with `Retry-After` instead of accumulating an unbounded queue.
- Alert at 70%, 80% and 90% of the monthly free compute allowance using
  `run.googleapis.com/container/billable_instance_time` plus request and memory metrics.
- At 90%, enter conservation mode: disable nonessential exports and reports and strengthen
  anonymous request limits. At 95%, serve a static maintenance response at the edge so new traffic
  does not reach Cloud Run.
- Use a Cloud Run spend cap below the theoretical free boundary if the preview is available to the
  billing account. Reporting has latency, so never set it at the exact financial limit.
7. Configure registration/password-reset throttling and Cloudflare bot protection before launch.

## Go-live checks

1. Execute `aikol-migrate`, then run `python manage.py check --deploy` as a temporary job override.
2. Create the administrator with the one-time `bootstrap_admin` management command in a
   Cloud Run Job. It generates a random password, creates a verified staff superuser, and
   prints only a Fernet-encrypted handoff token. Run `deploy/cloud-run/reveal-admin-password.ps1`
   on the owner's machine; it fetches that token and the existing Secret Manager encryption key
   and reveals the password only in the local terminal. The local `bootstrap-admin.ps1` route
   is blocked by a Windows PostgreSQL client crash. Never put the plaintext password in chat,
   a command argument, a committed file, or a Cloud Run job environment variable. Change the
   bootstrap password after first sign-in.
3. Test registration, password reset and each booking-status email.
4. Upload and retrieve a resource image from R2.
5. Restore the latest R2 database dump into a separate PostgreSQL database.
6. Confirm the PostgreSQL overlap constraint rejects conflicting pending and approved bookings.
7. Verify all three Scheduler jobs show successful executions.
8. Complete UAT before declaring production live.

## Updating

Run `deploy.ps1` again. On an existing deployment it runs two Cloud Run jobs with the new image
**before** any service receives it: `aikol-backup`, then `aikol-migrate`. Migrations are additive,
so the code already serving traffic keeps working on the new schema, and the new code never meets
a database that is missing a table it expects. Verify the latest R2 backup and restore test before
any high-risk schema or retention change.
