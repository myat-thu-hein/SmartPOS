# Security

This document describes how SmartPOS AI protects accounts, restaurant data and
money records, what was reviewed, and the known limitations.

## Threats considered

| Threat | Mitigation |
| --- | --- |
| Password guessing | Argon2id hashing; 10 attempts per 5 minutes per IP and per email; identical errors and timing for unknown accounts |
| Session theft | Random 256-bit tokens, stored only as HMAC-SHA256 hashes; httpOnly cookie, `Secure` in production, `SameSite=Lax`; 12-hour expiry; revoked on logout, deactivation and password change |
| CSRF | Unsafe cookie-authenticated requests must send `X-CSRF-Token`, which must match the session's token |
| XSS | React escapes output; strict CSP (no `unsafe-eval` in production, `frame-ancestors 'none'`); assistant answers render as text, never HTML; image URLs limited to `http(s)` |
| Clickjacking | `X-Frame-Options: DENY` and `frame-ancestors 'none'` |
| Cross-tenant access | Every query is scoped to the active restaurant; membership checked per request; foreign IDs return 404; row level security on every table |
| Privilege escalation | Permissions checked in the backend on every endpoint; managers cannot create or modify managers; nobody can remove their own administrator access |
| Tampering with prices or totals | The server computes all totals; price fields in requests are rejected (unknown fields return 422) |
| Duplicate charges or stock moves | Idempotency keys on orders, payments, refunds and purchase receipts, re-checked under row locks; tested with concurrent requests |
| Silent edits of financial history | Inventory and loyalty ledgers are append-only (a database trigger rejects UPDATE and DELETE); orders snapshot prices and names; audit log |
| Spreadsheet formula injection | CSV cells beginning with `=`, `+`, `-`, `@`, tab or CR are prefixed with `'` |
| SQL injection | SQLAlchemy parameterised queries only; the AI model has no database access |
| Prompt injection against the assistant | The model can only call 7 read-only, permission-checked, tenant-scoped tools with validated arguments; it cannot write, order or pay |
| Secrets leakage | Secrets come only from the environment; `.env` files are git-ignored; logs redact passwords, tokens, keys, cookies and authorization headers; query strings and request bodies are not logged |
| Insecure production configuration | Start-up fails on a weak or default `SECRET_KEY`, insecure cookies, wildcard CORS, the console email backend, or SMTP without TLS |
| Known-vulnerable dependencies | Exact pins; `npm audit --omit=dev` (0 issues) and `pip-audit` (none known) run on 2026-10-25 |

## Authentication

* **Passwords:** Argon2id (argon2-cffi defaults), rehashed when parameters
  change. Policy: 8–128 characters, not only digits and not only letters.
  Combining marks count as letters, so a Thai word on its own is rejected.
* **Browser sessions:** `POST /auth/login` sets `smartpos_session` (httpOnly)
  and `smartpos_csrf` (readable by the page so it can echo the value in
  `X-CSRF-Token`). With "keep me signed in" unticked, both cookies are sent
  without `Max-Age`, so the browser drops them when it closes (shared tills);
  the server-side session lifetime applies either way.
* **API clients:** `POST /auth/token` returns a bearer token with the same
  lifetime and revocation rules. CSRF does not apply to bearer requests.
* **Password reset:** single-use token, hashed at rest, valid for 30 minutes.
  The request endpoint always answers `202`, so it does not reveal which
  accounts exist. Completing a reset revokes all sessions.
* **Bootstrap:** no account has a built-in password. The first administrator is
  created with `python -m app.cli create-admin`, which prompts for the password
  (or reads a named environment variable) and never takes it as a command-line
  argument. Demo accounts exist only when the demo seed is run. In production
  the seed runs only on a deployment that is explicitly a public demo
  (`DEMO_LOGIN_ENABLED=true`), and then without an administrator account.

* **Rate limits:** sign-in, password reset, demo sign-in and the assistant use a
  sliding-window counter stored in PostgreSQL, so limits hold across workers
  and serverless instances. The client IP is the socket address unless
  `TRUST_FORWARDED_FOR=true`, which is only safe behind a proxy that overwrites
  `X-Forwarded-For` (Vercel does; so does the Compose frontend).

### Demo mode (`DEMO_LOGIN_ENABLED`)

Off by default. When on, `POST /auth/demo-login` signs visitors in to the
demo restaurant's manager, cashier or kitchen account: an ordinary session,
rate limited and audited (`auth.demo_login`). Safeguards:

* Only restaurants marked `is_demo`, and never a platform administrator. A
  public demo deployment creates no administrator account at all.
* Accounts that belong only to demo restaurants cannot change their password
  or profile and cannot create, edit or reset staff accounts (`403
  demo_restricted`). Visitors cannot lock each other out or use the demo to
  create accounts for real people's email addresses.
* No password is displayed or sent; the response is the same as a normal sign-in.
* The nightly refresh, `GET /internal/demo/refresh`, answers 404 unless demo
  mode and `CRON_SECRET` are both configured, compares the bearer secret in
  constant time, and only ever deletes restaurants marked `is_demo`.

### Append-only ledgers

Database triggers reject UPDATE and DELETE on `inventory_movements` and
`loyalty_transactions`. The trigger allows only (1) a referenced user, order or
transaction being deleted, which sets that one column to NULL, and (2) DELETE
of one restaurant's rows when the transaction names that restaurant in the
local setting `smartpos.purge_restaurant` (the demo refresh). Anyone able to
set that is already the table owner, who could drop the trigger anyway, so the
trigger guards against application mistakes rather than a malicious database
administrator.

## Roles and permissions

The backend enforces these permissions on every request. The frontend uses the
same names to hide what a role cannot do.

| Permission | Manager | Cashier | Kitchen |
| --- | :-: | :-: | :-: |
| `menu:read` | ✓ | ✓ | ✓ |
| `menu:write`, `recipes:read`, `recipes:write` | ✓ | | |
| `tables:read`, `tables:operate` | ✓ | ✓ | |
| `tables:write` | ✓ | | |
| `orders:read`, `orders:create`, `orders:complete`, `orders:cancel_draft` | ✓ | ✓ | |
| `orders:cancel` (confirmed orders, optional restock) | ✓ | | |
| `payments:record` | ✓ | ✓ | |
| `refunds:record` | ✓ | | |
| `discounts:apply` (up to the cashier limit) | ✓ | ✓ | |
| `discounts:override` (custom and above-limit discounts) | ✓ | | |
| `kitchen:read` | ✓ | ✓ | ✓ |
| `kitchen:update` | ✓ | | ✓ |
| `customers:read`, `customers:create` (cashiers see masked contact details) | ✓ | ✓ | |
| `customers:write`, `loyalty:adjust` | ✓ | | |
| `inventory:*`, `suppliers:*`, `purchasing:*` | ✓ | | |
| `analytics:read`, `reports:read` | ✓ | | |
| `forecast:read`, `forecast:run`, `recommendations:read`, `recommendations:review` | ✓ | | |
| `ai:use` | ✓ | | |
| `staff:manage` (cashier and kitchen accounts) | ✓ | | |
| `settings:read` | ✓ | ✓ | |
| `settings:write` | ✓ | | |

**Platform administrators** have every permission in every restaurant, plus
`platform:admin` (restaurants, all users, the manager role) and `audit:read`.

## Tenant isolation

* `X-Restaurant-ID` is only a selector. It is honoured only if the user has an
  active membership in that restaurant, and the restaurant is active.
* Services always filter on `restaurant_id`. Lookups by ID include the
  restaurant, so another tenant's IDs behave as if they did not exist (404).
* The frontend clears cached data when the user switches restaurants, and its
  query keys include the restaurant ID.
* PostgreSQL row level security is enabled on all tables with no permissive
  policies, which protects against accidental exposure through Supabase's Data
  API.

## Payments

SmartPOS records payments; it does not move money. Every payment method is
marked **simulated**, receipts state that staff recorded the payment, and card
or QR payments must be confirmed on the external terminal or banking app. No
card data is collected or stored; the optional `reference` field is meant for
a terminal slip number.

## AI assistant and data sent to third parties

* Without `OPENAI_API_KEY`, nothing leaves the server; the rule-based engine
  answers from the same tools.
* With a key, the question, the recent conversation (last 8 messages, each
  truncated) and the **tool results** are sent to OpenAI. Tool results contain
  business figures (sales totals, product names and quantities, stock levels,
  forecasts and reorder suggestions), never customer names, phone numbers or
  emails, and never credentials.
* The assistant cannot change data. Reorder suggestions still need a manager's
  approval and only produce **draft** purchase orders.
* Audit entries for `ai.query` record which tools were used and the question
  length, not the question text.

## Personal data

* Customers: name, optional phone, email and notes. Cashiers see masked contact
  details. Managers can **anonymise** a customer, which erases personal data
  but keeps the order and loyalty history needed for accounting.
* Staff: name, email and last sign-in. Audit logs keep the IP address of
  security-relevant actions.
* Logs never contain passwords, tokens, API keys, full payment credentials or
  request bodies.

## Security headers

Backend: `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`,
`Permissions-Policy`, `Cross-Origin-Opener-Policy`, `Cache-Control: no-store`,
and HSTS when served over HTTPS.

Frontend: a Content Security Policy (`default-src 'self'`; `connect-src 'self'`;
`frame-ancestors 'none'`; `form-action 'self'`), the same headers as the
backend, and HSTS in production builds.

## Review log (2026-10-25)

Issues found during the review and fixed:

* Product image URLs accepted `javascript:` URLs in the frontend form; the form
  now requires `http(s)`, matching the backend's `HttpUrl` validation.
* Request bodies silently ignored unknown fields; they are now rejected (`extra="forbid"`).
* Integrity-error logs could include row values such as email addresses; only
  the constraint name is logged now.
* Thai-only passwords passed the "letters and numbers or symbols" rule; fixed
  in both the backend and the frontend.
* Production lacked a way to send password reset emails; added an SMTP
  backend, and the console backend (which logs reset links) is refused in
  production.
* Interactive API docs are now off by default in production, and HSTS was added.

## Review log (2026-11-12)

* A shared demo account could have been taken over by changing its password;
  demo-only accounts can no longer change sign-in details or manage staff.
* Rate limits were per process, so they did not hold on serverless platforms;
  they are now stored in PostgreSQL.
* The ledger trigger failed with "record new has no field …" instead of its
  own error, and its `ON DELETE SET NULL` exception never worked for loyalty
  transactions; replaced with a table-agnostic version (migration 0005).
* The live event feed and notifications never include money amounts or
  personal data, and events are filtered by the reader's permissions.

## Known limitations

* There is no multi-factor authentication or SSO yet.
* The CSP allows `'unsafe-inline'` scripts because Next.js injects inline
  bootstrapping scripts. Nonce-based CSP is a possible hardening step.
* Payments are simulated records (see above).

## Reporting a vulnerability

Please do not open a public issue. Email the maintainers with steps to
reproduce, the affected version or commit, and the `X-Request-ID` of any
relevant request.
