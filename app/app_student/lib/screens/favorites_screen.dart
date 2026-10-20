import 'package:flutter/material.dart';
import 'package:app_core/app_core.dart';
import 'package:gpt_markdown/gpt_markdown.dart';
import '../widgets/student_page_state.dart';

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
  String _query = '';
  List<dynamic> get _visible => (_favs ?? [])
      .where(
        (f) => '${f['content']} ${f['teacher_name'] ?? ''}'
            .toLowerCase()
            .contains(_query.toLowerCase()),
      )
      .toList();

  Future<void> _undo(int messageId) async {
    try {
      await Api.I.addFavorite(messageId);
      if (mounted) await _load();
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(e.message)));
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(tr('操作失败，请检查网络后重试'))));
      }
    }
  }

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
      if (mounted) {
        setState(() {
          _favs = list;
          _error = null;
        });
      }
    } on ApiException catch (e) {
      if (mounted) {
        if (_favs == null) {
          setState(() => _error = e.message);
        } else {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text(tr("刷新收藏失败：{0}", [e.message]))),
          );
        }
      }
    } catch (_) {
      if (mounted) {
        if (_favs == null) {
          setState(() => _error = tr("收藏加载失败，请检查网络后重试"));
        } else {
          ScaffoldMessenger.of(
            context,
          ).showSnackBar(SnackBar(content: Text(tr("刷新收藏失败，请检查网络后重试"))));
        }
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _remove(int id) async {
    if (_removingId != null) return;
    final item = _favs!.firstWhere((f) => f['id'] == id);
    setState(() => _removingId = id);
    try {
      await Api.I.deleteFavorite(id);
      if (!mounted) return;
      setState(() => _favs!.removeWhere((item) => item['id'] == id));
      ScaffoldMessenger.of(context)
        ..hideCurrentSnackBar()
        ..showSnackBar(
          SnackBar(
            content: Text(tr('已取消收藏')),
            action: item['message_id'] is int
                ? SnackBarAction(
                    label: tr('撤销'),
                    onPressed: () => _undo(item['message_id'] as int),
                  )
                : null,
          ),
        );
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(e.message)));
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(tr("取消收藏失败，请重试"))));
      }
    } finally {
      if (mounted) setState(() => _removingId = null);
    }
  }

  @override
  Widget build(BuildContext context) {
    AppLanguage.watch(context);
    return Scaffold(
      appBar: AppBar(
        title: Text(tr("我的收藏")),
        actions: [
          IconButton(
            tooltip: tr("刷新收藏"),
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
          ? (_error == null
                ? const Center(child: CircularProgressIndicator())
                : StudentPageState(
                    icon: Icons.wifi_off_rounded,
                    title: tr("收藏加载失败"),
                    description: _error!,
                    onRetry: _load,
                  ))
          : _favs!.isEmpty
          ? StudentPageState(
              icon: Icons.bookmark_border_rounded,
              title: tr("把值得复习的讲解留下来"),
              description: tr("长按聊天消息即可收藏"),
            )
          : Column(
              children: [
                Padding(
                  padding: const EdgeInsets.fromLTRB(20, 12, 20, 0),
                  child: TextField(
                    decoration: InputDecoration(
                      prefixIcon: const Icon(Icons.search),
                      hintText: tr('搜索收藏'),
                    ),
                    onChanged: (value) => setState(() => _query = value.trim()),
                  ),
                ),
                if (_visible.isEmpty)
                  Padding(
                    padding: const EdgeInsets.all(24),
                    child: Text(tr('暂无记录')),
                  ),
                Expanded(
                  child: ListView.builder(
                    padding: const EdgeInsets.all(20),
                    itemCount: _visible.length,
                    itemBuilder: (_, i) {
                      final f = _visible[i] as Map<String, dynamic>;
                      final content = (f['content'] as String? ?? '').trim();
                      final title = content
                          .split('\n')
                          .first
                          .replaceFirst(RegExp(r'^#{1,6}\s+'), '');
                      return Card(
                        clipBehavior: Clip.antiAlias,
                        child: ExpansionTile(
                          key: PageStorageKey('favorite-${f['id']}'),
                          tilePadding: const EdgeInsets.symmetric(
                            horizontal: 16,
                            vertical: 8,
                          ),
                          leading: Icon(
                            Icons.bookmark_rounded,
                            color: Theme.of(context).colorScheme.primary,
                          ),
                          title: Text(
                            title.isEmpty ? tr("收藏的讲解") : title,
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(fontWeight: FontWeight.w700),
                          ),
                          subtitle: Text(
                            [
                                  f['teacher_name'],
                                  displayDate(f['created_at']),
                                  tr('展开阅读完整讲解与公式'),
                                ]
                                .where(
                                  (v) => v != null && v.toString().isNotEmpty,
                                )
                                .join(' · '),
                            style: TextStyle(fontSize: 12),
                          ),
                          childrenPadding: const EdgeInsets.fromLTRB(
                            20,
                            0,
                            20,
                            16,
                          ),
                          children: [
                            MessageImages(
                              blocks: f['content_blocks'] as List? ?? const [],
                            ),
                            GptMarkdown(
                              content,
                              style: const TextStyle(height: 1.6),
                              useDollarSignsForLatex: true,
                            ),
                            const SizedBox(height: 12),
                            if (f['conversation_id'] is int)
                              TextButton.icon(
                                onPressed: () => Navigator.pop(
                                  context,
                                  f['conversation_id'] as int,
                                ),
                                icon: const Icon(Icons.chat_bubble_outline),
                                label: Text(tr('查看来源对话')),
                              ),
                            Align(
                              alignment: Alignment.centerRight,
                              child: TextButton.icon(
                                icon: _removingId == f['id']
                                    ? const SizedBox(
                                        width: 18,
                                        height: 18,
                                        child: CircularProgressIndicator(
                                          strokeWidth: 2,
                                        ),
                                      )
                                    : const Icon(
                                        Icons.bookmark_remove_outlined,
                                        size: 18,
                                      ),
                                label: Text(tr("取消收藏")),
                                onPressed: _removingId == null && !_loading
                                    ? () => _remove(f['id'] as int)
                                    : null,
                              ),
                            ),
                          ],
                        ),
                      );
                    },
                  ),
                ),
              ],
            ),
    );
  }
}
