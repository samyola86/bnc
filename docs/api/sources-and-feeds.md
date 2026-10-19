# Sources, feeds, and candidate drafts

## Supported source types

| Type | Collection behavior |
| --- | --- |
| RSS / Atom | Reads the supplied public feed URL. |
| Website | Reads the permitted landing page and discovers advertised `rel="alternate"` RSS, Atom, or JSON Feed links. Editors may select a discovered feed or enter a direct feed URL. No full article extraction is attempted. |
| JSON Feed | Supports JSON Feed 1 and 1.1. |
| Public API | Accepts public endpoints returning RSS, Atom, or JSON Feed. Other schemas return an explanatory adapter-required result. API credentials and custom vendor adapters are not implemented. |
| Manual reference | Registers a publisher and URL without fetching or scheduling collection. |

Every source has publisher, URL, optional feed URL, language, default category, rights, collection mode, frequency (5–1440 minutes), active state, and notes. Inactive, reference-only, manual, and prohibited sources do not collect. Changing a source during a running fetch invalidates stale results before they can be stored.

Test Source can run before saving a source. Valid tests show discovered feed choices and up to three sample headlines. Saving does not require a successful test: unsupported references remain manageable with visible errors. A website without an advertised supported feed is not scraped.

## Local editor access

All endpoints below require `Authorization: Bearer <INGESTION_API_TOKEN>`. The token stays in the API/Next.js server environment. The localhost dashboard uses a same-origin, allowlisted Next.js proxy at `/api/newsroom/*`; it never includes the token in browser bundles. Mutation requests to that proxy require a matching `Origin` and JSON content type.

The credential maps to an active local source editor, and mutations create audit events. A disabled identity or a non-editor role is rejected. This is a development editor boundary, not a per-user session/MFA implementation. Do not expose this local dashboard as a shared authenticated newsroom until user sessions are implemented.

## API routes

All backend paths are prefixed with `/api/v1`.

| Method | Path | Result |
| --- | --- | --- |
| GET / POST | `/sources` | Cursor-paginated registry / create a source. |
| PATCH | `/sources/{id}` | Update source fields, activation, frequency, or permissions. |
| POST | `/sources/test` | Test an unsaved URL/type/permissions configuration. |
| POST | `/sources/{id}/test` | Test a registered source and update its health. |
| POST | `/sources/{id}/collect` | Queue a durable collection job; returns 202 and `job_id`. |
| POST | `/feeds/{id}/refresh` | Queue collection for a registered feed. |
| GET | `/ingestion/jobs/{id}` | Observe PENDING, RUNNING, SUCCEEDED, FAILED, or SKIPPED. |
| GET / PATCH | `/ingestion/settings` | Read/update the persistent candidate batch size (20–50, default 30). |
| GET | `/feeds/items` | Ranked candidates with publisher, category, publication date, original link, status, and structured attribution. |
| PATCH | `/feeds/items/{id}` | Select/dismiss, pin, or edit ranking inputs/override. |
| POST | `/feeds/items/{id}/draft` | Idempotently create an attributed candidate draft. |
| GET / PATCH | `/stories/{id}` | Read/edit candidate or manual drafts. Saves require `base_version`; stale saves return 409. |

`GET /feeds/items` accepts `status`, `source_id`, `query`, `category`, and `cursor`. An opaque ranking cursor retrieves another batch using a fixed freshness clock, so new arrivals before the cursor do not duplicate previously viewed stories. Changing filters requires a fresh cursor. The batch limit is persisted independently of how many articles the collector stores. A feed with 14 valid items shows 14 candidates, not fabricated placeholders. Inactive sources are excluded from candidate views; stored provenance is retained.

## Collection and deduplication

Celery Beat dispatches due sources once per minute. PostgreSQL row locks reserve work; per-source leases and idempotent job execution prevent overlapping collection. Frequency, jitter, exponential backoff, publisher rate limits, and stale-job recovery apply independently to each source. Both successful and failed jobs retain their status and result counts.

The collector uses conditional ETag/Last-Modified requests. It stores plain headline/summary metadata, author, category, date, canonical URL, content hash, and source occurrences. It does not retrieve full article pages or publisher photographs. At most 500 entries are processed per bounded feed response; skipped entries are reported.

`ingested_items` holds unique canonical candidates. `feed_entries` keeps every feed occurrence and its source publisher, original URL, rights, publication time, and retrieval time. An original publisher explicitly named in RSS/Atom item source metadata takes precedence over the registered feed owner; when absent, the editor-supplied registry publisher is retained. Unique canonical URL/content hash and feed/GUID constraints prevent repeat and concurrent duplication without treating syndicated copies as independent corroboration.

Ranking follows the architecture's weighted heuristic: .30 relevance + .25 public impact + .20 freshness + .15 corroboration + .10 uniqueness. Relevance, impact, and uniqueness begin at 50; corroboration begins at 0. Freshness declines over 72 hours, with unknown dates receiving 25. Editors can change inputs, override scores, and pin candidates. No AI verification or automatic factual corroboration is performed.

## Request and content controls

Only public HTTP(S) destinations on standard ports are accepted. Private/local/reserved DNS answers are rejected. Connections use validated IP addresses while preserving Host, TLS SNI, and certificate verification, preventing a second DNS resolution from bypassing the check. Redirect targets are revalidated and checked against robots policy before retrieval. Environment proxies are disabled.

Robots restrictions, access-denied responses, rate limits, positive crawl delays, and request-rate directives are respected. A shared Redis limiter coordinates origin requests across workers and manual tests. Very long declared delays fail with an explanation rather than being ignored. Responses are bounded to 2 MB and a request deadline; compressed responses that ignore the uncompressed request are rejected. XML DTDs/entities are rejected; HTML metadata is converted to plain text and never rendered as raw HTML.

## Attribution and editing

Open a candidate's **Create draft** action to enter the full-page editor under `/news-feeds/drafts/{id}`. The headline and metadata summary are prepopulated, the BNC article body starts empty, and original source credits carry forward automatically. Editors can add/edit/remove visible credits, add a publisher without a URL, enter a credit note, or designate original BNC reporting.

Each save creates an immutable `story_versions` record and a version-specific `story_sources` credit list. The original feed occurrences remain available in the provenance panel even if visible credits change. Concurrent edits return 409 rather than overwriting another revision.

Missing credits produce a warning and `attribution_blocks_publishing: false`; saving remains available. Rights and editorial approval remain independent. The existing Publishing module and external publishing adapters are outside this change; no publication integration or new publishing action is introduced.

## Verification

The shared editor also supports AI preview/apply/save and persistent Manual Writing. See [AI and Manual Writing](ai-and-manual-writing.md) for the additional protected story and AI-job endpoints. Automatic feed collection does not trigger AI generation or publishing.

For the new global collection settings, archive/restore behavior, historical candidate access and editorial table metadata, see [Collection and Incoming Stories](collection-and-incoming-stories.md). Existing endpoint defaults and source rights/security controls remain in effect.

The test suite includes fixtures for RSS, Atom, JSON Feed, discovery, unsupported pages/APIs, malformed XML, access restrictions, SSRF, redirect policy, DNS pinning, body limits, conditional requests, failure backoff, scheduling, ranking, pagination, attribution edits, and immutable revision conflicts. PostgreSQL tests use isolated randomly named schemas for concurrent deduplication, draft creation, revision conflict handling, and scheduler reservations. Worker metadata is also tested in a fresh Python process.

Run the PostgreSQL-inclusive suite inside the running Docker API container:

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml exec -T api sh -c 'BNC_TEST_DATABASE_URL="$DATABASE_URL" pytest -q'
docker compose --env-file .env -f infrastructure/docker-compose.yml exec -T api alembic check
```

During live verification, the public BBC Bangla RSS source was registered with metadata-only permissions and a 15-minute collection interval. Real Celery collection created 14 unique candidates; a repeat collection created no duplicates. Celery Beat was also observed scheduling and completing collection when the source became due. One candidate was converted into an attributed draft and manually revised without publishing it. The source remains available in the local registry.
