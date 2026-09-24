import 'package:flutter/material.dart';
import 'package:app_core/app_core.dart';

/// 未成年人模式管控设置卡：每日消息/时长上限、引导通知开关、休息时段。
/// 自持表单状态，保存后回调 [onSaved] 让首页刷新总览。
class ManagementSettingsCard extends StatefulWidget {
  final Map<String, dynamic> settings;
  final VoidCallback onSaved;
  const ManagementSettingsCard({
    super.key,
    required this.settings,
    required this.onSaved,
  });

  @override
  State<ManagementSettingsCard> createState() => _ManagementSettingsCardState();
}

class _ManagementSettingsCardState extends State<ManagementSettingsCard> {
  late final TextEditingController _capCtrl;
  late final TextEditingController _minutesCtrl;
  late bool _quietEnabled;
  late int _quietStart;
  late int _quietEnd;
  late bool _notifyFence;

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
    _quietEnabled = s['quiet_enabled'] as bool? ?? true;
    _quietStart = s['quiet_start'] as int? ?? 22;
    _quietEnd = s['quiet_end'] as int? ?? 6;
    _notifyFence = s['notify_fence'] as bool? ?? true;
  }

  @override
  void dispose() {
    _capCtrl.dispose();
    _minutesCtrl.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    await Api.I.updateSettings(
      int.tryParse(_capCtrl.text) ?? 200,
      widget.settings['review_enabled'] as bool? ?? true,
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
    widget.onSaved();
  }
  @override
  Widget build(BuildContext context) {
    return Card(
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
            OutlinedButton(onPressed: _save, child: const Text('保存设置')),
          ],
        ),
      ),
    );
  }
}
