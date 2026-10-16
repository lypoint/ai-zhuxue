import 'package:app_core/app_core.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  tearDown(() {
    Telemetry.events = null;
    Telemetry.errors = null;
  });

  test('domestic default performs no collection', () {
    expect(Telemetry.events, isNull);
    expect(Telemetry.errors, isNull);
    Telemetry.event(AppEvent.appReady);
    Telemetry.error(StateError('secret'), StackTrace.current);
  });

  test('errors omit messages and arbitrary stack text', () async {
    String? type;
    String? frames;
    Telemetry.errors = (value, stack, fatal) async {
      type = value;
      frames = stack.toString();
    };
    Telemetry.error(
      StateError('phone=13800000000 token=secret'),
      StackTrace.fromString(
        '#0      Api.request (package:app_core/src/api.dart:12:3)\n'
        'https://server/private?token=secret\nchat text',
      ),
    );
    await Future<void>.delayed(Duration.zero);
    expect(type, 'StateError');
    expect(frames, '#0      Api.request (package:app_core/src/api.dart:12:3)');
  });

  test(
    'sink failures do not break requests; no payload enters events',
    () async {
      final events = <AppEvent>[];
      Telemetry.events = (event, result, status) async {
        events.add(event);
        throw StateError('offline');
      };
      await http.runWithClient(
        () => Api.I.verifyStorePurchase('googleplay', 'secret-purchase-token'),
        () => MockClient((request) async => http.Response('{}', 200)),
      );
      await Future<void>.delayed(Duration.zero);
      expect(events, [AppEvent.purchaseVerify]);
    },
  );

  test(
    'API failures preserve caller error and report only safe status',
    () async {
      EventResult? result;
      int? status;
      String? type;
      Telemetry.events = (event, value, code) async {
        result = value;
        status = code;
      };
      Telemetry.errors = (value, stack, fatal) async {
        type = value;
      };
      await http.runWithClient(
        () async {
          await expectLater(
            Api.I.verifyStorePurchase('googleplay', 'secret'),
            throwsA(isA<ApiException>()),
          );
        },
        () => MockClient(
          (request) async =>
              http.Response('{"detail":"sensitive server text"}', 503),
        ),
      );
      await Future<void>.delayed(Duration.zero);
      expect(result, EventResult.failure);
      expect(status, 503);
      expect(type, 'ApiException');
    },
  );
  test('expected client errors are events without crash reports', () async {
    var reported = false;
    Telemetry.errors = (type, stack, fatal) async {
      reported = true;
    };
    await http.runWithClient(
      () async {
        await expectLater(
          Api.I.verifyStorePurchase('googleplay', 'private'),
          throwsA(isA<ApiException>()),
        );
      },
      () => MockClient((_) async => http.Response('{"detail":"invalid"}', 400)),
    );
    await Future<void>.delayed(Duration.zero);
    expect(reported, isFalse);
  });

  test('stream events contain only the fixed operation result', () async {
    final events = <AppEvent>[];
    Telemetry.events = (event, result, status) async {
      events.add(event);
      expect(result, EventResult.success);
      expect(status, isNull);
    };
    await http.runWithClient(
      () => Api.I.sendChatStream(null, 'private lesson text'),
      () => MockClient(
        (_) async => http.Response('event: done\ndata: {}\n\n', 200),
      ),
    );
    await Future<void>.delayed(Duration.zero);
    expect(events, [AppEvent.chatSend]);
  });
}
