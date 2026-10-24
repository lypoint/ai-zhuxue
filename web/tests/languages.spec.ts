import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
const metadata: Record<string, {rtl: boolean}> = JSON.parse(readFileSync(new URL("../../server/app/locales.json", import.meta.url), "utf8"));

for (const [role, port] of [["parent", 5173], ["student", 5174]] as const) {
  test(`${role} loads only the selected language and preserves all 78 options`, async ({ page }) => {
    const loaded: string[] = [];
    page.on("request", request => {
      if (request.url().includes("/generated-locales/")) loaded.push(request.url());
    });
    await page.route("**/api/browser/**/session", route => route.fulfill({status:401,json:{detail:"Not authenticated"}}));
    await page.route("**/api/browser/**/config", route => route.fulfill({json:{google_client_id:""}}));
    await page.goto(`http://localhost:${port}`);
    const picker = page.locator(".language-picker select");
    await expect(picker.locator("option")).toHaveCount(78);
    expect(loaded.every(url => /\/(en|messages)\.json/.test(url))).toBe(true);
    for (const [tag, info] of Object.entries(metadata)) {
      await picker.selectOption(tag);
      await expect(picker).toHaveValue(tag);
      await expect(picker).toBeEnabled();
      await expect(page.locator("html")).toHaveAttribute("lang",tag);
      await expect(page.locator("html")).toHaveAttribute("dir",info.rtl ? "rtl" : "ltr");
    }
    const count = loaded.length;
    await picker.selectOption("fr-CA");
    await expect(picker).toHaveValue("fr-CA");
    await expect(picker).toBeEnabled();
    expect(loaded.length).toBe(count);
    await page.reload();
    await expect(picker).toHaveValue("fr-CA");
  });
}

test("a failed language download keeps the previous selection and reports the failure", async ({ page }) => {
  await page.route("**/api/browser/parent/session", route => route.fulfill({status:401,json:{detail:"Not authenticated"}}));
  await page.route("**/api/browser/parent/config", route => route.fulfill({json:{google_client_id:""}}));
  await page.route("**/generated-locales/fr-FR.json*",route => route.abort());
  await page.goto("http://localhost:5173");
  const picker = page.locator(".language-picker select");
  await expect(picker).toHaveValue("en");
  await picker.selectOption("fr-FR");
  await expect(page.getByRole("alert")).toContainText("Network unavailable");
  await expect(picker).toHaveValue("en");
  await expect(picker).toBeEnabled();
  expect(await page.evaluate(() => localStorage.getItem("ai-learning-language"))).toBeNull();
});
