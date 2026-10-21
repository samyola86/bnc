# AI drafts and persistent Manual Writing

**19 October 2026 update:** Individual account sessions and the three-role policy supersede the earlier shared-editor authorization described below. Send to Publishing now submits for exact-revision review; approval and READY authorization are implemented, while external delivery remains disabled. See [Authentication and RBAC](authentication-and-rbac.md), [Editorial approval](editorial-approval.md) and [Task assignment](task-assignment.md).

Both workflows use `stories`, immutable `story_versions`, and version-specific `story_sources` in PostgreSQL. Candidate provenance remains in the original feed records; there is no separate manual editorial system. AI generation never automatically submits, approves or publishes a story.

## Configure and run

Keep `OPENAI_API_KEY` and `OPENAI_MODEL` in the root, ignored `.env` or the backend's deployment secret environment. Choose a model available to your account that supports the Responses API and Structured Outputs. Both settings are required; blank settings disable generation with a clear 503 error. Never put them in `NEXT_PUBLIC_*`, frontend environment files, browser code, or Git.

Compose already passes the root environment to the API and worker, while the dashboard receives the API address and forwards individual session cookies. After changing backend environment settings:

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml up -d --build
```

The one-shot migration adds `ai_jobs`. Existing sources, stories, and revisions are preserved. Keep the Celery worker and Redis running; AI generation returns 202 and the editor polls job status. For host backend development, run a worker from the repository root with the API package installed: `celery -A app.workers.celery_app:celery_app worker --pool=solo --loglevel=info`. Settings load the root `.env`.

## Editor workflow

1. **RSS:** choose a News Feeds candidate, create/open its draft, and choose Bengali or English in the editor. Original credits and the immutable provenance panel are retained.
2. **Manual:** open Manual Writing, enter a headline and language, and create a saved draft. Reopen it from the paginated manual story list at any time.
3. Write manually and use **Save revision**, or open **AI News Generator**. Candidate drafting uses only stored, permitted feed headline/excerpt metadata. Manual drafting requires factual reporting notes and explicit confirmation that those notes may be sent to OpenAI. Existing writing is never automatically sent as evidence.
4. **Generate with AI** queues a job without changing the story. The preview contains editable headline, summary, body, category, tags, and Facebook/Instagram captions. Captions are text only; no platform is contacted. Warnings, claims to verify, and paragraph evidence references appear alongside the preview.
5. **Apply preview to editor** asks for confirmation before replacing writing fields, including unsaved text. Sources & Credits are preserved. Edit and verify the result, then explicitly **Save revision**. Reloading a saved draft also asks before discarding unsaved edits. Successful AI previews and active job status can be recovered after a page refresh.
6. Add/edit/remove publisher credits, optional URLs, attribution notes and original-reporting flags. Missing credits show a warning and `attribution_blocks_publishing: false`. They do not prevent saving. Rights and human review remain separate.

Save requests carry `base_version`. A stale save or AI preview based on an older saved revision returns 409. Reload and reconcile your writing, or generate a new preview. Applying AI preserves its job ID, verification warnings and `human_review_required` in the saved version; later human edits retain this marker. Story status stays `DRAFT`.

## Protected API

All paths below are under `/api/v1` and require an individual account session. The browser uses the same-origin allowlisted `/api/newsroom` proxy. Writers are limited to owned/assigned stories; generation is attributed and rate-limited to the authenticated account. Backend source/provider credentials stay server-side.

| Method | Path | Behavior |
| --- | --- | --- |
| POST | `/stories` | Create a manual draft and revision 1. Requires `title`; accepts language, summary, body, category, tags, captions and credits. |
| GET | `/stories?origin=manual` | Paginated manual stories, with latest title, version, language, status and credit warnings. `origin=candidate` or `all` is also supported. |
| GET / PATCH | `/stories/{id}` | Retrieve/save either manual or candidate stories. PATCH requires `base_version` and creates an immutable revision. |
| GET | `/stories/{id}/versions` | Paginated saved revision content, newest first. |
| POST | `/stories/{id}/ai-draft` | Queue generation with `base_version`, `language` (`bn`/`en`), optional `reporting_notes`, and `notes_permitted`. Returns 202 and `job_id`. |
| GET | `/ai/jobs/{id}` | Durable job state, useful message, validated result, model, usage and timestamps. |
| GET | `/stories/{id}/ai-jobs` | Ten most recent jobs, allowing editor recovery after refresh. |

PATCH accepts `ai_job_id` when saving an applied preview. The job must have succeeded, belong to this story, and match the saved base revision. Existing writing and attribution remain unchanged by requests, failures, or previews. Normal explicit credit edits are versioned separately from immutable feed provenance.

## Evidence, limits and errors

The backend calls `POST https://api.openai.com/v1/responses` with `store: false`, a strict `text.format` JSON schema and a 6,000-token output cap. See the official [Structured Outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses). It sends no tools, performs no article scraping or URL fetching, and treats source strings as untrusted data. Outputs must match the requested language and cite evidence IDs actually supplied in the packet. Headlines, summaries, article paragraphs, classification, tags and captions are generated together. Schema validity and evidence IDs do not establish factual accuracy; editors must verify every claim.

Historical and current source rights must permit using the metadata (`metadata_only`, `licensed`, or `owned`) and collection mode must be `metadata`. Prohibited, reference-only, unknown-rights or evidence-free candidates need separately permitted reporting notes. A deduplicated item has one canonical excerpt; when any recorded source disallows its use, the backend conservatively excludes that excerpt. Permissions are checked again before worker execution. Sparse feed metadata should produce a short cautious draft, never an invented full report.

Jobs store model, template version, evidence snapshot, input hash, validated output, token usage, state and timestamps. No API keys or raw provider errors are stored in jobs or returned to clients. Evidence snapshots contain editorial material; apply your normal database access and backup policies. Costs are not estimated from hardcoded prices. Set provider project budgets separately.

There is one running job per story and a configurable per-editor hourly limit (`AI_HOURLY_LIMIT`, default 20). No automatic provider retries or batch generation incur unexpected repeated costs. Requests have a 90-second HTTP timeout and Celery execution limits. Abandoned jobs expire after five minutes when observed or retried. Missing credentials, queue outages, provider authentication/quota/server errors, timeouts, refusals, incomplete responses, invalid JSON/schema, wrong languages and invented evidence references leave saved writing unchanged and return actionable messages.

## Verification

Run frontend lint, typecheck and build as in the local runbook. Run backend tests, including PostgreSQL integration cases, with:

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml exec -T api sh -c 'BNC_TEST_DATABASE_URL="$DATABASE_URL" pytest -q'
docker compose --env-file .env -f infrastructure/docker-compose.yml exec -T api ruff check .
docker compose --env-file .env -f infrastructure/docker-compose.yml exec -T api alembic check
```

Tests exercise the Responses HTTP contract with a mocked provider, schema/error handling, RSS-to-AI-to-edited-version persistence, manual creation/listing/history/credits, stale previews, authorization, quotas and isolated PostgreSQL concurrency. They require no paid OpenAI requests. A live provider smoke test requires valid server credentials and model access; test results from the mock do not claim live model quality or factual verification.
