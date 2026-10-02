import 'package:app_student/student_app.dart';
import 'package:app_student/screens/chat_screen.dart';
import 'package:app_student/screens/bind_screen.dart';
import 'package:app_student/models/bubble.dart';
import 'package:app_student/widgets/message_bubble.dart';
import 'package:app_student/widgets/chat_drawer.dart';
import 'package:app_core/app_core.dart';
import 'package:gpt_markdown/gpt_markdown.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('学生端无 token 时显示绑定页', (tester) async {
    SharedPreferences.setMockInitialValues({});
    Api.I.clearToken();
    await tester.pumpWidget(const StudentApp());
    expect(find.text('输入家长端绑定码'), findsOneWidget);
    expect(find.text('绑定并开始学习'), findsOneWidget);
    expect(find.text('扫描家长端二维码'), findsOneWidget);
  });

  test('扫码内容只接受家长端的 8 位绑定码', () {
    expect(normalizeBindCode(' a3f9c2b1 '), 'A3F9C2B1');
    expect(normalizeBindCode('https://example.com'), isNull);
    expect(normalizeBindCode('1234567'), isNull);
  });

  testWidgets('聊天页空态展示欢迎语与输入框', (tester) async {
    SharedPreferences.setMockInitialValues({'token': 'fake'});
    await Api.I.loadToken();
    await tester.pumpWidget(const MaterialApp(home: ChatScreen()));
    expect(find.text('你好！今天想学什么？'), findsOneWidget);
    expect(find.text('正在恢复上次对话…'), findsOneWidget);
    expect(find.byIcon(Icons.arrow_upward), findsOneWidget);
    expect(find.byTooltip('选择老师'), findsOneWidget);
    expect(find.byIcon(Icons.school_outlined), findsNothing);
    expect(
      find.ancestor(of: find.text('AI 学习助手'), matching: find.byType(InkWell)),
      findsOneWidget,
    );
    expect(
      find.ancestor(
        of: find.byType(CircleAvatar).first,
        matching: find.byType(InkWell),
      ),
      findsOneWidget,
    );
  });

  testWidgets('孩子开始提问后不再显示恢复提示', (tester) async {
    SharedPreferences.setMockInitialValues({'token': 'fake'});
    await Api.I.loadToken();
    await tester.pumpWidget(const MaterialApp(home: ChatScreen()));
    await tester.enterText(find.byType(TextField), '你好');
    await tester.tap(find.byIcon(Icons.arrow_upward));
    await tester.pump();
    expect(find.text('正在恢复上次对话…'), findsNothing);
    expect(find.text('你好'), findsOneWidget);
  });

  testWidgets('只有老师消息可以打开操作菜单', (tester) async {
    final opened = <String>[];
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Column(
            children: [
              for (final role in ['user', 'assistant'])
                MessageBubble(
                  bubble: Bubble(role, '消息-$role'),
                  onLongPress: () => opened.add(role),
                ),
            ],
          ),
        ),
      ),
    );

    expect(find.text('复制'), findsNothing);
    expect(find.byTooltip('消息操作'), findsOneWidget);
    await tester.longPress(find.text('消息-user'));
    expect(opened, isEmpty);
    await tester.tap(find.byTooltip('消息操作'));
    await tester.longPress(find.byType(GptMarkdown).first);
    expect(opened, ['assistant', 'assistant']);
  });

  testWidgets('等待 AI 回复时显示进度提示', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: MessageBubble(
            bubble: Bubble('assistant', ''),
            onLongPress: () {},
            isLoading: true,
          ),
        ),
      ),
    );
    expect(find.text('正在回答…'), findsOneWidget);
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
  });

  testWidgets('老师回复失败时显示可点击的重试入口', (tester) async {
    var retries = 0;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: MessageBubble(
            bubble: Bubble('assistant', '⚠️ 老师回复失败，请重试', failed: true),
            onLongPress: () {},
            onRetry: () => retries++,
          ),
        ),
      ),
    );
    expect(find.text('重试回复'), findsOneWidget);
    expect(find.byTooltip('消息操作'), findsNothing);
    await tester.tap(find.text('重试回复'));
    expect(retries, 1);
  });

  testWidgets('老师卡片保持参考聊天页间距', (tester) async {
    tester.view.physicalSize = const Size(1125, 2436);
    tester.view.devicePixelRatio = 3;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: MessageBubble(
            bubble: Bubble('assistant', '一段讲解'),
            onLongPress: () {},
          ),
        ),
      ),
    );
    final card = tester.getRect(
      find
          .ancestor(
            of: find.byType(GptMarkdown),
            matching: find.byType(Container),
          )
          .first,
    );
    expect(card.left, 16);
    expect(card.right - 12, 351);
    expect(find.byTooltip('消息操作'), findsOneWidget);
    final menu = tester.getRect(find.byTooltip('消息操作'));
    final icon = tester.getRect(find.byIcon(Icons.more_horiz));
    expect(icon.left, greaterThan(card.left));
    expect(icon.right, lessThanOrEqualTo(card.right - 12));
    expect(menu.right, lessThanOrEqualTo(card.right - 12));
    expect(menu.top - card.top, lessThanOrEqualTo(8));
    expect(
      tester.getRect(find.byType(GptMarkdown)).top - card.top,
      lessThan(20),
    );
  });

  testWidgets('会话记录加载失败后可以重试', (tester) async {
    var retried = false;
    final scaffoldKey = GlobalKey<ScaffoldState>();
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          key: scaffoldKey,
          drawer: ChatDrawer(
            sessions: null,
            sessionsError: '会话记录加载失败，请重试',
            filteredSessions: const [],
            search: '',
            currentConversationId: null,
            onNewChat: () {},
            onSearchChanged: (_) {},
            onOpenStats: () {},
            onOpenFavorites: () {},
            onOpenReports: () {},
            onOpenGrades: () {},
            onLogout: () {},
            onOpenSession: (_) {},
            onSessionMenu: (_) {},
            onRetrySessions: () => retried = true,
          ),
          body: const SizedBox(),
        ),
      ),
    );
    scaffoldKey.currentState!.openDrawer();
    await tester.pumpAndSettle();
    expect(find.text('会话记录加载失败，请重试'), findsOneWidget);
    await tester.tap(find.text('重试'));
    expect(retried, isTrue);
  });

  testWidgets('学生退出登录前会确认并说明重新绑定', (tester) async {
    SharedPreferences.setMockInitialValues({'token': 'fake'});
    await Api.I.loadToken();
    await tester.pumpWidget(const MaterialApp(home: ChatScreen()));
    await tester.tap(find.byTooltip('聊天记录'));
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));
    await tester.tap(find.text('退出登录'));
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));
    expect(find.text('退出登录？'), findsOneWidget);
    expect(find.textContaining('重新生成绑定码'), findsOneWidget);
    await tester.tap(find.text('取消'));
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));
    expect(find.text('退出登录？'), findsNothing);

    await tester.tap(find.byTooltip('聊天记录'));
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));
    await tester.tap(find.text('退出登录'));
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));
    await tester.tap(find.text('退出'));
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));
    expect(find.byType(BindScreen), findsOneWidget);
  });
}
