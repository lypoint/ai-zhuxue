import 'package:image_picker/image_picker.dart';
import 'dart:async';
import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:app_core/app_core.dart';
import '../foreground_heartbeat.dart';
import '../models/bubble.dart';
import '../widgets/chat_drawer.dart';
import '../widgets/message_bubble.dart';
import '../widgets/daily_incentive_card.dart';
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
  final _inputFocus = FocusNode();
  final _scrollCtrl = ScrollController();
  final List<Bubble> _bubbles = [];
  final List<_DraftImage> _draftImages = [];
  Map<String, dynamic> _imageCapabilities = {};
  bool _uploadingImage = false;
  Timer? _imagePollTimer;
  bool _pollingImages = false;
  final Set<int> _diagramRequests = {};

  int? _conversationId;
  int _chatRevision = 0;
  bool _restoringLatest = true;
  bool _sending = false;
  final Map<String, dynamic> _learningSelections = {};
  final Set<int> _feedbackPending = {};
  Map<String, dynamic>? _dailyLearning;
  String? _dailyLearningError;
  int _dailyLearningRevision = 0;
  Timer? _dailyLearningTimer;

  void _applyDailyLearning(Map<String, dynamic> data) {
    _dailyLearningTimer?.cancel();
    setState(() {
      _dailyLearning = data;
      _dailyLearningError = null;
    });
    final delay = Duration(
      seconds: (data['today']['refresh_after_seconds'] as int) + 1,
    );
    _dailyLearningTimer = Timer(delay, _loadDailyLearning);
  }

  Future<void> _loadDailyLearning() async {
    final revision = ++_dailyLearningRevision;
    _dailyLearningTimer?.cancel();
    setState(() {
      _dailyLearning = null;
      _dailyLearningError = null;
    });
    try {
      final data = await Api.I.learningSummary();
      if (mounted && revision == _dailyLearningRevision) {
        _applyDailyLearning(data);
      }
    } catch (e) {
      if (mounted && revision == _dailyLearningRevision) {
        setState(() => _dailyLearningError = tr("今日奖励加载失败，请重试"));
      }
    }
  }

  Future<void> _openLearning() async {
    await Navigator.of(
      context,
    ).push(MaterialPageRoute(builder: (_) => const LearningScreen()));
    if (mounted) _loadDailyLearning();
  }

  Future<void> _feedback(Bubble bubble, String action) async {
    final id = bubble.messageId!;
    final revision = _chatRevision;
    if (_feedbackPending.contains(id)) return;
    setState(() => _feedbackPending.add(id));
    try {
      final result = await Api.I.learningFeedback(id, action);
      if (!mounted) return;
      ++_dailyLearningRevision;
      _applyDailyLearning(result);
      setState(() => _learningSelections['$id'] = result['action']);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            tr("{0} · 余额 {1} 颗", [
              result['awarded'] == true ? tr("今天参与学习，获得1颗小行星") : tr("反馈已记录"),
              result['balance'],
            ]),
          ),
        ),
      );
      if (action != 'understood' &&
          result['action'] == action &&
          result['changed'] == true &&
          revision == _chatRevision) {
        await _send(
          followUp: tr("{0}这条回答：\n{1}", [
            action == 'not_understood'
                ? tr("我还不懂，请降低难度，用更简单的例子换一种方式讲解")
                : tr("请沿用当前方式继续讲解，补充步骤和例子"),
            bubble.text.length > 3500
                ? bubble.text.substring(0, 3500)
                : bubble.text,
          ]),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(e is ApiException ? e.message : tr("反馈失败，请重试")),
          ),
        );
      }
    } finally {
      if (mounted) setState(() => _feedbackPending.remove(id));
    }
  }

  Future<void> _loadLearningSelections() async {
    try {
      final data = await Api.I.learningSelections();
      if (mounted) setState(() => _learningSelections.addAll(data));
    } catch (_) {
      /* Submission remains idempotent if history cannot load. */
    }
  }

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
      _loadDailyLearning();
    } else {
      _heartbeat.stop();
    }
  }

  @override
  void dispose() {
    _imagePollTimer?.cancel();
    if (Api.onUnauthorized == _onSessionExpired) Api.onUnauthorized = null;
    WidgetsBinding.instance.removeObserver(this);
    _heartbeat.stop();
    _dailyLearningTimer?.cancel();
    _inputFocus.dispose();
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
    _loadDailyLearning();
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
        title: Text(tr("登录已失效")),
        content: Text(tr("孩子已被删除、设备已被解绑或登录已失效。请联系家长获取新的绑定码。")),
        actions: [
          FilledButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: Text(tr("重新绑定")),
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
            _imageCapabilities = Map<String, dynamic>.from(
              teacher['capabilities'] as Map? ?? {},
            );
          }
        });
      }
    } catch (_) {
      if (mounted) {
        setState(() => _teacherLoadFailed = true);
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(tr("老师列表加载失败，请重试"))));
      }
    } finally {
      if (mounted) setState(() => _loadingTeachers = false);
    }
  }

  Future<void> _chooseTeacher() async {
    if (_draftImages.isNotEmpty) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(tr("请先发送或移除待发送的图片"))));
      return;
    }
    if (_sending || _uploadingImage || _openingSession) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(tr("请等待当前操作完成后再切换老师"))));
      return;
    }
    final selected = await showModalBottomSheet<Map<String, dynamic>>(
      context: context,
      builder: (ctx) => SafeArea(
        child: ListView(
          shrinkWrap: true,
          children: [
            ListTile(
              title: Text(
                tr("选择老师"),
                style: TextStyle(fontWeight: FontWeight.w700),
              ),
            ),
            ...(_teachers ?? const []).map((raw) {
              final teacher = raw as Map<String, dynamic>;
              final available = teacher['access'] == 'available';
              final access = teacher['access'] as String?;
              return ListTile(
                leading: _teacherAvatar(teacher['avatar_url'] as String? ?? ''),
                title: Text(
                  localizedTeacherName(teacher['name'] as String? ?? 'AI 老师'),
                ),
                subtitle: teacher['is_default'] == true
                    ? Text(tr("默认老师"))
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
                                ? tr("今日次数已用完")
                                : tr("需订阅"),
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
    if (_sending || _uploadingImage || _openingSession) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(tr("请等待当前操作完成后再切换老师"))));
      return;
    }
    if (selected['access'] != 'available') {
      await _policyDialog(
        ApiException(
          selected['access'] == 'daily_free_exhausted' ? 429 : 402,
          selected['access'] == 'daily_free_exhausted'
              ? tr("这位老师今日免费次数已用完，请通知家长购买会员后继续学习")
              : tr("这位老师需要会员，请通知家长在家长端购买会员后继续学习"),
        ),
      );
      return;
    }
    if (_conversationId != null) {
      final startNew = await showDialog<bool>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: Text(tr("切换老师？")),
          content: Text(tr("切换老师会开启新对话，当前聊天记录仍可在侧边栏查看。")),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(false),
              child: Text(tr("取消")),
            ),
            FilledButton(
              onPressed: () => Navigator.of(ctx).pop(true),
              child: Text(tr("开启新对话")),
            ),
          ],
        ),
      );
      if (startNew != true || !mounted) return;
      if (_sending || _uploadingImage || _openingSession) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(tr("请等待当前操作完成后再切换老师"))));
        return;
      }
    }
    setState(() => _selectingTeacher = true);
    final messenger = ScaffoldMessenger.of(context);
    messenger.hideCurrentSnackBar();
    messenger.showSnackBar(
      SnackBar(content: Text(tr("正在切换老师…")), duration: Duration(seconds: 30)),
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
        messenger.showSnackBar(SnackBar(content: Text(tr("切换老师失败，请检查网络后重试"))));
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
    messenger.showSnackBar(
      SnackBar(content: Text(tr("已切换到 {0}", [_teacherName]))),
    );
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
          _replaceBubbles(msgs);
          unawaited(_loadImageCapabilities());
        });
      }
    } catch (_) {
      if (mounted && revision == _chatRevision) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(tr("未能恢复上次对话，可在聊天记录中重新打开"))));
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
        setState(() => _sessionsError = tr("会话记录加载失败，请重试"));
      } else {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(tr("会话记录刷新失败，请重试"))));
      }
    }
  }

  /// 新建对话：清空当前气泡（历史仍在抽屉里，随时切回）
  void _newChat() {
    if (_draftImages.isNotEmpty) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(tr("请先发送或移除待发送的图片"))));
      return;
    }
    Navigator.of(context).pop(); // 关抽屉
    if (_sending || _uploadingImage || _openingSession || _selectingTeacher) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(tr("请等待当前回复或会话加载完成"))));
      return;
    }
    setState(() {
      _chatRevision++;
      _restoringLatest = false;
      _conversationId = null;
      _bubbles.clear();
      _draftImages.clear();
      _imageCapabilities = {};
    });
    _loadTeachers();
    _loadSessions();
  }

  /// 从抽屉载入历史会话
  Future<void> _openSession(int conversationId) async {
    if (_draftImages.isNotEmpty) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(tr("请先发送或移除待发送的图片"))));
      return;
    }
    Navigator.of(context).pop();
    if (_sending || _uploadingImage || _openingSession || _selectingTeacher) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(tr("请等待当前回复或会话加载完成"))));
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
      SnackBar(content: Text(tr("正在打开会话…")), duration: Duration(seconds: 30)),
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
        _replaceBubbles(msgs);
        unawaited(_loadImageCapabilities());
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
        messenger.showSnackBar(SnackBar(content: Text(tr("打开会话失败，请检查网络后重试"))));
      }
    } finally {
      if (mounted) setState(() => _openingSession = false);
    }
  }

  void _replaceBubbles(List<dynamic> messages) {
    _loadLearningSelections();
    _bubbles.clear();
    for (final m in messages) {
      _bubbles.add(
        Bubble(
          m['role'] as String,
          m['content'] as String,
          messageId: m['id'] as int?,
          contentBlocks: m['content_blocks'] as List? ?? const [],
          imageJob: m['image_job'] as Map<String, dynamic>?,
        ),
      );
    }
    if (messages.isNotEmpty &&
        messages.last['role'] == 'user' &&
        messages.last['fence_action'] == 'failed') {
      _bubbles.add(Bubble('assistant', tr("⚠️ 老师回复失败，请重试"), failed: true));
    }
    _startImagePolling();
  }

  Future<void> _refreshCurrentConversation() async {
    final id = _conversationId;
    if (id == null) return;
    final messages = await Api.I.conversationMessages(id);
    if (mounted) setState(() => _replaceBubbles(messages));
  }

  Future<void> _copyMessage(Bubble b) async {
    try {
      await Clipboard.setData(ClipboardData(text: b.text));
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(tr("已复制到剪贴板")),
            duration: Duration(seconds: 1),
          ),
        );
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(tr("复制失败，请重试"))));
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
              title: Text(tr("复制全文（含公式源码）")),
              onTap: () => Navigator.of(ctx).pop('copy'),
            ),
            ListTile(
              leading: const Icon(Icons.star_border),
              title: Text(tr("收藏")),
              onTap: () => Navigator.of(ctx).pop('favorite'),
            ),
            ListTile(
              leading: const Icon(Icons.flag_outlined),
              title: Text(tr("举报")),
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
          SnackBar(
            content: Text(tr("该消息暂不支持收藏")),
            duration: Duration(seconds: 1),
          ),
        );
        return;
      }
      if (_favoritingMessageId != null) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(tr("正在收藏上一条消息，请稍候"))));
        return;
      }
      _favoritingMessageId = b.messageId;
      final messenger = ScaffoldMessenger.of(context);
      messenger.hideCurrentSnackBar();
      messenger.showSnackBar(
        SnackBar(content: Text(tr("正在收藏…")), duration: Duration(seconds: 30)),
      );
      try {
        await Api.I.addFavorite(b.messageId!);
        if (mounted) {
          messenger.hideCurrentSnackBar();
          messenger.showSnackBar(
            SnackBar(content: Text(tr("已收藏 ⭐ 可在抽屉「我的收藏」查看"))),
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
          messenger.showSnackBar(SnackBar(content: Text(tr("收藏失败，请检查网络后重试"))));
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
      ).showSnackBar(SnackBar(content: Text(tr("请等待消息发送完成后再举报"))));
      return;
    }
    final reason = await showModalBottomSheet<String>(
      context: context,
      builder: (ctx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(title: Text(tr("选择举报原因"))),
            for (final text in [
              tr("内容不准确"),
              tr("内容不适合学生"),
              tr("存在不友善内容"),
              tr("其他问题"),
            ])
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
      SnackBar(content: Text(tr("正在提交举报…")), duration: Duration(seconds: 30)),
    );
    try {
      final result = await Api.I.reportMessage(b.messageId!, reason);
      if (!mounted) return;
      messenger.hideCurrentSnackBar();
      messenger.showSnackBar(
        SnackBar(
          content: Text(
            result['already'] == true
                ? tr("这条消息已举报，可在「我的举报」查看进度")
                : tr("举报已提交，可在「我的举报」查看回复"),
          ),
        ),
      );
    } on ApiException catch (e) {
      if (mounted) {
        messenger.hideCurrentSnackBar();
        messenger.showSnackBar(
          SnackBar(
            content: Text(
              e.status == 404 && e.rawMessage == 'Not Found'
                  ? tr("举报服务暂未上线，请稍后再试")
                  : e.message,
            ),
          ),
        );
      }
    } catch (_) {
      if (mounted) {
        messenger.hideCurrentSnackBar();
        messenger.showSnackBar(SnackBar(content: Text(tr("举报失败，请检查网络后重试"))));
      }
    }
  }

  /// 时段/时长/订阅拦截的全屏友好提示（比错误气泡更适合低龄用户）
  Future<void> _policyDialog(ApiException e) async {
    final (title, icon) = switch (e.status) {
      423 => (tr("休息时间到啦"), Icons.bedtime),
      429 when e.rawMessage.contains('免费次数') => (
        tr("请家长购买会员"),
        Icons.favorite_border,
      ),
      429 => (tr("今天的时间用完了"), Icons.schedule),
      402 => (tr("需要家长续费"), Icons.favorite_border),
      _ => (tr("提示"), Icons.info_outline),
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
            child: Text(tr("好的")),
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
              title: Text(tr("重命名")),
              onTap: () => Navigator.of(ctx).pop('rename'),
            ),
            ListTile(
              leading: Icon(
                c['pinned'] == true ? Icons.push_pin_outlined : Icons.push_pin,
              ),
              title: Text(c['pinned'] == true ? tr("取消置顶") : tr("置顶")),
              onTap: () => Navigator.of(ctx).pop('pin'),
            ),
            ListTile(
              leading: const Icon(Icons.delete_outline, color: Colors.red),
              title: Text(tr("删除会话"), style: TextStyle(color: Colors.red)),
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
        title: Text(tr("重命名会话")),
        content: TextField(
          controller: ctrl,
          autofocus: true,
          maxLength: 100,
          decoration: InputDecoration(hintText: tr("会话标题")),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: Text(tr("取消")),
          ),
          FilledButton(
            onPressed: () => Navigator.of(ctx).pop(ctrl.text.trim()),
            child: Text(tr("保存")),
          ),
        ],
      ),
    );
    if (title == null || title.isEmpty || !mounted) return;
    await _guard(() => Api.I.renameSession(cid, title), tr("会话已重命名"));
  }

  Future<void> _pinSession(int cid, bool pinned) async {
    await _guard(
      () => Api.I.pinSession(cid, pinned),
      pinned ? tr("会话已置顶") : tr("已取消置顶"),
    );
  }

  Future<void> _deleteSession(int cid) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(tr("删除会话？")),
        content: Text(tr("该会话会从孩子端隐藏，家长仍可在审查记录中查看。此操作不可撤销。")),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: Text(tr("取消")),
          ),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: Colors.red),
            onPressed: () => Navigator.of(ctx).pop(true),
            child: Text(tr("删除")),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    final deleted = await _guard(() => Api.I.deleteSession(cid), tr("会话已删除"));
    if (deleted && mounted && _conversationId == cid) {
      setState(() {
        _conversationId = null;
        _bubbles.clear();
      });
    }
  }

  /// 会话管理请求统一包裹：显示进度、结果，并在成功后刷新列表。
  Future<bool> _guard(Future<void> Function() action, String success) async {
    if (_draftImages.isNotEmpty) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(tr("请先发送或移除待发送的图片"))));
      return false;
    }
    if (_sessionActionPending) return false;
    if (_sending || _uploadingImage || _openingSession || _selectingTeacher) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(tr("请等待当前回复或会话加载完成"))));
      return false;
    }
    _sessionActionPending = true;
    final messenger = ScaffoldMessenger.of(context);
    messenger.hideCurrentSnackBar();
    messenger.showSnackBar(
      SnackBar(content: Text(tr("正在处理…")), duration: Duration(seconds: 30)),
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
        messenger.showSnackBar(SnackBar(content: Text(tr("操作失败，请检查网络后重试"))));
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

  Future<void> _loadImageCapabilities() async {
    final id = _conversationId;
    final revision = _chatRevision;
    if (id == null) return;
    try {
      final value = await Api.I.conversationCapabilities(id);
      if (mounted && id == _conversationId && revision == _chatRevision) {
        setState(() => _imageCapabilities = value);
      }
    } catch (_) {
      if (mounted && id == _conversationId) {
        setState(() => _imageCapabilities = {});
      }
    }
  }

  Future<void> _pickImage() async {
    if (_uploadingImage || _sending || _draftImages.length >= 3) return;
    final source = await showModalBottomSheet<ImageSource>(
      context: context,
      builder: (ctx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: const Icon(Icons.camera_alt_outlined),
              title: Text(tr('拍摄题目')),
              onTap: () => Navigator.pop(ctx, ImageSource.camera),
            ),
            ListTile(
              leading: const Icon(Icons.photo_library_outlined),
              title: Text(tr('从相册选择')),
              onTap: () => Navigator.pop(ctx, ImageSource.gallery),
            ),
          ],
        ),
      ),
    );
    if (source == null || !mounted) return;
    setState(() => _uploadingImage = true);
    try {
      final picked = await ImagePicker().pickImage(
        source: source,
        maxWidth: 2400,
        maxHeight: 2400,
        imageQuality: 90,
      );
      if (picked == null || !mounted) return;
      final bytes = await picked.readAsBytes();
      if (!mounted) return;
      final draft = _DraftImage(bytes);
      setState(() => _draftImages.add(draft));
      await _uploadDraft(draft);
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(tr('无法读取图片，请检查相机或相册权限'))));
      }
    } finally {
      if (mounted) setState(() => _uploadingImage = false);
    }
  }

  Future<void> _uploadDraft(_DraftImage draft) async {
    setState(() {
      _uploadingImage = true;
      draft.error = false;
    });
    try {
      final block = await Api.I.uploadChatImage(
        draft.bytes,
        conversationId: _conversationId,
      );
      if (mounted) setState(() => draft.block = block);
    } catch (_) {
      if (mounted) setState(() => draft.error = true);
    } finally {
      if (mounted) setState(() => _uploadingImage = false);
    }
  }

  Future<void> _requestDiagram(Bubble bubble) async {
    final id = bubble.messageId;
    if (id == null || !_diagramRequests.add(id)) return;
    setState(() {});
    try {
      final job = await Api.I.requestDiagram(id);
      if (!mounted) return;
      final index = _bubbles.indexWhere((b) => b.messageId == id);
      if (index >= 0) {
        setState(
          () => _bubbles[index] = Bubble(
            bubble.role,
            bubble.text,
            messageId: id,
            contentBlocks: bubble.contentBlocks,
            imageJob: job,
          ),
        );
      }
      _startImagePolling();
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
        ).showSnackBar(SnackBar(content: Text(tr('配图请求失败，请重试'))));
      }
    } finally {
      _diagramRequests.remove(id);
      if (mounted) setState(() {});
    }
  }

  void _startImagePolling() {
    _imagePollTimer?.cancel();
    if (!_bubbles.any(
      (b) => const ['queued', 'running'].contains(b.imageJob?['state']),
    )) {
      return;
    }
    _imagePollTimer = Timer.periodic(
      const Duration(seconds: 3),
      (_) => _pollImages(),
    );
  }

  Future<void> _pollImages() async {
    if (_pollingImages || !mounted) return;
    _pollingImages = true;
    final revision = _chatRevision;
    try {
      final pending = _bubbles
          .where(
            (b) => const ['queued', 'running'].contains(b.imageJob?['state']),
          )
          .toList();
      for (final bubble in pending) {
        final job = await Api.I.imageJob(bubble.imageJob!['id'] as int);
        if (!mounted || revision != _chatRevision) return;
        final index = _bubbles.indexWhere(
          (b) => b.messageId == bubble.messageId,
        );
        if (index >= 0) {
          setState(
            () => _bubbles[index] = Bubble(
              bubble.role,
              bubble.text,
              messageId: bubble.messageId,
              contentBlocks:
                  job['content_blocks'] as List? ?? bubble.contentBlocks,
              imageJob: job,
            ),
          );
        }
      }
      _startImagePolling();
    } catch (_) {
      // Keep pending state across network failures; reopening also restores it.
    } finally {
      _pollingImages = false;
    }
  }

  Widget _imageDrafts() => Wrap(
    spacing: 8,
    children: [
      for (final draft in _draftImages)
        SizedBox(
          width: 104,
          child: Column(
            children: [
              Stack(
                children: [
                  ClipRRect(
                    borderRadius: BorderRadius.circular(8),
                    child: Image.memory(
                      draft.bytes,
                      width: 100,
                      height: 80,
                      fit: BoxFit.cover,
                    ),
                  ),
                  Positioned(
                    right: 0,
                    top: 0,
                    child: IconButton(
                      tooltip: tr('移除图片'),
                      onPressed: _sending || _uploadingImage
                          ? null
                          : () => setState(() => _draftImages.remove(draft)),
                      icon: const Icon(Icons.cancel),
                    ),
                  ),
                ],
              ),
              if (draft.error)
                TextButton(
                  onPressed: _uploadingImage ? null : () => _uploadDraft(draft),
                  child: Text(tr('重试上传')),
                )
              else if (draft.block == null)
                const LinearProgressIndicator(),
            ],
          ),
        ),
    ],
  );

  Future<void> _send({int? retryUserIndex, String? followUp}) async {
    final retrying = retryUserIndex != null;
    final text = retrying
        ? _bubbles[retryUserIndex].text
        : followUp ?? _inputCtrl.text.trim();
    final imageBlocks = retrying
        ? _bubbles[retryUserIndex].contentBlocks
        : followUp == null
        ? _draftImages
              .where((d) => d.block != null)
              .map((d) => d.block!)
              .toList()
        : <dynamic>[];
    final drafts = !retrying && followUp == null
        ? List<_DraftImage>.from(_draftImages)
        : <_DraftImage>[];
    if ((text.isEmpty && imageBlocks.isEmpty) ||
        (!retrying && _draftImages.any((d) => d.block == null)) ||
        _sending ||
        _uploadingImage ||
        _openingSession ||
        _selectingTeacher ||
        _sessionActionPending) {
      return;
    }
    if (retrying &&
        (retryUserIndex != _bubbles.length - 2 || !_bubbles.last.failed)) {
      return;
    }
    final retryMessageId = retrying ? _bubbles[retryUserIndex].messageId : null;
    if (retrying && retryMessageId == null) return;
    if (!retrying && followUp == null) {
      _inputCtrl.clear();
      _draftImages.clear();
    }
    final userIndex = retryUserIndex ?? _bubbles.length;
    setState(() {
      _chatRevision++;
      _restoringLatest = false;
      _sending = true;
      if (retrying) {
        _bubbles[_bubbles.length - 1] = Bubble('assistant', '');
      } else {
        _bubbles.add(Bubble('user', text, contentBlocks: imageBlocks));
        _bubbles.add(Bubble('assistant', '')); // 流式占位，逐段填充
      }
    });
    _scrollToBottom();
    void updateLast(String text, {bool failed = false}) {
      if (!mounted) return;
      setState(() {
        _bubbles[_bubbles.length - 1] = Bubble(
          'assistant',
          text,
          failed: failed,
        );
      });
    }

    void showFailure(String message, {required bool retryable}) {
      if (!retrying && _bubbles[userIndex].messageId == null) {
        setState(() => _bubbles.removeRange(userIndex, _bubbles.length));
        _inputCtrl.text = text;
        _draftImages.addAll(drafts);
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(tr("发送失败，问题已保留在输入框，请重试"))));
      } else {
        updateLast(message, failed: retryable);
      }
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
        retryMessageId: retryMessageId,
        assetIds: imageBlocks
            .whereType<Map>()
            .where((b) => b['type'] == 'image')
            .map((b) => b['asset_id'] as String)
            .toList(),
        onMeta: (meta) {
          if (mounted) {
            _conversationId =
                meta['conversation_id'] as int? ?? _conversationId;
            final id = meta['user_message_id'] as int?;
            if (id != null) {
              setState(
                () => _bubbles[userIndex] = Bubble(
                  'user',
                  text,
                  messageId: id,
                  contentBlocks: imageBlocks,
                ),
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
      final mid = done['message_id'] as int?;
      if (mid == null) throw ApiException(503, tr("老师回复中断，请重试"));
      _bubbles[_bubbles.length - 1] = Bubble(
        'assistant',
        _bubbles.last.text.isEmpty ? tr("（没有收到内容）") : _bubbles.last.text,
        messageId: mid,
        imageJob: done['image_job'] as Map<String, dynamic>?,
      );
      _startImagePolling();
      _loadSessions();
    } on ApiException catch (e) {
      // 401 已由全局 _onSessionExpired 统一处理（清会话回绑定页）
      if (retrying && e.status == 409) {
        try {
          await _refreshCurrentConversation();
          if (mounted) {
            ScaffoldMessenger.of(
              context,
            ).showSnackBar(SnackBar(content: Text(tr("会话已更新，请查看老师回复"))));
          }
        } catch (_) {
          updateLast(tr("⚠️ 会话状态已变化，请重新打开聊天记录"), failed: true);
        }
      } else {
        final canRetry = _bubbles[userIndex].messageId != null;
        showFailure(
          '⚠️ ${e.message}',
          retryable:
              e.status == 503 && canRetry && !e.rawMessage.contains('请新开会话'),
        );
      }
      if (e.status != 401 && e.status != 503 && e.status != 409 && mounted) {
        await _policyDialog(e);
      }
    } catch (_) {
      final canRetry = _bubbles[userIndex].messageId != null;
      showFailure(tr("⚠️ 老师回复失败，请检查网络后重试"), retryable: canRetry);
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

  Future<void> _deleteAccount() async {
    if (_loggingOut) return;
    final navigator = Navigator.of(context);
    navigator.pop();
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(tr("删除学生账号？")),
        content: Text(
          tr("删除后将立即退出并解绑设备，家长会收到通知。学习记录仍由家长保留；如需删除学习数据，请联系家长。继续使用需重新绑定。"),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: Text(tr("取消")),
          ),
          FilledButton(
            style: FilledButton.styleFrom(
              backgroundColor: Theme.of(ctx).colorScheme.error,
            ),
            onPressed: () => Navigator.pop(ctx, true),
            child: Text(tr("删除账号")),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    setState(() => _loggingOut = true);
    try {
      await Api.I.deleteStudentAccount();
      if (!mounted) return;
      navigator.pushAndRemoveUntil(
        MaterialPageRoute(builder: (_) => const BindScreen()),
        (_) => false,
      );
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(tr("删除失败，请检查网络后重试"))));
      }
    } finally {
      if (mounted) setState(() => _loggingOut = false);
    }
  }

  Future<void> _logout() async {
    if (_loggingOut) return;
    final navigator = Navigator.of(context);
    navigator.pop(); // 关闭抽屉，让退出状态在页面上可见。
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(tr("退出登录？")),
        content: Text(tr("退出后需要家长端重新生成绑定码才能使用。聊天记录会保留。")),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: Text(tr("取消")),
          ),
          FilledButton(
            onPressed: () => Navigator.of(ctx).pop(true),
            child: Text(tr("退出")),
          ),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    setState(() => _loggingOut = true);
    final messenger = ScaffoldMessenger.of(context);
    messenger.showSnackBar(
      SnackBar(content: Text(tr("正在退出登录…")), duration: Duration(seconds: 30)),
    );
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
        messenger.showSnackBar(SnackBar(content: Text(tr("退出失败，请重试"))));
      }
    } finally {
      if (mounted) setState(() => _loggingOut = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    AppLanguage.watch(context);
    return Scaffold(
      appBar: AppBar(
        toolbarHeight:
            64 * MediaQuery.textScalerOf(context).scale(1).clamp(1, 1.5),
        actions: [
          const LanguageButton(),
          IconButton(
            tooltip: tr("学习反馈与小行星"),
            icon: const Icon(Icons.auto_awesome),
            onPressed: _openLearning,
          ),
        ],
        title: Tooltip(
          message: _teacherLoadFailed ? tr("重试加载老师") : tr("选择老师"),
          child: InkWell(
            borderRadius: BorderRadius.circular(8),
            onTap: _loadingTeachers || _selectingTeacher
                ? null
                : _teacherLoadFailed
                ? _loadTeachers
                : _teachers == null
                ? null
                : _chooseTeacher,
            child: Row(
              children: [
                _teacherAvatar(_teacherAvatarUrl),
                const SizedBox(width: 10),
                Flexible(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Flexible(
                            child: Text(
                              localizedTeacherName(_teacherName),
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                          const SizedBox(width: 2),
                          if (_loadingTeachers || _selectingTeacher)
                            const SizedBox(
                              width: 20,
                              height: 20,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          else
                            Icon(
                              _teacherLoadFailed
                                  ? Icons.refresh
                                  : Icons.keyboard_arrow_down,
                            ),
                        ],
                      ),
                      Text(
                        tr("受保护学习空间"),
                        style: TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
        leading: Builder(
          builder: (ctx) => IconButton(
            icon: const Icon(Icons.menu),
            tooltip: tr("聊天记录"),
            onPressed: () {
              FocusManager.instance.primaryFocus?.unfocus();
              _loadSessions();
              Scaffold.of(ctx).openDrawer();
            },
          ),
        ),
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
        onDeleteAccount: _deleteAccount,
        onOpenSession: _openSession,
        onSessionMenu: _sessionMenu,
        onRetrySessions: _loadSessions,
      ),
      body: Column(
        children: [
          if (MediaQuery.viewInsetsOf(context).bottom == 0)
            DailyIncentiveCard(
              summary: _dailyLearning,
              error: _dailyLearningError,
              onOpen: _openLearning,
              onRetry: _loadDailyLearning,
            ),
          if (_restoringLatest) ...[
            const LinearProgressIndicator(minHeight: 2),
            Padding(
              padding: EdgeInsets.symmetric(vertical: 6),
              child: Text(tr("正在恢复上次对话…"), style: TextStyle(fontSize: 12)),
            ),
          ],
          Expanded(child: _bubbles.isEmpty ? _emptyState() : _messageList()),
          if (_draftImages.isNotEmpty)
            Padding(padding: const EdgeInsets.all(8), child: _imageDrafts()),
          if (_uploadingImage) const LinearProgressIndicator(minHeight: 2),
          _inputBar(),
        ],
      ),
    );
  }

  Widget _emptyState() {
    return LayoutBuilder(
      builder: (context, constraints) {
        return SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: ConstrainedBox(
            constraints: BoxConstraints(
              minHeight: math.max(0, constraints.maxHeight - 48),
            ),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Center(
                  child: CircleAvatar(
                    radius: 32,
                    backgroundColor: Theme.of(
                      context,
                    ).colorScheme.primaryContainer,
                    child: Icon(
                      Icons.lightbulb_outline_rounded,
                      size: 32,
                      color: Theme.of(context).colorScheme.primary,
                    ),
                  ),
                ),
                const SizedBox(height: 20),
                Text(
                  tr("你好！今天想学什么？"),
                  textAlign: TextAlign.center,
                  style: TextStyle(fontSize: 23, fontWeight: FontWeight.w800),
                ),
                const SizedBox(height: 8),
                Text(
                  tr("从一个小问题开始，一步步学会"),
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: Theme.of(context).colorScheme.onSurfaceVariant,
                  ),
                ),
                const SizedBox(height: 24),
                for (final suggestion in [
                  (Icons.route_outlined, tr("理清解题思路"), tr("请帮我理清这道题的思路：")),
                  (
                    Icons.auto_stories_outlined,
                    tr("讲懂一个知识点"),
                    tr("请用简单的例子讲解这个知识点："),
                  ),
                  (Icons.edit_note_rounded, tr("一起做练习"), tr("请围绕这个知识点出一道练习题：")),
                ])
                  Card(
                    child: ListTile(
                      leading: Icon(suggestion.$1),
                      title: Text(suggestion.$2),
                      trailing: const Icon(Icons.north_west_rounded, size: 18),
                      onTap: () {
                        _inputCtrl.text = suggestion.$3;
                        _inputCtrl.selection = TextSelection.collapsed(
                          offset: _inputCtrl.text.length,
                        );
                        _inputFocus.requestFocus();
                      },
                    ),
                  ),
                const SizedBox(height: 4),
                Text(
                  tr("选择建议后，补充你的题目或知识点"),
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: 12,
                    color: Theme.of(context).colorScheme.onSurfaceVariant,
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _messageList() {
    return ListView.builder(
      controller: _scrollCtrl,
      padding: const EdgeInsets.symmetric(vertical: 12),
      keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
      itemCount: _bubbles.length,
      itemBuilder: (_, i) => MessageBubble(
        bubble: _bubbles[i],
        onDiagram:
            _imageCapabilities['image_output'] == true &&
                !_sending &&
                !_diagramRequests.contains(_bubbles[i].messageId)
            ? () => _requestDiagram(_bubbles[i])
            : null,
        feedback: _learningSelections['${_bubbles[i].messageId}'] as String?,
        onFeedback:
            _sending ||
                _uploadingImage ||
                _openingSession ||
                _selectingTeacher ||
                _sessionActionPending ||
                _feedbackPending.contains(_bubbles[i].messageId)
            ? null
            : (action) => _feedback(_bubbles[i], action),
        onLongPress: () => _messageMenu(_bubbles[i]),
        onRetry:
            _bubbles[i].failed && i == _bubbles.length - 1 && i > 0 && !_sending
            ? () => _send(retryUserIndex: i - 1)
            : null,
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
              if (_imageCapabilities['image_input'] == true)
                IconButton(
                  tooltip: tr('添加题目图片'),
                  icon: const Icon(Icons.add_photo_alternate_outlined),
                  onPressed:
                      _sending ||
                          _uploadingImage ||
                          _openingSession ||
                          _selectingTeacher ||
                          _draftImages.length >= 3
                      ? null
                      : _pickImage,
                ),
              Expanded(
                child: TextField(
                  controller: _inputCtrl,
                  focusNode: _inputFocus,
                  minLines: 1,
                  maxLines: 5,
                  textInputAction: TextInputAction.send,
                  onSubmitted: (_) => _send(),
                  decoration: InputDecoration(
                    hintText: tr("问一个学习问题…"),
                    filled: false,
                    border: InputBorder.none,
                    enabledBorder: InputBorder.none,
                    focusedBorder: InputBorder.none,
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
                          _uploadingImage ||
                          _openingSession ||
                          _selectingTeacher ||
                          _sessionActionPending
                      ? null
                      : _send,
                  tooltip: tr("发送问题"),
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

class _DraftImage {
  final Uint8List bytes;
  Map<String, dynamic>? block;
  bool error = false;
  _DraftImage(this.bytes);
}
