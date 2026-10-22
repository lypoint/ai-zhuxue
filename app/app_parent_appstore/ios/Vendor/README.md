# Vendor Frameworks

当前目录下包含 `ATAuthSDK_D.xcframework` 的**开源编译桩（Stub Framework）**，仅声明公开接口与默认降级逻辑，用于支持 CI 构建与开源环境开箱即用编译。

## 生产发版说明
如需打包支持真实中国大陆运营商一键登录的 iOS 安装包：
1. 请登录[阿里云号码认证控制台](https://help.aliyun.com/zh/pnvs/developer-reference/the-ios-client-access)下载对应版本的官方商业动态库 SDK（`ATAuthSDK_D.xcframework`）；
2. 解压并将商业版 `ATAuthSDK_D.xcframework` 覆盖到当前目录下；
3. 执行 `pod install` 并配合对应 Bundle ID 的 SDK Key 打包即可。
