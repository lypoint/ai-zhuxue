# Web Paddle Sandbox

2026-10-25：Sandbox 商品、Web 收银台与服务端权益闭环已实现，并使用真实 Paddle 测试卡在本地隔离数据库验收。生产 Web 支付仍关闭；本实现不接受 Paddle Live 凭据，不处理真实扣款。

## 配置

配置见 `server/.env.example`。`PADDLE_SANDBOX_ENABLED` 默认 `false`；启用还需 Sandbox API key、`test_` 客户端 token、回调目标的 secret，以及既有 `STORE_TOKEN_SECRET`。不得生成新密钥覆盖已有账本的加密密钥。

在 `STORE_PRODUCTS_JSON` 中新增 `paddle_sandbox` 字典，把 `family_monthly_1`、`family_monthly_2`、`family_monthly_10`、`family_monthly_100` 映射到对应 `pri_…`，保留其他渠道的映射。当前测试目录按既有业务价配置 CNY 66/99/300/3000，按月、含税、无 Paddle 试用、每单数量固定为 1。它们是测试配置，不代表海外正式售价。

API key 需要 `price.read`、`transaction.read/write`、`subscription.read`、`customer_portal_session.write`。创建目录和通知目标时另需相应 `product`、`price`、`client_token`、`notification_setting`、`checkout_settings` 写权限。生产进程启用 Sandbox 时，还必须将测试家庭 `/parent/billing/account` 返回的 UUID 加入 `PADDLE_SANDBOX_TEST_ACCOUNT_TOKENS`；否则拒绝测试购买和权益核验。

在 Sandbox 设置自己的 HTTPS 默认付款地址，并注册公网 `POST /payments/paddle/sandbox/notify`。订阅事件使用 `subscription.created/activated/updated/canceled/paused/past_due/resumed`，交易使用 `transaction.completed`。回调入口只暴露该路径并限制请求体；不可把带模拟身份的本地验收 API 整体通过隧道公开。

家长站模板已允许官方 `https://cdn.paddle.com/paddle/v2/paddle.js` 脚本、`https://sandbox-buy.paddle.com` iframe，以及 Sandbox 收银台/API 连接、官方 Sandbox 收银台样式 `https://sandbox-cdn.paddle.com/paddle/v2/assets/css/paddle.css`。学生站不加载支付脚本。付款链接使用家长站 `/subscription?_ptxn=txn_…`；登录后先由服务端校验交易归属，再打开收银台，不允许通过他人交易链接操作付款。

## 行为与接口

- `GET /parent/paddle/catalog`：从 Paddle 读取配置的真实价格，返回测试 token；关闭时返回空目录。
- `POST /parent/paddle/checkout`：校验家庭、现有订阅、待支付订单、名额数；服务端创建带 HMAC 家庭绑定的交易，重复点击复用未完成交易。当前只允许首次购买或原订阅失效后的购买，不实现升级/降级。
- `POST /parent/paddle/resume`：校验固定付款链接中的交易仍属于当前测试家庭，拒绝其他家庭或已取消交易。
- `POST /parent/paddle/verify`：查询交易完成状态和最新订阅，校验商品、数量及家庭绑定后记入既有订阅账本。浏览器成功事件本身不发权益。
- `GET /parent/paddle/manage`：仅返回当前家庭的 Paddle 订阅取消入口；API key 的 portal session 权限允许生成自动登录链接。
- `POST /payments/paddle/sandbox/notify`：校验原始请求体 HMAC 和 5 秒时间戳，持久化通知，再查询最新权威状态。复用既有通知重试和定期对账；不按通知到达顺序直接覆盖权益。

Sandbox 使用独立渠道 `paddle_sandbox`，不伪装成 Google Play，不累计到国内实收金额；与商店/微信的有效订阅互斥。复用家庭权益读取，无新增表或迁移。密钥、测试库、浏览器资料和付款证据保存在仓库外私有凭据区。

## 验证与边界

本地已完成真实测试卡购买两名额月订阅：收银台成功 → 真实签名回调 200 → 后端权威核验 → Web 展示 2 名额及 Paddle Sandbox 来源，刷新保留。Google 身份和家庭创建使用本地验收夹具，不代表生产 Google 登录和支付联调。

真实 Sandbox 另已验证：取消自动续订后回调更新 `auto_renew=false`，当前两名额保留至周期结束；收银台关闭/重开复用同一交易；拒付卡显示银行拒付，家庭仍为免费试用，没有付费权益。临时回调目标仅供此次本地验收，不能作为长期部署配置。

自动化覆盖开关/凭据缺失、待支付不发权益、交易复用、跨家庭拒绝、绑定篡改、伪造/过期签名、重复/乱序通知及生产测试家庭白名单：

```bash
cd server
ENV=test .venv/bin/python -m pytest tests/test_paddle_billing.py tests/test_store_billing.py tests/test_subscription.py tests/test_browser.py tests/test_monthly_tiers.py -q
cd ../web
npm run build
```

当前范围是 Sandbox 首次月订阅和取消/暂停等订阅状态同步。退款、争议/拒付（chargeback）、计费升级、Paddle Live、正式海外币种定价和 WebKit 真实付款尚未验收，不得据此开放正式收款。固定付款链接及家长/学生 CSP 隔离已有 Chromium/WebKit HTTPS 回归，外部 Paddle SDK 在该自动化测试中使用受控夹具。


## 线上部署顺序

1. 读取当前 API/CMS 的 systemd 生效目录、解释器、环境文件和迁移版本；备份数据库与配置。比较当前运行代码的基线摘要，只发布本次改动，保留现有 JWT/LLM/商店令牌密钥及其他渠道商品映射。
2. API 新增受限 Sandbox 环境文件：四项 Paddle 配置及专用 `PADDLE_SANDBOX_TEST_ACCOUNT_TOKENS`。UUID 从当前真实登录家庭的 `/parent/billing/account` 取得，不根据邮箱或历史测试账号猜测。该名单与 Apple/Google 测试名单独立；非名单家庭的目录返回禁用。
3. 无表结构或依赖变更时，沿用经核实的解释器与锁文件；从当前发布复制候选后，只替换本次 API 模块，验证其他文件摘要，运行离线测试与依赖检查后切换 API。CMS 不需随此次 API 发布切换。
4. 从准确提交构建家长静态产物，保留旧哈希资源供已打开页面使用；更新家长 root 和上述 CSP。学生、官网及已有 Google 通知路由保持。官网为精确的 `POST /payments/paddle/sandbox/notify` 新增原样代理和 64 KiB 上限，其他 Paddle 路径拒绝。配置通过 Caddy 校验后 reload。
5. 更新同一 Sandbox 通知目标到永久 HTTPS 地址，保留该目标的验签密钥，停用旧临时回调；核对默认付款链接为家长订阅页。检查公网 SDK/iframe、非授权家庭不可见、无签名回调被拒绝、API/CMS/双端健康，再由授权家庭使用测试卡验收。

回退只恢复此次 API 工作目录/drop-in、Sandbox 环境配置、家长静态 root/CSP 和新增回调代理；先比较当前摘要，避免覆盖并行任务。保留账本与数据库增量，不能恢复旧 dump 覆盖已发生的事务。
