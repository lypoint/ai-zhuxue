import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:app_student/widgets/daily_incentive_card.dart';

void main() {
  testWidgets('每日奖励展示未领取、已领取和加载失败状态', (tester) async {
    var opened = false;
    var retried = false;
    Future<void> show(Map<String, dynamic>? data, {String? error}) => tester.pumpWidget(
      MaterialApp(home: Scaffold(body: DailyIncentiveCard(
        summary: data, error: error, onOpen: () => opened = true,
        onRetry: () => retried = true,
      ))),
    );
    await show({'today': {'stars': 0}, 'balance': 3});
    expect(find.text('今日小行星等你领取'), findsOneWidget);
    expect(find.textContaining('如实反馈一次'), findsOneWidget);
    await tester.tap(find.text('今日小行星等你领取'));
    expect(opened, isTrue);
    await show({'today': {'stars': 1}, 'balance': 4});
    expect(find.text('今日已获得 1 颗小行星'), findsOneWidget);
    expect(find.textContaining('今天已领取 1/1'), findsOneWidget);
    await show(null, error: '今日奖励加载失败，请重试');
    expect(find.text('今日已获得 1 颗小行星'), findsNothing);
    await tester.tap(find.byTooltip('重试加载今日奖励'));
    expect(retried, isTrue);
  });

  testWidgets('窄屏放大文字可完整展示每日激励', (tester) async {
    tester.view.physicalSize = const Size(320, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(MaterialApp(home: MediaQuery(
      data: const MediaQueryData(textScaler: TextScaler.linear(1.5)),
      child: Scaffold(body: DailyIncentiveCard(
        summary: const {'today': {'stars': 1}, 'balance': 4},
        onOpen: () {}, onRetry: () {},
      )),
    )));
    expect(tester.takeException(), isNull);
    expect(find.text('今日已获得 1 颗小行星'), findsOneWidget);
  });
}
