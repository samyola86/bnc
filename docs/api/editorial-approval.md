# Revision-bound editorial review

News Bites additionally require a valid 1080 × 1350 PNG bound to the submitted immutable
revision. Review displays that saved graphic and its platform captions. Submit, approve
and READY verify the stored image's hash/dimensions, current input fingerprint, template
layout, photograph rights and required captions. Missing credits remain a warning;
prohibited source rights and unconfirmed/prohibited photograph rights block readiness.
Article body is not required for a graphic-only News Bite. All existing role, ownership,
concurrency and approval-invalidation rules still apply. See [News Bite templates](news-bite-templates.md).

The existing `publishing_requests` table now records submissions and current review outcomes. New `review_decisions` rows preserve each submission, approval, requested change, rejection, withdrawal and invalidation. No approval rewrites an immutable story version or implies publication.

| Action | Preconditions | Story state | Request outcome |
| --- | --- | --- | --- |
| Save | Own/assigned writer, or Editor/Superadmin; not under review | DRAFT | Active previous request invalidated |
| Submit | Latest saved version; readiness passes | IN_REVIEW | IN_REVIEW |
| Request changes | Editor/Superadmin; IN_REVIEW; reason required | CHANGES_REQUESTED | CHANGES_REQUESTED |
| Reject | Editor/Superadmin; IN_REVIEW; reason required | CHANGES_REQUESTED | REJECTED |
| Approve | Editor/Superadmin; exact latest submitted version; self-approval policy | APPROVED | APPROVED |
| Authorize READY | Editor/Superadmin; approved exact revision; readiness still passes | READY | READY |
| Withdraw | Authorized story access; active request; Writers limited to pending review | DRAFT | WITHDRAWN |

Rejection and withdrawal are preserved as review outcomes, separately from the architecture's story-state enum. Existing legacy QUEUED/SCHEDULED requests remain visible as preparation records; they gain no implicit approval. Edits after approval create a new DRAFT version and append INVALIDATED history to the previous request. Edits under review return 409 until withdrawal. PostgreSQL story-row locking serializes competing submissions/decisions; `base_version` checks reject stale revisions. Repeated active submission of the same version is idempotent.

## Readiness

Submission requires headline, body, category, tags, contributors, destinations, valid format and valid language. The current category model is free-text: valid means nonblank and within the existing field limit. Instagram adds a cover-image requirement; selecting a schedule adds a future timezone-aware datetime requirement. Prohibited source usage rights block readiness independently of attribution. Missing source attribution remains a non-blocking warning.

The editor computes the same conditional checklist for unsaved writing, highlights incomplete fields in amber, highlights attempted invalid submissions in red, and scrolls/focuses the first invalid field. Warnings clear as fields are completed. Counts include only applicable checks. Incomplete drafts can still save with a basic nonempty headline and valid field types. A submission saves current writing with optimistic concurrency before submitting that returned revision; it never silently submits an older version.

The server returns readiness errors as `error.fields`, keyed by `title`, `body`, `category`, `tags`, `contributors`, `destinations`, `format`, `language`, `cover_image_id`, `scheduled_at` or `credits_rights`. Backend checks remain authoritative. Writers cannot set publication schedules or approve, reject or authorize READY.

## API

- `GET /stories/{id}/readiness`: conditional completion counts and field errors for the latest saved revision.
- `POST /stories/{id}/submit-review`, or compatibility alias `/queue`: `{ "base_version": 3 }`.
- `GET /publishing/queue?status=IN_REVIEW`: filter by review status, legacy queue state or `all` for history. Writers see only owned/assigned stories.
- `GET /publishing/requests/{id}`: exact submitted draft, credits/provenance, AI warnings, metadata and immutable decision history.
- `POST /stories/{id}/approve`, `/request-changes`, `/reject`, `/ready`: `{ "request_id": "...", "base_version": 3, "notes": "...", "self_approval_override": false }`.
- `POST /publishing/queue/{id}/cancel`: withdrawal compatibility endpoint.

The review screen displays the complete snapshot, including image/credit, bylines, default and channel captions, source provenance, reporting notes and AI verification warnings. Decision history records actor, notes, timestamp and administrative exceptions. Record ownership (`stories.author_id`), revision authorship (`story_versions.editor_id`), contributor bylines and task assignments remain separate. Soft-deletion never removes historical identities.

Approval can complete associated IN_REVIEW tasks; this is not publication. READY still sends nothing to WordPress or social platforms. Platform dispatch, credentials and delivery confirmation remain a later phase.
