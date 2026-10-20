import 'dart:convert';
import 'package:app_core/app_core.dart';
import 'package:app_parent/screens/review_screen.dart';
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
    testWidgets('用量卡片不展示旧接口返回的成本 ($channel)', (tester) async {
      Api.I.channel = channel;
      addTearDown(() => Api.I.channel = '');
      final client = MockClient((request) async {
        final data = switch (request.url.path) {
          '/parent/students/7/conversations' => <dynamic>[],
          '/parent/students/7/usage' => {
            'today': {'tokens_in': 120, 'tokens_out': 30, 'cost': 9876.54},
            'total': {'tokens_in': 1200, 'tokens_out': 300, 'cost': 98765.43},
            'unit': 'CNY',
          },
          '/parent/students/7/summary' => {'today': {}, 'week': {}},
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
        await tester.pumpWidget(
          const MaterialApp(
            home: ReviewScreen(studentId: 7, studentName: '演示学生'),
          ),
        );
        await tester.pumpAndSettle();
        expect(find.text('AI 用量'), findsOneWidget);
        await tester.tap(find.text('AI 用量'));
        await tester.pumpAndSettle();
        expect(find.text('今日：输入 120 / 输出 30 Token'), findsOneWidget);
        expect(find.text('累计：输入 1200 / 输出 300 Token'), findsOneWidget);
        expect(find.textContaining('成本'), findsNothing);
        expect(find.textContaining('¥'), findsNothing);
        expect(find.textContaining('9876'), findsNothing);
        expect(tester.takeException(), isNull);
      }, () => client);
    });
  }
}
