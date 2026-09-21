# Set up production email delivery

The application already sends mail with Python/Django SMTP. No paid email-sending service is
required by the code. A real mailbox or SMTP relay that the Kulliyyah is authorised to use is
required; the code cannot create an email identity or bypass a provider's authentication policy.

1. Ask the administrator of the sending mailbox for its **SMTP host**, **port**, **username**,
   **password or app credential**, whether it uses **STARTTLS** or **SSL**, and the exact
   **From address** it permits. Ask whether username/password SMTP is allowed from Cloud Run.
   This application does not currently support OAuth-only SMTP accounts.
2. Sign in as an administrator. Open **System → Booking rules** (`/manage/settings/`). The
   **Email delivery** section is above the business-rule table.
3. Enter the supplied host, port, username and credential. Select only the encryption mode
   specified by the mailbox administrator: **Use TLS** or **Use SSL**, never both. Enter the
   permitted From address. Leave the connection timeout at its default unless instructed otherwise.
4. Read the queued-message count in the yellow notice. Once enabled, earlier unsent messages may
   leave on the next scheduled run. Check whether that is appropriate, especially if old account
   verification links could have expired (the link validity is three days).
5. Tick **Enable email delivery** and choose **Save email settings**. Never paste the password
   into a chat, ticket or source file; enter it only into the authenticated administrator form.
6. Register a disposable test account using a mailbox you control. The outbox is sent every
   minute. Check the inbox and spam folder, follow the verification link, then
   submit a test booking and confirm the booking email arrives.

If the test email does not arrive, turn delivery off to pause further attempts while diagnosing.
Check the maintenance service's send-mail logs for connection, authentication or sender-denied
errors; messages with fewer than five failed attempts will retry after you correct the settings.
Messages that reached five attempts need deliberate recovery. A saved configuration proves only
that the form accepted the values, **not** that the mail server accepted a message. If a provider
allows only OAuth, stop and plan an approved OAuth integration instead of using a personal password
or disabling verification.

Email delivery remains a public-launch blocker until the end-to-end test succeeds.
