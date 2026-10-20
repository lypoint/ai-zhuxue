import 'package:app_core/app_core.dart';
import 'package:flutter/material.dart';

class GuardianNameDialog extends StatefulWidget {
  const GuardianNameDialog({super.key, required this.initialName});

  final String initialName;

  @override
  State<GuardianNameDialog> createState() => _GuardianNameDialogState();
}

class _GuardianNameDialogState extends State<GuardianNameDialog> {
  late final _controller = TextEditingController(text: widget.initialName);
  bool _saving = false;
  String? _error;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (_saving) return;
    final name = _controller.text.trim();
    if (name.isEmpty || name.runes.length > 50) {
      setState(() => _error = tr('昵称需为 1-50 字符'));
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await Api.I.setGuardianNickname(name);
      if (mounted) Navigator.of(context).pop(name);
    } catch (e) {
      if (mounted) {
        setState(() {
          _saving = false;
          _error = e is ApiException ? e.message : tr('网络连接失败，请稍后重试');
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) => PopScope(
    canPop: !_saving,
    child: AlertDialog(
      title: Text(tr('修改名字')),
      content: TextField(
        controller: _controller,
        autofocus: true,
        enabled: !_saving,
        maxLength: 50,
        textInputAction: TextInputAction.done,
        onSubmitted: (_) => _save(),
        decoration: InputDecoration(labelText: tr('监护人名字'), errorText: _error),
      ),
      actions: [
        TextButton(
          onPressed: _saving ? null : () => Navigator.of(context).pop(),
          child: Text(tr('取消')),
        ),
        FilledButton(
          onPressed: _saving ? null : _save,
          child: Text(tr(_saving ? '保存中…' : '保存')),
        ),
      ],
    ),
  );
}
