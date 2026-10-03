# api.gker.net / admin.gker.net 发布记录

更新于 2026-10-03。此文件记录实际使用的 AI 助学发布方式；`gker/gker/docs/deployment.md` 中旧的 `api.gker.net → 8080` 说明不适用于当前服务。

## 当前环境

- SSH：本机先连接 ZeroTier，再用 `ssh root@192.168.195.76`。只使用密钥，不复制凭据到仓库。
- Caddy：`api.gker.net → 127.0.0.1:8100`，`admin.gker.net → 127.0.0.1:8101`。
- API：`aizhuxue-api.service`，CMS：`aizhuxue-cms.service`。两者均使用 `/srv/ai-zhuxue/venv`，从 `/srv/ai-zhuxue/releases/<git-short-sha>` 运行。
- 生效的发布路径写在 `/etc/systemd/system/aizhuxue-{api,cms}.service.d/release.conf`。API 工作目录为发布目录下的 `server`，CMS 为发布目录根目录。
- 环境变量在 `/etc/ai-zhuxue-api.env` 和 `/etc/ai-zhuxue-cms.env`；不要打印或提交其内容。数据库为本机 PostgreSQL 的 `aizhuxue`，API 启动时也会运行 Alembic 迁移。
- 学生端默认连接 `https://api.gker.net`。服务端发布不会自动更新已经安装的 App；Flutter 客户端仍须单独构建和分发。

## 下次发布

先在 `product` 仓库完成测试和提交，确认要发布的提交已推送。不要把其他会话的未提交修改打入包。下列命令在本机 `product` 目录执行，`REV` 使用目标提交的短 SHA：

```bash
REV=$(git rev-parse --short HEAD)
git archive --format=tar HEAD server cms | gzip -n > "/tmp/ai-zhuxue-$REV.tar.gz"
shasum -a 256 "/tmp/ai-zhuxue-$REV.tar.gz"
scp "/tmp/ai-zhuxue-$REV.tar.gz" root@192.168.195.76:/tmp/
```

在服务器上先核对包的 SHA-256，再备份数据库、解包和安装依赖。备份输出由 root 写入；`postgres` 用户不能穿过 `/srv/ai-zhuxue` 目录直接写文件。

```bash
REV=YOUR_SHORT_SHA  # 改成这次要发布的短 SHA
sha256sum "/tmp/ai-zhuxue-$REV.tar.gz"
install -d -m 700 -o root -g root /srv/ai-zhuxue/backups
sudo -u postgres pg_dump -Fc aizhuxue > "/srv/ai-zhuxue/backups/pre-$REV.dump"
chmod 600 "/srv/ai-zhuxue/backups/pre-$REV.dump"
pg_restore --list "/srv/ai-zhuxue/backups/pre-$REV.dump" >/dev/null
install -d -m 750 -o root -g aizhuxue "/srv/ai-zhuxue/releases/$REV"
tar -xzf "/tmp/ai-zhuxue-$REV.tar.gz" -C "/srv/ai-zhuxue/releases/$REV"
chown -R root:aizhuxue "/srv/ai-zhuxue/releases/$REV"
chmod -R g-w "/srv/ai-zhuxue/releases/$REV"
/srv/ai-zhuxue/venv/bin/pip install -r "/srv/ai-zhuxue/releases/$REV/server/requirements.txt"
```

查看本次迁移内容后，以 API 的现有环境运行迁移；不要把环境变量输出到终端或日志。下面的命令由服务器 root shell 执行：

```bash
set -a
. /etc/ai-zhuxue-api.env
set +a
cd "/srv/ai-zhuxue/releases/$REV/server"
runuser -u aizhuxue -- /srv/ai-zhuxue/venv/bin/alembic upgrade head
sudo -u postgres psql -d aizhuxue -Atc 'SELECT version_num FROM alembic_version'
```

切换前备份两个 `release.conf`，再写入新工作目录。确认备份文件存在后执行：

```bash
API_CONF=/etc/systemd/system/aizhuxue-api.service.d/release.conf
CMS_CONF=/etc/systemd/system/aizhuxue-cms.service.d/release.conf
cp -p "$API_CONF" "$API_CONF.bak.pre-$REV"
cp -p "$CMS_CONF" "$CMS_CONF.bak.pre-$REV"
printf '[Service]\nWorkingDirectory=/srv/ai-zhuxue/releases/%s/server\n' "$REV" > "$API_CONF.tmp"
printf '[Service]\nWorkingDirectory=/srv/ai-zhuxue/releases/%s\n' "$REV" > "$CMS_CONF.tmp"
chmod 644 "$API_CONF.tmp" "$CMS_CONF.tmp"
mv "$API_CONF.tmp" "$API_CONF"
mv "$CMS_CONF.tmp" "$CMS_CONF"
systemctl daemon-reload
systemctl restart aizhuxue-api aizhuxue-cms
systemctl is-active aizhuxue-api aizhuxue-cms
curl -fsS http://127.0.0.1:8100/health
curl -fsS http://127.0.0.1:8101/ -o /dev/null
```

最后从本机验收 `https://api.gker.net/health`、`https://api.gker.net/openapi.json`、`https://admin.gker.net/`，并检查 `journalctl -u aizhuxue-api -u aizhuxue-cms --since '10 minutes ago' -p err`。涉及具体功能时还需验证对应接口和客户端。发布失败时恢复 `$API_CONF.bak.pre-$REV`、`$CMS_CONF.bak.pre-$REV`，`systemctl daemon-reload` 后重启两项服务；数据库迁移能否回退须按该次迁移判断，必要时使用发布前的 `pg_dump` 备份恢复。

## 2026-10-02 发布

| 项目 | 结果 |
|---|---|
| 版本 | `4b606e2` → `30b63b0`；发布包由该 Git 提交生成，后续仅文档提交不改变线上版本 |
| 发布包 SHA-256 | `f659906fb00f3be33554d3aa1bca65372e1b54dcf8af13bbaac3587503ea82f4` |
| 数据库备份 | `/srv/ai-zhuxue/backups/pre-30b63b0-20261002.dump`，已用 `pg_restore --list` 检查 |
| 迁移 | `d4e5f6a7b8c9` → `e7f8a9b0c1d2`，为举报回复增加 `reply_text` 列 |
| 回滚配置 | 两个 `release.conf.bak.20261002-pre-30b63b0`，分别位于对应的 systemd drop-in 目录 |
| 验收 | API/CMS 服务 active；公网健康检查正常；OpenAPI 包含 `/chat/reports` 和 `ChatIn.retry_message_id`；CMS 页面包含举报功能；最近服务错误日志为空 |

本次本地后端 135 项测试和学生端测试通过，GitHub CI 全部通过。线上未发送真实学生消息来触发失败重试，避免改动用户对话和配额。

## 2026-10-02 API 热修复

`api.gker.net` 从 `30b63b0` 切到 `d3ca72f`；`admin.gker.net` 未改动，仍运行 `30b63b0`。这次将 DeepSeek 系列聊天模型的默认输出上限从 1024 提高到 8192 tokens，避免推理内容占满额度后没有正文；其他模型与围栏分类的额度未变。发布包 SHA-256 为 `5150a0301645d8980f9f2bd8db93d7c453cbce82a8c8efa8c4aaabdf18a125a4`。

数据库备份为 `/srv/ai-zhuxue/backups/pre-d3ca72f-20261002.dump`；本次没有新迁移，版本仍是 `e7f8a9b0c1d2`。API 回滚配置为 `/etc/systemd/system/aizhuxue-api.service.d/release.conf.bak.20261002-pre-d3ca72f`。服务健康检查与 CI 通过；在 iPhone 16e 模拟器点击原失败消息的“重试回复”后，老师回复正常显示，服务端复用原学生消息且仅新增一条老师回复。

## 2026-10-02 输出额度调整

`api.gker.net` 从 `d3ca72f` 切到 `b890cf9`；CMS 仍运行 `30b63b0`。流式和非流式聊天补全请求、聊天补全式围栏分类请求的 `max_tokens` 均为 40960。线上老师实际使用的阿里云 System One 结构化围栏接口使用 `state/questions` 请求格式，没有 `max_tokens` 字段，此次未更换分类接口，也没有给它添加未经确认支持的字段。第三个老师分组的 `gpt-6-luna` 在原额度和 40960 下均被上游报告为已下架，与本次额度调整无关。

发布包 SHA-256 为 `f7529960acef34a85a36ff73ad37c5d531171437ff586b6284b54116d49e78a9`。数据库备份为 `/srv/ai-zhuxue/backups/pre-b890cf9-20261002.dump`；没有新迁移。API 回滚配置为 `/etc/systemd/system/aizhuxue-api.service.d/release.conf.bak.20261002-pre-b890cf9`。本地后端 136 项测试与 GitHub CI 通过，公网健康检查正常，服务错误日志为空。

## 2026-10-03 准确性与生产支付保护

API 从 `b890cf9`、CMS 从 `30b63b0` 统一切到 `7ffc592`。本次统一评估、摘要、心跳和用量的本地日期口径，修复跨周统计；身心提示区分常见教育讨论、否定表达和个人求助，评估缓存区分规则版本与时区。生产续费和购买孩子名额接口在真实支付接入前返回 503，不生成模拟已支付订单或发放权益。没有客户端代码变更，无需更新 App。

| 项目 | 结果 |
|---|---|
| 发布包 SHA-256 | `68ad3a127e23e0d86c0588d8db08425bd1813d86b28e2b8e5d13d9af1f587b38`，服务器核对通过 |
| 数据库备份 | `/srv/ai-zhuxue/backups/pre-7ffc592-20261003.dump`，`pg_restore --list` 检查通过 |
| 迁移与依赖 | 均无变更；执行 `alembic upgrade head` 后仍为 `e7f8a9b0c1d2`，复用现有 venv |
| 回滚配置 | API/CMS 各自 drop-in 目录中的 `release.conf.bak.20261003-pre-7ffc592` |
| 本地与 CI | 后端 162 项测试通过；目标提交 GitHub CI 全部通过 |
| 服务器验证 | 日期边界与教育/个人求助规则检查通过；两项服务 active/running，自动重启次数为 0 |
| 公网验收 | `/health`、`/openapi.json` 和 CMS 首页均返回 200；最近 5 分钟服务错误日志为空 |

未使用真实家庭令牌执行评估或支付请求，避免写入用户评估、告警、订单和配额。支付保护由回归测试验证，线上验证发布目录及已加载版本。后续发布记录提交仅更新文档，不改变线上运行版本。

## 2026-10-03 家长自定义违禁词

API 从 `7ffc592` 切到 `54b9c71`，CMS 继续运行 `7ffc592`。家长端可设置按家庭生效的违禁词列表；学生输入包含任一指定词时，普通与流式聊天均直接拒答并提示重新输入学习方面的问题，不调用模型。匹配忽略英文大小写，清空列表可取消自定义限制。

| 项目 | 结果 |
|---|---|
| 发布包 SHA-256 | `cab5ecac2cc4533485a1b2352fb22dd2d672378f8c38a712d39a2c93dda20005`，服务器核对通过 |
| 数据库备份 | `/srv/ai-zhuxue/backups/pre-54b9c71-20261003.dump`，已用 `pg_restore --list` 检查 |
| 迁移 | `e7f8a9b0c1d2` → `a8b9c0d1e2f3`，增加 `family_settings.forbidden_words_json`，已有家庭默认空列表 |
| 回滚配置 | `/etc/systemd/system/aizhuxue-api.service.d/release.conf.bak.20261003-pre-54b9c71` |
| 本地与 CI | 从暂存内容导出的干净副本通过 165 项后端测试；目标提交 GitHub CI 全部通过 |
| iPhone 验收 | iPhone 16e / iOS 18.4，独立本地测试家庭保存 `Game` 后，学生发送 `game` 显示拒答提示；两条消息记录为 reject，模型调用记录为 0 |
| 生产验收 | 迁移及指定词规则断言通过；API/CMS active/running；公网健康检查、OpenAPI 和 CMS 首页均返回 200；OpenAPI 包含 `FamilySettingsIn.forbidden_words`；API 自动重启次数为 0，最近 5 分钟服务错误日志为空 |

生产验证未写入真实家庭的设置或对话。家长端界面修改已随功能提交，已安装 App 仍需单独更新客户端才能使用列表编辑入口；本次发布未上传 App Store/TestFlight 或分发签名安装包。发布包仅包含已提交代码，其他会话的学习奖励改动未打包。
