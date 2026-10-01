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
  String? _error;
  bool _markingRead = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    if (_data == null && _error != null && mounted) setState(() => _error = null);
    try {
      final d = await Api.I.notifications();
      if (mounted) setState(() { _data = d; _error = null; });
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } catch (_) {
      if (mounted) setState(() => _error = '通知加载失败，请检查网络后重试');
    }
  }

  Future<void> _readAll() async {
    if (_markingRead) return;
    setState(() => _markingRead = true);
    try {
      await Api.I.readAllNotifications();
      if (!mounted) return;
      setState(() {
        _data?['unread'] = 0;
        for (final item in _data?['items'] as List? ?? []) {
          item['is_read'] = true;
        }
      });
      await _load();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('已全部标为已读')),
        );
      }
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(e.message)),
        );
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('操作失败，请检查网络后重试')),
        );
      }
    } finally {
      if (mounted) setState(() => _markingRead = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final d = _data;
    return Scaffold(
      appBar: AppBar(
        title: const Text('通知'),
        actions: [
          TextButton(
            onPressed: d == null || d['unread'] == 0 || _markingRead ? null : _readAll,
            child: Text(_markingRead ? '处理中…' : '全部已读'),
          ),
        ],
      ),
      body: d == null
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
