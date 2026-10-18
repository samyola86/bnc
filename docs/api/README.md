# Foundation API

- `GET /health/live`: process liveness, independent of infrastructure.
- `GET /health/ready`: PostgreSQL and Redis readiness; returns 503 when unavailable.
- `GET /api/v1/dashboard/overview`: live PostgreSQL counts for stories, review, approval, and queued publications.
- `/docs` and `/openapi.json`: generated FastAPI reference.

Errors use `{"error":{"code":"...","message":"...","request_id":"..."}}`.
Responses include `X-Request-ID`. The dashboard fetches from the API server-side.

This is a local, read-only foundation. Authentication/RBAC and every write endpoint in architecture section 8 remain unimplemented. Do not expose this development API publicly. Adding write workflows requires immutable revisions, optimistic concurrency, authorization, approval records, audit trails, and idempotency before publishing can be enabled.
