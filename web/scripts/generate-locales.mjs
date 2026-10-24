import fs from 'node:fs';
import ts from 'typescript';

const root = new URL('../', import.meta.url);
const read = path => JSON.parse(fs.readFileSync(new URL(path, root), 'utf8'));
const catalog = read('../app/app_core/assets/i18n/catalog.json');
const metadata = read('../server/app/locales.json');
const web = read('src/web-translations.json');
const expanded = read('src/expanded-translations.json');
const ast = ts.createSourceFile('i18n.ts', fs.readFileSync(new URL('src/i18n.ts', root), 'utf8'), ts.ScriptTarget.Latest, true);
const sources = {};
function walk(node) {
  if (ts.isVariableDeclaration(node) && ['en', 'core'].includes(node.name.getText(ast))) {
    const values = {};
    for (const property of node.initializer.properties) {
      values[property.name.getText(ast)] = property.initializer.elements
        ? property.initializer.elements.map(value => value.text)
        : property.initializer.text;
    }
    sources[node.name.getText(ast)] = values;
  }
  ts.forEachChild(node, walk);
}
walk(ast);
const aliases = new Map(Object.entries(catalog.en).map(([key, value]) => [value.trim().toLowerCase(), key]));
const legacy = ['zh-Hans', 'zh-Hant', 'ja', 'ko', 'de', 'es'];
const directory = new URL('src/generated-locales/', root);
fs.mkdirSync(directory, {recursive:true});
function write(name, data) {
  const target = new URL(name + '.json', directory);
  const content = JSON.stringify(data) + '\n';
  if (fs.existsSync(target) && fs.readFileSync(target, 'utf8') === content) return;
  const temporary = new URL(name + '.' + process.pid + '.tmp', directory);
  fs.writeFileSync(temporary, content);
  fs.renameSync(temporary, target);
}
for (const locale of Object.keys(metadata)) {
  const translation = {};
  const index = legacy.indexOf(locale);
  for (const [key, value] of Object.entries(sources.en)) {
    const alias = aliases.get(value.toLowerCase());
    translation[key] = locale === 'en' ? value :
      expanded[locale]?.[key] || web[key]?.[index] || sources.core[key]?.[index] ||
      (alias && catalog[locale][alias]) || value;
  }
  write(locale, {translation, catalog:catalog[locale]});
}
write('messages', catalog._messages);
