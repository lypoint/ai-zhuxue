import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:app_core/app_core.dart';
import 'package:qr_flutter/qr_flutter.dart';
import '../widgets/subscription_card.dart';
import '../widgets/notification_badge.dart';
import '../widgets/student_review_card.dart';
import '../widgets/management_settings_card.dart';
import '../widgets/student_fence_dialog.dart';
import '../widgets/guardian_name_dialog.dart';
import 'notifications_screen.dart';
import '../billing.dart';
import 'login_screen.dart';
import 'device_manage_screen.dart';
import 'account_deletion_screen.dart';

/// 家庭总览：订阅状态、绑定码、孩子列表（分龄/审查/收藏）、未成年人模式管控设置。
class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});
  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> with WidgetsBindingObserver {
  Map<String, dynamic>? _family;
  String? _loadError;
  String? _partialLoadError;
  bool _overviewLoadFailed = false;
  bool _manualRefreshing = false;
  bool _billingPending = false;
  bool _loggingOut = false;
  bool _addingStudent = false;
  int? _updatingStudentId;
  int? _bindingStudentId;
  bool _showOnboarding = false;
  Map<String, dynamic>? _subscription;
  int _unread = 0;
  List<dynamic> _studentDeletionNotices = [];
  int _selectedTab = 0;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        context
            .getInheritedWidgetOfExactType<BillingScope>()
            ?.billing
            .recover();
      }
    });
    _refresh();
  }

  ParentBilling? _billing;
  int _billingRevision = 0;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final billing = context
        .dependOnInheritedWidgetOfExactType<BillingScope>()
        ?.billing;
    if (billing != _billing) {
      _billing?.removeListener(_billingChanged);
      _billing = billing;
      _billingRevision = billing?.revision ?? 0;
      billing?.addListener(_billingChanged);
    }
  }

  void _billingChanged() {
    if (mounted && _billingRevision != _billing!.revision) {
      _billingRevision = _billing!.revision;
      _refresh();
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) _refresh();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _billing?.removeListener(_billingChanged);
    super.dispose();
  }

  Future<void> _makeCode() => _addStudent();

  Future<void> _editFenceSettings(Map<String, dynamic> student) async {
    final saved = await showDialog<Map<String, dynamic>>(
      context: context,
      barrierDismissible: false,
      builder: (_) => StudentFenceDialog(
        studentId: student['id'] as int,
        studentName: student['nickname'] as String? ?? '',
        settings:
            student['fence_settings'] as Map<String, dynamic>? ?? const {},
      ),
    );
    if (saved != null && mounted) _refresh();
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
    final ctrl = TextEditingController(text: tr("我的孩子"));
    var gradeBand = '8-12';
    final form = await showDialog<Map<String, String>>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(tr("添加孩子")),
        content: StatefulBuilder(
          builder: (ctx, setDialogState) => Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: ctrl,
                autofocus: true,
                maxLength: 50,
                decoration: InputDecoration(labelText: tr("昵称")),
              ),
              DropdownButtonFormField<String>(
                // ignore: deprecated_member_use
                value: gradeBand,
                decoration: InputDecoration(labelText: tr("学段")),
                items: [
                  DropdownMenuItem(value: '8-12', child: Text(tr("8-12 岁"))),
                  DropdownMenuItem(value: '12-16', child: Text(tr("12-16 岁"))),
                  DropdownMenuItem(value: '16-18', child: Text(tr("16-18 岁"))),
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
            child: Text(tr("取消")),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, {
              'name': ctrl.text.trim(),
              'gradeBand': gradeBand,
            }),
            child: Text(tr("继续")),
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
      ).showSnackBar(SnackBar(content: Text(tr("请输入孩子昵称"))));
      return;
    }
    final fenceSettings = await showDialog<Map<String, dynamic>>(
      context: context,
      barrierDismissible: false,
      builder: (_) => StudentFenceDialog(studentName: name),
    );
    if (fenceSettings == null || !mounted) return;
    setState(() => _addingStudent = true);
    final messenger = ScaffoldMessenger.of(context);
    messenger.hideCurrentSnackBar();
    messenger.showSnackBar(
      SnackBar(content: Text(tr("正在添加孩子…")), duration: Duration(seconds: 30)),
    );
    try {
      final data = await Api.I.createStudent(
        name,
        gradeBand: gradeBand,
        fenceLevel: fenceSettings['fence_level'] as String,
        forbiddenWords: (fenceSettings['forbidden_words'] as List)
            .cast<String>(),
      );
      if (!mounted) return;
      messenger.hideCurrentSnackBar();
      _showBindCode(data['bind_code'] as String, tr("{0} 的绑定码", [name]));
      _refresh();
    } on ApiException catch (e) {
      if (!mounted) return;
      messenger.hideCurrentSnackBar();
      if (e.status == 409) {
        final add = await showDialog<bool>(
          context: context,
          builder: (ctx) => AlertDialog(
            title: Text(tr("需要增加孩子名额")),
            content: Text(
              tr("当前订阅没有可用名额。可选择更高名额的月订阅档位，支付与验单确认后立即生效，金额及续订周期以支付确认页为准。"),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(ctx, false),
                child: Text(tr("取消")),
              ),
              FilledButton(
                onPressed: () => Navigator.pop(ctx, true),
                child: Text(tr("增加名额")),
              ),
            ],
          ),
        );
        if (add == true && mounted) {
          await _buySeatAndRetry(name, gradeBand, fenceSettings);
        }
      } else {
        messenger.showSnackBar(SnackBar(content: Text(e.message)));
      }
    } catch (_) {
      if (mounted) {
        messenger.hideCurrentSnackBar();
        messenger.showSnackBar(SnackBar(content: Text(tr("添加孩子失败，请检查网络后重试"))));
      }
    } finally {
      if (mounted) setState(() => _addingStudent = false);
    }
  }

  Future<void> _buySeatAndRetry(
    String name,
    String gradeBand,
    Map<String, dynamic> fenceSettings,
  ) async {
    final messenger = ScaffoldMessenger.of(context);
    var seatAdded = false;
    messenger.hideCurrentSnackBar();
    messenger.showSnackBar(
      SnackBar(
        content: Text(tr("正在增加名额并添加孩子…")),
        duration: Duration(seconds: 30),
      ),
    );
    try {
      if (await _purchase('seat_add') != true) {
        if (mounted) messenger.hideCurrentSnackBar();
        return;
      }
      seatAdded = true;
      final data = await Api.I.createStudent(
        name,
        gradeBand: gradeBand,
        fenceLevel: fenceSettings['fence_level'] as String,
        forbiddenWords: (fenceSettings['forbidden_words'] as List)
            .cast<String>(),
      );
      if (!mounted) return;
      messenger.hideCurrentSnackBar();
      _showBindCode(data['bind_code'] as String, tr("{0} 的绑定码", [name]));
      _refresh();
    } on ApiException catch (e) {
      if (mounted) {
        messenger.hideCurrentSnackBar();
        messenger.showSnackBar(
          SnackBar(
            content: Text(
              seatAdded
                  ? tr("名额已增加，但添加孩子失败：{0}。请重试添加孩子", [e.message])
                  : e.message,
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
              seatAdded ? tr("名额已增加，但添加孩子失败。请重试添加孩子") : tr("操作失败，请检查网络后重试"),
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
      _showBindCode(
        data['code'] as String,
        tr("{0} · 重新绑定设备", [student['nickname']]),
      );
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
        ).showSnackBar(SnackBar(content: Text(tr("生成绑定码失败，请稍后重试"))));
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
      if (e.status != 401) _showLoadError(tr("加载失败：{0}", [e.message]));
      return;
    } catch (_) {
      _overviewLoadFailed = true;
      _showLoadError(tr("加载失败，请检查网络后重试"));
      return;
    }
    Map<String, dynamic>? sub;
    var unread = _unread;
    var deletionNotices = _studentDeletionNotices;
    final unavailable = <String>[];
    try {
      sub = await Api.I.subscription();
    } catch (_) {
      unavailable.add(tr("订阅信息"));
    }
    try {
      final notices = await Api.I.notifications(unreadOnly: true);
      unread = notices['unread'] as int;
      deletionNotices = (notices['items'] as List? ?? [])
          .where((n) => n['type'] == 'student_deleted')
          .toList();
    } catch (_) {
      unavailable.add(tr("通知数量"));
    }
    if (!mounted) return;
    _overviewLoadFailed = false;
    // P2 新用户引导：试用期内且还没有孩子绑定时展示
    final showGuide =
        (data['students'] as List).every((s) => s['active'] == false) &&
        (sub?['plan'] == 'free_trial');
    setState(() {
      _family = data;
      _loadError = null;
      _subscription = sub;
      _unread = unread;
      _studentDeletionNotices = deletionNotices;
      _partialLoadError = unavailable.isEmpty
          ? null
          : tr("{0}暂不可用，请刷新重试", [unavailable.join('、')]);
      _showOnboarding = showGuide;
    });
  }

  Future<void> _manualRefresh() async {
    if (_manualRefreshing) return;
    setState(() => _manualRefreshing = true);
    final messenger = ScaffoldMessenger.of(context);
    messenger.hideCurrentSnackBar();
    messenger.showSnackBar(
      SnackBar(content: Text(tr("正在刷新…")), duration: Duration(seconds: 30)),
    );
    try {
      await _refresh();
      if (!mounted) return;
      messenger.hideCurrentSnackBar();
      if (!_overviewLoadFailed && _partialLoadError == null) {
        messenger.showSnackBar(SnackBar(content: Text(tr("已刷新"))));
      }
    } catch (_) {
      if (mounted) {
        messenger.hideCurrentSnackBar();
        messenger.showSnackBar(SnackBar(content: Text(tr("刷新失败，请稍后重试"))));
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
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(message)));
    }
  }

  Future<void> _renameStudent(Map<String, dynamic> s) async {
    if (_updatingStudentId != null) return;
    final ctrl = TextEditingController(text: s['nickname'] as String? ?? '');
    final name = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(tr("修改昵称")),
        content: TextField(controller: ctrl, autofocus: true, maxLength: 50),
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
    if (name == null || !mounted) return;
    if (name.isEmpty) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(tr("请输入孩子昵称"))));
      return;
    }
    await _updateStudent(
      s['id'] as int,
      () => Api.I.setStudentNickname(s['id'] as int, name),
      tr("正在保存昵称…"),
      tr("已改名为 {0}", [name]),
    );
  }

  Future<void> _deleteStudent(Map<String, dynamic> student) async {
    final name = student['nickname'] as String? ?? tr("这个孩子");
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(tr("删除孩子")),
        content: Text(
          tr("确定删除 {0} 吗？删除后该学生端将无法继续使用，联网后会退出登录，学习记录仍会保留。", [name]),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: Text(tr("取消")),
          ),
          FilledButton(
            style: FilledButton.styleFrom(
              backgroundColor: Theme.of(ctx).colorScheme.error,
              foregroundColor: Theme.of(ctx).colorScheme.onError,
            ),
            onPressed: () => Navigator.pop(ctx, true),
            child: Text(tr("删除")),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    await _updateStudent(
      student['id'] as int,
      () async {
        await Api.I.deleteStudent(student['id'] as int);
      },
      tr("正在删除孩子…"),
      tr("已删除 {0}，学生端登录已失效", [name]),
    );
  }

  Future<void> _setGradeBand(Map<String, dynamic> s, String band) async {
    await _updateStudent(
      s['id'] as int,
      () => Api.I.setGradeBand(s['id'] as int, band),
      tr("正在更新学段…"),
      tr("学段已设为 {0}，将影响分龄内容与讲解风格", [band]),
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
        messenger.showSnackBar(SnackBar(content: Text(tr("操作失败，请检查网络后重试"))));
      }
    } finally {
      if (mounted) setState(() => _updatingStudentId = null);
    }
  }

  Future<void> _pay() async {
    await _purchase('subscription');
  }

  Future<void> _addSeat() async {
    await _purchase('seat_add');
  }

  Future<bool?> _purchase(String kind) async {
    if (_billingPending) return false;
    setState(() => _billingPending = true);
    final messenger = ScaffoldMessenger.of(context);
    try {
      final paid = await BillingScope.of(context).purchase(context, kind);
      if (!mounted) return false;
      if (paid == true) {
        messenger.showSnackBar(SnackBar(content: Text(tr("支付成功，权益已生效"))));
      }
      await _refresh();
      return paid;
    } on ApiException catch (error) {
      if (mounted) {
        messenger.showSnackBar(SnackBar(content: Text(error.message)));
      }
    } catch (_) {
      if (mounted) {
        messenger.showSnackBar(SnackBar(content: Text(tr("暂时无法创建订单，请稍后重试"))));
      }
    } finally {
      if (mounted) setState(() => _billingPending = false);
    }
    return false;
  }

  Future<void> _logout() async {
    if (_loggingOut) return;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(tr("退出登录？")),
        content: Text(tr("退出后需要重新登录，孩子的学习记录会保留。")),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: Text(tr("取消")),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: Text(tr("退出")),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    setState(() => _loggingOut = true);
    final messenger = ScaffoldMessenger.of(context);
    messenger.showSnackBar(
      SnackBar(content: Text(tr("正在退出登录…")), duration: Duration(seconds: 30)),
    );
    try {
      await Api.I.logout();
      if (!mounted) return;
      messenger.hideCurrentSnackBar();
      Navigator.of(
        context,
      ).pushReplacement(MaterialPageRoute(builder: (_) => const LoginScreen()));
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
    final family = _family;
    if (family == null) {
      return Scaffold(
        body: Center(
          child: _loadError == null
              ? const CircularProgressIndicator()
              : Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(trMessage(_loadError!)),
                    const SizedBox(height: 12),
                    FilledButton(
                      onPressed: () {
                        setState(() => _loadError = null);
                        _refresh();
                      },
                      child: Text(tr("重试")),
                    ),
                  ],
                ),
        ),
      );
    }
    final students = (family['students'] as List)
        .cast<Map<String, dynamic>>()
        .where((student) => student['active'] != false)
        .toList();
    final sub = _subscription;
    return Scaffold(
      appBar: AppBar(
        toolbarHeight: MediaQuery.textScalerOf(
          context,
        ).scale(kToolbarHeight).clamp(kToolbarHeight, 96),
        title: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text([tr("家庭"), tr("守护"), tr("我的")][_selectedTab]),
            Text(
              [
                tr("关注孩子的每一步成长"),
                tr("为孩子建立健康的学习习惯"),
                tr("家庭账户与服务"),
              ][_selectedTab],
              style: TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.w500,
                color: Theme.of(context).colorScheme.onSurfaceVariant,
              ),
            ),
          ],
        ),
        actions: [
          const LanguageButton(),
          IconButton(
            tooltip: tr("刷新首页"),
            onPressed: _manualRefreshing ? null : _manualRefresh,
            icon: _manualRefreshing
                ? const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.refresh),
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
                tooltip: tr("通知"),
              ),
              if (_unread > 0)
                Positioned(
                  right: 8,
                  top: 8,
                  child: NotificationBadge(count: _unread),
                ),
            ],
          ),
        ],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _selectedTab,
        onDestinationSelected: (value) {
          FocusManager.instance.primaryFocus?.unfocus();
          setState(() => _selectedTab = value);
        },
        destinations: [
          NavigationDestination(
            icon: Icon(Icons.home_outlined),
            selectedIcon: Icon(Icons.home),
            label: tr("家庭"),
          ),
          NavigationDestination(
            icon: Icon(Icons.shield_outlined),
            selectedIcon: Icon(Icons.shield),
            label: tr("守护"),
          ),
          NavigationDestination(
            icon: Icon(Icons.person_outline),
            selectedIcon: Icon(Icons.person),
            label: tr("我的"),
          ),
        ],
      ),
      body: Column(
        children: [
          if (_partialLoadError != null)
            Card(
              child: ListTile(
                leading: const Icon(Icons.info_outline),
                title: Text(trMessage(_partialLoadError!)),
                trailing: TextButton(
                  onPressed: _manualRefreshing ? null : _manualRefresh,
                  child: Text(tr("重试")),
                ),
              ),
            ),
          Expanded(
            child: IndexedStack(
              index: _selectedTab,
              children: [
                _tabList('family', [
                  for (final notice in _studentDeletionNotices)
                    Card(
                      child: ListTile(
                        leading: const Icon(Icons.person_remove_outlined),
                        title: Text(trMessage(notice['title'] as String)),
                        subtitle: Text(trMessage(notice['body'] as String)),
                        onTap: () async {
                          await Navigator.of(context).push(
                            MaterialPageRoute(
                              builder: (_) => const NotificationsScreen(),
                            ),
                          );
                          if (mounted) _refresh();
                        },
                      ),
                    ),
                  if (_showOnboarding) ...[
                    _onboardingCard(),
                    const SizedBox(height: 16),
                  ],
                  _guardianCard(family, students.length),
                  const SizedBox(height: 24),
                  _sectionTitle(tr("孩子的学习"), tr("每一次探索，都值得被看见")),
                  const SizedBox(height: 12),
                  if (students.isEmpty)
                    Card(
                      child: Padding(
                        padding: const EdgeInsets.all(24),
                        child: Column(
                          children: [
                            const Icon(Icons.school_outlined, size: 40),
                            const SizedBox(height: 12),
                            Text(tr("添加孩子，开启学习陪伴")),
                            const SizedBox(height: 8),
                            Text(
                              tr("添加后可生成绑定码，连接孩子的学生端。"),
                              textAlign: TextAlign.center,
                            ),
                          ],
                        ),
                      ),
                    ),
                  ...students.map(
                    (s) => Padding(
                      padding: const EdgeInsets.only(bottom: 16),
                      child: StudentReviewCard(
                        student: s,
                        onRename: () => _renameStudent(s),
                        onGradeBandChanged: (band) => _setGradeBand(s, band),
                        updatesDisabled: _updatingStudentId != null,
                        onRebind: _bindingStudentId == null
                            ? () => _rebindStudent(s)
                            : null,
                        bindingInProgress: _bindingStudentId == s['id'],
                        onDelete: () => _deleteStudent(s),
                        onFenceSettings: () => _editFenceSettings(s),
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
                  ),
                ]),
                ManagementSettingsCard(
                  scrollable: true,
                  settings: family['settings'] as Map<String, dynamic>,
                  onSaved: _refresh,
                ),
                _tabList('account', [
                  Card(
                    child: ListTile(
                      leading: const Icon(Icons.person_outline),
                      title: Text(tr("监护人名字")),
                      subtitle: Text(
                        family['guardian']['nickname'] as String? ?? tr("家长"),
                      ),
                      trailing: const Icon(Icons.edit_outlined),
                      onTap: () async {
                        final name = await showDialog<String>(
                          context: context,
                          barrierDismissible: false,
                          builder: (_) => GuardianNameDialog(
                            initialName:
                                family['guardian']['nickname'] as String? ?? '',
                          ),
                        );
                        if (name != null && mounted) {
                          setState(() => family['guardian']['nickname'] = name);
                        }
                      },
                    ),
                  ),
                  const SizedBox(height: 16),
                  if (sub != null)
                    SubscriptionCard(
                      onManage:
                          _billing != null && _billing!.channel != 'wechat'
                          ? () => _purchase('manage')
                          : null,
                      sub: sub,
                      onPay: _pay,
                      onAddSeat: _addSeat,
                      billingPending: _billingPending,
                    ),
                  const SizedBox(height: 16),
                  Card(
                    child: ListTile(
                      leading: const Icon(Icons.qr_code_2),
                      title: Text(_addingStudent ? tr("生成中…") : tr("学生端绑定码")),
                      subtitle: Text(tr("连接学生端设备")),
                      trailing: const Icon(Icons.chevron_right),
                      onTap: _addingStudent ? null : _makeCode,
                    ),
                  ),
                  const SizedBox(height: 24),
                  if (context.dependOnInheritedWidgetOfExactType<ParentLoginScope>()?.extraAccountActionBuilder != null) ...[
                    context.dependOnInheritedWidgetOfExactType<ParentLoginScope>()!.extraAccountActionBuilder!(context),
                    const SizedBox(height: 12),
                  ],
                  OutlinedButton.icon(
                    onPressed: _loggingOut ? null : _logout,
                    icon: const Icon(Icons.logout),
                    label: Text(_loggingOut ? tr("正在退出…") : tr("退出登录")),
                  ),
                  TextButton.icon(
                    onPressed: _loggingOut
                        ? null
                        : () => Navigator.of(context).push(
                            MaterialPageRoute(
                              builder: (_) => AccountDeletionScreen(
                                onManageSubscription:
                                    _billing != null &&
                                        _billing!.channel != 'wechat'
                                    ? () {
                                        _purchase('manage');
                                      }
                                    : null,
                              ),
                            ),
                          ),
                    style: TextButton.styleFrom(
                      foregroundColor: Theme.of(context).colorScheme.error,
                    ),
                    icon: const Icon(Icons.delete_outline),
                    label: Text(tr("删除账号")),
                  ),
                ]),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _tabList(String name, List<Widget> children) {
    return RefreshIndicator(
      onRefresh: _refresh,
      child: ListView(
        key: PageStorageKey(name),
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(20, 16, 20, 32),
        children: [
          Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 640),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: children,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _sectionTitle(String title, String subtitle) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title,
          style: theme.textTheme.titleLarge?.copyWith(
            fontWeight: FontWeight.w700,
          ),
        ),
        const SizedBox(height: 6),
        Text(
          subtitle,
          style: theme.textTheme.bodyMedium?.copyWith(
            color: theme.colorScheme.onSurfaceVariant,
          ),
        ),
      ],
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
            Text(
              tr("🎉 欢迎使用 AI 助学"),
              style: TextStyle(fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 6),
            Text(
              tr(
                "三步开始：\n1. 添加孩子，获取绑定码\n2. 在孩子设备安装学生端，输入绑定码\n3. 在「守护」设置休息时段与每日上限",
              ),
              style: TextStyle(fontSize: 13, height: 1.5),
            ),
            const SizedBox(height: 8),
            Align(
              alignment: Alignment.centerRight,
              child: TextButton(
                onPressed: () => setState(() => _showOnboarding = false),
                child: Text(tr("我知道了")),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _guardianCard(Map<String, dynamic> family, int childCount) {
    final scheme = Theme.of(context).colorScheme;
    if (childCount > 0) {
      return Card(
        color: scheme.primaryContainer,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                tr("{0}，你好", [family['guardian']['nickname'] ?? tr("家长")]),
                style: Theme.of(context).textTheme.titleMedium,
              ),
              const SizedBox(height: 8),
              Wrap(
                spacing: 12,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  Text(tr("一起陪伴 {0} 个孩子的学习与成长", [childCount])),
                  TextButton.icon(
                    onPressed: _addingStudent ? null : _addStudent,
                    icon: const Icon(Icons.add),
                    label: Text(_addingStudent ? tr("添加中…") : tr("添加孩子")),
                  ),
                ],
              ),
            ],
          ),
        ),
      );
    }
    return Container(
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFFE2F1E9), Color(0xFFF0F5E9)],
        ),
        borderRadius: BorderRadius.circular(28),
        border: Border.all(color: const Color(0xFFD8E8DE)),
      ),
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.spa_outlined, color: scheme.primary, size: 18),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  tr("陪伴成长 · 从每一天开始"),
                  style: TextStyle(color: scheme.primary, fontSize: 12),
                ),
              ),
            ],
          ),
          const SizedBox(height: 18),
          Text(
            tr("{0}，你好", [family['guardian']['nickname'] ?? tr("家长")]),
            style: Theme.of(context).textTheme.headlineSmall?.copyWith(
              color: scheme.onPrimaryContainer,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            tr("一起陪伴 {0} 个孩子的学习与成长", [childCount]),
            style: TextStyle(color: scheme.onSurfaceVariant, height: 1.5),
          ),
          const SizedBox(height: 20),
          FilledButton.icon(
            style: FilledButton.styleFrom(minimumSize: const Size(0, 48)),
            onPressed: _addingStudent ? null : _addStudent,
            icon: const Icon(Icons.add_rounded, size: 20),
            label: Text(_addingStudent ? tr("添加中…") : tr("添加孩子")),
          ),
        ],
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
      messenger.showSnackBar(SnackBar(content: Text(tr("绑定码已复制"))));
    } catch (_) {
      if (mounted) setState(() => _copyFailed = true);
    } finally {
      if (mounted) setState(() => _copying = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    AppLanguage.watch(context);
    return AlertDialog(
      title: Text(widget.label),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(tr("10 分钟内在学生端扫描，或输入以下绑定码")),
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
            Padding(
              padding: EdgeInsets.only(top: 8),
              child: Text(tr("复制失败，请重试"), style: TextStyle(color: Colors.red)),
            ),
        ],
      ),
      actions: [
        TextButton.icon(
          onPressed: _copying ? null : _copy,
          icon: const Icon(Icons.copy),
          label: Text(_copying ? tr("复制中…") : tr("复制绑定码")),
        ),
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: Text(tr("完成")),
        ),
      ],
    );
  }
}
