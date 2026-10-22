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

## Story editor media and publishing queue verification

Verified on 19 October 2026:

- **103 backend tests passed**, with isolated PostgreSQL integration checks and an opt-in real MinIO upload/read test enabled. The MinIO test removes only its own generated object. The existing Starlette/httpx deprecation warning remains.
- New regression coverage checks revision persistence of format, contributors, image references, captions and notes; compatibility with older save clients; immutable history; stale-write rejection; queue idempotency; cancellation on edits; required publishing metadata; Instagram image requirements; timezone/future schedule validation; non-blocking missing credits; and authorization.
- Image checks cover supported raster formats, decoded size/dimension limits, private storage round trips and invalid data. A final targeted run also verified truncated-image rejection: **11 passed, 1 skipped** (the opt-in real storage check was not enabled for that targeted run).
- Ruff, frontend ESLint, TypeScript and the final Next.js production build pass. The additive publishing-request migration applied successfully; `alembic check` reports no schema drift.
- Live HTTP checks returned 200 for Overview, Manual Writing, Publishing, the publishing queue proxy, summary and source listing. The existing BBC World source remains registered. Local sources and collected stories are database data, not repository seed files.
- No browser was available in the automation inventory, so visual/browser interaction verification is not claimed. No paid AI request or external platform publication was made.

The app preserves AI draft review, versioned source credits and original feed provenance. The new Publishing page stores revision-bound requests with selectable destinations and Dhaka-time schedules. It does not dispatch posts, grant editorial approval, simulate confirmed delivery, retry remote jobs or publish automatically at the requested time. Platform adapters and credentials are still required for those workflows. See [Story media and queue](../api/story-media-and-queue.md).
## Individual accounts, assignments and editorial approval

Verified on 19 October 2026:

- **114 backend tests passed**, with BNC_TEST_DATABASE_URL and BNC_TEST_MEDIA enabled. Tests use isolated PostgreSQL schemas and SQLite databases. The suite covers real account login/logout/renewal, Argon2id verification, MFA enrollment/replay/rate limits, reset single use/session revocation, expiry, suspension/deletion/demotion, last-Superadmin/self-lockout rules, forbidden administrative routes, writer ownership/assignment checks, task status/history/reassignment, exact-revision decisions and explicit self-approval exceptions.
- PostgreSQL concurrent approval tests confirm exactly one of two simultaneous decisions succeeds and exactly one approval event is retained. Migration tests preserve legacy user IDs, story ownership, immutable revisions, pending requests and audit references while disabling legacy shared identities without privilege elevation. Upgrade/downgrade metadata checks pass.
- The complete linked assignment → Writer draft → submission → independent Editor approval → task completion → READY path passes. A final targeted rerun of that path also passed. Suspended accounts cannot execute a pending AI provider job. Existing RSS, AI preview, source/provenance, media round-trip and revision regression tests pass without paid provider calls.
- **Two Chromium browser scenarios passed** against an opt-in test API in a disposable PostgreSQL schema: real Writer/Editor readiness/submission/approval/READY; and Superadmin MFA, account creation, suspension/reactivation/soft-deletion, and task-assignment screens. Field highlights, first-invalid focus, live warning removal, conditional Instagram checks, incomplete saves and hidden administrative navigation are asserted. Captured review/account-management screenshots were inspected. Browser testing found and fixed changing accessible field names and a sidebar footer overlapping administration links.
- Python Ruff, frontend ESLint, TypeScript and the Next.js production build pass. A fresh dashboard image installed successfully with npm ci from the updated lockfile. The live migration is e41b02a77d31; alembic check reports no schema drift.
- The only backend warning is the existing upstream Starlette/httpx test-client deprecation. The existing five high-severity development dependency audit entries remain outside this implementation; no forced dependency upgrades were applied.
- No real reset email, paid OpenAI request or external platform publication was performed. SMTP reset delivery is tested through a replacement mail sender. Production deployment requires TLS, Secure cookies, a fixed encryption key, MFA enrollment and working SMTP. MFA backup codes/recovery UI, expired-auth-record retention automation, notification delivery and account-list pagination beyond 200 records are not implemented.

The shared bearer token no longer authenticates dashboard users. Existing stories, jobs, source provenance, private images and old preparation requests are retained. No default Superadmin credentials were created in the newsroom database: use the documented interactive bootstrap. The local encryption key is kept in the ignored .env file. Actual platform delivery remains deliberately excluded; READY does not mean PUBLISHED.
Final live smoke checks: /login and API readiness returned HTTP 200; anonymous story access through the Next.js proxy returned 401. The newsroom database still contains its registered source and stored stories/revisions, and no browser-test schemas remain. The MFA encryption key validates without being printed. There are no active Superadmins until the operator completes interactive bootstrap; this is intentional, not a default-password fallback.
## Publishing submission timestamp repair

The local publishing_requests table had missing created_at and updated_at defaults, causing valid review submissions to fail with a not-null constraint error and HTTP 503. Migration f52c04b81a22 restores both defaults without changing existing rows and preserves them on downgrade, as the preceding schema already requires them.

The PostgreSQL regression removes these defaults in an isolated schema, applies the repair twice, then submits a story through the API and verifies persisted timestamps. All 11 targeted PostgreSQL review and account workflow tests pass; Ruff passes. The repair is applied locally and alembic check reports no new upgrade operations. The affected saved story also submitted successfully in a rollback-only transaction, leaving its draft state unchanged for the user to submit.

## Localhost and ngrok trusted-origin access

Added strict AUTH_ADDITIONAL_ORIGINS validation alongside the backward-compatible primary AUTH_ORIGIN. The FastAPI CSRF boundary and Next.js same-origin proxy accept only exact configured origins; the proxy additionally requires Host to match Origin and does not use forwarded host/protocol as authority. HTTPS cookie issuance, MFA verification, renewal and deletion always use Secure, while the existing local HTTP setting and forced-Secure production policy remain intact. Cookies retain HttpOnly, SameSite=Strict, Path=/ and no Domain.

Verification: 130 backend tests passed, 1 test skipped; 9 proxy tests passed. Backend coverage includes Writer/Superadmin MFA and session lifecycle on both origins, cookie host isolation, invalid origins, forwarding-header spoofing and production Secure policy. Ruff, frontend ESLint/TypeScript and the Next.js production build passed. The broader suite also exposed SQLite incompatibility in the previously pending timestamp-default repair; it now uses Alembic batch alteration and migration tests pass.

The API and dashboard were recreated with AUTH_ADDITIONAL_ORIGINS supplied through the process environment; the existing .env was not edited. A hidden ngrok process forwards only the requested public hostname to localhost:3000. Live localhost and ngrok login pages and the public Next.js asset returned 200, invalid credentials from valid origins reached authentication (401), and untrusted origins returned 403. No live account credentials or MFA secrets were used by these smoke checks. Add the documented non-secret variable to .env for future Compose recreations. Backend ports, database configuration, credentials and Docker volumes were preserved.

## Adaptive News Bite graphics — 22 October 2026

Four supplied references were inspected and renamed by their actual visual identity,
correcting doubled PNG extensions and swapped design labels. The four programmatic
templates preserve distinct newspaper, dark editorial, breaking-news and magazine styling.
They are adaptive recreations at 4:5, not pixel-perfect copies of the taller references.
Photo-safe text zones, bundled fonts and some decorations differ intentionally. No
reference screenshot is used as a background or exported as a finished template.

The final complete backend suite passed **175 tests** with PostgreSQL and real media checks
enabled. Including explicit PostgreSQL News Bite history and artifact/caption checks,
the final targeted graphics suite passed **44 tests**. Coverage includes all four
templates with 5/15/30/50-word English and Bengali headlines; bounded wrapping or explicit
overflow; invalid highlight ranges; landscape, portrait, square, low-resolution and
edge-subject crops; source-image preservation; deterministic 1080 × 1350 PNGs; byte equality
between preview and the saved graphic; JSON save/reopen; immutable revisions; stale writes;
rights/captions; ownership and Writer restrictions; exact-revision approval/READY and
approval invalidation after crop/caption edits. The existing Starlette test-client
deprecation warning remains.

Chromium passed the new full News Bite scenario, both AI-preview scenarios and the
existing Article readiness/Writer-to-independent-Editor approval scenario together.
The separate existing Superadmin MFA/account/task scenario also passed. News Bite browser
coverage includes template gallery switching without lost input, live text/image preview,
saved crop/template/caption restoration, explicit overflow, exact 1080 × 1350 download,
preview/download byte equality, enlargement, Article preservation and the actual saved
PNG in the review screen. Browser testing found and fixed a save-refresh race that could
otherwise overwrite typing immediately after saving a revision.

Frontend ESLint, TypeScript, the normal Turbopack `npm run build`, an isolated webpack
production build and all **9 proxy security tests** passed. `alembic check` reports no
new upgrade operations. No migration is needed: configuration and render metadata use
the existing immutable story JSON. Private originals and new rendered assets use the
existing media bucket and authenticated retrieval routes.

Full-size examples and eight browser screenshots are in
[`docs/evidence/newsbite`](../evidence/newsbite/). Both English and Bengali contact sheets
were visually inspected, including short/long examples of every template. Samples use the
already supplied newsroom background rather than extracting the reference photographs.
See [News Bite templates](../api/news-bite-templates.md) for exact constraints, known
differences, API/storage details and reproduction. No real account was used, no newsroom
story was changed by the browser tests, no paid AI call was made, and nothing was sent to
an external publishing platform. Browser databases use disposable schemas.

### Photographic-template visual correction

The earlier Dark Editorial and Breaking News compositions did not match the supplied
references: they placed photographs in separate frames and changed the typography and
rail proportions. Both are corrected as template/layout version 2, with full-background
photos, geometric Poppins English typography, Bengali shaping, centered tracked branding,
date treatment, smooth lower fades, quotation and social motifs, right-side CTA, curved
red corners, and a fixed 300px outlined breaking-news rail. The first highlighted phrase
starts a separate line without changing stored text. Output remains 1080 × 1350.

The full backend suite passes **196 tests**. The final typography passes **22 targeted
layout/parity/approval checks**, and the final corner/fade changes pass both photographic
pixel-regression checks. The updated Chromium News Bite scenario passes, including
version-2 save/reopen, exact PNG download, Article preservation and submission review.
ESLint, TypeScript, Ruff and the normal production build pass. The reference-text
[before/after comparison](../evidence/newsbite/correction/before-after.png) and native
PNG examples were inspected. Examples use BNC's supplied newsroom photo; no photograph
was extracted from the reference designs.

Version-1 rendering remains available for existing saved graphics. Clicking a photo
template selects version 2; existing drafts offer **Use matching reference layout**.
Saving creates a new revision and invalidates prior approval. Previously approved PNGs
are never replaced in place. No migration or authentication change is introduced.
