import { defineConfig } from "@playwright/test";
import base from "./playwright.config";

process.env.WEB_TEST_PARENT_URL = "https://localhost:18443";
process.env.WEB_TEST_STUDENT_URL = "https://127.0.0.1:19443";
process.env.WEB_TEST_HTTPS = "1";

export default defineConfig({
  ...base,
  testDir: ".",
  testMatch: ["tests/family.spec.ts", "tests/paddle.spec.ts", "tests-https/gateway.spec.ts"],
  outputDir: "test-results-https",
  reporter: [
    ["list"],
    ["html", { open: "never", outputFolder: "playwright-report-https" }],
  ],
  use: { ...base.use, ignoreHTTPSErrors: true },
  webServer: [
    {
      command: "node scripts/https-gateway.mjs",
      url: "http://127.0.0.1:8810/health",
      reuseExistingServer: false,
      timeout: 30_000,
    },
  ],
});
