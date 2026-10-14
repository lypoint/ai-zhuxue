import 'package:app_core/app_core.dart';
import 'package:flutter/material.dart';

class IdentityVerificationScreen extends StatefulWidget {
  const IdentityVerificationScreen({super.key, required this.verified});

  final bool verified;

  @override
  State<IdentityVerificationScreen> createState() =>
      _IdentityVerificationScreenState();
}

class _IdentityVerificationScreenState
    extends State<IdentityVerificationScreen> {
  final _name = TextEditingController();
  final _idNumber = TextEditingController();
  String? _error;
  bool _loading = false;

  @override
  void dispose() {
    _name.dispose();
    _idNumber.dispose();
    super.dispose();
  }

  Future<void> _verify() async {
    final name = _name.text.trim();
    final idNumber = _idNumber.text.trim();
    if (name.length < 2 ||
        !RegExp(r'^\d{15}$|^\d{17}[\dXx]$').hasMatch(idNumber)) {
      setState(() => _error = tr("请填写真实姓名和有效身份证号"));
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      await Api.I.verifyGuardianIdentity(name, idNumber);
      if (mounted) Navigator.of(context).pop(true);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } catch (_) {
      if (mounted) setState(() => _error = tr("连接失败，请稍后重试"));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    AppLanguage.watch(context);
    return Scaffold(
      appBar: AppBar(title: Text(tr("实名认证"))),
      body: ListView(
        padding: const EdgeInsets.all(24),
        children: [
          Text(
            widget.verified ? tr("已完成实名认证") : tr("实名认证不影响功能使用，可稍后完成。"),
            style: Theme.of(context).textTheme.titleMedium,
          ),
          if (!widget.verified) ...[
            const SizedBox(height: 8),
            Text(tr("使用当前登录手机号核验；系统只保存认证状态。")),
            const SizedBox(height: 24),
            TextField(
              controller: _name,
              maxLength: 30,
              decoration: InputDecoration(labelText: tr("真实姓名")),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _idNumber,
              maxLength: 18,
              autocorrect: false,
              enableSuggestions: false,
              decoration: InputDecoration(labelText: tr("身份证号")),
            ),
            if (_error != null)
              Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: Text(
                  _error!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ),
            FilledButton(
              onPressed: _loading ? null : _verify,
              child: Text(_loading ? tr("认证中…") : tr("提交认证")),
            ),
          ],
        ],
      ),
    );
  }
}
