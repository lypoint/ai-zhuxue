import 'package:flutter/material.dart';
import 'package:app_core/app_core.dart';
import 'package:qr_flutter/qr_flutter.dart';
import '../widgets/subscription_card.dart';
import '../widgets/notification_badge.dart';
import '../widgets/student_review_card.dart';
import '../widgets/management_settings_card.dart';
import 'notifications_screen.dart';
import 'login_screen.dart';

/// 家庭总览：订阅状态、绑定码、孩子列表（分龄/审查/收藏）、未成年人模式管控设置。
class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});
  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  Map<String, dynamic>? _family;
  String? _bindCode;
  String _bindLabel = '学生端绑定码';
  bool _showOnboarding = false;
  Map<String, dynamic>? _subscription;
  int _unread = 0;

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  Future<void> _makeCode() async {
    try {
      final data = await Api.I.createBindCode();
      if (!mounted) return;
      setState(() {
        _bindCode = data['code'] as String;
        _bindLabel = '学生端绑定码';
      });
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  Future<void> _addStudent() async {
    final ctrl = TextEditingController(text: '我的孩子');
    var gradeBand = '8-12';
    final form = await showDialog<Map<String, String>>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('添加孩子'),
        content: StatefulBuilder(
          builder: (ctx, setDialogState) => Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: ctrl,
                autofocus: true,
                maxLength: 50,
                decoration: const InputDecoration(labelText: '昵称'),
              ),
              DropdownButtonFormField<String>(
                value: gradeBand,
                decoration: const InputDecoration(labelText: '学段'),
                items: const [
                  DropdownMenuItem(value: '8-12', child: Text('8-12 岁')),
                  DropdownMenuItem(value: '12-16', child: Text('12-16 岁')),
                  DropdownMenuItem(value: '16-18', child: Text('16-18 岁')),
                ],
                onChanged: (value) {
                  if (value != null) setDialogState(() => gradeBand = value);
                },
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, {
              'name': ctrl.text.trim(),
              'gradeBand': gradeBand,
            }),
            child: const Text('继续'),
          ),
        ],
      ),
    );
    final name = form?['name'];
    gradeBand = form?['gradeBand'] ?? gradeBand;
    if (name == null || name.isEmpty || !mounted) return;
    try {
      final data = await Api.I.createStudent(name, gradeBand: gradeBand);
      setState(() {
        _bindCode = data['bind_code'] as String;
        _bindLabel = '$name 的绑定码';
      });
      _refresh();
    } on ApiException catch (e) {
      if (!mounted) return;
      if (e.status == 409) {
        final add = await showDialog<bool>(
          context: context,
          builder: (ctx) => AlertDialog(
            title: const Text('需要增加孩子名额'),
            content: const Text('当前订阅没有可用名额，是否增加 1 个名额？'),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(ctx, false),
                child: const Text('取消'),
              ),
              FilledButton(
                onPressed: () => Navigator.pop(ctx, true),
                child: const Text('增加名额'),
              ),
            ],
          ),
        );
        if (add == true) _buySeatAndRetry(name, gradeBand);
      } else {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  Future<void> _buySeatAndRetry(String name, String gradeBand) async {
    try {
      await Api.I.addSubscriptionSeats(
        1,
        idempotencyKey: 'seat-${DateTime.now().microsecondsSinceEpoch}',
      );
      final data = await Api.I.createStudent(name, gradeBand: gradeBand);
      if (!mounted) return;
      setState(() {
        _bindCode = data['bind_code'] as String;
        _bindLabel = '$name 的绑定码';
      });
      _refresh();
    } on ApiException catch (e) {
      if (mounted)
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  Future<void> _rebindStudent(Map<String, dynamic> student) async {
    try {
      final data = await Api.I.rebindCode(student['id'] as int);
      if (!mounted) return;
      setState(() {
        _bindCode = data['bind_code'] as String;
        _bindLabel = '${student['nickname']} 的重新绑定码';
      });
    } on ApiException catch (e) {
      if (mounted)
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(e.message)));
    }
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

  Future<void> _setGradeBand(Map<String, dynamic> s, String band) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      await Api.I.setGradeBand(s['id'] as int, band);
      messenger.showSnackBar(
        SnackBar(content: Text('学段已设为 $band，将影响分龄内容与讲解风格')),
      );
      _refresh();
    } on ApiException catch (e) {
      messenger.showSnackBar(SnackBar(content: Text(e.message)));
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

  Future<void> _addSeat() async {
    try {
      await Api.I.addSubscriptionSeats(
        1,
        idempotencyKey: 'seat-${DateTime.now().microsecondsSinceEpoch}',
      );
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('已增加 1 个孩子名额')));
      _refresh();
    } on ApiException catch (e) {
      if (mounted)
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
                Positioned(
                  right: 8,
                  top: 8,
                  child: NotificationBadge(count: _unread),
                ),
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
          if (sub != null)
            SubscriptionCard(sub: sub, onPay: _pay, onAddSeat: _addSeat),
          if (_showOnboarding) _onboardingCard(),
          _guardianCard(family, students.length),
          const SizedBox(height: 8),
          ...students.map(
            (s) => StudentReviewCard(
              student: s,
              onRename: () => _renameStudent(s),
              onGradeBandChanged: (band) => _setGradeBand(s, band),
              onRebind: () => _rebindStudent(s),
            ),
          ),
          const SizedBox(height: 8),
          ManagementSettingsCard(
            settings: family['settings'] as Map<String, dynamic>,
            onSaved: _refresh,
          ),
          if (_bindCode != null) _bindCodeCard(),
        ],
      ),
    );
  }

  Widget _onboardingCard() {
    return Card(
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
                onPressed: () => setState(() => _showOnboarding = false),
                child: const Text('我知道了'),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _guardianCard(Map<String, dynamic> family, int childCount) {
    return Card(
      child: ListTile(
        leading: const Icon(Icons.family_restroom),
        title: Text(family['guardian']['nickname'] as String? ?? '家长'),
        subtitle: Text('家庭 · $childCount 个孩子'),
        trailing: FilledButton.icon(
          onPressed: _addStudent,
          icon: const Icon(Icons.person_add, size: 17),
          label: const Text('添加孩子'),
        ),
      ),
    );
  }

  Widget _bindCodeCard() {
    return Card(
      color: const Color(0xFFE8F5F1),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            Text('$_bindLabel（10 分钟内有效）'),
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
    );
  }
}
