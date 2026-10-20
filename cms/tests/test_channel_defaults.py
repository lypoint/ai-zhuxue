"""Channel controls filter choices and save one channel at a time."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_channel_default_controls_and_save():
    node = shutil.which('node')
    if not node:
        pytest.skip('JavaScript check needs Node.js')
    html = (Path(__file__).resolve().parents[1] / 'index.html').read_text()
    assert '当前分组' not in html
    assert '仅一位默认' not in html
    assert 'setDefaultTeacher(' not in html
    script = html[html.index('const CHANNELS ='):html.index('async function editGroup(')]
    script += html[html.index('async function saveChannelDefault('):html.index('async function delGroup(')]
    harness = r'''
const assert=require('node:assert/strict');
const nodes=new Map();
const $=id=>{if(!nodes.has(id))nodes.set(id,{innerHTML:'',value:'',textContent:''});return nodes.get(id);};
const esc=value=>String(value??'').replaceAll('<','&lt;');
const attr=encodeURIComponent;
let ROLE='super',GROUPS=[];
let defaults={wechat:1,appstore:2,googleplay:null};
const items=[
 {id:1,name:'shared',teacher_name:'<共享>',teacher_channel:'all',teacher_enabled:true,default_channels:['wechat']},
 {id:2,name:'app',teacher_channel:'appstore',teacher_enabled:true,default_channels:['appstore']},
 {id:3,name:'disabled',teacher_channel:'all',teacher_enabled:false},
];
let writes=[];
const api=async(url,options)=>{
 if(options){writes.push({url,body:JSON.parse(options.body)});defaults.wechat=JSON.parse(options.body).teacher_id;return {};}
 return {items,channel_defaults:defaults};
};
const loadLogs=async()=>{};
'''
    checks = r'''
(async()=>{
 await loadGroups();
 const controls=$('channelDefaults').innerHTML;
 const select=channel=>controls.split(`id="default_${channel}"`)[1].split('</select>')[0];
 assert(select('wechat').includes('value="1"'));
 assert(!select('wechat').includes('value="2"'));
 assert(select('appstore').includes('value="2"'));
 assert(!select('googleplay').includes('value="2"'));
 assert(!controls.includes('value="3"'));
 assert(controls.includes('&lt;共享>'));
 assert.equal($('default_wechat').value,1);
 assert.equal($('default_appstore').value,2);
 assert.equal($('default_googleplay').value,'');
 assert($('groups').innerHTML.includes('微信默认'));
 $('default_wechat').value='2';
 await saveChannelDefault('wechat');
 assert.deepEqual(writes[0],{url:'/admin/teacher-defaults/wechat',body:{teacher_id:2}});
 assert.equal($('default_appstore').value,2);
 assert.equal($('channelDefaultStatus').textContent,'微信默认老师已保存');
 ROLE='admin'; await loadGroups();
 assert($('channelDefaults').innerHTML.includes('disabled'));
 assert(!$('channelDefaults').innerHTML.includes('onclick="saveChannelDefault'));
})().catch(error=>{console.error(error);process.exit(1);});
'''
    subprocess.run([node, '-e', harness+script+checks], check=True,capture_output=True,text=True)
