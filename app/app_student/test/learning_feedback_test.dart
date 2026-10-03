import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:app_student/models/bubble.dart';
import 'package:app_student/widgets/message_bubble.dart';

void main() {
  testWidgets('老师回答可更新反馈，重复选择和未完成回答不可提交', (tester) async {
    String? selected;
    Future<void> show(Bubble bubble, {String? feedback}) => tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: MessageBubble(
            bubble: bubble,
            onLongPress: () {},
            feedback: feedback,
            onFeedback: (action) => selected = action,
          ),
        ),
      ),
    );
    await show(Bubble('assistant', '讲解内容', messageId: 1));
    expect(find.text('懂了'), findsOneWidget);
    expect(find.text('不懂'), findsOneWidget);
    expect(find.text('继续讲解'), findsOneWidget);
    await tester.tap(find.text('不懂'));
    expect(selected, 'not_understood');
    selected = null;
    await show(
      Bubble('assistant', '讲解内容', messageId: 1),
      feedback: 'understood',
    );
    expect(find.text('✓ 懂了'), findsOneWidget);
    await tester.tap(find.text('不懂'));
    expect(selected, 'not_understood');
    selected = null;
    await tester.tap(find.text('✓ 懂了'));
    expect(selected, isNull);
    await show(Bubble('assistant', '生成中的内容'));
    expect(find.text('懂了'), findsNothing);
    await show(Bubble('user', '问题', messageId: 2));
    expect(find.text('懂了'), findsNothing);
  });
}
