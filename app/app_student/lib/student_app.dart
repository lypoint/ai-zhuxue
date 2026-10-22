import 'package:flutter/material.dart';
import 'package:app_core/app_core.dart';
import 'screens/bind_screen.dart';
import 'screens/chat_screen.dart';
import 'theme/student_theme.dart';

/// 学生端：绑定（输入家长端绑定码）→ 学习聊天（围栏内）。
class StudentApp extends StatelessWidget {
  final GlobalKey<NavigatorState>? navigatorKey;
  const StudentApp({super.key, this.navigatorKey});

  @override
  Widget build(BuildContext context) {
    return LanguageApp(
      builder: (locale) => MaterialApp(
        navigatorKey: navigatorKey,
        locale: locale,
        supportedLocales: supportedAppLocales,
        localizationsDelegates: appLocalizationDelegates,
        title: tr("AI 助学·学生版"),
        theme: studentTheme(),
        home: Api.I.hasToken ? const ChatScreen() : const BindScreen(),
      ),
    );
  }
}
