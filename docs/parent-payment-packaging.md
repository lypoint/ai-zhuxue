# 家长端多包与支付隔离设计

日期：2026-10-14。状态：三渠道壳、商店 SDK、验单/恢复/通知与隔离检查已实现；实际部署配置见 [渠道订阅接入](store-subscriptions.md)，真实商店沙盒与签名发布仍需验收。

家长端采用共享业务库与三个独立 Flutter 打包工程，每个工程拥有独立依赖图和原生配置。国内 Android 包保留微信支付，App Store 包接入 StoreKit，Google Play 包接入 Play Billing。支付渠道在构建入口确定，服务端统一核验交易并维护家庭权益。

本方案按应用内数字服务购买设计，商店包不提供微信支付、外部付款二维码或引导付款链接。现有 iOS 工程迁入 App Store 打包壳；首期不增加 iOS 微信支付分发渠道。学生端保持现有结构。

## 1 当前实现与改造边界

| 位置 | 当前行为 | 改造目标 |
| --- | --- | --- |
| `app/app_parent/pubspec.yaml` | 固定依赖 `fluwx`，包含微信插件配置 | 改成共享家长业务库，移出所有支付 SDK 与插件配置 |
| `app/app_parent/lib/screens/payment_screen.dart` | 页面直接初始化微信 SDK、支付、查单 | 将微信付款流程迁到微信打包壳，共享界面通过注入的支付入口发起购买 |
| `app/app_parent/lib/screens/home_screen.dart` | 先恢复微信待支付订单，再创建订单 | 委托当前打包壳处理购买与恢复，不在共享首页假设微信订单流程 |
| `app/app_core/lib/src/api.dart` | 提供微信订单 API 和家庭订阅 API | 保留兼容接口，新增商店商品、验单与权益查询接口，不依赖支付 SDK |
| `app/app_parent/android`、`ios` | 一个应用工程，同时承载微信原生依赖 | 迁入对应打包壳；平台认证 SDK、图标、登录和签名配置逐项保留 |
| `server/app/services/payment_orders.py` | 全局 `PAYMENT_MODE` 决定通道，付款后累加 30 天或名额 | 新订单购买完整月度档位，旧订单保留原报价与结算；商店交易独立验单 |
| `server/app/models.py` | 家庭一行订阅；微信待支付唯一索引；交易号最长 64 字符 | 保留微信订单约束，增加商店订阅来源与交易记录，不把商店购买套入微信待支付状态机 |

`--dart-define` 只能设置编译常量，Android flavor、iOS scheme 本身也不会从 Flutter 依赖图移除插件。Dart tree shaking 不能作为移除原生支付 SDK 的保证。因此不采用单一 `pubspec.yaml` 同时依赖三种 SDK、运行时选择渠道的方案。

## 2 发布包矩阵

| 构建渠道 | 打包工程 | 平台与产物 | 唯一支付依赖 | 应用标识 |
| --- | --- | --- | --- | --- |
| `wechat` | `app_parent_wechat` | Android APK，国内渠道 | `fluwx` | 保留 `com.aizhuxue.parent` |
| `appstore` | `app_parent_appstore` | iOS IPA | `in_app_purchase_storekit` | 保留当前 iOS Bundle ID，实施时核对签名与商店记录 |
| `googleplay` | `app_parent_googleplay` | Android AAB | `in_app_purchase_android` | 建议 `com.aizhuxue.parent.play`，创建商店记录前确认 |

Google Play 使用独立 applicationId，可与国内包并存，渠道签名、推送、号码认证及商店记录分别配置。家庭账号和服务端权益共享；本机登录存储按应用隔离。若已有 Google Play 应用记录，以已有 package name 为准，不能为了改渠道更换已发布标识。

共享库和三个打包壳都不依赖聚合包 `in_app_purchase`。截至设计日期，pub.dev 上该包同时依赖 Android 与 StoreKit 实现，不符合每个构建工程仅引入对应支付实现的要求。打包壳直接使用各平台实现的公开 API；可共享无原生支付实现的 `in_app_purchase_platform_interface`。实施时锁定经过验证的版本，确认所选 StoreKit 与 Billing SDK 的系统版本要求。

### 2.1 目录与依赖方向

```text
product/app/
  app_core/                         # 现有公共 API、主题、存储
  app_parent/                       # 家长 UI 与业务，改为共享 Flutter 库
    lib/parent_app.dart
    lib/bootstrap.dart              # 统一初始化与依赖注入
    lib/payments/payment_flow.dart  # 无 SDK 的购买入口契约
    lib/screens/                    # 登录、首页、家庭管理等
    pubspec.yaml                    # 无支付插件
  app_parent_wechat/
    lib/main.dart                   # 注入 WechatPaymentFlow
    lib/payments/                   # 微信付款页面和 SDK 调用
    android/
    pubspec.yaml                    # app_parent + fluwx
    pubspec.lock
  app_parent_appstore/
    lib/main.dart                   # 注入 AppStorePaymentFlow
    lib/payments/                   # StoreKit 购买、恢复及交易监听
    ios/
    pubspec.yaml                    # app_parent + StoreKit 实现
    pubspec.lock
  app_parent_googleplay/
    lib/main.dart                   # 注入 GooglePlayPaymentFlow
    lib/payments/                   # Billing 购买、恢复及交易监听
    android/
    pubspec.yaml                    # app_parent + Android Billing 实现
    pubspec.lock
  app_student/                      # 保持现有学生端
```

依赖只从打包壳指向 `app_parent`，再指向 `app_core`。共享库不得 import 打包壳或通过 export 间接导出支付插件。每个壳自己的 `pubspec.yaml`、锁文件、插件注册文件、Pods 和 Gradle 构建目录独立；不在同一目录反复覆盖 pubspec 或切换依赖。

共享家长代码只保留一份。原 `main.dart` 的 Flutter 初始化和 token 加载移到共享 bootstrap，各壳只传入固定渠道及支付实现。原打包脚本、IDE 启动配置和测试入口同步改指向对应工程。

### 2.2 支付入口与页面职责

共享库定义小型 `PaymentFlow` 契约：购买入口 `purchase(context, action)`、恢复入口 `restore(context)`，以及是否支持恢复购买的能力字段。`action` 表示续费或增加名额；返回结果只表示需要刷新服务端权益，不能直接表示已获得付费权限。首页、订阅卡片与家庭业务始终读取服务端订阅状态。

微信实现沿用现有订单页、待支付恢复、关闭订单、取消回调及查单补偿。商店实现负责商品查询、购买、恢复、交易监听和验单中的状态展示，不实现微信的预支付与关闭订单按钮。只有页面样式和业务入口共享，不强行统一底层交易状态机。

商店交易监听在应用初始化时注册，持续覆盖购买页外的续费、延迟交易与重启补偿。未登录收到的交易先保留，登录后再进行家庭绑定与验单；不能直接绑定到当前设备上一次登录的家庭。商店恢复入口常驻于订阅页面，Google Play 同时在登录和回到前台时查询有效购买。

## 3 原生配置隔离

| 配置层 | 微信 Android | App Store iOS | Google Play Android |
| --- | --- | --- | --- |
| 插件与原生库 | 仅微信 SDK | 仅 StoreKit 支付实现 | 仅 Google Billing 支付实现 |
| 支付配置 | 微信 AppID、回调 Activity、已登记签名 | In App Purchase 能力、商品与订阅组、商店签名 | Billing 权限、商品与基础方案、Play App Signing |
| 禁止残留 | StoreKit/Billing 支付实现 | `fluwx`、微信库、微信 URL Scheme/查询白名单/支付关联域 | `fluwx`、微信库/回调 Activity、StoreKit 支付实现 |

微信 iOS 的 URL Scheme 与查询白名单已存在于当前 `ios/Runner/Info.plist`，迁移时必须主动移除；微信专用 Associated Domains 如存在也要移除。仅删除 Dart import 或 `fluwx` 配置不保证已修改过的原生文件自动恢复。

共享登录依赖也纳入传递依赖检查。以后若引入微信登录插件并携带同一微信 SDK，需要重新评估商店包的“无微信 SDK”要求，不能把它当作与支付隔离无关的依赖。现有号码认证原生配置在每个目标工程分别登记实际应用标识与签名。

## 4 商店商品与现有业务的映射

### 4.1 推荐采用按名额分档的月度自动续订

各渠道使用相同的家庭月度档位价格：1 名额 ¥66/月，2 名额 ¥99/月，之后每个额外名额增加 ¥33/月；另有固定套餐 10 名额 ¥300/月、100 名额 ¥3000/月，优先于逐名额计算；基础与增量价读取 CMS，两个固定套餐不随 CMS 基础价变化，不按渠道加价。微信新订单不再累加 30 天或按剩余天数补差。商店包首期采用月度自动续订，每个商品包含确定的孩子名额数。例如业务档位 `family_monthly_1`、`family_monthly_2`，分别映射到 Apple product ID 和 Google product/base plan ID；实际档位清单由产品配置确定，覆盖上线时允许购买的名额范围。

| 用户动作 | 微信包 | 商店包 |
| --- | --- | --- |
| 新购或到期续费 | 按当前名额档位购买一个自然月 | 购买对应名额档位的月订阅 |
| 有效订阅期间续费 | 禁止重复购买同一档位叠加时长，到期后手动续订 | 展示自动续订状态和管理订阅入口，避免重复购买 |
| 增加名额 | 全价购买新档位月订阅，核验后立即增加名额 | 升级到更多名额的订阅商品，由商店处理差价与生效时间 |
| 降低名额档位 | 不新增微信降档功能 | 在商店支持的变更规则下办理，通常下周期生效；以权威状态为准 |
| 恢复购买 | 恢复微信待支付订单 | 恢复有效商店订阅并向服务端验单 |
| 取消自动续订 | 无此动作 | 跳转当前商店的订阅管理，保留已付周期内权益 |

Apple 的档位放入同一订阅组，正确设置服务级别；Google 使用支持替换的订阅商品，并传入旧 purchase token 和适用的 replacement mode。变更名额在服务端确认生效后更新；如果商店返回延期生效，就保持当前名额并展示计划变更。降档后的孩子不自动删除或解绑；超过额度时禁止新增，超额服务处置按明确的业务规则执行。

名额超出已配置的商店商品范围时，不发起购买，也不引导到微信付款；保留已获得权益并提示当前档位不可购买。发布前检查商品范围覆盖实际在用家庭，避免存在无法续订的档位。

微信即时升级从服务端确认支付时起计算一个自然月（按服务端业务时区，默认北京时间，月末日截到下月最后一天）；最终到期时间取既有到期时间与新周期结束时间的较晚者，保留历史已付或获赠权益，不将两个周期相加。升级收取新档位完整月费，例如 1 名额升级至 2 名额收取 ¥99，已有费用不折算抵扣，也不自动退款；确认页必须说明。

Apple 和 Google 使用相同的档位月价，即时升级优先选择平台支持的即时生效方案；平台可能退还旧周期费用或进行抵扣，实际升级扣款不能承诺与微信相同。平台返回延期生效时，不提前发放名额。统一的是档位月价，不是平台的升级结算金额；两家控制台需要维护与 CMS 相同的人民币目标月价，其他地区以当地币种商品价格为准。

上线前已创建的微信订单通过价格快照识别为旧规则，仍按原金额与原权益结算，避免已付款订单因规则切换而失去权益；新订单全部使用 `monthly_tier_v1`。

### 4.2 价格与试用

商店页以 SDK 返回的商品价格和币种展示，禁止继续用服务端 `amount_cents / 100` 固定显示人民币。CMS 管理档位和 product ID 映射、可售状态；商店价格由各自控制台维护。微信价格继续使用现有 CMS 定价。

服务端保留币种与可信来源的金额；无法获取准确金额的商店交易不能用客户端展示价格冒充已核验实付金额。现有“累计实付人民币”字段只保留其人民币账务含义，商店交易按币种分别记录，不能直接累计进去。

家庭现有的服务端免费试用与商店优惠试用是两套资格。首期不另开商店免费试用，避免两者叠加；后续如提供优惠，由商店判断 eligibility，服务端试用不能被每次恢复购买重新开启。

## 5 服务端验单与权益

### 5.1 接口边界

保留现有微信订单 API，新增下列接口。名称为拟定路径，实施时纳入 `docs/api.md`：

| 接口 | 职责 |
| --- | --- |
| `GET /parent/billing/catalog?channel=...&seat_count=...` | 已实现：返回所选档位的统一业务 product code、CNY 月价与版本；商店 product ID 映射在接入时补充，实际价格仍由 SDK 查询 |
| `POST /parent/billing/purchase-intents` | 校验家庭、目标档位及已有订阅，返回服务端生成的家庭绑定标识与购买意图 |
| `POST /parent/billing/apple/verify` | 接收 transaction ID 或签名交易凭据，向 Apple 核验并绑定家庭 |
| `POST /parent/billing/google/verify` | 接收 purchase token，向 Google 核验并绑定家庭 |
| `POST /billing/apple/notifications` | 接收并核验 App Store Server Notifications V2 |
| `POST /billing/google/notifications` | 接收经身份验证的 Pub/Sub RTDN，查询 Google API 后更新订阅 |
| `GET /parent/subscription` | 扩展为家庭当前权益、订阅来源、自动续订与计划变更信息 |

渠道字段和客户端编译常量用于路由及排错，不是可信验单证据。服务端对商店响应核对应用标识、商品白名单、环境、交易状态、到期时间与家庭绑定；Apple 的 `appAccountToken`、Google 的 `obfuscatedAccountId` 使用服务端生成的无明文个人信息标识。Google 新 token 与旧 token 的关联从可信响应追溯。一个商店订阅链不能同时绑定两个家庭；跨账号恢复冲突进入人工支持流程，不自动迁移权益。

保留微信服务配置，Apple/Google 使用各自配置与凭据同时运行。现有全局 `PAYMENT_MODE` 仅兼容微信与演示订单，不扩展成全服三选一开关，否则国内包与商店包无法同时服务。

### 5.2 交易处理

Apple 校验签名交易或通过 App Store Server API 查询，核对 bundle ID、product ID、environment、transaction ID、original transaction ID 及撤销信息。每次续订交易只处理一次。通知也必须验签与核验应用归属，不能仅凭通知类型授予权益。

Google 通过 Android Publisher API 查询订阅，核对 package name、product ID、购买状态、到期时间、账号关联及 token 替换链。RTDN 只是查单触发信号；验证 Pub/Sub 投递身份后仍要查询权威购买状态。Google token 在续订时可能不变，不能只用 token 判断是否为新周期。

客户端只在服务端已持久化核验结果之后 finish/complete 交易；网络或验单失败时保留待处理状态并重试。Apple 交易 finish、Google acknowledge 各按平台语义实现。Google 新订阅及时由后端确认，避免超过平台确认期限导致退款；自动续订不重复按新购买确认，PENDING 交易不确认、不发权益。客户端重启、服务器补偿任务和平台通知共同保证最终收敛。

Apple Sandbox、Google 测试购买与生产交易显式隔离；测试权益不能写入生产家庭账本。演示模式只供开发测试，发布构建禁用演示确认入口，服务端沿用生产禁止演示发权益的限制。

### 5.3 最小数据扩展

新增商店订阅来源表，至少包含 `family_id`、provider、environment、应用标识、商品/档位、订阅链标识、Google token、当前周期、生效名额、状态、自动续订状态与计划变更。Apple original transaction ID 或 Google 已关联的 token 链只能归属一个家庭。

新增商店交易及通知记录，记录已核验交易、周期、事件去重键与处理状态。Apple 使用 transaction ID 去重；Google 使用权威订单/周期信息处理续订，RTDN 消息去重与交易周期去重分开。交易唯一键包含 provider、environment、应用标识和平台交易标识；purchase token 使用可容纳平台凭据的字段，不塞入现有 64 字符交易号列。

未绑定家庭的续订通知保留待关联记录，在首次验单或恢复后重算，不能直接丢弃。事件乱序时重新读取最新平台状态，不能让迟到的取消通知覆盖后续已恢复的订阅。

现有 `subscriptions` 保留为家庭权益的读取入口，增加来源记录后按有效区间计算当前权益。微信新订单按自然月计算且不叠加有效期，历史订单按原规则履约；商店期限以平台 expiry 为准，禁止调用微信 `settle()` 对商店续订加 30 天。退款、撤销、到期、宽限期、扣款重试和账号保留状态分别按平台语义处理。

### 5.4 跨包使用与重复订阅

同一家庭可在任一包查看已购买的权益。商店包只展示本渠道的新购和管理入口，不返回微信预支付参数，也不恢复微信待支付订单。已有微信待支付订单不会阻塞商店订阅；现有仅作用于 `demo/wechat` 的待支付唯一索引保留。

首期默认一家庭只主动创建一个有效付费订阅来源。已有其他渠道付费权益时，购买页显示来源和到期时间，阻止新购；到期后可选择当前渠道。购买意图校验与家庭锁减少并发双购，但外部商店续订和离线购买不能被本地锁阻止。

如果已经出现两个付费来源，仍应核验并记账所有真实交易。家庭权益按各来源有效区间取可用权限，当前名额取有效来源中的最大值，周期与名额均不相加。权益在每个来源到期或变更时重新计算，不能把较大名额与另一来源较晚到期时间拼成一个虚假的长期高档位。页面提示重复订阅并提供本渠道管理入口；取消续订不会自动退款。

## 6 构建机制与产物验收

### 6.1 统一入口

拟增加 `tool/build_parent.sh <wechat|appstore|googleplay>`，参数只接受枚举，不允许任意组合渠道与平台。脚本在对应工程执行依赖解析和构建，并检查渠道专属配置、商品映射及正式签名。API 环境参数与支付渠道分离，切换 staging 不改变支付 SDK。

以下为完成目录改造后的构建示例，当前工程不能直接执行：

```sh
cd product/app/app_parent_wechat
flutter pub get --enforce-lockfile
flutter build apk --release --dart-define=BUILD_CHANNEL=wechat

cd ../app_parent_appstore
flutter pub get --enforce-lockfile
flutter build ipa --release --dart-define=BUILD_CHANNEL=appstore

cd ../app_parent_googleplay
flutter pub get --enforce-lockfile
flutter build appbundle --release --dart-define=BUILD_CHANNEL=googleplay
```

支付实现由 `main.dart` 的 import 与注入决定；`BUILD_CHANNEL` 只用于诊断、API 路由和一致性校验。入口、平台与 define 不一致时直接构建失败，不回退到微信。微信构建还需传入已核对的 AppID 等配置；签名、商户密钥与商店服务凭据不写入客户端公共配置。

CI 三个独立任务分别使用自己的工作目录与缓存键，缓存键包含渠道、平台、工具链和锁文件摘要。首次迁移删除对应工程旧插件元数据与原生依赖缓存后重新生成，避免遗留微信插件注册。三个应用锁文件提交 Git，正式构建使用固定工具链和锁文件。

### 6.2 发布门禁

每次构建均验证三层，任一失败不得上传商店：

1. **依赖图**：检查 `flutter pub deps`、`.flutter-plugins-dependencies` 与锁文件，允许当前支付插件，拒绝另外两种及其传递依赖。Google 校验 Gradle release 依赖树，Apple 校验 Pod 锁文件；微信包明确不存在 Billing 库。
2. **原生配置**：检查插件注册、最终 merged AndroidManifest、IPA 中最终 Info.plist 与签名 entitlements。商店包禁止微信回调 Activity、微信包查询、URL Scheme 和微信专用关联域，保留业务实际需要的其他域。
3. **产物**：解包最终 APK/AAB/IPA，Android 检查所有模块的 DEX 类、原生库、manifest 与资源，iOS 检查嵌入框架、静态链接符号和资源，确认不包含非目标支付 SDK。用已知测试产物校准扫描规则；单纯搜索文件名或字符串不能证明 SDK 缺席。记录渠道、应用标识、签名身份、版本、锁文件摘要与产物摘要。

### 6.3 行为验收

| 范围 | 必须覆盖 |
| --- | --- |
| 微信回归 | 已有付款页与订单测试、待支付恢复、取消、查单补偿、生产演示禁用 |
| 商店购买 | 新购、取消、PENDING、断网、购买成功但验单失败、重启后补交、恢复购买 |
| 订阅生命周期 | 自动续订、升级/延期降档、取消后到期、宽限期、退款/撤销、重复及乱序通知 |
| 安全与隔离 | 伪造凭据、错应用/商品/环境、重复交易、家庭绑定冲突、跨包登录与并发双购 |
| 发布产物 | 三渠道均只包含目标支付实现，商店页面没有微信付款入口或付款引导 |

StoreKit 本地配置用于开发流程验证，上架前还需 Apple Sandbox/TestFlight 与 Google Play 内部测试购买验证服务端完整链路。普通模拟器和无支付凭据的单元测试不能代替这些验收。

## 7 实施顺序

1. 提取共享 `app_parent`，新增三个打包壳及支付入口注入；先完成微信迁移与回归，验证登录、签名、号码认证和 UI 无退化。
2. 落地三渠道构建入口与依赖/配置/产物门禁，先证明商店壳里无微信 SDK。
3. 确定名额档位、自动续订文案与跨渠道购买规则，登记商店商品及应用标识。
4. 增加商店交易、订阅来源与验单接口，保留微信路径；实现通知、恢复、确认交易及补偿。
5. 接入两个商店的购买页面，完成沙盒与内部测试，再生成正式发布产物。

商店购买链路完成前，商店壳仅用于开发验证，不能作为已接入支付的正式发布包。当前设计不包含商店后台建商品、真实签名发布或正式扣款结果。

## 8 实施参考

- [现有微信支付接入与验收](wechat-payment.md)
- [Flutter StoreKit 实现](https://pub.dev/packages/in_app_purchase_storekit) 与 [Android Billing 实现](https://pub.dev/packages/in_app_purchase_android)
- [Apple 应用审核规则](https://developer.apple.com/app-store/review/guidelines/)
- [App Store Server API](https://developer.apple.com/documentation/appstoreserverapi)
- [Google Play Billing 服务端集成](https://developer.android.com/google/play/billing/backend)

实施时以目标商店、地区和所选 SDK 的当前要求为准；本方案采用两家商店原生购买的发布路径。
