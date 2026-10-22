# 客户端错误分析与埋点

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
