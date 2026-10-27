import { expect, test } from "@playwright/test";

const parentURL = process.env.WEB_TEST_PARENT_URL || "http://localhost:5173";

for (const locale of ["en", "zh-Hans"]) {
  for (const empty of [false, true]) {
    test(`parent requests final dispositions only (${locale}, empty=${empty})`, async ({ page }) => {
      await page.addInitScript(language => localStorage.setItem("ai-learning-language", language), locale);
      let requestedFinalOnly = false;
      await page.route("**/api/browser/parent/**", async route => {
        const url = new URL(route.request().url());
        let json: unknown = {};
        if (url.pathname.endsWith("/session"))
          json = { role: "parent", id: 1, family_id: 1, nickname: "Parent", csrf_token: "csrf" };
        else if (url.pathname.endsWith("/family"))
          json = { guardian: { id: 1 }, students: [], timezone: "UTC", settings: {} };
        else if (url.pathname.endsWith("/messages")) json = [];
        else if (url.pathname.endsWith("/fence-events")) {
          requestedFinalOnly = url.searchParams.get("final_only") === "true";
          const final = [
            { id: 2, stage: "policy", decision: "rewrite", category: "other" },
            { id: 3, stage: "policy", decision: "allow", category: "study" },
            { id: 4, stage: "parent_keywords", decision: "reject", category: "other" },
            { id: 5, stage: "output_check", decision: "reject", category: "sensitive" },
          ].map(event => ({ ...event, created_at: "2026-10-27T04:00:00Z" }));
          json = requestedFinalOnly ? empty ? [] : final : [
            { id: 1, stage: "classifier", decision: "pending", category: "study" }, ...final,
          ];
        }
        await route.fulfill({ json });
      });
      await page.goto(parentURL + "/activity/14");
      const section = page.locator("section").filter({
        has: page.getByRole("heading", { name: locale === "zh-Hans" ? "话题限制记录" : "Boundary events", exact: true }),
      });
      await expect(section).toBeVisible();
      await expect.poll(() => requestedFinalOnly).toBe(true);
      await expect(section.locator(".history-item")).toHaveCount(empty ? 0 : 4);
      await expect(section).not.toContainText(locale === "zh-Hans" ? "待处理" : "Pending");
      if (empty) await expect(section.locator(".empty")).toBeVisible();
      else {
        await expect(section.locator("strong")).toContainText(locale === "zh-Hans"
          ? ["已引导回学习", "已允许", "已拦截", "已拦截"]
          : ["Guided back to learning", "Allowed", "Blocked", "Blocked"]);
      }
    });
  }
}
