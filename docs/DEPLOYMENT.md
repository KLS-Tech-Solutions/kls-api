# Deployment runbook

Everything needed to take KLS Academy from a bare VPS to a running production
system, and to keep it running.

This is written to be followed literally, by whoever is holding the pager —
including you at 2am, including somebody who has never seen this codebase.
Where a step has a reason that is not obvious, the reason is given, because a
runbook whose steps look arbitrary is a runbook people start skipping.

**Read section 0 before buying anything.**

---

## 0. What you are deploying

Three pieces, three names:

| Piece | Repository | Public name |
|---|---|---|
| Student portal | `KLS-academy` | `academy.klstechsolutions.in` |
| Admin console | `KLS-admin-dashboard` | `admin.klstechsolutions.in` |
| API | `kls-api` | `api.klstechsolutions.in` |

Plus PostgreSQL 17, and Cloudflare R2 for uploaded files.

### The machine

A 4 GB / 2 vCPU VPS is comfortable for this. 2 GB works but leaves no headroom
during a Docker build — if you take the 2 GB option, build images somewhere
else and pull them, rather than building on the server.

Ubuntu 24.04 LTS. Any distribution works; this runbook's commands assume that
one.

### Things to get before you start

- [ ] VPS, with its IP address
- [ ] DNS control for `klstechsolutions.in`
- [ ] Cloudflare R2 bucket and API token
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
it with. Once both sessions are closed, a broken SSH config means a support
ticket.

Firewall:

```bash
ufw allow OpenSSH
ufw allow 80
ufw allow 443
ufw enable
```

Nothing else is exposed. In particular Postgres (5432) and the app ports (8000,
3000, 3001) stay closed — they are reachable only from inside the Docker
network and from `localhost`.

Automatic security updates:

```bash
sudo apt update && sudo apt install -y unattended-upgrades
sudo dpkg-reconfigure --priority=low unattended-upgrades
```

### Docker

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker kls
newgrp docker
docker --version && docker compose version
```

---

## 2. DNS

Four A records, all pointing at the VPS IP:

| Name | Type | Value |
|---|---|---|
| `academy` | A | your IP |
| `admin` | A | your IP |
| `api` | A | your IP |
| `www` | A | your IP (if you want it) |

If you use Cloudflare, set these to **DNS only** (grey cloud) until TLS is
issued in §5. Proxying before the certificate exists makes Let's Encrypt's
HTTP-01 challenge fail in a way whose error message does not mention
Cloudflare, and you will lose an hour to it.

Wait for propagation before continuing:

```bash
dig +short api.klstechsolutions.in
```

---

## 3. Get the code onto the server

```bash
sudo mkdir -p /srv/kls && sudo chown kls:kls /srv/kls
cd /srv/kls
git clone <your-remote>/kls-api.git
git clone <your-remote>/KLS-academy.git
git clone <your-remote>/KLS-admin-dashboard.git
```

---

## 4. Configuration

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

DATABASE_URL=postgresql+psycopg://kls:<DB_PASSWORD>@db:5432/kls_academy
SECRET_KEY=<SECRET_KEY>

# HTTPS only. The app refuses to start with a plain-http origin in production.
CORS_ORIGINS=https://academy.klstechsolutions.in,https://admin.klstechsolutions.in

MINIMUM_AGE=18

R2_ACCOUNT_ID=...
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_BUCKET=kls-academy

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
super-admin password. If the container exits immediately after start, read the
first ten lines of its log — the reason will be there in plain English.

### Frontend environment

Both frontends need `API_BASE_URL` pointing at the API, server-side only:

```ini
# /srv/kls/KLS-academy/.env.production
API_BASE_URL=https://api.klstechsolutions.in/api/v1
NEXT_PUBLIC_MIXPANEL_TOKEN=      # optional; empty disables analytics entirely
```

The JWT never reaches client JavaScript — the browser talks to the Next route
handlers, which hold httpOnly cookies and proxy to the API. `API_BASE_URL` is
therefore deliberately not `NEXT_PUBLIC_`.

---

## 5. Reverse proxy and TLS

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
	reverse_proxy localhost:8000
}

academy.klstechsolutions.in {
	reverse_proxy localhost:3000
}

admin.klstechsolutions.in {
	reverse_proxy localhost:3001
}
```

```bash
sudo systemctl reload caddy
```

Certificates are issued on first request to each name and renewed
automatically. If issuance fails, `journalctl -u caddy -n 50` says why; it is
almost always DNS not yet propagated, or a proxy in front.

Once TLS is working, turn Cloudflare's orange cloud back on if you want it, and
set SSL mode to **Full (strict)**.

---

## 6. Bring it up

The compose file in the repository is the development one — it mounts source
directories and runs uvicorn with `--reload`. Create a production override
beside it:

`/srv/kls/docker-compose.prod.yml`

```yaml
services:
  db:
    image: postgres:17-alpine
    restart: unless-stopped
    environment:
      POSTGRES_USER: kls
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_DB: kls_academy
    volumes:
      - postgres_data:/var/lib/postgresql/data
    # No ports section. Postgres is reachable only from this network.
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U kls -d kls_academy"]
      interval: 10s
      timeout: 5s
      retries: 10

  api:
    build: ./kls-api
    restart: unless-stopped
    depends_on:
      db:
        condition: service_healthy
    env_file: ./kls-api/.env
    # Bound to localhost, so only Caddy can reach it.
    ports: ["127.0.0.1:8000:8000"]
    command: >
      sh -c "alembic upgrade head &&
             uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2"

  academy:
    build: ./KLS-academy
    restart: unless-stopped
    env_file: ./KLS-academy/.env.production
    ports: ["127.0.0.1:3000:3000"]
    depends_on: [api]

  admin:
    build: ./KLS-admin-dashboard
    restart: unless-stopped
    env_file: ./KLS-admin-dashboard/.env.production
    environment:
      PORT: 3001
    ports: ["127.0.0.1:3001:3001"]
    depends_on: [api]

volumes:
  postgres_data:
```

```bash
cd /srv/kls
echo "DB_PASSWORD=<DB_PASSWORD>" > .env && chmod 600 .env
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
```

Migrations run as part of the API's start command, so `alembic upgrade head`
happens automatically on every deploy. To run it by hand:

```bash
docker compose -f docker-compose.prod.yml exec api alembic upgrade head
docker compose -f docker-compose.prod.yml exec api alembic current
```

### Create the first super admin

```bash
docker compose -f docker-compose.prod.yml exec api python scripts/seed.py
```

This reads `FIRST_SUPERADMIN_EMAIL` and `FIRST_SUPERADMIN_PASSWORD` from the
environment. Sign in at `admin.klstechsolutions.in` and **change the password
immediately**, then do §9 before you do anything else.

---

## 7. Verify the deployment

Do all of these. Each one has failed at least once in a way the others did not
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
```

Then, in a browser:

- [ ] Register an account. **The verification email arrives** — check Spam,
      Junk and Bin before concluding it did not.
- [ ] The link in that email signs you in, rather than landing on a "check your
      inbox" page.
- [ ] Registration refuses a date of birth under 18, with an explanation.
- [ ] Enrol in a domain; the offer letter PDF downloads and opens.
- [ ] Submit a task from the student side; it appears in the admin queue.
- [ ] Approve the last task; the certificate is issued immediately.
- [ ] The QR code on that certificate resolves to the public verification page.
- [ ] Paste the certificate number into `/verify` — it validates and is found.
- [ ] Reset your password; confirm the old session is signed out.
- [ ] Close the test account, then confirm the certificate still verifies.

Delete the test account's leftovers afterwards, or leave it — it is now an
anonymous shell either way.

---

## 8. Backups

**A backup you have never restored is a hypothesis.** This section is not done
until §8.3 has actually been run.

### 8.1 Nightly dump

`/srv/kls/backup.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

STAMP=$(date -u +%Y%m%dT%H%M%SZ)
DIR=/srv/kls/backups
mkdir -p "$DIR"

docker compose -f /srv/kls/docker-compose.prod.yml exec -T db \
  pg_dump -U kls -Fc kls_academy > "$DIR/kls_$STAMP.dump"

# Off the server. A backup on the same disk as the database protects against
# exactly one failure mode — a bad DELETE — and none of the others.
rclone copy "$DIR/kls_$STAMP.dump" r2:kls-backups/

# Keep a fortnight locally.
find "$DIR" -name 'kls_*.dump' -mtime +14 -delete
```

```bash
chmod +x /srv/kls/backup.sh
```

Configure `rclone` for the R2 bucket (`rclone config`, S3 provider,
Cloudflare), then schedule it:

```bash
crontab -e
# 02:30 UTC = 08:00 IST — after the quiet hours, before the day starts.
30 2 * * * /srv/kls/backup.sh >> /srv/kls/backup.log 2>&1
```

### 8.2 Also back up

- `/srv/kls/kls-api/.env` — encrypted, into the password manager, not R2
- The R2 bucket itself. Uploaded screenshots and PDFs are not in the database.
  Enable versioning on the bucket.

### 8.3 Rehearse a restore — do this once, now

```bash
# A scratch database beside the real one
docker compose -f docker-compose.prod.yml exec db createdb -U kls restore_test
docker compose -f docker-compose.prod.yml exec -T db \
  pg_restore -U kls -d restore_test < /srv/kls/backups/<latest>.dump

docker compose -f docker-compose.prod.yml exec db \
  psql -U kls -d restore_test -c "select count(*) from users;"
docker compose -f docker-compose.prod.yml exec db \
  psql -U kls -d restore_test -c "select count(*) from certificates;"

docker compose -f docker-compose.prod.yml exec db dropdb -U kls restore_test
```

If those counts are right, you have a backup. If the restore errored, you found
that out on a Tuesday afternoon instead of during an incident, which is the
entire point of doing it now.

Write the date you did this at the bottom of this file.

---

## 9. Access — do not skip this

Right now, one person can do everything and nobody else can do anything. That
is a single point of failure wearing a hat.

- [ ] Put every credential in a shared password manager: SSH key, VPS console
      login, DNS, R2 token, SMTP, `SECRET_KEY`, database password, super-admin
      login.
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
3. **Disk space.** Postgres and Docker images fill a small VPS quietly.
   ```bash
   df -h /
   docker system df
   ```
4. **Logs**, when something is wrong:
   ```bash
   docker compose -f docker-compose.prod.yml logs -f api --tail 200
   journalctl -u caddy -n 100
   ```

---

## 11. Deploying a change

```bash
cd /srv/kls/<repository>
git pull
cd /srv/kls
docker compose -f docker-compose.prod.yml up -d --build <service>
```

Migrations run automatically as the API starts.

**Take a dump before any deploy that includes a migration:**

```bash
/srv/kls/backup.sh
```

There is a short outage while a container restarts — seconds for the API,
rather longer for a frontend that has to build. Deploy when nobody is
mid-submission.

### Rolling back

Code:

```bash
cd /srv/kls/<repository>
git log --oneline -5
git checkout <previous-commit>
cd /srv/kls && docker compose -f docker-compose.prod.yml up -d --build <service>
```

A migration:

```bash
docker compose -f docker-compose.prod.yml exec api alembic downgrade -1
```

Every migration in this project has a tested `downgrade()` — CI runs the whole
chain forward, back to base, and forward again on every push, so a reversal is
not a leap of faith. It is still not free: a downgrade that drops a column
drops the data in it. Prefer restoring from the dump you took five minutes
earlier if any real data has been written since.

---

## 12. When something is wrong

| Symptom | Look here first |
|---|---|
| API container exits at once | `docker compose logs api` — config validation says exactly what is wrong |
| 502 from Caddy | The container behind it is down or still starting: `docker compose ps` |
| TLS not issuing | `journalctl -u caddy` — usually DNS, or a proxy in front of the challenge |
| Emails not arriving | `email_logs` table shows whether we sent; then check the recipient's spam folder |
| Everyone logged out at once | `SECRET_KEY` changed, or a `token_version` bump; check what was deployed |
| Uploads failing | R2 credentials, then bucket name, then the object size limit |
| Slow, no obvious cause | `docker stats`, then `df -h` — a full disk presents as generic slowness |

### Emergency: end every session immediately

If credentials are believed compromised, changing `SECRET_KEY` in `.env` and
restarting the API invalidates every token in existence at once. Everyone is
signed out and signs back in. It is blunt, instant, and reversible only in the
sense that people can log in again.

---

## 13. Recurring

**Weekly**

- [ ] A backup file actually landed in R2 for each of the last seven days
- [ ] `df -h` — disk under 80%
- [ ] Sentry: anything new and repeating

**Monthly**

- [ ] `sudo apt update && sudo apt upgrade`
- [ ] `docker system prune -f` (images only; the volume holds the database)
- [ ] Dependency audit — CI runs one on every push; read it
- [ ] **Rehearse the restore again.** Backups rot silently.

**Quarterly**

- [ ] Rotate the R2 and SMTP credentials
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
