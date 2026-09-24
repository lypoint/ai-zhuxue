import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:app_core/app_core.dart';
import 'package:app_parent/screens/login_screen.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('家长端登录页展示三要素核验表单', (tester) async {
    SharedPreferences.setMockInitialValues({});
    Api.I.clearToken();
    await tester.pumpWidget(const MaterialApp(home: LoginScreen()));
    expect(find.text('监护人姓名'), findsOneWidget);
    expect(find.text('身份证号'), findsOneWidget);
    expect(find.text('核验并注册'), findsOneWidget);
  });
}
