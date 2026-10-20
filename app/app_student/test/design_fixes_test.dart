import 'dart:async';
import 'dart:convert';
import 'package:app_core/app_core.dart';
import 'package:app_student/screens/favorites_screen.dart';
import 'package:app_student/screens/grades_screen.dart';
import 'package:app_student/screens/my_reports_screen.dart';
import 'package:app_student/widgets/student_grade_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:app_student/screens/bind_screen.dart';
import 'package:app_student/screens/chat_screen.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gpt_markdown/gpt_markdown.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

http.Response response(Object data, [int status = 200]) => http.Response(
  jsonEncode(data),
  status,
  headers: {'content-type': 'application/json; charset=utf-8'},
);

void main() {
  testWidgets('成绩校验阻止无效请求，失败保留草稿，保存中不能重复提交', (tester) async {
    var requests = 0;
    final pending = Completer<void>();
    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) => Scaffold(
            body: TextButton(
              child: const Text('打开'),
              onPressed: () => showDialog<bool>(
                context: context,
                barrierDismissible: false,
                builder: (_) => StudentGradeDialog(
                  onSave: (body) async {
                    requests++;
                    expect(body['subject'], '数学');
                    expect(body['score'], 90.0);
                    if (requests == 1) throw ApiException(503, '暂时无法保存');
                    await pending.future;
                  },
                ),
              ),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('打开'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('保存'));
    await tester.pumpAndSettle();
    expect(requests, 0);
    await tester.enterText(find.byKey(const ValueKey('subject')), '数学');
    await tester.enterText(find.byKey(const ValueKey('score')), '101');
    await tester.tap(find.text('保存'));
    await tester.pumpAndSettle();
    expect(find.text('得分不能超过满分'), findsOneWidget);
    expect(requests, 0);
    await tester.enterText(find.byKey(const ValueKey('score')), '90');
    await tester.tap(find.text('保存'));
    await tester.pumpAndSettle();
    expect(find.text('暂时无法保存'), findsOneWidget);
    expect(find.text('数学'), findsOneWidget);
    expect(find.text('90'), findsOneWidget);
    expect(requests, 1);
    await tester.tap(find.text('保存'));
    await tester.pump();
    expect(
      tester.widget<FilledButton>(find.byType(FilledButton)).onPressed,
      isNull,
    );
    expect(
      tester
          .widget<TextFormField>(find.byKey(const ValueKey('subject')))
          .enabled,
      isFalse,
    );
    expect(requests, 2);
    pending.complete();
    await tester.pumpAndSettle();
    expect(find.byType(StudentGradeDialog), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('成绩默认最近有效科目，手选全部后刷新仍保留全部', (tester) async {
    final subjects = <String?>[];
    final client = MockClient((request) async {
      if (request.url.path.endsWith('/grade-trend')) {
        subjects.add(request.url.queryParameters['subject']);
        return response({});
      }
      if (request.url.path.endsWith('/grades')) {
        return response([
          {
            'id': 1,
            'subject': '数学',
            'exam_date': '2026-10-01',
            'score': 80,
            'max_score': 100,
            'deleted': false,
          },
          {
            'id': 2,
            'subject': '语文',
            'exam_date': '2026-10-10',
            'score': 90,
            'max_score': 100,
            'deleted': false,
          },
          {
            'id': 3,
            'subject': '英语',
            'exam_date': '2026-10-20',
            'score': 90,
            'max_score': 100,
            'deleted': true,
          },
        ]);
      }
      return response([]);
    });
    addTearDown(client.close);
    await http.runWithClient(() async {
      await tester.pumpWidget(const MaterialApp(home: GradesScreen()));
      await tester.pumpAndSettle();
      expect(subjects, ['语文']);
      final dropdown = find.byType(DropdownButton<String>).first;
      await tester.tap(dropdown);
      await tester.pumpAndSettle();
      await tester.tap(find.text('全部科目').last);
      await tester.pumpAndSettle();
      expect(subjects.last, isNull);
      unawaited(
        tester
            .state<RefreshIndicatorState>(find.byType(RefreshIndicator))
            .show(),
      );
      await tester.pumpAndSettle();
      expect(subjects.last, isNull);
      expect(find.text('暂无学业评估记录'), findsNothing);
    }, () => client);
  });

  testWidgets('举报按处理状态计数筛选，展开渲染公式，可返回来源', (tester) async {
    int? source;
    final client = MockClient(
      (_) async => response([
        {
          'id': 1,
          'status': 'open',
          'reason': '计算不准确',
          'content': r'答案是 $x^2$。',
          'created_at': '2026-10-20T08:00:00Z',
          'conversation_id': 42,
        },
        {
          'id': 2,
          'status': 'reviewed',
          'reason': '已核实',
          'reply': '感谢反馈',
          'content': '回复',
          'created_at': '2026-10-19T08:00:00Z',
        },
        {'id': 3, 'status': 'dismissed', 'reason': '已关闭', 'content': '回复'},
      ]),
    );
    addTearDown(client.close);
    await http.runWithClient(() async {
      await tester.pumpWidget(
        MaterialApp(
          home: Builder(
            builder: (context) => Scaffold(
              body: TextButton(
                child: const Text('打开'),
                onPressed: () async {
                  source = await Navigator.of(context).push<int>(
                    MaterialPageRoute(builder: (_) => const MyReportsScreen()),
                  );
                },
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('打开'));
      await tester.pumpAndSettle();
      expect(find.text('全部 (3)'), findsOneWidget);
      await tester.tap(find.text('已处理 (2)'));
      await tester.pumpAndSettle();
      expect(find.text('原因：计算不准确'), findsNothing);
      expect(find.text('工作人员回复：感谢反馈'), findsOneWidget);
      await tester.tap(find.text('处理中 (1)'));
      await tester.pumpAndSettle();
      expect(find.text('原因：已核实'), findsNothing);
      await tester.tap(find.text('展开全文'));
      await tester.pumpAndSettle();
      expect(find.byType(GptMarkdown), findsOneWidget);
      await tester.tap(find.text('查看来源对话'));
      await tester.pumpAndSettle();
      expect(source, 42);
      expect(tester.takeException(), isNull);
    }, () => client);
  });

  testWidgets('收藏可搜索、撤销取消，并使用消息 ID 恢复', (tester) async {
    var removed = false;
    int? restored;
    final client = MockClient((request) async {
      if (request.method == 'DELETE') {
        removed = true;
        return response({});
      }
      if (request.method == 'POST') {
        restored = jsonDecode(request.body)['message_id'] as int;
        removed = false;
        return response({'id': 11});
      }
      return response([
        if (!removed)
          {
            'id': restored == null ? 7 : 11,
            'message_id': 99,
            'conversation_id': 42,
            'teacher_name': '数学老师',
            'content': '分数练习',
            'created_at': '2026-10-20T08:00:00Z',
          },
        {'id': 8, 'content': '语文练习'},
      ]);
    });
    addTearDown(client.close);
    await http.runWithClient(() async {
      await tester.pumpWidget(const MaterialApp(home: FavoritesScreen()));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField), '分数');
      await tester.pumpAndSettle();
      expect(find.text('语文练习'), findsNothing);
      await tester.tap(find.text('分数练习'));
      await tester.pumpAndSettle();
      expect(find.text('查看来源对话'), findsOneWidget);
      await tester.tap(find.text('取消收藏'));
      await tester.pumpAndSettle();
      expect(find.text('分数练习'), findsNothing);
      await tester.tap(find.text('撤销'));
      await tester.pumpAndSettle();
      expect(restored, 99);
      expect(find.text('分数练习'), findsOneWidget);
      expect(find.text('语文练习'), findsNothing);
    }, () => client);
  });
  testWidgets('绑定码粘贴校验完整内容，手动输入限制八位', (tester) async {
    var clipboard = ' a3f9c2b1 ';
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
      SystemChannels.platform,
      (call) async {
        if (call.method == 'Clipboard.getData') return {'text': clipboard};
        return null;
      },
    );
    addTearDown(
      () => tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
        SystemChannels.platform,
        null,
      ),
    );
    await tester.pumpWidget(const MaterialApp(home: BindScreen()));
    await tester.tap(find.byTooltip('粘贴绑定码'));
    await tester.pumpAndSettle();
    expect(
      tester.widget<TextField>(find.byType(TextField)).controller!.text,
      'A3F9C2B1',
    );
    clipboard = 'https://example.com';
    await tester.tap(find.byTooltip('粘贴绑定码'));
    await tester.pumpAndSettle();
    expect(find.text('请输入有效的 8 位绑定码'), findsOneWidget);
    expect(
      tester.widget<TextField>(find.byType(TextField)).controller!.text,
      'A3F9C2B1',
    );
    await tester.enterText(find.byType(TextField), '');
    await tester.enterText(find.byType(TextField), '123456789');
    expect(
      tester.widget<TextField>(find.byType(TextField)).controller!.text,
      '12345678',
    );
  });

  testWidgets('从收藏返回来源会话不弹出聊天页', (tester) async {
    String? opened;
    final client = MockClient((request) async {
      final path = request.url.path;
      if (path.endsWith('/teachers')) {
        return response([
          {
            'teacher_id': 1,
            'name': '数学老师',
            'selected': true,
            'access': 'available',
          },
        ]);
      }
      if (path.endsWith('/favorites')) {
        return response([
          {'id': 7, 'message_id': 99, 'conversation_id': 42, 'content': '分数练习'},
        ]);
      }
      if (path.endsWith('/conversations')) {
        opened = request.url.queryParameters['conversation_id'];
        return response([
          {'id': 99, 'role': 'assistant', 'content': '来源讲解'},
        ]);
      }
      if (path.endsWith('/sessions')) {
        return response([
          {
            'conversation_id': 42,
            'teacher_name': '数学老师',
            'title': '分数',
            'message_count': 1,
          },
        ]);
      }
      return response(<String, dynamic>{});
    });
    addTearDown(client.close);
    await http.runWithClient(() async {
      await tester.pumpWidget(const MaterialApp(home: ChatScreen()));
      await tester.pumpAndSettle();
      await tester.tap(find.byTooltip('聊天记录'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('我的收藏'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('分数练习'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('查看来源对话'));
      await tester.pumpAndSettle();
      expect(opened, '42');
      expect(find.byType(ChatScreen), findsOneWidget);
      expect(find.byType(FavoritesScreen), findsNothing);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox());
      await tester.pump();
    }, () => client);
  });
}
