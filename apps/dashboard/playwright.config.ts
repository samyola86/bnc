import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests/browser", workers: 1, timeout: 60000,
  use: { baseURL: "http://localhost:3002", headless: true, trace: "retain-on-failure" },
});
