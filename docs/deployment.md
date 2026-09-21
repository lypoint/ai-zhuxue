# 部署与运维

## 1. 配置项全表（`server/app/config.py`，全部环境变量）

| 变量 | 默认 | 说明 |
|------|------|------|
| `ENV` | `dev` | dev=固定短信码 123456 可用；prod 请务必切换 |
| `DATABASE_URL` | `sqlite:///./aizhuxue.db` | 生产用 `postgresql+psycopg2://…`（compose 已配） |
| `JWT_SECRET` | `change-me-in-prod` | **生产必须覆盖**，密钥管理服务注入 |
| `JWT_EXPIRE_HOURS` | `168` | token 有效期（小时） |
| `LLM_PROVIDER` | `glm` | `glm` \| `deepseek` \| `kimi`（OpenAI 兼容） |
| `GLM_API_KEY` / `DEEPSEEK_API_KEY` / `KIMI_API_KEY` | 空 | 对应厂商开放平台 Key |
| `CHAT_MODEL` | 空 | 留空用 provider 默认；上线型号须在已备案清单内 |
| `FENCE_MODEL` | 空 | 围栏分类用低成本档；留空同 CHAT_MODEL |
| `FENCE_MODE` | `heuristic` | `heuristic`（规则降级）\| `llm`（分类+二次判定，**验收与生产形态**） |
| `FENCE_DAILY_MESSAGE_CAP` | `200` | 全局每日消息上限（家长设置可覆盖） |
| `FENCE_QUIET_ENABLED` | `true` | 22–6 时段禁用开关（测试可关） |
| `FENCE_QUIET_START` / `FENCE_QUIET_END` | `22` / `6` | 禁用时段（按 `TZ_OFFSET_HOURS` 换算，与服务器时区无关） |
| `TZ_OFFSET_HOURS` | `8` | 本地日界/时段换算用的时区偏移（中国=8）；created_at 统一存 UTC |
| `GUARDIAN_VERIFY_PROVIDER` | `mock` | `mock` \| `aliyun` \| `tencent`（后两者待接入） |

## 2. 本地开发

```bash
cd server
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/alembic upgrade head                       # 从零建库（全部 17 表）
.venv/bin/uvicorn app.main:app --port 8100          # SQLite + mock 核验
FENCE_QUIET_ENABLED=false .venv/bin/uvicorn app.main:app --port 8100   # 测试时段放开
```

测试与围栏评测：

```bash
cd server
.venv/bin/python -m pytest -q                        # 单元+端到端测试（85 例）
.venv/bin/python -m tools.eval_fence                 # heuristic 指标
FENCE_MODE=llm GLM_API_KEY=sk-… .venv/bin/python -m tools.eval_fence   # 验收形态
```

## 3. Docker 部署

```bash
cd product
JWT_SECRET=$(openssl rand -hex 32) GLM_API_KEY=sk-… FENCE_MODE=llm docker compose up -d --build
```

- `db`：Postgres 16 + 健康检查 + 数据卷 `pgdata`；
- `api`：等 db 健康后启动，暴露 8000。生产建议前置 Nginx/Caddy 做 TLS 与限流；
- **时区**：日界与时段禁用按 `TZ_OFFSET_HOURS`（默认 8）换算，与容器时区无关，无需设置 TZ。

## 4. Flutter 构建产物

```bash
# 学生端 / 家长端（同一代码库，dart-define 切换）
flutter build apk --dart-define=ROLE=student --dart-define=API_BASE=https://api.example.com
flutter build apk --dart-define=ROLE=parent --dart-define=API_BASE=https://api.example.com
flutter build ipa   # iOS：需开发者账号签名
```

## 5. 生产 Checklist（骨架 → 上线）

**工程**
- [x] Alembic 迁移链可用（`alembic upgrade head` 从零建出全部 17 表；表结构变更走新迁移文件）
- [ ] JWT_SECRET/DB 密码/LLM Key 走密管，禁入 git
- [ ] API 限流（登录与 chat 端点）+ 请求日志 + 错误告警
- [ ] PostgreSQL 定期备份与恢复演练
- [ ] HTTPS（TLS 终结）+ App 端证书校验
- [ ] 短信服务商接入 + 短信码频控（dev 固定码仅 ENV=dev 生效）
- [ ] usage_logs → 成本看板（验证人均 token 假设）

**合规（依赖外部流程，见 compliance-design.md）**
- [ ] 三要素核验真实接入（阿里云/腾讯云开通）并留核验凭证
- [ ] 模型商书面确认未成年人服务许可
- [ ] App 备案 + 算法备案/安全评估（如法务意见认定需要）
- [ ] 《未成年人个人信息处理规则》、PIA 报告、监护人同意书上线（法务交付物）
- [ ] 公示所用已备案模型名称及备案号
- [ ] 围栏验收达标报告（题库 ≥300/库，指标全部过线）

**产品**
- [ ] 家长端实付订阅接入（真实支付通道，费率按通道确认）
- [ ] Web 端（仅聊天）复用 chat API
- [ ] 时长管控从「消息数近似」升级为真实使用时长统计
