import 'package:flutter/material.dart';
import 'package:app_core/app_core.dart';
import 'screens/bind_screen.dart';
import 'screens/chat_screen.dart';

/// 学生端：绑定（输入家长端绑定码）→ 学习聊天（围栏内）。
class StudentApp extends StatelessWidget {
  const StudentApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'AI 助学 - 学生端',
      theme: appTheme(const Color(0xFF3D8B7A)),
      home: Api.I.hasToken ? const ChatScreen() : const BindScreen(),
    );
  }
}
