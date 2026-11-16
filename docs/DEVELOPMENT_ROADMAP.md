# Development roadmap and progress

This file records the milestones, their acceptance criteria and the verified
state of the project. It is updated at the end of every milestone so that work
can resume from an exact point.

## Milestones

| # | Milestone | Acceptance criteria | Status |
|---|-----------|---------------------|--------|
| 1 | Project setup and architecture | Monorepo layout; backend core (config, logging, errors, security); Next.js scaffold | Done |
| 2 | Database, migrations, authentication | 37-table schema; Alembic migrations (up/down verified, `alembic check` clean); session auth with CSRF; RBAC; tenant context | Done |
| 3 | Products, categories, tables, recipes | CRUD with validation; modifiers with selection rules; versioned recipes; unit conversion | Done |
| 4 | POS, orders, payments, receipts | Server-side pricing; order state machine; stock deduction on confirm; idempotent payments and refunds; receipts | Done |
| 5 | Inventory, suppliers, purchase orders | Immutable movement ledger; stock counts; valuation; supplier price lists; PO lifecycle with partial receipts | Done |
| 6 | Kitchen display | NEW → PREPARING → READY → COMPLETED with role checks; live screen | Done |
| 7 | Customers and loyalty | Masked cashier view; ledger with earn, redeem and reverse; manual adjustments; anonymisation | Done |
| 8 | Analytics and reporting | Time-zone aware metrics; fair comparisons; breakdowns; CSV exports with formula-injection protection | Done |
| 9 | Forecasting and evaluation | 4 models behind one interface; rolling-origin backtests; MAE, RMSE and MAPE with zero handling; closed days | Done |
| 10 | Recommendations and AI assistant | Explainable reorder formula; manager review; draft POs only; OpenAI tool calling with permission-checked tools and offline fallback | Done |
| — | Frontend | Every navigation item is a working screen wired to the real API, for every role | Done |
| 11 | Integration testing, security, bug fixes | API end-to-end scenario; Playwright UI smoke tests; Vitest unit tests; security review with fixes | Done |
| 12 | Docker, CI/CD, docs, deployment prep | Dockerfiles and Compose verified; GitHub Actions; full documentation set | Done |

## Verified state (2026-10-25)

See [TESTING.md](TESTING.md#verification-record) for details.

* Backend: 114 pytest tests pass against PostgreSQL. Ruff is clean. Migrations
  go up, down and up again with no drift.
* Frontend: 39 Vitest tests pass; ESLint and TypeScript are clean;
  `next build` produces all 31 routes.
* Playwright: 3 UI smoke tests pass against the dev server and against the
  Docker Compose stack.
* Docker: both images build; Compose brings up db, backend and frontend
  healthy, with migrations and demo seed on start. The production procedure
  (separate migration step, `create-admin`, `APP_ENV=production`) was also run
  end to end, including the first sign-in in the browser.
* The demo seed creates about 5,700 synthetic orders, 45,000 consistent
  inventory movements and 100 purchase orders in about 15 seconds; the ledger
  sum equals every cached stock balance.
* Dependency audits are clean (npm production dependencies and pip-audit).

Not verified in this environment: running the GitHub Actions workflow on
GitHub itself (its steps were replayed locally), real SMTP delivery (tested
with a fake SMTP server), and the OpenAI-backed assistant against the live
OpenAI API (tested with a fake client; the offline mode was exercised end to
end).

## Changes made during milestones 11–12

* Product and supplier pages, purchase orders (create, edit draft, submit,
  receive with price-deviation warnings, cancel), analytics, forecasting with
  reorder review, assistant, reports, staff management, settings,
  administration, change-password dialog, 404 and no-access pages.
* Consumption and waste are now valued at the cost basis recorded on each
  movement, instead of today's average cost.
* Period comparisons for a day in progress use the same elapsed time of the
  previous period (today until now against yesterday until the same time).
* Payment-method refunds respect the order filters in analytics.
* Request bodies reject unknown fields; client-sent prices are rejected.
* `python -m app.cli create-admin` creates the first administrator.
  Administrators without any restaurant can still reach Administration.
* SMTP email backend; production rejects console email and SMTP without TLS.
* HSTS; interactive API docs off by default in production; integrity-error
  logs no longer include row values.
* The password policy treats combining marks as letters; frontend image URLs
  are limited to `http(s)`.
* Mobile layout fixes (grid items may shrink; no horizontal scrolling at 390 px).
* Membership responses include `is_demo`, so the demo badge no longer depends
  on the restaurant name.
* Spec audit follow-ups: the API end-to-end scenario now follows all 14 spec
  steps (including kitchen completion and movement checks); dashboard and
  sidebar tests added; Compose accepts `DATABASE_URL` (Supabase) and a
  `RUN_MIGRATIONS` switch; the first administrator is redirected to
  Administration after signing in; README and deployment guide expanded
  (build/start commands, controlled migrations, rollback, troubleshooting).

## Release 2 (2026-11): real-time, smart features, redesign, Vercel

Done and tested:

* **Review and fixes:** database-backed rate limits (they did not hold across
  processes); pooler-safe connections (prepared statements off for PgBouncer,
  Supabase and Neon poolers); a runtime `/api/v1` proxy instead of a build-time
  rewrite; the ledger trigger's field-access bug (migration 0005); POS
  `Ctrl+Enter` firing while a dialog was open; payment dialog dismissal now
  explains where the unpaid order went; unused code and the unused pandas
  dependency removed; scikit-learn replaced by a closed-form NumPy ridge
  regression (about 190 MB smaller deployment, identical results).
* **Real time:** transactional event outbox, SSE stream with resume and
  polling fallback, permission-filtered topics, query invalidation in the
  browser, live status indicator, toasts for other people's actions, and a
  notification center (low/out of stock once per crossing, deliveries,
  reorder suggestions) with per-user read state.
* **Smart features:** stock-out risk (days of cover vs lead time), structured
  explainable insights, POS add-on suggestions from association rules,
  customer favourites, forecast staleness warnings, net sales per day.
* **UI/UX:** new app shell (collapsible sidebar, command palette,
  notifications, live status), dashboard redesign with KPI sparklines, sign-in
  page, POS polish (in-cart badges, suggestion chips, mobile order bar), kitchen
  highlights for new tickets, motion that respects reduced-motion settings.
* **Deployment:** Vercel Services configuration, migrations in the build step,
  Neon/Supabase integration variables, demo mode with one-click role sign-in
  and safeguards, nightly demo refresh (Vercel Cron), runtime `BACKEND_URL`
  for Docker.

## Next steps (not started)

1. Payment provider integrations (card terminal, PromptPay confirmation).
2. Forecast features for holidays, promotions and weather; per-ingredient
   forecasts for stock not sold through recipes.
3. PostgreSQL `LISTEN/NOTIFY` (or a broker) behind the live-update stream for
   many hundreds of concurrent screens.
4. Multi-factor authentication and SSO for managers and administrators.
5. Nonce-based CSP to remove `'unsafe-inline'` for scripts.
6. Background jobs for long forecast runs on large menus.
7. Offline-tolerant POS (queue orders locally during network outages).
8. Complete the Thai translation of the interface.
