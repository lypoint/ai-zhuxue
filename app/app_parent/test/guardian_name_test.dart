import 'dart:convert';

import 'package:app_core/app_core.dart';
import 'package:app_parent/screens/home_screen.dart';
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
  for (final channel in ['wechat', 'appstore', 'googleplay']) {
    testWidgets('监护人改名校验、取消、失败重试和刷新 ($channel)', (tester) async {
      Api.I.channel = channel;
      addTearDown(() => Api.I.channel = '');
      var name = '原名字';
      var attempts = 0;
      final client = MockClient((request) async {
        expect(request.headers['X-App-Channel'], channel);
        if (request.method == 'PUT') {
          expect(request.url.path, '/parent/guardian/nickname');
          expect(jsonDecode(request.body), {'nickname': '小明妈妈'});
          attempts++;
          if (attempts == 1) {
            return http.Response('{"detail":"Try again"}', 503);
          }
          name = '小明妈妈';
          return http.Response('{"ok":true}', 200);
        }
        final data = switch (request.url.path) {
          '/parent/family' => {
            'guardian': {'nickname': name},
            'students': [],
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
      addTearDown(client.close);
      await http.runWithClient(() async {
        await tester.pumpWidget(const MaterialApp(home: HomeScreen()));
        await tester.pumpAndSettle();
        await tester.tap(find.text('我的'));
        await tester.pumpAndSettle();
        await tester.tap(find.text('监护人名字'));
        await tester.pumpAndSettle();
        expect(find.widgetWithText(TextField, '原名字'), findsOneWidget);
        await tester.tap(find.text('取消'));
        await tester.pumpAndSettle();
        expect(attempts, 0);
        await tester.tap(find.text('监护人名字'));
        await tester.pumpAndSettle();
        await tester.enterText(find.byType(TextField), '   ');
        await tester.tap(find.text('保存'));
        await tester.pumpAndSettle();
        expect(find.text('昵称需为 1-50 字符'), findsOneWidget);
        expect(attempts, 0);
        await tester.enterText(find.byType(TextField), '  小明妈妈  ');
        await tester.tap(find.text('保存'));
        await tester.pumpAndSettle();
        expect(find.text('Try again'), findsOneWidget);
        expect(find.widgetWithText(TextField, '  小明妈妈  '), findsOneWidget);
        await tester.tap(find.text('保存'));
        await tester.pumpAndSettle();
        expect(attempts, 2);
        expect(find.byType(AlertDialog), findsNothing);
        expect(find.text('小明妈妈'), findsWidgets);
        await tester.pumpWidget(const SizedBox());
        await tester.pumpAndSettle();
        await tester.pumpWidget(const MaterialApp(home: HomeScreen()));
        await tester.pumpAndSettle();
        await tester.tap(find.text('我的'));
        await tester.pumpAndSettle();
        expect(find.text('小明妈妈'), findsWidgets);
        expect(tester.takeException(), isNull);
      }, () => client);
    });
  }
}
