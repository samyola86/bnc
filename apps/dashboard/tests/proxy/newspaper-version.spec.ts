import { expect, test } from "@playwright/test";
import { editableNewspaper } from "../../features/stories/newspaper-version";

const saved = { template_id: "newspaper", template_version: 1 as const, layout_version: 1 as const,
  headline: "Original headline", highlight: "Original", supporting: "Summary", focal_x: .06, focal_y: .12 };

test("editable legacy Newspaper uses v2 without changing saved content or crop", () => {
  const preview = editableNewspaper(saved, true);
  expect(preview).toEqual({ ...saved, template_version: 2, layout_version: 2 });
  expect(saved.template_version).toBe(1);
  expect(JSON.stringify(preview)).not.toBe(JSON.stringify(saved));
});

test("in-review revision retains its saved layout", () => {
  expect(editableNewspaper(saved, false)).toBe(saved);
});

test("other designs and current Newspaper are preserved", () => {
  for (const template_id of ["dark-editorial", "breaking-news", "modern-magazine"]) {
    const other = { ...saved, template_id };
    expect(editableNewspaper(other, true)).toBe(other);
  }
  const current = { ...saved, template_version: 2 as const, layout_version: 2 as const };
  expect(editableNewspaper(current, true)).toBe(current);
});
