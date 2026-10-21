import 'dart:convert';

import 'package:app_student/screens/chat_screen.dart';
import 'package:app_student/widgets/message_bubble.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  testWidgets('启动恢复、切换及重新进入长会话都停在最新消息', (tester) async {
    List<Map<String, dynamic>> messages(int id) => [
      for (var i = 0; i < 60; i++)
        {
          'id': id * 100 + i,
          'role': i.isEven ? 'user' : 'assistant',
          'content': i == 59
              ? '会话$id 最新消息'
              : List.filled(i % 7 + 1, '会话$id 第$i条消息，长度不同的历史内容。').join('\n'),
        },
    ];
    final opened = <int>[];
    final client = MockClient((request) async {
      if (request.url.path == '/chat/conversations') {
        opened.add(int.parse(request.url.queryParameters['conversation_id']!));
      }
      final data = switch (request.url.path) {
        '/chat/latest' => {'conversation_id': 1, 'messages': messages(1)},
        '/chat/conversations' => messages(
          int.parse(request.url.queryParameters['conversation_id']!),
        ),
        '/chat/sessions' => [
          for (var id = 1; id <= 2; id++)
            {
              'conversation_id': id,
              'title': '历史会话$id',
              'message_count': 60,
              'last_time': '2026-10-21T09:00:00Z',
            },
        ],
        '/chat/teachers' => [],
        '/chat/availability' => {'resting': false},
        _ => <String, dynamic>{},
      };
      return http.Response(
        jsonEncode(data),
        200,
        headers: {'content-type': 'application/json; charset=utf-8'},
      );
    });
    addTearDown(client.close);
    await http.runWithClient(() async {
      await tester.pumpWidget(const MaterialApp(home: ChatScreen()));
      await tester.pumpAndSettle();
      final list = find.byWidgetPredicate(
        (widget) => widget is ListView && widget.controller != null,
      );
      ScrollPosition position() =>
          tester.widget<ListView>(list).controller!.position;
      void expectLatest(int id) {
        expect(position().extentBefore, 0);
        final latest = find.byWidgetPredicate(
          (widget) =>
              widget is MessageBubble && widget.bubble.text == '会话$id 最新消息',
        );
        expect(latest, findsOneWidget);
        final bounds = tester.getRect(list);
        final bottom = tester.getBottomLeft(latest).dy;
        expect(bottom, lessThanOrEqualTo(bounds.bottom));
        expect(bottom, greaterThan(bounds.top));
      }

      expectLatest(1);
      for (final id in [2, 1, 1]) {
        position().jumpTo(600);
        await tester.pumpAndSettle();
        expect(position().extentBefore, greaterThan(0));
        await tester.tap(find.byTooltip('聊天记录'));
        await tester.pumpAndSettle();
        await tester.scrollUntilVisible(
          find.text('历史会话$id'),
          250,
          scrollable: find
              .descendant(
                of: find.byType(Drawer),
                matching: find.byType(Scrollable),
              )
              .first,
        );
        await tester.pumpAndSettle();
        await tester.tap(find.text('历史会话$id'));
        await tester.pumpAndSettle();
        expect(opened.lastOrNull, id);
        expectLatest(id);
      }
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox());
    }, () => client);
  });
}
