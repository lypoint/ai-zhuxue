import 'language.dart';
import 'package:flutter/material.dart';
import 'trend_chart.dart';

/// 趋势时间范围选项：（标签，天数；null = 全部）
List<(String, int?)> get trendRangeOptions => <(String, int?)>[
  (tr('全部'), null),
  (tr('近 30 天'), 30),
  (tr('近 90 天'), 90),
  (tr('近一年'), 365),
];

/// 由范围天数计算 from 日期（YYYY-MM-DD）；null 表示不筛选。
String? trendFromDate(int? days) => days == null
    ? null
    : DateTime.now()
          .subtract(Duration(days: days))
          .toIso8601String()
          .substring(0, 10);

Map<String, String> get _directionLabels => {
  'up': tr('上升'),
  'down': tr('下降'),
  'stable': tr('稳定'),
};

/// 成绩趋势卡（规格 7.2）：折线趋势 + 科目/时间范围筛选。
/// 趋势数据由调用方获取（随页面下拉刷新）；筛选变化经 [onChanged] 通知重取。
class GradeTrendCard extends StatelessWidget {
  final Map<String, dynamic>? trend;
  final List<String> subjects;

  /// 当前筛选；[subject] 不在 [subjects] 中时按“全部科目”展示，避免断言失败。
  final String? subject;
  final int? rangeDays;
  final void Function(String? subject, int? rangeDays) onChanged;

  const GradeTrendCard({
    super.key,
    required this.trend,
    required this.subjects,
    required this.subject,
    required this.rangeDays,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    AppLanguage.watch(context);
    final t = trend ?? const <String, dynamic>{};
    final points = ((t['points'] as List?) ?? const [])
        .whereType<Map>()
        .map((e) => Map<String, dynamic>.from(e))
        .toList();
    final effectiveSubject = subjects.contains(subject) ? subject : null;
    final separateSubjects = effectiveSubject == null && subjects.length > 1;
    final direction = separateSubjects ? null : t['direction'] as String?;
    return Card(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(14, 12, 14, 10),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.show_chart, size: 20),
                const SizedBox(width: 6),
                Text(tr("成绩趋势"), style: TextStyle(fontWeight: FontWeight.bold)),
                const Spacer(),
                if (!separateSubjects)
                  Text(
                    direction == null || direction == 'insufficient'
                        ? tr("数据不足")
                        : _directionLabels[direction] ?? direction,
                    style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      color: direction == 'up'
                          ? const Color(0xFF1B7D46)
                          : direction == 'down'
                          ? const Color(0xFFC0392B)
                          : Colors.grey,
                    ),
                  ),
              ],
            ),
            Wrap(
              spacing: 4,
              runSpacing: 4,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                // ignore: deprecated_member_use
                DropdownButton<String>(
                  value: effectiveSubject,
                  hint: Text(tr("全部科目"), style: TextStyle(fontSize: 13)),
                  isDense: true,
                  underline: const SizedBox.shrink(),
                  items: [
                    DropdownMenuItem<String>(
                      value: null,
                      child: Text(tr("全部科目"), style: TextStyle(fontSize: 13)),
                    ),
                    for (final s in subjects)
                      DropdownMenuItem(
                        value: s,
                        child: Text(s, style: const TextStyle(fontSize: 13)),
                      ),
                  ],
                  onChanged: (v) => onChanged(v, rangeDays),
                ),
                const SizedBox(width: 10),
                // ignore: deprecated_member_use
                DropdownButton<int>(
                  value: rangeDays,
                  isDense: true,
                  underline: const SizedBox.shrink(),
                  items: [
                    for (final (label, days) in trendRangeOptions)
                      DropdownMenuItem(
                        value: days,
                        child: Text(
                          label,
                          style: const TextStyle(fontSize: 13),
                        ),
                      ),
                  ],
                  onChanged: (v) => onChanged(effectiveSubject, v),
                ),
              ],
            ),
            if (separateSubjects)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 20),
                child: Text(tr("请选择一个科目查看趋势，不同科目的成绩不混合比较。")),
              )
            else if (points.isEmpty)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 20),
                child: Text(tr("添加成绩后即可查看趋势")),
              )
            else
              TrendChart(points: points),
            const SizedBox(height: 4),
            if (!separateSubjects && points.isNotEmpty)
              Wrap(
                spacing: 12,
                runSpacing: 8,
                children: [
                  if (t['latest'] != null) Text(tr("最近 {0}%", [t['latest']])),
                  if (t['delta'] != null) Text(tr("变化 {0}", [t['delta']])),
                  if (t['average_last_3'] != null)
                    Text(tr("近三次平均 {0}%", [t['average_last_3']])),
                ],
              ),
          ],
        ),
      ),
    );
  }
}
