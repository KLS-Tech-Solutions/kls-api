# Deploying to Vercel + Render

Frontends on Vercel, API on Render, database on Supabase.

**Yes, this works — but not with the code exactly as it stands.** Render's free
tier has an ephemeral filesystem, and this application currently writes PDFs
and screenshots to local disk. §0 is the prerequisite work. Skip it and the
deployment will appear to succeed and then quietly lose files.

Read §0 and §1 before creating any account.

---

## 0. Prerequisites — two code changes

Render's free instances are wiped on **every restart and every redeploy**, and
free instances also spin down after about 15 minutes of inactivity, so restarts
are routine rather than rare.

What that does to each file this app writes:

| File | On restart | Verdict |
|---|---|---|
| Offer letters, certificates | Regenerate from the database record on next download | Safe already |
| **Chapter PDFs** | Gone. Rows remain, downloads 404 | **Must fix** |
| **Task screenshots** | Gone permanently. Nothing can rebuild them | **Must fix** |

### 0.1 Move chapter PDFs into Postgres

Eighteen chapters at roughly 550 KB each is about 10 MB. Supabase's free plan
allows 500 MB, so even a hundred chapters is comfortable. Storing them as a
`bytea` column removes the last thing on disk that cannot be rebuilt, and they
are then covered by the database backup you already take.

The alternative is Supabase Storage (1 GB free), which keeps blobs out of the
database at the cost of one more integration. Either closes the hole; the
column is less work.

### 0.2 Remove task screenshots

You have already decided on this: GitHub link plus written explanation, no
image uploads. The backend supports it per task today — `min_screenshots` and
`max_screenshots` are columns, and the LinkedIn step already uses `0/0`. What
is needed:

- the seeder sets `min_screenshots=0, max_screenshots=0` on every task
- `max_screenshots` relaxes from `ge=1` to `ge=0` in the admin update schema,
  so the console can set it too
- the submission form hides the uploader when `max_screenshots === 0` (it
  currently renders it unconditionally and hardcodes a minimum of three)
- copy sweep: curriculum task requirements, the terms and privacy pages, and
  the FAQ in `seo.ts` all mention screenshots

Once both are done, nothing the application cannot rebuild lives on disk, and
Render's ephemeral filesystem stops mattering.

---

## 1. Two things to know before you commit to this

### Render free spins down

After ~15 minutes idle, the instance sleeps. The next request wakes it, and the
cold start takes **up to a minute** — during which a student sees a hanging
page. For an MVP shown to a handful of people that is survivable. For a public
launch it is not, and Render's paid starter tier removes it.

A monitor pinging `/health` every 5 minutes keeps it awake and, conveniently,
also keeps your Supabase project from pausing. That is two problems solved by
one uptime check, and it is why §6 is not optional.

### Vercel's Hobby plan bars commercial use

Vercel's fair-use guidelines limit Hobby to non-commercial personal use, and
the definition reportedly extends to any deployment used for the financial gain
of anyone involved — including where a paid employee or consultant wrote the
code. KLS Academy is an MSME's product. Vercel can disable Hobby deployments at
its discretion and without notice.

Your options, honestly: accept the risk, pay for Pro at $20/user/month, or put
the two frontends on **Cloudflare Pages or Netlify**, neither of which has that
restriction. This guide uses Vercel because you asked for it; the decision is
yours to take knowingly.

---

## 2. Backend on Render

1. **New → Web Service**, connect the `kls-api` repository.
2. Settings:

   | Field | Value |
   |---|---|
   | Runtime | Python 3 |
   | Build command | `pip install -r requirements.txt` |
   | Start command | `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
   | Instance type | Free |
   | Region | Singapore — closest to India of Render's options |

   The port **must** be `$PORT`. Render assigns it; a hardcoded 8000 means the
   health check never passes and the deploy hangs on "in progress".

3. Environment variables:

```ini
ENVIRONMENT=production
DEBUG=false
SECRET_KEY=<generate: python -c "import secrets; print(secrets.token_urlsafe(48))">

DATABASE_URL=postgresql+psycopg://postgres.<ref>:<password>@aws-0-ap-south-1.pooler.supabase.com:5432/postgres?sslmode=require

CORS_ORIGINS=https://academy.klstechsolutions.in,https://admin.klstechsolutions.in
MINIMUM_AGE=18

MEDIA_ROOT=/tmp/kls-media

SMTP_HOST=...
SMTP_PORT=587
SMTP_USER=...
SMTP_PASSWORD=...
EMAIL_FROM=KLS Academy <klstechsolutions2025@gmail.com>

ACADEMY_BASE_URL=https://academy.klstechsolutions.in
ADMIN_BASE_URL=https://admin.klstechsolutions.in

FIRST_SUPERADMIN_EMAIL=admin@klstechsolutions.in
FIRST_SUPERADMIN_PASSWORD=<generate one>
```

`MEDIA_ROOT=/tmp/kls-media` is deliberate and only correct **after §0**. It
says: this directory is scratch space, everything in it is rebuildable. Note
that `app/core/config.py` refuses to start in production on a relative
`MEDIA_ROOT`, so an absolute path is required regardless.

4. Deploy. Watch the log for `alembic upgrade head` completing, then uvicorn
   starting. A config problem fails loudly in the first ten lines with a
   readable message — the validator in `config.py` is written for this moment.

5. Once live, run the seeds from Render's **Shell** tab:

```bash
python scripts/seed.py
python scripts/seed_content.py
```

Both need the `sys.path` bootstrap added when CI caught this — without it they
fail with `ModuleNotFoundError: No module named 'app'`. Make sure that commit
is pushed.

6. Confirm: `https://<service>.onrender.com/health` returns
   `{"status":"ok","environment":"production"}`.

---

## 3. Frontends on Vercel

Two separate Vercel projects from two repositories. Same steps for each.

1. **Add New → Project**, import the repository. Vercel detects Next.js; leave
   the build settings alone.
2. Environment variables — set for **Production, Preview and Development**:

```ini
API_BASE_URL=https://<your-render-service>.onrender.com/api/v1
NEXT_PUBLIC_MIXPANEL_TOKEN=
```

`API_BASE_URL` has no `NEXT_PUBLIC_` prefix on purpose. The browser never
calls the API directly — it calls Next route handlers, which hold the httpOnly
cookies and proxy onward. Prefixing it would compile the value into the client
bundle and hand the API URL to every visitor, which is not a secret but is not
information to publish either.

3. Deploy. Repeat for the admin dashboard.

4. Add your domains: `academy.klstechsolutions.in` on the academy project,
   `admin.klstechsolutions.in` on the admin project, then the CNAME records
   Vercel shows you.

---

## 4. Close the CORS loop

Until the domains exist, Render's `CORS_ORIGINS` is pointing at names that do
not resolve. Once Vercel gives you URLs, go back and set it to exactly the
origins in use:

```ini
CORS_ORIGINS=https://academy.klstechsolutions.in,https://admin.klstechsolutions.in
```

While testing on `*.vercel.app` subdomains, add those too — comma separated, no
spaces, no trailing slash, scheme included. The API refuses to start in
production if any origin is plain `http://`.

Render restarts on an environment change. Give it a minute.

---

## 5. Verify, in this order

```bash
curl https://<service>.onrender.com/health
curl -I https://academy.klstechsolutions.in
```

Then in a browser, end to end:

- [ ] Landing page lists six internship domains
- [ ] Register — and **confirm the error messages read correctly**: a taken
      email appears under the email field, not as a banner; a wrong password on
      sign-in says "Incorrect email or password" rather than anything about
      sessions expiring
- [ ] Verification email arrives (check Spam, Junk and Bin)
- [ ] The link in it signs you in
- [ ] Enrol; the offer letter PDF downloads and opens
- [ ] Open a chapter, then download it
- [ ] Sign in to the admin console; Catalogue → Notes shows 18 chapters
- [ ] Submit a task; it appears in the admin review queue
- [ ] Approve the last task; the certificate issues immediately
- [ ] The certificate's QR code resolves to the public verification page

**Then restart the Render service by hand and run the chapter download again.**
That is the test that proves §0 was done properly. If the PDF still opens, your
storage is genuinely stateless. If it 404s, chapter PDFs are still on disk.

---

## 6. Keep both free tiers alive

Not optional, and one action covers both:

Point an uptime monitor — UptimeRobot's free tier is enough — at
`https://<service>.onrender.com/health` every **5 minutes**.

- It stops Render spinning down, so students never hit a 60-second cold start.
- It keeps the Supabase project active, which otherwise **pauses after 7 days
  idle** and needs restoring by hand.
- It tells you when the site is down.

---

## 7. Backups are entirely yours

Supabase's free plan takes **no automatic backups**. Render stores nothing
durable. After §0 the only thing that matters is the database, so a single
nightly dump covers the whole system — which is the one upside of going
stateless.

From any machine that can reach Supabase:

```bash
pg_dump -Fc "$DATABASE_URL" > kls_$(date -u +%Y%m%d).dump
```

Schedule it, send the file somewhere off-platform, and **restore it once** to
prove it works. `docs/DEPLOYMENT.md` §8.3 has the rehearsal.

---

## 8. When something is wrong

| Symptom | Cause |
|---|---|
| Deploy hangs on "in progress" | Start command is not binding `$PORT` |
| First request takes ~60s | Free tier cold start. §6 |
| CORS error in the browser console | `CORS_ORIGINS` missing that exact origin, scheme included |
| `ModuleNotFoundError: No module named 'app'` | Seed scripts missing the `sys.path` bootstrap |
| Chapter downloads 404 after a redeploy | §0.1 not done |
| 500 on login after idle | Supabase project paused, or pooler connection dropped. §6 |
| Service won't start, config error in log | Read it — `config.py` names the exact variable |

---

## What this costs

Everything above is $0: Render free, Vercel Hobby, Supabase free, UptimeRobot
free. The honest caveats are the three already stated — Render's cold starts,
Vercel's commercial-use restriction, and the fact that backups are on you.

The first upgrade worth paying for, when students are relying on it, is
Render's paid tier to remove cold starts. Supabase Pro at $25/month for managed
daily backups is the second.
