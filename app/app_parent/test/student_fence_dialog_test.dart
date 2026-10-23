import 'dart:convert';
import 'package:app_core/app_core.dart';
import 'package:app_parent/widgets/student_fence_dialog.dart';
import 'package:app_parent/widgets/student_review_card.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  testWidgets('窄屏大字体下仍可打开指定孩子的围栏设置', (tester) async {
    tester.view.physicalSize = const Size(320, 700);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    var opened = false;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: MediaQuery(
            data: const MediaQueryData(textScaler: TextScaler.linear(1.4)),
            child: SingleChildScrollView(
              child: StudentReviewCard(
                student: const {
                  'id': 7,
                  'nickname': '小明',
                  'grade_band': '8-12',
                },
                onRename: () {},
                onRebind: () {},
                onManageDevices: () {},
                onGradeBandChanged: (_) async {},
                onFenceSettings: () => opened = true,
              ),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('资料与设备'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('围栏设置'));
    await tester.tap(find.text('围栏设置'));
    expect(opened, isTrue);
    expect(tester.takeException(), isNull);
  });

  testWidgets('围栏档位回显并与违禁词一起保存', (tester) async {
    SharedPreferences.setMockInitialValues({'token': 'test-token'});
    await Api.I.loadToken();
    Map<String, dynamic>? saved;
    final client = MockClient((request) async {
      expect(request.method, 'PUT');
      expect(request.url.path, '/parent/students/7/fence-settings');
      saved = jsonDecode(request.body) as Map<String, dynamic>;
      return http.Response('{"ok": true}', 200);
    });
    await http.runWithClient(() async {
      await tester.pumpWidget(
        MaterialApp(
          home: Builder(
            builder: (context) => Scaffold(
              body: TextButton(
                onPressed: () => showDialog<Map<String, dynamic>>(
                  context: context,
                  builder: (_) => const StudentFenceDialog(
                    studentId: 7,
                    studentName: '小明',
                    settings: {
                      'fence_level': 'relaxed',
                      'forbidden_words': ['GAME'],
                    },
                  ),
                ),
                child: const Text('打开'),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('打开'));
      await tester.pumpAndSettle();
      expect(find.text('小明 的围栏设置'), findsOneWidget);
      expect(find.text('宽松'), findsOneWidget);
      await tester.ensureVisible(find.byType(DropdownButtonFormField<String>));
      await tester.tap(find.byType(DropdownButtonFormField<String>));
      await tester.pumpAndSettle();
      await tester.tap(find.text('不设围栏').last);
      await tester.pumpAndSettle();
      expect(find.text('不设围栏：不按内容限制话题，仍执行自定义违禁词。'), findsOneWidget);
      await tester.ensureVisible(find.text('保存设置'));
      await tester.tap(find.text('保存设置'));
      await tester.pumpAndSettle();
      expect(saved?['fence_level'], 'off');
      expect(saved?['forbidden_words'], ['GAME']);
    }, () => client);
  });
}
