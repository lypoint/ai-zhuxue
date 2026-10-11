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
  late final TextEditingController _forbiddenWordsCtrl;
  late bool _quietEnabled;
  late int _quietStart;
  late int _quietEnd;
  late bool _notifyFence;
  bool _saving = false;

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
  }

  @override
  void dispose() {
    _capCtrl.dispose();
    _minutesCtrl.dispose();
    _forbiddenWordsCtrl.dispose();
    super.dispose();
  }

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
          ? '每日对话消息上限需为 10–1000 条'
          : '每日使用时长上限需为 0–480 分钟';
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(message)));
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
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('已保存')));
      widget.onSaved();
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              e.status == 422 ? '保存失败，请检查输入的设置' : '保存失败：${e.message}',
            ),
          ),
        );
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('保存失败，请检查网络后重试')));
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _section(context, Icons.schedule_rounded, '每日使用', '合理安排对话次数与学习时长'),
            const SizedBox(height: 20),
            TextField(
              controller: _capCtrl,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(
                labelText: '每日对话消息上限',
                helperText: '10–1000 条',
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _minutesCtrl,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(
                labelText: '每日使用时长上限',
                helperText: '0–480 分钟，0 表示不限',
                helperMaxLines: 2,
              ),
            ),
            const SizedBox(height: 12),
            const Divider(height: 32),
            _section(
              context,
              Icons.nights_stay_outlined,
              '休息时段',
              '为孩子留出充足的休息时间',
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                const Expanded(child: Text('休息时段限制')),
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
                  const Text('禁用时段'),
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
            const Divider(height: 32),
            _section(
              context,
              Icons.shield_outlined,
              '内容与通知',
              '设置家庭规则，及时了解学习动态',
            ),
            const SizedBox(height: 20),
            TextField(
              controller: _forbiddenWordsCtrl,
              minLines: 3,
              maxLines: 6,
              decoration: const InputDecoration(
                labelText: '违禁词列表（每行一个）',
                helperText: '包含任一词即拒绝回答，忽略英文大小写；清空后取消自定义限制',
                helperMaxLines: 4,
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
            const SizedBox(height: 24),
            FilledButton(
              onPressed: _saving ? null : _save,
              child: Text(_saving ? '保存中…' : '保存设置'),
            ),
          ],
        ),
      ),
    );
  }

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
