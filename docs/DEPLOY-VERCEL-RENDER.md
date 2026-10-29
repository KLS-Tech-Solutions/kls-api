# Deploying KLS Academy — Vercel + Render + Supabase

Two frontends on Vercel, the API on Render, the database on Supabase. All three
free tiers. This is written against the DNS you already have at your registrar.

---

## 0. Where you already are

Your zone currently holds:

| Type | Name | Points at | Status |
|---|---|---|---|
| CNAME | `academy` | `…vercel-dns-017.com` | Vercel — academy project |
| CNAME | `admin` | `…vercel-dns-017.com` | Vercel — admin project |
| CNAME | `www` | `…vercel-dns-017.com` | Vercel |
| A | `@` | `76.76.21.21` | Vercel apex |
| TXT | `_vercel` ×2 | domain verification | Vercel |
| TXT | `@` ×2 | google-site-verification | Search Console |

So both frontend domains are already delegated to Vercel. Good.

### The record you are missing

**There is no `api` record.** Nothing resolves `api.klstechsolutions.in`, so
both frontends will have nowhere to send requests. You add it in §2 once Render
gives you a hostname — it cannot be created before the service exists.

> One thing to confirm, not a problem: `@` and `www` now point at Vercel. If
> your main company site at `www.klstechsolutions.in` used to be hosted
> elsewhere, it has moved. The academy footer links to that address, so check
> it still loads what you expect.

---

## 1. Before you deploy — one blocker

Render's free tier has an **ephemeral filesystem**. It is wiped on every
restart and every redeploy, and free instances sleep after ~15 minutes idle, so
restarts are routine.

What that does to each thing this app writes to `MEDIA_ROOT`:

| File | After a restart |
|---|---|
| Offer letters, certificates | Fine — regenerated from the database record on next download |
| **Chapter PDFs** | Gone. Rows remain, downloads 404 |
| **Task screenshots** | Gone permanently. Nothing can rebuild them |

### The bridge that lets you launch this week

Add the chapter re-render to the **start command** (§2). Every boot then
re-creates the 18 curriculum PDFs from `scripts/curriculum/` in about ten
seconds, and chapter downloads survive restarts with no code change:

```
alembic upgrade head && python scripts/seed_content.py --pdfs-only && uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Two things this does **not** fix, and you should know both:

- **A PDF an admin uploads through the console is overwritten on the next
  restart** by the curriculum version, for chapters 1–3 of each domain. Until
  storage is durable, treat the admin chapter upload as "for new chapters
  only", not for replacing the seeded ones.
- **Task screenshots are still lost.** You already decided to drop screenshots
  in favour of the GitHub link; until that change ships, a student's
  submission images disappear on the next restart.

The real fix is moving chapter PDFs into Postgres — roughly 10 MB for 18
chapters against Supabase's 500 MB, and then covered by your database backup.
Do it when you have a working shell; the bridge above is honest enough for an
MVP in the meantime.

---

## 2. Backend on Render

### 2.1 Create the service

**New → Web Service**, connect the `kls-api` repository.

| Field | Value |
|---|---|
| Name | `kls-api` |
| Language | Python 3 |
| Region | **Singapore** — closest to India of Render's options |
| Branch | `main` (or `dev`, whichever you deploy from) |
| Build command | `pip install -r requirements.txt` |
| Start command | see below |
| Instance type | **Free** |

Start command — one line:

```
alembic upgrade head && python scripts/seed_content.py --pdfs-only && uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

`--port $PORT` is not optional. Render assigns the port; hardcode 8000 and the
health check never passes, and the deploy sits on "in progress" until it times
out.

### 2.2 Environment variables

```ini
ENVIRONMENT=production
DEBUG=false
SECRET_KEY=<python -c "import secrets; print(secrets.token_urlsafe(48))">

DATABASE_URL=postgresql+psycopg://postgres.<ref>:<password>@aws-0-ap-south-1.pooler.supabase.com:5432/postgres?sslmode=require

CORS_ORIGINS=https://academy.klstechsolutions.in,https://admin.klstechsolutions.in
MINIMUM_AGE=18
MEDIA_ROOT=/tmp/kls-media

SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=klstechsolutions2025@gmail.com
SMTP_PASSWORD=<Gmail app password, not your account password>
EMAIL_FROM=KLS Academy <klstechsolutions2025@gmail.com>

ACADEMY_BASE_URL=https://academy.klstechsolutions.in
ADMIN_BASE_URL=https://admin.klstechsolutions.in

FIRST_SUPERADMIN_EMAIL=admin@klstechsolutions.in
FIRST_SUPERADMIN_PASSWORD=<generate one, store it in the password manager>
```

`MEDIA_ROOT=/tmp/kls-media` is deliberate: it declares the directory to be
scratch. An absolute path is required regardless — `config.py` refuses to start
in production on a relative one.

For Gmail SMTP you need an **app password** from your Google account, with
2-step verification on. Your normal password will be rejected.

### 2.3 First deploy

Deploy and watch the log. You want to see `alembic upgrade head` complete, then
uvicorn start. A configuration problem fails in the first ten lines with a
readable message naming the variable — `config.py` is written for this moment.

Then open Render's **Shell** tab and seed:

```bash
python scripts/seed.py          # super admin + email template rows
python scripts/seed_content.py  # 6 streams, tasks, 18 chapters + PDFs
```

Run `seed_content.py` in full **once** — the start command only does
`--pdfs-only`, which re-renders files for chapters that already exist and
creates nothing.

Confirm: `https://kls-api.onrender.com/health` returns
`{"status":"ok","environment":"production"}`.

### 2.4 Add the custom domain

Render → your service → **Settings → Custom Domains → Add**
`api.klstechsolutions.in`. Render shows you a CNAME target.

**Now add the missing DNS record** at your registrar:

| Type | Name | Content | TTL |
|---|---|---|---|
| CNAME | `api` | `kls-api.onrender.com` *(use the exact target Render shows)* | 14400 |

Wait for propagation, then check:

```powershell
nslookup api.klstechsolutions.in
curl https://api.klstechsolutions.in/health
```

Render issues the TLS certificate automatically once the CNAME resolves.

---

## 3. Frontends on Vercel

Two separate projects, same steps. Your domains are already attached — this is
about configuring them.

### 3.1 Environment variables

For **each** project, set these for **Production, Preview and Development**:

**Academy project:**
```ini
API_BASE_URL=https://api.klstechsolutions.in/api/v1
NEXT_PUBLIC_MIXPANEL_TOKEN=
```

**Admin project:**
```ini
API_BASE_URL=https://api.klstechsolutions.in/api/v1
```

`API_BASE_URL` has no `NEXT_PUBLIC_` prefix on purpose. The browser never calls
the API directly — it calls Next route handlers, which hold the httpOnly
session cookies and proxy onward. Prefixing it would compile the value into the
client bundle.

### 3.2 Redeploy

Environment variables only take effect on a new build. After setting them:
**Deployments → ⋯ → Redeploy** on each project. Skipping this is the most
common reason a correctly configured Vercel project still fails.

---

## 4. Close the CORS loop

The API only accepts browser requests from origins it has been told about. You
set `CORS_ORIGINS` in §2.2; verify it matches exactly:

```ini
CORS_ORIGINS=https://academy.klstechsolutions.in,https://admin.klstechsolutions.in
```

Scheme included, no trailing slash, no spaces after the commas. If you are also
testing on the `*.vercel.app` preview URLs, add those too. The API refuses to
start in production if any origin is plain `http://`.

Render restarts on an environment change — give it a minute.

---

## 5. Verify, in order

```powershell
curl https://api.klstechsolutions.in/health
curl -I https://academy.klstechsolutions.in
curl -I https://admin.klstechsolutions.in
```

Then in a browser:

- [ ] Landing page lists **six** internship domains
- [ ] Register an account — no verification step; it lands on sign-in
- [ ] A **taken email** shows the error under the email field, not as a banner
- [ ] A **wrong password** says "Incorrect email or password" — not anything
      about sessions expiring
- [ ] Sign in with the password you just chose; it works immediately
- [ ] Welcome email arrives (check Spam, Junk and Bin)
- [ ] Enrol in a domain; the offer letter PDF downloads and opens
- [ ] Open a chapter, then **Download** it
- [ ] Admin console: sign in, Catalogue → Notes shows 18 chapters
- [ ] Submit a task; it appears in the admin review queue
- [ ] Approve the final task; the certificate issues immediately
- [ ] The certificate's QR code resolves to the public verification page

**Then restart the Render service by hand and download a chapter again.** That
is the test that proves the §1 bridge works. If it 404s, the start command is
wrong.

---

## 6. Keep both free tiers awake — not optional

One action solves two problems. Point an uptime monitor (UptimeRobot's free
tier is enough) at:

```
https://api.klstechsolutions.in/health      every 5 minutes
```

- Stops Render spinning down, so students never hit a 60-second cold start
- Keeps the Supabase project active — a free project **pauses after 7 days
  idle** and has to be restored by hand
- Tells you when the site is down

---

## 7. Backups are entirely yours

Supabase free takes **no automatic backups**. Render stores nothing durable. So
the database is the only thing that matters, and one nightly dump covers it:

```bash
pg_dump -Fc "$DATABASE_URL" > kls_$(date -u +%Y%m%d).dump
```

Run it on a schedule from any machine that can reach Supabase, keep the files
off-platform, and **restore one once** to prove it works —
`docs/DEPLOYMENT.md` §8.3 has the rehearsal.

---

## 8. When something goes wrong

| Symptom | Cause |
|---|---|
| Deploy stuck on "in progress" | Start command not binding `$PORT` |
| First request takes ~60s | Free-tier cold start. §6 |
| CORS error in the console | `CORS_ORIGINS` missing that exact origin |
| Frontend calls fail, `api.` doesn't resolve | The missing CNAME. §2.4 |
| Env var change had no effect | Vercel needs a redeploy. §3.2 |
| `ModuleNotFoundError: No module named 'app'` | Seed scripts missing the `sys.path` bootstrap — make sure that commit is pushed |
| Chapter downloads 404 after a redeploy | Start command missing `--pdfs-only`. §1 |
| 500s after the site has been idle | Supabase paused, or a dropped pooler connection. §6 |
| SMTP auth fails | Gmail needs an **app password**, not the account password |

---

## What this costs

Zero: Render free, Vercel Hobby, Supabase free, UptimeRobot free.

Three honest caveats. Render's cold starts, which §6 mitigates. Backups being
entirely your responsibility. And **Vercel's Hobby plan is limited to
non-commercial personal use** — the definition reportedly extends to any
deployment used for the financial gain of anyone involved, including where a
paid employee wrote the code, and Vercel can disable Hobby projects at its
discretion. KLS Academy is an MSME's product. Cloudflare Pages and Netlify
carry no such restriction if you would rather not hold that risk.

First thing worth paying for, once students depend on it: Render's paid tier to
remove cold starts. Supabase Pro at $25/month for managed daily backups is
second.
