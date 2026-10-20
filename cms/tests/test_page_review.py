"""Pagination, inline account editing and visible audit failures."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_review_interactions():
    node = shutil.which('node')
    if not node:
        pytest.skip('JavaScript checks need Node.js')
    html = (Path(__file__).resolve().parents[1] / 'index.html').read_text()
    fence = html[html.index('let fenceRequest='):html.index('let familyPage=')]
    family = html[html.index('let familyPage='):html.index('async function assistBind(')]
    user = html[html.index('const ADMIN_ROLES='):html.index('function canView(')]
    audit = html[html.index('async function loadLogs('):html.index('if (TOK) boot();')]
    harness = r'''
const assert=require('node:assert/strict');
const els=new Map();
const $=id=>{
 if(!els.has(id)) els.set(id,{value:'',textContent:'',innerHTML:'',hidden:true,disabled:false,
 querySelector(){return this;},scrollIntoView(){},focus(){}});
 return els.get(id);
};
const document={querySelector:()=>$('logTable')};
const esc=v=>String(v??''); const attr=esc; const textPreview=esc; const logDetail=esc;
const DEC={allow:'放行'},CAT={},STAGE={};
let ROLE='super',requests=[],fail=false,pending=null,usersFail=false;
const row=id=>({family_id:id,guardians:[],students:[],message_count:0});
const api=async(path,options)=>{
 requests.push({path,options});
 if(fail) throw new Error('网络错误');
 if(path==='/admin/llm-groups') return {items:[]};
 if(path.startsWith('/admin/families?')) {
   const page=Number(new URL('https://test'+path).searchParams.get('page'));
   if(pending && pending.page===page) return new Promise(resolve=>{pending.resolve=resolve});
   return {total:21,items:page>3?[]:[row(page*10)]};
 }
 if(path==='/admin/users') {if(usersFail)throw new Error('刷新失败');return [];}
 if(path.startsWith('/admin/users/')) return {ok:true};
 return {items:[]};
};
'''
    checks = r'''
(async()=>{
 await loadFamilies(); assert.equal($('familyPrev').disabled,true);assert.equal($('familyNext').disabled,false);
 assert.match($('familyPagination').textContent,/共 21/);
 await loadFamilies(3);assert.equal($('familyNext').disabled,true);assert.equal($('familyPrev').disabled,false);
 await loadFamilies();assert.equal(familyPage,3);
 await loadFamilies(4);assert.equal(familyPage,3);
 pending={page:1};const old=loadFamilies(1);
 await Promise.resolve(); await Promise.resolve();
 await loadFamilies(2);pending.resolve({total:21,items:[row(999)]});await old;
 assert(! $('famTable').innerHTML.includes('999'));assert.match($('familyPagination').textContent,/第 2/);
 fail=true; await loadFamilies();assert.match($('familyStatus').textContent,/加载失败/);assert.equal($('famTable').innerHTML,'');
 fail=false;
 editUser(7,'admin','原备注','演示');assert.equal($('userEditor').hidden,false);assert.equal($('ue_password').value,'');
 $('ue_password').value='short';let count=requests.length;await saveUser();assert.equal(requests.length,count);
 $('ue_password').value='x'.repeat(129);await saveUser();assert.equal(requests.length,count);
 $('ue_password').value='';$('ue_role').value='invalid';await saveUser();assert.equal(requests.length,count);
 $('ue_role').value='support';$('ue_note').value='x'.repeat(101);await saveUser();assert.equal(requests.length,count);
 $('ue_note').value=' 新备注 ';fail=true;await saveUser();assert.equal($('userEditor').hidden,false);assert.equal($('saveUserButton').disabled,false);
 fail=false;await saveUser();let req=requests.findLast(r=>r.options?.method==='PATCH');
 assert.deepEqual(JSON.parse(req.options.body),{role:'support',note:'新备注'});assert.equal($('userEditor').hidden,true);
 editUser(7,'admin','','演示');$('ue_password').value='example-test-password';usersFail=true;await saveUser();
 req=requests.findLast(r=>r.options?.method==='PATCH');assert.equal(JSON.parse(req.options.body).password,'example-test-password');
 assert.equal($('ue_password').value,'');assert.match($('userStatus').textContent,/列表加载失败/);
 fail=true;await loadLogs();await loadAssessmentAudits();
 assert.match($('logStatus').textContent,/加载失败/);assert.equal($('logTable').innerHTML,'');
 assert.match($('assessmentStatus').textContent,/加载失败/);
 fail=false;await loadLogs();await loadAssessmentAudits();
 assert.equal($('logStatus').textContent,'已更新');assert.match($('logTable').innerHTML,/暂无操作日志/);
 assert.equal($('assessmentStatus').textContent,'已更新');
 $('fdec').value='allow';await loadFence();assert.match($('fenceStatus').textContent,/放行.*0 条/);
 fail=true;await loadFence();assert.match($('fenceStatus').textContent,/加载失败/);assert.equal($('fenceTable').innerHTML,'');
})().catch(e=>{console.error(e);process.exit(1)});
'''
    result = subprocess.run([node, '-e', harness+fence+family+user+audit+checks],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
