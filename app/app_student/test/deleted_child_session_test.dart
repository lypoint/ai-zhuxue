import 'dart:convert';

import 'package:app_core/app_core.dart';
import 'package:app_student/screens/bind_screen.dart';
import 'package:app_student/student_app.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  setUpAll(() async {
    SharedPreferences.setMockInitialValues({'app_language': 'zh-Hans'});
    await AppLanguage.I.load();
  });
  for (final channel in ['wechat', 'googleplay']) {
    testWidgets('心跳发现孩子已删除后清除登录并回绑定页 ($channel)', (tester) async {
      Api.I.channel = channel;
      addTearDown(() => Api.I.channel = '');
      final key = channel == 'googleplay' ? 'google_login_token' : 'token';
      SharedPreferences.setMockInitialValues({key: 'student-session'});
      await Api.I.loadToken();
      var heartbeats = 0;
      final client = MockClient((request) async {
        if (request.url.path == '/chat/heartbeat') {
          heartbeats++;
          return http.Response(
            '{"detail":"student not found or inactive"}',
            401,
          );
        }
        final data = switch (request.url.path) {
          '/chat/teachers' || '/chat/sessions' => [],
          '/chat/learning' => {
            'today': {'refresh_after_seconds': 86400},
          },
          _ => <String, dynamic>{},
        };
        return http.Response(jsonEncode(data), 200);
      });
      addTearDown(client.close);
      await http.runWithClient(() async {
        await tester.pumpWidget(const StudentApp());
        await tester.pumpAndSettle();
        expect(Api.I.hasToken, true);
        await tester.pump(const Duration(seconds: 60));
        await tester.pumpAndSettle();
        expect(heartbeats, 1);
        expect(Api.I.hasToken, false);
        expect((await SharedPreferences.getInstance()).getString(key), isNull);
        expect(find.text('登录已失效'), findsOneWidget);
        await tester.tap(find.widgetWithText(FilledButton, '重新绑定'));
        await tester.pumpAndSettle();
        expect(find.byType(BindScreen), findsOneWidget);
        expect(tester.takeException(), isNull);
        await tester.pumpWidget(const SizedBox.shrink());
      }, () => client);
    });
  }
}
