import 'package:flutter/material.dart';
import 'package:app_core/app_core.dart';
import 'conversation_detail_screen.dart';

/// 通知中心（P0 安全闭环）：security 安全告警置顶标红。
class NotificationsScreen extends StatefulWidget {
  const NotificationsScreen({super.key});
  @override
  State<NotificationsScreen> createState() => _NotificationsScreenState();
}

class _NotificationsScreenState extends State<NotificationsScreen> {
  Map<String, dynamic>? _data;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final d = await Api.I.notifications();
    if (!mounted) return;
    setState(() => _data = d);
  }

  Future<void> _readAll() async {
    await Api.I.readAllNotifications();
    _load();
  }

  @override
  Widget build(BuildContext context) {
    final d = _data;
    return Scaffold(
      appBar: AppBar(
        title: const Text('通知'),
        actions: [
          TextButton(
            onPressed: d == null || d['unread'] == 0 ? null : _readAll,
            child: const Text('全部已读'),
          ),
        ],
      ),
      body: d == null
          ? const Center(child: CircularProgressIndicator())
          : d['total'] == 0
          ? const Center(child: Text('暂无通知'))
          : ListView.builder(
              padding: const EdgeInsets.all(12),
              itemCount: (d['items'] as List).length,
              itemBuilder: (_, i) =>
                  _tile(d['items'][i] as Map<String, dynamic>),
            ),
    );
  }

  Widget _tile(Map<String, dynamic> n) {
    final isSec = n['type'] == 'security';
    return Card(
      color: !n['is_read']
          ? (isSec ? const Color(0xFFFDEDEC) : const Color(0xFFF0F7F5))
          : null,
      child: ListTile(
        leading: Icon(
          isSec ? Icons.gpp_maybe : Icons.chat_bubble_outline,
          color: isSec ? Colors.red : const Color(0xFF15857A),
        ),
        title: Text(
          n['title'] as String? ?? '',
          style: TextStyle(
            fontWeight: n['is_read'] == true
                ? FontWeight.normal
                : FontWeight.bold,
            color: isSec ? Colors.red : null,
          ),
        ),
        subtitle: Text(
          '${n['body'] ?? ''}\n${(n['created_at'] ?? '').toString().replaceAll('T', ' ').substring(0, 16)}',
          style: const TextStyle(fontSize: 12),
        ),
        isThreeLine: true,
        trailing: n['conversation_id'] != null
            ? const Icon(Icons.chevron_right, size: 18)
            : null,
        onTap: n['conversation_id'] != null
            ? () => Navigator.of(context).push(
                MaterialPageRoute(
                  builder: (_) => ConversationDetailScreen(
                    conversationId: n['conversation_id'] as int,
                    title: '相关对话',
                  ),
                ),
              )
            : null,
      ),
    );
  }
}
