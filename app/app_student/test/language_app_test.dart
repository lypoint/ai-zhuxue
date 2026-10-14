import 'package:app_core/app_core.dart';
import 'package:app_student/student_app.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUpAll(() async {
    SharedPreferences.setMockInitialValues({'app_language': 'zh-Hans'});
    await AppLanguage.I.load();
    Api.I.clearToken();
  });
  testWidgets(
    'student root uses every supported language and retains bind code',
    (tester) async {
      await tester.pumpWidget(const StudentApp());
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField), 'A3F9C2B1');
      for (final locale in supportedAppLocales) {
        await tester.runAsync(
          () => AppLanguage.I.select(locale.toLanguageTag()),
        );
        await tester.pumpAndSettle();
        expect(find.text(tr('开始学习')), findsOneWidget);
        expect(find.text(tr('绑定并开始学习')), findsOneWidget);
        expect(find.text('A3F9C2B1'), findsOneWidget);
        expect(tester.takeException(), isNull);
      }
    },
  );
}
