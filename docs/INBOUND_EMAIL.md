# Automated email responses (inbound)

When someone emails you, the app:

1. records the message (admin → Inbound emails),
2. **auto-sends a safe acknowledgment immediately** ("we got your message…"),
3. **drafts a personalized AI reply and queues it for your approval** — nothing
   personalized sends until you click approve.

This "hybrid" design means senders always get an instant response, while you
stay in control of anything the AI writes.

Inbound mail is received via **SendGrid Inbound Parse**, which POSTs each email
to `POST /inbound/email/` on the app. We use a dedicated subdomain so it never
interferes with your existing Gmail/Workspace mail on your main domain.

## One-time setup

### 1. Pick a secret and set it on Heroku
```bash
heroku config:set INBOUND_EMAIL_TOKEN="$(python -c 'import secrets;print(secrets.token_urlsafe(24))')"
```
The webhook rejects any request whose `?token=` doesn't match this.

### 2. Add an MX record (Namecheap → Advanced DNS)
Point a subdomain (e.g. `parse`) at SendGrid:

| Type | Host    | Value            | Priority |
|------|---------|------------------|----------|
| MX   | `parse` | `mx.sendgrid.net`| 10       |

So the receiving address will be like `hello@parse.nemowaterrisk.com`.

### 3. Configure SendGrid Inbound Parse
SendGrid (free account) → **Settings → Inbound Parse → Add Host & URL**:
- **Receiving domain:** `parse.nemowaterrisk.com`
- **Destination URL:** `https://www.nemowaterrisk.com/inbound/email/?token=YOUR_SECRET`
  (use the exact `INBOUND_EMAIL_TOKEN` value)
- Leave "POST the raw MIME" unchecked — we use the parsed `from` / `subject` / `text` fields.

### 4. Publish the address
Put `hello@parse.nemowaterrisk.com` (or forward a nicer address to it) wherever
you invite replies. Any mail sent there flows through the webhook.

## Try it
Send an email to your parse address. Within a moment you should get the
acknowledgment, and in the admin you'll see the message under **Inbound emails**
plus a pending **Email reply** in **Approval items**. Approve it and run
`python manage.py run_orchestrator --stage distribute` (or your scheduled
distribution) to send the AI-drafted reply.

## Notes
- Replies send through your configured email backend (the Gmail SMTP you set up
  for reports), so they come from `DEFAULT_FROM_EMAIL`.
- If the LLM isn't configured, the acknowledgment still sends; the AI reply is
  simply skipped (no junk queued).
- Want fully-automatic replies (no approval)? That's a small change to the
  webhook — ask when you're ready; the approval-gated default is safer.
