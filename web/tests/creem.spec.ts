import { test, expect } from "@playwright/test";
const parentURL = process.env.WEB_TEST_PARENT_URL || "http://localhost:5173";
const checkout = "ch_" + "a".repeat(22);
for (const foreign of [false, true]) test(`Creem return verifies authority before access, foreign=${foreign}`, async ({ page }) => {
  let paid = false;
  let checks = 0;
  let release!: () => void;
  const verification = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/browser/parent/**", async route => {
    const path = new URL(route.request().url()).pathname;
    let json: unknown;
    if (path.endsWith("/config")) json = { google_client_id: "test-client" };
    else if (path.endsWith("/session")) json = { role: "parent", id: 1, family_id: 1, nickname: "Parent", csrf_token: "test-csrf" };
    else if (path.endsWith("/family")) json = { guardian: { id: 1, nickname: "Parent" }, students: [], timezone: "UTC", settings: {} };
    else if (path.endsWith("/subscription")) json = { active: true, plan: paid ? "monthly" : "free_trial", provider: paid ? "creem_test" : "mock", seat_count: paid ? 2 : 1, used_seats: 0, expires_at: "2027-01-01T00:00:00Z" };
    else if (path.endsWith("/creem/catalog")) json = { enabled: true, items: [] };
    else if (path.endsWith("/catalog")) json = { enabled: false, items: [] };
    else if (path.endsWith("/creem/verify")) {
      expect(route.request().postDataJSON()).toEqual({ checkout_id: checkout }); checks++;
      await verification;
      if (foreign) return route.fulfill({ status: 409, json: { detail: "This checkout belongs to another family." } });
      paid = true; json = { active: true };
    } else throw new Error("Unexpected request: " + path);
    await route.fulfill({ json });
  });
  await page.goto(parentURL + "/subscription?creem_return=1&checkout_id=" + checkout + "&signature=forged");
  await expect.poll(() => checks).toBe(1);
  await expect(page.getByText("Free trial", { exact: true })).toBeVisible();
  release();
  if (foreign) {
    await expect(page.getByRole("alert")).toHaveText("This checkout belongs to another family.");
    await expect(page.getByText("Free trial", { exact: true })).toBeVisible();
  } else await expect(page.getByText("0 / 2", { exact: true })).toBeVisible();
  await expect(page).toHaveURL(parentURL + "/subscription");
});
