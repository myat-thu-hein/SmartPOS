# SmartPOS AI: frontend

Next.js 16 (App Router) web app for SmartPOS AI. See the
[repository README](../README.md) and [docs/](../docs) for the full picture.

```bash
npm ci
cp .env.example .env.local     # BACKEND_URL=http://localhost:8000
npm run dev                    # http://localhost:3000
```

| Script | Purpose |
| --- | --- |
| `npm run dev` | Development server (Turbopack) |
| `npm run build` / `npm start` | Production build (standalone output) and server |
| `npm run lint` / `npm run typecheck` | ESLint and TypeScript |
| `npm test` | Vitest unit and component tests (`tests/unit`) |
| `npm run test:e2e` | Playwright smoke tests (`e2e/`) against a running stack; needs `E2E_PASSWORD` |

Structure:

* `app/`: routes. `(app)/` is the signed-in area; `login`, `forgot-password`,
  `reset-password` and `receipts/[id]` sit outside the shell.
* `features/`: feature logic and dialogs (POS cart, purchasing, forecasting, menu, orders).
* `components/`: UI primitives (`ui/`), shared states, charts and layout.
* `lib/`: API client (`api.ts`), auth context, formatting, i18n, navigation, password rules.
* `proxy.ts`: redirects visitors without a session cookie to `/login`. This is
  a convenience only; the API enforces authentication and permissions.

All API calls go through `/api/v1` on the same origin, so cookies stay
first-party. In development and Docker, `app/api/v1/[...path]/route.ts`
forwards them to `BACKEND_URL`, read at runtime (no rebuild needed to change
it). On Vercel, `vercel.json` routes `/api/v1/*` straight to the FastAPI service.
