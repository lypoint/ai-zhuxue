import 'package:app_student/student_app.dart';
import 'package:app_student/screens/chat_screen.dart';
import 'package:app_student/screens/bind_screen.dart';
import 'package:app_student/models/bubble.dart';
import 'package:app_student/widgets/message_bubble.dart';
import 'package:app_student/widgets/chat_drawer.dart';
import 'package:app_core/app_core.dart';
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

  testWidgets('发送和接收消息都可以点击复制按钮', (tester) async {
    final copied = <String>[];
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Column(
            children: [
              for (final role in ['user', 'assistant'])
                MessageBubble(
                  bubble: Bubble(role, '消息-$role'),
                  onLongPress: () {},
                  onCopy: () => copied.add(role),
                ),
            ],
          ),
        ),
      ),
    );

    expect(find.text('复制'), findsNWidgets(2));
    await tester.tap(find.text('复制').first);
    await tester.tap(find.text('复制').last);
    expect(copied, ['user', 'assistant']);
  });

  testWidgets('等待 AI 回复时显示进度提示', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: MessageBubble(
            bubble: Bubble('assistant', ''),
            onLongPress: () {},
            onCopy: () {},
            isLoading: true,
          ),
        ),
      ),
    );
    expect(find.text('正在回答…'), findsOneWidget);
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
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
