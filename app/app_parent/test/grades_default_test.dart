import 'dart:convert';

import 'package:app_core/app_core.dart';
import 'package:app_parent/screens/grades_screen.dart';
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

  testWidgets(
    'latest subject is selected and manual selection survives refresh',
    (tester) async {
      final subjects = <String?>[];
      final client = MockClient((request) async {
        final path = request.url.path;
        final Object body;
        if (path.endsWith('/grade-trend')) {
          subjects.add(request.url.queryParameters['subject']);
          body = {'points': []};
        } else if (path.endsWith('/grades')) {
          body = [
            {
              'subject': '数学',
              'exam_date': '2026-09-01',
              'score': 80,
              'max_score': 100,
            },
            {
              'subject': '语文',
              'exam_date': '2026-10-01',
              'score': 90,
              'max_score': 100,
            },
            {
              'subject': '英语',
              'exam_date': '2026-10-02',
              'deleted': true,
              'score': 70,
              'max_score': 100,
            },
          ];
        } else {
          body = [];
        }
        return http.Response(
          jsonEncode(body),
          200,
          headers: {'content-type': 'application/json; charset=utf-8'},
        );
      });
      addTearDown(client.close);
      await http.runWithClient(() async {
        await tester.pumpWidget(
          const MaterialApp(
            home: GradesScreen(studentId: 7, studentName: '小明'),
          ),
        );
        await tester.pumpAndSettle();
        expect(subjects, ['语文']);
        expect(
          tester.widget<GradeTrendCard>(find.byType(GradeTrendCard)).subject,
          '语文',
        );
        tester
            .widget<GradeTrendCard>(find.byType(GradeTrendCard))
            .onChanged('数学', null);
        await tester.pumpAndSettle();
        final refresh = tester
            .state<RefreshIndicatorState>(find.byType(RefreshIndicator))
            .show();
        await tester.pumpAndSettle();
        await refresh;
        expect(subjects.last, '数学');
        expect(
          tester.widget<GradeTrendCard>(find.byType(GradeTrendCard)).subject,
          '数学',
        );
        tester
            .widget<GradeTrendCard>(find.byType(GradeTrendCard))
            .onChanged(null, null);
        await tester.pumpAndSettle();
        final refreshAll = tester
            .state<RefreshIndicatorState>(find.byType(RefreshIndicator))
            .show();
        await tester.pumpAndSettle();
        await refreshAll;
        expect(
          tester.widget<GradeTrendCard>(find.byType(GradeTrendCard)).subject,
          isNull,
        );
        expect(tester.takeException(), isNull);
      }, () => client);
    },
  );

  testWidgets(
    'empty grades show one guide and keep deleted records accessible',
    (tester) async {
      final client = MockClient(
        (request) async => http.Response(
          request.url.path.endsWith('/grade-trend') ? '{"points":[]}' : '[]',
          200,
          headers: {'content-type': 'application/json; charset=utf-8'},
        ),
      );
      addTearDown(client.close);
      await http.runWithClient(() async {
        await tester.pumpWidget(
          const MaterialApp(
            home: GradesScreen(studentId: 7, studentName: '小明'),
          ),
        );
        await tester.pumpAndSettle();
        expect(find.byType(GradeTrendCard), findsNothing);
        expect(find.text('学业评估历史（0）'), findsNothing);
        expect(find.text('还没有成绩记录'), findsOneWidget);
        expect(find.text('新增成绩'), findsOneWidget);
        expect(find.byType(SwitchListTile), findsNothing);
        await tester.tap(find.text('成绩显示选项'));
        await tester.pumpAndSettle();
        expect(find.text('显示已删除成绩'), findsOneWidget);
        await tester.tap(find.byType(SwitchListTile));
        await tester.pumpAndSettle();
        expect(
          tester.widget<SwitchListTile>(find.byType(SwitchListTile)).value,
          isTrue,
        );
        expect(tester.takeException(), isNull);
      }, () => client);
    },
  );
}
