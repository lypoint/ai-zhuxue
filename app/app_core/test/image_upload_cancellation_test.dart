import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:app_core/app_core.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

class TrackingClient extends MockClient {
  TrackingClient(super.handler);
  bool closed = false;

  @override
  void close() => closed = true;
}

http.Response response(Object body) => http.Response(
  jsonEncode(body),
  200,
  headers: {'content-type': 'application/json'},
);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  for (final stage in ['prepare', 'transfer', 'complete']) {
    test('cancel during $stage closes transport and stops upload', () async {
      final cancellation = Completer<void>();
      final reached = Completer<void>();
      final pending = Completer<void>();
      final requests = <String>[];
      final client = TrackingClient((request) async {
        final current = request.url.path.endsWith('/media/uploads')
            ? 'prepare'
            : request.url.host == 'upload.example.com'
            ? 'transfer'
            : 'complete';
        requests.add(current);
        if (current == stage) {
          reached.complete();
          await pending.future;
        }
        return response(switch (current) {
          'prepare' => {
            'max_bytes': 10000,
            'upload_url': 'https://upload.example.com',
            'key': 'key',
            'token': 'token',
            'asset_id': 'asset',
          },
          'transfer' => {},
          _ => {'type': 'image', 'asset_id': 'asset'},
        });
      });
      await http.runWithClient(() async {
        final upload = Api.I.uploadChatImage(
          Uint8List.fromList([1, 2, 3]),
          cancelled: cancellation.future,
        );
        final result = expectLater(
          upload,
          throwsA(isA<http.ClientException>()),
        );
        await reached.future;
        cancellation.complete();
        await Future<void>.delayed(Duration.zero);
        expect(client.closed, isTrue);
        pending.complete();
        await result;
        final expected = ['prepare', 'transfer', 'complete'];
        expect(requests, expected.take(expected.indexOf(stage) + 1).toList());
      }, () => client);
    });
  }
}
