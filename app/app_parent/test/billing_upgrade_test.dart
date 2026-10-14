import 'dart:convert';

import 'package:app_parent/billing.dart';
import 'package:app_parent/screens/home_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

class TestBilling extends ParentBilling {
  TestBilling(this.accept);
  final bool accept;
  int purchases = 0;
  @override
  String get channel => 'appstore';
  @override
  Future<bool?> purchase(BuildContext context, String kind) async {
    expect(kind, 'seat_add');
    purchases++;
    return accept;
  }
}

void main() {
  for (final accepted in [true, false]) {
    testWidgets('名额不足走渠道购买，取消后不添加孩子 ($accepted)', (tester) async {
      tester.view.physicalSize = const Size(390, 844);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      var creates = 0;
      final billing = TestBilling(accepted);
      final client = MockClient((request) async {
        if (request.url.path == '/parent/students' &&
            request.method == 'POST') {
          creates++;
          return http.Response(
            creates == 1 ? '{"detail":"名额不足"}' : '{"bind_code":"123456"}',
            creates == 1 ? 409 : 200,
            headers: {'content-type': 'application/json; charset=utf-8'},
          );
        }
        final data = switch (request.url.path) {
          '/parent/family' => {
            'guardian': {'nickname': '家长', 'identity_verified': false},
            'students': [
              {'id': 1, 'nickname': '孩子', 'grade_band': '8-12'},
            ],
            'settings': {'daily_message_cap': 200, 'daily_minutes_cap': 60},
          },
          '/parent/subscription' => {
            'active': true,
            'plan': 'monthly',
            'seat_count': billing.purchases > 0 ? 10 : 1,
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
        await tester.pumpWidget(
          BillingScope(
            billing: billing,
            child: const MaterialApp(home: HomeScreen()),
          ),
        );
        await tester.pumpAndSettle();
        await tester.ensureVisible(find.text('添加孩子'));
        await tester.tap(find.text('添加孩子'));
        await tester.pumpAndSettle();
        await tester.tap(find.text('继续'));
        await tester.pumpAndSettle();
        expect(find.text('需要增加孩子名额'), findsOneWidget);
        await tester.tap(find.widgetWithText(FilledButton, '增加名额'));
        await tester.pumpAndSettle();
        expect(billing.purchases, 1);
        expect(creates, accepted ? 2 : 1);
        expect(
          find.text('我的孩子 的绑定码'),
          accepted ? findsOneWidget : findsNothing,
        );
      }, () => client);
      client.close();
      billing.dispose();
    });
  }
}
