import 'package:flutter/material.dart';
import 'package:app_core/app_core.dart';

/// 家长端成绩、趋势和评估：编辑只通过服务端版本接口完成。
class GradesScreen extends StatefulWidget {
  final int studentId;
  final String studentName;
  const GradesScreen({
    super.key,
    required this.studentId,
    required this.studentName,
  });
  @override
  State<GradesScreen> createState() => _GradesScreenState();
}

class _GradesScreenState extends State<GradesScreen> {
  List<dynamic>? _grades;
  Map<String, dynamic>? _trend;
  Map<String, dynamic>? _assessment;
  List<dynamic>? _academicRows;
  List<dynamic>? _wellbeingRows;
  bool _includeDeleted = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final values = await Future.wait([
        Api.I.parentGrades(widget.studentId, includeDeleted: _includeDeleted),
        Api.I.parentGradeTrend(widget.studentId),
        Api.I.parentAcademicAssessments(widget.studentId),
        Api.I.parentWellbeingAssessments(widget.studentId),
      ]);
      if (!mounted) return;
      setState(() {
        _grades = values[0] as List<dynamic>;
        _trend = values[1] as Map<String, dynamic>;
        _academicRows = values[2] as List<dynamic>;
        _wellbeingRows = values[3] as List<dynamic>;
      });
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  Future<void> _addOrEdit([Map<String, dynamic>? current]) async {
    final subject = TextEditingController(
      text: current?['subject'] as String? ?? '',
    );
    final title = TextEditingController(
      text: current?['title'] as String? ?? '',
    );
    final date = TextEditingController(
      text:
          current?['exam_date'] as String? ??
          DateTime.now().toIso8601String().substring(0, 10),
    );
    final score = TextEditingController(
      text: current?['score']?.toString() ?? '',
    );
    final max = TextEditingController(
      text: current?['max_score']?.toString() ?? '100',
    );
    final term = TextEditingController(text: current?['term'] as String? ?? '');
    final gradeType = TextEditingController(
      text: current?['grade_type'] as String? ?? 'exam',
    );
    final note = TextEditingController(text: current?['note'] as String? ?? '');
    final form = <String, TextEditingController>{
      'subject': subject,
      'title': title,
      'exam_date': date,
      'score': score,
      'max_score': max,
      'term': term,
      'grade_type': gradeType,
      'note': note,
    };
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(current == null ? '新增成绩' : '编辑成绩'),
        content: SizedBox(
          width: 360,
          child: SingleChildScrollView(
            child: Column(
              children: [
                for (final entry in form.entries)
                  TextField(
                    controller: entry.value,
                    decoration: InputDecoration(labelText: _label(entry.key)),
                    keyboardType: {'score', 'max_score'}.contains(entry.key)
                        ? TextInputType.number
                        : TextInputType.text,
                  ),
              ],
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('保存'),
          ),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    final body = {
      'subject': subject.text,
      'title': title.text,
      'exam_date': date.text,
      'score': double.tryParse(score.text),
      'max_score': double.tryParse(max.text),
      'term': term.text,
      'grade_type': gradeType.text,
      'note': note.text,
      'reason': current == null ? 'created' : 'edited',
    };
    try {
      if (current == null) {
        await Api.I.addParentGrade(widget.studentId, body);
      } else {
        await Api.I.editParentGrade(
          widget.studentId,
          current['id'] as int,
          body,
        );
      }
      _load();
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  String _label(String key) =>
      const {
        'subject': '科目',
        'title': '考试/作业名称',
        'exam_date': '日期 YYYY-MM-DD',
        'score': '得分',
        'max_score': '满分',
        'term': '学期',
        'grade_type': '成绩类型（exam/homework/quiz/other）',
        'note': '备注',
      }[key] ??
      key;

  Future<void> _showGrade(Map<String, dynamic> grade) async {
    final action = await showModalBottomSheet<String>(
      context: context,
      builder: (ctx) => SafeArea(
        child: Wrap(
          children: [
            ListTile(
              title: Text(
                '${grade['subject']} · ${grade['score']}/${grade['max_score']}',
              ),
            ),
            if (grade['deleted'] != true)
              ListTile(
                leading: const Icon(Icons.edit),
                title: const Text('编辑'),
                onTap: () => Navigator.pop(ctx, 'edit'),
              ),
            ListTile(
              leading: const Icon(Icons.history),
              title: const Text('查看修改历史'),
              onTap: () => Navigator.pop(ctx, 'history'),
            ),
            if (grade['deleted'] == true)
              ListTile(
                leading: const Icon(Icons.restore),
                title: const Text('恢复成绩'),
                onTap: () => Navigator.pop(ctx, 'restore'),
              )
            else
              ListTile(
                leading: const Icon(Icons.delete_outline),
                title: const Text('逻辑删除'),
                onTap: () => Navigator.pop(ctx, 'delete'),
              ),
          ],
        ),
      ),
    );
    if (!mounted || action == null) return;
    if (action == 'edit') return _addOrEdit(grade);
    if (action == 'history') {
      try {
        final rows = await Api.I.parentGradeHistory(
          widget.studentId,
          grade['id'] as int,
        );
        if (!mounted) return;
        showDialog<void>(
          context: context,
          builder: (ctx) => AlertDialog(
            title: const Text('成绩修改历史'),
            content: SizedBox(
              width: 360,
              child: ListView(
                shrinkWrap: true,
                children: rows
                    .map(
                      (r) => ListTile(
                        title: Text(
                          'v${r['version']} · ${r['score']}/${r['max_score']}',
                        ),
                        subtitle: Text(
                          '${r['edited_by_role']} · ${r['reason'] ?? ''}',
                        ),
                      ),
                    )
                    .toList(),
              ),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(ctx),
                child: const Text('关闭'),
              ),
            ],
          ),
        );
      } on ApiException catch (e) {
        if (mounted) {
          ScaffoldMessenger.of(
            context,
          ).showSnackBar(SnackBar(content: Text(e.message)));
        }
      }
    }
    if (action == 'delete') {
      await Api.I.deleteParentGrade(widget.studentId, grade['id'] as int);
      _load();
    }
    if (action == 'restore') {
      await Api.I.restoreParentGrade(widget.studentId, grade['id'] as int);
      _load();
    }
  }

  Future<void> _assess() async {
    try {
      final result = await Api.I.parentAcademicAssessment(widget.studentId);
      if (mounted) {
        setState(() {
          _assessment = result;
          _academicRows = [
            result,
            ...?_academicRows?.where(
              (row) => row['assessment_id'] != result['assessment_id'],
            ),
          ];
        });
      }
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  Future<void> _runWellbeing() async {
    try {
      final result = await Api.I.parentWellbeingAssessment(widget.studentId);
      if (mounted) {
        setState(() => _wellbeingRows = [result, ...?_wellbeingRows]);
      }
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: Text('${widget.studentName} · 学习记录'),
      actions: [
        IconButton(
          onPressed: _assess,
          icon: const Icon(Icons.insights),
          tooltip: '学业评估',
        ),
        IconButton(
          onPressed: _runWellbeing,
          icon: const Icon(Icons.favorite_border),
          tooltip: '身心状态关注',
        ),
      ],
    ),
    floatingActionButton: FloatingActionButton(
      onPressed: () => _addOrEdit(),
      child: const Icon(Icons.add),
    ),
    body: _grades == null
        ? const Center(child: CircularProgressIndicator())
        : RefreshIndicator(
            onRefresh: _load,
            child: ListView(
              padding: const EdgeInsets.all(12),
              children: [
                _trendCard(),
                if (_assessment != null) _assessmentCard(),
                if (_academicRows != null) _academicHistoryCard(),
                if (_wellbeingRows != null)
                  ..._wellbeingRows!.map(_wellbeingCard),
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('显示已删除成绩'),
                  value: _includeDeleted,
                  onChanged: (value) {
                    setState(() => _includeDeleted = value);
                    _load();
                  },
                ),
                if (_grades!.isEmpty)
                  const Padding(
                    padding: EdgeInsets.all(28),
                    child: Center(child: Text('还没有成绩记录')),
                  ),
                ..._grades!.map(
                  (g) => Card(
                    child: ListTile(
                      onTap: () => _showGrade(g as Map<String, dynamic>),
                      title: Text('${g['subject']} · ${g['title'] ?? ''}'),
                      subtitle: Text(
                        '${g['exam_date']} · ${g['term'] ?? ''} · ${g['grade_type'] ?? 'exam'}',
                      ),
                      trailing: Text('${g['score']}/${g['max_score']}'),
                    ),
                  ),
                ),
              ],
            ),
          ),
  );

  Widget _trendCard() {
    final t = _trend ?? {};
    return Card(
      child: ListTile(
        leading: const Icon(Icons.show_chart),
        title: Text('趋势：${t['direction'] ?? 'insufficient'}'),
        subtitle: Text(
          '最近 ${t['latest'] ?? '-'}% · 变化 ${t['delta'] ?? '-'} · 近三次平均 ${t['average_last_3'] ?? '-'}%',
        ),
      ),
    );
  }

  Widget _assessmentCard() {
    final subjects = (_assessment?['subjects'] as List?) ?? const [];
    final evidence = subjects
        .map((s) {
          final item = s as Map;
          final ids = (item['evidence_conversation_ids'] as List?) ?? const [];
          return '${item['subject']}（会话 ${ids.join('、')}）';
        })
        .join('、');
    return Card(
      color: const Color(0xFFE8F5F1),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('学业评估', style: TextStyle(fontWeight: FontWeight.bold)),
            Text((_assessment?['recommendations'] as List?)?.join('、') ?? '暂无建议'),
            if (evidence.isNotEmpty)
              Text('证据会话：$evidence', style: const TextStyle(fontSize: 12)),
            const Text(
              'AI 辅助估计，不是学校成绩或诊断。',
              style: TextStyle(fontSize: 12, color: Colors.grey),
            ),
          ],
        ),
      ),
    );
  }

  Widget _academicHistoryCard() => Card(
    child: ExpansionTile(
      title: Text('学业评估历史（${_academicRows!.length}）'),
      children: _academicRows!.map((raw) {
        final item = raw as Map<String, dynamic>;
        final period = item['period'] as Map<String, dynamic>?;
        final subjects = (item['subjects'] as List?) ?? const [];
        return ListTile(
          dense: true,
          title: Text(
            '${period?['from'] ?? '-'} 至 ${period?['to'] ?? '-'} · ${item['model'] ?? ''}',
          ),
          subtitle: Text(
            subjects.isEmpty
                ? '暂无识别到学科主题'
                : subjects.map((s) => (s as Map)['subject']).join('、'),
          ),
        );
      }).toList(),
    ),
  );
  Widget _wellbeingCard(dynamic value) {
    final item = value as Map<String, dynamic>;
    final signals = (item['signals'] as List?) ?? const [];
    return Card(
      child: ExpansionTile(
        leading: const Icon(Icons.favorite, color: Colors.orange),
        title: const Text('身心状态关注提示'),
        subtitle: Text(
          signals.isEmpty
              ? '暂未发现需要关注的表达'
              : signals.map((s) => (s as Map)['summary']).join('、'),
        ),
        trailing: item['ack_status'] == 'pending'
            ? PopupMenuButton<String>(
                onSelected: (status) async {
                  await Api.I.ackWellbeingAssessment(
                    item['assessment_id'] as int,
                    status,
                  );
                  _load();
                },
                itemBuilder: (_) => const [
                  PopupMenuItem(value: 'acknowledged', child: Text('已关注')),
                  PopupMenuItem(value: 'not_needed', child: Text('无需跟进')),
                ],
              )
            : const Icon(Icons.check),
        children: signals.expand((raw) {
          final signal = raw as Map<String, dynamic>;
          final evidence = (signal['evidence'] as List?) ?? const [];
          return [
            ListTile(
              dense: true,
              title: Text('${signal['type']} · ${signal['level']}'),
              subtitle: Text(
                evidence.isEmpty
                    ? '暂无原文证据'
                    : evidence
                          .map((e) => (e as Map)['excerpt'] ?? '')
                          .join('\n'),
              ),
            ),
          ];
        }).toList(),
      ),
    );
  }
}
