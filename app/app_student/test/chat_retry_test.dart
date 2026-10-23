import 'dart:convert';
import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:app_core/app_core.dart';
import 'package:app_student/screens/chat_screen.dart';
import 'package:app_student/widgets/message_bubble.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  testWidgets('测试重试收到409时的表现', (tester) async {
    SharedPreferences.setMockInitialValues({'token': 'test_token'});
    await Api.I.loadToken();

    var requestCount = 0;
    var getConversationsCalled = false;
    final client = MockClient.streaming((request, bodyStream) async {
      print('HTTP Request: ${request.method} ${request.url.path}');
      if (request.url.path.endsWith('/availability')) {
        return http.StreamedResponse(
          Stream.value(utf8.encode(jsonEncode({'resting': false}))),
          200,
          headers: {'content-type': 'application/json'},
        );
      }
      if (request.url.path.endsWith('/latest')) {
        return http.StreamedResponse(
          Stream.value(utf8.encode(jsonEncode({'conversation_id': 100, 'messages': []}))),
          200,
          headers: {'content-type': 'application/json'},
        );
      }
      if (request.url.path.endsWith('/teachers') || request.url.path.endsWith('/sessions')) {
        return http.StreamedResponse(
          Stream.value(utf8.encode(jsonEncode([]))),
          200,
          headers: {'content-type': 'application/json'},
        );
      }
      if (request.url.path.endsWith('/conversations')) {
        getConversationsCalled = true;
        // 模拟返回服务端已经生成的回复
        return http.StreamedResponse(
          Stream.value(utf8.encode(jsonEncode([
            {
              'id': 200,
              'role': 'user',
              'content': '请问什么是光合作用？',
              'fence_action': 'pending',
              'content_blocks': [],
            }
          ]))),
          200,
          headers: {'content-type': 'application/json'},
        );
      }
      if (request.url.path.endsWith('/chat/stream')) {
        requestCount++;
        if (requestCount == 1) {
          // 第一次请求：发送了 meta 之后网络错误中断
          final controller = StreamController<List<int>>();
          controller.add(utf8.encode('event: meta\ndata: {"conversation_id": 100, "user_message_id": 200, "fence_action": "allow", "category": "study"}\n\n'));
          controller.addError(http.ClientException('Network connection lost'));
          controller.close();
          return http.StreamedResponse(
            controller.stream,
            200,
            headers: {'content-type': 'text/event-stream'},
          );
        } else if (requestCount == 2) {
          // 第二次请求（重试）：服务端返回 409
          return http.StreamedResponse(
            Stream.value(utf8.encode(jsonEncode({'detail': 'conversation has newer messages'}))),
            409,
            headers: {'content-type': 'application/json'},
          );
        }
      }
      return http.StreamedResponse(
        Stream.value(utf8.encode(jsonEncode({}))),
        200,
        headers: {'content-type': 'application/json'},
      );
    });

    await http.runWithClient(() async {
      await tester.pumpWidget(const MaterialApp(home: ChatScreen()));
      await tester.pumpAndSettle();

      await tester.enterText(find.byType(TextField), '请问什么是光合作用？');
      await tester.pump();
      await tester.tap(find.byWidgetPredicate((w) => w is IconButton && w.tooltip == '发送问题'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 200));
      await tester.pumpAndSettle();

      expect(find.text('⚠️ 老师回复失败，请检查网络后重试'), findsOneWidget);
      expect(find.text('重试回复'), findsOneWidget);

      // 点击重试回复
      print('=== Tapping retry ===');
      await tester.tap(find.text('重试回复'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 200));
      await tester.pump(const Duration(milliseconds: 500));
      await tester.pumpAndSettle();

      print('=== After 409 refresh ===');
      print('getConversationsCalled: $getConversationsCalled');
      final bubbles = tester.widgetList<MessageBubble>(find.byType(MessageBubble));
      for (final b in bubbles) {
        print('Bubble: role=${b.bubble.role}, text=${b.bubble.text}, failed=${b.bubble.failed}');
      }

      // 验证修复：409 刷新后，由于该消息尚未完成回复，界面上必须保留重试气泡和“重试回复”按钮，气泡不能消失
      expect(find.text('⚠️ 老师回复失败，请重试'), findsOneWidget);
      expect(find.text('重试回复'), findsOneWidget);
      expect(find.text('上一条回复未完成，请重试'), findsOneWidget);
    }, () => client);
  });

  testWidgets('测试重试成功时正常展示老师回复结果', (tester) async {
    SharedPreferences.setMockInitialValues({'token': 'test_token'});
    await Api.I.loadToken();

    var requestCount = 0;
    final client = MockClient.streaming((request, bodyStream) async {
      if (request.url.path.endsWith('/availability')) {
        return http.StreamedResponse(
          Stream.value(utf8.encode(jsonEncode({'resting': false}))),
          200,
          headers: {'content-type': 'application/json'},
        );
      }
      if (request.url.path.endsWith('/latest')) {
        return http.StreamedResponse(
          Stream.value(utf8.encode(jsonEncode({'conversation_id': 100, 'messages': []}))),
          200,
          headers: {'content-type': 'application/json'},
        );
      }
      if (request.url.path.endsWith('/teachers') || request.url.path.endsWith('/sessions')) {
        return http.StreamedResponse(
          Stream.value(utf8.encode(jsonEncode([]))),
          200,
          headers: {'content-type': 'application/json'},
        );
      }
      if (request.url.path.endsWith('/chat/stream')) {
        requestCount++;
        if (requestCount == 1) {
          // 第一次：断开报错
          final controller = StreamController<List<int>>();
          controller.add(utf8.encode('event: meta\ndata: {"conversation_id": 100, "user_message_id": 200, "fence_action": "allow", "category": "study"}\n\n'));
          controller.addError(http.ClientException('Network error'));
          controller.close();
          return http.StreamedResponse(
            controller.stream,
            200,
            headers: {'content-type': 'text/event-stream'},
          );
        } else if (requestCount == 2) {
          // 第二次（重试）：成功返回回答
          final sseData = 'event: meta\ndata: {"conversation_id": 100, "user_message_id": 200, "fence_action": "allow", "category": "study"}\n\n'
              'event: delta\ndata: {"text": "光合作用是绿色植物利用太阳光进行能量转化的过程。"}\n\n'
              'event: done\ndata: {"message_id": 201, "tokens_in": 10, "tokens_out": 20}\n\n';
          return http.StreamedResponse(
            Stream.value(utf8.encode(sseData)),
            200,
            headers: {'content-type': 'text/event-stream'},
          );
        }
      }
      return http.StreamedResponse(
        Stream.value(utf8.encode(jsonEncode({}))),
        200,
        headers: {'content-type': 'application/json'},
      );
    });

    await http.runWithClient(() async {
      await tester.pumpWidget(const MaterialApp(home: ChatScreen()));
      await tester.pumpAndSettle();

      await tester.enterText(find.byType(TextField), '请问什么是光合作用？');
      await tester.pump();
      await tester.tap(find.byWidgetPredicate((w) => w is IconButton && w.tooltip == '发送问题'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 200));
      await tester.pumpAndSettle();

      expect(find.text('⚠️ 老师回复失败，请检查网络后重试'), findsOneWidget);
      expect(find.text('重试回复'), findsOneWidget);

      // 点击重试回复
      await tester.tap(find.text('重试回复'));
      await tester.pump();
      // 等待打字机显现定时器
      for (var i = 0; i < 30; i++) {
        await tester.pump(const Duration(milliseconds: 50));
      }
      await tester.pumpAndSettle();

      // 验证重试成功显示结果，并且重试按钮和失败提示已消失
      expect(find.textContaining('光合作用是绿色植物'), findsOneWidget);
      expect(find.text('重试回复'), findsNothing);
      expect(find.text('⚠️ 老师回复失败，请检查网络后重试'), findsNothing);
    }, () => client);
  });
}
