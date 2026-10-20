import 'dart:convert';

import 'package:app_core/app_core.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

const emptySummary = {
  'balance': 0,
  'earned': 0,
  'spent': 0,
  'rule': '规则',
  'agreements': [],
  'days': [],
  'redemptions': [],
  'history': [],
};

void main() {
  setUpAll(() async {
    SharedPreferences.setMockInitialValues({'app_language': 'zh-Hans'});
    await AppLanguage.I.load();
  });

  testWidgets('reward validation retains focused draft and retries safely', (
    tester,
  ) async {
    final posts = <Map<String, dynamic>>[];
    final client = MockClient((request) async {
      if (request.method == 'POST') {
        posts.add(jsonDecode(request.body) as Map<String, dynamic>);
        if (posts.length == 1) {
          return http.Response('{"detail":"unavailable"}', 503);
        }
      }
      return http.Response(
        jsonEncode(emptySummary),
        200,
        headers: {'content-type': 'application/json; charset=utf-8'},
      );
    });
    addTearDown(client.close);
    await http.runWithClient(() async {
      await tester.pumpWidget(
        const MaterialApp(home: LearningScreen(studentId: 7)),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('约定新奖励'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextFormField).at(0), 'Weekend-Park');
      await tester.tap(find.text('邀请孩子确认'));
      await tester.pumpAndSettle();
      expect(find.byType(AlertDialog), findsOneWidget);
      expect(find.text('请填写此项'), findsOneWidget);
      expect(find.text('Weekend-Park'), findsOneWidget);
      expect(posts, isEmpty);
      expect(tester.takeException(), isNull);

      for (final value in ['0', '100001', '1.5']) {
        await tester.enterText(find.byType(TextFormField).at(1), value);
        await tester.tap(find.text('邀请孩子确认'));
        await tester.pumpAndSettle();
        expect(find.text('请输入 1–100000 的整数'), findsOneWidget);
        expect(posts, isEmpty);
      }
      await tester.enterText(find.byType(TextFormField).at(1), '2');
      await tester.enterText(
        find.byType(TextFormField).at(2),
        ' This weekend ',
      );
      await tester.tap(find.text('邀请孩子确认'));
      await tester.pumpAndSettle();
      expect(find.byType(AlertDialog), findsNothing);
      expect(find.text('unavailable'), findsOneWidget);
      expect(posts.single['fulfillment'], 'This weekend');
      expect(tester.takeException(), isNull);

      await tester.tap(find.text('约定新奖励'));
      await tester.pumpAndSettle();
      expect(find.text('Weekend-Park'), findsOneWidget);
      expect(find.text('This weekend'), findsOneWidget);
      await tester.tap(find.byType(TextFormField).first);
      await tester.tap(find.text('邀请孩子确认'));
      await tester.pumpAndSettle();
      expect(posts, hasLength(2));
      expect(posts[1], posts[0]); // Retry preserves the idempotency key.
      expect(tester.takeException(), isNull);

      await tester.tap(find.text('约定新奖励'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextFormField).first, 'Cancel draft');
      await tester.tap(find.text('取消'));
      await tester.pumpAndSettle();
      expect(posts, hasLength(2));
      expect(tester.takeException(), isNull);
    }, () => client);
  });

  testWidgets(
    'reward empty state keeps the next action without empty sections',
    (tester) async {
      final client = MockClient(
        (_) async => http.Response(
          jsonEncode(emptySummary),
          200,
          headers: {'content-type': 'application/json; charset=utf-8'},
        ),
      );
      addTearDown(client.close);
      await http.runWithClient(() async {
        await tester.pumpWidget(
          const MaterialApp(home: LearningScreen(studentId: 7)),
        );
        await tester.pumpAndSettle();
        expect(find.text('约定新奖励'), findsOneWidget);
        expect(find.text('奖励兑换记录'), findsNothing);
        expect(find.text('反馈变化记录'), findsNothing);
        expect(find.text('每日反馈分布（含反馈更新）'), findsNothing);
        expect(find.text('孩子在对话中反馈后，这里会显示学习反馈与小行星变化。'), findsOneWidget);
        expect(tester.takeException(), isNull);
      }, () => client);
    },
  );
  testWidgets('student reward copy uses the student perspective', (
    tester,
  ) async {
    final client = MockClient(
      (_) async => http.Response(
        jsonEncode({
          ...emptySummary,
          'agreements': [
            {
              'id': 1,
              'reward': '公园',
              'stars': 1,
              'fulfillment': '周末',
              'accepted': false,
            },
            {
              'id': 2,
              'reward': '读书',
              'stars': 1,
              'fulfillment': '周末',
              'accepted': true,
            },
          ],
        }),
        200,
        headers: {'content-type': 'application/json; charset=utf-8'},
      ),
    );
    addTearDown(client.close);
    await http.runWithClient(() async {
      await tester.pumpWidget(const MaterialApp(home: LearningScreen()));
      await tester.pumpAndSettle();
      expect(find.text('等待你确认'), findsOneWidget);
      expect(find.text('你已确认'), findsOneWidget);
      expect(find.text('等待孩子确认'), findsNothing);
      await tester.scrollUntilVisible(
        find.text('你在对话中反馈后，这里会显示学习反馈与小行星变化。'),
        250,
        scrollable: find.byType(Scrollable).first,
      );
      expect(tester.takeException(), isNull);
    }, () => client);
  });
}
