# ai-zhuxue（AI 助学）

面向未成年人的受保护 AI 助学系统：学生端 AI 对话被学习围栏约束（仅限学习话题），家长端全量可见并可管控，**AGPL-3.0** 开源。

技术栈：**Flutter 双端（学生端/家长端）+ FastAPI + PostgreSQL**。

## 核心特性

- **学习围栏四阶段**：整句分类 → 红线白名单兜底 → 低置信度 LLM 二次判定 → 分级处置（应答/引导改写/拒绝）。规则模式六组各 300 题回归达标；真实模型须按当前配置重新评测并保留人工抽检记录（`tools/eval_fence.py`）。
- **家长可见性**：全部对话/逐条消息/围栏判定流水只读可查，支持内容搜索、学习摘要；审查导出和孩子注销已有 API，家长 App 操作入口待补。
- **时长管控**：App 前台心跳累计、每日上限、家长自定义禁用时段；摘要无心跳时回退估算，Web 后台标签页计时待校准。
- **安全优先流式**：默认先全文复核、通过后回放——复核拦截的内容在回放前替换；显式 `live=true` 或关闭安全优先配置时实时输出，已送达内容无法撤回。
- **订阅骨架**：注册开可配置试用 → 到期额度控制 → CMS 赠送/统计；开发与测试支持模拟续费，生产续费及购买名额返回 503，真实支付待接入。
- **CMS 管理后台**：运营看板、LLM 分组热切换、家庭标签路由、RBAC（super/admin/support）、会员赠送/扣除全留痕。
- **Web 端**：仅聊天（绑定/流式/Markdown/KaTeX/会话抽屉），范围冻结。

## 当前能力边界（2026-10-03）

- 家长以短信验证码或本机号码认证登录，实名认证为登录后的可选流程；真实三要素核验未接入，生产核验接口返回 503。手机号登录不等于确认监护人身份。
- 学业评估与身心状态关注提示使用 `rules-v2`，不调用评估大模型；按所选本地日期检索对话、围栏和成绩。身心提示区分一般教育讨论、否定表达和个人求助，仍可能误判，不作为诊断或自动处置依据。
- 评估、摘要、心跳日期与用量日界按 `TZ_OFFSET_HOURS`（默认 8）统一计算；数据库时间戳存 UTC，周统计从本地周一开始。
- 通知为站内通知，离线推送、送达确认与失败重试待接入；协议版本、单独同意与撤回记录待补。上线前需完成法务、隐私和未成年人保护评审。

## 文档索引

| 文档 | 内容 |
|------|------|
| [docs/architecture.md](docs/architecture.md) | 系统组成、核心数据流、数据模型、鉴权设计、技术决策 |
| [docs/api.md](docs/api.md) | 全部端点参考（请求/响应/错误码）+ Swagger（`/docs`） |
| [docs/fence-design.md](docs/fence-design.md) | 围栏四阶段管线、分级处置、验收指标、题库扩展规范、已知局限 |
| [docs/deployment.md](docs/deployment.md) | 配置项全表、本地/Docker 部署、生产 Checklist |
| [docs/compliance-design.md](docs/compliance-design.md) | 法规要求 → 产品机制 → 待法务界定点 对照 |
| [docs/roadmap.md](docs/roadmap.md) | M0–M3 路线图与依赖关系 |
| [docs/feature-spec-family-growth-and-learning.md](docs/feature-spec-family-growth-and-learning.md) | 家庭扩展、订阅名额、设备重绑、审查留存、成绩与评估功能规格 |
| [docs/branding/logo-plan.md](docs/branding/logo-plan.md) | App、Web 与 CMS 的统一标志及使用规范 |

## 快速开始

**后端**（开发模式：SQLite + mock 三要素核验 + 固定短信码 123456）：

```bash
cd server
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/alembic upgrade head                       # 从零建库（完整表结构）
.venv/bin/uvicorn app.main:app --port 8100
```

> **数据库说明**：本仓库**不含任何数据库文件**——库里是用户会话、对话与操作日志，不应出现在代码仓库。表结构全部由 Alembic 迁移链管理（`server/migrations/`），首次启动 `alembic upgrade head`（或以 `ENV=dev` 启动时自动 `create_all`）从零建出完整库。

配置经环境变量注入（复制 `.env.example` 为 `.env`）：`FENCE_MODE=llm` 配 `GLM_API_KEY`/`OPENROUTER_API_KEY` 启用 LLM 分类；默认 `heuristic` 规则模式（无 Key 可跑）。

**Flutter 双端**（`app/` 下三个包：共享库 `app_core` + 学生端 `app_student` + 家长端 `app_parent`）：

```bash
# 学生端
cd app/app_student
flutter pub get
flutter run   # 需要真机/模拟器；家长端同理在 app/app_parent

# 家长端
cd app/app_parent
flutter pub get
flutter run
# 默认连接 https://api.gker.net；本地调试：--dart-define=API_BASE=http://<host>:8100
```

**Docker 部署**：

```bash
JWT_SECRET=$(openssl rand -hex 32) CORS_ORIGINS=http://localhost:8101 FENCE_MODE=llm docker compose up -d --build
```

**CMS**（独立服务，与 API server 分离部署、互不影响起停）：`http://localhost:8101/`（管理员账号密码登录）。

```bash
# 本地开发（页面服务，API 默认指向 http://localhost:8100）
server/.venv/bin/uvicorn cms.main:app --port 8101
# 或指向其他后端地址
CMS_API_BASE=http://<api-host>:<port> server/.venv/bin/uvicorn cms.main:app --port 8101
```

CMS 页面仅使用服务端注入的 `CMS_API_BASE`，未配置时使用同源地址；跨域部署需设置 API 的 `CORS_ORIGINS`。
全新数据库完成迁移后，运行 `cd server && .venv/bin/python -m tools.create_admin`，按提示创建首个超级管理员；密码由终端安全输入。

## 质量保障

- `server/tests/`：pytest 覆盖围栏规则、审计、RBAC、绑定、每日上限、用量成本、家长审查、老师角色和成绩评估；
- `app/app_core/test/`、`app/app_student/test/`、`app/app_parent/test/`：共享库与 widget 测试；`flutter analyze` 零告警；
- `tools/eval_fence.py`：围栏题库指标评测 + `--check` 阈值断言（CI 中 key 缺失自动跳过）；
- CI：`.github/workflows/ci.yml`（pytest + flutter analyze/test + 围栏指标回归）。

## 围栏题库扩展

`tools/fence_bank.yaml` 含学习、娱乐、敏感、安全教育、伤害意图和对抗六组题库，每组 300 题。扩展规范见 [docs/fence-design.md](docs/fence-design.md)：

```bash
cd server
FENCE_MODE=llm OPENROUTER_API_KEY=sk-… python -m tools.eval_fence --check
```

## 许可与免责

- 代码以 **AGPL-3.0** 许可发布（见 [LICENSE](LICENSE)）——任何衍生服务（含云托管）须同样开源；
- 本项目调用第三方大模型 API（GLM/DeepSeek/Kimi/OpenRouter 等，OpenAI 兼容协议），模型的生成内容质量、合规性由使用者自行评估并遵守所在司法辖区要求；面向未成年人提供服务前，请完成所在地区的核验、备案等合规流程；
- 本仓库不含数据库文件与真实用户数据；示例中的手机号/短信码均为测试值。
