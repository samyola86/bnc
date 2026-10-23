# Newspaper version 2 — reference handoff, 24 October 2026

The Newspaper template now uses a separate Pillow/Raqm scene in
`services/api/app/newsbite/newspaper.py`. Other templates and the legacy Newspaper
v1 rendering branch are unchanged. New selections use v2. Editable v1 Newspaper
drafts now open with a v2 preview and an explicit unsaved-design notice. Save a new
revision to attach the new PNG. In-review revisions retain their saved layout.
Previously saved graphics and approval records are never rewritten.

The supplied `BNC_Newspaper_Codex_Handoff.html` contains a 1254 × 1254 approved
reference and a diagnostic app image. Horizontal coordinates were normalized by
1080/1254 = 0.861244. Output remains **1080 × 1350**, without stretching text or
the complete square composition. The supplied reference is not a runtime background.

## Measured geometry

`newspaper.GRID` is the version-specific source of geometry, also returned by the
template catalog. Coordinates are output pixels; rightmost painted edge is inclusive.
Glyph boxes in the JSON evidence use Pillow's exclusive right/bottom convention;
the website's box therefore ends at 1030 while its last painted column is 1029.
Alignment uses measured raster glyph masks, including side bearings and ink spread.

| Element | Geometry |
| --- | --- |
| Shared rules/photo grid | x=51 through x=1029, 979px raster width |
| Top rule | y=39, 5px |
| Masthead | visible top y=66, width 940px, maximum height 130px; visual center x=545 |
| Corporation name | visible top y=219, width 770px, center x=540 |
| Corporation rule | y=261, 5px |
| Metadata | visible top y=278, Libre Baskerville Bold 23px |
| Website | exact text `BNCNEWS.NET`, visible right edge x=1029 |
| Metadata double rules | y=308 / 320, 3px / 2px |
| Story start | y=345; category takes space only when present |
| English headline | Anton 129px preferred, 40px minimum; maximum eight lines / 650px |
| Headline line step | measured tallest shaped glyph + max(8px, 16% of font size) |
| Photograph | 2px black inside border, 280–900px height within remaining story space |
| Photo separator | 2px black rule, photo starts 17px below separator top |
| Optional fields | measured supporting text, attribution and footer; 18px gaps only for nonempty blocks |
| Content bottom | y=1299; footer space reserved before fitting photo |

The reference placeholder renders at a separator y=744 versus approximately y=751
in the normalized reference. This 7px difference comes from the selected font's
cap height and line spacing. Photo/story height is intentionally adapted to portrait.
The saved publication date is formatted in English uppercase; the reference's
fictional Sunday/2055 placeholder is never used as application content.

## Fonts and remaining approximation

Original font identities cannot be established from the flattened PNG alone.
These are **licensed visual approximations**, not a claim of exact font identity:

- **DM Serif Display Regular**, 2px ink spread, fitted uniformly within the visible
  masthead bounds, then letter-spaced to the measured width. Its serif shapes and
  stem weights still differ from the reference's heavier masthead.
- **Libre Baskerville Bold**, for the tracked corporation name, date and website.
  Date/website widths reflect this face, not a fabricated exact font match.
- **Anton Regular**, for the heavy condensed English headline. Case, punctuation,
  line breaks and stored copy are preserved; no forced uppercase or content edits.
- Existing **Noto Sans/Serif Bengali** via Raqm for complete shaped Bengali/mixed
  blocks; Poppins Regular for English supporting copy, credits and footer.

New font assets and individual SIL Open Font Licenses ship in `app/newsbite/fonts`.
Official source files:
[DM Serif Display](https://github.com/google/fonts/tree/main/ofl/dmserifdisplay),
[Libre Baskerville](https://github.com/google/fonts/tree/main/ofl/librebaskerville),
[Anton](https://github.com/google/fonts/tree/main/ofl/anton).
No browser font downloads, new runtime dependencies or network requests are needed.

Paper is seeded multiscale organic grain (seed 20261024), based on warm ivory
RGB(244,239,226) with subtle cloud/fine noise. It has no repeated point lattice.
The reference's exact fibers/stains are not reproduced, and the paper appearance
remains an approximation. Cached base paper is copied before drawing each scene.

## Preserved behavior and verification

The exact highlight substring remains optional; clearing it produces a black
headline. Category, summary/supporting, speaker, source/photo credits and footer
remain editable and visible. Empty optional fields reserve no phantom line boxes.
The same EXIF-aware `ImageOps.fit` and normalized focal coordinates produce the
cover crop. The border is painted inside the existing crop rectangle, leaving its
interior pixels unchanged. Original uploaded bytes are never edited.

Preview, enlargement, download and revision-bound saved export share the existing
server-generated PNG path. No new renderer pipeline, database migration, authentication
change, external publishing action or service configuration change was introduced.
The running bind-mounted API/dashboard pick up these changes; future image builds
include fonts through the existing package-data patterns.

See [visual evidence](../evidence/newsbite/newspaper-v2/README.md) for full-size PNGs,
header comparison/overlay, photo-edge comparison, measured bounds and test results.
Evidence reads the latest saved **Newspaper** Mahbubani revision without modifying
it; it preserves that revision's content, emphasis, focal point and date for v1/v2
comparison. Do not substitute the latest revision from a different template.

Reproduce with `python -m tests.newspaper_evidence <reference.png> <story.json>
<output-directory>` inside the API environment. The input JSON is a read-only export
of the relevant revision's `content_json`; image retrieval uses existing private
media storage. The extracted reference photograph is used only for the offline
placeholder evidence, never loaded by the application renderer.
