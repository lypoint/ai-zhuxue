import { test, expect } from "@playwright/test";
const studentURL = process.env.WEB_TEST_STUDENT_URL || "http://localhost:5174";

test("lesson search paginates, embeds the official player and stops at the time limit", async ({ page }) => {
  let remaining = 3600;
  const searches: string[] = [];
  await page.addInitScript(() => {
    localStorage.setItem("ai-learning-language", "en");
    sessionStorage.setItem("ai-learning-guide-1", "1");
  });
  // Isolate our player integration from the external platform and its media CDN.
  await page.route("https://player.bilibili.com/**", route => route.fulfill({ contentType: "text/html", body: "<p>Official player fixture</p>" }));
  await page.route("**/api/browser/student/**", async route => {
    const url = new URL(route.request().url());
    let json: unknown = {};
    if (url.pathname.endsWith("/session")) json = { role: "student", id: 1, family_id: 1, nickname: "Student", csrf_token: "test" };
    else if (url.pathname.endsWith("/availability")) json = { resting: false, remaining_seconds: remaining, used_seconds: 0, timezone: "UTC" };
    else if (url.pathname.endsWith("/videos")) {
      searches.push(url.searchParams.get("q") || "");
      const n = Number(url.searchParams.get("page"));
      json = { items: [{ id: "BV1CiYe6HEBV", title: `Math lesson ${n}`, author: "Teacher", duration: "16:33" }], page: n, has_more: n === 1 };
    } else if (url.pathname.endsWith("/videos/BV1CiYe6HEBV")) json = { id: "BV1CiYe6HEBV", title: "Math lesson", embed_url: "https://player.bilibili.com/player.html?bvid=BV1CiYe6HEBV&page=1&autoplay=0&danmaku=0" };
    await route.fulfill({ json });
  });
  await page.goto(studentURL + "/videos");
  await expect(page.getByRole("heading", { name: "Lesson videos" })).toBeVisible();
  await page.getByRole("textbox", { name: "Search a topic or lesson" }).fill("一元二次方程");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Math lesson 1" })).toBeVisible();
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Math lesson 2" })).toBeVisible();
  expect(searches).toEqual(["一元二次方程", "一元二次方程"]);
  await page.getByRole("button", { name: "Play video" }).click();
  const frame = page.locator("iframe");
  await expect(frame).toHaveAttribute("src", /player.bilibili.com.*autoplay=0/);
  await expect(frame).toHaveAttribute("allowfullscreen", "");
  await expect(page.frameLocator("iframe").getByText("Official player fixture")).toBeVisible();
  remaining = 0;
  await expect(frame).toHaveCount(0, { timeout: 20_000 });
  await expect(page.getByRole("alert")).toContainText("Video learning paused");
});
