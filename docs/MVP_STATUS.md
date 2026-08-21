> **Superseded — August 2026.** The product went open source and free. Payments were removed entirely, study notes were added, and storage was made private. Anything below about Razorpay, the certificate fee or a payment step is historical. See `README.md` for the current state.

# KLS Academy MVP 001 — status against the PRD

Assessed 7 Aug 2026 against `KLS_Academy_MVP_001_PRD.pdf` and the Implementation Guide,
across all three repos with the database running locally.

**One line:** the software is essentially built. What remains is almost entirely
**external accounts and deployment** — not code.

| Repo | State |
| --- | --- |
| `academy` — student frontend | 26 pages, 113 files, wired to the live API |
| `admin-dashboard` — admin console | 19 pages, 82 files, wired to the live API |
| `kls-api` — FastAPI backend | 56 endpoints, 20 tables, 28 passing tests |

---

## 1. PRD MVP features

| # | Feature | State | Note |
| --- | --- | --- | --- |
| 1 | Public website | ✅ Done | 8 public pages including certificate verification |
| 2 | Student registration & login | ✅ Done | JWT in httpOnly cookies · **email verification link needs SMTP** |
| 3 | Internship domain selection | ✅ Done | 6 domains seeded, enrolment enforces one at a time |
| 4 | Automatic PDF offer letter | ✅ Done | Generated on enrolment · **PDF needs WeasyPrint, HTML fallback works** |
| 5 | LinkedIn onboarding task | ✅ Done | Submit → admin verifies → technical tasks unlock |
| 6 | Student dashboard | ✅ Done | 11 screens driven by the journey stage |
| 7 | Admin dashboard | ✅ Done | Review queues, catalogue, students, analytics, team |
| 8 | Internship task management | ✅ Done | Variable task counts, add/remove/reorder |
| 9 | Project submission | ✅ Done | GitHub + 3–8 screenshots + explanation, enforced server-side |
| 10 | QR certificate generation | ✅ Done | Issued on payment, QR encodes the verification URL |
| 11 | Certificate verification | ✅ Done | Public, server-rendered, every attempt logged |
| 12 | Razorpay payment | 🟡 Wired | Order + verify + signature check built · **needs a live account and the browser checkout script** |

**11 of 12 complete.** Razorpay is the only partial, and it is blocked on an account
rather than on code.

---

## 2. Functional requirements

| FR | Requirement | State |
| --- | --- | --- |
| FR1 | Student & admin auth (JWT/RBAC) | ✅ Three roles, enforced server-side |
| FR2 | Registration & profile management | ✅ |
| FR3 | Internship domain selection | ✅ |
| FR4 | Automatic PDF offer letter | ✅ |
| FR5 | LinkedIn submission (Task 1) | ✅ |
| FR6 | Internship task management | ✅ |
| FR7 | Project submission | ✅ Files land in `./media` until R2 is connected |
| FR8 | Admin review & approval | ✅ Both queues, remarks mandatory |
| FR9 | Razorpay ₹50 payment | 🟡 Backend complete, checkout stubbed |
| FR10 | QR certificate generation | ✅ |
| FR11 | Public verification portal | ✅ |
| FR12 | Admin dashboard & analytics | ✅ Funnel by stage, pending counts, revenue |
| FR13 | Notifications & activity logs | 🟡 In-app notifications on all 9 events; **email not sent** |

---

## 3. What is actually left

Only four things, in the order they block launch.

### A. Email delivery — the biggest gap

Three flows are incomplete without it:

- **Student email verification** — the token is generated but never sent
- **Student password reset** — same
- **Admin invitations** — work today by copying the link, but should arrive by email

`app/services/email.py` already records every message in `email_logs` and returns the
link. Setting `SMTP_HOST` switches it to real delivery **with no call-site changes**.

Still to write: the eight templates from the schema doc, and hooking `send_email()` into
the workflow events that currently only create in-app notifications.

### B. Razorpay, live

Backend is done — order creation, signature verification, failure handling. Missing:

- A Razorpay account with KYC complete
- `checkout.js` in the student payment page (~30 lines) replacing the stub in
  `academy/src/app/dashboard/payment/page.tsx`
- A webhook endpoint for payments that complete out of band

### C. Deployment

Nothing is deployed. Two Vercel projects, one VPS, DNS, SSL, and a production database.

### D. Content and assets

- **Legal pages are placeholder copy** — Razorpay activation depends on them
- **MSME artwork** is still the cleaned-up raster from a watermarked source
- Offer letter and certificate designs are my interpretation — review before issuing

---

## 4. External services you need

### Must have before launch

| Service | What for | Cost | Notes |
| --- | --- | --- | --- |
| **Cloudflare R2** | Screenshots, offer letters, certificates | Free to 10 GB/month | S3-compatible. Create a bucket, an API token, then fill `R2_*` in `.env`. **No egress fees** — the reason the PRD picked it |
| **Razorpay** | The ₹50 certificate fee | 2% per transaction | Needs KYC: PAN, bank account, and your **MSME/Udyam certificate**. Also needs your live legal pages |
| **Email provider (SMTP)** | Verification, reset, invites, notifications | Free tiers available | See options below |
| **VPS** | FastAPI + Postgres | ₹400–800/month | Hostinger, DigitalOcean or Contabo. 2 GB RAM is plenty |
| **Vercel** | Both frontends | Free (Hobby) | Already your deploy target |
| **DNS records** | `academy.` · `admin.` · `api.` subdomains | Included | At your existing registrar |

### Email provider — pick one

| Option | Free tier | Best for |
| --- | --- | --- |
| **Brevo** | 300/day | Recommended — generous, simple SMTP, works from India |
| **Resend** | 3,000/month | Cleanest developer experience, needs domain verification |
| **Zoho Mail** | Paid, ~₹60/user/month | If you also want `@klstechsolutions.in` mailboxes |
| **AWS SES** | ~$0.10 per 1,000 | Cheapest at volume, fiddly sandbox exit |
| Gmail SMTP | 500/day | Works for testing; not for transactional mail at scale |

Whichever you choose, you get a host, port, username and password — they go straight
into `SMTP_*` in `.env`. No code changes.

### Worth having

| Service | What for | Cost |
| --- | --- | --- |
| **Sentry** | Error tracking in production | Free tier |
| **UptimeRobot** | Alerts if the API goes down | Free |
| **Managed Postgres** | Backups and failover handled for you | ₹0–800/month · or self-host on the VPS with `pg_dump` cron |

### Not needed

Docker (you're running natively), Kubernetes, Redis, a CDN beyond Vercel's, and any
paid analytics — the admin console already reports what the PRD asks for.

---

## 5. Recommended order

**1 · Cloudflare R2 (1 hour).** Free, no approval wait, and it turns screenshot uploads
from local files into real cloud storage. Start here because nothing else depends on it
and it removes a launch blocker immediately.

**2 · Email provider (2–3 hours).** Sign up, verify your domain, fill in `SMTP_*`, then
I write the templates and wire them to the workflow events. This closes the largest
remaining gap — three flows become complete at once.

**3 · Legal pages (half a day, mostly yours).** Terms, privacy and refund need real
copy. **Razorpay will not activate without them**, so this gates step 4.

**4 · Razorpay (1–2 days, mostly waiting).** Apply with KYC and your Udyam certificate.
While approval is pending I add the checkout script and the webhook.

**5 · Deployment (1 day).** VPS, DNS, SSL, production Postgres, both Vercel projects,
then flip `NEXT_PUBLIC_LAUNCH_MODE` to `live`.

**6 · UAT.** Run the PRD's demo scenarios end to end with a real student before opening
enrolment.

---

## 6. What I can start on right now

Nothing in step 1–2 is blocked on me, but these are code and I can do them today:

- **Razorpay checkout script** in the student payment page, plus the webhook endpoint —
  ready and waiting when your account is approved
- **Email templates** — the eight from the schema doc, written and wired, dormant until
  `SMTP_HOST` is set
- **Deployment configuration** — Dockerfile for the VPS, nginx/Caddy config, systemd
  service, Vercel settings, and a deployment runbook
- **Frontend end-to-end tests** covering the full student journey

The most useful of these is the deployment configuration, because it is the one thing
that turns "runs on my laptop" into "runs on the internet", and it can be prepared before
any account exists.
