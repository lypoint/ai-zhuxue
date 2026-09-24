# API 参考

Base URL：本地开发 `http://localhost:8100`；Android 模拟器内 `http://10.0.2.2:8100`。
交互式文档：服务启动后访问 `/docs`（Swagger UI）与 `/redoc`。

**鉴权**：除 `/health` 与 `/auth/*` 外均需 `Authorization: Bearer <JWT>`。JWT 区分 `role`（guardian/student），角色不匹配返回 403。

**通用错误**：`{"detail": "<中文原因>"}`（FastAPI 统一格式）。

---

## 系统

### GET /health
健康检查。返回 `{"status","env","fence_mode","llm_provider"}`。无鉴权。

---

## 认证 `/auth`

### POST /auth/guardian/register — 监护人注册（含三要素核验）
```json
{
  "phone": "13800001111",        // 11 位大陆手机号
  "sms_code": "123456",          // dev 固定码；生产接短信服务商
  "nickname": "爸爸",
  "real_name": "张三",            // 三要素之一
  "id_number": "11010120100307857X"  // 15/18 位
}
```
→ `200 {"token": "<jwt>", "role": "guardian"}`
错误：`400 guardian verify failed: <detail>`（三要素格式/一致性不通过）。
副作用：新监护人自动创建 Family + FamilySettings（审查 default-on，每日上限 200）。

### POST /auth/student/login — 学生端登录（凭绑定码）
```json
{"bind_code": "6E629AC5", "device_id": "emulator-5554-01", "nickname": "小明"}
```
→ `200 {"token","role":"student"}`。同一 device_id 重复登录复用学生身份并重新归属家庭。
错误：`400 bind code invalid or expired`（码不存在/已使用/超 10 分钟）。

---

## 绑定 `/bind`（guardian）

### POST /bind/code — 生成绑定码
→ `200 {"code": "A3F9C2B1", "expires_at": "..."}`
8 位大写十六进制，10 分钟有效，一次性。二维码内容即该 code。

### GET /bind/codes — 当前有效码列表
→ `200 [{"code","expires_at"}]`（未使用且未过期）。

---

## 学生聊天 `/chat`（student）

### POST /chat — 发送消息（围栏内）
```json
{"conversation_id": 3,     // 可空：空则新建对话
 "content": "帮我讲解一元一次方程"}   // 1..4000 字符
```
→ `200 MessageOut`（**assistant 回复**）：
```json
{"id":12,"role":"assistant","content":"…","fence_action":"allow|rewrite|reject",
 "tokens_in":0,"tokens_out":0,"created_at":"…"}
```
错误码：
| 码 | 含义 |
|---|---|
| 423 | 22:00–6:00 时段禁用（未成年人模式） |
| 429 | 当日消息上限用完（家长可配置，10–1000） |
| 503 | LLM 不可用（未配 Key/上游故障）——围栏已扣留内容为 reject 时不经过此错误 |
| 404 | conversation 不存在或不属于该学生 |

**输出格式**：系统提示要求模型以 Markdown 输出（标题/列表/表格/代码块），数学公式用 LaTeX（行内 `$...$`、独立 `$$...$$`）；客户端（Flutter gpt_markdown / Web KaTeX）负责渲染。

**行为要点**：`reject` 的回复内容为固定引导话术（含求助家长/老师提示），不经过 LLM；`rewrite` 会在系统提示中注入引导语把话题带回学习。

### GET /chat/conversations?conversation_id=N — 拉取某对话全部消息
→ `200 [MessageOut...]`（学生端重进 App 后恢复上下文）。

---

## 家长端 `/parent`（guardian，全部只读）

### GET /parent/family — 家庭总览
```json
{"guardian": {"id","phone","nickname"},
 "students": [{"id","nickname","grade_band"}],
 "settings": {"daily_message_cap": 200, "review_enabled": true}}
```

### GET /parent/students/{student_id}/conversations — 该学生全部对话
→ `200 [ConversationOut...]`（按 id 倒序）。学生不属于本家庭 → 404。

### GET /parent/conversations/{id}/messages — 逐条消息
→ `200 [MessageOut...]`（含每条的 `fence_action`）。

### GET /parent/conversations/{id}/fence-events — 围栏判定流水
→ `200 [FenceEventOut...]`：
```json
{"id":1,"stage":"classifier|whitelist|second_pass|policy",
 "decision":"allow|rewrite|reject","category":"study|entertainment|sensitive|other",
 "confidence":0.7,"created_at":"…"}
```

### GET /parent/students/{student_id}/export — 审查数据全量导出（条例 34 复制权）
→ `200` JSON：`{student, exported_at, conversations:[{id,title,messages,fence_events}]}`。只读，跨家庭 404。

### DELETE /parent/students/{student_id} — 学生注销（个保法删除权）
- 默认：**匿名注销**——学生停用（旧 token 立即失效）、昵称/设备号脱敏，对话内容保留（删除范围与审查留存的边界待法务意见问题 1）；
- `?purge=true`：连同对话、消息、围栏流水硬删除。
→ `200 {"ok": true, "mode": "anonymized"|"purged"}`

### GET /parent/students/{student_id}/usage — 用量与成本估算
→ `200 {total:{tokens_in,tokens_out,cost}, today:{…}, unit:"CNY, 按厂商现价估算"}`（价格见 `llm.py PRICE_PER_MTOK`）。

### POST /chat/heartbeat — 活跃心跳（student，P1 时长管控数据源）
`{"seconds": 60}`（1–120，学生端聊天页每 60s 上报）→ `{"ok": true, "day", "total_seconds"}`。
防刷：单次 ≤120；当日累计 ≤6 小时（超出静默丢弃）。服务端按时长上限（FamilySettings.daily_minutes_cap，0=不限）在 `/chat` 返回 429 文案「今天的学习时间用完了」。

### GET /chat/sessions — 学生端会话列表（student，Codex 风格抽屉数据源）
→ `200 [{conversation_id, title, message_count, pinned, last_time}]`（置顶优先，其余按最近更新倒序，最多 100 条）。

### PUT /chat/sessions/{id}/pin — 置顶/取消置顶（student）
`{"pinned": true|false}` → `200 {"ok": true, "pinned"}`。仅限本人会话。

### PATCH /chat/sessions/{id} — 重命名会话（student）
`{"title": "新标题"}`（1–100 字符）→ `200 {"ok": true, "title"}`。仅限本人会话，跨家庭/他人 404。

### DELETE /chat/sessions/{id} — 删除会话（student）
连同消息与围栏流水硬删除，家长端审查视图同步消失（学生删除权与审查留存的张力见 compliance-design 问题 1；家长导出可先行留存）。跨家庭/他人 404。

### GET /chat/latest — 学生端恢复最近对话（student）
→ `200 {conversation_id: int|null, messages: [MessageOut...]}`

### PUT /parent/settings — 更新管控设置（P1：含自定义休息时段）
```json
{"daily_message_cap": 100, "review_enabled": true,
 "quiet_enabled": true, "quiet_start": 22, "quiet_end": 6,
 "notify_fence": true}
```
→ `200 {"ok": true}`。`quiet_*` 为**家长自定义禁用时段**（覆盖全局 22–6；`quiet_enabled=false` 整体关闭）。学生端触发时 423 文案带实际时段。`daily_minutes_cap`（0–480）为每日真实使用时长上限（心跳累计，0=不限）。`notify_fence=false` 关闭围栏改写类通知（**security 安全告警不可关闭**）。

### PUT /parent/students/{id}/nickname — 修改孩子昵称（家长）
`{"nickname": "新昵称"}` → `200 {"ok": true}`。绑定后改名，跨家庭 404。

### GET /chat/my-stats — 学生自己的学习统计（student）
→ `200 {"today": {questions, blocked, minutes}, "week": {questions, blocked, minutes, active_days}, "favorites": n}`
口径与家长端摘要一致（只统计学生消息、真实时长优先），学生可在端内感知自己的使用情况。

### GET /parent/students/{id}/search — 审查内容搜索（家长）
`?q=`（≥2 字符，否则 422）→ 标题或消息全文匹配，倒序 ≤50 条：
`[{conversation_id, title, message_id, role, snippet, fence_action, created_at}]`。跨家庭 404。

### 生成侧内容安全复核（服务端行为，非端点）
assistant 生成完成后全文再过一次分类器（stage=`output_check`）：sensitive → 落库替换为拒绝话术 + security 告警。诚实声明：**流式已送达终端的部分无法撤回**，复核保障的是家长端审查视图与存储的一致性，并为评测统计（生成合格率）提供数据。

### GET /parent/students/{id}/summary — 学习摘要（P1，家长首页）
→ `200 {"today": {questions, blocked, guided, study, minutes}, "week": {…, active_days}}`
全部指标只统计学生消息；`minutes` 优先取端侧心跳累计的**真实使用时长**，无心跳数据时回退为消息跨度估算。

---

## Web 端

### GET /web — Web 学习助手（仅聊天，无鉴权，HTML）
单页实现：绑定码激活（复用 `/auth/student/login`）→ 聊天（复用 `POST /chat`）→ 重进恢复（复用 `/chat/latest`）。**范围冻结**：审查/管理功能不进 web 端。

## 限流

`/auth/*` 每分钟 20 次、`/chat*` 每分钟 30 次（按登录主体或 IP，滑动窗口），超限 429。单进程内存实现；`ENV=test` 时豁免（专项测试直接调用 `app.ratelimit.limiter`）。

## 数据模型约定

- 时间均为 UTC ISO8601（SQLite 落库为 naive UTC）。
- `fence_action` 为 null 表示该消息未经过围栏（当前仅 assistant 首条引导/系统消息）。
- 无删除/编辑接口（家长审查不可篡改）；M1 起补充账号注销与数据删除（个保法要求，见 compliance-design.md）。


---

## CMS `/admin`（RBAC 管理员）

鉴权（2026-09-19 RBAC 改造）：
1. **库内管理员**：`POST /admin/login {username, password}` → `{token, role, name}`（session_token 存库比对）；角色 `super`（全部权限）/ `ops`（只读运营，写操作 403）；
2. **环境变量后门**：Header `Authorization: Bearer <ADMIN_TOKENS 之一>` = super（部署引导期）。

管理后台前端已拆分为独立服务（`../cms`，默认端口 8101）：单页托管于 `GET /`，账号密码登录或 Token 登录，ops 角色隐藏写操作入口；跨端口调用本组 `/admin` API。页面后端地址优先级：`?api=` 参数 > `CMS_API_BASE` 环境变量注入 > 同源兜底。敏感操作留痕 `GET /admin/logs`（仅 super）。

### GET /admin/overview — 核心运营面板
```json
{"scale": {"families","guardians","students","conversations","messages"},
 "activity": {"messages_today","messages_yesterday"},
 "fence": {"by_decision": {...}, "by_category": {...}},
 "cost": {"total_cny","today_cny"},
 "llm_group": {"name","provider","chat_model","fence_model"}}
```
成本口径：优先上游真实 cost（openrouter accounting 落库 UsageLog.cost），缺省按已核实厂商现价估算。

### GET /admin/families?page=&size= — 家族列表
监护人手机号脱敏（139****0000）；含学生列表与消息量。

### GET /admin/fence-events?decision=&page= — 围栏流水审计

### GET /admin/llm-groups — 分组列表（含当前生效分组）
### POST /admin/llm-groups — 创建分组 `{name, provider, chat_model, fence_model, api_key?, daily_message_cap?, note?}`（super）
### PUT /admin/llm-groups/{id}/activate — 激活（全局唯一生效；**新对话立即生效，无需重启**）（super）

### 会员赠送/扣除（2026-09-19，super 专属）
- `POST /admin/families/{id}/grant {days: 1–3650, note?}` — 赠送会员天数（自当前到期日起顺延，试用中则自今起）；
- `POST /admin/families/{id}/revoke {days: 1–3650, note?}` — 扣除会员天数（到期时间提前 N 天，最早扣到当前时间即立即到期）；
- `GET /admin/logs?page=&size=` — 操作日志（admin/action/detail，倒序；赠送/扣除/分组变更全留痕）。
非 super 角色调用一律 403。

### 家庭标签路由（2026-09-19）

分组可绑定**标签**（`tag`，唯一），家庭可持有一个标签。聊天/围栏调用的模型按家庭路由，优先级：

1. **家庭标签**：`families.tag` 对应 `llm_groups.tag` 相同的分组（跨 provider/model 差异化，如 beta 家庭走 glm、正式家庭走 deepseek）；
2. **全局激活**分组（is_active）；
3. **环境变量**。

端点：
- `POST /admin/llm-groups` 增加 `tag` 字段（唯一，重复绑定 400）；
- `GET /admin/llm-groups` 返回 `tag` 与 `tagged_families` 数；
- `PUT /admin/families/{id}/tag` `{tag: "beta"|null}` 打/清标签（标签须已绑定分组，否则 400）；
- `GET /admin/families/{id}/routing` 查看该家庭实际路由结果（`routed_by: tag:xxx|active|env`）。
### DELETE /admin/llm-groups/{id} — 删除（激活中的删除后回退环境变量配置）

**运行时优先级**：`llm_groups.is_active` 分组 > 环境变量（`LLM_PROVIDER` 等）。分组内 api_key 为空时沿用环境变量 Key。


---

## 订阅 `/parent/subscription`（P0 商业闭环）

注册即开 30 天免费试用；到期后学生端 `/chat` 返回 **402**（detail：免费使用期已结束，请家长在家长端续费）。

### GET /parent/subscription — 订阅状态
```json
{"plan":"free_trial|monthly","active":true,"expires_at":"…","days_left":29,
 "price_cny":66.0,"provider":"mock","paid_amount":0.0}
```

### POST /parent/subscription/pay — 续费（骨架期 mock）
从当前到期时间（或现在，取较晚者）顺延 30 天，累计实付。生产替换为微信/支付宝支付回调（需商户资质，外部依赖）。

## 通知 `/parent/notifications`（P0 安全闭环）

| type | 触发 | 说明 |
|------|------|------|
| `security` | 敏感内容拦截（sensitive） | **安全告警**，标红展示；建议家长关注沟通 |
| `fence` | 非学习拦截/引导改写 | 改写类同类型同日去重（防骚扰） |
| `quota` | 每日消息上限触顶 | 同日去重 |
| `system` | 注册欢迎等 | — |

- `GET /parent/notifications?unread_only=&page=&size=` → `{unread, total, items:[{id,type,title,body,conversation_id,is_read,created_at}]}`
- `POST /parent/notifications/read-all` → 全部已读
- 推送通道（App 离线推送/微信服务号）为外部依赖，当前为 App 内通知中心 + 未读角标。


---

## 学段与收藏（P2：分龄差异化 + 学习沉淀）

### PUT /parent/students/{id}/grade-band — 设置孩子学段（家长）
`{"grade_band": "8-12|12-16|16-18"}` → 影响分龄内容、系统提示讲解风格与围栏分龄预期。非法值 422。

### 学生端收藏（student）
- `POST /chat/favorites` `{message_id}` — 收藏（快照内容，幂等，仅限本人会话消息）；
- `GET /chat/favorites` — 我的收藏（倒序，≤200）；
- `DELETE /chat/favorites/{id}` — 取消收藏；
- 家长可见：`GET /parent/students/{id}/favorites`（了解孩子兴趣点，只读）。
