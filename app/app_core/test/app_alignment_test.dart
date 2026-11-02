import 'dart:convert';
import 'dart:io';
import 'package:app_core/app_core.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  tearDown(() => FamilyTime.zone = null);
  test('legacy unset zones follow the configured server offset', () {
    FamilyTime.configure({
      'timezone': null,
      'legacy_timezone_offset_hours': -5,
    });
    expect(displayDate('2026-01-01T02:00:00Z'), '2025-12-31 21:00');
    FamilyTime.configure({});
  });
  test('family dates follow DST and preserve date-only school records', () {
    FamilyTime.zone = 'America/New_York';
    expect(displayDate('2026-03-08T06:30:00Z'), '2026-03-08 01:30');
    expect(displayDate('2026-03-08T07:30:00'), '2026-03-08 03:30');
    expect(displayDate('2026-11-01T05:30:00Z'), '2026-11-01 01:30');
    expect(displayDate('2026-11-01T06:30:00Z'), '2026-11-01 01:30');
    expect(displayDate('2026-03-08'), '2026-03-08');
  });
  test(
    'child settings and notification pagination use scoped API parameters',
    () async {
      await http.runWithClient(
        () async {
          await Api.I.updateStudentLearningSettings(42, {
            'daily_minutes_cap': 25,
          });
          await Api.I.notifications(page: 3, size: 30, unreadOnly: true);
          await Api.I.updateFamilyTimezone('Asia/Tokyo');
          expect(FamilyTime.zone, 'Asia/Tokyo');
        },
        () => MockClient((request) async {
          if (request.url.path.endsWith('learning-settings')) {
            expect(request.url.path, '/parent/students/42/learning-settings');
            expect(jsonDecode(request.body), {'daily_minutes_cap': 25});
          } else if (request.url.path.endsWith('notifications')) {
            expect(request.url.queryParameters, {
              'page': '3',
              'size': '30',
              'unread_only': 'true',
            });
          }
          return http.Response('{}', 200);
        }),
      );
    },
  );
  group('private student drafts', () {
    late Directory directory;
    setUp(() async {
      directory = await Directory.systemTemp.createTemp('student-draft-test-');
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(
            const MethodChannel('plugins.flutter.io/path_provider'),
            (call) async => directory.path,
          );
    });
    tearDown(() async {
      await StudentDrafts.clear();
      await directory.delete(recursive: true);
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(
            const MethodChannel('plugins.flutter.io/path_provider'),
            null,
          );
    });
    test('text and image bytes survive restart, isolated by account', () async {
      final draft = {
        'text': 'geometry',
        'conversation_id': 7,
        'images': [
          base64Encode([1, 2, 3]),
        ],
      };
      await StudentDrafts('family:student1').save(draft);
      expect(
        (await StudentDrafts('family:student1').load())!['images'],
        draft['images'],
      );
      expect(await StudentDrafts('family:student2').load(), isNull);
    });
    test(
      'logout invalidates writes already queued by the old screen',
      () async {
        final store = StudentDrafts('student1');
        final write = store.save({'text': 'private', 'images': []});
        await StudentDrafts.clear();
        await write;
        await store.save({'text': 'late write', 'images': []});
        expect(await StudentDrafts('student1').load(), isNull);
      },
    );
    test('expired and corrupt drafts are discarded', () async {
      final file = File('${directory.path}/student-draft.json');
      await file.writeAsString(
        jsonEncode({
          'owner': 'student1',
          'saved_at': '2020-01-01',
          'text': 'old',
          'images': [],
        }),
      );
      expect(await StudentDrafts('student1').load(), isNull);
      await file.writeAsString('{broken');
      expect(await StudentDrafts('student1').load(), isNull);
    });
  });
}
