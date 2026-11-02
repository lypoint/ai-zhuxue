import 'dart:convert';
import 'dart:io';
import 'package:flutter/services.dart';
import 'package:app_parent/screens/review_screen.dart';
import 'package:app_parent/screens/family_timezone_screen.dart';
import 'package:app_core/app_core.dart';
import 'package:app_parent/screens/notifications_screen.dart';
import 'package:app_parent/billing.dart';
import 'package:app_parent/widgets/management_settings_card.dart';
import 'package:app_parent/widgets/subscription_card.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  test(
    'management follows the entitlement source and rejects untrusted Waffo redirects',
    () {
      expect(subscriptionManagementUri('appstore')!.host, 'apps.apple.com');
      expect(subscriptionManagementUri('googleplay')!.host, 'play.google.com');
      expect(
        subscriptionManagementUri(
          'waffo',
          waffoUrl: 'https://pancake.waffo.ai/consumer/portal/session',
        )!.host,
        'pancake.waffo.ai',
      );
      for (final url in [
        'https://evil.example/consumer/portal/token',
        'http://pancake.waffo.ai/consumer/portal/token',
        'https://pancake.waffo.ai/store/pay',
        'https://user@pancake.waffo.ai/consumer/portal/token',
      ]) {
        expect(
          () => subscriptionManagementUri('waffo', waffoUrl: url),
          throwsFormatException,
        );
      }
      expect(subscriptionManagementUri('wechat'), isNull);
    },
  );
  testWidgets(
    'child controls save to the chosen child instead of family defaults',
    (tester) async {
      var saved = false;
      await http.runWithClient(
        () async {
          await tester.pumpWidget(
            MaterialApp(
              home: Scaffold(
                body: SingleChildScrollView(
                  child: ManagementSettingsCard(
                    studentId: 42,
                    settings: const {
                      'daily_message_cap': 200,
                      'daily_minutes_cap': 60,
                    },
                    onSaved: () => saved = true,
                  ),
                ),
              ),
            ),
          );
          await tester.enterText(find.byType(TextField).at(1), '25');
          await tester.pump();
          await tester.ensureVisible(find.text('保存设置'));
          await tester.tap(find.text('保存设置'));
          await tester.pumpAndSettle();
          expect(saved, isTrue);
        },
        () => MockClient((request) async {
          expect(request.url.path, '/parent/students/42/learning-settings');
          expect(jsonDecode(request.body)['daily_minutes_cap'], 25);
          return http.Response('{}', 200);
        }),
      );
    },
  );
  testWidgets(
    'subscription trial and recovery never claim there will be no charge',
    (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(
              child: SubscriptionCard(
                sub: const {
                  'plan': 'subscription_trial',
                  'active': true,
                  'provider': 'waffo',
                  'billing_status': 'grace',
                  'auto_renew': false,
                },
                onPay: () {},
                onManage: () {},
              ),
            ),
          ),
        ),
      );
      expect(find.text('付款恢复中'), findsOneWidget);
      expect(find.text('不会自动扣款'), findsNothing);
      expect(find.text('增加名额'), findsNothing);
      expect(find.text('管理原渠道订阅'), findsOneWidget);
    },
  );
  testWidgets(
    'notification pages and unread filter request the server, keeping page on failure',
    (tester) async {
      final requests = <Uri>[];
      var failNext = false;
      await http.runWithClient(
        () async {
          await tester.pumpWidget(
            const MaterialApp(home: NotificationsScreen()),
          );
          await tester.pumpAndSettle();
          expect(find.text('page-1-false'), findsOneWidget);
          await tester.tap(find.text('下一页'));
          await tester.pumpAndSettle();
          expect(find.text('page-2-false'), findsOneWidget);
          failNext = true;
          await tester.tap(find.text('下一页'));
          await tester.pumpAndSettle();
          expect(find.text('page-2-false'), findsOneWidget);
          expect(find.text('2 / 3'), findsOneWidget);
          failNext = false;
          await tester.tap(find.byType(Switch));
          await tester.pumpAndSettle();
          expect(find.text('page-1-true'), findsOneWidget);
          expect(requests.last.queryParameters['unread_only'], 'true');
          expect(requests.last.queryParameters['page'], '1');
        },
        () => MockClient((request) async {
          requests.add(request.url);
          if (failNext) return http.Response('{"detail":"offline"}', 503);
          final q = request.url.queryParameters;
          return http.Response(
            jsonEncode({
              'total': 61,
              'unread': 2,
              'items': [
                {
                  'id': 1,
                  'type': 'system',
                  'title': 'page-${q['page']}-${q['unread_only']}',
                  'body': '',
                  'is_read': false,
                },
              ],
            }),
            200,
          );
        }),
      );
    },
  );

  testWidgets('failed time-zone change keeps the confirmed family zone', (
    tester,
  ) async {
    FamilyTime.zone = 'Europe/London';
    await http.runWithClient(
      () async {
        await tester.pumpWidget(
          const MaterialApp(home: FamilyTimezoneScreen(zone: 'Europe/London')),
        );
        await tester.enterText(find.byType(TextField), 'Asia/Tokyo');
        await tester.pump();
        await tester.tap(find.widgetWithText(ListTile, 'Asia/Tokyo'));
        await tester.pumpAndSettle();
        expect(FamilyTime.zone, 'Europe/London');
        expect(find.text('change limited'), findsOneWidget);
      },
      () => MockClient((request) async {
        expect(jsonDecode(request.body), {'timezone': 'Asia/Tokyo'});
        return http.Response('{"detail":"change limited"}', 409);
      }),
    );
    FamilyTime.zone = null;
  });

  testWidgets('export shares a JSON file belonging to the selected child', (
    tester,
  ) async {
    final directory = (await tester.runAsync(
      () => Directory.systemTemp.createTemp('export-widget-'),
    ))!;
    Map<dynamic, dynamic>? shared;
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      (call) async => directory.path,
    );
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('dev.fluttercommunity.plus/share'),
      (call) async {
        shared = call.arguments as Map;
        return 'success';
      },
    );
    await http.runWithClient(
      () async {
        await tester.pumpWidget(
          const MaterialApp(
            home: ReviewScreen(studentId: 42, studentName: 'child'),
          ),
        );
        await tester.pumpAndSettle();
        await tester.runAsync(() async {
          await tester.tap(find.byTooltip('导出学习数据'));
          await Future<void>.delayed(const Duration(milliseconds: 100));
        });
        await tester.pumpAndSettle();
        expect(shared, isNotNull);
        await tester.runAsync(() async {
          final file = File((shared!['paths'] as List).single as String);
          expect(jsonDecode(await file.readAsString())['student']['id'], 42);
        });
        await tester.pumpWidget(const SizedBox.shrink());
      },
      () => MockClient((request) async {
        if (request.url.path.endsWith('/export')) {
          expect(request.url.path, '/parent/students/42/export');
          return http.Response('{"student":{"id":42},"conversations":[]}', 200);
        }
        return http.Response(
          request.url.path.endsWith('/conversations')
              ? '[]'
              : '{"total":{"tokens_in":0,"tokens_out":0},"today":{"tokens_in":0,"tokens_out":0}}',
          200,
        );
      }),
    );
    await tester.runAsync(() => directory.delete(recursive: true));
    for (final name in [
      'plugins.flutter.io/path_provider',
      'dev.fluttercommunity.plus/share',
    ]) {
      tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
        MethodChannel(name),
        null,
      );
    }
  });

  testWidgets(
    'Google registration trial does not promise an immediate charge or bonus days',
    (tester) async {
      Api.I.channel = 'googleplay';
      addTearDown(() => Api.I.channel = '');
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(
              child: SubscriptionCard(
                sub: const {'plan': 'free_trial', 'active': true},
                onPay: () {},
                onManage: () {},
              ),
            ),
          ),
        ),
      );
      expect(find.text('立即付款，剩余试用时长保留。'), findsNothing);
      expect(find.text('赠送时长不推迟自动扣款；取消自动续订后仍可使用。'), findsNothing);
      expect(find.textContaining('注册试用 3 天'), findsOneWidget);
    },
  );
}
