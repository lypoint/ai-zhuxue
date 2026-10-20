import 'package:app_core/app_core.dart';
import 'package:flutter/material.dart';

/// 会话抽屉（Codex 风格）：新对话、搜索、快捷入口，以及历史会话列表。
/// 所有交互通过回调上抛给 ChatScreen 处理（网络/状态副作用留在 State 中）。
class ChatDrawer extends StatelessWidget {
  final List<dynamic>? sessions;
  final String? sessionsError;
  final List<dynamic> filteredSessions;
  final String search;
  final int? currentConversationId;
  final VoidCallback onNewChat;
  final ValueChanged<String> onSearchChanged;
  final VoidCallback onOpenStats;
  final VoidCallback onOpenFavorites;
  final VoidCallback onOpenReports;
  final VoidCallback onOpenGrades;
  final VoidCallback onLogout;
  final VoidCallback? onDeleteAccount;
  final ValueChanged<int> onOpenSession;
  final ValueChanged<Map<String, dynamic>> onSessionMenu;
  final VoidCallback onRetrySessions;

  const ChatDrawer({
    super.key,
    required this.sessions,
    required this.sessionsError,
    required this.filteredSessions,
    required this.search,
    required this.currentConversationId,
    required this.onNewChat,
    required this.onSearchChanged,
    required this.onOpenStats,
    required this.onOpenFavorites,
    required this.onOpenReports,
    required this.onOpenGrades,
    required this.onLogout,
    this.onDeleteAccount,
    required this.onOpenSession,
    required this.onSessionMenu,
    required this.onRetrySessions,
  });

  @override
  Widget build(BuildContext context) {
    AppLanguage.watch(context);
    return Drawer(
      child: SafeArea(
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 20, 20, 12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    tr("我的学习空间"),
                    style: TextStyle(fontSize: 22, fontWeight: FontWeight.w800),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    tr("每一个问题，都是进步的开始"),
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.onSurfaceVariant,
                      fontSize: 12,
                    ),
                  ),
                  const SizedBox(height: 20),
                  FilledButton.icon(
                    onPressed: onNewChat,
                    icon: const Icon(Icons.add),
                    label: Text(tr("新对话")),
                  ),
                ],
              ),
            ),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 12),
                child: CustomScrollView(
                  slivers: [
                    SliverToBoxAdapter(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Padding(
                            padding: EdgeInsets.fromLTRB(8, 8, 8, 12),
                            child: Text(
                              tr("学习工具"),
                              style: TextStyle(fontWeight: FontWeight.w700),
                            ),
                          ),
                          LayoutBuilder(
                            builder: (context, constraints) => Wrap(
                              spacing: 8,
                              runSpacing: 8,
                              children: [
                                for (final item in [
                                  (
                                    Icons.insights_outlined,
                                    tr("我的学习统计"),
                                    onOpenStats,
                                  ),
                                  (
                                    Icons.bookmark_border_rounded,
                                    tr("我的收藏"),
                                    onOpenFavorites,
                                  ),
                                  (
                                    Icons.school_outlined,
                                    tr("成绩与评估"),
                                    onOpenGrades,
                                  ),
                                  (
                                    Icons.flag_outlined,
                                    tr("我的举报"),
                                    onOpenReports,
                                  ),
                                ])
                                  SizedBox(
                                    width: constraints.maxWidth,
                                    child: Material(
                                      color: Colors.white,
                                      borderRadius: BorderRadius.circular(16),
                                      child: InkWell(
                                        borderRadius: BorderRadius.circular(16),
                                        onTap: item.$3,
                                        child: Padding(
                                          padding: const EdgeInsets.all(12),
                                          child: Row(
                                            children: [
                                              Icon(
                                                item.$1,
                                                color: Theme.of(
                                                  context,
                                                ).colorScheme.primary,
                                              ),
                                              const SizedBox(width: 8),
                                              Expanded(
                                                child: Text(
                                                  item.$2,
                                                  style: const TextStyle(
                                                    fontSize: 13,
                                                  ),
                                                ),
                                              ),
                                            ],
                                          ),
                                        ),
                                      ),
                                    ),
                                  ),
                              ],
                            ),
                          ),
                          Padding(
                            padding: EdgeInsets.fromLTRB(8, 24, 8, 12),
                            child: Text(
                              tr("聊天记录"),
                              style: TextStyle(fontWeight: FontWeight.w700),
                            ),
                          ),
                          TextField(
                            decoration: InputDecoration(
                              isDense: true,
                              prefixIcon: Icon(Icons.search, size: 20),
                              hintText: tr("搜索会话"),
                            ),
                            onChanged: (v) => onSearchChanged(v.trim()),
                          ),
                          const SizedBox(height: 12),
                        ],
                      ),
                    ),
                    _sessionList(),
                    const SliverToBoxAdapter(child: SizedBox(height: 16)),
                  ],
                ),
              ),
            ),
            const Divider(height: 1),
            ListTile(
              leading: const Icon(Icons.manage_accounts_outlined, size: 20),
              title: Text(tr('账号与设置')),
              trailing: const LanguageButton(),
              onTap: () async {
                final action = await showModalBottomSheet<String>(
                  context: context,
                  builder: (ctx) => SafeArea(
                    child: Wrap(
                      children: [
                        ListTile(
                          leading: const Icon(Icons.logout),
                          title: Text(tr('退出登录')),
                          onTap: () => Navigator.pop(ctx, 'logout'),
                        ),
                        if (onDeleteAccount != null)
                          ListTile(
                            leading: Icon(
                              Icons.person_remove_outlined,
                              color: Theme.of(ctx).colorScheme.error,
                            ),
                            title: Text(tr('删除账号')),
                            onTap: () => Navigator.pop(ctx, 'delete'),
                          ),
                      ],
                    ),
                  ),
                );
                if (!context.mounted) return;
                if (action == 'logout') onLogout();
                if (action == 'delete') onDeleteAccount?.call();
              },
            ),
          ],
        ),
      ),
    );
  }

  Widget _sessionList() {
    if (sessions == null) {
      return SliverToBoxAdapter(
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 24),
          child: Center(
            child: sessionsError == null
                ? const CircularProgressIndicator()
                : Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(sessionsError!),
                      TextButton(
                        onPressed: onRetrySessions,
                        child: Text(tr("重试")),
                      ),
                    ],
                  ),
          ),
        ),
      );
    }
    if (filteredSessions.isEmpty) {
      return SliverToBoxAdapter(
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 24),
          child: Center(
            child: Text(search.isEmpty ? tr("还没有聊天记录") : tr("没有匹配的会话")),
          ),
        ),
      );
    }
    return SliverList.builder(
      itemCount: filteredSessions.length,
      itemBuilder: (_, i) {
        final c = filteredSessions[i] as Map<String, dynamic>;
        final selected = c['conversation_id'] == currentConversationId;
        final lastTime = displayDate(c['last_time']);
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
            tr("{0} 条 · {1}", [c['message_count'], lastTime]),
            style: const TextStyle(fontSize: 11),
          ),
          onTap: () => onOpenSession(c['conversation_id'] as int),
          onLongPress: () => onSessionMenu(c),
        );
      },
    );
  }
}
