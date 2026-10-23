import 'package:app_core/app_core.dart';
import 'package:flutter/material.dart';

/// Adding a child confirms these settings before the child and code are created.
class StudentFenceDialog extends StatefulWidget {
  final String studentName;
  final int? studentId;
  final Map<String, dynamic> settings;
  const StudentFenceDialog({
    super.key,
    required this.studentName,
    this.studentId,
    this.settings = const {},
  });

  @override
  State<StudentFenceDialog> createState() => _StudentFenceDialogState();
}

class _StudentFenceDialogState extends State<StudentFenceDialog> {
  late String _level;
  late final TextEditingController _words;
  bool _saving = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _level = widget.settings['fence_level'] as String? ?? 'strict';
    _words = TextEditingController(
      text: (widget.settings['forbidden_words'] as List? ?? []).join('\n'),
    );
  }

  @override
  void dispose() {
    _words.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (_saving) return;
    final words = _words.text
        .split('\n')
        .map((w) => w.trim())
        .where((w) => w.isNotEmpty)
        .toSet()
        .toList();
    if (words.length > 500 || words.any((w) => w.length > 100)) {
      setState(() => _error = tr("每个违禁词最多 100 个字符，最多 500 个。"));
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final id = widget.studentId;
      if (id != null) {
        await Api.I.updateStudentFenceSettings(
          id,
          fenceLevel: _level,
          forbiddenWords: words,
        );
      }
      if (mounted) {
        Navigator.pop(context, {
          'fence_level': _level,
          'forbidden_words': words,
        });
      }
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } catch (_) {
      if (mounted) setState(() => _error = tr("保存失败，请检查网络后重试"));
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    AppLanguage.watch(context);
    return PopScope(
      canPop: !_saving,
      child: AlertDialog(
        title: Text(tr("{0} 的围栏设置", [widget.studentName])),
        content: SingleChildScrollView(
          child: AbsorbPointer(
            absorbing: _saving,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(tr("请为这位孩子选择围栏强度和违禁词，仅对这位孩子生效，之后可随时修改。")),
                const SizedBox(height: 16),
                DropdownButtonFormField<String>(
                  value: _level,
                  isExpanded: true,
                  decoration: InputDecoration(labelText: tr("围栏强度")),
                  items: [
                    DropdownMenuItem(value: 'strict', child: Text(tr("严格"))),
                    DropdownMenuItem(value: 'relaxed', child: Text(tr("宽松"))),
                    DropdownMenuItem(value: 'off', child: Text(tr("不设围栏"))),
                  ],
                  onChanged: (value) {
                    if (value != null) setState(() => _level = value);
                  },
                ),
                const SizedBox(height: 8),
                Text(
                  tr(switch (_level) {
                    'relaxed' => '宽松：允许普通闲聊；有害内容引导回学习。',
                    'off' => '不设围栏：不按内容限制话题，仍执行自定义违禁词。',
                    _ => '严格：非学习内容引导回学习，敏感内容拒答并引导。',
                  }),
                ),
                const SizedBox(height: 16),
                TextField(
                  controller: _words,
                  minLines: 3,
                  maxLines: 6,
                  decoration: InputDecoration(
                    labelText: tr("违禁词列表（每行一个）"),
                    helperText: tr("自定义违禁词始终优先，命中后拒答并引导学习。"),
                    helperMaxLines: 4,
                  ),
                ),
                if (_error != null) ...[
                  const SizedBox(height: 8),
                  Text(
                    _error!,
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.error,
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: _saving ? null : () => Navigator.pop(context),
            child: Text(tr("取消")),
          ),
          FilledButton(
            onPressed: _saving ? null : _save,
            child: Text(
              _saving
                  ? tr("保存中…")
                  : widget.studentId == null
                  ? tr("保存并继续")
                  : tr("保存设置"),
            ),
          ),
        ],
      ),
    );
  }
}
