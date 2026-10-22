# 打包与部署

- 打包、发布、部署前必读 [部署与运维](docs/deployment.md)，图片功能另读 [图片部署说明](docs/image-feature-deployment.md)。README 快速开始仅用于开发。
- 家长端正式构建使用 `scripts/build_parent.py`；学生端按部署文档选择渠道壳。不得跳过锁文件、生产 API、签名、SDK 注入与产物校验步骤。
- 工具链和命令以当前脚本、锁文件及 `.github/workflows/ci.yml` 为准；发现与文档不一致时核实后同步文档，不靠改锁文件或绕过检查完成发布。
- 实际生产环境还须读取仓库外 `../credentials/store-subscriptions.md` 和 `../credentials/production-deploy-gker.md`。缺少凭据或环境说明时，不使用占位值发布；商业 SDK、签名及凭据不得入库。
- 历史发布记录不代表当前线上状态。部署前核对实际运行版本、环境、数据库迁移和回滚方案；不能把 CI 无签名调试构建当作正式发布验收。
- 多任务并行时，仅暂存当前会话的修改，逐行核对差异。Android 设备操作统一使用 ADB，不使用 `cua_repl`。
