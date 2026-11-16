# Deployment

SmartPOS AI has three parts: PostgreSQL, the FastAPI backend and the Next.js
frontend. Browsers only ever talk to one origin, so session cookies stay
first-party:

* **On Vercel**, `vercel.json` defines two [services](https://vercel.com/docs/services)
  in one project. Requests to `/api/v1/*` go straight to the FastAPI service and
  everything else to Next.js.
* **Elsewhere** (Docker Compose, a VM, `next dev`), the Next.js route handler
  `app/api/v1/[...path]/route.ts` forwards `/api/v1/*` to the backend at
  `BACKEND_URL`, read at runtime.

| Option | Good for |
| --- | --- |
| [1. Vercel + Neon or Supabase](#option-1-vercel) | Portfolio demo, small production use, zero servers |
| [2. One server with Docker Compose](#option-2-one-server-with-docker-compose) | Self-hosting on a VM you control |
| [3. Other managed hosts](#option-3-other-managed-hosts) | Render, Fly.io, Railway or Cloud Run for the backend |

## Production checklist

- [ ] `APP_ENV=production`. The backend refuses to start with insecure settings
      and prints what to fix.
- [ ] `SECRET_KEY`: 32+ random characters, stored as a secret, never committed.
      Rotating it signs everyone out and invalidates pending reset links.
- [ ] HTTPS end to end. Secure cookies are on by default in production.
- [ ] `FRONTEND_URL` and `CORS_ORIGINS`: the public HTTPS origin (never `*`).
- [ ] Email: `EMAIL_BACKEND=smtp` with a TLS relay, or leave it `disabled` and
      reset passwords from User Management.
- [ ] A first administrator created with the CLI. No account has a built-in password.
- [ ] Database backups or point-in-time recovery, and a tested restore.
- [ ] Optional: `OPENAI_API_KEY` for the natural-language assistant. Business
      figures are sent to OpenAI; customer details are not (see [SECURITY.md](SECURITY.md)).
- [ ] Public demo only: `DEMO_LOGIN_ENABLED=true` and `CRON_SECRET` (see
      [Demo mode](#demo-mode-for-a-public-portfolio-deployment)).

## Option 1: Vercel

What the repository already configures:

| File | Purpose |
| --- | --- |
| `vercel.json` | Services `web` (Next.js, `frontend/`) and `api` (FastAPI, `backend/`); `/api/v1/*` → `api`, everything else → `web`; a 300 s function limit for the API (live-update streams last 240 s, then reconnect); a daily cron for the demo refresh |
| `backend/pyproject.toml` | `[tool.vercel] entrypoint = "app.main:app"`, the dependency list, and `[tool.vercel.scripts] build`, which runs `app/vercel_build.py` |
| `backend/.python-version` | Python 3.13 |
| `backend/app/vercel_build.py` | Applies migrations during the build; on a demo deployment, creates the demo restaurant if it is missing |

### Steps

1. **Push the repository to GitHub** (see the main README).
2. **Create the project.** In Vercel choose *Add New… → Project*, import the
   repository, keep the **root directory at the repository root** and set
   **Framework Preset** to **Services**. Vercel reads `vercel.json` and builds
   both services. Do not set a build command for the project; each service has
   its own.

   > **Do not set Root Directory to `frontend`.** Vercel then builds only the
   > website: the build succeeds, but there is no API, so nobody can sign in
   > (requests to `/api/v1` answer `api_not_deployed`). To fix an existing
   > project: in *Settings → Build and Deployment*, clear **Root Directory**,
   > set **Framework Preset** to **Services**, save, and redeploy. A correct build log labels each line with its
   > service, `[vc:service:web]` or `[vc:service:api]`; a log without those
   > labels is building only one folder.
3. **Add a database** from *Storage* (Vercel Marketplace):
   * **Neon** sets `DATABASE_URL` (pooled) and `DATABASE_URL_UNPOOLED` (direct).
     Enable *preview branches* so each preview deployment gets its own copy of
     the database instead of migrating production's.
   * **Supabase** sets `POSTGRES_URL` (pooled) and `POSTGRES_URL_NON_POOLING` (direct).

   The backend uses the pooled URL at runtime (prepared statements are
   disabled automatically for PgBouncer-style poolers) and the direct URL for
   migrations. Client-specific URL options such as `pgbouncer=true` or
   `supa=…` are removed before connecting. Any other PostgreSQL 15+ works too:
   set `DATABASE_URL`, and optionally `MIGRATION_DATABASE_URL` for a direct connection.
4. **Set environment variables** (*Settings → Environment Variables*):

   | Variable | Value |
   | --- | --- |
   | `APP_ENV` | `production` |
   | `SECRET_KEY` ★ | `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
   | `FRONTEND_URL` | `https://<your-project>.vercel.app` (or your domain) |
   | `CORS_ORIGINS` | the same origin |
   | `TRUST_FORWARDED_FOR` | `true`. Vercel overwrites `X-Forwarded-For` with the real client IP, so rate limits apply per visitor |
   | `EMAIL_BACKEND` | `disabled`, or `smtp` with `SMTP_*` settings ★ |
   | `OPENAI_API_KEY` ★ | optional |

   ★ = mark as *Sensitive*. Leave `BACKEND_URL` and `NEXT_PUBLIC_API_URL`
   unset on Vercel; nothing needs them there.
5. **Deploy.** The `api` build log shows `SmartPOS build: applying migrations …`
   and `database schema is up to date`. If `APP_ENV`, `SECRET_KEY` or the
   database is missing, the build stops with a list of every missing setting and
   where to add it, instead of deploying a broken app. Preview deployments use
   the *Preview* environment's variables, so enable the variables there too (with
   a separate database) or previews will stop at the same check.
6. **Create the first administrator** from a trusted machine, using the
   production connection string (never commit it):

   ```bash
   cd backend
   vercel env pull .env.production.local      # or export DATABASE_URL=... yourself
   set -a; . ./.env.production.local; set +a
   python -m app.cli create-admin --email you@example.com --name "Your Name"
   rm .env.production.local
   ```

   Sign in, create your restaurant under *Administration*, and invite staff
   from *User Management*.
7. **Check it:** `https://<host>/api/v1/health/ready` returns `{"status":"ok"…}`;
   after signing in, the top bar shows **Live**.

### Demo mode for a public portfolio deployment

To let visitors try the app without an account:

| Variable | Value |
| --- | --- |
| `DEMO_LOGIN_ENABLED` | `true` |
| `CRON_SECRET` ★ | 16+ random characters (Vercel sends it to the cron job) |
| `DEMO_PASSWORD` ★ | optional; only needed to sign in to the demo accounts by password |

Then:

* The first build creates **Baan Siam (Demo)**: 120 days of synthetic sales,
  recipes, suppliers, purchase orders and a forecast. There is **no
  administrator account** on a public demo.
* The sign-in page shows **Explore the live demo** with *Manager*, *Cashier*
  and *Kitchen* buttons. They sign in to the demo restaurant's accounts by
  role; no password is shown or needed.
* The shared demo accounts cannot change their password, profile or staff
  accounts, so one visitor cannot lock out the next or use the demo to create
  accounts for real email addresses.
* Every day at about 19:17 UTC (02:17 in Bangkok; Hobby crons run within the
  hour) `GET /api/v1/internal/demo/refresh` replaces the demo restaurant with
  fresh history ending that day. Only restaurants marked as demo are touched.
  The endpoint returns 404 unless demo mode and `CRON_SECRET` are both set,
  and 401 without the exact secret.
* To refresh by hand: `python -m app.seed.demo --refresh --no-admin` with the
  production `DATABASE_URL`.

Visitors share the demo data, so anything they type is visible to the next
visitor until the nightly refresh. With an `OPENAI_API_KEY`, assistant
questions cost money. The assistant is rate limited per user, and all visitors
of one demo role share a user, so the limit also caps the whole demo. Leave the
key unset to use the free rule-based mode.

If the deployment is not a demo, delete the `crons` block from `vercel.json`
or leave it: the endpoint answers 404 and does nothing.

### Notes and limits on Vercel

* **Live updates** use Server-Sent Events. Each stream lasts
  `EVENTS_STREAM_SECONDS` (240 s), then the browser reconnects and resumes
  from the last event, so nothing is missed. If streaming is unavailable, the
  app falls back to polling every 3 seconds and says so in the top bar.
  Each open stream is a running function, so idle open tabs add function
  duration. Lower `EVENTS_STREAM_SECONDS` or close idle tabs on a tight budget.
* **Rate limits** (sign-in, assistant) are stored in PostgreSQL, so they hold
  across function instances.
* **Bundle size:** the backend's runtime dependencies are about 150 MB, well
  within Vercel's 500 MB Python limit (forecasting needs only NumPy); tests and
  caches are excluded from the bundle.
* **API docs** (`/api/docs`) are off in production. If you enable
  `API_DOCS_ENABLED`, add rewrites for `/api/docs` and `/api/v1/openapi.json`
  to the `api` service; only `/api/v1/*` is routed there by default.
* **Preview deployments** run migrations against whatever database the Preview
  environment points at. Give previews their own database (Neon branches), or
  set `SKIP_MIGRATIONS=1` for Preview.
* **Local emulation:** `vercel dev` runs both services with the same routing.
  Plain `npm run dev` plus `uvicorn` (see [SETUP.md](SETUP.md)) also works.

## Option 2: one server with Docker Compose

A small VM (2 vCPU, 4 GB RAM) runs the whole stack.

```bash
git clone <your repository> smartpos && cd smartpos
cp .env.example .env
```

Edit `.env`:

```ini
APP_ENV=production
SECRET_KEY=<python -c "import secrets; print(secrets.token_urlsafe(48))">
POSTGRES_PASSWORD=<random>
FRONTEND_URL=https://pos.example.com
COOKIE_SECURE=true
EMAIL_BACKEND=smtp
SMTP_HOST=smtp.example.com
SMTP_USERNAME=...
SMTP_PASSWORD=...
EMAIL_FROM=SmartPOS <no-reply@example.com>
SEED_DEMO=false
RUN_MIGRATIONS=false        # migrations are run deliberately, see below
```

```bash
docker compose build
docker compose up -d db
docker compose run --rm backend alembic upgrade head
docker compose up -d
docker compose exec backend python -m app.cli create-admin --email you@example.com --name "Your Name"
```

Only the frontend container publishes a port. It forwards `/api/v1` to
`http://backend:8000` (`BACKEND_URL`, set at runtime in `docker-compose.yml`).
Terminate TLS in front of port 3000. With Caddy, the whole configuration is:

```
pos.example.com {
    reverse_proxy 127.0.0.1:3000
}
```

Bind the published port to localhost (`"127.0.0.1:3000:3000"` in
`docker-compose.yml`) so that only the TLS proxy can reach it.

Upgrades (back up first; see [Database migrations](#database-migrations-in-production)):

```bash
docker compose exec -T db pg_dump -U smartpos -Fc smartpos > before-upgrade-$(date +%F).dump
git pull
docker compose build
docker compose run --rm backend alembic upgrade head
docker compose up -d
```

Backups:

```bash
docker compose exec -T db pg_dump -U smartpos -Fc smartpos > smartpos-$(date +%F).dump
# restore: docker compose exec -T db pg_restore -U smartpos -d smartpos --clean < smartpos-YYYY-MM-DD.dump
```

## Option 3: other managed hosts

### Database: Supabase, Neon or any PostgreSQL 15+

* Use the pooled connection for `DATABASE_URL` and the direct one for
  `MIGRATION_DATABASE_URL`. `postgres://` and `postgresql://` URLs are accepted.
* Migrations create every table with row level security enabled and no
  policies, so Supabase's `anon` and `authenticated` Data API roles can read
  nothing. Only the backend, connecting as the table owner, has access. Keep
  the Data API keys out of the frontend.

### Backend: Render, Fly.io, Railway or Cloud Run

* Docker, root directory `backend`. Health check path: `/api/v1/health/ready`.
* Environment: `APP_ENV=production`, `DATABASE_URL`, `SECRET_KEY`,
  `FRONTEND_URL`, `CORS_ORIGINS`, email and OpenAI settings.
* Set `RUN_MIGRATIONS=false` and run `alembic upgrade head` as the platform's
  pre-deploy command, so a failed migration stops the deploy before traffic moves.
* Client IPs: keep `TRUST_FORWARDED_FOR=false` unless the platform's proxy
  overwrites `X-Forwarded-For` and clients cannot reach the backend directly.
* Auto-deploy "after CI checks pass", so a commit whose tests fail is never deployed.

### Frontend: the Docker image, or any Node.js host

* Docker: `docker build -t smartpos-frontend frontend`, run with
  `-e BACKEND_URL=https://api.example.com`.
* Node: `NEXT_OUTPUT=standalone npm run build`, copy `.next/static` and `public`
  into `.next/standalone`, then `BACKEND_URL=https://api.example.com node .next/standalone/server.js`.
* Leave `NEXT_PUBLIC_API_URL` empty so requests stay same-origin.

## Build and start commands

| Component | Build | Start | Health check |
| --- | --- | --- | --- |
| Vercel | automatic (both services) | automatic | `GET /api/v1/health/ready` |
| Backend (Docker) | `docker build -t smartpos-backend backend` | image default: `uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers` (workers: `WEB_CONCURRENCY`, default 1) | `GET /api/v1/health/ready` |
| Backend (no Docker) | `pip install -r requirements.txt` | `uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers` | `GET /api/v1/health/ready` |
| Frontend (Docker) | `docker build -t smartpos-frontend frontend` | `docker run -e BACKEND_URL=… -p 3000:3000 smartpos-frontend` | `GET /login` |
| Frontend (Node) | `NEXT_OUTPUT=standalone npm run build` | `node .next/standalone/server.js` (after copying `.next/static` and `public`) | `GET /login` |
| Migrations | | `alembic upgrade head` (working directory `backend`) | `alembic current` |

## Production environment variables

Backend (★ = secret):

| Variable | Example | Notes |
| --- | --- | --- |
| `APP_ENV` | `production` | Enables the start-up safety checks |
| `SECRET_KEY` ★ | 48 random characters | Rotating it signs everyone out |
| `DATABASE_URL` ★ (or `POSTGRES_URL`) | `postgresql://user:pass@host/db?sslmode=require` | Pooled connections are fine |
| `MIGRATION_DATABASE_URL` ★ (or `DATABASE_URL_UNPOOLED`, `POSTGRES_URL_NON_POOLING`) | direct connection | Used by migrations; defaults to `DATABASE_URL` |
| `DATABASE_POOLER` | unset | `true`/`false` to override pooler detection (port 6543 or a `-pooler` host) |
| `FRONTEND_URL` | `https://pos.example.com` | Used in reset emails |
| `CORS_ORIGINS` | `https://pos.example.com` | Comma-separated; never `*` |
| `COOKIE_SECURE` | `true` (default in production) | |
| `COOKIE_DOMAIN` | unset | Only for cross-subdomain cookies |
| `TRUST_FORWARDED_FOR` | `true` on Vercel, `false` otherwise | Use the first `X-Forwarded-For` address as the client IP |
| `EMAIL_BACKEND` | `smtp` or `disabled` | |
| `EMAIL_FROM`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD` ★, `SMTP_SECURITY` | | `SMTP_SECURITY`: `starttls` (default) or `ssl` |
| `OPENAI_API_KEY` ★, `OPENAI_MODEL` | | Optional |
| `DEMO_LOGIN_ENABLED` | `false` | Public demo sign-in (see above) |
| `CRON_SECRET` ★ | random | Required by the demo refresh job |
| `EVENTS_STREAM_SECONDS` | `240` | Length of one live-update stream |
| `RUN_MIGRATIONS` | `false` | Docker entrypoint only |
| `SKIP_MIGRATIONS` | unset | `1` skips the Vercel build step's migrations |
| `FORWARDED_ALLOW_IPS` | `127.0.0.1` | Uvicorn: proxies whose forwarded headers are trusted |
| `API_DOCS_ENABLED` | unset (off) | Turn on to expose `/api/docs` |
| `LOG_LEVEL`, `LOG_FORMAT` | `INFO`, `json` | |

Frontend: `BACKEND_URL` (runtime; not needed on Vercel). Leave `NEXT_PUBLIC_API_URL` empty.

## Database migrations in production

Migrations are a deliberate deployment step, never a side effect of traffic:

1. Take a backup, or confirm point-in-time recovery is available.
2. Run `alembic upgrade head` once: the Vercel build step, a pre-deploy
   command, or a one-off job with the new image.
3. Only then switch traffic to the new application version.

All migrations in this repository are additive and reversible, but review
every new migration for destructive operations before it reaches production.
Never use `--reset` seeding or `alembic downgrade base` on a production database.

## Rollback

* **Application only (no schema change):** redeploy the previous deployment
  (Vercel: *Instant Rollback*) or image.
* **Release with a migration:** schema changes are backwards-compatible by
  convention (new columns nullable or defaulted, nothing dropped in the same
  release), so the previous application version keeps working on the new
  schema. Roll back the application first. Only if the migration itself must
  be undone, run `alembic downgrade -1` after a fresh backup.
* **Data problem:** restore the backup taken before the upgrade
  (`pg_restore --clean`, or point-in-time recovery). Inventory and loyalty
  ledgers are append-only at the database level, so data fixes are made with
  correcting entries, not edits.

## Troubleshooting

| Symptom | Likely cause and fix |
| --- | --- |
| Backend exits with "Invalid production configuration: …" | A start-up check failed; the message names the variable (weak `SECRET_KEY`, `CORS_ORIGINS=*`, console email, SMTP without TLS…) |
| Vercel build log has no `[vc:service:…]` labels, and sign-in fails with `api_not_deployed` | The project's Root Directory is `frontend`, so only the website was deployed. In *Settings → Build and Deployment*, clear Root Directory, set Framework Preset to Services, and redeploy |
| Vercel build stops with "this production deployment is missing settings the app needs" | Add the listed variables (step 4) or connect a database (step 3) for that environment, then redeploy |
| Vercel log shows `npm warn` lines (`cache-dir`, deprecated `eslint`, `install-scripts … allowScripts`) | Harmless: npm notices about the build machine's npm configuration and a dependency's install script. The real error, if any, is further down the log |
| Vercel refuses `vercel.json` (`services` is not supported) | Services may not be enabled for your account. Deploy as two projects instead: one with Root Directory `backend` (the API, with every variable from step 4), and one with Root Directory `frontend` and `BACKEND_URL` set to the API project's URL. The website forwards `/api/v1` to it, so cookies stay on the website's domain. In this setup the demo refresh cron in the root `vercel.json` does not run, and rate limits see the website's server address rather than each visitor's, so leave `TRUST_FORWARDED_FOR` unset |
| `/api/v1/health/ready` returns 503 | The database is unreachable: check the URL, network rules and `sslmode=require` |
| "prepared statement … does not exist" | A pooler on an unusual host or port was not detected: set `DATABASE_POOLER=true` |
| Sign-in succeeds but the next request is 401 | The cookie isn't stored: the site must be HTTPS when `COOKIE_SECURE=true`, and the browser must call the API on the same origin |
| 403 `csrf_failed` on every change | The `smartpos_csrf` cookie is blocked or a proxy strips `X-CSRF-Token`; serve the frontend and API from one origin |
| "Cannot reach the SmartPOS server" (Docker/Node) | `BACKEND_URL` is wrong for the frontend container; fix it and restart (no rebuild needed) |
| Every visitor is rate limited together | The client IP is the proxy's: set `TRUST_FORWARDED_FOR=true` where the proxy overwrites `X-Forwarded-For` (Vercel, the Compose frontend) |
| Top bar says "Live" with polling, or "Offline" | Streaming is blocked by a proxy (polling still works) / the API is down |
| The demo sign-in buttons do not appear | `DEMO_LOGIN_ENABLED` is not `true`, or no demo restaurant exists yet (redeploy, or run the seed with `--refresh`) |
| The cron log shows 401 | `CRON_SECRET` changed after the deployment was built: redeploy (Vercel sends the secret captured at build time) |
| Password reset emails never arrive | `EMAIL_BACKEND` is `disabled`, or SMTP failed (logged); managers can set passwords in User Management |
| Assistant says "offline mode" | `OPENAI_API_KEY` is not set, or the provider failed (the answer says which) |

## Health and monitoring

| Endpoint | Meaning |
| --- | --- |
| `GET /api/v1/health` | Process is up (liveness) |
| `GET /api/v1/health/ready` | Database reachable (readiness) |

Logs are JSON lines with `request_id`, method, path, status and duration.
Passwords, tokens, API keys and authorization headers are redacted, and query
strings are not logged. Every API response returns `X-Request-ID`; the same ID
appears in error bodies shown to users.

## Scaling

* **Backend:** stateless apart from PostgreSQL. Rate limits and the live-update
  feed live in the database, so any number of workers or function instances can
  run side by side.
* **Live updates:** each open screen polls the event table about once a second
  through its stream (an indexed range read). For many hundreds of concurrent
  screens, raise `EVENTS_POLL_INTERVAL_SECONDS` or move the feed to
  PostgreSQL `LISTEN/NOTIFY` or a message broker.
* **Forecasting** runs in the request (about a second for the demo menu). For
  very large menus, move `forecast/runs` to a background job.
* **Database:** all queries are tenant-scoped and indexed on `restaurant_id`.
  The connection pool defaults to 5 connections plus 10 overflow
  (`DATABASE_POOL_SIZE`, `DATABASE_MAX_OVERFLOW`); use a pooler on serverless platforms.

## Building images behind a corporate proxy

```bash
docker build --secret id=extra_ca,src=/path/to/proxy-ca.pem \
  --build-arg HTTPS_PROXY=http://proxy:3128 -t smartpos-backend backend
docker build --secret id=extra_ca,src=/path/to/proxy-ca.pem \
  --build-arg HTTPS_PROXY=http://proxy:3128 -t smartpos-frontend frontend
```

The CA is mounted only while dependencies download and is not stored in any
image layer. Docker's predefined proxy build arguments are not kept in the
image either.
