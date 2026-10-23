# Dark Editorial quote artwork

`BNC_Quote_Bubble.svg` is the user-supplied original, copied unchanged.
`BNC_Quote_Bubble.png` is its transparent 615 × 615 raster, generated with the
dashboard's installed Sharp SVG renderer at density 288. It includes the source
gradient, red/white glow, outline and quotation paths. Pillow downsamples it to
205 × 205 and composites it at (85,182), preserving the existing visible motif area.

Regenerate with Node and Sharp:

```js
await sharp("BNC_Quote_Bubble.svg", { density: 288 })
  .resize(615, 615).png().toFile("BNC_Quote_Bubble.png");
```

No new template version or runtime SVG/network dependency was introduced.
The former primitive circle/quotation drawing and social icon row were removed
from the current Dark Editorial design. Breaking News does not use this asset.
