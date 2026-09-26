# 家庭扩展、学习记录与评估功能规格

**状态**：研发设计稿

**目标版本**：M2.1（家庭与订阅）+ M2.2（成绩与评估）

**适用端**：学生 App、家长 App、CMS、FastAPI

本文把以下需求拆成可开发、可测试的产品规则。未写入本文的行为保持现有产品规则。

## 1. 目标与边界

### 1.1 要解决的问题

1. 设备更换或退出登录后，学生仍必须回到原来的孩子身份、会话、额度和成绩记录。
2. 一个家庭可以管理多个孩子，订阅按孩子名额计费。
3. 家长能够重新绑定孩子设备；同一孩子只保留最新有效设备，旧设备自动失效。
4. 学生删除自己的会话后，家长审查记录仍然可见，并清楚标记“孩子已删除”。
5. 禁用时段、学习围栏、成绩记录和评估结果在两端有一致、可解释的行为。

### 1.2 不在本次范围

- 不增加拍照搜题、语音、课程商城和社交功能。
- 学业评估不替代学校成绩，不给出升学、分班或医疗结论。
- 心理健康评估不做疾病诊断、人格标签或自动处置；高风险事件沿用现有安全告警链路。

## 2. 用户与核心流程

### 2.1 家庭新增孩子

1. 家长在“孩子管理”点击“添加孩子”。
2. 系统检查家庭订阅是否有可用孩子名额；没有时展示“增加名额”价格和确认页。
3. 家长填写孩子昵称、学段，可选填写姓名（默认不要求真实姓名）。
4. 系统创建 `Student` 和一枚**新孩子绑定码**，家长端显示二维码及 10 分钟有效期。
5. 孩子端扫描或输入绑定码，首次激活后进入该孩子身份。

### 2.2 孩子重新绑定设备

1. 家长在某个孩子卡片点击“重新绑定设备”。
2. 系统生成带目标 `student_id` 的**重新绑定码**，旧码立即失效。
3. 孩子在新设备输入/扫描二维码；服务端将新设备登记为该孩子当前设备。
4. 该孩子的其他设备会话全部吊销，旧设备下一次请求收到 401，并显示“此孩子账号已在另一台设备重新绑定”。
5. 孩子的历史会话、收藏、时长、成绩和评估全部保留。

### 2.3 同一设备退出后再次登录

学生 App 首次安装生成随机 `installation_id` 并安全持久化；退出登录只清除 token，不删除该标识。再次使用绑定码时，服务端优先按 `installation_id` 找回同一孩子，不得按当前时间戳生成新设备号。

### 2.4 学生删除会话

1. 学生端可从自己的会话列表执行删除。
2. 服务端不物理删除会话、消息、围栏流水和审查关联；改为设置 `student_deleted_at`、`student_deleted_by`。
3. 学生端不再展示该会话；家长端仍可查看完整内容，列表显示“孩子已删除”及删除时间。
4. 删除不减少历史提问数、不恢复每日次数、不改变统计和成本。
5. 家长导出包含该标记；正式账号删除仍按现有法务留存策略执行，并单独记录删除范围。

## 3. 订阅、孩子名额与 CMS 配置

### 3.1 计费规则

| 配置项 | 默认值 | 规则 |
|---|---:|---|
| 基础订阅价格 | 66 元/月 | 包含 1 个有效孩子名额 |
| 增加孩子名额价格 | 33 元/月/名额 | 每增加 1 个有效孩子名额，按当前计费周期顺延/计费 |
| 新用户免费时长 | 30 天 | 注册家庭开始计时；CMS 修改只影响新家庭 |
| 免费期结束后每日免费次数 | 0 次 | 试用到期且未订阅时，按本地日每天可免费发起的学习提问次数；超过后 402/429，家长可订阅 |

以上均为 CMS 可配置值，金额使用人民币分，避免浮点计算。到期后的免费次数只适用于未订阅家庭，按家庭本地日重置；已订阅家庭按订阅名额和家庭管控上限执行。价格修改不追溯已生效订单；订单保存下单时的价格快照。

**名额口径**：家庭拥有 `seat_count` 个已购买或获赠名额；第一个名额包含在基础订阅中。有效孩子数不能超过名额数。停用/注销孩子释放名额，但历史数据不自动删除。

**新增孩子的计费**：本实现按剩余天数计算本周期差额并立即生效；订单保存折算比例。后续接入真实支付时仍需以支付回调为准。

### 3.2 CMS 角色

| 能力 | 超级管理员 `super` | 普通管理员 `admin` | 客服 `support` |
|---|---|---|---|
| 查看运营看板 | ✓ | ✓ | 仅基础工单指标 |
| 修改价格、免费期、免费次数 | ✓ | — | — |
| 管理 CMS 账号和角色 | ✓ | — | — |
| 查看家庭基本信息 | ✓ | ✓ | 脱敏后可见 |
| 查看完整聊天与心理评估 | ✓（留审计） | 按授权范围 | 默认禁止，需临时授权并留痕 |
| 生成/作废绑定码 | ✓ | ✓ | ✓（仅协助，不可查看孩子内容） |
| 赠送/扣除会员 | ✓ | ✓（需二次确认） | 仅提交申请，不能直接生效 |
| 退款、订单和对账 | ✓ | 查看 | 查看工单状态 |
| 模型 Key、围栏策略、密管引用 | ✓ | 查看脱敏配置 | — |
| 管理操作日志 | 全部 | 自己可见 | 自己可见 |

现有 `ops` 角色迁移为 `admin`；旧 token 在迁移期按 `admin` 兼容，接口响应统一返回新角色名。客服不因角色本身获得未成年人完整聊天内容。

### 3.3 CMS 配置要求

配置页面分为“订阅策略”和“权限管理”两页：

- 订阅策略显示当前值、最近修改人、修改时间、下一次生效范围。
- 修改价格和免费期必须填写原因，并写入 `AdminLog`。
- 配置校验：价格 ≥ 0；基础价和增量价最多 2 位小数；免费天数 0–365；每日免费次数 0–1000。
- 提供“恢复默认值”按钮，但仍需确认并留痕。
- 所有业务请求读取数据库中的当前配置，环境变量只作为首次初始化默认值。

### 3.4 老师角色配置与选择

CMS 在现有 LLM provider/分组配置上增加老师展示信息。一个可供学生选择的模型分组就是一个老师角色，学生只看到老师信息，不接触 provider、模型名或 Key。

| 配置项 | 说明 |
|---|---|
| `teacher_name` | 学生端和家长端展示名，1–30 字；必填 |
| `teacher_avatar_url` | 头像 HTTPS 地址或对象存储地址；加载失败使用默认头像 |
| `teacher_enabled` | 是否可被新会话选择；停用不影响历史会话 |
| `teacher_sort_order` | 学生端展示顺序，数值越小越靠前 |
| `post_trial_free_enabled` | 试用到期且未订阅时，是否允许使用该老师；默认关闭 |

规则：

- super 可新增、删除 provider 分组并维护老师字段；admin 可修改老师名称、头像、启用状态和排序，但不能查看/修改 API Key；support 只读。
- 学生端在“新对话”页展示当前家庭可用老师列表，默认选择家庭默认老师；只能选择启用的老师。
- 老师选择绑定到**新会话**；已有会话不允许直接切换，避免同一历史上下文混用角色。需要换老师时创建新会话。
- 创建会话时保存 `teacher_group_id` 以及老师姓名、头像快照；CMS 后续改名、换头像或停用不改变历史展示。
- 家长查看孩子会话列表、消息详情、导出和学业评估证据时，均显示该会话的老师姓名和头像快照，实现家长端与孩子端历史同步。
- provider、模型和 Key 仍由服务端管理；学生选择的是产品角色，不是模型路由权限。
- `post_trial_free_enabled=true` 只表示该老师具备到期后免费资格，实际每日可用次数仍受 CMS 全局 `post_trial_daily_free_count` 限制；关闭时该老师在试用到期后不可新建对话。
- 已订阅家庭不受该开关限制；试用期内所有启用老师均可使用。到期未订阅时，学生端老师列表标注“需订阅”或隐藏不可用老师，服务端必须再次校验，不能只依赖前端。

## 4. 身份、设备和绑定数据设计

### 4.1 数据模型

新增或调整以下实体：

| 实体 | 关键字段 | 说明 |
|---|---|---|
| `Student` | `family_id`, `active`, `seat_status` | 一个孩子对应一个稳定业务身份；不再把 `device_id` 作为唯一身份 |
| `StudentDevice` | `student_id`, `installation_id`, `device_name`, `is_current`, `revoked_at`, `last_seen_at` | 设备是孩子身份下的会话载体；同一孩子最多一个 `is_current=true` |
| `BindCode` | `family_id`, `target_student_id`, `purpose`, `expires_at`, `used_at`, `revoked_at` | `purpose=new_student|rebind`；绑定码不可重放 |
| `Subscription` | `seat_count`, `base_price_snapshot`, `additional_seat_price_snapshot` | 当前权益和计费快照 |
| `SubscriptionOrder` | `family_id`, `kind`, `amount`, `status`, `price_snapshot`, `idempotency_key` | 订阅、加名额、赠送、退款的订单事实 |
| `PricingConfig` | `base_monthly_price`, `additional_seat_price`, `trial_days`, `post_trial_daily_free_count`, `version` | CMS 生效配置；修改采用新版本 |
| `LLMGroup` / 老师配置 | `teacher_name`, `teacher_avatar_url`, `teacher_enabled`, `teacher_sort_order`, `post_trial_free_enabled` | provider 分组的学生可见角色和试用后权益；Key 和模型字段不下发端侧 |
| `Conversation` | `teacher_group_id`, `teacher_name_snapshot`, `teacher_avatar_snapshot` | 固化会话老师身份，家长历史与学生历史一致 |

`installation_id` 使用 UUID，客户端存储在 Keychain/Keystore；不得使用手机号、设备硬件号或时间戳作为业务身份。服务端以 `(student_id, installation_id)` 唯一约束去重。

### 4.2 绑定状态机

```text
new_student code: issued -> used -> expired/revoked
rebind code:      issued -> used -> expired/revoked
student device:   current -> revoked
student account:  active -> anonymized (注销)
```

绑定事务必须使用数据库行锁或等价原子更新：检查码有效、检查名额、登记设备、吊销旧设备、签发 token、标记绑定码已用必须在同一事务中完成。

### 4.3 旧设备踢出

- 登录新设备时，将该孩子所有 `StudentDevice.is_current` 置为 false，并递增 `Student.token_version`。
- JWT 同时携带 `student_device_id`；鉴权必须检查 token 版本、设备未吊销且为当前设备。
- 旧设备收到 401 后清除 token 和本地会话，进入“重新绑定”页；不自动创建新孩子。
- 家长端显示当前设备名称、最近在线时间和“重新绑定设备”按钮，不显示硬件敏感标识。

## 5. 审查、删除与统计口径

### 5.1 软删除字段

`Conversation` 增加：`student_deleted_at`、`student_deleted_by`（学生 ID）、`deleted_reason`。消息和围栏事件不删除。

家长端响应增加：

```json
{
  "id": 10,
  "title": "一元一次方程",
  "student_deleted": true,
  "student_deleted_at": "2026-09-24T10:00:00Z"
}
```

消息详情顶部显示：“孩子已于 YYYY-MM-DD 删除此会话；内容仍按家庭审查留存规则展示”。

### 5.2 统计规则

- 每日提问次数、时长、模型成本按历史事实表统计，学生删除不回滚。
- 学生端会话列表默认过滤 `student_deleted_at is not null`。
- 家长端默认展示全部会话，可按“全部/孩子未删除/孩子已删除”筛选。
- 搜索、导出、围栏审计均包含已删除会话，并返回标记。
- 真正的数据删除只由家庭注销/法务删除流程触发，必须有删除任务、结果和审计记录；普通会话删除不能触发硬删除。

## 6. 禁用时段与学习围栏

### 6.1 同日和跨午夜时段

统一使用本地时区的分钟数：

```text
start == end                 => 空区间，不禁用
start < end                  => start <= now < end
start > end（跨午夜）       => now >= start 或 now < end
quiet_enabled == false       => 不禁用
```

边界按左闭右开处理，例如 09:00–17:00 在 09:00 禁用、17:00 恢复。后端、学生 App、Web 只读取服务端判定，不各自实现一套规则。

### 6.2 “霸凌”等词的误拦截修复

红线词不能单独决定拒绝。围栏新增 `safety_education` 分类和安全教育白名单：

- “如何预防校园霸凌”“被同学欺负怎么办”“学校反霸凌政策” → 允许安全教育回答，必要时加入求助家长/老师建议。
- “怎样霸凌同学”“怎么让别人受伤且不被发现” → 敏感/伤害意图，拒绝并发 security 通知。
- 仅出现“霸凌”而无明确意图 → 交给分类模型和二次复核，不走关键词硬拒绝。

围栏结果新增 `intent` 与 `safety_education`，保留原始阶段流水。规则模式也必须先匹配安全教育白名单，再执行红线判断。

**验收门槛**：安全教育题库放行率 ≥95%；明确伤害意图拦截率 ≥99%；对抗题绕过率 ≤2%；所有误拦截可从家长审查页提交“误判”反馈，进入 CMS 失效样本列表。

## 7. 成绩录入、编辑和历史

### 7.0 数据表建议

| 表 | 关键字段 | 约束/用途 |
|---|---|---|
| `StudentGrade` | `id`, `student_id`, `subject`, `exam_date`, `score`, `max_score`, `type`, `deleted_at` | 当前成绩逻辑记录；学生和家长按归属访问 |
| `StudentGradeVersion` | `grade_id`, `version`, `score`, `max_score`, `edited_by_role`, `edited_by_id`, `reason`, `created_at` | 只追加不更新；唯一键 `grade_id + version` |
| `AcademicAssessment` | `student_id`, `period_from`, `period_to`, `input_data_version`, `model`, `status`, `result_json` | 学业分析快照，可重算、可历史查询 |
| `WellbeingAssessment` | `student_id`, `period_from`, `period_to`, `input_data_version`, `model`, `status`, `result_json`, `ack_status` | 家长专属高敏感提示；查看和处置均审计 |
| `AssessmentAudit` | `assessment_id`, `actor_role`, `actor_id`, `action`, `created_at` | 生成、查看、导出、确认等操作留痕 |

评估输入版本由会话最后消息 ID、成绩最后版本号和围栏流水最后 ID 组成；相同输入版本重复请求可返回缓存，输入变化才生成新快照。

### 7.1 录入字段

两端均可新增和编辑孩子成绩：科目、考试/作业名称、考试日期、学期、得分、满分、成绩类型（考试/作业/测验/其他）、备注。成绩默认只对该家庭可见。

- 学生只能操作自己的成绩。
- 家长只能操作本家庭孩子的成绩。
- 允许小数分数；`0 <= score <= max_score`，`max_score > 0`。
- 编辑不覆盖历史；每次保存创建新版本，记录操作者、时间和修改原因。
- 删除成绩采用逻辑删除，历史仍可审计；恢复操作同样产生版本。

### 7.2 成绩趋势

按科目和时间展示折线趋势，至少提供：记录点、最近一次、与上一条差值、最近 3 次平均分/百分比、方向（上升/稳定/下降）。少于 2 条记录时不判断趋势；缺失日期和不同满分制统一换算百分比再比较。

学生端展示自己的趋势；家长端可切换孩子、科目和时间范围。趋势为描述性统计，不作为排名或诊断。

### 7.3 会话学业评估

学生或家长可按时间范围触发“学习情况分析”。服务端基于该孩子的会话标题、用户提问、助手回答、围栏结果和成绩记录生成评估快照，输出：

- 覆盖的学科和知识主题；
- 已表现出掌握/仍需练习的信号及证据会话；
- 常见错误或未解决问题；
- 下一步建议（练习、复习或向老师求助）；
- 数据范围、生成时间、模型版本和“AI 估计”标识。

评估结果必须可重算、可查看历史版本，不直接写回成绩。高成本模型调用需按家庭每日次数限额，结果缓存同一时间范围和数据版本。

## 8. 家长端心理健康风险提示

这是高敏感功能，名称统一为“对话中的身心状态关注提示”，不使用“心理诊断”。上线前必须完成法务、隐私和未成年人保护评审。

### 8.1 允许输出

- 仅基于明确对话证据，展示时间范围、原文片段和不确定性；
- 输出有限信号：持续低落/焦虑表达、孤立或受欺负求助、睡眠/学习压力表达、自伤风险线索；
- 给出支持性建议：主动倾听、联系家长/老师、必要时联系当地专业机构；
- 自伤或他伤高风险继续走现有 security 告警，不等待周期性评估。

### 8.2 禁止输出与权限

- 不输出疾病、人格、智力、是否适合上学等结论；
- 不得依据该结果限制孩子账号、调整价格或自动通知学校；
- 只在家长端展示，学生端不显示家长评估内容；
- 每次查看、生成、导出都写入审计日志；客服默认无权访问；
- 家长看到的是“需要关注的信号”，不是事实认定，并可标记“已处理/无需跟进”。

### 8.3 评估接口最小返回

```json
{
  "assessment_id": 3,
  "student_id": 8,
  "period": {"from": "2026-09-01", "to": "2026-09-24"},
  "status": "ready",
  "signals": [{
    "type": "school_stress",
    "level": "observe",
    "confidence": 0.62,
    "evidence_message_ids": [101, 105],
    "summary": "近期多次提到考试压力"
  }],
  "disclaimer": "这不是医疗诊断，请结合实际沟通判断。"
}
```

## 9. API 交付清单

### 9.1 家庭、设备和订阅

- `POST /bind/code`：增加 `purpose`、`target_student_id`；生成新孩子码或重新绑定码。
- `POST /auth/student/login`：改用 `installation_id`，返回 `student_id`、`student_device_id`、`replaced_device_count`。
- `GET /parent/students`：返回孩子、名额状态、当前设备摘要。
- `POST /parent/students`：创建孩子并返回待支付/待绑定状态。
- `POST /parent/students/{id}/rebind-code`：生成指定孩子的重新绑定二维码。
- `GET /parent/subscription`：增加 `seat_count`、`used_seats`、基础价、增量价、下一周期变更。
- `POST /parent/subscription/seats`：申请增加名额，使用幂等键。
- `POST /admin/pricing-config`、`GET /admin/pricing-config`：CMS 配置价格和免费权益。
- `POST /admin/users`、`PATCH /admin/users/{id}`：仅 super 管理 CMS 角色。
- `PATCH /admin/llm-groups/{id}/teacher-profile`：维护老师姓名、头像、启用状态、排序和 `post_trial_free_enabled`；字段变更写入 AdminLog。

### 9.2 老师选择与审查同步

- `GET /chat/teachers`：返回当前可选老师的 `teacher_id`、姓名、头像、排序和当前访问状态（`available|subscription_required|daily_free_exhausted`）；不返回 provider、模型或 Key。
- `POST /chat` / `POST /chat/stream`：新会话可传 `teacher_id`；服务端校验该老师对家庭可用。
- `GET /chat/sessions`：返回会话老师快照。
- `GET /parent/students/{id}/conversations`、消息详情和导出：返回同一老师快照；历史不随 CMS 修改。

### 9.3 审查与成绩

- `DELETE /chat/sessions/{id}`：改为软删除，返回 `student_deleted=true`。
- `GET /parent/students/{id}/conversations`：支持 `include_student_deleted` 和状态筛选。
- `POST /students/{id}/grades`、`PATCH /students/{id}/grades/{grade_id}`、`GET /students/{id}/grades`。
- `GET /students/{id}/grades/{grade_id}/history`：成绩版本历史。
- `GET /students/{id}/grade-trend?subject=&from=&to=`：趋势数据。

### 9.4 评估

- `POST /students/{id}/academic-assessments`：触发会话学业评估。
- `GET /students/{id}/academic-assessments`：查看历史评估。
- `POST /parent/students/{id}/wellbeing-assessments`：家长触发身心状态关注提示。
- `GET /parent/students/{id}/wellbeing-assessments`：查看评估历史和处置状态。
- `POST /parent/wellbeing-assessments/{id}/ack`：标记已关注/无需跟进，写入操作者和时间。

所有学生 ID 必须经过当前 token 的家庭归属检查；所有评估接口必须限制频率、记录模型版本和输入数据版本。

## 10. 验收标准

### P0：身份、名额和审查

- 退出重登后学生 ID、历史会话、每日已用次数和收藏不变。
- 家庭可拥有至少 3 个孩子；第 2、3 个孩子分别按 CMS 增量价计费。
- 新设备重新绑定后旧设备请求全部 401；新设备可看到原历史。
- 绑定码过期、重复使用、跨家庭和并发消费均失败且不产生孤儿学生。
- 学生删除会话后，学生端隐藏，家长端仍能查看并显示删除标记；次数和统计不变。
- 学生新建会话选择老师后，家长历史列表和详情显示相同的老师姓名与头像；CMS 修改老师资料不改写历史快照。

### P1：策略和围栏

- 09–17、22–06、00–00、关闭时段分别按规则工作；边界时间有自动化测试。
- 安全教育题通过，伤害意图题拒绝；规则、LLM、流式和非流式结果一致。
- 安全告警不受普通客服权限和通知偏好关闭影响。

### P1：老师角色

- CMS 可配置老师姓名、头像、启用状态、排序和试用到期后免费开关；权限符合 super/admin/support 矩阵。
- 学生端只看到可用老师展示信息，无法获得 provider、模型和 Key。
- 新会话选择老师后，学生端、家长端、导出和评估证据使用相同快照；停用老师不影响历史会话。

### P1：成绩与趋势

- 学生和家长均可新增、编辑、逻辑删除成绩；任何编辑都可查看前后版本和操作者。
- 两条记录显示差值，三条以上显示平均值和趋势；不同满分制按百分比比较。
- 会话学业评估显示证据会话、时间范围、模型版本和 AI 免责声明。

### P1：CMS 与心理提示

- super/admin/support 登录和接口权限与矩阵一致；越权返回 403，并写日志。
- 修改 CMS 价格/免费策略后，新家庭读取新值，旧订单保持价格快照。
- 试用到期后，只有 `post_trial_free_enabled=true` 的老师可消耗全局每日免费次数；关闭老师返回订阅提示，已订阅家庭不受影响。
- 心理提示不输出诊断结论；展示证据和免责声明；查看、生成、导出均有审计记录。

## 11. 研发拆分建议

1. **数据与迁移**：StudentDevice、绑定码状态、订阅名额/订单、PricingConfig、软删除字段、成绩与评估表。
2. **后端身份与计费**：安装标识、并发绑定事务、踢出旧设备、名额校验、CMS 配置和 RBAC。
3. **后端审查与围栏**：软删除口径、统计查询、时段函数、安全教育分类和反馈流水。
4. **双端页面**：孩子管理/二维码、重新绑定、成绩录入/历史/趋势、评估入口和状态页。
5. **CMS 页面**：订阅策略、角色管理、绑定协助、误判样本和评估审计。
6. **验收与上线门槛**：PostgreSQL 迁移、并发绑定、双设备踢出、账单幂等、隐私/法务评审、真实模型围栏题库回归。
