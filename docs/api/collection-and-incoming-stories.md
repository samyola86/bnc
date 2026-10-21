# Collection settings and Incoming Stories

**19 October 2026 update:** Individual account sessions and the three-role policy supersede the earlier shared-editor authorization described below. Send to Publishing now submits for exact-revision review; approval and READY authorization are implemented, while external delivery remains disabled. See [Authentication and RBAC](authentication-and-rbac.md), [Editorial approval](editorial-approval.md) and [Task assignment](task-assignment.md).

This implements the Sources/Incoming Stories layout from `html demo/Newsroom_Dashboard(2).html` using real PostgreSQL records and the existing FastAPI/Celery workflows. The HTML remains a visual/workflow reference; production never uses its fictional stories, sample collection, browser persistence, or publishing simulation.

## Automatic Story Collection

Sources is the primary home for `GET/PATCH /api/v1/ingestion/settings`. All fields persist in the singleton `ingestion_settings` record. PATCH accepts partial changes, including the previous `{ "candidate_limit": 30 }` contract. Null or unknown settings are rejected.

| Setting | Backend behavior |
| --- | --- |
| `candidate_limit` | 20–50 candidates per queue page. Ingestion storage is never capped or padded. |
| `default_interval` | 5–1440 minutes, copied only when a newly created source omits its interval. The UI prepopulates this default and allows an override. Existing intervals, backoff and publisher limits are retained. |
| `draft_language` | `bn` or `en`, used by new candidate and manual drafts. A source's optional `draft_language` overrides this default for its candidates; editors can override each story. Existing drafts and feed language/text are unchanged. The AI panel uses the editor's selected story language. |
| `source_mode` | `all_supported` schedules all supported, permitted source types; `feeds_only` schedules direct RSS/Atom/JSON Feed registrations. Website discovery and public feed API registrations remain available for explicit manual collection. Manual references never collect. |
| `preferred_categories` | Up to 20 category names; an optional, explicit Incoming Stories filter uses the latest saved draft category, otherwise the feed category. This never suppresses ingestion or overrides rights. |
| `automatic_collection` | Global scheduled-collection policy. Beat reserves no new jobs while off, queued scheduled jobs skip execution, and a pause during fetching discards that run's results before storage. Collect now remains available for active, permitted sources. |

Collection runs retain `trigger=manual/scheduled`. Workers recheck the global policy and source rights/activation; scheduled work excluded by policy cannot continue as a manual run. Changes to settings are audited. Changing the global interval does not reschedule or overwrite custom source intervals.

Defaults on upgrade are 30 stories, 15 minutes, Bengali drafts, all supported source types, no preferred category filter, and automatic collection on, preserving the previous scheduling behavior. Existing batch limits and source settings survive migration.

Website support means discovery of advertised public feeds only. Public APIs must return RSS, Atom or JSON Feed. Full article extraction and custom API formats remain unavailable. Collection does not automatically call OpenAI, translate, approve, or publish.

## Archive and restore

Authenticated Superadmin actions:

- `POST /api/v1/sources/{id}/archive`: idempotently archive, deactivate and clear the next scheduled run. The UI asks for confirmation. No source, candidate, feed occurrence, credit, revision, or audit record is deleted. A running fetch cannot commit metadata after its source is archived.
- `POST /api/v1/sources/{id}/restore`: idempotently restore the registry entry, keeping it inactive until explicitly activated. Archived sources cannot be edited, activated, tested or collected before restoration.
- `GET /api/v1/sources?include_archived=true`: include archived entries in the paginated registry. The default registry view hides them. Source views include `archived_at`, `draft_language`, `can_collect`, and `automatic_enabled`.

Historical attribution always remains accessible from the saved draft. Incoming Stories explicitly requests `include_inactive=true`, so archived/deactivated sources' collected stories remain browsable. The checkbox can restore the previous active-source-only view. The underlying candidates API retains its previous default (`include_inactive=false`). No source hard-delete endpoint exists.

## Incoming Stories

The production `/news-feeds` route now displays the editorial table with Story, Category & Tags, Users, Status and Actions columns. Source pills and the paged source selector support both active and archived registry entries. Headline search, exact category/status/source filters, stable ranking cursors, pins, score overrides, metadata/provenance review and select/dismiss/restore remain available.

Refresh Queue fetches actual backend data and returns to the first batch. It does not start collection; Sources → Collect now creates a real background job. Preferred-category filtering is opt-in. The category filter matches either the original feed category or the latest saved draft category; headline search similarly includes original and saved headlines. Cursor signatures include preferences/history flags, preventing reuse after filters change.

`GET /api/v1/feeds/items` adds `include_inactive` and `preferred_only`. Existing fields remain; additional fields are `draft_title`, `draft_category`, `tags`, `ai_assisted`, `assigned_author`, and `sources`. Saved draft metadata comes from the latest immutable version. No AI tags are claimed before a draft containing those tags is saved. Incoming feed bylines are not presented as assigned newsroom users; candidates without a story author show Unassigned.

Edit Story opens an existing saved draft or invokes the existing idempotent `POST /feeds/items/{id}/draft` and opens the shared full-page editor. PostgreSQL locking and the unique origin constraint still prevent duplicate drafts. Editor metadata is on the right, writing is wide, Preview displays the current unsaved text and credits safely, and a bottom action bar saves revisions. Preview never publishes or overwrites state. Existing AI apply/confirmation/save behavior populates headline, summary, body, category, tags, language and captions without replacing the provider/model implementation.

Sources & Credits remain editable, with publisher, optional URL, attribution notes and original-reporting flags. Missing credits warn without preventing save; `attribution_blocks_publishing` stays false. The separate editorial workflow now implements submission, exact-revision approval and READY; external delivery remains outside this feature.

## Summary counts

`GET /api/v1/feeds/summary` returns newsroom-wide database counts, independent of table filters:

- **Incoming:** stored DISCOVERED and SELECTED candidates, including inactive/archived source history.
- **Original Drafts:** independently authored stories in DRAFT or CHANGES_REQUESTED.
- **Awaiting Publication:** distinct accessible stories with active editorial requests or stored PENDING, SCHEDULED, RUNNING or RETRYABLE_FAILED delivery records.
- **Published:** distinct stories with stored CONFIRMED publication records, counted once across destinations.

Awaiting Publication now returns `available=true` for actual review/queue counts. Published still returns `available=false` because external delivery has not been implemented; it shows its recorded count and explanation. A zero is never presented as proof that a functioning publisher ran. Failed count requests also show an unavailable/error state.

## Verification

The suite covers global persistence/defaults, source overrides, scheduling policy/mode changes before and during fetching, manual collection while scheduling is paused, archive/restore with retained credits/provenance, queue category/tag/user metadata, idempotent editing, real summary counts, validation and migration preservation. Existing AI workflow tests additionally assert AI category/tags appear in the candidate table after save. PostgreSQL cases use isolated schemas; no test replaces newsroom data or uses paid AI calls.

Use the commands in the [local development runbook](../runbooks/local-development.md). After upgrading, Compose's migration service applies the additive migration; restart API, worker and scheduler to load the new policy code. No OpenAI credential/model change is required.
