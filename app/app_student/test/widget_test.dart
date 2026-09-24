import 'package:app_student/student_app.dart';
import 'package:app_student/screens/chat_screen.dart';
import 'package:app_core/app_core.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('学生端无 token 时显示绑定页', (tester) async {
    SharedPreferences.setMockInitialValues({});
    Api.I.clearToken();
    await tester.pumpWidget(const StudentApp());
    expect(find.text('输入家长端绑定码'), findsOneWidget);
    expect(find.text('绑定并开始学习'), findsOneWidget);
  });

  testWidgets('聊天页空态展示欢迎语与输入框', (tester) async {
    SharedPreferences.setMockInitialValues({'token': 'fake'});
    await Api.I.loadToken();
    await tester.pumpWidget(const MaterialApp(home: ChatScreen()));
    expect(find.text('你好！今天想学什么？'), findsOneWidget);
    expect(find.byIcon(Icons.arrow_upward), findsOneWidget);
  });
}
