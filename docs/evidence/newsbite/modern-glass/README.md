# Modern Magazine replacement

The pre-change code was committed and pushed to GitHub main as `e95a487` before
any Magazine changes. These samples show the subsequent local implementation.

- [Full-size photo layout, 1080 × 1350](photo-layout.png)
- [Orange composition without an attached photo](orange-layout.png)
- [Shaped Bengali sample](bengali.png)

The supplied reference defines the composition: a full-background photograph,
rounded frosted left panel, white condensed headline, orange underline/category,
summary, top corporation branding, and BNC NEWS / BNCNEWS.NET at the bottom.
These evidence samples use the existing permitted newsroom background. The app
continues to use the editor-selected photograph and focal point; it does not insert
the reference's person or recolor arbitrary photographs orange. The orange no-photo
sample is only a layout demonstration; normal graphic approval still requires a
permitted photograph. Font matching is approximate.

The orange tag is the actual story category, rendered uppercase. It is independent
of headline emphasis. Supporting text, attribution, custom footer, image rights and
the existing revision/approval workflow remain available. Long text shrinks within
safe limits or returns an explicit editing error. No additional template version,
database migration or external publishing action was introduced.

Checks: existing renderer/crop/workflow suite **46 passed**; subsequent focused
Magazine/shared preview-persistence tests **24 passed**; final Magazine/header checks
**21 passed**. These runs overlap and are not a count of unique tests. TypeScript,
changed-component ESLint, and Ruff passed. Tests cover English/Bengali, short/long
copy, category orange independent of highlight, full-cover focal cropping, immutable
original image bytes, deterministic output, overflow and preview/saved-PNG parity.

Reproduce: `python -m tests.magazine_evidence <photo> <output-directory>` in the API
environment. Geometry and behavior are documented in
[News Bite templates](../../../api/news-bite-templates.md#modern-magazine-replacement).
