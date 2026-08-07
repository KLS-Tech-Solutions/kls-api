# Running everything locally — no Docker

Postgres already installed, database `kls_academy` already created.
Follow this in order and the whole platform runs on your machine.

---

## Don't create the tables by hand

**Alembic creates them.** One command builds all 20 tables with the right columns,
foreign keys, indexes and constraints — exactly matching the SQLAlchemy models.

Hand-building tables in pgAdmin will drift from the models. The API will then fail in
ways that look like application bugs but are really column mismatches, and every future
schema change becomes a manual diff. Alembic also records which migration ran, so the
next change is one command instead of a hunt.

Use pgAdmin to **look at** the result, not to build it.

*(If you truly need the raw DDL — a locked-down server, a DBA who must review it —
`docs/schema.sql` is the generated script. Skip to the appendix.)*

---

## Step 1 — Python environment

Open **PowerShell** in `Desktop\kls-api`:

```powershell
python -m venv .venv
.venv\Scripts\activate
```

Your prompt should now start with `(.venv)`.

```powershell
pip install -r requirements.txt
```

**If `weasyprint` fails to install or import** — it needs GTK libraries that Windows
doesn't ship. This is fine and expected. The API detects it and stores documents as HTML
instead of PDF, so nothing breaks. To install the rest without it:

```powershell
pip install fastapi uvicorn[standard] python-multipart sqlalchemy alembic psycopg[binary] pydantic pydantic-settings email-validator pyjwt argon2-cffi boto3 razorpay qrcode[pil] jinja2 httpx
```

---

## Step 2 — Configuration

```powershell
copy .env.example .env
```

Generate a secret:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Open `.env` and set these four lines. **The database URL is the one that matters** —
use your own Postgres username and password, and note the `+psycopg` part:

```bash
DATABASE_URL=postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/kls_academy
SECRET_KEY=<paste the generated value>
FIRST_SUPERADMIN_EMAIL=admin@klstechsolutions.in
FIRST_SUPERADMIN_PASSWORD=<choose a real password>
```

Leave everything else as it is. R2, Razorpay and SMTP are all optional — the API
degrades gracefully without them.

---

## Step 3 — Create the tables

```powershell
alembic upgrade head
```

Expected output ends with:

```
INFO  [alembic.runtime.migration] Running upgrade  -> 87f2faee7f16, initial schema
```

**Check in pgAdmin:** refresh `kls_academy` → Schemas → public → Tables. You should see
**21 tables** (20 application tables plus `alembic_version`).

### Troubleshooting

| Error | Cause | Fix |
| --- | --- | --- |
| `ModuleNotFoundError: psycopg` | Driver missing | `pip install "psycopg[binary]"` |
| `password authentication failed` | Wrong credentials in `DATABASE_URL` | Check the user and password you use in pgAdmin |
| `database "kls_academy" does not exist` | Wrong database name | Confirm the exact name in pgAdmin |
| `could not connect to server` | Postgres not running | Start the `postgresql-x64-…` service in Windows Services |
| `Target database is not up to date` | Tables already exist | See "Starting over" below |

---

## Step 4 — Seed the catalogue and your admin account

```powershell
python scripts\seed.py
```

This creates 6 internship domains, 6 batches, 26 tasks, and your super admin. It prints
the admin email. **Those are your admin console credentials** — that email plus the
`FIRST_SUPERADMIN_PASSWORD` you chose in step 2.

It is safe to run again; it skips anything that already exists.

---

## Step 5 — Start the API

```powershell
uvicorn app.main:app --reload
```

- API: http://localhost:8000
- Interactive docs: http://localhost:8000/docs
- Health: http://localhost:8000/health

Leave this terminal running.

---

## Step 6 — Point the student app at it

New terminal, in `Desktop\academy`:

```powershell
copy .env.example .env.local
```

Edit `.env.local`:

```bash
NEXT_PUBLIC_LAUNCH_MODE=live
NEXT_PUBLIC_USE_MOCKS=false
API_BASE_URL=http://localhost:8000/api/v1
COOKIE_SECURE=false
```

```powershell
npm install
npm run dev
```

→ http://localhost:3000

---

## Step 7 — Point the admin console at it

New terminal, in `Desktop\admin-dashboard`:

```powershell
copy .env.example .env.local
npm install
npm run dev
```

→ http://localhost:3001 — sign in with the super admin from step 4.

---

## Step 8 — Prove it works end to end

Four terminals: Postgres (service), API, academy, admin.

1. **Register a student** at http://localhost:3000/register
2. **Enrol** in a domain from the dashboard → the offer letter appears with a real number
3. **Submit the LinkedIn task** with any `https://www.linkedin.com/posts/...` URL
4. **In the admin console** → LinkedIn reviews → approve it
5. **Back in the student app** → technical tasks are now unlocked
6. **Submit a task** — GitHub repo URL, 120+ character explanation, 3 screenshots
7. **Admin** → Task reviews → approve
8. Repeat for the remaining tasks → payment unlocks → pay → certificate issued
9. **Verify the certificate** at http://localhost:3000/verify

If a student is stuck at a stage they shouldn't be, that is the journey engine, and
`kls-api/app/services/journey.py` is the file to look at.

---

## The 20 tables and what each is for

| Table | Purpose |
| --- | --- |
| `users` | Everyone — students, admins, super admins. Role and status live here |
| `student_profiles` | College, degree, branch, year, LinkedIn, GitHub |
| `admin_profiles` | Designation and permissions for admin accounts |
| `email_tokens` | Single-use tokens: email verification, password reset, **admin invitations** |
| `internship_domains` | The six tracks students can enrol in |
| `internship_batches` | Each domain runs in batches with dates and seats |
| `tasks` | Per batch. `order_number` 0 is the LinkedIn onboarding task |
| `enrollments` | Links a student to a batch. One active per student |
| `offer_letters` | Number, PDF URL, LinkedIn verification flag |
| `linkedin_submissions` | Task 1 — the post URL and its review outcome |
| `task_submissions` | Repository, explanation, status, attempt number |
| `task_screenshots` | 3–8 images per submission, ordered |
| `admin_reviews` | Every approve/reject with remarks — the full history |
| `payments` | Razorpay order and payment ids, amount in **paise** |
| `certificates` | Number, PDF URL, QR URL, issued or revoked |
| `certificate_verification_logs` | Every public verification attempt, for audit |
| `notifications` | In-app notifications shown in the student dashboard |
| `email_templates` | Templates for Phase 8 — created, not yet used |
| `email_logs` | Every email sent or queued |
| `activity_logs` | Audit trail of consequential actions |

Plus `alembic_version`, which records the applied migration. Don't touch it.

**There is no `stage` column anywhere.** A student's stage is computed on every read from
the records above, so it can never contradict reality — an approval that gets reversed or
a payment that fails later immediately changes what the student sees.

---

## Starting over

To wipe and rebuild:

```powershell
alembic downgrade base
alembic upgrade head
python scripts\seed.py
```

Or drop the schema in pgAdmin and re-run `alembic upgrade head`:

```sql
DROP SCHEMA public CASCADE;
CREATE SCHEMA public;
```

---

## Daily routine, once set up

Three terminals:

```powershell
# 1
cd Desktop\kls-api; .venv\Scripts\activate; uvicorn app.main:app --reload

# 2
cd Desktop\academy; npm run dev

# 3
cd Desktop\admin-dashboard; npm run dev
```

---

## Appendix — creating the tables from raw SQL

Only if you cannot run Alembic. `docs/schema.sql` contains the full DDL.

1. pgAdmin → right-click `kls_academy` → **Query Tool**
2. Open `docs/schema.sql` (folder icon) → **Execute** (F5)
3. Refresh Tables — 21 should appear

The script inserts the `alembic_version` row, so Alembic will still see the database as
up to date and future migrations will apply normally.

**Regenerate it whenever the models change:**

```powershell
alembic upgrade head --sql > docs\schema.sql
```
