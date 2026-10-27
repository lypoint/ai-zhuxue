# 学生端与家长端语言支持

所有 Flutter 渠道共用 `app_core` 的语言配置；两个 Web 端也使用同一份清单。
`server/app/locales.json` 是 78 个语言/地区选项、原生名称及 RTL 标记的来源。
修改清单后运行 `python3 scripts/sync_locales.py`，生成 Flutter 配置和 iOS 语言、资源声明。

- 保留地区选择：`es-US`、`es-419`、`es`；`fr-FR`、`fr-CA`；`pt-BR`、`pt-PT`；`zh-Hant`、`zh-Hant-HK`、`zh-Hans`；`ms-MY`、`ms`。
- `fil` 与 `tl` 分别对应 Filipino 与 Tagalog；`nb` 对应 Norsk (Bokmål)。
- 用户给定的阿塞拜疆语名称使用西里尔文字，因此采用 `az-Cyrl`；译文转写参考 [Unicode CLDR Azerbaijani-Latin/BGN](https://github.com/unicode-org/cldr/blob/main/common/transforms/Azerbaijani-Latin-BGN.xml)。
- 阿拉伯语、希伯来语、乌尔都语、波斯语使用 RTL。切换语言不改动用户正文、聊天历史或家庭资料。
- Flutter 的“跟随系统”自动识别地区；手动选择使用设备偏好持久化，退出登录不重置。Web 在本地保存选择。

## 译文与校对

原有 7 种语言的既有译文保留。新增内容使用 Google 机器翻译生成，尚未经过母语审校。西班牙语地区选项复用现有通用西班牙语译文；法语、马来语等地区选项可能暂时具有相同译文，后续可独立校对。

- Flutter 界面及隐私弹窗：`app/app_core/assets/i18n/catalog.json`。
- Web 构建前从源词表生成 `web/src/generated-locales/`（不提交），浏览器仅加载当前语言，切换失败时保留原选择并提示网络错误。
- Web 新增语言文案：`web/src/expanded-translations.json`；既有文案仍使用 `web-translations.json` 和 `i18n.ts`。
- 服务端固定安全提示：`server/app/safety-translations.json`。运行时不请求翻译服务。
- iOS 系统权限提示：三个 iOS 工程的 `Runner/<locale>.lproj/InfoPlist.strings`。

机器翻译时保护 `{0}` 和 `{{count}}` 等参数，再校验参数数量和内容。母语校对时也必须保留这些参数。优先校对隐私授权、安全提示、账户删除及订阅文案，其次校对长文布局与地区用词。

Flutter 内置控件使用 SDK 自带的本地化委托，78 个选项逐一进行组件切换验证。系统控件、日期和数字的地区用词及文字变体受 SDK 数据覆盖限制，例如阿塞拜疆语内置控件可能使用拉丁文字。

聊天接口允许全部清单语种，并使用可信语言名称约束老师回复。全语种语义审核应使用已有的 LLM 围栏模式；规则降级模式仍只有原来的有限词表，不能视为完整多语种安全审核，本次没有放宽审核策略。

## 验证

- `app/app_core`：`flutter test test/language_test.dart`，检查完整键集、参数、78 种语言切换、输入保留、持久化与 RTL。
- `server`：`python -m pytest tests/test_language.py -q`，检查普通/流式聊天、安全提示、地区归一化及非法语言拒绝。
- `web`：`npm run check`，检查所有语言的完整文案、插值和地区识别。
- iOS：用 `plutil -lint` 检查 plist、工程文件及新增权限提示文件；发行构建与母语真机视觉验收另行执行。

## 国际官网

国际官网的首页、定价、隐私、条款和 AUP 使用同一份 78 个语言/地区清单。私有源码中的 `scripts/sync_site_languages.py` 从本仓库 `server/app/locales.json` 同步选择器、原生名称和 RTL 标记；`scripts/check_site_i18n.py` 检查清单一致及五页词条完整性。

官网保留原有七语译文，新增语言为机器翻译，尚未完成母语审校；部分地区选项共用通用译文。浏览器按需读取 `/assets/locales/<version>/<tag>.json`，不在首屏下载全部语言。地区识别规则与学习站一致，兼容原官网保存的 zh-CN/zh-TW 偏好；加载失败保留当前语言，并可重新选择重试。四种 RTL 语言同步设置页面方向。
