import 'package:app_core/app_core.dart';
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
    AppLanguage.watch(context);
    final earned = summary?['today']?['stars'] == 1;
    return Card(
      color: const Color(0xFFEAF2E9),
      margin: const EdgeInsets.fromLTRB(12, 4, 12, 4),
      child: InkWell(
        borderRadius: BorderRadius.circular(24),
        onTap: onOpen,
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            children: [
              Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(
                    earned ? Icons.auto_awesome : Icons.auto_awesome_outlined,
                    color: Theme.of(context).colorScheme.primary,
                  ),
                  if (summary != null) ...[
                    const SizedBox(height: 4),
                    Text(
                      tr("{0} 颗", [summary!['balance']]),
                      semanticsLabel: tr("可用 {0} 颗小行星", [summary!['balance']]),
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ],
                ],
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      summary == null
                          ? tr("今日参与奖励")
                          : earned
                          ? tr("今日已获得 1 颗小行星")
                          : tr("今日小行星等你领取"),
                      style: const TextStyle(fontWeight: FontWeight.w700),
                    ),
                    Text(
                      error != null
                          ? trMessage(error!)
                          : summary == null
                          ? tr("正在加载今日奖励…")
                          : earned
                          ? tr("感谢你的认真参与！今天已领取 1/1 颗。")
                          : tr("今天学一次、如实反馈一次，即可获得 1 颗。"),
                      style: TextStyle(
                        fontSize: 12,
                        color: Theme.of(context).colorScheme.onSurfaceVariant,
                      ),
                    ),
                  ],
                ),
              ),
              if (error != null)
                IconButton(
                  onPressed: onRetry,
                  tooltip: tr("重试加载今日奖励"),
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
