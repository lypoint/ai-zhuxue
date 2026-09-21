import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:gpt_markdown/gpt_markdown.dart';
import '../../core/api.dart';

/// 学生端：绑定（输入家长端绑定码）→ 学习聊天（围栏内）。
class StudentApp extends StatelessWidget {
  const StudentApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'AI 助学 - 学生端',
      theme: ThemeData(colorSchemeSeed: const Color(0xFF15857A), useMaterial3: true),
      home: Api.I.hasToken ? const ChatScreen() : const BindScreen(),
    );
  }
}

class BindScreen extends StatefulWidget {
  const BindScreen({super.key});
  @override
  State<BindScreen> createState() => _BindScreenState();
}

class _BindScreenState extends State<BindScreen> {
  final _codeCtrl = TextEditingController();
  String? _error;
  bool _loading = false;

  Future<void> _bind() async {
    setState(() { _loading = true; _error = null; });
    try {
      final deviceId = 'dev-${DateTime.now().millisecondsSinceEpoch}';
      await Api.I.studentLogin(_codeCtrl.text.trim().toUpperCase(), deviceId, '我的孩子');
      if (!mounted) return;
      Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (_) => const ChatScreen()));
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('绑定家长端')),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text('请输入家长端生成的 8 位绑定码', style: TextStyle(fontSize: 16)),
            const SizedBox(height: 16),
            TextField(
              controller: _codeCtrl,
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 24, letterSpacing: 4),
              decoration: InputDecoration(
                hintText: '如 A3F9C2B1',
                errorText: _error,
                border: const OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 16),
            FilledButton(
              onPressed: _loading ? null : _bind,
              child: Text(_loading ? '绑定中…' : '绑定并开始学习'),
            ),
          ],
        ),
      ),
    );
  }
}

class ChatScreen extends StatefulWidget {
  const ChatScreen({super.key});
  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final _inputCtrl = TextEditingController();
  final _scrollCtrl = ScrollController();
  final List<_Bubble> _bubbles = [];
  int? _conversationId;
  bool _sending = false;
  List<dynamic>? _sessions;
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
    _startHeartbeat();
  }

  Future<void> _restore() async {
    try {
      final data = await Api.I.latestConversation();
      final convId = data['conversation_id'] as int?;
      final msgs = (data['messages'] as List?) ?? const [];
      if (convId != null && msgs.isNotEmpty && mounted) {
        setState(() {
          _conversationId = convId;
          for (final m in msgs) {
            _bubbles.add(_Bubble(m['role'] as String, m['content'] as String));
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
      setState(() {
        _conversationId = conversationId;
        _bubbles.clear();
        for (final m in msgs) {
          _bubbles.add(_Bubble(m['role'] as String, m['content'] as String,
              messageId: m['id'] as int?));
        }
      });
      _scrollToBottom();
    } on ApiException catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  /// 消息长按菜单：复制 / 收藏（P2 学习沉淀）
  Future<void> _messageMenu(_Bubble b) async {
    final action = await showModalBottomSheet<String>(
      context: context,
      builder: (ctx) => SafeArea(child: Column(mainAxisSize: MainAxisSize.min, children: [
        ListTile(leading: const Icon(Icons.copy), title: const Text('复制全文（含公式源码）'),
            onTap: () => Navigator.of(ctx).pop('copy')),
        ListTile(leading: const Icon(Icons.star_border), title: const Text('收藏'),
            onTap: () => Navigator.of(ctx).pop('favorite')),
      ])),
    );
    if (!mounted || action == null) return;
    if (action == 'copy') {
      await Clipboard.setData(ClipboardData(text: b.text));
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('已复制到剪贴板'), duration: Duration(seconds: 1)));
      }
    } else if (action == 'favorite') {
      if (b.messageId == null) {
        ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('该消息暂不支持收藏'), duration: Duration(seconds: 1)));
        return;
      }
      try {
        await Api.I.addFavorite(b.messageId!);
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(content: Text('已收藏 ⭐ 可在抽屉「我的收藏」查看')));
        }
      } on ApiException catch (e) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
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
        actions: [FilledButton(onPressed: () => Navigator.of(ctx).pop(), child: const Text('好的'))],
      ));
  }

  List<dynamic> get _filteredSessions {
    final all = _sessions ?? const [];
    if (_search.isEmpty) return all;
    return all
        .where((e) => (e as Map<String, dynamic>)['title']
            .toString()
            .toLowerCase()
            .contains(_search.toLowerCase()))
        .toList();
  }

  /// 抽屉长按菜单：重命名 / 置顶 / 删除（Codex 风格会话管理）
  Future<void> _sessionMenu(Map<String, dynamic> c) async {
    final cid = c['conversation_id'] as int;
    final action = await showModalBottomSheet<String>(
      context: context,
      builder: (ctx) => SafeArea(child: Column(mainAxisSize: MainAxisSize.min, children: [
        ListTile(leading: const Icon(Icons.edit), title: const Text('重命名'),
            onTap: () => Navigator.of(ctx).pop('rename')),
        ListTile(
            leading: Icon(c['pinned'] == true ? Icons.push_pin_outlined : Icons.push_pin),
            title: Text(c['pinned'] == true ? '取消置顶' : '置顶'),
            onTap: () => Navigator.of(ctx).pop('pin')),
        ListTile(leading: const Icon(Icons.delete_outline, color: Colors.red),
            title: const Text('删除会话', style: TextStyle(color: Colors.red)),
            onTap: () => Navigator.of(ctx).pop('delete')),
      ])),
    );
    if (!mounted || action == null) return;
    if (action == 'rename') {
      final ctrl = TextEditingController(text: c['title'] as String? ?? '');
      final title = await showDialog<String>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('重命名会话'),
          content: TextField(controller: ctrl, autofocus: true,
              maxLength: 100, decoration: const InputDecoration(hintText: '会话标题')),
          actions: [
            TextButton(onPressed: () => Navigator.of(ctx).pop(), child: const Text('取消')),
            FilledButton(onPressed: () => Navigator.of(ctx).pop(ctrl.text.trim()),
                child: const Text('保存')),
          ],
        ),
      );
      if (title == null || title.isEmpty || !mounted) return;
      try {
        await Api.I.renameSession(cid, title);
        await _loadSessions();
      } on ApiException catch (e) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
        }
      }
    } else if (action == 'pin') {
      try {
        await Api.I.pinSession(cid, c['pinned'] != true);
        await _loadSessions();
      } on ApiException catch (e) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
        }
      }
    } else if (action == 'delete') {
      final confirmed = await showDialog<bool>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('删除会话？'),
          content: const Text('该会话的全部消息将被删除，且家长端不再可见。此操作不可撤销。'),
          actions: [
            TextButton(onPressed: () => Navigator.of(ctx).pop(false), child: const Text('取消')),
            FilledButton(
              style: FilledButton.styleFrom(backgroundColor: Colors.red),
              onPressed: () => Navigator.of(ctx).pop(true),
              child: const Text('删除')),
          ],
        ),
      );
      if (confirmed != true || !mounted) return;
      try {
        await Api.I.deleteSession(cid);
        if (_conversationId == cid) {
          setState(() {
            _conversationId = null;
            _bubbles.clear();
          });
        }
        await _loadSessions();
      } on ApiException catch (e) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
        }
      }
    }
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollCtrl.hasClients) {
        _scrollCtrl.animateTo(_scrollCtrl.position.maxScrollExtent,
            duration: const Duration(milliseconds: 200), curve: Curves.easeOut);
      }
    });
  }

  Future<void> _send() async {
    final text = _inputCtrl.text.trim();
    if (text.isEmpty || _sending) return;
    _inputCtrl.clear();
    setState(() {
      _sending = true;
      _bubbles.add(_Bubble('user', text));
      _bubbles.add(_Bubble('assistant', '')); // 流式占位，逐段填充
    });
    _scrollToBottom();
    void updateLast(String text) {
      setState(() {
        _bubbles[_bubbles.length - 1] = _Bubble('assistant', text);
      });
    }

    try {
      final done = await Api.I.sendChatStream(_conversationId, text,
          onMeta: (meta) => _conversationId = meta['conversation_id'] as int? ?? _conversationId,
          onDelta: (delta) {
            updateLast(_bubbles.last.text + delta);
            _scrollToBottom();
          });
      if (_bubbles.last.text.isEmpty) updateLast('（没有收到内容）');
      // 记录 message_id 以支持收藏
      final mid = done['message_id'] as int?;
      if (mid != null) {
        _bubbles[_bubbles.length - 1] =
            _Bubble('assistant', _bubbles.last.text, messageId: mid);
      }
      _loadSessions();
    } on ApiException catch (e) {
      updateLast('⚠️ ${e.message}');
      if (mounted) await _policyDialog(e);
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('AI 学习助手'),
        leading: Builder(builder: (ctx) => IconButton(
          icon: const Icon(Icons.menu), tooltip: '聊天记录',
          onPressed: () { _loadSessions(); Scaffold.of(ctx).openDrawer(); },
        )),
      ),
      drawer: Drawer(
        child: SafeArea(
          child: Column(children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
              child: FilledButton.icon(
                onPressed: _newChat,
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
                onChanged: (v) => setState(() => _search = v.trim()),
              ),
            ),
            const Divider(height: 1),
            ListTile(
              leading: const Icon(Icons.insights),
              title: const Text('我的学习统计'),
              onTap: () async {
                Navigator.of(context).pop();
                await Navigator.of(context).push(
                    MaterialPageRoute(builder: (_) => const MyStatsScreen()));
              },
            ),
            ListTile(
              leading: const Icon(Icons.star_border),
              title: const Text('我的收藏'),
              onTap: () async {
                Navigator.of(context).pop();
                await Navigator.of(context).push(
                    MaterialPageRoute(builder: (_) => const FavoritesScreen()));
              },
            ),
            ListTile(
              leading: const Icon(Icons.logout),
              title: const Text('退出登录'),
              onTap: () async {
                final drawerCtx = context;
                final navigator = Navigator.of(drawerCtx);
                final ok = await showDialog<bool>(
                  context: drawerCtx,
                  builder: (ctx) => AlertDialog(
                    title: const Text('退出登录？'),
                    content: const Text('退出后需要家长端重新生成绑定码才能使用。聊天记录会保留。'),
                    actions: [
                      TextButton(onPressed: () => Navigator.of(ctx).pop(false), child: const Text('取消')),
                      FilledButton(onPressed: () => Navigator.of(ctx).pop(true), child: const Text('退出')),
                    ],
                  ));
                if (ok != true || !mounted) return;
                await Api.I.logout();
                navigator.pushReplacement(
                    MaterialPageRoute(builder: (_) => const BindScreen()));
              },
            ),
            Expanded(
              child: _sessions == null
                  ? const Center(child: CircularProgressIndicator())
                  : _filteredSessions.isEmpty
                      ? Center(child: Text(_search.isEmpty ? '还没有聊天记录' : '没有匹配的会话'))
                      : ListView.builder(
                          itemCount: _filteredSessions.length,
                          itemBuilder: (_, i) {
                            final c = _filteredSessions[i] as Map<String, dynamic>;
                            final selected = c['conversation_id'] == _conversationId;
                            return ListTile(
                              selected: selected,
                              leading: Icon(selected ? Icons.chat_bubble : Icons.chat_bubble_outline,
                                  size: 20),
                              title: Row(children: [
                                if (c['pinned'] == true) ...[
                                  const Icon(Icons.push_pin, size: 13, color: Color(0xFF15857A)),
                                  const SizedBox(width: 4),
                                ],
                                Expanded(child: Text(c['title'] as String? ?? '',
                                    maxLines: 1, overflow: TextOverflow.ellipsis)),
                              ]),
                              subtitle: Text('${c['message_count']} 条 · ${(c['last_time'] ?? '').toString().replaceAll('T', ' ').sliceSafe(0, 16)}',
                                  style: const TextStyle(fontSize: 11)),
                              onTap: () => _openSession(c['conversation_id'] as int),
                              onLongPress: () => _sessionMenu(c),
                            );
                          },
                        ),
            ),
          ]),
        ),
      ),
      body: Column(children: [
        Expanded(
          child: _bubbles.isEmpty
              ? const Center(child: Text('你好！今天想学什么？可以问我作业和知识点。'))
              : ListView.builder(
                  controller: _scrollCtrl,
                  itemCount: _bubbles.length,
                  itemBuilder: (_, i) {
                    final b = _bubbles[i];
                    final isUser = b.role == 'user';
                    return Align(
                      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
                      child: GestureDetector(
                      onLongPress: () => _messageMenu(b),
                      child: Container(
                        margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                        constraints: BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.75),
                        decoration: BoxDecoration(
                          color: isUser ? const Color(0xFF15857A) : Colors.grey.shade200,
                          borderRadius: BorderRadius.circular(14),
                        ),
                        child: isUser
                            ? Text(b.text, style: const TextStyle(color: Colors.white))
                            : GptMarkdown(b.text,
                                style: const TextStyle(color: Colors.black87, height: 1.4),
                                useDollarSignsForLatex: true),
                      ),
                      ),
                    );
                  },
                ),
        ),
        SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(12, 4, 12, 8),
            child: Row(children: [
              Expanded(
                child: TextField(
                  controller: _inputCtrl,
                  onSubmitted: (_) {
                    _send();
                  },
                  decoration: const InputDecoration(hintText: '只能讨论学习内容哦',
                      border: OutlineInputBorder()),
                ),
              ),
              IconButton.filled(onPressed: _sending ? null : _send, icon: const Icon(Icons.send)),
            ]),
          ),
        ),
      ]),
    );
  }
}

class _Bubble {
  final String role;
  final String text;
  final int? messageId;
  _Bubble(this.role, this.text, {this.messageId});
}


extension _SliceSafe on String {
  String sliceSafe(int start, int end) => length <= start ? '' : substring(start, end > length ? length : end);
}


/// 我的收藏（P2 学习沉淀）：知识点/解答随时回看，家长端同步可见
class FavoritesScreen extends StatefulWidget {
  const FavoritesScreen({super.key});
  @override
  State<FavoritesScreen> createState() => _FavoritesScreenState();
}

class _FavoritesScreenState extends State<FavoritesScreen> {
  List<dynamic>? _favs;

  @override
  void initState() { super.initState(); _load(); }

  Future<void> _load() async {
    final list = await Api.I.myFavorites();
    if (!mounted) return;
    setState(() => _favs = list);
  }

  Future<void> _remove(int id) async {
    await Api.I.deleteFavorite(id);
    _load();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('我的收藏 ⭐')),
      body: _favs == null
          ? const Center(child: CircularProgressIndicator())
          : _favs!.isEmpty
              ? const Center(child: Text('长按聊天消息即可收藏'))
              : ListView.builder(
                  padding: const EdgeInsets.all(12),
                  itemCount: _favs!.length,
                  itemBuilder: (_, i) {
                    final f = _favs![i] as Map<String, dynamic>;
                    return Card(child: Padding(
                      padding: const EdgeInsets.fromLTRB(12, 8, 4, 8),
                      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Expanded(child: GptMarkdown(f['content'] as String? ?? '',
                            style: const TextStyle(color: Colors.black87, height: 1.4),
                            useDollarSignsForLatex: true)),
                        IconButton(
                          icon: const Icon(Icons.close, size: 18),
                          tooltip: '取消收藏',
                          onPressed: () => _remove(f['id'] as int),
                        ),
                      ]),
                    ));
                  },
                ),
    );
  }
}


/// 我的学习统计（P2 遗漏补齐）：学生自己可见，增强自我管理
class MyStatsScreen extends StatelessWidget {
  const MyStatsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('我的学习统计')),
      body: FutureBuilder<Map<String, dynamic>>(
        future: Api.I.myStats(),
        builder: (ctx, snap) {
          if (!snap.hasData) return const Center(child: CircularProgressIndicator());
          final d = snap.data!;
          return ListView(padding: const EdgeInsets.all(16), children: [
            _card('今天', [
              ['学习提问', '${d['today']['questions']} 次'],
              ['被拦截', '${d['today']['blocked']} 次'],
              ['学习时长', '约 ${d['today']['minutes']} 分钟'],
            ]),
            _card('本周', [
              ['学习提问', '${d['week']['questions']} 次'],
              ['被拦截', '${d['week']['blocked']} 次'],
              ['学习时长', '约 ${d['week']['minutes']} 分钟'],
              ['活跃天数', '${d['week']['active_days']} 天'],
              ['收藏知识点', '${d['favorites']} 条'],
            ]),
            const Padding(
              padding: EdgeInsets.all(12),
              child: Text('小提示：长按聊天消息可以收藏喜欢的内容哦 ⭐',
                  style: TextStyle(fontSize: 12, color: Colors.grey)),
            ),
          ]);
        },
      ),
    );
  }

  Widget _card(String title, List<List<String>> rows) {
    return Card(child: Padding(padding: const EdgeInsets.all(14), child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(title, style: const TextStyle(fontWeight: FontWeight.bold, color: Color(0xFF15857A))),
        const SizedBox(height: 8),
        ...rows.map((r) => Padding(
            padding: const EdgeInsets.symmetric(vertical: 3),
            child: Row(mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [Text(r[0]), Text(r[1], style: const TextStyle(fontWeight: FontWeight.w600))]))),
      ])));
  }
}
