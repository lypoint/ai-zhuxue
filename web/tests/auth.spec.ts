import { expect, test } from "@playwright/test";

const googleScript = `window.google={accounts:{id:{initialize(){},renderButton(element){const button=document.createElement('button');button.textContent='Sign in with Google';element.replaceChildren(button)}}}};`;

test.beforeEach(async ({ page }) => {
  await page.route("**/api/browser/parent/session", route =>
    route.fulfill({ status: 401, json: { detail: "Not authenticated" } }),
  );
});

test("healthy Google sign-in has no redundant retry button", async ({ page }) => {
  await page.route("**/api/browser/parent/config", route =>
    route.fulfill({ json: { google_client_id: "test-client" } }),
  );
  await page.route("https://accounts.google.com/gsi/client", route =>
    route.fulfill({ contentType: "application/javascript", body: googleScript }),
  );
  await page.goto("http://localhost:5173");
  await expect(page.getByRole("button", { name: "Sign in with Google", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry", exact: true })).toHaveCount(0);
});

test("failed config retry shows loading and recovers without a stale error", async ({ page }) => {
  let requests = 0;
  let release!: () => void;
  const pending = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/browser/parent/config", async route => {
    if (++requests === 1) {
      await route.fulfill({ status: 503, json: { detail: "Network unavailable. Please check the latest state before retrying." } });
    } else {
      await pending;
      await route.fulfill({ json: { google_client_id: "test-client" } });
    }
  });
  await page.route("https://accounts.google.com/gsi/client", route =>
    route.fulfill({ contentType: "application/javascript", body: googleScript }),
  );
  await page.goto("http://localhost:5173");
  await page.getByRole("button", { name: "Retry", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Loading");
  await expect(page.getByRole("button", { name: "Retry", exact: true })).toHaveCount(0);
  release();
  await expect(page.getByRole("button", { name: "Sign in with Google", exact: true })).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
  expect(requests).toBe(2);
});

test("Google SDK failure offers one working retry", async ({ page }) => {
  await page.route("**/api/browser/parent/config", route =>
    route.fulfill({ json: { google_client_id: "test-client" } }),
  );
  let requests = 0;
  await page.route("https://accounts.google.com/gsi/client", route =>
    ++requests === 1 ? route.abort() : route.fulfill({ contentType: "application/javascript", body: googleScript }),
  );
  await page.goto("http://localhost:5173");
  await expect(page.getByRole("button", { name: "Retry", exact: true })).toHaveCount(1);
  await page.getByRole("button", { name: "Retry", exact: true }).click();
  await expect(page.getByRole("button", { name: "Sign in with Google", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry", exact: true })).toHaveCount(0);
  expect(requests).toBe(2);
});
