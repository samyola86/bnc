# Initialization verification

Verified on 19 October 2026:

- Frontend ESLint: passed without warnings.
- TypeScript: passed.
- Next.js production build: passed; all nine navigation destinations generated.
- Production HTTP smoke check: all nine destinations returned HTTP 200 with the navigation shell.
- Backend: six tests passed, including live-count queries, sanitized database errors, trace IDs, and migration upgrade/downgrade with model consistency checks using SQLite.
- Backend Ruff lint and formatting: passed.
- Compose YAML: parsed successfully. This is a syntax check, not Docker Compose runtime validation.
- Initial migration: compiled successfully to PostgreSQL SQL with UUID keys and timezone-aware timestamps.
- Runtime npm dependency audit: zero reported vulnerabilities.

## Docker follow-up verification

Docker Desktop and WSL 2 are now installed. The application images build successfully, and PostgreSQL, Redis, the API, dashboard, Celery worker, and scheduler run in containers. The initial migration completed successfully against PostgreSQL; `alembic check` reports no schema drift. All six API tests pass inside the API container. All nine dashboard routes return HTTP 200, and the overview reports a connected editorial database. The API readiness endpoint confirms PostgreSQL and Redis connectivity. A `bnc.healthcheck` task was queued through Redis and executed successfully by the Celery worker.

The original MinIO images could not be pulled from Docker Hub or Quay. The Compose configuration now builds the pinned upstream server/client source releases using `infrastructure/minio/Dockerfile`. Both images built successfully. MinIO reports healthy, the `bnc-media` bucket was created, and the bucket initializer exited with code 0. The storage readiness endpoint and console both return HTTP 200. All seven long-running services are running; the migration and bucket initialization services exited successfully as intended.

The full npm audit reports five high-severity entries in one development dependency chain: `eslint-config-next` → `@next/eslint-plugin-next` → `fast-glob` → `micromatch` → `braces` (GHSA-vfj7-8cjw-p6xm). No compatible fix was reported by npm. Recheck when upstream releases a fix; the runtime dependency audit is clean. The backend test tooling also emits an upstream Starlette warning about its httpx test client.

## Sources and News Feeds verification

The ingestion/draft suite passes 49 tests inside Docker, including isolated PostgreSQL concurrency checks, worker imports in a fresh process, source discovery, RSS/Atom/JSON Feed parsing, original publisher metadata, permissions, DNS pinning/SSRF checks, robots/redirect restrictions, rate limiting, deduplication, scheduling, batch pagination, immutable revisions, and non-blocking credit warnings. Frontend ESLint, TypeScript, and the Next.js production build pass. The deployed database migration reports no schema drift.

Live HTTP checks cover the Sources, News Feeds, draft, and server proxy routes. Real Celery collection of the BBC Bangla public RSS feed produced 14 candidates; another collection preserved the same 14 canonical candidates. A real Beat tick also scheduled and completed collection. An attributed candidate draft was created and edited successfully. Browser automation was unavailable in this environment, so no visual/browser interaction check is claimed. See [Sources and feeds](../api/sources-and-feeds.md) for supported formats, APIs, and reproduction steps.

## AI News Generator and Manual Writing verification

- Complete backend suite: **76 passed** inside Docker, including isolated PostgreSQL persistence and concurrency tests. The existing upstream Starlette/httpx test-client deprecation warning remains.
- New tests cover the Responses HTTP request/schema contract, Bengali/English output validation, unknown evidence references, refusals, incomplete/invalid output, provider credentials/quota/server failures, timeouts, missing configuration, queue outages, changed source permissions, duplicate deliveries, per-editor limits, and stale/foreign previews.
- The RSS-to-AI-preview-to-human-edited-saved-version workflow passes with a mocked Responses provider. Manual stories persist in the same PostgreSQL story/version system, retain credit warnings, support listing/reopening, and reject simultaneous stale saves. Two simultaneous generation requests reserve only one job.
- Frontend ESLint and TypeScript pass. The Next.js production build passes, including `/manual-writing`, `/manual-writing/[id]`, and the existing candidate editor. The Windows sandbox initially denied a build worker process; the production build completed with process execution permission.
- The additive AI job migration upgraded the existing local PostgreSQL database, and `alembic check` reports no schema drift. Ruff checks pass across the API and migrations.
- Live Docker HTTP checks pass for Manual Writing, News Feeds, Sources, the manual editor, create/save/retrieve/list/history APIs, missing AI credentials, stale writes, cross-origin rejection and API authorization. A clearly labelled local verification draft was saved as revision 2. Celery responds and registers `bnc.generate_draft` alongside the existing ingestion tasks.
- `OPENAI_API_KEY` and `OPENAI_MODEL` are unset in the local backend. No paid OpenAI request was made; live provider output and model quality have not been verified. Configure both server-side to enable live generation. Browser interaction/visual checks are not claimed.

See [AI and Manual Writing](../api/ai-and-manual-writing.md) for the setup and workflow. AI previews do not save or publish automatically; editors confirm applying a preview and explicitly save the reviewed writing.

## Sources and Incoming Stories parity verification

Verified on 19 October 2026:

- **91 backend tests passed**, with PostgreSQL integration tests enabled in isolated schemas. The existing upstream Starlette/httpx deprecation warning remains. A prior overlapping run hit the existing worker-import subprocess timeout; the final complete run passed, including that test.
- New checks cover persisted collection defaults, preservation of existing intervals and batch settings, per-source/story language overrides, global scheduler pause/mode restrictions, policy changes during fetch, explicit manual collection while paused, and reuse of pending scheduled jobs for an explicit manual request.
- Archive/restore checks preserve candidates, credits, revisions and original provenance in SQLite and PostgreSQL. Queue checks cover saved category/tags, author identity, source/history filters, preferred categories, idempotent draft reopening and non-blocking missing-credit warnings. Publication summary tests count distinct stored stories across destinations while retaining the unavailable workflow state.
- Frontend ESLint, TypeScript and the Next.js production build pass. Ruff passes; the additive migration upgraded the local PostgreSQL database and `alembic check` reports no drift. Migration upgrade/downgrade and preservation checks pass.
- Live Docker HTTP checks pass for Sources, Incoming Stories, Manual Writing, the shared editor, persisted settings, summary and editorial metadata endpoints, saved-headline filtering, reopening an existing revision, API authorization and readiness. A real Celery RSS collection succeeded with **0 new candidates, 14 duplicates, 0 skipped**, preserving deduplication. The worker responds to readiness checks.
- Browser inventory was empty and the in-app browser was unavailable. No visual or browser-interaction verification is claimed. No paid OpenAI request was made for this change; its provider and model configuration were preserved. Publishing, custom API adapters and full article extraction remain unimplemented.

See [Collection and Incoming Stories](../api/collection-and-incoming-stories.md) for the settings semantics and additional API fields. Production contains no sample collection or simulated publishing.
