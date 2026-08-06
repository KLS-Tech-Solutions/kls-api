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
| POST | `/auth/register` *(public)* | `{ full_name, email, phone, password }` | `201 { email, email_verified: false }` |
| POST | `/auth/login` *(public)* | `{ email, password }` | `{ access_token, refresh_token, expires_in, user }` |
| POST | `/auth/refresh` *(public)* | `{ refresh_token }` | `{ access_token, refresh_token, expires_in }` |
| POST | `/auth/logout` | — | `204` |
| GET | `/auth/me` | — | `{ user }` |
| POST | `/auth/forgot-password` *(public)* | `{ email }` | `204` — always, even for unknown emails |
| POST | `/auth/reset-password` *(public)* | `{ token, password }` | `204` |
| POST | `/auth/verify-email` *(public)* | `{ token }` | `204` |

`expires_in` is seconds. If omitted the frontend assumes 30 minutes.

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
  "payment": { ... } | null,
  "certificate": { ... } | null,
  "notifications": [ ... ]
}
```

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
| POST | `/enrollments` | `{ domain_id, batch_id }` | `201 { enrollment_id }` · `409` if already enrolled |
| GET | `/me/tasks` | — | `Task[]` |
| POST | `/linkedin-submissions` | `{ linkedin_post_url }` | `201 { id, status: "pending" }` |
| POST | `/task-submissions` | **multipart** (below) | `201 { id, status: "under_review" }` |
| PATCH | `/me/profile` | `ProfileValues` | `StudentProfile` |
| GET | `/me/notifications` | — | `AppNotification[]` |
| PATCH | `/me/notifications/read` | `{ ids: string[] }` | `204` |
| GET | `/me/certificate` | — | `Certificate` · `null` when not issued |
| POST | `/payments/order` | — | `{ order_id, amount, currency, key_id }` |
| POST | `/payments/verify` | `{ razorpay_order_id, razorpay_payment_id, razorpay_signature }` | `Payment` |

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

`amount` from `/payments/order` is **paise** (5000 = ₹50), matching Razorpay.

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

- **Razorpay checkout is stubbed.** `/payments/order` and `/payments/verify` are wired,
  but the browser SDK that runs between them is not — `startPayment()` in
  `src/app/dashboard/payment/page.tsx` currently calls verify with a placeholder
  signature. Load `checkout.js` and use the real handler response once the account is live.
- **Password reset and email verification** have UI and endpoints defined, but the forms
  still resolve locally — they need the token from the URL, which needs the email
  templates to exist first.
