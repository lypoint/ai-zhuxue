import 'dart:async';
import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:app_core/app_core.dart';
import '../foreground_heartbeat.dart';
import '../models/bubble.dart';
import '../widgets/chat_drawer.dart';
import '../widgets/message_bubble.dart';
import 'bind_screen.dart';
import 'favorites_screen.dart';
import 'my_reports_screen.dart';
import 'my_stats_screen.dart';
import 'grades_screen.dart';

/// 学习聊天页：流式对话、会话抽屉、心跳时长上报、消息收藏与政策拦截提示。
class ChatScreen extends StatefulWidget {
  const ChatScreen({super.key});
  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> with WidgetsBindingObserver {
  final _inputCtrl = TextEditingController();
  final _scrollCtrl = ScrollController();
  final List<Bubble> _bubbles = [];
  int? _conversationId;
  int _chatRevision = 0;
  bool _restoringLatest = true;
  bool _sending = false;
  bool _openingSession = false;
  bool _sessionActionPending = false;
  int? _favoritingMessageId;
  bool _handling401 = false;
  bool _loggingOut = false;
  List<dynamic>? _sessions;
  String? _sessionsError;
  List<dynamic>? _teachers;
  bool _loadingTeachers = false;
  bool _teacherLoadFailed = false;
  bool _selectingTeacher = false;
  String _teacherName = 'AI 学习助手';
  String _teacherAvatarUrl = '';
  String _search = '';
  late final _heartbeat = ForegroundHeartbeat((seconds) {
    unawaited(Api.I.heartbeat(seconds).then<void>((_) {}, onError: (_) {}));
  });

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _heartbeat.start();
    } else {
      _heartbeat.stop();
    }
  }

  @override
  void dispose() {
    if (Api.onUnauthorized == _onSessionExpired) Api.onUnauthorized = null;
    WidgetsBinding.instance.removeObserver(this);
    _heartbeat.stop();
    super.dispose();
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    // 全局 401 兜底：token 失效或孩子设备被重新绑定（规格 4.3），
    // 任何请求（会话列表/收藏/成绩等）收到 401 都回到重新绑定页。
    Api.onUnauthorized = _onSessionExpired;
    _restore();
    _loadTeachers();
    if (WidgetsBinding.instance.lifecycleState == null ||
        WidgetsBinding.instance.lifecycleState == AppLifecycleState.resumed) {
      _heartbeat.start();
    }
  }

  /// 统一 401 处理：清会话、说明原因并回绑定页；防重入避免多处请求并发 401 时重复跳转。
  Future<void> _onSessionExpired() async {
    if (_handling401) return;
    _handling401 = true;
    final navigator = Navigator.of(context, rootNavigator: true);
    await Api.I.logout();
    if (!mounted) return;
    await showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('设备已重新绑定'),
        content: const Text('此孩子账号已在另一台设备重新绑定，历史记录已保留，请输入新的绑定码继续。'),
        actions: [
          FilledButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('重新绑定'),
          ),
        ],
      ),
    );
    navigator.pushAndRemoveUntil(
      MaterialPageRoute(builder: (_) => const BindScreen()),
      (route) => false,
    );
  }

  Future<void> _loadTeachers() async {
    if (_loadingTeachers) return;
    setState(() {
      _loadingTeachers = true;
      _teacherLoadFailed = false;
    });
    try {
      final teachers = await Api.I.teachers();
      if (mounted) {
        setState(() {
          _teachers = teachers;
          if (_conversationId == null && teachers.isNotEmpty) {
            final teacher = (teachers.cast<Map<String, dynamic>>().firstWhere(
              (item) => item['selected'] == true,
              orElse: () => teachers.first as Map<String, dynamic>,
            ));
            _teacherName = teacher['name'] as String? ?? 'AI 学习助手';
            _teacherAvatarUrl = teacher['avatar_url'] as String? ?? '';
          }
        });
      }
    } catch (_) {
      if (mounted) {
        setState(() => _teacherLoadFailed = true);
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('老师列表加载失败，请重试')));
      }
    } finally {
      if (mounted) setState(() => _loadingTeachers = false);
    }
  }

  Future<void> _chooseTeacher() async {
    if (_sending || _openingSession) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('请等待当前操作完成后再切换老师')));
      return;
    }
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
                leading: _teacherAvatar(teacher['avatar_url'] as String? ?? ''),
                title: Text(teacher['name'] as String? ?? 'AI 老师'),
                subtitle: teacher['is_default'] == true
                    ? const Text('默认老师')
                    : null,
                trailing: available
                    ? (teacher['selected'] == true
                          ? const Icon(Icons.check_circle_outline, size: 18)
                          : null)
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
                onTap: () => Navigator.of(ctx).pop(teacher),
              );
            }),
          ],
        ),
      ),
    );
    if (selected == null || !mounted) return;
    if (_sending || _openingSession) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('请等待当前操作完成后再切换老师')));
      return;
    }
    if (selected['access'] != 'available') {
      await _policyDialog(
        ApiException(
          selected['access'] == 'daily_free_exhausted' ? 429 : 402,
          selected['access'] == 'daily_free_exhausted'
              ? '这位老师今日免费次数已用完，请通知家长购买会员后继续学习'
              : '这位老师需要会员，请通知家长在家长端购买会员后继续学习',
        ),
      );
      return;
    }
    if (_conversationId != null) {
      final startNew = await showDialog<bool>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('切换老师？'),
          content: const Text('切换老师会开启新对话，当前聊天记录仍可在侧边栏查看。'),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(false),
              child: const Text('取消'),
            ),
            FilledButton(
              onPressed: () => Navigator.of(ctx).pop(true),
              child: const Text('开启新对话'),
            ),
          ],
        ),
      );
      if (startNew != true || !mounted) return;
      if (_sending || _openingSession) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('请等待当前操作完成后再切换老师')));
        return;
      }
    }
    setState(() => _selectingTeacher = true);
    final messenger = ScaffoldMessenger.of(context);
    messenger.hideCurrentSnackBar();
    messenger.showSnackBar(
      const SnackBar(content: Text('正在切换老师…'), duration: Duration(seconds: 30)),
    );
    try {
      final teacherId = selected['teacher_id'] as int?;
      if (teacherId != null) await Api.I.selectTeacher(teacherId);
    } on ApiException catch (e) {
      if (mounted) {
        messenger.hideCurrentSnackBar();
        await _policyDialog(e);
      }
      return;
    } catch (_) {
      if (mounted) {
        messenger.hideCurrentSnackBar();
        messenger.showSnackBar(
          const SnackBar(content: Text('切换老师失败，请检查网络后重试')),
        );
      }
      return;
    } finally {
      if (mounted) setState(() => _selectingTeacher = false);
    }
    if (!mounted) return;
    messenger.hideCurrentSnackBar();
    setState(() {
      _chatRevision++;
      _restoringLatest = false;
      _conversationId = null;
      _bubbles.clear();
      _teacherName = selected['name'] as String? ?? 'AI 学习助手';
      _teacherAvatarUrl = selected['avatar_url'] as String? ?? '';
    });
    messenger.showSnackBar(SnackBar(content: Text('已切换到 $_teacherName')));
    _loadTeachers();
    _loadSessions();
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
    final revision = _chatRevision;
    try {
      final data = await Api.I.latestConversation().timeout(
        const Duration(seconds: 10),
      );
      if (!mounted || revision != _chatRevision) return;
      final convId = data['conversation_id'] as int?;
      final msgs = (data['messages'] as List?) ?? const [];
      if (convId != null && msgs.isNotEmpty) {
        setState(() {
          _conversationId = convId;
          _teacherName = data['teacher_name'] as String? ?? _teacherName;
          _teacherAvatarUrl = data['teacher_avatar_url'] as String? ?? '';
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
      }
    } catch (_) {
      if (mounted && revision == _chatRevision) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('未能恢复上次对话，可在聊天记录中重新打开')),
        );
      }
    } finally {
      if (mounted) {
        setState(() => _restoringLatest = false);
        _loadSessions();
      }
    }
  }

  Future<void> _loadSessions() async {
    if (_sessions == null && _sessionsError != null && mounted) {
      setState(() => _sessionsError = null);
    }
    try {
      final list = await Api.I.sessions();
      if (mounted) {
        setState(() {
          _sessions = list;
          _sessionsError = null;
        });
      }
    } catch (_) {
      if (!mounted) return;
      if (_sessions == null) {
        setState(() => _sessionsError = '会话记录加载失败，请重试');
      } else {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('会话记录刷新失败，请重试')));
      }
    }
  }

  /// 新建对话：清空当前气泡（历史仍在抽屉里，随时切回）
  void _newChat() {
    Navigator.of(context).pop(); // 关抽屉
    if (_sending || _openingSession || _selectingTeacher) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('请等待当前回复或会话加载完成')));
      return;
    }
    setState(() {
      _chatRevision++;
      _restoringLatest = false;
      _conversationId = null;
      _bubbles.clear();
    });
    _loadTeachers();
    _loadSessions();
  }

  /// 从抽屉载入历史会话
  Future<void> _openSession(int conversationId) async {
    Navigator.of(context).pop();
    if (_sending || _openingSession || _selectingTeacher) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('请等待当前回复或会话加载完成')));
      return;
    }
    setState(() {
      _chatRevision++;
      _restoringLatest = false;
      _openingSession = true;
    });
    final messenger = ScaffoldMessenger.of(context);
    messenger.hideCurrentSnackBar();
    messenger.showSnackBar(
      const SnackBar(content: Text('正在打开会话…'), duration: Duration(seconds: 30)),
    );
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
        _teacherName = session?['teacher_name'] as String? ?? _teacherName;
        _teacherAvatarUrl = session?['teacher_avatar_url'] as String? ?? '';
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
      messenger.hideCurrentSnackBar();
      _scrollToBottom();
    } on ApiException catch (e) {
      if (mounted) {
        messenger.hideCurrentSnackBar();
        messenger.showSnackBar(SnackBar(content: Text(e.message)));
      }
    } catch (_) {
      if (mounted) {
        messenger.hideCurrentSnackBar();
        messenger.showSnackBar(
          const SnackBar(content: Text('打开会话失败，请检查网络后重试')),
        );
      }
    } finally {
      if (mounted) setState(() => _openingSession = false);
    }
  }

  Future<void> _copyMessage(Bubble b) async {
    try {
      await Clipboard.setData(ClipboardData(text: b.text));
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('已复制到剪贴板'),
            duration: Duration(seconds: 1),
          ),
        );
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('复制失败，请重试')));
      }
    }
  }

  /// 长按和三点共用消息操作菜单。
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
            ListTile(
              leading: const Icon(Icons.flag_outlined),
              title: const Text('举报'),
              onTap: () => Navigator.of(ctx).pop('report'),
            ),
          ],
        ),
      ),
    );
    if (!mounted || action == null) return;
    if (action == 'copy') {
      await _copyMessage(b);
    } else if (action == 'report') {
      await _reportMessage(b);
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
      if (_favoritingMessageId != null) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('正在收藏上一条消息，请稍候')),
        );
        return;
      }
      _favoritingMessageId = b.messageId;
      final messenger = ScaffoldMessenger.of(context);
      messenger.hideCurrentSnackBar();
      messenger.showSnackBar(const SnackBar(
        content: Text('正在收藏…'),
        duration: Duration(seconds: 30),
      ));
      try {
        await Api.I.addFavorite(b.messageId!);
        if (mounted) {
          messenger.hideCurrentSnackBar();
          messenger.showSnackBar(
            const SnackBar(content: Text('已收藏 ⭐ 可在抽屉「我的收藏」查看')),
          );
        }
      } on ApiException catch (e) {
        if (mounted) {
          messenger.hideCurrentSnackBar();
          messenger.showSnackBar(SnackBar(content: Text(e.message)));
        }
      } catch (_) {
        if (mounted) {
          messenger.hideCurrentSnackBar();
          messenger.showSnackBar(
            const SnackBar(content: Text('收藏失败，请检查网络后重试')),
          );
        }
      } finally {
        _favoritingMessageId = null;
      }
    }
  }

  Future<void> _reportMessage(Bubble b) async {
    if (b.messageId == null) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('请等待消息发送完成后再举报')));
      return;
    }
    final reason = await showModalBottomSheet<String>(
      context: context,
      builder: (ctx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const ListTile(title: Text('选择举报原因')),
            for (final text in ['内容不准确', '内容不适合学生', '存在不友善内容', '其他问题'])
              ListTile(
                title: Text(text),
                onTap: () => Navigator.of(ctx).pop(text),
              ),
          ],
        ),
      ),
    );
    if (reason == null || !mounted) return;
    final messenger = ScaffoldMessenger.of(context);
    messenger.hideCurrentSnackBar();
    messenger.showSnackBar(
      const SnackBar(content: Text('正在提交举报…'), duration: Duration(seconds: 30)),
    );
    try {
      final result = await Api.I.reportMessage(b.messageId!, reason);
      if (!mounted) return;
      messenger.hideCurrentSnackBar();
      messenger.showSnackBar(
        SnackBar(
          content: Text(
            result['already'] == true
                ? '这条消息已举报，可在「我的举报」查看进度'
                : '举报已提交，可在「我的举报」查看回复',
          ),
        ),
      );
    } on ApiException catch (e) {
      if (mounted) {
        messenger.hideCurrentSnackBar();
        messenger.showSnackBar(SnackBar(content: Text(e.message)));
      }
    } catch (_) {
      if (mounted) {
        messenger.hideCurrentSnackBar();
        messenger.showSnackBar(const SnackBar(content: Text('举报失败，请检查网络后重试')));
      }
    }
  }

  /// 时段/时长/订阅拦截的全屏友好提示（比错误气泡更适合低龄用户）
  Future<void> _policyDialog(ApiException e) async {
    final (title, icon) = switch (e.status) {
      423 => ('休息时间到啦', Icons.bedtime),
      429 when e.message.contains('免费次数') => ('请家长购买会员', Icons.favorite_border),
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
    await _guard(() => Api.I.renameSession(cid, title), '会话已重命名');
  }

  Future<void> _pinSession(int cid, bool pinned) async {
    await _guard(
      () => Api.I.pinSession(cid, pinned),
      pinned ? '会话已置顶' : '已取消置顶',
    );
  }

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
    final deleted = await _guard(() => Api.I.deleteSession(cid), '会话已删除');
    if (deleted && mounted && _conversationId == cid) {
      setState(() {
        _conversationId = null;
        _bubbles.clear();
      });
    }
  }

  /// 会话管理请求统一包裹：显示进度、结果，并在成功后刷新列表。
  Future<bool> _guard(Future<void> Function() action, String success) async {
    if (_sessionActionPending) return false;
    if (_sending || _openingSession || _selectingTeacher) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('请等待当前回复或会话加载完成')));
      return false;
    }
    _sessionActionPending = true;
    final messenger = ScaffoldMessenger.of(context);
    messenger.hideCurrentSnackBar();
    messenger.showSnackBar(
      const SnackBar(content: Text('正在处理…'), duration: Duration(seconds: 30)),
    );
    try {
      await action();
      await _loadSessions();
      if (mounted) {
        messenger.hideCurrentSnackBar();
        messenger.showSnackBar(SnackBar(content: Text(success)));
      }
      return true;
    } on ApiException catch (e) {
      if (mounted) {
        messenger.hideCurrentSnackBar();
        messenger.showSnackBar(SnackBar(content: Text(e.message)));
      }
    } catch (_) {
      if (mounted) {
        messenger.hideCurrentSnackBar();
        messenger.showSnackBar(const SnackBar(content: Text('操作失败，请检查网络后重试')));
      }
    } finally {
      _sessionActionPending = false;
    }
    return false;
  }

  void _scrollToBottom({bool animate = true}) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollCtrl.hasClients) {
        final bottom = _scrollCtrl.position.maxScrollExtent;
        if (animate) {
          _scrollCtrl.animateTo(
            bottom,
            duration: const Duration(milliseconds: 200),
            curve: Curves.easeOut,
          );
        } else {
          _scrollCtrl.jumpTo(bottom);
        }
      }
    });
  }

  Future<void> _send() async {
    final text = _inputCtrl.text.trim();
    if (text.isEmpty ||
        _sending ||
        _openingSession ||
        _selectingTeacher ||
        _sessionActionPending) {
      return;
    }
    _inputCtrl.clear();
    final userIndex = _bubbles.length;
    setState(() {
      _chatRevision++;
      _restoringLatest = false;
      _sending = true;
      _bubbles.add(Bubble('user', text));
      _bubbles.add(Bubble('assistant', '')); // 流式占位，逐段填充
    });
    _scrollToBottom();
    void updateLast(String text) {
      if (!mounted) return;
      setState(() {
        _bubbles[_bubbles.length - 1] = Bubble('assistant', text);
      });
    }

    // 参考聊天页每 25ms 显示约 3 个字；服务端短时间回放全文时也逐帧显现。
    final received = <String>[];
    final visible = StringBuffer();
    var shown = 0;
    Timer? revealTimer;
    Completer<void>? revealDone;
    void reveal() {
      if (!mounted) {
        revealTimer?.cancel();
        revealDone?.complete();
        return;
      }
      final remaining = received.length - shown;
      final count = math.min(remaining, math.max(3, (remaining / 32).ceil()));
      visible.writeAll(received.getRange(shown, shown + count));
      shown += count;
      updateLast(visible.toString());
      _scrollToBottom(animate: false);
      if (shown == received.length) {
        revealTimer?.cancel();
        revealTimer = null;
        revealDone?.complete();
      }
    }

    try {
      final done = await Api.I.sendChatStream(
        _conversationId,
        text,
        onMeta: (meta) {
          if (mounted) {
            _conversationId =
                meta['conversation_id'] as int? ?? _conversationId;
            final id = meta['user_message_id'] as int?;
            if (id != null) {
              setState(
                () => _bubbles[userIndex] = Bubble('user', text, messageId: id),
              );
            }
          }
        },
        onDelta: (delta) {
          if (!mounted || delta.isEmpty) return;
          received.addAll(delta.characters);
          if (revealTimer == null) {
            revealDone = Completer<void>();
            revealTimer = Timer.periodic(
              const Duration(milliseconds: 25),
              (_) => reveal(),
            );
          }
        },
        onReplace: (text) {
          revealTimer?.cancel();
          revealTimer = null;
          received.clear();
          shown = 0;
          visible.clear();
          updateLast(text);
          _scrollToBottom(animate: false);
        },
      );
      if (!mounted) return;
      if (revealTimer != null) await revealDone!.future;
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
      // 401 已由全局 _onSessionExpired 统一处理（清会话回绑定页）
      updateLast('⚠️ ${e.message}');
      if (e.status != 401 && mounted) {
        await _policyDialog(e);
      }
    } catch (_) {
      updateLast('⚠️ 发送失败，请检查网络后重试');
    } finally {
      revealTimer?.cancel();
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

  Future<void> _openReports() async {
    Navigator.of(context).pop();
    await Navigator.of(
      context,
    ).push(MaterialPageRoute(builder: (_) => const MyReportsScreen()));
  }

  Future<void> _openGrades() async {
    Navigator.of(context).pop();
    await Navigator.of(
      context,
    ).push(MaterialPageRoute(builder: (_) => const GradesScreen()));
  }

  Future<void> _logout() async {
    if (_loggingOut) return;
    final navigator = Navigator.of(context);
    navigator.pop(); // 关闭抽屉，让退出状态在页面上可见。
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
    setState(() => _loggingOut = true);
    final messenger = ScaffoldMessenger.of(context);
    messenger.showSnackBar(const SnackBar(
      content: Text('正在退出登录…'),
      duration: Duration(seconds: 30),
    ));
    try {
      await Api.I.logout();
      if (!mounted) return;
      messenger.hideCurrentSnackBar();
      navigator.pushReplacement(
        MaterialPageRoute(builder: (_) => const BindScreen()),
      );
    } catch (_) {
      if (mounted) {
        messenger.hideCurrentSnackBar();
        messenger.showSnackBar(const SnackBar(content: Text('退出失败，请重试')));
      }
    } finally {
      if (mounted) setState(() => _loggingOut = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Row(
          children: [
            _teacherAvatar(_teacherAvatarUrl),
            const SizedBox(width: 10),
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(_teacherName),
                const Text(
                  '受保护学习空间',
                  style: TextStyle(fontSize: 11, fontWeight: FontWeight.w500),
                ),
              ],
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
            tooltip: _teacherLoadFailed ? '重试加载老师' : '选择老师',
            onPressed: _loadingTeachers || _selectingTeacher
                ? null
                : _teacherLoadFailed
                ? _loadTeachers
                : _teachers == null
                ? null
                : _chooseTeacher,
            icon: _loadingTeachers || _selectingTeacher
                ? const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : Icon(
                    _teacherLoadFailed ? Icons.refresh : Icons.school_outlined,
                  ),
          ),
        ],
      ),
      drawer: ChatDrawer(
        sessions: _sessions,
        sessionsError: _sessionsError,
        filteredSessions: _filteredSessions,
        search: _search,
        currentConversationId: _conversationId,
        onNewChat: _newChat,
        onSearchChanged: (v) => setState(() => _search = v),
        onOpenStats: _openStats,
        onOpenFavorites: _openFavorites,
        onOpenReports: _openReports,
        onOpenGrades: _openGrades,
        onLogout: _logout,
        onOpenSession: _openSession,
        onSessionMenu: _sessionMenu,
        onRetrySessions: _loadSessions,
      ),
      body: Column(
        children: [
          if (_restoringLatest) ...[
            const LinearProgressIndicator(minHeight: 2),
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 6),
              child: Text('正在恢复上次对话…', style: TextStyle(fontSize: 12)),
            ),
          ],
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
        isLoading:
            _sending && i == _bubbles.length - 1 && _bubbles[i].text.isEmpty,
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
                  onPressed:
                      _sending ||
                          _openingSession ||
                          _selectingTeacher ||
                          _sessionActionPending
                      ? null
                      : _send,
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
