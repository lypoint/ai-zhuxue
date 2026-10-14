import 'package:flutter/material.dart';
import 'package:app_core/app_core.dart';
import 'conversation_detail_screen.dart';

/// 家长审查入口：某个孩子的全部对话列表 + 学习摘要 + 用量估算 + 全文搜索。
class ReviewScreen extends StatefulWidget {
  final int studentId;
  final String studentName;
  const ReviewScreen({
    super.key,
    required this.studentId,
    required this.studentName,
  });
  @override
  State<ReviewScreen> createState() => _ReviewScreenState();
}

class _ReviewScreenState extends State<ReviewScreen> {
  List<dynamic>? _conversations;
  Map<String, dynamic>? _usage;
  Map<String, dynamic>? _summary;
  List<dynamic>? _searchHits;
  final _searchCtrl = TextEditingController();
  String _status = 'all';
  String? _loadError;
  String? _supplementError;
  bool _refreshing = false;
  int _loadGeneration = 0;
  bool _searching = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _searchCtrl.dispose();
    super.dispose();
  }

  Future<void> _doSearch() async {
    final q = _searchCtrl.text.trim();
    if (q.length < 2) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(tr("请输入至少 2 个字再搜索"))));
      return;
    }
    if (_searching) return;
    setState(() {
      _searching = true;
      _searchHits = null;
    });
    try {
      final hits = await Api.I.searchConversations(widget.studentId, q);
      if (!mounted) return;
      setState(() => _searchHits = hits);
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(e.message)));
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(tr("搜索失败，请检查网络后重试"))));
      }
    } finally {
      if (mounted) setState(() => _searching = false);
    }
  }

  Future<void> _load({bool reportRetry = false}) async {
    final generation = ++_loadGeneration;
    final status = _status;
    setState(() => _refreshing = true);
    try {
      final list = await Api.I.conversations(widget.studentId, status: status);
      Map<String, dynamic>? usage;
      Map<String, dynamic>? summary;
      final unavailable = <String>[];
      try {
        usage = await Api.I.studentUsage(widget.studentId);
      } catch (_) {
        unavailable.add(tr("用量"));
      }
      try {
        summary = await Api.I.studentSummary(widget.studentId);
      } catch (_) {
        unavailable.add(tr("学习摘要"));
      }
      if (!mounted || generation != _loadGeneration || status != _status) {
        return;
      }
      setState(() {
        _conversations = list;
        _usage = usage;
        _summary = summary;
        _loadError = null;
        _supplementError = unavailable.isEmpty
            ? null
            : tr("{0}暂不可用，请重试", [unavailable.join('、')]);
      });
      if (reportRetry && unavailable.isNotEmpty) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(tr("部分信息仍未加载成功，请稍后重试"))));
      }
    } on ApiException catch (e) {
      if (!mounted || generation != _loadGeneration || status != _status) {
        return;
      }
      if (_conversations == null) {
        setState(() => _loadError = tr("对话记录加载失败，请重试"));
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(tr("刷新对话记录失败：{0}", [e.message]))),
        );
      }
    } catch (_) {
      if (!mounted || generation != _loadGeneration || status != _status) {
        return;
      }
      if (_conversations == null) {
        setState(() => _loadError = tr("对话记录加载失败，请检查网络后重试"));
      } else {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(tr("刷新对话记录失败，请检查网络后重试"))));
      }
    } finally {
      if (mounted && generation == _loadGeneration) {
        setState(() => _refreshing = false);
      }
    }
  }

  void _openConversation(
    int id,
    String title, {
    String teacherName = 'AI 老师',
    String teacherAvatarUrl = '',
    bool studentDeleted = false,
    String? studentDeletedAt,
  }) => Navigator.of(context).push(
    MaterialPageRoute(
      builder: (_) => ConversationDetailScreen(
        conversationId: id,
        title: title,
        teacherName: teacherName,
        teacherAvatarUrl: teacherAvatarUrl,
        studentDeleted: studentDeleted,
        studentDeletedAt: studentDeletedAt,
      ),
    ),
  );

  @override
  Widget build(BuildContext context) {
    AppLanguage.watch(context);
    return Scaffold(
      appBar: AppBar(
        title: Text(tr("{0} 的全部对话", [widget.studentName])),
        actions: [
          IconButton(
            tooltip: tr("刷新对话记录"),
            onPressed: _refreshing ? null : () => _load(reportRetry: true),
            icon: _refreshing
                ? const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.refresh),
          ),
        ],
      ),
      body: _conversations == null
          ? Center(
              child: _loadError == null
                  ? const CircularProgressIndicator()
                  : Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(trMessage(_loadError!)),
                        TextButton(
                          onPressed: () {
                            setState(() => _loadError = null);
                            _load();
                          },
                          child: Text(tr("重试")),
                        ),
                      ],
                    ),
            )
          : ListView(
              padding: const EdgeInsets.all(12),
              children: [
                _statusFilter(),
                _searchBar(),
                if (_supplementError != null)
                  Card(
                    child: ListTile(
                      leading: const Icon(Icons.info_outline),
                      title: Text(_supplementError!),
                      trailing: TextButton(
                        onPressed: _refreshing
                            ? null
                            : () => _load(reportRetry: true),
                        child: Text(tr("重试")),
                      ),
                    ),
                  ),
                if (_searchHits != null) ..._searchResults(),
                if (_summary != null) _summaryCard(),
                if (_usage != null) _usageCard(),
                if (_conversations!.isEmpty)
                  Padding(
                    padding: EdgeInsets.all(32),
                    child: Center(child: Text(tr("还没有对话记录"))),
                  ),
                ..._conversations!.map((c) {
                  final conv = c as Map<String, dynamic>;
                  final avatar = conv['teacher_avatar_url'] as String? ?? '';
                  return ListTile(
                    leading: _teacherAvatar(avatar),
                    title: Row(
                      children: [
                        Expanded(child: Text(conv['title'] as String? ?? '')),
                        if (conv['student_deleted'] == true)
                          Chip(
                            label: Text(
                              tr("孩子已删除"),
                              style: TextStyle(fontSize: 11),
                            ),
                          ),
                      ],
                    ),
                    subtitle: Text(
                      tr("{0} · {1}", [
                        conv['teacher_name'] ?? tr("AI 老师"),
                        (conv['created_at'] as String? ?? '').replaceAll(
                          'T',
                          ' ',
                        ),
                      ]),
                    ),
                    onTap: () => _openConversation(
                      conv['id'] as int,
                      conv['title'] as String? ?? '',
                      teacherName:
                          conv['teacher_name'] as String? ?? tr("AI 老师"),
                      teacherAvatarUrl:
                          conv['teacher_avatar_url'] as String? ?? '',
                      studentDeleted: conv['student_deleted'] == true,
                      studentDeletedAt: conv['student_deleted_at'] as String?,
                    ),
                  );
                }),
              ],
            ),
    );
  }

  Widget _teacherAvatar(String url) => CircleAvatar(
    child: url.isEmpty
        ? const Icon(Icons.school)
        : ClipOval(
            child: Image.network(
              url,
              width: 40,
              height: 40,
              fit: BoxFit.cover,
              errorBuilder: (_, __, ___) => const Icon(Icons.school),
            ),
          ),
  );

  Widget _statusFilter() => Row(
    children: [
      Text(tr("显示："), style: TextStyle(fontSize: 13)),
      DropdownButton<String>(
        value: _status,
        items: [
          DropdownMenuItem(value: 'all', child: Text(tr("全部"))),
          DropdownMenuItem(value: 'active', child: Text(tr("孩子未删除"))),
          DropdownMenuItem(value: 'deleted', child: Text(tr("孩子已删除"))),
        ],
        onChanged: (value) {
          if (value == null || value == _status) return;
          setState(() {
            _status = value;
            _conversations = null;
            _loadError = null;
            _searchHits = null;
          });
          _load();
        },
      ),
    ],
  );

  Widget _searchBar() {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: TextField(
        controller: _searchCtrl,
        decoration: InputDecoration(
          isDense: true,
          prefixIcon: const Icon(Icons.search, size: 20),
          hintText: tr("搜索消息内容（至少 2 字）"),
          border: const OutlineInputBorder(),
          suffixIcon: IconButton(
            icon: _searching
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.search),
            onPressed: _searching ? null : _doSearch,
          ),
        ),
        onSubmitted: (_) => _doSearch(),
      ),
    );
  }

  List<Widget> _searchResults() {
    return [
      Row(
        children: [
          Text(
            tr("搜索结果 {0} 条", [_searchHits!.length]),
            style: const TextStyle(fontSize: 12, color: Colors.grey),
          ),
          const Spacer(),
          TextButton(
            onPressed: () => setState(() => _searchHits = null),
            child: Text(tr("返回全部")),
          ),
        ],
      ),
      ..._searchHits!.map((hit) {
        final h = hit as Map<String, dynamic>;
        final isUser = h['role'] == 'user';
        return Card(
          child: ListTile(
            dense: true,
            leading: Icon(
              isUser ? Icons.person : Icons.smart_toy,
              size: 18,
              color: isUser ? const Color(0xFF1B2A4A) : const Color(0xFF15857A),
            ),
            title: Text(
              h['snippet'] as String? ?? '',
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontSize: 13),
            ),
            subtitle: Text(
              tr("会话: {0}", [h['title']]),
              style: const TextStyle(fontSize: 11),
            ),
            onTap: () => _openConversation(
              h['conversation_id'] as int,
              h['title'] as String? ?? '',
              teacherName: h['teacher_name'] as String? ?? tr("AI 老师"),
              teacherAvatarUrl: h['teacher_avatar_url'] as String? ?? '',
              studentDeleted: h['student_deleted'] == true,
            ),
          ),
        );
      }),
    ];
  }

  Widget _summaryCard() {
    final today = _summary!['today'];
    final week = _summary!['week'];
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(tr("学习摘要"), style: TextStyle(fontWeight: FontWeight.bold)),
            const SizedBox(height: 6),
            Text(
              tr("今日：提问 {0} 次 · 学习 {1} 次 · 引导 {2} 次 · 拦截 {3} 次 · 约 {4} 分钟", [
                today['questions'],
                today['study'],
                today['guided'],
                today['blocked'],
                today['minutes'],
              ]),
              style: const TextStyle(fontSize: 12),
            ),
            Text(
              tr("本周：提问 {0} 次 · 活跃 {1} 天 · 拦截 {2} 次 · 约 {3} 分钟", [
                week['questions'],
                week['active_days'],
                week['blocked'],
                week['minutes'],
              ]),
              style: const TextStyle(fontSize: 12, color: Colors.grey),
            ),
          ],
        ),
      ),
    );
  }

  Widget _usageCard() {
    final today = _usage!['today'];
    final total = _usage!['total'];
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              tr("AI 用量（估算成本）"),
              style: TextStyle(fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 4),
            Text(
              tr("今日：tokens {0}+{1}，约 ¥{2}", [
                today['tokens_in'],
                today['tokens_out'],
                today['cost'],
              ]),
              style: const TextStyle(fontSize: 12),
            ),
            Text(
              tr("累计：tokens {0}+{1}，约 ¥{2}", [
                total['tokens_in'],
                total['tokens_out'],
                total['cost'],
              ]),
              style: const TextStyle(fontSize: 12, color: Colors.grey),
            ),
          ],
        ),
      ),
    );
  }
}
