import 'dart:convert';
import 'package:app_core/app_core.dart';
import 'package:app_student/screens/favorites_screen.dart';
import 'package:app_student/screens/grades_screen.dart';
import 'package:app_student/screens/my_stats_screen.dart';
import 'package:app_student/theme/student_theme.dart';
import 'package:app_student/widgets/student_page_state.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gpt_markdown/gpt_markdown.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

http.Response response(Object data, [int status = 200]) => http.Response(
  jsonEncode(data),
  status,
  headers: {'content-type': 'application/json; charset=utf-8'},
);

Widget page(Widget child) => MaterialApp(
  theme: studentTheme(),
  home: child,
  builder: (context, child) => MediaQuery(
    data: MediaQuery.of(
      context,
    ).copyWith(textScaler: const TextScaler.linear(1.4)),
    child: child!,
  ),
);

void main() {
  testWidgets('收藏折叠预览，展开保留公式，取消收藏使用对应记录 ID', (tester) async {
    String? deleted;
    final client = MockClient((request) async {
      if (request.method == 'DELETE') {
        deleted = request.url.path;
        return response({});
      }
      return response([
        {'id': 7, 'content': '## 分数加法\n先通分，再相加：\n\$1/2+1/3=5/6\$'},
      ]);
    });
    addTearDown(client.close);
    await http.runWithClient(() async {
      await tester.pumpWidget(page(const FavoritesScreen()));
      await tester.pumpAndSettle();
      expect(find.text('分数加法'), findsOneWidget);
      expect(find.byType(GptMarkdown), findsNothing);
      await tester.tap(find.text('分数加法'));
      await tester.pumpAndSettle();
      expect(find.byType(GptMarkdown), findsOneWidget);
      await tester.ensureVisible(find.text('取消收藏'));
      await tester.tap(find.text('取消收藏'));
      await tester.pumpAndSettle();
      expect(deleted, '/chat/favorites/7');
      expect(find.text('把值得复习的讲解留下来'), findsOneWidget);
      expect(tester.takeException(), isNull);
    }, () => client);
  });

  testWidgets('收藏失败可重试且不会丢失服务端内容', (tester) async {
    var requests = 0;
    final client = MockClient(
      (_) async => ++requests == 1
          ? response({'detail': '暂时无法连接'}, 503)
          : response([
              {'id': 8, 'content': '复习重点'},
            ]),
    );
    addTearDown(client.close);
    await http.runWithClient(() async {
      await tester.pumpWidget(page(const FavoritesScreen()));
      await tester.pumpAndSettle();
      expect(find.text('暂时无法连接'), findsOneWidget);
      await tester.tap(find.text('重试'));
      await tester.pumpAndSettle();
      expect(find.text('复习重点'), findsOneWidget);
      expect(find.text('收藏加载失败'), findsNothing);
    }, () => client);
  });

  testWidgets('学习统计在窄屏大字体展示真实数值，无溢出', (tester) async {
    tester.view.physicalSize = const Size(320, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final client = MockClient(
      (_) async => response({
        'today': {'questions': 12, 'minutes': 30, 'blocked': 1},
        'week': {
          'questions': 99,
          'minutes': 180,
          'blocked': 2,
          'active_days': 5,
        },
        'favorites': 8,
      }),
    );
    addTearDown(client.close);
    await http.runWithClient(() async {
      await tester.pumpWidget(page(const MyStatsScreen()));
      await tester.pumpAndSettle();
      expect(find.text('12 次'), findsOneWidget);
      expect(find.text('约 30 分钟'), findsOneWidget);
      await tester.ensureVisible(find.text('8 条'));
      expect(tester.takeException(), isNull);
    }, () => client);
  });

  testWidgets('成绩类型显示中文，保存保留接口枚举值', (tester) async {
    Map<String, dynamic>? saved;
    final client = MockClient((request) async {
      if (request.method == 'POST') {
        saved = jsonDecode(request.body) as Map<String, dynamic>;
        return response({'id': 9});
      }
      return response(
        request.url.path == '/chat/grade-trend' ? <String, dynamic>{} : [],
      );
    });
    addTearDown(client.close);
    await http.runWithClient(() async {
      await tester.pumpWidget(page(const GradesScreen()));
      await tester.pumpAndSettle();
      await tester.tap(find.text('记录成绩'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField).at(0), '数学');
      await tester.enterText(find.byType(TextField).at(1), '分数练习');
      await tester.ensureVisible(find.byType(TextField).at(3));
      await tester.enterText(find.byType(TextField).at(3), '90');
      final type = find.byType(DropdownButtonFormField<String>);
      await tester.ensureVisible(type);
      await tester.tap(type);
      await tester.pumpAndSettle();
      await tester.tap(find.text('作业').last);
      await tester.pumpAndSettle();
      await tester.tap(find.text('保存'));
      await tester.pumpAndSettle();
      expect(saved?['grade_type'], 'homework');
      expect(saved?['score'], 90.0);
      expect(tester.takeException(), isNull);
    }, () => client);
  });

  testWidgets('成绩趋势标明全部科目，选定科目后可以恢复全部', (tester) async {
    String? subject;
    await tester.pumpWidget(
      page(
        Scaffold(
          body: StatefulBuilder(
            builder: (context, setState) => GradeTrendCard(
              trend: const {},
              subjects: const ['数学'],
              subject: subject,
              rangeDays: null,
              onChanged: (value, _) => setState(() => subject = value),
            ),
          ),
        ),
      ),
    );
    expect(find.text('全部科目'), findsOneWidget);
    await tester.tap(find.text('全部科目'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('数学').last);
    await tester.pumpAndSettle();
    expect(subject, '数学');
    await tester.tap(find.text('数学'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('全部科目').last);
    await tester.pumpAndSettle();
    expect(subject, isNull);
    expect(find.text('全部科目'), findsOneWidget);
  });

  testWidgets('错误状态在低高度大字体下可滚动重试', (tester) async {
    tester.view.physicalSize = const Size(320, 350);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    var retried = false;
    await tester.pumpWidget(
      page(
        Scaffold(
          body: StudentPageState(
            icon: Icons.wifi_off_rounded,
            title: '暂时无法加载学习记录',
            description: '请检查网络连接后再试一次',
            onRetry: () => retried = true,
          ),
        ),
      ),
    );
    await tester.ensureVisible(find.text('重试'));
    await tester.tap(find.text('重试'));
    expect(retried, isTrue);
    expect(tester.takeException(), isNull);
  });
}
