import fs from "node:fs";
import assert from "node:assert/strict";
import ts from "typescript";

const root = new URL("../", import.meta.url);
const source = fs.readFileSync(new URL("src/i18n.ts", root), "utf8");
const ast = ts.createSourceFile(
  "i18n.ts",
  source,
  ts.ScriptTarget.Latest,
  true,
);
const english = {},
  core = {};
function walk(node) {
  if (ts.isVariableDeclaration(node) && node.name.getText(ast) === "en") {
    for (const property of node.initializer.properties)
      english[property.name.getText(ast)] = property.initializer.text;
  }
  if (ts.isVariableDeclaration(node) && node.name.getText(ast) === "core") {
    for (const property of node.initializer.properties)
      core[property.name.getText(ast)] = property.initializer.elements.map(
        (value) => value.text,
      );
  }
  ts.forEachChild(node, walk);
}
walk(ast);
const catalog = JSON.parse(
  fs.readFileSync(
    new URL("../app/app_core/assets/i18n/catalog.json", root),
    "utf8",
  ),
);
const web = JSON.parse(
  fs.readFileSync(new URL("src/web-translations.json", root), "utf8"),
);
const aliases = new Map(
  Object.entries(catalog.en).map(([key, value]) => [
    value.trim().toLowerCase(),
    key,
  ]),
);
const locales = ["zh-Hans", "zh-Hant", "ja", "ko", "de", "es"];
for (const [key, values] of Object.entries({ ...core, ...web })) {
  assert.ok(english[key], `Unknown translation key: ${key}`);
  assert.equal(values.length, locales.length, `Missing locale: ${key}`);
  assert.ok(
    values.every((value) => typeof value === "string" && value.trim()),
    `Empty translation: ${key}`,
  );
}
for (const [key, value] of Object.entries(english)) {
  const alias = aliases.get(value.toLowerCase());
  locales.forEach((locale, index) => {
    const translated =
      web[key]?.[index] ||
      core[key]?.[index] ||
      (alias && catalog[locale][alias]);
    assert.ok(translated, `Untranslated: ${locale}/${key}`);
    assert.deepEqual(
      (translated.match(/\{\{.*?\}\}/g) || []).sort(),
      (value.match(/\{\{.*?\}\}/g) || []).sort(),
      `Interpolation mismatch: ${locale}/${key}`,
    );
  });
}
console.log(
  `PASS: ${Object.keys(english).length} semantic UI keys in all seven languages; interpolation preserved.`,
);
