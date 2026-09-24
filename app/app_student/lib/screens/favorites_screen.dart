import 'package:flutter/material.dart';
import 'package:app_core/app_core.dart';
import 'package:gpt_markdown/gpt_markdown.dart';

/// 我的收藏（P2 学习沉淀）：知识点/解答随时回看，家长端同步可见。
class FavoritesScreen extends StatefulWidget {
  const FavoritesScreen({super.key});
  @override
  State<FavoritesScreen> createState() => _FavoritesScreenState();
}

class _FavoritesScreenState extends State<FavoritesScreen> {
  List<dynamic>? _favs;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final list = await Api.I.myFavorites();
    if (!mounted) return;
    setState(() => _favs = list);
  }

  Future<void> _remove(int id) async {
    await Api.I.deleteFavorite(id);
    _load();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('我的收藏 ⭐')),
      body: _favs == null
          ? const Center(child: CircularProgressIndicator())
          : _favs!.isEmpty
          ? const Center(child: Text('长按聊天消息即可收藏'))
          : ListView.builder(
              padding: const EdgeInsets.all(12),
              itemCount: _favs!.length,
              itemBuilder: (_, i) {
                final f = _favs![i] as Map<String, dynamic>;
                return Card(
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(12, 8, 4, 8),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Expanded(
                          child: GptMarkdown(
                            f['content'] as String? ?? '',
                            style: const TextStyle(
                              color: Colors.black87,
                              height: 1.4,
                            ),
                            useDollarSignsForLatex: true,
                          ),
                        ),
                        IconButton(
                          icon: const Icon(Icons.close, size: 18),
                          tooltip: '取消收藏',
                          onPressed: () => _remove(f['id'] as int),
                        ),
                      ],
                    ),
                  ),
                );
              },
            ),
    );
  }
}
