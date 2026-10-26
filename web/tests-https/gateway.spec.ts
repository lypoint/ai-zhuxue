import { test, expect } from "@playwright/test";
import { randomUUID } from "node:crypto";

const parent = "https://localhost:18443";
const student = "https://127.0.0.1:19443";

test("HTTPS gateway enforces role routes, secure host-only cookies, CSP and unbuffered SSE", async ({
  page,
  context,
}) => {
  for (const origin of [parent, student]) {
    const html = await (await page.request.get(origin)).text();
    const script = html.match(/<script[^>]*src="([^"]+)"/);
    expect(script).not.toBeNull();
    const response = await page.request.get(new URL(script![1], origin).href, {
      headers: { "Accept-Encoding": "gzip" },
    });
    expect(response.headers()["content-encoding"]).toBe("gzip");
    expect(response.headers()["content-type"]).toContain("javascript");
    expect((await response.body()).length).toBeGreaterThan(100_000);
  }
  const document = await page.goto(parent + "/activity/123");
  expect(document!.status()).toBe(200);
  expect(document!.headers()["content-security-policy"]).toContain(
    "frame-ancestors 'none'",
  );
  expect(document!.headers()["strict-transport-security"]).toContain(
    "max-age=31536000",
  );
  expect(document!.headers()["cache-control"]).toContain("no-store");
  expect(await page.evaluate(() => window.isSecureContext)).toBe(true);
  const login = await page.request.post(parent + "/api/browser/parent/login", {
    headers: { Origin: parent },
    data: { id_token: "acceptance-google-" + randomUUID() },
  });
  expect(login.ok()).toBe(true);
  const parentHeaders = {
    Origin: parent,
    "X-CSRF-Token": (await login.json()).csrf_token,
  };
  expect(
    (
      await page.request.put(
        parent + "/api/browser/parent/api/parent/timezone",
        {
          headers: parentHeaders,
          data: { timezone: "UTC" },
        },
      )
    ).ok(),
  ).toBe(true);
  const child = await page.request.post(
    parent + "/api/browser/parent/api/parent/students",
    {
      headers: parentHeaders,
      data: { nickname: "HTTPS acceptance" },
    },
  );
  expect(child.ok()).toBe(true);
  const connected = await page.request.post(
    student + "/api/browser/student/connect",
    {
      headers: { Origin: student },
      data: {
        bind_code: (await child.json()).bind_code,
        installation_id: randomUUID(),
      },
    },
  );
  expect(connected.ok()).toBe(true);
  const studentCSRF = (await connected.json()).csrf_token;
  for (const [name, domain] of [
    ["parent", "localhost"],
    ["student", "127.0.0.1"],
  ]) {
    const cookie = (await context.cookies()).find(
      (cookie) => cookie.name === `__Host-ailearning-${name}`,
    );
    expect(cookie).toMatchObject({
      domain,
      path: "/",
      httpOnly: true,
      secure: true,
      sameSite: "Strict",
    });
  }
  expect(
    (await page.request.get(student + "/api/browser/parent/session")).status(),
  ).toBe(404);
  expect(
    (await page.request.get(parent + "/api/browser/student/session")).status(),
  ).toBe(404);
  expect(
    (await page.request.get(student + "/api/chat/my-stats")).status(),
  ).toBe(404);
  expect(
    (
      await page.request.post(student + "/api/browser/student/logout", {
        headers: { Origin: parent, "X-CSRF-Token": studentCSRF },
      })
    ).status(),
  ).toBe(403);
  const learningDocument = await page.goto(student + "/chat");
  const policy = learningDocument!.headers()["content-security-policy"];
  expect(policy).toContain("connect-src 'self'");
  expect(policy).toContain("frame-src 'none'");
  expect(policy).not.toContain("google");
  expect(await page.evaluate(() => document.cookie)).not.toContain(
    "ailearning",
  );
  const timing = await page.evaluate(async (csrf) => {
    const start = performance.now();
    const response = await fetch("/api/browser/student/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
      body: JSON.stringify({
        content: "Explain math SLOW_RESPONSE",
        locale: "en",
      }),
    });
    const reader = response.body!.getReader();
    const decoder = new TextDecoder();
    let first = 0,
      body = "";
    while (true) {
      const chunk = await reader.read();
      if (chunk.done) break;
      if (!first) first = performance.now() - start;
      body += decoder.decode(chunk.value, { stream: true });
    }
    return {
      status: response.status,
      trace: response.headers.get("X-Trace-Id"),
      serverTiming: response.headers.get("Server-Timing"),
      first,
      finished: performance.now() - start,
      body,
    };
  }, studentCSRF);
  expect(timing.status).toBe(200);
  expect(timing.trace).toMatch(/^[0-9a-f-]{36}$/);
  expect(timing.serverTiming).toContain(`trace;desc="${timing.trace}"`);
  expect(timing.serverTiming).toMatch(/edge_upstream_headers;dur=[0-9.]+/);
  expect(timing.serverTiming).not.toContain("{http.");
  expect(timing.body).toContain("event: meta");
  expect(timing.body).toContain("event: done");
  expect(timing.finished - timing.first).toBeGreaterThan(2500);
});
