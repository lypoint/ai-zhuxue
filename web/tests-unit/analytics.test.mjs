import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import ts from 'typescript';

const source = fs.readFileSync(new URL('../src/parent-analytics.ts', import.meta.url), 'utf8');
async function load(role = 'parent') {
  const events = [], collections = [], values = new Map();
  let loads = 0;
  globalThis.window = new EventTarget();
  globalThis.location = new URL('https://parents.example/activity/123?checkout_id=private#message-456');
  globalThis.document = { cookie: '' };
  globalThis.localStorage = { getItem: k => values.get(k) ?? null, setItem: (k, v) => values.set(k, v) };
  globalThis.analyticsTestSDK = { createAnalytics: async () => {
    loads++;
    return { log: (event, parameters) => events.push({ event, parameters }), consent: value => collections.push(value) };
  } };
  const compiled = ts.transpileModule(source, { compilerOptions: {target:ts.ScriptTarget.ES2022, module:ts.ModuleKind.ES2022} }).outputText
    .replace('import { browserEvent } from "./api";', 'const browserEvent = () => {};')
    .replaceAll('__WEB_ROLE__', JSON.stringify(role))
    .replaceAll('__PARENT_FIREBASE_CONFIG__', JSON.stringify({apiKey:'test', appId:'1:123:web:test', projectId:'test', measurementId:'G-TEST'}))
    .replace('import("./firebase-analytics")', 'Promise.resolve(globalThis.analyticsTestSDK)');
  const api = await import('data:text/javascript;base64,' + Buffer.from(compiled).toString('base64') + '#' + crypto.randomUUID());
  return { api, events, collections, values, loads: () => loads };
}
test('no consent means no SDK load, no queued events, and no tracking', async () => {
  const { api, events, loads } = await load();
  await api.track('login');
  assert.equal(loads(), 0);
  api.setAnalyticsConsent(false);
  await api.track('login');
  assert.equal(loads(), 0);
  api.setAnalyticsConsent(true);
  await api.track('sign_up');
  assert.deepEqual(events.map(e => e.event), ['sign_up']);
});
test('only enum parameters and canonical pages reach Firebase', async () => {
  const { api, events } = await load();
  api.setAnalyticsConsent(true);
  await api.track('page_view', {provider:'private-token', seat_count:2, status:200, email:'private@example.com', content:'private learning'}, 'activity/123?secret');
  assert.deepEqual(events[0].parameters, {seat_count:2, status:200, page_name:'activity', page_location:'https://parents.example/activity', page_title:'AI StudyNest Parent', page_referrer:''});
  await api.track('unknown-event', {status:200});
  assert.equal(events.length, 1);
  assert.equal(api.analyticsPage('/not-a-page/private?token=value'), 'other');
});
test('revocation stops collection immediately, including after cross-tab changes', async () => {
  const { api, events, collections, values } = await load();
  api.setAnalyticsConsent(true);
  await api.track('login');
  values.set('parent-analytics-choice', 'denied');
  const event = new Event('storage');
  Object.assign(event, {key:'parent-analytics-choice'});
  window.dispatchEvent(event);
  assert.equal(window['ga-disable-G-TEST'], true);
  await api.track('trial_start');
  assert.equal(events.length, 1);
  assert.equal(collections.at(-1), false);
});
test('API events do not leak resource IDs and ignore all learning content routes', async () => {
  const { api, events } = await load();
  api.setAnalyticsConsent(true);
  for (const path of ['/api/parent/students/123/rebind-code','/api/parent/waffo/verify','/api/parent/conversations/456/messages'])
    window.dispatchEvent(new CustomEvent('parent-api-result', {detail:{path,method:'POST',status:200}}));
  await api.track('login');
  assert.deepEqual(events.map(e => e.event).sort(), ['bind_code_create','login','subscription_verify'].sort());
  assert.ok(!JSON.stringify(events).includes('123'));
  assert.ok(!JSON.stringify(events).includes('456'));
});
test('student role never enables Firebase even with a config and a saved grant', async () => {
  const { api, loads, events } = await load('student');
  api.setAnalyticsConsent(true);
  await api.track('login');
  assert.equal(api.analyticsConfigured, false);
  assert.equal(loads(), 0);
  assert.equal(events.length, 0);
});
