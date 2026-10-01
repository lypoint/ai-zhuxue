import 'dart:async';
import 'dart:io' show Platform;
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:app_core/app_core.dart';
import 'home_screen.dart';

/// 家长优先使用本机号码登录，短信验证码作为回退；实名认证可在登录后完成。
class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});
  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  static const _oneTap = MethodChannel('ai.zhuxue/one_tap');
  static const _sdkKey = String.fromEnvironment('ALIYUN_AUTH_SDK_KEY');
  final _phone = TextEditingController();
  final _sms = TextEditingController();
  final _name = TextEditingController();
  String? _error;
  bool _loading = false;
  bool _sendingSms = false;
  bool _smsMode = _sdkKey.isEmpty;
  bool _oneTapAvailable = false;
  int _countdown = 0;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _checkOneTap());
  }

  @override
  void dispose() {
    _timer?.cancel();
    _phone.dispose();
    _sms.dispose();
    _name.dispose();
    super.dispose();
  }

  Future<void> _checkOneTap() async {
    if (!mounted) return;
    if (kIsWeb ||
        !(defaultTargetPlatform == TargetPlatform.iOS ||
          defaultTargetPlatform == TargetPlatform.android ||
          Platform.operatingSystem == 'ohos') ||
        _sdkKey.isEmpty) {
      setState(() => _smsMode = true);
      return;
    }
    try {
      final available = await _oneTap
          .invokeMethod<bool>('isAvailable', {'sdkKey': _sdkKey})
          .timeout(const Duration(seconds: 10), onTimeout: () => false);
      if (!mounted) return;
      setState(() {
        _oneTapAvailable = available == true;
        _smsMode = available != true;
      });
      if (available == true) await _loginOneTap();
    } catch (_) {
      if (mounted) setState(() => _smsMode = true);
    }
  }

  Future<void> _loginOneTap() async {
    if (_loading) return;
    setState(() { _loading = true; _error = null; });
    try {
      final token = await _oneTap
          .invokeMethod<String>('getLoginToken')
          .timeout(const Duration(seconds: 15));
      if (token == null || token.isEmpty) throw PlatformException(code: 'NO_TOKEN');
      await Api.I.guardianOneTap(token, nickname: _name.text.trim().isEmpty ? '家长' : _name.text.trim());
      if (!mounted) return;
      Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (_) => const HomeScreen()));
    } on ApiException catch (e) {
      if (mounted) setState(() => _smsMode = true);
      _showError(e.message);
    } catch (_) {
      if (mounted) setState(() => _smsMode = true);
      _showError('本机号码验证未完成，已切换短信验证码登录');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _sendSms() async {
    final phone = _phone.text.trim();
    if (!RegExp(r'^1\d{10}$').hasMatch(phone)) {
      _showError('手机号格式不正确');
      return;
    }
    setState(() { _sendingSms = true; _error = null; });
    try {
      await Api.I.sendGuardianSms(phone);
      if (!mounted) return;
      setState(() => _countdown = 60);
      _timer?.cancel();
      _timer = Timer.periodic(const Duration(seconds: 1), (timer) {
        if (!mounted || _countdown <= 1) {
          timer.cancel();
          if (mounted) setState(() => _countdown = 0);
        } else {
          setState(() => _countdown--);
        }
      });
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('验证码已发送，5 分钟内有效')));
    } on ApiException catch (e) {
      _showError(e.message);
    } catch (_) {
      _showError('连接失败，请检查网络或稍后重试');
    } finally {
      if (mounted) setState(() => _sendingSms = false);
    }
  }

  String? _validate() {
    if (_name.text.trim().isEmpty) return '请填写家长称呼';
    if (!RegExp(r'^1\d{10}$').hasMatch(_phone.text.trim())) {
      return '手机号格式不正确';
    }
    if (!RegExp(r'^\d{4,6}$').hasMatch(_sms.text.trim())) {
      return '请输入 4 至 6 位短信验证码';
    }
    return null;
  }

  void _showError(String message) {
    if (!mounted) return;
    setState(() => _error = message);
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(message)));
  }

  Future<void> _register() async {
    final validationError = _validate();
    if (validationError != null) {
      _showError(validationError);
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      await Api.I.registerGuardian(
        _phone.text.trim(),
        _sms.text.trim(),
        _name.text.trim(),
      );
      if (!mounted) return;
      Navigator.of(
        context,
      ).pushReplacement(MaterialPageRoute(builder: (_) => const HomeScreen()));
    } on ApiException catch (e) {
      final message = switch (e.message) {
        'invalid sms code' => '短信验证码错误，请检查后重试',
        _ when e.status == 422 => '提交的信息格式不正确，请检查后重试',
        _ => e.message,
      };
      _showError(message);
    } catch (_) {
      _showError('连接失败，请检查网络或稍后重试');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('家长端')),
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            colors: [Color(0xFFEFF2FF), Color(0xFFF6F8FB)],
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
          ),
        ),
        child: ListView(
          padding: const EdgeInsets.fromLTRB(24, 24, 24, 32),
          children: [
            _header(context),
            const SizedBox(height: 24),
            _formCard(context),
          ],
        ),
      ),
    );
  }

  Widget _header(BuildContext context) {
    return Row(
      children: [
        Container(
          width: 56,
          height: 56,
          decoration: BoxDecoration(
            color: const Color(0xFF253A68),
            borderRadius: BorderRadius.circular(15),
          ),
          child: Image.asset(
            'assets/logo-mark.png',
            package: 'app_core',
            color: Colors.white,
            semanticLabel: 'AI 助学',
          ),
        ),
        const SizedBox(width: 14),
        const Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                '建立受保护的学习空间',
                style: TextStyle(fontSize: 21, fontWeight: FontWeight.w800),
              ),
              SizedBox(height: 4),
              Text('登录后即可生成绑定码连接孩子设备', style: TextStyle(color: Colors.black54)),
            ],
          ),
        ),
      ],
    );
  }

  Widget _formCard(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              _smsMode ? '短信验证码登录' : '本机号码一键登录',
              style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 14),
            if (_smsMode) ...[
              TextField(
                controller: _name,
                decoration: const InputDecoration(
                  labelText: '家长称呼',
                  prefixIcon: Icon(Icons.person_outline),
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _phone,
                keyboardType: TextInputType.phone,
                maxLength: 11,
                decoration: InputDecoration(
                  labelText: '手机号',
                  counterText: '',
                  prefixIcon: const Icon(Icons.phone_outlined),
                  suffixIcon: TextButton(
                    onPressed: _sendingSms || _countdown > 0 ? null : _sendSms,
                    child: Text(_sendingSms ? '发送中…' : _countdown > 0 ? '${_countdown}s' : '发送验证码'),
                  ),
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _sms,
                keyboardType: TextInputType.number,
                autofillHints: const [AutofillHints.oneTimeCode],
                maxLength: 6,
                decoration: const InputDecoration(
                  labelText: '短信验证码',
                  counterText: '',
                  prefixIcon: Icon(Icons.verified_user_outlined),
                ),
              ),
              const SizedBox(height: 18),
              FilledButton.icon(
                onPressed: _loading ? null : _register,
                icon: const Icon(Icons.arrow_forward),
                label: Text(_loading ? '登录中…' : '登录或注册'),
              ),
              if (_oneTapAvailable)
                TextButton(onPressed: _loading ? null : _loginOneTap, child: const Text('本机号码一键登录')),
            ] else ...[
              const Text('即将使用当前设备的手机号完成验证。请在运营商授权页确认。'),
              const SizedBox(height: 18),
              FilledButton.icon(
                onPressed: _loading || !_oneTapAvailable ? null : _loginOneTap,
                icon: const Icon(Icons.phone_iphone),
                label: Text(_loading ? '正在验证…' : '本机号码一键登录'),
              ),
              TextButton(
                onPressed: () => setState(() => _smsMode = true),
                child: const Text('使用短信验证码'),
              ),
            ],
            if (_error != null)
              Padding(
                padding: const EdgeInsets.only(top: 12),
                child: Text(
                  _error!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
