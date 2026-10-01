import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:app_core/app_core.dart';
import 'package:app_parent/screens/login_screen.dart';
import 'package:app_parent/screens/identity_verification_screen.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('家长端登录页无需身份证号', (tester) async {
    SharedPreferences.setMockInitialValues({});
    Api.I.clearToken();
    await tester.pumpWidget(const MaterialApp(home: LoginScreen()));
    expect(find.text('家长称呼'), findsOneWidget);
    expect(find.text('身份证号'), findsNothing);
    expect(find.text('登录或注册'), findsOneWidget);
  });

  testWidgets('家长称呼为空时给出注册错误提示', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: LoginScreen()));
    await tester.ensureVisible(find.text('登录或注册'));
    await tester.tap(find.text('登录或注册'));
    await tester.pump();
    expect(find.textContaining('请填写家长称呼'), findsWidgets);
  });

  testWidgets('实名认证是登录后的可选流程', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(home: IdentityVerificationScreen(verified: false)),
    );
    expect(find.textContaining('不影响功能使用'), findsOneWidget);
    expect(find.text('真实姓名'), findsOneWidget);
    expect(find.text('身份证号'), findsOneWidget);
    await tester.tap(find.text('提交认证'));
    await tester.pump();
    expect(find.text('请填写真实姓名和有效身份证号'), findsOneWidget);
  });
}
