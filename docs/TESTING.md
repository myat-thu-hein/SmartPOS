# Testing

| Suite | Tool | Count | Command |
| --- | --- | --- | --- |
| Backend unit, API and integration | pytest against PostgreSQL | 146 tests | `cd backend && pytest -q` |
| Backend lint and format | Ruff | | `ruff check . && ruff format --check .` |
| Migrations | Alembic | | `alembic upgrade head && alembic check` |
| Frontend unit and component | Vitest + Testing Library (jsdom) | 51 tests | `cd frontend && npm test` |
| Frontend lint and types | ESLint, TypeScript | | `npm run lint && npm run typecheck` |
| UI end to end (several browsers at once) | Playwright | 10 tests | `npm run test:e2e` |

All suites run in GitHub Actions (`.github/workflows/ci.yml`) on every push and
pull request, along with a production build and both Docker image builds.

## Backend

The tests use a real PostgreSQL database, because the behaviour under test
depends on it: row locks, triggers, constraints, `ON CONFLICT` and time zones.

```bash
createdb --owner smartpos smartpos_test
cd backend
TEST_DATABASE_URL=postgresql://smartpos:smartpos@localhost:5432/smartpos_test pytest -q
```

Safety: the suite **drops and recreates the schema** of the test database, then
applies the Alembic migrations. It refuses to run unless the database name ends
in `_test`, so it can never touch development or production data. Tables are
truncated between tests, and password hashing uses fast Argon2 parameters in
tests only.

What the backend tests cover:

| File | Highlights |
| --- | --- |
| `test_auth.py` | Cookie and bearer sessions ("keep me signed in" off gives browser-session cookies), CSRF enforcement, logout revocation, rate limiting (per account and per network, shared across processes, cleared by a successful sign-in), trusted `X-Forwarded-For`, password change and reset (single-use, expiring tokens), no account enumeration, password policy (including Thai combining marks) |
| `test_permissions.py` | Endpoint × role matrix for cashier, kitchen, manager and administrator |
| `test_tenant_isolation.py` | Another restaurant's records return 404 and never appear in lists; the `X-Restaurant-ID` header cannot be spoofed; boundaries between administrators and staff |
| `test_units.py` | Base and pack unit conversion; cross-dimension conversions refused |
| `test_catalog.py` | Categories and products (same-restaurant checks), modifier groups and options (with ingredient use), table lifecycle, recipe versioning and cost, pack units |
| `test_pricing.py` | VAT inclusive and exclusive, service charge rules, discounts, loyalty redemption, rounding |
| `test_orders.py` | State machine, kitchen flow, stock deduction on confirm, edits that reconcile stock, cancellation with restock, payments, change, refunds, idempotency, **concurrent confirmations never oversell**, **concurrent duplicate payments**, ledger immutability (the trigger rejects UPDATE and DELETE), rejection of client-supplied prices |
| `test_inventory_purchasing.py` | Manual movements in any unit, stock counts, role restrictions, purchase order lifecycle, partial receiving, over-receipt protection, **concurrent duplicate receipts** |
| `test_customers_loyalty.py` | Earn, redeem, reversal, adjustments, masked contact details for cashiers, anonymisation |
| `test_analytics.py` | Time-zone day boundaries, summary maths, refunds in net sales, same-time-yesterday comparison, cost-basis valuation, filtered refunds, CSV formula escaping |
| `test_forecasting.py` | Metrics (including MAPE with zero actuals), each model, the closed-form ridge solver, closed days, a leak-free backtest, model selection, forecast coverage, reorder formula and minimum-order rounding |
| `test_ai.py` | Tool permission checks and argument validation, the OpenAI tool loop with a fake client (including tenant scoping), provider failures falling back to rules, intent detection |
| `test_config_email.py` | Production configuration guards, SMTP delivery (bodies never logged), API docs and HSTS by environment, connection-pooler detection, Neon/Supabase integration URLs |
| `test_cli.py` | Administrator bootstrap: password from the environment, strength checks, promotion |
| `test_e2e_scenario.py` | One full business day through the public API (below) |
| `test_realtime.py` | Event feed by role, tenant isolation, rolled-back changes emit nothing, low/out-of-stock alerts once per crossing with per-user read state, delivery notifications, the SSE stream with `Last-Event-ID` resume, stream membership checks |
| `test_insights.py` | Days of cover vs lead time (price-list lead time beats the supplier's; stock on order downgrades the risk), forecast staleness, structured and role-aware dashboard insights, POS suggestions (confidence, lift, never in the cart or unavailable, customer usual, popular now, tenant isolation), customer favourites |
| `test_demo_login.py` | Demo sign-in off by default, sign-in by role (never an administrator), shared demo accounts cannot change sign-in details or staff, real restaurants unaffected |
| `test_demo_refresh.py` | The refresh replaces only demo restaurants (ledger rows of other restaurants untouched); the cron endpoint is hidden without configuration and needs the exact secret; a new `DEMO_PASSWORD` (also from `.env`) is applied to accounts an earlier run created |
| `test_ledger.py` | Ledger rows cannot be updated or deleted; clearing a deleted user's reference is the only allowed change |
| `test_packaging.py` | `pyproject.toml` dependencies match `requirements.txt`; the Vercel entrypoint and Python version are set |

### End-to-end business scenario (`test_e2e_scenario.py`)

1. An administrator creates a manager account and a restaurant.
2. The manager configures VAT (inclusive), service charge and loyalty.
3. The manager creates cashier and kitchen accounts, and cannot create another manager.
4. Supplier, ingredients with opening stock and cost, and a price list with a minimum order.
5. Menu with a stock-consuming modifier, and a versioned recipe.
6. The cashier registers a customer and sends a dine-in order; stock is deducted exactly, and the SALE movements (with quantities, balances and the cashier as actor) are checked through the API.
7. The kitchen receives the ticket, never sees prices, and marks it preparing and ready.
8. Cash payment with change; an idempotent retry does not charge twice; loyalty points are earned; the receipt states that payments are simulated; the kitchen marks the order completed and the table is closed.
9. Only a manager can refund.
10. Analytics and the CSV report reflect the sale and the refund.
11. Forecast from history (next-day and 7-day, with backtest metrics); a cashier cannot approve a reorder suggestion; the manager approves it, and it only becomes a **draft** purchase order.
12. The purchase order is submitted and received in two deliveries; stock matches the ledger exactly.
13. The assistant answers from this restaurant's data; a cashier cannot use it.
14. Cashier and kitchen accounts get 403 for manager operations (products, settings, purchase orders, stock, forecasts, analytics, staff), and a second restaurant cannot see any of the data.

## Frontend

```bash
cd frontend
npm test            # Vitest: cart reducer, money and unit formatting, navigation by role,
                    # sidebar rendering, modifier rules, form schemas, password rules,
                    # PO estimates, login form (incl. first-admin redirect and demo
                    # roles, show/hide password, "keep me signed in", wrong-password and paused
                    # sign-in states, status banners, the signed-in panel), dashboard
                    # loading/data/error states and insights, chart
                    # table views, POS modifier dialog, and the real-time provider
                    # (batched cache refresh, polling fallback, stream resume, offline)
npm run lint
npm run typecheck
```

### UI end-to-end tests (Playwright)

These run against a live stack with the development demo data. They create
real orders, so never point them at production.

```bash
# backend running with: DEMO_PASSWORD=... python -m app.seed.demo
# frontend running on http://localhost:3000
cd frontend
E2E_PASSWORD="$DEMO_PASSWORD" npm run test:e2e
# or against another URL:
E2E_BASE_URL=http://localhost:3001 E2E_PASSWORD="$DEMO_PASSWORD" npx playwright test
```

Covered (`e2e/smoke.spec.ts`, `e2e/live-and-smart.spec.ts`, `e2e/auth.spec.ts`):
a wrong password explained and then corrected; signing out and the
"already signed in" panel; an incomplete reset link and the reset request; redirect to
sign-in; a cashier's sale through payment and the kitchen picking it up;
role-restricted pages and the analytics table view; **live sync between three
browser sessions** (a kitchen screen and a dashboard opened beforehand update
without reloading when the cashier sends an order, and the cashier is told
when the kitchen marks it ready); POS suggestions adding an item; the command
palette; and one-click demo sign-in (skipped unless the backend has
`DEMO_LOGIN_ENABLED=true`, as in CI). Tests are skipped when `E2E_PASSWORD` is unset.

## Verification record

### 2026-11-12 (release 2: real time, smart features, redesign, Vercel)

In the development container:

* Backend: 146 passed. Ruff check and format clean. `alembic check` reports no
  drift; migrations 0001–0006 go down to base and up again.
* Frontend: 51 Vitest tests passed; ESLint and `tsc` clean; `next build`
  succeeded (31 routes).
* Playwright: 7 passed against `next dev` (three consecutive runs) and 7 passed
  against the Docker Compose stack (production images, demo sign-in enabled).
* Real time, measured in the browser: a kitchen ticket appeared about 0.8 s
  after the cashier sent the order, and the cashier's "ready" message about
  0.9 s after the kitchen marked it.
* Docker: both images built (`BACKEND_URL` is now a runtime setting);
  `docker compose up` applied migrations, seeded the demo and served the app;
  the frontend proxy carried API calls, demo sign-in and an SSE stream.
* Vercel: `vercel build --prod` (CLI 65.14.0) completed locally for both
  services: Next.js built; the FastAPI service used Python 3.13 from
  `.python-version`, installed dependencies from `pyproject.toml` and ran the
  build step, which applied migrations to the database it was given. The
  output routes `/api/v1/*` to the API (300 s limit, streaming on) and the rest
  to Next.js, registers the cron job, and the API bundle is 145 MB without
  tests. A real deployment to Vercel could not be made from this environment
  (no Vercel account or network access to Vercel's API).
* Demo refresh: replacing the demo restaurant (about 5,700 orders and 46,000
  ledger rows) took 13 s and left no rows of the old restaurant; ordinary
  ledger DELETEs are still rejected.
* Dependency audits: `npm audit --omit=dev` found 0 vulnerabilities, and
  `pip-audit -r requirements.txt` found no known vulnerabilities.
* Browser checks: every page for every role without console errors or failed
  API calls; no horizontal scrolling at 390 px on 13 main pages; dashboard
  checked in light and dark mode.

### 2026-10-25 (release 1)

In the development container:

* Backend: 114 passed. Ruff check and format clean. `alembic check` reports no
  drift. Migrations go up, down and up again on a fresh database.
* Frontend: 39 Vitest tests passed; ESLint and `tsc` clean; `next build`
  succeeded (31 routes).
* Playwright: 3 passed against `next dev`, and 3 passed against the Docker
  Compose stack (production images).
* Docker: both images built; `docker compose up` applied migrations, seeded the
  demo and reported all three services healthy.
* Production mode (Compose with `APP_ENV=production`, `RUN_MIGRATIONS=false`):
  migrations run as a separate step, `create-admin` created the first
  administrator, `/api/docs` and the OpenAPI schema returned 404, HSTS was
  present, cookies were `Secure` and `HttpOnly`, and in the browser the new
  administrator landed on Administration and created the first restaurant.
* Dependency audits: `npm audit --omit=dev` found 0 vulnerabilities, and
  `pip-audit -r requirements.txt` found no known vulnerabilities.
* Manual browser checks at 1440, 768 and 390 px wide: every page renders without
  console errors or horizontal scrolling. The newer pages were also checked in
  dark mode.
