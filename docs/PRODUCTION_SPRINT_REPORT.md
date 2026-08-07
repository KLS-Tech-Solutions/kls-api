# Production Readiness Sprint — report

7 Aug 2026 · `academy` · `admin-dashboard` · `kls-api`

**Every priority is complete.** The platform now talks only to FastAPI and PostgreSQL.
There is no mock mode left to switch on, no demo data, and no code path that fabricates a
user or a session.

**Verification:** 50 backend tests pass, both frontends typecheck and build clean, and
`scripts/verify_integration.py` walks the entire workflow end to end — 21 assertions, all
passing.

---

## 1. Summary of changes

| Area | What changed |
| --- | --- |
| **Mock layer** | Deleted entirely from `academy`. `withMock()`, `USE_MOCKS`, and all four mock data files are gone |
| **Authentication** | Every flow hits the backend. Student portal refuses admin accounts; admin console refuses student accounts — both *before* a cookie is written |
| **Session expiry** | A dead session redirects to `/login` from one place in the API client instead of each screen rendering its own error |
| **Auto logout** | 30 minutes of inactivity in both apps, shared across browser tabs, with a warning two minutes before |
| **Seed data** | Now creates only the first super admin and the email template rows. No domains, batches, tasks or students |
| **Task configuration** | Nine new per-task settings a super admin controls, enforced by the API on every upload |
| **Domain management** | Ordering, image, activate/deactivate, full CRUD — super admin only |
| **Database** | One migration adding 10 columns. No data loss; existing rows take sensible defaults |
| **Contact details** | `klstechsolutions2025@gmail.com` everywhere, from one constant per app |
| **Cleanup** | Removed unused components, hooks, service functions and fabricated testimonials |

---

## 2. Every mock implementation removed

### Deleted files

| File | What it was |
| --- | --- |
| `academy/src/lib/api/mock.ts` | The `withMock()` switch every service went through |
| `academy/src/data/domains.ts` | Six hardcoded internship domains and batches |
| `academy/src/data/journey.ts` | `mockUser`, `buildJourney()` — a complete fake student with fabricated submissions, payments and a certificate |
| `academy/src/data/certificates.ts` | Two fake verifiable certificates |
| `academy/src/components/dashboard/stage-switcher.tsx` | Dev control that jumped the fake student between all ten journey stages |
| `admin-dashboard/src/components/ui/disclosure.tsx` | Unused component |

### Mock code paths removed

| Location | What it did |
| --- | --- |
| `academy/src/app/api/auth/login/route.ts` | Issued a `mock-access-token` cookie for **any** credentials when `USE_MOCKS` was on — a working fake login |
| `academy/src/app/api/auth/session/route.ts` | Returned `mockUser` instead of asking the backend who you were |
| `academy/src/app/api/auth/register/route.ts` | Returned success without creating anything |
| `academy/src/app/api/auth/refresh/route.ts` | Re-issued the mock token indefinitely |
| `academy/src/lib/api/config.ts` | `USE_MOCKS` flag |
| All five `*.service.ts` files | Every function had a mock branch returning invented data |
| `certificates.server.ts` | Verified against the two fake certificates |

### Demo content removed

| Item | Where |
| --- | --- |
| 6 demo domains, 6 batches, 26 tasks | `scripts/seed.py` |
| Three fabricated student testimonials | `academy` homepage and `data/content.ts` — invented quotes attributed to named students |
| "This form is a UI prototype — messages aren't delivered" | Contact form |
| "This is a UI prototype — no real payment is taken" | Payment dialog |

**Kept deliberately:** the certificate preview on the public homepage (marketing, per
your instruction) and `data/content.ts` — the journey steps, FAQs and "why KLS" copy,
which is real marketing content rather than placeholder data.

### Verification

```
grep -rn "USE_MOCKS|withMock|mockUser|@/data/domains|@/data/journey" academy/src
→ no matches
```

---

## 3. Authentication audit

### What was wrong

**A working fake login existed in production code.** With `NEXT_PUBLIC_USE_MOCKS=true`,
`POST /api/auth/login` set a session cookie for any email and password without ever
contacting the backend. It was one environment variable away from being live.

**An admin could sign in on the student portal** and vice versa, because neither app
checked the role — they just accepted whatever the shared backend returned.

**A 401 surfaced as an error message** on whichever screen happened to make the call,
leaving people staring at a broken dashboard instead of being asked to sign in.

### What it does now

| Requirement | Implementation | Verified |
| --- | --- | --- |
| Registration uses the backend | `POST /api/auth/register` → FastAPI, creates the row and the verification token | Integration script |
| Login uses the backend | Credentials go to FastAPI; argon2 verification | `test_security.py` |
| JWT works correctly | Access + refresh pair, httpOnly cookies | 13 security tests |
| Protected routes require auth | `RequireSession` / `RequireAdmin` client-side, API dependency server-side | Integration script |
| Invalid credentials never log in | Same 401 for unknown email and wrong password | `test_auth.py` |
| Expired JWT redirects to login | One refresh attempt, then `/login?reason=expired` | Manual + code path |
| Logout clears authentication | Server clears both cookies; client wipes the query cache | `test_auth.py` |
| Refresh preserves login | Token lives in a cookie, survives reload | By construction |
| Unauthorised calls redirect | `redirectToLogin()` in the API client | Both apps |
| No fake login anywhere | Mock branches deleted | grep, above |

### Cross-portal separation

The two portals share one backend, so each refuses the other's accounts **before writing
a cookie**:

- `academy/src/app/api/auth/login/route.ts` → 403 "Administrator accounts sign in on the admin console"
- `admin-dashboard/src/app/api/auth/login/route.ts` → 403 "This console is for administrators only"

The session endpoints re-check on every call, so a role change takes effect immediately
rather than at token expiry.

---

## 4. JWT audit

### Token design

| Property | Access token | Refresh token |
| --- | --- | --- |
| Lifetime | 30 minutes | 30 days |
| Claims | `sub`, `role`, `type`, `iat`, `exp`, `jti` | `sub`, `type`, `iat`, `exp`, `jti` — **no role** |
| Algorithm | HS256 | HS256 |
| Storage | httpOnly cookie | httpOnly cookie |

### Findings

**Strong, verified by test:**

1. **Passwords are argon2id hashed** with a per-password salt — two accounts with the same password produce different hashes.
2. **Tokens never reach JavaScript.** They live in httpOnly cookies; the browser calls `/api/proxy/*` and the Next server attaches the header. An XSS payload cannot read them.
3. **The `type` claim is checked.** A 30-day refresh token cannot be used as an access token.
4. **Forged tokens are rejected** — signature verification with the server secret.
5. **The role claim does not grant access.** Authorisation reads the database on every request, so a token minted with `role: super_admin` for a student account still gets 403. This is the finding I'd most want you to know: privilege comes from the account, not the token.
6. **Suspension is immediate.** A valid unexpired token stops working the moment the account is suspended.
7. **Refresh failure clears the session** rather than leaving a half-valid state.
8. **Concurrent 401s share one refresh call** instead of stampeding.

**Hardened this sprint:**

9. **Startup configuration check.** The API now refuses to boot in production with the placeholder `SECRET_KEY`, with `DEBUG` on, with a plain-http CORS origin, or with the placeholder admin password. In development it logs a warning instead. Previously a deployment could have shipped with a publicly known signing key.

**Accepted for now, worth revisiting:**

10. **No refresh token rotation tracking.** A stolen refresh token stays valid until expiry. Mitigated by httpOnly storage; a `jti` denylist is the fix if you want it.
11. **No rate limiting on login.** Nothing throttles password guessing. Worth adding at the nginx layer during deployment.
12. **`SECRET_KEY` rotation invalidates every session.** Fine, but plan a maintenance window for it.

---

## 5. Super Admin features

### Domain management — `/catalogue/domains`

Create · edit · delete · activate/deactivate · description · icon · **image URL** ·
duration · difficulty · **display order**.

Deleting a domain that has enrolled students is refused by the API with a clear message
suggesting deactivation instead — a hard delete would orphan real student records.

### Task management — `/catalogue/batches/[id]/tasks`

Add · edit · delete · reorder · change position · **enable/disable** · instructions ·
requirements checklist · deadline · estimated hours, plus the submission rules:

| Setting | Effect |
| --- | --- |
| `min_screenshots` / `max_screenshots` | 0–20, enforced on upload |
| `require_github` | A repository URL becomes mandatory or optional |
| `require_explanation` + `min_explanation_chars` | Written explanation and its length |
| `require_live_demo` | Demo URL becomes mandatory |
| `is_active` | Hides the task from students and skips it in the journey engine |

**Each batch has its own independent task list**, and task counts vary freely by domain.

Two behaviours worth knowing:

- **Disabling a task does not strand anyone.** The journey engine skips inactive tasks, so a student who finished everything else still reaches `all_tasks_approved`. There's a test for exactly this.
- **Reordering warns first.** Students are locked task-by-task behind the previous approval, so resequencing a running batch changes what is open to people mid-flight.

### Access control

Both modules sit behind `RequireCapability="manageCatalogue"`, the sidebar hides them for
plain admins, and the API returns 403 regardless. A plain admin hitting the endpoints
directly is refused — tested.

---

## 6. Database changes

One migration: `02584f9e6f21_task_configuration_and_domain_ordering`.

```
internship_domains  + image_url               varchar(500) null
                    + display_order           integer      not null default 0

tasks               + is_active               boolean      not null default true
                    + instructions            text         null
                    + min_screenshots         integer      not null default 3
                    + max_screenshots         integer      not null default 8
                    + require_github          boolean      not null default true
                    + require_explanation     boolean      not null default true
                    + min_explanation_chars   integer      not null default 120
                    + require_live_demo       boolean      not null default false
```

Apply with `alembic upgrade head`. **Server defaults are set on every non-null column**,
so existing rows adopt the previous behaviour rather than failing the migration.
`alembic downgrade` was tested and reverses cleanly.

**No schema change was needed for anything else** — the mock removal was entirely
frontend work, and the invite flow already reuses `email_tokens`.

### New scripts

- `scripts/reset_content.py --yes` — wipes domains, batches, tasks, students, submissions, payments and certificates, keeping administrators and email templates. Use it once to clear test data.
- `scripts/verify_integration.py` — the 21-assertion end-to-end check.

---

## 7. Security improvements

1. **Fake login removed** — the single most serious issue. Production code could issue a session for any credentials.
2. **Cross-portal role enforcement** at the login boundary, before a cookie exists.
3. **Startup configuration guard** — the API will not run in production with a placeholder secret, debug mode, or an insecure CORS origin.
4. **Automatic logout** after 30 minutes idle, coordinated across tabs. Only a timestamp goes in localStorage; no token ever does.
5. **Centralised 401 handling** — one redirect path, `replace` rather than `push` so the back button cannot return to a dead screen.
6. **Per-task server-side validation** — submission rules are enforced by the API, not just the form.
7. **Security test suite** — 13 tests covering hashing, token contents, forgery, expiry, type confusion, suspension and role separation, so these become regressions rather than rediscoveries.

---

## 8. Remaining issues

**Known and accepted:**

| Item | Impact | When |
| --- | --- | --- |
| No login rate limiting | Password guessing is unthrottled | Add at nginx during deployment |
| No refresh token rotation tracking | A stolen refresh token lives until expiry | Post-launch if wanted |
| Email verification and password reset generate tokens but send nothing | Students cannot self-serve either flow | Email sprint |
| Razorpay checkout is stubbed | Payment completes without a real gateway | Payments sprint |
| Screenshots write to `./media` | Not durable, not shared across servers | R2 sprint |
| WeasyPrint may not install on Windows | Documents store as HTML rather than PDF | Resolves on the Linux VPS |
| Legal pages are placeholder copy | **Blocks Razorpay activation** | Needs your copy |
| MSME artwork is a cleaned raster | Quality and licensing | Needs the official file |

**Not issues, but worth knowing:**

- The public site shows an "Enrolment opens shortly" panel until you create your first domain. That is correct behaviour for an empty catalogue, not a bug.
- `test_journey.py` and `test_task_rules.py` build their own catalogue rather than relying on the seed, which is why the clean seed didn't break them.

---

## 9. Suggested next sprint, before VPS

**Sprint: External services and content** — everything that needs an account, in the
order that unblocks the most.

1. **Cloudflare R2** *(1 hour)* — free, instant, no approval. Turns uploads from local files into real storage. Nothing depends on it, so it is pure progress.
2. **Email provider** *(half a day)* — Brevo's free tier is enough. This closes three incomplete flows at once: email verification, password reset and admin invitations. `app/services/email.py` already logs and returns links; only `SMTP_HOST` and the templates are missing.
3. **Legal pages** *(yours, half a day)* — terms, privacy, refund. **Razorpay will not activate without them**, so this gates step 4 and is the one item only you can do.
4. **Razorpay** *(apply early, integrate while waiting)* — KYC needs your PAN, bank account and Udyam certificate. I add `checkout.js` and the webhook meanwhile.
5. **Login rate limiting and a UAT pass** *(1 day)* — run the PRD's demo scenarios with a real student on a real device before anything is public.

Then the VPS sprint has nothing left to discover: deploy, point DNS, set env vars, flip
`NEXT_PUBLIC_LAUNCH_MODE` to `live`.

**Do step 3 first if you only do one thing.** It is the longest pole — it needs writing
and review, it blocks payments, and it is the only item that cannot be parallelised.
