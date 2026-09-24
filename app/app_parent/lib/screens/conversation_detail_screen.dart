import 'package:flutter/material.dart';
import 'package:app_core/app_core.dart';
import 'package:gpt_markdown/gpt_markdown.dart';
import '../constants/fence_labels.dart';

/// 单个会话详情：逐条消息 + 每条消息的围栏判定流水（家长审查）。
class ConversationDetailScreen extends StatefulWidget {
  final int conversationId;
  final String title;
  const ConversationDetailScreen({
    super.key,
    required this.conversationId,
    required this.title,
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
      appBar: AppBar(title: Text(widget.title)),
      body: _messages == null
          ? const Center(child: CircularProgressIndicator())
          : ListView.builder(
              padding: const EdgeInsets.all(12),
              itemCount: _messages!.length,
              itemBuilder: (_, i) =>
                  _messageTile(_messages![i] as Map<String, dynamic>),
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
        if (action != null)
          Padding(
            padding: const EdgeInsets.only(left: 8, bottom: 6),
            child: Text(
              '围栏：${fenceDecisionLabel[action] ?? action} · ${events.map((e) => "${fenceStageLabel[e['stage']] ?? e['stage']}/${fenceCategoryLabel[e['category']] ?? e['category']}").join(' → ')}',
              style: TextStyle(fontSize: 11, color: Colors.grey.shade600),
            ),
          ),
      ],
    );
  }
}
