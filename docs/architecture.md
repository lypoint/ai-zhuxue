# 架构与数据流

**版本**：2026-09-17（对应生产骨架 M0）｜评审依据：20260914 标准评审 + 20260916/17 关口核验

## 1. 系统组成

```
┌─────────────┐     ┌─────────────┐     ┌──────────────┐
│ 学生端 App   │     │ 家长端 App   │     │ Web 端(仅聊天)│
│ (Flutter,   │     │ (Flutter,   │     │ (规划中,复用  │
│  ROLE=      │     │  ROLE=      │     │  chat API)   │
│  student)   │     │  parent)    │     │              │
└──────┬──────┘     └──────┬──────┘     └──────┬───────┘
       │ HTTPS/JWT         │ HTTPS/JWT         │
       ▼                   ▼                   ▼
┌─────────────────────────────────────────────────────┐
│                FastAPI (server/app)                  │
│  auth(注册/登录)  bind(绑定码)  chat(聊天)  parent(审查) │
│         │                    │                       │
│         │             ┌──────┴────────┐              │
│         │             │ fence.py 围栏  │              │
│         │             │ 白名单→分类→   │              │
│         │             │ 二次判定→分级  │              │
│         │             └──────┬────────┘              │
│         ▼                    ▼                       │
│  guardian_verify       llm.py (GLM/DeepSeek/Kimi     │
│  (三要素核验)            OpenAI 兼容统一接入)           │
│         │                    │                       │
└─────────┼────────────────────┼───────────────────────┘
          ▼                    ▼
   阿里云/腾讯云          open.bigmodel.cn 等
   信息核验 API           (已备案大模型)
```

## 2. 核心数据流

### 2.1 激活链路（监护人主导）

1. **监护人注册** `POST /auth/guardian/register`：手机号+短信码 + **三要素核验**（姓名/身份证/手机号，`guardian_verify.py`；不采集人脸）。注册即创建 `Family` + `FamilySettings`（审查 default-on）。
2. **生成绑定码** `POST /bind/code`：8 位、10 分钟有效、一次性（`BindCode`）。
3. **学生绑定** `POST /auth/student/login`：学生端凭绑定码+设备号登录，创建/复用 `Student` 并归属家庭。此后学生端持 student JWT。

### 2.2 聊天链路（围栏内）

`POST /chat` 处理顺序：

```
政策检查(22-6禁用/每日上限) → 落库 user Message
  → fence.evaluate()：白名单→分类→(llm模式)二次判定→分级处置
  → FenceEvent 逐阶段落库 + user_msg.fence_action
  → 分支：
     reject  → 直接返回固定引导话术（assistant 消息, fence_action=reject）
     allow   → 拼接系统提示+近12条历史 → LLM 生成
     rewrite → 同上,但注入引导性系统提示把话题带回学习
  → assistant Message + UsageLog 落库 → 返回
```

### 2.3 会话恢复（学生端）

`GET /chat/latest`：返回学生最近一次对话的 id 与全部消息。学生端 ChatScreen 初始化时调用，重启 App 后聊天记录仍在（服务端持久化，UI 只做恢复）；恢复失败静默降级为新对话。

### 2.4 成本可观测

`GET /parent/students/{id}/usage`：按学生聚合 UsageLog，输出今日/累计 tokens 与**按厂商现价（`PRICE_PER_MTOK`）估算的成本**（优先上游真实 cost）。家长端审查页顶部展示。

### 2.5 审查链路（家长行使查阅权）

家长端全部只读：`/parent/family` 总览 → `/parent/students/{id}/conversations` → `/conversations/{id}/messages` + `/fence-events`。**不做任何删除/修改接口**——审查是监护人知情权的产品化，不可篡改（法务问题 1 的边界待界定前，先按最小暴露实现）。

## 3. 数据模型（8 表）

| 表 | 职责 | 关键设计 |
|---|---|---|
| `families` | 家庭（付费与管控单元） | 家长端订购的产品化载体 |
| `guardians` | 监护人 | phone 唯一；verified_at 记录核验时间 |
| `students` | 学生 | device_id 唯一；grade_band 分龄（8-12/12-16/16-18） |
| `bind_codes` | 一次性绑定码 | 10 分钟过期；used_by_student_id 防重放 |
| `family_settings` | 家长管控 | daily_message_cap（家长覆盖全局）、review_enabled |
| `conversations` / `messages` | 对话与消息 | fence_action 记录该条处置结果；tokens 用于成本核算 |
| `fence_events` | 围栏流水 | 每次判定的 stage/decision/category/confidence——误拦截分析与评测的基础数据 |
| `usage_logs` | 模型用量 | purpose 区分 chat/围栏分类/二次判定，供运营成本核算 |

## 4. 鉴权设计

- JWT（HS256），payload：`role`(guardian|student)、`sub`、`family_id`、`exp`（默认 7 天）。
- 端点隔离：`/chat/*` 仅 student token；`/parent/*` 仅 guardian token；`deps.py` 强制校验角色，student 无法访问任何家长端点，反之亦然。
- 学生端无独立账号体系（必须绑定家长端后使用），与提案「学生端扫码绑定家长端才能使用」一致。
- 已知短板（M1 解决）：无 token 吊销/刷新机制；guardian 依赖短信码频控（dev 为固定码）。

## 5. 关键技术决策与理由

| 决策 | 理由 |
|---|---|
| Flutter 单库双 flavor（dart-define ROLE） | 双端 UI 同构度高（都是列表+表单+聊天），一套代码降低双端成本；原生能力需求当前很少 |
| 围栏放服务端而非端侧 | 家长审查数据需要服务端落库；围栏可独立评测迭代；端侧仅做输入前提示。注意：规避设计分析中「端侧判定」是备选路径，当前不采用 |
| 围栏四阶段流水落库 | 验收指标（学习应答率/误拦截率/绕过率）需要逐阶段数据；误拦截申诉也要靠它 |
| LLM 统一 OpenAI 兼容抽象 | 三家模型商条款风险不同（DeepSeek/Kimi 已核实非禁止性，智谱待商务确认），需可一键切换并锁价 |
| create_all 而非 Alembic | 骨架期模型快速演进；上线前必须切换（见 roadmap M1） |
