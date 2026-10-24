import { test, expect } from "@playwright/test";

const parentURL = process.env.WEB_TEST_PARENT_URL || "http://localhost:5173";
const transaction = "txn_" + "a".repeat(26);
const sdkURL = "https://cdn.paddle.com/paddle/v2/paddle.js";

test("owned payment link opens Sandbox and waits for server verification", async ({ page }) => {
  let paid = false;
  let release!: () => void;
  const verification = new Promise<void>(resolve => { release = resolve; });
  let verifyRequests = 0;
  await page.route("**/api/browser/parent/**", async route => {
    const path = new URL(route.request().url()).pathname;
    let json: unknown;
    if (path.endsWith("/config")) json = { google_client_id: "test-client" };
    else if (path.endsWith("/session")) json = { role: "parent", id: 1, family_id: 1, nickname: "Parent", csrf_token: "test-csrf" };
    else if (path.endsWith("/family")) json = { guardian: { id: 1, nickname: "Parent" }, students: [], timezone: "UTC", settings: {} };
    else if (path.endsWith("/subscription")) json = { active: true, plan: paid ? "monthly" : "free_trial", provider: paid ? "paddle_sandbox" : "mock", seat_count: paid ? 2 : 1, used_seats: 0, expires_at: "2027-01-01T00:00:00Z" };
    else if (path.endsWith("/catalog")) json = { enabled: true, client_token: "test_fixture", items: [] };
    else if (path.endsWith("/resume")) {
      expect(route.request().postDataJSON()).toEqual({ transaction_id: transaction });
      json = { transaction_id: transaction, status: "ready" };
    } else if (path.endsWith("/verify")) {
      verifyRequests++;
      await verification;
      paid = true;
      json = { active: true };
    } else throw new Error("Unexpected payment request: " + path);
    await route.fulfill({ json });
  });
  await page.route(sdkURL, route => route.fulfill({ contentType: "application/javascript", body: `
    window.Paddle={Environment:{set(value){window.__paddleEnvironment=value}},Initialize(options){window.__paddleOptions=options},Checkout:{open(options){window.__paddleTransaction=options.transactionId;const frame=document.createElement('iframe');frame.src='https://sandbox-buy.paddle.com/test-checkout';document.body.append(frame)}}};
  ` }));
  await page.route("https://sandbox-buy.paddle.com/test-checkout", route => route.fulfill({ contentType: "text/html", body: "<p>Test Mode</p>" }));
  await page.goto(parentURL + "/subscription?_ptxn=" + transaction);
  await expect(page.frameLocator("iframe").getByText("Test Mode")).toBeVisible();
  expect(await page.evaluate(() => ({ environment: (window as any).__paddleEnvironment, transaction: (window as any).__paddleTransaction, token: (window as any).__paddleOptions.token }))).toEqual({ environment: "sandbox", transaction, token: "test_fixture" });
  await expect(page).toHaveURL(parentURL + "/subscription");
  await page.evaluate(id => (window as any).__paddleOptions.eventCallback({ name: "checkout.completed", data: { transaction_id: id } }), transaction);
  await expect.poll(() => verifyRequests).toBe(1);
  await expect(page.getByText("Free trial", { exact: true })).toBeVisible();
  release();
  await expect(page.getByText("0 / 2", { exact: true })).toBeVisible();
  await expect(page.locator("dd").filter({ hasText: "Paddle Sandbox" })).toBeVisible();
});

test("foreign payment link is rejected before loading Paddle", async ({ page }) => {
  let scripts = 0;
  await page.route(sdkURL, route => { scripts++; return route.abort(); });
  await page.route("**/api/browser/parent/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/resume")) return route.fulfill({ status: 409, json: { detail: "This checkout belongs to another family." } });
    const json = path.endsWith("/session") ? { role: "parent", id: 1, family_id: 1, nickname: "Parent", csrf_token: "test-csrf" }
      : path.endsWith("/family") ? { guardian: { id: 1, nickname: "Parent" }, students: [], timezone: "UTC", settings: {} }
      : path.endsWith("/catalog") ? { enabled: true, client_token: "test_fixture", items: [] }
      : { active: true, plan: "free_trial", seat_count: 1, used_seats: 0, expires_at: "2027-01-01T00:00:00Z" };
    return route.fulfill({ json });
  });
  await page.goto(parentURL + "/subscription?_ptxn=" + transaction);
  await expect(page.getByRole("alert")).toHaveText("This checkout belongs to another family.");
  expect(scripts).toBe(0);
  await expect(page.locator("iframe")).toHaveCount(0);
});
