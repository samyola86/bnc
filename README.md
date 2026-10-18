# BNC News Dashboard

Bangladesh News Corporation's modular newsroom foundation, based on [the architecture specification](docs/architecture.md).

## Run locally

Install Docker Desktop and start its Linux container engine. From this folder:

```powershell
Copy-Item .env.example .env
docker compose --env-file .env -f infrastructure/docker-compose.yml up --build
```

- Dashboard: http://localhost:3000
- FastAPI documentation: http://localhost:8000/docs
- MinIO console: http://localhost:9001

Compose automatically applies migrations before starting the API. See the [local development runbook](docs/runbooks/local-development.md) for host development, verification, environment variables, and shutdown.

## Repository

```text
apps/dashboard/                 Next.js App Router, TypeScript, Tailwind CSS 4
  components/{ui,layout}/        Local shadcn/ui primitives and reusable shell
  features/{overview,stories}/  Feature components
  public/brand/                 Supplied BNC logo location
services/api/
  app/api/v1/                   Versioned FastAPI routes
  app/{auth,db,editorial}/       Identity and revision model boundaries
  app/{ingestion,ai,media}/      Future ingestion, AI, media modules
  app/publishing/adapters/       Future independent destination adapters
  app/{analytics,workers}/      Analytics and Celery
  alembic/                      Versioned database migrations
  tests/                        API contracts and model checks
infrastructure/                 Local Docker Compose stack
integrations/wordpress-plugin/  Reserved companion plugin boundary
docs/                           Architecture, API, policy, and runbooks
```

## Implemented scope

All nine navigation destinations, responsive sidebar, overview with database counts and connection state, full-width writing layout preview, and clear empty states. The frontend uses locally owned shadcn/ui-style Button and Card components, a Radix Slot primitive, shared design tokens, and `components.json` for adding components with the shadcn CLI.

FastAPI provides liveness/readiness and a read-only `/api/v1/dashboard/overview`. The initial PostgreSQL migration covers users, sources, stories, story revisions, channels, and publications, with UUID keys, timezone-aware timestamps, revision uniqueness, foreign keys, and state checks. Celery uses Redis; MinIO provides private local object storage and bucket provisioning.

## Planned scope

Authentication/RBAC, persisted editing with TipTap, approval/audit records, complete source/feed and taxonomy schemas, media upload, revision conflicts, scheduling, SSE, and all external integrations. The writing preview does not save data. No external API keys are required or used. This initialization does not implement the full vertical slice in architecture section 19.

The supplied logo and legacy `Newsroom_Dashboard.html` were absent from the repository. A text wordmark is used until the original asset is supplied; see `public/brand/README.md`. Bengali/English input is supported, timestamps are stored in UTC, and the interface identifies Asia/Dhaka as the display timezone.
