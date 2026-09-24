import 'package:flutter/material.dart';
import 'package:app_core/app_core.dart';
import 'screens/home_screen.dart';
import 'screens/login_screen.dart';

/// 家长端根组件：已登录进入家庭总览，否则进入三要素核验注册页。
class ParentApp extends StatelessWidget {
  const ParentApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'AI 助学 - 家长端',
      theme: appTheme(const Color(0xFF5367A8)),
      home: Api.I.hasToken ? const HomeScreen() : const LoginScreen(),
    );
  }
}
