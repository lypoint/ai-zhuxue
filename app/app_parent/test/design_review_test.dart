import 'dart:convert';
import 'package:app_core/app_core.dart';
import 'package:app_parent/screens/grades_screen.dart';
import 'package:app_parent/screens/login_screen.dart';
import 'package:app_parent/theme/parent_theme.dart';
import 'package:app_parent/widgets/management_settings_card.dart';
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
  tearDown(() => AppLanguage.I.select('zh-Hans'));

  test('readable dates tolerate missing and invalid timestamps', () {
    expect(displayDate(null), '—');
    expect(displayDate('bad'), '—');
    expect(displayDate('2026-10-15'), '2026-10-15');
    expect(
      displayDate('2026-10-15T10:20:30.123456Z'),
      matches(r'^2026-10-\d{2} \d{2}:\d{2}$'),
    );
  });

  testWidgets('different subjects never share a trend line or direction', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: GradeTrendCard(
            trend: const {
              'direction': 'down',
              'latest': 88,
              'points': [
                {'percentage': 91},
                {'percentage': 88},
              ],
            },
            subjects: const ['数学', '语文'],
            subject: null,
            rangeDays: null,
            onChanged: (_, __) {},
          ),
        ),
      ),
    );
    expect(find.byType(TrendChart), findsNothing);
    expect(find.text('下降'), findsNothing);
    expect(find.textContaining('请选择一个科目'), findsOneWidget);
  });

  testWidgets(
    'fixed save bar keeps a failed draft and retries its exact values',
    (tester) async {
      var calls = 0;
      Map<String, dynamic>? saved;
      final client = MockClient((request) async {
        calls++;
        saved = jsonDecode(request.body) as Map<String, dynamic>;
        return http.Response(
          calls == 1 ? '{"detail":"unavailable"}' : '{}',
          calls == 1 ? 503 : 200,
        );
      });
      addTearDown(client.close);
      await http.runWithClient(() async {
        await tester.pumpWidget(
          MaterialApp(
            theme: parentTheme(),
            home: Scaffold(
              body: ManagementSettingsCard(
                scrollable: true,
                settings: const {
                  'daily_message_cap': 200,
                  'daily_minutes_cap': 60,
                },
                onSaved: () {},
              ),
            ),
          ),
        );
        expect(
          tester.widget<FilledButton>(find.byType(FilledButton)).onPressed,
          isNull,
        );
        await tester.enterText(find.byType(TextField).first, '150');
        await tester.pump();
        expect(find.text('有未保存的修改'), findsOneWidget);
        await tester.drag(
          find.byType(SingleChildScrollView).first,
          const Offset(0, -1600),
        );
        await tester.pumpAndSettle();
        await tester.tap(find.text('保存设置'));
        await tester.pumpAndSettle();
        expect(calls, 1);
        expect(find.text('有未保存的修改'), findsOneWidget);
        await tester.tap(find.text('保存设置'));
        await tester.pumpAndSettle();
        expect(calls, 2);
        expect(saved?['daily_message_cap'], 150);
        expect(saved?['quiet_start'], 22);
        expect(saved?['quiet_end'], 6);
        expect(find.text('有未保存的修改'), findsNothing);
        expect(tester.takeException(), isNull);
      }, () => client);
    },
  );

  testWidgets('English SMS login gives the phone field its full width', (
    tester,
  ) async {
    await AppLanguage.I.select('en');
    await tester.binding.setSurfaceSize(const Size(320, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(
      MaterialApp(theme: parentTheme(), home: const PhoneLoginScreen()),
    );
    await tester.pumpAndSettle();
    final field = tester.widget<TextField>(find.byType(TextField).at(1));
    expect(field.decoration?.suffixIcon, isNull);
    expect(tester.takeException(), isNull);
  });

  testWidgets(
    'grade form keeps invalid scores open and uses date/type selectors',
    (tester) async {
      final client = MockClient(
        (request) async => http.Response(
          request.url.path.endsWith('/grade-trend') ? '{"points":[]}' : '[]',
          200,
          headers: {'content-type': 'application/json'},
        ),
      );
      addTearDown(client.close);
      await http.runWithClient(() async {
        await tester.pumpWidget(
          MaterialApp(
            theme: parentTheme(),
            home: const GradesScreen(studentId: 7, studentName: '小明'),
          ),
        );
        await tester.pumpAndSettle();
        await tester.tap(find.byType(FloatingActionButton));
        await tester.pumpAndSettle();
        await tester.enterText(find.byType(TextFormField).at(0), '数学');
        await tester.enterText(find.byType(TextFormField).at(2), '101');
        await tester.tap(find.text('保存'));
        await tester.pumpAndSettle();
        expect(find.text('得分不能超过满分'), findsOneWidget);
        expect(
          tester
              .widget<TextField>(
                find.descendant(
                  of: find.byType(TextFormField).at(1),
                  matching: find.byType(TextField),
                ),
              )
              .readOnly,
          isTrue,
        );
        await tester.tap(find.text('更多信息（选填）'));
        await tester.pumpAndSettle();
        expect(find.byType(DropdownButtonFormField<String>), findsOneWidget);
        expect(find.text('考试'), findsOneWidget);
        expect(tester.takeException(), isNull);
      }, () => client);
    },
  );
}
