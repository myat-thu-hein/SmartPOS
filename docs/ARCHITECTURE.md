# Architecture

SmartPOS AI is a multi-tenant point-of-sale and restaurant management system: a
Next.js web app in front of a FastAPI service backed by PostgreSQL. Screens stay
in sync through a live event feed (Server-Sent Events with a polling fallback).
Forecasting runs inside the API process on NumPy. Smart insights, stock-out risk
and POS suggestions are computed from the restaurant's own data. The AI assistant
calls OpenAI when a key is configured and otherwise answers with a rule-based engine.

```
 Browser (POS, kitchen display, back office)
    │  HTTPS, one origin: /api/v1/* is the API, everything else the web app
    ▼
 Vercel: vercel.json routes /api/v1/* to the FastAPI service directly
 Elsewhere: Next.js forwards /api/v1/* to BACKEND_URL (app/api/v1/[...path]/route.ts)
    │
    ├─► Next.js 16 frontend ── proxy.ts: redirects visitors without a session cookie to /login
    ▼
 FastAPI backend
    ├─ middleware: request ID, security headers, no-store caching, JSON logs
    ├─ dependencies: session or bearer auth → CSRF check → X-Restaurant-ID membership → permission
    ├─ services: business rules and transactions
    ├─ realtime: event outbox → /events (poll) and /events/stream (SSE), notifications
    ├─ insights & suggestions: stock-out risk, explainable insights, POS add-ons
    ├─ forecasting: models, rolling-origin backtests, reorder maths
    └─ ai: read-only tools ─── OpenAI (optional) / rule-based fallback
    │  SQLAlchemy 2 (psycopg 3)
    ▼
 PostgreSQL 15+ (local, Docker or Supabase)
    append-only ledgers enforced by triggers · row level security on every table
    rate-limit counters and the live event feed are tables too (no Redis needed)
```

## Repository layout

| Path | Contents |
| --- | --- |
| `backend/app/core` | Settings, logging with redaction, error format, password hashing and token HMAC, database-backed rate limiter, permissions |
| `backend/app/models` | SQLAlchemy models (41 tables) |
| `backend/app/schemas` | Pydantic request/response models; request bodies reject unknown fields |
| `backend/app/api` | Routers (thin) and dependencies (`deps.py`: auth, tenancy, permissions) |
| `backend/app/services` | Orders, pricing, inventory, purchasing, recipes, loyalty, analytics, reports, recommendations, realtime, insights, suggestions, demo sign-in, audit |
| `backend/app/forecasting` | Metrics, models, backtesting, forecast runs |
| `backend/app/ai` | Tool registry, OpenAI orchestration, offline fallback |
| `backend/app/seed` | Demo data: seed, `--refresh` (replace only the demo restaurant), tenant purge |
| `backend/app/cli.py` | `create-admin` bootstrap command |
| `backend/app/vercel_build.py` | Vercel build step: migrations, first demo seed |
| `backend/migrations` | Alembic migrations |
| `frontend/app` | App Router pages (`(app)` = signed-in area) |
| `frontend/features` | Feature logic and dialogs (POS cart, purchasing, forecasting, menu) |
| `frontend/components` | UI primitives (shadcn-style on Radix), charts, layout |
| `frontend/lib` | API client, auth context, real-time provider, formatting, i18n (English/Thai), navigation |
| `vercel.json` | Vercel Services (web + api), routing and the demo refresh cron |

## Backend

### Request pipeline

1. `RequestContextMiddleware` assigns a request ID (returned as `X-Request-ID`
   and included in every log line and error body). It also adds security
   headers, HSTS when cookies are secure, and `Cache-Control: no-store` on API
   responses.
2. `get_auth` accepts either the `smartpos_session` httpOnly cookie (browsers) or
   `Authorization: Bearer` (API clients from `/auth/token`). Session tokens are
   random and only their HMAC-SHA256 hash is stored.
3. For cookie-authenticated unsafe methods, the `X-CSRF-Token` header must match
   the session's CSRF token (double-submit, bound to the session).
4. `RestaurantContext` resolves `X-Restaurant-ID` against the user's active
   memberships (platform administrators may enter any restaurant). Inactive
   restaurants are refused for non-administrators.
5. `require(Permission...)` checks the role's permission set. The frontend hides
   what a role cannot use, but the backend is the authority.

Endpoints stay thin. Services own business rules and transaction boundaries.
Every tenant query is scoped by `restaurant_id` (`repositories/tenant.py`), and
cross-tenant IDs return 404.

### Money, quantities and units

* Money is stored as integer minor units (satang). VAT and service charge are
  calculated with round-half-up per order (`services/pricing.py`) and support
  VAT-inclusive or VAT-exclusive menus.
* Ingredient quantities are `NUMERIC(14,3)` in a base unit (`g`, `ml`, `piece`).
  `kg` and `l` convert automatically. Per-ingredient pack units such as
  "tray = 30 piece" are user-defined, and cross-dimension conversions are refused.
* Unit costs are `NUMERIC` minor units per base unit, so a fraction of a satang
  per gram is representable.

### Orders, kitchen and payments

```
DRAFT → CONFIRMED → PREPARING → READY → COMPLETED
  └──────────┴───────────┴─────────┴──→ CANCELLED
```

* Totals are always recomputed by the server. `/orders/quote` prices a cart
  without saving it. Price fields sent by a client are rejected (422).
* **Confirm** sends the order to the kitchen and deducts stock in the same
  transaction. Ingredient rows are locked `SELECT … FOR UPDATE` in id order to
  avoid deadlocks. Confirming is idempotent. If stock is short, confirmation
  fails unless the restaurant allows negative stock.
* Order items pin the recipe version used, so editing a recipe never rewrites
  history. Editing a confirmed order reconciles stock by the order's net
  movements, and cancelling can restock (manager).
* The kitchen display moves tickets NEW → PREPARING → READY → COMPLETED and never
  receives prices.
* Payments and refunds are recorded, not processed: every method is marked
  *simulated* and receipts say so. `Idempotency-Key` makes order creation,
  payments, refunds and purchase-order receipts safe to retry. The key is unique
  per restaurant and re-checked after the order lock is taken, so concurrent
  duplicates collapse into one record.

### Inventory ledger

`inventory_movements` is the source of truth: OPENING, RECEIPT, PURCHASE_RECEIPT,
ISSUE, ADJUSTMENT (stock counts post one for the difference), WASTE, SALE and
SALE_REVERSAL movements. Each records the signed quantity, the balance after it,
the actor and links to the order or purchase order. A database trigger rejects UPDATE and DELETE on the ledger (and
on `loyalty_transactions`), so corrections are new movements. The trigger
allows only two things: a referenced user or order being deleted (its
`ON DELETE SET NULL` column becomes NULL and nothing else changes), and a
deliberate whole-restaurant purge (used to refresh the public demo) that names
the restaurant in a transaction-local setting.
`ingredients.current_stock` is a cached balance kept in step inside the same
transaction, and tests assert that it equals the ledger sum.

Cost: receipts with a price update the moving weighted-average cost. Every other
movement records the average cost in effect as its cost basis. Consumption and
waste reports therefore value usage at the cost of the day, and a later
expensive delivery does not revalue past sales.

### Purchasing

`DRAFT → SUBMITTED → PARTIALLY_RECEIVED → RECEIVED`, or `CANCELLED` (received
stock stays). Lines are entered in any unit and stored in base units. Prices
default to the supplier's price list. Each delivery is an idempotent receipt that
posts `PURCHASE_RECEIPT` movements.

### Forecasting and reorder suggestions

1. Daily demand per menu item comes from paid, non-cancelled orders in the
   restaurant's time zone. Days with no sales at all are treated as *closed*
   (missing), not as zero demand.
2. Four models: 7-day moving average, seasonal naive, day-of-week average
   (4 weeks), and a ridge regression on weekday and lag features, solved in
   closed form with NumPy (`RidgeFit`; identical to scikit-learn's `Ridge` to
   1e-11, without its 190 MB of dependencies). Predictions are clipped at zero.
3. Rolling-origin backtest: for each of the last N days, each model is fitted on
   data up to that day only and scored 1…H days ahead. MAE, RMSE and MAPE are
   stored. MAPE skips zero-actual points and reports how many were skipped. With
   `model=auto`, the lowest MAE wins.
4. Product forecasts × active recipes (with waste factors) give ingredient
   demand.
5. Reorder suggestion per ingredient:
   `max(0, demand over (lead time + review period) + safety stock − stock − open PO quantity)`,
   rounded up to the supplier's minimum order multiple. Every suggestion stores
   its inputs and a plain-language reason.
6. A manager approves, edits or rejects each suggestion. Approved ones become
   **draft** purchase orders, which someone must still submit. Nothing is
   ordered and no money moves automatically.

### Live updates and notifications

* **Transactional outbox.** Services call `realtime.emit()` inside the same
  transaction as the change (order confirmed, stock moved, table freed, PO
  received, menu edited…). The event commits or rolls back with the change, so
  a refused sale never announces anything. Events carry ids and statuses only,
  never money amounts or personal data.
* **Delivery.** `GET /events/stream` is a Server-Sent Events stream that reads
  new events about once a second and ends after `EVENTS_STREAM_SECONDS` (240 s,
  under Vercel's 300 s limit). The browser reconnects with `Last-Event-ID` and
  resumes exactly where it left off. `GET /events?after=` is the polling
  transport. Each event's topic maps to the permissions that may see it, so the
  kitchen never receives inventory events.
* **Browser.** `lib/realtime.tsx` uses the stream, falls back to polling after
  repeated failures and retries the stream a minute later. After an outage it
  refreshes everything once. Events mark the affected TanStack Query caches
  stale, batched over 250 ms, so the kitchen, tables, dashboard and stock
  screens update without reloads. Screens keep a slow safety refresh.
* **Notifications** (bell in the top bar): low stock and out of stock (sent
  once, when an ingredient crosses its reorder level or runs out), deliveries
  received and new reorder suggestions. Each notification is visible only to
  roles with the matching permission, and read state is per user.

### Smart insights, stock-out risk and suggestions

Everything here is computed from the restaurant's own records and explains the
numbers behind it. No AI provider is involved.

* **Stock-out risk** (`services/insights.py`): daily use comes from the current
  forecast when one exists, or else from net sales use over the last 14 days.
  Days of cover = stock ÷ daily use, compared with the supplier's lead time:
  *critical* when stock runs out before an order placed now could arrive,
  *warning* within a day of that or at the reorder level, *out* at zero. Stock
  already on order downgrades critical to warning and is stated.
* **Insights** on the dashboard and assistant page: sales pace against the same
  time yesterday, stock-out risk, reorder suggestions waiting, kitchen waits,
  forecast for tomorrow or a stale-forecast warning, best seller, this weekday's
  peak hour and menu items that have not sold in 14 days. Each has a severity
  and a link to the screen where it can be acted on, and each is shown only to
  roles that may see its figures.
* **POS suggestions** (`services/suggestions.py`): association rules over the
  last 90 days of paid orders. An item is suggested for the cart when it shared
  at least 3 orders with a cart item and its lift is above 1.3, i.e. it is
  bought with it more often than by chance. A selected customer's usual items
  come first; an empty cart shows what sells at this hour. Every chip states
  its reason ("In 75% of orders with Green Curry").
* **Forecast freshness:** a forecast that no longer predicts tomorrow, or is
  more than a week old, is flagged as stale on the dashboard and forecasting page.

### Demo mode

With `DEMO_LOGIN_ENABLED=true`, `POST /auth/demo-login` signs a visitor in to
the demo restaurant's manager, cashier or kitchen account (never an
administrator). While it is on, accounts that belong only to demo restaurants
cannot change their password or profile and cannot manage staff.
`GET /internal/demo/refresh` (Vercel Cron, `CRON_SECRET`) replaces the demo
restaurant with fresh history every night.

### AI assistant

The model never sees the database. `ai/tools.py` exposes seven read-only tools:
sales summary, top and slow products, inventory status, low stock, forecast, and
reorder suggestions. Each one is validated with Pydantic, limited by the
caller's permissions and scoped to the active restaurant. The orchestrator
allows at most 4 tool rounds, sends the last 8 messages, uses a 30-second
timeout, and falls back to the rule-based engine on any provider error. Without
`OPENAI_API_KEY`, the rule-based engine answers common questions from the same
tools. Requests are rate limited per user and audited (tool names only, never
the question text).

### Multi-tenancy and data protection

* Every business table carries `restaurant_id`, and services filter on it.
  Unique constraints are per restaurant.
* Row level security is enabled on all tables with no permissive policies.
  Roles other than the table owner (for example Supabase's `anon` and
  `authenticated` Data API roles) can read nothing. The API connects as the
  owner.
* Audit log entries cover sign-ins, settings, menu, recipe and price changes,
  purchasing, payments, refunds, cancellations, loyalty adjustments, staff
  changes and administrative actions.

## Frontend

* Next.js 16 App Router with Cache Components. The signed-in area
  (`app/(app)`) renders client-side because all of its data is per-user and
  per-restaurant. The shell is wrapped in Suspense so that dynamic routes such
  as `/orders/[id]` prerender a loading state.
* `lib/api.ts` is the only HTTP client. It sends `X-Restaurant-ID`, the CSRF
  header and idempotency keys, and turns error bodies into `ApiError`.
  TanStack Query caches are keyed by restaurant, so switching restaurants never
  shows another tenant's cached data.
* `lib/auth.tsx` loads `/auth/me` and exposes `can(permission)`. Navigation and
  actions follow the same permission names as the backend.
* The POS cart is a pure reducer (`features/pos/cart.ts`). Prices shown while
  typing come from the server quote.
* Charts (Recharts) use a validated colour palette, keep one hue for
  single-series data, and every chart has a table view. Status colours are
  always paired with an icon and a label.
* Thai-ready text: Noto Sans Thai alongside Inter, bilingual Thai/English
  receipts, and a translation dictionary (`lib/i18n.tsx`) that currently
  covers navigation, page titles and core POS labels. Other strings are
  English and can be added to the dictionary incrementally.
* Light and dark themes, and an 80 mm printable receipt.

## Deployment topology

* **Vercel:** one project with two services (`vercel.json`): Next.js (`web`) and
  FastAPI (`api`), on one domain. The API's build step applies migrations.
  PostgreSQL comes from Neon or Supabase through the Vercel Marketplace.
* **Docker Compose:** PostgreSQL, the backend (migrations on start) and the
  frontend (Next.js standalone server, which forwards `/api/v1` to the backend).
  Only the frontend port is published.

The backend keeps no state in memory (sessions, rate limits and the event feed
are in PostgreSQL), so it runs as several workers or serverless instances.
See [DEPLOYMENT.md](DEPLOYMENT.md).

## Known limitations

* Payments are recorded, not processed. There is no card terminal or PromptPay
  integration.
* Live updates poll an indexed event table from each open stream (about once a
  second). That suits a restaurant group; hundreds of concurrent screens would
  call for PostgreSQL `LISTEN/NOTIFY` or a message broker.
* Forecasts are per menu item from that restaurant's own history. There are no
  external signals such as weather or holidays.
* The Thai translation covers navigation and core POS labels; other strings are English.
