# KLS Academy — API contract

What the frontend already calls. The FastAPI backend needs to implement these
endpoints with these shapes; nothing in the UI will need to change when it does.

**Base path:** `/api/v1` (set via `API_BASE_URL`)
**Auth:** `Authorization: Bearer <access_token>` on everything except the endpoints
marked *public*.

The browser never calls FastAPI directly. It calls `/api/proxy/*` on the Next server,
which attaches the JWT from an httpOnly cookie and forwards the request. So a frontend
call to `/me/journey` arrives at FastAPI as `GET /api/v1/me/journey`.

---

## Auth

| Method | Path | Body | Returns |
| --- | --- | --- | --- |
| POST | `/auth/register` *(public)* | `{ full_name, email, phone?, state, country, date_of_birth, password }` | `201 { email, email_verified: true, email_sent }` |
| POST | `/auth/login` *(public)* | `{ email, password }` | `{ access_token, refresh_token, expires_in, user }` |
| POST | `/auth/refresh` *(public)* | `{ refresh_token }` | `{ access_token, refresh_token, expires_in }` |
| POST | `/auth/logout` | — | `204` |
| GET | `/auth/me` | — | `{ user }` |
| POST | `/auth/forgot-password` *(public)* | `{ email }` | `204` — always, even for unknown emails |
| POST | `/auth/reset-password` *(public)* | `{ token, password }` | `204` |
| GET | `/auth/invite/{token}` *(public)* | — | `{ full_name, email, role }` · 400 if used/expired |
| POST | `/auth/accept-invite` *(public)* | `{ token, password }` | `204` — sets the password and activates |

`expires_in` is seconds. If omitted the frontend assumes 30 minutes.

**There is no email verification step.** `/auth/register` returns an account
that is already `active` and `email_verified`, and the student can sign in
immediately. The welcome email carries no link to click. `/auth/verify-email`
and `/auth/resend-verification` were removed; the academy app answers both with
410 and a sentence, for anyone holding an old link.

---

## Public catalogue

| Method | Path | Returns |
| --- | --- | --- |
| GET | `/internship-domains?status=active` | `InternshipDomain[]` |
| GET | `/internship-domains/{slug}` | `InternshipDomain` |
| GET | `/internship-batches` | `InternshipBatch[]` |
| GET | `/internship-batches?domain_id=` | `InternshipBatch` |
| GET | `/certificates/verify/{certificate_number}` *(public)* | `Certificate` · `404` when not found |
| POST | `/contact` *(public)* | `{ name, email, phone?, topic, message }` → `204` |

`/certificates/verify` is called **server-side** by the Next verification page so a
shared link is indexable. It must stay public and unauthenticated.

---

## Student

### The aggregate

```
GET /me/journey → StudentJourney
```

This is the most important endpoint. The dashboard renders from it in a single round
trip rather than eight separate calls. Shape:

```jsonc
{
  "stage": "tasks_in_progress",   // the journey state machine, see below
  "user": { ... },
  "profile": { ... },
  "domain": { ... } | null,
  "batch": { ... } | null,
  "enrollment": { ... } | null,
  "offerLetter": { ... } | null,
  "linkedinSubmission": { ... } | null,
  "tasks": [ ... ],
  "submissions": [ ... ],         // each with `screenshots[]` and `review` embedded
  "certificate": { ... } | null,
  "notifications": [ ... ],
  "history": [ ... ],              // every internship taken, newest first
  "can_enroll_again": false        // true once the current one is certificated
}
```

**Everything above except `history` describes the *current* internship.** A student may
take another once the current one is certificated, so `certificate`,
`submissions` and `linkedinSubmission` are all scoped to the current enrolment — a
second internship starts genuinely empty.

`history[]` entries carry `enrollment_id`, `domain_title`, `batch_name`, `status`,
`is_current`, `tasks_approved`/`tasks_total`, and the `offer_letter_url` /
`certificate_number` / `certificate_url` for that internship. Documents from every
internship stay downloadable for good.

`stage` must be one of, in order:

```
not_enrolled · enrolled · offer_letter_generated · linkedin_submitted
linkedin_approved · tasks_in_progress · all_tasks_approved
payment_pending · paid · certificate_issued
```

The frontend uses `stage` alone to decide what is locked. **The backend owns this
value** — the UI never infers it. Getting it wrong is the one thing that will break
the dashboard.

### The rest

| Method | Path | Body | Returns |
| --- | --- | --- | --- |
| POST | `/enrollments` | `{ domain_id, batch_id }` | `201 { enrollment_id }` · `409` if the current internship is not yet certificated, or if that batch was already taken |
| GET | `/me/tasks` | — | `Task[]` |
| POST | `/linkedin-submissions` | `{ linkedin_post_url }` | `201 { id, status: "pending" }` |
| POST | `/task-submissions` | **multipart** (below) | `201 { id, status: "under_review" }` |
| PATCH | `/me/profile` | `ProfileValues` | `StudentProfile` |
| GET | `/me/notifications` | — | `AppNotification[]` |
| PATCH | `/me/notifications/read` | `{ ids: string[] }` | `204` |
| GET | `/me/certificate` | — | `Certificate` for the **current** internship · `null` when not issued |
| GET | `/me/chapters` | — | `LearningChapter[]` for the current domain, with `is_read` |
| GET | `/me/chapters/{id}/download` | — | The chapter PDF |
| POST | `/me/chapters/{id}/read` | — | `204` · idempotent |
| GET | `/screenshots/{id}` | — | Image bytes · owner or any admin, `404` otherwise |
| GET | `/me/offer-letter/download` | — | PDF for the current internship |
| GET | `/me/certificate/download` | — | PDF for the current internship |
| GET | `/me/internships/{enrollment_id}/offer-letter/download` | — | PDF · `404` if the enrolment is not the caller's |
| GET | `/me/internships/{enrollment_id}/certificate/download` | — | PDF · `404` if the enrolment is not the caller's |
| DELETE | `/me/account` | `{ password }` | `204` · `403` on a wrong password |

**Documents from past internships.** A student may take another internship once the
current one is certificated, and keeps lifetime access to everything earned. The
enrolment-scoped download routes serve any internship the caller has taken; someone
else's enrolment id returns `404`, not `403`, so ids cannot be probed.

**Closing an account is a soft delete.** Login is blocked and personal data is scrubbed,
but issued certificates stay publicly verifiable — `Certificate.student_name` snapshots
the recipient at issue for exactly this reason.

### Team — super admin only

| Method | Path | Body | Returns |
| --- | --- | --- | --- |
| GET | `/admin/admins` | — | `AdminAccount[]` |
| POST | `/admin/admins/invite` | `{ full_name, email, role }` | `{ admin, invite_url, email_delivered }` |
| PATCH | `/admin/admins/{id}` | `{ role?, status? }` | `AdminAccount` |

An invitation creates a **pending** account with an unusable random password hash. The
invitee sets their own password from the link, so no working credential is ever
transmitted. `invite_url` is returned only while SMTP is unconfigured; once email
delivery works it is `null`. Re-inviting the same address invalidates any previous link.
A super admin cannot change their own role or status, and the last active super admin
cannot be suspended.

**Task submission is multipart/form-data:**

| Field | Notes |
| --- | --- |
| `task_id` | |
| `title` | 5–120 chars |
| `github_url` | Must be a repository URL, not a profile |
| `live_demo_url` | Optional, https only |
| `description` | 120–5000 chars |
| `screenshots` | Repeated file field, 3–8 files, PNG/JPG/WebP, ≤5 MB each |
| `display_order` | Repeated, parallel to `screenshots`, 1-based |


---

## Error shapes

The frontend normalises these into one `ApiError` with a `kind`. Return them as FastAPI
does by default and nothing else is needed.

| Status | Meaning to the UI | Body |
| --- | --- | --- |
| 401 | Triggers one silent refresh, then a redirect to `/login` | `{ "detail": "..." }` |
| 403 | "You don't have access to this" | `{ "detail": "..." }` |
| 404 | Not found — a normal answer for certificate verification | `{ "detail": "..." }` |
| 409 | Message shown verbatim, e.g. "You are already enrolled" | `{ "detail": "..." }` |
| 422 | Mapped onto individual form fields | `{ "detail": [{ "loc": ["body","email"], "msg": "...", "type": "..." }] }` |
| 429 | "Too many attempts" | `{ "detail": "..." }` |
| 5xx | Generic message, retried twice | any |

For 422 the frontend reads `loc[-1]` as the field name, so the last element must match
the field name the form uses (`email`, `github_url`, `screenshots`, …).

Only 5xx and network failures are retried. 401, 403, 404, 409 and 422 are never retried.

---

## Cutover

1. Backend runs and passes these shapes.
2. Set `API_BASE_URL` to the FastAPI origin.
3. Set `NEXT_PUBLIC_USE_MOCKS=false`.
4. Set `COOKIE_SECURE=true` in any deployed environment.

No code change. Every service checks `USE_MOCKS` through the same `withMock()` helper,
so flipping the flag switches all of them at once. To test one endpoint at a time,
point `API_BASE_URL` at the real backend and temporarily edit that one service's
`withMock` call.

## Known gaps

- **Email delivery is not wired.** `app/services/email.py` records every message in
  `email_logs` and returns the action link to the caller. Set `SMTP_HOST` and the flow
  switches to real delivery with no call-site changes.
- **Razorpay checkout is stubbed.** `/payments/order` and `/payments/verify` are wired,
  but the browser SDK that runs between them is not — `startPayment()` in
  `src/app/dashboard/payment/page.tsx` currently calls verify with a placeholder
  signature. Load `checkout.js` and use the real handler response once the account is live.
- **Password reset and email verification** have UI and endpoints defined, but the forms
  still resolve locally — they need the token from the URL, which needs the email
  templates to exist first.


---

## Study notes — super admin

| Method | Path | Body | Returns |
| --- | --- | --- | --- |
| GET | `/admin/chapters?domain_id=` | — | `LearningChapter[]` |
| POST | `/admin/chapters` | `{ domain_id, title, summary?, order_number, difficulty, estimated_minutes }` | `201 LearningChapter` · `409` on a duplicate position |
| PATCH | `/admin/chapters/{id}` | partial | `LearningChapter` |
| POST | `/admin/chapters/{id}/pdf` | **multipart** `file` | `LearningChapter` · `422` if not a PDF or over 25 MB |
| DELETE | `/admin/chapters/{id}` | — | `204` |
| POST | `/admin/chapters/reorder` | `{ chapter_ids: [...] }` | `LearningChapter[]` |

Chapters belong to a **domain**, so material is uploaded once per domain rather than
per batch. `(domain_id, order_number)` is unique, which is why reorder writes in two
passes — moving chapter 3 into position 1 while 1 still holds it would otherwise
violate the constraint mid-update.

---

## There are no payments

The platform is free. `/payments/*`, `/admin/payments` and `/admin/settings` are gone
rather than disabled, and the journey has no `payment_pending` or `paid` stage. The
certificate is issued inside the transaction that approves the final task.

## Storage is private

`upload_bytes` returns a storage **key**, not a URL, and nothing is served from a
public bucket. Offer letters, certificates, screenshots and chapter PDFs all come back
through authenticated routes that check who is asking. `ScreenshotOut.image_url` is
rewritten to `/screenshots/{id}` on the way out, so both apps can render it in an
`<img>` and the route decides whether the caller may see it.

Document numbers are random (`KLS-ACAD-7QF3M2XKPB`), not sequential. The old
`count(rows) + 1` scheme both raced under concurrent enrolment and let anyone holding
one number guess the rest.
