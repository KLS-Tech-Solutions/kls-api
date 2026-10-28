# KLS Academy — API

**Open source and free.** There is no payment step anywhere in this platform — a
student enrols, does the work, and the certificate is issued the moment a reviewer
approves their final task. MIT licensed; the KLS brand assets in `app/static/brand/`
are not.

FastAPI backend for the KLS Academy virtual internship platform. **One backend and one
database serve both frontends** — `academy.klstechsolutions.in` (students) and
`admin.klstechsolutions.in` (reviewers).

`docs/API_CONTRACT.md` is the authoritative contract. Both frontends build against it.

---

## Run it

You need **Python 3.12** and a **PostgreSQL 17** server. Nothing is containerised —
the API runs directly, in a virtual environment.

```bash
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env         # set DATABASE_URL, SECRET_KEY, superadmin credentials
alembic upgrade head         # creates every table
python scripts/seed.py       # first super admin + email template rows
uvicorn app.main:app --reload
```

- API — http://localhost:8000
- Interactive docs — http://localhost:8000/docs

Generate a real secret before anything leaves your laptop:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Full step-by-step for Windows + local Postgres + pgAdmin: **`docs/LOCAL_SETUP.md`**.
Deploying to a server: **`docs/DEPLOYMENT.md`**.

**Never create the tables by hand.** `alembic upgrade head` builds them to match the
models exactly and records the version so later changes are incremental.
`docs/schema.sql` is a generated fallback for environments where Alembic cannot run.

`tests/test_migrations.py` builds a database by **running the migrations** and compares
it against the models. Every other test uses `Base.metadata.create_all()`, which reads
the models — so a migration that disagrees with them used to pass every test and fail in
production. It did, once: `learning_chapters.created_at` was created NOT NULL with no
column default while `TimestampMixin` relies on the database to fill it, and every insert
failed.

---

## Layout

```
app/
├── core/          config, database, security (JWT + argon2), RBAC dependencies
├── models/        SQLAlchemy — 20 tables from the v2 schema doc
├── schemas/       Pydantic request and response models
├── api/v1/        auth · public · student · enrollment · learning · admin · admins
├── services/      journey engine, aggregate, documents, email, storage, numbering
├── templates/     offer letter and certificate HTML + print CSS
├── static/brand/  logos inlined into generated documents
└── main.py
alembic/           migrations
scripts/seed.py    catalogue + first super admin
tests/             134 tests, including a full journey walkthrough
docs/              API contract · local setup · external services · status
```

---

## The journey engine — read this first

`app/services/journey.py` computes a single `stage` value:

```
not_enrolled → enrolled → offer_letter_generated → linkedin_submitted
→ linkedin_approved → tasks_in_progress → all_tasks_approved
→ certificate_issued
```

**It is derived on every read, never stored.** A stored stage would drift the moment an
approval is reversed or a certificate is revoked.
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
| Certificate issued when the final task is approved | `POST /admin/task-submissions/{id}/review` |
| Per-task submission rules (screenshots, GitHub, explanation) | `POST /task-submissions` → 422 |
| Revoked certificates fail public verification | `GET /certificates/verify/{n}` → 404 |
| Catalogue changes are super-admin only | `get_current_super_admin` |
| Study notes are managed by **any** admin | `POST /admin/chapters` |
| A closed account cannot sign in or be recovered by email | `UserStatus.DELETED` |

The next task unlocks as soon as the previous one is **submitted**, so review latency
never stalls a student. Approval still gates the certificate: `all_tasks_approved`
requires every submission to be signed off.

## More than one internship

A student may take another internship **once the current one is certificated**.
Anything earlier and they would abandon a half-done journey to start another.

**Everything the journey reports is scoped to the current enrolment.** This is the part
that breaks quietly: every query used to read by `student_id` alone, which was correct
while a student could only hold one enrolment. The moment they can hold two, a
student-wide certificate lookup makes a brand new internship report `certificate_issued`
on day one. `compute_stage`, `build_journey`, `_issue_certificate` and the LinkedIn
gate are all scoped now, and `tests/test_second_internship.py` pins it down.

`journey.history` carries every internship taken, newest first, each with its offer
letter and certificate URLs. Those stay downloadable for good, through
`GET /me/internships/{enrollment_id}/{offer-letter,certificate}/download` — a student
earned the credential and does not lose access to it by moving on.

---

Task counts are **variable per domain** — the seed creates 3–4 technical tasks depending
on the domain. `order_number` 0 is reserved for the LinkedIn onboarding task.

---

## Roles

| Capability | student | admin | super_admin |
| --- | :---: | :---: | :---: |
| Own journey, submissions, certificate | ✅ | — | — |
| Review LinkedIn and task submissions | — | ✅ | ✅ |
| View students and certificates | — | ✅ | ✅ |
| Study notes CRUD and PDF upload | — | ✅ | ✅ |
| Domain / batch / task CRUD | — | ❌ | ✅ |
| Revoke certificates, read activity logs | — | ❌ | ✅ |

---

## Tests

```bash
pytest
```

134 tests on SQLite — no Postgres needed. `tests/test_journey.py` walks one student from
registration to certificated, asserting the stage after every step and checking that
premature submissions, out-of-order tasks and duplicate enrolments are all refused.

---


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
without it, a scrubbed user row would make an earned credential verify as "Deleted
user".

## Storage

**Nothing is served from a public URL.** Offer letters, certificates, task
screenshots and study notes are all read back through authenticated routes that check
who is asking. What is stored in the database is an opaque key, never a link.

That is a change from the original design, which used a public bucket with sequential
filenames — anyone holding one certificate URL could increment the number and download
every student's documents. Numbers are random now as well, but the bucket being private
is the actual fix.

- **Where do uploads go?** To `MEDIA_ROOT` on local disk (`./media` by default). There
  is no object store; in production point this outside the code directory. The
  directory is not mounted for static serving.

---

## Documents

Offer letters and certificates are generated automatically:

- **Enrolling** creates the offer letter — number, PDF, stored URL — in the same
  transaction as the enrolment record.
- **Approving the final task** issues the certificate, generates a QR code pointing at
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

- Nothing outstanding for the core flow.

---

## Connecting the frontends

In `academy/.env.local`:

```bash
API_BASE_URL=http://localhost:8000/api/v1
```

There is no mock mode in either frontend — both read only from this API.

The student app talks to FastAPI through its own Next proxy so the JWT stays in an
httpOnly cookie. The admin app should do the same.


---

## Study notes

Each internship domain carries an ordered set of chapters — beginner to advanced —
that students work through before starting the technical tasks. A super admin adds
chapters and uploads a PDF per chapter at **Catalogue → Study notes**.

Chapters belong to the **domain**, not the batch, so material is uploaded once and
every cohort of that domain gets it.

**Any admin manages them**, not only super admins. Whoever reviews a domain's
submissions is best placed to fix its chapters, and routing that through one person is
how material goes stale. The catalogue itself — domains, batches, tasks — stays
super-admin only, because changing a batch mid-flight moves the goalposts for students
already enrolled. `learning_chapters.updated_by` records who last touched each chapter.

**Nothing is gated on the notes.** The tasks page prompts, and a student who ignores
them entirely can still submit. A hard gate would produce support requests from
people who learned the material elsewhere and cannot see why they are stuck — the
notes exist to make the internship feel prepared, not to police it.

`chapter_reads` records what a student has opened, which drives their progress bar
and tells admins whether the material is being used.

---

## Rate limiting

`app/core/ratelimit.py` guards login, registration, forgot-password and
resend-verification. Three problems, one mechanism: passwords guessable at machine
speed, the two email endpoints usable to flood someone's inbox, and — the one that
actually bites — those endpoints spending the daily email quota, at which point
genuine students stop receiving verification mail and cannot sign up at all.

It is an **in-process counter**, not Redis. The API runs as a single instance and a
datastore to defend a service this size is more moving parts than the problem
justifies. Scaling to several workers means moving this to shared state.

Enforcement is off under `ENVIRONMENT=test` because the suite signs in far more often
than any person would; `tests/test_learning_and_hardening.py` switches it back on to
prove the limits work.


---

## Continuous integration

`.github/workflows/ci.yml` runs on every push and pull request:

1. **Lint** with ruff.
2. **Migrations** applied, reversed to base, and applied again — against **PostgreSQL**,
   not SQLite.
3. **The full suite** on PostgreSQL.
4. **The seed script**, so a broken seed cannot reach main.

Point 2 and 3 matter more than they look. The suite runs on SQLite locally for speed,
and the two databases disagree in exactly the areas this codebase depends on. That gap
shipped a real bug once — see `tests/test_migrations.py`.

A separate advisory job runs `pip-audit`. It reports and does not block: a new CVE in a
transitive dependency should tell you, not stop you shipping an unrelated fix.
