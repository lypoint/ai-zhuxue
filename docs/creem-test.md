# Web Creem Test Mode

2026-10-26：已部署至线上家长 Web，仅指定测试家庭可见；真实测试卡购买及取消续订已使用独立合成家庭验收，未替用户线上家庭付款。

Creem 是海外 Web 支付备用通道。本实现仅接受 `creem_test_` 密钥，固定调用 `https://test-api.creem.io/v1`，逐项检查权威对象 `mode=test`。正式收款与账号审核不属于本次接入。

## 配置与商品

`CREEM_TEST_ENABLED` 默认 false。启用需要 `CREEM_TEST_API_KEY`、`CREEM_TEST_WEBHOOK_SECRET` 和已有 `STORE_TOKEN_SECRET`。不得替换原账本加密密钥。生产必须把测试家庭 `/parent/billing/account` 的 UUID 放进独立 `CREEM_TEST_ACCOUNT_TOKENS`；Paddle 和商店测试名单不会自动取得 Creem 权限。非名单家庭看不到测试商品。

在既有 `STORE_PRODUCTS_JSON` 增加 `creem_test` 映射，把 `family_monthly_1/2/10/100` 分别映射为 Creem Test 商品 ID，保留其他渠道映射。商品必须按月、无试用及计量附加费，每次购买数量固定为1。当前 USD 1/2/10/100 是四档名额的测试金额，不代表正式海外定价。

密钥、真实家庭 UUID、商品配置和验收记录只放在仓库外私有 credentials 或服务器权限600的环境文件。前端不需要 Creem 密钥或额外 SDK。

## 支付与权益

- `GET /parent/creem/catalog`：受家庭名单限制的权威测试目录。
- `POST /parent/creem/checkout`：校验名额及已有订阅，服务端创建带家庭 HMAC 绑定的 checkout；未付订单复用，不允许切换档位重复创建。
- `POST /parent/creem/verify`：服务端查询 checkout、订阅和最新付款交易；校验家庭、测试环境、商品及数量，再写现有加密账本。付款返回页参数及其 signature 仅触发核验，不能发权益。
- `GET /parent/creem/manage`：当前家庭绑定的 Creem 客户管理入口，可取消续订。
- `POST /payments/creem/test/notify`：64KiB 限制，按原始请求体验证 `creem-signature` HMAC-SHA256；通知按事件ID去重，重新查权威状态，复用既有持久重试和周期对账。

注册 checkout.completed、subscription.active/paid/scheduled_cancel/canceled/update/past_due/unpaid/expired/paused、refund.created、dispute.created。取消续订保留已付周期；退款或争议以最新权威交易状态撤销权益。不会延长未付款、暂停、欠费、已立即取消订阅的权限。当前仅首次购买和到期后重购，无升降档。不同来源有效订阅互斥。

## 发布与验证

按 deployment.md 及私有生产说明读取现行服务目录、环境文件和摘要，备份数据库与配置。无需依赖更新或数据库迁移。候选基于当前线上版本，只替换核对过的模块。Creem 环境文件仅增加本通道参数及合并后的商品映射，不改变原密钥和其他渠道开关。systemd 环境文件按 drop-in 的实际加载顺序覆盖；Creem 合并商品映射必须在已有 Paddle 配置之后生效，激活后从实际进程核对三通道映射，不能只以候选 canary 代替运行状态验证。

从已提交推送版本按 web/package-lock.json 执行 npm ci + build，只切换家长静态root并保留旧哈希资源。跳转式收银台无需改家长脚本/iframe CSP。官网精确新增上述 POST 通知路径及64KiB上限，保留现有Google/Paddle通知；学生站不增加支付入口。Webhook终点使用永久 HTTPS 通知URL。

```sh
cd server
ENV=test .venv/bin/python -m pytest tests/test_creem_billing.py tests/test_paddle_billing.py tests/test_store_billing.py tests/test_browser.py -q
cd ../web
npm run build
npx playwright test tests/creem.spec.ts tests/paddle.spec.ts
```

本地自动化验证关闭与Live密钥拒绝、生产专用名单、待付不发权益、绑定篡改、跨家庭、商品/数量/环境校验、重复/乱序通知及取消/退款。Chromium/WebKit 验证伪造返回参数不能绕过服务端核验。真实Creem测试卡另用合成家庭单独验收，不替用户生产家庭付款。

回退须先核对当前差异，只恢复此次API目录/drop-in、家长root和Creem通知路由，保留账本增量及其他任务改动，不恢复旧数据库覆盖新交易。
