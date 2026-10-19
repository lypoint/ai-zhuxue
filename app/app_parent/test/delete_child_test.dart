import 'dart:convert';

import 'package:app_core/app_core.dart';
import 'package:app_parent/screens/home_screen.dart';
import 'package:app_parent/widgets/student_review_card.dart';
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
  for (final channel in ['wechat', 'googleplay', 'appstore']) {
    testWidgets('删除孩子须确认，失败可重试，成功隐藏卡片 ($channel)', (tester) async {
      tester.view.physicalSize = const Size(390, 1000);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      SharedPreferences.setMockInitialValues({'app_language': 'zh-Hans'});
      Api.I.channel = channel;
      addTearDown(() => Api.I.channel = '');
      var deleted = false;
      var attempts = 0;
      final client = MockClient((request) async {
        expect(request.headers['X-App-Channel'], channel);
        if (request.method == 'DELETE') {
          expect(request.url.path, '/parent/students/7');
          attempts++;
          if (attempts == 1) {
            return http.Response('{"detail":"Try again"}', 503);
          }
          deleted = true;
          return http.Response('{"ok":true,"mode":"anonymized"}', 200);
        }
        final data = switch (request.url.path) {
          '/parent/family' => {
            'guardian': {'nickname': '家长'},
            'students': [
              {
                'id': 7,
                'nickname': deleted ? '已注销' : '小明',
                'grade_band': '8-12',
                'active': !deleted,
              },
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
      addTearDown(client.close);
      await http.runWithClient(() async {
        await tester.pumpWidget(const MaterialApp(home: HomeScreen()));
        await tester.pumpAndSettle();
        await tester.ensureVisible(find.text('资料与设备'));
        await tester.pumpAndSettle();
        await tester.tap(find.text('资料与设备'));
        await tester.pumpAndSettle();
        Future<void> openConfirmation() async {
          await tester.ensureVisible(find.text('删除孩子'));
          await tester.pumpAndSettle();
          await tester.tap(find.text('删除孩子'));
          await tester.pumpAndSettle();
        }

        await openConfirmation();
        expect(attempts, 0);
        await tester.tap(find.text('取消'));
        await tester.pumpAndSettle();
        expect(attempts, 0);
        await openConfirmation();
        await tester.tap(find.widgetWithText(FilledButton, '删除'));
        await tester.pumpAndSettle();
        expect(attempts, 1);
        expect(find.text('Try again'), findsOneWidget);
        expect(find.byType(StudentReviewCard), findsOneWidget);
        await openConfirmation();
        await tester.tap(find.widgetWithText(FilledButton, '删除'));
        await tester.pumpAndSettle();
        expect(attempts, 2);
        expect(find.byType(StudentReviewCard), findsNothing);
        expect(find.text('添加孩子，开启学习陪伴'), findsOneWidget);
        expect(tester.takeException(), isNull);
      }, () => client);
    });
  }
}
