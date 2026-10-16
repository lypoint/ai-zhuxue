import 'package:app_core/app_core.dart';
import 'package:app_parent/screens/home_screen.dart';
import 'package:flutter/material.dart';
import 'package:google_sign_in/google_sign_in.dart';

const googleServerClientId = String.fromEnvironment('GOOGLE_SERVER_CLIENT_ID');

class GoogleLoginScreen extends StatefulWidget {
  const GoogleLoginScreen({super.key, this.authenticate});
  final Future<String?> Function()? authenticate;
  @override
  State<GoogleLoginScreen> createState() => _GoogleLoginScreenState();
}

class _GoogleLoginScreenState extends State<GoogleLoginScreen> {
  bool _loading = false;
  String? _error;

  Future<String?> _authenticate() async {
    final google = GoogleSignIn(
      serverClientId: googleServerClientId,
      scopes: ['email'],
    );
    // Offer account selection again after logging out of the app.
    await google.signOut();
    final account = await google.signIn();
    if (account == null) return null;
    final token = (await account.authentication).idToken;
    if (token == null || token.isEmpty) {
      throw StateError('Missing Google ID token');
    }
    return token;
  }

  Future<void> _login() async {
    if (_loading) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final token = await (widget.authenticate ?? _authenticate)();
      if (token == null) return;
      await Api.I.guardianGoogle(token);
      if (!mounted) return;
      Navigator.of(
        context,
      ).pushReplacement(MaterialPageRoute(builder: (_) => const HomeScreen()));
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } catch (_) {
      if (mounted) setState(() => _error = tr('Google 登录失败，请检查网络后重试'));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    AppLanguage.watch(context);
    final configured =
        googleServerClientId.isNotEmpty || widget.authenticate != null;
    return Scaffold(
      appBar: AppBar(title: Text(tr('家长端')), actions: const [LanguageButton()]),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 400),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  tr('建立受保护的学习空间'),
                  style: Theme.of(context).textTheme.headlineSmall,
                ),
                const SizedBox(height: 12),
                Text(tr('使用 Google 账号登录，连接孩子设备并管理家庭订阅')),
                const SizedBox(height: 24),
                OutlinedButton(
                  onPressed: _loading || !configured ? null : _login,
                  child: Text(_loading ? tr('登录中…') : tr('使用 Google 账号登录')),
                ),
                PasswordLoginButton(
                  onLoggedIn: () => Navigator.of(context).pushReplacement(
                    MaterialPageRoute(builder: (_) => const HomeScreen()),
                  ),
                ),
                if (!configured) Text(tr('Google 登录尚未配置')),
                if (_error != null)
                  Text(
                    _error!,
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.error,
                    ),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
