import { test, expect } from "@playwright/test";

const parentURL = process.env.WEB_TEST_PARENT_URL || "http://localhost:5173";

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("parent-analytics-choice", "denied"));
});

for (const [autoRenew, billingStatus] of [[true, "active"], [false, "active"], [false, "grace"]] as const) {
  test(`subscription separates access expiry from automatic charge, renew=${autoRenew}, state=${billingStatus}`, async ({ page }) => {
    await page.route("**/api/browser/parent/**", async route => {
      const path = new URL(route.request().url()).pathname;
      const json = path.endsWith("/session")
        ? { role: "parent", id: 1, family_id: 1, nickname: "Parent", csrf_token: "test-csrf" }
        : path.endsWith("/family")
          ? { guardian: { id: 1, nickname: "Parent" }, students: [], timezone: "UTC", settings: {} }
          : path.endsWith("/catalog")
            ? { enabled: false, items: [] }
            : path.endsWith("/config")
              ? { google_client_id: "test-client" }
              : { active: true, plan: "monthly", provider: "waffo", seat_count: 2, used_seats: 0,
                  expires_at: "2026-12-01T00:00:00Z", next_billing_at: autoRenew ? "2026-11-16T00:00:00Z" : null,
                  auto_renew: autoRenew, billing_status: billingStatus, trial_extension_seconds: 0 };
      await route.fulfill({ json });
    });
    await page.goto(parentURL + "/subscription");
    await expect(page.getByText("Next charge", { exact: true })).toBeVisible();
    await expect(page.getByText("Your subscription is first charged after its free trial, then renews monthly until canceled. Unused registration trial time is not added.")).toBeVisible();
    if (billingStatus === "grace") {
      await expect(page.getByText("See your payment provider for the charge date.", { exact: true })).toBeVisible();
    } else if (autoRenew) {
      const access = await page.getByText("Expires", { exact: true }).locator("+ dd").innerText();
      const charge = await page.getByText("Next charge", { exact: true }).locator("+ dd").innerText();
      expect(charge).not.toEqual(access);
      expect(charge).not.toBe("—");
    } else await expect(page.getByText("No automatic charge", { exact: true })).toBeVisible();
  });
}
