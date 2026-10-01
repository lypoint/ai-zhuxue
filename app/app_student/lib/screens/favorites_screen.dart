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
  String? _error;
  bool _loading = false;
  int? _removingId;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    if (_loading) return;
    setState(() {
      _loading = true;
      if (_favs == null) _error = null;
    });
    try {
      final list = await Api.I.myFavorites();
      if (mounted) setState(() { _favs = list; _error = null; });
    } on ApiException catch (e) {
      if (mounted) {
        if (_favs == null) {
          setState(() => _error = e.message);
        } else {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('刷新收藏失败：${e.message}')),
          );
        }
      }
    } catch (_) {
      if (mounted) {
        if (_favs == null) {
          setState(() => _error = '收藏加载失败，请检查网络后重试');
        } else {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('刷新收藏失败，请检查网络后重试')),
          );
        }
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _remove(int id) async {
    if (_removingId != null) return;
    setState(() => _removingId = id);
    try {
      await Api.I.deleteFavorite(id);
      if (!mounted) return;
      setState(() => _favs!.removeWhere((item) => item['id'] == id));
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('已取消收藏')),
      );
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(e.message)),
        );
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('取消收藏失败，请重试')),
        );
      }
    } finally {
      if (mounted) setState(() => _removingId = null);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('我的收藏 ⭐'),
        actions: [
          IconButton(
            tooltip: '刷新收藏',
            onPressed: _loading || _removingId != null ? null : _load,
            icon: _loading
                ? const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.refresh),
          ),
        ],
      ),
      body: _favs == null
          ? Center(
              child: _error == null
                  ? const CircularProgressIndicator()
                  : Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(_error!),
                        TextButton(onPressed: _load, child: const Text('重试')),
                      ],
                    ),
            )
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
                          icon: _removingId == f['id']
                              ? const SizedBox(
                                  width: 18,
                                  height: 18,
                                  child: CircularProgressIndicator(strokeWidth: 2),
                                )
                              : const Icon(Icons.close, size: 18),
                          tooltip: '取消收藏',
                          onPressed: _removingId == null && !_loading
                              ? () => _remove(f['id'] as int)
                              : null,
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
