# Google Play 海外双端 Web 实施与验收

目标：实现家长与学生 Web；订阅支付按要求留空。记录日期：2026-10-24。

用户已明确批准“现在上线并继续验收”，生产 API、迁移、官网及双端 HTTPS 已启用。以下区分本地回归、真实线上验收与仍未验证的设备范围，不能把模拟器或夹具当作全部真机验收。

## 当前线上状态

- 品牌 AI StudyNest；官网 https://aistudynest.com、家长 https://parents.aistudynest.com、学生 https://learn.aistudynest.com。DNS 三站 A 记录已核实；新增子域未改 MX/TXT。
- 双站生产构建与 API 已启用；迁移版本 `0c3e7a9b2d41`。具体不可变发布目录、备份和恢复步骤保存在私有生产说明，部署前仍须读当前流程并检查运行状态。
- Google 现有 Web client audience 与 API 一致，家长 Origin 已保存；品牌及官网/政策 URL 已更新并重新读取。用户在 Chrome 完成真实 Google 登录，家庭、会话、试用权益读取成功。学生站不加载 Google 登录或支付。
- 主 API/CMS 健康，验单/通知现已迁至官网 Origin，旧域名入口返回 410；旧国内 `/web` 及别名返回 410。跨机角色代理保留正确 Host、真实客户端地址与及时 SSE，只开放相应角色接口。
- Cookie 实测为 host-only、Secure、HttpOnly、Strict 的 `__Host-` Cookie；错误 Origin/缺失 CSRF 返回 403，无会话 401，跨角色/普通原生学生接口不公开。Web 支付开关 false，订阅页仅显示权益。

## 真实线上家庭验收

仅使用本次新建的测试家庭与合成数据，未操作其他家庭。用户实际 Google 登录后创建测试孩子 `Web Acceptance 20261024`（ID 13），设置 Asia/Shanghai，绑定学生浏览器。

- 真实迪普思科流式文字：7×8 解释正确，家长审查和学生页均能显示公式。真实上传、裁剪、私有存储、审核、图片识别：2+2 图片正确识别并引导计数。
- 两个真实图示任务均 ready。首个图示被一致性审查阻止，人工重试后成功；已完成任务复用原 ID。此项是有限合成样本，不能推导普遍正确率。
- 修复真实回答的 `\(...\)` / `\[...\]` 数学分隔符兼容，代码片段与未闭合流式代码围栏保留；共享渲染组件覆盖双端。修复 rect/ellipse 图示丢失数字标签。专项回归与实际图示截图均已检查。
- 学生收藏及原消息入口、举报及历史、学习反馈、参与星、约定接受和兑换通过；家长已兑现，并确认刷新后的 Fulfilled 状态。
- 学生成绩新增/编辑/删除/恢复/版本/趋势、学业评估通过；家长修正成绩为 10/10，版本 5 作者为 Parent，历史保留学生版本与删除/恢复记录。
- 家长身心观察生成、确认并重新导出后 acknowledged；导出 200，包含对话、成绩及版本、两类评估、学习、用量和收藏。通知实际单条打开后未读由 1 变 0；分页边界和全部已读由本地浏览器覆盖。
- 订阅页显示试用有效、到期时间、1 个名额和来源，无购买按钮；设置具备同站隐私、帮助、条款、退出与注销入口。注销整个家庭未在真实用户账号上执行，由隔离回归覆盖。
- 用户允许忽略已下架的鸡皮提模型配置；没有修改该老师，也未记为该模型通过。

真实证据在仓库外 `designs/international-web-20261024/acceptance/`：`live-public-browsers.json`、`live-real-images.json`、`live-real-diagram.png`、`live-real-image-answer.png`、`live-student-real-text.png`、`live-student-features.json`、`live-parent-features.json`。私有部署/安全检查记录在 `credentials/web-acceptance-20261024/`。

## Android 16 线上模拟器

用户指定独占 `emulator-5554`，全程使用 ADB。正式 HTTPS 连接、首次说明、真实历史对话/公式/图片加载通过。重绑后旧桌面学生会话及历史接口均 401，单设备限制生效。输入合成草稿 `draft`，切到 HOME 再回原 Chrome 后保留；通过系统照片选择器选取本次合成算术图，裁剪、真实审核上传后显示 Saved。截图保存在 `android-live-*.png`。家长通过设备管理撤销后，Android 自动回到连接页面。旋转保留草稿；低高度发送按钮的可到达性由双引擎专项覆盖，Android 横屏截图本身不作为完整通过证据。模拟器不等同于物理摄像头或 iPad。

## 测试数据清理

已通过家长接口彻底删除精确核对过昵称和 ID 的测试孩子，返回 200/purged；家庭剩余孩子 0、已删孩子导出 404、家长会话 200。生产库只读检查确认该孩子的对话、消息、设备、任务、收藏、学习反馈、奖励、成绩、评估、用量和 Web 会话全部 0；5 个本次私有图片对象已删除，媒体残留 0。撤销的桌面学生会话文件和本次模拟器文件已移除。未删除家庭或改变试用权益。证据 `live-cleanup.json`，私有明细 `credentials/web-acceptance-20261024/cleanup-test-data.json`。

## 本地验证证据

- 服务端 SQLite：`cd server && .venv/bin/python -m pytest -q --disable-warnings`，469 passed、1 skipped（26.55 秒）；跳过项仅验证 PostgreSQL 连接会话时区。
- 服务端 PostgreSQL 15：独立临时实例，仅 Unix socket、无 TCP 监听；同一完整 pytest 命令，470 passed（26.20 秒）。验证连接 UTC、跨日用量、四个并发标签页不重复计时、四个独立进程共享限流；迁移和测试后停止实例并删除临时数据。
- 数据库兼容性修复：用量页统一比较 UTC 时间；应用与 Alembic 连接固定 UTC，避免数据库服务器本地时区重解释无时区时间。回归断言比较时间点而非数据库驱动的字符串样式，举报缺失源消息夹具保留外键一致性，审计记录按主键排序；没有开通 Web 支付。
- 前端：`cd web && npm run build`，七语检查、TypeScript、家长和学生生产构建通过；`npm audit --audit-level=low`，0 vulnerabilities。构建仍提示共享 chunk 超过 500 kB，首次加载性能需在目标网络评估。
- 浏览器：`cd web && npm test`，9 条独立流程 × Chromium/WebKit，18 passed（3.3 分钟）。覆盖家庭/设备/资料/限制/通知、文字/公式/图片/旋转/图示、收藏/举报/反馈追问/奖励、成绩/评估与建议、断网/草稿/停止重试、七语、注销及主屏幕配置。
- 最终补充：修正视口变化与键盘焦点跟随后，`npm test -- --grep 'family connects|reading position'`，4 passed（58.3 秒）；补齐操作错误翻译后，`npm test -- --grep 'offline drafts|browser errors'`，4 passed（24.2 秒），其中新增的七语错误流程在两种引擎各通过一次。共 10 条场景、20 个浏览器测试项在上述运行中验证；未把桌面引擎当作真机。
- 浏览器夹具：`server/tools/web_acceptance_server.py` 仅绑定 loopback 8810，临时 SQLite；真实 API 路由、权限和持久化，Google 身份、模型、图示、对象存储与图片审核由确定性夹具替代。测试不产生实际订单或扣款。
- 生产构建 HTTPS：`CADDY_BIN=/path/to/caddy npm run test:https`，Caddy v2.11.7，完整 22 passed（3.7 分钟，10 条业务场景加 1 条网关场景 × Chromium/WebKit）。使用实际双端 dist、实际 Caddy 模板及 HTTPS API 上游，验证角色 Host 隔离、深链接、CSP/HSTS/no-store、Secure/HttpOnly/host-only/Strict 的 `__Host-` Cookie、Origin 拒绝和 SSE 首帧先于慢响应完成；身份/模型/图片仍为夹具。修复 HTTPS 上游自动改写 Host，以及 WebKit 历史图片焦点滚动被强制拉回底部的问题。
- 补充 HTTPS：自定义老师名称在学生选择器/页头/回答及家长审查中保留，2 passed（33.3 秒）；异步图示排队、刷新后草稿和任务恢复、首次轮询 503 后恢复、完成图示复用及家长读取，2 passed（28.2 秒）。后者是新增第 11 条业务场景，未与前述完整 22 项合并重跑，单独记录两次补测结果。
- 数据迁移：全新 SQLite `alembic upgrade head` → `downgrade f1a2b3c4d5e6` → `upgrade head`，在 SQLite 和 PostgreSQL 15 均通过；临时数据库已删除。
- 官网：`python3 site/scripts/check_site_i18n.py` 与 `python3 site/googleplay/scripts/check_site_i18n.py` 均通过，分别 182/176 条、七语、三页。`site/` 为外层私有目录，不属于 product 仓库。
- 视觉：已检查家长桌面/手机、学生平板截图；稳定副本在外层 `designs/international-web-20261024/acceptance/`，分别保存 Chromium 与 WebKit 版本，并保留数据库、构建和浏览器终态日志；示例数据均为测试数据。
- Android 早期无设备的检查已被上述 Android 16 线上模拟器验收补充；桌面 WebKit 仍不等同于 iPad 真机。

CI 已配置 SQLite/PostgreSQL 服务端矩阵，以及 Web 构建、Chromium/WebKit 流程和失败产物保存；尚未在 GitHub 远端执行，不把配置文件当作 CI 绿灯。

## 补充专项回归

- 数学分隔符兼容及双端完整家庭流程，使用生产构建与 HTTPS 跨机 Origin 桥接模型，Chromium/WebKit 共 2 passed（53.9 秒）；日志 `math-https-regression.log`。
- 图示标签修复后图片服务专项 38 passed（2.04 秒）；日志 `diagram-label-tests.log`。
- 真实公网 Chromium/WebKit 检查官网/政策、学生深链接、同源请求、无横向溢出与双站入口；记录 `live-public-browsers.json`。
- 彻底删除修复：补齐学习反馈/奖励依赖的删除顺序，SQLite 16 passed / 1 skipped、PostgreSQL 17 passed（0.88 秒）；PostgreSQL 日志 `purge-postgres.log`。
- 横屏修复：聊天主区不受通用页面 padding 覆盖，低高度输入区可滚动，带图草稿可到达 Send；生产 HTTPS 构建 Chromium/WebKit 2 passed（14.3 秒），日志 `landscape-https.log`；相关家庭/阅读位置 HTTPS 补测 4 passed（1.2 分钟），日志 `landscape-family-regression.log`。

## 剩余范围和已知限制

1. 用户于 2026-10-24 明确“暂时不真机验收”：物理 Android/iPad/iPhone 的摄像头、系统键盘/分屏/旋转、锁屏、主屏幕安装和设备网站白名单项目延期；不记为通过。网页自身不提供系统锁定能力。
2. 七语语义键、窄屏和错误流程已自动检查，专业母语润色未认证；已有受控弱网首屏对比与三类真实图示样例检查，但不代表所有目标市场网络或模型普遍准确率。当前没有真实订单，付费交易按支付留空范围不作购买验收。
3. 学业评估仍是规则估计；本轮已修复七语常见回答语言指令误记英语的问题。未覆盖表达、隐含语义和主要信息在图片里的题目仍可能分科不充分；不代表学校成绩或医学诊断。
4. 订阅支付继续留空，原生 App 本轮未重新打包；真实家庭注销、真实审核拒绝素材、资源过期等破坏性/等待边界由隔离回归覆盖，未声称在生产逐一制造。

以上保留为未验收边界，不将“已上线”误报成“所有物理设备已通过”。

## 验单域名后续切换

用户确认旧路由无实际订单并授权全量切换后，主 API 中继、Google 公钥和 Pub/Sub 端点/audience 已统一使用新官网域名。真实 Pub/Sub 认证测试推送返回 200，旧验单/通知入口返回 410。23 项验单/通知测试通过；真实订单与网页购买仍不在本轮验证范围。具体配置和恢复资料见私有生产说明。

## 联系方式上线验证

2026-10-24：Web 双端帮助/隐私/条款窗口及 Google Play 官网三页页脚增加用户指定的联系邮箱 mailto 链接。构建与七语完整性检查通过；正式 HTTPS 上 Chromium/WebKit 分别检查双端帮助窗口和官网三页，各切换七语，邮箱链接正确且 375px 无横向溢出。截图已查看，证据 contact-live-checks.json 与 *-contact-*.png。该检查没有发送邮件。


## 当前软件回归复核（2026-10-24）

- 完整 SQLite：472 passed、1 skipped（28.02秒）；PostgreSQL：473 passed（30.77秒）；完整生产构建 HTTPS 跨机桥接模型：24 passed（4.5分钟），覆盖11条业务流程和1条网关场景×双引擎。日志 final-sqlite-all.log、final-postgres-all.log、final-https-all.log；这些 API/浏览器流程仍使用隔离身份与模型夹具。
- 后续补测：HEIC/超限/损坏图片拒绝后仍可正常选图、上传失败重试、数学图/旋转及横屏草稿，双引擎4 passed（56.4秒）；私有下载失败返回503后重试生成新的上游签名，1 passed（0.22秒）。
- 新发现并修复：学生对话列表误用成绩“版本历史”的文案，改用独立七语标签；会话运行时失效或首次加载401时遗漏清理 sessionStorage 私有草稿，现已清理且保留无关偏好。正常有效会话刷新不丢草稿；HTTPS会话/网关专项4 passed（27.1秒），日志 session-storage-https.log。
- 正式双站首次401清理：Chromium/WebKit×双角色共4项通过，private-storage-live.json；正式静态脚本解压后与检查过的 dist 字节一致，final-delivery.json。没有操作真实家庭或留下新测试孩子。
- 性能：双端原静态脚本未压缩，现仅 /assets/* 启用zstd/gzip，动态 API/SSE 保持原行为。1.6Mbps/150ms/CPU4x 的单次冷缓存对比：学生脚本940071→277211字节，可操作7.914→4.484秒；家长936139→275677字节，可操作8.590→4.568秒。证据 performance-before.json、performance-after.json。不是实际目标市场网络或所有设备的速度保证。

真机按用户要求延期；上述结果证明软件流程及本轮修复，不代替延期的物理设备检查或模型准确率题库。


## 学业评估后续修复（2026-10-24）

已修复回答语言指令误计学科：识别七语常见“用英语回答/解释”表达，词汇、语法等实际语言学习内容仍保留。原验收两条合成提示在新规则下为总提问2条、数学1条、英语0条；图片题仅凭提示文字不强行推断数学。原始消息不被改写。缓存输入版本升级为v6，旧快照保留，新生成不再命中旧规则结果。

修复评估起止日期相同时被拒绝的问题：学业双端及家长身心观察可生成单日评估，倒序和无效日期仍422。两类评估的业务日界仍使用家庭时区。18条分类回归含七语指令、真实语言学习及跨学科提问；API回归同时确认父/学生复用新缓存、旧快照及原消息保留。

完整SQLite 491 passed/1 skipped（29.13秒）、PostgreSQL492 passed（30.36秒）；新规则/缓存/日期及会话专项74 passed/1 skipped（0.91秒）；完整双端家庭HTTPS流程Chromium/WebKit 2 passed（55.4秒），包含同一天的三类生成操作。日志 assessment-final-sqlite.log、assessment-final-postgres.log、assessment-response-language.log、assessment-one-day-https.log。

API已部署。服务器实际部署代码和Python环境使用隔离临时库复验双端学业及家长身心单日接口通过，数据清理完成，未改真实家庭；实际运行服务健康及静态脚本交付复核通过。此canary不是向真实家庭的业务接口造数据；真机仍按用户要求延期。


## 三类真实图示样例检查（2026-10-24）

从当前运行 API 的配置选择 Google Play 可用的首选老师，使用当前 image_jobs.execute 中实际规划提示、deepseek-v4.1-flash 规划模型、当前程序绘图器和 qwen3-vl-plus 一致性复核模型。输入仅为合成教材题，复核直接读取合成图的数据URL；没有创建家庭、消息、图片任务或七牛对象，没有改老师配置。使用6次供应商调用，令牌用量保留在报告中，没有记为真实学生消费。

- 加法：2个蓝点+2个绿点，结果4个黑点；组数与总数标签正确。13个形状，规划/复核合计11.12秒。
- 数轴：0、1/2、1刻度等距，1/2位于中点，标签未裁切。7个形状，5.86秒。
- 长方形：边长4和3，面积12平方单位，标签不重叠；不将屏幕像素当作实际单位长度。4个形状，4.56秒。

三例均通过当前模型复核，本会话也逐张查看原图并检查上述关系；不是只根据JSON或模型结论记为通过。证据 diagram-quality-bank/report.json 和同目录三张JPG，报告附图片SHA-256及视觉检查说明。此样例组不代表全部模型题目准确率，也不替代此前已验证的真实存储/审核/双端页面链路或延期的真机检查。

目前可独立执行的软件回归、有限真实服务联调及上述样例组已记录。完整目标仍保留物理设备验收项目，按用户“暂时不真机验收”延期；不会用模拟器或桌面浏览器证明摄像头、系统白名单及锁屏行为。
