import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:app_core/app_core.dart';
import '../models/bubble.dart';
import '../widgets/chat_drawer.dart';
import '../widgets/message_bubble.dart';
import 'bind_screen.dart';
import 'favorites_screen.dart';
import 'my_stats_screen.dart';
import 'grades_screen.dart';

/// 学习聊天页：流式对话、会话抽屉、心跳时长上报、消息收藏与政策拦截提示。
class ChatScreen extends StatefulWidget {
  const ChatScreen({super.key});
  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final _inputCtrl = TextEditingController();
  final _scrollCtrl = ScrollController();
  final List<Bubble> _bubbles = [];
  int? _conversationId;
  bool _sending = false;
  List<dynamic>? _sessions;
  List<dynamic>? _teachers;
  int? _teacherId;
  String _teacherName = 'AI 学习助手';
  String _search = '';
  Timer? _hbTimer;

  /// 真实使用时长：聊天页每 60 秒上报一次心跳（P1 时长管控数据源）
  void _startHeartbeat() {
    _hbTimer?.cancel();
    _hbTimer = Timer.periodic(const Duration(seconds: 60), (_) {
      if (_sending) return;
      Api.I.heartbeat(60).catchError((_) {}); // 失败静默，下个周期再报
    });
  }

  @override
  void dispose() {
    _hbTimer?.cancel();
    super.dispose();
  }

  @override
  void initState() {
    super.initState();
    _restore();
    _loadTeachers();
    _startHeartbeat();
  }

  Future<void> _loadTeachers() async {
    try {
      final teachers = await Api.I.teachers();
      if (mounted) {
        setState(() {
          _teachers = teachers;
          // The first CMS-sorted teacher is the family default for a new chat.
          if (_conversationId == null && teachers.isNotEmpty) {
            final teacher = (teachers.cast<Map<String, dynamic>>().firstWhere(
              (item) => item['access'] == 'available',
              orElse: () => teachers.first as Map<String, dynamic>,
            ));
            _teacherId = teacher['teacher_id'] as int?;
            _teacherName = teacher['name'] as String? ?? 'AI 学习助手';
          }
        });
      }
    } catch (_) {}
  }

  Future<void> _chooseTeacher() async {
    final selected = await showModalBottomSheet<Map<String, dynamic>>(
      context: context,
      builder: (ctx) => SafeArea(
        child: ListView(
          shrinkWrap: true,
          children: [
            const ListTile(
              title: Text(
                '选择老师',
                style: TextStyle(fontWeight: FontWeight.w700),
              ),
            ),
            ...(_teachers ?? const []).map((raw) {
              final teacher = raw as Map<String, dynamic>;
              final available = teacher['access'] == 'available';
              final access = teacher['access'] as String?;
              return ListTile(
                enabled: available,
                leading: _teacherAvatar(teacher['avatar_url'] as String? ?? ''),
                title: Text(teacher['name'] as String? ?? 'AI 老师'),
                trailing: available
                    ? null
                    : Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          const Icon(Icons.lock_outline, size: 18),
                          const SizedBox(width: 4),
                          Text(
                            access == 'daily_free_exhausted'
                                ? '今日次数已用完'
                                : '需订阅',
                            style: const TextStyle(fontSize: 12),
                          ),
                        ],
                      ),
                onTap: available ? () => Navigator.of(ctx).pop(teacher) : null,
              );
            }),
          ],
        ),
      ),
    );
    if (selected == null || !mounted) return;
    if (_conversationId != null) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('老师只在新对话开始时生效')));
      return;
    }
    setState(() {
      _teacherId = selected['teacher_id'] as int?;
      _teacherName = selected['name'] as String? ?? 'AI 学习助手';
    });
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

  Future<void> _restore() async {
    try {
      final data = await Api.I.latestConversation();
      final convId = data['conversation_id'] as int?;
      final msgs = (data['messages'] as List?) ?? const [];
      if (convId != null && msgs.isNotEmpty && mounted) {
        setState(() {
          _conversationId = convId;
          _teacherId = data['teacher_id'] as int?;
          _teacherName = data['teacher_name'] as String? ?? _teacherName;
          for (final m in msgs) {
            _bubbles.add(Bubble(m['role'] as String, m['content'] as String));
          }
        });
      }
    } catch (_) {
      // 恢复失败（网络/服务不可用）不影响新对话
    }
    _loadSessions();
  }

  Future<void> _loadSessions() async {
    try {
      final list = await Api.I.sessions();
      if (mounted) setState(() => _sessions = list);
    } catch (_) {
      // 列表加载失败不阻塞聊天
    }
  }

  /// 新建对话：清空当前气泡（历史仍在抽屉里，随时切回）
  void _newChat() {
    Navigator.of(context).pop(); // 关抽屉
    setState(() {
      _conversationId = null;
      _bubbles.clear();
    });
    _loadSessions();
  }

  /// 从抽屉载入历史会话
  Future<void> _openSession(int conversationId) async {
    Navigator.of(context).pop();
    try {
      final msgs = await Api.I.conversationMessages(conversationId);
      if (!mounted) return;
      Map<String, dynamic>? session;
      for (final item in (_sessions ?? const [])) {
        if (item is Map<String, dynamic> &&
            item['conversation_id'] == conversationId) {
          session = item;
          break;
        }
      }
      setState(() {
        _conversationId = conversationId;
        _teacherId = session?['teacher_id'] as int?;
        _teacherName = session?['teacher_name'] as String? ?? _teacherName;
        _bubbles.clear();
        for (final m in msgs) {
          _bubbles.add(
            Bubble(
              m['role'] as String,
              m['content'] as String,
              messageId: m['id'] as int?,
            ),
          );
        }
      });
      _scrollToBottom();
    } on ApiException catch (e) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  /// 消息长按菜单：复制 / 收藏（P2 学习沉淀）
  Future<void> _messageMenu(Bubble b) async {
    final action = await showModalBottomSheet<String>(
      context: context,
      builder: (ctx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: const Icon(Icons.copy),
              title: const Text('复制全文（含公式源码）'),
              onTap: () => Navigator.of(ctx).pop('copy'),
            ),
            ListTile(
              leading: const Icon(Icons.star_border),
              title: const Text('收藏'),
              onTap: () => Navigator.of(ctx).pop('favorite'),
            ),
          ],
        ),
      ),
    );
    if (!mounted || action == null) return;
    if (action == 'copy') {
      await Clipboard.setData(ClipboardData(text: b.text));
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('已复制到剪贴板'),
            duration: Duration(seconds: 1),
          ),
        );
      }
    } else if (action == 'favorite') {
      if (b.messageId == null) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('该消息暂不支持收藏'),
            duration: Duration(seconds: 1),
          ),
        );
        return;
      }
      try {
        await Api.I.addFavorite(b.messageId!);
        if (mounted) {
          ScaffoldMessenger.of(
            context,
          ).showSnackBar(const SnackBar(content: Text('已收藏 ⭐ 可在抽屉「我的收藏」查看')));
        }
      } on ApiException catch (e) {
        if (mounted) {
          ScaffoldMessenger.of(
            context,
          ).showSnackBar(SnackBar(content: Text(e.message)));
        }
      }
    }
  }

  /// 时段/时长/订阅拦截的全屏友好提示（比错误气泡更适合低龄用户）
  Future<void> _policyDialog(ApiException e) async {
    final (title, icon) = switch (e.status) {
      423 => ('休息时间到啦', Icons.bedtime),
      429 => ('今天的时间用完了', Icons.schedule),
      402 => ('需要家长续费', Icons.favorite_border),
      _ => ('提示', Icons.info_outline),
    };
    if (!mounted) return;
    await showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        icon: Icon(icon, size: 40, color: const Color(0xFF15857A)),
        title: Text(title),
        content: Text(e.message, textAlign: TextAlign.center),
        actions: [
          FilledButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('好的'),
          ),
        ],
      ),
    );
  }

  List<dynamic> get _filteredSessions {
    final all = _sessions ?? const [];
    if (_search.isEmpty) return all;
    return all
        .where(
          (e) => (e as Map<String, dynamic>)['title']
              .toString()
              .toLowerCase()
              .contains(_search.toLowerCase()),
        )
        .toList();
  }

  /// 抽屉长按菜单：重命名 / 置顶 / 删除（Codex 风格会话管理）
  Future<void> _sessionMenu(Map<String, dynamic> c) async {
    final cid = c['conversation_id'] as int;
    final action = await showModalBottomSheet<String>(
      context: context,
      builder: (ctx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: const Icon(Icons.edit),
              title: const Text('重命名'),
              onTap: () => Navigator.of(ctx).pop('rename'),
            ),
            ListTile(
              leading: Icon(
                c['pinned'] == true ? Icons.push_pin_outlined : Icons.push_pin,
              ),
              title: Text(c['pinned'] == true ? '取消置顶' : '置顶'),
              onTap: () => Navigator.of(ctx).pop('pin'),
            ),
            ListTile(
              leading: const Icon(Icons.delete_outline, color: Colors.red),
              title: const Text('删除会话', style: TextStyle(color: Colors.red)),
              onTap: () => Navigator.of(ctx).pop('delete'),
            ),
          ],
        ),
      ),
    );
    if (!mounted || action == null) return;
    if (action == 'rename') {
      await _renameSession(cid, c['title'] as String? ?? '');
    } else if (action == 'pin') {
      await _pinSession(cid, c['pinned'] != true);
    } else if (action == 'delete') {
      await _deleteSession(cid);
    }
  }

  Future<void> _renameSession(int cid, String current) async {
    final ctrl = TextEditingController(text: current);
    final title = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('重命名会话'),
        content: TextField(
          controller: ctrl,
          autofocus: true,
          maxLength: 100,
          decoration: const InputDecoration(hintText: '会话标题'),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(ctx).pop(ctrl.text.trim()),
            child: const Text('保存'),
          ),
        ],
      ),
    );
    if (title == null || title.isEmpty || !mounted) return;
    await _guard(() => Api.I.renameSession(cid, title));
  }

  Future<void> _pinSession(int cid, bool pinned) =>
      _guard(() => Api.I.pinSession(cid, pinned));

  Future<void> _deleteSession(int cid) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('删除会话？'),
        content: const Text('该会话会从孩子端隐藏，家长仍可在审查记录中查看。此操作不可撤销。'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('取消'),
          ),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: Colors.red),
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('删除'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    if (_conversationId == cid) {
      setState(() {
        _conversationId = null;
        _bubbles.clear();
      });
    }
    await _guard(() => Api.I.deleteSession(cid));
  }

  /// 会话管理请求统一包裹：成功刷新列表，失败弹提示。
  Future<void> _guard(Future<void> Function() action) async {
    try {
      await action();
      await _loadSessions();
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollCtrl.hasClients) {
        _scrollCtrl.animateTo(
          _scrollCtrl.position.maxScrollExtent,
          duration: const Duration(milliseconds: 200),
          curve: Curves.easeOut,
        );
      }
    });
  }

  Future<void> _send() async {
    final text = _inputCtrl.text.trim();
    if (text.isEmpty || _sending) return;
    _inputCtrl.clear();
    setState(() {
      _sending = true;
      _bubbles.add(Bubble('user', text));
      _bubbles.add(Bubble('assistant', '')); // 流式占位，逐段填充
    });
    _scrollToBottom();
    void updateLast(String text) {
      setState(() {
        _bubbles[_bubbles.length - 1] = Bubble('assistant', text);
      });
    }

    try {
      final done = await Api.I.sendChatStream(
        _conversationId,
        text,
        teacherId: _conversationId == null ? _teacherId : null,
        onMeta: (meta) => _conversationId =
            meta['conversation_id'] as int? ?? _conversationId,
        onDelta: (delta) {
          updateLast(_bubbles.last.text + delta);
          _scrollToBottom();
        },
      );
      if (_bubbles.last.text.isEmpty) updateLast('（没有收到内容）');
      final mid = done['message_id'] as int?;
      if (mid != null) {
        _bubbles[_bubbles.length - 1] = Bubble(
          'assistant',
          _bubbles.last.text,
          messageId: mid,
        );
      }
      _loadSessions();
    } on ApiException catch (e) {
      updateLast('⚠️ ${e.message}');
      if (e.status == 401 && mounted) {
        await showDialog<void>(
          context: context,
          builder: (ctx) => AlertDialog(
            title: const Text('设备已重新绑定'),
            content: Text(e.message),
            actions: [
              FilledButton(
                onPressed: () => Navigator.of(ctx).pop(),
                child: const Text('重新绑定'),
              ),
            ],
          ),
        );
        await Api.I.logout();
        if (mounted) {
          Navigator.of(context).pushReplacement(
            MaterialPageRoute(builder: (_) => const BindScreen()),
          );
        }
      } else if (mounted) {
        await _policyDialog(e);
      }
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  Future<void> _openStats() async {
    Navigator.of(context).pop();
    await Navigator.of(
      context,
    ).push(MaterialPageRoute(builder: (_) => const MyStatsScreen()));
  }

  Future<void> _openFavorites() async {
    Navigator.of(context).pop();
    await Navigator.of(
      context,
    ).push(MaterialPageRoute(builder: (_) => const FavoritesScreen()));
  }

  Future<void> _openGrades() async {
    Navigator.of(context).pop();
    await Navigator.of(
      context,
    ).push(MaterialPageRoute(builder: (_) => const GradesScreen()));
  }

  Future<void> _logout() async {
    final navigator = Navigator.of(context);
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('退出登录？'),
        content: const Text('退出后需要家长端重新生成绑定码才能使用。聊天记录会保留。'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('退出'),
          ),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    await Api.I.logout();
    navigator.pushReplacement(
      MaterialPageRoute(builder: (_) => const BindScreen()),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(_teacherName),
            Text(
              '受保护学习空间',
              style: TextStyle(fontSize: 11, fontWeight: FontWeight.w500),
            ),
          ],
        ),
        leading: Builder(
          builder: (ctx) => IconButton(
            icon: const Icon(Icons.menu),
            tooltip: '聊天记录',
            onPressed: () {
              _loadSessions();
              Scaffold.of(ctx).openDrawer();
            },
          ),
        ),
        actions: [
          IconButton(
            tooltip: '选择老师',
            onPressed: _teachers == null ? null : _chooseTeacher,
            icon: const Icon(Icons.school_outlined),
          ),
        ],
      ),
      drawer: ChatDrawer(
        sessions: _sessions,
        filteredSessions: _filteredSessions,
        search: _search,
        currentConversationId: _conversationId,
        onNewChat: _newChat,
        onSearchChanged: (v) => setState(() => _search = v),
        onOpenStats: _openStats,
        onOpenFavorites: _openFavorites,
        onOpenGrades: _openGrades,
        onLogout: _logout,
        onOpenSession: _openSession,
        onSessionMenu: _sessionMenu,
      ),
      body: Column(
        children: [
          Expanded(child: _bubbles.isEmpty ? _emptyState() : _messageList()),
          _inputBar(),
        ],
      ),
    );
  }

  Widget _emptyState() {
    return Center(
      child: Card(
        margin: const EdgeInsets.symmetric(horizontal: 24),
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                Icons.lightbulb_outline,
                size: 38,
                color: Theme.of(context).colorScheme.primary,
              ),
              const SizedBox(height: 12),
              const Text(
                '你好！今天想学什么？',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 6),
              const Text(
                '可以问我作业、知识点和学习方法',
                style: TextStyle(color: Colors.black54),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _messageList() {
    return ListView.builder(
      controller: _scrollCtrl,
      itemCount: _bubbles.length,
      itemBuilder: (_, i) => MessageBubble(
        bubble: _bubbles[i],
        onLongPress: () => _messageMenu(_bubbles[i]),
      ),
    );
  }

  Widget _inputBar() {
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 4, 12, 8),
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(28),
            border: Border.all(
              color: Theme.of(
                context,
              ).colorScheme.outlineVariant.withValues(alpha: .55),
            ),
          ),
          child: Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _inputCtrl,
                  onSubmitted: (_) => _send(),
                  decoration: const InputDecoration(
                    hintText: '问一个学习问题…',
                    border: InputBorder.none,
                    contentPadding: EdgeInsets.symmetric(
                      horizontal: 18,
                      vertical: 14,
                    ),
                  ),
                ),
              ),
              Padding(
                padding: const EdgeInsets.only(right: 5),
                child: IconButton.filled(
                  onPressed: _sending ? null : _send,
                  icon: const Icon(Icons.arrow_upward),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
