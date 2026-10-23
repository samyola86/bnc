# Adaptive News Bite editor

Select **News bite** in the existing Story Editor's Format selector. The same saved story,
private media service and review queue are used. Article writing remains available when
switching back; template changes preserve writing, photograph, crop, credits, captions
and destinations. Fill the graphic fields, upload a permitted photo, confirm its rights,
and select Facebook/Instagram destinations and captions. Save revision stores the graphic;
Send to publishing saves and submits that exact revision for review. Downloading alone
does not save, approve or publish.

## Templates and references

| ID | Version | Identity | Photo position | Headline size, preferred/minimum |
| --- | --- | --- | --- | --- |
| `newspaper` | 2 | Ivory organic grain, measured serif masthead/header, condensed headline, framed photo, optional blue emphasis | Below writing | 129 / 40 px |
| `dark-editorial` | 2 | Full-background photo, lower fade, centered letter-spaced branding, red emphasis, quote bubble and vertical CTA | Full canvas | 80 / 44 px |
| `breaking-news` | 2 | Full-background photo, 300px locked red rail, large outlined BREAKING NEWS, blue emphasis | Behind writing, beside rail | 68 / 44 px |
| `modern-magazine` | 1 | Red/white background, rounded card/photo, category pill, blue emphasis | Above writing | 62 / 38 px |

Template/layout versions match: Magazine uses **1**; Newspaper, Dark Editorial and
Breaking News use **2**. Newspaper v1 remains available for saved revisions.
See [Newspaper v2 measurements and visual evidence](newspaper-v2.md). All output **1080 × 1350 RGB PNG**. Definitions
and bounds live in `app/newsbite/renderer.py`; adding/changing approved templates requires
an application release. A graphical template builder is not part of this phase.

The supplied files had doubled `.png.png` extensions and mismatched design labels.
They were renamed by visual identity to the four requested filenames in
`apps/dashboard/public/templates/references/`. All four were inspected. They are design
references, never runtime backgrounds. The app gallery uses generated thumbnails.

The photographic templates were corrected after visual review: version 1 incorrectly
placed the photograph in a separate frame. Version 2 uses full-background photography,
Poppins ExtraBold/Regular English typography, shaped Noto Bengali, reference-style header,
date, quotation bubble, arcs, vertical CTA, red corner curves and a wider
outlined breaking-news rail. Headline emphasis begins on its own line when preceded by
whitespace, without changing the saved headline or highlight offsets.

The references are taller than 4:5, so spacing is adapted to the required 1080 × 1350 canvas.
The editor supplies the photograph; the person embedded in a reference is not extracted
or automatically reused. Carousel dots are decorative, not active links.

The current Dark Editorial design uses the supplied `BNC_Quote_Bubble.svg` artwork
through a bundled transparent raster, preserving its red outline, white quotation
paths, shading and glow. Its former primitive circle/quotes and social icon row
were removed directly from version 2, as requested; no extra template version was
created. Existing stored PNG files remain stored, while new previews and saves use
the updated artwork. The SVG and raster ship in `app/newsbite/assets`; no runtime
SVG dependency is needed.

Version 1 remains reproducible for previously saved revisions and approvals. Selecting a
photographic template or Newspaper now chooses version 2. Editable legacy Newspaper
drafts open with the v2 preview and an unsaved-design notice; saving creates a new
revision. In-review revisions retain their saved layout. Other version-1 drafts offer **Use
matching reference layout**; this preserves content and requires saving a new revision.
It never replaces a previously approved PNG in place.

## Layout and Unicode

The engine reserves branding/date, category, attribution and footer space first. It
measures shaped text at preferred font sizes, wraps at word boundaries, grows text zones,
and contracts the photo within template limits before reducing type. Preferred size is
also the maximum. Headline height is at least 100 px, with template maximums of
600–660 px and at most ten lines. Supporting text uses 24–30 px type and at most 220 px;
credits reserve up to 160 px and the footer up to 100 px. Photo bounds are 280–650 px
(Breaking minimum 300; Magazine maximum 550). Gaps are 24 px. Exact per-template margins,
bounds and priorities are returned by `GET /news-bite/templates`.

For version-2 photographic designs, the photo covers the full canvas (beside the fixed
300px Breaking rail). The headline moves within the lower composition as text grows,
preserving at least 300px of clear photo below the header. Text remains within y=480–1220,
with a separate footer. Main text widths are 884px (Dark) and 700px (Breaking). Text shrinks
within the listed minimums and a continuous lower gradient maintains contrast. Speaker
attribution and supporting text follow the reference-specific order. Category and Breaking
footer values are retained in configuration even where these designs do not display them.

Text is never truncated, hidden or stretched to manufacture a fit. An unbreakable word
that exceeds its zone also fails fitting. Impossible content displays explicit editing
warnings and a non-exportable diagnostic canvas. Shorten the text or change template.
Incomplete drafts can still save and reopen. Submission/approval/READY require a valid
render. No smaller-than-minimum font fallback is used.

Bundled Noto Sans Bengali and Noto Serif Bengali variable fonts provide Bengali glyphs;
Poppins Regular/ExtraBold matches the corrected photo designs' English typography.
Pillow uses **Raqm/HarfBuzz** shaping; API images install `libraqm0` and fail clearly
if shaping/fonts are unavailable. Font files and SIL Open Font Licenses ship with the
Python package. There is no external browser-font dependency.

Emphasis stores an exact substring, colors its first occurrence, and preserves original
text offsets across wrapping. The full shaped line is painted through the highlight
range mask so emphasis does not reshape words separately. Invalid matches and partial
Bengali combining-character ranges are rejected. Multiple independently highlighted
ranges, bidirectional Arabic layouts and manual text positioning are not implemented.

## Images and rendering

The existing `/media` upload and authenticated retrieval endpoints retain original
JPG/PNG/WebP/GIF bytes in the private MinIO bucket. The renderer honors EXIF orientation,
uses cover cropping without stretching, applies the selected horizontal/vertical focal
point, rounded Magazine clipping and dark-template gradients, and warns about undersized
photos. Originals are never changed. There is no automatic photography retrieval or
face detection; editors choose crop position and verify rights/essential subject framing.
GIFs render their first frame. Use **Choose from media library** to reuse an existing image, or upload a replacement.

`POST /stories/{id}/news-bite/preview` accepts `{news_bite, cover_image_id, category,
image_caption}`. It enforces current session, CSRF and owned/assigned story write access.
The response includes PNG base64, dimensions, layout, warnings and errors. The client
debounces edits by 250 ms, aborts superseded requests and hides obsolete previews/exports
until the current result arrives. A detailed validation/storage/font failure is shown.
Enlargement and browser download use these same PNG bytes, not a screenshot of the UI.

Rendering is server-side and requires a reachable API; it does not work offline. Changing
font/rasterizer versions may change newly generated pixels. Existing reviewed PNGs are
retained byte-for-byte; reproducible releases should pin the deployed runtime image.

## Persistence and revision binding

No database migration is needed. `StoryVersion.content_json.news_bite` stores template
ID/version, layout version, independent graphic headline, highlighted segment, supporting
description, category-independent speaker/source attribution, publication date, focal
point, image rights and footer. Existing revision fields retain category, cover ID,
photographer credit, platform/default captions, contributors, tags and destinations.
Omitted configuration on legacy PATCH clients preserves the previous saved values.

Saving a News Bite renders its configuration and writes a new PNG through the existing
private media storage. Server-only `news_bite_render` records the asset ID, immutable
version ID, input fingerprint, SHA-256, dimensions and errors/warnings. Clients cannot
submit or forge this record. Incomplete/overflowing drafts store diagnostics without a
publishable graphic. Failed media/render storage leaves the database revision unsaved.
As with existing uploads, a later database failure can leave an unattached object;
automatic orphan collection remains future work.

Review and READY validation check configuration, safe layout, confirmed owned/licensed
image rights, photograph, applicable captions, exact revision binding, fingerprint,
actual stored PNG hash and 1080 × 1350 dimensions. A saved graphic is displayed in the
existing review screen alongside platform captions and source information. Existing
ownership, Writer restrictions, independent approval and explicit Superadmin exceptions
remain authoritative. Edits produce a new immutable DRAFT revision and invalidate the
previous approval, including changes only to captions, crop, attribution or template.

Missing attribution remains a non-blocking warning. Prohibited source rights block
submission separately; unverified/prohibited image rights also block News Bite readiness.
READY remains preparation for future delivery, not a confirmed Facebook/Instagram post.

## Evidence and reproduction

See [the contact sheet](../evidence/newsbite/contact-sheet.png), the eight full-size sample
exports beside it, and [browser screenshots](../evidence/newsbite/screenshots/).
Examples use BNC's supplied newsroom background as the photograph, not the reference
designs' embedded third-party photos. These are verification examples, not published stories.

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml exec api pytest -q tests/test_newsbite.py tests/test_newsbite_postgres.py
docker compose --env-file .env -f infrastructure/docker-compose.yml exec api alembic check
docker compose --env-file .env -f infrastructure/docker-compose.yml exec -w /workspace/apps/dashboard dashboard npm run lint
docker compose --env-file .env -f infrastructure/docker-compose.yml exec -w /workspace/apps/dashboard dashboard npm run typecheck
```

PostgreSQL tests require `BNC_TEST_DATABASE_URL` and use disposable schemas. Browser tests
in `tests/browser/news-bite.spec.ts` use the opt-in `tests.browser_server` API and dashboard
on port 3002, with a separate Next build directory. They must never use real accounts or
create verification stories in the production newsroom database. Install Chromium with
`npx playwright install chromium --with-deps` in the test dashboard container if needed.

Rebuild the shared API/worker/scheduler images for `libraqm0` and bundled fonts, and deploy
the updated dashboard. Keep the existing `.env`, volumes and network bindings unchanged.
No new environment variable, AI provider call, intelligence feature or automatic publishing
adapter is introduced.
