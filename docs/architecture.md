# 架构与数据流

**版本**：2026-09-17（对应生产骨架 M0）｜评审依据：20260914 标准评审 + 20260916/17 关口核验

## 1. 系统组成

```
┌─────────────┐     ┌─────────────┐     ┌──────────────┐
│ 学生端 App   │     │ 家长端 App   │     │ Web 端(仅聊天)│
│ (Flutter,   │     │ (Flutter,   │     │ (已实现,复用  │
│ app_student │     │ app_parent  │     │  chat API)   │
│ +app_core)  │     │ +app_core)  │     │              │
└──────┬──────┘     └──────┬──────┘     └──────┬───────┘
       │ HTTPS/JWT         │ HTTPS/JWT         │
       ▼                   ▼                   ▼
┌─────────────────────────────────────────────────────┐
│         FastAPI API 服务 (server/app, :8100)         │
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

## 1.5 CMS 独立服务

管理后台（CMS）是**独立 FastAPI 服务**（`cms/`，默认端口 8101）：只托管单页（`GET /`），
所有数据操作跨端口调用 API server 的 `/admin` 组接口。两服务互不依赖进程存活：
- 停 CMS：API、App、Web 聊天不受影响；
- 停 API server：CMS 页面仍可打开（接口调用报错）。
页面后端地址解析：`?api=` 参数 > `CMS_API_BASE` 环境变量注入 > 同源兜底。

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

家长端审查链路为：`/parent/family` 总览 → `/parent/students/{id}/conversations` → `/conversations/{id}/messages` + `/fence-events`；审查内容不可篡改，但家长可提交围栏误判反馈，成绩和评估通过独立版本化接口维护。

## 3. 数据模型

| 表 | 职责 | 关键设计 |
|---|---|---|
| `families` | 家庭（付费与管控单元） | 家长端订购的产品化载体 |
| `guardians` | 监护人 | phone 唯一；verified_at 记录核验时间 |
| `students` | 学生 | 稳定业务身份；grade_band 分龄（8-12/12-16/16-18） |
| `bind_codes` | 一次性绑定码 | 10 分钟过期；used_by_student_id 防重放 |
| `family_settings` | 家长管控 | daily_message_cap（家长覆盖全局）、review_enabled |
| `conversations` / `messages` | 对话与消息 | fence_action 记录该条处置结果；tokens 用于成本核算 |
| `fence_events` | 围栏流水 | 每次判定的 stage/decision/category/confidence——误拦截分析与评测的基础数据 |
| `fence_feedback` | 误判反馈 | 家长申诉与 CMS 复核状态，不修改原始围栏流水 |
| `usage_logs` | 模型用量 | purpose 区分 chat/围栏分类/二次判定，供运营成本核算 |

## 4. 鉴权设计

- JWT（HS256），payload：`role`(guardian|student)、`sub`、`family_id`、`exp`（默认 7 天）。
- 端点隔离：`/chat/*` 仅 student token；`/parent/*` 仅 guardian token；`deps.py` 强制校验角色，student 无法访问任何家长端点，反之亦然。
- 学生端无独立账号体系（必须绑定家长端后使用），与提案「学生端扫码绑定家长端才能使用」一致。
- 学生设备重绑和登出通过 token_version + StudentDevice 吊销旧 token；guardian 仍依赖短信码频控（dev 为固定码）。

## 5. 关键技术决策与理由

| 决策 | 理由 |
|---|---|
| Flutter 三包结构（app_core 共享库 + app_student + app_parent） | 双端 UI 同构度高（都是列表+表单+聊天），共享 api/theme 收敛进 app_core 免重复；两个独立 app 各自 applicationId，可同机并存、分别上架 |
| 围栏放服务端而非端侧 | 家长审查数据需要服务端落库；围栏可独立评测迭代；端侧仅做输入前提示。注意：规避设计分析中「端侧判定」是备选路径，当前不采用 |
| 围栏四阶段流水落库 | 验收指标（学习应答率/误拦截率/绕过率）需要逐阶段数据；误拦截申诉也要靠它 |
| LLM 统一 OpenAI 兼容抽象 | 三家模型商条款风险不同（DeepSeek/Kimi 已核实非禁止性，智谱待商务确认），需可一键切换并锁价 |
| Alembic 迁移 + 测试 create_all | 生产升级使用可回滚迁移；测试环境保留 create_all 便于隔离数据库 |

## 6. 后续功能的数据边界

家庭扩展、软删除、成绩与评估的字段和接口以 [feature-spec-family-growth-and-learning.md](feature-spec-family-growth-and-learning.md) 为准。关键原则：

- Student 是业务身份，设备通过 StudentDevice 关联；不能再用时间戳或单个设备号代表孩子；
- 绑定码区分 new_student 与 rebind，重新绑定在事务内吊销旧设备；
- 学生删除会话只写删除标记，家长审查、导出、成本和次数统计读取历史事实；
- 成绩版本不可覆盖，评估保存输入数据版本、模型版本、证据消息 ID 和生成时间；
- 心理健康相关输出属于高敏感推断，家长专属、客服默认禁止、所有访问留审计，且不产生医疗结论。
- provider 分组承载老师展示配置和试用到期后免费开关；会话保存老师姓名和头像快照，端侧只接收老师角色信息，不接触模型或 Key。
