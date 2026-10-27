# Waffo Web 订阅

注册即获得 3 天免绑卡试用、1 个学生名额。符合资格的家庭通过认证收银台开通 Waffo 原生 30 天免费试用，结束后首次扣款、按月续费，直至取消。两段试用重叠，注册试用剩余时长不补赠；立即订阅共约 30 天免费使用，用完 3 天再订阅共约 33 天。若中途停用后才订阅，累计免费使用时长与注册至首扣的日历跨度不同。

## 商品与身份

| 商品代码 | 学生总名额 | USD/月 |
| --- | ---: | ---: |
| family_monthly_1 | 1 | 9.99 |
| family_monthly_2 | 2 | 14.99 |
| family_monthly_10 | 10 | 49.99 |
| family_monthly_100 | 100 | 499.99 |

四个商品为 monthly，metadata.trialDays=30，免费试用不设置 trialAmount。美元价不含可能的税费，最终金额以结账页为准。放入同一产品组，开启 sharedTrial，关闭 selfServicePlanChange。首版支持新购、续费、取消/恢复续费与对账，不开放套餐变更；不能在门户切换套餐而绕过应用名额校验。

买家身份采用已有 StoreAccount.account_token，从登录家庭服务端取得。认证收银台 token 仅放 URL fragment，不使用匿名购买链接。订单附带家庭 HMAC 绑定和服务端业务订单号，回跳参数不能授予权益。已有开通记录的家庭再次订阅显式 withTrial=false，首次订阅省略该字段、遵循平台及产品组资格；禁止 withTrial=true 绕过原生防重复试用。

## 配置

见 server/.env.example：WAFFO_ENABLED、WAFFO_ENVIRONMENT、WAFFO_MERCHANT_ID、WAFFO_STORE_ID、WAFFO_PRIVATE_KEY_PATH、WAFFO_WEBHOOK_PUBLIC_KEY_PATH、WAFFO_TEST_ACCOUNT_TOKENS；STORE_PRODUCTS_JSON 的 waffo 字典映射以上四个代码至真实 PROD_ ID。保留原 STORE_TOKEN_SECRET，不能换密钥导致历史账本无法解密。

API Key 通过 RSA-SHA256 签名；对应环境由密钥决定。测试/生产私钥与回调公钥分别保存于私有凭据区，不入库。生产 API 使用测试环境时仅允许 WAFFO_TEST_ACCOUNT_TOKENS 中的家庭。默认关闭支付，未配置真实凭据时不可开放。

迁移 5b8c0d2e4f60 将仍为默认 30 天的数据库定价配置改为 3 天，解决已运行实例不读取环境默认值的问题；不删家庭或支付数据，不批量截断已有家庭权益。

## 接口

- GET /parent/waffo/catalog：四档美元目录、环境标记。
- POST /parent/waffo/checkout：验证套餐、名额、跨渠道互斥、已有订单；创建短期认证收银台。未提交且仍有效的同套餐会话复用，买家 token 每次重新签发。
- POST /parent/waffo/verify：reference 为应用业务订单号或 ORD_ ID；重新查询权威订单、家庭、环境、商品版本、周期、付款及退款状态，再写既有加密账本。
- POST /parent/waffo/refresh：刷新当前家庭的远程订阅，支持回跳遗失或清理浏览器缓存后的恢复。
- GET /parent/waffo/manage：为当前家庭即时签发消费者门户链接，响应 no-store；链接不可记录或缓存。
- POST /payments/waffo/notify：原始请求体 RSA 验签、64 KiB 上限，校验商店及环境。原始签名允许最多 45 分钟重试、最多 1 分钟未来时钟偏移；按事件类型和 ID 去重，持久重试并周期对账。

原生试用状态独立为 subscription_trial，按所选套餐授予权益，不生成实付统计、不补赠本地试用。canceling 保留当前周期权益，canceled/退款/争议按权威状态撤回。零元试用付款的 isFullyRefunded=true 不代表退款，不得撤权。past_due 保留短暂恢复窗口，最长到当前周期开始后 48 小时，不因一笔未付续费授予整月。退款不会自动停止 Waffo 续费，支持操作必须另行取消。

## 发布与验收

1. 按当前 deployment.md 与私有生产说明核对主机、配置和迁移。先用测试密钥验证四档真实目录、认证收银台、零元试用、首扣、取消、续费失败、签名及幂等；未发生的生命周期用隔离回归覆盖，不能宣称已真实验收。
2. 公网只代理精确 POST /payments/waffo/notify，限制请求体；移除旧支付测试回调和家长 CSP 中的旧支付 SDK/iframe 域名。Waffo 使用整页跳转，无需放宽学生 CSP。
3. 发布家长 Web 与 API，同时更新私有官网首页、价格页、条款及 78 种语言；新翻译使用独立版本 URL，保留上一版本资源供已打开页面使用。
4. 核对 Waffo 商品生产版本、产品组、生产签名公钥、回调与生产密钥后再启用正式收款。网站部署和真实扣款不包含在仅本地测试通过的结论中。

官方依据：[认证](https://docs.waffo.ai/api-reference/authentication)、[订阅](https://docs.waffo.ai/features/subscriptions)、[收银台](https://docs.waffo.ai/api-reference/endpoints/orders/create-checkout-session)、[通知](https://docs.waffo.ai/api-reference/webhooks)。GraphQL 查询字段已用真实测试 API introspection 核对，REST 价格对象不能直接照搬为 GraphQL 类型。

## 2026-10-27 发布验证

API/CMS、家长 Web 与官网已更新；四档 Waffo 生产商品和共享试用组已发布，生产通知已指向精确接口。数据库迁移到 5b8c0d2e4f60，当前配置 trial_days=3；旧测试通道权益停止，保留账本。未重建原生安装包，学生 Web 静态根与策略保持。

验证包括：服务端 889 passed / 1 skipped、Web 78 语种/类型检查与 12 单测、Chromium/WebKit 支付 HTTPS 专项 12 passed、CMS 运营页 2 passed、干净来源 npm ci/build、官网 84 个公网文件摘要一致。原生零元沙箱订阅取得 2 名额与 30 天试用，成功模拟续费后权威付款为 USD 14.99；取消和恢复入口可用，失败模拟进入恢复状态。生产密钥、商品规则及回调公钥已核对，并用生产 API 创建 60 秒收银台会话（未提交订单）；未执行真实扣款，尚无真实付费订单触发生产通知。

扩展家庭回归 20 passed / 6 failed，失败集中于既有图片流程；其中主图片场景在未修改的 Git 基线中双引擎同样失败，本次未修复。完整记录、精确源码及发布摘要、数据库备份与回退配置在私有生产说明中维护，不以支付专项通过代表所有图片流程通过。

恢复状态补充：返回 billing_status，past_due 的 grace 窗口即使 willRenew=false 也可能重试既有账单；页面显示扣款日期以服务商为准，不能显示“不会自动扣款”。后端及双引擎 HTTPS 均有专项回归。

## 2026-10-28 提交前审查

修复 PostgreSQL 中验单/刷新请求持有家庭行锁、又等待独立验单会话取得同一锁的问题；先结束授权事务，再执行独立核验，同步接口由线程池执行。独立 PostgreSQL 回归已在修复前复现、修复后通过。原生免费试用无论是否有零元付款，都按订阅记录一次开通事实；之后实付与恢复不重复开通。新购同时校验 USD 试用金额为零及自助换套餐关闭；用测试和生产四档真实商品只读查询验证新增 GraphQL 字段与规则。

本轮完整 SQLite 后端 893 passed / 3 skipped（含两个 PostgreSQL 专用用例）；PostgreSQL 的 Waffo/运营/浏览器专项 42 passed，Web 检查及 12 单测、双引擎支付 HTTPS 12 passed。扩展 PostgreSQL 商店回归另有四个既有时区表示断言失败，在未改 Git 基线可复现，未改其他渠道测试。以上是本轮本地审查验证，新增修复尚未部署，不替代前述发布验收。
