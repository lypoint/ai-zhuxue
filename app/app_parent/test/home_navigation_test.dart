import 'dart:convert';

import 'package:app_parent/theme/parent_theme.dart';
import 'package:app_parent/screens/home_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  for (final width in [390.0, 320.0]) {
    testWidgets('家庭导航分组且保留未保存的守护设置 ($width)', (tester) async {
      tester.view.physicalSize = Size(width, 844);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final client = MockClient((request) async {
        final data = switch (request.url.path) {
          '/parent/family' => {
            'guardian': {'nickname': '小明妈妈', 'identity_verified': false},
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
        expect(find.text('学习守护'), findsOneWidget);
        await tester.enterText(find.byType(TextField).first, '180');
        final editingFocus = tester
            .widget<EditableText>(find.byType(EditableText).first)
            .focusNode;
        expect(editingFocus.hasFocus, isTrue);
        await switchTo('我的');
        expect(editingFocus.hasFocus, isFalse);
        expect(find.text('实名认证'), findsOneWidget);
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
