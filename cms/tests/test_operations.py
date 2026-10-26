"""The operations panel preserves null rates and escapes unexpected labels."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_operations_panel_renders_cohort_and_retention_safely():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js required')
    html = Path(__file__).resolve().parents[1].joinpath('index.html').read_text()
    script = html[html.index('async function loadOperations()'):html.index('async function loadFence()')]
    harness = r'''
const assert=require('node:assert/strict');
const fields={operationsStart:{value:'2026-09-01'},operationsEnd:{value:'2026-09-30'},operationsTest:{checked:false},
operationsLoad:{disabled:false},operationsStatus:{},operationsReport:{innerHTML:'',replaceChildren(){this.innerHTML=''}}};
const $=id=>fields[id];
const esc=value=>String(value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
const f={mature_families:0,pending_families:2,steps:[{event:'<script>unexpected</script>',families:0,from_previous:null,from_start:null}]};
async function api(path){assert.ok(path.includes('include_test=false')); return {
registered_families:2,as_of:'2026-10-26T00:00:00Z',activation:f,student_experience:f,checkout:f,trial_to_paid:f,subscription_activation:f,
retention:[{day:7,eligible_families:0,returned_families:0,rate:null}]};}
'''
    harness += script + r'''
loadOperations().then(()=>{
assert.equal(fields.operationsLoad.disabled,false);
assert.match(fields.operationsReport.innerHTML,/待观察 2/);
assert.match(fields.operationsReport.innerHTML,/&lt;script&gt;/);
assert.ok(!fields.operationsReport.innerHTML.includes('<script>'));
assert.match(fields.operationsReport.innerHTML,/<td>—<\/td>/);
assert.ok(!fields.operationsReport.innerHTML.includes('NaN'));
}).catch(error=>{console.error(error);process.exitCode=1});
'''
    result = subprocess.run([node, '-e', harness], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr


def test_performance_panel_escapes_labels_and_preserves_missing_values():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js required')
    html = Path(__file__).resolve().parents[1].joinpath('index.html').read_text()
    script = html[html.index('async function loadPerformance()'):html.index('async function loadFence()')]
    harness = r'''
const assert=require('node:assert/strict');
const fields={performanceStart:{value:'2026-10-26'},performanceEnd:{value:'2026-10-26'},performanceLoad:{disabled:false},performanceStatus:{},performanceReport:{innerHTML:'',replaceChildren(){this.innerHTML=''}}};
const $=id=>fields[id];
const esc=value=>String(value).replaceAll('<','&lt;').replaceAll('>','&gt;');
async function api(path){assert.ok(path.startsWith('/admin/analytics/performance?')); return {groups:[{
operation:'chat_stream',model:'<script>unexpected</script>',server_samples:3,paired_samples:2,browser_errors:1,negative_residual_samples:0,
metrics:{model_ms:{samples:0,p50_ms:null,p95_ms:null}}}]};}
'''
    harness += script + r'''
loadPerformance().then(()=>{
assert.equal(fields.performanceLoad.disabled,false);
assert.match(fields.performanceReport.innerHTML,/&lt;script&gt;/);
assert.ok(!fields.performanceReport.innerHTML.includes('<script>'));
assert.match(fields.performanceReport.innerHTML,/<td>—<\/td>/);
assert.ok(!fields.performanceReport.innerHTML.includes('NaN'));
}).catch(error=>{console.error(error);process.exitCode=1});
'''
    result = subprocess.run([node, '-e', harness], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
