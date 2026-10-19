import 'dart:async';

import 'package:app_parent/screens/login_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets(
    '等待授权超过15秒不回退，SDK失败后才显示短信登录',
    (tester) async {
      const channel = MethodChannel('ai.zhuxue/one_tap');
      final token = Completer<String>();
      var requestedToken = false;
      tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(channel, (
        call,
      ) async {
        if (call.method == 'isAvailable') return true;
        if (call.method == 'getLoginToken') {
          requestedToken = true;
          return token.future;
        }
        throw StateError('Unexpected method: ${call.method}');
      });
      addTearDown(
        () => tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
          channel,
          null,
        ),
      );

      await tester.pumpWidget(const MaterialApp(home: PhoneLoginScreen()));
      await tester.pump();
      expect(requestedToken, isTrue);
      await tester.pump(const Duration(seconds: 20));
      expect(find.text('发送验证码'), findsNothing);
      expect(find.textContaining('已切换短信验证码登录'), findsNothing);

      token.completeError(PlatformException(code: 'ONE_TAP_UNAVAILABLE'));
      await tester.pump();
      await tester.pump();
      expect(find.text('发送验证码'), findsOneWidget);
      expect(find.textContaining('已切换短信验证码登录'), findsWidgets);
      expect(tester.takeException(), isNull);
    },
    variant: TargetPlatformVariant.only(TargetPlatform.android),
    // Run with --dart-define=ALIYUN_AUTH_SDK_KEY=test-only to exercise the SDK path.
    skip: const String.fromEnvironment('ALIYUN_AUTH_SDK_KEY').isEmpty,
  );
}
