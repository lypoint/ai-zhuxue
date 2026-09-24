import 'package:flutter/material.dart';

/// 会话抽屉（Codex 风格）：新对话、搜索、快捷入口，以及历史会话列表。
/// 所有交互通过回调上抛给 ChatScreen 处理（网络/状态副作用留在 State 中）。
class ChatDrawer extends StatelessWidget {
  final List<dynamic>? sessions;
  final List<dynamic> filteredSessions;
  final String search;
  final int? currentConversationId;
  final VoidCallback onNewChat;
  final ValueChanged<String> onSearchChanged;
  final VoidCallback onOpenStats;
  final VoidCallback onOpenFavorites;
  final VoidCallback onLogout;
  final ValueChanged<int> onOpenSession;
  final ValueChanged<Map<String, dynamic>> onSessionMenu;

  const ChatDrawer({
    super.key,
    required this.sessions,
    required this.filteredSessions,
    required this.search,
    required this.currentConversationId,
    required this.onNewChat,
    required this.onSearchChanged,
    required this.onOpenStats,
    required this.onOpenFavorites,
    required this.onLogout,
    required this.onOpenSession,
    required this.onSessionMenu,
  });

  @override
  Widget build(BuildContext context) {
    return Drawer(
      child: SafeArea(
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
              child: FilledButton.icon(
                onPressed: onNewChat,
                icon: const Icon(Icons.add),
                label: const Text('新对话'),
              ),
            ),
            const Divider(height: 1),
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 8, 12, 4),
              child: TextField(
                decoration: const InputDecoration(
                  isDense: true,
                  prefixIcon: Icon(Icons.search, size: 20),
                  hintText: '搜索会话',
                  border: OutlineInputBorder(),
                ),
                onChanged: (v) => onSearchChanged(v.trim()),
              ),
            ),
            const Divider(height: 1),
            ListTile(
              leading: const Icon(Icons.insights),
              title: const Text('我的学习统计'),
              onTap: onOpenStats,
            ),
            ListTile(
              leading: const Icon(Icons.star_border),
              title: const Text('我的收藏'),
              onTap: onOpenFavorites,
            ),
            ListTile(
              leading: const Icon(Icons.logout),
              title: const Text('退出登录'),
              onTap: onLogout,
            ),
            Expanded(child: _sessionList()),
          ],
        ),
      ),
    );
  }

  Widget _sessionList() {
    if (sessions == null) {
      return const Center(child: CircularProgressIndicator());
    }
    if (filteredSessions.isEmpty) {
      return Center(child: Text(search.isEmpty ? '还没有聊天记录' : '没有匹配的会话'));
    }
    return ListView.builder(
      itemCount: filteredSessions.length,
      itemBuilder: (_, i) {
        final c = filteredSessions[i] as Map<String, dynamic>;
        final selected = c['conversation_id'] == currentConversationId;
        final lastTime = (c['last_time'] ?? '')
            .toString()
            .replaceAll('T', ' ')
            .sliceSafe(0, 16);
        return ListTile(
          selected: selected,
          leading: Icon(
            selected ? Icons.chat_bubble : Icons.chat_bubble_outline,
            size: 20,
          ),
          title: Row(
            children: [
              if (c['pinned'] == true) ...[
                const Icon(Icons.push_pin, size: 13, color: Color(0xFF15857A)),
                const SizedBox(width: 4),
              ],
              Expanded(
                child: Text(
                  c['title'] as String? ?? '',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
          ),
          subtitle: Text(
            '${c['message_count']} 条 · $lastTime',
            style: const TextStyle(fontSize: 11),
          ),
          onTap: () => onOpenSession(c['conversation_id'] as int),
          onLongPress: () => onSessionMenu(c),
        );
      },
    );
  }
}

extension _SliceSafe on String {
  String sliceSafe(int start, int end) =>
      length <= start ? '' : substring(start, end > length ? length : end);
}
