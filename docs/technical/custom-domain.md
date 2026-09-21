# Give the system its own address

Production answers at `https://aikol-booking-qn23bk3fqa-as.a.run.app`. This is how to make it
answer at a name of the Kulliyyah's own, such as `aikolbooking.my`, and keep it working across
deployments. Nothing in the application changes; the work is a registrar, DNS, Cloud Run, and one
deployment parameter.

## 1. Decide who owns the name

A domain is registered to a person or an organisation, renewed yearly, and whoever holds the
registrar account controls where it points. Decide this before buying anything:

| Option | Who can register | Yearly cost (typical) | Notes |
| --- | --- | --- | --- |
| `aikolbooking.my` | Any Malaysian individual (MyKad) or organisation | RM 100 to 130 | Simplest. Registered personally it leaves with the person; register it to the Kulliyyah if possible |
| `aikolbooking.com.my` | A Malaysian business or organisation; MYNIC asks for the SSM certificate or equivalent | RM 80 to 100 | Reads as commercial; an academic unit rarely uses it |
| `booking.aikol.iium.edu.my` | Only IIUM, through ITD | Free | The institutional answer, and the one users would trust most, but it depends on ITD creating one DNS record, which this project has so far avoided |
| `aikolbooking.com` | Anyone | RM 50 to 70 | No Malaysian identity; not recommended for a Kulliyyah system |

Recommendation: ask ITD for the `iium.edu.my` subdomain first, because it costs nothing and
carries the university's name. If that is refused or slow, register `aikolbooking.my` in the
Kulliyyah's name at a MYNIC-accredited registrar (Exabytes, Nexus, IP ServerOne, ServerFreak,
WebNIC are the usual ones) with the office email as the account contact, not a personal one.

The rest of this page uses `aikolbooking.my` as the example. Replace it throughout.

## 2. Prove to Google that you control the domain

Cloud Run will only serve a domain that the Google account deploying the service has verified.

1. Open <https://search.google.com/search-console>, signed in as the account that runs
   `gcloud` (`afifdanial45@gmail.com` today).
2. Add a property of type **Domain**, enter `aikolbooking.my`.
3. Search Console shows a TXT record (`google-site-verification=...`). Add it at the registrar's
   DNS panel on the root of the domain. Come back and choose **Verify**. It can take a few minutes.

Alternatively, from PowerShell:

```powershell
gcloud domains verify aikolbooking.my
```

which opens the same page.

## 3. Map the domain to the public service

```powershell
gcloud beta run domain-mappings create --service aikol-booking --domain aikolbooking.my --region asia-southeast1 --project aikol-booking-system
```

The command prints the DNS records Cloud Run needs. For a root domain they are four `A` and four
`AAAA` records; for a subdomain such as `booking.aikolbooking.my` a single `CNAME` to
`ghs.googlehosted.com`. Enter them at the registrar exactly as printed. To see them again later:

```powershell
gcloud beta run domain-mappings describe --domain aikolbooking.my --region asia-southeast1 --project aikol-booking-system
```

Cloud Run then issues a TLS certificate itself. Until DNS has propagated and the certificate is
ready the mapping shows `CertificatePending`; it usually takes fifteen minutes to an hour, and
occasionally a day. Nothing is billed for the mapping or the certificate.

Do **not** map the maintenance service. It is private and is reached only by Cloud Scheduler.

## 4. Tell Django about the name

Django refuses any hostname it has not been told about. From now on, deploy with the domain:

```powershell
.\deploy\cloud-run\deploy.ps1 -ProjectId aikol-booking-system -PublicDomain aikolbooking.my
```

`-PublicDomain` adds the name to `DJANGO_ALLOWED_HOSTS` on both services (the `run.app` name stays,
because health checks and the scheduler use it), and `CSRF_TRUSTED_ORIGINS` follows automatically.
A deployment without the parameter pins the hosts back to the `run.app` name alone and the custom
address answers **400 Bad Request** until the next correct deploy, so put the parameter in whatever
note the office keeps of the deploy command.

To add it immediately without a full redeploy:

```powershell
gcloud run services update aikol-booking --region asia-southeast1 --project aikol-booking-system --update-env-vars "^@^DJANGO_ALLOWED_HOSTS=aikol-booking-qn23bk3fqa-as.a.run.app,aikolbooking.my"
```

## 5. Check

- `https://aikolbooking.my/` shows the sign-in page with a valid padlock.
- `https://www.aikolbooking.my/`: only if you also mapped `www` (a second `domain-mappings create`
  with `--domain www.aikolbooking.my`, and a CNAME). Most institutional sites skip `www` now.
- Request a password reset: the link in the email uses whichever hostname the request came in on,
  so a reset requested at the new address links back to the new address.
- The old `run.app` address keeps working. Leave it; nothing needs to be redirected.

## Things that do not need doing

- **No load balancer.** Google's HTTPS load balancer would also work and costs about RM 80 a
  month; the domain mapping does the same job for this traffic at no cost.
- **No Cloudflare proxy.** Cloudflare's free plan cannot rewrite the `Host` header, and Cloud Run
  routes by hostname, so proxying through it needs a Worker. Cloudflare is fine as the DNS host
  with the proxy switched off (grey cloud).
- **No change to email.** The From address is the Gmail account; the domain is not involved. If
  the office later wants mail from `@aikolbooking.my` that is a separate mailbox decision.

## Renewal

Put the renewal date in the office calendar. An expired domain takes the whole system offline at
that address within days, and a lapsed `.my` name can be registered by anyone after the grace
period. Turn on auto-renewal at the registrar and keep a card on file that will not expire first.
