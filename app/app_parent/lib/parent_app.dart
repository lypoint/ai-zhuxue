import 'package:flutter/material.dart';
import 'package:app_core/app_core.dart';
import 'screens/home_screen.dart';
import 'screens/login_screen.dart';

/// 家长端根组件：已登录进入家庭总览，否则进入手机号注册或登录页。
class ParentApp extends StatefulWidget {
  const ParentApp({super.key});
  @override
  State<ParentApp> createState() => _ParentAppState();
}

class _ParentAppState extends State<ParentApp> {
  final _navigatorKey = GlobalKey<NavigatorState>();
  bool _handlingExpired = false;

  @override
  void initState() {
    super.initState();
    // 全局 401 兜底：token 失效（登出吊销/过期）时清会话回登录页，
    // 覆盖审查、成绩、通知等所有家长端请求，避免各页面各自处理遗漏。
    Api.onUnauthorized = _onSessionExpired;
  }

  Future<void> _onSessionExpired() async {
    if (_handlingExpired) return;
    _handlingExpired = true;
    await Api.I.logout();
    _handlingExpired = false;
    _navigatorKey.currentState?.pushAndRemoveUntil(
      MaterialPageRoute(builder: (_) => const LoginScreen()),
      (route) => false,
    );
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      navigatorKey: _navigatorKey,
      title: 'AI 助学·家长版',
      theme: appTheme(const Color(0xFF5367A8)),
      home: Api.I.hasToken ? const HomeScreen() : const LoginScreen(),
    );
  }
}
