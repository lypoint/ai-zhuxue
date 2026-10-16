# 客户端错误分析与埋点

国内学生端 `app_student`、国内家长端 `app_parent_wechat` 保留空实现；共享业务代码只调用 `app_core` 的 `Telemetry`，不依赖 Firebase。App Store 当前也保持空实现。

Google Play 学生端 `app_student_googleplay`（`com.aizhuxue.student.play`）和家长端 `app_parent_googleplay`（`com.aizhuxue.parent.play`）使用独立渠道入口，引入 `play_telemetry`，接入 Firebase Analytics 与 Crashlytics。只有 release 构建启用采集；debug/profile 关闭。初始化或上报失败不阻断业务。

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

实际 Firebase JSON 不放入开源仓库。Gradle 默认从仓库上级的 `credentials/firebase/parent-google-services.json`、`student-google-services.json` 读取；CI 可用 `FIREBASE_CONFIG` 指定绝对路径。文件必须与应用包名匹配。不需要 Firebase 管理员私钥。

使用 Flutter 3.38.10。家长端沿用 `scripts/build_parent.py googleplay`，学生端在 `app/app_student_googleplay` 内运行 `flutter pub get --enforce-lockfile`、`flutter build apk --debug` 或 `flutter build appbundle --release`。学生端 release 也要求独立的 `android/key.properties` 和正式签名，禁止退回 debug 签名。API_BASE 等配置仍可用 `--dart-define` 传入。原有 `app_student` 构建命令继续产出国内包。

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
