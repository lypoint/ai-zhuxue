import 'package:app_parent/widgets/management_settings_card.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('使用时长超过后端上限时提示原因', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ManagementSettingsCard(
            settings: const {'daily_message_cap': 200, 'daily_minutes_cap': 60},
            onSaved: () {},
          ),
        ),
      ),
    );

    await tester.enterText(find.byType(TextField).at(1), '600');
    await tester.tap(find.text('保存设置'));
    await tester.pump();
    expect(find.text('每日使用时长上限需为 0–480 分钟'), findsOneWidget);
  });
}
