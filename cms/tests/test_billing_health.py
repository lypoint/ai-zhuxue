"""Payment callback alerts render failure, recovery and monitor outages."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_billing_health_alert_and_recovery():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js required')
    html = Path(__file__).resolve().parents[1].joinpath('index.html').read_text()
    script = html[html.index('async function loadBillingHealth()'):html.index('async function loadOperations()')]
    harness = r'''
const assert=require('node:assert/strict');
const field={setAttribute(k,v){this[k]=v}};
const $=()=>field;
let response={alert:true,channels:[{channel:'waffo',pending:3,oldest_age_seconds:600,max_attempts:3}]};
async function api(path){assert.equal(path,'/admin/billing/notification-health');if(response instanceof Error)throw response;return response;}
'''+script+r'''
(async()=>{
await loadBillingHealth();assert.equal(field.role,'alert');assert.match(field.textContent,/待处理 3/);
response={alert:false,channels:[]};await loadBillingHealth();assert.equal(field.role,'status');assert.match(field.textContent,/无重试积压/);
response=new Error('private');await loadBillingHealth();assert.equal(field.role,'alert');assert.match(field.textContent,/监控不可用/);assert.ok(!field.textContent.includes('private'));
})().catch(error=>{console.error(error);process.exitCode=1});
'''
    result = subprocess.run([node, '-e', harness], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
