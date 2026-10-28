# Deployment runbook

Everything needed to take KLS Academy from a bare VPS to a running production
system, and to keep it running.

**Nothing here is containerised.** The API runs as a systemd service in a
virtual environment, both frontends run as systemd services from a Next.js
standalone build, and Postgres is installed from the distribution's packages.
That is a deliberate choice for a platform this size: one machine, three
services, no orchestration layer to learn or debug at 2am.

This is written to be followed literally, by whoever is holding the pager —
including you months from now, including somebody who has never seen this
codebase. Where a step has a reason that is not obvious, the reason is given,
because a runbook whose steps look arbitrary is a runbook people start skipping.

**Read section 0 before buying anything.**

---

## 0. What you are deploying

Three pieces, three names:

| Piece | Repository | Runs on | Public name |
|---|---|---|---|
| Student portal | `KLS-academy` | port 3000 | `academy.klstechsolutions.in` |
| Admin console | `KLS-admin-dashboard` | port 3001 | `admin.klstechsolutions.in` |
| API | `kls-api` | port 8000 | `api.klstechsolutions.in` |

Plus PostgreSQL — either installed on this machine (§3) or managed by
Supabase (`docs/SUPABASE.md`).

**Uploaded files live on this server's disk**, under `MEDIA_ROOT`. There is no
object store. Offer letters, certificates, chapter notes and task screenshots
exist in exactly one place, which makes §8 load-bearing rather than
precautionary.

### The machine

A 4 GB / 2 vCPU VPS is comfortable. 2 GB works for running the services but is
tight for `npm run build`, which is the memory-hungry step — if you take 2 GB,
add swap before your first build (§1).

Ubuntu 24.04 LTS. Any distribution works; the commands assume that one.

### Things to get before you start

- [ ] VPS, with its IP address
- [ ] DNS control for `klstechsolutions.in`
- [ ] Somewhere off this server to put backups (any S3-compatible bucket,
      or another machine you can `rsync` to)
- [ ] SMTP credentials that can send as your sending address
- [ ] A password manager entry, shared with a second person (see §9)

---

## 1. First contact with the server

SSH in as root, then immediately stop using root.

```bash
adduser kls
usermod -aG sudo kls
rsync --archive --chown=kls:kls ~/.ssh /home/kls
```

Lock down SSH — `/etc/ssh/sshd_config`:

```
PermitRootLogin no
PasswordAuthentication no
```

```bash
systemctl restart ssh
```

**Before you close this session, open a second terminal and confirm you can
still get in as `kls`.** If you cannot, you still have the first session to fix
it with. Once both are closed, a broken SSH config means a support ticket.

Firewall:

```bash
ufw allow OpenSSH
ufw allow 80
ufw allow 443
ufw enable
```

Nothing else is exposed. Postgres (5432) and the three app ports are bound to
localhost and reachable only from the machine itself.

Automatic security updates:

```bash
sudo apt update && sudo apt install -y unattended-upgrades
sudo dpkg-reconfigure --priority=low unattended-upgrades
```

Swap, if you are on 2 GB. A Next.js build will be OOM-killed without it, and
the error it produces does not mention memory:

```bash
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### Runtimes

```bash
sudo apt install -y python3.12 python3.12-venv python3-pip \
                    postgresql postgresql-contrib libpq-dev build-essential git

# Node 22, from NodeSource — the distribution's Node is too old for Next 16.
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt install -y nodejs

python3.12 --version && node --version && psql --version
```

---

## 2. DNS

Three A records, all pointing at the VPS IP:

| Name | Type | Value |
|---|---|---|
| `academy` | A | your IP |
| `admin` | A | your IP |
| `api` | A | your IP |

If you use Cloudflare, set these to **DNS only** (grey cloud) until TLS is
issued in §5. Proxying before the certificate exists makes Let's Encrypt's
HTTP-01 challenge fail in a way whose error message does not mention
Cloudflare, and you will lose an hour to it.

Wait for propagation before continuing:

```bash
dig +short api.klstechsolutions.in
```

---

## 3. Database

```bash
sudo -u postgres psql
```

```sql
CREATE USER kls WITH PASSWORD 'PASTE_DB_PASSWORD_HERE';
CREATE DATABASE kls_academy OWNER kls;
\q
```

Confirm it only listens locally — the default, but worth checking, because a
Postgres open to the internet is found by scanners within hours:

```bash
sudo grep -E "^listen_addresses" /etc/postgresql/*/main/postgresql.conf
# listen_addresses = 'localhost'   (or absent, which means the same)
```

---

## 4. Code and configuration

```bash
sudo mkdir -p /srv/kls && sudo chown kls:kls /srv/kls

# Uploaded files and rendered PDFs. Deliberately a sibling of the code, not a
# child: `git pull` and a rebuild must never be able to touch it.
mkdir -p /srv/kls/media && chmod 750 /srv/kls/media

cd /srv/kls
git clone <your-remote>/kls-api.git
git clone <your-remote>/KLS-academy.git
git clone <your-remote>/KLS-admin-dashboard.git
```

### Generate the secrets

```bash
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(48))"
python3 -c "import secrets; print('DB_PASSWORD=' + secrets.token_urlsafe(24))"
python3 -c "import secrets; print('SUPERADMIN_PASSWORD=' + secrets.token_urlsafe(18))"
```

Put all three in the password manager **now**, before pasting them anywhere
else. A secret that exists only in a terminal scrollback is a secret you will
lose.

### `/srv/kls/kls-api/.env`

Start from `.env.example` and set:

```ini
ENVIRONMENT=production
DEBUG=false

# Local Postgres (§3). For Supabase instead, see docs/SUPABASE.md — use the
# session pooler on port 5432 and append ?sslmode=require.
DATABASE_URL=postgresql+psycopg://kls:<DB_PASSWORD>@localhost:5432/kls_academy
SECRET_KEY=<SECRET_KEY>

# HTTPS only. The app refuses to start with a plain-http origin in production.
CORS_ORIGINS=https://academy.klstechsolutions.in,https://admin.klstechsolutions.in

MINIMUM_AGE=18

# Outside the code directory, on purpose. A redeploy replaces /srv/kls/kls-api;
# a media folder inside it would go with every certificate ever issued.
MEDIA_ROOT=/srv/kls/media

SMTP_HOST=...
SMTP_PORT=587
SMTP_USER=...
SMTP_PASSWORD=...
EMAIL_FROM="KLS Academy <klstechsolutions2025@gmail.com>"

ACADEMY_BASE_URL=https://academy.klstechsolutions.in
ADMIN_BASE_URL=https://admin.klstechsolutions.in

FIRST_SUPERADMIN_EMAIL=admin@klstechsolutions.in
FIRST_SUPERADMIN_PASSWORD=<SUPERADMIN_PASSWORD>
```

```bash
chmod 600 /srv/kls/kls-api/.env
```

`app/core/config.py` refuses to start on a placeholder `SECRET_KEY`, on
`DEBUG=true` in production, on a plain-http CORS origin, and on a missing
super-admin password. If the service fails immediately after start, read the
first ten lines of `journalctl -u kls-api` — the reason will be there in plain
English.

### Frontend environment

```ini
# /srv/kls/KLS-academy/.env.production
API_BASE_URL=https://api.klstechsolutions.in/api/v1
NEXT_PUBLIC_MIXPANEL_TOKEN=      # optional; empty disables analytics entirely
```

```ini
# /srv/kls/KLS-admin-dashboard/.env.production
API_BASE_URL=https://api.klstechsolutions.in/api/v1
```

The JWT never reaches client JavaScript — the browser talks to the Next route
handlers, which hold httpOnly cookies and proxy to the API. `API_BASE_URL` is
therefore deliberately not `NEXT_PUBLIC_`.

### Install and build

```bash
# API
cd /srv/kls/kls-api
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/alembic upgrade head
.venv/bin/python scripts/seed.py        # first super admin + email template rows

# Frontends
cd /srv/kls/KLS-academy         && npm ci && npm run build
cd /srv/kls/KLS-admin-dashboard && npm ci && npm run build
```

Both frontends are configured with Next's `output: "standalone"`, which emits a
self-contained server at `.next/standalone/server.js`. The systemd units below
run that, not `next start`.

---

## 5. systemd services

Three units. Each restarts on failure and starts at boot.

`/etc/systemd/system/kls-api.service`:

```ini
[Unit]
Description=KLS Academy API
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=kls
WorkingDirectory=/srv/kls/kls-api
EnvironmentFile=/srv/kls/kls-api/.env
# Bound to localhost. Caddy is the only thing that should reach this.
ExecStart=/srv/kls/kls-api/.venv/bin/uvicorn app.main:app \
          --host 127.0.0.1 --port 8000 --workers 2
Restart=always
RestartSec=5

# The service needs to write nothing outside its own directory.
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/srv/kls/media

[Install]
WantedBy=multi-user.target
```

`/etc/systemd/system/kls-academy.service`:

```ini
[Unit]
Description=KLS Academy student portal
After=network.target

[Service]
Type=simple
User=kls
WorkingDirectory=/srv/kls/KLS-academy/.next/standalone
EnvironmentFile=/srv/kls/KLS-academy/.env.production
Environment=NODE_ENV=production
Environment=PORT=3000
Environment=HOSTNAME=127.0.0.1
ExecStart=/usr/bin/node server.js
Restart=always
RestartSec=5
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
```

`/etc/systemd/system/kls-admin.service` is identical except for the
description, `WorkingDirectory`, `EnvironmentFile`, and `PORT=3001`.

The standalone server needs the static assets and `public/` beside it, which
the build does not copy:

```bash
for app in KLS-academy KLS-admin-dashboard; do
  cp -r /srv/kls/$app/.next/static /srv/kls/$app/.next/standalone/.next/
  cp -r /srv/kls/$app/public       /srv/kls/$app/.next/standalone/
done
```

Forgetting this is the classic standalone mistake: the site loads but every
stylesheet and image 404s, so it renders as unstyled HTML.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now kls-api kls-academy kls-admin
sudo systemctl status kls-api kls-academy kls-admin --no-pager
```

---

## 6. Reverse proxy and TLS

Caddy, because it obtains and renews certificates by itself and its config for
this is nine lines. Nginx plus certbot is equally fine if you already know it.

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
  | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
  | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install -y caddy
```

`/etc/caddy/Caddyfile`:

```
api.klstechsolutions.in {
	reverse_proxy 127.0.0.1:8000
}

academy.klstechsolutions.in {
	reverse_proxy 127.0.0.1:3000
}

admin.klstechsolutions.in {
	reverse_proxy 127.0.0.1:3001
}
```

```bash
sudo systemctl reload caddy
```

Certificates are issued on first request to each name and renewed
automatically. If issuance fails, `journalctl -u caddy -n 50` says why; it is
almost always DNS not yet propagated, or a proxy in front.

Once TLS works, turn Cloudflare's orange cloud back on if you want it, and set
SSL mode to **Full (strict)**.

---

## 7. Verify the deployment

Do all of these. Each has failed at least once in a way the others did not
catch.

```bash
# The API is alive and knows it is in production
curl -s https://api.klstechsolutions.in/health
# {"status":"ok","environment":"production"}

# TLS is real on all three names
for h in api academy admin; do
  curl -sI "https://$h.klstechsolutions.in" | head -1
done

# Security headers are present
curl -sI https://api.klstechsolutions.in/health | grep -iE 'x-frame|nosniff|strict-transport'

# Nothing is listening publicly that should not be
sudo ss -tlnp | grep -vE '127\.0\.0\.1|::1'
# Expect only sshd, and caddy on 80/443.
```

Then, in a browser:

- [ ] Register an account. **The verification email arrives** — check Spam,
      Junk and Bin before concluding it did not.
- [ ] The link in that email signs you in, rather than landing on a "check your
      inbox" page.
- [ ] Registration refuses a date of birth under 18, with an explanation.
- [ ] Registration succeeds with the phone field left blank.
- [ ] The state picker lists Indian states, and becomes a text box when the
      country is changed.
- [ ] Sign-in is blocked until the terms box is ticked.
- [ ] Enrol in a domain; the offer letter PDF downloads and opens, and the seal
      on it carries no street name.
- [ ] A file appeared under `/srv/kls/media/offer-letters/` — this is the proof
      that `MEDIA_ROOT` is writable and pointing where you think.
- [ ] Upload a chapter PDF from the admin console, then **Read** and
      **Download** it as a student. Read opens in a viewer, Download saves.
- [ ] Submit a task from the student side; it appears in the admin queue.
- [ ] Approve the last task; the certificate is issued immediately.
- [ ] The QR code on that certificate resolves to the public verification page.
- [ ] Paste the certificate number into `/verify` — it validates and is found.
- [ ] Reset your password; confirm the old session is signed out.
- [ ] Close the test account, then confirm the certificate still verifies.

---

## 8. Backups

**A backup you have never restored is a hypothesis.** This section is not done
until §8.3 has actually been run.

**There are now two things to back up, not one.** The database holds the
records; `/srv/kls/media` holds every rendered PDF, every uploaded chapter and
every task screenshot. There is no object store behind that directory — it is
the only copy. A database restore without the media is a platform where every
chapter download 404s.

Offer letters and certificates are the exception: they regenerate from their
database record on the next download, so losing those is recoverable. **Chapter
notes and task screenshots are not** — nothing can reconstruct a PDF an admin
uploaded or a screenshot a student submitted.

If you move the database to Supabase (`docs/SUPABASE.md`), the free plan takes
**no** automatic backups, so this section is the only thing standing between
you and permanent loss.

### 8.1 Nightly backup

`/srv/kls/backup.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

STAMP=$(date -u +%Y%m%dT%H%M%SZ)
DIR=/srv/kls/backups
mkdir -p "$DIR"

# --- database ---------------------------------------------------------------
# DATABASE_URL works for a local Postgres and for Supabase alike, so this line
# does not change when you migrate.
pg_dump -Fc "$DATABASE_URL" > "$DIR/kls_$STAMP.dump"

# --- uploaded files ---------------------------------------------------------
# Incremental would be cheaper, but a single dated archive is restorable by
# somebody who has never seen this script before, which matters more at 2am.
tar -czf "$DIR/media_$STAMP.tar.gz" -C /srv/kls media

# --- off the server ---------------------------------------------------------
# A backup on the same disk as the data protects against exactly one failure
# mode — a bad DELETE — and none of the others.
rclone copy "$DIR/kls_$STAMP.dump"       remote:kls-backups/
rclone copy "$DIR/media_$STAMP.tar.gz"   remote:kls-backups/

# Keep a fortnight locally.
find "$DIR" -name 'kls_*.dump'     -mtime +14 -delete
find "$DIR" -name 'media_*.tar.gz' -mtime +14 -delete
```

```bash
chmod +x /srv/kls/backup.sh
```

Put `DATABASE_URL` in `/srv/kls/backup.env` (`chmod 600`) and source it from
cron rather than writing credentials into the script.

Configure `rclone` for wherever the backups go (`rclone config` — any
S3-compatible bucket, or `sftp` to another machine), then schedule it:

```bash
crontab -e
# 02:30 UTC = 08:00 IST — after the quiet hours, before the day starts.
30 2 * * * . /srv/kls/backup.env && /srv/kls/backup.sh >> /srv/kls/backup.log 2>&1
```

Watch the media archive's size for the first few weeks. Screenshots accumulate
faster than anything else here, and a nightly full tar stops being sensible
somewhere north of a few gigabytes — at that point move to `rclone sync` of the
directory plus a weekly archive.

### 8.2 Also back up

- `/srv/kls/kls-api/.env` — encrypted, into the password manager, not the
  backup bucket
- `/etc/systemd/system/kls-*.service` and `/etc/caddy/Caddyfile` — small, and
  they are the difference between a one-hour rebuild and a one-day one

### 8.3 Rehearse a restore — do this once, now

**The database:**

```bash
sudo -u postgres createdb -O kls restore_test
pg_restore --no-owner -d "postgresql://kls@localhost/restore_test" \
  /srv/kls/backups/<latest>.dump

psql "postgresql://kls@localhost/restore_test" -c "select count(*) from users;"
psql "postgresql://kls@localhost/restore_test" -c "select count(*) from certificates;"
psql "postgresql://kls@localhost/restore_test" -c "select count(*) from learning_chapters;"

sudo -u postgres dropdb restore_test
```

**The media archive** — equally important, and the half people skip:

```bash
mkdir -p /tmp/restore-test
tar -xzf /srv/kls/backups/media_<latest>.tar.gz -C /tmp/restore-test

# The three directories that matter, and a spot check that a PDF is a PDF
# rather than a zero-byte file the archive dutifully preserved.
ls /tmp/restore-test/media/{chapters,certificates,offer-letters}
find /tmp/restore-test/media -name '*.pdf' | head -1 | xargs file

rm -rf /tmp/restore-test
```

If those counts are right, you have a backup. If the restore errored, you found
out on a Tuesday afternoon instead of during an incident, which is the entire
point of doing it now.

Write the date you did this at the bottom of this file.

---

## 9. Access — do not skip this

Right now, one person can do everything and nobody else can do anything. That
is a single point of failure wearing a hat.

- [ ] Put every credential in a shared password manager: SSH key, VPS console
      login, DNS, backup storage, SMTP, `SECRET_KEY`, database password,
      super-admin login.
- [ ] Give a second trusted person access to it.
- [ ] Create a **second super admin account** through the admin console. One
      forgotten password should not lock the organisation out of its own
      platform.
- [ ] Confirm the second person can actually sign in — to the server and to the
      console. Untested access is not access.

---

## 10. Monitoring

Minimum viable, in the order worth doing:

1. **Uptime check** on `https://api.klstechsolutions.in/health`, every five
   minutes, alerting to a phone. UptimeRobot's free tier is enough.
2. **Error tracking.** Add Sentry to the API and both frontends. Without it,
   the first you hear of a 500 is a student emailing you about it — if they
   bother.
3. **Disk space.** Postgres and old builds fill a small VPS quietly.
   ```bash
   df -h /
   du -sh /srv/kls/media /srv/kls/backups /srv/kls/*/node_modules
   ```
   `media` only ever grows. Screenshots are the bulk of it.
4. **Logs**, when something is wrong:
   ```bash
   journalctl -u kls-api -f -n 200
   journalctl -u kls-academy -n 100
   journalctl -u caddy -n 100
   ```

---

## 11. Deploying a change

```bash
cd /srv/kls/<repository>
git pull
```

**API:**

```bash
cd /srv/kls/kls-api
.venv/bin/pip install -r requirements.txt   # only if requirements changed
/srv/kls/backup.sh                          # before any migration
.venv/bin/alembic upgrade head
sudo systemctl restart kls-api
```

**A frontend:**

```bash
cd /srv/kls/KLS-academy
npm ci && npm run build
cp -r .next/static .next/standalone/.next/
cp -r public .next/standalone/
sudo systemctl restart kls-academy
```

The API restart is a second or two. A frontend build takes a few minutes, but
the old process keeps serving throughout — only the restart at the end is
visible, and that is also seconds.

### Rolling back

Code:

```bash
cd /srv/kls/<repository>
git log --oneline -5
git checkout <previous-commit>
# then rebuild/restart as above
```

A migration:

```bash
cd /srv/kls/kls-api && .venv/bin/alembic downgrade -1
```

Every migration in this project has a tested `downgrade()` — CI runs the whole
chain forward, back to base, and forward again on every push, so a reversal is
not a leap of faith. It is still not free: a downgrade that drops a column
drops the data in it. Prefer restoring from the dump you took minutes earlier
if any real data has been written since.

---

## 12. When something is wrong

| Symptom | Look here first |
|---|---|
| API fails at start | `journalctl -u kls-api -n 30` — config validation says exactly what is wrong |
| 502 from Caddy | The service behind it is down: `systemctl status kls-api kls-academy kls-admin` |
| Site loads unstyled, assets 404 | The `.next/static` and `public/` copy in §5 was missed after a build |
| TLS not issuing | `journalctl -u caddy` — usually DNS, or a proxy in front of the challenge |
| Emails not arriving | `email_logs` table shows whether we sent; then the recipient's spam folder |
| Everyone logged out at once | `SECRET_KEY` changed, or a `token_version` bump; check what was deployed |
| Uploads failing | `MEDIA_ROOT` permissions, then `df -h` — a full disk fails writes |
| Downloads 404 but the record exists | The file is gone from `MEDIA_ROOT`; offer letters and certificates regenerate on next download, chapter notes must be re-uploaded |
| Build killed with no error | Out of memory. Add swap — see §1 |
| Slow, no obvious cause | `htop`, then `df -h` — a full disk presents as generic slowness |

### Emergency: end every session immediately

If credentials are believed compromised, changing `SECRET_KEY` in `.env` and
running `sudo systemctl restart kls-api` invalidates every token in existence at
once. Everyone is signed out and signs back in. It is blunt, instant, and
reversible only in the sense that people can log in again.

---

## 13. Recurring

**Weekly**

- [ ] A database dump **and** a media archive landed off-server for each of
      the last seven days
- [ ] `df -h` — disk under 80%
- [ ] Sentry: anything new and repeating

**Monthly**

- [ ] `sudo apt update && sudo apt upgrade`
- [ ] Dependency audit — CI runs one on every push; read it
- [ ] **Rehearse the restore again.** Backups rot silently.

**Quarterly**

- [ ] Rotate the backup-storage and SMTP credentials
- [ ] Confirm the second admin's access still works
- [ ] Re-read §9 and check it is all still true

---

## Record

| What | When | By |
|---|---|---|
| First deployed | | |
| Restore rehearsed | | |
| Second super admin created | | |
| Credentials shared | | |
| Restore rehearsed | | |
| Restore rehearsed | | |
