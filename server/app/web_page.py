"""Web 端（仅聊天）：单页静态实现，复用 /auth/student/login 与 /chat API。

范围冻结（提案第四轮）：仅聊天；审查/管理功能不进 web 端。
监护人核验锚定家长端 App/小程序，学生 web 端仍需绑定码激活。
"""

_WEB_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI 助学 · Web 学习助手</title>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/dompurify@3.1.6/dist/purify.min.js"></script>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css">
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/contrib/auto-render.min.js"></script>
<style>
  :root { --primary:#2F8B7D; --primary-dark:#21665C; --ink:#1E2A35; --muted:#71808E; --line:#E4EAEF; --surface:#fff; }
  * { box-sizing:border-box; margin:0; }
  body { font-family:system-ui,"PingFang SC","Microsoft YaHei",sans-serif; background:linear-gradient(180deg,#EDF9F5 0,#F7FAFC 34%,#F7FAFC 100%); color:var(--ink); height:100vh; display:flex; flex-direction:column; }
  header { background:rgba(255,255,255,.86); color:var(--ink); padding:16px 20px; font-size:18px; font-weight:750; border-bottom:1px solid rgba(228,234,239,.8); backdrop-filter:blur(12px); }
  header span { color:var(--primary); margin-right:8px; }
  main { flex:1; overflow-y:auto; padding:24px 16px; max-width:760px; width:100%; margin:0 auto; }
  .bubble { max-width:82%; padding:12px 15px; border-radius:18px; margin:8px 0; line-height:1.58; white-space:pre-wrap; word-break:break-word; box-shadow:0 5px 16px rgba(40,70,80,.06); }
  .user { background:var(--primary); color:#fff; margin-left:auto; border-bottom-right-radius:6px; }
  .assistant { background:var(--surface); border:1px solid var(--line); border-bottom-left-radius:6px; }
  footer { padding:12px 16px 16px; background:rgba(255,255,255,.9); border-top:1px solid var(--line); backdrop-filter:blur(12px); }
  .row { display:flex; gap:8px; max-width:760px; margin:0 auto; }
  input, button { font-size:15px; padding:12px 15px; border-radius:14px; border:1px solid var(--line); outline:none; }
  input { flex:1; background:#fff; box-shadow:0 4px 14px rgba(40,70,80,.04); }
  input:focus { border-color:var(--primary); box-shadow:0 0 0 3px rgba(47,139,125,.12); }
  button { background:var(--primary); color:#fff; border:none; cursor:pointer; font-weight:700; }
  button:hover { background:var(--primary-dark); }
  button:disabled { opacity:.5; }
  #gate { max-width:390px; margin:12vh auto 0; text-align:center; background:rgba(255,255,255,.88); padding:28px; border:1px solid var(--line); border-radius:24px; box-shadow:0 18px 50px rgba(35,75,80,.1); }
  #gate h3 { font-size:24px; margin-bottom:8px; }
  #drawer { position:fixed; inset:0 32% 0 0; background:rgba(255,255,255,.96); z-index:50; box-shadow:10px 0 30px rgba(20,45,55,.16); display:none; flex-direction:column; padding:18px; backdrop-filter:blur(14px); }
  #drawer .item { padding:12px 10px; border-radius:12px; cursor:pointer; font-size:14px; }
  #drawer .item:hover { background:#EDF8F5; }
  #drawer .item.active { background:#DFF3EE; color:var(--primary-dark); font-weight:700; }
  #drawer .item small { display:block; color:var(--muted); font-size:11px; margin-top:3px; }
  #drawer .new { width:100%; margin-bottom:10px; }
  #gate input { width:100%; text-align:center; letter-spacing:4px; font-size:21px; margin:14px 0; }
  #gate button { width:100%; }
  .hint { color:var(--muted); font-size:13px; margin-top:10px; }
  .err { color:#C0392B; font-size:13px; margin-top:8px; }
  .bubble.assistant p { margin:4px 0; }
  .bubble.assistant pre { background:#17232B; color:#D7E5E7; padding:12px; border-radius:12px; overflow-x:auto; font-size:13px; }
  .bubble.assistant code { background:#EFF5F4; padding:1px 5px; border-radius:5px; font-size:13px; }
  .bubble.assistant pre code { background:none; padding:0; }
  .bubble.assistant table { border-collapse:collapse; margin:8px 0; }
  .bubble.assistant th, .bubble.assistant td { border:1px solid var(--line); padding:5px 10px; font-size:13px; }
  @media (max-width:640px) { #drawer { inset:0 16% 0 0; } #gate { margin-top:8vh; } }
</style>
</head>
<body>
<header>
  <span style="cursor:pointer" id="menuBtn" onclick="toggleDrawer()">☰</span>
  AI 助学 · Web 学习助手
</header>
<div id="drawer">
  <button class="new" onclick="newChat()">＋ 新对话</button>
  <div class="item" onclick="showFavorites()">⭐ 我的收藏</div>
  <div id="sessList" style="overflow-y:auto; flex:1"></div>
</div>

<div id="gate">
  <h3>学生端激活</h3>
  <input id="code" placeholder="输入家长端 8 位绑定码" maxlength="8">
  <button onclick="bind()">绑定并开始学习</button>
  <div class="hint">绑定码由家长端 App 生成，10 分钟内有效</div>
  <div id="gateErr" class="err"></div>
</div>

<main id="chat" style="display:none"></main>
<footer id="inputRow" style="display:none">
  <div class="row">
    <input id="msg" placeholder="只能讨论学习内容哦" onkeydown="if(event.key==='Enter')send()">
    <button id="sendBtn" onclick="send()">发送</button>
  </div>
</footer>

<script>
const API = location.port === '8100' ? location.origin : (window.API_BASE || location.origin);
const $ = id => document.getElementById(id);
let conversationId = null, busy = false;

function token() { return localStorage.getItem('az_student_token'); }
function deviceId() {
  let d = localStorage.getItem('az_device_id');
  if (!d) { d = 'web-' + crypto.randomUUID(); localStorage.setItem('az_device_id', d); }
  return d;
}

async function api(path, body) {
  const resp = await fetch(API + path, {
    method: body ? 'POST' : 'GET',
    headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + (token() || '') },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.detail || '请求失败');
  return data;
}

async function bind() {
  $('gateErr').textContent = '';
  try {
    const data = await api('/auth/student/login', { bind_code: $('code').value.trim().toUpperCase(), device_id: deviceId(), nickname: '我的孩子' });
    localStorage.setItem('az_student_token', data.token);
    enterChat();
    startHeartbeat();
  } catch (e) { $('gateErr').textContent = e.message; }
}

function renderMd(el, text) {
  // marked 渲染 markdown；KaTeX auto-render 处理 $...$ 与 $$...$$ 公式
  // marked 不消毒 HTML：LLM 输出/学生输入可能携带 <script> 等载荷，必须过 DOMPurify
  el.innerHTML = DOMPurify.sanitize(marked.parse(text || '', {breaks: true}));
  if (window.renderMathInElement) {
    renderMathInElement(el, {delimiters: [
      {left: '$$', right: '$$', display: true},
      {left: '$', right: '$', display: false},
    ], throwOnError: false});
  }
}

function bubble(role, text, msgId) {
  const div = document.createElement('div');
  div.className = 'bubble ' + role;
  if (role === 'assistant') {
    renderMd(div, text);
    const fav = document.createElement('button');
    fav.textContent = '⭐ 收藏';
    fav.className = 'ghost';
    fav.style.cssText = 'margin-top:6px;font-size:11px;padding:3px 8px';
    fav.onclick = () => { if (msgId) toggleFavorite(msgId, fav); else fav.textContent = '生成中…'; };
    div.appendChild(document.createElement('br'));
    div.appendChild(fav);
  } else { div.textContent = text; }
  $('chat').appendChild(div);
  $('chat').scrollTop = $('chat').scrollHeight;
}

async function send() {
  const content = $('msg').value.trim();
  if (!content || busy) return;
  $('msg').value = ''; busy = true; $('sendBtn').disabled = true;
  bubble('user', content);
  try {
    const reply = await api('/chat', { conversation_id: conversationId, content });
    conversationId = reply.conversation_id ?? conversationId;
    bubble('assistant', reply.content, reply.id);
  } catch (e) { bubble('assistant', '⚠️ ' + e.message); }
  finally { busy = false; $('sendBtn').disabled = false; loadSessions(); }
}

let sessions = [];

async function loadSessions() {
  try {
    sessions = await api('/chat/sessions');
    const list = $('sessList');
    list.innerHTML = sessions.map(s => `
      <div class="item ${s.conversation_id === conversationId ? 'active' : ''}" onclick="openSession(${s.conversation_id})">
        ${s.title}
        <small>${s.message_count} 条 · ${(s.last_time || '').replace('T', ' ').slice(0, 16)}</small>
      </div>`).join('');
  } catch (_) {}
}

function toggleDrawer() {
  const d = $('drawer');
  d.style.display = d.style.display === 'flex' ? 'none' : 'flex';
  if (d.style.display === 'flex') loadSessions();
}

let favView = false;

async function showFavorites() {
  $('drawer').style.display = 'none';
  favView = true;
  $('chat').innerHTML = '<div class="bubble assistant">⭐ 我的收藏（加载中…）</div>';
  try {
    const favs = await api('/chat/favorites');
    $('chat').innerHTML = '';
    if (!favs.length) { bubble('assistant', '还没有收藏。长按/点击消息下的 ⭐ 即可收藏。'); return; }
    for (const f of favs) {
      const div = document.createElement('div');
      div.className = 'bubble assistant';
      renderMd(div, f.content);
      const del = document.createElement('button');
      del.textContent = '取消收藏';
      del.className = 'ghost';
      del.style.cssText = 'margin-top:6px;font-size:12px;padding:4px 10px;background:#fff;color:#C0392B;border:1px solid #C0392B';
      del.onclick = async () => {
        await fetch(API + '/chat/favorites/' + f.id, {method: 'DELETE', headers: {'Authorization': 'Bearer ' + token()}});
        showFavorites();
      };
      div.appendChild(del);
      $('chat').appendChild(div);
    }
  } catch (e) { bubble('assistant', '⚠️ ' + e.message); }
}

async function toggleFavorite(msgId, btn) {
  try {
    const r = await api('/chat/favorites', {message_id: msgId});
    btn.textContent = '⭐ 已收藏';
    btn.disabled = true;
  } catch (e) { alert(e.message); }
}

async function openSession(cid) {
  $('drawer').style.display = 'none';
  try {
    const msgs = await api('/chat/conversations?conversation_id=' + cid);
    $('chat').innerHTML = '';
    conversationId = cid;
    for (const m of msgs) bubble(m.role, m.content, m.id);
  } catch (e) { bubble('assistant', '⚠️ ' + e.message); }
}

function newChat() {
  $('drawer').style.display = 'none';
  $('chat').innerHTML = '';
  conversationId = null;
  bubble('assistant', '你好！今天想学什么？可以问我作业和知识点。');
}

async function enterChat() {
  $('gate').style.display = 'none';
  $('chat').style.display = 'block';
  $('inputRow').style.display = 'block';
  try {
    const latest = await api('/chat/latest');
    conversationId = latest.conversation_id;
    for (const m of latest.messages) bubble(m.role, m.content, m.id);
  } catch (_) { /* 恢复失败按新对话处理 */ }
  if (!$('chat').children.length) bubble('assistant', '你好！今天想学什么？可以问我作业和知识点。');
  loadSessions();
}

// 活跃心跳：每 60s 上报（与 App 端时长统计口径一致）
let hbTimer = null;
function startHeartbeat() {
  if (hbTimer) clearInterval(hbTimer);
  hbTimer = setInterval(() => {
    if (!token()) return;
    fetch(API + '/chat/heartbeat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token() },
      body: JSON.stringify({ seconds: 60 })
    }).catch(() => {});
  }, 60000);
}

if (token()) { enterChat(); startHeartbeat(); }
</script>
</body>
</html>"""

WEB_PAGE_HTML = _WEB_PAGE
