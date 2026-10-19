import 'package:flutter/material.dart';
import 'api.dart';
import 'language.dart';

/// Shared by every parent and student channel; credentials are never bundled.
class PasswordLoginButton extends StatelessWidget {
  const PasswordLoginButton({
    super.key,
    required this.onLoggedIn,
    this.student = false,
  });
  final VoidCallback onLoggedIn;
  final bool student;

  @override
  Widget build(BuildContext context) => TextButton(
    onPressed: () async {
      final success = await Navigator.of(context).push<bool>(
        MaterialPageRoute(
          builder: (_) => _PasswordLoginScreen(student: student),
        ),
      );
      if (context.mounted && success == true) onLoggedIn();
    },
    child: Text(tr('账号密码登录')),
  );
}

class _PasswordLoginScreen extends StatefulWidget {
  const _PasswordLoginScreen({required this.student});
  final bool student;
  @override
  State<_PasswordLoginScreen> createState() => _PasswordLoginScreenState();
}

class _PasswordLoginScreenState extends State<_PasswordLoginScreen> {
  final _username = TextEditingController();
  final _password = TextEditingController();
  bool _loading = false;
  String? _error;

  @override
  void dispose() {
    _username.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _login() async {
    if (_loading) return;
    final username = _username.text.trim();
    if (username.isEmpty || _password.text.isEmpty) {
      setState(() => _error = tr('请输入账号和密码'));
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      await Api.I.passwordLogin(
        username,
        _password.text,
        student: widget.student,
      );
      if (mounted) Navigator.of(context).pop(true);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } catch (_) {
      if (mounted) setState(() => _error = tr('连接失败，请检查网络或稍后重试'));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    AppLanguage.watch(context);
    return Scaffold(
      appBar: AppBar(
        title: Text(tr('账号密码登录')),
        actions: const [LanguageButton()],
      ),
      body: SafeArea(
        child: Align(
          alignment: Alignment.topCenter,
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 420),
            child: ListView(
              shrinkWrap: true,
              padding: const EdgeInsets.all(24),
              children: [
                Center(
                  child: Container(
                    width: 68,
                    height: 68,
                    decoration: BoxDecoration(
                      color: Theme.of(context).colorScheme.primary,
                      borderRadius: BorderRadius.circular(18),
                    ),
                    child: Image.asset(
                      'assets/logo-mark.png',
                      package: 'app_core',
                      color: Colors.white,
                      semanticLabel: tr('AI 助学'),
                    ),
                  ),
                ),
                const SizedBox(height: 18),
                Text(
                  widget.student ? tr('AI 助学·学生版') : tr('AI 助学·家长版'),
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                    fontWeight: FontWeight.w800,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  widget.student ? tr('和 AI 一起，把问题学会') : tr('登录后即可生成绑定码连接孩子设备'),
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: Theme.of(context).colorScheme.onSurfaceVariant,
                    height: 1.5,
                  ),
                ),
                const SizedBox(height: 28),
                TextField(
                  controller: _username,
                  autocorrect: false,
                  enableSuggestions: false,
                  keyboardType: TextInputType.visiblePassword,
                  autofillHints: const [AutofillHints.username],
                  textInputAction: TextInputAction.next,
                  decoration: InputDecoration(labelText: tr('账号')),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _password,
                  obscureText: true,
                  autocorrect: false,
                  enableSuggestions: false,
                  autofillHints: const [AutofillHints.password],
                  onSubmitted: (_) => _login(),
                  decoration: InputDecoration(labelText: tr('密码')),
                ),
                const SizedBox(height: 20),
                if (_error != null)
                  Text(
                    _error!,
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.error,
                    ),
                  ),
                FilledButton(
                  onPressed: _loading ? null : _login,
                  child: Text(_loading ? tr('登录中…') : tr('登录')),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
