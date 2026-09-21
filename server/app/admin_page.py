"""CMS 单页：运营数据看板 + LLM 分组管理。/cms 提供（管理员 Token 登录）。"""

CMS_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI 助学 CMS</title>
<style>
  :root { --primary:#1B2A4A; --accent:#15857A; --line:#E9E9E8; }
  * { box-sizing:border-box; margin:0; font-family: system-ui,"PingFang SC","Microsoft YaHei",sans-serif; }
  body { background:#F7F7F5; color:#37352F; }
  header { background:var(--primary); color:#fff; padding:14px 24px; display:flex; justify-content:space-between; align-items:center; }
  header b { font-size:17px; } header span { font-size:12px; opacity:.7; }
  main { max-width:1080px; margin:20px auto; padding:0 16px; }
  .cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; }
  .card { background:#fff; border-radius:10px; padding:14px 16px; border:1px solid var(--line); }
  .card .k { font-size:12px; color:#8C8A84; } .card .v { font-size:22px; font-weight:700; color:var(--primary); }
  .card .v.small { font-size:15px; }
  section { background:#fff; border:1px solid var(--line); border-radius:10px; padding:16px; margin-top:16px; }
  h2 { font-size:15px; margin-bottom:10px; color:var(--primary); }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th { text-align:left; color:#8C8A84; font-weight:500; padding:6px 8px; border-bottom:1px solid var(--line); }
  td { padding:6px 8px; border-bottom:1px solid #F2F2F0; }
  .tag { display:inline-block; padding:2px 8px; border-radius:10px; font-size:12px; }
  .beta-tag { background:#E8F0FE; color:#1A56A0; }
  .allow { background:#E8F5E9; color:#1B7D46; } .rewrite { background:#FEF9E7; color:#D4820A; }
  .reject { background:#FDEDEC; color:#C0392B; } .active { background:#E8F5E9; color:#1B7D46; }
  input, select, button { font-size:13px; padding:7px 10px; border-radius:8px; border:1px solid #D0D0D0; }
  button { background:var(--accent); color:#fff; border:none; cursor:pointer; }
  button.ghost { background:#fff; color:var(--accent); border:1px solid var(--accent); }
  .row { display:flex; gap:8px; flex-wrap:wrap; margin:6px 0; align-items:center; }
  #login { max-width:340px; margin:18vh auto; text-align:center; background:#fff; padding:28px; border-radius:12px; border:1px solid var(--line); }
  #login input { width:100%; margin:10px 0; }
  .err { color:#C0392B; font-size:12px; }
  .grid2 { display:grid; grid-template-columns:1fr 1fr; gap:16px; }
  @media (max-width:720px){ .grid2{grid-template-columns:1fr;} }
</style>
</head>
<body>
<div id="login">
  <h3>AI 助学 CMS</h3>
  <input id="user" placeholder="用户名">
  <input id="pass" type="password" placeholder="密码">
  <button style="width:100%" onclick="loginDb()">登录</button>
  <div class="hint" style="margin:8px 0">或使用环境变量 Token：</div>
  <input id="tok" type="password" placeholder="管理员 Token（env 后门）">
  <button class="ghost" style="width:100%" onclick="loginTok()">Token 登录</button>
  <div id="lerr" class="err"></div>
</div>

<div id="app" style="display:none">
<header><b>AI 助学 CMS · 运营管理</b><span id="grp"></span></header>
<main>
  <section>
    <h2>核心指标</h2>
    <div class="cards" id="cards"></div>
  </section>

  <div class="grid2">
    <section>
      <h2>围栏处置分布（policy 阶段）</h2>
      <div id="fenceDist"></div>
    </section>
    <section>
      <h2>最近围栏事件</h2>
      <div class="row"><select id="fdec"><option value="">全部</option><option value="allow">放行</option><option value="rewrite">改写</option><option value="reject">拦截</option></select>
      <button class="ghost" onclick="loadFence()">筛选</button></div>
      <table id="fenceTable"><thead><tr><th>时间</th><th>阶段</th><th>处置</th><th>类别</th></tr></thead><tbody></tbody></table>
    </section>
  </div>

  <section>
    <h2>家族列表</h2>
    <table id="famTable"><thead><tr><th>ID</th><th>监护人</th><th>学生</th><th>消息数</th><th>标签</th><th data-super-only>会员操作</th><th>创建</th></tr></thead><tbody></tbody></table>
  </section>

  <section data-super-only>
    <h2>LLM 分组管理 <span style="font-weight:400;font-size:12px;color:#8C8A84">（激活后新对话立即生效）</span></h2>
    <div id="groups"></div>
    <h2 style="margin-top:14px">新建分组</h2>
    <div class="row">
      <input id="g_name" placeholder="名称" style="width:110px">
      <select id="g_provider"><option value="openrouter">openrouter</option><option value="glm">glm</option><option value="deepseek">deepseek</option><option value="kimi">kimi</option></select>
      <input id="g_chat" placeholder="chat 模型" style="width:230px">
      <input id="g_fence" placeholder="fence 模型" style="width:230px">
      <input id="g_key" placeholder="API Key（可空=沿用环境）" style="width:220px" type="password">
      <input id="g_cap" placeholder="日上限(0=默认)" style="width:110px" type="number">
      <button onclick="addGroup()">创建</button>
    </div>
    <div style="font-size:12px;color:#8C8A84">路由优先级：家庭标签 &gt; 全局生效分组 &gt; 环境变量。给分组填标签后，在下方家族列表为家庭打上同名标签即可让该家庭使用本分组的 provider/model。</div>
    <div id="gerr" class="err"></div>
  </section>
  <section>
    <h2>操作日志</h2>
    <table id="logTable"><thead><tr><th>时间</th><th>管理员</th><th>操作</th><th>详情</th></tr></thead><tbody></tbody></table>
  </section>
</main>
</div>

<script>
const API = location.origin;
const $ = id => document.getElementById(id);
let TOK = sessionStorage.getItem('cms_tok') || '';
let ROLE = sessionStorage.getItem('cms_role') || 'ops';

function H() { return {'Content-Type':'application/json','Authorization':'Bearer '+TOK}; }
async function api(path, opts={}) {
  const r = await fetch(API+path, {...opts, headers:{...H(), ...(opts.headers||{})}});
  if (r.status === 403) { sessionStorage.removeItem('cms_tok'); location.reload(); throw new Error('reauth'); }
  const d = await r.json();
  if (!r.ok) throw new Error(d.detail || '请求失败');
  return d;
}
async function loginDb() {
  $('lerr').textContent = '';
  try {
    const r = await fetch(API + '/admin/login', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({username: $('user').value.trim(), password: $('pass').value})
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || '登录失败');
    TOK = d.token; ROLE = d.role; sessionStorage.setItem('cms_tok', TOK);
    sessionStorage.setItem('cms_role', ROLE);
    boot();
  } catch (e) { $('lerr').textContent = e.message; }
}
function loginTok() { TOK = $('tok').value.trim(); ROLE = 'super'; sessionStorage.setItem('cms_tok', TOK); sessionStorage.setItem('cms_role', 'super'); boot(); }

const DEC = {allow:'放行',rewrite:'改写',reject:'拦截'};
const CAT = {study:'学习',entertainment:'娱乐',sensitive:'敏感',other:'其他',unknown:'未知'};
const STAGE = {whitelist:'白名单',classifier:'分类',second_pass:'复核',policy:'处置'};

function boot() {
  api('/admin/overview').then(d => {
    $('login').style.display='none'; $('app').style.display='block';
    $('grp').textContent = (ROLE==='super'?'[超级管理员] ':'[运营·只读] ') + '当前分组: '+d.llm_group.name;
    // RBAC：ops 隐藏写操作区块
    document.querySelectorAll('[data-super-only]').forEach(el => {
      el.style.display = ROLE === 'super' ? '' : 'none';
    });
    const s=d.scale, a=d.activity, c=d.cost, f=d.fence;
    $('cards').innerHTML = [
      ['家庭', s.families],['监护人', s.guardians],['学生', s.students],['对话', s.conversations],['消息', s.messages],
      ['今日消息', a.messages_today],['昨日消息', a.messages_yesterday],
      ['成本(累计)', '¥'+c.total_cny],['成本(今日)', '¥'+c.today_cny],
    ].map(([k,v]) => `<div class="card"><div class="k">${k}</div><div class="v ${String(v).length>8?'small':''}">${v}</div></div>`).join('');
    const total = Object.values(f.by_decision).reduce((x,y)=>x+y,0) || 1;
    $('fenceDist').innerHTML = Object.entries(f.by_decision).map(([k,v]) =>
      `<div style="margin:6px 0"><span class="tag ${k}">${DEC[k]||k}</span> ${v} (${(v/total*100).toFixed(0)}%)</div>`).join('')
      + '<div style="margin-top:8px;font-size:12px;color:#8C8A84">类别: '+Object.entries(f.by_category).map(([k,v])=>(CAT[k]||k)+' '+v).join(' · ')+'</div>';
    loadFence(); loadFamilies(); if (ROLE === 'super') loadGroups(); loadLogs();
  }).catch(e => { if (e.message !== 'reauth') $('lerr').textContent = e.message; });
}

async function loadFence() {
  const dec = $('fdec').value;
  const d = await api('/admin/fence-events?size=12'+(dec?'&decision='+dec:''));
  $('fenceTable').querySelector('tbody').innerHTML = d.items.map(e =>
    `<tr><td>${(e.created_at||'').slice(5,16).replace('T',' ')}</td><td>${STAGE[e.stage]||e.stage}</td>
     <td><span class="tag ${e.decision}">${DEC[e.decision]||e.decision}</span></td>
     <td>${CAT[e.category]||e.category}</td></tr>`).join('');
}

async function loadFamilies() {
  const gd0 = await api('/admin/llm-groups');
  const tags = [...new Set(gd0.items.filter(g=>g.tag).map(g=>g.tag))];
  const d = await api('/admin/families?size=10');
  $('famTable').querySelector('tbody').innerHTML = d.items.map(f =>
    `<tr><td>${f.family_id}</td>
     <td>${f.guardians.map(g=>g.nickname||g.phone).join(', ')||'—'}</td>
     <td>${f.students.map(s=>s.nickname+(s.active?'':'(注销)')).join(', ')||'—'}</td>
     <td>${f.message_count}</td>
     <td>${f.tag?`<span class="tag beta-tag">${f.tag}</span>`:'—'} <select onchange="setTag(${f.family_id},this.value)">
        <option value="">清除</option>${tags.map(t=>`<option value="${t}" ${f.tag===t?'selected':''}>${t}</option>`).join('')}</select></td>
     <td data-super-only><button class="ghost" onclick="grantMembership(${f.family_id})">赠送</button> <button class="ghost" onclick="revokeMembership(${f.family_id})">扣除</button></td>
     <td>${(f.created_at||'').slice(0,10)}</td></tr>`).join('');
}

async function loadGroups() {
  const d = await api('/admin/llm-groups');
  $('groups').innerHTML = d.items.map(g => `
    <div class="row" style="border-bottom:1px solid #F2F2F0;padding:8px 0">
      <b>${g.name}</b> ${g.is_active?'<span class="tag active">生效中</span>':''}
      ${g.tag?`<span class="tag beta-tag">标签:${g.tag} (${g.tagged_families}家庭)</span>`:''}
      <span style="font-size:12px;color:#8C8A84">${g.provider} · chat:${g.chat_model} · fence:${g.fence_model} · key:${g.has_key?'已配':'沿用环境'} · 日上限:${g.daily_message_cap||'默认'}</span>
      ${g.is_active?'':'<button class="ghost" onclick="activate('+g.id+')">激活</button>'}
      <button class="ghost" onclick="delGroup(${g.id})">删除</button>
    </div>`).join('') || '<div style="color:#8C8A84;font-size:13px">暂无分组（使用环境变量配置）</div>';
}

async function activate(id) { await api('/admin/llm-groups/'+id+'/activate', {method:'PUT'}); loadGroups(); }
async function delGroup(id) { if(!confirm('确认删除该分组？')) return; await api('/admin/llm-groups/'+id, {method:'DELETE'}); loadGroups(); }

async function addGroup() {
  $('gerr').textContent='';
  try {
    await api('/admin/llm-groups', {method:'POST', body: JSON.stringify({
      name: $('g_name').value.trim(), provider: $('g_provider').value,
      chat_model: $('g_chat').value.trim(), fence_model: $('g_fence').value.trim(),
      api_key: $('g_key').value.trim(), daily_message_cap: parseInt($('g_cap').value||'0'),
      tag: $('g_tag').value.trim() || null,
    })});
    ['g_name','g_chat','g_fence','g_key','g_cap','g_tag'].forEach(i=>$(i).value='');
    loadGroups();
  } catch(e) { $('gerr').textContent = e.message; }
}

async function grantMembership(fid) {
  const days = prompt('赠送天数（1-3650）：', '30');
  if (!days) return;
  const note = prompt('备注（可空）：') || '';
  try {
    const d = await api('/admin/families/' + fid + '/grant', {method:'POST', body: JSON.stringify({days: parseInt(days), note})});
    alert('已赠送。当前剩余 ' + d.days_left + ' 天。');
    loadFamilies();
  } catch (e) { alert(e.message); }
}

async function revokeMembership(fid) {
  const days = prompt('扣除天数（1-3650）：', '30');
  if (!days) return;
  const note = prompt('备注（可空）：') || '';
  try {
    const d = await api('/admin/families/' + fid + '/revoke', {method:'POST', body: JSON.stringify({days: parseInt(days), note})});
    alert(d.active ? '已扣除。剩余 ' + d.days_left + ' 天。' : '已扣除至到期，该家庭订阅已失效。');
    loadFamilies();
  } catch (e) { alert(e.message); }
}

async function setTag(familyId, tag) {
  try {
    await api('/admin/families/' + familyId + '/tag', {method:'PUT', body: JSON.stringify({tag: tag || null})});
    loadFamilies();
  } catch(e) { alert(e.message); loadFamilies(); }
}

async function loadLogs() {
  try {
    const d = await api('/admin/logs?size=15');
    document.querySelector('#logTable tbody').innerHTML = d.items.map(l =>
      `<tr><td>${(l.created_at||'').slice(5,16).replace('T',' ')}</td><td>${l.admin}</td>
       <td>${l.action}</td><td style="font-size:12px;color:#666">${l.detail}</td></tr>`).join('');
  } catch (_) {}
}

if (TOK) boot();
</script>
</body>
</html>"""
