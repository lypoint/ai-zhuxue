import 'package:flutter/material.dart';
import 'package:app_core/app_core.dart';
import 'package:gpt_markdown/gpt_markdown.dart';

/// 孩子的收藏（P2 学习沉淀，家长可见以了解兴趣点）。
class ParentFavoritesScreen extends StatelessWidget {
  final int studentId;
  final String studentName;
  const ParentFavoritesScreen({
    super.key,
    required this.studentId,
    required this.studentName,
  });

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text('$studentName 的收藏')),
      body: FutureBuilder<List<dynamic>>(
        future: Api.I.studentFavorites(studentId),
        builder: (ctx, snap) {
          if (!snap.hasData) {
            return const Center(child: CircularProgressIndicator());
          }
          final items = snap.data!;
          if (items.isEmpty) return const Center(child: Text('还没有收藏内容'));
          return ListView.builder(
            padding: const EdgeInsets.all(12),
            itemCount: items.length,
            itemBuilder: (_, i) {
              final f = items[i] as Map<String, dynamic>;
              return Card(
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      GptMarkdown(
                        f['content'] as String? ?? '',
                        style: const TextStyle(
                          color: Colors.black87,
                          height: 1.4,
                        ),
                        useDollarSignsForLatex: true,
                      ),
                      const SizedBox(height: 4),
                      Text(
                        (f['created_at'] ?? '')
                            .toString()
                            .replaceAll('T', ' ')
                            .substring(0, 16),
                        style: const TextStyle(fontSize: 11, color: Colors.grey),
                      ),
                    ],
                  ),
                ),
              );
            },
          );
        },
      ),
    );
  }
}
