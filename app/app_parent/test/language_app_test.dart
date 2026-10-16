import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:app_core/app_core.dart';
import 'package:app_parent/parent_app.dart';
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
    'parent root uses every supported language and retains registration input',
    (tester) async {
      await tester.pumpWidget(const ParentApp());
      await tester.pumpAndSettle();
      final nickname = find.widgetWithText(TextField, tr('家长称呼'));
      await tester.enterText(nickname, '家长自己的称呼');
      for (final locale in supportedAppLocales) {
        await tester.runAsync(
          () => AppLanguage.I.select(locale.toLanguageTag()),
        );
        await tester.pumpAndSettle();
        expect(find.text(tr('家长端')), findsOneWidget);
        expect(find.text(tr('登录或注册')), findsOneWidget);
        expect(find.text('家长自己的称呼'), findsOneWidget);
        expect(tester.takeException(), isNull);
      }
    },
  );
  testWidgets('all parent tabs support seven languages on a narrow screen', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(320, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    SharedPreferences.setMockInitialValues({'token': 'test-token'});
    await Api.I.loadToken();
    final client = MockClient((request) async {
      final data = switch (request.url.path) {
        '/parent/family' => {
          'guardian': {'nickname': '原始昵称'},
          'students': [
            {'id': 1, 'nickname': '孩子原名', 'grade_band': '8-12'},
          ],
          'settings': {'daily_message_cap': 200, 'daily_minutes_cap': 60},
        },
        '/parent/subscription' => {
          'active': true,
          'plan': 'monthly',
          'seat_count': 1,
        },
        '/parent/notifications' => {'unread': 0},
        _ => throw StateError('Unexpected request: ${request.url}'),
      };
      return http.Response(
        jsonEncode(data),
        200,
        headers: {'content-type': 'application/json; charset=utf-8'},
      );
    });
    await http.runWithClient(() async {
      await tester.pumpWidget(const ParentApp());
      await tester.pumpAndSettle();
      for (final locale in supportedAppLocales) {
        await tester.runAsync(
          () => AppLanguage.I.select(locale.toLanguageTag()),
        );
        await tester.pumpAndSettle();
        for (final title in ['家庭', '守护', '我的']) {
          await tester.tap(
            find.descendant(
              of: find.byType(NavigationBar),
              matching: find.text(tr(title)),
            ),
          );
          await tester.pumpAndSettle();
          expect(tester.takeException(), isNull, reason: '$locale $title');
        }
      }
    }, () => client);
    client.close();
  });
}
