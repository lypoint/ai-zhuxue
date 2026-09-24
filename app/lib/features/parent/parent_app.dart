import 'package:flutter/material.dart';
import 'package:gpt_markdown/gpt_markdown.dart';
import 'package:qr_flutter/qr_flutter.dart';
import '../../core/api.dart';
import '../../core/theme.dart';

/// 家长端：注册（三要素核验）→ 家庭总览（绑定码/管控设置）→ 全量审查孩子的对话与围栏流水。
class ParentApp extends StatelessWidget {
  const ParentApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'AI 助学 - 家长端',
      theme: appTheme(const Color(0xFF5367A8)),
      home: Api.I.hasToken ? const HomeScreen() : const LoginScreen(),
    );
  }
}

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});
  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _phone = TextEditingController();
  final _sms = TextEditingController();
  final _name = TextEditingController();
  final _id = TextEditingController();
  String? _error;
  bool _loading = false;

  Future<void> _register() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      await Api.I.registerGuardian(
        _phone.text.trim(),
        _sms.text.trim(),
        '家长',
        _name.text.trim(),
        _id.text.trim(),
      );
      if (!mounted) return;
      Navigator.of(
        context,
      ).pushReplacement(MaterialPageRoute(builder: (_) => const HomeScreen()));
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('家长端')),
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            colors: [Color(0xFFEFF2FF), Color(0xFFF6F8FB)],
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
          ),
        ),
        child: ListView(
          padding: const EdgeInsets.fromLTRB(24, 24, 24, 32),
          children: [
            Row(
              children: [
                CircleAvatar(
                  radius: 28,
                  backgroundColor: Theme.of(context).colorScheme.primary,
                  child: const Icon(
                    Icons.family_restroom,
                    color: Colors.white,
                    size: 28,
                  ),
                ),
                const SizedBox(width: 14),
                const Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        '建立受保护的学习空间',
                        style: TextStyle(
                          fontSize: 21,
                          fontWeight: FontWeight.w800,
                        ),
                      ),
                      SizedBox(height: 4),
                      Text(
                        '完成核验后，生成绑定码连接孩子设备',
                        style: TextStyle(color: Colors.black54),
                      ),
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: 24),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(18),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const Text(
                      '监护人信息',
                      style: TextStyle(
                        fontSize: 17,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    const SizedBox(height: 14),
                    TextField(
                      controller: _name,
                      decoration: const InputDecoration(
                        labelText: '监护人姓名',
                        prefixIcon: Icon(Icons.person_outline),
                      ),
                    ),
                    const SizedBox(height: 12),
                    TextField(
                      controller: _id,
                      decoration: const InputDecoration(
                        labelText: '身份证号',
                        prefixIcon: Icon(Icons.badge_outlined),
                      ),
                    ),
                    const SizedBox(height: 12),
                    TextField(
                      controller: _phone,
                      keyboardType: TextInputType.phone,
                      decoration: const InputDecoration(
                        labelText: '手机号',
                        prefixIcon: Icon(Icons.phone_outlined),
                      ),
                    ),
                    const SizedBox(height: 12),
                    TextField(
                      controller: _sms,
                      keyboardType: TextInputType.number,
                      decoration: const InputDecoration(
                        labelText: '短信验证码',
                        helperText: '开发模式验证码：123456',
                        prefixIcon: Icon(Icons.verified_user_outlined),
                      ),
                    ),
                    const SizedBox(height: 18),
                    FilledButton.icon(
                      onPressed: _loading ? null : _register,
                      icon: const Icon(Icons.arrow_forward),
                      label: Text(_loading ? '核验中…' : '核验并注册'),
                    ),
                    if (_error != null)
                      Padding(
                        padding: const EdgeInsets.only(top: 12),
                        child: Text(
                          _error!,
                          style: TextStyle(
                            color: Theme.of(context).colorScheme.error,
                          ),
                        ),
                      ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});
  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  Map<String, dynamic>? _family;
  String? _bindCode;
  final _capCtrl = TextEditingController();
  bool _quietEnabled = true;
  int _quietStart = 22, _quietEnd = 6;
  final _minutesCtrl = TextEditingController();
  bool _notifyFence = true;
  bool _showOnboarding = false;

  Future<void> _makeCode() async {
    final data = await Api.I.createBindCode();
    setState(() => _bindCode = data['code'] as String);
  }

  Future<void> _saveSettings() async {
    final s = _family?['settings'];
    await Api.I.updateSettings(
      int.tryParse(_capCtrl.text) ?? 200,
      s?['review_enabled'] as bool? ?? true,
      quietEnabled: _quietEnabled,
      quietStart: _quietStart,
      quietEnd: _quietEnd,
      dailyMinutesCap: int.tryParse(_minutesCtrl.text) ?? 60,
      notifyFence: _notifyFence,
    );
    if (!mounted) return;
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(const SnackBar(content: Text('已保存')));
    _refresh();
  }

  Map<String, dynamic>? _subscription;
  int _unread = 0;

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  Future<void> _refresh() async {
    Map<String, dynamic> data;
    try {
      data = await Api.I.familyOverview();
    } on ApiException catch (e) {
      // token 失效（登出吊销/过期）：清本地会话并回登录页，避免白屏死路
      if (e.status == 401 && mounted) {
        await Api.I.logout();
        if (!mounted) return;
        Navigator.of(context).pushReplacement(
          MaterialPageRoute(builder: (_) => const LoginScreen()),
        );
      }
      return;
    }
    final settings = data['settings'] as Map<String, dynamic>;
    _capCtrl.text = (settings['daily_message_cap'] as num).toString();
    _minutesCtrl.text = (settings['daily_minutes_cap'] as num).toString();
    _quietEnabled = settings['quiet_enabled'] as bool? ?? true;
    _quietStart = settings['quiet_start'] as int? ?? 22;
    _quietEnd = settings['quiet_end'] as int? ?? 6;
    _notifyFence = settings['notify_fence'] as bool? ?? true;
    Map<String, dynamic>? sub;
    int unread = 0;
    try {
      sub = await Api.I.subscription();
    } on ApiException {
      sub = null;
    }
    try {
      unread = (await Api.I.notifications(unreadOnly: true))['unread'] as int;
    } on ApiException {
      // 通知不可用不阻塞首页
    }
    if (!mounted) return;
    // P2 新用户引导：试用期内且还没有孩子绑定时展示
    final showGuide =
        (data['students'] as List).isEmpty && (sub?['plan'] == 'free_trial');
    setState(() {
      _family = data;
      _subscription = sub;
      _unread = unread;
      _showOnboarding = showGuide;
    });
  }

  Future<void> _renameStudent(Map<String, dynamic> s) async {
    final ctrl = TextEditingController(text: s['nickname'] as String? ?? '');
    final name = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('修改昵称'),
        content: TextField(controller: ctrl, autofocus: true, maxLength: 50),
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
    if (name == null || name.isEmpty || !mounted) return;
    try {
      await Api.I.setStudentNickname(s['id'] as int, name);
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('已改名为 $name')));
      _refresh();
    } on ApiException catch (e) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  Future<void> _pay() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('确认续费'),
        content: const Text('AI 助学 · 月度订阅\n¥66.00 / 月（支付通道为演示模式）'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('确认支付'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    try {
      await Api.I.paySubscription();
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('续费成功！')));
      _refresh();
    } on ApiException catch (e) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  Future<void> _logout() async {
    await Api.I.logout();
    if (!mounted) return;
    Navigator.of(
      context,
    ).pushReplacement(MaterialPageRoute(builder: (_) => const LoginScreen()));
  }

  @override
  Widget build(BuildContext context) {
    final family = _family;
    if (family == null) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    final students = (family['students'] as List).cast<Map<String, dynamic>>();
    final sub = _subscription;
    return Scaffold(
      appBar: AppBar(
        title: const Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('家长端'),
            Text(
              '家庭学习控制台',
              style: TextStyle(fontSize: 11, fontWeight: FontWeight.w500),
            ),
          ],
        ),
        actions: [
          IconButton(
            onPressed: _makeCode,
            icon: const Icon(Icons.qr_code_2),
            tooltip: '生成绑定码',
          ),
          Stack(
            children: [
              IconButton(
                onPressed: () async {
                  await Navigator.of(context).push(
                    MaterialPageRoute(
                      builder: (_) => const NotificationsScreen(),
                    ),
                  );
                  _refresh();
                },
                icon: const Icon(Icons.notifications_none),
                tooltip: '通知',
              ),
              if (_unread > 0)
                Positioned(right: 8, top: 8, child: Badge(count: _unread)),
            ],
          ),
          PopupMenuButton<String>(
            onSelected: (v) {
              if (v == 'logout') _logout();
            },
            itemBuilder: (_) => const [
              PopupMenuItem(value: 'logout', child: Text('退出登录')),
            ],
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          if (sub != null) _SubscriptionCard(sub: sub, onPay: _pay),
          if (_showOnboarding)
            Card(
              color: const Color(0xFFFFF8E7),
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      '🎉 欢迎使用 AI 助学',
                      style: TextStyle(fontWeight: FontWeight.bold),
                    ),
                    const SizedBox(height: 6),
                    const Text(
                      '三步开始：\n1. 点右上角 📱 生成绑定码\n2. 在孩子设备安装学生端，输入绑定码\n3. 在下方设置休息时段与每日上限',
                      style: TextStyle(fontSize: 13, height: 1.5),
                    ),
                    const SizedBox(height: 8),
                    Align(
                      alignment: Alignment.centerRight,
                      child: TextButton(
                        onPressed: () =>
                            setState(() => _showOnboarding = false),
                        child: const Text('我知道了'),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          Card(
            child: ListTile(
              leading: const Icon(Icons.family_restroom),
              title: Text(family['guardian']['nickname'] as String? ?? '家长'),
              subtitle: Text('家庭 · ${students.length} 个孩子'),
            ),
          ),
          const SizedBox(height: 8),
          ...students.map(
            (s) => Card(
              child: ListTile(
                leading: const Icon(Icons.face),
                title: Row(
                  children: [
                    Expanded(child: Text(s['nickname'] as String? ?? '')),
                    IconButton(
                      icon: const Icon(Icons.edit, size: 16),
                      tooltip: '修改昵称',
                      onPressed: () => _renameStudent(s),
                    ),
                  ],
                ),
                subtitle: Text('学段 ${s['grade_band']}'),
                trailing: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    DropdownButton<String>(
                      value: s['grade_band'] as String,
                      underline: const SizedBox(),
                      items: const [
                        DropdownMenuItem(
                          value: '8-12',
                          child: Text('8-12岁', style: TextStyle(fontSize: 12)),
                        ),
                        DropdownMenuItem(
                          value: '12-16',
                          child: Text('12-16岁', style: TextStyle(fontSize: 12)),
                        ),
                        DropdownMenuItem(
                          value: '16-18',
                          child: Text('16-18岁', style: TextStyle(fontSize: 12)),
                        ),
                      ],
                      onChanged: (v) async {
                        if (v == null || v == s['grade_band']) return;
                        final messenger = ScaffoldMessenger.of(context);
                        try {
                          await Api.I.setGradeBand(s['id'] as int, v);
                          messenger.showSnackBar(
                            SnackBar(content: Text('学段已设为 $v，将影响分龄内容与讲解风格')),
                          );
                          _refresh();
                        } on ApiException catch (e) {
                          messenger.showSnackBar(
                            SnackBar(content: Text(e.message)),
                          );
                        }
                      },
                    ),
                    IconButton(
                      icon: const Icon(Icons.star_border, size: 20),
                      tooltip: '孩子的收藏',
                      onPressed: () => Navigator.of(context).push(
                        MaterialPageRoute(
                          builder: (_) => ParentFavoritesScreen(
                            studentId: s['id'] as int,
                            studentName: s['nickname'] as String? ?? '',
                          ),
                        ),
                      ),
                    ),
                    const Icon(Icons.chevron_right),
                  ],
                ),
                onTap: () => Navigator.of(context).push(
                  MaterialPageRoute(
                    builder: (_) => ReviewScreen(
                      studentId: s['id'] as int,
                      studentName: s['nickname'] as String? ?? '',
                    ),
                  ),
                ),
              ),
            ),
          ),
          const SizedBox(height: 8),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    '未成年人模式管控',
                    style: TextStyle(fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 8),
                  TextField(
                    controller: _capCtrl,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(
                      labelText: '每日对话消息上限',
                      border: OutlineInputBorder(),
                    ),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: _minutesCtrl,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(
                      labelText: '每日使用时长上限（分钟，0=不限）',
                      border: OutlineInputBorder(),
                    ),
                  ),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      const Expanded(
                        child: Text(
                          '学习引导通知\n（拦截/改写类，安全告警不受此开关影响）',
                          style: TextStyle(fontSize: 12),
                        ),
                      ),
                      Switch(
                        value: _notifyFence,
                        onChanged: (v) => setState(() => _notifyFence = v),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      const Text('休息时段限制'),
                      const Spacer(),
                      Switch(
                        value: _quietEnabled,
                        onChanged: (v) => setState(() => _quietEnabled = v),
                      ),
                    ],
                  ),
                  if (_quietEnabled)
                    Row(
                      children: [
                        const Text('禁用时段'),
                        const SizedBox(width: 8),
                        DropdownButton<int>(
                          value: _quietStart,
                          items: [
                            for (var h = 0; h < 24; h++)
                              DropdownMenuItem(value: h, child: Text('$h:00')),
                          ],
                          onChanged: (v) {
                            if (v != null) setState(() => _quietStart = v);
                          },
                        ),
                        const Text(' 至 '),
                        DropdownButton<int>(
                          value: _quietEnd,
                          items: [
                            for (var h = 0; h < 24; h++)
                              DropdownMenuItem(value: h, child: Text('$h:00')),
                          ],
                          onChanged: (v) {
                            if (v != null) setState(() => _quietEnd = v);
                          },
                        ),
                      ],
                    ),
                  const SizedBox(height: 12),
                  OutlinedButton(
                    onPressed: _saveSettings,
                    child: const Text('保存设置'),
                  ),
                ],
              ),
            ),
          ),
          if (_bindCode != null)
            Card(
              color: const Color(0xFFE8F5F1),
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  children: [
                    const Text('学生端绑定码（10 分钟内有效）'),
                    const SizedBox(height: 8),
                    Text(
                      _bindCode!,
                      style: const TextStyle(
                        fontSize: 28,
                        letterSpacing: 6,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 8),
                    SizedBox(
                      width: 140,
                      height: 140,
                      child: QrImageView(data: _bindCode!, size: 140),
                    ),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class ReviewScreen extends StatefulWidget {
  final int studentId;
  final String studentName;
  const ReviewScreen({
    super.key,
    required this.studentId,
    required this.studentName,
  });
  @override
  State<ReviewScreen> createState() => _ReviewScreenState();
}

class _ReviewScreenState extends State<ReviewScreen> {
  List<dynamic>? _conversations;
  Map<String, dynamic>? _usage;
  Map<String, dynamic>? _summary;
  List<dynamic>? _searchHits;
  final _searchCtrl = TextEditingController();

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _doSearch() async {
    final q = _searchCtrl.text.trim();
    if (q.length < 2) return;
    try {
      final hits = await Api.I.searchConversations(widget.studentId, q);
      if (!mounted) return;
      setState(() => _searchHits = hits);
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  Future<void> _load() async {
    final list = await Api.I.conversations(widget.studentId);
    Map<String, dynamic>? usage;
    Map<String, dynamic>? summary;
    try {
      usage = await Api.I.studentUsage(widget.studentId);
    } on ApiException {
      usage = null;
    }
    try {
      summary = await Api.I.studentSummary(widget.studentId);
    } on ApiException {
      summary = null;
    }
    if (!mounted) return;
    setState(() {
      _conversations = list;
      _usage = usage;
      _summary = summary;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text('${widget.studentName} 的全部对话')),
      body: _conversations == null
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(12),
              children: [
                Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: TextField(
                    controller: _searchCtrl,
                    decoration: InputDecoration(
                      isDense: true,
                      prefixIcon: const Icon(Icons.search, size: 20),
                      hintText: '搜索消息内容（至少 2 字）',
                      border: const OutlineInputBorder(),
                      suffixIcon: IconButton(
                        icon: const Icon(Icons.search),
                        onPressed: _doSearch,
                      ),
                    ),
                    onSubmitted: (_) => _doSearch(),
                  ),
                ),
                if (_searchHits != null) ...[
                  Row(
                    children: [
                      Text(
                        '搜索结果 ${_searchHits!.length} 条',
                        style: const TextStyle(
                          fontSize: 12,
                          color: Colors.grey,
                        ),
                      ),
                      const Spacer(),
                      TextButton(
                        onPressed: () => setState(() => _searchHits = null),
                        child: const Text('返回全部'),
                      ),
                    ],
                  ),
                  ..._searchHits!.map((hit) {
                    final hitMap = hit as Map<String, dynamic>;
                    return Card(
                      child: ListTile(
                        dense: true,
                        leading: Icon(
                          hitMap['role'] == 'user'
                              ? Icons.person
                              : Icons.smart_toy,
                          size: 18,
                          color: hitMap['role'] == 'user'
                              ? const Color(0xFF1B2A4A)
                              : const Color(0xFF15857A),
                        ),
                        title: Text(
                          hitMap['snippet'] as String? ?? '',
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(fontSize: 13),
                        ),
                        subtitle: Text(
                          '会话: ${hitMap['title']}',
                          style: const TextStyle(fontSize: 11),
                        ),
                        onTap: () => Navigator.of(context).push(
                          MaterialPageRoute(
                            builder: (_) => ConversationDetailScreen(
                              conversationId: hitMap['conversation_id'] as int,
                              title: hitMap['title'] as String? ?? '',
                            ),
                          ),
                        ),
                      ),
                    );
                  }),
                ],
                if (_summary != null)
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(12),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text(
                            '学习摘要',
                            style: TextStyle(fontWeight: FontWeight.bold),
                          ),
                          const SizedBox(height: 6),
                          Text(
                            '今日：提问 ${_summary!['today']['questions']} 次 · 学习 ${_summary!['today']['study']} 次 · 引导 ${_summary!['today']['guided']} 次 · 拦截 ${_summary!['today']['blocked']} 次 · 约 ${_summary!['today']['minutes']} 分钟',
                            style: const TextStyle(fontSize: 12),
                          ),
                          Text(
                            '本周：提问 ${_summary!['week']['questions']} 次 · 活跃 ${_summary!['week']['active_days']} 天 · 拦截 ${_summary!['week']['blocked']} 次 · 约 ${_summary!['week']['minutes']} 分钟',
                            style: const TextStyle(
                              fontSize: 12,
                              color: Colors.grey,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                if (_usage != null)
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(12),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text(
                            'AI 用量（估算成本）',
                            style: TextStyle(fontWeight: FontWeight.bold),
                          ),
                          const SizedBox(height: 4),
                          Text(
                            '今日：tokens ${_usage!['today']['tokens_in']}+${_usage!['today']['tokens_out']}，约 ¥${_usage!['today']['cost']}',
                            style: const TextStyle(fontSize: 12),
                          ),
                          Text(
                            '累计：tokens ${_usage!['total']['tokens_in']}+${_usage!['total']['tokens_out']}，约 ¥${_usage!['total']['cost']}',
                            style: const TextStyle(
                              fontSize: 12,
                              color: Colors.grey,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                if (_conversations!.isEmpty)
                  const Padding(
                    padding: EdgeInsets.all(32),
                    child: Center(child: Text('还没有对话记录')),
                  ),
                ..._conversations!.map((c) {
                  final conv = c as Map<String, dynamic>;
                  return ListTile(
                    leading: const Icon(Icons.forum),
                    title: Text(conv['title'] as String? ?? ''),
                    subtitle: Text(
                      (conv['created_at'] as String? ?? '').replaceAll(
                        'T',
                        ' ',
                      ),
                    ),
                    onTap: () => Navigator.of(context).push(
                      MaterialPageRoute(
                        builder: (_) => ConversationDetailScreen(
                          conversationId: conv['id'] as int,
                          title: conv['title'] as String? ?? '',
                        ),
                      ),
                    ),
                  );
                }),
              ],
            ),
    );
  }
}

const _fenceStageLabel = {
  'whitelist': '白名单',
  'classifier': '分类',
  'second_pass': '复核',
  'policy': '处置',
};
const _fenceDecisionLabel = {'allow': '放行', 'rewrite': '改写', 'reject': '拦截'};
const _fenceCategoryLabel = {
  'study': '学习',
  'entertainment': '娱乐',
  'sensitive': '敏感',
  'other': '其他',
};

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
              itemBuilder: (_, i) {
                final m = _messages![i] as Map<String, dynamic>;
                final isUser = m['role'] == 'user';
                final events = _fenceByMessage![m['id'] as int] ?? const [];
                final action = m['fence_action'] as String?;
                return Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Align(
                      alignment: isUser
                          ? Alignment.centerRight
                          : Alignment.centerLeft,
                      child: Container(
                        margin: const EdgeInsets.symmetric(vertical: 4),
                        padding: const EdgeInsets.symmetric(
                          horizontal: 14,
                          vertical: 10,
                        ),
                        constraints: BoxConstraints(
                          maxWidth: MediaQuery.of(context).size.width * 0.78,
                        ),
                        decoration: BoxDecoration(
                          color: isUser
                              ? const Color(0xFF1B2A4A)
                              : Colors.grey.shade200,
                          borderRadius: BorderRadius.circular(14),
                        ),
                        child: isUser
                            ? Text(
                                m['content'] as String? ?? '',
                                style: const TextStyle(color: Colors.white),
                              )
                            : GptMarkdown(
                                m['content'] as String? ?? '',
                                style: const TextStyle(
                                  color: Colors.black87,
                                  height: 1.4,
                                ),
                                useDollarSignsForLatex: true,
                              ),
                      ),
                    ),
                    if (action != null)
                      Padding(
                        padding: const EdgeInsets.only(left: 8, bottom: 6),
                        child: Text(
                          '围栏：${_fenceDecisionLabel[action] ?? action} · ${events.map((e) => "${_fenceStageLabel[e['stage']] ?? e['stage']}/${_fenceCategoryLabel[e['category']] ?? e['category']}").join(' → ')}',
                          style: TextStyle(
                            fontSize: 11,
                            color: Colors.grey.shade600,
                          ),
                        ),
                      ),
                  ],
                );
              },
            ),
    );
  }
}

/// 订阅状态卡（P0 商业闭环）：试用/生效/到期 + 续费按钮
class _SubscriptionCard extends StatelessWidget {
  final Map<String, dynamic> sub;
  final VoidCallback onPay;
  const _SubscriptionCard({required this.sub, required this.onPay});

  @override
  Widget build(BuildContext context) {
    final active = sub['active'] == true;
    final trial = sub['plan'] == 'free_trial';
    final days = sub['days_left'] as num? ?? 0;
    return Card(
      color: active ? const Color(0xFFE8F5F1) : const Color(0xFFFDEDEC),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Row(
          children: [
            Icon(
              active ? Icons.verified : Icons.warning_amber_rounded,
              color: active ? const Color(0xFF15857A) : Colors.red,
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    active
                        ? (trial ? '免费试用中 · 剩余 $days 天' : '订阅生效中 · 剩余 $days 天')
                        : '订阅已到期',
                    style: const TextStyle(fontWeight: FontWeight.bold),
                  ),
                  Text(
                    active ? '到期后孩子将无法继续使用' : '续费后孩子即可继续学习',
                    style: const TextStyle(fontSize: 12, color: Colors.grey),
                  ),
                ],
              ),
            ),
            // 防御性约束：个别环境（模拟器 gfxstream）CJK 字形测量异常会使按钮
            // 占满整行、把 Expanded 文本列压成 40px；封顶宽度在正常设备上无视觉差异。
            ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 140),
              child: FilledButton(
                onPressed: onPay,
                child: Text(active ? '续费' : '立即开通'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// 未读角标
class Badge extends StatelessWidget {
  final int count;
  const Badge({super.key, required this.count});
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(4),
      decoration: const BoxDecoration(
        color: Colors.red,
        shape: BoxShape.circle,
      ),
      constraints: const BoxConstraints(minWidth: 16, minHeight: 16),
      child: Text(
        '$count',
        textAlign: TextAlign.center,
        style: const TextStyle(color: Colors.white, fontSize: 9),
      ),
    );
  }
}

/// 通知中心（P0 安全闭环）：security 安全告警置顶标红
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
              itemBuilder: (_, i) {
                final n = d['items'][i] as Map<String, dynamic>;
                final isSec = n['type'] == 'security';
                return Card(
                  color: !n['is_read']
                      ? (isSec
                            ? const Color(0xFFFDEDEC)
                            : const Color(0xFFF0F7F5))
                      : null,
                  child: ListTile(
                    leading: Icon(
                      n['type'] == 'security'
                          ? Icons.gpp_maybe
                          : Icons.chat_bubble_outline,
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
              },
            ),
    );
  }
}

/// 孩子的收藏（P2 学习沉淀，家长可见以了解兴趣点）
class ParentFavoritesScreen extends StatelessWidget {
  final int studentId;
  final String studentName;
  const ParentFavoritesScreen({
    super.key,
    required this.studentId,
    required this.studentName,
  });

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text('$studentName 的收藏')),
      body: FutureBuilder<List<dynamic>>(
        future: Api.I.studentFavorites(studentId),
        builder: (ctx, snap) {
          if (!snap.hasData) {
            return const Center(child: CircularProgressIndicator());
          }
          final items = snap.data!;
          if (items.isEmpty) return const Center(child: Text('还没有收藏内容'));
          return ListView.builder(
            padding: const EdgeInsets.all(12),
            itemCount: items.length,
            itemBuilder: (_, i) {
              final f = items[i] as Map<String, dynamic>;
              return Card(
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      GptMarkdown(
                        f['content'] as String? ?? '',
                        style: const TextStyle(
                          color: Colors.black87,
                          height: 1.4,
                        ),
                        useDollarSignsForLatex: true,
                      ),
                      const SizedBox(height: 4),
                      Text(
                        (f['created_at'] ?? '')
                            .toString()
                            .replaceAll('T', ' ')
                            .substring(0, 16),
                        style: const TextStyle(
                          fontSize: 11,
                          color: Colors.grey,
                        ),
                      ),
                    ],
                  ),
                ),
              );
            },
          );
        },
      ),
    );
  }
}
