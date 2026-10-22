import { expect, test } from "@playwright/test";

const id = "11111111-1111-4111-8111-111111111111";

for (const stale of [false, true]) {
  test(`AI preview ${stale ? "blocks stale writing" : "confirms, applies and saves without browser dialogs"}`, async ({ page }) => {
    const draft = {
      id, title: "Saved headline", summary: "Saved summary", body: "Saved reporting",
      category: "World", language: "en", tags: ["Original"], social_captions: {},
      version: 2, status: "DRAFT", origin_item_id: null, warnings: [], provenance: [],
      credits: [{ source_id: null, publisher_name: "Reporter", original_url: null,
        attribution_text: "Original reporting", is_original_reporting: true, rights_status: "owned" }],
    };
    let saves = 0;
    await page.addInitScript(() => { window.confirm = () => { throw new Error("Native confirmation unavailable"); }; });
    await page.route("**/api/newsroom/**", async route => {
      const path = new URL(route.request().url()).pathname;
      if (path.endsWith("/auth/me")) return route.fulfill({ json: { mfa_required: false, user: { id: "writer", name: "Writer", role: "CONTENT_WRITER" } } });
      if (path.endsWith("/ai-jobs")) return route.fulfill({ json: { items: [{
        id: "job-1", base_version: stale ? 1 : 2, status: "SUCCEEDED", message: "Ready",
        result: { headline: "AI headline", summary: "AI summary", paragraphs: [{ text: "AI reporting", supporting_source_ids: [] }],
          language: "en", category: "Technology", tags: ["AI"], social_captions: { facebook: "FB caption", instagram: "IG caption" },
          claims_to_verify: [], editorial_warnings: [] },
      }] } });
      if (path.endsWith(`/stories/${id}`)) {
        if (route.request().method() === "PATCH") {
          saves++;
          const body = route.request().postDataJSON();
          expect(body.title).toBe("Edited AI headline");
          expect(body.body).toBe("AI reporting");
          expect(body.ai_job_id).toBe("job-1");
          expect(body.credits).toEqual(draft.credits);
          Object.assign(draft, body, { version: 3 });
        }
        return route.fulfill({ json: draft });
      }
      return route.fulfill({ json: { items: [] } });
    });
    await page.goto(`${process.env.BNC_BROWSER_URL ?? "http://localhost:3002"}/manual-writing/${id}`);
    const apply = page.getByRole("button", { name: "Apply preview to editor", exact: true });
    await expect(apply).toBeVisible();
    if (stale) {
      await expect(apply).toBeDisabled();
      await expect(page.getByText("The saved revision changed.", { exact: false })).toBeVisible();
      await expect(page.getByLabel("Headline", { exact: true })).toHaveValue("Saved headline");
      return;
    }
    await page.getByLabel("Headline", { exact: true }).fill("Unsaved writing");
    await apply.click();
    const confirmation = page.getByRole("group", { name: "Confirm applying AI preview" });
    await expect(confirmation).toBeVisible();
    await confirmation.getByRole("button", { name: "Cancel", exact: true }).click();
    await expect(page.getByLabel("Headline", { exact: true })).toHaveValue("Unsaved writing");
    await page.getByLabel("AI headline", { exact: true }).fill("Edited AI headline");
    await page.getByRole("button", { name: "Preview story", exact: true }).click();
    await apply.click();
    await confirmation.getByRole("button", { name: "Replace editor writing" }).click();
    await expect(page.getByLabel("Headline", { exact: true })).toHaveValue("Edited AI headline");
    await expect(page.getByLabel("Headline", { exact: true })).toBeFocused();
    await expect(page.getByLabel("Story body", { exact: true })).toHaveValue("AI reporting");
    await expect(page.getByLabel("Publisher name", { exact: true })).toHaveValue("Reporter");
    expect(saves).toBe(0);
    await page.getByRole("button", { name: "Save revision", exact: true }).first().click();
    await expect(page.getByText(/Revision 3/).first()).toBeVisible();
    expect(saves).toBe(1);
  });
}
