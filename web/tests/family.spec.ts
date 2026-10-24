import { test, expect, type Page } from "@playwright/test";
import { randomUUID } from "node:crypto";

const parentURL = process.env.WEB_TEST_PARENT_URL || "http://localhost:5173";
const studentURL = process.env.WEB_TEST_STUDENT_URL || "http://localhost:5174";

async function login(page: Page) {
  const identity = randomUUID();
  await page.route("https://accounts.google.com/gsi/client", (route) =>
    route.fulfill({
      contentType: "application/javascript",
      body: `window.google={accounts:{id:{initialize(options){window.__googleCallback=options.callback},renderButton(element){const button=document.createElement('button');button.textContent='Sign in with Google';button.onclick=()=>window.__googleCallback({credential:'acceptance-google-${identity}'});element.replaceChildren(button)}}}};`,
    }),
  );
  await page.goto(parentURL);
  await page
    .getByRole("button", { name: "Sign in with Google", exact: true })
    .click();
  await expect(page.locator(".app-shell")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "A little progress, every day." }),
  ).toBeVisible();
}

async function createChild(page: Page) {
  await page.goto(parentURL + "/schedule");
  const zoneForm = page
    .locator("form")
    .filter({ has: page.getByLabel("Family time zone", { exact: true }) });
  await zoneForm.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText("Changes saved.", { exact: true })).toBeVisible();
  await page.goto(parentURL + "/children");
  await page.getByRole("button", { name: "Add a child", exact: true }).click();
  await page.getByLabel("Nickname", { exact: true }).fill("Jamie");
  await page
    .locator("dialog")
    .getByRole("button", { name: "Save changes", exact: true })
    .click();
  const code = (
    await page.locator(".connection-code code").innerText()
  ).replace(/\s/g, "");
  await page
    .locator("dialog")
    .getByRole("button", { name: "Close", exact: true })
    .click();
  return code;
}

async function connect(page: Page, code: string) {
  await page.goto(studentURL);
  await page.getByLabel("Connection code", { exact: true }).fill(code);
  await page
    .getByRole("button", { name: "Connect to my family", exact: true })
    .click();
  await page
    .getByRole("button", { name: "I understand. Start learning", exact: true })
    .click();
  await expect(
    page.getByRole("heading", {
      name: "What would you like to understand today?",
    }),
  ).toBeVisible();
}

async function ask(page: Page, content: string) {
  await page
    .getByRole("textbox", {
      name: "Ask a question, or add a photo…",
      exact: true,
    })
    .fill(content);
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.locator(".message.assistant").last()).toContainText(
    "What do you notice about the denominator?",
  );
  await expect(
    page.getByRole("button", { name: "Stop generating", exact: true }),
  ).toHaveCount(0);
}

test("family connects, studies with images, reviews records, grades and rewards without payment", async ({
  page,
  context,
}, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await login(page);
  await page.goto(parentURL + "/schedule");
  await page
    .getByLabel("Family time zone", { exact: true })
    .selectOption("America/New_York");
  await page
    .locator("form")
    .filter({ has: page.getByLabel("Family time zone", { exact: true }) })
    .getByRole("button", { name: "Save changes" })
    .click();
  await expect(page.getByText("Changes saved.", { exact: true })).toBeVisible();
  const code = await createChild(page);
  const student = await context.newPage();
  student.on("pageerror", (error) => errors.push(error.message));
  const external: string[] = [];
  student.on("request", (request) => {
    if (
      !request.url().startsWith(studentURL) &&
      !request.url().startsWith("data:") &&
      !request.url().startsWith("blob:")
    )
      external.push(request.url());
  });
  await connect(student, code);
  await ask(student, "Explain math fractions 1/2 + 1/4");
  await expect(student.locator(".katex").first()).toBeVisible();
  await expect(student.locator(".katex")).toHaveCount(3);
  await expect(student.locator(".markdown pre code")).toHaveText(String.raw`\(keep this as code\)`);
  await student
    .locator(".message.assistant")
    .last()
    .getByRole("button", { name: "I understand", exact: true })
    .click();
  await student
    .locator(".message.assistant")
    .last()
    .getByRole("button", { name: "Save moment", exact: true })
    .click();
  await student
    .locator(".message.assistant")
    .last()
    .getByRole("button", { name: "Add an illustration", exact: true })
    .click();
  await expect(student.locator(".message.assistant img").last()).toBeVisible();
  await student
    .getByRole("textbox", {
      name: "Ask a question, or add a photo…",
      exact: true,
    })
    .fill("Explain this math problem in the image");
  const image = Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6kH8AAAAASUVORK5CYII=",
    "base64",
  );
  await student.locator("input[type=file]").first().setInputFiles({
    name: "question.png",
    mimeType: "image/png",
    buffer: image,
  });
  await student
    .getByRole("button", { name: "Use this photo", exact: true })
    .click();
  await expect(student.locator(".attachment")).toContainText("Saved");
  await expect(student.locator(".message.user")).toHaveCount(1);
  await ask(student, "Explain this math problem in the image");
  await expect(student.locator(".message.user img").last()).toBeVisible();
  await student
    .locator(".message.assistant")
    .last()
    .getByRole("button", { name: "Report this answer", exact: true })
    .click();
  await student
    .getByLabel("Reason", { exact: true })
    .fill("Please review this explanation.");
  await student
    .locator("dialog")
    .getByRole("button", { name: "Submit", exact: true })
    .click();
  await student.goto(studentURL + "/reports");
  await expect(
    student.getByText("Please review this explanation.", { exact: true }),
  ).toBeVisible();
  await student.goto(studentURL + "/favorites");
  await expect(
    student.getByRole("button", {
      name: "View source conversation",
      exact: true,
    }),
  ).toBeVisible();
  await student
    .getByRole("button", { name: "View source conversation", exact: true })
    .click();
  await expect(student.locator(".message.assistant").first()).toBeVisible();
  await student.goto(studentURL + "/grades");
  await student.getByRole("button", { name: "Add grade", exact: true }).click();
  await student.getByLabel("Subject", { exact: true }).last().fill("Math");
  await student.getByLabel("Title", { exact: true }).fill("Fractions quiz");
  await student.getByLabel("Date", { exact: true }).fill("2026-10-24");
  await student.getByLabel("Score", { exact: true }).fill("8");
  await student.getByLabel("Maximum score", { exact: true }).fill("10");
  await student
    .locator("dialog")
    .getByRole("button", { name: "Save changes", exact: true })
    .click();
  await expect(
    student.getByRole("heading", { name: "Fractions quiz", exact: true }),
  ).toBeVisible();
  await student.getByRole("button", { name: "Edit", exact: true }).click();
  await student.getByLabel("Score", { exact: true }).fill("9");
  await student
    .locator("dialog")
    .getByRole("button", { name: "Save changes", exact: true })
    .click();
  await student
    .getByRole("button", { name: "Version history", exact: true })
    .click();
  await expect(student.locator("dialog")).toContainText("Version 2");
  await student
    .locator("dialog")
    .getByRole("button", { name: "Close", exact: true })
    .click();
  await student.getByRole("button", { name: "Delete", exact: true }).click();
  await student
    .locator("dialog")
    .getByRole("button", { name: "Confirm", exact: true })
    .click();
  await student.getByLabel("Include removed items", { exact: true }).check();
  await student.getByRole("button", { name: "Restore", exact: true }).click();
  await student.getByLabel("Subject", { exact: true }).selectOption("Math");
  await expect(student.locator(".bar-chart")).toContainText("9/10");
  await student.goto(studentURL + "/assessments");
  await student.getByLabel("From", { exact: true }).fill(
    await student.getByLabel("To", { exact: true }).inputValue(),
  );
  await student
    .getByRole("button", { name: "Generate assessment", exact: true })
    .click();
  await expect(student.locator("[data-assessment-id]")).toHaveCount(1);
  await expect(student.locator("[data-assessment-id]")).toContainText(
    "Keep reviewing every week",
  );
  await student
    .getByRole("button", { name: /View source conversation #/ })
    .first()
    .click();
  await expect(student.locator(".message.assistant").first()).toBeVisible();
  await page.goto(parentURL + "/grades");
  await expect(
    page.getByRole("heading", { name: "Fractions quiz", exact: true }),
  ).toBeVisible();
  await page.goto(parentURL + "/activity");
  await page.locator(".conversation-row").first().click();
  await expect(page.locator(".transcript")).toContainText(
    "Explain math fractions",
  );
  await expect(page.locator(".transcript img").last()).toBeVisible();
  await page.goto(parentURL + "/learning");
  await page.getByLabel("Reward", { exact: true }).fill("A visit to the park");
  await page.getByLabel("Stars required", { exact: true }).fill("1");
  await page
    .getByLabel("How and when to fulfill", { exact: true })
    .fill("This weekend");
  await page
    .getByRole("button", { name: "Propose reward", exact: true })
    .click();
  await student.goto(studentURL + "/learning");
  await expect(
    student.getByRole("heading", { name: "A visit to the park", exact: true }),
  ).toBeVisible();
  await student
    .getByRole("button", { name: "Accept agreement", exact: true })
    .click();
  await student.getByRole("button", { name: "Redeem", exact: true }).click();
  await page.reload();
  await page
    .getByRole("button", { name: "Mark fulfilled", exact: true })
    .click();
  await page.goto(parentURL + "/assessments");
  await page.getByLabel("From", { exact: true }).fill(
    await page.getByLabel("To", { exact: true }).inputValue(),
  );
  await page
    .getByRole("button", { name: "Generate assessment", exact: true })
    .click();
  await expect(page.locator("[data-assessment-id]")).toHaveCount(1);
  await expect(page.locator("[data-assessment-id]")).toContainText(
    "Keep reviewing every week",
  );
  await page
    .getByRole("button", { name: "Wellbeing observations", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Generate assessment", exact: true })
    .click();
  await page.getByRole("button", { name: "Acknowledge", exact: true }).click();
  await expect(page.getByText("Acknowledged", { exact: true })).toBeVisible();
  await page.goto(parentURL + "/subscription");
  await expect(
    page.getByText(
      "Website subscriptions and payments are not available yet.",
      { exact: true },
    ),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: /pay|purchase|checkout/i }),
  ).toHaveCount(0);
  await page.goto(parentURL);
  await expect(
    page.getByRole("heading", {
      name: "A little progress, every day.",
      exact: true,
    }),
  ).toBeVisible();
  await expect(page.locator(".metrics strong").first()).not.toBeEmpty();
  await page.screenshot({
    path: testInfo.outputPath("parent-desktop.png"),
    fullPage: true,
  });
  await student.goto(studentURL + "/chat");
  await student.setViewportSize({ width: 1194, height: 834 });
  await expect(student.locator(".message.assistant").last()).toBeVisible();
  await expect(student.locator(".back-to-latest")).toHaveCount(0);
  await expect(student.locator(".message.assistant").last()).toBeInViewport({
    ratio: 0.8,
  });
  await student.screenshot({ path: testInfo.outputPath("student-tablet.png") });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: testInfo.outputPath("parent-phone.png"),
    fullPage: true,
  });
  expect(external).toEqual([]);
  expect(errors).toEqual([]);
});

test("failed streaming can retry, drafts survive refresh, and device revocation signs out student", async ({
  page,
  context,
}) => {
  await login(page);
  const code = await createChild(page);
  const student = await context.newPage();
  await connect(student, code);
  await student
    .getByRole("textbox", {
      name: "Ask a question, or add a photo…",
      exact: true,
    })
    .fill("My unsent math question");
  await student.reload();
  await expect(
    student.getByRole("textbox", {
      name: "Ask a question, or add a photo…",
      exact: true,
    }),
  ).toHaveValue("My unsent math question");
  await student
    .getByRole("textbox", {
      name: "Ask a question, or add a photo…",
      exact: true,
    })
    .fill("Explain math FAIL_ONCE");
  await student.getByRole("button", { name: "Send", exact: true }).click();
  await expect(
    student.getByRole("button", { name: "Retry", exact: true }),
  ).toBeVisible();
  await student.getByRole("button", { name: "Retry", exact: true }).click();
  await expect(student.locator(".message.assistant").last()).toContainText(
    "What do you notice",
  );
  await expect(student.locator(".message.user")).toHaveCount(1);
  await student.getByRole("textbox", {
    name: "Ask a question, or add a photo…", exact: true,
  }).fill("Private unsent draft before revocation");
  await expect.poll(() => student.evaluate(() =>
    Object.values(sessionStorage).includes("Private unsent draft before revocation"),
  )).toBe(true);
  await page.goto(parentURL + "/children");
  await page
    .getByRole("button", { name: "Disconnect device", exact: true })
    .click();
  await page
    .locator("dialog")
    .getByRole("button", { name: "Confirm", exact: true })
    .click();
  await student.locator('a[href="/reports"]').click();
  await expect(
    student.getByRole("heading", { name: "Connect to my family", exact: true }),
  ).toBeVisible();
  const privateKeys = () => student.evaluate(() =>
    Object.keys(sessionStorage).filter(key => key.startsWith("ai-learning-")),
  );
  await expect.poll(privateKeys).toEqual([]);
  await student.evaluate(() => {
    sessionStorage.setItem("ai-learning-draft-stale", "stale private draft");
    sessionStorage.setItem("unrelated-preference", "keep");
  });
  await student.reload();
  await expect(
    student.getByRole("heading", { name: "Connect to my family", exact: true }),
  ).toBeVisible();
  await expect.poll(privateKeys).toEqual([]);
  expect(await student.evaluate(() => sessionStorage.getItem("unrelated-preference"))).toBe("keep");
});

test("learning limits, boundaries, history controls, review, notifications and export work", async ({
  page,
  context,
}) => {
  await login(page);
  const code = await createChild(page);
  const student = await context.newPage();
  await connect(student, code);
  await page
    .getByLabel("Custom blocked words", { exact: true })
    .fill("volcanoes");
  await page
    .locator(".boundary-form")
    .getByRole("button", { name: "Save changes", exact: true })
    .click();
  await expect(page.getByText("Changes saved.", { exact: true })).toBeVisible();
  await student
    .getByRole("textbox", {
      name: "Ask a question, or add a photo…",
      exact: true,
    })
    .fill("Explain math volcanoes");
  await student.getByRole("button", { name: "Send", exact: true }).click();
  await expect(student.locator(".message.assistant")).toContainText(
    "I can't answer that question",
  );
  await page.goto(parentURL + "/activity");
  await page.locator(".conversation-row").first().click();
  await page
    .getByRole("button", { name: "Flag for review", exact: true })
    .last()
    .click();
  await page
    .getByLabel("Notes", { exact: true })
    .fill("Educational question, please review.");
  await page
    .locator("dialog")
    .getByRole("button", { name: "Submit", exact: true })
    .click();
  await expect(page.getByText("Changes saved.", { exact: true })).toBeVisible();
  await student
    .locator(".history-row")
    .first()
    .getByRole("button", { name: "Rename", exact: true })
    .click();
  await student
    .getByLabel("Title", { exact: true })
    .fill("Our science question");
  await student
    .locator("dialog")
    .getByRole("button", { name: "Save changes", exact: true })
    .click();
  await student.getByRole("button", { name: "Pin", exact: true }).click();
  await expect(
    student.getByRole("button", { name: "Unpin", exact: true }),
  ).toBeVisible();
  await student
    .getByRole("searchbox", { name: "Search conversations", exact: true })
    .fill("volcanoes");
  await expect(student.locator(".history-title")).toContainText(
    "Our science question",
  );
  await student.getByRole("button", { name: "Delete", exact: true }).click();
  await student
    .locator("dialog")
    .getByRole("button", { name: "Confirm", exact: true })
    .click();
  await expect(student.locator(".history-row")).toHaveCount(0);
  await page.goto(parentURL + "/activity");
  await page
    .getByRole("combobox", { name: "Include removed items", exact: true })
    .selectOption("deleted");
  await expect(page.locator(".conversation-row")).toContainText(
    "Our science question",
  );
  const downloadPromise = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Export learning data", exact: true })
    .click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/^learning-\d+\.json$/);
  await page.goto(parentURL + "/notifications");
  await page.locator(".notification-row").first().click();
  await expect(page.locator("dialog")).toBeVisible();
  await page
    .locator("dialog")
    .getByRole("button", { name: "Close", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Mark all as read", exact: true })
    .click();
  await expect(page.getByText("Unread: 0", { exact: true })).toBeVisible();
  await page.goto(parentURL + "/schedule");
  await page.getByLabel("Quiet hours", { exact: true }).check();
  const timeZone = await page
    .getByLabel("Family time zone", { exact: true })
    .inputValue();
  const hour = Number(
    new Intl.DateTimeFormat("en-US", {
      timeZone,
      hour: "numeric",
      hourCycle: "h23",
    }).format(new Date()),
  );
  await page
    .getByLabel("Start hour", { exact: true })
    .selectOption(String(hour));
  await page
    .getByLabel("End hour", { exact: true })
    .selectOption(String((hour + 1) % 24));
  await page
    .locator("form")
    .filter({ has: page.getByLabel("Daily question limit", { exact: true }) })
    .getByRole("button", { name: "Save changes", exact: true })
    .click();
  await student.goto(studentURL + "/chat?new=rest-check");
  await expect(
    student.getByRole("heading", {
      name: "Time for a short break",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    student.getByRole("button", { name: "Send", exact: true }),
  ).toHaveCount(0);
  await page.goto(parentURL + "/settings");
  await page
    .getByRole("button", { name: "Sign out of this browser", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Sign in to your family", exact: true }),
  ).toBeVisible();
});

test("offline drafts, stopping generation, language switching and account deletion work", async ({
  page,
  context,
}) => {
  await login(page);
  const code = await createChild(page);
  const student = await context.newPage();
  await connect(student, code);
  const question = student.getByRole("textbox", {
    name: "Ask a question, or add a photo…",
    exact: true,
  });
  await question.fill("Explain math SLOW_RESPONSE");
  await context.setOffline(true);
  await expect(
    student.getByRole("button", { name: "Send", exact: true }),
  ).toBeDisabled();
  await expect(question).toHaveValue("Explain math SLOW_RESPONSE");
  await context.setOffline(false);
  await student.getByRole("button", { name: "Send", exact: true }).click();
  await student
    .getByRole("button", { name: "Stop generating", exact: true })
    .click();
  await expect(
    student.getByRole("button", { name: "Retry", exact: true }),
  ).toBeVisible();
  await student.getByRole("button", { name: "Retry", exact: true }).click();
  await expect(student.locator(".message.assistant").last()).toContainText(
    "What do you notice",
  );
  await expect(student.locator(".message.user")).toHaveCount(1);
  await page.goto(parentURL + "/settings");
  await page.setViewportSize({ width: 390, height: 844 });
  for (const language of ["zh-Hans", "zh-Hant", "ja", "ko", "de", "es", "en"]) {
    await page.locator(".topbar select").selectOption(language);
    await expect(page.locator("html")).toHaveAttribute("lang", language);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  }
  await student.goto(studentURL + "/settings");
  await student.getByRole("button", { name: "Privacy", exact: true }).click();
  await expect(student.locator("dialog")).toContainText(
    "Your family can review learning conversations",
  );
  await student
    .locator("dialog")
    .getByRole("button", { name: "Close", exact: true })
    .click();
  await student
    .getByRole("button", { name: "Delete account", exact: true })
    .click();
  await student.getByLabel("Type DELETE", { exact: true }).fill("DELETE");
  await student
    .locator("dialog")
    .getByRole("button", { name: "Confirm", exact: true })
    .click();
  await expect(
    student.getByRole("heading", { name: "Connect to my family", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", {
      name: "Request family account deletion",
      exact: true,
    })
    .click();
  await page.getByLabel("Type DELETE", { exact: true }).fill("DELETE");
  await page
    .locator("dialog")
    .getByRole("button", { name: "Confirm", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Sign in to your family", exact: true }),
  ).toBeVisible();
});

test("untrusted markdown stays local and photo uploads can retry without sending the draft", async ({
  page,
  context,
}) => {
  await login(page);
  const code = await createChild(page);
  const student = await context.newPage();
  const external: string[] = [];
  student.on("request", (request) => {
    if (
      !request.url().startsWith(studentURL) &&
      !/^(data|blob):/.test(request.url())
    )
      external.push(request.url());
  });
  await connect(student, code);
  await ask(
    student,
    String.raw`Explain math $\frac{1}{2}$.

<script>window.__unsafe = true</script>
<img src="https://outside.invalid/raw.png" onerror="window.__unsafe=true">
![tracking](https://outside.invalid/image.png)
[external](https://outside.invalid)
$\href{javascript:alert(1)}{unsafe}$
$\includegraphics{https://outside.invalid/math.png}$`,
  );
  const markdown = student.locator(".message.user .markdown");
  await expect(markdown.locator("script, img, a, iframe")).toHaveCount(0);
  expect(
    await student.evaluate(
      () => (window as Window & { __unsafe?: boolean }).__unsafe,
    ),
  ).toBeUndefined();
  await student
    .getByRole("textbox", {
      name: "Ask a question, or add a photo…",
      exact: true,
    })
    .fill("Explain this math photo");
  const photoInput = student.locator("input[type=file]").first();
  await photoInput.setInputFiles({
    name: "unsupported.heic",
    mimeType: "image/heic",
    buffer: Buffer.from("synthetic unsupported format"),
  });
  await expect(student.getByRole("alert")).toContainText(
    "Choose a JPEG, PNG or WebP image.",
  );
  await photoInput.setInputFiles({
    name: "too-large.png",
    mimeType: "image/png",
    buffer: Buffer.alloc(30 * 1024 * 1024 + 1),
  });
  await expect(student.getByRole("alert")).toContainText(
    "This image is too large. Choose a smaller image.",
  );
  await photoInput.setInputFiles({
    name: "corrupt.png",
    mimeType: "image/png",
    buffer: Buffer.from("synthetic invalid image bytes"),
  });
  await expect(student.locator("dialog [role=alert]")).toContainText(
    "Choose a JPEG, PNG or WebP image.",
  );
  await expect(
    student.getByRole("button", { name: "Use this photo", exact: true }),
  ).toBeDisabled();
  await student.locator("dialog .dialog-heading button").click();
  await expect(student.locator(".attachment")).toHaveCount(0);
  let fail = true;
  await student.route("**/api/browser/student/upload?*", (route) => {
    if (fail) {
      fail = false;
      return route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Temporary upload failure" }),
      });
    }
    return route.continue();
  });
  for (let n = 0; n < 2; n++) {
    await student
      .locator("input[type=file]")
      .first()
      .setInputFiles({
        name: `question-${n}.png`,
        mimeType: "image/png",
        buffer: Buffer.from(
          "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6kH8AAAAASUVORK5CYII=",
          "base64",
        ),
      });
    await student
      .getByRole("button", { name: "Use this photo", exact: true })
      .click();
    if (n === 0)
      await student
        .locator(".attachment")
        .getByRole("button", { name: "Retry", exact: true })
        .click();
    await expect(student.locator(".attachment").nth(n)).toContainText("Saved");
  }
  await expect(student.locator(".message.user")).toHaveCount(1);
  await ask(student, "Explain this math photo");
  await expect(
    student.locator(".message.user").last().locator("img"),
  ).toHaveCount(2);
  await student
    .locator(".message.user")
    .last()
    .getByRole("button", { name: "View image", exact: true })
    .first()
    .click();
  await expect(student.locator("dialog .full-image")).toBeVisible();
  expect(external).toEqual([]);
});

test("parent edits grades, saved sources and notification pages work, and switching teachers respects capabilities", async ({
  page,
  context,
}) => {
  await login(page);
  const code = await createChild(page);
  const student = await context.newPage();
  await connect(student, code);
  await ask(student, "Explain math fractions NOTIFICATION_PAGINATION");
  const originalConversation = new URL(student.url()).searchParams.get(
    "conversation",
  );
  await student
    .locator(".message.assistant")
    .last()
    .getByRole("button", { name: "Save moment", exact: true })
    .click();
  await student.goto(studentURL + "/favorites");
  const search = student.getByRole("searchbox", {
    name: "Search",
    exact: true,
  });
  await search.fill("no matching saved content");
  await expect(
    student.getByRole("button", {
      name: "View source conversation",
      exact: true,
    }),
  ).toHaveCount(0);
  await search.fill("denominator");
  await expect(
    student.getByRole("button", {
      name: "View source conversation",
      exact: true,
    }),
  ).toHaveCount(1);
  await page.goto(parentURL + "/favorites");
  await page
    .getByRole("button", { name: "View source conversation", exact: true })
    .click();
  await expect(page.locator(".transcript")).toContainText(
    "NOTIFICATION_PAGINATION",
  );
  await expect(page).toHaveURL(
    new RegExp(`/activity/${originalConversation}#message-`),
  );
  await page.goto(parentURL + "/notifications");
  await expect(page.locator(".notification-row")).toHaveCount(20);
  await page.getByRole("button", { name: "Next page", exact: true }).click();
  await expect(page.locator(".notification-row")).toHaveCount(2);
  await expect(
    page.getByText("Welcome to AI StudyNest", { exact: true }),
  ).toBeVisible();
  await page
    .locator(".notification-row")
    .filter({ hasText: "Learning update 1" })
    .click();
  await page
    .locator("dialog")
    .getByRole("button", { name: "View source conversation", exact: true })
    .click();
  await expect(page.locator(".transcript")).toContainText(
    "NOTIFICATION_PAGINATION",
  );
  await page.goto(parentURL + "/notifications");
  await page.getByLabel("Unread only", { exact: true }).check();
  await expect(page.getByText("Unread: 21", { exact: true })).toBeVisible();
  await expect(page.locator(".notification-row")).toHaveCount(20);
  await page.getByRole("button", { name: "Next page", exact: true }).click();
  await expect(page.locator(".notification-row")).toHaveCount(1);
  await expect(
    page.getByRole("button", { name: "Next page", exact: true }),
  ).toBeDisabled();
  await page.goto(parentURL + "/grades");
  await page.getByRole("button", { name: "Add grade", exact: true }).click();
  await page.getByLabel("Subject", { exact: true }).last().fill("Science");
  await page.getByLabel("Title", { exact: true }).fill("Parent-entered quiz");
  await page.getByLabel("Date", { exact: true }).fill("2026-10-24");
  await page.getByLabel("Score", { exact: true }).fill("16");
  await page.getByLabel("Maximum score", { exact: true }).fill("20");
  await page
    .locator("dialog")
    .getByRole("button", { name: "Save changes", exact: true })
    .click();
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await page.getByLabel("Score", { exact: true }).fill("18");
  await page
    .locator("dialog")
    .getByRole("button", { name: "Save changes", exact: true })
    .click();
  await student.goto(studentURL + "/grades");
  await expect(student.locator(".grade-value")).toContainText("18");
  await student
    .getByRole("button", { name: "Version history", exact: true })
    .click();
  await expect(student.locator("dialog")).toContainText("Version 2");
  await expect(student.locator("dialog")).toContainText("Parent");
  await student.goto(studentURL + "/favorites");
  await student
    .getByRole("button", { name: "Remove saved moment", exact: true })
    .click();
  await expect(
    student.getByRole("button", {
      name: "View source conversation",
      exact: true,
    }),
  ).toHaveCount(0);
  await page.goto(parentURL + "/favorites");
  await expect(
    page.getByRole("button", { name: "View source conversation", exact: true }),
  ).toHaveCount(0);
  await student.goto(studentURL + "/chat");
  await student.locator(".teacher-select").click();
  await student
    .locator("dialog")
    .getByRole("button", { name: "Text guide Active", exact: true })
    .click();
  await expect(student.locator(".teacher-select")).toContainText("Text guide");
  await expect(
    student.getByRole("button", { name: "Add photo", exact: true }),
  ).toHaveCount(0);
  await ask(student, "Explain math with text only");
  await expect(
    student.locator(".message.assistant .message-byline"),
  ).toContainText("Text guide");
  await expect(
    student.getByRole("button", { name: "Add an illustration", exact: true }),
  ).toHaveCount(0);
  expect(new URL(student.url()).searchParams.get("conversation")).not.toEqual(
    originalConversation,
  );
  await student.goto(studentURL + `/chat?conversation=${originalConversation}`);
  await expect(student.locator(".teacher-select")).toContainText(
    "Learning guide",
  );
  await expect(
    student.getByRole("button", { name: "Add photo", exact: true }),
  ).toBeVisible();
  await student.locator(".teacher-select").click();
  await student
    .locator("dialog")
    .getByRole("button", { name: "自定义导师 Active", exact: true })
    .click();
  await expect(student.locator(".teacher-select")).toContainText("自定义导师");
  await ask(student, "Explain math with a custom teacher");
  await expect(
    student.locator(".message.assistant .message-byline"),
  ).toContainText("自定义导师");
  await page.goto(parentURL + "/activity");
  await expect(
    page.locator(".conversation-row").filter({ hasText: "自定义导师" }),
  ).toHaveCount(1);
  await page.goto(parentURL);
  await expect(
    page.locator(".conversation-row").filter({ hasText: "自定义导师" }),
  ).toHaveCount(1);
});

test("family profiles and limits persist, replacement disconnects the old browser, and removing a child revokes access", async ({
  page,
  browser,
}) => {
  await login(page);
  const code = await createChild(page);
  const deviceOptions = {
    locale: "en-US",
    ignoreHTTPSErrors: process.env.WEB_TEST_HTTPS === "1",
  };
  const oldDevice = await browser.newContext(deviceOptions);
  const replacementDevice = await browser.newContext(deviceOptions);
  try {
    const student = await oldDevice.newPage();
    await connect(student, code);
    await page.goto(parentURL + "/children");
    await page
      .locator(".child-card")
      .getByRole("button", { name: "Edit", exact: true })
      .click();
    await page.getByLabel("Nickname", { exact: true }).fill("Alex");
    await page.getByLabel("Age range", { exact: true }).selectOption("12-16");
    await page
      .locator("dialog")
      .getByRole("button", { name: "Save changes", exact: true })
      .click();
    await expect(page.locator(".child-card")).toContainText("Alex");
    await expect(page.locator(".child-card")).toContainText("12-16");
    await page.reload();
    await expect(
      page.getByRole("combobox", { name: "Choose a child", exact: true }),
    ).toHaveValue(/\d+/);
    await expect(page.locator(".child-card")).toContainText("Alex");
    await page.goto(parentURL + "/settings");
    await page.getByLabel("Name", { exact: true }).fill("Taylor");
    const profileSaved = page.waitForResponse(
      (response) =>
        response.url().endsWith("/parent/guardian/nickname") &&
        response.request().method() === "PUT",
    );
    await page
      .getByRole("button", { name: "Save changes", exact: true })
      .click();
    expect((await profileSaved).ok()).toBe(true);
    await page.reload();
    await expect(page.getByLabel("Name", { exact: true })).toHaveValue(
      "Taylor",
    );
    await page.goto(parentURL + "/schedule");
    await page
      .getByLabel("Daily learning time (minutes)", { exact: true })
      .fill("45");
    await page.getByLabel("Daily question limit", { exact: true }).fill("30");
    await page
      .getByLabel("Learning boundary notifications", { exact: true })
      .uncheck();
    const scheduleSaved = page.waitForResponse(
      (response) =>
        response.url().endsWith("/parent/settings") &&
        response.request().method() === "PUT",
    );
    await page
      .locator("form")
      .filter({ has: page.getByLabel("Daily question limit", { exact: true }) })
      .getByRole("button", { name: "Save changes", exact: true })
      .click();
    expect((await scheduleSaved).ok()).toBe(true);
    await expect(
      page.getByText("Changes saved.", { exact: true }),
    ).toBeVisible();
    await page.reload();
    await expect(
      page.getByLabel("Daily learning time (minutes)", { exact: true }),
    ).toHaveValue("45");
    await expect(
      page.getByLabel("Daily question limit", { exact: true }),
    ).toHaveValue("30");
    await expect(
      page.getByLabel("Learning boundary notifications", { exact: true }),
    ).not.toBeChecked();
    await page.goto(parentURL + "/children");
    await page
      .locator(".child-card")
      .getByRole("button", { name: "Connect a device", exact: true })
      .click();
    await expect(page.locator("dialog")).toContainText("signs the child out");
    await page
      .locator("dialog")
      .getByRole("button", { name: "Confirm", exact: true })
      .click();
    const replacementCode = (
      await page.locator(".connection-code code").innerText()
    ).replace(/\s/g, "");
    await page
      .locator("dialog")
      .getByRole("button", { name: "Close", exact: true })
      .click();
    const replacement = await replacementDevice.newPage();
    await connect(replacement, replacementCode);
    await expect(replacement.locator(".topbar")).toContainText("Alex");
    await student.reload();
    await expect(
      student.getByRole("heading", {
        name: "Connect to my family",
        exact: true,
      }),
    ).toBeVisible();
    await page
      .locator(".child-card")
      .getByRole("button", { name: "Delete", exact: true })
      .click();
    await page
      .locator("dialog")
      .getByRole("button", { name: "Confirm", exact: true })
      .click();
    await expect(page.locator(".child-card")).toContainText("Inactive");
    await replacement.reload();
    await expect(
      replacement.getByRole("heading", {
        name: "Connect to my family",
        exact: true,
      }),
    ).toBeVisible();
  } finally {
    await oldDevice.close();
    await replacementDevice.close();
  }
});

test("reading position survives new illustrations and learning follow-ups preserve drafts and attachments", async ({
  page,
  context,
}) => {
  await login(page);
  const code = await createChild(page);
  const student = await context.newPage();
  await connect(student, code);
  await ask(
    student,
    "Explain math fractions. " +
      "Please explain each step of this learning question. ".repeat(55),
  );
  let releaseDiagram!: () => void;
  const diagramGate = new Promise<void>((resolve) => {
    releaseDiagram = resolve;
  });
  await student.route(
    "**/api/browser/student/api/chat/messages/*/diagram",
    async (route) => {
      await diagramGate;
      await route.continue();
    },
  );
  await student
    .getByRole("button", { name: "Add an illustration", exact: true })
    .click();
  const scroller = student.locator(".message-scroll");
  await scroller.hover();
  await student.mouse.wheel(0, -10000);
  await expect(
    student.getByRole("button", {
      name: "Back to latest messages",
      exact: true,
    }),
  ).toBeVisible();
  releaseDiagram();
  await expect(student.locator(".message.assistant img")).toHaveCount(1);
  await student.evaluate(
    () =>
      new Promise((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(resolve)),
      ),
  );
  await expect(scroller).toHaveJSProperty("scrollTop", 0);
  await student
    .getByRole("button", { name: "Back to latest messages", exact: true })
    .click();
  await expect
    .poll(() =>
      scroller.evaluate(
        (element) =>
          element.scrollHeight - element.scrollTop - element.clientHeight,
      ),
    )
    .toBeLessThan(64);
  const input = student.getByRole("textbox", {
    name: "Ask a question, or add a photo…",
    exact: true,
  });
  await input.fill("Keep this draft for later");
  await student
    .locator("input[type=file]")
    .first()
    .setInputFiles({
      name: "draft.png",
      mimeType: "image/png",
      buffer: Buffer.from(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6kH8AAAAASUVORK5CYII=",
        "base64",
      ),
    });
  await student
    .getByRole("button", { name: "Use this photo", exact: true })
    .click();
  await expect(student.locator(".attachment")).toContainText("Saved");
  const originalAnswer = student.locator(".message.assistant").first();
  await originalAnswer
    .getByRole("button", { name: "Keep explaining", exact: true })
    .click();
  await expect(student.locator(".message.user")).toHaveCount(2);
  await expect(student.locator(".message.assistant").last()).toContainText(
    "What do you notice",
  );
  await expect(input).toHaveValue("Keep this draft for later");
  await expect(student.locator(".attachment")).toContainText("Saved");
  await expect(student.locator(".message.user").last()).not.toContainText(
    "Keep this draft",
  );
  await expect(
    student.locator(".message.user").last().locator("img"),
  ).toHaveCount(0);
  const feedbackSaved = student.waitForResponse(
    (response) =>
      response.url().endsWith("/learning-feedback") &&
      response.request().method() === "POST",
  );
  await scroller.hover();
  await student.mouse.wheel(0, -10000);
  await originalAnswer
    .getByRole("button", { name: "Keep explaining", exact: true })
    .click();
  expect((await (await feedbackSaved).json()).changed).toBe(false);
  await expect(student.locator(".message.user")).toHaveCount(2);
  await originalAnswer
    .getByRole("button", { name: "I don't understand yet", exact: true })
    .click();
  await expect(student.locator(".message.user")).toHaveCount(3);
  await expect(student.locator(".message.assistant").last()).toContainText(
    "What do you notice",
  );
  await expect(input).toHaveValue("Keep this draft for later");
  await expect(student.locator(".attachment")).toContainText("Saved");
  await originalAnswer
    .getByRole("button", { name: "Copy", exact: true })
    .focus();
  await expect(
    originalAnswer.getByRole("button", { name: "Copy", exact: true }),
  ).toBeInViewport();
});

test("home-screen entries stay local and rotating a photo preserves its pixels and draft", async ({
  page,
  context,
}) => {
  await login(page);
  const code = await createChild(page);
  const student = await context.newPage();
  await connect(student, code);
  for (const [tab, role] of [
    [page, "Parent"],
    [student, "Student"],
  ] as const) {
    const href = await tab.locator('link[rel="manifest"]').getAttribute("href");
    const manifest = await (
      await tab.request.get(new URL(href!, tab.url()).href)
    ).json();
    expect(manifest.name).toBe(`AI StudyNest · ${role}`);
    expect(manifest.start_url).toBe("/");
    expect(manifest.scope).toBe("/");
    expect(manifest.display).toBe("standalone");
    for (const icon of manifest.icons) {
      const url = new URL(icon.src, tab.url());
      expect(url.origin).toBe(new URL(tab.url()).origin);
      const response = await tab.request.get(url.href);
      expect(response.ok()).toBe(true);
      const bytes = await response.body();
      const size = Number(icon.sizes.split("x")[0]);
      expect(bytes.readUInt32BE(16)).toBe(size);
      expect(bytes.readUInt32BE(20)).toBe(size);
    }
  }
  const image = await student.evaluate(() => {
    const canvas = document.createElement("canvas");
    canvas.width = 100;
    canvas.height = 60;
    const draw = canvas.getContext("2d")!;
    draw.fillStyle = "red";
    draw.fillRect(0, 0, 40, 60);
    draw.fillStyle = "blue";
    draw.fillRect(40, 0, 60, 60);
    return canvas.toDataURL("image/png").split(",")[1];
  });
  const input = student.getByRole("textbox", {
    name: "Ask a question, or add a photo…",
    exact: true,
  });
  await input.fill("Not sent by rotate");
  await student
    .locator("input[type=file]")
    .first()
    .setInputFiles({
      name: "sideways.png",
      mimeType: "image/png",
      buffer: Buffer.from(image, "base64"),
    });
  await student
    .getByRole("button", { name: "Rotate clockwise", exact: true })
    .click();
  const preview = student.locator("dialog .crop-preview img");
  await expect(preview).toHaveJSProperty("naturalWidth", 60);
  await expect(preview).toHaveJSProperty("naturalHeight", 100);
  expect(
    await preview.evaluate((element: HTMLImageElement) => {
      const canvas = document.createElement("canvas");
      canvas.width = 60;
      canvas.height = 100;
      const draw = canvas.getContext("2d")!;
      draw.drawImage(element, 0, 0);
      return [
        Array.from(draw.getImageData(30, 10, 1, 1).data),
        Array.from(draw.getImageData(30, 80, 1, 1).data),
      ];
    }),
  ).toEqual([
    [255, 0, 0, 255],
    [0, 0, 255, 255],
  ]);
  const uploaded = student.waitForResponse(
    (response) =>
      response.url().includes("/api/browser/student/upload?") &&
      response.request().method() === "POST",
  );
  await student
    .getByRole("button", { name: "Use this photo", exact: true })
    .click();
  expect(await (await uploaded).json()).toMatchObject({
    width: 60,
    height: 100,
  });
  await expect(student.locator(".attachment")).toContainText("Saved");
  await expect(student.locator(".message.user")).toHaveCount(0);
  await expect(input).toHaveValue("Not sent by rotate");
  // A phone in landscape must still let the learner reach Send with a photo attached.
  await student.setViewportSize({ width: 812, height: 270 });
  const send = student.getByRole("button", { name: "Send", exact: true });
  await send.scrollIntoViewIfNeeded();
  await expect(send).toBeInViewport({ ratio: 1 });
  await expect(input).toHaveValue("Not sent by rotate");
  await student.setViewportSize({ width: 375, height: 700 });
  await expect(send).toBeInViewport({ ratio: 1 });
});

test("browser errors explain the next action in all seven languages", async ({
  page,
}) => {
  await page.route("**/api/browser/student/connect", (route) =>
    route.fulfill({
      status: 409,
      contentType: "application/json",
      body: JSON.stringify({
        detail:
          "Ask your parent to confirm the family time zone before connecting.",
      }),
    }),
  );
  await page.goto(studentURL);
  await page.locator('input[name="code"]').fill("ABCDEF12");
  const messages = {
    en: "Ask your parent to confirm the family time zone before connecting.",
    "zh-Hans": "请先让家长确认家庭时区，再连接设备。",
    "zh-Hant": "請先讓家長確認家庭時區，再連接裝置。",
    ja: "接続する前に、保護者に家族のタイムゾーンを確認してもらってください。",
    ko: "연결하기 전에 보호자에게 가족 시간대를 확인해 달라고 요청하세요.",
    de: "Bitte deine Eltern, vor dem Verbinden die Familienzeitzone zu bestätigen.",
    es: "Pide a tu padre o madre que confirme la zona horaria familiar antes de conectar.",
  };
  for (const [language, message] of Object.entries(messages)) {
    await page.locator(".language-picker select").selectOption(language);
    const failed = page.waitForResponse((response) =>
      response.url().endsWith("/browser/student/connect"),
    );
    await page.locator("form button.primary").click();
    expect((await failed).status()).toBe(409);
    await expect(page.locator(".toast")).toContainText(message);
    await expect(page).not.toHaveTitle(/undefined/);
  }
});

test("queued illustrations survive refresh, recover polling and reuse the completed job", async ({
  page,
  context,
}) => {
  await login(page);
  const code = await createChild(page);
  const student = await context.newPage();
  await connect(student, code);
  await ask(student, "Explain math fractions ASYNC_DIAGRAM");
  const input = student.getByRole("textbox", {
    name: "Ask a question, or add a photo…",
    exact: true,
  });
  await input.fill("Keep this draft while the illustration is prepared");
  let polls = 0,
    requests = 0;
  student.on("request", (request) => {
    if (request.method() === "POST" && request.url().endsWith("/diagram"))
      requests++;
  });
  await student.route(
    "**/api/browser/student/api/chat/image-jobs/*",
    (route) => {
      polls++;
      return polls === 1
        ? route.fulfill({
            status: 503,
            contentType: "application/json",
            body: JSON.stringify({
              detail: "Image storage or review is unavailable. Please retry.",
            }),
          })
        : route.continue();
    },
  );
  const created = student.waitForResponse(
    (response) =>
      response.url().endsWith("/diagram") &&
      response.request().method() === "POST",
  );
  await student
    .getByRole("button", { name: "Add an illustration", exact: true })
    .click();
  const job = await (await created).json();
  expect(job.state).toBe("queued");
  await expect(
    student.getByText("Preparing illustration…", { exact: true }),
  ).toBeVisible();
  await student.reload();
  await expect(input).toHaveValue(
    "Keep this draft while the illustration is prepared",
  );
  await expect(student.locator(".message.assistant img")).toBeVisible();
  expect(polls).toBeGreaterThanOrEqual(2);
  expect(requests).toBe(1);
  const existing = student.waitForResponse(
    (response) =>
      response.url().endsWith("/diagram") &&
      response.request().method() === "POST",
  );
  await student
    .getByRole("button", { name: "Add an illustration", exact: true })
    .click();
  expect((await (await existing).json()).id).toBe(job.id);
  await expect(student.locator(".message.assistant img")).toHaveCount(1);
  await expect(input).toHaveValue(
    "Keep this draft while the illustration is prepared",
  );
  await page.goto(parentURL + "/activity");
  await page.locator(".conversation-row").first().click();
  await expect(page.locator(".transcript img")).toBeVisible();
});
