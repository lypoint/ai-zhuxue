import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:app_core/app_core.dart';
import 'package:qr_flutter/qr_flutter.dart';
import '../widgets/subscription_card.dart';
import '../widgets/notification_badge.dart';
import '../widgets/student_review_card.dart';
import '../widgets/management_settings_card.dart';
import 'notifications_screen.dart';
import 'login_screen.dart';
import 'device_manage_screen.dart';
import 'identity_verification_screen.dart';

/// 家庭总览：订阅状态、绑定码、孩子列表（分龄/审查/收藏）、未成年人模式管控设置。
class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});
  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  Map<String, dynamic>? _family;
  String? _loadError;
  String? _partialLoadError;
  bool _overviewLoadFailed = false;
  bool _manualRefreshing = false;
  bool _makingCode = false;
  bool _billingPending = false;
  bool _loggingOut = false;
  bool _addingStudent = false;
  int? _updatingStudentId;
  int? _bindingStudentId;
  bool _showOnboarding = false;
  Map<String, dynamic>? _subscription;
  int _unread = 0;

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  Future<void> _makeCode() async {
    if (_makingCode) return;
    setState(() => _makingCode = true);
    try {
      final data = await Api.I.createBindCode();
      _showBindCode(data['code'] as String, '学生端绑定码');
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
        ).showSnackBar(const SnackBar(content: Text('网络连接失败，请稍后重试')));
      }
    } finally {
      if (mounted) setState(() => _makingCode = false);
    }
  }

  void _showBindCode(String code, String label) {
    if (!mounted) return;
    showDialog<void>(
      context: context,
      builder: (_) => BindCodeDialog(code: code, label: label),
    );
  }

  Future<void> _addStudent() async {
    if (_addingStudent) return;
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
                // ignore: deprecated_member_use
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
    if (name == null || !mounted) return;
    if (name.isEmpty) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('请输入孩子昵称')));
      return;
    }
    setState(() => _addingStudent = true);
    final messenger = ScaffoldMessenger.of(context);
    messenger.hideCurrentSnackBar();
    messenger.showSnackBar(
      const SnackBar(content: Text('正在添加孩子…'), duration: Duration(seconds: 30)),
    );
    try {
      final data = await Api.I.createStudent(name, gradeBand: gradeBand);
      if (!mounted) return;
      messenger.hideCurrentSnackBar();
      _showBindCode(data['bind_code'] as String, '$name 的绑定码');
      _refresh();
    } on ApiException catch (e) {
      if (!mounted) return;
      messenger.hideCurrentSnackBar();
      if (e.status == 409) {
        // 规格要求确认页展示「增加名额」价格（来自订阅配置，人民币元）
        final seatPrice = _subscription?['additional_seat_price'];
        final priceText = seatPrice == null ? '' : ' ¥$seatPrice/月';
        final add = await showDialog<bool>(
          context: context,
          builder: (ctx) => AlertDialog(
            title: const Text('需要增加孩子名额'),
            content: Text('当前订阅没有可用名额。增加 1 个名额$priceText（按剩余天数折算，立即生效），是否继续？'),
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
        if (add == true && mounted) await _buySeatAndRetry(name, gradeBand);
      } else {
        messenger.showSnackBar(SnackBar(content: Text(e.message)));
      }
    } catch (_) {
      if (mounted) {
        messenger.hideCurrentSnackBar();
        messenger.showSnackBar(
          const SnackBar(content: Text('添加孩子失败，请检查网络后重试')),
        );
      }
    } finally {
      if (mounted) setState(() => _addingStudent = false);
    }
  }

  Future<void> _buySeatAndRetry(String name, String gradeBand) async {
    final messenger = ScaffoldMessenger.of(context);
    var seatAdded = false;
    messenger.hideCurrentSnackBar();
    messenger.showSnackBar(
      const SnackBar(
        content: Text('正在增加名额并添加孩子…'),
        duration: Duration(seconds: 30),
      ),
    );
    try {
      await Api.I.addSubscriptionSeats(
        1,
        idempotencyKey: 'seat-${DateTime.now().microsecondsSinceEpoch}',
      );
      seatAdded = true;
      final data = await Api.I.createStudent(name, gradeBand: gradeBand);
      if (!mounted) return;
      messenger.hideCurrentSnackBar();
      _showBindCode(data['bind_code'] as String, '$name 的绑定码');
      _refresh();
    } on ApiException catch (e) {
      if (mounted) {
        messenger.hideCurrentSnackBar();
        messenger.showSnackBar(
          SnackBar(
            content: Text(
              seatAdded ? '名额已增加，但添加孩子失败：${e.message}。请重试添加孩子' : e.message,
            ),
          ),
        );
        if (seatAdded) _refresh();
      }
    } catch (_) {
      if (mounted) {
        messenger.hideCurrentSnackBar();
        messenger.showSnackBar(
          SnackBar(
            content: Text(
              seatAdded ? '名额已增加，但添加孩子失败。请重试添加孩子' : '操作失败，请检查网络后重试',
            ),
          ),
        );
        if (seatAdded) _refresh();
      }
    }
  }

  Future<void> _rebindStudent(Map<String, dynamic> student) async {
    if (_bindingStudentId != null) return;
    final studentId = student['id'] as int;
    setState(() => _bindingStudentId = studentId);
    try {
      final data = await Api.I.rebindCode(studentId);
      if (!mounted) return;
      _showBindCode(data['code'] as String, '${student['nickname']} 的绑定码');
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(e.message)));
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('生成绑定码失败，请稍后重试')),
        );
      }
    } finally {
      if (mounted) setState(() => _bindingStudentId = null);
    }
  }

  Future<void> _refresh() async {
    Map<String, dynamic> data;
    try {
      data = await Api.I.familyOverview();
    } on ApiException catch (e) {
      // token 失效（401）已由根级全局兜底（ParentApp._onSessionExpired）处理；
      _overviewLoadFailed = true;
      if (e.status != 401) _showLoadError('加载失败：${e.message}');
      return;
    } catch (_) {
      _overviewLoadFailed = true;
      _showLoadError('加载失败，请检查网络后重试');
      return;
    }
    Map<String, dynamic>? sub;
    var unread = _unread;
    final unavailable = <String>[];
    try {
      sub = await Api.I.subscription();
    } catch (_) {
      unavailable.add('订阅信息');
    }
    try {
      unread = (await Api.I.notifications(unreadOnly: true))['unread'] as int;
    } catch (_) {
      unavailable.add('通知数量');
    }
    if (!mounted) return;
    _overviewLoadFailed = false;
    // P2 新用户引导：试用期内且还没有孩子绑定时展示
    final showGuide =
        (data['students'] as List).isEmpty && (sub?['plan'] == 'free_trial');
    setState(() {
      _family = data;
      _loadError = null;
      _subscription = sub;
      _unread = unread;
      _partialLoadError = unavailable.isEmpty
          ? null
          : '${unavailable.join('、')}暂不可用，请刷新重试';
      _showOnboarding = showGuide;
    });
  }

  Future<void> _manualRefresh() async {
    if (_manualRefreshing) return;
    setState(() => _manualRefreshing = true);
    final messenger = ScaffoldMessenger.of(context);
    messenger.hideCurrentSnackBar();
    messenger.showSnackBar(const SnackBar(
      content: Text('正在刷新…'),
      duration: Duration(seconds: 30),
    ));
    try {
      await _refresh();
      if (!mounted) return;
      messenger.hideCurrentSnackBar();
      if (!_overviewLoadFailed && _partialLoadError == null) {
        messenger.showSnackBar(const SnackBar(content: Text('已刷新')));
      }
    } catch (_) {
      if (mounted) {
        messenger.hideCurrentSnackBar();
        messenger.showSnackBar(const SnackBar(content: Text('刷新失败，请稍后重试')));
      }
    } finally {
      if (mounted) setState(() => _manualRefreshing = false);
    }
  }

  void _showLoadError(String message) {
    if (!mounted) return;
    if (_family == null) {
      setState(() => _loadError = message);
    } else {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
    }
  }

  Future<void> _renameStudent(Map<String, dynamic> s) async {
    if (_updatingStudentId != null) return;
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
    if (name == null || !mounted) return;
    if (name.isEmpty) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('请输入孩子昵称')));
      return;
    }
    await _updateStudent(
      s['id'] as int,
      () => Api.I.setStudentNickname(s['id'] as int, name),
      '正在保存昵称…',
      '已改名为 $name',
    );
  }

  Future<void> _setGradeBand(Map<String, dynamic> s, String band) async {
    await _updateStudent(
      s['id'] as int,
      () => Api.I.setGradeBand(s['id'] as int, band),
      '正在更新学段…',
      '学段已设为 $band，将影响分龄内容与讲解风格',
    );
  }

  Future<void> _updateStudent(
    int studentId,
    Future<void> Function() action,
    String progress,
    String success,
  ) async {
    if (_updatingStudentId != null) return;
    setState(() => _updatingStudentId = studentId);
    final messenger = ScaffoldMessenger.of(context);
    messenger.hideCurrentSnackBar();
    messenger.showSnackBar(
      SnackBar(content: Text(progress), duration: const Duration(seconds: 30)),
    );
    try {
      await action();
      if (!mounted) return;
      messenger.hideCurrentSnackBar();
      messenger.showSnackBar(SnackBar(content: Text(success)));
      await _refresh();
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
      if (mounted) setState(() => _updatingStudentId = null);
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
    await _runBilling(() => Api.I.paySubscription(), '正在续费…', '续费成功！');
  }

  Future<void> _runBilling(
    Future<void> Function() action,
    String progress,
    String success,
  ) async {
    if (_billingPending) return;
    setState(() => _billingPending = true);
    final messenger = ScaffoldMessenger.of(context);
    messenger.hideCurrentSnackBar();
    messenger.showSnackBar(
      SnackBar(content: Text(progress), duration: const Duration(seconds: 30)),
    );
    try {
      await action();
      if (!mounted) return;
      messenger.hideCurrentSnackBar();
      messenger.showSnackBar(SnackBar(content: Text(success)));
      await _refresh();
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
      if (mounted) setState(() => _billingPending = false);
    }
  }

  Future<void> _addSeat() async {
    final seatPrice = _subscription?['additional_seat_price'];
    final priceText = seatPrice == null ? '' : ' ¥$seatPrice/月';
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('确认增加名额'),
        content: Text('增加 1 个孩子名额$priceText，按剩余天数折算后立即生效。是否继续？'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('确认增加'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    await _runBilling(
      () => Api.I.addSubscriptionSeats(
        1,
        idempotencyKey: 'seat-${DateTime.now().microsecondsSinceEpoch}',
      ),
      '正在增加名额…',
      '已增加 1 个孩子名额',
    );
  }

  Future<void> _logout() async {
    if (_loggingOut) return;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('退出登录？'),
        content: const Text('退出后需要重新登录，孩子的学习记录会保留。'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('取消')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('退出')),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
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
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(builder: (_) => const LoginScreen()),
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
    final family = _family;
    if (family == null) {
      return Scaffold(
        body: Center(
          child: _loadError == null
              ? const CircularProgressIndicator()
              : Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(_loadError!),
                    const SizedBox(height: 12),
                    FilledButton(
                      onPressed: () {
                        setState(() => _loadError = null);
                        _refresh();
                      },
                      child: const Text('重试'),
                    ),
                  ],
                ),
        ),
      );
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
            tooltip: '刷新首页',
            onPressed: _manualRefreshing ? null : _manualRefresh,
            icon: _manualRefreshing
                ? const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.refresh),
          ),
          IconButton(
            onPressed: _makingCode ? null : _makeCode,
            icon: _makingCode
                ? const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.qr_code_2),
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
            enabled: !_loggingOut,
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
          if (_partialLoadError != null)
            Card(
              child: ListTile(
                leading: const Icon(Icons.info_outline),
                title: Text(_partialLoadError!),
                trailing: TextButton(
                  onPressed: _manualRefreshing ? null : _manualRefresh,
                  child: const Text('重试'),
                ),
              ),
            ),
          if (sub != null)
            SubscriptionCard(
              sub: sub,
              onPay: _pay,
              onAddSeat: _addSeat,
              billingPending: _billingPending,
            ),
          if (_showOnboarding) _onboardingCard(),
          _guardianCard(family, students.length),
          Card(
            child: ListTile(
              leading: const Icon(Icons.verified_user_outlined),
              title: const Text('实名认证'),
              subtitle: Text(
                family['guardian']['identity_verified'] == true
                    ? '已认证'
                    : '未认证 · 不影响功能使用',
              ),
              trailing: const Icon(Icons.chevron_right),
              onTap: () async {
                final verified = await Navigator.of(context).push<bool>(
                  MaterialPageRoute(
                    builder: (_) => IdentityVerificationScreen(
                      verified: family['guardian']['identity_verified'] == true,
                    ),
                  ),
                );
                if (verified == true) _refresh();
              },
            ),
          ),
          const SizedBox(height: 8),
          ...students.map(
            (s) => StudentReviewCard(
              student: s,
              onRename: () => _renameStudent(s),
              onGradeBandChanged: (band) => _setGradeBand(s, band),
              updatesDisabled: _updatingStudentId != null,
              onRebind: _bindingStudentId == null ? () => _rebindStudent(s) : null,
              bindingInProgress: _bindingStudentId == s['id'],
              onManageDevices: () => Navigator.of(context).push(
                MaterialPageRoute(
                  builder: (_) => DeviceManageScreen(
                    studentId: s['id'] as int,
                    studentName: s['nickname'] as String? ?? '',
                  ),
                ),
              ),
            ),
          ),
          const SizedBox(height: 8),
          ManagementSettingsCard(
            settings: family['settings'] as Map<String, dynamic>,
            onSaved: _refresh,
          ),
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
        trailing: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 140),
          child: FilledButton.icon(
            onPressed: _addingStudent ? null : _addStudent,
            icon: const Icon(Icons.person_add, size: 17),
            label: Text(_addingStudent ? '添加中…' : '添加孩子'),
          ),
        ),
      ),
    );
  }
}

class BindCodeDialog extends StatefulWidget {
  const BindCodeDialog({super.key, required this.code, required this.label});

  final String code;
  final String label;

  @override
  State<BindCodeDialog> createState() => _BindCodeDialogState();
}

class _BindCodeDialogState extends State<BindCodeDialog> {
  bool _copying = false;
  bool _copyFailed = false;

  Future<void> _copy() async {
    setState(() {
      _copying = true;
      _copyFailed = false;
    });
    try {
      await Clipboard.setData(ClipboardData(text: widget.code));
      if (!mounted) return;
      final messenger = ScaffoldMessenger.of(context);
      Navigator.pop(context);
      messenger.showSnackBar(const SnackBar(content: Text('绑定码已复制')));
    } catch (_) {
      if (mounted) setState(() => _copyFailed = true);
    } finally {
      if (mounted) setState(() => _copying = false);
    }
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: Text(widget.label),
    content: Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        const Text('10 分钟内在学生端扫描，或输入以下绑定码'),
        const SizedBox(height: 16),
        SizedBox(
          width: 180,
          height: 180,
          child: QrImageView(data: widget.code, size: 180),
        ),
        const SizedBox(height: 8),
        Text(
          widget.code,
          textAlign: TextAlign.center,
          style: const TextStyle(fontSize: 24, letterSpacing: 4),
        ),
        if (_copyFailed)
          const Padding(
            padding: EdgeInsets.only(top: 8),
            child: Text('复制失败，请重试', style: TextStyle(color: Colors.red)),
          ),
      ],
    ),
    actions: [
      TextButton.icon(
        onPressed: _copying ? null : _copy,
        icon: const Icon(Icons.copy),
        label: Text(_copying ? '复制中…' : '复制绑定码'),
      ),
      TextButton(
        onPressed: () => Navigator.pop(context),
        child: const Text('完成'),
      ),
    ],
  );
}
