import { test, expect, type Page } from "@playwright/test";

test.skip(!process.env.WEB_TEST_FIREBASE_CONFIG, "Run with the synthetic Web Firebase config; never use a real property in this test.");
const parentURL = process.env.WEB_TEST_PARENT_URL || "http://localhost:5173";
const studentURL = process.env.WEB_TEST_STUDENT_URL || "http://localhost:5174";

async function mockBusiness(page: Page, connected = false) {
  await page.route("**/api/browser/parent/**", route => {
    const path = new URL(route.request().url()).pathname;
    const json = path.endsWith("/session") ? {role:"parent",id:1,family_id:1,nickname:"Private Parent",csrf_token:"private-csrf"}
      : path.endsWith("/family") ? {guardian:{id:1,nickname:"Private Parent"},students:connected ? [{id:111,nickname:"Private Child",active:true,grade_band:"8-12",seat_status:"active",fence_settings:{fence_level:"off",forbidden_words:[]},current_device:{name:"Private Device",last_seen_at:"2026-10-26T00:00:00Z"}}] : [],timezone:"UTC",settings:{}}
      : path.endsWith("/catalog") ? {enabled:false,items:[]}
      : path.endsWith("/subscription") ? {active:true,plan:"free_trial",expires_at:"2027-01-01T00:00:00Z",seat_count:1,used_seats:0}
      : path.endsWith("/notifications/unread-count") ? {count:0}
      : path.endsWith("/usage") ? {today:{tokens_in:0,tokens_out:0},total:{tokens_in:0,tokens_out:0}} : {};
    return route.fulfill({json: path.endsWith("/devices") ? [] : json});
  });
}
async function mockGoogle(page: Page) {
  let requests = 0;
  page.on("request", request => { if (/google-analytics|googletagmanager|firebase.*googleapis/.test(request.url())) requests++; });
  await page.route("https://firebase.googleapis.com/**", route => route.fulfill({json:{appId:"1:123:web:test",measurementId:"G-TEST",projectId:"test"}}));
  await page.route("https://firebaseinstallations.googleapis.com/**", async route => {
    const body = route.request().postDataJSON();
    await route.fulfill({json:{name:"projects/test/installations/test",fid:body?.fid || "cabcdefghijklmnopqrstu",refreshToken:"synthetic",authToken:{token:"synthetic",expiresIn:"3600s"}}});
  });
  await page.route("https://www.googletagmanager.com/**", route => route.fulfill({contentType:"application/javascript",body:"/* Test gtag transport: commands remain in dataLayer. */"}));
  await page.route(/https:\/\/[^/]*(google-analytics|analytics\.google)\.com\//, route => route.fulfill({status:204,body:""}));
  return () => requests;
}
async function commands(page: Page) {
  return page.evaluate(() => ((window as any).dataLayer || []).map((row: any) => Array.from(row)));
}
test("real Firebase SDK waits for consent, strips private URLs, and stops after withdrawal", async ({page}) => {
  const count = await mockGoogle(page);
  const firstParty: unknown[] = [];
  page.on("request", request => {
    if (new URL(request.url()).pathname === "/api/browser/parent/events") firstParty.push(request.postDataJSON());
  });
  await mockBusiness(page, true);
  await page.goto(parentURL + "/subscription?checkout_id=private-checkout#private-message");
  await expect(page.getByRole("button",{name:"Accept All",exact:true})).toBeVisible();
  expect(count()).toBe(0);
  expect(firstParty).toHaveLength(0);
  await page.getByRole("button",{name:"Accept All",exact:true}).click();
  await expect.poll(async () => (await commands(page)).filter((row: any) => row[0] === "event" && row[1] === "page_view").length).toBeGreaterThan(0);
  await expect.poll(async () => (await commands(page)).filter((row: any) => row[0] === "event" && row[1] === "child_connected_observed").length).toBe(1);
  await expect.poll(() => firstParty.length).toBeGreaterThan(0);
  expect(JSON.stringify(firstParty)).not.toMatch(/private-checkout|private-message|Private Parent|Private Child|private-csrf/);
  const sent = await commands(page);
  const config = sent.find((row: any) => row[0] === "config" && row[1] === "G-TEST")?.[2] as any;
  expect(config.send_page_view).toBe(false);
  expect(config.allow_google_signals).toBe(false);
  const events = sent.filter((row: any) => row[0] === "event");
  expect(JSON.stringify(events)).not.toMatch(/private-checkout|private-message|Private Parent|Private Child|Private Device|private-csrf/);
  expect(events.find((row: any) => row[1] === "page_view")?.[2]).toMatchObject({page_name:"subscription",page_location:parentURL + "/subscription",page_referrer:""});
  await page.getByRole("button",{name:"Data Privacy & Consent",exact:true}).click();
  await page.getByRole("button",{name:"Essential Only",exact:true}).click();
  expect(await page.evaluate(() => (window as any)["ga-disable-G-TEST"])).toBe(true);
  const before = (await commands(page)).filter((row: any) => row[0] === "event").length;
  const firstPartyBefore = firstParty.length;
  await page.getByRole("link",{name:"Children & devices",exact:true}).click();
  await expect(page.getByRole("heading",{name:"Private Child",exact:true})).toBeVisible();
  expect((await commands(page)).filter((row: any) => row[0] === "event").length).toBe(before);
  expect(firstParty).toHaveLength(firstPartyBefore);
});
test("essential-only choice persists and never loads Firebase", async ({page}) => {
  const count = await mockGoogle(page);
  await mockBusiness(page);
  await page.goto(parentURL + "/subscription");
  await page.getByRole("button",{name:"Essential Only",exact:true}).click();
  await page.reload();
  await expect(page.getByRole("button",{name:"Data Privacy & Consent",exact:true})).toBeVisible();
  await expect(page.getByRole("button",{name:"Accept All",exact:true})).toHaveCount(0);
  expect(count()).toBe(0);
});
test("student Web never loads Firebase or offers an analytics prompt", async ({page}) => {
  const count = await mockGoogle(page);
  await page.route("**/api/browser/student/session", route => route.fulfill({status:401,json:{detail:"Sign in"}}));
  await page.goto(studentURL);
  await expect(page.getByRole("button",{name:"Data Privacy & Consent",exact:true})).toHaveCount(0);
  expect(count()).toBe(0);
});
