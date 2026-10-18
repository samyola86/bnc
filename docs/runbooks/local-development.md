# Local development

Run commands from the repository root in PowerShell. Install Docker Desktop (Linux containers) and start its engine first.

```powershell
Copy-Item .env.example .env
docker compose --env-file .env -f infrastructure/docker-compose.yml config --quiet
docker compose --env-file .env -f infrastructure/docker-compose.yml up --build
```

Compose runs PostgreSQL, Redis, MinIO, bucket initialization, a one-shot migration, FastAPI, a Celery worker and scheduler, and Next.js. There are no scheduled external jobs. Ports bind to localhost. The `.env` values are development credentials only. If you change credentials, keep `DATABASE_URL` in sync for host-based commands; Compose constructs its internal database URL from `POSTGRES_*`.

Open the dashboard at http://localhost:3000, API docs at http://localhost:8000/docs, and MinIO console at http://localhost:9001 (credentials in `.env`). Readiness is http://localhost:8000/health/ready. The overview starts with real zero counts in an empty database.

## Checks

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

The API uses localhost defaults and loads the root `.env`. Next.js uses the localhost API default unless `API_INTERNAL_URL` is set in the shell or `apps/dashboard/.env.local`.

## Database changes

Add models in their feature module and import them in `app/db/models.py`. Create a reviewed migration with `alembic revision --autogenerate -m "description"` from `services/api`, then run `alembic upgrade head`. Set `DATABASE_URL` in that shell when credentials differ from defaults. Never replace migrations with runtime `create_all()`.

## Shutdown and persistence

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml down
```

Named volumes preserve the database, Redis, and media across restarts. Removing volumes deletes local data. This Compose setup is for development only.
