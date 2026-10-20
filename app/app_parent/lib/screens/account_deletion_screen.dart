import 'package:app_core/app_core.dart';
import 'package:flutter/material.dart';
import 'login_screen.dart';

class AccountDeletionScreen extends StatefulWidget {
  const AccountDeletionScreen({super.key, this.onManageSubscription});
  final VoidCallback? onManageSubscription;

  @override
  State<AccountDeletionScreen> createState() => _AccountDeletionScreenState();
}

class _AccountDeletionScreenState extends State<AccountDeletionScreen> {
  final _confirmation = TextEditingController();
  bool _sending = false;
  bool _submitted = false;
  String? _requestId;
  String? _error;

  @override
  void dispose() {
    _confirmation.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_sending || _confirmation.text.trim() != 'DELETE') return;
    setState(() {
      _sending = true;
      _error = null;
    });
    try {
      final requestId = await Api.I.requestAccountDeletion();
      if (mounted) {
        setState(() {
          _requestId = requestId;
          _submitted = true;
        });
      }
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } catch (_) {
      if (mounted) setState(() => _error = tr("提交失败，请检查网络后重试"));
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    AppLanguage.watch(context);
    return PopScope(
      canPop: !_sending && !_submitted,
      child: Scaffold(
        appBar: AppBar(
          title: Text(tr("删除账号")),
          automaticallyImplyLeading: !_sending && !_submitted,
        ),
        body: ListView(
          padding: const EdgeInsets.all(24),
          children: [
            if (_submitted) ...[
              const Icon(Icons.check_circle_outline, size: 48),
              const SizedBox(height: 16),
              Text(
                tr("删除申请已提交"),
                style: Theme.of(context).textTheme.titleLarge,
              ),
              const SizedBox(height: 12),
              SelectableText(tr("申请编号：{0}", [_requestId!])),
              const SizedBox(height: 12),
              Text(
                tr(
                  "账号及关联学生端已停用，可使用原登录方式重新注册。新账号不会恢复原家庭数据。我们将在 30 天内处理原账号的删除申请。",
                ),
              ),
              const SizedBox(height: 24),
              FilledButton(
                onPressed: () => Navigator.of(context).pushAndRemoveUntil(
                  MaterialPageRoute(builder: (_) => const LoginScreen()),
                  (_) => false,
                ),
                child: Text(tr("完成")),
              ),
            ] else ...[
              Icon(
                Icons.warning_amber_rounded,
                size: 48,
                color: Theme.of(context).colorScheme.error,
              ),
              const SizedBox(height: 16),
              Text(
                tr("删除账号及关联数据"),
                style: Theme.of(context).textTheme.titleLarge,
              ),
              const SizedBox(height: 12),
              Text(
                tr(
                  "提交后，当前家长账号和所有关联学生端将立即停用，可重新注册新账号。新账号不会恢复原家庭数据或继承原家庭权益。原账号资料和关联学习数据将进入删除流程，完成后无法恢复。",
                ),
              ),
              const SizedBox(height: 20),
              ExpansionTile(
                tilePadding: EdgeInsets.zero,
                title: Text(tr("数据处理说明")),
                children: [
                  Text(
                    tr(
                      "我们将在 30 天内处理。必要的支付、退款和安全记录依法保留；备份按轮换周期清除。Firebase 安装数据无法按家庭账号定位，相关请求请联系 support@gker.net。",
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              Text(
                tr(
                  widget.onManageSubscription == null
                      ? "微信支付为单次购买，无需取消自动续订；删除账号不产生自动退款。"
                      : "删除账号不会自动取消 Apple 或 Google Play 订阅。请先在商店取消自动续订，避免继续扣费；本操作不产生自动退款。",
                ),
              ),
              if (widget.onManageSubscription != null)
                TextButton(
                  onPressed: _sending ? null : widget.onManageSubscription,
                  child: Text(tr("管理订阅")),
                ),
              const SizedBox(height: 12),
              Text(tr("只删除部分数据或共同家庭账号，请联系 support@gker.net。不要提供密码或验证码。")),
              const SizedBox(height: 24),
              TextField(
                controller: _confirmation,
                enabled: !_sending,
                autocorrect: false,
                enableSuggestions: false,
                onChanged: (_) => setState(() {}),
                decoration: InputDecoration(labelText: tr("输入 DELETE 确认")),
              ),
              if (_error != null) ...[
                const SizedBox(height: 12),
                Text(
                  _error!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ],
              const SizedBox(height: 24),
              FilledButton(
                style: FilledButton.styleFrom(
                  backgroundColor: Theme.of(context).colorScheme.error,
                ),
                onPressed: !_sending && _confirmation.text.trim() == 'DELETE'
                    ? _submit
                    : null,
                child: Text(_sending ? tr("正在提交…") : tr("申请删除账号")),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
