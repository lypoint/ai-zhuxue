import 'package:app_core/app_core.dart';
import 'package:flutter/material.dart';

/// Keep the draft alive until the server confirms the save.
class StudentGradeDialog extends StatefulWidget {
  final Map<String, dynamic>? current;
  final Future<void> Function(Map<String, dynamic>) onSave;
  const StudentGradeDialog({super.key, this.current, required this.onSave});

  @override
  State<StudentGradeDialog> createState() => _StudentGradeDialogState();
}

class _StudentGradeDialogState extends State<StudentGradeDialog> {
  final _form = GlobalKey<FormState>();
  late final _fields = {
    for (final key in [
      'subject',
      'exam_date',
      'score',
      'max_score',
      'title',
      'term',
      'note',
    ])
      key: TextEditingController(
        text:
            widget.current?[key]?.toString() ??
            (key == 'exam_date'
                ? DateTime.now().toIso8601String().substring(0, 10)
                : key == 'max_score'
                ? '100'
                : ''),
      ),
  };
  late String _type =
      const [
        'exam',
        'homework',
        'quiz',
        'other',
      ].contains(widget.current?['grade_type'])
      ? widget.current!['grade_type'] as String
      : 'exam';
  bool _saving = false;
  String? _error;

  @override
  void dispose() {
    for (final controller in _fields.values) {
      controller.dispose();
    }
    super.dispose();
  }

  Future<void> _save() async {
    if (_saving || !_form.currentState!.validate()) return;
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await widget.onSave({
        for (final field in _fields.entries) field.key: field.value.text.trim(),
        'score': double.parse(_fields['score']!.text.trim()),
        'max_score': double.parse(_fields['max_score']!.text.trim()),
        'grade_type': _type,
        'reason': widget.current == null ? 'created' : 'edited',
      });
      if (mounted) Navigator.pop(context, true);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } catch (_) {
      if (mounted) setState(() => _error = tr('操作失败，请检查网络后重试'));
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Widget _field(
    String key,
    String label, {
    bool number = false,
    bool required = false,
  }) => Padding(
    padding: const EdgeInsets.only(bottom: 12),
    child: TextFormField(
      key: ValueKey(key),
      controller: _fields[key],
      enabled: !_saving,
      keyboardType: number
          ? const TextInputType.numberWithOptions(decimal: true)
          : TextInputType.text,
      readOnly: key == 'exam_date',
      decoration: InputDecoration(
        labelText: tr(label),
        suffixIcon: key == 'exam_date'
            ? const Icon(Icons.calendar_today_outlined)
            : null,
      ),
      onTap: key != 'exam_date'
          ? null
          : () async {
              final date = await showDatePicker(
                context: context,
                initialDate:
                    (DateTime.tryParse(_fields[key]!.text) ?? DateTime.now())
                        .clampDate(),
                firstDate: DateTime(2000),
                lastDate: DateTime(2100, 12, 31),
              );
              if (date != null && mounted) {
                _fields[key]!.text = date.toIso8601String().substring(0, 10);
              }
            },
      validator: (value) {
        final text = value?.trim() ?? '';
        if (required && text.isEmpty) return tr('请填写此项');
        if (number) {
          final n = double.tryParse(text);
          if (n == null ||
              !n.isFinite ||
              n < 0 ||
              (key == 'max_score' && n == 0)) {
            return tr('请输入有效分数');
          }
          final max = double.tryParse(_fields['max_score']!.text.trim());
          if (key == 'score' && max != null && n > max) {
            return tr('得分不能超过满分');
          }
        }
        return null;
      },
    ),
  );

  @override
  Widget build(BuildContext context) => PopScope(
    canPop: !_saving,
    child: AlertDialog(
      title: Text(widget.current == null ? tr('新增成绩') : tr('编辑成绩')),
      content: SizedBox(
        width: 360,
        child: SingleChildScrollView(
          child: Form(
            key: _form,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                _field('subject', '科目', required: true),
                _field('exam_date', '日期', required: true),
                _field('score', '得分', number: true, required: true),
                _field('max_score', '满分', number: true, required: true),
                ExpansionTile(
                  title: Text(tr('更多信息（选填）')),
                  tilePadding: EdgeInsets.zero,
                  children: [
                    _field('title', '考试/作业名称'),
                    DropdownButtonFormField<String>(
                      value: _type,
                      decoration: InputDecoration(labelText: tr('成绩类型')),
                      items: [
                        for (final entry in {
                          'exam': '考试',
                          'homework': '作业',
                          'quiz': '测验',
                          'other': '其他',
                        }.entries)
                          DropdownMenuItem(
                            value: entry.key,
                            child: Text(tr(entry.value)),
                          ),
                      ],
                      onChanged: _saving
                          ? null
                          : (value) => setState(() => _type = value!),
                    ),
                    const SizedBox(height: 12),
                    _field('term', '学期'),
                    _field('note', '备注'),
                  ],
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
      ),
      actions: [
        TextButton(
          onPressed: _saving ? null : () => Navigator.pop(context, false),
          child: Text(tr('取消')),
        ),
        FilledButton(
          onPressed: _saving ? null : _save,
          child: _saving
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : Text(tr('保存')),
        ),
      ],
    ),
  );
}

extension on DateTime {
  DateTime clampDate() => isBefore(DateTime(2000))
      ? DateTime(2000)
      : isAfter(DateTime(2100, 12, 31))
      ? DateTime(2100, 12, 31)
      : this;
}
