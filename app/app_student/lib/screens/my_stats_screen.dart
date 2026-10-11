import 'package:flutter/material.dart';
import 'package:app_core/app_core.dart';
import '../widgets/student_page_state.dart';

/// 我的学习统计（P2）：学生自己可见，增强自我管理。
class MyStatsScreen extends StatefulWidget {
  const MyStatsScreen({super.key});

  @override
  State<MyStatsScreen> createState() => _MyStatsScreenState();
}

class _MyStatsScreenState extends State<MyStatsScreen> {
  late Future<Map<String, dynamic>> _stats;

  @override
  void initState() {
    super.initState();
    _stats = Api.I.myStats();
  }

  void _retry() => setState(() {
    _stats = Api.I.myStats();
  });

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('我的学习统计')),
      body: FutureBuilder<Map<String, dynamic>>(
        future: _stats,
        builder: (ctx, snap) {
          if (snap.hasError) {
            return StudentPageState(
              icon: Icons.wifi_off_rounded,
              title: '学习统计加载失败',
              description: '请检查网络后重试',
              onRetry: _retry,
            );
          }
          if (!snap.hasData) {
            return const Center(child: CircularProgressIndicator());
          }
          final d = snap.data!;
          return RefreshIndicator(
            onRefresh: () async {
              _retry();
              await _stats.then<void>((_) {}, onError: (_) {});
            },
            child: ListView(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: const EdgeInsets.all(20),
              children: [
                Card(
                  color: const Color(0xFFE7F1E9),
                  child: Padding(
                    padding: const EdgeInsets.all(20),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Icon(
                          Icons.wb_sunny_outlined,
                          color: Theme.of(context).colorScheme.primary,
                        ),
                        const SizedBox(height: 12),
                        const Text(
                          '今天的学习足迹',
                          style: TextStyle(
                            fontSize: 22,
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                        const SizedBox(height: 6),
                        const Text('每一次提问，都在积累新的理解'),
                        const SizedBox(height: 24),
                        LayoutBuilder(
                          builder: (_, constraints) => Wrap(
                            spacing: 16,
                            runSpacing: 20,
                            children: [
                              for (final metric in [
                                ('学习提问', '${d['today']['questions']} 次'),
                                ('学习时长', '约 ${d['today']['minutes']} 分钟'),
                              ])
                                SizedBox(
                                  width:
                                      constraints.maxWidth < 260 ||
                                          MediaQuery.textScalerOf(
                                                context,
                                              ).scale(1) >
                                              1.2
                                      ? constraints.maxWidth
                                      : (constraints.maxWidth - 16) / 2,
                                  child: Column(
                                    crossAxisAlignment:
                                        CrossAxisAlignment.start,
                                    children: [
                                      Text(
                                        metric.$2,
                                        style: TextStyle(
                                          fontSize: 22,
                                          fontWeight: FontWeight.w800,
                                          color: Theme.of(
                                            context,
                                          ).colorScheme.primary,
                                        ),
                                      ),
                                      const SizedBox(height: 4),
                                      Text(metric.$1),
                                    ],
                                  ),
                                ),
                            ],
                          ),
                        ),
                        const SizedBox(height: 20),
                        Text(
                          '今日被拦截 ${d['today']['blocked']} 次',
                          style: TextStyle(
                            fontSize: 12,
                            color: Theme.of(
                              context,
                            ).colorScheme.onSurfaceVariant,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                _card('本周学习概览', [
                  ['学习提问', '${d['week']['questions']} 次'],
                  ['学习时长', '约 ${d['week']['minutes']} 分钟'],
                  ['活跃天数', '${d['week']['active_days']} 天'],
                  ['收藏知识点', '${d['favorites']} 条'],
                  ['被拦截', '${d['week']['blocked']} 次'],
                ]),
                Padding(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 8,
                    vertical: 12,
                  ),
                  child: Text(
                    '把有帮助的讲解收藏起来，复习时再看一遍。',
                    style: TextStyle(
                      fontSize: 13,
                      height: 1.5,
                      color: Theme.of(context).colorScheme.onSurfaceVariant,
                    ),
                  ),
                ),
              ],
            ),
          );
        },
      ),
    );
  }

  Widget _card(String title, List<List<String>> rows) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              title,
              style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 16),
            for (final row in rows)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 8),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(child: Text(row[0])),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        row[1],
                        textAlign: TextAlign.end,
                        style: const TextStyle(fontWeight: FontWeight.w700),
                      ),
                    ),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }
}
