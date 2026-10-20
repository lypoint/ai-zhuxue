import 'package:app_parent/billing.dart';
import 'package:app_parent_wechat/wechat_billing.dart';
import 'dart:convert';

import 'package:app_parent/theme/parent_theme.dart';
import 'package:app_parent/screens/home_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  for (final seats in [10, 100]) {
    testWidgets('选择 $seats 名额套餐并按目标总名额创建订单', (tester) async {
      tester.view.physicalSize = const Size(390, 844);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final cents = seats == 10 ? 30000 : 300000;
      Map<String, dynamic>? createdBody;
      final order = {
        'order_id': 7,
        'out_trade_no': 'tier-order',
        'kind': 'seat_add',
        'status': 'pending',
        'payment_mode': 'demo',
        'billing_rule': 'monthly_tier_v1',
        'target_seat_count': seats,
        'amount_cents': cents,
      };
      final client = MockClient((request) async {
        if (request.url.path == '/parent/payments/orders' &&
            request.method == 'POST') {
          createdBody = jsonDecode(request.body) as Map<String, dynamic>;
          return http.Response(jsonEncode(order), 200);
        }
        final data = switch (request.url.path) {
          '/parent/family' => {
            'guardian': {'nickname': '家长'},
            'students': [
              {'id': 1, 'nickname': '孩子', 'grade_band': '8-12'},
            ],
            'settings': {'daily_message_cap': 200, 'daily_minutes_cap': 60},
          },
          '/parent/subscription' => {
            'active': true,
            'plan': 'monthly',
            'seat_count': 1,
          },
          '/parent/notifications' => {'unread': 0},
          '/parent/payments/pending' => {'items': <dynamic>[]},
          '/parent/billing/catalog' => {
            'items': [
              {'seat_count': 2, 'amount_cents': 9900},
              {'seat_count': 10, 'amount_cents': 30000},
              {'seat_count': 100, 'amount_cents': 300000},
            ],
          },
          '/parent/payments/orders/7' => order,
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
          BillingScope(billing: WechatBilling(), child: MaterialApp(theme: parentTheme(), home: const HomeScreen())),
        );
        await tester.pumpAndSettle();
        await tester.tap(
          find.descendant(
            of: find.byType(NavigationBar),
            matching: find.text('我的'),
          ),
        );
        await tester.pumpAndSettle();
        await tester.ensureVisible(find.text('增加名额'));
        await tester.tap(find.text('增加名额'));
        await tester.pumpAndSettle();
        expect(find.text('选择升级后的总名额'), findsOneWidget);
        await tester.tap(
          find.text('$seats 个名额 · ¥${(cents / 100).toStringAsFixed(2)}/月'),
        );
        await tester.pumpAndSettle();
        expect(createdBody?['kind'], 'seat_add');
        expect(createdBody?['target_seat_count'], seats);
        expect(find.text('家庭月订阅 · $seats 个孩子名额'), findsOneWidget);
        expect(
          find.text('¥${(cents / 100).toStringAsFixed(2)}'),
          findsOneWidget,
        );
        expect(tester.takeException(), isNull);
      }, () => client);
    });
  }

  for (final width in [390.0, 320.0]) {
    testWidgets('家庭导航分组且保留未保存的守护设置 ($width)', (tester) async {
      tester.view.physicalSize = Size(width, 844);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final client = MockClient((request) async {
        final data = switch (request.url.path) {
          '/parent/family' => {
            'guardian': {'nickname': '小明妈妈'},
            'students': [
              {'id': 1, 'nickname': '小明', 'grade_band': '8-12'},
              {'id': 2, 'nickname': '小红', 'grade_band': '12-16'},
            ],
            'settings': {'daily_message_cap': 200, 'daily_minutes_cap': 60},
          },
          '/parent/subscription' => {
            'active': true,
            'plan': 'monthly',
            'days_left': 12,
          },
          '/parent/notifications' => {'unread': 2},
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
          MaterialApp(
            theme: parentTheme(),
            builder: (context, child) => MediaQuery(
              data: MediaQuery.of(
                context,
              ).copyWith(textScaler: TextScaler.linear(width == 320 ? 1.4 : 1)),
              child: child!,
            ),
            home: const HomeScreen(),
          ),
        );
        await tester.pumpAndSettle();
        expect(find.text('孩子的学习'), findsOneWidget);
        expect(find.text('实名认证'), findsNothing);
        expect(find.byType(TextField), findsNothing);
        expect(tester.takeException(), isNull);

        Future<void> switchTo(String label) async {
          await tester.tap(
            find.descendant(
              of: find.byType(NavigationBar),
              matching: find.text(label),
            ),
          );
          await tester.pumpAndSettle();
          expect(tester.takeException(), isNull);
        }

        await switchTo('守护');
        expect(find.text('每日使用'), findsOneWidget);
        await tester.enterText(find.byType(TextField).first, '180');
        final editingFocus = tester
            .widget<EditableText>(find.byType(EditableText).first)
            .focusNode;
        expect(editingFocus.hasFocus, isTrue);
        await switchTo('我的');
        expect(editingFocus.hasFocus, isFalse);
        expect(find.text('实名认证'), findsNothing);
        expect(find.textContaining('订阅生效中'), findsOneWidget);
        await switchTo('守护');
        expect(
          tester
              .widget<TextField>(find.byType(TextField).first)
              .controller!
              .text,
          '180',
        );
        await switchTo('家庭');
        expect(find.text('孩子的学习'), findsOneWidget);
      }, () => client);
    });
  }
}
