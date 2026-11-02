# 学生端

本工程是国内 Android 学生入口，同时向学生渠道壳提供共享界面。Google Play 使用 `../app_student_googleplay`，App Store 使用 `../app_student_appstore`，不得混用渠道产物。

打包前必读 [部署与运维](../../docs/deployment.md#4-flutter-构建产物)：Flutter 3.38.10、匹配锁文件的 `PUB_HOSTED_URL`、严格依赖解析、显式生产 `API_BASE`、iOS Xcode 16、正式签名及产物验收。直接运行 Flutter 时，环境变量不会自动传成 Dart define。

学生文字与待发图片草稿保存于应用私有目录，按 API、渠道和家庭／学生标识隔离，重启可恢复；历史对话暂时离线不影响草稿恢复。重新打开后图片重新上传，只有消息入库确认后才清除已发草稿；发送失败保留输入。草稿超过 7 天不恢复，退出、注销或会话失效时清理，并使旧页面排队写入失效。日期与评估范围按家庭时区计算。
