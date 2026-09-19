# Action test matrix

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe tools\test_action_matrix.py
```

The script refuses production settings, inventories all 72 named application routes, and runs the
complete Django regression suite in a disposable SQLite test database. It does **not** seed or
alter production. The route inventory detects newly added screens/actions that have not been
classified; it does not by itself prove that every input combination works. The tests supply
the behaviour checks below.

| Area | Actions and refusal paths exercised | Automated test modules |
| --- | --- | --- |
| Accounts | Register as IIUM/public user; reject duplicates and invalid identifiers; verify email and reject replay/tampering; sign in, throttle, reset password, edit profile, sign out, enforce role and ownership | `apps.accounts.tests` |
| Second factor | Enrol an authenticator (QR, manual key, confirm code, recovery codes shown once and stored hashed); verify each session; refuse wrong, replayed and other people's codes; throttle; keep sign-out reachable; hold approvers, administrators and Django's admin at the door and leave ordinary users alone; administrator reset ends the person's sessions and is refused for oneself; command-line reset for the last administrator | `apps.accounts.tests.test_mfa` |
| Resource browsing | List, filter, paginate and inspect venues/cars; check status and placeholder images | `apps.resources.tests`, `apps.accounts.tests.test_smoke` |
| Resource administration | Create/edit/deactivate/delete through the history gates; manage facilities, order and images; reject bad uploads and unauthorized access | `apps.resources.tests` |
| Booking | Prefill a selected slot; submit room and car requests; reject missing/invalid fields, conflicts, rule violations and unverified accounts; view, search, paginate and cancel own requests | `apps.bookings.tests`, `apps.accounts.tests.test_design` |
| Recurring booking | Preview/submit full or partial series; handle breaks/clashes; approve or cancel series and occurrences | `apps.bookings.tests.test_workflow`, `test_rules`, `test_operational_workflows` |
| Decisions and keys | Approve/reject requests; record vehicle management decision and driver; issue and return keys; reject duplicate or unauthorized handovers | `apps.bookings.tests.test_workflow`, `test_operational_workflows`, `test_keys` |
| Settings and communications | Update governed settings and SMTP configuration; encrypt password; queue and send mail with a mocked SMTP connection; verify disabled delivery leaves mail queued | `apps.administration.tests`, `apps.notifications.tests`, `config.tests.test_maintenance` |
| Data and reports | Import validation, CSV exports, reporting, retention preview and guarded deletion, backup storage limits, audit entries | `apps.importexport.tests`, `apps.administration.tests.test_backup_command`, `config.tests.test_storage` |
| Security | CSRF, escaping, authorization matrix, account enumeration, headers and production setting check | `apps.accounts.tests.test_security` |

## UAT that automated tests cannot establish

Before public launch, an authorized tester should complete these on the deployed site using
non-sensitive test records, then remove/cancel them according to the retention policy:

1. Submit a room and a car request in the browser; confirm each new booking reference appears.
2. Submit invalid fields and a taken slot; confirm the form names the problem without creating a booking.
3. Complete the approver, management, key-issue and key-return flows in the browser.
4. Configure an authorized SMTP mailbox in System settings, enable delivery, then register a
   disposable test account and confirm the verification link and booking emails actually arrive.
5. Review the booking form, popup, navigation and tables at 320 px, tablet and desktop widths with
   keyboard and touch input.
6. Verify a production PostgreSQL concurrency test before relying on the database exclusion
   constraint. The SQLite suite skips that provider-specific test.

Never enter a real administrator password into test fixtures or commit SMTP credentials.
