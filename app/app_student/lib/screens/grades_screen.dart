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
  bool _changingGrade = false;
  bool _trendLoading = false;
  bool _assessing = false;
  String? _loadError;
  String? _subject;
  int? _rangeDays;

  @override
  void initState() {
    super.initState();
    _load();
  }

  List<String> get _subjects => (_grades ?? const [])
      .map((g) => (g as Map<String, dynamic>)['subject'] as String?)
      .whereType<String>()
      .toSet()
      .toList()
    ..sort();

  Future<void> _load() async {
    try {
      final values = await Future.wait([
        Api.I.studentGrades(includeDeleted: _includeDeleted),
        Api.I.studentGradeTrend(
          subject: _subject,
          from: trendFromDate(_rangeDays),
        ),
        Api.I.studentAcademicAssessments(),
      ]);
      if (mounted) {
        setState(() {
          _grades = values[0] as List<dynamic>;
          _trend = values[1] as Map<String, dynamic>;
          _assessmentRows = values[2] as List<dynamic>;
          _loadError = null;
        });
      }
    } on ApiException catch (e) {
      if (mounted && _grades == null) {
        setState(() => _loadError = e.message);
      } else if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(e.message)));
      }
    } catch (_) {
      if (mounted && _grades == null) {
        setState(() => _loadError = '成绩加载失败，请检查网络后重试');
      } else if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('刷新失败，请检查网络后重试')));
      }
    }
  }

  Future<void> _changeGrade(
    Future<void> Function() action,
    String success,
  ) async {
    if (_changingGrade) return;
    setState(() => _changingGrade = true);
    final messenger = ScaffoldMessenger.of(context);
    messenger.hideCurrentSnackBar();
    messenger.showSnackBar(
      const SnackBar(content: Text('正在处理成绩…'), duration: Duration(seconds: 30)),
    );
    try {
      await action();
      await _load();
      if (mounted) {
        messenger.hideCurrentSnackBar();
        messenger.showSnackBar(SnackBar(content: Text(success)));
      }
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
      if (mounted) setState(() => _changingGrade = false);
    }
  }

  /// 筛选变化只重取趋势，不刷新成绩与评估列表。
  Future<void> _loadTrend() async {
    setState(() => _trendLoading = true);
    try {
      final t = await Api.I.studentGradeTrend(
        subject: _subject,
        from: trendFromDate(_rangeDays),
      );
      if (mounted) setState(() => _trend = t);
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
        ).showSnackBar(const SnackBar(content: Text('趋势加载失败，请重试')));
      }
    } finally {
      if (mounted) setState(() => _trendLoading = false);
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
    await _changeGrade(() async {
      if (current == null) {
        await Api.I.addStudentGrade(body);
      } else {
        await Api.I.editStudentGrade(current['id'] as int, body);
      }
    }, current == null ? '成绩已添加' : '成绩已保存');
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
      await _changeGrade(
        () => Api.I.deleteStudentGrade(grade['id'] as int),
        '成绩已删除，可在“显示已删除成绩”中恢复',
      );
      return;
    }
    if (action == 'restore') {
      await _changeGrade(
        () => Api.I.restoreStudentGrade(grade['id'] as int),
        '成绩已恢复',
      );
      return;
    }
    if (action == 'history') {
      try {
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
          ).showSnackBar(const SnackBar(content: Text('修改历史加载失败，请重试')));
        }
      }
    }
  }

  Future<void> _assess() async {
    // 规格 7.3：按时间范围触发学业评估
    final range = await chooseAssessmentRange(context);
    if (range == null || !mounted) return;
    setState(() => _assessing = true);
    try {
      final r = await Api.I.studentAcademicAssessment(
        from: range.from,
        to: range.to,
      );
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
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('学业评估已更新')));
      }
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
        ).showSnackBar(const SnackBar(content: Text('学业评估失败，请检查网络后重试')));
      }
    } finally {
      if (mounted) setState(() => _assessing = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('成绩与学习评估'),
        actions: [
          IconButton(
            onPressed: _assessing ? null : _assess,
            icon: _assessing
                ? const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.insights),
            tooltip: '学业评估',
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: _changingGrade ? null : () => _edit(),
        child: const Icon(Icons.add),
      ),
      body: _grades == null
          ? Center(
              child: _loadError == null
                  ? const CircularProgressIndicator()
                  : Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(_loadError!),
                        TextButton(
                          onPressed: () {
                            setState(() => _loadError = null);
                            _load();
                          },
                          child: const Text('重试'),
                        ),
                      ],
                    ),
            )
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView(
                padding: const EdgeInsets.all(12),
                children: [
                  if (_trendLoading)
                    const LinearProgressIndicator(minHeight: 2),
                  GradeTrendCard(
                    trend: _trend,
                    subjects: _subjects,
                    subject: _subject,
                    rangeDays: _rangeDays,
                    onChanged: (subject, rangeDays) {
                      setState(() {
                        _subject = subject;
                        _rangeDays = rangeDays;
                      });
                      _loadTrend();
                    },
                  ),
                  if (_assessment != null) _assessmentCard(),
                  if (_assessmentRows != null) _assessmentHistoryCard(),
                  SwitchListTile(
                    contentPadding: EdgeInsets.zero,
                    title: const Text('显示已删除成绩'),
                    value: _includeDeleted,
                    onChanged: (value) {
                      setState(() {
                        _includeDeleted = value;
                        _grades = null;
                        _loadError = null;
                      });
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

  /// 当次学业评估结果：建议 + 证据会话 + 时间范围/模型 + 免责声明（规格 7.3）
  Widget _assessmentCard() {
    final period = _assessment?['period'] as Map<String, dynamic>?;
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
            const Text(
              '学业评估',
              style: TextStyle(fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 4),
            Text(
              (_assessment?['recommendations'] as List?)?.join('、') ?? '暂无建议',
            ),
            if (evidence.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text('证据会话：$evidence', style: const TextStyle(fontSize: 12)),
              ),
            const SizedBox(height: 4),
            Text(
              '时间范围：${period?['from'] ?? '-'} 至 ${period?['to'] ?? '-'} · 模型 ${_assessment?['model'] ?? '-'}',
              style: const TextStyle(fontSize: 12, color: Colors.grey),
            ),
            Text(
              _assessment?['disclaimer'] as String? ??
                  'AI 辅助估计，不是学校成绩或诊断。',
              style: const TextStyle(fontSize: 12, color: Colors.grey),
            ),
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
