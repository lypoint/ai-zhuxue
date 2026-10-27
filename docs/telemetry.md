# 客户端错误分析与埋点

## 家长 Web Firebase Analytics（2026-10-26）

仅家长 Web 接入 Firebase JS SDK 13.1.0，使用独立 Web 应用。`PARENT_FIREBASE_CONFIG` 在 Vite 家长构建时注入；学生构建不注入配置、不打入 Firebase SDK。真实配置位于仓库外 `credentials/firebase/parent-web-config.json`，本地通过被忽略的 `web/.env.parent.local` 注入，格式见 `web/.env.parent.example`。这是公开 Web SDK 配置，不是管理员凭据；不得放入服务账号私钥或 Measurement Protocol API secret。

初次访问默认不加载 Firebase/gtag，也不补发授权前的事件。家长可选择“仅必要功能”或“全部接受”，并通过页面固定的“数据隐私与合规声明”入口随时修改。选择按浏览器保存在 `parent-analytics-choice`，跨标签页同步。撤回时先设置 GA disable 标志，关闭收集与授权，清除可访问的 GA Cookie；已上传数据不会因本地撤回而被远程删除。存储或 SDK 被阻止时不影响登录、家庭管理与支付。开发模式的事件标记 `debug_mode`，正式构建不启用此标记。

| 事件 | 真实触发点 / 口径 |
|---|---|
| `page_view` | 同意后的首次页面及 SPA 页面切换；页面按固定枚举归类 |
| `login_start`、`login` | 收到 Google 凭证后提交服务端登录、登录 API 成功/失败；不发送凭证 |
| `sign_up`、`trial_start` | 服务端确认本次新建家长家庭时触发，老账号登录不计注册或重新开始试用 |
| `child_create` | 家长创建孩子 API 成功/失败；不发送孩子字段 |
| `bind_code_create` | 新建孩子时成功生成绑定码，或重新生成绑定码的成功/失败；不发送码值 |
| `child_connected_observed` | 同意后，家长页面在本次挂载中首次从已认证家庭响应看到孩子已连接设备。不发送孩子/家庭 ID；不是服务端真实首次激活时间，刷新页面可再次观察 |
| `view_subscription` | 登录后的订阅页面展示；在该页面授予授权时也记录 |
| `begin_checkout`、`checkout_open` | 选择套餐并跳转经过服务端校验的 Waffo 收银台；跨站实际加载不可观测，埋点不阻塞跳转 |
| `checkout_closed`、`checkout_error` | Waffo 创建或跳转失败记错误；离站后关闭或取消不伪造关闭事件 |
| `subscription_verify` | 服务端验单请求成功/失败，包含重复核验和恢复；不是首次付款、营收或续费事件 |
| `subscription_manage` | 请求订阅管理入口成功/失败；不等于用户已取消自动续订 |

仅发送枚举 `provider/result/page_name`、有效范围内的 `seat_count/status`。不设置 Analytics User-ID、账号属性或广告属性，不发送家庭/孩子 ID、姓名、邮箱、学习内容、API 请求体、登录令牌、绑定码、支付引用、完整路径、查询串、hash 或 referrer。`page_location` 固定为 Origin 加页面枚举，`page_title` 固定为产品名称。广告存储、广告用户数据、广告个性化、Google signals 均关闭。新 Web 数据流的“增强型衡量”已确认关闭，避免自动表单、出站链接及浏览历史采集绕过固定事件规则。

上述 Firebase 漏斗只代表同意统计的浏览器样本，不提供跨浏览器家庭去重。服务端和学习站现已增加第一方事件，按本次产品决策不设同意门槛，支持家庭去重的激活、学习、结账、30 天转化和留存；详见 [运营漏斗与事件口径](operations-analytics.md)。自动续费、退款和净收入仍需财务事实与账本。不得把 `subscription_verify` 当作 GA `purchase` 事件，或凭付款回跳 URL 发放/统计付款成功。云端已注册事件范围的 `page_name`（Parent Web Page）、`provider`（Billing Provider）、`result`（Operation Result）自定义维度；其他环境部署时检查并复用同名定义。

验证：`npm run check`；使用合成配置 `WEB_TEST_FIREBASE_CONFIG='{"apiKey":"test","appId":"1:123:web:test","projectId":"test","measurementId":"G-TEST"}' npx playwright test tests/analytics.spec.ts` 验证真实 SDK、授权前零外发、撤回、参数脱敏和学生隔离。该测试拦截所有 Google 采集请求。真实私有配置另已通过本地页面授权，云端 DebugView 收到 `page_view`、`session_start`、`first_visit`，确认 `page_location` 为固定本地页面；测试后已撤回本地授权。证据在私有 Firebase 目录。2026-10-26 已随 `13b2537` 发布生产家长站；公网产物与授权/拒绝入口已核对，学习站保持第一方采集及同源隔离。

## 原生 App

国内学生端 `app_student`、国内家长端 `app_parent_wechat` 保留空实现；共享业务代码只调用 `app_core` 的 `Telemetry`，不依赖 Firebase，亦不包含任何海外合规与跟踪代码。

海外渠道引入 `overseas_compliance` 模块提供轻量级 GDPR 动态 Consent 管理与合规弹窗：
- Google Play 学生端 `app_student_googleplay` 与家长端 `app_parent_googleplay` 引入 `play_telemetry`，接入 Firebase Analytics 与 Crashlytics。遵循 GDPR Privacy by Default 原则，由用户在 GDPR 弹窗中的明确授权动态调用 `analytics.setConsent(analyticsStorageConsentGranted: granted)`。
- App Store 家长端 `app_parent_appstore` 与学生端 `app_student_appstore`（iOS）集成 `app_tracking_transparency`，在 `Info.plist` 及七语言本地化资源中声明 `NSUserTrackingUsageDescription`，并在启动时完成隐私告知与追踪权限申请。

## 数据范围

自定义事件只接受固定枚举，不接受任意业务字段。参数为 `result=success/failure` 和可选 HTTP `status`。

| 事件 | 时机 |
| --- | --- |
| `app_ready` | 入口初始化完成并调用 runApp |
| `account_login` | 家长 Google 登录 API 成功或失败 |
| `student_bind` | 学生绑定登录 API 成功或失败 |
| `chat_send` | 流式聊天请求完成或失败 |
| `bind_code_create` | 家长创建绑定码 API 成功或失败 |
| `purchase_verify` | 服务端验单 API 成功或失败 |
| `purchase_restore` | 商店恢复请求完成或失败；不代表权益已核验 |
| `account_logout` | 注销登录 API 成功或失败 |

自定义错误上报仅包含异常类型和过滤后的 Dart 包代码位置，不传异常消息、请求路径、请求体、手机号、邮箱、登录/购买令牌、孩子昵称或聊天内容。预期的 HTTP 4xx 不报 Crashlytics；HTTP 5xx、解析/网络异常记为非致命错误。Flutter 框架异常和未捕获异步异常记为 fatal。Crashlytics SDK 本身仍会收集标准崩溃诊断（设备/系统/应用版本、安装标识、原生堆栈等）；Analytics 仍有标准会话和设备信息。

广告存储、广告用户数据及广告个性化均拒绝；移除 AD_ID 权限，不设置用户 ID 或用户属性，关闭自动页面上报。学生端与家长端通过不同 Firebase App 区分。

## 私有配置与构建

实际 Firebase Android 配置 JSON 不放入开源仓库。两个 Google Play 渠道的调试及正式构建均须准备配置：家长默认读取仓库上级 `credentials/firebase/parent-google-services.json`（`com.aizhuxue.parent.play`），学生默认读取 `credentials/firebase/student-google-services.json`（`com.aizhuxue.student.play`）。本地或 CI 可用 `FIREBASE_CONFIG` 指定对应 JSON 的绝对路径；它由 Gradle 读取，切换渠道时必须同步切换或清除该覆盖变量。发布前检查文件可读且 JSON 中的 Android 包名匹配。不需要 Firebase 管理员私钥，不能把后端 Google 服务账号 JSON 当作此配置。

使用 Flutter 3.38.10。完整构建参数见 [部署与运维](deployment.md#4-flutter-构建产物)：家长端沿用 `scripts/build_parent.py googleplay`，学生端在 `app/app_student_googleplay` 内严格解析依赖再构建。学生端 release 也要求独立的 `android/key.properties` 和正式签名，禁止退回 debug 签名；直接执行 Flutter 时必须显式传入生产 HTTPS `--dart-define=API_BASE=...` 及实际政策地址，不能依赖环境变量自动传入。原有 `app_student` 构建命令继续产出国内包。

依赖及 APK/AAB 隔离检查（仓库根目录）：

```sh
python3 scripts/check_telemetry.py app_student
python3 scripts/check_telemetry.py app_parent_wechat
python3 scripts/check_telemetry.py app_student_googleplay --artifact app/app_student_googleplay/build/app/outputs/flutter-apk/app-debug.apk
python3 scripts/check_telemetry.py app_parent_googleplay --artifact app/app_parent_googleplay/build/app/outputs/flutter-apk/app-debug.apk
```

Crashlytics Gradle 插件已加入两个 Play 壳。当前构建不启用 Dart obfuscate/split-debug-info；如以后启用，必须在发布流程上传对应 Flutter 符号，否则不能恢复 Dart 堆栈。不要向真实用户投放故意崩溃的测试包。

## 发布验证

代码构建通过不代表云端已收到数据。正式发布前，应在受控测试设备运行 release 包，确认两个应用各自的 `app_ready` 及一条无敏感信息的测试错误抵达 Firebase，再检查 Crashlytics 版本、堆栈和事件参数；测试错误验证后应移除测试触发代码。debug/profile 不会产生上述数据。

2026-10-16 已同步线上七语言隐私政策（https://gker.net/privacy/），说明 Firebase Analytics/Crashlytics 的安装标识、IP 推导粗略位置、应用互动、订阅购买及诊断数据、处理用途、渠道差异和未成年人范围。家长端 Google Play Data Safety 已填完并保存草稿，包含现有业务数据；无广告声明已保存，但审核登录详细信息及目标受众等前置声明尚未完成，因此尚未送审。现有 OAuth 仍为外部测试状态，仅指定测试邮箱可登录，需先提供可供审核员访问的登录方案。学生端尚无 Google Play 应用条目，声明对照已私下留存，创建条目后需按实际发布功能填写。家长端 1.0.2（3）已发布到 Google Play 内部测试轨道；学生端 release 尚缺正式签名配置。正式上线前仍需验证两个 Firebase App 的真实数据到达，并完成商店声明送审。

2026-10-16 后续变更：实名认证表单、核验接口及相关状态字段已移除；家长端 1.0.3（4）已发布到内部测试。线上七语言隐私政策同步移除可选身份核验说明，Data Safety 草稿取消仅用于证件核验的“其他信息”数据类型；昵称、Google 邮箱、用户 ID 等现有业务声明保留。Data Safety 仍需完成审核登录和目标受众前置声明后才能送审。
