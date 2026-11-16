# SmartPOS

**A real-time point of sale and restaurant management system with explainable
demand forecasting, stock-out prediction, smart reorder suggestions and
add-on recommendations, all computed from the restaurant's own data.**

SmartPOS runs a restaurant's day from the counter to the kitchen to the
storeroom. Cashiers ring up orders, the kitchen display updates the moment an
order is confirmed, every sale deducts ingredients through versioned recipes,
and managers see live sales, stock-out risk and reorder suggestions they can
approve with a click. Nothing is ordered or paid automatically.

Main workflow: order → POS → payment → kitchen → inventory consumption → live
dashboard → demand forecast → reorder suggestion → manager approval → purchase
order → delivery.

## Screenshots

![Dashboard with live KPIs and smart insights](docs/screenshots/dashboard.png)

| POS with add-on suggestions | Kitchen display (live) |
| --- | --- |
| ![POS](docs/screenshots/pos.png) | ![Kitchen display](docs/screenshots/kitchen.png) |
| **Inventory with days of cover** | **Forecasting and backtests** |
| ![Inventory](docs/screenshots/inventory.png) | ![Forecasting](docs/screenshots/forecasting.png) |
| **Reorder suggestions** | **Analytics** |
| ![Reorder suggestions](docs/screenshots/reorder-suggestions.png) | ![Analytics](docs/screenshots/analytics.png) |
| **Sign-in with one-click demo** | **Mobile POS** |
| ![Sign-in](docs/screenshots/login.png) | ![Mobile POS](docs/screenshots/pos-mobile.png) |

*All screenshots show the synthetic "Baan Siam (Demo)" restaurant.*

## Highlights

* **Real-time across screens.** Orders, stock, tables, deliveries and
  notifications reach every open screen within about a second through
  Server-Sent Events, with automatic polling fallback and resume-after-outage.
  Events are written in the same database transaction as the change, so a
  refused sale never announces anything.
* **AI you can check.** Every insight, prediction and suggestion states the
  numbers behind it: "Tofu lasts about 1.8 days but delivery takes 2",
  "Steamed rice is in 75% of orders with Green Curry (2× more than chance)".
  Forecast models are chosen by rolling-origin backtests, not assumed.
* **Correct money and stock.** Integer minor units, server-side pricing,
  idempotent payments, an append-only inventory ledger enforced by database
  triggers, and row locks that keep concurrent sales consistent.
* **Production-minded.** Role-based access enforced by the API, tenant
  isolation backed by PostgreSQL row level security, CSRF-protected httpOnly
  sessions, database-backed rate limits, strict production config checks,
  redacted structured logs, 207 automated tests (146 backend, 51 frontend, 10
  end-to-end), CI, Docker and a Vercel setup.

## Features

* **POS:** product grid with search and categories, modifiers with rules,
  dine-in and takeaway, server-calculated Thai VAT (inclusive or exclusive) and
  service charge, discounts with cashier limits, loyalty redemption, cash change,
  in-cart quantity badges, keyboard shortcuts (`/`, `Ctrl+Enter`), a sticky
  order bar on phones, and 80 mm receipts in Thai and English.
* **Smart POS suggestions:** "often ordered together" from association rules
  over the last 90 days (support, confidence and lift), a selected customer's
  usual items, and what sells at this hour when the cart is empty.
* **Live kitchen display:** New, Preparing and Ready columns, ticket age with
  late warnings, a highlight for tickets that just arrived, and no prices.
  Front-of-house staff are told when an order is ready.
* **Dashboard:** greeting, KPI tiles with 14-day sparklines and comparisons at
  the same time yesterday, sales charts with table views, stock at risk, top
  products, kitchen status, forecast for tomorrow and smart insights.
* **Smart insights:** sales pace, stock-out risk, reorder suggestions waiting,
  kitchen waits, stale forecasts, best sellers, this weekday's peak hour and
  items that have not sold in two weeks, each linked to the screen where you act on it.
* **Inventory:** stock in base units with kg/L and pack-unit conversion, an
  append-only movement ledger, stock counts and waste, **days of cover against
  supplier lead time**, low-stock and out-of-stock notifications (sent once per
  crossing), and moving-average valuation.
* **Forecasting:** four models (moving average, seasonal naive, day-of-week
  average and a ridge regression on weekday and lag features) compared by
  rolling-origin backtests with MAE, RMSE and MAPE; ingredient demand through
  recipes; explainable reorder suggestions that become draft purchase orders
  only after a manager approves them; stale-forecast warnings.
* **Recipes, suppliers and purchasing:** versioned recipes pinned to each sale,
  supplier price lists with minimum orders and lead times, and
  draft → submitted → partially received → received purchase orders with
  idempotent deliveries.
* **Customers and loyalty:** order history, favourite items, total spending,
  a points ledger, masked contact details for cashiers, and anonymisation.
* **Analytics and reports:** sales, products, categories, payments, hours,
  consumption, waste and purchases with fair period comparisons, filters,
  chart and table views, and CSV exports.
* **Sign-in:** show/hide password, Caps Lock warning, "keep me signed in",
  clear error messages with a countdown when sign-in is paused, banners after
  sign-out, session expiry or a password reset, an "already signed in" panel
  for shared tills, a live password checklist on reset, and English/Thai and
  light/dark before signing in.
* **App shell:** collapsible sidebar, `Ctrl/⌘+K` command palette, notification
  center, live connection status, light and dark themes, responsive from phone
  to desktop, and English/Thai.
* **Roles and tenants:** administrator, manager, cashier and kitchen; several
  restaurants per account; an audit log.
* **Demo mode:** an optional "Explore the live demo" panel on the sign-in page
  for portfolio deployments, with safeguards and a nightly data refresh.

## Architecture

```
Browser ──► one origin ──┬─ /api/v1/* ──► FastAPI backend ──► PostgreSQL
                         │                  ├─ services (orders, pricing, inventory, purchasing, …)
                         │                  ├─ realtime (event outbox → SSE / polling, notifications)
                         │                  ├─ insights, stock-out risk, POS suggestions
                         │                  ├─ forecasting (NumPy) and reorder maths
                         │                  └─ AI tools ──► OpenAI (optional)
                         └─ everything else ► Next.js frontend
```

On Vercel, `vercel.json` routes `/api/v1/*` to the FastAPI service and the rest
to Next.js. With Docker or `next dev`, Next.js forwards `/api/v1/*` to the
backend. Either way the browser talks to one origin, so cookies stay
first-party. The backend keeps no state in memory, so it scales out or runs
serverless. Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Technology stack

| Layer | Technology |
| --- | --- |
| Frontend | Next.js 16 (App Router), React 19, TypeScript (strict), Tailwind CSS 4, Radix-based components, Lucide icons, TanStack Query, React Hook Form + Zod, Recharts |
| Backend | Python 3.13, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, psycopg 3 |
| Data and ML | PostgreSQL 15+ (local, Docker, Neon or Supabase), NumPy |
| Real time | Server-Sent Events over a transactional outbox table, polling fallback |
| AI | OpenAI API (optional) with tool calling; deterministic rule-based fallback |
| Quality | pytest, Vitest + Testing Library, Playwright, Ruff, ESLint, GitHub Actions |
| Delivery | Vercel (Services), Docker, Docker Compose |

## Quick start

### Option A: Docker

```bash
git clone <your-repository-url> SmartPOS-AI && cd SmartPOS-AI
cp .env.example .env
# In .env set:
#   SECRET_KEY        (python -c "import secrets; print(secrets.token_urlsafe(48))")
#   POSTGRES_PASSWORD (any random value)
#   SEED_DEMO=true and DEMO_PASSWORD=<choose one> to load the demo restaurant
#   DEMO_LOGIN_ENABLED=true for the one-click demo buttons
docker compose up --build
```

Open <http://localhost:3000>. Use the demo buttons, or sign in as
`manager@`, `cashier@`, `kitchen@` or `admin@smartpos.demo` with your `DEMO_PASSWORD`.

### Option B: run the backend and frontend directly

```bash
# 1. Database (once)
createuser --pwprompt smartpos            # password "smartpos" matches the development default
createdb --owner smartpos smartpos
createdb --owner smartpos smartpos_test   # for the test suite

# 2. Backend
cp .env.example .env                      # the backend reads ../.env
cd backend
python3.13 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
alembic upgrade head
DEMO_PASSWORD='choose-a-password-1' python -m app.seed.demo
uvicorn app.main:app --reload             # http://localhost:8000

# 3. Frontend (second terminal)
cd frontend
npm ci
cp .env.example .env.local                # BACKEND_URL=http://localhost:8000
npm run dev                               # http://localhost:3000
```

Step-by-step explanations and troubleshooting: [docs/SETUP.md](docs/SETUP.md).

## Environment setup

All settings come from environment variables; `.env.example` documents them.
The most important:

| Variable | Purpose |
| --- | --- |
| `APP_ENV` | `development` or `production` (production refuses insecure settings at start-up) |
| `SECRET_KEY` | Random, 32+ characters; signs sessions and reset tokens |
| `DATABASE_URL` (or `POSTGRES_URL`) | PostgreSQL connection; pooled URLs work |
| `MIGRATION_DATABASE_URL` | Optional direct connection for migrations |
| `FRONTEND_URL`, `CORS_ORIGINS` | Public URL and allowed browser origins |
| `TRUST_FORWARDED_FOR` | `true` behind Vercel or the Compose frontend (per-visitor rate limits) |
| `DEMO_LOGIN_ENABLED`, `CRON_SECRET` | Public demo mode and its nightly refresh |
| `OPENAI_API_KEY` | Optional assistant provider |
| `EMAIL_BACKEND`, `SMTP_*` | Password-reset email |
| `BACKEND_URL` (frontend) | Where Next.js forwards `/api/v1` outside Vercel (runtime) |

Never commit `.env`, and never put secrets in `NEXT_PUBLIC_*` variables. The
full list is in [docs/SETUP.md](docs/SETUP.md#environment-variables) and
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md#production-environment-variables).

## Database and migrations

```bash
cd backend
alembic upgrade head        # create or upgrade the schema
alembic check               # verify that models and migrations match
alembic downgrade -1        # step back one migration (take a backup first)
```

The local default is `postgresql://smartpos:smartpos@localhost:5432/smartpos`;
Docker Compose starts its own PostgreSQL with a persistent volume. Schema
documentation: [docs/DATABASE_DESIGN.md](docs/DATABASE_DESIGN.md).

## Demo data

```bash
cd backend
DEMO_PASSWORD='choose-a-password-1' python -m app.seed.demo              # add the demo restaurant
DEMO_PASSWORD='choose-a-password-1' python -m app.seed.demo --refresh    # replace only the demo restaurant with fresh history
DEMO_PASSWORD='choose-a-password-1' python -m app.seed.demo --reset --yes   # wipe the LOCAL database and reseed
```

"Baan Siam (Demo)" has a Thai menu, recipes, tables, suppliers, customers,
about 120 days of synthetic sales (with realistic dish pairings) and
purchasing, a forecast and reorder suggestions. It is labelled as demo data
everywhere. For a real installation, create an administrator instead:

```bash
python -m app.cli create-admin --email you@example.com --name "Your Name"   # prompts for the password
```

## Running the tests

```bash
# Backend (needs the smartpos_test database; it is wiped on each run)
cd backend
ruff check . && ruff format --check .
pytest -q

# Frontend
cd frontend
npm run lint && npm run typecheck
npm test                                            # Vitest unit and component tests
E2E_PASSWORD="$DEMO_PASSWORD" npm run test:e2e      # Playwright, against a running stack with demo data
```

What each suite covers, and the latest verification record: [docs/TESTING.md](docs/TESTING.md).

## Docker commands

```bash
docker compose up --build -d                      # build and start db, backend, frontend
docker compose logs -f backend                    # follow backend logs
docker compose exec backend python -m app.cli create-admin --email you@example.com
docker compose exec backend alembic upgrade head  # run migrations by hand
docker compose down                               # stop (data kept)
docker compose down -v                            # stop and DELETE the database volume
```

## API documentation

* Interactive docs: <http://localhost:8000/api/docs> (Swagger UI) and
  <http://localhost:8000/api/redoc>, on outside production.
* OpenAPI schema: <http://localhost:8000/api/v1/openapi.json>.
* Conventions, error codes, live-update examples and all 149 operations:
  [docs/API_DOCUMENTATION.md](docs/API_DOCUMENTATION.md).
* Health checks: `GET /api/v1/health` (liveness) and `GET /api/v1/health/ready` (database).

## Known limitations

* **Payments are recorded, not processed.** Card and QR payments must be
  confirmed on your terminal or banking app; receipts mark them as simulated.
* **Nothing is ordered automatically.** Forecasts, insights and AI answers are
  advice. A manager approves reorder suggestions, which become draft purchase orders.
* Forecasts use each restaurant's own sales history only, without holidays,
  promotions or weather.
* Live updates read an indexed event table about once a second per open
  screen. That suits a restaurant group, not thousands of concurrent screens.
* The interface is in English; navigation, page titles, core POS labels and
  receipts are also available in Thai.
* No multi-factor authentication or SSO yet.

## Future improvements

Card terminal and PromptPay integrations, holiday and promotion features for
forecasting, PostgreSQL `LISTEN/NOTIFY` for live updates at larger scale, full
Thai translation, MFA and SSO, a nonce-based CSP, background forecast jobs and
an offline-tolerant POS. See [docs/DEVELOPMENT_ROADMAP.md](docs/DEVELOPMENT_ROADMAP.md).

## Documentation

| Document | Contents |
| --- | --- |
| [Setup](docs/SETUP.md) | Local development, environment variables, demo data, troubleshooting |
| [User guide](docs/USER_GUIDE.md) | How each role uses the system |
| [Architecture](docs/ARCHITECTURE.md) | Components, request pipeline, ledgers, live updates, insights, forecasting, AI |
| [Database design](docs/DATABASE_DESIGN.md) | Tables, constraints, integrity guarantees, migrations |
| [API documentation](docs/API_DOCUMENTATION.md) | Conventions, errors, examples, all operations |
| [Testing](docs/TESTING.md) | Test suites, how to run them, verification record |
| [Deployment](docs/DEPLOYMENT.md) | Vercel, demo mode, Docker Compose, other hosts, rollback, troubleshooting |
| [Security](docs/SECURITY.md) | Threat model, roles and permissions, demo safeguards, data handling, review log |
| [Development roadmap](docs/DEVELOPMENT_ROADMAP.md) | Milestones, status and next steps |

## Project layout

```
backend/    FastAPI app (app/), Alembic migrations, pytest suite, Dockerfile, Vercel build step
frontend/   Next.js app, Vitest tests (tests/), Playwright tests (e2e/), Dockerfile
docs/       Documentation and screenshots
vercel.json · docker-compose.yml · .env.example · .github/workflows/ci.yml
```
