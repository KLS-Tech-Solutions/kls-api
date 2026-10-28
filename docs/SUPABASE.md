# Moving the database to Supabase

Supabase is managed PostgreSQL. Nothing in this codebase is Supabase-specific —
it is a Postgres connection string, so the move is a configuration change and a
data copy, not a port.

**What goes to Supabase:** the database only.
**What stays on your server:** every file. Offer letters, certificates, chapter
notes and task screenshots are written to `MEDIA_ROOT` on local disk. Supabase
Storage is not used, and the free tier's 1 GB storage allowance is irrelevant
to us.

---

## 1. Is the free plan enough?

Short answer: yes to start, with two caveats you must plan around.

| | Free | Pro |
|---|---|---|
| Price | $0 | $25/month |
| Database | 500 MB | 8 GB |
| Egress | 5 GB/month | 250 GB |
| Active projects | 2 | unlimited |
| Automatic backups | **none** | daily, 7-day retention |
| Idle behaviour | **paused after 7 days** | always on |

**500 MB is plenty.** This schema stores text and timestamps. No files, no
blobs. Thousands of students and their submissions will not approach it.

### Caveat 1 — the free plan pauses

A free project with no database activity for 7 days is paused, and someone has
to log in and restore it. For a launched platform that is a real outage, and it
arrives exactly when traffic is thinnest, which is early.

The uptime check in the runbook prevents it: a request every five minutes to
`/health` keeps the project active. **Set that up before you point production
at Supabase**, not after.

### Caveat 2 — the free plan has no backups

This is the serious one. Supabase takes no automatic backups on the free plan,
so a dropped table or a bad migration is unrecoverable from their side.

The nightly `pg_dump` in `docs/DEPLOYMENT.md` §8 is what covers this, and on
the free plan it stops being belt-and-braces and becomes the only belt. Do not
run free-tier Supabase in production without it, and rehearse the restore.

**When to move to Pro:** when real students have real certificates. $25/month
buys daily managed backups and no pausing, and at that point the data is other
people's credentials, not your test rows.

---

## 2. Which connection string

This is where most Supabase migrations lose an afternoon. Supabase offers
several and they are not interchangeable.

| Route | Host | Port | IPv4? | Use it for |
|---|---|---|---|---|
| Direct | `db.<ref>.supabase.co` | 5432 | **No — IPv6 only** | nothing, unless your server has IPv6 |
| Shared pooler, session | `aws-0-<region>.pooler.supabase.com` | 5432 | Yes | **the app and Alembic** |
| Shared pooler, transaction | same host | 6543 | Yes | not this project |

**Use the shared pooler on port 5432.**

Two reasons, both of which produce confusing failures if ignored:

- **The direct host is IPv6-only.** Most VPS providers hand out an IPv4
  address. The failure is a connection timeout or "Network is unreachable",
  which reads like a firewall problem and is not one. IPv4 on the direct host
  is a paid add-on; the shared pooler is IPv4 on every plan, so just use it.

- **Port 6543 is transaction mode.** It hands a different backend to each
  statement, so prepared statements, `SET`, advisory locks and `LISTEN/NOTIFY`
  stop behaving. Alembic wants a real session. Session mode on 5432 is what you
  want for both the app and migrations.

Your string, from Project Settings → Database → Connection string → **Session
pooler**:

```ini
DATABASE_URL=postgresql+psycopg://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require
```

Three things to change from what Supabase gives you:

1. `postgresql://` → **`postgresql+psycopg://`**. This project uses psycopg 3;
   without the driver suffix SQLAlchemy reaches for psycopg2, which is not
   installed.
2. Append **`?sslmode=require`**. Without it psycopg will connect in clear text
   if the server allows it, and every row crosses the internet in the open. The
   app refuses to start in production without it.
3. The username is `postgres.<project-ref>`, not `postgres`. The pooler needs
   the project in the username to know where to route you.

`app/core/database.py` notices a non-local host and tunes the pool
accordingly — smaller, with `pool_recycle` set well inside the pooler's idle
timeout, because a connection dropped by the pooler surfaces as an
intermittent "server closed the connection unexpectedly" on a request that did
nothing wrong.

---

## 3. Moving the data

If you have not launched, skip the copy: point `DATABASE_URL` at Supabase, run
`alembic upgrade head` and `python scripts/seed.py`, and you are done.

If you have live data:

```bash
# 1. Stop the API so nothing writes during the copy.
sudo systemctl stop kls-api

# 2. Dump the current database.
pg_dump -h localhost -U kls -Fc kls_academy > /srv/kls/backups/pre-supabase.dump

# 3. Restore into Supabase. --no-owner and --no-acl matter: the roles from your
#    server do not exist there, and without these every GRANT fails noisily.
pg_restore \
  --no-owner --no-acl \
  -d "postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require" \
  /srv/kls/backups/pre-supabase.dump

# 4. Point the app at Supabase, then start it.
sudo nano /srv/kls/kls-api/.env       # DATABASE_URL=...
sudo systemctl start kls-api
```

Verify before you tell anyone:

```bash
# Alembic agrees about the schema version
cd /srv/kls/kls-api && .venv/bin/alembic current

# The data actually arrived
psql "<your-supabase-url>" -c "select count(*) from users;"
psql "<your-supabase-url>" -c "select count(*) from certificates;"
```

Then sign in, download a certificate, and verify one on the public page. The
PDF comes off local disk and the record comes from Supabase — that single click
exercises both halves of the new arrangement, which is the thing worth testing.

**Keep `pre-supabase.dump`.** It is your way back for as long as the old
Postgres is gone and Supabase is unproven.

---

## 4. After the move

- [ ] Uptime check hitting `/health` every 5 minutes — this is what stops the
      project being paused
- [ ] Nightly `pg_dump` now pointing at the Supabase URL, **and one rehearsed
      restore** (`docs/DEPLOYMENT.md` §8)
- [ ] The old local Postgres stopped, but its final dump kept
- [ ] Supabase database password in the password manager
- [ ] Network restrictions set to allow your server's IP, if you want them

One thing not to do: do not enable Supabase Row Level Security on these tables.
RLS exists for clients that talk to Postgres directly with an anon key. Nothing
here does — every request goes through the API, which checks the user's role
against the database on every call. Turning RLS on would lock out the service
role the app connects as and break every query, for no gain.

---

## Sources

Supabase plan limits and connection modes change; check the current pages
before relying on the numbers above.

- [Supabase Pricing](https://supabase.com/pricing)
- [Connect to your database](https://supabase.com/docs/guides/database/connecting-to-postgres)
- [Supavisor session mode moved off port 6543](https://github.com/orgs/supabase/discussions/32755)
