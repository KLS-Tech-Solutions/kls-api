# Moving the database to Supabase

Supabase is managed PostgreSQL. Nothing in this codebase is Supabase-specific —
it is a Postgres connection string — so the move is a configuration change plus
either a reseed or a data copy.

**What goes to Supabase:** the database only.
**What stays on your machine or server:** every file. Offer letters,
certificates, chapter PDFs and task screenshots are written to `MEDIA_ROOT` on
local disk. Supabase Storage is not used, so the free tier's 1 GB file
allowance is irrelevant to us.

Commands are written for **PowerShell on Windows**, since that is where the
local database currently lives. Where the syntax differs on Linux it is noted.

---

## Step 0 — Decide which path you are on

This is the only decision that matters, and it takes one query.

```powershell
psql -U postgres -d kls_academy -c "SELECT count(*) FROM users WHERE role = 'student';"
```

| Result | Path | Why |
|---|---|---|
| `0` students | **A — rebuild** | Faster, cleaner, and avoids `pg_dump` version trouble entirely |
| Real students | **B — dump and restore** | You have data that cannot be regenerated |

Path A is almost certainly yours if you have not launched. Everything in the
database right now — six streams, eighteen chapters, your admin account — is
produced by scripts in this repository, so recreating it on Supabase is two
commands and is *more* reliable than copying it.

### The `pg_dump` version trap (Path B only)

`pg_dump` refuses to dump from a server newer than itself, and a dump taken
from a newer server frequently fails to restore into an older one. Supabase
currently provisions Postgres 15 or 17 depending on the project; your Windows
install may be 17.

Check both before you start:

```powershell
pg_dump --version
psql -U postgres -d kls_academy -c "SHOW server_version;"
```

If your local server is newer than the Supabase one, use the **`pg_dump` that
ships with the lower version**, or take Path A. Mismatched versions produce an
error about an unsupported version number partway through a restore, usually
after you have already pointed the app at the new database.

---

## Step 1 — Create the Supabase project

1. Sign up at supabase.com and create a project.
2. Choose the region closest to your students — **Mumbai (ap-south-1)** for
   India. Region cannot be changed later, and it sets your latency floor.
3. Set a strong database password. **Put it in the password manager now** — the
   dashboard will not show it again.
4. Wait for provisioning, around two minutes.

### A note on the free plan

| | Free | Pro |
|---|---|---|
| Price | $0 | $25/month |
| Database | 500 MB | 8 GB |
| Automatic backups | **none** | daily, 7-day retention |
| Idle behaviour | **paused after 7 days** | always on |

500 MB is ample — this schema is text and timestamps, and the PDFs are not in
it. The two caveats are real though, and Step 6 deals with both. Move to Pro
when students hold certificates that matter.

---

## Step 2 — Get the right connection string

In the dashboard: **Project Settings → Database → Connection string**.

You will be offered several. **Use the Session pooler on port 5432.**

| Route | Host | Port | IPv4? | Use it |
|---|---|---|---|---|
| Direct | `db.<ref>.supabase.co` | 5432 | **No — IPv6 only** | no |
| Session pooler | `aws-0-<region>.pooler.supabase.com` | 5432 | Yes | **yes, for everything** |
| Transaction pooler | same host | 6543 | Yes | no |

Why this matters, because both failures are confusing:

- **The direct host is IPv6-only.** Most home connections and most VPS
  providers are IPv4. The failure is a connection timeout or "Network is
  unreachable", which reads like a firewall problem and is not one. IPv4 on the
  direct host is a paid add-on; the pooler is IPv4 on every plan.
- **Port 6543 is transaction mode.** It gives a different backend to each
  statement, so prepared statements, `SET`, advisory locks and `LISTEN/NOTIFY`
  misbehave. Alembic needs a real session. Session mode on 5432 is correct for
  both the app and migrations.

---

## Step 3 — Point the app at it

Edit `kls-api\.env` and change one line:

```ini
DATABASE_URL=postgresql+psycopg://postgres.<ref>:<password>@aws-0-ap-south-1.pooler.supabase.com:5432/postgres?sslmode=require
```

Three edits to what Supabase hands you, all required:

1. `postgresql://` → **`postgresql+psycopg://`**. This project uses psycopg 3;
   without the suffix SQLAlchemy reaches for psycopg2, which is not installed.
2. Append **`?sslmode=require`**. Without it psycopg will connect in clear text
   if the server permits it. The app refuses to start in production without it.
3. The username is **`postgres.<project-ref>`**, not `postgres`. The pooler
   reads the project from the username to know where to route you.

If your password contains `@`, `:`, `/` or `#`, percent-encode it — those
characters terminate fields in a URL. `@` becomes `%40`.

Confirm it connects before going further:

```powershell
cd C:\Users\Lenovo\Desktop\kls-api
.\.venv\Scripts\python -c "from app.core.database import engine; import sqlalchemy as sa; print(engine.connect().execute(sa.text('select version()')).scalar())"
```

That should print a PostgreSQL version string. If it hangs, you are on the
IPv6 direct host — go back to Step 2.

---

## Step 4A — Rebuild on Supabase (no student data)

```powershell
cd C:\Users\Lenovo\Desktop\kls-api
.\.venv\Scripts\activate

alembic upgrade head          # creates every table
python scripts\seed.py        # super admin + email template rows
python scripts\seed_content.py  # 6 streams, tasks, 18 chapters + PDFs
```

`seed_content.py` re-renders the chapter PDFs into `MEDIA_ROOT`, so the files
and the rows agree afterwards. That is the main reason this path is cleaner
than a copy: a database restore would carry rows pointing at PDF files, and
you would have to make sure those files existed separately.

Skip to Step 5.

---

## Step 4B — Dump and restore (you have student data)

```powershell
cd C:\Users\Lenovo\Desktop\kls-api

# 1. Stop anything writing to the database (close the API).

# 2. Dump. -Fc is the compressed custom format pg_restore wants.
pg_dump -U postgres -Fc -d kls_academy -f .\pre-supabase.dump

# 3. Restore. --no-owner and --no-acl matter: the roles from your machine do
#    not exist on Supabase, and without these every GRANT fails noisily.
pg_restore --no-owner --no-acl `
  -d "postgresql://postgres.<ref>:<password>@aws-0-ap-south-1.pooler.supabase.com:5432/postgres?sslmode=require" `
  .\pre-supabase.dump
```

A few warnings during restore are normal — Supabase ships extensions and
schemas your dump also describes. Errors mentioning `public` schema ownership
are safe to ignore. Errors about *your* tables are not.

Then confirm Alembic agrees about the schema version:

```powershell
alembic current      # should print c4a7e21f8d90 (head)
```

**Your media files do not move.** The rows reference PDFs under `MEDIA_ROOT`;
make sure that directory travels with the application. If the files are gone,
offer letters and certificates regenerate on next download, but **chapter PDFs
do not** — rerun `python scripts\seed_content.py --pdfs-only` to recreate them.

Keep `pre-supabase.dump` until Supabase has proven itself. It is your way back.

---

## Step 5 — Verify

```powershell
# Tables arrived
psql "<your-supabase-url>" -c "\dt"

# Content arrived
psql "<your-supabase-url>" -c "SELECT count(*) FROM internship_domains;"   # 6
psql "<your-supabase-url>" -c "SELECT count(*) FROM learning_chapters;"    # 18
psql "<your-supabase-url>" -c "SELECT count(*) FROM users;"
```

Then start the API and walk the path that touches both halves:

```powershell
uvicorn app.main:app --reload
```

- [ ] `http://localhost:8000/health` returns `ok`
- [ ] The catalogue lists six domains
- [ ] Sign in to the admin console; Catalogue → Notes shows 18 chapters
- [ ] Register a student, enrol, and **download the offer letter**
- [ ] Open a chapter PDF as that student

That last pair is the real test: the record comes from Supabase and the file
comes from local disk, so one click exercises the whole new arrangement.

---

## Step 6 — The two things that are now your responsibility

Do not skip these. On the free plan they are not optional extras; they are the
difference between a database and a liability.

### 6.1 Stop the project being paused

A free project with no activity for 7 days is paused and has to be restored by
hand. Point an uptime monitor at your health endpoint every 5 minutes —
UptimeRobot's free tier is enough — and it will never go idle.

This only works once the API is deployed somewhere public. Until then, open
the Supabase dashboard at least weekly.

### 6.2 Take your own backups

**Supabase takes no automatic backups on the free plan.** A dropped table is
gone. The nightly dump in `docs/DEPLOYMENT.md` §8 now points at Supabase:

```bash
pg_dump -Fc "$DATABASE_URL" > "$DIR/kls_$STAMP.dump"
```

That same section also archives `MEDIA_ROOT`, which matters more than before:
the database is now somewhere else, so a single backup no longer captures the
whole system. **Rehearse one restore** — §8.3 — before you rely on any of it.

---

## Notes

**Do not enable Row Level Security on these tables.** RLS exists for clients
that talk to Postgres directly with an anon key. Nothing here does — every
request goes through the API, which checks the user's role against the database
on each call. Turning RLS on would block the role the app connects as and break
every query, for no security gain.

**Connection pooling is already tuned.** `app/core/database.py` detects a
non-local host and switches to a smaller pool with `pool_recycle` set well
inside the pooler's idle timeout. Without that, a connection dropped by
Supavisor surfaces as an intermittent "server closed the connection
unexpectedly" on a request that did nothing wrong.

**Network restrictions** (Project Settings → Database) can limit access to your
server's IP once deployed. Worth doing, but add the IP before you enable it or
you will lock yourself out.

---

## Sources

Supabase plan limits and connection modes change. Check the current pages
before relying on the numbers above.

- [Supabase Pricing](https://supabase.com/pricing)
- [Connect to your database](https://supabase.com/docs/guides/database/connecting-to-postgres)
- [Supavisor session mode moved off port 6543](https://github.com/orgs/supabase/discussions/32755)
