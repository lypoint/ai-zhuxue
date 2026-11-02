import 'dart:convert';
import 'dart:io';
import 'package:app_core/app_core.dart';
import 'package:app_student/screens/chat_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  testWidgets(
    'offline history still restores a draft; failed submission keeps it',
    (tester) async {
      final directory = (await tester.runAsync(
        () => Directory.systemTemp.createTemp('draft-widget-'),
      ))!;
      tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
        const MethodChannel('plugins.flutter.io/path_provider'),
        (call) async => directory.path,
      );
      final claims = base64Url.encode(
        utf8.encode(
          jsonEncode({'role': 'student', 'family_id': 3, 'sub': '7'}),
        ),
      );
      SharedPreferences.setMockInitialValues({
        'token': 'header.$claims.signature',
      });
      await Api.I.loadToken();
      final owner = Api.I.studentDraftOwner!;
      await tester.runAsync(
        () => StudentDrafts(owner).save({
          'text': 'my unsent question',
          'conversation_id': null,
          'images': [],
        }),
      );
      var submissions = 0;
      final client = MockClient((request) async {
        if (request.url.path == '/chat/stream') submissions++;
        if (request.url.path == '/chat/latest' ||
            request.url.path == '/chat/stream') {
          return http.Response('{"detail":"offline"}', 503);
        }
        return http.Response(
          request.url.path == '/chat/teachers' ||
                  request.url.path == '/chat/sessions'
              ? '[]'
              : '{}',
          200,
        );
      });
      await http.runWithClient(() async {
        await tester.runAsync(() async {
          await tester.pumpWidget(const MaterialApp(home: ChatScreen()));
          await Future<void>.delayed(const Duration(milliseconds: 100));
        });
        await tester.pumpAndSettle();
        expect(
          tester.widget<TextField>(find.byType(TextField)).controller!.text,
          'my unsent question',
        );
        ScaffoldMessenger.of(
          tester.element(find.byType(TextField)),
        ).hideCurrentSnackBar();
        await tester.pumpAndSettle();
        await tester.ensureVisible(find.byIcon(Icons.arrow_upward));
        await tester.runAsync(() async {
          await tester.tap(find.byIcon(Icons.arrow_upward));
          await Future<void>.delayed(const Duration(milliseconds: 500));
        });
        await tester.pumpAndSettle();
        expect(submissions, 1);
        await tester.runAsync(() async {
          expect(
            (await StudentDrafts(owner).load())!['text'],
            'my unsent question',
          );
        });
        await tester.runAsync(() => tester.pumpWidget(const SizedBox.shrink()));
      }, () => client);
      await tester.runAsync(() async {
        await StudentDrafts.clear();
        await directory.delete(recursive: true);
      });
      tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
        const MethodChannel('plugins.flutter.io/path_provider'),
        null,
      );
      Api.I.clearToken();
    },
  );
}
