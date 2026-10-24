# AI StudyNest · Google Play 海外 Web

当前域名（2026-10-24 已上线）：官网 `https://aistudynest.com`，家长端 `https://parents.aistudynest.com`，学生端 `https://learn.aistudynest.com`。DNS/TLS 与家长真实 Google 登录已验证；后续发布仍须复核实际配置。验单及通知已迁至官网，旧 `i.lix.do` 返回 410；具体步骤见 [部署与运维](../docs/deployment.md#6-google-play-海外双端-web)，验收证据见 [Web 验收记录](../docs/web-acceptance.md)。

React/TypeScript/Vite，一个锁文件、家长和学生独立构建；复用 FastAPI 业务 API。

```sh
npm ci
npm run dev:parent
# 第二个终端
npm run dev:student
```

开发代理默认 `http://127.0.0.1:8100`，可通过 `WEB_DEV_API` 指定。后端开发配置 `WEB_ENABLED=true`、`WEB_PARENT_ORIGIN=http://localhost:5173`、`WEB_STUDENT_ORIGIN=http://localhost:5174`。浏览器应使用 localhost，与可信 Origin 配置一致。

```sh
npm run check
npm run build
npx playwright install chromium webkit
npm test
```

测试独立启用 8810 后端及 5173/5174 前端，端口占用时拒绝复用。测试后端使用隔离 SQLite，以及明确的 Google/模型/图片外部依赖夹具；不代表真实 Google 登录、模型或对象存储已验收。

可用 Caddy 2.11+ 验证实际生产构建和 HTTPS 网关：

```sh
CADDY_BIN=/absolute/path/to/caddy npm run test:https
```

该命令先构建，再启动家长 `https://localhost:18443`、学生 `https://127.0.0.1:19443`、HTTPS API 桥接 18811 及隔离 API 8810；端口必须空闲。自动生成临时证书和隔离数据库，仅测试浏览器忽略测试证书错误，上游显式信任临时 CA；不安装系统信任、不修改生产配置。测试后停止本次进程并删除临时证书/数据库。使用真实 Caddy 模板、静态产物、安全响应头和 Secure Cookie；Google 身份、模型、审核及存储仍由夹具替代。

产物为 `dist/parent/`、`dist/student/`。生产不需要 Node 服务。`Caddyfile` 为双独立 HTTPS Origin 的配置模板；部署步骤及必需配置见 `../docs/deployment.md`。学生端资源、字体、图片上传与读取均为同源；不运行 Google 登录或付款组件。

订阅页仅展示已有家庭权益、购买来源与原渠道管理入口；购买和支付留空，浏览器适配层拒绝支付接口。

两端提供各自的 Web manifest 和同源主屏幕图标；没有 Service Worker，不缓存私有学习数据，也不提供离线学习或设备锁定。浏览器与主屏幕入口的会话存储可能不同；需要重新连接时，使用原孩子的替换设备流程，不新建孩子。图标沿用 Lucide Sprout，授权见 `public/lucide-license.txt`；随构建提供 Inter 与 KaTeX 的许可证副本。

进度与尚未通过项见 `../docs/web-acceptance.md`。浏览器自动化不代替真实 iPad/Android 设备验证。

跨机双层代理可用 `CADDY_BIN=/absolute/path/to/caddy WEB_TEST_ORIGIN_BRIDGE=1 npm run test:https -- --grep "HTTPS gateway"` 补验：第一层按上游 TLS 主机发送 Host，第二层按角色路由恢复应用 Host，保留转发客户端地址并及时刷新 SSE。该本地模式仅验证链路行为；生产来源 IP 限制还须在实际两台服务器验证。
