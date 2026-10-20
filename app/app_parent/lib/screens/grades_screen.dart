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
  bool _changingGrade = false;
  bool _trendLoading = false;
  bool _defaultSubjectSelected = false;
  String? _assessmentAction;
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
        Api.I.parentGrades(widget.studentId, includeDeleted: _includeDeleted),
        Api.I.parentAcademicAssessments(widget.studentId),
        Api.I.parentWellbeingAssessments(widget.studentId),
      ]);
      if (!mounted) return;
      setState(() {
        _grades = values[0];
        _academicRows = values[1];
        _wellbeingRows = values[2];
        if (!_defaultSubjectSelected ||
            (_subject != null && !_subjects.contains(_subject))) {
          final recent =
              _grades!
                  .where((g) => g['deleted'] != true && g['subject'] != null)
                  .toList()
                ..sort(
                  (a, b) => (b['exam_date'] as String? ?? '').compareTo(
                    a['exam_date'] as String? ?? '',
                  ),
                );
          _subject = recent.isEmpty ? null : recent.first['subject'] as String;
          _defaultSubjectSelected = recent.isNotEmpty;
        }
        _trend = null;
        _loadError = null;
      });
      if (_grades!.isNotEmpty) await _loadTrend();
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
        setState(() => _loadError = tr("学习记录加载失败，请检查网络后重试"));
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
      final t = await Api.I.parentGradeTrend(
        widget.studentId,
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
    final formKey = GlobalKey<FormState>();
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(current == null ? tr("新增成绩") : tr("编辑成绩")),
        content: SizedBox(
          width: 360,
          child: SingleChildScrollView(
            child: Form(
              key: formKey,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  for (final key in [
                    'subject',
                    'exam_date',
                    'score',
                    'max_score',
                  ]) ...[
                    TextFormField(
                      controller: form[key],
                      readOnly: key == 'exam_date',
                      decoration: InputDecoration(
                        labelText: _label(key),
                        suffixIcon: key == 'exam_date'
                            ? const Icon(Icons.calendar_today)
                            : null,
                      ),
                      keyboardType: {'score', 'max_score'}.contains(key)
                          ? const TextInputType.numberWithOptions(decimal: true)
                          : TextInputType.text,
                      onTap: key == 'exam_date'
                          ? () async {
                              final chosen = await showDatePicker(
                                context: ctx,
                                initialDate:
                                    DateTime.tryParse(date.text) ??
                                    DateTime.now(),
                                firstDate: DateTime(2000),
                                lastDate: DateTime(2100),
                              );
                              if (chosen != null) {
                                date.text = chosen.toIso8601String().substring(
                                  0,
                                  10,
                                );
                              }
                            }
                          : null,
                      validator: (value) {
                        if ((value ?? '').trim().isEmpty) return tr("请填写此项");
                        if (key == 'score' || key == 'max_score') {
                          final number = double.tryParse(value!);
                          if (number == null ||
                              !number.isFinite ||
                              number < 0 ||
                              (key == 'max_score' && number == 0)) {
                            return tr("请输入有效分数");
                          }
                          if (key == 'score' &&
                              number >
                                  (double.tryParse(max.text) ??
                                      double.infinity)) {
                            return tr("得分不能超过满分");
                          }
                        }
                        return null;
                      },
                    ),
                    const SizedBox(height: 12),
                  ],
                  ExpansionTile(
                    tilePadding: EdgeInsets.zero,
                    title: Text(tr("更多信息（选填）")),
                    children: [
                      TextField(
                        controller: title,
                        decoration: InputDecoration(labelText: tr("考试/作业名称")),
                      ),
                      const SizedBox(height: 12),
                      DropdownButtonFormField<String>(
                        value: gradeType.text,
                        decoration: InputDecoration(labelText: tr("成绩类型")),
                        items: ['exam', 'homework', 'quiz', 'other']
                            .map(
                              (type) => DropdownMenuItem(
                                value: type,
                                child: Text(_typeLabel(type)),
                              ),
                            )
                            .toList(),
                        onChanged: (value) {
                          if (value != null) gradeType.text = value;
                        },
                      ),
                      const SizedBox(height: 12),
                      TextField(
                        controller: term,
                        decoration: InputDecoration(labelText: tr("学期")),
                      ),
                      const SizedBox(height: 12),
                      TextField(
                        controller: note,
                        minLines: 2,
                        maxLines: 4,
                        decoration: InputDecoration(labelText: tr("备注")),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: Text(tr("取消")),
          ),
          FilledButton(
            onPressed: () {
              if (formKey.currentState!.validate()) Navigator.pop(ctx, true);
            },
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
      'term': term.text,
      'grade_type': gradeType.text,
      'note': note.text,
      'reason': current == null ? 'created' : 'edited',
    };
    await _changeGrade(() async {
      if (current == null) {
        await Api.I.addParentGrade(widget.studentId, body);
      } else {
        await Api.I.editParentGrade(
          widget.studentId,
          current['id'] as int,
          body,
        );
      }
    }, current == null ? tr("成绩已添加") : tr("成绩已保存"));
  }

  String _label(String key) =>
      {
        'subject': tr("科目"),
        'title': tr("考试/作业名称"),
        'exam_date': tr("日期"),
        'score': tr("得分"),
        'max_score': tr("满分"),
        'term': tr("学期"),
        'grade_type': tr("成绩类型（exam/homework/quiz/other）"),
        'note': tr("备注"),
      }[key] ??
      key;

  String _typeLabel(String type) => switch (type) {
    'exam' => tr("考试"),
    'homework' => tr("作业"),
    'quiz' => tr("测验"),
    _ => tr("其他"),
  };

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
                title: Text(tr("编辑")),
                onTap: () => Navigator.pop(ctx, 'edit'),
              ),
            ListTile(
              leading: const Icon(Icons.history),
              title: Text(tr("查看修改历史")),
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
            title: Text(tr("成绩修改历史")),
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
    if (action == 'delete') {
      await _changeGrade(
        () => Api.I.deleteParentGrade(widget.studentId, grade['id'] as int),
        tr("成绩已删除，可在“显示已删除成绩”中恢复"),
      );
    }
    if (action == 'restore') {
      await _changeGrade(
        () => Api.I.restoreParentGrade(widget.studentId, grade['id'] as int),
        tr("成绩已恢复"),
      );
    }
  }

  Future<void> _assess() async {
    // 规格 7.3：按时间范围触发学业评估
    final range = await chooseAssessmentRange(context);
    if (range == null || !mounted) return;
    setState(() => _assessmentAction = 'academic');
    try {
      final result = await Api.I.parentAcademicAssessment(
        widget.studentId,
        from: range.from,
        to: range.to,
      );
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
      if (mounted) setState(() => _assessmentAction = null);
    }
  }

  Future<void> _runWellbeing() async {
    // 规格 8.3：提示基于明确时间范围内的对话证据，触发前先选范围
    final range = await chooseAssessmentRange(context);
    if (range == null || !mounted) return;
    setState(() => _assessmentAction = 'wellbeing');
    try {
      final result = await Api.I.parentWellbeingAssessment(
        widget.studentId,
        from: range.from,
        to: range.to,
      );
      if (mounted) {
        setState(() => _wellbeingRows = [result, ...?_wellbeingRows]);
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(tr("身心状态关注结果已更新"))));
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
        ).showSnackBar(SnackBar(content: Text(tr("生成失败，请检查网络后重试"))));
      }
    } finally {
      if (mounted) setState(() => _assessmentAction = null);
    }
  }

  @override
  Widget build(BuildContext context) {
    AppLanguage.watch(context);
    return Scaffold(
      appBar: AppBar(title: Text(tr("{0} · 成绩与成长", [widget.studentName]))),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _changingGrade ? null : () => _addOrEdit(),
        icon: const Icon(Icons.add),
        label: Text(tr("新增成绩")),
      ),
      body: _grades == null
          ? Center(
              child: _loadError == null
                  ? const CircularProgressIndicator()
                  : Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(trMessage(_loadError!)),
                        TextButton(
                          onPressed: () {
                            setState(() => _loadError = null);
                            _load();
                          },
                          child: Text(tr("重试")),
                        ),
                      ],
                    ),
            )
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView(
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 96),
                children: [
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      OutlinedButton.icon(
                        onPressed: _assessmentAction == null ? _assess : null,
                        icon: const Icon(Icons.insights),
                        label: Text(
                          _assessmentAction == 'academic'
                              ? tr("处理中…")
                              : tr("学业评估"),
                        ),
                      ),
                      OutlinedButton.icon(
                        onPressed: _assessmentAction == null
                            ? _runWellbeing
                            : null,
                        icon: const Icon(Icons.favorite_border),
                        label: Text(
                          _assessmentAction == 'wellbeing'
                              ? tr("处理中…")
                              : tr("身心状态关注"),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  if (_trendLoading)
                    const LinearProgressIndicator(minHeight: 2),
                  if (_grades!.isNotEmpty)
                    GradeTrendCard(
                      trend: _trend,
                      subjects: _subjects,
                      subject: _subject,
                      rangeDays: _rangeDays,
                      onChanged: (subject, rangeDays) {
                        setState(() {
                          _subject = subject;
                          _rangeDays = rangeDays;
                          _trend = null;
                        });
                        _loadTrend();
                      },
                    ),
                  if (_assessment != null) _assessmentCard(),
                  if (_academicRows?.isNotEmpty == true) _academicHistoryCard(),
                  if (_wellbeingRows != null)
                    ..._wellbeingRows!.map(_wellbeingCard),
                  if (_grades!.isEmpty)
                    Card(
                      child: Padding(
                        padding: const EdgeInsets.all(28),
                        child: Column(
                          children: [
                            Icon(
                              Icons.insights_outlined,
                              size: 40,
                              color: Theme.of(context).colorScheme.primary,
                            ),
                            const SizedBox(height: 12),
                            Text(
                              tr("还没有成绩记录"),
                              style: Theme.of(context).textTheme.titleMedium,
                            ),
                            const SizedBox(height: 8),
                            Text(tr("添加成绩后即可查看趋势")),
                          ],
                        ),
                      ),
                    ),
                  ExpansionTile(
                    tilePadding: EdgeInsets.zero,
                    title: Text(tr("成绩显示选项")),
                    children: [
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
                    ],
                  ),
                  ..._grades!
                      .where(
                        (g) => _subject == null || g['subject'] == _subject,
                      )
                      .map(
                        (g) => Card(
                          margin: const EdgeInsets.only(bottom: 12),
                          child: ListTile(
                            onTap: () => _showGrade(g as Map<String, dynamic>),
                            title: Text(
                              '${g['subject']} · ${g['title'] ?? ''}',
                            ),
                            subtitle: Text(
                              '${g['exam_date']} · ${g['term'] ?? ''} · ${_typeLabel(g['grade_type'] as String? ?? 'exam')}',
                            ),
                            trailing: Text('${g['score']}/${g['max_score']}'),
                          ),
                        ),
                      ),
                ],
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
          return tr("{0}（学习记录 {1}）", [
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
            Text(
              (_assessment?['recommendations'] as List?)
                      ?.map((value) => trMessage(value.toString()))
                      .join(', ') ??
                  tr("暂无建议"),
            ),
            if (evidence.isNotEmpty)
              Text(
                tr("参考学习记录：{0}", [evidence]),
                style: const TextStyle(fontSize: 12),
              ),
            Text(
              tr("AI 辅助估计，不是学校成绩或诊断。"),
              style: TextStyle(fontSize: 12, color: Colors.grey),
            ),
          ],
        ),
      ),
    );
  }

  Widget _academicHistoryCard() => Card(
    child: ExpansionTile(
      title: Text(tr("学业评估历史（{0}）", [_academicRows!.length])),
      children: _academicRows!.map((raw) {
        final item = raw as Map<String, dynamic>;
        final period = item['period'] as Map<String, dynamic>?;
        final subjects = (item['subjects'] as List?) ?? const [];
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
            subjects.isEmpty
                ? tr("暂无识别到学科主题")
                : subjects
                      .map((s) => trMessage((s as Map)['subject'].toString()))
                      .join('、'),
          ),
        );
      }).toList(),
    ),
  );
  Widget _wellbeingCard(dynamic value) {
    final item = value as Map<String, dynamic>;
    final signals = (item['signals'] as List?) ?? const [];
    final period = item['period'] as Map<String, dynamic>?;
    return Card(
      child: ExpansionTile(
        leading: const Icon(Icons.favorite, color: Colors.orange),
        title: Text(tr("身心状态关注提示")),
        subtitle: Text(
          signals.isEmpty
              ? tr("暂未发现需要关注的表达")
              : signals
                    .map((s) => trMessage((s as Map)['summary'].toString()))
                    .join('、'),
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
                itemBuilder: (_) => [
                  PopupMenuItem(value: 'acknowledged', child: Text(tr("已关注"))),
                  PopupMenuItem(value: 'not_needed', child: Text(tr("无需跟进"))),
                ],
              )
            : const Icon(Icons.check),
        children: [
          ListTile(
            dense: true,
            title: Text(
              tr("时间范围：{0} 至 {1} · 模型 {2}", [
                period?['from'] ?? '-',
                period?['to'] ?? '-',
                item['model'] ?? '-',
              ]),
            ),
          ),
          ...signals.expand((raw) {
            final signal = raw as Map<String, dynamic>;
            final evidence = (signal['evidence'] as List?) ?? const [];
            return [
              ListTile(
                dense: true,
                title: Text('${signal['type']} · ${signal['level']}'),
                subtitle: Text(
                  evidence.isEmpty
                      ? tr("暂无原文证据")
                      : evidence
                            .map((e) => (e as Map)['excerpt'] ?? '')
                            .join('\n'),
                ),
              ),
            ];
          }),
          // 规格 8.2/8.3：家长看到的是信号而非事实认定，必须展示免责声明
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
            child: Text(
              item['disclaimer'] as String? ?? tr("这不是医疗诊断，请结合实际沟通判断。"),
              style: const TextStyle(fontSize: 11, color: Colors.grey),
            ),
          ),
        ],
      ),
    );
  }
}
