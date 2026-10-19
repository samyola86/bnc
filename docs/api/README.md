# Foundation API

- `GET /health/live`: process liveness, independent of infrastructure.
- `GET /health/ready`: PostgreSQL and Redis readiness; returns 503 when unavailable.
- `GET /api/v1/dashboard/overview`: live PostgreSQL counts for stories, review, approval, and queued publications.
- `/docs` and `/openapi.json`: generated FastAPI reference.

Errors use `{"error":{"code":"...","message":"...","request_id":"..."}}`.
Responses include `X-Request-ID`. The dashboard fetches from the API server-side.

The Sources, ingestion, candidate queue, and candidate draft endpoints are implemented and protected by a server-only local editor credential. See [Sources and feeds](sources-and-feeds.md) for supported formats, API routes, scheduling, deduplication, request controls, and attributed draft editing.

Per-user authentication, approvals, and external publishing remain planned. The development dashboard binds to localhost; publishing integrations remain inactive.

Persistent Manual Writing and candidate drafts now share the story/version APIs. OpenAI Responses draft jobs return editable previews and require explicit human apply/save. See [AI and Manual Writing](ai-and-manual-writing.md) for endpoints, server-side configuration, permissions and tests.

The Sources collection panel, archive/restore, Incoming Stories editorial table, summary counts and shared editor preview are described in [Collection and Incoming Stories](collection-and-incoming-stories.md).

The shared editor now persists story format, contributor bylines, cover images, image alt text/credits, reporting notes, selected destinations, social captions and timezone-aware schedules. Private image upload/retrieval and the revision-bound editorial publishing queue are described in [Story media and queue](story-media-and-queue.md). Queue requests are saved preparation; external approval and automatic platform delivery remain unimplemented.