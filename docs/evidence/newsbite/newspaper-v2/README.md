# Newspaper v2 visual verification

Prepared 24 October 2026 from the supplied self-contained HTML handoff.

| Evidence | File |
| --- | --- |
| Approved square reference, 1254 × 1254 | [approved-reference.png](approved-reference.png) |
| Actual portrait placeholder render, 1080 × 1350 | [placeholder.png](placeholder.png) |
| Actual Mahbubani story, 1080 × 1350 | [mahbubani-v2.png](mahbubani-v2.png) |
| Identical saved content/settings, v1 versus v2 | [before-after.png](before-after.png) |
| Native header close-ups, reference above / render below | [header-comparison.png](header-comparison.png) |
| Corresponding header regions, 50% overlay | [header-overlay.png](header-overlay.png) |
| Corresponding separator/photo-border regions | [photo-edge-comparison.png](photo-edge-comparison.png) |
| Constants, glyph bounds, date/focal evidence | [measurements.json](measurements.json) |

Additional full-size samples: [short English black](en-short-black.png),
[short English blue](en-short-blue.png), [long English black](en-long-black.png),
[long English blue](en-long-blue.png), [short Bengali black](bn-short-black.png),
[short Bengali blue](bn-short-blue.png), [long Bengali black](bn-long-black.png),
[long Bengali blue](bn-long-blue.png).

The Mahbubani evidence uses the latest saved **Newspaper** revision's content and
settings, including publication date **22 October 2026** and focal coordinates
**(0.06, 0.12)**. Only the template/layout version changes between the two exports.
No story revision, photograph, approval or database record was changed to create it.

The placeholder retains the reference's headline and has empty optional fields.
Its reference photograph is extracted solely for this offline evidence. The app
renderer does not load the reference image; it still draws dynamic text and an
editor-selected photograph on generated paper.

Visual inspection covered native output, the header close-up/overlay, the photo
border and long Bengali text. Masthead glyph bounds now follow the measured
940px width / 130px height at x=75, y=66. Corporation lettering spans 770px centered
at x=540; metadata/rules/photo share x=51–1029. The placeholder separator is 7px
above the normalized reference because Anton's glyph metrics differ. The extra
portrait height goes into the photo/story region rather than stretching the square.

**Remaining differences:** DM Serif Display, Libre Baskerville and Anton are
licensed approximations. Original font identities remain unverified. Masthead
letterforms/stem weights, metadata widths and paper fibers are visibly different;
this evidence does not establish exact pixel/font fidelity. The website intentionally
uses the requested `.NET`, and the date intentionally comes from saved content.
See [implementation and measured layout](../../../api/newspaper-v2.md).

Validation:

- Full API suite: **230 passed, 9 skipped** (opt-in environment checks), with one
  upstream Starlette/httpx deprecation warning.
- Isolated real PostgreSQL integration suite: **7 passed**, including v2 News Bite
  JSON/history and stale-write checks; temporary schemas are cleaned by fixtures.
- Final header/catalog adjustment checks: **2 passed**.
- Proxy/origin suite: **9 passed**.
- TypeScript, changed-component ESLint, and Python Ruff checks passed.
- Focused Newspaper tests cover 5/15/30/50-word English/Bengali, blue emphasis on/off,
  exact interior crop pixels at three focal points and three image aspect ratios,
  original preservation, deterministic PNG output, overflow and legacy selection.
- Preview/saved export byte parity and revision/approval checks include Newspaper v2.

No browser editorial workflow was rerun in this change; its shared API operations
and PNG bytes were tested directly. No external publication or paid AI call was made.
