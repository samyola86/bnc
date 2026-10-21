import { test, expect } from "@playwright/test";

test("editor discovers real stored cluster evidence and opens the existing draft editor", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email or username").fill("browsereditor");
  await page.getByLabel("Password", { exact: true }).fill("browser-test-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL("http://localhost:3002/");
  await page.getByRole("link", { name: "Trending Stories", exact: true }).first().click();
  await expect(page.getByRole("heading", { name: "Trending Stories", exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Browser discovery: Bangladesh cyclone response begins" }).click();
  await expect(page.getByRole("heading", { name: "Trend detail", exact: true })).toBeVisible();
  await page.getByText("Evidence, score explanation and limitations", { exact: true }).click();
  await expect(page.getByText("Search interest: unavailable · Independent confirmations: not established")).toBeVisible();
  await expect(page.getByRole("link", { name: "Publisher", exact: true })).toHaveAttribute("href", /publisher.example/);
  await expect(page.getByRole("heading", { name: "Trend history", exact: true })).toBeVisible();
  await page.screenshot({ path: "test-results/trend-evidence.png", fullPage: true });
  await page.getByRole("button", { name: "Create / open draft", exact: true }).click();
  await expect(page).toHaveURL(/\/news-feeds\/drafts\/[a-f0-9-]{36}/);
  await expect(page.getByLabel("Headline", { exact: true })).toHaveValue("Browser discovery: Bangladesh cyclone response begins");
});
