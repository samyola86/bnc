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
  app/{ingestion,ai,media}/      Ingestion, AI drafting, and future media modules
  app/publishing/adapters/       Future independent destination adapters
  app/{analytics,workers}/      Analytics and Celery
  alembic/                      Versioned database migrations
  tests/                        API contracts and model checks
infrastructure/                 Local Docker Compose stack
integrations/wordpress-plugin/  Reserved companion plugin boundary
docs/                           Architecture, API, policy, and runbooks
```

## Implemented scope

All nine navigation destinations, responsive sidebar, and overview with database counts and connection state. Sources supports registration, testing, website feed discovery, activation, frequency, and manual collection. News Feeds displays real attributed candidates with filtering, ranking, pins, editorial status, and configurable 20–50 item batches. Candidate drafts and Manual Writing share a full-page editor with PostgreSQL persistence, immutable revisions, optimistic concurrency, tags, captions, and editable Sources & Credits. Manual stories can be created, listed, reopened and explicitly saved.

FastAPI provides health endpoints, dashboard counts, and the protected source/ingestion/story/AI APIs. PostgreSQL stores feeds, deduplicated candidates, feed provenance, collection jobs, revisioned credits, AI jobs, audit events, and queue configuration. Celery and Redis handle scheduled collection, per-origin rate limiting, and AI draft execution; MinIO provides private local object storage. See the [Sources and feeds guide](docs/api/sources-and-feeds.md) and [AI and Manual Writing guide](docs/api/ai-and-manual-writing.md) for behavior and tests.

For AI drafting, set `OPENAI_API_KEY` and `OPENAI_MODEL` only in the root ignored `.env` (API and worker environment), then recreate the services with `docker compose --env-file .env -f infrastructure/docker-compose.yml up -d --build`. Choose a model supporting the Responses API and Structured Outputs. Blank credentials leave manual editing available and return a useful configuration error for AI requests. The dashboard never receives these values. An editor can generate Bengali or English copy from permitted RSS metadata or explicitly authorized reporting notes, edit the preview, confirm replacement, and save a new revision. Source provenance is retained, missing credits warn without blocking, and AI-assisted writing always requires human review.

## Planned scope

Per-user authentication/MFA, TipTap rich text, editorial approvals, complete taxonomy/media workflows, publication scheduling, SSE, and WordPress/social integrations. The source and story modules use a server-only local editor credential shared by Next.js and FastAPI; generate `INGESTION_API_TOKEN` in `.env`. Public RSS/Atom and JSON Feed collection needs no external API keys. The full publishing vertical slice in architecture section 19 remains planned; AI never publishes or approves stories.

The supplied logo and legacy `Newsroom_Dashboard.html` were absent from the repository. A text wordmark is used until the original asset is supplied; see `public/brand/README.md`. Bengali/English input is supported, timestamps are stored in UTC, and the interface identifies Asia/Dhaka as the display timezone.
