import 'dart:convert';

import 'package:app_parent_wechat/payment_screen.dart';
import 'package:app_parent/theme/parent_theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  for (final width in [390.0, 320.0]) {
    testWidgets('演示订单展示服务端金额且确认后返回成功 ($width)', (tester) async {
      tester.view.physicalSize = Size(width, 844);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final order = <String, dynamic>{
        'order_id': 7,
        'out_trade_no': 'test-order-7',
        'kind': 'subscription',
        'status': 'pending',
        'payment_mode': 'demo',
        'billing_rule': 'monthly_tier_v1',
        'target_seat_count': 2,
        'amount_cents': 9900,
        'payment_params': <String, dynamic>{},
      };
      var confirms = 0;
      final client = MockClient((request) async {
        if (request.url.path.endsWith('/demo-confirm')) {
          confirms++;
          return http.Response(jsonEncode({...order, 'status': 'paid'}), 200);
        }
        expect(request.method, 'GET');
        return http.Response(jsonEncode(order), 200);
      });
      addTearDown(client.close);
      await http.runWithClient(() async {
        await tester.pumpWidget(
          MaterialApp(
            theme: parentTheme(),
            home: Builder(
              builder: (context) => Scaffold(
                body: TextButton(
                  onPressed: () async {
                    final paid = await Navigator.push<bool>(
                      context,
                      MaterialPageRoute(
                        builder: (_) => PaymentScreen(order: order),
                      ),
                    );
                    if (context.mounted && paid == true) {
                      ScaffoldMessenger.of(
                        context,
                      ).showSnackBar(const SnackBar(content: Text('已验证支付')));
                    }
                  },
                  child: const Text('打开订单'),
                ),
              ),
            ),
          ),
        );
        await tester.tap(find.text('打开订单'));
        await tester.pumpAndSettle();
        expect(find.text('¥99.00'), findsOneWidget);
        expect(find.text('家庭月订阅 · 2 个孩子名额'), findsOneWidget);
        expect(find.textContaining('一个自然月'), findsOneWidget);
        expect(find.textContaining('不会扣款'), findsOneWidget);
        expect(tester.takeException(), isNull);
        await tester.tap(find.text('确认演示支付'));
        await tester.pumpAndSettle();
        expect(confirms, 1);
        expect(find.text('已验证支付'), findsOneWidget);
        expect(tester.takeException(), isNull);
      }, () => client);
    });
  }
}
