# 部署与运维

本文提供通用部署与配置说明。实际生产环境地址、凭据、发布步骤及恢复资料由部署方在仓库之外单独保管，不随本仓库分发。

## 0. 后续 Agent 的执行入口（2026-10-23 同步）

- 本文是当前通用打包部署流程；家长构建行为见 `scripts/build_parent.py`，CI 环境见 `.github/workflows/ci.yml`。发布前先核对三者及目标渠道锁文件，不直接复制历史验收记录中的命令。
- 实际生产环境先读私有 [渠道与凭据说明](../../credentials/store-subscriptions.md) 和 [生产部署说明](../../credentials/production-deploy-gker.md)。当前生产使用什么进程管理、端口和配置文件，须以该环境的说明及只读检查结果为准；下方 Docker 示例不代表既有 systemd 环境的升级方式。
- 客户端正式构建必须显式设置远程 HTTPS `API_BASE`；默认值已改为 `http://127.0.0.1:8100`。宿主机环境变量不会自动成为 Dart define，直接执行 Flutter 时必须传 `--dart-define=API_BASE=...`。
- 服务端更新：核对目标提交与现有版本 → 比较依赖和迁移 → 备份并确认恢复方式 → 按该环境流程发布 → 检查健康、迁移版本和关键业务。依赖有变化时必须安装当前 `server/requirements.txt`；不能只切换源码并复用未更新的虚拟环境。保留现有 `JWT_SECRET`、`LLM_KEY_SECRET`、`STORE_TOKEN_SECRET`，不要套用首次部署示例重新生成。
- systemd 环境还须先只读核对每个服务实际生效的 `ExecStart`、`WorkingDirectory`、`User`、`EnvironmentFiles` 和 `DropInPaths`。API/CMS 可能使用不同虚拟环境，依赖安装及迁移必须指向本次选定的实际环境；依赖变化时优先创建独立新环境并保留旧环境供回滚。切换时保留原启动参数和环境文件，确认所有 drop-in 合并后使用了预期环境，不能只改工作目录或向历史共享 venv 安装依赖。
- 图片功能新增配置、字体挂载、迁移和启用顺序见 [图片部署说明](image-feature-deployment.md)。客户端还需验收隐私政策链接、首次选择“仅必要功能”、家长/学生设置撤回授权及统计/诊断停止收集。

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
| `PRICING_POST_TRIAL_DAILY_FREE_COUNT` | `0` | 旧配置兼容字段；实际免费次数按 CMS 中各老师分组配置 |

## 2. 本地开发

```bash
cd server
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/alembic upgrade head                       # 从零建库（完整表结构）
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

### 工具链与依赖

以下命令均从 `product/` 根目录开始。工具链必须与目标工程已提交的锁文件配套：家长微信 / 家长 App Store 使用 **Flutter 3.32.8**；三个学生入口与家长 Google Play 使用 **Flutter 3.38.10**（Dart 3.10）。锁文件中的 `flutter_test` 间接依赖也受 Flutter 版本约束，不能把所有渠道统一切到某一版本。CI 当前也分配不同版本，但没有覆盖所有学生渠道，发布应按下表逐个验证。

```bash
export FLUTTER=/path/to/flutter-3.38.10/bin/flutter  # 按目标渠道选择，见下表
export PUB_HOSTED_URL=https://pub.flutter-io.cn
"$FLUTTER" --version
```

`PUB_HOSTED_URL` 须匹配已提交锁文件中的源地址（CI 已设置同一值）。每个目标工程先运行 `flutter pub get --enforce-lockfile`；离线且缓存齐备时可加 `--offline`。失败须检查 Flutter 版本、源地址及锁文件，不通过删除锁文件或普通 `pub get` 绕过。新增共享依赖时，更新所有受影响渠道的锁文件并分别验证；本轮 `url_launcher` 已同步两个学生渠道。

iOS 构建前显式选择本机已安装的 **Xcode 16** 并检查，CI `store-ios` 也会选择 Xcode 16：

```bash
export DEVELOPER_DIR=/Applications/Xcode_16.2.app/Contents/Developer  # 改为实际安装路径
xcodebuild -version
```

正式包还需有效签名与对应渠道配置。CI 的 `--debug --no-codesign` 仅验证编译；无商业 SDK 的 iOS 调试包会降级为短信登录，不代表正式一键登录可用。

### 渠道入口与正式构建

| 目标 | 工程 | Flutter | 构建入口 |
| --- | --- | --- | --- |
| 国内学生 Android | `app/app_student` | 3.38.10 | `flutter build apk --release` |
| 学生 Google Play | `app/app_student_googleplay` | 3.38.10 | `flutter build appbundle --release` |
| 学生 App Store | `app/app_student_appstore` | 3.38.10 | `flutter build ipa --release` |
| 家长微信 | `app/app_parent_wechat` | 3.32.8 | `python3 scripts/build_parent.py wechat` |
| 家长 Google Play | `app/app_parent_googleplay` | 3.38.10 | `python3 scripts/build_parent.py googleplay` |
| 家长 App Store | `app/app_parent_appstore` | 3.32.8 | `python3 scripts/build_parent.py appstore` |

家长共享库 `app/app_parent` 不可直接打包。家长脚本读取并传入环境中的 `API_BASE`、`PRIVACY_URL`、`TERMS_URL` 及该渠道认证参数：国内为 `ALIYUN_AUTH_SDK_KEY`，Google Play 为 `GOOGLE_SERVER_CLIENT_ID`（须与服务端 `GOOGLE_LOGIN_CLIENT_ID` 配套）；微信还需 `WECHAT_APP_ID` 与工程配置一致。App Store / Google Play 正式家长包要求 HTTPS 政策地址。真实签名与密钥加载见 [渠道构建与密钥加载](../../credentials/store-subscriptions.md#从私有-credentials-加载号码认证-key)。

学生端示例（先加载部署方确认的真实 `API_BASE`；按上表替换目标目录和构建类型，Google Play 与 iOS 不使用国内工程代替）：

```bash
(
  set -e
  : "${API_BASE:?先设置生产 HTTPS API_BASE}"
  cd app/app_student
  "$FLUTTER" pub get --enforce-lockfile
  "$FLUTTER" build apk --release --dart-define=API_BASE="$API_BASE"
)
```

学生海外包直接构建时还须传入 `--dart-define=PRIVACY_URL="$PRIVACY_URL"`，使用部署方确认的 HTTPS 政策地址。正式发布前检查 Android 签名配置、iOS 签名、包名、版本及构建号，确认版本高于已发布版本。

### iOS 家长商业 SDK 与产物检查

`ATAuthSDK_D.xcframework` 已从 Git 移除并被忽略。正式包必须准备官方 SDK，将其放在 `app/app_parent_appstore/ios/Vendor/`，或设置 `ALIYUN_AUTH_IOS_SDK_PATH` 指向该 `.xcframework`；不要依赖脚本对本机历史发布目录的兜底搜索。客户端 SDK Key 仍需匹配 Bundle ID。

`build_parent.py appstore` 会注入 SDK、检查 `ATAuthSDK.bundle`、执行 `pod install --repo-update` 后再构建 IPA，避免先构建无 SDK 调试包导致 Pods 缓存漏装。不能直接 `flutter build ipa` 绕过该流程。脚本还会清理对应旧输出目录，构建后扫描异渠道 SDK、已知编译桩及正式 SDK 资源包；必须使用本次成功命令输出的产物路径。

家长 Android 脚本正式输出 AAB；国内若需 APK，须在对应渠道工程中显式传入生产 API、认证 Key 和微信 AppID，再返回 `product/` 运行 `python3 scripts/build_parent.py wechat --artifact <本次APK路径>` 校验。独立检查现有产物使用 `--artifact`，不能只运行 `--check`（后者只检查依赖）。学生 Google Play 产物另运行 `python3 scripts/check_telemetry.py app_student_googleplay --artifact <本次AAB路径>`，检查 Firebase 渠道隔离；该脚本不校验签名，签名需单独核验。学生 iOS 须检查实际签名包并完成设备验收。

### 4.1 国内 Android APK 发布

国内学生端和家长端的 APK 统一上传七牛对象存储，经 CDN 分发；国内官网的所有 APK 按钮直接使用对应版本的 CDN HTTPS 地址，不再把 APK 上传到官网服务器。国内官网首页与“家庭使用”区域的按钮须同时更新。Google Play 渠道沿用独立发布流程。

发布顺序：

1. 构建使用正式签名及生产配置的国内 APK，记录包名、版本、文件大小、签名指纹与 SHA-256。
2. 使用私有 Qshell 账户上传至七牛，按渠道和版本保存新对象；不覆盖旧版本文件，也不在仓库保存七牛密钥。
3. 校验对象与本地产物一致，并通过 CDN HTTPS 完整下载核对 SHA-256、大小及 Range 206；检查官网 Referer 可访问。验收失败时保持原官网链接。
4. 备份线上页面，更新并部署官网所有学生端、家长端下载链接，再检查公网页面实际链接和下载响应。回滚时恢复上一版本页面链接，保留旧对象供回退。

生产空间、CDN 地址、Qshell 命令与证书续期步骤见私有[七牛发布说明](../../credentials/qiniu-release-20261019/README.md)。生产服务器的 `qiniu-cert-renew.timer` 每天两次检查续期；服务负责 HTTP-01 验证、上传证书、更新 CDN 绑定并核验公网证书。部署或验证失败时任务返回失败，下次运行重试；检查 `systemctl status qiniu-cert-renew.timer qiniu-cert-renew.service` 和对应 journal。证书、ACME 账户、七牛密钥与部署状态只保存在服务器私有目录，具体路径和恢复方法见私有说明。

## 5. 生产 Checklist（骨架 → 上线）

**工程**
- [x] Alembic 迁移链可用（`alembic upgrade head` 从零建出完整表结构；表结构变更走新迁移文件）
- [ ] JWT_SECRET/LLM_KEY_SECRET/DB 密码/LLM Key 走密管，禁入 git
- [x] API 限流（/auth、/chat、/admin/login 共库分钟窗口；多进程生效）
- [ ] 请求日志 + 错误告警
- [ ] PostgreSQL 定期备份与恢复演练
- [ ] HTTPS（TLS 终结）：`--profile tls` Caddy 或自备反代；App 端证书校验
- [ ] 短信服务商接入 + 短信码频控（固定码仅 ENV=dev/test 生效；prod 注册未开放前返回 503）
- [ ] usage_logs → 成本看板（验证人均 token 假设）

**安全加固（2026-09-26 落地）**
- [x] prod 启动自检：JWT_SECRET 弱配置直接拒启
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
