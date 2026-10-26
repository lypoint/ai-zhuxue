import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
const source=fs.readFileSync(new URL('../src/request-performance.ts', import.meta.url),'utf8');
const code=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText;
function load(overrides={}) {
 const context=vm.createContext({exports:{},crypto:{randomUUID:()=> '11111111-1111-4111-8111-111111111111'},performance:{now:()=>10},...overrides});
 vm.runInContext(code,context);
 return context.exports;
}
test('missing UUID API or resource observer does not interrupt learning',()=>{
 const perf=load({crypto:{}});
 assert.equal(perf.startPerformance('chat_stream',()=>{}),undefined);
 assert.doesNotThrow(()=>perf.observeImagePerformance(()=>{})());
 const broken=load({PerformanceObserver:class {constructor(){throw Error('unsupported');}}});
 assert.doesNotThrow(()=>broken.observeImagePerformance(()=>{})());
});
test('response UUID correlates metrics, appended timing parses, failed reporting stays optional',()=>{
 let now=10;
 const perf=load({performance:{now:()=>now}});
 let payload;
 const attempt=perf.startPerformance('chat_stream',value=>{payload=value; throw Error('telemetry only');});
 now=30;
 const values={'X-Trace-Id':'22222222-2222-4222-8222-222222222222','Server-Timing':'trace;desc="uuid", app_headers;dur=1, edge_upstream_headers;dur=12.34'};
 attempt.headers({headers:{get:name=>values[name]}});
 now=60; attempt.mark('browser_first_delta_ms');
 now=80; attempt.mark('browser_first_delta_ms');
 attempt.result='success';
 assert.doesNotThrow(()=>attempt.finish());
 assert.equal(payload.trace_id,values['X-Trace-Id']);
 assert.equal(payload.metrics.browser_headers_ms,20);
 assert.equal(payload.metrics.browser_first_delta_ms,50);
 assert.equal(payload.metrics.browser_total_ms,70);
 assert.equal(payload.metrics.edge_upstream_headers_ms,12.34);
 assert.deepEqual(Object.keys(payload).sort(),['metrics','operation','result','trace_id']);
});
