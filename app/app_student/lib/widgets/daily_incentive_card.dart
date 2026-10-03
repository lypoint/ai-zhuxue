import 'package:flutter/material.dart';

/// Participation rewards have equal value for every honest feedback choice.
class DailyIncentiveCard extends StatelessWidget {
  final Map<String, dynamic>? summary;
  final String? error;
  final VoidCallback onOpen;
  final VoidCallback onRetry;
  const DailyIncentiveCard({
    super.key,
    required this.summary,
    this.error,
    required this.onOpen,
    required this.onRetry,
  });

  @override
  Widget build(BuildContext context) {
    final earned = summary?['today']?['stars'] == 1;
    return Card(
      margin: const EdgeInsets.fromLTRB(12, 4, 12, 4),
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: onOpen,
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            children: [
              Icon(
                earned ? Icons.auto_awesome : Icons.auto_awesome_outlined,
                color: Theme.of(context).colorScheme.primary,
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      summary == null
                          ? '今日参与奖励'
                          : earned
                          ? '今日已获得 1 颗小行星'
                          : '今日小行星等你领取',
                      style: const TextStyle(fontWeight: FontWeight.w700),
                    ),
                    Text(
                      error != null
                          ? error!
                          : summary == null
                          ? '正在加载今日奖励…'
                          : earned
                          ? '感谢你的认真参与！今天已领取 1/1 颗。'
                          : '今天学一次、如实反馈一次，即可获得 1 颗。',
                    ),
                    if (summary != null)
                      Text(
                        '可用 ${summary!['balance']} 颗 · 懂了、不懂、继续讲解都一样值得鼓励',
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                  ],
                ),
              ),
              if (error != null)
                IconButton(
                  onPressed: onRetry,
                  tooltip: '重试加载今日奖励',
                  icon: const Icon(Icons.refresh),
                )
              else
                const Icon(Icons.chevron_right),
            ],
          ),
        ),
      ),
    );
  }
}
