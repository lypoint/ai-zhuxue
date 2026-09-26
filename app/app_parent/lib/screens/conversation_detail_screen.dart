import 'package:flutter/material.dart';
import 'package:app_core/app_core.dart';
import 'package:gpt_markdown/gpt_markdown.dart';
import '../constants/fence_labels.dart';

/// 单个会话详情：逐条消息 + 每条消息的围栏判定流水（家长审查）。
class ConversationDetailScreen extends StatefulWidget {
  final int conversationId;
  final String title;
  final String teacherName;
  final String teacherAvatarUrl;
  final bool studentDeleted;
  final String? studentDeletedAt;
  const ConversationDetailScreen({
    super.key,
    required this.conversationId,
    required this.title,
    this.teacherName = 'AI 老师',
    this.teacherAvatarUrl = '',
    this.studentDeleted = false,
    this.studentDeletedAt,
  });
  @override
  State<ConversationDetailScreen> createState() =>
      _ConversationDetailScreenState();
}

class _ConversationDetailScreenState extends State<ConversationDetailScreen> {
  List<dynamic>? _messages;
  Map<int, List<dynamic>>? _fenceByMessage;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final messages = await Api.I.messages(widget.conversationId);
    final events = await Api.I.fenceEvents(widget.conversationId);
    final byMsg = <int, List<dynamic>>{};
    for (final e in events) {
      final mid = e['message_id'] as int?;
      if (mid != null) (byMsg[mid] ??= []).add(e);
    }
    setState(() {
      _messages = messages;
      _fenceByMessage = byMsg;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Row(
          children: [
            CircleAvatar(
              radius: 14,
              child: widget.teacherAvatarUrl.isEmpty
                  ? const Icon(Icons.school, size: 16)
                  : ClipOval(
                      child: Image.network(
                        widget.teacherAvatarUrl,
                        width: 28,
                        height: 28,
                        fit: BoxFit.cover,
                        errorBuilder: (_, __, ___) =>
                            const Icon(Icons.school, size: 16),
                      ),
                    ),
            ),
            const SizedBox(width: 8),
            Expanded(child: Text('${widget.teacherName} · ${widget.title}')),
          ],
        ),
      ),
      body: _messages == null
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(12),
              children: [
                if (widget.studentDeleted)
                  Card(
                    color: const Color(0xFFFFF4E5),
                    child: ListTile(
                      leading: const Icon(Icons.delete_outline),
                      title: const Text('孩子已删除此会话'),
                      subtitle: Text(
                        '删除时间：${widget.studentDeletedAt ?? '未知'} · 内容仍按家庭审查规则保留',
                      ),
                    ),
                  ),
                ..._messages!.map(
                  (m) => _messageTile(m as Map<String, dynamic>),
                ),
              ],
            ),
    );
  }

  Widget _messageTile(Map<String, dynamic> m) {
    final isUser = m['role'] == 'user';
    final events = _fenceByMessage![m['id'] as int] ?? const [];
    final action = m['fence_action'] as String?;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Align(
          alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
          child: Container(
            margin: const EdgeInsets.symmetric(vertical: 4),
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            constraints: BoxConstraints(
              maxWidth: MediaQuery.of(context).size.width * 0.78,
            ),
            decoration: BoxDecoration(
              color: isUser ? const Color(0xFF1B2A4A) : Colors.grey.shade200,
              borderRadius: BorderRadius.circular(14),
            ),
            child: isUser
                ? Text(
                    m['content'] as String? ?? '',
                    style: const TextStyle(color: Colors.white),
                  )
                : GptMarkdown(
                    m['content'] as String? ?? '',
                    style: const TextStyle(color: Colors.black87, height: 1.4),
                    useDollarSignsForLatex: true,
                  ),
          ),
        ),
        if (action != null && action != 'allow')
          Padding(
            padding: const EdgeInsets.only(left: 8, bottom: 6),
            child: Wrap(
              crossAxisAlignment: WrapCrossAlignment.center,
              spacing: 8,
              children: [
                Text(
                  '围栏：${fenceDecisionLabel[action] ?? action} · ${events.map((e) => "${fenceStageLabel[e['stage']] ?? e['stage']}/${fenceCategoryLabel[e['category']] ?? e['category']}").join(' → ')}',
                  style: TextStyle(fontSize: 11, color: Colors.grey.shade600),
                ),
                TextButton(
                  onPressed: () => _reportFalsePositive(m['id'] as int, events),
                  style: TextButton.styleFrom(
                    padding: const EdgeInsets.symmetric(horizontal: 4),
                    minimumSize: const Size(0, 28),
                  ),
                  child: const Text('反馈误判', style: TextStyle(fontSize: 11)),
                ),
              ],
            ),
          ),
      ],
    );
  }

  Future<void> _reportFalsePositive(int messageId, List<dynamic> events) async {
    try {
      await Api.I.submitFenceFeedback(
        widget.conversationId,
        messageId: messageId,
        eventId: events.isEmpty ? null : events.first['id'] as int?,
      );
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('已提交误判反馈，感谢帮助我们改进')));
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }
}
