# 家长端手机号登录

家长端打开登录页时会检测本机号码认证。可用时展示运营商授权页，服务端使用阿里云 `GetMobile` 换取手机号；不可用、用户取消或取号失败时提供短信验证码登录。短信使用阿里云生成的 6 位验证码，5 分钟有效，服务端调用 `CheckSmsVerifyCode` 并要求 `Model.VerifyResult=PASS`。两种方式共用同一个手机号的家长账号。

## 服务端

生产环境在密管或部署环境注入 `ALIYUN_ACCESS_KEY_ID`、`ALIYUN_ACCESS_KEY_SECRET`。RAM 用户只授予 `dypns:GetMobile`、`dypns:SendSmsVerifyCode`、`dypns:CheckSmsVerifyCode`。签名、模板和场景名见 `server/.env.example`。缺少 AccessKey 时接口返回 503，不接受开发验证码。

短信发送接口为 `POST /auth/guardian/sms/send`，请求体 `{"phone":"139..."}`；短信登录沿用 `POST /auth/guardian/register`；本机号码登录使用 `POST /auth/guardian/one-tap`，只传 SDK 返回的 `access_token`，客户端不得自行传手机号。短信发送按 IP、手机号每分钟和每日限流。

## 客户端

构建家长端时从密管向 Flutter 传入各平台各自的号码认证 SDK 密钥：

```sh
flutter build ipa --dart-define=ALIYUN_AUTH_SDK_KEY="$IOS_AUTH_SDK_KEY"
flutter build apk --dart-define=ALIYUN_AUTH_SDK_KEY="$ANDROID_AUTH_SDK_KEY"
```

SDK 密钥绑定 App 标识与签名，不能跨平台复用，也不要提交到仓库。当前阿里云方案：iOS `com.aizhuxue.appParent`（Code `FC220000013735048`）；Android 调试包 `com.aizhuxue.parent`（Code `FC220000013775056`，使用本机 debug.keystore，仅供调试）。正式 Android 签名确定后需另建方案并使用其密钥。模拟器无 SIM 卡会直接使用短信方式；本机号码取号必须在有三大运营商 SIM 和移动数据的真机上验收。

鸿蒙原生构建还需要与当前 Dart 3.8 项目兼容的 Flutter HarmonyOS 工具链、DevEco Studio 5/API 12、AppId 和正式签名。阿里云鸿蒙方案创建表单要求 19 位 AppId 和 64 位包签名。取得这些资料后再创建方案并接入已下载的鸿蒙 `.har`，同时需要适配 `mobile_scanner`、`shared_preferences`、`flutter_secure_storage` 等插件。
