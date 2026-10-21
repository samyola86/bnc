# News intelligence and multi-source discovery

Implemented 21 October 2026 in the existing ingestion, ranking, account and editorial architecture. Recommendations are machine-generated reporting leads, never approval, verification or publication. No article drafting runs during ingestion or classification. Existing OPENAI_MODEL and article-generation behavior are unchanged.

## Source adapters and activation

The existing Sources registry now accepts RSS/Atom/JSON Feed, advertised website feeds and authorized public feed APIs plus `GDELT`, `GOOGLE_NEWS` and `INSTAGRAM_ACCOUNT`. New source registrations default **inactive**. A Superadmin explicitly verifies usage permissions and technical availability before activation. Existing active sources, custom intervals, rights and notes are preserved.

Provider-specific non-secret configuration lives in `provider_config`:

```json
{"query":"Bangladesh","hl":"en-BD","gl":"BD","ceid":"BD:en"}
```

Google News uses the fixed public RSS search endpoint. Publisher attribution from the feed is preserved. Google redirect URLs remain marked unresolved; the collector does not decode opaque links or fetch full articles. GDELT uses the public DOC 2.0 artlist endpoint with a bounded 100-record, rolling 24-hour query; canonical URLs preserve original publisher domains. Its `seendate` is stored as discovery metadata, **not** represented as a publisher's publication timestamp. A coverage timeline endpoint uses `timelinevol`. Article counts and timelines are coverage signals, not independent confirmations.

Both public adapters use BNC's existing DNS pinning, redirect/robots rules, Redis rate limiting, bounded responses, durable collection jobs and scheduling/backoff. Empty valid provider results are retained as empty; malformed or blocked responses produce visible collection errors. No access restrictions are bypassed. Scheduled source modes continue to apply; feeds-only mode excludes API discovery types.

Register Instagram with source type `INSTAGRAM_ACCOUNT`, its public account URL and `provider_config={"username":"account_name"}`. Official Meta Business Discovery uses backend-only `META_INSTAGRAM_TOKEN`, `META_INSTAGRAM_ACCOUNT_ID` and `META_GRAPH_VERSION`; it requires an eligible professional account, appropriate token permissions and access to the target supported account. The account ID must be numeric. Only account identity, post ID/permalink, caption (bounded to 1,200 characters), timestamp, type and permitted like/comment counts are requested. No private posts, photos or scraped pages are fetched. Bearer credentials go only to the fixed Graph API host, never a source-provided URL or pagination link.

Each collection reads at most 50 media records, persists the opaque next cursor only after successful ingestion and resumes on the next cycle. Timestamp watermarks stop pagination through already synchronized history while the fetched head page refreshes permitted engagement metrics; feed/post IDs and canonical URLs prevent duplicate posts. Repeated cursors stop with an error. HTTP 429 backs off; denied/unsupported access is explained in source health. Live Meta access is not verified without operator credentials/permissions.

Editors and Superadmins can use the **Manual Instagram reporting lead** form in Trending Stories (also Sources for Superadmins). A public `/p/` or `/reel/` permalink and user-supplied permitted headline/caption are ingested without network retrieval. Invalid hosts and prohibited/archived sources are rejected; duplicate links do not create duplicate candidates. Manual account attribution is unverified. Sources must be active and eligible before their leads enter automatic intelligence/recommendations.

Google Trends is an explicit `UNCONFIGURED` provider abstraction until official authorized API access is available. There is no webpage scraping or unofficial Trends API. Search interest is returned as `null`, not fabricated zero. `AudienceProvider` defines the future observation interface for authorized WordPress/Meta analytics; provider observations and trend snapshots already support persistent timestamped data. Audience integrations are not implemented in this phase.

## Idempotent publisher provisioning

Run on the trusted API host:

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml exec -T api python -m app.intelligence.provision
```

Provisioning checks known keys, matching feed/URL and publisher names. It inserts missing inactive references only, never updates administrator edits or activates a source. Candidate feeds cover BBC General/World/Business/Technology/Asia and The Business Standard. CNN and Reuters are manual/reference registrations; obsolete public RSS is not assumed usable. Provisioning tests missing feed URLs and records their actual health. The Superadmin settings page registers missing inactive entries without a long blocking network probe; use Test Source there or the CLI for availability checks.

## Classification, taxonomy and safeguards

Metadata-only Bengali/English classification runs on Celery cadence. Deterministic publisher-category/keyword rules run first; unknown items can use strict OpenAI Responses Structured Outputs. Categories, optional secondary category, tags, topic keywords, entities, geography, Bangladesh relevance, public interest, confidence and evidence limitations are schema-validated against the configured taxonomy. Publisher categories stay separate in `ingested_items`; machine analysis and human overrides live in `item_analyses`.

Cache identity includes title/summary/language/publisher category, taxonomy, model and prompt version (`metadata-classifier-v2`). Same-feed metadata changes update raw candidate metadata, never saved story versions; changed fingerprints invalidate classification. Successful results are cached; changed taxonomy/model can reclassify. Human category/tag overrides remain separate and survive every automatic update. Deterministic labels/tags are conservative heuristics, not named-entity verification. No embeddings, full articles or publishing tools are used.

Configure the API/worker environment independently of drafting:

```dotenv
OPENAI_CLASSIFICATION_MODEL=gpt-6-luna
OPENAI_CLASSIFICATION_INPUT_PER_MILLION=0.10
OPENAI_CLASSIFICATION_OUTPUT_PER_MILLION=0.50
```

These are example USD-per-million rates checked against the official model page on 21 October 2026, not a guarantee of future pricing or account access. Verify your own model/access/pricing and update deployment values. `.env.example` leaves the model blank and rates zero, disabling paid classification until configured. The existing API key is reused server-side. Credentials and drafting model are never returned to the browser.

Superadmin **AI Intelligence Settings** persist in PostgreSQL: optional automatic classification (initially off), explicit pause, server-configured model, $1/day target, 5 paid candidates per cycle (maximum 10), 50 processed items/cycle (5–100), concurrency 1 (1–4), 15-minute cadence (5–1440), normalized taxonomy and five ranking weights. Taxonomy labels reject normalized duplicates. Settings are validated and audited; Editors/Writers cannot change them.

Before every paid call, a locked singleton settings row serializes a persistent maximum-cost reservation. Calls reserve 16,000 input and 1,400 output tokens at the configured model-specific prices. Request/schema bytes are bounded conservatively within that reservation. In-flight and uncertain costs count against the UTC daily cap. Provider-returned token usage reconciles successful requests. Unknown prices, exhausted budget, disabled processing and concurrency caps prevent calls. Failed/uncertain calls retain reserved cost and cannot retry the same cache key automatically. Quota/rate errors pause optional AI. Expired worker reservations become UNKNOWN after ten minutes, retain cost and release concurrency slots. The $1 application cap is **not** an OpenAI account billing guarantee; article drafting and other account traffic are outside it. Provider account billing remains authoritative. Manual reconciliation/retention of uncertain old ledger entries is an operator task.

## Clusters, trends and ranking

Exact canonical/content duplicates retain the existing one-candidate/multiple-occurrence provenance model. Related event clustering uses deterministic Unicode-normalized title tokens, shared terms, available classified entities/geography, number-conflict rejection and a 48-hour activity window. It is deliberately conservative and does not claim reliable cross-language semantic event matching. No embeddings are generated. Clusters retain representative titles/categories/keywords, membership, activity, confidence and editorial corrections. Editors/Superadmins can split selected items into a new cluster or merge them into a specified existing cluster; corrected membership is preserved.

Trend snapshots persist for **1h, 6h, 24h, 7d** in 15-minute buckets. Each compares recent coverage with the immediately preceding equal-length baseline. Smoothed log growth yields normalized 0–100 coverage momentum; zero-baseline reports do not create infinite growth. Accessible Instagram engagement changes influence momentum only when at least two real observations exist; raw engagement and unavailable signals remain distinguishable. Scores measure coverage, not public popularity. Publisher labels/counts are shown, but independent confirmations are always unavailable until a separate factual-verification process establishes them. Repeated/syndicated occurrence patterns produce warnings rather than confirmation credit.

The existing ranking SQL uses intelligence scores when available and retains the original weighted ranking for unanalyzed candidates. Both paths preserve explicit item score overrides and pins. The intelligence priority calculation uses the existing relevance, public-impact, freshness and uniqueness inputs, adding trend momentum and metadata evidence quality. Initial configurable weights: Bangladesh relevance .30, public impact .25, trend .20, evidence .15, freshness/originality .10. Evidence quality means metadata completeness/traceability, never factual reliability. Instagram leads receive a lower evidence ceiling. Cluster score overrides are separate audited editorial decisions. New scores refresh on analysis cadence; refresh the candidate cursor after a cycle or editorial score change.

Sparse but significant leads can rank through relevance/impact independently of large coverage counts. Machine recommendations include contributing values/weights, explanation, source references, analysis time, confidence and limitations. No automatic source counting is described as corroboration.

## API

All paths below are relative to `/api/v1/intelligence` and require the existing session/CSRF boundary.

| Method/path | Permission and behavior |
| --- | --- |
| GET `/trends`, `/recommendations` | Authenticated; real clusters, filters and bounded pagination. |
| GET `/trends/{id}` | Evidence, related items, score factors and up to 100 historical snapshots. |
| PATCH `/trends/{id}` | Editor/Superadmin pin/dismiss/score override; null clears the score override. |
| POST `/trends/{id}/select` | Editor/Superadmin adds the representative item to the existing Selected queue. |
| POST `/trends/{id}/draft` | Existing idempotent draft creator; current writer ownership/assignment restrictions remain authoritative. |
| POST `/trends/{id}/move` | Editor/Superadmin `{item_ids,target_cluster_id?}` merge/split. |
| PATCH `/items/{id}/classification` | Editor/Superadmin human category/tags override. |
| POST `/sources/{id}/instagram-post` | Editor/Superadmin permitted manual reporting lead. |
| GET `/gdelt-timeline?query=...` | Bounded GDELT coverage timeline or explicit unavailable response. |
| GET/PATCH `/settings` | Superadmin configuration, provider readiness, current UTC daily usage and sanitized errors. |
| POST `/cycle` | Superadmin queue; respects lease and analysis cadence. |
| POST `/provision` | Superadmin idempotent inactive publisher provisioning. |

List filters: `window=1h|6h|24h|7d`, `category`, `geography=all|BD|global`, `query`, `order=priority|momentum`, `unreviewed`, `needs_verification`, `offset`, `limit` (1–50). Exact category labels are accepted, including Business & Economy, Technology and World. All discovery leads need verification, so that filter currently includes all eligible recommendations. Candidate and source rights are rechecked; prohibited/inactive/archived metadata is excluded from recommendations and paid classification. Feed occurrence rights remain separate from current source rights.

The UI links to Incoming Stories, uses the existing full-page editor and lets Superadmins assign an opened draft through the existing task API. It never submits, schedules, approves or publishes on behalf of the user. Existing readiness and exact-revision review rules are unchanged.

## Operational bounds and limitations

- A cycle processes at most 100 prioritized candidate items; top 5–10 at most may use paid classification. More records progress on later cycles. At most 500 recent clusters are refreshed/listed per cycle/view; historic snapshot detail is bounded to 100 records. This is an explicit initial operational bound, not exhaustive historical search.
- Cross-language event matching, embeddings, automatic independent corroboration, guaranteed syndication detection, live audience analytics and full-article extraction are not implemented. Editors can correct clusters and classification.
- Google Trends requires authorized access and remains unconfigured. Instagram needs Meta permissions; manual links work now. Google News/GDELT may be blocked or temporarily unavailable; failed source health must remain visible. No scraping bypass is provided.
- No notification delivery, external platform publication, archival retention jobs or automatic provider invoice reconciliation is introduced. Usage uses real response token counts and configured estimates; uncertain requests need operator review.

Provider references: [GDELT DOC 2.0](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/), [official Google Trends access](https://developers.google.com/search/apis/trends), [Meta Business Discovery](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-facebook-login/business-discovery/), [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs), [GPT-6 Luna model](https://developers.openai.com/api/docs/models/gpt-6-luna).

## Storage and file map

Migration `5431b66d1876` adds `intelligence_settings`, `item_analyses`, `intelligence_usage`, `story_clusters`, `cluster_members`, `trend_snapshots`, and `provider_observations`; it extends Sources, feed occurrence metadata and cached candidate intelligence scores. Downgrade removes only new intelligence structures and converts new provider registrations into inactive manual references before restoring the original source-type constraint. Existing editorial tables and their IDs are retained.

- `services/api/app/intelligence/`: provider protocols/adapters, inactive provisioning, settings/structured classification schemas, usage reservation/cache, clustering/trend scoring, protected API and leased Celery cycle.
- Existing `config.py`, `db/models.py`, ingestion models/schemas/service/candidates, editorial draft creator, main router and Celery configuration connect the extension without a parallel collector/editor.
- `services/api/alembic/versions/5431b66d1876_news_intelligence_providers_.py`: reviewed additive schema upgrade/rollback.
- `services/api/tests/test_intelligence.py`, `test_intelligence_postgres.py`, migration expectations and opt-in browser server: discovery, cost/concurrency, RBAC, source/provenance and editorial integration verification.
- `apps/dashboard/features/intelligence/` and `/trending`, `/trending/[id]`, `/recommendations`, `/intelligence-settings`: real-data discovery, details/history, editorial corrections and administration.
- Existing Sources form/workspace, feed API types/Incoming Stories links, account settings/session boundary, navigation and the API proxy provide integration and preserve role/origin checks.
- `.env.example`, README, architecture, ingestion/AI API guides and development/verification runbooks document setup, provider permissions, model pricing and operational limits.

New drafts opened from recommendations carry suggested category/tags and model/prompt provenance in their initial immutable revision. Reopening an existing draft never overwrites human writing, tags or classification. No article body is generated by this action.
