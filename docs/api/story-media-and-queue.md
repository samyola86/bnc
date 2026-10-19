# Story media and publishing preparation

The shared candidate/manual editor retains AI drafting, immutable revisions, stale-write protection and versioned source credits. It now also saves:

- Format (`article` or `news_bite`), contributor bylines and reporting notes.
- A private cover image reference, alt text and caption/credit.
- Selected destinations: WordPress, Facebook, Instagram, LinkedIn and X.
- A default social caption alongside the existing Facebook/Instagram overrides.
- An optional timezone-aware requested publication time; the editor displays Asia/Dhaka.

These fields live in `StoryVersion.content_json`. Older revisions remain readable. PATCH requests that omit the new fields preserve their existing values. Contributor names are editorial bylines; they do not create login accounts or change the existing record owner.

## Images

`POST /api/v1/media` accepts JSON `{ "data": "<base64 image bytes>" }` and returns an image ID. JPG, PNG, WebP and GIF files must decode successfully, be no larger than 3 MiB and have at most 40 million pixels. SVG and invalid image bytes are rejected. The service stores the original bytes in the configured private MinIO/S3 bucket with server-side credentials. The browser retrieves images through the same-origin credential proxy at `/api/newsroom/media/{id}`. Images are not public bucket objects.

Save a revision to attach an uploaded image. Removing a cover clears its reference in the next revision; previous revisions retain their image. Unattached uploads are retained; automatic orphan cleanup and a media-library browser remain future work.

## Publishing queue

`POST /api/v1/stories/{id}/queue` takes `{ "base_version": 2 }` and queues that exact saved revision. It requires a headline, body, category, tags, contributors and at least one destination. Instagram feed posts also require a cover. Requested schedules must be in the future and include a timezone. Missing source credit remains a non-blocking warning.

Requests are stored in `publishing_requests`, separately from confirmed platform deliveries. Repeating submission of the same saved revision returns the existing request. Editing a story cancels its active request, requiring explicit resubmission. `GET /api/v1/publishing/queue` displays the newest 200 active entries; `POST /api/v1/publishing/queue/{id}/cancel` removes an entry from the active queue while retaining its record and audit trail. Awaiting Publication counts distinct queued stories and pending deliveries.

This implements the HTML demo's publishing preparation with database persistence. **It does not implement external delivery, approval, automatic dispatch at the scheduled time, retries, or corrections to remote posts.** The UI explicitly shows that approval and connected platform adapters are required. No request is marked as published merely because its requested time has passed. The Published page continues to represent confirmed external deliveries only.

## Verification

`tests/test_story_distribution.py` covers revision persistence and compatibility, schedule validation, duplicate submissions, invalidation after edits, cancellation, missing-credit behavior, authorization and image validation/round trips. Run the backend suite and `alembic check`, then dashboard lint, typecheck and production build.
