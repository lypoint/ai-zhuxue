import { expect, test } from "@playwright/test";

const parentURL = process.env.WEB_TEST_PARENT_URL || "http://localhost:5173";
const png = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6kH8AAAAASUVORK5CYII=", "base64");

for (const locale of ["en", "zh-Hans"]) {
  test(`parent transcript renders current teacher names and same-origin avatars (${locale})`, async ({ page }) => {
    await page.addInitScript(language => localStorage.setItem("ai-learning-language", language), locale);
    const requests: string[] = [];
    page.on("request", request => requests.push(request.url()));
    let renamed = false;
    await page.route("**/api/browser/parent/**", async route => {
      const path = new URL(route.request().url()).pathname;
      if (path.includes("/teacher-avatars/")) {
        await route.fulfill({ contentType: "image/png", body: png });
        return;
      }
      let json: unknown = {};
      if (path.endsWith("/session")) json = { role: "parent", id: 1, family_id: 1, csrf_token: "csrf" };
      else if (path.endsWith("/family")) json = { guardian: { id: 1 }, students: [], settings: {}, timezone: "UTC" };
      else if (path.endsWith("/fence-events")) json = [];
      else if (path.endsWith("/messages")) json = [
        { id: 1, role: "user", content: "Please introduce yourself." },
        ...[renamed ? "Sophia" : "Lisa", "Emily", "John", "Active"].map((name, i) => ({
          id: i + 2, role: "assistant", content: "Let's learn together.", teacher_name: name,
          teacher_avatar_url: i < 3 ? `https://api.example.com/teacher-avatars/${String(i).repeat(32)}.png` : "",
          created_at: "2026-10-27T04:00:00Z", fence_action: "allow",
        })),
      ];
      await route.fulfill({ json });
    });
    await page.goto(parentURL + "/activity/14");
    const messages = page.locator(".message.assistant");
    await expect(messages).toHaveCount(4);
    for (const [i, name] of ["Lisa", "Emily", "John", "Active"].entries())
      await expect(messages.nth(i).locator(".message-byline")).toHaveText(name);
    for (let i = 0; i < 3; i++) {
      const img = messages.nth(i).locator("img.teacher-avatar");
      await expect(img).toHaveAttribute("src", `/api/browser/parent/api/teacher-avatars/${String(i).repeat(32)}.png`);
      await expect.poll(() => img.evaluate((element: HTMLImageElement) => element.naturalWidth)).toBe(1);
    }
    await expect(messages.nth(3).locator(".teacher-avatar-placeholder")).toBeVisible();
    await expect(page.locator(".message.user .teacher-avatar")).toHaveCount(0);
    renamed = true;
    await page.reload();
    await expect(messages.first().locator(".message-byline")).toHaveText("Sophia");
    expect(requests.filter(url => url.includes("api.example.com"))).toEqual([]);
  });
}
