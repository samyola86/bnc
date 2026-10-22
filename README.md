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

Sources now centralizes Automatic Story Collection: batch size, new-source interval defaults, draft language, scheduled source mode, preferred-category filter preferences and a working global scheduler toggle. Sources can be archived/restored while retaining collected stories and attribution. Incoming Stories uses the editorial table with source pills, filters, saved draft tags/categories, author identity, ranking, pins, provenance and one-click editing. The shared editor includes a right-side metadata panel, preview and bottom save bar. Summary cards show real database counts and distinguish queued editorial requests from confirmed external delivery. See [Collection and Incoming Stories](docs/api/collection-and-incoming-stories.md) for exact defaults, overrides and API compatibility.

For AI drafting, set `OPENAI_API_KEY` and `OPENAI_MODEL` only in the root ignored `.env` (API and worker environment), then recreate the services with `docker compose --env-file .env -f infrastructure/docker-compose.yml up -d --build`. Choose a model supporting the Responses API and Structured Outputs. Blank credentials leave manual editing available and return a useful configuration error for AI requests. The dashboard never receives these values. An editor can generate Bengali or English copy from permitted RSS metadata or explicitly authorized reporting notes, edit the preview, confirm replacement, and save a new revision. Source provenance is retained, missing credits warn without blocking, and AI-assisted writing always requires human review.

The story editor also supports Article / News bite format, contributor bylines, private cover-image upload with alt text and credit, reporting notes, selectable platform destinations and Dhaka-time schedules. Send to publishing saves a revision-bound queue request; edits cancel stale requests. Send to Publishing now submits the exact saved revision for editorial review. Editors approve and authorize READY; external delivery still requires future connected adapters. See [Story media and queue](docs/api/story-media-and-queue.md).

Individual accounts now use three roles: SUPERADMIN, EDITOR and CONTENT_WRITER. Superadmins manage accounts, assignments, collection configuration and audit history. Writers edit owned/assigned drafts and submit for review; Editors review other users' exact revisions and authorize READY. Live readiness highlights, task history, MFA, secure reset/session revocation and explicit audited administrative exceptions are implemented. Before first sign-in, follow the [one-time Superadmin bootstrap](docs/api/authentication-and-rbac.md). See [Editorial approval](docs/api/editorial-approval.md) and [Task assignment](docs/api/task-assignment.md).

## Planned scope

TipTap rich text, complete taxonomy/media workflows, automatic scheduled platform delivery, SSE, and WordPress/social integrations. Individual HttpOnly server-side sessions now authenticate users; the legacy `INGESTION_API_TOKEN` is no longer accepted. Public RSS/Atom and JSON Feed collection needs no external API keys. The full publishing vertical slice in architecture section 19 remains planned; AI never publishes or approves stories.

The supplied logo is absent, so a text wordmark is used until the original asset is supplied; see `public/brand/README.md`. The available `html demo/Newsroom_Dashboard(2).html` supplies the editorial layout/workflow reference. Bengali/English input is supported, timestamps are stored in UTC, and the interface identifies Asia/Dhaka as the display timezone.
## Adaptive News Bite graphics

The existing Story Editor's **News bite** format supports four adaptive BNC templates,
English/Bengali typography, live 4:5 preview, focal cropping, exact 1080 × 1350 PNG export
and revision-bound graphic/caption approval. [Usage and implementation](docs/api/news-bite-templates.md)
· [Sample designs](docs/evidence/newsbite/contact-sheet.png). Rebuild API/worker/scheduler
images for Bengali text shaping; no new database migration or secret is required.
