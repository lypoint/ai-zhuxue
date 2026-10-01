import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:app_core/app_core.dart';
import 'package:app_parent/screens/login_screen.dart';
import 'package:app_parent/screens/home_screen.dart';
import 'package:app_parent/screens/identity_verification_screen.dart';
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
  });

  testWidgets('家长称呼为空时给出注册错误提示', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: LoginScreen()));
    await tester.ensureVisible(find.text('登录或注册'));
    await tester.tap(find.text('登录或注册'));
    await tester.pump();
    expect(find.textContaining('请填写家长称呼'), findsWidgets);
  });

  testWidgets('实名认证是登录后的可选流程', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(home: IdentityVerificationScreen(verified: false)),
    );
    expect(find.textContaining('不影响功能使用'), findsOneWidget);
    expect(find.text('真实姓名'), findsOneWidget);
    expect(find.text('身份证号'), findsOneWidget);
    await tester.tap(find.text('提交认证'));
    await tester.pump();
    expect(find.text('请填写真实姓名和有效身份证号'), findsOneWidget);
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
    addTearDown(() => tester.binding.defaultBinaryMessenger
        .setMockMethodCallHandler(SystemChannels.platform, null));
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
    expect(
      tester.getSize(find.byType(StudentReviewCard)).height,
      lessThan(230),
    );
    await tester.tap(find.text('绑定设备'));
    expect(bindRequested, isTrue);
  });

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
}
