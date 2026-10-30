import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";

test("high contrast preserves keyboard focus on fields and the borderless chat composer", async ({ page, browserName }) => {
  test.skip(browserName !== "chromium", "Forced colors emulation requires Chromium.");
  const css = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");
  await page.emulateMedia({ forcedColors: "active" });
  await page.setContent(`<style>${css}</style>
    <input aria-label="Name">
    <select aria-label="Language"><option>English</option></select>
    <textarea aria-label="Notes"></textarea>
    <div class="composer"><textarea aria-label="Question"></textarea></div>`);

  for (const name of ["Name", "Language", "Notes", "Question"]) {
    await page.keyboard.press("Tab");
    const field = page.getByLabel(name, { exact: true });
    await expect(field).toBeFocused();
    await expect(field).toHaveCSS("box-shadow", "none");
    await expect(field).toHaveCSS("outline-style", "solid");
    await expect(field).toHaveCSS("outline-width", "2px");
  }
});
