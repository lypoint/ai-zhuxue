# 家长端渠道订阅接入

## 包与运行入口

| 渠道 | Flutter 包 | 平台 | 唯一支付 SDK | 应用标识 |
|---|---|---|---|---|
| 国内微信 | `app/app_parent_wechat` | Android | fluwx 5.7.2 | `com.aizhuxue.parent` |
| App Store | `app/app_parent_appstore` | iOS 15+ | in_app_purchase_storekit 0.4.4 / StoreKit 2 | `com.aizhuxue.appParent` |
| Google Play | `app/app_parent_googleplay` | Android | in_app_purchase_android 0.5.0 / Billing 8.0.0 | `com.aizhuxue.parent.play` |

`app_parent` 是共享 UI 与家庭业务库；`parent_store` 仅依赖支付平台接口，不携带任何商店支付实现。SDK 注册、购买参数和原生工程属于对应渠道壳。不要从共享库直接运行 App，不要添加聚合依赖 `in_app_purchase`（会引入两个商店实现）。三份 pubspec.lock 独立固定依赖。

微信/App Store 可用 Flutter 3.32.8；Google Play 使用 Flutter 3.38.10（本包 .fvmrc 已固定，Dart >=3.10）。CI 为 Google Play 固定 Flutter 3.38.10，其余包固定 Flutter 3.32.8。原有短信与阿里云一键登录保留；新 Google 包标识及渠道签名需要另行登记号码认证方案。

## 商品与即时升级

各渠道使用同一个业务月价：1 名额 ¥66、2 名额 ¥99，其余一般档位每增加一个名额增加 ¥33；**10 总名额 ¥300、100 总名额 ¥3000** 覆盖公式。10/100 表示订阅的总名额，不是购买额外数量。商店只能出售服务端配置过的商品；国内微信仍可按请求名额计算。

- 微信是单次月订阅，升级支付完整目标档位月价，确认后立即增名额；不按天补差、不叠加 30 天。保留已有更晚的有效期。
- Apple：所有名额档位建在**同一个自动续订订阅组**，按名额从多到少设置等级（多名额为更高等级），确保升级立即生效。注意 10 名额价格低于公式下的 9 名额，等级必须按权益排序。旧周期退款与新周期收费由 Apple 处理。首期关闭 Family Sharing，权益绑定本应用家庭账号，不能用 Apple 家庭共享复制到另一个应用家庭。
- Google：每档建一个自动续订订阅商品，**仅启用一个按月 base plan，不配置优惠、年付或预付计划**。即时升级传原订阅 token 和 `chargeFullPrice`，商店按该模式立即收费并处理剩余价值及续订日；服务端以 subscriptionsv2 返回的实际到期时间为准。
- 客户端展示商店本地化价格；CNY 商品与业务月价不一致时阻止购买。其他地区需在控制台配置对应当地价格，汇率与税费不能保证数值相同。
- 不开放提前重复购买同档或降档。商店有效订阅自动续订，取消入口打开商店订阅管理页面。
- 家庭权益可跨渠道使用；购买入口阻止有其他渠道有效订阅或自动续订的家庭跨渠道再买。已被商店实际扣款的交易仍需验单入账，不拒绝恢复、不叠加周期。多个来源同时有效时，选择名额最多的来源及它自己的到期时间（同名额优先有效付费来源，再比较到期时间），到期后回落到仍有效的来源。

## 服务端配置

参照 `server/.env.example` 与 docker-compose.yml。商品 ID 只是示例，必须与控制台实际 ID 一致。`STORE_PRODUCTS_JSON` 将业务码映射到商店 ID，例如：

```json
{"appstore":{"family_monthly_1":"family.monthly.1","family_monthly_2":"family.monthly.2","family_monthly_10":"family.monthly.10","family_monthly_100":"family.monthly.100"},"googleplay":{"family_monthly_1":"family_monthly_1","family_monthly_2":"family_monthly_2","family_monthly_10":"family_monthly_10","family_monthly_100":"family_monthly_100"}}
```

如需 3～9 等其他档位，在两个控制台建立月订阅并加入映射，月价按业务公式设置。不要把同一个商品 ID 映射到多个档位。CMS 改价后须同步商店控制台再开放新购买；商品映射是持久权益解释，不能随意把已售商品改成不同名额。

生成一次 `STORE_TOKEN_SECRET`：

```bash
cd server
.venv/bin/python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

保存到密管并持久保留。Google token 与通知引用以 Fernet 加密落库；变更密钥必须先迁移旧记录，直接替换将导致恢复与对账失败。不要把令牌、签名材料或真实密钥提交进 Git。

Apple 配置：`APPLE_ENVIRONMENT`、`APPLE_BUNDLE_ID`、生产 `APPLE_APP_ID` 数字 ID、`APPLE_ISSUER_ID`、`APPLE_KEY_ID`、`APPLE_PRIVATE_KEY_PATH`。从 [Apple PKI](https://www.apple.com/certificateauthority/) 下载 Apple 根证书（DER，通常 Apple Root CA G3），使用 `APPLE_ROOT_CERT_PATHS` 配置可信根；服务端启用证书链与在线撤销校验，不信任客户端自行上传的证书。生产默认仅接受 Production。开发 Sandbox 可使用独立测试后端（ENV=test/dev），测试构建通过 API_BASE 指向该后端。App Review / TestFlight 使用正式后端时，先为审核家庭创建登录账号，取得 `/parent/billing/account` 的 UUID 并加入 STORE_TEST_ACCOUNT_TOKENS 白名单；仅这些家庭允许测试权益。Production 交易查不到时才尝试 Sandbox API，仍校验证书链、环境、bundle ID、商品及家庭绑定；Sandbox 与 Production 交易链/流水隔离。不要把 APPLE_ENVIRONMENT 全局改成 Sandbox。

Google 配置：`GOOGLE_PACKAGE_NAME`、`GOOGLE_SERVICE_ACCOUNT_PATH`，在 Play Console / Google Cloud 启用 Android Publisher API 并授权服务账号管理订阅订单。订阅通知 Pub/Sub 的 authenticated push audience 为 `GOOGLE_PUBSUB_AUDIENCE`，push 服务账号邮箱为 `GOOGLE_PUBSUB_EMAIL`。OIDC 校验固定 Google 公钥、发行者、audience、已验证邮箱。生产默认拒绝 Google testPurchase；许可测试账号也必须将对应家庭 UUID 加入 STORE_TEST_ACCOUNT_TOKENS，或让测试构建连接独立测试后端。

Docker 使用 `STORE_KEY_DIR` 挂载 `/run/store`，里面放 apple.p8、Google 服务账号 JSON 和 Apple 根证书，目录在 Git 中忽略。`PAYMENT_MODE` 仅控制微信/演示支付，不决定商店验单通道。微信未启用时，生产 demo 订单接口继续拒绝购买，不影响商店订阅接口。

生产启动执行 Alembic `c3d4e5f6a7b8`，新增家庭商店账号、订阅来源、交易流水与通知 inbox。家庭使用服务端随机 UUID 绑定 Apple appAccountToken / Google obfuscatedAccountId。无绑定或绑定其他家庭的交易不能领权益；恢复购买必须先登录原家庭账号。旧订单与国内权益保持原有数据。

## API 与通知

- `GET /parent/billing/catalog?channel=appstore|googleplay&seat_count=N`：仅返回已配置商品及统一 CNY 目标月价。
- `GET /parent/billing/account`：登录家庭的稳定商店账号 token。
- `POST /parent/billing/purchase`：`channel`、`product_code`；校验购买资格，返回商品 ID、账号 token；Google 升级还返回当前家庭原订阅 token。
- `POST /parent/billing/verify`：`channel`、`reference`；Apple 为交易 ID，Google 为 purchase token。服务器向商店查询权威状态，再校验商品与家庭。成功返回家庭订阅状态，客户端此后才能 finish/complete 交易。
- `POST /payments/appstore/notify`：Apple App Store Server Notifications V2 的 signedPayload；验签后重新查订阅状态。
- `POST /payments/googleplay/notify`：authenticated Pub/Sub push；处理 subscriptionNotification、voidedPurchaseNotification 与测试通知。

自动续订、即时升级、宽限期、取消、到期、扣款失败与退款撤销均以商店状态更新权益。Google 新交易在验单与绑定成功后由服务端 acknowledge，客户端退出也不会遗漏确认。通知按事件 ID 去重，未绑定/处理失败的通知持久保存；每分钟取最多 100 个已到重试时间的待处理通知（失败指数退避，最长一小时），并对最近一小时未核对的订阅分批主动查单，弥补通知漏达。网络故障时不伪造延长权益，已验证期限仍可使用。

`store_transactions` 保留按商店交易号去重的验证流水。Apple 保存签名交易中的原币种 milliunit 价格；Google 未查询订单金额时不虚构成交价。现有 `paid_amount` / CMS 收款汇总仍是国内人民币订单统计，不能当作含海外币种的总收入；商店财务结算需用控制台财务报表。

## 构建与验证

本地调试可从相应包执行 flutter run。统一构建脚本从 product 根目录执行：

```bash
FLUTTER=/path/to/flutter python3 scripts/build_parent.py wechat --debug
FLUTTER=/path/to/flutter python3 scripts/build_parent.py appstore --debug
FLUTTER=/path/to/flutter-3.38.10 python3 scripts/build_parent.py googleplay --debug
python3 scripts/build_parent.py googleplay --check
```

正式构建省略 `--debug`：Android 输出 AAB，iOS 输出已签名 IPA。两个 Android 包都需要 `android/key.properties`（参照 key.properties.example）；Release 禁止使用 debug 签名。国内商店如需 APK，可在对应壳执行 flutter build apk --release，随后用脚本 --artifact 验证。

微信设置真实 `WECHAT_APP_ID`（与 fluwx pubspec 配置、服务端商户 AppID、Android 包名与签名一致）。商店 Release 设置 HTTPS `PRIVACY_URL` 与 `TERMS_URL`（订阅页显示入口），iOS 还需 `ALIYUN_AUTH_SDK_KEY` 和 Xcode 签名配置，号码认证 SDK key 必须匹配该 bundle ID。API_BASE 可选，默认项目线上 API。

脚本检查依赖图、共享库 SDK 导入、App Store plist/Podfile.lock，并扫描编译产物中的异渠道支付标识。支付 SDK 是编译依赖隔离，不能靠运行时 channel 开关替代。发布时还需检查最终签名、包 ID、目标 SDK 与商店最新审核要求。

真实沙盒验收必须使用控制台已配置的商品、签名和测试账号：首次订阅 → 杀进程再恢复 → 同档不可重复购买 → 1→10→100 即时升级 → 自动续订 → 取消但未到期 → 宽限/失败 → 到期 → 退款撤销 → 重复/乱序通知 → 换家庭拒绝复用凭证 → 换商店账号 → 原家庭在另一渠道只读使用权益。单元测试使用伪平台和受控权威响应，不能代替真实商店扣款验收。

## 本轮本地验证（2026-10-14）

- 三渠道调试构建与依赖/编译产物 SDK 隔离检查通过；iOS 为设备 arm64 无签名构建，Android 为 APK 调试构建。
- Flutter：共享家长 13 项、微信壳 7 项、共享商店流程 3 项测试通过，相关包静态分析通过。
- 服务端订阅测试覆盖权威验单、交易与通知去重、跨家庭拒绝、即时升级、过期/退款撤权、测试账号白名单、Google push OIDC、旧交易替换以及独立来源权益。SQLite 从空库迁移到最新版本已跑通。
- 未进行真实商店沙盒扣款、真机往返、正式签名 IPA/AAB 发布和 Docker 部署（本机无 Docker）。现有 Alembic 全量 schema 检查仍有其他旧表的索引/外键差异，新增商店表没有检测到差异。
