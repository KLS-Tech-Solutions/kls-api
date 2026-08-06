# KLS Academy — API

FastAPI backend for the KLS Academy virtual internship platform. **One backend and one
database serve both frontends** — `academy.klstechsolutions.in` (students) and
`admin.klstechsolutions.in` (reviewers).

`docs/API_CONTRACT.md` is the authoritative contract. Both frontends build against it.

---

## Run it

You need **Docker Desktop**. Nothing else — Postgres comes up in the compose stack.

```bash
cp .env.example .env          # then set SECRET_KEY
docker compose up             # Postgres + API, migrations run automatically
docker compose exec api python scripts/seed.py
```

- API — http://localhost:8000
- Interactive docs — http://localhost:8000/docs
- Postgres — `localhost:5432`, user `kls`, password `kls_dev_password`

Generate a real secret before anything leaves your laptop:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### Without Docker

```bash
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
# point DATABASE_URL at a Postgres you're running, then:
alembic upgrade head
python scripts/seed.py
uvicorn app.main:app --reload
```

---

## Layout

```
app/
├── core/          config, database, security (JWT + argon2), RBAC dependencies
├── models/        SQLAlchemy — 20 tables from the v2 schema doc
├── schemas/       Pydantic request and response models
├── api/v1/        auth · public · student · enrollment · admin routers
├── services/      journey engine, aggregate builder, storage, numbering, notifications
└── main.py
alembic/           migrations
scripts/seed.py    catalogue + first super admin
tests/             17 tests, including a full journey walkthrough
docs/              the API contract
```

---

## The journey engine — read this first

`app/services/journey.py` computes a single `stage` value:

```
not_enrolled → enrolled → offer_letter_generated → linkedin_submitted
→ linkedin_approved → tasks_in_progress → all_tasks_approved
→ payment_pending → paid → certificate_issued
```

**It is derived on every read, never stored.** A stored stage would drift the moment an
approval is reversed, a payment fails after the fact, or a certificate is revoked.
Deriving it means the value cannot lie.

`GET /me/journey` returns that stage plus everything the dashboard needs in one round
trip. **Both frontends render locks from `stage` alone and never infer it** — so if a
transition is wrong here, a student is stuck with no way forward.

`GET /admin/students/{id}` returns the identical shape, which is why the admin app can
reuse the same TypeScript types.

---

## Business rules enforced server-side

Frontend validation is a convenience. These are the rules that actually hold:

| Rule | Where |
| --- | --- |
| One active internship per student | `POST /enrollments` → 409 |
| Offer letter generated on enrolment | `POST /enrollments`, same transaction |
| Technical tasks locked until LinkedIn is approved | `POST /task-submissions` → 403 |
| Tasks are sequential — previous must be approved | `POST /task-submissions` → 403 |
| 3–8 screenshots, PNG/JPG/WebP, ≤5 MB each | `POST /task-submissions` → 422 |
| Payment locked until every task is approved | `POST /payments/order` → 403 |
| Certificate only after successful payment | Phase 6 |
| Revoked certificates fail public verification | `GET /certificates/verify/{n}` → 404 |
| Catalogue changes are super-admin only | `get_current_super_admin` |

Task counts are **variable per domain** — the seed creates 3–4 technical tasks depending
on the domain. `order_number` 0 is reserved for the LinkedIn onboarding task.

---

## Roles

| Capability | student | admin | super_admin |
| --- | :---: | :---: | :---: |
| Own journey, submissions, payment | ✅ | — | — |
| Review LinkedIn and task submissions | — | ✅ | ✅ |
| View students, payments, certificates | — | ✅ | ✅ |
| Domain / batch / task CRUD | — | ❌ | ✅ |
| Revoke certificates, read activity logs | — | ❌ | ✅ |

---

## Tests

```bash
pytest
```

17 tests on SQLite — no Postgres needed. `tests/test_journey.py` walks one student from
registration to paid, asserting the stage after every step and checking that premature
submissions, out-of-order tasks, duplicate enrolments and early payment are all refused.

---

## Storage and payments degrade gracefully

- **No R2 credentials?** Uploads write to `./media` so the API runs on a laptop.
- **No Razorpay keys?** `/payments/order` returns a development order id so the flow can
  be exercised end to end. Signature verification switches on automatically once
  `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET` are set.

---

## Not built yet

- **Offer letter and certificate PDFs** (Phase 6). WeasyPrint and qrcode are already in
  `requirements.txt`; `app/services/storage.py` has `save_document()` ready. Certificate
  issuance hooks in at the end of `POST /payments/verify`.
- **Email delivery** (Phase 8). In-app notifications are written on every workflow event;
  `email_templates` and `email_logs` tables exist and are unused.
- **Razorpay webhook** for reconciling payments that complete out of band.

---

## Connecting the frontends

In `academy/.env.local`:

```bash
NEXT_PUBLIC_USE_MOCKS=false
API_BASE_URL=http://localhost:8000/api/v1
```

The student app talks to FastAPI through its own Next proxy so the JWT stays in an
httpOnly cookie. The admin app should do the same.
