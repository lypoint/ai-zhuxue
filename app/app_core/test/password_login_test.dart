import 'dart:convert';
import 'package:app_core/app_core.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUpAll(() async {
    SharedPreferences.setMockInitialValues({'app_language': 'zh-Hans'});
    await AppLanguage.I.load();
  });
  tearDown(() {
    Api.onUnauthorized = null;
    Api.I.clearToken();
  });

  test(
    'password requests carry channel and keep credentials out of URL',
    () async {
      for (final channel in ['wechat', 'appstore', 'googleplay', 'harmony']) {
        Api.I.channel = channel;
        await http.runWithClient(
          () async {
            await Api.I.passwordLogin('reviewtest', 'test-password');
            expect(Api.I.hasToken, true);
          },
          () => MockClient((request) async {
            expect(request.url.path, '/auth/guardian/password');
            expect(request.url.query, isEmpty);
            expect(request.headers['X-App-Channel'], channel);
            expect(jsonDecode(request.body), {
              'username': 'reviewtest',
              'password': 'test-password',
            });
            return http.Response('{"token":"test-session"}', 200);
          }),
        );
      }
    },
  );

  testWidgets('wrong password stays on form; retry enters the app', (
    tester,
  ) async {
    var attempts = 0;
    var signedIn = false;
    var unauthorized = false;
    Api.onUnauthorized = () => unauthorized = true;
    await http.runWithClient(
      () async {
        await tester.pumpWidget(
          MaterialApp(
            home: Scaffold(
              body: PasswordLoginButton(onLoggedIn: () => signedIn = true),
            ),
          ),
        );
        await tester.tap(find.text('账号密码登录'));
        await tester.pumpAndSettle();
        await tester.enterText(find.byType(TextField).at(0), 'reviewtest');
        await tester.enterText(find.byType(TextField).at(1), 'test-password');
        expect(
          tester.widget<TextField>(find.byType(TextField).at(1)).obscureText,
          true,
        );
        await tester.tap(find.text('登录'));
        await tester.pumpAndSettle();
        expect(find.text('账号或密码错误'), findsOneWidget);
        expect(signedIn, false);
        expect(unauthorized, false);
        await tester.tap(find.text('登录'));
        await tester.pumpAndSettle();
        expect(signedIn, true);
      },
      () => MockClient((request) async {
        attempts++;
        return attempts == 1
            ? http.Response(
                '{"detail":"账号或密码错误"}',
                401,
                headers: {'content-type': 'application/json; charset=utf-8'},
              )
            : http.Response('{"token":"test-session"}', 200);
      }),
    );
  });
}
