import 'dart:convert';

import 'package:app_core/app_core.dart';
import 'package:app_parent/screens/account_deletion_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  for (final channel in ['wechat', 'appstore', 'googleplay']) {
    testWidgets(
      'deletion requires confirmation and clears only the accepted session ($channel)',
      (tester) async {
        Api.I.channel = channel;
        final tokenKey = channel == 'googleplay'
            ? 'google_login_token'
            : 'token';
        SharedPreferences.setMockInitialValues({tokenKey: 'session'});
        await Api.I.loadToken();
        var attempts = 0;
        var managed = false;
        final client = MockClient((request) async {
          expect(request.method, 'POST');
          expect(request.url.path, '/parent/account/deletion-request');
          expect(request.headers['Authorization'], 'Bearer session');
          expect(request.headers['X-App-Channel'], channel);
          expect(jsonDecode(request.body), {'confirmation': 'DELETE'});
          attempts++;
          return http.Response(
            attempts == 1
                ? '{"detail":"Try again"}'
                : '{"status":"pending","request_id":"AD-1"}',
            attempts == 1 ? 503 : 202,
          );
        });
        await http.runWithClient(() async {
          await tester.pumpWidget(
            MaterialApp(
              home: AccountDeletionScreen(
                onManageSubscription: () => managed = true,
              ),
            ),
          );
          await tester.pumpAndSettle();
          final submit = find.widgetWithText(FilledButton, '申请删除账号');
          expect(tester.widget<FilledButton>(submit).onPressed, isNull);
          await tester.tap(find.text('管理订阅'));
          expect(managed, true);
          await tester.enterText(find.byType(TextField), 'DELETE');
          await tester.pumpAndSettle();
          await tester.ensureVisible(submit);
          await tester.tap(submit);
          await tester.pumpAndSettle();
          expect(find.text('Try again'), findsOneWidget);
          expect(Api.I.hasToken, true);
          expect(
            (await SharedPreferences.getInstance()).getString(tokenKey),
            'session',
          );
          await tester.tap(submit);
          await tester.pumpAndSettle();
          expect(attempts, 2);
          expect(find.text('删除申请已提交'), findsOneWidget);
          expect(find.text('申请编号：AD-1'), findsOneWidget);
          expect(Api.I.hasToken, false);
          expect(
            (await SharedPreferences.getInstance()).getString(tokenKey),
            isNull,
          );
        }, () => client);
        client.close();
        Api.I.channel = '';
      },
    );
  }
}
