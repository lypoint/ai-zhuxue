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
    testWidgets('删除学生账号确认、取消、失败重试及清除凭据 ($channel)', (tester) async {
      Api.I.channel = channel;
      addTearDown(() => Api.I.channel = '');
      final key = channel == 'googleplay' ? 'google_login_token' : 'token';
      SharedPreferences.setMockInitialValues({key: 'student-session'});
      await Api.I.loadToken();
      var attempts = 0;
      final client = MockClient((request) async {
        if (request.url.path == '/auth/student/account/delete') {
          expect(request.method, 'POST');
          expect(jsonDecode(request.body), {'confirmation': 'DELETE'});
          expect(request.headers['Authorization'], 'Bearer student-session');
          attempts++;
          return http.Response(
            attempts == 1 ? '{"detail":"Try again"}' : '{"ok":true}',
            attempts == 1 ? 503 : 200,
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
        Future<void> openDeletion() async {
          await tester.tap(find.byIcon(Icons.menu));
          await tester.pumpAndSettle();
          await tester.tap(find.text('删除账号'));
          await tester.pumpAndSettle();
        }

        await openDeletion();
        await tester.tap(find.text('取消'));
        await tester.pumpAndSettle();
        expect(attempts, 0);
        expect(Api.I.hasToken, true);
        await openDeletion();
        await tester.tap(find.widgetWithText(FilledButton, '删除账号'));
        await tester.pumpAndSettle();
        expect(attempts, 1);
        expect(Api.I.hasToken, true);
        expect(find.text('删除失败，请检查网络后重试'), findsOneWidget);
        await openDeletion();
        await tester.tap(find.widgetWithText(FilledButton, '删除账号'));
        await tester.pumpAndSettle();
        expect(attempts, 2);
        expect(Api.I.hasToken, false);
        expect((await SharedPreferences.getInstance()).getString(key), isNull);
        expect(find.byType(BindScreen), findsOneWidget);
        expect(tester.takeException(), isNull);
        await tester.pumpWidget(const SizedBox.shrink());
      }, () => client);
    });
  }
}
