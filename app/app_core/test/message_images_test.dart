import 'dart:convert';
import 'package:app_core/app_core.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  testWidgets('text-only historical messages need no image request', (
    tester,
  ) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(body: MessageImages(blocks: [])),
      ),
    );
    expect(find.byType(Image), findsNothing);
  });

  testWidgets('private image authorization failures offer a retry', (
    tester,
  ) async {
    var requests = 0;
    await http.runWithClient(
      () async {
        await tester.pumpWidget(
          const MaterialApp(
            home: Scaffold(
              body: MessageImages(
                blocks: [
                  {
                    'type': 'image',
                    'asset_id': 'private-asset',
                    'caption': 'question',
                  },
                ],
              ),
            ),
          ),
        );
        await tester.pumpAndSettle();
        expect(
          find.byWidgetPredicate((widget) => widget is TextButton),
          findsOneWidget,
        );
        await tester.tap(
          find.byWidgetPredicate((widget) => widget is TextButton),
        );
        await tester.pumpAndSettle();
        expect(requests, 2);
      },
      () => MockClient((request) async {
        requests++;
        expect(request.url.path, '/media/private-asset');
        return http.Response('{"detail":"not available"}', 404);
      }),
    );
  });

  test(
    'image requests send asset IDs and preserve stream reservation metadata',
    () async {
      final bodies = <Map<String, dynamic>>[];
      Map<String, dynamic>? meta;
      await http.runWithClient(
        () async {
          await Api.I.sendChat(12, '', assetIds: ['asset-id']);
          await expectLater(
            Api.I.sendChatStream(
              12,
              '',
              assetIds: ['asset-id'],
              onMeta: (value) => meta = value,
            ),
            throwsA(isA<ApiException>()),
          );
        },
        () => MockClient((request) async {
          bodies.add(jsonDecode(request.body) as Map<String, dynamic>);
          if (request.url.path.endsWith('/stream')) {
            expect(request.url.query, isEmpty);
            return http.Response(
              '{"detail":"retry"}',
              503,
              headers: {'x-user-message-id': '21', 'x-conversation-id': '12'},
            );
          }
          return http.Response('{}', 200);
        }),
      );
      expect(
        bodies.every((body) => body['asset_ids'][0] == 'asset-id'),
        isTrue,
      );
      expect(meta?['user_message_id'], 21);
      expect(meta?['conversation_id'], 12);
    },
  );
}
