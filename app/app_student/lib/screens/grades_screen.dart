import 'package:flutter/material.dart';
import 'package:app_core/app_core.dart';

class GradesScreen extends StatefulWidget {
  const GradesScreen({super.key});
  @override
  State<GradesScreen> createState() => _GradesScreenState();
}

class _GradesScreenState extends State<GradesScreen> {
  List<dynamic>? _grades;
  Map<String, dynamic>? _trend;
  Map<String, dynamic>? _assessment;
  List<dynamic>? _assessmentRows;
  bool _includeDeleted = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final values = await Future.wait([
        Api.I.studentGrades(includeDeleted: _includeDeleted),
        Api.I.studentGradeTrend(),
        Api.I.studentAcademicAssessments(),
      ]);
      if (mounted)
        setState(() {
          _grades = values[0] as List<dynamic>;
          _trend = values[1] as Map<String, dynamic>;
          _assessmentRows = values[2] as List<dynamic>;
        });
    } on ApiException catch (e) {
      if (mounted)
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  Future<void> _edit([Map<String, dynamic>? current]) async {
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
    final gradeType = TextEditingController(
      text: current?['grade_type'] as String? ?? 'exam',
    );
    final term = TextEditingController(
      text: current?['term'] as String? ?? '',
    );
    final note = TextEditingController(text: current?['note'] as String? ?? '');
    final fields = [
      ('科目', subject, false),
      ('考试/作业名称', title, false),
      ('日期 YYYY-MM-DD', date, false),
      ('得分', score, true),
      ('满分', max, true),
      ('成绩类型（exam/homework/quiz/other）', gradeType, false),
      ('学期', term, false),
      ('备注', note, false),
    ];
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(current == null ? '新增成绩' : '编辑成绩'),
        content: SizedBox(
          width: 340,
          child: SingleChildScrollView(
            child: Column(
              children: [
                for (final f in fields)
                  TextField(
                    controller: f.$2,
                    keyboardType: f.$3
                        ? TextInputType.number
                        : TextInputType.text,
                    decoration: InputDecoration(labelText: f.$1),
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
      'grade_type': gradeType.text,
      'term': term.text,
      'note': note.text,
      'reason': current == null ? 'created' : 'edited',
    };
    try {
      if (current == null) {
        await Api.I.addStudentGrade(body);
      } else {
        await Api.I.editStudentGrade(current['id'] as int, body);
      }
      _load();
    } on ApiException catch (e) {
      if (mounted)
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  Future<void> _details(Map<String, dynamic> grade) async {
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
              title: const Text('历史'),
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
    if (action == 'edit') return _edit(grade);
    if (action == 'delete') {
      await Api.I.deleteStudentGrade(grade['id'] as int);
      _load();
      return;
    }
    if (action == 'restore') {
      await Api.I.restoreStudentGrade(grade['id'] as int);
      _load();
      return;
    }
    if (action == 'history') {
      final rows = await Api.I.studentGradeHistory(grade['id'] as int);
      if (!mounted) return;
      showDialog<void>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('修改历史'),
          content: SizedBox(
            width: 340,
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
    }
  }

  Future<void> _assess() async {
    try {
      final r = await Api.I.studentAcademicAssessment();
      if (mounted) {
        setState(() {
          _assessment = r;
          _assessmentRows = [
            r,
            ...?_assessmentRows?.where(
              (row) => row['assessment_id'] != r['assessment_id'],
            ),
          ];
        });
      }
    } on ApiException catch (e) {
      if (mounted)
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  @override
  Widget build(BuildContext context) {
    final trend = _trend ?? const <String, dynamic>{};
    return Scaffold(
      appBar: AppBar(
        title: const Text('成绩与学习评估'),
        actions: [
          IconButton(onPressed: _assess, icon: const Icon(Icons.insights)),
        ],
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: () => _edit(),
        child: const Icon(Icons.add),
      ),
      body: _grades == null
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView(
                padding: const EdgeInsets.all(12),
                children: [
                  Card(
                    child: ListTile(
                      leading: const Icon(Icons.show_chart),
                      title: Text('趋势：${trend['direction'] ?? 'insufficient'}'),
                      subtitle: Text(
                        '最近 ${trend['latest'] ?? '-'}% · 变化 ${trend['delta'] ?? '-'} · 近三次平均 ${trend['average_last_3'] ?? '-'}%',
                      ),
                    ),
                  ),
                  if (_assessment != null)
                    Card(
                      color: const Color(0xFFE8F5F1),
                      child: Padding(
                        padding: const EdgeInsets.all(12),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text(
                              '学业评估',
                              style: TextStyle(fontWeight: FontWeight.bold),
                            ),
                            Text(
                              (_assessment?['recommendations'] as List?)?.join(
                                    '、',
                                  ) ??
                                  '暂无建议',
                            ),
                            const Text(
                              'AI 辅助估计，不是学校成绩或诊断。',
                              style: TextStyle(
                                fontSize: 12,
                                color: Colors.grey,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  if (_assessmentRows != null) _assessmentHistoryCard(),
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
                      padding: EdgeInsets.all(30),
                      child: Center(child: Text('还没有成绩记录')),
                    ),
                  ..._grades!.map((raw) {
                    final grade = raw as Map<String, dynamic>;
                    return Card(
                      child: ListTile(
                        onTap: () => _details(grade),
                        title: Text(
                          '${grade['subject']} · ${grade['title'] ?? ''}',
                        ),
                        subtitle: Text(
                          '${grade['exam_date']} · ${grade['term'] ?? ''} · ${grade['grade_type'] ?? 'exam'}',
                        ),
                        trailing: Text(
                          '${grade['score']}/${grade['max_score']}',
                        ),
                      ),
                    );
                  }),
                ],
              ),
            ),
    );
  }

  Widget _assessmentHistoryCard() => Card(
    child: ExpansionTile(
      title: Text('学业评估历史（${_assessmentRows!.length}）'),
      children: _assessmentRows!.map((raw) {
        final item = raw as Map<String, dynamic>;
        final period = item['period'] as Map<String, dynamic>?;
        return ListTile(
          dense: true,
          title: Text(
            '${period?['from'] ?? '-'} 至 ${period?['to'] ?? '-'} · ${item['model'] ?? ''}',
          ),
          subtitle: Text(
            ((item['recommendations'] as List?) ?? const []).join('、'),
          ),
        );
      }).toList(),
    ),
  );
}
