"""Family labels display their state without a duplicate badge or clear action."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_family_tag_empty_assigned_orphan_and_readonly_states():
    node = shutil.which('node')
    if not node:
        pytest.skip('JavaScript check needs Node.js')
    html = (Path(__file__).resolve().parents[1] / 'index.html').read_text()
    script = html[html.index('let familyPage='):html.index('async function assistBind(')]
    harness = r'''
const assert=require('node:assert/strict');
const tbody={innerHTML:''};
const $=()=>({querySelector:()=>tbody});
const esc=value=>String(value??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
let ROLE='super',tags=[],tag=null;
const api=async path=>path.startsWith('/admin/llm-groups')
  ? {items:tags.map(tag=>({tag}))}
  : {total:1,items:[{family_id:7,tag,guardians:[],students:[],message_count:0}]};
'''
    checks = r'''
(async()=>{
  await loadFamilies();
  assert(tbody.innerHTML.includes('未设置标签'));
  assert(tbody.innerHTML.includes('disabled'));
  assert(!tbody.innerHTML.includes('清除'));
  tags=['内测']; await loadFamilies();
  assert(!tbody.innerHTML.includes('disabled'));
  assert(tbody.innerHTML.includes('value="" selected>未设置标签'));
  tag='内测'; await loadFamilies();
  assert(tbody.innerHTML.includes('is-set'));
  assert(tbody.innerHTML.includes('value="内测" selected'));
  assert(tbody.innerHTML.includes('移除标签'));
  assert(!tbody.innerHTML.includes('tag beta-tag'));
  tag='<旧标签>'; await loadFamilies();
  assert(tbody.innerHTML.includes('value="&lt;旧标签&gt;" selected'));
  assert(!tbody.innerHTML.includes('<旧标签>'));
  ROLE='support'; await loadFamilies();
  assert(!tbody.innerHTML.includes('<select'));
  assert(tbody.innerHTML.includes('&lt;旧标签&gt;'));
  tag=null; await loadFamilies();
  assert(tbody.innerHTML.includes('未设置标签'));
})().catch(e=>{console.error(e);process.exit(1)});
'''
    subprocess.run([node, '-e', harness+script+checks], check=True,
                   capture_output=True, text=True)
