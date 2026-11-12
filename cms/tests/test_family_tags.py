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
let ROLE='super',tags=[],tag=null,registration_channel=null,registration_device=null;
const api=async path=>path.startsWith('/admin/llm-groups')
  ? {items:tags.map(tag=>({tag}))}
  : {total:1,items:[{family_id:7,tag,registration_channel,registration_device,guardians:[],students:[],message_count:0}]};
'''
    checks = r'''
(async()=>{
  await loadFamilies();
  assert(tbody.innerHTML.includes('未设置标签'));
  assert(tbody.innerHTML.includes('disabled'));
  assert(!tbody.innerHTML.includes('清除'));
  assert(tbody.innerHTML.includes('未记录'));
  registration_channel='googleplay';registration_device={brand:'Xiaomi',model:'<device>',ip_address:'2001:db8::17'};
  await loadFamilies();
  assert(tbody.innerHTML.includes('Google Play'));assert(tbody.innerHTML.includes('Xiaomi &lt;device&gt;'));
  assert(tbody.innerHTML.includes('&lt;device&gt;'));assert(!tbody.innerHTML.includes('<device>'));
  assert(tbody.innerHTML.includes('IP：2001:db8::17'));
  assert(!tbody.innerHTML.includes('查看设备信息'));
  registration_device={platform:'android'}; await loadFamilies();
  assert(tbody.innerHTML.includes('品牌型号未记录'));assert(tbody.innerHTML.includes('IP：未记录'));
  registration_channel='web';registration_device={platform:'web',brand:'忽略品牌',model:'忽略型号',user_agent:'Mozilla/5.0 <browser> "quoted"',ip_address:'198.51.100.1'};
  await loadFamilies();
  assert(tbody.innerHTML.includes('title="Mozilla/5.0 &lt;browser&gt; &quot;quoted&quot;"'));
  assert(tbody.innerHTML.includes('>Mozilla/5.0 &lt;browser&gt; &quot;quoted&quot;</span>'));
  assert(!tbody.innerHTML.includes('忽略品牌'));assert(!tbody.innerHTML.includes('<browser>'));
  assert(tbody.innerHTML.includes('IP：198.51.100.1'));
  registration_device=null;await loadFamilies();assert(tbody.innerHTML.includes('User-Agent 未记录'));
  registration_channel=null;registration_device={platform:'web',user_agent:'Platform web UA'};
  await loadFamilies();assert(tbody.innerHTML.includes('>Platform web UA</span>'));
  registration_channel='googleplay';registration_device={brand:'Xiaomi',model:'Phone',user_agent:'Native UA'};
  await loadFamilies();assert(tbody.innerHTML.includes('>Xiaomi Phone</span>'));assert(!tbody.innerHTML.includes('Native UA'));
  registration_channel=null;
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
