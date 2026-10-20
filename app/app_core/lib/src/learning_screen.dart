import 'language.dart';
import 'package:flutter/material.dart';
import 'api.dart';
import 'display_date.dart';

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
    final values = await showDialog<List<String>>(
      context: context,
      builder: (_) => _RewardProposalDialog(initialValues: _proposal),
    );
    if (values == null || !mounted) return;
    final count = int.parse(values[1]);
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
              Card(
                color: Theme.of(context).colorScheme.primaryContainer,
                child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Icon(Icons.auto_awesome, size: 32),
                      const SizedBox(height: 12),
                      Text(
                        tr("小行星 {0} 颗", [_data!['balance']]),
                        style: Theme.of(context).textTheme.headlineSmall,
                      ),
                      const SizedBox(height: 8),
                      Text(
                        tr("累计获得 {0} · 已兑换 {1}", [
                          _data!['earned'],
                          _data!['spent'],
                        ]),
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 12),
              Card(
                child: ExpansionTile(
                  title: Text(tr("奖励规则")),
                  childrenPadding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
                  expandedCrossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(trMessage(_data!['rule'] as String)),
                    const SizedBox(height: 8),
                    Text(tr("这是参与奖励，不代表已经掌握知识。懂了、不懂、继续讲解都同样值得鼓励。")),
                    const SizedBox(height: 8),
                    Text(tr("反馈可以更新，变化会保留；懂了比例仅供了解学习过程，不用于评分。")),
                  ],
                ),
              ),
              const SizedBox(height: 16),
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 12),
                child: Text(
                  tr("双方约定的奖励"),
                  style: Theme.of(context).textTheme.titleMedium,
                ),
              ),
              if (_isParent)
                FilledButton(
                  onPressed: _saving ? null : _propose,
                  child: Text(tr("约定新奖励")),
                ),
              if ((_data!['agreements'] as List).isEmpty)
                Text(
                  (_isParent
                      ? tr("还没有约定，先一起商量想兑换什么吧。")
                      : tr("还没有约定，先和家长商量想兑换什么吧。")),
                ),
              for (final agreement in _data!['agreements'] as List)
                Card(
                  margin: const EdgeInsets.only(bottom: 12),
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
                              ? (_isParent ? tr("孩子已确认") : tr("你已确认"))
                              : (_isParent ? tr("等待孩子确认") : tr("等待你确认")),
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
              if ((_data!['days'] as List).isEmpty &&
                  (_data!['history'] as List).isEmpty)
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(20),
                    child: Text(
                      _isParent
                          ? tr("孩子在对话中反馈后，这里会显示学习反馈与小行星变化。")
                          : tr("你在对话中反馈后，这里会显示学习反馈与小行星变化。"),
                    ),
                  ),
                ),
              if ((_data!['days'] as List).isNotEmpty) ...[
                const SizedBox(height: 16),
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 12),
                  child: Text(
                    tr("每日反馈分布（含反馈更新）"),
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ),
                for (final day in _data!['days'] as List)
                  Card(
                    margin: const EdgeInsets.only(bottom: 12),
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
              ],
              if ((_data!['redemptions'] as List).isNotEmpty) ...[
                const SizedBox(height: 16),
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 12),
                  child: Text(
                    tr("奖励兑换记录"),
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ),
                for (final row in _data!['redemptions'] as List)
                  Card(
                    margin: const EdgeInsets.only(bottom: 12),
                    child: ListTile(
                      title: Text(
                        tr("{0} · {1} 颗", [row['reward'], row['stars']]),
                      ),
                      subtitle: Text(
                        tr("{0}\n兑现时间：{1}\n{2}", [
                          displayDate(row['created_at']),
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
              ],
              if ((_data!['history'] as List).isNotEmpty) ...[
                const SizedBox(height: 16),
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 12),
                  child: Text(
                    tr("反馈变化记录"),
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ),
                for (final event in _data!['history'] as List)
                  ListTile(
                    title: Text(
                      tr("回答 #{0} · {1}", [
                        event['message_id'],
                        trMessage(event['label'].toString()),
                      ]),
                    ),
                    subtitle: Text(displayDate(event['created_at'])),
                  ),
              ],
            ],
          ],
        ),
      ),
    );
  }
}

class _RewardProposalDialog extends StatefulWidget {
  const _RewardProposalDialog({this.initialValues});

  final List<String>? initialValues;

  @override
  State<_RewardProposalDialog> createState() => _RewardProposalDialogState();
}

class _RewardProposalDialogState extends State<_RewardProposalDialog> {
  final _formKey = GlobalKey<FormState>();
  late final _reward = TextEditingController(text: widget.initialValues?[0]);
  late final _stars = TextEditingController(
    text: widget.initialValues?[1] ?? '1',
  );
  late final _fulfillment = TextEditingController(
    text: widget.initialValues?[2],
  );

  @override
  void dispose() {
    _reward.dispose();
    _stars.dispose();
    _fulfillment.dispose();
    super.dispose();
  }

  void _submit() {
    if (!_formKey.currentState!.validate()) return;
    Navigator.of(
      context,
    ).pop([_reward.text.trim(), _stars.text.trim(), _fulfillment.text.trim()]);
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: Text(tr("和孩子约定奖励")),
    content: SingleChildScrollView(
      child: Form(
        key: _formKey,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(tr("建议选择共同活动或周末安排。基本陪伴和生活需要不应作为兑换条件。保存后由孩子确认。")),
            const SizedBox(height: 16),
            TextFormField(
              controller: _reward,
              maxLength: 200,
              textInputAction: TextInputAction.next,
              decoration: InputDecoration(
                labelText: tr("奖励内容"),
                hintText: tr("例如：周末一起去公园"),
              ),
              validator: (value) =>
                  value == null || value.trim().isEmpty ? tr("请填写此项") : null,
            ),
            TextFormField(
              controller: _stars,
              keyboardType: TextInputType.number,
              textInputAction: TextInputAction.next,
              decoration: InputDecoration(
                labelText: tr("所需小行星"),
                errorMaxLines: 2,
                prefixIcon: IconButton(
                  tooltip: tr("减少"),
                  icon: const Icon(Icons.remove),
                  onPressed: () => _stars.text =
                      '${((int.tryParse(_stars.text) ?? 1) - 1).clamp(1, 100000)}',
                ),
                suffixIcon: IconButton(
                  tooltip: tr("增加"),
                  icon: const Icon(Icons.add),
                  onPressed: () => _stars.text =
                      '${((int.tryParse(_stars.text) ?? 1) + 1).clamp(1, 100000)}',
                ),
              ),
              validator: (value) {
                final count = int.tryParse(value?.trim() ?? '');
                return count == null || count < 1 || count > 100000
                    ? tr("请输入 1–100000 的整数")
                    : null;
              },
            ),
            const SizedBox(height: 16),
            TextFormField(
              controller: _fulfillment,
              maxLength: 100,
              textInputAction: TextInputAction.done,
              onFieldSubmitted: (_) => _submit(),
              decoration: InputDecoration(
                labelText: tr("兑现时间"),
                hintText: tr("例如：兑换后当周周末"),
              ),
              validator: (value) =>
                  value == null || value.trim().isEmpty ? tr("请填写此项") : null,
            ),
          ],
        ),
      ),
    ),
    actions: [
      TextButton(
        onPressed: () => Navigator.of(context).pop(),
        child: Text(tr("取消")),
      ),
      FilledButton(onPressed: _submit, child: Text(tr("邀请孩子确认"))),
    ],
  );
}
