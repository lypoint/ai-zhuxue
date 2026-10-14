# 家长端微信 APP 支付

App Store 与 Google Play 的支付隔离、打包入口和商店验单改造见 [家长端多包与支付隔离设计](parent-payment-packaging.md)；实现与构建命令见 [渠道订阅接入](store-subscriptions.md)。

新订单使用统一家庭月度档位：默认 1 名额 ¥66/月、2 名额 ¥99/月，每个额外名额增加 ¥33/月，另有固定套餐 10 名额 ¥300/月、100 名额 ¥3000/月；基础与增量价读取 CMS，固定套餐优先，不随 CMS 基础价变化。到期后购买一个自然月，有效付费订阅不能通过重复购买同档位叠加时长。增加名额按新档位全额购买月订阅，核验后立即生效，不再按天补差；例如 1 名额升级至 2 名额本次收取 ¥99，不抵扣已付旧档位费用。新周期从确认支付起计一个自然月（默认北京时间），保留既有更晚到期时间，不相加。规则切换前已创建的订单仍按原报价及权益结算。创建订单不会发放权益；微信 API v3 查单或已验签解密的成功回调才发放权益，重复通知不会重复续费或增加名额。客户端微信回调只触发服务端查单。

## 演示验收

服务端使用 `ENV=dev` 或 `test`、`PAYMENT_MODE=demo`，其余微信字段沿用 `server/.env.example` 的演示值。演示模式不需要 PEM 文件、不联系微信、不扣款；家长端订单页明确显示「演示支付」。生产 `ENV=prod` 禁止创建或确认演示支付。

家长端「我的」→「续费」或「增加名额」→确认服务端金额→「确认演示支付」。离开页面后再次进入任一购买入口，会恢复待支付订单；可继续支付或关闭。金额包含所有当前孩子名额，续费不再固定展示 ¥66。

```sh
cd server
ENV=test .venv/bin/python -m pytest tests/test_wechat_pay.py tests/test_payment_orders.py tests/test_subscription.py -q
cd ../app/app_parent_wechat
flutter test
flutter analyze
flutter test test/wechat_payment_test.dart --dart-define=WECHAT_APP_ID=wx_test_app
```

## 资质下来后的替换位置

1. 微信开放平台注册移动应用，开通商户 APP 支付并绑定 AppID 与商户号。Android 包名为 `com.aizhuxue.parent`，填写实际发布证书签名。当前微信包仅用于国内 Android，iOS 使用 App Store 包。正式 Android 发布须使用已登记的发布签名，release 必须提供对应 android/key.properties，禁止调试签名。
2. 服务端配置 `PAYMENT_MODE=wechat`、`WECHAT_APP_ID`、`WECHAT_MCH_ID`、`WECHAT_MERCHANT_SERIAL`、32 字节 `WECHAT_API_V3_KEY`、`WECHAT_NOTIFY_URL`。回调地址必须为公网 HTTPS，路径为 `/payments/wechat/notify`，反向代理须转发原始请求体及 `Wechatpay-*` 请求头。
3. 商户 RSA 私钥保存于 `WECHAT_PRIVATE_KEY_PATH`；微信支付公钥保存于 `WECHAT_PLATFORM_PUBLIC_KEY_PATH`，`WECHAT_PLATFORM_SERIAL` 填写与该公钥匹配的 `PUB_KEY_ID_...`。本实现采用微信支付公钥验签模式；在商户平台启用该模式并下载公钥，更新公钥时同时替换文件与 ID。不把私钥或 API v3 密钥放进 Flutter。
4. Docker Compose 已映射上述配置；设置 `WECHAT_KEY_DIR` 为仓库外的目录，里面放置 `merchant_private.pem` 和 `platform_public.pem`。非容器部署可使用实际文件路径。正式密钥经密管注入，不提交 Git。
5. 微信壳 `app/app_parent_wechat/pubspec.yaml` 的 `fluwx.app_id` 替换为正式 AppID，执行 `flutter pub get`。同一 AppID 通过 WECHAT_APP_ID 编译变量注入客户端，并与服务端保持一致；插件生成 Android 微信回调 Activity。
6. 构建时传入与上述配置一致的值：

```sh
flutter build apk --release \
  --dart-define=WECHAT_APP_ID=wx替换为正式AppID \
  --dart-define=WECHAT_UNIVERSAL_LINK=https://替换为正式域名/wechat/
```

iOS 构建同样传入这两个 define，并使用开通 Associated Domains 的签名配置。服务端生产启动自动执行 Alembic 迁移，新版本为 `b1c2d3e4f5a6`，已有 mock 订单保留。

## 上线验证

先在已安装微信的真机使用正式资质执行小额支付，核对微信商户账单、服务端订单号/交易号及订阅到账；分别验证取消、返回应用、断网重试、关闭订单、重复回调和新增孩子名额。演示凭据不能发起真实扣款，Android 模拟器演示验收不能代替真机正式支付验收。

API：`POST /parent/payments/orders` 创建订单，`GET /parent/payments/pending` 恢复待支付订单，`POST /parent/payments/orders/{id}/prepare` 更新预支付参数，`GET /parent/payments/orders/{id}` 查单，`POST /parent/payments/orders/{id}/close` 关闭订单。所有家长接口按家庭鉴权；演示确认 `/demo-confirm` 在正式模式和生产环境不可用于发放权益。

## 历史验收（2026-10-12，以下金额和权益基于调整前规则）

- 服务端完整回归：197 项通过；支付测试包含真实 RSA 签名验证、AES-GCM 回调解密、签名伪造/过期、金额与商户不匹配、重复通知、查单补偿、家庭隔离、生产演示禁用和预支付失败重试。
- 家长端 14 项测试通过（包含微信测试 define），静态分析通过；SDK 成功回调不会直接授予权益。
- Android APK 构建通过，模拟器演示验收：¥66 续费到账、待支付订单恢复、¥33 增加名额到账、两名额续费显示 ¥99、关闭订单；核对本地数据库确认两个订单 paid、一个订单 closed，累计演示金额 9900 分，名额 2 个。
- iOS 微信支付依赖安装完成，arm64 模拟器 Xcode 构建通过。通用双架构 Flutter 构建在本机出现框架架构匹配错误，已用明确的 arm64 模拟器目标验证。
- 正式商户扣款及真机微信往返尚未验证，等待正式资质和配置后按上面的上线步骤验证。
