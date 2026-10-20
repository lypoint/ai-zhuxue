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
  bool _loading = false;
  bool _markingRead = false;
  bool _unreadOnly = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    if (_loading) return;
    setState(() {
      _loading = true;
      if (_data == null) _error = null;
    });
    try {
      final d = await Api.I.notifications();
      if (mounted) {
        setState(() {
          _data = d;
          _error = null;
        });
      }
    } on ApiException catch (e) {
      if (mounted) {
        if (_data == null) {
          setState(() => _error = e.message);
        } else {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text(tr("刷新通知失败：{0}", [e.message]))),
          );
        }
      }
    } catch (_) {
      if (mounted) {
        if (_data == null) {
          setState(() => _error = tr("通知加载失败，请检查网络后重试"));
        } else {
          ScaffoldMessenger.of(
            context,
          ).showSnackBar(SnackBar(content: Text(tr("刷新通知失败，请检查网络后重试"))));
        }
      }
    } finally {
      if (mounted) setState(() => _loading = false);
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
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(tr("已全部标为已读"))));
      }
      await _load();
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
        ).showSnackBar(SnackBar(content: Text(tr("操作失败，请检查网络后重试"))));
      }
    } finally {
      if (mounted) setState(() => _markingRead = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    AppLanguage.watch(context);
    final d = _data;
    final items = (d?['items'] as List? ?? [])
        .where((n) => !_unreadOnly || n['is_read'] != true)
        .toList();
    return Scaffold(
      appBar: AppBar(
        title: Text(tr("通知")),
        actions: [
          IconButton(
            tooltip: tr("刷新通知"),
            onPressed: _loading || _markingRead ? null : _load,
            icon: _loading
                ? const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.refresh),
          ),
          TextButton(
            onPressed: d == null || d['unread'] == 0 || _markingRead
                ? null
                : _readAll,
            child: Text(_markingRead ? tr("处理中…") : tr("全部已读")),
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
                        Text(trMessage(_error!)),
                        TextButton(onPressed: _load, child: Text(tr("重试"))),
                      ],
                    ),
            )
          : Column(
              children: [
                SwitchListTile(
                  title: Text(tr("只看未读")),
                  value: _unreadOnly,
                  onChanged: (value) => setState(() => _unreadOnly = value),
                ),
                Expanded(
                  child: items.isEmpty
                      ? Center(child: Text(tr("暂无通知")))
                      : ListView.separated(
                          padding: const EdgeInsets.all(16),
                          itemCount: items.length,
                          separatorBuilder: (_, __) =>
                              const SizedBox(height: 12),
                          itemBuilder: (_, i) =>
                              _tile(items[i] as Map<String, dynamic>),
                        ),
                ),
              ],
            ),
    );
  }

  Widget _tile(Map<String, dynamic> n) {
    final isSec = n['type'] == 'security';
    final createdAt = displayDate(n['created_at']);
    return Card(
      color: !n['is_read']
          ? (isSec ? const Color(0xFFFDEDEC) : const Color(0xFFF0F7F5))
          : null,
      child: ListTile(
        leading: Icon(
          isSec
              ? Icons.gpp_maybe
              : n['type'] == 'system'
              ? Icons.info_outline
              : Icons.chat_bubble_outline,
          color: isSec ? Colors.red : const Color(0xFF15857A),
        ),
        title: Text(
          trMessage(n['title'] as String? ?? ''),
          style: TextStyle(
            fontWeight: n['is_read'] == true
                ? FontWeight.normal
                : FontWeight.bold,
            color: isSec ? Colors.red : null,
          ),
        ),
        subtitle: Text(
          '${trMessage(n['body'] as String? ?? '')}\n${n['is_read'] == true ? tr("已读") : tr("未读")} · $createdAt',
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
                    title: tr("相关对话"),
                  ),
                ),
              )
            : null,
      ),
    );
  }
}
