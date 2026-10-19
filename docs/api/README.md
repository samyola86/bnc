# Foundation API

- `GET /health/live`: process liveness, independent of infrastructure.
- `GET /health/ready`: PostgreSQL and Redis readiness; returns 503 when unavailable.
- `GET /api/v1/dashboard/overview`: live PostgreSQL counts for stories, review, approval, and queued publications.
- `/docs` and `/openapi.json`: generated FastAPI reference.

Errors use `{"error":{"code":"...","message":"...","request_id":"..."}}`.
Responses include `X-Request-ID`. The dashboard fetches from the API server-side.

The Sources, ingestion, candidate queue, and candidate draft endpoints are implemented and protected by a server-only local editor credential. See [Sources and feeds](sources-and-feeds.md) for supported formats, API routes, scheduling, deduplication, request controls, and attributed draft editing.

Per-user authentication, approvals, and external publishing remain planned. The development dashboard binds to localhost; publishing integrations remain inactive.
