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

Full step-by-step for Windows + local Postgres + pgAdmin: **`docs/LOCAL_SETUP.md`**.

```bash
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env         # set DATABASE_URL, SECRET_KEY, superadmin credentials
alembic upgrade head         # creates all 20 tables
python scripts/seed.py
uvicorn app.main:app --reload
```

**Never create the tables by hand.** `alembic upgrade head` builds them to match the
models exactly and records the version so later changes are incremental.
`docs/schema.sql` is a generated fallback for environments where Alembic cannot run.

---

## Layout

```
app/
├── core/          config, database, security (JWT + argon2), RBAC dependencies
├── models/        SQLAlchemy — 20 tables from the v2 schema doc
├── schemas/       Pydantic request and response models
├── api/v1/        auth · public · student · enrollment · admin · admins routers
├── services/      journey engine, aggregate, documents, email, storage, numbering
├── templates/     offer letter and certificate HTML + print CSS
├── static/brand/  logos inlined into generated documents
└── main.py
alembic/           migrations
scripts/seed.py    catalogue + first super admin
tests/             88 tests, including a full journey walkthrough
docs/              API contract · local setup · external services · status
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
| One internship at a time, until it is certificated | `POST /enrollments` → 409 |
| The same batch cannot be taken twice | `POST /enrollments` → 409 |
| Offer letter generated on enrolment | `POST /enrollments`, same transaction |
| Technical tasks locked until LinkedIn is approved | `POST /task-submissions` → 403 |
| Tasks are sequential — previous must be **submitted** (not approved) | `POST /task-submissions` → 403 |
| 3–8 screenshots, PNG/JPG/WebP, ≤5 MB each | `POST /task-submissions` → 422 |
| Payment locked until every task is approved | `POST /payments/order` → 403 |
| Certificate only after successful payment | `POST /payments/verify` |
| Per-task submission rules (screenshots, GitHub, explanation) | `POST /task-submissions` → 422 |
| Revoked certificates fail public verification | `GET /certificates/verify/{n}` → 404 |
| Catalogue changes are super-admin only | `get_current_super_admin` |
| Changing the certificate fee is super-admin only | `PATCH /admin/settings/certificate-fee` |
| A closed account cannot sign in or be recovered by email | `UserStatus.DELETED` |

The next task unlocks as soon as the previous one is **submitted**, so review latency
never stalls a student. Approval still gates the certificate: `all_tasks_approved`
requires every submission to be signed off.

## More than one internship

A student may take another internship **once the current one is certificated** —
finished *and* paid for. Anything earlier and they would abandon a half-done journey.

**Everything the journey reports is scoped to the current enrolment.** This is the part
that breaks quietly: every query used to read by `student_id` alone, which was correct
while a student could only hold one enrolment. The moment they can hold two, a
student-wide certificate lookup makes a brand new internship report `certificate_issued`
on day one. `compute_stage`, `build_journey`, `_issue_certificate` and the LinkedIn
gate are all scoped now, and `tests/test_second_internship.py` pins it down.

`journey.history` carries every internship taken, newest first, each with its offer
letter and certificate URLs. Those stay downloadable for good, through
`GET /me/internships/{enrollment_id}/{offer-letter,certificate}/download` — a student
paid for the credential and does not lose access to it by moving on.

---

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

88 tests on SQLite — no Postgres needed. `tests/test_journey.py` walks one student from
registration to paid, asserting the stage after every step and checking that premature
submissions, out-of-order tasks, duplicate enrolments and early payment are all refused.

---

## Runtime settings

`platform_settings` is a key/value table for operational levers a super admin can change
without a deploy. Currently one key: `certificate_fee_paise`.

Each reader falls back to the `.env` value when the row does not exist, so a fresh
database behaves exactly as it did before the table existed and seeding is not mandatory.

**A payment keeps the price it was quoted.** `Payment.amount` is written at order time
and never re-read, so a fee change mid-checkout cannot reprice an in-flight order.

## Closing an account

`DELETE /me/account` takes the current password — it is irreversible, and an unattended
session should not be enough to trigger it.

It is a **soft delete**. The user row survives as an anonymous shell so issued
certificates keep a valid foreign key and stay publicly verifiable; an employer's
verification link must not start 404ing because the student later closed their account.
Removed: name, phone, the whole student profile, the password, and every outstanding
email token. The address is replaced with `deleted+<id>@account.invalid`, which also
releases the real one for re-registration.

`Certificate.student_name` snapshots the recipient at issue for exactly this reason —
without it, a scrubbed user row would make a paid-for credential verify as "Deleted
user".

## Storage and payments degrade gracefully

- **No R2 credentials?** Uploads write to `./media` so the API runs on a laptop.
- **No Razorpay keys?** `/payments/order` returns a development order id so the flow can
  be exercised end to end. Signature verification switches on automatically once
  `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET` are set.

---

## Documents

Offer letters and certificates are generated automatically:

- **Enrolling** creates the offer letter — number, PDF, stored URL — in the same
  transaction as the enrolment record.
- **A successful payment** issues the certificate, generates a QR code pointing at
  `/verify/{number}` on the academy site, and marks the enrolment complete.

`app/services/documents.py` renders both with **ReportLab** — pure Python with prebuilt
wheels, so it works on Windows, macOS and Linux with no system libraries. WeasyPrint was
replaced because it needs GTK, which does not install cleanly on Windows and silently
downgraded documents to HTML.

**Only the base-14 fonts are used** (Helvetica and Times). Shipping a font file would
look marginally nicer and introduce a whole class of "why does the server output differ"
bugs. A document renders identically on a developer's Windows machine and on the VPS.

The **offer letter** is A4 portrait: a navy→blue letterhead band, a *Programme at a
glance* table, a terms panel, and the company seal. The **certificate** is A4 landscape
with a navy and gold frame, the seal ghosted at 4% as a watermark, and a QR pointing at
the public verification page. Assets live in `app/static/brand/`.

**Neither document carries a signature line.** Both are issued electronically and state
so, directing anyone who needs to check to the QR code or the verification cell. A
printed "Authorised Signatory" on a document nobody signed is worse than none at all.
`tests/test_documents.py` asserts this, along with the absence of the fee amount, and
that long names and domain titles are shrunk or ellipsised rather than allowed to run
through the border.

**Downloads regenerate on demand.** `GET /me/offer-letter/download` and
`GET /me/certificate/download` re-render the PDF if the stored file is missing or is not
a PDF, then stream it. The database record is the source of truth; the file is a
rendering of it, so a lost file is never a lost document.

## Administrator invitations

`POST /admin/admins/invite` creates a **pending** account with an unusable random
password hash and a 7-day single-use link. The invitee sets their own password at
`/accept-invite?token=…` on the admin console, so **no working credential is ever
transmitted**. Re-inviting the same address invalidates the previous link.

Guards: a super admin cannot change their own role or status, and the last active super
admin cannot be suspended — the platform can never be locked out of itself.

## Email

Ten workflow emails, all through `app/services/email.py`:

| Event | Email |
| --- | --- |
| Registration | Verify your email — 24-hour link |
| Resend verification | A fresh link; the previous one is invalidated |
| Forgot password | Reset link — 30 minutes, single use |
| Enrolment | Offer letter ready, with the LinkedIn next step |
| LinkedIn approved / rejected | Reviewer's remarks, verbatim |
| Task approved / rejected | Remarks, and whether this was the last task |
| Payment received | Receipt with the transaction id |
| Certificate issued | Number, download link and verification URL |
| Admin invitation | Set-your-own-password link |

**Every message carries a "check your Spam, Junk or Bin folder" note** and a plain-text
alternative alongside the HTML — some clients and filters reject HTML-only mail.

Delivery runs in a **background task**, so a slow SMTP handshake never delays a student's
request, and it is wrapped so that **a failure never breaks a workflow**: an enrolment
still succeeds if email is down. Every attempt is recorded in `email_logs`, and the
in-app notification is always written regardless.

Set `SMTP_HOST` and the rest of the `SMTP_*` values — see `docs/EXTERNAL_SERVICES.md`.
With them unset, emails are composed and logged but not sent.

## Not built yet

- **Razorpay browser checkout and webhook.** Order creation and signature verification
  are done; the `checkout.js` step between them is not.

---

## Connecting the frontends

In `academy/.env.local`:

```bash
API_BASE_URL=http://localhost:8000/api/v1
```

There is no mock mode in either frontend — both read only from this API.

The student app talks to FastAPI through its own Next proxy so the JWT stays in an
httpOnly cookie. The admin app should do the same.
