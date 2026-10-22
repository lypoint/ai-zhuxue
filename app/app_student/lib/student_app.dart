import 'package:flutter/material.dart';
import 'package:app_core/app_core.dart';
import 'screens/bind_screen.dart';
import 'screens/chat_screen.dart';
import 'theme/student_theme.dart';

/// Scope for injecting channel-specific student actions (e.g. overseas GDPR privacy settings).
class StudentScope extends InheritedWidget {
  final List<Widget> Function(BuildContext context)? extraAccountActionBuilder;

  const StudentScope({
    super.key,
    required super.child,
    this.extraAccountActionBuilder,
  });

  static StudentScope? of(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<StudentScope>();

  @override
  bool updateShouldNotify(StudentScope oldWidget) =>
      extraAccountActionBuilder != oldWidget.extraAccountActionBuilder;
}

/// 学生端：绑定（输入家长端绑定码）→ 学习聊天（围栏内）。
class StudentApp extends StatelessWidget {
  final GlobalKey<NavigatorState>? navigatorKey;
  final List<Widget> Function(BuildContext context)? extraAccountActionBuilder;
  const StudentApp({super.key, this.navigatorKey, this.extraAccountActionBuilder});

  @override
  Widget build(BuildContext context) {
    return StudentScope(
      extraAccountActionBuilder: extraAccountActionBuilder,
      child: LanguageApp(
        builder: (locale) => MaterialApp(
          navigatorKey: navigatorKey,
          locale: locale,
          supportedLocales: supportedAppLocales,
          localizationsDelegates: appLocalizationDelegates,
          title: tr("AI 助学·学生版"),
          theme: studentTheme(),
          home: Api.I.hasToken ? const ChatScreen() : const BindScreen(),
        ),
      ),
    );
  }
}
