# 老师渠道配置

CMS 的 LLM 分组支持设置适用渠道：`all`（全部渠道）、`wechat`（微信）、`appstore`（App Store）、`googleplay`（Google Play）。可在列表中直接切换，也可在新建、编辑分组时设置。渠道修改使用已有老师配置权限，并记录操作审计。

升级数据库后，已有老师自动设为 `all`，保持原有可见性。若同一模型需要不同的老师名字、免费额度或排序，分别创建对应渠道的分组。

客户端通过 `X-App-Channel` 请求头传递渠道：

- 家长端三个独立入口固定使用各自的渠道，无需额外编译参数。
- 学生端 Android 默认 `wechat`，iOS 默认 `appstore`；Google Play 学生包必须使用 `--dart-define=APP_CHANNEL=googleplay`。
- 未携带请求头的旧客户端及 Web 默认为 `wechat`；未知渠道返回 422。

```sh
cd app/app_student
flutter build apk --dart-define=APP_CHANNEL=googleplay
# 本地验收可增加 --debug --dart-define=API_BASE=http://127.0.0.1:18100
# 并执行 adb reverse tcp:18100 tcp:18100
```

`GET /chat/teachers` 仅返回已激活且适用当前渠道或全部渠道的老师。默认老师、家庭标签、上次选择均在可见老师内解析；上次老师不适用当前渠道时自动回退。选择老师及新建普通/流式对话均校验渠道，不能通过提交其他渠道的老师 ID 绕过筛选。当前渠道没有老师时返回空列表，新建对话提示暂无老师，不回退到其他渠道。

`GET /parent/subscription` 的 `teachers` 返回同一渠道规则下的老师角色信息和每日免费额度，`free_teacher_count` 同步按渠道计算；家长端在“账户”订阅卡展示名单。不返回模型地址或密钥。

历史会话保留原老师快照与继续对话能力，渠道调整不会迁移或删除历史。渠道头用于分发配置，不是独立的身份或会员授权凭证；订阅权益仍按家庭检查。

## 2026-10-16 验收记录

使用独立本地 SQLite、测试家庭和四位测试老师，未修改线上数据。

| 验收项 | 结果 |
|---|---|
| CMS 列表切换 App Store → Google Play → App Store | 刷新后保存正确，审计记录包含前后渠道 |
| Android 学生端微信包 | 仅通用老师、微信专属老师 |
| Android 学生端 Google Play 包 | 仅通用老师、谷歌专属老师 |
| Android 家长端微信包，账户订阅卡 | 仅通用老师、微信专属老师 |
| Android 家长端 Google Play 包，账户订阅卡 | 仅通用老师、谷歌专属老师 |
| 其他渠道老师 ID 选择及新建普通/流式对话 | 404 |
| 切换渠道后，上次老师不可用 | 回退到当前渠道可见老师 |
| 当前渠道没有老师 | 列表为空，新对话 503 |
| 迁移升级、回退、再升级 | 保留原老师，渠道默认 all |

测试：后端与 CMS 293 项、共享库 8 项、学生端 23 项、家长端 15 项通过；共享库及双端静态分析无问题。Google Play 家长包使用本机 Flutter 3.38.10，其余调试包使用 Flutter 3.32.8。模拟器为 Pixel 9 Pro API 36.1（emulator-5554）。

范围：本次验收覆盖渠道配置、名单与选择规则；未验收 iOS 真机、商店支付和真实模型回复。
