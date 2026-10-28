# Deploying the MVP on Oracle Cloud Always Free

A single Always Free VM runs the whole platform — the API and both frontends —
at no cost, indefinitely. The database is already on Supabase, so this machine
only has to run three services and hold the media directory.

**This document covers the Oracle-specific parts only.** Once the VM exists and
you can SSH to it, go to `docs/DEPLOYMENT.md` and follow it from §1 — it is
written for exactly this shape of deployment. The differences are listed in §5
below.

---

## Why this host

Your backend writes every PDF and screenshot to `MEDIA_ROOT` on local disk.
Free platform-as-a-service tiers — Render, Railway and the rest — give you an
**ephemeral filesystem**: it is wiped on every restart and redeploy.

For this application that means offer letters and certificates survive (they
regenerate from their database record on the next download), but the 18 chapter
PDFs have to be re-seeded by hand, and **student task screenshots are lost
permanently**. A real VM with a real disk removes that whole category of
problem.

---

## 1. What Always Free gives you

**Check the current numbers in your own console before planning around them.**
Oracle reduced the Ampere allowance around June 2026 and its own pages were
inconsistent about it for a while — some sources report 2 OCPUs and 12 GB,
others still show the older 4 OCPUs and 24 GB.

Either figure is comfortably more than this platform needs. Two ARM cores and
12 GB of RAM will run the API, both Next.js servers and Caddy without noticing.

You also get 200 GB of block storage across the tenancy, which is far more
media than you will produce for a long while.

Oracle asks for a card to verify identity. Always Free resources are not
charged, but **do not upgrade to Pay As You Go** unless you mean to — once
upgraded, resources beyond the free allowance start billing.

---

## 2. Create the instance

1. Sign up at cloud.oracle.com. **Choose your home region carefully** — it is
   effectively permanent, and capacity varies a lot between regions. For India,
   Mumbai or Hyderabad; pick the same region as your Supabase project if you
   can, to keep database latency low.
2. Compute → Instances → **Create instance**.
3. Image: **Ubuntu 24.04**.
4. Shape: **Ampere / VM.Standard.A1.Flex**, then set OCPUs and memory to
   whatever your tenancy's Always Free limit allows.
5. Add your SSH public key. Generate one first if you have none:
   ```powershell
   ssh-keygen -t ed25519 -C "kls-deploy"
   # then paste the contents of C:\Users\Lenovo\.ssh\id_ed25519.pub
   ```
6. Create.

### If you get "Out of host capacity"

This is the single most common friction with Always Free and it is not your
fault — Oracle has no free ARM capacity in that availability domain at that
moment. Oracle's own guidance is to try another availability domain in the same
region if one exists, or to wait and retry; capacity can take days to return.

What actually works:

- Retry at a different time of day. Capacity frees up unpredictably.
- Try each availability domain in your region in turn.
- If you need the MVP up this week and keep hitting it, fall back to a small
  paid VPS — a Hetzner CX22 is around ₹350/month and provisions instantly. Every
  other instruction in `docs/DEPLOYMENT.md` applies unchanged.

---

## 3. Open the network — both halves

This trips up nearly everyone on Oracle, because there are **two** firewalls and
opening only one leaves the server silently unreachable.

### 3.1 The cloud security list

Networking → Virtual Cloud Networks → your VCN → Subnet → Security List →
**Add Ingress Rules**:

| Source CIDR | Protocol | Destination port |
|---|---|---|
| `0.0.0.0/0` | TCP | 80 |
| `0.0.0.0/0` | TCP | 443 |

Port 22 is already open from the default rules.

### 3.2 The instance's own iptables

**Oracle's Ubuntu images ship with iptables rules that drop inbound traffic**,
regardless of what the security list says. If you skip this, ports 80 and 443
appear open in the console and time out from the internet, and you will spend an
hour blaming DNS.

```bash
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save
```

If `netfilter-persistent` is missing: `sudo apt install -y iptables-persistent`.

Verify from your own machine before going further:

```powershell
curl -v http://<your-public-ip>
```

A connection refused is fine at this stage — nothing is listening yet. A
**timeout** means the firewall is still blocking and §3.2 did not take.

---

## 4. ARM, briefly

Ampere is `aarch64`, not x86. For this project that is a non-issue: every
dependency ships ARM wheels, and the PDF renderer is pure Python with no system
libraries by design.

Install the build toolchain anyway, so that if any wheel is missing for ARM, pip
can compile it rather than failing:

```bash
sudo apt install -y build-essential python3-dev libpq-dev
```

---

## 5. Now follow the main runbook — with three changes

Go to `docs/DEPLOYMENT.md` and work through it from §1. Three differences:

**Skip §3 entirely (Database).** Your database is on Supabase. Do not install
PostgreSQL on this machine. Your `DATABASE_URL` is the Supabase session-pooler
string from `docs/SUPABASE.md`.

**In §5 (systemd), drop the Postgres dependency** from `kls-api.service`, since
there is no local Postgres to wait for:

```ini
[Unit]
Description=KLS Academy API
After=network.target
```

**In §8 (Backups), the database half now points at Supabase.** The script in the
runbook already uses `$DATABASE_URL`, so it needs no edit — but understand what
changed: Supabase's free plan takes **no automatic backups**, so that nightly
dump is now the only copy of your database. The media archive in the same script
is the only copy of your uploads. Rehearse the restore (§8.3).

---

## 6. Keep the Supabase project awake

A free Supabase project with no database activity for 7 days is paused and has
to be restored by hand. Once the API is reachable, point an uptime monitor at
`https://api.klstechsolutions.in/health` every 5 minutes — UptimeRobot's free
tier is enough. That both keeps Supabase active and tells you when the site is
down, which is §10 of the runbook anyway.

---

## 7. A note on the frontends

Both Next.js apps run on this VM as systemd services, which is what
`docs/DEPLOYMENT.md` §5 sets up. You do **not** need Vercel.

That is deliberate. Vercel's Hobby plan is limited to non-commercial personal
use, and the definition is broad enough to cover a product built by an
organisation — Vercel can disable a Hobby deployment at its discretion. Running
them yourself avoids the question entirely. If you later want a CDN in front,
Cloudflare's free plan proxies your domain without that restriction.

---

## Checklist

- [ ] Instance created, SSH works
- [ ] Security list has 80 and 443
- [ ] **iptables rules added and saved** (§3.2)
- [ ] DNS A records point at the public IP (runbook §2)
- [ ] `docs/DEPLOYMENT.md` §1, §2, §4–§7 followed, §3 skipped
- [ ] `/srv/kls/media` exists and is outside the code tree
- [ ] `DATABASE_URL` is the Supabase pooler string with `?sslmode=require`
- [ ] Uptime monitor on `/health`
- [ ] Nightly backup running, and one restore rehearsed

---

## Sources

Free-tier terms change. Verify in your own console before planning around them.

- [Oracle Cloud Free Tier FAQ](https://www.oracle.com/cloud/free/faq/)
- [Oracle quietly cuts free tier Ampere A1 resources in half](https://linuxiac.com/oracle-quietly-cuts-free-tier-ampere-a1-resources-in-half/)
- [OCI free tier breakdown](https://fullmetalbrackets.com/blog/oci-free-tier-breakdown)
- [Vercel Hobby fair use: non-commercial only](https://convika.com/compare/vercel-hobby-commercial-use/)
