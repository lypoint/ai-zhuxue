# 家长端共享库

此包提供共享界面与家庭业务，不含支付 SDK，也不直接打包。

执行入口为 `../app_parent_wechat`、`../app_parent_appstore`、`../app_parent_googleplay`。
当前通用流程见 [部署与运维](../../docs/deployment.md#4-flutter-构建产物)，正式包使用 `scripts/build_parent.py`。真实商店参数及密钥加载见仓库外的 [渠道订阅接入](../../../credentials/store-subscriptions.md)。
