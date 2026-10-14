import 'package:flutter/material.dart';
import 'package:app_core/app_core.dart';
import '../widgets/student_page_state.dart';

Map<String, String> get _gradeTypes => {
  'exam': tr('考试'),
  'homework': tr('作业'),
  'quiz': tr('测验'),
  'other': tr('其他'),
};

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

  List<String> get _subjects =>
      (_grades ?? const [])
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
        setState(() => _loadError = tr("成绩加载失败，请检查网络后重试"));
      } else if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(tr("刷新失败，请检查网络后重试"))));
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
      SnackBar(content: Text(tr("正在处理成绩…")), duration: Duration(seconds: 30)),
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
        messenger.showSnackBar(SnackBar(content: Text(tr("操作失败，请检查网络后重试"))));
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
        ).showSnackBar(SnackBar(content: Text(tr("趋势加载失败，请重试"))));
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
    final term = TextEditingController(text: current?['term'] as String? ?? '');
    final note = TextEditingController(text: current?['note'] as String? ?? '');
    final fields = [
      (tr("科目"), subject, false),
      (tr("考试/作业名称"), title, false),
      (tr("日期 YYYY-MM-DD"), date, false),
      (tr("得分"), score, true),
      (tr("满分"), max, true),
      (tr("成绩类型"), gradeType, false),
      (tr("学期"), term, false),
      (tr("备注"), note, false),
    ];
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(current == null ? tr("新增成绩") : tr("编辑成绩")),
        content: SizedBox(
          width: 340,
          child: SingleChildScrollView(
            child: Column(
              children: [
                for (final f in fields)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: f.$2 == gradeType
                        ? DropdownButtonFormField<String>(
                            value: _gradeTypes.containsKey(gradeType.text)
                                ? gradeType.text
                                : 'other',
                            decoration: InputDecoration(labelText: tr("成绩类型")),
                            items: _gradeTypes.entries
                                .map(
                                  (entry) => DropdownMenuItem(
                                    value: entry.key,
                                    child: Text(entry.value),
                                  ),
                                )
                                .toList(),
                            onChanged: (value) {
                              if (value != null) gradeType.text = value;
                            },
                          )
                        : TextField(
                            controller: f.$2,
                            keyboardType: f.$3
                                ? TextInputType.number
                                : TextInputType.text,
                            decoration: InputDecoration(labelText: f.$1),
                          ),
                  ),
              ],
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: Text(tr("取消")),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: Text(tr("保存")),
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
    }, current == null ? tr("成绩已添加") : tr("成绩已保存"));
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
                title: Text(tr("编辑")),
                onTap: () => Navigator.pop(ctx, 'edit'),
              ),
            ListTile(
              leading: const Icon(Icons.history),
              title: Text(tr("历史")),
              onTap: () => Navigator.pop(ctx, 'history'),
            ),
            if (grade['deleted'] == true)
              ListTile(
                leading: const Icon(Icons.restore),
                title: Text(tr("恢复成绩")),
                onTap: () => Navigator.pop(ctx, 'restore'),
              )
            else
              ListTile(
                leading: const Icon(Icons.delete_outline),
                title: Text(tr("逻辑删除")),
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
        tr("成绩已删除，可在“显示已删除成绩”中恢复"),
      );
      return;
    }
    if (action == 'restore') {
      await _changeGrade(
        () => Api.I.restoreStudentGrade(grade['id'] as int),
        tr("成绩已恢复"),
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
            title: Text(tr("修改历史")),
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
                child: Text(tr("关闭")),
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
          ).showSnackBar(SnackBar(content: Text(tr("修改历史加载失败，请重试"))));
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
        ).showSnackBar(SnackBar(content: Text(tr("学业评估已更新"))));
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
        ).showSnackBar(SnackBar(content: Text(tr("学业评估失败，请检查网络后重试"))));
      }
    } finally {
      if (mounted) setState(() => _assessing = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    AppLanguage.watch(context);
    return Scaffold(
      appBar: AppBar(
        title: Text(tr("成绩与学习评估")),
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
            tooltip: tr("学业评估"),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _changingGrade ? null : () => _edit(),
        icon: const Icon(Icons.add),
        label: Text(tr("记录成绩")),
      ),
      body: _grades == null
          ? (_loadError == null
                ? const Center(child: CircularProgressIndicator())
                : StudentPageState(
                    icon: Icons.wifi_off_rounded,
                    title: tr("成绩加载失败"),
                    description: _loadError!,
                    onRetry: () {
                      setState(() => _loadError = null);
                      _load();
                    },
                  ))
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView(
                padding: const EdgeInsets.fromLTRB(20, 12, 20, 100),
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
                    title: Text(tr("显示已删除成绩")),
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
                    StudentPageState(
                      icon: Icons.school_outlined,
                      title: tr("还没有成绩记录"),
                      description: tr("点击“记录成绩”，留下每一次学习的进步"),
                    ),
                  ..._grades!.map((raw) {
                    final grade = raw as Map<String, dynamic>;
                    final type = _gradeTypes[grade['grade_type']] ?? tr("其他");
                    return Card(
                      child: InkWell(
                        borderRadius: BorderRadius.circular(24),
                        onTap: () => _details(grade),
                        child: Padding(
                          padding: const EdgeInsets.all(18),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Wrap(
                                spacing: 12,
                                runSpacing: 8,
                                crossAxisAlignment: WrapCrossAlignment.center,
                                children: [
                                  Text(
                                    '${grade['subject']}',
                                    style: TextStyle(
                                      fontSize: 17,
                                      fontWeight: FontWeight.w700,
                                      color: Theme.of(
                                        context,
                                      ).colorScheme.primary,
                                    ),
                                  ),
                                  Text(
                                    '${grade['score']} / ${grade['max_score']}',
                                    style: const TextStyle(
                                      fontSize: 20,
                                      fontWeight: FontWeight.w800,
                                    ),
                                  ),
                                  if (grade['deleted'] == true) Text(tr("已删除")),
                                ],
                              ),
                              const SizedBox(height: 10),
                              Text(
                                grade['title'] as String? ?? '',
                                style: const TextStyle(
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                              const SizedBox(height: 6),
                              Text(
                                [grade['exam_date'], type, grade['term']]
                                    .where(
                                      (v) =>
                                          v != null && v.toString().isNotEmpty,
                                    )
                                    .join(' · '),
                                style: TextStyle(
                                  fontSize: 12,
                                  color: Theme.of(
                                    context,
                                  ).colorScheme.onSurfaceVariant,
                                ),
                              ),
                            ],
                          ),
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
          return tr("{0}（会话 {1}）", [
            trMessage(item['subject'].toString()),
            ids.join(', '),
          ]);
        })
        .join('、');
    return Card(
      color: const Color(0xFFE8F5F1),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(tr("学业评估"), style: TextStyle(fontWeight: FontWeight.bold)),
            const SizedBox(height: 4),
            Text(
              (_assessment?['recommendations'] as List?)
                      ?.map((value) => trMessage(value.toString()))
                      .join(', ') ??
                  tr("暂无建议"),
            ),
            if (evidence.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text(
                  tr("证据会话：{0}", [evidence]),
                  style: const TextStyle(fontSize: 12),
                ),
              ),
            const SizedBox(height: 4),
            Text(
              tr("时间范围：{0} 至 {1} · 模型 {2}", [
                period?['from'] ?? '-',
                period?['to'] ?? '-',
                _assessment?['model'] ?? '-',
              ]),
              style: const TextStyle(fontSize: 12, color: Colors.grey),
            ),
            Text(
              _assessment?['disclaimer'] as String? ?? tr("AI 辅助估计，不是学校成绩或诊断。"),
              style: const TextStyle(fontSize: 12, color: Colors.grey),
            ),
          ],
        ),
      ),
    );
  }

  Widget _assessmentHistoryCard() => Card(
    child: ExpansionTile(
      title: Text(tr("学业评估历史（{0}）", [_assessmentRows!.length])),
      children: _assessmentRows!.map((raw) {
        final item = raw as Map<String, dynamic>;
        final period = item['period'] as Map<String, dynamic>?;
        return ListTile(
          dense: true,
          title: Text(
            tr("{0} 至 {1} · {2}", [
              period?['from'] ?? '-',
              period?['to'] ?? '-',
              item['model'] ?? '',
            ]),
          ),
          subtitle: Text(
            ((item['recommendations'] as List?) ?? const [])
                .map((value) => trMessage(value.toString()))
                .join(', '),
          ),
        );
      }).toList(),
    ),
  );
}
