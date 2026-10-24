import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  timeout: 120_000,
  expect: { timeout: 12_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    locale: "en-US",
    actionTimeout: 15_000,
    navigationTimeout: 20_000,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    viewport: { width: 1440, height: 1000 },
  },
  projects: [
    { name: "chromium", use: { browserName: "chromium" } },
    { name: "webkit", use: { browserName: "webkit" } },
  ],
  webServer: [
    {
      command: "../server/.venv/bin/python -m tools.web_acceptance_server",
      cwd: "../server",
      url: "http://127.0.0.1:8810/health",
      reuseExistingServer: false,
      timeout: 30_000,
    },
    {
      command: "WEB_DEV_API=http://127.0.0.1:8810 npm run dev:parent",
      url: "http://localhost:5173",
      reuseExistingServer: false,
      timeout: 30_000,
    },
    {
      command: "WEB_DEV_API=http://127.0.0.1:8810 npm run dev:student",
      url: "http://localhost:5174",
      reuseExistingServer: false,
      timeout: 30_000,
    },
  ],
});
