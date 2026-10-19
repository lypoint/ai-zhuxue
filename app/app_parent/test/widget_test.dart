import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:app_core/app_core.dart';
import 'package:app_parent/screens/login_screen.dart';
import 'package:app_parent/screens/home_screen.dart';
import 'package:app_parent/widgets/student_review_card.dart';
import 'package:app_parent/widgets/subscription_card.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('家长端登录页无需身份证号', (tester) async {
    SharedPreferences.setMockInitialValues({});
    Api.I.clearToken();
    await tester.pumpWidget(const MaterialApp(home: LoginScreen()));
    expect(find.text('家长称呼'), findsOneWidget);
    expect(find.text('身份证号'), findsNothing);
    expect(find.text('登录或注册'), findsOneWidget);
    expect(find.byType(PasswordLoginButton), findsOneWidget);
  });

  testWidgets('永久会员展示百名额且不提供重复购买入口', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SubscriptionCard(
            sub: const {
              'plan': 'permanent',
              'active': true,
              'seat_count': 100,
              'used_seats': 0,
            },
            onPay: () => fail('Lifetime membership must not purchase'),
            onAddSeat: () => fail('Top tier needs no extra seats'),
            onManage: () => fail('No recurring subscription to manage'),
          ),
        ),
      ),
    );
    expect(find.text('永久会员'), findsOneWidget);
    expect(find.text('孩子名额 0/100'), findsOneWidget);
    expect(find.byType(FilledButton), findsNothing);
    expect(find.byType(TextButton), findsNothing);
  });

  testWidgets('家长称呼为空时给出注册错误提示', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: LoginScreen()));
    await tester.ensureVisible(find.text('登录或注册'));
    await tester.tap(find.text('登录或注册'));
    await tester.pump();
    expect(find.textContaining('请填写家长称呼'), findsWidgets);
  });

  testWidgets('绑定码弹窗显示二维码和关闭按钮', (tester) async {
    var copyFails = false;
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
      SystemChannels.platform,
      (call) async {
        if (copyFails && call.method == 'Clipboard.setData') {
          throw PlatformException(code: 'COPY_FAILED');
        }
        return null;
      },
    );
    addTearDown(
      () => tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
        SystemChannels.platform,
        null,
      ),
    );
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (context) => TextButton(
              onPressed: () => showDialog<void>(
                context: context,
                builder: (_) =>
                    const BindCodeDialog(code: 'A3F9C2B1', label: '学生端绑定码'),
              ),
              child: const Text('生成绑定码'),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('生成绑定码'));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(find.text('A3F9C2B1'), findsOneWidget);
    expect(find.text('学生端绑定码'), findsOneWidget);
    expect(find.byType(SelectableText), findsNothing);
    expect(find.text('复制绑定码'), findsOneWidget);
    await tester.tap(find.text('完成'));
    await tester.pumpAndSettle();
    expect(find.text('学生端绑定码'), findsNothing);
    await tester.tap(find.text('生成绑定码'));
    await tester.pumpAndSettle();
    copyFails = true;
    await tester.tap(find.text('复制绑定码'));
    await tester.pumpAndSettle();
    expect(find.text('学生端绑定码'), findsOneWidget);
    expect(find.text('复制失败，请重试'), findsOneWidget);
    copyFails = false;
    await tester.tap(find.text('复制绑定码'));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(find.text('学生端绑定码'), findsNothing);
    expect(find.text('绑定码已复制'), findsOneWidget);
  });

  testWidgets('窄屏孩子卡片展示绑定入口', (tester) async {
    var bindRequested = false;
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Center(
            child: StudentReviewCard(
              student: const {
                'id': 1,
                'nickname': '我的孩子',
                'grade_band': '8-12',
              },
              onRename: () {},
              onRebind: () => bindRequested = true,
              onManageDevices: () {},
              onGradeBandChanged: (_) async {},
            ),
          ),
        ),
      ),
    );
    expect(tester.takeException(), isNull);
    expect(find.text('我的孩子'), findsOneWidget);
    expect(find.text('绑定设备'), findsOneWidget);
    for (final label in ['学习内容', '查看孩子的提问与老师解答', '收藏', '成绩', '资料与设备']) {
      expect(find.text(label), findsOneWidget);
    }
    expect(
      tester.getSize(find.byType(StudentReviewCard)).height,
      lessThan(360),
    );
    await tester.tap(find.text('绑定设备'));
    expect(bindRequested, isTrue);
  });

  for (final hasPending in [false, true]) {
    testWidgets('有效月订阅只能恢复待支付订单，仍可即时升级 ($hasPending)', (tester) async {
      var upgraded = false;
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SubscriptionCard(
              sub: {
                'active': true,
                'plan': 'monthly',
                'monthly_price_cny': 99,
                'can_purchase_subscription': false,
                'has_pending_payment': hasPending,
              },
              onPay: () {},
              onAddSeat: () => upgraded = true,
            ),
          ),
        ),
      );
      expect(find.textContaining('¥99/月'), findsOneWidget);
      final button = tester.widget<FilledButton>(find.byType(FilledButton));
      expect(button.onPressed != null, hasPending);
      expect(find.text(hasPending ? '继续支付' : '订阅有效'), findsOneWidget);
      await tester.tap(find.text('增加名额'));
      expect(upgraded, isTrue);
    });
  }

  testWidgets('订阅处理中禁用支付和增加名额按钮', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SubscriptionCard(
            sub: const {'active': true, 'plan': 'monthly'},
            onPay: () {},
            onAddSeat: () {},
            billingPending: true,
          ),
        ),
      ),
    );
    expect(find.text('处理中…'), findsOneWidget);
    expect(
      tester
          .widget<FilledButton>(find.widgetWithText(FilledButton, '处理中…'))
          .onPressed,
      isNull,
    );
    expect(
      tester
          .widget<TextButton>(find.widgetWithText(TextButton, '增加名额'))
          .onPressed,
      isNull,
    );
  });

  testWidgets('更新孩子资料时禁用重复编辑', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: StudentReviewCard(
            student: const {'id': 1, 'nickname': '孩子', 'grade_band': '8-12'},
            onRename: () {},
            onRebind: null,
            onManageDevices: () {},
            onGradeBandChanged: (_) async {},
            updatesDisabled: true,
          ),
        ),
      ),
    );
    await tester.tap(find.text('资料与设备'));
    await tester.pumpAndSettle();
    expect(
      tester
          .widget<DropdownButton<String>>(find.byType(DropdownButton<String>))
          .onChanged,
      isNull,
    );
    expect(
      tester
          .widget<TextButton>(
            find.ancestor(
              of: find.text('改名'),
              matching: find.byWidgetPredicate(
                (widget) => widget is TextButton,
              ),
            ),
          )
          .onPressed,
      isNull,
    );
  });

  testWidgets('窄屏放大文字时孩子操作仍可阅读', (tester) async {
    tester.view.physicalSize = const Size(320, 700);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: MediaQuery(
            data: const MediaQueryData(textScaler: TextScaler.linear(1.4)),
            child: StudentReviewCard(
              student: const {'id': 1, 'nickname': '孩子', 'grade_band': '8-12'},
              onRename: () {},
              onRebind: () {},
              onManageDevices: () {},
              onGradeBandChanged: (_) async {},
            ),
          ),
        ),
      ),
    );
    expect(tester.takeException(), isNull);
    expect(find.text('收藏'), findsOneWidget);
    await tester.tap(find.text('资料与设备'));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(find.text('设备'), findsOneWidget);
  });
}
