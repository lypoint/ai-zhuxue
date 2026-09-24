import 'package:flutter/material.dart';
import 'package:app_core/app_core.dart';

/// 我的学习统计（P2）：学生自己可见，增强自我管理。
class MyStatsScreen extends StatelessWidget {
  const MyStatsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('我的学习统计')),
      body: FutureBuilder<Map<String, dynamic>>(
        future: Api.I.myStats(),
        builder: (ctx, snap) {
          if (!snap.hasData) {
            return const Center(child: CircularProgressIndicator());
          }
          final d = snap.data!;
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              _card('今天', [
                ['学习提问', '${d['today']['questions']} 次'],
                ['被拦截', '${d['today']['blocked']} 次'],
                ['学习时长', '约 ${d['today']['minutes']} 分钟'],
              ]),
              _card('本周', [
                ['学习提问', '${d['week']['questions']} 次'],
                ['被拦截', '${d['week']['blocked']} 次'],
                ['学习时长', '约 ${d['week']['minutes']} 分钟'],
                ['活跃天数', '${d['week']['active_days']} 天'],
                ['收藏知识点', '${d['favorites']} 条'],
              ]),
              const Padding(
                padding: EdgeInsets.all(12),
                child: Text(
                  '小提示：长按聊天消息可以收藏喜欢的内容哦 ⭐',
                  style: TextStyle(fontSize: 12, color: Colors.grey),
                ),
              ),
            ],
          );
        },
      ),
    );
  }

  Widget _card(String title, List<List<String>> rows) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              title,
              style: const TextStyle(
                fontWeight: FontWeight.bold,
                color: Color(0xFF15857A),
              ),
            ),
            const SizedBox(height: 8),
            ...rows.map(
              (r) => Padding(
                padding: const EdgeInsets.symmetric(vertical: 3),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(r[0]),
                    Text(
                      r[1],
                      style: const TextStyle(fontWeight: FontWeight.w600),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
