# External services — what to do, in order

Three accounts to set up: **Cloudflare R2**, **email (SMTP)** and **Razorpay**. Each
section ends with the exact lines to paste into `kls-api/.env`.

**Do them in this order.** R2 is free and instant. Email unblocks three half-finished
flows. Razorpay takes days to approve and needs your legal pages published first — so
apply early, but it cannot be first.

You do **not** need any of these to keep developing. The API already degrades: uploads
go to `./media`, emails are logged with the link returned, and payments use a
development order id.

---

# 1 · Cloudflare R2 — file storage

**What it stores:** task screenshots, offer letter PDFs, certificate PDFs and QR codes.

**Why R2 and not S3:** no egress fees. Every certificate download and every screenshot a
reviewer opens costs nothing to serve. On S3 that is billed per gigabyte.

**Cost:** free up to 10 GB stored and 1 million writes a month. You will not approach
that with a few hundred students.

### Steps

1. **Create the account** — cloudflare.com → Sign up. A card is required even on the free
   tier; you will not be charged within the free allowance.

2. **Enable R2** — dashboard → **R2 Object Storage** in the sidebar → *Purchase R2 Plan*.
   Choose the free tier.

3. **Create a bucket**
   - Name: `kls-academy`
   - Location: **Automatic** or **Asia-Pacific**
   - Click *Create bucket*

4. **Make it publicly readable** — this matters. Certificates and screenshots are fetched
   directly by the browser.
   - Open the bucket → **Settings** → **Public access**
   - Under *R2.dev subdomain*, click **Allow Access**
   - Copy the URL it gives you, like `https://pub-abc123....r2.dev`

5. **Create an API token**
   - R2 overview → **Manage R2 API Tokens** → *Create API token*
   - Permission: **Object Read & Write**
   - Scope: *Apply to specific buckets* → `kls-academy`
   - TTL: leave as forever
   - **Copy the Access Key ID and Secret Access Key now** — the secret is shown once.

6. **Find your Account ID** — it is on the R2 overview page, right-hand side. A 32-character
   hex string.

### Paste into `.env`

```bash
R2_ACCOUNT_ID=your_32_character_account_id
R2_ACCESS_KEY_ID=your_access_key_id
R2_SECRET_ACCESS_KEY=your_secret_access_key
R2_BUCKET=kls-academy
R2_PUBLIC_BASE_URL=https://pub-abc123xyz.r2.dev
```

Restart the API. Nothing else changes — `app/services/storage.py` switches from local
files to R2 as soon as the credentials are present.

### Check it worked

Enrol a test student and download the offer letter. Then in the Cloudflare dashboard,
open the bucket — you should see `offer-letters/KLS-ACAD-2026-00001.pdf`.

**If files were already created locally**, they stay in `./media` and will regenerate into
R2 on the next download. Nothing is lost.

---

# 2 · Email (SMTP)

**What it unblocks — three flows are incomplete without it:**

- Student email verification
- Student password reset
- Administrator invitations (currently you copy the link by hand)

## Which provider

| Provider | Free tier | Verdict |
| --- | --- | --- |
| **Brevo** | 300 emails/day, forever | **Recommended.** Works well from India, plain SMTP, no card |
| Resend | 3,000/month | Cleanest developer experience, needs domain verification |
| Zoho Mail | ~₹60/user/month | Choose this if you also want `@klstechsolutions.in` mailboxes |
| AWS SES | ~$0.10 per 1,000 | Cheapest at volume, awkward sandbox exit |
| Gmail SMTP | 500/day | Fine for testing only — Google throttles transactional sending |

300 a day covers roughly 100 new students daily. Start with Brevo.

### Brevo steps

1. Sign up at **brevo.com** with `klstechsolutions2025@gmail.com`.
2. Verify that address from the email they send.
3. **Senders, Domains & Dedicated IPs** → *Senders* → **Add a sender**
   - Name: `KLS Academy`
   - Email: `klstechsolutions2025@gmail.com`
   - Confirm from the verification email.
4. **SMTP & API** → **SMTP** tab. You will see:
   - Server: `smtp-relay.brevo.com`
   - Port: `587`
   - Login: something like `8a1b2c001@smtp-brevo.com`
   - Click **Generate a new SMTP key** and copy it.

### Paste into `.env`

```bash
SMTP_HOST=smtp-relay.brevo.com
SMTP_PORT=587
SMTP_USER=8a1b2c001@smtp-brevo.com
SMTP_PASSWORD=your_generated_smtp_key
EMAIL_FROM="KLS Academy <klstechsolutions2025@gmail.com>"
```

**The SMTP login is not your Brevo account email** — it is that `@smtp-brevo.com` address.
This trips most people up.

### Later, for deliverability

Once you own DNS for `klstechsolutions.in`, add Brevo's SPF and DKIM records and send from
`noreply@klstechsolutions.in`. Gmail increasingly puts unauthenticated bulk mail in spam.
Not urgent at your volume, but do it before a real intake.

### What still needs building

Setting `SMTP_HOST` makes `app/services/email.py` start delivering — **the invitation
email works immediately**. Verification, password reset and workflow notifications
currently create in-app notifications only; wiring them to `send_email()` is a small
piece of work I can do in one pass once your account exists.

### Check it worked

Invite an administrator from `/team` in the admin console. If the copy-link box is
replaced by "Email sent", delivery is live.

---

# 3 · Razorpay — the ₹50 certificate fee

**Longest lead time. Apply early.**

## Before you apply

**Your legal pages must be live and reachable.** Razorpay's reviewers open them. They are
currently placeholder copy at:

- `academy.klstechsolutions.in/legal/terms`
- `/legal/privacy`
- `/legal/refund`

**This is the real blocker**, and the only item nobody but you can do. The refund policy
must state what is refundable — ours already says the ₹50 is refunded if payment is taken
but no certificate is issued.

## Documents to have ready

- PAN (business or proprietor)
- **Udyam / MSME registration certificate**
- Bank account number and IFSC
- Cancelled cheque or a bank statement
- Address proof for the business

## Steps

1. Sign up at **razorpay.com** → choose **Business** account.
2. Complete KYC — upload the documents above. Approval typically takes 2–4 working days.
3. While waiting, use **Test Mode**: Settings → API Keys → *Generate Test Key*. You get
   `rzp_test_...` and a secret. Everything can be exercised end to end with test cards.
4. Once approved, Settings → API Keys → **Generate Live Key** → `rzp_live_...`.

### Paste into `.env`

```bash
# Test first
RAZORPAY_KEY_ID=rzp_test_xxxxxxxxxxxxx
RAZORPAY_KEY_SECRET=your_test_secret
CERTIFICATE_FEE_PAISE=5000
```

`CERTIFICATE_FEE_PAISE` is in **paise** — 5000 is ₹50. Getting this wrong by a factor of
100 is the classic payments mistake.

Signature verification switches on automatically the moment these are set.

### What still needs building

The backend is complete: `/payments/order` creates a real Razorpay order and
`/payments/verify` checks the signature. **Missing is the browser checkout** — about 30
lines loading Razorpay's `checkout.js` in `academy/src/app/dashboard/payment/page.tsx`,
plus a webhook endpoint for payments that complete out of band. I can write both now so
they are ready the day your account is approved.

### Test cards (test mode only)

```
Card:  4111 1111 1111 1111
CVV:   any 3 digits
Expiry: any future date
```

---

# Order of work

| # | Task | Yours or mine | Time |
| --- | --- | --- | --- |
| 1 | Cloudflare R2 account, bucket, token | Yours | 1 hour |
| 2 | Paste `R2_*` and restart | Yours | 5 min |
| 3 | Brevo account and SMTP key | Yours | 30 min |
| 4 | Wire email templates to workflow events | Mine | half a day |
| 5 | **Write the legal pages** | Yours | half a day |
| 6 | Apply to Razorpay with KYC | Yours | 1 hour + 2–4 days waiting |
| 7 | Razorpay checkout script and webhook | Mine | half a day |
| 8 | End-to-end test in Razorpay test mode | Both | 2 hours |

**Start step 5 today even though it is fifth in the list.** It has the longest dependency
chain — it gates Razorpay approval, which gates going live — and it is the one thing that
cannot be parallelised or done by anyone else.

---

# A note on secrets

`.env` is in `.gitignore` and must stay there. When the VPS arrives these values are set
as environment variables on the server, not committed. If a key is ever pasted into a
chat, a commit or a screenshot, rotate it — all three providers let you revoke and reissue
in seconds.
