# ai-zhuxue（AI 助学）

面向未成年人的受保护 AI 助学系统：学生端 AI 对话被学习围栏约束（仅限学习话题），家长端全量可见并可管控，**AGPL-3.0** 开源。

技术栈：**Flutter 双端（学生端/家长端）+ FastAPI + PostgreSQL**。

## 核心特性

- **学习围栏四阶段**：整句分类 → 红线白名单兜底 → 低置信度 LLM 二次判定 → 分级处置（应答/引导改写/拒绝）。llm 模式实测：学习应答率 100%、敏感拦截 100%、对抗绕过拦截 100%（题库评测脚本 `tools/eval_fence.py` 随附）。
- **家长可见性**：全部对话/逐条消息/围栏判定流水只读可查，支持内容搜索、学习摘要、审查导出。
- **时长管控**：真实心跳累计（非消息数近似）、每日上限、家长自定义禁用时段。
- **安全优先流式**：默认先全文复核、通过后回放——敏感内容在任何字符到达终端前即被替换。
- **商业化闭环**：注册开试用 → 到期拦截 → 续费/赠送 → CMS 订阅统计。
- **CMS 管理后台**：运营看板、LLM 分组热切换、家庭标签路由、RBAC（super/ops）、会员赠送/扣除全留痕。
- **Web 端**：仅聊天（绑定/流式/Markdown/KaTeX/会话抽屉），范围冻结。

## 文档索引

| 文档 | 内容 |
|------|------|
| [docs/architecture.md](docs/architecture.md) | 系统组成、核心数据流、数据模型、鉴权设计、技术决策 |
| [docs/api.md](docs/api.md) | 全部端点参考（请求/响应/错误码）+ Swagger（`/docs`） |
| [docs/fence-design.md](docs/fence-design.md) | 围栏四阶段管线、分级处置、验收指标、题库扩展规范、已知局限 |
| [docs/deployment.md](docs/deployment.md) | 配置项全表、本地/Docker 部署、生产 Checklist |
| [docs/compliance-design.md](docs/compliance-design.md) | 法规要求 → 产品机制 → 待法务界定点 对照 |
| [docs/roadmap.md](docs/roadmap.md) | M0–M3 路线图与依赖关系 |

## 快速开始

**后端**（开发模式：SQLite + mock 三要素核验 + 固定短信码 123456）：

```bash
cd server
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/alembic upgrade head                       # 从零建库（全部 17 表）
.venv/bin/uvicorn app.main:app --port 8100
```

> **数据库说明**：本仓库**不含任何数据库文件**——库里是用户会话、对话与操作日志，不应出现在代码仓库。表结构全部由 Alembic 迁移链管理（`server/migrations/`），首次启动 `alembic upgrade head`（或以 `ENV=dev` 启动时自动 `create_all`）从零建出完整库。

配置经环境变量注入（复制 `.env.example` 为 `.env`）：`FENCE_MODE=llm` 配 `GLM_API_KEY`/`OPENROUTER_API_KEY` 启用 LLM 分类；默认 `heuristic` 规则模式（无 Key 可跑）。

**Flutter 双端**（同一代码库，dart-define 切换）：

```bash
cd app
flutter pub get
flutter run --dart-define=ROLE=student   # 学生端
flutter run --dart-define=ROLE=parent    # 家长端
# API 地址：--dart-define=API_BASE=http://<host>:8100（模拟器默认 10.0.2.2:8100）
```

**Docker 部署**：

```bash
JWT_SECRET=$(openssl rand -hex 32) FENCE_MODE=llm docker compose up -d --build
```

**CMS**（独立服务，与 API server 分离部署、互不影响起停）：`http://localhost:8101/`（管理员账号或 `ADMIN_TOKENS` 环境变量）。

```bash
# 本地开发（页面服务，API 默认指向 http://localhost:8100）
server/.venv/bin/uvicorn cms.main:app --port 8101
# 或指向其他后端地址
CMS_API_BASE=http://<api-host>:<port> server/.venv/bin/uvicorn cms.main:app --port 8101
```

CMS 页面确定后端地址的优先级：URL `?api=` 参数 > 服务端注入的 `CMS_API_BASE` > 同源兜底。

## 质量保障

- `server/tests/`：**85 例 pytest**（围栏规则/处置策略/审计流水、API 端到端、RBAC 角色隔离、绑定码防重放、每日上限强制、用量成本、家长审查、赠送扣除）；
- `app/test/`：widget 测试；`flutter analyze` 零告警；
- `tools/eval_fence.py`：围栏题库指标评测 + `--check` 阈值断言（CI 中 key 缺失自动跳过）；
- CI：`.github/workflows/ci.yml`（pytest + flutter analyze/test + 围栏指标回归）。

## 围栏题库扩展

`tools/fence_bank.yaml` 为双题库（学习应答/红线拦截），当前为演示规模。扩展规范见 [docs/fence-design.md](docs/fence-design.md)：

```bash
cd server
FENCE_MODE=llm OPENROUTER_API_KEY=sk-… python -m tools.eval_fence --check
```

## 许可与免责

- 代码以 **AGPL-3.0** 许可发布（见 [LICENSE](LICENSE)）——任何衍生服务（含云托管）须同样开源；
- 本项目调用第三方大模型 API（GLM/DeepSeek/Kimi/OpenRouter 等，OpenAI 兼容协议），模型的生成内容质量、合规性由使用者自行评估并遵守所在司法辖区要求；面向未成年人提供服务前，请完成所在地区的核验、备案等合规流程；
- 本仓库不含数据库文件与真实用户数据；示例中的手机号/短信码均为测试值。
