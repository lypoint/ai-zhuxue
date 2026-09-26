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
{"bind_code": "6E629AC5", "installation_id": "uuid-from-keychain", "nickname": "小明"}
```
→ `200 {"token","role":"student", "student_id", "student_device_id", "replaced_device_count"}`。installation_id 持久化用于找回同一孩子；重新绑定时新设备生效，旧设备全部吊销。旧 device_id 参数仅在迁移期兼容，不再作为学生业务身份。
错误：`400 bind code invalid or expired`（码不存在/已使用/超 10 分钟）。

---

## 绑定 `/bind`（guardian）

### POST /bind/code — 生成绑定码
→ `200 {"code": "A3F9C2B1", "expires_at": "..."}`
8 位大写十六进制，10 分钟有效，一次性。二维码内容即该 code。

### GET /bind/codes — 当前有效码列表
→ `200 [{"code","expires_at"}]`（未使用且未过期）。

### DELETE /bind/codes/{code} — 作废绑定码
仅限所属家庭的监护人；未使用码作废后不可再次登录，重复或跨家庭返回 404。

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

## 家长端 `/parent`（guardian；审查内容只读，成绩/评估/管控使用独立写接口）

### GET /parent/family — 家庭总览
```json
{"guardian": {"id","phone","nickname"},
 "students": [{"id","nickname","grade_band"}],
 "settings": {"daily_message_cap": 200, "review_enabled": true}}
```

### GET /parent/students/{student_id}/conversations — 该学生全部对话
→ `200 [ConversationOut...]`（按 id 倒序，含老师姓名/头像快照和 `student_deleted` 标记）。
支持 `status=all|active|deleted` 筛选；学生不属于本家庭 → 404。

### GET /parent/conversations/{id}/messages — 逐条消息
→ `200 [MessageOut...]`（含每条的 `fence_action` 以及会话老师快照 `teacher_id`、`teacher_name`、`teacher_avatar_url`）。

### POST /parent/conversations/{id}/feedback — 提交围栏误判
`{"message_id": 12, "event_id": 18, "note": "可选说明"}` → `{ "ok": true, "feedback_id": 3, "status": "open" }`。仅限本家庭；反馈进入 CMS 失效样本队列，重复开放反馈幂等返回。

### GET /parent/conversations/{id}/fence-events — 围栏判定流水
→ `200 [FenceEventOut...]`：
```json
{"id":1,"stage":"classifier|whitelist|second_pass|policy",
 "decision":"allow|rewrite|reject","category":"study|entertainment|sensitive|other",
 "confidence":0.7,"intent":"study|harm|safety_education",
 "safety_education":false,"created_at":"…"}
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
学生侧软删除：学生端隐藏，家长审查、搜索、导出仍可见并标记 `student_deleted=true`，删除不回滚次数、时长和成本。跨家庭/他人 404；家庭注销/法务删除才触发正式数据删除。

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

`/auth/*` 每 IP 每分钟 20 次、`/chat*` 每 IP 每分钟 300 次且每学生每分钟 30 次、`/admin/login` 每 IP 每分钟 10 次、其余 `/admin/*` 每 IP 每分钟 120 次。数据库固定分钟计数在多进程间共享，超限 429，`ENV=test` 时豁免。反向代理部署须正确配置可信代理地址，使应用获得真实客户端 IP。

## 数据模型约定

- 时间均为 UTC ISO8601（SQLite 落库为 naive UTC）。
- `fence_action` 为 null 表示该消息未经过围栏（当前仅 assistant 首条引导/系统消息）。
- 家长审查接口不提供改写历史消息的能力；学生会话删除为软删除，家庭注销/法务流程才触发正式数据删除（见 compliance-design.md）。


---

## CMS `/admin`（RBAC 管理员）

鉴权（2026-09-19 RBAC 改造）：
1. **库内管理员**：`POST /admin/login {username, password}` → `{token, role, name}`（session_token 存库比对）；角色 `super`（全部权限）/ `admin`（普通管理员）/ `support`（客服最小权限）；迁移期 `ops` 按 `admin` 兼容。
2. **环境变量后门**：Header `Authorization: Bearer <ADMIN_TOKENS 之一>` = super（部署引导期）。

管理后台前端已拆分为独立服务（`../cms`，默认端口 8101）：单页托管于 `GET /`，账号密码登录或 Token 登录，admin 和 support 角色按权限隐藏操作入口；跨端口调用本组 `/admin` API。页面后端地址由 `CMS_API_BASE` 环境变量注入，未配置时同源兜底。敏感操作留痕 `GET /admin/logs`（super 可查看全部，admin/support 仅查看本人记录）。

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

### POST /admin/families/{id}/bind-code — 客服协助绑定
客服、管理员和超级管理员可生成一次性新孩子码或重新绑定码；仅返回码、有效期和目标孩子，不返回聊天内容。

### DELETE /admin/families/{id}/bind-code/{code} — 作废绑定码
admin/super/support 均可作废该家庭尚未使用的绑定码，并写入操作日志。

### GET /admin/fence-events?decision=&page= — 围栏流水审计

### GET/PATCH /admin/fence-feedback — 误判反馈与失效样本
`GET` 返回待复核反馈；客服角色的消息内容脱敏。`PATCH /admin/fence-feedback/{id}` 使用 `status=open|reviewed|dismissed`，仅 super/admin 可修改并写入日志。

### GET /admin/llm-groups — 分组列表（含当前生效分组）
### POST /admin/llm-groups — 创建分组 `{name, provider, chat_model, fence_model, api_key?, daily_message_cap?, note?, teacher_name?, teacher_avatar_url?, teacher_enabled?, teacher_sort_order?, post_trial_free_enabled?}`（super）
### PUT /admin/llm-groups/{id}/activate — 激活（全局唯一生效；**新对话立即生效，无需重启**）（super）

### 会员赠送/扣除（2026-09-19，super/admin）
- `POST /admin/families/{id}/grant {days: 1–3650, note?}` — 赠送会员天数（自当前到期日起顺延，试用中则自今起）；
- `POST /admin/families/{id}/revoke {days: 1–3650, note?}` — 扣除会员天数（到期时间提前 N 天，最早扣到当前时间即立即到期）；
- `GET /admin/logs?page=&size=` — 操作日志（admin/action/detail，倒序；赠送/扣除/分组变更全留痕）。
admin 可执行赠送/扣除并由 CMS 二次确认；support 不能直接生效，价格、账号和分组创建/激活/删除仍仅 super。

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

### GET /admin/users — CMS 账号列表
仅 super；返回账号名、角色和备注，不返回密码哈希。

### GET /admin/assessment-audits — 评估审计索引
仅 super/admin；返回评估类型、评估 ID、操作者、动作和时间，不返回评估正文或孩子消息。

**运行时优先级**：`llm_groups.is_active` 分组 > 环境变量（`LLM_PROVIDER` 等）。分组内 api_key 为空时沿用环境变量 Key。


---

## 订阅 `/parent/subscription`（P0 商业闭环）

注册即开 30 天免费试用；到期后仅 CMS 开启“试用到期后免费”的老师可消耗全局每日免费次数，其他老师返回 **402**，次数耗尽返回 **429**。

### GET /parent/subscription — 订阅状态
```json
{"plan":"free_trial|monthly","active":true,"expires_at":"…","days_left":29,
 "price_cny":66.0,"provider":"mock","paid_amount":0.0,
 "base_monthly_price_cents":6600,"additional_seat_price_cents":3300}
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


---

## 家庭扩展、成绩与评估 API

完整业务规则见 [feature-spec-family-growth-and-learning.md](feature-spec-family-growth-and-learning.md)。以下端点已纳入当前 API。

### 家庭与设备

- `GET /parent/students`：孩子列表、名额占用、当前设备摘要。
- `POST /parent/students`：创建孩子；无可用名额时返回 `409 seat_required`。
- `POST /parent/students/{id}/rebind-code`：生成指定孩子的重新绑定二维码，旧码失效。
- `POST /bind/code`：`purpose=new_student|rebind`、可选 `target_student_id`；一次性、10 分钟有效。
- `POST /auth/student/login`：使用持久化 `installation_id`；新设备绑定会吊销同一孩子的旧设备。

### 老师角色

- `GET /chat/teachers`：返回当前家庭可选老师的 `teacher_id`、`name`、`avatar_url`、`sort_order`、`access`；`access` 为 `available|subscription_required|daily_free_exhausted`，不返回 provider、模型或 Key。
- `POST /chat`、`POST /chat/stream`：新会话可传 `teacher_id`；已有会话固定原老师。
- `GET /chat/sessions`：返回 `teacher_id`、`teacher_name`、`teacher_avatar_url` 快照。
- `PATCH /admin/llm-groups/{id}/teacher-profile`：super/admin 按权限修改老师姓名、头像、启用状态、排序和 `post_trial_free_enabled`；修改只影响新会话，写入 AdminLog。
- 家长会话列表、消息详情、导出和评估证据返回同一老师快照，保证历史同步。

### 订阅与 CMS

- `GET /parent/subscription`：返回 `seat_count`、`used_seats`、基础价、增量价、免费期和到期后每日免费次数。
- `POST /parent/subscription/seats`：按当前周期剩余天数折算并立即增加孩子名额，必须携带幂等键。
- `GET/POST /admin/pricing-config`：super 读取/修改基础价、增量价、试用天数、到期后每日免费次数。
- `POST /admin/users`、`PATCH /admin/users/{id}`：super 创建和调整 `super/admin/support` 账号。

### 成绩与趋势

- `GET/POST/PATCH/DELETE /chat/grades[/{grade_id}]`：学生只可访问本人；删除为逻辑删除，`GET /chat/grades?include_deleted=true` 可查看并恢复。
- `GET/POST/PATCH/DELETE /parent/students/{id}/grades[/{grade_id}]`：家长只可访问本家庭孩子；编辑、删除和恢复均产生新版本。
- `GET /chat/grades/{grade_id}/history`、`GET /parent/students/{id}/grades/{grade_id}/history`：返回版本、操作者、时间和修改原因。
- `GET /chat/grade-trend?subject=&from=&to=`、`GET /parent/students/{id}/grade-trend?subject=&from=&to=`：按百分比返回趋势点、差值、平均值和方向。

### 评估

- `POST/GET /chat/academic-assessments`、`POST/GET /parent/students/{id}/academic-assessments`：生成或读取带证据、输入时间范围、数据版本、模型版本和免责声明的学业评估；生成按主体每日限额。
- `POST/GET /parent/students/{id}/wellbeing-assessments`：家长专属的“身心状态关注提示”；不输出诊断结论。
- `POST /parent/wellbeing-assessments/{id}/ack`：记录家长已关注/无需跟进。查看、生成、导出均写审计日志。
