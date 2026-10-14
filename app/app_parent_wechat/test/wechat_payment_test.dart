import 'dart:convert';

import 'package:app_parent_wechat/payment_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  testWidgets(
    '微信 SDK 成功回调仍须服务端确认后才返回成功',
    (tester) async {
      const channel = MethodChannel('com.jarvanmo/fluwx');
      final messenger = tester.binding.defaultBinaryMessenger;
      Map<dynamic, dynamic>? sdkPayment;
      messenger.setMockMethodCallHandler(channel, (call) async {
        if (call.method == 'payWithFluwx') sdkPayment = call.arguments as Map;
        return true;
      });
      addTearDown(() => messenger.setMockMethodCallHandler(channel, null));
      final order = <String, dynamic>{
        'order_id': 9,
        'out_trade_no': 'wechat-order-9',
        'kind': 'subscription',
        'status': 'pending',
        'payment_mode': 'wechat',
        'amount_cents': 6600,
        'payment_params': {
          'appId': 'wx_test_app',
          'partnerId': '1900000001',
          'prepayId': 'test-prepay',
          'packageValue': 'Sign=WXPay',
          'nonceStr': 'nonce',
          'timeStamp': '1700000000',
          'sign': 'server-signed-value',
        },
      };
      var paid = false;
      final client = MockClient(
        (request) async => http.Response(
          jsonEncode({...order, 'status': paid ? 'paid' : 'pending'}),
          200,
        ),
      );
      addTearDown(client.close);
      await http.runWithClient(() async {
        await tester.pumpWidget(
          MaterialApp(
            home: Builder(
              builder: (context) => Scaffold(
                body: TextButton(
                  onPressed: () => Navigator.push(
                    context,
                    MaterialPageRoute(
                      builder: (_) => PaymentScreen(order: order),
                    ),
                  ),
                  child: const Text('打开订单'),
                ),
              ),
            ),
          ),
        );
        await tester.tap(find.text('打开订单'));
        await tester.pumpAndSettle();
        await tester.tap(find.text('使用微信支付'));
        await tester.pumpAndSettle();
        expect(sdkPayment?['prepayId'], 'test-prepay');
        expect(sdkPayment?['sign'], 'server-signed-value');
        await messenger.handlePlatformMessage(
          channel.name,
          const StandardMethodCodec().encodeMethodCall(
            const MethodCall('onPayResponse', {
              'errCode': 0,
              'errStr': '',
              'type': 5,
            }),
          ),
          (_) {},
        );
        await tester.pumpAndSettle();
        expect(find.text('确认订单'), findsOneWidget);
        paid = true;
        await tester.tap(find.text('刷新支付结果'));
        await tester.pumpAndSettle();
        expect(find.text('打开订单'), findsOneWidget);
        expect(tester.takeException(), isNull);
      }, () => client);
    },
    skip: const String.fromEnvironment('WECHAT_APP_ID') != 'wx_test_app',
  );
}
