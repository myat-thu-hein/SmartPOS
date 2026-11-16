# Local setup

There are two ways to run SmartPOS AI locally: everything in Docker (quickest),
or the backend and frontend directly on your machine (best for development).

## Option A: Docker Compose

Requirements: Docker with Compose v2.

```bash
cp .env.example .env
# Edit .env:
#   SECRET_KEY        python -c "import secrets; print(secrets.token_urlsafe(48))"
#   POSTGRES_PASSWORD any random value
#   SEED_DEMO=true and DEMO_PASSWORD=<your choice> to load the demo restaurant
docker compose up --build
```

Open <http://localhost:3000> and sign in as `manager@smartpos.demo` (or `admin@`,
`cashier@`, `kitchen@`) with your `DEMO_PASSWORD`. The backend applies
migrations on start. Data persists in the `pgdata` volume; remove it with
`docker compose down -v`.

> **Behind a TLS-intercepting proxy?** Builds that download packages need your
> proxy's CA. Pass it as a build secret (it is not stored in the image):
> `docker build --secret id=extra_ca,src=/path/to/ca.pem ...`. If outbound
> traffic must go through an HTTP proxy, add `--build-arg HTTPS_PROXY=...`.

## Option B: run the services directly

Requirements: Python 3.13, Node.js 22, PostgreSQL 15 or newer.

### 1. Database

```bash
createuser --pwprompt smartpos          # password: smartpos (the development default)
createdb --owner smartpos smartpos
createdb --owner smartpos smartpos_test # used by the backend test suite
```

Any PostgreSQL works. To use another server or Supabase, set `DATABASE_URL` in
`.env` (`postgresql://user:password@host:5432/dbname`; `postgres://` URLs are
accepted too).

### 2. Backend

```bash
cp .env.example .env                    # at the repository root; the backend reads ../.env
cd backend
python3.13 -m venv .venv
source .venv/bin/activate               # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
alembic upgrade head
DEMO_PASSWORD='choose-a-password-1' python -m app.seed.demo   # optional demo data
uvicorn app.main:app --reload
```

The API runs at <http://localhost:8000>, with interactive docs at
<http://localhost:8000/api/docs>.

Demo data (development only):

* `python -m app.seed.demo` creates "Baan Siam (Demo)": a Thai restaurant with
  menu, recipes, suppliers, about 120 days of synthetic sales and purchasing,
  a forecast and reorder suggestions. Everything is labelled *Demo*.
* Without `DEMO_PASSWORD`, a random password is generated and printed once.
* `--reset --yes` wipes the database first (local databases only; add
  `--allow-remote` deliberately for anything else). `--days N` changes the
  history length.
* `python -m app.seed.demo --refresh` replaces only the demo restaurant with
  fresh history ending today (handy when the local demo data gets old).
* The seed refuses to run when `APP_ENV=production`, except on a public demo
  deployment (`DEMO_LOGIN_ENABLED=true`).

### 3. Frontend

```bash
cd frontend
npm ci
cp .env.example .env.local              # BACKEND_URL=http://localhost:8000
npm run dev
```

Open <http://localhost:3000>. The Next.js server forwards `/api/v1/*` to
`BACKEND_URL` (read at runtime), so the browser only ever talks to one origin.

### 4. Optional: the OpenAI-powered assistant

Set `OPENAI_API_KEY` (and optionally `OPENAI_MODEL`) in `.env` and restart the
backend. Without a key, the assistant answers common questions with the
built-in rule-based engine. Both modes use the same read-only data tools.

### 5. Optional: email for password resets

In development, reset links are written to the backend log. To send real
email, set `EMAIL_BACKEND=smtp` with `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`,
`SMTP_PASSWORD` and `EMAIL_FROM`.

## Creating an administrator without demo data

```bash
cd backend
python -m app.cli create-admin --email you@example.com --name "Your Name"   # prompts for a password
```

Sign in, open **Administration**, create a restaurant, then add its manager.

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_ENV` | `development` | `development`, `test` or `production` (strict checks) |
| `DATABASE_URL` (or `POSTGRES_URL`) | `postgresql://smartpos:smartpos@localhost:5432/smartpos` | PostgreSQL connection; pooled URLs (PgBouncer, Supabase, Neon) are supported |
| `SECRET_KEY` | development placeholder | HMAC key for session and reset tokens; production requires 32+ random characters |
| `SESSION_TTL_HOURS` | `12` | Session lifetime |
| `COOKIE_SECURE` | on in production | Secure cookies (HTTPS only) |
| `COOKIE_SAMESITE` | `lax` | `lax`, `strict` or `none` (needs secure cookies) |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated origins allowed to call the API directly |
| `FRONTEND_URL` | `http://localhost:3000` | Used in password reset links |
| `EMAIL_BACKEND` | `console` (dev) / `disabled` (prod) | `console`, `smtp` or `disabled` |
| `EMAIL_FROM`, `SMTP_*` | | SMTP settings (`SMTP_SECURITY`: `starttls` or `ssl`) |
| `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_BASE_URL` | unset, `gpt-4.1-mini` | Assistant provider |
| `API_DOCS_ENABLED` | on outside production | Serve `/api/docs` and the OpenAPI schema |
| `LOG_FORMAT`, `LOG_LEVEL` | `json`, `INFO` | Structured logs with secret redaction |
| `LOGIN_RATE_LIMIT_ATTEMPTS`, `LOGIN_RATE_LIMIT_IP_ATTEMPTS`, `LOGIN_RATE_LIMIT_WINDOW_SECONDS` | `10`, `60`, `300` | Sign-in throttling per account and per client IP (staff often share one connection) |
| `DEMO_PASSWORD` | random | Password for the demo accounts; read from the environment or `.env`, and applied again whenever the seed runs (so changing it and re-running the seed, or restarting Docker with `SEED_DEMO=true`, updates it) |
| `DEMO_LOGIN_ENABLED` | `false` | One-click demo sign-in on the login page (public demo deployments) |
| `CRON_SECRET` | unset | Secret for the nightly demo refresh job (Vercel Cron) |
| `TRUST_FORWARDED_FOR` | `false` | Use `X-Forwarded-For` as the client IP (only behind a proxy that overwrites it) |
| `MIGRATION_DATABASE_URL` | unset | Direct connection for migrations; also read as `DATABASE_URL_UNPOOLED` / `POSTGRES_URL_NON_POOLING` |
| `EVENTS_STREAM_SECONDS`, `EVENTS_POLL_INTERVAL_SECONDS` | `240`, `1.0` | Live-update stream length and how often it checks for events |
| `RUN_MIGRATIONS`, `SEED_DEMO` (Docker only) | `true`, `false` | Run `alembic upgrade head` and/or the demo seed when the backend container starts |
| `BACKEND_URL` (frontend) | `http://localhost:8000` | Where Next.js forwards `/api/v1`. Read at runtime (not used on Vercel, which routes `/api/v1` itself) |
| `NEXT_PUBLIC_API_URL` (frontend) | empty | Only to call the API cross-origin from the browser. It is public, so never put secrets in `NEXT_PUBLIC_*` |

## Troubleshooting

* **"Refusing to run tests against database …"**: the test database name must
  end with `_test`, because the tests drop and recreate its schema.
* **Sign-in works but every page says "not assigned to any restaurant"**: the
  account has no active membership. An administrator can add it from
  Administration → Restaurants → Add member.
* **"Invalid email or password" for a demo account**: the accounts use the
  `DEMO_PASSWORD` of the last seed run. Set it in `.env` and re-run
  `python -m app.seed.demo` (or restart Docker with `SEED_DEMO=true`); the
  existing accounts are updated. If it was never set, the first run printed a
  random password (`docker compose logs backend`).
* **The frontend shows "Cannot reach the SmartPOS server"**: check that the
  backend is running and that `BACKEND_URL` points at it.
* **Changes to `globals.css` don't show up in `next dev`**: stop the dev
  server, delete `frontend/.next/dev`, and start it again.
