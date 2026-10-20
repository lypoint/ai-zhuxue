import 'package:flutter/material.dart';
import 'package:app_core/app_core.dart';
import 'package:gpt_markdown/gpt_markdown.dart';
import 'conversation_detail_screen.dart';

/// 孩子的收藏（P2 学习沉淀，家长可见以了解兴趣点）。
class ParentFavoritesScreen extends StatefulWidget {
  final int studentId;
  final String studentName;
  const ParentFavoritesScreen({
    super.key,
    required this.studentId,
    required this.studentName,
  });

  @override
  State<ParentFavoritesScreen> createState() => _ParentFavoritesScreenState();
}

class _ParentFavoritesScreenState extends State<ParentFavoritesScreen> {
  late Future<List<dynamic>> _favorites;
  final Set<int> _expanded = {};

  @override
  void initState() {
    super.initState();
    _favorites = Api.I.studentFavorites(widget.studentId);
  }

  void _retry() => setState(() {
    _favorites = Api.I.studentFavorites(widget.studentId);
  });

  @override
  Widget build(BuildContext context) {
    AppLanguage.watch(context);
    return Scaffold(
      appBar: AppBar(title: Text(tr("{0} 的收藏", [widget.studentName]))),
      body: FutureBuilder<List<dynamic>>(
        future: _favorites,
        builder: (ctx, snap) {
          if (snap.hasError) {
            return Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(tr("收藏加载失败，请检查网络后重试")),
                  TextButton(onPressed: _retry, child: Text(tr("重试"))),
                ],
              ),
            );
          }
          if (!snap.hasData) {
            return const Center(child: CircularProgressIndicator());
          }
          final items = snap.data!;
          if (items.isEmpty) {
            return Center(
              child: Padding(
                padding: const EdgeInsets.all(32),
                child: Text(
                  tr("孩子收藏的老师解答会显示在这里，方便一起回顾。"),
                  textAlign: TextAlign.center,
                ),
              ),
            );
          }
          return ListView.builder(
            padding: const EdgeInsets.all(12),
            itemCount: items.length,
            itemBuilder: (_, i) {
              final f = items[i] as Map<String, dynamic>;
              final content = f['content'] as String? ?? '';
              final expanded = _expanded.contains(f['id']);
              return Card(
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      MessageImages(
                        blocks: f['content_blocks'] as List? ?? const [],
                      ),
                      GptMarkdown(
                        content.length > 240 && !expanded
                            ? '${content.substring(0, 240)}…'
                            : content,
                        style: const TextStyle(
                          color: Colors.black87,
                          height: 1.4,
                        ),
                        useDollarSignsForLatex: true,
                      ),
                      if (content.length > 240)
                        TextButton(
                          onPressed: () => setState(() {
                            if (expanded) {
                              _expanded.remove(f['id']);
                            } else {
                              _expanded.add(f['id'] as int);
                            }
                          }),
                          child: Text(expanded ? tr("收起") : tr("展开全文")),
                        ),
                      if (f['conversation_id'] != null)
                        TextButton.icon(
                          icon: const Icon(Icons.forum_outlined, size: 18),
                          label: Text(tr("查看来源对话")),
                          onPressed: () => Navigator.of(context).push(
                            MaterialPageRoute(
                              builder: (_) => ConversationDetailScreen(
                                conversationId: f['conversation_id'] as int,
                                title: tr("相关对话"),
                              ),
                            ),
                          ),
                        ),
                      const SizedBox(height: 8),
                      Text(
                        displayDate(f['created_at']),
                        style: const TextStyle(
                          fontSize: 11,
                          color: Colors.grey,
                        ),
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
