import 'package:flutter/material.dart';

/// 评估时间范围：from/to 均为 YYYY-MM-DD（to = 今天）。
class AssessmentRange {
  final String from;
  final String to;
  const AssessmentRange({required this.from, required this.to});
}

/// 学业/身心评估触发前选择时间范围（规格 7.3「按时间范围触发」）。
/// 返回 null 表示用户取消。
Future<AssessmentRange?> chooseAssessmentRange(BuildContext context) async {
  final days = await showDialog<int>(
    context: context,
    builder: (ctx) => SimpleDialog(
      title: const Text('选择分析时间范围'),
      children: [
        for (final (label, value) in const [
          ('近 7 天', 7),
          ('近 30 天', 30),
          ('近 90 天', 90),
          ('近一年', 365),
        ])
          SimpleDialogOption(
            onPressed: () => Navigator.pop(ctx, value),
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 6),
              child: Text(label),
            ),
          ),
      ],
    ),
  );
  if (days == null) return null;
  final now = DateTime.now();
  return AssessmentRange(
    from: now
        .subtract(Duration(days: days))
        .toIso8601String()
        .substring(0, 10),
    to: now.toIso8601String().substring(0, 10),
  );
}
