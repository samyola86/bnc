# Supplied Dark Editorial quote artwork

The current Dark Editorial version 2 directly replaces its primitive circle/quotes
with the user-supplied `BNC_Quote_Bubble.svg` and removes the top-right social icon row.
No extra template version was introduced. Other template designs are unchanged.

- [Full 1080 × 1350 rendered preview](preview.png)
- [Quote artwork and empty former icon region](quote-and-header.png)

The original SVG is preserved unchanged in `app/newsbite/assets`; its bundled
transparent 3× raster includes the supplied gradients and red/white glow. Runtime
preview/export still use the same Pillow PNG generation. Source and conversion
instructions live beside the asset.

Validation: 21 focused quote/photographic regression tests and one Dark Editorial
preview/save/export byte-parity test passed; TypeScript, ESLint and Ruff passed.
Pixel tests verify exact alpha composition and removal of all four icon positions.
