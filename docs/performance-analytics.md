# 学习链路耗时分析

用于分析浏览器 → 学习站 Caddy → 业务 API → 模型/图片存储的耗时，以及后续减少代理层的实测效果。CMS「概览 → 链路耗时」或 `GET /admin/analytics/performance?start=YYYY-MM-DD&end=YYYY-MM-DD` 可查看，仅运营管理员可读。

## 采集与配对

每次聊天 HTTP 尝试产生独立 UUID `trace_id`，请求头 `X-Trace-Id` 传递，响应头返回规范化 UUID。重试用新 UUID；服务端另记录内部问题 ID 和尝试次数。图片上传同样传递 UUID，图片读取在 URL 附带一次加载的随机 `_trace` UUID（不含身份信息），并通过 Resource Timing 配对；优先采用响应 `Server-Timing: trace;desc="UUID"`。部分 WebKit 图片元素不提供 Server-Timing 明细时，仍可用随机 UUID 配对浏览器总时间和服务端阶段，但网关差值保持缺失。随机 UUID 随图片来源/重试版本或组件重新挂载更新，不增加额外图片请求。

服务端和学习站浏览器分别上报，按 UUID、家庭、孩子、操作类型联合匹配。身份来自已认证会话，不接受浏览器指定家庭/孩子。浏览器只接受固定计时字段、有限非负数、最长一小时；需 Origin/CSRF 和学生会话，限每孩子每分钟 60 次，重复上报不覆盖。浏览器数据仍是不可信观测，不应作为计费、安全或服务端事实依据。

服务端/学习站统计无需同意；家长 Web 仍遵循 Firebase 同意机制，本次不采集家长页面性能。无问题正文、图片内容、URL、令牌、邮箱或持久浏览器标识；内部家庭/孩子/问题 ID 用于配对和删除。账户完整删除时同步删除性能记录，停用家庭不参与报告。

## 计时定义（全部毫秒）

所有时间使用各节点的单调时钟；不相减不同机器的墙上时间。

| 字段 | 起止与含义 |
| --- | --- |
| `browser_headers_ms` | 浏览器开始本次 fetch 至收到响应头；图片资源为 Resource Timing 的 responseStart − startTime |
| `browser_first_delta_ms` | 开始 fetch 至解析到首个非空 delta/replace，在交给界面回调前计时；不是像素绘制时间 |
| `browser_done_ms` / `browser_total_ms` | 开始 fetch 至解析 done / 流读取结束或失败；上传 done 为解析完 JSON；图片 total 为资源完成，不代表解码/绘制成功 |
| `edge_upstream_headers_ms` | 学习站 Caddy 的 upstream.latency_ms，即开始上游 RoundTrip 至响应头；包括连接、写请求、代理队列和等待，不是纯网络 RTT |
| `server_headers_ms` / `server_total_ms` | ASGI 收到请求至产生响应头 / 请求处理完成（含流与清理，不含性能记录写入） |
| `server_first_delta_ms` / `server_done_ms` | ASGI 开始至生成首个非空文本 SSE / done 事件，尚不保证网络送达 |
| `policy_ms` | 权益、配额、休息时段检查 |
| `prepare_images_ms` / `context_ms` | 提问图片准备 / 历史上下文与提示组装 |
| `input_review_ms` / `output_review_ms` | 输入审核 / 输出安全复核，可能包含内部模型和数据库操作 |
| `model_ms` | 应用观察到的聊天模型调用/迭代总时间，包含上游网络；实时流模式还可能包含发送下游的背压 |
| `model_first_token_ms` | 聊天模型调用开始至上游首个非空文本 token；仅真实流式调用提供，非推理内部时间 |
| `persist_ms` | 聊天处理显式计时的数据库提交累计；不是全请求所有 SQL 时间 |
| `upload_receive_ms` / `image_sanitize_ms` | 接收上传正文 / 图片清理 |
| `storage_upload_ms` / `image_review_ms` / `storage_read_ms` | 图片存储上传 / 图片审核 / 从存储下载 |

阶段有嵌套、未覆盖操作和实时流背压，不能简单相加等于总耗时。安全优先的 buffered 模式需先完成模型输出及复核才发首字，必须与 realtime 分组比较。未发生、未成功采集的阶段保持缺失，不能补零。

## 差值及如何评估减少一层服务

先对同一次请求计算以下差值，再汇总 P50/P95，禁止把独立分布的 P95 直接相减：

- `edge_api_headers_residual_ms` = edge_upstream_headers − server_headers，估计学习站到业务 API 的往返及中间代理开销。
- `browser_edge_headers_residual_ms` = browser_headers − edge_upstream_headers，估计浏览器到学习站及浏览器调度等开销。
- `first_delta_path_residual_ms` = browser_first_delta − server_first_delta，观察请求进入到首个文本抵达之间，服务端以外的路径、排队及解析开销。

这些是包含双向路径与未观测处理的时间差，不是某一台机器的独占时间，也不是迁移收益保证。负差值单独计为异常请求，不截断成零、不纳入差值分位数。浏览器失败/取消统计数量，其不完整计时不混入成功浏览器耗时；图片资源完成单列为 incomplete。应同时看配对覆盖率、各指标样本数、服务端失败/拒绝/未完成分组；缺网、退出页面、浏览器不支持 Resource Timing、限流、采集写入失败都会造成缺样。

保持现状先以 `PERFORMANCE_VARIANT=baseline` 采样；未来实际调整链路后设置 `direct`，`PERFORMANCE_NODE` 使用固定节点标签（字母/数字/下划线/短横线，最多 32 字符）。配置仅为标记，不改变任何路由。按相同模型、审核模式、文本/图片、结果及首次/重试组比较。优先随机分流或交替时间窗，用相同题目/图片、近似输入输出长度、地域网络与负载验证；同时比较首字、完成时间、错误率及样本量。真正可宣称的提速是改路前后的端到端差异，不能只引用当前残差。

## 部署与维护

先迁移 `4a7b9c1d3e5f`（依赖孩子学习设置迁移 `3f6a8b0c2d4e`），发布 API/CMS，再发布学习站 Web 和其 Caddy 配置。仅学习站最外层增加 `edge_upstream_headers`，中间代理必须透传 `X-Trace-Id` 与全部 `Server-Timing`，不能覆盖或再加同名 edge 指标。API 单独发布可以先收集服务端阶段；网关未更新时不产生网关差值。

报告按服务端完成时间筛选最多 7 个 UTC 自然日，额外扫描前后一小时用于匹配稍晚到达的浏览器上报。原始扫描最多 50,000 行（含浏览器），超限请缩短时间窗。当前全量采集上述操作，未实现自动过期清理或日聚合；运营需按实际流量制定留存/归档，容量增大时再加聚合。性能记录在响应发送后以独立短事务写入，失败不改变学习响应，只输出固定失败日志，不输出 SQL 或连接信息。

本地 HTTPS 验收使用当前 `web/Caddyfile` 和双层代理，覆盖流式响应头透传及聊天/上传/读取配对；本地模拟模型不能替代生产网络与真实模型的性能实测。
