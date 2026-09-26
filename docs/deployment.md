# 部署与运维

## 1. 配置项全表（`server/app/config.py`，全部环境变量）

| 变量 | 默认 | 说明 |
|------|------|------|
| `ENV` | `dev` | dev=固定短信码 123456 可用；prod 请务必切换 |
| `DATABASE_URL` | `sqlite:///./aizhuxue.db` | 生产用 `postgresql+psycopg2://…`（compose 已配） |
| `JWT_SECRET` | `change-me-in-prod` | **生产必须覆盖**，密钥管理服务注入 |
| `CORS_ORIGINS` | 空 | 生产 CMS 页面的完整 Origin；多个用逗号分隔 |
| `FORWARDED_ALLOW_IPS` | `127.0.0.1` | 使用反向代理时填可信代理 IP，由 Uvicorn 读取真实客户端 IP |
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
| `PRICING_BASE_MONTHLY_PRICE` | `66` | 首次初始化时的基础月费（元）；运行中以 CMS 数据库配置为准 |
| `PRICING_ADDITIONAL_SEAT_PRICE` | `33` | 首次初始化时的增量孩子名额价格（元）；运行中以 CMS 配置为准 |
| `PRICING_TRIAL_DAYS` | `30` | 首次初始化时的新用户试用天数 |
| `PRICING_POST_TRIAL_DAILY_FREE_COUNT` | `0` | 首次初始化时的到期后每日免费次数；老师角色开关仍由 CMS 控制 |
| `GUARDIAN_VERIFY_PROVIDER` | `mock` | 核验服务尚未接入；生产注册/登录接口暂返回 503 |

## 2. 本地开发

```bash
cd server
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/alembic upgrade head                       # 从零建库（全部 25 表）
.venv/bin/uvicorn app.main:app --port 8100          # SQLite + mock 核验
FENCE_QUIET_ENABLED=false .venv/bin/uvicorn app.main:app --port 8100   # 测试时段放开
```

测试与围栏评测：

```bash
cd server
.venv/bin/python -m pytest -q                        # 单元+端到端测试（109 例）
.venv/bin/python -m tools.eval_fence                 # heuristic 指标
FENCE_MODE=llm GLM_API_KEY=sk-… .venv/bin/python -m tools.eval_fence   # 验收形态
```

## 3. Docker 部署

```bash
cd product
JWT_SECRET=$(openssl rand -hex 32) CORS_ORIGINS=http://localhost:8101 GLM_API_KEY=sk-… FENCE_MODE=llm docker compose up -d --build
```

- `db`：Postgres 16 + 健康检查 + 数据卷 `pgdata`；
- `api`：等 db 健康后启动，8000 仅绑定 127.0.0.1；对外必须走 TLS（见下）；
- 短信尚未接入：`ENV=prod` 的监护人注册/登录接口返回 503；现有有效令牌仍可使用。正式开放前须接入一次性短信码验证。
- **时区**：日界与时段禁用按 `TZ_OFFSET_HOURS`（默认 8）换算，与容器时区无关，无需设置 TZ。

### 3.1 HTTPS / TLS（强制）

api/cms 端口已只绑 127.0.0.1，不再裸奔 HTTP。两种对外方式：

```bash
# 方式 A：内置 Caddy（ACME 自动签发续期，需公网域名 + 80/443 放行）
cd product
JWT_SECRET=$(openssl rand -hex 32) LLM_KEY_SECRET=$(openssl rand -hex 32) \
  API_DOMAIN=api.example.com CMS_DOMAIN=cms.example.com \
  GLM_API_KEY=sk-… FENCE_MODE=llm docker compose --profile tls up -d --build

# 方式 B：自备 Nginx/云 LB 做反代
#   - 反代到 127.0.0.1:8000（API）与 127.0.0.1:8101（CMS）；
#   - SSE 场景关闭代理缓冲（Nginx: proxy_buffering off；X-Accel-Buffering 已设）。
```

新增环境变量：`LLM_KEY_SECRET`（CMS 存入的 LLM api_key 落库加密密钥，未设置回落 JWT_SECRET；**一旦有分组配了 key 并上线，就不要再改**，否则密文不可解）。

## 4. Flutter 构建产物

```bash
# 学生端（applicationId com.aizhuxue.student）
cd app/app_student
flutter build apk --dart-define=API_BASE=https://api.example.com
# 家长端（applicationId com.aizhuxue.parent）
cd app/app_parent
flutter build apk --dart-define=API_BASE=https://api.example.com
flutter build ipa   # iOS：需开发者账号签名
```

## 5. 生产 Checklist（骨架 → 上线）

**工程**
- [x] Alembic 迁移链可用（`alembic upgrade head` 从零建出全部 25 表；表结构变更走新迁移文件）
- [ ] JWT_SECRET/LLM_KEY_SECRET/DB 密码/LLM Key 走密管，禁入 git
- [x] API 限流（/auth、/chat、/admin/login 共库分钟窗口；多进程生效）
- [ ] 请求日志 + 错误告警
- [ ] PostgreSQL 定期备份与恢复演练
- [ ] HTTPS（TLS 终结）：`--profile tls` Caddy 或自备反代；App 端证书校验
- [ ] 短信服务商接入 + 短信码频控（固定码仅 ENV=dev/test 生效；prod 注册未开放前返回 503）
- [ ] usage_logs → 成本看板（验证人均 token 假设）

**安全加固（2026-09-26 落地）**
- [x] prod 启动自检：JWT_SECRET/ADMIN_TOKENS 弱配置直接拒启
- [x] Admin 密码 pbkdf2（60 万轮，登录时自动升级旧 SHA256 账号）
- [x] Admin session token 12 小时过期
- [x] CMS/Web 前端全量输出转义（innerHTML XSS）
- [x] LLM api_key 落库加密（encv1 封装，密钥 LLM_KEY_SECRET；存量明文兼容读）
- [x] 家长端设备管理：`GET /parent/students/{id}/devices`、`POST .../devices/{id}/revoke`（踢出即 token_version+1）
- [x] 学生 token 强制携带设备信息，缺设备字段的旧 token 拒绝

**合规（依赖外部流程，见 compliance-design.md）**
- [ ] 三要素核验真实接入（阿里云/腾讯云开通）并留核验凭证
- [ ] 模型商书面确认未成年人服务许可
- [ ] App 备案 + 算法备案/安全评估（如法务意见认定需要）
- [ ] 《未成年人个人信息处理规则》、PIA 报告、监护人同意书上线（法务交付物）
- [ ] 公示所用已备案模型名称及备案号
- [x] 围栏离线验收报告（六组题库各 300 题，自动指标全部过线；真实模型评测仍需凭证后复跑）

**产品**
- [ ] 家长端实付订阅接入（真实支付通道，费率按通道确认）
- [ ] Web 端（仅聊天）复用 chat API
- [ ] 时长管控从「消息数近似」升级为真实使用时长统计
