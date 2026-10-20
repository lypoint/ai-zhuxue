"""Exercise the shipped inline editors, validation and escaped long text."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_inline_editors_preserve_drafts_on_error_and_submit_valid_values():
    node = shutil.which('node')
    if not node:
        pytest.skip('JavaScript editor checks need Node.js')
    html = (Path(__file__).resolve().parents[1] / 'index.html').read_text()
    preview = html[html.index('function textPreview('):html.index('function H(')]
    report = html[html.index('function replyReport('):html.index('async function loadUsers(')]
    teacher = html[html.index('let editingTeacherProfile='):html.index('async function loadPricing(')]
    harness = r'''
const assert=require('node:assert/strict');
const elements=new Map();
const $=id=>{
  if(!elements.has(id)) elements.set(id,{hidden:true,value:'',textContent:'',
    scrollIntoView(){},focus(){this.focused=true;}});
  return elements.get(id);
};
const esc=value=>String(value??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const REPORTS=[{id:31,content:'<script>消息原文</script>'}];
const GROUPS=[{id:2,name:'模型分组',teacher_name:'老师',teacher_enabled:true,
  teacher_sort_order:5,post_trial_daily_free_count:3}];
let editingReport=null,requests=[],fail=false,reportsLoaded=0,groupsLoaded=0;
const api=async(path,options)=>{
  requests.push({path,body:JSON.parse(options.body)});
  if(fail)throw new Error('保存失败');
};
const loadReports=async()=>{reportsLoaded++;};
const loadGroups=async()=>{groupsLoaded++;};
const loadLogs=async()=>{};
'''
    checks = r'''
(async()=>{
  assert.equal(textPreview(null),'—');
  assert.equal(textPreview('<b>'), '&lt;b&gt;');
  const long='<script>'+ '中'.repeat(150) + '</script>';
  const rendered=textPreview(long);
  assert(rendered.includes('<details'));
  assert(rendered.includes(esc(long)));
  assert(!rendered.includes('<script>'));
  replyReport(31,'原回复');
  assert.equal($('reportContext').textContent,REPORTS[0].content);
  assert.equal($('reportReply').value,'原回复');
  assert.equal($('reportReply').focused,true);
  $('reportReply').value='   ';
  await saveReportReply();
  assert.equal(requests.length,0);
  $('reportReply').value='中'.repeat(1001);
  await saveReportReply();
  assert.equal(requests.length,0);
  $('reportReply').value=' 已核实 ';
  fail=true;
  await saveReportReply();
  assert.equal($('reportEditor').hidden,false);
  assert.equal($('reportReply').value,' 已核实 ');
  assert.equal($('reportReplyError').textContent,'保存失败');
  assert.equal($('saveReportReplyButton').disabled,false);
  fail=false;
  await saveReportReply();
  assert.deepEqual(requests.at(-1),{path:'/admin/fence-feedback/31',body:{status:'reviewed',reply:'已核实'}});
  assert.equal($('reportEditor').hidden,true);
  assert.equal(reportsLoaded,1);
  editTeacher(2);
  assert.equal($('tp_name').value,'老师');
  assert.equal($('tp_free').value,3);
  assert.equal($('tp_sort').value,5);
  $('tp_free').value='-1';
  const count=requests.length;
  await saveTeacherProfile();
  assert.equal(requests.length,count);
  $('tp_free').value='2.5';
  await saveTeacherProfile();
  assert.equal(requests.length,count);
  $('tp_free').value='0';$('tp_sort').value='-2';$('tp_name').value=' 新老师 ';
  fail=true;
  await saveTeacherProfile();
  assert.equal($('teacherProfile').hidden,false);
  assert.equal($('tp_error').textContent,'保存失败');
  fail=false;
  await saveTeacherProfile();
  assert.deepEqual(requests.at(-1),{path:'/admin/llm-groups/2/teacher-profile',body:{teacher_name:'新老师',teacher_enabled:true,teacher_sort_order:-2,post_trial_daily_free_count:0}});
  assert.equal($('teacherProfile').hidden,true);
  assert.equal(groupsLoaded,1);
})().catch(error=>{console.error(error);process.exit(1);});
'''
    subprocess.run([node, '-e', harness+preview+report+teacher+checks], check=True,
                   capture_output=True, text=True)
