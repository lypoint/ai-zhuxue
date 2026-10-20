import 'package:flutter/material.dart';
import 'package:app_core/app_core.dart';

/// 未成年人模式管控设置卡：每日消息/时长上限、引导通知开关、休息时段。
/// 自持表单状态，保存后回调 [onSaved] 让首页刷新总览。
class ManagementSettingsCard extends StatefulWidget {
  final Map<String, dynamic> settings;
  final VoidCallback onSaved;
  final bool scrollable;
  const ManagementSettingsCard({
    super.key,
    this.scrollable = false,
    required this.settings,
    required this.onSaved,
  });

  @override
  State<ManagementSettingsCard> createState() => _ManagementSettingsCardState();
}

class _ManagementSettingsCardState extends State<ManagementSettingsCard> {
  late final TextEditingController _capCtrl;
  late final TextEditingController _minutesCtrl;
  late final TextEditingController _forbiddenWordsCtrl;
  late bool _quietEnabled;
  late int _quietStart;
  late int _quietEnd;
  late bool _notifyFence;
  bool _saving = false;
  late String _savedValue;
  String get _value =>
      '${_capCtrl.text}|${_minutesCtrl.text}|${_forbiddenWordsCtrl.text}|$_quietEnabled|$_quietStart|$_quietEnd|$_notifyFence';
  bool get _dirty => _value != _savedValue;
  void _changed() => setState(() {});

  @override
  void initState() {
    super.initState();
    final s = widget.settings;
    _capCtrl = TextEditingController(
      text: (s['daily_message_cap'] as num).toString(),
    );
    _minutesCtrl = TextEditingController(
      text: (s['daily_minutes_cap'] as num).toString(),
    );
    _forbiddenWordsCtrl = TextEditingController(
      text: (s['forbidden_words'] as List? ?? []).join('\n'),
    );
    _quietEnabled = s['quiet_enabled'] as bool? ?? true;
    _quietStart = s['quiet_start'] as int? ?? 22;
    _quietEnd = s['quiet_end'] as int? ?? 6;
    _notifyFence = s['notify_fence'] as bool? ?? true;
    _savedValue = _value;
    for (final controller in [_capCtrl, _minutesCtrl, _forbiddenWordsCtrl]) {
      controller.addListener(_changed);
    }
  }

  @override
  void dispose() {
    _capCtrl.dispose();
    _minutesCtrl.dispose();
    _forbiddenWordsCtrl.dispose();
    super.dispose();
  }

  SnackBar _snackBar(String message) => SnackBar(
    content: Text(message),
    behavior: SnackBarBehavior.floating,
    margin: EdgeInsets.fromLTRB(16, 0, 16, widget.scrollable ? 96 : 16),
  );

  Future<void> _save() async {
    if (_saving) return;
    final cap = int.tryParse(_capCtrl.text.trim());
    final minutes = int.tryParse(_minutesCtrl.text.trim());
    if (cap == null ||
        cap < 10 ||
        cap > 1000 ||
        minutes == null ||
        minutes < 0 ||
        minutes > 480) {
      final message = cap == null || cap < 10 || cap > 1000
          ? tr("每日对话消息上限需为 10–1000 条")
          : tr("每日使用时长上限需为 0–480 分钟");
      ScaffoldMessenger.of(context).showSnackBar(_snackBar(message));
      return;
    }
    setState(() => _saving = true);
    try {
      await Api.I.updateSettings(
        cap,
        widget.settings['review_enabled'] as bool? ?? true,
        quietEnabled: _quietEnabled,
        quietStart: _quietStart,
        quietEnd: _quietEnd,
        dailyMinutesCap: minutes,
        notifyFence: _notifyFence,
        forbiddenWords: _forbiddenWordsCtrl.text
            .split('\n')
            .map((word) => word.trim())
            .where((word) => word.isNotEmpty)
            .toSet()
            .toList(),
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(_snackBar(tr("已保存")));
      setState(() => _savedValue = _value);
      widget.onSaved();
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          _snackBar(
            e.status == 422 ? tr("保存失败，请检查输入的设置") : tr("保存失败：{0}", [e.message]),
          ),
        );
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(_snackBar(tr("保存失败，请检查网络后重试")));
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    AppLanguage.watch(context);
    final form = Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _section(
              context,
              Icons.schedule_rounded,
              tr("每日使用"),
              tr("合理安排对话次数与学习时长"),
            ),
            const SizedBox(height: 20),
            TextField(
              controller: _capCtrl,
              keyboardType: TextInputType.number,
              decoration: InputDecoration(
                labelText: tr("每日对话消息上限"),
                helperText: tr("10–1000 条"),
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _minutesCtrl,
              keyboardType: TextInputType.number,
              decoration: InputDecoration(
                labelText: tr("每日使用时长上限"),
                helperText: tr("0–480 分钟，0 表示不限"),
                helperMaxLines: 2,
              ),
            ),
            Wrap(
              spacing: 8,
              children: [
                for (final minutes in [30, 60, 90])
                  ActionChip(
                    label: Text(tr("{0} 分钟", [minutes])),
                    onPressed: () => _minutesCtrl.text = '$minutes',
                  ),
              ],
            ),
            const Divider(height: 32),
            _section(
              context,
              Icons.nights_stay_outlined,
              tr("休息时段"),
              tr("为孩子留出充足的休息时间"),
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(child: Text(tr("休息时段限制"))),
                Switch(
                  value: _quietEnabled,
                  onChanged: (v) => setState(() => _quietEnabled = v),
                ),
              ],
            ),
            if (_quietEnabled)
              Wrap(
                spacing: 8,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  Text(tr("禁用时段")),
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
                  Text(tr(" 至 ")),
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
            if (_quietEnabled)
              Wrap(
                spacing: 8,
                children: [
                  for (final hours in [(21, 7), (22, 6)])
                    ChoiceChip(
                      label: Text(
                        '${hours.$1}:00 → ${hours.$2.toString().padLeft(2, '0')}:00',
                      ),
                      selected:
                          _quietStart == hours.$1 && _quietEnd == hours.$2,
                      onSelected: (_) => setState(() {
                        _quietStart = hours.$1;
                        _quietEnd = hours.$2;
                      }),
                    ),
                ],
              ),
            const Divider(height: 32),
            _section(
              context,
              Icons.shield_outlined,
              tr("内容与通知"),
              tr("设置家庭规则，及时了解学习动态"),
            ),
            const SizedBox(height: 20),
            TextField(
              controller: _forbiddenWordsCtrl,
              minLines: 3,
              maxLines: 6,
              decoration: InputDecoration(
                labelText: tr("违禁词列表（每行一个）"),
                helperText: tr("包含任一词即拒绝回答，忽略英文大小写；清空后取消自定义限制"),
                helperMaxLines: 4,
              ),
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: Text(
                    tr("学习引导通知\n（拦截/改写类，安全告警不受此开关影响）"),
                    style: TextStyle(fontSize: 12),
                  ),
                ),
                Switch(
                  value: _notifyFence,
                  onChanged: (v) => setState(() => _notifyFence = v),
                ),
              ],
            ),
            if (!widget.scrollable) _saveBar(),
          ],
        ),
      ),
    );
    if (!widget.scrollable) return form;
    return Column(
      children: [
        Expanded(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(20),
            child: Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 640),
                child: AbsorbPointer(absorbing: _saving, child: form),
              ),
            ),
          ),
        ),
        Material(
          color: Theme.of(context).colorScheme.surface,
          elevation: 4,
          child: SafeArea(
            top: false,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
              child: _saveBar(),
            ),
          ),
        ),
      ],
    );
  }

  Widget _saveBar() => Row(
    children: [
      Expanded(
        child: Text(
          _dirty ? tr("有未保存的修改") : tr("已保存"),
          style: TextStyle(
            color: Theme.of(context).colorScheme.onSurfaceVariant,
          ),
        ),
      ),
      const SizedBox(width: 12),
      Expanded(
        flex: 2,
        child: FilledButton(
          onPressed: _saving || !_dirty ? null : _save,
          child: Text(
            _saving ? tr("保存中…") : tr("保存设置"),
            textAlign: TextAlign.center,
          ),
        ),
      ),
    ],
  );

  Widget _section(
    BuildContext context,
    IconData icon,
    String title,
    String subtitle,
  ) {
    final scheme = Theme.of(context).colorScheme;
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        CircleAvatar(
          radius: 20,
          backgroundColor: scheme.primaryContainer,
          child: Icon(icon, color: scheme.primary, size: 20),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                title,
                style: const TextStyle(
                  fontWeight: FontWeight.w700,
                  fontSize: 16,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                subtitle,
                style: TextStyle(
                  fontSize: 12,
                  height: 1.5,
                  color: scheme.onSurfaceVariant,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}
