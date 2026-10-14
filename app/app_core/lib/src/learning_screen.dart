import 'language.dart';
import 'package:flutter/material.dart';
import 'api.dart';

class LearningScreen extends StatefulWidget {
  final int? studentId;
  const LearningScreen({super.key, this.studentId});
  @override
  State<LearningScreen> createState() => _LearningScreenState();
}

class _LearningScreenState extends State<LearningScreen> {
  Map<String, dynamic>? _data;
  String? _error;
  bool _saving = false;
  final Map<int, String> _redemptionRequests = {};
  String? _proposalRequest;
  List<String>? _proposal;
  bool get _isParent => widget.studentId != null;
  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final data = await Api.I.learningSummary(studentId: widget.studentId);
      if (mounted) {
        setState(() {
          _data = data;
          _error = null;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() => _error = e is ApiException ? e.message : tr("加载失败，请重试"));
      }
    }
  }

  Future<void> _run(Future<Map<String, dynamic>> Function() operation) async {
    if (_saving) return;
    setState(() => _saving = true);
    try {
      final data = await operation();
      if (mounted) setState(() => _data = data);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(e is ApiException ? e.message : tr("操作失败，请重试")),
          ),
        );
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _propose() async {
    final reward = TextEditingController(text: _proposal?[0]);
    final stars = TextEditingController(text: _proposal?[1] ?? '1');
    final fulfillment = TextEditingController(text: _proposal?[2]);
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(tr("和孩子约定奖励")),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(tr("建议选择共同活动或周末安排。基本陪伴和生活需要不应作为兑换条件。保存后由孩子确认。")),
              TextField(
                controller: reward,
                maxLength: 200,
                decoration: InputDecoration(labelText: tr("奖励内容")),
              ),
              TextField(
                controller: stars,
                keyboardType: TextInputType.number,
                decoration: InputDecoration(labelText: tr("所需小行星")),
              ),
              TextField(
                controller: fulfillment,
                maxLength: 100,
                decoration: InputDecoration(
                  labelText: tr("兑现时间"),
                  hintText: tr("例如：兑换后当周周末"),
                ),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: Text(tr("取消")),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: Text(tr("邀请孩子确认")),
          ),
        ],
      ),
    );
    final values = [
      reward.text.trim(),
      stars.text.trim(),
      fulfillment.text.trim(),
    ];
    reward.dispose();
    stars.dispose();
    fulfillment.dispose();
    if (confirmed != true || !mounted) return;
    final count = int.tryParse(values[1]);
    if (values[0].isEmpty ||
        values[2].isEmpty ||
        count == null ||
        count < 1 ||
        count > 100000) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(tr("请填写奖励、兑现时间和有效的小行星数量"))));
      return;
    }
    if (_proposal?.join('\n') != values.join('\n')) _proposalRequest = null;
    _proposal = values;
    _proposalRequest ??= '${DateTime.now().microsecondsSinceEpoch}';
    await _run(() async {
      final data = await Api.I.proposeReward(
        widget.studentId!,
        values[0],
        count,
        values[2],
        _proposalRequest!,
      );
      _proposalRequest = null;
      _proposal = null;
      return data;
    });
  }

  Future<void> _redeem(Map<String, dynamic> agreement) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(tr("确认兑换")),
        content: Text(
          tr("{0}\n扣除 {1} 颗小行星\n兑现时间：{2}", [
            agreement['reward'],
            agreement['stars'],
            agreement['fulfillment'],
          ]),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: Text(tr("取消")),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: Text(tr("确认兑换")),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    final id = agreement['id'] as int;
    final request = _redemptionRequests.putIfAbsent(
      id,
      () => '${DateTime.now().microsecondsSinceEpoch}',
    );
    await _run(() async {
      final data = await Api.I.redeemStars(widget.studentId, id, request);
      _redemptionRequests.remove(id);
      return data;
    });
  }

  @override
  Widget build(BuildContext context) {
    AppLanguage.watch(context);
    return Scaffold(
      appBar: AppBar(title: Text(tr("学习反馈与小行星"))),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            if (_error != null) ...[
              Text(trMessage(_error!)),
              TextButton(onPressed: _load, child: Text(tr("重试"))),
            ],
            if (_data == null && _error == null)
              const Center(child: CircularProgressIndicator()),
            if (_data != null) ...[
              Text(
                tr("小行星 {0} 颗", [_data!['balance']]),
                style: Theme.of(context).textTheme.headlineSmall,
              ),
              Text(
                tr("累计获得 {0} · 已兑换 {1}", [_data!['earned'], _data!['spent']]),
              ),
              Text(trMessage(_data!['rule'] as String)),
              Text(tr("这是参与奖励，不代表已经掌握知识。懂了、不懂、继续讲解都同样值得鼓励。")),
              Text(tr("反馈可以更新，变化会保留；懂了比例仅供了解学习过程，不用于评分。")),
              const SizedBox(height: 16),
              Text(tr("双方约定的奖励")),
              if (_isParent)
                FilledButton(
                  onPressed: _saving ? null : _propose,
                  child: Text(tr("约定新奖励")),
                ),
              if ((_data!['agreements'] as List).isEmpty)
                Text(tr("还没有约定，先一起商量想兑换什么吧。")),
              for (final agreement in _data!['agreements'] as List)
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(12),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          tr("{0} · {1} 颗", [
                            agreement['reward'],
                            agreement['stars'],
                          ]),
                        ),
                        Text(tr("兑现时间：{0}", [agreement['fulfillment']])),
                        Text(
                          agreement['accepted'] == true
                              ? tr("孩子已确认")
                              : tr("等待孩子确认"),
                        ),
                        if (!_isParent && agreement['accepted'] != true)
                          TextButton(
                            onPressed: _saving
                                ? null
                                : () => _run(
                                    () => Api.I.acceptReward(
                                      agreement['id'] as int,
                                    ),
                                  ),
                            child: Text(tr("我同意这个约定")),
                          ),
                        if (agreement['accepted'] == true)
                          TextButton(
                            onPressed:
                                _saving ||
                                    (_data!['balance'] as num) <
                                        (agreement['stars'] as num)
                                ? null
                                : () => _redeem(
                                    agreement as Map<String, dynamic>,
                                  ),
                            child: Text(tr("兑换奖励")),
                          ),
                      ],
                    ),
                  ),
                ),
              const SizedBox(height: 16),
              Text(tr("每日反馈分布（含反馈更新）")),
              if ((_data!['days'] as List).isEmpty) Text(tr("还没有学习反馈")),
              for (final day in _data!['days'] as List)
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(12),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          tr("{0} · {1} 次反馈 · 参与奖励 {2} 颗", [
                            day['date'],
                            day['total'],
                            day['stars'],
                          ]),
                        ),
                        for (final entry in {
                          'understood': tr("懂了"),
                          'not_understood': tr("不懂"),
                          'continue': tr("继续讲解"),
                        }.entries)
                          Text(
                            tr("{0}：{1} 次（{2}%）", [
                              entry.value,
                              day['counts'][entry.key],
                              ((day['ratios'][entry.key] as num) * 100)
                                  .toStringAsFixed(1),
                            ]),
                          ),
                      ],
                    ),
                  ),
                ),
              const SizedBox(height: 16),
              Text(tr("奖励兑换记录")),
              for (final row in _data!['redemptions'] as List)
                Card(
                  child: ListTile(
                    title: Text(
                      tr("{0} · {1} 颗", [row['reward'], row['stars']]),
                    ),
                    subtitle: Text(
                      tr("{0}\n兑现时间：{1}\n{2}", [
                        row['created_at'],
                        row['fulfillment'],
                        row['fulfilled'] == true ? tr("已兑现") : tr("待兑现"),
                      ]),
                    ),
                    trailing: _isParent && row['fulfilled'] != true
                        ? TextButton(
                            onPressed: _saving
                                ? null
                                : () => _run(
                                    () => Api.I.fulfillReward(
                                      widget.studentId!,
                                      row['id'] as int,
                                    ),
                                  ),
                            child: Text(tr("已兑现")),
                          )
                        : null,
                  ),
                ),
              const SizedBox(height: 16),
              Text(tr("反馈变化记录")),
              for (final event in _data!['history'] as List)
                ListTile(
                  title: Text(
                    tr("回答 #{0} · {1}", [
                      event['message_id'],
                      trMessage(event['label'].toString()),
                    ]),
                  ),
                  subtitle: Text('${event['created_at']}'),
                ),
            ],
          ],
        ),
      ),
    );
  }
}
