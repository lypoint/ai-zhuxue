import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import ts from 'typescript';
const source = fs.readFileSync(new URL('../src/math-markdown.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ES2022}}).outputText;
const {normalizeMathMarkdown:normalize} = await import('data:text/javascript;base64,' + Buffer.from(compiled).toString('base64'));

test('normalizes live-provider TeX alongside existing dollar math',()=>{
 assert.equal(normalize(String.raw`Why \(7 \times 8 = 56\), and $x^2$.`),String.raw`Why $7 \times 8 = 56$, and $x^2$.`);
 assert.equal(normalize('First\\[\nx+y=3\n\\]Last'),'First\n$$\nx+y=3\n$$\nLast');
});
test('preserves code fences, variable backtick spans and unfinished streamed code',()=>{
 for(const code of [String.raw`\(x\)`,String.raw`\[x\]`]){
  for(const fence of ['```','````','~~~']){
   const source=fence+'text\n'+code+'\n'+fence+'\nThen \\(y\\)';
   assert.equal(normalize(source),fence+'text\n'+code+'\n'+fence+'\nThen $y$');
   assert.equal(normalize(fence+'text\n'+code),fence+'text\n'+code);
  }
  assert.equal(normalize('`'+code+'` and \\(y\\)'), '`'+code+'` and $y$');
  assert.equal(normalize('``a ` '+code+'`` and \\(y\\)'), '``a ` '+code+'`` and $y$');
 }
});
test('a shorter fence inside a longer code block does not expose formulas',()=>{
 const source='````\n```\n\\(x\\)\n```\n````\n\\(y\\)';
 assert.equal(normalize(source),'````\n```\n\\(x\\)\n```\n````\n$y$');
});
