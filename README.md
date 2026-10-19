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

All nine navigation destinations, responsive sidebar, and overview with database counts and connection state. Sources supports registration, testing, website feed discovery, activation, frequency, and manual collection. News Feeds displays real attributed candidates with filtering, ranking, pins, editorial status, and configurable 20–50 item batches. Candidate drafts have a full-page editor with immutable revisions, optimistic concurrency, and editable Sources & Credits. The original Manual Writing preview remains separate.

FastAPI provides health endpoints, dashboard counts, and the protected source/ingestion/draft APIs. PostgreSQL stores feeds, deduplicated candidates, feed provenance, collection jobs, revisioned credits, audit events, and queue configuration. Celery and Redis handle scheduled collection, per-origin rate limiting, and job execution; MinIO provides private local object storage. See the [Sources and feeds guide](docs/api/sources-and-feeds.md) for behavior and tests.

## Planned scope

Per-user authentication/MFA, TipTap rich text, editorial approvals, complete taxonomy/media workflows, publication scheduling, SSE, and AI/WordPress/social integrations. The source modules use a server-only local editor credential shared by Next.js and FastAPI; generate `INGESTION_API_TOKEN` in `.env`. Public RSS/Atom and JSON Feed collection needs no external API keys. The separate Manual Writing preview does not save data. The full publishing vertical slice in architecture section 19 remains planned.

The supplied logo and legacy `Newsroom_Dashboard.html` were absent from the repository. A text wordmark is used until the original asset is supplied; see `public/brand/README.md`. Bengali/English input is supported, timestamps are stored in UTC, and the interface identifies Asia/Dhaka as the display timezone.
