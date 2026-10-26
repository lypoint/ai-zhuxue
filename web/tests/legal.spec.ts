import { expect, test } from "@playwright/test";

for (const role of ["parent", "student"] as const) {
  test(`${role} contact dialog links privacy and terms without leaving the site`, async ({ page }) => {
    const origin = `http://localhost:${role === "parent" ? 5173 : 5174}`;
    const external: string[] = [];
    page.on("request", request => {
      if (!request.url().startsWith(origin)) external.push(request.url());
    });
    await page.route(`**/api/browser/${role}/session`, route => route.fulfill({status:401,json:{detail:"Sign in"}}));
    await page.route(`**/api/browser/${role}/config`, route => route.fulfill({json:{google_client_id:""}}));
    await page.goto(origin);
    await page.getByRole("button", {name:"Help",exact:true}).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.locator('a[href^="mailto:"]')).toBeVisible();
    for (const title of ["Privacy", "Terms"]) {
      await dialog.getByRole("button", {name:title,exact:true}).click();
      await expect(dialog.getByRole("heading", {name:title,exact:true})).toBeVisible();
      await expect(dialog).toContainText("ChatGPT, Claude and Gemini");
      await expect(dialog).not.toContainText(/DeepSeek|\bGLM\b|OpenRouter/i);
      expect(page.url()).toBe(origin + "/");
    }
    expect(external).toEqual([]);
  });
}
