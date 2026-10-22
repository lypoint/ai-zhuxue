# Vendor Frameworks

为遵守商业 SDK 授权与开源合规要求，专有闭源 SDK（如 `ATAuthSDK_D.xcframework`）已在 Git 中忽略（.gitignore），不随本开源代码仓库分发。

本工程支持**无闭源 SDK 时的自动解耦与平滑降级**：
- 开源克隆与 CI 环境下，直接 `pod install` 与构建即可成功编译，应用会自动降级为短信验证码登录。

## 生产发版说明
如需打包支持真实中国大陆运营商一键登录的 iOS 正式包：
1. 请登录[阿里云号码认证控制台](https://help.aliyun.com/zh/pnvs/developer-reference/the-ios-client-access)下载对应版本的官方商业动态库 SDK（`ATAuthSDK_D.xcframework`）；
2. 解压并将商业版 `ATAuthSDK_D.xcframework` 放置到当前目录下（或通过环境变量 `ALIYUN_AUTH_IOS_SDK_PATH` 指定）；
3. 配合对应 Bundle ID 的 `ALIYUN_AUTH_SDK_KEY` 环境变量执行发布脚本即可自动注入并完成校验。
