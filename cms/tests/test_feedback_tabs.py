"""Execute the actual queue UI code against a small DOM/API fake."""
import shutil
import subprocess
from pathlib import Path

import pytest


def test_queue_switching_pagination_and_processed_actions():
    node = shutil.which('node')
    if not node:
        pytest.skip('JavaScript queue check needs Node.js')
    html = (Path(__file__).resolve().parents[1] / 'index.html').read_text()
    script = html[html.index('const feedbackQueue ='):html.index('function replyReport(')]
    harness = r'''
const assert=require('node:assert/strict');
const elements=new Map();
const $=id=>{
  if(!elements.has(id)) elements.set(id,{attributes:{},textContent:'',innerHTML:'',
    setAttribute(k,v){this.attributes[k]=v;},querySelector(){return this;}});
  return elements.get(id);
};
const esc=value=>String(value??'');
const attr=encodeURIComponent;
const textPreview=value=>esc(value);
let requests=[];
let pending=true;
const api=async(url,options)=>{
  requests.push(url);
  if(options) {pending=false;return {};}
  const params=new URL('http://localhost'+url).searchParams;
  const handled=params.get('status')==='handled';
  return {total:handled?31:pending?1:0,items:handled?[
    {id:2,status:'reviewed',reply:'已核实',content:'已处理内容'},
    {id:3,status:'dismissed',reply:'',content:'驳回内容'}
  ]:pending?[{id:1,status:'open',content:'待处理内容'}]:[]};
};
'''
    checks = r'''
(async()=>{
  await loadFeedback();
  assert(requests.at(-1).includes('status=open'));
  assert($('feedbackTable').innerHTML.includes('标记已复核'));
  await closeFeedback(1);
  assert($('feedbackTable').innerHTML.includes('暂无待处理反馈'));
  await switchQueue('feedback','handled');
  assert(requests.at(-1).includes('status=handled'));
  assert(!$('feedbackTable').innerHTML.includes('标记已复核'));
  assert($('feedbackTable').innerHTML.includes('已驳回'));
  assert.equal($('feedbackHandledTab').attributes['aria-selected'],'true');
  assert.equal($('feedbackOpenTab').attributes['aria-selected'],'false');
  assert.equal($('feedbackPanel').attributes['aria-labelledby'],'feedbackHandledTab');
  assert.equal($('feedbackNext').disabled,false);
  await loadFeedback(2);
  assert(requests.at(-1).includes('page=2'));
  await switchQueue('report','handled');
  assert(requests.at(-1).includes('kind=message_report&status=handled'));
  assert($('reportTable').innerHTML.includes('已核实'));
  assert($('reportTable').innerHTML.includes('修改回复'));
  assert.equal(reportQueue.page,1);
  assert.equal(feedbackQueue.page,2);
  await switchQueue('feedback','open');
  assert.equal(feedbackQueue.page,1);
  assert.equal($('feedbackPrev').disabled,true);
})().catch(error=>{console.error(error);process.exit(1);});
'''
    subprocess.run([node,'-e',harness+script+checks],check=True,capture_output=True,text=True)
