# 部署与运维

本文提供通用部署与配置说明。实际生产环境地址、凭据、发布步骤及恢复资料由部署方在仓库之外单独保管，不随本仓库分发。

## 0. 后续 Agent 的执行入口（2026-10-24 同步）

- 本文是当前通用打包部署流程；家长构建行为见 `scripts/build_parent.py`，CI 环境见 `.github/workflows/ci.yml`。发布前先核对三者及目标渠道锁文件，不直接复制历史验收记录中的命令。
- 实际生产环境先读私有 [渠道与凭据说明](../../credentials/store-subscriptions.md) 和 [生产部署说明](../../credentials/production-deploy-gker.md)。当前生产使用什么进程管理、端口和配置文件，须以该环境的说明及只读检查结果为准；下方 Docker 示例不代表既有 systemd 环境的升级方式。
- 各渠道版本号一致性原则：除非特殊说明，最新发布版本的各个渠道版本号（version name）尽量保持一致。例如国内包是 1.0.3，则 Google Play 即使历史版本是 1.0.1 也应同步对齐至 1.0.3，反之亦然；构建号（versionCode / build number）按各渠道各自历史记录严格递增，且必须高于各渠道/商店已发布的最大版本。
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

以下命令均从 `product/` 根目录开始。工具链必须与目标工程已提交的锁文件配套：家长微信 / 家长 App Store 使用 **Flutter 3.32.8**；三个学生入口与家长 Google Play 使用 **Flutter 3.38.10**（Dart 3.10）。锁文件中的 `flutter_test` 间接依赖也受 Flutter 版本约束，不能把所有渠道统一切到某一版本。正式发布按下表逐个验证，不从 CI 的测试矩阵推导发布工具链。

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

### CI 与正式发布校验的区别

以下为当前 `.github/workflows/ci.yml` 的实际检查范围，不是正式发布命令：

| CI 任务 | 当前工具链与依赖解析 | 发布时仍需单独完成 |
| --- | --- | --- |
| `app` 测试矩阵 | 家长 Google Play 使用 3.38.10，其余矩阵工程（含国内 `app_student`）使用 3.32.8；运行普通 `flutter pub get` | 按发布渠道表使用对应 Flutter，对已提交锁文件执行 `--enforce-lockfile`；不得把 CI 中重新解析依赖当作发布锁文件已通过 |
| `store-ios` | 家长 App Store 使用 3.32.8、严格依赖解析、Xcode 16 和无签名 debug 构建 | 正式签名、官方号码认证 SDK 注入及实际 IPA 验收 |
| 学生 Google Play / 学生 App Store | 两个独立渠道壳尚未纳入上述矩阵 | 使用 3.38.10 分别严格解析依赖、构建及验收渠道产物 |

国内学生端的 CI 测试工具链目前与发布工具链不同。CI 绿灯不能代替 Flutter 3.38.10 下的发布依赖验证；也不能为匹配 CI 而降级发布工具链、改写锁文件或跳过检查。此处只说明现有 CI 的边界，不表示 CI 已与全部发布渠道对齐。

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

**两个 Google Play 渠道在构建前都必须准备各自的 Firebase 配置 JSON**，包括调试构建；完整说明见 [私有配置与构建](telemetry.md#私有配置与构建)。默认位置相对 `product/` 如下：

| 渠道 | 配置文件 | JSON 中须包含的 Android 包名 |
| --- | --- | --- |
| 家长 Google Play | `../credentials/firebase/parent-google-services.json` | `com.aizhuxue.parent.play` |
| 学生 Google Play | `../credentials/firebase/student-google-services.json` | `com.aizhuxue.student.play` |

若文件位于其他目录，在该次构建的环境中设置 `FIREBASE_CONFIG` 为对应 JSON 的绝对路径，并确认文件可读、包名匹配；切换家长/学生构建时须同步切换该变量，不能沿用另一渠道的 JSON。该变量由 Gradle 读取，不是 Dart define。不要把 Firebase Android 配置与后端 Google 服务账号私钥混用，后者不得打入 App；这些私有 JSON 均不提交 Git。仅依赖解析通过或 Google OAuth 配置齐备，不能代替这一步。

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

学生海外包直接构建时还须传入 `--dart-define=PRIVACY_URL="$PRIVACY_URL"`，使用部署方确认的 HTTPS 政策地址。正式发布前检查 Android 签名配置、iOS 签名、包名、版本及构建号：除非特殊说明，各渠道展示版本号尽量同步保持一致（如国内包发布 1.0.3，Google Play 等其他渠道即使前版为 1.0.1 也应同步对齐为 1.0.3），构建号确认严格递增且高于该渠道已发布版本。

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
- [x] 海外 Web 双端生产发布、真实 Google 与合成学习流程联调；Android 模拟器补充验证完成范围见 [Web 验收记录](web-acceptance.md)；物理设备仍待验收
- [ ] 时长管控从「消息数近似」升级为真实使用时长统计

## 6. Google Play 海外双端 Web

源码为 `web/`，复用本服务，不增加 Node 业务后端。订阅页只读展示已核验权益和购买来源，网页支付未接入；不得把开发 mock 购买开放给网页。

2026-10-25：新增默认关闭的 Paddle Sandbox 接入，已在本地隔离家庭验收真实测试卡购买与签名回调，详见 [Paddle Sandbox](paddle-sandbox.md)。新增线上固定付款链接、Sandbox 专用测试家庭名单及家长 CSP 部署步骤；线上已仅对指定测试家庭启用 Sandbox，真实收款保持关闭；发布结果见私有生产记录和公网检查。

2026-10-26：Creem Test Mode 备用支付接入流程见 [Creem 测试支付](creem-test.md)。仅指定测试家庭可见，正式收款保持关闭；部署前后状态以私有生产记录为准。

家长 Web Firebase Analytics：构建前从私有 `credentials/firebase/parent-web-config.json` 注入 `PARENT_FIREBASE_CONFIG`（JSON，必须是 Web App 的 `apiKey/appId/projectId/measurementId`），不要使用 Android 配置或管理员私钥；本地可写入忽略的 `web/.env.parent.local`，示例见 `web/.env.parent.example`。SDK 及 gRPC 安全修复覆盖版本已锁定在 `web/package-lock.json`，按 `npm ci` 安装，不复用旧依赖目录。配置缺失时统计入口和收集都关闭，字段不完整时构建失败；学生构建始终不包含 Firebase 配置/SDK。独立云端 Web 数据流已建立并确认增强型衡量关闭，本地测试事件已抵达 DebugView；2026-10-26 已随 `13b2537` 配套发布 API/CMS、家长及学习站静态页面。

上线时仅对家长 CSP 增加 `web/Caddyfile` 中明确列出的 gtag 脚本、Analytics 收集及 Firebase Web 配置/安装请求域名，学生 CSP 保持原样。检查实际生效代理（包括跨机两跳）与模板一致，并同步国际官网完整隐私政策中的 Web Analytics、浏览器标识、用途、可撤回授权和 Google 数据处理说明；家长 Web 内的隐私说明已同步。发布后验证：首次/拒绝时无 Firebase 请求；同意后固定事件到达独立 Web 数据流；页面/支付回跳的 query、hash 和资源 ID 不出现在事件参数；撤回和跨标签页同步立即停止；学生产物无 Firebase SDK/数据流标识。埋点事件口径、同意样本限制与测试命令见 [埋点说明](telemetry.md#家长-web-firebase-analytics2026-10-26)。本改动无数据库迁移，但 Web 注册事件需配套启用带 `is_new_user` 的登录响应，旧响应按非新用户处理。

服务端/学习站运营统计（2026-10-26）：新增迁移 `2e5f7a9b1c3d`，按当前环境先迁移及发布 API，再发布 Web 和 CMS。服务端、学习站不设同意门槛；家长 Web 保留同意控制。没有新的第三方密钥或学习站 CSP 域名。CMS 概览新增管理员专用漏斗查询，事件与成熟 cohort、支付证据缺口及上线验证见 [运营统计](operations-analytics.md)。本次无历史回填；2026-10-26 已随 `13b2537` 上线，国际官网七语完整隐私政策同步披露第一方统计范围。

孩子独立学习管控（2026-10-26 发布）：新增迁移 `3f6a8b0c2d4e`，为学生保存学习时长、每日提问上限、休息时段和学习引导通知偏好。Web 孩子详情及学习安排均保存到 `/parent/students/{id}/learning-settings`；首页剩余时长、学生 availability 和服务端校验使用对应孩子配置。未单独设置的孩子沿用旧家庭默认值；首次保存完整快照后不再随旧家庭默认值变更。旧 `/parent/settings` 兼容接口保留，安全通知不可关闭。先升级服务端/数据库，再切换 Web；本次移除家长 Web 的 AI 用量面板及请求，不删除后台用量账本。

### 品牌与当前域名（2026-10-24 已上线）

英文品牌为 **AI StudyNest**。海外官网由旧域名迁移至 `https://aistudynest.com`；家长站为 `https://parents.aistudynest.com`，学生站为 `https://learn.aistudynest.com`。两站 Cookie 保持 host-only，不设置父域 Domain。

当前生产配置为 `WEB_PARENT_ORIGIN=https://parents.aistudynest.com`、`WEB_STUDENT_ORIGIN=https://learn.aistudynest.com`；本地开发 Origin 保持 localhost。Google OAuth 的 JavaScript 授权来源配置为家长站 Origin，品牌名称改为 AI StudyNest；学生站不注册 Google 登录。Google Play 官网入口配置已随双站上线，源码位于外层 `site/googleplay/web-entrypoints.json`。后续发布须核对入口仍指向这两个 Origin。

三站 DNS/TLS、家长 Google OAuth 与真实登录已验证。下表为当前域名职责，后续发布仍须核对实际运行配置；不要把历史迁移步骤当成尚未完成的待办。

| 入口 | 当前职责 |
|---|---|
| `https://aistudynest.com` | Google Play 渠道官网、双端入口、隐私与条款；同时承载受限验单中继及通知路由 |
| `https://parents.aistudynest.com` | 家长 Web、Google 登录、家庭与学习管理、只读订阅权益 |
| `https://learn.aistudynest.com` | 学生 Web、连接码绑定、同源学习与私有媒体；不加载 Google 登录或支付 |
| `https://i.lix.do` | 已退役，所有入口返回 410，不代理或重定向 |

`GOOGLE_GATEWAY_URL=https://aistudynest.com`；`GOOGLE_PUBSUB_AUDIENCE`、Pub/Sub push endpoint 与 OIDC audience 均为 `https://aistudynest.com/payments/googleplay/notify`。官网 `/google/request`、`/google/certs` 保持主 API 来源限制及共享凭据鉴权，通知保留 Google OIDC 验签。新链路已通过认证测试推送，旧路由不再保留；具体主机、密钥与恢复材料只在私有生产说明中维护。域名迁移涉及原生包中的政策链接时，按对应渠道正式构建流程更新，不修改已有 APK；本轮未重新打包原生 App。

### 构建与本地验收

家长话题限制记录（2026-10-27）：先发布支持 `/parent/conversations/{id}/fence-events?final_only=true` 的 API，再构建发布家长 Web。最终结果视图只返回 policy、parent_keywords、output_check 的 allow/rewrite/reject；同一消息保留最后一条处置，无消息关联的旧记录分别保留。默认 API 仍返回完整流水，不删除或重写原始数据。分类、上下文检查等中间状态不作为最终结果。无新增依赖、环境变量或迁移；验收分类隐藏、重试/宽松策略覆盖、违禁词和输出拦截、空结果及家庭权限隔离。回退先恢复家长静态 root，再恢复 API 发布路径，保留数据库。

学生 Web 老师头像（2026-10-27）：聊天顶部、老师列表和回答区域使用 CMS 上传头像的 `/api/browser/student/api/teacher-avatars/{filename}` 同源路径，不直接请求配置中的跨域 URL，不放宽 CSP。文件名沿用服务端的 32 位十六进制及 png/jpg/webp 校验；未配置、不支持的外链或加载失败时回退默认图标。旧会话优先展示可见老师当前头像，老师不可见时使用会话快照。此更新仅需构建与发布学生 Web，无 API、依赖、环境变量或迁移变更；发布前验证带会话的头像读取、历史与新会话、切换老师和失败回退，保留旧哈希资源，回退只恢复学生站静态 root。

老师身份与图片状态修复（2026-10-27）：先发布 API 的聊天提示词，再发布家长、学生 Web（共用 `MessageCard`）。Gemini、ChatGPT、Claude 的老师身份取自会话名称快照，自我介绍遵循客户端当前回复语言，名称不翻译；不改写历史回答或模型配置。图片任务 `skipped` 不显示错误，只有 `failed` 显示失败提示，默认本地化提示不再次交给翻译函数。本次无新增依赖、环境变量或数据库迁移；按实际运行目录核对差异，保留已有模型凭据、系统配置及旧哈希资源。验证普通/流式聊天的身份与语言、历史会话中跳过配图不出现错误、中英文真正失败时仍显示图片提示。回退只恢复本次 API 发布路径和双端静态 root，不恢复数据库。

```sh
cd web
npm ci
npm run build
npx playwright install chromium webkit
npm test
```

锁文件为 `web/package-lock.json`。Node 使用 Vite 8 支持的版本（20.19+、22.12+；本次开发使用 26.4）。产物分别为 `web/dist/parent/`、`web/dist/student/`。构建不读取或打入私钥；Google Web client ID 由已确认的后端配置经 `/browser/parent/config` 提供。

Playwright 自启隔离的 8810 测试 API，以及 5173/5174 前端；端口占用时直接报错，不复用现有服务。测试夹具替代 Google 身份验证、模型和私有图片外部服务，因此仍需验收真实 Google OAuth、存储审核和模型配置。验收详情及未完成项见 [Web 验收记录](web-acceptance.md)。

本地生产构建 HTTPS 验证：安装独立 Caddy 2.11+ 后运行 `CADDY_BIN=/absolute/path/to/caddy npm run test:https`。该流程使用临时证书、隔离数据库和实际代理模板，端口为 18443/19443/18811/8810，不安装系统 CA；身份、模型和图片依赖仍使用夹具。它验证本地网关，不代表公网部署或真实 OAuth 已通过。详见 `web/README.md`。

### 生产必需配置

| 配置 | 要求 |
|---|---|
| `WEB_ENABLED` | 默认 false；完成迁移、代理和 OAuth 核对后启用 |
| `WEB_PARENT_ORIGIN` | 家长站真实 HTTPS Origin，不含路径、查询串或片段 |
| `WEB_STUDENT_ORIGIN` | 学生站真实 HTTPS Origin；必须与家长站不同 |
| `WEB_SESSION_HOURS` | 默认 168；会话有服务端到期与撤销，Cookie 为 Secure/HttpOnly/host-only/SameSite=Strict |
| `GOOGLE_LOGIN_CLIENT_ID` | 已核实的 OAuth Web client ID；Google 控制台允许家长 Origin，继续严格校验 audience |
| 图片配置 | 沿用当前图片部署说明；学生上传、审核后读取经学习站同源代理，不重定向到存储域名 |

迁移新增 `families.timezone`、前一时区与切换时间，以及 `web_sessions`。未配置家庭继续沿用 `TZ_OFFSET_HOURS`，已有原生 App 不改认证协议；Web 连接前须由家长确认 IANA 时区。切换最多每日一次，首个新学习日延续已用额度，历史时长记录不改名、不复制为新消费。时间戳仍为 UTC，日界通过 IANA 时区处理夏令时。

应用与 Alembic 的 PostgreSQL 连接均固定会话时区为 UTC，避免服务器本地时区重新解释旧调用方写入的无时区 UTC 时间。上线前核对历史写入约定、数据库会话时区和样本时间戳；此次改动不重写历史时间数据。家庭时区仅用于业务日界与显示，不用作数据库连接时区。

`web/Caddyfile` 是双站模板，导入前设置：两端的真实 Origin、`WEB_PARENT_ROOT`/`WEB_STUDENT_ROOT`（本次构建的绝对目录）、`WEB_API_UPSTREAM`（已核实 API 上游）。代理必须保留真实 Host，分别只开放 `/api/browser/parent/*` 与 `/api/browser/student/*`，剥离 `/api` 后转发；关闭 SSE 缓冲。普通静态路径回退到该角色的 `index.html`，不得把另一角色或原生 API 整体暴露到学习站。模板含角色独立 CSP，学生站仅允许本站脚本、字体及私有图片。

两处反向代理均显式设置 `header_up Host {hostport}` 和 `flush_interval -1`。Caddy 2.11+ 对 HTTPS 上游默认改写 Host；浏览器后端依赖原始角色 Host 校验，因此不能省略该覆盖。参见 [Caddy HTTPS 上游说明](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy#https)。

Google Play 官网源码在仓库外层私有 `site/googleplay/`，不加入开源 `product` 仓库。其双端链接由同源 `/web-entrypoints.json` 配置，格式为 `{"parent":"家长站真实 HTTPS Origin","student":"学生站真实 HTTPS Origin"}`。两端必须是不同 Origin；未配置时入口隐藏，不能用示例域名或历史 API 地址代替真实配置。与本次构建一起检查入口实际跳转、深链接刷新和浏览器会话。

国内私有官网已在源码中移除旧 Web 入口、使用步骤与现行政策范围中的 Web 描述。API `/web` 固定返回 410，旧内嵌页面已删除；国内服务器曾配置的 `/ai-zhuxue/` 等别名还须按真实反代配置返回 410，并刷新缓存。不能删除 App 使用的 `/chat`、`/auth`、`/parent` 等业务 API，也不能把国内 token 自动转到海外站。

后续更新仍按本文件第 0 节读取私有生产说明、核对真实环境、备份数据库与保留原密钥，再执行迁移与站点切换。2026-10-24 经用户批准已完成首次生产启用、迁移与真实 Google/合成学习流程验收；这不代替 iPad/Android 真机与真实网站白名单验收。

### 跨机 HTTPS 上游

静态站与 API 反代位于不同主机时，不能直接把站点 Host 发往只接受 API 域名的中间 Caddy：第一跳的 Host/TLS SNI 应匹配已确认的 API 域名；第二跳仅接受已确认静态站节点的源 IP，并按 `/browser/parent/*` 与 `/browser/student/*` 分别将 Host 还原为对应站点主机名，再转发至 loopback API。未匹配的 `/browser/*` 返回 404；原生 API 路由保留。多组 `handle` 使用 `route` 保持明确顺序，避免通用拒绝规则抢先匹配。

站点入口代理使用 Caddy 默认行为丢弃不可信客户端提供的 X-Forwarded-*；中间 API 代理仅对受源 IP 约束的角色路由转发该客户端地址，避免所有家庭共享节点 IP 的限流桶。两跳都关闭 SSE 缓冲。不要在通用 API 路由信任任意客户端提交的转发头。实际节点、候选文件、数据库备份和切换脚本保存在私有生产说明；新代理先校验、备份，先切换 API 并验证迁移/健康，再启用静态站，最后检查 TLS、跨角色隔离、真实 Google 登录和当前验单健康。

### 2026-10-24 已上线与真实回归

官网及双端 HTTPS 已在用户批准后启用；生产 Web Origin 使用上述确定域名，数据库当前迁移 `0c3e7a9b2d41`。API 保留现有 systemd/虚拟环境和密钥，CMS 保留原发布；两跳角色代理、当前验单路由及备份恢复方式见私有生产说明。不可从本段跳过运行状态检查直接复用历史发布包。

真实 Google 登录、家庭/试用权益、学生连接、真实流式/公式/识图/图示、反馈/收藏/奖励、成绩/评估/导出和重绑失效已有线上证据。上线后修复 TeX 分隔符兼容、图示形状标签、含反馈奖励的孩子彻底删除与横屏输入区，专门回归和实际输出均已核验。支付仍关闭；原生 App 未重打包。物理设备按用户要求暂缓验收；母语审校、目标市场性能与评估分类局限见 [Web 验收记录](web-acceptance.md)。

### 2026-10-24 验单域名全量切换

用户确认旧路由没有实际订单后，Google 验单中继、公钥读取及 Pub/Sub authenticated push 已统一迁至 AI StudyNest 官网 Origin。主 API 的 `GOOGLE_GATEWAY_URL`、`GOOGLE_PUBSUB_AUDIENCE` 与 Pub/Sub 的 push endpoint / OIDC audience 必须一致更新；实际值与备份位置见私有生产说明。验单路径保持主 API 来源 IP 限制及共享凭据鉴权，通知保持原始 Google OIDC 验签；没有放宽接口。

已核实新端点 Google 公钥 200、无凭据 401、跨包操作 403、合成无效令牌 400 invalid、真实 Pub/Sub 认证测试推送 200。旧域名仅返回 410，不代理或重定向；当前调用方不再使用旧域名。官网、家长站、学生站与 API/CMS 健康复核通过。此变更不启用 Web 支付，也不代表真实订单购买验收；本轮没有代码、依赖或数据库迁移变更。

### 联系方式静态更新

2026-10-24：双端帮助/隐私/条款窗口与 Google Play 渠道官网三页页脚加入用户指定的联系邮箱链接，支持七语标签。静态构建与当前站点单独部署，保留现行验单、下载及角色代理；不因官网源码存在其他任务修改而整站覆盖发布。生效目录和恢复文件见私有生产说明。

### 国内与国际官网法律页面独立维护

两站的隐私政策和使用条款分别维护，不共用法律正文，不介绍或对比另一版本。站点信息、支持邮箱、登录方式、支付渠道和 SDK 数据处理说明必须与本站实际提供的服务一致；国际站保留适用的 Google 登录与 Firebase 披露，国内站不包含国际版本的披露。第三方服务的处理地区说明仍按实际情况保留，不因站点分离而删除。

| 官网 | 私有源码（仓库外层） | 隐私政策 / 使用条款 | 支持邮箱 |
|---|---|---|---|
| 国内 `https://gker.net` | `site/` | `/privacy/`、`/terms/` | `support@gker.net` |
| 国际 `https://aistudynest.com` | `site/googleplay/` | `/privacy/`、`/terms/` | `support@aistudynest.com` |

修改时同步各站法律 HTML 与各自 `assets/i18n.js` 的七语文案、标题、摘要、更新日期和正文/页脚邮箱；相对链接与 canonical 只指向本站。变更翻译脚本时更新引用它的三页缓存版本号，避免客户端继续加载旧的混合文案。两套官网源码由外层私有工作区管理，`product` 仓库不包含 `site/`，不能只发布本部署文档而漏传静态文件。

本地分别运行 `python3 site/scripts/check_site_i18n.py`、`python3 site/googleplay/scripts/check_site_i18n.py`（从外层工作区执行），并检查两站隐私/条款在全部七语下的标题、适用范围、登录/支付/统计说明、邮箱链接与页面跳转。国内页面不得出现国际品牌、国际域名或国际支持邮箱；国际页面不得出现国内版本说明、国内官网域名或国内支持邮箱。

生产发布前按第 0 节读取私有生产说明，确认两个域名各自实际生效的静态根目录并分别备份。以现行线上文件建立候选，仅合入本次核对过的 HTML/翻译改动；`site/` 上传不得递归混入 `site/googleplay/`，国际目录也不得用国内目录覆盖。保持现行下载、验单/通知路由及家长/学生站代理配置。发布后分别检查两域名的 `/privacy/`、`/terms/` 与翻译脚本响应、canonical、七语正文和所有支持邮箱，确认刷新缓存后生效；失败时恢复对应站点的备份。发布结果、产物摘要及备份位置记录在私有生产说明中。

2026-10-26 法律文案已发布（配套 `13b2537`）：国际官网七语 AI 说明更新为 ChatGPT（OpenAI）、Claude（Anthropic）、Gemini（Google）等能力，并注明以实际启用配置为准及必要接入/托管/传输处理，不将展示名称等同于线路已切换。隐私政策与条款日期更新为 2026-10-26，三页翻译脚本缓存版本同步。Web 双端 78 语种同步模型说明，联系邮箱所在帮助/法律弹窗补齐站内隐私与条款入口；学生站不新增外域依赖。国际官网邮箱页脚原有两项法律链接已核对保留。官网私有源码的本次差异保存在仓库外 `credentials/international-legal-20261026.patch`，不能漏掉这些静态文件，仅发布 product 并不会更新国际官网。

2026-10-26 发布验收：API/CMS 使用实际运行目录构建增量候选，保留既有 import 位置修复、启动参数、环境覆盖及支付测试名单。核验依赖未变并通过 `pip check`；备份数据库后执行 `0c3e7a9b2d41` → `1d4e6f8a0b2c` → `2e5f7a9b1c3d`，同时上线前一提交的剩余试用时长策略。PostgreSQL 事件写入/幂等/报表探针通过并回滚合成数据。两服务 active、NRestarts=0，最近错误日志为空。Web 从准确提交干净副本 `npm ci` 构建，学生包不含 Firebase，保留旧哈希资源；国际官网仅替换本次四个文件，Caddy 仅切三处 root 与家长 Firebase CSP，学习站 CSP 保持同源。公网三站入口、法律页面和脚本摘要与候选一致，七语隐私/条款模型名称及 Web 联系邮箱旁法律入口经浏览器核对，家长拒绝统计时未加载 Firebase 脚本。原生安装包未重建，真实付款未重测；静态政策更新不切换模型线路。数据库备份、候选与回退配置、线上回执和证据保存在私有生产说明及 `credentials/analytics-legal-release-20261026/`。回退代码保留增量 schema，不以旧备份覆盖新业务数据。

### 静态传输与会话失效复核

2026-10-24：双端 Caddy 对 /assets/* 启用 zstd/gzip，动态接口与 SSE 不套用静态压缩；发布后核对压缩响应解码字节与检查过的 dist 一致。模板与双引擎 HTTPS 网关回归覆盖静态内容可读、安全 Cookie 和及时 SSE。会话运行时失效及初次加载401均清理当前标签页私有草稿；有效会话刷新仍恢复草稿，无关偏好保留。用户已暂缓物理设备验收，后续恢复时按 Web 验收记录继续。

### 学生端与家长端 78 个语言选项

语言清单统一由 `server/app/locales.json` 维护，原生名称、地区区分、RTL、译文位置和校对边界见 [语言支持说明](languages.md)。Web 构建会生成独立语言资源，首屏和切换仅加载当前语言，发布时须带齐整个 `dist` 中的语言资源。Web 和服务端需配套发布：先启用允许全部语种的服务端，再切换家长/学生静态站，避免新前端请求被旧接口拒绝。此次不新增依赖或数据库迁移；原生 App 源码同步提交，安装包仍按对应渠道单独构建发布。

发布前核对新旧目录中的依赖和文件摘要。基于当前生效版本建立独立候选，只替换本次核对过的语言模块、Schema、分类提示与两个语言 JSON，保留线上其他修复。备份当前 API 启动配置、静态代理配置和数据库，核验恢复材料；服务端使用原环境和密钥。切换后检查 78 个规范标签及地区别名、双端语言切换与持久化、RTL、登录状态和普通/流式聊天语言传递。新增译文是机器翻译，部分地区共用基础译文，母语校对单独跟进。

### Web 登录页配置加载与重试

家长站仅在登录配置加载失败时显示配置“重试”；重试期间显示加载状态，成功后移除错误和重试入口。Google 登录 SDK 加载失败时由登录组件提供独立重试。学生站不请求无用的 Google 登录配置。

登录页静态修复须从已提交、已推送的目标版本构建，并按 `web/package-lock.json` 执行 `npm ci`，不能将并行工作区的未发布改动混入产物。运行 `npm run build` 和 `npx playwright test tests/auth.spec.ts`，覆盖正常加载、配置失败恢复及 SDK 失败恢复。部署前读取实际生效的静态根目录和代理配置，保留当前版本及配置恢复点；只切换本次角色站点，发布后核对公网资源摘要、Google 登录按钮及异常重试行为。

### 评估规则与缓存版本

2026-10-24：学业分类区分已覆盖的回答语言指令与实际语言课程，规则更新时同步递增输入版本，避免家长/学生复用旧快照。历史快照保留，仅重新生成时使用新版本。评估日期按完整业务日包含首尾两天，起止相同合法，倒序或无效日期仍拒绝。此改动无迁移/依赖变更；生产更新前校验原文件摘要，备份当前代码配置和数据库，切换后检查健康与当前部署代码的隔离canary。

### 学习链路耗时（2026-10-26 发布）

新增迁移 `4a7b9c1d3e5f`（接在孩子学习设置迁移 `3f6a8b0c2d4e` 后），先 API/CMS、再学生 Web 与学习站 Caddy；透传 trace 和 Server-Timing，仅学习站外层增加 upstream 响应头计时。`PERFORMANCE_NODE=primary`、`PERFORMANCE_VARIANT=baseline` 为默认标记，不改变路由。指标定义、分位数比较方法、配对缺样及容量限制见 [学习链路耗时分析](performance-analytics.md)。发布后先收集 baseline；新增埋点不代表已经测得减少一层服务器的提速。

### 界面文案校订发布（2026-10-26）

文案提交 `5249742` 已发布 API、CMS 和 Web 双端；本次按用户要求继续发布其余孩子独立学习设置与链路耗时功能。原生翻译源码已提交，不重新打包或上传商店。其余 75 个语言/地区版本已调整高频标题与术语，并修正部分误译和 DELETE 确认词；长说明、支付、隐私、安全及低频提示尚未全部完成逐条校订，不将技术检查通过视为母语人工审校完成。

本次完整发布先备份并升级两项增量迁移，再切换 API/CMS，最后发布双端静态和学习站最外层 Server-Timing 响应头。依赖不变，保留现行环境、密钥、官网、支付代理和角色隔离；回退仅恢复本次服务目录和静态 root/响应头，保留增量 schema，不恢复旧数据库覆盖新增业务。

完整功能提交 `a0d3d93` 已完成上述部署，数据库为 `4a7b9c1d3e5f`。API/CMS 健康检查、双端首页与抽查资源字节比对通过；生产 PostgreSQL 的性能记录写入、冲突忽略与配对报告已用回滚事务验证。未调用收费模型，也未改变支付开关。详细配置与恢复证据仅保存在私有部署记录。
