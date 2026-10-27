import { test, expect } from "@playwright/test";
const parentURL = process.env.WEB_TEST_PARENT_URL || "http://localhost:5173";

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("parent-analytics-choice", "denied"));
});
const reference = "waffo-" + "a".repeat(32);
for (const foreign of [false, true]) test(`Waffo return checks authority before trial access, foreign=${foreign}`, async ({ page }) => {
  let verified = false;
  let checks = 0;
  let release!: () => void;
  const verification = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/browser/parent/**", async route => {
    const path = new URL(route.request().url()).pathname;
    let json: unknown;
    if (path.endsWith("/config")) json = { google_client_id: "test-client" };
    else if (path.endsWith("/session")) json = { role: "parent", id: 1, family_id: 1, nickname: "Parent", csrf_token: "test-csrf" };
    else if (path.endsWith("/family")) json = { guardian: { id: 1, nickname: "Parent" }, students: [], timezone: "UTC", settings: {} };
    else if (path.endsWith("/subscription")) json = { active: true, plan: verified ? "subscription_trial" : "free_trial", provider: verified ? "waffo" : "mock", seat_count: verified ? 2 : 1, used_seats: 0, expires_at: "2027-01-01T00:00:00Z" };
    else if (path.endsWith("/waffo/catalog")) json = { enabled: true, test_mode: true, items: [] };
    else if (path.endsWith("/waffo/verify")) {
      expect(route.request().postDataJSON()).toEqual({ reference }); checks++;
      await verification;
      if (foreign) return route.fulfill({ status: 409, json: { detail: "This checkout belongs to another family." } });
      verified = true; json = { active: true };
    } else throw new Error("Unexpected request: " + path);
    await route.fulfill({ json });
  });
  await page.goto(parentURL + "/subscription?waffo_return=" + reference + "&paid=true");
  await expect.poll(() => checks).toBe(1);
  await expect(page.getByText("Free trial", { exact: true })).toBeVisible();
  release();
  if (foreign) {
    await expect(page.getByRole("alert")).toHaveText("This checkout belongs to another family.");
    await expect(page.getByText("Free trial", { exact: true })).toBeVisible();
  } else {
    await expect(page.getByText("0 / 2", { exact: true })).toBeVisible();
    await expect(page.getByText("Subscription free trial", { exact: true })).toBeVisible();
  }
  await expect(page).toHaveURL(parentURL + "/subscription");
});

test("Waffo prices are USD display units and foreign checkout URLs are rejected", async ({ page }) => {
  await page.route("**/api/browser/parent/**", async route => {
    const path = new URL(route.request().url()).pathname;
    const json = path.endsWith("/session") ? { role: "parent", id: 1, family_id: 1, nickname: "Parent", csrf_token: "test-csrf" }
      : path.endsWith("/family") ? { guardian: { id: 1, nickname: "Parent" }, students: [], timezone: "UTC", settings: {} }
      : path.endsWith("/config") ? { google_client_id: "test-client" }
      : path.endsWith("/catalog") ? { enabled: true, test_mode: false, items: [{ product_code: "family_monthly_2", seat_count: 2, amount: "14.99", currency: "USD" }] }
      : path.endsWith("/checkout") ? { reference, url: "https://checkout.waffo.ai.evil.example/steal" }
      : { active: true, plan: "free_trial", seat_count: 1, used_seats: 0, expires_at: "2027-01-01T00:00:00Z" };
    await route.fulfill({ json });
  });
  await page.goto(parentURL + "/subscription");
  await page.getByRole("button", { name: /\$14\.99/ }).click();
  await expect(page.getByRole("alert")).toContainText("verified");
  await expect(page).toHaveURL(parentURL + "/subscription");
});
