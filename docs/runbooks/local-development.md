# Local development

Run commands from the repository root in PowerShell. Install Docker Desktop (Linux containers) and start its engine first.

```powershell
Copy-Item .env.example .env
docker compose --env-file .env -f infrastructure/docker-compose.yml config --quiet
docker compose --env-file .env -f infrastructure/docker-compose.yml up --build
```

Compose runs PostgreSQL, Redis, MinIO, bucket initialization, a one-shot migration, FastAPI, a Celery worker and scheduler, and Next.js. Registered, permitted sources collect on schedule. AI drafting is available when configured; external publishing remains inactive. Ports bind to localhost. The `.env` values are development credentials only. If you change credentials, keep `DATABASE_URL` in sync for host-based commands; Compose constructs its internal database URL from `POSTGRES_*`.

Individual accounts replace the shared editor token. Configure AUTH_ENCRYPTION_KEY, the exact AUTH_ORIGIN and local-only AUTH_COOKIE_SECURE=false, recreate services, and run `docker compose --env-file .env -f infrastructure/docker-compose.yml exec api python -m app.auth.bootstrap`. Complete MFA at /login. See [Authentication and RBAC](../api/authentication-and-rbac.md) for key generation, secure production settings and reset delivery.

The first build takes several minutes: MinIO and its client are compiled from pinned upstream source releases because the original community container images are no longer available from Docker Hub/Quay. Subsequent starts reuse the local images. Docker Desktop must report its Linux engine as running; on Windows it needs WSL 2. Restart your terminal after installing Docker so its CLI is added to PATH.

Open the dashboard at http://localhost:3000, API docs at http://localhost:8000/docs, and MinIO console at http://localhost:9001 (credentials in `.env`). Readiness is http://localhost:8000/health/ready. The overview starts with real zero counts in an empty database.

## Checks

Manual Writing creates and explicitly saves persistent stories without external credentials. To enable AI drafting, set `OPENAI_API_KEY` and `OPENAI_MODEL` only in the root ignored `.env`, then recreate services with `docker compose --env-file .env -f infrastructure/docker-compose.yml up -d --build`. Do not overwrite an existing `.env` when upgrading. Compose passes these settings to backend services only. `AI_HOURLY_LIMIT` defaults to 20 jobs per editor. Keep the worker running and see the [AI and Manual Writing guide](../api/ai-and-manual-writing.md) for evidence permissions, preview/apply/save behavior, and error handling.

```powershell
npm ci
npm run lint
npm run typecheck
npm run build
docker compose --env-file .env -f infrastructure/docker-compose.yml exec api pytest
docker compose --env-file .env -f infrastructure/docker-compose.yml exec api ruff check .
docker compose --env-file .env -f infrastructure/docker-compose.yml exec api alembic check
```

## Host frontend and API

Node.js 22+ and Python 3.12+ are required. Start PostgreSQL and Redis through Compose:

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml up -d postgres redis minio media-init
npm ci
npm run dev
```

In a second terminal:

```powershell
py -3.12 -m venv services/api/.venv
services/api/.venv/Scripts/Activate.ps1
pip install -e "services/api[dev]"
# Load the root .env explicitly for the backend; run from the root.
alembic -c services/api/alembic.ini upgrade head
uvicorn app.main:app --reload --app-dir services/api
```

The API uses localhost defaults and loads the root `.env`. Next.js uses the localhost API default unless `API_INTERNAL_URL` is set in the shell or `apps/dashboard/.env.local`. For host frontend development, set the API URL and matching AUTH_ORIGIN; the Next.js proxy forwards individual session cookies. It needs no shared bearer credential.

## Database changes

Add models in their feature module and import them in `app/db/models.py`. Create a reviewed migration with `alembic revision --autogenerate -m "description"` from `services/api`, then run `alembic upgrade head`. Set `DATABASE_URL` in that shell when credentials differ from defaults. Never replace migrations with runtime `create_all()`.

## Shutdown and persistence

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml down
```

Named volumes preserve the database, Redis, and media across restarts. Removing volumes deletes local data. This Compose setup is for development only.

## Sources and Incoming Stories

Sources → Automatic Story Collection persists the display batch limit, new-source frequency default, draft-language default, scheduled source mode, preferred-category filters and global automatic collection toggle. Existing source intervals stay unchanged. Explicit Collect now remains available while automatic collection is paused. Source Archive/Restore retains all candidates and attribution; restored sources stay inactive until activated. See [Collection and Incoming Stories](../api/collection-and-incoming-stories.md) for exact semantics and API compatibility.

The Incoming Stories table browses real candidates and saved draft metadata. Edit Story creates/reopens one draft, and the shared editor provides right-side metadata, preview and a bottom save bar. Publishing counters clearly show their unavailable workflow; no delivery or sample-collection behavior is simulated.

## Browser workflow verification

The browser suite runs against a separate API and dashboard, with test-only accounts in a randomly named PostgreSQL schema. The opt-in test API deletes its own schema on graceful shutdown and cannot start without BNC_BROWSER_TEST=1. Never aim this harness at newsroom data or reuse its fixture passwords for real accounts.

1. In an API-container terminal, run `BNC_BROWSER_TEST=1 uvicorn tests.browser_server:app --host 0.0.0.0 --port 8002`.
2. Build the dashboard, then start a second dashboard process inside its container with `API_INTERNAL_URL=http://api:8002 npm run start --workspace @bnc/dashboard -- --port 3002`.
3. Install the browser runtime once in that container with `npx playwright install --with-deps chromium`.
4. From `/workspace/apps/dashboard`, run `npm run test:browser`.
5. Gracefully stop the test API (SIGTERM) to run schema cleanup, and stop the second dashboard process. Test traces/screenshots are ignored by Git.

The browser tests use genuine separate Writer/Editor sessions and authenticator enrollment for the test Superadmin. They verify required-field highlights, live warning removal, focus, conditional Instagram requirements, incomplete saves, exact-revision submission/approval/READY, hidden administration for writers, account creation/suspension/reactivation/soft-deletion and task assignment. Test account and editorial screenshots are captured for visual inspection.
## Simultaneous localhost and ngrok access

Keep AUTH_ORIGIN=http://localhost:3000 and the existing local AUTH_COOKIE_SECURE=false. Add this non-secret setting to the root .env without replacing its other contents:

```dotenv
AUTH_ADDITIONAL_ORIGINS=["https://trustable-detail-drift.ngrok-free.dev"]
```

Both API and dashboard read the same exact allowlist. Public origins must use HTTPS; paths, credentials and wildcards are rejected. An empty JSON array preserves localhost-only behavior. No CORS change is needed: browser requests go through the dashboard's same-origin API proxy. The proxy requires the Origin to be allowlisted and its host/port to match the actual Host header; forwarded host/protocol headers cannot authorize a request. Keep ngrok's original public Host header (do not use --host-header=rewrite).

Recreate only the API and dashboard to apply this change:

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml up -d --no-deps --force-recreate api dashboard
ngrok http --url=trustable-detail-drift.ngrok-free.dev 3000
```

To apply temporarily without editing .env, set `$env:AUTH_ADDITIONAL_ORIGINS='["https://trustable-detail-drift.ngrok-free.dev"]'` in that PowerShell session before the compose command. Future recreation must use the same setting (or add it to .env). Worker/scheduler recreation is unnecessary for browser authentication. No database, Redis, MinIO, migration or volume change is required. Only port 3000 is tunneled; ports 3000/8000 and infrastructure retain their loopback bindings.

Visit http://localhost:3000/login and https://trustable-detail-drift.ngrok-free.dev/login. Sign in and verify your authenticator separately at each hostname: host-only cookies intentionally do not share sign-in between addresses. Cookies retain HttpOnly, SameSite=Strict and Path=/ with no Domain. HTTPS trusted origins always get Secure cookies, even with the local HTTP setting false; AUTH_COOKIE_SECURE=true continues to force Secure everywhere. Logout/renewal/MFA rotation use the same rule. Account suspension, password reset and sign-out-all still revoke sessions across both addresses through the existing database. Password-reset emails continue to use the configured primary AUTH_ORIGIN.

The additional Next.js allowedDevOrigins entries contain only exact configured hostnames for development assets; the API proxy still validates the complete scheme/host/port. Never use a wildcard ngrok domain. The ngrok process must be running; the application does not install ngrok or manage its account credentials.

Run `pytest -q tests/test_auth_origins.py tests/test_accounts_workflow.py` in the API container and `npx playwright test --config apps/dashboard/playwright.proxy.config.ts` in the dashboard container at /workspace. These test real API login/MFA and session lifecycle in an isolated test database, and proxy behavior with a stubbed upstream response without real credentials.
