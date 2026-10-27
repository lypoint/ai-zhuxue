import { expect, test, type Page } from "@playwright/test";

const studentURL = process.env.WEB_TEST_STUDENT_URL || "http://localhost:5174";
const filename = (letter: string) => `${letter.repeat(32)}.png`;
const avatar = (letter: string) => `https://api.example.com/teacher-avatars/${filename(letter)}`;
const source = (letter: string) => `/api/browser/student/api/teacher-avatars/${filename(letter)}`;
const image = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6kH8AAAAASUVORK5CYII=", "base64");

async function setup(page: Page, hidden = false) {
  await page.addInitScript(() => sessionStorage.setItem("ai-learning-guide-1", "1"));
  const requests: string[] = [];
  page.on("request", request => requests.push(request.url()));
  const teachers = [
    { teacher_id: 6, name: "Gemini", avatar_url: avatar("a"), selected: true, access: "available" },
    { teacher_id: 7, name: "ChatGPT", avatar_url: avatar("b"), access: "available" },
    { teacher_id: 8, name: "Claude", avatar_url: avatar("c"), access: "available" },
    { teacher_id: 9, name: "Missing", avatar_url: "", access: "available" },
    { teacher_id: 10, name: "Broken", avatar_url: avatar("e"), access: "available" },
    { teacher_id: 11, name: "External", avatar_url: "https://untrusted.example/avatar.png", access: "available" },
  ];
  const messages = [
    { id: 1, role: "user", content: "Help me study math.", teacher_id: 6, teacher_avatar_url: avatar("d") },
    { id: 2, role: "assistant", content: "Let's learn together.", teacher_id: 6, teacher_avatar_url: avatar("d"), fence_action: "allow" },
  ];
  await page.route("**/api/browser/student/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.includes("/teacher-avatars/")) {
      if (path.endsWith(filename("e"))) await route.fulfill({ status: 404, body: "Not found" });
      else await route.fulfill({ contentType: "image/png", body: image });
      return;
    }
    let json: unknown = {};
    if (path.endsWith("/session")) json = { role: "student", id: 1, family_id: 1, nickname: "Student", csrf_token: "csrf" };
    else if (path.endsWith("/availability")) json = { resting: false, remaining_seconds: 3600, timezone: "UTC" };
    else if (path.endsWith("/teachers")) json = hidden ? teachers.slice(1) : teachers;
    else if (path.endsWith("/sessions")) json = [{ conversation_id: 14, title: "Math", teacher_id: 6, teacher_name: "Gemini" }];
    else if (path.endsWith("/favorites")) json = [];
    else if (path.endsWith("/capabilities")) json = { image_input: false, image_output: false };
    else if (path.endsWith("/conversations")) json = messages;
    else if (path.endsWith("/latest")) json = { conversation_id: 14, teacher_id: 6, teacher_avatar_url: avatar("d"), messages };
    await route.fulfill({ json });
  });
  return requests;
}

test("configured avatars render in all three places and update when switching teachers", async ({ page }) => {
  const requests = await setup(page);
  await page.goto(studentURL + "/chat?conversation=14");
  await expect(page.locator(".teacher-select img")).toHaveAttribute("src", source("a"));
  await expect(page.locator(".message.assistant .teacher-avatar")).toHaveAttribute("src", source("a"));
  await expect(page.locator(".message.user .teacher-avatar")).toHaveCount(0);
  await expect.poll(() => page.locator(".teacher-select img").evaluate((img: HTMLImageElement) => img.naturalWidth)).toBe(1);
  await page.locator(".teacher-select").click();
  for (const [name, letter] of [["Gemini", "a"], ["ChatGPT", "b"], ["Claude", "c"]])
    await expect(page.locator(".teacher-option").filter({ hasText: name }).locator("img")).toHaveAttribute("src", source(letter));
  await page.locator(".teacher-option").filter({ hasText: "ChatGPT" }).click();
  await expect(page.locator(".teacher-select img")).toHaveAttribute("src", source("b"));
  await expect(page.locator(".message")).toHaveCount(0);
  await page.locator(".teacher-select").click();
  await page.locator(".teacher-option").filter({ hasText: "Claude" }).click();
  await expect(page.locator(".teacher-select img")).toHaveAttribute("src", source("c"));
  expect(requests.filter(url => /api\.example\.com|untrusted\.example/.test(url))).toEqual([]);
});

test("latest and explicitly opened history retain avatar snapshots for unavailable teachers", async ({ page }) => {
  await setup(page, true);
  for (const path of ["/chat", "/chat?conversation=14"]) {
    await page.goto(studentURL + path);
    await expect(page.locator(".teacher-select img")).toHaveAttribute("src", source("d"));
    await expect(page.locator(".message.assistant img.teacher-avatar")).toHaveAttribute("src", source("d"));
  }
});

test("missing, unsupported and failed avatars fall back, and changing teacher restores the image", async ({ page }) => {
  const requests = await setup(page);
  await page.goto(studentURL + "/chat?new=1");
  await page.locator(".teacher-select").click();
  for (const name of ["Missing", "Broken", "External"])
    await expect(page.locator(".teacher-option").filter({ hasText: name }).locator(".teacher-avatar-placeholder")).toBeVisible();
  await page.locator(".teacher-option").filter({ hasText: "Broken" }).click();
  await expect(page.locator(".teacher-select .teacher-avatar-placeholder")).toBeVisible();
  await page.locator(".teacher-select").click();
  await page.locator(".teacher-option").filter({ hasText: "Gemini" }).click();
  await expect(page.locator(".teacher-select img")).toHaveAttribute("src", source("a"));
  await expect.poll(() => page.locator(".teacher-select img").evaluate((img: HTMLImageElement) => img.naturalWidth)).toBe(1);
  expect(requests.some(url => url.includes("untrusted.example"))).toBe(false);
});
