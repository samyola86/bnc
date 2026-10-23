import { expect, test } from "@playwright/test";

test("library uploads and story uploads share storage and images can be reused", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email or username").fill("browserwriter");
  await page.getByLabel("Password", { exact: true }).fill("browser-test-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL("http://localhost:3002/");
  await page.goto("/media-library");
  const uploaded = page.waitForResponse(response => response.url().endsWith("/api/newsroom/media") && response.request().method() === "POST");
  await page.getByLabel("Upload to media library", { exact: true }).setInputFiles("public/images/login-background.png");
  const response = await uploaded;
  expect(response.status()).toBe(201);
  const asset = await response.json();
  const image = page.getByRole("img", { name: `Library image ${asset.id}`, exact: true });
  await expect(image).toBeVisible();
  await expect.poll(() => image.evaluate((element: HTMLImageElement) => element.naturalWidth)).toBeGreaterThan(0);
  await page.reload();
  await expect(image).toBeVisible();

  await page.goto("/manual-writing");
  await page.getByLabel("New story headline").fill("Media library reuse verification");
  await page.getByRole("button", { name: "Create saved draft" }).click();
  await expect(page.getByRole("heading", { name: "Manual story", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Choose from media library", exact: true }).click();
  await page.locator("article").filter({ hasText: asset.id }).getByRole("button", { name: "Use image", exact: true }).click();
  await page.getByRole("button", { name: "Save revision", exact: true }).first().click();
  await expect(page.getByText(/Revision 2/).first()).toBeVisible();
  const story = await (await page.request.get(`/api/newsroom/stories/${page.url().split("/").at(-1)}`)).json();
  expect(story.cover_image_id).toBe(asset.id);

  const editorUpload = page.waitForResponse(response => response.url().endsWith("/api/newsroom/media") && response.request().method() === "POST");
  await page.getByLabel("Upload / replace image", { exact: true }).setInputFiles("public/images/login-background.png");
  const editorAsset = await (await editorUpload).json();
  await page.getByRole("button", { name: "Save revision", exact: true }).first().click();
  await expect(page.getByText(/Revision 3/).first()).toBeVisible();
  await page.goto("/media-library");
  await expect(page.getByRole("img", { name: `Library image ${editorAsset.id}`, exact: true })).toBeVisible();
  await expect(page.getByRole("img", { name: `Library image ${asset.id}`, exact: true })).toBeVisible();
});
