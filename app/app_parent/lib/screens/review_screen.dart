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

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _doSearch() async {
    final q = _searchCtrl.text.trim();
    if (q.length < 2) return;
    try {
      final hits = await Api.I.searchConversations(widget.studentId, q);
      if (!mounted) return;
      setState(() => _searchHits = hits);
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  Future<void> _load() async {
    final list = await Api.I.conversations(widget.studentId);
    Map<String, dynamic>? usage;
    Map<String, dynamic>? summary;
    try {
      usage = await Api.I.studentUsage(widget.studentId);
    } on ApiException {
      usage = null;
    }
    try {
      summary = await Api.I.studentSummary(widget.studentId);
    } on ApiException {
      summary = null;
    }
    if (!mounted) return;
    setState(() {
      _conversations = list;
      _usage = usage;
      _summary = summary;
    });
  }

  void _openConversation(int id, String title) => Navigator.of(context).push(
    MaterialPageRoute(
      builder: (_) =>
          ConversationDetailScreen(conversationId: id, title: title),
    ),
  );

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text('${widget.studentName} 的全部对话')),
      body: _conversations == null
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(12),
              children: [
                _searchBar(),
                if (_searchHits != null) ..._searchResults(),
                if (_summary != null) _summaryCard(),
                if (_usage != null) _usageCard(),
                if (_conversations!.isEmpty)
                  const Padding(
                    padding: EdgeInsets.all(32),
                    child: Center(child: Text('还没有对话记录')),
                  ),
                ..._conversations!.map((c) {
                  final conv = c as Map<String, dynamic>;
                  return ListTile(
                    leading: const Icon(Icons.forum),
                    title: Text(conv['title'] as String? ?? ''),
                    subtitle: Text(
                      (conv['created_at'] as String? ?? '').replaceAll('T', ' '),
                    ),
                    onTap: () => _openConversation(
                      conv['id'] as int,
                      conv['title'] as String? ?? '',
                    ),
                  );
                }),
              ],
            ),
    );
  }

  Widget _searchBar() {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: TextField(
        controller: _searchCtrl,
        decoration: InputDecoration(
          isDense: true,
          prefixIcon: const Icon(Icons.search, size: 20),
          hintText: '搜索消息内容（至少 2 字）',
          border: const OutlineInputBorder(),
          suffixIcon: IconButton(
            icon: const Icon(Icons.search),
            onPressed: _doSearch,
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
            '搜索结果 ${_searchHits!.length} 条',
            style: const TextStyle(fontSize: 12, color: Colors.grey),
          ),
          const Spacer(),
          TextButton(
            onPressed: () => setState(() => _searchHits = null),
            child: const Text('返回全部'),
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
              '会话: ${h['title']}',
              style: const TextStyle(fontSize: 11),
            ),
            onTap: () => _openConversation(
              h['conversation_id'] as int,
              h['title'] as String? ?? '',
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
            const Text('学习摘要', style: TextStyle(fontWeight: FontWeight.bold)),
            const SizedBox(height: 6),
            Text(
              '今日：提问 ${today['questions']} 次 · 学习 ${today['study']} 次 · 引导 ${today['guided']} 次 · 拦截 ${today['blocked']} 次 · 约 ${today['minutes']} 分钟',
              style: const TextStyle(fontSize: 12),
            ),
            Text(
              '本周：提问 ${week['questions']} 次 · 活跃 ${week['active_days']} 天 · 拦截 ${week['blocked']} 次 · 约 ${week['minutes']} 分钟',
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
            const Text(
              'AI 用量（估算成本）',
              style: TextStyle(fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 4),
            Text(
              '今日：tokens ${today['tokens_in']}+${today['tokens_out']}，约 ¥${today['cost']}',
              style: const TextStyle(fontSize: 12),
            ),
            Text(
              '累计：tokens ${total['tokens_in']}+${total['tokens_out']}，约 ¥${total['cost']}',
              style: const TextStyle(fontSize: 12, color: Colors.grey),
            ),
          ],
        ),
      ),
    );
  }
}
