import { expect, test } from "@playwright/test";

const studentURL = process.env.WEB_TEST_STUDENT_URL || "http://localhost:5174";

for (const locale of ["en", "zh-Hans"]) {
  test(`image jobs skip silently and show failed hints without translating twice (${locale})`, async ({ page }) => {
    await page.addInitScript((language) => {
      localStorage.setItem("ai-learning-language", language);
      sessionStorage.setItem("ai-learning-guide-1", "1");
    }, locale);
    const jobs = [
      { state: "skipped", error: "" },
      { state: "skipped", error: "The image could not be loaded. Please retry." },
      { state: "failed", error: "" },
      { state: "failed", error: "The image could not be loaded. Please retry." },
      { state: "queued", error: "" },
      { state: "running", error: "" },
      { state: "ready", error: "" },
      null,
    ];
    await page.route("**/api/browser/student/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      let json: unknown = {};
      if (path.endsWith("/session"))
        json = { role: "student", id: 1, family_id: 1, nickname: "Student", csrf_token: "test-csrf" };
      else if (path.endsWith("/availability"))
        json = { resting: false, remaining_seconds: 3600, used_seconds: 0, timezone: "UTC" };
      else if (path.endsWith("/teachers"))
        json = [{ teacher_id: 1, name: "Gemini", selected: true, access: "available" }];
      else if (path.endsWith("/sessions") || path.endsWith("/favorites")) json = [];
      else if (path.endsWith("/capabilities")) json = { image_input: false, image_output: false };
      else if (path.endsWith("/conversations"))
        json = jobs.map((job, index) => ({
          id: index + 1, role: "assistant", content: "The answer is ready.",
          teacher_id: 1, fence_action: "allow",
          image_job: job ? { id: index + 1, ...job } : null,
        }));
      await route.fulfill({ json });
    });
    await page.goto(studentURL + "/chat?conversation=14");
    const messages = page.locator(".message.assistant");
    await expect(messages).toHaveCount(jobs.length);
    for (const id of [1, 2, 7, 8])
      await expect(page.locator(`[data-message-id="${id}"] .muted`)).toHaveCount(0);
    const unavailable = locale === "zh-Hans" ? "图片暂不可用" : "Image unavailable";
    for (const id of [3, 4])
      await expect(page.locator(`[data-message-id="${id}"] .muted`)).toHaveText(unavailable);
    for (const id of [5, 6])
      await expect(page.locator(`[data-message-id="${id}"] [role="status"]`)).toBeVisible();
    await expect(messages.filter({ hasText: /请求未能完成|The request could not be completed/ })).toHaveCount(0);
    await expect(page.getByRole("alert")).toHaveCount(0);
  });
}
