import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import ts from 'typescript';
const source = fs.readFileSync(new URL('../src/locale.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ES2022}}).outputText;
const {resolveLocale} = await import('data:text/javascript;base64,' + Buffer.from(compiled).toString('base64'));
const locales = JSON.parse(fs.readFileSync(new URL('../../server/app/locales.json', import.meta.url)));
const supported = Object.keys(locales);
test('all 78 selections retain their canonical region and script', () => {
  assert.equal(supported.length, 78);
  for (const tag of supported) assert.equal(resolveLocale(tag, supported), tag);
});
test('device aliases resolve to the correct regional preference', () => {
  for (const [input, expected] of Object.entries({
    'es-MX':'es-419', 'es-US':'es-US', 'es-ES':'es', 'es-PH':'es',
    'fr-Latn-CA':'fr-CA', 'es-Latn-US':'es-US', 'pt-Latn-PT':'pt-PT',
    'fr':'fr-FR', 'fr-CA':'fr-CA', 'pt-PT':'pt-PT', 'pt':'pt-BR',
    'zh-HK':'zh-Hant-HK', 'zh-TW':'zh-Hant', 'zh-Hans-HK':'zh-Hans',
    'zh_Hant':'zh-Hant', 'no-NO':'nb', 'xx':'en', 'en-US':'en',
  })) assert.equal(resolveLocale(input, supported), expected, input);
  assert.deepEqual(supported.filter(tag => locales[tag].rtl), ['ar','he','ur','fa']);
});
