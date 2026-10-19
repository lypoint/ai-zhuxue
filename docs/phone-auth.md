# 家长端渠道登录

国内微信包与现有 App Store 包保留手机号自动登录及短信验证。Google Play 包仅显示 Google 账号登录，不包含阿里云号码认证 SDK；退出登录与会话失效也返回本渠道登录页。

## 国内手机号登录

家长端打开登录页时会检测本机号码认证。可用时展示运营商授权页，服务端使用阿里云 `GetMobile` 换取手机号；不可用、用户取消或取号失败时提供短信验证码登录。短信使用阿里云生成的 6 位验证码，5 分钟有效，服务端调用 `CheckSmsVerifyCode` 并要求 `Model.VerifyResult=PASS`。两种方式共用同一个手机号的家长账号。

## 服务端

生产环境在密管或部署环境注入 `ALIYUN_ACCESS_KEY_ID`、`ALIYUN_ACCESS_KEY_SECRET`。RAM 用户只授予 `dypns:GetMobile`、`dypns:SendSmsVerifyCode`、`dypns:CheckSmsVerifyCode`。签名、模板和场景名见 `server/.env.example`。缺少 AccessKey 时接口返回 503，不接受开发验证码。

短信发送接口为 `POST /auth/guardian/sms/send`，请求体 `{"phone":"139..."}`；短信登录沿用 `POST /auth/guardian/register`；本机号码登录使用 `POST /auth/guardian/one-tap`，只传 SDK 返回的 `access_token`，客户端不得自行传手机号。短信发送按 IP、手机号每分钟和每日限流。

## 客户端

家长端打包统一从开源仓库外的 `../credentials/` 加载平台 env 文件，具体可复制命令见[渠道构建与密钥加载](../../credentials/store-subscriptions.md#从私有-credentials-加载号码认证-key)。

iOS 使用 `aliyun-auth-ios.env`，Android 调试使用 `aliyun-auth-android-debug.env`。微信正式包使用待补齐的 `aliyun-auth-wechat-release.env`。Google Play 不使用阿里云号码认证配置。构建前清除继承的 `ALIYUN_AUTH_SDK_KEY`，启用 Shell 出错即退出，加载后检查非空；禁止用调试 Key 补位。`aliyun_key` 是大模型 API Key，不能用于号码认证。服务端 AccessKey 也不能传入客户端。

SDK 密钥绑定 App 标识与签名，不能跨平台复用，也不要提交到仓库。当前阿里云方案：iOS `com.aizhuxue.appParent`（Code `FC220000013735048`）；Android 调试包 `com.aizhuxue.parent`（Code `FC220000013775056`，使用本机 debug.keystore，仅供调试）。正式 Android 签名确定后需另建方案并使用其密钥。模拟器无 SIM 卡会直接使用短信方式；本机号码取号必须在有三大运营商 SIM 和移动数据的真机上验收。

鸿蒙原生构建还需要与当前 Dart 3.8 项目兼容的 Flutter HarmonyOS 工具链、DevEco Studio 5/API 12、AppId 和正式签名。阿里云鸿蒙方案创建表单要求 19 位 AppId 和 64 位包签名。取得这些资料后再创建方案并接入已下载的鸿蒙 `.har`，同时需要适配 `mobile_scanner`、`shared_preferences`、`flutter_secure_storage` 等插件。


## Google Play 账号登录

Google Play 壳独立依赖 `google_sign_in`。构建传入 `GOOGLE_SERVER_CLIENT_ID`，值为 OAuth Web 客户端 ID；服务端 `GOOGLE_LOGIN_CLIENT_ID` 必须为同一值。在 Google Cloud 为 `com.aizhuxue.parent.play` 及实际分发签名 SHA-1 登记 Android OAuth 客户端；Play 应用签名与本地上传/调试签名分别登记，不能互相替代。客户端不使用或打包 Web 客户端密钥。

客户端仅向 `POST /auth/guardian/google` 发送 Google ID token，携带 `X-App-Channel: googleplay`。服务端验证 Google RS256 签名、issuer、audience、有效期及已验证邮箱，以稳定的 `sub` 识别家长；邮箱改变不会新建家庭，也不会按邮箱合并手机号账号。Google-only 家长的 `phone` 为 null，家庭与订阅功能照常使用。

迁移 `d6e7f8a9b0c1` 保留原手机号账号，新增唯一 Google 身份。Google Play 使用独立登录缓存，升级后原手机号会话需要重新用 Google 登录。渠道头用于产品入口约束，不是可信设备证明。Google 公钥可通过已配置的受限 HTTPS 中继获取，仍由主 API 验签。真实 Google 登录需完成 OAuth 配置和签名真机测试。

## 账号删除与重新注册

家长在“我的 → 删除账号”提交确认后，原家庭和关联学生端立即停用，手机号、Google 身份和审核登录凭据解除占用，可再次登录注册为独立的新家庭。新注册不会恢复原家庭数据。旧令牌不能访问原家庭；删除申请重试仍返回原申请编号。原家庭数据继续按删除流程清理，支付、退款与必要审计记录保留。

学生在聊天侧边栏选择“删除账号”，确认后停用本学生身份、撤销全部设备登录并释放设备标识；学习记录仍由家长保留，确认页明确说明此范围。家长家庭页刷新或恢复前台时显示未读删除通知，通知中心保留记录；原孩子不再出现在有效孩子卡片中。如需删除学习数据，由家长另行申请。

CMS 管理员在“家长账号删除记录”查看申请编号、原家庭/家长 ID、申请时间、待清理/已完成状态及完成时间，支持分页。`GET /admin/account-deletions` 仅运营管理员及超级管理员可读，不返回原手机号、Google 身份或密码。学生主动删除也写入操作审计 `student.account_deleted`。后台仍使用现有 `python -m app.account_deletion complete` 流程执行数据清理，不能将停用状态当作清理已完成。
